#!/usr/bin/env python3
"""sample.py — randomized selection engine for the j22 function survey.

Enumerates the end-user-visible function universe (CLI manifest + the GUI
layers of the tree under test), draws a seeded random sample of at least
half of it in a random order, assigns each item a response profile
(accept / decline / cancel / invalid) so prompt-bearing surfaces exercise
different scenarios, and writes the archive that makes the run
repeatable:  replay mode re-reads the archive and reproduces the exact
list, order, and profiles.

The universe is enumerated from the exact tree under test — the working
tree, or an extracted release tarball — so a survey of an older release
samples that release's real surface.

Stdlib-only (mirrors tests/integrated/e2e), except the optional GUI
enumeration which imports the tree's action_dispatch (needs gi; skipped
only with --no-gui for unit tests).

Usage (see --help): modes `new` and `replay`; the journey drives this.
Exit codes: 0 ok, 2 usage/premise failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

SURVEY_DIR = os.path.dirname(os.path.abspath(__file__))

PROFILES = ("accept", "decline", "cancel", "invalid")
DEFAULT_FRACTION = 0.5
RELEASE_WINDOW = 5  # the five most recent published releases

# ---------------------------------------------------------------------------
# CLI universe manifest
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """The universe manifest is inconsistent with the repo it describes."""


def parse_universe_tsv(path):
    """Parse universe.tsv into (rows, headers).  Comment/# lines skipped."""
    rows = []
    headers = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            fields = line.split("\t")
            if headers is None:
                headers = fields
                continue
            rows.append(dict(zip(headers, fields)))
    if headers is None or not rows:
        raise ManifestError(f"no data rows parsed from {path}")
    return rows, headers


def cli_universe(repo_root):
    """CLI universe items from the manifest, validated against bin/."""
    rows, _ = parse_universe_tsv(os.path.join(SURVEY_DIR, "universe.tsv"))
    items = []
    for row in rows:
        cmd = row["command"]
        if not os.access(os.path.join(repo_root, "bin", cmd), os.X_OK):
            raise ManifestError(f"manifest command missing from bin/: {cmd}")
        item = {
            "id": row["id"],
            "kind": "cli",
            "name": cmd,
            "lab": row["lab"],
            "node": row["node"],
            "depth": row["depth"],
        }
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# GUI universe (L1 buttons from ACTION_HANDLERS; L2/L3 from gui_catalog)
# ---------------------------------------------------------------------------


def gui_button_universe(repo_root):
    """L1: one item per ACTION_HANDLERS (page, button) pair.

    Imports the tree's action_dispatch with GUI logging fenced into a
    scratch dir (the realized-check rule: never touch operator state).
    """
    scratch = tempfile.mkdtemp(prefix="survey-enum-")
    os.environ.setdefault("ZFSUTILITIES_LOG_DIR", scratch)
    python_dir = os.path.join(repo_root, "python")
    sys.path.insert(0, python_dir)
    try:
        import action_dispatch
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ManifestError(f"cannot import action_dispatch from {python_dir}: {exc}") from exc
    items = []
    for page in sorted(action_dispatch.ACTION_HANDLERS):
        for button in sorted(action_dispatch.ACTION_HANDLERS[page]):
            items.append(
                {
                    "id": f"gui-b-{page}-{button}",
                    "kind": "gui-button",
                    "name": button,
                    "page": page,
                }
            )
    return items


def gui_catalog_universe(repo_root):
    """L2 widget interactions + L3 composites from gui_catalog (pure data)."""
    sys.path.insert(0, SURVEY_DIR)
    import gui_catalog

    items = []
    for page, interactions in sorted(gui_catalog.L2_INTERACTIONS.items()):
        for inter in interactions:
            items.append(
                {
                    "id": f"gui-w-{page}-{inter['suffix']}",
                    "kind": "gui-widget",
                    "name": inter["label"],
                    "page": page,
                    "role": inter["role"],
                }
            )
    for comp in gui_catalog.L3_COMPOSITES:
        items.append(
            {
                "id": f"gui-c-{comp['id']}",
                "kind": "gui-composite",
                "name": comp["label"],
                "page": comp["page"],
            }
        )
    del repo_root  # catalog is tree-relative data; kept for signature parity
    return items


