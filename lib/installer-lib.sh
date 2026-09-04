#!/bin/bash
# installer-lib.sh
# Shared helper functions for ZFSutilities installers.
#
# This file is sourced by install-single-node and install-two-node.
# It provides interactive prompts, explanations, safe remediation
# helpers, and prerequisite-failure parsing for the prerequisite phase.

# Associative array: installer_failures[name]=apt_package
# Populated by parse_check_prerequisites_failures.
declare -A installer_failures

# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------
# ask_yn is provided by bashinit, which the installers source before
# sourcing this library.

# ------------------------------------------------------------------
# Explanations
# ------------------------------------------------------------------

explain_prerequisite() {
    local name="$1"
    local description="$2"
    local why_needed="$3"
    local remediation="$4"

    echo ""
    echo "  ✗ $name"
    echo "    What it is: $description"
    echo "    Why it is needed: $why_needed"
    echo "    How the installer will fix it:"
    echo "      $remediation"
}

explain_doc_server() {
    echo ""
    echo "  Documentation (MkDocs)"
    echo "    What it provides:"
    echo "      • The HTML documentation site used by the GUI viewer"
    echo "      • A readable, searchable local copy of all guides and reference"
    echo "      • Automatic rebuilding of the site during installation"
    echo ""
    echo "    Why it is required:"
    echo "      • The GUI documentation viewer and local browser docs need the"
    echo "        built site/ directory"
    echo "      • It is part of a complete ZFSutilities installation"
    echo ""
    echo "    Steps the installer will take:"
    echo "      1. Try to install MkDocs and the Material theme from apt:"
    echo "         apt-get install mkdocs mkdocs-material"
    echo "      2. If apt packages are unavailable, use pip3 with"
    echo "         --break-system-packages (required on modern Debian/Ubuntu)."
    echo "      3. Verify that mkdocs and the Material theme are installed"
}

# ------------------------------------------------------------------
# Remediation
# ------------------------------------------------------------------

# Run apt-get update if it has not been run recently, then install packages.
# Returns 0 on success, non-zero on failure.
apt_install() {
    local packages=("$@")

    echo ""
    echo "  Updating package lists..."
    if ! apt-get update -qq; then
        echo "  ✗ Failed to update package lists." >&2
        return 1
    fi

    echo "  Installing: ${packages[*]}"
    if apt-get install -y "${packages[@]}"; then
        echo "  ✓ Installed: ${packages[*]}"
        return 0
    else
        echo "  ✗ Failed to install: ${packages[*]}" >&2
        return 1
    fi
}

# Install the documentation server (MkDocs).
# Returns 0 on success, non-zero on failure.
install_doc_server() {
    echo ""
    echo "  Installing mkdocs and mkdocs-material..."

    # Prefer distribution packages because modern Debian/Ubuntu block
    # system-wide pip installs (PEP 668). Fall back to pip3 only if the
    # user explicitly accepts the --break-system-packages override.
    if apt_install mkdocs mkdocs-material; then
        echo "  ✓ mkdocs installed from distribution packages"
        return 0
    fi

    echo ""
    echo "  Distribution package installation failed."
    echo "  Modern Debian/Ubuntu systems prevent system-wide pip installs by default."
    echo "  The installer can retry using pip3 with --break-system-packages, but"
    echo "  this may conflict with Python packages managed by apt."

    if ! ask_yn "Retry mkdocs installation with --break-system-packages?" "N"; then
        echo "  Skipped pip-based installation."
        return 1
    fi

    echo ""
    echo "  Ensuring python3-pip is available..."
    if ! command -v pip3 >/dev/null 2>&1; then
        if ! apt_install python3-pip; then
            echo "  ✗ Could not install python3-pip." >&2
            return 1
        fi
    else
        echo "  ✓ pip3 is already installed"
    fi

    echo ""
    echo "  Installing mkdocs and mkdocs-material via pip3..."
    # Pin mkdocs<2 to avoid the incompatible MkDocs 2.0 rewrite until the
    # project migrates to Zensical. Material for MkDocs 9.7.5+ enforces this
    # itself, but pinning here protects earlier versions and non-apt installs.
    if pip3 install --break-system-packages "mkdocs<2" mkdocs-material; then
        echo "  ✓ mkdocs installed"
        return 0
    else
        echo "  ✗ Could not install mkdocs/material via pip3." >&2
        return 1
    fi
}

