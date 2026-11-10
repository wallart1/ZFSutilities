# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- **2026-11-09 — itf stage-B HTTP server died silently mid-download (one-shot, unreproduced).**
  Run `run-20261109-210703-j22-function-survey`: the survey's tree-staging
  `itf_http_serve` (python http.server, pid 2098437, `--bind 0.0.0.0`, port
  8000) answered its readiness probe at 21:32:37, then the guest's
  `curl http://10.0.0.127:8000/...` was refused at 21:32:39 — no listener,
  no traceback in `http-stageb.log`, no OOM/segfault/systemd events in the
  journal, kernel quiet. The same-step download 4 minutes earlier (j05 lab)
  and a manual replay of the exact serve+fetch sequence both worked. Not the
  loopback-shadow class the probe already guards (the probe fetches our
  content). One unrelated data point: Dev's own qemu-ga ran a
  `list-vm-disks`-style guest-agent disk enumeration at 21:32:37
  (production-side, read-only, not the lab — the lab's qm ran inside its
  nested-PVE compute guest). Cause unknown; `--rerun` recovered cleanly
  (guest GET 200 at 22:04:50). If this recurs: watch port 8000 with a
  sampler during the stage-B window and check for agent-driven activity on
  the dev host at the same moment.

---

- **2026-11-10 — upgrade-zfsutilities prints a remote activation command
  that does not run as printed.**
  The closing report of a two-node upgrade prints
  `ssh root@<host> switch-version <version>` for each remote target
  (`upgrade_main`, the "Activate when ready" block). A command handed to
  ssh runs in a non-login shell, and the product's PATH wiring is
  `/etc/profile.d/zfsutilities.sh` (login shells only) plus the sudoers
  `secure_path` — so `switch-version` is not found there. The journeys
  wrap the command in `bash -lc` (j12 carries the note; j23 and j25 do
  the same), which is why no journey has caught it. `install-two-node`
  already uses the absolute path for its own remote activation. Fix
  candidate: print the absolute form
  (`/usr/local/lib/zfsutilities/bin/switch-version`), then have j23/j25
  run the printed line unmodified. Found by code review; not yet
  reproduced on a live host.

---

- **2026-11-10 — upgrade-zfsutilities: a failed baseline capture aborts
  with "unbound variable".**
  `process_host` sets `host_verifiable[$host]` only when the
  trust-on-first-upgrade capture succeeds (`baseline-captured`). On a
  failed capture the element stays unset: the `no-baseline` state named
  in the declaration comment and handled by `render_host_report` is
  never assigned anywhere. The two
  `"${host_verifiable[$host]}" == "no-baseline"` reads in `upgrade_main`
  carry no `:-` default, so under `set -u` the script dies there instead
  of printing the "local modifications cannot be verified" warning that
  `process_host`'s own comment promises. Nothing has been changed at
  that point, so the abort is safe; the message is wrong. Fix candidate:
  assign `no-baseline` in both failure branches. Found by code review.

---

- **2026-11-10 — j13 reads the four-field guest record into three
  variables.**
  `tests/integrated/journeys/j13-iscsi-storage-restore.journey` reads
  `guest-storage.txt` and `guest-compute.txt` with
  `read -r _ s_vmid s_ip` (and the compute twin). The records carry a
  fourth field (the live qm guest name) since the name-based orphan
  fence, so `s_ip` and `c_ip` come back as `<ip> <name>` and every later
  guest command gets a bad address. Every other journey consumes the
  fourth field (j06/j07/j14/j15 name it; j23/j24/j25 discard it). j13
  has not run since the record format changed. Fix: add the name slot.

---

- **2026-11-10 — j05's lease re-acquire rewrites the wrong record file.**
  `_j05_storage_lease_reacquire` writes the re-leased address to
  `guest-${gname}.txt`; its only caller passes `j05-storage`, so the
  file is `guest-j05-storage.txt`. The record every consumer reads is
  the role-named `guest-storage.txt`. After a storage/compute
  same-address collision, the journeys that compose the j05 lab and
  re-read the record (j06, j07, j13, j14, j15, j23, j24, j25) would get
  the old, collided address. Reachable only on a DHCP collision; not
  observed in a run. Fix: write the role-named file.

---

- **2026-11-10 — over-100-column lines remain in the older journey
  files.**
  Character-accurate counts: `tests/integrated/journeys/common.sh` 4
  (all inside generated guest commands: the apt-get line, the fstab
  line, the boot-journal grep, the by-path awk loop), j15 3, j16 1,
  j17 3, j20 22. The three journeys added in the 0.140.0 cycle are
  clean. Wrapping must keep the generated guest text byte-identical
  (a backslash-newline is removed inside an unquoted heredoc and kept
  inside a quoted one).

---
