#!/usr/bin/env python3
"""Actual process failure and kernel-permit acceptance in a marked offline VM."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,hashlib,tempfile,traceback
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file() and Path('/etc/openwrt_release').is_file()
D=Path(sys.argv[1] if len(sys.argv)>1 else '/root/pg-acceptance/candidate8-faults')
assert not D.exists(),'Do not overwrite failure evidence'
D.mkdir(parents=True);checks=[];events=[];frozen={};result={'ok':False,'checks':checks}
def save():
 (D/'progress.json').write_text(json.dumps(result,indent=2))
def good(value,label):
 assert value,label
 checks.append(label);save();print('PASS',label,flush=True)
def run(*args,check=True,timeout=30,input=None):
 with tempfile.TemporaryFile(mode='w+t')as out,tempfile.TemporaryFile(mode='w+t')as err:
  p=subprocess.run(args,stdout=out,stderr=err,text=True,input=input,timeout=timeout)
  out.seek(0);err.seek(0);p.stdout=out.read();p.stderr=err.read()
  if check and p.returncode:raise AssertionError((args[:3],p.returncode,(p.stdout+p.stderr)[-1500:]))
  return p
def rpc(obj,method,payload=None):
 p=run('ubus','-t','20','call',obj,method,json.dumps(payload or {}),timeout=28)
 r=json.loads(p.stdout)if p.stdout.strip()else{}
 assert r.get('ok',True)is not False,(obj,method,r)
 return r
def state():return rpc('proxy_guard','status')
def supervision():
 p=Path('/var/run/proxy-guard/supervision.json')
 return json.loads(p.read_text())if p.exists()else{}
def observe(label,st=None):
 st=st or state();events.append({'label':label,'uptime':float(Path('/proc/uptime').read_text().split()[0]),'state':st,'supervision':supervision()})
 (D/'events.json').write_text(json.dumps(events,indent=2));return st
def wait(pred,label,seconds):
 end=time.monotonic()+seconds;last={}
 while time.monotonic()<end:
  last=state()
  if pred(last):return observe(label,last)
  time.sleep(.7)
 observe('FAILED '+label,last);raise AssertionError(label)
def apply(values):
 sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if a.get('confirmation_required'):
  tx=a['transaction'];end=time.monotonic()+110
  while time.monotonic()<end:
   current=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
   if current.get('id')==tx['id']and current.get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('native self-check confirmation timeout')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
 return a
def identity(pid):
 try:
  fields=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
  if fields[0]in ('Z','X'):return None
  return str(pid)+':'+fields[19]
 except (OSError,IndexError):return None
def daemon():
 pid=int(Path('/var/run/proxy-guard/daemon.pid').read_text())
 argv=Path('/proc/'+str(pid)+'/cmdline').read_bytes().split(b'\0')
 assert b'/usr/libexec/proxy-guard'in argv and b'daemon'in argv,argv
 return pid
def freeze_tree():
 root=daemon();ident=identity(root);assert ident
 os.kill(root,signal.SIGSTOP);frozen[root]=ident
 parents={}
 for f in Path('/proc').glob('[0-9]*/stat'):
  try:
   p=int(f.parent.name);fields=f.read_text().rsplit(') ',1)[1].split();parents.setdefault(int(fields[1]),[]).append(p)
  except (ValueError,OSError,IndexError):pass
 def walk(pid):
  for child in parents.get(pid,[]):
   ident=identity(child)
   if ident:
    try:os.kill(child,signal.SIGSTOP);frozen[child]=ident;walk(child)
    except ProcessLookupError:pass
 walk(root)
 return root
def thaw():
 for pid,ident in list(frozen.items()):
  if identity(pid)==ident:
   try:os.kill(pid,signal.SIGCONT)
   except ProcessLookupError:pass
  frozen.pop(pid,None)
flow_code=r"""
import socket,json,concurrent.futures,secrets
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def one(row):
 name,fam,kind,host=row;s=socket.socket(fam,kind);s.settimeout(3);s.bind(('fd77:88::2'if fam==socket.AF_INET6 else'10.77.0.2',0));token=secrets.token_hex(12).encode()
 try:
  s.connect((host,23456));s.sendall(token);return name,s.recv(4096)==token
 except OSError:return name,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:print(json.dumps(dict(pool.map(one,rows))))
