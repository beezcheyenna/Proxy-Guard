#!/usr/bin/env python3
"""Install the exact candidate through the native package manager, without service fixes."""
from pathlib import Path
import os,sys,json,subprocess,hashlib,tarfile,io,traceback,shutil,time
assert Path('/etc/pgvm-fixture').is_file()
stage=Path(sys.argv[1]);D=Path('/root/pg-acceptance/candidate8-install');D.mkdir(parents=True)
r={'ok':False,'checks':[]};(D/'test-driver.py').write_bytes(Path(__file__).read_bytes())
def cmd(a,timeout=240):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 with(D/'commands.log').open('a')as f:f.write(repr(a)+'\n'+p.stdout+p.stderr+'\n')
 assert p.returncode==0,(a,p.returncode,p.stderr[-900:]);return p.stdout
def rpc(o,m,d):
 value=json.loads(cmd(['ubus','-t','30','call',o,m,json.dumps(d)],45)or'{}')
 assert value.get('ok',True)is not False,(o,m,value);return value
def good(v,n):assert v,n;r['checks'].append(n);print('PASS '+n,flush=True)
def cfg():
 return {str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in Path('/etc/config').iterdir()if p.is_file()and not p.name.endswith(('-opkg','.apk-new','.apk-old'))}
try:
 before=cfg();sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
 packs=stage/'packages'
 if shutil.which('apk'):
  cmd(['apk','--no-network','--allow-untrusted','add','--force-reinstall',str(packs/'luci-app-proxy-guard-0.3.0-r21.apk'),str(packs/'luci-app-proxy-guard-pro-0.3.1-r5.apk')])
  versions=cmd(['apk','list','--installed','luci-app-proxy-guard','luci-app-proxy-guard-pro'])
  good('0.3.0-r21'in versions and '0.3.1-r5'in versions,'native APK installed both intended package versions')
 else:
  cmd(['opkg','--force-reinstall','install',str(packs/'luci-app-proxy-guard_0.3.0-21_all.ipk'),str(packs/'luci-app-proxy-guard-pro_0.3.1-5_all.ipk')])
  versions='\n'.join(cmd(['opkg','status',name])for name in ['luci-app-proxy-guard','luci-app-proxy-guard-pro'])
  good('Version: 0.3.0-21'in versions and 'Version: 0.3.1-5'in versions,'native IPK installed both intended package versions')
 r['versions']=versions
 after=cfg();r['configuration_before']=before;r['configuration_after']=after
 good(before==after,'native reinstall preserves all saved router and plugin configurations')
 checked={}
 for p in packs.glob('*.ipk'):
  with tarfile.open(p)as t:parts={Path(m.name).name:t.extractfile(m).read()for m in t if m.isfile()}
  with tarfile.open(fileobj=io.BytesIO(parts['control.tar.gz']))as t:
   controls={Path(m.name).name:t.extractfile(m).read().decode()for m in t if m.isfile()}
  confs={x.lstrip('/')for x in controls['conffiles'].splitlines()}
  with tarfile.open(fileobj=io.BytesIO(parts['data.tar.gz']))as t:
   for m in t:
    if not m.isfile():continue
    rel=m.name.removeprefix('./');path=Path('/')/rel
    if rel in confs:
     mode=path.stat().st_mode&0o777
     assert mode&~m.mode==0 and mode&0o600==0o600,('configuration permission exceeds package policy',str(path),oct(mode),oct(m.mode))
     continue
    good_mode=(path.stat().st_mode&0o777)==m.mode
    assert good_mode,('installed permission',str(path),oct(path.stat().st_mode&0o777),oct(m.mode))
    digest=hashlib.sha256(t.extractfile(m).read()).hexdigest()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,('installed payload',str(path))
    checked[str(path)]=digest
 good(len(checked)==109,'all 109 non-configuration program/resource files and package permissions match actual artifacts')
 r['installed_file_sha256']=checked
 manifest=json.loads((stage/'runtime-manifest.json').read_text())
 good(all(checked.get(p)==v for p,v in manifest['files'].items()),'critical runtime manifest matches the final candidate')
 Path('/tmp/pg-final-runtime-manifest.json').write_text(json.dumps(manifest,indent=2))
 access=rpc('session','access',{'ubus_rpc_session':sid,'scope':'ubus','object':'proxy_guard','function':'status'})
 good(access.get('access')is True,'pre-install login session retains its existing status permission')
 state=rpc('proxy_guard','status',{});r['state_after_install']=state
 good('enforcement'in state,'status RPC is registered through installation hooks without a manual refresh')
 # The new persistent ucode module must take effect through package hooks,
 # before any acceptance test changes configuration or restarts a service.
 active={}
 for key in ['enabled','passwall_watch','passwall_log_watch']:
  p=subprocess.run(['uci','-q','get','proxy_guard.main.'+key],capture_output=True,text=True)
  active[key]=p.stdout.strip()
 if all(v=='1'for v in active.values()):
  end=time.monotonic()+45;samples=[]
  while time.monotonic()<end:
   try:
    fast=json.loads(Path('/var/run/proxy-guard/fast.json').read_text())
    cursor=fast.get('log_cursor')or{}
    samples.append({'time':time.time(),'encoding':cursor.get('buffer_encoding'),'phase':fast.get('phase')})
    if cursor.get('buffer_encoding')=='base64':break
   except (OSError,UnicodeDecodeError,json.JSONDecodeError)as error:
    samples.append({'time':time.time(),'error':str(error)})
   time.sleep(.5)
  r['live_module_samples']=samples
  good(bool(samples)and samples[-1].get('encoding')=='base64','installation hooks activate the new persistent log module without a manual restart')
 else:r['live_module_check']='inactive log monitoring; checked when explicitly enabled in the next focused test'
 r['ok']=True
except Exception:r['error']=traceback.format_exc();print(r['error'],flush=True)
r['finished_at']=time.time();(D/'complete.json').write_text(json.dumps(r,indent=2))
raise SystemExit(0 if r['ok']else 1)
