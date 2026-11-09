"""Real HTTP + nft + TCP/UDP/IPv4/IPv6. ONLY in a private namespace in the offline VM."""
from pathlib import Path
import atexit,importlib.util,json,os,subprocess,sys,tempfile,threading,socket,hashlib,hmac,time,uuid,urllib.request,urllib.error
assert sys.platform=='linux' and os.geteuid()==0
assert Path('/.proxy-guard-test-root').is_file()
assert os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net')
ROOT=Path(__file__).resolve().parents[2]
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
 for port,udp in [(22,False),(24443,False),(24443,True),(23456,False),(25000,False),(28080,False)]:
  s=socket.socket(socket.AF_INET if version==4 else socket.AF_INET6,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
  s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  if version==6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind(('0.0.0.0' if version==4 else '::',port));s.settimeout(.2)
  if not udp:s.listen()
  sockets.append(s);threading.Thread(target=serve,args=(s,udp),daemon=True).start()
probe="""import socket,sys
v,udp,port,dst=sys.argv[1:];s=socket.socket(socket.AF_INET if v=='4' else socket.AF_INET6,socket.SOCK_DGRAM if udp=='1' else socket.SOCK_STREAM);s.settimeout(.45)
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
try:
 for name in names:
  for v in [4,6]:check(test(name,v,22),'unmanaged SSH22 retains native access '+name+' IPv'+str(v))
 driver.commit('table inet access_unrelated { chain input { type filter hook input priority 0; policy accept; tcp dport 28080 drop; }; }\n')
 sync();sync('2606:4700:4700::1111')
 for name in names:
  for v in [4,6]:
   for udp in [False,True]:
    check(test(name,v,24443,udp)==(name==names[0]),'dynamic source '+name+' IPv'+str(v)+(' UDP' if udp else ' TCP'))
   check(test(name,v,23456)==(name==names[0]),'static source '+name+' IPv'+str(v))
   check(test(name,v,25000),'unselected listener keeps native access '+name+' IPv'+str(v))
   check(not test(name,v,28080),'system firewall still wins '+name+' IPv'+str(v))
 # An unauthorized peer must still answer VPS-initiated connections,
 # including replies addressed to a protected local port.
 peer_code="""import socket,threading,time
def serve(s,udp):
 while True:
  try:
   if udp:
    data,a=s.recvfrom(1024);s.sendto(data,a)
   else:
    c,_=s.accept()
    with c:c.sendall(c.recv(1024))
  except OSError:break
sockets=[]
for family in [socket.AF_INET,socket.AF_INET6]:
 for udp in [False,True]:
  s=socket.socket(family,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
  if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind(('0.0.0.0' if family==socket.AF_INET else '::',26000))
  if not udp:s.listen()
  sockets.append(s);threading.Thread(target=serve,args=(s,udp),daemon=True).start()
print('ready',flush=True)
time.sleep(120)
"""
 peer_process=subprocess.Popen(['ip','netns','exec',names[1],'python3','-u','-c',peer_code],stdout=subprocess.PIPE,text=True)
 try:
  check(peer_process.stdout.readline().strip()=='ready','isolated external peer is listening')
  for version in [4,6]:
   for udp in [False,True]:
    sock=socket.socket(socket.AF_INET if version==4 else socket.AF_INET6,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM)
    sock.settimeout(2)
    sock.bind(('10.77.2.1' if version==4 else 'fd77:2::1',26666))
    sock.connect(('9.9.9.9' if version==4 else '2001:4860:4860::8888',26000))
    sock.sendall(b'outbound');reply=sock.recv(99);sock.close()
    check(reply==b'outbound','VPS-initiated '+('UDP' if udp else 'TCP')+' reply bypasses protected-port filtering IPv'+str(version))
 finally:
  peer_process.terminate();peer_process.wait(timeout=3)
 try:
  urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8788/v1/sync',b'{}',headers={'X-Pg-Signature':'0'*64}),timeout=3)
  raise AssertionError('unauthorized HTTP accepted')
 except urllib.error.HTTPError as e:check(e.code==401,'actual HTTP rejects unauthorized sync')
 persistent="""import socket,sys
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.settimeout(1);s.connect(('10.77.1.1',24443));s.sendall(b'a');assert s.recv(1)==b'a';print('ready',flush=True)
sys.stdin.readline()
try:s.sendall(b'b');print('open' if s.recv(1)==b'b' else 'closed',flush=True)
except OSError:print('blocked',flush=True)
"""
 p=subprocess.Popen(['ip','netns','exec',names[0],'python3','-u','-c',persistent],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 check(p.stdout.readline().strip()=='ready','existing TCP connection established before source change')
 sync('9.9.9.9')
 p.stdin.write('continue\n');p.stdin.flush()
 check(p.stdout.readline().strip() in ('blocked','closed'),'source change blocks an existing TCP connection')
 p.wait(timeout=3)
 sync('2001:4860:4860::8888')
 for v in [4,6]:
  for udp in [False,True]:
   check(not test(names[0],v,24443,udp) and test(names[1],v,24443,udp),'new dynamic source takes over IPv'+str(v)+(' UDP' if udp else ' TCP'))
 engine.leases[4]=(engine.leases[4][0],time.monotonic()+2)
 driver.apply(engine.effective_policy(),engine.leases);time.sleep(3)
 check(not test(names[1],4,24443,True),'kernel expires a dynamic lease without a subsequent sync')
 check(test(names[0],4,22) and test(names[0],4,23456),'SSH and static rules remain after dynamic expiry')
 sync('8.8.8.8',2)
 check(test(names[0],4,24443,True),'IPv4 authorization positive control before family removal')
 sync('2606:4700:4700::1111',3,families=[6])
 check(not test(names[0],4,24443,True) and test(names[0],6,24443,True),'IPv6-only update revokes the existing IPv4 dynamic authorization')
 check(test(names[0],4,23456),'static IPv4 access remains independent of dynamic family selection')
 sync('9.9.9.9',4)
 # Real repeated policy replacement, not only a mocked interface.
 flood="""import socket,time,json,sys,select
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.015);end=time.monotonic()+180;received=0;sent=0
while time.monotonic()<end and not select.select([sys.stdin],[],[],0)[0]:
 s.sendto(b'blocked',('10.77.1.1',24443));sent+=1
 try:
  if s.recv(99)==b'blocked':received+=1
 except OSError:pass
print(json.dumps({'sent':sent,'received':received}))
"""
 sync('9.9.9.9',4)
 floodproc=subprocess.Popen(['ip','netns','exec',names[0],'python3','-c',flood],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 for revision in range(5,11):
  altered=json.loads(json.dumps(policy));altered[1]['ports'].append(str(25001+revision%2))
  sync('9.9.9.9',revision,altered)
  check(test(names[1],4,24443,True),'authorized UDP works after policy update '+str(revision))
 counts=json.loads(floodproc.communicate('stop\n',timeout=10)[0])
 check(counts['sent']>10 and counts['received']==0,'six actual rule replacements leak zero unauthorized UDP packets '+json.dumps(counts))
 # IPv4 refreshes intentionally retain a separately leased IPv6 family.
 # Move both families before asserting that the first peer is unauthorized.
 sync('2001:4860:4860::8888',11,policy,legacy=True)
 confirmed=sync('9.9.9.9',11,policy,legacy=True)
 check(confirmed['policy']['default_deny'] is False and confirmed['policy']['auto_discover'] is False,'signed legacy flags are confirmed as selected-port-only')
 for name in names:
  for version in [4,6]:
   check(test(name,version,25000),'legacy flags leave unselected listeners alone '+name+' IPv'+str(version))
   check(not test(name,version,28080),'legacy flags preserve the native firewall rejection '+name+' IPv'+str(version))
 for version in [4,6]:
  for udp in [False,True]:
   check(not test(names[0],version,24443,udp),'legacy flags retain selected-port rejection IPv'+str(version)+(' UDP' if udp else ' TCP'))
 sync('9.9.9.9',12,policy,False)
 check(test(names[0],4,24443) and not test(names[0],4,28080),'disabled access policy leaves the system firewall effective')
 # Simulate an interrupted update by retaining the actual independently committed guard.
 driver.commit(m.render(engine.state['policy'],engine.leases,m.GUARD))
 restarted=m.Engine('a'*40,'home',Path(tmp.name)/'state.json',m.Nft())
 check(restarted.driver.snapshot(m.GUARD) is None and restarted.leases=={},'restart repairs a leftover guard and discards dynamic leases')
 driver.cleanup()
 check(driver.snapshot() is None and driver.snapshot(m.GUARD) is None,'cleanup removes only both owned tables')
 check(driver.call(['list','table','inet','access_unrelated'],check=False).returncode==0,'unrelated firewall table preserved')
 # Simulate a cold start by removing all owned tables after a real signed
 # policy update. Invalid config/state must not turn into a whole-host block.
 sync('9.9.9.9',13,policy)
 driver.cleanup()
 check(test(names[0],4,25000) and test(names[0],6,25000),'unselected listeners are reachable after explicit cleanup')
 badconfig=Path(tmp.name)/'bad.json';badconfig.write_text(json.dumps({'device_id':'home','agent_secret':'bad'}))
 state=Path(tmp.name)/'state.json'
 failed=subprocess.run([sys.executable,str(ROOT/'companion/vps/agent.py'),'--config',str(badconfig),'--state',str(state),'--restore-policy'],capture_output=True,text=True,timeout=25)
 check(failed.returncode!=0 and driver.snapshot(m.BOOT)is not None,'invalid config retains last selected-port startup protection')
 for version in [4,6]:
  check(not test(names[0],version,24443) and test(names[0],version,25000) and test(names[0],version,22),'startup guard restricts selected port and preserves other access IPv'+str(version))
 driver.cleanup();state.write_text('{')
 validconfig=Path(tmp.name)/'valid.json';validconfig.write_text(json.dumps({'device_id':'home','agent_secret':'a'*40}))
 failed=subprocess.run([sys.executable,str(ROOT/'companion/vps/agent.py'),'--config',str(validconfig),'--state',str(state),'--restore-policy'],capture_output=True,text=True,timeout=25)
 check(failed.returncode!=0 and driver.snapshot(m.BOOT)is not None,'corrupt main state restores separate last-valid port cache')
 for version in [4,6]:
  check(not test(names[0],version,24443) and test(names[0],version,25000),'cached startup protection does not take over other listeners IPv'+str(version))
 restored=subprocess.run([sys.executable,str(ROOT/'companion/vps/agent.py'),'--config',str(validconfig),'--state',str(Path(tmp.name)/'fresh.json'),'--restore-policy'],capture_output=True,text=True,timeout=25)
 check(restored.returncode==0 and driver.snapshot(m.BOOT)is None and driver.snapshot()is not None,'first installation with no selected ports adds no source restrictions')
 check(test(names[0],4,25000) and test(names[0],6,25000) and test(names[0],4,24443),'empty selected-port policy leaves listeners to native firewall')
 check(not test(names[0],4,28080),'empty selected-port policy cannot override native firewall')
 driver.cleanup();check(driver.snapshot(m.BOOT)is None,'explicit cleanup removes the owned bootstrap table')
 print('PASS VPS access real packet and HTTP suite',flush=True)
finally:
 server.shutdown();stop.set()
 for s in sockets:s.close()
 for name in names:cmd('ip','netns','delete',name,check=False)
 tmp.cleanup()
