#!/bin/bash
# upgrade-lib.sh
# Shared helpers for upgrade-zfsutilities and deploy-version: deployment
# manifests, deployed-tree change scanning, modification salvaging,
# release-tarball fetching, and deployment-target enumeration.
#
# This library is deliberately bashinit-free (pure bash + coreutils + curl)
# so the same file can be sourced locally by bin/ scripts or piped to a
# remote deployment target and executed there:
#     ssh root@host bash -s -- __scan /usr/local/lib/zfsutilities \
#         < lib/upgrade-lib.sh
# Remote driver modes are selected by a __-prefixed first argument, which
# local callers never pass.

# ------------------------------------------------------------------
# File-set rules
# ------------------------------------------------------------------
# upgrade_lib_excluded <relpath>
# Exit 0 when a deployed-tree path must be excluded from manifests and
# change scans: the built documentation site (regenerated at deploy time),
# Python bytecode, stale NFS silo files, and the manifest itself.
upgrade_lib_excluded() {
    local relpath="$1"
    local base=${relpath##*/}
    [[ "$relpath" == "docs/site" || "$relpath" == docs/site/* ]] && return 0
    [[ "$relpath" == */__pycache__/* || "$relpath" == "__pycache__" ]] && return 0
    [[ "$base" == *.pyc ]] && return 0
    [[ "$base" == .nfs* ]] && return 0
    # The manifest and its in-progress sibling (write_manifest redirects
    # into the tree before hashing starts) never record themselves.
    [[ "$base" == "MANIFEST.sha256" || "$base" == "MANIFEST.sha256.tmp" ]] \
        && return 0
    return 1
}

# upgrade_lib_deployed_path <relpath>
# Exit 0 when a repository path belongs to the deployed set
# (bin/, lib/, python/, docs/, share/, VERSION).
upgrade_lib_deployed_path() {
    local relpath="$1"
    [[ "$relpath" == bin/* || "$relpath" == lib/* || "$relpath" == python/* \
        || "$relpath" == docs/* || "$relpath" == share/* \
        || "$relpath" == "VERSION" ]]
}

# ------------------------------------------------------------------
# Hashing and manifests
# ------------------------------------------------------------------
# upgrade_lib_hash_tree <dir>
# Emit sorted "<sha256>  <relpath>" lines for every included regular file
# under <dir> (symlinks such as the GUI launcher are skipped). Paths are
# relative to <dir>.
upgrade_lib_hash_tree() {
    local dir="$1"
    [[ -d "$dir" ]] || return 1
    (
        cd "$dir" || exit 1
        local path relpath hash
        while IFS= read -r -d '' path; do
            relpath=${path#./}
            upgrade_lib_excluded "$relpath" && continue
            hash=$(sha256sum "$path") || exit 1
            hash=${hash%% *}
            printf '%s  %s\n' "$hash" "$relpath"
        done < <(find . -type f -print0 | LC_ALL=C sort -z)
    )
}

# upgrade_lib_write_manifest <version_dir>
# Write MANIFEST.sha256 recording the pristine state of a freshly
# deployed tree, so later upgrades can detect local modifications.
# Returns non-zero when hashing fails (a partial manifest is never left
# behind).
upgrade_lib_write_manifest() {
    local version_dir="$1"
    local tmp="$version_dir/MANIFEST.sha256.tmp"
    [[ -d "$version_dir" ]] || return 1
    upgrade_lib_hash_tree "$version_dir" > "$tmp" || { rm -f "$tmp"; return 1; }
    mv -f "$tmp" "$version_dir/MANIFEST.sha256"
}

# upgrade_lib_repo_hashes <extracted_release_root>
# Hash only the deployed subset of an extracted release tree, for use as
# a change-scan baseline when no manifest exists.
upgrade_lib_repo_hashes() {
    local root="$1"
    local line path
    while IFS= read -r line; do
        path=${line#*  }
        upgrade_lib_deployed_path "$path" || continue
        printf '%s\n' "$line"
    done < <(upgrade_lib_hash_tree "$root")
}

# upgrade_lib_classify <tree_hashes_file> <baseline_hashes_file>
# Compare two "<hash>  <path>" listings and emit tagged lines:
#   MOD <path>  — hash differs between baseline and tree
#   ADD <path>  — present in the tree only (locally added)
#   DEL <path>  — present in the baseline only (locally removed)
# Emission is path-sorted so reports and salvage orders are deterministic.
upgrade_lib_classify() {
    local tree_file="$1" baseline_file="$2"
    local -A thash bhash seen
    local line hash path p
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        hash=${line%% *}
        path=${line#*  }
        thash["$path"]=$hash
        seen["$path"]=tree
    done < "$tree_file"
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        hash=${line%% *}
        path=${line#*  }
        bhash["$path"]=$hash
        [[ "${seen[$path]:-}" == "tree" ]] || seen["$path"]=baseline
    done < "$baseline_file"
    while IFS= read -r p; do
        # printf emits one empty line for an empty key set; skip it.
        [[ -n "$p" ]] || continue
        if [[ "${seen[$p]}" == "tree" ]]; then
            [[ -n "${bhash[$p]:-}" ]] && [[ "${thash[$p]}" != "${bhash[$p]}" ]] \
                && printf 'MOD %s\n' "$p"
            [[ -z "${bhash[$p]:-}" ]] && printf 'ADD %s\n' "$p"
        else
            printf 'DEL %s\n' "$p"
        fi
    done < <(printf '%s\n' "${!seen[@]}" | LC_ALL=C sort)
}

# ------------------------------------------------------------------
# Version helpers
# ------------------------------------------------------------------
# upgrade_lib_active_version <version_base>
# Echo the version the "current" symlink points at, or nothing.
upgrade_lib_active_version() {
    local version_base="$1" link
    link=$(readlink "$version_base/current" 2>/dev/null || true)
    [[ -n "$link" ]] && basename "$link"
    return 0
}

# upgrade_lib_version_lt <a> <b>
# Exit 0 when version a is strictly older than version b.
upgrade_lib_version_lt() {
    [[ "$1" != "$2" ]] \
        && [[ "$(printf '%s\n%s\n' "$1" "$2" | LC_ALL=C sort -V | head -1)" == "$1" ]]
}

# ------------------------------------------------------------------
# Network fetch and extraction
# ------------------------------------------------------------------
# upgrade_lib_http_get <url> <dest_file>
# Fetch <url> into <dest_file>. Returns curl's exit status so callers can
# distinguish HTTP errors (22) from network failures.
upgrade_lib_http_get() {
    curl -fL --retry 2 -sS -o "$2" "$1"
}

# upgrade_lib_default_tarball_url <version>
# Echo the release-tarball URL for a version.
upgrade_lib_default_tarball_url() {
    local default_url="https://github.com/wallart1/ZFSutilities/archive/refs/tags/v%s.tar.gz"
    local template="${ZFSUTILITIES_TAG_TARBALL_URL:-$default_url}"
    # shellcheck disable=SC2059
    printf "$template" "$1"
}

# upgrade_lib_extract_tarball <tarball> <dest_dir>
# Extract a release tarball (single top-level directory) into <dest_dir>
# and echo the extracted root directory.
upgrade_lib_extract_tarball() {
    local tarball="$1" dest_dir="$2"
    [[ -f "$tarball" ]] || return 1
    mkdir -p "$dest_dir" || return 1
    tar -xzf "$tarball" -C "$dest_dir" || return 1
    local root
    # || true: head's early exit can SIGPIPE find under pipefail callers;
    # an empty result is rejected by the -n check below.
    root=$(find "$dest_dir" -mindepth 1 -maxdepth 1 -type d | head -1 || true)
    [[ -n "$root" ]] || return 1
    printf '%s\n' "$root"
}

# upgrade_lib_json_string <json_file> <field>
# Echo the string value of a top-level JSON field ("field": "value").
# The GitHub releases API keeps these on single lines. The grep pattern
# below matches the field's quoted key followed by ":" and everything up
# to (excluding) the next ',' or '}' — safe for the fields we read
# (tag_name, html_url, tarball_url), whose values never contain either
# character; cut's 4th '"'-delimited field is the value itself
# (""field"": ""value"" -> field 2 is the key, field 4 the value).
# Field names arrive from this file's own call sites, never user input.
# The trailing || true keeps a missing field (and head's early close under
# pipefail callers) an empty answer rather than a failure — callers treat
# empty as "fall back to the default".
upgrade_lib_json_string() {
    local file="$1" field="$2"
    grep -o "\"$field\":[^,}]*" "$file" | head -1 | cut -d'"' -f4 || true
}

# ------------------------------------------------------------------
# Deployment-target enumeration
# ------------------------------------------------------------------
# upgrade_lib_resolve_deploy_conf
# Echo the deploy-group config path — the modern location first, the
# legacy flat file as fallback — or nothing when neither exists. This is
# the exact resolution deploy-version performs, kept here so both scripts
# always enumerate the same target set. ZFSUTILITIES_LEGACY_DEPLOY_CONF
# overrides the legacy location (testing/non-standard layouts), mirroring
# the ZFSUTILITIES_LEGACY_NODE_CONF knob in paths.sh.
upgrade_lib_resolve_deploy_conf() {
    local modern="${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}/deploy.conf"
    local legacy="${ZFSUTILITIES_LEGACY_DEPLOY_CONF:-/etc/zfsutilities-deploy.conf}"
    if [[ -f "$modern" ]]; then
        printf '%s\n' "$modern"
    elif [[ -f "$legacy" ]]; then
        printf '%s\n' "$legacy"
    fi
}

# upgrade_lib_group_lines
# After the caller has sourced a deploy.conf, emit one "name<TAB>hosts"
# line per DEPLOY_GROUP_* variable, in ${!DEPLOY_GROUP_*} expansion order.
upgrade_lib_group_lines() {
    local var
    for var in "${!DEPLOY_GROUP_@}"; do
        printf '%s\t%s\n' "${var#DEPLOY_GROUP_}" "${!var}"
    done
}

# upgrade_lib_legacy_hosts
# Resolve the node configuration the way node-lib.sh does and emit three
# lines: node mode, storage host, compute host (empty where unset). The
# modern node.conf that install-two-node writes to the system config dir
# comes first; the legacy flat files are fallbacks. The conf is sourced
# inside a subshell so its variables do not leak into the caller. With no
# conf at all, deployment enumeration stays single-node (local host only).
upgrade_lib_legacy_hosts() {
    (
        NODE_MODE=""
        STORAGE_HOST=""
        COMPUTE_HOST=""
        modern_node="${ZFSUTILITIES_SYSTEM_CONFIG_DIR:-/etc/zfsutilities}/node.conf"
        legacy_node="${ZFSUTILITIES_LEGACY_NODE_CONF:-/etc/zfsutilities-node.conf}"
        legacy_two_node="${ZFSUTILITIES_LEGACY_TWO_NODE_CONF:-/etc/two-node.conf}"
        conf=""
        if [[ -f "$modern_node" ]]; then
            conf="$modern_node"
        elif [[ -f "$legacy_node" ]]; then
            conf="$legacy_node"
        elif [[ -f "$legacy_two_node" ]]; then
            conf="$legacy_two_node"
        fi
        if [[ -n "$conf" ]]; then
            # shellcheck source=/dev/null
            source "$conf"
            # Backward compat: configs without NODE_MODE are legacy
            # two-node configs (node-lib.sh semantics).
            : "${NODE_MODE:=two-node}"
        else
            NODE_MODE="single-node"
        fi
        printf '%s\n%s\n%s\n' "$NODE_MODE" "$STORAGE_HOST" "$COMPUTE_HOST"
    )
}

# ------------------------------------------------------------------
# SSH control-socket sharing
# ------------------------------------------------------------------
# upgrade_lib_ssh_control_path <host> <pid>
# Echo the ssh ControlPath deploy-version uses for <host>. When
# ZFSUTILITIES_SSH_CONTROL_PATH is set it is a printf template (%s =
# host) owned by the caller — upgrade-zfsutilities exports one so every
# connection in an upgrade, deploy-version's sync included, multiplexes
# through a single master (one password prompt per host). The default
# reproduces deploy-version's historical per-invocation socket.
upgrade_lib_ssh_control_path() {
    if [[ -n "${ZFSUTILITIES_SSH_CONTROL_PATH:-}" ]]; then
        # shellcheck disable=SC2059
        printf "${ZFSUTILITIES_SSH_CONTROL_PATH}" "$1"
    else
        printf '/tmp/.deploy-version-ssh-%s-%s' "$1" "$2"
    fi
}

# ------------------------------------------------------------------
# Remote driver
# ------------------------------------------------------------------
# upgrade_lib_scan_output <version_base>
# Emit the machine-readable scan of a host's deployed installation:
#   ACTIVE <version> | ACTIVE NONE
#   MANIFEST-ABSENT                  (when no manifest exists)
#   MLINE <manifest line>            (one per manifest line, otherwise)
#   FILE <sha256>  <relpath>         (one per file in the active tree)
#   END
upgrade_lib_scan_output() {
    local version_base="$1"
    local active dir
    active=$(upgrade_lib_active_version "$version_base")
    printf 'ACTIVE %s\n' "${active:-NONE}"
    dir="$version_base/versions/$active"
    if [[ -n "$active" && -f "$dir/MANIFEST.sha256" ]]; then
        sed 's/^/MLINE /' "$dir/MANIFEST.sha256"
    else
        printf 'MANIFEST-ABSENT\n'
    fi
    if [[ -n "$active" ]]; then
        upgrade_lib_hash_tree "$dir" | sed 's/^/FILE /'
    fi
    printf 'END\n'
}

# upgrade_lib_salvage_files <version_base> <old_version> <timestamp> <new_version> <relpath...>
# Archive the listed files from versions/<old_version>/ into
# salvaged-changes/<old_version>/<timestamp>/, preserving relative paths
# and file attributes, and write a provenance README. Echoes
# "SALVAGED <count>".
upgrade_lib_salvage_files() {
    local version_base="$1" old_version="$2" ts="$3" new_version="$4"
    shift 4
    local dest="$version_base/salvaged-changes/$old_version/$ts"
    local relpath count=0
    mkdir -p "$dest" || return 1
    for relpath in "$@"; do
        [[ -n "$relpath" ]] || continue
        [[ -f "$version_base/versions/$old_version/$relpath" ]] || continue
        mkdir -p "$dest/$(dirname "$relpath")"
        cp -a -- "$version_base/versions/$old_version/$relpath" \
            "$dest/$relpath" || return 1
        ((++count))
    done
    {
        echo "Local modifications salvaged by upgrade-zfsutilities"
        echo "=================================================="
        echo "Host:            $(hostname -s 2>/dev/null || echo unknown)"
        echo "Salvaged from:   active version $old_version"
        echo "Superseded by:   version $new_version"
        echo "Salvaged at:     $ts UTC"
        echo "Files preserved: $count"
        echo
        echo "These files were changed or added on this host after the"
        echo "original installation. They were archived before the upgrade"
        echo "replaced the active tree, so they no longer take effect."
        echo "Re-apply any change you still want to the new version's files"
        echo "(or to the repository), then re-deploy."
    } > "$dest/README.txt"
    printf 'SALVAGED %s\n' "$count"
}

# upgrade_lib_remote_driver <mode> <version_base> [args...]
# Entry point executed on a remote target over ssh. Modes:
#   __scan   <version_base>
#   __salvage <version_base> <old_version> <timestamp> <new_version> <relpath...>
upgrade_lib_remote_driver() {
    local mode="$1"
    shift
    local version_base="$1"
    shift
    case "$mode" in
        __scan)
            upgrade_lib_scan_output "$version_base"
            ;;
        __salvage)
            upgrade_lib_salvage_files "$version_base" "$@"
            ;;
    esac
}

# Entry guard: run the remote driver when this file is executed rather
# than sourced — directly, or piped over ssh as "bash -s -- __scan ...".
# Sourcing never passes a __-prefixed first argument, and the BASH_SOURCE
# check keeps a stray argument from firing the driver in a sourced call.
if [[ "${1:-}" == __* ]] \
    && { [[ -z "${BASH_SOURCE[0]:-}" ]] || [[ "${BASH_SOURCE[0]}" == "${0}" ]]; }; then
    upgrade_lib_remote_driver "$@"
    exit $?
fi
