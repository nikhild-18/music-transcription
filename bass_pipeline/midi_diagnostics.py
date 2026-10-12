"""Collect timestamped structural MIDI issues without guessing repaired notes."""

import mido


def midi_issues(path):
    midi = mido.MidiFile(path)
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError("unsupported MIDI timing")
    seconds, tempo = 0.0, 500000
    active, seen, issues = {}, set(), []
    for index, event in enumerate(mido.merge_tracks(midi.tracks)):
        seconds += mido.tick2second(event.time, midi.ticks_per_beat, tempo)
        if event.type == "set_tempo":
            tempo = event.tempo
        elif event.type in ("note_on", "note_off"):
            key = (event.channel, event.note)
            common = {
                "event_index": index,
                "start_seconds": seconds,
                "pitch_midi": event.note,
                "channel": event.channel,
            }
            if event.type == "note_on" and event.velocity > 0:
                if active.get(key):
                    issues.append(
                        {
                            **common,
                            "code": "overlapping_start",
                            "label": "Overlapping same-pitch start",
                            "prior_starts_seconds": [x[0] for x in active[key]],
                        }
                    )
                active.setdefault(key, []).append((seconds, index))
                seen.add(key)
            elif not active.get(key):
                issues.append(
                    {
                        **common,
                        "code": "orphan_stop",
                        "label": "Unmatched note stop",
                        "leading": key not in seen,
                    }
                )
            else:
                # Counting only: do not export guessed pairings for ambiguous notes.
                prior = active[key].pop(0)
                if seconds <= prior[0]:
                    issues.append(
                        {
                            **common,
                            "code": "nonpositive_duration",
                            "label": "Zero-duration note or ambiguous pairing",
                        }
                    )
    for (channel, pitch), starts in active.items():
        for onset, index in starts:
            issues.append(
                {
                    "event_index": index,
                    "start_seconds": onset,
                    "pitch_midi": pitch,
                    "channel": channel,
                    "code": "unterminated_note",
                    "label": "Start without a matching stop",
                }
            )
    return sorted(issues, key=lambda issue: issue["event_index"])
