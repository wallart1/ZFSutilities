# Contributing to ZFS Utilities

Thank you for considering a contribution. This project moves quickly —
often several releases a week — so this document explains the contribution
shapes that survive that pace, and how submissions are processed.

## Issues first

For anything beyond a small fix, open an
[issue](https://github.com/wallart1/ZFSutilities/issues) first and describe
the problem or use case. Substantial changes are usually implemented
in-tree by the maintainer, and a discussed issue is the fastest route to
see an idea land. Opening an issue first also avoids weeks of work on a
change that cannot be accepted in its proposed shape.

## What makes a good pull request

- **Small and localized.** One fix or one improvement per PR. Typo fixes,
  documentation corrections, and single-file bug fixes are ideal.
- **Short-lived.** Rebase onto the latest `main` before submitting, and
  rebase again if review takes time. This repository's `main` advances
  daily; branches that fall behind by a release or more are closed, and
  you are welcome to rebase and reopen.
- **Honest about testing.** State what you ran and on what environment.

## Before you submit

1. Fork the repository and create a topic branch.
2. Rebase onto the current `main`.
3. Run the gates your environment supports, and say so in the PR:
   - `./tests/run-tests` — the full suite. The environment preflight
     skips suites whose requirements (root, ZFS test pools, GUI
     libraries) are unavailable and reports them as skipped, so a run on
     a plain Linux box is still meaningful.
   - `ruff check .` — if you touched Python (configuration lives in
     `pyproject.toml`).
   - `mkdocs build -f docs/mkdocs.yml` — if you touched the
     documentation.
4. Read [AGENTS.md](AGENTS.md) — it is the project's coding contract. The
   short version: no hard-coded installation-specific data in mainline
   code; no deprecated constructs; tests accompany behavior changes;
   documentation is updated with the change.
5. Do **not** edit `VERSION` or the change log; releases are cut by the
   maintainer.

## How your pull request is processed

- **Nothing merges automatically.** Every PR is manually reviewed by the
  maintainer; CI passing is necessary but not sufficient.
- CI (the test workflow) runs automatically on your PR.
- A PR is a snapshot of the moment it was last rebased. If it can no
  longer be evaluated against current `main`, it may be closed with a
  request to rebase and reopen.
- Sometimes an idea is implemented in-tree instead of merging, because
  the change must fit project conventions or an in-flight campaign. In
  that case the originating issue or PR is credited in the commit
  message. Closing a PR is not a judgment about the contributor.
- Changes touching installation, deployment, or CI receive extra
  scrutiny: this project runs as root on live ZFS pools.

By submitting a contribution you agree it is licensed under the project's
[MIT License](LICENSE).
