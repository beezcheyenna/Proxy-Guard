-- Read-only validation of a browser draft. No commit, reload or probe traffic.
local core=require 'proxy-guard.core'
local json=require 'luci.jsonc'
local M={}
local function read(path,limit) local f=io.open(path,'r');if not f then return '' end;local s=f:read(limit or '*a');f:close();return s end
function M.check(raw)
    local rows={};local function add(code,level) rows[#rows+1]={code=code,level=level} end
    if type(raw)~='table' then return {ok=false,checks={{code='configuration',level='error'}}} end
    local draft={};for k,v in pairs(raw) do draft[k]=v end
    draft.enabled='1' -- Check whether it could be enabled, even while off.
    local valid,c=pcall(core.load_config,draft)
    if not valid then return {ok=false,checks={{code='configuration',level='error'}},error=tostring(c):sub(1,500)} end
    add('configuration','ok')
    local worker=require 'proxy-guard.worker'
    local devices,why=pcall(worker.devices,c);add('interfaces',devices and 'ok' or 'error');if not devices then rows[#rows].detail=tostring(why):sub(1,500) end
    local compatible,why,details=worker.compatibility(true)
    if type(details)=='table' then for _,row in ipairs(details) do rows[#rows+1]=row end
    else add('compatibility',compatible and 'ok' or 'error');rows[#rows].detail=why end
    -- --check validates a transaction without installing rules or opening access.
    -- The fixed, address-free program exercises the kernel expressions we use.
    local feature_check=[[nft -c -f - >/dev/null 2>&1 <<'PG_FEATURES'
 table inet __proxy_guard_preflight {
  set ifaces { type ifname; flags timeout; timeout 4s; }
  set times { typeof meta time; flags interval; }
  set nets6 { type ipv6_addr; flags interval; }
  chain expressions {
   iifname @ifaces return
   meta time @times return
   ip6 saddr @nets6 return
   meta l4proto { 6, 17 } ct direction reply ct status dnat ct original proto-dst 53 fib saddr type local th sport 53 return
  }
 }
PG_FEATURES
]]
    add('kernel_features',os.execute(feature_check)==0 and 'ok' or 'error')
    if rows[#rows].level=='error' then rows[#rows].detail='无法核验所需的 nftables 内核功能，请检查防火墙和内核模块' end
    local client_profile
    if c.passwall_watch then
        local clients=require 'proxy-guard.clients'
        client_profile=clients.resolve(c.proxy_client)
        clients.bind(c,client_profile)
        local tun=false;local system_tun=false
        for _,checks in pairs(client_profile.checks or {}) do for _,item in ipairs(checks) do
            if item.tun then
                tun=true
                if client_profile.client=='homeproxy' and item.config=='/var/run/homeproxy/sing-box-c.json' then
                    local text=read(item.config,1048577);local good,data=pcall(json.parse,text)
                    if #text<=1048576 and good and type(data)=='table' then
                        for _,inbound in ipairs(data.inbounds or {}) do
                            if inbound.type=='tun' and (inbound.stack==nil or inbound.stack=='system') then system_tun=true end
                        end
                    end
                end
            end
        end end
        -- A stopped/restarting client is an outage to protect against, not a
        -- reason to reject a valid blocking policy. Gates remain closed until
        -- the adapter and configured services become verifiable.
        add('client_mode',client_profile.available and 'ok' or 'warning')
        rows[#rows].detail=client_profile.available and (tun and 'TUN' or 'Redirect / TPROXY') or client_profile.error
        if system_tun then
            local pipe=io.popen('/usr/bin/sing-box version 2>/dev/null','r');local text=pipe and pipe:read(4096) or '';if pipe then pipe:close() end
            local version=text:match('sing%-box version ([%w%.%-%+]+)')
            if version=='1.12.25' then
                add('homeproxy_tun_ipv6_udp','error')
                rows[#rows].detail='此 sing-box 版本已复现 TUN IPv6 UDP 故障；请选择已验证的转发模式或修复后的内核'
            end
        end
    end
    local listening=false;local port=string.format('%04X',c.socks_port)
    for line in read('/proc/net/tcp'):gmatch('[^\n]+') do
        local ip,p,state=line:match('^%s*%d+:%s+(%x+):(%x+)%s+%S+%s+(%x+)')
        if p==port and state=='0A' and (ip=='0100007F' or ip=='00000000') then listening=true end
    end
    add('socks_listener',listening and 'ok' or 'warning')
    local available=require('proxy-guard.udp').available();add('udp_runtime',not c.udp_check and 'off' or available and 'ok' or 'error')
    local services
    if c.passwall_watch then
        local profile=client_profile
        local mode=profile.dns_mode or 'dnsmasq'
        local pipe=io.popen('ucode /usr/lib/proxy-guard/inspect-services.uc '..core.quote(mode)..' '..core.quote(json.stringify(profile))..' 2>/dev/null','r')
        local text=pipe and pipe:read(32769) or '';if pipe then pipe:close() end
        local good,value=pcall(json.parse,text);services=good and type(value)=='table' and value or nil
        local healthy=services and profile.available
        for _,name in ipairs({'tcp','udp','dns'}) do
            if (profile.required or {})[name]~=false and not (services and services[name]) then healthy=false end
        end
        add('passwall_services',healthy and 'ok' or 'warning')
        rows[#rows].client=profile.client;rows[#rows].detail=profile.error

    end
    local broad=false;for _,net in ipairs(c.sources6) do if net=='::/0' then broad=true end end
    if broad then add('ipv6_scope','warning') end
    if #c.sources6==0 then add('ipv6_scope','warning');rows[#rows].detail='IPv6 不在本次保护范围内' end
    if c.schedule_enabled then add('schedule_clock',core.schedule(c,os.time()).clock_valid and 'ok' or 'error') end
    add('topology','warning')
    local ok=true;for _,row in ipairs(rows) do if row.level=='error' then ok=false end end
    return {ok=ok,checks=rows,read_only=true,udp_available=available}
end
return M
