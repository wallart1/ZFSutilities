"""Tests for golden.py — canonical form, compare, update, and missing paths."""

import golden
import pytest


class _GoldenStub:
    """Minimal testcase double exposing what golden.py reads.

    Records skipTest calls instead of raising so tests can assert on them.
    The class lives in this module, so ``type(stub).__module__`` is
    "test_golden" and golden_path() resolves under the patched root.
    """

    def __init__(self, method_name="stub_method"):
        self._testMethodName = method_name
        self.skips = []

    def skipTest(self, msg):
        self.skips.append(msg)


@pytest.fixture
def golden_root(tmp_path, monkeypatch):
    """Point golden.py at a scratch directory so no real goldens are touched."""
    monkeypatch.setattr(golden, "_GOLDEN_ROOT", tmp_path)
    return tmp_path


def _write_golden(stub, text):
    path = golden.golden_path(stub)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_canonical_list_is_one_element_per_line():
    assert golden._canonical(["a", "b", "c"]) == "a\nb\nc\n"


def test_canonical_list_strips_extra_blank_elements():
    assert golden._canonical(["a", ""]) == "a\n"


def test_canonical_string_normalizes_trailing_newlines():
    assert golden._canonical("hello\n\n") == "hello\n"


def test_golden_path_uses_module_class_and_method_names(golden_root):
    stub = _GoldenStub("some_method")
    assert (
        golden.golden_path(stub)
        == golden_root / "test_golden" / "_GoldenStub.some_method.golden"
    )


def test_compare_passes_when_golden_matches(golden_root):
    stub = _GoldenStub()
    _write_golden(stub, "a\nb\n")
    golden.check(stub, ["a", "b"])


def test_compare_raises_unified_diff_on_mismatch(golden_root):
    stub = _GoldenStub()
    _write_golden(stub, "a\nb\n")
    with pytest.raises(AssertionError) as excinfo:
        golden.check(stub, ["a", "c"])
    message = str(excinfo.value)
    assert "--- " in message
    assert "+++ " in message
    assert "-b" in message
    assert "+c" in message


def test_missing_golden_names_creating_command(golden_root):
    stub = _GoldenStub()
    with pytest.raises(AssertionError, match="UPDATE_GOLDEN=1 tests/run-tests test_golden"):
        golden.check(stub, ["a"])


def test_update_rewrites_changed_golden_and_skips(golden_root, monkeypatch):
    stub = _GoldenStub()
    path = _write_golden(stub, "old\n")
    monkeypatch.setenv("UPDATE_GOLDEN", "1")
    golden.check(stub, ["new"])
    assert path.read_text() == "new\n"
    assert stub.skips == ["golden updated: _GoldenStub.stub_method"]


def test_update_creates_missing_golden_and_skips(golden_root, monkeypatch):
    stub = _GoldenStub()
    monkeypatch.setenv("UPDATE_GOLDEN", "1")
    golden.check(stub, ["a", "b"])
    assert golden.golden_path(stub).read_text() == "a\nb\n"
    assert len(stub.skips) == 1


def test_update_leaves_identical_golden_untouched(golden_root, monkeypatch):
    stub = _GoldenStub()
    path = _write_golden(stub, "a\nb\n")
    before = path.stat().st_mtime_ns
    monkeypatch.setenv("UPDATE_GOLDEN", "1")
    golden.check(stub, ["a", "b"])
    assert path.read_text() == "a\nb\n"
    assert path.stat().st_mtime_ns == before
    assert stub.skips == []
