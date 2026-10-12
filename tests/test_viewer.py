import io
import json

import numpy as np
import pytest
import soundfile as sf

from bass_pipeline.artifacts import discover
from bass_pipeline.sync_check import publish as publish_sync
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


def test_waveform_and_delivered_pcm_share_impulse_timing(tmp_path):
    publish_sync(tmp_path, tmp_path / "outputs/diagnostics/sync")
    catalog = Catalog(tmp_path)
    uid = catalog.rows[0]["uid"]
    for start in (0, 0.3, 2.125):
        meta, wav = catalog.clip(uid, start, 3)
        samples, rate = sf.read(io.BytesIO(wav), always_2d=True)
        assert len(samples) / rate == pytest.approx(meta["end"] - meta["start"])
        peaks = [
            float(chunk.max())
            for chunk in np.array_split(
                np.max(np.abs(samples), axis=1), len(meta["peaks"])
            )
        ]
        np.testing.assert_allclose(peaks, meta["peaks"], atol=1 / 32768)
        for second in range(1, 6):
            if meta["start"] <= second < meta["end"]:
                frame = round((second - meta["start"]) * rate)
                assert samples[frame, 0] > 0.14
                if frame:
                    assert samples[frame - 1, 0] == 0
    assert len(catalog.events(uid)["events"]) == 5
    with pytest.raises(FileExistsError):
        publish_sync(tmp_path, tmp_path / "outputs/diagnostics/sync")


@pytest.mark.parametrize("rate", [0.5, 0.75])
def test_stretched_preview_preserves_pitch_and_source_timeline(tmp_path, rate):
    sr = 16000
    t = np.arange(sr * 4) / sr
    sf.write(tmp_path / "tone.wav", 0.1 * np.sin(2 * np.pi * 110 * t), sr)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"audio_path": "tone.wav", "layers": []}]))
    (tmp_path / "report.json").write_text('{"quarantined": []}')
    meta, wav = Catalog(tmp_path, manifest).clip(0, 0, 4, rate)
    signal, sample_rate = sf.read(io.BytesIO(wav))
    assert len(signal) / sample_rate == pytest.approx(4 / rate, abs=1 / sr)
    assert meta["end"] == 4  # Not the stretched playback duration.
    middle = signal[sr : 2 * sr]
    frequency = np.argmax(np.abs(np.fft.rfft(middle * np.hanning(len(middle)))))
    assert abs(frequency - 110) <= 1


def test_stretched_reference_clicks_remain_near_source_markers(tmp_path):
    publish_sync(tmp_path, tmp_path / "outputs/diagnostics/sync")
    catalog = Catalog(tmp_path)
    uid = catalog.rows[0]["uid"]
    for rate in (0.5, 0.75):
        _, wav = catalog.clip(uid, 0, 6, rate)
        signal, sr = sf.read(io.BytesIO(wav))
        for second in range(1, 6):
            lo, hi = (
                round((second / rate - 0.1) * sr),
                round((second / rate + 0.1) * sr),
            )
            peak = (lo + np.argmax(abs(signal[lo:hi]))) / sr * rate
            assert abs(peak - second) < 0.025  # preview only; not label retiming
