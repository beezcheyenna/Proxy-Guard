#!/usr/bin/env python3
"""Real ucode/parser cache regression; only in a marked disposable OpenClash VM."""
from pathlib import Path
import argparse,concurrent.futures,json,os,shutil,stat,subprocess,tempfile,time
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('/usr/lib/proxy-guard/clients.uc'));a=p.parse_args()
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file(),'dedicated isolated VM required'
assert shutil.which('ucode') and Path('/usr/bin/ruby').is_file()
checks={}
with tempfile.TemporaryDirectory(prefix='pg-profile-cache-')as raw:
 d=Path(raw);d.chmod(0o700);cache=d/'cache';cache.mkdir(mode=0o700)
 for f in Path('/usr/lib/proxy-guard').glob('*.uc'):shutil.copy2(f,d/f.name)
 ruby=d/'parser.rb';original=Path('/usr/lib/proxy-guard/read-mihomo.rb').read_text();ruby.write_text(original)
 text=a.source.read_text().replace('/var/run/proxy-guard/',str(cache)+'/').replace('/usr/lib/proxy-guard/read-mihomo.rb',str(ruby))
 assert text.count('function yaml_metadata(client,path) {')==1
 text=text.replace('function yaml_metadata(client,path) {','export function yaml_metadata(client,path) {')
 (d/'clients.uc').write_text(text)
 config=d/'config.yaml';config.write_text('socks-port: 17370\nredir-port: 17371\ntproxy-port: 17372\ndns:\n  enable: true\n  listen: 127.0.0.1:17373\nauthentication:\n  - fixture:fixture-password\n');config.chmod(0o600)
 script=d/'call.uc';script.write_text("import { yaml_metadata } from './clients.uc';\nlet v=yaml_metadata('openclash',"+json.dumps(str(config))+");\nprintf('%J\\n',{ok:type(v)=='object',port:v && v['socks-port']});\n")
 def call():
  result=subprocess.run(['ucode',str(script)],capture_output=True,text=True,timeout=14)
  assert result.returncode==0,result.stderr
  return json.loads(result.stdout)
 def check(name,value):
  checks[name]=bool(value);print(('PASS 'if value else'FAIL ')+name,flush=True);assert value,name
 def expire():
  p=cache/'profile-openclash.json';value=json.loads(p.read_text());value['updated']=0
  q=cache/'expire.tmp';q.write_text(json.dumps(value));q.chmod(0o600);q.replace(p)
 check('cold configuration uses the actual YAML parser',call()=={'ok':True,'port':17370})
 state=json.loads((cache/'profile-openclash.json').read_text())
 check('cache stores a content fingerprint',state.get('version')==3 and len(state.get('digest')or'')==64)
 ruby.write_text("raise 'unchanged configuration must not be reparsed'\n")
 expire();check('expired unchanged configuration survives unavailable parser',call()=={'ok':True,'port':17370})
 before=config.stat();config.write_text(config.read_text().replace('socks-port: 17370','socks-port: 17374'));os.utime(config,ns=(before.st_atime_ns,before.st_mtime_ns))
 expire();check('same-size same-mtime changed configuration cannot reuse stale cache',call()['ok']is False)
 ruby.write_text('sleep 1.5\n'+original)
 check('valid changed configuration allows a bounded slow parser',call()=={'ok':True,'port':17374})
 ruby.write_text("raise 'verified unchanged configuration must not be reparsed'\n")
 expire()
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:values=list(pool.map(lambda _:call(),range(16)))
 check('concurrent refreshes return complete verified metadata',all(v=={'ok':True,'port':17374}for v in values))
 p=cache/'profile-openclash.json';value=json.loads(p.read_text())
 check('published cache stays private and complete',stat.S_IMODE(p.stat().st_mode)==0o600 and value.get('value',{}).get('socks-port')==17374)
 check('temporary cache files are removed',sorted(x.name for x in cache.iterdir())==['profile-openclash.json'])
print(json.dumps({'ok':True,'checks':checks},sort_keys=True))
