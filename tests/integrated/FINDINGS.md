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
passed), and shipped in 0.141.0.  Earlier closures stay
recoverable via `git log` (F-048 and F-049 in 0.140.0; F-034 in
0.137.0; F-045 and F-046 in 0.138.0, along with plan 026's F-037
verification — the user-cued j15/j16 reruns of 2026-11-04).  No
rows remain; the table below is empty until the next journey
files a finding.

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-051 | 2026-11-17 | j22-function-survey (mint leg) | Pools → Export froze the window for good: with a live iSCSI LUN session holding the pool's zvol, `zpool export` blocks uninterruptibly (D-state, taskq_wait — observed live on the guest) and the handler ran it synchronously on the UI thread with no bound; the post-failure blocker-recovery flow never got its turn (run-20261117-150953; reproduced run-20261117-153840 and run-20261117-160333) | GUI export path: `pool_actions.on_pools_export` → `zfs_repository.export_pool_detailed` (unbounded `_run`) | verified | in-cycle per approved session plan: export runs in a worker thread with a hard UI-side deadline (`EXPORT_STALL_WARN_S`, default 120 s, env-overridable); on stall a holder-naming WARN tells the user to release LUN sessions and retry — a subprocess timeout alone cannot reclaim a D-state child. Verified by the archive replay run-20261117-162554: the Export op completed at the 120 s bound with the window alive and the survey verdict green (every selected item passed) |

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
