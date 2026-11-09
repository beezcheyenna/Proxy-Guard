-- Group structured events; damaged metadata must not hide intact raw logs.
local M={}
local causes={boot=true,watchdog=true,worker=true,log=true,services=true,interruption=true,schedule=true}
local function number(v) return type(v)=='number' and v>=0 and v<1e12 and v or nil end
local function normalize(e)
    if type(e)~='table' or type(e.id)~='string' or #e.id>=160 or not number(e.started_uptime) then return nil end
    local s={id=e.id,started_at=number(e.started_at),started_uptime=e.started_uptime,
        elapsed=number(e.elapsed) or 0,resets=number(e.resets) or 0,holding=e.holding==true,
        completed_uptime=number(e.completed_uptime),stable_elapsed=number(e.stable_elapsed),stable_required=number(e.stable_required),causes={}}
    if type(e.causes)=='table' then for key in pairs(causes) do if e.causes[key]==true then s.causes[key]=true end end end
    return s
end
function M.group(entries)
    local by_id,out={},{}
    for _,item in ipairs(entries) do
        local e=normalize(item.incident)
        if e then
            local row=by_id[e.id]
            if not row then row={id=e.id,started_at=e.started_at,started_uptime=e.started_uptime,steps={}};by_id[e.id]=row;out[#out+1]=row end
            if not row.summary or e.elapsed>=row.summary.elapsed then row.summary=e end
            if #row.steps<40 then row.steps[#row.steps+1]={time=number(item.time),stage=type(item.stage)=='string' and item.stage or nil,elapsed=e.elapsed} end
        end
    end
    -- A policy/device change can replace an unfinished incident. Its last
    -- historical snapshot must not look like a second live recovery forever.
    -- Do not invent a completion time: explicitly point to the later record.
    for i=1,#out-1 do
        local current=out[i].summary
        if current and not current.completed_uptime then
            for j=i+1,#out do
                local later=out[j].summary
                if later and later.started_uptime>=current.started_uptime then
                    current.superseded=true;break
                end
            end
        end
    end
    local tail={};for i=math.max(1,#out-19),#out do tail[#tail+1]=out[i] end
    return tail
end
return M
