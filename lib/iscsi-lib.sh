#!/usr/bin/bash
# iscsi-lib.sh
# Shared iSCSI helpers: target-state discovery (parse_backstores,
# parse_target_luns, parse_target_acls, discover_zvols, is_vm_backstore_name),
# ACL MappedLUN binding after LUN (re)creation (iscsi_grant_lun_to_acls), the
# detection helpers (detect_stale_lio_files, detect_manifest_without_zvols,
# detect_vm_refs_missing_live, detect_pool_identity), and the
# teardown/rebuild helpers used by zfsdelfs and zfs-send-receive.
#
# This library is sourced at the file level by:
#   - zfsdelfs, to tear down iSCSI LUNs before destroying VM zvols.
#   - zfs-send-receive, to rebuild iSCSI LUNs after a successful zfs receive.
#   - repair-iscsi-luns and export-iscsi-state, for the discovery helpers.
#   - setup-iscsi-targets and reconcile-iscsi-state, for the discovery and
#     detection helpers.
#   - iscsi-recover-encrypted-luns and iscsi-add-encrypted-luns, to grant a
#     (re)created LUN to every existing ACL initiator on its target.
#   - check-prerequisites (--two-node, with ISCSI_LIB_NO_BOOTSTRAP=1), for
#     the detection helpers only.
#
# The library loads its own dependencies (bashinit and node-lib.sh) when the
# sourcing context has not already loaded them. The probe is node-lib's
# pool_to_target (not bashinit): zfsdelfs sources bashinit itself but relies
# on this block for node-lib, while repair-iscsi-luns and export-iscsi-state
# source both before this library — and in unit tests a re-load here would
# re-run bashinit's session-log setup and clobber the harness's command mocks.
# ISCSI_LIB_NO_BOOTSTRAP=1 exempts a strictly standalone consumer
# (check-prerequisites, a read-only gate that must also run pre-install with
# no installed bashinit): it sources this library for the restore-time
# detection helpers only, none of which needs the session machinery.
if [[ "${ISCSI_LIB_NO_BOOTSTRAP:-}" != "1" ]] \
        && [[ $(type -t pool_to_target 2>/dev/null) != "function" ]]; then
    source ~/bashinit
    bashinit

    NODE_LIB="${NODE_LIB:-$(find_zfsutility_script node-lib.sh)}"
    if [[ -z "$NODE_LIB" ]]; then
        log_msg "FATAL: Could not locate node-lib.sh"
        exit 1
    fi
    source "$NODE_LIB"
fi

# Tracks iSCSI LUNs torn down during dataset deletion.
# Key: dataset name. Value: "target:lun_num:backstore_name:encrypted_flag"
# Populated by iscsi_teardown_zvol; consumed by iscsi_rebuild_torn_down.
# encrypted_flag is "Y" if the backstore was listed in /etc/iscsi-encrypted-luns.conf.
# -g is required: libraries are loaded through bashinit's source_helper function,
# and a bare declare here would create a function-local that vanishes when
# source_helper returns, silently breaking every later iscsi_teardown[...] write.
# The =() initializer is equally required: a declare executed in a function
# frame leaves an element-less array that set -u callers cannot length-check
# (iscsi_rebuild_torn_down's ${#iscsi_teardown[@]} aborts with "unbound
# variable"); initializing at declaration clears that state.
declare -gA iscsi_teardown=()

# iSCSI manifest paths used by teardown/rebuild helpers.
: "${ISCSI_MANIFEST:=/etc/rtslib-fb-target/expected-backstores.txt}"
: "${ISCSI_ENCRYPTED_CONF:=${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}"\
"/iscsi-encrypted-luns.conf}"

# Legacy fallback: if the new path does not exist and the legacy path does, use
# the legacy path so existing installs keep working before the Step 5 migration.
if [[ ! -e "$ISCSI_ENCRYPTED_CONF" && -f "/etc/iscsi-encrypted-luns.conf" ]]; then
    ISCSI_ENCRYPTED_CONF="/etc/iscsi-encrypted-luns.conf"
fi

# Check if a VM is running for a given VMID.
# Returns: 0=stopped/not found, 1=running, 2=can't determine (SSH failed)
function iscsi_check_vm_running {
    local vmid="$1"
    local status
    if [[ "$node_mode" == "single-node" ]]; then
        status=$(qm status "$vmid" 2>/dev/null)
    else
        status=$(ssh -o ConnectTimeout=5 -o BatchMode=yes root@"$compute_host" \
            "qm status $vmid 2>/dev/null" 2>/dev/null)
    fi
    if [[ -z "$status" ]]; then
        return 2
    fi
    [[ "$status" == *"status: running"* ]] && return 1
    return 0
}

# ------------------------------------------------------------------
# Target state discovery
# ------------------------------------------------------------------
# Shared parsers for targetcli listings and ZFS dataset listings, factored
# out of repair-iscsi-luns so repair, export-iscsi-state, and later
# recovery tooling all read the live LIO topology the same way. Output is
# delivered through the _bs_*/_lun_*/_acl_*/_zvols globals below (declare -g
# per the sourced-library law); each parse function resets its own outputs
# before filling them.

