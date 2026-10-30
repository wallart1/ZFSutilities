#!/usr/bin/env bash
# common.sh — shared journey stages, factored from j01-fresh-install.
#
# Composable stages:
#   itf_journey_stage_os <gname> <hostname> [--base B] [--role R] [--sysdisk GB]
#       Fresh Debian guest: custom serial-console ISO + preseed install,
#       IP discovery, root SSH, os-installed snapshot.
#       --sysdisk overrides the site-config system-disk size (the VM-OS
#       image build installs onto a small disk so the cached image fits
#       the zvols it is restored onto).
#       Under --rerun: roll the previous run's guest back to its
#       os-installed checkpoint instead of reinstalling.
#       Sets globals J_VMID and J_GUEST_IP on success.
#   itf_journey_stage_pve_os <gname> <hostname> [--base B] [--role R]
#       Fresh Proxmox VE guest: auto-installer boot ISO (answers embedded,
#       no preseed server), serial-watch the install, IP discovery, root
#       SSH, pve-installed snapshot.  The compute-role counterpart of
#       stage_os.
#   itf_journey_stage_install <guest-ip>
#       First-time-user product install: download (per ITF_SW_SOURCE),
#       expected-to-fail prerequisite check on the fresh system,
#       install-single-node with piped answers, installed-state verify.
#   itf_journey_stage_prepare_install <guest-ip>
#       The shared prefix of stage_install without the installer run —
#       download tooling, the user's download, the prerequisite check —
#       for failure-path journeys that drive the installer themselves.
#   itf_journey_stage_from_template <gname> [--base B] [--template T] [--role R]
#       Clone start: full-clone a post-install baseline template
#       (itf template build) instead of installing — the fast path for
#       journeys whose scenario begins after installation.
#       Under --rerun: roll the previous run's guest back to its
#       as-cloned checkpoint instead of cloning.
#       Sets globals J_VMID and J_GUEST_IP on success.
#   itf_journey_stage_test_pools <gname> <base> <vmid> <guest_ip>
#       The documented three-RAIDZ1 test pools (j01/j04/j05/j11 recipe)
#       as one stage: pool-disk hot-plug, guest recipe, pools-created
#       snapshot.  Coordinates are explicit — two-node journeys stage
#       several guests and J_* then holds only the last one's.
#   itf_single_node_lab_main <gname>
#       The single-node lab prefix (j04/j11): template clone,
#       installed-state verify, test pools.
#   itf_journey_stage_reboot_guest <gname> <role> [--power] [--timeout N]
#       Reboot a staged role guest (in-guest reboot; --power = guarded
#       stop/start), wait for ssh, re-discover a re-leased DHCP address,
#       rewrite the guest record, refresh J_GUEST_IP.
#       itf_reboot_guest_begin/wait are its split halves — the gap
#       between them is the outage window for peer-node fallout.
#   itf_vmos_image_zvol <s_ip> <zvol>
#       Write the cached VM-OS image (itf vmimage build) onto a
#       product-created zvol from the storage guest (sparse dd).
#   itf_vm_* — agent-channel workload helpers for the VM booted from
#       that zvol: boot gate, 1 Hz timestamp writer, sample/checksum,
#       stall-gap parser (see the section comments below).
#   itf_keystore_* — the LUKS key-device lab on the storage guest
#       (provision/insert/remove/unlock_mount/lock_umount), and
#       itf_journey_stage_encrypted_key_lun for the opt-in
#       j05_two_node_lab_main --encrypted-keys tail.
#   itf_journey_stage_boot_workload_lab <gname> <s_base> <s_vmid> <s_ip> <c_ip>
#       The j15 boot-and-keys staging tail on the encrypted two-node
#       lab: OS LUNs through the product (plain for VM 101, encrypted
#       for VM 202), VM-OS image, running writers, fence premise,
#       pre-reboot save+check gates, workload VMs parked stopped.
#   Boot-and-keys scenario helpers (j15): itf_key_ceremony (the
#       documented key ceremony as one stage), itf_storage_boot_state +
#       itf_boot_journal_verdict (boot-journal capture and the pure
#       order/verdict parser), itf_storage_load_keys,
#       itf_keystore_unlock_mount_wrong, itf_vm_disk_links_present /
#       itf_wait_vm_disk_links, itf_compute_fallout_sample,
#       itf_fence_tick, itf_vm_evidence, itf_new_vm_disk_encrypted,
#       itf_safe_save_gate, itf_iscsi_check_gate, itf_keystatus.
#
# Stages remember their guest in $ITF_RUN_DIR/guest.txt (base + vmid,
# + IP once discovered); a --role R labels it per-guest instead
# (guest-<R>.txt) so a two-guest journey like j05 keeps one record per
# node.
#
# HTTP-server shutdown on abort paths goes through the J_PIDFILE /
# J_PIDFILE2 globals: an EXIT trap cannot see function-locals after the
# function returns, so the stage functions publish their pidfiles there
# and clear them once stopped.

itf_journey_stage_os() {
    local gname="$1"
    local guest_hostname="$2"
    shift 2
    local base="${ITF_BASE_HOSTS[0]}" role="" sysdisk="${ITF_GUEST_SYSTEM_DISK_GB:-}"
    while (( $# > 0 )); do
        case "$1" in
            --base) base="$2"; shift 2 ;;
            --role) role="$2"; shift 2 ;;
            --sysdisk) sysdisk="$2"; shift 2 ;;
            *) echo "itf: unknown itf_journey_stage_os option: $1" >&2; return 2 ;;
        esac
    done
    # Per-guest record file: guest.txt by default, guest-<role>.txt when
    # the journey labels the stage's role.
    local guest_file="$ITF_RUN_DIR/guest.txt"
    [[ -n "$role" ]] && guest_file="$ITF_RUN_DIR/guest-${role}.txt"
    local vmid guest_ip dev_ip preseed_file serve_dir

    # --rerun: replay on the previous run's guest — a rollback to the
    # os-installed checkpoint replaces the whole install machinery (the
    # driver put the recorded guests in rerun-guests.tsv; nothing there =
    # fresh run).  The rolled-back guest is a clean Debian with the
    # prerequisites genuinely missing, so install-start journeys (j01,
    # j08, j09) keep their coverage — a template clone can never stand in
    # for that.
    local rerun_pair r_base r_vmid
    rerun_pair="$(itf_rerun_guest "$(basename "$guest_file")")"
    if [[ -n "$rerun_pair" ]]; then
        r_base="${rerun_pair%% *}"
        r_vmid="${rerun_pair##* }"
        # Remember the guest for post-mortem/diagnostics even if we abort.
        echo "$r_base $r_vmid" > "$guest_file"
        if itf_qm "$r_base" status "$r_vmid" \
                > "$ITF_RUN_DIR/guest-status-${gname}.log" 2>&1; then
            itf_step pass "rerun guest present" "vmid $r_vmid on $r_base"
        else
            itf_step fail "rerun guest present" \
                "vmid $r_vmid no longer on $r_base — run fresh (no --rerun)"
            return 1
        fi
        if itf_qm "$r_base" listsnapshot "$r_vmid" 2>/dev/null \
                | awk '$1 == "`->" && $2 == "os-installed" { found = 1 }
                       END { exit !found }'; then
            itf_step pass "os-installed checkpoint present" "vmid $r_vmid"
        else
            itf_step fail "os-installed checkpoint present" \
                "vmid $r_vmid has no os-installed snapshot — run fresh (no --rerun)"
            return 1
        fi
        # Snapshots newer than os-installed SURVIVE a rollback on this
        # stack but go stale (their content predates the replay) — and
        # the replay re-snapshots the same names, which would collide.
        # Remove them first so the guest matches a fresh install's
        # checkpoint list.
        itf_guest_stop "$r_base" "$r_vmid" > /dev/null 2>&1 || true
        local stale
        while IFS= read -r stale; do
            [[ -n "$stale" ]] || continue
            if itf_qm "$r_base" delsnapshot "$r_vmid" "$stale" \
                    > "$ITF_RUN_DIR/guest-delsnap-${gname}.log" 2>&1; then
                itf_step pass "stale snapshot removed" \
                    "$stale (newer than os-installed, left stale by the rollback)"
            else
                itf_step fail "stale snapshot removed" \
                    "$stale — see guest-delsnap-${gname}.log"
                return 1
            fi
        done < <(itf_qm "$r_base" listsnapshot "$r_vmid" 2>/dev/null \
                | awk '$1 == "`->" {
                    if ($2 == "os-installed") { seen = 1; next }
                    if (seen && $2 != "current") print $2
                }')
        if itf_guest_rollback "$r_base" "$r_vmid" os-installed \
                > "$ITF_RUN_DIR/guest-rollback-${gname}.log" 2>&1; then
            itf_step pass "guest rolled back to os-installed" \
                "vmid $r_vmid — no reinstall; the journey replays from the checkpoint"
        else
            itf_step fail "guest rolled back to os-installed" \
                "see guest-rollback-${gname}.log"
            return 1
        fi
        # The rollback restores the os-installed snapshot's VM config,
        # which still carries the installer-time CPU freeze (--freeze 1
        # pairs the frozen start with an explicit resume so the serial
        # console catches the first boot byte).  Clear it AFTER the
        # rollback and BEFORE the start — a pre-rollback clear reverts
        # with the config — or the guest sits frozen in prelaunch and
        # the IP/ssh gates time out.  itf_guest_clone clears the same
        # inherited flag on every clone.
        if itf_qm "$r_base" set "$r_vmid" --freeze 0 \
                > "$ITF_RUN_DIR/guest-freeze-${gname}.log" 2>&1; then
            itf_step pass "installer freeze cleared" \
                "vmid $r_vmid boots unfrozen after the rollback"
        else
            itf_step fail "installer freeze cleared" \
                "see guest-freeze-${gname}.log"
            return 1
        fi
        if itf_guest_start "$r_base" "$r_vmid" \
                > "$ITF_RUN_DIR/guest-start-${gname}.log" 2>&1; then
            itf_step pass "guest started" "vmid $r_vmid"
        else
            itf_step fail "guest started" "see guest-start-${gname}.log"
            return 1
        fi
        guest_ip="$(itf_guest_ip "$r_base" "$r_vmid" 600)"
        if [[ -n "$guest_ip" ]]; then
            itf_step pass "guest IP discovered" "$guest_ip"
            echo "$r_base $r_vmid $guest_ip" > "$guest_file"
        else
            itf_step fail "guest IP discovered" "guest agent reported nothing in 600s"
            return 1
        fi
        if itf_wait_ssh "$guest_ip" 300; then
            itf_step pass "guest ssh reachable" "root@${guest_ip}"
        else
            itf_step fail "guest ssh reachable"
            return 1
        fi
        # shellcheck disable=SC2034  # consumed by the journey scripts
        J_VMID="$r_vmid"
        # shellcheck disable=SC2034  # consumed by the journey scripts
        J_GUEST_IP="$guest_ip"
        return 0
    fi

    serve_dir="$ITF_RUN_DIR/serve"
    mkdir -p "$serve_dir"
    preseed_file="$serve_dir/preseed-${gname}.cfg"
    if itf_preseed_render "$preseed_file" "$guest_hostname"; then
        itf_step pass "preseed rendered" "$preseed_file"
    else
        itf_step fail "preseed rendered"
        return 1
    fi

    dev_ip="$(itf_dev_ip)"
    if [[ -n "$dev_ip" ]]; then
        itf_step pass "dev IP discovered" "$dev_ip"
    else
        itf_step fail "dev IP discovered" "set ITF_DEV_IP in the site config"
        return 1
    fi

    J_PIDFILE="$ITF_RUN_DIR/http.pid"
    if itf_http_serve "$serve_dir" "$J_PIDFILE"; then
        itf_step info "preseed HTTP serving" \
            "http://${dev_ip}:${ITF_HTTP_PORT}/preseed-${gname}.cfg"
    else
        itf_step fail "preseed HTTP serving" \
            "port $ITF_HTTP_PORT unavailable — see $ITF_RUN_DIR/http.log"
        J_PIDFILE=""
        return 1
    fi
    # Abort paths (set -u, Ctrl-C, failed steps) must not leak the HTTP
    # server onto the port — the next run would fail its serve gate.
    # The globals outlive the stage function, unlike its locals.
    _journey_exit_cleanup() {
        [[ -n "${J_PIDFILE:-}" ]] && itf_http_stop "$J_PIDFILE"
        [[ -n "${J_PIDFILE2:-}" ]] && itf_http_stop "$J_PIDFILE2"
        # An EXIT-trap handler must not end in failure: under the driver's
        # set -e, a false [[ ]] guard as the last command rewrites a
        # successful run's exit code to 1.
        return 0
    }
    trap _journey_exit_cleanup EXIT
    # Fetch the URL ourselves before spending a guest install on it: a
    # 404 here is exactly what sends d-i into interactive prompting.
    if curl -fsS --max-time 10 -o /dev/null \
        "http://127.0.0.1:${ITF_HTTP_PORT}/preseed-${gname}.cfg"; then
        itf_step pass "preseed URL serves" \
            "200 OK from http://${dev_ip}:${ITF_HTTP_PORT}/preseed-${gname}.cfg"
    else
        itf_step fail "preseed URL serves" "fetch failed — see $ITF_RUN_DIR/http.log"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    # The installer's syslog target: d-i streams its log via UDP to the
    # base, which the journey pulls back as an artifact — the only
    # visibility into hangs that draw nothing on the serial console.
    local base_ip boot_append boot_iso
    base_ip="$(itf_read "$base" hostname -I | awk '{print $1}')"
    if [[ -z "$base_ip" ]]; then
        itf_step fail "base LAN IP discovered" "needed for the installer syslog target"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    # Custom boot ISO: serial-console bootloader + auto-booted default
    # entry carrying the kernel append below.  Typing the boot line over
    # the serial console is lossy under nested virt (observed twice:
    # characters dropped from auto=), so the installer must start with
    # zero keystrokes.  The hostname/domain/interface answers ride on
    # the kernel command line because network preseeding loads only
    # AFTER network config, and the hostname question comes during it.
    boot_append="auto=true url=http://${dev_ip}:${ITF_HTTP_PORT}/preseed-${gname}.cfg"
    boot_append+=" netcfg/get_hostname=${guest_hostname} netcfg/get_domain=localdomain"
    boot_append+=" netcfg/choose_interface=auto log_host=${base_ip} console=ttyS0,115200n8 ---"
    boot_iso="$(itf_iso_customize "$base" "$boot_append" \
        2>"$ITF_RUN_DIR/iso-customize.log")"
    if [[ -n "$boot_iso" ]]; then
        itf_step pass "custom boot ISO ready" \
            "$boot_iso (serial console, auto-boot, preseed append)"
    else
        itf_step fail "custom boot ISO ready" "see iso-customize.log"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    vmid="$(itf_guest_create "$gname" --base "$base" --iso "$boot_iso" \
        --sysdisk "$sysdisk" --freeze 2>"$ITF_RUN_DIR/guest-create.log")"
    if [[ -n "$vmid" ]]; then
        itf_step pass "guest created (CPU-frozen)" "vmid $vmid"
    else
        itf_step fail "guest created" "see guest-create.log"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi
    # Remember the guest for post-mortem/diagnostics even if we abort.
    echo "$base $vmid" > "$guest_file"

    # Installer syslog capture listener on the base (target address was
    # baked into the boot append above).
    if itf_syslog_start "$base" "$vmid"; then
        itf_step pass "syslog capture armed" \
            "d-i logs -> ${base_ip}:514 -> /tmp/itf-syslog-${vmid}.log"
    else
        itf_step fail "syslog capture armed" "needed to diagnose installer hangs"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    # Power on FROZEN (no boot output yet), attach the serial console,
    # then resume — the console captures from the very first byte.  The
    # custom ISO auto-boots into the preseeded install, so the driver
    # only WATCHES: transcript + exit pattern (finishing reboot or the
    # installed system's login prompt).  The blind keypress kick stays
    # as a backstop if the resume ever races the attach.
    local serial_log driver_pid driver_rc
    serial_log="$ITF_RUN_DIR/serial-install.log"
    : > "$serial_log"

    if itf_qm "$base" start "$vmid" > "$ITF_RUN_DIR/guest-start.log" 2>&1; then
        itf_step pass "guest started (frozen)" "vmid $vmid"
    else
        itf_step fail "guest started" "see guest-start.log"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    python3 "$ITF_ROOT/lib/serial_console.py" \
        --host "$base" --user "$ITF_SSH_USER" --vmid "$vmid" \
        --kick $'\x1b[B' --kick-delay 8 \
        --wait 'Installation complete' --send $'\n' \
        --exit-after 'Restarting system|Power down|login:' \
        --timeout 3600 \
        --log "$serial_log" > "$ITF_RUN_DIR/serial-console.log" 2>&1 &
    driver_pid=$!
    sleep 5

    if itf_qm "$base" resume "$vmid" > "$ITF_RUN_DIR/guest-resume.log" 2>&1; then
        itf_step info "guest resumed" "boot proceeding with console attached"
    else
        itf_step fail "guest resumed" "see guest-resume.log"
        kill "$driver_pid" 2>/dev/null
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi

    wait "$driver_pid"
    driver_rc=$?
    itf_syslog_stop "$base" "$vmid" "$ITF_RUN_DIR/installer-syslog.log" \
        && itf_artifact "installer-syslog" "$ITF_RUN_DIR/installer-syslog.log" || true
    itf_artifact "serial-transcript" "$serial_log"
    if [[ $driver_rc -eq 0 ]]; then
        itf_step pass "serial install driven" \
            "install ran to its finishing reboot (see serial-install.log)"
    else
        itf_step fail "serial install driven" "driver rc=$driver_rc — see serial-install.log"
        itf_http_stop "$J_PIDFILE"
        J_PIDFILE=""
        return 1
    fi
    itf_http_stop "$J_PIDFILE"
    J_PIDFILE=""

    # The installer is finishing its reboot now.  Boot order is disk-first,
    # so the ISO no longer wins; detach it anyway (best-effort) so no later
    # reset can ever land in a second installer round.
    if itf_qm "$base" set "$vmid" --ide2 none,media=cdrom \
            > "$ITF_RUN_DIR/iso-detach.log" 2>&1; then
        itf_step info "install ISO detached" "guest reboots from disk only"
    else
        itf_step info "install ISO detach failed" "see iso-detach.log (non-fatal)"
    fi

    # The guest itself must have fetched the preseed (the 127.0.0.1 GETs
    # are our own probe and URL check; anything else is the installer).
    if grep -v '^127\.0\.0\.1' "$ITF_RUN_DIR/http.log" \
            | grep -q "GET /preseed-${gname}.cfg"; then
        itf_step pass "preseed fetched by guest" "GET logged in http.log"
    else
        itf_step fail "preseed fetched by guest" \
            "no guest GET in http.log — install ran without the preseed"
        return 1
    fi

    guest_ip="$(itf_guest_ip "$base" "$vmid" 600)"
    if [[ -n "$guest_ip" ]]; then
        itf_step pass "guest IP discovered" "$guest_ip"
        echo "$base $vmid $guest_ip" > "$guest_file"
    else
        itf_step fail "guest IP discovered" "guest agent reported nothing in 600s"
        return 1
    fi

    if itf_wait_ssh "$guest_ip" 600; then
        itf_step pass "guest ssh reachable" "root@${guest_ip}"
    else
        itf_step fail "guest ssh reachable"
        return 1
    fi

    if itf_guest_snapshot "$base" "$vmid" os-installed > /dev/null 2>&1; then
        itf_step pass "snapshot os-installed" "clean Debian checkpoint for later stages"
    else
        itf_step fail "snapshot os-installed"
    fi

    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_VMID="$vmid"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_GUEST_IP="$guest_ip"
    return 0
}

