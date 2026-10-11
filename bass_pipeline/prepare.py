"""Extract verified archives and build unsplit, auditable note manifests."""

import json
import shutil
import stat
import subprocess
import tarfile
import zipfile
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import mido
import numpy as np
import soundfile as sf
import yaml

from bass_pipeline.audit import inspect_archive, repository_path, safe_member
from bass_pipeline.core import Note


def extract_archive(source: Path, destination: Path, checksum: str) -> dict:
    """Verify before writing; never use extractall or overwrite an existing tree.

    A failed extraction remains for inspection, without a completion marker.
    """
    if destination.exists():
        raise FileExistsError(destination)
    audit = inspect_archive(source, checksum)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < audit["uncompressed_bytes"] + 2**30:
        raise ValueError("insufficient space (requires 1 GiB reserve)")
    destination.mkdir()

    def copy(name, stream):
        safe_member(name)
        target = repository_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            shutil.copyfileobj(stream, output, length=1024 * 1024)

    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                safe_member(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("links not supported")
                if not member.is_dir():
                    with archive.open(member) as stream:
                        copy(member.filename, stream)
    else:
        with tarfile.open(source, "r|gz") as archive:
            for member in archive:
                safe_member(member.name)
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        copy(member.name, stream)
                elif not member.isdir():
                    raise ValueError("links/special files not supported")
    write_json(destination / "_extraction.json", audit)
    return audit


def write_json(path: Path, value) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def midi_notes(path: Path) -> list[Note]:
    """Merge tempo maps; pair note events by channel/pitch, not by track order.

    Ambiguous overlapping same-pitch notes and incomplete pairs fail explicitly.
    Sustain controllers are not interpreted as note extensions.
    """
    midi = mido.MidiFile(path)
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("asynchronous/SMPTE MIDI is not supported")
    active = {}
    notes = []
    tempo = 500000
    seconds = 0.0
    for event in mido.merge_tracks(midi.tracks):
        seconds += mido.tick2second(event.time, midi.ticks_per_beat, tempo)
        if event.type == "set_tempo":
            tempo = event.tempo
        elif event.type in ("note_on", "note_off"):
            key = (event.channel, event.note)
            if event.type == "note_on" and event.velocity > 0:
                if key in active:
                    raise ValueError(f"ambiguous overlapping MIDI note {key}")
                active[key] = seconds
            else:
                if key not in active:
                    raise ValueError(f"unmatched MIDI note-off {key}")
                notes.append(Note(event.note, active.pop(key), seconds))
    if active:
        raise ValueError("unterminated MIDI notes")
    return sorted(notes, key=lambda n: (n.onset_seconds, n.pitch_midi))


def idmt_notes(path: Path) -> tuple[str, list[Note], list[dict]]:
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML document types/entities are not supported")
    root = ElementTree.fromstring(raw)
    audio = root.findtext("globalParameter/audioFileName")
    if not audio or Path(audio).name != audio or "\\" in audio:
        raise ValueError("invalid IDMT audio filename")
    events = root.findall("transcription/event")
    notes = [
        Note(
            int(e.findtext("pitch")),
            float(e.findtext("onsetSec")),
            float(e.findtext("offsetSec")),
        )
        for e in events
    ]
    techniques = [
        {
            child.tag: child.text
            for child in e
            if child.tag not in ("pitch", "onsetSec", "offsetSec")
        }
        for e in events
    ]
    return audio, notes, techniques


def build_manifest(root: Path, extracted: Path, output: Path) -> dict:
    """Strict pairing, full audio decode checks, explicit quarantine; no splitting."""
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    (output / "notes").mkdir()
    rows, rejected = [], []

    def add(dataset, key, audio, labels, reader, context, bass_type, metadata=None):
        record_id = f"{dataset}-{key}"
        try:
            notes = reader(labels)
            if not notes:
                raise ValueError("empty annotation")
            info = sf.info(audio)
            # Decode in bounded blocks to catch truncation without loading whole songs.
            frames = 0
            peak = 0.0
            with sf.SoundFile(audio) as stream:
                for block in stream.blocks(blocksize=65536, always_2d=True):
                    if not np.isfinite(block).all():
                        raise ValueError("non-finite audio samples")
                    frames += len(block)
                    peak = max(peak, float(np.max(np.abs(block))))
            if frames != info.frames or info.duration <= 0:
                raise ValueError("audio frame count/duration mismatch")
            if max(n.offset_seconds for n in notes) > info.duration + 0.05:
                raise ValueError("annotation extends beyond audio by more than 50 ms")
            path = output / "notes" / f"{record_id}.json"
            write_json(path, [asdict(n) for n in notes])
            rows.append(
                {
                    "schema_version": "1.0",
                    "recording_id": record_id,
                    "dataset": dataset,
                    "group_id": dataset
                    + "-"
                    + (key.split("-")[0] if dataset == "babyslakh" else key),
                    "split": None,
                    "audio_path": str(audio.relative_to(root)),
                    "source_annotation_path": str(labels.relative_to(root)),
                    "annotation_path": str(path.relative_to(root)),
                    "bass_type": bass_type,
                    "audio_context": context,
                    "sample_rate": info.samplerate,
                    "channels": info.channels,
                    "duration_seconds": info.duration,
                    "note_count": len(notes),
                    "pitch_min": min(n.pitch_midi for n in notes),
                    "pitch_max": max(n.pitch_midi for n in notes),
                    "peak": peak,
                    "alignment_listening_reviewed": False,
                    "warnings": (
                        ["metadata render/save flags disagree with available files"]
                        if dataset == "babyslakh"
                        and (
                            not metadata.get("audio_rendered")
                            or not metadata.get("midi_saved")
                        )
                        else []
                    ),
                    "metadata": metadata or {},
                }
            )
        except (ValueError, RuntimeError, OSError) as error:
            rejected.append({"recording_id": record_id, "reason": str(error)})

    filo = extracted / "filobass" / "FiloBass ISMIR Publication"
    audio_files = {p.stem: p for p in (filo / "audio_bass_stems").glob("*.mp3")}
    midi_files = {p.stem: p for p in (filo / "midi_fully_aligned").glob("*.mid")}
    if not audio_files or audio_files.keys() != midi_files.keys():
        raise ValueError("FiloBass audio/MIDI pairing mismatch")
    for key in sorted(audio_files):
        add(
            "filobass",
            key,
            audio_files[key],
            midi_files[key],
            midi_notes,
            "separated_stem",
            "unknown",
        )

    idmt = extracted / "idmt_single_track"
    for labels in sorted((idmt / "annotation").glob("*.xml")):
        audio_name, notes, techniques = idmt_notes(labels)
        add(
            "idmt",
            labels.stem,
            idmt / "audio" / audio_name,
            labels,
            lambda _, notes=notes: notes,
            "isolated_recording",
            "electric",
            {"techniques_by_note": techniques},
        )

    for meta_path in sorted((extracted / "babyslakh").rglob("metadata.yaml")):
        metadata = yaml.safe_load(meta_path.read_text())
        track = meta_path.parent
        for stem, properties in sorted(metadata["stems"].items()):
            if properties["inst_class"] != "Bass" or properties["is_drum"]:
                continue
            if Path(stem).name != stem or "\\" in stem:
                raise ValueError("invalid stem ID")
            add(
                "babyslakh",
                f"{track.name}-{stem}",
                track / "stems" / f"{stem}.wav",
                track / "MIDI" / f"{stem}.mid",
                midi_notes,
                "synthetic_stem",
                "synthetic",
                {"source_uuid": metadata.get("UUID"), **properties},
            )

    counts = defaultdict(int)
    for row in rows:
        counts[row["dataset"]] += 1
    write_json(output / "manifest.json", rows)
    report = {
        "created_utc": datetime.now(UTC).isoformat(),
        "accepted": dict(counts),
        "quarantined": rejected,
        "status": "unsplit; alignment and pretraining overlap need review",
    }
    write_json(output / "report.json", report)
    if any(counts[d] == 0 for d in ("filobass", "idmt", "babyslakh")):
        raise ValueError("a dataset has no valid records; see report.json")
    return report


def main():
    import argparse
    import tomllib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["extract", "manifest"])
    parser.add_argument("--extracted", default="data/extracted/v1")
    parser.add_argument("--output", default="data/processed/v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    extracted = repository_path(root, args.extracted)
    output = repository_path(root, args.output)
    for path in (extracted, output):
        if not path.is_relative_to(root / "data") or path == root / "data":
            parser.error("destinations must be under data/")
    config = tomllib.loads((root / "configs/pipeline.toml").read_text())
    if args.command == "extract":
        if extracted.exists():
            parser.error("extraction destination exists; choose a new directory")
        extracted.mkdir(parents=True)
        for item in config["archives"]:
            print(f"Extracting {item['dataset']} ...", flush=True)
            extract_archive(
                repository_path(root, item["path"]),
                extracted / item["dataset"],
                item["md5"],
            )
    else:
        for item in config["archives"]:
            marker = extracted / item["dataset"] / "_extraction.json"
            if not marker.is_file():
                parser.error("missing successful extraction marker")
        print(json.dumps(build_manifest(root, extracted, output), indent=2))
        provenance = {
            "git_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "git_dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=root, text=True
                ).strip()
            ),
            "config": config,
            "extractions": {
                item["dataset"]: json.loads(
                    (extracted / item["dataset"] / "_extraction.json").read_text()
                )
                for item in config["archives"]
            },
        }
        write_json(output / "provenance.json", provenance)


if __name__ == "__main__":
    main()
