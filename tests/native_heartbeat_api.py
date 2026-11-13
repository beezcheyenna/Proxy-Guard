#!/usr/bin/env python3
"""Native heartbeat/API acceptance. ONLY in a disposable, disconnected OpenWrt VM.
Uses real curl, TLS, SOCKS, HTTP API authentication and nftables. The endpoint is a local
fixture on a disconnected guest.
"""
from pathlib import Path
import json,os,subprocess,sys,time,threading,socket,ssl,select,struct,urllib.request,urllib.error,http.server,socketserver,concurrent.futures
assert Path('/etc/pgvm-fixture').is_file() and Path('/.proxy-guard-test-root').is_file()
ROOT=Path('/tmp/hb-acceptance');ROOT.mkdir(exist_ok=True)
RESULT=[];COUNTS=[]
def run(*args,check=True):
 p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=45)
 if check and p.returncode:raise AssertionError((args,p.returncode,p.stdout[-4000:]))
 return p.stdout
def shell(cmd):return run('sh','-c',cmd)
def check(value,name):
 if not value:raise AssertionError(name)
 RESULT.append(name);print('PASS',name,flush=True)
def wait(fn,seconds=35):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  value=fn()
  if value:return value
  time.sleep(.4)
 raise AssertionError('condition timeout')
def uci(options):
 script=''.join("set proxy_guard.main.%s='%s'\n"%(k,v) for k,v in options.items())+'commit proxy_guard\n'
 p=subprocess.run(['uci','batch'],input=script,text=True,capture_output=True)
 assert p.returncode==0,p.stderr
def state():return json.loads(run('ubus','-S','call','proxy_guard','status'))
def confirm_change():
 # A direct UCI commit may be picked up by the production setup observer
 # before the explicit local apply. Confirm the actual transaction, regardless
 # of which path won the lock. Never skip self-check or force a confirmation.
 owned={}
 def ready():
  info=json.loads(run('ubus','-S','call','proxy_guard','setup_info','{"ubus_rpc_session":"local"}'))
  tx=info.get('transaction')
  if not tx:
   result=json.loads(run('ubus','-S','call','proxy_guard','apply','{"confirm_flow":true}',check=False))
   assert result.get('ok') or 'setup_transaction_busy' in str(result),result
   if result.get('ok') and not result.get('confirmation_required'):return {'confirmed':True}
   if result.get('transaction'):owned.update(result['transaction'])
   return False
  if tx.get('phase')!='confirming':return False
  if tx.get('claimable'):
   reply=json.loads(run('ubus','-S','call','proxy_guard','setup_claim',check=False))
   if not reply.get('ok'):
    assert any(e in str(reply) for e in ('setup_transaction_busy','setup_no_pending_transaction',
                                         'setup_transaction_owner_mismatch')),reply
    return False
   tx=reply['transaction']
  if not tx.get('token') and tx.get('id')==owned.get('id'):tx['token']=owned.get('token')
  if not tx.get('token'):
   # The lock owner may still be writing the claimable transaction while
   # this read-only RPC observes it. Poll again instead of assuming a token.
   return False
  reply=json.loads(run('ubus','-S','call','proxy_guard','setup_confirm',
                  json.dumps({'id':tx['id'],'token':tx['token']}),check=False))
  if not reply.get('ok'):
   assert 'setup_transaction_busy' in str(reply) or 'setup_no_pending_transaction' in str(reply),reply
   return False
  return reply
 wait(ready,50)
def apply(options):
 uci(options);confirm_change()
 wait(lambda: state().get('enforcement') not in ('unverified','missing'),15)
