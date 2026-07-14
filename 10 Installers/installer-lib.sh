#!/bin/bash
# installer-lib.sh
# Shared helper functions for ZFSutilities installers.
#
# This file is sourced by install-single-node and install-two-node.
# It provides interactive prompts, explanations, safe remediation
# helpers, and prerequisite-failure parsing for the prerequisite phase.

# Associative array: INSTALLER_FAILURES[name]=apt_package
# Populated by parse_check_prerequisites_failures.
declare -A INSTALLER_FAILURES

# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

# Ask a yes/no question. Returns 0 for yes, 1 for no.
# Default is "no" unless the second argument is "Y".
ask_yn() {
    local prompt="$1"
    local default="${2:-N}"
    local answer

    while true; do
        if [[ "$default" == "Y" ]]; then
            read -rp "${prompt} [Y/n]: " answer
            answer="${answer:-Y}"
        else
            read -rp "${prompt} [y/N]: " answer
            answer="${answer:-N}"
        fi

        case "$answer" in
            [Yy]|[Yy][Ee][Ss])
                return 0
                ;;
            [Nn]|[Nn][Oo])
                return 1
                ;;
            *)
                echo "  Please answer y or n."
                ;;
        esac
    done
}

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
    local stamp="/var/cache/apt/archives/lock"

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
    if pip3 install --break-system-packages mkdocs mkdocs-material; then
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
# Populates the associative array INSTALLER_FAILURES[name]=package.
parse_check_prerequisites_failures() {
    local output="$1"
    local line category name package message

    # Clear any existing entries
    INSTALLER_FAILURES=()

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        # Format: category|name|package|message
        category="${line%%|*}"; line="${line#*|}"
        name="${line%%|*}"; line="${line#*|}"
        package="${line%%|*}"; line="${line#*|}"
        message="$line"
        INSTALLER_FAILURES["$name"]="$package"
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
        pip3)                 echo "Python package installer used to install MkDocs when distribution packages are unavailable" ;;
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
        pip3)
            echo "Required to build the ZFSutilities documentation site (used as a fallback by the documentation-server installer)"
            ;;
        *)
            echo "Required by ZFSutilities"
            ;;
    esac
}

prerequisite_remediation() {
    local name="$1"
    local package="$2"
    if [[ -n "$package" ]]; then
        echo "Run: apt-get install $package"
    else
        echo "No automatic installation step is known; please install $name manually"
    fi
}

# Explain every failure currently in INSTALLER_FAILURES.
explain_all_failures() {
    local name package
    for name in "${!INSTALLER_FAILURES[@]}"; do
        package="${INSTALLER_FAILURES[$name]}"
        explain_prerequisite \
            "$name" \
            "$(prerequisite_description "$name")" \
            "$(prerequisite_why_needed "$name")" \
            "$(prerequisite_remediation "$name" "$package")"
    done
}

# Collect unique apt packages from INSTALLER_FAILURES.
collect_apt_packages() {
    local name package packages=()
    for name in "${!INSTALLER_FAILURES[@]}"; do
        package="${INSTALLER_FAILURES[$name]}"
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

    if ! apt_install $packages; then
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
        echo "      sudo pip3 install --break-system-packages mkdocs mkdocs-material" >&2
        return 1
    fi
}

# ------------------------------------------------------------------
# Desktop launcher symlinks
# ------------------------------------------------------------------

# shellcheck source=desktop-launcher-lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/desktop-launcher-lib.sh"

# ------------------------------------------------------------------
# Retention profile initialization
# ------------------------------------------------------------------

# Ensure the shared JSON config has a default retention profile.
# On a new install this also removes any pool-specific policies so only
# `default` remains. Existing user-entered profiles are preserved.
ensure_retention_profiles() {
    local config_path="${ZFSCONFIG_PATH:-/root/.config/zfsutilities.json}"
    local new_install="false"
    if [[ ! -f "$config_path" ]]; then
        new_install="true"
    fi

    local lib_dir
    lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local helper="$lib_dir/installer_retention.py"

    local python_src
    if [[ -d "/usr/local/lib/zfsutilities/current/07 GTK + Python" ]]; then
        python_src="/usr/local/lib/zfsutilities/current/07 GTK + Python"
    else
        python_src="$(cd "$lib_dir/../07 GTK + Python" && pwd)"
    fi

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

# Run ensure_retention_profiles on a remote host via SSH.
# Warnings only on failure so the install can continue.
ensure_retention_profiles_remote() {
    local host="$1"
    local config_path="${ZFSCONFIG_PATH:-/root/.config/zfsutilities.json}"
    local helper="/usr/local/lib/zfsutilities/current/10 Installers/installer_retention.py"
    local python_src="/usr/local/lib/zfsutilities/current/07 GTK + Python"
    local installer_src="/usr/local/lib/zfsutilities/current/10 Installers"

    local new_install_flag=""
    if ssh -o ConnectTimeout=5 "root@$host" "[[ ! -f '$config_path' ]]" >/dev/null 2>&1; then
        new_install_flag="--new-install"
    fi

    echo "=== Retention Profiles on $host ==="
    ssh -o ConnectTimeout=5 "root@$host" \
        "PYTHONPATH='$python_src:$installer_src' python3 '$helper' --config-path '$config_path' $new_install_flag" \
        || echo "  ⚠ Could not initialize retention profiles on $host" >&2
}
