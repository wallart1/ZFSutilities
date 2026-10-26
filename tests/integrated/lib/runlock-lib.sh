#!/usr/bin/env bash
# runlock-lib.sh — the one-run-at-a-time fence for itf entry points.
#
# Every run binds the site-configured HTTP port on the dev host (preseeds,
# dev tarballs), arms the shared UDP-514 installer-syslog listener on a
# base host, and drives guests whose RAM footprint fits one two-node lab
# per base. The parallel repo lanes share one dev host and one physical
# site, so two runs started together — from this tree or a sibling lane's
# — collide mid-run: the loser fails at itf_http_serve ("port busy"),
# loses syslog datagrams, or stacks 8 GB guests past base RAM. Neither
# humans nor agents can be relied on to check for an active run first,
# so the driver itself serializes: `itf journey run` and
# `itf template build` acquire this lock before doing anything.
#
# Mechanism: an advisory kernel lock (flock) held on fd 9 of a
# machine-global file. The lock lives exactly as long as the run's own
# process — any death (kill, crash, session loss) releases it instantly,
# so it can never go stale and needs no cleanup verb. This is
# deliberately NOT the product's dataset lock manager (zfslockctl /
# python zfs_lock_manager): those key locks by ZFS dataset for root-run
# product operations, while this fence keys by dev host and must work
# for the unprivileged orchestrator with no product environment.
#
# The holder records itself in the lock file (description, pid, start
# time, repo root), so a waiting run and `itf status` can name WHO is
# holding the fence — across lanes, since the file is machine-global.
#
# The flock fences dev-side processes only.  When the dev host restarts
# mid-run the kernel releases the lock instantly and correctly — but the
# run's guests live on the base hosts and do NOT die with dev, so the
# next acquire would otherwise start a second lab stacked on the orphans
# (base RAM, reserved VMIDs) with nothing but advisory notices in the
# way.  itf_runlock_orphan_fence closes that structurally at acquire
# time: guests recorded by INTERRUPTED runs of this tree that still
# exist on their base (the base's own `qm list` is the authority, so it
# is correct across dev restarts) refuse the new start until they are
# reused (`journey run <same> --rerun`) or discarded (`guest destroy`).
#
# Knobs (environment):
#   ITF_RUN_LOCK          lock file (default /tmp/itf-active-run.lock;
#                         tests MUST point this at a private path)
#   ITF_RUNLOCK_WAIT      seconds to wait for the active run to finish
#                         before giving up (default 7200 — longer than
#                         any journey; 0 refuses immediately)
#   ITF_RUNLOCK_HEARTBEAT seconds between heartbeat lines while waiting
#                         (default 30; clamped to the wait budget)

# Best-effort read of the recorded holder line (empty when unknown).
itf_runlock_holder() {
    local lock="${ITF_RUN_LOCK:-/tmp/itf-active-run.lock}"
    [[ -r "$lock" ]] || return 0
    head -n 1 "$lock" 2>/dev/null || true
    return 0
}

# The repo root for the holder record: ITF_ROOT is tests/integrated.
_itf_runlock_repo_root() {
    local root=""
    root="$(cd "${ITF_ROOT:-../..}/../.." 2>/dev/null && pwd)" || root=""
    printf '%s' "${root:-unknown-tree}"
}

