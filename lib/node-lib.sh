#!/usr/bin/bash
# shellcheck disable=SC2034
# /usr/local/lib/node-lib.sh
#
# Helper library for scripts that may run in single-node or two-node mode.
# Replaces two-node-lib.sh with mode-aware behavior.
#
# Sourced as the very first non-comment line in every VM disk management
# and ZFS clone script.
#
# Sourcing this file:
#   1. Loads /etc/zfsutilities-node.conf (or falls back to /etc/two-node.conf
#      for backward compatibility), failing clearly if neither exists.
#   2. In single-node mode: sets STORAGE_HOST=COMPUTE_HOST=THIS_HOST,
#      leaves iSCSI vars empty.
#   3. In two-node mode: validates all required vars as before.
#   4. Defines mode-check and pool helper functions.
#
# After this file has been sourced, the following are available to the caller:
#
#   node_mode         "single-node" or "two-node" (copied from NODE_MODE)
#   storage_host      short hostname of the storage host (= this_host in single-node)
#   compute_host      short hostname of the compute host (= this_host in single-node)
#   this_host         short hostname of this machine (always set)
#
#   Two-node only:
#   storage_ip        iSCSI portal IP on the storage network
#   iqn_prefix        iSCSI target IQN prefix
#   pool_target       associative array: pool name -> target short name
#                     (copied from POOL_TARGET)
#   expected_iscsi_devices
#                     optional minimum iSCSI device (LUN) count used by
#                     rescan-storage's low-device warning (copied from
#                     EXPECTED_ISCSI_DEVICES; empty disables the warning)
#
#   The node config file itself uses the uppercase names NODE_MODE,
#   STORAGE_HOST, COMPUTE_HOST, STORAGE_IP, IQN_PREFIX, POOL_TARGET,
#   EXPECTED_ISCSI_DEVICES (optional). Those are externally set (config file /
#   tests) and stay uppercase; this library exposes lowercase copies for
#   internal use.
#
#   is_single_node          returns 0 in single-node mode
#   is_two_node             returns 0 in two-node mode
#   pool_to_target <pool>   echoes the full IQN (two-node only), returns 1 if unknown or single-node
#   pool_list               echoes valid pool names from pool_target (two-node only)
#   is_known_pool <pool>    two-node: returns 0 if pool is in pool_target; else 1
#   gen_mac                 generates a Proxmox-compatible random MAC address
#   get_json_archive_path   reads archive_path from the JSON config file

# Co-operate with bashinit: ensure $mydir is set when this library is sourced
# before bashinit runs.  bashinit itself will overwrite nothing if $mydir is
# already set, so this is safe to call first.
if [[ -z "${mydir:-}" && -n "${BASH_SOURCE[1]:-}" ]]; then
    mydir=$(cd "$(dirname "$(realpath "${BASH_SOURCE[1]}")")" && pwd)
fi

# Minimal log_msg fallback for the rare case this library is sourced before
# bashinit.  The real bashinit log_msg will replace this once it is loaded.
if [[ $(type -t log_msg 2>/dev/null) != "function" ]]; then
    function log_msg {
        local caller_file="${BASH_SOURCE[1]:-node-lib.sh}"
        local caller_line="${BASH_LINENO[0]}"
        echo "$(realpath "$caller_file"):$caller_line: $*" >&2
    }
fi

# Load centralized paths if not already inherited from bashinit.
if [[ -z "${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-}" ]]; then
    PATHS_LIB="${PATHS_LIB:-$(find_zfsutility_script paths.sh)}"
    if [[ -n "$PATHS_LIB" ]]; then
        # shellcheck source=/dev/null
        source "$PATHS_LIB"
    fi
fi

: "${NODE_CONF:=${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}/node.conf}"

# Backward compatibility: fall back to legacy /etc/zfsutilities-node.conf and
# /etc/two-node.conf if the new conf doesn't exist.
if [[ ! -r "$NODE_CONF" ]]; then
    if [[ -r "${ZFSUTILITIES_LEGACY_NODE_CONF:-/etc/zfsutilities-node.conf}" ]]; then
        NODE_CONF="${ZFSUTILITIES_LEGACY_NODE_CONF:-/etc/zfsutilities-node.conf}"
    elif [[ -r "${ZFSUTILITIES_LEGACY_TWO_NODE_CONF:-/etc/two-node.conf}" ]]; then
        NODE_CONF="${ZFSUTILITIES_LEGACY_TWO_NODE_CONF:-/etc/two-node.conf}"
    else
        log_msg "FATAL: Missing $NODE_CONF"
        log_msg "FATAL:   Install via: bin/install-single-node or install-two-node"
        exit 1
    fi
