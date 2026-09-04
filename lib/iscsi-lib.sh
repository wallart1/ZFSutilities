#!/usr/bin/bash
# iscsi-lib.sh
# Shared iSCSI teardown/rebuild helpers used by zfsdelfs and zfs-send-receive.
#
# This library is sourced at the file level by both scripts so that:
#   - zfsdelfs can tear down iSCSI LUNs before destroying VM zvols.
#   - zfs-send-receive can rebuild iSCSI LUNs after a successful zfs receive.
#
# The library loads its own dependencies (bashinit and node-lib.sh).

source ~/bashinit
bashinit

NODE_LIB="${NODE_LIB:-$(find_zfsutility_script node-lib.sh)}"
if [[ -z "$NODE_LIB" ]]; then
    log_msg "FATAL: Could not locate node-lib.sh"
    exit 1
fi
source "$NODE_LIB"

# Tracks iSCSI LUNs torn down during dataset deletion.
# Key: dataset name. Value: "target:lun_num:backstore_name:encrypted_flag"
# Populated by iscsi_teardown_zvol; consumed by iscsi_rebuild_torn_down.
# encrypted_flag is "Y" if the backstore was listed in /etc/iscsi-encrypted-luns.conf.
declare -A iscsi_teardown

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
