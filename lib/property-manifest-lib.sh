#!/usr/bin/bash
# property-manifest-lib.sh
# Property-manifest capture for backup fidelity: after a dataset's backup
# transfer verifies, record its locally-set properties next to the backup
# copy so a restore can replay them later. The transfer streams stay
# property-less (-cw) by design — the manifest is the only property
# carrier.
#
# Store shape: <destfs>/<source-pool>/zfsutilities-manifests — one small
# dedicated filesystem per backup root, created once (zfs create -p,
# canmount=on), inheriting the backup root's efficiency settings. It must
# stay unencrypted; a refusal to create it (e.g. under an encrypted
# parent) WARNs once and skips manifests for the rest of the run — fail
# open, the data still flows.
#
# One file per dataset per generation, named <dataset with / → %2F>@<snap>:
# a header (format version, dataset, snapshot, body sha256) followed by
# the sorted property=value lines of `zfs get -s local all` minus the
# exclusion set (properties the raw stream already carries or that cannot
# be set post-create; keylocation is deliberately kept). Files are written
# tmp+rename while the manifest dataset is temporarily mounted — mounted
# at first capture, unmounted at propmanifest_finish and on EXIT, each
# only when this library did the mounting.
#
# The manifest dataset itself is snapshotted once per generation under
# the same generation snapname as the data, so the existing cleanup /
# zfsoffsiteretain retention prunes it in lockstep — no new pruning code.
#
# Contract: every failure is a WARN and rc 0. A manifest problem never
# fails a backup. Writes and the generation snapshot run under a write
# lock on the manifest dataset (zfslockmanager, like every mutation).

if [[ $(type -t log_msg 2>/dev/null) != "function" ]]; then
    source ~/bashinit
    bashinit
fi

# Run latches (plain assignments on purpose: this file is sourced at
# function scope, and plain assignments land in globals — a declare here
# would create source_helper-local variables that vanish on return).
_propmanifest_ok=""      # manifest dataset verified/created this process
_propmanifest_skip=""    # manifest dataset that failed — skipped since
_propmanifest_mounted="" # manifest dataset this library mounted
_propmanifest_mnt=""     # mountpoint of the current manifest dataset

# Derive the manifest dataset that stores <fs>'s manifests when it is
# backed up under <destfs>. Pure string work — no zfs calls, safe in
# dry-run.
# Usage: propmanifest_dataset <destfs> <fs>
# Output: <destfs>/<first component of fs>/zfsutilities-manifests
function propmanifest_dataset {
    printf '%s/%s/zfsutilities-manifests\n' "$1" "${2%%/*}"
}

# True when a property name is excluded from manifests: the raw stream
# already carries it (encryption family, volblocksize), it is run state
# (keystatus), or it cannot be set post-create (encryptionroot).
# keylocation is deliberately NOT excluded — replay sets it and then
# best-effort loads the key.
# Usage: propmanifest_excluded <property-name>
# Returns: 0 excluded, 1 kept.
function propmanifest_excluded {
    case "$1" in
        encryption|keyformat|pbkdf2iters|keystatus|encryptionroot|volblocksize)
            return 0
            ;;
    esac
    return 1
}

# Escape a dataset name for use as a manifest file name ('/' → '%2F').
# Usage: propmanifest_escape <dataset>
# Output: the escaped name.
function propmanifest_escape {
    local name="$1"
    name="${name//\//%2F}"
    printf '%s\n' "$name"
}

# Ensure the manifest dataset exists. Idempotent per process and latched
# per manifest dataset: one refusal (e.g. an encrypted parent rejects the
# unencrypted child) WARNs once and every later capture on that store is
# a no-op. Fail open by contract — returns 0 either way.
# Usage: propmanifest_ensure_dataset <manifest-ds>
function propmanifest_ensure_dataset {
    local mds="$1"
    [[ "$_propmanifest_skip" = "$mds" ]] && return 0
    [[ "$_propmanifest_ok" = "$mds" ]] && return 0
    if zfs list -H -o name "$mds" >/dev/null 2>&1; then
        _propmanifest_ok="$mds"
        return 0
    fi
    local err
    if err=$(zfs create -p "$mds" 2>&1); then
        log_msg "VERB: Created property-manifest dataset $mds"
        _propmanifest_ok="$mds"
    else
        log_msg "WARN: Could not create property-manifest dataset $mds —" \
            "skipping property manifests for this run ($err)"
        _propmanifest_skip="$mds"
    fi
    return 0
}