# ------------------------------------------------------------------
# Prerequisite parsing and handling
# ------------------------------------------------------------------

# Parse failures from check-prerequisites --list-failures output.
# Populates the associative array installer_failures[name]=package.
parse_check_prerequisites_failures() {
    local output="$1"
    local line name package

    # Clear any existing entries
    installer_failures=()

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        # Format: category|name|package|message
        line="${line#*|}"      # skip category
        name="${line%%|*}"; line="${line#*|}"
        package="${line%%|*}"; line="${line#*|}"
        # message is the remainder; we only need name→package
        installer_failures["$name"]="$package"
    done <<< "$output"
}

# Human-readable descriptions for each failure name.
prerequisite_description() {
    local name="$1"
    case "$name" in
        bash)                 echo "The GNU Bourne-Again shell" ;;
        zfs)                  echo "The ZFS userspace command-line tool" ;;
        zpool)                echo "The ZFS pool administration tool" ;;
        pv)                   echo "Pipe Viewer, used for transfer progress bars" ;;
        rsync)                echo "File synchronization tool used by pull backups" ;;
        "python3")            echo "The Python 3 interpreter" ;;
        "python3 module: gi") echo "The PyGObject introspection bindings for GTK3" ;;
        "gir1.2-gtk-3.0")     echo "GTK3 GObject introspection data" ;;
        "gir1.2-webkit2-4.1") echo "WebKit2 GObject introspection data" ;;
        "libwebkit2gtk-4.1-0") echo "WebKit2 runtime library" ;;
        ssh)                  echo "OpenSSH client for remote two-node commands" ;;
        scp)                  echo "OpenSSH secure copy for remote two-node file transfer" ;;
        targetcli)            echo "LIO target configuration CLI" ;;
        rtslib-fb-targetctl)  echo "LIO target systemd service" ;;
        iscsiadm)             echo "iSCSI initiator administration tool" ;;
        pip3)
            echo "Python package installer used to install MkDocs when" \
                "distribution packages are unavailable"
            ;;
        *)                    echo "$name" ;;
    esac
}

prerequisite_why_needed() {
    local name="$1"
    case "$name" in
        bash|zfs|zpool|pv|rsync)
            echo "Core ZFSutilities scripts use this command directly"
            ;;
        "python3"|"python3 module: gi"|"gir1.2-gtk-3.0"|"gir1.2-webkit2-4.1"|"libwebkit2gtk-4.1-0")
            echo "Required by the GTK graphical user interface"
            ;;
        ssh|scp)
            echo "Required for two-node mode to communicate between storage and compute hosts"
            ;;
        targetcli|rtslib-fb-targetctl)
            echo "Required on the storage host to export ZFS zvols as iSCSI LUNs"
            ;;
        iscsiadm)
            echo "Required on the compute host to connect to the storage host's iSCSI targets"
            ;;
        pip3)
            echo "Required to build the ZFSutilities documentation site" \
                "(used as a fallback by the documentation-server installer)"
            ;;
        *)
            echo "Required by ZFSutilities"
            ;;
    esac
}

prerequisite_remediation() {
    local name="$1"
    local package="$2"
    case "$name" in
        rtslib-fb-targetctl)
            # The service is provided by python3-rtslib-fb, but installing
            # targetcli-fb pulls in the full LIO target stack including the service.
            echo "Run: apt-get install targetcli-fb"
            ;;
        *)
            if [[ -n "$package" ]]; then
                echo "Run: apt-get install $package"
            else
                echo "No automatic installation step is known; please install $name manually"
            fi
            ;;
    esac
}

# Explain every failure currently in installer_failures.
explain_all_failures() {
    local name package
    for name in "${!installer_failures[@]}"; do
        package="${installer_failures[$name]}"
        explain_prerequisite \
            "$name" \
            "$(prerequisite_description "$name")" \
            "$(prerequisite_why_needed "$name")" \
            "$(prerequisite_remediation "$name" "$package")"
    done
}

