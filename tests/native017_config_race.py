# Reproduce the status-reset race using real tick, configuration apply and TLS.
import json,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native017-config-race.json'
def wait(fn,t=60):return h.wait_for(fn,t)
def count():return int(h.cmd('cat /tmp/event017-cf-count').strip())
wait(lambda s:s.get('enforcement')=='allowing')
pid=h.cmd('cat /var/run/proxy-guard/daemon.pid').strip()
before=count()
h.cmd('kill -STOP '+pid)
try:
 h.cmd('printf wrong >/tmp/event017-ip-mode\nsleep 7\n/usr/libexec/proxy-guard tick',30)
 s=h.state()
 assert s.get('enforcement')=='blocked' and s.get('primary_probe_ok') is False,s
 event=h.decode(h.cmd('cat /var/run/proxy-guard/cf-event.json'))
 assert event['pending'] is True,event
 seq=event['sequence']
 h.cmd('uci set proxy_guard.main.interval=5\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nprintf good >/tmp/event017-ip-mode')
 event=h.decode(h.cmd('cat /var/run/proxy-guard/cf-event.json'))
 assert event['pending'] is True and event['sequence']==seq,event
 assert count()==before
finally:
 h.cmd('kill -CONT '+pid)
s=wait(lambda s:s.get('enforcement')=='allowing')
assert count()==before+1,(before,count(),s)
h.results.append({'case':'confirmed fault persisted before next tick survives apply resetting main status and issues one recovery CF request','status':s,'event':event,'cf_before':before,'cf_after':count()})
h.result_file.write_text(json.dumps(h.results,ensure_ascii=False,indent=2)+'\n')
print('PASS confirmed primary fault survives same-tick config apply and issues one recovery CF request',flush=True)
