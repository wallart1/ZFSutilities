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

# itf_guest_clone <name> [--base B] [--template T] [--vmid V] [--mem MB] [--cores N]
#
# Full-clones a post-install baseline template (template-lib; default
# ITF_TEMPLATE_NAME, or the compute profile's name via --template) and
# echoes the new VMID on stdout (everything else to stderr, like
# itf_guest_create).  Full clone by design: block storages such as the
# lvmthin itfguests have no linked clones, a thin-pool full clone copies
# only allocated blocks, and the clone is independent of the template —
# later template rebuilds cannot break a running journey's guest.
itf_guest_clone() {
    local name="$1"
    shift
    local base="${ITF_BASE_HOSTS[0]}" template="${ITF_TEMPLATE_NAME:-}" vmid="" mem="" cores=""
    local key

    while (( $# > 0 )); do
        key="$1"
        case "$key" in
            --base) base="$2"; shift 2 ;;
            --template) template="$2"; shift 2 ;;
            --vmid) vmid="$2"; shift 2 ;;
            --mem) mem="$2"; shift 2 ;;
            --cores) cores="$2"; shift 2 ;;
            *) echo "itf: unknown itf_guest_clone option: $key" >&2; return 2 ;;
        esac
    done

    local tmpl_vmid
    tmpl_vmid="$(itf_template_vmid "$base" "$template")" || return 1
    if [[ -z "$tmpl_vmid" ]]; then
        echo "itf: no baseline template '$template' on $base — " \
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