# Collect unique apt packages from installer_failures.
collect_apt_packages() {
    local name package packages=()
    for name in "${!installer_failures[@]}"; do
        package="${installer_failures[$name]}"
        [[ -n "$package" ]] || continue
        # Avoid duplicates
        local found=0
        local p
        for p in "${packages[@]}"; do
            [[ "$p" == "$package" ]] && { found=1; break; }
        done
        [[ $found -eq 0 ]] && packages+=("$package")
    done
    printf '%s\n' "${packages[@]}"
}

# Run check-prerequisites and handle the result interactively.
# Returns 0 if all required prerequisites are present (or were successfully
# installed), 1 otherwise.
run_interactive_prerequisites() {
    local mode="$1"
    local check_prereqs="$2"
    local failures
    local packages

    echo "=== Checking Prerequisites ==="
    echo ""

    # First run
    if "$check_prereqs" "$mode"; then
        # check-prerequisites already printed the success summary
        return 0
    fi

    # Gather machine-readable failures
    failures=$("$check_prereqs" "$mode" --list-failures 2>/dev/null || true)
    if [[ -z "$failures" ]]; then
        echo ""
        echo "✗ Prerequisites check failed, but no automatic remediation is available."
        return 1
    fi

    parse_check_prerequisites_failures "$failures"

    echo ""
    echo "The following required prerequisite(s) are missing:"
    explain_all_failures

    echo ""
    if ! ask_yn "Install missing required prerequisites now?" "Y"; then
        echo ""
        echo "Aborted. Please install the items above manually, then re-run the installer."
        return 1
    fi

    packages=$(collect_apt_packages | tr '\n' ' ')
    if [[ -z "$packages" ]]; then
        echo ""
        echo "✗ No installable packages were identified. Please install the items manually."
        return 1
    fi

    echo ""
    echo "The installer will run:"
    echo "  apt-get update"
    echo "  apt-get install -y $packages"

    if ! ask_yn "Proceed with installation?" "Y"; then
        echo ""
        echo "Aborted. Please install the items manually, then re-run the installer."
        return 1
    fi

    if ! apt_install "$packages"; then
        echo ""
        echo "✗ Automatic installation failed. Please install the items manually and re-run."
        return 1
    fi

    # Re-check
    echo ""
    echo "Re-checking prerequisites..."
    if "$check_prereqs" "$mode"; then
        # check-prerequisites already printed the success summary
        return 0
    else
        echo ""
        echo "✗ Some prerequisites are still missing after remediation."
        echo "   Please install them manually and re-run the installer."
        return 1
    fi
}

# Ensure the documentation server (MkDocs) is installed.
# Installs without prompting. Returns 0 on success, non-zero on failure.
ensure_doc_server() {
    echo "=== Documentation (MkDocs) ==="

    if command -v mkdocs >/dev/null 2>&1 && python3 -c "import material" >/dev/null 2>&1; then
        echo ""
        echo "  ✓ mkdocs and mkdocs-material are already installed."
        return 0
    fi

    explain_doc_server

    echo ""
    echo "  Installing mkdocs and mkdocs-material..."
    if install_doc_server; then
        echo ""
        echo "  ✓ Documentation server is ready."
        return 0
    else
        echo ""
        echo "  ✗ Documentation server could not be installed." >&2
        echo "    Install manually and re-run the installer:" >&2
        echo "      sudo apt-get install python3-pip" >&2
        echo "      sudo pip3 install --break-system-packages \"mkdocs<2\" mkdocs-material" >&2
        return 1
    fi
}

# ------------------------------------------------------------------
# Two-node iSCSI stack installation
# ------------------------------------------------------------------

