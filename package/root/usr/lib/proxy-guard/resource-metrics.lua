-- CPU accounting uses all online logical processors as 100% of the system.
local M={}
local function finite(n) return type(n)=='number' and n>=0 and n<math.huge end
function M.cpu_snapshot(text)
    if type(text)~='string' then return nil end
    local line=text:match('^cpu%s+([^\n]+)');if not line then return nil end
    local fields={};for word in line:gmatch('%S+') do
        if not word:match('^%d+$') then return nil end
        fields[#fields+1]=tonumber(word)
    end
    if #fields<8 then return nil end
    local ticks=0
    -- guest and guest_nice (fields 9/10) are already included in user/nice.
    for i=1,8 do if not finite(fields[i]) then return nil end;ticks=ticks+fields[i] end
    local cores=0;for _ in text:gmatch('\ncpu%d+%s') do cores=cores+1 end
    if cores<1 then return nil end
    return ticks,cores
end
function M.cpu_usage(previous,current)
    if type(previous)~='table' or type(current)~='table' or
        previous.cpu_basis~='all_online_cpus' or current.cpu_basis~='all_online_cpus' or
        type(current.identity)~='string' or previous.identity~=current.identity or
        not finite(current.cpu_cores) or current.cpu_cores<1 or previous.cpu_cores~=current.cpu_cores then return nil end
    for _,key in ipairs({'sample_uptime','cpu_ticks','system_ticks'}) do
        if not finite(previous[key]) or not finite(current[key]) then return nil end
    end
    local elapsed=current.sample_uptime-previous.sample_uptime
    local total=current.system_ticks-previous.system_ticks;local used=current.cpu_ticks-previous.cpu_ticks
    if elapsed<=0 or total<=0 or used<0 then return nil end
    local fraction=math.min(1,used/total)
    return math.floor(fraction*1000+0.5)/10,math.floor(fraction*current.cpu_cores*1000+0.5)/10
end
return M
