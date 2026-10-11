# Music transcription

A learning-oriented project for evaluating and eventually fine-tuning AI models for music transcription.

## Status

The contained local Python environment and development checks are ready. No model,
training pipeline, or application has been implemented. No GitHub remote or Azure
resource has been created for this project.

## Initial approach

1. Establish a contained development environment and credential-safe workflow.
2. Define the transcription task, output format, datasets, and evaluation criteria.
3. Run an existing baseline and build a repeatable evaluation harness.
4. Fine-tune only after the baseline and held-out evaluation are established.

Local development uses VS Code and an isolated Python environment. Current PyTorch workloads will run on Linux in Azure because official modern PyTorch builds do not support this workstation's Intel macOS architecture.

See [the setup record](docs/setup.md) and [the working agreement](AGENTS.md).

## Local checks

Use the repository wrapper rather than a globally installed `uv` command:

```sh
scripts/uv sync --frozen
scripts/check
```

The wrapper keeps uv's cache, managed Python installation, and virtual environment
inside ignored repository directories. `scripts/check` runs Ruff, pytest, and a
secret scan over tracked and untracked files that are not ignored.

Review all current changes and rerun the checks with:

```sh
scripts/review
```

Create a local commit by supplying a message and the exact files to include:

```sh
scripts/commit "Set up contained Python development environment" \
  .gitignore .python-version README.md docs/setup.md pyproject.toml \
  scripts/check scripts/commit scripts/review scripts/uv \
  tests/test_setup.py uv.lock
```

The commit command refuses pre-existing staged changes, runs the checks, stages
only the named paths, shows the complete proposed commit, and asks for confirmation.
It does not push anything to a remote.

## Repository scope

This repository contains source, tests, documentation, and reproducible configuration. Original recordings, datasets, model weights, credentials, and large outputs are kept outside Git.

No open-source license has been selected yet. Select a license and audit the repository before public release.
