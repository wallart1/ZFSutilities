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
#   itf_survey_install_baseline <guest-ip>
#       Bare-desktop legs only (the mint profile, single-node shape):
#       first-time-user install-single-node from the staged tree, so the
#       survey starts from the same post-install point the storage leg's
#       template clone provides.
#   itf_survey_stage_playground <guest-ip>
#       Survey-owned scratch state + the pinned payload config
#       (ZFSCONFIG_PATH) every CLI recipe runs under.
#   itf_survey_stage_world <guest-ip>
#       World-variant dispatcher: stages the world the archive names
#       (ITF_SURVEY_WORLD, default thin — the playground above; lived-in
#       adds the aged, product-named snapshot ladder via the guest clock
#       walk; busy stages the same ladder and itf_survey_busy_start adds
#       the bounded background operation) and reports the variant +
#       stage elapsed time (cost visibility).
#   itf_survey_stage_gui_env <guest-ip>
#       In-guest Xvfb (the product's GUI deps are already installed).
#   itf_survey_run_cli_item <guest-ip> <id> <command> <depth> <invoke>
#                           <profiles> <rcs> <feeds> <assert> <profile>
#                           [node] [busy-mark]
#       One CLI item: placeholder resolution, profile-selected stdin
#       feed and expected rc, timeout-bounded guest invocation, log
#       artifact, PASS/FAIL step; in busy runs a refuse-ok row may pass
#       via the clean holder-naming lock refusal.  A survey_recipe_<command> function,
#       when defined below, takes over the whole invocation (bespoke
#       depth in universe.tsv).
#   itf_survey_run_gui_items <guest-ip>
#       Drive gui_probe.py over the GUI items with crash-resume
#       retries; one PASS/FAIL/BLOCKED step per item, results pulled
#       back as they verdict.
#   itf_survey_wrap <guest-ip>
#       survey-results.tsv artifact, pool-residue check, profile and
#       depth distribution summary.  Returns 1 when any item failed.

# Survey state lives in run-dir files; the few globals below are
# declared -g so set -u callers can reference them unconditionally.
declare -g SURVEY_ITEMS=""
declare -g SURVEY_ARCHIVE=""
declare -g SURVEY_SW=""
declare -g SURVEY_WORLD=""
declare -g SURVEY_WORLD_SEED=""
declare -g SURVEY_WORLD_ANCHOR=""

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
        --world "${ITF_SURVEY_WORLD:-thin}"
        --github-repo "${ITF_GITHUB_REPO:-}"
        --extract-dir "$ITF_RUN_DIR/survey-tree")
    [[ -n "${ITF_SURVEY_SEED:-}" ]] && sampler_args+=(--seed "$ITF_SURVEY_SEED")
    [[ -n "${ITF_SURVEY_FRACTION:-}" ]] \
        && sampler_args+=(--fraction "$ITF_SURVEY_FRACTION")
    [[ -n "${ITF_SURVEY_WORLD_SEED:-}" ]] \
        && sampler_args+=(--world-seed "$ITF_SURVEY_WORLD_SEED")
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
    SURVEY_WORLD="$(sed -n 's/^# world //p' "$ITF_RUN_DIR/survey-select.out" | head -1)"
    SURVEY_WORLD_SEED="$(sed -n 's/^# world-seed //p' \
        "$ITF_RUN_DIR/survey-select.out" | head -1)"
    SURVEY_WORLD_ANCHOR="$(sed -n 's/^# world-anchor //p' \
        "$ITF_RUN_DIR/survey-select.out" | head -1)"
    # The sampler always prints the world line; a missing one is the same
    # missing-world-is-thin rule the archive loader applies.
    [[ -n "$SURVEY_WORLD" ]] || SURVEY_WORLD=thin

    # Early fence: the closed variant list, refused before any lab is
    # cloned (the sampler validates the name too — this catches a typo
    # minutes earlier than the world stage would).
    case "$SURVEY_WORLD" in
        thin|lived-in|busy) ;;
        *)
            itf_step fail "survey world variant" \
                "world '$SURVEY_WORLD' is not a known variant (thin | lived-in | busy)"
            return 1
            ;;
    esac

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

    # World digest guard: recompute the digest from the (variant, seed,
    # anchor) the sampler reported and compare with the archived one.
    # A fresh run self-checks; a replay proves the current planner can
    # still rebuild the recorded world — a mismatch means planner drift,
    # and the run refuses rather than surveying a different world than
    # the archive names.  Pre-world archives (no digest field) replay as
    # thin, whose staging has no planner to drift.
    local digest_arch digest_now
    digest_arch="$(python3 - "$SURVEY_ARCHIVE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    print(json.load(f).get("world", {}).get("digest", ""))
PYEOF
    )" || digest_arch=""
    if [[ -n "$digest_arch" ]]; then
        if [[ -z "$SURVEY_WORLD_SEED" ]]; then
            itf_step fail "survey world digest" \
                "archive carries a world digest but the selection reported no world seed"
            return 1
        fi
        local -a digest_args=(--variant "$SURVEY_WORLD" --seed "$SURVEY_WORLD_SEED")
        [[ -n "$SURVEY_WORLD_ANCHOR" ]] \
            && digest_args+=(--anchor "$SURVEY_WORLD_ANCHOR")
        digest_now="$(python3 "$ITF_ROOT/survey/world.py" digest \
            "${digest_args[@]}" 2>/dev/null || true)"
        if [[ "$digest_now" != "$digest_arch" ]]; then
            itf_step fail "survey world digest" \
                "archived $digest_arch != planner's $digest_now — planner drift; \
stage a new run instead of replaying this archive"
            return 1
        fi
        itf_step pass "survey world digest" \
            "world=$SURVEY_WORLD digest=$digest_arch (planner match)"
    fi

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
        "$n items; needs-two-node=$needs_two; sw=$SURVEY_SW; world=$SURVEY_WORLD"
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
    itf_step_start "survey tree staging [compute]" "tar + cross-guest scp + extract"
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
# Baseline install (bare-desktop legs — the mint profile, single-node
# shape; the two-node lab installs via install-two-node itself)
# ---------------------------------------------------------------------------

itf_survey_install_baseline() {
    local guest_ip="$1"
    itf_step_start "survey baseline install" \
        "first-time-user install-single-node onto the bare desktop"
    # The fresh-system sequence from j01's install stage (common.sh),
    # minus the download: the tree under test is already staged by
    # itf_survey_stage_tree, and this baseline carries no installed
    # product to verify first (the mint template has none by design).
    local pre_log="$ITF_RUN_DIR/survey-prereq.log"
    if itf_guest_exec "$guest_ip" \
            "/root/ZFSutilities/bin/check-prerequisites --single-node" \
            > "$pre_log" 2>&1; then
        itf_step fail "prereq check (fresh desktop)" \
            "unexpectedly reported all-present"
    else
        itf_step pass "prereq check (fresh desktop)" \
            "reports the missing items a user must handle"
        itf_artifact "survey-prereq" "$pre_log"
    fi
    itf_journey_run_installer "$guest_ip" 'y\ny\n\n\n' \
        "install-single-node completes" || return 1
    itf_journey_verify_installed "$guest_ip"
    return 0
}

# ---------------------------------------------------------------------------
# Playground: survey-owned scratch state + the pinned payload config
# ---------------------------------------------------------------------------

