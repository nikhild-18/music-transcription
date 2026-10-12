"""Inclusive inspection inventory. Never determines training eligibility."""

import hashlib
import json
from pathlib import Path

import soundfile as sf
import yaml

from bass_pipeline.audit import repository_path


def source_inventory(root: Path):
    rows, errors = [], []

    def add(base, dataset, key, audio, label):
        rid = f"{dataset}-{key}"
        row = {
            "uid": hashlib.sha256(f"{base}:{rid}".encode()).hexdigest(),
            "run_id": str(base.relative_to(root)) + " / source inventory",
            "stage": "source inspection",
            "recording_id": rid,
            "dataset": dataset,
            "status": "not_run",
            "training_eligible": False,
            "audio_path": str(audio.relative_to(root)),
            "audio_origin": 0,
            "duration_seconds": 0,
            "layers": [],
            "warnings": [],
            "source_annotation_path": str(label.relative_to(root)),
            "steps": [],
        }
        for name, path in (
            ("audio availability", audio),
            ("annotation availability", label),
        ):
            try:
                repository_path(root, str(path.relative_to(root))).stat()
                row["steps"].append({"stage": name, "status": "succeeded"})
            except (OSError, ValueError):
                row["steps"].append(
                    {
                        "stage": name,
                        "status": "failed",
                        "error": "file missing or outside repository",
                    }
                )
                row["status"] = "failed"
        try:
            info = sf.info(repository_path(root, row["audio_path"]))
            row["duration_seconds"] = info.duration
            row["sample_rate"] = info.samplerate
            row["channels"] = info.channels
        except (OSError, ValueError, RuntimeError):
            row["steps"].append(
                {
                    "stage": "audio header",
                    "status": "failed",
                    "error": "audio header unreadable",
                }
            )
            row["status"] = "failed"
        rows.append(row)

    for base in (
        sorted((root / "data/extracted").iterdir())
        if (root / "data/extracted").exists()
        else []
    ):
        if not base.is_dir() or base.is_symlink():
            continue
        filo = base / "filobass" / "FiloBass ISMIR Publication"
        audio = {p.stem: p for p in (filo / "audio_bass_stems").glob("*.mp3")}
        labels = {p.stem: p for p in (filo / "midi_fully_aligned").glob("*.mid")}
        for key in sorted(audio.keys() | labels.keys()):
            add(
                base,
                "filobass",
                key,
                audio.get(key, filo / "audio_bass_stems" / f"{key}.mp3"),
                labels.get(key, filo / "midi_fully_aligned" / f"{key}.mid"),
            )
        idmt = base / "idmt_single_track"
        keys = {p.stem for p in (idmt / "audio").glob("*.wav")} | {
            p.stem for p in (idmt / "annotation").glob("*.xml")
        }
        for key in sorted(keys):
            add(
                base,
                "idmt",
                key,
                idmt / "audio" / f"{key}.wav",
                idmt / "annotation" / f"{key}.xml",
            )
        for path in sorted((base / "babyslakh").rglob("metadata.yaml")):
            try:
                safe = repository_path(root, str(path.relative_to(root)))
                metadata = yaml.safe_load(safe.read_text())
                for stem, properties in metadata["stems"].items():
                    if properties["inst_class"] == "Bass" and not properties["is_drum"]:
                        if Path(stem).name != stem or "\\" in stem:
                            raise ValueError("unsafe stem ID")
                        add(
                            base,
                            "babyslakh",
                            f"{path.parent.name}-{stem}",
                            path.parent / "stems" / f"{stem}.wav",
                            path.parent / "MIDI" / f"{stem}.mid",
                        )
            except (ValueError, OSError, KeyError, TypeError, yaml.YAMLError) as error:
                errors.append(f"{path.relative_to(root)}: {error}")
    # Attach historical outcomes only when a manifest points to this source tree.
    for manifest in sorted((root / "data/processed").rglob("manifest.json")):
        try:
            accepted = json.loads(
                repository_path(root, str(manifest.relative_to(root))).read_text()
            )
            report_path = manifest.parent / "report.json"
            report = json.loads(report_path.read_text()) if report_path.exists() else {}
            roots = {str(Path(r["audio_path"]).parts[:3]) for r in accepted}
            by_id = {r["recording_id"]: r for r in accepted}
            rejected = {
                r["recording_id"]: r["reason"] for r in report.get("quarantined", [])
            }
            for row in rows:
                if str(Path(row["audio_path"]).parts[:3]) not in roots:
                    continue
                rid = row["recording_id"]
                if rid in rejected:
                    row["status"] = "failed"
                    row["steps"].append(
                        {
                            "stage": "legacy preparation",
                            "status": "failed",
                            "error": rejected[rid],
                            "run": str(manifest.parent.relative_to(root)),
                        }
                    )
                elif rid in by_id and by_id[rid]["audio_path"] == row["audio_path"]:
                    row["steps"].append(
                        {
                            "stage": "legacy preparation",
                            "status": "succeeded",
                            "run": str(manifest.parent.relative_to(root)),
                        }
                    )
                    if row["status"] != "failed":
                        row["status"] = "needs_review"
                    row["layers"] = [
                        {
                            "id": "reference",
                            "kind": "reference",
                            "path": by_id[rid]["annotation_path"],
                            "time_origin_seconds": 0,
                        }
                    ]
        except (ValueError, OSError, KeyError, TypeError) as error:
            errors.append(f"{manifest.relative_to(root)}: {error}")
    exclusion_path = root / "configs/exclusions.json"
    exclusions = (
        json.loads(exclusion_path.read_text()) if exclusion_path.exists() else {}
    )
    for row in rows:
        if row["recording_id"] in exclusions:
            row["status"] = "excluded"
            row["steps"].append(
                {
                    "stage": "owner exclusion",
                    "status": "excluded",
                    "error": exclusions[row["recording_id"]]["reason"],
                }
            )
    return rows, errors
