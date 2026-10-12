"""Generic review events. Times are local to their layer, in seconds."""

import json
import math

from bass_pipeline.audit import repository_path


def validate_event(event):
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    for key in ("id", "label"):
        if not isinstance(event.get(key), str) or not event[key]:
            raise ValueError(f"event {key} must be a nonempty string")
    start = event.get("start_seconds")
    end = event.get("end_seconds", start)
    for value in (start, end):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("event times must be finite and nonnegative")
    if end < start:
        raise ValueError("event end precedes start")
    if event.get("severity", "info") not in ("info", "warning", "error"):
        raise ValueError("unsupported event severity")
    return {**event, "end_seconds": end, "severity": event.get("severity", "info")}


def read_events(root, layers):
    """One bad layer never blocks the other layers (or audio)."""
    result, errors = [], []
    for layer in layers:
        if layer["kind"] != "events":
            continue
        try:
            values = json.loads(repository_path(root, layer["path"]).read_text())
            if not isinstance(values, list):
                raise ValueError("event layer must contain an array")
            validated = [validate_event(value) for value in values]
            if len({v["id"] for v in validated}) != len(validated):
                raise ValueError("duplicate event IDs within layer")
            origin = layer["time_origin_seconds"]
            result.extend(
                {
                    **value,
                    "start_seconds": value["start_seconds"] + origin,
                    "end_seconds": value["end_seconds"] + origin,
                    "layer": layer["id"],
                }
                for value in validated
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"{layer['id']}: {error}")
    return {
        "events": sorted(
            result, key=lambda e: (e["start_seconds"], e["layer"], e["id"])
        ),
        "layer_errors": errors,
    }
