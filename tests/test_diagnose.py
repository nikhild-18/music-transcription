import mido

from bass_pipeline.diagnose import nearby_starts


def test_diagnostic_threshold_velocity_and_intervening_stop(tmp_path):
    path = tmp_path / "test.mid"
    midi = mido.MidiFile(ticks_per_beat=500)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=40, velocity=80),
                mido.Message("note_on", note=40, velocity=80),
                mido.Message("note_off", note=40, time=10),
                mido.Message("note_on", note=40, velocity=90, time=10),
                mido.Message("note_on", note=40, velocity=90, time=21),
            ]
        )
    )
    midi.save(path)
    before = path.read_bytes()
    pairs = nearby_starts(path)
    assert len(pairs) == 2
    assert pairs[0]["exact_duplicate_start"]
    assert not pairs[1]["exact_duplicate_start"]
    assert pairs[1]["stop_since_previous_start"]
    assert pairs[1]["gap_ms"] == 20
    assert path.read_bytes() == before
