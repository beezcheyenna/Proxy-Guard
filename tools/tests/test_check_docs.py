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
        for rel in (*docs.HOMEPAGES.values(), docs.ENGLISH_HOME_ALIAS):
            self.write(rel, "| Standard \x601.2.3-4\x60 | Pro \x602.3.4-5\x60 |\n")
        for rel in docs.CHANGELOGS:
            self.write(rel, "# Changes\n\n## 1.2.3-4 / Pro 2.3.4-5\n")
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


    def test_existing_link_to_wrong_language_fails(self):
        manual, destinations = self.language_fixture()
        page = self.root / manual["en"]
        page.write_text(page.read_text() + "\n[Installation](TARGET.md)\n")
        self.assertEqual(docs.check_links(self.root)[0], [])
        self.assertEqual(docs.check_languages(self.root, (manual, destinations)), [
            "manual/HELP.en.md: en link targets zh-CN page 'TARGET.md'; use manual/TARGET.en.md",
        ])

    def test_same_language_link_and_switcher_pass(self):
        manual, destinations = self.language_fixture()
        page = self.root / manual["en"]
        page.write_text(page.read_text() + "\n[Installation](TARGET.en.md#install)\n")
        self.assertEqual(docs.check_languages(self.root, (manual, destinations)), [])
        self.assertEqual(docs.check_links(self.root)[0], [])

    def test_missing_translation_fails(self):
        manual, destinations = self.language_fixture()
        (self.root / manual["ja"]).unlink()
        errors = docs.check_languages(self.root, (manual, destinations))
        self.assertIn("manual/HELP.ja.md: missing ja translation", errors)

    def test_wrong_script_with_correct_suffix_fails(self):
        manual, destinations = self.language_fixture()
        page = self.root / manual["en"]
        page.write_text(page.read_text() + "\n这段内容是中文而不是对应的英文翻译。\n")
        errors = docs.check_languages(self.root, (manual, destinations))
        self.assertIn("manual/HELP.en.md: unexpected han prose in en page", errors)

    def test_switcher_must_open_the_corresponding_translation(self):
        manual, destinations = self.language_fixture()
        page = self.root / manual["en"]
        page.write_text(page.read_text().replace("[English](HELP.en.md)", "[English](HELP.md)"))
        errors = docs.check_languages(self.root, (manual, destinations))
        self.assertIn("manual/HELP.en.md: invalid five-language navigation", errors)

    def test_english_release_cannot_link_to_chinese_main_document(self):
        self.write("docs/USAGE.md", "# 安装与使用\n")
        self.release["body"] = "[Installation](https://github.com/beezcheyenna/Proxy-Guard/blob/main/docs/USAGE.md)"
        errors = docs.check_release(self.root, self.release)
        self.assertTrue(any("non-English document" in error for error in errors))

    def test_release_english_anchor_is_verified(self):
        self.write("docs/USAGE.en.md", "# Install\n\n<a id=\"installation\"></a>\n")
        base = "https://github.com/beezcheyenna/Proxy-Guard/blob/main/docs/USAGE.en.md"
        self.release["body"] = f"[Install]({base}#installation)"
        self.assertEqual(docs.check_release(self.root, self.release), [])
        self.release["body"] = f"[Install]({base}#wrong-section)"
        self.assertTrue(any("missing anchor" in error for error in docs.check_release(self.root, self.release)))

    def language_fixture(self):
        manual = docs.localized_pages("manual/HELP", "zh-CN")
        destinations = docs.localized_pages("manual/TARGET", "zh-CN")
        prose = {
            "en": "Read the installation instructions for this firmware.",
            "zh-CN": "请选择与设备固件相符的安装方式。",
            "ja": "ファームウェアに合う手順を選びます。",
            "ru": "Выберите инструкцию для установленной прошивки.",
            "fa": "روش نصب متناسب با فریم‌ور دستگاه را انتخاب کنید.",
        }
        for group in (manual, destinations):
            for lang, page in group.items():
                nav = docs.language_menu(page, group)
                self.write(page, f"# Help\n\n{nav}\n\n<a id=\"install\"></a>\n\n{prose[lang]}\n")
        return manual, destinations


if __name__ == "__main__":
    unittest.main()