def enumerate_universe(repo_root, with_gui=True):
    """The full sampling universe, deterministically ordered by id."""
    items = cli_universe(repo_root)
    if with_gui:
        items += gui_button_universe(repo_root)
        items += gui_catalog_universe(repo_root)
    items.sort(key=lambda it: it["id"])
    seen = set()
    for it in items:
        if it["id"] in seen:
            raise ManifestError(f"duplicate universe id: {it['id']}")
        seen.add(it["id"])
    return items


def universe_digest(items):
    """Stable digest over ids+kinds — replay drift detection."""
    payload = "\n".join(f"{it['id']}\t{it['kind']}" for it in items)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Software-under-test resolution (working tree or one of the five newest)
# ---------------------------------------------------------------------------


def github_releases(repo, url=None, timeout=30):
    """The published releases of `owner/repo`, newest first.

    Uses curl when available (the dev host's shell environment carries
    any credentials/gitconfig curl would use); falls back to urllib.
    """
    api = url or f"https://api.github.com/repos/{repo}/releases?per_page=30"
    cmd = [
        "curl",
        "-fsSL",
        "--max-time",
        str(timeout),
        "-H",
        "Accept: application/vnd.github+json",
        api,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        with urllib.request.urlopen(api, timeout=timeout) as resp:
            out = resp.read().decode()
    releases = json.loads(out)
    return [
        {
            "tag": rel["tag_name"],
            "version": rel["tag_name"].lstrip("v"),
            "published": rel.get("published_at", ""),
            "tarball": rel["tarball_url"],
        }
        for rel in releases
        if not rel.get("draft") and not rel.get("prerelease")
    ]


def resolve_sw(spec, releases):
    """Validate an ITF_SURVEY_SW spec against the release window.

    Returns {"mode": "tree"} or {"mode": "release", "tag", "version",
    "tarball"}; raises ValueError naming the five newest on any mismatch.
    """
    spec = (spec or "tree").strip()
    if spec == "tree":
        return {"mode": "tree"}
    window = releases[:RELEASE_WINDOW]
    names = ", ".join(r["tag"] for r in window) or "(none published)"
    if spec == "latest":
        if not window:
            raise ValueError("no published releases")
        rel = window[0]
    elif re.fullmatch(r"prev:[1-4]", spec):
        idx = int(spec.split(":")[1])
        if idx >= len(window):
            raise ValueError(f"{spec} beyond the {RELEASE_WINDOW} newest releases ({names})")
        rel = window[idx]
    elif spec.startswith("tag:"):
        want = spec[4:]
        rel = next((r for r in window if r["tag"] == want), None)
        if rel is None:
            raise ValueError(
                f"{want} is not among the {RELEASE_WINDOW} newest published releases: {names}"
            )
    else:
        raise ValueError(f"bad ITF_SURVEY_SW spec: {spec!r} (tree | latest | prev:N | tag:<v>)")
    return {
        "mode": "release",
        "tag": rel["tag"],
        "version": rel["version"],
        "tarball": rel["tarball"],
    }


def fetch_release_tree(sw, dest_dir):
    """Download+extract the release tarball; returns the tree root path."""
    os.makedirs(dest_dir, exist_ok=True)
    tarball = os.path.join(dest_dir, f"{sw['tag']}.tar.gz")
    subprocess.run(
        ["curl", "-fsSL", "--max-time", "300", "-o", tarball, sw["tarball"]],
        check=True,
    )
    subprocess.run(["tar", "-xzf", tarball, "-C", dest_dir], check=True)
    os.unlink(tarball)
    entries = [e for e in os.listdir(dest_dir) if not e.endswith(".tar.gz")]
    if len(entries) != 1:
        raise ManifestError(f"release tarball not release-shaped: {entries}")
    return os.path.join(dest_dir, entries[0])


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def build_sample(items, seed, fraction):
    """Seeded ≥50% sample in random order, each item with a profile.

    Profiles are drawn from the same seeded RNG after the sample is
    chosen, so (seed, universe) fully determines the run.
    """
    if not 0.5 <= fraction <= 1.0:
        raise ValueError(f"fraction must be within [0.5, 1.0], got {fraction}")
    rng = random.Random(seed)
    k = math.ceil(len(items) * fraction)
    chosen = rng.sample(items, k)
    rng.shuffle(chosen)
    sampled = []
    for it in chosen:
        entry = dict(it)
        entry["profile"] = rng.choice(PROFILES)
        sampled.append(entry)
    return sampled


def write_archive(path, sample, *, seed, fraction, sw, universe_items):
    counts = {}
    for it in sample:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    archive = {
        "format": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seed": seed,
        "fraction": fraction,
        "sw": sw,
        "universe_digest": universe_digest(universe_items),
        "universe_counts": {
            "total": len(universe_items),
            **{
                kind: sum(1 for it in universe_items if it["kind"] == kind)
                for kind in ("cli", "gui-button", "gui-widget", "gui-composite")
            },
        },
        "sample_counts": counts,
        "items": sample,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=1)
        f.write("\n")
    return archive


def load_archive(path):
    with open(path, encoding="utf-8") as f:
        archive = json.load(f)
    for key in ("format", "seed", "fraction", "sw", "universe_digest", "items"):
        if key not in archive:
            raise ManifestError(f"archive missing key: {key}")
    if archive["format"] != 1:
        raise ManifestError(f"unknown archive format: {archive['format']}")
    return archive


def replay_drift(archive, universe_items):
    """Compare an archived sample against today's universe.

    Returns (missing, unknown): ids the archive selected that no longer
    exist, and — informational — nothing else.  Replay still runs the
    resolvable items; drift is reported, never silently dropped.
    """
    live = {it["id"] for it in universe_items}
    missing = [it["id"] for it in archive["items"] if it["id"] not in live]
    digest_now = universe_digest(universe_items)
    digest_match = archive["universe_digest"] == digest_now
    return missing, digest_match


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit(sample):
    for it in sample:
        page = it.get("page", "")
        print(
            "\t".join(
                [
                    it["id"],
                    it["kind"],
                    it.get("name", ""),
                    page,
                    it.get("profile", "-"),
                ]
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("new", "replay"))
    parser.add_argument(
        "--repo-root",
        default=SURVEY_DIR + "/../..",
        help="tree under test (default: this working tree)",
    )
    parser.add_argument("--seed", help="pin the RNG seed (default: random)")
    parser.add_argument("--fraction", type=float, default=DEFAULT_FRACTION)
    parser.add_argument("--archive", help="archive to write (new) or read (replay)")
    parser.add_argument("--extract-dir", help="keep the fetched release tree here (release mode)")
    parser.add_argument("--releases-url", help=argparse.SUPPRESS)
    parser.add_argument("--github-repo", default=os.environ.get("ITF_GITHUB_REPO", ""))
    parser.add_argument(
        "--sw",
        default=os.environ.get("ITF_SURVEY_SW", "tree"),
        help="tree | latest | prev:N | tag:<v>",
    )
    parser.add_argument(
        "--no-gui", action="store_true", help="skip GUI enumeration (unit tests only)"
    )
    parser.add_argument(
        "--emit-universe",
        action="store_true",
        help="print the universe (id,kind) instead of sampling",
    )
    args = parser.parse_args(argv)

    repo_root = os.path.realpath(args.repo_root)
    if not os.path.isdir(os.path.join(repo_root, "bin")):
        print(f"FATAL: not a product tree: {repo_root}", file=sys.stderr)
        return 2

    # SW resolution: only release specs need the GitHub window; tree mode
    # must work offline.
    releases = []
    if args.sw != "tree":
        if not args.github_repo:
            print("FATAL: release mode needs --github-repo/ITF_GITHUB_REPO", file=sys.stderr)
            return 2
        try:
            releases = github_releases(args.github_repo, url=args.releases_url)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"FATAL: cannot read releases: {exc}", file=sys.stderr)
            return 2
    try:
        sw = resolve_sw(args.sw, releases)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    enum_root = repo_root
    extract_dir = None
    if sw["mode"] == "release":
        try:
            extract_dir = tempfile.mkdtemp(prefix="survey-sw-")
            enum_root = fetch_release_tree(sw, extract_dir)
        except (OSError, subprocess.CalledProcessError, ManifestError) as exc:
            print(f"FATAL: release fetch failed: {exc}", file=sys.stderr)
            return 2

    try:
        items = enumerate_universe(enum_root, with_gui=not args.no_gui)
    except ManifestError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.emit_universe:
        for it in items:
            print(f"{it['id']}\t{it['kind']}")
        return 0

    if args.mode == "replay":
        if not args.archive:
            print("FATAL: replay needs --archive", file=sys.stderr)
            return 2
        try:
            archive = load_archive(args.archive)
        except (OSError, ManifestError, json.JSONDecodeError) as exc:
            print(f"FATAL: {exc}", file=sys.stderr)
            return 2
        # Replay fidelity: the archived SW target defines the tree; a
        # conflicting explicit ITF_SURVEY_SW is refused rather than
        # ignored.  (`sw`, resolved earlier, carries the requested tag.)
        arch_sw = archive["sw"]
        if args.sw != "tree" and sw.get("tag") != arch_sw.get("tag"):
            print(
                f"FATAL: archive surveyed {json.dumps(arch_sw)} but "
                f"ITF_SURVEY_SW={args.sw} names {sw.get('tag')!r} — replay "
                "must use the archived target",
                file=sys.stderr,
            )
            return 2
        if arch_sw.get("mode") == "release":
            try:
                extract_dir = args.extract_dir or tempfile.mkdtemp(prefix="survey-sw-")
                enum_root = fetch_release_tree(arch_sw, extract_dir)
            except (OSError, subprocess.CalledProcessError, ManifestError) as exc:
                print(f"FATAL: release fetch failed: {exc}", file=sys.stderr)
                return 2
            try:
                items = enumerate_universe(enum_root, with_gui=not args.no_gui)
            except ManifestError as exc:
                print(f"FATAL: {exc}", file=sys.stderr)
                return 2
        missing, digest_match = replay_drift(archive, items)
        note = "" if digest_match else " universe-drift=yes"
        sw_label = arch_sw.get("tag") or arch_sw.get("mode", "tree")
        print(f"# replay {os.path.basename(args.archive)}{note}")
        print(f"# seed {archive['seed']}")
        print(f"# sw {sw_label}")
        print(f"# enum-root {enum_root}")
        if missing:
            print(f"# missing-from-universe: {','.join(missing)}")
        _emit(archive["items"])
        return 0

    # new
    seed = args.seed or hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    try:
        sample = build_sample(items, seed, args.fraction)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    archive_path = args.archive or os.path.join(
        SURVEY_DIR,
        "archives",
        time.strftime("survey-%Y%m%d-%H%M%S-") + seed[:8] + ".json",
    )
    archive = write_archive(
        archive_path,
        sample,
        seed=seed,
        fraction=args.fraction,
        sw=sw,
        universe_items=items,
    )
    sw_label = sw.get("tag") or sw.get("mode", "tree")
    print(f"# archive {archive_path}")
    print(f"# seed {seed}")
    print(f"# sw {sw_label}")
    print(f"# enum-root {enum_root}")
    print(f"# sampled {len(sample)}/{len(items)}")
    _emit(sample)
    return 0


if __name__ == "__main__":
    sys.exit(main())