# itf_iso_fetch [debian|pve]
#
# Downloads an installer ISO into the dev-side cache directory.  The
# selector names the configured ISO (Debian netinst for storage-role
# installs, Proxmox VE ISO for compute-role installs); it defaults to
# the Debian one so existing callers keep working.
itf_iso_fetch() {
    local sel="${1:-debian}" url name
    case "$sel" in
        debian) url="$ITF_DEBIAN_ISO_URL"; name="$ITF_ISO_NAME" ;;
        pve) url="$ITF_PVE_ISO_URL"; name="$ITF_PVE_ISO_NAME" ;;
        *)
            echo "itf: unknown ISO selector: $sel (expected debian|pve)" >&2
            return 2
            ;;
    esac
    if [[ -z "$url" || -z "$name" ]]; then
        echo "itf: ISO '$sel' is not configured in the site config" >&2
        return 1
    fi
    mkdir -p "$ITF_CACHE_DIR" || return 1
    local dest="$ITF_CACHE_DIR/$name"
    if [[ -s "$dest" ]]; then
        echo "itf: ISO already cached: $dest"
        return 0
    fi
    echo "itf: fetching $url"
    curl -fL --retry 3 --progress-bar -o "$dest" "$url" || {
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

# itf_pve_answers_render <outfile> <fqdn>
#
# Writes the Proxmox VE auto-installer answer file (answer TOML) for a
# disposable compute-role guest: root login locked to a random unrecorded
# password hash with SSH key auth (the installer's [global] root-ssh-keys
# does what the Debian preseed's late_command did), DHCP networking, one
# ext4 system disk, and the first-boot hook enabled.  Schema verified
# against the PVE 9.2 installer (proxmox-auto-installer 9.x).
itf_pve_answers_render() {
    local out="$1" fqdn="$2"
    # The autoinstaller requires a FULLY-qualified name with DHCP
    # networking ("either a fully-qualified domain name or extended
    # configuration for usage with DHCP") — a bare label like the
    # template build hostname aborts the install.  Qualify bare labels
    # with the same domain the Debian preseed pins (localdomain).
    [[ "$fqdn" == *.* ]] || fqdn+=".localdomain"
    local sshkey=""
    [[ -f "$ITF_SSH_KEY" ]] && sshkey="$(tr -d '\n' < "$ITF_SSH_KEY")"
    if [[ -z "$sshkey" ]]; then
        echo "itf: no public key at $ITF_SSH_KEY — guests would be unreachable" >&2
        return 1
    fi
    # A quote in the key comment would break the TOML basic string.
    if [[ "$sshkey" == *'"'* ]]; then
        echo "itf: public key at $ITF_SSH_KEY contains a double quote — unusable" >&2
        return 1
    fi
    # Same policy as the Debian preseed: a VALID random crypt hash nobody
    # records, never a lock value the installer might reject.
    local rootpw_hash=""
    rootpw_hash="$(openssl passwd -6 "$(head -c 32 /dev/urandom | base64 | tr -d '\n')")"
    if [[ -z "$rootpw_hash" || "$rootpw_hash" != \$6\$* ]]; then
        echo "itf: cannot generate root password hash — is openssl available?" >&2
        return 1
    fi
    cat > "$out" <<TOML
[global]
keyboard = "en-us"
country = "us"
fqdn = "$fqdn"
mailto = "root@$fqdn"
timezone = "UTC"
root-password-hashed = "$rootpw_hash"
root-ssh-keys = [
  "$sshkey",
]
reboot-mode = "reboot"

[network]
source = "from-dhcp"

[disk-setup]
filesystem = "ext4"
disk-list = ["sda"]

[first-boot]
source = "from-iso"
ordering = "network-online"
TOML
    # A TOML syntax error would only surface a full install later — fail
    # here instead (python3 is already an itf prerequisite).
    python3 -c "import tomllib, sys; tomllib.load(open(sys.argv[1], 'rb'))" "$out" \
        || { echo "itf: rendered PVE answer file is not valid TOML" >&2; return 1; }
    return 0
}

# itf_pve_first_boot_render <outfile>
#
# Writes the first-boot hook the PVE auto-installer copies into the
# installed system (it rides on the boot ISO as proxmox-first-boot and
# runs once, after network-online): the day-one admin work on a fresh
# PVE host — switch apt to the no-subscription repos (the ISO ships
# enterprise repos no test guest has credentials for) and install the
# qemu guest agent so the orchestrator can discover the guest's IP.
itf_pve_first_boot_render() {
    local out="$1"
    cat > "$out" <<'HOOK'
#!/bin/bash
# Embedded by the itf orchestrator; runs once on the installed system.
set -e
src_dir=/etc/apt/sources.list.d
# Enterprise repos have no credentials here; disable their deb822
# stanzas and add the pve-no-subscription group for this release.
# A deb822 file carries no Enabled line while true (the default), so
# the flag must be joined to the EXISTING stanza: appending after a
# blank line starts a new headerless stanza that apt rejects
# ("Malformed stanza 2 (type)").  Rewrite with trailing blanks
# stripped and exactly one newline, then append the field.
for f in "$src_dir"/pve-enterprise.sources "$src_dir"/ceph.sources; do
    [[ -f "$f" ]] || continue
    grep -q '^Enabled: false' "$f" && continue
    printf '%s\nEnabled: false\n' "$(cat "$f")" > "$f.new"
    mv "$f.new" "$f"
done
. /etc/os-release
cat > "$src_dir/proxmox-no-subscription.sources" <<SRC
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: ${VERSION_CODENAME}
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
SRC
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq qemu-guest-agent
systemctl enable --now qemu-guest-agent
echo "itf-first-boot-ok"
HOOK
}

# itf_pve_iso_customize <base-host> <fqdn>
#
# Builds and uploads the automated-install boot ISO for a compute-role
# guest from the cached Proxmox VE ISO (constant remote name
# "itf-pve-boot.iso", overwritten on rebuild; a stamp file of the
# rendered answers+hook skips rebuilds while they are unchanged).
#
# The PVE auto-installer flow (verified against the 9.2.1 ISO and the
# upstream assistant's own output):
#   - grub.cfg's FIRST entry becomes "Install Proxmox VE (Automated)"
#     with a 10 s menu timeout when auto-installer-mode.toml exists at
#     the ISO root — the stock grub.cfg already contains the entry, so
#     no boot-menu surgery is needed;
#   - the ONLY grub.cfg change here appends console=ttyS0,115200 to that
#     entry's kernel line so the install is watchable (and gateable)
#     over `qm terminal`;
#   - auto-installer-mode.toml (mode = "iso") makes proxmox-fetch-answer
#     read /cdrom/answer.toml from the medium itself — no network fetch,
#     no preseed HTTP server needed for PVE installs;
#   - the [first-boot] from-iso hook rides as proxmox-first-boot at the
#     ISO root and runs once on the installed system.
itf_pve_iso_customize() {
    local base="$1" fqdn="$2"
    # Qualify BEFORE the stamp below: the cache key must track the name
    # actually written into the answers file (itf_pve_answers_render
    # applies the same rule defensively).
    [[ "$fqdn" == *.* ]] || fqdn+=".localdomain"
    local name="itf-pve-boot.iso"
    local out="$ITF_CACHE_DIR/$name"
    local stamp="$ITF_CACHE_DIR/${name%.iso}.answers"

    # Only the final ISO name goes to stdout; everything informational
    # goes to stderr (mirrors itf_iso_customize).
    local work="$ITF_RUN_DIR/pve-iso-build"
    mkdir -p "$work"
    if ! itf_pve_answers_render "$work/answer.toml" "$fqdn"; then
        return 1
    fi
    itf_pve_first_boot_render "$work/proxmox-first-boot"
    # Stamp over the STABLE inputs only — the answers file itself embeds
    # a fresh random root-password hash on every render, which would
    # defeat the cache (the cached ISO simply keeps the hash it was
    # built with).
    local want_stamp
    want_stamp="$(printf '%s\n%s\n' "$fqdn" "$ITF_PVE_ISO_NAME"; \
        cat "$ITF_SSH_KEY" "$work/proxmox-first-boot" \
        | sha256sum | awk '{print $1}')"

    if [[ -s "$out" && -f "$stamp" && "$(cat "$stamp")" == "$want_stamp" ]]; then
        echo "itf: custom PVE boot ISO already built: $out" >&2
    else
        local tool
        for tool in 7z genisoimage python3; do
            if ! command -v "$tool" > /dev/null 2>&1; then
                echo "itf: $tool is required to customize the PVE boot ISO (not on PATH)" >&2
                return 1
            fi
        done
        [[ -s "$ITF_CACHE_DIR/$ITF_PVE_ISO_NAME" ]] || {
            echo "itf: PVE ISO not cached — run 'itf iso fetch pve' first" >&2
            return 1
        }

        local tree="$ITF_CACHE_DIR/pve-iso-tree"
        rm -rf "$tree"
        mkdir -p "$tree" || return 1
        # 7z extracts every regular file but REFUSES the ISO's relative
        # symlinks (the dists/ tree links into proxmox/packages, plus a
        # root "debian -> ." alias), logging each refusal as
        # "Dangerous (symbolic) link path was ignored : <path> : <target>"
        # and exiting non-zero.  The log is therefore the complete list
        # of what to restore by hand — and the rebuild stays faithful to
        # the stock repo layout instead of silently dropping links.
        local xlog="$work/pve-7z.log" xrc=0
        7z x -y -o"$tree" "$ITF_CACHE_DIR/$ITF_PVE_ISO_NAME" > /dev/null 2> "$xlog" \
            || xrc=$?
        if (( xrc != 0 && xrc != 2 )) \
                || grep -v 'Dangerous \(symbolic \)\?link path was ignored' "$xlog" \
                    | grep -q '^ERROR'; then
            rm -rf "$tree"
            echo "itf: PVE ISO extraction failed (see $xlog)" >&2
            return 1
        fi
        awk -F' : ' '/Dangerous (symbolic )?link path was ignored/ {print $2 "\t" $3}' \
            "$xlog" > "$work/pve-links.tsv"
        local rel target n_restore=0 n_bad=0
        while IFS=$'\t' read -r rel target; do
            [[ -n "$rel" && -n "$target" ]] || continue
            mkdir -p "$tree/$(dirname "$rel")"
            ln -sfn "$target" "$tree/$rel"
            n_restore=$((n_restore + 1))
            # Every restored link must resolve back inside the tree
            # (the root-level "debian -> ." alias resolves to the tree
            # root itself, which is fine).
            case "$(readlink -m "$tree/$rel")" in
                "$tree"|"$tree"/*) ;;
                *)
                    echo "itf: restored link escapes tree: $rel -> $target" >&2
                    n_bad=$((n_bad + 1))
                    ;;
            esac
        done < "$work/pve-links.tsv"
        if (( n_bad > 0 )); then
            rm -rf "$tree"
            return 1
        fi
        echo "itf: restored $n_restore symlinks dropped by 7z" >&2
        if [[ ! -f "$tree/boot/grub/grub.cfg" || ! -f "$tree/boot/linux26" \
                || ! -f "$tree/boot/grub/i386-pc/eltorito.img" ]]; then
            rm -rf "$tree"
            echo "itf: unexpected PVE ISO layout (missing grub/linux26/eltorito)" >&2
            return 1
        fi

        cp "$work/answer.toml" "$tree/answer.toml"
        # genisoimage -r keeps exec bits only where the source tree has
        # them; the post-hook runs this file on the installed system.
        install -m 0755 "$work/proxmox-first-boot" "$tree/proxmox-first-boot"
        printf 'mode = "iso"\npartition_label = "proxmox-ais"\n\n[http]\n' \
            > "$tree/auto-installer-mode.toml"

        # Serial console on the Automated entry — the only kernel-line
        # change.  Match the exact stock line to fail loudly if a future
        # ISO rewords it.
        if ! grep -q 'linux.*/boot/linux26.*proxmox-start-auto-installer$' \
                "$tree/boot/grub/grub.cfg"; then
            rm -rf "$tree"
            echo "itf: Automated boot entry not found in PVE grub.cfg" >&2
            return 1
        fi
        sed -i \
            's#\(linux.*/boot/linux26.*proxmox-start-auto-installer\)$#\1 console=ttyS0,115200#' \
            "$tree/boot/grub/grub.cfg"

        # El Torito BIOS boot via grub's image; -boot-info-table is an
        # isolinux convention grub does not use, so it is deliberately
        # omitted here.
        if ! genisoimage -quiet -r -J -joliet-long \
                -b boot/grub/i386-pc/eltorito.img \
                -c boot/boot.cat \
                -no-emul-boot -boot-load-size 4 \
                -o "$out" "$tree"; then
            rm -rf "$tree"
            echo "itf: PVE ISO rebuild failed" >&2
            return 1
        fi

        # grub's El Torito image carries a 16-byte load record at boot
        # sector offset 8 — {2048-sector count, load LBA, byte size, tag}
        # — written by xorriso when Proxmox mastered the stock ISO.  The
        # LBA is an ABSOLUTE sector number, and genisoimage does not
        # re-patch it: a rebuilt ISO whose layout moved the boot image
        # makes boot.img fetch its core from whatever now lives at the
        # stock sector, and the guest hangs silently right after
        # "Booting from DVD/CD...".  Re-point the LBA at the boot image's
        # actual sector in the rebuilt ISO — the same patch xorriso
        # applies at master time — and fail loudly when the field does
        # not hold the stock value (a future ISO mastering change).
        if ! python3 - "$ITF_CACHE_DIR/$ITF_PVE_ISO_NAME" "$out" <<'PYEOF'
import struct
import sys


def boot_rba(path):
    with open(path, "rb") as f:
        f.seek(17 * 2048 + 71)
        cat = struct.unpack("<I", f.read(4))[0]
        f.seek(cat * 2048)
        entry = f.read(64)
    if entry[0] != 1 or entry[30:32] != b"\x55\xaa":
        raise SystemExit(f"no El Torito catalog found in {path}")
    boot = entry[32:64]
    if boot[0] != 0x88 or boot[1] != 0x00:
        raise SystemExit(f"unexpected El Torito entry in {path}")
    return struct.unpack("<I", boot[8:12])[0]


stock_rba = boot_rba(sys.argv[1])
new_rba = boot_rba(sys.argv[2])
with open(sys.argv[2], "r+b") as f:
    f.seek(new_rba * 2048 + 12)
    old = struct.unpack("<I", f.read(4))[0]
    if old != stock_rba:
        raise SystemExit(
            f"boot image LBA field holds {old}, expected stock {stock_rba}"
        )
    f.seek(new_rba * 2048 + 12)
    f.write(struct.pack("<I", new_rba))
PYEOF
        then
            rm -rf "$tree" "$out"
            echo "itf: PVE boot-image LBA re-patch failed" >&2
            return 1
        fi
        rm -rf "$tree"
        printf '%s' "$want_stamp" > "$stamp"
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
