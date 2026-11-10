# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped.  The ledger is empty as of 2026-11-03: F-034 shipped
verified in 0.137.0; F-045 and F-046 shipped verified in 0.138.0
(j20 EE/SS stages + both new restore e2e scenarios green on the
released tree); and F-037 (plan 026's fix, shipped in the 0.137.0
release) was pruned at the owner's direction — the fresh j16 rerun
that would have flipped it to `verified` never ran.  The user-cued
j16 of 2026-11-04 (run-20261104-005453, on the 0.138.0-dev tree)
later supplied that verification: S7a's `iscsi-restore-luns` returned
the recorded non-identity mapped_lun 8→0 grant exactly, and S7b's
map-driven rebuild recreated the pair after the total wipe (see the
run's `s7b-grant-restored.log`); the row stays pruned.  Recover all
rows via `git log`.

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-047 | 2026-11-04 | j22-function-survey | The GUI cannot start on a fresh single-node install: `python/memory_page.py` and `python/alignment_page.py` `import cairo` at module level, but the gui prerequisite set never installs or checks a python cairo binding — on the run's clean Debian guest `import cairo` fails (ModuleNotFoundError) before a window exists (run-20261104-155519-j22-function-survey, survey-gui-probe-1.log; the probe environment had to apt-install python3-cairo itself). | installer/prereq gui set (bin/check-prerequisites + install remediation) | open | — |
| F-048 | 2026-11-10 | j23-two-node-release-upgrade | The archive prompt on a two-node upgrade is unreachable under piped stdin: establishing the per-host SSH control master (`open_ssh_master`: `ssh -o ControlMaster=auto -o ControlPersist … true`) drains the invoking shell's stdin, so every unread answer line is gone before the "Archive the changes…?" ask_yn reads EOF and declines by default — the upgrade aborts cleanly and never reaches salvage/deploy (run-20261110-001536-j23-two-node-release-upgrade, guest-upgrade2.log: both hosts scanned, rsync-pulled diffs rendered, then "Aborted. Nothing was changed."; a controlled probe on the retained lab showed the master establishment eating 6/6 stdin lines). Terminal use is unaffected. | bin/upgrade-zfsutilities (open_ssh_master) | verified | — (fixed in place: `</dev/null` on the establishment; run-20261110-003751-j23 re-staged the fixed tree from the dev tarball and its pass 2 approved the archive prompt, salvaged on both hosts, and completed green) |
| F-049 | 2026-11-10 | j24-two-node-uninstall-reinstall | The interactive uninstall menu can never be answered, in a terminal or under piped stdin alike: the 1/2/c `read` at the top of `present_interactive_dialog` was split across two quoted arguments (`read -rp "Choose 1 (software only) or 2 (clean up everything)," \` + `" or c to cancel [1/2/c]: " choice`), so bash parsed the second string as a second variable NAME and aborted with `not a valid identifier` (rc 1) before any choice was read (run-20261110-020627-j24-two-node-uninstall-reinstall, guest-dryrun-storage.log line 32). Every `--yes` path skips the menu, which is why j02 and the unit suites never saw it. | bin/uninstall-zfsutilities (present_interactive_dialog) | verified | — (fixed in place: the prompt is built in one `menu_prompt` string ahead of the read; test-uninstall-zfsutilities green, and run-20261110-023946-j24 re-staged the fixed tree and walked the interactive menu green on BOTH hosts — the dry-run stages assert the full menu/peer/confirm walk) |

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
