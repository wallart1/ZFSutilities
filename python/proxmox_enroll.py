"""Proxmox storage enrollment offer for newly created or migrated pools.

A pool is only usable from the Proxmox GUI once it is registered as a
Proxmox storage (Datacenter → Storage): a ``zfspool`` entry on the local
host in single-node mode, an ``iscsi`` entry on the compute host in
two-node mode.  This module asks the user, after a pool is created on the
Disks page (or migrated, or on demand from the Disks page button), whether
to run the ``enroll-proxmox-pool`` script to do that automatically, and
provides the pure helpers that decide whether the offer applies at all.

All decision logic is kept in pure helpers (testable without GTK); the
enrollment itself runs as a non-fatal ``BashStep`` on the dataset runner so
an enrollment failure does not look like a pool-creation failure.
"""

import re
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")

import node_config
from backup_config import log_msg
from command_builders import BashStep
from disks_page import refresh_disks_page, update_disks_button_sensitivity
from gi.repository import Gtk
from iscsi_enroll import derive_target_short, is_iscsi_managed_pool
from path_utils import resolve_local_bin
from pools_page import on_pools_refresh

# Proxmox storage IDs: start with a letter or digit, then letters, digits,
# dot, underscore, or hyphen (mirrors the bash storage_id_is_valid check).
_STORAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# ssh probe/read options for compute-host pvesm queries (status-check
# convention: fail fast when keys or the host are unavailable).
_SSH_OPTS = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]

_PROBE_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Pure helpers (no GTK, no subprocess) — unit-tested directly
# ---------------------------------------------------------------------------


def derive_storage_id(pool_name: str, two_node: bool) -> str:
    """Derive the default Proxmox storage ID for *pool_name*.

    Single-node uses the pool name; two-node prefixes the iSCSI target short
    name with ``iscsi-`` (the documented storage.cfg convention).
    """
    if two_node:
        return f"iscsi-{derive_target_short(pool_name)}"
    return pool_name


def storage_id_is_valid(text: str) -> bool:
    """Return True when *text* is a non-empty valid Proxmox storage ID."""
    return bool(_STORAGE_ID_RE.match(text))


def parse_storage_ids(status_text: str) -> set[str]:
    """Extract storage IDs (first column) from ``pvesm status`` output.

    The ``Name`` header line is skipped.
    """
    ids = set()
    for line in (status_text or "").splitlines():
        fields = line.split()
        if not fields or fields[0] == "Name":
            continue
        ids.add(fields[0])
    return ids


def pvesm_status_argv(config: dict) -> list[str]:
    """Build the argv that lists Proxmox storages for *config*.

    Single-node runs ``pvesm status`` locally; two-node queries the compute
    host over ssh (the storage host has no Proxmox storages of its own).
    """
    if node_config.is_two_node(config):
        host = config.get("compute_host") or ""
        return ["ssh", *_SSH_OPTS, f"root@{host}", "pvesm", "status"]
    return ["pvesm", "status"]


def pvesm_presence_argv(config: dict) -> list[str] | None:
    """Build the argv that probes for pvesm, or None for a local check.

    Single-node presence is checked with ``shutil.which`` (no subprocess);
    two-node probes the compute host over ssh.
    """
    if node_config.is_two_node(config):
        host = config.get("compute_host") or ""
        return ["ssh", *_SSH_OPTS, f"root@{host}", "command", "-v", "pvesm"]
    return None


def build_enroll_command(
    pool_name: str, storage_id: str | None = None, dry_run: bool = False
) -> list[str]:
    """Build the ``enroll-proxmox-pool`` argv for *pool_name*.

    The optional *storage_id* overrides the derived Proxmox storage ID;
    empty/None parts are omitted.  ``--dry-run`` is placed before the pool
    name when *dry_run* is set.
    """
    script = resolve_local_bin("enroll-proxmox-pool") or "enroll-proxmox-pool"
    argv = [script]
    if dry_run:
        argv.append("--dry-run")
    argv.append(pool_name)
    if storage_id:
        argv.append(storage_id)
    return argv