# _survey_config_version — the pinned payload config must carry the
# enumerated tree's schema version.  A stale constant silently re-runs the
# migration chain (or mislabels seeded rows written in the current
# schema), so the version is read from the tree the sampler enumerated —
# working tree or fetched release.  Step-free by design: callers run this
# inside $( ), where an itf_step would vanish with the subshell; the
# caller validates the (numeric) output and owns the failure step.
_survey_config_version() {
    local enum_root out
    enum_root="$(sed -n 's/^# enum-root //p' "$ITF_RUN_DIR/survey-select.out" \
        2>/dev/null | head -1 | tr -d '\r')"
    if [[ -z "$enum_root" || ! -d "$enum_root/python" ]]; then
        echo "survey config version: no enumerated tree in survey-select.out" >&2
        return 1
    fi
    out="$(python3 - "$enum_root" <<'PYEOF'
import sys

sys.path.insert(0, sys.argv[1] + "/python")
from config_migrations import CONFIG_VERSION

print(CONFIG_VERSION)
PYEOF
    )" || out=""
    if [[ ! "$out" =~ ^[0-9]+$ ]]; then
        echo "survey config version: no CONFIG_VERSION under $enum_root/python" >&2
        return 1
    fi
    printf '%s' "$out"
}

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
# Survey-owned state dir: schedule profiles (and any other runtime state
# the product writes) stay inside the run's footprint — the same
# no-operator-state premise as the pinned config, and the teardown
# deletes it wholesale.  Every reader honors this env (paths.py).
export ZFSUTILITIES_STATE_DIR=/root/survey-state
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
    # and the product defaults, never an operator's saved state.  The
    # schema version comes from the enumerated tree — never a constant.
    local cfg cfgver
    cfgver="$(_survey_config_version)" || true
    if [[ ! "$cfgver" =~ ^[0-9]+$ ]]; then
        itf_step fail "survey config version" \
            "could not pin the tree's CONFIG_VERSION (select must run first; \
the enum tree needs python/config_migrations.py)"
        return 1
    fi
    cfg="$ITF_RUN_DIR/survey-config.json"
    python3 - "$cfg" "$cfgver" <<'PYEOF'
import json, sys

cfg = {
    "config_version": int(sys.argv[2]),
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
            "ZFSCONFIG_PATH=/root/survey-config.json (three test pools, schema v$cfgver)"
    else
        itf_step fail "survey config pinned"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Lived-in world (playground + the aged snapshot ladder)
# ---------------------------------------------------------------------------

itf_survey_stage_lived_in() {
    local guest_ip="$1"
    # The thin playground first: every CLI recipe's {DS}/{SNAP}/{STREAM}
    # prey and the pinned config are variant-independent.
    itf_survey_stage_playground "$guest_ip" || return 1

    # The plan is a pure function of (variant, seed, anchor); the anchor
    # comes from the archive via select (direct stage calls fall back to
    # reading it from the archive the same way).
    if [[ -z "$SURVEY_WORLD_ANCHOR" ]]; then
        SURVEY_WORLD_ANCHOR="$(python3 - "$SURVEY_ARCHIVE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    print(json.load(f).get("world", {}).get("anchor", ""))
PYEOF
        )"
    fi
    if [[ -z "$SURVEY_WORLD_SEED" || -z "$SURVEY_WORLD_ANCHOR" ]]; then
        itf_step fail "survey world plan" \
            "world seed/anchor unknown - select must run first \
(seed='${SURVEY_WORLD_SEED:-}' anchor='${SURVEY_WORLD_ANCHOR:-}')"
        return 1
    fi
    # busy stages this same ladder (its background operation is runtime
    # activity, not plan state), but the digest names the variant — plan
    # as whichever one the archive carries so the digest guard holds.
    local -a plan_args=(--variant "${SURVEY_WORLD:-lived-in}" --seed "$SURVEY_WORLD_SEED"
        --anchor "$SURVEY_WORLD_ANCHOR")
    local plan_json="$ITF_RUN_DIR/survey-world-plan.json"
    local ladder_raw="$ITF_RUN_DIR/survey-world-ladder.tsv"
    local ladder="$ITF_RUN_DIR/survey-world-ladder.run.tsv"
    local plan_out
    if ! plan_out="$(python3 "$ITF_ROOT/survey/world.py" plan "${plan_args[@]}" \
            --out-json "$plan_json" --out-tsv "$ladder_raw" 2>&1)"; then
        itf_step fail "survey world plan" "world.py refused: $plan_out"
        return 1
    fi
    # Defense in depth behind select's guard: the plan's digest must be
    # the archived one, or this tree stages a different world than the
    # archive names.
    local digest_arch digest_now
    digest_arch="$(python3 - "$SURVEY_ARCHIVE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    print(json.load(f).get("world", {}).get("digest", ""))
PYEOF
    )"
    digest_now="$(printf '%s\n' "$plan_out" | sed -n 's/^digest //p')"
    if [[ "$digest_now" != "$digest_arch" ]]; then
        itf_step fail "survey world plan" \
            "plan digest $digest_now != archived $digest_arch - planner drift"
        return 1
    fi
    itf_step pass "survey world plan" \
        "$(printf '%s\n' "$plan_out" | tr '\n' ' ')"

    # Render the rid-relative placeholders and push plan + interpreter.
    local recv_ds="zfstest2/survey-$SURVEY_RID-recv"
    sed -e "s|{BASE}|$SURVEY_DS|g" -e "s|{DS2BASE}|$recv_ds|g" \
        "$ladder_raw" > "$ladder"
    itf_guest_exec "$guest_ip" 'rm -rf /root/survey-harness && mkdir -p /root/survey-harness' \
        > /dev/null 2>&1
    if ! itf_guest_put "$guest_ip" "$ladder" /root/survey-world-ladder.tsv \
            > /dev/null 2>&1 \
        || ! itf_guest_put "$guest_ip" "$ITF_ROOT/survey/world-stage.sh" \
            /root/survey-harness/world-stage.sh > /dev/null 2>&1; then
        itf_step fail "survey world plan" "could not push ladder/world-stage.sh"
        return 1
    fi

    # Freeze the walk guest(s): storage always; the compute guest too in
    # two-node labs (its iSCSI fence timer must not tick against a
    # walked-back storage clock).
    local -a walk_ips=("$guest_ip")
    if [[ -f "$ITF_RUN_DIR/guest-compute.txt" ]]; then
        walk_ips+=("$(awk '{print $3}' "$ITF_RUN_DIR/guest-compute.txt")")
    fi
    if ! itf_guest_time_freeze "${walk_ips[@]}"; then
        itf_step fail "survey clock walk" "freeze failed on $(printf '%s ' "${walk_ips[@]}")"
        return 1
    fi
    local walk_rc=0
    _survey_walk_ladder "$guest_ip" "$ladder" "$recv_ds" || walk_rc=1
    # The clock ALWAYS comes back — a lab left 100 days in the past is
    # the one unrecoverable staging failure.
    if ! itf_guest_time_restore "${walk_ips[@]}"; then
        itf_step fail "survey clock restore" \
            "guest clock may be left walked on $(printf '%s ' "${walk_ips[@]}") \
- manual restore needed"
        walk_rc=1
    fi
    (( walk_rc )) && return 1

    # Verification against the plan (real clock again): every planned
    # snapshot exists with its planned creation, holds are in place, and
    # the two real zfsdailybackup runs added their product snapshots.
    local verify_log="$ITF_RUN_DIR/survey-world-verify.log"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$guest_ip" '
        source /root/survey-env.sh 2>/dev/null || true
        zfs list -Hp -t snapshot -o name,creation -s creation -r "$SURVEY_DS"
        echo "== holds =="
        zfs list -H -t snapshot -o name -r "$SURVEY_DS" | while read -r s; do
            zfs holds -H "$s" 2>/dev/null || true
        done
        echo "== recv =="
        zfs list -Hp -t snapshot -o name,creation -s creation -r "'"$recv_ds"'" 2>/dev/null || true
    ' > "$verify_log" 2>&1
    itf_artifact "survey-world-verify" "$verify_log"
    local verify_out
    if ! verify_out="$(python3 - "$plan_json" "$verify_log" "$SURVEY_DS" "$recv_ds" <<'PYEOF'
import json, sys

plan = json.load(open(sys.argv[1]))
base, recv = sys.argv[3], sys.argv[4]
names = {}
holds = set()
section = None
recv_snaps = 0
for line in open(sys.argv[2]):
    fields = line.split()
    if line.startswith("=="):
        section = line.strip()
        continue
    if section == "== holds ==" and len(fields) >= 2:
        holds.add((fields[0], fields[1]))
    elif section == "== recv ==" and len(fields) >= 2 and "@" in fields[0]:
        recv_snaps += 1
    elif not section and len(fields) >= 2 and "@" in fields[0]:
        names[fields[0]] = int(fields[1])
