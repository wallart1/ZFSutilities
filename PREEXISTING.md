# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- tests/test-unarchive-vm Test 25 ("Unknown METHOD value is fatal") fails
  under full-suite load (2026-11-17 wrap-up run): the child FATALs earlier at
  the "Not a ZFS dataset" mock-state probe (unarchive-vm:282, old code) so the
  unknown-method FATAL never fires. Rerun-green alone (43/43); the same suite
  flaked once in the pub3 0.142.0 gate run the same week. Load-sensitive mock
  state setup, unrelated to the 0.142.0 campaigns.
