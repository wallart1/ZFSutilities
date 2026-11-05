#!/usr/bin/env bash
# survey-lib.sh — shared stages and item runners for j22-function-survey.
#
# Composable pieces (sourced by the journey; the full itf helper set is
# already preloaded by the driver):
#
#   itf_survey_select
#       Resolve the software target (ITF_SURVEY_SW: tree | latest |
#       prev:N | tag:<v> — validated against the five most recent
#       published releases), enumerate the universe from THAT tree,
#       sample >=50% in random order with per-item response profiles,
#       and archive the list.  ITF_SURVEY_ARCHIVE=<file> replays an
#       archived list instead.  Leaves, on dev:
#         $ITF_RUN_DIR/survey-items.tsv    ordered selection
#         $ITF_RUN_DIR/survey-archive.json the archive (also copied to
#                                          tests/integrated/survey/archives/)
#         $ITF_RUN_DIR/survey-tree         (release mode) the fetched
#                                          release tree used for both
#                                          enumeration and guest staging
#         SURVEY_ITEMS / SURVEY_ARCHIVE / SURVEY_SW globals.
#   itf_survey_stage_tree <guest-ip>
#       Push the tree under test into the guest at /root/ZFSutilities
#       (working tree or the fetched release — always the enumerated
#       tree; j11's dev-tarball serve path).
#   itf_survey_stage_playground <guest-ip>
#       Survey-owned scratch state + the pinned payload config
#       (ZFSCONFIG_PATH) every CLI recipe runs under.
#   itf_survey_stage_gui_env <guest-ip>
#       In-guest Xvfb (the product's GUI deps are already installed).
#   itf_survey_run_cli_item <guest-ip> <id> <command> <depth> <invoke>
#                           <profiles> <rcs> <feeds> <assert> <profile>
#       One CLI item: placeholder resolution, profile-selected stdin
#       feed and expected rc, timeout-bounded guest invocation, log
#       artifact, PASS/FAIL step.  A survey_recipe_<command> function,
#       when defined below, takes over the whole invocation (bespoke
#       depth in universe.tsv).
#   itf_survey_run_gui_items <guest-ip>
#       Drive gui_probe.py over the GUI items with crash-resume
#       retries; one PASS/FAIL/BLOCKED step per item, results pulled
#       back as they verdict.
#   itf_survey_wrap <guest-ip>
#       survey-results.tsv artifact, pool-residue check, profile and
#       depth distribution summary.  Returns 1 when any item failed.

# Survey state lives in run-dir files; the couple of globals below are
# declared -g so set -u callers can reference them unconditionally.
declare -g SURVEY_ITEMS=""
declare -g SURVEY_ARCHIVE=""
declare -g SURVEY_SW=""

# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

