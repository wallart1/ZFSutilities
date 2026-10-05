#!/usr/bin/env bash
# common.sh — shared journey stages, factored from j01-fresh-install.
#
# Two composable stages every cycle-1 journey starts with:
#   itf_journey_stage_os <gname> <hostname>
#       Fresh Debian guest: custom serial-console ISO + preseed install,
#       IP discovery, root SSH, os-installed snapshot.
#       Sets globals J_VMID and J_GUEST_IP on success.
#   itf_journey_stage_install <guest-ip>
#       First-time-user product install: download (per ITF_SW_SOURCE),
#       expected-to-fail prerequisite check on the fresh system,
#       install-single-node with piped answers, installed-state verify.
#
# HTTP-server shutdown on abort paths goes through the J_PIDFILE /
# J_PIDFILE2 globals: an EXIT trap cannot see function-locals after the
# function returns, so the stage functions publish their pidfiles there
# and clear them once stopped.

itf_journey_stage_os() {
    local gname="$1"
    local guest_hostname="$2"
    local base="${ITF_BASE_HOSTS[0]}"
    local vmid guest_ip dev_ip preseed_file serve_dir

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
    echo "$base $vmid" > "$ITF_RUN_DIR/guest.txt"

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
        echo "$base $vmid $guest_ip" > "$ITF_RUN_DIR/guest.txt"
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

# itf_journey_run_installer <guest-ip> <answers-printf-format> <step-label>
#
# Runs ./bin/install-single-node from the guest's /root/ZFSutilities
# tree with piped answers and records the outcome under <step-label>.
itf_journey_run_installer() {
    local guest_ip="$1"
    local feed_format="$2"
    local label="$3"
    local answers inst_log inst_rc
    answers="$ITF_RUN_DIR/install-answers.txt"
    printf '%b' "$feed_format" > "$answers"
    inst_log="$ITF_RUN_DIR/guest-install.log"
    itf_guest_exec_feed "$guest_ip" "$answers" \
        "cd /root/ZFSutilities && ./bin/install-single-node" > "$inst_log" 2>&1
    inst_rc=$?
    itf_artifact "install-transcript" "$inst_log"
    if [[ $inst_rc -eq 0 ]]; then
        itf_step pass "$label" "rc=0 with piped answers"
    else
        itf_step fail "$label" "rc=$inst_rc — first-time-user flow broke; see guest-install.log"
        return 1
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

    local dl_script relver dev_ip
    dev_ip="$(itf_dev_ip)"
    dl_script="$ITF_RUN_DIR/guest-dl.sh"
    if [[ "$ITF_SW_SOURCE" == "dev-tarball" ]]; then
        # Repair-verification source: a tarball of the current working
        # tree, fetched from a second short-lived HTTP server (the
        # Stage A preseed server is already down by now).  Site-local
        # and generated content stays out of the tarball.
        local repo_root tarball serve_msg
        repo_root="$ITF_ROOT/../.."
        tarball="$ITF_RUN_DIR/serve/zfsutilities-dev.tar.gz"
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

    local pre_log
    pre_log="$ITF_RUN_DIR/guest-prereq.log"
    if itf_guest_exec "$guest_ip" "/root/ZFSutilities/bin/check-prerequisites --single-node" \
        > "$pre_log" 2>&1; then
        itf_step fail "prereq check (fresh system)" "unexpectedly reported all-present"
    else
        itf_step pass "prereq check (fresh system)" "reports the missing items a user must handle"
        itf_artifact "prereq-check" "$pre_log"
    fi

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
