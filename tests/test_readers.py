import hashlib
import zipfile

import mido
import numpy as np
import pytest
import soundfile as sf
import yaml

from bass_pipeline.prepare import (
    build_manifest,
    extract_archive,
    idmt_notes,
    midi_notes,
)


def test_midi_tempo_change_and_velocity_zero(tmp_path):
    path = tmp_path / "test.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend(
        [
            mido.Message("note_on", note=40, velocity=90),
            mido.MetaMessage("set_tempo", tempo=1000000, time=480),
            mido.Message("note_on", note=40, velocity=0, time=480),
        ]
    )
    midi.save(path)
    (note,) = midi_notes(path)
    assert note.onset_seconds == 0
    assert note.offset_seconds == 1.5
    assert note.pitch_midi == 40


def test_midi_missing_note_off_rejected(tmp_path):
    path = tmp_path / "test.mid"
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([mido.Message("note_on", note=40)]))
    midi.save(path)
    with pytest.raises(ValueError, match="unterminated"):
        midi_notes(path)


def test_idmt_preserves_techniques(tmp_path):
    path = tmp_path / "label.xml"
    path.write_text("""<instrumentRecording><globalParameter>
    <audioFileName>001.wav</audioFileName></globalParameter><transcription>
    <event><pitch>28</pitch><onsetSec>0</onsetSec><offsetSec>1</offsetSec>
    <excitationStyle>FS</excitationStyle></event>
    </transcription></instrumentRecording>""")
    name, notes, techniques = idmt_notes(path)
    assert name == "001.wav"
    assert notes[0].pitch_midi == 28
    assert techniques == [{"excitationStyle": "FS"}]
    path.write_text("<!DOCTYPE x><x/>")
    with pytest.raises(ValueError):
        idmt_notes(path)


def test_extract_preserves_source_and_refuses_overwrite(tmp_path):
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("nested/file.txt", "hello")
    original = archive.read_bytes()
    checksum = hashlib.md5(original, usedforsecurity=False).hexdigest()
    destination = tmp_path / "extracted"
    extract_archive(archive, destination, checksum)
    assert (destination / "nested/file.txt").read_text() == "hello"
    assert archive.read_bytes() == original
    with pytest.raises(FileExistsError):
        extract_archive(archive, destination, checksum)


def test_extract_rejects_traversal_before_writing(tmp_path):
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape", "hello")
    checksum = hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()
    with pytest.raises(ValueError):
        extract_archive(archive, tmp_path / "extracted", checksum)
    assert not (tmp_path / "extracted").exists()


def test_manifest_pairs_all_datasets_and_quarantines_bad_labels(tmp_path):
    extracted = tmp_path / "extracted"

    def audio(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, np.zeros(16000), 16000, format="WAV")

    def midi(path, duration=480):
        path.parent.mkdir(parents=True, exist_ok=True)
        file = mido.MidiFile(ticks_per_beat=480)
        file.tracks.append(
            mido.MidiTrack(
                [
                    mido.Message("note_on", note=40, velocity=90),
                    mido.Message("note_off", note=40, time=duration),
                ]
            )
        )
        file.save(path)

    filo = extracted / "filobass" / "FiloBass ISMIR Publication"
    for key, duration in [("good", 480), ("bad", 4800)]:
        audio(filo / "audio_bass_stems" / f"{key}.mp3")
        midi(filo / "midi_fully_aligned" / f"{key}.mid", duration)
    idmt = extracted / "idmt_single_track"
    audio(idmt / "audio" / "001.wav")
    (idmt / "annotation").mkdir()
    (idmt / "annotation" / "001.xml").write_text("""<instrumentRecording>
    <globalParameter><audioFileName>001.wav</audioFileName></globalParameter>
    <transcription><event><pitch>40</pitch><onsetSec>0</onsetSec>
    <offsetSec>0.5</offsetSec></event></transcription></instrumentRecording>""")
    baby = extracted / "babyslakh" / "Track01"
    audio(baby / "stems" / "S01.wav")
    midi(baby / "MIDI" / "S01.mid")
    (baby / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "stems": {
                    "S01": {
                        "inst_class": "Bass",
                        "is_drum": False,
                        "audio_rendered": False,
                        "midi_saved": False,
                    },
                    "S02": {"inst_class": "Piano", "is_drum": False},
                }
            }
        )
    )
    output = tmp_path / "processed"
    report = build_manifest(tmp_path, extracted, output)
    assert report["accepted"] == {"filobass": 1, "idmt": 1, "babyslakh": 1}
    assert report["quarantined"][0]["recording_id"] == "filobass-bad"
    import json

    rows = json.loads((output / "manifest.json").read_text())
    assert all(row["split"] is None for row in rows)
    assert rows[-1]["warnings"]
    assert rows[-1]["group_id"] == "babyslakh-Track01"
    with pytest.raises(FileExistsError):
        build_manifest(tmp_path, extracted, output)
