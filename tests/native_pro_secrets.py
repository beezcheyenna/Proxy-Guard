#!/usr/bin/env python3
"""Legacy credential upgrade/old-session regression in a marked disposable VM.
Provide a fixture read-only LuCI login; never run on a router in active use.
"""
from pathlib import Path
import argparse,base64,hashlib,json,os,secrets,stat,subprocess,urllib.request
p=argparse.ArgumentParser();p.add_argument('--package','--ipk',dest='package',type=Path,required=True);p.add_argument('--reader-login',type=Path,required=True);a=p.parse_args()
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file(),'dedicated isolated VM required'
login=json.loads(a.reader_login.read_text());config=Path('/etc/config/proxy_guard_access');before=config.read_bytes()
keys={p.name:(p.read_bytes(),stat.S_IMODE(p.stat().st_mode))for p in Path('/etc/proxy-guard-access').glob('*.key')};sessions=[];checks={}
def cli(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=180);assert r.returncode==0,str(args[:2])+': '+str(r.returncode);return r.stdout
def call(sid,obj,method,data):
 q={'jsonrpc':'2.0','id':1,'method':'call','params':[sid,obj,method,data]};req=urllib.request.Request('http://127.0.0.1/ubus/',data=json.dumps(q).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=20)as r:return json.load(r)
def code(r):return r.get('result',[None])[0]
def session():
 r=call('0'*32,'session','login',{'username':login['username'],'password':login['password'],'timeout':600});assert code(r)==0
 sid=r['result'][1]['ubus_rpc_session'];sessions.append(sid);return sid
def check(n,v):checks[n]=bool(v);print(('PASS 'if v else'FAIL ')+n,flush=True);assert v,n
legacy={'device_token':secrets.token_urlsafe(40),'path_token':secrets.token_urlsafe(40)}
try:
 for k,v in {'enabled':'0',**legacy}.items():cli(['uci','set','proxy_guard_access.main.'+k+'='+v])
 cli(['uci','commit','proxy_guard_access']);old=session()
 r=call(old,'uci','get',{'config':'proxy_guard_access','section':'main'})
 check('fixture models readable committed legacy secrets',code(r)==0 and all(v in json.dumps(r)for v in legacy.values()))
 assert a.package.suffix in ('.ipk','.apk'),'a native package artifact is required'
 package_args=['apk','--no-network','--allow-untrusted','add','--force-reinstall'] if a.package.suffix=='.apk' else ['opkg','--force-reinstall','install']
 install_log=cli(package_args+[str(a.package.resolve())])
 if a.package.suffix=='.apk':check('native APK reinstall actually executed','Reinstalling luci-app-proxy-guard-pro' in install_log and 'unavailable' not in install_log)
 values=json.loads(cli(['ubus','call','uci','get',json.dumps({'config':'proxy_guard_access','section':'main'})]))['values']
 check('disabled state survives upgrade',values.get('enabled')=='0')
 check('supported legacy secret fields leave UCI',all(k not in values for k in legacy))
 for name,file in [('device_token','device.key'),('path_token','path.key')]:
  f=Path('/etc/proxy-guard-access')/file;check(name+' moves privately without changing its value',f.read_text()==legacy[name]and stat.S_IMODE(f.stat().st_mode)==0o600)
 for label,sid in [('old',old),('new',session())]:
  for obj,method,data in [('uci','get',{'config':'proxy_guard_access','section':'main'}),('proxy_guard_access','status',{}),('proxy_guard_access','raw_info',{})]:
   r=call(sid,obj,method,data);check(label+' session '+method+' stays usable without secrets',code(r)==0 and all(v not in json.dumps(r)for v in legacy.values()))
  for method in ['apply','restart_xray','reboot_vps']:
   r=call(sid,'proxy_guard_access',method,{});check(label+' session '+method+' stays denied',code(r)==6 or r.get('error',{}).get('code')==-32002)
 check('migration is idempotent',json.loads(cli(['/usr/libexec/proxy-guard-access-migrate-secrets'])).get('migrated')==0)
 extra=secrets.token_urlsafe(40);cli(['uci','set','proxy_guard_access.main.path_token='+extra]);cli(['uci','commit','proxy_guard_access']);cli(['/etc/init.d/proxy-guard-access','start'])
 values=json.loads(cli(['ubus','call','uci','get',json.dumps({'config':'proxy_guard_access','section':'main'})]))['values']
 check('disabled startup also migrates credentials','path_token'not in values and Path('/etc/proxy-guard-access/path.key').read_text()==extra)
 print(json.dumps({'ok':True,'checks':len(checks)}))
finally:
 for sid in sessions:
  subprocess.run(['ubus','call','session','destroy',json.dumps({'ubus_rpc_session':sid})],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 config.write_bytes(before);config.chmod(0o600)
 for f in Path('/etc/proxy-guard-access').glob('*.key'):
  if f.name not in keys:f.unlink()
 for name,(data,mode)in keys.items():
  f=Path('/etc/proxy-guard-access')/name;f.write_bytes(data);f.chmod(mode)
