# Glossary

Items to add:
    acls
    LIO
    DEL
    cast
    Phase-4 precedent
    idiom

Plain-language definitions of terms as they are actually used in this
repository — in agent work reports, SESSION_NOTES.md, CI output, and the
docs. Entries are added alphabetically as jargon comes to light, without
waiting for a request; a term belongs here the moment a report has to
pause to explain it.

## autoinstall

Ubuntu's unattended-installer format: a `#cloud-config` file (plus a
companion `meta-data` file) that answers every installer question in
advance. The itf ubuntu template profile uses one instead of a Debian
preseed — the seed pair is served over the same dev-side HTTP server and
the boot ISO points the installer at it (`ds=nocloud-net`). The Debian
equivalent is a preseed; Proxmox uses its own answer TOML.

## capped table window

Every treeview table in the GUI sits in its own scrolled window that
sizes to its rows: the window grows with the data up to 20 visible rows,
then stops growing and scrolls inside instead, while an empty table
keeps a small header-only floor. The shared helper is
`gui_helpers.capped_treeview_scroll`; the one-row allowance past the
target absorbs a classic horizontal scrollbar so the 20th row stays
visible. A caller can instead pin a constant window
(`fixed_rows=True`), but every shipped table uses the natural-sizing
default.

## CI

Continuous Integration: the GitHub Actions pipelines that automatically
build and test every push. For this project, CI runs the lint checks and
the test suites on GitHub's `ubuntu-latest` runner as the unprivileged
`runner` user. CI differs from the development desktop in ways that
matter: it installs a newer pytest, and it lacks the desktop's root-owned
leftover files — so some failures appear only on CI ("CI-only failures"),
and CI flakes can resist being reproduced locally (the 2026-10-31
dashboard TTL-cache flake was fixed green without a local failure ever
being produced). A "CI run" is one execution of the pipeline. Rerunning a
failed job is normal triage, but the run recorded at a release tag is
never redone or moved — "the tag run stays red by rule," because tags are
history.

## config version

The saved configuration file (`/var/lib/zfsutilities/config.json`)
carries a `config_version` number: the generation of its JSON schema.
Every release that changes the saved-config structure ships a migration
in `python/config_migrations.py` and bumps `CONFIG_VERSION`. Migrations
run automatically, forward only — an older file is upgraded on load; a
newer one is never downgraded. The warning

    WARN: Config version 31 is newer than software expects (30).
    Some features may not work correctly.

means the saved config is newer than the running software: something
newer already ran on this host and saved the config, and older software
is now reading it — classically after a rollback (here: the config was
migrated to generation 31 by 0.136.0-era software, then the host ran a
generation-30 release again, so every GUI start warned). It is a
warning, not a failure: the software still starts, and keys it does not
know ride along in the file unharmed (the 30→31 migration only dropped
two dead restore-page keys, which older releases tolerate). It stops
appearing once the software is again at least as new as the config.
Since the archive mechanism landed, the config loader preserves the
pre-migration state of every generation under `config-archive/`, and
`switch-version` restores the matching archive on a rollback instead of
letting the mismatch happen.

## controlled reboot

The planned, one-time reboot of stewie (the storage node) that closes out
the 2026-10-27 iSCSI boot-incident hardening campaign. The label is the
campaign's own — it appears nowhere in the code; the authoritative step
list is the "Corrected exercise sequence" file. In brief: deploy the
current release to both hosts first (the precondition); refresh the
recovery authorities with `sudo safe-iscsi-save`; reboot once; expect the
boot journal to log "post-restore verification FAILED" with DRIFT lines
naming vm-101-disk-1 and vm-202-disk-5 (normal until the encryption keys
load); converge within the same boot (load keys →
`sudo iscsi-recover-encrypted-luns` → `sudo export-iscsi-state --check`
returning success); Dashboard shortfall rows clear. The exercise proves
the 2026-10-27 incident class — the node silently coming up with 3 of 33
LUNs mapped while every gate passed — is dead: nothing silent, nothing
destroyed, one clean recovery.

## dp module identity

