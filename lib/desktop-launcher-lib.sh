#!/bin/bash
# desktop-launcher-lib.sh
# Shared helpers for creating and removing user home-directory launcher
# symlinks for the ZFSutilities GUI and documentation viewer.
#
# Sourced by switch-version and the installers.

# Names of launcher symlinks created in the desktop user's home directory.
DESKTOP_LAUNCHER_NAMES=(
    "ZFSutilities GUI"
    "ZFSutilities Documentation"
)

# Names of launcher symlinks that are no longer used.  switch-version removes
# these when wiring or unwiring a version so stale shortcuts do not accumulate.
OBSOLETE_DESKTOP_LAUNCHER_NAMES=()

# Return the username that owns the current desktop session, or empty string.
# Prefers SUDO_USER, then falls back to the owner of the X11 display socket.
get_desktop_user() {
    local user

    user="${SUDO_USER:-}"
    if [[ -n "$user" ]]; then
        echo "$user"
        return 0
    fi

    # Fall back to owner of the X11 socket for the current display
    local display="${DISPLAY:-:0}"
    local display_num="${display%%.*}"
    display_num="${display_num#:}"
    local x11_sock="/tmp/.X11-unix/X${display_num}"

    if [[ -e "$x11_sock" ]]; then
        local uid
        uid=$(stat -c '%u' "$x11_sock" 2>/dev/null || true)
        if [[ -n "$uid" && "$uid" != "0" ]]; then
            user=$(id -un "$uid" 2>/dev/null || true)
            if [[ -n "$user" ]]; then
                echo "$user"
                return 0
            fi
        fi
    fi

    return 0
}

# Return the home directory for the given username, or empty string on failure.
get_user_home() {
    local user="$1"
    local home

    home=$(getent passwd "$user" 2>/dev/null | cut -d: -f6)
    echo "$home"
}

# Create desktop symlinks for the GUI and documentation viewer in the given
# user's home directory.  Existing files/symlinks with the same names are
# replaced.  Prints status messages and returns 0 on success.
create_desktop_symlinks() {
    local user="$1"
    local home

    if [[ -z "$user" ]]; then
        echo "  ⚠ Cannot determine desktop user; skipping home-directory symlinks."
        echo "    To create them manually, run:"
        echo "      ln -s /usr/local/lib/zfsutilities/current/bin/zfsutilities-gui \"\$HOME/ZFSutilities GUI\""
        echo "      ln -s /usr/local/lib/zfsutilities/current/bin/zfsutilities-docs \"\$HOME/ZFSutilities Documentation\""
        return 1
    fi

    home=$(get_user_home "$user")
    if [[ -z "$home" || ! -d "$home" ]]; then
        echo "  ⚠ Home directory for '$user' not found; skipping home-directory symlinks."
        return 1
    fi

    local gui_link="${home}/ZFSutilities GUI"
    local docs_link="${home}/ZFSutilities Documentation"
    local gui_target="/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui"
    local docs_target="/usr/local/lib/zfsutilities/current/bin/zfsutilities-docs"

    rm -f "$gui_link"
    ln -s "$gui_target" "$gui_link"
    chown -h "$user:" "$gui_link" 2>/dev/null || true
    echo "  ✓ $gui_link -> $gui_target"

    rm -f "$docs_link"
    ln -s "$docs_target" "$docs_link"
    chown -h "$user:" "$docs_link" 2>/dev/null || true
    echo "  ✓ $docs_link -> $docs_target"

    return 0
}

# Remove desktop symlinks for the GUI and documentation viewer from the given
# user's home directory.  Missing links are silently ignored.  Prints status
# messages for removed links and returns 0 on success.
remove_desktop_symlinks() {
    local user="$1"
    local home

    if [[ -z "$user" ]]; then
        echo "  ⚠ Cannot determine desktop user; skipping home-directory symlink removal."
        return 1
    fi

    home=$(get_user_home "$user")
    if [[ -z "$home" || ! -d "$home" ]]; then
        echo "  ⚠ Home directory for '$user' not found; skipping home-directory symlink removal."
        return 1
    fi

    local name link
    for name in "${DESKTOP_LAUNCHER_NAMES[@]}" "${OBSOLETE_DESKTOP_LAUNCHER_NAMES[@]}"; do
        link="${home}/${name}"
        if [[ -L "$link" ]]; then
            rm -f "$link"
            echo "  ✓ Removed $link"
        fi
    done

    return 0
}
