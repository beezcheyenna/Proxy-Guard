package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local m=require 'proxy-guard.cf-event'
local core=require 'proxy-guard.core'
local n=0
local function check(ok,label) assert(ok,label);n=n+1 end
local function copy(t) local r={} for k,v in pairs(t) do r[k]=type(v)=='table' and copy(v) or v end return r end
local s=m.load(nil,'boot-a')
check(m.pending(s),'initial boot gets one pending attempt')
check(m.begin(s,1700000000,'203.0.113.7'),'first attempt reserved')
check(not m.begin(s,1700000001,'203.0.113.7'),'same event cannot reserve twice')
local seq=s.sequence
s=m.load(copy(s),'boot-a')
check(not m.pending(s) and s.result.outcome=='interrupted','kill after reservation cannot repeat request after worker restart')
m.finish(s,{outcome='unavailable',http_code=429,curl_code=0},1700000002,2)
check(m.qualify(s,true),'auxiliary429 does not alone block fresh successful primary checks')
check(not m.pending(s),'429 cannot schedule retries')
m.observe(s,{recovered=true})
m.observe(s,{primary_fault=true})
check(m.pending(s) and s.sequence==seq+1,'confirmed new primary outage schedules one request')
seq=s.sequence
for i=1,100 do m.observe(s,{primary_fault=true}) end
check(s.sequence==seq,'continuous primary outage does not generate repeated events')
m.observe(s,{fault_id='local-1',primary_fault=true})
check(s.sequence==seq,'local event joins already pending network outage')
m.begin(s,1700000010,'203.0.113.7')
m.finish(s,{outcome='ok',observed='203.0.113.7',colo='NRT',http_code=200,curl_code=0},1700000011,2)
for i=1,10 do m.observe(s,{fault_id='local-1',primary_fault=true}) end
check(s.sequence==seq and not m.pending(s),'duplicate local/network observations after attempt do not retry')
s=m.load(copy(s),'boot-a')
check(s.sequence==seq and not m.pending(s),'same-boot restart preserves attempt identity')
m.observe(s,{recovered=true})
m.observe(s,{fault_id='local-2'})
check(m.pending(s) and s.sequence==seq+1,'new local outage after release gets another attempt')
m.begin(s,1700000020,'203.0.113.7')
m.finish(s,{outcome='mismatch',observed='203.0.113.99',colo='NRT',http_code=200,curl_code=0},1700000021,2)
check(m.status(s,true).rechecking,'conflicting CF result remains visible for revalidation')
check(not m.qualify(s,true),'one later primary success cannot override mismatch')
check(not m.qualify(s,false),'a failed primary breaks consecutive confirmation')
check(not m.qualify(s,true),'fresh confirmation sequence starts again after failure')
check(m.qualify(s,true),'two consecutive later fresh primary successes finish conflict recheck')
check(not m.status(s,true).rechecking and not m.pending(s),'completed recheck does not retry CF')
seq=s.sequence
m.observe(s,{recovered=true})
m.observe(s,{primary_fault=true})
check(s.sequence==seq+1 and m.pending(s),'a genuine later primary interruption remains eligible')
s=m.load(copy(s),'boot-a')
check(m.pending(s),'confirmed primary fault remains pending independently of main status or configuration reset')
local fresh=m.load(copy(s),'boot-b')
check(fresh.sequence==1 and m.pending(fresh),'new boot resets RAM-only event budget')
for _,broken in ipairs({false,'x',1,{schema=1},{schema=1,boot_id='boot-a',sequence=-1}}) do
 check(m.pending(m.load(broken,'boot-a')),'malformed state becomes bounded initial event')
end
check(not core.config().cf_event_check,'auxiliary event verification stays off while optional exit verification is off')
check(core.config({exit_check='1',expected_exit4='203.0.113.7'}).cf_event_check,'auxiliary event verification defaults on when exit verification is enabled')
check(not core.config({cf_event_check='0'}).cf_event_check,'auxiliary event verification can be disabled')
check(not pcall(core.config,{cf_event_check='1;id'}),'malformed auxiliary toggle rejected')
local c=core.config({exit_check='1',expected_exit4='203.0.113.7'})
check(c.exit_url=='https://api.ipify.org/','routine primary exit API is ipify')
check(c.exit_fallback_url=='https://4.ident.me/','configured ipify IPv4 checks have one timeout fallback')
local custom=core.config({expected_exit4='203.0.113.7',exit_url='https://fixture.test/ipv4'})
check(custom.exit_fallback_url==nil and c.probe_budget-custom.probe_budget==c.timeout,'only ipify reserves a fallback timeout')
local backup='https://backup.example/ip?format=text'
local configured=core.config({expected_exit4='203.0.113.7',exit_url=custom.exit_url,exit_fallback_url=backup})
check(configured.exit_fallback_url==backup and configured.exit_fallback_host=='backup.example','custom primary and backup are supported')
check(configured.probe_budget-custom.probe_budget==configured.timeout,'a configured backup reserves one more request')
local cleared=core.config({expected_exit4='203.0.113.7',exit_fallback_url=''})
check(cleared.exit_fallback_url==c.exit_fallback_url,'clearing the override restores the ipify backup')
check(not pcall(core.config,{expected_exit4='203.0.113.7',exit_fallback_url='http://backup.example/ip'}),'backup requires HTTPS')
check(core.config({exit_check='0',exit_fallback_url=backup}).exit_fallback_url==nil,'disabled verification has no IP fallback')
local seen={}
for _,t in ipairs(c.targets) do seen[t.url]=true;check(not t.url:find('cloudflare',1,true),'routine targets exclude Cloudflare') end
check(seen['https://www.gstatic.com/generate_204'] and seen['https://connectivity-check.ubuntu.com/'],'default recurring connectivity checks exclude extra exit lookups')
local legacy=core.config({expected_exit4='203.0.113.7',targets={'https://www.gstatic.com/generate_204|204','https://api.ipify.org/|200'}})
check(legacy.exit_check and legacy.targets[2].url==legacy.exit_url,'explicit legacy IP target and verification are preserved')
print('PASS '..n..' CF event module and configuration boundary assertions')
