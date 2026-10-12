"""Non-destructive MIDI onset proximity report; never merges or repairs notes."""

import argparse
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

import mido

from bass_pipeline.audit import repository_path
from bass_pipeline.inventory import source_inventory
from bass_pipeline.midi_diagnostics import midi_issues
from bass_pipeline.prepare import write_json
from bass_pipeline.repair import (
    PitchConfig,
    SilenceConfig,
    pitch_evidence,
    silence_evidence,
)


def leading_stops(path):
    midi = mido.MidiFile(path)
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("unsupported MIDI timing")
    seconds, tempo = 0.0, 500000
    seen, stops = set(), []
    for event in mido.merge_tracks(midi.tracks):
        seconds += mido.tick2second(event.time, midi.ticks_per_beat, tempo)
        if event.type == "set_tempo":
            tempo = event.tempo
        elif event.type in ("note_on", "note_off"):
            key = (event.channel, event.note)
            if event.type == "note_on" and event.velocity > 0:
                seen.add(key)
            elif key not in seen:
                stops.append(
                    {
                        "pitch_midi": event.note,
                        "channel": event.channel,
                        "stop_seconds": seconds,
                    }
                )
    return stops


def nearby_starts(path: Path, threshold_ms: float = 20) -> list[dict]:
    if not math.isfinite(threshold_ms) or threshold_ms < 0:
        raise ValueError("threshold must be finite and nonnegative")
    midi = mido.MidiFile(path)
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("unsupported MIDI timing")
    seconds, tick, tempo = 0.0, 0, 500000
    previous, last_stop = {}, {}
    candidates = []
    for event in mido.merge_tracks(midi.tracks):
        seconds += mido.tick2second(event.time, midi.ticks_per_beat, tempo)
        tick += event.time
        if event.type == "set_tempo":
            tempo = event.tempo
        elif event.type in ("note_on", "note_off"):
            key = (event.channel, event.note)
            if event.type == "note_off" or event.velocity == 0:
                last_stop[key] = tick
                continue
            if key in previous:
                old_time, old_tick, old_velocity = previous[key]
                gap = (seconds - old_time) * 1000
                if gap <= threshold_ms + 1e-9:
                    candidates.append(
                        {
                            "pitch_midi": event.note,
                            "channel": event.channel,
                            "first_start_seconds": old_time,
                            "second_start_seconds": seconds,
                            "gap_ms": gap,
                            "first_velocity": old_velocity,
                            "second_velocity": event.velocity,
                            "exact_duplicate_start": tick == old_tick
                            and event.velocity == old_velocity,
                            "stop_since_previous_start": key in last_stop
                            and last_stop[key] >= old_tick,
                            "local_bpm_at_second_start": 60000000 / tempo,
                            "local_32nd_duration_ms": tempo / 8000,
                            "action": "review_only",
                        }
                    )
            previous[key] = (seconds, tick, event.velocity)
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold-ms", type=float, default=20)
    parser.add_argument("--output", required=True)
    parser.add_argument("--orphan-pitch", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = repository_path(root, args.output)
    if not destination.is_relative_to(root / "outputs"):
        parser.error("report must be under outputs/")
    if destination.exists():
        parser.error("report exists; choose a new filename")
    rows, inventory_errors = source_inventory(root)
    results = []
    started = time.perf_counter()
    for row in rows:
        if row.get("status") == "excluded":
            continue
        source = row["source_annotation_path"]
        if Path(source).suffix.lower() not in (".mid", ".midi"):
            continue
        entry = {"recording_id": row["recording_id"], "source_path": source}
        try:
            entry["structural_issues"] = midi_issues(repository_path(root, source))
            for issue in entry["structural_issues"]:
                if issue["code"] == "orphan_stop" and issue["leading"]:
                    issue["silence_evidence"] = silence_evidence(
                        repository_path(root, row["audio_path"]), issue["start_seconds"]
                    )
            entry["candidates"] = nearby_starts(
                repository_path(root, source), args.threshold_ms
            )
            if args.orphan_pitch:
                entry["orphan_proposals"] = []
                for stop in leading_stops(repository_path(root, source)):
                    evidence = pitch_evidence(
                        repository_path(root, row["audio_path"]),
                        stop["pitch_midi"],
                        stop["stop_seconds"],
                    )
                    entry["orphan_proposals"].append({**stop, **evidence})
        except (ValueError, OSError, EOFError, RuntimeError) as error:
            entry["error"] = str(error)
        results.append(entry)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "threshold_ms": args.threshold_ms,
        "mode": "diagnostic_only",
        "policy": "adjacent same-channel/pitch starts; no transitive merging",
        "tempo_warning": "MIDI tempo may be a timing encoding, not musical tempo",
        "inventory_errors": inventory_errors,
        "recordings": results,
        "elapsed_seconds": time.perf_counter() - started,
        "pitch_config": asdict(PitchConfig()) if args.orphan_pitch else None,
        "silence_config": asdict(SilenceConfig()),
    }
    write_json(destination, report)
    print(
        json.dumps(
            {
                "recordings": len(results),
                "candidate_pairs": sum(len(r.get("candidates", [])) for r in results),
                "report": args.output,
            }
        )
    )


if __name__ == "__main__":
    main()
