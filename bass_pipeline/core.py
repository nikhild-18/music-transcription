"""Pure data operations: no model runtime, audio mutation, or cloud access."""

import hashlib
import math
from dataclasses import dataclass


def positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class Note:
    """Sounding MIDI pitch; seconds relative to the original recording."""

    pitch_midi: int
    onset_seconds: float
    offset_seconds: float

    def __post_init__(self) -> None:
        if type(self.pitch_midi) is not int or not 0 <= self.pitch_midi <= 127:
            raise ValueError("pitch_midi must be an integer in [0, 127]")
        if not math.isfinite(self.onset_seconds) or self.onset_seconds < 0:
            raise ValueError("onset must be finite and nonnegative")
        if (
            not math.isfinite(self.offset_seconds)
            or self.offset_seconds <= self.onset_seconds
        ):
            raise ValueError("offset must be finite and greater than onset")


@dataclass(frozen=True)
class Recording:
    recording_id: str
    dataset: str
    group_id: str
    duration_seconds: float

    def __post_init__(self) -> None:
        if not all((self.recording_id, self.dataset, self.group_id)):
            raise ValueError("recording, dataset, and leakage group IDs are required")
        positive(self.duration_seconds, "duration")


def plan_splits(
    recordings: list[Recording],
    ratios: tuple[float, float, float] = (0.7, 0.15, 0.15),
    seed: int = 20261010,
) -> dict[str, str]:
    """Provisional per-dataset, group-level split; freeze output before training.

    A group joins all stems/versions of a song (or performers where known).
    Ratios target groups, not audio hours. Tiny datasets may have empty splits.
    Changing the collection may change assignments; never regenerate a test split
    after experiments begin. Cross-dataset duplicates require curation first.
    """
    if len(ratios) != 3 or any(not math.isfinite(r) or r < 0 for r in ratios):
        raise ValueError("three finite nonnegative split ratios are required")
    if not math.isclose(sum(ratios), 1.0):
        raise ValueError("split ratios must sum to one")
    ids = [r.recording_id for r in recordings]
    if len(ids) != len(set(ids)):
        raise ValueError("recording IDs must be globally unique")
    result = {}
    for dataset in sorted({r.dataset for r in recordings}):
        rows = [r for r in recordings if r.dataset == dataset]
        groups = sorted(
            {r.group_id for r in rows},
            key=lambda group: hashlib.sha256(
                f"{seed}:{dataset}:{group}".encode()
            ).hexdigest(),
        )
        exact = [len(groups) * ratio for ratio in ratios]
        counts = [math.floor(n) for n in exact]
        remainder_order = sorted(range(3), key=lambda i: (-(exact[i] - counts[i]), i))
        for i in remainder_order[: len(groups) - sum(counts)]:
            counts[i] += 1
        labels = [
            label
            for label, count in zip(("train", "validation", "test"), counts)
            for _ in range(count)
        ]
        assignments = dict(zip(groups, labels))
        result.update({r.recording_id: assignments[r.group_id] for r in rows})
    return result


def excerpt_windows(
    duration: float, length: float, include_short_tail: bool = True
) -> list[tuple[float, float]]:
    """Non-overlapping half-open windows; no waveform padding or label clipping."""
    positive(duration, "duration")
    positive(length, "excerpt length")
    windows = []
    for i in range(math.ceil(duration / length)):
        start = i * length
        end = min((i + 1) * length, duration)
        if end > start and (include_short_tail or end - start >= length - 1e-9):
            windows.append((start, end))
    return windows


def notes_overlapping(notes: list[Note], start: float, end: float) -> list[Note]:
    """Keep full original times, including carry-in notes, for a future tokenizer.

    Clipping a note at a crop boundary would invent an onset. YourMT3's adapter
    must encode carry-in/continuation events using its own tokenizer.
    """
    if not math.isfinite(start) or start < 0 or not math.isfinite(end) or end <= start:
        raise ValueError("invalid excerpt boundaries")
    return [n for n in notes if n.onset_seconds < end and n.offset_seconds > start]


def onset_scores(
    reference: list[Note], prediction: list[Note], tolerance_ms: float = 50
) -> dict[str, float | int]:
    """Exact MIDI pitch + onset tolerance with one-to-one maximum matching.

    Sorted greedy matching is maximum-cardinality for each pitch's ordered time
    points with a constant tolerance. Offsets are intentionally not scored.
    Empty/empty yields F1=0, with counts provided; report silent files separately.
    """
    positive(tolerance_ms, "onset tolerance")
    tolerance = tolerance_ms / 1000
    matches = 0
    for pitch in {n.pitch_midi for n in reference}:
        refs = sorted(n.onset_seconds for n in reference if n.pitch_midi == pitch)
        preds = sorted(n.onset_seconds for n in prediction if n.pitch_midi == pitch)
        i = j = 0
        while i < len(refs) and j < len(preds):
            delta = preds[j] - refs[i]
            if abs(delta) <= tolerance + 1e-12:
                matches += 1
                i += 1
                j += 1
            elif delta < -tolerance:
                j += 1
            else:
                i += 1
    precision = matches / len(prediction) if prediction else 0.0
    recall = matches / len(reference) if reference else 0.0
    return {
        "true_positives": matches,
        "false_positives": len(prediction) - matches,
        "false_negatives": len(reference) - matches,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
    }
