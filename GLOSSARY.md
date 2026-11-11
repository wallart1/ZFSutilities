# Glossary

**Items to be added by Zcode:**
    rid-suffixed datasets


Plain-language definitions of terms as they are actually used in this
repository — in agent work reports, SESSION_NOTES.md, CI output, and the
docs. Entries are added alphabetically as jargon comes to light, without
waiting for a request; a term belongs here the moment a report has to
pause to explain it.

## ACL

Access Control List. In this repository the word almost always means
the iSCSI kind, not filesystem permissions: inside each target's TPG,
LIO keeps a per-initiator ACL that admits one compute node — identified
by its IQN — and says which LUNs it may see, the "mapped LUN" grants
(reports say "ACL MappedLUN" for the grant and "TPG LUN mapping" for
the export itself). The distinction is load-bearing in the
boot-incident work: `iscsi-recover-encrypted-luns` originally rebuilt
TPG LUN mappings but never ACL MappedLUNs, so a recovered node could
come up with LUNs mapped yet no initiator granted; recovery now
rebuilds both, the pool state map (version 2) records every grant —
initiator, mapped LUN, LUN — so reconcile and the boot verifier can
restore and check them exactly, losing a still-expected grant is
refused (FATAL) never silently remapped, and `safe-iscsi-save`'s
authoritative gate compares every old mapping and grant before any
write. ZFS filesystem ACLs exist too (`acltype` and friends — a
locally-set one simply rides the property manifests like any other
dataset property), but nothing in the repository manages them directly.

## autoinstall

Ubuntu's unattended-installer format: a `#cloud-config` file (plus a
companion `meta-data` file) that answers every installer question in
advance. The itf ubuntu template profile uses one instead of a Debian
preseed — the seed pair is served over the same dev-side HTTP server and
the boot ISO points the installer at it (`ds=nocloud-net`). The Debian
equivalent is a preseed; Proxmox uses its own answer TOML.

## backstore

LIO's named handle for a block device it serves over iSCSI — the
`/backstores/block/<name>` entry pointing at a zvol's `/dev/zvol/...`
device. The VM-disk tooling here creates them named `vm-<id>-disk-<n>`,
but the name is only a birth label: which device a backstore serves is
the truth. The busy resolver matches exports by device and never by
name, so a renamed or reused backstore cannot drag the wrong dataset
into a diagnosis.

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
boot journal to log "post-restore verification PENDING" with DRIFT lines
naming vm-101-disk-1 and vm-202-disk-5 (normal until the encryption keys
load; the encrypted-aware verdict since repair plan 027 — an every-boot
expected FAILED trained operators to ignore the verifier, so keys-pending
drift now journals PENDING and FAILED is reserved for unexpected drift);
converge within the same boot (load keys →
`sudo iscsi-recover-encrypted-luns` → `sudo export-iscsi-state --check`
returning success); Dashboard shortfall rows clear. The exercise proves
the 2026-10-27 incident class — the node silently coming up with 3 of 33
LUNs mapped while every gate passed — is dead: nothing silent, nothing
destroyed, one clean recovery.

## dataset action

