#!/usr/bin/env python3
"""Read-only, dependency-free documentation checks; no services or network by default."""
import argparse
from collections import Counter
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from posixpath import relpath
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


LOCALES = {
    "en": "English",
    "zh-CN": "简体中文",
    "ja": "日本語",
    "ru": "Русский",
    "fa": "فارسی",
}


def localized_pages(stem, default_language):
    return {
        lang: f"{stem}.md" if lang == default_language else f"{stem}.{lang}.md"
        for lang in LOCALES
    }


HOMEPAGES = {
    lang: "README.md" if lang == "en" else f"docs/README.{lang}.md"
    for lang in LOCALES
}
CONTRIBUTING = {
    lang: "CONTRIBUTING.md" if lang == "en" else f"docs/CONTRIBUTING.{lang}.md"
    for lang in LOCALES
}
DOCUMENTS = (
    HOMEPAGES,
    CONTRIBUTING,
    *(localized_pages(f"docs/{name}", "zh-CN") for name in (
        "BUILDING", "COMPATIBILITY", "DISCLAIMER", "GUIDED-SETUP", "LICENSING",
        "PGHB", "PRIVACY", "RECOVERY", "TEST-MATRIX",
        "USAGE", "USER-GUIDE",
    )),
    *(localized_pages(name, "en") for name in (
        "docs/LOG_COMPATIBILITY", "docs/THIRD_PARTY_NOTICES", "LICENSES/README",
    )),
)
# Published changelogs are English, including the older localized URLs.
CHANGELOGS = {"docs/CHANGELOG.md", *(
    f"docs/CHANGELOG.{lang}.md" for lang in ("en", "ja", "ru", "fa")
)}
LOCALIZED_CHANGELOGS = {
    f"docs/CHANGELOG.{lang}.md": lang for lang in ("ja", "ru", "fa")
}
# These copies ship with the router packages. Repository navigation uses the
# localized notices without relying on installed-file layout.
PACKAGE_NOTICES = {
    "package/root/usr/share/proxy-guard/LICENSES/README.md",
    "package/root/usr/share/proxy-guard/LICENSING.md",
    "package/root/usr/share/proxy-guard/THIRD_PARTY_NOTICES.md",
}
ENGLISH_HOME_ALIAS = "docs/README.en.md"
ARCHIVE_INDEX = "archive/0.3/README.md"
REPO = "beezcheyenna/Proxy-Guard"

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
REF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]*>|\S+)", re.M)
INLINE = re.compile(r"!?\[[^\]\n]*\]\(")
REFERENCE = re.compile(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.M)


def prose(text):
    lines, fence = [], None
    for line in text.splitlines():
        opening = re.match(r"^\s{0,3}(\x60{3,}|~{3,})", line)
        if fence:
            if re.match(r"^\s{0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*$", line):
                fence = None
            lines.append("")
        elif opening:
            fence = (opening[1][0], len(opening[1]))
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if not value:
                continue
            if key in ("href", "src"):
                self.links.append(value)
            if key == "id" or (tag == "a" and key == "name"):
                self.ids.add(value)


def anchor_ids(text):
    text = prose(text)
    parser = Tags()
    parser.feed(text)
    result, seen = set(parser.ids), Counter()
    titles = [m[1] for m in HEADING.finditer(text)]
    titles += re.findall(r"^([^\n]+)\n(?:={3,}|-{3,})\s*$", text, re.M)
    for title in titles:
        title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)
        title = unescape(re.sub(r"<[^>]*>", "", title)).lower()
        title = re.sub(r"[^\w\s-]", "", title)
        slug = re.sub(r"\s", "-", title.strip())
        count = seen[slug]
        seen[slug] += 1
        result.add(slug if count == 0 else f"{slug}-{count}")
    return result


def destination(value):
    value = value.strip()
    if value.startswith("<"):
        return value[1:value.find(">")]
    return re.split(r"\s+", value, maxsplit=1)[0] if value else ""


