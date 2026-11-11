from pathlib import Path
import subprocess,json,hashlib,time,sys,traceback,os,shutil
assert Path('/etc/pgvm-fixture').exists()
ROOT=Path('/mnt/pg-candidate')
PKGS=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'packages'
OUT=Path('/tmp/pg-lifecycle')
OUT.mkdir(exist_ok=True)
IS_APK=shutil.which('apk') is not None
SUFFIX='.apk'if IS_APK else'.ipk'
B=next(f for f in PKGS.glob('*'+SUFFIX)if 'guard-pro'not in f.name)
P=next(f for f in PKGS.glob('*'+SUFFIX)if 'guard-pro'in f.name)
checks=[]
def run(args,ok=True,timeout=150):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 with(OUT/'commands.log').open('a')as f:f.write(json.dumps({'argv':args,'rc':p.returncode,'out':p.stdout,'err':p.stderr},ensure_ascii=False)+'\n')
 if ok:assert p.returncode==0,(args,p.returncode,p.stdout[-1500:],p.stderr[-1500:])
 return p
def record(name,**values):
 checks.append({'name':name,**values});(OUT/'results.json').write_text(json.dumps(checks,indent=2));print('PASS',name,flush=True)
def ubus(obj,method,args=None):
 return json.loads(run(['ubus','-t','30','call',obj,method,json.dumps(args or{})]).stdout)
def install(path,reinstall=False):
 if IS_APK:
  args=['apk','--no-network','--allow-untrusted','add',str(path)]
  if reinstall:args=['apk','--no-network','--allow-untrusted','add','--force-reinstall',str(path)]
 else:args=['opkg','install']+(['--force-reinstall']if reinstall else[])+[str(path)]
 result=run(args)
 if reinstall:
  assert '[APK unavailable'not in result.stdout+result.stderr,(result.stdout,result.stderr)
  if IS_APK:assert 'Reinstalling'in result.stdout+result.stderr,(result.stdout,result.stderr)
 return result
def digest(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
def rpc(sid,obj,method,args=None):
 payload=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':[sid,obj,method,args or{}]})
 text=run(['curl','--noproxy','*','-sS','--max-time','25','http://127.0.0.1/ubus','-H','Content-Type: application/json','--data-binary',payload]).stdout
 return json.loads(text)
def status(obj='proxy_guard'):
 return ubus(obj,'status')
def clean_system():
 return {str(p):digest(p)for n in ['network','firewall','dhcp']if(p:=Path('/etc/config')/n).exists()}
try:
 before=clean_system()
 # This session is created before installation; no rpcd reload in the test.
 session=ubus('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 assert not run(['ubus','list','proxy_guard'],ok=False).stdout.strip()
 record('clean firmware has no Proxy Guard RPC object')
 install(B)
 s=status();assert not s.get('enabled') and s.get('enforcement')!='blocked',s
 record('fresh standard install immediately registers RPC and stays disabled',status=s)
 r=rpc(session,'proxy_guard','status');assert r.get('result',[99])[0]==0,r
 record('pre-install login session accesses native HTTP RPC after install')
 r=rpc('0'*32,'proxy_guard','apply');assert r.get('error',{}).get('code')==-32002 or r.get('result',[0])[0]==6,r
 record('unauthenticated HTTP mutation is denied')
 text=run(['curl','--noproxy','*','-fsS','--max-time','15','http://127.0.0.1/luci-static/resources/view/proxy-guard/overview.js']).stdout
 assert hashlib.sha256(text.encode()).hexdigest()==digest('/www/luci-static/resources/view/proxy-guard/overview.js')
 record('real HTTP serves the installed Standard view')
 for locale in ['en','zh-cn','ja','ru','fa']:
  assert Path('/usr/lib/lua/luci/i18n/proxy-guard.'+locale+'.lmo').stat().st_size>0
 record('all five Standard catalogs installed')
 run(['uci','set','proxy_guard.main.interval=17']);run(['uci','commit','proxy_guard'])
 base_conf=digest('/etc/config/proxy_guard')
 base_files={str(x):digest(x)for x in [Path('/usr/lib/proxy-guard/core.lua'),Path('/www/luci-static/resources/view/proxy-guard/overview.js')]}
 install(P)
 assert not status('proxy_guard_access').get('enabled')
 assert digest('/etc/config/proxy_guard')==base_conf
 assert all(digest(k)==h for k,h in base_files.items())
 assert Path('/etc/config/proxy_guard_access').stat().st_mode&0o777==0o600
 assert rpc(session,'proxy_guard_access','status').get('result',[99])[0]==0
 record('fresh Pro install preserves Standard and registers Pro RPC for old session')
 for locale in ['en','zh-cn','ja','ru','fa']:
  assert Path('/usr/lib/lua/luci/i18n/proxy-guard-pro.'+locale+'.lmo').stat().st_size>0
 record('all five Pro catalogs are owned by Pro')
 install(P,True)
 assert digest('/etc/config/proxy_guard')==base_conf and all(digest(k)==h for k,h in base_files.items())
 assert rpc(session,'proxy_guard_access','status').get('result',[99])[0]==0
 record('Pro force-reinstall is independent of Standard')
 pro_conf=digest('/etc/config/proxy_guard_access')
 install(B,True)
 assert digest('/etc/config/proxy_guard')==base_conf
 assert digest('/etc/config/proxy_guard_access')==pro_conf
 assert rpc(session,'proxy_guard','status').get('result',[99])[0]==0
 record('Standard force-reinstall preserves both configurations and Pro')
 run(['apk','--no-network','del','luci-app-proxy-guard-pro']if IS_APK else['opkg','remove','luci-app-proxy-guard-pro'])
 assert not run(['ubus','list','proxy_guard_access'],ok=False).stdout.strip()
 assert rpc(session,'proxy_guard','status').get('result',[99])[0]==0
 assert digest('/etc/config/proxy_guard')==base_conf
 record('Pro removal retains functioning Standard')
 run(['apk','--no-network','del','luci-app-proxy-guard']if IS_APK else['opkg','remove','luci-app-proxy-guard'])
 assert not run(['ubus','list','proxy_guard'],ok=False).stdout.strip()
 assert not Path('/etc/rc.d/S18proxy-guard').exists()
 assert not Path('/usr/libexec/proxy-guard').exists()
 assert 'proxy_guard'not in run(['nft','list','tables']).stdout
 assert clean_system()==before
 record('Standard uninstall clears owned hooks and rules, preserves network firewall DNS configs')
 if '--leave-installed'in sys.argv[2:]:
  install(B);install(P)
  assert not status().get('enabled')and not status('proxy_guard_access').get('enabled')
  assert clean_system()==before
  record('native packages can be installed again after removal and remain disabled')
 result={'ok':True,'package_manager':'apk'if IS_APK else'opkg','checks':checks}
except Exception:
 result={'ok':False,'package_manager':'apk'if IS_APK else'opkg','checks':checks,'error':traceback.format_exc()}
(OUT/'complete.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

raise SystemExit(0 if result['ok'] else 1)
