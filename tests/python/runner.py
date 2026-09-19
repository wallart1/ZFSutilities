#!/usr/bin/env python3
"""Deprecated shim — the Python test suites now run under pytest.

This module previously implemented a custom unittest runner. It now forwards
to ``python3 -m pytest`` so existing invocations keep working:

    python3 runner.py                      # -> pytest tests/python
    python3 runner.py test_backup_config   # -> pytest tests/python/test_backup_config.py
    python3 runner.py --list              # -> pytest --collect-only -q
    python3 runner.py --count             # Alias for --list

Prefer calling pytest directly (see docs/docs/developer-guide/testing.md);
this shim exists only for muscle memory and older documentation.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.realpath(os.path.join(_HERE, "..", ".."))


def _translate_args(argv):
    """Map legacy runner.py arguments to pytest arguments."""
    pytest_args = []
    targets = []
    count_mode = False
    verbosity = []
    for arg in argv:
        if arg in ("--list", "--count"):
            count_mode = True
        elif arg in ("-q", "--quiet"):
            pytest_args.append("-q")
        elif arg in ("-v", "--verbose"):
            verbosity.append("-v")
        elif arg in ("-b", "--buffer"):
            # pytest captures output per test by default; -b has no equivalent.
            pass
        elif arg == "--failures-only":
            # No exact pytest equivalent; -q prints only failures plus summary.
            pytest_args.append("-q")
        elif arg.startswith("-"):
            pytest_args.append(arg)
        else:
            name = arg
            if not name.startswith("test_"):
                name = f"test_{name}"
            if not name.endswith(".py"):
                name += ".py"
            targets.append(os.path.join("tests", "python", name))

    if count_mode:
        return ["--collect-only", "-q"] + targets

    result = verbosity or pytest_args or ["-q"]
    if verbosity and pytest_args:
        result = verbosity + pytest_args
    if targets:
        result = targets + ["-x", "--tb=short"] + result
    else:
        result = ["tests/python", "-n", "auto"] + result
    return result


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    print(
        "runner.py is deprecated: forwarding to pytest. Use "
        "`python3 -m pytest tests/python` directly.",
        file=sys.stderr,
    )
    os.chdir(_REPO_ROOT)
    os.execvp(
        "python3",
        ["python3", "-m", "pytest"] + _translate_args(argv),
    )


if __name__ == "__main__":
    main()
