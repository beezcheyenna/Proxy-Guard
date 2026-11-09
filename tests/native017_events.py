# Real SOCKS/TLS event-count acceptance in the disconnected OpenWrt lab.
# Uses exact hostnames through isolated fixture DNS/TLS; no RPC repair.
import json,shlex,time
import vm_boot_guard as h
h.tag();h.results=[];h.result_file=h.lab/'logs/native017-events.json'
def count(name='cf'):
 return int(h.cmd('cat /tmp/event017-'+name+'-count 2>/dev/null || printf 0').strip())
def mode(name,value):h.cmd('printf %s '+shlex.quote(value)+' >/tmp/event017-'+name+'-mode')
def wait(fn,t=70):return h.wait_for(fn,t)
def healthy():return wait(lambda s:s.get('enforcement')=='allowing' and s.get('last_probe_ok') is True)
def cf(s):return s.get('cf_event',{})
def record(name,**kw):
 h.results.append({'case':name,**kw});h.result_file.write_text(json.dumps(h.results,ensure_ascii=False,indent=2)+'\n');print('PASS '+name,flush=True)
def primary_outage():
 mode('ip','wrong')
 s=wait(lambda s:s.get('enforcement')=='blocked' and s.get('exit_check',{}).get('observed')=='203.0.113.99')
 before=count();time.sleep(2)
 assert count()==before,'CF must wait for successful fresh primary recovery'
 return s
h.cmd("""set -eu
/etc/init.d/proxy-guard stop
uci set proxy_guard.main.enabled=1
uci set proxy_guard.main.mode=guard
uci set proxy_guard.main.startup_grace=0
uci set proxy_guard.main.schedule_enabled=0
uci set proxy_guard.main.passwall_watch=0
uci set proxy_guard.main.boot_guard=0
uci set proxy_guard.main.self_heal=0
uci set proxy_guard.main.udp_check=0
uci set proxy_guard.main.cf_event_check=1
uci set proxy_guard.main.interval=5
uci set proxy_guard.main.timeout=2
uci set proxy_guard.main.fail_threshold=1
uci set proxy_guard.main.recover_threshold=1
uci set proxy_guard.main.expected_exit4=203.0.113.7
uci set proxy_guard.main.exit_url=https://api.ipify.org/
uci -q delete proxy_guard.main.targets
uci add_list proxy_guard.main.targets='https://www.gstatic.com/generate_204|204'
uci add_list proxy_guard.main.targets='https://api.ipify.org/|200'
uci -q delete proxy_guard.main.sources4
uci add_list proxy_guard.main.sources4=192.0.2.0/24
uci -q delete proxy_guard.main.sources6
uci add_list proxy_guard.main.sources6=2001:db8:1::/64
uci -q delete proxy_guard.main.local4
uci add_list proxy_guard.main.local4=192.0.2.0/24
uci -q delete proxy_guard.main.local6
uci add_list proxy_guard.main.local6=2001:db8:1::/64
uci commit proxy_guard
printf good >/tmp/event017-ip-mode
printf good >/tmp/event017-cf-mode
""")
# This reset starts a functional scenario only; cold-boot is accepted separately.
start_count=count()
h.cmd('rm -f /var/run/proxy-guard/cf-event.json\n/etc/init.d/proxy-guard start')
s=healthy();s=wait(lambda s:cf(s).get('outcome')=='ok');after=count()
assert after==start_count+1,(start_count,after,s)
initial=count();time.sleep(12)
assert count()==initial,'healthy routine probes repeatedly called CF'
s=h.state();assert len(s['probes'])==2 and all('cloudflare' not in x['host'] for x in s['probes']),s
record('real HTTPS/SOCKS routine Google/ipify probes do not repeat CF',status=s,cf_requests=initial,primary_requests=count('ip'),google_requests=count('google'),traffic=h.traffic(False))
h.cmd('uci set proxy_guard.main.interval=6\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\nfw4 reload >/tmp/event017-fw4.log 2>&1')
healthy();h.cmd('/etc/init.d/proxy-guard restart');healthy();time.sleep(7)
assert count()==initial
record('save/apply, firewall4 reload and plugin restart do not duplicate same-boot CF',cf_requests=count())
primary_outage();before=count();mode('ip','good');s=healthy()
assert count()==before+1,(before,count(),s)
time.sleep(8);assert count()==before+1
record('one new primary outage gets exactly one CF call after primary recovery',status=s,cf_requests=count(),traffic=h.traffic(False))
primary_outage();before=count();mode('cf','429');mode('ip','good');s=healthy()
assert count()==before+1 and cf(s).get('http_code')==429 and cf(s).get('outcome')=='unavailable',(before,count(),s)
time.sleep(8);assert count()==before+1
record('CF HTTP429 is auxiliary and never retries the same event',status=s,cf_requests=count())
primary_outage();before=count();mode('cf','wrong');mode('ip','good')
s=wait(lambda s:cf(s).get('outcome')=='mismatch' and cf(s).get('rechecking') is True)
assert s.get('enforcement')=='blocked' and s.get('last_probe_ok') is False,s
record('explicit wrong CF exit keeps protection despite prior primary success',status=s,traffic=h.traffic(True))
s=healthy();assert count()==before+1,(before,count(),s)
time.sleep(8);assert count()==before+1
record('CF mismatch needs later fresh primary confirmations without recursive CF fault loop',status=s,cf_requests=count())
primary_outage();before=count();mode('cf','timeout');mode('ip','good');s=healthy()
assert count()==before+1 and cf(s).get('outcome')=='unavailable',s
time.sleep(8);assert count()==before+1
record('bounded CF timeout does not repeat or override successful primary checks',status=s,cf_requests=count())
h.cmd('uci set proxy_guard.main.cf_event_check=0\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply');healthy()
before=count();primary_outage();mode('ip','good');healthy();assert count()==before
record('disabled switch suppresses CF during genuine outage/recovery',cf_requests=count())
mode('cf','good')
h.cmd('uci set proxy_guard.main.cf_event_check=1\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply');healthy();assert count()==before
record('reenabling completed auxiliary verification does not create routine calls',cf_requests=count())
print('ALL NATIVE017 EVENT HTTP/SOCKS/LEASE CASES PASSED',flush=True)
