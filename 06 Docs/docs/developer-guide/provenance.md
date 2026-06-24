# Development Provenance

Significant portions of this project were developed by
[Claude Code](https://www.claude.com/product/claude-code), Anthropic's
command-line AI coding agent, working under the direct supervision of the
project maintainer. Every change produced by the agent was reviewed, tested,
and accepted by a human before being incorporated into the codebase.

## AI Models Used

Development used Anthropic's Claude models, primarily:

- **Claude Opus 4.6** — most implementation work, architecture decisions
- **Claude Sonnet 4.6** — routine edits, exploration, code review
- **Claude Haiku 4.5** — quick lookups and short-form tasks

Model selection was made per-task based on complexity.

## Claude Code

Claude Code is available from Anthropic:

- **Website:** <https://www.claude.com/product/claude-code>
- **Install (CLI):** `npm install -g @anthropic-ai/claude-code`
- **Documentation:** <https://docs.claude.com/en/docs/claude-code>

Claude Code runs as a terminal CLI and is also available as a desktop app
(Mac/Windows), a web app at <https://claude.ai/code>, and IDE extensions for
VS Code and JetBrains.

## CLAUDE Files in the Distribution

The distribution includes project-specific instruction files that Claude
Code reads when operating on this codebase:

| File                     | Purpose                                              |
| ------------------------ | ---------------------------------------------------- |
| `CLAUDE.md`              | Top-level project context and conventions            |
| `AGENTS.md`              | Guidance for AI coding assistants                    |
| `08 Two-node/CLAUDE.md`  | Two-node infrastructure background                   |

These files are shipped with the project so that anyone running Claude Code
against the repository gets the same working context the maintainer uses.
They are plain Markdown and can be read directly by humans as a
supplementary reference to this documentation.