def link_targets(text):
    text = re.sub(r"(\x60+).*?\1", "", prose(text))
    parser = Tags()
    parser.feed(text)
    targets = list(parser.links)
    definitions = {m[1].strip().lower(): destination(m[2]) for m in REF.finditer(text)}
    targets += list(definitions.values())
    for match in INLINE.finditer(text):
        pos, start, depth = match.end(), match.end(), 1
        while pos < len(text) and depth:
            char = text[pos]
            if char == "\\":
                pos += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            pos += 1
        if depth == 0:
            targets.append(destination(text[start:pos - 1]))
    for match in REFERENCE.finditer(text):
        key = (match[2] or match[1]).strip().lower()
        if key not in definitions:
            targets.append("UNDEFINED_REFERENCE:" + key)
    return targets


def markdown_files(root):
    for file in sorted(root.rglob("*.md")):
        if not SKIP_DIRS.intersection(file.relative_to(root).parts):
            yield file


def github_document(url):
    parts = unquote(url.path).strip("/").split("/")
    repo_parts = REPO.lower().split("/")
    if [p.lower() for p in parts[:2]] != repo_parts:
        return None
    if url.hostname == "github.com" and len(parts) >= 5 and parts[2] == "blob":
        return parts[3], "/".join(parts[4:])
    if url.hostname == "raw.githubusercontent.com" and len(parts) >= 4:
        return parts[2], "/".join(parts[3:])
    return None


def local_destination(root, source, url):
    document = github_document(url)
    if document and document[0] == "main":
        return (root / document[1]).resolve()
    if url.scheme or url.netloc:
        return None
    rel = unquote(url.path)
    if not rel:
        return source
    if rel.startswith("/"):
        return (root / rel.lstrip("/")).resolve()
    return (source.parent / rel).resolve()


def check_links(root):
    root = Path(root).resolve()
    errors, count, cache = [], 0, {}
    for file in markdown_files(root):
        for target in link_targets(file.read_text(encoding="utf-8")):
            if target.startswith("UNDEFINED_REFERENCE:"):
                errors.append(f"{file.relative_to(root)}: {target}")
                continue
            try:
                url = urlsplit(unescape(target))
                dest = local_destination(root, file, url)
            except ValueError:
                errors.append(f"{file.relative_to(root)}: malformed link {target!r}")
                continue
            if dest is None:
                continue
            count += 1
            if not dest.is_relative_to(root) or not dest.exists():
                errors.append(f"{file.relative_to(root)}: missing local target {target!r}")
                continue
            if url.fragment and dest.suffix.lower() == ".md":
                if dest not in cache:
                    cache[dest] = anchor_ids(dest.read_text(encoding="utf-8"))
                if unquote(url.fragment) not in cache[dest]:
                    errors.append(f"{file.relative_to(root)}: missing anchor {target!r}")
    return errors, count


def language_menu(page, variants):
    directory = Path(page).parent
    return " · ".join(
        f"[{label}]({relpath(variants[lang], directory)})"
        for lang, label in LOCALES.items()
    )


def page_locales(groups=DOCUMENTS):
    return {
        path: lang
        for variants in groups
        for lang, path in variants.items()
    }


SCRIPT_RANGES = {
    "han": r"[\u3400-\u9fff]",
    "kana": r"[\u3041-\u3096\u30a1-\u30fa]",
    "cyrillic": r"[\u0400-\u052f]",
    "arabic": r"[\u0600-\u06ff\u0750-\u077f]",
}
PRIMARY_SCRIPT = {"zh-CN": "han", "ja": "kana", "ru": "cyrillic", "fa": "arabic"}


