"""Versioned APK upgrades with packet-arrival counters in a marked offline VM."""
from pathlib import Path
import subprocess,json,time,sys,traceback,hashlib,os,tempfile
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
candidate,upgrades=map(Path,sys.argv[1:3]);O=Path('/tmp/pg-apk-upgrade');O.mkdir(exist_ok=True)
assert not(O/'complete.json').exists(),'Never overwrite upgrade evidence'
checks=[];process=None;started=time.monotonic()
def command(*args,check=True,timeout=150,input=None):
 with tempfile.TemporaryFile(mode='w+t')as f:
  p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,text=True,input=input,timeout=timeout)
  f.seek(0);out=f.read()
 with(O/'commands.jsonl').open('a')as f:f.write(json.dumps({'args':args,'rc':p.returncode,'output':out})+'\n')
 if check:assert p.returncode==0,(args,p.returncode,out[-2500:])
 return out
def rpc(obj,method,values=None):return json.loads(command('ubus','-t','60','call',obj,method,json.dumps(values or{}),timeout=75))
def ok(value,message):
 assert value,message
 checks.append(message);print('PASS '+message,flush=True)
def wait(predicate,label,seconds=100):
 end=time.monotonic()+seconds;s={}
 while time.monotonic()<end:
  s=rpc('proxy_guard','status')
  if predicate(s):ok(True,label);return s
  time.sleep(.5)
 raise AssertionError((label,s))
def http_rpc(sid,obj):
 body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':[sid,obj,'status',{}]})
 value=json.loads(command('curl','--noproxy','*','-fsS','--max-time','25','http://127.0.0.1/ubus','-H','Content-Type: application/json','--data-binary',body))
 assert value.get('result',[99])[0]==0,value
 return value['result'][1]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pkg(*args):return command('apk','--no-network','--allow-untrusted',*args,timeout=240)
def counters():
 rows=json.loads(command('ip','netns','exec','pgwan','nft','-j','list','table','inet','pg_upgrade_arrivals'))['nftables']
 return {r['counter']['name']:r['counter']['packets']for r in rows if 'counter'in r}
def zero():
 command('ip','netns','exec','pgwan','nft','reset','counters','table','inet','pg_upgrade_arrivals')