A GUI operation that mutates pools or datasets — destroy, sever clone,
rewrite data, apply profile, create/grow/maintain/migrate a pool, wipe
labels, enroll a pool. Each one runs on its own runner, and more than one
may be in flight at a time; what serializes them is the
[dataset lock](#dataset-lock) each one takes, not a shared queue. When a
dataset action collides with another operation, its confirmation is
refused with a warning that names the lock's holder.

## dataset lock

A reservation on a pool, dataset, or snapshot that serializes ZFS
operations across everything the project runs — GUI actions, backups,
offsite transfers, scrubs. Locks live as small JSON files under
`/run/lock/zfsutilities/`, shared between the Python GUI and the bash
tools, with three types: read (`r`), write (`w`), and destroy (`x`). They
are hierarchical: a write lock on a pool root blocks write actions on
every dataset below it, so an offsite transfer receiving into a pool
fences mounting inside that pool until it finishes. When an action is
refused because another operation holds the lock, the Datasets page
names the holder in a warning dialog instead of failing silently.

## deferred destruction

`zfs destroy -d`: marks a held snapshot for deletion instead of
destroying it now — it disappears by itself once the last hold on it is
released. The busy resolver offers this as its safe default for
deliberate hold tags: no hold is released by the tool, and the hold's
owner keeps control until they let go.

## DEL

One of the three change classifications `upgrade-zfsutilities` prints
when comparing the deployed tree against the baseline manifest
(`upgrade_lib_classify` in the upgrade library): **MOD** — the file
exists in both but differs; **ADD** — new in this version; **DEL** —
the new version deletes it, so the upgrade removes it from the deployed
tree (behind the usual safety checks). The baseline is *captured* on
the first upgrade over an unmanaged tree (trust-on-first-upgrade,
FINDINGS F-025: pre-existing local modifications are absorbed, not
flagged); later upgrades scan against it and offer to salvage local
content. The rule the j19-baseline-capture journey taught: a DEL anchor
must be a file inside a deployed tree — deploy-version copies `bin/
lib/ python/ docs/ share/ VERSION` only, so a repo-root file
(README.md) can never be the deleted file, while a docs/ file can. The
upgrade ITF journeys exercise the classification live.

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

## exit-status bits (smartctl)

smartctl's exit status is a bitmask, not a single error code: each bit
names one finding (8 = the disk is failing, 32 = the error log holds
entries, 64 = self-test errors, and so on). A nonzero exit therefore
often *accompanies* a full report rather than replacing it, so the
project gates on whether smartctl printed output and uses the exit
status only to explain it — the SMART Details warning names the set
bits ("error-log entries (rc=32)") instead of hiding the report behind
the nonzero code.

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

## full gate

Short form of [full unit gate](#full-unit-gate), the phrase reports use
("the full gate is green") for the complete unit-tier run — every suite
via `tests/run-tests`, soak suites excluded unless `--with-soak`. When a
report says full gate, nothing was cherry-picked: the whole unit tier
ran, at the end, before reporting, per the house rules in
tests/AGENTS.md.

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

## function survey

The j22 journey: a randomized sweep over the end-user-visible
functions. Each run draws a fresh random sample of at least half the
sampling universe, shuffles the order, archives the list, and executes
every item with full logging — CLI commands from the tree under test
and GUI operations driven through the real window. Repeated runs
explore different corners of the surface; the sample archive makes any
single run exactly repeatable.

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

## guest agent (QEMU guest agent, qga)

The small service (`qemu-guest-agent`) inside a VM that lets the
hypervisor ask the guest questions — for this project, the guest
filesystem block sizes behind the Blocksize Alignment view
(`alignment_guestfs.py` asks through `qm guest cmd <vmid> ping` /
`qm guest exec`).
Three separate conditions get confused under one label: the VM's PVE
config lacking the `agent:` line ("not configured"), the service not
answering ("not running"), and the VM being stopped — the classifier
names them separately, and a failed probe logs PVE's raw stderr so the
real cause survives. On the compute node the channel shows up as a
`<vmid>.qga` socket plus a `virtio-serial` bus on each VM's `kvm`
command line.

## GUI

The GTK3 graphical application for managing backups, snapshots,
retention, disks, iSCSI, and their dashboards:
`python/zfsutilities_gui.py` plus the page modules in `python/`. It
always runs as root (`sudo`), because every operation targets live ZFS
pools. In the test suites the GTK layer is faked with the `mock_gtk`
context so GUI code can be tested headless, and the one realized-window
check runs under a private Xvfb display.

## hold tag

A named bookmark placed on a snapshot (`zfs hold`) that refuses its
destruction until someone releases it by name (`zfs release`). The
backup rules here place product holds (`offsite-*` and friends) through
zfshold so retention stays honest. The busy resolver classifies the
tags it finds into deliberate holds (never released by the tooling) and
`.send-*` cancelled-transfer leftovers (safe to release on
confirmation).

## idiom

A recurring, recognized code pattern that other work reuses by
reference: "the datasets-page idiom," "the scroll save/restore
idiom," "the workload-profile dialog idiom" each mean "build it the
way that existing surface does" — the named page is the reference
implementation. House style now uses the word sparingly in agent
reports (name the pattern plainly instead), but the developer docs
still use it freely.

## IQN

iSCSI Qualified Name — the unique permanent name every iSCSI
participant answers by: each initiator (the compute node logging in)
carries one from `/etc/iscsi/initiatorname.iscsi`, and each target
carries one built from the site's `IQN_PREFIX`
(`iqn.<year>-<month>.<domain>:<label>`). The two-node installer
derives both from node.conf, and the pool state map records ACL
initiators by IQN name — which is why a rebuild must re-grant by that
exact name (the grant dimension, map schema version 2) and why a
renamed initiator shows up as drift rather than silently losing its
LUNs. Report phrases: "the initiator IQN," "IQN prefix mismatch."

## keys pending

The posture of an encrypted LUN whose key is not loaded — on this
project, specifically after a storage host reboots without its key
device: the plain LUNs keep serving, the encrypted LUN's backstore is
not restored (the boot journal records PENDING), and the pool state
map classifies it keys-pending. Nothing may read the encrypted device
while pending (the read stalls for hours against the dead target), and
the upgrade path must not write iSCSI state — the pool map stays the
recovery authority until the key ceremony. j25 exercises the whole
posture.

## LIO

Linux-I/O target: the Linux kernel's built-in iSCSI target subsystem —
the thing that actually serves this project's zvols to the compute
node over the storage network (on this site, stewie serves the
zvol-backed LUNs through LIO and tweety's VMs log into them).
`targetcli` is its management shell over rtslib-fb,
`/etc/rtslib-fb-target/` holds its saved configuration (saveconfig,
refreshed only under `safe-iscsi-save`'s loss-refusing gate), and the
"LIO tree" is its live configuration of targets, TPGs, backstores,
and LUN mappings. Nearly every iSCSI feature here — the state map,
reconcile, the boot verifier, the safe-save gate — reads or rebuilds
the LIO tree; the test journeys' "LIO total loss" scenarios exercise
losing it entirely. Report phrases anchored here: "LIO holds the
zvol" — while a zvol is exported, ZFS destroy answers `dataset is
busy` (holds before destroy); "concurrent LIO mutators" — anything
else editing the target config while repo tooling runs; "LIO portals
are host-level sockets" — the `0.0.0.0:3260` wildcard binds
`INADDR_ANY:3260`, and while any TPG rides it, no specific `:3260`
portal can be created.

## load-bearing

Report adjective for a thing other things silently depend on: remove
or break it and nothing complains immediately — the failure surfaces
much later, somewhere else. "Load-bearing comment" (the comment a
future edit must read to keep a subtle invariant), "load-bearing
record" (the run-tagged guest records: the invariant that a run dir
with guest records is a lab that may still exist is exactly what
`--rerun` sourcing and the orphan fence rely on — the verdict-time
teardown deletes records only together with their guests), "the
distinction is load-bearing" (ACL entry: mapped-LUN grants vs TPG
mappings). Spotting one is a wrap-up finding in itself.

## loop device

A pseudo block device the kernel binds to a file or another block
device (`losetup`). The Datasets page uses one to make a ZFS volume
mountable: **Mount** on a volume attaches its `/dev/zvol/...` device to
a read-only loop device with partition scanning, and the volume's
partitions then mount read-only under `/mnt/zfsutilities/...`. The
attach is read-only on purpose — these volumes are often live VM disks
served over iSCSI. **Unmount** on the volume row unmounts every
partition by device (an exact-layer `umount`, so a foreign mount stacked
on a partition's mountpoint is never touched) and then detaches the
loop device.

## LUN

Logical Unit Number — a numbered export slot inside an iSCSI target.
In this project every LUN is a zvol: the storage node serves
`vm-<vmid>-disk-<n>` zvols through LIO, and the compute node's VMs
see them as SCSI disks after logging in. Two numbers ride the word:
the **TPG LUN** (the mapping inside the target — export slot N is
backstore X) and the **mapped LUN** (the ACL grant — initiator Y may
see target LUN N as its local LUN M); they differ whenever a grant is
non-identity (mapped 8 → TPG 0, the case that made the map's grants
dimension necessary). The safe-save gate compares LUN mappings, not
backstore counts, precisely because the 2026-10-27 incident passed
every count gate with 33 backstores defined and only 3 LUNs mapped.

## message-level gate

A filter on what a script prints to the terminal, set with the
`ZFSUTILITIES_MSG_LEVEL` environment variable (`DEBUG`, `VERB`, `INFO`,
`WARN`, or `FATAL`). Messages below the chosen level stay off the
terminal; the session log still records every message. `archive-vm` runs
its helper scripts under a `WARN` gate, so an archive run prints its own
step-by-step narrative and the helpers speak only when something is
wrong. Unset (the default), every message prints.

## meta package

A package whose only job is to depend on the current version of
something, so installing it always pulls the latest matching piece. The
prerequisite checker remediates a missing ZFS kernel module with
`linux-headers-amd64` (the headers meta package) rather than one
kernel's headers: the meta tracks every future kernel, so a routine
`apt full-upgrade` lands the new kernel's headers automatically and
`zfs-dkms` rebuilds the module on its own.

## mock

A stand-in that imitates a real dependency during tests, so suites can
run without root, real pools, real iSCSI, or a display. The project's
principal mocks: `mock_gtk` (fake GTK widgets), `MockSubprocess`
(scripted `zfs`/`zpool`/`targetcli` responses), and the node-lib mocks in
the bash suites. The standing rule is mock fidelity: a mock must model
the real tool's actual behavior, because an unfaithful mock lets tests
pass vacuously — green while proving nothing.

## mount namespace

Each process on Linux sees mounts through a namespace: containers
(Docker, LXC, systemd units with `PrivateMounts`) get their own, so a
dataset can be mounted inside a container while the main namespace —
and every "who has this file open" tool run from it (`fuser`, `lsof`)
— reports nothing. That is the classic shape behind a "dataset is
busy" refusal with an empty `lsof`: the busy-resolver's report names
the holding pid and its mountpoint (found by scanning
`/proc/*/mounts`), and never touches the container itself.

## oracle

The authoritative source a check or exercise is judged against — the
answer key. When reports say "the oracle is the user's Corrected
exercise sequence file," they mean the controlled-reboot exercise is
verified against that file's steps, not against a summary or memory.
Distinguished from a mock (which fakes a dependency for testing): an
oracle defines truth for a verification.

## Phase-4 precedent

Report shorthand for citing an earlier campaign phase that already
settled a question, as the established way to do it now. The phrase is
campaign-relative (several campaigns had their own Phase 4), but the
one usually meant is the concurrency campaign's Phase 4, shared-state
file locking: every shared JSON/state file got one advisory `flock`
lock file, with Python's `fcntl.flock` and the bash `zfsconfig`
helper interoperating on the same locks ("Resolved by Phase 4" in
`concurrency-collisions.md`). Following the Phase-4 precedent for a
new shared file means giving it its own lock file on that pattern
rather than inventing a new scheme.

## pickling

Python's `pickle` serialization, which `multiprocessing` uses to hand
worker closures and bound methods from the test process to its child
processes. The word appears in reports almost always in the failure
"cannot pickle": a worker target defined as a nested closure or a
bound method serializes fine under the classic **fork** start method
(children inherit memory; nothing is pickled at all) but not under
**spawn**/**forkserver** (children are fresh interpreters, so the
target must pickle). Python 3.14 made forkserver the default, which is
why several suites now pin the fork start context explicitly — the
pickling constraint is about the process model, not the test logic.

## probe

A small scripted live check of one ZFS behavior, run inside a test guest
and judged against a version-keyed expectation — pass/fail, never
best-effort. The j21-zfs-probes journey runs seven of them (the "probe
matrix") across the three baseline templates to measure the OpenZFS
behaviors the backup engine's design rests on; `probes.tsv` in the run
report is the recorded outcome. Unrelated to the GUI's guest-filesystem
probe (the Alignment view's validator, journey j06).

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

## pv

A standard terminal tool (`pv`, "pipe viewer") that shows transfer
progress — bar, percent, elapsed time, ETA, rate, bytes — for whatever
flows through it. This repository uses it as a display-only pipeline
stage: `zfs-send-receive` (via `lib/transfer-lib.sh`) and the archive
engine (`lib/archive-engine.sh`) put `pv` between the data source and the
writer so a long transfer shows a live, single updating line. Two house
laws govern it. Display only: `pv` never rate-limits here — pacing is
`lib/pace_stream.py`'s job (`pv -L` bursts after stalls and was removed).
Terminal only: `pv` writes to stderr, never through `log_msg`, so
progress never grows the session log; a run without a terminal shows no
progress line at all.

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

## recurrence fence

The installer guard that keeps a site's iSCSI target namespace from
forking on a reinstall: when `install-two-node` runs on a host that
already has live LIO targets, the IQN-prefix prompt defaults to the
prefix those targets already use (read live from `targetcli /iscsi
ls`), not to a fresh date-derived one. Without it a recovery install
could default to a new prefix and silently strand the old targets —
LUN tooling would look under the new prefix while Proxmox keeps
logging into the old ones. Born from the 2026-10 production incident;
first exercised on the reinstall path by the j24 journey (uninstall,
then reinstall over the untouched live targets).

## relabel mode

The itf upgrade-staging mode (`itf_journey_stage_upgrade_env
--relabel`) for a lab installed from the tree under test: the served
"latest release" is that same tree re-labeled one patch newer, so an
interrupted deploy targets a `versions/<v>` directory that exists on
no host and the partial-dir checks stay deterministic. Dev-tarball
source only — real GitHub cannot be re-labeled. j25 runs on it; j23's
pass 2 uses the same re-label stage.

## response profile

The per-item answer style a function-survey run applies to every prompt
it meets: **accept** (yes/OK — the mutation really happens, then is
asserted), **decline** (explicit no), **cancel** (dismiss the dialog or
cancel the runner), or **invalid** (garbage input that must be refused
without effect). Profiles are drawn from the seeded random stream and
stored in the sample archive, so a replay reproduces the same scenario
choices. The wrap-up reports the distribution as evidence that runs
exercise varied scenarios instead of one constant safe default.

## resume token

The handle OpenZFS leaves on a dataset after an interrupted
`zfs receive` — a token that lets the receive continue where it stopped
instead of restarting from scratch. While one is outstanding the
dataset cannot be destroyed ("dataset is busy"); `zfs receive -A`
discards the token together with the partial data. The busy resolver
offers exactly that, as a destructive choice with a safe default.

## run dir

The product's runtime-state directory, `/run/zfsutilities` by default
(override with `ZFSUTILITIES_RUN_DIR`). It lives on tmpfs, so its
contents vanish at reboot: snapshot-name markers, the scrub state
file, the GUI's pid file, and sever-vm-clone's transfer scratch all
belong there precisely because a crash-leaked leftover disappears at
the next boot instead of littering disk. Tools re-create the directory
on demand; it is not configuration and never survives a reboot.

## salvage

The upgrade's safety copy of local content: before replacing a
version directory, upgrade-zfsutilities archives every modified,
added, or removed file it is about to overwrite into
`salvaged-changes/<version>/<timestamp>/` (with a combined diff) on
each deployment target, so the operator can re-apply anything still
wanted. Salvage always precedes the deploy — an interrupted first
run leaves the archive behind (j10, j23, j25).

## sample archive

The JSON file a function-survey run writes (under
`tests/integrated/survey/archives/` and the run dir): the seed, the
fraction, the software target, a digest of the universe it was drawn
from, and the ordered item list with each item's response profile.
Replaying an archive (`ITF_SURVEY_ARCHIVE=<file>`) reproduces the exact
run; a universe that has since changed is reported as drift, never
silently dropped. This is also the repair-verification artifact: the
same list re-run against a fixed tree proves the fix.

## sampling universe

The complete list of end-user-visible functions a function survey draws
from: every documented CLI command (minus the two recorded exclusion
tables) plus the GUI surface of the tree under test — action buttons,
central-content widget interactions, and multi-widget composites. The
GUI half is enumerated at run time from the product code, so it can
never drift from what the user actually sees; the CLI half is a
manifest whose sync with the docs is enforced by a test.

## shadowed mount

A dataset the kernel lists as mounted whose mountpoint path cannot be
reached, because a later mount over an ancestor (typically a pool root
mounted after its children) covers the path. Data written through the
path lands in the covering filesystem instead, and `zfs unmount` fails
with a misleading error: `no such pool or dataset` when nothing is left
at the path, or `unmount failed` when an empty leftover directory of the
same name sits inside the cover. The GUI therefore tests the path (is it
a real mountpoint?) rather than the error text. The covering layer is
called the *cover*; the GUI repairs the order by unmounting the affected
set (detaching covers with an exact-layer `umount` so unrelated mounted
children are not cascaded) and remounting parents-first. Contrast an
*orphaned* mount, where an ancestor is unmounted and the path is simply
missing.

## shape

Report shorthand for the exact pattern or structure of a thing. An output
line's shape is its columns and format. A failure's shape is which
symptoms appear in which combination — "the 3/33 incident shape" means 33
backstores defined, only 3 LUNs mapped, and every count gate green. A
config's or a systemd unit's shape is its fields and their structure.
Claims about a shape are usually pinned by a fixture or a regex, so the
pattern cannot drift silently.

## SSH connection reuse (ControlMaster)

OpenSSH's connection multiplexing: the first `ssh` to a host starts a
background "master" connection, and later `ssh` commands to the same
user@host reuse it through a control socket instead of logging in again.
Configured with `-o ControlMaster=auto -o ControlPath=… -o
ControlPersist=<seconds>`; the master closes itself after the persist
window of inactivity, and a dead socket is replaced automatically. In this
project `path_utils.ssh_command()` builds every Python-side remote command
this way (600 s persist), matching the Bash side's `deploy-version` and
`upgrade-zfsutilities`. Why it matters here: each fresh root login writes
roughly two dozen journal lines plus a systemd user-session cycle on the
target node — the Dashboard's automatic refresh once logged in three times
per tick, which flooded the compute node's journal (~14,000 lines/hour at
the 30 s default). With reuse plus the batched probe
(`dashboard_page._probe_remote_host`), a refresh rides one existing
connection and the poll becomes invisible in the remote journal.

## suite

One named group of tests. Bash suites are `tests/test-*`; Python suites
are `tests/python/test_*.py`; the special gates (docs integrity, the soak
leg, the integrated journeys) are suites too. The "affected suites" of a
change are the ones covering the files it touched. House rule (root
AGENTS.md): during iteration run only the affected suites; run the full
suite once, at the end — the full gate is `tests/run-tests`.

## TCG

Tiny Code Generator: QEMU's software CPU emulator — the fallback that
runs a virtual machine entirely in code when hardware virtualization
(KVM) is unavailable. The integration-test lab nests Proxmox inside its
guests with no /dev/kvm passthrough, so every lab VM boots under TCG
("a TCG boot", `kvm=0`): much slower than KVM but faithful, which is
why lab boot proofs are timed generously and judged by behavior, not
speed.

## TPG

Target Portal Group: the container inside an iSCSI target (LIO/
targetcli) that holds the LUN mappings and the ACL initiator grants.
In practice every target in this setup has exactly one (TPG 1), so
"the TPG's mappings" means the target's complete LUN map — the thing
the safe-iscsi-save gate compares against the expected-backstores
manifest, and the thing the 2026-10-27 incident silently lost (33
backstores defined, only 3 mapped, because the gates counted
backstores instead of TPG mappings).

## trust-on-first-upgrade

How upgrade-zfsutilities handles an active version that has neither a
`MANIFEST.sha256` nor an obtainable release tarball (every deployment
older than 0.125.0, and versions never tagged on GitHub): it captures
a baseline manifest from the current tree, so every future upgrade
scans against it — modifications older than that moment are
indistinguishable from pristine content, and the report says so
(F-025; j19 proves the capture, j23 proves it over ssh on the remote
host).

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

## world

The complete fake ZFS state a bash suite defines for the `zfs()` mock in
`tests/test-lib.sh` — every dataset row, existence flag, property, and
snapshot the mock will answer with. Reports say "mock world" for the
whole set and "world rewrite" for the fix shape where a suite's fake
tree is completed instead of working around a gap: the 2026-11-03
mock-fidelity fix made rooted `zfs list <root>` listings stay inside the
requested root, which exposed suites whose worlds modeled only part of
the tree (a destination that existed in the existence model but had no
listing rows). Related: mock (the stand-in itself) and the standing
mock-fidelity rule.
