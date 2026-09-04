#!/usr/bin/bash
# shellcheck disable=SC2034,SC2221,SC2222
# test-lib.sh — Shared utilities and mock infrastructure for ZFS Utilities tests.
# Source this file at the top of every test-* script.

# =============================================================================
# Bootstrap: resolve repo root and load bashinit BEFORE defining mocks.
# =============================================================================

mydir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export mydir

# Point helper resolution at the repo copy instead of any deployed version.
# Individual tests can still override ZFSUTILITIES_BIN_DIR to inject mocks.
: "${ZFSUTILITIES_BIN_DIR:=$mydir/bin}"
: "${ZFSUTILITIES_CURRENT_BIN_DIR:=$mydir/bin}"
export ZFSUTILITIES_BIN_DIR ZFSUTILITIES_CURRENT_BIN_DIR

# Point bashinit's optional paths.sh bootstrap at the repo copy. Tests that
# re-source bashinit from mock helper dirs would otherwise trigger a spurious
# "Could not find sibling script: paths.sh" WARN because the mock dirs do not
# contain lib/paths.sh.
: "${PATHS_LIB:=$mydir/lib/paths.sh}"
export PATHS_LIB

# Disable the automatic Step-5 migration so tests do not touch production paths.
export ZFSUTILITIES_DISABLE_MIGRATION=1

source "$mydir/bin/bashinit"
bashinit

source "$mydir/bin/rootcheck"
rootcheck() { true; }   # Tests do not require root.

# Redirect log_msg output to a per-test log file so tests stay quiet without
# reintroducing message-level filtering. Tests that need the real log_msg
# behavior can save/restore the original function or source bashinit directly.
_TEST_LOG_FILE="/tmp/zfsutilities-test-$$.log"
: > "${_TEST_LOG_FILE}"

# Output-reduction flags set by the outer harness.
_ZFSUTILITIES_TESTS_QUIET="${ZFSUTILITIES_TESTS_QUIET:-}"
_ZFSUTILITIES_TESTS_FAILURES_ONLY="${ZFSUTILITIES_TESTS_FAILURES_ONLY:-}"

# Track the current test name so failures can still be reported with context
# when per-test output is suppressed.
_CURRENT_TEST_NAME=""
function log_msg {
    # Strip the optional --long-prefix flag so it does not appear in captured
    # test logs. Tests run with stderr redirected, so the harness keeps the
    # long file:line prefix form.
    if [[ "${1:-}" == "--long-prefix" ]]; then
        shift
    fi
    local caller_file="${BASH_SOURCE[1]}"
    local caller_line="${BASH_LINENO[0]}"
    local prefix
    if [[ -n "$caller_file" ]]; then
        prefix="$(realpath "$caller_file"):$caller_line:"
    else
        prefix="zfsutilities:"
    fi
    local _ts
    _ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${_ts}  ${prefix} $*" >> "${_TEST_LOG_FILE}" 2>/dev/null || true
}

# Return the path to the current test's redirected log file.
get_test_log_file() {
    echo "${_TEST_LOG_FILE}"
}

# Clear the current test's redirected log file.
clear_test_log_file() {
    : > "${_TEST_LOG_FILE}"
}

# =============================================================================
# Test Counters and Colors
# =============================================================================

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# =============================================================================
# Test Reporting Helpers
# =============================================================================

test_start() {
    ((TESTS_RUN++))
    _CURRENT_TEST_NAME="$1"
    _CURRENT_TEST_COUNTED=0
    _CURRENT_TEST_FAILED=0
    if [[ -z "$_ZFSUTILITIES_TESTS_QUIET" && -z "$_ZFSUTILITIES_TESTS_FAILURES_ONLY" ]]; then
        echo -n "  Test $TESTS_RUN: $1... "
    fi
}

test_pass() {
    if [[ "$_CURRENT_TEST_COUNTED" -eq 0 && "${_CURRENT_TEST_FAILED:-0}" -eq 0 ]]; then
        ((TESTS_PASSED++))
        _CURRENT_TEST_COUNTED=1
    fi
    if [[ -z "$_ZFSUTILITIES_TESTS_QUIET" && -z "$_ZFSUTILITIES_TESTS_FAILURES_ONLY" ]]; then
        echo -e "${GREEN}PASS${NC}"
    fi
}