"""
def flows(allow,label):
 values=json.loads(run('ip','netns','exec','pglan','python3','-c',flow_code,timeout=15).stdout)
 good(all(v is allow for v in values.values()),label+' '+json.dumps(values))
def outage(enabled):
 if enabled:
  run('ip','netns','exec','pgwan','nft','-c','-f','-',input='table inet pg_fixture_outage {\n chain input {\n  type filter hook input priority -300; policy accept;\n  tcp dport 443 drop\n }\n}\n')
  run('ip','netns','exec','pgwan','nft','-f','-',input='table inet pg_fixture_outage {\n chain input {\n  type filter hook input priority -300; policy accept;\n  tcp dport 443 drop\n }\n}\n')
 else:run('ip','netns','exec','pgwan','nft','delete','table','inet','pg_fixture_outage',check=False)
def configs():
 return {name:hashlib.sha256(Path('/etc/config/'+name).read_bytes()).hexdigest()for name in ['network','firewall','dhcp','passwall','passwall2','nikki','homeproxy','openclash']if Path('/etc/config/'+name).exists()}
def services():
 result={}
 for name in ['network','dnsmasq','nikki','passwall','passwall2','openclash','homeproxy']:
  tree=rpc('service','list',{'name':name})
  result[name]=[identity(v['pid'])for v in tree.get(name,{}).get('instances',{}).values()if v.get('pid')]
 cores=[]
 for path in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   argv=path.read_bytes().split(bytes([0]))
   if argv and Path(argv[0].decode(errors='replace')).name in ['xray','sing-box','mihomo','clash_meta','naive','sslocal','hysteria']:
    ident=identity(int(path.parent.name))
    if ident:cores.append(ident)
  except (OSError,ValueError):pass
 result['proxy_core_processes']=sorted(cores)
 return result
original=None;restored=False
try:
 manifest=json.loads(Path('/tmp/pg-final-runtime-manifest.json').read_text())
 good(all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in manifest['files'].items()),'installed final candidate runtime hashes match')
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 original={k:v for k,v in original.items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original))
 before_cfg=configs();before_services=services()
 outage(False)
 common={'enabled':'1','mode':'guard','passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','self_heal':'0','self_heal_stale':'15','self_heal_window':'600','self_heal_cooldown':'30','self_heal_limit':'10','cf_event_check':'0','exit_check':'0','udp_check':'0','interval':'5','timeout':'2','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0'}
 profile=json.loads(run('ucode','/usr/lib/proxy-guard/inspect-client.uc',original.get('proxy_client','auto')).stdout)
 good(profile.get('available')is True and profile.get('socks_port')is not None,'native active client supplies the manual listener binding')
 common.update({'client_auto_ports':'0','socks_port':str(profile['socks_port']),'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':sorted(set(['53']+[str(x)for x in profile['dns_ports']]))})
 apply(common)
 healthy=wait(lambda s:s.get('enforcement')=='allowing','baseline allowing',70)
 flows(True,'four protected flow baselines are reachable')
 # SIGKILL is handled by real procd, while an already confirmed outage remains blocked.
 outage(True)
 wait(lambda s:s.get('enforcement')=='blocked','HTTPS outage is blocked before process death',50)
 old=daemon();old_ident=identity(old);os.kill(old,signal.SIGKILL)
 end=time.monotonic()+35
 while time.monotonic()<end:
  try:
   if identity(daemon())!=old_ident:break
  except (OSError,AssertionError,ProcessLookupError):pass
  time.sleep(.5)
 else:raise AssertionError('procd did not replace SIGKILLed monitor')
 good(identity(daemon())!=old_ident,'procd replaces a killed monitor without manual service refresh')
 flows(False,'process replacement preserves outage blocking on IPv4/IPv6 TCP/UDP')
 outage(False);wait(lambda s:s.get('enforcement')=='allowing','checks recover after procd respawn',60)
 # With both independent recovery and service monitoring off, only the kernel
 # lease can revoke a permission when the entire main worker tree is frozen.
 start=observe('before lease-only freeze');lease=int(start['lease_seconds'])
 root=freeze_tree();deadline=time.monotonic()+lease+25
 wait(lambda s:s.get('enforcement')=='blocked','kernel permission expires with detector frozen',lease+25)
 good(identity(root)==frozen[root],'stalled process was not restarted while self-heal is disabled')
 flows(False,'expired kernel permission blocks all four protected paths')
 thaw();wait(lambda s:s.get('enforcement')=='allowing','resumed monitor obtains a new permission',65)
 flows(True,'all four paths recover after fresh probes')
 # Allow one further recovery within a 600-second rolling window.
 current=supervision();recent=[x for x in current.get('restarts',[])if float(Path('/proc/uptime').read_text().split()[0])-x<600]
 assert len(recent)<10,'existing recovery budget prevents isolated one-restart test'
 limit=len(recent)+1
 apply({'self_heal':'1','self_heal_limit':str(limit)})
 wait(lambda s:supervision().get('state')=='healthy'and s.get('enforcement')=='allowing','independent supervisor reaches healthy baseline',120)
 first=observe('before self-heal freeze');threshold=int(supervision()['main_threshold'])
 old=freeze_tree();old_ident=frozen[old]
 wait(lambda s:s.get('enforcement')=='blocked','lease closes access before automatic repair',int(first['lease_seconds'])+25)
 flows(False,'stalled monitor is blocked before the supervisor restarts it')
 end=time.monotonic()+threshold+65
 while time.monotonic()<end:
  try:
   if identity(daemon())!=old_ident:break
  except (OSError,AssertionError,ProcessLookupError):pass
  time.sleep(.7)
 else:raise AssertionError('independent supervisor did not replace frozen monitor tree')
 good(identity(daemon())!=old_ident,'independent supervisor replaces the frozen monitor and inherited lock holders')
 thaw()
 wait(lambda s:s.get('enforcement')=='allowing'and supervision().get('state')=='healthy','automatic repair verifies health before returning to normal',125)
 good(supervision().get('restart_count')==limit,'automatic repair consumed exactly one recovery allowance')
 flows(True,'automatic repair restores all four paths')
 # A second stall must not create a restart loop.
 second=observe('before rate-limit freeze');old=freeze_tree();old_ident=frozen[old]
 wait(lambda s:s.get('enforcement')=='blocked'and supervision().get('state')=='limited','repeated stall reaches the configured recovery limit',threshold+85)
 good(identity(old)==old_ident and supervision().get('restart_count')==limit,'exhausted budget keeps the stalled process without unbounded restarts')
 flows(False,'recovery budget exhaustion keeps all four paths blocked')
 thaw()
 wait(lambda s:s.get('enforcement')=='allowing'and supervision().get('state')=='healthy','manual process recovery still requires successful probes',70)
 good(configs()==before_cfg,'recovery never edits network, firewall, DNS or proxy client configuration')
 good(services()==before_services,'recovery does not restart network, DNS or the active proxy client')
 apply(original);restored=True;wait(lambda s:s.get('enforcement')=='allowing','original confirmed settings restored',150)
 flows(True,'restored confirmed configuration remains usable')
 result['ok']=True
except Exception:
 result['error']=traceback.format_exc();raise
finally:
 thaw();outage(False)
 if original is not None and not restored:
  try:apply(original)
  except Exception:result['cleanup_error']=traceback.format_exc();result['ok']=False
 for name in ['supervision.json','supervision-events.jsonl','worker-health.json','status.json','fast.json']:
  path=Path('/var/run/proxy-guard')/name
  if path.exists():(D/name).write_bytes(path.read_bytes())
 result['finished_at']=time.time();save();(D/'complete.json').write_text(json.dumps(result,indent=2))
