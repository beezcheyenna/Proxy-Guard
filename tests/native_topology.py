"""Real same-interface routing, bridge bypass and asymmetric-return tests."""
from pathlib import Path
import json,subprocess,time,sys,traceback,tempfile,concurrent.futures,hashlib
assert Path('/etc/pgvm-fixture').is_file()
O=Path('/tmp/pg-native-topology');O.mkdir()
checks=[];pids=[];start=time.monotonic()
def run(*args,check=True,timeout=120,input=None):
 with tempfile.TemporaryFile(mode='w+t')as f:
  p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,text=True,timeout=timeout,input=input);f.seek(0);out=f.read()
 with(O/'commands.jsonl').open('a')as f:f.write(json.dumps({'argv':args,'rc':p.returncode,'out':out})+'\n')
 if check:assert p.returncode==0,(args,p.returncode,out[-3000:])
 return out
def rpc(obj,method,args=None):return json.loads(run('ubus','-t','60','call',obj,method,json.dumps(args or{}))or'{}')
def ok(v,label):
 assert v,label
 checks.append(label);print('PASS '+label,flush=True)
def wait(fn,label,seconds=100):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  s=rpc('proxy_guard','status')
  if fn(s):ok(True,label);return s
  time.sleep(.5)
 raise AssertionError((label,s))
sid=rpc('session','login',{'username':'root','password':''})['ubus_rpc_session']
def apply(values):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 a=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True});assert a.get('ok'),a
 if a.get('confirmation_required'):
  tx=a['transaction'];end=time.monotonic()+100
  while time.monotonic()<end:
   t=rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction',{})
   if t.get('phase')=='confirming':break
   time.sleep(.3)
  else:raise AssertionError(('confirmation not reached',t))
  c=rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':tx['id'],'token':tx['token']});assert c.get('ok'),c
 return a
server=r"""
import socket,threading,time,sys,json
hosts=json.loads(sys.argv[1]);port=int(sys.argv[2])
def serve(host,kind):
 family=socket.AF_INET6 if ':'in host else socket.AF_INET
 s=socket.socket(family,kind);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((host,port))
 if kind==socket.SOCK_DGRAM:
  while True:
   data,peer=s.recvfrom(2048);s.sendto(data,peer)
 else:
  s.listen(32)
  def echo(c):
   with c:
    while True:
     d=c.recv(2048)
     if not d:return
     c.sendall(d)
  while True:
   c,a=s.accept();threading.Thread(target=echo,args=(c,),daemon=True).start()
for host in hosts:
 for kind in [socket.SOCK_STREAM,socket.SOCK_DGRAM]:threading.Thread(target=serve,args=(host,kind),daemon=True).start()
while True:time.sleep(60)
"""
probe=r"""
import socket,json,secrets,concurrent.futures,sys
targets=json.loads(sys.argv[1]);sources=json.loads(sys.argv[2]);port=int(sys.argv[3])
def one(row):
 proto,family,key,host,source=row;s=socket.socket(family,socket.SOCK_STREAM if proto=='tcp' else socket.SOCK_DGRAM);s.settimeout(2)
 try:
  if source:s.bind((source,0))
  s.connect((host,port));data=secrets.token_bytes(16);s.sendall(data);return key,s.recv(16)==data
 except OSError:return key,False
 finally:s.close()
rows=[(p,f,p+str(i+4),targets[i],sources[i])for i,f in [(0,socket.AF_INET),(1,socket.AF_INET6)]for p in ['tcp','udp']]
# Keep stable family labels 4 and 6.
rows=[(p,f,p+('6'if f==socket.AF_INET6 else'4'),h,s)for p,f,k,h,s in rows]
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:print(json.dumps(dict(pool.map(one,rows))))
"""
def flows(ns,targets,sources,allow,label,port=24680):
 values=json.loads(run('ip','netns','exec',ns,'python3','-c',probe,json.dumps(targets),json.dumps(sources),str(port),timeout=20))
 ok(len(values)==4 and all(v is allow for v in values.values()),label+' '+json.dumps(values))
