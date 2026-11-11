#!/usr/bin/env python3
"""Real TLS/SOCKS primary/fallback endpoint acceptance in a private test namespace."""
from pathlib import Path
import json,subprocess,time,os,signal,uuid,traceback,shutil,sys
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
Q=Path(sys.argv[2] if len(sys.argv)>2 else '/tmp/pg-exit-fixture');Q.mkdir(parents=True)
client=sys.argv[1] if len(sys.argv)>1 else 'passwall'
assert client in ['passwall','nikki','homeproxy']
checks=[];server=None;old_server=None;old_command=None;original=None;result={'ok':False}
def run(args,timeout=60,check=True,**kw):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,**kw)
 if check:assert p.returncode==0,(args[:3],p.returncode,p.stderr[-600:])
 return p.stdout
def rpc(o,m,d=None):
 x=json.loads(run(['ubus','-t','20','call',o,m,json.dumps(d or{})],timeout=25)or'{}')
 assert x.get('ok',True),(m,x);return x
def status():return rpc('proxy_guard','status')
def good(c,n):assert c,n;checks.append(n);print('PASS '+n,flush=True)
def wait(fn,label,seconds=90):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  d=fn()
  if d:return d
  time.sleep(.6)
 raise AssertionError(label)
def apply(values):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 r=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if r.get('confirmation_required'):
  t=r['transaction'];wait(lambda:(rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}).get('phase')=='confirming','self-check')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':t['id'],'token':t['token']})
def stop_pid(pid):
 p=Path('/proc')/str(pid)
 if not p.exists():return
 os.kill(pid,signal.SIGTERM)
 wait(lambda:not p.exists()or p.joinpath('stat').read_text().split(') ',1)[1].startswith('Z'),'owned fixture process stop',15)
flow_code="""import socket,concurrent.futures,json
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def f(r):
 n,a,t,h=r;s=socket.socket(a,t);s.bind(('fd77:88::2'if a==socket.AF_INET6 else'10.77.0.2',0));s.settimeout(2)
 try:s.connect((h,23456));s.sendall(b'fallback-fixture');return n,s.recv(40)==b'fallback-fixture'
 except OSError:return n,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(f,rows))))
"""
def flows():return json.loads(run(['ip','netns','exec','pglan','python3','-c',flow_code],timeout=15))
def scenario(name,primary,fallback,allow,via=None,observed=None,continuous=False):
 epoch=str(uuid.uuid4());mode={'epoch':epoch,'primary':primary,'fallback':fallback}
 (Q/'mode.json').write_text(json.dumps(mode));baseline=status().get('last_probe_at',0);seen=set();states=[];end=time.monotonic()+100
 while time.monotonic()<end:
  s=status();at=s.get('last_probe_at',0);states.append({'at':at,'enforcement':s.get('enforcement'),'exit':s.get('exit_check')})
  if continuous:good_now=s.get('enforcement')=='allowing';assert good_now,(name,'unexpected interruption during fallback',states[-4:])
  if at>baseline:seen.add(at)
  events=[json.loads(l)for l in (Q/'requests.jsonl').read_text().splitlines()]if(Q/'requests.jsonl').exists()else[]
  own=[e for e in events if e['epoch']==epoch]
  if len(seen)>=3 and sum(e['host']=='api.ipify.org'for e in own)>=3:break
  time.sleep(.8)
 else:raise AssertionError((name,'two complete real probe rounds',states[-3:]))
 x=s.get('exit_check',{})
 good(s.get('enforcement')==('allowing'if allow else'blocked'),name+' actual rule state')
 good(x.get('via')==via,name+' reports the actual endpoint')
 if observed is not None:good(x.get('observed')==observed,name+' observed IPv4 is accurate')
 if primary=='timeout':good(sum(e['host']=='4.ident.me'for e in own)>=2,name+' invokes fallback after real curl timeout')
 else:good(not any(e['host']=='4.ident.me'for e in own),name+' never invokes fallback without primary timeout')
 paths=flows();(Q/(name+'-before-assert.json')).write_text(json.dumps({'status':s,'paths':paths,'requests':own},indent=2));good(all(v is allow for v in paths.values()),name+' IPv4/IPv6 TCP/UDP paths '+json.dumps(paths))
 if continuous:good(True,name+' no blocking reported during timeout fallback')
 (Q/(name+'.json')).write_text(json.dumps({'mode':mode,'states':states,'requests':own,'paths':paths},indent=2))
