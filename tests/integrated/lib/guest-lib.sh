#!/usr/bin/env bash
# tests/integrated/lib/guest-lib.sh
#
# Nested-guest lifecycle for the itf orchestrator: creation from the
# reserved VMID range, start/stop/snapshot/rollback/destroy, ISO fetch and
# guarded upload, preseed rendering, and post-install discovery of the
# guest's DHCP address via the qemu guest agent.
#
# All base-host access goes through base-lib's guarded itf_qm/itf_read —
# nothing here talks to a base system directly.
#
# Guest model (defaults from the site config):
#   SeaBIOS + virtio-scsi, system disk scsi0 on ITF_GUEST_STORAGE, optional
#   test-pool disk scsi1, NIC on ITF_BRIDGE (DHCP from the LAN), qemu guest
#   agent enabled, serial0 socket with vga=serial0 so the installer boot
#   prompt is reachable over `qm terminal` (see serial_console.py).

if [[ -n "${ITF_LIB_GUEST_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_GUEST_LOADED=1

# itf_vmid_pick <base-host>
#
# Echoes the first free VMID inside the reserved range, or fails when the
# range is exhausted.
itf_vmid_pick() {
    local base="$1"
    local used vmid
    used="$(itf_qm "$base" list | awk 'NR>1 {print $1}' | sort -n | tr '\n' ' ')" || return 1
    for (( vmid = ITF_VMID_FIRST; vmid <= ITF_VMID_LAST; vmid++ )); do
        [[ " $used " == *" $vmid "* ]] || { echo "$vmid"; return 0; }
    done
    echo "itf: VMID range ${ITF_VMID_FIRST}-${ITF_VMID_LAST} exhausted on $base" >&2
    return 1
}

# itf_guest_create <name> [--base B] [--vmid V] [--mem MB] [--cores N]
#                   [--sysdisk GB] [--pooldisk GB] [--iso NAME] [--freeze] [--start]
#
# Creates the guest and echoes its VMID on stdout (everything else goes to
# stderr so the VMID is capturable).  --freeze sets "Freeze CPU at
# startup" so the serial console can be attached before boot proceeds
# (the caller resumes with itf_qm <base> resume <vmid>).
itf_guest_create() {
    local name="$1"
    shift
    local base="${ITF_BASE_HOSTS[0]}" vmid="" mem="$ITF_GUEST_MEMORY_MB" cores="$ITF_GUEST_CORES"
    # The pool disk is OPT-IN (--pooldisk): a second virtio disk present
    # during the install makes Linux's virtio-scsi enumeration a race
    # (observed live: which disk is /dev/sda flips between boots), so the
    # installer must see exactly one disk.  Journeys attach the pool disk
    # by hotplug once the OS is up (see J01 Stage D).
    local sysdisk="$ITF_GUEST_SYSTEM_DISK_GB" pooldisk=0 iso="" start=0 freeze=0
    local key

    while (( $# > 0 )); do
        key="$1"
        case "$key" in
            --base) base="$2"; shift 2 ;;
            --vmid) vmid="$2"; shift 2 ;;
            --mem) mem="$2"; shift 2 ;;
            --cores) cores="$2"; shift 2 ;;
            --sysdisk) sysdisk="$2"; shift 2 ;;
            --pooldisk) pooldisk="$2"; shift 2 ;;
            --iso) iso="$2"; shift 2 ;;
            --freeze) freeze=1; shift ;;
            --start) start=1; shift ;;
            *) echo "itf: unknown itf_guest_create option: $key" >&2; return 2 ;;
        esac
    done

    if [[ -z "$vmid" ]]; then
        vmid="$(itf_vmid_pick "$base")" || return 1
    elif ! itf_vmid_in_range "$vmid"; then
        echo "itf: --vmid $vmid outside reserved range ${ITF_VMID_FIRST}-${ITF_VMID_LAST}" >&2
        return 2
    fi

    local -a qargs=(
        create "$vmid"
        --name "$name"
        --bios seabios
        --ostype "$ITF_GUEST_OSTYPE"
        --memory "$mem"
        --cores "$cores"
        --scsihw virtio-scsi-pci
        --scsi0 "${ITF_GUEST_STORAGE}:${sysdisk}"
        --net0 "${ITF_GUEST_NET_MODEL},bridge=${ITF_BRIDGE}"
        --agent enabled=1
        --serial0 socket
        --vga serial0
        --onboot 0
    )
    if (( freeze )); then
        qargs+=(--freeze 1)
    fi
    if (( pooldisk > 0 )); then
        qargs+=(--scsi1 "${ITF_GUEST_STORAGE}:${pooldisk}")
    fi
    if [[ -n "$iso" ]]; then
        # Dir-storage ISO volids carry the PVE content prefix (iso/<name>).
        # Disk-first boot order: a blank system disk is not bootable, so
        # first boot still falls through to the installer ISO — but the
        # post-install reboot boots the disk.  CD-first order makes that
        # reboot land in the installer again (d-i ejects the tray, but the
        # QEMU reset that follows closes it), wedging the journey at guest
        # IP discovery forever.
        qargs+=(--ide2 "${ITF_ISO_STORAGE}:iso/${iso},media=cdrom" --boot "order=scsi0;ide2")
    else
        qargs+=(--boot "order=scsi0")
    fi

    itf_qm "$base" "${qargs[@]}" >&2 || return 1

    if (( start )); then
        itf_qm "$base" start "$vmid" >&2 || return 1
    fi
    echo "$vmid"
}

