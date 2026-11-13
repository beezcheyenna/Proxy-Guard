package.path='/usr/lib/?.lua;'..package.path
local json=require 'luci.jsonc'
local action=arg[1]
if action=='supervise' or action=='recovery_check' then
    local ok,value=pcall(function()
        local supervision=require 'proxy-guard.supervision'
        return action=='supervise' and supervision.tick() or {ok=supervision.check(arg[2])}
    end)
    print(json.stringify(ok and value or {ok=false,error='自检执行异常'}))
    os.exit(ok and value.ok~=false and 0 or 1)
end
local allowed={tick=true,apply=true,status=true,logs=true,clear_logs=true,stop=true,cleanup=true}
if not allowed[action] then io.stderr:write('Unsupported action\n'); os.exit(2) end
local worker
local ok,result=pcall(function()
    worker=require 'proxy-guard.worker'
    if action=='tick' or action=='apply' then return {ok=worker.tick(action=='apply')} end
    return worker[action]()
end)
-- Expected configuration/environment/proxy failures return normally. Only
-- uncaught execution errors count towards automatic plugin recovery.
-- Only the daemon's tick is its heartbeat; saves and netifd reconciliation
-- must not make a stalled daemon appear alive.
if action=='tick' then
    pcall(function()
        local path='/var/run/proxy-guard/worker-health.json'
        local f=io.open(path,'r');local old=f and json.parse(f:read('*a')) or {};if f then f:close() end
        local t=io.open('/proc/uptime','r');local up=t and tonumber(t:read('*a'):match('^[%d%.]+')) or 0;if t then t:close() end
        f=assert(io.open(path..'.new','w'));f:write(json.stringify({updated_uptime=up,errors=ok and 0 or ((old and old.errors or 0)+1)}));f:close();assert(os.rename(path..'.new',path))
    end)
end
if not ok then
    if worker and action~='status' and action~='logs' then pcall(worker.fail,result) end
    print(json.stringify({ok=false,error=tostring(result):sub(1,500)})); os.exit(1)
end
print(json.stringify(result or {ok=true}))
if type(result)=='table' and result.ok==false then os.exit(1) end
