#!/usr/bin/env python3
"""Read early receiver evidence and validate recovery without any service refresh."""
from pathlib import Path
import subprocess,json,time,traceback,sys,hashlib
assert Path('/etc/pgvm-fixture').is_file()
Q=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/pg-cold-acceptance');Q.mkdir(parents=True)
def run(a,timeout=30):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout);assert p.returncode==0,(a[:3],p.returncode,p.stderr[-500:]);return p.stdout
def status():return json.loads(run(['ubus','-t','15','call','proxy_guard','status','{}'],20))
states=[];checks=[];report=None
def good(v,n):assert v,n;checks.append(n);print('PASS '+n,flush=True)
try:
 manifest=json.loads(Path('/usr/share/pg-lab-boot/runtime-manifest.json').read_text())
 good(all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in manifest['files'].items()),'cold boot uses the exact installed candidate payload')
 end=time.monotonic()+260
 while not Path('/tmp/pg-early-boot/pump.json').exists():
  assert time.monotonic()<end,'early packet pump did not finish'
  time.sleep(3)
 report=json.loads(run(['python3','/usr/share/pg-lab-boot/early.py','report']))
 good(all(v==0 for v in report['arrivals'].values()),'zero IPv4/IPv6 TCP/UDP arrivals from the start of boot')
 good(all(v['responses']==0 and v['attempts']>100 for v in report['pump'].values()),'all four early clients attempted repeatedly without a successful response')
 events=[json.loads(l)for l in report['events'].splitlines()]
 guard=next(e['uptime']for e in events if e['guard_table'])
 lan=next(e['uptime']for e in events if e['lan_addresses'] and any(a.get('scope')=='global' and a.get('family')in ['inet','inet6'] for iface in json.loads(e['lan_addresses']) for a in iface.get('addr_info',[])))
 good(guard<lan,'fixed guard rules are present before LAN addresses become usable')
 good(status().get('enforcement')=='blocked','status agrees with the boot outage packet result')
 mg=run(['ip','netns','exec','pglan','curl','-q','-sS','--max-time','5','-o','/dev/null','-w','%{http_code}','http://10.77.0.1/'])
 good(mg in ['200','301','302','303'],'router management remains accessible during cold protection')
 own=run(['python3','-c',"import socket;s=socket.create_connection(('9.9.9.9',23456),3);s.sendall(b'router-cold');assert s.recv(30)==b'router-cold';print('ok')"])
 good(own.strip()=='ok','router own external traffic remains accessible during cold protection')
 run(['ip','netns','exec','pgwan','nft','delete','table','inet','pg_fixture_outage'])
 end=time.monotonic()+200
 while time.monotonic()<end:
  s=status();fast=s.get('fast_watch')or{}
  states.append({'uptime':float(Path('/proc/uptime').read_text().split()[0]),'enforcement':s.get('enforcement'),'phase':fast.get('phase'),'stable':fast.get('stable_elapsed',0),'reason':s.get('reason')})
  if s.get('enforcement')=='allowing' and fast.get('phase')=='normal' and fast.get('stable_elapsed',0)>=60:break
  time.sleep(2)
 else:raise AssertionError(states[-3:])
 good(any(x['enforcement']=='allowing' and x['phase']=='sensitive'for x in states),'successful real probes release traffic during sensitive observation')
 good(states[-1]['stable']>=60,'sixty uninterrupted seconds return the cold recovery to normal')
 code="""import socket,concurrent.futures,json
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def f(r):
 n,a,t,h=r;s=socket.socket(a,t);s.settimeout(3)
 try:s.connect((h,23456));s.sendall(b'cold-restored');return n,s.recv(32)==b'cold-restored'
 except OSError:return n,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(f,rows))))
"""
 paths=json.loads(run(['ip','netns','exec','pglan','python3','-c',code],15))
 good(all(paths.values()),'IPv4/IPv6 TCP/UDP forwarding recovers after cold protection')
 result={'ok':True,'checks':checks,'cold':report,'states':states,'recovered_paths':paths,'no_manual_service_refresh':True}
except Exception:result={'ok':False,'checks':checks,'cold':report,'states':states,'error':traceback.format_exc()};print(result['error'],flush=True)
(Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
