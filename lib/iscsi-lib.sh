#!/usr/bin/bash
# iscsi-lib.sh
# Shared iSCSI helpers: target-state discovery (parse_backstores,
# parse_target_luns, parse_target_acls, discover_zvols, is_vm_backstore_name)
# plus the teardown/rebuild helpers used by zfsdelfs and zfs-send-receive.
#
# This library is sourced at the file level by:
#   - zfsdelfs, to tear down iSCSI LUNs before destroying VM zvols.
#   - zfs-send-receive, to rebuild iSCSI LUNs after a successful zfs receive.
#   - repair-iscsi-luns and export-iscsi-state, for the discovery helpers.
#
# The library loads its own dependencies (bashinit and node-lib.sh) when the
# sourcing context has not already loaded them. The probe is node-lib's
# pool_to_target (not bashinit): zfsdelfs sources bashinit itself but relies
# on this block for node-lib, while repair-iscsi-luns and export-iscsi-state
# source both before this library — and in unit tests a re-load here would
# re-run bashinit's session-log setup and clobber the harness's command mocks.
if [[ $(type -t pool_to_target 2>/dev/null) != "function" ]]; then
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
    done < <(pool_list)
    [[ -n "$best" ]] && printf '%s\n' "$best"
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
