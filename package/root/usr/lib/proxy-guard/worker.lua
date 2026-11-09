local core=require 'proxy-guard.core'
local cf_event=require 'proxy-guard.cf-event'
local json=require 'luci.jsonc'
local uci=require 'uci'
local clients=require 'proxy-guard.clients'
local M={}
local run='/var/run/proxy-guard'
local status_path=run..'/status.json'
local cf_event_path=run..'/cf-event.json'
local cf_event_url='https://www.cloudflare.com/cdn-cgi/trace'
local log_path=run..'/events.jsonl'
local policy_path=run..'/firewall.json'
local removing_path=run..'/removing'
local bootstrap_path='/etc/proxy-guard/fw4-guard.nft'
local function control_generation()
    return (function() local f=io.open(run..'/control-generation','r');if not f then return 'initial' end;local v=f:read('*l');f:close();return v or 'initial' end)()
end

local function read(path)
    local f=io.open(path,'r'); if not f then return nil end
    local s=f:read('*a'); f:close(); return s
end

local function write(path,content)
    local f=assert(io.open(path..'.new','w')); assert(f:write(content)); assert(f:close())
    assert(os.rename(path..'.new',path))
end

local function command(cmd)
    local f=assert(io.popen('('..cmd..') 2>&1; printf "\\n__PG_EXIT:%s\\n" "$?"','r'))
    local out=f:read('*a') or ''; f:close()
    local rc=tonumber(out:match('\n__PG_EXIT:(%d+)\n$')) or 255
    return rc,(out:gsub('\n__PG_EXIT:%d+\n$',''))
end
M.command=command

local function now()
    return math.floor(tonumber((read('/proc/uptime') or ''):match('^[%d%.]+')) or 0)
end