def check_prose_language(content, lang):
    # Ignore code, link destinations and markup. A script check catches a
    # copied translation, while terminology and meaning still need review.
    body = re.sub(r"(\x60+).*?\1", "", prose(content))
    body = re.sub(r"\]\([^)\n]+\)", "]", body)
    body = re.sub(r"<[^>\n]+>", "", body)
    letters = {
        script: sum(unicodedata.category(c).startswith("L") for c in re.findall(pattern, body))
        for script, pattern in SCRIPT_RANGES.items()
    }
    primary = PRIMARY_SCRIPT.get(lang)
    if primary and letters[primary] < 8:
        return f"body does not contain enough {lang} prose"
    allowed = {"han", "kana"} if lang == "ja" else {primary}
    for script, count in letters.items():
        if script not in allowed and count >= 8:
            return f"unexpected {script} prose in {lang} page"
    return None


def check_languages(root, groups=DOCUMENTS):
    root = Path(root).resolve()
    locales = page_locales(groups)
    variants_by_path = {path: variants for variants in groups for path in variants.values()}
    if groups is DOCUMENTS:
        locales[ENGLISH_HOME_ALIAS] = "en"
        variants_by_path[ENGLISH_HOME_ALIAS] = HOMEPAGES
    errors = []
    for rel, lang in locales.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"{rel}: missing {lang} translation")
            continue
        menu = language_menu(rel, variants_by_path[rel])
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines.count(menu) != 1 or menu not in lines[:5]:
            errors.append(f"{rel}: invalid five-language navigation")
        body = "\n".join(line for line in lines if line != menu)
        problem = check_prose_language(body, lang)
        if problem:
            errors.append(f"{rel}: {problem}")
        for target in link_targets(body):
            if target.startswith("UNDEFINED_REFERENCE:"):
                continue
            try:
                dest = local_destination(root, path, urlsplit(unescape(target)))
            except ValueError:
                continue  # check_links reports malformed URLs
            if dest is None or not dest.is_relative_to(root):
                continue
            # GitHub renders a directory's README; do not let a directory
            # link silently bypass the same-language navigation check.
            if dest.is_dir() and (dest / 'README.md').is_file():
                dest = dest / 'README.md'
            dest_rel = dest.relative_to(root).as_posix()
            target_lang = locales.get(dest_rel)
            if target_lang and target_lang != lang:
                desired = variants_by_path[dest_rel][lang]
                errors.append(f"{rel}: {lang} link targets {target_lang} page {target!r}; use {desired}")
    if groups is DOCUMENTS:
        known = locales.keys() | CHANGELOGS | PACKAGE_NOTICES | {ARCHIVE_INDEX}
        for file in markdown_files(root):
            rel = file.relative_to(root).as_posix()
            if rel not in known:
                errors.append(f"{rel}: add this page to the language inventory")
    return errors


def package_versions(make):
    def value(key):
        version = r"\d+\.\d+\.\d+" if key.endswith("_VERSION") else r"\d+"
        match = re.search(rf"^{key}[ \t]*:?=[ \t]*({version})[ \t]*$", make, re.M)
        if match is None:
            raise ValueError(f"Missing or invalid {key} in package/Makefile")
        return match[1]

    version, revision = value("PKG_VERSION"), value("PKG_RELEASE")
    pro = None
    if re.search(r"^PG_PRO_(?:VERSION|RELEASE)[ \t]*:?=", make, re.M):
        pro = f"{value('PG_PRO_VERSION')}-{value('PG_PRO_RELEASE')}"
    return version, revision, pro


def standalone_assets(version, release):
    return {
        f"luci-app-proxy-guard_{version}-{release}_all.ipk",
        f"luci-app-proxy-guard-{version}-r{release}.apk",
        f"proxy-guard-source-{version}-r{release}.tar.gz",
        "CHANGELOG.en.md",
        "SHA256SUMS",
    }


def expected_assets(standard, pro):
    sv, sr = standard.rsplit("-", 1)
    pv, pr = pro.rsplit("-", 1)
    return {
        f"luci-app-proxy-guard_{standard}_all.ipk",
        f"luci-app-proxy-guard-{sv}-r{sr}.apk",
        f"luci-app-proxy-guard-pro_{pro}_all.ipk",
        f"luci-app-proxy-guard-pro-{pv}-r{pr}.apk",
        f"proxy-guard-source-{standard}-pro-{pro}.tar.gz",
        "SHA256SUMS",
    }


