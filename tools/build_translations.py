#!/usr/bin/env python3
"""Build and verify separately packaged LuCI translations with official po2lmo."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = ('standard', 'pro')
LANGUAGES = (('en', 1), ('zh-cn', 0), ('ja', 2), ('ru', None), ('fa', None))
BASE = ROOT / 'package/root/www/luci-static/resources'
PRO = ROOT / 'package/pro/root/www/luci-static/resources'
PRO_MENU = 'VPS access rules (Pro)'
PRO_PREFIX = 'proxy-guard-pro:'
SHARED_PRO_VIEWS = (
    ('proxy_guard_remote_trial.js', 'proxy_guard_pro_remote_trial.js'),
    ('view/proxy-guard/raw.js', 'view/proxy-guard/access-raw.js'),
)
PATTERN = r"const pattern = new RegExp(Object.keys(messages).sort((a, b) => b.length - a.length).map(value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');"


def directory(edition):
    path = ROOT / 'package/i18n'
    return path / 'pro' if edition == 'pro' else path


def inputs(edition):
    folder = directory(edition)
    paths = [folder / name for name in ('messages.tsv', 'ru.json', 'fa.json')]
    if edition == 'pro':
        paths.extend(BASE / source for source, _ in SHARED_PRO_VIEWS)
    return paths


def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify(edition=None):
    for name in (edition,) if edition else EDITIONS:
        manifest = json.loads((directory(name) / 'generated.json').read_text())
        assert manifest['inputs'] == hashes(inputs(name)), 'Rebuild ' + name + ' translations and views'
        for path, digest in manifest['files'].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, 'Stale generated artifact: ' + path


def entries(folder):
    rows = [line.split('\t') for line in (folder / 'messages.tsv').read_text().splitlines()
            if line and not line.startswith('#')]
    assert all(len(row) == 3 and all(row) for row in rows), 'Invalid translation row'
    assert len({row[0] for row in rows}) == len(rows), 'Duplicate source message'
    return rows


def compile_catalog(po2lmo, edition, rows, language, column):
    folder = directory(edition)
    extra = json.loads((folder / (language + '.json')).read_text()) if column is None else None
    catalog = {}
    for row in rows:
        # LuCI hashes trimmed keys with whitespace collapsed.
        key = ' '.join(row[1].split())
        if edition == 'pro' and key != PRO_MENU:
            key = PRO_PREFIX + key
        value = row[column] if column is not None else extra[row[1]]
        assert isinstance(value, str) and value, 'Missing ' + language + ' translation: ' + row[1]
        assert catalog.setdefault(key, value) == value, 'Conflicting gettext translation: ' + row[1]
    if language == 'en' and edition == 'standard':
        catalog['proxy-guard-language-name'] = 'English'
    po = folder / (language + '.po')
    header = 'Content-Type: text/plain; charset=UTF-8\nLanguage: ' + language + '\n'
    content = '# Generated from messages.tsv; use tools/build_translations.py.\nmsgid ""\nmsgstr ' + json.dumps(header) + '\n\n'
    content += '\n\n'.join('msgid ' + json.dumps(key, ensure_ascii=False) + '\nmsgstr ' + json.dumps(value, ensure_ascii=False)
                           for key, value in sorted(catalog.items())) + '\n'
    po.write_text(content)
    prefix = 'package/pro/root' if edition == 'pro' else 'package/root'
    domain = 'proxy-guard-pro' if edition == 'pro' else 'proxy-guard'
    lmo = ROOT / prefix / 'usr/lib/lua/luci/i18n' / (domain + '.' + language + '.lmo')
    lmo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([po2lmo, str(po), str(lmo)], check=True)
    return [po, lmo]


def runtime_module(rows, edition):
    messages = json.dumps({row[0]: row[1] for row in rows}, ensure_ascii=False, indent=4)
    header = "'use strict';\n'require baseclass';\n"
    body = '\n// Generated diagnostic translations. Preserve raw technical details.\nconst messages = ' + messages + ';\n' + PATTERN + '\n'
    if edition == 'pro':
        return header + "'require proxy_guard_i18n as shared';\n" + body + """
function gettext(key) {
    // Old base packages contain unscoped copies of these strings.
    const id = 'proxy-guard-pro:' + key;
    const translated = _(id);
    return translated === id ? _(key) : translated;
}

return baseclass.extend({
    gettext,
    decorate: node => shared.decorate(node),
    modal: (ui, title, children) => shared.modal(ui, title, children),
    runtime: function(value) {
        if (typeof value !== 'string') return value;
        const translated = value.replace(pattern, key => gettext(messages[key]));
        return translated === value ? shared.runtime(value) : translated;
    }
});
"""
    return header + body + """
return baseclass.extend({
    direction: function() {
        const lang = typeof document !== 'undefined' ? document.documentElement.lang || '' : '';
        return /^fa(?:[-_]|$)/i.test(lang) ? 'rtl' : 'ltr';
    },
    decorate: function(node) {
        node.dir=this.direction(); node.classList.add('pg-guard');
        node.querySelectorAll('input,textarea').forEach(el => { el.dir=/(?:port|ports|sources[46]|local[46]|expected_exit4|exit_url|exit_fallback_url|endpoint|targets|interfaces|udp_server|udp_query|device_id)$/.test(el.id) ? 'ltr' : 'auto'; });
        return node;
    },
    modal: function(ui,title,children) { return ui.showModal(title,[this.decorate(E('div',{},children))]); },
    runtime: function(value) {
        return typeof value === 'string' ? value.replace(pattern, match => _(messages[match])) : value;
    }
});
"""


def build(edition, po2lmo):
    folder = directory(edition)
    rows = entries(folder)
    outputs = []
    for language, column in LANGUAGES:
        outputs.extend(compile_catalog(po2lmo, edition, rows, language, column))
    runtime = (PRO / 'proxy_guard_pro_i18n.js') if edition == 'pro' else (BASE / 'proxy_guard_i18n.js')
    runtime.write_text(runtime_module(rows, edition))
    outputs.append(runtime)
    if edition == 'pro':
        # Both editions share the existing editor and confirmation behavior.
        # Pro ships its own localized view even on already installed base IPKs.
        for source, target in SHARED_PRO_VIEWS:
            text = (BASE / source).read_text()
            anchor = "'require proxy_guard_i18n as pgI18n';"
            assert text.count(anchor) == 1
            text = text.replace(anchor, "'require proxy_guard_pro_i18n as pgI18n';")
            text = text.replace("'require proxy_guard_remote_trial as pgRemoteTrial';",
                                "'require proxy_guard_pro_remote_trial as pgRemoteTrial';")
            out = PRO / target
            out.write_text('// Generated from ' + source + ' by tools/build_translations.py.\n'
                           + re.sub(r'\b_\(', 'pgI18n.gettext(', text))
            outputs.append(out)
    (folder / 'generated.json').write_text(json.dumps({
        'inputs': hashes(inputs(edition)), 'files': hashes(outputs)
    }, indent=2) + '\n')
    verify(edition)
    print('Built five ' + edition + ' catalogs for ' + str(len(rows)) + ' messages')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('po2lmo', help='Official LuCI po2lmo executable')
    parser.add_argument('--only', choices=EDITIONS)
    args = parser.parse_args()
    for edition in (args.only,) if args.only else EDITIONS:
        build(edition, args.po2lmo)


if __name__ == '__main__':
    main()
