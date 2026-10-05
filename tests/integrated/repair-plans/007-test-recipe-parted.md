# Repair Plan 007 — test-pool recipe assumes parted is installed

Finding: **F-007** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (covered by the user's standing repair approval).  Docs preamble added; journey Stage D mirrors the updated recipe.  Verification: J01 rerun.**
Evidence: results/run-20261005-140352-j01-fresh-install/guest-pools.log —

```
/root/itf-pools.sh: line 4: parted: command not found
```

— immediately after a fully successful single-node install (rc=0),
running the documented recipe verbatim.

## Root cause

The "Creating Local Test Pools" recipe in
`docs/docs/developer-guide/testing.md` begins directly with
`parted -s /dev/sdb mklabel gpt` (and later `partprobe`).  A fresh
Debian netinst system ships neither `parted` nor `partprobe`, and
neither is a ZFSutilities prerequisite (the product itself never calls
them — only this recipe does).  First-time followers of the recipe hit
`parted: command not found` with no hint.

## Proposed change

Docs-only: add one preamble line to the recipe's code block (before
`mklabel`):

```bash
# parted/partprobe are not part of a base Debian install.
apt-get install -y parted
```

Files touched: `docs/docs/developer-guide/testing.md`.

## Verification

1. Docs suites (anchors/build) stay green.
2. J01 rerun once F-007 is approved: the journey's Stage D script
   mirrors the recipe verbatim, so with the preamble in place (journey
   updated to match the recipe) the three pools are created and the
   journey reaches full green for the first time.