fi

# shellcheck source=/etc/zfsutilities-node.conf
source "$NODE_CONF"

# Backward compat: configs without NODE_MODE are legacy two-node configs
node_mode="${NODE_MODE:-two-node}"
this_host=$(hostname -s)

is_single_node() { [[ "$node_mode" == "single-node" ]]; }
is_two_node()    { [[ "$node_mode" == "two-node" ]]; }

if is_single_node; then
    storage_host="${STORAGE_HOST:-$this_host}"
    compute_host="${COMPUTE_HOST:-$this_host}"
    storage_ip="${STORAGE_IP:-}"
    iqn_prefix="${IQN_PREFIX:-}"
    # -g is required: libraries are loaded through bashinit's source_helper
    # function (e.g. unarchive-vm's ssh payloads), and a bare declare here
    # would create a function-local that vanishes when source_helper returns,
    # emptying the map under pool_to_target/pool_list/is_known_pool.
    declare -gA pool_target=() 2>/dev/null || true
else
    # Two-node mode: copy the externally set config vars to lowercase and
    # validate the copies.
    storage_host="${STORAGE_HOST:-}"
    compute_host="${COMPUTE_HOST:-}"
    storage_ip="${STORAGE_IP:-}"
    iqn_prefix="${IQN_PREFIX:-}"
    for _v in storage_host compute_host storage_ip iqn_prefix; do
        if [[ -z "${!_v:-}" ]]; then
            log_msg "FATAL: $NODE_CONF: $_v is empty or unset"
            exit 1
        fi
    done
    unset _v

    # POOL_TARGET is declared by the sourced node.conf, not in this file.
    # shellcheck disable=SC2153
    if ! declare -p POOL_TARGET >/dev/null 2>&1; then
        log_msg "FATAL: $NODE_CONF: POOL_TARGET associative array is not declared"
        exit 1
    fi
    # -g is required: libraries are loaded through bashinit's source_helper
    # function, and a bare declare here would create a function-local that
    # vanishes when source_helper returns, emptying the map under
    # pool_to_target/pool_list/is_known_pool.
    declare -gA pool_target=()
    for _pool in "${!POOL_TARGET[@]}"; do
        pool_target["$_pool"]="${POOL_TARGET[$_pool]}"
    done
    unset _pool
fi

# Optional in either mode (consumed only by two-node iSCSI scripts): the
# operator-declared minimum iSCSI device count for rescan-storage's
# low-device warning.  Empty means "no expectation declared" and disables it.
expected_iscsi_devices="${EXPECTED_ISCSI_DEVICES:-}"

# One-shot per-process cache of the local LIO target list, probed lazily by
# _warn_when_target_missing. Empty string means "not probed yet"; after a
# probe the variable is always set (possibly to an empty list).
_lio_target_list=""
declare -gA _lio_warned_targets=() 2>/dev/null || true

# Warn once per IQN when the constructed target does not exist in the local
# LIO tree. This catches IQN-prefix drift: node.conf's iqn_prefix differs
# from the prefix of the live targets (e.g. after a reinstall in a different
# month), so LUN mapping would target a fresh/empty target while Proxmox
# still logs in to the old one. Best-effort and read-only: it never changes
# pool_to_target's result, runs only on the storage host (the only host
# with a LIO target tree), and stays silent when targetcli is absent or no
# targets exist yet (fresh install before setup-iscsi-targets).
_warn_when_target_missing() {
    local iqn="$1"
    [[ "$(hostname -s)" == "$storage_host" ]] || return 0
    command -v targetcli >/dev/null 2>&1 || return 0
    if [[ -z "$_lio_target_list" ]]; then
        _lio_target_list=$(targetcli /iscsi ls 2>/dev/null || true)
    fi
    printf '%s\n' "$_lio_target_list" | grep -q "iqn\." || return 0
    if [[ -n "${_lio_warned_targets[$iqn]:-}" ]]; then
        return 0
    fi
    if ! printf '%s\n' "$_lio_target_list" | grep -q "$iqn"; then
        _lio_warned_targets["$iqn"]=1
        log_msg "WARN: pool_to_target: target $iqn does not exist in the local LIO target tree"
        log_msg "WARN:   If targets exist under a different IQN prefix, node.conf's IQN_PREFIX"
        log_msg "WARN:   has drifted from the live targets — LUNs would map to the wrong target."
        log_msg "WARN:   Check 'targetcli /iscsi ls' and the IQN_PREFIX in $NODE_CONF."
    fi
    return 0
}

