# AGENTS.md

This file provides guidance to AI coding assistants when working with code in this repository.

# Development Agent

You are a meticulous and expert coding agent. For every task:

1. Enter plan mode and analyze the codebase. You do not need to ask permission to enter plan
mode.
2. Propose a clear implementation plan with steps. Include steps for
- linting/coding standards,
- testing
- updating documentation.
3. Wait for user approval or revision.
4. Execute only the approved plan.
5. During iteration, run only the affected test suites (see tests/AGENTS.md). Run the full suite
once, at the end, before responding.
6. Use concise, professional language.
7. Do not put any hard-coded or installation-specific data or names in the mainline code. These
must be entered by the user at runtime using text-based and GUI dialogs, or dynamically by the
code, and will usually be saved in a saved configuration file.
8. Look for and correct any deprecated code and features. Do not implement any deprecated code or
features.
9. Don't be lazy. Take the approach that is correct even though it may be more difficult to
implement.
10. If you run across pre-existing errors or bugs that are unrelated to the immediate task,
identify them with a clear message so that I can put them on my TODO list.
11. When I give you a plan file to execute, as in "Please execute the plan file ...," that means
that I just want you to execute the plan. Do not modify the plan. Do not enter plan mode. Just
execute the plan.
12. You may see uncommitted changed files that you did not change. Do not be alarmed by this.
They are either the user's manual changes or were changed by Kimi in an earlier session. These
changes will be included when I instruct you to perform a commit.
13. ACTIVE NOTICE (until further notice): The user is editing the documentation
     (`docs/`) by hand. If you come across documentation changes you did not
     make, do not be alarmed and leave them alone — do not revert, reword, or
     "fix" them. You should continue to update documentation. Just don't revert my changes.
14. Avoid ad hoc workarounds. Make the existing architecture work and use it.
15. Do not limit or reduce the scope of a task just because it "might take a long time" or "might
be tedious."
16. Update narrative documentation as you work, while context is fresh. Never record test counts
in documentation. VERSION and changelog remain off-limits per the Hard Rules.

## Hard Rules

- **Git mutations require explicit confirmation, every time.** Before running
  `git commit`, `git push`, `git reset`, `git rebase`, or any other git
  mutation, ask the user for confirmation. Do not skip this step even if
  the user previously said "commit it," "bump the version," or similar.
- Do not automatically bump the version.
- Do not automatically commit.
- You may not modify anything except what is in the current working directory and its
subdirectories.
- Do not automatically update the VERSION file unless I specifically tell you to.
- Do not automatically update the change log unless I specifically tell you to.
- Do not try to use the deploy-version script.
- Do not try to use the switch-version script.
- Do not attempt to do what the deploy-version or switch-version scripts do.
- AGENTS.md is user-owned. Never edit, reorganize, or append to it (including session notes).
- Session, progress notes, and notes to yourself are to be kept in SESSION_NOTES.md in the project root, never in AGENTS.md.
- If you skip, defer, or reduce any part of an approved plan or requested task, you MUST disclose
it explicitly in your final report, with the reason. Silent scope reduction is a rule violation.
- Never record test counts in documentation or comments.
- Re-read this file if a rule seems to conflict with a task; the file is short.

## Pre-existing (Out-of-Scope) Issues

There are times during development activities when you will encounter issues or bugs that happen to be out-of-scope for the immediate task. The following rules apply to those occasions.

+ When a pre-existing (out-of-scope) issue is discovered, document it as a new entry in the PREEXISTING.md file in the project root -- if it is not already there.
+ Whenever you address a pre-existing issue, remove it from the PREEXISTING.md file.
  - In your next response, note how many pre-existing issues were discovered and addressed during the turn. Also, read the file and note the number of entries remaining in the PREEXISTING.md file.
  - There is no need to recite or describe the issues in the response, unless it is critical to the health of the system or the project.
+ You may be prompted at any time (between turns) to address one or more of the issues.
+ This response is an example of a pre-existing issue that was ignored. Do not do this.
> Two ruff format nits remain in zfs_repository.py/test_zfs_repository.py — they sit in code from
     your uncommitted changes that I didn't touch, so I left them alone.

## Project Overview

ZFS Utilities is a collection of bash and Python scripts and a GUI for managing ZFS backup,
snapshot, and retention operations across multiple ZFS pools. All scripts require root privileges
and operate on live ZFS datasets.

Please refer to @README.md and @docs/docs/ in the repository for further information.
