"""Two-node / single-node configuration parser.

Mirrors the behavior of ``lib/node-lib.sh`` for the Python layer.  Reads
``/etc/zfsutilities/node.conf`` (with legacy fallbacks) and exposes the node
mode, host identities, storage network details, and the pool-to-target map.
"""

import os
import re
import socket
import subprocess

from paths import get_system_config_dir

# Legacy fallback paths, matching lib/node-lib.sh.
_LEGACY_NODE_CONF = "/etc/zfsutilities-node.conf"
_LEGACY_TWO_NODE_CONF = "/etc/two-node.conf"


def _local_hostname() -> str:
    """Return the short hostname of this machine."""
    try:
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


def _find_config_file(path: str | None = None) -> str | None:
    """Return the node configuration file to use, or None if none exists."""
    if path is not None:
        return path if os.path.isfile(path) else None

    env_path = os.environ.get("ZFSUTILITIES_NODE_CONF")
    if env_path and os.path.isfile(env_path):
        return env_path

    candidates = [
        os.path.join(get_system_config_dir(), "node.conf"),
        _LEGACY_NODE_CONF,
        _LEGACY_TWO_NODE_CONF,
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _bash_parse_config(path: str) -> dict:
    """Parse the bash-style node config file using bash itself.

    This avoids reimplementing associative-array parsing in Python and keeps
    the Python layer in sync with whatever bash reads from the file.
    """
    script = f"""
source {path!r} >/dev/null 2>&1 || exit 0
: "${{NODE_MODE:=two-node}}"
echo "NODE_MODE=${{NODE_MODE}}"
echo "STORAGE_HOST=${{STORAGE_HOST:-}}"
echo "COMPUTE_HOST=${{COMPUTE_HOST:-}}"
echo "STORAGE_IP=${{STORAGE_IP:-}}"
echo "POOL_TARGET_BEGIN"
if declare -p POOL_TARGET >/dev/null 2>&1; then
    for k in "${{!POOL_TARGET[@]}}"; do
        printf 'POOL_TARGET[%s]=%s\\n' "$k" "${{POOL_TARGET[$k]}}"
    done
fi
"""
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    data = {
        "mode": "two-node",
        "storage_host": "",
        "compute_host": "",
        "storage_ip": "",
        "pools": set(),
    }
    if result.returncode != 0:
        return data

    in_pools = False
    pool_re = re.compile(r"^POOL_TARGET\[(.+?)\]=(.+)$")
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "POOL_TARGET_BEGIN":
            in_pools = True
            continue
        if in_pools:
            match = pool_re.match(line)
            if match:
                data["pools"].add(match.group(1))
            continue
        if line.startswith("NODE_MODE="):
            data["mode"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("STORAGE_HOST="):
            data["storage_host"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("COMPUTE_HOST="):
            data["compute_host"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("STORAGE_IP="):
            data["storage_ip"] = line.split("=", 1)[1].strip().strip('"').strip("'")

    return data


def load_node_config(path: str | None = None) -> dict:
    """Load node configuration and return a normalized dict.

    Returns:
        A dict with keys:
            - ``mode``: "single-node" or "two-node"
            - ``this_host``: short hostname of the local machine
            - ``storage_host``: short hostname of the storage node
            - ``compute_host``: short hostname of the compute node
            - ``storage_ip``: storage-network portal IP (may be empty)
            - ``pools``: set of pool names configured in POOL_TARGET
    """
    this_host = _local_hostname()
    defaults = {
        "mode": "single-node",
        "this_host": this_host,
        "storage_host": this_host,
        "compute_host": this_host,
        "storage_ip": "",
        "pools": set(),
    }

    config_path = _find_config_file(path)
    if config_path is None:
        return defaults

    parsed = _bash_parse_config(config_path)
    mode = parsed.get("mode") or "two-node"
    if mode not in ("single-node", "two-node"):
        mode = "two-node"

    if mode == "single-node":
        return {
            "mode": "single-node",
            "this_host": this_host,
            "storage_host": this_host,
            "compute_host": this_host,
            "storage_ip": "",
            "pools": set(),
        }

    storage_host = parsed.get("storage_host") or this_host
    compute_host = parsed.get("compute_host") or this_host
    return {
        "mode": "two-node",
        "this_host": this_host,
        "storage_host": storage_host,
        "compute_host": compute_host,
        "storage_ip": parsed.get("storage_ip", ""),
        "pools": parsed.get("pools", set()) or set(),
    }


def is_two_node(config: dict | None = None) -> bool:
    """Return True if the configuration is two-node."""
    if config is None:
        config = load_node_config()
    return config.get("mode") == "two-node"


def is_storage_host(config: dict | None = None) -> bool:
    """Return True if this machine is the configured storage host."""
    if config is None:
        config = load_node_config()
    return config.get("this_host") == config.get("storage_host")


def is_compute_host(config: dict | None = None) -> bool:
    """Return True if this machine is the configured compute host."""
    if config is None:
        config = load_node_config()
    return config.get("this_host") == config.get("compute_host")


def get_peer_host(config: dict | None = None) -> str | None:
    """Return the hostname of the other node, or None in single-node mode."""
    if config is None:
        config = load_node_config()
    if not is_two_node(config):
        return None
    this_host = config.get("this_host")
    storage = config.get("storage_host")
    compute = config.get("compute_host")
    if this_host == storage and compute and compute != this_host:
        return compute
    if this_host == compute and storage and storage != this_host:
        return storage
    if storage and storage != this_host:
        return storage
    if compute and compute != this_host:
        return compute
    return None


def get_lock_authority_host(dataset: str, config: dict | None = None) -> str | None:
    """Return the host that should hold a lock for *dataset*, or None for local.

    In single-node mode, or when the dataset's pool is not known to the
    two-node configuration, the lock is local and this returns None.

    In two-node mode, if the dataset's pool is in ``config["pools"]`` and this
    host is not the storage host, the storage host is returned.
    """
    if config is None:
        config = load_node_config()
    if not is_two_node(config):
        return None
    pool = dataset.split("/", 1)[0] if "/" in dataset else dataset
    if pool not in (config.get("pools") or set()):
        return None
    storage = config.get("storage_host")
    if not storage or is_storage_host(config):
        return None
    return storage
