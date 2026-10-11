# lib/archive-engine.sh — shared transfer engine for archive-vm/unarchive-vm.
# Sourced by bin/archive-vm and bin/unarchive-vm on the compute host AND by
# their two-node SSH helpers on the storage host, so both node modes run
# literally the same transfer logic. Requires bashinit (log_msg,
# append_exit_trap) to be sourced first.
#
# Volblocksize policy: volblocksize is creation-only and always travels
# inside a zfs send stream; overriding volblocksize at receive time is
# refused by current OpenZFS userland and is meaningless for raw streams.
# Reblocking therefore only happens by creating the destination zvol with
# the target volblocksize and device-copying onto it:
#   - unencrypted zvols   → device copy, archived at volblocksize=1M
#   - encrypted zvols     → raw send/receive as-is (a device copy would read
#                           plaintext and break encryption end-to-end)

# Wait for a /dev/zvol device node to appear (udev settle after
# snapdev=visible or zfs create). Bounded; prints nothing.
archive_dev_wait() {
    local dev="$1"
    local i
    # The unit-test harnesses mock zfs but have no /dev/zvol tree.
    [[ ${ARCHIVE_VM_TEST_NO_ROOT:-0} == "1" ]] && return 0
    [[ ${UNARCHIVE_VM_TEST_NO_ROOT:-0} == "1" ]] && return 0
    for ((i = 0; i < 30; i++)); do
        [[ -e "$dev" ]] && return 0
        sleep 1
    done
    return 1
}

# Hash two block devices and compare their logical content — end-to-end
# integrity for the device-copy path, which has no stream checksums.
# Prints the verification result; returns 1 on mismatch or hash failure.
archive_hash_verify() {
    local src="$1" dst="$2"
    local out line1 line2 rest h1 h2
    log_msg "INFO:   Verifying copy integrity (sha256)..."
    out=$(sha256sum "$src" "$dst" 2>/dev/null) || {
        log_msg "FATAL: Failed to hash devices"
        return 1
    }
    line1="${out%%$'\n'*}"
    rest="${out#*$'\n'}"
    line2="${rest%%$'\n'*}"
    h1="${line1%%[[:space:]]*}"
    h2="${line2%%[[:space:]]*}"
    if [[ -z "$h1" || -z "$h2" || "$h1" != "$h2" ]]; then
        log_msg "FATAL: Hash mismatch between ${src} and ${dst}"
        log_msg "FATAL: The archive copy is corrupt; re-run the archive."
        return 1
    fi
    log_msg "INFO:   ✓ Copy verified (sha256 match)"
    return 0
}

# Find the shallowest missing ancestor of $1 (walking up until an existing
# dataset hides the rest of the chain) and create the whole chain with one
# `zfs create -p`. Sets the caller-visible variable named by $2 to the
# shallowest created level ("" when nothing was created) so a failed run can
# destroy exactly what it introduced — never a pre-existing empty ancestor.
archive_create_parents() {
    local parent="$1" created_var="$2"
    local level="$parent"
    local created_root=""
    while [[ -n "$level" && "$level" != "." && "$level" != "/" ]]; do
        if zfs list -H -o name "$level" 2>/dev/null | grep -qxF -- "$level"; then
            break
        fi
        created_root="$level"
        level=$(dirname "$level")
    done
    if [[ -n "$created_root" ]]; then
        zfs create -p "$parent" || return 1
    fi
    # Dynamic scoping: the caller declares the variable local; printf -v
    # assigns it there without leaking an export into the environment.
    printf -v "$created_var" '%s' "$created_root"
    return 0
}

# Destroy a zvol this run created plus the parent chain this run created
# (created_root from archive_create_parents; destroy -r removes the chain).
archive_rollback_created() {
    local dataset="$1" dataset_created="$2" created_root="$3"
    if [[ "$dataset_created" == "1" ]]; then
        zfs destroy -r "$dataset" 2>/dev/null || true
        log_msg "WARN: Removed partial archive dataset ${dataset}"
    fi
    if [[ -n "$created_root" ]]; then
        zfs destroy -r "$created_root" 2>/dev/null || true
        log_msg "WARN: Removed created parent ${created_root}"
    fi
}

