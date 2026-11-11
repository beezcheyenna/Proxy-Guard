"""Early-boot packet fixture. Run only in disposable, disconnected router VMs."""
from pathlib import Path
import json,sys,subprocess,time,threading,socket,secrets,os,shutil
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
R=Path('/usr/share/pg-lab-boot');D=Path('/tmp/pg-offline-fixture');O=Path('/tmp/pg-early-boot')
def cmd(*a,check=True):
 p=subprocess.run(a,capture_output=True,text=True,timeout=25)
 if check:assert p.returncode==0,(a,p.stdout,p.stderr)
 return p.stdout
def bg(a,name):
 O.mkdir(exist_ok=True)
 return subprocess.Popen(a,stdin=subprocess.DEVNULL,stdout=(O/(name+'.log')).open('w'),stderr=subprocess.STDOUT,start_new_session=True).pid
def install():
 R.mkdir(exist_ok=True)
 assert D.is_dir() and all((D/n).is_file()for n in ['cert.pem','key.pem','backend.json'])
 for n in ['cert.pem','key.pem','backend.json']:shutil.copy2(D/n,R/n)
 shutil.copy2('/tmp/pg_latest_fixture.py',R/'fixture.py')
 shutil.copy2(__file__,R/'early.py')
 init=Path('/etc/init.d/pg-lab-early')
 init.write_text('#!/bin/sh /etc/rc.common\nSTART=13\nSTOP=89\nstart() {\n    /usr/bin/python3 -B /usr/share/pg-lab-boot/early.py start >/tmp/pg-early-prepare.log 2>&1\n}\n')
 init.chmod(0o755);cmd(str(init),'enable')
 print('INSTALLED private fixture before Proxy Guard and netifd; no guard service was refreshed')
def start():
 O.mkdir(exist_ok=True);D.mkdir(exist_ok=True)
 assert not cmd('ip','netns','list').strip(),'early fixture requires fresh boot namespaces'
 cmd('modprobe','veth')
 for n in ['pglan','pgwan']:cmd('ip','netns','add',n)
 for ns,link,peer,addr4,addr6 in [('pglan','pglan0','pglan1','10.77.0.2/24','fd77:88::2/64'),('pgwan','pgwan0','pgwan1','10.88.0.2/24','fd88::2/64')]:
  cmd('ip','link','add',link,'type','veth','peer','name',peer)
  cmd('ip','link','set',peer,'netns',ns)
  for args in [('link','set','lo','up'),('link','set',peer,'up'),('addr','add',addr4,'dev',peer),('-6','addr','add',addr6,'dev',peer,'nodad')]:cmd('ip','-n',ns,*args)
  cmd('ip','link','set',link,'up')
 for ip in ['9.9.9.9/32','9.9.9.10/32']:cmd('ip','-n','pgwan','addr','add',ip,'dev','lo')
 cmd('ip','-n','pgwan','-6','addr','add','2001:4860:99::9/128','dev','lo','nodad')
 cmd('ip','-n','pgwan','route','replace','10.77.0.0/24','via','10.88.0.1')
 cmd('ip','-n','pgwan','-6','route','replace','fd77:88::/64','via','fd88::1')
 cmd('ip','-n','pglan','route','replace','default','via','10.77.0.1')
 cmd('ip','-n','pglan','-6','route','replace','default','via','fd77:88::1')
 rule='table inet pg_early_arrivals {\n'
 for k in ['tcp4','udp4','tcp6','udp6']:rule+=' counter '+k+' {}\n'
 rule+=' chain input { type filter hook input priority -399; policy accept;\n'
 for family,host,suffix in [('ip','9.9.9.9','4'),('ip6','2001:4860:99::9','6')]:
  for proto in ['tcp','udp']:rule+=f' {family} daddr {host} {proto} dport 23456 counter name {proto}{suffix}\n'
 rule+=' }\n}\ntable inet pg_fixture_outage { chain input { type filter hook input priority -300; policy accept; tcp dport 443 drop; }\n}\n'
 (O/'receivers.nft').write_text(rule)
 cmd('ip','netns','exec','pgwan','nft','-f',str(O/'receivers.nft'))
 for n in ['cert.pem','key.pem','backend.json']:shutil.copy2(R/n,D/n)
 pids={}
 pids['backend']=bg(['ip','netns','exec','pgwan','/usr/bin/xray','run','-config',str(D/'backend.json')],'backend')
 pids['servers']=bg(['ip','netns','exec','pgwan','python3','-B',str(R/'fixture.py'),'servers'],'servers')
 pids['pump']=bg(['ip','netns','exec','pglan','python3','-B',str(R/'early.py'),'pump'],'pump')
 pids['observe']=bg(['python3','-B',str(R/'early.py'),'observe'],'observe')
 (O/'ready.json').write_text(json.dumps({'uptime':float(Path('/proc/uptime').read_text().split()[0]),'pids':pids,'guard_table_at_start':cmd('nft','list','tables'),'guard_enabled':cmd('uci','-q','get','proxy_guard.main.enabled')}))
def pump():
 rows=[(p+z,f,t,h)for f,h,z in [(socket.AF_INET,'9.9.9.9','4'),(socket.AF_INET6,'2001:4860:99::9','6')]for p,t in [('tcp',socket.SOCK_STREAM),('udp',socket.SOCK_DGRAM)]]
 until=time.monotonic()+180;counts={};threads=[]
 def worker(row):
  k,f,t,h=row;attempts=success=0;first=None
  while time.monotonic()<until:
   s=socket.socket(f,t);s.settimeout(.3);attempts+=1
   try:
    s.bind(('fd77:88::2'if f==socket.AF_INET6 else'10.77.0.2',0))
    s.connect((h,23456));data=secrets.token_bytes(16);s.sendall(data)
    if s.recv(16)==data:
     success+=1
     if first is None:first=float(Path('/proc/uptime').read_text().split()[0])
   except OSError:pass
   finally:s.close()
   time.sleep(.08)
  counts[k]={'attempts':attempts,'responses':success,'first_response_uptime':first}
 for row in rows:
  t=threading.Thread(target=worker,args=(row,));t.start();threads.append(t)
 for t in threads:t.join()
 (O/'pump.json').write_text(json.dumps(counts))
def observe():
 until=time.monotonic()+180;previous=None
 while time.monotonic()<until:
  tables=cmd('nft','list','tables',check=False)
  addresses=cmd('ip','-j','address','show','dev','br-lan',check=False)
  state={'guard_table':'table inet proxy_guard' in tables,'lan_addresses':addresses}
  if state!=previous:
   with(O/'boot-events.jsonl').open('a')as f:f.write(json.dumps({'uptime':float(Path('/proc/uptime').read_text().split()[0]),**state})+'\n')
   previous=state
  time.sleep(.5)
def report():
 data=json.loads(cmd('ip','netns','exec','pgwan','nft','-j','list','table','inet','pg_early_arrivals'))
 counts={r['counter']['name']:r['counter']['packets']for r in data['nftables']if 'counter'in r}
 print(json.dumps({'arrivals':counts,'ready':json.loads((O/'ready.json').read_text()),'pump':json.loads((O/'pump.json').read_text())if(O/'pump.json').exists()else None,'events':(O/'boot-events.jsonl').read_text()}))
if __name__=='__main__':globals()[sys.argv[1]]()
