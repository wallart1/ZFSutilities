# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (Performance page, narrow-window horizontal page scroll — discovered
  2026-10-21 while probing the page's table/ladder geometry under
  Xvfb): below roughly a 600px window the whole page grows its own
  horizontal scrollbar, because the section-header subtitle labels and
  the value-grid captions set no ellipsize and a Gtk.Label's minimum
  width is its full natural text width (the widest, the Alignment view's
  "device → pool → dataset → VM · advisory only" subtitle and the
  "Memory-tier Observations (since boot)" heading, pin the page minimum
  near 600px). Every table already scrolls on its own, so the page-level
  scrollbar only ever carries label text. Fix direction when addressed:
  ellipsize the section-header subtitle (and optionally the page title
  row) so the page minimum follows the tables' minimums instead.

- (test-suite display hygiene, xdist worker leader windows — discovered
  2026-10-21 while investigating an operator-visible flash during full
  runs): the full python batch runs under `pytest -n N`, and each xdist
  worker process is spawned by execnet as `python -c <bootstrap>`. The
  one real-GTK suite (`tests/python/test_datasets_tree.py`, no mock_gtk)
  makes every worker that runs it open the ambient X display, and GDK
  then creates its per-connection client-leader window — an unmapped
  10x10 window named/classed `-c` (GTK takes the name from the
  `python -c` argv). Verified invisible (Map State IsUnMapped for the
  window's whole life) and destroyed at worker exit, so it is NOT the
  flash class of leak the realized check had — but it is the same
  structural class: test processes connecting to the operator's display,
  and the mechanism a future mapped-widget test would flash through.
  Fence direction (when addressed): give the python batch (or at least
  the real-GTK suite) a private display the way the realized check does,
  so no test process ever opens the ambient display. Investigation
  evidence: three instrumented full runs (managed-window watcher via
  wmctrl + root-children watcher via xwininfo with xprop class/map-state
  capture) showed zero mapped windows from the suites; only these
  unmapped leaders appeared.

- (iSCSI recovery, safe-iscsi-save boot config — discovered 2026-10-21
  during bare-metal stewie recovery):
  `safe-iscsi-save`'s `generate_boot_config` strips encrypted
  storage_objects and their LUN entries from each TPG's `luns` array
  when writing `saveconfig-boot.json`, but does NOT strip the
  corresponding `MappedLUN` entries from each TPG's `acls` → `node_acl`
  → `mapped_luns` tree. Result: at the next boot,
  `rtslib-fb-targetctl.service`'s `targetctl restore` reads
  `saveconfig-boot.json`, sees ACL MappedLUNs referencing LUN indexes
  that no longer have corresponding TPG LUNs (because they were
  stripped), and logs warnings like:
      Could not find matching TPG LUN 1 for MappedLUN 1, skipped
      Could not find matching TPG LUN 8 for MappedLUN 8, skipped
  The warnings are non-fatal (the non-encrypted LUNs restore fine) but
  indicate an internally inconsistent boot config. The fix is to
  strip the matching `mapped_luns` entries alongside the `luns`
  entries in the same Python filter inside `generate_boot_config` in
  bin/safe-iscsi-save (around the loop that mutates
  `tpg["luns"]`). File: bin/safe-iscsi-save, function
  `generate_boot_config`, the `for target in config.get("targets", [])`
  loop.

- (encrypted-LUN recovery workflow, documentation gap — discovered
  2026-10-21 during bare-metal stewie recovery):
  The encrypted-LUN boot path assumes ZFS encryption keys are
  available at boot time, either via `keylocation=file://...`
  pointing at a non-encrypted filesystem that's mounted before
  `rtslib-fb-targetctl.service` starts, or via a systemd unit
  that calls `zfs load-key` for the encrypted iSCSI zvols before
  the target service starts. The operator's setup uses a
  LUKS-encrypted USB key drive that is not plugged in at boot
  time — a perfectly reasonable security choice — and loads keys
  manually after the first post-boot login. This breaks the
  boot-time assumption, and the project has no documented
  "manual recovery after key load" workflow for the encrypted
  iSCSI LUN case. The required workflow (reverse-engineered
  during this recovery session) is:
    1. Plug in USB key drive, unlock LUKS, mount
    2. `zfs load-key` for each encrypted iSCSI zvol
    3. `targetcli /backstores/block create <name> /dev/zvol/<pool>/<path>`
       for each encrypted backstore (they were stripped from
       saveconfig-boot.json and are not restored at boot)
    4. `targetcli /iscsi/<iqn>/tpg1/luns create /backstores/block/<name> <lun_idx>`
       for each encrypted backstore, using the LUN index recorded
       in saveconfig.json (NOT auto-assigned — auto-assignment can
       collide or pick the wrong index when orphan targets exist;
       see the IQN-prefix-mismatch item below)
    5. `safe-iscsi-save` to persist
    6. `rescan-storage` (or `repair-iscsi-luns --force-relogin`)
       to surface the LUNs on the compute host
    7. `qm start <vmid>` for each affected VM
  This workflow should be documented in docs/docs/user-guide/proxmox-integration.md
  (or a new "encrypted LUN recovery" page), and ideally wrapped
  in a single script — `iscsi-recover-encrypted-luns` or
  similar — that the operator can run after manually loading keys,
  which performs steps 3–6 idempotently and verifies the result
  against the expected LUN indexes in saveconfig.json. The
  existing `iscsi-add-encrypted-luns` script is *almost* this,
  but its `lookup_lun_number` scans all targets in saveconfig.json
  and returns the first matching backstore name regardless of
  which target it's on — so when orphan targets exist (see the
  IQN-prefix-mismatch item), it can return the wrong LUN index.
  Out-of-scope for the recovery session that discovered this;
  recorded for later addressing.