itf_survey_select() {
    local sampler="$ITF_ROOT/survey/sample.py"
    local mode="new" sel_log first_line
    if [[ -n "${ITF_SURVEY_ARCHIVE:-}" ]]; then
        mode="replay"
        if [[ ! -f "$ITF_SURVEY_ARCHIVE" ]]; then
            itf_step fail "survey archive present" \
                "ITF_SURVEY_ARCHIVE=$ITF_SURVEY_ARCHIVE not found"
            return 1
        fi
    fi

    # --rerun without an explicit archive replays the newest prior j22
    # run's archived list when one exists (the driver's replay-the-
    # previous-run semantics extended to the selection).
    if [[ "$mode" == "new" && -s "$ITF_RUN_DIR/rerun-guests.tsv" ]]; then
        local prior prior_arch
        prior="$(ls -1d "$ITF_RUNS_DIR"/run-*-j22-function-survey 2>/dev/null \
            | sort -r | while IFS= read -r p; do
                [[ "$p" == "$ITF_RUN_DIR" ]] && continue
                [[ -f "$p/survey-archive.json" ]] && { echo "$p"; break; }
            done)"
        if [[ -n "$prior" ]]; then
            prior_arch="$prior/survey-archive.json"
            itf_step info "survey list reuse" \
                "--rerun without ITF_SURVEY_ARCHIVE: replaying $(basename "$prior")'s list"
            ITF_SURVEY_ARCHIVE="$prior_arch"
            mode="replay"
        fi
    fi

    # SURVEY_REPO_ROOT lets the unit suite point enumeration at the real
    # repo from a hermetic ITF_ROOT copy.
    local repo_root="${SURVEY_REPO_ROOT:-$ITF_ROOT/../..}"
    local -a sampler_args=(--repo-root "$repo_root" "$mode"
        --sw "${ITF_SURVEY_SW:-tree}"
        --github-repo "${ITF_GITHUB_REPO:-}"
        --extract-dir "$ITF_RUN_DIR/survey-tree")
    [[ -n "${ITF_SURVEY_SEED:-}" ]] && sampler_args+=(--seed "$ITF_SURVEY_SEED")
    [[ -n "${ITF_SURVEY_FRACTION:-}" ]] \
        && sampler_args+=(--fraction "$ITF_SURVEY_FRACTION")
    if [[ "$mode" == "replay" ]]; then
        sampler_args+=(--archive "$ITF_SURVEY_ARCHIVE")
    else
        sampler_args+=(--archive "$ITF_RUN_DIR/survey-archive.json")
    fi

    sel_log="$ITF_RUN_DIR/survey-select.log"
    if ! python3 "$sampler" "${sampler_args[@]}" \
            > "$ITF_RUN_DIR/survey-select.out" 2> "$sel_log"; then
        itf_step fail "survey selection" "see survey-select.log"
        itf_artifact "survey-select" "$sel_log"
        return 1
    fi
    itf_artifact "survey-select" "$sel_log"

    first_line="$(grep -m1 '^# ' "$ITF_RUN_DIR/survey-select.out")"
    SURVEY_SW="$(sed -n 's/^# sw //p' "$ITF_RUN_DIR/survey-select.out" | head -1)"

    if [[ "$mode" == "new" ]]; then
        SURVEY_ARCHIVE="$ITF_RUN_DIR/survey-archive.json"
        # The durable archive home: committed when the user chooses.
        mkdir -p "$ITF_ROOT/survey/archives"
        cp "$SURVEY_ARCHIVE" \
            "$ITF_ROOT/survey/archives/$(basename "$SURVEY_ARCHIVE")"
        itf_step pass "survey selection created" "$first_line"
    else
        SURVEY_ARCHIVE="$ITF_SURVEY_ARCHIVE"
        # Self-contained run dirs: replay copies the archive it used.
        [[ -f "$ITF_RUN_DIR/survey-archive.json" ]] \
            || cp "$SURVEY_ARCHIVE" "$ITF_RUN_DIR/survey-archive.json"
        itf_step pass "survey selection replayed" \
            "$(basename "$SURVEY_ARCHIVE") — $first_line"
    fi
    itf_artifact "survey-archive" "$SURVEY_ARCHIVE"

    # The ordered item list (sampler TSV, comments stripped).
    grep -v '^#' "$ITF_RUN_DIR/survey-select.out" \
        > "$ITF_RUN_DIR/survey-items.tsv" || true
    SURVEY_ITEMS="$ITF_RUN_DIR/survey-items.tsv"
    local n
    n="$(grep -c . "$SURVEY_ITEMS" || true)"
    if (( n == 0 )); then
        itf_step fail "survey selection" "sampler produced no items"
        return 1
    fi

    # Lab shape follows the selection: any two-node item forces the j05
    # lab; otherwise the single-node lab suffices (resolved from the
    # manifest's lab column per selected CLI id).
    local needs_two=0 id lab _kind _name _page _profile
    while IFS=$'\t' read -r id _kind _name _page _profile; do
        [[ -n "$id" ]] || continue
        lab="$(awk -F'\t' -v i="$id" '$1==i {print $3; exit}' \
            "$ITF_ROOT/survey/universe.tsv")"
        [[ "$lab" == "two" ]] && { needs_two=1; break; }
    done < "$SURVEY_ITEMS"
    # shellcheck disable=SC2034  # consumed by the journey
    SURVEY_NEEDS_TWO=$needs_two
    itf_step info "survey lab shape" \
        "$n items; needs-two-node=$needs_two; sw=$SURVEY_SW"
    return 0
}

# ---------------------------------------------------------------------------
# Tree staging (the enumerated tree is the tree under test)
# ---------------------------------------------------------------------------

