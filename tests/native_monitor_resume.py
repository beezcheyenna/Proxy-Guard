"""Recovery from a real client restart while the monitor is intentionally stopped."""
from pathlib import Path
import json,sys,subprocess,time,traceback,tempfile,hashlib
assert Path('/etc/pgvm-fixture').is_file()
client=sys.argv[1];assert client in ['passwall','passwall2','openclash','nikki','homeproxy']
checks=[];began=time.monotonic();O=Path('/tmp/pg-monitor-resume');O.mkdir(exist_ok=True)
assert not(O/'complete.json').exists(),'Do not overwrite native recovery evidence'
def run(*args,timeout=150):
 with tempfile.TemporaryFile(mode='w+t')as f:
  r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,text=True,timeout=timeout);f.seek(0);out=f.read()
 with(O/'commands.jsonl').open('a')as f:f.write(json.dumps({'args':args,'rc':r.returncode,'out':out})+'\n')
 assert r.returncode==0,(args,r.returncode,out[-3000:])
 return out
def rpc(obj,method,args=None):return json.loads(run('ubus','-t','60','call',obj,method,json.dumps(args or{})))
def ok(v,label):
 assert v,label
 checks.append(label);print('PASS '+label,flush=True)
def wait(predicate,label,seconds=120):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  s=rpc('proxy_guard','status')
  if predicate(s):ok(True,label);return s
  time.sleep(.5)
 raise AssertionError((label,s))
flow=r"""
import socket,concurrent.futures,json,secrets
def one(row):
 k,f,t,h=row;s=socket.socket(f,t);s.settimeout(2)
 try:
  s.bind(('fd77:88::2' if f==socket.AF_INET6 else '10.77.0.2',0))
  s.connect((h,23456));token=secrets.token_bytes(16);s.sendall(token)
  return k,s.recv(16)==token
 except OSError:return k,False
 finally:s.close()
rows=[(p+z,f,t,h)for f,h,z in [(socket.AF_INET,'9.9.9.9','4'),(socket.AF_INET6,'2001:4860:99::9','6')]for p,t in [('tcp',socket.SOCK_STREAM),('udp',socket.SOCK_DGRAM)]]
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(one,rows))))
"""
def flows(allow,label):
 v=json.loads(run('ip','netns','exec','pglan','python3','-c',flow))
 ok(all(x is allow for x in v.values()),label+' '+json.dumps(v))
try:
 s=wait(lambda s:s.get('enforcement')=='allowing','configured real proxy is healthy before pausing the monitor')
 conf=json.loads(Path('/var/run/proxy-guard/status.json').read_text())['fast_config']
 ok(conf.get('log_watch') is True and conf.get('services_watch') is True,'both service and log monitoring are enabled in the actual snapshot')
 old=json.loads(Path('/var/run/proxy-guard/fast.json').read_text())
 ok(old['log_cursor']['available'] and not old['log_cursor']['pending'],'initial real client journal has a stable cursor')
 flows(True,'IPv4/IPv6 TCP/UDP work before the pause')
 run('/etc/init.d/proxy-guard','stop')
 time.sleep(5)
 flows(False,'stopping the detector retains real blocking rules')
 saved=json.loads(Path('/var/run/proxy-guard/fast.json').read_text())
 ok(saved.get('log_cursor',{}).get('offset',-1)>=old['log_cursor']['offset'] and saved['log_cursor'].get('inode')==old['log_cursor'].get('inode'),'stopped monitor retains the original journal cursor')
 run('/etc/init.d/'+client,'restart',timeout=260)
 profile=json.loads(run('ucode','/usr/lib/proxy-guard/inspect-client.uc',client))
 path=Path(profile['log_path'])
 (O/'client-log-after-restart.txt').write_text(path.read_text(errors='replace'))
 time.sleep(36)
 flows(False,'client restart cannot release the stopped guard')
 run('/etc/init.d/proxy-guard','start')
 s=wait(lambda s:s.get('enforcement')=='allowing' and not(s.get('fast_watch',{}).get('log_watch',{}).get('pending')),'resumed detector consumes the completed unread cycle and recovers',150)
 flows(True,'IPv4/IPv6 TCP/UDP resume after successful real validation')
 latest=json.loads(Path('/var/run/proxy-guard/fast.json').read_text())
 ok(not latest['log_cursor'].get('clock_error') and latest['log_cursor'].get('kind')=='complete','matching clocks and ordered completion clear only the actual stopped cycle')
 result={'ok':True,'checks':checks,'seconds':time.monotonic()-began,'log_module_sha256':hashlib.sha256(Path('/usr/lib/proxy-guard/passwall-log.uc').read_bytes()).hexdigest()}
except Exception:
 result={'ok':False,'checks':checks,'seconds':time.monotonic()-began,'error':traceback.format_exc()}
 print(result['error'],flush=True)
finally:
 for name in ['fast.json','status.json','events.jsonl','fast-events.jsonl']:
  p=Path('/var/run/proxy-guard')/name
  if p.exists():(O/name).write_bytes(p.read_bytes())
 (O/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
