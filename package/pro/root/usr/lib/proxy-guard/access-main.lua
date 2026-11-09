package.path='/usr/lib/?.lua;'..package.path
local m=require 'proxy-guard.access'
local json=require 'luci.jsonc'
if arg[1]=='egress' then local ok,value=pcall(m.collect_egress);os.exit(ok and value and 0 or 1) end
if arg[1]=='status' then print(json.stringify(m.status()));return end
if arg[1]=='bump' then m.bump();return end
if arg[1]=='recover_trial'then local ok,result=pcall(m.recover_trial);os.exit(ok and result and 0 or 1)end
if arg[1]=='jobs' then
    local ok,result=pcall(m.jobs)
    if not ok then pcall(m.abort_job,tostring(result):match('([a-z_]+)$') or 'operation_failed') end
    os.exit(ok and result and 0 or 1)
end
if arg[1]~='once' then os.exit(2) end
local trial_ok,trial_result=pcall(m.policy_progress)
if not trial_ok or not trial_result then os.exit(1)end
local health_ok,health_result=pcall(m.health)
local path_ok,path_result=pcall(m.path)
local ok,result=pcall(m.once)
os.remove('/var/run/proxy-guard-access/heartbeat-wake')
if not ok then
    local f=io.open('/var/run/proxy-guard-access/status.json.new','w')
    if f then f:write(json.stringify({enabled=true,phase='error',error=tostring(result):match('([a-z_]+)$') or 'configuration_error',updated_at=os.time()}));f:close();os.rename('/var/run/proxy-guard-access/status.json.new','/var/run/proxy-guard-access/status.json') end
    os.remove('/var/run/proxy-guard-access/headers');os.remove('/var/run/proxy-guard-access/headers.new')
end
os.exit(ok and result and 0 or 1)