# itf_guest_start <base> <vmid>
itf_guest_start() { itf_qm "$1" start "$2"; }

# itf_guest_clone <name> [--base B] [--vmid V] [--mem MB] [--cores N]
#
# Full-clones the post-install baseline template (template-lib) and echoes
# the new VMID on stdout (everything else to stderr, like
# itf_guest_create).  Full clone by design: block storages such as the
# lvmthin itfguests have no linked clones, a thin-pool full clone copies
# only allocated blocks, and the clone is independent of the template —
# later template rebuilds cannot break a running journey's guest.
itf_guest_clone() {
    local name="$1"
    shift
    local base="${ITF_BASE_HOSTS[0]}" vmid="" mem="" cores=""
    local key

    while (( $# > 0 )); do
        key="$1"
        case "$key" in
            --base) base="$2"; shift 2 ;;
            --vmid) vmid="$2"; shift 2 ;;
            --mem) mem="$2"; shift 2 ;;
            --cores) cores="$2"; shift 2 ;;
            *) echo "itf: unknown itf_guest_clone option: $key" >&2; return 2 ;;
        esac
    done

    local tmpl_vmid
    tmpl_vmid="$(itf_template_vmid "$base")" || return 1
    if [[ -z "$tmpl_vmid" ]]; then
        echo "itf: no baseline template '$ITF_TEMPLATE_NAME' on $base — " \
            "run: itf template build" >&2
        return 1
    fi

    if [[ -z "$vmid" ]]; then
        vmid="$(itf_vmid_pick "$base")" || return 1
    elif ! itf_vmid_in_range "$vmid"; then
        echo "itf: --vmid $vmid outside reserved range ${ITF_VMID_FIRST}-${ITF_VMID_LAST}" >&2
        return 2
    fi

    itf_qm "$base" clone "$tmpl_vmid" "$vmid" --name "$name" --full 1 >&2 || return 1
    # Templates built from install journeys carry the installer-time CPU
    # freeze (stage_os pairs freeze with an explicit resume so the serial
    # console catches the first boot byte); a clone has no such pairing
    # and would sit paused forever if started as-is.  Clear unconditionally.
    itf_qm "$base" set "$vmid" --freeze 0 >&2 || return 1
    if [[ -n "$mem" || -n "$cores" ]]; then
        local -a sargs=(set "$vmid")
        [[ -n "$mem" ]] && sargs+=(--memory "$mem")
        [[ -n "$cores" ]] && sargs+=(--cores "$cores")
        itf_qm "$base" "${sargs[@]}" >&2 || return 1
    fi
    echo "$vmid"
}

# itf_guest_stop <base> <vmid>
#
# Graceful shutdown with a hard-stop fallback after 90s.
itf_guest_stop() {
    local base="$1" vmid="$2"
    itf_qm "$base" shutdown "$vmid" --timeout 90 || itf_qm "$base" stop "$vmid"
}

