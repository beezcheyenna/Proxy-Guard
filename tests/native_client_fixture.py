"""Disposable offline router fixture. Never run outside a marked test VM."""
from pathlib import Path
import os,sys,subprocess,json,time,ssl,http.server,socket,socketserver,threading,struct,shutil,tempfile
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
D=Path('/tmp/pg-offline-fixture');D.mkdir(exist_ok=True)
def cmd(*args,check=True,timeout=120):
 # An upstream daemon may retain init stdout after its parent exits. A file
 # keeps the real parent exit/timeout meaningful without waiting for pipe EOF.
 with tempfile.TemporaryFile(mode='w+t')as capture:
  p=subprocess.run(args,stdout=capture,stderr=subprocess.STDOUT,text=True,check=False,timeout=timeout)
  capture.seek(0);p.stdout=capture.read();p.stderr=''
  if check and p.returncode:raise subprocess.CalledProcessError(p.returncode,args,p.stdout,p.stderr)
  return p
def bg(args,log):
 f=(D/log).open('ab');return subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
def setuci(key,value):
 cmd('uci','set',key+'='+str(value))
def assert_firmware_modules():
 # Bundled vendor kernel modules must survive lab package setup unchanged.
 # Equal version/vermagic strings do not establish ABI compatibility.
 import hashlib
 changed=[]
 for rom in Path('/rom/lib/modules').rglob('*.ko'):
  live=Path(str(rom).replace('/rom/','/',1))
  if not live.is_file() or hashlib.sha256(live.read_bytes()).digest()!=hashlib.sha256(rom.read_bytes()).digest():
   changed.append(str(live))
 assert not changed,'Lab preparation replaced bundled firmware modules: '+repr(changed)
