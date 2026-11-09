from pathlib import Path
from datetime import datetime,timezone
import sys,json,time,shlex
r=Path(sys.argv[1]).resolve();sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(r/'candidate-tests'))
import vm_boot_guard as h
h.results=[];h.result_file=r/'logs/final-upgrade-stress.json';h.tag()
def wait(fn,timeout=90):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  s=h.state()
  if fn(s):return s
  time.sleep(.5)
 raise AssertionError(s)
def login(user='root'):
 return h.decode(h.cmd('ubus call session login '+shlex.quote(json.dumps({'username':user,'password':'proxy-guard-fixture' if user=='root' else 'proxy-guard-audit','timeout':3600}))))['ubus_rpc_session']
def old_guard():
 h.cmd('uci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\n'
  'opkg install --force-downgrade /opt/pgvm/audit013-private.ipk',120)
 wall=int(h.cmd('date +%s').strip())
 clock=lambda t:datetime.fromtimestamp(t,timezone.utc).strftime('%H:%M:%S')
 h.cmd('cp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard\n'
  'uci set proxy_guard.main.enabled=1\nuci set proxy_guard.main.mode=guard\n'
  'uci set proxy_guard.main.passwall_watch=0\nuci set proxy_guard.main.boot_guard=0\n'
  'uci set proxy_guard.main.udp_check=0\nuci set proxy_guard.main.schedule_enabled=1\n'
  'uci set proxy_guard.main.schedule_repeat=daily\nuci set proxy_guard.main.schedule_utc_offset=+00:00\n'
  'uci set proxy_guard.main.schedule_start='+clock(wall-60)+'\nuci set proxy_guard.main.schedule_end='+clock(wall+1200)+'\n'
  'uci set proxy_guard.main.fast_wait_seconds=23\nuci commit proxy_guard')
 sid=login();viewer=login('audit_viewer');assert h.rpc(sid,'proxy_guard','apply',{})['ok']
 wait(lambda s:s['enforcement']=='blocked');h.traffic(True)
 return sid,viewer
def upgrade(sid,viewer,case):
 conf=h.cmd('sha256sum /etc/config/proxy_guard').split()[0]
 before=h.b.counts(h.tag())['received']
 out=h.cmd('opkg install /opt/pgvm/final015-private.ipk',120)
 s=h.rpc(sid,'proxy_guard','status',{})
 assert s['version']=='0.1.15' and s['enforcement']=='blocked',s
 assert h.cmd('sha256sum /etc/config/proxy_guard').split()[0]==conf
 assert h.cmd('uci get proxy_guard.main.fast_wait_seconds').strip()=='23'
 assert h.rpc(viewer,'proxy_guard','status',{})['enforcement']=='blocked'
 h.traffic(True)
 after=h.b.counts(h.tag())['received'];delta={k:after.get(k,0)-before.get(k,0) for k in h.external}
 assert not any(delta.values()),delta
 h.record(case,external_packets=delta,config_preserved=True,old_sessions_retained=True,output=out)
for i in range(1,4):
 sid,viewer=old_guard();upgrade(sid,viewer,'repeat '+str(i)+' active 0.1.13 upgrade keeps all eight external flows blocked')
sid,viewer=old_guard()
h.cmd('/etc/init.d/proxy-guard stop\n'
 'ucode -e '+shlex.quote('import {open} from "fs";let f=open("/var/lock/proxy-guard.lock","a");let deadline=clock(true)[0]+15;while(!f.lock("xn")){assert(clock(true)[0]<deadline);sleep(100);}f.close();')+
 '\nrm /var/lock/proxy-guard.lock\nmkdir /var/lock/proxy-guard.lock')
before=h.cmd('sha256sum /etc/config/proxy_guard /usr/lib/proxy-guard/core.lua')
rc,out=h.vmctl.cmd('test -f /etc/pgvm-fixture || exit 1\nopkg install /opt/pgvm/final015-private.ipk',120)
assert rc!=0 and 'preinst script returned status 1' in out,out
assert h.cmd('sha256sum /etc/config/proxy_guard /usr/lib/proxy-guard/core.lua')==before
assert h.state()['version']=='0.1.13'
h.record('corrupt operation lock aborts before replacing old code/config and preserves blocking',output=out,traffic=h.traffic(True))
h.cmd('rmdir /var/lock/proxy-guard.lock')
upgrade(sid,viewer,'retry after restoring the deliberately corrupt lock completes through normal install hooks')
h.cmd('uci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nsha256sum -c /opt/pgvm/system-config.sha256')
h.record('upgrade stress leaves router configuration unchanged and disables fixture protection')
print('ALL REPEATED ACTIVE UPGRADES AND PREINST FAILURE CONTRACTS PASSED',flush=True)
