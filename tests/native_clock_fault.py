#!/usr/bin/env python3
"""Actual process failure and kernel-permit acceptance in a marked offline VM."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,hashlib,tempfile,traceback
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file() and Path('/etc/openwrt_release').is_file()
D=Path(sys.argv[1] if len(sys.argv)>1 else '/root/pg-acceptance/candidate10-clock')
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
 sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
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

reference_wall=time.time();reference_mono=time.monotonic()
def set_clock(offset):
 target=reference_wall+(time.monotonic()-reference_mono)+offset
 time.clock_settime(time.CLOCK_REALTIME,target)
 actual=time.time()
 good(abs(actual-target)<3,'guest realtime shifted by '+str(offset)+' seconds')
def restore_config(values):
 sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 for k in current:
  if not k.startswith('.') and k not in values:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':k})
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if a.get('confirmation_required'):
  tx=a['transaction'];end=time.monotonic()+120
  while time.monotonic()<end:
   t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
   if t.get('id')==tx['id'] and t.get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('restore confirmation self-check timeout')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
 return sid
original=None
try:
 manifest=json.loads(Path('/tmp/pg-final-runtime-manifest.json').read_text())
 good(len(manifest['files'])==109 and all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items()),'109 final package payload hashes match')
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'];original={k:v for k,v in original.items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original,indent=2));before_cfg=configs();before_services=services()
 profile=json.loads(run('ucode','/usr/lib/proxy-guard/inspect-client.uc',original['proxy_client']).stdout)
 good(profile.get('available')is True,'actual selected client listener profile available')
 settings={'enabled':'1','mode':'guard','passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','self_heal':'0','cf_event_check':'0','exit_check':'0','udp_check':'0','interval':'5','timeout':'2','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0','client_auto_ports':'0','socks_port':str(profile['socks_port']),'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':sorted(set(['53']+[str(x)for x in profile['dns_ports']]))}
 apply(settings);wait(lambda s:s.get('enforcement')=='allowing','baseline allowing',90);flows(True,'four-flow baseline')
 for offset in [-600,600]:
  wait(lambda s:s.get('enforcement')=='allowing','healthy before clock shift',90)
  baseline=observe('before clock shift '+str(offset));lease=int(baseline['lease_seconds'])
  pid=freeze_tree();ident=frozen[pid];started=time.monotonic();set_clock(offset)
  early=state();elapsed=time.monotonic()-started
  good(elapsed<lease-8 and early.get('enforcement')=='allowing','wall clock shift alone does not immediately expire the kernel permit')
  flows(True,'permission remains active immediately after realtime shift '+str(offset))
  wait(lambda s:s.get('enforcement')=='blocked','monotonic kernel expiry after clock shift '+str(offset),lease+25)
  good(time.monotonic()-started<=lease+30 and identity(pid)==ident,'frozen worker and expiry deadline are unaffected by realtime shift')
  flows(False,'expired permit blocks IPv4/IPv6 TCP/UDP after realtime shift '+str(offset))
  thaw();set_clock(0);wait(lambda s:s.get('enforcement')=='allowing','fresh probes restore permission after clock test',90);flows(True,'four flows restored after clock test '+str(offset))
 # The user confirmation window must also be monotonic.
 sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 before=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':{'fail_threshold':'2'}})
 trial=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True});good(trial.get('confirmation_required')is True,'real RPC creates confirmation trial')
 tx=trial['transaction'];end=time.monotonic()+120
 while time.monotonic()<end:
  info=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid});t=info.get('transaction')or{}
  if t.get('id')==tx['id'] and t.get('phase')=='confirming':break
  time.sleep(.5)
 else:raise AssertionError('trial did not reach confirmation')
 remaining=t['remaining'];started=time.monotonic();set_clock(600)
 info=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid});t=info.get('transaction')or{}
 good(t.get('id')==tx['id'] and t.get('phase')=='confirming' and t.get('remaining',0)>=remaining-8,'forward wall clock jump does not end the confirmation window early')
 end=time.monotonic()+remaining+15
 while time.monotonic()<end:
  info=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid})
  if not info.get('transaction'):break
  time.sleep(.7)
 good(not info.get('transaction') and info.get('last_result',{}).get('reason')=='confirmation_timeout','unconfirmed trial rolls back after monotonic deadline')
 good(time.monotonic()-started>=remaining-5,'rollback did not happen immediately after clock jump')
 actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 good(actual==before,'clock-shifted rollback restores complete saved configuration')
 set_clock(0)
 good(configs()==before_cfg,'clock acceptance leaves network, firewall, DNS and client files unchanged')
 good(services()==before_services,'clock acceptance does not restart unrelated services or proxy cores')
 result['ok']=True
except Exception:result['error']=traceback.format_exc();print(result['error'],flush=True)
finally:
 thaw()
 try:
  time.clock_settime(time.CLOCK_REALTIME,reference_wall+(time.monotonic()-reference_mono));result['clock_restored']=abs(time.time()-(reference_wall+(time.monotonic()-reference_mono)))<3
  if original is not None:
   restore_config(original)
   actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   assert {k:v for k,v in actual.items()if not k.startswith('.')}==original
   wait(lambda s:s.get('enforcement')=='allowing','original configuration recovery',180)
   result['original_configuration_restored']=True
 except Exception:result['ok']=False;result['cleanup_error']=traceback.format_exc()
 result['finished']=time.time();save();(D/'complete.json').write_text(json.dumps(result,indent=2))