# itf_guest_destroy <base> <vmid>
#
# Removes the guest and its disks.  The VMID guard in itf_qm makes it
# impossible to destroy anything outside the reserved range.
itf_guest_destroy() {
    local base="$1" vmid="$2"
    itf_qm "$base" shutdown "$vmid" --timeout 60 >/dev/null 2>&1 \
        || itf_qm "$base" stop "$vmid" >/dev/null 2>&1 || true
    itf_qm "$base" destroy "$vmid" --destroy-unreferenced-disks 1 --purge
}

# itf_guest_snapshot <base> <vmid> <snapname>
itf_guest_snapshot() { itf_qm "$1" snapshot "$2" "$3"; }

# itf_guest_rollback <base> <vmid> <snapname> [--start]
itf_guest_rollback() {
    local base="$1" vmid="$2" snap="$3" start="${4:-}"
    itf_guest_stop "$base" "$vmid" >/dev/null 2>&1 || true
    itf_qm "$base" rollback "$vmid" "$snap" || return 1
    [[ "$start" == "--start" ]] && itf_guest_start "$base" "$vmid"
    return 0
}

# itf_guest_ip <base> <vmid> [timeout-seconds]
#
# Polls the qemu guest agent for the guest's first non-loopback IPv4
# address and echoes it.  The agent is installed by the preseed, so this
# works from the first boot after install.
itf_guest_ip() {
    local base="$1" vmid="$2" timeout="${3:-300}"
    local deadline=$(( SECONDS + timeout )) ip out
    while (( SECONDS < deadline )); do
        out="$(itf_qm "$base" guest cmd "$vmid" network-get-interfaces 2>/dev/null)" || true
        ip="$(printf '%s' "$out" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
# qm guest cmd prints the raw result list; pvesh-style wrappers may
# hand back the {"result": [...]} envelope instead.  Accept both.
ifaces = data.get("result", []) if isinstance(data, dict) else data
if not isinstance(ifaces, list):
    sys.exit(0)
for iface in ifaces:
    if not isinstance(iface, dict) or iface.get("name", "").startswith("lo"):
        continue
    for addr in iface.get("ip-addresses", []):
        if addr.get("ip-address-type") == "ipv4" and not addr["ip-address"].startswith("127."):
            print(addr["ip-address"])
            sys.exit(0)
' )" || true
        if [[ -n "$ip" ]]; then
            echo "$ip"
            return 0
        fi
        sleep 5
    done
    echo "itf: guest agent reported no usable IPv4 within ${timeout}s (vmid $vmid)" >&2
    return 1
}

# itf_iso_path [name]
#
# Absolute path of an installer ISO on a base host.  PVE dir storages
# keep ISO content under <path>/template/iso/.
itf_iso_path() {
    printf '%s/template/iso/%s' "$ITF_ISO_DIR" "${1:-$ITF_ISO_NAME}"
}

# itf_iso_fetch
#
# Downloads the installer ISO into the dev-side cache directory.
itf_iso_fetch() {
    mkdir -p "$ITF_CACHE_DIR" || return 1
    local dest="$ITF_CACHE_DIR/$ITF_ISO_NAME"
    if [[ -s "$dest" ]]; then
        echo "itf: ISO already cached: $dest"
        return 0
    fi
    echo "itf: fetching $ITF_DEBIAN_ISO_URL"
    curl -fL --retry 3 --progress-bar -o "$dest" "$ITF_DEBIAN_ISO_URL" || {
        rm -f "$dest"
        echo "itf: ISO download failed" >&2
        return 1
    }
    local size
    size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
    if (( size < 50 * 1024 * 1024 )); then
        echo "itf: cached ISO suspiciously small (${size} bytes) — refusing" >&2
        rm -f "$dest"
        return 1
    fi
    echo "itf: cached $dest ($(( size / 1024 / 1024 )) MiB)"
}

