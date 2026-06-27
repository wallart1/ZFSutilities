"""
Shared GTK helper utilities used by multiple page modules.
"""

import re
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GLib

from backup_config import log_msg, MSG_LEVELS, set_log_sink
from logging_config import DEFAULT_MSG_LEVEL, parse_msg_level, viewer_should_show
from zfs_repository import get_default_repository, DatasetRow


def set_monospace_font(renderer):
    """Render a Gtk.CellRendererText in a fixed-pitch font.

    Use this for date/time columns so similar values align vertically.
    """
    renderer.set_property("font", "monospace")


def bold_label(text):
    """Return a Gtk.Label with bold Pango markup for section headings."""
    label = Gtk.Label()
    label.set_markup(f"<b>{text}</b>")
    label.set_halign(Gtk.Align.START)
    return label


ACTIVE_COLUMN_WIDTH = 60
TREEVIEW_MIN_WIDTH = 100

# Placeholder rows used while lazy-loading tree children.
PLACEHOLDER_NAMES = {
    "(loading...)", "(no datasets)", "(empty)", "(no holds)"
}


def configure_treeview_column(col, width=None, min_width=20, resizable=True):
    """Configure a TreeViewColumn as fixed-width and user-resizable.

    Fixed-width columns can be resized by the user and, unlike the default
    GROW_ONLY sizing, they allow the window to shrink horizontally. The
    column's minimum width is recorded so the persistence layer can later
    clamp restored widths to the intended minimum.
    """
    if width is None:
        width = min_width
    if min_width is not None:
        col.set_min_width(min_width)
    col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
    col.set_fixed_width(width)
    if resizable:
        col.set_resizable(True)


def setup_row_scroll(scrolled_window, treeview):
    """Set the scroll step increment to match the TreeView row height.

    Connects to the treeview's size-allocate signal to update the vadjustment
    step increment once rows are rendered.
    """
    def _update_step(tv, _allocation):
        model = tv.get_model()
        if model is None:
            return
        tree_iter = model.get_iter_first()
        if tree_iter is None:
            return
        path = model.get_path(tree_iter)
        rect = tv.get_background_area(path, None)
        if rect.height > 0:
            vadj = scrolled_window.get_vadjustment()
            if vadj.get_step_increment() != rect.height:
                vadj.set_step_increment(rect.height)
    treeview.connect("size-allocate", _update_step)


# ---------------------------------------------------------------------------
# Cell data functions
# ---------------------------------------------------------------------------

def dataset_name_cell_func(column, renderer, model, tree_iter, data=None):
    """Style: bold for pools, italic for snapshots and holds, normal for datasets.
    Clone datasets get a [clone] suffix. Placeholder rows are gray italic."""
    name = model.get_value(tree_iter, 0)
    if name in ("(loading...)", "(no datasets)", "(empty)", "(no holds)"):
        renderer.set_property("weight", Pango.Weight.NORMAL)
        renderer.set_property("style", Pango.Style.ITALIC)
        renderer.set_property("foreground", "gray")
        renderer.set_property("markup", None)
        renderer.set_property("text", name)
        return
    ds_type = model.get_value(tree_iter, 2)
    origin = model.get_value(tree_iter, 6)
    if model.iter_parent(tree_iter) is None:
        renderer.set_property("weight", Pango.Weight.BOLD)
        renderer.set_property("style", Pango.Style.NORMAL)
        renderer.set_property("foreground", None)
        renderer.set_property("markup", None)
        renderer.set_property("text", name)
    elif ds_type == "hold" or name.startswith('@'):
        renderer.set_property("weight", Pango.Weight.NORMAL)
        renderer.set_property("style", Pango.Style.ITALIC)
        renderer.set_property("foreground", None)
        renderer.set_property("markup", None)
        renderer.set_property("text", name)
    elif origin and ds_type in ("filesystem", "volume"):
        escaped = GLib.markup_escape_text(name)
        renderer.set_property("weight", Pango.Weight.NORMAL)
        renderer.set_property("style", Pango.Style.NORMAL)
        renderer.set_property("foreground", None)
        renderer.set_property("markup",
                              f'{escaped} <span foreground="gray">[clone]</span>')
    else:
        renderer.set_property("weight", Pango.Weight.NORMAL)
        renderer.set_property("style", Pango.Style.NORMAL)
        renderer.set_property("foreground", None)
        renderer.set_property("markup", None)
        renderer.set_property("text", name)


# ---------------------------------------------------------------------------
# Full name builder
# ---------------------------------------------------------------------------

def build_full_dataset_name(model, tree_iter):
    """Walk up the tree to build the full ZFS name from a TreeIter.

    Stops at hold rows — for a hold, returns only up to the parent snapshot.
    """
    parts = []
    it = tree_iter
    while it is not None:
        val = model.get_value(it, 0)
        ds_type = model.get_value(it, 2)
        if ds_type == "hold":
            it = model.iter_parent(it)
            continue
        parts.append(val)
        it = model.iter_parent(it)
    parts.reverse()
    result = parts[0]
    for p in parts[1:]:
        if p.startswith('@'):
            result += p
        else:
            result += '/' + p
    return result


# ---------------------------------------------------------------------------
# Expand / collapse state helpers
# ---------------------------------------------------------------------------

def get_expanded_rows(store, view):
    """Return set of full dataset names whose rows are currently expanded."""
    expanded = set()
    def _walk(tree_iter, prefix):
        while tree_iter:
            name = store.get_value(tree_iter, 0)
            full = f"{prefix}/{name}" if prefix else name
            path = store.get_path(tree_iter)
            if view.row_expanded(path):
                expanded.add(full)
            child = store.iter_children(tree_iter)
            if child:
                _walk(child, full)
            tree_iter = store.iter_next(tree_iter)
    _walk(store.get_iter_first(), "")
    return expanded


def restore_expanded_rows(store, view, expanded):
    """Re-expand rows that were previously expanded, loading children as needed."""
    def _walk(tree_iter, prefix):
        while tree_iter:
            name = store.get_value(tree_iter, 0)
            full = f"{prefix}/{name}" if prefix else name
            next_iter = store.iter_next(tree_iter)
            if full in expanded:
                path = store.get_path(tree_iter)
                loaded = store.get_value(tree_iter, 7)
                if not loaded and name != "(loading...)":
                    on_row_expanded(view, tree_iter, path)
                view.expand_row(path, False)
                child = store.iter_children(tree_iter)
                if child:
                    _walk(child, full)
            tree_iter = next_iter
    _walk(store.get_iter_first(), "")


def expand_tree_recursively(view, store, tree_iter=None):
    """Expand *tree_iter* and all of its lazy-loaded descendants.

    If *tree_iter* is None, start from the first root row.  Placeholder rows
    such as ``(loading...)`` are skipped.
    """
    if tree_iter is None:
        tree_iter = store.get_iter_first()
    if tree_iter is None:
        return

    path = store.get_path(tree_iter)
    if not view.row_expanded(path):
        view.expand_row(path, False)

    child = store.iter_children(tree_iter)
    while child:
        name = store.get_value(child, 0)
        if name not in PLACEHOLDER_NAMES:
            expand_tree_recursively(view, store, child)
        child = store.iter_next(child)


def _tree_path_indices(path):
    """Return a list of integer indices for a Gtk.TreePath or test path."""
    if hasattr(path, "get_indices"):
        return list(path.get_indices())
    if isinstance(path, str):
        return [int(p) for p in path.split(":") if p]
    if isinstance(path, (list, tuple)):
        return [int(p) for p in path]
    return []


def expand_path_to_row(view, store, path):
    """Expand every ancestor of *path* so the target row is visible.

    Lazy-loaded ancestors are loaded before they are expanded.  The target
    row itself is not expanded.  Returns the target TreeIter, or None if the
    path cannot be reached.
    """
    indices = _tree_path_indices(path)
    if not indices:
        return None

    it = None
    for depth, idx in enumerate(indices):
        if depth == 0:
            it = store.get_iter_first()
            for _ in range(idx):
                if it is None:
                    return None
                it = store.iter_next(it)
        else:
            child = store.iter_children(it)
            it = child
            for _ in range(idx):
                if it is None:
                    return None
                it = store.iter_next(it)

        if it is None:
            return None

        subpath = Gtk.TreePath.new_from_indices(indices[:depth + 1])
        name = store.get_value(it, 0)
        loaded = store.get_value(it, 7)
        if (
            depth < len(indices) - 1
            and not view.row_expanded(subpath)
            and not loaded
            and name not in PLACEHOLDER_NAMES
        ):
            on_row_expanded(view, it, subpath)
        if depth < len(indices) - 1 and not view.row_expanded(subpath):
            view.expand_row(subpath, False)

    return it