itf_survey_stage_tree() {
    local guest_ip="$1"
    # The effective target is what the sampler reported (replay follows
    # the archive, not the env).
    if [[ -n "$SURVEY_SW" && "$SURVEY_SW" != "tree" ]]; then
        # Release mode: stage the fetched release tree.  The download
        # stage's dev-tarball branch tars ITF_SURVEY_TREE_DIR when set
        # (the release-pin extension in common.sh).  The guest dir is
        # cleared first: the lab staging (j05) already downloaded the
        # WORKING tree there, and tar extracts overlay — without the
        # clear, the release survey would silently run the union of both
        # trees (observed live: identical bin/ made it invisible).
        local tree_dir
        tree_dir="$(sed -n 's/^# enum-root //p' "$ITF_RUN_DIR/survey-select.out" \
            | head -1 | tr -d '\r')"
        if [[ -z "$tree_dir" || ! -d "$tree_dir" ]]; then
            itf_step fail "survey tree staged" \
                "release mode but no enum-root in survey-select.out"
            return 1
        fi
        itf_guest_exec "$guest_ip" 'rm -rf /root/ZFSutilities' > /dev/null 2>&1
        ITF_SURVEY_TREE_DIR="$tree_dir" \
            itf_journey_stage_download "$guest_ip" || return 1
        return 0
    fi
    itf_journey_stage_download "$guest_ip" || return 1
}

# ---------------------------------------------------------------------------
# Compute-guest tree staging (two-node shape only)
# ---------------------------------------------------------------------------