def rpc(sid,obj,method,p=None):
 data=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':[sid,obj,method,p or {}]}).encode()
 req=urllib.request.Request('http://127.0.0.1/ubus',data,{'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=20 if method=='test_proxy' else 8)as f:return json.load(f)
API_URL='https://127.0.0.1/cgi-bin/proxy-guard-api'
API_UUID=Path('/var/run/proxy-guard/api-uuid')
# The isolated router's local web server uses its disposable test certificate.
API_TLS=ssl._create_unverified_context()
def http_api(uuid,route='status',payload=None,headers=None,base=API_URL):
 request_headers=dict(headers or {})
 if uuid:request_headers['Authorization']='Bearer '+uuid
 data=None if payload is None else json.dumps(payload).encode()
 if data is not None:request_headers.setdefault('Content-Type','application/json')
 request=urllib.request.Request(base+'/'+route,data,request_headers)
 try:
  reply=urllib.request.urlopen(request,context=API_TLS,timeout=22)
 except urllib.error.HTTPError as error:
  reply=error
 with reply:return reply.code,json.load(reply)

def call(uuid,method,params=None):
 route={'request_block':'block','cancel_block':'cancel'}.get(method,method)
 if params and params.get('refresh'):route='diagnostics'
 body=(params or {}) if route in ('block','cancel') else None
 for attempt in range(8):
  code,value=http_api(uuid,route,body)
  if value.get('error')!='busy':return value
  time.sleep(.25)
 return value

def uuid_value():
 try:return API_UUID.read_text().strip()
 except FileNotFoundError:return False

def is_error(reply):
 return 'error' in reply or reply.get('result',[1])[0]!=0 or not reply['result'][1].get('ok',True)
mode={'web-one':'good','web-two':'good','public':'good','diagnostic':'good','primary_ip':'good','backup_ip':'good'}
PUBLIC_BODY='ネットは広大だわ'.encode()
PGHB_CALLS=[]
DETAIL_HEADERS={
 'Ciphers-SHA1':'GXSPDLP4G3X+prK73a4wBuOaHRc=',
 'Cipher':'AEAD-CHACHA20-POLY1305-SHA256',
 'City':'Tokyo',
 'Client-Port':'49321',
 'Client-TCP':'false',
 'Continent':'AS',
 'Delivery-Rate':'184320',
 'Edge-IP':'2001:db8::5',
 'Edge-Port':'443',
 'Edge-Time':'28',
 'Extensions-LE':'7zIpdDU5pvFPPBI2/PCzqbaXnRA=',
 'HTTP':'HTTP/2',
 'Host':'hb.pghb.app',
 'Method':'GET',
 'Path':'/f',
 'QUIC-RTT':'0',
 'Received-MS':'0',
 'Region':'Tokyo',
 'Region-Code':'13',
 'Request-ID':'9995d743-ea45-40cf-b3d4-8b91a0f6789f',
 'TCP-RTT':'1.2',
 'TLS-Extensions':'dGVzdC1maW5nZXJwcmludA==',
 'TLS-Hello':'312',
 'Timestamp':'1794541291',
}
DETAIL_METADATA={
 'asn':64501,
 'cipher':DETAIL_HEADERS['Cipher'],
 'ciphers_sha1':DETAIL_HEADERS['Ciphers-SHA1'],
 'city':'Tokyo',
 'client_port':49321,
 'client_tcp':False,
 'continent':'AS',
 'country':'JP',
 'delivery_rate':184320,
 'edge_ip':'2001:db8::5',
 'edge_port':443,
 'edge_ms':28,
 'extensions_le':DETAIL_HEADERS['Extensions-LE'],
 'http':'HTTP/2',
 'host':'hb.pghb.app',
 'ip':'203.0.113.7',
 'method':'GET',
 'path':'/f',
 'quic_rtt_ms':0,
 'ray':'abcdef123-NRT',
 'received_ms':0,
 'region':'Tokyo',
 'region_code':'13',
 'request_id':DETAIL_HEADERS['Request-ID'],
 'tcp_rtt_ms':1.2,
 'tls':'TLSv1.3',
 'tls_extensions':DETAIL_HEADERS['TLS-Extensions'],
 'tls_hello_bytes':312,
 'timestamp':1794541291,
}
BASIC_METADATA={key:DETAIL_METADATA[key] for key in ('asn','country','ip','ray','tls')}

class HTTP(http.server.BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  from urllib.parse import urlparse
  u=urlparse(self.path);COUNTS.append((time.monotonic(),u.path))
  path=u.path;public=path in ('/','/f')
  website=self.headers.get('Host','web-one.test').split('.')[0]
  kind=mode['diagnostic' if path=='/f' else 'public' if public else 'primary_ip' if path=='/ip' else 'backup_ip' if path=='/backup' else website]
  nonce=self.headers.get('X-PGHB-Nonce')
  if public:PGHB_CALLS.append((time.monotonic(),path,nonce,kind))
  if kind in ('timeout','stall_good'):time.sleep(5)
  if kind=='slow_good':time.sleep(.9)
  if kind=='deny':code,body=403,b'denied'
  elif kind=='redirect':code,body=302,b'login'
  elif kind=='empty':code,body=200,b''
  elif kind=='malformed':code,body=200,b'<html>login</html>'
  elif public:
   code,body=200,PUBLIC_BODY+(b'\n' if kind=='newline' else b'')
  elif path in ('/ip','/backup'):code,body=200,b'203.0.113.8' if kind=='wrong_ip' else b'203.0.113.7'
  else:code,body=204,b''
  try:
   self.send_response(code);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Type','text/plain' if public else 'application/json')
   if public:
    addresses={'wrong_ip':'203.0.113.8','invalid_ip':'invalid-address','ipv6_only':'2001:db8::7'}
    if kind!='no_ip':self.send_header('X-PGHB-IP',addresses.get(kind,'203.0.113.7'))
    self.send_header('X-PGHB-Country','JP');self.send_header('X-PGHB-ASN','64501')
    self.send_header('X-PGHB-Ray','abcdef123-NRT');self.send_header('X-PGHB-TLS','TLSv1.3')
    self.send_header('CF-Cache-Status','HIT')
    if path=='/f':
     if nonce and kind!='missing_nonce':self.send_header('X-PGHB-Nonce','stale' if kind=='wrong_nonce' else nonce)
     self.send_header('CF-Access-Client-Secret','must-not-copy')
     for name, value in DETAIL_HEADERS.items():self.send_header('X-PGHB-'+name,value)
     self.send_header('X-PGHB-Metro-Code','001')
     self.send_header('X-PGHB-Future','second  value')
     self.send_header('x-pghb-future','<b>literal</b>')
   if code==302:self.send_header('Location','https://web-one.test/login')
   self.end_headers();self.wfile.write(body)
  except (OSError,ssl.SSLError):pass
class TLSServer(socketserver.ThreadingMixIn,http.server.HTTPServer):
 daemon_threads=True
class Socks(socketserver.BaseRequestHandler):
 def handle(self):
  c=self.request;c.settimeout(20)
  def recv(n):
   b=b''
   while len(b)<n:
    a=c.recv(n-len(b))
    if not a:raise OSError('EOF')
    b+=a
   return b
  try:
   v,n=recv(2);recv(n);c.sendall(b'\x05\x00')
   v,cmd,_,typ=recv(4)
   assert cmd==1
   if typ==3:host=recv(recv(1)[0]).decode()
   elif typ==1:host=socket.inet_ntop(socket.AF_INET,recv(4))
   else:raise OSError('Unexpected address family')
   port=struct.unpack('!H',recv(2))[0]
   assert host in ('web-one.test','web-two.test','hb.pghb.app') and port==443,(host,port)
   with socket.create_connection(('127.0.0.1',19443),timeout=3)as remote:
    c.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
    while True:
     ready,_,_=select.select([c,remote],[],[],20)
     if not ready:break
     for src in ready:
      data=src.recv(65536)
      if not data:return
      (remote if src is c else c).sendall(data)
  except (OSError,AssertionError):pass
class SOCKS(socketserver.ThreadingTCPServer):
 allow_reuse_address=True;daemon_threads=True
def accounts():
 password='isolated-fixture-password'
 hashed=run('openssl','passwd','-6','-salt','pgfixture',password).strip()
 for name,role,write in [('pgdenied','luci-base',False),('pgadmin','luci-app-proxy-guard',True),('pgreadonly','luci-app-proxy-guard',False)]:
  script="set rpcd.%s=login\nset rpcd.%s.username='%s'\nset rpcd.%s.password='%s'\nadd_list rpcd.%s.read='%s'\n"%(name,name,name,name,hashed,name,role)
  if write:script+="add_list rpcd.%s.write='%s'\n"%(name,role)
  script+='commit rpcd\n'
  subprocess.run(['uci','batch'],input=script,text=True,check=True)
 run('/etc/init.d/rpcd','reload')
 users={}
 for name in ('pgdenied','pgadmin','pgreadonly'):
  def login():
   try:
    reply=rpc('0'*32,'session','login',{'username':name,'password':password})
    return reply['result'][1]['ubus_rpc_session'] if reply.get('result',[1])[0]==0 else False
   except (OSError,ValueError):return False
  users[name]=wait(login,30)
 return users
def fast_heartbeat_boundary():
 # Real Mihomo listeners + native client adapter, not a mocked running API.
 cfg=Path('/etc/nikki/run/config.yaml');original=cfg.read_bytes();old=run('uci','export','nikki')
 proc=None;log=(ROOT/'mihomo-fast.log').open('w')
 def fast():return json.loads(Path('/var/run/proxy-guard/fast.json').read_text())
 def launch():return subprocess.Popen(['/usr/bin/mihomo','-d','/etc/nikki/run','-f',str(cfg)],stdout=log,stderr=subprocess.STDOUT)
 try:
  subprocess.run(['uci','batch'],input="set nikki.config.core_only='0'\nset nikki.proxy.enabled='1'\nset nikki.proxy.tcp_mode='redirect'\nset nikki.proxy.udp_mode='tproxy'\ncommit nikki\n",text=True,check=True)
  cfg.write_text("mixed-port: 17890\nsocks-port: 17891\nredir-port: 17892\ntproxy-port: 17893\nallow-lan: false\nmode: direct\nlog-level: warning\nipv6: true\ndns:\n  enable: true\n  listen: 127.0.0.1:17894\n  nameserver: [127.0.0.1:15399]\nproxies: []\nrules: []\n")
  proc=launch();time.sleep(1);check(proc.poll() is None,'actual Mihomo core starts for service-monitor integration')
  apply({'check_mode':'public','proxy_client':'nikki','passwall_watch':'1','boot_guard':'1','passwall_log_watch':'0','fast_wait_enabled':'1','fast_wait_seconds':'6','fast_stable_enabled':'1','fast_stable_seconds':'60','public_hb_recover':'3'})
  wait(lambda:state()['enforcement']=='allowing',75)
  f=fast();hb=json.loads(Path('/var/run/proxy-guard/heartbeat.json').read_text())
  check(f['all_up'] and hb['successes']==3 and hb.get('fast_trip')==f['trip'],'boot wait and three heartbeat successes release with actual TCP UDP DNS services')
  mode['public']='deny'
  def delay_and_blocked():
   if fast().get('phase')!='delay':return False
   view=state()
   return view['enforcement']=='blocked' and view['fast_watch']['holding']
  wait(delay_and_blocked,30)
  check(True,'official HTTPS failure in sensitive mode re-enters blocking wait')
  p=subprocess.run(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py','probe','4','tcp'])
  check(p.returncode!=0,'sensitive heartbeat fault blocks actual client TCP traffic')
  mode['public']='good';wait(lambda:state()['enforcement']=='allowing',75)
  check(True,'pending heartbeat recovery does not repeatedly restart blocking wait')
  ready=ROOT/'fw4-lock-ready';ready.unlink(missing_ok=True)
  gate_lock=subprocess.Popen(['ucode','-e',"import {open} from 'fs';let h=open('/var/run/fw4.lock','a');h.lock('x');let r=open('/tmp/hb-acceptance/fw4-lock-ready','w');r.write('1');r.close();sleep(18000);"])
  try:
   wait(ready.exists,7)
   def lease_expired():
    v=json.loads(run('nft','-j','list','set','inet','proxy_guard','service_ifaces'))
    return fast().get('gate_ok') is False and any(not e['set'].get('elem') for e in v['nftables'] if 'set' in e)
   wait(lease_expired,14)
   snap=state()
   check(snap['enforcement']=='blocked' and snap['fast_watch']['gate_ok'] is False,
         'verified kernel block is reported even when fw4 lock delays the watcher')
   p=subprocess.run(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py','probe','4','tcp'])
   check(p.returncode!=0,'expired kernel permit rejects real TCP packets under lock contention')
  finally:
   gate_lock.terminate();gate_lock.wait(timeout=10)
  wait(lambda:state()['enforcement']=='allowing',75)
  proc.terminate();proc.wait(timeout=10)
  wait(lambda:state()['enforcement']=='blocked',15)
  check(True,'real proxy-core exit still blocks independently of a successful heartbeat endpoint')
  proc=launch();wait(lambda:state()['enforcement']=='allowing',75)
  f=fast();hb=json.loads(Path('/var/run/proxy-guard/heartbeat.json').read_text())
  check(hb.get('fast_trip')==f['trip'] and hb['successes']==3,'restarted core requires new incident-bound heartbeat confirmations')
 finally:
  mode['public']='good'
  apply({'passwall_watch':'0','boot_guard':'0','public_hb_recover':'2'})
  if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=10)
  log.close();cfg.write_bytes(original)
  subprocess.run(['uci','import','nikki'],input=old,text=True,check=True);run('uci','commit','nikki')
def mode_switches(reader, denied):
 def allowing():return state()['enforcement']=='allowing'
 def blocked():return state()['enforcement']=='blocked'
 def exit_state(outcome):
  value=state()
  return value if value.get('exit_check',{}).get('outcome')==outcome else False
 def paths(after=0):return [path for _,path in COUNTS[after:]]
 def full_calls():return [entry for entry in PGHB_CALLS if entry[1]=='/f']
 def traffic():
  return subprocess.run(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py',
                         'probe','4','tcp'],stdout=subprocess.DEVNULL).returncode==0

 common={'public_hb_url':'https://ignored.test/','public_hb_interval':'2','public_hb_timeout':'3',
         'public_hb_fail':'2','public_hb_recover':'2','api_enabled':'1','diagnostics_enabled':'1',
         'diagnostics_interval':'10','diagnostics_ttl':'30',
         'cf_event_check':'1','cf_event_source':'trace','cf_event_public_path':'full'}
 apply(dict(common,check_mode='public',exit_check='0'))
 wait(allowing,45)
 check(not full_calls() and '/cdn-cgi/trace' not in paths() and 'cf_event' not in state(),
       'boot and recovery ignore stale Cloudflare settings without reaching /f or Trace')
 check(state().get('observed_exit4')=='203.0.113.7','official status can show the observed IPv4 with verification disabled')
 check(all(n is None for _,path,n,_ in PGHB_CALLS if path=='/'),'routine official HTTPS never sends a nonce')

 detail=call(reader,'status')
 check('diagnostics' not in detail and detail['public_observation']['metadata']==BASIC_METADATA,
       'status returns basic heartbeat metadata without detailed diagnostic headers')
 check(not detail['public_observation']['stale'] and detail['public_observation']['source']=='https://hb.pghb.app/',
       'detailed observation reports freshness and source')
 for candidate in (None,denied,'00000000-0000-4000-8000-000000000000'):
  code,result=http_api(candidate,'diagnostics')
  check(code==401 and 'uuid' not in result,'unauthorized diagnostic request rejected')
 for _ in range(3):state();call(reader,'status')
 check(not full_calls(),'regular state queries send no /f request')

 mode['diagnostic']='wrong_nonce'
 code,response=http_api(reader,'diagnostics')
 snap=response['diagnostics']
 check(code==502 and response['uuid']==reader and snap['nonce_verified'] is False and not snap.get('headers'),
       'wrong nonce returns an error and no diagnostic headers')
 check(allowing() and traffic(),'wrong nonce does not change the real firewall verdict')
 check(len(full_calls())==1,'one diagnostic request makes exactly one upstream request')
 code,response=http_api(reader,'diagnostics')
 check(code==429 and response['retry_after']>0 and response['uuid']==reader,'diagnostic cooldown returned in the same response')
 time.sleep(response['retry_after']+.2)
 mode['diagnostic']='timeout'
 probes=sum(path=='/' for path in paths())
 code,response=http_api(reader,'diagnostics')
 check(code==504 and response['diagnostics']['curl_code']==28 and allowing() and traffic(),'diagnostic timeout returns 504 and preserves traffic')
 wait(lambda:sum(path=='/' for path in paths())>probes,12)
 check(True,'diagnostics do not pause official HTTPS monitoring')
 time.sleep(10.2)
 mode['diagnostic']='good'
 code,response=http_api(reader,'diagnostics')
 snap=response['diagnostics']
 headers={row['name'].lower():row['value'] for row in snap['headers']}
 check(code==200 and response['uuid']==reader and snap['nonce_verified'] and headers['x-pghb-client-tcp']=='false'
       and headers['x-pghb-metro-code']=='001' and
       [row['value'] for row in snap['headers'] if row['name'].lower()=='x-pghb-future']==['second  value','<b>literal</b>'],
       'one authenticated HTTPS request returns raw diagnostic header values and duplicates')
 check('metadata' not in snap and 'must-not-copy' not in json.dumps(snap),'diagnostics expose only PGHB response headers')
 log=run('ubus','-S','call','proxy_guard','logs')
 check('tls_hello_bytes' not in log and 'must-not-copy' not in log and
       DETAIL_METADATA['request_id'] not in log and reader not in log,
       'non-administrative log response omits UUID and detailed response headers')
 if os.getenv('PG_TEST_UUID_ONLY'):return
 return exit_provider_cases()

def exit_provider_cases():
 def allowing():return state()['enforcement']=='allowing'
 def blocked():return state()['enforcement']=='blocked'
 def exit_state(outcome):
  value=state()
  return value if value.get('exit_check',{}).get('outcome')==outcome else False
 def paths(after=0):return [path for _,path in COUNTS[after:]]
 def full_calls():return [entry for entry in PGHB_CALLS if entry[1]=='/f']
 def traffic():
  return subprocess.run(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py',
                         'probe','4','tcp'],stdout=subprocess.DEVNULL).returncode==0
 full_count=len(full_calls())
 before=len(COUNTS)
 apply({'exit_check':'1','expected_exit4':'203.0.113.7','public_hb_interval':'4'})
 wait(lambda:allowing() and exit_state('match'),40)
 check(set(paths(before))=={'/'} and state()['heartbeat']['successes']==2,
       'default exit source reuses official connectivity without IP-service or diagnostic calls')
 mode['public']='wrong_ip'
 first=wait(lambda:(lambda v:v if v and v['heartbeat'].get('failures')==1 else False)(exit_state('mismatch')),20)
 if first['enforcement']!='allowing':
  print('FIRST_MISMATCH',json.dumps({k:first.get(k) for k in ('phase','enforcement','heartbeat','fast_watch','exit_check','reason','firewall_error','next_probe','last_probe_ok','api','updated_uptime')}),flush=True)
  for gate in ('healthy_ifaces','heartbeat_ifaces','api_blocks'):
   print('FIRST_GATE',run('nft','list','set','inet','proxy_guard',gate,check=False).strip(),flush=True)
 check(first['enforcement']=='allowing','official wrong IP respects the consecutive-failure threshold')
 wait(blocked,20)
 check(not traffic(),'explicit wrong official exit blocks actual traffic')
 mode['public']='good'
 wait(lambda:allowing() and exit_state('match'),35)
 check(state()['heartbeat']['successes']==2 and traffic(),'official recovery requires consecutive valid checks')
 mode['public']='newline';wait(blocked,24)
 check(True,'official HTTPS rejects a trailing newline')
 mode['public']='good';wait(allowing,32)

 before=len(COUNTS)
 apply({'check_mode':'web','interval':'5','fail_threshold':'2','recover_threshold':'2'})
 wait(lambda:allowing() and state()['check_mode']=='web' and exit_state('match'),42)
 check({'/generate_204','/'}<=set(paths(before)) and not {'/f','/ip','/backup'}&set(paths(before)),
       'website checks can use the official endpoint only for optional IPv4')
 mode['web-one']='deny'
 wait(lambda:(lambda v:v['last_probe_ok'] and any(not p['ok'] for p in v['probes']))(state()),22)
 check(allowing() and traffic(),'one of two third-party website targets can fail without blocking')
 mode['web-two']='deny';wait(blocked,25)
 check(not traffic(),'consecutive third-party website failures block actual TCP')
 mode['web-one']='good';mode['web-two']='good';wait(allowing,30)
 check(state()['successes']==2 and traffic(),'third-party HTTPS restores after two successful rounds')

 apply({'exit_provider':'text','exit_url':'https://web-one.test/ip','exit_fallback_url':'https://web-one.test/backup','timeout':'2'})
 wait(lambda:allowing() and exit_state('match'),35)
 # Reconfiguration can overlap the last request of the previous policy.
 # Sample a complete, already active round rather than the commit window.
 before=len(COUNTS)
 wait(lambda:'/ip' in paths(before),22)
 check('/backup' not in paths(before) and '/' not in paths(before),
       'third-party exit source tries its primary before considering its backup')
 before=len(COUNTS);mode['primary_ip']='timeout'
 wait(lambda:(lambda v:v and v['exit_check'].get('via'))(exit_state('match')),22)
 check('/backup' in paths(before) and allowing(),'primary timeout uses the backup through SOCKS')
 mode['backup_ip']='timeout'
 both=wait(lambda:exit_state('timeout'),25)
 check(both['enforcement']=='allowing' and both['exit_check'].get('ok') is None and traffic(),
       'two IP timeouts alone do not block healthy website traffic')
 mode['primary_ip']='wrong_ip';before=len(COUNTS)
 wait(lambda:blocked() and exit_state('mismatch'),25)
 check('/backup' not in paths(before)[paths(before).index('/ip')+1:] and not traffic(),
       'explicit wrong IPv4 blocks without trying the backup')
 mode['primary_ip']='timeout'
 wait(lambda:exit_state('timeout'),25)
 check(blocked() and state()['exit_check']['mismatch_pending'] and not traffic(),
       'two timeouts cannot clear a confirmed IPv4 mismatch')
 mode['primary_ip']='good';mode['backup_ip']='good'
 wait(lambda:allowing() and exit_state('match'),30)
 check(not state()['exit_check']['mismatch_pending'] and traffic(),'matching IPv4 clears the mismatch and restores traffic')
 check(len(full_calls())==full_count and '/cdn-cgi/trace' not in paths(),
       'neither HTTPS mode nor IP fallback automatically requests /f or Trace')

 apply({'check_mode':'public','public_hb_interval':'2','exit_provider':'text'})
 wait(lambda:allowing() and state()['check_mode']=='public' and exit_state('match'),40)
 before=len(COUNTS)
 wait(lambda:{'/','/ip'}<=set(paths(before)),22)
 check('/generate_204' not in paths(before),
       'official HTTPS supports a separately selected third-party IP source')
 apply({'exit_check':'0','exit_provider':'public'})
 wait(lambda:allowing() and not state().get('exit_check',{}).get('enabled'),30)
def latest_changes(users,private_flow):
 admin=users['pgadmin']
 scope=('4','tcp','hblan','232')
 snapshot=Path('/var/run/proxy-guard/api-requests.json')
 config=Path('/etc/config/proxy_guard')
 def allowing():return state()['enforcement']=='allowing'
 def blocked():return state()['enforcement']=='blocked'
 def details():return call(wait(uuid_value,15),'status')
 def preview(draft,token=admin):
  return rpc(token,'proxy_guard','test_proxy',{'draft':json.dumps(draft)})
 def response(reply):
  assert reply.get('result',[1])[0]==0,reply
  return reply['result'][1]
 apply({'api_enabled':'1','api_max_seconds':'120','public_hb_interval':'4',
        'public_hb_fail':'2','public_hb_recover':'2','diagnostics_enabled':'0'})
 wait(allowing,40)
 one=wait(uuid_value,15)
 check(private_flow(*scope),'test client is online before diagnostics or preview')
 draft={'check_mode':'public','socks_port':'19080','passwall_watch':'0','client_auto_ports':'0',
        'public_hb_timeout':'2','exit_check':'1','expected_exit4':'203.0.113.7'}
 before=config.read_bytes()
 n_full=sum(path=='/f' for _,path in COUNTS)
 for sid in ['0'*32,users['pgreadonly'],users['pgdenied']]:
  check(is_error(preview(draft,sid)),'preview requires the LuCI write permission')
 value=response(preview(draft))
 check(value['ok'] and value['connectivity_ok'] and value['exit_check']['outcome']=='match',
       'authenticated preview uses real SOCKS, TLS and the expected IPv4')
 value=response(preview(dict(draft,socks_port='19081')))
 check(value['ok'] and not value['connectivity_ok'] and value['checks'][0]['curl_code']!=0,
       'preview uses the unsaved loopback SOCKS port')
 check(is_error(preview(dict(draft,socks_port='invalid'))),'preview validates draft settings')
 shared=dict(draft,check_mode='web',targets=['https://web-one.test/ip|200','https://web-two.test/generate_204|204'],min_success='2',
             timeout='3',exit_provider='text',exit_url='https://web-one.test/ip',
             exit_fallback_url='https://web-one.test/backup')
 mode['primary_ip']='timeout'
 value=response(preview(shared))
 mode['primary_ip']='good'
 check(value['ok'] and value['connectivity_ok'] and value['exit_check']['outcome']=='match' and
       value['checks'][0].get('via')=='web-one.test',
       'preview shares the same timeout fallback when the website is also the IP target')
 check(config.read_bytes()==before and allowing() and private_flow(*scope) and
       sum(path=='/f' for _,path in COUNTS)==n_full,
       'preview does not save, change enforcement, or request full diagnostics')

 def samples(stop,seen):
  while not stop.is_set():
   seen.append(private_flow(*scope))
   stop.wait(.25)
 stop=threading.Event();seen=[]
 worker=threading.Thread(target=samples,args=(stop,seen),daemon=True);worker.start()
 time.sleep(.5)
 try:apply({'diagnostics_enabled':'1','diagnostics_interval':'10','diagnostics_ttl':'30'})
 finally:stop.set();worker.join(timeout=5)
 check(len(seen)>=2 and all(seen) and allowing(),'saving diagnostic settings preserves live protected traffic')
 a=call(one,'request_block',{'seconds':25,'request_id':'diag-keeps-deadline'})
 check(a['ok'] and a['effective'] and blocked() and not private_flow(*scope),
       'authenticated timed request reaches the kernel')
 before_request=json.loads(snapshot.read_text())['items'][0]
 apply({'diagnostics_interval':'12','diagnostics_ttl':'35'})
 after=json.loads(snapshot.read_text())['items'][0]
 check(before_request['until_uptime']==after['until_uptime'] and blocked() and not private_flow(*scope),
       'diagnostic settings preserve the active block and its original deadline')
 wait(allowing,34)
 check(private_flow(*scope) and not call(one,'status')['api']['count'],'the same block expires automatically')

 mode['public']='deny'
 first=wait(lambda:(lambda s:s if s.get('failure_progress',{}).get('count')==1 else None)(state()),18)
 check(first['failure_progress']['threshold']==2 and first['enforcement']=='allowing',
       'first failed official sample is reported while the kernel still allows')
 wait(blocked,20)
 check('connectivity' in state()['block_reasons'] and not private_flow(*scope),
       'a second failed sample blocks actual traffic and reports connectivity')
 mode['public']='good';wait(allowing,30)

 now=time.time()
 fmt=lambda t:time.strftime('%H:%M:%S',time.gmtime(t))
 apply({'schedule_enabled':'1','schedule_start':fmt(now-180),'schedule_end':fmt(now+180),
        'schedule_repeat':'daily','schedule_utc_offset':'+00:00'})
 wait(lambda:'schedule' in state().get('block_reasons',[]),12)
 a=call(one,'request_block',{'seconds':30,'request_id':'schedule-and-api'})
 check(a['ok'] and {'schedule','api'}<=set(call(one,'status')['block_reasons']),
       'schedule and API blocks appear together in the live API')
 call(one,'cancel_block',{'request_id':'schedule-and-api'})
 check('api' not in state()['block_reasons'] and 'schedule' in state()['block_reasons'] and
       not private_flow(*scope),'withdrawing an API request leaves the schedule enforced')
 apply({'schedule_enabled':'0','exit_check':'1','expected_exit4':'203.0.113.7'})
 wait(allowing,45)
 for kind,reason in [('no_ip','missing_ip'),('invalid_ip','invalid_ip'),('ipv6_only','ipv6_only')]:
  mode['public']=kind
  sample=wait(lambda:(lambda s:s if s.get('exit_check',{}).get('reason')==reason else None)(details()),18)
  check(sample['exit_check']['outcome']=='unavailable','official response distinguishes '+reason)
  if kind=='invalid_ip':
   check('ip' not in sample['public_observation']['metadata'],'invalid IP stays out of authorized metadata')
  wait(blocked,18)
 mode['public']='good'
 wait(allowing,35)
 check(private_flow(*scope) and state()['exit_check']['outcome']=='match','matching IPv4 restores protected traffic')

def main():
 # Assert the native source fixture has registered the expected methods.
 check(Path('/www/cgi-bin/proxy-guard-api').is_file() and not Path('/usr/libexec/rpcd/proxy_guard_api').exists(),
       'package exposes the HTTPS API and has no separate rpcd API object')
 cfg=run('uci','export','proxy_guard');(ROOT/'original.uci').write_text(cfg)
 uci({'enabled':'0'})
 run('/etc/init.d/proxy-guard','stop')
 assert not any(i.get('table',{}).get('name')=='proxy_guard' for i in json.loads(run('nft','-j','list','tables'))['nftables']), 'disabled fixture still has an active guard table'
 # Disposable fixture baseline, local veth paths only.
 if Path('/etc/init.d/nikki').exists():run('/etc/init.d/nikki','stop')
 run('nft','flush','table','inet','fw4')
 run('python3','/tmp/heartbeat_network_fixture.py','setup')
 traffic_cases=[(fam,proto,ns,dest) for fam in ('4','6') for proto in ('tcp','udp')
                for ns,dest in (('hblan','232'),('hbwan','231'))]
 def private_flow(fam,proto,ns,dest):
  return subprocess.run(['ip','netns','exec',ns,'python3','/tmp/heartbeat_network_fixture.py','probe',fam,proto,dest]).returncode==0
 for case in traffic_cases:
  wait(lambda:private_flow(*case),7)
 check(True,'unprotected lab baseline carries IPv4/IPv6 TCP and UDP in both directions')
 shell("mkdir -p /tmp/hb-acceptance; openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/hb-acceptance/key.pem -out /tmp/hb-acceptance/cert.pem -days 3 -subj /CN=heartbeat.test -addext 'subjectAltName=DNS:heartbeat.test,DNS:web-one.test,DNS:web-two.test,DNS:hb.pghb.app' >/dev/null 2>&1")
 with open('/etc/ssl/certs/ca-certificates.crt','ab')as f:f.write((ROOT/'cert.pem').read_bytes())
 http=TLSServer(('127.0.0.1',19443),HTTP);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(ROOT/'cert.pem',ROOT/'key.pem')
 http.socket=ctx.wrap_socket(http.socket,server_side=True)
 socks=SOCKS(('127.0.0.1',19080),Socks)
 for srv in [http,socks]:threading.Thread(target=srv.serve_forever,daemon=True).start()
 probe=run('curl','-q','--silent','--show-error','--proxy','socks5h://127.0.0.1:19080','--noproxy','','--max-time','3','https://hb.pghb.app/')
 check(probe.encode()==PUBLIC_BODY,'real TLS/SOCKS fixture reachable before enabling protection')
 COUNTS.clear();PGHB_CALLS.clear()
 run('uci','-q','delete','proxy_guard.main',check=False)
 script="""set proxy_guard.main=proxy_guard
set proxy_guard.main.enabled='1'
set proxy_guard.main.mode='guard'
set proxy_guard.main.setup_complete='1'
set proxy_guard.main.interfaces='hb-in'
set proxy_guard.main.sources4='198.19.231.0/24'
set proxy_guard.main.sources6='2001:db8:231::/64'
set proxy_guard.main.local4='198.19.231.0/24'
set proxy_guard.main.local6='fd00::/64'
set proxy_guard.main.proxy_ports='19080'
add_list proxy_guard.main.targets='https://web-one.test/generate_204|204'
add_list proxy_guard.main.targets='https://web-two.test/generate_204|204'
set proxy_guard.main.passwall_watch='0'
set proxy_guard.main.client_auto_ports='0'
set proxy_guard.main.proxy_client='auto'
set proxy_guard.main.socks_port='19080'
set proxy_guard.main.startup_grace='0'
set proxy_guard.main.self_heal='0'
set proxy_guard.main.exit_check='0'
set proxy_guard.main.interval='5'
set proxy_guard.main.timeout='2'
set proxy_guard.main.fail_threshold='1'
set proxy_guard.main.recover_threshold='1'
set proxy_guard.main.check_mode='public'
set proxy_guard.main.public_hb_url='https://ignored.test/'
set proxy_guard.main.public_hb_interval='1'
set proxy_guard.main.public_hb_timeout='3'
set proxy_guard.main.public_hb_fail='1'
set proxy_guard.main.public_hb_recover='2'
set proxy_guard.main.api_enabled='0'
set proxy_guard.main.api_default_seconds='6'
set proxy_guard.main.api_max_seconds='30'
commit proxy_guard
"""
 subprocess.run(['uci','batch'],input=script,text=True,check=True)
 confirm_change()
 wait(lambda:state().get('enforcement')=='allowing',45)
 check(COUNTS and all(path=='/' for _,path in COUNTS),'official mode only sends basic HTTPS requests; a raw URL override is ignored')
 check(state().get('heartbeat',{}).get('allowed'),'exact official response through real TLS/SOCKS confirms the permit')
 if os.getenv('PG_TEST_NEW_ONLY'):
  users=accounts()
  latest_changes(users,private_flow)
  if os.getenv('PG_TEST_REPEAT_MODE'):
   mode_switches(wait(uuid_value,15),users['pgdenied'])
  return finish()
 if os.getenv('PG_TEST_EXIT_ONLY'):
  exit_provider_cases()
  return finish()
 if os.getenv('PG_TEST_MODE_ONLY'):
  users=accounts()
  apply({'api_enabled':'1'})
  mode_switches(wait(uuid_value,15),users['pgdenied'])
  return finish()
 if not os.getenv('PG_TEST_TAIL_ONLY'):
  for fam in ['4','6']:
   for proto in ['tcp','udp']:
    for ns,dest in [('hblan','232'),('hbwan','231')]:
     check(private_flow(fam,proto,ns,dest),'healthy bidirectional '+fam+' '+proto+' '+ns)
    Path('/tmp/hb-flow-'+fam+'-'+proto+'.jsonl').unlink(missing_ok=True)
    subprocess.Popen(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py','flow',fam,proto],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for bad in ([] if os.getenv('PG_TEST_RESUME_API') else ['deny','redirect','malformed','empty','timeout']):
   mode['public']=bad;wait(lambda:state().get('enforcement')=='blocked',15)
   check(state().get('heartbeat',{}).get('allowed') is False,'heartbeat rejects '+bad)
   mode['public']='good';wait(lambda:state().get('enforcement')=='allowing',20)
   check(state()['heartbeat']['successes']==2,'recovery threshold after '+bad)
  users=accounts()
  check(http_api(None)[0]==403,'API defaults off')
  check(not API_UUID.exists(),'API off has no UUID')
  apply({'api_enabled':'1'})
  wait(lambda:state().get('enforcement')=='allowing')
  one=reader=wait(uuid_value,15)
  check(API_UUID.stat().st_mode&0o777==0o600,'UUID is private to the router administrator')
  code, value=http_api(one)
  check(code==200 and value.get('ok') and value['uuid']==one,'valid UUID returns status and UUID')
  code, value=http_api(None,headers={'Cookie':'sysauth_https='+users['pgadmin']})
  check(code==401 and 'uuid' not in value,'LuCI session cookie alone cannot call the API')
  check(http_api(users['pgadmin'])[0]==401,'router session is not an API credential')
  admin=rpc(users['pgadmin'],'proxy_guard','api_credentials')
  check(admin['result'][1]['uuid']==one,'LuCI administrator can copy the applied UUID')
  check(is_error(rpc(users['pgreadonly'],'proxy_guard','api_credentials')),'read-only LuCI role cannot retrieve UUID')
  admin_log=rpc(users['pgadmin'],'proxy_guard','logs')['result'][1]
  public_log=rpc(users['pgreadonly'],'proxy_guard','logs')['result'][1]
  check(any(row.get('api_uuid')==one for row in admin_log['entries']) and one not in json.dumps(public_log),
        'only administrators see the full UUID in the event log')
  check(call(one,'request_block',{'seconds':31}).get('error')=='invalid_duration','excess duration rejected')
  check(call(one,'request_block',{'seconds':-1}).get('error')=='invalid_duration','negative duration rejected')
  check(http_api(one,'block')[0]==405,'GET cannot create a block')
  check(http_api(one,'block',{'seconds':5},headers={'Content-Type':'text/plain'})[0]==415,'mutation requires a JSON body')
  lock=subprocess.Popen(['ucode','-e',"import {open} from 'fs';let h=open('/var/lock/proxy-guard-api.lock','a');h.lock('x');sleep(5000);"])
  time.sleep(.5)
  rejected=http_api(one,'block',{'seconds':5,'request_id':'blocked-by-lock'})
  check(rejected[0]==503 and rejected[1].get('error')=='busy','busy API lock returns an explicit rejection')
  check(state()['enforcement']=='allowing','ordinary API lock contention does not create a proxy fault')
  lock.wait(timeout=10)
  a=call(one,'request_block',{'seconds':30,'request_id':'owned-request-one'})
  check(a['ok'] and a['effective'] and state()['enforcement']=='blocked','API blocks immediately with an effective kernel verdict')
  for fam in ['4','6']:
   for proto in ['tcp','udp']:
    p=subprocess.run(['ip','netns','exec','hblan','python3','/tmp/heartbeat_network_fixture.py','probe',fam,proto])
    check(p.returncode!=0,'API blocks actual '+fam+' '+proto+' traffic')
    rows=[json.loads(x)for x in Path('/tmp/hb-flow-'+fam+'-'+proto+'.jsonl').read_text().splitlines()]
    check(any(not x['ok'] for x in rows[-4:]),'API blocks established '+fam+' '+proto+' flow')
  b=call(one,'request_block',{'seconds':30,'request_id':'owned-request-one'})
  check(b['ok'] and call(one,'status')['api']['count']==1,'idempotent retry does not duplicate or extend')
  check(call(one,'request_block',{'seconds':29,'request_id':'owned-request-one'}).get('error')=='request_conflict',
        'conflicting retry rejected')
  check(http_api(None,'cancel',{'request_id':'owned-request-one'})[0]==401 and state()['enforcement']=='blocked',
        'unauthenticated cancellation cannot remove a block')
  b=call(one,'request_block',{'seconds':20})
  call(one,'cancel_block',{'request_id':'owned-request-one'})
  check(state()['enforcement']=='blocked','overlapping request keeps block active')
  call(one,'cancel_block',{'request_id':b['request_id']})
  wait(lambda:state()['enforcement']=='allowing')
  check(True,'last withdrawal restores only when ordinary gates allow')
  call(one,'request_block',{'seconds':2});wait(lambda:state()['enforcement']=='allowing',10)
  check(True,'bounded request expires automatically')
  mode['public']='deny';wait(lambda:state()['enforcement']=='blocked',15)
  a=call(one,'request_block',{'seconds':8})
  call(one,'cancel_block',{'request_id':a['request_id']})
  check(state()['enforcement']=='blocked','API cancellation never overrides an official HTTPS fault')
  apply({'api_enabled':'0'})
  check(http_api(one)[0]==403 and not API_UUID.exists(),'UI API disable revokes the UUID immediately')
  apply({'api_enabled':'1'})
  reader=wait(uuid_value,15)
  check(reader!=one and http_api(one)[0]==401 and http_api(reader)[0]==200,
        're-enabling rotates the UUID and rejects the previous UUID')
  check(state()['enforcement']=='blocked','API disable preserves other blocking gates')
  mode['public']='good';wait(lambda:state()['enforcement']=='allowing')
 if not os.getenv('PG_TEST_TAIL_ONLY'):
  mode_switches(reader,users['pgdenied'])
 if os.getenv('PG_TEST_UUID_ONLY'):return finish()
 fast_heartbeat_boundary()
 # Dead detector cannot retain an infinite authorization.
 pid=Path('/var/run/proxy-guard/heartbeat_watch.pid').read_text().strip()
 run('kill','-STOP',pid)
 wait(lambda:state()['enforcement']=='blocked',15)
 check(True,'heartbeat permit expires when its monitor stalls')
 run('kill','-CONT',pid);wait(lambda:state()['enforcement']=='allowing',25)
 run('/etc/init.d/proxy-guard','stop')
 check(state()['enforcement']=='blocked','explicit stop keeps scoped protection closed')
 time.sleep(.2)
 leftovers=[]
 for f in Path('/proc').glob('[0-9]*/cmdline'):
  try:
   args=f.read_bytes().split(b'\0')
   if len(args)>2 and args[1] in [b'/usr/lib/proxy-guard/extension-lock.uc',b'/usr/lib/proxy-guard/extension-main.lua'] and args[2] in [b'heartbeat',b'heartbeat_gate',b'api_sync']:leftovers.append(f.parent.name)
  except OSError:pass
 check(not leftovers,'stop leaves no heartbeat workers or inherited locks behind')
 finish()
def finish():
 (ROOT/'results.json').write_text(json.dumps({'ok':True,'checks':RESULT,'requests':len(COUNTS)},indent=2))
 print(json.dumps({'ok':True,'count':len(RESULT),'requests':len(COUNTS)}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as e:
  (ROOT/'results.json').write_text(json.dumps({'ok':False,'checks':RESULT,'error':repr(e),'requests':len(COUNTS)},indent=2))
  try:print('STATE',json.dumps(state()),flush=True)
  except Exception as detail:print('STATE_UNAVAILABLE',repr(detail),flush=True)
  print(run('logread'),flush=True)
  raise
 finally:
  run('python3','/tmp/heartbeat_network_fixture.py','cleanup',check=False)
