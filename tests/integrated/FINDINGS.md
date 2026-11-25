# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped.  Pruned at the 0.141.0 release (2026-11-12): F-047 and
F-050 — both fixed in the dev tree (2026-11-11, approved session
plan for the pub-tree j22 run), verified by the green archive
replay of the same 107-item draw on the fixed tree
(run-20261111-203336-j22-function-survey — every selected item
passed), and shipped in 0.141.0.  Pruned at the 0.142.0 release (2026-11-17): F-051 — the
  Pools-page Export D-state freeze (live iSCSI LUN session held the
  pool's zvol; `zpool export` blocked uninterruptibly on the UI thread
  with no bound).  Fixed by the release-gate wrap-up: the export runs
  in a worker thread with a hard UI-side deadline (`EXPORT_STALL_WARN_S`,
  default 120 s), and on stall the holder-naming WARN plus the
  blocker-recovery flow takes over; verified by the archive replay
  run-20261117-162554 (export completed at the bound, window alive,
  survey green) and shipped in 0.142.0.  Earlier closures stay
recoverable via `git log` (F-048 and F-049 in 0.140.0; F-034 in
0.137.0; F-045 and F-046 in 0.138.0, along with plan 026's F-037
verification — the user-cued j15/j16 reruns of 2026-11-04).  No
rows remain; the table below is empty until the next journey
files a finding.

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-052 | 2026-11-23 | j22-function-survey (`results/run-20261123-200238-j22-function-survey/`) | `zfsresume` printed no verdict at all for a valid resume token — on zfs 2.2.2 the `zfs send -nP -t` dry-run exits 0 with the decoded contents, and both report branches sat inside the failure path; an unrecognized probe failure was misreported as "seems valid" | `bin/zfsresume` token validation | verified (replay `run-20261123-202938-j22-function-survey` green, real-path item passed with the live "seems valid" verdict) | in-session fix under the approved 2026-11-23 survey plan |
| F-053 | 2026-11-24 | j22-function-survey full-function leg (`results/run-20261124-004523-j22-function-survey/`) | `zfsdailybackup`/`rsync-dailybackup` left `compute_host` unset on two-node sites: both templates hand-rolled the node.conf resolution and defined the lowercase host pair only in single-node mode, while node.conf carries the uppercase `COMPUTE_HOST` — stock non-strict runs degraded to a failed-pull WARN at the compute pull banner; any strict-mode site copy died "unbound variable" | `bin/zfsdailybackup` + `bin/rsync-dailybackup` node resolution | verified (run-20261124-010402: the full-function leg's site pair ran both pulls and the backup send past the compute banner) | in-session fix under the approved 2026-11-24 full-function plan |
| F-054 | 2026-11-24 | j22-function-survey full-function leg (`results/run-20261124-010402-j22-function-survey/`) | `zfsdailybackup`'s prune leg dies under the strict mode its own shipped `rsync-dailybackup` template imposes (the template carries `set -euo pipefail`, which sourcing turns on for the rest of the orchestrator): the sourced `cleanup()` reads `${#releaseholds_tags[@]}` and bare `$1`–`$4` positionals before any default, so the prune call (`cleanup '' '' dailybackup`) FATALs "unbound variable" — any stock-template user with `prune='Y'` (the default) hits this after the first successful backup | `bin/zfscleanup`/`bin/zfsretain`/`bin/zfsdelsnap` + the orchestrator templates' strict-mode robustness | verified (run-20261124-052832 green: the full-function leg runs the site pair end to end — snapshot, pulls, send, prune — rc 0) | in-session fix under the approved 2026-11-24 full-function plan: `:-` defaults on caller scalars/positionals and `declare -p` guards for tag arrays (zfscleanup, zfsretain, zfsdelsnap); the orchestrator re-asserts its documented non-strict mode at the rsync source point AND at the prune leg (sourced standalones — `zfs-send-receive` sources strict `zfsdelfs` — re-arm mid-run; live-traced via bash -x in the kept lab); regressions: test-zfscleanup strict-mode caller test, test-zfsdailybackup/test-rsync-dailybackup two-node resolution tests; 0.144.0 lane wrap-up (2026-11-24) closed what the fix had missed — three more unguarded reads in `delsnap` (the tag-array length, the remaining-holds result, `skipbusy`) and the tag-array length in `zfsmassdelsnaps` — the same way, each with a strict-caller regression test in test-zfsdelsnap, test-zfsretain, or test-zfsmassdelsnaps |

Status values: `open` → `planned` (repair plan approved) → `fixed`
(dev change landed) → `verified` (rerun green) → `accepted` (user waives).
Two further terminal states close a row without a code change:
`documented` (product-truth rows → repo docs; UX/future-direction rows →
`REQUIREMENTS.md`, the row links its destination) and `superseded`
(folds into another row). Every finding ends in exactly ONE terminal
state — no row stays open past a campaign wrap (G5 triage rule,
2026-10-31; the user adjudicates the non-obvious calls via phase/repair
plans).

Guidelines:

- A finding is a *product* behavior gap observed through the end-user
  surface (installer, CLI, GUI, docs-as-shipped).  Harness bugs are fixed
  directly in `tests/integrated/` and never appear here.
- Record the failing journey run directory (`results/run-*-<tag>/`) in the
  symptom cell so raw evidence is traceable.
- Never fix a product bug inside a guest; guests are disposable.  See
  `repair-plans/README.md` for the loop.
