#!/usr/bin/env python3
"""Native worker boundary regression; only in a disconnected disposable router.
Freeze owned daemons, replay a fresh expired-delay snapshot, and let real curl
and the installed Lua/UCI/nft code run. Compare an archived old worker with the
candidate worker without replacing installed program files.
"""
from pathlib import Path
import os,sys,json,time,subprocess,signal,fcntl,threading,traceback,hashlib
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
old_path,new_path=map(Path,sys.argv[1:3])
D=Path('/tmp/pg-delay-boundary-regression');D.mkdir()
R=Path('/var/run/proxy-guard');checks=[];paused={};locks=[];original=None;sid=None
result={'ok':False,'checks':checks,'workers':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [old_path,new_path]}}
def cmd(args,timeout=45,check=True,**kw):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,**kw)
 if check:assert p.returncode==0,(args[:3],p.returncode,p.stderr[-800:],p.stdout[-800:])
 return p.stdout
def rpc(o,m,d=None):
 v=json.loads(cmd(['ubus','-t','20','call',o,m,json.dumps(d or{})],25)or'{}')
 assert v.get('ok',True)is not False,(m,v);return v
def status():return rpc('proxy_guard','status')
def wait(fn,label,timeout=120):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  v=fn()
  if v:return v
  time.sleep(.2)
 raise AssertionError(label)
def apply(v):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':v})
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if a.get('confirmation_required'):
  t=a['transaction'];wait(lambda:(rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}).get('phase')=='confirming','configuration self-check')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':t['id'],'token':t['token']})
def good(v,label):
 assert v,label;checks.append(label);print('PASS '+label,flush=True)
def ident(pid):
 p=Path('/proc')/str(pid);a=p.joinpath('stat').read_text().split(') ',1)[1].split()
 return a[19],p.joinpath('cmdline').read_bytes()
def thaw():
 for f in locks:
  try:fcntl.flock(f,fcntl.LOCK_UN);f.close()
  except OSError:pass
 locks.clear()
 for pid,expected in list(paused.items()):
  try:
   if ident(pid)==expected:os.kill(pid,signal.SIGCONT)
  except (OSError,ProcessLookupError):pass
 paused.clear()
def freeze():
 for attempt in range(100):
  for filename,action in [('daemon.pid',b'daemon'),('fast_watch.pid',b'fast-watch.uc'),('supervisor.pid',b'supervisor')]:
   pid=int((R/filename).read_text());identity=ident(pid)
   assert action in identity[1],(filename,pid)
   paused[pid]=identity;os.kill(pid,signal.SIGSTOP)
  try:
   for name in ['proxy-guard.lock','proxy-guard-fast.lock','proxy-guard-supervision.lock']:
    f=open('/var/lock/'+name,'a')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except: f.close();raise
    locks.append(f)
   return
  except BlockingIOError:thaw();time.sleep(.2)
 raise AssertionError('could not pause owned daemons between transactions')
def atomic(path,obj):
 temp=path.with_name(path.name+'.boundary');temp.write_text(json.dumps(obj));temp.replace(path)
def descendants(root):
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:rows[int(p.name)]=(int(p.joinpath('stat').read_text().split(') ',1)[1].split()[1]),p.joinpath('cmdline').read_bytes())
  except (OSError,ValueError,IndexError):pass
 owned={root};changed=True
 while changed:
  changed=False
  for pid,(parent,args)in rows.items():
   if parent in owned and pid not in owned:owned.add(pid);changed=True
 return [(p,rows[p][1])for p in owned if p in rows]