- (iSCSI boot path, boot-config.conf drop-in — discovered 2026-10-21
  during bare-metal stewie recovery):
  The comment block in
  /etc/systemd/system/rtslib-fb-targetctl.service.d/boot-config.conf
  (installed by bin/install-two-node from the boot-config.conf template
  in the repo) says:
      After the service starts with the boot config, ExecStartPost
      (iscsi-add-encrypted-luns) adds the encrypted LUNs back if
      their keys happen to be loaded.
  But the actual drop-in file contains only the `ExecStart=` /
  `ExecStart=` override pair — there is NO `ExecStartPost=` line in
  the installed drop-in. So `iscsi-add-encrypted-luns` does NOT run
  automatically after `rtslib-fb-targetctl.service` starts. On any
  stewie reboot where ZFS keys are loaded (e.g. via a separate
  systemd unit or by operator script) the encrypted LUNs stay
  missing until the operator manually runs `iscsi-add-encrypted-luns`
  or `restart-iscsi-services`. Either (a) drop the misleading
  comment from the template so the missing ExecStartPost is not
  implied, or (b) add the ExecStartPost line to the installed
  drop-in (or as a separate drop-in file shipped by
  install-two-node). Discovered because the operator's encrypted
  LUNs (vm-101-disk-1, vm-202-disk-5) silently vanished from the
  running LIO target after stewie rebooted even though the keys
  were loaded manually before any VM start was attempted.

- (iSCSI configuration drift, IQN prefix mismatch — discovered
  2026-10-21 during bare-metal stewie recovery):
  `install-two-node` derives the default `IQN_PREFIX` from
  `date +%Y-%m` at install time (bin/install-two-node:168:
  `default_iqn="iqn.$(date +%Y-%m).local.${storage_host}"`). If a
  storage host is reinstalled in a different month than the original
  install, the new node.conf has a different `IQN_PREFIX` than the
  IQN prefix of the existing LIO targets carried over from
  `/etc/rtslib-fb-target/saveconfig.json` (if that file survived the
  reinstall) or from a bare-metal restore. Result: the active LIO
  target tree ends up with targets under BOTH the old and the new
  IQN prefixes for the same pool, and:
    - `setup-iscsi-targets` creates fresh targets under the new
      prefix (per node.conf), leaving the old-prefix targets as
      orphans.
    - `repair-iscsi-luns` maps LUNs to whichever target
      `pool_to_target` returns — which always uses the new
      `iqn_prefix` from node.conf, so it adds LUN mappings to the
      new-prefix target while the old-prefix target's LUNs (which
      Proxmox may still be logging in to) are not updated.
    - `iscsi-add-encrypted-luns`'s `lookup_lun_number` scans ALL
      targets in saveconfig.json and returns the first matching
      backstore name, regardless of which target it's on. With two
      targets holding the same backstore at different LUN indexes,
      it can return the WRONG LUN index, then `targetcli create
      ... $idx` either fails silently (LUN collision on the
      correct target) or maps the encrypted disk to the wrong LUN
      index. Both outcomes break Proxmox VM disk mappings.
  Discovered because the storage host had both
  `iqn.2026-02.local.stewie:threeamigos` (Proxmox's configured
  target) and `iqn.2026-10.local.stewie:threeamigos` (orphan from
  an earlier install) live in LIO simultaneously, and
  `repair-iscsi-luns --force-relogin` mapped the unencrypted
  backstores to the orphan `2026-10` target (visible in its log
  output) while Proxmox continued to log in to the `2026-02`
  target. Proposed mitigations, either or both:
    (a) `install-two-node` should warn if `IQN_PREFIX` differs from
        the IQN prefix of any target in an existing
        `/etc/rtslib-fb-target/saveconfig.json`, and require
        explicit confirmation before installing the new prefix.
    (b) `setup-iscsi-targets` should detect existing targets whose
        short names match `pool_target[*]` but whose IQN prefix
        differs from `iqn_prefix`, and either refuse to create the
        duplicate or delete the orphan after explicit confirmation.
    (c) `pool_to_target` in lib/node-lib.sh could verify the
        constructed IQN actually exists in LIO (via `targetcli
        /iscsi ls`) before returning it, and warn loudly if it
        doesn't — this catches the inverse case (node.conf prefix
        doesn't match any live target).
  Out-of-scope for the recovery session that discovered this;
  recorded for later addressing.

