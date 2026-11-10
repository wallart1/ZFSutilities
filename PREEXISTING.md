# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## test-sever-vm-clone: one-off bare-assert flake in the full gate (2026-11-10)

- Full-gate run 2026-11-10 09:00 (message-wording task): Test 16 ("phase-1
  engine failure: the parent prints resume guidance and leaks no results
  file") hit a bare sub-assert `FAIL Reason: Expected '0', got '1'`;
  suite verdict 25/26.
- The suite passes alone (26/26, 0 failed) and the two earlier full-gate
  runs the same day were green, so this is a one-off, not a steady
  failure; cause not yet isolated (nothing in that task touched the
  sever-vm-clone surface).

---

## GLOSSARY.md: `mock` sits after `mount namespace` (2026-11-10)

- The file's own law is case-insensitive alphabetical order; `mock`
  (< `mount namespace`, "moc" < "mou") has sat below it since before the
  0.140.0 cycle (present in the 0871a06 base, both lanes, and the
  merged tree). Found during the 0.140.0 pub2-lane merge's order check,
  which fixed the merge-introduced `function survey`/`full gate` pair;
  this pre-existing pair was left for its own cue.

---
