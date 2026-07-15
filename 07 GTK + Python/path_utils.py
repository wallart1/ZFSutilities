"""Shared path-resolution helpers for the ZFS Utilities Python layer.

Mirrors the Bash ``$mydir`` / ``find_zfsutility_script`` / ``remote_zfsutilities_bin``
functionality so the GTK GUI can locate sibling scripts, read the deployed
version, and resolve remote SSH paths without hard-coding installation
locations.
"""

import os
import subprocess


# Base directory for versioned deployments.  Overridable for tests and for
# non-standard installations.
_DEPLOYMENT_BASE = os.environ.get(
    "ZFSUTILITIES_VERSION_BASE", "/usr/local/lib/zfsutilities"
)

# Remote deployment paths.  Overridable for tests and non-standard installs.
_REMOTE_BIN = os.environ.get(
    "ZFSUTILITIES_REMOTE_BIN", os.path.join(_DEPLOYMENT_BASE, "current/bin")
)
_REMOTE_VERSION_PATH = os.environ.get(
    "ZFSUTILITIES_REMOTE_VERSION",
    os.path.join(_DEPLOYMENT_BASE, "current/VERSION"),
)


def get_script_dir(depth=1):
    """Return the directory of the caller's source file.

    ``depth=1`` returns the immediate caller's directory; larger values walk
    further up the call stack.  This mirrors ``bashinit``'s ``$mydir``.
    """
    frame = __import__("inspect").stack()[depth]
    return os.path.dirname(os.path.realpath(frame.filename))


def _candidate_dirs(script_dir=None):
    """Return the ordered list of directories to search for sibling scripts."""
    if script_dir is None:
        script_dir = get_script_dir(depth=2)
    return [
        script_dir,
        os.path.join(script_dir, ".."),
        os.path.join(script_dir, "08 Two-node"),
        os.path.join(script_dir, "..", "08 Two-node"),
        os.path.join(script_dir, "09 ZFS clone support"),
        os.path.join(script_dir, "..", "09 ZFS clone support"),
    ]


def find_script(name, script_dir=None):
    """Search for *name* in the standard repo/deployment candidate directories.

    Returns the absolute path of the first existing regular file, or ``None``
    if no candidate matches.
    """
    for candidate in _candidate_dirs(script_dir):
        path = os.path.realpath(os.path.join(candidate, name))
        if os.path.isfile(path):
            return path
    return None


def resolve_local_bin(name, script_dir=None):
    """Return the absolute path to a sibling executable, or ``None``."""
    return find_script(name, script_dir=script_dir)


def is_deployed_layout(script_dir=None):
    """Return ``True`` if *script_dir* lives inside a versioned deployment."""
    if script_dir is None:
        script_dir = get_script_dir(depth=2)
    return f"{_DEPLOYMENT_BASE}{os.sep}versions{os.sep}" in os.path.realpath(
        script_dir
    )


def _version_base(script_dir=None):
    """Return the version-root directory for the current layout.

    In the repo this is the parent of ``07 GTK + Python/``.  In a deployed
    layout it is ``_DEPLOYMENT_BASE/current``.
    """
    if script_dir is None:
        script_dir = get_script_dir(depth=3)
    if is_deployed_layout(script_dir):
        return os.path.join(_DEPLOYMENT_BASE, "current")
    return os.path.dirname(script_dir)


def get_version(script_dir=None):
    """Read the ``VERSION`` file for the current layout.

    Tries the repo root (or deployed ``current`` directory) first, then falls
    back to the explicit deployment path.  Returns ``"dev"`` if no version
    file can be found.
    """
    candidates = [_version_base(script_dir)]
    candidates.append(os.path.join(_DEPLOYMENT_BASE, "current"))

    for base in candidates:
        path = os.path.join(base, "VERSION")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read().strip()
            except OSError:
                continue
    return "dev"


def get_docs_path(script_dir=None):
    """Return the path to the built documentation ``index.html``.

    Checks the repo layout first, then the deployed layout.  Returns ``None``
    if no built docs are found.
    """
    candidates = [
        os.path.join(_version_base(script_dir), "06 Docs", "site", "index.html"),
        os.path.join(_DEPLOYMENT_BASE, "current", "06 Docs", "site", "index.html"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def get_profile_runner_path(script_dir=None):
    """Return the path to ``profile_runner.py`` for the current layout.

    In a deployed layout this uses the ``current`` symlink so cron jobs and
    ad-hoc runs track version switches automatically.  In the repo it returns
    the sibling copy.
    """
    if is_deployed_layout(script_dir):
        return os.path.join(
            _DEPLOYMENT_BASE, "current", "07 GTK + Python", "profile_runner.py"
        )
    if script_dir is None:
        script_dir = get_script_dir(depth=2)
    return os.path.join(script_dir, "profile_runner.py")


def resolve_remote_bin(host, timeout=15):
    """Resolve the remote active-version ``bin/`` directory over SSH.

    Returns the resolved path, or ``None`` if resolution fails.
    """
    cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=10",
        f"root@{host}",
        f"realpath {_REMOTE_BIN} 2>/dev/null || readlink -f {_REMOTE_BIN} 2>/dev/null",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if path:
                return path
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def resolve_remote_script(host, name):
    """Return ``"<remote_bin>/<name>"`` or just ``"<name>"`` on failure."""
    remote_bin = resolve_remote_bin(host)
    if remote_bin:
        return os.path.join(remote_bin, name)
    return name


def resolve_remote_version(host, timeout=15):
    """Read the deployed ``VERSION`` file from *host* via SSH.

    Returns the version string, or ``"unknown"`` if it cannot be determined.
    """
    cmd = [
        "ssh",
        "-o",
        "ConnectTimeout=10",
        f"root@{host}",
        f"cat {_REMOTE_VERSION_PATH} 2>/dev/null",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            if version:
                return version
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"
