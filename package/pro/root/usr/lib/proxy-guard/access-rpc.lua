#!/usr/bin/lua
package.path='/usr/lib/?.lua;'..package.path
local json=require 'luci.jsonc'
local core=require 'proxy-guard.core'
local access=require 'proxy-guard.access'
if arg[1]=='list' then print('{"raw_info":{"ubus_rpc_session":""},"raw_parse":{"ubus_rpc_session":"","text":"","token":""},"status":{"ubus_rpc_session":""},"policy_confirm":{"ubus_rpc_session":"","id":""},"policy_cancel":{"ubus_rpc_session":"","id":""},"egress_info":{"ubus_rpc_session":"","refresh":false},"apply":{"ubus_rpc_session":"","raw_token":""},"preflight":{"ubus_rpc_session":""},"restart_xray":{"ubus_rpc_session":""},"reboot_vps":{"ubus_rpc_session":""}}');return end
local actions={raw_info=true,raw_parse=true,status=true,policy_confirm=true,policy_cancel=true,egress_info=true,apply=true,preflight=true,restart_xray=true,reboot_vps=true}
if arg[1]~='call' or not actions[arg[2]] then print('{}');os.exit(2) end
if arg[2]=='raw_info' or arg[2]=='raw_parse' then
    local ok,result=pcall(function()
        local raw=require 'proxy-guard.raw'
        local request=json.parse(io.read(262145) or '{}')
        assert(type(request)=='table','raw_text_invalid')
        if arg[2]=='raw_info' then return raw.info('proxy_guard_access',request.ubus_rpc_session) end
        return raw.parse('proxy_guard_access',request.text,request.token,request.ubus_rpc_session)
    end)
    print(json.stringify(ok and result or {ok=false,error=tostring(result):match('([a-z_]+)$') or 'raw_validation_failed'}));os.exit(ok and 0 or 1)
