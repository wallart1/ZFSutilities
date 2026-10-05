#!/usr/bin/env bash
# tests/integrated/lib/ssh-lib.sh
#
# Transport helpers for the itf orchestrator.
#
# Three planes, three helpers:
#   - base hosts (Proxmox VMs): itf_base_exec runs a command as root via
#     "ssh <user>@<base> sudo -n bash -c ..." — the only sanctioned path to
#     privileged base operations, and always wrapped by base-lib's guards.
#   - guests (the machines under test): itf_guest_exec / itf_guest_put talk
#     to root@<guest-ip> directly; guests are disposable and unrestricted.
#   - dev-side services: a small HTTP server (itf_http_serve) used to serve
#     preseed files to installing guests.
#
# No site-specific data here: hosts, user, and ports all come from the site
# configuration (config-lib.sh).

if [[ -n "${ITF_LIB_SSH_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_SSH_LOADED=1

# itf_base_exec <base-host> <command-string>
#
# Runs <command-string> through bash on the base host as root.  The command
# string is quoted as a single argument so the remote shell receives it
# verbatim.  Returns the ssh exit status.
itf_base_exec() {
    local base="$1" cmd="$2"
    if [[ -z "${ITF_SSH_USER:-}" ]]; then
        echo "itf: ITF_SSH_USER not set — site config not loaded?" >&2
        return 1
    fi
    ssh -o BatchMode=yes -o ConnectTimeout=10 -n -T \
        "${ITF_SSH_USER}@${base}" \
        "sudo -n bash -c $(printf '%q' "$cmd")"
}

# itf_base_put <base-host> <local-file> <remote-temp-path>
#
# Copies a file to the base host as the unprivileged SSH user (target must
# be writable by it, e.g. under /tmp).  Privileged placement is a separate,
# guarded step (see base-lib's itf_iso_upload).
itf_base_put() {
    local base="$1" local_file="$2" remote_path="$3"
    if [[ -z "${ITF_SSH_USER:-}" ]]; then
        echo "itf: ITF_SSH_USER not set — site config not loaded?" >&2
        return 1
    fi
    scp -q -o BatchMode=yes -o ConnectTimeout=10 \
        "$local_file" "${ITF_SSH_USER}@${base}:${remote_path}"
}

# itf_base_get <base-host> <remote-path> <local-dest>
#
# Copies a file back from the base host as the unprivileged SSH user
# (the remote file must be readable by it).
itf_base_get() {
    local base="$1" remote="$2" dest="$3"
    if [[ -z "${ITF_SSH_USER:-}" ]]; then
        echo "itf: ITF_SSH_USER not set — site config not loaded?" >&2
        return 1
    fi
    scp -q -o BatchMode=yes -o ConnectTimeout=10 \
        "${ITF_SSH_USER}@${base}:${remote}" "$dest"
}

# itf_syslog_start <base-host> <vmid>
#
# Starts a UDP-514 syslog listener on the base host appending to
# /tmp/itf-syslog-<vmid>.log.  Paired with the debian-installer
# `log=<base-lan-ip>` boot parameter this gives installer-side
# visibility into hangs that draw nothing on the serial console
# (observed: deterministic d-i wedge at "Configuring apt").
itf_syslog_start() {
    local base="$1" vmid="$2"
    local log="/tmp/itf-syslog-${vmid}.log"
    # The [first-digit] bracket form is the pkill/pgrep self-match
    # guard: the regex "[8]000" matches "8000" but never the literal
    # pattern text itself.  (Bracketing the LAST digit instead —
    # "8000[0]" — demands an extra digit and matches nothing.)
    local pat="socat.*itf-syslog-[${vmid:0:1}]${vmid:1}"
    if itf_base_exec "$base" \
        "pgrep -f '${pat}' > /dev/null 2>&1"; then
        return 0
    fi
    # Spawn and verify in ONE remote command: separate ssh calls race
    # (the listener needs a moment to appear).  UDP-RECVFROM,fork is the
    # PERSISTENT form — plain UDP-RECV exits after one datagram, and
    # stray LAN noise to :514 would silently kill such a capture.
    local socat_start
    socat_start="nohup socat -u UDP-RECVFROM:514,fork OPEN:${log},creat,append"
    socat_start+=" > /dev/null 2>&1 & sleep 1; pgrep -f '${pat}' > /dev/null 2>&1"
    if ! itf_base_exec "$base" "$socat_start"; then
        echo "itf: syslog listener did not start on $base (UDP 514 busy?)" >&2
        return 1
    fi
    itf_log_action "$base" "syslog-capture start: vmid $vmid -> $log"
}

# itf_syslog_stop <base-host> <vmid> <local-dest>
#
# Stops the listener and pulls the captured installer syslog back to
# <local-dest>; the remote copy is then removed.
itf_syslog_stop() {
    local base="$1" vmid="$2" dest="$3"
    local log="/tmp/itf-syslog-${vmid}.log"
    local pat="socat.*itf-syslog-[${vmid:0:1}]${vmid:1}"
    itf_base_exec "$base" "pkill -f '${pat}'" || true
    if itf_base_get "$base" "$log" "$dest"; then
        itf_base_exec "$base" "rm -f ${log}" || true
        itf_log_action "$base" "syslog-capture stop: vmid $vmid"
        return 0
    fi
    return 1
}

# itf_guest_exec <guest-ip> <command-string>
#
# Guests are disposable and DHCP-recycled: a fresh guest at a previously
# used address presents a DIFFERENT host key, which accept-new rejects as
# a mismatch.  All guest ssh/scp therefore pin StrictHostKeyChecking=no
# with a throwaway known-hosts file — never consult or pollute the
# operator's known_hosts.
_ITF_GUEST_SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null)

itf_guest_exec() {
    local ip="$1" cmd="$2"
    ssh "${_ITF_GUEST_SSH_OPTS[@]}" -o ConnectTimeout=10 -n \
        "root@${ip}" "$cmd"
}

# itf_guest_exec_feed <guest-ip> <answers-file> <command-string>
#
# Runs <command-string> on the guest with the local <answers-file> piped
# to its stdin — how journeys "type" answers into interactive installers
# (ask_yn and read -rp both consume plain stdin).
itf_guest_exec_feed() {
    local ip="$1" answers="$2" cmd="$3"
    ssh "${_ITF_GUEST_SSH_OPTS[@]}" -o ConnectTimeout=10 \
        "root@${ip}" "$cmd" < "$answers"
}

# itf_guest_put <guest-ip> <local-file> <remote-path>
itf_guest_put() {
    local ip="$1" local_file="$2" remote_path="$3"
    scp -q "${_ITF_GUEST_SSH_OPTS[@]}" -o ConnectTimeout=10 \
        "$local_file" "root@${ip}:${remote_path}"
}

# itf_wait_ssh <ip> [timeout-seconds]
#
# Polls until root@<ip> accepts passwordless SSH.  Default timeout 900s
# (a full OS install can take several minutes before sshd is up).
itf_wait_ssh() {
    local ip="$1" timeout="${2:-900}"
    local deadline=$(( SECONDS + timeout ))
    while (( SECONDS < deadline )); do
        if ssh "${_ITF_GUEST_SSH_OPTS[@]}" -o ConnectTimeout=5 \
            "root@${ip}" true 2>/dev/null; then
            return 0
        fi
        sleep 10
    done
    echo "itf: timed out after ${timeout}s waiting for ssh on ${ip}" >&2
    return 1
}

# itf_dev_ip
#
# Echoes dev's primary LAN IPv4 (first non-loopback address, excluding
# container/bridge ranges).  Used to build the preseed URL; override by
# setting ITF_DEV_IP in the site config.
itf_dev_ip() {
    if [[ -n "${ITF_DEV_IP:-}" ]]; then
        echo "$ITF_DEV_IP"
        return 0
    fi
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
        | grep -v '^127\.' \
        | grep -v '^172\.(1[6-9]|2[0-9]|3[01])\.' \
        | head -1
}

# _itf_http_probe <port> <path> — raw HTTP/1.0 GET via bash /dev/tcp;
# rc 0 only when the response status line says 200 OK.  A bare connect
# is not enough: a squatter bound to 127.0.0.1 can shadow our wildcard
# server on loopback (SO_REUSEADDR lets both bind), so readiness must
# be proven by fetching OUR content, not by opening a socket.
_itf_http_probe() {
    local port="$1" path="$2" resp
    resp="$(
        {
            exec 3<>"/dev/tcp/127.0.0.1/$port" || return 1
            printf 'GET %s HTTP/1.0\r\n\r\n' "$path" >&3
            cat <&3
        } 2>/dev/null
    )"
    [[ "$resp" == *"200 OK"* ]]
}