# Collect a dataset's manifest body: the sorted property=value lines of
# its locally-set properties, exclusion set removed. User properties ride
# free (`zfs get -s local all` includes them). Empty output is valid —
# nothing is set locally; the header-only manifest still says so.
# Usage: propmanifest_props <fs>
# Output: sorted property=value lines (possibly empty).
# Returns: 1 when the zfs get itself fails (dataset gone mid-run).
function propmanifest_props {
    local fs="$1" raw line prop rest body=""
    if ! raw=$(zfs get -Hpo property,value,source -s local all "$fs" 2>/dev/null); then
        return 1
    fi
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        prop="${line%%$'\t'*}"
        propmanifest_excluded "$prop" && continue
        rest="${line#*$'\t'}"
        body+="$prop=${rest%%$'\t'*}"$'\n'
    done <<< "$raw"
    printf '%s' "$body" | LC_ALL=C sort
}

# Ensure the manifest dataset is mounted and usable; the mountpoint
# directory lands in $_propmanifest_mnt (empty on failure). Must be
# called directly, never inside a command substitution — the failure
# latches and the EXIT trap it arms belong to the caller's shell, and a
# subshell would discard them. Failure (legacy/none mountpoint, mount
# refusal) latches a run-level skip. Mounts at most one manifest dataset
# per process; the unmount is guaranteed by propmanifest_finish (normal
# end) and an EXIT trap armed here (abnormal end), both only when this
# function mounted it.
# Usage: propmanifest_mount <manifest-ds>
# Sets: $_propmanifest_mnt (mountpoint directory, empty on failure).
function propmanifest_mount {
    local mds="$1" mp mounted
    _propmanifest_mnt=""
    mp=$(zfs get -H -o value mountpoint "$mds" 2>/dev/null) || mp=""
    if [[ -z "$mp" || "$mp" == "legacy" || "$mp" == "none" || "$mp" == "-" ]]; then
        log_msg "WARN: Property-manifest dataset $mds has no usable mountpoint" \
            "('${mp:-none}') — skipping property manifests for this run."
        _propmanifest_skip="$mds"
        return 0
    fi
    mounted=$(zfs get -H -o value mounted "$mds" 2>/dev/null) || mounted=""
    if [[ "$mounted" != "yes" ]]; then
        if ! zfs mount "$mds" 2>/dev/null; then
            log_msg "WARN: Could not mount $mds — skipping property" \
                "manifests for this run."
            _propmanifest_skip="$mds"
            return 0
        fi
        if [[ -z "$_propmanifest_mounted" ]]; then
            _propmanifest_mounted="$mds"
            if declare -f append_exit_trap >/dev/null 2>&1; then
                append_exit_trap "zfs unmount '$mds' 2>/dev/null || true"
            fi
        fi
    fi
    _propmanifest_mnt="$mp"
}

# Snapshot the manifest dataset under the same generation snapname as the
# data, so cleanup/zfsoffsiteretain retention prunes it in lockstep.
# Idempotent per generation: the first capture of a run creates it, the
# rest observe it exists. WARN-only on refusal.
# Usage: propmanifest_snapshot <manifest-ds> <snapname-with-@>
function propmanifest_snapshot {
    local mds="$1" snap="$2"
    if zfs list -t snapshot "$mds$snap" >/dev/null 2>&1; then
        return 0
    fi
    if ! zfs snapshot "$mds$snap" 2>/dev/null; then
        log_msg "WARN: Could not snapshot property-manifest dataset" \
            "$mds$snap — retention lockstep may lag this generation."
        return 0
    fi
    log_msg "VERB: Snapshot $mds$snap holds this generation's property manifests."
}

