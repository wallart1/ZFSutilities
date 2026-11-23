"""Tests for the j22 world planner (tests/integrated/survey/world.py).

Covers the lived-in ladder's contracts: determinism per (variant, seed,
anchor), the digest document (thin stays the Phase-1 formula), the
product's bucket-derivation law, the over-retention shape against the
real DEFAULT_RETENTION, duplicate prey clusters, budgets, rid-relative
naming, and the TSV the guest walk consumes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.realpath(os.path.join(TESTS_DIR, "..", ".."))
SURVEY_DIR = os.path.join(REPO_ROOT, "tests", "integrated", "survey")
for _p in (SURVEY_DIR, os.path.join(REPO_ROOT, "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import world
from feature_config import DEFAULT_RETENTION

ANCHOR = 1765756800  # 2025-12-15T00:00Z — pinned so every test is exact
SEED = "unitworld"


def _plan(seed=SEED, anchor=ANCHOR):
    return world.relative_plan("lived-in", seed, anchor)


def _resolved(seed=SEED, anchor=ANCHOR):
    return world.resolve_epochs(_plan(seed, anchor), anchor)


def _tsv_rows(text):
    return [line.split("\t") for line in text.splitlines() if line and not line.startswith("#")]


# ---------------------------------------------------------------------------
# Determinism + digest
# ---------------------------------------------------------------------------


def test_plan_deterministic_same_seed_and_anchor():
    a = json.dumps(_plan(), sort_keys=True)
    b = json.dumps(_plan(), sort_keys=True)
    assert a == b
    assert world.emit_ladder_tsv(_resolved()) == world.emit_ladder_tsv(_resolved())


def test_plan_seed_sensitive():
    assert json.dumps(_plan(), sort_keys=True) != json.dumps(_plan("other"), sort_keys=True)


def test_digest_matches_plan_document():
    plan = _plan()
    doc = {"anchor": "2025-12-15", "plan": plan, "seed": SEED, "variant": "lived-in"}
    want = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:16]
    assert world.world_digest("lived-in", SEED, ANCHOR) == want


def test_thin_digest_is_the_phase1_formula():
    want = hashlib.sha256(
        json.dumps({"seed": SEED, "variant": "thin"}, sort_keys=True).encode()
    ).hexdigest()[:16]
    assert world.world_digest("thin", SEED) == want
    assert world.world_digest("thin", SEED, ANCHOR) == want  # anchor never matters


def test_digest_seed_and_anchor_sensitive():
    base = world.world_digest("lived-in", SEED, ANCHOR)
    assert base != world.world_digest("lived-in", "other", ANCHOR)
    assert base != world.world_digest("lived-in", SEED, ANCHOR + 7 * 86400)


def test_thin_has_no_plan_busy_refused():
    assert world.relative_plan("thin", SEED) is None
    for bad, exc in (("busy", "Phase 5"), ("bogus", "bad world variant")):
        try:
            world.relative_plan(bad, SEED)
            raise AssertionError(f"{bad} accepted")
        except world.PlanError as e:
            assert exc in str(e)
    try:
        world.relative_plan("lived-in", SEED)  # no anchor
        raise AssertionError("lived-in without anchor accepted")
    except world.PlanError as e:
        assert "anchor" in str(e)


# ---------------------------------------------------------------------------
# Shape: over-retention, prey clusters, clone, budgets
# ---------------------------------------------------------------------------


def test_primary_ladder_over_retained_vs_product_defaults():
    rows = [r for r in _plan()["ladder"] if r["dataset"] == world.PRIMARY_DS]
    counts = Counter(r["bucket"] for r in rows)
    defaults = {b["name"]: b for b in DEFAULT_RETENTION}
    for bucket, spec in defaults.items():
        got = counts[bucket]
        assert got > spec["retain"], (
            f"primary {bucket} count {got} not over retain={spec['retain']}"
        )
    assert counts["d"] == world.PRIMARY_COUNTS["d"]
    assert counts["s"] == world.PRIMARY_COUNTS["s"]


def test_duplicate_prey_clusters_present():
    plan = _plan()
    prim = [r for r in plan["ladder"] if r["dataset"] == world.PRIMARY_DS]
    d_days = Counter(r["day_offset"] for r in prim if r["bucket"] == "d")
    assert max(d_days.values()) >= world.SAMEDAY_DUPS, "same-day d cluster missing"
    # Same-month offsite pair: day offsets within one calendar month of
    # each other (the pair is constructed on real dates; offsets within
    # 27 days of each other and both beyond 65 days back is the pair).
    offsx = [r["day_offset"] for r in prim if r["bucket"] == "s"]
    aged = [o for o in offsx if o <= -65]
    assert len(aged) >= world.SAMEMONTH_S_DUPS
    assert any(abs(a - b) <= 27 for a in aged for b in aged if a != b)


def test_aged_offsite_pair_clears_the_65d_minage():
    resolved = _resolved()
    anchor = dt.datetime.fromtimestamp(ANCHOR, tz=dt.timezone.utc).date()
    ages = sorted(
        (
            (anchor - dt.datetime.fromtimestamp(r["epoch"], tz=dt.timezone.utc).date()).days
            for r in resolved["ladder"]
            if r["label"] == "offsite" and r["dataset"] == world.PRIMARY_DS
        ),
        reverse=True,
    )
    assert ages[1] > 65, f"second-oldest offsite age {ages[1]} does not clear minage"


def test_offsite_pair_minage_holds_across_seed_anchor_corners():
    """The minage bound is structural, not seed luck.

    Regression: the same-month partner draw used to be unconstrained, so
    some (seed, anchor) corners landed the second pair member under the
    65-day minage — and the plan only failed at stage time, after the
    lab was cloned (live hit: seed p3gate2026, anchor 1795016717, pair
    ages [71, 58]).  The partner pick is now bounded to days at least 66
    back, so every corner plans validly.
    """
    import random

    rng = random.Random(1795016717)
    corners = [("p3gate2026", 1795016717)]
    corners += [
        (f"corner{i}-{rng.getrandbits(32):08x}", rng.randint(1_780_000_000, 1_800_000_000))
        for i in range(40)
    ]
    for seed, anchor_epoch in corners:
        resolved = world.resolve_epochs(
            world.relative_plan("lived-in", seed, anchor_epoch), anchor_epoch
        )
        anchor = dt.datetime.fromtimestamp(anchor_epoch, tz=dt.timezone.utc).date()
        ages = sorted(
            (
                (anchor - dt.datetime.fromtimestamp(r["epoch"], tz=dt.timezone.utc).date()).days
                for r in resolved["ladder"]
                if r["label"] == "offsite" and r["dataset"] == world.PRIMARY_DS
            ),
            reverse=True,
        )
        assert ages[1] > 65, (
            f"seed={seed} anchor={anchor_epoch}: second-oldest offsite age "
            f"{ages[1]} does not clear minage"
        )


def test_lived_in_digests_of_validated_worlds_never_move():
    """The Phase-2 gate worlds must replay forever.

    The digest recorded by the 2026-11-18 Phase-2 gate runs (both runs,
    fresh and replay, identical) is pinned here: the planner must
    reproduce it byte-for-byte.  Any change that moves this digest makes
    every archived lived-in world non-replayable (planner-drift refusal)
    — including the minage-bound partner fix, which is why that fix only
    redirects draws that were already invalid.
    """
    assert world.world_digest("lived-in", "gatesingle", 1794984375) == "875689885d1390ec"


def test_one_clone_row_and_matching_directive():
    plan = _plan()
    clones = [r for r in plan["ladder"] if r["bucket"] == "c"]
    assert len(clones) == 1
    assert clones[0]["label"] == "clone"
    assert plan["clone"]["minute"] == clones[0]["minute"]
    assert plan["clone"]["dataset"] == clones[0]["dataset"]
    assert plan["clone"]["target"] == world.CLONE_TARGET


def test_two_dailybackup_run_points():
    plan = _plan()
    assert len(plan["dailybackup"]) == world.DAILYBACKUP_RUNS
    for e in plan["dailybackup"]:
        assert e["source"] == world.BACKUP_SRC_DS
        assert e["dest"] == world.RECV_DEST


def test_budgets_enforced_in_plan():
    plan = _plan()
    snapshots = len(plan["ladder"]) + len(plan["dailybackup"])
    assert snapshots <= world.MAX_SNAPSHOTS
    payload = sum(f["bytes"] for d in plan["datasets"] for f in d["files"])
    assert payload + world.VOL_BYTES <= world.MAX_PAYLOAD_BYTES


def test_budget_fences_raise():
    real_max, real_cap = world.MAX_SNAPSHOTS, world.MAX_PAYLOAD_BYTES
    try:
        world.MAX_SNAPSHOTS = 10
        try:
            _plan()
            raise AssertionError("snapshot budget not enforced")
        except world.PlanError as e:
            assert "snapshots" in str(e)
        world.MAX_SNAPSHOTS = real_max
        world.MAX_PAYLOAD_BYTES = 1024
        try:
            _plan()
            raise AssertionError("payload budget not enforced")
        except world.PlanError as e:
            assert "payload" in str(e)
    finally:
        world.MAX_SNAPSHOTS, world.MAX_PAYLOAD_BYTES = real_max, real_cap


def test_selective_offsite_holds():
    plan = _plan()
    held = [r for r in plan["ladder"] if r["hold"]]
    assert len(held) == world.HELD_OFFSITE_ROWS
    assert all(r["label"] == "offsite" for r in held)
    assert all(r["hold"].startswith("offsite-") for r in held)


# ---------------------------------------------------------------------------
# Product laws: bucket derivation, names, uniqueness
# ---------------------------------------------------------------------------


def test_bucket_law_holds_for_resolved_rows():
    resolved = _resolved()
    for r in resolved["ladder"]:
        date = dt.datetime.fromtimestamp(r["epoch"], tz=dt.timezone.utc).date()
        if r["bucket"] == "c":
            continue
        world.assert_bucket_law(date, r["label"], r["bucket"])  # raises on violation


def test_row_names_follow_product_construction():
    resolved = _resolved()
    for r in resolved["ladder"]:
        ts = dt.datetime.fromtimestamp(r["epoch"], tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        want = f"clone-{ts}-c" if r["bucket"] == "c" else f"{r['label']}-{ts}-{r['bucket']}"
        assert r["name"] == want


def test_ladder_rows_unique_per_dataset():
    keys = [(r["dataset"], r["day_offset"], r["minute"]) for r in _plan()["ladder"]]
    assert len(keys) == len(set(keys))
    names = [(r["dataset"], r["name"]) for r in _resolved()["ladder"]]
    assert len(names) == len(set(names))


def test_tree_depth_and_two_zvols():
    plan = _plan()
    fs = [d["name"] for d in plan["datasets"] if d["kind"] == "fs"]
    zvols = [d for d in plan["datasets"] if d["kind"] == "zvol"]
    assert len(zvols) == 2
    assert all(d["volsize"] == world.VOLSIZE for d in zvols)
    # Depth >= 3 below the base (pool/survey-rid is level 1).
    assert any(name.count("/") >= 2 for name in fs)


# ---------------------------------------------------------------------------
# TSV emission
# ---------------------------------------------------------------------------


def test_tsv_shape_directives_and_ordering():
    text = world.emit_ladder_tsv(_resolved())
    lines = text.splitlines()
    assert any(l.startswith("# dataset ") for l in lines)
    assert sum(1 for l in lines if l.startswith("# zvol") or " zvol " in l) == 2
    assert sum(1 for l in lines if l.startswith("# file ")) >= 10
    assert sum(1 for l in lines if l.startswith("# dailybackup ")) == 2
    assert sum(1 for l in lines if l.startswith("# clone ")) == 1
    rows = _tsv_rows(text)
    assert all(len(r) == 6 for r in rows)
    epochs = [int(r[0]) for r in rows]
    assert epochs == sorted(epochs), "rows not in walk order"
    assert all(r[1].startswith("{BASE}/") for r in rows)
    assert any("{DS2BASE}" in l for l in lines if l.startswith("# dailybackup "))
    # No absolute (rid- or pool-bearing) names in the digest document.
    assert "zfstest" not in text


def test_cli_plan_and_digest(tmp_path):
    import subprocess

    out_json = tmp_path / "plan.json"
    out_tsv = tmp_path / "ladder.tsv"
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(SURVEY_DIR, "world.py"),
            "plan",
            "--variant",
            "lived-in",
            "--seed",
            SEED,
            "--anchor",
            str(ANCHOR),
            "--out-json",
            str(out_json),
            "--out-tsv",
            str(out_tsv),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert f"digest {world.world_digest('lived-in', SEED, ANCHOR)}" in r.stdout
    assert out_tsv.read_text() == world.emit_ladder_tsv(_resolved())
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(SURVEY_DIR, "world.py"),
            "digest",
            "--variant",
            "lived-in",
            "--seed",
            SEED,
            "--anchor",
            str(ANCHOR),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == world.world_digest("lived-in", SEED, ANCHOR)
    r = subprocess.run(
        [
            sys.executable,
            os.path.join(SURVEY_DIR, "world.py"),
            "digest",
            "--variant",
            "busy",
            "--seed",
            SEED,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 2
    assert "Phase 5" in r.stderr