# Archive one zvol from <zvol><snap_name> into <archive_dataset>, writing
# the .original_volblocksize sidecar and the METHOD= line of .disk_info
# under <archive_mount> (the caller appends DISK_KEY/LUN/TARGET). Returns
# 0 on success; on failure the reason is logged, this run's datasets are
# rolled back, and 1 is returned.
archive_one_zvol() {
    local zvol="$1" snap_name="$2" archive_dataset="$3" archive_mount="$4"
    local orig_vbs encryption volsize snapdev_prev method
    local created_root="" dataset_created=0 snapdev_changed=0
    local src_dev dst_dev snapdev_arg

    orig_vbs=$(zfs get -H -o value volblocksize "$zvol")
    log_msg "INFO:   Original volblocksize: ${orig_vbs}"
    encryption=$(zfs get -H -o value encryption "$zvol")

    if ! archive_create_parents "$(dirname "$archive_dataset")" created_root; then
        log_msg "FATAL: Failed to create parent dataset for ${archive_dataset}"
        return 1
    fi

    if [[ "$encryption" == "off" || "$encryption" == "-" ]]; then
        method=copy
        log_msg "INFO:   Archive method: device copy (reblock to 1M)"
        volsize=$(zfs get -H -o value volsize "$zvol")
        snapdev_prev=$(zfs get -H -o value snapdev "$zvol")
        if [[ "$snapdev_prev" != "visible" ]]; then
            if ! zfs set snapdev=visible "$zvol"; then
                log_msg "FATAL: Failed to expose snapshot device on ${zvol}"
                archive_rollback_created "$archive_dataset" 0 "$created_root"
                return 1
            fi
            snapdev_changed=1
            snapdev_arg="$snapdev_prev"
            # Revert even when killed mid-copy: a visible snapdev must not
            # outlive this run. Harmlessly re-applied after clean reverts.
            if declare -f append_exit_trap >/dev/null 2>&1; then
                append_exit_trap \
                    "zfs set snapdev=${snapdev_arg} ${zvol} 2>/dev/null || true"
            fi
        fi
        if zfs list -H -o name "$archive_dataset" 2>/dev/null \
                | grep -qxF -- "$archive_dataset"; then
            log_msg "FATAL: Archive dataset already exists: ${archive_dataset}"
            log_msg "FATAL: Destroy it first to re-archive: zfs destroy -r ${archive_dataset}"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            return 1
        fi
        src_dev="/dev/zvol/${zvol}${snap_name}"
        if ! archive_dev_wait "$src_dev"; then
            log_msg "FATAL: Snapshot device did not appear: ${src_dev}"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            return 1
        fi
        if ! zfs create -s -V "$volsize" -o volblocksize=1M "$archive_dataset"; then
            log_msg "FATAL: Failed to create archive zvol ${archive_dataset}"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" 0 "$created_root"
            return 1
        fi
        dataset_created=1
        dst_dev="/dev/zvol/${archive_dataset}"
        if ! archive_dev_wait "$dst_dev"; then
            log_msg "FATAL: Archive device did not appear: ${dst_dev}"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        if ! cp --sparse=always "$src_dev" "$dst_dev"; then
            log_msg "FATAL: Device copy failed (${src_dev} → ${dst_dev})"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        sync "$dst_dev" 2>/dev/null || sync
        if ! archive_hash_verify "$src_dev" "$dst_dev"; then
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        if ! zfs snapshot "${archive_dataset}@archive"; then
            log_msg "FATAL: Failed to snapshot archived zvol ${archive_dataset}@archive"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        if [[ "$snapdev_changed" == "1" ]]; then
            zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
            snapdev_changed=0
        fi
    else
        method=raw
        log_msg "INFO:   Archive method: raw send/receive (encrypted)"
        if ! zfs send -cw "${zvol}${snap_name}" | zfs receive "$archive_dataset"; then
            log_msg "FATAL: Failed to archive ${zvol} (raw send/receive)"
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
    fi

    mkdir -p "$(dirname "${archive_mount}/${zvol}.original_volblocksize")"
    echo "$orig_vbs" > "${archive_mount}/${zvol}.original_volblocksize"
    echo "METHOD=${method}" > "${archive_mount}/${zvol}.disk_info"
    return 0
}

# Read the METHOD= line from an archive's .disk_info sidecar. Unmarked
# archives predate the method marker and were made by raw send/receive.
archive_method_of() {
    local info_file="$1"
    local method
    method=$(grep '^METHOD=' "$info_file" 2>/dev/null | cut -d= -f2)
    echo "${method:-raw}"
}

