#!/usr/bin/env python3
"""Actual netifd multi-LAN discovery and IPv6 automatic-scope acceptance."""
from pathlib import Path
import json,subprocess,time,ipaddress,traceback,sys
client=sys.argv[1]if len(sys.argv)>1 else'passwall'
assert client in ['passwall','passwall2','openclash','nikki','homeproxy']
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
Q=Path('/tmp/pg-native-scope');Q.mkdir()
backup={str(p):p.read_bytes()for p in [Path('/etc/config/network'),Path('/etc/config/firewall'),Path('/etc/config/proxy_guard')]}
checks=[];owned=[];sid=None
def run(a,check=True,timeout=75):
 p=subprocess.run(a,capture_output=True,text=True,timeout=timeout)
 if check:assert p.returncode==0,(a[:3],p.returncode,p.stderr[-500:])
 return p.stdout
def rpc(o,m,d=None):
 r=json.loads(run(['ubus','-t','20','call',o,m,json.dumps(d or{})],timeout=25)or'{}');assert r.get('ok',True),(m,r);return r
def wait(fn,label,seconds=80):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  r=fn()
  if r:return r
  time.sleep(.5)
 raise AssertionError(label)
def good(v,n):assert v,n;checks.append(n);print('PASS '+n,flush=True)
def apply(values):
 rpc('uci','set',{'ubus_rpc_session':sid,'config':'proxy_guard','section':'main','values':values})
 r=rpc('proxy_guard','apply',{'ubus_rpc_session':sid,'confirm_flow':True})
 if r.get('confirmation_required'):
  t=r['transaction']
  wait(lambda:(rpc('proxy_guard','setup_info',{'ubus_rpc_session':sid}).get('transaction')or{}).get('phase')=='confirming','real auto-scope rule self-check')
  rpc('proxy_guard','setup_confirm',{'ubus_rpc_session':sid,'id':t['id'],'token':t['token']})