test_fail() {
    if [[ "${_CURRENT_TEST_FAILED:-0}" -eq 0 ]]; then
        if [[ "$_CURRENT_TEST_COUNTED" -ne 0 ]]; then
            # A previous assertion already counted this test as passed; correct
            # the tally because the final result is a failure.
            ((TESTS_PASSED--))
        fi
        ((TESTS_FAILED++))
        _CURRENT_TEST_FAILED=1
        _CURRENT_TEST_COUNTED=1
    fi
    local reason="$1"
    # Failures must always be visible, even when other per-test output is
    # suppressed. Emit the full test label when the harness did not already
    # print it via test_start().
    if [[ -n "$_ZFSUTILITIES_TESTS_QUIET" || -n "$_ZFSUTILITIES_TESTS_FAILURES_ONLY" ]]; then
        echo -n "  Test $TESTS_RUN: $_CURRENT_TEST_NAME... "
    fi
    echo -e "${RED}FAIL${NC}"
    [[ -n "$reason" ]] && echo "    Reason: $reason"
}

test_skip() {
    if [[ "$_CURRENT_TEST_COUNTED" -eq 0 ]]; then
        ((TESTS_SKIPPED++))
        _CURRENT_TEST_COUNTED=1
    fi
    if [[ -z "$_ZFSUTILITIES_TESTS_QUIET" && -z "$_ZFSUTILITIES_TESTS_FAILURES_ONLY" ]]; then
        echo -e "${YELLOW}SKIP${NC}"
        [[ -n "$1" ]] && echo "    Reason: $1"
    fi
}

# =============================================================================
# Assertion Helpers
# =============================================================================

assert_equals() {
    local expected="$1" actual="$2"
    if [[ "$expected" == "$actual" ]]; then
        test_pass
    else
        test_fail "Expected '$expected', got '$actual'"
    fi
}

assert_contains() {
    local haystack="$1" needle="$2"
    if [[ "$haystack" == *"$needle"* ]]; then
        test_pass
    else
        test_fail "Expected string to contain '$needle'"
    fi
}

assert_rc() {
    local expected="$1" actual="$2"
    if [[ "$expected" -eq "$actual" ]]; then
        test_pass
    else
        test_fail "Expected rc=$expected, got rc=$actual"
    fi
}

assert_array_len() {
    local expected="$1"; shift
    local actual=("$@")
    if [[ "${#actual[@]}" -eq "$expected" ]]; then
        test_pass
    else
        test_fail "Expected array length $expected, got ${#actual[@]}"
    fi
}

# =============================================================================
# Test Environment Setup / Teardown
# =============================================================================

setup_test_env() {
    # Clean up any stale per-caller snapfiles from prior test runs belonging to us.
    # Tests set ZFSUTILITIES_RUN_NEXTSNAP_PREFIX or fall back to the new run dir.
    local prefix="${ZFSUTILITIES_RUN_NEXTSNAP_PREFIX:-/run/zfsutilities/nextsnap_}"
    rm -f "${prefix}$(basename "$0" | tr -c 'A-Za-z0-9_' '_')"
}

teardown_test_env() {
    # Propagate test_summary's return code so a failing suite still exits
    # non-zero when teardown is the last command in the test script.
    local rc=${_TEST_SUMMARY_RC:-0}
    local prefix="${ZFSUTILITIES_RUN_NEXTSNAP_PREFIX:-/run/zfsutilities/nextsnap_}"
    rm -f "${prefix}$(basename "$0" | tr -c 'A-Za-z0-9_' '_')"
    return "$rc"
}

# =============================================================================
# Mock State Variables
# =============================================================================

