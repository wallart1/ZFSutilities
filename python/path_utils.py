"""Shared path-resolution helpers for the ZFS Utilities Python layer.

Mirrors the Bash ``$mydir`` / ``find_zfsutility_script`` / ``remote_zfsutilities_bin``
functionality so the GTK GUI can locate sibling scripts, read the deployed
version, and resolve remote SSH paths without hard-coding installation
locations.
"""

import os
import subprocess
import tempfile

# Base directory for versioned deployments.  Overridable for tests and for
# non-standard installations.
_DEPLOYMENT_BASE = os.environ.get("ZFSUTILITIES_VERSION_BASE", "/usr/local/lib/zfsutilities")

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


# Relative path from a repo/deployment root to the built docs index.
_DOCS_INDEX = os.path.join("docs", "site", "index.html")

# Relative path from a repo/deployment root to the Python source directory.
_PYTHON_DIR = "python"


def _repo_candidate_dirs(script_dir=None):
    """Return the ordered list of repo-layout directories to search."""
    if script_dir is None:
        script_dir = get_script_dir(depth=2)
    return [
        script_dir,
        os.path.join(script_dir, ".."),
        os.path.join(script_dir, "..", "lib"),
        os.path.join(script_dir, "..", "bin"),
        os.path.join(script_dir, "..", "share"),
        os.path.join(script_dir, "..", "python"),
    ]


def _candidate_dirs(script_dir=None):
    """Return the ordered list of directories to search for sibling scripts."""
    return _repo_candidate_dirs(script_dir)


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
    return f"{_DEPLOYMENT_BASE}{os.sep}versions{os.sep}" in os.path.realpath(script_dir)


def _version_base(script_dir=None):
    """Return the version-root directory for the current layout.

    In the repo this is the parent of ``python/``.  In a deployed
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

    Resolution is layout-faithful: a repo checkout resolves within the repo
    and a deployed layout resolves to the active deployment.  There is no
    cross-layout fallback, so a GUI launched from the repo can never
    silently view (or edit) a deployment's documents.  Returns ``None`` if
    the layout's site is not built.
    """
    path = os.path.join(_version_base(script_dir), _DOCS_INDEX)
    if os.path.isfile(path):
        return path
    return None


def get_profile_runner_path(script_dir=None):
    """Return the path to ``profile_runner.py`` for the current layout.

    In a deployed layout this uses the ``current`` symlink so cron jobs and
    ad-hoc runs track version switches automatically.  In the repo it returns
    the sibling copy.
    """
    return os.path.join(_version_base(script_dir), _PYTHON_DIR, "profile_runner.py")


# Seconds an idle multiplexed SSH master connection is kept alive (see
# ``ssh_command``).  Comfortably exceeds the Dashboard refresh-interval
# ceiling (300 s) so steady-state polling reuses one connection; the master
# self-expires after the window, so a closed or crashed GUI leaves no
# permanent sockets behind.
SSH_CONTROL_PERSIST = 600


def _mux_socket_dir():
    """Return a private directory for SSH multiplex control sockets.

    Tries an XDG runtime directory first, then ``/run/zfsutilities``, then a
    uid-tagged temp directory.  Returns ``None`` when no candidate can be
    created and written, in which case callers fall back to a plain ssh
    argv without multiplexing.
    """
    candidates = []
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        candidates.append(os.path.join(xdg, "zfsutilities-ssh-mux"))
    candidates.append("/run/zfsutilities/ssh-mux")
    candidates.append(os.path.join(tempfile.gettempdir(), f"zfsutilities-ssh-mux-{os.getuid()}"))
    for directory in candidates:
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            os.chmod(directory, 0o700)
        except OSError:
            continue
        if os.access(directory, os.W_OK):
            return directory
    return None


def ssh_command(host, remote_cmd):
    """Build the ssh argv used to run ``remote_cmd`` as root on ``host``.

    Adds OpenSSH connection multiplexing (ControlMaster/ControlPersist) so
    recurring callers — the Dashboard's periodic probes — reuse one
    background connection instead of logging in for every call: each fresh
    root login costs the remote host roughly two dozen journal lines plus a
    systemd user-session cycle.  Mirrors the multiplexed ssh already used
    by ``bin/deploy-version`` and ``bin/upgrade-zfsutilities``.  Falls back
    to a plain ssh argv when no private control-socket directory is
    available.
    """
    argv = ["ssh", "-o", "ConnectTimeout=10"]
    socket_dir = _mux_socket_dir()
    if socket_dir:
        argv += [
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPath=" + os.path.join(socket_dir, "%r@%h-%p"),
            "-o",
            f"ControlPersist={SSH_CONTROL_PERSIST}",
        ]
    return argv + [f"root@{host}", remote_cmd]


def remote_version_path():
    """Return the remote VERSION file path used by version probes."""
    return _REMOTE_VERSION_PATH


def resolve_remote_bin(host, timeout=15):
    """Resolve the remote active-version ``bin/`` directory over SSH.

    Returns the resolved path, or ``None`` if resolution fails.
    """
    cmd = ssh_command(
        host,
        f"realpath {_REMOTE_BIN} 2>/dev/null || readlink -f {_REMOTE_BIN} 2>/dev/null",
    )
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


def resolve_remote_version(host, timeout=15):
    """Read the deployed ``VERSION`` file from *host* via SSH.

    Returns the version string, or ``"unknown"`` if it cannot be determined.
    """
    cmd = ssh_command(host, f"cat {_REMOTE_VERSION_PATH} 2>/dev/null")
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