# Ensure the LIO target stack is installed and the service is enabled on the
# local storage host. Returns 0 if ready, non-zero if the user declines or
# installation fails.
ensure_iscsi_target_stack() {
    echo "=== iSCSI Target Stack (storage host) ==="
    echo ""

    local need_install=false
    if ! command -v targetcli >/dev/null 2>&1; then
        echo "  ✗ targetcli not found"
        need_install=true
    else
        echo "  ✓ targetcli found"
    fi

    if ! systemctl cat rtslib-fb-targetctl >/dev/null 2>&1; then
        echo "  ✗ rtslib-fb-targetctl.service not found"
        need_install=true
    else
        echo "  ✓ rtslib-fb-targetctl.service found"
    fi

    if [[ "$need_install" != true ]]; then
        echo ""
        return 0
    fi

    echo ""
    echo "  The LIO target stack is required on the storage host to export"
    echo "  ZFS zvols as iSCSI LUNs. It can be installed from distribution packages."
    echo ""

    if ! ask_yn "Install the LIO target stack now (apt-get install targetcli-fb)?" "Y"; then
        echo "  Aborted. Install targetcli-fb manually and re-run the installer."
        return 1
    fi

    if ! apt_install targetcli-fb; then
        echo "  ✗ Could not install targetcli-fb." >&2
        echo "    Install manually and re-run the installer:" >&2
        echo "      sudo apt-get install targetcli-fb" >&2
        return 1
    fi

    echo ""
    echo "  Enabling rtslib-fb-targetctl.service..."
    if systemctl enable rtslib-fb-targetctl >/dev/null 2>&1; then
        echo "  ✓ rtslib-fb-targetctl.service enabled"
    else
        echo "  ⚠ Could not enable rtslib-fb-targetctl.service" >&2
    fi

    echo ""
    return 0
}

# Ensure open-iscsi is installed and the initiator service is enabled on the
# remote compute host. Returns 0 if ready, non-zero if the user declines or
# installation fails.
ensure_open_iscsi_remote() {
    local host="$1"

    echo "=== iSCSI Initiator (compute host: $host) ==="
    echo ""

    if ssh -o ConnectTimeout=5 -o BatchMode=yes "root@${host}" \
        "command -v iscsiadm >/dev/null 2>&1" >/dev/null 2>&1; then
        echo "  ✓ open-iscsi (iscsiadm) found on $host"
        echo ""
        return 0
    fi

    echo "  ✗ open-iscsi (iscsiadm) not found on $host"
    echo ""
    echo "  The iSCSI initiator is required on the compute host so Proxmox VE"
    echo "  can connect to the storage host's iSCSI targets."
    echo ""

    if ! ask_yn "Install open-iscsi on $host now?" "Y"; then
        echo "  Aborted. Install open-iscsi on $host manually and re-run the installer."
        return 1
    fi

    echo ""
    echo "  Installing open-iscsi on $host..."
    if ssh -o ConnectTimeout=30 "root@${host}" \
        "apt-get update -qq && apt-get install -y open-iscsi" >/dev/null 2>&1; then
        echo "  ✓ open-iscsi installed on $host"
    else
        echo "  ✗ Could not install open-iscsi on $host." >&2
        echo "    Install manually and re-run the installer:" >&2
        echo "      ssh root@${host} apt-get install open-iscsi" >&2
        return 1
    fi

    echo ""
    echo "  Enabling iscsid.service on $host..."
    if ssh -o ConnectTimeout=10 "root@${host}" \
        "systemctl enable iscsid >/dev/null 2>&1"; then
        echo "  ✓ iscsid.service enabled on $host"
    else
        echo "  ⚠ Could not enable iscsid.service on $host" >&2
    fi

    echo ""
    return 0
}

# ------------------------------------------------------------------
# Partial uninstall detection
# ------------------------------------------------------------------

