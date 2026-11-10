# ITF Coverage Map

Journey coverage of the product surface, by node mode. Agent-maintained:
rows are added when a journey exists to fill them, and gap rows are
candidates only — a gap is built when a real need names it (no
speculative coverage). The journeys themselves are described in
[Integrated Testing](integrated-testing.md) and
`tests/integrated/journeys/README.md`.

| Surface | Single-node | Two-node |
|---------|-------------|----------|
| Fresh install, prerequisite remediation, test pools | j01 | j05 (storage role; installer drives both) |
| Installer failure paths (declined remediation, dead apt) | j08, j09 | — |
| Uninstall / reinstall / install over leftovers | j02, j03 | j24 (live LUNs byte-survive the `--all-nodes` purge; recurrence-fence reinstall; both SW sources once releases carry the F-049 menu fix) |
| Post-install baseline (wiring, pools, product surface) | j04 | j05 verify stages |
| Release upgrade (scan/salvage/deploy/activate) | j10, j12 (interrupted: SIGTERM early, SIGKILL mid-deploy), j19 (trust-on-first-upgrade baseline capture) | j23 (remote scan/salvage/baseline over per-host SSH masters, deploy.conf group targets, per-host switch-version output; dev-tarball only), j25 (interrupted on the encrypted lab with keys pending: SIGTERM at the scan marker, SIGKILL mid-local-deploy, SIGKILL aimed at the remote sync; recovery leaves the iSCSI records byte-identical and so does activation — the fence tick the timer restart fires is waited out first, its documented saveconfig re-save tolerated in the absent-link shape; key ceremony on the upgraded tree; dev-tarball only) |
| GUI payload e2e matrix (offsite chain, backup/prune/rsync orchestrators, restore payloads incl. receive-as-encrypted) | j11 (+dev-container/dev-host contexts) | — |
| Backup property fidelity (manifest capture, offsite travel, replay, retention lockstep, sendstream `.props` consumption, standalone replay, receive-as-encrypted restore + FATAL guard) | j20 (incl. the offsite-onward + restore payload pairs) | — |
| ZFS-semantics probe matrix (receive `-o volblocksize`, stream fidelity plain/`-c`/`-cw`, keylocation prompt vs `file://`, receive-as-encrypted, raw `-o` refusal, encryptionroot-self) | j21 (`--template storage/compute/ubuntu`, per-template version-keyed expectations; `probes.tsv` = the measured truths behind `zfs_capabilities`' receive-family entries) | — |
| First LUN round trip (new-vm-disk → iSCSI → VM config → save) | — | j05 (composed by every j06+ lab journey) |
| Guest-probe validator (pools/datasets/PVE fetch, honest degradation) | — | j06 |
| Archive / unarchive + target rebuild (IQN drift) | — | j07 |
| Bare-metal storage-restore regression (detector + map-driven rebuild at recorded LUNs) | — | j13 |
| Compute fence wiring + unit-driven unattended recover | — | j14 |
| Boot & keys: journal oracle, blind recovery, compute fallout, wrong input | — | j15 (S1, S1c, S1b, S2, S3, S4, S5a/S5b, M1, M4) |
| LIO total loss & identity: live loss, 3-of-33 shape, total-wipe pair, corrupt saveconfig, pool identity | — | j16 (S6–S9, S18) |
| Interrupted & contradictory operations: SIGINT half states, collisions, concurrent mutators (fenced), mistyped input | — | j17 (S10–S14, S12 fence, M2, M3, M5) |
| Compute & power events: compute reboot, both-node cycle with unreachable storage, orphan LUN teardown | — | j18 (S15–S17) |

Scenario IDs (S/M) are specified in the campaign plan and asserted by the
journeys; `export-iscsi-state --check` stands in for Dashboard data in the
recovery scenarios (the blind-recovery rule).

## Gap rows (future candidates — built only when a real need names them)

None open. The last one — the two-node interrupted upgrade with keys
pending — is j25.

## Parked (standing policy)

- **GUI automation** and the remaining **OS matrix** (template profiles
  beyond storage/compute/ubuntu) — parked by standing decision; reopened
  only by an explicit user trigger (the ubuntu profile is the one named
  exception: the j21 probe matrix needed a 2.2-era OpenZFS leg).
- The 17 test-exempt legacy `bin/` commands are permanently excluded
  from journey scope (closed list, user decision 2026-10-26).

## Companion registers

Product defects found by journeys live in `tests/integrated/FINDINGS.md`
(each row ends in exactly one terminal state); UX gaps and design
directions live in `tests/integrated/REQUIREMENTS.md`. Both are linked
from `tests/integrated/README.md`.
