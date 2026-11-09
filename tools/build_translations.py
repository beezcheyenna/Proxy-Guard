#!/usr/bin/env python3
"""Build bundled LuCI catalogs with the official po2lmo host tool.

Run on the build host. Both SDK and standalone packages copy the same generated
catalogs from package/root. No translation service or runtime dependency is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'package/i18n/messages.tsv'
MANIFEST = ROOT / 'package/i18n/generated.json'


def entries():
    rows = [line.split('\t') for line in SOURCE.read_text().splitlines()
            if line and not line.startswith('#')]
    assert all(len(row) == 3 and all(row) for row in rows), 'Invalid translation row'
    assert len({row[0] for row in rows}) == len(rows), 'Duplicate source message'
    return rows


def verify():
    manifest = json.loads(MANIFEST.read_text())
    for language in ('ru','fa'):
        path=ROOT/('package/i18n/'+language+'.json')
        assert manifest.get('extra_sources',{}).get(language)==hashlib.sha256(path.read_bytes()).hexdigest(), 'Rebuild extra language catalogs: '+language
    assert manifest['source'] == hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'Rebuild translations after editing messages.tsv'
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, 'Stale generated translation: ' + name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('po2lmo', help='Official LuCI po2lmo executable')
    args = parser.parse_args()
    rows = entries()
    outputs = []
    # English is the source language. Bundle an English catalog as well.
    for language, column in [('en', 1), ('zh-cn', 0), ('ja', 2), ('ru', None), ('fa', None)]:
        extra=json.loads((ROOT/('package/i18n/'+language+'.json')).read_text()) if column is None else None
        catalog = {}
        for row in rows:
            # LuCI's gettext hashes trim and collapse whitespace in keys.
            key = ' '.join(row[1].split())
            value=row[column] if column is not None else extra[row[1]]
            assert isinstance(value,str) and value, 'Missing '+language+' translation: '+row[1]
            old = catalog.setdefault(key, value)
            assert old == value, 'Conflicting gettext translation: ' + row[1]
        po = ROOT / ('package/i18n/' + language + '.po')
        header = 'Content-Type: text/plain; charset=UTF-8\nLanguage: ' + language + '\n'
        content = '# Generated from messages.tsv; use tools/build_translations.py.\nmsgid ""\nmsgstr ' + json.dumps(header) + '\n\n'
        # An English marker keeps po2lmo from deleting an all-identity catalog.
        if language == 'en':
            catalog['proxy-guard-language-name'] = 'English'
        content += '\n\n'.join('msgid ' + json.dumps(key, ensure_ascii=False) + '\nmsgstr ' + json.dumps(value, ensure_ascii=False)
                                 for key, value in sorted(catalog.items())) + '\n'
        po.write_text(content)
        lmo = ROOT / ('package/root/usr/lib/lua/luci/i18n/proxy-guard.' + language + '.lmo')
        lmo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([args.po2lmo, str(po), str(lmo)], check=True)
        outputs += [po, lmo]
    runtime = ROOT / 'package/root/www/luci-static/resources/proxy_guard_i18n.js'
    runtime.write_text("'use strict';\n'require baseclass';\n\n"
        '// Generated diagnostic translations. Preserve raw technical details.\n'
        + 'const messages = ' + json.dumps({row[0]: row[1] for row in rows}, ensure_ascii=False, indent=4) + ';\n'
        + r"const pattern = new RegExp(Object.keys(messages).sort((a, b) => b.length - a.length).map(value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');" + '\n'
        + "return baseclass.extend({\n    direction: function() {\n        const lang = typeof document !== 'undefined' ? document.documentElement.lang || '': '';\n        return /^fa(?:[-_]|$)/i.test(lang) ? 'rtl' : 'ltr';\n    },\n    decorate: function(node) {\n        node.dir=this.direction(); node.classList.add('pg-guard');\n        node.querySelectorAll('input,textarea').forEach(el => { el.dir=/(?:port|ports|sources[46]|local[46]|expected_exit4|exit_url|endpoint|targets|interfaces|udp_server|udp_query|device_id)$/.test(el.id) ? 'ltr' : 'auto'; });\n        return node;\n    },\n    modal: function(ui,title,children) { return ui.showModal(title,[this.decorate(E('div',{},children))]); },\n    runtime: function(value) {\n        return typeof value === 'string' ? value.replace(pattern, match => _(messages[match])) : value;\n    }\n});\n")
    outputs.append(runtime)
    MANIFEST.write_text(json.dumps({'source': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'extra_sources': {language:hashlib.sha256((ROOT/('package/i18n/'+language+'.json')).read_bytes()).hexdigest() for language in ('ru','fa')},
        'files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in outputs}}, indent=2) + '\n')
    verify()
    print('Built English, Chinese, Japanese, Russian and Persian catalogs:', len(rows), 'messages')


if __name__ == '__main__':
    main()
