"""Create a synthetic, non-training timing reference through the viewer contract."""

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from bass_pipeline.audit import repository_path


def publish(root, destination):
    destination = repository_path(root, str(destination.relative_to(root)))
    if not destination.is_relative_to(root / "outputs/diagnostics"):
        raise ValueError("sync check must be under outputs/diagnostics")
    destination.mkdir(parents=True, exist_ok=False)
    rate = 16000
    signal = np.zeros(rate * 6)
    events = []
    for second in range(1, 6):
        # Low-level, short tone bursts with a sharp known start; no microphone use.
        t = np.arange(320) / rate
        signal[second * rate : second * rate + len(t)] = (
            0.15 * np.cos(2 * np.pi * 800 * t) * np.exp(-t * 180)
        )
        events.append(
            {"id": str(second), "label": "Known tone onset", "start_seconds": second}
        )
    sf.write(destination / "clicks.wav", signal, rate, subtype="PCM_16")
    (destination / "events.json").write_text(json.dumps(events, indent=2))
    relative = str(destination.relative_to(root))
    descriptor = {
        "schema_version": "1.0",
        "run_id": destination.name,
        "stage": "synthetic playback timing check",
        "provenance": {
            "purpose": (
                "Compare heard clicks with white cursor crossing orange markers "
                "at 1–5 seconds. Not training data; no repairs or offsets."
            )
        },
        "recordings": [
            {
                "recording_id": "timing-clicks",
                "dataset": "synthetic-QA",
                "duration_seconds": 6,
                "training_eligible": False,
                "audio": {"path": relative + "/clicks.wav", "time_origin_seconds": 0},
                "layers": [
                    {
                        "id": "known-onsets",
                        "kind": "events",
                        "path": relative + "/events.json",
                        "time_origin_seconds": 0,
                    }
                ],
            }
        ],
    }
    (destination / "viewer.json").write_text(json.dumps(descriptor, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    publish(root, repository_path(root, args.output))
    print(f"Timing reference ready: {args.output}")


if __name__ == "__main__":
    main()
