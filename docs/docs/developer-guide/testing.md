# Testing

ZFS Utilities has a two-layer test framework:

- **Bash suites** in `tests/` — test bash scripts with mock `zfs` / `zpool` overrides.
- **Python suites** in `tests/python/` — test Python modules (`backup_config.py`,
  `command_builders.py`, GUI helpers, etc.) with `unittest` and `MagicMock`.

Both layers are run automatically by `tests/run-tests`.

---

## Running Tests

```bash
# All suites (bash + Python)
tests/run-tests

# Single bash suite
tests/run-tests test-zfsretain

# Single Python suite
tests/run-tests test_backup_config

# Quiet — summary only
tests/run-tests -q

# Failures only
tests/run-tests --failures-only

# Include the *-soak timing suites (see "Soak suites" below)
tests/run-tests --with-soak

# List live per-suite test counts (--count is an alias for --list). Bash
# suites run quietly once so the counts are executed totals, not estimates;
# Python suites are counted by pytest collection, which runs no tests.
tests/run-tests --list

# Bash suites: limit parallelism (default is one below nproc, min 2)
tests/run-tests --jobs 4

# Bash suites: serial debug mode (same results, no parallelism)
tests/run-tests --jobs 1

# Show the 10 slowest bash suites at the end (N optional, default 10)
tests/run-tests --slowest 10

# Persist the full console stream to a file (overwrites any previous file)
tests/run-tests --log /tmp/zfs-run.log
```

The `--log` option captures the harness's own console output, including
failing-suite dumps and the overall summary; it pairs with the
redirect-and-read pattern in `tests/AGENTS.md` so a truncated interactive
console never forces a full-suite rerun.

Test counts are intentionally not maintained in documentation — use
`--list` whenever a current number is needed.

The `tests/run-tests` harness detects whether a name starts with `test_` (Python) or
`test-` (bash) and routes it to the correct runner.

