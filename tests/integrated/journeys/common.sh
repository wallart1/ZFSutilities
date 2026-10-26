#!/usr/bin/env bash
# common.sh — shared journey stages, factored from j01-fresh-install.
#
# Composable stages:
#   itf_journey_stage_os <gname> <hostname> [--base B] [--role R]
#       Fresh Debian guest: custom serial-console ISO + preseed install,
#       IP discovery, root SSH, os-installed snapshot.
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
    local base="${ITF_BASE_HOSTS[0]}" role=""
    while (( $# > 0 )); do
        case "$1" in
            --base) base="$2"; shift 2 ;;
            --role) role="$2"; shift 2 ;;
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
        --freeze 2>"$ITF_RUN_DIR/guest-create.log")"
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
