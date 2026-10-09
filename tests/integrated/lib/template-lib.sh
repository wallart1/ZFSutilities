#!/usr/bin/env bash
# tests/integrated/lib/template-lib.sh
#
# The post-install baseline template: a guest built once through the real
# first-time-user path (OS install, product install, OS package updates,
# boot health gate), then converted to a Proxmox template.  Journeys clone
# it (itf_guest_clone / itf_journey_stage_from_template) and start at the
# post-install point in a minute or two instead of repeating the full
# install every run.
#
# Lifecycle (all base-host access through the base-lib guard):
#   itf template status                     presence + stamp, per role
#   itf template build [--base B]           rebuild from scratch, stamp,
#         [--profile storage|compute]       convert (see profiles below)
#         [--sw-source ..] [--force]
#   itf template destroy [--base B] [--profile ..]  remove the template
#
# Two profiles share this machinery:
#   storage  the Debian product baseline (site-config ITF_TEMPLATE_NAME,
#            expected on the storage base): OS + product install + updates
#            — the j01 first-time-user path.
#   compute  the PVE-only baseline (ITF_COMPUTE_TEMPLATE_NAME, expected on
#            the compute base): installed from the Proxmox VE ISO via the
#            auto-installer, then package updates.  NO product install —
#            the installer's deploy push to the compute host is part of
#            what the two-node journey exercises.
#
# Rebuilds are ALWAYS from scratch, never an in-place upgrade: the baseline
# must keep first-time-user fidelity — no version-dir drift, no
# upgrade-path contamination.  A rebuild costs one unattended install (≈ a
# j01 run) and doubles as a smoke run of the software it installs.
#
# The stamp rides in the PVE description field (`qm set --description`,
# read back via `qm config`): it travels with the template and needs no
# new write paths on the base host.  One line only — PVE renders multi-line
# values with indented continuations that are easy to mis-parse — and the
# marker uses '|' not ':': a colon after a name-shaped token reads as a
# storage reference to the confinement guard.
#
# Identity is the NAME (site-config ITF_TEMPLATE_NAME /
# ITF_COMPUTE_TEMPLATE_NAME), not the VMID: rebuilds occupy a fresh VMID,
# and the guard's name-based protection picks the new one up the moment
# the rename lands.

if [[ -n "${ITF_LIB_TEMPLATE_LOADED:-}" ]]; then
    return 0 2>/dev/null || true
fi
ITF_LIB_TEMPLATE_LOADED=1

# itf_template_vmid <base-host> [name]
#
# Echoes the named template's VMID, or nothing when absent.  Thin wrapper
# so journey/guest code never touches the guard's private resolver.
itf_template_vmid() { _itf_template_vmid_resolve "$1" "${2:-}"; }

# itf_template_stamp_render <profile> <src-key> <src-val> <version> <kernel> <rev>
#
# Echoes the one-line stamp.  <src-key>/<src-val> is what drives
# freshness: "sw-source release|dev-tarball" for the storage profile,
# "pve-iso <iso-name>" for the compute profile.  Freshness matching is
# by "key=value" substring (_itf_template_fresh /
# _itf_template_compute_fresh), so field order is conventional, not
# load-bearing.  The timestamp uses hyphens, not colons: PVE
# percent-encodes colons when rendering the description in `qm config`
# (observed live: built=… %3A…), and a colon-free stamp round-trips
# verbatim.
itf_template_stamp_render() {
    # src-key feeds a "key=value" stamp field; keep it name-shaped.
    [[ "$2" =~ ^[a-z][a-z-]*$ ]] || return 1
    printf 'itf-stamp| profile=%s %s=%s version=%s rev=%s kernel=%s built=%s' \
        "$1" "$2" "$3" "$4" "$6" "$5" "$(date -u '+%Y-%m-%dT%H-%M-%SZ')"
}

# itf_template_stamp_parse <string>
#
# Validates a raw stamp and echoes it normalized (marker dropped).  Fails
# on blank or foreign descriptions.  The source field is sw-source=
# (storage profile) or pve-iso= (compute profile); profile= itself is
# optional so stamps from before the two-template split still parse
# (they simply never match a compute freshness check).
itf_template_stamp_parse() {
    local s="${1:-}"
    [[ "$s" == "itf-stamp| "* ]] || return 1
    s="${s#itf-stamp| }"
    local f
    for f in version rev kernel built; do
        [[ "$s" == *"$f="* ]] || return 1
    done
    [[ "$s" == *"sw-source="* || "$s" == *"pve-iso="* ]] || return 1
    printf '%s' "$s"
}

