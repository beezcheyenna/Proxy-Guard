"""Real 3x-ui login versus selected ports; only offline nested net/mount/PID namespaces."""
from pathlib import Path
import atexit,os,sys,json,subprocess,tempfile,shutil,sqlite3,secrets,time,threading,http.server,urllib.request
assert sys.platform=='linux' and os.geteuid()==0 and Path('/etc/pgvm-fixture').is_file()
assert os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net') or os.getpid()==1
# The runner must create private mount+network+PID namespaces and mount /proc.
assert os.getpid()==1
S=Path(os.environ['PG_SOURCE']);sys.path.insert(0,str(S/'companion/vps'));import agent
T=tempfile.TemporaryDirectory(prefix='pg-panel-');W=Path(T.name);checks=[]
def run(*args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=90,**kw)
def good(v,label):
 assert v,label
 checks.append(label);print('PASS '+label,flush=True)
run('mount','--make-rprivate','/');run('ip','link','set','lo','up')
# Private database and installation tree: no changes to the existing panel service.
X=W/'x-ui';shutil.copytree('/usr/local/x-ui',X)
D=W/'db';D.mkdir();src=sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True);dst=sqlite3.connect(D/'x-ui.db');src.backup(dst);dst.execute("UPDATE inbounds SET enable=0");dst.commit();dst.close();src.close()
run('mount','--bind',str(X),'/usr/local/x-ui');run('mount','--bind',str(D),'/etc/x-ui')
user='lab_'+secrets.token_hex(4);password=secrets.token_urlsafe(24)
run('/usr/local/x-ui/x-ui','setting','-username',user,'-password',password,'-port','28080','-listenIP','0.0.0.0','-webBasePath','/pgtest/',cwd='/usr/local/x-ui')
panel_log=(W/'panel.log').open('w');panel=subprocess.Popen(['/usr/local/x-ui/x-ui'],cwd='/usr/local/x-ui',stdout=panel_log,stderr=subprocess.STDOUT)
atexit.register(panel.terminate)
for _ in range(90):
 try:
  urllib.request.urlopen('http://127.0.0.1:28080/pgtest/',timeout=1).read();break
 except OSError:time.sleep(.2)
else:raise RuntimeError('private real 3x-ui did not start: '+(W/'panel.log').read_text()[-900:])
# Two external sources, no internet route.
names=[]
for i,source in enumerate(['8.8.8.8','9.9.9.9'],1):
 name='pgpanel_'+str(i);names.append(name)
 run('ip','netns','add',name);run('ip','link','add','panelh'+str(i),'type','veth','peer','name','panelc'+str(i));run('ip','link','set','panelc'+str(i),'netns',name)
 run('ip','addr','add','10.78.'+str(i)+'.1/24','dev','panelh'+str(i));run('ip','link','set','panelh'+str(i),'up')
 run('ip','-n',name,'link','set','lo','up');run('ip','-n',name,'addr','add',source+'/32','dev','panelc'+str(i));run('ip','-n',name,'link','set','panelc'+str(i),'up');run('ip','-n',name,'route','add','10.78.'+str(i)+'.1/32','dev','panelc'+str(i));run('ip','route','add',source+'/32','dev','panelh'+str(i))
atexit.register(lambda:[subprocess.run(['ip','netns','delete',name],capture_output=True)for name in names])
# A genuine HTTP reverse proxy to the same panel, representing a shared proxy/panel front port.
class Front(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  try:
   with urllib.request.urlopen('http://127.0.0.1:28080'+self.path,timeout=3) as r:body=r.read();self.send_response(r.status);self.send_header('Content-Type',r.headers.get('Content-Type','text/html'));self.end_headers();self.wfile.write(body)
  except OSError:self.send_error(502)
 def log_message(self,*args):pass
front=http.server.ThreadingHTTPServer(('0.0.0.0',24443),Front);threading.Thread(target=front.serve_forever,daemon=True).start();atexit.register(front.server_close)
probe="""import urllib.request,urllib.parse,http.cookiejar,json,sys
base,user,password,login=sys.argv[1:];jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
try:
 if login=='1':
  token=json.load(client.open(base+'/csrf-token',timeout=8)).get('obj')
  data=urllib.parse.urlencode({'username':user,'password':password}).encode()
  req=urllib.request.Request(base+'/login',data,headers={'X-CSRF-Token':token,'Referer':base+'/panel/','Origin':base.rsplit('/pgtest',1)[0]})
  print('ok' if json.load(client.open(req,timeout=8)).get('success') else 'failed')
 else:
  r=client.open(base+'/',timeout=8);print('ok' if r.status==200 and len(r.read())>100 else 'failed')
except OSError as e:print('blocked:'+type(e).__name__+':'+str(e))
"""
def access(which,port,login=False):
 result=run('ip','netns','exec',names[which-1],'python3','-c',probe,'http://10.78.'+str(which)+'.1:'+str(port)+'/pgtest',user,password,str(int(login))).stdout.strip()
 print('PANEL_PROBE',which,port,'login'if login else'http',result,flush=True)
 return result=='ok'
driver=agent.Nft()
def policy(ports,mode='whitelist',source='dynamic'):
 p=agent.normalize_policy(True,[dict(id='selected',name='Fixture',enabled=True,protocol='tcp',ports=ports,source_mode=source,sources=[])],mode=mode)
 driver.apply(p,{4:('8.8.8.8',time.monotonic()+600)});return p
atexit.register(driver.cleanup)
good(access(1,28080,True) and access(2,28080,True),'real 3x-ui authentication baseline from both external sources')
policy(['24443'])
good(access(1,24443) and not access(2,24443),'shared front port obeys selected whitelist')
good(access(1,28080,True) and access(2,28080,True),'independent unselected 3x-ui panel login remains reachable')
policy(['24443','28080'])
good(access(1,28080,True) and not access(2,28080),'explicitly selecting panel port filters panel login')
policy(['24443','28080'],mode='observe')
observed_panel=access(2,28080,True);observed_front=access(2,24443)
good(observed_panel and observed_front,'observe mode does not filter panel or shared front port')
policy(['24443','28080'],source='any')
good(access(2,28080,True) and access(2,24443),'explicit unrestricted source keeps selected panel reachable')
print(json.dumps({'checks':checks,'real_panel':'3x-ui','production_changed':False}),flush=True)