def scenario(name,path,phase):
 up=int(float(Path('/proc/uptime').read_text().split()[0]))
 fast=dict(baseline_fast);fast.update(phase=phase,holding=True,boot_pending=False,log_pending=False,probe_after=up-2,probe_floor=0,delay_until=up-1,updated_uptime=up,trip=baseline_fast.get('trip',0)+1,stale=False)
 state=dict(baseline_status);state.update(phase='blocked',blocked=True,successes=0,failures=0,next_probe=0,last_probe=0,last_probe_at=0,last_probe_ok=False,primary_probe_ok=False,fast_trip=fast['trip'],fast_generation=fast.get('generation'))
 cmd(['nft','flush','set','inet','proxy_guard','healthy_ifaces'])
 atomic(R/'status.json',state);atomic(R/'fast.json',fast)
 started=time.monotonic()
 lua="package.path='/usr/lib/?.lua;'..package.path;local w=assert(loadfile(arg[1]))();assert(w.tick(false))"
 script=D/'tick.lua';script.write_text(lua)
 out=(D/(name+'.log')).open('w')
 p=subprocess.Popen(['lua',str(script),str(path)],stdout=out,stderr=subprocess.STDOUT,pass_fds=tuple(f.fileno()for f in locks))
 seen=set();samples=[]
 while p.poll()is None:
  for pid,args in descendants(p.pid):
   if b'curl' in args.split(bytes([0]))[0] and b'www.gstatic.com' in args:seen.add(pid)
  if seen and phase=='delay':fast['phase']='sensitive'
  fast['updated_uptime']=int(float(Path('/proc/uptime').read_text().split()[0]))
  atomic(R/'fast.json',fast)
  if time.monotonic()-started>45:p.kill();raise AssertionError(name+' tick timeout')
  time.sleep(.03)
 out.close();assert p.returncode==0,(name,(D/(name+'.log')).read_text())
 s=json.loads((R/'status.json').read_text())
 value={'curl_processes':len(seen),'seconds':time.monotonic()-started,'state':s,'final_fast':fast}
 (D/(name+'.json')).write_text(json.dumps(value,indent=2))
 return value
try:
 sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 original={k:v for k,v in rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'].items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original))
 apply({'enabled':'1','mode':'guard','passwall_watch':'1','passwall_log_watch':'0','boot_guard':'0','self_heal':'0','cf_event_check':'0','udp_check':'0','exit_check':'1','expected_exit4':'9.9.9.9','exit_url':'https://api.ipify.org','exit_fallback_url':'https://4.ident.me','interval':'5','timeout':'3','min_success':'1','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0','fast_wait_enabled':'1','fast_wait_seconds':'15','fast_stable_enabled':'1','fast_stable_seconds':'60','targets':['https://www.gstatic.com/generate_204|204','https://connectivity-check.ubuntu.com|204']})
 wait(lambda:status().get('enforcement')=='allowing','healthy baseline before boundary replay',160)
 # This is an intentionally mismatched HTTP target, served by the private TLS fixture.
 apply({'targets':['https://www.gstatic.com/generate_204|200','https://connectivity-check.ubuntu.com|204']})
 wait(lambda:(R/'fast.json').exists()and json.loads((R/'fast.json').read_text()).get('stamp')==json.loads((R/'status.json').read_text()).get('config_stamp'),'matching native fast/config generation')
 freeze()
 baseline_fast=json.loads((R/'fast.json').read_text());baseline_status=json.loads((R/'status.json').read_text())
 old=scenario('old-expired-delay',old_path,'delay')
 good(old['curl_processes']>0 and old['state'].get('last_probe_ok')is True and len(old['state'].get('probes',[]))==2 and old['state']['probes'][0].get('ok')is False,'archived worker reproduces premature normal-mode qualification at delay boundary')
 fixed=scenario('fixed-expired-delay',new_path,'delay')
 good(fixed['curl_processes']==0 and fixed['state'].get('last_probe')==0,'candidate issues no HTTPS request while watcher still reports delay')
 sensitive=scenario('fixed-sensitive',new_path,'sensitive')
 good(sensitive['curl_processes']>0 and sensitive['state'].get('last_probe_ok')is False and len(sensitive['state'].get('probes',[]))==1,'candidate requires all targets once watcher enters sensitive phase')
 x=sensitive['state'].get('exit_check',{})
 good(x.get('attempted')is False and 'ok'not in x and 'curl_code'not in x,'skipped exit lookup has no false failure result')
 good(sensitive['state'].get('blocked')is True,'failed strict recovery leaves protection blocked')
 result['ok']=True
except Exception:result['error']=traceback.format_exc();print(result['error'],flush=True)
finally:
 thaw()
 try:
  if original is not None and sid:apply(original)
 except Exception:result['cleanup_error']=traceback.format_exc();result['ok']=False
 result['finished_at']=time.time();(D/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
