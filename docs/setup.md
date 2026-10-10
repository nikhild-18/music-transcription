# Setup record

## Completed

- Audited an Intel Mac with macOS 15.7.9, four CPU cores, and 8 GB RAM.
- Storage cleanup was performed by the owner. The follow-up audit reported 139 GiB available.
- Confirmed that Documents no longer contains an enclosing Git repository.
- Initialized this dedicated repository with a main branch.
- Added a file-preservation working agreement and initial ignore rules before adding project code or dependencies.
- Configured repository-local Git identity using the verified GitHub username and ID-based noreply address; global Git settings were preserved.
- Checked that ignore rules cover sample secret, virtual environment, data, checkpoint, and scratch paths.

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
| uv, Azure CLI, FFmpeg | Not found on the paths checked during the initial audit |

## Next checkpoints

- Register only this repository as a local Codex project and open it in VS Code.
- Verify effective write permissions. The setup task originally has broader access to the Codex documents directory; this file does not change that policy.
- Retire the obsolete Documents-level trusted-project setting without changing unrelated settings.
- Install uv and a project-specific Python version after reviewing compatibility. Python 3.11 is provisional until the chosen baseline's requirements are checked.
- Create pyproject.toml, a project virtual environment, and a committed lockfile. Keep ML-only dependencies separate from lightweight local dependencies.
- Add linting, tests, and secret scanning; verify using harmless fixtures.
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
- [Codex permissions](https://learn.chatgpt.com/docs/permissions)
- [Intel macOS PyTorch build deprecation](https://dev-discuss.pytorch.org/t/pytorch-macos-x86-builds-deprecation-starting-january-2024/1690)
