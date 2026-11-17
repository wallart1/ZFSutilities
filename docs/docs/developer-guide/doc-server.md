# Documentation Server

The documentation is built with [MkDocs](https://www.mkdocs.org/) using the
[Material theme](https://squidfunk.github.io/mkdocs-material/).

## Viewing the Documentation

The documentation can be viewed in three ways:

1. **Embedded viewer in the GTK GUI** — choose **Help → Documentation**. This
   opens the built-in WebKit viewer and displays the pre-built site in
   `docs/site/`. The static site is refreshed each time `startdocserver`
   starts or restarts the server; it is not rebuilt while the server keeps
   running.
2. **Standalone documentation viewer** — open the **ZFSutilities Documentation**
   symlink in the installing user's home directory, or run `zfsutilities-docs`.
   This is the same viewer as the embedded one and also displays the pre-built
   `docs/site/` content, refreshed at the same times.
3. **Web browser via `startdocserver`** — run `startdocserver`, then open
   `http://<host>:8000` in a web browser. This is the only option that provides
   MkDocs live reload: edits saved in `docs/docs/` are rebuilt and the browser
   page refreshes automatically.

!!! note "Viewers follow the launch layout"
    Both viewers serve the built site belonging to the code that is running:
    a GUI or viewer launched from a repository checkout reads the
    repository's `docs/site/`, and one launched from a deployment reads
    `/usr/local/lib/zfsutilities/current/docs/site/`. A repository launch
    never falls back to the deployed site — when the repository's
    `docs/site/` has not been built, the viewer shows the `mkdocs build`
    instructions instead of deployment content. The site location is chosen
    once when the viewer window opens, so a viewer that is already open
    keeps serving the tree it started with until it is reopened.

!!! tip "Live updates while editing"
    If you are actively editing documentation, use `startdocserver` and a web
    browser. The embedded and standalone viewers show the static build in
    `docs/site/`, which `startdocserver` rebuilds whenever it starts or
    restarts the server (`startdocserver --restart` forces a refresh). While
    the server keeps running, they only update after the next `mkdocs build`
    or `deploy-version` run.

!!! tip "You are not required to use the docserver"
    The server does not need to be running during normal operations. And, it
    is not needed to edit the files in `docs/docs/`. The net benefit is that
    it provides a *dynamically-updated* view (via a web browser) of the 
    documentation while you are editing the `docs/docs/` files.

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
  the old process and restarts from the current directory.
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

Before the server starts, the script rebuilds the static site in `docs/site/`
with `mkdocs build --clean` so the embedded and standalone viewers show
current content; build output is logged to `~/docserver-build.log`.  A failed
static build logs a WARN and does not prevent the live server from starting.

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

Output goes to `docs/site/`, which is not in the distribution.

### Clean builds

`mkdocs build` does **not** remove stale files from `site/` by default. If you
want to guarantee a completely clean build, delete the `site/` directory first
or use the `--clean` flag:

```bash
cd "<project_directory>/docs" && python3 -m mkdocs build --clean
```

