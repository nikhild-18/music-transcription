"""Review-only boundary-note proposals. No mutation of source/training labels."""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class BoundaryNote:
    """Already active at source zero; onset is unknown, never an onset target."""

    pitch_midi: int
    offset_seconds: float
    onset_seconds: None = None
    already_sounding: bool = True

    def __post_init__(self):
        if type(self.pitch_midi) is not int or not 0 <= self.pitch_midi <= 127:
            raise ValueError("invalid pitch")
        if not math.isfinite(self.offset_seconds) or self.offset_seconds <= 0:
            raise ValueError("invalid offset")
        if self.onset_seconds is not None or self.already_sounding is not True:
            raise ValueError("boundary note must not invent an onset")


@dataclass(frozen=True)
class PitchConfig:
    max_seconds: float = 5
    frame_seconds: float = 0.128
    hop_seconds: float = 0.01
    cents_tolerance: float = 50
    min_periodicity: float = 0.8
    min_rms: float = 0.0001
    consecutive_frames: int = 3


def pitch_evidence(
    audio: Path, pitch: int, stop: float, config: PitchConfig = PitchConfig()
) -> dict:
    """FFT autocorrelation baseline, not calibrated confidence or onset truth.

    Searches a broad bass register (MIDI 21–72), then compares with target; never
    forces an estimate to the desired pitch. Only complete pre-stop frames used.
    """
    if not math.isfinite(stop) or stop <= 0:
        raise ValueError("stop must be positive and finite")
    if config.frame_seconds <= 0 or config.hop_seconds <= 0:
        raise ValueError("frame and hop must be positive")
    if config.consecutive_frames < 1:
        raise ValueError("at least one evidence frame required")
    result = {
        "pitch_midi": pitch,
        "orphan_stop_seconds": stop,
        "status": "unresolved",
        "action": "review_only",
        "confidence_calibrated": False,
        "matching_frames": [],
    }
    if stop > config.max_seconds:
        return {**result, "reason": "CPU scan limit exceeded; no deletion proposed"}
    with sf.SoundFile(audio) as stream:
        rate = stream.samplerate
        data = stream.read(int(stop * rate), always_2d=True)
    # Choose highest-energy channel; averaging stereo could cancel the bass.
    if not len(data) or not np.isfinite(data).all():
        return {**result, "reason": "empty or nonfinite audio"}
    signal = data[:, np.argmax(np.mean(data**2, axis=0))]
    size, hop = (
        round(config.frame_seconds * rate),
        max(1, round(config.hop_seconds * rate)),
    )
    min_lag = max(1, int(rate / (440 * 2 ** ((72 - 69) / 12))))
    max_lag = min(size - 2, math.ceil(rate / (440 * 2 ** ((21 - 69) / 12))))
    fft_size = 1 << (2 * size - 1).bit_length()
    streak = []
    for start in range(0, len(signal) - size + 1, hop):
        frame = signal[start : start + size]
        rms = float(np.sqrt(np.mean(frame**2)))
        frame = frame - frame.mean()
        spectrum = np.fft.rfft(frame, n=fft_size)
        corr = np.fft.irfft(spectrum * spectrum.conj(), n=fft_size)[:size]
        energy = np.concatenate(([0.0], np.cumsum(frame**2)))
        lags = np.arange(min_lag, max_lag + 1)
        denom = np.sqrt(energy[size - lags] * (energy[size] - energy[lags]))
        normalized = corr[lags] / np.maximum(denom, 1e-20)
        peaks = (
            np.flatnonzero(
                (normalized[1:-1] > normalized[:-2])
                & (normalized[1:-1] >= normalized[2:])
            )
            + 1
        )
        matched = False
        if rms >= config.min_rms and len(peaks):
            best = float(normalized[peaks].max())
            candidates = peaks[
                normalized[peaks] >= max(config.min_periodicity, best * 0.95)
            ]
            if len(candidates):
                index = int(candidates[0])
                estimated = 69 + 12 * math.log2((rate / lags[index]) / 440)
                matched = abs(estimated - pitch) * 100 <= config.cents_tolerance
                if matched:
                    evidence = {
                        "frame_start_seconds": start / rate,
                        "frame_end_seconds": (start + size) / rate,
                        "estimated_midi": estimated,
                        "rms": rms,
                        "periodicity": float(normalized[index]),
                    }
                    result["matching_frames"].append(evidence)
        streak = streak + [start] if matched else []
        if len(streak) >= config.consecutive_frames:
            first = streak[0]
            # Require initial samples to carry energy before proposing a carry-in.
            initial_rms = float(np.sqrt(np.mean(signal[:hop] ** 2)))
            if first == 0 and initial_rms >= config.min_rms:
                return {
                    **result,
                    "status": "carry_in_candidate",
                    "boundary_note": {
                        "pitch_midi": pitch,
                        "onset_seconds": None,
                        "offset_seconds": stop,
                        "already_sounding": True,
                    },
                    "reason": "pitch evidence reaches boundary; "
                    "verify no new attack at zero",
                }
            return {
                **result,
                "status": "onset_region_candidate",
                "onset_interval_seconds": [
                    max(0, (first - hop) / rate),
                    (first + size) / rate,
                ],
                "reason": "pitch presence, not a verified attack; inspect waveform",
            }
    return {
        **result,
        "reason": "insufficient matching pitch evidence; no deletion proposed",
    }