# ---------------------------------------------------------------------------
# Lazy loaders
# ---------------------------------------------------------------------------

def on_row_expanded(view, tree_iter, path, _data=None):
    """Load children on demand when a row is expanded."""
    store = view.get_model()
    loaded = store.get_value(tree_iter, 7)
    name = store.get_value(tree_iter, 0)
    ds_type = store.get_value(tree_iter, 2)
    if loaded:
        return

    # Mark as loaded to prevent re-entry
    store.set_value(tree_iter, 7, True)

    repo = getattr(view, '_zfs_repo', None) or get_default_repository()

    # Determine what to load based on node type
    parent = store.iter_parent(tree_iter)
    if parent is None:
        load_pool_children(store, tree_iter, name, repo=repo)
    elif ds_type in ("filesystem", "volume") or (not name.startswith('@') and ds_type != "hold"):
        full_name = build_full_dataset_name(store, tree_iter)
        load_dataset_children(store, tree_iter, full_name, repo=repo)
    elif name.startswith('@') or ds_type == "snapshot":
        full_name = build_full_dataset_name(store, tree_iter)
        load_snapshot_children(store, tree_iter, full_name, repo=repo)

    # If nothing loaded, add placeholder BEFORE removing dummy so GTK never
    # sees a childless row (which would auto-collapse it).
    has_real = False
    child = store.iter_children(tree_iter)
    while child:
        if store.get_value(child, 0) != "(loading...)":
            has_real = True
            break
        child = store.iter_next(child)

    if not has_real:
        if parent is None:
            label = "(no datasets)"
        elif ds_type in ("filesystem", "volume") or (not name.startswith('@') and ds_type != "hold"):
            label = "(empty)"
        elif name.startswith('@') or ds_type == "snapshot":
            label = "(no holds)"
        else:
            label = "(empty)"
        store.append(tree_iter, [label, "", "", "", "", "", "", True])

    # Now safe to remove dummy — row still has at least one child
    child = store.iter_children(tree_iter)
    while child:
        next_child = store.iter_next(child)
        if store.get_value(child, 0) == "(loading...)":
            store.remove(child)
        child = next_child


def load_pool_children(store, pool_iter, pool_name, repo=None):
    """Load direct child datasets under a pool."""
    repo = repo or get_default_repository()
    try:
        for row in repo.list_datasets(pool=pool_name, depth=1):
            row_data = [row.creation, row.ds_type, row.used, row.avail, row.refer]
            origin_val = row.origin if row.origin != "-" else ""

            if row.name == pool_name:
                # Update pool row with real data
                store.set(pool_iter,
                          1, row_data[0], 2, row_data[1],
                          3, row_data[2], 4, row_data[3],
                          5, row_data[4], 6, "")
                continue

            short_name = row.name.rsplit('/', 1)[-1]
            child_iter = store.append(
                pool_iter,
                [short_name] + row_data + [origin_val, False]
            )
            # Add dummy so dataset appears expandable
            store.append(child_iter, ["(loading...)", "", "", "", "", "", "", True])

    except subprocess.CalledProcessError as e:
        store.append(pool_iter,
                     ["(error)", str(e), "", "", "", "", "", True])


def load_dataset_children(store, ds_iter, ds_name, repo=None):
    """Load snapshots and sub-datasets for a dataset (snapshots first)."""
    repo = repo or get_default_repository()

    # Load snapshots of this exact dataset (not descendants).
    # depth=1 is required because ZFS does not list a dataset's own snapshots
    # at depth=0; depth=1 returns the target's snapshots and direct children's.
    try:
        snaps = [
            row for row in repo.list_snapshots(ds_name, depth=1)
            if row.name.split('@')[0] == ds_name
        ]
        for row in snaps:
            snap_part = '@' + row.name.split('@')[1]
            row_data = [row.creation, row.ds_type, row.used, row.avail, row.refer]
            clones_val = row.clones if row.clones != "-" else ""
            child_iter = store.append(
                ds_iter,
                [snap_part] + row_data + [clones_val, False]
            )
            store.append(child_iter, ["(loading...)", "", "", "", "", "", "", True])
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Could not load snapshots for {ds_name}: {e}")

    # Load sub-datasets
    try:
        children = repo.list_datasets(pool=ds_name, depth=1)
        for row in children:
            if row.name == ds_name or row.ds_type == "snapshot":
                continue
            row_data = [row.creation, row.ds_type, row.used, row.avail, row.refer]
            origin_val = row.origin if row.origin != "-" else ""
            short_name = row.name.rsplit('/', 1)[-1]
            child_iter = store.append(
                ds_iter,
                [short_name] + row_data + [origin_val, False]
            )
            store.append(child_iter, ["(loading...)", "", "", "", "", "", "", True])
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log_msg(f"WARN: Could not load children for {ds_name}: {e}")


def load_snapshot_children(store, snap_iter, snap_name, repo=None):
    """Load holds for a snapshot."""
    repo = repo or get_default_repository()
    try:
        for hold in repo.list_holds(snap_name):
            store.append(
                snap_iter,
                [hold.tag, hold.date, "hold", "", "", "", "", True]
            )
    except subprocess.CalledProcessError:
        pass

# ---------------------------------------------------------------------------
# Button styling
# ---------------------------------------------------------------------------

def set_button_markup_red(button, dirty):
    """Set a button label red if dirty, normal if clean."""
    def _find_label(widget):
        if isinstance(widget, Gtk.Label):
            return widget
        if hasattr(widget, 'get_children'):
            for child in widget.get_children():
                found = _find_label(child)
                if found:
                    return found
        if hasattr(widget, 'get_child'):
            child = widget.get_child()
            if child:
                return _find_label(child)
        return None
    lbl = _find_label(button)
    if lbl:
        text = lbl.get_text()
        lbl.set_markup(f'<span foreground="red">{text}</span>' if dirty else text)


# ---------------------------------------------------------------------------
# Dirty state tracker
# ---------------------------------------------------------------------------

class DirtyTracker:
    """Generic dirty-state tracker for a page.

    Usage:
        tracker = DirtyTracker(app, collect_fn, save_button_attr_name)
        tracker.mark_clean()          # call after saving
        tracker.check()               # call on any change
        tracker.revert(load_fn)       # call to revert
    """

    def __init__(self, app, collect_fn, save_button_attr):
        self.app = app
        self.collect_fn = collect_fn
        self.save_button_attr = save_button_attr
        self._saved = collect_fn()

    def mark_clean(self):
        self._saved = self.collect_fn()
        self._update_button(False)

    def check(self):
        dirty = self.collect_fn() != self._saved
        self._update_button(dirty)
        return dirty

    def revert(self, load_fn):
        load_fn(self._saved)
        self._update_button(False)

    def _update_button(self, dirty):
        btn = getattr(self.app, self.save_button_attr, None)
        if btn:
            set_button_markup_red(btn, dirty)


# ---------------------------------------------------------------------------
# Dialog builders
# ---------------------------------------------------------------------------

def create_dialog(title, parent, buttons, default_response=None, size=None):
    """Create a standard Gtk.Dialog with margins and spacing."""
    dialog = Gtk.Dialog(
        title=title, transient_for=parent, modal=True, destroy_with_parent=True
    )
    for btn_text, response in buttons:
        dialog.add_button(btn_text, response)
    if default_response is not None:
        dialog.set_default_response(default_response)
    if size:
        dialog.set_default_size(*size)
    content = dialog.get_content_area()
    content.set_spacing(10)
    content.set_margin_start(10)
    content.set_margin_end(10)
    content.set_margin_top(10)
    content.set_margin_bottom(10)
    return dialog


