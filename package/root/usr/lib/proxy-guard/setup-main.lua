package.path='/usr/lib/?.lua;'..package.path
local json=require 'luci.jsonc'
local setup=require 'proxy-guard.setup'
local allowed={apply=true,setup_info=true,setup_discover=true,setup_confirm=true,setup_cancel=true,setup_previous=true,setup_claim=true,observe=true,tick=true,boot=true,installed=true}
local action=arg[1]
if not allowed[action] then os.exit(2) end
local request={}
local ok,result=pcall(function()
 if action~='tick' and action~='boot' and action~='observe' and action~='installed' then
  local s=io.read(65537) or '';assert(#s<=65536,'setup_request_too_large')
  if s~='' then request=json.parse(s);assert(type(request)=='table','setup_request_invalid') end
 end
 if action=='apply' then return setup.apply(request)
 elseif action=='tick' or action=='boot' then return setup.tick(action=='boot')
 elseif action=='installed' then return setup.installed()
 elseif action=='setup_info' then return setup.info(request.ubus_rpc_session)
 elseif action=='setup_discover' then return setup.discover(request)
 elseif action=='setup_previous' then return setup.previous()
 elseif action=='observe' then return setup.observe()
 elseif action=='setup_claim' then return setup.claim(request)
 else return setup.confirm(request,action=='setup_cancel') end
end)
if action=='apply' and (not ok or result.ok==false) then
 local failure=ok and result or {ok=false,error=tostring(result):sub(1,1500)}
 local state_ok,state=false,nil
 if not failure.retry_after_install then state_ok,state=pcall(setup.info) end
 if state_ok then
  failure.active_enabled=state.active_enabled
  local sid=request.ubus_rpc_session
  if state.active_enabled==false and type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32) then
   local payload=json.stringify({ubus_rpc_session=sid,config='proxy_guard',section='main',values={enabled='0'}})
   local core=require 'proxy-guard.core'
   os.execute('ubus -t 5 call uci set '..core.quote(payload)..' >/dev/null 2>&1')
  end
 end
 print(json.stringify(failure))
else
 print(json.stringify(ok and result or {ok=false,error=tostring(result):sub(1,1500)}))
end
os.exit(ok and result.ok~=false and 0 or 1)

