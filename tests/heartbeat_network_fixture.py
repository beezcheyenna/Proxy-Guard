#!/usr/bin/env python3
"""Private-network fixture for native_heartbeat_api.py, never for a real router."""
from pathlib import Path
import subprocess,socket,threading,sys,time,json,os,signal
assert Path('/etc/pgvm-fixture').exists()
def cmd(*a):subprocess.run(a,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def cleanup():
 for f in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   argv=f.read_bytes().split(b'\0')
   if len(argv)>2 and argv[1].endswith(b'/heartbeat_network_fixture.py') and argv[2] in (b'serve',b'flow'):
    os.kill(int(f.parent.name),signal.SIGTERM)
  except (OSError,ValueError):pass
def setup():
 cleanup()
 for ns in ['hblan','hbwan']:
  subprocess.run(['ip','netns','del',ns],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  cmd('ip','netns','add',ns);cmd('ip','-n',ns,'link','set','lo','up')
 for name,ns,subnet in [('hb-in','hblan','231'),('hb-out','hbwan','232')]:
  subprocess.run(['ip','link','del',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  cmd('ip','link','add',name,'type','veth','peer','name',name+'-peer')
  cmd('ip','link','set',name+'-peer','netns',ns)
  cmd('ip','addr','add','198.19.'+subnet+'.1/24','dev',name)
  cmd('ip','-6','addr','add','2001:db8:'+subnet+'::1/64','dev',name,'nodad')
  cmd('ip','link','set',name,'up')
  cmd('ip','-n',ns,'addr','add','198.19.'+subnet+'.2/24','dev',name+'-peer')
  cmd('ip','-n',ns,'-6','addr','add','2001:db8:'+subnet+'::2/64','dev',name+'-peer','nodad')
  cmd('ip','-n',ns,'link','set',name+'-peer','up')
  cmd('ip','-n',ns,'route','add','default','via','198.19.'+subnet+'.1')
  cmd('ip','-n',ns,'-6','route','add','default','via','2001:db8:'+subnet+'::1')
 Path('/proc/sys/net/ipv4/ip_forward').write_text('1')
 Path('/proc/sys/net/ipv6/conf/all/forwarding').write_text('1')
 # A flushed fw4 input chain still retains its DROP policy. Establish the
 # disconnected fixture baseline explicitly before testing the plugin.
 for chain in ['input','output','forward']:
  cmd('nft','add','rule','inet','fw4',chain,'counter','accept')
 for ns in ['hblan','hbwan']:
  subprocess.Popen(['ip','netns','exec',ns,'python3',__file__,'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
def serve():
 def stream(c):
  try:
   while True:
    data=c.recv(4096)
    if not data:break
    c.sendall(data)
  except OSError:pass
  finally:c.close()
 def listen(family,kind):
  s=socket.socket(family,kind);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind(('::' if family==socket.AF_INET6 else '0.0.0.0',19444))
  if kind==socket.SOCK_STREAM:s.listen()
  while True:
   if kind==socket.SOCK_STREAM:
    c,_=s.accept();threading.Thread(target=stream,args=(c,),daemon=True).start()
   else:
    data,peer=s.recvfrom(4096);s.sendto(data,peer)
 for family in [socket.AF_INET,socket.AF_INET6]:
  for kind in [socket.SOCK_STREAM,socket.SOCK_DGRAM]:threading.Thread(target=listen,args=(family,kind),daemon=True).start()
 while True:time.sleep(60)
def probe(family,proto,side='232'):
 fam=socket.AF_INET6 if family=='6' else socket.AF_INET
 s=socket.socket(fam,socket.SOCK_STREAM if proto=='tcp' else socket.SOCK_DGRAM)
 s.settimeout(1.2)
 try:
  s.connect(('2001:db8:'+side+'::2' if family=='6' else '198.19.'+side+'.2',19444))
  s.sendall(b'probe');return s.recv(16)==b'probe'
 except OSError:return False
 finally:s.close()
def flow(family,proto):
 fam=socket.AF_INET6 if family=='6' else socket.AF_INET
 s=socket.socket(fam,socket.SOCK_STREAM if proto=='tcp' else socket.SOCK_DGRAM);s.settimeout(.7)
 s.connect(('2001:db8:232::2' if family=='6' else '198.19.232.2',19444))
 path=Path('/tmp/hb-flow-'+family+'-'+proto+'.jsonl')
 for count in range(2000):
  value=str(count).encode();ok=False
  try:s.sendall(value);ok=s.recv(1024)==value
  except OSError:pass
  with path.open('a')as f:f.write(json.dumps({'t':time.monotonic(),'ok':ok})+'\n')
  time.sleep(.3)
if __name__=='__main__':
 if sys.argv[1]=='setup':setup()
 elif sys.argv[1]=='cleanup':cleanup()
 elif sys.argv[1]=='serve':serve()
 elif sys.argv[1]=='probe':sys.exit(0 if probe(*sys.argv[2:])else 1)
 elif sys.argv[1]=='flow':flow(*sys.argv[2:])
