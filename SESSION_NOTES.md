# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves: an entry is
obsolete once its cycle is committed, durable knowledge belongs in `docs/`
or PREEXISTING.md, and only undocumented gotchas and active threads are kept
here. Pruned history remains recoverable from git.

(2026-10-15 prune: everything through Release 0.125.0 is committed and
documented — the itf campaign, releases 0.114.0–0.125.0, and every wrap-up
entry were removed; recoverable via `git log`.)
(2026-10-16 prune: the Performance-page/alignment plan run, the blocksize
ladder, the scroll-stability work, and the zfswipe notification rework are
committed with Release 0.126.0 — their entries were removed; recoverable
via `git log`.)
(2026-10-22 prune: the 0.126.1 revert-and-redo campaign through Release
0.126.3 is committed, pushed, and released — the restore/rework/wrap-up
entries were removed; recoverable via `git log`. Live items condensed into
the threads below.)

## Persistent gotchas (not documented in docs/)

- `source_helper` scoping law (vm-205 incident, 2026-10-16): bashinit's
  `source_helper` is a function, so a library sourced through it runs inside
  the helper's frame — every top-level `declare` (incl. `declare -A` maps
  declared by a sourced node.conf) becomes function-local and **vanishes when
  source_helper returns**, while functions and plain assignments survive
  globally. Any library state that must outlive the source needs `declare -g`
  / `-gA` (now done in node-lib, iscsi-lib, zfslockmanager — keep it that
  way for future libs). Symptom signature: a lookup helper works when its
  orchestrator sourced the lib at top level (storage-host runs inherit the
  populated globals; the `declare -f` guards skip source_helper) but returns
  empty-map failures only in ssh-shipped payloads running in fresh shells.

- Strict-mode (`set -euo pipefail`) flip idioms (2026-10-16 wrap-up, 13
  orchestrators migrated): (1) a function whose last statement is
  `[[ cond ]] && assign` returns 1 when the condition is false — close
  with an `if` or an explicit `return 0` or callers under `-e` abort
  (discover_iscsi_state class); (2) inside `while IFS= read -r` loops
  use `[[ -n "$x" ]] || continue`, never `[[ -n "$x" ]] && append` —
  a blank input line would otherwise make the loop itself the failing
  command; (3) associative-array reads on possibly-missing keys need
  `:-` guards even inside `[[ ... ]]` — `-u` fires at expansion time;
  (4) every `$(cmd | grep | head)` whose empty result is legitimate
  (LUN "not mapped", candidate "none found", sidecar "key absent")
  needs a trailing `|| true` — under pipefail the mid-pipeline grep
  fails the substitution and `-e` turns an empty answer into an abort;
  (5) `((++var))` is safe, `((var++))` is not (returns the old value);
  (6) child-engine heredocs are non-interactive — they get the full
  trio too, while sourced libraries must never set shell options.
  Sourced bashinit/node-lib/paths run under `-u` safely (all vars have
  defaults); on_storage/on_compute's `rc=$?` capture only works because
  every caller invokes them in an `if`/`||` context (errexit is
  suppressed inside functions called from conditions).

