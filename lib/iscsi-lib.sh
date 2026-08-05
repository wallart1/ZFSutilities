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
declare -A ISCSI_TEARDOWN

# iSCSI manifest paths used by teardown/rebuild helpers.
: "${ISCSI_MANIFEST:=/etc/rtslib-fb-target/expected-backstores.txt}"
: "${ISCSI_ENCRYPTED_CONF:=${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}/iscsi-encrypted-luns.conf}"

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
    if [[ "$NODE_MODE" == "single-node" ]]; then
        status=$(qm status "$vmid" 2>/dev/null)
    else
        status=$(ssh -o ConnectTimeout=5 -o BatchMode=yes root@"$COMPUTE_HOST" \
            "qm status $vmid 2>/dev/null" 2>/dev/null)
    fi
    if [[ -z "$status" ]]; then
        return 2
    fi
    echo "$status" | grep -q "status: running" && return 1
    return 0
}

# Remove a backstore name from the expected-backstores manifest if present.
function manifest_remove_backstore {
    local bsname="$1"
    if [[ -f "$ISCSI_MANIFEST" ]] && grep -q "^${bsname}$" "$ISCSI_MANIFEST"; then
        sed -i "/^${bsname}$/d" "$ISCSI_MANIFEST"
        log_msg "INFO: Removed ${bsname} from expected-backstores manifest"
    fi
}

# Add a backstore name to the expected-backstores manifest if not present.
function manifest_add_backstore {
    local bsname="$1"
    if [[ -f "$ISCSI_MANIFEST" ]] && ! grep -q "^${bsname}$" "$ISCSI_MANIFEST"; then
        echo "$bsname" >> "$ISCSI_MANIFEST"
        log_msg "INFO: Added ${bsname} to expected-backstores manifest"
    fi
}

# Remove a backstore entry from the encrypted-luns config if present.
function encrypted_conf_remove_backstore {
    local bsname="$1"
    if [[ -f "$ISCSI_ENCRYPTED_CONF" ]] && grep -q "^${bsname}:" "$ISCSI_ENCRYPTED_CONF"; then
        sed -i "/^${bsname}:/d" "$ISCSI_ENCRYPTED_CONF"
        log_msg "INFO: Removed ${bsname} from encrypted LUNs config"
    fi
}

# Add a backstore entry to the encrypted-luns config if not present.
# Format: backstore_name:zvol_device:target_short
function encrypted_conf_add_backstore {
    local bsname="$1"
    local zvol_dev="$2"
    local target_short="$3"
    if [[ -f "$ISCSI_ENCRYPTED_CONF" ]] && ! grep -q "^${bsname}:" "$ISCSI_ENCRYPTED_CONF"; then
        echo "${bsname}:${zvol_dev}:${target_short}" >> "$ISCSI_ENCRYPTED_CONF"
        log_msg "INFO: Added ${bsname} to encrypted LUNs config"
    fi
}