# itf_iso_upload <base-host> [name]
#
# Uploads a cached ISO to the base host's itf ISO storage.  The filename
# is config-validated to start with 'itf-', and the transfer is staged via
# /tmp as the unprivileged user before a guarded move into the ISO dir.
itf_iso_upload() {
    local base="$1" name="${2:-$ITF_ISO_NAME}"
    local src="$ITF_CACHE_DIR/$name"
    [[ -s "$src" ]] || {
        echo "itf: ISO not cached: $src — run 'itf iso fetch' first" >&2
        return 1
    }
    if [[ "$name" != itf-* ]]; then
        echo "itf: refusing to upload non-itf ISO name: $name" >&2
        return 1
    fi
    local tmp="/tmp/itf-iso-upload-$$"
    if ! itf_base_put "$base" "$src" "$tmp"; then
        itf_base_exec "$base" "rm -f $(printf '%q' "$tmp")" || true
        return 1
    fi
    if ! itf_base_exec "$base" \
        "mv $(printf '%q' "$tmp") $(printf '%q' "$(itf_iso_path "$name")")"; then
        itf_base_exec "$base" "rm -f $(printf '%q' "$tmp")" || true
        return 1
    fi
    itf_log_action "$base" "iso-upload: $name"
    echo "itf: uploaded $name to $base:$(itf_iso_path "$name")"
}

# itf_iso_customize <base-host> <kernel-append>
#
# Builds and uploads a boot-customized copy of the cached installer ISO
# (constant remote name "itf-boot.iso", overwritten on rebuild; a stamp
# file skips the rebuild while <kernel-append> is unchanged).  The
# custom isolinux.cfg turns on the bootloader serial console and
# auto-boots a default entry carrying <kernel-append> after 2 seconds,
# so the guest installs unattended with ZERO keystrokes over the
# serial line — typing the boot line interactively is lossy under
# nested virtualization (dropped characters garble auto= and derail
# the install into interactive prompts).  Requires 7z (extract) and
# genisoimage (rebuild) on the dev host.
itf_iso_customize() {
    local base="$1" append="$2"
    local name="itf-boot.iso"
    local out="$ITF_CACHE_DIR/$name"
    local stamp="$ITF_CACHE_DIR/${name%.iso}.append"

    # Only the final ISO name goes to stdout — callers capture stdout as
    # the value; everything informational goes to stderr.
    if [[ -s "$out" && -f "$stamp" && "$(cat "$stamp")" == "$append" ]]; then
        echo "itf: custom boot ISO already built: $out" >&2
    else

    local tool
    for tool in 7z genisoimage; do
        if ! command -v "$tool" > /dev/null 2>&1; then
            echo "itf: $tool is required to customize the boot ISO (not on PATH)" >&2
            return 1
        fi
    done
    [[ -s "$ITF_CACHE_DIR/$ITF_ISO_NAME" ]] || {
        echo "itf: pristine ISO not cached — run itf_iso_fetch first" >&2
        return 1
    }

    local tree="$ITF_CACHE_DIR/iso-tree"
    rm -rf "$tree"
    mkdir -p "$tree" || return 1
    if ! 7z x -y -o"$tree" "$ITF_CACHE_DIR/$ITF_ISO_NAME" > /dev/null; then
        rm -rf "$tree"
        echo "itf: ISO extraction failed" >&2
        return 1
    fi
    if [[ ! -f "$tree/isolinux/isolinux.bin" || ! -f "$tree/install.amd/vmlinuz" ]]; then
        rm -rf "$tree"
        echo "itf: unexpected ISO layout (missing isolinux/install.amd)" >&2
        return 1
    fi

    cat > "$tree/isolinux/isolinux.cfg" <<CFG
SERIAL 0 115200
DEFAULT itf
PROMPT 0
TIMEOUT 20
LABEL itf
  KERNEL /install.amd/vmlinuz
  INITRD /install.amd/initrd.gz
  APPEND $append
CFG

    if ! genisoimage -quiet -r -J -joliet-long \
            -b isolinux/isolinux.bin -c isolinux/boot.cat \
            -no-emul-boot -boot-load-size 4 -boot-info-table \
            -o "$out" "$tree"; then
        rm -rf "$tree"
        echo "itf: ISO rebuild failed" >&2
        return 1
    fi
    rm -rf "$tree"
    printf '%s' "$append" > "$stamp"
    fi
    # Always (re)upload: the base storage must hold this exact ISO even
    # when the cached build was reused.
    itf_iso_upload "$base" "$name" >&2 || return 1
    echo "$name"
}

