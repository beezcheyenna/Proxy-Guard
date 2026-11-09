package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local core=require 'proxy-guard.core'
local machine=require 'proxy-guard.supervision-state'
local udp=require 'proxy-guard.udp'
local incidents=require 'proxy-guard.incidents'
local n=0
local function check(ok,name) assert(ok,name);n=n+1 end
local c=core.config({enabled='1',expected_exit4='203.0.113.7',schedule_enabled='0',passwall_watch='1',self_heal_stale='15',self_heal_cooldown='30',self_heal_limit='2',self_heal_window='60'})
local function o(t,good) return {up=t,started=0,boot_id='a',main_updated=good and t or 0,fast_updated=good and t or 0,probe_budget=5,lease_seconds=10} end
local s=machine.step(c,nil,o(10,false));check(s.state=='starting','startup grace prevents false recovery')
s=machine.step(c,s,o(100,true));check(s.state=='healthy','healthy heartbeat')
s=machine.step(c,s,o(101,false));check(s.state=='suspect' and not s.action,'two observations required')
s=machine.step(c,s,o(106,false));check(s.action=='restart' and s.restart_count==1,'stale main queues recovery')
s=machine.step(c,s,o(111,false));s=machine.step(c,s,o(116,false));check(s.state=='cooldown' and not s.action,'cooldown prevents restart loop')
s=machine.step(c,s,o(136,false));check(s.action=='restart' and s.restart_count==2,'second recovery after cooldown')
s=machine.step(c,s,o(137,false));s=machine.step(c,s,o(138,false));check(s.state=='cooldown','budget also respects cooldown')
s=machine.step(c,s,o(166,false));check(s.action=='restart' and s.restart_count==2,'sliding window expires first recovery at exact boundary')
c.self_heal_limit=1;s=machine.step(c,s,o(196,false));s=machine.step(c,s,o(197,false));check(s.state=='limited' and not s.action,'rolling restart budget enforced')
c.self_heal_window=5;s=machine.step(c,{boot_id="a",restarts={190},last_restart=190,failures=2},o(198,false));check(s.state=='healthy' or s.state=='cooldown','independent last restart preserves cooldown after window expires')
local fresh=machine.step(c,s,{up=10,started=0,boot_id='new',main_updated=10,fast_updated=10});check(fresh.restart_count==0,'new boot resets monotonic restart budget')
c.self_heal=false;s=machine.step(c,nil,o(200,false));check(s.state=='watching' and not s.action,'explicit self-heal off')
c.self_heal=true;c.enabled=false;s=machine.step(c,nil,o(200,false));check(s.state=='disabled' and not s.action,'disabled never recovered')
c.enabled=true;local obs=o(200,false);obs.stopped=true;s=machine.step(c,nil,obs);check(s.state=='stopped' and not s.action,'manual stop takes precedence')
obs=o(200,true);obs.fast_updated=0;s=machine.step(c,nil,obs);s=machine.step(c,s,obs);check(s.action=='restart' and s.reason=='fast_heartbeat','independent fast heartbeat')
obs=o(200,true);obs.runtime_errors=3;s=machine.step(c,nil,obs);s=machine.step(c,s,obs);check(s.action=='restart' and s.reason=='execution_errors','uncaught execution errors can trigger recovery')
obs=o(200,true);obs.runtime_errors=0;s=machine.step(c,s,obs);check(s.state=='healthy','expected proxy failure is not execution failure')
obs=o(50,true);obs.probe_budget=90;obs.main_updated=1;s=machine.step(c,nil,obs);check(s.state=='starting','large valid probe budget cannot cause false restart')
for _,key in ipairs({'self_heal_stale','self_heal_cooldown','self_heal_limit','self_heal_window','udp_port','udp_timeout'}) do
    check(not pcall(core.config,{[key]='1;id'}),key..' injection')
end
for _,name in ipairs({'','example.com/hi','example.com:53','a..b','-test.example','test-.example',string.rep('a',64)..'.test','a\nb'}) do
    check(not pcall(core.config,{udp_query=name}),'invalid UDP name '..name)
end
check(core.config({udp_query='a-b.Example.com'}).udp_query=='a-b.Example.com','valid domain')
check(not pcall(core.config,{udp_check='1'}),'UDP requires explicit target')
check(not core.config().udp_check,'UDP default off')
local d=core.config({udp_check='1',udp_server='203.0.113.53'});check(d.lease_seconds==core.config().lease_seconds+d.udp_timeout,'UDP included in bounded permit budget')
local id='\18\52';local question='\7example\3com\0\0\1\0\1';local packet=id..'\129\128\0\1\0\0\0\0\0\0'..question
check(udp.valid_dns(packet,id,'EXAMPLE.COM'),'DNS ID and question match')
for _,bad in ipairs({packet:sub(1,-2),'xx'..packet:sub(3),id..'\1'..packet:sub(4),id..'\131'..packet:sub(4),packet:sub(1,3)..'\131'..packet:sub(5),packet:sub(1,12)..'\192\12'}) do
    check(not udp.valid_dns(bad,id,'example.com'),'invalid/truncated/forged DNS response')
