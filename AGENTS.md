# Project working agreement

## Teaching
- Explain each development or ML concept when it becomes relevant, including why a tool or practice is needed and how to verify it.
- Work in small, understandable steps. The owner is returning to substantial software development after working mostly on ad hoc scripts.

## File boundaries and preservation
- This repository is the write boundary for project work. Broader reading must be relevant to the task.
- Do not modify existing files outside this repository without explicit authorization for the exact change. Installations and user-level configuration require a separately explained scope.
- Create outputs in explicitly designated output directories. Do not overwrite existing user files just because you originally generated them.
- Preserve unrelated or uncommitted user edits. Inspect Git state before editing.
- Do not delete user data, rewrite history, force-push, or perform destructive Git operations without explicit authorization.
- Never initialize Git in a parent directory such as Documents or a home directory.
- These instructions do not replace enforced filesystem permissions; verify the active sandbox when opening a new task.

## Credentials and publication
- Never print, commit, or place credentials in chat, logs, notebooks, configuration examples, or generated reports.
- Prefer browser authentication locally and managed identities or OIDC for Azure workloads.
- Keep real credentials and original datasets outside the agent's writable repository where practical.
- Before staging, inspect the exact files. Before a push, check staged content for secrets and accidental personal data.
- The intended GitHub repository starts private. Publishing or changing visibility requires the owner's explicit instruction.

## Project direction
- Build evaluation and a baseline before fine-tuning music transcription models.
- Develop and run lightweight checks locally; use Linux on Azure for the current PyTorch training environment.
- Keep raw audio, datasets, downloaded weights, checkpoints, and experiment outputs out of Git.
- Before spending Azure credits, verify subscription eligibility, GPU quota, region, expected cost, and shutdown behavior. Budget alerts alone do not cap spending.
- Track reproducibility: code revision, dependency versions, configuration, data version, random seeds, and evaluation results.

## Current state
- See README.md and docs/setup.md. There is no application or ML implementation yet.