# Remove iSCSI LUN+backstore for a zvol before it is destroyed.
# Only acts on datasets matching vm-<N>-disk-<N> that have a targetcli backstore.
# Records the removal in ISCSI_TEARDOWN[] so callers can rebuild after zfs receive.
# Returns: 0=done (or not needed), 1=VM is running (caller should abort)
function iscsi_teardown_zvol {
    local dataset="$1"
    local bsname="${dataset##*/}"

    # Identify VM disk zvols by their naming convention.
    # Example: "vm-105-disk-0" matches; "threeamigos/data" does not.
    [[ "$bsname" =~ ^vm-([0-9]+)-disk-[0-9]+$ ]] || return 0
    local vmid="${BASH_REMATCH[1]}"

    # In single-node mode, no iSCSI teardown is needed.
    [[ "$NODE_MODE" == "single-node" ]] && return 0

    # Skip if no backstore exists for this name.
    targetcli /backstores/block ls 2>/dev/null | grep -q " ${bsname} " || return 0

    # Skip if the backstore points to a different zvol than the one being deleted.
    # This prevents backup pool datasets from triggering teardown of the live
    # iSCSI backstore on the primary pools.
    local bs_dev
    bs_dev=$(targetcli "/backstores/block/${bsname}" info 2>/dev/null \
        | grep -oP '/dev/zvol/\S+' | head -1)
    if [[ -n "$bs_dev" && "$bs_dev" != "/dev/zvol/${dataset}" ]]; then
        return 0
    fi

    # Discover which target has a LUN for this backstore.
    local target="" lun_num=""
    local t
    while IFS= read -r t; do
        lun_num=$(targetcli "/iscsi/${t}/tpg1/luns" ls 2>/dev/null \
            | grep "$bsname" | grep -oP 'lun\K[0-9]+' | head -1)
        if [[ -n "$lun_num" ]]; then
            target="$t"
            break
        fi
    done < <(targetcli /iscsi ls 2>/dev/null | grep -oP 'iqn\.\S+')

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
        log_msg "WARN: Could not verify VM ${vmid} status (${COMPUTE_HOST} unreachable?)." \
            "Proceeding."
    fi

    log_msg "INFO: Removing iSCSI LUN ${lun_num} + backstore ${bsname} from ${target}"
    targetcli "/iscsi/${target}/tpg1/luns" delete "lun${lun_num}" 2>/dev/null
    targetcli /backstores/block delete "$bsname" 2>/dev/null

    # Clean up iSCSI manifests so the backstore is not considered expected after
    # the dataset is destroyed.
    local encrypted_flag="N"
    if [[ -f "$ISCSI_ENCRYPTED_CONF" ]] && grep -q "^${bsname}:" "$ISCSI_ENCRYPTED_CONF"; then
        encrypted_flag="Y"
    fi
    manifest_remove_backstore "$bsname"
    encrypted_conf_remove_backstore "$bsname"

    ISCSI_TEARDOWN["$dataset"]="${target}:${lun_num}:${bsname}:${encrypted_flag}"
    log_msg "INFO: iSCSI teardown complete: $bsname (LUN ${lun_num})"
    return 0
}

# Rebuild iSCSI LUNs recorded in ISCSI_TEARDOWN after a successful zfs receive.
# Preserves original LUN numbers so by-path symlinks on the compute host remain stable.
function iscsi_rebuild_torn_down {
    [[ ${#ISCSI_TEARDOWN[@]} -gt 0 ]] || return 0

    local dataset target lun_num bsname zvol_dev encrypted_flag rebuilt=false
    for dataset in "${!ISCSI_TEARDOWN[@]}"; do
        IFS=: read -r target lun_num bsname encrypted_flag <<< "${ISCSI_TEARDOWN[$dataset]}"
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
        targetcli "/iscsi/${target}/tpg1/luns" create "/backstores/block/${bsname}" "$lun_num" 2>/dev/null

        # Restore manifest entries that teardown removed.
        manifest_add_backstore "$bsname"
        if [[ "$encrypted_flag" == "Y" ]]; then
            encrypted_conf_add_backstore "$bsname" "$zvol_dev" "${target##*:}"
        fi

        unset "ISCSI_TEARDOWN[$dataset]"
        rebuilt=true
        log_msg "INFO: iSCSI rebuild complete: $bsname (LUN ${lun_num})"
    done

    if [[ "$rebuilt" == true && "$NODE_MODE" != "single-node" ]]; then
        log_msg "INFO: Saving iSCSI configuration..."
        local safe_iscsi_save
        safe_iscsi_save=$(find_zfsutility_script safe-iscsi-save)
        "$safe_iscsi_save"
        log_msg "INFO: Triggering iSCSI rescan on ${COMPUTE_HOST}..."
        local rescan_path
        rescan_path=$(remote_zfsutility_script "$COMPUTE_HOST" rescan-storage)
        ssh -o ConnectTimeout=10 root@"$COMPUTE_HOST" \
            "bash -lc $(printf '%q' "$rescan_path")" 2>/dev/null \
            || log_msg "WARN: Could not rescan $COMPUTE_HOST —" \
                "run 'sudo rescan-storage' on $COMPUTE_HOST manually"
    fi
}
