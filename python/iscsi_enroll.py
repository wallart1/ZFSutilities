"""Two-node iSCSI enrollment offer for newly created or migrated pools.

In a two-node configuration, VM disks on a pool are only usable over iSCSI
once the pool is registered in ``POOL_TARGET`` on both nodes and the iSCSI
target has been rebuilt on the storage host.  This module asks the user,
after a pool is created on the Disks page, whether to run the
``enroll-iscsi-pool`` script to do that automatically, and provides the pure
helpers that decide whether the offer applies at all.

All decision logic is kept in pure helpers (testable without GTK); the
enrollment itself runs as a non-fatal ``BashStep`` on the dataset runner so
an enrollment failure does not look like a pool-creation failure.
"""

import gi

gi.require_version("Gtk", "3.0")

import node_config
from backup_config import log_msg
from command_builders import BashStep
from disks_page import refresh_disks_page, update_disks_button_sensitivity
from gi.repository import Gtk
from path_utils import resolve_local_bin
from pools_page import on_pools_refresh

# Characters allowed in an iSCSI target short name (mirrors the bash
# derive_target_short character class: lowercase letters, digits, dot, hyphen).
_SHORT_NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789.-"


# ---------------------------------------------------------------------------
# Pure helpers (no GTK, no subprocess) — unit-tested directly
# ---------------------------------------------------------------------------


def derive_target_short(pool_name: str) -> str:
    """Derive the iSCSI target short name for *pool_name*.

    Lowercases the pool name and keeps only characters valid in an iSCSI
    target short name ([a-z0-9.-]); everything else is stripped.  This must
    mirror the bash ``derive_target_short`` exactly.
    """
    return "".join(char for char in pool_name.lower() if char in _SHORT_NAME_CHARS)


def is_iscsi_managed_pool(pool_name: str, config: dict | None = None) -> bool:
    """Return True when *pool_name* is enrolled in two-node iSCSI.

    A pool is managed when the configuration is two-node and the pool has a
    ``POOL_TARGET`` entry (``config["pools"]``).
    """
    if config is None:
        config = node_config.load_node_config()
    return node_config.is_two_node(config) and pool_name in (config.get("pools") or set())


def build_enroll_command(
    pool_name: str, short_name: str | None = None, dry_run: bool = False
) -> list[str]:
    """Build the ``enroll-iscsi-pool`` argv for *pool_name*.

    The optional *short_name* overrides the derived iSCSI target short name;
    empty/None parts are omitted.  ``--dry-run`` is placed before the pool
    name when *dry_run* is set.
    """
    script = resolve_local_bin("enroll-iscsi-pool") or "enroll-iscsi-pool"
    argv = [script]
    if dry_run:
        argv.append("--dry-run")
    argv.append(pool_name)
    if short_name:
        argv.append(short_name)
    return argv


def _short_name_is_valid(text: str) -> bool:
    """Return True when *text* is a non-empty valid iSCSI short name."""
    if not text:
        return False
    return all(char in _SHORT_NAME_CHARS for char in text)


def log_manual_enrollment_steps(pool_name: str) -> None:
    """Log the three manual steps that enroll *pool_name* in two-node iSCSI."""
    short = derive_target_short(pool_name)
    log_msg(f'INFO:   1. add [{pool_name}]="{short}" to POOL_TARGET in node.conf on both nodes')
    log_msg("INFO:   2. run 'sudo setup-iscsi-targets' on the storage host")
    log_msg("INFO:   3. run 'sudo rescan-storage' on the compute host")


# ---------------------------------------------------------------------------
# Enrollment offer (GTK)
# ---------------------------------------------------------------------------


def _show_enroll_dialog(app, pool_name: str, default_short: str) -> str | None:
    """Ask whether to enroll *pool_name* in two-node iSCSI.

    Returns the short-name entry text when the user answers YES, or None when
    the offer is declined.  The entry is pre-filled with *default_short*.
    """
    dialog = Gtk.MessageDialog(
        transient_for=app,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Enroll pool '{pool_name}' in two-node iSCSI?",
    )
    dialog.format_secondary_text(
        "Adds POOL_TARGET entries on both nodes, creates the iSCSI target on "
        "the storage host, and rescans the compute host so VM disks on this "
        "pool work over iSCSI."
    )
    entry = Gtk.Entry()
    entry.set_text(default_short)
    entry.set_activates_default(True)
    dialog.set_default_response(Gtk.ResponseType.YES)
    content = dialog.get_content_area()
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


def offer_iscsi_enrollment(app, pool_name: str, on_done=None) -> bool:
    """Offer to enroll *pool_name* in two-node iSCSI after pool creation.

    Returns True when the enrollment step was handed to the dataset runner,
    False when the offer does not apply (single-node or compute host), the
    pool is already enrolled, the runner is busy, or the user declined.
    *on_done* is called without arguments after the enrollment step finishes.
    """
    config = node_config.load_node_config()
    if not node_config.is_two_node(config) or not node_config.is_storage_host(config):
        return False
    if is_iscsi_managed_pool(pool_name, config):
        return False

    runner = getattr(app, "dataset_runner", None)
    if runner is None or runner.running:
        log_msg(
            f"INFO: iSCSI enrollment for pool '{pool_name}' skipped because a "
            "dataset action is not available or already running. Manual steps:"
        )
        log_manual_enrollment_steps(pool_name)
        return False

    default_short = derive_target_short(pool_name)
    short_name = _show_enroll_dialog(app, pool_name, default_short)
    if short_name is None:
        log_msg(f"INFO: iSCSI enrollment for pool '{pool_name}' declined. Manual steps:")
        log_manual_enrollment_steps(pool_name)
        return False
    if not _short_name_is_valid(short_name):
        log_msg(
            f"WARN: Invalid iSCSI short name '{short_name}' for pool "
            f"'{pool_name}' — falling back to '{default_short}'"
        )
        short_name = default_short

    step = BashStep(
        build_enroll_command(pool_name, short_name),
        f"Enroll pool {pool_name} in iSCSI",
        is_rsync=False,
        fatal=False,
    )

    def _on_enroll_complete(cancelled=False, rc=None):
        update_disks_button_sensitivity(app)
        app._disks_inventory_cache.invalidate()
        refresh_disks_page(app)
        on_pools_refresh(app)
        if cancelled:
            log_msg(f"INFO: iSCSI enrollment for pool '{pool_name}' cancelled")
        elif rc:
            log_msg(f"WARN: iSCSI enrollment for pool '{pool_name}' failed (rc={rc})")
        else:
            log_msg(f"INFO: Pool '{pool_name}' enrolled in two-node iSCSI")
        if on_done is not None:
            on_done()

    runner.operation_detail = f"Enroll iSCSI: {pool_name}"
    runner.set_steps([step])
    update_disks_button_sensitivity(app)
    runner.start(on_complete=_on_enroll_complete)
    return True