# itf_journey_stage_pve_os <gname> <hostname> [--base B] [--role R]
#
# Fresh Proxmox VE guest via the auto-installer: itf_pve_iso_customize
# embeds the answers (root SSH key, DHCP, single ext4 disk, first-boot
# repo-hygiene hook) in the boot ISO, so unlike stage_os there is no
# preseed HTTP server and no installer syslog to arm — the installer
# streams to the serial console the driver watches.  Success/failure is
# gated on the transcript actually containing the installer's own
# "Installation done" line, not merely on the console driver exiting.
# Sets globals J_VMID and J_GUEST_IP on success.
itf_journey_stage_pve_os() {
    local gname="$1"
    local guest_hostname="$2"
    shift 2
    local base="${ITF_COMPUTE_BASE:-${ITF_BASE_HOSTS[0]}}" role=""
    while (( $# > 0 )); do
        case "$1" in
            --base) base="$2"; shift 2 ;;
            --role) role="$2"; shift 2 ;;
            *) echo "itf: unknown itf_journey_stage_pve_os option: $1" >&2; return 2 ;;
        esac
    done
    local guest_file="$ITF_RUN_DIR/guest-pve.txt"
    [[ -n "$role" ]] && guest_file="$ITF_RUN_DIR/guest-${role}.txt"
    local vmid guest_ip boot_iso

    boot_iso="$(itf_pve_iso_customize "$base" "$guest_hostname" \
        2>"$ITF_RUN_DIR/iso-customize.log")"
    if [[ -n "$boot_iso" ]]; then
        itf_step pass "PVE auto-install ISO ready" \
            "$boot_iso (answers + first-boot hook embedded)"
    else
        itf_step fail "PVE auto-install ISO ready" "see iso-customize.log"
        return 1
    fi

    vmid="$(itf_guest_create "$gname" --base "$base" --iso "$boot_iso" \
        --freeze 2>"$ITF_RUN_DIR/guest-create.log")"
    if [[ -n "$vmid" ]]; then
        itf_step pass "guest created (CPU-frozen)" "vmid $vmid"
    else
        itf_step fail "guest created" "see guest-create.log"
        return 1
    fi
    echo "$base $vmid" > "$guest_file"

    # Power on FROZEN, attach the serial console, then resume — same
    # first-byte capture as stage_os.  grub's stock menu auto-boots the
    # Automated entry after its 10 s timeout, so the driver only WATCHES
    # (no keystrokes: an arrow key would move the menu selection OFF the
    # automated entry).
    local serial_log driver_pid driver_rc
    serial_log="$ITF_RUN_DIR/serial-install.log"
    : > "$serial_log"

    if itf_qm "$base" start "$vmid" > "$ITF_RUN_DIR/guest-start.log" 2>&1; then
        itf_step pass "guest started (frozen)" "vmid $vmid"
    else
        itf_step fail "guest started" "see guest-start.log"
        return 1
    fi

    # The installer's own exit lines: unconfigured.sh prints
    # "Installation done, rebooting..." on success; every failure path
    # funnels into err_reboot's "Installation aborted" (post-hook
    # failures print their own banner first and may wait 30 s).
    python3 "$ITF_ROOT/lib/serial_console.py" \
        --host "$base" --user "$ITF_SSH_USER" --vmid "$vmid" \
        --exit-after 'Installation done|Installation aborted|hook failed' \
        --timeout 3600 \
        --log "$serial_log" > "$ITF_RUN_DIR/serial-console.log" 2>&1 &
    driver_pid=$!
    sleep 5

    if itf_qm "$base" resume "$vmid" > "$ITF_RUN_DIR/guest-resume.log" 2>&1; then
        itf_step info "guest resumed" "boot proceeding with console attached"
    else
        itf_step fail "guest resumed" "see guest-resume.log"
        kill "$driver_pid" 2>/dev/null
        return 1
    fi

    wait "$driver_pid"
    driver_rc=$?
    itf_artifact "serial-transcript" "$serial_log"
    if [[ $driver_rc -eq 0 ]] && grep -q 'Installation done' "$serial_log"; then
        itf_step pass "serial install driven" \
            "installer reported completion (see serial-install.log)"
    else
        itf_step fail "serial install driven" \
            "driver rc=$driver_rc — see serial-install.log"
        return 1
    fi

    # Boot order is disk-first; detach the install ISO anyway so no later
    # reset can land in a second installer round.
    if itf_qm "$base" set "$vmid" --ide2 none,media=cdrom \
            > "$ITF_RUN_DIR/iso-detach.log" 2>&1; then
        itf_step info "install ISO detached" "guest reboots from disk only"
    else
        itf_step info "install ISO detach failed" "see iso-detach.log (non-fatal)"
    fi

    # The first-boot hook (repo hygiene + qemu-guest-agent) runs on this
    # first boot of the installed system, so IP discovery deliberately
    # waits through it.
    guest_ip="$(itf_guest_ip "$base" "$vmid" 900)"
    if [[ -n "$guest_ip" ]]; then
        itf_step pass "guest IP discovered" "$guest_ip"
        echo "$base $vmid $guest_ip" > "$guest_file"
    else
        itf_step fail "guest IP discovered" \
            "guest agent reported nothing in 900s (first-boot hook installs it)"
        return 1
    fi

    if itf_wait_ssh "$guest_ip" 600; then
        itf_step pass "guest ssh reachable" "root@${guest_ip}"
    else
        itf_step fail "guest ssh reachable"
        return 1
    fi

    if itf_guest_snapshot "$base" "$vmid" pve-installed > /dev/null 2>&1; then
        itf_step pass "snapshot pve-installed" "clean PVE checkpoint for later stages"
    else
        itf_step fail "snapshot pve-installed"
    fi

    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_VMID="$vmid"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_GUEST_IP="$guest_ip"
    return 0
}

# itf_journey_run_installer <guest-ip> <answers-printf-format> <step-label> [expected-rc]
#
# Runs ./bin/install-single-node from the guest's /root/ZFSutilities
# tree with piped answers and records the outcome under <step-label>.
# expected-rc (default 0) asserts a chosen exit code — failure-path
# journeys (prereq decline, apt failure) expect the installer's graceful
# abort (rc 1), not success.
itf_journey_run_installer() {
    local guest_ip="$1"
    local feed_format="$2"
    local label="$3"
    local expected_rc="${4:-0}"
    local answers inst_log inst_rc
    answers="$ITF_RUN_DIR/install-answers.txt"
    printf '%b' "$feed_format" > "$answers"
    inst_log="$ITF_RUN_DIR/guest-install.log"
    itf_guest_exec_feed "$guest_ip" "$answers" \
        "cd /root/ZFSutilities && ./bin/install-single-node" > "$inst_log" 2>&1
    inst_rc=$?
    itf_artifact "install-transcript" "$inst_log"
    if [[ $inst_rc -eq $expected_rc ]]; then
        if [[ $expected_rc -eq 0 ]]; then
            itf_step pass "$label" "rc=0 with piped answers"
        else
            itf_step pass "$label" "rc=$inst_rc as expected (graceful failure path)"
        fi
    else
        itf_step fail "$label" \
            "rc=$inst_rc, expected $expected_rc — see guest-install.log"
        return 1
    fi
    return 0
}

# itf_journey_stage_download <guest-ip>
#
# Downloads the product tree to /root/ZFSutilities on the guest, the way
# a user does: the latest published GitHub release, or (dev-tarball
# source) a tarball of the current working tree fetched from a
# short-lived second HTTP server.  Site-local and generated content
# stays out of the dev tarball.  Cleans the server up on every abort
# path via the J_PIDFILE2 global (see the trap note at the top).
itf_journey_stage_download() {
    local guest_ip="$1"
    local dl_script relver dev_ip
    dev_ip="$(itf_dev_ip)"
    dl_script="$ITF_RUN_DIR/guest-dl.sh"
    if [[ "$ITF_SW_SOURCE" == "dev-tarball" ]]; then
        local repo_root tarball serve_msg
        repo_root="$ITF_ROOT/../.."
        tarball="$ITF_RUN_DIR/serve/zfsutilities-dev.tar.gz"
        # The install path creates the serve dir for its preseed; the
        # clone-start path (j05) reaches this stage without one.
        mkdir -p "$ITF_RUN_DIR/serve"
        if ! tar -czf "$tarball" -C "$repo_root" \
                --exclude=.git \
                --exclude=.zcode \
                --exclude=docs/site \
                --exclude=tests/integrated/cache \
                --exclude=tests/integrated/results \
                --exclude=tests/integrated/site/config \
                --exclude=__pycache__ \
                --exclude='*.pyc' \
                . 2> "$ITF_RUN_DIR/dev-tarball.log"; then
            itf_step fail "release downloaded" "dev tarball build failed (see dev-tarball.log)"
            return 1
        fi
        J_PIDFILE2="$ITF_RUN_DIR/http-stageb.pid"
        serve_msg="$(itf_http_serve "$ITF_RUN_DIR/serve" "$J_PIDFILE2" 2>&1)" || {
            itf_step fail "release downloaded" "stage-B serve: $serve_msg"
            J_PIDFILE2=""
            return 1
        }
        cat > "$dl_script" <<EOF
#!/bin/bash
set -e
cd /root
echo "downloading: dev tarball from orchestrator"
curl -fsSL "http://${dev_ip}:${ITF_HTTP_PORT}/zfsutilities-dev.tar.gz" -o dev.tar.gz
mkdir -p /root/ZFSutilities
tar -xzf dev.tar.gz -C /root/ZFSutilities
rm -f dev.tar.gz
echo "release-version: \$(cat /root/ZFSutilities/VERSION)-dev"
EOF
    else
        cat > "$dl_script" <<EOF
#!/bin/bash
set -e
cd /root
latest_url=\$(curl -fsSL "https://api.github.com/repos/${ITF_GITHUB_REPO}/releases/latest" \
    | awk -F'"' '/tarball_url/{print \$4; exit}')
echo "downloading: \$latest_url"
curl -fsSL "\$latest_url" -o release.tar.gz
mkdir -p /root/ZFSutilities
tar -xzf release.tar.gz -C /root/ZFSutilities --strip-components=1
rm -f release.tar.gz
echo "release-version: \$(cat /root/ZFSutilities/VERSION)"
EOF
    fi
    itf_guest_put "$guest_ip" "$dl_script" /root/itf-dl.sh > /dev/null 2>&1
    relver="$(itf_guest_exec "$guest_ip" "bash /root/itf-dl.sh" \
        > "$ITF_RUN_DIR/guest-release-dl.log" 2>&1 \
        && awk -F': ' '/release-version/{print $2}' "$ITF_RUN_DIR/guest-release-dl.log")"
    if [[ -n "$relver" ]]; then
        itf_step pass "release downloaded" \
            "version $relver (dev repo: $(cat "$ITF_ROOT/../../VERSION" 2>/dev/null || echo '?'))"
        itf_artifact "release-download" "$ITF_RUN_DIR/guest-release-dl.log"
    else
        itf_step fail "release downloaded" "see guest-release-dl.log"
        if [[ -n "${J_PIDFILE2:-}" ]]; then
            itf_http_stop "$J_PIDFILE2"
            J_PIDFILE2=""
        fi
        return 1
    fi
    if [[ -n "${J_PIDFILE2:-}" ]]; then
        itf_http_stop "$J_PIDFILE2"
        J_PIDFILE2=""
    fi
    return 0
}

