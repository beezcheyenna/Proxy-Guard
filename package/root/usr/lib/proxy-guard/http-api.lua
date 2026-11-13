-- SPDX-License-Identifier: MIT
package.path = '/usr/lib/?.lua;' .. package.path
local json = require 'luci.jsonc'
local auth = require 'proxy-guard.api-auth'
local core = require 'proxy-guard.core'
local worker = require 'proxy-guard.worker'
local api = require 'proxy-guard.extensions'

local routes = {
    ['/status'] = { method = 'GET', action = 'status' },
    ['/diagnostics'] = { method = 'GET', action = 'diagnostics' },
    ['/block'] = { method = 'POST', action = 'block' },
    ['/cancel'] = { method = 'POST', action = 'cancel' }
}
local responses = {
    [200] = 'OK', [400] = 'Bad Request', [401] = 'Unauthorized',
    [403] = 'Forbidden', [404] = 'Not Found', [405] = 'Method Not Allowed',
    [409] = 'Conflict', [413] = 'Content Too Large', [415] = 'Unsupported Media Type',
    [429] = 'Too Many Requests', [500] = 'Internal Server Error',
    [502] = 'Bad Gateway', [503] = 'Service Unavailable', [504] = 'Gateway Timeout'
}
local errors = {
    api_disabled = 403, authentication_required = 401, configuration_changed = 409, configuration_pending = 409,
    protection_not_active = 409, policy_not_ready = 503, request_state_unavailable = 503,
    invalid_duration = 400, invalid_request_id = 400, request_conflict = 409,
    busy = 503, too_many_requests = 429, diagnostic_cooldown = 429, firewall_failed = 503
}

local function send(code, result, extra)
    io.write('Status: ', code, ' ', responses[code], '\r\n',
        'Content-Type: application/json\r\nCache-Control: no-store\r\n',
        'X-Content-Type-Options: nosniff\r\n', extra or '', '\r\n', json.stringify(result), '\n')
end

-- The CGI peer address comes from uhttpd, never from a forwarding header.
local function local_peer()
    local peer = (os.getenv('REMOTE_ADDR') or ''):lower()
    peer = peer:match('^::ffff:(%d+%.%d+%.%d+%.%d+)$') or peer
    if peer == '127.0.0.1' or peer == '::1' then return true end
    local family = peer:find(':',1,true) and 6 or 4
    if peer:find('/',1,true) or not core.cidr(peer,family) then return false end
    local rc,route = worker.command('ip -'..family..' route get '..core.quote(peer))
    local device = rc == 0 and route:match('%sdev%s+([^%s]+)')
    if not device or route:match('%svia%s') then return false end

    local names, devices = {}, {}
    local function add(dst, list)
        for name in (type(list)=='string' and list or table.concat(list or {},' ')):gmatch('%S+') do
            dst[name] = true
        end
    end
    require('uci').cursor():foreach('firewall','zone',function(zone)
        if zone.name == 'lan' then
            add(names,zone.network)
            add(devices,zone.device)
        end
    end)
    if devices[device] then return true end
    local status, output = worker.command('ubus -t 2 -S call network.interface dump')
    local data = status == 0 and json.parse(output)
    for _, interface in ipairs(data and data.interface or {}) do
        if names[interface.interface] and device == (interface.l3_device or interface.device) then
            return true
        end
    end
    return false
end

local function body()
    local content_type = (os.getenv('CONTENT_TYPE') or ''):lower():match('^[^;%s]+')
    if content_type ~= 'application/json' then return nil,415,'json_required' end
    local length = os.getenv('CONTENT_LENGTH') or ''
    if not length:match('^%d+$') then return nil,400,'invalid_request' end
    local size = tonumber(length)
    if size > 4096 then return nil,413,'request_too_large' end
    local raw = io.read(size) or ''
    if #raw ~= size or not raw:match('^%s*{') then return nil,400,'invalid_request' end
    local ok, value = pcall(json.parse,raw)
    if not ok or type(value) ~= 'table' then return nil,400,'invalid_request' end
    return value
end

local function handle()
    local route = routes[os.getenv('PATH_INFO') or '']
    if not route then return 404,{ok=false,error='unknown_endpoint'} end
    if os.getenv('REQUEST_METHOD') ~= route.method then
        return 405,{ok=false,error='method_not_allowed'},'Allow: '..route.method..'\r\n'
    end
    if (os.getenv('QUERY_STRING') or '') ~= '' then return 400,{ok=false,error='unexpected_query'} end
    if os.getenv('HTTPS') ~= 'on' then return 403,{ok=false,error='https_required'} end
    if not auth.enabled() then return 403,{ok=false,error='api_disabled'} end

    local uuid = auth.bearer()
    if not auth.matches(uuid) then
        return 401,{ok=false,error='authentication_required'},'WWW-Authenticate: Bearer\r\n'
    end

    if not local_peer() then return 403,{ok=false,error='lan_required'} end

    local ok, result, status = pcall(function()
        local config, stamp, raw = api.api_config()
        api.api_log(config,route.action,uuid)
        if route.action == 'status' then return api.api_status(config,stamp,uuid,raw) end

        -- Parse the HTTP body before acquiring any lock used by the firewall.
        local payload
        if route.method == 'POST' then
            local value, code, error_code = body()
            if not value then return {ok=false,error=error_code},code end
            if value.request_id~=nil and
                (type(value.request_id)~='string' or #value.request_id>64 or not value.request_id:match('^[%w_-]*$')) then
                return {ok=false,error='invalid_request_id'}
            end
            if route.action=='block' and value.seconds~=nil then
                local seconds=value.seconds
                if type(seconds)~='number' or seconds~=math.floor(seconds) or seconds<0 or seconds>config.api_max_seconds then
                    return {ok=false,error='invalid_duration'}
                end
            end
            payload=json.stringify({request_id=value.request_id,seconds=value.seconds})
        end
        local command='ucode /usr/lib/proxy-guard/extension-lock.uc api_'..route.action
        if payload then command=command..' '..core.quote(payload) end
        local _, output=worker.command(command)
        local response=json.parse(output)
        assert(type(response)=='table' and type(response.ok)=='boolean','operation_failed')
        return response
    end)
    if not auth.matches(uuid) then return 401,{ok=false,error='authentication_required'},'WWW-Authenticate: Bearer\r\n' end
    if not ok then
        local code = tostring(result):match('([a-z_]+)$')
        result = {ok=false,error=errors[code] and code or 'operation_failed'}
    end

    result.uuid = uuid
    local diagnostic = result.diagnostics
    local diagnostic_error = diagnostic and not diagnostic.ok and (diagnostic.curl_code==28 and 504 or 502)
    local code = status or errors[result.error] or diagnostic_error or (result.ok and 200 or 500)
    local retry = result.retry_after or result.error=='busy' and 1
    local extra = retry and 'Retry-After: '..retry..'\r\n' or nil
    return code,result,extra
end

local ok, code, result, extra = pcall(handle)
if ok then send(code,result,extra)
else send(500,{ok=false,error='operation_failed'}) end
