import json,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native016-pending.json'
h.cmd("""cp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard
uci set proxy_guard.main.enabled=1
uci set proxy_guard.main.mode=guard
uci set proxy_guard.main.passwall_watch=0
uci set proxy_guard.main.boot_guard=0
uci set proxy_guard.main.self_heal=0
uci set proxy_guard.main.udp_check=0
uci set proxy_guard.main.schedule_enabled=0
uci set proxy_guard.main.startup_grace=0
uci -q delete proxy_guard.main.interfaces
uci add_list proxy_guard.main.interfaces=pg-missing0
uci commit proxy_guard
/etc/init.d/proxy-guard start""")
s=h.wait_for(lambda s:s.get('interface_waiting') is True,35)
assert s['phase']=='waiting_interface' and s['enforcement']=='unverified' and s.get('blocked') is None,s
h.record('missing ingress preloads rules but does not claim verified traffic coverage',status=s,traffic=h.traffic(False))
pid=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
h.cmd('kill -STOP '+pid)
try:
 h.cmd('nft add rule inet proxy_guard decision counter')
 s=h.state();assert s['enforcement']=='unverified' and not s.get('interface_waiting'),s
 h.record('damaged preloaded rules are not hidden by the normal waiting state',status=s)
finally:h.cmd('kill -CONT '+pid)
h.wait_for(lambda s:s.get('interface_waiting') is True,30)
h.cmd('uci -q delete proxy_guard.main.interfaces\nuci add_list proxy_guard.main.interfaces=br-lan\nuci commit proxy_guard\n/etc/init.d/proxy-guard reload')
h.wait_for(lambda s:s['enforcement']=='allowing',60)
pid=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
h.cmd('kill -STOP '+pid)
try:
 before=h.state()['updated_uptime']
 h.cmd('ifdown lan',40)
 s=h.wait_for(lambda s:s.get('interface_waiting') is True and s['updated_uptime']>before,30)
 h.record('actual netifd ifdown without DEVICE synchronizes preloaded policy',status=s)
 before=s['updated_uptime']
 h.cmd('ifup lan',40)
 s=h.wait_for(lambda s:s['firewall_present'] and s['updated_uptime']>before and not s.get('interface_waiting'),30)
 assert h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()==pid
 h.record('actual netifd down/up synchronizes status without restarting the detector',status=s)
finally:h.cmd('kill -CONT '+pid)
h.wait_for(lambda s:s['enforcement']=='allowing',60)
h.cmd('uci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nsha256sum -c /opt/pgvm/system-config.sha256')
h.record('interface recovery verifies fresh checks and retains system configuration',status=h.state(),traffic=h.traffic(False))
print('ALL PENDING POLICY AND REAL NETIFD CASES PASSED',flush=True)
