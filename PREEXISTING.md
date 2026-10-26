# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (toolchain deprecation, docs build): `mkdocs build -f docs/mkdocs.yml`
  prints a mkdocs-material WARNING — "MkDocs 2.0 is incompatible with
  Material for MkDocs" — on every build (exit 0, site still builds cleanly).
  Action is a toolchain decision (pin mkdocs <2 vs migrate to Zensical),
  already analyzed in SESSION_NOTES.md's Zensical thread; recorded here so
  it can be prompted for a decision. Not resolved (code freeze).
  Zensical is under development. We are waiting for a 1.x.x release.
  (Rechecked 2026-10-08: PyPI shows 0.0.69; still no 1.x.
  Rechecked 2026-10-10: unchanged, 0.0.69.
  Rechecked 2026-10-11: unchanged, 0.0.69.
  Reconfirmed 2026-10-11 (user): keep waiting for 1.x.
  Rechecked 2026-10-12: 0.0.70; still no 1.x.)
  (Rechecked 2026-10-13: unchanged, 0.0.70.)
  (Rechecked 2026-10-16: 0.0.71; still no 1.x.)
  (Rechecked 2026-10-22: unchanged, 0.0.71.)
  (Rechecked 2026-10-22 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 wrap-up: unchanged, 0.0.71 — no 1.x; hold stands.
  Rechecked 2026-10-23 (itf cycle): 0.0.72 — first movement since 10-16,
  still no 1.x; hold stands. The mkdocs<2 pin remains the documented
  product stance — doc-server.md and messages/index.md carry it.
  Rechecked 2026-10-24 wrap-up: unchanged, 0.0.72 — no 1.x; hold stands.
  Rechecked 2026-10-25 wrap-up: unchanged, 0.0.72 — no 1.x; hold stands.
  Rechecked 2026-10-26 wrap-up: 0.0.73 — still no 1.x; hold stands.)