# itf_journey_stage_prepare_install <guest-ip>
#
# The shared prefix of every installer journey: the guest's download
# tooling (what a user does first), the user's download (per
# ITF_SW_SOURCE), and the expected-to-fail prerequisite check on the
# fresh system.  Failure-path journeys (prereq decline, apt failure)
# continue from here with their own installer feeds.
itf_journey_stage_prepare_install() {
    local guest_ip="$1"

    local guest_tooling
    guest_tooling="apt-get update -qq && DEBIAN_FRONTEND=noninteractive"
    guest_tooling+=" apt-get install -y -qq curl ca-certificates"
    if itf_guest_exec "$guest_ip" "$guest_tooling" \
        > "$ITF_RUN_DIR/guest-curl-install.log" 2>&1; then
        itf_step pass "guest: download tooling" "curl installed (what a user does first)"
    else
        itf_step fail "guest: download tooling" "see guest-curl-install.log"
        return 1
    fi

    itf_journey_stage_download "$guest_ip" || return 1

    local pre_log
    pre_log="$ITF_RUN_DIR/guest-prereq.log"
    if itf_guest_exec "$guest_ip" "/root/ZFSutilities/bin/check-prerequisites --single-node" \
        > "$pre_log" 2>&1; then
        itf_step fail "prereq check (fresh system)" "unexpectedly reported all-present"
    else
        itf_step pass "prereq check (fresh system)" "reports the missing items a user must handle"
        itf_artifact "prereq-check" "$pre_log"
    fi
    return 0
}

# itf_journey_stage_install <guest-ip>
#
# First-time-user product install: download (per ITF_SW_SOURCE),
# expected-to-fail prerequisite check on the fresh system, installer
# run with the fresh-system answer feed.
itf_journey_stage_install() {
    local guest_ip="$1"
    local feed_format='y\ny\n\n\n'

    itf_journey_stage_prepare_install "$guest_ip" || return 1

    # The installer's prompts, answered as a user would: accept the
    # offered prerequisite installation (y), confirm the apt run (y),
    # accept the default hostname (Enter), decline the config edit
    # (Enter).  The two remediation prompts exist because the
    # prerequisites step runs (the F-003 repair resolves the checker
    # from bin/).
    itf_journey_run_installer "$guest_ip" "$feed_format" "install-single-node completes" \
        || return 1
    return 0
}

# itf_journey_verify_installed <guest-ip>
#
# The installed-state assertions from j01 Stage C: deployment layout,
# config files, and the login-shell PATH wiring (profile.d only loads
# for login shells — a plain ssh command never sees it).
itf_journey_verify_installed() {
    local guest_ip="$1"
    local verify_log
    verify_log="$ITF_RUN_DIR/guest-verify.log"
    itf_guest_exec "$guest_ip" '
        echo "== current symlink =="
        ls -l /usr/local/lib/zfsutilities/current
        echo "== installed VERSION =="
        cat /usr/local/lib/zfsutilities/current/VERSION
        echo "== node.conf =="
        cat /etc/zfsutilities/node.conf
        echo "== zfsdailybackup on PATH (login shell) =="
        bash -lc "command -v zfsdailybackup"
        echo "== retention config exists =="
        ls -l /var/lib/zfsutilities/config.json
    ' > "$verify_log" 2>&1
    itf_guest_exec "$guest_ip" \
        "test -L /usr/local/lib/zfsutilities/current \
         && test -x /usr/local/lib/zfsutilities/current/bin/zfsdailybackup \
         && grep -q 'NODE_MODE=\"single-node\"' /etc/zfsutilities/node.conf \
         && bash -lc \"command -v zfsdailybackup\" \
         && test -s /var/lib/zfsutilities/config.json" > /dev/null 2>&1 \
        && itf_step pass "installed state verified" "see guest-verify.log" \
        || itf_step fail "installed state verified" "see guest-verify.log"
    itf_artifact "install-verify" "$verify_log"
}

# itf_journey_stage_test_pools <gname> <base> <vmid> <guest_ip>
#
# The documented three-RAIDZ1 test pools (the recipe from
# docs/docs/developer-guide/testing.md), factored from j01/j04/j05/j11:
# hot-plug the pool disk, run the recipe in the guest, snapshot
# pools-created.  Coordinates are explicit (not the J_* globals) because
# two-node journeys stage several guests and J_* then holds only the
# last one's.
#
# The pool disk attaches only AFTER the OS is up.  A second virtio disk
# present during an install reorders guest disk enumeration (observed
# live: the pool disk became /dev/sda and the OS installed onto it while
# the system disk stayed blank — "Boot failed: not a bootable disk").
# One disk at install time keeps /dev/sda unambiguous; virtio-scsi
# hotplug makes the pool disk appear as the only other disk, /dev/sdb.
itf_journey_stage_test_pools() {
    local gname="$1" base="$2" vmid="$3" guest_ip="$4"
    local wait_sdb
    # shellcheck disable=SC2016  # expansion runs in the guest
    wait_sdb='for i in $(seq 1 30); do lsblk -dn -o NAME | grep -qx sdb'
    wait_sdb+=' && exit 0; sleep 2; done; exit 1'
    if itf_qm "$base" set "$vmid" --scsi1 "${ITF_GUEST_STORAGE}:${ITF_GUEST_POOL_DISK_GB}" \
            > "$ITF_RUN_DIR/pooldisk-attach.log" 2>&1 \
            && itf_guest_exec "$guest_ip" "$wait_sdb"; then
        itf_step pass "pool disk attached" \
            "scsi1 (${ITF_GUEST_POOL_DISK_GB}G) hot-plugged, guest sees /dev/sdb"
    else
        itf_step fail "pool disk attached" "see pooldisk-attach.log"
        return 1
    fi

    local pool_script
    pool_script="$ITF_RUN_DIR/guest-pools.sh"
    cat > "$pool_script" <<'EOF'
#!/bin/bash
# The user recipe from docs/docs/developer-guide/testing.md on /dev/sdb,
# plus a udev settle the documented recipe lacks.
set -e
# parted/partprobe are not part of a base Debian install.
apt-get install -y parted
parted -s /dev/sdb mklabel gpt
for i in {1..15}; do
    if [[ $i -eq 1 ]]; then start="1MiB"; else start="$(( (i-1)*5120 ))MiB"; fi
    if [[ $i -eq 15 ]]; then end="100%"; else end="$(( i*5120 ))MiB"; fi
    parted -a optimal -s /dev/sdb mkpart primary "${start}" "${end}"
done
partprobe /dev/sdb
# udev creates the partition nodes asynchronously after partprobe, so an
# immediate zpool create races them ("cannot resolve path '/dev/sdbN'";
# run-20261007-152717-j04-post-install-baseline).  Settle, then wait
# (bounded) for the last partition node; the final test fails cleanly if
# it never appears.
udevadm settle --timeout=30 || true
for i in $(seq 1 30); do
    [[ -e /dev/sdb15 ]] && break
    sleep 1
done
[[ -e /dev/sdb15 ]]
zpool create -f zfstest1 raidz1 /dev/sdb1 /dev/sdb2 /dev/sdb3 /dev/sdb4 /dev/sdb5
zpool create -f zfstest2 raidz1 /dev/sdb6 /dev/sdb7 /dev/sdb8 /dev/sdb9 /dev/sdb10
zpool create -f zfstest3 raidz1 /dev/sdb11 /dev/sdb12 /dev/sdb13 /dev/sdb14 /dev/sdb15
zpool list
EOF
    itf_guest_put "$guest_ip" "$pool_script" /root/itf-pools.sh > /dev/null 2>&1
    if itf_guest_exec "$guest_ip" "bash /root/itf-pools.sh" \
        > "$ITF_RUN_DIR/guest-pools.log" 2>&1; then
        itf_step pass "test pools created" "zfstest1/2/3 (three RAIDZ1, docs recipe)"
        itf_artifact "pools" "$ITF_RUN_DIR/guest-pools.log"
    else
        itf_step fail "test pools created" "see guest-pools.log"
        return 1
    fi

    if itf_guest_snapshot "$base" "$vmid" pools-created > /dev/null 2>&1; then
        itf_step pass "snapshot pools-created" "test-pools checkpoint for later stages"
    else
        itf_step fail "snapshot pools-created"
    fi
    return 0
}

# itf_journey_stage_upgrade_env <gname>
#
# The shared release-upgrade staging, factored from j10: the upgrade
# premise (active version strictly older than the tree under test), the
# user's download of the tree under test, the change-scan baseline for
# the OLD version, and the itf HTTP server (the dev-tarball "latest
# release"; the pristine baseline when the old version's GitHub tag is
# missing) with its abort-path cleanup trap.  Requires J_GUEST_IP —
# run itf_journey_stage_from_template first.  Sets globals:
#   J_ACTIVE_VERSION      the deployed (old) version
#   J_TARGET_VERSION      the tree-under-test version
#   J_UPGRADE_CMD         full upgrader invocation (cd + env + command)
#   J_UPGRADE_ENV_EXPORTS "export K=V" lines for guest wrapper scripts
#                         that background the upgrader themselves
itf_journey_stage_upgrade_env() {
    local gname="$1"
    local guest_ip="${J_GUEST_IP:?itf_journey_stage_from_template must run first}"
    local vb=/usr/local/lib/zfsutilities

    # --- The upgrade premise: active version strictly older than the
    # tree under test.  sort -V decides "older": the premise holds when
    # the active version is the strictly smaller of the two (a rebuilt
    # template carrying the tree's own version makes them equal and
    # fails here).
    local active_version target_version repo_root
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    active_version="$(itf_guest_exec "$guest_ip" \
        'basename "$(readlink /usr/local/lib/zfsutilities/current)"')" || active_version=""
    if [[ -n "$active_version" ]]; then
        itf_step pass "old version deployed" \
            "template clone runs $active_version (current symlink)"
    else
        itf_step fail "old version deployed" "cannot read the current symlink"
        return 1
    fi

    repo_root="$ITF_ROOT/../.."
    if [[ "$ITF_SW_SOURCE" == "dev-tarball" ]]; then
        target_version="$(cat "$repo_root/VERSION" 2>/dev/null || true)"
    else
        target_version="$(curl -fsS --max-time 30 \
            "https://api.github.com/repos/${ITF_GITHUB_REPO}/releases/latest" \
            | awk -F'"' '/tag_name/{print $4; exit}' | sed 's/^v//')" || target_version=""
    fi
    if [[ -z "$target_version" ]]; then
        itf_step fail "new version resolved" \
            "cannot determine the tree-under-test version (sw-source $ITF_SW_SOURCE)"
        return 1
    fi
    local oldest
    oldest="$(printf '%s\n%s\n' "$active_version" "$target_version" \
        | LC_ALL=C sort -V | head -1)"
    if [[ "$active_version" != "$target_version" && "$oldest" == "$active_version" ]]; then
        itf_step pass "upgrade premise holds" \
            "$active_version (deployed) < $target_version (tree under test)"
    else
        itf_step fail "upgrade premise holds" \
            "template carries $active_version, tree under test is $target_version —" \
            "this journey needs the storage template STALE (older than the tree" \
            "under test).  PREP: do NOT rebuild the template; run from a newer" \
            "tree, or point ITF_SW_SOURCE at the latest release"
        return 1
    fi

    # --- The user's download: the tree under test lands in
    # /root/ZFSutilities; the upgrader runs from it.
    itf_journey_stage_download "$guest_ip" || return 1

    # --- The change-scan baseline for the OLD version.  With no
    # MANIFEST.sha256 (deployments older than 0.125.0), the scan needs
    # the active version's release tarball — and many released versions
    # were never tagged on GitHub (0.118.0 among them: the default tag
    # URL 404s; FINDINGS F-025).  When the tag is missing, capture the
    # guest's as-deployed active tree (pristine by construction —
    # nothing has touched it yet) and serve it via the documented
    # ZFSUTILITIES_TAG_TARBALL_URL override, the way an operator with
    # the original tree would.
    local tag_url
    tag_url="https://github.com/${ITF_GITHUB_REPO}/archive/refs/tags/v${active_version}.tar.gz"
    local tag_http="" pristine_env="" api_env=""
    tag_http="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -L \
        "$tag_url" 2>/dev/null)" || tag_http=""
    local dev_ip="" serve_dir=""
    if [[ "$tag_http" == "200" ]]; then
        itf_step pass "change-scan baseline available" \
            "GitHub has the v$active_version tag tarball — no override needed"
    else
        dev_ip="$(itf_dev_ip)"
        if [[ -z "$dev_ip" ]]; then
            itf_step fail "change-scan baseline available" \
                "v$active_version untagged on GitHub and ITF_DEV_IP unset" \
                "(cannot serve the captured pristine tree)"
            return 1
        fi
        serve_dir="$ITF_RUN_DIR/serve"
        mkdir -p "$serve_dir"
        # docs/site is excluded from change scans anyway; leaving it out
        # keeps the pull small.  One top-level dir = release-tarball
        # shape, which the upgrade's extractor requires.
        if ! itf_guest_exec "$guest_ip" \
                "tar -czf /root/itf-pristine-$active_version.tar.gz \
                    --exclude='$active_version/docs/site' \
                    -C $vb/versions '$active_version'" \
                > "$ITF_RUN_DIR/guest-pristine-pack.log" 2>&1 \
            || ! itf_guest_get "$guest_ip" "/root/itf-pristine-$active_version.tar.gz" \
                "$serve_dir/pristine-$active_version.tar.gz" \
                > "$ITF_RUN_DIR/guest-pristine-pull.log" 2>&1; then
            itf_step fail "change-scan baseline available" \
                "pristine capture/pull failed — see guest-pristine-{pack,pull}.log"
            return 1
        fi
        # %s is where the upgrade substitutes the version (upgrade-lib's
        # ZFSUTILITIES_TAG_TARBALL_URL template).
        local pristine_url
        pristine_url="http://${dev_ip}:${ITF_HTTP_PORT}/pristine-%s.tar.gz"
        pristine_env="ZFSUTILITIES_TAG_TARBALL_URL=${pristine_url}"
        itf_step pass "change-scan baseline available" \
            "v$active_version untagged on GitHub — serving the captured" \
            "as-deployed tree via ZFSUTILITIES_TAG_TARBALL_URL"
    fi

    # --- The itf HTTP server, up when anything must be served —
    # dev-tarball mode always ("latest release" for the upgrade target:
    # latest.json + a release-shaped tarball of the current dev tree);
    # release mode only when the pristine override above is active.
    local tarball
    local upgrade_cmd="cd /root/ZFSutilities && ./bin/upgrade-zfsutilities"
    if [[ "$ITF_SW_SOURCE" == "dev-tarball" ]]; then
        if [[ -z "$dev_ip" ]]; then
            dev_ip="$(itf_dev_ip)"
            if [[ -z "$dev_ip" ]]; then
                itf_step fail "served release ready" "set ITF_DEV_IP in the site config"
                return 1
            fi
        fi
        serve_dir="$ITF_RUN_DIR/serve"
        mkdir -p "$serve_dir"
        tarball="$serve_dir/zfsutilities-$target_version.tar.gz"
        # Release shape: exactly one top-level directory (GitHub tarball
        # layout) — upgrade_lib_extract_tarball rejects anything else.
        # Same exclude set as itf_journey_stage_download's dev tarball.
        if ! tar -czf "$tarball" -C "$repo_root" \
                --exclude=.git \
                --exclude=.zcode \
                --exclude=docs/site \
                --exclude=tests/integrated/cache \
                --exclude=tests/integrated/results \
                --exclude=tests/integrated/site/config \
                --exclude=__pycache__ \
                --exclude='*.pyc' \
                --transform="s@^\.@zfsutilities-$target_version@" \
                . 2> "$ITF_RUN_DIR/dev-tarball.log"; then
            itf_step fail "served release ready" \
                "dev tarball build failed (see dev-tarball.log)"
            return 1
        fi
        # The fields upgrade-zfsutilities reads: tag_name (the version),
        # html_url (release notes link), tarball_url (the download).
        cat > "$serve_dir/latest.json" <<EOF
{
  "tag_name": "v$target_version",
  "html_url": "http://${dev_ip}:${ITF_HTTP_PORT}/",
  "tarball_url": "http://${dev_ip}:${ITF_HTTP_PORT}/zfsutilities-$target_version.tar.gz"
}
EOF
    elif [[ -z "$serve_dir" ]]; then
        itf_step info "served release ready" \
            "release source with a tagged baseline: the guest talks to real" \
            "GitHub — no override, no server"
    fi
    if [[ -n "$serve_dir" ]]; then
        # Abort paths must not leak the server onto the port: the trap
        # outlives the stages (J_PIDFILE2 is cleared once stopped).
        _journey_upgrade_exit_cleanup() {
            [[ -n "${J_PIDFILE:-}" ]] && itf_http_stop "$J_PIDFILE"
            [[ -n "${J_PIDFILE2:-}" ]] && itf_http_stop "$J_PIDFILE2"
            # An EXIT-trap handler must not end in failure: under the
            # driver's set -e, a false [[ ]] guard as the last command
            # rewrites a successful run's exit code to 1.
            return 0
        }
        J_PIDFILE2="$ITF_RUN_DIR/http-upgrade.pid"
        if ! itf_http_serve "$serve_dir" "$J_PIDFILE2"; then
            itf_step fail "served release ready" \
                "port $ITF_HTTP_PORT unavailable — see $ITF_RUN_DIR/http-upgrade.log"
            J_PIDFILE2=""
            return 1
        fi
        trap _journey_upgrade_exit_cleanup EXIT
        # Probe what we serve before spending the run on it — same
        # rationale as the preseed probe in stage_os.
        local probe_ok=0 probe_url
        for probe_url in \
            "http://127.0.0.1:${ITF_HTTP_PORT}/latest.json" \
            "http://127.0.0.1:${ITF_HTTP_PORT}/zfsutilities-$target_version.tar.gz" \
            "http://127.0.0.1:${ITF_HTTP_PORT}/pristine-$active_version.tar.gz"; do
            [[ -f "$serve_dir/$(basename "$probe_url")" ]] || continue
            curl -fsS --max-time 10 -o /dev/null "$probe_url" || probe_ok=1
        done
        if (( probe_ok == 0 )); then
            local served_what="pristine v$active_version baseline"
            [[ "$ITF_SW_SOURCE" == "dev-tarball" ]] \
                && served_what="latest.json + v$target_version tarball + $served_what"
            itf_step pass "served release ready" \
                "$served_what at http://${dev_ip}:${ITF_HTTP_PORT}/"
        else
            itf_step fail "served release ready" "probe fetch failed"
            itf_http_stop "$J_PIDFILE2"
            J_PIDFILE2=""
            return 1
        fi
    fi
    # Env assignments sit on the upgrader invocation itself: a prefix on
    # the leading cd would apply only to the cd.
    local env_exports=""
    if [[ "$ITF_SW_SOURCE" == "dev-tarball" ]]; then
        api_env="ZFSUTILITIES_RELEASE_API=http://${dev_ip}:${ITF_HTTP_PORT}/latest.json"
        upgrade_cmd="cd /root/ZFSutilities && $api_env${pristine_env:+ $pristine_env}"
        upgrade_cmd+=" ./bin/upgrade-zfsutilities"
    elif [[ -n "$pristine_env" ]]; then
        upgrade_cmd="cd /root/ZFSutilities && $pristine_env ./bin/upgrade-zfsutilities"
    fi
    local ev
    for ev in $api_env $pristine_env; do
        [[ -n "$ev" ]] || continue
        env_exports+="export ${ev%%=*}=\"${ev#*=}\""$'\n'
    done

    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_ACTIVE_VERSION="$active_version"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_TARGET_VERSION="$target_version"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_UPGRADE_CMD="$upgrade_cmd"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_UPGRADE_ENV_EXPORTS="$env_exports"
    return 0
}

