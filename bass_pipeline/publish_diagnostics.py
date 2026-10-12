"""Publish a saved MIDI diagnostic report using the generic viewer contract."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from bass_pipeline.audit import repository_path
from bass_pipeline.inventory import source_inventory
from bass_pipeline.prepare import midi_notes
from bass_pipeline.repair import remove_silent_leading_stops


def diagnostic_events(entry):
    events = []
    for issue in entry.get("structural_issues", []):
        events.append(
            {
                "id": f"structure-{issue['event_index']}-{issue['code']}",
                "start_seconds": issue["start_seconds"],
                "label": issue["label"],
                "severity": "error",
                "status": "unresolved",
                "details": issue,
            }
        )
    for index, pair in enumerate(entry.get("candidates", [])):
        events.append(
            {
                "id": f"nearby-start-{index}",
                "start_seconds": pair["first_start_seconds"],
                "end_seconds": pair["second_start_seconds"],
                "label": "Exact duplicate start"
                if pair["exact_duplicate_start"]
                else "Nearby note starts",
                "severity": "warning",
                "status": "review_only",
                "details": pair,
            }
        )
    for index, orphan in enumerate(entry.get("orphan_proposals", [])):
        if "structural_issues" in entry:
            continue  # Already represented by the parser issue, not a duplicate marker.
        events.append(
            {
                "id": f"orphan-stop-{index}",
                "start_seconds": orphan["stop_seconds"],
                "label": "Leading orphan stop",
                "severity": "error",
                "status": orphan["status"],
                "details": orphan,
            }
        )
    return events


def publish(root, report_path, destination, repair_recordings=()):
    root = root.resolve()
    destination = repository_path(root, str(destination.relative_to(root)))
    if not destination.is_relative_to(root / "outputs/diagnostics"):
        raise ValueError("destination must be under outputs/diagnostics")
    if destination.exists():
        raise ValueError("destination exists; choose a new run directory")
    report_path = repository_path(root, str(report_path.relative_to(root)))
    raw = report_path.read_bytes()
    report = json.loads(raw)
    sources, errors = source_inventory(root)
    if errors:
        raise ValueError(f"source inventory errors: {errors}")
    by_source = {(r["recording_id"], r["source_annotation_path"]): r for r in sources}
    available = {entry["recording_id"] for entry in report["recordings"]}
    if set(repair_recordings) - available:
        raise ValueError("requested repair recording absent from report")
    destination.mkdir(parents=True, exist_ok=False)
    recordings, payloads = [], []
    for index, entry in enumerate(report["recordings"]):
        source = by_source[(entry["recording_id"], entry["source_path"])]
        event_path = destination / f"events-{index:04d}.json"
        events = diagnostic_events(entry)
        layers = list(source["layers"])
        status = source["status"]
        steps = list(source["steps"])
        if source["recording_id"] in repair_recordings:
            derived = destination / f"repaired-{index:04d}.mid"
            removed = remove_silent_leading_stops(
                repository_path(root, source["source_annotation_path"]),
                repository_path(root, source["audio_path"]),
                derived,
            )
            removed_indices = {issue["event_index"] for issue in removed}
            for event in events:
                if (
                    event["id"].startswith("structure-")
                    and event["details"]["event_index"] in removed_indices
                ):
                    event["status"] = "removed_in_derived_midi"
                    event["severity"] = "info"
            step = {
                "stage": "quiet-prefix-v1",
                "removed_stops": removed,
                "status": "no_change",
                "source_midi_sha256": hashlib.sha256(
                    repository_path(root, source["source_annotation_path"]).read_bytes()
                ).hexdigest(),
            }
            if removed:
                step.update(
                    status="derived_midi_written", path=str(derived.relative_to(root))
                )
                try:
                    notes = midi_notes(derived)
                    notes_path = destination / f"repaired-notes-{index:04d}.json"
                    payloads.append((notes_path, [asdict(n) for n in notes]))
                    layers.append(
                        {
                            "id": "repaired-reference",
                            "kind": "reference",
                            "path": str(notes_path.relative_to(root)),
                            "time_origin_seconds": 0,
                        }
                    )
                    status = "needs_review"
                except ValueError as error:
                    step["remaining_error"] = str(error)
            steps.append(step)
        payloads.append((event_path, events))
        recordings.append(
            {
                "recording_id": source["recording_id"],
                "source_recording_id": source["recording_id"],
                "source_annotation_path": source["source_annotation_path"],
                "dataset": source["dataset"],
                "duration_seconds": source["duration_seconds"],
                "status": status,
                "training_eligible": False,
                "steps": steps
                + [
                    {
                        "stage": "diagnostics",
                        "status": "review_only",
                        "event_count": len(events),
                        "error": entry.get("error"),
                    }
                ],
                "audio": {"path": source["audio_path"], "time_origin_seconds": 0},
                "layers": layers
                + [
                    {
                        "id": "diagnostics",
                        "kind": "events",
                        "path": str(event_path.relative_to(root)),
                        "time_origin_seconds": 0,
                    }
                ],
            }
        )
    descriptor = {
        "schema_version": "1.0",
        "run_id": destination.name,
        "stage": "diagnostics · review only",
        "provenance": {
            "source_report": str(report_path.relative_to(root)),
            "source_report_sha256": hashlib.sha256(raw).hexdigest(),
            "threshold_ms": report["threshold_ms"],
            "pitch_config": report.get("pitch_config"),
            "silence_config": report.get("silence_config"),
            "repair_recordings": list(repair_recordings),
            "policy": report.get("policy"),
            "notice": (
                "Originals preserved; opt-in repairs are separate derived MIDI/notes. "
                "Not training-approved. Source status captured at publication."
            ),
        },
        "recordings": recordings,
    }
    # Descriptor is the completion marker: discovery sees only finished runs.
    for path, value in payloads + [(destination / "viewer.json", descriptor)]:
        with path.open("x") as stream:
            json.dump(value, stream, indent=2)
    return descriptor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repair-recording", action="append", default=[])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = publish(
        root,
        repository_path(root, args.report),
        repository_path(root, args.output),
        args.repair_recording,
    )
    print(
        f"Published {len(result['recordings'])} recordings: {args.output}/viewer.json"
    )


if __name__ == "__main__":
    main()