def preserved(saved):return all(digest(p)==h for p,h in saved.items())
traffic=r"""
import socket,threading,time,secrets,os
stop='/tmp/pg-apk-upgrade/stop'
def worker(family,kind,host):
 while not os.path.exists(stop):
  s=socket.socket(family,kind);s.settimeout(.6)
  try:
   s.bind(('fd77:88::2' if family==socket.AF_INET6 else '10.77.0.2',0))
   s.connect((host,23456));s.sendall(secrets.token_bytes(16));s.recv(16)
  except OSError:pass
  finally:s.close()
  time.sleep(.15)
threads=[]
for family,host in [(socket.AF_INET,'9.9.9.9'),(socket.AF_INET6,'2001:4860:99::9')]:
 for kind in [socket.SOCK_STREAM,socket.SOCK_DGRAM]:
  t=threading.Thread(target=worker,args=(family,kind,host));t.start();threads.append(t)
for t in threads:t.join()
"""
try:
 pkg('add',str(candidate/'luci-app-proxy-guard-pro-0.3.1-r5.apk'))
 sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 wait(lambda s:s.get('enforcement')=='allowing','baseline allows real client traffic before the upgrade')
 before={str(p):digest(p)for p in [Path('/etc/config/proxy_guard'),Path('/etc/config/proxy_guard_access')]}
 files={str(p):digest(p)for p in [Path('/usr/lib/proxy-guard/core.lua'),Path('/usr/lib/proxy-guard/fast-watch.uc'),Path('/usr/lib/proxy-guard/passwall-log.uc'),Path('/www/luci-static/resources/view/proxy-guard/overview.js')]}
 rule='table inet pg_upgrade_arrivals {\n'
 for key in ['tcp4','udp4','tcp6','udp6']:rule+=' counter '+key+' {}\n'
 rule+=' chain input { type filter hook input priority -399; policy accept;\n'
 for family,addr,suffix in [('ip','9.9.9.9','4'),('ip6','2001:4860:99::9','6')]:
  for proto in ['tcp','udp']:rule+=f' {family} daddr {addr} {proto} dport 23456 counter name {proto}{suffix}\n'
 rule+=' }\n}\n'
 command('ip','netns','exec','pgwan','nft','-f','-',input=rule)
 (O/'stop').unlink(missing_ok=True)
 process=subprocess.Popen(['ip','netns','exec','pglan','python3','-u','-c',traffic],stdout=(O/'traffic.log').open('w'),stderr=subprocess.STDOUT)
 time.sleep(8);arrivals=counters();ok(len(arrivals)==4 and all(v>0 for v in arrivals.values()),'all four native packet-arrival counters work while access is allowed')
 command('ip','netns','exec','pgwan','nft','-f','-',input='table inet pg_fixture_outage { chain input { type filter hook input priority -300; policy accept; tcp dport 443 drop; }\n}\n')
 wait(lambda s:s.get('enforcement')=='blocked','actual proxy probe failure blocks before package replacement',70)
 time.sleep(5);zero();time.sleep(4)
 ok(all(v==0 for v in counters().values()),'blocked IPv4/IPv6 TCP/UDP produce no upstream packets before upgrade')
 pkg('add',str(upgrades/'luci-app-proxy-guard-pro-0.3.1-r6.apk'))
 ok('0.3.1-r6' in pkg('list','--installed','luci-app-proxy-guard-pro'),'native package manager performed a real Pro version upgrade')
 ok('0.3.0-r21' in pkg('list','--installed','luci-app-proxy-guard') and preserved(files),'Pro version upgrade leaves Standard version and payload unchanged')
 ok(preserved(before),'Pro version upgrade preserves both saved configurations')
 ok(all(v==0 for v in counters().values()),'no IPv4/IPv6 TCP/UDP packet escaped during the Pro version upgrade')
 response=http_rpc(sid,'proxy_guard_access')
 ok(isinstance(response,dict),'old authenticated session reaches Pro RPC after version upgrade')
 pkg('add',str(upgrades/'luci-app-proxy-guard-0.3.0-r21.apk'))
 ok('0.3.0-r21' in pkg('list','--installed','luci-app-proxy-guard'),'native package manager performed a real Standard version upgrade')
 ok(preserved(before),'Standard version upgrade preserves both saved configurations')
 time.sleep(6);after=counters();ok(all(v==0 for v in after.values()),'no IPv4/IPv6 TCP/UDP packet escaped during Standard version upgrade')
 response=http_rpc(sid,'proxy_guard')
 ok(response.get('enforcement')=='blocked','old authenticated session reports actual blocking after upgrade')
 command('ip','netns','exec','pgwan','nft','delete','table','inet','pg_fixture_outage')
 wait(lambda s:s.get('enforcement')=='allowing','fresh successful probes restore traffic after the upgrade',140)
 time.sleep(8);ok(all(v>0 for v in counters().values()),'all four packet paths recover after successful validation')
 result={'ok':True,'checks':checks,'seconds':time.monotonic()-started,'upgrade_fixture_only':True,'base_config_hashes':before}
except Exception:
 result={'ok':False,'checks':checks,'seconds':time.monotonic()-started,'error':traceback.format_exc()}
 print(result['error'],flush=True)
finally:
 (O/'stop').touch()
 if process:
  try:process.wait(timeout=6)
  except subprocess.TimeoutExpired:process.terminate()
 try:
  result['status']=rpc('proxy_guard','status')
  result['arrivals']=counters()
 except Exception:pass
 (O/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