def setup():
 assert_firmware_modules()
 assert cmd('ip','netns','list').stdout.strip()=='','fresh namespace fixture required'
 cmd('ip','netns','add','pgwan');cmd('ip','netns','add','pglan')
 cmd('ip','link','add','pgwan0','type','veth','peer','name','pgwan1')
 cmd('ip','link','set','pgwan1','netns','pgwan')
 cmd('ip','link','add','pglan0','type','veth','peer','name','pglan1')
 cmd('ip','link','set','pglan1','netns','pglan')
 cmd('ip','link','set','pglan0','master','br-lan');cmd('ip','link','set','pglan0','up')
 for ns,iface,ip4,ip6 in [('pgwan','pgwan1','10.88.0.2/24','fd88::2/64'),('pglan','pglan1','10.77.0.2/24','fd77:88::2/64')]:
  for args in [('link','set','lo','up'),('link','set',iface,'up'),('addr','add',ip4,'dev',iface),('-6','addr','add',ip6,'dev',iface,'nodad')]:
   cmd('ip','-n',ns,*args)
 for address in ['9.9.9.9/32','9.9.9.10/32']:cmd('ip','-n','pgwan','addr','add',address,'dev','lo')
 cmd('ip','-n','pgwan','-6','addr','add','2001:4860:99::9/128','dev','lo','nodad')
 cmd('ip','-n','pgwan','route','replace','10.77.0.0/24','via','10.88.0.1')
 cmd('ip','-n','pgwan','-6','route','replace','fd77:88::/64','via','fd88::1')
 cmd('ip','-n','pglan','route','replace','default','via','10.77.0.1')
 cmd('ip','-n','pglan','-6','route','replace','default','via','fd77:88::1')
 cmd('uci','-q','del_list','network.@device[0].ports=pglan0',check=False)
 cmd('uci','add_list','network.@device[0].ports=pglan0')
 setuci('network.lan.ipaddr','10.77.0.1/24')
 setuci('network.wan.proto','static');setuci('network.wan.device','pgwan0');setuci('network.wan.ipaddr','10.88.0.1');setuci('network.wan.netmask','255.255.255.0');setuci('network.wan.gateway','10.88.0.2')
 setuci('network.wan.ip6addr','fd88::1/64');setuci('network.wan.ip6gw','fd88::2')
 cmd('uci','-q','delete','network.wan6',check=False)
 cmd('uci','-q','delete','network.lan.ip6addr',check=False)
 cmd('uci','add_list','network.lan.ip6addr=fd77:88::1/64')
 cmd('uci','set','dhcp.@dnsmasq[0].noresolv=1')
 cmd('uci','-q','delete','dhcp.@dnsmasq[0].server',check=False)
 cmd('uci','add_list','dhcp.@dnsmasq[0].server=9.9.9.9')
 for package in ['network','dhcp']:cmd('uci','commit',package)
 # Explicit fixture prerequisite; the separate default-offload rejection case
 # is retained as negative evidence. Proxy Guard never changes these values.
 setuci('firewall.@defaults[0].flow_offloading','0')
 setuci('firewall.@defaults[0].flow_offloading_hw','0')
 setuci('firewall.@zone[1].masq','0');cmd('uci','commit','firewall')
 cmd('/etc/init.d/network','reload');time.sleep(3)
 cmd('ip','link','set','pglan0','master','br-lan')
 cmd('ip','route','replace','9.9.9.9/32','via','10.88.0.2','dev','pgwan0')
 cmd('ip','route','replace','9.9.9.10/32','via','10.88.0.2','dev','pgwan0')
 cmd('ip','-6','route','replace','2001:4860:99::9/128','via','fd88::2','dev','pgwan0')
 cmd('/etc/init.d/dnsmasq','restart');cmd('/etc/init.d/firewall','reload')
 for key,val in [('net.ipv4.ip_forward','1'),('net.ipv6.conf.all.forwarding','1')]:cmd('sysctl','-w',key+'='+val)
 cert=D/'cert.pem';key=D/'key.pem'
 cmd('openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','3','-keyout',str(key),'-out',str(cert),'-subj','/CN=Proxy Guard offline fixture',
  '-addext','subjectAltName=DNS:one.test,DNS:two.test,DNS:api.ipify.org,DNS:api64.ipify.org,DNS:www.cloudflare.com,DNS:www.google.com,DNS:www.gstatic.com,DNS:4.ident.me,DNS:connectivity-check.ubuntu.com',
  '-addext','basicConstraints=critical,CA:TRUE',timeout=90)
 with open('/etc/ssl/certs/ca-certificates.crt','ab')as out:out.write(b'\n'+cert.read_bytes())
 backend={'log':{'loglevel':'warning'},'dns':{'hosts':{'one.test':'9.9.9.9','two.test':'9.9.9.10','api.ipify.org':'9.9.9.9','api64.ipify.org':'9.9.9.9','www.cloudflare.com':'9.9.9.9','www.google.com':'9.9.9.9','www.gstatic.com':'9.9.9.9','4.ident.me':'9.9.9.9','connectivity-check.ubuntu.com':'9.9.9.9'},'servers':['9.9.9.9']},
 'inbounds':[{'listen':'10.88.0.2','port':18080,'protocol':'socks','settings':{'auth':'noauth','udp':True,'ip':'10.88.0.2'}}],
 'outbounds':[{'protocol':'freedom','settings':{'domainStrategy':'UseIP'}}]}
 (D/'backend.json').write_text(json.dumps(backend))
 bg(['ip','netns','exec','pgwan','/usr/bin/xray','run','-config',str(D/'backend.json')],'backend.log')
 bg(['ip','netns','exec','pgwan','python3','-B',__file__,'servers'],'servers.log')
 time.sleep(2)
 check=json.loads(cmd('ip','-j','route','get','10.77.0.2').stdout)[0]
 assert check['dev']=='br-lan' and 'gateway'not in check,('fixture LAN return route',check)
 cmd('ip','netns','exec','pglan','ping','-c','1','-W','3','10.77.0.1')
 cmd('ip','netns','exec','pglan','ping','-6','-c','1','-W','3','fd77:88::1')
 print('PASS offline gateway, LAN return route, IPv4/IPv6 management, backend SOCKS, DNS and HTTPS fixtures prepared',flush=True)
