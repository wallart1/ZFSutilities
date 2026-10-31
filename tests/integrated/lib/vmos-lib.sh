#!/usr/bin/env bash
# tests/integrated/lib/vmos-lib.sh
#
# VM-OS disk image for the recovery-scenario journeys (campaign G0): a
# minimal bootable Debian that gets dd-ed onto product-created zvols, so
# a workload VM boots from its iSCSI LUN and answers `qm guest exec`.
#
# The image is built ONCE from the same machinery every journey already
# trusts — the cached Debian netinst ISO, the standard preseed (which
# installs qemu-guest-agent), and the serial-console install driver — so
# it boots in this exact lab topology by construction.  No external
# image source, no cloud-init, no qcow2 handling.
#
# Artifact shape under ITF_CACHE_DIR:
#   itf-vmos.raw.gz   gzip'd raw dump of the build guest's system disk
#   itf-vmos.stamp    cache key over the stable build inputs
#
# The build SELF-VERIFIES before caching anything: the dump is restored
# onto a blank second disk of the build guest, that disk is booted via a
# boot-order flip, and success means `qm guest ping` answered on the
# RESTORED copy — exactly the property the scenarios depend on
# (dd-onto-block-device -> boot -> agent answers).
#
# The journey-side helper that consumes the cache (itf_vmos_image_zvol)
# lives in journeys/common.sh with the other lab builders; only the
# build/status machinery is driver-side.

