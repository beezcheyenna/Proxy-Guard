local M={}
local json=require 'luci.jsonc'
local uci=require 'uci'
local core=require 'proxy-guard.core'
local run='/var/run/proxy-guard-access'
local lane=arg and arg[1]=='jobs' and 'jobs-' or ''
local headers_path=run..'/'..lane..'headers'
local request_path=run..'/'..lane..'request'
local function read(path,max)
    local f=io.open(path,'r');if not f then return nil end
    local text=f:read(max or 65537);f:close();return text
end
local function decoded(path) local s=read(path);if not s then return nil end;local ok,r=pcall(json.parse,s);return ok and type(r)=='table' and r or nil end
local function write(path,s)
    local f=assert(io.open(path..'.new','w'));assert(f:write(s));assert(f:close());assert(os.rename(path..'.new',path))
end
local function number(v,default,lo,hi)
    v=v or tostring(default);assert(type(v)=='string' and v:match('^%d+$'),'invalid_number')
    local n=tonumber(v);assert(n>=lo and n<=hi,'invalid_number');return n
end
local function flag(v,default)
    if v==nil then return default end
    assert(v=='0' or v=='1','invalid_flag');return v=='1'
end
local function list(v)
    if v==nil then return {} end
    assert(type(v)=='table','invalid_list');return v
end
function M.sections()
    local c=uci.cursor();assert(c:load('/etc/config/proxy_guard_access'),'config_unavailable')
    local result={}
    c:foreach('proxy_guard_access',nil,function(s) result[s['.name']]=s end)
    return result
