#!/usr/bin/env bash
# tests/integrated/lib/config-lib.sh
#
# Site configuration for the itf (integrated testing framework) orchestrator.
#
# The orchestrator is repo tooling that must run against arbitrary test
# environments: every environment-specific value (base hosts, VMID range,
# storage names, ISO source) lives in a site configuration file, never in
# this code.  The committed site/config.example documents every key with
# generic placeholders; the real file is tests/integrated/site/config and
# is gitignored.
#
# Usage: source this library, then call itf_config_load (optionally with an
# explicit path, or set ITF_SITE_CONFIG).  Loading is fail-closed: a missing
# or invalid file aborts with a message pointing at the example file.
#
# After a successful load the ITF_* variables are set in the current shell
# and itf_config_validate has passed.

if [[ -n "${ITF_LIB_CONFIG_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_CONFIG_LOADED=1

# Root of the integrated-testing tree (the directory containing itf).
ITF_ROOT="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"

# Abort helper for config errors (independent of any product logging).
itf_config_die() {
    echo "itf: $*" >&2
    exit 2
}

# itf_config_load [path]
#
# Sources the site config (default: $ITF_ROOT/site/config, overridable via
# ITF_SITE_CONFIG), applies neutral defaults, and validates the result.
itf_config_load() {
    local path="${1:-${ITF_SITE_CONFIG:-$ITF_ROOT/site/config}}"

    if [[ ! -f "$path" ]]; then
        itf_config_die "site configuration not found: $path
Create it from the committed example:
    cp '$ITF_ROOT/site/config.example' '$ITF_ROOT/site/config'
then edit the values for your test environment. The orchestrator refuses
to run without a site configuration (fail-closed by design)."
    fi
    # shellcheck disable=SC1090
    source "$path"

    # Neutral defaults only — anything environment-specific must come from
    # the site config itself.
    ITF_RUNS_DIR="${ITF_RUNS_DIR:-$ITF_ROOT/results}"
    ITF_CACHE_DIR="${ITF_CACHE_DIR:-$ITF_ROOT/cache}"
    ITF_HTTP_PORT="${ITF_HTTP_PORT:-8000}"
    ITF_GUEST_NET_MODEL="${ITF_GUEST_NET_MODEL:-virtio}"
    ITF_GUEST_OSTYPE="${ITF_GUEST_OSTYPE:-l26}"
    ITF_SSH_KEY="${ITF_SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"

    itf_config_validate \
        || itf_config_die "site configuration validation failed (see messages above)"
}

# itf_config_validate
#
# Checks every required key and prints all problems at once.  Returns 0 when
# the configuration is usable.
itf_config_validate() {
    local problems=0

    _itf_req_var() {
        # _itf_req_var <varname> <description>
        local val="${!1:-}"
        if [[ -z "$val" ]]; then
            echo "itf-config: missing required key $1 ($2)" >&2
            problems=1
        fi
    }
    _itf_req_num() {
        # _itf_req_num <varname> <min> <description>
        local val="${!1:-}"
        if [[ ! "$val" =~ ^[0-9]+$ ]] || (( val < $2 )); then
            echo "itf-config: $1 must be an integer >= $2 (got '${val:-empty}')" >&2
            problems=1
        fi
    }

    if [[ -z "${ITF_BASE_HOSTS[*]:-}" ]]; then
        echo "itf-config: ITF_BASE_HOSTS must name at least one base host" >&2
        problems=1
    fi

    _itf_req_var ITF_SSH_USER "SSH user on the base hosts"
    _itf_req_num ITF_VMID_FIRST 100 "first reserved VMID"
    _itf_req_num ITF_VMID_LAST 100 "last reserved VMID"
    if [[ "${ITF_VMID_FIRST:-0}" =~ ^[0-9]+$ && "${ITF_VMID_LAST:-0}" =~ ^[0-9]+$ ]] \
        && (( ITF_VMID_FIRST > ITF_VMID_LAST )); then
        echo "itf-config: ITF_VMID_FIRST must be <= ITF_VMID_LAST" >&2
        problems=1
    fi

    _itf_req_var ITF_GUEST_STORAGE "PVE storage for guest disks"
    _itf_req_var ITF_ISO_STORAGE "PVE storage for ISO images"
    if [[ -n "${ITF_GUEST_STORAGE:-}" && "${ITF_GUEST_STORAGE}" == "${ITF_ISO_STORAGE:-}" ]]; then
        echo "itf-config: ITF_GUEST_STORAGE and ITF_ISO_STORAGE must differ" >&2
        problems=1
    fi

    for var in ITF_GUEST_STORAGE ITF_ISO_STORAGE; do
        val="${!var:-}"
        if [[ -n "$val" && ! "$val" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]]; then
            echo "itf-config: $var has invalid characters: $val" >&2
            problems=1
        fi
    done

    if [[ -n "${ITF_ISO_DIR:-}" && ! "${ITF_ISO_DIR}" =~ ^/ ]]; then
        echo "itf-config: ITF_ISO_DIR must be an absolute path" >&2
        problems=1
    fi
    _itf_req_var ITF_ISO_DIR "directory backing ITF_ISO_STORAGE on the base host"
    if [[ -n "${ITF_ACTION_LOG:-}" && ! "${ITF_ACTION_LOG}" =~ ^/ ]]; then
        echo "itf-config: ITF_ACTION_LOG must be an absolute path" >&2
        problems=1
    fi
    _itf_req_var ITF_ACTION_LOG "append-only audit log on the base host"

    _itf_req_var ITF_BRIDGE "PVE bridge guests attach to"
    _itf_req_num ITF_GUEST_MEMORY_MB 1024 "guest memory in MiB"
    _itf_req_num ITF_GUEST_CORES 1 "guest vCPU count"
    _itf_req_num ITF_GUEST_SYSTEM_DISK_GB 4 "guest system disk in GiB"
    _itf_req_num ITF_GUEST_POOL_DISK_GB 0 "guest test-pool disk in GiB"

    _itf_req_var ITF_DEBIAN_ISO_URL "installer ISO download URL"
    if [[ -n "${ITF_DEBIAN_ISO_URL:-}" && ! "${ITF_DEBIAN_ISO_URL}" =~ ^https?:// ]]; then
        echo "itf-config: ITF_DEBIAN_ISO_URL must be an http(s) URL" >&2
        problems=1
    fi
    _itf_req_var ITF_ISO_NAME "ISO file name on the base host"
    if [[ -n "${ITF_ISO_NAME:-}" && ! "${ITF_ISO_NAME}" =~ ^itf- ]]; then
        echo "itf-config: ITF_ISO_NAME must start with 'itf-' (upload guard)" >&2
        problems=1
    fi

    case "${ITF_SW_SOURCE:-}" in
        release|dev-tarball) ;;
        *)
            echo "itf-config: ITF_SW_SOURCE must be 'release' or 'dev-tarball'" >&2
            problems=1
            ;;
    esac
    _itf_req_var ITF_GITHUB_REPO "GitHub owner/repo for release downloads"

    return "$problems"
}