When an ambient X display exists, the Python batch fences itself onto a
private Xvfb (`tests/python/conftest.py` starts one for the whole run before
the pytest-xdist workers spawn, so every worker — including the one real-GTK
suite that would otherwise open the operator's display and flash its
client-leader window — inherits it; display numbers 89..80 stay clear of the
realized check's own 99..90). Headless runs (no `DISPLAY`) and environments
without `/usr/bin/Xvfb` keep the previous behavior; the fence names itself
via the `ZFSUTILITIES_TEST_DISPLAY=private` marker.

### Parallel bash runs and per-suite timing

Bash suites run in parallel by default (`--jobs N`; default `nproc - 1`, min 2,
leaving one core for the system). Suites are self-contained — mocked `zfs`/`zpool`,
own `mktemp` state, per-suite lock dirs — so parallel runs are safe; `--jobs 1` is
the serial debug mode and produces identical pass/fail results.

Per-suite wall time is always recorded. At the end of every run:

- `--slowest N` prints the N slowest bash suites with their durations.
- A soft budget warns (never fails) about non-soak suites taking more than 5
  seconds, listed in an `Over budget (> 5s)` section. Keep suites under the
  budget using the env-overridable timing knobs (see "Soak suites" below), not
  by deleting coverage.

### Soak suites

Bash suites whose name ends in `-soak` contain randomized, time-dependent
timing-conflict coverage (for example `test-zfslockmanager-soak`). They run at
realistic timings — seconds, not milliseconds — so they are excluded from default
runs: `tests/run-tests` reports them as `SKIPPED (soak suite)` and they do not
affect the exit code. Run them on demand or nightly, either by naming the suite
explicitly (`tests/run-tests test-zfslockmanager-soak`) or with `--with-soak`.

New tests must not use real `sleep` calls to probe timing behavior — use the
env-overridable timing knobs the product exposes (for the lock manager see
[lock-manager.md](lock-manager.md#timing-knobs-environment-overrides)) and keep
genuinely time-dependent conflict scenarios in a `-soak` suite.

### Environment preflight and skips

A red suite must always mean a real problem, so `tests/run-tests` detects the
environment up front — GTK (`gi`), `pv`, `zfs`/`zpool`, root, and the
integration test pools — and compares it against the requirements declared in
`tests/requirements.manifest` (one `capability path` line per suite).

Suites whose requirements are missing are reported as
`SKIPPED (missing: <caps>)` with the reason stated, are not executed, and never
affect the exit code; when skips are the only non-passes the run still exits 0.
The first line of a normal run summarizes the detection:

```text
Environment: gi=present pv=present zfs=present root=MISSING test-pools=MISSING
```

Python suites that use GTK-dependent modules without `mock_gtk()` declare the
dependency in `tests/requirements.manifest` and guard it, so direct
`pytest tests/python/...` invocations skip identically:

- Module-level imports of GTK-dependent modules go through
  `test_support.import_or_skip_gi("<module>")` (so collection survives
  without gi), paired with `pytestmark = requires_gi` (so a mock-bound
  module already in the `sys.modules` cache cannot let tests run against
  mocks).
- GTK used only inside test bodies — `@patch` decorators on GUI modules, or
  runtime GUI imports outside a `mock_gtk()` context — is covered by
  `pytestmark = requires_gi` alone.

A consistency check in `test_gui_infrastructure.py` enforces both rules and
that the manifest matches the guarded suites. Skipped Python tests are
counted separately in the overall summary (`Python tests skipped`).

The upshot: in a bare container (no GTK/ZFS/pv) the harness runs every
environment-independent suite green and lists every skipped suite with its
reason — nothing red that is not a real regression. Unexpected skips on a
development machine are environment problems to report, never to work around.

### CI and dev container

One canonical test environment is defined in code and used by both CI and the
dev container. `share/dev/install-test-deps.sh` installs every system and
Python dependency the suite needs (Debian/Ubuntu); it is the single source of
truth, consumed by both of the following. `requirements-dev.txt` includes
matplotlib so the realized Performance-page check exercises the production
matplotlib renderer on CI, not just the Cairo fallback a bare runner would
select.

`.devcontainer/` builds an Ubuntu 24.04 image with all dependencies. To run
the suite in it from a repo checkout:

```bash
docker build -f .devcontainer/Dockerfile -t zfsutilities-dev .
docker run --rm --init -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/workspace" -w /workspace zfsutilities-dev xvfb-run -a bash tests/run-tests
```

Rebuild the image whenever `share/dev/install-test-deps.sh` or
`requirements-dev.txt` changes — dependencies are baked in at build time, so a
stale image keeps failing even after the fix lands in the repo (an image built
before the `python3-gi-cairo` addition fails every GUI-importing suite with
`ModuleNotFoundError`, the same failure CI hit on v0.112.0).

The GUI suites instantiate real GTK widgets, so the container (which has no
display) runs the suite under `xvfb-run`. `--init` gives the container a real
init process (`xvfb-run` waits on a signal from `Xvfb` and misbehaves as PID
1), and invoking the suite through `bash` keeps the command identical on any
volume/filesystem. `PYTHONDONTWRITEBYTECODE=1` keeps the run from leaving
root-owned `__pycache__` directories throughout the user-owned checkout.
Inside the container the run is
green; the only skips are the soak suite (excluded from default runs), the
integration suite (no test pools in a container), and the payload e2e
suites' pool-touching scenarios (see below). A few individual tests that
inject failures through filesystem permissions also skip themselves when the
suite runs as root (the container does), since root ignores mode bits.

The GUI payload e2e suites (`tests/python/test_offsite_e2e.py`,
`tests/python/test_backup_payload_e2e.py`) exercise the real payload
builders and the real BackupRunner against real pools; their scenario
levels and contexts are documented in the integrated-testing guide's
"GUI payload e2e matrix" section. For the read-only layer (dry-run
payloads plus the runner mechanics), run them in the dev container with
the ZFS control device passed through — `share/dev/run-e2e-container`
wraps exactly that (unprivileged `--device /dev/zfs` run; every
dataset-mutating ioctl needs `CAP_SYS_ADMIN`, so mutating scenarios
self-skip and the script verifies the host pool set is unchanged). The
full matrix runs in the ITF guest via the `j11-payload-e2e` journey.

`.github/workflows/tests.yml` runs on every push and pull request: install
dependencies, run the suite under `xvfb-run -a`, then run the
documentation-integrity suite. A scheduled nightly job runs
`tests/run-tests --with-soak`.

---

## Bash Test Suites

| Suite | What it covers |
|-------|----------------|
| `test-archive-vm` | `archive-vm` retire-snapshot selection, two-node target/LUN resolution encoding (separate ssh argv entries, since IQNs contain colons), and invocation (single-node, two-node, and invoked-on-storage with the transfer running locally — no compute bounce); the shared transfer library's copy path (thin `create -V` at 1M, snapshot-device copy with in-flight source hashing and a separate destination read-back verify, `@archive` snapshot, snapdev expose/revert), the encrypted raw path, hash-mismatch and in-flight source-hash-failure aborts with parent-chain rollback, the in-flight hash read pattern (source hashed from the stream, never re-read as a file; the only file-argument hash names the destination), the base64 config-content handoff to the storage-side payload, rate limiting (paced copy via the `pace_stream.py` pacer and `dd conv=sparse`, a single paced destination read-back with the source device read exactly once, raw-pipeline pacer segment, unlimited runs keeping the unpaced dd pipeline, prompt save/forward via `transfer_rate_limit`), re-run idempotency (`@archive`-snapshot skip, interrupted-leftover destroy-and-redo, payload completion probe), the refusal to run unlimited when a rate is set but the pacer cannot be resolved, a static no-`receive -o volblocksize` guard, and Step-4 removal (the `ssh -t` + input-hold + `--skip-rescan` delegation argv, single-rescan behavior, and the outcome-verified failure gates: a declined remote confirm exits 0 yet keeps the Proxmox config, fails the run, and prints no success summary — as does a failed remote or `zfsdelfs` destroy) |
| `test-attach-vm-disk` | `attach-vm-disk` zvol-path parsing and validation; node-aware zvol validation (two-node compute-host SSH round trip, storage-host delegation, single-node local check); single-node attach reaching the config write — the disk line is built and appended to the stub VM config, key auto-detect picking the next free slot |
| `test-bashinit` | `bashinit` helpers: `log_msg` survives a `cd` after relative-path invocation; session-log selection when the log file is writable vs unwritable; input-hold marker emission and uuid reuse for `ask_yn`/`ask_line`; `input_hold_env_prefix` expansion for `ssh -t` delegation |
| `test-check-prerequisites` | `check-prerequisites` tool version checks (mkdocs major-version gating) |
| `test-check-vm-disk-paths` | `check-vm-disk-paths` compute-host iSCSI fence: reference gathering, healthy tick, missing-path detection (exit 1, report-only), and the `--recover` flow — local rescan fixes, storage-host reconcile over ssh, identity conflicts reported only |
| `test-cleanup-zfsutilities-legacy` | `cleanup-zfsutilities-legacy` prompt, `--yes`, `--dry-run`, and non-symlink guards |
| `test-clone-vm` | `clone-vm` storage heredoc bootstrap and lock sourcing |
| `test-deploy-version` | Root-level script selection, exclusions, retention-policy file filtering, critical-script validation, no production wiring, and VERSION-file casing; shared upgrade-lib units (deploy-conf resolution modern/legacy, group lines, ssh control-path template, node-conf resolution modern-first with node-lib back-compat); real script execution through the non-root hatch against an ssh/rsync shim (modern and legacy deploy confs, shared ControlPath socket, MANIFEST.sha256 write/verify, mkdocs-build-failure FATAL exiting cleanly through `bin/bashfatal`) |
| `test-detach-vm-disk` | `detach-vm-disk` iSCSI manifest removal |
| `test-enroll-efi-keys-vm` | `enroll-efi-keys-vm` EFI-disk and iSCSI by-path parsing for Secure Boot enrollment |
| `test-enroll-iscsi-pool` | `enroll-iscsi-pool` POOL_TARGET insertion (multi-line/single-line/no declaration), idempotence, peer-first ordering, storage-host gating, dry-run, single-node no-op |
| `test-enroll-proxmox-pool` | `enroll-proxmox-pool` storage-ID derivation/validation, pvesm-status parsing, single-node zfspool path (dataset creation, idempotence, missing-pvesm guard), two-node iscsi path (compute-host SSH delegation, iSCSI-enrollment prerequisite), dry-run |
| `test-export-iscsi-state` | `export-iscsi-state` pool-resident iSCSI state map: newest-map resolution across online pools, degraded-state refusal with manifest/map fallbacks, `--check` drift reporting, and the read-only `--print-map` dump (newest-wins, no targetcli dependency, mutual exclusion with `--check`) |
| `test-ensure-restored-vm-iscsi` | `ensure-restored-vm-iscsi` parsing: zvol basename/pool extraction, by-path LUN extraction, VM-config LUN lookup, EFI disk detection by size, fallback LUN assignment when zvol disk numbers do not match config slots, and storage-side script forwarding |
| `test-findoffsitepool` | `findoffsitepool` online-candidate selection |
| `test-installer-checks` | Installer prerequisite checks and desktop-launcher helper functions |
| `test-installer-flows` | Execution harness for the installers' interactive flows: `install-single-node` and `install-two-node` run end to end as a non-root user (a mirror tree redirects `script_dir` at stub `check-prerequisites`/`deploy-version`/`switch-version`/`setup-iscsi-targets` while `lib/` and `share/` stay the repository copies; ssh/scp/systemctl/sudo/targetcli/findmnt/hostname/mkdocs are recorded shell functions; answers are piped on stdin; the retention helper runs for real against a fixture config). Covers fresh installs (config generation and template substitution, deploy/activate, systemd drop-ins, encrypted-luns conf, node.conf copy to the compute host, PVE rescan patch applied/skipped), keep-existing-config paths (regression fence for the lowercase-host refresh that used to die at the storage-host check), mode switches declined/accepted, storage-host and SSH-prerequisite fatals, legacy conf notices, partial-uninstall remnants, obsolete systemd-artifact removal, and input validation (empty compute host, non-numeric LUN count, zero pools) |
| `test-installer-retention` | Installer default retention profile initialization and preservation of existing user profiles |
| `test-installer-structure` | Installer layout structural checks (F-002 guard: `bin/` scripts must resolve every library they load from the shipped repository layout — installer-lib path resolution, `bin/`→`lib/` file existence) |
| `test-iscsi-add-encrypted-luns` | Encrypted-LUN config path resolution (modern + legacy fallback), target-scoped LUN-index lookup, and conditional persistence (save only when a backstore was added) |
| `test-iscsi-fresh-install-guards` | Structural guards for the defects a fresh two-node install hits on its first VM-disk operation: safe-iscsi-save exit status checked by every persisting caller (F-016), expected-backstores manifest grown even when absent — the fresh-install state (F-016b), and fresh-TPG initiator access (ACL enablement, F-017) |
| `test-iscsi-recover-encrypted-luns` | Post-key-load encrypted-LUN recovery: recorded LUN indexes scoped to the configured target (orphan-target indexes ignored), refusal to auto-assign, idempotency, and persistence/rescan triggers |
| `test-itf-base-guard` | itf `lib/base-lib.sh`: the confinement guard every base-host access passes through — allow-listed commands only, no escape hatches |
| `test-itf-config` | itf `lib/config-lib.sh`: site-configuration loading and fail-closed validation |
| `test-itf-driver` | itf driver dispatch under strict mode: subcommand routing, journey validation and registration, `--rerun` preparation, `itf status`, and run-lock serialization — holder record, wait/heartbeat/refuse, and the acquire-time orphan fence over interrupted runs' guests (rerun exemptions, fail-closed base checks, no base contact on the healthy path) |
| `test-itf-lab-stages` | itf lab-layer builders in `journeys/common.sh` + `lib/vmos-lib.sh`: the shared test-pools stage, the single-node lab, the VM-OS image build/dump/self-verify orchestration, the agent-channel workload helpers and stall-gap parser, the reboot stage with DHCP address rediscovery, and the LUKS keystore helpers — including that the passphrase only ever travels via stdin and the encrypted lab tail stays off without its flag |
| `test-itf-report` | itf `lib/report-lib.sh`: progressive PASS/FAIL/SKIP run reports and run-state derivation |
| `test-itf-ssh` | itf `lib/ssh-lib.sh`: the dev-side HTTP preseed server lifecycle — a silently dead server would turn an unattended guest install into an interactive hang |
| `test-itf-template` | itf `lib/template-lib.sh`: post-install baseline templates — stamp, name resolution, clone, freshness |
| `test-itf-watch` | itf `watch` target resolution (`itf_watch_resolve` on top of run state) |
| `test-list-vm-disks` | `list-vm-disks` VM disk maps: configs, LUN/host-device maps, running VMs, guest-agent queries, table rendering |
| `test-lock-coverage` | Static checks that locked scripts source zfslockmanager, initialize it, and acquire locks |
| `test-logging` | `log_msg` writes all messages to the session log file and ignores `msg_level`; unset `ZFSUTILITIES_LOG_FILE` handling; `ask_yn`, `warn`, and `die` helpers |
| `test-migration` | One-time migration of config/history/profiles/system files with legacy symlinks |
| `test-module-dependencies` | Static analysis: root-level bash modules source the modules whose functions they call; no stale legacy directory literals anywhere in the script set — `*.sh`/`*.py` plus the extensionless `bin/` scripts, `tests/test-*` suites, and harness runners (fixture data excluded) |
| `test-move-vm-disk` | `move-vm-disk` helper functions: disk-key parsing, manifest add/remove, validation helpers, state round-trip, heredoc bootstrap |
| `test-new-vm-disk` | `new-vm-disk` EFI disk-line building with `ms-cert` gating |
| `test-node-lib` | node-lib helpers: config loading, `find_zfsutility_script` search paths, remote script resolution, `on_storage`/`on_compute` transports (local subshell with inherited functions and args vs ssh with the `transfer_rate_limit` prefix), JSON-config readers/writers, MAC generation |
| `test-no-debug-hooks` | Static guard: no shipped `bin/` or `lib/` script enables the `bashdebug` traps or xtrace (`setx`); both modules remain available for manual interactive use |
| `test-paths` | `paths.sh` defaults, composed paths, legacy paths, and environment overrides |
| `test-proxmox-required-guards` | Proxmox scripts fail fast when `qm`/`pct` are absent |
| `test-remove-vm` | `remove-vm` VMID validation, config-referenced/orphan/reassigned zvol classification, `--cleanup-orphans`, and user confirmation |
| `test-remove-vm-disk` | `remove-vm-disk` storage-side teardown (LUN, backstore, expected-backstores manifest, encrypted-LUNs config) against a state-mutating targetcli mock; destroy routed through `zfsdelfs autoproceed='Y'` with the mock `zfs destroy` refusing child-snapshot datasets (real-ZFS semantics); decline-exits-0 with no teardown; rerun after the LUN is already gone; and the compute-host wrapper's `ssh -t` + input-hold + `--skip-rescan` delegation and rescan-even-on-failure |
| `test-rename-vm-disk` | `rename-vm-disk` VM-config reference discovery (single- and two-node) |
| `test-reconcile-iscsi-state` | `reconcile-iscsi-state` map-driven LUN reconcile: backstore rebuild at the recorded LUNs, per-item refusal of identity conflicts, manifest/saveconfig/pool-map refresh, and the compute-host rescan |
| `test-repair-iscsi-luns` | `repair-iscsi-luns` backstore/target parsing and zvol discovery |
| `test-repair-vm-disk-refs` | `repair-vm-disk-refs` compute-host VM-config repair: the identity chain (config slot → map backstore → live slot), by-path rewrite with options preserved byte-for-byte, per-item refusals with evidence (no map entry, cross-VM backstore, not exported live, running/unknown VM, two refs to one backstore), map sanity gates (host/IQN-prefix/storage-IP), dry-run, the two-round-trip storage-host fetch, and post-apply device verification with rescan |
| `test-repair-vm-disk-sizes` | `repair-vm-disk-sizes` size byte-to-human conversion, by-path/storage-ref size resolution, config line repair, dry-run |
| `test-rootcheck` | `rootcheck` guard terminates the process (exit 1) when not root and returns cleanly when root — each branch skipped when the suite runs as the other uid |
| `test-rsync-dailybackup` | `rsync-dailybackup` site-specific rsync helper: job execution with exclude patterns, malformed-job skip, node-config resolution (FHS conf first, legacy fallback), missing-config non-fatal |
| `test-rescan-storage` | `rescan-storage` low-device-count warning against the optional `EXPECTED_ISCSI_DEVICES` minimum (set/empty/non-numeric/zero) |
| `test-restart-iscsi-services` | VM running-state detection before iSCSI target restart and main() helper invocation |
| `test-run-tests-preflight` | Harness self-test: run-tests environment preflight, manifest requirement skips, soak-suite gating, and the pytest exit-5 rule |
| `test-sever-vm-clone` | `sever-vm-clone` severance cycle on a file-backed mock ZFS: argument/qm guards, two-phase cutover with pre/post GUID verifies, origin gates (phase 1 refuses a staged copy that is still a clone with nothing destroyed; post-swap backstop fails a still-clone swap), phase-1 engine failure (the parent reaches its rc handler: resume guidance prints, nothing destructive ran, no scratch results file leaks), children-first snapshot sweep (the mock `zfs destroy` refuses datasets with child snapshots), holds lifecycle, name-preserving swap, `--continue` recovery from each crash phase, `--rollback` (impossible after origin destroy), holding-pool mode with space-feasibility gates, two-node storage-entry delegation; the mock `zfs send` enforces argv fidelity (no `-i`/`-I`/`-t` inside option clusters) |
| `test-safe-iscsi-save` | Degraded-config guard for iSCSI saveconfig and encrypted-backstore boot-config stripping |
| `test-setup-iscsi-targets` | `setup-iscsi-targets` initial target setup plus the post-restore detection signature (evidence printed) and the reconcile offer — declined leaves the system untouched, accepted runs the reconcile; a fresh install still detects clean |
| `test-snapshot-names` | Static checks pinning every snapshot-name producer to the canonical UTC helper, plus a cross-implementation consistency matrix against the Python `snapshot_naming` module |
| `test-startdocserver` | Server health checks, PID discovery, CWD mismatch, restart logic, static-site refresh on start |
| `test-strict-mode` | Static guard: the migrated orchestrators keep `set -euo pipefail` (new strict-mode scripts register here) |
| `test-switch-version` | Version switching, production wiring, prior-version uninstall, rollback, `--uninstall`, `--list`, and obsolete systemd artifact cleanup — including the iSCSI fence-unit gate (single-node skip, fresh two-node compute deploy with no node config yet) |
| `test-test-lib` | Harness assertion helpers: pass/fail/skip counter semantics and golden assertions; per-PID `/tmp` artifact lifecycle (green suites remove log and mock-state dir, failed suites retain only the log, exit status survives the cleanup trap); the source-time orphan sweep (a dead suite's leftover mock-state dir is reaped by the next suite to source `test-lib.sh`, a live suite's dir is never touched) |
| `test-unarchive-vm` | `unarchive-vm` `--new-vmid` rewriting, UUID regeneration, conflict handling; METHOD-branching restores (copy reblock via sidecar volblocksize vs raw/legacy plain receive), sidecar policy (missing `.disk_info` fatal, missing volblocksize sidecar warn for raw / fatal for copy), unknown-method rejection; rate-limited restore copy (pacer pacing, dd conv=sparse, a single paced destination read-back with the source device read exactly once), in-flight source-hash coverage (hash read pattern, source-hash-failure abort with rollback); re-run idempotency (`RESTORED_AS` marker skip, unmarked-destination confirm/decline gates, completed-run clean exit); two-node restore staging (bash-format node conf, both hosts on the stub hostname so payloads take the local branches, ssh/targetcli mocks): Step-2 pool→target mapping via `pool_to_target` across two mapped pools and Step-3 by-path disk-line LUN rewrites; and static payload-routing checks (on_storage/on_compute, no compute bounce) |
| `test-uninstall-some-versions` | Bulk version uninstall from an explicit list file |
| `test-uninstall-version` | Single-version uninstall prompting with `-y`/`--yes` |
| `test-uninstall-zfsutilities` | Full uninstall: preserve-by-default, `--purge`, `--dry-run` |
| `test-upgrade-zfsutilities` | `upgrade-zfsutilities` end-to-end against a file:// fake GitHub (release tarballs, latest.json) with transport-only ssh/rsync shims that re-execute the real piped library against per-host fake version bases: up-to-date/no-op paths, both consent declines, happy paths clean and with local changes (modification listing, unified diffs, per-host salvage, combined diff), manifest baseline and tarball fallback, untagged no-diff and unverifiable-host consent flow, ssh-failure abort, multi-host deploy groups, and modern node.conf target enumeration with no deploy.conf; switch-version is asserted never executed |
| `test-validate-guestfs-probe` | `share/dev/validate-guestfs-probe.sh` execution harness: the `--self-check` probe chain (scripted qm runner, no host/root/zfs) passes against the repository python tree — fencing the validator against drift in the `alignment_guestfs` probe internals it consumes — plus `-h` usage (including the live-verdict wording: non-zero exit with reasons when any source comes back empty) and the non-root refusal of a bare run; the root+zfs live path itself is fenced end to end by the itf j06-guest-probe-validator journey |
| `test-vm-disk-two-node-gate` | Structural checks on the Proxmox (`qm`) gate of the vm-disk family: two-node storage-role exemption, `qm` still demanded elsewhere, `my_host` assigned once before the gate, storage delegation present |
| `test-zfs-diagnose-busy` | Diagnostic output from `zfs-diagnose-busy` — busy dataset causes |
| `test-zfs-send-receive-dryrun` | Dry-run logging, space checks, resume-token helpers (including non-existent destination), clone messages, the pacer stage in headless rate-limited mode, full-copy lock hand-off, two-step full transfers, pool-root full-copy fallback |
| `integration/test-zfs-send-receive-pools` | Real-pool integration tests for `zfs-send-receive`: full copy, incremental with/without intermediates, rollback, resume token, space-check skip, clone copy. Requires root and the local test pools described below. |
| `test-zfsbuildfsarray` | Dataset array building with includes/excludes/depth/sorting |
| `test-zfscheckagainst` | `zfscheckagainst` snapshot verification against backup/offsite counterparts (online and hold-tag paths) |
| `test-zfscheckrunningvms` | `zfscheckrunningvms` exit codes when `qm`/`pct` are missing |
| `test-zfscleanup` | Pool selection: config pools, explicit argument, fallback to online pools, offline skip |
| `test-zfscommsnap` | Common snapshot detection by GUID, most-recent/oldest modes |
| `test-zfsconfig` | `zfsconfig` pool-entry emission (string, dict, and mixed forms) |
| `test-zfsdailybackup` | `zfsdailybackup` pull/push failure WARN-and-continue and dry-run logging |
| `test-zfsdelallholds` | Selective hold release by tag patterns |
| `test-zfsdelallsnaps` | Return-code behavior and lock acquisition around snapshot deletion |
| `test-zfsdelfs` | iSCSI teardown/rebuild manifest cleanup for `zfsdelfs` |
| `test-zfsdelsnap` | Snapshot deletion safety checks, hold release, `zfscheckagainst` dependency sourcing, user-hold blocking; `_delsnap_preview_gate` (the read-only dry-run mirror of the gates): checkagainst rc matrix incl. exit-8 subshell containment and context folding, minimum-age keep and unknown-age fall-through, holds held/remaining/releasable classification, clone dependents |
| `test-zfsfullcopy` | `zfsfullcopy` full-copy wrapper: overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfslockctl` | `zfslockctl cmd_wait` availability and interval validation: fractional `ZFSLOCK_WAIT_INTERVAL`, invalid/zero fallback, no-sleep fast path |
| `test-zfslockmanager` | Lock acquire/release, conflict detection, hierarchy, stale cleanup, headless abort, multi-lock acquisition, timing-knob sanitization, `source_helper` loading context |
| `test-zfslockmanager-remote` | Remote lock hold/check/conflict protocol |
| `test-zfslockmanager-soak` | Randomized timing-conflict scenarios for the lock manager at realistic timings — including wait/retry loops and headless timed waits (skipped by default; see "Soak suites") |
| `test-zfsmassdelsnaps` | Mass snapshot deletion: ignore/respect retention, dry-run, approval, releaseholds forwarding; gate-reason "Would: Keep" preview lines stay out of the parsed candidate list and space estimate |
| `test-zfsmount` | Lock acquisition before mount/unmount per dataset |
| `test-zfshold` | `zfshold` hold helper: duplicate-tag detection as INFO (including a nested dataset re-found through a parent-subtree hold), real hold failures surfaced loudly, no-match exit 0, missing pattern rejected |
| `test-zfsreapplyholds` | Capture/release/apply snapshot holds, no-lock opt-out, CLI argument parsing, dry-run apply/release |
| `test-zfs-send-receive-holds` | `zfs-send-receive` destination hold preservation: capture/reapply ordering on full copies, skip on plain incrementals, dry-run, and `preserve_target_holds='N'`; capture failure aborts before any transfer |
| `test-zfsrestore` | `zfsrestore` full-copy wrapper: overrides, legacy second overrides, required parameters, single `send-receive` invocation, parameter forwarding |
| `test-zfsrestoresendstream` | Lock acquisition before each zfs receive destination |
| `test-zfsresume` | Lock acquisition before reading resume token |
| `test-zfs-migrate-send` | `zfs-migrate-send` fresh-send pipeline (`-Rw`/`-u -F -s -v`), `-nPRw` size estimate (incl. zero-byte vs missing-estimate), incremental catch-up send (`-Rw -I` with `$fromsnap`, incl. incremental estimate and rc 8), clone-source copies (origin-free plain full of the oldest snapshot plus `-w -I`, never `-R`; single-snapshot, catch-up, re-run skip when `@oldest` is already staged, local-compression receive override), resume via `zfs send -t <token>` (received `-v`), stale/unexpected token abort + fresh retry, failure re-run hint (rc 8), pv progress and pacer rate-limit plumbing; the zfs send mock rejects option clusters containing `-i`/`-I`/`-t` |
| `test-transfer-lib` | `transfer-lib.sh` pv-arg construction (tty/LOG_INHERIT/headless), pacer-stage construction and ordering (pacer before pv; headless paces without pv), the unresolvable-pacer failure mode (pace args empty, `transfer_do` FATALs before any pipeline stage runs), resume-token validation and stale-string classification, token abort (live + dry-run), space-check math and WARN text, `transfer_do` pipeline argv (incl. the `-I` second-target incremental form) and FATAL rc |
| `test-zfsretain` | Retention policy phases (offsite dedup, same-day dedup, oldest-first bucket pruning, empty logging, retain=0); dry-run wiring of `_delsnap_preview_gate` (per-phase Keep downgrades with phase context, forwarded minage/releaseholds/context argv, no delsnap calls, caveat naming only the unmodelable residuals) |
| `test-zfsretain-debug` | `zfsretain` sources cleanly and defines the retain function |
| `test-zfsscruball` | `zfsscruball` state file, `zpool scrub -w` invocation, completed-pool skip |
| `test-zfssend` | `zfssend` defines a send function after sourcing |
| `test-zfsshowbigstuff` | `zfsshowbigstuff` usage errors and sort-option handling |
| `test-zfssnapbuild` | Snapshot name generation, bucket logic, snapfile handling |
| `test-zfswipe` | `zfswipe` inactive-disk label wipe: argument/inactive-disk guards, typed confirmation, already-clean short circuit, `zpool labelclear` before `wipefs`, dd fallback math and residue failure, dd-failure kernel notification, partition-table targets |
| `test-zfsunmount` | Lock acquisition before unmount per dataset |

Bash tests run without a real ZFS pool — commands are intercepted with bash
function overrides so every suite can execute as a normal user.

### Writing a New Bash Suite

1. Create `tests/test-<scriptname>` (executable, no extension).
2. Source `test-lib.sh` at the top.
3. Define test functions that call `test_start` plus any assertion helpers.
4. Call `test_summary` at the end.  The suite's `/tmp` artifacts are cleaned
   up automatically at exit (failed suites keep their log for post-mortem).
   If the suite needs its own exit cleanup, register it with
   `append_exit_trap` rather than a bare `trap ... EXIT`.

If the suite genuinely needs a system binary that other suites mock (rather
than overriding the command the way `test-lib.sh` mocks do), declare the
requirement with a `capability tests/test-<scriptname>` line in
`tests/requirements.manifest` so the harness skips it cleanly where the binary
is absent.

Minimal example:

```bash
#!/usr/bin/bash
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test-lib.sh"

test_example() {
    test_start "Addition works"
    local result=$(( 2 + 2 ))
    assert_equals "4" "$result"
}

test_example
test_summary
```

### Bash Assertion Helpers

| Helper | Usage |
|--------|-------|
| `assert_equals expected actual` | Pass if strings match |
| `assert_contains haystack needle` | Pass if haystack contains needle |
| `assert_rc expected actual` | Pass if return codes match |
| `assert_array_len expected "${arr[@]}"` | Pass if array length matches |
| `assert_golden name actual` | Compare against `tests/golden/<suite>/<name>.golden` (see below) |

### Golden Files

Command-construction tests compare against golden files instead of
per-argument assertion clusters. `assert_golden <name> <actual>` (bash) and
`golden.check(testcase, actual)` (Python) compare against
`tests/golden/<suite>/<name>.golden` in canonical form: exactly one trailing
newline, and argv lists serialized one element per line so diffs read
per-argument.

After a legitimate refactor, run `UPDATE_GOLDEN=1 tests/run-tests <suite>`,
then `git diff` the goldens and review them like code. Update mode rewrites
only goldens whose content actually changed (an update run with no product
change produces an empty `git diff`), and marks those tests "updated" (bash:
the `Updated:` summary line; Python: skips) rather than passed. Missing
goldens fail with the command that creates them. Regeneration runs should
target single suites (they run serially through `run-tests`); update mode
under a parallel full run is not the documented path.

### Bash Mock Infrastructure

`test-lib.sh` overrides `zfs()`, `zpool()`, `delsnap()`, `ask_yn()`, `date()`, and
`log_msg()` (redirected to a per-test log file).
Because scripts are *sourced* into the test shell, these overrides intercept
`$(zfs ...)` and pipeline invocations automatically — no `PATH` manipulation is
needed.

#### Common Mock State Variables

| Variable | Purpose |
|----------|---------|
| `_mock_zfs_fs_list` | Output for general `zfs list` dataset listings |
| `_mock_zfs_snap_lists[<dataset>]` | Snapshot names per dataset (for `zfs list -t snap`) |
| `_mock_zfs_guid_lists[<dataset>]` | GUID list per dataset (for `zfs list -o guid`) |
| `_mock_zfs_props[<dataset>:<property>]` | Property values returned by `zfs get` |
| `_mock_zfs_snaps[<snapshot>]` | Snapshot existence flag (for `zfs list -t snapshot <snap>`) |
| `_mock_zfs_datasets[<dataset>]` | Dataset existence flag (for `zfs list <dataset>`) |
| `_mock_zfs_send_size` | Byte size returned by `zfs send -nP` |
| `_mock_zpool_list` | Output for `zpool list -Ho name` |

#### Setting Up Mocks

```bash
# Dataset listing
mock_zfs_fs_list "pool/src/data\npool/src/vm"

# Snapshots for a specific dataset
mock_zfs_snap_list_for "pool/src" "pool/src@snap1\npool/src@snap2"

# Property lookup
mock_zfs_prop "pool/src" "available" "10000000000"
mock_zfs_prop "pool/src@snap1" "type" "snapshot"
```

---

## Python Test Suites

| Suite | What it covers |
|-------|----------------|
| `test_action_dispatch` | Page button specs, action dispatch table, Logs tab button wiring, and Disks tab pool-growth button wiring |
| `test_alignment_analysis` | `alignment_analysis.py` — analysis rules (ashift vs member sectors, recordsize/volblocksize vs ashift block, survey mismatch, observation-gated advice with traffic thresholds), per-dataset objset observed-size rules (interval vs since-boot basis selection, per-dataset op floor, zvol partial-block advice, survey-declaration citation, per-pool fallback plus the stated-limit finding when objset kstats are missing), topology-aware mixed-geometry findings (per-vdev-group naming, cross-group silence, pool-wide fallback without a tree), workload classifier, ARC readouts, `blocksize_ladder` data inputs (stack order, size grouping with ×counts, rung states, per-source and per-pool degrade, non-power-of-two sizes), degrade paths, stable per-rule finding keys and per-pool dataset-read-failure findings |
| `test_alignment_guestfs` | `alignment_guestfs.py` — the guest-agent probe against a scripted runner (no real ssh/qm: every guest round-trip asserted by argv shape — `qm guest ping` availability, the single `lsblk -bJ` device-tree exec, the batched `stat -f -c %S`), the zvol↔guest-disk match chain per tier (pinned serial wins, UUID/PARTUUID signature intersection with cross-volume clone refusal, size+bus fallback with the bus-letter mapping), wire-format parsing (qm-exec JSON, lsblk trees incl. dm/LVM mount attribution and `\xNN` escape decoding, storage-side zvol signature reads), ssh-channel selection per node config, the TTL cache (window, volsize keying), and the per-volume degrade reasons (agent unavailable/unreachable, VM stopped, timeout, command failure, no mounts, unsafe mount paths, stat garbage) |
| `test_alignment_page` | Alignment view: Performance view switcher (radios, stack children, persistence, the map-time re-assert of a pre-realization restore that GTK dropped, dispatcher routing), sample application to chain/topology/findings/workload stores and memory-tier readouts (topology rows cover vdev classes, group names, members, ashift-known-but-status-failed degrade, and in-place reconcile across ashift drift; findings cover the per-dataset observed-size rows, the interval-basis handoff between two applies, and the objset entry of the degrade note), the blocksize-ladder section (factory fallback selection under mocks, apply path feeding per-pool rungs, per-source degrade, Cairo draw smoke), table ergonomics (every table in its own fixed twenty-line window — longer tables scroll inside it, shorter or empty ones keep the full height; scan columns sortable with the hidden identity key excluded; ellipsizing cells with hover tooltips that fire only where the text actually truncates; one non-last expand column per table), the datasets-page scroll save/restore idiom around every apply (including the refresh chain and the survey dialog's in-place refresh), ordered in-place row reconciliation on hidden key columns (ordered and sorted-store paths), degrade notes (including per-pool dataset-read failures and per-volume guest-probe failures), probed-guest-filesystem detail cells, workload-survey dialog save/cancel/hint paths |
| `test_alignment_realized` | Realized-window scroll and geometry check: spawns `alignment_realized_check.py`, which builds the real Performance page in a realized `Gtk.Window` (a private Xvfb — never the ambient display, so nothing can flash on the operator's desktop mid-suite; the check skips when no private display is possible and names the display it drove on stdout, which the suite asserts is not the inherited one) and drives the GTK main loop — asserting the vertical offset holds across a findings change and a transient per-pool dataset failure while content above the viewport stays put, the topology table keeps its row identities, and the blocksize ladder keeps its per-pool rungs (dropping dataset/VM rungs with the per-pool failure, via whichever renderer the factory selected under real GTK) (the sample's pools carry vdev topologies and its datasets carry objset counters, so the new finding rows render and reconcile in the realized window too). A second geometry pass locks the Performance page's widget geometry in realized windows at several widths — every table window keeps its fixed twenty-line height whatever its row count (empty tables included), each table whose columns overflow shows its own live horizontal scrollbar while the page itself never scrolls sideways (so each table's vertical scrollbar sits inside the visible width), the far-right column renders its configured fixed width with the designated expand column absorbing slack, and the ladder canvas never drops below its content-derived minimum with its own live horizontal scrollbar at a mid-width window (the reproduced `max_content_width` clamp) — and at a deliberately narrow window (400 px, overridable via `REALIZED_NARROW_W` for threshold experiments) the page itself must stay non-scrolling horizontally in both views, locking the ellipsized section headers and value-grid captions (an unellipsized header pins the page minimum at its full natural text width and grows a page-level scrollbar that only ever carries label text) — and the suite runs that pass under both chart renderers (`REALIZED_CHART_RENDERER=cairo` flips the check to the Cairo fallbacks before any page builds; the check names the selected ladder class on stdout, which the suite asserts); runs as a child process so real-GTK bindings and the warmed matplotlib backend cannot poison the mock-bound module caches |
| `test_alignment_stats` | `alignment_stats.py` — `zpool iostat -r` parser (captured multi-pool output), zfs-size/bucket-label parsers, per-dataset objset-kstat parser (captured 2.2/2.4 bodies) with delta rates and average request sizes, PVE VM-config parsing (the VM-level `agent:` switch, the marker-delimited compute-node dump, the ssh fetch and its local-wins / two-node-fallback / single-node-never-fetches selection), guest-probe target assembly (serial + storage-side signatures) and probe results flowing into the sample, sample collection with fake repos, per-source degrade, and per-pool dataset-read degrade |
| `test_app_context` | Shared operational state (app context) helpers for GUI pages |
| `test_backup_config` | Config load/save, defaults, pools, retention, UI state, snapshot name generation, log pruning, message level |
| `test_backup_history` | History entry schema, load/save/prune, success-rate calculation, human-size parsing, duration formatting |
| `test_backup_page` | Backup tab UI labels (including pre/post command labels), config load/collect helpers, and frame header widget support |
| `test_backup_runner` | Session log creation, subprocess output parsing, byte counting, trailer formatting, completion-callback rc/failure reporting, fatal step messages, log size cap, and spawn-failure-as-step-failure (a step that never launches finishes rc=1, skips its post-callback, and still runs the finally step first) |
| `test_charting` | `charting.py` — shared rolling-chart vocabulary (nice-ceiling ladder, age labels), the theme palette (light/dark resolution from style-context colours, the LIGHT_PALETTE degrade, dark state re-mapping), the GUI-base-font scale (`chart_font_scale`: theme-font resolution with its degrade-to-1.0 paths, and every text site plus the ladder width floor scaling with it in both matplotlib renderers), the lazy backend probe (unavailable under mock_gtk), factory fallback selection for both chart kinds, the matplotlib rolling chart against a fake backend (artist updates, scaling, legend, reference line, one-shot layout, legend rebuild on style-updated so theme flips recolour immediately), and the matplotlib blocksize ladder (bar positions/widths/colours per rung, per-pool dashed reference lines, log2 axis with power-of-two ticks, bold pool headers, legend patches, the content-minimum-only canvas width request (the retired followed-width API stays retired), the ladder text sizes, height/layout following the row set only, empty/unavailable placeholders) |
| `test_checkagainst_derivation` | Checkagainst derived-row generation, merge, and source/dest-root helpers |
| `test_checkagainst_page` | Checkagainst tab table editing and config persistence |
| `test_pace_stream` | `lib/pace_stream.py` pacer: rate grammar matrix, chunk clamps, deadline/forfeit arithmetic (injectable clock), CLI passthrough (file/stdin, short final chunk), rate-bounded elapsed time, SIGPIPE rc 141 |
| `test_command_builders` | Rsync/ZFS command builders, retention step descriptions, endpoint parsing, dry-run assignments, host detection |
| `test_config_core` | JSON config load/save and generic state helpers |
| `test_config_migrations` | Schema migrations 1→26, idempotency, missing migration errors |
| `test_cron_manager` | Cron line generation, condition support, configured cron-log path, timestamp-stamped sink, human-readable interpretation, next-run computation |
| `test_dashboard_page` | Dashboard layout (the section tables in their own 20-row capped scrolled windows, the page viewport sizing content by natural height), task handling, pool/VM/scrub/history queries, warning indicators (incl. SSD/NVMe wear), surface-test running-task cancel, async refresh loading state |
| `test_dataset_actions` | Datasets tab actions (mount/unmount/destroy/holds) driven through BackupRunner |
| `test_datasets_page` | Datasets tab UI, dataset tree, and mounted-state refresh |
| `test_datasets_tree` | Lazy dataset-tree loading in `gui_helpers` |
| `test_diagnose_zfs_repository` | `diagnose_zfs_repository.py` — diagnostic main() output for pools, datasets, snapshots, and error paths |
| `test_disk_actions` | `disk_actions.py` — Disks tab SMART-details action and selected-disk path resolution (name/by-id fallback) |
| `test_disk_repository` | `disk_repository.py` — lsblk, by-id, and smartctl subprocess isolation, wear/self-test parsing, boot-disk filtering |
| `test_disk_surface_test` | `disk_surface_test.py` — SMART self-test state machine, JSON persistence under flock, cell-text formatting, start/cancel dialog, Disks-page sensitivity gating and dashboard cancel dispatch |
| `test_disks_page` | Disks tab UI, including topology-selection highlighting in the inventory |
| `test_profile_dialogs` | Apply Profile picker treeview/dialog/execution, Rewrite Data gating plus its truthful completion summary (results-file capture/count plumbing, the rc=0 matrix — files-rewritten count, rewrote-nothing, summary-unavailable/incomplete, datasets missing a summary — and results/capture cleanup), the generated rewrite script really executed against a stub `zfs` (count, no-op, rc propagation, mount/unmount), workload profile manager/editor (driven from the Datasets page); Add/Recall schedule-profile dialogs and duplicate-name overwrite handling |
| `test_disks_page_growth_buttons` | Disks tab pool-growth button sensitivity gating (Add Data Vdev, Expand Vdev, Replace, Detach, Add Infra Vdev, Migrate Pool): compute-host, runner-busy, tooltip precedence |
| `test_docs_integrity` | MkDocs nav consistency, orphan-file detection, internal link resolution, anchor existence, hook importability; AGENTS.md repo-relative path and `Branch:` reference validation |
| `test_docs_viewer` | Standalone documentation viewer launcher |
| `test_feature_config` | Per-feature config getters/setters, snapshot name generation, checkagainst entry merge, workload and pool profile quintets/immutability |
| `test_file_locking` | Advisory flock helpers |
| `test_golden` | `golden.py` golden-file helper — canonical serialization, compare/update modes, missing-golden errors |
| `test_gui_helpers` | `gui_helpers` utilities, including mounted-snapshot detection via `mount -t zfs`, orange non-default expander labels, log font scaling (CSS steps, persistence, restore, View menu wiring), Pango-escaping in section headers / notes, and the capped table-window helper (fixed twenty-row minimum pinned to the cap for the Performance pages, the Dashboard's explicit natural-height convention, row-target scaling, and the cap following the measured row height) |
| `test_gui_infrastructure` | GTK mock setup, GUI module imports, docs viewer zoom/navigation/state persistence, anchor scrolling |
| `test_installer_retention` | Installer retention profile initialization: default-only on new install and preservation of existing profiles |
| `test_iscsi_enroll` | `iscsi_enroll.py` — derive_target_short, is_iscsi_managed_pool, enroll argv building, post-create enrollment offer (two-node gating, decline/failure paths) |
| `test_proxmox_enroll` | `proxmox_enroll.py` — storage-ID derivation/validation, pvesm argv building and status parsing, post-create Proxmox offer (mode gating, iSCSI prerequisite, already-registered skip, decline/failure paths), Disks-page action guards |
| `test_legacy_retention` | Legacy `zfsretainpol-*` file parsing and pool scanning |
| `test_log_index` | Persistent session-log metadata index |
| `test_logging_config` | Message levels, GUI sink, session log env helpers, and session log truncation |
| `test_logrotate_manager` | Logrotate drop-in content (per-log stanzas, rotation policy, configured paths) and write behaviour incl. FATAL-on-failure |
| `test_logs_page` | Log list scanning, filtering, deletion, status parsing, cron-log rows incl. rotated copies, gzip decompression in the viewer, tail-only viewer for large files, column-header label tooltips, saved font-scale restore, and pop-out reparenting |
| `test_main` | GUI entry point: PID-file single-instance, auto-replace, transient wait dialog, event pumping, retry-after-remote registration, pkexec logic, initial dashboard refresh |
| `test_memory_page` | Performance tab: Live Charts / Blocksize Alignment view switcher, charts value grids/notes/charts, every table window pinned to the fixed twenty-row cap (both views), the ladder window's page-width floor wiring, device-table column-width persistence binding, the exposed page ScrolledWindow (`performance_scrolled`), refresh-interval persistence, fixed chart heights at the pack sites |
| `test_migration` | One-time state-file migration helper |
| `test_node_config` | Two-node configuration loading and resolution |
| `test_offsite_page` | Offsite tab UI, offsite pool detection, and config helpers |
| `test_offsite_e2e` | GUI payload e2e (offsite family): real BackupRunner driven headless through a GLib main loop — pty stdin, input-hold REQ/ACK round trip, rc propagation — plus the offsite scenario matrix from `e2e_support` (chain steps with holds, incrementals, rollback, resume tokens, scrub pause, dry-run) against the zfstest pools; mutating scenarios self-skip where dataset mutations are unavailable |
| `test_offsite_runner` | Offsite run command builders and pool detection |
| `test_backup_payload_e2e` | GUI payload e2e (backup family): the backup send/receive payloads (full, incremental, destructive with hold preservation), the prune payload, the rsync wrapper, and the strict-mode-flipped leaf orchestrators (zfssend, zfsfullcopy, zfsrestore) plus the zfshold round trip — CLI orchestrators run protocol-off through the pty executor, as cron/terminal would |
| `test_page_runners` | Backup/offsite/restore run handlers, session log preparation, auto-destination, pull-step activation |
| `test_path_utils` | Shared path helpers mirroring bash `$mydir` / `find_zfsutility_script` behavior |
| `test_paths` | Centralized path-resolution module (local and remote deployed layouts) |
| `test_pool_actions` | Pool registry add/remove/save/revert action handlers |
| `test_pool_create` | `pool_create.py` — disk eligibility and partition policy, vdev separation, pool-name validation, ashift suggestion, RAIDZ capacity estimator, RAID10 count validation, pool-profile `-o`/`-O` option builders |
| `test_pool_create_wizard` | `pool_create_wizard.py` — wizard page gating, exact command building (incl. RAID10 mirror pairs and profile-driven `-o`/`-O` flags), handler guards, Create Pool button sensitivity, blocksize/profile interplay, scripted end-to-end flow with lock acquire/release and registry offer |
| `test_pool_growth` | `pool_growth.py` — attach/replace/detach classification, replace-pair and infra-vdev validation, scrub-block check |
| `test_pool_growth_dialogs` | `pool_growth_dialogs.py` — Add Vdev/Attach/Replace/Detach/Infra-Vdev pure helpers, handler guards, and dialog flows |
| `test_pool_migrate` | `pool_migrate.py` — migration snapshot/temp-pool naming, cutover snapshot naming, zvol-to-VMID mapping, step planning (incl. cutover catch-up placement), capacity checks, tree verification, migration argv builders |
| `test_pool_migrate_dialogs` | `pool_migrate_dialogs.py` — Migrate Pool dialog problems/warnings/plan, origin-derived new-pool settings (Match origin pool defaults, blocksize, infra-vdev warning), scrub-block gate, handler guards, two-phase copy/cutover execution (incl. cutover catch-up steps, cutover-time layout abort, and the running-VM gate), iSCSI repair chaining |
| `test_pool_profiles` | `pool_profiles.py` — schema constants, profile property filtering and canonical `-o`/`-O` ordering, blocksize resolution/labels/below-recommendation, profile validation, origin pseudo-profile derivation, infra-vdev classification |
| `test_pool_profile_dialogs` | `pool_profile_dialogs.py` — pool profile manager (list, add, edit, builtin delete guard, reset) and editor (add/edit, builtin save-as-new, overwrite confirm/decline, validation), Disks-page action wiring |
| `test_pool_watch` | Per-pool dataset watch window |
| `test_pools_page` | Pools tab registry UI |
| `test_profile_integration` | Concurrent profile execution: disjoint datasets, same-dataset conflict, backup+prune serialization |
| `test_profile_manager` | Profile CRUD, update, name validation, listing, existence checks, lifecycle logging, condition defaults |
| `test_profile_runner` | Backup/offsite/restore/retention profile step building, rsync failure diagnosis in headless runs |
| `test_profile_runner_concurrency` | Per-profile advisory locks, duplicate-invocation suppression, and metadata |
| `test_profile_validation` | Backup/offsite profile scope-alignment checks |
| `test_restore_page` | Restore tab UI widgets, config load/collect, auto-destination, advanced variables |
| `test_restore_runner` | Restore destination computation and zfs-send-receive parameter mapping |
| `test_retention_actions` | Retention tab action handlers |
| `test_retention_page` | Retention Policies tab UI |
| `test_runner_factory` | Runner factory wiring for page runners |
| `test_runner_shim` | `runner.py` deprecation shim — legacy argument translation to pytest and deprecation notice |
| `test_schedule_page` | Schedule page path resolution, dirty tracking, condition field, run-now child-watch handling, fatal-fallback logging, async refresh, and next-run caching |
| `test_scrub_manager` | Scrub state parsing, queue/target management, priority ordering, tick logic, systemd timers, ZFS-native in-progress operation parsing, persistent event log (config-driven path) |
| `test_scrub_page` | Scrub page store schema, flicker-free refresh logic, and drag-and-drop priority ordering |
| `test_session_log` | Per-run session log helpers (create, append, trailer, size cap) |
| `test_workload_profiles` | Workload profile property filtering, profile matching, apply plan, `zfs set` command building, warnings |
| `test_zfs_capabilities` | OpenZFS release-variation gating (incl. patch-level minimums such as `zfs_rewrite` at 2.3.4), pool-feature cross-check parsing |
| `test_zfs_diagnostics` | `gui_helpers.diagnose_dataset_busy` — detects each known cause via mocked `subprocess.run` |
| `test_zfs_lock_manager` | `zfs_lock_manager` two-node lock behavior and stale-lock cleanup (including unverifiable holder scripts) |
| `test_zfs_repository` | `zfs_repository.py` — ZFS/zpool subprocess isolation, importable-pool config parsing, zvol listing, `zpool create` (incl. RAID10 mirror pairs) and pool-growth/migration command building (incl. incremental `from_snap`) and execution |
| `test_zfsinfo` | Pool/dataset/snapshot info gathering with mocked `subprocess` |
| `test_zfsutilities_gui` | Main GUI window behavior, dashboard/scrub/pools/disks timer lifecycle, and log-font handler dispatch |

Most Python suites are standard `unittest.TestCase` classes executed by
[pytest](https://docs.pytest.org/) with
[pytest-xdist](https://pytest-xdist.readthedocs.io/) parallelism — no test
rewrite was needed and assertion failures get pytest's expected-vs-actual
diff output. A few suites (for example `test_golden`) use pytest fixtures
directly. `tests/run-tests` remains the single entry point for both
layers; `tests/python/runner.py` is a deprecated shim that forwards to
pytest for older invocations.

### Python Dependencies

- `pytest` and `pytest-xdist` — the test runner. Install both with
  `python3 -m pip install -r requirements-dev.txt`.
- `pyyaml` — required only for `test_docs_integrity` (parses `mkdocs.yml`).
  Install with `python3 -m pip install pyyaml`.
- `gi` — the GTK tests mock `gi.repository` so no display server is needed.

### Running Python Suites Directly

```bash
# All Python suites, parallel across CPUs (worker count auto-capped by
# available memory — each xdist worker peaks at ~600-900 MB; override with
# ZFSUTILITIES_PYTEST_JOBS=N)
python3 -m pytest tests/python -n auto -q

# Specific suite (fail-fast, short tracebacks)
python3 -m pytest tests/python/test_backup_config.py -x --tb=short

# Single-process run (definition order; useful for order-dependence checks)
python3 -m pytest tests/python -q

# Legacy entry points still work (runner.py prints a deprecation notice)
./tests/run-python-tests
./tests/run-python-tests test_backup_config
```

`--failures-only` has no exact pytest equivalent; it maps to `-q`, which
prints only failures plus the final summary.

GUI suites import their modules under `test_support.mock_gtk()`. Without
options, the first `mock_gtk()` context that imports a GUI module wins: the
module keeps that context's `Gtk`/`GLib` mocks for the rest of the session,
and each `Gtk.Widget()` returns one shared per-class mock whose call history
accumulates across every test that ran before. Tests must therefore not rely
on unittest's alphabetical method ordering and must not assert per-test call
counts on shared widget mocks without resetting them first; likewise, patch
attributes on the module object the code under test actually imported (e.g.
patch `gui_helpers.Gtk.MessageDialog` — via a module reference bound at the
test file's own import — not a re-imported copy).

For per-test module freshness, pass `fresh=True`: every loaded GUI module
(see `test_support.GUI_MODULES`) is evicted from `sys.modules` for the
duration of the context and restored on exit, so imports inside the context
bind the current context's mocks and call history starts empty — without
leaking a different module object to the rest of the session. Use it whenever
a test asserts on widget call counts or needs to patch a GUI module it did
not itself import. Helpers that re-import a GUI module (the `_import_*`
helpers several suites use) must always pass `fresh=True`: otherwise a GUI
dependency cached with real bindings — for example `gui_helpers` imported at
collection time by a suite that uses real GTK — leaks real Gtk into the
re-imported module and crashes tests that hand mock windows to real dialog
constructors (`TypeError: could not convert value for property
'transient_for' from MagicMock to GtkWindow`).

One binding-shape rule prevents the cross-suite flakes that only appear under
`pytest -n auto`: an in-function import of a GUI module must never run bare.
Inside a test or helper, either import under a `mock_gtk()` context (the
suite's own first import establishes the sticky binding), evict the module
with `sys.modules.pop` first, or use `import_gui_fresh`. A bare import binds
whatever the `sys.modules` cache happens to hold — real classes cached by
another suite's decorator-driven import, or a mock copy from another context
— and mixing the two fails in bizarre ways (`AttributeError: Attempting to
set unsupported magic method '__init__'`, `TypeError: isinstance() arg 2
must be a type`). `TestGiImportGuards` in `test_gui_infrastructure.py`
enforces this statically.

### Writing a New Python Suite

1. Create `tests/python/test_<modulename>.py`.
2. Import `unittest` and helpers from `test_support.py`.
3. Define `unittest.TestCase` subclasses.
4. Use `test_support` fixtures for config isolation, log capture, subprocess
   mocking, and GTK mocking.
5. If the suite uses a GTK-dependent module from `python/` without
   `mock_gtk()`, declare it in `tests/requirements.manifest` and guard it:
   `test_support.import_or_skip_gi("<module>")` (with
   `pytestmark = requires_gi`) for module-level imports, or
   `pytestmark = requires_gi` alone for GTK used only inside test bodies.
   A consistency check in `test_gui_infrastructure.py` enforces this.

Minimal example:

```python
import unittest
from test_support import temp_config_dir, capture_logs

import config_core


class TestMyFeature(unittest.TestCase):
    def test_loads_default(self):
        with temp_config_dir():
            cfg = config_core.load_config()
            self.assertIn("pools", cfg)


if __name__ == "__main__":
    unittest.main()
```

### Python Golden Files

The `golden` module (`tests/python/golden.py`) is the Python half of the
golden-file workflow (see "Golden Files" above):

```python
import golden

golden.check(self, step.command)  # list: one element per line
```

`golden.check(testcase, actual, name=None)` resolves the golden as
`tests/golden/<module>/<Class>.<test>.golden` (an explicit `name` overrides
the default) and raises `AssertionError` with a unified diff on mismatch.
With `UPDATE_GOLDEN=1` a differing golden is rewritten and the test is
skipped; identical content passes and leaves the file untouched.

In update mode, updated tests appear as skips; the harness 'skipped' total
then includes golden updates in addition to any environment skips.
Compare-mode skips are environment or marker skips only.

### Python Test Support Fixtures

`tests/python/test_support.py` provides shared infrastructure:

| Fixture | Purpose |
|---------|---------|
| `temp_config_dir()` | Overrides `CONFIG_PATH`, `CRON_FILE`, `SNAPFILE`, `OFFSITE_SNAPFILE`, `SESSION_LOG_DIR`, and advisory-lock paths to a temp directory |
| `mock_subprocess()` | Patches `subprocess.run` with a stateful mock that handles `zfs`, `zpool`, `rsync`, and `ssh` commands |
| `capture_logs()` | Captures `log_msg` output to a list for assertions |
| `capture_stderr()` | Captures `sys.stderr` to a string |
| `mock_gtk()` | Patches `gi.repository` with `MagicMock` so GUI modules import without a display |
| `import_gui_fresh(name)` | Inside a `mock_gtk()` context: evicts *name* and the whole GUI closure from `sys.modules`, then imports — guarantees the module binds to the *current* context's mocks instead of a stale copy cached by another suite |
| `import_or_skip_gi(name)` | Imports a GTK-dependent module at module level, skipping the whole suite cleanly when `gi` is unavailable |
| `requires_gi` | Module-level `pytest.mark.skipif` for suites that use GTK only inside test bodies |
| `check_pyyaml()` | Skips the current test if `pyyaml` is not installed |

### Python Mock Subprocess

The `MockSubprocess` class tracks every call and returns canned output:

```python
from test_support import mock_subprocess

with mock_subprocess() as m:
    m.add_zpool_list([{"name": "tank", "health": "ONLINE"}])
    m.add_zfs_list([{"name": "tank/data", "used": "10G"}])
    # ... code that calls subprocess.run(...) ...
    self.assertEqual(len(m.calls), 2)
```

---

## Integration Tests with Real Pools

In addition to the mock-based bash and Python suites, the repository contains a
small real-pool integration suite:

```
tests/integration/test-zfs-send-receive-pools
```

This suite exercises `bin/zfs-send-receive` against actual ZFS pools. It is kept
separate from `tests/run-tests` because it requires root privileges and
dedicated test pools.

### Required Test Pools

The suite expects two local test pools. Defaults:

- Source: `zfstest1`
- Destination: `zfstest2`

Pool names are configurable via environment variables:

```bash
export ZFSUTILITIES_TEST_SRC_POOL=zfstest1
export ZFSUTILITIES_TEST_DST_POOL=zfstest2
sudo tests/integration/test-zfs-send-receive-pools
```

Only pools in the suite's explicit allow-list (`zfstest1`, `zfstest2`,
`zfstest3`) may be used. The suite refuses to run if a configured pool is not
in the allow-list or is not online.

### Creating Local Test Pools

On the development VM, `/dev/sdb` is a 75 GiB empty virtual disk. It can be
partitioned and used to create three small RAIDZ1 test pools:

```bash
# parted/partprobe are not part of a base Debian install.
apt-get install -y parted

# Create a GPT label and 15 ~5 GiB partitions.
parted -s /dev/sdb mklabel gpt
for i in {1..15}; do
    if [[ $i -eq 1 ]]; then
        start="1MiB"
    else
        start="$(( (i-1)*5120 ))MiB"
    fi
    if [[ $i -eq 15 ]]; then
        end="100%"
    else
        end="$(( i*5120 ))MiB"
    fi
    parted -a optimal -s /dev/sdb mkpart primary "${start}" "${end}"
done
partprobe /dev/sdb

# Create three RAIDZ1 pools.
zpool create -f zfstest1 raidz1 /dev/sdb1 /dev/sdb2 /dev/sdb3 /dev/sdb4 /dev/sdb5
zpool create -f zfstest2 raidz1 /dev/sdb6 /dev/sdb7 /dev/sdb8 /dev/sdb9 /dev/sdb10
zpool create -f zfstest3 raidz1 /dev/sdb11 /dev/sdb12 /dev/sdb13 /dev/sdb14 /dev/sdb15
```

Each pool reports roughly 24.5 GiB of raw space, yielding about 20 GiB of
usable space after RAIDZ1 parity. The integration suite still sets
`space_check_min_buffer=0` for its normal scenarios to keep the existing small-
transfer logic path. The space-check scenario itself verifies the skip behavior
by setting an artificially large buffer.

### Running the Integration Suite

```bash
sudo tests/integration/test-zfs-send-receive-pools
```

The suite skips cleanly with a stated reason when named via the harness on a
machine that lacks root or the test pools:

```bash
tests/run-tests tests/integration/test-zfs-send-receive-pools
# SKIPPED (missing: root test-pools) (test-zfs-send-receive-pools)
```

The suite:

- Skips cleanly with a message if not run as root.
- Validates pool names against the allow-list.
- Creates uniquely named test datasets for each scenario.
- Uses `trap` to destroy all test datasets on success and on failure.

After a run, verify that no test datasets remain:

```bash
zfs list -r zfstest1 zfstest2
```

### Scenarios Covered

| Scenario | What it exercises |
|----------|-------------------|
| Full copy to empty destination | `doincrementals='N'` two-step transfer: full copy of oldest snapshot + incremental catch-up to target |
| Incremental copy with common snapshot | `doincrementals='Y'` with `dointermediates='Y'` |
| Incremental copy without intermediates | `doincrementals='Y'` with `dointermediates='N'` |
| Destination rollback | `handle_commsnap_rc` rc=16 with `autoproceed='Y'` |
| Resume token handling | Partial receive leaves a token; re-run resumes and completes |
| Space check skip | Large `space_check_min_buffer` causes skip |
| Clone dataset copy | Clone replicates as an independent dataset |

## Integrated End-User Testing

Beyond the mock-based suites and the real-pool integration suite above,
the repository includes an orchestrator (`tests/integrated/itf`) that
exercises the product as a first-time end user on disposable nested
guests in the base Proxmox test VMs — fresh install from a release or
dev tarball, install-over-leftovers, uninstall/reinstall, the two-node
install across a storage guest and a PVE-from-ISO compute guest on
separate base hosts, and installer failure paths (declined
prerequisite remediation, apt breaking mid-remediation) — under a
strict confinement guard for the base hosts, with `journey run
--rerun` replaying on the previous run's guests for fast re-verify
loops.  See
[Integrated Testing](integrated-testing.md) and
`tests/integrated/README.md`.

## Tips and Gotchas

### Bash

* **Log redirection** — `log_msg` output is redirected to a per-test log file by
`test-lib.sh` so the harness stays quiet.  Tests that need to assert on
`log_msg` output should read the file returned by `get_test_log_file()` (or
use `get_stderr_log()` from `test-zfs-send-receive-dryrun`).
* **Automatic `/tmp` cleanup** — every suite's per-PID artifacts
(`/tmp/zfsutilities-test-<pid>.log` and `/tmp/mock_zfs_state_<pid>`) are
removed by an exit trap when the suite process ends.  A suite that failed or
crashed keeps its log for post-mortem (the path is printed on stderr when it
is retained); green runs leave nothing behind.  A suite killed through an
untrapped signal cannot run its exit trap, so sourcing `test-lib.sh` also
sweeps away any `mock_zfs_state_<pid>` directory whose owning process is
gone — signal-killed runs cannot accumulate litter.
* **Exit cleanup composes** — suites or scripts that need their own exit-time
cleanup must register it with `append_exit_trap '<command>'` (from
`bashinit`), never a bare `trap '<command>' EXIT`, which would silently
discard everything registered earlier in the same shell.  `zfslock_init`
already registers its lock release this way.
* **Root check** — [rootcheck](../commands-and-modules/modules.md#rootcheck) is mocked to a no-op.  Any future suite that
legitimately requires root should check `$EUID` and call `test_skip` when
non-root.
* **Inner functions** — Functions defined *inside* another function (e.g.
`check_space_available` inside `send-receive`) become available for direct
testing **after** the outer function has been executed once.
* **Bash array scope** — Always declare and assign arrays on one line:
  `local arr=($@)`.  Splitting `arr=($@); local arr` can create an empty
array in bash 5.2.
* **Snapshot existence** — The `zfs list -t snapshot <name@snap>` mock returns
exit code 1 when the snapshot is not present in `_mock_zfs_snaps`, so scripts
that test existence with `! zfs list ...` work correctly.
* **Combined short options** — The mock parses `-Hp` as combined flags, so
`zfs get -Hp -o value available pool` resolves the property and dataset
correctly.

### Python

- **Clear stale bytecode as a wrap-up practice.** `__pycache__` directories
are gitignored artifacts that Python regenerates on demand, but stale `.pyc`
files (for example a cache left behind by a renamed or deleted suite) can
cause phantom import or test behavior. Periodically removing all
`__pycache__` directories — a good development-cycle wrap-up step before the
final full test run — keeps the caches honest; the suite run regenerates only
what it needs.
* **Config isolation** — Always wrap config-mutating tests in
`temp_config_dir()` so they do not touch the real `/var/lib/zfsutilities/config.json`.
* **GTK mocking** — Use `mock_gtk()` as a context manager when importing any
module that touches `gi.repository.Gtk`. The mock provides enough structure
for `Window` subclasses to instantiate without a display.
* **Memory footprint** — Each pytest-xdist worker peaks at roughly 600-900 MB
(the full serial layer peaks under 1 GB). `tests/run-tests` caps the worker
count by `MemAvailable` (banner line `pytest-workers=N`; override with
`ZFSUTILITIES_PYTEST_JOBS=N`) so a full run cannot crowd a desktop browser
into an OOM kill. If a run dies to the OOM killer anyway, check for leftover
trees first: interrupting the harness terminates its pytest tree, but runs
started directly with `pytest -n` leave nothing to clean up either — an
`execnet` worker exits when its controller dies.
* **Subprocess in background** — Some code spawns subprocesses with `&`.
Capturing output from a mock requires writing to a temp file from the mock
function and calling `wait` before reading it back.
* **Log capture** — `capture_logs()` intercepts `backup_config.log_msg()`
output. It works for both Python modules and bash scripts invoked via
`subprocess.run` because the bash `log_msg` writes to stderr, which can be
captured separately with `capture_stderr()`.
* **Linting** — Run `ruff check .` from the repository root before committing
Python changes. The Ruff configuration is in `pyproject.toml`.