# Return 0 if the argument is a well-formed VM backstore name
# (vm-<vmid>-disk-<n>), else 1.
is_vm_backstore_name() {
    local base="$1" mid suf
    [[ "$base" == vm-*-disk-* ]] || return 1
    mid="${base#vm-}"
    mid="${mid%-disk-*}"
    suf="${base##*-disk-}"
    [[ "$mid" =~ ^[0-9]+$ ]] || return 1
    [[ "$suf" =~ ^[0-9]+$ ]] || return 1
}

# Parse targetcli backstore list into a newline-separated list of:
#   backstore_name device_path
# Output variables:
#   _bs_names[]      array of backstore names
#   _bs_devs[name]   associative array of device paths
parse_backstores() {
    _bs_names=()
    unset -v _bs_devs
    declare -gA _bs_devs=()

    local raw
    raw=$(targetcli /backstores/block ls 2>/dev/null) || return 0

    local line name dev rest
    while IFS= read -r line; do
        # Match lines like:
        #   o- vm-101-disk-0 ........ [/dev/zvol/threeamigos/proxmox/vm-101-disk-0 (1.0MiB) ...]
        [[ "$line" == *"o- vm-"* ]] || continue
        rest="${line#*"o- vm-"}"
        name="vm-${rest%%[[:space:]]*}"
        is_vm_backstore_name "$name" || continue
        [[ "$line" == *"[/dev/zvol/"* ]] || continue
        dev="${line#*"[/dev/zvol/"}"
        dev="/dev/zvol/${dev%%[[:space:]]*}"
        _bs_names+=("$name")
        _bs_devs["$name"]="$dev"
    done <<< "$raw"
}

# Parse targetcli LUN list for a given target IQN.
# Output variables:
#   _lun_indexes[name]   associative array: backstore name -> LUN index
#   _used_indexes[]      sorted array of indexes already in use
parse_target_luns() {
    local iqn="$1"
    _used_indexes=()
    unset -v _lun_indexes
    declare -gA _lun_indexes=()

    local raw
    raw=$(targetcli "/iscsi/${iqn}/tpg1/luns" ls 2>/dev/null) || return 0

    local line idx name rest
    while IFS= read -r line; do
        # Match lines like:
        #   | o- lun19 ..... [block/vm-207-disk-2 (/dev/zvol/...) (...)]
        [[ "$line" == *"block/vm-"* ]] || continue
        rest="${line#*lun}"
        idx="${rest%%[![:digit:]]*}"
        [[ "$idx" =~ ^[0-9]+$ ]] || continue
        rest="${line#*"block/vm-"}"
        name="vm-${rest%%[[:space:]]*}"
        is_vm_backstore_name "$name" || continue
        _lun_indexes["$name"]="$idx"
        _used_indexes+=("$idx")
    done <<< "$raw"
}

# Parse targetcli ACL list for a given target IQN.
# Output variable: _acl_initiators[] sorted, deduplicated array of
# initiator IQNs.
parse_target_acls() {
    local iqn="$1"
    _acl_initiators=()

    local raw
    raw=$(targetcli "/iscsi/${iqn}/tpg1/acls" ls 2>/dev/null) || return 0

    # The character-class regex below extracts initiator IQN tokens from
    # targetcli's acls-ls listing. It is anchored on the literal "iqn."
    # prefix and restricted to the iSCSI-name grammar (RFC 3720: the only
    # characters legal in any segment are letters, digits, dots, colons,
    # underscores, and hyphens) — the same documented pattern as
    # probe_target_usage in node-lib.sh.
    mapfile -t _acl_initiators < <(printf '%s\n' "$raw" \
        | grep -o 'iqn\.[A-Za-z0-9.:_-]*' | sort -u)
    return 0
}

# Grant a TPG LUN to every existing ACL initiator on a target, at the same
# index the TPG LUN holds (identity mapping: create <lun> <lun>). Used after a
# LUN is (re)created: an explicit-mode ACL node grants nothing until it carries
# a MappedLUN for the new index, so without this the initiator cannot see the
# LUN even though the mapping exists. Idempotent — initiators whose ACL already
# shows a mapped_lun at that index are skipped. Demo-mode targets with no live
# ACL nodes no-op: their ACL nodes (with grants for every LUN) self-generate on
# initiator login.
# Returns 0 when every existing initiator has the grant, 1 otherwise.
# The grant-create argument order is targetcli's UIACL create:
#   acls/<initiator> create <mapped_lun> <tpg_lun>
# — the FIRST argument is the LUN number the initiator sees.
iscsi_grant_lun_to_acls() {
    local iqn="$1" lun="$2"
    local init failed=0

    parse_target_acls "$iqn"
    for init in "${_acl_initiators[@]}"; do
        if targetcli "/iscsi/${iqn}/tpg1/acls/${init}" ls 2>/dev/null \
                | grep -q "mapped_lun${lun}[^0-9]"; then
            continue
        fi
        if ! targetcli "/iscsi/${iqn}/tpg1/acls/${init}" \
                create "$lun" "$lun" >/dev/null 2>&1; then
            log_msg "WARN: ${init} — could not grant LUN ${lun} on ${iqn} (create failed)"
            failed=1
            continue
        fi
        # Post-create verification, the same contract the LUN-mapping steps
        # keep: a create that reports success must be visible in the listing.
        if targetcli "/iscsi/${iqn}/tpg1/acls/${init}" ls 2>/dev/null \
                | grep -q "mapped_lun${lun}[^0-9]"; then
            log_msg "INFO:   ✓ granted LUN ${lun} to ${init}"
        else
            log_msg "WARN: ${init} — could not grant LUN ${lun} on ${iqn} (verify failed)"
            failed=1
        fi
    done
    return "$failed"
}

# Discover all VM zvols in configured pools.
# Output variable: _zvols[] array of "pool/dataset" strings.
discover_zvols() {
    _zvols=()
    local pool
    while IFS= read -r pool; do
        [[ -z "$pool" ]] && continue
        local ds base parent
        while IFS= read -r ds; do
            [[ -z "$ds" ]] && continue
            # Keep only "<pool>/proxmox/vm-<vmid>-disk-<n>" (exactly 3 path components)
            parent="${ds%/*}"
            base="${ds##*/}"
            [[ "$parent" == */proxmox ]] || continue
            [[ "$parent" == */*/* ]] && continue
            is_vm_backstore_name "$base" || continue
            _zvols+=("$ds")
        done < <(zfs list -H -o name -r "${pool}/proxmox" 2>/dev/null)
    done < <(pool_list)
}

# ------------------------------------------------------------------
# Pool-resident state map
# ------------------------------------------------------------------
# The pool-resident LUN map (iscsi-state.json) is the bare-metal-restore
# recovery authority: it is written by export-iscsi-state onto every online
# pool and read back by reconcile-iscsi-state. These helpers locate and read
# the map so export and reconcile always resolve the same newest copy.

# File name of the state map inside each <pool>/zfsutilities dataset.
: "${ISCSI_STATE_FILENAME:=iscsi-state.json}"

# Print the string value of a top-level field in a JSON file (empty on any
# error). python3 is already a project-wide dependency (safe-iscsi-save, GUI).
read_json_string_field() {
    local file="$1" field="$2"
    python3 -c 'import json, sys
try:
    with open(sys.argv[1]) as f:
        v = json.load(f).get(sys.argv[2])
    print(v if isinstance(v, str) else "")
except Exception:
    pass' "$file" "$field" 2>/dev/null
}

# Print the state map's recorded pool identities as "name|guid" lines (empty
# on any error, on a missing file, or when the map predates the pools key).
# The consumer of the pool-identity fence; modeled on read_json_string_field.
read_map_pool_guids() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    python3 -c 'import json, sys
try:
    with open(sys.argv[1]) as f:
        pools = json.load(f).get("pools", {})
    for name in sorted(pools):
        guid = pools[name]
        if isinstance(guid, str) and guid.isdigit():
            print("%s|%s" % (name, guid))
except Exception:
    pass' "$file" 2>/dev/null
    return 0
}

# Pools whose zfsutilities datasets are searched for the state map: the
# configured pools when node-lib is loaded (the writer only writes there),
# or every imported pool for standalone consumers (check-prerequisites
# sources this library without node-lib; maps live on configured pools,
# which are necessarily imported when a map can exist at all).
_state_map_search_pools() {
    if [[ $(type -t pool_list 2>/dev/null) == "function" ]]; then
        pool_list
    else
        zpool list -Ho name 2>/dev/null || true
    fi
}

# Locate the newest state map across online pools. Prints the path of the
# map with the newest "generated" timestamp, or nothing when no pool
# holds one. All maps are written by the same host with date -Iseconds, so
# timestamps share one UTC offset and compare correctly as strings.
newest_iscsi_state_map() {
    local pool online mnt f ts best="" best_ts=""
    online=$(zpool list -Ho name 2>/dev/null || true)
    while IFS= read -r pool; do
        [[ -z "$pool" ]] && continue
        grep -qxF -- "$pool" <<< "$online" || continue
        mnt=$(zfs list -H -o mountpoint "${pool}/zfsutilities" 2>/dev/null) || continue
        [[ -z "$mnt" || "$mnt" == "-" ]] && continue
        f="${mnt}/${ISCSI_STATE_FILENAME}"
        [[ -f "$f" ]] || continue
        ts=$(read_json_string_field "$f" "generated")
        [[ -z "$ts" ]] && continue
        if [[ -z "$best_ts" || "$ts" > "$best_ts" ]]; then
            best="$f"
            best_ts="$ts"
        fi
    done < <(_state_map_search_pools)
    [[ -n "$best" ]] && printf '%s\n' "$best"
}

# ------------------------------------------------------------------
# Restore-time detection (bare-metal-restore signatures)
# ------------------------------------------------------------------
# A storage-host bare-metal restore regresses saveconfig.json and the
# expected-backstores manifest together (both live on the OS disk) while the
# pools re-import current. These read-only detectors surface the three
# post-restore signatures so check-prerequisites can warn informationally
# and setup-iscsi-targets can offer the reconcile. Findings accumulate in
# the _detect_lines array (declare -g per the sourced-library law); the
# callers print them in their own voice and decide what to do.
#
# Every helper here must also survive `set -euo pipefail` (check-prerequisites
# sources this library under it) and a missing tool set: each detector
# returns quietly when its inputs are absent, so a pre-install gate on a
# fresh host reports nothing rather than failing.

# LIO's persisted config — the OS-disk file whose content (and, with
# rsync-preserved mtimes, timestamp) regresses in a bare-metal restore.
: "${ISCSI_SAVECONFIG:=/etc/rtslib-fb-target/saveconfig.json}"

# Tests substitute the compute-host VM-reference gather with a file of
# list-vm-disks --gather-vm-info records (VM|targetshort:lun|vmid|name|key).
# Unset = gather over ssh via iscsi_detect_vm_gather below.
: "${ISCSI_DETECT_VM_REFS_FILE:=}"

# Reset the detection evidence accumulator (findings from a previous run
# and the one-shot zvol scan cache).
detect_reset() {
    _detect_lines=()
    _detect_zvol_recs=""
    _detect_zvols_scanned=false
    return 0
}
declare -ga _detect_lines=()
_detect_zvol_recs=""
_detect_zvols_scanned=false

# One-shot scan of the VM zvols (same universe as discover_zvols: datasets
# exactly at <pool>/proxmox/vm-<vmid>-disk-<n>). With node-lib loaded the
# scan is scoped to the configured pools; standalone consumers
# (check-prerequisites) get the all-pools equivalent — backup copies that
# nest deeper than <pool>/proxmox never match either shape. Populates
# _detect_zvol_recs as "backstore|creation_epoch" lines.
_detect_ensure_zvols() {
    [[ "$_detect_zvols_scanned" == true ]] && return 0
    _detect_zvols_scanned=true
    _detect_zvol_recs=""

    local pool ds base parent ct
    if [[ $(type -t pool_list 2>/dev/null) == "function" ]]; then
        while IFS= read -r pool; do
            [[ -z "$pool" ]] && continue
            while IFS=$'\t' read -r ds ct; do
                [[ -n "$ds" ]] || continue
                parent="${ds%/*}"
                base="${ds##*/}"
                [[ "$parent" == "$pool/proxmox" ]] || continue
                is_vm_backstore_name "$base" || continue
                _detect_zvol_recs+="${base}|${ct}"$'\n'
            done < <(zfs list -Hp -t volume -o name,creation -r "$pool/proxmox" 2>/dev/null)
        done < <(pool_list)
    else
        while IFS=$'\t' read -r ds ct; do
            [[ -n "$ds" ]] || continue
            parent="${ds%/*}"
            base="${ds##*/}"
            [[ "$parent" == */proxmox ]] || continue
            [[ "$parent" == */*/* ]] && continue
            is_vm_backstore_name "$base" || continue
            _detect_zvol_recs+="${base}|${ct}"$'\n'
        done < <(zfs list -Hp -t volume -o name,creation 2>/dev/null)
    fi
    return 0
}

# Print an epoch value as a human-readable timestamp (or @<epoch> when date
# cannot parse it).
_detect_fmt_time() {
    date -d "@$1" '+%Y-%m-%d %H:%M' 2>/dev/null || printf '@%s' "$1"
    return 0
}

# Signature (a): saveconfig.json or the manifest predates the newest VM zvol.
# A bare-metal restore rewrites the OS disk from an older backup (rsync
# preserves mtimes), so an OS-disk file older than a still-current zvol means
# the recorded LIO state is missing everything created since the backup point.
detect_stale_lio_files() {
    _detect_ensure_zvols

    local newest_name="" newest_ct=0 name ct
    while IFS='|' read -r name ct; do
        [[ -n "$name" ]] || continue
        [[ -n "$ct" && "$ct" != *[!0-9]* ]] || continue
        if (( ct > newest_ct )); then
            newest_ct=$ct
            newest_name="$name"
        fi
    done <<< "${_detect_zvol_recs}"
    [[ -n "$newest_name" ]] || return 0

    local f mt msg
    for f in "$ISCSI_SAVECONFIG" "$ISCSI_MANIFEST"; do
        [[ -f "$f" ]] || continue
        mt=$(stat -c %Y -- "$f" 2>/dev/null) || continue
        [[ -n "$mt" && "$mt" != *[!0-9]* ]] || continue
        if (( newest_ct > mt )); then
            msg="${f##*/} was last written $(_detect_fmt_time "$mt")"
            msg+=" but VM zvol ${newest_name} was created"
            msg+=" $(_detect_fmt_time "$newest_ct") — OS-disk LIO state predates"
            msg+=" the pools (bare-metal restore signature)"
            _detect_lines+=("$msg")
        fi
    done
    return 0
}

# Signature (c): manifest entries with no matching zvol. The manifest is
# maintained by the LUN tooling, so on a healthy system every entry has a
# zvol; an entry without one means the manifest regressed to a backup point
# that predates a disk removal (or the zvol is gone while the manifest says
# otherwise).
detect_manifest_without_zvols() {
    [[ -f "$ISCSI_MANIFEST" ]] || return 0
    _detect_ensure_zvols

    local -A seen=()
    local name ct entry msg
    while IFS='|' read -r name ct; do
        [[ -n "$name" ]] && seen["$name"]=1
    done <<< "${_detect_zvol_recs}"

    while IFS= read -r entry; do
        is_vm_backstore_name "$entry" || continue
        if [[ -z "${seen[$entry]:-}" ]]; then
            msg="manifest expects ${entry} but no such VM zvol exists"
            msg+=" (deleted, offline pool, or a regressed manifest)"
            _detect_lines+=("$msg")
        fi
    done < "$ISCSI_MANIFEST"
    return 0
}

# VM-reference gather for detection: list-vm-disks --gather-vm-info on the
# compute host (records: VM|targetshort:lun|vmid|name|key, including
# efidisk refs). Unit tests override this function or point
# ISCSI_DETECT_VM_REFS_FILE at a fixture.
iscsi_detect_vm_gather() {
    local remote_script
    remote_script=$(remote_zfsutility_script "$compute_host" "list-vm-disks") || return 1
    ssh -o ConnectTimeout=10 "root@${compute_host}" \
        "${remote_script} --gather-vm-info" 2>/dev/null
}

# Signature (b): compute-host VM disk references whose (target, LUN) is
# absent from the live LIO tree — the PVE side of a regressed LIO config
# (VM start aborts on the missing by-path link). Requires the live-tree
# helper from node-lib (lio_target_iqns); returns quietly without it or
# when the compute host cannot be gathered (unreachable is not itself a
# restore signature).
detect_vm_refs_missing_live() {
    [[ $(type -t lio_target_iqns 2>/dev/null) == "function" ]] || return 0

    local vm_data=""
    if [[ -n "$ISCSI_DETECT_VM_REFS_FILE" && -f "$ISCSI_DETECT_VM_REFS_FILE" ]]; then
        vm_data=$(cat "$ISCSI_DETECT_VM_REFS_FILE" 2>/dev/null) || vm_data=""
    elif [[ $(type -t iscsi_detect_vm_gather 2>/dev/null) == "function" ]]; then
        vm_data=$(iscsi_detect_vm_gather) || vm_data=""
    else
        return 0
    fi
    [[ -n "$vm_data" ]] || return 0

    local -A live_shorts=() live_slots=()
    local iqn short bs
    while IFS= read -r iqn; do
        [[ -n "$iqn" ]] || continue
        short="${iqn##*:}"
        live_shorts["$short"]=1
        parse_target_luns "$iqn"
        for bs in "${!_lun_indexes[@]}"; do
            live_slots["${short}|${_lun_indexes[$bs]}"]=1
        done
    done < <(lio_target_iqns)

    local -a fields=()
    local disk_id vmid vname vkey lun msg
    while IFS='|' read -r -a fields; do
        [[ "${fields[0]:-}" == "VM" ]] || continue
        disk_id="${fields[1]:-}"
        vmid="${fields[2]:-}"
        vname="${fields[3]:-}"
        vkey="${fields[4]:-}"
        [[ "$disk_id" == *:* ]] || continue
        short="${disk_id%%:*}"
        lun="${disk_id##*:}"
        [[ -n "$lun" && "$lun" != *[!0-9]* ]] || continue
        msg="VM ${vmid} (${vname}) ${vkey} references"
        if [[ -z "${live_shorts[$short]:-}" ]]; then
            msg+=" target ${short} LUN ${lun} — no live iSCSI target carries that name"
            _detect_lines+=("$msg")
        elif [[ -z "${live_slots[${short}|${lun}]:-}" ]]; then
            msg+=" ${short} LUN ${lun} — that LUN is not exported live"
            msg+=" (bare-metal restore signature)"
            _detect_lines+=("$msg")
        fi
    done <<< "$vm_data"
    return 0
}

# Return 0 if a config-table token from `zpool import` output names a zvol
# leaf device: zd<digits> with an optional p<digits> partition suffix (with
# or without a /dev/ prefix), or any /dev/zvol/ path. Guest pools living on
# host zvols (the ITF lab guests reuse production pool names inside their
# disks) are excluded from the duplicate-name signature by this test.
# Fixed-string decomposition only — no regex, no extglob.
_detect_is_zvol_leaf() {
    local tok="${1##*/}"
    if [[ "$1" == /dev/zvol/* ]]; then
        return 0
    fi
    [[ "$tok" == zd* ]] || return 1
    local d="${tok#zd}" p=""
    if [[ "$d" == *p* ]]; then
        p="${d##*p}"
        d="${d%p*}"
        if [[ -z "$p" || "$p" == *[!0-9]* ]]; then
            return 1
        fi
    fi
    [[ -n "$d" && "$d" != *[!0-9]* ]]
}

# Pool-identity detection (the renaming class): a pool renamed or replaced
# under a known name leaves the LUN topology silently serving a different
# pool. Read-only signatures, findings accumulate in _detect_lines and are
# never acted on (identities are human-resolved by design — no auto-rename,
# no auto-repair):
#   (a) an expected pool is not imported, or an imported pool is not
#       expected — the expected set comes from pool_list when node-lib is
#       loaded, else from the map's recorded pools (the standalone
#       check-prerequisites context, where the map is the recorded
#       expected-set);
#   (b) an imported pool's live GUID differs from the map-recorded GUID
#       (a reused name never reuses a GUID);
#   (c) a `zpool import` candidate whose name duplicates an imported pool
#       and whose devices are not zvols (see _detect_is_zvol_leaf).
# Returns quietly when zpool is absent, nothing is imported, no expected-set
# source exists (pre-install gate), or a scan is unreadable — a detector
# never fails the caller.
detect_pool_identity() {
    command -v zpool >/dev/null 2>&1 || return 0

    local imported=""
    imported=$(zpool list -Ho name 2>/dev/null) || return 0
    [[ -n "$imported" ]] || return 0

    local -A map_guid=()
    local map_file name guid
    map_file=$(newest_iscsi_state_map 2>/dev/null) || map_file=""
    if [[ -n "$map_file" ]]; then
        while IFS='|' read -r name guid; do
            [[ -n "$name" ]] && map_guid["$name"]="$guid"
        done < <(read_map_pool_guids "$map_file")
    fi

    # (a) expected vs imported.
    local -A expected=() imported_set=()
    while IFS= read -r name; do
        [[ -n "$name" ]] && imported_set["$name"]=1
    done <<< "$imported"
    if [[ $(type -t pool_list 2>/dev/null) == "function" ]]; then
        while IFS= read -r name; do
            [[ -n "$name" ]] && expected["$name"]=1
        done < <(pool_list)
    else
        for name in "${!map_guid[@]}"; do
            expected["$name"]=1
        done
    fi
    local msg
    if [[ ${#expected[@]} -gt 0 ]]; then
        for name in "${!expected[@]}"; do
            if [[ -z "${imported_set[$name]:-}" ]]; then
                msg="expected pool ${name} is not imported"
                msg+=" — offline, renamed, or replaced"
                _detect_lines+=("$msg")
            fi
        done
        for name in "${!imported_set[@]}"; do
            if [[ -z "${expected[$name]:-}" ]]; then
                msg="imported pool ${name} is not in the node config"
                msg+=" — an unexpected pool is serving data here"
                _detect_lines+=("$msg")
            fi
        done
    fi

    # (b) live GUID vs the map-recorded GUID.
    for name in "${!map_guid[@]}"; do
        [[ -n "${imported_set[$name]:-}" ]] || continue
        guid=$(zpool get -H -o value guid "$name" 2>/dev/null) || guid=""
        if [[ -n "$guid" && "$guid" != *[!0-9]* ]] \
                && [[ "$guid" != "${map_guid[$name]}" ]]; then
            msg="pool ${name} renamed or replaced — map recorded GUID"
            msg+=" ${map_guid[$name]}, live GUID ${guid}"
            _detect_lines+=("$msg")
        fi
    done

    # (c) import candidates duplicating an imported pool name.
    local cand_raw=""
    cand_raw=$(zpool import 2>/dev/null) || cand_raw=""
    [[ -n "$cand_raw" ]] || return 0

    local -a cands=() words=()
    local cpool="" cand_id="" zvol_leaf=false word
    while IFS= read -r name; do
        read -ra words <<< "$name"
        [[ ${#words[@]} -gt 0 ]] || continue
        case "${words[0]}" in
            pool:)
                if [[ -n "$cpool" ]]; then
                    cands+=("${cpool}|${cand_id}|${zvol_leaf}")
                fi
                cpool="${words[1]:-}"
                cand_id=""
                zvol_leaf=false
                ;;
            id:)
                [[ -n "${words[1]:-}" ]] && cand_id="${words[1]}"
                ;;
            *)
                for word in "${words[@]}"; do
                    if _detect_is_zvol_leaf "$word"; then
                        zvol_leaf=true
                        break
                    fi
                done
                ;;
        esac
    done <<< "$cand_raw"
    if [[ -n "$cpool" ]]; then
        cands+=("${cpool}|${cand_id}|${zvol_leaf}")
    fi

    for name in "${cands[@]}"; do
        IFS='|' read -r cpool cand_id zvol_leaf <<< "$name"
        [[ -n "${imported_set[$cpool]:-}" ]] || continue
        [[ "$zvol_leaf" == true ]] && continue
        msg="an importable pool is also named ${cpool}"
        [[ -n "$cand_id" ]] && msg+=" (id ${cand_id})"
        msg+=" on non-zvol devices — the imported pool of that name may not"
        msg+=" be the one the config expects (rename or replacement evidence)"
        _detect_lines+=("$msg")
    done
    return 0
}

# Remove a backstore name from the expected-backstores manifest if present.
function manifest_remove_backstore {
    local bsname="$1"
    if [[ -f "$ISCSI_MANIFEST" ]] && grep -qxF -- "$bsname" "$ISCSI_MANIFEST"; then
        # Drop the exact-line match with awk (fixed string, no regex);
        # cat back into the original path keeps the file inode and mode.
        awk -v b="$bsname" '$0 != b' "$ISCSI_MANIFEST" > "${ISCSI_MANIFEST}.tmp"
        cat -- "${ISCSI_MANIFEST}.tmp" > "$ISCSI_MANIFEST"
        rm -f -- "${ISCSI_MANIFEST}.tmp"
        log_msg "INFO: Removed ${bsname} from expected-backstores manifest"
    fi
}

# Add a backstore name to the expected-backstores manifest if not present.
function manifest_add_backstore {
    local bsname="$1"
    if [[ -f "$ISCSI_MANIFEST" ]] && ! grep -qxF -- "$bsname" "$ISCSI_MANIFEST"; then
        echo "$bsname" >> "$ISCSI_MANIFEST"
        log_msg "INFO: Added ${bsname} to expected-backstores manifest"
    fi
}

# Return 0 if the encrypted-luns config has a line starting with "$1:".
# awk index() replaces the old "^name:" regex anchor without any regex.
_encrypted_conf_has_prefix() {
    [[ -f "$ISCSI_ENCRYPTED_CONF" ]] || return 1
    awk -v b="$1:" 'index($0, b) == 1 { f=1; exit } END { exit !f }' \
        "$ISCSI_ENCRYPTED_CONF"
}

# Remove a backstore entry from the encrypted-luns config if present.
function encrypted_conf_remove_backstore {
    local bsname="$1"
    if _encrypted_conf_has_prefix "$bsname"; then
        # Drop the anchored line (prefix match via index, no regex).
        awk -v b="${bsname}:" 'index($0, b) != 1' "$ISCSI_ENCRYPTED_CONF" \
            > "${ISCSI_ENCRYPTED_CONF}.tmp"
        cat -- "${ISCSI_ENCRYPTED_CONF}.tmp" > "$ISCSI_ENCRYPTED_CONF"
        rm -f -- "${ISCSI_ENCRYPTED_CONF}.tmp"
        log_msg "INFO: Removed ${bsname} from encrypted LUNs config"
    fi
}

# Add a backstore entry to the encrypted-luns config if not present.
# Format: backstore_name:zvol_device:target_short
function encrypted_conf_add_backstore {
    local bsname="$1"
    local zvol_dev="$2"
    local target_short="$3"
    if ! _encrypted_conf_has_prefix "$bsname"; then
        echo "${bsname}:${zvol_dev}:${target_short}" >> "$ISCSI_ENCRYPTED_CONF"
        log_msg "INFO: Added ${bsname} to encrypted LUNs config"
    fi
}

# Remove iSCSI LUN+backstore for a zvol before it is destroyed.
# Only acts on datasets matching vm-<N>-disk-<N> that have a targetcli backstore.
# Records the removal in iscsi_teardown[] so callers can rebuild after zfs receive.
# Returns: 0=done (or not needed), 1=VM is running (caller should abort)
function iscsi_teardown_zvol {
    local dataset="$1"
    local bsname="${dataset##*/}"

    # Identify VM disk zvols by their naming convention.
    # Example: "vm-105-disk-0" matches; "threeamigos/data" does not.
    # Bash glob + prefix/suffix stripping replaces the old vm-<N>-disk-<N>
    # regex; the reconstructed name must equal the original so that only the
    # exact vm-<N>-disk-<N> shape matches, and both parts must be non-empty
    # all-digit strings (the '' case in the glob patterns rejects empties).
    [[ "$bsname" == vm-*-disk-* ]] || return 0
    local _vmid="${bsname#vm-}" _tail
    _vmid="${_vmid%%-disk-*}"
    _tail="${bsname##*-disk-}"
    [[ "vm-${_vmid}-disk-${_tail}" == "$bsname" ]] || return 0
    case $_vmid in ''|*[!0-9]*) return 0 ;; esac
    case $_tail in ''|*[!0-9]*) return 0 ;; esac
    local vmid="$_vmid"

    # In single-node mode, no iSCSI teardown is needed.
    [[ "$node_mode" == "single-node" ]] && return 0

    # Skip if no backstore exists for this name.
    targetcli /backstores/block ls 2>/dev/null \
        | grep -qF -- " ${bsname} " || return 0

    # Skip if the backstore points to a different zvol than the one being deleted.
    # This prevents backup pool datasets from triggering teardown of the live
    # iSCSI backstore on the primary pools.
    local bs_dev
    bs_dev=$(targetcli "/backstores/block/${bsname}" info 2>/dev/null \
        | awk '{for(i=1;i<=NF;i++) if(index($i,"/dev/zvol/")==1){print $i; exit}}')
    if [[ -n "$bs_dev" && "$bs_dev" != "/dev/zvol/${dataset}" ]]; then
        return 0
    fi

    # Discover which target has a LUN for this backstore.
    local target="" lun_num=""
    local t
    while IFS= read -r t; do
        # Strip everything through the first "lun" token and keep the
        # leading digits ("... lun3 [block/..." -> "3").
        lun_num=$(targetcli "/iscsi/${t}/tpg1/luns" ls 2>/dev/null \
            | grep -F -- "$bsname" \
            | while IFS= read -r _lun_line; do
                _lun_rest="${_lun_line#*lun}"
                printf '%s\n' "${_lun_rest%%[!0-9]*}"
            done \
            | head -1)
        if [[ -n "$lun_num" ]]; then
            target="$t"
            break
        fi
    done < <(targetcli /iscsi ls 2>/dev/null | while IFS= read -r _t_line; do
        # targetcli separates each target name from its dotted leader with a
        # space, so the IQN is a whole whitespace-delimited token.
        read -ra _t_words <<< "$_t_line"
        for _t in "${_t_words[@]}"; do
            case "$_t" in iqn.*) printf '%s\n' "$_t" ;; esac
        done
    done)

    if [[ -z "$target" ]]; then
        log_msg "WARN: Backstore $bsname has no matching LUN — removing backstore only."
        targetcli /backstores/block delete "$bsname" 2>/dev/null
        return 0
    fi

    # Verify VM is not running before tearing down.
    local vm_rc
    iscsi_check_vm_running "$vmid"
    vm_rc=$?
    if [[ $vm_rc -eq 1 ]]; then
        log_msg "WARN: VM ${vmid} is running. Stop the VM before deleting $bsname."
        return 1
    elif [[ $vm_rc -eq 2 ]]; then
        log_msg "WARN: Could not verify VM ${vmid} status (${compute_host} unreachable?)." \
            "Proceeding."
    fi

    log_msg "INFO: Removing iSCSI LUN ${lun_num} + backstore ${bsname} from ${target}"
    targetcli "/iscsi/${target}/tpg1/luns" delete "lun${lun_num}" 2>/dev/null
    targetcli /backstores/block delete "$bsname" 2>/dev/null

    # Clean up iSCSI manifests so the backstore is not considered expected after
    # the dataset is destroyed.
    local encrypted_flag="N"
    if _encrypted_conf_has_prefix "$bsname"; then
        encrypted_flag="Y"
    fi
    manifest_remove_backstore "$bsname"
    encrypted_conf_remove_backstore "$bsname"

    iscsi_teardown["$dataset"]="${target}:${lun_num}:${bsname}:${encrypted_flag}"
    log_msg "INFO: iSCSI teardown complete: $bsname (LUN ${lun_num})"
    return 0
}

# Rebuild iSCSI LUNs recorded in iscsi_teardown after a successful zfs receive.
# Preserves original LUN numbers so by-path symlinks on the compute host remain stable.
function iscsi_rebuild_torn_down {
    [[ ${#iscsi_teardown[@]} -gt 0 ]] || return 0

    local dataset target lun_num bsname zvol_dev encrypted_flag rebuilt=false
    for dataset in "${!iscsi_teardown[@]}"; do
        IFS=: read -r target lun_num bsname encrypted_flag <<< "${iscsi_teardown[$dataset]}"
        zvol_dev="/dev/zvol/$dataset"

        # Wait up to 10s for zvol device to appear after zfs receive.
        local _i
        for _i in $(seq 1 20); do
            [[ -b "$zvol_dev" ]] && break
            sleep 0.5
        done

        if [[ ! -b "$zvol_dev" ]]; then
            log_msg "WARN: $zvol_dev not found after receive — cannot rebuild iSCSI for $bsname"
            continue
        fi

        log_msg "INFO: Rebuilding iSCSI: $bsname → LUN ${lun_num} on ${target}"
        targetcli /backstores/block create "$bsname" "$zvol_dev" 2>/dev/null
        targetcli "/iscsi/${target}/tpg1/luns" create \
            "/backstores/block/${bsname}" "$lun_num" 2>/dev/null

        # Restore manifest entries that teardown removed.
        manifest_add_backstore "$bsname"
        if [[ "$encrypted_flag" == "Y" ]]; then
            encrypted_conf_add_backstore "$bsname" "$zvol_dev" "${target##*:}"
        fi

        unset "iscsi_teardown[$dataset]"
        rebuilt=true
        log_msg "INFO: iSCSI rebuild complete: $bsname (LUN ${lun_num})"
    done

    if [[ "$rebuilt" == true && "$node_mode" != "single-node" ]]; then
        log_msg "INFO: Saving iSCSI configuration..."
        local safe_iscsi_save
        safe_iscsi_save=$(find_zfsutility_script safe-iscsi-save)
        "$safe_iscsi_save"
        log_msg "INFO: Triggering iSCSI rescan on ${compute_host}..."
        local rescan_path
        rescan_path=$(remote_zfsutility_script "$compute_host" rescan-storage)
        ssh -o ConnectTimeout=10 root@"$compute_host" \
            "bash -lc $(printf '%q' "$rescan_path")" 2>/dev/null \
            || log_msg "WARN: Could not rescan $compute_host —" \
                "run 'sudo rescan-storage' on $compute_host manually"
    fi
}
