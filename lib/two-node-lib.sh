#!/usr/bin/bash
# /usr/local/lib/two-node-lib.sh
#
# Deprecated compatibility wrapper for old scripts that source
# /usr/local/lib/two-node-lib.sh.
#
# New code should source node-lib.sh directly. node-lib.sh provides the
# same helpers (pool_to_target, pool_list, is_known_pool) plus
# single-node / two-node mode awareness.

node_lib_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=node-lib.sh
source "${node_lib_dir}/node-lib.sh"
