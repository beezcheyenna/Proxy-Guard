# Local PassWall process/log signals in a disconnected OpenWrt fixture.
import base64,json,shlex,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native017-fast-events.json'
def record(name,**kw):
 h.results.append({'case':name,**kw});h.result_file.write_text(json.dumps(h.results,ensure_ascii=False,indent=2)+'\n');print('PASS '+name,flush=True)
h.record=record
def count(name='cf'):return int(h.cmd('cat /tmp/event017-'+name+'-count 2>/dev/null || printf 0').strip())
def wait(fn,t=50):return h.wait_for(fn,t)
def emit(message):
 encoded=base64.b64encode(message.encode()).decode()
 code='import * as fs from "fs"; let d=localtime(time()); let f=fs.open("/tmp/log/passwall.log","a"); f.write(sprintf("%04d-%02d-%02d %02d:%02d:%02d: %s\\n",d.year,d.mon,d.mday,d.hour,d.min,d.sec,b64dec("'+encoded+'")));f.close();'
 h.cmd('ucode -e '+shlex.quote(code))
h.cmd("""mkdir -p /tmp/log
uci set proxy_guard.main.passwall_watch=1
uci set proxy_guard.main.boot_guard=0
uci set proxy_guard.main.passwall_log_watch=1
uci set proxy_guard.main.passwall_log_interval=1
uci set proxy_guard.main.passwall_trigger=any
uci set proxy_guard.main.fast_wait_enabled=1
uci set proxy_guard.main.fast_wait_seconds=10
uci set proxy_guard.main.fast_stable_enabled=1
uci set proxy_guard.main.fast_stable_seconds=60
uci set proxy_guard.main.cf_event_check=1
uci commit proxy_guard
printf good >/tmp/event017-cf-mode
printf good >/tmp/event017-ip-mode
/usr/libexec/proxy-guard apply
""")
s=wait(lambda s:s.get('enforcement')=='allowing' and s.get('fast_watch',{}).get('phase')=='normal')
before=count();emit('删除 nftables 规则完成。')
s=wait(lambda s:s.get('enforcement')=='blocked' and s.get('fast_watch',{}).get('phase')=='log_wait',12)
first=h.fast().get('cf_event_id');assert first
h.cmd('test -f /tmp/fast-dns.pid\nkill $(cat /tmp/fast-dns.pid)')
s=wait(lambda s:s.get('fast_watch',{}).get('dns') is False,12)
assert h.fast().get('cf_event_id')==first and count()==before
ip_before=count('ip');google_before=count('google');time.sleep(2)
assert count('ip')==ip_before and count('google')==google_before and count()==before
h.record('log deletion and service loss merge one event; pending log recovery performs no external checks',status=s,cf_requests=count(),traffic=h.traffic(True))
h.cmd('/tmp/etc/passwall/bin/chinadns-ng /tmp/etc/passwall/acl/default/chinadns_ng.uc >/tmp/fast-dns.log 2>&1 &\necho $! >/tmp/fast-dns.pid')
emit('运行完成！')
s=wait(lambda s:s.get('enforcement')=='allowing' and s.get('fast_watch',{}).get('phase')=='sensitive')
assert count()==before+1,(before,count(),s)
h.record('merged log/service recovery issues exactly one CF call and opens 60-second observation',status=s,cf_requests=count(),traffic=h.traffic(False))
before=count();emit('删除 nftables 规则完成。')
s=wait(lambda s:s.get('enforcement')=='blocked' and s.get('fast_watch',{}).get('phase')=='delay',12)
f=h.fast();assert f.get('cf_event_id')!=first
end=f['delay_until'];emit('运行完成！');ip_before=count('ip');google_before=count('google')
time.sleep(1)
s=h.state();assert s.get('enforcement')=='blocked' and h.fast()['delay_until']==end,s
assert count()==before and count('ip')==ip_before and count('google')==google_before
h.record('new interruption during sensitivity starts configured blocking wait with no external probes',status=s,cf_requests=count())
s=wait(lambda s:s.get('enforcement')=='allowing' and s.get('fast_watch',{}).get('phase')=='sensitive')
assert count()==before+1,(before,count(),s)
time.sleep(4);assert count()==before+1
h.record('new sensitivity outage schedules a second distinct CF call, without repeated recovery calls',status=s,cf_requests=count())
print('ALL NATIVE017 LOCAL EVENT MERGE / SENSITIVITY CASES PASSED',flush=True)
