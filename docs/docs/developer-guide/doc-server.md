# Documentation Server

The documentation is built with [MkDocs](https://www.mkdocs.org/) using the
[Material theme](https://squidfunk.github.io/mkdocs-material/).

## Viewing the Documentation

The documentation can be viewed in three ways:

1. **Embedded viewer in the GTK GUI** — choose **Help → Documentation**. This
   opens the built-in WebKit viewer and displays the pre-built site in
   `docs/site/`. It does **not** automatically refresh when Markdown source
   files change.
2. **Standalone documentation viewer** — open the **ZFSutilities Documentation**
   symlink in the installing user's home directory, or run `zfsutilities-docs`.
   This is the same viewer as the embedded one and also displays the pre-built
   `docs/site/` content without auto-refresh.
3. **Web browser via `startdocserver`** — run `startdocserver`, then open
   `http://<host>:8000` in a web browser. This is the only option that provides
   MkDocs live reload: edits saved in `docs/docs/` are rebuilt and the browser
   page refreshes automatically.

!!! tip "Live updates while editing"
    If you are actively editing documentation, use `startdocserver` and a web
    browser. The embedded and standalone viewers show the most recent static
    build and only update after the next `mkdocs build` or the next
    `deploy-version` run.

## Automatic Installation

Both installers — `bin/install-single-node` and
`bin/install-two-node` — install MkDocs and the Material theme as
one of their first steps. MkDocs is pinned to `mkdocs<2` because
MkDocs 2.x is incompatible with this project. After the installer runs,
start the server manually:

```bash
startdocserver
```

The docs will then be available at:

```
http://<host>:8000
```

## Configuration

`mkdocs.yml` lives in `docs/` (not the project root). The content is in
`docs/docs/`. MkDocs requires the `docs_dir` to be a child of the config
file's directory — it cannot be the same directory.

## Version Tracking

The documentation footer displays the version of the ZFS Utilities deployment
that the current docs originate from. This is handled automatically:

- **`startdocserver`** checks whether an existing server on port 8000 is
  serving from the correct directory. If a stale server is running (e.g.
  started from an old repo checkout or a previous deployed version), it stops
  the old process and restarts from the current directory. PID discovery falls
  back through `lsof`, `fuser`, `pgrep -f 'mkdocs serve'`, and
  `pgrep -f 'http.server 8000'`.
- **[switch-version](../commands-and-modules/two-node.md#switch-version-any-host)** stops any running documentation server after switching
  versions. The next invocation of `startdocserver` will start fresh from the
  newly activated version. It detects `mkdocs serve` processes.
- **[deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root)** rebuilds the static `site/` directory in the deployed
  version so it carries the correct version stamp.

## Running the Server Manually

!!! tip "One-step solution"
    The `startdocserver` script is the recommended way to edit documentation.
    It handles watching, auto-rebuilding, and serving in a single command:

    ```bash
    startdocserver
    ```

    You do **not** need to run `mkdocs build` manually while the server is
    running in MkDocs mode.

!!! note "Running from a repo checkout"
    If you are working directly from a repository checkout rather than a
    deployed version, run `./bin/startdocserver` from the project root instead.
    An optional path argument is accepted for compatibility but ignored.

!!! tip "Force a fresh start"
    If the browser still shows stale content after editing, stop and restart
    the server explicitly:

    ```bash
    startdocserver --restart
    ```

    This is useful when switching between repo checkouts or when a browser or
    server cache is holding onto old content.

The `startdocserver` script starts the documentation server in the background
(listening on `0.0.0.0:8000`).  If the server is already running, the script
verifies that it is serving from the expected directory; if not, it stops the
stale server and restarts from the correct directory.  Server output is logged
to `~/docserver.log`.

The server runs in MkDocs live-reload mode and auto-rebuilds on source
changes; the browser page is refreshed automatically via a livereload
WebSocket. MkDocs is required; if it is not installed, `startdocserver` exits
with an error.

### Direct MkDocs commands (advanced)

!!! note "For CI and troubleshooting only"
    These commands are for continuous-integration pipelines or special cases.
    For day-to-day editing, use `./startdocserver` instead.

To start the server directly without the helper script:

```bash
cd "<project_directory>/docs" && python3 -m mkdocs serve -a 0.0.0.0:8000
```

To build a static site:

```bash
cd "<project_directory>/docs" && python3 -m mkdocs build
```

Output goes to `docs/site/` (not distributed).

### Clean builds

`mkdocs build` does **not** remove stale files from `site/` by default. If you
want to guarantee a completely clean build, delete the `site/` directory first
or use the `--clean` flag:

```bash
cd "<project_directory>/docs" && python3 -m mkdocs build --clean
```

## Edit-in-MarkText Integration

Each page has a pencil icon (top-right). Clicking it opens the source `.md`
file directly in MarkText via a custom `openmd://` URI scheme.

MarkText is an AppImage installed at `/home/dan/MarkText/marktext`. Use the
actively maintained fork at <https://github.com/Tkaixiang/marktext>.

### Setup

**Handler script** at `~/bin/openmd-handler`:

```bash
#!/bin/bash
path="${1#openmd://}"
path=$(python3 -c "import urllib.parse,sys; print(urllib.parse.unquote(sys.argv[1]))" "$path")
exec /home/dan/MarkText/marktext "$path"
```

**Desktop entry** at `~/.local/share/applications/openmd.desktop`:

```ini
[Desktop Entry]
Version=1.0
Name=Open Markdown File
Exec=/home/dan/bin/openmd-handler %u
Type=Application
StartupNotify=false
MimeType=x-scheme-handler/openmd;
NoDisplay=true
```

**Register the scheme:**

```bash
chmod +x ~/bin/openmd-handler
update-desktop-database ~/.local/share/applications/
xdg-mime default openmd.desktop x-scheme-handler/openmd
```

**Firefox:** on first click, choose **Always allow** when prompted about
`openmd` links.

### How the URL is constructed

A MkDocs hook (`docs/hooks/edit_links.py`) sets `page.edit_url` for each
page:

```python
file_path = os.path.join(docs_dir, page.file.src_path)
page.edit_url = f"openmd://{urllib.parse.quote(file_path, safe='/:@()')}"
```

The handler strips `openmd://`, URL-decodes the path, and passes the
filesystem path to MarkText.

MkDocs validates `repo_url` and only accepts `http://` or `https://`, so the
hook sets `page.edit_url` directly to bypass this.

!!! note "Embedded viewer also uses `openmd://`"
    The GTK GUI's embedded documentation viewer intercepts `openmd://` links
    internally. Clicking the pencil icon launches the configured editor directly
    without relying on a desktop URI handler. See
    [GTK GUI Reference → Help Menu](../user-guide/gtk-gui.md#help-menu).