# itf_vmos_image_zvol <s_ip> <zvol-dataset>
#
# Writes the cached VM-OS image (lib/vmos-lib.sh builds it once) onto a
# product-created zvol from the STORAGE guest: the gzipped raw image is
# pushed into the guest and decompressed straight onto /dev/zvol/<zvol>
# with conv=sparse (zero blocks become holes — the sparse zvol stays
# thin on the small test pools).  The OS then lives on the block device
# the product exported, exactly as in production; VM boot + agent
# helpers live just below.
itf_vmos_image_zvol() {
    local s_ip="$1" zvol="$2"
    local gz="$ITF_CACHE_DIR/itf-vmos.raw.gz"
    if [[ ! -s "$gz" ]]; then
        itf_step fail "VM-OS image available" \
            "no cached image at $gz — PREP: itf vmimage build"
        return 1
    fi
    itf_step info "VM-OS image available" "$(du -h "$gz" | awk '{print $1}') cached image"
    # shellcheck disable=SC2016  # the $ expansions run in the guest
    if itf_guest_put "$s_ip" "$gz" /root/itf-vmos.raw.gz > /dev/null 2>&1 \
        && itf_guest_exec "$s_ip" "
            set -e
            [[ -b /dev/zvol/$zvol ]]
            gunzip -dc /root/itf-vmos.raw.gz | dd of=/dev/zvol/$zvol bs=4M conv=sparse status=none
            sync
            rm -f /root/itf-vmos.raw.gz
        " > "$ITF_RUN_DIR/vmos-image-zvol.log" 2>&1; then
        itf_step pass "VM-OS image written to zvol" \
            "/dev/zvol/$zvol (sparse dd; OS rides the product-created LUN)"
    else
        itf_step fail "VM-OS image written to zvol" "see vmos-image-zvol.log"
        return 1
    fi
    return 0
}

# --- Running-VM workload helpers (recovery-scenario campaign) ---
#
# The workload VM boots the cached VM-OS image from its iSCSI LUN; every
# helper below drives it ON THE COMPUTE GUEST through `qm` — the same
# channel an operator's PVE uses — with the qemu guest agent as the only
# in-VM channel (no ssh into the workload VM).  The writer appends a
# timestamp to /workload.log on the LUN-backed root filesystem and syncs
# every tick, so an iSCSI outage stalls it exactly where production
# would: on writeback to the LUN.

# itf_vm_wait_agent <c_ip> <vmid> [timeout-seconds]
#
# Polls the workload VM's guest agent on the compute guest until it
# answers.  The agent-RPC form is `qm agent <vmid> ping` — PVE 9 has no
# `qm guest ping` (qm guest only wraps exec/file-*).  TCG boots are
# slow; keep the default generous.
itf_vm_wait_agent() {
    local c_ip="$1" vmid="$2" timeout="${3:-900}"
    local deadline=$(( SECONDS + timeout ))
    while (( SECONDS < deadline )); do
        if itf_guest_exec "$c_ip" "qm agent $vmid ping" > /dev/null 2>&1; then
            return 0
        fi
        sleep 5
    done
    return 1
}

# itf_vm_boot_with_agent <c_ip> <vmid> [timeout-seconds]
#
# Idempotent boot gate for the workload VM: enable the agent channel,
# force TCG (the lab's nested PVE has no /dev/kvm passthrough — the
# established boot-proof pattern), start, and require the agent to
# answer before the caller proceeds.
itf_vm_boot_with_agent() {
    local c_ip="$1" vmid="$2" timeout="${3:-900}"
    if itf_guest_exec "$c_ip" "qm set $vmid --agent enabled=1 --kvm 0" \
            > "$ITF_RUN_DIR/vm-$vmid-agent.log" 2>&1 \
        && itf_guest_exec "$c_ip" "qm start $vmid" \
            >> "$ITF_RUN_DIR/vm-$vmid-agent.log" 2>&1; then
        itf_step info "VM $vmid starting" "agent channel on, TCG, boot in progress"
    else
        itf_step fail "VM $vmid starting" "see vm-$vmid-agent.log"
        return 1
    fi
    if itf_vm_wait_agent "$c_ip" "$vmid" "$timeout"; then
        itf_step pass "VM $vmid agent ready" "qm guest ping answered (TCG boot)"
    else
        itf_step fail "VM $vmid agent ready" \
            "no agent answer within ${timeout}s — see vm-$vmid-agent.log"
        return 1
    fi
    return 0
}

# _itf_vm_exec_out <raw-qm-guest-exec-output>
#
# Extracts the output payload from a `qm guest exec` result.  qm prints
# a pretty-printed JSON dict whose payload key is "out-data" (live-proven
# on PVE 9.2.21); older/mock shapes may use "out".  python's
# ast.literal_eval parses both the JSON and python-repr quoting shapes.
_itf_vm_exec_out() {
    python3 -c '
import ast, sys
raw = sys.stdin.read().strip()
try:
    data = ast.literal_eval(raw)
except (ValueError, SyntaxError):
    sys.exit(1)
if isinstance(data, dict):
    sys.stdout.write(data.get("out-data", data.get("out", "")))
' 2>/dev/null
}

# itf_vm_workload_start <c_ip> <vmid>
#
# Starts the detached 1 Hz timestamp writer on the workload VM's
# LUN-backed root filesystem.  nohup + & inside the guest-exec'd shell
# detaches it from the agent call, which returns immediately.
itf_vm_workload_start() {
    local c_ip="$1" vmid="$2"
    local inner='while :; do date +%s >> /workload.log; sync; sleep 1; done'
    if itf_guest_exec "$c_ip" \
        "qm guest exec $vmid -- sh -c 'nohup sh -c \"$inner\" >/dev/null 2>&1 &'" \
        > "$ITF_RUN_DIR/vm-$vmid-workload-start.log" 2>&1; then
        itf_step pass "workload writer started [VM $vmid]" \
            "1 Hz timestamps to /workload.log with per-tick sync"
    else
        itf_step fail "workload writer started [VM $vmid]" \
            "see vm-$vmid-workload-start.log"
        return 1
    fi
}

# itf_vm_workload_sample <c_ip> <vmid>
#
# Echoes the workload log's current content (clean timestamps, one per
# line) on stdout for the caller to save/parse.  rc 1 when the agent
# channel fails (VM down or agent gone — itself a scenario signal, the
# caller decides).
itf_vm_workload_sample() {
    local c_ip="$1" vmid="$2"
    local raw
    raw="$(itf_guest_exec "$c_ip" \
        "qm guest exec $vmid -- cat /workload.log" 2>/dev/null)" || return 1
    printf '%s' "$raw" | _itf_vm_exec_out
}

# itf_vm_workload_checksum <c_ip> <vmid>
#
# Echoes `cksum /workload.log` from inside the workload VM (before/after
# comparisons around an event prove no silent corruption).  rc 1 when
# the agent channel fails.
itf_vm_workload_checksum() {
    local c_ip="$1" vmid="$2"
    local raw
    raw="$(itf_guest_exec "$c_ip" \
        "qm guest exec $vmid -- cksum /workload.log" 2>/dev/null)" || return 1
    printf '%s' "$raw" | _itf_vm_exec_out
}

# itf_vm_workload_stop <c_ip> <vmid>
#
# Stops the writer (idempotent; no match is fine — the VM may be down).
itf_vm_workload_stop() {
    local c_ip="$1" vmid="$2"
    itf_guest_exec "$c_ip" \
        "qm guest exec $vmid -- pkill -f workload.log" > /dev/null 2>&1 || true
}

# itf_vm_workload_gaps <sample-file> [threshold-seconds=5]
#
# Pure parser over a saved sample (one epoch timestamp per line, as
# itf_vm_workload_sample emits): echoes "samples=<n> max_gap=<s>" and
# returns 1 when no timestamps parsed.  A max_gap above the threshold is
# the stall signal; the caller asserts.
itf_vm_workload_gaps() {
    local sample="$1" threshold="${2:-5}"
    python3 - "$sample" "$threshold" <<'PYEOF'
import sys

path, threshold = sys.argv[1], float(sys.argv[2])
try:
    with open(path) as f:
        ts = [float(line) for line in f if line.strip()]
except (OSError, ValueError):
    sys.exit(1)
if len(ts) < 2:
    print(f"samples={len(ts)} max_gap=0.0")
    sys.exit(0)
gaps = [b - a for a, b in zip(ts, ts[1:])]
print(f"samples={len(ts)} max_gap={max(gaps):.1f}")
PYEOF
}

# itf_reboot_guest_begin <gname> <role> [--power]
#
# Issues the disruptive half for the role's staged guest and returns
# immediately; itf_reboot_guest_wait brings the guest back.  Splitting
# the two lets a journey observe peer-node fallout INSIDE the outage
# window (j15's S1b samples the compute node between begin and wait).
# Default is the in-guest `reboot` over ssh (rc 255 from the dropping
# connection is the expected success shape); --power models a power
# event's down-stroke instead (guarded shutdown here, start in the
# wait).  The chosen mode is remembered in reboot-mode-<role> for the
# wait half.
itf_reboot_guest_begin() {
    local gname="$1" role="$2"
    shift 2
    local power=0
    while (( $# > 0 )); do
        case "$1" in
            --power) power=1; shift ;;
            *) echo "itf: unknown itf_reboot_guest_begin option: $1" >&2; return 2 ;;
        esac
    done

    local guest_file="$ITF_RUN_DIR/guest-${role}.txt"
    if [[ ! -f "$guest_file" ]]; then
        itf_step fail "guest record present [$role]" \
            "no $guest_file — stage the lab first"
        return 1
    fi
    local base vmid old_ip
    read -r base vmid old_ip < "$guest_file" || {
        itf_step fail "guest record present [$role]" "malformed $guest_file"
        return 1
    }

    if (( power )); then
        if itf_guest_stop "$base" "$vmid" \
                > "$ITF_RUN_DIR/reboot-${gname}.log" 2>&1; then
            itf_step pass "guest powered off [$role]" \
                "vmid $vmid: guarded shutdown (start comes with the wait)"
        else
            itf_step fail "guest powered off [$role]" "see reboot-${gname}.log"
            return 1
        fi
        echo power > "$ITF_RUN_DIR/reboot-mode-${role}"
        return 0
    fi

    # The ssh session dies with the guest: rc 255 is the drop, not a
    # failure.  Any other rc means the command itself failed.
    itf_guest_exec "$old_ip" "reboot" \
        > "$ITF_RUN_DIR/reboot-${gname}.log" 2>&1
    local reboot_rc=$?
    if [[ $reboot_rc -eq 0 || $reboot_rc -eq 255 ]]; then
        itf_step pass "guest rebooted [$role]" "in-guest reboot issued (vmid $vmid)"
    else
        itf_step fail "guest rebooted [$role]" \
            "rc=$reboot_rc — see reboot-${gname}.log"
        return 1
    fi
    echo inguest > "$ITF_RUN_DIR/reboot-mode-${role}"
    return 0
}

