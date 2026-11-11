from pathlib import Path
import os,sys,subprocess,json,time,traceback,socket,concurrent.futures,http.cookiejar,urllib.request,urllib.parse,tempfile,hashlib
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').exists()
checks=[];began=time.monotonic()
for path in ['/tmp/pg-native-dns-history.jsonl','/tmp/pg-native-flow-history.jsonl','/tmp/pg-first-blocked-status.json','/tmp/pg-completed-failure-status.json']:
 Path(path).unlink(missing_ok=True)
native_case=sys.argv[1]
assert native_case in ['hy','ss','naive','naive-quic']
expected={'tcp4':True,'udp4':not native_case.startswith('naive'),'tcp6':native_case!='ss','udp6':native_case!='ss'}
required={'tcp':True,'udp':not native_case.startswith('naive'),'dns':True}
# SSRust defaults to IPv4 listeners. Naive IPv6 follows direct routing here.
# These are explicit baseline limitations, not claims of IPv6 proxy support.
def run(*args,check=True,timeout=30,input=None):
 with tempfile.TemporaryFile(mode="w+t")as out,tempfile.TemporaryFile(mode="w+t")as err:
  result=subprocess.run(args,check=False,stdout=out,stderr=err,text=True,timeout=timeout,input=input)
  out.seek(0);err.seek(0);result.stdout=out.read();result.stderr=err.read()
  if check:result.check_returncode()
  return result
def ok(value,label):
 assert value,label
 checks.append(label);print('PASS '+label,flush=True)
def status():
 value=run('ubus','call','proxy_guard','status','{}',timeout=10)
 return json.loads(value.stdout)
def wait(pred,label,seconds):
 end=time.monotonic()+seconds;last={}
 while time.monotonic()<end:
  last=status()
  if pred(last):ok(True,label);return last
  time.sleep(.7)
 raise AssertionError(label+': '+json.dumps(last)[:1800])
draft={}
def setuci(key,value):
 assert key.startswith('proxy_guard.main.');draft[key.split('.',2)[2]]=str(value)
def listuci(key,values):
 assert key.startswith('proxy_guard.main.');draft[key.split('.',2)[2]]=list(values)
def rpc(obj,method,value):
 p=run('ubus','-t','15','call',obj,method,json.dumps(value),timeout=22)
 r=json.loads(p.stdout)if p.stdout.strip()else{}
 assert r.get('ok',True) is not False,(method,r)
 return r
def outage(enable):
 if enable:
  run('ip','netns','exec','pgwan','nft','-f','-',input='table inet pg_fixture_outage { chain input { type filter hook input priority -300; policy accept; tcp dport 443 drop;\n }\n}\n')
 else:run('ip','netns','exec','pgwan','nft','delete','table','inet','pg_fixture_outage')
child_code=r"""
import socket,json,sys,concurrent.futures,secrets,time,os
from pathlib import Path
def mark(event,name,**kw):
 with Path('/tmp/pg-native-flow-history.jsonl').open('a')as f:f.write(json.dumps(dict(event=event,name=name,pid=os.getpid(),wall=time.time(),uptime=time.monotonic(),**kw))+'\n')
spec=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
sockets={}
def check(row):
 name,family,kind,host=row
 try:
  if name not in sockets:
   s=socket.socket(family,kind);s.bind(('fd77:88::2' if family==socket.AF_INET6 else '10.77.0.2',0));s.settimeout(3);mark('connecting',name,local=s.getsockname(),remote=[host,23456]);s.connect((host,23456));mark('connected',name,local=s.getsockname());sockets[name]=s
  s=sockets[name];s.settimeout(.02)
  try:
   while s.recv(4096):pass
  except OSError:pass
  s.settimeout(3);token=secrets.token_hex(8).encode();mark('sending',name,token=token.decode());s.sendall(token);data=b''
  while token not in data and len(data)<4096:
   part=s.recv(4096)
   if not part:return name,False
   data+=part
  mark('received',name,ok=token in data,length=len(data));return name,token in data
 except OSError as e:mark('error',name,error=str(e),errno=e.errno);return name,False
for line in sys.stdin:
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:out=dict(pool.map(check,spec))
 print(json.dumps(out),flush=True)
"""
def dns_probe(destination):
 code=r"""
import socket,struct,json
host=DEST
import secrets
nonce=secrets.token_hex(6).encode()
labels=[nonce,b'proxy-guard-fixture',b'example',b'com']
q=struct.pack('!HHHHHH',0x2973,0x100,1,0,0,0)+b''.join(bytes([len(label)])+label for label in labels)+bytes([0])+struct.pack('!HH',1,1)
out={}
for tcp in [False,True]:
 family=socket.AF_INET6 if ':'in host else socket.AF_INET
 s=socket.socket(family,socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM);s.settimeout(5)
 if family==socket.AF_INET6:s.bind(('fd77:88::2',0))
 try:
  s.connect((host,53));s.sendall(struct.pack('!H',len(q))+q if tcp else q);r=s.recv(4096)
  if tcp:
   while len(r)<2:
    part=s.recv(4096)
    if not part:raise OSError('DNS EOF')
    r+=part
   need=struct.unpack('!H',r[:2])[0]
   while len(r)<need+2:
    part=s.recv(4096)
    if not part:break
    r+=part
   if len(r)<need+2:raise OSError('truncated DNS response')
   r=r[2:need+2]
  out['tcp'if tcp else'udp']=r[:2]==q[:2] and len(r)>12 and (r[3]&15)==0 and struct.unpack('!H',r[6:8])[0]>0 and socket.inet_aton('9.9.9.9')in r
 except OSError:out['tcp'if tcp else'udp']=False
 finally:s.close()
print(json.dumps(out))
""".replace('DEST',repr(destination))
 return json.loads(run('ip','netns','exec','pglan','python3','-c',code,timeout=20).stdout)
