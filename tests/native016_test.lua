package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local core=require 'proxy-guard.core'
local n=0
local function check(ok,name) assert(ok,name);n=n+1 end
local trace='https://www.cloudflare.com/cdn-cgi/trace'
check(core.config({check_mode="web"}).targets[1].url=='https://www.gstatic.com/generate_204','Google default')
check(core.config({check_mode="web"}).targets[2].url=='https://connectivity-check.ubuntu.com/' and core.config({check_mode="web"}).targets[2].code==204,'default recurring targets do not perform extra IP lookup')
check(core.config().exit_url=='https://api.ipify.org/','reuse ipify for exit')
for _,url in ipairs({trace,trace..'?x=1','https://fixture.test/cdn-cgi/trace'}) do check(core.is_trace_url(url),url) end
for _,url in ipairs({trace..'evil',trace..'/other',trace..'#frag','http://www.cloudflare.com/cdn-cgi/trace','https://foo.test/?/cdn-cgi/trace'}) do check(not core.is_trace_url(url),'reject false trace '..url) end
local a=core.trace('ip=203.0.113.7\ncolo=NRT\nhttp=http/2\ntls=TLSv1.3\n')
check(a and a.ip=='203.0.113.7' and a.colo=='NRT','valid trace')
check(core.trace('ip=203.0.113.7\r\ncolo=SJC\r\n').colo=='SJC','CRLF and colo changes')
check(core.trace('ip=2001:db8::7\ncolo=NRT\n').ip=='2001:db8::7','IPv6 is reported and compared honestly')
for _,body in ipairs({'','<html>ok</html>','203.0.113.7','ip=203.0.113.7\n','colo=NRT\n','ip=256.1.2.3\ncolo=NRT',
 'ip=203.0.113.7/32\ncolo=NRT','ip=203.0.113.7\nip=203.0.113.7\ncolo=NRT',
 'ip=203.0.113.7\ncolo=NRT\ncolo=SJC','ip=203.0.113.7\ncolo=nrt','ip=203.0.113.7\ncolo=NRT\rjunk',
 'ip=203.0.113.7\ncolo=NRT\0','ip=203.0.113.7\ncolo=NRT\nuag='..string.rep('x',4096)}) do
 check(core.trace(body)==nil,'invalid/truncated trace')
end
check(core.exit_response('https://custom.test/',' 203.0.113.7\n').ip=='203.0.113.7','legacy plain IP')
check(core.exit_response(trace,'ip=203.0.113.7\ncolo=NRT').ip=='203.0.113.7','exit trace parser')
check(not core.exit_response('https://custom.test/','ip=203.0.113.7\ncolo=NRT'),'plain endpoint does not guess format')
local c=core.config({enabled='1',mode='guard',expected_exit4='203.0.113.7',passwall_watch='1'})
local d={['br-lan']={pending=true}}
local b=core.bootstrap(c,d)
check(b:find('add table inet proxy_guard',1,true)~=nil,'native table')
check(not b:find('delete table',1,true),'no destructive replacement on reload')
for _,name in ipairs({'healthy_ifaces','service_ifaces','healthy_times'}) do
 check(not b:find('flush set inet proxy_guard '..name,1,true),'preserve '..name)
 check(not b:find('add element inet proxy_guard '..name,1,true),'never extend '..name)
end
check(b:find('flush set inet proxy_guard sources4',1,true)~=nil,'static scope refreshed')
check(b:find('meta pkttype host',1,true)~=nil,'early name based host scope')
check(b:find('priority %-310')~=nil,'early hook')
check(not b:find('"21:59:55"',1,true),'numeric UTC time')
local fallback=core.rules(c,{['br-lan']={kind=1,mac='02:00:00:00:00:01',bridge_filter_mac='02:00:00:00:00:01'}})
check(fallback:find('ether daddr 02:00:00:00:00:01',1,true)~=nil,'incompatible bridge filtering uses safe MAC scope')
check(fallback:find('ether daddr != 02:00:00:00:00:01 return',1,true)~=nil,'bridge transit remains preserved')
check(not fallback:find('meta pkttype host',1,true),'rewritten packet type never scopes bridge filtering')
print('PASS '..n..' trace and native policy assertions')
