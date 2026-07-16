# /usr/local/lib/two-node-lib.sh
#
# Helper library for the scripts in 08 Two-node/ and 09 ZFS clone support/.
# Sourced as the very first non-comment line in every two-node script.
#
# Sourcing this file:
#   1. Loads /etc/two-node.conf (the site config), failing clearly if missing.
#   2. Defines pool_to_target / pool_list / is_known_pool helpers so scripts
#      do not have to know the layout of $POOL_TARGET.
#
# After this file has been sourced, the following are available to the caller:
#
#   STORAGE_HOST      short hostname of the storage / iSCSI target host
#   COMPUTE_HOST      short hostname of the Proxmox / iSCSI initiator host
#   STORAGE_IP        iSCSI portal IP on the storage network
#   IQN_PREFIX        iSCSI target IQN prefix (everything before ":<short>")
#   POOL_TARGET       associative array: pool name -> target short name
#
#   pool_to_target <pool>   echoes the full IQN, returns 1 if pool unknown
#   pool_list               echoes valid pool names, one per line
#   is_known_pool <pool>    returns 0 if pool is in POOL_TARGET, 1 otherwise

: "${TWO_NODE_CONF:=/etc/two-node.conf}"

if [[ ! -r "$TWO_NODE_CONF" ]]; then
    echo "✗ Missing $TWO_NODE_CONF" >&2
    echo "  Install via: 10 Installers/install-two-node (run on the storage host as root)" >&2
    exit 1
fi

# shellcheck source=/etc/two-node.conf
source "$TWO_NODE_CONF"

# Sanity-check the variables the conf is required to define. Missing values
# here mean the conf has been hand-edited into an inconsistent state.
for _v in STORAGE_HOST COMPUTE_HOST STORAGE_IP IQN_PREFIX; do
    if [[ -z "${!_v:-}" ]]; then
        echo "✗ $TWO_NODE_CONF: $_v is empty or unset" >&2
        exit 1
    fi
done
unset _v

if ! declare -p POOL_TARGET >/dev/null 2>&1; then
    echo "✗ $TWO_NODE_CONF: POOL_TARGET associative array is not declared" >&2
    exit 1
fi

# pool_to_target <pool> -> echoes the full IQN, returns 1 if pool unknown
pool_to_target() {
    local pool="$1"
    local short="${POOL_TARGET[$pool]:-}"
    if [[ -z "$short" ]]; then
        echo "✗ Unknown pool: $pool (not in POOL_TARGET in $TWO_NODE_CONF)" >&2
        return 1
    fi
    echo "${IQN_PREFIX}:${short}"
}

# pool_list -> echoes valid pool names, one per line
pool_list() {
    printf '%s\n' "${!POOL_TARGET[@]}"
}

# is_known_pool <pool> -> 0 if in POOL_TARGET, 1 otherwise
is_known_pool() {
    [[ -n "${POOL_TARGET[$1]:-}" ]]
}
