#!/usr/bin/env python3
"""Native package migration with real UCI, including an unrelated pending CLI edit."""
from pathlib import Path
import os,sys,subprocess,json,time,hashlib,traceback,shlex,shutil
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file()
stage=Path(sys.argv[1]);D=Path(sys.argv[2]);D.mkdir(parents=True);checks=[];original=None;r={'ok':False,'checks':checks}
def run(a,timeout=60):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 with(D/'commands.log').open('a')as f:f.write(repr(a)+'\n'+p.stdout+p.stderr+'\n')
 assert p.returncode==0,(a[:3],p.returncode,p.stderr[-1200:]);return p.stdout
def rpc(o,m,p=None,allow_busy=False):
 v=json.loads(run(['ubus','-t','30','call',o,m,json.dumps(p or{})],40)or'{}');assert v.get('ok',True)is not False or (allow_busy and v.get('error')=='setup_transaction_busy'),(o,m,v);return v
def good(v,label):
 assert v,label
 checks.append(label);print('PASS',label,flush=True)
def apply(values,cleanup=False):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 deadline=time.monotonic()+10
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True},allow_busy=cleanup)
 while cleanup and a.get('error')=='setup_transaction_busy' and time.monotonic()<deadline:
  info=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid})
  assert not info.get('transaction'),'cleanup must not cancel or replace an active transaction'
  with(D/'cleanup-busy-retries.jsonl').open('a')as f:f.write(json.dumps({'at':time.time(),'error':a['error'],'active_transaction':False})+'\n')
  time.sleep(.25)
  a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True},allow_busy=True)
 assert a.get('ok')is True,a
 if a.get('confirmation_required'):
  tx=a['transaction'];end=time.monotonic()+120
  while time.monotonic()<end:
   t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
   if t.get('id')==tx['id']and t.get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('self-check confirmation')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
def disk_values():
 current=False;out={}
 for line in Path('/etc/config/proxy_guard').read_text().splitlines():
  t=shlex.split(line,comments=True)
  if not t:continue
  if t[0]=='config':current=len(t)>2 and t[2]=='main'
  elif current and len(t)==3:
   if t[0]=='option':out[t[1]]=t[2]
   elif t[0]=='list':out.setdefault(t[1],[]).append(t[2])
 return out
def fixture(targets,exit_url):
 run(['uci','-q','delete','proxy_guard.main.targets'])
 for value in targets:run(['uci','add_list','proxy_guard.main.targets='+value])
 run(['uci','set','proxy_guard.main.exit_url='+exit_url]);run(['uci','set','proxy_guard.main.interval=17']);run(['uci','commit','proxy_guard'])
def platform_configs():
 return {n:hashlib.sha256(Path('/etc/config/'+n).read_bytes()).hexdigest()for n in ['network','firewall','dhcp','system']if Path('/etc/config/'+n).exists()}
try:
 good(not run(['uci','changes','proxy_guard']).strip(),'no pre-existing CLI changes are overwritten')
 platform_before=platform_configs();sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 original={k:v for k,v in rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'].items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original,indent=2))
 apply({'enabled':'0'})
 end=time.monotonic()+50
 while time.monotonic()<end:
  if rpc('proxy_guard','status').get('enforcement')=='off':break
  time.sleep(.5)
 good(rpc('proxy_guard','status').get('enforcement')=='off','public apply disables protection before the migration scenario')
 old=['https://www.gstatic.com/generate_204|204','https://www.google.com/generate_204|204']
 fixture(old,'https://www.cloudflare.com/cdn-cgi/trace')
 run(['uci','set','proxy_guard.main.interval=47'])
 if shutil.which('apk'):
  run(['apk','--no-network','--allow-untrusted','add','--force-reinstall',str(stage/'packages/luci-app-proxy-guard-0.3.0-r21.apk')],300)
 else:
  run(['opkg','--force-reinstall','install',str(stage/'packages/luci-app-proxy-guard_0.3.0-21_all.ipk')],300)
 values=disk_values();r['migrated_values']={k:values.get(k)for k in ['targets','exit_url','interval','enabled']}
 good(values['targets']==[old[0],'https://connectivity-check.ubuntu.com/|204']and values['exit_url']=='https://api.ipify.org/','real install hook migrates exactly recognized old endpoint presets')
 good(values['interval']=='17'and values['enabled']=='0','install migration preserves committed custom timing and disabled state')
 pending=run(['uci','changes','proxy_guard']);r['pending_changes_after_install']=pending
 good('proxy_guard.main.interval='in pending and '47'in pending,'install migration does not commit or discard the unrelated pending CLI edit')
 good(rpc('proxy_guard','status').get('enforcement')=='off','post-install RPC is available without manual service refresh')
 run(['uci','revert','proxy_guard.main.interval'])
 custom=old+['https://custom.example.test/check|204']
 fixture(custom,'https://custom.example.test/ip')
 before=Path('/etc/config/proxy_guard').read_bytes()
 run(['/usr/libexec/proxy-guard-migrate'])
 good(Path('/etc/config/proxy_guard').read_bytes()==before and disk_values()['targets']==custom,'custom three-target configuration and exit endpoint are preserved')
 run(['/usr/libexec/proxy-guard-migrate'])
 good(Path('/etc/config/proxy_guard').read_bytes()==before,'native migration is idempotent')
 good(platform_configs()==platform_before,'migration leaves network firewall DNS and system configuration unchanged')
 r['ok']=True
except Exception:r['error']=traceback.format_exc();print(r['error'],flush=True)
finally:
 if original is not None:
  try:
   pending=run(['uci','changes','proxy_guard'])
   if 'proxy_guard.main.interval='in pending:run(['uci','revert','proxy_guard.main.interval'])
   current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   for key in current:
    if not key.startswith('.')and key not in original:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':key})
   apply(original,cleanup=True)
   actual={k:v for k,v in rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'].items()if not k.startswith('.')}
   assert actual==original
   r['original_configuration_restored']=True
  except Exception:r['ok']=False;r['cleanup_error']=traceback.format_exc()
 r['finished']=time.time();(D/'complete.json').write_text(json.dumps(r,indent=2))
