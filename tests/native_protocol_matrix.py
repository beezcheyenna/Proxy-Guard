#!/usr/bin/env python3
"""Final candidate native protocol matrix inside the private router fixture."""
from pathlib import Path
import subprocess,json,time,shutil,traceback,hashlib
assert Path('/etc/pgvm-fixture').is_file()
Q=Path('/root/pg-acceptance/candidate8-protocol');Q.mkdir();cases={}
def rpc(o,m,a):
 p=subprocess.run(['ubus','-t','30','call',o,m,json.dumps(a)],capture_output=True,text=True,timeout=40)
 assert p.returncode==0,(m,p.stderr);d=json.loads(p.stdout or'{}');assert d.get('ok',True),(m,d);return d
def stop(name):
 p=subprocess.run(['/etc/init.d/'+name,'stop'],capture_output=True,text=True,timeout=240)
 assert p.returncode==0,(name,p.stderr)
try:
 # Reconstruct only the test login fixture after /tmp is cleared by cold boot.
 # The real existing account must authenticate; no password or ACL is changed.
 rpc('session','login',{'username':'root','password':''})
 Path('/tmp/pg-latest-login.json').write_text(json.dumps({'password':''}))
 Path('/tmp/pg-latest-login.json').chmod(0o600)
 assert json.loads(Path('/root/pg-acceptance/candidate8-install/complete.json').read_text())['ok']
 assert Path('/mnt/pg-protocol/caddy').is_file() and Path('/mnt/pg-protocol/ssserver').is_file()
 pids=json.loads(Path('/tmp/pg-native-protocols/pids.json').read_text())
 assert all(Path('/proc/'+str(pid)).exists()for name,pid in pids.items()if name in ['hysteria','naive','ss']),pids
 previous='passwall' if __import__('sys').argv[1:]==['passwall']else'nikki'
 for kind in ['hy','ss','naive','naive-quic']:
  O=Q/kind;O.mkdir();(Q/'current.json').write_text(json.dumps({'case':kind,'started':time.time()}))
  sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
  rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':{'enabled':'0'}})
  rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
  end=time.monotonic()+60
  while rpc('proxy_guard','status',{}).get('enforcement')!='off':
   assert time.monotonic()<end;time.sleep(.5)
  stop(previous)
  subprocess.run(['/etc/init.d/'+previous,'disable'],capture_output=True,timeout=30)
  subprocess.run(['ip','netns','exec','pgwan','nft','delete','table','inet','pg_fixture_outage'],capture_output=True)
  with(O/'client.log').open('w')as f:p=subprocess.run(['python3','-u','-B','/tmp/pg-native-protocol-fixture.py','client',kind],stdout=f,stderr=subprocess.STDOUT,timeout=450)
  previous='passwall'
  if p.returncode:
   cases[kind]={'ok':False,'stage':'client','rc':p.returncode};continue
  for name in ['pg-integration-result.json','pg-runtime71.json','pg-first-blocked-status.json','pg-completed-failure-status.json','pg-native-dns-history.jsonl','pg-native-flow-history.jsonl']:Path('/tmp/'+name).unlink(missing_ok=True)
  with(O/'guard.log').open('w')as f:p=subprocess.run(['python3','-u','-B','/tmp/pg-native-protocol-guard.py',kind,'passwall'],stdout=f,stderr=subprocess.STDOUT,timeout=1600)
  for name in ['pg-integration-result.json','pg-runtime71.json','pg-first-blocked-status.json','pg-completed-failure-status.json','pg-native-dns-history.jsonl','pg-native-flow-history.jsonl']:
   if Path('/tmp/'+name).exists():shutil.copy2('/tmp/'+name,O/name)
  value=json.loads((O/'pg-integration-result.json').read_text())
  cases[kind]={'ok':p.returncode==0 and value.get('ok'),'checks':len(value.get('checks',[])),'error':value.get('error')}
  (Q/'results.json').write_text(json.dumps(cases,indent=2));print(json.dumps(cases[kind]),flush=True)
 result={'ok':len(cases)==4 and all(c['ok']for c in cases.values()),'cases':cases}
except Exception:result={'ok':False,'cases':cases,'error':traceback.format_exc()};print(result['error'],flush=True)
(Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
