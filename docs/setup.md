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