def add_scrolled_text_view(parent, text, monospace=True,
                           wrap_mode=Gtk.WrapMode.NONE, min_height=None):
    """Add a non-editable scrolled TextView to a container."""
    buf = Gtk.TextBuffer()
    buf.set_text(text)
    tv = Gtk.TextView(buffer=buf)
    tv.set_editable(False)
    tv.set_cursor_visible(False)
    if monospace:
        tv.set_monospace(True)
    tv.set_wrap_mode(wrap_mode)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    if min_height is not None:
        sw.set_min_content_height(min_height)
    sw.add(tv)
    parent.add(sw)
    return sw


# ---------------------------------------------------------------------------
# ZFS path / process helpers
# ---------------------------------------------------------------------------

def get_snapshot_mountpoint(dataset, snap_name, repo=None):
    """Return the on-disk path where a ZFS snapshot is accessible."""
    repo = repo or get_default_repository()
    mountpoint = repo.get_property(dataset, "mountpoint")
    return f"{mountpoint}/.zfs/snapshot/{snap_name}"


def get_busy_processes(path):
    """Return a list of (pid, name) tuples for processes using *path*."""
    pids = set()
    try:
        result = subprocess.run(
            ["fuser", "-m", path], capture_output=True, text=True, check=True,
        )
        for line in result.stdout.strip().splitlines():
            if ":" in line:
                pids.update(line.split(":", 1)[1].strip().split())
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if not pids:
        try:
            result = subprocess.run(
                ["lsof", "-t", "+D", path], capture_output=True, text=True, check=True,
            )
            pids.update(result.stdout.strip().split())
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    processes = []
    for pid in pids:
        try:
            ps = subprocess.run(
                ["ps", "-p", pid, "-o", "comm="], capture_output=True, text=True, check=True,
            )
            name = ps.stdout.strip()
            if name:
                processes.append((pid, name))
        except subprocess.CalledProcessError:
            continue
    return processes


