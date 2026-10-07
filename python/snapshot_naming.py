"""Snapshot-name timestamp and bucket rules (single Python source of truth).

Snapshot names embed the instant they were taken as ``YYYY-MM-DDTHH:MMZ`` —
UTC with a literal ``Z`` suffix.  The ``+HH:MM`` offsets ISO-8601 would emit
are illegal in ZFS snapshot names (``+`` is not in the dataset-name charset
west of UTC renders ``-HH:MM`` which is legal, which is why the old
``date -Iminutes`` names only failed on UTC and east-of-UTC hosts).  GNU
``date -d`` and Python 3.11+ ``datetime.fromisoformat`` both parse the ``Z``
form natively, so consumers stay format-agnostic.

Names created before this convention embed a local offset (e.g.
``2026-07-14T11:23-04:00``); they are valid forever and no migration is
planned — destroying and recreating a snapshot to "fix" its name loses the
snapshot's identity.  Every consumer must accept both forms.

The bash twin of these helpers lives in ``bin/bashinit``
(``snapname_timestamp``); ``tests/python/test_snapshot_naming.py`` pins the
two implementations to identical output.
"""

from __future__ import annotations

from datetime import datetime, timezone


def snapshot_timestamp(when: datetime | None = None) -> str:
    """Return the snapshot-name timestamp for *when* (now if None).

    Aware datetimes are converted to UTC; naive datetimes are interpreted
    as local time first.  The rendered ``…Z`` string is always UTC so the
    same instant produces the same name on hosts in different zones.
    """
    dt = when if when is not None else datetime.now()
    if dt.tzinfo is None:
        # Naive datetimes are assumed to be local time.
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def bucket_for(when: datetime | None = None, label: str = "dailybackup") -> str:
    """Return the retention-bucket letter for *when* under *label*.

    One clock: the bucket follows the UTC instant encoded in the name, the
    same rule the bash ``zfssnapbuild`` applies.  A run within the offset
    hours around local midnight can therefore land in a different bucket
    than the local calendar day suggests (Sat 20:00 America/New_York is
    already Sunday UTC → ``w``); the Schedule page surfaces that edge.

    Precedence: ``offsite`` label → ``s``; UTC 1st of month → ``m``;
    UTC Sunday → ``w`` (monthly wins when the 1st falls on a Sunday);
    otherwise ``d``.
    """
    dt = when if when is not None else datetime.now()
    if dt.tzinfo is None:
        dt = dt.astimezone()
    dt = dt.astimezone(timezone.utc)
    if label.lstrip("@") == "offsite":
        return "s"
    if dt.strftime("%d") == "01":
        return "m"
    if dt.strftime("%a") == "Sun":
        return "w"
    return "d"
