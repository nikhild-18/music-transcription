"""Run with scripts/uv run --frozen python -m bass_pipeline audit."""

import argparse
import json
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from bass_pipeline.audit import inspect_archive, repository_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["audit"])
    parser.add_argument("--config", default="configs/pipeline.toml")
    parser.add_argument(
        "--output", help="New JSON report under outputs/; never overwritten"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path = repository_path(root, args.config)
    config = tomllib.loads(config_path.read_text())
    output = None
    if args.output:
        output = repository_path(root, args.output)
        if not output.is_relative_to(root / "outputs"):
            parser.error("reports must be under outputs/")
        if output.exists():
            parser.error("output already exists; choose a new report name")
    report = {
        "created_utc": datetime.now(UTC).isoformat(),
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "git_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "config": config,
        "archives": {},
    }
    for item in config["archives"]:
        print(f"Verifying {item['dataset']} ...", flush=True)
        report["archives"][item["dataset"]] = inspect_archive(
            repository_path(root, item["path"]), item["md5"]
        )
    encoded = json.dumps(report, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            stream.write(encoded)
        print(f"Report: {output.relative_to(root)}")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