- (dev-machine environment, migration sweep hazard — found 2026-10-19 during
  the archived pool-activity campaign): `run_migration()` re-executes the
  FHS legacy-file sweep out of the user's real HOME whenever
  `ZFSUTILITIES_STATE_DIR` points at a fresh directory (the
  `.migration_complete` sentinel is state-dir-relative), so any
  redirected-state scratch run MOVES real HOME files
  (~/.config/zfsutilities.json, ~/.config/profiles) into the scratch dir —
  deletion if it is a TemporaryDirectory. Live incident on 2026-10-19: both
  legacy files lost; two dangling symlinks remain in ~/.config (left for the
  user); live /var/lib tree unaffected. Fix direction: gate the legacy sweep
  to the real state dir or honor the disable flag before any move. Scratch
  runs must set ZFSUTILITIES_DISABLE_MIGRATION in the meantime.

- (test-suite blind spot, module-dependency check — found 2026-10-20):
  `tests/test-module-dependencies` derives the repo root so that it scans
  only repo-root-level scripts; everything under `bin/` (including the
  archived `poolactivityctl`) is invisible to it, so the suite passes
  vacuously and guards nothing about the scripts it was presumably meant to
  cover. Real guards today: shellcheck + the per-script bash suites.

- (toolchain deprecation, docs build): `mkdocs build -f docs/mkdocs.yml`
  prints a mkdocs-material WARNING — "MkDocs 2.0 is incompatible with
  Material for MkDocs" — on every build (exit 0, site still builds cleanly).
  Action is a toolchain decision (pin mkdocs <2 vs migrate to Zensical),
  already analyzed in SESSION_NOTES.md's Zensical thread; recorded here so
  it can be prompted for a decision. Not resolved (code freeze).
  Zensical is under development. We are waiting for a 1.x.x release.
  (Rechecked 2026-10-08: PyPI shows 0.0.69; still no 1.x.
  Rechecked 2026-10-10: unchanged, 0.0.69.
  Rechecked 2026-10-11: unchanged, 0.0.69.
  Reconfirmed 2026-10-11 (user): keep waiting for 1.x.
  Rechecked 2026-10-12: 0.0.70; still no 1.x.)
  (Rechecked 2026-10-13: unchanged, 0.0.70.)
  (Rechecked 2026-10-16: 0.0.71; still no 1.x.)

- (test-suite poisoning hazard, matplotlib backend probe cache — found
  2026-10-21 while adding chart-font tests): any test that triggers
  `charting.matplotlib_backend()`'s real probe while no `mock_gtk()` is
  active (e.g. calling a chart renderer's `update()` outside the
  `matplotlib_backend` patch, after a `mock_gtk(fresh=True)` context has
  exited) lets the probe import the REAL gtk3agg backend on a
  GTK-equipped host and caches it in the module binding. Every later
  suite then constructs real `FigureCanvasGTK3Agg` objects under mocked
  gi, which dies with a cryptic PyGObject
  `SystemError: gi.FunctionInfo(set_events...) returned a result with an
  exception set` (chained from a TypeError deep in the mixed state) —
  one such call poisoned 73 tests in a following suite this cycle. The
  charting tests' `_built()` pattern (patcher.start() + addCleanup) is
  the safe shape; a structural fence would be a mock-aware guard in the
  probe itself (e.g. refusing to cache a real backend when
  `charting.Gtk` is a mock), not attempted this cycle.

- (future objective, migration/create fidelity — narrowed 2026-10-03):
  No creation path (Create Pool wizard or Migrate Pool) can *plan*
  infrastructure vdevs (special / log / cache / spare): the review page
  warns when the source pool has them, a post-cutover INFO reminder says to
  re-add them with Add Infrastructure Vdev, and as of 2026-10-03 the
  holding-mode rebuild picker preselects only true data members (former
  infra-vdev disks are listed unchecked, labeled with their class, so they
  can no longer be silently absorbed into data vdevs). Remaining gap is the
  planning UI itself, deliberately deferred as a future objective (user
  decision 2026-10-03): per-class disk pickers in the wizards plus
  `zpool add <class>` steps after the create step (or an extended
  `zpool create` vdev spec). Originally discovered 2026-10-03 during the
  pool-level migration audit.
  This item is in abayance as a future objective.
  (Reconfirmed 2026-10-11 (user): keep deferred.)