A debugging phrase from the 2026-10-31 CI flake investigation. `dp` is
the shorthand variable name the Python test suites use for a page module:
`dashboard_page` in test_dashboard_page.py (and the same shorthand names
`disks_page` in that page's own suite). A module's "identity" is which
in-memory module object the name resolves to. If the same module ends up
imported twice in different states — once with the real GTK, once under
the mocked GTK context — there are two separate module objects, each with
its own module-level caches, and a cache-related test can pass or fail
depending on which object it sees. The diagnostic in
`test_failure_is_not_cached` prints the dp module identity alongside the
cache contents precisely so that a dual-module-instance cause would be
visible there.

## drift

Divergence between two things that are supposed to match. The boot
verifier prints DRIFT lines when the live iSCSI LUN mappings differ
from the pool-resident state map; the pool-identity fence warns when a
pool's GUID changed under the same name; config drift is a saved config
whose shape no longer matches what its version stamp promises. Drift is
an observation, not itself an error — each fence decides which drift is
fatal, which warns, and which is by design (a one-sided pool name is
deliberately not drift).

## fence

In the iSCSI two-node setup, the fence is the systemd service and timer
(`zfsutilities-iscsi-fence.service`, a 5-minute tick on the compute
host) that watches the storage link: when the node cannot reach its
iSCSI storage, the fence isolates it so a half-connected compute node
cannot corrupt shared state. The Dashboard reports a failed fence as a
warning row. More generally, reports use "fence" for any structural
barrier that keeps an unsafe condition from causing harm unattended — a
private Xvfb display fencing tests off the real desktop, a gate fencing
a degraded write. The house rule: fences rank above protocols; safety
must hold when nobody is watching.

## full unit gate

Running the complete unit-tier test gate — every suite, not just the
ones affected by the current change — via `tests/run-tests`: all bash
suites (`tests/test-*`) plus the whole Python pytest leg
(`tests/python/`), with the long-running `*-soak` timing suites skipped
by default and included only with `--with-soak`. The phrase compresses
three house rules (tests/AGENTS.md): iterate on affected suites only,
never debug against a full run, and run the full gate once, at the end,
before reporting. A "gate" generally is any check that must pass before
work counts as done — lint (ruff, shellcheck), docs integrity, and the
test suites; the release gate is the full run plus `--with-soak`. The
unit tier is distinct from the integration tiers: `tests/integration/`
(root-gated, real pools) and `tests/integrated/` (journey guests), which
run for their own reasons, not as part of the unit gate.

## gate

A check that must pass before something is allowed to happen. Gates
refuse rather than warn: safe-iscsi-save compares live iSCSI mappings
against the expected-backstores manifest and refuses to write on a loss;
switch-version's config-generation gate refuses a downgrade it cannot
do safely; lint, docs integrity, and the test suites gate a release.
The 2026-10-27 boot incident happened because every gate passed while
counting the wrong thing (backstores instead of LUN mappings) — which is
why gates are red-proofed (temporarily disabled to prove their tests
actually fail) and authority-keyed (compared against the manifest/map,
not raw counts).

## green

Passing. A suite, run, or CI check is green when every test in it passes
(zero failures); the opposite is red. Typical usage: "full suite green,"
"CI fixed green." One caution travels with the word: in the bash suites a
failed test can display a misleading verdict line, so the failure count —
not the displayed verdict — is the truth.

## GUI

The GTK3 graphical application for managing backups, snapshots,
retention, disks, iSCSI, and their dashboards:
`python/zfsutilities_gui.py` plus the page modules in `python/`. It
always runs as root (`sudo`), because every operation targets live ZFS
pools. In the test suites the GTK layer is faked with the `mock_gtk`
context so GUI code can be tested headless, and the one realized-window
check runs under a private Xvfb display.

## mock

A stand-in that imitates a real dependency during tests, so suites can
run without root, real pools, real iSCSI, or a display. The project's
principal mocks: `mock_gtk` (fake GTK widgets), `MockSubprocess`
(scripted `zfs`/`zpool`/`targetcli` responses), and the node-lib mocks in
the bash suites. The standing rule is mock fidelity: a mock must model
the real tool's actual behavior, because an unfaithful mock lets tests
pass vacuously — green while proving nothing.

## oracle

The authoritative source a check or exercise is judged against — the
answer key. When reports say "the oracle is the user's Corrected
exercise sequence file," they mean the controlled-reboot exercise is
verified against that file's steps, not against a summary or memory.
Distinguished from a mock (which fakes a dependency for testing): an
oracle defines truth for a verification.

## property manifest

A small file recording one dataset's locally-set ZFS properties, captured
next to the backup after the transfer verifies (`lib/property-manifest-lib.sh`).
Backups send property-less `-cw` streams, so compression, recordsize,
`keylocation`, user properties and friends would otherwise never reach the
backup; the manifest is the sidecar that carries them for replay at
restore. One file per dataset per generation, named
`<dataset with / → %2F>@<snapname>`, stored on a dedicated filesystem
(`<destfs>/<source pool>/zfsutilities-manifests`) that is snapshotted
under the same generation snapname as the data — so ordinary retention
prunes it in lockstep. The store also travels: offsite onward legs carry
it to the offsite pool as an ordinary dataset (capture stays off — copies
hold no local properties), and replay finds it by probing the deeper
offsite-hop shape before the direct backup root. Excludes what the raw
stream already carries (the encryption family, `volblocksize`);
`keylocation` is deliberately kept.

**Replay** is the restore-time half: after the transfer, `zfsreplayprops`
(shared by `zfsrestore`, the GUI restore payload, and `zfsrestoresendstream`'s
`.props` siblings) verifies the manifest (header, dataset, sha256) and
re-applies each property with `zfs set` — a `file://` keylocation
additionally gets a best-effort non-interactive `zfs load-key`. Everything
about replay is WARN-only: a missing, stale, or corrupt manifest never
fails a restore; the dataset simply keeps its inherited defaults.

## probe

A small scripted live check of one ZFS behavior, run inside a test guest
and judged against a version-keyed expectation — pass/fail, never
best-effort. The j21-zfs-probes journey runs seven of them (the "probe
matrix") across the three baseline templates to measure the OpenZFS
behaviors the backup engine's design rests on; `probes.tsv` in the run
report is the recorded outcome. Unrelated to the GUI's guest-filesystem
probe (the Alignment view's validator, journey j06).

## receive as encrypted

Receiving an UNencrypted backup stream into a dataset created encrypted by
the receive itself — `zfs receive -o encryption=on -o keyformat=raw -o
keylocation=file://…` on the initial receive only (the Restore tab's
*Receive as encrypted* option). The restored dataset becomes its own
encryption root wearing the given raw key; already-encrypted sources are
skipped automatically because raw streams refuse encryption-family `-o`
overrides. Works on every OpenZFS release in the fleet, so no capability
entry is needed. See "Receiving a Restore as Encrypted" in the user guide.

## receive family

The capability-table entries that describe `zfs receive` behavior
(`recv_o_volblocksize` is the first). They are gated on the SMALLER of
the userland and kernel-module versions, because `zfs receive` runs in
userland while the effect lands in the kernel module — a split stack
(one half old, one half new) must clear the bar on both sides. See
`RECEIVE_FAMILY` in `python/zfs_capabilities.py`.

## shape

Report shorthand for the exact pattern or structure of a thing. An output
line's shape is its columns and format. A failure's shape is which
symptoms appear in which combination — "the 3/33 incident shape" means 33
backstores defined, only 3 LUNs mapped, and every count gate green. A
config's or a systemd unit's shape is its fields and their structure.
Claims about a shape are usually pinned by a fixture or a regex, so the
pattern cannot drift silently.

## suite

One named group of tests. Bash suites are `tests/test-*`; Python suites
are `tests/python/test_*.py`; the special gates (docs integrity, the soak
leg, the integrated journeys) are suites too. The "affected suites" of a
change are the ones covering the files it touched. House rule (root
AGENTS.md): during iteration run only the affected suites; run the full
suite once, at the end — the full gate is `tests/run-tests`.

## TPG

Target Portal Group: the container inside an iSCSI target (LIO/
targetcli) that holds the LUN mappings and the ACL initiator grants.
In practice every target in this setup has exactly one (TPG 1), so
"the TPG's mappings" means the target's complete LUN map — the thing
the safe-iscsi-save gate compares against the expected-backstores
manifest, and the thing the 2026-10-27 incident silently lost (33
backstores defined, only 3 mapped, because the gates counted
backstores instead of TPG mappings).

## TCG

Tiny Code Generator: QEMU's software CPU emulator — the fallback that
runs a virtual machine entirely in code when hardware virtualization
(KVM) is unavailable. The integration-test lab nests Proxmox inside its
guests with no /dev/kvm passthrough, so every lab VM boots under TCG
("a TCG boot", `kvm=0`): much slower than KVM but faithful, which is
why lab boot proofs are timed generously and judged by behavior, not
speed.

## TTL

Time-to-live: how many seconds a cached result stays valid. The GUI wraps
expensive scans in TTL caches — Dashboard's disk-wear, iSCSI LUN, fence,
and pool-identity checks at 300 s; the disk inventory; guest filesystem
probes at 600 s — so the periodic auto-refresh does not rescan everything
each tick, and ssh-based checks stay within their churn budgets. Failures
are never cached, and repair paths reset or bypass the cache so the UI
shows fresh state. "The TTL flake" is the CI-only failure class where a
leaked real refresh thread outlived a test and wrote a stale entry into a
cache the next test read.
