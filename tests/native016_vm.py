"""Native fw4, netifd and trace acceptance in the disconnected OpenWrt lab."""
import json,shlex,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native016-integration.json'
def wait(fn,timeout=50):
 return h.wait_for(fn,timeout)
def record(name,**kw):h.record(name,**kw)
def set_mode(value):
 return int(float(h.cmd('printf %s '+shlex.quote(value)+' >/tmp/pg-native-trace-mode\ncut -d \' \' -f 1 /proc/uptime').strip()))+1
def pid():return h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
trace=r"""#!/bin/sh
n=$(cat /tmp/pg-native-trace-count 2>/dev/null)
n=$((n+1))
printf '%s' "$n" >/tmp/pg-native-trace-count
mode=$(cat /tmp/pg-native-trace-mode 2>/dev/null)
printf 'Status: 200 OK\r\nContent-Type: text/plain\r\n\r\n'
case "$mode" in
 html) printf '<html>not trace</html>' ;;
 wrong) printf 'ip=203.0.113.99\ncolo=NRT\n' ;;
 duplicate) printf 'ip=203.0.113.7\nip=203.0.113.99\ncolo=NRT\n' ;;
 ipv6) printf 'ip=2001:db8::7\ncolo=NRT\n' ;;
 huge) head -c 5000 /dev/zero ;;
 sjc) printf 'ip=203.0.113.7\ncolo=SJC\n' ;;
 *) printf 'ip=203.0.113.7\ncolo=NRT\n' ;;
esac
"""
h.put('/tmp/pg-native-trace.cgi',trace.encode())
h.put('/tmp/pg-native-health.cgi', b"#!/bin/sh\nprintf 'Status: 204 No Content\\r\\n\\r\\n'\n")
h.cmd("""mkdir -p /opt/pgvm/www/cdn-cgi
cp /tmp/pg-native-trace.cgi /opt/pgvm/www/cdn-cgi/trace
cp /tmp/pg-native-health.cgi /opt/pgvm/www/cdn-cgi/health
chmod 755 /opt/pgvm/www/cdn-cgi/trace /opt/pgvm/www/cdn-cgi/health
if ! test -f /opt/pgvm/native016-fixture.original; then cp /etc/init.d/pgvm-fixture /opt/pgvm/native016-fixture.original; fi
sed 's#-x /cgi-bin#-x /cdn-cgi#' /opt/pgvm/native016-fixture.original > /etc/init.d/pgvm-fixture
/etc/init.d/pgvm-fixture restart
cp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard
uci set proxy_guard.main.enabled=1
uci set proxy_guard.main.mode=guard
uci set proxy_guard.main.startup_grace=0
uci set proxy_guard.main.schedule_enabled=0
uci set proxy_guard.main.passwall_watch=0
uci set proxy_guard.main.boot_guard=0
uci set proxy_guard.main.self_heal=0
uci set proxy_guard.main.udp_check=0
uci set proxy_guard.main.interval=300
uci set proxy_guard.main.timeout=2
uci set proxy_guard.main.fail_threshold=1
uci set proxy_guard.main.recover_threshold=1
uci set proxy_guard.main.expected_exit4=203.0.113.7
uci set proxy_guard.main.exit_url=https://fixture.test/cdn-cgi/trace
uci -q delete proxy_guard.main.targets
uci add_list proxy_guard.main.targets='https://fixture.test/cdn-cgi/health|204'
uci add_list proxy_guard.main.targets='https://fixture.test/cdn-cgi/trace|200'
printf good >/tmp/pg-native-trace-mode
printf 0 >/tmp/pg-native-trace-count
uci commit proxy_guard
/etc/init.d/proxy-guard start""",60)
s=wait(lambda s:s.get('enforcement')=='allowing' and s.get('exit_check',{}).get('colo')=='NRT')
count=int(h.cmd('cat /tmp/pg-native-trace-count'))
assert count==1,(count,s)
record('real SOCKS HTTPS trace shares one request for target and exit validation',status=s,count=count,traffic=h.traffic(False))
oldpid=pid();stamp=s.get('started_at')
for i in range(6):
 h.cmd('fw4 check >/tmp/pg-native-fw4-check.log 2>&1\nfw4 reload >/tmp/pg-native-fw4-reload.log 2>&1',45)
 s=h.state();assert s['enforcement']=='allowing' and s['phase']=='healthy' and pid()==oldpid,s