def persistent(label,allow):
 flow.stdin.write('check\n');flow.stdin.flush();reply=json.loads(flow.stdout.readline())
 ok(all(v is (expected[k] if allow else False) for k,v in reply.items()),label+' '+json.dumps(reply))
def fresh(allow,label):
 with subprocess.Popen(['ip','netns','exec','pglan','python3','-u','-c',child_code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)as p:
  p.stdin.write('check\n');p.stdin.flush();reply=json.loads(p.stdout.readline())
  p.stdin.close();p.wait(timeout=8)
 ok(all(v is (expected[k] if allow else False) for k,v in reply.items()),label+' '+json.dumps(reply))
try:
 case,client=sys.argv[1:]
 Path('/tmp/pg-integration-result.json').unlink(missing_ok=True)
 expected_files=json.loads(Path('/tmp/pg-final-runtime-manifest.json').read_text())['files']
 mismatches=[path for path,digest in expected_files.items()if not Path(path).is_file()or hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest]
 ok(not mismatches,'actual final installed runtime matches the candidate manifest '+str(mismatches))
 profile=json.loads(run('ucode','/usr/lib/proxy-guard/inspect-client.uc',client).stdout)
 ok(profile.get('available') is True,'actual client profile resolves')
 ok(profile['required']==required,'native capabilities match the actual core, including absent UDP support')
 services=json.loads(run('ucode','/usr/lib/proxy-guard/inspect-services.uc',profile.get('dns_mode')or'dnsmasq',json.dumps(profile)).stdout)
 ok(all(services.get(name)is True for name,needed in profile['required'].items()if needed),'configured client listeners and TUN ownership are running')
 if profile.get('socks_auth_file'):
  for k in ['socks_auth_file','socks_curl_file']:ok(Path(profile[k]).stat().st_mode&0o777==0o600,'private '+k+' permissions')
 dns_start=time.monotonic();streak=0;dns_history=[]
 while time.monotonic()-dns_start<70:
  baseline={destination:dns_probe(destination)for destination in ['10.77.0.1','fd77:88::1']};dns_history.append(baseline)
  streak=streak+1 if all(all(row.values())for row in baseline.values())else 0
  if streak>=3:break
  time.sleep(1)
 if streak<3:print('DNS_BASELINE_SAMPLES '+json.dumps(dns_history[-3:]),flush=True)
 ok(streak>=3,'DNS baseline is stable on TCP/UDP and IPv4/IPv6 before enabling protection')
 print('INFO baseline DNS startup seconds='+str(round(time.monotonic()-dns_start,2))+' failed samples='+str(sum(not all(all(row.values())for row in item.values())for item in dns_history)),flush=True)
 flow=subprocess.Popen(['ip','netns','exec','pglan','python3','-u','-c',child_code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 persistent('pre-existing paths match the declared native-core baseline',True)
 for key,val in {'enabled':'1','mode':'guard','proxy_client':client,'client_auto_ports':'1','passwall_watch':'1','passwall_log_watch':'1',
  'boot_guard':'1','cf_event_check':'1','exit_url':'https://api.ipify.org','exit_fallback_url':'https://4.ident.me','exit_check':'1','expected_exit4':'9.9.9.9','expected_exit6':'','interval':'10','timeout':'5','fail_threshold':'1','recover_threshold':'1',
  'startup_grace':'0','schedule_enabled':'0','udp_check':'0' if native_case.startswith('naive') else '1','udp_server':'9.9.9.9','udp_port':'53','udp_query':'one.test','udp_timeout':'2',
  'fast_wait_enabled':'1','fast_wait_seconds':'15','fast_stable_enabled':'1','fast_stable_seconds':'60'}.items():setuci('proxy_guard.main.'+key,val)
 for key,val in {'interfaces':['br-lan'],'sources4':['10.77.0.2/32'],'sources6':['fd77:88::2/128'],'local4':['10.77.0.0/24'],'local6':['fd77:88::/64'],
  'dns_ports':['53'],'targets':['https://www.gstatic.com/generate_204|204','https://connectivity-check.ubuntu.com|204']}.items():listuci('proxy_guard.main.'+key,val)
 outage(True)
 auth=json.loads(Path('/tmp/pg-latest-login.json').read_text())
 sid=rpc('session','login',{'username':'root','password':auth['password']})['ubus_rpc_session']
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':draft})
 applied=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 ok(applied.get('confirmation_required')is True,'actual authenticated RPC applies session draft with confirmation')
 tx=applied['transaction'];limit=time.monotonic()+100
 while time.monotonic()<limit:
  current=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction',{})
  if current.get('phase')=='confirming':break
  time.sleep(.5)
 else:raise AssertionError('native rule self-check never reached confirmation')
 rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
 ok(True,'actual runtime rules are explicitly confirmed while the proxy is unavailable')
 s=wait(lambda s:s.get('enforcement')=='blocked','real rules report blocked during boot protection/outage',40)
 ok(set(profile.get('dns_ports',[]))<=set((s.get('client')or{}).get('dns_ports',[])),'automatic binding includes the actual redirected DNS listeners')
 persistent('existing TCP/UDP IPv4/IPv6 flows are blocked',False)
 fresh(False,'new TCP/UDP IPv4/IPv6 flows are blocked')
 # LAN DNS and management must remain accessible while public HTTPS is unavailable.
 dns=dns_probe('10.77.0.1');ok(all(dns.values()),'local DNS TCP and UDP remain available '+json.dumps(dns))
 dns6=dns_probe('fd77:88::1');ok(all(dns6.values()),'local IPv6 DNS TCP and UDP remain available '+json.dumps(dns6))
 mg=run('ip','netns','exec','pglan','curl','-q','-sS','--noproxy','*','--max-time','3','-o','/dev/null','-w','%{http_code}','http://10.77.0.1/',check=False)
 ok(mg.returncode==0 and mg.stdout in ['200','301','302','303'],'router management remains reachable while blocked')
 rootcode="import socket;s=socket.create_connection(('9.9.9.9',23456),2);s.sendall(b'router');assert s.recv(6)==b'router';print('ok')"
 ok(run('python3','-c',rootcode).stdout.strip()=='ok','router own external flow remains available while clients are blocked')
 outage(False)
 s=wait(lambda s:s.get('enforcement')=='allowing' and (s.get('fast_watch')or{}).get('phase')=='sensitive','successful real checks restore access into sensitive monitoring',65)
 fresh(True,'supported paths match the declared baseline after release')
 flow.stdin.write('check\n');flow.stdin.flush();old_reply=json.loads(flow.stdout.readline())
 ok(all(old_reply[k] is True for k in ['udp4','udp6'] if expected[k]),'pre-existing supported UDP paths recover after release; unsupported paths are not claimed')
 print('INFO existing TCP sockets after blocking: '+json.dumps({k:v for k,v in old_reply.items()if k.startswith('tcp')}),flush=True)
 before_failure_probe=s.get('last_probe_at',0)
 outage(True);trip=time.monotonic();fault_uptime=int(float(Path('/proc/uptime').read_text().split()[0]))
 s=wait(lambda s:s.get('enforcement')=='blocked','a real failure during the 60-second sensitive period blocks access',max(18,(s.get('probe_budget')or 0)+8))
 Path('/tmp/pg-first-blocked-status.json').write_text(json.dumps(s,indent=2))
 # The kernel/watchdog can revoke a permit before the probing worker publishes.
 # Primary failure also includes exit-IP/UDP errors: an in-flight round may
 # have passed both HTTPS targets before the fault. Wait for an actual HTTPS
 # failure in a round that starts after the injected outage.
 s=wait(lambda s:s.get('last_probe_at',0)>before_failure_probe and s.get('probe_started',0)>=fault_uptime and any(p.get('ok') is False for p in s.get('probes',[])),'a new HTTPS failure starting after the injected outage is published',max(90,(s.get('probe_budget')or 0)*2+30))
 Path('/tmp/pg-completed-failure-status.json').write_text(json.dumps(s,indent=2))
 ok(s.get('exit_check',{}).get('attempted') is False and 'ok' not in s['exit_check'] and s['exit_check'].get('curl_code') is None and '出口验证失败' not in s.get('reason',''),'strict HTTPS failure blocks while reporting the skipped exit check honestly')
 ok((s.get('fast_watch')or{}).get('phase')in ['delay','log_wait','boot_wait','sensitive'],'sensitive failure stays in a blocking recovery phase')
 outage(False)
 s=wait(lambda s:s.get('enforcement')=='allowing' and (s.get('fast_watch')or{}).get('phase')=='sensitive','after sensitive failure recovery repeats the delay and resumes observation',50)
 fresh(True,'supported paths match baseline after a sensitive-period fault')
 s=wait(lambda s:s.get('enforcement')=='allowing' and (s.get('fast_watch')or{}).get('phase')=='normal' and (s.get('fast_watch')or{}).get('stable_elapsed',0)>=(s.get('fast_watch')or{}).get('stable_required',60),'60 uninterrupted seconds after the latest real fault returns to normal mode',180)
 public=json.dumps(s)+run('ubus','call','proxy_guard','logs','{}').stdout
 if profile.get('socks_auth_file'):
  auth=json.loads(Path(profile['socks_auth_file']).read_text())
  ok(auth['password']not in public and '"password":'not in public and '"username":'not in public,'status and event RPC do not expose SOCKS credentials')
 run('/etc/init.d/'+client,'stop',timeout=240)
 s=wait(lambda s:s.get('enforcement')=='blocked','native client stop revokes access',35)
 fresh(False,'native client stop blocks new TCP/UDP IPv4/IPv6 flows')
 run('/etc/init.d/'+client,'start',timeout=240)
 s=wait(lambda s:s.get('enforcement')=='allowing' and (s.get('fast_watch')or{}).get('phase')=='sensitive','native client restart restores access into sensitive monitoring',120)
 fresh(True,'native client restart restores the declared baseline paths')
 s=wait(lambda s:s.get('enforcement')=='allowing' and (s.get('fast_watch')or{}).get('phase')=='normal','native client restart completes stable observation',180)
 ok((s.get('fast_watch')or{}).get('stable_elapsed',0)>=60,'native restart completes at least sixty uninterrupted seconds after the last real fault')
 if client in ('openclash','nikki'):
  auth=json.loads(Path('/tmp/pg-latest-login.json').read_text())
  sid=rpc('session','login',{'username':'root','password':auth['password']})['ubus_rpc_session']
  values={'passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','client_auto_ports':'0','socks_port':str(profile['socks_port']),
   'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':list(dict.fromkeys(['53']+[str(x)for x in profile['dns_ports']]))}
  rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
  change=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True});tx=change['transaction'];end=time.monotonic()+110
  while time.monotonic()<end:
   if rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction',{}).get('phase')=='confirming':break
   time.sleep(.5)
  else:raise AssertionError('monitor-off self-check did not enter confirmation')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']})
  wait(lambda s:s.get('phase')=='healthy' and s.get('enforcement')=='allowing','authenticated SOCKS checks survive disabled service monitor',90)
  fresh(True,'authenticated SOCKS and IPv4/IPv6 TCP/UDP remain usable with service monitoring off')
 Path('/tmp/pg-integration-result.json').write_text(json.dumps({'ok':True,'case':case,'checks':checks,'baseline_paths':expected,'native_case':native_case,'seconds':time.monotonic()-began}))
 print('PASS COMPLETE_REAL_CLIENT_INTEGRATION '+case,flush=True)
except Exception:
 Path('/tmp/pg-integration-result.json').write_text(json.dumps({'ok':False,'case':case,'checks':checks,'error':traceback.format_exc(),'seconds':time.monotonic()-began}))
 raise
finally:
 try:
  runtime={name:Path('/var/run/proxy-guard/'+name).read_text()for name in ['status.json','fast.json','supervision.json','supervision-events.jsonl','events.jsonl','fast-events.jsonl','worker-health.json','setup-result.json','control-generation']if Path('/var/run/proxy-guard/'+name).exists()}
  if 'profile' in globals() and profile.get('log_path'):
   log=Path(profile['log_path'])
   if log.is_file():runtime['client_log']=log.read_text(errors='replace')[-65536:]
  p=subprocess.run(['logread'],capture_output=True,text=True,timeout=20);runtime['system_log']=p.stdout[-65536:]
  p=subprocess.run(['ps','w'],capture_output=True,text=True,timeout=20);runtime['processes']=p.stdout
  Path('/tmp/pg-runtime71.json').write_text(json.dumps(runtime))
 except Exception:pass
 if 'flow'in globals():
  flow.stdin.close();flow.terminate()
