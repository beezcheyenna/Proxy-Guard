package.path='/usr/lib/?.lua;'..package.path
local json=require 'luci.jsonc'
local ok,result=pcall(function()
    local m=require 'proxy-guard.extensions'
    local action=arg[1]
    if action=='api_diagnostics' or action=='api_block' or action=='api_cancel' then
        local auth=require 'proxy-guard.api-auth'
        local uuid=auth.bearer()
        assert(auth.matches(uuid),'authentication_required')
        assert(auth.ready(),'configuration_pending')
        local config,stamp,raw=m.api_config()
        if action=='api_diagnostics' then return m.api_diagnostics(config,stamp,raw,uuid) end
        return m.api_mutate(config,stamp,uuid,json.parse(arg[2]),action=='api_cancel')
    end
    return assert(m[action])()
end)
if arg[1]=='heartbeat' then pcall(function() require('proxy-guard.extensions').note_completion(ok and (type(result)~='table' or result.ok~=false)) end) end
print(json.stringify(ok and result or {ok=false,error=tostring(result):match('([a-z_]+)$') or 'operation_failed'}))
os.exit(ok and (type(result)~='table' or result.ok~=false) and 0 or 1)
