import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("check_docs", Path(__file__).resolve().parents[1] / "check_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocumentationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("package/Makefile", "PKG_VERSION:=1.2.3\nPKG_RELEASE:=4\nPG_PRO_VERSION:=2.3.4\nPG_PRO_RELEASE:=5\n")
        for lang in docs.LANGUAGES:
            suffix = "." + lang if lang else ""
            self.write("README.md" if lang == "en" else ("docs/README.zh-CN.md" if not lang else f"docs/README{suffix}.md"), "| Standard \x601.2.3-4\x60 | Pro \x602.3.4-5\x60 |\n")
            self.write(f"docs/CHANGELOG{suffix}.md", "# Changes\n\n## 1.2.3-4 / Pro 2.3.4-5\n")
            self.write(f"docs/USER-GUIDE{suffix}.md", "# Guide\n")
        self.release = {"tag_name": "v1.2.3-4-pro-2.3.4-5", "draft": False, "prerelease": False,
                        "assets": [{"name": n} for n in docs.expected_assets("1.2.3-4", "2.3.4-5")]}

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def test_clean_fixture(self):
        self.assertEqual(docs.check_links(self.root)[0], [])
        self.assertEqual(docs.check_versions(self.root), [])
        self.assertEqual(docs.check_release(self.root, self.release), [])

    def test_missing_file_and_fragment(self):
        self.write("links.md", "[missing](gone.md)\n[fragment](README.md#absent)\n")
        self.assertEqual(len(docs.check_links(self.root)[0]), 2)

    def test_unicode_duplicate_and_explicit_anchors(self):
        self.write("target.md", "# 故障恢复\n# 故障恢复\n<a id=\"manual\"></a>\n")
        self.write("links.md", "[a](target.md#故障恢复) [b](target.md#故障恢复-1) [c](target.md#manual)\n")
        self.assertEqual(docs.check_links(self.root)[0], [])

    def test_html_images_and_encoded_path(self):
        self.write("image sample.png", "fixture")
        self.write("links.md", '<a href="README.md"><img src="image%20sample.png"></a>\n')
        self.assertEqual(docs.check_links(self.root)[0], [])

    def test_code_and_external_links_are_not_local(self):
        self.write("links.md", "\x60\x60\x60sh\n[not a link](missing.md)\n\x60\x60\x60\n\x60[example](absent.md)\x60\n[x](https://example.invalid/path)\n")
        self.assertEqual(docs.check_links(self.root)[0], [])

    def test_reference_definition_and_missing_reference(self):
        self.write("links.md", "[known][k]\n[k]: README.md\n[unknown][bad]\n")
        self.assertEqual(len(docs.check_links(self.root)[0]), 1)

    def test_parent_escape_is_rejected(self):
        self.write("links.md", "[outside](../outside.md)\n")
        self.assertTrue(docs.check_links(self.root)[0])

    def test_stale_localized_readme(self):
        self.write("docs/README.fa.md", "| Standard \x601.2.3-3\x60 | Pro \x602.3.4-5\x60 |\n")
        self.assertTrue(docs.check_versions(self.root))

    def test_stale_changelog(self):
        self.write("docs/CHANGELOG.ja.md", "## 1.2.3-3 / Pro 2.3.4-5\n")
        self.assertTrue(docs.check_versions(self.root))

    def test_stale_package_filename(self):
        self.write("docs/USAGE.md", "Install \x60luci-app-proxy-guard_1.2.3-3_all.ipk\x60.\n")
        self.assertTrue(docs.check_versions(self.root))

    def test_release_tag_mismatch(self):
        self.release["tag_name"] = "v1.2.3-3-pro-2.3.4-5"
        self.assertTrue(docs.check_release(self.root, self.release))

    def test_prerelease_is_not_stable(self):
        self.release["prerelease"] = True
        self.assertTrue(docs.check_release(self.root, self.release))

    def test_missing_release_asset(self):
        self.release["assets"].pop()
        self.assertTrue(docs.check_release(self.root, self.release))


if __name__ == "__main__":
    unittest.main()
