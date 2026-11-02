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
# The replay half restores captured settings: propmanifest_replay finds a
# backup copy's manifest (exact generation first, newest available as the
# fallback), verifies the header and body checksum, and re-applies the
# properties with `zfs set` — keylocation additionally triggers a
# best-effort non-interactive `zfs load-key`. Used by bin/zfsreplayprops,
# which zfsrestore, the GUI restore payload, and zfsrestoresendstream
# (.props siblings) share.
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

# ---------------------------------------------------------------------------
# Replay (restore fidelity)
# ---------------------------------------------------------------------------

# Derive the manifest store and dataset lookup key for a backup copy at
# <fs>. The mirrored-chain shape every fleet chain uses puts the original
# source pool in the second component: <backup root>/<source pool>/...,
# so the store is the first two components plus zfsutilities-manifests
# and the key is the name minus its first component — exactly what
# propmanifest_dataset/escape wrote at capture time. Pure string work.
# Usage: propmanifest_store_of <backup-copy-fs>
# Output: <manifest-ds> <lookup-key> (space-separated; dataset names
#         never contain spaces)
# Returns: 1 when the name has fewer than two components.
function propmanifest_store_of {
    local fs="$1" first rest
    first="${fs%%/*}"
    rest="${fs#*/}"
    if [[ "$rest" = "$fs" ]]; then
        return 1
    fi
    printf '%s/%s/zfsutilities-manifests %s\n' \
        "$first" "${rest%%/*}" "$rest"
}

# Newest manifest file for one dataset: the last file (byte order — the
# UTC-canonical generation names sort chronologically) whose name starts
# with <prefix>. Pure string/file work, no zfs calls.
# Usage: propmanifest_newest_file <prefix-including-trailing-@>
# Output: the newest matching file name (empty when none).
function propmanifest_newest_file {
    local LC_ALL=C
    local prefix="$1" best="" f
    for f in "$prefix"*; do
        [[ -f "$f" ]] && best="$f"
    done
    printf '%s\n' "$best"
}

# Parse and verify one manifest file. Pure: no logging, no state, no zfs
# calls — safe inside a command substitution. The expected dataset may be
# empty to skip the dataset check (callers that were handed the file
# directly trust its dataset field).
# Usage: body=$(propmanifest_parse <file> <expected-dataset-or-empty>)
# Output: the verified property=value body (rc 0 only).
# Returns: 0 ok; 1 unreadable; 2 unknown format version; 3 dataset
#          mismatch; 4 sha256 mismatch.
function propmanifest_parse {
    local file="$1" expect="$2"
    local line seen_blank=0 version_ok=0 ds_field="" sum_field="" body=""
    [[ -r "$file" ]] || return 1
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ $seen_blank -eq 0 ]]; then
            case "$line" in
                '# zfsutilities property manifest v1') version_ok=1 ;;
                '# dataset: '*) ds_field="${line#\# dataset: }" ;;
                '# snapshot: '*) : ;;
                '# sha256: '*) sum_field="${line#\# sha256: }" ;;
                '') seen_blank=1 ;;
            esac
        else
            # Capture writes the body without a trailing newline (its
            # sort ran through a command substitution), so the verified
            # reconstruction joins lines with separators only.
            if [[ -n "$line" ]]; then
                [[ -n "$body" ]] && body+=$'\n'
                body+="$line"
            fi
        fi
    done < "$file"
    [[ $version_ok -eq 1 ]] || return 2
    [[ -z "$expect" || "$ds_field" = "$expect" ]] || return 3
    local sum
    sum=$(printf '%s' "$body" | sha256sum | awk '{print $1}')
    [[ "$sum" = "$sum_field" ]] || return 4
    printf '%s' "$body"
}