# itf_reboot_guest_wait <gname> <role> [--timeout N]
#
# The return half of itf_reboot_guest_begin: start the guest back up on
# a --power begin, wait for ssh on the old address, re-discover the IP
# via the guest agent when DHCP re-leased a different one, rewrite the
# guest-<role>.txt record, and refresh J_GUEST_IP — callers must
# re-read coordinates (or use J_GUEST_IP) after any disruptive stage.
itf_reboot_guest_wait() {
    local gname="$1" role="$2"
    shift 2
    local timeout=900
    while (( $# > 0 )); do
        case "$1" in
            --timeout) timeout="$2"; shift 2 ;;
            *) echo "itf: unknown itf_reboot_guest_wait option: $1" >&2; return 2 ;;
        esac
    done

    local mode="inguest"
    local mode_file="$ITF_RUN_DIR/reboot-mode-${role}"
    [[ -f "$mode_file" ]] && read -r mode < "$mode_file"
    rm -f "$mode_file"

    local guest_file="$ITF_RUN_DIR/guest-${role}.txt"
    local base vmid old_ip
    read -r base vmid old_ip < "$guest_file" || {
        itf_step fail "guest record present [$role]" "malformed $guest_file"
        return 1
    }

    if [[ "$mode" == power ]]; then
        if itf_guest_start "$base" "$vmid" \
                >> "$ITF_RUN_DIR/reboot-${gname}.log" 2>&1; then
            itf_step pass "guest powered on [$role]" "vmid $vmid"
        else
            itf_step fail "guest powered on [$role]" "see reboot-${gname}.log"
            return 1
        fi
    else
        # In-guest mode: the reboot takes seconds to reach sshd.  Wait
        # for ssh to GO AWAY first — waiting only for the return races
        # the shutdown window (a first probe can hit still-alive sshd
        # mid-shutdown and "succeed" against the dying boot).
        local gone=$(( SECONDS + "${ITF_REBOOT_GONE_WAIT:-180}" ))
        until (( SECONDS >= gone )); do
            itf_guest_exec "$old_ip" "true" > /dev/null 2>&1 || break
            sleep "${ITF_REBOOT_POLL:-5}"
        done
        if itf_guest_exec "$old_ip" "true" > /dev/null 2>&1; then
            itf_step fail "guest went down [$role]" \
                "ssh still up ${ITF_REBOOT_GONE_WAIT:-180}s after the reboot — did it reboot?"
            return 1
        fi
        itf_step pass "guest went down [$role]" "ssh dropped after the reboot"
    fi

    if itf_wait_ssh "$old_ip" "$timeout"; then
        itf_step pass "guest ssh reachable [$role]" "$old_ip (address kept)"
        # shellcheck disable=SC2034  # consumed by the journey scripts
        J_GUEST_IP="$old_ip"
        return 0
    fi

    # DHCP may have re-leased a different address during the reboot.
    local new_ip
    new_ip="$(itf_guest_ip "$base" "$vmid" 600)"
    if [[ -z "$new_ip" ]]; then
        itf_step fail "guest ssh reachable [$role]" \
            "ssh never returned on $old_ip and the agent reports no address"
        return 1
    fi
    if ! itf_wait_ssh "$new_ip" 300; then
        itf_step fail "guest ssh reachable [$role]" \
            "neither $old_ip nor rediscovered $new_ip answers ssh"
        return 1
    fi
    echo "$base $vmid $new_ip" > "$guest_file"
    itf_step pass "guest ssh reachable [$role]" \
        "address re-leased during reboot: $old_ip -> $new_ip (record updated)"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_GUEST_IP="$new_ip"
    return 0
}

# itf_journey_stage_reboot_guest <gname> <role> [--power] [--timeout N]
#
# Reboots the role's staged guest and brings its coordinates back in one
# call (in-guest `reboot`; --power = guarded stop/start power cycle).
# Composed of itf_reboot_guest_begin + itf_reboot_guest_wait; callers
# that need the outage window open call those two directly.
itf_journey_stage_reboot_guest() {
    local gname="$1" role="$2"
    shift 2
    local power=0 timeout=900
    while (( $# > 0 )); do
        case "$1" in
            --power) power=1; shift ;;
            --timeout) timeout="$2"; shift 2 ;;
            *) echo "itf: unknown itf_journey_stage_reboot_guest option: $1" >&2; return 2 ;;
        esac
    done
    local -a begin_args=("$gname" "$role")
    (( power )) && begin_args+=(--power)
    itf_reboot_guest_begin "${begin_args[@]}" || return 1
    itf_reboot_guest_wait "$gname" "$role" --timeout "$timeout" || return 1
    return 0
}

# --- LUKS key-device lab (recovery-scenario campaign) ---
#
# Models production's removable LUKS key store on the STORAGE guest: a
# small dedicated disk (scsi2, hot-plugged like the pool disk) is
# LUKS-formatted in the guest, carries an ext4 filesystem labeled
# ZFSkeys with the per-pool key file at the conventional path, and the
# guest's fstab gains the production mount line (noauto — the operator
# mounts manually; the lab never resurrects the removed unlock
# automation).  "Insert the USB" = re-attach the captured volume +
# luksOpen + mount; "remove it" = umount + luksClose + detach.
#
# The passphrase reaches cryptsetup through stdin (--key-file -) piped
# from a mode-600 run-dir feed file: never in argv, never in a command
# string, never in a step message or log.

# _itf_keystore_feed
#
# Echoes the path of the passphrase feed file, (re)written from the
# site config without a trailing newline so luksFormat and every later
# luksOpen see identical key bytes.
_itf_keystore_feed() {
    local feed="$ITF_RUN_DIR/keystore-passphrase"
    printf '%s' "$ITF_KEYSTORE_PASSPHRASE" > "$feed"
    chmod 600 "$feed"
    echo "$feed"
}

# _itf_keystore_config_ok
#
# Fails with a PREP hint when the site config lacks the keystore pair
# (the encrypted-key lab is opt-in; sites that never run it leave the
# keys unset, which config validation accepts).
_itf_keystore_config_ok() {
    if [[ -z "${ITF_KEYSTORE_PASSPHRASE:-}" || -z "${ITF_KEYFILE_NAME:-}" ]]; then
        itf_step fail "keystore site config" \
            "ITF_KEYSTORE_PASSPHRASE + ITF_KEYFILE_NAME required — PREP:" \
            "set them in tests/integrated/site/config (see config.example)"
        return 1
    fi
    return 0
}

# _itf_keystore_wait_sdc <s_ip>
#
# Bounded wait for the key device node inside the storage guest (scsi0
# system, scsi1 pool disk — the key device is the third disk, /dev/sdc).
_itf_keystore_wait_sdc() {
    local s_ip="$1"
    # shellcheck disable=SC2016  # expansion runs in the guest
    itf_guest_exec "$s_ip" '
        for i in $(seq 1 30); do lsblk -dn -o NAME | grep -qx sdc && exit 0; sleep 2; done
        exit 1
    '
}

# itf_keystore_provision <s_base> <s_vmid> <s_ip>
#
# Creates the key device: attach a 1G scsi2 volume, capture its volid
# for later re-attach, LUKS-format whole-disk, mkfs.ext4 labeled
# ZFSkeys, mount at /mnt/ZFSkeys, write the 0400 key file, add the
# production fstab line.  Leaves the store MOUNTED (the caller creates
# the encrypted LUN next); lock with itf_keystore_lock_umount.
itf_keystore_provision() {
    local s_base="$1" s_vmid="$2" s_ip="$3"
    _itf_keystore_config_ok || return 1

    local tool_log="$ITF_RUN_DIR/keystore-cryptsetup.log"
    if itf_guest_exec "$s_ip" \
            "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cryptsetup" \
            > "$tool_log" 2>&1; then
        itf_step pass "cryptsetup installed" "storage guest (LUKS tooling)"
    else
        itf_step fail "cryptsetup installed" "see keystore-cryptsetup.log"
        return 1
    fi

    if itf_qm "$s_base" set "$s_vmid" --scsi2 "${ITF_GUEST_STORAGE}:1" \
            > "$ITF_RUN_DIR/keystore-attach.log" 2>&1 \
        && _itf_keystore_wait_sdc "$s_ip" > /dev/null 2>&1; then
        itf_step pass "key device attached" \
            "scsi2 (1G) hot-plugged, storage guest sees /dev/sdc"
    else
        itf_step fail "key device attached" "see keystore-attach.log"
        return 1
    fi

    # Capture the volume for itf_keystore_insert re-attaches.
    itf_qm "$s_base" config "$s_vmid" 2>/dev/null \
        | sed -n 's/^scsi2:[[:space:]]*//p' | head -1 | cut -d, -f1 \
        > "$ITF_RUN_DIR/keystore-volid.txt"
    if [[ -s "$ITF_RUN_DIR/keystore-volid.txt" ]]; then
        itf_step pass "key device volume captured" \
            "$(cat "$ITF_RUN_DIR/keystore-volid.txt") (re-attach identity)"
    else
        itf_step fail "key device volume captured" "no scsi2 line in guest config"
        return 1
    fi

    local feed
    feed="$(_itf_keystore_feed)"
    if itf_guest_exec_feed "$s_ip" "$feed" \
            "cryptsetup luksFormat --batch-mode --key-file - /dev/sdc" \
            > "$ITF_RUN_DIR/keystore-format.log" 2>&1; then
        itf_step pass "key device LUKS-formatted" \
            "/dev/sdc (passphrase via stdin, never in argv)"
    else
        itf_step fail "key device LUKS-formatted" "see keystore-format.log"
        return 1
    fi

    local key_path="/mnt/ZFSkeys/keys/${ITF_KEYFILE_NAME}"
    if ! itf_guest_exec_feed "$s_ip" "$feed" \
            "cryptsetup luksOpen --key-file - /dev/sdc keys" \
            > "$ITF_RUN_DIR/keystore-open.log" 2>&1; then
        itf_step fail "key device opened" "see keystore-open.log"
        return 1
    fi
    # shellcheck disable=SC2029  # expansions run on the storage guest
    if itf_guest_exec "$s_ip" "
            set -e
            mkfs.ext4 -q -L ZFSkeys /dev/mapper/keys
            mkdir -p /mnt/ZFSkeys
            mount /dev/mapper/keys /mnt/ZFSkeys
            mkdir -p /mnt/ZFSkeys/keys
            dd if=/dev/urandom of=${key_path} bs=32 count=1 status=none
            chmod 400 ${key_path}
            grep -q 'LABEL=ZFSkeys /mnt/ZFSkeys' /etc/fstab \\
                || echo 'LABEL=ZFSkeys /mnt/ZFSkeys auto nosuid,nodev,nofail,x-gvfs-show,noauto 0 0' >> /etc/fstab
            test -s ${key_path}
        " > "$ITF_RUN_DIR/keystore-mkfs.log" 2>&1; then
        itf_step pass "ZFSkeys store provisioned" \
            "ext4 labeled ZFSkeys; ${key_path} (0400); production fstab line"
    else
        itf_step fail "ZFSkeys store provisioned" "see keystore-mkfs.log"
        return 1
    fi
    return 0
}

# itf_keystore_insert <s_base> <s_vmid>
#
# Re-attaches the captured key-device volume ("insert the USB").
itf_keystore_insert() {
    local s_base="$1" s_vmid="$2"
    local volid
    volid="$(cat "$ITF_RUN_DIR/keystore-volid.txt" 2>/dev/null)"
    if [[ -z "$volid" ]]; then
        itf_step fail "key device inserted" \
            "no captured volid — provision the keystore first"
        return 1
    fi
    if itf_qm "$s_base" set "$s_vmid" --scsi2 "$volid" \
            > "$ITF_RUN_DIR/keystore-insert.log" 2>&1; then
        itf_step pass "key device inserted" "$volid re-attached as scsi2"
    else
        itf_step fail "key device inserted" "see keystore-insert.log"
        return 1
    fi
}

# itf_keystore_remove <s_base> <s_vmid>
#
# Detaches the key-device volume ("remove the USB"); the volume stays on
# the itf guest storage for the next insert and is destroyed with the
# guest.
itf_keystore_remove() {
    local s_base="$1" s_vmid="$2"
    if itf_qm "$s_base" set "$s_vmid" --delete scsi2 \
            > "$ITF_RUN_DIR/keystore-remove.log" 2>&1; then
        itf_step pass "key device removed" "scsi2 detached (volume kept for re-insert)"
    else
        itf_step fail "key device removed" "see keystore-remove.log"
        return 1
    fi
}

# itf_keystore_unlock_mount <s_ip>
#
# The operator's blind-recovery step: luksOpen (passphrase via stdin)
# and mount the store; verifies the key file is visible at the
# conventional path.
itf_keystore_unlock_mount() {
    local s_ip="$1"
    _itf_keystore_wait_sdc "$s_ip" > /dev/null 2>&1
    local feed
    feed="$(_itf_keystore_feed)"
    if ! itf_guest_exec_feed "$s_ip" "$feed" \
            "cryptsetup luksOpen --key-file - /dev/sdc keys" \
            > "$ITF_RUN_DIR/keystore-unlock.log" 2>&1; then
        itf_step fail "key store unlocked" "see keystore-unlock.log"
        return 1
    fi
    local key_path="/mnt/ZFSkeys/keys/${ITF_KEYFILE_NAME}"
    # shellcheck disable=SC2029  # expansions run on the storage guest
    if itf_guest_exec "$s_ip" "
            set -e
            mkdir -p /mnt/ZFSkeys
            mount /dev/mapper/keys /mnt/ZFSkeys
            test -s ${key_path}
        " > "$ITF_RUN_DIR/keystore-mount.log" 2>&1; then
        itf_step pass "key store unlocked + mounted" \
            "/dev/mapper/keys on /mnt/ZFSkeys; ${key_path} visible"
    else
        itf_step fail "key store unlocked + mounted" "see keystore-mount.log"
        return 1
    fi
}

# itf_keystore_lock_umount <s_ip>
#
# The operator's lock step after keys are loaded: umount + luksClose.
itf_keystore_lock_umount() {
    local s_ip="$1"
    # shellcheck disable=SC2016  # expansions run in the guest
    if itf_guest_exec "$s_ip" '
            umount /mnt/ZFSkeys
            cryptsetup luksClose keys
        ' > "$ITF_RUN_DIR/keystore-lock.log" 2>&1; then
        itf_step pass "key store locked + unmounted" \
            "production posture after key load (device can be removed)"
    else
        itf_step fail "key store locked + unmounted" "see keystore-lock.log"
        return 1
    fi
}