- Backslash line-joins keep the continuation line's indent, so
  `"arg-part-a" \` + indented `"part-b"` becomes **two arguments**, not
  one concatenated string — for one-argument payloads (ssh command
  strings, sed programs) build them in a variable with `+=`.  Inside
  unquoted heredocs, `\`+newline joins with the indent intact, so
  source-wrapping payload lines only ever changes inter-word spaces.
  When verifying a heredoc edit by extraction, aim at the RIGHT block
  (files can hold several with the same marker) and keep `<<MARKER` in
  the opener, or the "payload" executes as live script (a `cd /root` +
  `set -e` block aborts harmlessly as non-root, but the check is
  vacuous — 0 rendered lines means the check proved nothing).
- The bash test harness (`tests/run-tests`) runs suites **without pipefail**,
  so a failure branch that depends on a pipeline's non-zero exit code cannot
  fire under the harness (e.g. the dry-run estimate-failure branch of
  `zfs-migrate-send`). Tests assert the reachable path instead (the
  "Unable to get stream size estimate" message).
- `tests/test-archive-vm`: `ask_yn` cannot be mocked — sourcing `archive-vm`
  re-runs bashinit via `~/bashinit`, which unconditionally redefines it — so
  dialog answers are fed via stdin in prompt order. With dependent clones
  present, the severance question is the first stdin consumer, before
  the archive-base prompt.
- `docs/docs/commands-and-modules/modules.md`: nested (lettered) sub-lists
  need 4-space indentation; at 3 spaces Python-Markdown flattens the nested
  list, which `test_docs_integrity` rejects.
- `tests/python/test_gui_infrastructure.py` `TestPageAnchorMapping` audits
  `_PAGE_ANCHORS` against the **locally built docs site**
  (`docs/site/…/gtk-gui/index.html`, untracked). Adding a page or changing
  docs anchors requires BOTH updating that test's `expected_pages` set and
  rebuilding the site (`cd docs && mkdocs build`), or the full suite fails.
- bash EXIT traps under `set -e`: any failing statement inside an EXIT-trap
  handler aborts the rest of the handler (run-tests' kill_pytest_tree had to
  `|| true` the kill/wait pair). `append_exit_trap` in `bin/bashinit` is the
  registry to use — never a bare `trap ... EXIT` (it silently clobbers any
  earlier one). Also: bash 5.2 does not fire an EXIT trap armed inside a
  bare `while read` loop that is itself a pipeline segment, and a `&`-
  launched script is SIGINT-immune (POSIX async-subshell SIG_IGN) — use
  SIGTERM to test interruption paths.
- GTK dialog modules: `gi.require_version("Gtk", "3.0")` must run BEFORE
  `from gi.repository import Gtk` — importing Gtk first pins Gdk 4.0 and
  then `gui_helpers`' `gi.require_version("Gdk", "3.0")` raises. Every
  dialog module follows the `import gi` → `require_version` → imports
  order; new ones must too.
- New gi-guarded python suites must be added to `tests/requirements.manifest`
  (`gi tests/python/<suite>.py`) — `test_gui_infrastructure` audits manifest
  ↔ guarded-suite equality and the FULL suite fails otherwise (affected
  suites alone stay green).
- Overriding a **sourced library function** in a test (e.g. `transfer_pacer`)
  and then `unset -f`-ing it DELETES the function — unlike external
  commands there is no PATH fallback. Save and restore with
  `_orig=$(declare -f fn)` … `eval "$_orig"` (0.125.0 cycle: `unset -f
  transfer_pacer` broke the two paced tests that ran after it).
- Pipeline child **startup** order is not guaranteed by bash — the scheduler
  can run any subshell first. Tests that assert stage order must record
  data-dependent markers (a downstream stage writes only after draining the
  upstream's EOF), never echo-at-entry (0.125.0 cycle: the pacer-before-pv
  order test failed ~1 run in 6 under load).
- test-lib.sh redirects `log_msg` into `$_TEST_LOG_FILE`; a `get_log()`
  helper is NOT provided by test-lib — it is defined per-suite
  (test-transfer-lib, test-zfs-migrate-send). In suites without it, assert
  against `cat "${_TEST_LOG_FILE}"`.
- Docs viewer: it picks its site ONCE at window construction — rebuilding
  the repo site does not fix an already-open window; the browser/
  desktop-handler openmd flow still receives paths baked at `mkdocs build`
  time (edit_links.py unchanged — relative baking would break the handler).
  Deployed launches resolve through `current`, so a versions/<v>-baked URL
  re-anchors to `current` and survives version switches.

- `tests/test-module-dependencies` now scans `bin/` and `lib/` too (was
  repo-root-only, i.e. vacuous — the repo root has no loose scripts). New
  scripts must resolve every called function through a direct `source`,
  `source_helper`, a `find_zfsutility_script` reference, or a variable
  assignment feeding `source "$var"`; `declare -f <fn>` guards mark a
  function as an optional caller-provided dependency (the
  zfslockmanager→node-lib pattern). The scanner masks multi-line quoted
  strings and comment tails, so python `-c` payloads and `# ... (send base)`
  comments are not mistaken for bash calls.

## Active / parked threads