# itf_template_stamp_read <base-host> <vmid>
#
# Reads the template's stamp from `qm config` and echoes the normalized
# form.  Fails when the description is absent or not an itf stamp.
itf_template_stamp_read() {
    local desc
    desc="$(itf_qm "$1" config "$2" 2>/dev/null | sed -n 's/^description: //p')"
    itf_template_stamp_parse "$desc"
}

# _itf_template_would_version <sw-source>
#
# Echoes the product version a build with <sw-source> would install, for
# freshness comparison.  release: the latest published GitHub release;
# dev-tarball: this repository's VERSION.
_itf_template_would_version() {
    local ver=""
    if [[ "$1" == release ]]; then
        # Pull the latest release tag from the GitHub API JSON reply: the
        # sed keeps only the capture group inside the quoted "tag_name"
        # value ("v0.1.2" -> "0.1.2" via the ${ver#v} strip below).
        ver="$(curl -fsS --max-time 30 \
            "https://api.github.com/repos/${ITF_GITHUB_REPO}/releases/latest" \
            2>/dev/null \
            | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
        printf '%s' "${ver#v}"
    else
        cat "$ITF_ROOT/../../VERSION" 2>/dev/null
    fi
}

# _itf_template_fresh <stamp> <sw-source>
#
# True when an existing template's stamp already reflects what a build
# with <sw-source> would produce (release: source+version; dev-tarball
# adds the repo rev — every commit is a new dev baseline).
_itf_template_fresh() {
    local stamp="$1" src="$2" want ver
    [[ -n "$stamp" ]] || return 1
    ver="$(_itf_template_would_version "$src")"
    [[ -n "$ver" ]] || return 1
    want="sw-source=$src version=$ver"
    if [[ "$src" == dev-tarball ]]; then
        want+=" rev=$(git -C "$ITF_ROOT/../.." rev-parse --short HEAD 2>/dev/null || echo unknown)"
    fi
    [[ " $stamp " == *" $want "* ]]
}

# _itf_template_compute_fresh <stamp>
#
# True when an existing compute-profile template's stamp already reflects
# the configured PVE ISO.  The compute baseline carries no product (the
# two-node installer's deploy push is part of what j05 exercises), so the
# ISO name — which encodes the PVE release — is the freshness driver;
# package-update drift inside is what --force is for.
_itf_template_compute_fresh() {
    local stamp="$1"
    [[ -n "$stamp" ]] || return 1
    [[ -n "${ITF_PVE_ISO_NAME:-}" ]] || return 1
    [[ " $stamp " == *" profile=compute pve-iso=${ITF_PVE_ISO_NAME} "* ]]
}