problems = []
# The count expectation: every planned ladder row, the snapshots the two
# product runs created on backup-src, and the playground's own snapshot
# on the base dataset (the -r listing includes the base itself).
for r in plan["ladder"]:
    full = f"{base}/{r['dataset']}@{r['name']}"
    if full not in names:
        problems.append(f"missing {full}")
    elif abs(names[full] - r["epoch"]) > 30:
        # The clock walk's landing jitter (clock set over ssh + zfssnapbuild
        # startup) can run past the original ±5s — live-observed +6s on a
        # replayed world (run-20261123-202102). Bucket/day semantics are
        # minute-scale, so the tolerance absorbs jitter, not exactness.
        problems.append(f"{full} creation {names[full]} != planned {r['epoch']}")
    if r["hold"] and (full, r["hold"]) not in holds:
        problems.append(f"hold {r['hold']} missing on {full}")
want = len(plan["ladder"]) + len(plan["dailybackup"]) + 1
if len(names) != want:
    problems.append(f"{len(names)} snapshots under base, planned {want}")
if recv_snaps < len(plan["dailybackup"]):
    problems.append(f"receive tree carries {recv_snaps} snapshots")
if problems:
    print("; ".join(problems))
    sys.exit(1)
print(f"ladder={len(plan['ladder'])} holds={sum(1 for r in plan['ladder'] if r['hold'])} "
      f"product_runs={len(plan['dailybackup'])} recv={recv_snaps}")
PYEOF
    )"; then
        itf_step fail "survey world verified" "${verify_out:-see survey-world-verify.log}"
        return 1
    fi
    itf_step pass "survey world verified" "$verify_out"

    # Teardown knowledge: the lived-in extras the wrap must release
    # (holds/clone/recv tree) beyond the playground's own destroys.
    cat >> "$ITF_RUN_DIR/survey-env.sh" <<EOF
SURVEY_RECV_DS=$recv_ds
SURVEY_CLONE_DS=$SURVEY_DS/clone-work
EOF
    # shellcheck disable=SC1090
    source "$ITF_RUN_DIR/survey-env.sh"
    itf_guest_put "$guest_ip" "$ITF_RUN_DIR/survey-env.sh" \
        /root/survey-env.sh > /dev/null 2>&1

    # Phase 3 config rows, deliberately AFTER the walk: the ladder's two
    # zfsdailybackup directive runs happen under the minimal config, so
    # the seeded steps and the directive sends never interact.
    itf_survey_stage_config_rows "$guest_ip" || return 1
    return 0
}

# ---------------------------------------------------------------------------
# Lived-in config rows (populated retention/backup/offsite config + the
# schedule profiles; the GUI pages stop rendering cold-start emptiness)
# ---------------------------------------------------------------------------

itf_survey_stage_config_rows() {
    local guest_ip="$1"
    local start=$SECONDS
    local cfgver
    cfgver="$(_survey_config_version)" || true
    if [[ ! "$cfgver" =~ ^[0-9]+$ ]]; then
        itf_step fail "survey config version" \
            "could not pin the tree's CONFIG_VERSION (select must run first; \
the enum tree needs python/config_migrations.py)"
        return 1
    fi

    # The enriched pinned config replaces the playground's minimal one
    # (same premise: config-reading surfaces see the test pools, never
    # operator state).  Rows use the schemas the GUI's own collect_*
    # functions write (backup_page/offsite_page) and the retention
    # resolution zfsconfig documents (pool -> <offsite> -> default).
    # Deterministic in the run's scratch names and deliberately OUTSIDE
    # the world digest — the digest pins the ladder plan, this staging is
    # a pure function of names the archive already implies, so replays
    # rebuild it identically and pre-Phase-3 archives stay valid.
    local cfg="$ITF_RUN_DIR/survey-config-rows.json"
    # shellcheck disable=SC2153  # SURVEY_DS2 is real (sourced survey env)
    python3 - "$cfg" "$cfgver" "$SURVEY_DS" "$SURVEY_DS2" <<'PYEOF'
import json, sys

path, cfg_version, ds, ds2 = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]


def buckets(d, w, m, s):
    return [
        {"name": "d", "retain": d, "minage": 0},
        {"name": "w", "retain": w, "minage": 0},
        {"name": "m", "retain": m, "minage": 0},
        {"name": "s", "retain": s, "minage": 65},
    ]


cfg = {
    "config_version": cfg_version,
    "pools": [
        {"name": p, "offsite_candidate": p == "zfstest3"}
        for p in ("zfstest1", "zfstest2", "zfstest3")
    ],
    # Pool-specific policies carry distinct counts so the Retention page
    # shows real non-default rows; "<offsite>" serves offsite-candidate
    # pools (zfstest3) per zfsconfig's resolution order.
    "retention": {
        "default": buckets(3, 2, 2, 4),
        "zfstest1": buckets(4, 3, 3, 6),
        "zfstest2": buckets(2, 2, 1, 3),
        "<offsite>": buckets(3, 2, 2, 4),
    },
    "backup": {
        "send_receive_steps": [
            {"active": True, "source": ds, "dest": ds2 + "-recv"},
        ],
        "pull_steps": [
            {"active": False, "source": ds, "dest": ds2 + "-pull", "excludes": []},
        ],
    },
    # Offsite includes/excludes are STRINGS here (offsite_page's own
    # storage shape; the profile runner shlex-splits them).
    "offsite": {
        "steps": [
            {
                "active": False,
                "source": ds,
                "dest": "<offsite>/survey",
                "includes": "backup-src",
                "excludes": "clone-work",
            },
        ],
    },
    # Check Against: the page's user tree is its only editable surface,
    # so one seeded user row keeps edit-cell live under any draw (an
    # empty user tree left the role nothing to commit to — live-failed
    # run-20261124-121057; port of the pub3 lane fix).
    "checkagainst": {
        "backup_derived_active": True,
        "offsite_derived_active": True,
        "backup_derived": [],
        "offsite_derived": [],
        "user_entries": [
            {
                "label": "survey-user",
                "source_root": ds + "/home",
                "dest_root": ds2,
                "comment": "survey seeded row",
            },
        ],
    },
}
with open(path, "w") as f:
    json.dump(cfg, f, indent=1)
PYEOF
    if ! itf_guest_put "$guest_ip" "$cfg" /root/survey-config.json \
            > /dev/null 2>&1; then
        itf_step fail "survey config rows staged"
        return 1
    fi

    # Schedule profiles in the survey-owned state dir (the playground env
    # already pins ZFSUTILITIES_STATE_DIR there).  profile_manager's own
    # create_profile schema; all inactive so nothing fires via cron — the
    # rows render on the Schedule page and the per-tab profile dialogs.
    # The product has no past-due schedule state (cron_manager computes
    # forward next-runs only), so variety comes from real cron shapes,
    # including the ordinal weekday form the Next-Run renderer parses.
    local pdir="$ITF_RUN_DIR/survey-state-profiles"
    rm -rf "$pdir"
    mkdir -p "$pdir"
    python3 - "$pdir" "$SURVEY_DS" "$SURVEY_DS2" "$SURVEY_WORLD_ANCHOR" <<'PYEOF'
import json, os, sys

outdir, ds, ds2, anchor = sys.argv[1:5]
created = f"{anchor}T00:00:00"


def cron(minute="0", hour="2", day="*", month="*", weekday="*", condition=""):
    return {"minute": minute, "hour": hour, "day": day,
            "month": month, "weekday": weekday, "condition": condition}


def profile(name, tab, config, cron_fields):
    return {
        "profile_name": name,
        "tab_type": tab,
        "created_at": created,
        "config": config,
        "dry_run": True,
        "cron": cron(**cron_fields),
        "active": False,
        "comment": "seeded by the j22 lived-in world",
    }