- **End-user usability fixes from the 0.126.3 wrap-up feedback (2026-10-22,
  uncommitted).** Three items off the wrap-up report's end-user notes:
  (1) Drop-in automation: `switch-version`'s `install_wiring` now refreshes
  the `rtslib-fb-targetctl` drop-ins from the ACTIVATED version's
  `share/two-node/` (gated on `command -v targetctl` — storage hosts only;
  cmp-identical files untouched, daemon-reload only on change).
  install-two-node's own drop-in step was removed — it copied from the repo
  checkout, masking version skew (the exact trap the feedback came from).
  (2) `iscsi-recover-encrypted-luns` no longer prints `qm start` commands;
  recovery output ends at the summary. (3) The IQN-drift orphan flows do
  their own usage checking: new read-only `probe_target_usage` in node-lib
  (ACL/demo context locally; one ssh to the compute host for
  qemu-server/lxc configs referencing the IQN + live iscsiadm sessions;
  unreachable ⇒ treated as in-use). setup-iscsi-targets refuses to even
  offer deletion of an in-use/unverifiable orphan; install-two-node's
  drift gate dies before its proceed prompt unless every drifted target is
  verified unused (user chose hard-refuse over an evidence-enriched
  prompt). install-two-node now sources node-lib instead of hand-copying
  the node.conf lowercase vars (removes the duplicated parse, gains the
  probe). Tests: probe matrix in test-node-lib (subshell mocks), two new
  drift-refusal flow tests (ssh mock gained a qemu-server payload case with
  _mock_probe_refs/_mock_probe_sessions/_mock_probe_unreachable knobs),
  three drop-in tests in test-switch-version (fake targetctl on PATH;
  empty-PATH trick for the no-targetctl skip), structural probe-gate
  assertions in test-iscsi-fresh-install-guards.

- **upgrade-zfsutilities prerequisite gate (added 2026-10-22, uncommitted).**
  After download/staging, the upgrade now runs the STAGED release's
  bin/check-prerequisites (mode from upgrade_lib_legacy_hosts' first line;
  deployed checker as fallback; WARN-skip when neither exists) through the
  installers' shared run_interactive_prerequisites, aborting rc=1 before
  any scan/change when it cannot pass. installer-lib.sh's
  installer_failures became declare -gA — required for sourcing through
  source_helper (the frame-local declare would have silently corrupted
  remediation parsing). Tests: stub checker in the fake tarball records
  args to FAKE_PREREQ_MARKER, exits FAKE_PREREQ_RC; abort + mode tests.

- **Rsync-pull failure tails (fixed 2026-10-22, uncommitted).** The 2026-10-21
  stewie runs (both profiles, 0.108.0 and 0.126.1) failed every rsync pull
  rc=11 with only "Error in file I/O" in the session log — the pull wrapper
  shipped all output to the source host's rsync-pull.log, starving
  _run_command's capture that _diagnose_rsync_failure feeds on. Wrappers now
  tee to a local temp file and print a header + tail -15 to the runner on
  failure; the WARN carries "(full rsync output: host:path)". The Oct 21
  root cause is unrecoverable (local log truncated at today's 06:00 reset;
  rocky/tweety logs off-limits) and self-resolved — 2026-10-22 runs green,
  threeamigos clean. behavioral test: TestRsyncLogWrapperBehavior.

- **CI red on the 0.126.3 push (fixed 2026-10-22, uncommitted).** GitHub's
  first run of the 0.126.2+0.126.3 batch failed 3 python tests (test +
  nightly soak jobs alike): the realized geometry check asserted the
  matplotlib ladder a matplotlib-less runner never selects (matplotlib is
  now in requirements-dev.txt, flowing to CI and the dev container via
  install-test-deps.sh), and the two spawn-failure tests hit
  /var/log/zfsutilities through start()'s _truncate_rsync_log as the
  unprivileged runner user (test_backup_runner's _patch_log_dirs now
  redirects RSYNC_LOG_DIR/RSYNC_LOG_FILE into its tmpdir). Full suite green
  locally; the definitive check is the CI run after push. A matplotlib
  requirements-manifest capability was considered and rejected — the
  canonical-env contract makes a hard failure in a non-canonical
  environment the honest outcome.

- **PREEXISTING.md resolution pass (2026-10-22, uncommitted).** All nine
  actionable entries were fixed this session (safe-iscsi-save mapped_luns
  strip, encrypted-LUN recovery script + target-scoped lookups,
  boot-config.conf ExecStartPost, IQN-prefix drift guards in three places,
  redirected-state migration fence in both python and bash sweeps, the
  module-dependency scan extension, the charting mock fence, Performance
  page ellipsize, the conftest private-Xvfb fence). Remaining entries are
  the Zensical 1.x wait (rechecked 0.0.71) and the user-deferred
  infra-vdev planning objective.