# itf_template_os_upgrade <guest-ip> [profile]
#
# The OS-package-update stage of the build, so every clone starts from a
# current OS at zero per-journey cost.  On the storage profile it runs
# AFTER the product install: upgrading first would leave the ZFS module
# untestable at this point (zfsutils-linux arrives with the product
# prerequisites), and upgrading after install additionally proves an
# installed system survives a routine `apt full-upgrade` — exactly what a
# real user's machine does weeks after install.  Applies all pending
# updates, reboots onto a new kernel when one was installed, and
# health-gates the result: newest kernel running, plus the profile's
# stack check (storage: ZFS module loadable; compute: pveversion and a
# live pvestatd — a PVE host whose status daemon is dead is not a
# usable compute baseline).
itf_template_os_upgrade() {
    local ip="$1" profile="${2:-storage}"
    local up_log="$ITF_RUN_DIR/template-upgrade.log"
    # itf_guest_exec takes the whole command as ONE argument — build it in
    # a variable so line-wrapping can never silently drop words (a split
    # into several quoted args once truncated the command at "-qq" and the
    # guest saw apt-get with no command word).
    local upgrade_cmd
    upgrade_cmd="apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get -y -qq "
    upgrade_cmd+="-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "
    upgrade_cmd+="full-upgrade"
    if itf_guest_exec "$ip" "$upgrade_cmd" > "$up_log" 2>&1; then
        itf_step pass "template: OS packages updated" "see template-upgrade.log"
    else
        itf_step fail "template: OS packages updated" "see template-upgrade.log"
        return 1
    fi
    itf_artifact "template-upgrade" "$up_log"

    # Reboot only when a newer kernel than the running one is installed.
    # The probe ALWAYS answers yes/no (an empty answer means the transport
    # hiccuped, not that no reboot is needed — a silent empty once skipped
    # a required reboot and the boot gate caught it downstream); retry a
    # bounded number of times and fail loudly, with the probe's own log,
    # when no answer arrives.  A plain [[ ]] && echo yes form cannot make
    # that distinction and is deliberately not used.
    local probe_log="$ITF_RUN_DIR/template-reboot-probe.log"
    local reboot_needed=""
    for _ in 1 2 3; do
        # shellcheck disable=SC2016  # the expansions run in the guest
        reboot_needed="$(itf_guest_exec "$ip" '
            newest=$(ls /boot/vmlinuz-* 2>/dev/null | sort -V | tail -1)
            if [[ -n "$newest" && "vmlinuz-$(uname -r)" != "$(basename "$newest")" ]]
            then echo yes; else echo no; fi
        ' 2>"$probe_log")"
        [[ "$reboot_needed" == yes || "$reboot_needed" == no ]] && break
        sleep 10
    done
    if [[ "$reboot_needed" != yes && "$reboot_needed" != no ]]; then
        itf_step fail "template: reboot decision" \
            "probe gave no answer in 3 attempts — see template-reboot-probe.log"
        itf_artifact "reboot-probe" "$probe_log"
        return 1
    fi
    if [[ "$reboot_needed" == yes ]]; then
        itf_guest_exec "$ip" reboot > /dev/null 2>&1 || true
        # Wait for the old boot to drop ssh before waiting for the new
        # one, or wait-ssh can succeed against the dying instance.
        local deadline=$(( SECONDS + 120 ))
        while (( SECONDS < deadline )); do
            itf_guest_exec "$ip" true > /dev/null 2>&1 || break
            sleep 5
        done
        if itf_wait_ssh "$ip" 600; then
            itf_step pass "template: rebooted onto new kernel" \
                "now running $(itf_guest_exec "$ip" 'uname -r' 2>/dev/null)"
        else
            itf_step fail "template: rebooted onto new kernel" "ssh did not return in 600s"
            return 1
        fi
    else
        itf_step info "template: no reboot needed" "running kernel is the newest installed"
    fi

    local gate_log="$ITF_RUN_DIR/template-gate.log"
    # shellcheck disable=SC2016  # the expansions run in the guest
    local gate_script
    if [[ "$profile" == compute ]]; then
        gate_script='
            set -e
            newest=$(ls /boot/vmlinuz-* | sort -V | tail -1)
            [[ "vmlinuz-$(uname -r)" == "$(basename "$newest")" ]]
            systemctl is-active --quiet pvestatd
            echo "gate-ok kernel=$(uname -r) pve=$(pveversion)"
        '
    else
        gate_script='
            set -e
            newest=$(ls /boot/vmlinuz-* | sort -V | tail -1)
            [[ "vmlinuz-$(uname -r)" == "$(basename "$newest")" ]]
            modprobe zfs
            echo "gate-ok kernel=$(uname -r) zfs=$(cat /sys/module/zfs/version)"
        '
    fi
    if itf_guest_exec "$ip" "$gate_script" > "$gate_log" 2>&1; then
        itf_step pass "template: boot health gate" "$(tail -1 "$gate_log")"
    else
        itf_step fail "template: boot health gate" \
            "newest kernel / profile stack check failed — see template-gate.log"
        itf_artifact "template-gate" "$gate_log"
        return 1
    fi
    itf_artifact "template-gate" "$gate_log"
    return 0
}