# itf_preseed_render <outfile> <hostname>
#
# Writes a fully automated Debian preseed for a disposable test guest:
# root login locked (SSH-key-only), no desktop, serial console, openssh and
# the qemu guest agent installed, single-disk guided partitioning.  The
# file must be served over HTTP from dev (ssh-lib's itf_http_serve).
itf_preseed_render() {
    local out="$1" hostname="$2"
    local sshkey=""
    [[ -f "$ITF_SSH_KEY" ]] && sshkey="$(tr -d '\n' < "$ITF_SSH_KEY")"
    if [[ -z "$sshkey" ]]; then
        echo "itf: no public key at $ITF_SSH_KEY — guests would be unreachable" >&2
        return 1
    fi

    # Root gets a random password nobody records: a VALID crypt hash is
    # the only form every user-setup version honors silently (the "!"
    # lock value is ignored by trixie's user-setup, which then prompts
    # interactively and stalls the unattended install).  Root SSH stays
    # key-only regardless: sshd defaults to PermitRootLogin
    # prohibit-password and the late_command installs our key.
    local rootpw_hash=""
    rootpw_hash="$(openssl passwd -6 "$(head -c 32 /dev/urandom | base64 | tr -d '\n')")"
    if [[ -z "$rootpw_hash" || "$rootpw_hash" != \$6\$* ]]; then
        echo "itf: cannot generate root password hash — is openssl available?" >&2
        return 1
    fi

    cat > "$out" <<PRESEED
d-i debian-installer/locale string en_US
d-i keyboard-configuration/xkb-keymap select us

d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string $hostname
d-i netcfg/get_domain string localdomain

d-i mirror/country string manual
d-i mirror/http/hostname string deb.debian.org
d-i mirror/http/directory string /debian
d-i mirror/suite string stable
# country=manual drives the explicit mirror flow, which asks for a proxy
# even when none is wanted; preseed it blank to keep the install unattended.
d-i mirror/http/proxy string
# Close the remaining apt-setup questions the same way (observed live:
# any unanswered modal stops the install dead with a ticking clock).
# contrib=true: the guest models a user who followed the documented
# requirements — zfsutils-linux (needed by the three-RAIDZ1 test pools)
# is in Debian's contrib archive only; a stock main-only guest cannot
# apt-install it (itf finding F-005; check-prerequisites probes for this
# and prints a contrib note when it sees no installation candidate).
d-i apt-setup/services-select multiselect security, updates
d-i apt-setup/non-free-firmware boolean true
d-i apt-setup/non-free boolean false
d-i apt-setup/contrib boolean true

# Netinst booted as a CD-ROM: without these the installer blocks forever
# on the apt-cdrom-setup "Scan extra installation media?" dialog (observed
# live: modal box, ticking status clock, zero network/disk activity —
# easily misread as a hang).
apt-cdrom-setup apt-setup/cdrom/set-first boolean false
apt-cdrom-setup apt-setup/cdrom/set-next boolean false
apt-cdrom-setup apt-setup/cdrom/set-double boolean false

d-i clock-setup/utc boolean true
d-i time/zone string Etc/UTC

# Root login with a random unrecorded password: SSH key auth only.
d-i passwd/root-login boolean true
d-i passwd/root-password-crypted password $rootpw_hash
d-i passwd/make-user boolean false

# One partition, ext4, no swap questions.
d-i partman-auto/method string regular
d-i partman-auto/disk string /dev/sda
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

popularity-contest popularity-contest/participate boolean false
tasksel tasksel/first multiselect standard
d-i pkgsel/include string openssh-server qemu-guest-agent

grub-installer grub-installer/only_debian boolean true
grub-installer grub-installer/with_other_os boolean false
# The install runs with exactly one disk (the pool disk is hot-plugged
# only after the OS is up), so /dev/sda is unambiguous; the explicit pin
# stays as belt-and-braces against any future second disk at grub time.
d-i grub-installer/bootdev string /dev/sda

d-i finish-install/reboot_in_progress note

d-i preseed/late_command string \\
    in-target mkdir -p /root/.ssh ; \\
    echo "$sshkey" > /target/root/.ssh/authorized_keys ; \\
    in-target chmod 700 /root/.ssh ; \\
    in-target chmod 600 /root/.ssh/authorized_keys ; \\
    in-target sed -i \
        's/^#\?GRUB_CMDLINE_LINUX=.*/GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200n8"/' \
        /etc/default/grub ; \\
    in-target update-grub || true
PRESEED
}
