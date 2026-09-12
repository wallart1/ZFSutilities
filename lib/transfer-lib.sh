#!/usr/bin/bash
# transfer-lib.sh
# Shared ZFS send/receive transfer helpers used by zfs-send-receive and
# zfs-migrate-send.
#
# This library is sourced at the file level by both scripts so that:
#   - zfs-send-receive can do resumable, rate-limited, pv-instrumented
#     replication for backup/restore.
#   - zfs-migrate-send can do the same for one-shot Migrate Pool copy steps.
#
# The library loads its own dependency (bashinit).

source ~/bashinit
bashinit

# Abort (discard) a receive resume token on a destination dataset.
# Dry-run aware: honors the caller's $dryrun ('N' = really abort).
# Usage: transfer_abort_resume_token <dest>
# Returns: 0 always (the abort itself is best-effort, as in zfs-send-receive).
function transfer_abort_resume_token {
    local dest="$1"
    if [[ ${dryrun:-N} != 'N' ]]; then
        log_msg "INFO: Dry-run: Would abort resume token on $dest"
    else
        zfs receive -A "$dest"
    fi
}

# Classify the error text of a failed `zfs send -nP -t <token>` dry-run.
# Usage: transfer_resume_token_stale <errtext>
# Returns: 0 when the token is known-stale/invalid, 1 otherwise.
function transfer_resume_token_stale {
    local errtext="$1"
    [[ "$errtext" == *"no longer exists"* \
        || "$errtext" == *"@--head--"* \
        || "$errtext" == *"Invalid argument"* \
        || "$errtext" == *"does not match"* \
        || "$errtext" == *"destination has been modified"* ]]
}

# Validate a receive resume token and report the remaining byte count.
# Usage: transfer_validate_resume_token <token>
# Output: on success, the remaining byte count (awk '/^size/ {print $2}');
#         on failure, the captured error text.
# Returns: 0 on success, 1 on failure (caller decides stale vs. unexpected
#          using transfer_resume_token_stale).
function transfer_validate_resume_token {
    local token="$1"
    local resumedata
    if ! resumedata=$(zfs send -nP -t "$token" 2>&1); then
        printf '%s\n' "$resumedata"
        return 1
    fi
    # awk '/^size/ {print $2}' — Extract remaining byte count from resume
    # token info.
    echo "$resumedata" | awk '/^size/ {print $2}'
}

# Build the pv argument array for a transfer into the global
# transfer_pv_args array.
# Usage: transfer_pv_args <datatosend> <use_pv>
#   use_pv='Y' + tty on stderr          -> -pterb -s <size>
#   use_pv='Y' + ZFSUTILITIES_LOG_INHERIT=Y -> -fpterb -s <size>
#   $pv_rate_limit set + progress wanted -> append -L <rate>
#   $pv_rate_limit set + no progress     -> -q -L <rate>
#   otherwise                            -> empty array (no pv in the pipeline)
function transfer_pv_args {
    local datatosend="$1" use_pv="$2"
    transfer_pv_args=()
    local progress_desired="N"
    # Progress display: natural in terminal, forced in GUI, suppressed otherwise
    if [[ "$use_pv" = 'Y' ]]; then
        if [[ -t 2 ]]; then
            # Terminal available — natural progress display
            transfer_pv_args=(-pterb -s "$datatosend")
            progress_desired="Y"
        elif [[ "${ZFSUTILITIES_LOG_INHERIT:-}" = "Y" ]]; then
            # Parent runner is capturing output — force output for parser
            transfer_pv_args=(-fpterb -s "$datatosend")
            progress_desired="Y"
        fi
    fi
    # Rate limit: visible in terminal/GUI, quiet in headless/non-interactive
    local rate_limit="${pv_rate_limit:-}"
    if [[ -n "$rate_limit" ]]; then
        if [[ "$progress_desired" = "Y" ]]; then
            transfer_pv_args+=("-L" "$rate_limit")
        else
            transfer_pv_args=(-q -L "$rate_limit")
        fi
    fi
}

