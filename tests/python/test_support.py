"""Shared mock infrastructure and helpers for ZFS Utilities Python tests."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure the Python source directory is on the path.
REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import backup_config
import config_core
import cron_manager
import feature_config
import file_locking


# ---------------------------------------------------------------------------
# Documentation helpers
# ---------------------------------------------------------------------------

DOCS_DIR = os.path.join(REPO_ROOT, "06 Docs", "docs")
MKDOCS_YML = os.path.join(REPO_ROOT, "06 Docs", "mkdocs.yml")
HELP_TOPICS_PATH = os.path.join(PYTHON_SRC, "help_topics.json")


def load_help_topics():
    """Load and return the help_topics.json dict."""
    with open(HELP_TOPICS_PATH) as f:
        return json.load(f)


def try_load_mkdocs_yml():
    """Parse mkdocs.yml and return the config dict, or None if pyyaml missing."""
    try:
        import yaml
        with open(MKDOCS_YML) as f:
            return yaml.safe_load(f)
    except ImportError:
        return None


def extract_markdown_links(filepath):
    """Extract all [text](url) links from a markdown file."""
    links = []
    with open(filepath) as f:
        for line in f:
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
                links.append(m.group(2))
    return links


def extract_markdown_headers(filepath):
    """Extract all header anchors from a markdown file."""
    headers = []
    with open(filepath) as f:
        for line in f:
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                text = m.group(2).strip()
                # Strip inline markdown links and formatting
                text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
                # Remove asterisks and backticks (not underscores)
                text = text.replace("*", "").replace("`", "")
                anchor = re.sub(r"[^\w\s-]", "", text).lower().strip()
                anchor = re.sub(r"[\s]+", "-", anchor)
                headers.append(anchor)
    return headers


def resolve_relative_link(source_dir, source_file, link):
    """Resolve a relative markdown link against its source file."""
    if "://" in link or link.startswith("/"):
        return None  # external or absolute
    base = link.split("#")[0]
    if not base:
        return source_file  # same-page anchor
    path = os.path.normpath(os.path.join(source_dir, base))
    return path


def collect_nav_files(nav, results=None):
    """Recursively collect all .md file paths from mkdocs nav structure."""
    if results is None:
        results = []
    if isinstance(nav, list):
        for item in nav:
            collect_nav_files(item, results)
    elif isinstance(nav, dict):
        for _key, val in nav.items():
            if isinstance(val, str) and val.endswith(".md"):
                results.append(val)
            else:
                collect_nav_files(val, results)
    return results


def list_all_md_files():
    """Return all .md files under DOCS_DIR, relative to DOCS_DIR."""
    md_files = []
    for root, _dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), DOCS_DIR)
                md_files.append(rel)
    return md_files


def extract_python_module_names(filepath):
    """Extract module file names documented as ### `module.py` headers."""
    modules = []
    with open(filepath) as f:
        for line in f:
            m = re.match(r"^###\s+`([a-zA-Z0-9_]+\.py)`\s*$", line)
            if m:
                modules.append(m.group(1))
    return modules


def check_pyyaml():
    """Return True if pyyaml is installed, else raise SkipTest with install instructions."""
    try:
        import yaml  # noqa: F401
        return True
    except ImportError:
        raise unittest.SkipTest(
            "pyyaml is required for documentation integrity tests. "
            "Install it with: python3 -m pip install pyyaml"
        )


def strip_html_tags(text):
    """Remove simple HTML tags from text for validation."""
    return re.sub(r"<[^>]+>", "", text)


def has_unclosed_html_tags(text):
    """Check for common unclosed tags (b, i, tt, span, br). Returns True if any found."""
    for tag in ("b", "i", "tt", "span"):
        open_count = len(re.findall(rf"<{tag}(?:\s+[^>]*)?>", text, re.IGNORECASE))
        close_count = len(re.findall(rf"</{tag}>", text, re.IGNORECASE))
        if open_count != close_count:
            return True
    return False


# ---------------------------------------------------------------------------
# startdocserver bash helpers
# ---------------------------------------------------------------------------