end
function M.load(sections)
    local s=sections.main or {}
    local c={enabled=flag(s.enabled,false)}
    if not c.enabled then return c end
    c.policy_enabled=flag(s.policy_enabled,true)
    c.policy_confirm=flag(s.policy_confirm,true);c.policy_confirm_seconds=number(s.policy_confirm_seconds,60,30,300)
    -- Deprecated settings must never expand protection to unrelated ports.
    c.default_deny=false
    c.auto_discover=false
    c.mode=s.protection_mode or 'standard';assert(c.mode=='standard' or c.mode=='whitelist' or c.mode=='observe','invalid_protection_mode')
    c.ssh={managed=flag(s.ssh_managed,false),confirmed=flag(s.ssh_confirmed,false),port=number(s.ssh_port,22,1,65535),
        rescue_enabled=flag(s.ssh_rescue,true),after=number(s.ssh_after,60,10,3600),scope=s.ssh_scope or 'public',
        open_seconds=number(s.ssh_open_seconds,0,0,3600),managers=list(s.ssh_managers)}
    assert(c.ssh.open_seconds==0 or c.ssh.open_seconds>=30,'invalid_ssh_policy')
    assert(c.ssh.scope=='public' or c.ssh.scope=='restricted','invalid_ssh_policy')
    assert(#c.ssh.managers<=32,'invalid_management_sources')
    for _,v in ipairs(c.ssh.managers) do assert(type(v)=='string' and (core.cidr(v,4) or core.cidr(v,6)) and not v:match('/0$'),'invalid_management_sources') end
    c.path_watch=flag(s.path_watch,false);c.path_endpoint=s.path_endpoint or ''
    c.path_interval=number(s.path_interval,10,5,60)
    c.path_token=s.path_token
    if not c.path_token or c.path_token=='' then c.path_token=read('/etc/proxy-guard-access/path.key',257) or '' end
    c.allow_restart=flag(s.allow_restart,false);c.allow_reboot=flag(s.allow_reboot,false)
    c.maintenance_timeout=number(s.maintenance_timeout,180,30,600)
    local function endpoint(value)
        local address,port6=value:match('^https://%[([%x:]+)%]:(%d+)/*$')
        if not address then address=value:match('^https://%[([%x:]+)%]/*$') end
        if address then
            assert(core.cidr(address,6) and (not port6 or tonumber(port6)>=1 and tonumber(port6)<=65535),'invalid_endpoint')
            return 'https://['..address..']'..(port6 and ':'..port6 or '')
        end
        local host,port=value:match('^https://([A-Za-z0-9%.%-]+):(%d+)/*$')
        if not host then host=value:match('^https://([A-Za-z0-9%.%-]+)/*$') end
        if port then assert(tonumber(port)>=1 and tonumber(port)<=65535,'invalid_endpoint') end
        assert(host and #host<=253 and host:match('^[A-Za-z0-9]') and host:match('[A-Za-z0-9]$') and not host:find('..',1,true),'invalid_endpoint')
        return 'https://'..host..(port and (':'..port) or '')
    end
    c.endpoint=endpoint(s.endpoint or '')
    if c.path_watch then
        c.path_endpoint=endpoint(c.path_endpoint)
        assert(type(c.path_token)=='string' and #c.path_token>=32 and #c.path_token<=256 and c.path_token:match('^[A-Za-z0-9_-]+$') and not c.path_token:match('^REPLACE_'),'invalid_path_token')
    end
    assert(not c.ssh.managed or c.path_watch,'ssh_requires_independent_path')
    c.transport=s.transport or 'cloudflare'
    assert(c.transport=='cloudflare' or c.transport=='direct','invalid_transport')
    assert(not c.path_watch or c.transport~='cloudflare' or c.path_endpoint~=c.endpoint,'ssh_requires_independent_path')
    c.health_interval=number(s.health_interval,10,5,60)
    c.health_guard=flag(s.health_guard,false)
    c.device_id=s.device_id or ''
    assert(c.device_id:match('^[A-Za-z0-9_-]+$') and #c.device_id<=64,'invalid_device_id')
    c.device_token=s.device_token
    if not c.device_token or c.device_token=='' then c.device_token=read('/etc/proxy-guard-access/device.key',257) or '' end
    assert(#c.device_token>=32 and #c.device_token<=256 and c.device_token:match('^[A-Za-z0-9_-]+$') and not c.device_token:match('^REPLACE_'),'invalid_device_token')
    assert(flag(s.direct_confirmed,false),'direct_confirmation_required')
    c.family=s.family or 'ipv4';assert(c.family=='ipv4' or c.family=='ipv6' or c.family=='both','invalid_family')
    c.address_families=c.family=='both' and {4,6} or {c.family=='ipv6' and 6 or 4}
    c.interval=number(s.interval,300,60,3600);c.ttl=number(s.ttl,900,120,86400)
    assert(c.ttl>=c.interval*2,'lease_too_short')
    c.timeout=number(s.timeout,8,2,15);c.revision=number(s.revision,1,1,9007199254740991)
    assert(not c.ssh.managed or not c.ssh.rescue_enabled or c.ssh.after>=2*math.max(c.health_interval,c.path_interval)+c.timeout,'ssh_timeout_too_short')
    c.rules={};local used={tcp={},udp={}};local names={};for name,r in pairs(sections) do if r['.type']=='rule' then names[#names+1]=name end end
    table.sort(names);assert(#names<=32,'too_many_rules')
    for _,name in ipairs(names) do
        local r=sections[name]
        assert(#name<=32 and name:match('^[A-Za-z0-9_-]+$'),'invalid_rule')
        local rule={id=name,name=r.name or name,enabled=flag(r.enabled,true),protocol=r.protocol or 'tcp',
            ports=list(r.ports),mode=r.protection_mode or 'inherit',source_mode=r.source_mode or 'dynamic',sources=list(r.sources),
            limits={rate_enabled=flag(r.rate_enabled,true),rate=number(r.rate,40,1,10000),burst=number(r.burst,80,1,20000),
                connections_enabled=flag(r.connections_enabled,true),connections=number(r.connections,128,1,10000),
                bandwidth_enabled=flag(r.bandwidth_enabled,false),bandwidth=number(r.bandwidth,1048576,1024,1073741824),
                sustain=number(r.sustain,10,1,300),cooldown=number(r.cooldown,30,1,3600),window=number(r.window,60,5,600)}}
        assert(rule.limits.burst>=rule.limits.rate,'burst_below_rate')
        assert(type(rule.name)=='string' and #rule.name>=1 and #rule.name<=64 and not rule.name:find('[%z\1-\31]'),'invalid_rule')
        assert(rule.mode=='inherit' or rule.mode=='standard' or rule.mode=='whitelist' or rule.mode=='observe','invalid_rule_mode')
        if rule.mode~='inherit' then c.requires_rule_modes=true end
        assert(rule.protocol=='tcp' or rule.protocol=='udp' or rule.protocol=='both','invalid_protocol')
        assert(rule.source_mode=='any' or rule.source_mode=='all' or rule.source_mode=='dynamic' or rule.source_mode=='static' or rule.source_mode=='mixed','invalid_source_mode')
        if rule.source_mode=='all' then c.requires_source_modes=true end
        assert(not(rule.enabled and rule.source_mode=='all' and (rule.mode=='inherit' and c.mode or rule.mode)=='whitelist'),'whitelist_requires_authorized_sources')
        assert(#rule.ports>=1 and #rule.ports<=32,'invalid_ports')
        local spans={}
        for _,port in ipairs(rule.ports) do
            assert(type(port)=='string','invalid_ports')
            local a,b=port:match('^(%d+)%-(%d+)$');if not a then a=port:match('^%d+$');b=a end
            a,b=tonumber(a),tonumber(b);assert(a and a>=1 and a<=b and b<=65535,'invalid_ports')
            for _,old in ipairs(spans) do assert(a>old[2] or b<old[1],'overlapping_ports') end
            spans[#spans+1]={a,b}
        end
        assert(#rule.sources<=64,'invalid_sources')
        for _,source in ipairs(rule.sources) do
            assert(type(source)=='string' and #source<=64 and (core.cidr(source,4) or core.cidr(source,6)),'invalid_sources')
        end
        if rule.enabled and rule.source_mode=='static' then assert(#rule.sources>0,'empty_static_whitelist') end
        if rule.enabled then
            if c.ssh.managed and rule.protocol~='udp' then
                for _,span in ipairs(spans) do assert(c.ssh.port<span[1] or c.ssh.port>span[2],'ssh_port_overlaps_service') end
            end
            for _,proto in ipairs(rule.protocol=='both' and {'tcp','udp'} or {rule.protocol}) do
                for _,span in ipairs(spans) do
                    for _,old in ipairs(used[proto]) do assert(span[1]>old[2] or span[2]<old[1],'overlapping_rules') end
                    used[proto][#used[proto]+1]=span
                end
            end
        end
        c.rules[#c.rules+1]=rule
    end
    assert(#json.stringify(c.rules)+#json.stringify(c.ssh)<=22000,'policy_too_large')
    return c
end
-- Read endpoint and both credentials as one local snapshot. The lock is
-- released before HTTPS; an in-flight request may only use a consistent pair.
function M.load_current()
 local trial=require 'proxy-guard.access-trial'
 return trial.locked(function()
  assert(not (read(run..'/installing')or read(run..'/updating'))and not read('/var/run/proxy-guard/removing'),'apply_busy')
  local p=trial.pending()
  assert(not p or(p.phase~='preparing'and p.phase~='restoring'),'policy_trial_busy')
  return M.load(M.sections())
 end)
end
function M.recover_trial()
 if (read(run..'/installing')or read(run..'/updating'))or read('/var/run/proxy-guard/removing')then return false end
 local trial=require 'proxy-guard.access-trial'
 local ok,p=pcall(trial.pending)
 if not ok then
  local rows=M.sections();if rows.main and rows.main.enabled=='0'then trial.stop();return true end
  error(p)
 end
 if not p then return trial.recover_preparing()end
 if p.phase=='preparing'then return trial.recover_preparing()end
 if p.phase=='restoring'then trial.restore(p.restore_reason or'interrupted_restore',p.restore_remote);return true end
 local rows=M.sections();if rows.main and rows.main.enabled=='0'then trial.stop()end
 return true
end
function M.confirms(c,response)
    if type(response)~='table' or response.protocol~=3 then return false end
    local policy=response.policy or response.ingress
    if type(policy)~='table' or policy.mode~=c.mode or policy.enabled~=c.policy_enabled or policy.default_deny~=c.default_deny or policy.auto_discover~=c.auto_discover then return false end
    if type(policy.ssh)~='table' then return false end
    for _,key in ipairs({'managed','confirmed','port','rescue_enabled','after','scope','open_seconds'}) do if policy.ssh[key]~=c.ssh[key] then return false end end
    if c.requires_source_modes or policy.source_modes_v2==true then
        if policy.source_modes_v2~=true or type(policy.rule_effects)~='table' then return false end
        local wanted={};local count=0
        for _,r in ipairs(c.rules or {})do
            local mode=(r.mode or 'inherit')=='inherit'and c.mode or r.mode
            wanted[r.id]=not r.enabled and 'disabled'or mode~='observe'and r.source_mode=='any'and'bypass'or mode;count=count+1
        end
        local actual=0;for id,effect in pairs(policy.rule_effects)do if wanted[id]~=effect then return false end;actual=actual+1 end
        if actual~=count then return false end
    end
    if c.requires_rule_modes or policy.per_rule_modes==true then
        if policy.per_rule_modes~=true or type(policy.rule_modes)~='table' then return false end
        local wanted={};local count=0
        for _,r in ipairs(c.rules or {}) do wanted[r.id]=(r.mode or 'inherit')=='inherit' and c.mode or r.mode;count=count+1 end
        local actual=0;for id,mode in pairs(policy.rule_modes) do if wanted[id]~=mode then return false end;actual=actual+1 end
        if actual~=count then return false end
    end
    if type(policy.address_families)~='table' or #policy.address_families~=#c.address_families then return false end
    for index,family in ipairs(c.address_families) do if policy.address_families[index]~=family then return false end end
    return true
end
local function execute(s)
    local f=assert(io.popen(s..' 2>/dev/null','r'));local text=f:read(128);local ok=f:close()
    return ok,text
end
local function generation() return read(run..'/generation',100) or '' end
local function uptime() return tonumber((read('/proc/uptime',100) or ''):match('^[%d%.]+')) or 0 end
local function still_current(g,revision)
    if read(run..'/stopped') or generation()~=g then return false end
    local ok,c=pcall(M.load_current)
    return ok and c.enabled and c.revision==revision
end
local function request(c,family,path,body,via_proxy)
    local header_file=c._request_dir and c._request_dir..'headers' or headers_path
    local request_file=c._request_dir and c._request_dir..'request' or request_path
    local response=(c._request_dir or (run..'/'..lane))..'response-'..family
    os.remove(response)
    local proxy=''
    local proxy_auth=''
    if via_proxy then
        local cursor=uci.cursor();cursor:load('/etc/config/proxy_guard')
        local raw=cursor:get_all('proxy_guard','main') or {}
        local port=number(raw.socks_port,1070,1,65535)
        if raw.passwall_watch=='1' then
            local clients=require 'proxy-guard.clients'
            local profile=clients.resolve(raw.proxy_client or 'passwall')
            if raw.client_auto_ports=='1' then assert(profile.available and profile.socks_port,'client_adapter_unavailable') end
            local binding={client_auto_ports=raw.client_auto_ports=='1',socks_port=port,proxy_ports={}}
            clients.bind(binding,profile);port=binding.socks_port
            if binding._socks_curl_file then
                core.proxy_options(binding) -- Validate the private path before constructing curl arguments.
                proxy_auth=' --config '..core.quote(binding._socks_curl_file)
            end
        else
            local clients=require 'proxy-guard.clients'
            local binding={socks_port=port}
            clients.bind_auth(binding,clients.resolve(raw.proxy_client or 'auto'))
            if binding._socks_curl_file then
                core.proxy_options(binding)
                proxy_auth=' --config '..core.quote(binding._socks_curl_file)
            end
        end
        proxy='socks5h://127.0.0.1:'..port
    end
    local command='curl -q --silent --proto =https --max-redirs 0 --retry 0 --proxy '..core.quote(proxy)..
        proxy_auth..' --noproxy '..core.quote(via_proxy and '' or '*')..' --connect-timeout '..math.min(5,c.timeout)..' --max-time '..c.timeout..
        ' --max-filesize 32768 -'..family..' --header '..core.quote('@'..header_file)..
        ' --output '..core.quote(response)
    if body then write(request_file,json.stringify(body));command=command..' --header '..core.quote('Content-Type: application/json')..
        ' --data-binary '..core.quote('@'..request_file) end
    local _,output=execute(command..' --write-out '..core.quote('%{http_code}')..' '..core.quote((via_proxy and c.path_endpoint or c.endpoint)..path)..[[; printf ':%s' "$?"]])
    local http,code=output:match('^(%d%d%d):(%d+)$');local text=read(response)
    os.remove(response);os.remove(request_file)
    assert(tonumber(code)==0 and text and #text<=32768,'https_failed')
    local parsed,data=pcall(json.parse,text);assert(parsed and type(data)=='table','invalid_worker_response')
    if tonumber(http)<200 or tonumber(http)>=300 or data.ok~=true then
        local allowed={operation_busy=true,operation_cooldown=true,expired_operation=true,xui_usr1_not_confirmed=true}
        if data.code=='operation_or_authentication_denied' then error('remote_operation_denied') end
        error(allowed[data.code] and data.code or 'invalid_worker_response')
    end

    return data
end
-- One explicit read-only request, isolated from heartbeat/maintenance files.
local function egress_connection()
    local all=M.sections();assert(type(all.main)=='table','configuration_error')
    local main={enabled='1'}
    -- Connection-only loader: unrelated port/SSH policies cannot block a read.
    for _,key in ipairs({'endpoint','transport','device_id','direct_confirmed','device_token','timeout','revision'}) do main[key]=all.main[key] end
    return M.load({main=main})
end
function M.fetch_egress()
    local c=egress_connection()
    local private=run..'/egress/'
    assert(os.execute('umask 077; mkdir -p '..private..'; chmod 700 '..private)==0,'egress_directory_unavailable')
    c._request_dir=private
    write(private..'headers','Authorization: Bearer '..c.device_token..'\n')
    local ok,result=pcall(function()
        local body={device_id=c.device_id}
        -- Do not let Lua's and/or idiom turn direct GET into an empty POST.
        if c.transport=='direct' then body=nil end
        local data=request(c,4,c.transport=='direct' and '/v1/direct/egress-info' or '/v1/egress-info',body)
        assert(data.egress_info_schema==1 and type(data.candidates)=='table' and #data.candidates<=32,'invalid_egress_response')
        assert(type(data.generated_at)=='number' and data.generated_at>0 and data.generated_at<4102444800,'invalid_egress_response')
        local safe={ok=true,generated_at=data.generated_at,candidates={},business_egress_verified=false,ambiguous=data.ambiguous==true,measurement={state='unavailable',stale=true}}
        if type(data.measurement)=='table' then
            safe.measurement.state=({disabled=true,pending=true,fresh=true,stale=true,unavailable=true,conflict=true})[data.measurement.state] and data.measurement.state or 'unavailable'
            safe.measurement.stale=data.measurement.stale~=false
        end
        for _,row in ipairs(data.candidates) do
            assert(type(row)=='table' and type(row.ipv4)=='string' and core.cidr(row.ipv4,4) and not row.ipv4:find('/',1,true),'invalid_egress_response')
            assert(type(row.evidence)=='table' and #row.evidence>=1 and #row.evidence<=8,'invalid_egress_response')
            local entry={ipv4=row.ipv4,evidence={}}
            for _,e in ipairs(row.evidence) do
                assert(type(e)=='table' and ({interface=true,panel=true,measured=true})[e.source],'invalid_egress_response')
                assert(type(e.checked_at)=='number' and e.checked_at>0 and e.checked_at<4102444800,'invalid_egress_response')
                if e.source~='measured' or safe.measurement.stale==false then
                    entry.evidence[#entry.evidence+1]={source=e.source,checked_at=e.checked_at}
                end
            end
            if #entry.evidence>0 then safe.candidates[#safe.candidates+1]=entry end
        end
        return safe
    end)
    for _,name in ipairs({'headers','headers.new','request','request.new','response-4'}) do os.remove(private..name) end
    assert(ok,result)
    return result
end

local function egress_identity()
    local c=egress_connection()
    return table.concat({c.endpoint,c.transport,c.device_id,tostring(c.revision),generation()},'\n')
end
function M.egress_info(refresh)
    local identity=egress_identity()
    assert(os.execute('umask 077; mkdir -p '..run..'/egress; chmod 700 '..run..' '..run..'/egress')==0,'egress_directory_unavailable')
    local path=run..'/egress/state.json'
    local state=decoded(path)
    local age=state and state.boot==read('/proc/sys/kernel/random/boot_id',128) and uptime()-(state.started or 0) or math.huge
    if refresh and not (state and state.phase=='pending' and age>=0 and age<45) then
        local id=(read('/proc/sys/kernel/random/uuid',128) or ''):gsub('%s','')
        assert(#id==36,'egress_random_unavailable')
        state={id=id,identity=identity,phase='pending',started=uptime(),boot=read('/proc/sys/kernel/random/boot_id',128)}
        write(path,json.stringify(state))
        -- Base setup watcher dispatches outside this RPC's lock.
        write(run..'/egress-request','1\n')
        age=0
    end
    if not state then return {ok=true,phase='idle'} end
    if state.identity~=identity then return {ok=false,error='egress_connection_changed'} end
    if age<0 or age>=45 and state.phase=='pending' then return {ok=false,error='egress_request_expired'} end
    if state.phase=='ready' then
        if uptime()-(state.finished or 0)>60 then return {ok=false,error='egress_refresh_required'} end
        local data=state.data;assert(type(data)=='table','invalid_egress_response')
        data.phase='ready';return data
    elseif state.phase=='error' then return {ok=false,error=state.error or 'egress_read_failed'} end
    return {ok=true,phase='pending'}
end
function M.collect_egress()
    local path=run..'/egress/state.json'
    local state=decoded(path)
    if not state or state.phase~='pending' then return true end
    local ok,data=pcall(M.fetch_egress)
    local current=decoded(path)
    if not current or current.id~=state.id then return false end
    local current_ok,current_identity=pcall(egress_identity)
    if not current_ok or state.identity~=current_identity then ok=false;data='egress_connection_changed' end
    state.phase=ok and 'ready' or 'error';state.finished=uptime()
    if ok then state.data=data else state.error=tostring(data):match('([a-z_]+)$') or 'egress_read_failed' end
    write(path,json.stringify(state));return ok
end

local function publish(s)
    s.updated_at=os.time();write(run..'/status.json',json.stringify(s))
end
function M.policy_progress()
    if (read(run..'/installing')or read(run..'/updating'))or read('/var/run/proxy-guard/removing')then return false end
    local trial=require 'proxy-guard.access-trial';local pending=trial.pending()
    if not pending then return true end
    if pending.phase=='restoring'then trial.restore(pending.restore_reason or'interrupted_restore',pending.restore_remote);return false end
    if pending.phase=='preparing'then return trial.recover_preparing()end
    if pending.action=='cancel'and not pending.sent then trial.restore('user_cancelled',true);return true end
    local c=M.load_current()
    if not c.enabled then trial.stop();return true end
    local spec,why=trial.spec(c);if why=='restored'then return false end
    if not pending.action then return true end
    local body={device_id=c.device_id,trial_id=pending.id,revision=pending.revision}
    if c.transport=='direct'then body.issued_at=os.time()*1000;body.request_id=(read('/proc/sys/kernel/random/uuid',100)or''):gsub('%s','')end
    write(headers_path,'Authorization: Bearer '..c.device_token..'\n')
    local ok,response=pcall(request,c,c.family=='ipv6'and 6 or 4,(c.transport=='direct'and'/v1/direct/policy-'or'/v1/policy-')..pending.action,body)
    os.remove(headers_path)
    if ok then trial.observe(response)end
    return ok
end
function M.health(force)
    local c=M.load_current()
    if not c.enabled or read(run..'/stopped') then os.remove(run..'/health.json');return true end
    local previous=decoded(run..'/health.json') or {}
    local gen=generation();local up=uptime()
    if not force and not read(run..'/heartbeat-wake') and previous.generation==gen and previous.revision==c.revision and
       up-(previous.checked_uptime or 0)<c.health_interval then return true end
    write(headers_path,'Authorization: Bearer '..c.device_token..'\n')
    local status_body={device_id=c.device_id}
    if c.transport=='direct' then status_body=nil end
    local ok,remote=pcall(request,c,c.family=='ipv6' and 6 or 4,
        c.transport=='direct' and '/v1/direct/status' or '/v1/status',status_body)
    os.remove(headers_path);os.remove(headers_path..'.new')
    if not still_current(gen,c.revision) then return false end
    if ok then local result=require('proxy-guard.access-trial').observe(remote);if result and result.phase~='confirmed'then return false end end
    local service_ok=ok and remote.agent_ready==true and type(remote.health)=='table' and
        remote.health.configured==true and remote.health.ok==true and remote.health.stale~=true
    local revision_ok=ok and remote.revision==c.revision and M.confirms(c,remote)
    local authorization_ok=ok and type(remote.leases)=='table'
    if authorization_ok then
        for _,family in ipairs(c.address_families) do
            local lease=remote.leases[tostring(family)]
            authorization_ok=authorization_ok and type(lease)=='table' and type(lease.expires_in)=='number' and lease.expires_in>=c.health_interval+2
        end
    end
    if revision_ok and not authorization_ok then write(run..'/wake','1\n') end
    local good=service_ok and revision_ok and authorization_ok
    local safe=ok and remote or nil
    write(run..'/health.json',json.stringify({ok=good,remote=safe,checked_at=os.time(),
        checked_uptime=uptime(),generation=gen,revision=c.revision,service_ok=service_ok,revision_ok=revision_ok,authorization_ok=authorization_ok,error=not ok and 'agent_unavailable' or nil}))
    if ok then write(run..'/last-health.json',assert(read(run..'/health.json')))end
    return good
end
function M.once()
    local c=M.load_current()
    if not c.enabled or read(run..'/stopped') then
        publish({enabled=c.enabled,phase=c.enabled and 'stopped' or 'disabled'});return true
    end
    local trial=require 'proxy-guard.access-trial';local spec,restored=trial.spec(c);if restored then return false end
    local previous=decoded(run..'/status.json') or {}
    local gen=generation();local now=os.time();local up=uptime()
    local wake=read(run..'/wake')~=nil
    local forced=previous.generation~=gen or previous.revision~=c.revision
    if not forced and (previous.next_uptime or 0)>up and not (wake and up-(previous.attempted_uptime or 0)>=15) then return true end
    os.remove(run..'/wake')
    local result={enabled=true,phase='syncing',generation=gen,revision=c.revision,attempted_at=now,attempted_uptime=up,addresses=previous.addresses or {}}
    publish(result)
    write(headers_path,'Authorization: Bearer '..c.device_token..'\n')
    local cursor=uci.cursor();cursor:load('/etc/config/proxy_guard')
    local proxy=cursor:get('proxy_guard','main','expected_exit4')
    local ok,why=pcall(function()
        if c.requires_rule_modes or c.requires_source_modes or spec then
            local body=c.transport~='direct' and {device_id=c.device_id} or nil
            local remote=request(c,c.family=='ipv6' and 6 or 4,c.transport=='direct' and '/v1/direct/status' or '/v1/status',body)
            assert(remote.protocol==3 and type(remote.ingress)=='table' and remote.ingress.per_rule_modes==true,'per_rule_modes_unavailable')
            assert(not c.requires_source_modes or remote.ingress.source_modes_v2==true,'source_modes_unavailable')
            assert(not spec or remote.ingress.policy_confirmation==true,'policy_confirmation_unavailable')
        end
        for _,family in ipairs(c.family=='both' and {4,6} or {c.family=='ipv6' and 6 or 4}) do
            assert(still_current(gen,c.revision),'configuration_changed')
            local observed=request(c,family,c.transport=='direct' and '/v1/direct/observe' or '/v1/observe')
            assert(type(observed.observed_ip)=='string' and #observed.observed_ip<=45 and observed.family==family,'invalid_worker_response')
            assert(not proxy or proxy=='' or observed.observed_ip~=proxy,'proxy_egress_detected')
            assert(still_current(gen,c.revision),'configuration_changed')
            local uuid=read('/proc/sys/kernel/random/uuid',100)
            assert(uuid,'random_unavailable')
            if spec then trial.sent()end
            local done=request(c,family,c.transport=='direct' and '/v1/direct/sync' or '/v1/sync',
                {device_id=c.device_id,observed_ip=observed.observed_ip,
                issued_at=os.time()*1000,request_id=uuid:gsub('%s+$',''),
                policy_enabled=c.policy_enabled,mode=c.mode,ssh=c.ssh,default_deny=c.default_deny,auto_discover=c.auto_discover,address_families=c.address_families,revision=c.revision,ttl=c.ttl,rules=c.rules,policy_trial=spec})
            assert(done.protocol==3,'agent_protocol_mismatch')
            assert(M.confirms(c,done),'policy_not_confirmed')
            assert(done.observed_ip==observed.observed_ip and type(done.expires_at)=='number' and type(done.policy_hash)=='string' and #done.policy_hash==64 and done.policy_hash:match('^[a-f0-9]+$'),'invalid_worker_response')
            result.addresses[tostring(family)]={ip=done.observed_ip,expires_at=done.expires_at,applied_at=done.applied_at}
            result.policy_hash=done.policy_hash
            trial.observe(done)
        end
    end)
    os.remove(headers_path);os.remove(headers_path..'.new')
    if not ok and spec and tostring(why):match('policy_confirmation_unavailable')then trial.restore('policy_confirmation_unavailable',true);return false end
    if not still_current(gen,c.revision) then return true end
    if ok then
        local selected={};for _,family in ipairs(c.address_families) do selected[tostring(family)]=true end
        for family in pairs(result.addresses) do if not selected[family] then result.addresses[family]=nil end end
    end
    result.phase=ok and (trial.pending()and'confirming'or'synced') or 'error'
    -- Only fixed diagnostic codes may enter status; never persist secrets/commands.
    result.error=not ok and (tostring(why):match('([a-z_]+)$') or 'sync_failed') or nil
    result.failures=ok and 0 or math.min((previous.failures or 0)+1,6)
    local delay=ok and c.interval or math.min(c.interval,15*2^(result.failures-1))
    result.next_attempt=os.time()+delay;result.next_uptime=uptime()+delay
    publish(result);return ok
end
function M.status(owner)
    local ok,c=pcall(M.load_current)
    if not ok then return {enabled=true,phase='error',error=tostring(c):match('([a-z_]+)$') or 'configuration_error'} end
    local trial_ok,trial_status=pcall(require('proxy-guard.access-trial').public,owner)
    if not trial_ok or type(trial_status)~='table'then return{enabled=c.enabled,phase='error',error='policy_trial_storage_invalid'}end
    if not c.enabled then
        local last=decoded(run..'/status.json')or{}
        return{enabled=false,phase='disabled',last_known=true,addresses=last.addresses,remote_health=decoded(run..'/last-health.json'),policy_trial=trial_status}
    end
    local s=decoded(run..'/status.json') or {enabled=true,phase='waiting'}
    if s.revision~=c.revision or s.generation~=generation() then s.phase='waiting' end
    s.stale=s.phase~='waiting' and s.phase~='stopped' and uptime()>(s.next_uptime or 0)+60
    s.remote_health=decoded(run..'/health.json')
    s.permissions={restart_xray=c.allow_restart,reboot_vps=c.allow_reboot}
    s.path_health=decoded(run..'/path.json');s.operation=decoded(run..'/operation.json');s.preflight=decoded(run..'/preflight.json')
    s.policy_trial=trial_status
    if s.policy_trial.pending and(s.policy_trial.phase=='restoring'or s.policy_trial.phase=='remote_restoring')then s.phase='restoring'end
    if s.phase=='confirming'and not s.policy_trial.pending then s.phase=s.policy_trial.last_result and s.policy_trial.last_result.phase=='confirmed'and'synced'or'error' end
    if read(run..'/stopped')then s.last_known=true;s.remote_health=decoded(run..'/last-health.json')end
    return s
end
function M.save_secret(secret,kind)
    assert(type(secret)=='string' and #secret>=32 and #secret<=256 and secret:match('^[A-Za-z0-9_-]+$'),'invalid_device_token')
    assert(os.execute('umask 077; mkdir -p /etc/proxy-guard-access && chmod 700 /etc/proxy-guard-access')==0,'secret_store_failed')
    assert(kind==nil or kind=='path','invalid_secret_kind')
    local path='/etc/proxy-guard-access/'..(kind=='path' and 'path.key' or 'device.key')
    write(path,secret)
    assert(os.execute('chmod 600 '..path)==0,'secret_store_failed')
end
function M.path(force)
    local c=M.load_current()
    if not c.enabled or not c.path_watch then return true end
    local previous=decoded(run..'/path.json') or {};local up=uptime();local gen=generation()
    if not force and not read(run..'/heartbeat-wake') and previous.generation==gen and up-(previous.checked_uptime or 0)<c.path_interval then return true end
    local fast=decoded('/var/run/proxy-guard/fast.json')
    if not force and fast and (fast.phase=='boot_wait' or fast.phase=='delay' and up<(fast.delay_until or 0)) then return true end
    write(headers_path,'Authorization: Bearer '..c.path_token..'\n')
    local id=(read('/proc/sys/kernel/random/uuid',100) or ''):gsub('%s+$','')
    local ok,result=pcall(request,c,4,'/v1/direct/path-heartbeat',{device_id=c.device_id,channel='proxy',request_id=id,issued_at=os.time()*1000},true)
    os.remove(headers_path)
    if not still_current(gen,c.revision) then return false end
    local good=ok and result.channel=='proxy'
    write(run..'/path.json',json.stringify({ok=good,checked_uptime=uptime(),checked_at=os.time(),generation=gen,error=not good and 'proxy_path_unavailable' or nil}))
    return good
end
function M.queue(action)
    assert(action=='preflight' or action=='restart_xray' or action=='reboot_vps','unsupported_action')
    local c=M.load_current();assert(c.enabled,'synchronization_disabled')
    assert(action=='preflight' or action=='restart_xray' and c.allow_restart or action=='reboot_vps' and c.allow_reboot,'maintenance_not_allowed')
    local fs=require 'nixio.fs'
    assert(fs.mkdir(run..'/pending','700'),'operation_busy')
    local ok,result=pcall(function()
        local id=(read('/proc/sys/kernel/random/uuid',100) or ''):gsub('%s+$','');assert(#id==36,'random_unavailable')
        local value={operation_id=id,action=action,phase='queued',created_at=os.time(),created_uptime=uptime(),revision=c.revision,generation=generation(),timeout=c.maintenance_timeout}
        write(run..'/operation.json',json.stringify(value));write(run..'/pending/job.json',json.stringify(value));return value
    end)
    if not ok then fs.rmdir(run..'/pending');error(result) end
    return result
end
function M.jobs()
    local fs=require 'nixio.fs';local path=run..'/pending/job.json';local job=decoded(path)
    if not job then return true end
    local c=M.load_current();local gen=generation();local up=uptime()
    local function finish(phase,why)
        job.phase=phase;job.error=why;job.updated_at=os.time();write(run..'/operation.json',json.stringify(job))
        os.remove(path);fs.rmdir(run..'/pending');os.remove('/var/run/proxy-guard/maintenance.json')
    end
    if not c.enabled or job.revision~=c.revision or job.generation~=gen then finish('failed','configuration_changed');return false end
    if up-job.created_uptime>job.timeout then finish('failed','recovery_not_verified');return false end
    if job.action=='preflight' then
        write(run..'/heartbeat-wake','1\n')
        local health=decoded(run..'/health.json') or {};local path_health=decoded(run..'/path.json') or {}
        if (health.checked_uptime or 0)>=job.created_uptime and (not c.path_watch or (path_health.checked_uptime or 0)>=job.created_uptime) then
            local good=health.ok and (not c.path_watch or path_health.ok)
            write(run..'/preflight.json',json.stringify({ok=good,checked_at=os.time()}));finish(good and 'complete' or 'failed');return good
        end
        return true
    end
    if job.phase=='queued' then
        assert(job.action=='restart_xray' and c.allow_restart or job.action=='reboot_vps' and c.allow_reboot,'maintenance_not_allowed')
        assert(os.execute('/usr/libexec/proxy-guard maintenance >/dev/null 2>&1')==0,'local_protection_not_ready')
        assert(uptime()-job.created_uptime<job.timeout-2 and still_current(gen,c.revision),'configuration_changed')
        write(headers_path,'Authorization: Bearer '..c.device_token..'\n')
        local now=os.time()*1000;local id=(read('/proc/sys/kernel/random/uuid',100) or ''):gsub('%s+$','')
        local ok,result=pcall(request,c,c.family=='ipv6' and 6 or 4,c.transport=='direct' and '/v1/direct/command' or '/v1/command',
            {device_id=c.device_id,operation_id=job.operation_id,action=job.action,request_id=id,issued_at=now,expires_at=now+30000,revision=c.revision})
        os.remove(headers_path)
        local error_code=not ok and (tostring(result):match('([a-z_]+)$') or 'command_result_unknown') or nil
        if error_code=='remote_operation_denied' or error_code=='operation_busy' or error_code=='operation_cooldown' or error_code=='expired_operation' or error_code=='xui_usr1_not_confirmed' then finish('failed',error_code);return false end
        job.phase=ok and result.operation and result.operation.phase or 'uncertain'
        job.error=not ok and 'command_result_unknown' or nil
        write(path,json.stringify(job));write(run..'/operation.json',json.stringify(job))
    end
    local health=decoded(run..'/health.json') or {};local operations=health.remote and health.remote.maintenance and health.remote.maintenance.operations or {}
    for _,item in ipairs(operations) do
        if item.operation_id==job.operation_id then
            job.phase=item.phase
            if item.phase=='complete' or item.phase=='failed' or item.phase=='indeterminate' then finish(item.phase,item.error);return item.phase=='complete' end
            write(path,json.stringify(job));write(run..'/operation.json',json.stringify(job))
        end
    end
    return true
end
function M.abort_job(code)
    local fs=require 'nixio.fs';local job=decoded(run..'/pending/job.json')
    if job then job.phase='failed';job.error=code;write(run..'/operation.json',json.stringify(job)) end
    os.remove(run..'/pending/job.json');fs.rmdir(run..'/pending');os.remove('/var/run/proxy-guard/maintenance.json')
end
function M.bump()
    local c=uci.cursor();assert(c:load('/etc/config/proxy_guard_access'),'config_unavailable')
    local next=number(c:get('proxy_guard_access','main','revision'),1,1,9007199254740990)+1
    c:set('proxy_guard_access','main','revision',tostring(next));assert(c:commit('proxy_guard_access'));return next
end
return M
