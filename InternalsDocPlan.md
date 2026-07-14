# Plan: Enhance Commands and Modules Reference Internals — Option C (Phased)

## Objective

Make the **Commands and Modules Reference** a thorough internals reference for **both the bash backend and the Python GTK GUI**. Each existing bash entry and each major Python module will describe its internal flow, list the modules it calls, and cross-reference the shared data structures it consumes or produces.

## Chosen Scope: Option C — Bash + Python modules

This plan covers:

1. The existing 61 root-level commands in `commands.md`.
2. The existing 22 sourceable bash modules in `modules.md`.
3. The existing 23 two-node / iSCSI / VM lifecycle scripts in `two-node.md`.
4. A new Python modules reference page for the major `07 GTK + Python/` modules.

Work is broken into phases so each piece can be reviewed, tested, and merged independently.

## Standard Entry Template

Every bash and Python entry will use this section order where applicable:

1. One-line purpose.
2. Usage example (bash) or import/use pattern (Python).
3. **Arguments** / **Parameters** table.
4. **Globals / Attributes** table with cross-references to `global-variables.md` (bash) or `data-structures.md` (Python).
5. **Internal flow / algorithm** — decisions and sequencing.
6. **Called modules** table — module → purpose in this entry.
7. **Data structures consumed / produced** table — structure → `data-structures.md` anchor.
8. **Return codes / Exceptions / Side effects** table if meaningful.
9. **See also** links to related entries.

## Phase 1 — Dependency and data-structure mapping

**Goal:** Produce a single source-of-truth scratch document listing, for every script/module:

- `source $mydir/<module>` occurrences.
- Direct function calls into other modules (`buildfsarray`, `send-receive`, `retain`, `delsnap`, etc.).
- Reads/writes of shared structures (`$fsarray`, `$zfspoolarray`, `ISCSI_TEARDOWN`, JSON config sections, manifests, session log index, history, lock files).
- Key internal variables set/used.
- For Python: imports, `AppContext` consumers, `ZfsRepository` callers, config savers/loaders, dataclasses produced.

**Activities:**

- Read every script in the three bash reference pages.
- Read the major Python modules in `07 GTK + Python/`.
- Update `developer-guide/data-structures.md` and `global-variables.md` anchors if new shared structures are discovered.

**Deliverable:** Internal mapping document (not committed; can live in `/home/dan/.kimi/plans/` or a temporary file in repo).

**Exit criteria:** Mapping is complete enough to begin writing reference updates.

## Phase 2 — Bash commands reference (`commands.md`)

**Goal:** Add internals, called modules, and data-structure cross-references to all 61 entries.

**Activities:**

- Add a **Called modules** table to each entry.
- Add a **Data structures consumed / produced** table to each entry.
- Add or expand **Internal flow / algorithm** descriptions for orchestrators and complex commands:
  - `zfsdailybackup`, `zfscleanup`, `zfsrestore`, `zfsfullcopy`, `zfssendoffsite`, `zfsoffsiteretain`
  - `zfsdelfs`, `zfsdelallsnaps`, `zfsdelholds`, `zfssend`, `zfsresume`
  - `zfscleanupbadoffsiteholds`, `zfsholds`, `zfsshowholds`, `zfsshowbigstuff`
- Ensure every table links to the relevant `data-structures.md` / `global-variables.md` anchors.
- Add return-code tables where missing.

**Deliverable:** Updated `06 Docs/docs/commands-and-modules/commands.md`.

**Exit criteria:** `test_docs_integrity` passes for this file; MkDocs build produces no link warnings.

## Phase 3 — Bash modules reference (`modules.md`)

**Goal:** Add internals, called modules, and data-structure cross-references to all 22 module entries.

**Activities:**

- Add **Called modules** and **Data structures** tables to simpler modules that lack them.
- Expand **Internal flow / algorithm** descriptions for the complex modules:
  - `zfsretain` — three-phase pruning in detail.
  - `zfs-send-receive` — full vs incremental, common-snapshot selection, resumable receives, `ISCSI_TEARDOWN` rebuild, hold management.
  - `zfssnapbuild` — snapshot name construction and bucket assignment.
  - `zfslockmanager` — lock file format, conflict detection, stale cleanup.
  - `zfsoverrides` — parse semantics and precedence.
  - `zfscheckagainst` — already detailed; verify it links to the new `zfscommsnap`/`zfsconfig` references.

**Deliverable:** Updated `06 Docs/docs/commands-and-modules/modules.md`.

**Exit criteria:** `test_docs_integrity` passes; MkDocs build produces no link warnings.

## Phase 4 — Two-node reference (`two-node.md`)