try:
 sid=rpc('session','login',{'username':'root','password':json.loads(Path('/tmp/pg-latest-login.json').read_text())['password']})['ubus_rpc_session']
 apply({'enabled':'0'});wait(lambda:rpc('proxy_guard','status').get('enforcement')=='off','initial disabled state')
 assert run(['uci','get','firewall.@zone[0].name']).strip()=='lan'
 assert run(['uci','get','firewall.@zone[1].name']).strip()=='wan'
 for i in range(1,5):
  name='pg_lab'+str(i);bridge='br-pg'+str(i);port='pgt'+str(i);peer=port+'p'
  assert subprocess.run(['uci','-q','get','network.'+name],capture_output=True).returncode!=0
  run(['ip','link','add',bridge,'type','bridge']);owned.append((name,bridge,port))
  run(['ip','link','add',port,'type','veth','peer','name',peer])
  run(['ip','link','set',port,'master',bridge])
  run(['uci','set','network.pg_dev'+str(i)+'=device'])
  run(['uci','set','network.pg_dev'+str(i)+'.name='+bridge])
  run(['uci','set','network.pg_dev'+str(i)+'.type=bridge'])
  run(['uci','add_list','network.pg_dev'+str(i)+'.ports='+port])
  for dev in [port,peer,bridge]:run(['ip','link','set',dev,'up'])
  values={name:'interface',name+'.proto':'static',name+'.device':bridge,name+'.ipaddr':'172.22.'+str(i)+'.1',name+'.netmask':'255.255.255.0',name+'.ip6addr':'fd22:'+str(i)+'::1/64'}
  for k,v in values.items():run(['uci','set','network.'+k+'='+v])
  run(['uci','add_list','firewall.@zone['+('0'if i<4 else'1')+'].network='+name])
 run(['uci','commit','network']);run(['uci','commit','firewall'])
 run(['/etc/init.d/network','reload']);run(['/etc/init.d/firewall','reload'])
 expected={'br-lan','br-pg1','br-pg2','br-pg3'}
 def discover_ready():
  d=rpc('proxy_guard','setup_discover',{'proxy_client':client})
  (Q/'last-discovery.json').write_text(json.dumps(d,indent=2))
  (Q/'last-netifd.json').write_text(run(['ubus','call','network.interface','dump']))
  (Q/'last-links.json').write_text(run(['ip','-j','link']))
  return d if expected<={x['device']for x in d['interfaces']if x['up']}else None
 discovery=wait(discover_ready,'netifd did not expose all four LAN devices',90)
 (Q/'discovery.json').write_text(json.dumps(discovery,indent=2))
 recommended=[r for r in discovery['interfaces']if r['recommended']]
 good({r['device']for r in recommended}==expected,'all four real LAN devices are recommended')
 good('br-pg4'not in {r['device']for r in discovery['interfaces']},'static WAN device is excluded despite having addresses')
 for i in range(1,4):
  r=next(r for r in recommended if r['device']=='br-pg'+str(i))
  good(r['sources4']==['172.22.'+str(i)+'.0/24'] and ipaddress.ip_network('fd22:'+str(i)+'::/64')in [ipaddress.ip_network(x,strict=False)for x in r['sources6']],'actual IPv4/IPv6 prefixes discovered for LAN '+str(i))
 untouched={n:Path(n).read_bytes()for n in backup if n!='/etc/config/proxy_guard'}
 profile=json.loads(run(['ucode','/usr/lib/proxy-guard/inspect-client.uc',client]))
 s4=list(dict.fromkeys(x for r in recommended for x in r['sources4']));s6=list(dict.fromkeys(x for r in recommended for x in r['sources6']))
 apply({'enabled':'1','mode':'guard','proxy_client':client,'interfaces':sorted(expected),'sources4':s4,'sources6':s6,'local4':s4,'local6':s6,'ipv6_protect':'1','passwall_watch':'0','passwall_log_watch':'0','boot_guard':'0','client_auto_ports':'0','socks_port':str(profile['socks_port']),'proxy_ports':[str(x)for x in profile['proxy_ports']],'dns_ports':[str(x)for x in profile['dns_ports']],'cf_event_check':'0','udp_check':'0','exit_check':'1','expected_exit4':'9.9.9.10','exit_url':'https://api.ipify.org/','interval':'5','timeout':'3','fail_threshold':'1','recover_threshold':'1','startup_grace':'0','schedule_enabled':'0'})
 s=wait(lambda:(lambda s:s if s.get('enforcement')=='blocked' and s.get('exit_check',{}).get('observed')=='9.9.9.9'else None)(rpc('proxy_guard','status')),'known wrong exit did not block',80)
 good(True,'actual discovered IPv6 prefixes pass native rule self-check and block on wrong exit')
 rules=run(['nft','list','table','inet','proxy_guard'])
 good(all(n in rules for n in expected),'native rules include every selected LAN device')
 route=json.loads(run(['ip','-n','pglan','-6','-j','route','get','2001:4860:99::9']))[0]
 address=ipaddress.ip_address(route.get('prefsrc')or route.get('src'))
 good(any(address in ipaddress.ip_network(c,strict=False)for c in s6),'automatic IPv6 prefixes cover the actual SLAAC-selected client address')
 flow="""import socket,json,concurrent.futures
rows=[('tcp4',socket.AF_INET,socket.SOCK_STREAM,'9.9.9.9'),('udp4',socket.AF_INET,socket.SOCK_DGRAM,'9.9.9.9'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'2001:4860:99::9'),('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'2001:4860:99::9')]
def f(r):
 n,a,t,h=r;s=socket.socket(a,t);s.settimeout(2)
 try:s.connect((h,23456));s.sendall(b'auto-scope');return n,s.recv(30)==b'auto-scope'
 except OSError:return n,False
 finally:s.close()
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as e:print(json.dumps(dict(e.map(f,rows))))
"""
 flows=json.loads(run(['ip','netns','exec','pglan','python3','-c',flow],timeout=15))
 good(all(v is False for v in flows.values()),'automatic scope blocks IPv4 and SLAAC IPv6 on TCP and UDP')
 good(all(Path(n).read_bytes()==b for n,b in untouched.items()),'discovery and protection apply do not change network or firewall configuration')
 result={'ok':True,'checks':checks,'selected':sorted(expected),'sources4':s4,'sources6':s6,'actual_ipv6_source':str(address),'flows':flows}
except Exception:result={'ok':False,'checks':checks,'error':traceback.format_exc()};print(result['error'],flush=True)
finally:
 try:
  if sid:apply({'enabled':'0'});wait(lambda:rpc('proxy_guard','status').get('enforcement')=='off','cleanup off',40)
 except Exception:result['ok']=False;result['cleanup_off_error']=traceback.format_exc()
 for n,b in backup.items():Path(n).write_bytes(b)
 run(['/etc/init.d/network','reload'],check=False);run(['/etc/init.d/firewall','reload'],check=False)
 for name,bridge,port in owned:
  run(['ip','link','delete',port],check=False);run(['ip','link','delete',bridge],check=False)
 (Q/'complete.json').write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result['ok']else 1)