# Restore one archived zvol <arc_dataset> (original relative path
# <orig_zvol>, sidecars under <archive_mount>) to <new_zvol> using the
# recorded method. Returns 0 on success; on failure the reason is logged,
# this run's datasets are rolled back, and 1 is returned. The zvol write
# lock is the caller's responsibility.
unarchive_one_zvol() {
    local arc_dataset="$1" orig_zvol="$2" new_zvol="$3" archive_mount="$4"
    local info_file vbs_file method orig_vbs
    local snap snap_name volsize snapdev_prev snapdev_changed=0
    local created_root="" dataset_created=0 src_dev dst_dev

    info_file="${archive_mount}/${orig_zvol}.disk_info"
    vbs_file="${archive_mount}/${orig_zvol}.original_volblocksize"

    method=$(archive_method_of "$info_file")
    if [[ "$method" != "copy" && "$method" != "raw" ]]; then
        log_msg "FATAL: Unknown archive method '${method}' in ${info_file}"
        return 1
    fi

    snap=$(zfs list -H -t snapshot -o name -S creation "$arc_dataset" 2>/dev/null | head -1)
    if [[ -z "$snap" ]]; then
        log_msg "FATAL: No snapshots found on archive dataset: $arc_dataset"
        return 1
    fi
    snap_name="@${snap##*@}"

    if ! archive_create_parents "$(dirname "$new_zvol")" created_root; then
        log_msg "FATAL: Failed to create parent dataset for ${new_zvol}"
        return 1
    fi

    if [[ "$method" == "copy" ]]; then
        if [[ ! -s "$vbs_file" ]]; then
            log_msg "FATAL: Missing volblocksize sidecar for copy-method restore:"
            log_msg "FATAL:   ${vbs_file}"
            return 1
        fi
        orig_vbs=$(cat "$vbs_file")
        log_msg "INFO:   Restore method: copy (reblock to ${orig_vbs})"
        volsize=$(zfs get -H -o value volsize "$arc_dataset")
        snapdev_prev=$(zfs get -H -o value snapdev "$arc_dataset")
        if [[ "$snapdev_prev" != "visible" ]]; then
            if ! zfs set snapdev=visible "$arc_dataset"; then
                log_msg "FATAL: Failed to expose snapshot device on ${arc_dataset}"
                return 1
            fi
            snapdev_changed=1
            if declare -f append_exit_trap >/dev/null 2>&1; then
                append_exit_trap \
                    "zfs set snapdev=${snapdev_prev} ${arc_dataset} 2>/dev/null || true"
            fi
        fi
        src_dev="/dev/zvol/${snap}"
        if ! archive_dev_wait "$src_dev"; then
            log_msg "FATAL: Snapshot device did not appear: ${src_dev}"
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            return 1
        fi
        if ! zfs create -s -V "$volsize" -o volblocksize="$orig_vbs" "$new_zvol"; then
            log_msg "FATAL: Failed to create zvol ${new_zvol}"
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            return 1
        fi
        dataset_created=1
        dst_dev="/dev/zvol/${new_zvol}"
        if ! archive_dev_wait "$dst_dev"; then
            log_msg "FATAL: Restore device did not appear: ${dst_dev}"
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
        if ! cp --sparse=always "$src_dev" "$dst_dev"; then
            log_msg "FATAL: Device copy failed (${src_dev} → ${dst_dev})"
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
        sync "$dst_dev" 2>/dev/null || sync
        if ! archive_hash_verify "$src_dev" "$dst_dev"; then
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
        if [[ "$snapdev_changed" == "1" ]]; then
            zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            snapdev_changed=0
        fi
    else
        log_msg "INFO:   Restore method: raw send/receive"
        if ! zfs send -cw "${arc_dataset}${snap_name}" | zfs receive "$new_zvol"; then
            log_msg "FATAL: Failed to restore ${new_zvol} (raw send/receive)"
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
    fi
    return 0
}

# Mirror of archive_rollback_created for the restore direction (message
# wording says "restore", not "archive").
unarchive_rollback_created() {
    local dataset="$1" dataset_created="$2" created_root="$3"
    if [[ "$dataset_created" == "1" ]]; then
        zfs destroy -r "$dataset" 2>/dev/null || true
        log_msg "WARN: Removed partial restored zvol ${dataset}"
    fi
    if [[ -n "$created_root" ]]; then
        zfs destroy -r "$created_root" 2>/dev/null || true
        log_msg "WARN: Removed created parent ${created_root}"
    fi
}
