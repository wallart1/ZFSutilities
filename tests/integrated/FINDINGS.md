# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped.  Pruned at the 0.140.0 release (2026-11-10): F-048 and
F-049 — both fixed in the dev tree, verified by their journeys'
green re-runs on the fixed trees, and shipped in 0.140.0.  Earlier
closures stay recoverable via `git log` (F-034 in 0.137.0; F-045
and F-046 in 0.138.0, along with plan 026's F-037 verification —
the user-cued j15/j16 reruns of 2026-11-04).  One row remains:
F-047, open.

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-047 | 2026-11-04 | j22-function-survey | The GUI cannot start on a fresh single-node install: `python/memory_page.py` and `python/alignment_page.py` `import cairo` at module level, but the gui prerequisite set never installs or checks a python cairo binding — on the run's clean Debian guest `import cairo` fails (ModuleNotFoundError) before a window exists (run-20261104-155519-j22-function-survey, survey-gui-probe-1.log; the probe environment had to apt-install python3-cairo itself). | installer/prereq gui set (bin/check-prerequisites + install remediation) | open | — |

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