# itf_template_clear_snapshots <base-host> <vmid>
#
# Deletes every PVE snapshot on the build VM: `qm template` refuses to
# convert a VM that still carries snapshots (observed live: the
# os-installed checkpoint stage_os takes).  The `current` pseudo-entry
# listsnapshot prints is the "you are here" marker, not a snapshot, and
# is skipped.
itf_template_clear_snapshots() {
    local base="$1" vmid="$2"
    local names snap
    names="$(itf_qm "$base" listsnapshot "$vmid" 2>/dev/null | awk '
        {
            # Snapshot lines lead with an arrow field (`->`); the name is
            # the token right after it, and `current` is the you-are-here
            # pseudo-entry listsnapshot prints, not a snapshot.
            for (i = 1; i < NF; i++)
                if ($i ~ /->$/) {
                    n = $(i + 1)
                    if (n != "current") print n
                    break
                }
        }')"
    [[ -n "$names" ]] || return 0
    for snap in $names; do
        if ! itf_qm "$base" delsnapshot "$vmid" "$snap" > /dev/null 2>&1; then
            itf_step fail "template: snapshot removed" \
                "qm delsnapshot $vmid $snap refused (see run report)"
            return 1
        fi
    done
    # shellcheck disable=SC2086  # one printf arg per snapshot name
    itf_step pass "template: snapshots removed" \
        "$(printf '%s ' $names)— qm template requires a snapshot-free VM"
    return 0
}

# itf_template_status
#
# Human-readable template presence + stamp, one line per role: the
# storage baseline where the site expects it, the compute baseline when
# the site configures two-node keys.
itf_template_status() {
    local vmid stamp
    local sbase="${ITF_STORAGE_BASE:-${ITF_BASE_HOSTS[0]:-}}"
    if [[ -n "$sbase" ]]; then
        vmid="$(itf_template_vmid "$sbase")" || vmid=""
        if [[ -n "$vmid" ]]; then
            stamp="$(itf_template_stamp_read "$sbase" "$vmid" 2>/dev/null)" \
                || stamp="(no/foreign stamp — rebuild: itf template build --force)"
            echo "  $sbase: $ITF_TEMPLATE_NAME = vmid $vmid — ${stamp#itf-stamp| }"
        else
            echo "  $sbase: no template '$ITF_TEMPLATE_NAME' (create: itf template build)"
        fi
    fi
    if [[ -n "${ITF_COMPUTE_BASE:-}" && -n "${ITF_COMPUTE_TEMPLATE_NAME:-}" ]]; then
        vmid="$(itf_template_vmid "$ITF_COMPUTE_BASE" "$ITF_COMPUTE_TEMPLATE_NAME")" \
            || vmid=""
        if [[ -n "$vmid" ]]; then
            stamp="$(itf_template_stamp_read "$ITF_COMPUTE_BASE" "$vmid" 2>/dev/null)" \
                || stamp="(no/foreign stamp — rebuild: itf template build --force)"
            echo "  $ITF_COMPUTE_BASE: $ITF_COMPUTE_TEMPLATE_NAME" \
                "= vmid $vmid — ${stamp#itf-stamp| }"
        else
            echo "  $ITF_COMPUTE_BASE: no template '$ITF_COMPUTE_TEMPLATE_NAME'" \
                "(create: itf template build --base $ITF_COMPUTE_BASE --profile compute)"
        fi
    fi
}

