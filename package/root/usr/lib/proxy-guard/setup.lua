-- Plugin-scoped confirmed configuration transactions. The browser owns no timer.
local json=require 'luci.jsonc'
local core=require 'proxy-guard.core'
local uci=require 'uci'
local package_state=require 'proxy-guard.package-state'
local M={}
local dir='/etc/proxy-guard/setup'
local config_path='/etc/config/proxy_guard'
local pending_path=dir..'/pending.json'
local result_path='/var/run/proxy-guard/setup-result.json'
local function read(path,limit)
 local f=io.open(path,'r');if not f then return nil end
 local s=f:read((limit or 65536)+1);f:close();assert(#s<=(limit or 65536),'setup_file_too_large');return s
end
local function decoded(path) local s=read(path,524288);if not s then return nil end;local good,v=pcall(json.parse,s);assert(good and type(v)=='table','setup_state_invalid');return v end
local function pending()
 local p=decoded(pending_path);if not p then return nil end
 local recovery=p.phase=='rollback_pending'
 assert(p.package_install==nil or type(p.package_install)=='boolean','setup_state_invalid')
 if p.package_install then assert(type(p.installer_pid)=='string' and p.installer_pid:match('^%d+$') and type(p.installer_started)=='string' and p.installer_started:match('^%d+$'),'setup_state_invalid') end
 assert(p.phase=='checking' or p.phase=='confirming' or recovery,'setup_state_invalid')
 assert(type(p.previous)=='string' and #p.previous>0 and #p.previous<=65536,'setup_state_invalid')
 assert(p.candidate==nil and p.phase=='checking' or type(p.candidate)=='string' and #p.candidate<=65536,'setup_state_invalid')
 assert(type(p.id)=='string' and (#p.id==36 or recovery and p.id=='recovery'),'setup_state_invalid')
 assert(type(p.owner)=='string' and (p.owner=='local' or p.owner=='unclaimed' or #p.owner==32 and p.owner:match('^%x+$')),'setup_state_invalid')
 assert(type(p.boot)=='string' and #p.boot==36,'setup_state_invalid')
 assert(type(p.generation)=='string' and #p.generation<=64 and p.generation:match('^[%w%-]+$'),'setup_state_invalid')
 if not recovery then
  assert(type(p.token)=='string' and #p.token==36,'setup_state_invalid')
  assert(type(p.deadline)=='number' and p.deadline>0 and p.deadline<1e12,'setup_state_invalid')
 end
 return p
end
local function write(path,text)
 local f=assert(io.open(path..'.new','w'),'setup_write_failed');assert(f:write(text));assert(f:close());assert(os.rename(path..'.new',path),'setup_replace_failed')
end
local function save(path,value)write(path,json.stringify(value)..'\n')end
local function up()return assert(tonumber((read('/proc/uptime',512) or ''):match('^[%d%.]+')),'setup_clock_unavailable')end
local function boot()return (read('/proc/sys/kernel/random/boot_id',128) or ''):gsub('%s','')end
local function uuid()local s=(read('/proc/sys/kernel/random/uuid',128) or ''):gsub('%s','');assert(#s==36 and s:match('^[%x%-]+$'),'setup_random_unavailable');return s end
local function run(command,limit)
 local f=io.popen(command,'r');local out=f and f:read((limit or 32768)+1) or '';local ok=f and f:close();assert(#out<=(limit or 32768),'setup_response_too_large');return out,ok
end
local function cursor_raw(path)
 local c=uci.cursor();assert(c:load(path or config_path),'setup_configuration_unreadable');local r=c:get_all('proxy_guard','main');assert(type(r)=='table','setup_configuration_unreadable');return r
end
local function init()
 assert(os.execute('umask 077; mkdir -p '..dir..' /var/run/proxy-guard /var/lock; chmod 700 '..dir..' /var/run/proxy-guard')==0,'setup_directory_unavailable')
end
local function monitor_running()
 local pid=(read('/var/run/proxy-guard/daemon.pid',128) or ''):match('^(%d+)')
 if not pid then return false end
 local argv=read('/proc/'..pid..'/cmdline',4096) or ''
 return (string.char(0)..argv):find(string.char(0)..'/usr/libexec/proxy-guard'..string.char(0)..'daemon'..string.char(0),1,true)~=nil
end
local function current_generation()return (read('/var/run/proxy-guard/control-generation',128) or 'initial'):gsub('%s','')end
local function request_apply(generation)
 assert(type(generation)=='string' and #generation<=64 and generation:match('^[%w%-]+$'),'setup_control_invalid')
 -- The independent watcher dispatches after this lock is released. Detached
 -- children must never inherit the transaction lock and stall confirmations.
 write('/var/run/proxy-guard/setup-apply-request',generation..'\n')
end
local function complete(p,phase,reason)
 save(result_path,{ok=phase=='confirmed',phase=phase,reason=reason,at=os.time(),id=p.id})
 assert(os.execute('/bin/sync')==0,'setup_sync_failed')
 os.remove(pending_path)
 os.remove(dir..'/trial-previous')
 assert(os.execute('/bin/sync')==0,'setup_sync_failed')
end
local function restore(p,reason)
 -- Never overwrite a newer CLI edit, another transaction, or a replacement file.
 local current=read(config_path)
 if current~=p.candidate then complete(p,'conflict','configuration_changed');return {ok=false,phase='conflict'} end
 -- A delayed kernel recovery must not rewrite the same flash config on every tick.
 if current~=p.previous then write(config_path,p.previous) end
 -- Restore effective rules before reporting completion. A probe holding the
 -- main lock cannot delay rollback indefinitely or renew a stale permit.
 local applied=os.execute('/usr/libexec/proxy-guard try_apply >/dev/null 2>&1')==0
 if not applied then
  os.execute('ucode /usr/lib/proxy-guard/quiesce.uc >/dev/null 2>&1')
  for _=1,20 do
   if os.execute('/usr/libexec/proxy-guard try_apply >/dev/null 2>&1')==0 then applied=true;break end
   os.execute("ucode -e 'sleep(100)'")
  end
 end
 if not applied then
  if p.phase~='rollback_pending' then
   p.phase='rollback_pending';p.rollback_reason=reason;p.candidate=p.previous;save(pending_path,p)
  end
  return {ok=false,phase='rollback_pending',reason=reason}
 end
 if reason~='service_stopped' then request_apply(current_generation()) end
 complete(p,'rolled_back',reason)
 return {ok=true,phase='rolled_back',reason=reason}
end
local function installer_active(p)
 if not p or not p.package_install or p.boot~=boot() then return false end
 local text=read('/proc/'..p.installer_pid..'/stat',8192)
 if not text then return false end
 local fields={};for value in (text:match('^.*%) (.*)$')or''):gmatch('%S+')do fields[#fields+1]=value end
 if fields[20]~=p.installer_started then return false end
 local command=(read('/proc/'..p.installer_pid..'/cmdline',8192)or''):match('^[^%z]+')or''
 local name=command:match('[^/]+$')
 return name=='opkg' or name=='opkg-cl' or name=='apk'
end
local function package_busy()
 if read('/var/run/proxy-guard/removing',128)~=nil or package_state.state()=='active' then return true end
 local good,p=pcall(pending)
 return good and installer_active(p)
end
function M.info(owner)
 local p=pending()
 local raw=cursor_raw()
 local active_enabled
 if raw.enabled=='0' then active_enabled=false elseif raw.enabled=='1' then active_enabled=true end
 local pro=io.open('/usr/lib/proxy-guard/access.lua','r');local pro_available=pro~=nil;if pro then pro:close() end
 local result={ok=true,active_enabled=active_enabled,wizard_complete=raw.setup_complete=='1',has_confirmed=read(dir..'/confirmed')~=nil,pro_available=pro_available}
 if p then
  result.transaction={id=p.id,phase=p.phase,remaining=math.max(0,math.ceil((p.deadline or 0)-up())),owned=owner~=nil and p.owner==owner,claimable=p.owner=='unclaimed' and p.phase~='rollback_pending'}
  if result.transaction.owned then result.transaction.token=p.token end
 end
 result.last_result=decoded(result_path)
 return result
end
function M.apply(request)
 if package_busy() then return {ok=false,retry_after_install=true,error='A package operation is in progress. Try again when it finishes.'} end
 init()
 if request.raw_token and request.raw_token~='' then require('proxy-guard.raw').check('proxy_guard',request.raw_token,request.ubus_rpc_session) end
 local sid=request.ubus_rpc_session
 assert(sid==nil or type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32),'setup_session_invalid')
 local raw
 if sid then
  local query=json.stringify({ubus_rpc_session=sid,config='proxy_guard',section='main'})
  local text=run('ubus -t 5 call uci get '..core.quote(query)..' 2>/dev/null')
  local data=json.parse(text);assert(type(data)=='table' and type(data.values)=='table','setup_session_configuration_unavailable');raw=data.values
 else raw=cursor_raw() end
 local c=core.load_config(raw)
 local active=pending()
 -- An explicit emergency off wins over a pending trial; old jobs cannot undo it.
 assert(not active or not c.enabled,'setup_transaction_busy')
 if c.enabled and sid then
  if request.confirm_flow~=true then return {ok=false,error='Reload this page before enabling protection.'} end
  for _,method in ipairs({'setup_confirm','setup_cancel'}) do
   local query=json.stringify({ubus_rpc_session=sid,scope='ubus',object='proxy_guard',['function']=method})
   local text=run('ubus -t 2 call session access '..core.quote(query)..' 2>/dev/null')
   local value=json.parse(text)
   if type(value)~='table' or value.access~=true then return {ok=false,error='Sign out of LuCI and sign in again to use updated permissions.'} end
  end
 end
 if c.enabled then
  local checked=require('proxy-guard.preflight').check(raw)
  assert(checked.ok,'setup_preflight_failed: '..tostring(checked.error or json.stringify(checked.checks)))
 end
 local current=assert(read(config_path),'setup_configuration_unreadable')
 local before=read(dir..'/confirmed') or current
 if package_busy() then return {ok=false,retry_after_install=true,error='A package operation is in progress. Try again when it finishes.'} end
 local generation=current_generation()
 local p={id=uuid(),token=uuid(),owner=sid or 'local',previous=before,boot=boot(),phase='checking',deadline=up()+120,generation=generation}
 if c.enabled then
  write(dir..'/trial-previous',before);save(pending_path,p);assert(os.execute('/bin/sync')==0,'setup_sync_failed')
 end
 if sid then
  local payload=json.stringify({ubus_rpc_session=sid,config='proxy_guard'})
  if os.execute('ubus -t 5 call uci commit '..core.quote(payload)..' >/dev/null 2>&1')~=0 then
   if c.enabled then os.remove(pending_path) end
   error('setup_commit_failed')
  end
 end
 p.candidate=assert(read(config_path),'setup_configuration_unreadable')
 if c.enabled then
  save(pending_path,p)
 else
  os.remove(pending_path)
  write(dir..'/previous',before);write(dir..'/confirmed',p.candidate)
  complete(p,'confirmed','explicit_off')
 end
 request_apply(generation)
 return {ok=true,queued=true,confirmation_required=c.enabled,transaction=c.enabled and {id=p.id,token=p.token,phase=p.phase} or nil}
end
function M.tick(on_boot)
 init()
 local valid,p=pcall(pending)
 if not valid then
  local previous=read(dir..'/trial-previous') or read(dir..'/confirmed')
  assert(previous,'setup_recovery_unavailable')
  return restore({id='recovery',candidate=read(config_path),previous=previous,owner='local',boot=boot(),generation=current_generation()},'transaction_state_invalid')
 end
 if installer_active(p) and os.getenv('PG_SETUP_PREINSTALL')~='1' then return {ok=true,phase='package_updating'} end
 if not p then
  if on_boot and not read(dir..'/confirmed') then core.load_config(cursor_raw());write(dir..'/confirmed',assert(read(config_path)));assert(os.execute('/bin/sync')==0,'setup_sync_failed') end
  return {ok=true,phase='idle'}
 end
 if p.candidate==nil then
  p.candidate=read(config_path)
  return restore(p,p.package_install and 'package_install_interrupted' or current_generation()~=p.generation and 'service_stopped' or 'interrupted_commit')
 end
 if p.phase=='rollback_pending' then return restore(p,p.rollback_reason or 'runtime_self_check_failed') end
 if on_boot or p.boot~=boot() then return restore(p,'restart_before_confirmation') end
 if read(config_path)~=p.candidate then complete(p,'conflict','configuration_changed');return {ok=false,phase='conflict'} end
 if current_generation()~=p.generation then return restore(p,'service_stopped') end
 if up()>=(p.deadline or 0) then return restore(p,p.phase=='confirming' and 'confirmation_timeout' or 'self_check_timeout') end
 if p.phase=='checking' then
  local ok,s=pcall(function()return require('proxy-guard.worker').status()end)
  local c=core.load_config(cursor_raw())
  if ok and s and s.enabled==true and monitor_running() and not s.stale and s.phase~='error' and
    ((c.mode=='monitor' and s.enforcement=='off') or (c.mode=='guard' and (s.enforcement=='blocked' or s.enforcement=='allowing'))) then
   p.phase='confirming';p.deadline=up()+30;save(pending_path,p)
  end
 end
 return {ok=true,phase=p.phase}
end
function M.confirm(request,cancel)
 init();local p=assert(pending(),'setup_no_pending_transaction')
 assert(request.token==p.token and request.id==p.id,'setup_transaction_mismatch')
 local owner=request.ubus_rpc_session or 'local';assert(owner==p.owner,'setup_transaction_owner_mismatch')
 if p.boot~=boot() or up()>=(p.deadline or 0) then restore(p,'confirmation_timeout');error('setup_confirmation_expired') end
 if cancel then return restore(p,'user_cancelled') end
 assert(p.phase=='confirming','setup_self_check_pending')
 assert(read(config_path)==p.candidate,'setup_configuration_changed')
 local c=core.load_config(cursor_raw())
 local status=require('proxy-guard.worker').status()
 if not monitor_running() or status.stale or status.phase=='error' or c.mode=='guard' and status.enforcement~='blocked' and status.enforcement~='allowing' then
  restore(p,'runtime_self_check_failed');error('setup_runtime_self_check_failed')
 end
 write(dir..'/previous',p.previous);write(dir..'/confirmed',p.candidate)
 complete(p,'confirmed','user_confirmed')
 return {ok=true,phase='confirmed'}
end
function M.previous()
 init();local text=assert(read(dir..'/confirmed'),'setup_no_previous_configuration')
 write(dir..'/proxy_guard',text)
 local raw=cursor_raw(dir..'/proxy_guard');os.remove(dir..'/proxy_guard')
 return {ok=true,draft=raw}
end
function M.discover(request)
 local choice=request and request.proxy_client or 'auto'
 if choice=='' then choice='auto' end
 assert(type(choice)=='string' and ({auto=true,passwall=true,passwall2=true,openclash=true,nikki=true,homeproxy=true})[choice],'setup_client_invalid')
 local text=run('ubus -t 5 call network.interface dump 2>/dev/null',65536)
 local data=json.parse(text);assert(type(data)=='table' and type(data.interface)=='table','setup_network_unavailable')
 local configured=uci.cursor();configured:load('/etc/config/network')
 local lan_networks,wan_networks={},{}
 local firewall=uci.cursor()
 if firewall:load('/etc/config/firewall') then
  firewall:foreach('firewall','zone',function(zone)
   local nets=type(zone.network)=='table' and zone.network or {zone.network}
   for _,name in ipairs(nets) do
    if zone.name=='lan' then lan_networks[name]=true end
    if zone.name=='wan' or zone.masq=='1' and zone.name~='lan' and name~='lan' then wan_networks[name]=true end
   end
  end)
 end
 local function network4(address,mask)
  if not core.cidr(address..'/'..mask,4) then return nil end
  local number=0;for part in address:gmatch('%d+') do number=number*256+tonumber(part) end
  number=math.floor(number/2^(32-mask))*2^(32-mask)
  local parts={};for i=4,1,-1 do parts[i]=tostring(number%256);number=math.floor(number/256) end
  return table.concat(parts,'.')..'/'..mask
 end
 local candidates={};local seen={}
 for _,item in ipairs(data.interface) do
  local name=item.interface;local device=item.l3_device or item.device
  local proto=type(name)=='string' and configured:get('network',name,'proto') or nil
  local trusted=name=='lan' or lan_networks[name]==true
  if not wan_networks[name] and (trusted or proto~='dhcp' and proto~='dhcpv6' and proto~='pppoe') and type(device)=='string' and #device<=15 and device:match('^[%w_%.%-]+$') and device~='lo' and not seen[device] and proto~='wireguard' and proto~='none' then
   local row={name=name,device=device,up=item.up==true,recommended=trusted,sources4={},sources6={},local4={},local6={}}
   for _,a in ipairs(item['ipv4-address'] or {}) do
    local m=tonumber(a.mask);if type(a.address)=='string' and m and m>=1 and m<=32 and a.address~='127.0.0.1' then
     local cidr=network4(a.address,m);if cidr then row.sources4[#row.sources4+1]=cidr;row.local4[#row.local4+1]=cidr end
    end
   end
   for _,a in ipairs(item['ipv6-address'] or {}) do
    local m=tonumber(a.mask);if type(a.address)=='string' and m and m>=1 and m<=128 and not a.address:lower():match('^fe[89ab]') then
     local cidr=a.address..'/'..m;row.sources6[#row.sources6+1]=cidr;row.local6[#row.local6+1]=cidr
    end
   end
   for _,a in ipairs(item['ipv6-prefix-assignment'] or {}) do
    local m=tonumber(a.mask);if type(a.address)=='string' and m and m>=1 and m<=128 then
     local cidr=a.address..'/'..m;row.sources6[#row.sources6+1]=cidr;row.local6[#row.local6+1]=cidr
    end
   end
   if #row.sources4+#row.sources6>0 then candidates[#candidates+1]=row;seen[device]=true end
  end
 end
 table.sort(candidates,function(a,b)return a.device<b.device end)
 local profile=require('proxy-guard.clients').resolve(choice)
 return {ok=true,defaults=cursor_raw('/usr/share/proxy-guard/defaults/proxy_guard'),interfaces=candidates,client={available=profile.available,client=profile.client,error=profile.error,socks_port=profile.socks_port,proxy_ports=profile.proxy_ports,dns_ports=profile.dns_ports},read_only=true}
end
-- Covers LuCI's global UCI Apply and explicit CLI commits as well as our page.
function M.observe()
 if package_busy() then return {ok=true,phase='package_updating'} end
 init()
 if read(pending_path) then return {ok=true,phase='pending'} end
 local baseline=read(dir..'/confirmed')
 if not baseline or read(config_path)==baseline then return {ok=true,phase='idle'} end
 local good,result=pcall(M.apply,{})
 if not good then
  return restore({id=uuid(),candidate=read(config_path),previous=baseline,owner='unclaimed',boot=boot(),generation=current_generation()},'external_self_check_failed')
 end
 if result.confirmation_required then
  local p=assert(pending());p.owner='unclaimed';save(pending_path,p)
 end
 return result
end
function M.claim(request)
 init()
 local p=assert(pending(),'setup_no_pending_transaction')
 local sid=request.ubus_rpc_session
 assert(sid==nil or type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32),'setup_session_invalid')
 assert(p.owner=='unclaimed','setup_transaction_owner_mismatch')
 assert(p.boot==boot() and up()<p.deadline,'setup_confirmation_expired')
 p.owner=sid or 'local';p.token=uuid();save(pending_path,p)
 return M.info(p.owner)
end
function M.installed()
 init()
 local p=pending()
 assert(not p or p.package_install==true,'setup_transaction_busy')
 core.load_config(cursor_raw())
 write(dir..'/confirmed',assert(read(config_path),'setup_configuration_unreadable'))
 complete(p or {id=uuid()},'confirmed','package_installed')
 return {ok=true,phase='installed'}
end
return M