# Check for remnants of a previous or partial uninstall and offer to clean
# them up before continuing with installation.
#
# Args:
#   $1  Absolute path to the repository root (used to locate the repo copy of
#       uninstall-zfsutilities when no deployed version exists).
#
# Returns 0 if the system is clean or cleanup succeeded.
# Returns 1 if remnants were found but the user declined cleanup.
check_partial_uninstall() {
    local repo_dir="$1"
    local version_base="${ZFSUTILITIES_VERSION_BASE:-/usr/local/lib/zfsutilities}"
    local systemd_dir="/etc/systemd/system"
    local partial=0

    # A version base directory without a current symlink usually means a
    # previous uninstall was interrupted.
    if [[ -d "$version_base" && ! -L "$version_base/current" ]]; then
        partial=1
    fi

    # systemd/cron integration left behind without a deployed version also
    # indicates a partial uninstall.
    if [[ ! -d "$version_base/versions" ]]; then
        if [[ -d "$systemd_dir/rtslib-fb-targetctl.service.d" || \
              -f "/etc/cron.d/zfsutilities" ]]; then
            partial=1
        fi
    fi

    if [[ $partial -eq 0 ]]; then
        return 0
    fi

    local _warning_bar
    _warning_bar=$(printf '%.0s━' {1..204})
    echo ""
    echo "$_warning_bar"
    echo "  ⚠  WARNING: Remnants of a previous ZFSutilities installation detected"
    echo ""
    echo "  This usually means a previous uninstall was interrupted or incomplete."
    echo "  Continuing without cleaning up may leave stale wiring, services, or"
    echo "  cron entries behind."
    echo ""
    echo "  It is strongly recommended to run uninstall-zfsutilities first."
    echo "$_warning_bar"
    echo ""

    if ! ask_yn "Run uninstall-zfsutilities now to clean up remnants?" "Y"; then
        echo ""
        echo "⚠  Continuing without cleanup. The installation may not work correctly."
        echo "   You can run uninstall-zfsutilities manually and then re-run this"
        echo "   installer."
        echo ""
        return 1
    fi

    local uninstaller=""
    if [[ -x "$version_base/current/bin/uninstall-zfsutilities" ]]; then
        uninstaller="$version_base/current/bin/uninstall-zfsutilities"
    elif [[ -x "$repo_dir/uninstall-zfsutilities" ]]; then
        uninstaller="$repo_dir/uninstall-zfsutilities"
    fi

    if [[ -z "$uninstaller" ]]; then
        echo "✗ ERROR: uninstall-zfsutilities not found." >&2
        echo "   Expected one of:" >&2
        echo "     $version_base/current/bin/uninstall-zfsutilities" >&2
        echo "     $repo_dir/uninstall-zfsutilities" >&2
        return 1
    fi

    echo "Running: $uninstaller --yes"
    if "$uninstaller" --yes; then
        echo "✓ Cleanup complete. Continuing with installation."
        return 0
    else
        echo "✗ ERROR: uninstall-zfsutilities failed." >&2
        return 1
    fi
}

# ------------------------------------------------------------------
# Desktop launcher symlinks
# ------------------------------------------------------------------

# shellcheck source=desktop-launcher-lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/desktop-launcher-lib.sh"

# ------------------------------------------------------------------
# Runtime directory creation
# ------------------------------------------------------------------

# Create the FHS-aligned directories used by ZFSutilities.
# Called by the installers after sourcing this library.
ensure_zfsutilities_dirs() {
    install -d -m 0755 \
        "${ZFSUTILITIES_SYSTEM_CONFIG_DIR}" \
        "${ZFSUTILITIES_STATE_DIR}" \
        "${ZFSUTILITIES_RUN_DIR}"
}

# ------------------------------------------------------------------
# Retention profile initialization
# ------------------------------------------------------------------

# Ensure the shared JSON config has a default retention profile.
# On a new install this also removes any pool-specific policies so only
# `default` remains. Existing user-entered profiles are preserved.
ensure_retention_profiles() {
    local config_path=\
"${ZFSCONFIG_PATH:-${ZFSUTILITIES_CONFIG_PATH:-/var/lib/zfsutilities/config.json}}"
    local new_install="false"
    if [[ ! -f "$config_path" ]]; then
        new_install="true"
    fi

    install -d -m 0755 "$(dirname "$config_path")"

    local lib_dir
    lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    local python_src
    if [[ -n "${ZFSUTILITIES_PYTHON_SRC:-}" ]]; then
        python_src="$ZFSUTILITIES_PYTHON_SRC"
    elif [[ -d "/usr/local/lib/zfsutilities/current/python" ]]; then
        python_src="/usr/local/lib/zfsutilities/current/python"
    else
        python_src="$(cd "$lib_dir/../python" && pwd)"
    fi
    local helper="$python_src/installer_retention.py"

    local new_install_flag=""
    if [[ "$new_install" == "true" ]]; then
        new_install_flag="--new-install"
    fi

    echo "=== Retention Profiles ==="
    if [[ "$new_install" == "true" ]]; then
        echo "  New install — creating default retention profile..."
    else
        echo "  Ensuring retention profiles are initialized (existing profiles preserved)..."
    fi

    PYTHONPATH="${python_src}:${lib_dir}" \
        python3 "$helper" --config-path "$config_path" ${new_install_flag}
}

