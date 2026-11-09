#!/usr/bin/env python3
"""Regenerate exact lifecycle signatures from audited upstream PO catalogs.
Run only on the build host. This tool never executes upstream scripts.
"""
import argparse,ast,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPECS=[('Restart the service and apply the new rules.','restart',[None]),
 ('Failed or timed out waiting for subscription/rule updates. Restart cancelled.','cancelled',[None]),
 ('Delete %s rules is complete.','rules_removed',['nftables','iptables']),
 ('Clear %s.','sets_cleared',['NFTSet','IPSet']),
 ('Clearing and closing related programs and cache complete.','stopped',[None]),
 ('Starting to load %s firewall rules...','rules_loading',['nftables','iptables']),
 ('Running complete!','complete',[None])]
def po_entries(path):
    entries={};key=None;value='';part=None
    for line in path.read_text().splitlines()+['msgid ""']:
        if line.startswith('msgid '):
            if key is not None: entries[key]=value
            key=ast.literal_eval(line[6:]);value='';part='key'
        elif line.startswith('msgstr '): value=ast.literal_eval(line[7:]);part='value'
        elif line.startswith('"'):
            if part=='key':key+=ast.literal_eval(line)
            elif part=='value':value+=ast.literal_eval(line)
    return entries

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('upstream',type=Path);args=ap.parse_args()
    manifests=json.loads((args.upstream/'manifest.json').read_text());pw=next(args.upstream.glob('openwrt-passwall2-*/luci-app-passwall2'))
    messages=json.loads((ROOT/'tests/passwall-log-legacy.json').read_text());corpus=[]
    catalogs={'en':{}}
    for path in sorted(pw.glob('po/*/*.po')):
        if path.parent.is_symlink():continue
        catalogs[path.parent.name]=po_entries(path)
    for locale,catalog in catalogs.items():
        for source,kind,parameters in SPECS:
            translated=catalog.get(source) or source
            for parameter in parameters:
                assert translated.count('%s')==(parameter is not None),(locale,source,translated)
                message=translated.replace('%s',parameter) if parameter is not None else translated
                assert messages.get(message,kind)==kind,(locale,message)
                messages[message]=kind;corpus.append({'language':locale,'message':message,'kind':kind,'source':source})
    # Global startup failures and the original fixed-language PassWall messages.
    for message,kind in json.loads((ROOT/'tests/passwall-log-legacy.json').read_text()).items():
        corpus.append({'language':'legacy','message':message,'kind':kind,'source':'fixed-language PassWall or prior canonical English'})
    messages['防火墙规则加载完成！']='rules_ready'
    for language,message in [('en','Firewall rules loaded.'),('zh-cn','防火墙规则加载完成！')]:
        if language=='zh-cn':corpus.append({'language':language,'message':message,'kind':'rules_ready','source':'PassWall nftables.sh / iptables.sh'})
    sourcefiles=[]
    for manifest in manifests:
        repo=args.upstream/(manifest['repo']+'-'+manifest['commit'])
        for path in sorted(repo.rglob('*')):
            if not path.is_file() or path.suffix not in ('.sh','.lua') and 'root/etc/init.d/' not in str(path):continue
            for line_number,line in enumerate(path.read_text(errors='replace').splitlines(),1):
                if re.search(r'\b(echolog|log_i18n|log)\s*\(?',line) and not line.lstrip().startswith(('#','--')):
                    sourcefiles.append({'repo':manifest['repo'],'file':str(path.relative_to(repo)),'line':line_number,'text':line.strip()})
    digest=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    path=ROOT/'package/root/usr/lib/proxy-guard/passwall-log.uc';body=path.read_text()
    start=body.index('const messages = ');end=body.index('\n};',start)+3
    replacement='const messages = '+json.dumps(messages,ensure_ascii=False,sort_keys=True,indent=4)+';'
    body=body[:start]+replacement+body[end:]
    body=re.sub(r"const catalog_id = '[a-f0-9]+';\n",'',body)
    body=body.replace(replacement,replacement+"\nconst catalog_id = '"+digest+"';",1)
    path.write_text(body)
    (ROOT/'tests/passwall_log_corpus.json').write_text(json.dumps({'upstream':manifests,'languages':sorted(catalogs),'cases':corpus},ensure_ascii=False,indent=2)+'\n')
    (args.upstream/'log-call-inventory.json').write_text(json.dumps(sourcefiles,ensure_ascii=False,indent=2)+'\n')
    print('Exact lifecycle signatures:',len(messages),'languages:',','.join(sorted(catalogs)),'corpus:',len(corpus),'audited log calls:',len(sourcefiles))
if __name__=='__main__':main()
