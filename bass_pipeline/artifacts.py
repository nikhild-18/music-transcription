"""Viewer artifact v1: paths are repository-relative, times map to source seconds."""

import hashlib
import json
import math
from pathlib import Path

from bass_pipeline.audit import repository_path
from bass_pipeline.inventory import source_inventory

ROOTS = (
    "data/processed",
    "outputs/preprocessing",
    "outputs/inference",
    "outputs/evaluation",
)


def offset(value):
    if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
        raise ValueError("time_origin_seconds must be finite and nonnegative")
    return value


def discover(root: Path):
    rows, errors, held = [], [], []
    for folder in ROOTS:
        for path in sorted((root / folder).rglob("viewer.json")):
            try:
                repository_path(root, str(path.relative_to(root)))
                spec = json.loads(path.read_text())
                if spec["schema_version"] != "1.0":
                    raise ValueError("unsupported viewer schema")
                local = []
                seen = set()
                for row in spec["recordings"]:
                    rid = row["recording_id"]
                    if not isinstance(rid, str) or not rid or rid in seen:
                        raise ValueError("recording IDs must be nonempty and unique")
                    seen.add(rid)
                    audio = row["audio"]
                    audio_exists = repository_path(root, audio["path"]).is_file()
                    origin = offset(audio["time_origin_seconds"])
                    duration = row["duration_seconds"]
                    if not math.isfinite(duration) or duration <= 0:
                        raise ValueError("invalid duration")
                    layer_ids = set()
                    for layer in row["layers"]:
                        if layer["id"] in layer_ids:
                            raise ValueError("duplicate layer ID")
                        layer_ids.add(layer["id"])
                        if layer["kind"] not in ("reference", "prediction"):
                            raise ValueError("unsupported note layer kind")
                        offset(layer["time_origin_seconds"])
                        repository_path(root, layer["path"])
                    uid = hashlib.sha256(
                        f"{path.relative_to(root)}:{rid}".encode()
                    ).hexdigest()
                    local.append(
                        {
                            **row,
                            "uid": uid,
                            "run_id": spec["run_id"],
                            "stage": spec["stage"],
                            "audio_path": audio["path"],
                            "audio_origin": origin,
                            "warnings": row.get("warnings", []),
                            "status": row.get("status", "needs_review")
                            if audio_exists
                            else "failed",
                            "steps": row.get("steps", [])
                            + (
                                []
                                if audio_exists
                                else [
                                    {
                                        "stage": "audio availability",
                                        "status": "failed",
                                        "error": "audio file missing",
                                    }
                                ]
                            ),
                        }
                    )
                rows.extend(local)
                report = path.parent / "report.json"
                if report.exists():
                    held.extend(json.loads(report.read_text()).get("quarantined", []))
            except (KeyError, TypeError, ValueError, OSError) as error:
                errors.append(f"{path.relative_to(root)}: {error}")
    # Backward compatibility: directories with a descriptor take precedence.
    for path in sorted((root / "data/processed").rglob("manifest.json")):
        if (path.parent / "viewer.json").exists():
            continue
        try:
            repository_path(root, str(path.relative_to(root)))
            for row in json.loads(path.read_text()):
                uid = hashlib.sha256(
                    f"{path.relative_to(root)}:{row['recording_id']}".encode()
                ).hexdigest()
                rows.append(
                    {
                        **row,
                        "uid": uid,
                        "run_id": str(path.parent.relative_to(root)),
                        "stage": "ingestion",
                        "audio_origin": 0,
                        "layers": [
                            {
                                "id": "reference",
                                "kind": "reference",
                                "path": row["annotation_path"],
                                "time_origin_seconds": 0,
                            }
                        ],
                    }
                )
            report = path.parent / "report.json"
            if report.exists():
                held.extend(json.loads(report.read_text()).get("quarantined", []))
        except (KeyError, TypeError, ValueError, OSError) as error:
            errors.append(f"{path.relative_to(root)}: {error}")
    sources, source_errors = source_inventory(root)
    rows.extend(sources)
    for row in rows:
        row.setdefault("status", "needs_review")
        row.setdefault("steps", [])
        row.setdefault("training_eligible", False)
    return rows, {"quarantined": held, "discovery_errors": errors + source_errors}
