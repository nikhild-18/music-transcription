# Setup record

## Completed

- Audited an Intel Mac with macOS 15.7.9, four CPU cores, and 8 GB RAM.
- Storage cleanup was performed by the owner. The follow-up audit reported 139 GiB available.
- Confirmed that Documents no longer contains an enclosing Git repository.
- Initialized this dedicated repository with a main branch.
- Added a file-preservation working agreement and initial ignore rules before adding project code or dependencies.
- Configured repository-local Git identity using the verified GitHub username and ID-based noreply address; global Git settings were preserved.
- Checked that ignore rules cover sample secret, virtual environment, data, checkpoint, and scratch paths.
- Verified that the active task can write only inside this repository and necessary system temporary directories. Disposable write probes succeeded in those locations and were removed.
- Installed uv 0.13.0 as an unmanaged repository-local tool under the ignored `.tools/` directory; no shell profile or global path was changed.
- Installed CPython 3.11.17 under the ignored `.python/` directory and created an isolated `.venv/`.
- Added `pyproject.toml`, `.python-version`, and a `uv.lock` intended for commit for reproducible local tooling.
- Added Ruff, pytest, and detect-secrets checks. Linting and the setup smoke test pass, and a temporary synthetic secret fixture is correctly rejected.

## Existing tools observed

| Tool | Version / status |
| --- | --- |
| VS Code | 1.135.0; Python, Pylance, Jupyter, and Remote SSH extensions present |
| Git | 2.35.1 |
| GitHub CLI | 2.5.0; local login configuration exists, authentication not yet validated |
| Homebrew | 3.3.13; package metadata from 2022 |
| Default Python | 3.8.5 |
| Conda | 4.14.0 |
| Docker | Desktop 3.4.0 / CLI 20.10.7; not needed for the initial local setup |
| uv | 0.13.0, repository-local via `scripts/uv` |
| Azure CLI, FFmpeg | Not found on the paths checked during the initial audit |

## Local workflow

### Review-only correction diagnostics

```sh
scripts/uv run --frozen python -m bass_pipeline.diagnose --threshold-ms 20 --orphan-pitch --output outputs/correction-diagnostics-v1.json
```

This never alters MIDI, training labels or prior reports. The 20 ms proximity
report compares adjacent starts of the same channel/pitch; it flags intervening
stops and does not perform transitive merges. The optional orphan diagnostic uses
bounded FFT autocorrelation on CPU, no learned model or new dependencies. Default
search limit is 5 seconds before a leading orphan stop, using 128 ms frames and
10 ms hops. Evidence must persist for three frames, with periodicity >=0.8,
RMS >=0.0001 and pitch within 50 cents. These are provisional heuristic settings
in PitchConfig, not calibrated confidence or guaranteed error bounds.

Outputs distinguish carry-in candidates (already sounding, onset unknown), coarse
onset-region candidates, and unresolved cases. Diagnosis never deletes stops.
BoundaryNote explicitly uses null onset and already_sounding=true; it is separate
from the existing Note schema and must not enter onset training/scoring as a zero
onset. Model tie-token integration is still pending. Diagnosis can confuse octave
harmonics, bleed and noise; real recordings require review beyond synthetic tests.

Owner exclusions live in configs/exclusions.json and are honored by preparation,
source inspection and diagnostics. Track00017-S04 is excluded because both its
stem audio and MIDI are absent. No original file was deleted. Historical outputs
remain unchanged; source inspection shows exclusions only under Explicitly excluded.

### Local annotation viewer

The structural MIDI diagnostic now scans beyond the first parser failure and
reports all overlapping starts, orphan stops, and remaining unclosed starts with
timestamps. Ambiguous pairing is counted, not exported as guessed note labels.
These findings become orange markers using the generic event layer. Non-timestamped
file/decode failures remain in processing history; no invented timestamp is assigned.

An opt-in derived repair is available through `publish_diagnostics`:

```sh
scripts/uv run --frozen python -m bass_pipeline.diagnose --threshold-ms 20 --orphan-pitch --output outputs/correction-diagnostics-v2.json
scripts/uv run --frozen python -m bass_pipeline.publish_diagnostics --report outputs/correction-diagnostics-v2.json --output outputs/diagnostics/correction-review-v2 --repair-recording filobass-Sonnymoon-for-Two --repair-recording filobass-Star-Eyes
```