# Apply a verified manifest body to <dest> with `zfs set`, one property at
# time: a property this host cannot set (or that the exclusion set kept
# out of manifests by design) is skipped with a WARN, never fatal.
# keylocation is special: after setting it, a file:// location triggers a
# best-effort non-interactive `zfs load-key` (a missing/unreadable key
# file WARNs — the dataset simply stays locked); any other location is
# set but never loaded (loading it would need an interactive prompt).
# Usage: propmanifest_apply_body <body> <dest>
function propmanifest_apply_body {
    local body="$1" dest="$2"
    local applied=0 skipped=0 line prop val
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        prop="${line%%=*}"
        val="${line#*=}"
        if propmanifest_excluded "$prop"; then
            log_msg "WARN: Property $prop is excluded from replay —" \
                "skipped on $dest."
            skipped=$((skipped + 1))
            continue
        fi
        if ! zfs set "$prop=$val" "$dest" 2>/dev/null; then
            log_msg "WARN: Could not set $prop on $dest — skipped" \
                "(not settable on this host)."
            skipped=$((skipped + 1))
            continue
        fi
        applied=$((applied + 1))
        if [[ "$prop" = "keylocation" ]]; then
            if [[ "$val" = file://* ]]; then
                if zfs load-key "$dest" 2>/dev/null; then
                    log_msg "VERB: Loaded the key for $dest from its keylocation."
                else
                    log_msg "WARN: Could not load the key for $dest" \
                        "(keylocation file missing or unreadable) — the" \
                        "dataset stays locked until its key is loaded."
                fi
            else
                log_msg "WARN: keylocation on $dest set to $val; key not" \
                    "loaded (only file:// locations load non-interactively)."
            fi
        fi
    done <<< "$body"
    log_msg "VERB: Replayed $applied properties onto $dest from its" \
        "property manifest ($skipped skipped)."
    return 0
}

# Replay one manifest file handed over directly (the .props sibling of a
# .zfssendstream file) onto <dest>: verify (no dataset expectation — the
# caller chose the file), then apply. Runs under a write lock on the
# destination. WARN-only, never fatal.
# Usage: propmanifest_apply_file <file> <dest>
function propmanifest_apply_file {
    local file="$1" dest="$2"
    local lock_rc=0 lock_id body rc=0

    if [[ ${dryrun:-N} != 'N' ]]; then
        log_msg "INFO: Dry-run: Would replay property manifest $file onto $dest"
        return 0
    fi
    if ! declare -f zfslock_wait_or_resolve >/dev/null 2>&1 \
            || ! declare -f zfslock_release >/dev/null 2>&1; then
        log_msg "WARN: Property manifest $file not replayed (lock manager not loaded)."
        return 0
    fi
    zfslock_wait_or_resolve "$dest" "w" \
        "property manifest replay: $file -> $dest" || lock_rc=$?
    if [[ $lock_rc -ne 0 ]]; then
        log_msg "WARN: Property manifest $file not replayed (lock conflict on $dest)."
        return 0
    fi
    lock_id="$zfslock_id"

    body=$(propmanifest_parse "$file" "") || rc=$?
    if [[ $rc -ne 0 ]]; then
        propmanifest_parse_warn "$rc" "$file" "" "$dest"
        zfslock_release "$lock_id"
        return 0
    fi
    propmanifest_apply_body "$body" "$dest"
    zfslock_release "$lock_id"
    return 0
}

# Map a propmanifest_parse rc to its WARN line. Internal helper.
# Usage: propmanifest_parse_warn <rc> <file> <expected-ds> <dest>
function propmanifest_parse_warn {
    case "$1" in
        1) log_msg "WARN: Property manifest $2 could not be read —" \
            "replay skipped for $4." ;;
        2) log_msg "WARN: Property manifest $2 has an unknown format" \
            "version — replay skipped for $4." ;;
        3) log_msg "WARN: Property manifest $2 records a different" \
            "dataset than $3 — replay skipped for $4." ;;
        4) log_msg "WARN: Property manifest $2 failed its sha256 check —" \
            "replay skipped for $4." ;;
    esac
    return 0
}

# Mount <mds> for replay, unmounting a different store this library
# mounted earlier (a restore spanning several source pools touches one
# store per pool; only one stays mounted at a time). Internal helper.
# Usage: propmanifest_switch_mount <manifest-ds>
# Sets: $_propmanifest_mnt via propmanifest_mount (empty on failure).
function propmanifest_switch_mount {
    local mds="$1"
    if [[ -n "$_propmanifest_mounted" && "$_propmanifest_mounted" != "$mds" ]]; then
        zfs unmount "$_propmanifest_mounted" 2>/dev/null || true
        _propmanifest_mounted=""
    fi
    propmanifest_mount "$mds"
}