end
check(not udp.valid_dns(packet,id,'other.example'),'wrong question rejected')
local grouped=incidents.group({{time=1,stage='blocked',incident={id='a',started_uptime=1,elapsed=0}},
{time=2,stage='normal',incident={id='a',started_uptime=1,elapsed=60,completed_uptime=61}},
{time=3,stage='sensitive',incident={id='a',started_uptime=1,elapsed=15}}})
check(#grouped==1 and #grouped[1].steps==3 and grouped[1].summary.elapsed==60,'clock changes cannot regress incident summary')
s=machine.step(c,{boot_id='a',restarts='broken',failures='broken',last_restart='broken'},{up=300,started=0,boot_id='a',main_updated='broken',fast_updated='broken'});check(s.state=='suspect','corrupt state types cannot disable supervisor')
local expired=o(300,true);expired.recovery_expired=true;s=machine.step(c,nil,expired);s=machine.step(c,s,expired);check(s.action=='restart' and s.reason=='recovery_timeout','a lost queued restart cannot leave a fresh but permanently held worker')
local old={boot_id='a',state='suspect',restarts={},failures=2}
s=machine.step(c,old,o(300,false));check(old.state=='suspect' and #old.restarts==0,'supervision transitions do not mutate previous snapshot or hide limit log')
package.loaded['luci.jsonc']=package.loaded['luci.jsonc'] or {}
local preflight=require 'proxy-guard.preflight'
check(not preflight.check({enabled='0',expected_exit4='203.0.113.7'}).ok,'draft cannot pass with implicit scope/target defaults that real enable rejects')
check(not preflight.check({enabled='0',interfaces={'br-lan;id'}}).ok,'preflight validates interface input before environment inspection')
check(#incidents.group({{incident={id='x',started_uptime=0,elapsed='broken',causes='broken'}},{incident={id='y',started_uptime='bad'}}})==1,'damaged incident metadata cannot make intact log RPC fail')
local history=incidents.group({
 {incident={id='boot:37',started_uptime=37,elapsed=0,holding=true,causes={boot=true}}},
 {incident={id='boot:44',started_uptime=44,elapsed=350,holding=false,completed_uptime=394,causes={boot=true}}}
})
check(#history==2 and history[1].summary.superseded==true,'a replaced startup incident is not presented as still active')
check(history[1].summary.completed_uptime==nil,'missing completion is not fabricated')
check(history[2].summary.completed_uptime==394 and not history[2].summary.superseded,'completed later incident stays authoritative')
local live=incidents.group({{incident={id='live',started_uptime=10,holding=true}}})
check(live[1].summary.holding and not live[1].summary.superseded,'latest incomplete incident remains pending')
local recovery_config=core.config({enabled='1',expected_exit4='203.0.113.7',self_heal_stale='15',self_heal_cooldown='30',self_heal_limit='2',self_heal_window='60'})
local fault={up=100,started=0,boot_id='history',main_updated=0,fast_updated=100,probe_budget=1,lease_seconds=1,wall_time=1800000000}
local history_state=machine.step(recovery_config,nil,fault);history_state=machine.step(recovery_config,history_state,fault)
check(history_state.last_reason=='main_heartbeat' and history_state.last_restart_at==1800000000 and history_state.last_restart_result=='queued','restart cause and wall time are recorded without command or configuration data')
local healthy={up=110,started=0,boot_id='history',main_updated=110,fast_updated=110,probe_budget=1,lease_seconds=1}
history_state=machine.step(recovery_config,history_state,healthy)
check(history_state.last_restart_result=='recovered' and history_state.last_reason=='main_heartbeat','successful recovery preserves the cause for diagnosis')
check(history_state.restart_count==1 and history_state.restart_limit==2,'recovered monitors retain their rolling restart budget')
healthy.boot_id='next-boot';healthy.up=1;healthy.main_updated=1;healthy.fast_updated=1
history_state=machine.step(recovery_config,history_state,healthy)
check(history_state.last_reason==nil and history_state.restart_count==0,'restart history cannot leak across a new monotonic boot')
local enable_config=core.config({enabled='0',passwall_watch='1',self_heal_stale='15'})
local enable_state=machine.step(enable_config,nil,o(500,false))
enable_config.enabled=true;local enable_obs=o(501,true);enable_obs.fast_updated=nil
enable_state=machine.step(enable_config,enable_state,enable_obs)
check(enable_state.state=='starting' and not enable_state.action,'enabling after long disabled runtime starts a new heartbeat grace')
enable_obs.up=502;enable_state=machine.step(enable_config,enable_state,enable_obs)
check(enable_state.state=='starting' and not enable_state.action,'second observation cannot restart a monitor still starting')
enable_obs.up=600;enable_state=machine.step(enable_config,enable_state,enable_obs);enable_state=machine.step(enable_config,enable_state,enable_obs)
check(enable_state.action=='restart','new activation grace remains bounded and still detects a real crash')
local damaged_grace=machine.step(enable_config,{boot_id='a',state='healthy',activation_started=1e12},o(800,false));check(damaged_grace.state=='suspect','corrupt future activation time cannot suppress crash detection')
print('PASS '..n..' new supervisor, configuration, UDP response and incident assertions')