def check_versions(root):
    root = Path(root)
    version, revision, pro = package_versions((root / "package/Makefile").read_text(encoding="utf-8"))
    standard = f"{version}-{revision}"
    revisions = {("IPK", standard), ("APK", f"{version}-r{revision}")}
    errors = []
    for rel in (*HOMEPAGES.values(), ENGLISH_HOME_ALIAS):
        file = root / rel
        if not file.is_file():
            errors.append(f"Missing language document: {rel}")
            continue
        content = file.read_text()
        if not pro:
            shown = set(re.findall(r"\b(IPK|APK)\s*[(（]?\s*`(\d+\.\d+\.\d+-r?\d+)`", prose(content)))
            if shown != revisions:
                errors.append(f"{rel}: package revisions must be {standard} (IPK) and {version}-r{revision} (APK)")
        else:
            rows = [line for line in content.splitlines()
                    if line.startswith("|") and re.search(r"\d+\.\d+\.\d+-\d+", line)]
            if not rows or not all(f"\x60{x}\x60" in rows[0] for x in (standard, pro)):
                errors.append(f"{rel}: current edition table must show {standard} / {pro}")
    release_heading = re.compile(r"^## " + re.escape(version) + r"(?: \(unreleased\))?$", re.M)
    canonical = root / "docs/CHANGELOG.md"
    english_notes = release_heading.split(canonical.read_text(encoding="utf-8"), maxsplit=1)[-1] if canonical.is_file() else ""
    for rel in sorted(CHANGELOGS):
        file = root / rel
        if not file.is_file():
            errors.append(f"Missing changelog: {rel}")
            continue
        content = file.read_text()
        if not pro:
            if not release_heading.search(content):
                errors.append(f"{rel}: missing changelog for {version}")
        else:
            heading = re.search(r"^## (?!Unreleased(?:\s|$))(.+)$", content, re.M)
            if not heading or not all(x in heading[1] for x in (standard, pro)):
                errors.append(f"{rel}: first release heading must show {standard} / {pro}")
        if not pro and rel in LOCALIZED_CHANGELOGS:
            lang = LOCALIZED_CHANGELOGS[rel]
            partitions = release_heading.split(content, maxsplit=1)
            intro, notes = partitions if len(partitions) == 2 else (content, "")
            if not notes.strip() or notes != english_notes:
                errors.append(f"{rel}: release entries must match the English changelog")
            if f"(README.{lang}.md)" not in intro or f"(USER-GUIDE.{lang}.md)" not in intro:
                errors.append(f"{rel}: changelog navigation must point to the {lang} homepage and guide")
            problem = check_prose_language(notes, "en")
        else:
            problem = check_prose_language(content, "en")
        if problem:
            errors.append(f"{rel}: {problem}")
    pages = sorted(root.glob("docs/USAGE*.md")) + sorted(root.glob("docs/LINUX-AGENT-INSTALL*.md"))
    valid = expected_assets(standard, pro) if pro else standalone_assets(version, revision)
    binary_names = {name for name in valid if name.endswith((".ipk", ".apk"))}
    artifact = re.compile(r"(?:luci-app-proxy-guard(?:-pro)?[_-][0-9][A-Za-z0-9._-]*\.(?:ipk|apk)|proxy-guard-source-[0-9][A-Za-z0-9._-]*\.tar\.gz)")
    for file in pages:
        if file.exists():
            names = set(artifact.findall(file.read_text()))
            if not pro and file.name.startswith("USAGE") and not binary_names <= names:
                errors.append(f"{file.relative_to(root)}: missing current installation examples")
            for name in sorted(names - valid):
                errors.append(f"{file.relative_to(root)}: stale artifact example {name}")
    return errors