if [[ -n "${ITF_LIB_VMOS_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_VMOS_LOADED=1

# Root of the integrated-testing tree (the directory containing itf);
# config-lib normally sets ITF_ROOT first, but this library stays
# loadable standalone (framework tests source it directly).
ITF_ROOT="${ITF_ROOT:-$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)}"

ITF_VMOS_NAME="itf-vmos"
ITF_VMOS_BUILD_NAME="itf-vmos-build"
ITF_VMOS_DEFAULT_DISK_GB=4

# itf_vmos_stamp_want
#
# Echoes the cache key over the STABLE build inputs: the ISO, the ssh
# key, and the disk size.  The rendered preseed itself embeds a fresh
# random root-password hash on every render (stage_os calls
# itf_preseed_render), which must not defeat the cache — the same rule
# itf_pve_iso_customize applies to its answers stamp.
itf_vmos_stamp_want() {
    local disk_gb="${1:-$ITF_VMOS_DEFAULT_DISK_GB}"
    local hash
    hash="$(sha256sum "$ITF_SSH_KEY" 2>/dev/null | awk '{print $1}')"
    printf '%s %s %s %s' "$ITF_ISO_NAME" "$hash" "${disk_gb}G" "preseed-v1"
}

# itf_vmos_cached [disk-gb]
#
# True when the cache holds an image whose stamp matches the inputs.
itf_vmos_cached() {
    local want
    want="$(itf_vmos_stamp_want "${1:-}")"
    [[ -s "$ITF_CACHE_DIR/$ITF_VMOS_NAME.raw.gz" \
        && -f "$ITF_CACHE_DIR/$ITF_VMOS_NAME.stamp" \
        && "$(cat "$ITF_CACHE_DIR/$ITF_VMOS_NAME.stamp")" == "$want" ]]
}

# itf_vmos_status
#
# Human-facing cache state for `itf vmimage status`.
itf_vmos_status() {
    local img="$ITF_CACHE_DIR/$ITF_VMOS_NAME.raw.gz"
    if itf_vmos_cached; then
        echo "cached: $img ($(du -h "$img" | awk '{print $1}'))"
        echo "stamp:  $(cat "$ITF_CACHE_DIR/$ITF_VMOS_NAME.stamp")"
        return 0
    fi
    if [[ -s "$img" ]]; then
        echo "stale:  $img exists but its stamp does not match the current inputs"
        echo "        rerun: itf vmimage build"
    else
        echo "absent: no cached VM-OS image"
        echo "        build: itf vmimage build"
    fi
    return 1
}

# _itf_vmos_scsi0_volid <base> <vmid>
#
# Echoes the guest's scsi0 volid from `qm config` (e.g.
# "itfguests:vm-8005-disk-0").  Fails loudly when the config carries no
# scsi0 line — that would mean the build guest lost its system disk.
_itf_vmos_scsi0_volid() {
    local base="$1" vmid="$2" volid
    # The volid itself contains a colon ("storage:volume"), so split on
    # the key prefix, not on colons; trailing ",options" fall away.
    volid="$(itf_qm "$base" config "$vmid" 2>/dev/null \
        | sed -n 's/^scsi0:[[:space:]]*//p' | head -1)"
    volid="${volid%%,*}"
    if [[ -z "$volid" ]]; then
        echo "itf: build guest $vmid has no scsi0 volume in its config" >&2
        return 1
    fi
    echo "$volid"
}

# itf_vmos_dump_to_run_dir <base> <vmid>
#
# Dumps the STOPPED build guest's system disk into
# $ITF_RUN_DIR/itf-vmos.raw.gz: pvesm path resolves the volume (itf
# volumes only — the guard refuses anything else), the base-side dd|gzip
# is the one sanctioned read of an itf-storage volume (audit-logged,
# disposable build-guest data only), and the result is pulled back
# through the unprivileged scp path.  The world-readable /tmp staging
# file is acceptable: its content is a disposable test image whose root
# password is random and unrecorded.
itf_vmos_dump_to_run_dir() {
    local base="$1" vmid="$2"
    local volid devpath tmp_remote
    volid="$(_itf_vmos_scsi0_volid "$base" "$vmid")" || return 1
    devpath="$(itf_pvesm "$base" path "$volid" 2>/dev/null | tail -1)" || {
        echo "itf: pvesm path failed for $volid" >&2
        return 1
    }
    if [[ -z "$devpath" || ! "$devpath" == /* ]]; then
        echo "itf: pvesm path returned no absolute path for $volid" >&2
        return 1
    fi
    if [[ "$devpath" == *.qcow2 ]]; then
        echo "itf: itf guest storage is qcow2-backed ($devpath); the VM-OS" \
            "image needs a raw-backed storage (lvmthin or dir+raw)" >&2
        echo "itf: PREP: recreate ITF_GUEST_STORAGE raw-backed, or point it at" \
            "an lvmthin storage" >&2
        return 1
    fi
    tmp_remote="/tmp/itf-vmos-dump-$$"
    itf_log_action "$base" "vmos-dump: $volid -> $tmp_remote"
    local dump_cmd
    dump_cmd="dd if=$(printf '%q' "$devpath") bs=4M status=none"
    dump_cmd+=" | gzip -1c > $(printf '%q' "$tmp_remote")"
    dump_cmd+=" && chmod 644 $(printf '%q' "$tmp_remote")"
    if ! itf_base_exec "$base" "$dump_cmd"; then
        itf_base_exec "$base" "rm -f $(printf '%q' "$tmp_remote")" || true
        echo "itf: base-side dump failed for $devpath" >&2
        return 1
    fi
    if ! itf_base_get "$base" "$tmp_remote" "$ITF_RUN_DIR/$ITF_VMOS_NAME.raw.gz"; then
        itf_base_exec "$base" "rm -f $(printf '%q' "$tmp_remote")" || true
        echo "itf: dump pull-back failed" >&2
        return 1
    fi
    itf_base_exec "$base" "rm -f $(printf '%q' "$tmp_remote")" || true
    itf_log_action "$base" "vmos-dump: pulled and cleaned $tmp_remote"
    if [[ ! -s "$ITF_RUN_DIR/$ITF_VMOS_NAME.raw.gz" ]]; then
        echo "itf: dump came back empty" >&2
        return 1
    fi
    return 0
}

# itf_vmos_wait_guest_ping <base> <vmid> [timeout-seconds]
#
# Polls the guest agent until it answers or the timeout expires.  The
# agent-RPC form is `qm agent <vmid> ping` — the VMID comes BEFORE the
# agent command, and there is no `qm guest ping` on PVE 9 at all (both
# live-verified on 9.2.21).  Read verb, no audit noise.
itf_vmos_wait_guest_ping() {
    local base="$1" vmid="$2" timeout="${3:-900}"
    local deadline=$(( SECONDS + timeout ))
    while (( SECONDS < deadline )); do
        if itf_qm "$base" agent "$vmid" ping > /dev/null 2>&1; then
            return 0
        fi
        sleep 5
    done
    return 1
}

# itf_vmos_build [--force] [--disk-gb N]
#
# Builds (or reuses) the cached VM-OS image.  Requires the report
# context the driver's vmimage subcommand sets up (ITF_RUN_DIR +
# itf_step) and the run lock; stages:
#   1. stamp short-circuit (cached image with matching inputs);
#   2. fresh preseed install of a small dedicated Debian guest
#      (itf_journey_stage_os — qemu-guest-agent rides in the preseed);
#   3. stop the guest, dump its system disk base-side into the run dir;
#   4. self-verify: restore the dump onto a blank scsi1 of the same
#      guest, boot THAT disk via boot order, and require the agent to
#      answer on the restored copy;
#   5. destroy the build guest, promote the dump + stamp into the cache.
itf_vmos_build() {
    local force=0 disk_gb="$ITF_VMOS_DEFAULT_DISK_GB"
    while (( $# > 0 )); do
        case "$1" in
            --force) force=1; shift ;;
            --disk-gb) disk_gb="$2"; shift 2 ;;
            *) echo "itf: unknown itf_vmos_build option: $1" >&2; return 2 ;;
        esac
    done
    if [[ ! "$disk_gb" =~ ^[0-9]+$ ]] || (( disk_gb < 4 )); then
        echo "itf: --disk-gb must be an integer >= 4" >&2
        return 2
    fi

    if (( ! force )) && itf_vmos_cached "$disk_gb"; then
        itf_step skip "VM-OS image build" \
            "already cached and fresh — $(itf_vmos_status | head -1);" \
            "rerun with --force to rebuild"
        return 0
    fi

    [[ -s "$ITF_CACHE_DIR/$ITF_ISO_NAME" ]] || {
        itf_step fail "VM-OS image build" \
            "Debian ISO not cached — PREP: itf iso fetch"
        return 1
    }

    local base="${ITF_STORAGE_BASE:-${ITF_BASE_HOSTS[0]}}"

    # A leftover build VM marks an interrupted build attempt.
    local leftover_vmid
    leftover_vmid="$(itf_qm "$base" list 2>/dev/null \
        | awk -v n="$ITF_VMOS_BUILD_NAME" '$2 == n {print $1; exit}')"
    if [[ -n "$leftover_vmid" ]]; then
        itf_step info "vmimage: leftover build VM removed" "vmid $leftover_vmid"
        itf_guest_destroy "$base" "$leftover_vmid" > /dev/null 2>&1 || true
    fi

    # 1. The minimal Debian: OS install only (no product), same preseed
    #    and serial-driver machinery the journeys trust.  The install
    #    runs on a disk of the image's OWN size (--sysdisk), so the dump
    #    restores exactly onto the zvols and verify disks of that size;
    #    a small disk also keeps the cached gzip thin.  (Conditional
    #    source: the in-process framework tests pre-load common.sh with
    #    stubbed stages — re-sourcing would clobber them.)
    # shellcheck disable=SC1090  # dynamic path into the journeys tree
    declare -F itf_journey_stage_os > /dev/null \
        || source "$ITF_ROOT/journeys/common.sh"
    if ! itf_journey_stage_os "$ITF_VMOS_BUILD_NAME" "$ITF_VMOS_NAME" \
            --base "$base" --sysdisk "$disk_gb"; then
        return 1
    fi
    local vmid="$J_VMID"

    # 2. Quiesced dump: the guest must be DOWN for a consistent read.
    if itf_guest_stop "$base" "$vmid" > "$ITF_RUN_DIR/vmos-build-stop.log" 2>&1; then
        itf_step pass "build guest stopped" "vmid $vmid (quiesced for the dump)"
    else
        itf_step fail "build guest stopped" "see vmos-build-stop.log"
        return 1
    fi
    if itf_vmos_dump_to_run_dir "$base" "$vmid"; then
        itf_step pass "system disk dumped" \
            "$ITF_RUN_DIR/$ITF_VMOS_NAME.raw.gz (gzip'd raw, audit-logged)"
    else
        itf_step fail "system disk dumped" "see messages above"
        return 1
    fi

    # 3. Self-verify on a blank second disk of the same guest: restore,
    #    boot the RESTORED copy, require the agent to answer.  This is
    #    the exact property scenarios depend on later (dd -> boot ->
    #    qm guest exec works).
    local gz="$ITF_RUN_DIR/$ITF_VMOS_NAME.raw.gz"
    # The install guest carries the installer-time CPU freeze (--freeze 1
    # pairs the frozen start with an explicit resume during the serial
    # install); any later start without a resume would sit frozen in
    # prelaunch with the agent silent forever.  Clear it AFTER the dump's
    # stop and BEFORE the verify start — itf_guest_clone clears the same
    # inherited flag on every clone for the same reason.
    if itf_qm "$base" set "$vmid" --freeze 0 \
            > "$ITF_RUN_DIR/vmos-verify-unfreeze.log" 2>&1 \
        && itf_qm "$base" set "$vmid" --scsi1 "${ITF_GUEST_STORAGE}:${disk_gb}" \
            > "$ITF_RUN_DIR/vmos-verify-attach.log" 2>&1 \
        && itf_guest_start "$base" "$vmid" \
            > "$ITF_RUN_DIR/vmos-verify-start.log" 2>&1; then
        itf_step pass "verify boot started" \
            "build guest up with blank scsi1 (${disk_gb}G; installer freeze cleared)"
    else
        itf_step fail "verify boot started" \
            "see vmos-verify-{unfreeze,attach,start}.log"
        return 1
    fi
    local s_ip
    s_ip="$(itf_guest_ip "$base" "$vmid" 600)"
    if [[ -z "$s_ip" ]]; then
        itf_step fail "verify boot started" "guest agent reported no IP in 600s"
        return 1
    fi
    itf_guest_put "$s_ip" "$gz" /root/itf-vmos.raw.gz > /dev/null 2>&1
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if itf_guest_exec "$s_ip" '
            set -e
            for i in $(seq 1 30); do lsblk -dn -o NAME | grep -qx sdb && break; sleep 2; done
            lsblk -dn -o NAME | grep -qx sdb
            gunzip -dc /root/itf-vmos.raw.gz | dd of=/dev/sdb bs=4M conv=sparse status=none
            sync
            rm -f /root/itf-vmos.raw.gz
        ' > "$ITF_RUN_DIR/vmos-verify-restore.log" 2>&1; then
        itf_step pass "image restored to verify disk" "/dev/sdb (sparse dd)"
    else
        itf_step fail "image restored to verify disk" "see vmos-verify-restore.log"
        return 1
    fi

    # Boot the RESTORED disk: stop, scsi1 first, start, agent gate.
    itf_guest_stop "$base" "$vmid" > /dev/null 2>&1 || true
    if itf_qm "$base" set "$vmid" --boot "order=scsi1" \
            > "$ITF_RUN_DIR/vmos-verify-order.log" 2>&1 \
            && itf_guest_start "$base" "$vmid" \
            > "$ITF_RUN_DIR/vmos-verify-boot.log" 2>&1; then
        itf_step info "verify boot reordered" "booting from the restored disk (scsi1)"
    else
        itf_step fail "verify boot reordered" "see vmos-verify-{order,boot}.log"
        return 1
    fi
    if itf_vmos_wait_guest_ping "$base" "$vmid" 900; then
        itf_step pass "restored image boots with agent" \
            "qm guest ping answered on the dd-restored copy"
    else
        itf_step fail "restored image boots with agent" \
            "no agent answer within 900s — see vmos-verify-boot.log"
        return 1
    fi

    # 4. Promote to the cache; the build guest's work is done.
    itf_guest_destroy "$base" "$vmid" > "$ITF_RUN_DIR/vmos-build-destroy.log" 2>&1 \
        || {
            itf_step fail "build guest destroyed" "see vmos-build-destroy.log"
            return 1
        }
    mkdir -p "$ITF_CACHE_DIR"
    mv "$gz" "$ITF_CACHE_DIR/$ITF_VMOS_NAME.raw.gz"
    itf_vmos_stamp_want "$disk_gb" > "$ITF_CACHE_DIR/$ITF_VMOS_NAME.stamp"
    itf_step pass "VM-OS image cached" \
        "$ITF_CACHE_DIR/$ITF_VMOS_NAME.raw.gz \
($(du -h "$ITF_CACHE_DIR/$ITF_VMOS_NAME.raw.gz" | awk '{print $1}'))"
    return 0
}