# itf_journey_stage_encrypted_key_lun <gname> <s_base> <s_vmid> <s_ip> <c_ip>
#
# The opt-in encrypted-key tail of the two-node lab: provision the LUKS
# keystore, create the ENCRYPTED vm-101-disk-1 through the product (the
# compute-side new-vm-disk re-executes on storage, where the key-path
# prompt reads the piped answer), verify the encrypted-LUN registration
# and the loaded-key posture with the store locked, and snapshot
# enc-lab-ready on the storage guest.
itf_journey_stage_encrypted_key_lun() {
    local gname="$1" s_base="$2" s_vmid="$3" s_ip="$4" c_ip="$5"
    local pool="zfstest1" key_path="/mnt/ZFSkeys/keys/${ITF_KEYFILE_NAME}"

    itf_keystore_provision "$s_base" "$s_vmid" "$s_ip" || return 1

    # Fresh-host staging: install-two-node seeds this conf from the
    # site-specific sample (production entries by design); a fresh lab
    # host has no encrypted LUNs yet, and the sample's vm-101-disk-1
    # entry collides with the lab's own backstore name — new-vm-disk's
    # prefix-only registration check would then skip the real entry
    # (FINDINGS F-027).  Reset to empty; the product writes its own
    # line right below.
    if itf_guest_exec "$s_ip" \
            ": > /etc/zfsutilities/iscsi-encrypted-luns.conf" \
            > "$ITF_RUN_DIR/keystore-conf-reset.log" 2>&1; then
        itf_step pass "encrypted-luns conf reset (fresh host)" \
            "installer-seeded sample entries cleared; the product writes its own"
    else
        itf_step fail "encrypted-luns conf reset (fresh host)" \
            "see keystore-conf-reset.log"
        return 1
    fi

    local answers="$ITF_RUN_DIR/new-vm-disk-encrypted-answers.txt"
    printf '%s\n' "$key_path" > "$answers"
    local disk_log="$ITF_RUN_DIR/new-vm-disk-encrypted.log"
    itf_guest_exec_feed "$c_ip" "$answers" \
        "bash -lc 'new-vm-disk $pool 101 1 4G --encrypted'" \
        > "$disk_log" 2>&1
    local disk_rc=$?
    itf_artifact "new-vm-disk-encrypted" "$disk_log"
    if [[ $disk_rc -eq 0 ]] \
            && grep -q "✓ Configuration saved" "$disk_log" \
            && itf_guest_exec "$c_ip" \
                "grep -q '^scsi1: /dev/disk/by-path/' /etc/pve/qemu-server/101.conf"; then
        itf_step pass "encrypted LUN created" \
            "vm-101-disk-1 (4G) through new-vm-disk --encrypted; scsi1 line written"
    else
        itf_step fail "encrypted LUN created" \
            "rc=$disk_rc — see new-vm-disk-encrypted.log"
        return 1
    fi

    local conf_log="$ITF_RUN_DIR/encrypted-luns-conf.log"
    # The conf must hold EXACTLY the lab entry (plan 022's journey gate):
    # the fresh-host reset models no pre-existing encrypted LUNs, so any
    # second line would be a registration bug (F-027 class).
    # shellcheck disable=SC2029  # expansions run on the storage guest
    if itf_guest_exec "$s_ip" "
            test \"\$(wc -l < /etc/zfsutilities/iscsi-encrypted-luns.conf)\" -eq 1 \\
            && grep -q '^vm-101-disk-1:/dev/zvol/${pool}/proxmox/vm-101-disk-1:${pool}\$' \\
                /etc/zfsutilities/iscsi-encrypted-luns.conf \\
            && zfs get -H -o value keystatus ${pool}/proxmox/vm-101-disk-1 \\
            | grep -qx available
        " > "$conf_log" 2>&1; then
        itf_step pass "encrypted LUN registered + key loaded" \
            "iscsi-encrypted-luns.conf entry; keystatus available"
    else
        itf_step fail "encrypted LUN registered + key loaded" "see encrypted-luns-conf.log"
        return 1
    fi

    # Lock the store FIRST, then re-verify the posture: the key stays
    # loaded with the device gone (the production posture the boot
    # scenarios start from).
    itf_keystore_lock_umount "$s_ip" || return 1
    itf_keystore_remove "$s_base" "$s_vmid" || return 1
    local post_log="$ITF_RUN_DIR/encrypted-posture.log"
    # shellcheck disable=SC2029  # expansions run on the storage guest
    if itf_guest_exec "$s_ip" \
            "zfs get -H -o value keystatus ${pool}/proxmox/vm-101-disk-1" \
            > "$post_log" 2>&1 \
            && grep -qx available "$post_log"; then
        itf_step pass "keys stay loaded with store removed" \
            "keystatus available, key device detached (production posture)"
    else
        itf_step fail "keys stay loaded with store removed" "see encrypted-posture.log"
        return 1
    fi

    if itf_guest_snapshot "$s_base" "$s_vmid" enc-lab-ready > /dev/null 2>&1; then
        itf_step pass "snapshot enc-lab-ready" "encrypted-lab checkpoint on storage"
    else
        itf_step fail "snapshot enc-lab-ready"
    fi
    return 0
}

# --- Boot-and-keys scenario helpers (recovery-scenario campaign G1) ---
#
# The j15 machinery on top of the encrypted two-node lab: product-command
# runners with end-state gates, the operator's key ceremony as one stage,
# boot-journal capture plus a pure order/verdict parser, and the
# compute-side fallout observables (sessions, by-path links, fence ticks,
# workload samples).  Recovery paths consume only user-visible signals
# and documented commands — never injection state.

# itf_new_vm_disk_encrypted <c_ip> <pool> <vmid> <disknum> <size> <key-path> <log-stem>
#
# Runs new-vm-disk --encrypted on the compute guest with the key-path
# prompt answered from a feed file (the G0 stage's pattern), captures the
# transcript under <log-stem>.log, and returns the product's rc.  The
# CALLER owns the step and the end-state gates — success paths assert
# the "✓ Configuration saved" line + the scsiN config line; M1-style
# failure paths assert the FATAL line and that no zvol appeared.
itf_new_vm_disk_encrypted() {
    local c_ip="$1" pool="$2" vmid="$3" disknum="$4" size="$5" key_path="$6" stem="$7"
    local answers="$ITF_RUN_DIR/${stem}-answers.txt"
    printf '%s\n' "$key_path" > "$answers"
    itf_guest_exec_feed "$c_ip" "$answers" \
        "bash -lc 'new-vm-disk $pool $vmid $disknum $size --encrypted'" \
        > "$ITF_RUN_DIR/${stem}.log" 2>&1
    local rc=$?
    itf_artifact "$stem" "$ITF_RUN_DIR/${stem}.log"
    return "$rc"
}

# itf_safe_save_gate <s_ip> <label>
#
# The documented "persist the healthy target config" step with its
# end-state gate: safe-iscsi-save must complete with the clean-pass line.
itf_safe_save_gate() {
    local s_ip="$1" label="$2"
    local log="$ITF_RUN_DIR/safe-iscsi-save-${label}.log"
    itf_guest_exec "$s_ip" "bash -lc 'safe-iscsi-save'" > "$log" 2>&1
    local rc=$?
    itf_artifact "safe-iscsi-save-$label" "$log"
    if [[ $rc -eq 0 ]] && grep -q "✓ iSCSI configuration saved" "$log"; then
        itf_step pass "target config saved [$label]" "clean pass — see $(basename "$log")"
        return 0
    fi
    itf_step fail "target config saved [$label]" \
        "rc=$rc — see $(basename "$log")"
    return 1
}

# itf_iscsi_check_gate <s_ip> <label>
#
# export-iscsi-state --check with its end-state gate: rc 0 plus the
# no-drift line — the stand-in for a healthy Dashboard view.
itf_iscsi_check_gate() {
    local s_ip="$1" label="$2"
    local log="$ITF_RUN_DIR/iscsi-check-${label}.log"
    itf_guest_exec "$s_ip" "bash -lc 'export-iscsi-state --check'" > "$log" 2>&1
    local rc=$?
    itf_artifact "iscsi-check-$label" "$log"
    if [[ $rc -eq 0 ]] && grep -q "✓ No drift" "$log"; then
        itf_step pass "state map check OK [$label]" "live LUNs match the pool map"
        return 0
    fi
    itf_step fail "state map check OK [$label]" "rc=$rc — see $(basename "$log")"
    return 1
}

# itf_storage_load_keys <s_ip> [dataset]
#
# The documented key-loading step: `zfs load-key -a` (the operator's
# form, per zfs-keys.md) or `zfs load-key <dataset>` for one.  With -a
# the exit code is noisy about keys that were already loaded, so success
# is judged the way the operator sees it: every encrypted LUN registered
# in iscsi-encrypted-luns.conf (or the one named dataset) reports
# keystatus available afterwards.
itf_storage_load_keys() {
    local s_ip="$1" dataset="${2:-}"
    local stem="load-keys"
    [[ -n "$dataset" ]] && stem="load-key-$(basename "$dataset")"
    local log="$ITF_RUN_DIR/${stem}.log"
    itf_guest_exec "$s_ip" "bash -lc 'zfs load-key ${dataset:--a}'" > "$log" 2>&1
    local rc=$?
    itf_artifact "$stem" "$log"
    local gate_log="$ITF_RUN_DIR/${stem}-keystatus.log"
    local gate_cmd
    if [[ -n "$dataset" ]]; then
        gate_cmd="test \"\$(zfs get -H -o value keystatus $dataset)\" = available"
    else
        # shellcheck disable=SC2016  # expansions run in the guest
        gate_cmd='missing=0
while read -r ds; do
    st=$(zfs get -H -o value keystatus "$ds")
    echo "$ds: $st"
    [[ $st = available ]] || missing=1
done < <(awk -F: "NF==3 && \$1 !~ /^#/ {sub(/^\/dev\/zvol\//, \"\", \$2); print \$2}" \
    /etc/zfsutilities/iscsi-encrypted-luns.conf)
exit $missing'
    fi
    if { [[ $rc -eq 0 ]] || [[ -z "$dataset" ]]; } \
            && itf_guest_exec "$s_ip" "$gate_cmd" > "$gate_log" 2>&1; then
        itf_step pass "ZFS keys loaded" \
            "zfs load-key ${dataset:--a}; keystatus gates green (see $(basename "$gate_log"))"
        return 0
    fi
    itf_step fail "ZFS keys loaded" \
        "rc=$rc — see $(basename "$log") / $(basename "$gate_log")"
    return 1
}

# itf_keystatus <s_ip> <dataset> <available|unavailable> [label]
#
# Asserts a dataset's keystatus — the user-visible posture signal the
# boot scenarios pivot on.
itf_keystatus() {
    local s_ip="$1" ds="$2" expect="$3"
    local label="${4:-$ds}"
    local log="$ITF_RUN_DIR/keystatus-${label}.log"
    itf_guest_exec "$s_ip" "zfs get -H -o value keystatus $ds" > "$log" 2>&1
    local got
    got="$(tail -n 1 "$log")"
    if [[ "$got" == "$expect" ]]; then
        itf_step pass "keystatus $expect [$label]" "$ds"
        return 0
    fi
    itf_step fail "keystatus $expect [$label]" \
        "$ds reports '$got' — see $(basename "$log")"
    return 1
}

# _itf_keystore_feed_wrong
#
# The wrong-passphrase feed (S4): distinct bytes, same handling rules as
# the real one — mode 600, no trailing newline, never in a command
# string, step message, or log.
_itf_keystore_feed_wrong() {
    local feed="$ITF_RUN_DIR/keystore-passphrase-wrong"
    printf '%s-wrong' "$ITF_KEYSTORE_PASSPHRASE" > "$feed"
    chmod 600 "$feed"
    echo "$feed"
}

# itf_keystore_unlock_mount_wrong <s_ip>
#
# The mistyped-passphrase attempt: luksOpen fed the WRONG bytes must
# fail cleanly and leave no mapper behind.  A zero rc here would mean
# the wrong passphrase opened the store — a hard failure (and the
# mapper gets closed again).
itf_keystore_unlock_mount_wrong() {
    local s_ip="$1"
    _itf_keystore_wait_sdc "$s_ip" > /dev/null 2>&1
    local feed log rc
    feed="$(_itf_keystore_feed_wrong)"
    log="$ITF_RUN_DIR/keystore-unlock-wrong.log"
    itf_guest_exec_feed "$s_ip" "$feed" \
        "cryptsetup luksOpen --key-file - /dev/sdc keys" > "$log" 2>&1
    rc=$?
    itf_artifact "keystore-unlock-wrong" "$log"
    if [[ $rc -eq 0 ]]; then
        itf_step fail "wrong passphrase rejected" \
            "luksOpen SUCCEEDED with wrong bytes — mapper closed, file a finding"
        itf_guest_exec "$s_ip" "cryptsetup luksClose keys" > /dev/null 2>&1 || true
        return 1
    fi
    if itf_guest_exec "$s_ip" "test ! -e /dev/mapper/keys"; then
        itf_step pass "wrong passphrase rejected" \
            "luksOpen failed cleanly, no mapper left behind (see $(basename "$log"))"
        return 0
    fi
    itf_step fail "wrong passphrase rejected" \
        "luksOpen failed but /dev/mapper/keys exists — see $(basename "$log")"
    return 1
}

# itf_key_ceremony <label> <s_base> <s_vmid> <s_ip> [recover|add]
#
# The operator's full key ceremony after a keys-absent boot — the
# documented sequence, blind-recovery shaped: insert the key device,
# luksOpen + mount the store, load the ZFS keys, run
# iscsi-recover-encrypted-luns (default) or iscsi-add-encrypted-luns
# (the zfs-keys.md path), then umount + luksClose + detach.  Every step
# is a product-documented command; the caller adds its own output-line
# gates on the recover/add transcript.
itf_key_ceremony() {
    local label="$1" s_base="$2" s_vmid="$3" s_ip="$4" mode="${5:-recover}"
    itf_keystore_insert "$s_base" "$s_vmid" || return 1
    itf_keystore_unlock_mount "$s_ip" || return 1
    itf_storage_load_keys "$s_ip" || return 1
    local cmd="iscsi-recover-encrypted-luns"
    [[ "$mode" == add ]] && cmd="iscsi-add-encrypted-luns"
    local log="$ITF_RUN_DIR/${mode}-encrypted-${label}.log"
    itf_guest_exec "$s_ip" "bash -lc '$cmd'" > "$log" 2>&1
    local rc=$?
    itf_artifact "$mode-encrypted-$label" "$log"
    if [[ $rc -ne 0 ]]; then
        itf_step fail "encrypted LUNs recovered [$label]" \
            "$cmd rc=$rc — see $(basename "$log")"
        return 1
    fi
    itf_step pass "encrypted LUNs recovered [$label]" \
        "$cmd rc=0 — see $(basename "$log")"
    itf_keystore_lock_umount "$s_ip" || return 1
    itf_keystore_remove "$s_base" "$s_vmid" || return 1
    return 0
}

