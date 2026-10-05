#!/usr/bin/env bash
# tests/integrated/lib/report-lib.sh
#
# Progressive run reporting for itf journeys and preflight.
#
# Every journey (and preflight) runs inside its own directory under
# ITF_RUNS_DIR (default: tests/integrated/results, gitignored):
#
#   results/run-<timestamp>-<tag>/
#       meta.txt     tag, start time, caller
#       steps.tsv    one line per step: <utc-ts> <status> <name> <detail>
#       report.md    human-readable report, written progressively
#       <artifact>   anything the journey saves alongside (logs, listings,
#                    screenshots) — record with itf_artifact
#
# Steps are PASS/FAIL/SKIP/INFO; the summary counts failures and
# itf_report_finish returns 1 when any step failed.

if [[ -n "${ITF_LIB_REPORT_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_REPORT_LOADED=1

ITF_STEPS_TOTAL=0
ITF_STEPS_PASS=0
ITF_STEPS_FAIL=0
ITF_STEPS_SKIP=0
ITF_STEPS_INFO=0

# itf_report_init <tag>
#
# Starts a run: creates the run directory and initializes the report files.
# Sets ITF_RUN_DIR for the rest of the shell.
itf_report_init() {
    local tag="${1:-run}"
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    ITF_RUN_DIR="${ITF_RUNS_DIR}/run-${stamp}-${tag}"
    mkdir -p "$ITF_RUN_DIR" || { echo "itf: cannot create run dir $ITF_RUN_DIR" >&2; return 1; }
    # Fresh counters per run: a shell that starts a second run (preflight
    # after a failed journey, tests, ...) must not inherit the first run's
    # steps.
    ITF_STEPS_TOTAL=0
    ITF_STEPS_PASS=0
    ITF_STEPS_FAIL=0
    ITF_STEPS_SKIP=0
    ITF_STEPS_INFO=0
    {
        echo "tag:      $tag"
        echo "started:  $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "caller:   ${ITF_RUN_CALLER:-interactive}"
    } > "$ITF_RUN_DIR/meta.txt"
    {
        echo "# itf run: $tag"
        echo ""
        echo "- started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    } > "$ITF_RUN_DIR/report.md"
    : > "$ITF_RUN_DIR/steps.tsv"
    echo "itf: run directory $ITF_RUN_DIR"
}

# itf_step <status> <name> [detail...]
#
# Records one step.  status: pass | fail | skip | info.
itf_step() {
    local status="$1" name="$2"
    shift 2
    local detail="${*:-}"

    if [[ -z "${ITF_RUN_DIR:-}" ]]; then
        echo "itf: itf_step called before itf_report_init (step '$name' dropped)" >&2
        return 1
    fi

    case "$status" in
        pass) ITF_STEPS_PASS=$((ITF_STEPS_PASS + 1)) ;;
        fail) ITF_STEPS_FAIL=$((ITF_STEPS_FAIL + 1)) ;;
        skip) ITF_STEPS_SKIP=$((ITF_STEPS_SKIP + 1)) ;;
        info) ITF_STEPS_INFO=$((ITF_STEPS_INFO + 1)) ;;
        *)
            echo "itf: invalid step status '$status' (step '$name' recorded as info)" >&2
            status=info
            ITF_STEPS_INFO=$((ITF_STEPS_INFO + 1))
            ;;
    esac
    ITF_STEPS_TOTAL=$((ITF_STEPS_TOTAL + 1))

    printf '%s\t%s\t%s\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$status" "$name" "$detail" \
        >> "$ITF_RUN_DIR/steps.tsv"
    {
        case "$status" in
            pass) echo "- **PASS** $name${detail:+ — $detail}" ;;
            fail) echo "- **FAIL** $name${detail:+ — $detail}" ;;
            skip) echo "- *SKIP* $name${detail:+ — $detail}" ;;
            *) echo "- INFO $name${detail:+ — $detail}" ;;
        esac
    } >> "$ITF_RUN_DIR/report.md"

    echo "[${status}] ${name}${detail:+ — $detail}"
    return 0
}

# itf_artifact <label> <file>
#
# Copies a file produced during the run into the run directory and records
# it in the report.
itf_artifact() {
    local label="$1" file="$2"
    if [[ -z "${ITF_RUN_DIR:-}" ]]; then
        echo "itf: itf_artifact called before itf_report_init" >&2
        return 1
    fi
    if [[ ! -f "$file" ]]; then
        echo "itf: artifact source missing: $file" >&2
        return 1
    fi
    local base src dst
    base="$(basename "$file")"
    src="$(readlink -f "$file" 2>/dev/null || echo "$file")"
    dst="$ITF_RUN_DIR/$base"
    if [[ "$src" != "$dst" ]]; then
        cp "$file" "$dst"
    fi
    echo "- ARTIFACT [$label] $base" >> "$ITF_RUN_DIR/report.md"
}

# itf_report_finish
#
# Writes the summary section and returns 1 if any step failed.
itf_report_finish() {
    if [[ -z "${ITF_RUN_DIR:-}" ]]; then
        echo "itf: itf_report_finish called before itf_report_init" >&2
        return 1
    fi
    {
        echo ""
        echo "## Summary"
        echo ""
        echo "- total: $ITF_STEPS_TOTAL  pass: $ITF_STEPS_PASS" \
            "  fail: $ITF_STEPS_FAIL  skip: $ITF_STEPS_SKIP  info: $ITF_STEPS_INFO"
        echo "- finished: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    } >> "$ITF_RUN_DIR/report.md"
    echo "itf: run finished: total=$ITF_STEPS_TOTAL pass=$ITF_STEPS_PASS" \
        " fail=$ITF_STEPS_FAIL skip=$ITF_STEPS_SKIP"
    (( ITF_STEPS_FAIL == 0 ))
}