record('six real firewall4 reloads preserve the permit and do not restart protection',status=s,traffic=h.traffic(False))
h.cmd('uci set proxy_guard.main.interval=5\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply')
wait(lambda s:s.get('enforcement')=='allowing')
set_mode('sjc')
s=wait(lambda s:s.get('exit_check',{}).get('colo')=='SJC')
assert s['enforcement']=='allowing',s
record('Cloudflare data-center changes do not cause blocking',status=s)
for mode in ['html','wrong','duplicate','ipv6','huge']:
 boundary=set_mode(mode)
 s=wait(lambda s:s['enforcement']=='blocked' and s.get('last_probe_ok') is False and s.get('probe_started',0)>=boundary,40)
 if mode=='ipv6':assert s['exit_check']['observed']=='2001:db8::7',s
 record('invalid trace '+mode+' is rejected even with HTTP 200',status=s,traffic=h.traffic(True))
 boundary=set_mode('good')
 wait(lambda s:s['enforcement']=='allowing' and s.get('last_probe_ok') is True and s.get('probe_started',0)>=boundary,40)
record('valid trace restores access after all malformed response cases',traffic=h.traffic(False))
# Unrelated events must not create updates; matching events reconcile with the
# daemon paused, proving the netifd hook itself performs the synchronization.
oldpid=pid();h.cmd('kill -STOP '+oldpid);time.sleep(.5)
try:
 baseline=h.state()['updated_uptime']
 h.cmd("ACTION=ifupdate DEVICE=unrelated0 /sbin/hotplug-call iface")
 assert h.state()['updated_uptime']==baseline
 time.sleep(1.1)
 h.cmd("ACTION=ifupdate DEVICE=br-lan /sbin/hotplug-call iface")
 s=h.state();assert s['updated_uptime']>baseline and s['enforcement']=='allowing',s
 assert pid()==oldpid
 record('real hotplug-call ignores unrelated interfaces and updates the configured ingress without restart',status=s)
finally:h.cmd('kill -CONT '+oldpid)
wait(lambda s:s['enforcement']=='allowing')
# Repeated reloads are not a source of new permission. A shortened real kernel
# timeout must still expire while the worker is suspended.
oldpid=pid();h.cmd('kill -STOP '+oldpid);time.sleep(.5)
try:
 h.cmd('nft flush set inet proxy_guard healthy_ifaces\nnft \'add element inet proxy_guard healthy_ifaces { "br-lan" timeout 4s }\'')
 began=time.monotonic()
 for i in range(3):h.cmd('fw4 reload >/tmp/pg-native-expiry-reload.log 2>&1',45)
 while time.monotonic()-began<5:time.sleep(.1)
 s=h.state();assert s['enforcement']=='blocked',s
 record('firewall4 reload cannot renew an expired kernel permit',status=s,traffic=h.traffic(True))
finally:h.cmd('kill -CONT '+oldpid)
wait(lambda s:s['enforcement']=='allowing')
h.cmd('/etc/init.d/proxy-guard stop')
h.cmd('fw4 reload >/tmp/pg-native-stopped-reload.log 2>&1')
s=h.state();assert s['enforcement']=='blocked',s
record('stopped plugin stays blocked through firewall4 reload',status=s,traffic=h.traffic(True))
h.cmd('nft delete table inet proxy_guard\nfw4 reload >/tmp/pg-native-rebuild.log 2>&1')
# Deliberate external deletion has a known gap before reload. This check starts
# after fw4's transaction has completed; it does not claim that gap is protected.
h.cmd('test -f /etc/proxy-guard/fw4-guard.nft\nnft list table inet proxy_guard >/tmp/pg-native-restored.nft\nACTION=ifup DEVICE=br-lan /sbin/hotplug-call iface')
svc=h.decode(h.cmd('ubus call service list '+shlex.quote(json.dumps({'name':'proxy-guard'}))))
assert not svc.get('proxy-guard',{}).get('instances'),svc
record('firewall4 reconstructs the default-block policy without a running plugin; hotplug honors explicit stop',traffic=h.traffic(True),service=svc)
h.cmd('/etc/init.d/proxy-guard start')
wait(lambda s:s['enforcement']=='allowing')
# Current legacy plain-IP services continue to work when explicitly configured.
h.cmd("uci set proxy_guard.main.exit_url=https://fixture.test/exit.txt\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply")
wait(lambda s:s['enforcement']=='allowing' and s.get('exit_check',{}).get('ok'))
record('custom plain-IP exit services remain compatible',traffic=h.traffic(False))
h.cmd('uci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nfw4 reload >/tmp/pg-native-disabled-reload.log 2>&1\ntest ! -f /etc/proxy-guard/fw4-guard.nft\n! nft list table inet proxy_guard >/dev/null 2>&1\nsha256sum -c /opt/pgvm/system-config.sha256')
record('explicit off removes the persistent policy and fw4 cannot recreate it',status=h.state(),traffic=h.traffic(False))
h.cmd('cp /opt/pgvm/native016-fixture.original /etc/init.d/pgvm-fixture\n/etc/init.d/pgvm-fixture restart')
print('ALL NATIVE 0.1.16 TRACE / FW4 / NETIFD CASES PASSED',flush=True)
