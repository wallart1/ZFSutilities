# Repair Plans

A repair plan is the proposal that turns a `FINDINGS.md` entry into a
concrete change in the **dev repository**.  Product bugs are never fixed
inside guests — guests are disposable; the fix lands in the repo, ships in
a dev tarball, and is verified by rerunning the affected journey.

## Flow

```
FINDINGS.md entry (open)
  → repair-plans/NNN-slug.md   (drafted by the agent)
  → USER APPROVAL              (hard gate; may be covered by an explicit
                               standing approval for a repair campaign —
                               recorded in the finding's status cell)
  → execute in dev repo via the normal AGENTS.md workflow
  → build dev tarball, redeploy to guest (fresh or in-place)
  → rerun affected journeys → green → finding `verified`, plan closed
```

## File naming and contents

`NNN-slug.md`, where `NNN` is the next free number (match the FINDINGS.md
row).  A plan contains:

- **Finding**: ID + journey + run directory holding the raw evidence.
- **Root cause**: what actually failed, reproduced on the dev tree.
- **Proposed change**: dev-repo diff summary (files, behavior).
- **Blast radius**: affected suites, docs, installer behavior.
- **Verification**: which journeys rerun, expected results.

Plans for findings the user explicitly accepts (waives) are closed with
an `accepted` note instead of execution.
