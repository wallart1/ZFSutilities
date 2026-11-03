# Integrated Testing Findings

Product issues discovered by itf journeys run against real installs
(GitHub release or dev tarball) in the disposable nested guests.  One row
per finding; repair plans live in `repair-plans/NNN-slug.md` and are
executed in the dev repository only after explicit user approval.

Published rows are pruned at each release (recoverable via
`git log`); rows remain here only while their outcome is not yet
shipped — currently F-037 (plan 026's fix shipped in the 0.137.0
release; the row stays until the user-cued fresh j16 run flips it
to `verified`).  F-034 shipped verified in 0.137.0 and was pruned.

| ID | Date | Journey | Symptom | Suspected area | Status | Repair plan |
|----|------|---------|---------|----------------|--------|-------------|
| F-045 | 2026-11-03 | e2e payload matrix, new `restore-receive-encrypted` scenario (dev-host sudo leg, first run) | A receive-as-encrypted restore can never transfer: the engine sends every stream `-cw`, and `zfs receive -o encryption=on` refuses embedded-data streams outright (`cannot receive new filesystem stream: incompatible embedded data stream feature with encrypted receive` — measured on OpenZFS 2.2.2, plain stream + encrypted receive verified working in the same probe). P6's unit suites mock zfs, so the transfer shape was never exercised; j21-p5 measured only plain streams | bin/zfs-send-receive sendoptions: the receive-as-encrypted path kept the universal `-cw` send | fixed (2026-11-03, same session, act-on-analysis: when the initial receive carries the encryption `-o` overrides, the send drops `-cw` and goes plain — the only stream form an encrypted receive takes; property fidelity for this transfer is the manifest replay's job, and encrypted sources never reach the gate (their raw streams keep their own encryption). EXTENDED same day after j20's EE stage caught the second half: the step-2 catch-up `-cw -I` into the just-created encrypted dataset is refused by the same law, so a destination-encryption probe now drops `-cw` for EVERY receive into an encrypted destination from an unencrypted source (plain incrementals into it verified working with the engine's own `-u` receive flags; the raw `-w` path for encrypted sources is untouched) — and the probe runs PER TRANSFER STEP, not once per dataset: step 1 CREATES the destination encrypted, so a once-per-dataset probe stale-sees its absence (the first fix attempt failed j20 exactly that way). Unit pins `test_encrypted_step1_send_is_plain` + `test_incremental_into_encrypted_dest_sends_plain`; both new restore e2e scenarios green under sudo on the dev host; j20's EE stage exercises the full fixed path in the ITF) | — |
| F-046 | 2026-11-03 | j20 SS stage (results/run-20261103-133427-j20-property-manifest: guest-sendstream.log) | The unpaced `zfsrestoresendstream` can never transfer: its pipeline is `pv \| "${pace_argv[@]}" \| zfs receive`, and bash runs a zero-word pipeline segment as a null command that swallows the stream (measured on bash 5.2: `echo hi \| "${x[@]}" \| cat` delivers nothing) — `zfs receive` reads instant EOF and FATALs `cannot receive: failed to read from stream`. Regressed at the 0.133.0 rate-governance rework; unit suites mock the pipeline so the shape was never real, and no journey drove the script until j20's SS stage. `zfsreadthru` (both read passes, 0.133.0) shares the idiom — its unpaced read-through silently stops reading the pool | empty-array pacer segment in bin/zfsrestoresendstream + bin/zfsreadthru (lib/transfer-lib.sh composes correctly by branch — production transfers unaffected) | fixed (2026-11-03, same session, act-on-analysis: both scripts compose the pipeline by branch — paced `pv \| python3 pace_stream.py <rate> \| zfs receive`, unpaced `pv \| zfs receive` with no pacer stage, exactly like transfer_do's four-shape composition; zfsreadthru gains a `read_pass` helper so both passes share it. New source-shape guard `test_restoresendstream_pipeline_composed_by_branch` refuses the idiom's return in both scripts — mocks cannot see pipeline semantics; j20's SS stage is the live regression test) | — |
| F-037 | 2026-10-29 | J16 S7b (results/run-20261030-033206-j16-iscsi-total-loss: s7b-authority.log, s7b-grant-gap.log) | After a total target wipe, the saveconfig recovery authority is destroyed by the documented recovery itself: setup-iscsi-targets saves its freshly created (empty) targets with a bare `targetcli saveconfig`, overwriting the LUN/ACL records iscsi-restore-luns would have needed — the pool map is the only surviving authority. And the map records ACL initiator NAMES but no grant indexes, so the non-identity mapped_lun 8→0 grant is unrecoverable through the map path (it returns only via S7a's saveconfig restore, and the map's ACL dimension silently dissolves to demo mode on rebuild). Every recovery converges, but non-identity grants are lost and nothing warns | total-loss authority chain: setup's unconditional save + the map's grant-less ACL schema | fixed (2026-11-01; repair plan 026 EXECUTED same day, user-cued: the pool map gained a grants dimension (per-ACL `mapped_lun→tpg_lun` pairs, schema version 2; dual-read keeps legacy name-list maps parsing with today's identity behavior). Export records pairs red-proven on the old shape; reconcile rebuilds recorded pairs exactly — grant-bearing ACL records rebuild on demo TPGs too, a present-but-differing pair refuses and blocks the map refresh; the shared `iscsi_grant_lun_to_acls` heal recreates recorded pairs and never blanket-grants identity over a recorded set. Two in-cycle finds fixed: the reconcile map-refresh gate ignored ACL-grant failures, and a live-proven SIGPIPE race (`targetcli | grep -q` under pipefail flips found objects to missing — it aborted the first fresh run's S6; fixed on all plan surfaces + setup's `/iscsi ls` probes). Unit suites green (export 30, reconcile 32, recover 14, add 9, restore 6, setup 13, repair-refs 29; full bash suite green; python 4355 passed — one host-load flake green in isolation). Fix shipped in the 0.137.0 release; F-037 flips to `verified` on a user-cued fresh j16 run) | [026](repair-plans/026-map-grants-dimension.md) |

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
