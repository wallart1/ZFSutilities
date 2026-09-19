"""Tests for MkDocs documentation integrity — nav, links, hooks, anchors,
and AGENTS.md reference integrity (repo-relative paths and branch names)."""

import importlib.util
import os
import re
import subprocess
import unittest

from test_support import (
    DOCS_DIR,
    MKDOCS_YML,
    PYTHON_SRC,
    REPO_ROOT,
    check_pyyaml,
    collect_nav_files,
    extract_command_script_names,
    extract_markdown_headers,
    extract_markdown_links,
    extract_python_module_names,
    list_all_md_files,
    resolve_relative_link,
)

# --- AGENTS.md reference validation -----------------------------------------
#
# Existence semantics: a candidate reference passes if it exists on disk under
# REPO_ROOT. A candidate that does not exist passes only when git ignores it
# (generated content such as docs/site/, which is absent on fresh clones);
# everything else is a failure reported as "source:line: token". Candidates
# starting with an AUTHOR_MACHINE_ALLOWLIST entry are reported as allowlisted,
# never failed. Placeholder tokens (containing <...>) are validated by their
# longest literal repo-relative parent directory.
#
# Candidates are extracted from inline code spans and from prose. A prose
# token qualifies as repo-relative when it starts with a known top-level
# directory prefix (bin/, lib/, python/, tests/, docs/, share/) or ends in a
# known file extension; a bare token qualifies when it names a known root
# file. This classification (not extension alone) is what keeps pool names
# (threeamigos/proxmox), host roles (storage/compute), and generic noun pairs
# (pool/dataset, zfs/zpool) from being treated as paths. MIN_ROOT_CANDIDATES
# is an extraction floor so a broken regex cannot degrade the suite to a
# vacuous pass.

AGENTS_MD_FILES = [
    os.path.join(REPO_ROOT, "AGENTS.md"),
    os.path.join(REPO_ROOT, "tests", "AGENTS.md"),
]

KNOWN_TOP_LEVEL_PREFIXES = ("bin/", "lib/", "python/", "tests/", "docs/", "share/")

KNOWN_ROOT_FILES = frozenset(
    {
        "AGENTS.md",
        "README.md",
        "VERSION",
        "LICENSE",
        "pyproject.toml",
        ".shellcheckrc",
        "SESSION_NOTES.md",
    }
)