# Capture one dataset's local properties into the manifest store under
# <destfs>, then snapshot the store in lockstep. Dry-run aware (honors
# the caller's $dryrun). Entire contract is fail-open: every failure
# WARNs and returns 0 — the backup result is never affected.
# Usage: propmanifest_capture <fs> <destfs> <snapname-with-@>
function propmanifest_capture {
    local fs="$1" destfs="$2" snap="$3"
    local mds mnt body sum fname dir tmpf count lock_rc lock_id
    mds=$(propmanifest_dataset "$destfs" "$fs")

    if [[ ${dryrun:-N} != 'N' ]]; then
        log_msg "INFO: Dry-run: Would capture property manifest for $fs under $mds"
        return 0
    fi

    # The lock manager is caller-provided (zfs-send-receive sources it);
    # without it there is no safe way to write — WARN and skip, fail open.
    if ! declare -f zfslock_wait_or_resolve >/dev/null 2>&1 \
            || ! declare -f zfslock_release >/dev/null 2>&1; then
        log_msg "WARN: Property manifest for $fs not written (lock manager not loaded)."
        return 0
    fi

    # Write lock on the manifest dataset — same manager and discipline as
    # every other mutation. Any lock failure WARNs and skips only this
    # dataset's manifest.
    lock_rc=0
    zfslock_wait_or_resolve "$mds" "w" \
        "property manifest capture: $fs -> $mds" || lock_rc=$?
    if [[ $lock_rc -ne 0 ]]; then
        log_msg "WARN: Property manifest for $fs not written (lock conflict on $mds)."
        return 0
    fi
    lock_id="$zfslock_id"

    propmanifest_ensure_dataset "$mds"
    if [[ "$_propmanifest_skip" = "$mds" ]]; then
        zfslock_release "$lock_id"
        return 0
    fi

    propmanifest_mount "$mds"
    mnt="$_propmanifest_mnt"
    if [[ -z "$mnt" ]]; then
        zfslock_release "$lock_id"
        return 0
    fi

    if ! body=$(propmanifest_props "$fs"); then
        log_msg "WARN: Property manifest for $fs not written (zfs get failed)."
        zfslock_release "$lock_id"
        return 0
    fi

    dir="$mnt"
    fname="$(propmanifest_escape "$fs")@${snap#@}"
    sum=$(printf '%s' "$body" | sha256sum | awk '{print $1}')
    tmpf="$dir/.tmp.${fname}.$$"
    # Probe the temp file openable first — with the redirections in this
    # order the probe's own failure message is silenced; the body write
    # then runs against a known-openable file.
    if ! : 2>/dev/null > "$tmpf"; then
        log_msg "WARN: Property manifest for $fs not written (write to $mds failed)."
        zfslock_release "$lock_id"
        return 0
    fi
    if ! {
            printf '# zfsutilities property manifest v1\n'
            printf '# dataset: %s\n' "$fs"
            printf '# snapshot: %s\n' "$snap"
            printf '# sha256: %s\n' "$sum"
            printf '\n'
            printf '%s' "$body"
        } > "$tmpf" 2>/dev/null || ! mv -f "$tmpf" "$dir/$fname" 2>/dev/null; then
        rm -f "$tmpf" 2>/dev/null || true
        log_msg "WARN: Property manifest for $fs not written (write to $mds failed)."
        zfslock_release "$lock_id"
        return 0
    fi

    count=$(printf '%s' "$body" | grep -c '=' || true)
    log_msg "VERB: Wrote property manifest for $fs to $mds ($count properties)."

    propmanifest_snapshot "$mds" "$snap"
    zfslock_release "$lock_id"
    return 0
}

# End-of-run cleanup: unmount the manifest dataset when this library
# mounted it. The EXIT trap armed at mount time covers abnormal ends;
# this covers the normal one so the store does not stay mounted through
# the caller's later phases.
# Usage: propmanifest_finish
function propmanifest_finish {
    if [[ -n "$_propmanifest_mounted" ]]; then
        zfs unmount "$_propmanifest_mounted" 2>/dev/null || true
        _propmanifest_mounted=""
    fi
    return 0
}
