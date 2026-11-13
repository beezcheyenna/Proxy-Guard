-- Pure monotonic-time restart budget. Proxy/configuration failures are not
-- evidence that the monitor itself is broken.
local M={}
function M.step(c,old,o)
    local s={boot_id=o.boot_id,restarts={}}
    if type(old)=='table' and old.boot_id==o.boot_id then for k,v in pairs(old) do s[k]=v end end
    s.failures=tonumber(s.failures) or 0
    s.last_restart=tonumber(s.last_restart)
    if s.last_restart and (s.last_restart<0 or s.last_restart>o.up) then s.last_restart=nil end
    -- A daemon may have run disabled for hours before the user enables it.
    -- Its service-start timestamp is not the start of the new monitor epoch.
    if c.enabled and type(old)=='table' and old.boot_id==o.boot_id and (old.state=='disabled' or old.active_enabled==false or c.passwall_watch and old.watch_enabled==false or c.heartbeat_enabled and not old.heartbeat_enabled) then
        s.activation_started=o.up
    end
    s.active_enabled=c.enabled;s.watch_enabled=c.passwall_watch;s.heartbeat_enabled=c.heartbeat_enabled
    s.checked_uptime=o.up;s.enabled=c.self_heal;s.reason=nil;s.action=nil;s.retry_in=nil
    local kept={}
    for _,t in ipairs(type(s.restarts)=='table' and s.restarts or {}) do if type(t)=='number' and t>=0 and t<=o.up and o.up-t<c.self_heal_window then kept[#kept+1]=t end end
    s.restarts=kept;s.restart_count=#kept;s.restart_limit=c.self_heal_limit
    if not c.enabled then s.state='disabled';s.failures=0;return s end
    if o.stopped then s.state='stopped';s.failures=0;return s end
    if not c.self_heal then s.state='watching';s.failures=0;return s end
    local threshold=math.max(c.self_heal_stale,(o.probe_budget or 0)+10,(o.lease_seconds or 0)+5)
    s.main_threshold=threshold
    local activation=tonumber(s.activation_started)
    if not activation or activation<0 or activation>o.up then activation=0;s.activation_started=nil end
    local started=math.max(o.started or o.up,activation)
    if o.up-started<threshold then s.state='starting';s.failures=0;return s end
    local missing=type(o.main_updated)~='number' or o.main_updated>o.up+2 or o.up-o.main_updated>threshold
    local fast=c.passwall_watch and (type(o.fast_updated)~='number' or o.fast_updated>o.up+2 or o.up-o.fast_updated>c.self_heal_stale)
    local heartbeat=c.heartbeat_enabled and (type(o.heartbeat_updated)~='number' or o.heartbeat_updated>o.up+2 or o.up-o.heartbeat_updated>math.max(c.self_heal_stale,(c.heartbeat_lease or 0)+10) or (tonumber(o.heartbeat_errors) or 0)>=3)
    local runtime=(tonumber(o.runtime_errors) or 0)>=3
    if not missing and not fast and not heartbeat and not runtime and not o.recovery_expired then
        s.state='healthy';s.failures=0
        if s.last_restart_result=='queued' then s.last_restart_result='recovered';s.recovered_uptime=o.up end
        return s
    end
    s.reason=o.recovery_expired and 'recovery_timeout' or runtime and 'execution_errors' or missing and 'main_heartbeat' or fast and 'fast_heartbeat' or 'heartbeat_monitor'
    s.failures=(s.failures or 0)+1
    if s.failures<2 then s.state='suspect';return s end
    local last=s.last_restart or kept[#kept]
    if last and o.up-last<c.self_heal_cooldown then s.state='cooldown';s.retry_in=c.self_heal_cooldown-(o.up-last);return s end
    if #kept>=c.self_heal_limit then s.state='limited';s.retry_in=c.self_heal_window-(o.up-kept[1]);return s end
    kept[#kept+1]=o.up;s.restart_count=#kept;s.last_restart=o.up;s.state='queued';s.action='restart';s.failures=0;s.last_reason=s.reason;s.last_restart_at=o.wall_time;s.last_restart_result='queued'
    return s
end
return M