_mock_zfs_fs_list=""
_mock_zfs_snap_list=""
_mock_zfs_snap_list_creation=""
declare -gA _mock_zfs_props=()
declare -gA _mock_zfs_snaps=()
declare -gA _mock_zfs_datasets=()
declare -gA _mock_zfs_snap_lists=()
declare -gA _mock_zfs_guid_lists=()
declare -gA _mock_zfs_holds=()
_mock_zfs_send_size="0"
_mock_zpool_list=""
_mock_zfs_last_sequence=""  # tracks -s / -S passed to zfs list
_mock_zfs_guid_list=""
_mock_zfs_state_dir="/tmp/mock_zfs_state_$$"
mkdir -p "$_mock_zfs_state_dir"

# Date mocking
_mock_date_iso="2025-06-15T10:00-04:00"
_mock_date_dow="Sun"
_mock_date_dom="15"

# ask_yn mocking
_mock_ask_yn_rc=0

# delsnap mocking
_mock_delsnap_calls=()

# =============================================================================
# Mock Setup Helpers
# =============================================================================

mock_zfs_fs_list() {
    _mock_zfs_fs_list="$1"
}

mock_zfs_snap_list() {
    _mock_zfs_snap_list="$1"
}

mock_zfs_snap_list_creation() {
    _mock_zfs_snap_list_creation="$1"
}

mock_zfs_prop() {
    local dataset="$1" prop="$2" value="$3"
    _mock_zfs_props["$dataset:$prop"]="$value"
}

mock_zfs_snap_exists() {
    local snap="$1"
    _mock_zfs_snaps["$snap"]=1
}

mock_zfs_dataset_exists() {
    local ds="$1"
    _mock_zfs_datasets["$ds"]=1
}

mock_zfs_send_size() {
    _mock_zfs_send_size="$1"
}

mock_zfs_guid_list() {
    _mock_zfs_guid_list="$1"
}

mock_zfs_snap_list_for() {
    local dataset="$1"
    _mock_zfs_snap_lists["$dataset"]="$2"
}

mock_zfs_guid_list_for() {
    local dataset="$1"
    _mock_zfs_guid_lists["$dataset"]="$2"
}

mock_zfs_holds() {
    local snapshot="$1"
    shift
    _mock_zfs_holds["$snapshot"]="$*"
}

mock_zpool_list() {
    _mock_zpool_list="$1"
}

mock_date() {
    _mock_date_iso="$1"
    _mock_date_dow="${2:-Sun}"
    _mock_date_dom="${3:-15}"
}

mock_ask_yn() {
    _mock_ask_yn_rc="${1:-0}"
}

# =============================================================================
# Mock Command Overrides
# =============================================================================