**Goal:** Add internals, called modules, and data-structure cross-references to all 23 two-node entries.

**Activities:**

- Add **Called modules** and **Data structures consumed / produced** tables to each entry.
- Describe how `node-lib.sh` is sourced and how node-config globals gate behavior.
- Document cross-module call chains:
  - `new-vm-disk` → `safe-iscsi-save`, manifest updates
  - `remove-vm-disk` / `zfsdelfs` → iSCSI teardown → `zfs-send-receive` rebuild
  - `unlock-zfs-keys` / `restart-iscsi-services` → `iscsi-add-encrypted-luns`
  - `retire-vm` / `unretire-vm` / `promote-vm-clone` / `zfsclone-vm` clone lifecycle
- Cross-reference `ISCSI_TEARDOWN`, `POOL_TARGET`, expected-backstores manifest, encrypted-LUNs config.

**Deliverable:** Updated `06 Docs/docs/commands-and-modules/two-node.md`.

**Exit criteria:** `test_docs_integrity` passes; MkDocs build produces no link warnings.

## Phase 5 — New Python modules reference page

**Goal:** Create `06 Docs/docs/commands-and-modules/python-modules.md` covering the major Python modules in `07 GTK + Python/`.

**Groupings (one section per group):**

- **Config and data** — `config_core.py`, `feature_config.py`, `backup_config.py`, `config_migrations.py`
- **ZFS repository and info** — `zfs_repository.py`, `zfsinfo.py`, `diagnose_zfs_repository.py`
- **Command builders and runners** — `command_builders.py`, `backup_runner.py`, `offsite_runner.py`, `restore_runner.py`, `profile_runner.py`, `runner_factory.py`, `backup_history.py`
- **GUI pages and actions** — `app_context.py`, `action_dispatch.py`, `backup_page.py`, `offsite_page.py`, `restore_page.py`, `retention_page.py`, `checkagainst_page.py`, `datasets_page.py`, `dashboard_page.py`, `pools_page.py`, `schedule_page.py`, `logs_page.py`, `scrub_page.py`
- **Managers and helpers** — `profile_manager.py`, `profile_dialogs.py`, `cron_manager.py`, `scrub_manager.py`, `pool_watch.py`, `dataset_actions.py`, `pool_actions.py`, `retention_actions.py`, `snapshot_manager.py`, `gui_helpers.py`, `log_index.py`, `logging_config.py`
- **Entry points** — `main.py`, `zfsutilities_gui.py`, `docs_viewer.py`, `legacy_retention.py`

**Per-group content:**

- Purpose of each module.
- Key classes/functions.
- Called modules / imported helpers.
- Data structures consumed/produced (cross-reference existing `data-structures.md` Python dataclass sections).

**Deliverables:**

- New `06 Docs/docs/commands-and-modules/python-modules.md`.
- Update `06 Docs/docs/commands-and-modules/index.md` to link the new page.
- Update `06 Docs/mkdocs.yml` nav to include the new page.

**Exit criteria:** `test_docs_integrity` passes; MkDocs build produces no link warnings.

## Phase 6 — Anchor and cross-link cleanup

**Goal:** Ensure every new cross-reference resolves.

**Activities:**

- Add any missing anchors to `data-structures.md` and `global-variables.md`.
- Verify all relative paths are correct (`../developer-guide/...`).
- Run `tests/run-python-tests test_docs_integrity`.
- Run `mkdocs build` from `06 Docs/`.

**Deliverable:** Clean build and passing tests.

## Phase 7 — Final review and summary

**Goal:** Validate consistency across all updated pages.

**Activities:**

- Re-read the updated reference pages for consistent terminology and formatting.
- Summarize modified/new files and notable content additions.
- Confirm no version bump and no git commit was performed.

**Deliverable:** Summary message to user.

## Deliverables (all phases)

- `06 Docs/docs/commands-and-modules/commands.md` (updated)
- `06 Docs/docs/commands-and-modules/modules.md` (updated)
- `06 Docs/docs/commands-and-modules/two-node.md` (updated)
- `06 Docs/docs/commands-and-modules/python-modules.md` (new)
- `06 Docs/docs/commands-and-modules/index.md` (updated)
- `06 Docs/mkdocs.yml` (updated nav)
- `06 Docs/docs/developer-guide/data-structures.md` / `global-variables.md` (anchor additions only if needed)
- Passing `test_docs_integrity` (and MkDocs build)

## Notes / Constraints

- No automatic version bump and no automatic git commit.
- No changes to production nodes (`stewie`, etc.); this is documentation work only.
- Each phase can be paused and reviewed before starting the next.