# itf_template_build [--base B] [--profile storage|compute] [--sw-source ..] [--force]
#
# Rebuilds a baseline template from scratch through the shared journey
# stages (storage: Debian OS + product install; compute: PVE from the
# auto-installer ISO).  Refuses nothing except a fresh template without
# --force; any failure leaves the previous template untouched and the
# attempt behind under the name <template>-build, which the next build
# cleans up.
itf_template_build() {
    local sw_source="$ITF_SW_SOURCE" force=0 profile=storage base=""
    while (( $# > 0 )); do
        case "$1" in
            --sw-source) sw_source="$2"; shift 2 ;;
            --force) force=1; shift ;;
            --base) base="$2"; shift 2 ;;
            --profile) profile="$2"; shift 2 ;;
            *) echo "itf: unknown itf_template_build option: $1" >&2; return 2 ;;
        esac
    done
    case "$sw_source" in
        release|dev-tarball) ;;
        *) echo "itf: --sw-source must be 'release' or 'dev-tarball'" >&2; return 2 ;;
    esac
    case "$profile" in
        storage|compute) ;;
        *) echo "itf: --profile must be 'storage' or 'compute'" >&2; return 2 ;;
    esac

    local template_name
    if [[ "$profile" == compute ]]; then
        template_name="${ITF_COMPUTE_TEMPLATE_NAME:-}"
        base="${base:-${ITF_COMPUTE_BASE:-${ITF_BASE_HOSTS[0]:-}}}"
        if [[ -z "$template_name" || -z "${ITF_PVE_ISO_NAME:-}" ]]; then
            echo "itf: compute profile needs ITF_COMPUTE_TEMPLATE_NAME and" \
                "ITF_PVE_ISO_URL/ITF_PVE_ISO_NAME in the site config" >&2
            return 2
        fi
    else
        template_name="${ITF_TEMPLATE_NAME:-}"
        base="${base:-${ITF_STORAGE_BASE:-${ITF_BASE_HOSTS[0]:-}}}"
    fi
    if [[ -z "$template_name" || -z "$base" ]]; then
        echo "itf: no template name or base host to build on" >&2
        return 2
    fi
    local build_name="${template_name}-build"

    local old_vmid old_stamp
    old_vmid="$(itf_template_vmid "$base" "$template_name")"
    if [[ -n "$old_vmid" ]]; then
        old_stamp="$(itf_template_stamp_read "$base" "$old_vmid" 2>/dev/null)" || old_stamp=""
        local fresh=0
        if (( ! force )); then
            if [[ "$profile" == compute ]]; then
                _itf_template_compute_fresh "$old_stamp" && fresh=1
            else
                _itf_template_fresh "$old_stamp" "$sw_source" && fresh=1
            fi
        fi
        if (( fresh )); then
            itf_step skip "template build" \
                "already fresh — $old_stamp; rerun with --force to rebuild"
            return 0
        fi
    fi

    # A leftover <template>-build VM marks an interrupted build attempt.
    local leftover_vmid
    leftover_vmid="$(itf_qm "$base" list 2>/dev/null \
        | awk -v n="$build_name" '$2 == n {print $1; exit}')"
    if [[ -n "$leftover_vmid" ]]; then
        itf_step info "template: leftover build VM removed" "vmid $leftover_vmid"
        itf_guest_destroy "$base" "$leftover_vmid" > /dev/null 2>&1 || true
    fi

    # The baseline IS the first-time-user install: reuse the journey
    # stages verbatim.  The hostname rides the template into every clone.
    # shellcheck disable=SC1090  # dynamic path into the journeys tree
    source "$ITF_ROOT/journeys/common.sh"
    local build_hostname="${template_name//_/-}"
    if [[ "$profile" == compute ]]; then
        itf_journey_stage_pve_os "$build_name" "$build_hostname" \
            --base "$base" || return 1
    else
        itf_journey_stage_os "$build_name" "$build_hostname" --base "$base" || return 1
        itf_journey_stage_install "$J_GUEST_IP" || return 1
        itf_journey_verify_installed "$J_GUEST_IP"
    fi
    local guest_ip="$J_GUEST_IP"

    itf_template_os_upgrade "$guest_ip" "$profile" || return 1
    if [[ "$profile" == storage ]]; then
        # Re-verify the product wiring after any upgrade reboot.
        itf_journey_verify_installed "$guest_ip"
    fi

    # Stamp inputs from the installed system itself, not from what we
    # intended to install.
    local version kernel rev stamp src_key src_val
    if [[ "$profile" == compute ]]; then
        version="$(itf_guest_exec "$guest_ip" 'pveversion' 2>/dev/null)"
        src_key=pve-iso
        src_val="$ITF_PVE_ISO_NAME"
    else
        version="$(itf_guest_exec "$guest_ip" \
            'cat /usr/local/lib/zfsutilities/current/VERSION' 2>/dev/null)"
        src_key=sw-source
        src_val="$sw_source"
    fi
    kernel="$(itf_guest_exec "$guest_ip" 'uname -r' 2>/dev/null)"
    rev="$(git -C "$ITF_ROOT/../.." rev-parse --short HEAD 2>/dev/null || echo unknown)"
    stamp="$(itf_template_stamp_render "$profile" "$src_key" "$src_val" \
        "$version" "$kernel" "$rev")"

    local vmid="$J_VMID"
    itf_guest_stop "$base" "$vmid" > "$ITF_RUN_DIR/template-shutdown.log" 2>&1 || true
    # Snapshot-free before conversion (qm template refuses otherwise).
    itf_template_clear_snapshots "$base" "$vmid" || return 1
    # Drop the installer-time CPU freeze inherited from the install
    # stages' freeze-and-resume console-capture flow: nothing resumes a
    # clone, so the template must boot as soon as a clone is started.
    if itf_qm "$base" set "$vmid" --freeze 0 > /dev/null 2>&1; then
        itf_step pass "template: freeze cleared" \
            "install-time CPU freeze dropped — clones boot unattended"
    else
        itf_step fail "template: freeze cleared" \
            "qm set --freeze 0 failed on vmid $vmid"
        return 1
    fi

    # Convert BEFORE touching the old template, while the VM still carries
    # the -build name (guard protection tracks the template name): every
    # failure below leaves the old baseline in place and the attempt
    # recoverable by the leftover cleanup on the next build.
    if itf_qm "$base" set "$vmid" --description "$stamp" > /dev/null 2>&1 \
            && itf_qm "$base" template "$vmid" > /dev/null 2>&1; then
        itf_step pass "template: converted to template" \
            "vmid $vmid stamped: ${stamp#itf-stamp| }"
    else
        itf_step fail "template: converted to template" "qm template failed on vmid $vmid"
        return 1
    fi
    if [[ -n "$old_vmid" && "$old_vmid" != "$vmid" ]]; then
        if ITF_TEMPLATE_OVERRIDE=1 itf_qm "$base" destroy "$old_vmid" \
                --destroy-unreferenced-disks 1 --purge > /dev/null 2>&1; then
            itf_step info "template: previous template removed" "vmid $old_vmid"
        else
            itf_step fail "template: previous template removed" \
                "vmid $old_vmid — destroy it manually, then rerun the build"
            return 1
        fi
    fi
    # Rename last: from this moment the guard's name-based protection and
    # every clone start hitting the new template.
    if itf_qm "$base" set "$vmid" --name "$template_name" > /dev/null 2>&1; then
        itf_step pass "template ready" \
            "$template_name = vmid $vmid ($src_val $version) — journeys clone it"
    else
        itf_step fail "template rename" \
            "qm set --name failed on vmid $vmid — finish manually (see guest.txt)"
        return 1
    fi
    return 0
}