KNOWN_FILE_EXTENSIONS = (".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".json", ".txt")

MIN_ROOT_CANDIDATES = 10

AUTHOR_MACHINE_ALLOWLIST = ("/NFS1/",)

BRANCH_ALLOWLIST = frozenset()

BRANCH_RE = re.compile(r"Branch:\s*([A-Za-z0-9._/-]+)")

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

_PROSE_TOKEN_RE = re.compile(r"(?<![\w/@.~$-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.+*<>-]+)+)")

_PLACEHOLDER_RE = re.compile(r"[<*[]")


def _strip_fenced_blocks(text):
    return _FENCE_RE.sub("", text)


def _clean_token(token):
    return token.strip().lstrip("@").rstrip(".,);:]}>")


def _extract_candidates(text):
    """Extract (line_no, token) repo-relative reference candidates."""
    text = _strip_fenced_blocks(text)
    candidates = []
    seen = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        for span in re.findall(r"`([^`]+)`", line):
            # Command strings like `tests/run-tests test-<name>` are skipped
            # here; the prose pass below still picks up the path sub-token.
            if re.search(r"\s", span):
                continue
            token = _clean_token(span)
            if "/" in token and not token.startswith(("/", "~")):
                candidates.append((line_no, token))
        for match in _PROSE_TOKEN_RE.finditer(line):
            token = _clean_token(match.group(1))
            if token.startswith(KNOWN_TOP_LEVEL_PREFIXES) or token.endswith(
                KNOWN_FILE_EXTENSIONS
            ):
                candidates.append((line_no, token))
        for fname in KNOWN_ROOT_FILES:
            if re.search(r"(?<![\w./-])" + re.escape(fname) + r"(?![\w/-])", line):
                candidates.append((line_no, fname))
    unique = []
    for line_no, token in candidates:
        if (line_no, token) not in seen:
            seen.add((line_no, token))
            unique.append((line_no, token))
    return unique


def _is_git_ignored(rel_path):
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "check-ignore", "-q", "--", rel_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _local_branch_exists(name):
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "branch", "--list", name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _resolve_candidate(token):
    """Classify one candidate: ok / problem / ignored / allowlisted."""
    if token.startswith(AUTHOR_MACHINE_ALLOWLIST):
        return "allowlisted", token
    if _PLACEHOLDER_RE.search(token):
        # Validate the longest literal repo-relative parent directory:
        # tests/python/test_<name>.py requires tests/python/ to exist.
        literal = _PLACEHOLDER_RE.split(token)[0].rstrip("/")
        parent = os.path.dirname(literal) or literal
        full = os.path.join(REPO_ROOT, parent)
        if os.path.isdir(full):
            return "ok", parent + "/"
        return "problem", f"placeholder parent directory missing: {parent}/"
    full = os.path.join(REPO_ROOT, token)
    if os.path.exists(full):
        return "ok", token
    if _is_git_ignored(token):
        return "ignored", token
    return "problem", "no such file or directory (and not git-ignored)"


def _validate_agents_md_text(text, source_label):
    """Validate one AGENTS.md text. Returns (problems, ignored, allowlisted,
    candidates)."""
    problems, ignored, allowlisted = [], [], []
    candidates = _extract_candidates(text)
    for line_no, token in candidates:
        status, detail = _resolve_candidate(token)
        if status == "problem":
            problems.append(f"{source_label}:{line_no}: '{token}' -> {detail}")
        elif status == "ignored":
            ignored.append(token)
        elif status == "allowlisted":
            allowlisted.append(token)
    return problems, ignored, allowlisted, candidates


def _validate_branch_mentions(text, source_label):
    """Every 'Branch: <name>' mention must name a local branch or be allowlisted."""
    problems = []
    for line_no, line in enumerate(_strip_fenced_blocks(text).splitlines(), 1):
        for match in BRANCH_RE.finditer(line):
            name = match.group(1)
            if name not in BRANCH_ALLOWLIST and not _local_branch_exists(name):
                problems.append(
                    f"{source_label}:{line_no}: 'Branch: {name}' -> "
                    "no such local branch (and not allowlisted)"
                )
    return problems


class TestMkDocsYml(unittest.TestCase):
    def setUp(self):
        check_pyyaml()
        import yaml

        yaml.SafeLoader.add_constructor(
            "tag:yaml.org,2002:python/name:pymdownx.superfences.fence_code_format",
            lambda loader, node: "pymdownx.superfences.fence_code_format",
        )
        with open(MKDOCS_YML) as f:
            self.config = yaml.safe_load(f)

    def test_site_name_present(self):
        self.assertIn("site_name", self.config)
        self.assertTrue(self.config["site_name"])

    def test_docs_dir_exists(self):
        docs_dir = self.config.get("docs_dir", "docs")
        full_path = os.path.join(os.path.dirname(MKDOCS_YML), docs_dir)
        self.assertTrue(os.path.isdir(full_path), f"docs_dir does not exist: {full_path}")

    def test_all_nav_entries_exist(self):
        nav = self.config.get("nav", [])
        nav_files = collect_nav_files(nav)
        self.assertGreater(len(nav_files), 0)
        for rel_path in nav_files:
            with self.subTest(file=rel_path):
                full = os.path.join(DOCS_DIR, rel_path)
                self.assertTrue(os.path.isfile(full), f"Nav entry missing: {rel_path}")

    def test_no_orphan_md_files(self):
        """Every .md file under docs/ should be reachable via nav."""
        nav = self.config.get("nav", [])
        nav_files = set(collect_nav_files(nav))
        all_files = set(list_all_md_files())
        # Some files may be intentionally unlisted (e.g. messages/index.md is listed)
        orphans = all_files - nav_files
        if orphans:
            self.fail(f"Orphan markdown files not in nav: {sorted(orphans)}")


class TestMarkdownLinks(unittest.TestCase):
    def test_all_internal_links_resolve(self):
        failures = []
        for root, _dirs, files in os.walk(DOCS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                filepath = os.path.join(root, fname)
                source_dir = os.path.dirname(filepath)
                links = extract_markdown_links(filepath)
                for link in links:
                    resolved = resolve_relative_link(source_dir, filepath, link)
                    if resolved is None:
                        continue  # external/absolute link
                    if not os.path.isfile(resolved):
                        rel_src = os.path.relpath(filepath, DOCS_DIR)
                        failures.append(f"{rel_src}: '{link}' -> missing file '{resolved}'")
        if failures:
            self.fail("Broken internal links found:\n  " + "\n  ".join(failures))

    def test_no_links_escape_docs_dir(self):
        failures = []
        for root, _dirs, files in os.walk(DOCS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                filepath = os.path.join(root, fname)
                source_dir = os.path.dirname(filepath)
                links = extract_markdown_links(filepath)
                for link in links:
                    resolved = resolve_relative_link(source_dir, filepath, link)
                    if resolved is None:
                        continue
                    real = os.path.realpath(resolved)
                    if not real.startswith(os.path.realpath(DOCS_DIR)):
                        rel_src = os.path.relpath(filepath, DOCS_DIR)
                        failures.append(f"{rel_src}: '{link}' escapes docs dir")
        if failures:
            self.fail("Links escaping docs/ found:\n  " + "\n  ".join(failures))

    def test_all_internal_anchors_exist(self):
        failures = []
        for root, _dirs, files in os.walk(DOCS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                filepath = os.path.join(root, fname)
                source_dir = os.path.dirname(filepath)
                links = extract_markdown_links(filepath)
                for link in links:
                    if "#" not in link:
                        continue
                    resolved = resolve_relative_link(source_dir, filepath, link)
                    if resolved is None:
                        continue
                    if not os.path.isfile(resolved):
                        continue  # already caught by file test
                    anchor = link.split("#", 1)[1]
                    headers = extract_markdown_headers(resolved)
                    if anchor.lower() not in headers:
                        rel_src = os.path.relpath(filepath, DOCS_DIR)
                        rel_tgt = os.path.relpath(resolved, DOCS_DIR)
                        failures.append(f"{rel_src}: anchor '{anchor}' not found in {rel_tgt}")
        if failures:
            self.fail("Broken anchors found:\n  " + "\n  ".join(failures))


class TestMkDocsHooks(unittest.TestCase):
    def test_hooks_exist(self):
        check_pyyaml()
        import yaml

        yaml.SafeLoader.add_constructor(
            "tag:yaml.org,2002:python/name:pymdownx.superfences.fence_code_format",
            lambda loader, node: "pymdownx.superfences.fence_code_format",
        )
        with open(MKDOCS_YML) as f:
            config = yaml.safe_load(f)
        hooks = config.get("hooks", [])
        for hook_spec in hooks:
            hook_path = os.path.join(os.path.dirname(MKDOCS_YML), hook_spec)
            with self.subTest(hook=hook_spec):
                self.assertTrue(os.path.isfile(hook_path), f"Hook missing: {hook_path}")

    def test_hooks_importable(self):
        hooks_dir = os.path.join(os.path.dirname(MKDOCS_YML), "hooks")
        for fname in os.listdir(hooks_dir):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(hooks_dir, fname)
            with self.subTest(hook=fname):
                spec = importlib.util.spec_from_file_location(fname[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # Verify expected entry points exist
                if fname == "edit_links.py":
                    self.assertTrue(hasattr(mod, "on_page_context"))
                elif fname == "version_stamp.py":
                    self.assertTrue(hasattr(mod, "on_config"))


class TestCommandScriptsReference(unittest.TestCase):
    def test_all_documented_command_scripts_exist(self):
        """Every script listed in commands.md must exist in bin/."""
        ref_path = os.path.join(DOCS_DIR, "commands-and-modules", "commands.md")
        self.assertTrue(os.path.isfile(ref_path))
        documented = extract_command_script_names(ref_path)
        self.assertGreater(len(documented), 0)
        missing = []
        for script in documented:
            script_path = os.path.join(REPO_ROOT, "bin", script)
            if not os.path.isfile(script_path):
                missing.append(script)
        if missing:
            self.fail(f"Documented command scripts missing from bin/: {missing}")


class TestDocsDirectoryStructure(unittest.TestCase):
    def test_index_md_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(DOCS_DIR, "index.md")))

    def test_no_empty_directories(self):
        """Warn if there are empty directories under docs/."""
        empty = []
        for root, dirs, files in os.walk(DOCS_DIR):
            if root == DOCS_DIR:
                continue
            if not dirs and not files:
                empty.append(os.path.relpath(root, DOCS_DIR))
        if empty:
            self.fail(f"Empty directories under docs/: {empty}")


class TestPythonModulesReference(unittest.TestCase):
    def test_all_documented_python_modules_exist(self):
        """Every module listed in python-modules.md must exist in python/."""
        ref_path = os.path.join(DOCS_DIR, "commands-and-modules", "python-modules.md")
        self.assertTrue(os.path.isfile(ref_path))
        documented = extract_python_module_names(ref_path)
        self.assertGreater(len(documented), 0)
        missing = []
        for module in documented:
            module_path = os.path.join(PYTHON_SRC, module)
            if not os.path.isfile(module_path):
                missing.append(module)
        if missing:
            self.fail(f"Documented Python modules missing from {PYTHON_SRC}: {missing}")


class TestMarkdownListIndentation(unittest.TestCase):
    def test_nested_lists_under_numbered_items_are_sufficiently_indented(self):
        """Nested list markers under numbered items must be indented by 4.

        MkDocs uses Python-Markdown with a tab length of 4. Any list item
        inside a numbered-list tree must be indented at least 4 spaces past
        its parent list item; otherwise Python-Markdown treats it as a
        continuation of the ordered list, flattening the intended nested
        structure and changing the rendered item counts.
        """
        list_marker_re = re.compile(r"^(\s*)(\d+\.\s+|[*+-]\s+)")
        numbered_marker_re = re.compile(r"^(\s*)(\d+\.\s+)")
        failures = []

        for root, _dirs, files in os.walk(DOCS_DIR):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()

                # Stack of (indent, content_indent, is_numbered, in_numbered_tree)
                stack = []
                for i, raw_line in enumerate(lines):
                    line = raw_line.rstrip("\n")
                    if not line.strip():
                        continue

                    m = list_marker_re.match(line)
                    if m:
                        indent = len(m.group(1))
                        marker_text = m.group(2)
                        marker_width = len(marker_text.rstrip())
                        spaces_after = len(marker_text) - marker_width
                        content_indent = indent + marker_width + spaces_after
                        is_numbered = numbered_marker_re.match(line) is not None

                        while stack and stack[-1][0] >= indent:
                            stack.pop()

                        in_numbered_tree = is_numbered or (bool(stack) and stack[-1][3])

                        if stack and in_numbered_tree and indent < stack[-1][0] + 4:
                            rel = os.path.relpath(path, DOCS_DIR)
                            failures.append(
                                f"{rel}:{i + 1}: nested list marker at indent "
                                f"{indent} must be at least "
                                f"{stack[-1][0] + 4} (parent item indent "
                                f"{stack[-1][0]} + 4)"
                            )

                        stack.append((indent, content_indent, is_numbered, in_numbered_tree))
                    else:
                        non_space_indent = len(line) - len(line.lstrip())
                        if non_space_indent == 0 and line.strip():
                            stack = []
                        else:
                            while stack and stack[-1][1] > non_space_indent:
                                stack.pop()

        if failures:
            self.fail(
                "Insufficiently indented nested lists found (will render as "
                "flattened ordered lists):\n  " + "\n  ".join(failures)
            )


class TestAgentsMdReferences(unittest.TestCase):
    """Stale references in AGENTS.md files must fail this suite."""

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_root_agents_md_meets_extraction_floor(self):
        text = self._read(os.path.join(REPO_ROOT, "AGENTS.md"))
        _problems, _ignored, _allowlisted, candidates = _validate_agents_md_text(
            text, "AGENTS.md"
        )
        tokens = sorted({token for _line, token in candidates})
        self.assertGreaterEqual(
            len(tokens),
            MIN_ROOT_CANDIDATES,
            f"Only {len(tokens)} reference candidates extracted from root "
            f"AGENTS.md (floor {MIN_ROOT_CANDIDATES}); the extractor is "
            f"probably broken. Found: {tokens}",
        )

    def test_all_references_exist(self):
        failures = []
        for path in AGENTS_MD_FILES:
            label = os.path.relpath(path, REPO_ROOT)
            text = self._read(path)
            problems, _ignored, _allowlisted, _candidates = _validate_agents_md_text(
                text, label
            )
            failures.extend(problems)
            failures.extend(_validate_branch_mentions(text, label))
        if failures:
            self.fail("Stale references in AGENTS.md files:\n  " + "\n  ".join(failures))

    def test_checker_flags_bogus_reference(self):
        text = (
            "See bin/no-such-script-here and docs/no-such-guide.md "
            "for details.\n"
        )
        problems, _ignored, _allowlisted, _candidates = _validate_agents_md_text(
            text, "synthetic"
        )
        joined = "\n".join(problems)
        self.assertIn("bin/no-such-script-here", joined)
        self.assertIn("docs/no-such-guide.md", joined)
        # Clean text must produce no problems.
        problems, _ignored, _allowlisted, _candidates = _validate_agents_md_text(
            "No references here.\n", "synthetic"
        )
        self.assertEqual(problems, [])

    def test_placeholder_token_validates_parent_dir(self):
        text = "Run pytest tests/python/test_<name>.py -x --tb=short.\n"
        problems, _ignored, _allowlisted, _candidates = _validate_agents_md_text(
            text, "synthetic"
        )
        self.assertEqual(problems, [])

    def test_git_ignored_path_is_skipped(self):
        # docs/site/ is gitignored generated content; a missing file under it
        # must be skipped, not failed.
        status, _detail = _resolve_candidate("docs/site/fake-generated-page.html")
        self.assertEqual(status, "ignored")

    def test_author_machine_path_is_allowlisted(self):
        status, _detail = _resolve_candidate("/NFS1/dan/plan/some-file.md")
        self.assertEqual(status, "allowlisted")

    def test_branch_mentions_exist(self):
        failures = []
        for path in AGENTS_MD_FILES:
            label = os.path.relpath(path, REPO_ROOT)
            failures.extend(_validate_branch_mentions(self._read(path), label))
        if failures:
            self.fail("Stale branch references in AGENTS.md files:\n  " + "\n  ".join(failures))

    def test_branch_checker_flags_unknown_branch(self):
        problems = _validate_branch_mentions("Branch: nope-xyz\n", "synthetic")
        self.assertTrue(problems)
        self.assertEqual(_validate_branch_mentions("No branch line.\n", "synthetic"), [])


if __name__ == "__main__":
    unittest.main()
