import numpy as np
import pytest
import soundfile as sf

from bass_pipeline.repair import BoundaryNote, pitch_evidence


def test_boundary_note_does_not_fabricate_onset():
    assert BoundaryNote(34, 0.75).onset_seconds is None
    with pytest.raises(ValueError):
        BoundaryNote(34, 0.75, onset_seconds=0)


def test_pitch_diagnostic_decay_silence_wrong_pitch_and_late_attack(tmp_path):
    path = tmp_path / "audio.wav"
    rate = 16000
    t = np.arange(rate) / rate
    tone = 0.2 * np.cos(2 * np.pi * (440 * 2 ** ((34 - 69) / 12)) * t) * np.exp(-t)
    sf.write(path, tone, rate)
    result = pitch_evidence(path, 34, 0.75)
    assert result["status"] == "carry_in_candidate"
    assert result["boundary_note"]["onset_seconds"] is None
    assert pitch_evidence(path, 40, 0.75)["status"] == "unresolved"
    assert pitch_evidence(path, 34, 10)["status"] == "unresolved"
    tone[: rate // 3] = 0
    sf.write(path, tone, rate)
    assert pitch_evidence(path, 34, 0.75)["status"] == "onset_region_candidate"
    # Audio after the orphan stop must not contribute any evidence.
    assert pitch_evidence(path, 34, 0.25)["status"] == "unresolved"
    sf.write(path, np.zeros(rate), rate)
    assert pitch_evidence(path, 34, 0.75)["status"] == "unresolved"