# itf_template_destroy [--base B] [--profile storage|compute]
#
# Removes the template.  Clones are independent (full clones), so no guest
# is affected; the override is scoped to this one guarded call.
itf_template_destroy() {
    local profile=storage base=""
    while (( $# > 0 )); do
        case "$1" in
            --base) base="$2"; shift 2 ;;
            --profile) profile="$2"; shift 2 ;;
            *) echo "itf: unknown itf_template_destroy option: $1" >&2; return 2 ;;
        esac
    done
    case "$profile" in
        storage|compute) ;;
        *) echo "itf: --profile must be 'storage' or 'compute'" >&2; return 2 ;;
    esac

    local template_name
    if [[ "$profile" == compute ]]; then
        template_name="${ITF_COMPUTE_TEMPLATE_NAME:-}"
        base="${base:-${ITF_COMPUTE_BASE:-${ITF_BASE_HOSTS[0]:-}}}"
    else
        template_name="${ITF_TEMPLATE_NAME:-}"
        base="${base:-${ITF_STORAGE_BASE:-${ITF_BASE_HOSTS[0]:-}}}"
    fi
    if [[ -z "$template_name" || -z "$base" ]]; then
        echo "itf: no template name or base host to destroy on" >&2
        return 2
    fi

    local vmid
    vmid="$(itf_template_vmid "$base" "$template_name")" || vmid=""
    if [[ -z "$vmid" ]]; then
        echo "itf: no template '$template_name' on $base" >&2
        return 1
    fi
    if ITF_TEMPLATE_OVERRIDE=1 itf_qm "$base" destroy "$vmid" \
            --destroy-unreferenced-disks 1 --purge; then
        echo "itf: destroyed template '$template_name' (vmid $vmid) on $base"
        return 0
    fi
    return 1
}