# Acquire the run lock. $1 = holder description ("journey run <name>",
# "template build ..."). Prints the waiting/heartbeats/refusals to
# stderr; returns 0 holding fd 9, non-zero when the lock could not be
# taken (the caller must NOT start the run).
itf_runlock_acquire() {
    local desc="$1"
    local lock="${ITF_RUN_LOCK:-/tmp/itf-active-run.lock}"
    local max_wait="${ITF_RUNLOCK_WAIT:-7200}"
    local hb="${ITF_RUNLOCK_HEARTBEAT:-30}"

    [[ "$max_wait" =~ ^[0-9]+$ ]] || max_wait=7200
    [[ "$hb" =~ ^[0-9]+$ ]] || hb=30
    # A heartbeat coarser than the whole wait budget would overshoot it.
    if (( max_wait > 0 && hb > max_wait )); then
        hb=$max_wait
    fi
    (( hb > 0 )) || hb=1

    if ! command -v flock >/dev/null 2>&1; then
        echo "itf: flock not found — cannot take the run lock;" >&2
        echo "itf: refusing to start unserialized (install util-linux)." >&2
        return 1
    fi

    # Open append-only so a refused starter never truncates the holder's
    # record; the rewrite below happens only while WE hold the lock.
    exec 9>>"$lock" || {
        echo "itf: cannot open run lock $lock" >&2
        return 1
    }

    if flock -n 9; then
        printf '%s | pid %s | started %s | %s\n' \
            "$desc" "$$" "$(date '+%Y-%m-%d %H:%M:%S %Z')" \
            "$(_itf_runlock_repo_root)" > "$lock" 2>/dev/null || true
        return 0
    fi

    local holder
    holder="$(itf_runlock_holder)"
    echo "itf: another itf run is active${holder:+ — $holder}" >&2
    echo "itf: concurrent runs share HTTP port ${ITF_HTTP_PORT:-8000}, the" >&2
    echo "itf: installer-syslog listener, and the base hosts' guest budget," >&2
    echo "itf: so this run will not start until that one finishes." >&2
    if (( max_wait == 0 )); then
        echo "itf: refusing now (ITF_RUNLOCK_WAIT=0). See: itf status" >&2
        return 1
    fi
    echo "itf: waiting up to $(( max_wait / 60 )) min (ITF_RUNLOCK_WAIT);" >&2
    echo "itf: heartbeats every ${hb}s; the run starts the moment the lock frees." >&2

    local waited=0
    while :; do
        if flock -w "$hb" 9; then
            echo "itf: run lock acquired after ${waited}s." >&2
            printf '%s | pid %s | started %s | %s\n' \
                "$desc" "$$" "$(date '+%Y-%m-%d %H:%M:%S %Z')" \
                "$(_itf_runlock_repo_root)" > "$lock" 2>/dev/null || true
            return 0
        fi
        waited=$(( waited + hb ))
        if (( waited >= max_wait )); then
            echo "itf: run lock still held after ${waited}s — giving up" >&2
            echo "itf: (ITF_RUNLOCK_WAIT). Holder at timeout:" >&2
            echo "itf: $(itf_runlock_holder)" >&2
            echo "itf: See: itf status" >&2
            return 1
        fi
        echo "itf: still waiting for the active run (${waited}s elapsed)..." >&2
    done
}

# Release explicitly (tests; normal runs release by process exit).
itf_runlock_release() {
    exec 9>&- 2>/dev/null || true
    return 0
}

