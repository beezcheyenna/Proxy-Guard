package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local core=require 'proxy-guard.core'
local n=0
local function check(ok,name)assert(ok,name);n=n+1 end
local function cfg(change)
 local values={enabled='1',mode='guard'}
 for k,v in pairs(change or {})do values[k]=v end
 return core.config(values)
end
check(not core.config().api_enabled and core.config().check_mode=='public','official HTTPS is default; API is opt-in')
check(#cfg().targets==0 and not cfg().exit_check,'official mode never runs website probes or implicitly checks IP')
check(cfg().public_hb_url=='https://hb.pghb.app/','official mode uses the published endpoint')
for _,values in ipairs({
 {check_mode='cf'},{check_mode='both'},{api_enabled='yes'},{api_default_seconds=20,api_max_seconds=10},
 {public_hb_interval=0},{public_hb_timeout=16},{public_hb_fail=0},{public_hb_recover=11}
}) do check(not pcall(cfg,values),'reject malformed configuration') end
local c=cfg({api_enabled='1'});local d={['br-lan']={pending=true}}
local rules=core.rules(c,d);local bootstrap=core.bootstrap(c,d)
for _,name in ipairs({'heartbeat_ifaces','api_blocks'})do
 check(rules:find('set '..name,1,true),'native gate '..name)
 check(not bootstrap:find('flush set inet proxy_guard '..name,1,true),'fw4 preserves gate deadlines '..name)
end
for _,direction in ipairs({'iifname','oifname'})do
 check(rules:find(direction..' != @heartbeat_ifaces counter drop',1,true),'heartbeat is bidirectional')
 check(rules:find(direction..' @api_blocks counter drop',1,true),'API is bidirectional')
end
check(not core.rules(core.config({enabled='1',mode='guard',check_mode='web'}),d):find('heartbeat_ifaces',1,true),'no heartbeat gate in legacy web mode')
check(not core.rules(core.config({enabled='1',mode='guard'}),d):find('api_blocks',1,true),'no API gate when disabled')
local machine=require 'proxy-guard.supervision-state'
local obs={up=200,wall_time=1800000000,boot_id='fixture',started=0,main_updated=200,fast_updated=200,heartbeat_updated=0,heartbeat_errors=0}
local a=machine.step(c,nil,obs);a=machine.step(c,a,obs)
check(a.action=='restart' and a.reason=='heartbeat_monitor','a hung official monitor is supervised independently')
obs.heartbeat_updated=200;a=machine.step(c,nil,obs)
check(a.state=='healthy','HTTPS transport failure is not a process failure when its execution heartbeat is fresh')
obs.heartbeat_errors=3;a=machine.step(c,nil,obs);a=machine.step(c,a,obs)
check(a.action=='restart','repeated official monitor execution errors request recovery')
obs.heartbeat_errors=0;a=machine.step(c,{boot_id='fixture',heartbeat_enabled=false,state='healthy'},obs)
check(a.state=='starting','enabling the official mode later receives an activation grace period')
print('PASS '..n..' heartbeat and API policy assertions')
