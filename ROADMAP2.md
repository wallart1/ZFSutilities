# Plan: Subpool and Remote Support — Revised

## Context from Feedback

- **GitHub first.** Publishing should happen before a major feature branch.
- **No backward-compatibility constraint.** We can redesign freely.
- **Restore design intent.** The original workflow is "restore backups from whence they came." Subpool destinations for Restore may be unnecessary; we should not contort `sourcefsremovequalifiers` unless there is a real use case.
- **Remote architecture.** Pushing scripts (or script fragments) to remote hosts and executing them locally there is preferable to SSH-wrapping every `zfs` command ad-hoc.
- **No shortcuts.** Full support for remote source *and* remote destination, including resume tokens, common snapshots, holds, and destination preparation.

---

## Pre-requisite: Publish to GitHub

Before any coding, create a clean public repository.

1. Audit the repo for secrets, hostnames, or internal paths in code/comments (e.g. `root@rocky`, `COMPUTE_HOST`, hard-coded pool names).
2. Write a `LICENSE` (e.g. MIT or GPL-3.0).
3. Ensure `README.md` is up to date.
4. Create the repo and push `main`.

> **Question for you:** Do you want me to do the GitHub audit/push as part of this plan, or handle it separately?

---

## Option A — Incremental v1.x.x (SSH Wrappers, Minimal Redesign)

Keep the existing `zfs-send-receive` monolith, but make it remote-aware by:
- Adding `source_host` / `dest_host` globals.
- Replacing raw `zfs` calls with `_zfs_src` / `_zfs_dst` wrappers.
- Overriding `buildfsarray`, `getcommonsnap`, `delfs`, `delallsnaps`, `delallholds`, `zfshold` inside `zfs-send-receive` when hosts are set.

**Pros:** Smallest blast radius. Reuses existing control flow.
**Cons:** The script remains a 500-line monolith with mixed local/remote logic. Every future ZFS feature must remember to use wrappers.

---

## Option B — Clean v1.x.x Redesign (Remote Agents / Script Push)

Split `zfs-send-receive` into distinct phases and push a minimal "agent" script to each remote host.

### Architecture

1. **Local orchestrator** (`zfs-send-receive` running on the GUI host or cron host) decides which side is remote.
2. **Agent script** (`zfs-remote-agent`) is copied to `/tmp/zfsutilities-agent/` on each remote host via `scp` (or assumed already installed). The agent accepts commands like:
   ```bash
   zfs-remote-agent buildfsarray <sourcefs> [depth] [includes...]
   zfs-remote-agent commsnap <fs_s> <fs_d> [commsnap_mostrecent]
   zfs-remote-agent snapshot <fs> <snapname>
   zfs-remote-agent send <fs@snap> [opts]
   zfs-remote-agent receive <fs> [opts]
   zfs-remote-agent getprop <fs> <prop>
   zfs-remote-agent resume_token <fs>
   zfs-remote-agent abort_resume <fs>
   zfs-remote-agent list_snaps <fs>
   zfs-remote-agent check_space <pool>
   zfs-remote-agent delfs <fs>
   zfs-remote-agent delallsnaps <fs>
   zfs-remote-agent applyhold <tag> <fs> <snap>
   ```
3. The orchestrator runs each phase by calling the agent on the appropriate host:
   - **Discovery:** `agent@source` → `buildfsarray` → returns JSON/array of datasets.
   - **Pre-flight:** `agent@source` → `commsnap`, `agent@dest` → `resume_token`, `check_space`.
   - **Transfer:** Spawn a piped SSH process: `agent@source send ... | agent@dest receive ...`.
   - **Post-flight:** `agent@dest` → `verify` (GUID comparison), `agent@source/dest` → `applyhold`.

### What changes

| Component | Change |
|-----------|--------|
| `zfs-send-receive` | Becomes a thin orchestrator. Source/dest logic is removed into functions that call either local commands or the remote agent. |
| `zfs-remote-agent` (new) | Single bash script with a `case "$1"` dispatcher. Reuses existing helper scripts where possible. |
| `zfsbuildfsarray` | Unchanged for local use; agent calls it locally on the remote host. |
| `zfscommsnap` | Unchanged for local use; agent calls `getcommonsnap` locally. |
| `zfshold`, `zfsdelfs`, etc. | Unchanged for local use; agent delegates to them. |
| Python command builders | Parse `host:dataset`, pass `source_host`/`dest_host` to the orchestrator. |
| Python runners | No change to command structure; just new host variables. |

### Subpool Support

- **Backup / Offsite:** Already works; `sourcefs` and `destfs` are arbitrary dataset paths. We only update tooltips.
- **Restore:** Keep the original design intent. Do NOT add arbitrary subpool destinations. Fix the bug in `profile_runner._compute_restore_params` so it matches `restore_runner.compute_restore_params` and correctly handles the intended "restore from backup to original" mapping. If a user enters an unsupported mapping, show a clear error explaining the expected format.

### Pros / Cons of Option B

**Pros:**
- Clean separation of concerns. Remote logic lives in one place (the agent).
- Local scripts (`zfsbuildfsarray`, `zfscommsnap`, etc.) stay simple and unchanged.
- Easy to extend: add a new agent command instead of sprinkling SSH logic everywhere.
- The orchestrator can be rewritten in Python later without touching the agent.

**Cons:**
- More files to manage (agent deployment, scp/ssh round-trips).
- Slightly higher latency due to multiple SSH round-trips for discovery/pre-flight.
- Requires `root@host` passwordless SSH (already assumed in the codebase).

---

## Recommendation

**Option B (Clean Redesign)** is the right choice given:
- You own the whole stack and backward compatibility is not a constraint.
- The "no shortcuts" feedback makes the wrapper approach (Option A) unsuitable.
- The agent model maps naturally to future features (e.g. multi-hop replication, parallel transfers).

**Sequence:**
1. GitHub publish (audit + push).
2. Branch `v1.x.x` from `main`.
3. Implement `zfs-remote-agent` and refactor `zfs-send-receive` into an orchestrator.
4. Update Python command builders and GUI tooltips.
5. Update tests.
6. Merge to `main`, tag `v1.0.0`.

---

## Questions Before Proceeding

1. **GitHub:** Should I include the GitHub audit/push in this plan, or do you want to handle that separately?
2. **Agent deployment:** Should the orchestrator auto-deploy the agent to `/tmp/zfsutilities-agent/` on first use, or should we assume `zfsutilities` is already installed on remote hosts?
3. **Restore subpools:** Confirm that we should NOT support arbitrary subpool destinations for Restore. The UI will accept only mappings that fit the original `sourcefsremovequalifiers` model (e.g. `backuppool/threeamigos/proxmox` → `threeamigos/proxmox`).