def bg(ns,hosts,port,name):
 log=(O/(name+'.log')).open('w')
 p=subprocess.Popen(['ip','netns','exec',ns,'python3','-u','-c',server,json.dumps(hosts),str(port)],stdout=log,stderr=subprocess.STDOUT);pids.append(p)
def nsrun(ns,*args):return run('ip','-n',ns,*args)
try:
 original=rpc('uci','get',{'config':'proxy_guard','section':'main'})['values']
 (O/'original.json').write_text(json.dumps(original))
 apply({'enabled':'0'});wait(lambda s:s.get('enforcement')=='off','public disable leaves baseline unfiltered')
 run('/etc/init.d/proxy-guard','stop');run('/etc/init.d/passwall','stop',timeout=240)
 for ns,root,peer,ip4,ip6 in [('pgaltgw','pgalt0','pgalt1','10.77.0.254/24','fd77:88::fe/64'),('pgbypass','pgbypass0','pgbypass1','10.77.0.3/24','fd77:88::3/64')]:
  run('ip','netns','add',ns);run('ip','link','add',root,'type','veth','peer','name',peer);run('ip','link','set',peer,'netns',ns)
  run('ip','link','set',root,'master','br-lan');run('ip','link','set',root,'up')
  for args in [('link','set','lo','up'),('link','set',peer,'up'),('addr','add',ip4,'dev',peer),('-6','addr','add',ip6,'dev',peer,'nodad')]:nsrun(ns,*args)
 for addr in ['9.9.9.20/32','10.99.0.2/32']:nsrun('pgaltgw','addr','add',addr,'dev','lo')
 for addr in ['2001:4860:99::20/128','fd99::2/128']:nsrun('pgaltgw','-6','addr','add',addr,'dev','lo','nodad')
 for ns in ['pgbypass','pglan']:
  for family in ['ipv4','ipv6']:
   run('ip','netns','exec',ns,'sysctl','-w','net.'+family+'.conf.all.accept_redirects=0')
 nsrun('pgbypass','route','replace','default','via','10.77.0.254')
 nsrun('pgbypass','-6','route','replace','default','via','fd77:88::fe')
 for host in ['9.9.9.20/32','10.99.0.2/32']:run('ip','route','replace',host,'via','10.77.0.254','dev','br-lan')
 for host in ['2001:4860:99::20/128','fd99::2/128']:run('ip','-6','route','replace',host,'via','fd77:88::fe','dev','br-lan')
 # Force the protected client's return path through the router in both families.
 nsrun('pgaltgw','route','replace','10.77.0.2/32','via','10.77.0.1','dev','pgalt1')
 nsrun('pgaltgw','-6','route','replace','fd77:88::2/128','via','fd77:88::1','dev','pgalt1')
 # A recreated veth has a new peer MAC; discard only the fixture peer's stale neighbor entries.
 run('ip','neigh','del','10.77.0.254','dev','br-lan',check=False)
 run('ip','-6','neigh','del','fd77:88::fe','dev','br-lan',check=False)
 deadline=time.monotonic()+70
 while any(Path('/sys/class/net/'+n+'/brport/state').read_text().strip()!='3' for n in ['pgalt0','pgbypass0']):
  assert time.monotonic()<deadline,'fixture bridge ports did not become forwarding'
  time.sleep(.2)
 for args in [('ping','-c','1','-W','2','10.77.0.254'),('ping','-6','-I','fd77:88::1','-c','1','-W','2','fd77:88::fe')]:
  run(*args)
 bg('pgaltgw',['9.9.9.20','2001:4860:99::20','10.99.0.2','fd99::2'],24680,'remote-echo')
 bg('pglan',['10.77.0.2','fd77:88::2'],24681,'protected-echo');time.sleep(2)
 receiver='table inet pg_topology_arrivals {\n'
 for key in ['tcp4','udp4','tcp6','udp6']:receiver+=' counter '+key+' {}\n'
 receiver+=' chain input { type filter hook input priority -399; policy accept;\n'
 for family,addr,suffix in [('ip','10.77.0.2','4'),('ip6','fd77:88::2','6')]:
  for proto in ['tcp','udp']:receiver+=f' {family} daddr {addr} {proto} dport 24681 counter name {proto}{suffix}\n'
 receiver+=' }\n}\n'
 run('ip','netns','exec','pglan','nft','-f','-',input=receiver)
 def arrivals():
  rows=json.loads(run('ip','netns','exec','pglan','nft','-j','list','table','inet','pg_topology_arrivals'))['nftables']
  return {r['counter']['name']:r['counter']['packets']for r in rows if 'counter'in r}
 def zero_arrivals():run('ip','netns','exec','pglan','nft','reset','counters','table','inet','pg_topology_arrivals')

 pub=['9.9.9.20','2001:4860:99::20'];lan=['10.77.0.2','fd77:88::2'];local=['10.99.0.2','fd99::2']
 flows('pglan',pub,lan,True,'unprotected baseline supports same-interface routed TCP/UDP IPv4/IPv6')
 flows('pgaltgw',lan,pub,True,'unprotected reverse routing works without NAT',24681)
 ok(len(arrivals())==4 and all(v>0 for v in arrivals().values()),'receiver counters see all four baseline arrival paths')
 flows('pgbypass',pub,['10.77.0.3','fd77:88::3'],True,'alternate gateway bridge baseline works')
 flows('pglan',local,lan,True,'cross-subnet LAN baseline works')
 values={'enabled':'1','mode':'guard','proxy_client':'passwall','client_auto_ports':'0','passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','exit_check':'0','udp_check':'0','socks_port':'1070','startup_grace':'0','fail_threshold':'1','recover_threshold':'1','interval':'5','timeout':'2','schedule_enabled':'0','interfaces':['br-lan'],'sources4':['10.77.0.0/24'],'sources6':['fd77:88::/64'],'local4':['10.77.0.0/24','10.99.0.0/24'],'local6':['fd77:88::/64','fd99::/64'],'proxy_ports':['1070','1041'],'dns_ports':['53','11400'],'targets':['https://one.test/generate_204|204','https://two.test/generate_204|204']}
 apply(values);wait(lambda s:s.get('enforcement')=='blocked','real unavailable SOCKS path blocks the whole configured LAN range')
 flows('pglan',pub,lan,False,'same-interface routed traffic is blocked in all four paths')
 zero_arrivals()
 flows('pgaltgw',lan,pub,False,'return traffic traversing the router is blocked without NAT',24681)
 ok(all(v==0 for v in arrivals().values()),'no packets reached protected receivers while the return path traversed the router')
 flows('pgbypass',pub,['10.77.0.3','fd77:88::3'],True,'devices in the protected subnet using another gateway remain usable over pure bridging')
 flows('pglan',local,lan,True,'explicit cross-subnet LAN exceptions remain usable')
 run('/etc/init.d/firewall','reload',timeout=160)
 flows('pglan',pub,lan,False,'native firewall reload retains same-interface blocking')
 flows('pgbypass',pub,['10.77.0.3','fd77:88::3'],True,'native firewall reload preserves other-gateway bridge traffic')
 nsrun('pgaltgw','route','del','10.77.0.2/32');nsrun('pgaltgw','-6','route','del','fd77:88::2/128')
 zero_arrivals()
 flows('pgaltgw',lan,pub,False,'responses still traverse the router so asymmetric flows do not complete',24681)
 received=arrivals()
 ok(len(received)==4 and all(v>0 for v in received.values()),'asymmetric incoming packets bypass the router and reach the protected receiver despite blocked replies '+json.dumps(received))
 result={'ok':True,'checks':checks,'seconds':time.monotonic()-start}
except Exception:
 result={'ok':False,'checks':checks,'seconds':time.monotonic()-start,'error':traceback.format_exc()};print(result['error'],flush=True)
finally:
 for p in pids:
  p.terminate()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 for file in ['status.json','firewall.json','fast.json']:
  f=Path('/var/run/proxy-guard')/file
  if f.exists():(O/file).write_bytes(f.read_bytes())
 (O/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok'] else 1)