STARTDOCSERVER_PATH = os.path.join(REPO_ROOT, "startdocserver")


# ---------------------------------------------------------------------------
# startdocserver bash helpers
# ---------------------------------------------------------------------------

STARTDOCSERVER_PATH = os.path.join(REPO_ROOT, "startdocserver")


# ---------------------------------------------------------------------------
# Config isolation
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def temp_config_dir():
    """Override config and cron file paths to a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_config_path = backup_config.CONFIG_PATH
        orig_core_config_path = config_core.CONFIG_PATH
        orig_cron_file = cron_manager.CRON_FILE
        orig_snapfile = backup_config.SNAPFILE
        orig_core_snapfile = feature_config.SNAPFILE
        orig_offsite_snapfile = backup_config.OFFSITE_SNAPFILE
        orig_core_offsite_snapfile = feature_config.OFFSITE_SNAPFILE
        orig_snapname_lock = backup_config.SNAPNAME_LOCK
        orig_core_snapname_lock = feature_config.SNAPNAME_LOCK
        orig_snapname_reserved = backup_config.SNAPNAME_RESERVED
        orig_core_snapname_reserved = feature_config.SNAPNAME_RESERVED
        orig_config_lock = file_locking.CONFIG_LOCK_PATH
        orig_history_lock = file_locking.HISTORY_LOCK_PATH
        orig_log_index_lock = file_locking.LOG_INDEX_LOCK_PATH
        orig_scrub_state_lock = file_locking.SCRUB_STATE_LOCK_PATH
        import profile_runner
        orig_profile_lock_dir = profile_runner.PROFILE_LOCK_DIR
        profiles_dir = os.path.join(tmpdir, "profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        config_path = os.path.join(tmpdir, "zfsutilities.json")
        backup_config.CONFIG_PATH = config_path
        config_core.CONFIG_PATH = config_path
        cron_manager.CRON_FILE = os.path.join(tmpdir, "zfsutilities.cron")
        snapfile = os.path.join(tmpdir, "zfsnextsnap")
        offsite_snapfile = os.path.join(tmpdir, "zfsnextsnap_offsite")
        snapname_lock = os.path.join(tmpdir, "snapname.lock")
        snapname_reserved = os.path.join(tmpdir, "snapname.reserved")
        backup_config.SNAPFILE = snapfile
        feature_config.SNAPFILE = snapfile
        backup_config.OFFSITE_SNAPFILE = offsite_snapfile
        feature_config.OFFSITE_SNAPFILE = offsite_snapfile
        backup_config.SNAPNAME_LOCK = snapname_lock
        feature_config.SNAPNAME_LOCK = snapname_lock
        backup_config.SNAPNAME_RESERVED = snapname_reserved
        feature_config.SNAPNAME_RESERVED = snapname_reserved
        file_locking.CONFIG_LOCK_PATH = os.path.join(tmpdir, ".config.lock")
        file_locking.HISTORY_LOCK_PATH = os.path.join(tmpdir, ".history.lock")
        file_locking.LOG_INDEX_LOCK_PATH = os.path.join(tmpdir, ".log_index.lock")
        file_locking.SCRUB_STATE_LOCK_PATH = os.path.join(tmpdir, ".scrub_state.lock")
        profile_runner.PROFILE_LOCK_DIR = os.path.join(tmpdir, "profiles", "locks")
        try:
            yield tmpdir
        finally:
            backup_config.CONFIG_PATH = orig_config_path
            config_core.CONFIG_PATH = orig_core_config_path
            cron_manager.CRON_FILE = orig_cron_file
            backup_config.SNAPFILE = orig_snapfile
            feature_config.SNAPFILE = orig_core_snapfile
            backup_config.OFFSITE_SNAPFILE = orig_offsite_snapfile
            feature_config.OFFSITE_SNAPFILE = orig_core_offsite_snapfile
            backup_config.SNAPNAME_LOCK = orig_snapname_lock
            feature_config.SNAPNAME_LOCK = orig_core_snapname_lock
            backup_config.SNAPNAME_RESERVED = orig_snapname_reserved
            feature_config.SNAPNAME_RESERVED = orig_core_snapname_reserved
            file_locking.CONFIG_LOCK_PATH = orig_config_lock
            file_locking.HISTORY_LOCK_PATH = orig_history_lock
            file_locking.LOG_INDEX_LOCK_PATH = orig_log_index_lock
            file_locking.SCRUB_STATE_LOCK_PATH = orig_scrub_state_lock
            profile_runner.PROFILE_LOCK_DIR = orig_profile_lock_dir


@contextlib.contextmanager
def temp_lock_dir():
    """Route zfs_lock_manager lock files to a temporary directory."""
    import zfs_lock_manager
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = zfs_lock_manager.ZFSLOCK_DIR
        orig_locks = zfs_lock_manager.ZFSLOCK_LOCKS_DIR
        orig_pids = zfs_lock_manager.ZFSLOCK_PIDS_DIR
        zfs_lock_manager.ZFSLOCK_DIR = tmpdir
        zfs_lock_manager.ZFSLOCK_LOCKS_DIR = os.path.join(tmpdir, ".locks")
        zfs_lock_manager.ZFSLOCK_PIDS_DIR = os.path.join(tmpdir, ".pids")
        try:
            yield tmpdir
        finally:
            zfs_lock_manager.ZFSLOCK_DIR = orig_dir
            zfs_lock_manager.ZFSLOCK_LOCKS_DIR = orig_locks
            zfs_lock_manager.ZFSLOCK_PIDS_DIR = orig_pids


def write_config(data):
    """Write a config dict to the current CONFIG_PATH."""
    with open(backup_config.CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def read_config():
    """Read the config dict from the current CONFIG_PATH."""
    with open(backup_config.CONFIG_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Environment patching
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def patch_environ(**kwargs):
    """Temporarily set environment variables."""
    orig = {k: os.environ.get(k) for k in kwargs}
    for k, v in kwargs.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# Subprocess mocking
# ---------------------------------------------------------------------------

class MockSubprocess:
    """State container for mocked subprocess.run calls."""

    def __init__(self):
        self.calls = []
        self._zpool_list = []
        self._zfs_fs_list = []
        self._zfs_snap_list = {}
        self._zfs_props = {}
        self._command_handlers = {}

    def add_zpool_list(self, pools):
        """Set pools for 'zpool list -H -o name,health,size,alloc,free,cap'."""
        self._zpool_list = pools

    def add_zfs_list(self, datasets):
        """Set datasets for 'zfs list -H -o ...'."""
        self._zfs_fs_list = datasets

    def add_zfs_snaps(self, dataset, lines):
        """Set snapshot lines for 'zfs list -t snapshot -r <dataset>'."""
        self._zfs_snap_list[dataset] = lines

    def add_zfs_prop(self, dataset, prop, value):
        self._zfs_props[f"{dataset}:{prop}"] = value

    def set_command_handler(self, cmd_pattern, handler):
        """Register a handler for commands matching a regex pattern."""
        self._command_handlers[cmd_pattern] = handler

    def run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if isinstance(cmd, str):
            cmd_str = cmd
            cmd_parts = cmd.split()
        else:
            cmd_str = " ".join(str(c) for c in cmd)
            cmd_parts = list(cmd)

        # Custom handlers first
        for pattern, handler in self._command_handlers.items():
            if re.search(pattern, cmd_str):
                return handler(cmd, **kwargs)

        # zpool list
        if cmd_parts and cmd_parts[0] == "zpool" and "list" in cmd_str:
            stdout = "\n".join(
                "\t".join([
                    p['name'],
                    p.get('health', 'ONLINE'),
                    p.get('size', '1T'),
                    p.get('alloc', '100G'),
                    p.get('free', '900G'),
                    p.get('cap', '10%'),
                ])
                for p in self._zpool_list
            )
            return self._completed(stdout)

        # zfs list
        if cmd_parts and cmd_parts[0] == "zfs" and "list" in cmd_str:
            # Snapshot listing
            if "-t" in cmd_parts and "snapshot" in cmd_str:
                dataset = cmd_parts[-1] if cmd_parts[-1] != "snapshot" else None
                if dataset and dataset in self._zfs_snap_list:
                    return self._completed("\n".join(self._zfs_snap_list[dataset]))
                return self._completed("")
            # Dataset listing
            stdout = "\n".join(
                f"{d['name']}\t{d.get('used', '10G')}\t{d.get('avail', '100G')}\t{d.get('refer', '5G')}\t{d.get('mountpoint', '/')}"
                for d in self._zfs_fs_list
            )
            return self._completed(stdout)

        # zfs get
        if cmd_parts and cmd_parts[0] == "zfs" and "get" in cmd_str:
            key = f"{cmd_parts[-1]}:{cmd_parts[-2]}"
            value = self._zfs_props.get(key, "-")
            return self._completed(f"{cmd_parts[-1]}\t{cmd_parts[-2]}\t{value}")

        # Default: success with empty output
        return self._completed("")

    @staticmethod
    def _completed(stdout, stderr="", rc=0):
        import subprocess
        return subprocess.CompletedProcess(
            args=[], returncode=rc, stdout=stdout, stderr=stderr
        )

    def popen(self, cmd, **kwargs):
        """Popen-compatible entry point used by streaming runners."""
        completed = self.run(cmd, **kwargs)
        return _MockPopen(completed)


class _MockPopen:
    """Minimal Popen stand-in returned by MockSubprocess.popen()."""

    def __init__(self, completed):
        self._completed = completed
        self.stdout = io.StringIO(completed.stdout or "")
        self.returncode = None

    def wait(self):
        self.returncode = self._completed.returncode
        return self.returncode


@contextlib.contextmanager
def mock_subprocess():
    """Patch subprocess.run and subprocess.Popen with a MockSubprocess instance."""
    m = MockSubprocess()
    with patch("subprocess.run", side_effect=m.run), patch(
        "subprocess.Popen", side_effect=m.popen
    ):
        yield m


# ---------------------------------------------------------------------------
# Log capture
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def capture_logs():
    """Capture all log_msg output to a list of strings."""
    logs = []
    orig_sink = backup_config.get_log_sink()

    def _sink(msg):
        logs.append(msg)

    backup_config.set_log_sink(_sink)
    try:
        yield logs
    finally:
        backup_config.set_log_sink(orig_sink)


@contextlib.contextmanager
def capture_stderr():
    """Capture stderr output to a string."""
    old = sys.stderr
    buf = io.StringIO()
    sys.stderr = buf
    try:
        yield buf
    finally:
        sys.stderr = old


# ---------------------------------------------------------------------------
# GTK mocking
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def mock_gtk():
    """Patch gi.repository so GUI modules can be imported without a display."""
    gi_mock = MagicMock()
    gtk_mock = MagicMock()
    pango_mock = MagicMock()
    gdk_mock = MagicMock()
    gobject_mock = MagicMock()

    gi_mock.require_version = MagicMock()

    # FakeWindow allows subclasses to set real attributes on self
    class FakeWindow:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            return MagicMock()
    gtk_mock.Window = FakeWindow
    gtk_mock.Box = MagicMock()
    gtk_mock.Label = MagicMock()
    gtk_mock.Entry = MagicMock()
    gtk_mock.Button = MagicMock()
    gtk_mock.TreeView = MagicMock()
    gtk_mock.TreeStore = MagicMock()
    gtk_mock.ScrolledWindow = MagicMock()
    gtk_mock.MessageDialog = MagicMock()
    gtk_mock.Menu = MagicMock()
    gtk_mock.MenuItem = MagicMock()
    gtk_mock.Clipboard = MagicMock()
    gtk_mock.Image = MagicMock()
    gtk_mock.STOCK_CANCEL = "gtk-cancel"
    gtk_mock.STOCK_OK = "gtk-ok"
    gtk_mock.ResponseType = MagicMock()
    gtk_mock.ResponseType.CANCEL = 0
    gtk_mock.ResponseType.OK = 1
    gtk_mock.ResponseType.YES = 2
    gtk_mock.ResponseType.NO = 3
    gtk_mock.SelectionMode = MagicMock()
    gtk_mock.SelectionMode.SINGLE = 0
    gtk_mock.SelectionMode.MULTIPLE = 1
    gtk_mock.MessageType = MagicMock()
    gtk_mock.MessageType.WARNING = 1
    gtk_mock.ButtonsType = MagicMock()
    gtk_mock.ButtonsType.YES_NO = 1
    gtk_mock.Orientation = MagicMock()
    gtk_mock.Orientation.HORIZONTAL = 1
    gtk_mock.Orientation.VERTICAL = 2
    gtk_mock.Align = MagicMock()
    gtk_mock.Align.START = 1
    gtk_mock.PolicyType = MagicMock()
    gtk_mock.PolicyType.AUTOMATIC = 1
    gtk_mock.IconSize = MagicMock()
    gtk_mock.IconSize.BUTTON = 1
    gtk_mock.TreeViewGridLines = MagicMock()
    gtk_mock.TreeViewGridLines.HORIZONTAL = 1
    gtk_mock.Pango = pango_mock
    gtk_mock.Pango.Weight = MagicMock()
    gtk_mock.Pango.Weight.NORMAL = 400
    gtk_mock.Pango.Style = MagicMock()
    gtk_mock.Pango.Style.NORMAL = 0
    gtk_mock.Pango.Style.ITALIC = 2

    # WebKit2 mock
    webkit_mock = MagicMock()
    webkit_mock.WebView = MagicMock()
    webkit_mock.WebView.new_with_user_content_manager = MagicMock()
    webkit_mock.WebView.return_value.get_settings.return_value = MagicMock()
    webkit_mock.PolicyDecisionType = MagicMock()
    webkit_mock.PolicyDecisionType.NAVIGATION_ACTION = 0
    webkit_mock.PolicyDecisionType.NEW_WINDOW_ACTION = 1
    webkit_mock.PolicyDecisionType.RESPONSE = 2
    webkit_mock.LoadEvent = MagicMock()
    webkit_mock.LoadEvent.STARTED = 0
    webkit_mock.LoadEvent.COMMITTED = 1
    webkit_mock.LoadEvent.FINISHED = 2
    webkit_mock.LoadEvent.REDIRECTED = 3
    webkit_mock.UserContentManager = MagicMock()
    webkit_mock.UserStyleSheet = MagicMock()
    webkit_mock.UserStyleSheet.new = MagicMock()
    webkit_mock.UserScript = MagicMock()
    webkit_mock.UserScript.new = MagicMock()
    webkit_mock.UserContentInjectedFrames = MagicMock()
    webkit_mock.UserContentInjectedFrames.ALL_FRAMES = 0
    webkit_mock.UserStyleLevel = MagicMock()
    webkit_mock.UserStyleLevel.USER = 0
    webkit_mock.UserScriptInjectionTime = MagicMock()
    webkit_mock.UserScriptInjectionTime.START = 0
    webkit_mock.UserScriptInjectionTime.END = 1

    modules = {
        "gi": gi_mock,
        "gi.repository": gi_mock.repository,
        "gi.repository.Gtk": gtk_mock,
        "gi.repository.Pango": pango_mock,
        "gi.repository.Gdk": gdk_mock,
        "gi.repository.GObject": gobject_mock,
        "gi.repository.WebKit2": webkit_mock,
    }

    # Build the nested module structure
    gi_mock.repository.Gtk = gtk_mock
    gi_mock.repository.Pango = pango_mock
    gi_mock.repository.Gdk = gdk_mock
    gi_mock.repository.GObject = gobject_mock
    gi_mock.repository.WebKit2 = webkit_mock

    orig_modules = dict(sys.modules)
    for name, mod in modules.items():
        sys.modules[name] = mod

    try:
        yield gtk_mock
    finally:
        # Restore only the modules we replaced
        for name in modules:
            if name in orig_modules:
                sys.modules[name] = orig_modules[name]
            else:
                sys.modules.pop(name, None)
