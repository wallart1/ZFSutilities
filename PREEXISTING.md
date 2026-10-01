# This file is maintained by Kimi Code. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- 2026-10-01 (repo): `ScrubQueue.__init__` only applies the caller's `target`
  argument when no `scrub_state.json` exists yet; when prior state exists,
  `_load()` overwrites `self.target` with the persisted value. As a result,
  `run_scrub_profile()`'s `simultaneous` profile setting is silently ignored
  on any system with existing scrub state, while the profile still logs
  "Scrub profile started on N pool(s), target={simultaneous}" — the logged
  target may not be the one actually used. Discovered during the
  scrub-state root-cause audit; not resolved (code freeze).
