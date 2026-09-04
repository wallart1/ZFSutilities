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
#
#   The node config file itself uses the uppercase names NODE_MODE,
#   STORAGE_HOST, COMPUTE_HOST, STORAGE_IP, IQN_PREFIX, POOL_TARGET.
#   Those are externally set (config file / tests) and stay uppercase; this
#   library exposes lowercase copies for internal use.
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
    declare -A pool_target=() 2>/dev/null || true
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

    if ! declare -p POOL_TARGET >/dev/null 2>&1; then
        log_msg "FATAL: $NODE_CONF: POOL_TARGET associative array is not declared"
        exit 1
    fi
    declare -A pool_target=()
    for _pool in "${!POOL_TARGET[@]}"; do
        pool_target["$_pool"]="${POOL_TARGET[$_pool]}"
    done
    unset _pool
fi

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
    echo "${iqn_prefix}:${short}"
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
