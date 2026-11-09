"""Real HTTP + nft + TCP/UDP/IPv4/IPv6. ONLY in a private namespace in the offline VM."""
from pathlib import Path
import atexit,importlib.util,json,os,subprocess,sys,tempfile,threading,socket,hashlib,hmac,time,uuid,urllib.request,urllib.error
assert sys.platform=='linux' and os.geteuid()==0
assert Path('/.proxy-guard-test-root').is_file()
assert os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net')
ROOT=Path(os.environ.get('PG_SOURCE',Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(ROOT/'companion/vps'))
spec=importlib.util.spec_from_file_location('access_agent',ROOT/'companion/vps/agent.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def cmd(*args,check=True):
 return subprocess.run(args,check=check,text=True,capture_output=True,timeout=12)
def check(value,label):
 assert value,label
 print('PASS '+label,flush=True)
cmd('ip','link','set','lo','up')
cmd('mount','--make-rprivate','/')
names=['pg_access_'+str(os.getpid())+'_a','pg_access_'+str(os.getpid())+'_b']
def cleanup_names():
 for name in names:cmd('ip','netns','delete',name,check=False)
atexit.register(cleanup_names)
for index,name in enumerate(names,1):
 cmd('ip','netns','add',name)
 host,peer='va'+str(index),'vp'+str(index)
 cmd('ip','link','add',host,'type','veth','peer','name',peer)
 cmd('ip','link','set',peer,'netns',name)
 cmd('ip','addr','add','10.77.'+str(index)+'.1/24','dev',host)
 cmd('ip','-6','addr','add','fd77:'+str(index)+'::1/64','dev',host,'nodad')
 cmd('ip','link','set',host,'up')
 v4=['8.8.8.8','9.9.9.9'][index-1];v6=['2606:4700:4700::1111','2001:4860:4860::8888'][index-1]
 for args in [('link','set','lo','up'),('link','set',peer,'up'),
  ('addr','add',v4+'/32','dev',peer),
  ('-6','addr','add',v6+'/128','dev',peer,'nodad'),
  ('route','add','10.77.'+str(index)+'.1/32','dev',peer),
  ('-6','route','add','fd77:'+str(index)+'::1/128','dev',peer)]:
  cmd('ip','-n',name,*args)
 cmd('ip','route','add',v4+'/32','dev',host)
 cmd('ip','-6','route','add',v6+'/128','dev',host)
stop=threading.Event();sockets=[]
def serve(sock,udp):
 while not stop.is_set():
  try:
   if udp:
    data,remote=sock.recvfrom(1000);sock.sendto(data,remote)
   else:
    client,_=sock.accept()
    def echo(c):
     with c:
      c.settimeout(10)
      try:
       while True:
        data=c.recv(1000)
        if not data:break
        c.sendall(data)
      except OSError:pass
    threading.Thread(target=echo,args=(client,),daemon=True).start()
  except socket.timeout:pass
  except OSError:break
for version in [4,6]:
 for port,udp in [(22,False),(24443,False),(24443,True),(23456,False),(25000,False),(25000,True),(28080,False)]:
  s=socket.socket(socket.AF_INET if version==4 else socket.AF_INET6,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  if version==6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind(('0.0.0.0' if version==4 else '::',port));s.settimeout(.2)
  if not udp:s.listen()
  sockets.append(s);threading.Thread(target=serve,args=(s,udp),daemon=True).start()
probe="""import socket,sys
v,udp,port,dst=sys.argv[1:];s=socket.socket(socket.AF_INET if v=='4' else socket.AF_INET6,socket.SOCK_DGRAM if udp=='1' else socket.SOCK_STREAM);s.settimeout(2)
try:
 s.connect((dst,int(port)));s.sendall(b'probe');r=s.recv(99);print('ok' if r==b'probe' else 'bad')
except OSError:print('blocked')
"""
def test(name,v,port,udp=False):
 i=1 if name==names[0] else 2
 dst='10.77.'+str(i)+'.1' if v==4 else 'fd77:'+str(i)+'::1'
 return cmd('ip','netns','exec',name,'python3','-c',probe,str(v),str(int(udp)),str(port),dst).stdout.strip()=='ok'
tmp=tempfile.TemporaryDirectory();driver=m.Nft()
engine=m.Engine('a'*40,'home',Path(tmp.name)/'state.json',driver)
server=m.Server(('127.0.0.1',8788),engine);threading.Thread(target=server.serve_forever,daemon=True).start()
def sync(ip='8.8.8.8',revision=1,rules=None,enabled=True,families=None,legacy=False):
 body=json.dumps(dict(device_id='home',observed_ip=ip,policy_enabled=enabled,mode="whitelist",
  rules=rules if rules is not None else policy,revision=revision,ttl=120,address_families=families or [4,6],
  issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()),default_deny=legacy,auto_discover=legacy),separators=(',',':')).encode()
 sig=hmac.new(b'a'*40,body,hashlib.sha256).hexdigest()
 request=urllib.request.Request('http://127.0.0.1:8788/v1/sync',body,headers={'X-Pg-Signature':sig,'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=12) as response:return json.load(response)
policy=[
 dict(id='ssh',name='SSH',enabled=True,protocol='tcp',ports=['22'],source_mode='any',sources=[]),
 dict(id='proxy',name='Proxy',enabled=True,protocol='both',ports=['24443'],source_mode='dynamic',sources=[]),
 dict(id='replycheck',name='Reply check',enabled=True,protocol='both',ports=['26666'],source_mode='dynamic',sources=[]),
 dict(id='static',name='Static',enabled=True,protocol='tcp',ports=['23456'],source_mode='static',
  sources=['8.8.8.8/32','2606:4700:4700::1111/128'])]
def use(mode='standard',limits=None,ssh=None,runtime=None):
 p=m.normalize_policy(True,[dict(id='proxy',name='Proxy',enabled=True,protocol='both',ports=['24443'],source_mode='dynamic',sources=[],limits=limits or {})],mode=mode,ssh=ssh)
 engine.state['policy']=p;engine.runtime=runtime or {};engine.leases={4:('8.8.8.8',time.monotonic()+300),6:('2606:4700:4700::1111',time.monotonic()+300)}
 driver.apply(engine.effective_policy(),engine.leases)
 return p

def burst(name,port,count=10,sport=0,version=4):
 i=1 if name==names[0]else 2
 code=r"""import socket,sys,select,time,secrets
port,count,sport,dst,version=map(str,sys.argv[1:]);count=int(count);sport=int(sport);sockets=[];received=set();prefix=secrets.token_bytes(12)
try:
 for i in range(count):
  if not sport or not sockets:
   sock=socket.socket(socket.AF_INET6 if version=='6'else socket.AF_INET,socket.SOCK_DGRAM);sock.setblocking(False)
   if sport:sock.bind(('::' if version=='6'else'0.0.0.0',sport))
   sockets.append(sock)
  sock=sockets[0]if sport else sockets[-1]
  sock.sendto(prefix+bytes([i])+b'x'*(512-len(prefix)-1),(dst,int(port)))
 # Receive grace does not space the burst or replenish its limiter between sends.
 end=time.monotonic()+2
 while len(received)<count and time.monotonic()<end:
  readable,_,_=select.select(sockets,[],[],max(0,end-time.monotonic()))
  for sock in readable:
   try:
    data=sock.recv(1024)
    if len(data)==512 and data.startswith(prefix):received.add(data[len(prefix)])
   except BlockingIOError:pass
 print(len(received))
finally:
 for sock in sockets:sock.close()
"""
 return int(cmd('ip','netns','exec',name,'python3','-c',code,str(port),str(count),str(sport),'fd77:'+str(i)+'::1'if version==6 else'10.77.'+str(i)+'.1',str(version)).stdout.strip())
try:
 # Different destinations and protocols must retain independent modes and limits.
 mixed_rules=[
  dict(id='white',name='Custom whitelist',enabled=True,protocol='tcp',ports=['24443'],source_mode='static',sources=['9.9.9.9/32','2001:4860:4860::8888/128'],mode='whitelist'),
  dict(id='observe',name='Observe UDP',enabled=True,protocol='udp',ports=['24443'],source_mode='dynamic',sources=[],mode='observe',limits={'rate':1,'burst':1,'connections':1}),
  dict(id='limit',name='Custom limits',enabled=True,protocol='both',ports=['25000'],source_mode='dynamic',sources=[],mode='standard',limits={'rate':1,'burst':1,'connections_enabled':False,'cooldown':2,'window':5,'bandwidth_enabled':True,'bandwidth':1024}),
  dict(id='inherited',name='Inherited',enabled=True,protocol='tcp',ports=['23456'],source_mode='dynamic',sources=[])]
 mixed=m.normalize_policy(True,mixed_rules,mode='observe')
 engine.state['policy']=mixed;engine.runtime={};engine.leases={4:('8.8.8.8',time.monotonic()+300),6:('2606:4700:4700::1111',time.monotonic()+300)}
 driver.apply(engine.effective_policy(),engine.leases)
 for name in names:
  for version in (4,6):
   check(test(name,version,24443)==(name==names[1]),'per-port custom static whitelist IPv'+str(version)+' '+name)
   check(test(name,version,24443,True),'same-number UDP observe stays accessible IPv'+str(version)+' '+name)
   check(test(name,version,23456),'inherited observe stays accessible IPv'+str(version)+' '+name)
 check(burst(names[1],24443)==10,'observe rule does not enforce its configured low rate')
 check(burst(names[1],25000)<6,'custom standard rule limits only its destination')
 check(burst(names[0],25000)==10,'custom standard rule preserves authorized household traffic')
 from telemetry import Telemetry
 from reality_check import RealityCheck
 from monitor import EventStore
 telemetry=Telemetry(engine,RealityCheck({'config_path':'','access_log':'','telemetry_file':''}),EventStore())
 telemetry.sample_counters(driver.snapshot())
 check(any(x['source_ip']=='9.9.9.9'and x['port']==24443 and x['protocol']=='udp'and x['bytes']>0 for x in telemetry.observations),'actual nft concatenated source and destination counters reach Agent telemetry')
 mixed['mode']='whitelist';driver.apply(engine.effective_policy(),engine.leases)
 for version in (4,6):
  check(not test(names[1],version,23456),'inherited rule follows changed global default IPv'+str(version))
  check(test(names[1],version,24443,True),'explicit observe rule survives changed global default IPv'+str(version))
 for mode in('standard','whitelist','observe'):
  use(mode)
  for name in names:
   for version in(4,6):
    for udp in(False,True):check(test(name,version,24443,udp)==(mode!='whitelist'or name==names[0]),mode+' selected port IPv'+str(version)+(' UDP'if udp else' TCP')+' '+name)
    check(test(name,version,25000),mode+' unselected listener keeps native access IPv'+str(version))
 use('observe',{'rate':1,'burst':1,'connections':1})
 check(burst(names[1],24443)==10,'observe mode records repeated UDP without blocking')
 seen=[x['set']for x in driver.snapshot()['nftables']if 'set'in x and x['set']['name']=='seen4_0_udp']
 check(bool(seen and seen[0].get('elem')),'actual per-source observation set is populated')
 print('OBSERVED_ELEMENT',json.dumps(seen[0].get('elem',[])[:1]),flush=True)
 p=use('standard',{'rate':1,'burst':1,'connections_enabled':False,'cooldown':2,'window':5})
 p['rules'][0]['ports'].append('25000');engine.state['policy']=p;driver.apply(engine.effective_policy(),engine.leases)
 received=burst(names[1],24443,12)
 check(received<6,'kernel new-flow rate limit rejects excess requests '+str(received))
 check(burst(names[0],24443)==10,'household authorization bypasses resource limits')
 check(test(names[1],4,25000,True),'a limited port does not limit a second port in the same service rule')
 time.sleep(2.2);check(test(names[1],4,24443,True),'kernel cooldown expires without policy replacement')
 use('standard',{'rate_enabled':False,'connections':1,'cooldown':1})
 hold=r"""import socket,sys
s=socket.socket();s.settimeout(1);s.connect(('10.77.2.1',24443));s.sendall(b'a');assert s.recv(1)==b'a';print('ready',flush=True);sys.stdin.readline();s.close()
"""
 held=subprocess.Popen(['ip','netns','exec',names[1],'python3','-u','-c',hold],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 try:
  check(held.stdout.readline().strip()=='ready','first tracked connection establishes')
  check(not test(names[1],4,24443),'concurrency cap rejects a second tracked connection')
  check(test(names[1],4,25000),'concurrency cap leaves other services alone')
 finally:held.communicate('stop\n',timeout=3)
 runtime={'fallback_restricted':{'proxy':[dict(protocol='udp',source='9.9.9.9',sport=55001,port=24443,until=time.monotonic()+20)]}}
 p=use('standard',{'rate_enabled':False,'connections_enabled':False,'bandwidth_enabled':True,'bandwidth':1024},runtime=runtime)
 received=burst(names[1],24443,10,55001)
 check(received<5,'only the verified fallback flow is bandwidth limited '+str(received))
 check(burst(names[1],24443,10,55002)==10,'another flow from the same IP remains usable')
 check(burst(names[0],24443)==10,'household traffic remains usable during fallback limiting')
 # Regression: a standard per-port rule must keep bandwidth runtime tuples
 # under either of the other global defaults, not only global standard.
 for global_mode in ('observe','whitelist'):
  runtime['fallback_restricted']['proxy']=[dict(protocol='udp',source=ip,sport=55001,port=24443,until=time.monotonic()+90)for ip in ['9.9.9.9','2001:4860:4860::8888']]
  p['mode']=global_mode;p['rules'][0]['mode']='standard'
  engine.state['policy']=p;engine.runtime=runtime;driver.apply(engine.effective_policy(),engine.leases)
  for family in (4,6):
   check(burst(names[1],24443,10,55001,version=family)<5,'per-rule standard fallback bandwidth under global '+global_mode+' IPv'+str(family))
   check(burst(names[1],24443,10,55002,version=family)==10,'independent flow remains usable under global '+global_mode+' IPv'+str(family))
 p=use('standard',{'rate':1,'burst':1,'connections_enabled':False,'cooldown':2,'window':5})
 p['rules'][0]['source_mode']='all';engine.state['policy']=p;driver.apply(engine.effective_policy(),engine.leases)
 check(burst(names[0],24443,12)<6,'all-source standard limits also apply to authenticated household IP')
 check(burst(names[1],24443,12)<6,'all-source standard limits unknown sources')
 p['rules'][0]['source_mode']='any';engine.state['policy']=p;driver.apply(engine.effective_policy(),engine.leases)
 check(burst(names[0],24443)==10 and burst(names[1],24443)==10,'legacy any remains explicit unprotected bypass')

 # This tests the kernel timer primitive with explicit runtime input; daemon
 # ownership and management preflight are separately checked in the unit suite.
 now=time.monotonic();runtime={'ssh_armed':True,'last_home':['8.8.8.8'],'ssh_hold_until':now+8,'ssh_public_until':now+24}
 use('whitelist',ssh={'managed':True,'confirmed':True,'port':22,'managers':['8.8.8.8/32'],'open_seconds':30},runtime=runtime)
 check(not test(names[1],4,22),'managed SSH initially rejects an unauthorized new source')
 check(test(names[0],4,22),'managed SSH preserves authorized management access')
 print('SSH_DEADLINES',now+8,now+24,'armed_at',time.monotonic(),flush=True)
 time.sleep(max(0,now+10.2-time.monotonic()));check(test(names[1],4,22),'kernel lease opens emergency SSH without userspace renewal')
 check(test(names[1],4,25000),'emergency SSH does not affect other ports')
 time.sleep(max(0,now+25.2-time.monotonic()));check(not test(names[1],4,22),'kernel lease closes the public emergency window')
 check(test(names[0],4,22),'management addresses still work after the public window')
 server.shutdown();server.server_close()
 # Measure the original short test hold before using a robust kernel timer.
 diagnostic=time.monotonic()
 use('whitelist',ssh={'managed':True,'confirmed':True,'port':22,'open_seconds':0},runtime={'ssh_armed':True,'last_home':['8.8.8.8'],'ssh_hold_until':diagnostic+3,'ssh_public_until':0})
 print('ORIGINAL_3S_HOLD_APPLICATION_SECONDS',time.monotonic()-diagnostic,flush=True)
 now=time.monotonic()
 runtime={'ssh_armed':True,'last_home':['8.8.8.8'],'ssh_hold_until':now+15,'ssh_public_until':0}
 use('whitelist',ssh={'managed':True,'confirmed':True,'port':22,'open_seconds':0},runtime=runtime)
 check(not test(names[1],4,22),'unlimited rescue remains closed during heartbeat hold')
 elements=[x['set'] for x in driver.snapshot()['nftables'] if 'set' in x and x['set']['name']=='ssh_public'][0]['elem']
 check(elements==[22] or elements==[{'elem':{'val':22}}], 'unlimited rescue public kernel element has no expiry')
 print('UNLIMITED_HOLD_APPLIED_AFTER',time.monotonic()-now,flush=True)
 time.sleep(max(0,now+16-time.monotonic()))
 for version in (4,6):check(test(names[1],version,22),'unlimited rescue opens after kernel hold IPv'+str(version))
 driver.commit('delete element inet pg_vps_access ssh_public { 22 }\nadd element inet pg_vps_access ssh_public { 22 timeout 30s }\n')
 corrupt=driver.snapshot()
 live=[x['set'] for x in corrupt['nftables'] if 'set' in x and x['set']['name']=='ssh_public'][0]['elem']
 check(any(isinstance(x,dict) and x.get('elem',x).get('expires',0)>0 for x in live),'fault injection is still live when permanence is checked')
 check(not driver.runtime_matches(engine.effective_policy(),engine.leases,driver.snapshot()),'runtime verifier rejects an unexpected timeout on a permanent rescue element')
 driver.apply(engine.effective_policy(),engine.leases)
 check(driver.runtime_matches(engine.effective_policy(),engine.leases,driver.snapshot()),'normal policy application restores an unbounded rescue element')
 time.sleep(4)
 check(test(names[1],4,22),'unlimited rescue remains reachable after permanent-element repair')
 runtime['ssh_hold_until']=time.monotonic()+60
 engine.runtime=runtime;driver.apply(engine.effective_policy(),engine.leases)
 check(not test(names[1],4,22),'recovered household authorization can restore the closed hold gate')
 from control import Server as ControlServer
 config={'direct_token':'d'*40,'path_token':'p'*40,'services':[{'name':'Xray','process_names':['python3.12','python3'],'tcp_ports':[24443],'udp_ports':[24443],'required':True}],'maintenance':{'enabled':True,'allow_restart_xray':True,'allow_reboot':False,'service':'Xray'}}
 server=ControlServer(('127.0.0.1',8788),engine,config,'pro');threading.Thread(target=server.serve_forever,daemon=True).start()
 calls=[];server.maintenance.executor=lambda action,c:calls.append(action)
 def envelope(**kw):return dict(device_id='home',revision=engine.state['revision'],issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()),**kw)
 def api(path,body,token=None,signed=False):
  raw=json.dumps(body,separators=(',',':')).encode();headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  if signed:headers['X-Pg-Signature']=hmac.new(b'a'*40,raw,hashlib.sha256).hexdigest()
  try:
   with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8788'+path,raw,headers=headers),timeout=12)as reply:return reply.status,json.load(reply)
  except urllib.error.HTTPError as error:return error.code,json.load(error)
 before=server.safety.last_control;code,result=api('/v1/direct/path-heartbeat',envelope(channel='proxy'),token='p'*40)
 check(code==200 and result['channel']=='proxy','real HTTP accepts the independent authenticated proxy heartbeat')
 check(server.safety.last_control==before,'proxy heartbeat does not refresh the control heartbeat')
 check(api('/v1/direct/path-heartbeat',envelope(channel='proxy'),token='d'*40)[0]==401,'control secret cannot impersonate the separate path secret')
 body=envelope(include_analysis=False)
 check(api('/v1/status',body,signed=True)[0]==200 and api('/v1/status',body,signed=True)[0]==403,'real signed status rejects nonce replay')
 body=envelope(action='restart_xray',operation_id=str(uuid.uuid4()),expires_at=int(time.time()*1000)+30000)
 check(api('/v1/direct/command',body,token='d'*40)[0]==200,'authenticated API accepts an explicitly allowed fixed action')
 body['request_id']=str(uuid.uuid4());check(api('/v1/direct/command',body,token='d'*40)[0]==200,'duplicate operation ID returns the existing record')
 time.sleep(1.3);check(calls==['restart_xray'],'duplicate requests dispatch only one fixed action through the test executor')
 check(api('/v1/direct/command',envelope(action='reboot_vps',operation_id=str(uuid.uuid4()),expires_at=int(time.time()*1000)+30000),token='d'*40)[0]==403,'Agent permissions independently deny reboot')
 with urllib.request.urlopen('http://127.0.0.1:8788/health',timeout=5)as reply:check(set(json.load(reply))=={'ok'},'public health endpoint exposes no private status')
 # Pause only the monitoring thread to make fault injection deterministic;
 # resume the same production reconciliation loop, without a manual repair.
 target=server.reconcile_thread._target;server.reconcile_stop.set();server.reconcile_thread.join(10)
 driver.commit('flush set inet pg_vps_access dynamic4\nadd element inet pg_vps_access dynamic4 { 9.9.9.9 timeout 120s }\n')
 check(not driver.runtime_matches(engine.effective_policy(),engine.leases,driver.snapshot()),'runtime verification detects a forged dynamic authorization despite unchanged rule definitions')
 server.reconcile_stop.clear();server.reconcile_thread=threading.Thread(target=target,daemon=True);server.reconcile_thread.start()
 deadline=time.monotonic()+12
 while time.monotonic()<deadline:
  if driver.runtime_matches(engine.effective_policy(),engine.leases,driver.snapshot()):break
  time.sleep(.2)
 check(test(names[0],4,24443)and not test(names[1],4,24443),'normal reconciliation restores the authenticated source and removes the forged source')
 print('PASS Standard and Pro basic mode/lease/API suite',flush=True)
finally:
 server.shutdown();server.server_close();stop.set();driver.cleanup()
 for s in sockets:s.close()
 for name in names:cmd('ip','netns','delete',name,check=False)
 tmp.cleanup()
