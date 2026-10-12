import io
import json

import numpy as np
import pytest
import soundfile as sf

from bass_pipeline.artifacts import discover
from bass_pipeline.viewer import Catalog


def test_clip_preserves_absolute_time_and_bounds(tmp_path):
    sf.write(tmp_path / "audio.wav", np.zeros(32000), 16000)
    (tmp_path / "notes.json").write_text(
        json.dumps(
            [
                {"pitch_midi": 40, "onset_seconds": 0.5, "offset_seconds": 1.5},
                {"pitch_midi": 41, "onset_seconds": 0, "offset_seconds": 0.4},
            ]
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps([{"audio_path": "audio.wav", "annotation_path": "notes.json"}])
    )
    (tmp_path / "report.json").write_text('{"quarantined": []}')
    catalog = Catalog(tmp_path, manifest)
    meta, wav = catalog.clip(0, 1, 5)
    assert meta["start"] == 1
    assert meta["end"] == 2
    assert len(meta["notes"]) == 1
    assert meta["notes"][0]["onset_seconds"] == 0.5
    assert sf.info(io.BytesIO(wav)).frames == 16000
    for index, start, length in [
        (-1, 0, 5),
        (1, 0, 5),
        (0, -1, 5),
        (0, 0, 1000),
        (0, float("nan"), 5),
        (0, 2, 5),
    ]:
        with pytest.raises(ValueError):
            catalog.clip(index, start, length)
    catalog.rows[0]["audio_path"] = "../outside.wav"
    with pytest.raises(ValueError):
        catalog.clip(0, 0, 5)


def test_discovery_refresh_layers_and_offsets(tmp_path):
    sf.write(tmp_path / "audio.wav", np.zeros(32000), 16000)
    note = {"pitch_midi": 40, "onset_seconds": 0.5, "offset_seconds": 1.5}
    (tmp_path / "notes.json").write_text(json.dumps([note]))
    folder = tmp_path / "outputs/inference/run1"
    folder.mkdir(parents=True)
    descriptor = {
        "schema_version": "1.0",
        "run_id": "run1",
        "stage": "inference",
        "recordings": [
            {
                "recording_id": "song",
                "dataset": "new-dataset",
                "duration_seconds": 2,
                "audio": {"path": "audio.wav", "time_origin_seconds": 45},
                "layers": [
                    {
                        "id": "pred",
                        "kind": "prediction",
                        "path": "notes.json",
                        "time_origin_seconds": 45,
                    }
                ],
            }
        ],
    }
    catalog = Catalog(tmp_path)
    assert catalog.rows == []
    (folder / "viewer.json").write_text(json.dumps(descriptor))
    catalog.refresh()
    uid = catalog.rows[0]["uid"]
    meta, _ = catalog.clip(uid, 45, 1)
    assert meta["notes"][0]["onset_seconds"] == 45.5
    assert meta["notes"][0]["layer"] == "pred"
    assert meta["start"] == 45
    descriptor["recordings"][0]["layers"][0]["path"] = "../escape.json"
    (folder / "viewer.json").write_text(json.dumps(descriptor))
    rows, report = discover(tmp_path)
    assert rows == []
    assert len(report["discovery_errors"]) == 1


def test_legacy_discovery_and_descriptor_precedence(tmp_path):
    folder = tmp_path / "data/processed/v1"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "recording_id": "song",
                    "audio_path": "a.wav",
                    "annotation_path": "n.json",
                }
            ]
        )
    )
    rows, _ = discover(tmp_path)
    assert len(rows) == 1
    (folder / "viewer.json").write_text('{"schema_version": "unknown"}')
    rows, report = discover(tmp_path)
    assert rows == []  # Never silently fall back from a broken descriptor.
    assert report["discovery_errors"]


def test_failed_source_stays_playable_and_missing_files_visible(tmp_path):
    base = tmp_path / "data/extracted/v1/idmt_single_track"
    (base / "audio").mkdir(parents=True)
    (base / "annotation").mkdir()
    sf.write(base / "audio/001.wav", np.zeros(32000), 16000)
    (base / "annotation/002.xml").write_text("<broken>")
    catalog = Catalog(tmp_path)
    assert len(catalog.rows) == 2
    row = next(r for r in catalog.rows if r["recording_id"] == "idmt-001")
    assert row["status"] == "failed"
    assert row["training_eligible"] is False
    meta, wav = catalog.clip(row["uid"], 0, 1)
    assert meta["notes"] == []
    assert wav
    missing_audio = next(r for r in catalog.rows if r["recording_id"] == "idmt-002")
    assert missing_audio["duration_seconds"] == 0
    assert catalog.details(missing_audio["uid"])["source"] == "<broken>"


def test_broken_layer_does_not_block_audio(tmp_path):
    sf.write(tmp_path / "audio.wav", np.zeros(32000), 16000)
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            [
                {
                    "audio_path": "audio.wav",
                    "layers": [
                        {
                            "id": "bad",
                            "kind": "reference",
                            "path": "missing.json",
                            "time_origin_seconds": 0,
                        }
                    ],
                }
            ]
        )
    )
    (tmp_path / "report.json").write_text('{"quarantined": []}')
    meta, wav = Catalog(tmp_path, path).clip(0, 0, 1)
    assert meta["layer_errors"]
    assert not meta["notes"]
    assert wav
