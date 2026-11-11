#!/usr/bin/env python3
"""Real fast-monitor SIGSTOP/SIGKILL acceptance; disconnected router VM only."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,traceback,hashlib
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file() and Path('/etc/openwrt_release').is_file()
D=Path(sys.argv[1]);D.mkdir(parents=True);checks=[];events=[];frozen=None;original=None;result={'ok':False,'checks':checks}
def run(args,timeout=35):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert p.returncode==0,(args[:3],p.returncode,p.stderr[-1000:]);return p.stdout
def rpc(o,m,p=None):
 r=json.loads(run(['ubus','-t','25','call',o,m,json.dumps(p or{})],32)or'{}')
 assert r.get('ok',True)is not False,(o,m,r);return r
def status():return rpc('proxy_guard','status')
def good(v,label):
 assert v,label
 checks.append(label);(D/'progress.json').write_text(json.dumps(result,indent=2));print('PASS',label,flush=True)
def wait(pred,label,seconds=150):
 end=time.monotonic()+seconds;last={}
 while time.monotonic()<end:
  last=status()
  if pred(last):
   events.append({'label':label,'uptime':up(),'state':last});(D/'events.json').write_text(json.dumps(events,indent=2));return last
  time.sleep(.7)
 events.append({'label':'FAILED '+label,'uptime':up(),'state':last});(D/'events.json').write_text(json.dumps(events,indent=2));raise AssertionError(label)
def up():return float(Path('/proc/uptime').read_text().split()[0])
def identity(pid):
 try:
  fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
  return None if fields[0]in ['Z','X']else str(pid)+':'+fields[19]
 except (OSError,IndexError):return None
def watcher():
 pid=int(Path('/var/run/proxy-guard/fast_watch.pid').read_text())
 args=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(bytes([0]))
 assert any(x.endswith(b'/fast-watch.uc')for x in args),args
 return pid
def current_identity():
 try:return identity(watcher())
 except (OSError,ValueError,AssertionError):return None
def apply(values):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 r=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if r.get('confirmation_required'):
  tx=r['transaction'];end=time.monotonic()+120
  while time.monotonic()<end:
   t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
   if t.get('id')==tx['id']and t.get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('confirmation self-check timeout')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
def thaw():
 global frozen
 if frozen and identity(frozen[0])==frozen[1]:os.kill(frozen[0],signal.SIGCONT)
 frozen=None
flow="""import socket,json,concurrent.futures,secrets
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def probe(row):
 name,f,k,h=row;s=socket.socket(f,k);s.settimeout(3);s.bind(('fd77:88::2'if f==socket.AF_INET6 else'10.77.0.2',0))
 try:
  token=secrets.token_bytes(16);s.connect((h,23456));s.sendall(token);return name,s.recv(32)==token
 except OSError:return name,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(probe,rows))))
"""
def flows(allowed,label):
 r=json.loads(run(['ip','netns','exec','pglan','python3','-c',flow],15));good(all(v is allowed for v in r.values()),label+' '+json.dumps(r))
try:
 manifest=json.loads(Path('/tmp/pg-final-runtime-manifest.json').read_text())
 good(all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items()),'actual candidate payload matches manifest')
 sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'];original={k:v for k,v in original.items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original,indent=2))
 apply({'self_heal':'0','passwall_watch':'1','boot_guard':'1','fast_wait_enabled':'1','fast_wait_seconds':'15','fast_stable_enabled':'1','fast_stable_seconds':'60'})
 wait(lambda s:s.get('enforcement')=='allowing'and(s.get('fast_watch')or{}).get('phase')=='normal','normal monitored baseline',200)
 flows(True,'normal baseline has all four paths')
 pid=watcher();frozen=(pid,identity(pid));started=up();os.kill(pid,signal.SIGSTOP)
 wait(lambda s:s.get('enforcement')=='blocked','stale fast watcher closes the kernel gate',60)
 time.sleep(6)
 good(identity(pid)==frozen[1],'self-heal disabled leaves the frozen watcher identity unchanged')
 raw=json.loads(Path('/var/run/proxy-guard/status.json').read_text())
 good(isinstance(raw.get('probe_started'),(int,float))and raw['probe_started']<=started+4,'main worker starts no new probes after monitor freshness expires')
 flows(False,'a stalled fast watcher blocks IPv4/IPv6 TCP/UDP')
 thaw()
 s=wait(lambda s:s.get('enforcement')=='allowing'and(s.get('fast_watch')or{}).get('phase')=='sensitive','resumed watcher requires fresh successful probes',100)
 good((s.get('fast_watch')or{}).get('stable_elapsed',0)<60,'resumed watcher releases during sensitive observation')
 flows(True,'fresh probes restore all four paths after SIGCONT')
 wait(lambda s:s.get('enforcement')=='allowing'and(s.get('fast_watch')or{}).get('phase')=='normal','resumed watcher completes uninterrupted observation',140)
 old=current_identity();assert old;os.kill(watcher(),signal.SIGKILL)
 end=time.monotonic()+45
 while time.monotonic()<end:
  ident=current_identity()
  if ident and ident!=old:break
  time.sleep(.4)
 else:raise AssertionError('procd failed to replace killed fast watcher')
 good(ident!=old,'procd replaces a killed fast watcher without manual service refresh')
 wait(lambda s:s.get('enforcement')=='blocked','replacement watcher revokes the old permission',25)
 flows(False,'watcher replacement blocks all four paths before new confirmation')
 wait(lambda s:s.get('enforcement')=='allowing'and(s.get('fast_watch')or{}).get('phase')=='sensitive','new watcher verifies actual proxy before release',110)
 flows(True,'all four paths recover after watcher replacement')
 wait(lambda s:s.get('enforcement')=='allowing'and(s.get('fast_watch')or{}).get('phase')=='normal','new watcher completes sixty-second observation',140)
 result['ok']=True
except Exception:result['error']=traceback.format_exc();print(result['error'],flush=True)
finally:
 thaw()
 if original is not None:
  try:
   current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   for key in current:
    if not key.startswith('.')and key not in original:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':key})
   apply(original)
   actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   assert {k:v for k,v in actual.items()if not k.startswith('.')}==original
   result['original_configuration_restored']=True
  except Exception:result['ok']=False;result['cleanup_error']=traceback.format_exc()
 result['finished']=time.time();(D/'complete.json').write_text(json.dumps(result,indent=2))
