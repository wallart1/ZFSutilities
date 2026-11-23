#!/usr/bin/env bash
# world-stage.sh — guest-side staging for the j22 lived-in world.
#
# Interprets the ladder TSV world.py emitted (survey-lib.sh renders the
# {BASE}/{DS2BASE} placeholders to the run's scratch names before
# pushing it — no tokens remain in the file this reads).  The dev side
# owns the clock (guest-lib's itf_guest_time_set) and the orchestration;
# this script owns the product mechanics: the dataset tree, snapshots
# named through the staged tree's own zfssnapbuild (derivation and
# reservation bookkeeping are the product's, not a reimplementation),
# the clone step, and the two real zfsdailybackup runs.
#
# Usage (run in the guest as root, tree = the staged /root/ZFSutilities):
#   world-stage.sh tree       <tree> <tsv>
#   world-stage.sh group      <tree> <tsv> <epoch>
#   world-stage.sh clone      <tree> <tsv> <epoch>
#   world-stage.sh dailybackup <tree> <src> <dest>
set -euo pipefail

cmd="${1:?usage: world-stage.sh tree|group|clone|dailybackup ...}"
tree="${2:?tree root required}"
tsv="${3:?ladder tsv required}"

# The product's own sourcing path (the sequence every product CLI uses),
# with one deliberate difference: zfssnapbuild comes from the staged
# tree's bin/ directly, NOT via source_helper — the helper resolver
# prefers the installed deployment, and the survey's software under test
# is the staged tree (observed live: the resolver reached the baseline
# install's 0.118.0 zfssnapbuild, whose unset-bucket read dies under
# this script's set -u).  The c-bucket name comes from zfsclone-vm's
# construction, built on the same snapname_timestamp helper.
# shellcheck source=/root/ZFSutilities/bin/bashinit
# shellcheck disable=SC1091
source "$tree/bin/bashinit"
bashinit
# shellcheck source=/root/ZFSutilities/bin/zfssnapbuild
# shellcheck disable=SC1091
source "$tree/bin/zfssnapbuild"

# The planned-name assert: zfssnapbuild derives the bucket from the
# (already walked) clock exactly as production does; a mismatch means
# the plan and the product disagree and the run must stop, not stage a
# misnamed snapshot.  Returns nonzero; the caller runs under set -e, so
# the refusal aborts the staging run.
_assert_name() {
    local ds="$1" planned="$2" built="$3"
    if [[ "$built" != "$planned" ]]; then
        echo "world-stage: $ds planned $planned but the product built $built" >&2
        return 1
    fi
}

mode_tree() {
    local _ name kind volsize
    # Datasets come parent-first (the plan's list order).
    while IFS=' ' read -r _ _ name kind volsize; do
        [[ -n "$name" ]] || continue
        if [[ "$kind" == "zvol" ]]; then
            zfs create -V "${volsize:-16M}" "$name"
        else
            zfs create -p "$name"
        fi
    done < <(grep '^# dataset ' "$tsv")
    local _ds path bytes
    while IFS=' ' read -r _ _ _ds path bytes; do
        [[ -n "$_ds" ]] || continue
        mkdir -p "/${_ds}/$(dirname "$path")"
        dd if=/dev/urandom of="/${_ds}/${path}" bs="$bytes" count=1 status=none
    done < <(grep '^# file ' "$tsv")
}

mode_group() {
    local epoch="$4"
    local _e ds rlabel rbucket hold planned built
    # The plan's row variables deliberately avoid zfssnapbuild's own
    # `label`/`bucket` globals so the derivation always runs.
    while IFS=$'\t' read -r _e ds rlabel rbucket hold planned; do
        if [[ "$rbucket" == "c" ]]; then
            built="clone-$(snapname_timestamp)-c"
        else
            built="$(zfssnapbuild "$rlabel")"
            built="${built#@}"   # zfssnapbuild echoes the @-prefixed form
            # Without this, the next call would find the nextsnap file
            # and prompt for reuse (zfssnapbuild's interactive path).
            removesnapfile
        fi
        _assert_name "$ds" "$planned" "$built"
        zfs snapshot "${ds}@${built}"
        if [[ "$hold" != "-" && -n "$hold" ]]; then
            zfs hold "$hold" "${ds}@${built}"
        fi
        echo "staged ${ds}@${built} hold=${hold:-none}"
    done < <(awk -F'\t' -v e="$epoch" '$1 == e' "$tsv")
}

mode_clone() {
    local epoch="$4"
    # The c-bucket row at this epoch names the origin; the directive
    # line names the clone target.
    local row target
    row="$(awk -F'\t' -v e="$epoch" '$1 == e && $4 == "c" {print $2 "@" $6}' "$tsv")"
    if [[ -z "$row" ]]; then
        echo "world-stage: no c-bucket row at epoch $epoch" >&2
        exit 1
    fi
    target="$(awk -v e="$epoch" \
        '$1 == "#" && $2 == "clone" && $3 == e {print $5; exit}' "$tsv")"
    if [[ -z "$target" ]]; then
        echo "world-stage: no clone directive at epoch $epoch" >&2
        exit 1
    fi
    zfs clone "$row" "$target"
    echo "cloned $row -> $target"
}

mode_dailybackup() {
    local src="$4" dest="$5"
    # A real run of the product's orchestrator, redirected at the
    # survey's scratch datasets through the product's own overrides
    # mechanism: the site pulls and prune are off, and send-receive (a
    # plain function call inside the eval'd override string) ships the
    # source to the scratch receive tree under the name zfssnapbuild
    # just built at the walked clock.  The trailing read -rp gets its
    # newline on stdin.
    cd "$tree"
    printf '\n' | ./bin/zfsdailybackup \
        "pull_rocky='N';pull_tweety='N';pull_stewie='N';backup_threeamigos_proxmox='N';backup_NVME1='N';prune='N';sourcefs='${src}';destfs='${dest}';send-receive"
}

case "$cmd" in
    tree) mode_tree ;;
    group) mode_group "$@" ;;
    clone) mode_clone "$@" ;;
    dailybackup) mode_dailybackup "$@" ;;
    *) echo "world-stage: unknown mode '$cmd'" >&2; exit 2 ;;
esac