# itf_runlock_orphan_fence [rerun-guests.tsv]
#
# Acquire-time orphan fence, run by the caller WHILE HOLDING the run
# lock (see the header).  Scans this tree's run records for INTERRUPTED
# runs whose recorded guests still exist on their base host and refuses
# the start, naming each leftover and its recovery commands.  Done runs
# are invisible to it by design: they legitimately keep guests for the
# run → fix → --rerun loop; only an interrupted run means the operator
# lost track of guests that are still consuming the base.
#
# $1 optionally names this run's rerun-guests.tsv: those (base, VMID)
# pairs are the guests THIS run takes over (journey run --rerun rolls
# them back to the staging checkpoint), so they are exempt — and when
# every candidate is exempt, no base is contacted at all (a rerun must
# not need its bases reachable to pass this fence).
#
# Semantics:
#   - no interrupted runs with guest records → rc 0, zero base contact
#     (the healthy path pays nothing);
#   - a recorded guest absent from its base's `qm list` → not a blocker
#     (the leftover was already destroyed);
#   - a base that cannot be queried fails CLOSED — an unverified base is
#     not a clean base;
#   - ITF_DRY_RUN skips the fence with a notice (dry-run mutates
#     nothing and its qm output is a print line, not a guest table).
#
# On refusal: prints the leftovers and recovery commands to stderr,
# RELEASES the run lock (fd 9), and returns 1 — the caller must not
# start the run.
itf_runlock_orphan_fence() {
    local exempt_spec="${1:-}"
    local runs_dir="${ITF_RUNS_DIR:-}"

    if [[ -n "${ITF_DRY_RUN:-}" ]]; then
        echo "itf: orphan fence skipped (ITF_DRY_RUN — no base query, no refusal)" >&2
        return 0
    fi
    [[ -d "$runs_dir" ]] || return 0

    # Guests this run takes over via --rerun ("<file> <base> <vmid>" per
    # line, written by the driver's rerun preparation).
    local -A exempt=()
    local _base _vmid
    if [[ -n "$exempt_spec" && -f "$exempt_spec" ]]; then
        while read -r _ _base _vmid _; do
            [[ -n "${_base:-}" && "${_vmid:-}" =~ ^[0-9]+$ ]] || continue
            exempt["$_base/$_vmid"]=1
        done < "$exempt_spec"
    fi

    # Candidates: guest records of interrupted runs, newest run first.
    local -a cands=()
    local run state caller rec base vmid rec_line
    while IFS= read -r run; do
        state="$(itf_run_state "$run")"
        [[ "$state" == "interrupted" ]] || continue
        # Strip the "caller:" prefix rather than splitting on ": *": the
        # value itself embeds a colon ("journey:<name>", "template:build").
        caller="$(awk '/^caller:/{sub(/^caller:[ \t]*/, ""); print; exit}' \
            "$run/meta.txt" 2>/dev/null)" || caller=""
        for rec in "$run"/guest*.txt; do
            [[ -f "$rec" ]] || continue
            base="" vmid=""
            read -r base vmid _ < "$rec" || true
            [[ -n "$base" && "$vmid" =~ ^[0-9]+$ ]] || continue
            rec_line="$(basename "$run")"$'\t'"${caller:-unknown}"
            rec_line+=$'\t'"$(basename "$rec")"$'\t'"$base"$'\t'"$vmid"
            cands+=("$rec_line")
        done
    done < <(ls -1d "$runs_dir"/run-* 2>/dev/null | sort -r)
    (( ${#cands[@]} > 0 )) || return 0

    # Only non-exempt candidates can block, and only they cost a base
    # query.
    local -a check=()
    local cand
    for cand in "${cands[@]}"; do
        IFS=$'\t' read -r _ _ _ base vmid <<< "$cand"
        [[ -n "${exempt["$base/$vmid"]:-}" ]] || check+=("$cand")
    done
    (( ${#check[@]} > 0 )) || return 0

    # One `qm list` per involved base is the authority on what exists —
    # the recorded file state never is (a dev restart orphans exactly
    # the kind of stale record a file-only check would trust).
    local -A present=() unreachable=() want=()
    local -a bases=()
    for cand in "${check[@]}"; do
        IFS=$'\t' read -r _ _ _ base vmid <<< "$cand"
        if [[ -z "${want["$base"]:-}" ]]; then
            want["$base"]=1
            bases+=("$base")
        fi
    done
    local b out v
    for b in "${bases[@]}"; do
        if ! out="$(itf_qm "$b" list 2>/dev/null)"; then
            unreachable["$b"]=1
            continue
        fi
        while read -r v _; do
            [[ "$v" =~ ^[0-9]+$ ]] || continue
            present["$b/$v"]=1
        done <<< "$out"
    done

    # Blockers, their destroy commands, and — per interrupted JOURNEY —
    # the rerun hint that reuses its guests in place.
    local -a blockers=() destroys=() hints=()
    local -A seen=() destroy_seen=() hint_seen=()
    local rname rcaller gfile
    for cand in "${check[@]}"; do
        IFS=$'\t' read -r rname rcaller gfile base vmid <<< "$cand"
        [[ -n "${seen["$rname/$base/$vmid"]:-}" ]] && continue
        seen["$rname/$base/$vmid"]=1
        if [[ -n "${unreachable["$base"]:-}" ]]; then
            blockers+=("$rname: $base/$vmid ($gfile)" \
"— base unreachable, existence unverified")
        else
            [[ -n "${present["$base/$vmid"]:-}" ]] || continue
            blockers+=("$rname: $base/$vmid ($gfile)")
        fi
        if [[ -z "${destroy_seen["$base/$vmid"]:-}" ]]; then
            destroy_seen["$base/$vmid"]=1
            destroys+=("itf guest destroy $base $vmid")
        fi
        if [[ "$rcaller" == journey:* && -z "${hint_seen["$rcaller"]:-}" ]]; then
            hint_seen["$rcaller"]=1
            hints+=("itf journey run ${rcaller#journey:} --rerun")
        fi
    done
    (( ${#blockers[@]} > 0 )) || return 0

    echo "itf: refusing to start: interrupted runs left guests on the base hosts:" >&2
    for cand in "${blockers[@]}"; do
        echo "itf:   $cand" >&2
    done
    if (( ${#hints[@]} > 0 )); then
        echo "itf: recover first — reuse the leftovers in place (rolls them back" >&2
        echo "itf: to the staging checkpoint, no re-clone/reinstall):" >&2
        for cand in "${hints[@]}"; do
            echo "itf:   $cand" >&2
        done
        echo "itf: or discard each leftover (guests are disposable at any time):" >&2
    else
        echo "itf: recover first — discard each leftover (guests are disposable" >&2
        echo "itf: at any time; this interrupted run has no rerun path):" >&2
    fi
    for cand in "${destroys[@]}"; do
        echo "itf:   $cand" >&2
    done
    echo "itf: (the run lock fences dev processes; the guests live on the bases" >&2
    echo "itf: and outlive it — this fence makes the bases the authority)" >&2
    itf_runlock_release
    return 1
}

# One-line lock state for `itf status`: names the holder when held. The
# probe runs in a subshell so its own lock attempt cannot linger.
itf_runlock_status() {
    local lock="${ITF_RUN_LOCK:-/tmp/itf-active-run.lock}"
    if [[ ! -e "$lock" ]]; then
        echo "  free"
        return 0
    fi
    if ( exec 9>>"$lock" && flock -n 9 ) 2>/dev/null; then
        echo "  free"
    else
        echo "  held — $(itf_runlock_holder)"
    fi
    return 0
}
