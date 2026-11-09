"""Actual offline VM regression: interface applies cannot mask a stalled detector."""
import json,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native016-heartbeat.json'
h.cmd("""cp /opt/pgvm/boot019-before-fresh.conf /etc/config/proxy_guard
uci set proxy_guard.main.enabled=1
uci set proxy_guard.main.mode=guard
uci set proxy_guard.main.schedule_enabled=0
uci set proxy_guard.main.passwall_watch=0
uci set proxy_guard.main.boot_guard=0
uci set proxy_guard.main.startup_grace=0
uci set proxy_guard.main.interval=5
uci set proxy_guard.main.timeout=2
uci set proxy_guard.main.self_heal=1
uci set proxy_guard.main.self_heal_stale=15
uci set proxy_guard.main.self_heal_cooldown=30
uci set proxy_guard.main.self_heal_limit=2
uci set proxy_guard.main.self_heal_window=600
uci commit proxy_guard
/etc/init.d/proxy-guard start""")
h.wait_for(lambda s:s['enforcement']=='allowing',45)
pid=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
h.cmd('kill -STOP '+pid)
samples=[]
try:
 for i in range(12):
  h.cmd('ACTION=ifupdate DEVICE=br-lan /sbin/hotplug-call iface')
  s=h.state();current=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
  samples.append({'seconds':i*5,'pid':current,'phase':s.get('phase'),'enforcement':s.get('enforcement'),'supervision':s.get('supervision')})
  time.sleep(5)
 still=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()==pid
 assert not still, samples
 h.record('interface apply events cannot mask a stopped daemon heartbeat',old_pid=pid,samples=samples)
finally:
 h.cmd('if test -d /proc/'+pid+'; then kill -CONT '+pid+'; fi\nuci set proxy_guard.main.enabled=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply')
