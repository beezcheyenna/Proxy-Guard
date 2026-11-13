#!/usr/bin/env python3
"""Build and verify Proxy Guard LuCI translations with official po2lmo."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = (('en', 1), ('zh-cn', 0), ('ja', 2), ('ru', None), ('fa', None))
BASE = ROOT / 'package/root/www/luci-static/resources'
CATALOG = ROOT / 'package/i18n'
PATTERN = r"const pattern = new RegExp(Object.keys(messages).sort((a, b) => b.length - a.length).map(value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');"


def inputs():
    return [CATALOG / name for name in ('messages.tsv', 'ru.json', 'fa.json')]


def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify():
    manifest = json.loads((CATALOG / 'generated.json').read_text())
    assert manifest['inputs'] == hashes(inputs()), 'Rebuild Proxy Guard translations'
    for path, digest in manifest['files'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, 'Stale generated artifact: ' + path


def entries(folder):
    rows = [line.split('\t') for line in (folder / 'messages.tsv').read_text().splitlines()
            if line and not line.startswith('#')]
    assert all(len(row) == 3 and all(row) for row in rows), 'Invalid translation row'
    assert len({row[0] for row in rows}) == len(rows), 'Duplicate source message'
    return rows


def compile_catalog(po2lmo, rows, language, column):
    folder = CATALOG
    extra = json.loads((folder / (language + '.json')).read_text()) if column is None else None
    catalog = {}
    for row in rows:
        # LuCI hashes trimmed keys with whitespace collapsed.
        key = ' '.join(row[1].split())
        value = row[column] if column is not None else extra[row[1]]
        assert isinstance(value, str) and value, 'Missing ' + language + ' translation: ' + row[1]
        assert catalog.setdefault(key, value) == value, 'Conflicting gettext translation: ' + row[1]
    if language == 'en':
        catalog['proxy-guard-language-name'] = 'English'
    po = folder / (language + '.po')
    header = 'Content-Type: text/plain; charset=UTF-8\nLanguage: ' + language + '\n'
    content = '# Generated from messages.tsv; use tools/build_translations.py.\nmsgid ""\nmsgstr ' + json.dumps(header) + '\n\n'
    content += '\n\n'.join('msgid ' + json.dumps(key, ensure_ascii=False) + '\nmsgstr ' + json.dumps(value, ensure_ascii=False)
                           for key, value in sorted(catalog.items())) + '\n'
    po.write_text(content)
    lmo = ROOT / 'package/root/usr/lib/lua/luci/i18n' / ('proxy-guard.' + language + '.lmo')
    lmo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([po2lmo, str(po), str(lmo)], check=True)
    return [po, lmo]


def runtime_module(rows):
    messages = json.dumps({row[0]: row[1] for row in rows}, ensure_ascii=False, indent=4)
    header = "'use strict';\n'require baseclass';\n"
    body = '\n// Generated diagnostic translations. Preserve raw technical details.\nconst messages = ' + messages + ';\n' + PATTERN + '\n'
    return header + body + """
return baseclass.extend({
    direction: function() {
        const lang = typeof document !== 'undefined' ? document.documentElement.lang || '' : '';
        return /^fa(?:[-_]|$)/i.test(lang) ? 'rtl' : 'ltr';
    },
    decorate: function(node) {
        node.dir=this.direction(); node.classList.add('pg-guard');
        node.querySelectorAll('input,textarea').forEach(el => { if(el.hasAttribute('dir')) return; el.dir=/(?:port|ports|sources[46]|local[46]|expected_exit4|exit_url|exit_fallback_url|cf_hb_url|cf_hb_id|cf_hb_secret|endpoint|targets|interfaces|udp_server|udp_query|device_id)$/.test(el.id) ? 'ltr' : 'auto'; });
        return node;
    },
    modal: function(ui,title,children) { return ui.showModal(title,[this.decorate(E('div',{},children))]); },
    runtime: function(value) {
        return typeof value === 'string' ? value.replace(pattern, match => _(messages[match])) : value;
    }
});
"""


def build(po2lmo):
    rows = entries(CATALOG)
    outputs = []
    for language, column in LANGUAGES:
        outputs.extend(compile_catalog(po2lmo, rows, language, column))
    runtime = BASE / 'proxy_guard_i18n.js'
    runtime.write_text(runtime_module(rows))
    outputs.append(runtime)
    (CATALOG / 'generated.json').write_text(json.dumps({
        'inputs': hashes(inputs()), 'files': hashes(outputs)
    }, indent=2) + '\n')
    verify()
    print('Built five catalogs for ' + str(len(rows)) + ' messages')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('po2lmo', help='Official LuCI po2lmo executable')
    parser.add_argument('--only', choices=('standard',), help=argparse.SUPPRESS)
    args = parser.parse_args()
    build(args.po2lmo)


if __name__ == '__main__':
    main()
