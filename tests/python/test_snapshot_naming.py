"""Tests for snapshot_naming.py — the canonical UTC+Z snapshot-name rules.

Also pins the python helpers against the bash twin (snapname_timestamp in
bin/bashinit) on an epoch matrix: the epoch form of the bash helper is
deterministic and timezone-independent, so both implementations can be
compared directly.  The bucket-rule cross-check (which needs the bash test
mock) lives in tests/test-snapshot-names.
"""

import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from typing import ClassVar

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from snapshot_naming import bucket_for, snapshot_timestamp


class TestSnapshotTimestamp(unittest.TestCase):
    def test_aware_datetime_renders_utc_z(self):
        when = datetime(2026, 10, 6, 21, 46, tzinfo=timezone(timedelta(hours=-4)))
        self.assertEqual(snapshot_timestamp(when), "2026-10-07T01:46Z")

    def test_utc_datetime_renders_z(self):
        when = datetime(2026, 10, 7, 1, 46, tzinfo=timezone.utc)
        self.assertEqual(snapshot_timestamp(when), "2026-10-07T01:46Z")

    def test_naive_datetime_is_local_assumed(self):
        # Naive datetimes carry no offset; the helper interprets them as
        # local time.  Whatever the zone, the rendering is still Z-form.
        name = snapshot_timestamp(datetime(2026, 10, 7, 1, 46))
        self.assertRegex(name, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")

    def test_now_renders_z(self):
        self.assertRegex(snapshot_timestamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$")

    def test_output_is_zfs_name_legal(self):
        # "+" is illegal in ZFS snapshot names; the Z form must never embed
        # an ISO offset.
        when = datetime(2026, 10, 7, 1, 46, tzinfo=timezone.utc)
        self.assertNotIn("+", snapshot_timestamp(when))


class TestBucketFor(unittest.TestCase):
    def test_monthly_on_first(self):
        when = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(bucket_for(when), "m")

    def test_monthly_wins_when_first_is_sunday(self):
        when = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(bucket_for(when), "m")

    def test_weekly_on_sunday(self):
        when = datetime(2026, 10, 11, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(bucket_for(when), "w")

    def test_daily_otherwise(self):
        when = datetime(2026, 10, 7, 1, 46, tzinfo=timezone.utc)
        self.assertEqual(bucket_for(when), "d")

    def test_offsite_label_shortcircuits(self):
        when = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(bucket_for(when, "offsite"), "s")
        self.assertEqual(bucket_for(when, "@offsite"), "s")

    def test_bucket_follows_utc_not_local(self):
        # Local Saturday 23:30 New York is already UTC Sunday: one clock.
        new_york = timezone(timedelta(hours=-4))
        when = datetime(2026, 10, 10, 23, 30, tzinfo=new_york)
        self.assertEqual(bucket_for(when), "w")

    def test_naive_datetime_is_local_assumed(self):
        name = bucket_for(datetime(2026, 10, 7, 1, 46))
        self.assertIn(name, ("d", "w", "m", "s"))


class TestBashTwinParity(unittest.TestCase):
    """python snapshot_timestamp == bash snapname_timestamp, per epoch."""

    EPOCHS: ClassVar[list[int]] = [
        1790824020,  # 2026-10-01T03:07Z — UTC 1st (monthly)
        1790885220,  # 2026-10-01T20:07Z — same UTC day, other side of noon
        1791262600,  # 2026-10-06T04:56Z — ordinary Wednesday
        1791342600,  # 2026-10-07T03:10Z — ordinary Wednesday, later
        1791517200,  # 2026-10-09T03:40Z — Friday
        1791709800,  # 2026-10-11T09:10Z — UTC Sunday (weekly)
        1792219200,  # 2026-10-17T07:20Z — Saturday
        1792313700,  # 2026-10-18T09:35Z — UTC Sunday (weekly)
        1772958300,  # 2026-03-08T07:05Z — US DST spring-forward Sunday
        1793559300,  # 2026-11-01T06:15Z — fall-back Sunday on the 1st
    ]

    def _bash_snapname_timestamp(self, epoch, tz):
        result = subprocess.run(
            ["bash", "-c", f'source "{REPO_ROOT}/bin/bashinit"; snapname_timestamp {epoch}'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**os.environ, "TZ": tz},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_epoch_matrix_matches_bash(self):
        for tz in ("UTC", "America/New_York", "Asia/Tokyo"):
            for epoch in self.EPOCHS:
                with self.subTest(tz=tz, epoch=epoch):
                    when = datetime.fromtimestamp(epoch, timezone.utc)
                    self.assertEqual(
                        snapshot_timestamp(when),
                        self._bash_snapname_timestamp(epoch, tz),
                    )


if __name__ == "__main__":
    unittest.main()