def diagnose_dataset_busy(target, stderr_text="", repo=None):
    """Diagnose why a ZFS dataset or snapshot cannot be destroyed.

    Logs specific causes via log_msg so the user knows what to fix.
    """
    repo = repo or get_default_repository()
    found_cause = False
    is_snapshot = "@" in target

    if stderr_text:
        log_msg(f"WARN: ZFS reported: {stderr_text.strip()}")
    log_msg(f"WARN: Diagnosing why {target} cannot be destroyed...")

    # 1. Clone dependents
    if is_snapshot:
        try:
            clones = repo.get_clones(target)
            if clones and clones != "-":
                log_msg(f"WARN:   → Snapshot has clone dependents: {clones}")
                log_msg("WARN:     Use 'promote-vm-clone' or 'zfs promote' to cut dependencies first.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    else:
        try:
            clone_snaps = repo.get_recursive_snapshot_clones(target)
            if clone_snaps:
                log_msg(f"WARN:   → One or more snapshots of {target} have clone dependents.")
                log_msg("WARN:     Use 'promote-vm-clone' or 'zfs promote' to cut dependencies first.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 2. ZFS holds (snapshots only)
    if is_snapshot:
        try:
            holds = repo.list_holds(target)
            if holds:
                tags = sorted({hold.tag for hold in holds})
                log_msg(f"WARN:   → Snapshot has holds: {' '.join(tags)}")
                log_msg("WARN:     Use 'releaseholds' option or 'zfs release <tag> <snap>'.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 3. Mounted / open files
    try:
        mounted = repo.get_property(target, "mounted")
        if mounted == "yes":
            mountpoint = repo.get_property(target, "mountpoint")
            log_msg(f"WARN:   → Dataset is mounted at {mountpoint}.")
            procs = get_busy_processes(mountpoint)
            if procs:
                names = " ".join({name for _pid, name in procs})
                log_msg(f"WARN:     Open processes: {names}")
                log_msg("WARN:     Stop the processes or unmount before destroying.")
            else:
                log_msg("WARN:     No open processes detected (try unmounting first).")
            found_cause = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 4. Active send / receive
    try:
        token = repo.get_property(target, "receive_resume_token")
        if token and token != "-":
            log_msg("WARN:   → Dataset has an active or interrupted receive (resume token present).")
            log_msg("WARN:     Abort with 'zfs receive -A <dataset>' or allow it to complete.")
            found_cause = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ["pgrep", "-f", f"zfs send.*{target}"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            log_msg(f"WARN:   → An active 'zfs send' involving {target} is running.")
            log_msg("WARN:     Wait for it to complete before destroying.")
            found_cause = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 5. Bookmarks (snapshots only)
    if is_snapshot:
        try:
            dataset, snap_name = target.split("@", 1)
            bmarks = repo.list_bookmarks(dataset, snap_name)
            if bmarks:
                log_msg(f"WARN:   → Snapshot is referenced by bookmark(s): {' '.join(bmarks)}")
                log_msg("WARN:     Destroy the bookmark(s) first with 'zfs destroy <bookmark>'.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 6. iSCSI LUN exposure (zvols only)
    bsname = target.split("/")[-1]
    vmid_match = re.fullmatch(r"vm-(\d+)-disk-\d+", bsname)
    if vmid_match:
        try:
            result = subprocess.run(
                ["targetcli", "/backstores/block", "ls"],
                capture_output=True, text=True,
            )
            if result.returncode == 0 and f" {bsname} " in result.stdout:
                lun_info = ""
                try:
                    iscsi_out = subprocess.run(
                        ["targetcli", "/iscsi", "ls"],
                        capture_output=True, text=True, check=True,
                    ).stdout
                    for t in re.findall(r"iqn\.\S+", iscsi_out):
                        try:
                            luns = subprocess.run(
                                ["targetcli", f"/iscsi/{t}/tpg1/luns", "ls"],
                                capture_output=True, text=True, check=True,
                            ).stdout
                            if bsname in luns:
                                m = re.search(rf"lun(\d+).*?{re.escape(bsname)}", luns)
                                if m:
                                    lun_info = f"{t} (LUN {m.group(1)})"
                                    break
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            continue
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

                if lun_info:
                    log_msg(f"WARN:   → Zvol is exposed as an iSCSI LUN on {lun_info}.")
                else:
                    log_msg(f"WARN:   → Zvol has an iSCSI backstore ({bsname}) but no LUN mapping.")
                log_msg("WARN:     Use 'remove-vm-disk' or targetcli to tear down iSCSI first.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 7. Running VM using the zvol
    if vmid_match:
        vmid = vmid_match.group(1)
        try:
            result = subprocess.run(
                ["qm", "status", vmid],
                capture_output=True, text=True, check=True,
            )
            if "running" in result.stdout:
                log_msg(f"WARN:   → VM {vmid} is RUNNING and may be using {target}.")
                log_msg("WARN:     Stop the VM before destroying this zvol.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # 8. NFS / SMB shares
    for prop, label in [("sharenfs", "NFS"), ("sharesmb", "SMB")]:
        try:
            value = subprocess.run(
                ["zfs", "get", "-H", "-o", "value", prop, target],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            if value and value != "off" and value != "-":
                log_msg(f"WARN:   → Dataset is shared via {label} ({value}).")
                log_msg(f"WARN:     Unshare with 'zfs set {prop}=off {target}' before destroying.")
                found_cause = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    if not found_cause:
        log_msg("WARN:   → No specific cause identified. Common remaining reasons:")
        log_msg("WARN:       • The dataset is referenced by a child snapshot that is busy.")
        log_msg("WARN:       • A process has the dataset open through a different path.")
        log_msg("WARN:       • The pool is undergoing a scrub or resilver.")
        log_msg("WARN:     Try: fuser -m <mountpoint>  or  lsof +D <mountpoint>")


# ---------------------------------------------------------------------------
# Placeholder page
# ---------------------------------------------------------------------------

def create_placeholder_page(title, description):
    """Create a placeholder page with title and description."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(20)
    box.set_margin_end(20)
    box.set_margin_top(20)
    box.set_margin_bottom(20)

    title_label = Gtk.Label()
    title_label.set_markup(f"<big><b>{title}</b></big>")
    title_label.set_halign(Gtk.Align.START)
    title_label.set_selectable(True)
    box.pack_start(title_label, False, False, 0)

    box.pack_start(Gtk.Separator(), False, False, 5)

    desc_label = Gtk.Label(label=description)
    desc_label.set_halign(Gtk.Align.START)
    desc_label.set_valign(Gtk.Align.START)
    desc_label.set_line_wrap(True)
    desc_label.set_selectable(True)
    box.pack_start(desc_label, False, False, 0)

    placeholder = Gtk.Label(label="(Content to be implemented)")
    placeholder.set_valign(Gtk.Align.CENTER)
    placeholder.set_vexpand(True)
    placeholder.set_opacity(0.5)
    box.pack_start(placeholder, True, True, 0)

    return box


# ---------------------------------------------------------------------------
# Editable list view (toggle + two text columns + buttons)
# ---------------------------------------------------------------------------

class EditableListView:
    """Reusable ListStore(bool, str, str) with Add/Remove/Move buttons."""

    def __init__(self, on_changed=None, columns=None):
        self.on_changed = on_changed
        self.columns = columns or [
            (1, "Source", 120), (2, "Destination", 120)
        ]
        self.store = Gtk.ListStore(bool, str, str)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggle)
        col0 = Gtk.TreeViewColumn("Active", toggle, active=0)
        configure_treeview_column(col0, width=ACTIVE_COLUMN_WIDTH,
                                  min_width=ACTIVE_COLUMN_WIDTH)
        self.view.append_column(col0)

        for idx, title, width in self.columns:
            r = Gtk.CellRendererText()
            r.set_property("editable", True)
            r.connect("edited", self._on_edited, idx)
            r.connect("editing-started", self._on_editing_started, idx)
            col = Gtk.TreeViewColumn(title, r, text=idx)
            configure_treeview_column(col, width=width)
            self.view.append_column(col)

        self.view.connect("row-activated", on_row_activated, self.columns[0][0])
        self.view.set_reorderable(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(120)
        scroll.add(self.view)
        setup_row_scroll(scroll, self.view)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        for label, cb in (("Add", self._on_add),
                          ("Remove", self._on_remove)):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            btn_box.pack_start(btn, False, False, 0)

        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.widget.pack_start(scroll, True, True, 0)
        self.widget.pack_start(btn_box, False, False, 0)

        self.store.connect("row-changed", self._notify)
        self.store.connect("row-inserted", self._notify)
        self.store.connect("row-deleted", self._notify)

    def set_on_changed(self, on_changed):
        self.on_changed = on_changed

    def _notify(self, *args):
        if self.on_changed:
            self.on_changed()

    def _on_toggle(self, renderer, path):
        tree_iter = self.store.get_iter_from_string(path)
        self.store.set_value(tree_iter, 0, not self.store.get_value(tree_iter, 0))

    def _on_edited(self, renderer, path, new_text, col_idx):
        tree_iter = self.store.get_iter_from_string(path)
        self.store.set_value(tree_iter, col_idx, new_text)

    def _on_editing_started(self, renderer, editable, path, col_idx):
        editable.connect(
            "key-press-event", handle_editing_key_press,
            self.view, path, col_idx, [c[0] for c in self.columns])

    def _on_add(self, button):
        tree_iter = self.store.append([True, "", ""])
        path = self.store.get_path(tree_iter)
        GLib.idle_add(self.view.set_cursor, path, self.view.get_column(1), True)

    def _on_remove(self, button):
        sel = self.view.get_selection()
        model, tree_iter = sel.get_selected()
        if tree_iter:
            model.remove(tree_iter)

    def get_store(self):
        return self.store

    def get_view(self):
        return self.view

    def get_widget(self):
        return self.widget

    def set_data(self, rows):
        """rows: iterable of (active, source, dest)"""
        self.store.clear()
        for active, src, dst in rows:
            self.store.append([active, src, dst])

    def get_data(self):
        """Return list of dicts."""
        return [
            {"active": row[0], "source": row[1], "dest": row[2]}
            for row in self.store
        ]


# ---------------------------------------------------------------------------
# Variable row builder (label + entry/combo + help icon)
# ---------------------------------------------------------------------------

def add_var_row(grid, row, key, variables, widgets_dict,
                yn_vars=None, topic_map=None):
    """Add a label + widget row to a grid for the given variable key.

    If key is in yn_vars, a Y/N ComboBoxText is created.
    Otherwise a Gtk.Entry is created.
    The widget is stored in widgets_dict[key].
    """
    lbl = Gtk.Label(label=key)
    lbl.set_halign(Gtk.Align.END)
    grid.attach(lbl, 0, row, 1, 1)

    yn_vars = yn_vars or set()
    if key in yn_vars:
        widget = Gtk.ComboBoxText()
        widget.append_text("Y")
        widget.append_text("N")
        default = "N" if key == "allow_destructive" else "Y"
        widget.set_active(0 if variables.get(key, default) == "Y" else 1)
    else:
        widget = Gtk.Entry()
        widget.set_text(variables.get(key, ""))
        widget.set_hexpand(True)
        widget.set_width_chars(1)

    grid.attach(widget, 1, row, 1, 1)
    widgets_dict[key] = widget


# ---------------------------------------------------------------------------
# TreeView search navigation
# ---------------------------------------------------------------------------

def on_row_activated(treeview, path, column, edit_col_idx):
    """When a row is clicked/activated, start editing the specified column."""
    col = treeview.get_column(edit_col_idx)
    treeview.set_cursor(path, col, True)


def on_toggle(renderer, path, store):
    """Toggle a boolean value in a ListStore."""
    tree_iter = store.get_iter_from_string(path)
    store.set_value(tree_iter, 0, not store.get_value(tree_iter, 0))


def on_cell_edited(renderer, path, new_text, store, col_idx):
    """Update a cell value in a ListStore."""
    tree_iter = store.get_iter_from_string(path)
    store.set_value(tree_iter, col_idx, new_text)


def handle_editing_key_press(widget, event, treeview, path_str, col_idx,
                               editable_cols):
    """Handle Tab/Shift+Tab across editable columns in a TreeView."""
    if event.keyval == Gdk.KEY_Tab:
        widget.editing_done()
        widget.remove_widget()
        model = treeview.get_model()
        path = Gtk.TreePath.new_from_string(path_str)
        cur = editable_cols.index(col_idx)
        if cur < len(editable_cols) - 1:
            next_col = editable_cols[cur + 1]
            GLib.idle_add(treeview.set_cursor, path,
                          treeview.get_column(next_col), True)
        else:
            nxt = model.iter_next(model.get_iter(path))
            if nxt:
                nxt_path = model.get_path(nxt)
                GLib.idle_add(treeview.set_cursor, nxt_path,
                              treeview.get_column(editable_cols[0]), True)
        return True
    elif event.keyval == Gdk.KEY_ISO_Left_Tab:
        widget.editing_done()
        widget.remove_widget()
        model = treeview.get_model()
        path = Gtk.TreePath.new_from_string(path_str)
        cur = editable_cols.index(col_idx)
        if cur > 0:
            prev_col = editable_cols[cur - 1]
            GLib.idle_add(treeview.set_cursor, path,
                          treeview.get_column(prev_col), True)
        else:
            row_idx = path[0]
            if row_idx > 0:
                prev_path = Gtk.TreePath.new_from_indices([row_idx - 1])
                GLib.idle_add(treeview.set_cursor, prev_path,
                              treeview.get_column(editable_cols[-1]), True)
        return True
    return False


class TreeSearch:
    """Debounced search with prev/next navigation for a Gtk.TreeView."""

    def __init__(self, treeview, entry, results_label, prev_btn, next_btn,
                 placeholder_names=None, full_name_func=None):
        self.view = treeview
        self.entry = entry
        self.results_label = results_label
        self.prev_btn = prev_btn
        self.next_btn = next_btn
        self.placeholder_names = placeholder_names or {
            "(loading...)", "(no datasets)", "(empty)", "(no holds)"
        }
        self.full_name_func = full_name_func
        self._text = ""
        self._matches = []
        self._current_idx = -1
        self._debounce_id = None
        self._frozen = False

        self.entry.connect("changed", self._on_changed)
        self.entry.connect("activate", self._on_activate)
        self.prev_btn.connect("clicked", self._on_prev)
        self.next_btn.connect("clicked", self._on_next)

    def _on_changed(self, entry):
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(
            150, self._do_search, entry.get_text().strip()
        )

    def _do_search(self, text):
        self._debounce_id = None
        self._text = text
        self._run_search()
        return False

    def _on_activate(self, entry):
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = None
        self._text = entry.get_text().strip()
        self._run_search()

    def _find_matches(self, store, text):
        matches = []
        lower = text.lower()

        def _walk(tree_iter):
            while tree_iter:
                name = store.get_value(tree_iter, 0)
                if name not in self.placeholder_names:
                    candidates = [name]
                    if self.full_name_func:
                        full_name = self.full_name_func(store, tree_iter)
                        if full_name and full_name != name:
                            candidates.append(full_name)
                    for candidate in candidates:
                        if lower in candidate.lower():
                            matches.append(store.get_path(tree_iter))
                            break
                child = store.iter_children(tree_iter)
                if child:
                    _walk(child)
                tree_iter = store.iter_next(tree_iter)

        _walk(store.get_iter_first())
        return matches

    def _run_search(self):
        text = self._text
        if not text:
            self._matches = []
            self._current_idx = -1
            self.view.get_selection().unselect_all()
            self._update_ui()
            return

        store = self.view.get_model()
        prev_path = None
        if self._matches and self._current_idx >= 0:
            try:
                prev_path = self._matches[self._current_idx]
            except IndexError:
                prev_path = None

        self._matches = self._find_matches(store, text)

        if not self._matches:
            self._current_idx = -1
            self.view.get_selection().unselect_all()
            self._update_ui()
            return

        if prev_path is not None and prev_path in self._matches:
            self._current_idx = self._matches.index(prev_path)
        elif self._current_idx >= 0 and self._current_idx < len(self._matches):
            pass
        else:
            self._current_idx = 0

        self._goto_match(self._current_idx)

    def _goto_match(self, idx):
        if not self._matches or idx < 0 or idx >= len(self._matches):
            return
        path = self._matches[idx]
        store = self.view.get_model()
        self.freeze()
        try:
            expand_path_to_row(self.view, store, path)
            selection = self.view.get_selection()
            selection.unselect_all()
            selection.select_path(path)
            self.view.scroll_to_cell(path, None, True, 0.5, 0.5)
            self._update_ui()
        finally:
            self.thaw()
            self._update_matches_from_store()

    def _update_matches_from_store(self):
        """Recompute matches after expanding rows without changing selection."""
        if not self._text:
            return
        store = self.view.get_model()
        current_path = None
        if 0 <= self._current_idx < len(self._matches):
            current_path = self._matches[self._current_idx]
        self._matches = self._find_matches(store, self._text)
        if current_path is not None and current_path in self._matches:
            self._current_idx = self._matches.index(current_path)
        elif self._matches:
            self._current_idx = min(self._current_idx, len(self._matches) - 1)
            if self._current_idx < 0:
                self._current_idx = 0
        else:
            self._current_idx = -1
        self._update_ui()

    def _update_ui(self):
        count = len(self._matches)
        idx = self._current_idx
        if self._text and count > 0:
            self.results_label.set_text(f"{idx + 1} of {count}")
        elif self._text:
            self.results_label.set_text("0 of 0")
        else:
            self.results_label.set_text("")
        self.prev_btn.set_sensitive(count > 0 and idx > 0)
        self.next_btn.set_sensitive(count > 0)

    def _on_prev(self, button):
        if not self._matches or self._current_idx <= 0:
            return
        self._current_idx -= 1
        self._goto_match(self._current_idx)

    def _on_next(self, button):
        if not self._matches:
            return
        if self._current_idx < len(self._matches) - 1:
            self._current_idx += 1
        else:
            self._current_idx = 0
        self._goto_match(self._current_idx)

    def freeze(self):
        """Suppress search re-runs triggered by expand/collapse signals."""
        self._frozen = True

    def thaw(self):
        """Resume search re-runs triggered by expand/collapse signals."""
        self._frozen = False

    def handle_expand_collapse(self):
        """Call this from row-expanded/row-collapsed handlers if search is active."""
        if self._text and not self._frozen:
            self._run_search()

    def clear(self):
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = None
        self.entry.set_text("")
        self._text = ""
        self._matches = []
        self._current_idx = -1
        self.view.get_selection().unselect_all()
        self._update_ui()


def get_tree_selection_items(view):
    """Get structured list of selected items from the datasets tree.

    Returns list of dicts:
      {"type": "pool",     "name": pool_name}
      {"type": "dataset",  "name": full_dataset_name}
      {"type": "snapshot", "name": snap_short (without @), "dataset": full_dataset}
      {"type": "hold",     "tag": tag, "snapshot": snap_short, "dataset": full_dataset}
    """
    selection = view.get_selection()
    model, paths = selection.get_selected_rows()
    items = []
    for path in paths:
        tree_iter = model.get_iter(path)
        name = model.get_value(tree_iter, 0)
        if name in ("(loading...)", "(no datasets)", "(empty)", "(no holds)"):
            continue
        ds_type = model.get_value(tree_iter, 2)

        if ds_type == "hold":
            parent_iter = model.iter_parent(tree_iter)
            snap_name = model.get_value(parent_iter, 0).lstrip('@')
            ds_iter = model.iter_parent(parent_iter)
            dataset = build_full_dataset_name(model, ds_iter)
            items.append({
                "type": "hold",
                "tag": name,
                "snapshot": snap_name,
                "dataset": dataset,
                "zfs_type": ds_type,
            })
        elif name.startswith('@') or ds_type == "snapshot":
            parent_iter = model.iter_parent(tree_iter)
            dataset = build_full_dataset_name(model, parent_iter)
            items.append({
                "type": "snapshot",
                "name": name.lstrip('@'),
                "dataset": dataset,
                "zfs_type": ds_type,
            })
        elif model.iter_parent(tree_iter) is None:
            items.append({"type": "pool", "name": name, "zfs_type": ds_type})
        else:
            items.append({
                "type": "dataset",
                "name": build_full_dataset_name(model, tree_iter),
                "zfs_type": ds_type,
            })
    return items


def _allow_scrolled_treeview_shrink(treeview):
    """Let the ScrolledWindow containing *treeview* shrink narrower than its child.

    A TreeView with fixed-width columns requests a natural width equal to the
    sum of those columns, which normally forces the parent window to remain
    wide. Setting a small min-content-width on the surrounding ScrolledWindow
    (and a small minimum size on the TreeView itself) allows the window to
    shrink and relies on horizontal scrolling for any overflow.
    """
    treeview.set_size_request(TREEVIEW_MIN_WIDTH, -1)
    parent = treeview.get_parent()
    while parent is not None:
        # Use duck-typing so the helper works both with real GTK widgets and
        # with MagicMock-based test fixtures.
        if hasattr(parent, "set_min_content_width"):
            parent.set_min_content_width(TREEVIEW_MIN_WIDTH)
            parent.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            return
        parent = parent.get_parent()


def _ensure_treeview_scrolling(treeview):
    """Apply _allow_scrolled_treeview_shrink once *treeview* is realized."""
    def _on_realize(tv):
        _allow_scrolled_treeview_shrink(tv)

    if treeview.get_realized():
        _on_realize(treeview)
    else:
        treeview.connect("realize", _on_realize)


def reset_resizable_columns_to_min_width(window):
    """Reset every resizable TreeViewColumn in *window* to a narrow width.

    Walks the widget hierarchy recursively. For each Gtk.TreeView, every
    column with get_resizable() True is reset to its own minimum width.
    Non-resizable columns are left unchanged.

    Returns the number of columns reset.
    """
    count = 0

    def _walk(widget):
        nonlocal count
        if hasattr(widget, "get_columns") and callable(widget.get_columns):
            for col in widget.get_columns():
                if col.get_resizable():
                    min_width = max(20, col.get_min_width())
                    col.set_min_width(min_width)
                    col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                    col.set_fixed_width(min_width)
                    count += 1
        if hasattr(widget, "get_children"):
            for child in widget.get_children():
                _walk(child)
        elif hasattr(widget, "get_child"):
            child = widget.get_child()
            if child:
                _walk(child)

    _walk(window)
    return count


def confirm_and_minimize_width(window):
    """Prompt the user, then reset resizable columns and shrink *window*.

    *window* must provide the methods used by ZFSUtilitiesWindow
    (get_window, unmaximize, get_size, resize, config).
    """
    dialog = Gtk.MessageDialog(
        transient_for=window,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text="Reset column widths and minimize window?",
    )
    dialog.format_secondary_text(
        "This will reset all resizable table column widths across every "
        "tab to their minimum values and shrink the main window as narrow "
        "as possible."
    )
    ok_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
    if ok_button:
        ok_button.set_label("Minimize Width")

    response = dialog.run()
    dialog.destroy()

    if response != Gtk.ResponseType.OK:
        log_msg("VERB: Minimize width cancelled")
        return

    gdk_window = window.get_window()
    if gdk_window and (gdk_window.get_state() & Gdk.WindowState.MAXIMIZED):
        window.unmaximize()

    count = reset_resizable_columns_to_min_width(window)

    # Discard saved column widths so they are not restored later
    window.config.setdefault("ui_state", {}).setdefault("treeview_columns", {})
    window.config["ui_state"]["treeview_columns"] = {}
    from backup_config import save_config
    save_config(window.config)

    _width, height = window.get_size()
    # Ask GTK to re-negotiate the new minimum size before requesting the
    # narrow width, otherwise the resize may be clamped to the old minimum.
    window.queue_resize()
    window.resize(1, height)

    log_msg(
        f"INFO: Reset {count} column width(s) to minimum and minimized "
        f"window width"
    )


def create_menu_bar(app):
    """Create the menu bar and attach it to app.main_box."""
    menu_bar = Gtk.MenuBar()
    app.main_box.pack_start(menu_bar, False, False, 0)

    file_menu = Gtk.Menu()
    file_item = Gtk.MenuItem(label="File")
    file_item.set_submenu(file_menu)
    menu_bar.append(file_item)

    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", app.on_quit)
    file_menu.append(quit_item)

    view_menu = Gtk.Menu()
    view_item = Gtk.MenuItem(label="View")
    view_item.set_submenu(view_menu)
    menu_bar.append(view_item)

    minimize_width_item = Gtk.MenuItem(label="Minimize Width...")
    minimize_width_item.connect("activate", app.on_minimize_width)
    view_menu.append(minimize_width_item)

    help_menu = Gtk.Menu()
    help_item = Gtk.MenuItem(label="Help")
    help_item.set_submenu(help_menu)
    menu_bar.append(help_item)

    docs_item = Gtk.MenuItem(label="Documentation")
    docs_item.connect("activate", app.on_documentation)
    help_menu.append(docs_item)

    help_page_item = Gtk.MenuItem(label="Help with this page")
    help_page_item.connect("activate", app.on_help_with_page)
    help_menu.append(help_page_item)

    sep = Gtk.SeparatorMenuItem()
    help_menu.append(sep)

    editor_item = Gtk.MenuItem(label="Set Documentation Editor...")
    editor_item.connect("activate", app.on_set_docs_editor)
    help_menu.append(editor_item)

    about_item = Gtk.MenuItem(label="About")
    about_item.connect("activate", app.on_about)
    help_menu.append(about_item)


class TextViewSearch:
    """Reusable search widget group for a Gtk.TextView.

    Provides a search entry, Search / Reset / Previous / Next buttons,
    and a match counter.  Highlights all matches in yellow and the
    current match in orange.
    """

    def __init__(self, text_view):
        self.text_view = text_view
        self.matches = []
        self.current = -1

        buf = text_view.get_buffer()
        self.tag_highlight = buf.create_tag(None, background="yellow")
        self.tag_current = buf.create_tag(None, background="orange")

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Search...")
        self.entry.set_hexpand(True)
        self.entry.set_width_chars(1)
        self.entry.connect("activate", lambda _e: self.search())

        search_btn = Gtk.Button()
        search_btn.set_image(
            Gtk.Image.new_from_icon_name("system-search", Gtk.IconSize.BUTTON)
        )
        search_btn.set_tooltip_text("Search")
        search_btn.connect("clicked", lambda _b: self.search())

        reset_btn = Gtk.Button()
        reset_btn.set_image(
            Gtk.Image.new_from_icon_name("edit-clear", Gtk.IconSize.BUTTON)
        )
        reset_btn.set_tooltip_text("Reset")
        reset_btn.connect("clicked", lambda _b: self.clear())

        prev_btn = Gtk.Button()
        prev_btn.set_image(
            Gtk.Image.new_from_icon_name("go-previous", Gtk.IconSize.BUTTON)
        )
        prev_btn.set_tooltip_text("Previous match")
        prev_btn.connect("clicked", lambda _b: self.navigate(-1))

        next_btn = Gtk.Button()
        next_btn.set_image(
            Gtk.Image.new_from_icon_name("go-next", Gtk.IconSize.BUTTON)
        )
        next_btn.set_tooltip_text("Next match")
        next_btn.connect("clicked", lambda _b: self.navigate(1))

        self.counter = Gtk.Label()
        self.counter.set_halign(Gtk.Align.START)
        self.counter.set_margin_end(10)

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self._box.set_margin_bottom(5)
        self._box.pack_start(self.entry, True, True, 0)
        self._box.pack_start(search_btn, False, False, 0)
        self._box.pack_start(reset_btn, False, False, 0)
        self._box.pack_start(prev_btn, False, False, 0)
        self._box.pack_start(next_btn, False, False, 0)
        self._box.pack_start(self.counter, False, False, 0)

    @property
    def widget(self):
        return self._box

    def search(self):
        """Find all occurrences of the search text and highlight them."""
        query = self.entry.get_text()
        if not query:
            self.clear()
            return

        buf = self.text_view.get_buffer()
        self.clear(keep_query=True)

        start = buf.get_start_iter()
        end = buf.get_end_iter()
        text = buf.get_text(start, end, True)

        matches = []
        for m in re.finditer(re.escape(query), text, re.IGNORECASE):
            match_start = buf.get_iter_at_offset(m.start())
            match_end = buf.get_iter_at_offset(m.end())
            buf.apply_tag(self.tag_highlight, match_start, match_end)
            matches.append((match_start.copy(), match_end.copy()))

        self.matches = matches
        if matches:
            self.current = 0
            buf.apply_tag(self.tag_current, matches[0][0], matches[0][1])
            self._scroll_to_current()
            self._update_counter()
        else:
            self.counter.set_text("0 matches")

    def clear(self, keep_query=False):
        """Remove all search highlights and reset match state."""
        buf = self.text_view.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        buf.remove_tag(self.tag_highlight, start, end)
        buf.remove_tag(self.tag_current, start, end)
        self.matches = []
        self.current = -1
        self.counter.set_text("")
        if not keep_query:
            self.entry.set_text("")

    def navigate(self, direction):
        """Move to the next or previous match."""
        if not self.matches:
            return
        buf = self.text_view.get_buffer()
        old_idx = self.current
        if 0 <= old_idx < len(self.matches):
            old_start, old_end = self.matches[old_idx]
            buf.remove_tag(self.tag_current, old_start, old_end)

        current = old_idx + direction
        if current < 0:
            current = len(self.matches) - 1
        elif current >= len(self.matches):
            current = 0
        self.current = current

        new_start, new_end = self.matches[current]
        buf.apply_tag(self.tag_current, new_start, new_end)
        self._scroll_to_current()
        self._update_counter()

    def _scroll_to_current(self):
        """Scroll the viewer so the current match is visible."""
        if not (0 <= self.current < len(self.matches)):
            return
        start_iter, _ = self.matches[self.current]
        mark = self.text_view.get_buffer().create_mark(None, start_iter, False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 0.3)
        self.text_view.get_buffer().delete_mark(mark)

    def _update_counter(self):
        """Update the match counter label (e.g. '3 / 12')."""
        total = len(self.matches)
        self.counter.set_text(
            "" if total == 0 else f"{self.current + 1} / {total}"
        )


class LogPopoutWindow(Gtk.Window):
    """Independent window that hosts a widget when popped out."""

    def __init__(self, app, title="ZFS Utilities — Log", toggle_widget=None):
        super().__init__(title=title)
        self.app = app
        self._toggle_widget = toggle_widget
        self.set_default_size(1000, 600)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.box)
        self.connect("delete-event", self._on_delete_event)

    def _on_delete_event(self, _widget, _event):
        """Reparent widget back and hide instead of destroy."""
        if self._toggle_widget and self._toggle_widget.get_active():
            self._toggle_widget.set_active(False)
        return True


def _on_popout_toggled(button, app, panel_box):
    """Toggle the info panel between main window and pop-out window."""
    if button.get_active():
        # Pop out
        app.vpaned.remove(panel_box)
        app.popout_window.box.pack_start(panel_box, True, True, 0)
        app.popout_window.show_all()
        # Restore saved geometry
        from backup_config import get_ui_state
        state = get_ui_state(app.config).get("log_window", {})
        if state.get("width") and state.get("height"):
            app.popout_window.resize(state["width"], state["height"])
        if state.get("x") is not None and state.get("y") is not None:
            app.popout_window.move(state["x"], state["y"])
        # Wire up geometry tracking
        if hasattr(app, '_ui_state') and app._ui_state is not None:
            app.popout_window.connect(
                "configure-event", app._ui_state.on_configure
            )
    else:
        # Pop back in
        app.popout_window.box.remove(panel_box)
        app.vpaned.pack2(panel_box, resize=True, shrink=False)
        app.popout_window.hide()
        # Restore vpaned position
        from backup_config import get_ui_state
        vpaned_pos = get_ui_state(app.config).get("main_window", {}).get(
            "vpaned_position"
        )
        if vpaned_pos:
            app.vpaned.set_position(vpaned_pos)


def _on_log_status_clicked(app):
    """Jump to the latest log message matching the current status level."""
    level = getattr(app, "_log_status_level", None)
    if not level:
        return False
    app.info_search.entry.set_text(f"{level}:")
    app.info_search.search()
    if app.info_search.matches:
        app.info_search.navigate(-1)
    return False


def create_info_panel(app):
    """Create the info panel at the bottom with stdin entry.

    Sets attributes on *app*: log_scrolled, info_text, progress_bar,
    status_label, stdin_entry, stdin_send_btn, log_level_button, and the
    pop-out log window.
    """
    panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    panel_box.set_size_request(-1, 150)
    app.vpaned.pack2(panel_box, resize=True, shrink=False)

    app.log_scrolled = Gtk.ScrolledWindow()
    app.log_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    app.log_scrolled.set_shadow_type(Gtk.ShadowType.IN)

    app.info_text = Gtk.TextView()
    app.info_text.set_editable(False)
    app.info_text.set_cursor_visible(False)
    app.info_text.set_wrap_mode(Gtk.WrapMode.CHAR)
    app.info_text.set_left_margin(5)
    app.info_text.set_right_margin(5)
    app.log_scrolled.add(app.info_text)

    app.info_search = TextViewSearch(app.info_text)
    panel_box.pack_start(app.info_search.widget, False, False, 0)
    panel_box.pack_start(app.log_scrolled, True, True, 0)

    app._log_auto_scroll = True
    app._log_programmatic_scroll = False
    app.info_text.connect("size-allocate", app._on_log_size_allocate)
    vadj = app.log_scrolled.get_vadjustment()
    vadj.connect("value-changed", app._on_log_scroll_changed)

    app.progress_bar = Gtk.ProgressBar()
    app.progress_bar.set_show_text(True)
    app.progress_bar.set_no_show_all(True)
    app.progress_bar.get_style_context().add_class("status-bar-label")
    # Progress bar is kept for backward compatibility with runners but not shown
    # in the UI per user request.

    app.status_label = Gtk.Label()
    app.status_label.set_halign(Gtk.Align.START)
    app.status_label.set_ellipsize(Pango.EllipsizeMode.END)
    app.status_label.set_no_show_all(True)
    app.status_label.get_style_context().add_class("status-bar-label")
    app.status_label.set_margin_start(5)
    app.status_label.set_margin_end(5)
    app.status_label.set_margin_top(2)
    app.status_label.set_margin_bottom(2)
    panel_box.pack_start(app.status_label, False, False, 0)

    stdin_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
    stdin_box.set_margin_start(5)
    stdin_box.set_margin_end(5)
    stdin_box.set_margin_top(2)
    stdin_box.set_margin_bottom(2)
    panel_box.pack_start(stdin_box, False, False, 0)

    stdin_label = Gtk.Label(label="Input:")
    stdin_box.pack_start(stdin_label, False, False, 0)

    app.stdin_entry = Gtk.Entry()
    app.stdin_entry.set_width_chars(1)
    app.stdin_entry.set_sensitive(False)
    app.stdin_entry.connect("activate", app._on_stdin_activate)
    stdin_box.pack_start(app.stdin_entry, True, True, 0)

    app.stdin_send_btn = Gtk.Button(label="Send")
    app.stdin_send_btn.set_sensitive(False)
    app.stdin_send_btn.connect("clicked", app._on_stdin_send)
    stdin_box.pack_start(app.stdin_send_btn, False, False, 0)

    app.log_status_label = Gtk.Label()
    app.log_status_label.set_no_show_all(True)

    app.log_status_event_box = Gtk.EventBox()
    app.log_status_event_box.add(app.log_status_label)
    app.log_status_event_box.set_tooltip_text(
        "Click to find the latest warning/error message"
    )
    app.log_status_event_box.connect(
        "button-press-event",
        lambda _widget, _event: _on_log_status_clicked(app),
    )
    app.log_status_event_box.set_no_show_all(True)
    stdin_box.pack_start(app.log_status_event_box, False, False, 0)

    app._info_panel_level = DEFAULT_MSG_LEVEL
    app._info_panel_lines = []
    app.log_level_button = Gtk.MenuButton(
        label=app._info_panel_level
    )
    app.log_level_button.set_tooltip_text("Filter messages shown in the log panel")
    log_menu = Gtk.Menu()
    log_group = []
    for level in MSG_LEVELS:
        item = Gtk.RadioMenuItem(label=level)
        if log_group:
            item.join_group(log_group[0])
        log_group.append(item)
        if level == app._info_panel_level:
            item.set_active(True)
        item.connect("toggled", app._on_log_level_toggled, level)
        log_menu.append(item)
    log_menu.show_all()
    app.log_level_button.set_popup(log_menu)
    stdin_box.pack_start(app.log_level_button, False, False, 0)

    clear_btn = Gtk.Button(label="Clear")
    clear_btn.connect(
        "clicked",
        lambda _b: (
            app.info_text.get_buffer().set_text(""),
            app._info_panel_lines.clear(),
            app.info_search.clear(),
            app.clear_log_status(),
            app._update_progress(None, ""),
        ),
    )
    stdin_box.pack_start(clear_btn, False, False, 0)

    # Pop-out toggle button
    app._popout_toggle = Gtk.ToggleButton()
    app._popout_toggle.set_image(
        Gtk.Image.new_from_icon_name("window-new", Gtk.IconSize.BUTTON)
    )
    app._popout_toggle.set_tooltip_text(
        "Pop out log panel into a separate window"
    )
    app._popout_toggle.connect("toggled", _on_popout_toggled, app, panel_box)
    stdin_box.pack_end(app._popout_toggle, False, False, 0)

    # Create pop-out window (hidden by default)
    app.popout_window = LogPopoutWindow(
        app, toggle_widget=app._popout_toggle
    )

    set_log_sink(app.log_message)

    log_msg("INFO: Welcome to ZFS Utilities")
    log_msg("INFO: Select a category from the sidebar to get started.")


class UIStateManager:
    """Debounced save/restore of window size, position, and paned divider."""

    def __init__(self, window, config):
        self.window = window
        self.config = config
        self._timer = None
        self._treeviews = {}

    def restore(self):
        """Restore window state from config."""
        from backup_config import get_ui_state
        state = get_ui_state(self.config)
        mw = state.get("main_window", {})

        if mw.get("maximized"):
            self.window.maximize()
        else:
            width = mw.get("width")
            height = mw.get("height")
            x = mw.get("x")
            y = mw.get("y")
            if width and height:
                self.window.resize(width, height)
            if x is not None and y is not None:
                self.window.move(x, y)

        vpaned_pos = mw.get("vpaned_position")
        if vpaned_pos:
            GLib.idle_add(self._apply_vpaned, vpaned_pos)

        # Defer pop-out restore until window is realized
        log_state = state.get("log_window", {})
        if log_state.get("popped_out"):
            self.window.connect(
                "realize",
                lambda _w: self.window._popout_toggle.set_active(True),
            )

    def _apply_vpaned(self, position):
        self.window.vpaned.set_position(position)
        return False

    def bind_treeview(self, treeview, state_key):
        """Register a TreeView for persistent column widths.

        Restore saved widths via GLib.idle_add after realization, scaling them
        down if they would force the window wider than the saved size.
        Connect notify::width on every resizable column to debounced save.
        """
        # Defer registration until after the idle restoration has run.  This
        # prevents window configure events that fire before the TreeView is
        # allocated from saving placeholder widths for hidden stack pages.
        # state is not cached yet; read directly from config
        from backup_config import get_ui_state
        ui_state = get_ui_state(self.config)
        saved = ui_state.get("treeview_columns", {}).get(state_key)
        saved_widths = list(saved) if saved else []

        def _apply():
            if saved_widths:
                widths = list(saved_widths)
                saved_width = ui_state.get("main_window", {}).get("width")
                if saved_width:
                    # Approximate non-treeview chrome: sidebar + action box +
                    # frames/margins.  The exact value is not critical; the goal
                    # is simply to keep restored columns from expanding the
                    # window beyond its saved width.
                    budget = saved_width - 300
                    if budget > 0:
                        total = sum(widths)
                        if total > budget:
                            scale = budget / total
                            widths = [max(20, int(w * scale)) for w in widths]

                columns = treeview.get_columns()
                widths = [
                    max(w, columns[i].get_min_width())
                    for i, w in enumerate(widths)
                    if i < len(columns) and columns[i].get_resizable()
                ]
                for i, width in enumerate(widths):
                    if i < len(columns):
                        col = columns[i]
                        col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                        col.set_fixed_width(width)

            # Connect notify::width handlers AFTER any restoration so that
            # initial layout notifications do not overwrite saved widths with
            # default/minimum values.
            for col in treeview.get_columns():
                if col.get_resizable():
                    col.connect("notify::width", lambda *_a: self._schedule_save())

            # Register only once restoration and handler wiring are complete.
            self._treeviews[state_key] = treeview
            return False

        GLib.idle_add(_apply)

        # Ensure the surrounding ScrolledWindow can shrink even when columns
        # are restored to wide fixed widths.
        _ensure_treeview_scrolling(treeview)

    def on_configure(self, _window, _event):
        self._schedule_save()
        return False

    def on_window_state_event(self, _window, _event):
        self._schedule_save()
        return False

    def on_vpaned_changed(self, _paned, _gparam):
        self._schedule_save()

    def _schedule_save(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._do_save)

    def _do_save(self):
        from backup_config import save_ui_state
        self._timer = None
        state = {"main_window": {}, "log_window": {}}
        mw = state["main_window"]
        mw["maximized"] = bool(
            self.window.get_window() and
            self.window.get_window().get_state() & Gdk.WindowState.MAXIMIZED
        )
        if not mw["maximized"]:
            width, height = self.window.get_size()
            x, y = self.window.get_position()
            mw["width"] = width
            mw["height"] = height
            mw["x"] = x
            mw["y"] = y
        vpaned_pos = self.window.vpaned.get_position()
        if vpaned_pos > 0:
            mw["vpaned_position"] = vpaned_pos

        lw = state["log_window"]
        popped = (
            self.window.popout_window is not None
            and self.window.popout_window.get_visible()
        )
        lw["popped_out"] = popped
        if popped and self.window.popout_window:
            pw = self.window.popout_window
            p_width, p_height = pw.get_size()
            p_x, p_y = pw.get_position()
            lw["width"] = p_width
            lw["height"] = p_height
            lw["x"] = p_x
            lw["y"] = p_y

        # Persist TreeView column widths.  Skip TreeViews that are not yet
        # realized or whose columns still have placeholder widths (this happens
        # for pages hidden in a Gtk.Stack when a save fires before they are
        # allocated).
        tvc = {}
        for key, tv in self._treeviews.items():
            if not tv.get_realized():
                continue
            widths = []
            valid = True
            for col in tv.get_columns():
                if not col.get_resizable():
                    continue
                width = col.get_width()
                if width < col.get_min_width():
                    valid = False
                    break
                widths.append(width)
            if valid and widths:
                tvc[key] = widths
        if tvc:
            state["treeview_columns"] = tvc

        save_ui_state(self.config, state)
        return False

    def flush(self):
        """Flush any pending save immediately."""
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._do_save()


def enable_treeview_copy(treeview, app=None, datasets_view=None):
    """Add right-click Copy menu to a TreeView.

    If *datasets_view* is provided and matches *treeview*, additional
    "Copy full name" items are offered for dataset/snapshot rows.
    """
    def _copy_cb(text):
        if app is not None:
            display = app.get_display()
        else:
            display = Gdk.Display.get_default()
        clipboard = Gtk.Clipboard.get_default(display)
        clipboard.set_text(text, -1)
        log_msg(f"INFO: Copied: {text}")

    def _on_button_press(tv, event):
        if event.button != 3:
            return False
        path_info = tv.get_path_at_pos(int(event.x), int(event.y))
        if path_info is None:
            return False
        path, column = path_info[0], path_info[1]
        tv.set_cursor(path, column, False)
        model = tv.get_model()
        tree_iter = model.get_iter(path)
        menu = Gtk.Menu()

        col_idx = tv.get_columns().index(column)
        cell_value = model.get_value(tree_iter, col_idx)
        item_cell = Gtk.MenuItem(label=f"Copy: {cell_value}")
        item_cell.connect("activate", lambda _w, t=cell_value: _copy_cb(t))
        menu.append(item_cell)

        if tv is datasets_view and isinstance(model, Gtk.TreeStore):
            ds_type = model.get_value(tree_iter, 2)
            if ds_type == "hold":
                parent_iter = model.iter_parent(tree_iter)
                if parent_iter:
                    full_name = build_full_dataset_name(model, parent_iter)
                    item_full = Gtk.MenuItem(label=f"Copy snapshot: {full_name}")
                    item_full.connect("activate", lambda _w, t=full_name: _copy_cb(t))
                    menu.append(item_full)
            else:
                full_name = build_full_dataset_name(model, tree_iter)
                if full_name != cell_value:
                    item_full = Gtk.MenuItem(label=f"Copy full name: {full_name}")
                    item_full.connect("activate", lambda _w, t=full_name: _copy_cb(t))
                    menu.append(item_full)

        n_cols = model.get_n_columns()
        if tv is datasets_view:
            n_cols = min(n_cols, 7)
        row_values = [model.get_value(tree_iter, i) for i in range(n_cols)]
        row_text = "\t".join(str(v) for v in row_values)
        item_row = Gtk.MenuItem(label="Copy row")
        item_row.connect("activate", lambda _w, t=row_text: _copy_cb(t))
        menu.append(item_row)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    treeview.connect("button-press-event", _on_button_press)


def enable_textview_copy(textview):
    """Add right-click Copy/Select All menu to a Gtk.TextView."""
    buf = textview.get_buffer()

    def _copy_cb(_widget):
        bounds = buf.get_selection_bounds()
        if bounds:
            start, end = bounds
            text = buf.get_text(start, end, False)
        else:
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        clipboard = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        clipboard.set_text(text, -1)

    def _select_all_cb(_widget):
        buf.select_range(buf.get_start_iter(), buf.get_end_iter())

    def _on_button_press(tv, event):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.connect("activate", _copy_cb)
        select_all_item = Gtk.MenuItem(label="Select All")
        select_all_item.connect("activate", _select_all_cb)
        menu.append(copy_item)
        menu.append(select_all_item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    textview.connect("button-press-event", _on_button_press)
