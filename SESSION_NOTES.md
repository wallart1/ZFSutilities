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
(2026-10-22 release prune: the 0.126.3 follow-up campaign — wrap-up
usability fixes, upgrade prereq gate, rsync failure tails, CI red,
PREEXISTING resolution pass — is committed as 1e5d92e, pushed, and
released as 0.127.0; those entries were removed, recoverable via
`git log`.)
(2026-10-23 release prune: the 0.128.0 and 0.129.0 campaigns — the
unarchive-vm live-tree iSCSI rebuild + F-020..F-024 lifecycle fixes,
canmount profiles, probe-target dedupe, FHS conf precedence, both
wrap-up review passes, and the zfstestvm lun-32/33 + cron.log threads —
are committed as 3713eff/a964289, pushed, and released as v0.129.0;
those entries were removed, recoverable via `git log`. Live items
condensed into the threads below.)
(2026-10-24 release prune: the 0.130.0 combined-release campaigns — the
itf fast-re-verification + j08/j09 journeys (pub lane, 94558b8), the
iSCSI-resilience M1/M2 state map + reconcile engine with the
safe-iscsi-save hook and shared iscsi-lib parsers (pub2 lane, 5395aff),
both lane wrap-ups, the lane merge ad27709, and the parallel-repo
infrastructure notes — are committed, pushed, and released as v0.130.0;
those entries were removed, recoverable via `git log`. The lane workflow
and the same-version merge rule live in the shared agent memory and the
owner's guide.)

(2026-10-25 release prune: the 0.132.0 combined release — pub's
strict-mode campaign with the declare -gA law, the offsite hotfixes
(zfshold per-snapshot contract, j07's zfsdelfs/mydir fix), the j10
journey + F-025 baseline capture, the GUI payload e2e matrix, both
7-step wrap-ups, and (via the pub2 lane merge 6a3c26b) 0.131.0's iSCSI
resilience M3+M4 with activation wiring, the pub3 Dashboard/GUI work,
the lane merges, and the pub3-lane infrastructure notes — are
committed, pushed to origin main, tagged v0.132.0, and released; those
entries were removed, recoverable via `git log`.)

(2026-10-26 release prune: the 0.133.0 combined release — pub's
per-enclosure rate governance campaign (P1-P3) with the j12
interrupted-upgrade journey and the wrap-up fixes, and via the lane
merges pub2's iSCSI resilience M5+M6 (repair-vm-disk-refs,
export-iscsi-state --print-map, j13/j14, the F-026 fence gate fix)
with the itf run lock and orphan fence, and pub3's scheduler
%-escape fix, checkagainst ui_state resurrection fix, unsaved-changes
quit guard, cron breadcrumbs, Performance fixes, README screenshots,
and the changelog archive split — are committed (3187f7e, d7a8b38,
0111e0f), pushed to origin main, tagged v0.133.0, and released; those
entries were removed, recoverable via `git log`.)

(2026-10-31 release prune: the 0.134.0–0.136.0 releases — pub's
enclosure P4/P5 GUI, the iSCSI boot-incident hardening (0.135.0), the ITF
recovery campaign G0–G5 with repair plans 022–024, pub2's shadowed-mount
fence/cancel/mount-order work and 0.136.0's restore resume + Logs
Miscellaneous list + sidebar tab-red, pub3's Datasets Show Details work
and 0.136.0's notifications, and both lane-merge turn records — are
committed, pushed to origin main (0111e0f..55d4c3d), and released as
v0.136.0 (0.134.0/0.135.0 shipped untagged inside the same push); those
entries were removed, recoverable via `git log`.)

## Persistent gotchas (not documented in docs/)

- Logs tab two-list structure (2026-10-30): the main list keeps
  `_LOG_FILENAME_RE` (core types only, unchanged); everything
  session-shaped with a non-core type routes to the collapsed
  "Miscellaneous Logs" treeview via `_MISC_LOG_FILENAME_RE` (type class
  excludes `_` so the type/name split falls on the first underscore —
  do NOT widen it to `[A-Za-z0-9_-]` or names containing underscores
  split wrong). Both lists share ONE LogIndex pass
  (`_scan_session_dir` returns both row sets and the index
  `remove_missing` runs on the union — splitting the pass into two
  scans would purge the other list's index entries every refresh).
  Shared viewer + Delete button: `_on_selection_changed` takes the
  source view and mutually clears the other list under
  `app._logs_clearing_other_view` (re-entrancy guard); the delete
  button sensitivity and `_on_delete_selected` union both views.
  Persistent-log rows (cron in main; scrub/rsync in misc) come from
  `paths` config keys via `_scan_log_and_rotations` — add new
  persistent logs to `_PERSISTENT_LOG_SPECS`, not ad hoc scans.
  Production facts that motivated this (stewie 2026-10-30): 264 of 294
  session files were `cli`; sessions dir holds nothing older than
  2026-10-21 (retention 30, prune mtime-based — the Oct 21–22 bare-metal
  OS restore is the likely history loss point, not a pruning bug).

- MagicMock dialog suites vs refresh_*_page sections (2026-10-26
  enclosure work): anything refreshed from a refresh_*_page helper must
  tuple-guard its selection reads (see disks_page._repopulate_enclosures)
  — four dialog suites drive refresh_disks_page with MagicMock apps
  whose selections answer non-tuples, and an unguarded unpack takes them
  all down.

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

- **Guest-probe future work (validation COMPLETE 2026-10-23):** surface
  sample.pve_failure inside the Alignment view when VM layers are
  missing.

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


## 2026-10-31 (night) — v0.136.0 published; CI TTL-cache poisoning fixed

Published 0.136.0 (pushed 0111e0f..55d4c3d, tagged v0.136.0, GitHub
release; compare base v0.133.0 — 0.134.0/0.135.0 rode the push untagged).
Post-publish prunes (notes, repair-plans, FINDINGS, results) sit in the
working tree riding the next notes commit. CI on the pushed commit went
RED: 5 dashboard TTL-cache tests on one xdist worker — a leaked REAL
async dashboard-refresh thread (the page-switch handler fires it) whose
ssh/zpool gathers time out over seconds on runners, so its cache writes
landed inside later tests (compute-mocks at 0 calls, one
[]-is-not-None). Unreproducible locally (subprocesses fail fast) across
pytest 7.4.4 and a pytest-9.2.0 venv, 4 workers, Xvfb; CI installs
pytest 9.2.0 via install-test-deps.sh vs the dev host's 7.4.4. Fix
(user-approved), two commits: (1) 9e927cd — tests/python/conftest.py
autouse drain: the refresh worker is wrapped to track its threads; after
every test live workers are joined (70s bound) and the three TTL caches
reset cold. Red/green-proven with a straggler simulation; the CI rerun
proved the stragglers REAL (the python leg stretched 59s→326s from the
joins) but the five TTL tests stayed red — the drain was necessary, not
sufficient. (2) 43ebb1d — the three TTL suites now patch in a PRIVATE
cache dict plus a controlled monotonic() clock per test (dashboard_page
uses time.monotonic() only), making the assertions independent of
wall-clock time and shared module state; test_failure_is_not_cached
reports the dp module identity + cache on failure (the diagnostic if
this ever recurs — a dual-module-instance cause would show there). CI
GREEN on 43ebb1d. The tag's red run stays red (never move tags); the
fix commit's green run is the proof. The exact CI-side writer was never
pinned down (no local reproduction across pytest 7.4.4/9.2.0 venv, 4
workers, Xvfb); the per-test isolation makes the question moot.

## 2026-10-31 (late) — j11-payload-e2e green on the published payload

User cued the live j11 run (the 0.136.0 lanes include payload-stack
work: interrupted-restore resume + run-completion notifications). Run
`run-20261031-192033-j11-payload-e2e`: every journey step green —
template clone, three test pools, 0.136.0-dev staged from the working
tree, full payload matrix (offsite holds/incrementals/rollback/resume/
scrub-pause, backup/prune/rsync, strict-mode orchestrators; real
per-scenario wall times, not a vacuous pass), pool-residue clean.
Guest + both disks + both checkpoint snapshots destroyed at the
verdict; bases clean, lock freed. ~8.5 min wall — clone-linked start
+ small pools, far under the G5 install-flow estimates, as expected
for j11's shape. No FINDINGS; deploy cue's payload-validation
precondition is now green.

## 2026-11-01 — repair plan 025 (F-034) executed, live-disproved,
## corrected, verified

User cued plan 025 (setup-iscsi-targets portal binding). First pass
implemented the plan as written (per-target create-then-replace,
fresh-TPG window only): red-proven suite, docs rows, FINDINGS → fixed.
The j05 journey disproved the plan's core premise LIVE: LIO portals are
host-level sockets — the 0.0.0.0:3260 wildcard binds INADDR_ANY:3260,
and while ANY TPG rides it no specific :3260 portal can be created
anywhere ("Could not create NetworkPortal in configFS"); the plan's
"port conflict only exists for the SAME address" contradicted F-024's
own verified row. Guest-side probes proved the working sequence: purge
the wildcard from ALL TPGs, then bind specifics (two-arg `portals
create <ip> <port>` — the one-token ip:port form parses as a bare IP
and can never bind). User approved the corrected recipe same day:
post-loop host-wide purge-then-bind in the all-fresh window only
(existing targets never purged — a wildcard removal on an established
target would drop live sessions), wildcard-restore rollback, FATAL if
a TPG ends portal-less (F-024 law). Unit portal mock rebuilt to model
host-level sockets (shared ip:port references, ANY-bind blocking) —
the per-TPG mock it replaced is what let units stay green against an
impossible mechanism; red-proven against the pre-025 script. Harness
defects fixed in-cycle (never FINDINGS rows): j05's portal probe used
an invalid one-shot `targetcli ... ls 2` (depth parses as a path) →
per-TPG portals ls sourced from node.conf; j16's assert grepped the
pre-correction wording. Verification: j05 --rerun green (three
specific binds live, wildcard purged, first LUN round trip through
the specific portal) and j16 --rerun green after a mid-run dev reboot
(--rerun takeover did exactly what the orphan fence designed); S7b
total-wipe rebuild storage-IP-bound with recovery through it. F-034
`verified`; plan 025 closes at the next release prune. Deploy note:
production targets exist → setup re-runs keep today's posture there;
the specific bind lands only on fresh installs.

User cued repair plan 026 (map grants dimension, F-037). Executed as
written with one execution-time decision the plan left open: dual-read
migration with the version marker bumped to 2 (readers accept legacy
name-list maps; identity-grant behavior preserved for them — the map's
own pools-key precedent). export-iscsi-state records per-initiator
mapped_lun->tpg_lun pairs (parser extended in iscsi-lib.sh; red-proven
on the old shape; golden regenerated); reconcile recreates recorded
pairs exactly — grant-bearing ACL records rebuild even on demo TPGs
(a demo login self-generates identity grants only), a present pair
mapping differently refuses (FATAL) and — second in-cycle find — the
map-refresh gate now blocks on ANY apply failure, because the failed
ACL grant previously slipped past the per-backstore outcome check and
would have let the refresh overwrite the recorded authority;
iscsi_grant_lun_to_acls (recover + add-encrypted heal path) recreates
recorded pairs and leaves initiators whose recorded set lacks the LUN
ungranted instead of blanket identity. Third find, live-proven by the
first j16 attempt: `targetcli ... | grep -q` under pipefail flips found
objects to "missing" (grep -q exits on match, targetcli SIGPIPEs, 141
pipeline) — it made reconcile refuse a live target at S6 while the
compute sessions stayed up; a 300/300 local repro; fixed on all
plan-026 surfaces plus setup's /iscsi ls probes, remaining ~25 sites
recorded in PREEXISTING.md. The rerun then hit the shared-lab fence:
pub2's concurrent journeys hold VMID 8001-8004 on the base hosts and
my lane's stale Oct-31 claim points at pub2's live j05-storage, so the
orphan fence refuses (destroying/--rerun would hit pub2's guest).
User chose: keep waiting for a window (background retry loop, verdict
to /tmp/j16-queued-verdict.txt); F-037 stays `fixed` until that run
flips it `verified`. Also fixed in the window: one dev-tarball build
failure was my run racing the user's live doc edits ("file changed as
we read it") — timing only. Full bash suite green once at the end;
python 4355 passed with one host-load flake (profile_runner 15s
subprocess timeout under pub2's VM load; 110/110 green in isolation).