end
if arg[2]=='status' then local request=json.parse(io.read(4097)or'{}')or{};print(json.stringify(access.status(request.ubus_rpc_session)));return end
if arg[2]=='policy_confirm'or arg[2]=='policy_cancel'then
 local ok,result=pcall(function()
  local request=json.parse(io.read(4097)or'{}');assert(type(request)=='table','invalid_session')
  local sid=request.ubus_rpc_session;assert(type(sid)=='string'and #sid==32 and sid:match('^%x+$'),'invalid_session')
  return require('proxy-guard.access-trial').action(arg[2]=='policy_confirm'and'confirm'or'cancel',sid,request.id)
 end)
 print(json.stringify(ok and {ok=true,queued=true,policy_trial=result}or{ok=false,error=tostring(result):match('([a-z_]+)$')or'policy_trial_failed'}));return
end
local function call(method,payload)
    local command='ubus -t 2 call uci '..method..' '..core.quote(json.stringify(payload))
    local f=assert(io.popen(command..[[ 2>/dev/null; printf '\nPG_ACCESS_RC_%s\n' "$?"]],'r'))
    local output=f:read(131073) or '';f:close()
    assert(#output<=131072,'policy_too_large')
    local text,code=output:match('^(.*)\nPG_ACCESS_RC_(%d+)\n?$')
    assert(tonumber(code)==0,'uci_operation_failed')
    if not text or text:match('^%s*$') then return {} end
    local value=json.parse(text)
    assert(type(value)=='table' and not value.error,'uci_operation_failed');return value
end
if arg[2]~='apply' then
    local ok,result=pcall(function()
        local request=json.parse(io.read(4097) or '')
        local sid=type(request)=='table' and request.ubus_rpc_session
        assert(type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32),'invalid_session')
        local data={ubus_rpc_session=sid,scope='ubus',object='proxy_guard_access',['function']=arg[2]}
        local f=assert(io.popen('ubus -t 2 call session access '..core.quote(json.stringify(data))..' 2>/dev/null','r'))
        local value=json.parse(f:read(4097) or '');f:close();assert(type(value)=='table' and value.access==true,'access_denied')
        if arg[2]=='egress_info' then return access.egress_info(request.refresh==true) end
        return access.queue(arg[2])
    end)
    print(json.stringify(ok and (arg[2]=='egress_info' and result or {ok=true,queued=true,operation=result}) or {ok=false,error=tostring(result):match('([a-z_]+)$') or 'queue_failed'}))
    os.exit(ok and 0 or 1)
end
local created_trial,active_owner
local ok,why=pcall(function() return require('proxy-guard.access-trial').locked(function()
    local fs=require 'nixio.fs';assert(not fs.access('/var/run/proxy-guard-access/installing')and not fs.access('/var/run/proxy-guard-access/updating')and not fs.access('/var/run/proxy-guard/removing'),'apply_busy')
    local parsed,request=pcall(json.parse,io.read(4097) or '')
    assert(parsed and type(request)=='table','invalid_request')
    if request.raw_token and request.raw_token~='' then require('proxy-guard.raw').check('proxy_guard_access',request.raw_token,request.ubus_rpc_session) end
    local sid=request.ubus_rpc_session;active_owner=sid
    if sid~=nil then
        assert(type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32),'invalid_session')
        local data=call('get',{ubus_rpc_session=sid,config='proxy_guard_access'})
        assert(type(data.values)=='table','config_unavailable')
        local config=access.load(data.values)
        if config.enabled and config.policy_confirm then
            for _,method in ipairs({'policy_confirm','policy_cancel'})do
                local query=json.stringify({ubus_rpc_session=sid,scope='ubus',object='proxy_guard_access',['function']=method})
                local f=assert(io.popen('ubus -t 2 call session access '..core.quote(query)..' 2>/dev/null','r'))
                local granted=json.parse(f:read(4097)or'');f:close()
                assert(type(granted)=='table'and granted.access==true,'session_permissions_updated')
            end
        end
        local committed=access.sections()
        local trial=require 'proxy-guard.access-trial'
        assert(not config.enabled or not trial.pending(),'policy_trial_busy')
        local revision=tonumber(committed.main and committed.main.revision) or 1
        assert(revision>=1 and revision<9007199254740991,'invalid_revision')
        if config.enabled and config.policy_confirm then created_trial=trial.prepare(sid,revision+1,config.policy_confirm_seconds,data.values).id end
        call('set',{ubus_rpc_session=sid,config='proxy_guard_access',section='main',values={revision=tostring(revision+1)}})
        -- Staged credentials belong only to this session and never enter readable committed UCI.
        local submitted=data.values.main and data.values.main.device_token
        local path_submitted=data.values.main and data.values.main.path_token
        for _,secret in pairs({device=submitted,path=path_submitted}) do
            assert(secret=='' or type(secret)=='string' and #secret>=32 and #secret<=256 and secret:match('^[A-Za-z0-9_-]+$') and not secret:match('^REPLACE_'),'invalid_device_token')
        end
        if submitted and submitted~='' then
            call('delete',{ubus_rpc_session=sid,config='proxy_guard_access',section='main',option='device_token'})
        end
        if path_submitted and path_submitted~='' then call('delete',{ubus_rpc_session=sid,config='proxy_guard_access',section='main',option='path_token'}) end
        call('commit',{ubus_rpc_session=sid,config='proxy_guard_access'})
        if submitted and submitted~='' then access.save_secret(submitted) end
        if path_submitted and path_submitted~='' then access.save_secret(path_submitted,'path') end
        if config.enabled and config.policy_confirm then trial.committed()elseif not config.enabled then trial.stop()end
    else
        access.load(access.sections());access.bump()
    end
    -- Fixed asynchronous action. No network activity is performed inside RPC.
    os.execute('/etc/init.d/proxy-guard-access restart >/dev/null 2>&1 </dev/null &')
end) end)
if not ok and created_trial then pcall(function()local t=require 'proxy-guard.access-trial';local p=t.pending();if p and p.id==created_trial then t.restore('local_apply_failed',true)end end)end
print(json.stringify(ok and {ok=true,queued=true,policy_trial=require('proxy-guard.access-trial').public(active_owner)} or {ok=false,error=tostring(why):match('([a-z_]+)$') or 'apply_failed'}))
os.exit(ok and 0 or 1)