The `quiet-prefix-v1` rule removes only a leading unmatched stop, before any start
of that channel/pitch, if the entire preceding audio (0.05–5 seconds) is available
and finite, every channel's peak is <= -50 dBFS, and every 20 ms frame's RMS is
<= -60 dBFS. Thresholds live in `SilenceConfig`; no normalization is applied.
This is an amplitude heuristic, not proof of silence: quiet genuine notes could
fall below it. It is not automatically enabled for all datasets or training.
Each named recording gets a new MIDI with elapsed time preserved across removed
events, plus an audit of measurements and the source MIDI hash. Original files
and prior runs are never overwritten. Remaining structural errors still block
canonical notes. Both named songs still have overlaps after removing their leading
stop; their removed-stop markers are explicitly marked `removed_in_derived_midi`.

Playback timing: the default **Audio clock** engine schedules decoded PCM with
Web Audio and draws the cursor from the same schedule, using `getOutputTimestamp`
when available (otherwise a base/output-latency estimate). It does not add an
arbitrary 200 ms correction or modify labels. Slow previews use pinned
Pedalboard/Rubber Band time stretching before playback. The rendered buffer plays
at unity rate while the cursor maps back to source seconds; pitch is preserved.
Changing speed renders a new preview and retains the cursor position. The old
browser playback mode has been removed. Compare sound with the white plot line.
Processing is CPU-based and bounded to the selected 1–30 s window. Stretching can
soften or move transients: use 1x for precise onset judgments. Synthetic tests
bound click-peak displacement to 25 ms source time, not a guarantee for music.
Pedalboard uses GPL-licensed Rubber Band: review redistribution licensing before
packaging/publishing an application; this is not a permissive-only dependency.
Device timestamps are best-effort, not proof of acoustic/Bluetooth calibration.

Generate an independent timing reference (refuses an existing output directory):

```sh
scripts/uv run --frozen python -m bass_pipeline.sync_check --output outputs/diagnostics/playback-sync-v1
```

This emits quiet tone bursts with exact onsets at 1, 2, 3, 4, and 5 seconds,
using the same artifact contract as every other run. Compare speeds at 1x
and 0.5x, first on built-in/wired audio if possible. Tone onsets should coincide
with the cursor crossing orange markers. Python tests verify WAV/peak alignment;
`node --test tests/player.test.js` (Node 18+) tests clock mapping and transport
state without audio hardware. These JS tests are separate from `scripts/check`.
No microphone/system-audio recording is performed. Human listening confirmation
is still needed before claiming the reported perceptual offset is resolved.

The viewer supports generic `events` layers alongside `reference` and `prediction`
note layers. Each event JSON array item has a unique string `id`, a `label`,
`start_seconds`, optional `end_seconds` (omitted means a point), and optional
`severity` (`info`, `warning`, `error`), `status`, and `details`. End must not precede
start. Layer `time_origin_seconds` maps these times to the source timeline once.
This format is algorithm-independent: diagnostics, evaluation mistakes, and
uncertain regions can all publish it. Events do not change training labels.

Publish an existing diagnostic report into a new, discoverable run:

```sh
scripts/uv run --frozen python -m bass_pipeline.publish_diagnostics --report outputs/correction-diagnostics-v1.json --output outputs/diagnostics/correction-review-v1
```

Existing destinations are refused. This adapter emits event files per recording
and writes `viewer.json` last. It retains source IDs, source inspection status,
available note layers, and report hash/configuration provenance. It does not
re-run diagnostics. Without `--repair-recording` it makes no repairs.
Discovery also searches `outputs/diagnostics`.
Select the published run; orange markers and the expandable event list expose
findings, evidence, and jump-to-time buttons. Layer checkboxes control events too.
The `?run=correction-review-v1` URL selects that run explicitly.

Event loading is independent of audio/note loading; a missing or malformed layer
does not hide the other layers. Audio remains windowed; event JSON is loaded for
the selected recording, not the whole corpus. Very large per-recording event
files will eventually need pagination/indexing. Run provenance is visible in its
own panel. See `configs/events.example.json` for point/interval examples.
The ruler has 0.5 s minor ticks (0.1 s at half speed) and faint guides.
This is still a read-only inspection tool, not a repair approval editor.

The viewer additionally inventories known dataset layouts beneath each version
directory in `data/extracted/`. Select a **source inventory** run to inspect all
discovered FiloBass/IDMT recordings and BabySlakh bass metadata entries, including
missing pairs. This inventory is read-only and reconstructed on discovery; it does
not modify historical manifests or approve anything for training. New dataset
formats still need an inventory adapter or an explicit viewer descriptor.

Filter by **Failed / held**, **Not processed**, or **Needs review**. Audio remains
playable when labels are absent or unreadable. Expand processing history to inspect
availability checks, historical preparation outcomes, source paths and a bounded
raw MIDI/XML preview. MIDI preview times are delta ticks, not canonical seconds.
Malformed note layers are reported without blocking audio. Missing audio remains
visible but is not playable. Raw compressed archives are not playable; extraction
must happen first. Existing legacy reports lack precise stage codes, so their
errors are explicitly labeled **legacy preparation**, not guessed stages.

