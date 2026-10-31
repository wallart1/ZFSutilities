# Recovery Requirements Register

Requirements for future coding, seeded from the recovery-scenario
campaign's journey outcomes (roadmap phase 3.9, j15–j18) and the FINDINGS
triage. A row records a UX gap or design direction the journeys proved
live; it is the durable input for future repair plans — promotion from a
row to a plan is the owner's call, never automatic. Product-truth rows
(what an operator must know today) are additionally documented in the
user-facing pages named by the row.

Companion files: `FINDINGS.md` (the defect ledger — every finding ends in
exactly one terminal state per the triage rule) and
`repair-plans/` (numbered proposals awaiting approval).

| ID | Date | Source | Requirement | Status |
|----|------|--------|-------------|--------|
| R-01 | 2026-10-30 | F-032 (j15 S1b) | Running VMs never resume disk IO after a storage power event: iSCSI links and sessions re-login automatically, but both workload VMs (plain and encrypted root) keep stalled writers until a manual stop/start — the operator symptom is silently stalled VMs behind healthy-looking paths. Direction: surface the condition (fence/verifier naming VMs needing restart), or document the stop/start as the standard post-outage step (interim: noted in two-node.md's power-event notes) | open |
| R-02 | 2026-10-30 | F-030 (j15 S1) | `qm start` on an encrypted-root VM whose LUN is keys-pending "succeeds" against a stale device node and the guest never boots — no abort signal anywhere between "VM starts" and "VM hangs". Direction: a pre-start observable (the product cannot see PVE's start, but the fence/check surfaces could name the pending-keys LUN before the operator starts the VM) | open |
| R-03 | 2026-10-30 | F-031 (j15 S1b) | The compute fence is blind to a TOTAL storage outage: PVE patches the iSCSI replacement timeout to 24 h, dead sessions keep the by-path links present, and link existence is the fence's only outage signal — a tick reports healthy minutes into a full outage. Direction: a liveness dimension (session state / target reachability) alongside link presence | open |
| R-04 | 2026-10-30 | F-038 (j16 S6) | `check-prerequisites --two-node` passes GREEN on a fully-unmapped target: its post-restore detection is mtime/manifest-scoped, so live loss with current files is out of its scope — an inexperienced user's first instinct (the health gate) sees all green on a degraded system. Direction: widen the gate's scope or point it at `setup-iscsi-targets`' live detector | open |
| R-05 | 2026-10-30 | j18 S15 | PVE's boot-time autostart races the iSCSI login: startall fires before the links exist, fails on the by-path stat, and never retries — onboot alone does not return running VMs unattended on iSCSI disks, and the fence heals links but not starts. Direction: a post-boot start retry (fence tick or onboot-adjacent helper); today the operator's `qm start` is the everyday path (noted in two-node.md's power-event notes) | open |
| R-06 | 2026-10-30 | j18 S17 | Documented teardowns (`remove-vm --cleanup-orphans`, `remove-vm-disk`) leave a ghost 0-GiB device row on the compute host that `rescan-storage` cannot drop — only a session re-login clears it. Direction: teardown paths log out / re-login the affected sessions, or the ghost row is named in the teardown output with its one-command clear | open |
| R-07 | 2026-10-30 | j17 M3 | Destructive confirmations are `y/N`, not type-to-confirm: a wrong-object yes at `remove-vm-disk`'s destroy prompts is one keystroke away. Direction: type-to-confirm (dataset or VMID+disk) on the destructive class; j17 proves the validation-before-mutation pattern already holds everywhere else | open |
| R-08 | 2026-10-30 | F-029 (j15 S1/S1c) | Every keys-absent boot journals `post-restore verification FAILED` + DRIFT — correct per the documented semantics, but an every-boot expected FAILED trains operators to ignore the verifier exactly when an unexpected drift arrives. Direction: an encrypted-aware verdict distinguishing expected keys-pending drift from unexpected drift (repair-plan path only — behavior change) | open |
| R-09 | 2026-10-30 | j15 S5b | The only posture that legitimately journals boot-time verification OK is a key-loading unit ordered before the restore (the boot drop-in's own "separate key-loading unit" clause); the lab prototyped the ordering (`After zfs-import*`, `Before` the targetctl restore, `zfs load-key -a`). Direction: ship that optional unit (or a documented template of it) so operators stop hand-rolling it; the removed boot automation stays removed — this is the explicit, opt-in, race-free form | open |

Status values: `open` → `promoted → repair-plan NNN` (owner-approved) →
`addressed (version)` — or `declined (date, reason)`.

Maintenance rules:

- One row per requirement; the source cell names the journey scenario or
  FINDINGS row that proved it (raw evidence lives in the run directory
  that finding records).
- New rows come only from journey outcomes or user direction — no
  speculative requirements.
- A row never silently disappears: promotion, addressing, or declining
  is recorded in the status cell with a date.
