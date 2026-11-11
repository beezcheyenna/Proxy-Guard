from pathlib import Path
import subprocess,json,time,sys,traceback
assert Path('/etc/pgvm-fixture').is_file()
client,root=sys.argv[1:];Q=Path(root);Q.mkdir(parents=True)
def rpc(o,m,a):
 p=subprocess.run(['ubus','-t','30','call',o,m,json.dumps(a)],capture_output=True,text=True,timeout=40)
 assert p.returncode==0,p.stderr
 d=json.loads(p.stdout or'{}');assert d.get('ok',True),(m,d);return d
try:
 sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 Path('/tmp/pg-latest-login.json').write_text(json.dumps({'password':''}));Path('/tmp/pg-latest-login.json').chmod(0o600)
 profile=json.loads(subprocess.check_output(['ucode','/usr/lib/proxy-guard/inspect-client.uc',client],text=True))
 assert profile.get('available'),profile
 vals={'enabled':'1','mode':'guard','proxy_client':client,'client_auto_ports':'1','passwall_watch':'1','passwall_log_watch':'1','boot_guard':'1','self_heal':'1','fast_wait_enabled':'1','fast_wait_seconds':'15','fast_stable_enabled':'1','fast_stable_seconds':'60','cf_event_check':'0','udp_check':'1'if profile['required'].get('udp')else'0','exit_check':'1','expected_exit4':'9.9.9.9','exit_url':'https://api.ipify.org','exit_fallback_url':'https://4.ident.me','interval':'5','timeout':'3','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0','interfaces':['br-lan'],'sources4':['10.77.0.0/24'],'sources6':['fd77:88::/64'],'local4':['10.77.0.0/24'],'local6':['fd77:88::/64'],'ipv6_protect':'1'}
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':vals})
 d=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 assert d.get('confirmation_required'),d
 tx=d['transaction'];end=time.monotonic()+100
 while time.monotonic()<end:
  t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
  if t.get('phase')=='confirming':break
  time.sleep(.5)
 else:raise AssertionError('actual rule self check did not reach confirmation')
 rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
 result={'ok':True,'client':client,'explicit_fixture_configuration':vals,'profile_required':profile['required'],'state':rpc('proxy_guard','status',{})}
except Exception:result={'ok':False,'error':traceback.format_exc()}
(Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
