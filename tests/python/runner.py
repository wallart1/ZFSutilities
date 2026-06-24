#!/usr/bin/env python3
"""Custom unittest runner matching the bash test harness output style."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"


class ColoredResult(unittest.TextTestResult):
    """unittest result class emitting colored PASS/FAIL/SKIP lines."""

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self._test_counter = 0

    def _write_status(self, test, label, color):
        self._test_counter += 1
        name = self._test_name(test)
        self.stream.write(f"  Test {self._test_counter}: {name}... ")
        self.stream.write(f"{color}{label}{NC}\n")
        self.stream.flush()

    def _test_name(self, test):
        if hasattr(test, "_testMethodName"):
            return test._testMethodName
        return str(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._write_status(test, "PASS", GREEN)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._write_status(test, "FAIL", RED)
        _, value, _ = err
        if value:
            for line in str(value).splitlines():
                self.stream.write(f"    Reason: {line}\n")

    def addError(self, test, err):
        super().addError(test, err)
        self._write_status(test, "FAIL", RED)
        _, value, _ = err
        if value:
            for line in str(value).splitlines():
                self.stream.write(f"    Reason: {line}\n")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._write_status(test, "SKIP", YELLOW)
        self.stream.write(f"    Reason: {reason}\n")

    def printErrors(self):
        pass


class ColoredRunner(unittest.TextTestRunner):
    resultclass = ColoredResult

    def run(self, test):
        result = self.resultclass(self.stream, self.descriptions, self.verbosity)
        result.failfast = self.failfast
        result.buffer = self.buffer
        result.tb_locals = self.tb_locals
        start_test_run = getattr(result, "startTestRun", None)
        if start_test_run is not None:
            start_test_run()
        try:
            test(result)
        finally:
            stop_test_run = getattr(result, "stopTestRun", None)
            if stop_test_run is not None:
                stop_test_run()
        return result


def _load_module(path):
    """Load a test module from file path."""
    name = os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def run_suite(suite, name):
    print("=" * 40)
    print(f"Running: {name}")
    print("=" * 40)
    runner = ColoredRunner(verbosity=0, stream=sys.stdout)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    if failed:
        print(f"{RED}  SUITE FAILED{NC} ({name})")
    else:
        print(f"{GREEN}  SUITE PASSED{NC} ({name})")
    print("")
    return passed, failed, skipped


def main(argv=None):
    argv = argv or sys.argv[1:]
    start_dir = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()

    requested = [a for a in argv if not a.startswith("-")]

    if requested:
        suites = []
        for name in requested:
            module_name = name if name.startswith("test_") else f"test_{name}"
            if not module_name.endswith(".py"):
                module_name += ".py"
            path = os.path.join(start_dir, module_name)
            if os.path.isfile(path):
                mod = _load_module(path)
                suites.append((module_name[:-3], loader.loadTestsFromModule(mod)))
            else:
                print(f"Module not found: {path}")
                return 1
    else:
        # Discover all test_*.py files
        files = sorted(
            f for f in os.listdir(start_dir)
            if f.startswith("test_") and f.endswith(".py") and f != "test_support.py"
        )
        suites = []
        for fname in files:
            mod = _load_module(os.path.join(start_dir, fname))
            suites.append((fname[:-3], loader.loadTestsFromModule(mod)))

    if not suites:
        print("No test suites found.")
        return 1

    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for name, suite in suites:
        p, f, s = run_suite(suite, name)
        total_passed += p
        total_failed += f
        total_skipped += s

    print("=" * 40)
    print("Overall Summary")
    print("=" * 40)
    print(f"  Suites:  {len(suites)}")
    print(f"  Passed:  {total_passed}")
    print(f"  Failed:  {total_failed}")
    if total_skipped:
        print(f"  Skipped: {total_skipped}")

    print("")
    if total_failed:
        print("Some test suites failed.")
        return 1
    print("All test suites passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
