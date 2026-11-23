#!/usr/bin/env python3
"""world.py — deterministic world planner for the j22 function survey.

The lived-in world variant stages an aged, product-authentic snapshot
ladder: snapshots named by the product's own zfssnapbuild naming
(<label>-<YYYY-MM-DDTHH:MMZ>-<bucket>), with their ZFS creation times set
by walking the guest clock backward then forward (creation cannot be
backdated).  The plan is a pure function of (variant, seed): the dataset
tree with file payloads, the ladder rows, selective offsite holds, the
clone-bucket snapshot, and two real zfsdailybackup run points.

Determinism vs staging date: buckets follow the calendar (Sundays are
'w' days, month 1sts are 'm'), so a plan can only be deterministic
relative to a pinned anchor DATE.  The anchor is chosen when the archive
is written (sample.py records it in the world object), the digest covers
anchor date + plan, and replay regenerates the plan against the archived
anchor — the identical absolute world, down to every snapshot's date.
Dataset names are base-relative ({BASE} placeholder), so the digest is
run-rid-independent.

Bucket law (mirrors bin/zfssnapbuild): bucket 'm' on the 1st of the
month (monthly wins over weekly), 'w' on other Sundays, 'd' on ordinary
days; the offsite label forces 's'; zfsclone-vm's clone snapshots carry
'c' in the same positional slot.  The planner picks day slots that land
on the right UTC days, and the guest-side staging (world-stage.sh)
asserts the product's own derivation reproduces each planned name.

Budgets are enforced in-plan (hard errors): at most MAX_SNAPSHOTS
snapshots including the zfsdailybackup-created ones, and at most
MAX_PAYLOAD_BYTES of file payload plus zvols.

Usage (see --help): the journey library drives this; survey-lib.sh
renders {BASE}/{DS2BASE} placeholders to the run's scratch names before
pushing the ladder TSV into the guest.
Stdlib-only (mirrors tests/integrated/survey/sample.py).
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import random
import sys
import time

WORLDS = ("thin", "lived-in", "busy")
DIGEST_WIDTH = 16
DAY = 86400
SUNDAY = 6  # datetime.date.weekday(): Monday=0 ... Sunday=6

# In-plan budget fences (the plan file's ~40 snapshots / ~200 MB).
MAX_SNAPSHOTS = 40
MAX_PAYLOAD_BYTES = 200 * 1024 * 1024

# The tree every lived-in world builds under {BASE}.  Parent-first order
# (world-stage.sh creates them in list order).  docs carries the primary
# over-retained ladder, photos the secondary variety ladder, backup-src
# is the leaf the two zfsdailybackup runs send, and the two zvols give
# the disk-facing surfaces real volumes.
TREE_DATASETS = (
    ("home", "fs"),
    ("home/user", "fs"),
    ("home/user/docs", "fs"),
    ("home/user/photos", "fs"),
    ("backup-src", "fs"),
    ("vm-disks", "fs"),
    ("vm-disks/disk-a", "zvol"),
    ("vm-disks/disk-b", "zvol"),
)
PRIMARY_DS = "home/user/docs"
SECONDARY_DS = "home/user/photos"
BACKUP_SRC_DS = "backup-src"
VOLSIZE = "16M"
VOL_BYTES = 2 * 16 * 1024 * 1024
CLONE_TARGET = "{BASE}/clone-work"
RECV_DEST = "{DS2BASE}"

# Over-retention shape vs DEFAULT_RETENTION (python/feature_config.py):
# d:3/w:2/m:2/s:4.  The primary dataset carries the full over-retained
# ladder plus the same-day (retention Phase-1) and same-month offsite
# (Phase-0) duplicate prey; the secondary dataset adds cross-dataset
# variety within the same budget.
PRIMARY_COUNTS = {"d": 6, "w": 4, "m": 4, "s": 6}
DEFAULT_RETAIN = {"d": 3, "w": 2, "m": 2, "s": 4}
SAMEDAY_DUPS = 3
SAMEMONTH_S_DUPS = 2
SECONDARY_COUNTS = {"m": 2, "w": 3, "d": 4, "s": 3}
DAILYBACKUP_RUNS = 2
HELD_OFFSITE_ROWS = 4


class PlanError(ValueError):
    """The requested world cannot be planned (unknown/unimplemented)."""


def resolve_variant(spec):
    """Validate a world-variant name; returns it, defaulting to thin.

    Mirrors sample.resolve_world's closed list so the two modules can
    never disagree on what a world is called.
    """
    spec = (spec or "thin").strip()
    if spec not in WORLDS:
        raise PlanError(f"bad world variant: {spec!r} ({' | '.join(WORLDS)})")
    return spec


# ---------------------------------------------------------------------------
# Day-slot math (UTC calendar days relative to the staging anchor)
# ---------------------------------------------------------------------------


def _sundays(anchor, count):
    """The newest `count` Sundays older than the anchor day, 1sts skipped.

    Monthly takes precedence when the 1st falls on a Sunday
    (zfssnapbuild's derivation order), so those Sundays are not 'w' days.
    Newest first.
    """
    d = anchor - dt.timedelta(days=1)
    while d.weekday() != SUNDAY:
        d -= dt.timedelta(days=1)
    out = []
    while len(out) < count:
        if d.day != 1:
            out.append(d)
        d -= dt.timedelta(days=7)
    return out


def _month_firsts(anchor, count):
    """The newest `count` month 1sts at least two days before the anchor.

    Newest first.
    """
    d = anchor.replace(day=1)
    out = []
    while len(out) < count:
        if d < anchor - dt.timedelta(days=1):
            out.append(d)
        d = (d - dt.timedelta(days=1)).replace(day=1)
    return out


def _ordinary_day(rng, anchor, lo, hi, taken, tries=500):
    """A seeded ordinary UTC day lo..hi days back (not Sunday, not the 1st).

    Bounded rejection sampling: a window whose free candidates are
    exhausted (pathological seed) raises instead of spinning.
    """
    for _ in range(tries):
        d = anchor - dt.timedelta(days=rng.randint(lo, hi))
        if d.weekday() != SUNDAY and d.day != 1 and d not in taken:
            return d
    raise PlanError(f"no free ordinary day within {lo}..{hi} days of the anchor")


def _same_month_partner(rng, day, taken, min_age_date=None):
    """A different day inside `day`'s month, not already used.

    With ``min_age_date``, the pick must not fall after that date — the
    offsite pair's minage guarantee.  The unconstrained draw happens
    first and is kept when it already qualifies, so every plan the old
    planner produced validly is reproduced byte-for-byte; only draws
    that were already invalid fall back to the oldest qualifying day
    (deterministically, with no extra rng consumption, so the rest of
    the stream stays put).
    """
    days_in_month = calendar.monthrange(day.year, day.month)[1]
    candidates = [
        day.replace(day=d)
        for d in range(1, days_in_month + 1)
        if d != day.day and day.replace(day=d) not in taken
    ]
    if not candidates:
        raise PlanError(f"no free partner day in {day:%Y-%m}")
    pick = rng.choice(candidates)
    if min_age_date is not None and pick > min_age_date:
        aged = [c for c in candidates if c <= min_age_date]
        if not aged:
            raise PlanError(
                f"no partner day in {day:%Y-%m} clears the minage ({min_age_date:%Y-%m-%d})"
            )
        pick = min(aged)
    return pick


def _bucket_of(date, label):
    """The bucket zfssnapbuild would derive for `date` + `label`."""
    if label == "offsite":
        return "s"
    if date.day == 1:
        return "m"
    if date.weekday() == SUNDAY:
        return "w"
    return "d"


def assert_bucket_law(date, label, bucket):
    """A ladder row's day must satisfy the product's bucket derivation."""
    derived = _bucket_of(date, label)
    if derived != bucket:
        raise PlanError(
            f"bucket law violated: {date.isoformat()} {label} plans {bucket} "
            f"but zfssnapbuild derives {derived}"
        )


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------


def _seeded_files(rng, stem, count, lo, hi):
    """Seeded file specs for one filesystem dataset (bytes in [lo, hi])."""
    return [{"path": f"{stem}-{i:02d}.dat", "bytes": rng.randint(lo, hi)} for i in range(count)]


def _datasets(rng):
    """The tree with seeded file payloads (base-relative names)."""
    files = {
        "home": _seeded_files(rng, "home", 2, 1024, 64 * 1024),
        "home/user": _seeded_files(rng, "user", 3, 1024, 128 * 1024),
        "home/user/docs": _seeded_files(rng, "doc", 5, 8 * 1024, 3 * 1024 * 1024),
        "home/user/photos": _seeded_files(rng, "photo", 4, 64 * 1024, 4 * 1024 * 1024),
        "backup-src": _seeded_files(rng, "mail", 3, 4 * 1024, 512 * 1024),
        "vm-disks": _seeded_files(rng, "note", 1, 1024, 4096),
    }
    return [
        (
            {"name": name, "kind": "zvol", "volsize": VOLSIZE, "files": []}
            if kind == "zvol"
            else {"name": name, "kind": "fs", "files": files[name]}
        )
        for name, kind in TREE_DATASETS
    ]


def _relative_plan_lived_in(seed, anchor):
    """The lived-in plan: pure function of (seed, anchor date)."""
    rng = random.Random(f"lived-in:{seed}")

    # Days only need uniqueness within a (dataset, label) family: a real
    # day sees a daily backup AND an offsite send on overlapping
    # datasets, so cross-family day sharing is authentic and keeps the
    # seeded windows starvation-free.
    used = {}

    def free_day(lo, hi, *keys):
        taken = set()
        for k in keys:
            taken |= used.get(k, set())
        d = _ordinary_day(rng, anchor, lo, hi, taken)
        for k in keys:
            used.setdefault(k, set()).add(d)
        return d

    p_daily = (PRIMARY_DS, "dailybackup")
    p_offsite = (PRIMARY_DS, "offsite")
    s_daily = (SECONDARY_DS, "dailybackup")
    s_offsite = (SECONDARY_DS, "offsite")

    # Shared day slots (a real backup moment snapshots many datasets at
    # once, so the two ladder datasets share calendar days).
    month_days = _month_firsts(anchor, PRIMARY_COUNTS["m"])
    week_days = _sundays(anchor, PRIMARY_COUNTS["w"])
    ord_days = [free_day(lo, hi, p_daily) for lo, hi in ((12, 45), (5, 11), (2, 4))]
    dup_day = free_day(2, 9, p_daily)
    clone_day = free_day(10, 18, (PRIMARY_DS, "clone"))

    # Offsite slots: two aged beyond the default s minage of 65 days
    # sharing a month (Phase-0 prey — removal-eligible), fresh protected
    # ones on both datasets.  The partner pick is bounded to days at
    # least 66 back (age > the 65-day minage): without the bound a
    # partner later in the shared month can land under the minage, and
    # the plan would only fail at stage time — after the lab is cloned.
    s_old_day1 = free_day(70, 100, p_offsite)
    s_old_day2 = _same_month_partner(
        rng,
        s_old_day1,
        used.get(p_offsite, set()) | {s_old_day1},
        min_age_date=anchor - dt.timedelta(days=66),
    )
    used.setdefault(p_offsite, set()).add(s_old_day2)
    s_fresh_days = [
        free_day(lo, hi, p_offsite) for lo, hi in ((30, 40), (20, 28), (12, 18), (5, 9))
    ]
    sec_s_days = [free_day(lo, hi, s_offsite) for lo, hi in ((46, 60), (22, 28), (6, 10))]
    sec_d_extra = [
        _ordinary_day(rng, anchor, lo, hi, used.get(s_daily, set()) | set(ord_days[:2]))
        for lo, hi in ((8, 11), (4, 7))
    ]
    used.setdefault(s_daily, set()).update(sec_d_extra)
    # The shared moments also count as the secondary's used days, so its
    # own picks can never re-land on them (identical-row collision).
    used.setdefault(s_daily, set()).update(ord_days[:2])

    # One logical backup moment = one (day, label) minute, shared across
    # datasets (the walk sets the clock once per moment).  Rows that
    # deliberately repeat a day (the same-day duplicate cluster) pass a
    # distinct mk so their names cannot collide — minutes stay unique
    # per (dataset, day) because zfssnapbuild names carry only minute
    # granularity.
    minute_pool = {}
    used_minutes = {}

    def minute_for(key, ds, day):
        if key in minute_pool:
            return minute_pool[key]
        for _ in range(5000):
            m = rng.randint(0, 1439)
            if m not in used_minutes.setdefault((ds, day), set()):
                minute_pool[key] = m
                used_minutes[(ds, day)].add(m)
                return m
        raise PlanError("minute pool exhausted (deterministic-plan fence)")

    def row(ds, day, label, bucket, hold="", mk=None):
        offset = (day - anchor).days
        if offset >= 0:
            raise PlanError(f"ladder point {day:%Y-%m-%d} must land before the anchor")
        if bucket != "c":
            assert_bucket_law(day, label, bucket)
        key = mk if mk is not None else (day, label)
        return {
            "day_offset": offset,
            "minute": minute_for(key, ds, day),
            "dataset": ds,
            "label": label,
            "bucket": bucket,
            "hold": hold,
        }

    # Offsite rows with their selective holds (a real offsite send holds
    # only what it shipped): four held rows across both datasets.
    offsite_slots = [(PRIMARY_DS, d) for d in (s_old_day1, s_old_day2, *s_fresh_days)] + [
        (SECONDARY_DS, d) for d in sec_s_days
    ]
    held_idx = set(rng.sample(range(len(offsite_slots)), k=HELD_OFFSITE_ROWS))
    hold_tags = {i: f"offsite-{rng.getrandbits(24):06x}" for i in held_idx}

    ladder = []
    # Primary: the over-retained headliner.
    for day in month_days:
        ladder.append(row(PRIMARY_DS, day, "dailybackup", "m"))
    for day in week_days:
        ladder.append(row(PRIMARY_DS, day, "dailybackup", "w"))
    for day in ord_days:
        ladder.append(row(PRIMARY_DS, day, "dailybackup", "d"))
    for i in range(SAMEDAY_DUPS):
        ladder.append(row(PRIMARY_DS, dup_day, "dailybackup", "d", mk=(dup_day, "dailybackup", i)))
    for i, (ds, day) in enumerate(offsite_slots):
        ladder.append(row(ds, day, "offsite", "s", hold_tags.get(i, "")))
    # Secondary: cross-dataset variety (shares the moments, extra days).
    for day in month_days[: SECONDARY_COUNTS["m"]]:
        ladder.append(row(SECONDARY_DS, day, "dailybackup", "m"))
    for day in week_days[: SECONDARY_COUNTS["w"]]:
        ladder.append(row(SECONDARY_DS, day, "dailybackup", "w"))
    for day in ord_days[:2] + sec_d_extra:
        ladder.append(row(SECONDARY_DS, day, "dailybackup", "d"))
    # The clone-bucket snapshot (zfsclone-vm's @clone-<ts>-c
    # convention); the clone directive reuses the row's moment.
    clone_row = row(PRIMARY_DS, clone_day, "clone", "c")
    ladder.append(clone_row)

    dailybackup = [
        {
            "day_offset": (day - anchor).days,
            "minute": minute_for((day, "dailybackup"), BACKUP_SRC_DS, day),
            "source": BACKUP_SRC_DS,
            "dest": RECV_DEST,
        }
        for day in (
            free_day(18, 24, (BACKUP_SRC_DS, "dailybackup")),
            free_day(2, 6, (BACKUP_SRC_DS, "dailybackup")),
        )
    ]
    clone = {
        "day_offset": clone_row["day_offset"],
        "minute": clone_row["minute"],
        "dataset": PRIMARY_DS,
        "target": CLONE_TARGET,
    }

    plan = {
        "datasets": _datasets(rng),
        "ladder": ladder,
        "dailybackup": dailybackup,
        "clone": clone,
    }
    _enforce_budget(plan)
    _enforce_shape(plan, s_old_day1, s_old_day2)
    return plan


def _payload_bytes(plan):
    return sum(f["bytes"] for d in plan["datasets"] for f in d["files"])


def _enforce_budget(plan):
    snapshots = len(plan["ladder"]) + len(plan["dailybackup"])
    if snapshots > MAX_SNAPSHOTS:
        raise PlanError(f"plan wants {snapshots} snapshots (max {MAX_SNAPSHOTS})")
    total = _payload_bytes(plan) + VOL_BYTES
    if total > MAX_PAYLOAD_BYTES:
        raise PlanError(f"plan wants {total} payload bytes (max {MAX_PAYLOAD_BYTES})")


def _enforce_shape(plan, s_old_day1, s_old_day2):
    """The plan-file shape contracts, made mechanical."""
    if s_old_day1.month != s_old_day2.month or s_old_day1 == s_old_day2:
        raise PlanError("offsite duplicate pair must share a month")
    prim = [r for r in plan["ladder"] if r["dataset"] == PRIMARY_DS]
    counts = {b: sum(1 for r in prim if r["bucket"] == b) for b in "dwms"}
    for bucket, want in PRIMARY_COUNTS.items():
        if counts[bucket] != want:
            raise PlanError(f"primary {bucket} count {counts[bucket]} != {want}")
    for bucket, retain in DEFAULT_RETAIN.items():
        if counts[bucket] <= retain:
            raise PlanError(f"primary {bucket} not over-retained ({counts[bucket]} <= {retain})")
    sec = [r for r in plan["ladder"] if r["dataset"] == SECONDARY_DS]
    sec_counts = {b: sum(1 for r in sec if r["bucket"] == b) for b in "dwms"}
    for bucket, want in SECONDARY_COUNTS.items():
        if sec_counts[bucket] != want:
            raise PlanError(f"secondary {bucket} count {sec_counts[bucket]} != {want}")
    d_days = [r["day_offset"] for r in prim if r["bucket"] == "d"]
    if not any(d_days.count(off) >= SAMEDAY_DUPS for off in set(d_days)):
        raise PlanError("no same-day duplicate cluster")
    if len(plan["dailybackup"]) != DAILYBACKUP_RUNS:
        raise PlanError("two zfsdailybackup run points are required")
    clones = [r for r in plan["ladder"] if r["bucket"] == "c"]
    if len(clones) != 1 or clones[0]["label"] != "clone":
        raise PlanError("exactly one clone-bucket row is required")
    if len({(r["dataset"], r["day_offset"], r["minute"]) for r in plan["ladder"]}) != len(
        plan["ladder"]
    ):
        raise PlanError("ladder rows collide per dataset")
    holds = [r["hold"] for r in plan["ladder"] if r["hold"]]
    if len(holds) != HELD_OFFSITE_ROWS or not all(h.startswith("offsite-") for h in holds):
        raise PlanError("selective offsite holds are missing or mis-tagged")


def relative_plan(variant, seed, anchor=None):
    """The plan document for (variant, seed, anchor).

    `anchor` is the staging epoch (int) the calendar slots are picked
    against; it is part of the plan's identity.  thin has no plan (its
    world is the playground); busy and unknown variants raise PlanError —
    busy is reserved for Phase 5.
    """
    variant = resolve_variant(variant)
    if variant == "thin":
        return None
    if variant == "busy":
        raise PlanError("world 'busy' is not implemented in this tree (Phase 5)")
    if anchor is None:
        raise PlanError("non-thin worlds need the staging anchor")
    anchor_date = dt.datetime.fromtimestamp(int(anchor), tz=dt.timezone.utc).date()
    return _relative_plan_lived_in(seed, anchor_date)


def world_digest(variant, seed, anchor=None):
    """Stable digest over the world plan document (universe_digest style).

    thin's document is the (variant, seed) pair alone — byte-identical to
    the Phase-1 formula — so thin digests stay valid as later phases
    extend non-thin documents with their plan rows.  Non-thin documents
    pin the anchor date as well: same seed, different staging date means
    a different (calendar-correct) world.
    """
    doc = {"seed": seed, "variant": variant}
    plan = relative_plan(variant, seed, anchor)
    if plan is not None:
        anchor_date = dt.datetime.fromtimestamp(int(anchor), tz=dt.timezone.utc).date()
        doc["anchor"] = anchor_date.isoformat()
        doc["plan"] = plan
    payload = json.dumps(doc, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:DIGEST_WIDTH]


# ---------------------------------------------------------------------------
# Epoch resolution + TSV emission
# ---------------------------------------------------------------------------


def _snap_ts(epoch):
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _row_name(row, epoch):
    if row["bucket"] == "c":
        return f"clone-{_snap_ts(epoch)}-c"
    return f"{row['label']}-{_snap_ts(epoch)}-{row['bucket']}"


def resolve_epochs(plan, anchor_epoch):
    """Concrete epochs + product names for every plan point.

    The anchor's UTC midnight is the base; day_offset * 86400 + minute*60
    gives each point its instant.  Returns a new structure (the relative
    plan stays pristine — it is the digest document).  The offsite pair's
    65-day minage observability is enforced here, against the anchor.
    """
    midnight = anchor_epoch - (anchor_epoch % DAY)

    def epoch_of(offset, minute):
        return midnight + offset * DAY + minute * 60

    rows = []
    for r in plan["ladder"]:
        row = dict(r)
        row["epoch"] = epoch_of(row["day_offset"], row["minute"])
        row["name"] = _row_name(row, row["epoch"])
        # The bucket law is anchor-relative (weekday/day-of-month), so it
        # is enforced here, against the resolved dates — the same check
        # world-stage.sh asserts against the product's own derivation.
        date = dt.datetime.fromtimestamp(row["epoch"], tz=dt.timezone.utc).date()
        if row["bucket"] != "c":
            assert_bucket_law(date, row["label"], row["bucket"])
        rows.append(row)
    dailybackup = []
    for d in plan["dailybackup"]:
        e = dict(d)
        e["epoch"] = epoch_of(e["day_offset"], e["minute"])
        dailybackup.append(e)
    clone = dict(plan["clone"])
    clone["epoch"] = epoch_of(clone["day_offset"], clone["minute"])

    # Retention's offsite minage (default 65 days): the aged pair (the
    # two oldest offsite rows by construction) must clear it at staging
    # time, or the minage gate is unobservable.
    anchor_date = dt.datetime.fromtimestamp(anchor_epoch, tz=dt.timezone.utc).date()
    ages = sorted(
        (
            (anchor_date - dt.datetime.fromtimestamp(r["epoch"], tz=dt.timezone.utc).date()).days
            for r in rows
            if r["label"] == "offsite" and r["dataset"] == PRIMARY_DS
        ),
        reverse=True,
    )
    if len(ages) < 2 or ages[1] <= 65:
        raise PlanError(f"offsite pair ages {ages[:2]} do not clear the 65d minage")
    return {
        "datasets": plan["datasets"],
        "ladder": rows,
        "dailybackup": dailybackup,
        "clone": clone,
        "anchor_epoch": anchor_epoch,
    }


def emit_ladder_tsv(resolved):
    """The walk script: '#'-directive header lines + one row per snapshot.

    Directives survey-lib.sh drives (dailybackup runs, the clone step)
    and world-stage.sh's tree builder both parse this single file; the
    {BASE}/{DS2BASE} placeholders are rendered to run-scratch names by
    survey-lib before the file is pushed into the guest.
    """
    out = [
        "# variant lived-in",
        f"# anchor {resolved['anchor_epoch']}",
    ]
    for d in resolved["datasets"]:
        if d["kind"] == "zvol":
            out.append(f"# dataset {{BASE}}/{d['name']} zvol {d['volsize']}")
        else:
            out.append(f"# dataset {{BASE}}/{d['name']} fs")
    for d in resolved["datasets"]:
        for f in d["files"]:
            out.append(f"# file {{BASE}}/{d['name']} {f['path']} {f['bytes']}")
    for e in resolved["dailybackup"]:
        out.append(f"# dailybackup {e['epoch']} {{BASE}}/{e['source']} {e['dest']}")
    c = resolved["clone"]
    out.append(f"# clone {c['epoch']} {{BASE}}/{c['dataset']} {c['target']}")
    for row in sorted(resolved["ladder"], key=lambda r: (r["epoch"], r["dataset"])):
        hold = row["hold"] or "-"
        out.append(
            f"{row['epoch']}\t{{BASE}}/{row['dataset']}\t{row['label']}"
            f"\t{row['bucket']}\t{hold}\t{row['name']}"
        )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="emit the plan JSON + ladder TSV")
    p_plan.add_argument("--variant", required=True)
    p_plan.add_argument("--seed", required=True)
    p_plan.add_argument("--anchor", type=int, help="staging anchor epoch (default: now)")
    p_plan.add_argument("--out-json", help="write the resolved plan JSON here")
    p_plan.add_argument("--out-tsv", help="write the ladder TSV here")

    p_dig = sub.add_parser("digest", help="print the world digest")
    p_dig.add_argument("--variant", required=True)
    p_dig.add_argument("--seed", required=True)
    p_dig.add_argument("--anchor", type=int, help="staging anchor epoch")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "digest":
            print(world_digest(args.variant, args.seed, args.anchor))
            return 0
        variant = resolve_variant(args.variant)
        if variant == "thin":
            print(f"digest {world_digest(variant, args.seed)}")
            print("snapshots 0")
            return 0
        anchor = args.anchor if args.anchor is not None else int(time.time())
        plan = relative_plan(variant, args.seed, anchor)
        resolved = resolve_epochs(plan, anchor)
        tsv = emit_ladder_tsv(resolved)
        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as f:
                json.dump(resolved, f, indent=1, sort_keys=True)
                f.write("\n")
        if args.out_tsv:
            with open(args.out_tsv, "w", encoding="utf-8") as f:
                f.write(tsv)
        print(f"digest {world_digest(variant, args.seed, anchor)}")
        print(f"snapshots {len(resolved['ladder']) + len(resolved['dailybackup'])}")
        print(f"payload_bytes {_payload_bytes(plan) + VOL_BYTES}")
        return 0
    except PlanError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
