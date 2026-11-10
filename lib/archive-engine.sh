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
#
# Pacing: the effective rate for a run is the minimum of
# $transfer_rate_limit (the prompted archive rate) and every per-enclosure
# cap of every enclosure touched by the source and destination pools,
# resolved once per archived/restored zvol through the shared resolver
# lib/enclosure_rate.py — an enclosure cap applies even when no archive
# rate was prompted. Every data movement — device copy, hash verification,
# raw send/receive — is passed through the python pacer lib/pace_stream.py
# at that combined rate so an archive run cannot saturate a small storage
# host. Resolver failures fail open: a loud WARN and the prompted rate as
# before caps existed, never a blocked archive. The pacer caps the stream
# flat: a stalled pipeline forfeits the missed budget instead of buying a
# later burst (pv -L enforced only a long-run average and burst to
# 1.5-3.5x the cap after every ZFS txg/throttle stall). Empty or unset
# means unlimited (a plain dd reader).
#
# Progress: every data movement — device copy, hash verification, raw
# send/receive — can show a live one-line progress display (bar, percent,
# elapsed, ETA, rate, bytes) through a display-only pv stage, the same law
# as lib/transfer-lib.sh's transfer_pv_args: natural in-place display when
# stderr is a terminal, forced output (-f) when a capturing parent set
# ZFSUTILITIES_LOG_INHERIT=Y, and no stage otherwise. The stage is
# display-only: pv writes to stderr, never through log_msg, so a run with
# progress showing adds nothing to the session log. The invoking script
# sets $archive_progress_mode (tty|force|empty) once from ITS stderr —
# across a two-node ssh hop the remote engine's stderr is a pipe and
# cannot test the operator's terminal itself, so the mode rides over as
# an on_storage payload argument. A missing pv binary or an unknown mode
# silently drops the display; progress must never fail a transfer.
#
# Integrity: the device-copy path carries no stream checksums, so its
# source is hashed in flight — the copy stream is teed to a background
# sha256sum through a fifo — and the destination is read back after the
# copy and compared against that digest. The source device is read
# exactly once per copy; only the destination gets a second pass.

# True when $1 is a valid rate value (digits plus an optional K/M/G/T/P/E
# suffix with optional i and B, case-insensitive; the grammar
# lib/pace_stream.py parses) or is empty (= unlimited). A rate of zero is
# refused — the pacer divides by the rate, so zero cannot be paced.
# Implemented with parameter expansion and a case list so no regex exceeds
# the 10-character policy limit.
archive_valid_rate() {
    local rate="$1" num suffix lower
    [[ -z "$rate" ]] && return 0
    num="${rate%%[!0-9]*}"
    [[ -n "$num" ]] || return 1
    # Strip the leading zeros; an empty remainder means the rate is zero.
    [[ -n "${num#"${num%%[!0]*}"}" ]] || return 1
    suffix="${rate#"$num"}"
    lower="${suffix,,}"
    case "$lower" in
        ""|k|m|g|t|p|e|ki|mi|gi|ti|pi|ei|kb|mb|gb|tb|pb|eb|kib|mib|gib|tib|pib|eib)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Resolve the python pacing helper (lib/pace_stream.py) once per run into
# _archive_pacer. The helper lives beside this library in every layout
# (repo, deployed, absolute-path sourcing), so BASH_SOURCE's own directory
# is authoritative; find_zfsutility_script is a fallback for unusual
# deployments. Returns 1 when not found so a paced run fails loudly
# instead of silently running unlimited.
archive_pacer() {
    local candidate
    if [[ -z "${_archive_pacer:-}" ]]; then
        candidate="$(dirname "${BASH_SOURCE[0]}")/pace_stream.py"
        if [[ -f "$candidate" ]]; then
            _archive_pacer="$candidate"
        elif declare -f find_zfsutility_script >/dev/null 2>&1; then
            _archive_pacer=$(find_zfsutility_script pace_stream.py 2>/dev/null || true)
        fi
    fi
    [[ -n "${_archive_pacer:-}" ]]
}

