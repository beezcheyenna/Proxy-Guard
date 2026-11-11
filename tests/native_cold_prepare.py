#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,time,traceback,hashlib,sys
assert Path('/etc/pgvm-fixture').exists()
Q=Path(sys.argv[2] if len(sys.argv)>2 else '/tmp/pg-cold-preparation');Q.mkdir(parents=True)
client=sys.argv[1] if len(sys.argv)>1 else 'passwall'
assert client in ['passwall','nikki','homeproxy']
def run(a,timeout=40,check=True):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 if check:assert p.returncode==0,(a[:3],p.returncode,p.stderr[-500:])
 return p.stdout
def rpc(o,m,d=None):
 r=json.loads(run(['ubus','-t','20','call',o,m,json.dumps(d or{})],25)or'{}');assert r.get('ok',True),(m,r);return r
def wait(fn,label,seconds=180):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  x=fn()
  if x:return x
  time.sleep(2)
 raise AssertionError(label)
try:
 login=json.loads(Path('/tmp/pg-latest-login.json').read_text())
 sid=rpc('session','login',{'username':'root','password':login['password']})['ubus_rpc_session']
 profile=json.loads(run(['ucode','/usr/lib/proxy-guard/inspect-client.uc',client]))
 assert profile.get('available') and profile.get('socks_port'),profile
 # Check actual service and TLS three times before introducing a boot outage.
 probes=[]
 for _ in range(3):
  args=['curl','-q']
  if profile.get('socks_curl_file'):args+=['--config',profile['socks_curl_file']]
  args+=['--socks5-hostname','127.0.0.1:'+str(profile['socks_port']),'--connect-timeout','4','--max-time','8','-sS','-o','/dev/null','-w','%{http_code}','https://one.test/generate_204']
  x=run(args)
  assert x=='204',x;probes.append(x);time.sleep(1)
 values={'enabled':'1','mode':'guard','proxy_client':client,'client_auto_ports':'1','passwall_watch':'1','passwall_log_watch':'1','boot_guard':'1','fast_wait_enabled':'1','fast_wait_seconds':'15','fast_stable_enabled':'1','fast_stable_seconds':'60','cf_event_check':'0','udp_check':'0','exit_check':'1','expected_exit4':'9.9.9.9','exit_url':'https://api.ipify.org','exit_fallback_url':'https://4.ident.me','interval':'5','timeout':'3','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0','interfaces':['br-lan'],'sources4':['10.77.0.0/24'],'sources6':['fd77:88::/64'],'local4':['10.77.0.0/24'],'local6':['fd77:88::/64'],'ipv6_protect':'1'}
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 r=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if r.get('confirmation_required'):
  t=r['transaction']
  wait(lambda:(rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}).get('phase')=='confirming','self check',60)
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':t['id'],'token':t['token']})
 state=wait(lambda:(lambda s:s if s.get('enforcement')=='allowing' and s.get('fast_watch',{}).get('phase')=='normal'else None)(rpc('proxy_guard','status')),'healthy normal mode before reboot',200)
 flow="""import socket,json,concurrent.futures
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def f(r):
 n,a,t,h=r;s=socket.socket(a,t);s.settimeout(3)
 try:s.connect((h,23456));s.sendall(b'preboot');return n,s.recv(30)==b'preboot'
 except OSError:return n,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(f,rows))))
"""
 paths=json.loads(run(['ip','netns','exec','pglan','python3','-c',flow],20));assert all(paths.values()),paths
 out=run(['python3','/tmp/pg-native-early-final.py','install'])
 Path('/usr/share/pg-lab-boot/runtime-manifest.json').write_bytes(Path('/tmp/pg-final-runtime-manifest.json').read_bytes())
 run(['/etc/init.d/'+client,'enable'])
 assert 'pglan0'in Path('/etc/config/network').read_text()
 result={'ok':True,'client':client,'probes':probes,'paths':paths,'state':state,'fixture_install':out,'config_sha256':hashlib.sha256(Path('/etc/config/proxy_guard').read_bytes()).hexdigest()}
except Exception:result={'ok':False,'error':traceback.format_exc()};print(result['error'],flush=True)
(Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
