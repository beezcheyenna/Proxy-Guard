#!/usr/bin/env python3
"""Actual OpenWrt RPC/UCI setup acceptance; only in a disposable offline VM."""
from pathlib import Path
import argparse,json,os,subprocess,time,traceback
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file() and Path('/etc/openwrt_release').is_file(), 'isolated OpenWrt VM required'
parser=argparse.ArgumentParser();parser.add_argument('--round',type=int,choices=(1,2),default=1);parser.add_argument('--output',default='/tmp/pg-native-setup.json');args=parser.parse_args()
O=Path(args.output);checks=[];result={'round':args.round,'checks':checks,'ok':False}
def record():
 O.write_text(json.dumps(result,indent=2))
def good(value,name):
 assert value,name
 checks.append(name);record();print('PASS',name,flush=True)
def run(argv,**kw):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=kw.pop('timeout',35),**kw)
 assert p.returncode==0,(argv[:3],p.returncode,(p.stdout+p.stderr)[-1200:])
 return p.stdout
def call(obj,method,payload=None,accept=True):
 p=subprocess.run(['ubus','-t','15','call',obj,method,json.dumps(payload or {})],capture_output=True,text=True,timeout=20)
 try:value=json.loads(p.stdout) if p.stdout.strip() else {}
 except ValueError:raise AssertionError((method,p.returncode,p.stdout[-500:],p.stderr[-500:]))
 if accept:assert p.returncode==0 and value.get('ok',True)!=False,(method,value)
 return value
def wait(fn,label,seconds=110):
 end=time.monotonic()+seconds;last=None
 while time.monotonic()<end:
  last=fn()
  if last:return last
  time.sleep(.5)
 raise AssertionError(label+' '+str(last))
def login():
 auth=json.loads(Path(os.environ.get('PG_TEST_LOGIN','/tmp/pg-browser21-login.json')).read_text())
 return call('session','login',{'username':'root','password':auth['password']})['ubus_rpc_session']
def stage(values,owner=None):
 call('uci','set',{'ubus_rpc_session':owner or sid,'config':'proxy_guard','section':'main','values':values})
def info(owner=None):
 return call('proxy_guard','setup_info',{'ubus_rpc_session':owner or sid})
def apply(values,owner=None):
 owner=owner or sid;stage(values,owner)
 return call('proxy_guard','apply',{'ubus_rpc_session':owner,'confirm_flow':True})
def confirming(owner=None):
 value=info(owner).get('transaction') or {}
 return value if value.get('phase')=='confirming' else None
def finish(tx,method='setup_confirm',owner=None):
 return call('proxy_guard',method,{'ubus_rpc_session':owner or sid,'id':tx['id'],'token':tx['token']})
def off():
 apply({'enabled':'0'})
 wait(lambda:not info().get('transaction'),'explicit off failed',30)
 wait(lambda:call('proxy_guard','status').get('enforcement')=='off','off rules not restored',30)
def trial():
 r=apply({'enabled':'1','mode':'monitor','exit_check':'0','expected_exit4':'','passwall_watch':'0','boot_guard':'0','schedule_enabled':'0'})
 assert r.get('confirmation_required') is True,r
 return wait(lambda:confirming(),'runtime self-check failed to enter confirmation')