# Resolve the per-enclosure rate resolver (lib/enclosure_rate.py) once per
# run into _archive_resolver — same resolution law as archive_pacer
# (BASH_SOURCE's own directory first, find_zfsutility_script fallback);
# $ZFSUTILITIES_ENCLOSURE_RATE overrides the location for tests and unusual
# deployments. Returns 1 when not found; callers fail open, never fatally.
archive_resolver() {
    local candidate="${ZFSUTILITIES_ENCLOSURE_RATE:-}"
    if [[ -n "$candidate" ]]; then
        # Re-check every call: tests repoint the env at per-test fakes, and
        # a vanished override must not leave a stale resolution behind.
        _archive_resolver=""
        [[ -x "$candidate" ]] && _archive_resolver="$candidate"
    elif [[ -z "${_archive_resolver:-}" ]]; then
        candidate="$(dirname "${BASH_SOURCE[0]}")/enclosure_rate.py"
        if [[ -x "$candidate" ]]; then
            _archive_resolver="$candidate"
        elif declare -f find_zfsutility_script >/dev/null 2>&1; then
            candidate=$(find_zfsutility_script enclosure_rate.py 2>/dev/null || true)
            [[ -x "$candidate" ]] && _archive_resolver="$candidate"
        fi
    fi
    [[ -n "${_archive_resolver:-}" ]]
}

# Resolve the run's effective rate once: the minimum of $3 (the prompted
# activity rate, empty = unlimited) and every enclosure cap of the pools of
# the $1 source and $2 destination datasets (pool = first path component).
# Prints the winning rate (empty = unlimited). Fails open per campaign
# policy: a missing resolver or any resolver failure logs a loud WARN and
# prints the activity rate unchanged — an archive run never blocks on an
# enclosure-scan hiccup. Logs an INFO when an enclosure cap changes the
# pace. The resolver's stderr flows straight through to the session log;
# only its stdout is the rate.
archive_resolve_rate() {
    local src="$1" dst="$2" rate_limit="$3"
    local src_pool dst_pool combined
    src_pool="${src%%/*}"
    dst_pool="${dst%%/*}"
    if ! archive_resolver; then
        log_msg "WARN: Enclosure rate resolution failed" \
            "(enclosure_rate.py not found); ignoring enclosure caps for this transfer"
        printf '%s' "$rate_limit"
        return 0
    fi
    if ! combined=$("$_archive_resolver" --min-with "$rate_limit" \
            "$src_pool" "$dst_pool"); then
        log_msg "WARN: Enclosure rate resolution failed;" \
            "ignoring enclosure caps for this transfer"
        printf '%s' "$rate_limit"
        return 0
    fi
    if [[ -n "$combined" && "$combined" != "$rate_limit" ]]; then
        # Pace-changing notice: the run is about to move at a rate the
        # operator did not type, so it is shown even when a driven flow
        # gates INFO off the terminal (the empty prefix assignment lifts
        # the ZFSUTILITIES_MSG_LEVEL gate for this one call only).
        ZFSUTILITIES_MSG_LEVEL='' log_msg "INFO: Enclosure rate cap applied: ${combined}"
    fi
    printf '%s' "$combined"
}