# Run one zfs send | pv | zfs receive pipeline under pipefail.
# Usage: transfer_do <desc> <sendopts> <recvopts> <use_pv> <datatosend> \
#                    <send_target> <recv_target>
#   sendopts/recvopts are space-separated option strings; send_target is
#   omitted from the send command when sendopts contains -t <token> (the
#   token already encodes the snapshot).
# Logs "FATAL: <desc> failed. RC=N" on failure; caller-specific failure
# handling (lock release, exit codes, re-run hints) stays in the callers.
# Returns: the pipeline's exit status (nonzero on any pipeline failure).
function transfer_do {
    local desc="$1" sendopts="$2" recvopts="$3" use_pv="$4" datatosend="$5"
    local send_target="$6" recv_target="$7"

    transfer_pv_args "$datatosend" "$use_pv"

    # Build option arrays without using read, so callers that override read
    # (for example, test mocks that auto-answer prompts) cannot corrupt the
    # option parsing. Briefly disable globbing and then restore the prior
    # shell option state.
    local _save_glob
    _save_glob=$(shopt -p nullglob extglob failglob)
    local _noglob_was_set=0
    [[ "$-" == *f* ]] && _noglob_was_set=1
    set -f
    # shellcheck disable=SC2206
    # Intentional word splitting: $sendopts is a space-separated option string.
    local -a _sendopts=($sendopts)
    local -a send_cmd=(zfs send "${_sendopts[@]}")
    [[ "$sendopts" != *"-t"* ]] && send_cmd+=("$send_target")

    # shellcheck disable=SC2206
    # Intentional word splitting: $recvopts is a space-separated option string.
    local -a _recvopts=($recvopts)
    local -a recv_cmd=(zfs receive "${_recvopts[@]}" "$recv_target")
    if [[ $_noglob_was_set -eq 0 ]]; then
        set +f
    fi
    eval "$_save_glob"

    # Enable pipefail just for the pipeline so a failing zfs send or pv is
    # detected even when zfs receive exits 0; restore the prior state after.
    local _save_pipefail
    _save_pipefail=$(set -o | awk '$1 == "pipefail" {print $2}')
    set -o pipefail
    # Capture the status with `|| _rc=$?` (not a bare pipeline followed by
    # `$?`) so a failing pipeline is also handled safely if a future caller
    # invokes transfer_do outside a condition context under `set -e`.
    local _rc=0
    if [[ ${#transfer_pv_args[@]} -gt 0 ]]; then
        "${send_cmd[@]}" | pv "${transfer_pv_args[@]}" | "${recv_cmd[@]}" || _rc=$?
    else
        "${send_cmd[@]}" | "${recv_cmd[@]}" || _rc=$?
    fi
    [[ "$_save_pipefail" != "on" ]] && set +o pipefail
    if [[ $_rc -ne 0 ]]; then
        log_msg "FATAL: $desc failed. RC=$_rc"
        return "$_rc"
    fi
    return 0
}

# Check that a destination pool has room for a transfer (10% margin, minimum
# 1 GiB buffer unless $space_check_min_buffer overrides it).
# Usage: transfer_check_space <datatosend> <dest_pool>
# Returns: 0 when space is sufficient or cannot be determined; 1 when the
#          space check fails (after logging the same WARN text as
#          zfs-send-receive's check_space_available).
function transfer_check_space {
    local datatosend="$1" dest_pool="$2"
    [[ $datatosend -le 0 ]] && return 0
    local dest_avail
    dest_avail=$(zfs get -Hp -o value available "$dest_pool" 2>/dev/null)
    # Regex: ^[0-9]+$
    # Purpose: Validate that dest_avail is a non-negative integer.
    # Examples: "12345678" -> match; "-1" -> no match; "" -> no match.
    [[ -z "$dest_avail" || ! "$dest_avail" =~ ^[0-9]+$ ]] && return 0
    local safety_margin=$(( datatosend / 10 ))
    # The minimum buffer is configurable (e.g., for integration tests on
    # small pools) but defaults to 1 GiB in production.
    local min_buffer="${space_check_min_buffer:-$(( 1024 * 1024 * 1024 ))}"
    [[ $safety_margin -lt $min_buffer ]] && safety_margin=$min_buffer
    local space_needed=$(( datatosend + safety_margin ))
    [[ $dest_avail -ge $space_needed ]] && return 0
    log_msg "WARN: Insufficient space on destination pool '$dest_pool'." \
        "\n\tData to send: $(echo "$datatosend" | numfmt --to=iec-i)" \
        "\n\tSpace needed (with 10% margin): $(echo $space_needed | numfmt --to=iec-i)" \
        "\n\tSpace available: $(echo "$dest_avail" | numfmt --to=iec-i)"
    return 1
}
