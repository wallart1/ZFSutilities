#!/usr/bin/env bash
# tests/integrated/lib/base-lib.sh
#
# Guarded access to the base Proxmox systems.
#
# SAFETY MODEL — this library is the only sanctioned path for the
# orchestrator to touch a base PVE host, and it enforces the confinement
# rules agreed in the Phase 0 plan:
#
#   1. Only qm lifecycle verbs from a fixed allow-list may run, and only
#      against VMIDs inside the reserved range (site config ITF_VMID_FIRST
#      .. ITF_VMID_LAST).
#   2. Storage references (any "storage:..." token) must name the itf
#      storages from the site config — the base system's own storages
#      (local, local-lvm, ...) can never be written through this path.
#   3. Absolute paths are rejected unless they live under the configured
#      ISO directory.
#   4. Every mutating operation is appended to the audit log on the base
#      host (ITF_ACTION_LOG) before it runs.
#   5. pvesm is read-only ("status" only) and general reads go through a
#      small allow-list (itf_read).  The orchestrator never edits storage
#      definitions, network config, systemd units, or packages on a base.
#   6. ITF_DRY_RUN=1 prints guarded commands instead of executing them.
#
# The daily snapshots of the base VMs are the recovery net behind these
# guardrails, not a substitute for them.

if [[ -n "${ITF_LIB_BASE_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_BASE_LOADED=1

# Read-only qm verbs the orchestrator may use.
_ITF_QM_READ_VERBS="list status config version guest terminal monitor wait"
# Mutating qm verbs — each one is audit-logged before execution.
_ITF_QM_MUTATE_VERBS="create set start resume stop shutdown snapshot rollback destroy"

_itf_verb_allowed() {
    local verb="$1"
    [[ " $_ITF_QM_READ_VERBS $_ITF_QM_MUTATE_VERBS " == *" $verb "* ]]
}

_itf_verb_mutating() {
    local verb="$1"
    [[ " $_ITF_QM_MUTATE_VERBS " == *" $verb "* ]]
}

# itf_vmid_in_range <vmid>
itf_vmid_in_range() {
    local vmid="$1"
    [[ "$vmid" =~ ^[0-9]+$ ]] || return 1
    (( vmid >= ITF_VMID_FIRST && vmid <= ITF_VMID_LAST ))
}

# itf_storage_allowed <name>
itf_storage_allowed() {
    local name="$1"
    [[ "$name" == "$ITF_GUEST_STORAGE" || "$name" == "$ITF_ISO_STORAGE" ]]
}

# itf_qm_check <args...>
#
# Validates a qm argument vector against the confinement rules.  Returns 0
# and stays silent when acceptable; otherwise prints each violation to
# stderr and returns 1.  Rules:
#   - the verb must be allow-listed;
#   - every standalone numeric token is a VMID and must be in range;
#   - every token containing ':' must be a "storage:payload" reference with
#     an itf storage prefix and a slash-free payload;
#   - every absolute path must live under ITF_ISO_DIR.
itf_qm_check() {
    local bad=0
    local i token prev rest prefix value
    local -a args=("$@")

    if (( ${#args[@]} == 0 )); then
        echo "itf-guard: no qm verb given" >&2
        return 1
    fi

    local verb="${args[0]}"
    if ! _itf_verb_allowed "$verb"; then
        echo "itf-guard: qm verb '$verb' is not allow-listed" >&2
        bad=1
    fi

    for (( i = 0; i < ${#args[@]}; i++ )); do
        token="${args[i]}"
        prev=""
        if (( i > 0 )); then
            prev="${args[i - 1]}"
        fi

        # Standalone numeric token = VMID (option values follow a '-' token).
        if [[ "$token" =~ ^[0-9]+$ && ! "$prev" == -* ]]; then
            if ! itf_vmid_in_range "$token"; then
                echo "itf-guard: VMID $token is outside the reserved range" \
                    "${ITF_VMID_FIRST}-${ITF_VMID_LAST}" >&2
                bad=1
            fi
        fi

        # For --opt=value tokens, examine the value part too.
        rest="$token"
        if [[ "$token" == --*=* ]]; then
            rest="${token#*=}"
        fi

        # Storage-reference shape: name before the first colon.
        if [[ "$rest" == *:* ]]; then
            prefix="${rest%%:*}"
            if [[ "$prefix" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]]; then
                if ! itf_storage_allowed "$prefix"; then
                    echo "itf-guard: storage '$prefix' is not an itf storage" \
                        "(guest: $ITF_GUEST_STORAGE, iso: $ITF_ISO_STORAGE)" >&2
                    bad=1
                fi
                # Payload: plain volume names (itfguests:32) or dir-storage
                # content paths (itfiso:iso/name.iso), optionally followed
                # by PVE comma options (...,media=cdrom).  Volname = safe
                # path segments, never a ".." segment; options = bounded
                # charset, no whitespace.
                value="${rest#*:}"
                local volname="${value%%,*}"
                local volopts=""
                [[ "$value" == *,* ]] && volopts="${value#*,}"
                if [[ ! "$volname" =~ ^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$ \
                    || "$volname" == *".."* ]]; then
                    echo "itf-guard: storage payload has unsafe characters: $rest" >&2
                    bad=1
                fi
                if [[ -n "$volopts" && ! "$volopts" =~ \
                    ^[A-Za-z0-9_.=-]+(,[A-Za-z0-9_.=-]+)*$ ]]; then
                    echo "itf-guard: storage options have unsafe characters: $rest" >&2
                    bad=1
                fi
            fi
        fi

        # Absolute paths only under the ISO directory.
        if [[ "$token" == /* && "$token" != "$ITF_ISO_DIR"* ]]; then
            echo "itf-guard: absolute path '$token' is outside $ITF_ISO_DIR" >&2
            bad=1
        fi
    done

    return "$bad"
}

# itf_log_action <base-host> <text>
#
# Appends a timestamped line to the audit log on the base host.
itf_log_action() {
    local base="$1" text="$2"
    local line
    line="$(date -u '+%Y-%m-%dT%H:%M:%SZ') itf[$$]: $text"
    itf_base_exec "$base" \
        "printf '%s\n' $(printf '%q' "$line") >> $(printf '%q' "$ITF_ACTION_LOG")"
}

# itf_qm <base-host> <qm-args...>
#
# Guarded qm: validates the arguments, audit-logs mutating verbs, then runs
# qm on the base host as root.  Set ITF_DRY_RUN=1 to print instead of
# execute (the audit log entry is still written, marked DRY-RUN).
# Refusals return 22 without touching the base host.
itf_qm() {
    local base="$1"
    shift

    if ! itf_qm_check "$@"; then
        echo "itf: REFUSED qm $* on $base (see itf-guard messages above)" >&2
        return 22
    fi

    local remote="qm"
    local a
    for a in "$@"; do
        remote+=" $(printf '%q' "$a")"
    done

    if _itf_verb_mutating "$1"; then
        local marker=""
        [[ -n "${ITF_DRY_RUN:-}" ]] && marker=" DRY-RUN"
        itf_log_action "$base" "qm${marker}: $remote"
    fi

    if [[ -n "${ITF_DRY_RUN:-}" ]]; then
        echo "[dry-run] $base: $remote"
        return 0
    fi

    itf_base_exec "$base" "$remote"
}

# itf_pvesm <base-host> status
#
# The only pvesm operation allowed: read-only status.
itf_pvesm() {
    local base="$1" sub="${2:-}"
    if [[ "$sub" != "status" ]]; then
        echo "itf-guard: pvesm '$sub' refused (status is the only allowed subcommand)" >&2
        return 22
    fi
    itf_base_exec "$base" "pvesm status"
}

# itf_read <base-host> <command...>
#
# Allow-listed read-only commands on a base host.  Anything not matching an
# entry below is refused with rc 22 — the orchestrator has no general
# shell on the base systems.
itf_read() {
    local base="$1"
    shift
    local cmd="$*"

    _itf_starts_with() { [[ "$1" == "$2"* ]]; }
    _itf_ends_with() { [[ "$1" == *"$2" ]]; }

    local allowed=0
    case "$cmd" in
        pveversion|pvesm\ status|free\ -h|nproc|lsblk|hostname\ -I) allowed=1 ;;
    esac
    if (( ! allowed )) && _itf_starts_with "$cmd" "grep " \
        && _itf_ends_with "$cmd" " /proc/cpuinfo"; then allowed=1; fi
    if (( ! allowed )) && _itf_starts_with "$cmd" "ip link show "; then allowed=1; fi
    if (( ! allowed )) && _itf_starts_with "$cmd" "ip -d link show "; then allowed=1; fi
    if (( ! allowed )) && { _itf_starts_with "$cmd" "test -e " \
        || _itf_starts_with "$cmd" "test -f "; }; then allowed=1; fi
    if (( ! allowed )) && _itf_starts_with "$cmd" "tail -" \
        && _itf_ends_with "$cmd" " $ITF_ACTION_LOG"; then allowed=1; fi
    if (( ! allowed )) && _itf_starts_with "$cmd" "ls -l $ITF_ISO_DIR"; then allowed=1; fi

    if (( ! allowed )); then
        echo "itf-guard: read command not allow-listed: $cmd" >&2
        return 22
    fi

    # Rebuild the command with per-argument quoting: the remote bash -c
    # re-parses the string, so any metacharacters inside an argument (e.g.
    # the '(vmx|svm)' pattern) must arrive escaped, as they would when
    # typed in quotes.
    local quoted="" a
    for a in "$@"; do
        quoted+=" $(printf '%q' "$a")"
    done
    itf_base_exec "$base" "${quoted# }"
}