try:
 sid=login();other=login();good(sid!=other,'independent real rpcd sessions')
 good(not info().get('transaction'),'no pending transaction after normal installation')
 off();baseline=Path('/etc/config/proxy_guard').read_bytes()
 other_configs={str(p):p.read_bytes()for p in Path('/etc/config').iterdir()if p.is_file()and p.name not in ('proxy_guard','luci')}
 discovery=call('proxy_guard','setup_discover')
 good(discovery.get('read_only') and any(x['device']=='br-lan' and x['recommended'] for x in discovery['interfaces']),'discovery reads actual LAN interface and recommends it')
 good(Path('/etc/config/proxy_guard').read_bytes()==baseline,'discovery does not change committed protection configuration')

 firewall=Path('/etc/config/firewall');firewall_before=firewall.read_bytes()
 try:
  run(['uci','set','firewall.@zone[0].masq=1']);run(['uci','commit','firewall'])
  masq=call('proxy_guard','setup_discover')
  good(any(x['device']=='br-lan' and x['recommended'] for x in masq['interfaces']),'an existing masquerading LAN is still offered without changing NAT')
 finally:firewall.write_bytes(firewall_before)
 good(discovery['defaults']['enabled']=='0' and discovery['defaults']['exit_check']=='0' and discovery['defaults']['setup_complete']=='0','immutable factory defaults keep protection and exit check off')
 stage({'enabled':'1','mode':'monitor'})
 r=call('proxy_guard','apply',{'ubus_rpc_session':sid},False)
 good(r.get('ok') is False and 'Reload' in r.get('error','') and Path('/etc/config/proxy_guard').read_bytes()==baseline,'old page cannot enable without supporting confirmation flow')
 stage({'enabled':'1','exit_check':'1','expected_exit4':'not-an-ip'})
 r=call('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True},False)
 good(r.get('ok') is False and r.get('active_enabled') is False and not info().get('transaction'),'invalid enable fails before commit and clears only the enable draft')
 stage({'exit_check':'0','expected_exit4':''})
 tx=trial()
 good(0<tx['remaining']<=30,'countdown starts at 30 seconds after actual runtime self-check')
 alien=info(other)['transaction']
 good(not alien['owned'] and 'token'not in alien,'foreign session cannot read confirmation secret')
 denied=call('proxy_guard','setup_confirm',{'ubus_rpc_session':other,'id':tx['id'],'token':tx['token']},False)
 good(denied.get('ok') is False,'foreign session cannot confirm even with copied token')
 r=call('proxy_guard','apply',{'ubus_rpc_session':other,'confirm_flow':True},False)
 good(r.get('ok') is False,'second enabled apply cannot replace pending transaction')
 finish(tx)
 good(not info().get('transaction') and info()['last_result']['phase']=='confirmed','explicit confirmation accepts candidate')
 good(call('proxy_guard','status')['enforcement']=='off','monitor-only mode never installs blocking rules')
 previous=call('proxy_guard','setup_previous')
 good(previous['draft']['enabled']=='1' and previous['draft']['mode']=='monitor','restore entry loads latest confirmed configuration')
 off();baseline=Path('/etc/config/proxy_guard').read_bytes()
 tx=trial();finish(tx,'setup_cancel')
 good(Path('/etc/config/proxy_guard').read_bytes()==baseline and not info().get('transaction'),'cancel restores exact previous configuration')
 good(call('proxy_guard','status')['enforcement']=='off','cancel restores effective disabled rule state')
 tx=trial();time.sleep(tx['remaining']+4)
 wait(lambda:not info().get('transaction'),'backend did not time out',15)
 good(Path('/etc/config/proxy_guard').read_bytes()==baseline,'without browser activity countdown restores exact configuration')
 good(info()['last_result']['phase']=='rolled_back' and info()['last_result']['reason']=='confirmation_timeout','timeout records rollback rather than success')
 late=call('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']},False)
 good(late.get('ok') is False,'late confirmation cannot reactivate expired settings')
 # Standard LuCI global UCI commit must enter the same confirmation mechanism.
 stage({'enabled':'1','mode':'monitor','exit_check':'0','passwall_watch':'0','boot_guard':'0','schedule_enabled':'0'})
 call('uci','commit',{'ubus_rpc_session':sid,'config':'proxy_guard'})
 unclaimed=wait(lambda:(info().get('transaction')or{}).get('claimable') and info()['transaction'],'global Apply was not observed')
 good('token'not in unclaimed,'external Apply does not expose unclaimed token')
 claimed=call('proxy_guard','setup_claim',{'ubus_rpc_session':sid})['transaction']
 good(claimed['owned'] and claimed['remaining']<=120,'authenticated page claims global Apply without resetting timer')
 tx=wait(lambda:confirming(),'claimed runtime self-check failed');finish(tx)
 off();baseline=Path('/etc/config/proxy_guard').read_bytes()
 if args.round==2:
  tx=trial()
  Path('/etc/proxy-guard/setup/pending.json').write_text('{}')
  wait(lambda:not Path('/etc/proxy-guard/setup/pending.json').exists(),'invalid journal did not recover',45)
  good(Path('/etc/config/proxy_guard').read_bytes()==baseline,'valid JSON with invalid journal schema restores independent backup')
  tx=trial()
  run(['/etc/init.d/proxy-guard','stop'],timeout=90)
  wait(lambda:not info().get('transaction'),'manual stop did not cancel trial',40)
  good(Path('/etc/config/proxy_guard').read_bytes()==baseline and Path('/var/run/proxy-guard/stopped').exists(),'explicit service stop cancels pending trial without restarting it')
  run(['/etc/init.d/proxy-guard','start'],timeout=90)
  wait(lambda:call('proxy_guard','status').get('enforcement')=='off','explicit restart off state',40)
 good(all(Path(name).read_bytes()==data for name,data in other_configs.items()),'setup leaves network, firewall, DNS and client configuration untouched')
 result['ok']=True
except Exception:
 result['error']=traceback.format_exc();print(result['error'],flush=True)
finally:
 record()
raise SystemExit(0 if result['ok']else 1)