def release_document(root, ref, rel):
    if ref == "main":
        path = (root / rel).resolve()
        return path.read_text(encoding="utf-8") if path.is_relative_to(root) and path.is_file() else None
    # Release links can use a tag or a full commit ID. Read the exact Git
    # object so a newer document in main cannot satisfy an old link.
    revision = ref if re.fullmatch(r"[0-9a-f]{40}", ref) else f"refs/tags/{ref}"
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", f"{revision}:{rel}"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else None


def check_release(root, release):
    root = Path(root).resolve()
    version, revision, pro = package_versions((root / "package/Makefile").read_text(encoding="utf-8"))
    standard = f"{version}-{revision}"
    tag = f"v{standard}-pro-{pro}" if pro else f"v{version}"
    valid = expected_assets(standard, pro) if pro else standalone_assets(version, revision)
    errors = []
    if release.get("tag_name") != tag:
        errors.append(f"Latest stable Release must be {tag}; found {release.get('tag_name')!r}")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        errors.append("Expected a published stable Release, not draft/prerelease/unknown")
    names = {a.get("name") for a in release.get("assets", []) if isinstance(a, dict)}
    for missing in sorted(valid - names):
        errors.append(f"Stable Release missing asset: {missing}")
    if not pro:
        for extra in sorted(names - valid):
            errors.append(f"Unexpected standalone Release asset: {extra}")
    locales = page_locales()
    locales[ENGLISH_HOME_ALIAS] = "en"
    for target in link_targets(release.get("body") or ""):
        url = urlsplit(unescape(target))
        link = github_document(url)
        if link and link[1].endswith(".md"):
            ref, rel = link
            if locales.get(rel) != "en" and rel not in CHANGELOGS:
                errors.append(f"English Release links to a non-English document: {target}")
            content = release_document(root, ref, rel)
            if content is None:
                errors.append(f"Release links to missing document or Git ref: {target}")
            elif url.fragment and unquote(url.fragment) not in anchor_ids(content):
                errors.append(f"Release links to missing anchor: {target}")
    return errors


def check_license_manifest(directory):
    directory = directory.resolve()
    manifest = directory / "LICENSES/SOURCES.json"
    errors = []
    for item in json.loads(manifest.read_text(encoding="utf-8"))["sources"]:
        rel = item["path"]
        path = (directory / rel).resolve()
        if not path.is_relative_to(directory / "LICENSES") or not path.is_file():
            errors.append(f"{manifest}: missing license file {rel!r}")
            continue
        content = path.read_bytes()
        if len(content) != item["bytes"] or sha256(content).hexdigest() != item["sha256"]:
            errors.append(f"{manifest}: unexpected license file contents for {rel!r}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--release-json", type=Path)
    group.add_argument("--latest-release", metavar="OWNER/REPO")
    args = parser.parse_args(argv)
    try:
        errors, count = check_links(args.root)
        errors += check_languages(args.root)
        errors += check_versions(args.root)
        root = args.root.resolve()
        errors += check_license_manifest(root)
        errors += check_license_manifest(root / "package/root/usr/share/proxy-guard")
        if args.release_json:
            errors += check_release(args.root, json.loads(args.release_json.read_text()))
        if args.latest_release:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.latest_release):
                raise ValueError("Invalid GitHub repository name")
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "Proxy-Guard-doc-check"}
            if os.environ.get("GITHUB_TOKEN"):
                headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
            request = Request(f"https://api.github.com/repos/{args.latest_release}/releases/latest", headers=headers)
            with urlopen(request, timeout=30) as response:
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("Release response exceeds size limit")
                release = json.loads(payload)
            errors += check_release(args.root, release)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Documentation check could not complete: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print("ERROR:", error)
    print(
        f"Checked {len(DOCUMENTS)} five-language document sets, {count} local references, "
        f"source versions, and license manifests. {len(errors)} error(s)."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