# probe_target_usage <full-iqn>
# Read-only usage probe for one iSCSI target, for the IQN-prefix-drift
# guards (setup-iscsi-targets orphan deletion, install-two-node drift
# confirmation): determines whether anything still consumes the target so
# those decisions never depend on the operator knowing what an ACL is or
# where Proxmox keeps guest configs.
#
# Prints plain-language evidence lines via log_msg and returns:
#   0 — VERIFIED UNUSED: no guest config on the compute host references
#       the target and no live iSCSI session is attached to it
#   1 — IN USE or UNVERIFIABLE: a guest config references it, a live
#       session is attached, or the compute host could not be reached
#       (unreachable is treated as in use, so the unsafe action is the
#       one that gets refused)
#
# Storage-side ACL state is printed as context only: two-node targets may
# run demo-mode ACLs (generate_node_acls=1), where an empty ACL list
# means "any initiator may log in", not "nobody uses it" — the
# authoritative usage signal is the compute host. Strictly read-only.
probe_target_usage() {
    local iqn="$1"

    # An IQN's alphabet is [A-Za-z0-9.:_-]; anything else is not ours to
    # interpolate into the ssh command string below — refuse rather than
    # risk it.
    [[ "$iqn" =~ ^iqn\.[A-Za-z0-9.:_-]+$ ]] || return 1
    [[ "$(hostname -s)" == "$storage_host" ]] || return 1
    command -v targetcli >/dev/null 2>&1 || return 1

    # The two regexes in this function are character-class filters over the
    # iSCSI-name grammar (RFC 3720: "iqn." followed by date- and
    # domain-qualified names, colon-separated; the only characters legal in
    # any of its segments are letters, digits, dots, colons, underscores,
    # and hyphens):
    #   ^iqn\.[A-Za-z0-9.:_-]+$   — full-string validation of the caller's
    #                               IQN argument (safety fence above)
    #   iqn\.[A-Za-z0-9.:_-]*     — extraction of initiator IQN tokens from
    #                               targetcli's acls-ls listing
    # Both are anchored on the literal "iqn." prefix; neither needs
    # alternation or look-around.

    local acl_initiators
    acl_initiators=$(targetcli "/iscsi/${iqn}/tpg1/acls" ls 2>/dev/null \
        | grep -o 'iqn\.[A-Za-z0-9.:_-]*' | sort -u | tr '\n' ' ')
    if [[ -n "$acl_initiators" ]]; then
        log_msg "INFO: probe: ${iqn} — ACL initiators: ${acl_initiators}"
    elif targetcli "/iscsi/${iqn}/tpg1" get attribute generate_node_acls 2>/dev/null \
            | grep -q "generate_node_acls=1"; then
        log_msg "INFO: probe: ${iqn} — demo-mode ACLs (any initiator may log" \
            "in; an empty ACL list is normal)"
    fi

    # One round trip: guest configs referencing the IQN (VM and container),
    # plus the count of live initiator sessions. The trailing echo makes
    # the remote command's exit status 0 even when grep finds nothing.
    local remote_out
    if ! remote_out=$(ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${compute_host}" \
            "grep -l -- '${iqn}' /etc/pve/qemu-server/*.conf /etc/pve/lxc/*.conf 2>/dev/null; \
             echo SESSIONS:\$(iscsiadm -m session 2>/dev/null | grep -c -- '${iqn}')" \
            2>/dev/null); then
        log_msg "WARN: probe: could not verify ${iqn} — ${compute_host}" \
            "unreachable via SSH; treating as in use"
        return 1
    fi

    local session_count vm_configs conf
    session_count="${remote_out##*SESSIONS:}"
    vm_configs="${remote_out%%SESSIONS:*}"
    session_count="${session_count//[[:space:]]/}"
    vm_configs="${vm_configs//$'\n'/ }"

    if [[ -n "${vm_configs// /}" ]]; then
        log_msg "WARN: probe: ${iqn} — guest configs on ${compute_host} still" \
            "reference this target:"
        # shellcheck disable=SC2086 # word-splitting the grep -l list is intended
        for conf in $vm_configs; do
            log_msg "WARN: probe:   $(basename "$conf")"
        done
        return 1
    fi
    if [[ "$session_count" =~ ^[0-9]+$ && "$session_count" -gt 0 ]]; then
        log_msg "WARN: probe: ${iqn} — ${session_count} live iSCSI session(s) attached"
        return 1
    fi

    log_msg "INFO: probe: ${iqn} — no guest config on ${compute_host}" \
        "references this target and no live session exists (verified unused)"
    return 0
}

# pool_to_target <pool> -> echoes the full IQN, returns 1 if pool unknown or single-node
pool_to_target() {
    local pool="$1"
    if is_single_node; then
        log_msg "WARN: pool_to_target: iSCSI not available in single-node mode"
        return 1
    fi
    local short="${pool_target[$pool]:-}"
    if [[ -z "$short" ]]; then
        log_msg "WARN: Unknown pool: $pool (not in POOL_TARGET in $NODE_CONF)"
        return 1
    fi
    local iqn="${iqn_prefix}:${short}"
    _warn_when_target_missing "$iqn"
    echo "$iqn"
}

# pool_list -> echoes valid pool names, one per line (two-node only; empty in single-node)
pool_list() {
    is_single_node && return 0
    printf '%s\n' "${!pool_target[@]}"
}

# is_known_pool <pool> -> 0 if in POOL_TARGET, 1 otherwise (always 1 in single-node)
is_known_pool() {
    is_single_node && return 1
    [[ -n "${pool_target[$1]:-}" ]]
}

# remote_zfsutilities_bin <host>
# SSH to root@host and resolve the active version's bin/ directory via the
# /usr/local/lib/zfsutilities/current symlink.  Prints the resolved path and
# returns 0 on success; returns 1 if the remote path cannot be resolved.
remote_zfsutilities_bin() {
    local host="$1"
    local bin_path
    bin_path=$(ssh -o ConnectTimeout=10 "root@${host}" \
        'realpath /usr/local/lib/zfsutilities/current/bin 2>/dev/null' \
        '|| readlink -f /usr/local/lib/zfsutilities/current/bin 2>/dev/null' \
        2>/dev/null)
    if [[ -n "$bin_path" ]]; then
        printf '%s\n' "$bin_path"
        return 0
    fi
    return 1
}

# remote_zfsutility_script <host> <name>
# Combine remote_zfsutilities_bin and find_zfsutility_script semantics for
# remote execution.  Prints "<remote_bin>/<name>" when resolution succeeds,
# otherwise prints just "<name>" so the caller can fall back to the remote
# PATH.
remote_zfsutility_script() {
    local host="$1"
    local name="$2"
    local remote_bin
    remote_bin=$(remote_zfsutilities_bin "$host")
    if [[ -n "$remote_bin" ]]; then
        printf '%s/%s\n' "$remote_bin" "$name"
    else
        printf '%s\n' "$name"
    fi
}

# ------------------------------------------------------------------
# Clone helpers
# ------------------------------------------------------------------
# These are used by scripts in bin/ that manage VM clones.  They live here
# because those scripts already source node-lib.sh for single-node / two-node
# configuration.

# Generate a Proxmox-compatible random MAC address.
gen_mac() {
    printf 'BC:24:11:%02X:%02X:%02X' \
        $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256))
}

# Read the archive_path value from the JSON config file.
get_json_archive_path() {
    local config_file=\
"${JSON_CONFIG:-${ZFSUTILITIES_CONFIG_PATH:-/var/lib/zfsutilities/config.json}}"
    # Legacy fallback: use the old path if the new one has not been migrated yet.
    local legacy_config="${ZFSUTILITIES_LEGACY_CONFIG_PATH:-/root/.config/zfsutilities.json}"
    if [[ ! -e "$config_file" && -f "$legacy_config" ]]; then
        config_file="$legacy_config"
    fi
    python3 -c "
import json
try:
    with open('${config_file}') as f:
        c = json.load(f)
    print(c.get('archive_path', ''), end='')
except Exception:
    pass
"
}

# Read the archive_rate_limit value from the JSON config file (a rate
# value such as 100M, or empty for unlimited).
get_json_archive_rate_limit() {
    local config_file=\
"${JSON_CONFIG:-${ZFSUTILITIES_CONFIG_PATH:-/var/lib/zfsutilities/config.json}}"
    local legacy_config="${ZFSUTILITIES_LEGACY_CONFIG_PATH:-/root/.config/zfsutilities.json}"
    if [[ ! -e "$config_file" && -f "$legacy_config" ]]; then
        config_file="$legacy_config"
    fi
    python3 -c "
import json
try:
    with open('${config_file}') as f:
        c = json.load(f)
    print(c.get('archive_rate_limit', ''), end='')
except Exception:
    pass
"
}

# Write one key into the JSON config file, creating the file when missing.
# An empty value removes the key. Usage: save_json_config_key <key> <value>
save_json_config_key() {
    local key="$1" value="$2"
    local config_file=\
"${JSON_CONFIG:-${ZFSUTILITIES_CONFIG_PATH:-/var/lib/zfsutilities/config.json}}"
    python3 - "$config_file" "$key" "$value" << 'PYEOF'
import json, os, sys
conf_file, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(conf_file) as f:
        c = json.load(f)
except Exception:
    c = {}
if value == "":
    c.pop(key, None)
else:
    c[key] = value
os.makedirs(os.path.dirname(conf_file), exist_ok=True)
with open(conf_file, 'w') as f:
    json.dump(c, f, indent=2)
PYEOF
}

# Join a path under a mountpoint without doubling the slash: an absolute
# suffix (e.g. /etc/pve/qemu-server/205.conf mirrored under an archive
# mount) or a trailing slash on the mount must not produce "//".
# Usage: path_under_mount <mount> <path>  (prints the joined path)
path_under_mount() {
    local mount="$1" suffix="$2"
    printf '%s/%s' "${mount%/}" "${suffix#/}"
}

# Run a payload (read from stdin, like an ssh here-doc) on the storage
# host. When this shell already IS the storage host the payload runs
# locally in a subshell — so its `set -e` dies with it and the caller's
# shell functions (including test mocks) stay visible — with
# ZFSUTILITIES_BIN_DIR pointing at the orchestrator's helper directory;
# otherwise the payload ships over `ssh bash -s` with transfer_rate_limit
# forwarded. Positional arguments after the function name become the
# payload's "$@". Usage:
#   on_storage <args...> << 'EOF' ... payload ... EOF
on_storage() {
    local payload_tmp rc
    payload_tmp=$(mktemp "${TMPDIR:-/tmp}/zfsu-payload.XXXXXX")
    # The path is baked into the handler (payload_tmp is local and gone by
    # exit time); the guard covers contexts without bashinit's trap helper.
    if declare -f append_exit_trap >/dev/null 2>&1; then
        append_exit_trap "rm -f '$payload_tmp'"
    fi
    cat > "$payload_tmp"
    if [[ "$(hostname -s)" == "$storage_host" ]]; then
        (
            export ZFSUTILITIES_BIN_DIR="${ZFSUTILITIES_BIN_DIR:-$mydir}"
            set -- "$@"
            # shellcheck disable=SC1090
            source "$payload_tmp"
        )
        rc=$?
    else
        ssh root@"$storage_host" \
            "transfer_rate_limit='${transfer_rate_limit:-}' bash -s" "$@" \
            < "$payload_tmp"
        rc=$?
    fi
    rm -f "$payload_tmp"
    return $rc
}

# Mirror of on_storage for the compute host.
on_compute() {
    local payload_tmp rc
    payload_tmp=$(mktemp "${TMPDIR:-/tmp}/zfsu-payload.XXXXXX")
    if declare -f append_exit_trap >/dev/null 2>&1; then
        append_exit_trap "rm -f '$payload_tmp'"
    fi
    cat > "$payload_tmp"
    if [[ "$(hostname -s)" == "$compute_host" ]]; then
        (
            export ZFSUTILITIES_BIN_DIR="${ZFSUTILITIES_BIN_DIR:-$mydir}"
            set -- "$@"
            # shellcheck disable=SC1090
            source "$payload_tmp"
        )
        rc=$?
    else
        ssh root@"$compute_host" \
            "transfer_rate_limit='${transfer_rate_limit:-}' bash -s" "$@" \
            < "$payload_tmp"
        rc=$?
    fi
    rm -f "$payload_tmp"
    return $rc
}