profiles = [
    profile("root-backup-survey", "backup", {
        "variables": {"label": "dailybackup"},
        "pull_steps": [],
        "pull_steps_active": True,
        "send_receive_steps": [
            {"active": True, "source": ds, "dest": ds2 + "-recv"},
        ],
        "post_steps": {"remove_snapfile": True, "run_retention": True},
    }, {"minute": "30", "hour": "1"}),
    profile("root-offsite-survey", "offsite", {
        "variables": {"includes": "backup-src", "excludes": "clone-work"},
        "steps": [
            {"active": False, "source": ds, "dest": "<offsite>/survey",
             "includes": "backup-src", "excludes": "clone-work"},
        ],
        "pause_scrubs": False,
    }, {"minute": "0", "hour": "3", "day": "1"}),
    profile("root-retention-survey", "retention", {
        "prune_label": "dailybackup",
        "prune_pools": ["zfstest1"],
    }, {"minute": "45", "hour": "2"}),
    # First Saturday of the month — the ordinal weekday form
    # (cron_manager._parse_weekday / profile_runner's runtime guard).
    profile("root-scrub-survey", "scrub", {
        "pools": ["zfstest2"],
        "simultaneous": 1,
    }, {"weekday": "6#1"}),
]
for p in profiles:
    with open(os.path.join(outdir, p["profile_name"] + ".json"), "w") as f:
        json.dump(p, f, indent=2)
