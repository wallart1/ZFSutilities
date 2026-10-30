# Repair Plan 022 — encrypted-LUN registration matches by name prefix only

Finding: **F-027** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-29 (user-approved).** The registration and
removal logic was extracted into `register_encrypted_lun` /
`remove_encrypted_lun_entry` (the suites' function-extraction pattern);
unit gates red-proven; journey gate (conf holds exactly the lab entry)
added to the encrypted-lab tail. Verification rides the j05/j16 lab
reruns.

## Root cause

`bin/install-two-node` (Step 5) seeds a fresh storage host's
`/etc/zfsutilities/iscsi-encrypted-luns.conf` from the site-specific
sample `share/two-node/iscsi-encrypted-luns.conf` whenever the conf
does not exist yet.  That sample intentionally carries the operator's
real production entries (site-specific by design, same stance as
zfssendoffsite's usage examples) — on the lab's fresh guest:
`vm-101-disk-1:/dev/zvol/threeamigos/proxmox/vm-101-disk-1:threeamigos`
and `vm-202-disk-5:...`.

`bin/new-vm-disk` decides "already registered" with a name-PREFIX
match (line 552):

```bash
if [[ -f "$encrypted_conf" ]] && grep -q "^${backstore_name}:" "$encrypted_conf"; then
    log_msg "INFO: ✓ Already in encrypted LUNs config"
```

The lab's first encrypted disk is `vm-101-disk-1` on `zfstest1` — the
name collides with the sample's production entry while the device path
and target differ.  The registration is silently skipped, the conf
keeps the foreign line, and every reader of the conf
(`iscsi-add-encrypted-luns`, `safe-iscsi-save`'s boot-config
exclusion, `restart-iscsi-services`) keys on the PHANTOM device path
for that backstore.  Observed live in
run-20261028-183706-j05-two-node-install: "✓ Already in encrypted LUNs
config", no lab entry in the conf, keystatus correctly `available`
(the zvol itself is fine — only the registration bookkeeping is lost).

Any environment that shares a backstore name with a shipped-sample
entry hits this: the lab (vm-101-disk-1 is the natural first guest
disk), any second site built from the sample, or a host repurposed
after the sample was installed.

## Proposed repair

In `bin/new-vm-disk`, replace the prefix match with a full-line match
against the entry the product is about to register:

```bash
expected="${backstore_name}:${zvol_dev}:${target_short}"
if grep -qxF "$expected" "$encrypted_conf" 2>/dev/null; then
    # truly already registered
elif grep -q "^${backstore_name}:" "$encrypted_conf" 2>/dev/null; then
    # same name, different device/target: replace the stale line
    # (in-place sed) + WARN with old and new lines spelled out
else
    echo "$expected" >> "$encrypted_conf"
fi
```

A same-name/different-device line is stale (device moved, pool
renamed) or foreign (sample carry-over); either way the conf must end
holding the entry that matches the zvol just created, and the operator
must see that a line was replaced (WARN with both lines, never silent).

Mirror check in `remove-vm-disk`'s conf-removal path (it deletes by
name prefix today; it must delete the line matching the zvol it
removed, not any line sharing the name).

## Verification plan

- Unit: `tests/test-new-vm-disk` gains (a) same-name-different-device
  input → conf rewritten to the expected line + WARN; (b) exact-match
  input → untouched, no WARN; (c) fresh conf → appended.
- Journey: `j05 --encrypted-keys` (the encrypted-lab tail) must show
  the registration step green WITHOUT the lab's fresh-host conf reset
  once the fix rides the dev tarball; the staging reset stays (a fresh
  lab host models no pre-existing encrypted LUNs) but the journey also
  asserts the conf holds exactly the lab entry afterwards.