- **unarchive-vm 205 live rerun (pending 0.126.3 deployment).** The Step-2
  `declare -gA` fix shipped in 0.126.1+; tweety's live rerun died only
  because stewie ran 0.125.0 (pre-fix). Zvols are restored+verified; only
  iSCSI reconstruction is blocked, and the post-deploy rerun takes the
  create path on both targets (nvme1 + threeamigos) — no enroll-iscsi-pool
  needed.

- **Guest-probe live validation (pending the user's paste).** After 0.126.3
  deploys: `sudo "/NFS1/dan(NFS1)/zfsutilities-pub/share/dev/validate-guestfs-probe.sh"`
  on stewie, then analysis of its output (self-check already green there
  against the byte-identical 0.126.2 module).

- **0.126.1-revert residue (user decisions pending).** /var/lib/zfsutilities
  holds pool_activity.json + scrub_state.json.20261020T163711.bak from the
  brief repo-GUI run — the scrub queue comes up empty until the .bak is
  restored; two dangling ~/.config symlinks from the migration-sweep
  incident remain. The aborted pool-activity campaign lives only on branch
  `archive/pre-revert-20261020` (07010d6).

- **Zvol-snapshot-mount plan v3 (2026-10-01) — parked, NOT approved.** Plan
  written next to v1/v2 in
  `/NFS1/dan(NFS1)/zfsutilities-plan/Plans in abeyance/Zvol-snapshot-mount/`.
  Base is v2's architecture plus four fixes: (1) the archive-vm guard must
  scan raw discovery output (Pass 1 drops the archived VM's own clones — the
  natural browse-then-archive case); (2) promote-vm-clone marker skip in all
  four awk blocks; (3) migration pre-flight on source AND destination pools
  (receive uses -F); (4) reuse the shipped `parent_type` field + refreshed
  line numbers. Implementation notes: dataset-component-only marker test in
  buildfsarray; wait for the clone's /dev/zvol node before loop_attach.
  Shipped behavior until approved: volume-snapshot mounts rejected with WARN
  + disabled Mount button; no clone-based volume-snapshot mounting (user
  decision).

- **Zensical vs MkDocs evaluation (2026-10-02) — research only, no code
  changed.** User asked whether Zensical (zensical.org, the Material-team
  successor SSG; note spelling, not "Zensicle") can replace MkDocs here.
  Answer: functionally yes at 0.0.67 — verified by pip-installing zensical in
  a scratch venv and building a copy of the real docs: clean build, page set
  identical to mkdocs output (32/32 HTML), build time on par (~7.5 s), and
  the pip install is self-contained (no mkdocs-material needed; classic
  Material theme built in). The two custom hooks are the only functional
  gap, and both have config-only replacements, verified: `hooks:` is silently
  ignored by zensical, so (a) version_stamp.py → `extra.version: !ENV VAR`
  (footer rendered "ZFS Utilities v…"); (b) edit_links.py → `repo_url:
  openmd:/` + `edit_uri: /<abs path>/docs/docs/` yields byte-identical
  openmd:// URIs (MkDocs itself rejects a non-http repo_url, so that config
  becomes zensical-only; side effect: a "Go to repository" header icon
  pointing at the docs dir; the absolute path is machine-specific, unlike the
  hook's dynamic derivation). Mermaid: `<pre class="mermaid">` fences render
  and the mermaid runtime is inlined in bundle.js (not browser-verified).
  pymdownx.details is configured in mkdocs.yml but unused in content (zero
  `???` blocks). If migrating, use `theme.variant: classic` for Material
  look parity. Migration surface beyond docs/: bin/startdocserver (build/
  serve invocations `zensical build --clean` / `zensical serve -a 0.0.0.0:8000`,
  plus exporting the !ENV version), bin/check-prerequisites (mkdocs<2 pin
  logic), lib/installer-lib.sh, share/dev/install-test-deps.sh, and tests/
  {test-startdocserver, test-deploy-version, test-installer-checks,
  test-check-prerequisites, python/test_support.py}. Holding back: still
  0.0.x with releases every few days — expect breaking changes before 1.0.