PYEOF
    itf_guest_exec "$guest_ip" 'mkdir -p /root/survey-state/profiles' \
        > /dev/null 2>&1
    local f
    for f in "$pdir"/*.json; do
        [[ -e "$f" ]] || continue
        if ! itf_guest_put "$guest_ip" "$f" \
                "/root/survey-state/profiles/$(basename "$f")" > /dev/null 2>&1; then
            itf_step fail "survey schedule profiles staged" \
                "$(basename "$f") push failed"
            return 1
        fi
    done
    itf_step pass "survey config rows staged" \
        "retention default+2 pools+<offsite>, send/receive+pull steps, offsite step, \
4 inactive schedule profiles (schema v$cfgver, $(( SECONDS - start ))s)"
    return 0
}

# _survey_walk_ladder <ip> <rendered-ladder> <recv-ds> — the clock walk.
# Runs between freeze and restore; any failure bubbles up so the caller
# can still restore the clock.
_survey_walk_ladder() {
    local guest_ip="$1" ladder="$2" recv_ds="$3"
    local tree=/root/ZFSutilities
    local stage='bash /root/survey-harness/world-stage.sh'
    local tsv=/root/survey-world-ladder.tsv
    local walk_log="$ITF_RUN_DIR/survey-world-walk.log"
    : > "$walk_log"
    # zfsdailybackup's one interactive prompt (Press enter) reads this.
    local db_feed="$ITF_RUN_DIR/survey-db.feed"
    printf '\n' > "$db_feed"

    if ! itf_guest_exec "$guest_ip" "$stage tree $tree $tsv" \
            > "$ITF_RUN_DIR/survey-world-tree.log" 2>&1; then
        itf_step fail "survey world tree" "see survey-world-tree.log"
        return 1
    fi
    itf_step pass "survey world tree" "datasets, files, zvols per the plan"

    local epoch src dst
    # The walk visits every plan moment: ladder-row epochs plus the
    # dailybackup run points (their own moments, so the snapshots those
    # runs create age with the walk's later points).
    while IFS= read -r epoch; do
        [[ -n "$epoch" ]] || continue
        if ! itf_guest_time_set "$guest_ip" "$epoch"; then
            itf_step fail "survey clock walk" \
                "forward-only fence refused epoch $epoch - see survey-world-walk.log"
            return 1
        fi
        if awk -F'\t' -v e="$epoch" '$1 == e' "$ladder" | grep -q .; then
            if ! itf_guest_exec "$guest_ip" "$stage group $tree $tsv $epoch" \
                    >> "$walk_log" 2>&1; then
                itf_step fail "survey world ladder" \
                    "group at epoch $epoch failed - see survey-world-walk.log"
                return 1
            fi
        fi
        # Directive fields: '#', 'dailybackup', <epoch>, <src>, <dest>.
        while read -r _ _ _ src dst; do
            if ! itf_guest_exec_feed "$guest_ip" "$db_feed" \
                    "cd $tree && $stage dailybackup $tree $tsv $src $dst" \
                    >> "$walk_log" 2>&1; then
                itf_step fail "survey world dailybackup" \
                    "run at epoch $epoch for $src failed - see survey-world-walk.log"
                return 1
            fi
        done < <(grep -F "# dailybackup $epoch " "$ladder" || true)
        if grep -qF "# clone $epoch " "$ladder"; then
            if ! itf_guest_exec "$guest_ip" "$stage clone $tree $tsv $epoch" \
                    >> "$walk_log" 2>&1; then
                itf_step fail "survey world clone" \
                    "clone at epoch $epoch failed - see survey-world-walk.log"
                return 1
            fi
        fi
    done < <(
        {
            grep -v '^#' "$ladder" | cut -f1
            grep '^# dailybackup ' "$ladder" | awk '{print $3}'
        } | sort -n -u
    )
    itf_step pass "survey world ladder" "walk complete - see survey-world-walk.log"
    return 0
}

# ---------------------------------------------------------------------------
# World staging (variant dispatcher)
# ---------------------------------------------------------------------------

itf_survey_stage_world() {
    local guest_ip="$1"
    # The sampler reported the world in select (replay follows the
    # archive, not the env); the env fallback covers direct calls.
    local variant="${SURVEY_WORLD:-${ITF_SURVEY_WORLD:-thin}}"
    local start=$SECONDS
    case "$variant" in
        thin)
            itf_survey_stage_playground "$guest_ip" || return 1
            ;;
        lived-in)
            itf_survey_stage_lived_in "$guest_ip" || return 1
            ;;
        busy)
            # The identical staging as lived-in: the background
            # operation is launched later (itf_survey_busy_start,
            # after the GUI env) and is runtime activity, not world
            # state — the digest names the variant and the ladder is
            # the same.
            itf_survey_stage_lived_in "$guest_ip" || return 1
            ;;
        *)
            itf_step fail "survey world staged" "unknown world variant: '$variant'"
            return 1
            ;;
    esac
    # Cost visibility: the world axis is budgeted, so the report shows
    # what each variant's staging actually took.
    itf_step info "survey world staged" \
        "variant=$variant elapsed=$(( SECONDS - start ))s"
    return 0
}

# ---------------------------------------------------------------------------
# GUI environment
# ---------------------------------------------------------------------------

itf_survey_stage_gui_env() {
    local guest_ip="$1"
    itf_step_start "survey GUI env" "apt install Xvfb + python3-gi-cairo"
    # The gui prerequisite set now checks the cairo binding itself
    # (F-047 fixed): python3-gi-cairo provides BOTH the bare `import
    # cairo` (via its python3-cairo dependency) and the GI cairo bridge
    # that marshals cairo.Context in draw callbacks — a bare
    # python3-cairo install leaves every fallback-chart draw dying with
    # "Couldn't find foreign struct converter for 'cairo.Context'".  The
    # lab guest starts from a template built before the fix, so the
    # probing environment installs the pair itself (Xvfb is not a
    # product prerequisite at all).
    if itf_guest_exec "$guest_ip" \
            'DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                xvfb python3-gi-cairo > /var/log/survey-xvfb-install.log 2>&1 \
             && command -v Xvfb && python3 -c "import cairo"' \
            > "$ITF_RUN_DIR/survey-xvfb.log" 2>&1; then
        itf_step pass "GUI probing environment" \
            "Xvfb + python3-gi-cairo installed in guest"
    else
        itf_step fail "GUI probing environment" "see survey-xvfb.log"
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Busy-world background operation (busy = lived-in + one bounded real op
# running while the random actions land — the lock/EBUSY surfaces a
# sequential survey cannot reach)
# ---------------------------------------------------------------------------

# itf_survey_busy_start <guest-ip>
#
# Launches the bounded background operation on the storage guest: a real
# zfsdailybackup run redirected at the survey's scratch pair through the
# product's own overrides mechanism (the world stage's mode_dailybackup
# shape) — source backup-src, a FRESH receive tree so the send is full
# and therefore paceable, and transfer_rate_limit riding the same
# overrides string so lib/pace_stream.py stretches the window to
# seconds-to-a-minute scale.  Fallback when the backup cannot hold: a
# scrub of zfstest2 (IO load without dataset locks).  The op runs under
# setsid in its own session (j12's detached-launch pattern) so teardown
# can signal the whole process group; pid/mode land in guest-side files
# the teardown reads back.
itf_survey_busy_start() {
    local guest_ip="$1"
    local rate="${ITF_SURVEY_BUSY_RATE:-32k}"
    local busy_dest="${SURVEY_DS2}-busy"

    # Teardown knowledge (the wrap also destroys the tree).
    cat >> "$ITF_RUN_DIR/survey-env.sh" <<EOF
SURVEY_BUSY_DEST=$busy_dest
EOF
    itf_guest_put "$guest_ip" "$ITF_RUN_DIR/survey-env.sh" \
        /root/survey-env.sh > /dev/null 2>&1

    local overrides="pull_rocky='N';pull_tweety='N';pull_stewie='N';"
    overrides+="backup_threeamigos_proxmox='N';backup_NVME1='N';prune='N';"
    overrides+="sourcefs='$SURVEY_DS/backup-src';destfs='$busy_dest';"
    overrides+="transfer_rate_limit='$rate';send-receive"
    local launcher="$ITF_RUN_DIR/survey-busy-start.sh"
    cat > "$launcher" <<EOF
#!/bin/bash
# itf j22 busy world (generated): launch the bounded background op.
set -u
printf '\n' > /root/survey-busy.feed
cd /root/ZFSutilities
# zfssnapbuild's nextsnap-reuse prompt would eat the feed newline.
rm -f /run/zfsutilities/nextsnap_* 2>/dev/null || true
setsid ./bin/zfsdailybackup "${overrides}" \\
    < /root/survey-busy.feed > /root/survey-busy.log 2>&1 &
echo \$! > /root/survey-busy.pid
echo backup > /root/survey-busy.mode
exit 0
EOF
    if ! itf_guest_put "$guest_ip" "$launcher" /root/survey-busy-start.sh \
            > /dev/null 2>&1 \
        || ! itf_guest_exec "$guest_ip" 'bash /root/survey-busy-start.sh'; then
        itf_step fail "survey busy op start" "could not launch background backup"
        return 1
    fi

    # Bounded liveness verify: alive after 5 s = running; gone but the
    # log shows real work = finished fast (a short window, still a real
    # op); gone with no work markers = launch failed -> scrub fallback.
    local probe
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    probe="$(itf_guest_exec "$guest_ip" '
        sleep 5
        pid=$(cat /root/survey-busy.pid 2>/dev/null || echo 0)
        if kill -0 "$pid" 2>/dev/null; then
            echo running
        elif grep -qE "New snapshot|zfs send|completed" \
                /root/survey-busy.log 2>/dev/null; then
            echo finished
        else
            echo failed
        fi
    ' 2>/dev/null)"
    case "$probe" in
        running)
            itf_step pass "survey busy op started" \
                "paced backup $SURVEY_DS/backup-src -> $busy_dest rate=$rate"
            ;;
        finished)
            itf_step pass "survey busy op started" \
                "backup to $busy_dest completed within the launch probe (short window)"
            ;;
        *)
            itf_step info "survey busy op fallback" \
                "background backup did not hold - starting a zfstest2 scrub instead"
            if itf_guest_exec "$guest_ip" '
                    zpool scrub zfstest2 \
                        > /root/survey-busy.log 2>&1 \
                    && echo scrub > /root/survey-busy.mode \
                    && echo 0 > /root/survey-busy.pid
                '; then
                itf_step pass "survey busy op started" \
                    "scrub of zfstest2 running as the background load"
            else
                itf_step fail "survey busy op started" \
                    "neither backup nor scrub could start - see survey-busy.log"
                return 1
            fi
            ;;
    esac
    return 0
}

# itf_survey_busy_teardown <guest-ip>
#
# Joins or kills the background operation before the wrap: the invariant
# sweep judges a quiesced system, so the op must be gone by then.  The
# preferred path is the join (bounded in-guest polling, no long sleeps);
# a timeout escalates TERM then KILL on the whole session group, and a
# leftover lock after a kill is the sweep's honest failure, never
# hand-cleaned here.  The scrub fallback stops by pool-state polling —
# scrub ioctls complete asynchronously, so the command's return says
# nothing about the pool (the scrub-pause semantics law).
itf_survey_busy_teardown() {
    local guest_ip="$1"
    local stopper="$ITF_RUN_DIR/survey-busy-stop.sh"
    cat > "$stopper" <<'EOF'
#!/bin/bash
# itf j22 busy world (generated): join/kill the background op.
set -u
mode=$(cat /root/survey-busy.mode 2>/dev/null || echo none)
case "$mode" in
    backup)
        pid=$(cat /root/survey-busy.pid 2>/dev/null || echo 0)
        for _ in $(seq 1 45); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 2
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
            for _ in $(seq 1 5); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 2
            done
            kill -0 "$pid" 2>/dev/null \
                && kill -KILL -- "-$pid" 2>/dev/null
            echo "outcome: killed (join window exceeded)"
        else
            echo "outcome: joined"
        fi
        ;;
    scrub)
        zpool scrub -s zfstest2 2>/dev/null || true
        for _ in $(seq 1 30); do
            zpool status zfstest2 2>/dev/null | grep -q 'scrub in progress' \
                || break
            sleep 2
        done
        if zpool status zfstest2 2>/dev/null | grep -q 'scrub in progress'; then
            echo "outcome: scrub stop still settling"
        else
            echo "outcome: scrub stopped"
        fi
        ;;
    *)
        echo "outcome: no busy op recorded"
        ;;
esac
EOF
    if ! itf_guest_put "$guest_ip" "$stopper" /root/survey-busy-stop.sh \
            > /dev/null 2>&1; then
        itf_step fail "survey busy op teardown" "could not push the stopper"
        return 1
    fi
    local outcome
    outcome="$(itf_guest_exec "$guest_ip" 'bash /root/survey-busy-stop.sh')" \
        || outcome="outcome: teardown ssh failed"
    itf_guest_exec "$guest_ip" \
        'cat /root/survey-busy.log 2>/dev/null || true' \
        > "$ITF_RUN_DIR/survey-busy.log" 2>/dev/null || true
    itf_artifact "survey-busy" "$ITF_RUN_DIR/survey-busy.log"
    case "$outcome" in
        "outcome: joined"|"outcome: scrub stopped"|"outcome: no busy op recorded")
            itf_step pass "survey busy op teardown" "$outcome"
            ;;
        *)
            itf_step fail "survey busy op teardown" "$outcome"
            return 1
            ;;
    esac
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

# _survey_busy_lock_refusal <log>
#
# True when the log shows the busy world's clean lock refusal — the
# zfslock_wait_or_resolve contract under a headless caller: a WARN that
# names the holder (the busy operation's own zfsdailybackup), then the
# non-interactive abort.  Any other shape (a different holder, a stale
# lock from an earlier item, a plain failure) stays false, so the
# strict verdict applies — and outside busy worlds this is always
# false.
_survey_busy_lock_refusal() {
    [[ "${SURVEY_WORLD:-}" == busy ]] || return 1
    [[ -s "$1" ]] || return 1
    grep -q "WARN: Lock conflict on '" "$1" \
        && grep -q "held by dataset=" "$1" \
        && grep -q "script='zfsdailybackup'" "$1" \
        && grep -q "non-interactive mode" "$1"
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
    # universe.tsv's busy column: refuse-ok marks the rows whose prey
    # can meet the background operation's locks (empty for older rows).
    local busy_mark="${12:--}"

    # Route to the guest that owns the command (two-node items).
    local target_ip="$guest_ip"
    if [[ "$node" == "compute" ]]; then
        target_ip="$(itf_survey_compute_ip)" || return 1
    fi

    local log="$ITF_RUN_DIR/items/$id.log"
    mkdir -p "$ITF_RUN_DIR/items"

    # Bespoke recipes own the whole invocation.  Recipe functions follow
    # bash's underscore convention (survey_recipe_<name with _>), so the
    # dash-named commands map over before the lookup — without the
    # mapping, dash commands silently fell through to the generic path
    # (invoke "-" + rcs "-" + assert "-" = a vacuous pass) while their
    # recipes never ran.
    local recipe="survey_recipe_${command//-/_}"
    if [[ "$depth" == "bespoke" ]] && declare -f "$recipe" > /dev/null; then
        itf_step_start "survey item $id" "bespoke $command [$profile]"
        "$recipe" "$target_ip" "$id" "$profile" "$log" \
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
    itf_step_start "survey item $id" "$resolved [$depth/$profile]"
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
    elif [[ "$busy_mark" == refuse-ok ]] && _survey_busy_lock_refusal "$log"; then
        # Busy-world acquire-or-refuse: the item honestly lost the zlm
        # lock to the background operation (holder named in the WARN) —
        # the product's documented contract, so it passes with the
        # refusal visible in the detail.
        itf_step pass "item $id" \
            "[$depth/$profile] $resolved — [busy-refused] lock holder named; see items/$id.log"
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

survey_recipe_zfsresume() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # invalid keeps the argument-validation surface; every other profile
    # runs the real thing: a truncated stream received with -s leaves a
    # receive_resume_token, and zfsresume validates that token (it
    # inspects; it does not complete the transfer).
    if [[ "$profile" == "invalid" ]]; then
        _survey_guest_run "$ip" "-" './bin/zfsresume' "$log"
        local rc=$?
        itf_artifact "item-$id" "$log"
        if (( rc == 8 )) \
                && grep -q "FATAL: A resumable destination dataset" "$log"; then
            itf_step pass "item $id" \
                "[bespoke/$profile] zfsresume argument validation (rc 8)"
            return 0
        fi
        itf_step fail "item $id" \
            "[bespoke/$profile] expected the no-argument FATAL; see items/$id.log"
        return 1
    fi
    # Prey: cut the playground stream and receive -s into a scratch
    # dataset, halving until the receive is genuinely partial (the token
    # property is set).  A complete receive or a too-small cut both just
    # retry smaller; exhaustion is an honest item failure.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if ! itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        res="${SURVEY_DS2}-res"
        zfs receive -A "$res" 2>/dev/null || true
        zfs destroy -r "$res" 2>/dev/null || true
        size=$(stat -c %s "$SURVEY_STREAM")
        n=$(( size * 3 / 5 ))
        while (( n >= 4096 )); do
            head -c "$n" "$SURVEY_STREAM" | zfs receive -s "$res" 2>&1 || true
            tok=$(zfs get -H -o value receive_resume_token "$res" 2>/dev/null)
            if [[ -n "$tok" && "$tok" != "-" ]]; then
                echo "resumable-at=$n"
                exit 0
            fi
            zfs receive -A "$res" 2>/dev/null || true
            zfs destroy -r "$res" 2>/dev/null || true
            n=$(( n / 2 ))
        done
        echo "no-resumable-state"
        exit 1
    ' > "$log.prey" 2>&1; then
        itf_artifact "item-$id-prey" "$log.prey"
        itf_step fail "item $id" \
            "[bespoke/$profile] could not create resumable receive state; see items/$id.log.prey"
        return 1
    fi
    itf_artifact "item-$id-prey" "$log.prey"
    _survey_guest_run "$ip" "-" './bin/zfsresume "${SURVEY_DS2}-res"' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    # Converge: abort any remaining partial receive, then destroy.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        zfs receive -A "${SURVEY_DS2}-res" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS2}-res" 2>/dev/null || true
    ' > /dev/null 2>&1
    if (( rc == 0 )) && grep -qE "seems valid|WARN: Resume token" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] zfsresume validated a real resume token (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_zfsdelallsnaps() {
    local ip="$1" id="$2" profile="$3" log="$4"
    # Self-sufficient holds+clone prey under the scratch dataset's own
    # label: an offsite-* hold and a clone dependent exercise the
    # releaseholds path and the clone-skip WARN that empty-state runs can
    # never reach.  The aged ladder (label dailybackup) is untouched.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if ! itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        zfs release offsite-survey "${SURVEY_DS}@delme" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS}/delme-clone" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS}@delme" 2>/dev/null || true
        zfs snapshot "${SURVEY_DS}@delme"
        zfs hold offsite-survey "${SURVEY_DS}@delme"
        zfs clone "${SURVEY_DS}@delme" "${SURVEY_DS}/delme-clone"
    ' > "$log.prey" 2>&1; then
        itf_artifact "item-$id-prey" "$log.prey"
        itf_step fail "item $id" \
            "[bespoke/$profile] holds+clone prey staging failed; see items/$id.log.prey"
        return 1
    fi
    itf_artifact "item-$id-prey" "$log.prey"
    local feed="\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/zfsdelallsnaps "$SURVEY_DS" delme releaseholds recursive' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    # Converge: release whatever survived (a decline leaves hold+snap),
    # then drop the clone and the snapshot.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        zfs release offsite-survey "${SURVEY_DS}@delme" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS}/delme-clone" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS}@delme" 2>/dev/null || true
    ' > /dev/null 2>&1
    # releaseholds releases the offsite-* tag, and the clone dependent
    # then skips that snapshot with a WARN (delsnap returns 1 for it, so
    # the script may legitimately exit 1 on the accept path).  Under a
    # busy world the prey sits inside the background op's lock scope,
    # so the clean refusal is an equally honest outcome.
    if grep -qE "clone dependents|INFO" "$log" && (( rc == 0 || rc == 1 )); then
        itf_step pass "item $id" \
            "[bespoke/$profile] zfsdelallsnaps releaseholds+clone flow (see items/$id.log)"
        return 0
    fi
    if _survey_busy_lock_refusal "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] zfsdelallsnaps — [busy-refused] lock holder \
named (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

# --- shared vm-disk prey/convergence (two-node rows, compute guest) ------

# _survey_vmdisk_ensure_scratch <ip> — the survey's scratch disk slot 9 on
# lab VM 101, created through the product (two-node wiring included).
# "Already exists" is as good as created; both leave prey in place.
_survey_vmdisk_ensure_scratch() {
    local ip="$1"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        printf "y\\ny\\n" | timeout 300 ./bin/new-vm-disk \
            "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK" 1G \
            > /root/survey-vmd-setup.log 2>&1 || true
    ' > /dev/null 2>&1
}

# _survey_vmdisk_ensure_vm <ip> <vmid> — an EMPTY survey VM (no disks,
# never started): instant to create and destroy, unlike a ~12-minute full
# clone.  Only used where a command genuinely needs a second VM.
_survey_vmdisk_ensure_vm() {
    local ip="$1" vmid="$2"
    # shellcheck disable=SC2016  # SURVEY_RID expands on dev
    itf_guest_exec "$ip" \
        "qm status $vmid >/dev/null 2>&1 || qm create $vmid --name survey-$SURVEY_RID \
--memory 64 > /root/survey-vmd-vm-$vmid.log 2>&1" \
        > /dev/null 2>&1
}

# _survey_vmdisk_converge <ip> — remove every scratch disk slot the
# recipes use (VM 101 slots 9/10, the moved disk on 9101) through the
# product, then drop the empty survey VM itself.
_survey_vmdisk_converge() {
    local ip="$1"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        for vm in "$SURVEY_VMID" 9101; do
            for slot in 9 10; do
                printf "y\\ny\\ny\\n" | timeout 300 ./bin/remove-vm-disk \
                    "$SURVEY_POOL" "$vm" "$slot" \
                    > "/root/survey-vmd-teardown-$vm-$slot.log" 2>&1 || true
            done
        done
        qm status 9101 >/dev/null 2>&1 && \
            qm destroy 9101 --purge > /root/survey-vmd-destroy-9101.log 2>&1 || true
    ' > /dev/null 2>&1
}

survey_recipe_attach_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_vmdisk_ensure_scratch "$ip"
    local feed="y\\ny\\n"   # Continue-anyway (running VM) + Proceed
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "cancel" ]] && feed="\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/attach-vm-disk "$SURVEY_POOL/proxmox/vm-$SURVEY_VMID-disk-$SURVEY_VDISK" '\
'"$SURVEY_VMID" "$SURVEY_VDISK"' \
        "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    _survey_vmdisk_converge "$ip"
    if (( rc == 0 )) || grep -qE "INFO|Aborted|FATAL" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] attach-vm-disk flow + convergence (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_detach_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_vmdisk_ensure_scratch "$ip"
    # Prey: the disk must be attached before it can detach — through the
    # product's own attach, prompts answered accept.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        printf "y\\ny\\n" | timeout 300 ./bin/attach-vm-disk \
            "$SURVEY_POOL/proxmox/vm-$SURVEY_VMID-disk-$SURVEY_VDISK" \
            "$SURVEY_VMID" "$SURVEY_VDISK" \
            > /root/survey-vmd-attach-prey.log 2>&1 || true
    ' > /dev/null 2>&1
    local feed="y\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "cancel" ]] && feed="\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/detach-vm-disk "$SURVEY_VMID" "$SURVEY_VDISK"' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    _survey_vmdisk_converge "$ip"
    if (( rc == 0 )) || grep -qE "INFO|Aborted|FATAL" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] detach-vm-disk flow + convergence (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_move_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_vmdisk_ensure_scratch "$ip"
    # The move walks the disk reference, so the source disk is attached
    # first (product attach, accept answers); the destination is the
    # empty survey VM.  "Both VMs must be stopped" is the script's
    # advisory WARN — the destination never started.
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$ip" '
        source /root/survey-env.sh 2>/dev/null || true
        cd /root/ZFSutilities
        printf "y\\ny\\n" | timeout 300 ./bin/attach-vm-disk \
            "$SURVEY_POOL/proxmox/vm-$SURVEY_VMID-disk-$SURVEY_VDISK" \
            "$SURVEY_VMID" "$SURVEY_VDISK" \
            > /root/survey-vmd-attach-prey.log 2>&1 || true
    ' > /dev/null 2>&1
    _survey_vmdisk_ensure_vm "$ip" 9101
    local feed="y\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "cancel" ]] && feed="\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/move-vm-disk "$SURVEY_VMID" "$SURVEY_VDISK" 9101' "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    _survey_vmdisk_converge "$ip"
    if (( rc == 0 )) || grep -qE "Disk moved|Aborted|FATAL|INFO" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] move-vm-disk flow + convergence (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_rename_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_vmdisk_ensure_scratch "$ip"
    local feed="y\\n"
    [[ "$profile" == "decline" ]] && feed="n\\n"
    [[ "$profile" == "cancel" ]] && feed="\\n"
    [[ "$profile" == "invalid" ]] && feed="zzz\\nn\\n"
    _survey_guest_run "$ip" "$feed" \
        './bin/rename-vm-disk "$SURVEY_POOL/proxmox/vm-$SURVEY_VMID-disk-$SURVEY_VDISK" '\
'"$SURVEY_POOL/proxmox/vm-$SURVEY_VMID-disk-10"' \
        "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    _survey_vmdisk_converge "$ip"
    if (( rc == 0 )) || grep -qE "renamed|Aborted|FATAL|INFO" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] rename-vm-disk flow + convergence (see items/$id.log)"
        return 0
    fi
    itf_step fail "item $id" "[bespoke/$profile] see items/$id.log"
    return 1
}

survey_recipe_resize_vm_disk() {
    local ip="$1" id="$2" profile="$3" log="$4"
    _survey_vmdisk_ensure_scratch "$ip"
    # Grow-only and promptless: the profile axis has nothing to answer.
    _survey_guest_run "$ip" "-" \
        './bin/resize-vm-disk "$SURVEY_POOL" "$SURVEY_VMID" "$SURVEY_VDISK" 2G' \
        "$log"
    local rc=$?
    itf_artifact "item-$id" "$log"
    _survey_vmdisk_converge "$ip"
    if (( rc == 0 )) || grep -qE "Zvol resized|Done|FATAL|INFO" "$log"; then
        itf_step pass "item $id" \
            "[bespoke/$profile] resize-vm-disk flow + convergence (see items/$id.log)"
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
    itf_step_start "GUI probe run" "up to 3 attempts, timeout 5400s each"
    while (( attempt < 3 )); do
        attempt=$(( attempt + 1 ))
        local probe_log="$ITF_RUN_DIR/survey-gui-probe-$attempt.log"
        # shellcheck disable=SC2016  # the $ expansions run in the guest
        if itf_guest_exec "$guest_ip" '
            source /root/survey-env.sh
            export SURVEY_DS SURVEY_RID
            # The GUI is a config-reading surface like every CLI recipe:
            # the pinned survey config (three registered test pools) is
            # what the managed-pool scope keys its rows on — the
            # installed config registers none, so without this the
            # datasets/pools pages survey an empty world.  Both override
            # names: the Python GUI reads ZFSUTILITIES_CONFIG_PATH
            # (config_core), the shell side ZFSCONFIG_PATH (installer-lib)
            # — one env, two keys.
            export ZFSCONFIG_PATH=/root/survey-config.json
            export ZFSUTILITIES_CONFIG_PATH=/root/survey-config.json
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

# _survey_invariant_sweep <guest-ip>
#
# The end-of-run oracle: cross-item damage the per-item verdicts cannot
# see.  Judged on a quiesced system (the busy op is torn down before the
# wrap) but BEFORE the playground teardown — scratch state and planned
# holds must still exist to be judged.  Runs in every variant: pools
# healthy, pinned config valid JSON, lock dir empty, no stray
# .send-*/unplanned holds on scratch, no /tmp litter, GUI results
# complete.  Planned offsite holds come from the run's world plan
# (absent in thin — there, ANY hold on scratch is a surprise).  One
# PASS/FAIL step; the problems land in the survey-invariants artifact.
_survey_invariant_sweep() {
    local guest_ip="$1"
    local inv_log="$ITF_RUN_DIR/survey-invariants.log"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    local facts
    facts="$(itf_guest_exec "$guest_ip" '
        source /root/survey-env.sh 2>/dev/null || true
        echo "== pools =="
        zpool list -H -o name,health 2>/dev/null
        echo "== config =="
        if python3 -m json.tool /root/survey-config.json > /dev/null 2>&1; then
            echo parses
        else
            echo broken
        fi
        echo "== locks =="
        ls -A /run/lock/zfsutilities/.locks 2>/dev/null || true
        echo "== holds =="
        for base in "$SURVEY_DS" "$SURVEY_DS2"; do
            zfs list -H -t snapshot -o name -r "$base" 2>/dev/null \
                | while read -r s; do
                    zfs holds -H "$s" 2>/dev/null || true
                  done
        done
        echo "== tmp =="
        ls -d /tmp/survey-* 2>/dev/null || true
    ' 2>/dev/null)" || facts=""
    local -a sweep_args=("$ITF_RUN_DIR/survey-invariants.facts"
        "$ITF_RUN_DIR/survey-world-plan.json"
        "${SURVEY_ITEMS:-$ITF_RUN_DIR/survey-items.tsv}"
        "$ITF_RUN_DIR/survey-gui-results.jsonl")
    printf '%s\n' "$facts" > "${sweep_args[0]}"
    itf_artifact "survey-invariants-facts" "${sweep_args[0]}"
    local problems
    problems="$(python3 - "${sweep_args[@]}" <<'PYEOF'
import json, os, sys

facts_path, plan_path, items_path, results_path = sys.argv[1:5]
section = None
pools, locks, holds, tmp = [], [], [], []
config_state = "missing"
for line in open(facts_path):
    line = line.rstrip("\n")
    if line.startswith("== ") and line.endswith(" =="):
        section = line[3:-3]
        continue
    if not line.strip():
        continue
    if section == "pools":
        pools.append(line.split())
    elif section == "config":
        config_state = line.strip()
    elif section == "locks":
        locks.append(line)
    elif section == "holds":
        holds.append(line.split())
    elif section == "tmp":
        tmp.append(line)

problems = []
for fields in pools:
    if len(fields) >= 2 and fields[1] != "ONLINE":
        problems.append(f"pool not ONLINE: {' '.join(fields)}")
if not pools:
    problems.append("no pools listed (zpool list empty?)")
if config_state != "parses":
    problems.append(f"pinned config JSON {config_state}")
if locks:
    problems.append(f"lock dir not empty: {' '.join(locks)}")
planned = set()
if os.path.exists(plan_path):
    with open(plan_path) as f:
        for row in json.load(f).get("ladder", []):
            if row.get("hold"):
                planned.add(row["hold"])
for fields in holds:
    if len(fields) < 2:
        continue
    if fields[1].startswith(".send-"):
        problems.append(f"stray send hold {fields[0]} {fields[1]}")
    elif fields[1] not in planned:
        problems.append(f"unexpected hold {fields[0]} {fields[1]}")
for t in tmp:
    problems.append(f"/tmp litter: {t}")

# GUI completeness: every drawn GUI item must have a verdict record
# (crash-resume retries append duplicates; any record with a verdict
# counts, resource samples do not).
gui_ids, seen = [], set()
if os.path.exists(items_path):
    for line in open(items_path):
        fields = line.rstrip("\n").split("\t")
        # Item kinds: cli | gui-button | gui-widget | gui-composite.
        if len(fields) >= 2 and fields[1].startswith("gui") and fields[0]:
            gui_ids.append(fields[0])
if os.path.exists(results_path):
    with open(results_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("verdict") and rec.get("id"):
                seen.add(rec["id"])
missing = [i for i in gui_ids if i not in seen]
if missing:
    problems.append("GUI results incomplete: " + ", ".join(missing))

print("\n".join(problems) if problems else "clean")
PYEOF
)"
    printf '%s\n' "$problems" > "$inv_log"
    itf_artifact "survey-invariants" "$inv_log"
    if [[ "$problems" != "clean" ]]; then
        itf_step fail "survey invariant sweep" \
            "$(printf '%s\n' "$problems" | head -3 | tr '\n' '; ') — see survey-invariants.log"
        return 1
    fi
    itf_step pass "survey invariant sweep" \
        "pools ONLINE, config parses, lock dir empty, holds/tmp/results clean"
    return 0
}

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

    # Depth distribution of the drawn CLI items (joined back to the
    # universe's depth column): the run report's measure of what the
    # world axis bought.  Report artifact only — these numbers never go
    # into documentation.
    local depth_counts
    depth_counts="$(awk -F'\t' '
        NR == FNR { if (!/^#/) depth[$1] = $5; next }
        /^#/ || $1 == "" { next }
        $1 ~ /^cli-/ { c[depth[$1]]++ }
        END { for (k in c) printf "%s=%d\n", (k == "" ? "unknown" : k), c[k] }
    ' "$ITF_ROOT/survey/universe.tsv" "$items" | sort | tr '\n' ' ')"
    itf_step info "survey depth distribution" "${depth_counts:-none}"

    # GUI resource envelope (report-only): the probe sampled its own
    # VmRSS/fd count at start, every N ops, and end — the GUI runs in
    # the probe's process, so growth here is a FINDINGS candidate for a
    # product leak, never a run verdict.
    local res_summary
    res_summary="$(python3 - "$ITF_RUN_DIR/survey-gui-results.jsonl" <<'PYEOF'
import json, os, sys

path = sys.argv[1]
first = last = None
if os.path.exists(path):
    with open(path) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "resources":
                if first is None:
                    first = rec
                last = rec


def kv(rec, key):
    val = rec.get(key)
    return "?" if val is None else val


def delta(key):
    a, b = first.get(key), last.get(key)
    if a is None or b is None:
        return "?"
    return f"{b - a:+d}"


if first is None:
    print("none recorded")
else:
    print(
        f"VmRSS {kv(first, 'vmrss_kb')}->{kv(last, 'vmrss_kb')} kB "
        f"({delta('vmrss_kb')}), fds {kv(first, 'fds')}->{kv(last, 'fds')} "
        f"({delta('fds')}), ops {kv(first, 'ops_done')}->{kv(last, 'ops_done')}"
    )
PYEOF
)"
    itf_step info "GUI resource envelope" "$res_summary"

    # End-of-run invariant sweep (Phase 5): the cross-item oracle, run
    # while the scratch world still exists.  Teardown and the residue
    # gate always run after it — a sweep failure fails the run but
    # never skips cleanup.
    local sweep_failed=0
    _survey_invariant_sweep "$guest_ip" || sweep_failed=1

    # Playground teardown first: the scratch state the recipes ran against
    # is the survey's own and must not outlive it (the residue gate below
    # then proves the pool is clean).
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    itf_guest_exec "$guest_ip" '
        source /root/survey-env.sh 2>/dev/null || true
        # Lived-in extras first: offsite holds and the clone block
        # zfs destroy (and the receive tree is its own scratch root).
        if [[ -n "${SURVEY_RECV_DS:-}" ]]; then
            zfs list -H -t snapshot -o name -r "$SURVEY_DS" 2>/dev/null \
                | while read -r s; do
                    zfs holds -H "$s" 2>/dev/null || true
                  done | while read -r snap tag _rest; do
                    case "$tag" in
                        offsite-*) zfs release "$tag" "$snap" 2>/dev/null || true ;;
                    esac
                  done
            zfs destroy -r "$SURVEY_CLONE_DS" 2>/dev/null || true
            zfs destroy -r "$SURVEY_RECV_DS" 2>/dev/null || true
        fi
        # The scratch datasets are pool-root children (zfstest1/survey-<rid>),
        # not members of a zfstest1/survey subtree — destroy each by name.
        # The -recv/-res siblings carry the same rid and are absent in runs
        # that never created them (harmless destroys).
        zfs destroy -r "$SURVEY_DS" 2>/dev/null || true
        zfs destroy "$SURVEY_VOL" 2>/dev/null || true
        zfs destroy -r "$SURVEY_DS2" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS2}-recv" 2>/dev/null || true
        zfs destroy -r "${SURVEY_DS2}-res" 2>/dev/null || true
        # Busy-world receive tree (absent in other variants; harmless).
        zfs destroy -r "${SURVEY_DS2}-busy" 2>/dev/null || true
        rm -f "$SURVEY_STREAM" /root/survey-tree.tgz
        # The survey-owned state dir (schedule profiles and any other
        # runtime state written under the pinned ZFSUTILITIES_STATE_DIR).
        rm -rf /root/survey-state
    ' > "$ITF_RUN_DIR/survey-teardown.log" 2>&1 || true

    # Two-node labs: every vm-disk recipe converges itself, but the wrap
    # re-runs the convergence on the compute guest so the residue gate
    # below stays a gate, not a lottery.
    if [[ -f "$ITF_RUN_DIR/guest-compute.txt" ]]; then
        local c_ip
        if c_ip="$(itf_survey_compute_ip)"; then
            _survey_vmdisk_converge "$c_ip"
        fi
    fi

    # Residue: the survey must leave nothing of its own behind.
    local residue_log="$ITF_RUN_DIR/survey-residue.log"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if itf_guest_exec "$guest_ip" \
            'zfs list -H -o name -r zfstest1 zfstest2 zfstest3 2>/dev/null \
             | grep -E "survey-|9100|9101"' \
            > "$residue_log" 2>&1; then
        itf_step fail "survey residue check" \
            "survey-owned datasets/VMs left behind — see survey-residue.log"
        itf_artifact "survey-residue" "$residue_log"
        return 1
    fi
    itf_step pass "survey residue check" \
        "no survey-* datasets remain (GUI effects on non-scratch state are the lab's to keep)"
    (( sweep_failed )) && return 1
    return 0
}
