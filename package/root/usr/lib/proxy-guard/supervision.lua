-- Independent heartbeat supervision; never restarts PassWall or network/DNS.
local core=require 'proxy-guard.core'
local json=require 'luci.jsonc'
local machine=require 'proxy-guard.supervision-state'
local metrics=require 'proxy-guard.resource-metrics'
local M={}
local run='/var/run/proxy-guard'
local function read(path) local f=io.open(path,'r');if not f then return nil end;local s=f:read('*a');f:close();return s end
local function decoded(path) local ok,s=pcall(json.parse,read(path) or '');return ok and type(s)=='table' and s or nil end
local function write(path,value) local f=assert(io.open(path..'.new','w'));assert(f:write(json.stringify(value)));assert(f:close());assert(os.rename(path..'.new',path)) end
local function up() return tonumber((read('/proc/uptime') or ''):match('^[%d%.]+')) or 0 end
local function control() return (read(run..'/control-generation') or 'initial'):match('^([%w%-]+)') end
local function configuration()
    local raw=require('uci').cursor():get_all('proxy_guard','main')
    local c=core.load_config(raw)
    if raw.enabled=='0' then
        c.resource_monitor=raw.resource_monitor~='0';c.self_heal=raw.self_heal~='0'
        for key,bounds in pairs({self_heal_window={60,3600},self_heal_cooldown={30,3600},self_heal_limit={1,10},self_heal_stale={15,600}}) do
            local value=tonumber(raw[key]);if value and value%1==0 and value>=bounds[1] and value<=bounds[2] then c[key]=value end
        end
    end
    return c
