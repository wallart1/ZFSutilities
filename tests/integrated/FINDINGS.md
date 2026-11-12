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
the user-cued j15/j16 reruns of 2026-11-04).  Two rows remain:
F-047 and F-050, both fixed in the dev tree (2026-11-11, approved
session plan for the pub-tree j22 run) and verified by the green
archive replay of the same 107-item draw on the fixed tree
(run-20261111-203336-j22-function-survey — every selected item
passed).

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-047 | 2026-11-04 | j22-function-survey | The GUI cannot start on a fresh single-node install: `python/memory_page.py` and `python/alignment_page.py` `import cairo` at module level, but the gui prerequisite set never installs or checks a python cairo binding — on the run's clean Debian guest `import cairo` fails (ModuleNotFoundError) before a window exists (run-20261104-155519-j22-function-survey, survey-gui-probe-1.log; the probe environment had to apt-install python3-cairo itself). The 2026-11-11 pub run added the second layer: with a bare `python3-cairo` the import succeeds but PyGObject cannot marshal `cairo.Context` — every fallback-chart draw dies with `Couldn't find foreign struct converter for 'cairo.Context'` (run-20261111-195614-j22-function-survey, survey-gui-probe-1.log). | installer/prereq gui set (bin/check-prerequisites + install remediation) | verified | session plan 2026-11-11: gui set gains `check_python_module cairo` + `check_apt_pkg python3-gi-cairo` (installer-lib description rows added) |
| F-050 | 2026-11-11 | j22-function-survey | A GUI dataset action crashes when zfs prints raw non-UTF-8 bytes in command output: fed an invalid snapshot name (`survey-garbage-µ`), `zfs snapshot` fails with `invalid character '\302' in name` — the message embeds the offending byte, and the product's subprocess calls decoded captured output with strict UTF-8 (`text=True`), so `_snapshot_one` died with UnicodeDecodeError instead of refusing gracefully (run-20261111-195614-j22-function-survey, survey-gui-probe-1.log traceback; reproduced on the kept lab guest). Wild dataset/snapshot names make this reachable with real data, through every text-mode subprocess site. | python subprocess decode layer (`ZfsRepository._run` and every text-mode `subprocess` call) | verified | session plan 2026-11-11: `errors="replace"` on all text-mode subprocess sites |

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