# Replay one dataset's captured local properties onto <dest> after it was
# restored from the backup copy <fs>. Lookup: the exact generation first
# (the backup copy's newest snapshot — the generation just restored),
# then the newest available manifest for that dataset with a WARN, then
# nothing but a WARN (pre-feature generations keep inherited defaults).
# Entire contract is fail-open: every failure WARNs and returns 0 — the
# restore result is never affected.
# Usage: propmanifest_replay <backup-copy-fs> <dest-fs>
function propmanifest_replay {
    local fs="$1" dest="$2"
    local mds key store lock_rc=0 lock_id mnt snaps snap exact file body rc=0

    if [[ ${dryrun:-N} != 'N' ]]; then
        store=$(propmanifest_store_of "$fs" 2>/dev/null || true)
        log_msg "INFO: Dry-run: Would replay property manifest for $dest" \
            "from ${store%% *}"
        return 0
    fi

    store=$(propmanifest_store_of "$fs") || store=""
    if [[ -z "$store" ]]; then
        log_msg "WARN: Cannot derive a property-manifest store from $fs —" \
            "replay skipped for $dest."
        return 0
    fi
    mds="${store%% *}"
    key="${store#* }"

    # Write lock on the destination — the replay's `zfs set` batch is a
    # mutation like any other. Any lock failure WARNs and skips replay
    # for this dataset only.
    if ! declare -f zfslock_wait_or_resolve >/dev/null 2>&1 \
            || ! declare -f zfslock_release >/dev/null 2>&1; then
        log_msg "WARN: Property replay for $dest skipped (lock manager not loaded)."
        return 0
    fi
    zfslock_wait_or_resolve "$dest" "w" \
        "property manifest replay: $fs -> $dest" || lock_rc=$?
    if [[ $lock_rc -ne 0 ]]; then
        log_msg "WARN: Property replay for $dest skipped (lock conflict on $dest)."
        return 0
    fi
    lock_id="$zfslock_id"

    if ! zfs list -H -o name "$mds" >/dev/null 2>&1; then
        log_msg "WARN: No property-manifest store $mds — $dest keeps its" \
            "inherited defaults (backup predates property manifests)."
        zfslock_release "$lock_id"
        return 0
    fi

    propmanifest_switch_mount "$mds"
    mnt="$_propmanifest_mnt"
    if [[ -z "$mnt" ]]; then
        zfslock_release "$lock_id"
        return 0
    fi

    # Exact generation = the newest snapshot on the backup copy (name
    # sort: UTC-canonical names sort chronologically).
    snaps=$(zfs list -t snapshot -H -o name -S name "$fs" 2>/dev/null) || snaps=""
    snap="${snaps%%$'\n'*}"
    snap="${snap#*@}"
    if [[ -z "$snap" ]]; then
        log_msg "WARN: No snapshots on $fs — property replay skipped for $dest."
        zfslock_release "$lock_id"
        return 0
    fi

    exact="$mnt/$(propmanifest_escape "$key")@$snap"
    file="$exact"
    if [[ ! -f "$exact" ]]; then
        file=$(propmanifest_newest_file "$mnt/$(propmanifest_escape "$key")@")
        if [[ -z "$file" ]]; then
            log_msg "WARN: No property manifest for $key in $mds — $dest" \
                "keeps its inherited defaults."
            zfslock_release "$lock_id"
            return 0
        fi
        log_msg "WARN: Exact-generation manifest @$snap not found for" \
            "$key — using the newest available (${file##*/})."
    fi

    body=$(propmanifest_parse "$file" "$key") || rc=$?
    if [[ $rc -ne 0 ]]; then
        propmanifest_parse_warn "$rc" "$file" "$key" "$dest"
        zfslock_release "$lock_id"
        return 0
    fi

    propmanifest_apply_body "$body" "$dest"
    zfslock_release "$lock_id"
    return 0
}
