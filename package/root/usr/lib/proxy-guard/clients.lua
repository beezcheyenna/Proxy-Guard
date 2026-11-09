local json=require 'luci.jsonc'
local core=require 'proxy-guard.core'
local M={}
function M.resolve(choice)
    local pipe=io.popen('ucode /usr/lib/proxy-guard/inspect-client.uc '..core.quote(choice or 'auto')..' 2>/dev/null','r')
    local text=pipe and pipe:read(32769) or ''
    if pipe then pipe:close() end
    local ok,value=pcall(json.parse,text)
    if #text>32768 or not ok or type(value)~='table' then
        return {client=choice or 'auto',available=false,error='client_adapter_unavailable',required={tcp=true,udp=true,dns=true}}
    end
    return value
end
function M.bind_auth(c,profile)
    if profile.available and profile.socks_port==c.socks_port then
        c._socks_auth_file=profile.socks_auth_file;c._socks_curl_file=profile.socks_curl_file
    end
    return c
end
function M.bind(c,profile,previous)
    if not c.client_auto_ports then
        return M.bind_auth(c,profile)
    end
    local binding=profile.available and profile or previous or {}
    local socks=tonumber(binding.socks_port)
    if socks and socks>=1 and socks<=65535 and socks==math.floor(socks) then c.socks_port=socks end
    local seen={}
    for _,value in ipairs(c.proxy_ports) do seen[tonumber(value) or value]=true end
    for _,value in ipairs(binding.proxy_ports or {}) do
        local port=tonumber(value)
        if port and port==math.floor(port) and port>=1 and port<=65535 and not seen[port] then
            c.proxy_ports[#c.proxy_ports+1]=port;seen[port]=true
        end
    end
    c.dns_ports=c.dns_ports or {}
    local dns_seen={}
    for _,value in ipairs(c.dns_ports) do dns_seen[tonumber(value) or value]=true end
    for _,value in ipairs(binding.dns_ports or {}) do
        local port=tonumber(value)
        if port and port==math.floor(port) and port>=1 and port<=65535 then
            if seen[port] then
                profile.available=false;profile.error='client_listener_configuration_unavailable'
            elseif not dns_seen[port] then
                c.dns_ports[#c.dns_ports+1]=port;dns_seen[port]=true
            end
        end
    end
    return M.bind_auth(c,profile)
end
return M
