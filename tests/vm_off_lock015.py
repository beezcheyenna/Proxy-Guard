from pathlib import Path
import sys,json,time,shlex
r=Path(sys.argv[1]).resolve();sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(r/'candidate-tests'))
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=r/'logs/off-hang-final015-results.json'
def wait(fn,timeout=80):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  s=h.state()
  if fn(s):return s
  time.sleep(.5)
 raise AssertionError(s)
def login():
 return h.decode(h.cmd('ubus call session login '+shlex.quote(json.dumps({'username':'root','password':'proxy-guard-fixture','timeout':3600}))))['ubus_rpc_session']
h.cmd('sleep 600 </dev/null >/tmp/pg015-unrelated.log 2>&1 &\necho $! >/tmp/pg015-unrelated.pid')
other=h.cmd('cat /tmp/pg015-unrelated.pid').strip()
for action in ['http_apply','reload','stop','uninstall']:
 h.cmd('cp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard\n'
  'uci set proxy_guard.main.enabled=1\nuci set proxy_guard.main.mode=guard\n'
  'uci set proxy_guard.main.startup_grace=0\nuci set proxy_guard.main.schedule_enabled=0\n'
  'uci set proxy_guard.main.passwall_watch=0\nuci set proxy_guard.main.boot_guard=0\n'
  'uci set proxy_guard.main.self_heal=1\nuci set proxy_guard.main.udp_check=0\n'
  'uci set proxy_guard.main.timeout=4\nuci set proxy_guard.main.interval=5\nuci commit proxy_guard')
 sid=login();assert h.rpc(sid,'proxy_guard','apply',{})['ok']
 wait(lambda s:s['enforcement']=='allowing')
 h.traffic(False)
 h.cmd((h.root/'tests/orphan_fixture.sh').read_text())
 orphan=h.cmd('cat /tmp/pg014-orphan.pid').strip()
 daemon=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
 h.cmd('kill -CONT '+daemon)
 began=time.monotonic()
 if action=='http_apply':
  h.rpc(sid,'uci','set',{'config':'proxy_guard','section':'main','values':{'enabled':'0','schedule_start':'invalid'}})
  assert h.rpc(sid,'proxy_guard','apply',{})['ok']
 elif action=='reload':
  h.cmd('uci set proxy_guard.main.enabled=0\nuci set proxy_guard.main.schedule_start=invalid\nuci commit proxy_guard\n/etc/init.d/proxy-guard reload',15)
 elif action=='stop':
  h.cmd('/etc/init.d/proxy-guard stop',15)
 else:
  h.cmd('opkg remove luci-app-proxy-guard\ntest ! -e /usr/libexec/proxy-guard\n! nft list table inet proxy_guard >/dev/null 2>&1\n! ubus list proxy_guard | grep -qx proxy_guard',20)
 if action!='uninstall':
  s=wait(lambda s:s['enforcement']==('blocked' if action=='stop' else 'off'),15)
  assert s.get('firewall_present')==(action=='stop'),s
 else:s={'uninstalled':True}
 elapsed=time.monotonic()-began;assert elapsed<20,elapsed
 h.cmd('test ! -d /proc/'+orphan+'\nkill -0 '+other)
 h.record(action+' completes with a real orphaned Lua lock owner; unrelated process survives',seconds=round(elapsed,3),status=s,traffic=h.traffic(action=='stop'))
 time.sleep(6)
 h.cmd('kill -0 '+other)
 if action=='uninstall':
  src=(r/'vm/source014-mount').read_text()
  h.cmd('opkg install '+src+'/final015-private.ipk',90)
  wait(lambda s:s['enforcement']=='allowing')
  assert h.rpc(sid,'proxy_guard','status',{})['version']=='0.1.15'
  h.record('reinstall after hung-worker removal preserves enabled config and old HTTP session')
 elif action=='stop':
  service=h.decode(h.cmd('ubus call service list '+shlex.quote(json.dumps({'name':'proxy-guard'}))))
  assert not service.get('proxy-guard',{}).get('instances'),service
  h.record('explicit stop remains blocked with no running service instances')
 else:
  assert h.state()['enforcement']=='off'
  h.record('procd respawn after '+action+' honors off without recreating rules')
 h.cmd('ubus call session destroy '+shlex.quote(json.dumps({'ubus_rpc_session':sid})))
h.cmd('kill '+other+'\ncp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard\n'
 'uci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nsha256sum -c /opt/pgvm/system-config.sha256')
print('ALL FINAL OFF / RELOAD / STOP / UNINSTALL LOCK REGRESSIONS PASSED',flush=True)