# itf_storage_boot_state <s_ip> <label>
#
# Captures the CURRENT boot's evidence from the storage guest: the
# rtslib-fb-targetctl unit journal (the drop-in echoes + verifier
# verdict + DRIFT detail), a cross-unit ordering snapshot (ZFS import vs
# the restore), and the pre-start backup file posture — the backup lands
# at /etc/rtslib-fb-target/saveconfig.json.pre-start and no stray
# root-level /.pre-start remains (the wrong-path artifact an earlier
# drop-in revision wrote).  Run before any other reboot.
itf_storage_boot_state() {
    local s_ip="$1" label="$2"
    local journal="$ITF_RUN_DIR/boot-${label}.journal"
    local order="$ITF_RUN_DIR/boot-${label}.order"
    # The verifier ExecStartPost can still be running when sshd answers
    # (the encrypted-LUN adds shift it later); wait (bounded) for its
    # verdict line before capturing so the parser sees a finished boot.
    local verdict_start=$SECONDS
    until (( SECONDS - verdict_start >= "${ITF_BOOT_VERDICT_WAIT:-120}" )); do
        if itf_guest_exec "$s_ip" \
                'journalctl -b -u rtslib-fb-targetctl.service --no-pager \
                    | grep -q "post-restore verification"'; then
            break
        fi
        sleep "${ITF_BOOT_VERDICT_POLL:-5}"
    done
    # shellcheck disable=SC2016  # expansions run in the guest
    if ! itf_guest_exec "$s_ip" \
            'journalctl -b -u rtslib-fb-targetctl.service --no-pager' \
            > "$journal" 2>/dev/null; then
        itf_step fail "boot journal captured [$label]" \
            "journalctl failed on the storage guest"
        return 1
    fi
    itf_artifact "boot-journal-$label" "$journal"
    # shellcheck disable=SC2016  # expansions run in the guest
    if ! itf_guest_exec "$s_ip" \
            'journalctl -b --no-pager | grep -nE "zfs-import-cache\.service|zfs-import\.target|targetctl:" || true' \
            > "$order" 2>/dev/null; then
        itf_step fail "boot order snapshot [$label]" "journalctl grep failed"
        return 1
    fi
    itf_artifact "boot-order-$label" "$order"
    # shellcheck disable=SC2016  # expansions run in the guest
    if itf_guest_exec "$s_ip" \
            'test -f /etc/rtslib-fb-target/saveconfig.json.pre-start && test ! -e /.pre-start'; then
        itf_step pass "pre-start backup posture [$label]" \
            "saveconfig.json.pre-start present; no stray /.pre-start"
    else
        itf_step fail "pre-start backup posture [$label]" \
            "backup file missing or stray /.pre-start exists"
        return 1
    fi
    return 0
}

