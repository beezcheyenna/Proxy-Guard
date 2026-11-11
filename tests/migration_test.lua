package.path=(os.getenv('PG_SOURCE')or'/src')..'/package/root/usr/lib/?.lua;'..package.path
local source=(os.getenv('PG_SOURCE')or'/src')..'/package/root/usr/libexec/proxy-guard-migrate'
source=arg[1]or source
local original_uci=package.loaded.uci;local real_open=io.open;local checks=0
local function run(raw)
 local committed=false
 package.loaded.uci={cursor=function()return {
  load=function(_,path)assert(path=='/etc/config/proxy_guard');return true end,
  get_all=function()return raw end,
  set=function(_,config,section,key,value)assert(config=='proxy_guard'and section=='main');raw[key]=value;return true end,
  commit=function(_,config)assert(config=='proxy_guard');committed=true;return true end
 }end}
 io.open=function(path,...)if path=='/usr/share/proxy-guard/private-exit-migration'then return nil end;return real_open(path,...)end
 assert(loadfile(source))();io.open=real_open;package.loaded.uci=original_uci
 return raw,committed
end
local c=run({targets={'https://www.google.com/generate_204|204','https://cp.cloudflare.com/generate_204|204'},exit_url='https://www.cloudflare.com/cdn-cgi/trace',expected_exit4='9.9.9.9',interval='17'})
assert(c.targets[1]=='https://www.gstatic.com/generate_204|204'and c.targets[2]=='https://connectivity-check.ubuntu.com/|204','legacy defaults must use two connectivity targets, not a recurring IP reflector');checks=checks+1
assert(c.exit_url=='https://api.ipify.org/'and c.exit_check=='1'and c.interval=='17','migration preserves legacy verification opt-in and timing');checks=checks+1
local custom={'https://first.example/generate_204|204','https://second.example/generate_204|204'}
c=run({targets=custom,exit_url='https://custom.example/ip',exit_check='0',setup_complete='1',expected_exit4='',interval='19'})
assert(c.targets==custom and c.exit_url=='https://custom.example/ip'and c.exit_check=='0'and c.interval=='19','custom targets and explicit verification-off are retained');checks=checks+1
local gstatic='https://www.gstatic.com/generate_204|204'
local google='https://www.google.com/generate_204|204'
local ubuntu='https://connectivity-check.ubuntu.com/|204'
local committed
c,committed=run({targets={gstatic,google},exit_url='https://custom.example/ip',exit_check='0',setup_complete='1',cf_event_check='1',interval='19',min_success='2'})
assert(committed and c.targets[1]==gstatic and c.targets[2]==ubuntu,'migrate the exact previous default pair');checks=checks+1
assert(c.exit_url=='https://custom.example/ip' and c.exit_check=='0' and c.interval=='19' and c.min_success=='2','migrating the default pair leaves probe options alone');checks=checks+1
c,committed=run(c)
assert(not committed and c.targets[2]==ubuntu,'the new pair needs no further migration');checks=checks+1
local expanded={gstatic,google,'https://third.example/check|204'}
c,committed=run({targets=expanded,exit_check='0',setup_complete='1',cf_event_check='1'})
assert(not committed and c.targets==expanded,'retain custom lists that happen to include both old defaults');checks=checks+1
print('PASS '..checks..' default migration and custom configuration preservation assertions')
