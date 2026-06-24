"""Tests for MkDocs documentation integrity — nav, links, hooks, anchors."""

import importlib.util
import os
import re
import unittest

from test_support import (
    check_pyyaml, collect_nav_files, extract_markdown_headers,
    extract_markdown_links, list_all_md_files, resolve_relative_link,
    DOCS_DIR, MKDOCS_YML, REPO_ROOT
)


class TestMkDocsYml(unittest.TestCase):

    def setUp(self):
        check_pyyaml()
        import yaml
        yaml.SafeLoader.add_constructor(
            'tag:yaml.org,2002:python/name:pymdownx.superfences.fence_code_format',
            lambda loader, node: 'pymdownx.superfences.fence_code_format'
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
                        failures.append(
                            f"{rel_src}: anchor '{anchor}' not found in {rel_tgt}"
                        )
        if failures:
            self.fail("Broken anchors found:\n  " + "\n  ".join(failures))


class TestMkDocsHooks(unittest.TestCase):

    def test_hooks_exist(self):
        check_pyyaml()
        import yaml
        yaml.SafeLoader.add_constructor(
            'tag:yaml.org,2002:python/name:pymdownx.superfences.fence_code_format',
            lambda loader, node: 'pymdownx.superfences.fence_code_format'
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


if __name__ == "__main__":
    unittest.main()