Structural success is **needs review**, not training approval. No approvals or
repairs are saved. Source inventory only reads audio headers; it does not imply
full audio validation. Historical outcomes are attached to the same source tree;
multiple historical attempts remain listed in processing history.

The default viewer now discovers `viewer.json` recursively under
`data/processed`, `outputs/preprocessing`, `outputs/inference`, and
`outputs/evaluation`. Click **Discover runs** (or refresh the page) after creating
a run; no server restart is needed. Legacy `manifest.json` catalogs under
`data/processed` remain supported when no sibling viewer.json exists.
New preparation runs automatically emit a descriptor; existing outputs are untouched.

Use `configs/viewer.example.json` as the contract for new stages, saving the
completed descriptor as `viewer.json` alongside each run's outputs. Write the
descriptor last, after its referenced files are complete. Paths are relative to
the repository root, never the descriptor. Each recording has a stable ID, dataset,
audio duration, one audio path and zero or more reference/prediction note layers.
Notes are JSON arrays in our canonical pitch/onset/offset format.

Every audio and note layer declares `time_origin_seconds`: the original recording
time corresponding to its local zero. Full-song files use 0; a crop starting at
45 seconds uses 45. Already-absolute notes use 0 even when audio is cropped.
The viewer adds this origin once to put layers on the same source timeline.
This contract supports offsets, not time stretching; time-warped outputs must
map their notes back to source time or be inspected as a separate timeline.

Select a run and recording, then toggle layers: reference notes are gold filled
blocks; predictions are mint outlines. For original/processed audio comparison,
publish separate recordings/runs with `source_recording_id` linking them. There
is no simultaneous A/B playback yet. Configuration and source-run metadata placed
inside `provenance` are rendered in the Run provenance panel. Invalid descriptors appear as
discovery warnings. Unsupported tensors/spectrograms are not rendered yet.

```sh
scripts/uv run --frozen python -m bass_pipeline.viewer
```

Open http://127.0.0.1:8765 in a browser. Stop the server with Ctrl-C.
The server binds only to loopback, reads the processed v1 manifest, and exposes
only the catalog and bounded audio clips (not arbitrary repository files).
Use `--port 8766` if needed, or `--manifest data/processed/v2/manifest.json`
for a later manifest with a sibling report.json.

Choose a dataset/recording and a 5–30 second window. Audio controls support
playback, slower speed, and looping; click the waveform/piano roll to seek.
The plot and note table retain absolute recording timestamps, including notes
that began before the current window. Reference labels are not model predictions.
Browser playback uses temporary in-memory 16-bit WAV clips at the original sample
rate without normalization; original files are unchanged. The waveform envelope
uses maximum amplitude across channels. This is a review aid, not a sample-accurate
audio editor. No approval decisions, corrections or annotations are saved yet.

Held examples are listed separately; they cannot yet be inspected with converted
notes. No third-party scripts, telemetry, cloud services, or model are required.

Run project commands through `scripts/uv`. The wrapper redirects uv's cache and
managed Python directories into ignored repository paths, avoiding user-level
configuration and storage.

```sh
scripts/uv sync --frozen
scripts/check
```

`--frozen` tells uv to reproduce `uv.lock` without silently changing dependency
versions. Use a deliberate, reviewed lock operation when dependencies change.

The managed Python interpreter passed import checks for native standard-library
modules. uv could not patch one dynamic-library install name because Apple Command
Line Tools are absent. Prebuilt development-tool wheels work; installing the
system-wide tools should be considered separately if a future package must compile
a native extension.

## Next checkpoints

### YourMT3+ pipeline milestone

YourMT3+ is the selected model family. Exact upstream revision, checkpoint,
tokenizer, frontend, and Linux training dependencies still need to be pinned.
No TensorFlow training stack or Azure resources have been installed/provisioned.

The first local pipeline layer uses only Python's standard library:

```sh
scripts/check
scripts/uv run --frozen python -m bass_pipeline audit --output outputs/data-audit-001.json
```

Choose a new output name for each audit; reports are ignored by Git and never
overwritten. The audit verifies published archive checksums, records SHA-256,
inventories file types and uncompressed size, and rejects dangerous archive paths
and links. It does not extract files or validate audio/annotation alignment yet.