def _subprocess_run(argv: list[str]) -> tuple[int, str]:
    """Run *argv* and return ``(rc, stdout)``; non-zero/absent → (1, "")."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=_PROBE_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return result.returncode, result.stdout or ""


def query_storage_ids(config: dict, run=_subprocess_run) -> set[str] | None:
    """Return the Proxmox storage IDs for *config*, or None when unreadable."""
    rc, stdout = run(pvesm_status_argv(config))
    if rc:
        return None
    return parse_storage_ids(stdout)


def proxmox_present(config: dict, run=_subprocess_run) -> bool:
    """Return True when the host that runs pvesm for *config* has it.

    Single-node: the local host.  Two-node: the compute host, reached over
    ssh (must also be the storage host, since that is where the script runs).
    """
    if node_config.is_two_node(config):
        if not node_config.is_storage_host(config):
            return False
        probe = pvesm_presence_argv(config)
        rc, _ = run(probe)
        return rc == 0
    return shutil.which("pvesm") is not None


def log_manual_enrollment_steps(pool_name: str, include_iscsi: bool = False) -> None:
    """Log the manual steps that register *pool_name* with Proxmox."""
    script = f"sudo enroll-proxmox-pool {pool_name}"
    if include_iscsi:
        log_msg(f"INFO:   1. run 'sudo enroll-iscsi-pool {pool_name}' on the storage host")
        log_msg(f"INFO:   2. run '{script}' on the storage host")
    elif node_config.is_two_node():
        log_msg(f"INFO:   run '{script}' on the storage host (registers an iSCSI storage")
        log_msg("INFO:   on the compute host in Datacenter → Storage)")
    else:
        log_msg(f"INFO:   run '{script}' (creates {pool_name}/proxmox and registers a")
        log_msg("INFO:   ZFS storage in Datacenter → Storage)")


# ---------------------------------------------------------------------------
# Enrollment offer (GTK)
# ---------------------------------------------------------------------------


def _show_enroll_dialog(app, pool_name: str, default_id: str, config: dict) -> str | None:
    """Ask whether to register *pool_name* as Proxmox storage.

    Returns the storage-ID entry text when the user answers YES, or None
    when the offer is declined.  The entry is pre-filled with *default_id*.
    """
    if node_config.is_two_node(config):
        secondary = (
            f"Adds an iSCSI storage in Proxmox (Datacenter → Storage) named "
            f"'{default_id}' on the compute host "
            f"{config.get('compute_host')}, using portal "
            f"{config.get('storage_ip')} and the pool's iSCSI target, so VM "
            "disks on this pool can be attached from the Proxmox GUI."
        )
    else:
        secondary = (
            f"Adds a ZFS storage in Proxmox (Datacenter → Storage) named "
            f"'{default_id}', backed by {pool_name}/proxmox, so VM disks can "
            "be created on this pool from the Proxmox GUI."
        )
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Register pool '{pool_name}' with Proxmox?",
    )
    dialog.format_secondary_text(secondary)
    label = Gtk.Label(label="Proxmox storage ID:")
    label.set_halign(Gtk.Align.START)
    entry = Gtk.Entry()
    entry.set_text(default_id)
    entry.set_activates_default(True)
    dialog.set_default_response(Gtk.ResponseType.YES)
    content = dialog.get_content_area()
    content.add(label)
    content.add(entry)
    dialog.show_all()
    try:
        response = dialog.run()
        if response != Gtk.ResponseType.YES:
            return None
        text = entry.get_text()
        return text if isinstance(text, str) else ""
    finally:
        dialog.destroy()


def offer_proxmox_enrollment(app, pool_name: str, on_done=None) -> bool:
    """Offer to register *pool_name* as Proxmox storage after a pool action.

    Returns True when the enrollment step was handed to the dataset runner,
    False when the offer does not apply (no Proxmox, wrong host, pool not
    enrolled in two-node iSCSI, storage already registered, runner busy, or
    the user declined).  *on_done* is called without arguments after the
    enrollment step finishes.
    """
    config = node_config.load_node_config()
    if node_config.is_two_node(config) and not node_config.is_storage_host(config):
        return False
    if node_config.is_two_node(config) and not is_iscsi_managed_pool(pool_name, config):
        log_msg(
            f"INFO: Proxmox storage enrollment for pool '{pool_name}' skipped: the "
            "pool is not enrolled in two-node iSCSI. Manual steps:"
        )
        log_manual_enrollment_steps(pool_name, include_iscsi=True)
        return False
    if not proxmox_present(config):
        if node_config.is_two_node(config):
            log_msg(
                f"WARN: Proxmox (pvesm) not reachable on compute host "
                f"{config.get('compute_host')} — pool '{pool_name}' was not "
                "registered. Manual steps:"
            )
            log_manual_enrollment_steps(pool_name)
        return False

    default_id = derive_storage_id(pool_name, node_config.is_two_node(config))
    registered = query_storage_ids(config)
    if registered is None:
        log_msg(
            f"WARN: Could not read pvesm status — cannot tell whether pool "
            f"'{pool_name}' is already registered with Proxmox. Manual steps:"
        )
        log_manual_enrollment_steps(pool_name)
        return False
    if default_id in registered:
        log_msg(
            f"INFO: Pool '{pool_name}' is already registered with Proxmox as storage '{default_id}'"
        )
        return False

    runner = getattr(app, "dataset_runner", None)
    if runner is None or runner.running:
        log_msg(
            f"INFO: Proxmox storage enrollment for pool '{pool_name}' skipped because "
            "a dataset action is not available or already running. Manual steps:"
        )
        log_manual_enrollment_steps(pool_name)
        return False

    storage_id = _show_enroll_dialog(app, pool_name, default_id, config)
    if storage_id is None:
        log_msg(f"INFO: Proxmox storage enrollment for pool '{pool_name}' declined. Manual steps:")
        log_manual_enrollment_steps(pool_name)
        return False
    if not storage_id_is_valid(storage_id):
        log_msg(
            f"WARN: Invalid Proxmox storage ID '{storage_id}' for pool "
            f"'{pool_name}' — falling back to '{default_id}'"
        )
        storage_id = default_id

    step = BashStep(
        build_enroll_command(pool_name, storage_id),
        f"Enroll pool {pool_name} in Proxmox",
        is_rsync=False,
        fatal=False,
    )

    def _on_enroll_complete(cancelled=False, rc=None):
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: Proxmox storage enrollment for pool '{pool_name}' cancelled")
        elif rc:
            log_msg(f"WARN: Proxmox storage enrollment for pool '{pool_name}' failed (rc={rc})")
        else:
            log_msg(f"INFO: Pool '{pool_name}' registered with Proxmox as storage '{storage_id}'")
        if on_done is not None:
            on_done()

    runner.operation_detail = f"Enroll in Proxmox: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_enroll_complete)
    return True


def on_disks_enroll_proxmox(app) -> None:
    """Disks page action: enroll the selected pool with Proxmox."""
    selector = getattr(app, "_disks_pool_selector", None)
    pool_name = selector.get_active_text() if selector is not None else ""
    if not pool_name:
        log_msg("WARN: No pool selected for Proxmox enrollment")
        return
    if node_config.is_two_node() and not node_config.is_storage_host():
        log_msg("WARN: Proxmox enrollment is available only on the storage host")
        return
    runner = getattr(app, "dataset_runner", None)
    if runner is not None and runner.running:
        log_msg("WARN: A dataset action is already running")
        return
    offer_proxmox_enrollment(app, pool_name)