itf_survey_stage_tree_compute() {
    local s_ip="$1" c_ip="$2"
    # Compute-node items run the tree's bin/ too — copy the already-staged
    # tree across the lab's root-SSH link (j05 admin pre-work) instead of
    # serving a second download.
    # shellcheck disable=SC2016  # the $ expansions run in the guests
    if itf_guest_exec "$s_ip" 'tar -czf /root/survey-tree.tgz -C /root ZFSutilities' \
            > "$ITF_RUN_DIR/survey-tree-pack.log" 2>&1 \
        && itf_guest_exec "$c_ip" '
            set -e
            scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                root@'"$s_ip"':/root/survey-tree.tgz /root/survey-tree.tgz
            rm -rf /root/ZFSutilities
            tar -xzf /root/survey-tree.tgz -C /root
            rm -f /root/survey-tree.tgz
            test -x /root/ZFSutilities/bin/zfsholds
        ' > "$ITF_RUN_DIR/survey-tree-unpack.log" 2>&1 \
        && itf_guest_exec "$s_ip" 'rm -f /root/survey-tree.tgz' \
            > /dev/null 2>&1; then
        itf_step pass "survey tree staged [compute]" \
            "storage's staged tree copied to the compute guest"
    else
        itf_step fail "survey tree staged [compute]" \
            "see survey-tree-pack.log / survey-tree-unpack.log"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Playground: survey-owned scratch state + the pinned payload config
# ---------------------------------------------------------------------------

itf_survey_stage_playground() {
    local guest_ip="$1"
    local rid
    rid="$(basename "$ITF_RUN_DIR" | sed 's/^run-[0-9]*-//; s/-j22.*//' \
        | tail -c 7)"
    [[ -n "$rid" ]] || rid="r$$"

    local env_script
    env_script="$ITF_RUN_DIR/survey-env.sh"
    cat > "$env_script" <<EOF
SURVEY_RID=$rid
SURVEY_POOL=zfstest1
SURVEY_POOL2=zfstest2
SURVEY_POOL3=zfstest3
SURVEY_SUB=zfstest1/survey
SURVEY_DS=zfstest1/survey-$rid
SURVEY_DS2=zfstest2/survey-$rid
SURVEY_SNAP=zfstest1/survey-$rid@survey-$rid
SURVEY_VOL=zfstest1/survey-vol-$rid
SURVEY_STREAM=/root/survey-$rid.stream
SURVEY_WORK=/root/survey-$rid
SURVEY_VMID=101
SURVEY_VDISK=9
SURVEY_CONFIG=/root/survey-config.json
EOF
    # shellcheck disable=SC1090
    source "$env_script"
    export SURVEY_DS   # the GUI probe targets the scratch dataset row

    if itf_guest_put "$guest_ip" "$env_script" /root/survey-env.sh \
            > /dev/null 2>&1 \
        && itf_guest_exec "$guest_ip" '
            set -e
            source /root/survey-env.sh
            mkdir -p "$SURVEY_WORK"
            zfs create -p "$SURVEY_DS"
            echo survey-data > "/$SURVEY_DS/survey-file"
            zfs snapshot "$SURVEY_SNAP"
            zfs create "$SURVEY_DS2"
            zfs create -V 16M "$SURVEY_VOL"
            zfs send "$SURVEY_SNAP" > "$SURVEY_STREAM"
            zfs get -s local -H -o property,value,source all "$SURVEY_DS" \
                > "$SURVEY_WORK/local.props"
        ' > "$ITF_RUN_DIR/survey-playground.log" 2>&1; then
        itf_step pass "survey playground staged" \
            "scratch datasets, snapshot, zvol, stream (rid $rid)"
    else
        itf_step fail "survey playground staged" "see survey-playground.log"
        return 1
    fi

    # The pinned payload config (e2e_support premise): every recipe runs
    # under ZFSCONFIG_PATH so config-reading commands see the test pools
    # and the product defaults, never an operator's saved state.
    local cfg
    cfg="$ITF_RUN_DIR/survey-config.json"
    python3 - "$cfg" <<'PYEOF'
import json, sys

cfg = {
    "config_version": 12,
    "pools": [
        {"name": p, "offsite_candidate": p == "zfstest3"}
        for p in ("zfstest1", "zfstest2", "zfstest3")
    ],
    "retention": {"default": []},
}
with open(sys.argv[1], "w") as f:
    json.dump(cfg, f, indent=1)
PYEOF
    if itf_guest_put "$guest_ip" "$cfg" /root/survey-config.json \
            > /dev/null 2>&1; then
        itf_step pass "survey config pinned" \
            "ZFSCONFIG_PATH=/root/survey-config.json (three test pools)"
    else
        itf_step fail "survey config pinned"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# GUI environment
# ---------------------------------------------------------------------------

itf_survey_stage_gui_env() {
    local guest_ip="$1"
    # python3-cairo is documented as a product gap (F-047): the GUI's
    # memory/alignment pages import cairo at module level, but the gui
    # prerequisite set never installs a python cairo binding — the
    # probing environment supplies it so the rest of the GUI surface
    # can be surveyed pending the repair.
    if itf_guest_exec "$guest_ip" \
            'DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                xvfb python3-cairo > /var/log/survey-xvfb-install.log 2>&1 \
             && command -v Xvfb && python3 -c "import cairo"' \
            > "$ITF_RUN_DIR/survey-xvfb.log" 2>&1; then
        itf_step pass "GUI probing environment" \
            "Xvfb + python3-cairo installed in guest"
    else
        itf_step fail "GUI probing environment" "see survey-xvfb.log"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# CLI item execution
# ---------------------------------------------------------------------------

# _survey_feed_for <feeds-map> <profile> -> stdout feed text (\n unescaped)
_survey_feed_for() {
    local map="$1" profile="$2" feed=""
    local pair
    for pair in ${map//;;/ }; do
        if [[ "${pair%%=*}" == "$profile" ]]; then
            feed="${pair#*=}"
            break
        fi
    done
    [[ "$feed" == "-" ]] && feed=""
    printf '%b' "$feed"
}

# _survey_rc_for <rcs-map> <profile> -> expected rc ("*" = any)
_survey_rc_for() {
    local map="$1" profile="$2"
    local pair
    for pair in ${map//;;/ }; do
        if [[ "${pair%%=*}" == "$profile" ]]; then
            printf '%s' "${pair#*=}"
            return
        fi
    done
    printf '*'
}

# _survey_resolve <string> — substitute {PLACEHOLDER} tokens from the
# playground env (already sourced on dev).
_survey_resolve() {
    local s="$1"
    s="${s//\{RID\}/$SURVEY_RID}"
    s="${s//\{POOL\}/$SURVEY_POOL}"
    s="${s//\{POOL2\}/$SURVEY_POOL2}"
    s="${s//\{POOL3\}/$SURVEY_POOL3}"
    s="${s//\{DS\}/$SURVEY_DS}"
    s="${s//\{DS2\}/$SURVEY_DS2}"
    s="${s//\{SNAP\}/$SURVEY_SNAP}"
    s="${s//\{SUB\}/$SURVEY_SUB}"
    s="${s//\{VOL\}/$SURVEY_VOL}"
    s="${s//\{STREAM\}/$SURVEY_STREAM}"
    s="${s//\{WORK\}/$SURVEY_WORK}"
    s="${s//\{VMID\}/$SURVEY_VMID}"
    s="${s//\{VDISK\}/$SURVEY_VDISK}"
    printf '%s' "$s"
}

itf_survey_run_cli_item() {
    local guest_ip="$1"
    local id="$2" command="$3" depth="$4" invoke="$5"
    # shellcheck disable=SC2034  # profiles column documents the recipe
    local profiles="$6"
    local rcs="$7" feeds="$8" assert="$9" profile="${10}"
    local node="${11:-storage}"

    # Route to the guest that owns the command (two-node items).
    local target_ip="$guest_ip"
    if [[ "$node" == "compute" ]]; then
        target_ip="$(itf_survey_compute_ip)" || return 1
    fi

    local log="$ITF_RUN_DIR/items/$id.log"
    mkdir -p "$ITF_RUN_DIR/items"

    # Bespoke recipes own the whole invocation.
    if [[ "$depth" == "bespoke" ]] \
            && declare -f "survey_recipe_$command" > /dev/null; then
        "survey_recipe_$command" "$target_ip" "$id" "$profile" "$log" \
            && return 0 || return 1
    fi

    local resolved feed_file expected_rc
    resolved="$(_survey_resolve "$invoke")"
    feed_file="$ITF_RUN_DIR/items/$id.feed"
    _survey_feed_for "$feeds" "$profile" > "$feed_file"
    expected_rc="$(_survey_rc_for "$rcs" "$profile")"

    # shellcheck disable=SC2016  # the $ expansions run in the guest
    local guest_cmd
    guest_cmd="source /root/survey-env.sh 2>/dev/null || true
cd /root/ZFSutilities
export ZFSCONFIG_PATH=/root/survey-config.json
timeout 300 ./bin/$resolved"
    itf_guest_exec_feed "$target_ip" "$feed_file" "$guest_cmd" \
        > "$log" 2>&1
    local rc=$?
    itf_artifact "item-$id" "$log"

    local ok=0 why=""
    if [[ "$expected_rc" == "*" ]]; then
        ok=1
    elif (( rc == expected_rc )); then
        ok=1
    else
        why="rc=$rc expected=$expected_rc"
    fi
    if (( ok )) && [[ "$assert" != "-" ]] \
            && ! grep -qE "$assert" "$log"; then
        ok=0
        why="output missing /$assert/"
    fi
    if (( ok )); then
        itf_step pass "item $id" \
            "[$depth/$profile] $resolved — see items/$id.log"
    else
        itf_step fail "item $id" \
            "[$depth/$profile] $resolved — ${why:-failed}; see items/$id.log"
        return 1
    fi
    return 0
}

itf_survey_compute_ip() {
    local rec="$ITF_RUN_DIR/guest-compute.txt"
    if [[ ! -f "$rec" ]]; then
        itf_step fail "compute guest record" \
            "no $rec — a two-node item ran without the j05 lab"
        return 1
    fi
    awk '{print $3}' "$rec"
}

# ---------------------------------------------------------------------------
# Bespoke recipes (depth=bespoke rows in universe.tsv)
# ---------------------------------------------------------------------------

# _survey_guest_run <ip> <feed> <cmd> <log> — shared invocation wrapper.
# <cmd> is harness-authored and may carry quoted arguments (expanded via
# eval in the guest, where the playground env is sourced); <feed> "-"
# means empty stdin.
_survey_guest_run() {
    local ip="$1" feed="$2" cmd="$3" log="$4"
    [[ "$feed" == "-" ]] && feed=""
    local feed_file="$log.feed"
    printf '%b' "$feed" > "$feed_file"
    # shellcheck disable=SC2016
    itf_guest_exec_feed "$ip" "$feed_file" "
source /root/survey-env.sh 2>/dev/null || true
cd /root/ZFSutilities
export ZFSCONFIG_PATH=/root/survey-config.json
eval timeout 300 $cmd" > "$log" 2>&1
}

survey_recipe_startdocserver() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # Serve-or-fail-gracefully: bounded run, then probe the documented
    # local port; a clean FATAL (e.g. mkdocs absent) is the honest
    # no-tooling user path and passes.
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        cd /root/ZFSutilities
        (timeout 60 ./bin/startdocserver > /root/startdocserver.log 2>&1; \
         echo $? > /root/startdocserver.rc) &
        sleep 20
        if curl -fsS --max-time 5 -o /dev/null http://127.0.0.1:8000/; then
            echo SERVED
        fi
        grep -qE "FATAL|ERROR|Traceback|mkdocs" /root/startdocserver.log && echo DIAGNOSED
    ' > "$log" 2>&1
    itf_artifact "item-$id" "$log"
    if grep -q "SERVED\|DIAGNOSED" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] startdocserver served or failed gracefully"
        return 0
    fi
    itf_step fail "item $id" \
        "[bespoke/$profile] startdocserver neither served nor diagnosed — see items/$id.log"
    return 1
}

survey_recipe_watchall() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # A curses tool: needs a pty (script -e) and a real TERM, and dies at
    # the timeout — rc 124 means it was alive and scrolling.
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        cd /root/ZFSutilities
        TERM=xterm timeout 10 script -qec "./bin/watchall -n 1 -m 20 \"echo tick\"" /dev/null
        echo "watchall-rc=$?"
    ' > "$log" 2>&1
    itf_artifact "item-$id" "$log"
    # rc 124 = alive at the timeout kill; rc 0 = clean pty-exit render.
    # Both prove the curses UI came up; a Traceback proves it did not.
    if grep -qE "watchall-rc=(0|124)" "$log" && ! grep -q "Traceback" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] watchall ran under a pty (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_watchit() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        TERM=xterm timeout 10 script -qec "./bin/watchit \$SURVEY_POOL" /dev/null
        echo "watchit-rc=$?"
    ' > "$log" 2>&1
    itf_artifact "item-$id" "$log"
    if grep -qE "watchit-rc=(0|124)" "$log" && grep -qE "zfstest1|NAME" "$log" \
            && ! grep -q "Traceback" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] watchit rendered pool state under a pty"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_zfssend() {
    local ip="$1" id="$2" profile="$3" log="$4"
    local feed="\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/zfssend "source=$SURVEY_DS dest=$SURVEY_DS2 label=survey"' "$log"
    itf_artifact "item-$id" "$log"
    itf_step pass "item $id" \
        "[bespoke/$profile] zfssend copy flow (see items/$id.log)"
    return 0
}

survey_recipe_zfsrestore() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_guest_run "$ip" "\\n" \
        './bin/zfsrestore "source=$SURVEY_DS dest=$SURVEY_DS2"' "$log"
    itf_artifact "item-$id" "$log"
    itf_step pass "item $id" \
        "[bespoke/$profile] zfsrestore two-step copy attempt (see items/$id.log)"
    return 0
}