# itf_boot_journal_verdict <journal-log> <order-log> <ok|failed> <lun>...
#
# Pure parser over itf_storage_boot_state's captures (unit-testable with
# fixtures).  Asserts, in order:
#   - the first ZFS-import mention precedes the restore line (the
#     drop-in's import gating, from the cross-unit snapshot);
#   - the unit journal shows the pre-start backup echo, then the
#     boot-config restore echo, then the verdict line;
#   - mode failed: every named encrypted LUN appears on a DRIFT line
#     AFTER the verdict (the check's re-emitted detail);
#   - mode ok: every named encrypted LUN appears on an "✓ Added" line
#     from the ExecStartPost add hook BEFORE the verdict.
# Echoes the verdict word on stdout; rc 1 (with reasons on stderr) when
# any assertion fails.  Tolerant of the stderr script:line: prefixes the
# product's journald lines carry.
itf_boot_journal_verdict() {
    local journal="$1" order="$2" mode="$3"
    shift 3
    local -a luns=("$@")
    local bad=0

    local import_n restore_n
    import_n="$(grep -nE 'zfs-import-cache\.service|zfs-import\.target' "$order" 2>/dev/null \
        | head -n 1 | cut -d: -f1)"
    restore_n="$(grep -n 'targetctl: restoring boot config' "$order" 2>/dev/null \
        | head -n 1 | cut -d: -f1)"
    if [[ -z "$import_n" || -z "$restore_n" ]] \
            || (( import_n >= restore_n )); then
        echo "import-order: import@${import_n:-none} restore@${restore_n:-none}" >&2
        bad=1
    fi

    local backup_n unit_restore_n verdict_n=""
    backup_n="$(grep -n 'targetctl: backed up saveconfig.json' "$journal" 2>/dev/null \
        | head -n 1 | cut -d: -f1)"
    unit_restore_n="$(grep -n 'targetctl: restoring boot config' "$journal" 2>/dev/null \
        | head -n 1 | cut -d: -f1)"
    if [[ "$mode" == ok ]]; then
        verdict_n="$(grep -n 'post-restore verification OK' "$journal" 2>/dev/null \
            | head -n 1 | cut -d: -f1)"
    else
        verdict_n="$(grep -n 'post-restore verification FAILED' "$journal" 2>/dev/null \
            | head -n 1 | cut -d: -f1)"
    fi
    if [[ -z "$backup_n" || -z "$unit_restore_n" || -z "$verdict_n" ]] \
            || (( backup_n >= unit_restore_n || unit_restore_n >= verdict_n )); then
        echo "order: backup@${backup_n:-none} restore@${unit_restore_n:-none}" \
            " verdict@${verdict_n:-none}" >&2
        bad=1
    fi

    local lun line_n
    if [[ "$mode" == ok ]]; then
        for lun in "${luns[@]}"; do
            line_n="$(grep -n "✓ Added ${lun} (LUN" "$journal" 2>/dev/null \
                | head -n 1 | cut -d: -f1)"
            if [[ -z "$line_n" ]] || (( line_n >= verdict_n )); then
                echo "added: ${lun}@${line_n:-none}" >&2
                bad=1
            fi
        done
        echo ok
    else
        for lun in "${luns[@]}"; do
            line_n="$(grep -n "DRIFT: .*${lun}" "$journal" 2>/dev/null \
                | head -n 1 | cut -d: -f1)"
            if [[ -z "$line_n" ]] || (( line_n <= verdict_n )); then
                echo "drift: ${lun}@${line_n:-none}" >&2
                bad=1
            fi
        done
        echo failed
    fi
    (( bad )) && return 1
    return 0
}

# itf_storage_reboot_assert <label> <s_ip> <ok|failed> <lun>...
#
# Post-reboot boot evidence as one gated step: capture the boot state,
# then run the journal parser in the requested mode with the scenario's
# encrypted LUNs.  This is the P6-oracle assertion — verdict, ordering,
# and per-LUN DRIFT/Added naming.
itf_storage_reboot_assert() {
    local label="$1" s_ip="$2" mode="$3"
    shift 3
    itf_storage_boot_state "$s_ip" "$label" || return 1
    local verdict
    if verdict="$(itf_boot_journal_verdict \
            "$ITF_RUN_DIR/boot-${label}.journal" \
            "$ITF_RUN_DIR/boot-${label}.order" \
            "$mode" "$@" 2> "$ITF_RUN_DIR/boot-${label}.verdict.err")"; then
        itf_step pass "boot journal oracle [$label]" \
            "verdict=$verdict; order + per-LUN naming asserted"
        return 0
    fi
    itf_step fail "boot journal oracle [$label]" \
        "see boot-${label}.verdict.err / boot-${label}.journal"
    return 1
}

# itf_vm_disk_links_present <c_ip> <vmid>...
#
# True when every /dev/disk/by-path link referenced by the given VMs'
# configs exists on the compute guest — the fence's own health rule,
# used to classify what returned unaided vs. what needed a rescan.
itf_vm_disk_links_present() {
    local c_ip="$1"
    shift
    local vm confs="" script
    for vm in "$@"; do
        confs+=" /etc/pve/qemu-server/${vm}.conf"
    done
    # shellcheck disable=SC2016  # expansions run in the guest
    script='
        missing=0
        for conf in@CONFS@; do
            if [[ ! -f "$conf" ]]; then
                echo "missing-conf: $conf"
                missing=1
                continue
            fi
            for dev in $(awk "/^scsi[0-9]+: .dev.disk.by-path./ {print \$2}" "$conf" | cut -d, -f1); do
                if [[ ! -e "$dev" ]]; then
                    echo "missing: $dev"
                    missing=1
                fi
            done
        done
        exit $missing
    '
    script="${script//@CONFS@/$confs}"
    itf_guest_exec "$c_ip" "$script"
}

# itf_wait_vm_disk_links <c_ip> <timeout-seconds> <vmid>...
#
# Bounded poll until itf_vm_disk_links_present succeeds; echoes the
# elapsed seconds at success (0 = the links were already back — nothing
# manual was needed).
itf_wait_vm_disk_links() {
    local c_ip="$1" timeout="$2"
    shift 2
    local start=$SECONDS
    while (( SECONDS - start < timeout )); do
        if itf_vm_disk_links_present "$c_ip" "$@" > /dev/null 2>&1; then
            echo $(( SECONDS - start ))
            return 0
        fi
        sleep "${ITF_LINK_POLL_INTERVAL:-10}"
    done
    return 1
}

# itf_compute_fallout_sample <c_ip> <label> <vmid>...
#
# One labeled snapshot of the compute node's user-visible state: iSCSI
# sessions, by-path links, and per-VM qm status — taken before, during,
# and after disruptive events.  Observation only; never a gate.
itf_compute_fallout_sample() {
    local c_ip="$1" label="$2"
    shift 2
    local vm cmd
    # shellcheck disable=SC2016  # expansions run in the guest
    cmd='
        echo "== date =="; date "+%F %T"
        echo "== iscsi sessions =="
        iscsiadm -m session 2>&1 || true
        echo "== disk by-path links =="
        ls -l /dev/disk/by-path/ 2>&1 | grep -i iscsi || true
    '
    for vm in "$@"; do
        # shellcheck disable=SC2029  # vmid expands host-side by design
        cmd+="
        echo \"== qm status $vm ==\"
        qm status $vm 2>&1 || true
        "
    done
    local log="$ITF_RUN_DIR/fallout-${label}.log"
    itf_guest_exec "$c_ip" "$cmd" > "$log" 2>&1
    itf_artifact "fallout-$label" "$log"
    itf_step info "compute fallout sampled [$label]" "see fallout-${label}.log"
    return 0
}

# itf_fence_tick <c_ip> <label>
#
# One manual fence tick on the compute guest: start the fence service
# (Type=oneshot — its rc IS the tick's verdict), then capture what the
# tick journaled since it began.  Returns the tick's rc.
itf_fence_tick() {
    local c_ip="$1" label="$2"
    local log="$ITF_RUN_DIR/fence-tick-${label}.log"
    # shellcheck disable=SC2016  # expansions run in the guest
    itf_guest_exec "$c_ip" '
        since=$(date "+%F %T")
        systemctl start zfsutilities-iscsi-fence.service
        rc=$?
        echo "tick-rc: $rc"
        journalctl -u zfsutilities-iscsi-fence.service --since "$since" --no-pager
        exit $rc
    ' > "$log" 2>&1
    local rc=$?
    itf_artifact "fence-tick-$label" "$log"
    return "$rc"
}

# itf_vm_evidence <c_ip> <vmid> <label>
#
# Saves a workload sample + checksum pair under <label> (fallout
# evidence around disruptive events).  rc 1 when the agent channel is
# down — itself a scenario signal the caller records and classifies.
itf_vm_evidence() {
    local c_ip="$1" vm="$2" label="$3"
    local sample="$ITF_RUN_DIR/workload-${label}-${vm}.txt"
    local cksum="$ITF_RUN_DIR/workload-${label}-${vm}.cksum"
    if ! itf_vm_workload_sample "$c_ip" "$vm" > "$sample" 2>/dev/null; then
        echo "agent-channel-down" > "$sample"
        itf_artifact "workload-$label-$vm" "$sample"
        return 1
    fi
    itf_vm_workload_checksum "$c_ip" "$vm" > "$cksum" 2>/dev/null || true
    itf_artifact "workload-$label-$vm" "$sample"
    itf_artifact "workload-cksum-$label-$vm" "$cksum"
    return 0
}

# itf_vm_workload_wait_sample <c_ip> <vmid> <out-file> [timeout-seconds]
#
# Bounded poll for a GROWING workload sample (>= 2 timestamps): the
# writer is nohup'd inside the VM and its first append can lag the
# agent call by seconds, so a single immediate sample races it.
itf_vm_workload_wait_sample() {
    local c_ip="$1" vm="$2" out="$3" timeout="${4:-120}"
    local start=$SECONDS
    while (( SECONDS - start < timeout )); do
        if itf_vm_workload_sample "$c_ip" "$vm" > "$out" 2>/dev/null \
                && [[ $(wc -l < "$out") -ge 2 ]]; then
            return 0
        fi
        sleep "${ITF_VM_SAMPLE_INTERVAL:-5}"
    done
    return 1
}

# itf_journey_stage_boot_workload_lab <gname> <s_base> <s_vmid> <s_ip> <c_ip>
#
# The j15 boot-and-keys staging tail on the encrypted two-node lab
# (run AFTER j05_two_node_lab_main --encrypted-keys):
#   - VM 101 becomes the everyday workload VM: its OS rides a plain 4G
#     LUN (vm-101-disk-2, product-created), boot order scsi2, and the
#     encrypted spare (vm-101-disk-1) is DETACHED from it — a storage
#     reboot costs VM 101 a session drop, never the key ceremony.
#   - VM 202 becomes the encrypted-root workload VM: its OS rides the
#     product-created encrypted vm-202-disk-0.
#   - both boot under TCG with the guest agent, run the 1 Hz writer,
#     and are then parked stopped (the scenario posture); the fence
#     timer premise and the P6 pre-reboot gates (safe-iscsi-save clean
#     pass + export-iscsi-state --check OK) close the staging.
itf_journey_stage_boot_workload_lab() {
    local gname="$1" s_base="$2" s_vmid="$3" s_ip="$4" c_ip="$5"
    local pool_a="zfstest1"
    local key_path="/mnt/ZFSkeys/keys/${ITF_KEYFILE_NAME}"
    local vm log

    local gz="$ITF_CACHE_DIR/itf-vmos.raw.gz"
    if [[ -s "$gz" ]]; then
        itf_step pass "VM-OS image available" \
            "$(du -h "$gz" | awk '{print $1}') cached"
    else
        itf_step fail "VM-OS image available" \
            "no cached image at $gz — PREP: itf vmimage build"
        return 1
    fi

    # The scenarios create disks on the other two test pools; the
    # documented enrollment is the admin step a user does first.
    local pool
    for pool in zfstest2 zfstest3; do
        log="$ITF_RUN_DIR/enroll-${pool}.log"
        if itf_guest_exec "$s_ip" "bash -lc 'enroll-proxmox-pool $pool'" \
                > "$log" 2>&1; then
            itf_step pass "pool registered as PVE storage" \
                "$pool on the compute host (see $(basename "$log"))"
        else
            itf_step fail "pool registered as PVE storage" \
                "$pool — see $(basename "$log")"
            return 1
        fi
    done

    # --- VM 101: plain-OS everyday workload VM ---
    log="$ITF_RUN_DIR/new-vm-disk-101-2.log"
    if itf_guest_exec "$c_ip" "bash -lc 'new-vm-disk $pool_a 101 2 4G'" \
            > "$log" 2>&1 \
            && grep -q "✓ Configuration saved" "$log"; then
        itf_step pass "plain OS LUN created" \
            "vm-101-disk-2 (4G) through new-vm-disk (see $(basename "$log"))"
        itf_artifact "new-vm-disk-101-2" "$log"
    else
        itf_step fail "plain OS LUN created" "see new-vm-disk-101-2.log"
        return 1
    fi
    if itf_guest_exec "$c_ip" "qm set 101 --delete scsi1" \
            > "$ITF_RUN_DIR/vm101-detach-scsi1.log" 2>&1; then
        itf_step pass "encrypted spare detached from VM 101" \
            "vm-101-disk-1 stays registered on the target, owned by no VM"
    else
        itf_step fail "encrypted spare detached from VM 101" \
            "see vm101-detach-scsi1.log"
        return 1
    fi
    itf_vmos_image_zvol "$s_ip" "${pool_a}/proxmox/vm-101-disk-2" || return 1

    # --- VM 202: encrypted-OS workload VM ---
    if itf_guest_exec "$c_ip" \
            "bash -lc 'qm create 202 --name j15-vm202 --scsihw virtio-scsi-pci'" \
            > "$ITF_RUN_DIR/qm-create-202.log" 2>&1; then
        itf_step pass "VM 202 created (stopped)" \
            "container for the encrypted-root workload VM"
    else
        itf_step fail "VM 202 created" "see qm-create-202.log"
        return 1
    fi
    # The G0 lab tail ends in the production posture (store locked and
    # detached) — new-vm-disk's key-path check runs on the STORAGE side,
    # so the store must be present again for the encrypted OS LUN.
    itf_keystore_insert "$s_base" "$s_vmid" || return 1
    itf_keystore_unlock_mount "$s_ip" || return 1
    if itf_new_vm_disk_encrypted "$c_ip" "$pool_a" 202 0 4G "$key_path" \
            new-vm-disk-enc-202-0 \
            && grep -q "✓ Configuration saved" \
                "$ITF_RUN_DIR/new-vm-disk-enc-202-0.log" \
            && itf_guest_exec "$c_ip" \
                "grep -q '^scsi0: /dev/disk/by-path/' /etc/pve/qemu-server/202.conf"; then
        itf_step pass "encrypted OS LUN created" \
            "vm-202-disk-0 (4G) through new-vm-disk --encrypted"
    else
        itf_step fail "encrypted OS LUN created" \
            "see new-vm-disk-enc-202-0.log"
        return 1
    fi
    itf_vmos_image_zvol "$s_ip" "${pool_a}/proxmox/vm-202-disk-0" || return 1
    # Back to the production posture: lock and detach — the key stays
    # loaded with the device gone (what every scenario reboot starts
    # from).
    itf_keystore_lock_umount "$s_ip" || return 1
    itf_keystore_remove "$s_base" "$s_vmid" || return 1

    # Boot order: VM 101's root is the OS LUN (scsi2; scsi0 is blank).
    if itf_guest_exec "$c_ip" "qm set 101 --boot order=scsi2" \
            > "$ITF_RUN_DIR/vm101-boot-order.log" 2>&1; then
        itf_step info "VM 101 boot order set" "scsi2 (the plain OS LUN)"
    else
        itf_step fail "VM 101 boot order set" "see vm101-boot-order.log"
        return 1
    fi

    itf_vm_boot_with_agent "$c_ip" 101 || return 1
    itf_vm_boot_with_agent "$c_ip" 202 || return 1
    itf_vm_workload_start "$c_ip" 101 || return 1
    itf_vm_workload_start "$c_ip" 202 || return 1

    # Both writers checked in: a growing sample proves the agent channel
    # and the LUN-backed root filesystem (polled — the first append lags
    # the writer start by seconds).
    local sample
    for vm in 101 202; do
        sample="$ITF_RUN_DIR/workload-staging-${vm}.txt"
        if itf_vm_workload_wait_sample "$c_ip" "$vm" "$sample" \
                && itf_vm_workload_gaps "$sample" 5 \
                    > "$ITF_RUN_DIR/workload-staging-${vm}.gaps"; then
            itf_step pass "writer baseline [VM $vm]" \
                "$(cat "$ITF_RUN_DIR/workload-staging-${vm}.gaps")"
            itf_artifact "workload-staging-$vm" "$sample"
        else
            itf_step fail "writer baseline [VM $vm]" \
                "no clean growing sample — see workload-staging-${vm}.txt"
            return 1
        fi
    done

    # Fence premise: the boot scenarios lean on the timer the units
    # activation installed (j14 proved installation; this is the
    # runtime premise).
    # shellcheck disable=SC2016  # expansions run in the guest
    if itf_guest_exec "$c_ip" '
            test "$(systemctl is-enabled zfsutilities-iscsi-fence.timer)" = enabled \
            && test "$(systemctl is-active zfsutilities-iscsi-fence.timer)" = active
        ' > "$ITF_RUN_DIR/fence-premise.log" 2>&1; then
        itf_step pass "fence timer armed" \
            "zfsutilities-iscsi-fence.timer enabled + active on compute"
    else
        itf_step fail "fence timer armed" "see fence-premise.log"
        return 1
    fi

    # The P6 pre-reboot gates on the healthy lab.
    itf_safe_save_gate "$s_ip" "$gname" || return 1
    itf_iscsi_check_gate "$s_ip" "$gname" || return 1

    # Final writer evidence, then park both VMs stopped (the posture
    # every scenario reboot starts from).
    for vm in 101 202; do
        itf_vm_evidence "$c_ip" "$vm" "staging-final" || return 1
    done
    # shellcheck disable=SC2016  # expansions run in the guest
    if itf_guest_exec "$c_ip" '
            set -e
            for vm in 101 202; do
                qm shutdown $vm --timeout 45 || qm stop $vm
                test "$(qm status $vm | awk "{print \$2}")" = stopped
            done
        ' > "$ITF_RUN_DIR/vm-park.log" 2>&1; then
        itf_step pass "workload VMs parked" \
            "both stopped; writers sampled + checksummed (see vm-park.log)"
    else
        itf_step fail "workload VMs parked" "see vm-park.log"
        return 1
    fi

    # Storage posture snapshot for the report.
    # shellcheck disable=SC2016  # expansions run in the guest
    itf_guest_exec "$s_ip" '
        echo "== encrypted-luns conf =="
        cat /etc/zfsutilities/iscsi-encrypted-luns.conf
        echo "== keystatus =="
        zfs list -t volume -o name,keystatus | grep -E "vm-|^NAME"
        echo "== backstores =="
        targetcli ls /backstores 2>/dev/null || true
    ' > "$ITF_RUN_DIR/storage-posture.log" 2>&1
    itf_artifact "storage-posture" "$ITF_RUN_DIR/storage-posture.log"
    return 0
}

# itf_single_node_lab_main <gname>
#
# The single-node lab prefix, factored from j04/j11: clone the
# post-install baseline template, verify the installed state, and create
# the documented three-RAIDZ1 test pools.  Sets J_VMID/J_GUEST_IP (the
# clone stage's globals) for the caller's scenario stages.
itf_single_node_lab_main() {
    local gname="$1"

    itf_journey_stage_from_template "$gname" || return 1

    itf_journey_verify_installed "$J_GUEST_IP"

    itf_journey_stage_test_pools "$gname" "${ITF_BASE_HOSTS[0]}" "$J_VMID" \
        "$J_GUEST_IP" || return 1
    return 0
}

# itf_rerun_guest <guest-file-basename>
#
# --rerun support: echoes "base vmid" for the guest the driver marked for
# rerun (rerun-guests.tsv, written by "itf journey run NAME --rerun"),
# nothing at all when this is a fresh run.  Keyed by the guest-record
# file name the staging stage would write (guest.txt, guest-<role>.txt)
# so a composed journey's lab stages find their own guests.
itf_rerun_guest() {
    local key="$1"
    local spec="${ITF_RUN_DIR}/rerun-guests.tsv"
    if [[ -f "$spec" ]]; then
        awk -v k="$key" '$1 == k { print $2, $3 }' "$spec" 2>/dev/null || true
    fi
    return 0
}

# itf_journey_stage_from_template <gname> [--base B] [--template T] [--role R]
#
# Clone start: full-clone a post-install baseline template (default: the
# storage profile's ITF_TEMPLATE_NAME) and snapshot `as-cloned` as the
# journey's rollback checkpoint.  Fails fast with a PREP hint when the
# template is missing or carries no stamp — per the journey contract,
# never half-run.  Sets J_VMID and J_GUEST_IP.
#
# Under --rerun (the driver resolved the previous run's guests into
# rerun-guests.tsv) this stage rolls the recorded guest back to its
# as-cloned checkpoint instead of cloning — the whole journey then
# replays on the same guest with no template copy.
itf_journey_stage_from_template() {
    local gname="$1"
    shift
    local base="${ITF_STORAGE_BASE:-${ITF_BASE_HOSTS[0]}}" role=""
    local template="${ITF_TEMPLATE_NAME:-}"
    while (( $# > 0 )); do
        case "$1" in
            --base) base="$2"; shift 2 ;;
            --template) template="$2"; shift 2 ;;
            --role) role="$2"; shift 2 ;;
            *) echo "itf: unknown itf_journey_stage_from_template option: $1" >&2; return 2 ;;
        esac
    done
    local guest_file="$ITF_RUN_DIR/guest.txt"
    [[ -n "$role" ]] && guest_file="$ITF_RUN_DIR/guest-${role}.txt"
    local tmpl_vmid stamp vmid guest_ip

    # --rerun: replay on the previous run's guest — rolling back to the
    # as-cloned checkpoint replaces the template clone (the driver put
    # the recorded guests in rerun-guests.tsv; nothing there = fresh run).
    local rerun_pair r_base r_vmid
    rerun_pair="$(itf_rerun_guest "$(basename "$guest_file")")"
    if [[ -n "$rerun_pair" ]]; then
        r_base="${rerun_pair%% *}"
        r_vmid="${rerun_pair##* }"
        # Remember the guest for post-mortem/diagnostics even if we abort.
        echo "$r_base $r_vmid" > "$guest_file"
        if itf_qm "$r_base" status "$r_vmid" \
                > "$ITF_RUN_DIR/guest-status-${gname}.log" 2>&1; then
            itf_step pass "rerun guest present" "vmid $r_vmid on $r_base"
        else
            itf_step fail "rerun guest present" \
                "vmid $r_vmid no longer on $r_base — run fresh (no --rerun)"
            return 1
        fi
        if itf_qm "$r_base" listsnapshot "$r_vmid" 2>/dev/null \
                | awk '$1 == "`->" && $2 == "as-cloned" { found = 1 }
                       END { exit !found }'; then
            itf_step pass "as-cloned checkpoint present" "vmid $r_vmid"
        else
            itf_step fail "as-cloned checkpoint present" \
                "vmid $r_vmid has no as-cloned snapshot — run fresh (no --rerun)"
            return 1
        fi
        # Snapshots newer than as-cloned SURVIVE a rollback on this stack
        # but go stale (their content predates the replay) — and the
        # replay re-snapshots the same names, which would collide.  Remove
        # them first so the guest matches a fresh clone's checkpoint list.
        itf_guest_stop "$r_base" "$r_vmid" > /dev/null 2>&1 || true
        local stale
        while IFS= read -r stale; do
            [[ -n "$stale" ]] || continue
            if itf_qm "$r_base" delsnapshot "$r_vmid" "$stale" \
                    > "$ITF_RUN_DIR/guest-delsnap-${gname}.log" 2>&1; then
                itf_step pass "stale snapshot removed" \
                    "$stale (newer than as-cloned, left stale by the rollback)"
            else
                itf_step fail "stale snapshot removed" \
                    "$stale — see guest-delsnap-${gname}.log"
                return 1
            fi
        done < <(itf_qm "$r_base" listsnapshot "$r_vmid" 2>/dev/null \
                | awk '$1 == "`->" {
                    if ($2 == "as-cloned") { seen = 1; next }
                    if (seen && $2 != "current") print $2
                }')
        if itf_guest_rollback "$r_base" "$r_vmid" as-cloned --start \
                > "$ITF_RUN_DIR/guest-rollback-${gname}.log" 2>&1; then
            itf_step pass "guest rolled back to as-cloned" \
                "vmid $r_vmid — no re-clone; the journey replays from the checkpoint"
        else
            itf_step fail "guest rolled back to as-cloned" \
                "see guest-rollback-${gname}.log"
            return 1
        fi
        guest_ip="$(itf_guest_ip "$r_base" "$r_vmid" 600)"
        if [[ -n "$guest_ip" ]]; then
            itf_step pass "guest IP discovered" "$guest_ip"
            echo "$r_base $r_vmid $guest_ip" > "$guest_file"
        else
            itf_step fail "guest IP discovered" "guest agent reported nothing in 600s"
            return 1
        fi
        if itf_wait_ssh "$guest_ip" 300; then
            itf_step pass "guest ssh reachable" "root@${guest_ip}"
        else
            itf_step fail "guest ssh reachable"
            return 1
        fi
        # shellcheck disable=SC2034  # consumed by the journey scripts
        J_VMID="$r_vmid"
        # shellcheck disable=SC2034  # consumed by the journey scripts
        J_GUEST_IP="$guest_ip"
        return 0
    fi

    tmpl_vmid="$(itf_template_vmid "$base" "$template")"
    if [[ -z "$tmpl_vmid" ]]; then
        itf_step fail "baseline template available" \
            "no '$template' on $base — PREP: itf template build"
        return 1
    fi
    if ! stamp="$(itf_template_stamp_read "$base" "$tmpl_vmid" 2>/dev/null)"; then
        itf_step fail "baseline template available" \
            "vmid $tmpl_vmid has no readable itf stamp — PREP: itf template build --force"
        return 1
    fi
    itf_step pass "baseline template available" \
        "$template (vmid $tmpl_vmid): ${stamp#itf-stamp| }"

    vmid="$(itf_guest_clone "$gname" --base "$base" --template "$template" \
        2>"$ITF_RUN_DIR/guest-clone-${gname}.log")"
    if [[ -n "$vmid" ]]; then
        itf_step pass "guest cloned from template" \
            "vmid $vmid — post-install baseline in minutes, not a reinstall"
    else
        itf_step fail "guest cloned from template" "see guest-clone-${gname}.log"
        return 1
    fi
    # Remember the guest for post-mortem/diagnostics even if we abort.
    echo "$base $vmid" > "$guest_file"

    if itf_guest_start "$base" "$vmid" > "$ITF_RUN_DIR/guest-start-${gname}.log" 2>&1; then
        itf_step pass "guest started" "vmid $vmid"
    else
        itf_step fail "guest started" "see guest-start-${gname}.log"
        return 1
    fi

    guest_ip="$(itf_guest_ip "$base" "$vmid" 600)"
    if [[ -n "$guest_ip" ]]; then
        itf_step pass "guest IP discovered" "$guest_ip"
        echo "$base $vmid $guest_ip" > "$guest_file"
    else
        itf_step fail "guest IP discovered" "guest agent reported nothing in 600s"
        return 1
    fi

    if itf_wait_ssh "$guest_ip" 300; then
        itf_step pass "guest ssh reachable" "root@${guest_ip}"
    else
        itf_step fail "guest ssh reachable"
        return 1
    fi

    if itf_guest_snapshot "$base" "$vmid" as-cloned > /dev/null 2>&1; then
        itf_step pass "snapshot as-cloned" "post-install checkpoint for this journey"
    else
        itf_step fail "snapshot as-cloned"
    fi

    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_VMID="$vmid"
    # shellcheck disable=SC2034  # consumed by the journey scripts
    J_GUEST_IP="$guest_ip"
    return 0
}
