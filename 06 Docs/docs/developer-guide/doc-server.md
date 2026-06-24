# Documentation Server

The documentation is built with [MkDocs](https://www.mkdocs.org/) using the
[Material theme](https://squidfunk.github.io/mkdocs-material/).

## Automatic Installation

Both installers — `10 Installers/install-single-node` and
`10 Installers/install-two-node` — install MkDocs and the Material theme as
one of their first steps. After the installer runs, start the server
manually:

```bash
startdocserver
```

The docs will then be available at:

```
http://<host>:8000
```

!!! note "MkDocs is only required for editing documentation"
    The pre-built static site in `06 Docs/site/` can be served without MkDocs.
    `startdocserver` automatically falls back to Python's built-in
    `http.server` when MkDocs is not installed. You only need MkDocs if you
    intend to edit the `.md` source files and rebuild the site.

## Configuration

`mkdocs.yml` lives in `06 Docs/` (not the project root). The content is in
`06 Docs/docs/`. MkDocs requires the `docs_dir` to be a child of the config
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
  newly activated version. It detects both `mkdocs serve` and
  `python3 -m http.server` fallback processes.
- **[deploy-version](../commands-and-modules/two-node.md#deploy-version-repo-root)** rebuilds the static `site/` directory in the deployed
  version (if MkDocs is available) so the fallback also carries the correct
  version stamp.

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
    deployed version, run `./startdocserver` from the project root instead.
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

If MkDocs is installed, the server runs in live-reload mode and auto-rebuilds
on source changes; the browser page is refreshed automatically via a
livereload WebSocket. If MkDocs is missing, the script serves the pre-built
`site/` directory instead. In fallback mode, edits to `.md` files do **not**
appear until the static site is rebuilt with `mkdocs build` and the server is
restarted (use `startdocserver --restart`).

### Direct MkDocs commands (advanced)

!!! note "For CI and troubleshooting only"
    These commands are for continuous-integration pipelines or special cases.
    For day-to-day editing, use `./startdocserver` instead.

To start the server directly without the helper script:

```bash
cd "<project_directory>/06 Docs" && python3 -m mkdocs serve -a 0.0.0.0:8000
```

To build a static site:

```bash
cd "<project_directory>/06 Docs" && python3 -m mkdocs build
```

Output goes to `06 Docs/site/` (not distributed).

### Clean builds

`mkdocs build` does **not** remove stale files from `site/` by default. If you
want to guarantee a completely clean build, delete the `site/` directory first
or use the `--clean` flag:

```bash
cd "<project_directory>/06 Docs" && python3 -m mkdocs build --clean
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

A MkDocs hook (`06 Docs/hooks/edit_links.py`) sets `page.edit_url` for each
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