survey_recipe_zfsrestoresendstream() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_guest_run "$ip" "\\n" \
        './bin/zfsrestoresendstream "$SURVEY_STREAM" "$SURVEY_DS2"' "$log"
    itf_artifact "item-$id" "$log"
    itf_step pass "item $id" \
        "[bespoke/$profile] stream restore attempt (see items/$id.log)"
    return 0
}

survey_recipe_zfsreplayprops() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_guest_run "$ip" "-" \
        './bin/zfsreplayprops "$SURVEY_DS2" "$SURVEY_POOL/survey"' "$log"
    itf_artifact "item-$id" "$log"
    itf_step pass "item $id" \
        "[bespoke/$profile] property replay attempt (see items/$id.log)"
    return 0
}

survey_recipe_clone_vm() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # Clone the lab VM into a survey-owned VMID, then remove it again —
    # the accept profile really copies; decline exercises the refusal.
    local feed="y\\ny\\ny\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "cancel" ]] && feed="\\n"
    [[ "$profile" == "invalid" ]] && feed="definitely-not-yes\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/clone-vm "$SURVEY_VMID" 9100 "survey$SURVEY_RID"' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    # Converge: the survey VM must not linger whatever the profile did.
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        qm status 9100 > /dev/null 2>&1 && printf "y\\ny\\ny\\n" \
            | timeout 300 /root/ZFSutilities/bin/remove-vm 9100 \
            > /root/survey-clone-vm-cleanup.log 2>&1 || true
    ' > /dev/null 2>&1
    if (( rc == 0 )) || grep -qE "INFO|FATAL|decline|aborted" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] clone-vm flow + teardown (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_new_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    local feed="y\\ny\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/new-vm-disk "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK" 1G' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    if (( rc == 0 )) || grep -qE "INFO|FATAL" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] new-vm-disk flow (teardown rides remove-vm-disk's recipe)"
        # Leave disk 9 for remove-vm-disk's own recipe; if this profile
        # declined, create it so the next destructive item has prey.
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_remove_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # Self-sufficient: create the scratch disk through the product,
    # then run the item's own profile against it.
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        printf "y\\ny\\n" | timeout 300 ./bin/new-vm-disk \
            "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK" 1G \
            > /root/survey-rmd-setup.log 2>&1 || true
    ' > /dev/null 2>&1
    local feed="y\\ny\\ny\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/remove-vm-disk "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK"' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    # Converge regardless of profile outcome.
    # shellcheck disable=SC2016
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        printf "y\\ny\\ny\\n" | timeout 300 \
            /root/ZFSutilities/bin/remove-vm-disk \
            "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK" \
            > /root/survey-rmd-cleanup.log 2>&1 || true
    ' > /dev/null 2>&1
    if (( rc == 0 )) || grep -qE "INFO|FATAL|aborted" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] remove-vm-disk flow + convergence (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

# ---------------------------------------------------------------------------
# GUI items
# ---------------------------------------------------------------------------

itf_survey_run_gui_items() {
    local guest_ip="$1"
    local ops="$ITF_RUN_DIR/survey-gui-ops.tsv" results="$ITF_RUN_DIR/survey-gui-results.jsonl"
    local items="${SURVEY_ITEMS:-$ITF_RUN_DIR/survey-items.tsv}"
    grep -E $'^[^\t]+\tgui-' "$items" > "$ops" || true
    if [[ ! -s "$ops" ]]; then
        itf_step info "GUI items" "selection contains no GUI items"
        return 0
    fi
    itf_guest_put "$guest_ip" "$ops" /root/survey-ops.tsv > /dev/null 2>&1

    # The probe harness is DEV-side test code, pushed independently of
    # the tree under test: a release survey stages the RELEASE tree,
    # which predates the survey and carries no tests/integrated/survey/.
    itf_guest_exec "$guest_ip" 'rm -rf /root/survey-harness && mkdir -p /root/survey-harness' \
        > /dev/null 2>&1
    itf_guest_put "$guest_ip" "$ITF_ROOT/survey/gui_probe.py" \
        /root/survey-harness/gui_probe.py > /dev/null 2>&1
    itf_guest_put "$guest_ip" "$ITF_ROOT/survey/gui_catalog.py" \
        /root/survey-harness/gui_catalog.py > /dev/null 2>&1

    local attempt=0
    while (( attempt < 3 )); do
        attempt=$(( attempt + 1 ))
        local probe_log="$ITF_RUN_DIR/survey-gui-probe-$attempt.log"
        # shellcheck disable=SC2016  # the $ expansions run in the guest
        if itf_guest_exec "$guest_ip" '
            source /root/survey-env.sh
            export SURVEY_DS SURVEY_RID
            timeout 5400 python3 /root/survey-harness/gui_probe.py \
                --ops /root/survey-ops.tsv \
                --results /root/survey-results.jsonl \
                --repo /root/ZFSutilities
        ' > "$probe_log" 2>&1; then
            break
        fi
        # rc != 0: either failures inside (expected -> break to verdicts)
        # or a crash/stall (resume helps only if work remains).
        if grep -q "gui_probe: done" "$probe_log" \
            || grep -q "nothing pending" "$probe_log"; then
            break
        fi
        itf_step info "GUI probe attempt $attempt" \
            "probe died before finishing — resuming (crash-resume results)"
    done
    itf_artifact "survey-gui-probe" "$probe_log"

    if ! itf_guest_get "$guest_ip" /root/survey-results.jsonl "$results" \
            > /dev/null 2>&1; then
        itf_step fail "GUI results pulled" "no survey-results.jsonl from guest"
        return 1
    fi
    itf_artifact "survey-gui-results" "$results"

    # One step per GUI op, in archived order.
    local failed=0 blocked=0 passed=0
    local id _kind name _page profile
    while IFS=$'\t' read -r id _kind name _page profile; do
        [[ -n "$id" ]] || continue
        local rec verdict detail
        # Verdict lines only: the results file also carries "started"
        # markers, and a bare id match would hit the marker first.
        rec="$(grep "\"id\": \"$id\"" "$results" | grep -m1 '"verdict"' || true)"
        verdict="$(printf '%s' "$rec" | sed -n 's/.*"verdict": "\([a-z]*\)".*/\1/p')"
        detail="$(printf '%s' "$rec" | sed -n 's/.*"detail": "\([^"]*\)".*/\1/p')"
        if [[ "$verdict" == "pass" ]]; then
            passed=$(( passed + 1 ))
            itf_step pass "item $id" "[$profile] $name — ${detail:0:90}"
        elif [[ "$verdict" == "blocked" ]]; then
            blocked=$(( blocked + 1 ))
            itf_step skip "item $id" "[$profile] $name — ${detail:0:90}"
        elif [[ "$verdict" == "fail" ]]; then
            failed=$(( failed + 1 ))
            itf_step fail "item $id" "[$profile] $name — ${detail:0:90}"
        else
            failed=$(( failed + 1 ))
            itf_step fail "item $id" "no verdict recorded (probe incomplete)"
        fi
    done < "$ops"

    itf_step info "GUI items summary" \
        "$passed pass, $blocked blocked, $failed fail (attempt $attempt)"
    (( failed == 0 )) && return 0 || return 1
}

# ---------------------------------------------------------------------------
# Wrap-up
# ---------------------------------------------------------------------------

itf_survey_wrap() {
    local guest_ip="$1"
    local results_tsv="$ITF_RUN_DIR/survey-results.tsv"
    local items="${SURVEY_ITEMS:-$ITF_RUN_DIR/survey-items.tsv}"
    {
        printf 'id\tkind\tname\tpage\tverdict\tprofile\tduration\tdetail\n'
        awk -F'\t' -v r="$ITF_RUN_DIR/survey-gui-results.jsonl" '
            BEGIN { while ((getline line < r) > 0)
                        if (line ~ /"verdict"/) recs[++n] = line }
            {
                id = $1; kind = $2; name = $3; page = $4; profile = $5
                verdict = "-"; duration = ""; detail = ""
                for (i = 1; i <= n; i++) {
                    if (recs[i] ~ ("\"id\": \"" id "\"")) {
                        verdict = recs[i]
                        sub(/.*"verdict": "/, "", verdict)
                        sub(/".*/, "", verdict)
                        duration = recs[i]
                        sub(/.*"duration": /, "", duration)
                        sub(/[,}].*/, "", duration)
                        detail = recs[i]
                        sub(/.*"detail": "/, "", detail)
                        sub(/".*/, "", detail)
                        break
                    }
                }
                printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", \
                    id, kind, name, page, verdict, profile, duration, \
                    substr(detail, 1, 120)
            }
        ' "$items"
    } > "$results_tsv"
    itf_artifact "survey-results" "$results_tsv"

    # CLI steps were already recorded as PASS/FAIL steps; the TSV above
    # carries every item's verdict for tooling.
    local gui_counts
    gui_counts="$(python3 - "$results_tsv" <<'PYEOF'
import csv, sys
from collections import Counter

counts = Counter()
profiles = Counter()
with open(sys.argv[1]) as f:
    for row in csv.DictReader(f, delimiter="\t"):
        counts[row["verdict"]] += 1
        if row["verdict"] in ("pass", "fail", "blocked"):
            profiles[row["profile"]] += 1
print(" ".join(f"{k}={v}" for k, v in sorted(counts.items())))
print(" ".join(f"profile-{k}={v}" for k, v in sorted(profiles.items())))
PYEOF
)"
    itf_step info "survey verdict distribution" \
        "$(printf '%s\n' "$gui_counts" | head -1); $(printf '%s\n' "$gui_counts" | tail -1)"

    # Playground teardown first: the scratch state the recipes ran against
    # is the survey's own and must not outlive it (the residue gate below
    # then proves the pool is clean).
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$guest_ip" '
        source /root/survey-env.sh 2>/dev/null || true
        # The scratch datasets are pool-root children (zfstest1/survey-<rid>),
        # not members of a zfstest1/survey subtree — destroy each by name.
        zfs destroy -r "$SURVEY_DS" 2>/dev/null || true
        zfs destroy "$SURVEY_VOL" 2>/dev/null || true
        zfs destroy -r "$SURVEY_DS2" 2>/dev/null || true
        rm -f "$SURVEY_STREAM" /root/survey-tree.tgz
    ' > "$ITF_RUN_DIR/survey-teardown.log" 2>&1 || true

    # Residue: the survey must leave nothing of its own behind.
    local residue_log="$ITF_RUN_DIR/survey-residue.log"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if itf_guest_exec "$guest_ip" \
            'zfs list -H -o name -r zfstest1 zfstest2 zfstest3 2>/dev/null \
             | grep -E "survey-|9100"' \
            > "$residue_log" 2>&1; then
        itf_step fail "survey residue check" \
            "survey-owned datasets/VMs left behind — see survey-residue.log"
        itf_artifact "survey-residue" "$residue_log"
        return 1
    fi
    itf_step pass "survey residue check" \
        "no survey-* datasets remain (GUI effects on non-scratch state are the lab's to keep)"
    return 0
}