`configs/pipeline.toml` records the selected family and provisional split,
excerpt, preprocessing, augmentation, and evaluation settings. The pure functions
in `bass_pipeline/core.py` provide note validation, deterministic group-level
split planning, excerpt boundaries, and exact-pitch/onset one-to-one scoring.
The split proportions target groups rather than seconds or notes. Tiny datasets
may have empty splits. Audit cross-dataset duplicates before assigning groups.

Split plans are not yet benchmark splits: audit pretrained checkpoint exposure
(especially SMT-Bass and Slakh), approve assignments, then freeze manifests.
Notes crossing excerpt boundaries retain original timing; the future YourMT3+
adapter must encode continuing notes without inventing note onsets.

### Extraction and annotation readers

The local reader environment now includes locked Mido, PyYAML, SoundFile and
NumPy dependencies. These are separate from the future Linux GPU training stack.

```sh
scripts/uv run --frozen python -m bass_pipeline.prepare extract
scripts/uv run --frozen python -m bass_pipeline.prepare manifest
```

Defaults are `data/extracted/v1` and `data/processed/v1`; both are ignored by Git.
Existing destinations are refused, not overwritten. For a later deliberate rerun,
use a new `--output data/processed/v2` or `--extracted data/extracted/v2`.
Failed/incomplete directories are retained for inspection, not automatically removed.

Extraction verifies checksums, validates paths, rejects links, checks free space,
and writes a completion marker only after successful copying. Original archives
are unchanged. The manifest command requires successful extraction markers.

Readers use FiloBass fully aligned MIDI, IDMT XML note events (retaining technique
metadata), and BabySlakh bass-class stems paired with their individual MIDI files.
MIDI tempo changes and zero-velocity note-offs are handled. Ambiguous overlapping
same-pitch MIDI notes, unmatched events, and unsupported time formats are rejected
rather than repaired silently. MIDI sustain pedals are not interpreted.

Audio is fully decoded in bounded blocks, checking finite samples and frame
counts. Notes extending more than 50 ms beyond audio are quarantined. This is a
structural check, not proof of perceptual onset alignment. No audio is resampled,
normalized, denoised, or augmented. FiloBass instrument type remains unknown pending
curation; BabySlakh is explicitly synthetic. Metadata/file disagreements are flagged.

Generated files include `manifest.json`, one note JSON array per accepted recording,
`report.json` with rejections, and `provenance.json` with extraction hashes,
configuration and Git state. No dataset contents are committed. All splits remain
unset pending curation and pretrained-data overlap review.

Remaining pre-GPU work (readers and extraction are now implemented):

1. Review the real-data validation report and explicitly resolve quarantined items.
2. Inspect dataset licenses, bass types, techniques and duplicate song identities.
3. Validate audio headers, note ranges, timing alignment and bass selection;
   inspect/listen to representative recordings before freezing manifests.
4. Pin one upstream checkpoint/configuration and implement its data adapter.
5. Compare the lightweight evaluator with a standard evaluation library, add
   per-recording reporting and record environment/configuration provenance.
6. Confirm Azure eligibility, quota, price and shutdown controls before a paid
   checkpoint-load / short training smoke test.

### Earlier setup checklist (historical)

- Confirm only this repository is registered as the local Codex project and open it in VS Code.
- Retire the obsolete Documents-level trusted-project setting without changing unrelated settings; this requires separately authorized user-level configuration access.
- Define the transcription scope, output representation, evaluation datasets, metrics, and held-out split.
- Select and record the first baseline. Python 3.11 is compatible with the current Basic Pitch metadata, but no model dependency has been added yet.
- Keep ML-only dependencies separate from lightweight local dependencies.
- Validate local GitHub authentication and create a private remote repository.
- Verify Azure credit offer, expiry, service eligibility, region and quota. Configure cost controls before provisioning compute.

## Concepts

- **Repository:** a deliberately scoped folder whose source history is recorded by Git.
- **Commit:** a named snapshot of the staged files. Untracked and ignored files are not protected by a commit.
- **Virtual environment:** an isolated set of Python packages for one project.
- **Lockfile:** the resolved dependency versions used to reconstruct an environment.
- **Sandbox:** enforced limits on where an agent's commands can read and write; distinct from Git history or written instructions.
- **Evaluation harness:** repeatable code that runs models against fixed examples and measures their predictions consistently.

## References

- [uv projects](https://docs.astral.sh/uv/guides/projects/)
- [uv installer options](https://docs.astral.sh/uv/reference/installer/)
- [Codex permissions](https://learn.chatgpt.com/docs/permissions)
- [Intel macOS PyTorch build deprecation](https://dev-discuss.pytorch.org/t/pytorch-macos-x86-builds-deprecation-starting-january-2024/1690)
- [Basic Pitch project metadata](https://github.com/spotify/basic-pitch/blob/main/pyproject.toml)
