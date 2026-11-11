#!/usr/bin/env python3
"""Bounded steady-state resource and persistent-write observation in an offline router VM."""
from pathlib import Path
import os,sys,json,time,subprocess,hashlib,traceback,statistics
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file() and Path('/etc/openwrt_release').is_file()
D=Path(sys.argv[1]);assert not D.exists();D.mkdir(parents=True)
duration=int(sys.argv[2])if len(sys.argv)>2 else 1200;assert 300<=duration<=1800
checks=[];samples=[];result={'ok':False,'duration_seconds':duration,'checks':checks}
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=30);assert p.returncode==0,(args[:3],p.returncode,p.stderr[-1000:]);return p.stdout
flow_code="\nimport socket,json,concurrent.futures,secrets\nrows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]\ndef one(row):\n name,fam,kind,host=row;s=socket.socket(fam,kind);s.settimeout(3);s.bind(('fd77:88::2'if fam==socket.AF_INET6 else'10.77.0.2',0));token=secrets.token_hex(12).encode()\n try:\n  s.connect((host,23456));s.sendall(token);return name,s.recv(4096)==token\n except OSError:return name,False\n finally:s.close()\nwith concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:print(json.dumps(dict(pool.map(one,rows))))\n"
def probe(label):
 values=json.loads(run(['ip','netns','exec','pglan','python3','-c',flow_code]))
 good(all(v is True for v in values.values()),label+' '+json.dumps(values))
def rpc(o,m,payload=None):
 r=json.loads(run(['ubus','-t','20','call',o,m,json.dumps(payload or {})])or'{}');assert r.get('ok',True)is not False,r;return r
def good(v,label):
 assert v,label;checks.append(label);print('PASS',label,flush=True)
def identities():
 out={}
 for n in ['daemon','fast_watch','supervisor']:
  pid=int(Path('/var/run/proxy-guard/'+n+'.pid').read_text())
  stat=Path('/proc/'+str(pid)+'/stat').read_text().rsplit(') ',1)[1].split()
  assert stat[0]not in ['Z','X']
  argv=Path('/proc/'+str(pid)+'/cmdline').read_bytes()
  assert b'proxy-guard'in argv
  out[n]={'pid':pid,'started':stat[19],'fds':len(list(Path('/proc/'+str(pid)+'/fd').iterdir()))}
 return out
def persistent():
 out={}
 files=[Path('/etc/config/proxy_guard')]+sorted(Path('/etc/proxy-guard').rglob('*'))
 for p in files:
  if p.is_file():
   st=p.stat();out[str(p)]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mtime_ns':st.st_mtime_ns,'size':st.st_size}
 return out
def apply(values,restore=False):
 sid=rpc('session','login',{'username':'root','password':'','timeout':3600})['ubus_rpc_session']
 if restore:
  current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
  for k in current:
   if not k.startswith('.')and k not in values:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':k})
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 value=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if value.get('confirmation_required'):
  tx=value['transaction'];end=time.monotonic()+120
  while time.monotonic()<end:
   t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}
   if t.get('id')==tx['id']and t.get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('steady configuration self-check did not reach confirmation')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
original=None
try:
 manifest=json.loads(Path('/tmp/pg-final-runtime-manifest.json').read_text())
 good(len(manifest['files'])==109 and all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items()),'109 installed final package payload hashes match')
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 original={k:v for k,v in original.items()if not k.startswith('.')}
 (D/'original-config.json').write_text(json.dumps(original,indent=2))
 apply({'enabled':'1','mode':'guard','self_heal':'1','resource_monitor':'1','passwall_watch':'1','passwall_log_watch':'1','client_auto_ports':'1','boot_guard':'0'})
 end=time.monotonic()+240
 while time.monotonic()<end:
  s=rpc('proxy_guard','status')
  if s.get('enforcement')=='allowing' and (not s.get('fast_watch',{}).get('enabled') or s.get('fast_watch',{}).get('phase')=='normal') and s.get('supervision',{}).get('state')=='healthy':break
  time.sleep(2)
 else:raise AssertionError('steady baseline unavailable')
 probe('four protected flows pass before steady observation')
 baseline=identities();files=persistent();initial_restarts=s['supervision']['restart_count'];started=time.monotonic()
 while time.monotonic()-started<duration:
  s=rpc('proxy_guard','status');ids=identities()
  logs={p.name:p.stat().st_size for p in Path('/var/run/proxy-guard').glob('*.jsonl*')if p.is_file()}
  row={'elapsed':time.monotonic()-started,'enforcement':s.get('enforcement'),'phase':s.get('phase'),'fast_phase':s.get('fast_watch',{}).get('phase'),'supervision':s.get('supervision',{}),'processes':ids,'logs':logs}
  samples.append(row);(D/'samples.json').write_text(json.dumps(samples,indent=2))
  assert s.get('enforcement')=='allowing',row
  assert s.get('supervision',{}).get('restart_count',0)<=initial_restarts,row
  assert all((ids[k]['pid'],ids[k]['started'])==(baseline[k]['pid'],baseline[k]['started'])for k in baseline),row
  assert persistent()==files,'persistent configuration or boot-rule file was rewritten during steady probes'
  time.sleep(min(15,max(0,duration-(time.monotonic()-started))))
 probe('four protected flows pass after steady observation')
 good(len(samples)>=duration//20,'steady observation sampled throughout bounded duration')
 good(all(x['enforcement']=='allowing'for x in samples),'protection remained allowing throughout stable checks')
 good(True,'three supervised process identities and recovery counters remained unchanged')
 good(persistent()==files,'no persistent configuration or boot-rule file rewrites during steady probes')
 for name in baseline:
  values=[x['processes'][name]['fds']for x in samples]
  good(max(values)-min(values)<=32,name+' file descriptors stayed within bounded observed range')
 rss=[x['supervision'].get('resources',{}).get('rss_kib')for x in samples];rss=[x for x in rss if isinstance(x,(int,float))]
 good(len(rss)>=len(samples)*.8,'native resource sampler supplied memory observations')
 first=statistics.median(rss[:5]);last=statistics.median(rss[-5:])
 good(last<=first*4+16384,'no large retained-RSS growth in this bounded observation')
 result.update(ok=True,samples=len(samples),rss_kib={'initial_median':first,'final_median':last,'min':min(rss),'max':max(rss)},fd_ranges={k:[min(x['processes'][k]['fds']for x in samples),max(x['processes'][k]['fds']for x in samples)]for k in baseline},limits=['QEMU TCG CPU values are not physical-router performance measurements','20-minute observation does not establish long-term absence of leaks','RSS threshold is a coarse regression guard, not a leak detector'],persistent_files=files)
except Exception:result['error']=traceback.format_exc();print(result['error'],flush=True)
finally:
 if original is not None:
  try:
   apply(original,restore=True)
   actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   assert {k:v for k,v in actual.items()if not k.startswith('.')}==original
   result['original_configuration_restored']=True
  except Exception:result['ok']=False;result['cleanup_error']=traceback.format_exc()
 result['finished']=time.time();(D/'complete.json').write_text(json.dumps(result,indent=2))
