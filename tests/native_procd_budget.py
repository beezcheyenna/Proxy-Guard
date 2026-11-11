#!/usr/bin/env python3
"""Repeated busy-disable/procd respawn acceptance in a marked offline router."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,traceback,hashlib,tempfile
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').exists()and Path('/etc/openwrt_release').exists()
D=Path(sys.argv[1]);assert not D.exists();D.mkdir(parents=True)
expect_old='--expect-exhausted'in sys.argv[2:];checks=[];frozen={};r={'ok':False,'checks':checks,'cycles':[],'expected_old_failure':expect_old};original=None
RULES="table inet pg_budget_outage {\n chain input {\n type filter hook input priority -300; policy accept;\n tcp dport 443 drop\n }\n}\n"
def run(a,check=True,timeout=60,input=None):
 with tempfile.TemporaryFile(mode='w+t')as out,tempfile.TemporaryFile(mode='w+t')as err:
  p=subprocess.run(a,text=True,input=input,stdout=out,stderr=err,timeout=timeout)
  out.seek(0);err.seek(0);p.stdout=out.read();p.stderr=err.read()
  assert not check or p.returncode==0,(a[:4],p.returncode,(p.stdout+p.stderr)[-1000:])
  return p
def rpc(o,m,p=None):
 d=json.loads(run(['ubus','-t','40','call',o,m,json.dumps(p or{})],timeout=50).stdout or'{}')
 assert d.get('ok',True)is not False,(o,m,d);return d
def save(): (D/'progress.json').write_text(json.dumps(r,indent=2))
def good(v,label):
 assert v,label
 checks.append(label);save();print('PASS',label,flush=True)
def ident(pid):
 try:
  a=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
  return None if a[0]in ['Z','X']else str(pid)+':'+a[19]
 except (OSError,IndexError):return None
def daemon():
 try:
  pid=int(Path('/var/run/proxy-guard/daemon.pid').read_text());a=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(bytes([0]))
  return pid if a[1:3]==[b'/usr/libexec/proxy-guard',b'daemon']and ident(pid)else None
 except (OSError,ValueError):return None
def state():return rpc('proxy_guard','status')
def wait(fn,seconds,label):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  val=fn()
  if val:return val
  time.sleep(.4)
 raise AssertionError(label)
def apply(values):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if a.get('confirmation_required'):
  tx=a['transaction']
  wait(lambda:(lambda t:t.get('id')==tx['id']and t.get('phase')=='confirming')(rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}),110,'self-check reaches confirmation')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
 return a
def outage(on):
 if on:
  run(['ip','netns','exec','pgwan','nft','-c','-f','-'],input=RULES)
  run(['ip','netns','exec','pgwan','nft','-f','-'],input=RULES)
 else:run(['ip','netns','exec','pgwan','nft','delete','table','inet','pg_budget_outage'],check=False)
def held():
 code='import {open} from "fs";let f=open("/var/lock/proxy-guard.lock","a",0o600);if(!f)exit(2);let free=f.lock("xn");f.close();exit(free?1:0);'
 p=run(['ucode','-e',code],check=False,timeout=10);assert p.returncode in [0,1],p.stderr
 return p.returncode==0
def thaw():
 for pid,old in list(frozen.items()):
  if ident(pid)==old:
   try:os.kill(pid,signal.SIGCONT)
   except ProcessLookupError:pass
  frozen.pop(pid,None)
def freeze_busy():
 end=time.monotonic()+35
 while time.monotonic()<end:
  root=daemon()
  if not root or not held():time.sleep(.15);continue
  before=ident(root);os.kill(root,signal.SIGSTOP);frozen[root]=before;parents={}
  for f in Path('/proc').glob('[0-9]*/stat'):
   try:
    a=f.read_text().rsplit(') ',1)[1].split();parents.setdefault(int(a[1]),[]).append(int(f.parent.name))
   except (OSError,IndexError,ValueError):pass
  def pause(pid):
   for child in parents.get(pid,[]):
    old=ident(child)
    if old:
     try:os.kill(child,signal.SIGSTOP);frozen[child]=old;pause(child)
     except ProcessLookupError:pass
  pause(root)
  if held():return root,before
  thaw();time.sleep(.1)
 raise AssertionError('could not freeze a real native worker holding its lock')
def live_service():
 return rpc('service','list',{'name':'proxy-guard','verbose':True})
try:
 r['init_sha256']=hashlib.sha256(Path('/etc/init.d/proxy-guard').read_bytes()).hexdigest()
 sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 original={k:v for k,v in rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'].items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original))
 # Explicit comparison precondition only. No service refresh occurs between
 # user-equivalent off/on actions or after the final injected SIGKILL.
 if '--installed'not in sys.argv[2:]:run(['/etc/init.d/proxy-guard','restart'],timeout=120)
 values={'enabled':'1','mode':'guard','self_heal':'0','passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','exit_check':'0','cf_event_check':'0','udp_check':'0','startup_grace':'0','interval':'5','timeout':'4','fail_threshold':'1','recover_threshold':'1','schedule_enabled':'0'}
 # This test deliberately disables service monitoring. Automatic listener
 # binding belongs to that feature; carry its current effective ports into
 # the manual fixture instead of reusing a stale hidden/manual fallback.
 if original.get('client_auto_ports')=='1'and original.get('passwall_watch')=='1':
  profile=json.loads(run(['ucode','/usr/lib/proxy-guard/inspect-client.uc',original.get('proxy_client','auto')]).stdout)
  assert profile.get('available')and profile.get('socks_port'),profile
  values.update({'client_auto_ports':'0','socks_port':str(profile['socks_port']),'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':[str(x)for x in profile['dns_ports']]})
  r['manual_test_binding']={k:values[k]for k in ['socks_port','proxy_ports','dns_ports']}
 apply(values)
 wait(lambda:state().get('enforcement')=='allowing',80,'healthy initial native probe')
 good(all(live_service().get('proxy-guard',{}).get('instances',{}).get(k,{}).get('running')for k in ['instance1','fast_watch','supervisor']),'all three packaged services run before busy-disable actions')
 exhausted=None
 for i in range(1,7):
  outage(True);old_pid,old_id=freeze_busy();good(held(),'cycle '+str(i)+' freezes an actual locked worker')
  started=time.monotonic();response=apply({'enabled':'0'})
  wait(lambda:state().get('enforcement')=='off',40,'explicit off removes protection')
  good(ident(old_pid)!=old_id,'cycle '+str(i)+' explicit off clears the blocked worker')
  thaw();outage(False)
  end=time.monotonic()+18;new=None
  while time.monotonic()<end:
   pid=daemon()
   if pid and ident(pid)!=old_id:new=ident(pid);break
   time.sleep(.5)
  row={'cycle':i,'old':old_id,'new':new,'seconds':time.monotonic()-started,'procd':live_service()}
  r['cycles'].append(row);save()
  if not new:exhausted=i;break
  good(True,'cycle '+str(i)+' main process is available without a manual refresh')
  if not expect_old:good(all(row['procd'].get('proxy-guard',{}).get('instances',{}).get(k,{}).get('running')for k in ['instance1','fast_watch','supervisor']),'cycle '+str(i)+' keeps all three supervised processes running')
  apply({'enabled':'1'})
  wait(lambda:state().get('enforcement')=='allowing',80,'re-enable verifies actual proxy connectivity')
 if expect_old:
  good(exhausted is not None,'original implementation exhausts procd during ordinary busy disables')
  r['old_failure_reproduced']=True
 else:
  good(exhausted is None and len(r['cycles'])==6,'six busy disable/enable cycles preserve procd availability')
  pid=daemon();old=ident(pid);os.kill(pid,signal.SIGKILL)
  wait(lambda:daemon()and ident(daemon())!=old,25,'a genuine subsequent SIGKILL respawns')
  good(True,'procd still replaces a genuinely killed monitor after repeated explicit disables')
  wait(lambda:state().get('enforcement')=='allowing',90,'fresh probes restore health after the real process failure')
 r['ok']=True
except Exception:
 r['error']=traceback.format_exc();print(r['error'],flush=True)
 try:r['failure_status']=state()
 except Exception:r['failure_status_error']=traceback.format_exc()
finally:
 thaw();outage(False)
 if original is not None:
  try:
   # Cleanup is recorded separately and never used as an acceptance result.
   if not daemon():run(['/etc/init.d/proxy-guard','restart'],timeout=120)
   current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   for key in current:
    if not key.startswith('.')and key not in original:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':key})
   apply(original)
   actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   assert {k:v for k,v in actual.items()if not k.startswith('.')}==original
   r['original_configuration_restored']=True
  except Exception:r['cleanup_error']=traceback.format_exc();r['ok']=False
 r['final_service']=live_service()
 r['finished']=time.time();save();(D/'complete.json').write_text(json.dumps(r,indent=2))
raise SystemExit(0 if r['ok']else 1)
