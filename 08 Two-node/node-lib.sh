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

: "${NODE_CONF:=/etc/zfsutilities-node.conf}"

# Backward compatibility: fall back to /etc/two-node.conf if new conf doesn't exist
if [[ ! -r "$NODE_CONF" ]]; then
    if [[ -r /etc/two-node.conf ]]; then
        NODE_CONF="/etc/two-node.conf"
    else
        log_msg "FATAL: Missing $NODE_CONF"
        log_msg "FATAL:   Install via: 10 Installers/install-single-node or install-two-node"
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
            log_msg "FATAL: $NODE_CONF: $_v is empty or unset"
            exit 1
        fi
    done
    unset _v

    if ! declare -p POOL_TARGET >/dev/null 2>&1; then
        log_msg "FATAL: $NODE_CONF: POOL_TARGET associative array is not declared"
        exit 1
    fi
fi

# pool_to_target <pool> -> echoes the full IQN, returns 1 if pool unknown or single-node
pool_to_target() {
    local pool="$1"
    if is_single_node; then
        log_msg "FATAL: pool_to_target: iSCSI not available in single-node mode"
        return 1
    fi
    local short="${POOL_TARGET[$pool]:-}"
    if [[ -z "$short" ]]; then
        log_msg "FATAL: Unknown pool: $pool (not in POOL_TARGET in $NODE_CONF)"
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

# find_zfsutility_script <name>
# Locate a sibling script when running from the repo or from a deployed bin/
# directory.  Candidate directories are checked in the order listed below;
# the first existing regular file wins.
#   1. $mydir/<name>
#   2. $mydir/../<name>                      (repo subdir -> root)
#   3. $mydir/08 Two-node/<name>             (repo root -> two-node)
#   4. $mydir/../08 Two-node/<name>          (repo clone-support -> two-node)
#   5. $mydir/09 ZFS clone support/<name>    (repo root -> clone-support)
#   6. $mydir/../09 ZFS clone support/<name> (repo two-node -> clone-support)
#   7. $mydir/../lib/<name>                  (deployed bin/ -> lib/)
#   8. /usr/local/lib/<name>                 (system-wide library symlink)
# Prints the resolved path and returns 0 on success, otherwise logs a FATAL
# message and returns 1.
if [[ $(type -t find_zfsutility_script 2>/dev/null) != "function" ]]; then
    find_zfsutility_script() {
        local name="$1"
        local candidate
        for candidate in \
            "$mydir/$name" \
            "$mydir/../$name" \
            "$mydir/08 Two-node/$name" \
            "$mydir/../08 Two-node/$name" \
            "$mydir/09 ZFS clone support/$name" \
            "$mydir/../09 ZFS clone support/$name" \
            "$mydir/../lib/$name" \
            "/usr/local/lib/$name"; do
            if [[ -f "$candidate" ]]; then
                realpath "$candidate"
                return 0
            fi
        done
        log_msg "FATAL: Could not find sibling script: $name"
        return 1
    }
fi

# remote_zfsutilities_bin <host>
# SSH to root@host and resolve the active version's bin/ directory via the
# /usr/local/lib/zfsutilities/current symlink.  Prints the resolved path and
# returns 0 on success; returns 1 if the remote path cannot be resolved.
remote_zfsutilities_bin() {
    local host="$1"
    local bin_path
    bin_path=$(ssh -o ConnectTimeout=10 "root@${host}" \
        'realpath /usr/local/lib/zfsutilities/current/bin 2>/dev/null || readlink -f /usr/local/lib/zfsutilities/current/bin 2>/dev/null' 2>/dev/null)
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
