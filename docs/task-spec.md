# Bass transcription task specification

Status: proposed v1 contract

## Goal

Given an isolated, monophonic jazz-bass recording, predict the performed notes as
MIDI pitches with onset and offset times in seconds.

The first model accepts either upright or electric bass. The source instrument
does not determine the eventual tablature instrument.

```text
isolated bass audio -> timed note events -> MIDI / notation / electric-bass tab
```

Source separation, score layout, chord recognition, and tablature generation are
separate pipeline stages. Later stages may share evidence, but each must remain
independently measurable.

## Canonical representation

MIDI is an export format, not the project's source of truth. The canonical
representation preserves performance timing before notation quantizes it.

Each recording has a manifest entry:

```json
{
  "schema_version": "1.0",
  "recording_id": "example-001",
  "dataset": "example",
  "audio_path": "audio/example-001.wav",
  "split": "train",
  "bass_type": "upright",
  "audio_context": "isolated_stem",
  "annotation_path": "annotations/example-001.notes.jsonl"
}
```

Each line of the annotation file describes one note:

```json
{"pitch_midi": 40, "onset_seconds": 1.238, "offset_seconds": 1.611}
```

Required v1 fields:

- `pitch_midi`: integer MIDI note number.
- `onset_seconds`: note start measured from the beginning of the audio.
- `offset_seconds`: note end measured from the beginning of the audio.

Dataset metadata records provenance, licensing, annotation method, and any usage
restrictions. Predictions may additionally contain confidence and alternative
pitch candidates; these must not overwrite reference annotations.

Beat positions, quantized durations, chords, measures, form, string and fret,
articulations, and ghost-note labels will be added as separate annotation layers.
This keeps information from one model from becoming an irreversible assumption
for another model.

## Evaluation unit and split

The primary evaluation unit is a note event: one pitch and its onset. Offset
accuracy will be recorded for analysis but will not determine the first v1 pass
condition.

Training, validation, and test splits occur at the recording level. When dataset
metadata permits, performances by the same bassist must not appear in both the
training and final test sets. Splitting short excerpts from one recording across
sets would leak its performer, instrument, room, and production characteristics.

The final test set remains fixed and is not used to choose thresholds or training
checkpoints. Validation data is used for those development decisions.

Initial reports will include:

- Note precision, recall, and F1 for correct pitch and onset.
- Pitch-only accuracy to distinguish pitch errors from timing errors.
- Onset timing error in milliseconds.
- Note metrics at configurable onset tolerances, initially 25, 50, and 100 ms.
- Results grouped by upright and electric bass.
- Per-recording results so aggregate scores cannot hide severe failures.

The 50 ms tolerance is the primary headline metric. The 25 ms and 100 ms results
are stricter and looser diagnostics. These values are evaluation configuration,
not constants embedded in metric code, so experiments can change or sweep them
without modifying the evaluator. Minimum dataset coverage remains a review
decision.

## V1 scope boundaries

Included:

- Isolated upright and electric jazz bass.
- Predominantly monophonic, pizzicato performance.
- Performed pitch and timing rather than inferred harmonic function.
- Walking lines and ordinary single-note passages.

Deferred:

- Source separation from a full ensemble recording.
- Bowed bass, chords, slap techniques, and extended techniques.
- Ghost notes and detailed articulations.
- Beat, measure, chord, and song-form recognition.
- Readable score engraving and direct Guitar Pro export.
- Learned string and fret assignment.

Deferred features must not require discarding or rewriting the v1 note timing.

## First hill-climbing loop

1. Validate a fixed collection of audio and reference note events.
2. Run an unchanged baseline model.
3. Save predictions, metrics, configuration, model version, and Git revision.
4. Inspect errors by category and dataset slice.
5. Change one controlled variable.
6. Keep the change only when it improves validation results without regressing
   important slices.

No fine-tuning begins until the data validator, fixed split, metric implementation,
and unchanged baseline result are reproducible.

## Decisions queued after this contract

1. Approve datasets and their roles: training, validation, or final testing.
2. Choose an exact, non-public storage location for original audio.
3. Define the committed manifest format without exposing restricted filenames or
   personal filesystem paths.
4. Select the first unchanged baseline model.
