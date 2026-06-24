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
#   NODE_MODE         "single-node" or "two-node"
#   STORAGE_HOST      short hostname of the storage host (= THIS_HOST in single-node)
#   COMPUTE_HOST      short hostname of the compute host (= THIS_HOST in single-node)
#   THIS_HOST         short hostname of this machine (always set)
#
#   Two-node only:
#   STORAGE_IP        iSCSI portal IP on the storage network
#   IQN_PREFIX        iSCSI target IQN prefix
#   POOL_TARGET       associative array: pool name -> target short name
#
#   is_single_node          returns 0 in single-node mode
#   is_two_node             returns 0 in two-node mode
#   pool_to_target <pool>   echoes the full IQN (two-node only), returns 1 if unknown or single-node
#   pool_list               echoes valid pool names from POOL_TARGET (two-node only)
#   is_known_pool <pool>    returns 0 if pool is in POOL_TARGET (two-node only; always 1 in single-node)

: "${NODE_CONF:=/etc/zfsutilities-node.conf}"

# Backward compatibility: fall back to /etc/two-node.conf if new conf doesn't exist
if [[ ! -r "$NODE_CONF" ]]; then
    if [[ -r /etc/two-node.conf ]]; then
        NODE_CONF="/etc/two-node.conf"
    else
        echo "✗ Missing $NODE_CONF" >&2
        echo "  Install via: 10 Installers/install-single-node or install-two-node" >&2
        exit 1
    fi
fi

# shellcheck source=/etc/zfsutilities-node.conf
source "$NODE_CONF"

# Backward compat: configs without NODE_MODE are legacy two-node configs
: "${NODE_MODE:=two-node}"

THIS_HOST=$(hostname -s)

is_single_node() { [[ "$NODE_MODE" == "single-node" ]]; }
is_two_node()    { [[ "$NODE_MODE" == "two-node" ]]; }

if is_single_node; then
    : "${THIS_HOST:=$(hostname -s)}"
    STORAGE_HOST="$THIS_HOST"
    COMPUTE_HOST="$THIS_HOST"
    STORAGE_IP=""
    IQN_PREFIX=""
    declare -A POOL_TARGET=() 2>/dev/null || true
else
    # Two-node mode: validate required vars
    for _v in STORAGE_HOST COMPUTE_HOST STORAGE_IP IQN_PREFIX; do
        if [[ -z "${!_v:-}" ]]; then
            echo "✗ $NODE_CONF: $_v is empty or unset" >&2
            exit 1
        fi
    done
    unset _v

    if ! declare -p POOL_TARGET >/dev/null 2>&1; then
        echo "✗ $NODE_CONF: POOL_TARGET associative array is not declared" >&2
        exit 1
    fi
fi

# pool_to_target <pool> -> echoes the full IQN, returns 1 if pool unknown or single-node
pool_to_target() {
    local pool="$1"
    if is_single_node; then
        echo "✗ pool_to_target: iSCSI not available in single-node mode" >&2
        return 1
    fi
    local short="${POOL_TARGET[$pool]:-}"
    if [[ -z "$short" ]]; then
        echo "✗ Unknown pool: $pool (not in POOL_TARGET in $NODE_CONF)" >&2
        return 1
    fi
    echo "${IQN_PREFIX}:${short}"
}

# pool_list -> echoes valid pool names, one per line (two-node only; empty in single-node)
pool_list() {
    is_single_node && return 0
    printf '%s\n' "${!POOL_TARGET[@]}"
}

# is_known_pool <pool> -> 0 if in POOL_TARGET, 1 otherwise (always 1 in single-node)
is_known_pool() {
    is_single_node && return 1
    [[ -n "${POOL_TARGET[$1]:-}" ]]
}
