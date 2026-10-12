import json

import numpy as np
import pytest
import soundfile as sf

from bass_pipeline.events import read_events, validate_event
from bass_pipeline.publish_diagnostics import publish
from bass_pipeline.viewer import Catalog


@pytest.mark.parametrize(
    "update",
    [
        {"start_seconds": -1},
        {"start_seconds": float("nan")},
        {"start_seconds": True},
        {"end_seconds": 0},
        {"label": ""},
        {"severity": "unexpected"},
    ],
)
def test_invalid_events(update):
    with pytest.raises(ValueError):
        validate_event({"id": "a", "label": "test", "start_seconds": 1, **update})


def test_generic_events_offsets_and_independent_failures(tmp_path):
    event = {"id": "a", "label": "Anything", "start_seconds": 1, "end_seconds": 2}
    (tmp_path / "events.json").write_text(json.dumps([event]))
    layer = {
        "id": "events",
        "kind": "events",
        "path": "events.json",
        "time_origin_seconds": 45,
    }
    result = read_events(
        tmp_path, [layer, {**layer, "id": "bad", "path": "missing.json"}]
    )
    assert result["events"][0]["start_seconds"] == 46
    assert result["events"][0]["end_seconds"] == 47
    assert len(result["layer_errors"]) == 1
    (tmp_path / "events.json").write_text(json.dumps([event, event]))
    assert read_events(tmp_path, [layer])["layer_errors"]


def test_events_discovered_without_audio_and_do_not_break_audio(tmp_path):
    folder = tmp_path / "outputs/diagnostics/test"
    folder.mkdir(parents=True)
    (tmp_path / "events.json").write_text(
        '[{"id":"a","label":"Check","start_seconds":0.5}]'
    )
    spec = {
        "schema_version": "1.0",
        "run_id": "test",
        "stage": "arbitrary stage",
        "recordings": [
            {
                "recording_id": "song",
                "duration_seconds": 2,
                "audio": {"path": "audio.wav", "time_origin_seconds": 0},
                "layers": [
                    {
                        "id": "findings",
                        "kind": "events",
                        "path": "events.json",
                        "time_origin_seconds": 0,
                    },
                    {
                        "id": "broken-notes",
                        "kind": "reference",
                        "path": "missing.json",
                        "time_origin_seconds": 0,
                    },
                ],
            }
        ],
    }
    (folder / "viewer.json").write_text(json.dumps(spec))
    catalog = Catalog(tmp_path)
    uid = catalog.rows[0]["uid"]
    assert catalog.rows[0]["status"] == "failed"
    assert catalog.events(uid)["events"][0]["end_seconds"] == 0.5
    sf.write(tmp_path / "audio.wav", np.zeros(32000), 16000)
    meta, wav = catalog.clip(uid, 0, 1)
    assert wav and len(meta["layer_errors"]) == 1
    assert not meta["notes"]


def test_publish_preserves_report_and_refuses_overwrite(tmp_path):
    base = tmp_path / "data/extracted/v1/idmt_single_track"
    (base / "audio").mkdir(parents=True)
    (base / "annotation").mkdir()
    sf.write(base / "audio/001.wav", np.zeros(32000), 16000)
    (base / "annotation/001.xml").write_text("<test/>")
    report = {
        "threshold_ms": 20,
        "recordings": [
            {
                "recording_id": "idmt-001",
                "source_path": str((base / "annotation/001.xml").relative_to(tmp_path)),
                "orphan_proposals": [{"stop_seconds": 0.75, "status": "unresolved"}],
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    before = path.read_bytes()
    output = tmp_path / "outputs/diagnostics/run"
    publish(tmp_path, path, output)
    catalog = Catalog(tmp_path)
    row = next(r for r in catalog.rows if r["run_id"] == "run")
    assert catalog.events(row["uid"])["events"][0]["status"] == "unresolved"
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="exists"):
        publish(tmp_path, path, output)
