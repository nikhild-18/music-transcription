# Music transcription

A learning-oriented project for evaluating and eventually fine-tuning AI models for music transcription.

## Status

Environment setup only. No model, training pipeline, or application has been implemented. No GitHub remote or Azure resource has been created for this project.

## Initial approach

1. Establish a contained development environment and credential-safe workflow.
2. Define the transcription task, output format, datasets, and evaluation criteria.
3. Run an existing baseline and build a repeatable evaluation harness.
4. Fine-tune only after the baseline and held-out evaluation are established.

Local development uses VS Code and an isolated Python environment. Current PyTorch workloads will run on Linux in Azure because official modern PyTorch builds do not support this workstation's Intel macOS architecture.

See [the setup record](docs/setup.md) and [the working agreement](AGENTS.md).

## Repository scope

This repository contains source, tests, documentation, and reproducible configuration. Original recordings, datasets, model weights, credentials, and large outputs are kept outside Git.

No open-source license has been selected yet. Select a license and audit the repository before public release.