end
local function proc(pid)
    local raw=read('/proc/'..pid..'/stat') or ''
    local tail=raw:match('^%d+ %(.+%) (.*)$')
    if not tail then return nil end
    local fields={};for word in tail:gmatch('%S+') do fields[#fields+1]=word end
    if fields[1]=='Z' or fields[1]=='X' then return nil end
    return {identity=pid..':'..tostring(fields[20]),ticks=(tonumber(fields[12]) or 0)+(tonumber(fields[13]) or 0)+(tonumber(fields[14]) or 0)+(tonumber(fields[15]) or 0),
        rss=tonumber((read('/proc/'..pid..'/status') or ''):match('VmRSS:%s+(%d+)')) or 0}
end
local function resources(previous,now)
    local seen,roots,children={},{},{};local rss,ticks,count=0,0,0
    -- OpenWrt commonly omits CONFIG_CHECKPOINT_RESTORE and task/children.
    -- A fixed glob lists stat paths; only proc metadata is read, never commands.
    local paths=io.popen("printf '%s\\n' /proc/[0-9]*/stat",'r')
    if paths then
        for path in paths:lines() do
            local pid=path:match('^/proc/(%d+)/stat$')
            local tail=pid and (read(path) or ''):match('^%d+ %(.+%) (.*)$')
            local parent=tail and tail:match('^%S+%s+(%d+)')
            if parent then children[parent]=children[parent] or {};children[parent][#children[parent]+1]=pid end
        end
        paths:close()
    end
    local function walk(pid)
        if seen[pid] or count>=32 then return end;seen[pid]=true
        local p=proc(pid);if not p then return end
        rss=rss+p.rss;ticks=ticks+p.ticks;count=count+1
        for _,child in ipairs(children[pid] or {}) do walk(child) end
    end
    for _,role in ipairs({'daemon','fast_watch','supervisor'}) do
        local pid=(read(run..'/'..role..'.pid') or ''):match('^(%d+)')
        local command=pid and read('/proc/'..pid..'/cmdline') or ''
        local argv={};for word in (command or ''):gmatch('[^%z]+') do argv[#argv+1]=word end
        local owned=role=='fast_watch' and argv[2]=='/usr/lib/proxy-guard/fast-watch.uc' or
            role~='fast_watch' and argv[2]=='/usr/libexec/proxy-guard' and argv[3]==role
        if pid and owned then local p=proc(pid);if p then roots[#roots+1]=p.identity;walk(pid) end end
    end
    table.sort(roots);local identity=table.concat(roots,',')
    local sizes=0
    for _,name in ipairs({'events.jsonl','events.jsonl.1','checks.jsonl','checks.jsonl.1','fast-events.jsonl','fast-events.jsonl.1','supervision-events.jsonl','supervision-events.jsonl.1'}) do
        local f=io.open(run..'/'..name,'r');if f then sizes=sizes+(f:seek('end') or 0);f:close() end
    end
    local system_ticks,cores=metrics.cpu_snapshot(read('/proc/stat'))
    local sample={sample_uptime=now,rss_kib=rss,process_count=count,log_bytes=sizes,
        cpu_ticks=ticks,system_ticks=system_ticks,cpu_cores=cores,cpu_basis='all_online_cpus',identity=identity}
    sample.cpu_percent,sample.cpu_core_percent=metrics.cpu_usage(previous,sample)
    return sample
end
local function event(c,s,message)
    local path=run..'/supervision-events.jsonl';local f=io.open(path,'r');local size=f and f:seek('end') or 0;if f then f:close() end
    if size>c.log_kib*1024 then assert(os.rename(path,path..'.1')) end
    f=assert(io.open(path,'a'));assert(f:write(json.stringify({time=os.time(),level=(s.state=='queued' or s.state=='limited') and 'error' or 'info',event='self_heal_'..s.state,message=message})..'\n'));f:close()
end
function M.check(generation)
    if type(generation)~='string' or #generation>64 or not generation:match('^[%w%-]+$') then return false end
    if read(run..'/removing') or read(run..'/stopped') or control()~=generation then return false end
    local ok,c=pcall(configuration);if not ok or not c.enabled or not c.self_heal then return false end
    local request=decoded(run..'/recovery-hold.json')
    return request and request.generation==generation and type(request.queued_uptime)=='number' and request.queued_uptime<=up() and up()-request.queued_uptime<=30 or false
end
function M.tick()
    local now=up();local previous=decoded(run..'/supervision.json');local ok,c=pcall(configuration)
    if not ok then
        -- Invalid/transient UCI reads pause recovery without erasing its budget.
        local boot=(read('/proc/sys/kernel/random/boot_id') or ''):match('%S+')
        local s=previous and previous.boot_id==boot and previous or {boot_id=boot,restarts={},restart_count=0}
        s.state='config_error';s.checked_uptime=now;s.enabled=false;s.reason='configuration';s.action=nil;s.resources=nil
        write(run..'/supervision.json',s)
        return {ok=true,state='config_error'}
    end
    local status=decoded(run..'/status.json') or {};local fast=decoded(run..'/fast.json') or {}
    local boot=(read('/proc/sys/kernel/random/boot_id') or ''):match('%S+')
    local start=tonumber(read(run..'/service-start-uptime'))
    if not start or start<0 or start>now then
        start=previous and previous.boot_id==boot and tonumber(previous.first_seen) or now
        if not start or start<0 or start>now then start=now end
    end
    local health=decoded(run..'/worker-health.json') or {}
    local request=decoded(run..'/recovery-hold.json')
    -- Samples can advance while client discovery reads configuration.
    now=up()
    local recovery_expired=read(run..'/recovery-hold.json')~=nil and
        (not request or type(request.queued_uptime)~='number' or request.queued_uptime>now or now-request.queued_uptime>30 or request.generation~=control())
    local s=machine.step(c,previous,{up=now,wall_time=os.time(),boot_id=boot,recovery_expired=recovery_expired,
        started=start,stopped=read(run..'/stopped')~=nil,main_updated=health.updated_uptime,
        fast_updated=fast.updated_uptime,runtime_errors=health.errors,probe_budget=c.probe_budget,lease_seconds=c.lease_seconds})
    s.first_seen=start
    if c.resource_monitor then s.resources=resources(previous and previous.resources,now) else s.resources=nil end
    if s.action=='restart' then
        local generation=control()
        if not generation or #generation>64 then s.state='control_error';s.action=nil
        else
            write(run..'/recovery-hold.json',{generation=generation,queued_uptime=now,reason=s.reason})
            write(run..'/supervision.json',s)
            event(c,s,'插件心跳异常，已保持保护并排队重新启动本插件')
            os.execute('/etc/init.d/proxy-guard recover_config '..core.quote(generation)..' >/dev/null 2>&1 </dev/null &')
            return {ok=true,state=s.state}
        end
    elseif s.last_restart_result=='recovered' and previous and previous.last_restart_result=='queued' then event(c,s,'插件检测进程已恢复响应')
    elseif s.state=='limited' and (not previous or previous.state~='limited') then event(c,s,'自动恢复已达到次数上限，保持现有保护并等待冷却') end
    write(run..'/supervision.json',s)
    return {ok=true,state=s.state}
end
return M