# Copy one block device onto another while hashing the source stream in
# flight: the bytes are teed to a background sha256sum through a fifo, so
# the source device is read exactly once per archive (the copy and its
# hash share one pass). The destination is NOT hashed here — it is read
# back separately, after sync, by archive_hash_verify, which compares
# that digest against the one stored into the caller-visible variable
# named by $3 (declare it local at the call site; printf -v assigns
# through bash's dynamic scoping, like archive_create_parents).
#
# Pacing: a paced run throttles the read head through lib/pace_stream.py
# (python3); an unlimited run reads with dd. Both write through the same
# tee→fifo hash side-channel into the same sparse writer — dd conv=sparse
# seeks all-zero input rather than writing it, at the dd block-size
# granularity, so a thin archive zvol stays thin either way.
#
# Progress: the optional $4 (total bytes) arms a display-only pv stage
# between the tee and the writer dd (see archive_pv_args); omitted or
# empty plus a display mode leaves the stage sizeless, and no display
# mode leaves the pipelines byte-identical to a display-less run.
#
# Failure containment: a dead hash consumer or a dead writer breaks the
# pipeline via SIGPIPE and pipefail, so a partial copy or a truncated
# hash can never return success.
archive_copy_devices() {
    local src="$1" dst="$2" hash_var="$3" total_bytes="${4:-}"
    local tmp_dir fifo hash_file sha_pid pipe_rc=0 sha_rc=0 hash=""
    if [[ -n "${transfer_rate_limit:-}" ]] && ! archive_pacer; then
        log_msg "FATAL: Rate limit set but pace_stream.py not found"
        return 1
    fi
    archive_pv_args "$total_bytes"
    tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/zfsutilities-copy.XXXXXX") || return 1
    fifo="${tmp_dir}/hash.fifo"
    hash_file="${tmp_dir}/src.sha256"
    if ! mkfifo "$fifo"; then
        rm -rf "$tmp_dir"
        return 1
    fi
    # Kill-mid-copy backstop; the normal return paths remove the directory
    # themselves (accumulated trap strings for already-removed directories
    # are harmless no-ops, like the snapdev revert traps).
    if declare -f append_exit_trap >/dev/null 2>&1; then
        append_exit_trap "rm -rf '${tmp_dir}'"
    fi
    sha256sum < "$fifo" > "$hash_file" 2>/dev/null &
    sha_pid=$!
    # Four explicit pipeline variants (the transfer_do law): an empty pv
    # array cannot collapse into the next segment, and a paced reader and
    # a display stage are independent choices. Every dd runs quiet
    # (status=none); the pv stage owns the terminal display.
    if [[ -n "${transfer_rate_limit:-}" && ${#archive_pv_args[@]} -gt 0 ]]; then
        ( set -o pipefail
          python3 "$_archive_pacer" "$transfer_rate_limit" -- "$src" \
              | tee "$fifo" \
              | pv "${archive_pv_args[@]}" \
              | dd of="$dst" bs=16M conv=sparse,notrunc iflag=fullblock status=none
        ) || pipe_rc=1
    elif [[ -n "${transfer_rate_limit:-}" ]]; then
        ( set -o pipefail
          python3 "$_archive_pacer" "$transfer_rate_limit" -- "$src" \
              | tee "$fifo" \
              | dd of="$dst" bs=16M conv=sparse,notrunc iflag=fullblock status=none
        ) || pipe_rc=1
    elif [[ ${#archive_pv_args[@]} -gt 0 ]]; then
        ( set -o pipefail
          dd if="$src" bs=16M iflag=fullblock status=none \
              | tee "$fifo" \
              | pv "${archive_pv_args[@]}" \
              | dd of="$dst" bs=16M conv=sparse,notrunc iflag=fullblock status=none
        ) || pipe_rc=1
    else
        ( set -o pipefail
          dd if="$src" bs=16M iflag=fullblock status=none \
              | tee "$fifo" \
              | dd of="$dst" bs=16M conv=sparse,notrunc iflag=fullblock status=none
        ) || pipe_rc=1
    fi
    # The wait closes the truncated-stream race: only after sha256sum
    # exits is the hash file complete.
    wait "$sha_pid" || sha_rc=1
    hash=$(awk '{ print $1 }' "$hash_file" 2>/dev/null)
    rm -rf "$tmp_dir"
    printf -v "$hash_var" '%s' "$hash"
    if [[ "$pipe_rc" -ne 0 ]]; then
        return 1
    fi
    if [[ "$sha_rc" -ne 0 || -z "$hash" ]]; then
        log_msg "FATAL: Failed to hash source during copy"
        return 1
    fi
    return 0
}

# Build the optional pacing segment for a raw send/receive pipeline into
# the pace_pipe array (empty when unlimited). Usage:
#   archive_pace_pipe; zfs send ... | "${pace_pipe[@]}" | zfs receive ...
# The pacer is a standalone filter segment (its CLI takes <rate> [--] [file]
# only — trailing pipeline words belong to the NEXT segment, never here).
# Returns 1 (with a FATAL log) when a rate is set but the pacer cannot be
# resolved.
archive_pace_pipe() {
    pace_pipe=()
    if [[ -n "${transfer_rate_limit:-}" ]]; then
        if ! archive_pacer; then
            log_msg "FATAL: Rate limit set but pace_stream.py not found"
            return 1
        fi
        pace_pipe=(python3 "$_archive_pacer" "$transfer_rate_limit")
    fi
}

# Build the optional progress display options into the archive_pv_args
# array (empty when off) — the engine counterpart of transfer-lib's
# transfer_pv_args. Usage:
#   archive_pv_args [total_bytes]
#   ... | pv "${archive_pv_args[@]}" | <next stage> ...
# The array holds OPTION WORDS ONLY: pv must stand as its own pipeline
# segment, because any word after pv's options would be taken as a file
# operand — `... | "${archive_pv_args[@]}" dd of=...` would make pv try to
# open "dd" and "of=..." as input files. $archive_progress_mode is set
# once by the invoking script (tty|force|empty; see the header). -B 16M
# matches the dd writer's block size so the display stage cannot throttle
# the copy; -s is added only when the caller knows the total. A missing
# pv binary or an unrecognized mode silently drops the display.
archive_pv_args() {
    archive_pv_args=()
    case "${archive_progress_mode:-}" in
        tty|force) ;;
        *) return 0 ;;
    esac
    command -v pv >/dev/null 2>&1 || return 0
    local -a pv_opts=(-pterb -B 16M)
    if [[ "$archive_progress_mode" == "force" ]]; then
        pv_opts=(-fpterb -B 16M)
    fi
    if [[ -n "${1:-}" ]]; then
        pv_opts+=(-s "$1")
    fi
    archive_pv_args=("${pv_opts[@]}")
}

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

# Read back the destination device ($2) and compare its digest against the
# in-flight source hash captured by archive_copy_devices — end-to-end
# integrity for the device-copy path, which has no stream checksums. Only
# the destination is read; $1 names the source for the mismatch messages.
# Prints the verification result; returns 1 on mismatch or hash failure.
# The optional $4 (total bytes) sizes the display-only pv stage (see
# archive_pv_args); with no display mode the pipelines are unchanged.
archive_hash_verify() {
    local src="$1" dst="$2" expected="$3" total_bytes="${4:-}"
    local h2
    log_msg "INFO:   Verifying copy integrity (sha256)..."
    archive_pv_args "$total_bytes"
    if [[ -n "${transfer_rate_limit:-}" ]]; then
        # Rate-capped hashing: read the device through the pacer so the
        # verify pass cannot saturate the pool; sha256sum of stdin yields
        # the same digest as of the file.
        if ! archive_pacer; then
            log_msg "FATAL: Rate limit set but pace_stream.py not found"
            return 1
        fi
        if [[ ${#archive_pv_args[@]} -gt 0 ]]; then
            h2=$(python3 "$_archive_pacer" "$transfer_rate_limit" -- "$dst" \
                | pv "${archive_pv_args[@]}" | sha256sum 2>/dev/null) || {
                log_msg "FATAL: Failed to hash devices"
                return 1
            }
        else
            h2=$(python3 "$_archive_pacer" "$transfer_rate_limit" -- "$dst" \
                | sha256sum 2>/dev/null) || {
                log_msg "FATAL: Failed to hash devices"
                return 1
            }
        fi
    elif [[ ${#archive_pv_args[@]} -gt 0 ]]; then
        # Unlimited with a display: pv is the reader (the device is its
        # file operand) and sha256sum digests the stream.
        h2=$(pv "${archive_pv_args[@]}" "$dst" | sha256sum 2>/dev/null) || {
            log_msg "FATAL: Failed to hash devices"
            return 1
        }
    else
        h2=$(sha256sum "$dst" 2>/dev/null) || {
            log_msg "FATAL: Failed to hash devices"
            return 1
        }
    fi
    h2="${h2%%[[:space:]]*}"
    if [[ -z "$expected" || -z "$h2" || "$expected" != "$h2" ]]; then
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
    local src_dev dst_dev snapdev_arg copy_src_hash=""
    local volsize_bytes="" raw_size=""

    # One resolver call per run (rate governance): the local shadow of
    # transfer_rate_limit carries the combined rate — min(prompted rate,
    # enclosure caps of the source zvol's and the archive's pools) — into
    # the existing paced paths (device copy, hash verify, raw send/receive)
    # for exactly this zvol; the caller's prompted value is untouched.
    local _activity_rate="${transfer_rate_limit:-}"
    local transfer_rate_limit
    transfer_rate_limit=$(archive_resolve_rate "$zvol" "$archive_dataset" \
        "$_activity_rate")

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
        # Exact bytes for the progress display's -s total (parsable -p).
        volsize_bytes=$(zfs get -Hp -o value volsize "$zvol" 2>/dev/null \
            || true)
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
        if ! archive_copy_devices "$src_dev" "$dst_dev" copy_src_hash \
                "$volsize_bytes"; then
            log_msg "FATAL: Device copy failed (${src_dev} → ${dst_dev})"
            if [[ "$snapdev_changed" == "1" ]]; then
                zfs set snapdev="$snapdev_arg" "$zvol" 2>/dev/null || true
                snapdev_changed=0
            fi
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        sync "$dst_dev" 2>/dev/null || sync
        if ! archive_hash_verify "$src_dev" "$dst_dev" "$copy_src_hash" \
                "$volsize_bytes"; then
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
        if ! archive_pace_pipe; then
            archive_rollback_created "$archive_dataset" "$dataset_created" "$created_root"
            return 1
        fi
        # awk '/^size/ {print $2}'  —  Extract the stream's byte size from
        # the send dry-run for the progress display. Fails open: an empty
        # probe shows rate/bytes/elapsed without percent/ETA.
        raw_size=$(zfs send -nPcw "${zvol}${snap_name}" 2>/dev/null \
            | awk '/^size/ {print $2}' || true)
        archive_pv_args "$raw_size"
        # Four explicit pipeline variants (the transfer_do law): stage
        # order keeps the pacer before pv so the displayed rate is the
        # paced rate the destination actually receives.
        local send_rc=0
        if [[ ${#pace_pipe[@]} -gt 0 && ${#archive_pv_args[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${zvol}${snap_name}" \
                | "${pace_pipe[@]}" | pv "${archive_pv_args[@]}" \
                | zfs receive "$archive_dataset" ) || send_rc=$?
        elif [[ ${#pace_pipe[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${zvol}${snap_name}" \
                | "${pace_pipe[@]}" | zfs receive "$archive_dataset" ) || send_rc=$?
        elif [[ ${#archive_pv_args[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${zvol}${snap_name}" \
                | pv "${archive_pv_args[@]}" \
                | zfs receive "$archive_dataset" ) || send_rc=$?
        else
            ( set -o pipefail
              zfs send -cw "${zvol}${snap_name}" \
                | zfs receive "$archive_dataset" ) || send_rc=$?
        fi
        if [[ $send_rc -ne 0 ]]; then
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

# Classify an archive dataset for re-run idempotency. Prints one word:
#   absent   — the dataset does not exist
#   partial  — it exists without post-verification evidence (no @archive
#              snapshot, unknown method, or a volblocksize its method does
#              not imply) — unverified leftovers from an interrupted run
#   complete — @archive snapshot present (written only after the hash
#              verification passed, so it is a completion marker by
#              construction) and the volblocksize matches the method
# Usage: archive_completion_state <archive_dataset> <archive_mount> <zvol>
archive_completion_state() {
    local archive_dataset="$1" archive_mount="$2" zvol="$3"
    if ! zfs list -H -o name "$archive_dataset" 2>/dev/null \
            | grep -qxF -- "$archive_dataset"; then
        echo absent
        return 0
    fi
    if ! zfs list -H -t snapshot -o name "$archive_dataset" 2>/dev/null \
            | grep -qxF -- "${archive_dataset}@archive"; then
        echo partial
        return 0
    fi
    local info_file method vbs expected
    info_file="${archive_mount}/${zvol}.disk_info"
    method=$(archive_method_of "$info_file")
    if [[ "$method" != "copy" && "$method" != "raw" ]]; then
        echo partial
        return 0
    fi
    vbs=$(zfs get -H -o value volblocksize "$archive_dataset" 2>/dev/null)
    expected=""
    if [[ "$method" == "copy" ]]; then
        expected="1M"
    elif [[ -f "${archive_mount}/${zvol}.original_volblocksize" ]]; then
        expected=$(cat "${archive_mount}/${zvol}.original_volblocksize")
    fi
    if [[ -n "$expected" && "$vbs" != "$expected" ]]; then
        echo partial
        return 0
    fi
    echo complete
    return 0
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
    local created_root="" dataset_created=0 src_dev dst_dev copy_src_hash=""
    local volsize_bytes="" raw_size=""

    # One resolver call per run (rate governance): the local shadow of
    # transfer_rate_limit carries the combined rate — min(prompted rate,
    # enclosure caps of the archive's and the new zvol's pools) — into the
    # existing paced paths for exactly this zvol; the caller's prompted
    # value is untouched.
    local _activity_rate="${transfer_rate_limit:-}"
    local transfer_rate_limit
    transfer_rate_limit=$(archive_resolve_rate "$arc_dataset" "$new_zvol" \
        "$_activity_rate")

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
        # Exact bytes for the progress display's -s total (parsable -p).
        volsize_bytes=$(zfs get -Hp -o value volsize "$arc_dataset" \
            2>/dev/null || true)
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
        if ! archive_copy_devices "$src_dev" "$dst_dev" copy_src_hash \
                "$volsize_bytes"; then
            log_msg "FATAL: Device copy failed (${src_dev} → ${dst_dev})"
            [[ "$snapdev_changed" == "1" ]] \
                && zfs set snapdev="$snapdev_prev" "$arc_dataset" 2>/dev/null || true
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
        sync "$dst_dev" 2>/dev/null || sync
        if ! archive_hash_verify "$src_dev" "$dst_dev" "$copy_src_hash" \
                "$volsize_bytes"; then
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
        if ! archive_pace_pipe; then
            unarchive_rollback_created "$new_zvol" "$dataset_created" "$created_root"
            return 1
        fi
        # awk '/^size/ {print $2}'  —  Extract the stream's byte size from
        # the send dry-run for the progress display. Fails open: an empty
        # probe shows rate/bytes/elapsed without percent/ETA.
        raw_size=$(zfs send -nPcw "${arc_dataset}${snap_name}" 2>/dev/null \
            | awk '/^size/ {print $2}' || true)
        archive_pv_args "$raw_size"
        # Four explicit pipeline variants (the transfer_do law): stage
        # order keeps the pacer before pv so the displayed rate is the
        # paced rate the destination actually receives.
        local send_rc=0
        if [[ ${#pace_pipe[@]} -gt 0 && ${#archive_pv_args[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${arc_dataset}${snap_name}" \
                | "${pace_pipe[@]}" | pv "${archive_pv_args[@]}" \
                | zfs receive "$new_zvol" ) || send_rc=$?
        elif [[ ${#pace_pipe[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${arc_dataset}${snap_name}" \
                | "${pace_pipe[@]}" | zfs receive "$new_zvol" ) || send_rc=$?
        elif [[ ${#archive_pv_args[@]} -gt 0 ]]; then
            ( set -o pipefail
              zfs send -cw "${arc_dataset}${snap_name}" \
                | pv "${archive_pv_args[@]}" \
                | zfs receive "$new_zvol" ) || send_rc=$?
        else
            ( set -o pipefail
              zfs send -cw "${arc_dataset}${snap_name}" \
                | zfs receive "$new_zvol" ) || send_rc=$?
        fi
        if [[ $send_rc -ne 0 ]]; then
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

# ------------------------------------------------------------------
# Archive listing (unarchive-vm --list)
# ------------------------------------------------------------------

# Parse a zfs human size value ("10G", "1.50M", plain digits) into bytes;
# prints -1 when the value does not parse. Parameter expansion and a case
# list only, like archive_valid_rate, so no regex exceeds the 10-character
# policy limit; the decimal part is scaled by digit concatenation so the
# math stays integer.
archive_size_bytes() {
    local value="$1" num int frac unit mult scale i
    num="${value%%[!0-9.]*}"
    [[ -n "$num" ]] || { echo -1; return 0; }
    unit="${value#"$num"}"
    int="${num%%.*}"
    frac="${num#*.}"
    [[ "$num" == *.* ]] || frac=""
    [[ "$int" =~ ^[0-9]+$ ]] || { echo -1; return 0; }
    [[ -z "$frac" || "$frac" =~ ^[0-9]+$ ]] || { echo -1; return 0; }
    case "${unit,,}" in
        ""|b)          mult=1 ;;
        k|ki|kb|kib)   mult=1024 ;;
        m|mi|mb|mib)   mult=$((1024 * 1024)) ;;
        g|gi|gb|gib)   mult=$((1024 * 1024 * 1024)) ;;
        t|ti|tb|tib)   mult=$((1024 * 1024 * 1024 * 1024)) ;;
        p|pi|pb|pib)   mult=$((1024 * 1024 * 1024 * 1024 * 1024)) ;;
        e|ei|eb|eib)   mult=$((1024 * 1024 * 1024 * 1024 * 1024 * 1024)) ;;
        *) echo -1; return 0 ;;
    esac
    scale=1
    for (( i = 0; i < ${#frac}; i++ )); do
        (( scale *= 10 ))
    done
    # 10# forces base 10: zfs prints decimals with leading zeros ("1.08G",
    # "2.05T"), and plain bash arithmetic would read "08" as an invalid
    # octal literal. The empty frac keeps its bare-name zero (10# with no
    # digits is a syntax error).
    local frac_term=0
    [[ -n "$frac" ]] && frac_term=$(( 10#$frac * mult / scale ))
    # A negative result is 64-bit wraparound (values past the exabyte
    # range no real zvol reaches); report it as unparseable.
    local out=$(( 10#$int * mult + frac_term ))
    if (( out < 0 )); then
        echo -1
    else
        echo "$out"
    fi
}

# Humanize <bytes> the way zfs prints sizes: the largest of B..E that keeps
# the value at or above 1, one decimal, trailing ".0" trimmed ("360G",
# "1.5T", "512K").
archive_size_human() {
    local bytes="$1" div=1 unit_idx=0 whole tenths
    local -a labels=(B K M G T P E)
    while (( bytes / div >= 1024 && unit_idx < 6 )); do
        (( div *= 1024 ))
        (( ++unit_idx ))
    done
    whole=$(( bytes / div ))
    tenths=$(( (bytes % div) * 10 / div ))
    if (( tenths == 0 )); then
        echo "${whole}${labels[$unit_idx]}"
    else
        echo "${whole}.${tenths}${labels[$unit_idx]}"
    fi
}

# Print one VM's listing block. <disk_rows> carries the VM's original zvol
# paths (relative to the archive base), one per line. Helper of
# archive_list_vms; path_under_mount comes from node-lib.
archive_list_one_vm() {
    local vmid="$1" disk_rows="$2" archive_base="$3" archive_mount="$4"
    local pve_conf_dir="$5"
    local conf vm_name name_line tail volsize bytes total=0 size_ok=1
    local info_file markers marker marked=0 disk_count=0 no_sidecar=0
    local disk_note disk_line
    local -a restored_list=() disk_lines=()
    local -A restored_set=()

    conf="$(path_under_mount "$archive_mount" \
        "${pve_conf_dir}/${vmid}.conf")"
    vm_name="(no archived config)"
    if [[ -f "$conf" ]]; then
        vm_name="(unnamed)"
        # || true: a config without a name line is an empty answer handled
        # by the -n check below, not a failure.
        name_line=$(grep '^name: ' "$conf" 2>/dev/null | head -1 || true)
        [[ -n "$name_line" ]] && vm_name="${name_line#name: }"
    fi

    while IFS= read -r tail; do
        [[ -n "$tail" ]] || continue
        ((++disk_count))
        volsize=$(zfs get -H -o value volsize "${archive_base}/${tail}" \
            2>/dev/null || true)
        [[ -n "$volsize" && "$volsize" != "-" ]] || volsize="unknown"
        bytes=$(archive_size_bytes "$volsize")
        if [[ "$bytes" -lt 0 ]]; then
            size_ok=0
        else
            total=$(( total + bytes ))
        fi
        info_file="$(path_under_mount "$archive_mount" "${tail}.disk_info")"
        disk_note=""
        if [[ ! -f "$info_file" ]]; then
            disk_note="  [no sidecar]"
            ((++no_sidecar))
        fi
        # Fixed-string grep: markers are exact RESTORED_AS=vm-<id>-disk-<n>
        # lines the restore appends after verification. || true keeps a
        # marker-less sidecar an empty answer.
        markers=$(grep -F 'RESTORED_AS=vm-' "$info_file" 2>/dev/null || true)
        if [[ -n "$markers" ]]; then
            ((++marked))
        fi
        while IFS= read -r marker; do
            [[ -n "$marker" ]] || continue
            marker="${marker#RESTORED_AS=vm-}"
            marker="${marker%%-disk-*}"
            [[ "$marker" =~ ^[0-9]+$ ]] || continue
            if [[ -z "${restored_set[$marker]+x}" ]]; then
                restored_set[$marker]=1
                restored_list+=("$marker")
            fi
        done <<< "$markers"
        disk_lines+=("INFO:   ${tail}  ${volsize}${disk_note}")
    done <<< "$disk_rows"

    local total_str="unknown"
    [[ "$size_ok" == "1" ]] && total_str=$(archive_size_human "$total")
    local state=""
    if (( ${#restored_list[@]} > 0 )); then
        local joined="${restored_list[0]}"
        for marker in "${restored_list[@]:1}"; do
            joined+=", ${marker}"
        done
        if [[ "$marked" == "$disk_count" ]]; then
            state=" — restored as: ${joined}"
        else
            state=" — partially restored as: ${joined}"
        fi
    fi
    if (( disk_count > 0 && no_sidecar == disk_count )); then
        state+=" — pre-sidecar archive (manual restore)"
    fi
    local disk_word="disks"
    (( disk_count == 1 )) && disk_word="disk"
    log_msg "INFO: VM ${vmid} — ${vm_name} — ${disk_count} ${disk_word}," \
        "${total_str} total${state}"
    for disk_line in "${disk_lines[@]}"; do
        log_msg "$disk_line"
    done
}

# List every archived VM under <archive_base> (mounted at <archive_mount>):
# groups the archived zvols by vmid and prints each VM's name (from the
# archived Proxmox config), its disks with volsize, the summed size, and
# the restore state recorded in the .disk_info sidecars. Read-only. Runs
# wherever the archive datasets live — inline on a single node, inside the
# two-node storage payload — so both node modes run literally the same
# listing code, like the transfer paths. path_under_mount comes from
# node-lib.
# Usage: archive_list_vms <archive_base> <archive_mount> <pve_conf_dir>
archive_list_vms() {
    local archive_base="$1" archive_mount="$2" pve_conf_dir="$3"
    local all_zvols row tail vm_part vmid disknum vm_count=0
    local -a vmids=()
    local -A vm_known=() vm_disk_rows=()

    # Same rooted enumeration as the restore discovery; the || true keeps an
    # empty archive an empty answer under pipefail.
    all_zvols=$(zfs list -H -t volume -o name -r "$archive_base" 2>/dev/null \
        | grep -F "${archive_base}/" \
        | sort \
        || true)

    while IFS= read -r row; do
        [[ -n "$row" ]] || continue
        tail="${row#"${archive_base}"/}"
        # Only VM-disk zvols count: <pool>/proxmox/vm-<vmid>-disk-<n> with
        # a numeric vmid and disk number; anything else under the base is
        # skipped silently.
        [[ "$tail" == *"/proxmox/vm-"*"-disk-"* ]] || continue
        vm_part="${tail##*/proxmox/vm-}"
        vmid="${vm_part%-disk-*}"
        disknum="${vm_part#*-disk-}"
        [[ "$vmid" =~ ^[0-9]+$ && "$disknum" =~ ^[0-9]+$ ]] || continue
        if [[ -z "${vm_known[$vmid]+x}" ]]; then
            vm_known[$vmid]=1
            vmids+=("$vmid")
        fi
        vm_disk_rows[$vmid]+="${tail}"$'\n'
    done <<< "$all_zvols"

    log_msg "INFO: === Archived VMs under ${archive_base} ==="
    if (( ${#vmids[@]} > 0 )); then
        mapfile -t vmids < <(printf '%s\n' "${vmids[@]}" | sort -n)
    fi
    for vmid in "${vmids[@]}"; do
        ((++vm_count))
        archive_list_one_vm "$vmid" "${vm_disk_rows[$vmid]}" \
            "$archive_base" "$archive_mount" "$pve_conf_dir"
    done
    if (( vm_count == 0 )); then
        log_msg "INFO: No archived VMs under ${archive_base}."
    fi
}