# itf_http_serve <directory> <pidfile>
#
# Serves <directory> over HTTP on ITF_HTTP_PORT using python3's stdlib
# server, bound to all interfaces so guests on the LAN can fetch the
# preseed.  Background process; stop with itf_http_stop.  The server's
# own output goes to "<pidfile-minus-.pid>.log" so bind failures are
# diagnosable.  Fails loudly (rc 1, nothing written to the pidfile) if
# the port is already taken or the server dies on startup — a silently
# dead server turns into an unattended guest install that falls back
# to interactive prompts.  Readiness is a GET of a unique marker file
# from the served directory, which also catches loopback shadowing.
itf_http_serve() {
    local dir="$1" pidfile="$2"
    local log="${pidfile%.pid}.log"
    if [[ -f "$pidfile" ]]; then
        local old
        old=$(cat "$pidfile" 2>/dev/null || true)
        if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
            echo "itf: http server already running (pid $old) — stop it first" >&2
            return 1
        fi
        rm -f "$pidfile"
    fi
    python3 -m http.server "$ITF_HTTP_PORT" --bind 0.0.0.0 --directory "$dir" \
        >"$log" 2>&1 &
    local pid=$!
    local marker=".itf-ready-$pid"
    : > "$dir/$marker"
    local _
    for _ in 1 2 3 4 5; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$dir/$marker"
            echo "itf: http server exited on startup — port $ITF_HTTP_PORT busy" \
                "or bad directory? see $log" >&2
            return 1
        fi
        if _itf_http_probe "$ITF_HTTP_PORT" "/$marker"; then
            rm -f "$dir/$marker"
            echo "$pid" > "$pidfile"
            echo "itf: serving $dir on port $ITF_HTTP_PORT (pid $pid)"
            return 0
        fi
        sleep 1
    done
    rm -f "$dir/$marker"
    kill "$pid" 2>/dev/null || true
    echo "itf: http server never became ready on port $ITF_HTTP_PORT — see $log" >&2
    return 1
}

# itf_http_stop <pidfile>
itf_http_stop() {
    local pidfile="$1"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(cat "$pidfile")
        kill "$pid" 2>/dev/null || true
        rm -f "$pidfile"
    fi
}