def servers():
 class Http(http.server.BaseHTTPRequestHandler):
  def do_GET(self):
   if '/generate_204'in self.path or self.path=='/health' or self.headers.get('Host')=='connectivity-check.ubuntu.com':code,body=204,b''
   elif '/cdn-cgi/trace'in self.path:code,body=200,b'ip=9.9.9.9\ncolo=NRT\nts=1793400000\n'
   else:code,body=200,b'9.9.9.9\n'
   self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def log_message(self,*args):pass
 for host in ['9.9.9.9','9.9.9.10']:
  context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(D/'cert.pem',D/'key.pem')
  class TLS(http.server.ThreadingHTTPServer):
   def finish_request(self,request,address):
    request.settimeout(3)
    try:
     with context.wrap_socket(request,server_side=True)as secure:Http(secure,address,self)
    except OSError:request.close()
  server=TLS((host,443),Http)
  threading.Thread(target=server.serve_forever,daemon=True).start()
 def dns(data):
  if len(data)<12:return b''
  at=12
  while at<len(data)and data[at]:
   size=data[at];at+=1+size
  at+=1
  if at+4>len(data):return b''
  kind=struct.unpack('!H',data[at:at+2])[0];end=at+4
  raw=socket.inet_pton(socket.AF_INET,'9.9.9.9')if kind==1 else socket.inet_pton(socket.AF_INET6,'2001:4860:99::9')if kind==28 else None
  answer=b'\xc0\x0c'+struct.pack('!HHIH',kind,1,30,len(raw))+raw if raw else b''
  return data[:2]+b'\x81\x80\x00\x01'+struct.pack('!H',int(raw is not None))+b'\x00\x00\x00\x00'+data[12:end]+answer
 class TCP(socketserver.BaseRequestHandler):
  def handle(self):
   if self.server.server_address[1]==53:
    data=self.request.recv(2)
    if len(data)!=2:return
    size=struct.unpack('!H',data)[0];data=b''
    while len(data)<size:
     q=self.request.recv(size-len(data))
     if not q:return
     data+=q
    reply=dns(data);self.request.sendall(struct.pack('!H',len(reply))+reply)
   else:
    self.request.settimeout(120)
    try:
     while True:
      data=self.request.recv(4096)
      if not data:return
      self.request.sendall(data)
    except OSError:pass
 class UDP(socketserver.BaseRequestHandler):
  def handle(self):
   data,sock=self.request
   sock.sendto(dns(data)if self.server.server_address[1]==53 else data,self.client_address)
 class T(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
 class U(socketserver.ThreadingUDPServer):allow_reuse_address=True;daemon_threads=True
 class T6(T):address_family=socket.AF_INET6
 class U6(U):address_family=socket.AF_INET6
 for address in ['9.9.9.9','2001:4860:99::9']:
  for port in [53,23456]:
   for cls,handler in [(T if ':'not in address else T6,TCP),(U if ':'not in address else U6,UDP)]:
    server=cls((address,port),handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 print('SERVERS_READY',flush=True)
 while True:time.sleep(30)

def wait_openclash_ready(started):
 """The upstream init returns before check_core_status installs its rules."""
 import re,hashlib
 end=time.monotonic()+180;rows=[];streak=0;last_digest=None
 try:
  while time.monotonic()<end:
   log=Path('/tmp/openclash.log').read_text(errors='replace')
   lines=log.splitlines();starts=[i for i,l in enumerate(lines)if 'OpenClash Start Running...'in l]
   done=[]
   for i,line in enumerate(lines):
    if 'OpenClash Start Successful!'not in line:continue
    try:stamp=time.mktime(time.strptime(line[:19],'%Y-%m-%d %H:%M:%S'))
    except ValueError:continue
    if stamp>=int(started)and starts and i>starts[-1]:done.append(line)
   chain=cmd('nft','list','chain','inet','fw4','openclash_mangle_v6',check=False).stdout
   hook=cmd('nft','list','chain','inet','fw4','mangle_prerouting',check=False).stdout
   rules=cmd('ip','-6','rule','show',check=False).stdout
   routes=cmd('ip','-6','route','show','table','354',check=False).stdout
   udp=cmd('uci','-q','get','openclash.config.enable_v6_udp_proxy',check=False).stdout.strip()=='1'
   mode=cmd('uci','-q','get','openclash.config.ipv6_mode',check=False).stdout.strip()or'0'
   expected='default dev utun'if mode=='2'else'local default dev lo'
   ready=bool(done)and'jump openclash_mangle_v6'in hook and'0x162'in rules and expected in routes
   if udp:ready=ready and any('udp'in l and('tproxy ip6'in l if mode=='0'else'mark set'in l)for l in chain.splitlines())
   digest=hashlib.sha256(re.sub(r'counter packets \d+ bytes \d+','counter',chain+hook+rules+routes).encode()).hexdigest()
   streak=streak+1 if ready and digest==last_digest else(1 if ready else 0)
   last_digest=digest
   rows.append({'wall':time.time(),'uptime':time.monotonic(),'fresh_completion':done[-1:] ,'ready':ready,'stable_samples':streak,'kernel_identity':digest})
   if streak>=3:
    print('PASS fresh native OpenClash startup completed and actual IPv6 hooks/routes are stable',flush=True)
    return
   time.sleep(1)
  raise AssertionError('OpenClash native startup or IPv6 rules never completed: '+json.dumps(rows[-3:]))
 finally:
  Path('/tmp/pg-upstream-ready.json').write_text(json.dumps({'started':started,'samples':rows,'chain':chain,'hook':hook,'policy':rules,'routes':routes},indent=2))

def client(case):
 assert_firmware_modules()
 # PassWall's real UI forces TPROXY when IPv6 transparency is enabled.
 # REDIRECT fixtures keep that option off: IPv6 forwarding is still tested,
 # but it is direct traffic, and must be blocked by Proxy Guard on failure.
 tcp_redirect=case in ('pwxr','pwsr')
 if tcp_redirect:case=case[:-1]
 if case in ('pwx','pws'):
  cmd('uci','-q','delete','passwall.fixture',check=False)
  values={'passwall.@global[0].enabled':'1','passwall.@global[0].node':'fixture','passwall.@global[0].node_socks_port':'1070',
   'passwall.@global[0].filter_proxy_ipv6':'0','passwall.@global[0].dns_mode':'tcp','passwall.@global[0].remote_dns':'9.9.9.9',
   'passwall.@global[0].use_direct_list':'0','passwall.@global[0].use_proxy_list':'0','passwall.@global[0].use_block_list':'0',
   'passwall.@global[0].use_gfw_list':'0','passwall.@global[0].chn_list':'proxy',
   'passwall.@global_forwarding[0].ipv6_tproxy':'0'if tcp_redirect else'1','passwall.@global_forwarding[0].tcp_proxy_way':'redirect'if tcp_redirect else'tproxy','passwall.@global_forwarding[0].tcp_redir_ports':'1:65535',
   'passwall.@global_forwarding[0].udp_redir_ports':'1:65535','passwall.@global_delay[0].start_delay':'0',
   'passwall.fixture':'nodes','passwall.fixture.remarks':'Offline controlled SOCKS','passwall.fixture.type':'Xray'if case=='pwx'else'sing-box',
   'passwall.fixture.protocol':'socks','passwall.fixture.address':'10.88.0.2','passwall.fixture.port':'18080','passwall.fixture.version':'5'}
  for key,val in values.items():setuci(key,val)
  cmd('uci','commit','passwall');cmd('/etc/init.d/passwall','enable');cmd('/etc/init.d/passwall','restart',timeout=180)
 elif case.startswith('p2'):
  cmd('uci','-q','delete','passwall2.fixture',check=False)
  for key,val in {'passwall2.@global[0].enabled':'1','passwall2.@global[0].node':'fixture','passwall2.@global[0].node_socks_port':'1070',
   'passwall2.@global[0].direct_dns_protocol':'udp','passwall2.@global[0].direct_dns':'9.9.9.9','passwall2.@global[0].remote_dns_protocol':'tcp',
   'passwall2.@global[0].remote_dns':'9.9.9.9','passwall2.@global_forwarding[0].ipv6_tproxy':'1','passwall2.@global_forwarding[0].tcp_proxy_way':'tproxy',
   'passwall2.@global_delay[0].start_delay':'0','passwall2.@global_delay[0].start_daemon':'1',
   'passwall2.fixture':'nodes','passwall2.fixture.remarks':'Offline controlled SOCKS','passwall2.fixture.type':'Xray'if case=='p2x'else'sing-box',
   'passwall2.fixture.protocol':'socks','passwall2.fixture.address':'10.88.0.2','passwall2.fixture.port':'18080','passwall2.fixture.version':'5'}.items():setuci(key,val)
  cmd('uci','commit','passwall2');cmd('/etc/init.d/passwall2','enable');cmd('/etc/init.d/passwall2','restart',timeout=150)
 elif case.startswith(('oc','nk')):
  profile={'port':8080,'socks-port':1080,'mixed-port':7890,'redir-port':7891,'tproxy-port':7892,'allow-lan':True,'bind-address':'*','ipv6':True,
   'mode':'rule','log-level':'info','external-controller':'127.0.0.1:9090','profile':{'store-selected':False},
   'hosts':{'one.test':'9.9.9.9','two.test':'9.9.9.10','api.ipify.org':'9.9.9.9','www.cloudflare.com':'9.9.9.9','www.gstatic.com':'9.9.9.9','4.ident.me':'9.9.9.9','connectivity-check.ubuntu.com':'9.9.9.9'},
   'proxies':[{'name':'offline-fixture','type':'socks5','server':'10.88.0.2','port':18080,'udp':True}],
   'rules':['MATCH,offline-fixture'],'dns':{'enable':True,'listen':'[::]:1053','ipv6':True,'enhanced-mode':'redir-host','default-nameserver':['9.9.9.9'],'nameserver':['udp://9.9.9.9']},
   'tun':{'enable':case.endswith('t'),'device':'nikki'if case.startswith('nk')else'utun','stack':'mixed','auto-route':False,'auto-detect-interface':False}}
  if case.startswith('nk'):
   dest=Path('/etc/nikki/profiles/offline.yaml');dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(profile))
   for key,val in {'nikki.config.enabled':'1','nikki.config.profile':'file:offline.yaml','nikki.proxy.tcp_mode':'tun'if case.endswith('t')else'redirect',
    'nikki.proxy.udp_mode':'tun'if case.endswith('t')else'tproxy','nikki.mixin.dns_mode':'redir-host',
    'nikki.mixin.dns_nameserver':'1','nikki.log.clear_at_stop':'0','nikki.mixin.ui_url':'','nikki.log.scheduled_clear':'0'}.items():setuci(key,val)
   # Keep the client's default local SOCKS authentication enabled.
   for index in range(20):
    row=cmd('uci','-q','get',f'nikki.@nameserver[{index}].type',check=False)
    if row.returncode:break
    cmd('uci','-q','delete',f'nikki.@nameserver[{index}].nameserver',check=False);cmd('uci','add_list',f'nikki.@nameserver[{index}].nameserver=udp://9.9.9.9')
   cmd('uci','commit','nikki');cmd('/etc/init.d/nikki','enable');cmd('/etc/init.d/nikki','restart',timeout=180)
  else:
   dest=Path('/etc/openclash/config/offline.yaml');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(profile))
   core=Path('/etc/openclash/core/clash_meta');core.parent.mkdir(parents=True,exist_ok=True);candidate=Path('/mnt/pg-clients/tools/mihomo');candidate=candidate if candidate.exists()else Path('/usr/bin/mihomo')
   if candidate.resolve()!=core.resolve():shutil.copyfile(candidate,core)
   core.chmod(0o755)
   for key,val in {'openclash.config.config_path':str(dest),'openclash.config.enable':'1','openclash.config.en_mode':'redir-host-tun'if case.endswith('t')else'redir-host',
    'openclash.config.core_type':'Meta','openclash.config.ipv6_enable':'1','openclash.config.enable_custom_dns':'0','openclash.config.router_self_proxy':'1',
    'openclash.config.disable_udp_quic':'0','openclash.config.geo_auto_update':'0','openclash.config.geosite_auto_update':'0',
    'openclash.config.china_ip_route':'0','openclash.config.china_ip6_route':'0','openclash.config.proxy_mode':'rule'}.items():setuci(key,val)
   cmd('uci','commit','openclash');cmd('/etc/init.d/openclash','enable');started=time.time();cmd('/etc/init.d/openclash','restart',timeout=180)
   wait_openclash_ready(started)
 elif case.startswith('hp'):
  for key,val in {'homeproxy.fixture':'node','homeproxy.fixture.type':'socks','homeproxy.fixture.address':'10.88.0.2','homeproxy.fixture.port':'18080',
   'homeproxy.config.main_node':'fixture','homeproxy.config.main_udp_node':'same','homeproxy.config.routing_mode':'global',
   'homeproxy.config.proxy_mode':'tun'if case.endswith('t')else'redirect_tproxy','homeproxy.config.routing_port':'',
   'homeproxy.config.dns_server':'tcp://9.9.9.9','homeproxy.config.ipv6_support':'1','homeproxy.control.lan_proxy_mode':'global'}.items():setuci(key,val)
  cmd('uci','commit','homeproxy');cmd('/etc/init.d/homeproxy','enable');cmd('/etc/init.d/homeproxy','restart',timeout=150)
 else:raise ValueError('unknown client case '+case)
 print('PASS actual upstream init invoked '+case,flush=True)
if __name__=='__main__':
 if sys.argv[1]=='setup':setup()
 elif sys.argv[1]=='servers':servers()
 elif sys.argv[1]=='client':client(sys.argv[2])