zfs() {
    local args=("$@")
    local subcmd="$1"
    shift

    case "$subcmd" in
        list)
            local type="" outcols="" have_listing_opt=0 specific_arg=""
            local arg_idx=1
            while [[ $arg_idx -lt ${#args[@]} ]]; do
                local a="${args[$arg_idx]}"
                case "$a" in
                    -H*|-h*)
                        if [[ "$a" == *"t"* ]]; then
                            type="${args[$((arg_idx+1))]}"
                            have_listing_opt=1
                            ((arg_idx+=2))
                            continue
                        fi
                        ((arg_idx++))
                        continue
                        ;;
                    -d*|-r)
                        have_listing_opt=1
                        ((arg_idx++))
                        continue
                        ;;
                    -s)
                        have_listing_opt=1
                        _mock_zfs_last_sequence="s"
                        echo "s" > "$_mock_zfs_state_dir/sequence"
                        ((arg_idx++))
                        continue
                        ;;
                    -S)
                        have_listing_opt=1
                        _mock_zfs_last_sequence="S"
                        echo "S" > "$_mock_zfs_state_dir/sequence"
                        ((arg_idx++))
                        continue
                        ;;
                    -t)
                        type="${args[$((arg_idx+1))]}"
                        have_listing_opt=1
                        ((arg_idx+=2))
                        continue
                        ;;
                    -o)
                        outcols="${args[$((arg_idx+1))]}"
                        [[ "$outcols" == "name" ]] ||\
                        [[ "$outcols" == "name,creation" ]] && have_listing_opt=1
                        ((arg_idx+=2))
                        continue
                        ;;
                    -H)
                        ((arg_idx++))
                        continue
                        ;;
                    -*)
                        have_listing_opt=1
                        ((arg_idx++))
                        continue
                        ;;
                    *)
                        specific_arg="$a"
                        ((arg_idx++))
                        continue
                        ;;
                esac
                ((arg_idx++))
            done

            # Origin lookup (special case: -o origin, no listing opts)
            if [[ "$outcols" == "origin" && "$have_listing_opt" -eq 0 ]]; then
                local key="$specific_arg:origin"
                if [[ -n "${_mock_zfs_props[$key]+x}" ]]; then
                    echo "${_mock_zfs_props[$key]}"
                else
                    echo "-"
                fi
                return 0
            fi

            # Snapshot-specific checks
            if [[ "$type" == *"snapshot"* || "$type" == *"snap"* || "$type" == *"bookmark"* ]]; then
                # Snapshot existence check when a specific snapshot name is given
                if [[ "$specific_arg" == *"@"* ]]; then
                    if [[ -n "${_mock_zfs_snaps[$specific_arg]+x}" ]]; then
                        echo "$specific_arg"
                        return 0
                    fi
                    return 1
                fi
                if [[ "$outcols" == "name,creation" ]]; then
                    [[ -n "$_mock_zfs_snap_list_creation" ]] \
                        && echo -e "$_mock_zfs_snap_list_creation"
                elif [[ "$outcols" == "guid" ]]; then
                    if [[ -n "${_mock_zfs_guid_lists[$specific_arg]+x}" ]]; then
                        echo -e "${_mock_zfs_guid_lists[$specific_arg]}"
                    elif [[ -n "$_mock_zfs_guid_list" ]]; then
                        echo -e "$_mock_zfs_guid_list"
                    fi
                else
                    if [[ -n "${_mock_zfs_snap_lists[$specific_arg]+x}" ]]; then
                        echo -e "${_mock_zfs_snap_lists[$specific_arg]}"
                    elif [[ -n "$_mock_zfs_snap_list" ]]; then
                        echo -e "$_mock_zfs_snap_list"
                    fi
                fi
                return 0
            fi

            # Dataset existence check (no listing options)
            if [[ "$have_listing_opt" -eq 0 && -n "$specific_arg" && "$specific_arg" != -* ]]; then
                if [[ -n "${_mock_zfs_datasets[$specific_arg]+x}" ]]; then
                    echo "$specific_arg"
                    return 0
                fi
                return 1
            fi

            # General dataset listing
            [[ -n "$_mock_zfs_fs_list" ]] && echo -e "$_mock_zfs_fs_list"
            return 0
            ;;

        get)
            local prop="" dataset="" output_value_only=0
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    -H*|-p*) shift ;;
                    -o)
                        if [[ "$2" == "value" ]]; then
                            output_value_only=1
                        fi
                        shift 2
                        ;;
                    *)
                        if [[ -z "$prop" ]]; then
                            prop="$1"
                        else
                            dataset="$1"
                        fi
                        shift
                        ;;
                esac
            done
            local key="$dataset:$prop"
            local value
            if [[ -n "${_mock_zfs_props[$key]+x}" ]]; then
                value="${_mock_zfs_props[$key]}"
            else
                value="-"
            fi
            if [[ $output_value_only -eq 1 ]]; then
                echo "$value"
            else
                printf '%s\t%s\t%s\n' "$dataset" "$prop" "$value"
            fi
            return 0
            ;;

        send)
            local is_dryrun=0
            for a in "$@"; do
                [[ "$a" == "-nP" ]] && is_dryrun=1
            done
            if [[ $is_dryrun -eq 1 ]]; then
                echo "size	$_mock_zfs_send_size"
                return 0
            fi
            return 0
            ;;

        snapshot|create|destroy|receive|rollback|set)
            return 0
            ;;

        holds)
            local snapshot="${args[-1]}"
            local tags="${_mock_zfs_holds[$snapshot]:-}"
            local tag
            for tag in $tags; do
                printf '%s\t%s\t%s\n' "$snapshot" "$tag" "2025-01-01T00:00:00"
            done
            return 0
            ;;

        hold)
            local tag="${args[1]}"
            local snapshot="${args[2]}"
            local current="${_mock_zfs_holds[$snapshot]:-}"
            if [[ -n "$current" ]]; then
                _mock_zfs_holds["$snapshot"]="$current $tag"
            else
                _mock_zfs_holds["$snapshot"]="$tag"
            fi
            return 0
            ;;

        release)
            local tag="${args[1]}"
            local snapshot="${args[2]}"
            local current="${_mock_zfs_holds[$snapshot]:-}"
            local new_tags=""
            local t
            for t in $current; do
                if [[ "$t" != "$tag" ]]; then
                    new_tags="$new_tags $t"
                fi
            done
            new_tags="${new_tags# }"
            if [[ -n "$new_tags" ]]; then
                _mock_zfs_holds["$snapshot"]="$new_tags"
            else
                unset '_mock_zfs_holds[$snapshot]'
            fi
            return 0
            ;;

        *)
            return 0
            ;;
    esac
}

