"""Tests for the j22 function-survey sampler (tests/integrated/survey).

Covers the selection engine's contracts: manifest/docs sync in both
directions, determinism, the >=50% floor, archive round-trip and drift
reporting, the five-newest release window, profile assignment, and the
GUI catalog's structural sanity.  The gi-needing tests (real-tree GUI
enumeration) use the module-level requires_gi guard so the suite skips
cleanly on hosts without the GTK bindings.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys

import pytest
from test_support import requires_gi

pytestmark = requires_gi

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.realpath(os.path.join(TESTS_DIR, "..", ".."))
SURVEY_DIR = os.path.join(REPO_ROOT, "tests", "integrated", "survey")
if SURVEY_DIR not in sys.path:
    sys.path.insert(0, SURVEY_DIR)

import sample as sampler

# ---------------------------------------------------------------------------
# Manifest parsing + docs sync (the closed-list law, made mechanical)
# ---------------------------------------------------------------------------


def _manifest_rows():
    rows, headers = sampler.parse_universe_tsv(os.path.join(SURVEY_DIR, "universe.tsv"))
    return rows, headers


def _documented_commands():
    names = set()
    for page in ("commands.md", "two-node.md"):
        path = os.path.join(REPO_ROOT, "docs", "docs", "commands-and-modules", page)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        names |= set(re.findall(r"^- \[`([A-Za-z0-9][A-Za-z0-9._-]*)`", src, re.MULTILINE))
        names |= set(re.findall(r"^### `([A-Za-z0-9][A-Za-z0-9._-]*)`", src, re.MULTILINE))
    return names


_EXCLUSION_LINE = re.compile(r"^#   (?P<reason>[a-z-]+): (?P<name>[a-z0-9][a-z0-9._-]*)\s*$")


def _manifest_exclusions():
    """Parse the EXCLUDED rows out of universe.tsv's comments.

    Only reason-class rows match ("#   misc: zfsstatus") — one documented
    command per line; prose comments never match.
    """
    excluded = set()
    with open(os.path.join(SURVEY_DIR, "universe.tsv"), encoding="utf-8") as f:
        for line in f:
            match = _EXCLUSION_LINE.match(line.rstrip("\n"))
            if match:
                excluded.add(match.group("name"))
    return excluded


def test_manifest_parses_with_expected_columns():
    rows, headers = _manifest_rows()
    assert "id" in headers and "command" in headers
    assert "lab" in headers and "node" in headers and "depth" in headers
    assert rows, "universe.tsv must carry at least one command row"
    for row in rows:
        assert row["lab"] in ("single", "two"), row
        assert row["node"] in ("storage", "compute"), row
        assert row["depth"] in ("deep", "argcheck", "bespoke"), row


def test_manifest_commands_exist_in_bin():
    for row in _manifest_rows()[0]:
        assert os.access(os.path.join(REPO_ROOT, "bin", row["command"]), os.X_OK), (
            f"manifest command missing from bin/: {row['command']}"
        )


def test_manifest_ids_are_stable_cli_names():
    for row in _manifest_rows()[0]:
        assert row["id"] == f"cli-{row['command']}", row


def test_documented_surface_is_manifest_plus_exclusions():
    """No documented command silently misses the sampling universe."""
    rows, _ = _manifest_rows()
    manifest = {row["command"] for row in rows}
    documented = _documented_commands()
    excluded = _manifest_exclusions()
    unaccounted = documented - manifest - excluded
    assert not unaccounted, f"documented but neither sampled nor excluded: {sorted(unaccounted)}"


def test_manifest_rows_are_documented():
    """Every sampled command is a documented user command."""
    rows, _ = _manifest_rows()
    documented = _documented_commands()
    for row in rows:
        assert row["command"] in documented, f"{row['command']} is sampled but not documented"


def test_exclusions_are_subset_of_documented():
    excluded = _manifest_exclusions()
    documented = _documented_commands()
    stray = excluded - documented
    assert not stray, f"exclusion table names non-documented entries: {stray}"


# ---------------------------------------------------------------------------
# Sampling: determinism, floor, profiles
# ---------------------------------------------------------------------------


def _fake_items(n=40):
    return [{"id": f"cli-cmd{i:03d}", "kind": "cli", "name": f"cmd{i}"} for i in range(n)]


def test_same_seed_same_sample_and_order():
    a = sampler.build_sample(_fake_items(), "seed-1", 0.5)
    b = sampler.build_sample(_fake_items(), "seed-1", 0.5)
    assert [i["id"] for i in a] == [i["id"] for i in b]
    assert [i["profile"] for i in a] == [i["profile"] for i in b]


def test_different_seed_different_order_or_set():
    a = sampler.build_sample(_fake_items(), "seed-1", 0.5)
    b = sampler.build_sample(_fake_items(), "seed-2", 0.5)
    ids_a = [i["id"] for i in a]
    ids_b = [i["id"] for i in b]
    assert ids_a != ids_b  # 40-choose-20: collision probability ~0


def test_sample_at_least_half():
    items = _fake_items(41)
    sample = sampler.build_sample(items, "s", 0.5)
    assert len(sample) == math.ceil(41 * 0.5)  # 21, never floor
    assert len(sample) >= len(items) / 2


def test_fraction_below_half_refused():
    with pytest.raises(ValueError):
        sampler.build_sample(_fake_items(), "s", 0.49)
    with pytest.raises(ValueError):
        sampler.build_sample(_fake_items(), "s", 1.5)


def test_every_item_carries_a_valid_profile():
    sample = sampler.build_sample(_fake_items(), "s", 1.0)
    assert len(sample) == 40
    for item in sample:
        assert item["profile"] in sampler.PROFILES


def test_profiles_vary_across_a_full_sample():
    sample = sampler.build_sample(_fake_items(200), "mixed-seed", 1.0)
    used = {item["profile"] for item in sample}
    assert len(used) >= 3, "a full sample must draw varied profiles"


def test_universe_digest_stable_and_sensitive():
    items = _fake_items()
    d1 = sampler.universe_digest(items)
    d2 = sampler.universe_digest(list(items))
    assert d1 == d2
    items[0]["id"] = "cli-changed"
    assert sampler.universe_digest(items) != d1


# ---------------------------------------------------------------------------
# Archive round-trip + replay drift
# ---------------------------------------------------------------------------


def test_archive_round_trip(tmp_path):
    items = _fake_items()
    sample = sampler.build_sample(items, "arch-seed", 0.5)
    path = tmp_path / "survey.json"
    archive = sampler.write_archive(
        str(path), sample, seed="arch-seed", fraction=0.5, sw={"mode": "tree"}, universe_items=items
    )
    loaded = sampler.load_archive(str(path))
    assert loaded["seed"] == "arch-seed"
    assert loaded["sw"] == {"mode": "tree"}
    assert [i["id"] for i in loaded["items"]] == [i["id"] for i in sample]
    assert loaded["items"][0]["profile"] == sample[0]["profile"]
    assert archive["universe_counts"]["total"] == len(items)


def test_replay_drift_reports_missing_ids(tmp_path):
    items = _fake_items()
    sample = sampler.build_sample(items, "drift-seed", 0.5)
    path = tmp_path / "survey.json"
    sampler.write_archive(
        str(path),
        sample,
        seed="drift-seed",
        fraction=0.5,
        sw={"mode": "tree"},
        universe_items=items,
    )
    # Shrink the universe: one selected id disappears.
    shrunken = [it for it in items if it["id"] != sample[0]["id"]]
    missing, digest_match = sampler.replay_drift(sampler.load_archive(str(path)), shrunken)
    assert missing == [sample[0]["id"]]
    assert digest_match is False
    # Unchanged universe: no drift.
    missing, digest_match = sampler.replay_drift(sampler.load_archive(str(path)), items)
    assert missing == []
    assert digest_match is True


def test_load_archive_rejects_bad_format(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"format": 99, "items": []}))
    with pytest.raises(sampler.ManifestError):
        sampler.load_archive(str(path))


# ---------------------------------------------------------------------------
# Release window (the five most recent published releases)
# ---------------------------------------------------------------------------


def _fake_releases(n=8):
    return [
        {
            "tag": f"v0.{140 - i}.0",
            "version": f"0.{140 - i}.0",
            "published": f"2026-11-0{i % 10}",
            "tarball": f"http://x/{i}",
        }
        for i in range(n)
    ]


def test_resolve_sw_tree():
    assert sampler.resolve_sw("tree", _fake_releases()) == {"mode": "tree"}
    assert sampler.resolve_sw("", _fake_releases()) == {"mode": "tree"}


def test_resolve_sw_latest_and_prev():
    rels = _fake_releases()
    sw = sampler.resolve_sw("latest", rels)
    assert sw["tag"] == "v0.140.0"
    sw = sampler.resolve_sw("prev:2", rels)
    assert sw["tag"] == "v0.138.0"


def test_resolve_sw_tag_inside_window():
    sw = sampler.resolve_sw("tag:v0.137.0", _fake_releases())
    assert sw["mode"] == "release"
    assert sw["version"] == "0.137.0"


def test_resolve_sw_refusals_name_the_five():
    rels = _fake_releases()
    with pytest.raises(ValueError) as exc:
        sampler.resolve_sw("tag:v0.100.0", rels)
    assert "v0.140.0" in str(exc.value)  # the five newest are listed
    with pytest.raises(ValueError):
        sampler.resolve_sw("prev:9", rels)
    with pytest.raises(ValueError):
        sampler.resolve_sw("wat", rels)


def test_github_releases_via_file_url(tmp_path):
    payload = [
        {
            "tag_name": "v0.140.0",
            "published_at": "2026-11-03T00:00:00Z",
            "tarball_url": "http://x/1",
            "draft": False,
            "prerelease": False,
        },
        {
            "tag_name": "v0.139.0",
            "published_at": "2026-11-02T00:00:00Z",
            "tarball_url": "http://x/2",
            "draft": False,
            "prerelease": True,
        },
        {
            "tag_name": "v0.138.0",
            "published_at": "2026-11-01T00:00:00Z",
            "tarball_url": "http://x/3",
            "draft": False,
            "prerelease": False,
        },
    ]
    path = tmp_path / "releases.json"
    path.write_text(json.dumps(payload))
    rels = sampler.github_releases("o/r", url=f"file://{path}")
    assert [r["tag"] for r in rels] == ["v0.140.0", "v0.138.0"]  # prerelease out


def test_cli_mode_end_to_end_tree(tmp_path):
    """The sampler CLI: new, then replay of the archive it wrote."""
    work = tmp_path
    archive = work / "a.json"
    out1 = subprocess.run(
        [
            sys.executable,
            os.path.join(SURVEY_DIR, "sample.py"),
            "new",
            "--repo-root",
            REPO_ROOT,
            "--no-gui",
            "--seed",
            "cli-seed",
            "--fraction",
            "1.0",
            "--archive",
            str(archive),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    ids1 = [line.split("\t")[0] for line in out1.splitlines() if line and not line.startswith("#")]
    manifest_rows, _ = _manifest_rows()
    assert len(ids1) == len(manifest_rows)  # fraction 1.0 = the whole CLI universe
    out2 = subprocess.run(
        [
            sys.executable,
            os.path.join(SURVEY_DIR, "sample.py"),
            "replay",
            "--repo-root",
            REPO_ROOT,
            "--no-gui",
            "--archive",
            str(archive),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    ids2 = [line.split("\t")[0] for line in out2.splitlines() if line and not line.startswith("#")]
    assert ids1 == ids2
    assert "enum-root" in out2


# ---------------------------------------------------------------------------
# GUI catalog structure
# ---------------------------------------------------------------------------


def test_gui_catalog_ids_unique():
    import gui_catalog

    ids = []
    for page, interactions in gui_catalog.L2_INTERACTIONS.items():
        for inter in interactions:
            ids.append(f"gui-w-{page}-{inter['suffix']}")
    for comp in gui_catalog.L3_COMPOSITES:
        ids.append(f"gui-c-{comp['id']}")
    assert len(ids) == len(set(ids)), "duplicate catalog ids"
    assert len(ids) >= 40, "the catalog should cover every page meaningfully"


def test_gui_catalog_roles_known():
    import gui_catalog

    known = {
        "select-first",
        "select-second",
        "select-multi",
        "toggle-active",
        "toggle-check",
        "edit-cell",
        "cycle-combo",
        "set-entry",
        "adjust-spin",
        "toggle-dry-run",
        "navigate",
        "expand-first",
        "collapse-all",
    }
    for interactions in gui_catalog.L2_INTERACTIONS.values():
        for inter in interactions:
            assert inter["role"] in known, inter


def test_gui_catalog_covers_every_page():
    import action_dispatch
    import gui_catalog

    pages_with_catalog = set(gui_catalog.L2_INTERACTIONS)
    pages_in_product = set(action_dispatch.ACTION_HANDLERS)
    assert pages_with_catalog == pages_in_product


# ---------------------------------------------------------------------------
# Real-tree enumeration (gi-gated)
# ---------------------------------------------------------------------------


def test_gui_button_universe_from_real_tree():
    try:
        import gi

        gi.require_version("Gtk", "3.0")
    except Exception:
        pytest.skip("gi unavailable")
    items = sampler.gui_button_universe(REPO_ROOT)
    assert len(items) >= 90
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids))
    assert all(i["kind"] == "gui-button" for i in items)


def test_cli_universe_validates_against_real_bin():
    items = sampler.cli_universe(REPO_ROOT)
    assert len(items) >= 55
    assert all(i["kind"] == "cli" for i in items)
    labs = {i["lab"] for i in items}
    assert labs <= {"single", "two"}


def test_enumerate_universe_sorted_and_unique():
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        with_gui = True
    except Exception:
        with_gui = False
    items = sampler.enumerate_universe(REPO_ROOT, with_gui=with_gui)
    ids = [i["id"] for i in items]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
