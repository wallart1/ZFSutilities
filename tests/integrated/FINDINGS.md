# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped.  Pruned at the 0.144.0 release (2026-11-25): F-053 and F-054 —
F-053, the two-node `compute_host` resolution gap (`zfsdailybackup` and
the `rsync-dailybackup` template defined the storage/compute host pair
only in single-node mode, so a stock run degraded to a failed-pull WARN
and a strict-mode site copy died "unbound variable"), and F-054, the
prune chain's strict-caller fragility (the shipped rsync template turns
strict mode on when sourced, and the prune leg's unguarded reads
aborted "unbound variable" before deleting anything).  Both were found
by the j22 full-function legs, fixed in-session under the approved
2026-11-24 plan, and verified by the green runs
run-20261124-010402-j22-function-survey and
run-20261124-052832-j22-function-survey (the site pair ran snapshot,
pulls, send, and prune end to end); the 0.144.0 wrap-up closed the
reads the first fix had missed.  Shipped in 0.144.0.  Pruned at the
0.143.0 release (2026-11-23): F-052 — the zfsresume silent-verdict
defect (`zfs send -nP -t` for a valid token exits 0 with the decoded
contents on zfs 2.2.2, but both report branches sat inside the failure
path, and an unrecognized probe failure printed "seems valid").  Fixed
under the approved 2026-11-23 survey plan: decoded contents are the
validity signal, and unexpected failures WARN with wording reused from
zfs-migrate-send; verified by the green replay
run-20261123-202938-j22-function-survey (the real-path item passed with
the live "seems valid" verdict) and shipped in 0.143.0.  Earlier
closures stay recoverable via `git log` (F-051 in 0.142.0; F-047 and
F-050 in 0.141.0; F-048 and F-049 in 0.140.0; F-034 in 0.137.0; F-045
and F-046 in 0.138.0, along with plan 026's F-037 verification — the
user-cued j15/j16 reruns of 2026-11-04).

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|

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