try:
 sid=rpc('session','login',{'username':'root','password':json.loads(Path('/tmp/pg-latest-login.json').read_text())['password'],'timeout':3600})['ubus_rpc_session']
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values'];original={k:v for k,v in original.items()if not k.startswith('.')}
 (Q/'original-config.json').write_text(json.dumps(original,indent=2))
 apply({'enabled':'0'});wait(lambda:status().get('enforcement')=='off','initial off')
 profile=json.loads(run(['ucode','/usr/lib/proxy-guard/inspect-client.uc',client]))
 assert profile.get('available') and profile.get('socks_port')
 fixture=Path('/tmp/pg_latest_fixture.py');text=fixture.read_text()
 begin=text.index('  def do_GET(self):');end=text.index('  def log_message',begin)
 handler="""  def do_GET(self):
   cfg=json.loads(Path('/tmp/pg-exit-fixture/mode.json').read_text());host=self.headers.get('Host','').split(':')[0]
   kind='primary'if host=='api.ipify.org'else'fallback'if host=='4.ident.me'else'other';mode=cfg.get(kind,'ok')
   with open('/tmp/pg-exit-fixture/requests.jsonl','a')as f:f.write(json.dumps({'epoch':cfg['epoch'],'host':host,'mode':mode,'uptime':time.monotonic()})+'\\n')
   if mode=='timeout':time.sleep(7);return
   if mode=='http_error':code,body=503,b'fixture unavailable'
   elif mode=='invalid':code,body=200,b'not-an-ip'
   elif mode=='wrong':code,body=200,b'9.9.9.10\\n'
   elif kind in ['primary','fallback']:code,body=200,b'9.9.9.9\\n'
   else:code,body=204,b''
   self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
"""
 handler=handler.replace('/tmp/pg-exit-fixture',str(Q))
 serverfile=Q/'servers.py';serverfile.write_text(text[:begin]+handler+text[end:])
 (Q/'mode.json').write_text(json.dumps({'epoch':'baseline','primary':'ok','fallback':'ok'}))
 ns=Path('/var/run/netns/pgwan').stat().st_ino
 found=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   args=p.joinpath('cmdline').read_bytes().split(bytes([0]))
   if any(str(x).encode()in args for x in [fixture,Path('/usr/share/pg-lab-boot/fixture.py')]) and b'servers'in args and p.joinpath('ns/net').stat().st_ino==ns:found.append((int(p.name),[x.decode()for x in args if x]))
  except OSError:pass
 assert len(found)==1,found
 old_server,old_command=found[0];stop_pid(old_server)
 out=(Q/'server.log').open('w')
 server=subprocess.Popen(['ip','netns','exec','pgwan','python3','-B',str(serverfile),'servers'],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
 wait(lambda:'SERVERS_READY'in(Q/'server.log').read_text(),'TLS fixture ready',25)
 # Prove a healthy native client path before enabling the controlled protection case.
 good(all(flows().values()),'real client forwarding baseline works before endpoint faults')
 apply({'enabled':'1','mode':'guard','proxy_client':client,'passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','client_auto_ports':'0','socks_port':str(profile['socks_port']),'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':[str(x)for x in profile['dns_ports']],'cf_event_check':'0','udp_check':'0','exit_check':'1','expected_exit4':'9.9.9.9','exit_url':'https://api.ipify.org','exit_fallback_url':'https://4.ident.me/','interval':'5','timeout':'2','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0','targets':['https://one.test/generate_204|204','https://two.test/generate_204|204'],'min_success':'1'})
 wait(lambda:status().get('enforcement')=='allowing','baseline successful probes')
 scenario('primary-healthy','ok','ok',True,observed='9.9.9.9')
 scenario('primary-timeout-fallback-ok','timeout','ok',True,via='4.ident.me',observed='9.9.9.9',continuous=True)
 scenario('primary-recovered','ok','ok',True,observed='9.9.9.9')
 scenario('primary-wrong-ip','wrong','ok',False,observed='9.9.9.10')
 scenario('primary-http503','http_error','ok',False)
 scenario('primary-invalid-body','invalid','ok',False)
 scenario('both-timeout','timeout','timeout',False,via='4.ident.me')
 scenario('fallback-wrong-ip','timeout','wrong',False,via='4.ident.me',observed='9.9.9.10')
 scenario('final-primary-recovery','ok','ok',True,observed='9.9.9.9')
 result={'ok':True,'checks':checks,'real_https_and_socks':True,'cloudflare_not_contacted':True}
except Exception:result={'ok':False,'checks':checks,'error':traceback.format_exc()};print(result['error'],flush=True)
finally:
 try:apply({'enabled':'0'})
 except Exception:pass
 if server is not None and server.poll()is None:stop_pid(server.pid)
 if old_server is not None:
  out=(Q/'restored-server.log').open('w')
  p=subprocess.Popen(['ip','netns','exec','pgwan',*old_command],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
  result['restored_fixture_pid']=p.pid
 if original is not None:
  try:
   if old_server is not None:wait(lambda:'SERVERS_READY'in(Q/'restored-server.log').read_text(),'restored TLS fixture ready',25)
   current=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   for k in current:
    if not k.startswith('.')and k not in original:rpc('uci','delete',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','option':k})
   apply(original)
   actual=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
   assert {k:v for k,v in actual.items()if not k.startswith('.')}==original
   result['original_configuration_restored']=True
  except Exception:result['ok']=False;result['cleanup_error']=traceback.format_exc()
 (Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