zpool() {
    if [[ "$1" == "list" ]]; then
        # Support both "-Ho name" and "-H -o name" forms.
        if [[ "$2" == "-Ho" && "$3" == "name" ]] || \
           [[ "$2" == "-H" && "$3" == "-o" && "$4" == "name" ]]; then
            echo -e "$_mock_zpool_list"
            return 0
        fi
    fi
    return 0
}

date() {
    if [[ "$1" == "-Iminutes" ]]; then
        echo "$_mock_date_iso"
        return 0
    fi
    if [[ "$1" == "-d" ]]; then
        shift 2
        case "$1" in
            +%a) echo "$_mock_date_dow" ;;
            +%d) echo "$_mock_date_dom" ;;
            *) command date "$@" ;;
        esac
        return 0
    fi
    command date "$@"
}

ask_yn() {
    return "$_mock_ask_yn_rc"
}

delsnap() {
    _mock_delsnap_calls+=("$1")
    return 0
}

# =============================================================================
# Retention Policy Mock
# =============================================================================

mock_retention_policy() {
    echo "bktname[0]='d'; bktretain[0]=3; minage[0]=0"
    echo "bktname[1]='w'; bktretain[1]=2; minage[1]=7"
    echo "bktname[2]='m'; bktretain[2]=2; minage[2]=30"
}

# =============================================================================
# Lock Manager Stubs (for scripts that source zfslockmanager)
# =============================================================================

zfslock_init() { true; }
zfslock_acquire() { zfslock_id="/tmp/mock_lock_$$"; return 0; }
zfslock_wait_or_resolve() { zfslock_id="/tmp/mock_lock_$$"; return 0; }
zfslock_release() { true; }
zfslock_release_all() { true; }

# =============================================================================
# VM Check Stubs
# =============================================================================

# Default Proxmox tool stubs so scripts that source VM lifecycle helpers do not
# fail their qm/pct guard during tests. Tests that need to simulate an absent
# Proxmox installation can unset these functions.
qm() { true; }
pct() { true; }

checkrunningvms() { return 2; }
printrunningvms() { true; }

# =============================================================================
# Summary Helper
# =============================================================================

test_summary() {
    echo ""
    echo "  Total:   $TESTS_RUN"
    echo -e "  Passed:  ${GREEN}$TESTS_PASSED${NC}"
    [[ $TESTS_FAILED -gt 0 ]] && echo -e "  Failed:  ${RED}$TESTS_FAILED${NC}" \
        || echo "  Failed:  0"
    [[ $TESTS_SKIPPED -gt 0 ]] && echo -e "  Skipped: ${YELLOW}$TESTS_SKIPPED${NC}" || true
    echo ""
    local rc=0
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        rc=0
    else
        echo -e "${RED}Some tests failed.${NC}"
        rc=1
    fi
    # Save the result so teardown_test_env can propagate it even when it is
    # called after test_summary.
    _TEST_SUMMARY_RC=$rc
    return $rc
}
