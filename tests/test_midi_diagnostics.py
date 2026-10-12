import mido
import numpy as np
import soundfile as sf

from bass_pipeline.midi_diagnostics import midi_issues
from bass_pipeline.prepare import midi_notes
from bass_pipeline.repair import remove_silent_leading_stops, silence_evidence


def save_midi(path, messages):
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack(messages))
    midi.save(path)


def test_all_structural_issues_not_just_first_or_close_starts(tmp_path):
    path = tmp_path / "source.mid"
    save_midi(
        path,
        [
            mido.Message("note_off", note=34, time=480),
            mido.Message("note_on", note=40, time=480),
            mido.Message("note_on", note=40, time=240),
            mido.Message("note_off", note=40, time=480),
            mido.Message("note_off", note=42, time=480),
        ],
    )
    issues = midi_issues(path)
    assert [i["code"] for i in issues].count("orphan_stop") == 2
    overlap = next(i for i in issues if i["code"] == "overlapping_start")
    assert overlap["start_seconds"] == 1.25  # >20ms from previous start
    assert any(i["code"] == "unterminated_note" for i in issues)


def test_silent_orphan_removal_preserves_absolute_timing_and_original(tmp_path):
    audio, source, derived = (
        tmp_path / n for n in ["audio.wav", "source.mid", "derived.mid"]
    )
    sf.write(audio, np.zeros(32000), 16000)
    save_midi(
        source,
        [
            mido.Message("note_off", note=34, time=480),
            mido.Message("note_on", note=40, time=480),
            mido.MetaMessage("set_tempo", tempo=1000000, time=0),
            mido.Message("note_off", note=40, time=480),
        ],
    )
    original = source.read_bytes()
    removed = remove_silent_leading_stops(source, audio, derived)
    assert len(removed) == 1
    assert midi_notes(derived)[0].onset_seconds == 1
    assert midi_notes(derived)[0].offset_seconds == 2
    assert source.read_bytes() == original
    assert not midi_issues(derived)


def test_silence_gate_checks_all_frames_channels_and_only_prior_audio(tmp_path):
    audio = tmp_path / "audio.wav"
    data = np.zeros((16000, 2))
    data[12000:, 1] = 0.2  # after stop: irrelevant
    sf.write(audio, data, 16000)
    assert silence_evidence(audio, 0.5)["eligible"]
    data[7000, 1] = 0.1  # brief spike, only in right channel
    sf.write(audio, data, 16000)
    assert not silence_evidence(audio, 0.5)["eligible"]
    data[:8000, 1] = 0.002  # peak below limit, but sustained energy fails
    sf.write(audio, data, 16000)
    assert not silence_evidence(audio, 0.5)["eligible"]
    assert not silence_evidence(audio, 6)["eligible"]
