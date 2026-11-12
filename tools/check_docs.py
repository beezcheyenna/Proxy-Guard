#!/usr/bin/env python3
"""Read-only, dependency-free documentation checks; no services or network by default."""
import argparse
from collections import Counter
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

LANGUAGES = ("", "en", "ja", "ru", "fa")
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


def check_links(root):
    root = Path(root).resolve()
    errors, count, cache = [], 0, {}
    for file in sorted(root.rglob("*.md")):
        if any(part in SKIP_DIRS for part in file.relative_to(root).parts):
            continue
        for target in link_targets(file.read_text(encoding="utf-8")):
            if target.startswith("UNDEFINED_REFERENCE:"):
                errors.append(f"{file.relative_to(root)}: {target}")
                continue
            try:
                url = urlsplit(unescape(target))
            except ValueError:
                errors.append(f"{file.relative_to(root)}: malformed link {target!r}")
                continue
            if url.scheme or url.netloc or target.startswith("//"):
                continue
            count += 1
            rel = unquote(url.path)
            dest = ((root / rel.lstrip("/")) if rel.startswith("/") else (file.parent / rel)).resolve() if rel else file
            if not dest.is_relative_to(root) or not dest.exists():
                errors.append(f"{file.relative_to(root)}: missing local target {target!r}")
                continue
            if url.fragment and dest.suffix.lower() == ".md":
                if dest not in cache:
                    cache[dest] = anchor_ids(dest.read_text(encoding="utf-8"))
                if unquote(url.fragment) not in cache[dest]:
                    errors.append(f"{file.relative_to(root)}: missing anchor {target!r}")
    return errors, count


def versions(root):
    text = (Path(root) / "package/Makefile").read_text(encoding="utf-8")
    def value(key):
        match = re.search(r"^" + key + r"\s*:?=\s*(\S+)", text, re.M)
        if not match:
            raise ValueError(f"Missing {key} in package/Makefile")
        return match[1]
    return value("PKG_VERSION") + "-" + value("PKG_RELEASE"), value("PG_PRO_VERSION") + "-" + value("PG_PRO_RELEASE")


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
    standard, pro = versions(root)
    errors = []
    for lang in LANGUAGES:
        suffix = "." + lang if lang else ""
        readme = root / ("README.md" if lang == "en" else ("docs/README.zh-CN.md" if not lang else f"docs/README{suffix}.md"))
        log = root / f"docs/CHANGELOG{suffix}.md"
        guide = root / f"docs/USER-GUIDE{suffix}.md"
        for file in (readme, log, guide):
            if not file.is_file():
                errors.append(f"Missing language document: {file.relative_to(root)}")
        if readme.exists():
            lines = readme.read_text().splitlines()
            rows = [line for line in lines if line.startswith("|") and re.search(r"\d+\.\d+\.\d+-\d+", line)]
            if not rows or not all(f"\x60{x}\x60" in rows[0] for x in (standard, pro)):
                errors.append(f"{readme.relative_to(root)}: current edition table must show {standard} / {pro}")
        if log.exists():
            heading = re.search(r"^## (.+)$", log.read_text(), re.M)
            if not heading or not all(x in heading[1] for x in (standard, pro)):
                errors.append(f"{log.relative_to(root)}: first release heading must show {standard} / {pro}")
    pages = [root / "docs/USAGE.md", root / "docs/LINUX-AGENT-INSTALL.md"]
    valid = expected_assets(standard, pro)
    artifact = re.compile(r"(?:luci-app-proxy-guard(?:-pro)?[_-][0-9][A-Za-z0-9._-]*\.(?:ipk|apk)|proxy-guard-source-[0-9][A-Za-z0-9._-]*\.tar\.gz)")
    for file in pages:
        if file.exists():
            for name in artifact.findall(file.read_text()):
                if name not in valid:
                    errors.append(f"{file.relative_to(root)}: stale artifact example {name}")
    return errors


def check_release(root, release):
    standard, pro = versions(root)
    tag = f"v{standard}-pro-{pro}"
    errors = []
    if release.get("tag_name") != tag:
        errors.append(f"Latest stable Release must be {tag}; found {release.get('tag_name')!r}")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        errors.append("Expected a published stable Release, not draft/prerelease/unknown")
    names = {a.get("name") for a in release.get("assets", []) if isinstance(a, dict)}
    for missing in sorted(expected_assets(standard, pro) - names):
        errors.append(f"Stable Release missing asset: {missing}")
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
        errors += check_versions(args.root)
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
    print(f"Checked {count} local references, five languages and source versions; {len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