local function fingerprint(value)
    if type(value)~='table' then return type(value)..':'..tostring(value) end
    local keys={}; for k in pairs(value) do keys[#keys+1]=k end
    table.sort(keys,function(a,b) return tostring(a)<tostring(b) end)
    local out={}
    for _,k in ipairs(keys) do out[#out+1]=fingerprint(k)..'='..fingerprint(value[k]) end
    return '{'..table.concat(out,';')..'}'
end

local function config()
    local cursor=uci.cursor()
    local raw=cursor:get_all('proxy_guard','main')
    local c=core.load_config(raw)
    if c.passwall_watch then
        c._client_profile=clients.resolve(c.proxy_client)
        local ok,previous=pcall(json.parse,read(status_path) or '')
        clients.bind(c,c._client_profile,ok and type(previous)=='table' and previous.client or nil)
    elseif c.enabled then
        -- Authentication belongs to the selected SOCKS listener, independently
        -- of whether lifecycle/service monitoring is enabled.
        clients.bind_auth(c,clients.resolve(c.proxy_client))
    end
    return c
end

local function decoded(path)
    local ok,s=pcall(json.parse,read(path) or '')
    return ok and type(s)=='table' and s or nil
end
local function saved() return decoded(status_path) end
local function cf_saved()
    local boot=(read('/proc/sys/kernel/random/boot_id') or ''):match('^[%x%-]+') or 'unknown'
    return cf_event.load(decoded(cf_event_path),boot)
end
local function cf_save(state)
    local value=json.stringify(state)
    if read(cf_event_path)~=value then write(cf_event_path,value) end
end

function M.devices(c,allow_pending)
    local result={}
    -- br_netfilter rewrites PACKET_OTHERHOST to PACKET_HOST before inet hooks.
    -- In that unsupported mode retain MAC-scoped blocking, never classify
    -- other-gateway L2 transit using its rewritten packet type.
    local bridge_filter=false
    for _,family in ipairs({'iptables','ip6tables'}) do
        if tonumber(read('/proc/sys/net/bridge/bridge-nf-call-'..family) or '')==1 then bridge_filter=true end
    end
    for _,iface in ipairs(c.interfaces) do
        local path='/sys/class/net/'..iface..'/'
        local kind=tonumber(read(path..'type') or '')
        local flags=tonumber(read(path..'flags') or '')
        if allow_pending and not (kind and flags) then
            result[iface]={pending=true}
        else
            assert(kind and flags,'入口设备不存在：'..iface)
            assert(allow_pending or flags%2==1,'入口设备尚未启用：'..iface)
            assert(not read(path..'brport/port_no'),'请选择网桥设备，不能选择交换端口：'..iface)
            assert(kind==1 or kind==65534,'不支持的入口设备类型：'..iface)
            local d={kind=kind,index=tonumber(read(path..'ifindex') or '')}
            if allow_pending and flags%2==0 then
                -- A newly created bridge can change its MAC when netifd adds
                -- the first port. Keep the name-based policy until it is up.
                d.pending=true
            elseif kind==1 then
                d.mac=(read(path..'address') or ''):match('^([%x:]+)')
                assert(d.mac and d.mac:match('^%x%x:%x%x:%x%x:%x%x:%x%x:%x%x$') and d.mac~='00:00:00:00:00:00','入口设备 MAC 无效：'..iface)
                if bridge_filter then d.bridge_filter_mac=d.mac end
            end
            result[iface]=d
        end
    end
    return result
end

local function policy_stamp(c,devices)
    local ingress={}
    for name,d in pairs(devices) do ingress[name]={kind=d.kind,index=d.index,pending=d.pending,bridge_filter_mac=d.bridge_filter_mac} end
    local policy={version=core.VERSION,devices=ingress}
    for k,v in pairs(c) do
        -- Log verbosity/rotation has no effect on connectivity or health.
        if not tostring(k):match('^_') and k~='debug' and k~='log_kib' and k~='resource_monitor' and not tostring(k):match('^self_heal') then policy[k]=v end
    end
    return fingerprint(policy)
end

local function event(c,level,kind,message)
    -- Frequent check details must never rotate away protection events.
    local path=level=='debug' and run..'/checks.jsonl' or log_path
    local line=json.stringify({time=os.time(),level=level,event=kind,message=message})..'\n'
    local f=io.open(path,'r')
    local size=f and f:seek('end') or 0
    if f then f:close() end
    if size+#line>(c and c.log_kib or 64)*1024 then assert(os.rename(path,path..'.1')) end
    f=assert(io.open(path,'a'))
    assert(f:write(line)); assert(f:close())
    command('logger -t proxy-guard -p daemon.'..(level=='debug' and 'debug' or level=='error' and 'err' or 'notice')..' -- '..core.quote(message))
end

local function stable(value)
    if type(value)~='table' then return value end
    local out={}
    for k,v in pairs(value) do
        if k=='counter' then out[k]={}
        elseif k~='handle' then out[k]=stable(v) end
    end
    return out
end

local function table_state(stamp)
    local rc,text=command('TZ=UTC0 nft -j list table inet proxy_guard')
    if rc~=0 then
        local check=command('nft -j list tables')
        return {exists=false,error=check~=0 and '无法读取防火墙规则' or nil,alive={}}
    end
    local data=json.parse(text)
    if type(data)~='table' or type(data.nftables)~='table' then return {exists=true,alive={},error='防火墙返回格式无效'} end
    local alive,service_alive,objects={},{},{sets={},chains={},rules={}}
    local time_alive=true
    local utc=os.date('!%Y-%m-%d %H:%M:%S')
    for _,entry in ipairs(data.nftables) do
        if entry.table then objects.table=stable(entry.table) end
        if entry.chain then objects.chains[entry.chain.name]=stable(entry.chain) end
        if entry.rule then
            local name=entry.rule.chain
            objects.rules[name]=objects.rules[name] or {}
            table.insert(objects.rules[name],stable(entry.rule))
        end
        local s=entry.set
        if s then
            local item=stable(s)
            if s.name=='healthy_ifaces' or s.name=='healthy_times' or s.name=='service_ifaces' then item.elem=nil
            elseif item.elem then table.sort(item.elem,function(a,b) return fingerprint(a)<fingerprint(b) end) end
            objects.sets[s.name]=item
        end
        if s and s.name=='healthy_ifaces' then
            for _,item in ipairs(s.elem or {}) do
                local element=type(item)=='table' and (item.elem or item) or {val=item}
                if element.val and (element.expires==nil or element.expires>0) then alive[element.val]=true end
            end
        end
        if s and s.name=='service_ifaces' then
            for _,item in ipairs(s.elem or {}) do
                local element=type(item)=='table' and (item.elem or item) or {val=item}
                if element.val and (element.expires==nil or element.expires>0) then service_alive[element.val]=true end
            end
        end
        if s and s.name=='healthy_times' then
            time_alive=false
            for _,element in ipairs(s.elem or {}) do
                local range=type(element)=='table' and element.range
                if type(range)=='table' and #range==2 then
                    if type(range[1])=='number' and type(range[2])=='number' then
                        time_alive=os.time()>=range[1] and os.time()<range[2]
                    elseif type(range[1])=='string' and type(range[2])=='string' and
                        range[1]:match('^%d%d%d%d%-%d%d%-%d%d %d%d:%d%d:%d%d$') and
                        range[2]:match('^%d%d%d%d%-%d%d%-%d%d %d%d:%d%d:%d%d$') then
                        time_alive=utc>=range[1] and utc<range[2]
                    end
                end
                if time_alive then break end
            end
        end
    end
    -- Compare every installed set, ordered rule expression and hook, excluding
    -- only kernel-assigned handles, counters and the deliberately dynamic lease.
    -- The baseline is captured immediately after our atomic installation and
    -- tied to the validated config, actual devices and plugin version.
    local signature=fingerprint(objects)
    local expected=decoded(policy_path)
    local complete=expected and expected.signature==signature and (not stamp or expected.stamp==stamp)
    return {exists=true,complete=not not complete,alive=alive,service_alive=service_alive,time_alive=time_alive,signature=signature}
end

local function apply_nft(script)
    write(run..'/transaction.nft',script)
    local rc,out=command('TZ=UTC0 nft -c -f '..core.quote(run..'/transaction.nft'))
    if rc==0 then rc,out=command('TZ=UTC0 nft -f '..core.quote(run..'/transaction.nft')) end
    os.remove(run..'/transaction.nft')
    return rc==0,out
end

local function policy_transaction(mode,script,bootstrap)
    write(run..'/transaction.nft',script or '')
    if bootstrap then write(run..'/fw4-next.nft',bootstrap) end
    local rc,out=command('ucode /usr/lib/proxy-guard/firewall-sync.uc '..core.quote(mode))
    os.remove(run..'/transaction.nft'); os.remove(run..'/fw4-next.nft')
    assert(rc==0,out~='' and out or '无法同步系统防火墙保护规则')
end

local function persist_policy(c,devices)
    local script=core.bootstrap(c,devices)
    if read(bootstrap_path)~=script then policy_transaction('persist','',script) end
end

local function update_guard_present()
    return read(run..'/update-guard.active')~=nil or command('nft list table inet proxy_guard_update >/dev/null 2>&1')==0
end

local function remove_policy(exists)
    if exists or read(bootstrap_path) or update_guard_present() then policy_transaction('disable',exists and 'delete table inet proxy_guard\n' or '') end
end

local function install_policy(c,devices,stamp)
    local definition=core.rules(c,devices)
    -- Commit this independent, empty-permit guard before rewriting live hooks.
    local guard=definition:gsub('inet proxy_guard([ %{%s])','inet proxy_guard_update%1')
    write(run..'/update-guard.nft',guard)
    local previous=decoded(policy_path)
    local current=table_state()
    local known_schema=previous and type(previous.stamp)=='string' and
        (previous.stamp:match('string:version=string:0%.1%.1[678]}$') or previous.stamp:match('string:version=string:0%.2%.0}$'))
    if known_schema and current.complete then
        -- These known schemas use the same owned base hooks and set types.
        -- Keep hooks registered while atomically replacing their rules/sets.
        -- Deleting and recreating base hooks exposed routed packets during a
        -- real pending-to-ready cold-boot transition, despite one nft batch.
        local bootstrap=core.bootstrap(c,devices)
        local revoke='flush set inet proxy_guard healthy_ifaces\n'
        if c.passwall_watch then revoke=revoke..'flush set inet proxy_guard service_ifaces\n' end
        if c.schedule_enabled then revoke=revoke..'flush set inet proxy_guard healthy_times\n' end
        policy_transaction('install',bootstrap..revoke,bootstrap)
    else
        -- Unknown or damaged tables cannot be accepted as a trusted baseline.
        policy_transaction('install',definition,core.bootstrap(c,devices))
    end
    local actual=table_state()
    assert(actual.exists and actual.signature,actual.error or '无法核验刚安装的规则')
    write(policy_path,json.stringify({stamp=stamp,signature=actual.signature,definition=definition}))
end

local function compatibility(detailed)
    local rows={};local failure
    local function add(code,ok,why)
        rows[#rows+1]={code=code,level=ok and 'ok' or 'error',detail=not ok and why or nil}
        if not ok and not failure then failure=why end
    end
    local cursor=uci.cursor();local offload=false
    local enabled={['1']=true,on=true,['true']=true,yes=true}
    cursor:foreach('firewall','defaults',function(s)
        if enabled[s.flow_offloading] or enabled[s.flow_offloading_hw] then offload=true end
    end)
    add('configured_offload',not offload,'当前启用了流量卸载，无法保证阻断已有连接；插件不会擅自修改系统设置')
    if failure and not detailed then return false,failure end
    local rc,text=command('nft -j list flowtables');local ok,data=pcall(json.parse,text)
    local verified=rc==0 and ok and type(data)=='table' and type(data.nftables)=='table'
    local active=false
    if verified then for _,entry in ipairs(data.nftables) do if entry.flowtable then active=true end end end
    add('running_offload',verified and not active,not verified and '无法核验运行中的流量卸载状态' or '运行中的防火墙仍存在 nft flowtable，无法保证阻断已有连接；请先核对并停用流量卸载')
    if failure and not detailed then return false,failure end
    local bridged=false
    for _,family in ipairs({'iptables','ip6tables'}) do
        if tonumber(read('/proc/sys/net/bridge/bridge-nf-call-'..family) or '0')==1 then bridged=true end
    end
    add('bridge_filtering',not bridged,'桥接流量进入 IP 防火墙，可能影响交换功能；暂不启用阻断')
    return failure==nil,failure,rows
end

local function publish(c,s)
    s.version=core.VERSION; s.enabled=c.enabled; s.mode=c.mode
    s.updated_at=os.time(); s.updated_uptime=now()
    s.lease_seconds=c.lease_seconds
    s.probe_budget=c.timeout*(#c.targets+1+(c.cf_event_check and 1 or 0))+(c.udp_check and c.udp_timeout or 0)
    s.cf_event=cf_event.status(cf_saved(),c.cf_event_check)
    s.interfaces=c.interfaces; s.sources4=c.sources4; s.sources6=c.sources6
    s.schedule=core.schedule(c,os.time())
    local profile=c._client_profile
    if c.passwall_watch and not profile then profile=clients.resolve(c.proxy_client) end
    local dns_mode=profile and profile.dns_mode or 'dnsmasq'
    local ports={};for i,v in ipairs(c.proxy_ports or {}) do ports[i]=v end
    local installed={};for i,v in ipairs(profile and profile.installed or {}) do installed[i]=v end
    local dns_ports={};for i,port in ipairs(c.dns_ports) do dns_ports[i]=port end
    s.client=profile and {name=profile.client,requested=profile.requested,available=profile.available,
        error=profile.error,socks_port=c.socks_port,detected_socks_port=profile.socks_port,proxy_ports=ports,dns_ports=dns_ports,installed=installed} or nil
    -- luci.jsonc treats a second reference to the same Lua table as a cycle
    -- and serializes it as null. Keep the two published interface lists separate.
    local fast_interfaces={}
    for i,iface in ipairs(c.interfaces) do fast_interfaces[i]=iface end
    s.fast_config={enabled=c.passwall_watch or s.remote_health and s.remote_health.required or s.fast_watch and s.fast_watch.enabled and s.fast_watch.phase~='normal' or false,services_watch=c.passwall_watch,mode=c.mode,interfaces=fast_interfaces,
        trigger_any=c.passwall_trigger=='any',
        boot_guard=c.boot_guard and c.passwall_watch,
        log_watch=c.passwall_log_watch,log_interval=c.passwall_log_interval,
        dns_mode=dns_mode,client_profile=profile,
        wait_enabled=c.fast_wait_enabled,wait_seconds=c.fast_wait_seconds,
        stable_enabled=c.fast_stable_enabled,stable_seconds=c.fast_stable_seconds,
        interval=c.interval,probe_freshness=c.lease_seconds,log_kib=c.log_kib}
    write(status_path,json.stringify(s))
end

local function fast_state(c,stamp)
    local f=decoded(run..'/fast.json')
    if f and f.stamp==stamp and f.updated_uptime and now()-f.updated_uptime<=4 then return f end
    return nil
end

local function sync_fast(c,s,stamp)
    local f=fast_state(c,stamp)
    if f and f.holding and (f.trip~=s.fast_trip or f.generation~=s.fast_generation) then
        s.fast_trip=f.trip; s.fast_generation=f.generation; s.successes=0; s.failures=0; s.next_probe=now()
        s.blocked=c.mode=='guard'; s.phase=s.blocked and 'blocked' or 'down'
        s.reason='本地代理服务保护等待中'
        if c.mode=='guard' then assert(apply_nft(core.lease(c,false))) end
    end
    return f
end

local function reset_fault(s,why,blocked)
    s.phase='error'; s.reason=tostring(why); s.blocked=blocked
    s.successes=0; s.failures=0; s.next_probe=now()
    s.updated_at=os.time(); s.updated_uptime=now()
end

local function check_lease(c,s,fw)
    if s.blocked then return end
    -- The kernel intentionally withdraws the permit at a scheduled boundary.
    -- sync_schedule records that planned block; it is not a health failure.
    if c.schedule_enabled and c.mode=='guard' and core.schedule(c,os.time()).active then return end
    for _,iface in ipairs(c.interfaces) do
        if not fw.alive[iface] or c.schedule_enabled and fw.time_alive==false then
            s.phase='blocked'; s.blocked=true; s.successes=0; s.next_probe=now()
            event(c,'error','lease_expired','健康许可已过期，外网已阻断，重新确认代理状态')
            return
        end
    end
end

local function sync_schedule(c,s)
    if not c.schedule_enabled or c.mode~='guard' then return false end
    local wall,up=os.time(),now()
    local schedule=core.schedule(c,wall)
    local changed=s.schedule_cycle and s.schedule_cycle~=schedule.last_start
    local jumped=s.schedule_wall and math.abs((wall-s.schedule_wall)-(up-s.schedule_uptime))>2
    local hold=schedule.active or not schedule.clock_valid
    local leaving=s.schedule_waiting and not hold
    s.schedule_cycle=schedule.last_start; s.schedule_wall=wall; s.schedule_uptime=up
    if c.passwall_watch and (leaving or changed) and not hold and not jumped then
        s.schedule_waiting=false; s.schedule_release=(s.schedule_release or 0)+1
        local fast=fast_state(c,s.config_stamp)
        if fast and (fast.must_wait or fast.log_pending or fast.phase=='log_wait' or
            fast.holding and fast.log_recovery) then
            -- The planned window ending cannot satisfy a separate real fault
            -- or reset its consecutive-recovery counter to an allowed state.
            s.blocked=true; s.phase='blocked'; s.successes=0; s.failures=0; s.next_probe=up
            s.reason='定时保护已结束，仍等待本轮故障恢复'
            assert(apply_nft(core.lease(c,false,wall)))
            event(c,'info','schedule',s.reason)
            return true
        end
        s.blocked=false; s.phase='healthy'; s.successes=0; s.failures=0; s.next_probe=up
        s.last_probe_ok=nil
        s.reason='定时保护结束，已放行并进入敏感观察，不执行故障等待'
        assert(apply_nft(core.lease(c,true,wall)))
        event(c,'info','schedule',s.reason)
        return true
    end
    if hold or changed or jumped or leaving then
        local old=s.phase
        s.blocked=true; s.successes=0; s.failures=0; s.next_probe=up
        s.schedule_waiting=hold
        if not schedule.clock_valid then
            s.phase='error'; s.reason='系统时间尚未有效，无法确认定时窗口；保持外网阻断'
        elseif schedule.active then
            s.phase='scheduled'; s.reason='定时保护窗口 '..c.schedule_start..'–'..c.schedule_end..'（'..schedule.timezone..'），局域网和 DNS 保留'
        else
            s.phase='recovering'; s.reason=jumped and '系统时间发生跳变，重新确认代理状态' or '定时窗口已结束，重新累计代理恢复次数'
        end
        assert(apply_nft(core.lease(c,false)))
        if old~=s.phase or changed or jumped then event(c,'info','schedule',s.reason) end
        return true
    end
    return false
end

function M.tick(force)
    -- Uninstall marks this before stopping procd. Queued reloads/ticks must not
    -- recreate the table after cleanup, even when the UCI file is unreadable.
    if read(removing_path)~=nil then return false end
    local ok,c=pcall(config)
    local previous=saved()
    local generation=control_generation()
    if not ok then
        if table_state().exists then apply_nft('flush set inet proxy_guard healthy_ifaces\n') end
        local old_reason=previous and previous.reason
        local s=previous or {}; reset_fault(s,c,true)
        if old_reason~=s.reason then event(nil,'error','config_error',s.reason) end
        write(status_path,json.stringify(s)); return false
    end
    local devices={}
    if c.enabled and c.mode=='guard' then
        local valid,result=pcall(M.devices,c)
        if not valid then
            -- At S18 netifd has not created br-lan yet. Name-based nft
            -- matches can be installed now; waiting for the next daemon tick
            -- would allow the first routed packets through without a policy.
            local pending_ok,pending=pcall(M.devices,c,true)
            local compatible=compatibility()
            if pending_ok and compatible then
                local pending_stamp=policy_stamp(c,pending)
                local fw=table_state(pending_stamp)
                assert(not fw.error,fw.error)
                if not fw.complete or update_guard_present() then install_policy(c,pending,pending_stamp)
                else persist_policy(c,pending); assert(apply_nft('flush set inet proxy_guard healthy_ifaces\n')) end
            elseif table_state().exists then
                assert(apply_nft('flush set inet proxy_guard healthy_ifaces\n'))
            end
            local s=previous or core.initial(c,now())
            if pending_ok and compatible then
                local reason='等待局域网接口就绪'
                if s.phase~='waiting_interface' then event(c,'info','interface_wait',reason) end
                reset_fault(s,reason,true); s.phase='waiting_interface'
                s.config_stamp=policy_stamp(c,pending)
            else
                if s.reason~=tostring(result) then event(c,'error','interface_error',tostring(result)) end
                reset_fault(s,result,true)
            end
            publish(c,s); return false
        end
        devices=result
    end
    local stamp=policy_stamp(c,devices)
    local changed=not previous or previous.config_stamp~=stamp
    local s=changed and core.initial(c,now()) or previous
    s.config_stamp=stamp
    local fw=table_state(stamp)
    if fw.error then error(fw.error) end
    if not c.enabled or c.mode=='monitor' then
        remove_policy(fw.exists)
        os.remove(policy_path)
        if changed then event(c,'info','mode',c.enabled and '仅监测已开启，不添加阻断规则' or '保护已关闭，已撤销插件自己的阻断规则') end
        s.blocked=false
        if not c.enabled then os.remove(run..'/recovery-hold.json');publish(c,s); return true end
    else
        local compatible,why=compatibility()
        if not compatible then
            -- Existing rules distinguish packets addressed to this gateway from
            -- bridge transit. Migrate an old/damaged table before retaining it;
            -- merely flushing its lease could keep unsafe old bridge rules.
            if fw.exists then
                if changed or not fw.complete then install_policy(c,devices,stamp)
                else assert(apply_nft('flush set inet proxy_guard healthy_ifaces\n')) end
            end
            if s.reason~=why then event(c,'error','incompatible',why) end
            reset_fault(s,why,fw.exists); publish(c,s); return false
        end
        if changed or not fw.exists or not fw.complete or update_guard_present() then
            install_policy(c,devices,stamp)
            s=core.initial(c,now()); s.config_stamp=stamp
            event(c,'info','armed','保护已开启，等待代理就绪；局域网访问继续保留')
        else
            persist_policy(c,devices)
            check_lease(c,s,fw)
        end
    end
    -- A Pro module may require fresh remote service health. It can only
    -- withhold a local permit; it never grants one without local probes.
    local has_remote,remote_module=pcall(require,'proxy-guard.remote')
    local remote_ok,remote=pcall(function()
        if read('/var/run/proxy-guard-access/updating') then
            local package_state=require('proxy-guard.package-state')
            if package_state.in_progress() then return {required=true,ok=false,stale=true,reason='VPS 健康状态不可用'} end
        end
        if has_remote then return remote_module.status() end
        -- A damaged installed Pro module must not silently remove its gate.
        if read('/usr/share/proxy-guard/feature-pro.json') then
            local cursor=require('uci').cursor()
            local loaded=cursor:load('/etc/config/proxy_guard_access')
            if not loaded or cursor:get('proxy_guard_access','main','enabled')==nil or
                cursor:get('proxy_guard_access','main','enabled')=='1' and
                cursor:get('proxy_guard_access','main','health_guard')=='1' then
                return {required=true,ok=false,stale=true,reason='VPS 健康状态不可用'}
            end
        end
        return {required=false}
    end)
    if not remote_ok or type(remote)~='table' then remote={required=true,ok=false,stale=true,reason='VPS 健康状态不可用'} end
    local maintenance=decoded(run..'/maintenance.json')
    if maintenance and type(maintenance.expires_uptime)=='number' and maintenance.expires_uptime>now() then
        remote={required=true,ok=false,reason='远程维护进行中，保持外网保护'}
        s.maintenance={active=true,operation_id=maintenance.operation_id,remaining=maintenance.expires_uptime-now()}
    else
        if maintenance then os.remove(run..'/maintenance.json') end
        s.maintenance=nil
    end
    s.remote_health=remote
    if remote.required and not remote.ok then
        if c.mode=='guard' then assert(apply_nft(core.lease(c,false))) end
        reset_fault(s,remote.reason,c.mode=='guard')
        s.phase=c.mode=='guard' and 'blocked' or 'down';s.remote_fault=true;s.next_probe=now()+1
        publish(c,s);return true
    elseif s.remote_fault then
        s.remote_fault=nil;s.successes=0;s.next_probe=0;s.last_probe=0;s.phase='recovering'
    end
    if read(run..'/recovery-hold.json') then
        if c.mode=='guard' then assert(apply_nft(core.lease(c,false))) end
        reset_fault(s,'插件自动恢复中，等待新的代理验证',c.mode=='guard');publish(c,s);return true
    end
    if sync_schedule(c,s) then publish(c,s); return true end
    local fast=sync_fast(c,s,stamp)
    local cf_state=cf_saved()
    if c.cf_event_check then
        cf_event.observe(cf_state,{fault_id=fast and fast.cf_event_id,
            primary_fault=s.primary_probe_ok==false and (s.phase=='blocked' or s.phase=='down'),
            recovered=(s.phase=='healthy' or s.phase=='suspect') and (not fast or not fast.holding)})
        cf_save(cf_state)
    end
    if c.passwall_watch and s.schedule_release and
        (not fast or fast.schedule_release~=s.schedule_release) then publish(c,s); return true end
    if c.passwall_watch and c.boot_guard and (not fast or fast.phase=='boot_wait') then publish(c,s); return true end
    if fast and (fast.phase=='log_wait' or fast.log_pending or
        fast.phase=='delay' and now()<(fast.delay_until or 0)) then publish(c,s); return true end
    local probe_config=c
    if fast and fast.phase~='normal' then
        probe_config={}; for k,v in pairs(c) do probe_config[k]=v end
        probe_config.interval=math.min(c.interval,fast.interval or c.interval)
        s.next_probe=math.min(s.next_probe or 0,(s.last_probe or 0)+probe_config.interval)
    end
    if force or now()<math.max(s.next_probe or 0,core.startup_deadline(c)) then publish(c,s); return true end
    local probe_started=now()
    local probe_clock=os.clock()
    local probe_trip=fast and fast.trip or 0
    local probe_generation=fast and fast.generation
    local strict_probe=fast and (fast.phase=='sensitive' or fast.phase=='ramp')
    local successes=0; local results={}
    local reused
    for index,target in ipairs(c.targets) do
        local body_path=(core.is_trace_url(target.url) or target.url==c.exit_url) and (run..'/target-response-'..index) or nil
        if body_path then os.remove(body_path) end
        local rc,out=command(core.probe_command(c,target,body_path))
        local code,seconds=out:match('(%d%d%d)%s+([%d%.]+)%s*$')
        local body=body_path and (read(body_path) or '') or ''
        if body_path then os.remove(body_path) end
        local trace=core.is_trace_url(target.url) and core.trace(body) or nil
        local good=rc==0 and tonumber(code)==target.code and (not core.is_trace_url(target.url) or trace~=nil)
        if good then successes=successes+1 end
        local result={host=target.host,ok=good,curl_code=rc,http_code=tonumber(code) or 0,milliseconds=math.floor((tonumber(seconds) or 0)*1000)}
        if trace then result.observed=trace.ip; result.colo=trace.colo end
        results[#results+1]=result
        if target.url==c.exit_url then reused={rc=rc,code=tonumber(code) or 0,body=body} end
        if strict_probe and not good then break end
    end
    local exit_rc,exit_code,exit_body=1,0,''
    if c.exit_check and (not strict_probe or successes==#c.targets) then
        if reused then exit_rc,exit_code,exit_body=reused.rc,reused.code,reused.body
        else
            local exit_path=run..'/exit-response'
            os.remove(exit_path)
            local exit_out
            exit_rc,exit_out=command(core.probe_command(c,{url=c.exit_url},exit_path))
            exit_code=tonumber(exit_out:match('(%d%d%d)%s+[%d%.]+%s*$')) or 0
            exit_body=read(exit_path) or ''
            os.remove(exit_path)
        end
    end
    local exit_value=core.exit_response(c.exit_url,exit_body)
    local exit_ok=not c.exit_check or exit_rc==0 and exit_code==200 and exit_value~=nil and exit_value.ip==c.expected_exit4
    if c.mode=='guard' then
        -- Probes can outlive a permit or an external rules/config change.
        -- Never renew based solely on the snapshot from before the probes.
        local current_ok,current=pcall(config)
        local device_ok,current_devices=false,nil
        if current_ok then device_ok,current_devices=pcall(M.devices,current) end
        if not current_ok or not device_ok or policy_stamp(current,current_devices)~=stamp then
            -- A concurrent save or interface change cancels this old probe; it
            -- is not a crashed worker and must not spend the restart budget.
            -- Keep real nft/I/O errors exceptional rather than hiding them.
            assert(apply_nft(core.lease(c,false)))
            reset_fault(s,'检测期间配置或入口设备已变化，等待重新核验',true)
            publish(c,s);return true
        end
        local compatible,why=compatibility()
        assert(compatible,why)
        local latest=table_state(stamp)
        assert(not latest.error and latest.exists and latest.complete,latest.error or '检测期间保护规则已变化，等待重新核验')
        check_lease(c,s,latest)
        -- A round spanning a window or clock adjustment is not evidence of
        -- recovery after that window, even when its HTTP requests succeeded.
        if sync_schedule(c,s) then publish(c,s); return true end
    end
    local old_phase=s.phase
    local latest_fast=sync_fast(c,s,stamp)
    if latest_fast and latest_fast.holding and
        (latest_fast.trip~=probe_trip or latest_fast.generation~=probe_generation or latest_fast.phase=='delay' or
         latest_fast.phase=='boot_wait' or latest_fast.phase=='log_wait' or latest_fast.log_pending or
         probe_started<(latest_fast.probe_after or 0)) then
        publish(c,s); return true
    end
    if generation~=control_generation() or read(run..'/recovery-hold.json') or read(run..'/stopped') then
        if c.mode=='guard' then assert(apply_nft(core.lease(c,false))) end
        reset_fault(s,'检测轮次已取消，保持阻断并等待重新验证',c.mode=='guard');publish(c,s);return true
    end
    local udp_result={enabled=c.udp_check}
    if c.udp_check then
        udp_result=strict_probe and successes~=#c.targets and {enabled=true,ok=false,code='http_failed'} or require('proxy-guard.udp').probe(c)
    end
    local primary_ok=successes>=(strict_probe and #c.targets or c.min_success) and exit_ok and (not c.udp_check or udp_result.ok)
    local cf_attempted,cf_mismatch=false,false
    if c.cf_event_check and primary_ok and cf_event.pending(cf_state) then
        -- Reserve the single attempt durably in RAM before curl. A killed
        -- process must not cause an unbounded retry burst on its restart.
        cf_event.begin(cf_state,os.time(),c.expected_exit4);cf_save(cf_state)
        cf_attempted=true
        local path=run..'/cf-event-response';os.remove(path)
        local rc,out=command(core.probe_command(c,{url=cf_event_url},path))
        local code=tonumber(out:match('(%d%d%d)%s+[%d%.]+%s*$')) or 0
        local trace=rc==0 and code==200 and core.trace(read(path) or '') or nil
        os.remove(path)
        cf_mismatch=trace~=nil and trace.ip~=c.expected_exit4
        local outcome=cf_mismatch and 'mismatch' or trace and 'ok' or 'unavailable'
        cf_event.finish(cf_state,{outcome=outcome,observed=trace and trace.ip,
            colo=trace and trace.colo,http_code=code,curl_code=rc},os.time(),c.recover_threshold)
        cf_save(cf_state)
        event(c,cf_mismatch and 'error' or 'info','cf_event',
            'CF 事件核验: '..outcome..', HTTP='..code..', curl='..rc..', IP='..(trace and trace.ip or ''))
    end
    -- UDP and the auxiliary CF I/O can outlive a permit/configuration.
    if generation~=control_generation() or read(run..'/recovery-hold.json') or read(run..'/stopped') then
        if c.mode=='guard' then assert(apply_nft(core.lease(c,false))) end
        reset_fault(s,'检测轮次已取消，保持阻断并等待重新验证',c.mode=='guard');publish(c,s);return true
    end
    if (c.udp_check or cf_attempted) and c.enabled and c.mode=='guard' then
        local latest_ok,latest_config=pcall(config)
        local device_valid,latest_devices=false,nil
        if latest_ok then device_valid,latest_devices=pcall(M.devices,latest_config) end
        if not latest_ok or not device_valid or policy_stamp(latest_config,latest_devices)~=stamp then
            assert(apply_nft(core.lease(c,false)));reset_fault(s,'检测期间配置或入口设备已变化，等待重新核验',true);publish(c,s);return true
        end
        local latest=table_state(stamp);local compatible,why=compatibility()
        if not compatible or not latest.complete then
            assert(apply_nft(core.lease(c,false)));reset_fault(s,why or '检测期间保护规则已变化，等待重新核验',true);publish(c,s);return true
        end
        check_lease(c,s,latest)
        if sync_schedule(c,s) then publish(c,s);return true end
    end
    latest_fast=sync_fast(c,s,stamp)
    if latest_fast and latest_fast.holding and
        (latest_fast.trip~=probe_trip or latest_fast.generation~=probe_generation or
         latest_fast.phase=='delay' or latest_fast.phase=='boot_wait' or latest_fast.phase=='log_wait' or
         latest_fast.log_pending or probe_started<(latest_fast.probe_after or 0)) then
        publish(c,s);return true
    end
    s.udp_probe=udp_result
    s.probe_cpu_ms=math.floor((os.clock()-probe_clock)*1000)
    s.primary_probe_ok=primary_ok
    -- A contradictory CF response cannot be overridden by the ipify result
    -- obtained before it. Require fresh subsequent primary confirmations.
    local cf_allowed=not c.cf_event_check or (not cf_mismatch and cf_event.qualify(cf_state,primary_ok))
    if c.cf_event_check then cf_save(cf_state) end
    s.last_probe_ok=primary_ok and cf_allowed
    s.probe_started=probe_started
    -- Sensitive observation fails on the first failed round, even though the
    -- normal failure threshold remains unchanged outside that phase.
    if (strict_probe and not s.last_probe_ok) or not cf_allowed then s.failures=c.fail_threshold-1 end
    s=core.step(probe_config,s,s.last_probe_ok,now())
    if c.cf_event_check then
        -- Record a confirmed network outage in the same locked transaction.
        -- A configuration apply before the next tick must not erase this event.
        cf_event.observe(cf_state,{primary_fault=not primary_ok and (s.phase=='blocked' or s.phase=='down')})
        cf_save(cf_state)
    end
    s.probes=results
    s.last_probe_at=os.time()
    s.exit_check={enabled=c.exit_check,ok=c.exit_check and exit_ok or nil,expected=c.exit_check and c.expected_exit4 or '',observed=exit_value and exit_value.ip or '',colo=exit_value and exit_value.colo or nil,curl_code=exit_rc,http_code=exit_code}
    if c.exit_check and not exit_ok then s.reason='代理出口验证失败：出口不符或验证服务不可达' end
    if not cf_allowed then s.reason='CF 出口核验不一致，等待新的出口验证确认' end
    if c.mode=='guard' then
        local script,allowed=core.lease(c,not s.blocked,os.time())
        if not s.blocked and not allowed then
            s.blocked=true; s.successes=0; s.phase='scheduled'
            s.reason='进入定时保护窗口，等待窗口结束后重新检测'; s.schedule_waiting=true
        end
        local applied,why=apply_nft(script)
        if not applied then error(why) end
    end
    if old_phase~=s.phase then
        local reason=s.reason
        if s.phase=='healthy' and latest_fast and latest_fast.holding then
            reason='代理探测已通过，等待快速保护确认放行'
        end
        event(c,s.phase=='blocked' and 'error' or 'info',s.phase,reason..(c.mode=='monitor' and '（仅监测，未阻断）' or ''))
    end
    if c.debug or old_phase~=s.phase then
        local detail={}
        for _,r in ipairs(results) do detail[#detail+1]=r.host..': curl='..r.curl_code..', HTTP='..r.http_code..', '..r.milliseconds..'ms' end
        if c.exit_check then
        detail[#detail+1]='出口验证: '..(exit_ok and '成功' or '失败')..', curl='..exit_rc..', HTTP='..exit_code..', IP='..s.exit_check.observed
        end
        event(c,c.debug and 'debug' or 'info','probe',table.concat(detail,'; '))
    end
    publish(c,s)
    return true
end

M.compatibility=compatibility

function M.status()
    local previous=saved()
    local s=previous or {phase='unavailable',reason='运行状态缺失，等待检测服务重新核验'}
    local config_ok,c=pcall(config)
    if config_ok and not c.exit_check then s.exit_check={enabled=false} end
    local device_ok,devices=true,{}
    if config_ok and c.enabled and c.mode=='guard' then device_ok,devices=pcall(M.devices,c) end
    local pending=false
    if config_ok and c.enabled and c.mode=='guard' and not device_ok then
        local good,value=pcall(M.devices,c,true)
        if good then pending=true; devices=value end
    end
    local stamp=config_ok and (device_ok or pending) and policy_stamp(c,devices) or nil
    local applied=previous and previous.config_stamp==stamp
    s.interfaces_ready=not pending
    s.config_stamp=nil
    s.fast_config=nil
    local fw=table_state(stamp)
    -- A fresh, deliberately disabled install has no daemon or saved status.
    -- Only report it as disabled when the owned firewall table is also absent.
    if config_ok and not c.enabled and not fw.error and not fw.exists and not update_guard_present() then
        return {version=core.VERSION,phase='disabled',reason='插件未启用',enforcement='off',firewall_present=false,stale=false,exit_check={enabled=c.exit_check},supervision=decoded(run..'/supervision.json')}
    end
    s.firewall_present=fw.exists
    s.stale=type(s.updated_uptime)~='number' or s.updated_uptime>now()+2 or now()-s.updated_uptime>math.max(15,(tonumber(s.probe_budget) or 0)+10)
    if fw.error then s.enforcement='unknown'; s.firewall_error=fw.error
    elseif not config_ok or not device_ok then s.enforcement='unverified'; s.firewall_error=pending and (fw.complete and applied and '等待局域网接口就绪' or '规则、配置或运行状态尚未核验一致') or tostring(config_ok and devices or c)
    elseif fw.exists and (not fw.complete or not applied) then s.enforcement='unverified'; s.firewall_error='规则、配置或运行状态尚未核验一致'
    elseif not fw.exists then s.enforcement=(c.enabled and c.mode=='guard') and 'missing' or 'off'
    else
        local all=true
        for _,iface in ipairs(c.interfaces) do
            if not fw.alive[iface] or c.passwall_watch and not (fw.service_alive or {})[iface] then all=false end
        end
        s.enforcement=all and (not c.schedule_enabled or fw.time_alive~=false) and 'allowing' or 'blocked'
    end
    if config_ok and (not c.enabled or not c.exit_check) then s.exit_check={enabled=false} end
    if config_ok then
        if c.enabled and c.passwall_watch then
            local fast=fast_state(c,stamp)
            if fast then
                s.fast_watch={enabled=true,phase=fast.phase,tcp=fast.tcp,udp=fast.udp,dns=fast.dns,client=fast.client,required=fast.required,
                    boot_pending=fast.boot_pending,log_watch=fast.log_watch,
                    wait_remaining=math.max(0,(fast.delay_until or 0)-now()),
                    stable_elapsed=fast.stable_elapsed,stable_required=fast.stable_required,
                    holding=fast.holding,stale=fast.stale,gate_ok=fast.gate_ok,episode=fast.episode}
                if c.mode=='guard' and fast.gate_ok==false then
                    s.enforcement='unverified'; s.firewall_error='快速检查无法更新防火墙许可'
                end
                if device_ok and c.mode=='guard' and fw.complete and applied and s.enforcement=='blocked' then
                    if fast.phase=='log_wait' or fast.log_pending then s.phase='blocked'; s.reason='等待客户端本轮启动及已配置服务恢复'
                    elseif fast.phase=='boot_wait' then s.phase='blocked'; s.reason='开机保护等待 TCP、UDP、DNS 全部运行'
                    elseif fast.phase=='delay' then s.phase='blocked'; s.reason='本地代理服务保护等待中'
                    elseif fast.holding then s.phase='recovering'; s.reason='正在敏感检测，等待代理验证通过' end
                end
            else
                s.fast_watch={enabled=true,stale=true}
                if c.mode=='guard' and s.enforcement=='blocked' then
                    s.phase='blocked'; s.reason='快速检查尚未就绪，保持外网阻断'
                end
            end
        end
        s.schedule=core.schedule(c,os.time())
        if c.enabled and c.mode=='guard' and c.schedule_enabled and fw.complete and applied and device_ok then
            if not s.schedule.clock_valid then
                s.enforcement='unverified'; s.firewall_error='系统时间尚未有效，保持外网阻断'
            elseif s.schedule.active then
                s.enforcement='blocked'; s.phase='scheduled'; s.successes=0
                s.reason='定时保护窗口 '..c.schedule_start..'–'..c.schedule_end..'（'..s.schedule.timezone..'），局域网和 DNS 保留'
            elseif c.schedule_enabled and fw.time_alive==false and (s.phase=='healthy' or s.phase=='suspect' or s.phase=='scheduled') then
                s.phase='recovering'; s.successes=0; s.reason='放行许可已到期，等待重新确认代理状态'
            end
        end
    end
    if config_ok and c.enabled and c.mode=='guard' then
        local compatible,why=compatibility()
        if not compatible then s.enforcement='unverified'; s.firewall_error=why end
    end
    if update_guard_present() then
        s.enforcement='unverified';s.firewall_error='规则、配置或运行状态尚未核验一致'
    end
    if s.phase=='error' then s.enforcement='unverified' end
    -- RPC consumers must see the combined kernel gates, not just the slower
    -- network worker's internal blocked flag while fast protection is holding.
    if s.enforcement=='blocked' then s.blocked=true
    elseif s.enforcement=='allowing' or s.enforcement=='off' then s.blocked=false
    else s.blocked=nil end
    s.interface_waiting=pending and fw.complete and not not applied and s.firewall_error=='等待局域网接口就绪' or false
    s.supervision=decoded(run..'/supervision.json')
    if config_ok and c.enabled and c.self_heal then
        if not s.supervision then s.supervision={state='unavailable',enabled=true,stale=true}
        else s.supervision.stale=type(s.supervision.checked_uptime)~='number' or s.supervision.checked_uptime>now()+2 or now()-s.supervision.checked_uptime>20 end
    end
    return s
end

function M.logs()
    local all,skipped={},0
    for _,path in ipairs({log_path..'.1',log_path,run..'/fast-events.jsonl.1',run..'/fast-events.jsonl',run..'/checks.jsonl.1',run..'/checks.jsonl',run..'/supervision-events.jsonl.1',run..'/supervision-events.jsonl'}) do
        for line in (read(path) or ''):gmatch('[^\n]+') do
            local good,item=pcall(json.parse,line)
            if good and type(item)=='table' and type(item.time)=='number' and item.time>=0 and item.time<math.huge
                and type(item.message)=='string' and type(item.level)=='string' and type(item.event)=='string' then
                item._order=#all+1; all[#all+1]=item
            else skipped=skipped+1 end
        end
    end
    table.sort(all,function(a,b) return a.time==b.time and a._order<b._order or a.time<b.time end)
    local events,details={},{}
    for _,item in ipairs(all) do
        item._order=nil
        local target=(item.level=='debug' or item.event=='probe') and details or events
        target[#target+1]=item
    end
    local function tail(items,limit)
        local result={}; for i=math.max(1,#items-limit+1),#items do result[#result+1]=items[i] end
        return result
    end
    return {entries=tail(events,200),details=tail(details,100),skipped=skipped,incidents=require('proxy-guard.incidents').group(all)}
end

function M.clear_logs()
    os.remove(log_path..'.1'); write(log_path,'')
    os.remove(run..'/checks.jsonl.1'); os.remove(run..'/checks.jsonl')
    os.remove(run..'/fast-events.jsonl.1'); os.remove(run..'/fast-events.jsonl')
    os.remove(run..'/supervision-events.jsonl.1');os.remove(run..'/supervision-events.jsonl')
    event(nil,'info','log_clear','用户清空插件日志')
    return {ok=true}
end

function M.cleanup()
    assert(read(removing_path)~=nil,'仅允许在卸载流程中清理规则')
    local fw=table_state()
    assert(not fw.error,fw.error)
    remove_policy(fw.exists)
    os.remove('/etc/proxy-guard')
    fw=table_state()
    assert(not fw.error and not fw.exists,fw.error or '插件规则未清理完成')
    os.remove(policy_path)
    os.remove(status_path)
    os.remove(cf_event_path); os.remove(cf_event_path..'.new')
    os.remove(run..'/update-guard.nft');os.remove(run..'/update-guard.nft.new')
    os.remove(run..'/cf-event-response'); os.remove(run..'/cf-event-response.new')
    os.remove(run..'/fast.json')
    os.remove(run..'/fast-poll')
    os.remove(run..'/fast-transaction.nft')
    for _,name in ipairs({'supervision.json','worker-health.json','recovery-hold.json','service-start-uptime','daemon.pid','fast_watch.pid','supervisor.pid','maintenance.json'}) do os.remove(run..'/'..name) end
    return {ok=true}
end

function M.stop()
    local ok,c=pcall(config)
    if ok and (not c.enabled or c.mode=='monitor') then
        remove_policy(table_state().exists)
    elseif table_state().exists then
        assert(apply_nft('flush set inet proxy_guard healthy_ifaces\n'))
    end
    local s=saved()
    if s then
        s.successes=0; s.failures=0; s.next_probe=now(); s.blocked=ok and c.enabled and c.mode=='guard'
        s.phase=s.blocked and 'blocked' or s.phase
        s.reason='检测服务已停止'; write(status_path,json.stringify(s))
    end
    event(ok and c or nil,'info','service_stop','检测服务停止；保护模式保留阻断，关闭保护请使用总开关')
end

function M.fail(message)
    -- Never remove the guard on an internal error. A running permission expires in kernel.
    if table_state().exists then apply_nft('flush set inet proxy_guard healthy_ifaces\n') end
    local s=saved() or {}
    local old_reason=s.reason
    reset_fault(s,tostring(message):sub(1,500),true)
    write(status_path,json.stringify(s))
    if old_reason~=s.reason then event(nil,'error','internal_error',s.reason) end
end

function M.maintenance()
    assert(not read(removing_path) and not read(run..'/stopped'),'local_protection_not_ready')
    local generation=control_generation()
    local c=config()
    local job=decoded('/var/run/proxy-guard-access/pending/job.json')
    assert(job and (job.action=='restart_xray' or job.action=='reboot_vps') and type(job.operation_id)=='string' and #job.operation_id==36,'invalid_maintenance_request')
    assert(type(job.created_uptime)=='number' and type(job.timeout)=='number' and job.timeout>=30 and job.timeout<=600 and now()-job.created_uptime<job.timeout,'expired_maintenance_request')
    if not c.enabled or c.mode~='guard' then return {ok=true,protection_required=false} end
    local devices=M.devices(c,true)
    if not table_state().exists then assert(apply_nft(core.rules(c,devices))) end
    write(run..'/maintenance.json',json.stringify({operation_id=job.operation_id,expires_uptime=job.created_uptime+job.timeout}))
    assert(apply_nft(core.lease(c,false)))
    local s=saved() or core.initial(c,now())
    reset_fault(s,'远程维护进行中，保持外网保护',true)
    s.phase='blocked';s.remote_fault=true;s.remote_health={required=true,ok=false,reason=s.reason}
    s.maintenance={active=true,operation_id=job.operation_id,remaining=job.created_uptime+job.timeout-now()}
    assert(generation==control_generation() and not read(removing_path),'local_protection_not_ready')
    publish(c,s);event(c,'info','maintenance','远程维护前已启用本地保护，等待重新验证')
    return {ok=true,protection_required=true}
end

return M
