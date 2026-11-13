-- SPDX-License-Identifier: MIT
-- Independent heartbeat permit and additive, owned API block requests.
local M={}
local core=require 'proxy-guard.core'
local json=require 'luci.jsonc'
local api_auth=require 'proxy-guard.api-auth'
local run='/var/run/proxy-guard'
local function W() return require 'proxy-guard.worker' end
local function read(path,limit)
 local f=io.open(path,'r');if not f then return nil end
 local value=f:read((limit or 262144)+1) or '';f:close()
 if #value>(limit or 262144) then return nil end
 return value
end
local function decode(path)
 local ok,v=pcall(json.parse,read(path) or '')
 return ok and type(v)=='table' and v or nil
end
local function write(path,value)
 local f=assert(io.open(path..'.new','w'),'state_write_failed')
 assert(require('nixio.fs').chmod(path..'.new','600'),'state_write_failed')
 assert(f:write(value));assert(f:close());assert(os.rename(path..'.new',path))
end
local function save(path,value) write(path,json.stringify(value)) end
local function now() return tonumber((read('/proc/uptime',128) or ''):match('^[%d%.]+')) or 0 end
local function boot() return (read('/proc/sys/kernel/random/boot_id',128) or ''):gsub('%s','') end
local function generation() return (read(run..'/control-generation',128) or 'initial'):gsub('%s','') end
local function stopped()return read(run..'/stopped')~=nil or read(run..'/removing')~=nil end
local function uuid() return assert(read('/proc/sys/kernel/random/uuid',128),'random_unavailable'):gsub('%s','') end
local function nft(script,name)
 local path=run..'/'..name..'-gate.nft';write(path,script)
 local rc=W().command('TZ=UTC0 nft -f '..core.quote(path))
 os.remove(path);return rc==0
end
local function context(raw)
 local c=W().config(raw)
 local d=c.enabled and c.mode=='guard' and W().devices(c,true) or {}
 return c,W().policy_stamp(c,d)
end
local function event(c,kind,message,level,api_uuid)
 local path=run..(kind=='heartbeat' and '/heartbeat-events.jsonl' or kind=='diagnostic' and '/diagnostic-events.jsonl' or '/api-events.jsonl')
 local line=json.stringify({time=os.time(),level=level or 'info',event=kind,message=message,api_uuid=api_uuid})..'\n'
 local current=io.open(path,'r');local size=current and current:seek('end') or 0
 if current then current:close() end
 if size+#line>c.log_kib*1024 then os.rename(path,path..'.1') end
 local f=assert(io.open(path,'a'));assert(f:write(line));assert(f:close())
end
function M.note_completion(ok)
 local old=decode(run..'/heartbeat-health.json') or {}
 save(run..'/heartbeat-health.json',{updated_uptime=now(),errors=ok and 0 or math.min(100,(tonumber(old.errors) or 0)+1)})
end
function M.heartbeat_state(c,stamp)
 local s=decode(run..'/heartbeat.json')
 if not c.heartbeat_enabled then return {enabled=false,allowed=true} end
 local up=now()
 local fast=c.passwall_watch and decode(run..'/fast.json')
 local incident_stale=c.passwall_watch and (not fast or fast.stamp~=stamp or not s or
    s.fast_trip~=fast.trip or s.fast_generation~=fast.generation)
 if not s or incident_stale or s.stamp~=stamp or s.boot~=boot() or s.generation~=generation() or
    type(s.checked_uptime)~='number' or s.checked_uptime>up or up-s.checked_uptime>c.heartbeat_lease then
    return {enabled=true,allowed=false,stale=true,phase='waiting'}
 end
 return {enabled=true,allowed=s.allowed==true,phase=s.phase,last_ok=s.last_ok,checked_at=s.checked_at,
    checked_uptime=s.checked_uptime,next_probe=s.next_probe,failures=s.failures,successes=s.successes,
    http_code=s.http_code,curl_code=s.curl_code,milliseconds=s.milliseconds,provider=c.check_mode,
    public=s.public,exit_check=s.exit_check,stale=false}
end
function M.heartbeat_gate()
 local c,stamp=context()
 if not c.enabled or not c.heartbeat_enabled or c.mode~='guard' or stopped() then return {ok=true,skipped=true} end
 local fw=W().table_state(stamp)
 if not fw.complete then return {ok=false,error='policy_not_ready'} end
 local s=M.heartbeat_state(c,stamp)
 local script='flush set inet proxy_guard heartbeat_ifaces\n'
 if s.allowed and not read(run..'/recovery-hold.json') then
  local remaining=math.floor(c.heartbeat_lease-(now()-s.checked_uptime))
  if remaining>0 then
   local values={};for _,v in ipairs(c.interfaces)do values[#values+1]=core.quote(v):gsub("'",'"')..' timeout '..remaining..'s' end
   script=script..'add element inet proxy_guard heartbeat_ifaces { '..table.concat(values,', ')..' }\n'
  end
 end
 return {ok=nft(script,'heartbeat')}
end
M.tls_fallback_message='官方 HTTPS 请求使用了 TLS 1.2，建议使用 TLS 1.3。'

local function tls_version_unavailable(rc,out)
 -- Old curl builds can reject the option before opening a connection.
 if rc==4 or rc==2 and out:find('option --tlsv1.3:',1,true) then return true end
 if rc~=35 then return false end
 out=out:lower()
 -- mbedTLS reports the peer's fatal alert without its description (-0x7780).
 -- Limit retries to these failures before HTTP, with certificate checks on both attempts.
 return out:find('alert protocol version',1,true) or out:find('alert version',1,true)
     or out:find('unsupported protocol',1,true)
     or out:find('unsupported ssl version',1,true)
     or out:find('unsupported minimum tls version',1,true)
     or out:find('no protocols available',1,true)
     or out:find('ssl_handshake returned: (-0x7780)',1,true)
end

-- Public endpoint requests share curl/SOCKS policy with the legacy probes.
-- Secrets are never put on argv, and optional telemetry is bounded/whitelisted.
function M.public_probe(c,options)
 options=options or {}
 local parser=require 'proxy-guard.public-heartbeat'
 local tag=options.full and 'public-full' or 'public-basic'
 local prefix=run..'/'..tag..'-'..require('nixio').getpid()
 local body_path,header_path,request_path=prefix..'.body',prefix..'.headers',prefix..'.request'
 local nonce=options.full and uuid():gsub('%-','') or nil
 local request='Cache-Control: no-cache\n'
 if nonce then request=request..'X-PGHB-Nonce: '..nonce..'\n' end
 write(request_path,request)
 local probe={};for k,v in pairs(c)do probe[k]=v end;probe.timeout=c.public_hb_timeout
 local url=options.full and c.public_diag_url or c.public_hb_url
 local started=now()
 local function request_tls(version)
  os.remove(body_path);os.remove(header_path)
  local rc,out=W().command(core.probe_command(probe,{url=url},body_path,version)..
     ' --dump-header '..core.quote(header_path)..' --header @'..core.quote(request_path))
  return rc,out,tonumber(out:match('(%d%d%d)%s+[%d%.]+%s*$')) or 0
 end
 local version='1.3'
 local rc,out,code=request_tls(version)
 if code==0 and tls_version_unavailable(rc,out) then
  local remaining=math.floor((probe.timeout-(now()-started))*100)/100
  if remaining>=0.2 then
   probe.timeout=remaining
   version='1.2'
   rc,out,code=request_tls(version)
  end
 end
 local body=read(body_path,4096) or '';local headers=read(header_path,32768)
 os.remove(request_path);os.remove(body_path);os.remove(header_path)
 local good,why,fields,ip_reason,raw_headers=parser.verify(rc,code,body,headers,nonce,nil,options.full or options.headers)
 local nonce_verified
 if nonce then nonce_verified=(rc==0 or rc==63 and code>=400) and fields~=nil and fields.nonce==nonce end
 -- Leave room for the status envelope in the local ubus response.
 if raw_headers and #json.stringify(raw_headers)>32768 then
  good,why,raw_headers=false,'diagnostic_headers_too_large',nil
 end
 return {ok=good,reason=why,rc=rc,code=code,public=true,milliseconds=math.floor((now()-started)*1000),
   metadata=not options.full and parser.metadata(fields) or nil,
   headers=raw_headers and #raw_headers>0 and raw_headers or nil,
   observed=fields and fields.ip,ip_reason=ip_reason,nonce_verified=nonce_verified,
   source=url,checked_at=os.time(),checked_uptime=now(),tls_version=code>0 and version or nil}
end
function M.record_public(c,stamp,response,gen)
 -- This is the ordinary website worker's observation for official exit verification.
 local path=run..'/public-observation.json'
 local boot_id=boot()
 local current=gen or generation()
 local previous=decode(path)
 local last=previous and previous.stamp==stamp and previous.boot==boot_id and
    previous.generation==current and previous.last_tls_version or nil
 save(path,{stamp=stamp,boot=boot_id,generation=current,
   ok=response.ok,reason=response.reason,source=response.source,checked_at=response.checked_at,
   checked_uptime=response.checked_uptime,metadata=response.metadata,last_tls_version=response.tls_version or last})
 return response.tls_version=='1.2' and last~='1.2'
end
-- Keep a known mismatch across fast incidents and service restarts in this boot.
local mismatch_path=run..'/exit-mismatch.json'
function M.exit_mismatch_pending(c)
 if not c.exit_check then return false end
 local prior=decode(mismatch_path)
 return prior~=nil and prior.expected==c.expected_exit4 and prior.boot==boot()
end
local exit_unavailable_messages={missing_ip='响应中未提供出口 IP 地址',
 invalid_ip='返回的出口 IP 地址格式无效',ipv6_only='服务只返回了 IPv6，无法校验出口 IPv4'}
function M.exit_unavailable_message(reason) return exit_unavailable_messages[reason] end

function M.exit_result(c,response)
 local outcome,observed,reason=core.exit_outcome(c,response)
 if outcome=='off' then return {enabled=false},true end
 local pending=M.exit_mismatch_pending(c)
 if outcome=='mismatch' and not pending then
  save(mismatch_path,{expected=c.expected_exit4,boot=boot()})
  pending=true
 elseif outcome=='match' and pending then
  os.remove(mismatch_path)
  pending=false
 end
 local status={enabled=true,attempted=response~=nil,outcome=outcome,expected=c.expected_exit4,
   observed=observed,reason=reason,mismatch_pending=pending==true}
 if response then
  status.curl_code=response.rc;status.http_code=response.code
  if response.fallback then status.via=c.exit_fallback_host end
 end
 if outcome=='match' then status.ok=true
 elseif outcome=='mismatch' or outcome=='unavailable' then status.ok=false end
 return status,outcome=='match' or (outcome=='timeout' and not pending)
end
local function current_record(path,stamp)
 local v=decode(path)
 return v and v.stamp==stamp and v.boot==boot() and v.generation==generation() and v or nil
end
local function diagnostic_stamp(c,policy_stamp)
 return table.concat({'headers',policy_stamp,tostring(c.diagnostics_enabled),c.diagnostics_interval,c.diagnostics_ttl},'|')
end

local function diagnostic_source(c)
 return c.diagnostics_enabled and c.public_diag_url or c.public_hb_url
end

local function diagnostic_result(response)
 return {ok=response.ok,reason=response.reason,source=response.source,checked_at=response.checked_at,
    headers=response.headers,nonce_verified=response.nonce_verified,
    http_code=response.code,curl_code=response.rc,milliseconds=response.milliseconds}
end

function M.heartbeat()
 if stopped() then return {ok=true,skipped=true} end
 local c,stamp=context()
 if not c.enabled or not c.heartbeat_enabled then os.remove(run..'/heartbeat.json');os.remove(run..'/heartbeat-poll');return {ok=true,skipped=true} end
 if not read(run..'/heartbeat-poll') then write(run..'/heartbeat-poll','1') end
 local snapshot=decode(run..'/status.json')
 if not snapshot or snapshot.config_stamp~=stamp or read(run..'/recovery-hold.json') then return {ok=true,skipped=true} end
 local fast=decode(run..'/fast.json')
 if c.passwall_watch then
  if not fast or fast.stamp~=stamp or type(fast.updated_uptime)~='number' or now()-fast.updated_uptime>4 or
   fast.phase=='boot_wait' or fast.phase=='delay' or fast.phase=='log_wait' or fast.log_pending then return {ok=true,skipped=true} end
 end
 if now()<core.startup_deadline(c) then return {ok=true,skipped=true} end
 local gen=generation()
 local s=decode(run..'/heartbeat.json')
 if not s or s.stamp~=stamp or s.boot~=boot() or s.generation~=gen or
    c.passwall_watch and (s.fast_trip~=fast.trip or s.fast_generation~=fast.generation) or
    type(s.checked_uptime)~='number' or now()<s.checked_uptime or now()-s.checked_uptime>c.heartbeat_lease then
  s={stamp=stamp,boot=boot(),generation=gen,allowed=false,failures=0,successes=0,phase='waiting'}
 end
 local strict=fast and fast.stamp==stamp and (fast.phase=='sensitive' or fast.phase=='ramp')
 local interval=strict and c.sensitive_interval or c.public_hb_interval
 if now()<(s.checked_uptime or 0)+interval then return {ok=true,skipped=true} end
 local started=now()
 local public=M.public_probe(c)
 local exit
 if c.exit_check then
  if c.exit_provider=='public' then exit=public
  elseif public.ok then exit=W().text_exit_probe(c) end
 end
 -- The result cannot renew permissions for changed configuration,
 -- a new service generation, or a new fast-protection incident.
 local _,newstamp=context()
 local latest_fast=decode(run..'/fast.json')
 if stopped() or gen~=generation() or newstamp~=stamp or read(run..'/recovery-hold.json') or
    (c.passwall_watch and (not latest_fast or latest_fast.stamp~=stamp or
       latest_fast.trip~=fast.trip or latest_fast.generation~=fast.generation or
       latest_fast.phase=='delay' or latest_fast.phase=='boot_wait' or latest_fast.phase=='log_wait' or latest_fast.log_pending or
       started<(latest_fast.probe_after or 0))) then
  return {ok=true,cancelled=true}
 end
 local exit_check,exit_ok=M.exit_result(c,exit)
 local good=public.ok and exit_ok
 local old=s.phase
 local old_tls=s.last_tls_version
 s.last_tls_version=public.tls_version or old_tls
 local old_exit=s.exit_check and s.exit_check.outcome
 local old_exit_reason=s.exit_check and s.exit_check.reason
 s.checked_uptime=now();s.checked_at=os.time();s.next_probe=s.checked_uptime+interval
 s.last_ok=good;s.curl_code=public.rc;s.http_code=public.code;s.milliseconds=math.floor((now()-started)*1000)
 s.provider=c.check_mode;s.exit_check=exit_check
 s.public={ok=public.ok,reason=public.reason,source=public.source,checked_at=public.checked_at,
     checked_uptime=public.checked_uptime,metadata=public.metadata}
 s.fast_trip=fast and fast.trip;s.fast_generation=fast and fast.generation
 if good then
  s.failures=0;s.successes=math.min(s.successes+1,c.public_hb_recover)
  if s.allowed or s.successes>=c.public_hb_recover then s.allowed=true;s.phase='healthy' else s.phase='recovering' end
 else
  s.successes=0;s.failures=math.min(s.failures+1,c.public_hb_fail)
  if strict or not s.allowed or s.failures>=c.public_hb_fail then s.allowed=false;s.phase='blocked' else s.phase='suspect' end
 end
 save(run..'/heartbeat.json',s)
 local code=W().command('ucode /usr/lib/proxy-guard/extension-lock.uc heartbeat_gate')
 if public.tls_version=='1.2' and old_tls~='1.2' then
  event(c,'heartbeat',M.tls_fallback_message,'warning')
 end
 if old~=s.phase then
  local messages={healthy='官方 HTTPS 检测通过',blocked='官方 HTTPS 检测失败',
   suspect='官方 HTTPS 检测失败，尚未达到阻断阈值',recovering='官方 HTTPS 检测恢复，等待连续成功确认'}
  event(c,'heartbeat',messages[s.phase])
 end
 if (old_exit~=exit_check.outcome or old_exit_reason~=exit_check.reason) and exit_check.attempted then
  local messages={match='出口 IPv4 校验通过',mismatch='出口 IPv4 与预期不符',
   timeout='出口 IPv4 查询超时，暂未取得地址',unavailable='无法校验出口 IPv4'}
  event(c,'heartbeat',M.exit_unavailable_message(exit_check.reason) or messages[exit_check.outcome])
 end
 return {ok=code==0 or code==75,deferred=code==75}
end

local function input(limit)
 limit=limit or 4096
 local text=io.read(limit+1) or '{}';assert(#text<=limit,'invalid_request')
 local ok,p=pcall(json.parse,text);assert(ok and type(p)=='table','invalid_request')
 return p
end
function M.luci_owner(p,method)
 local object='proxy_guard'
 local sid=p.ubus_rpc_session
 assert(type(sid)=='string' and #sid==32 and sid:match('^[%x]+$') and sid~=string.rep('0',32),'authentication_required')
 local rc,out=W().command('ubus -t 2 -S call session get '..core.quote(json.stringify({ubus_rpc_session=sid})))
 local value=rc==0 and json.parse(out)
 local name=value and value.values and value.values.username
 assert(type(name)=='string' and #name>0 and #name<=128,'authentication_required')
 local granted_rc,granted_out=W().command('ubus -t 2 -S call session access '..core.quote(json.stringify({
   ubus_rpc_session=sid,scope='ubus',object=object,['function']=method})))
 local granted=granted_rc==0 and json.parse(granted_out)
 assert(type(granted)=='table' and granted.access==true,'access_denied')
 return name
end
local function bind_probe_client(c)
 local clients=require 'proxy-guard.clients'
 local profile=clients.resolve(c.proxy_client)
 if c.passwall_watch then clients.bind(c,profile) else clients.bind_auth(c,profile) end
end

local function diagnostic_config(raw)
 local c=core.config({
    socks_port=raw.socks_port,proxy_client=raw.proxy_client,passwall_watch=raw.passwall_watch,
    client_auto_ports=raw.client_auto_ports,public_hb_timeout=raw.public_hb_timeout
 })
 bind_probe_client(c)
 return c
end

function M.run_diagnostics()
 M.luci_owner(input(),'run_diagnostics')
 assert(not read(run..'/removing'),'operation_failed')
 local c=diagnostic_config(require('uci').cursor():get_all('proxy_guard','main') or {})
 local response=M.public_probe(c,{full=true})
 if response.tls_version=='1.2' then event(c,'diagnostic',M.tls_fallback_message,'warning') end
 return {ok=true,diagnostics=diagnostic_result(response)}
end

-- A manual check uses a bounded preview. It never calls the monitor state
-- machine or renews the kernel permits. Only this LuCI RPC accepts a draft.
function M.test_proxy()
 local request=input(18000)
 M.luci_owner(request,'test_proxy')
 assert(type(request.draft)=='string' and #request.draft<=16000,'invalid_draft')
 local raw=json.parse(request.draft)
 assert(type(raw)=='table','invalid_draft')
 local config={}
 for _,field in ipairs({'check_mode','socks_port','proxy_client','passwall_watch','client_auto_ports',
    'targets','timeout','min_success','public_hb_timeout','exit_check','expected_exit4','exit_provider',
    'exit_url','exit_fallback_url'}) do config[field]=raw[field] end
 local valid,c=pcall(core.config,config)
 if not valid then return {ok=false,error='invalid_draft',detail=tostring(c):sub(1,300)} end
 if read(run..'/removing') then return {ok=false,error='operation_failed'} end
 bind_probe_client(c)
 local budget=12
 local started=now()
 local function run_probe(timeout,request_probe)
  local remaining=math.floor((budget-(now()-started))*10)/10
  if remaining<0.2 then return nil end
  local p={};for k,v in pairs(c) do p[k]=v end
  p.timeout=math.min(timeout,remaining)
  p.public_hb_timeout=p.timeout
  return request_probe(p)
 end
 local result={ok=true,check_mode=c.check_mode,checks={},complete=true,socks_port=c.socks_port}
 local function add(response,host,passed)
  if not response then result.complete=false;return end
  result.checks[#result.checks+1]={host=host,ok=passed,curl_code=response.rc,http_code=response.code,
     milliseconds=response.milliseconds,reason=response.reason}
 end
 local official,successes
 local function basic()
  local response=run_probe(c.public_hb_timeout,M.public_probe)
  add(response,c.public_hb_url:match('^https://([^/]+)'),response and response.ok)
  return response
 end
 local function text_ip(url)
  local path=run..'/exit-response-'..require('nixio').getpid()
  return run_probe(c.timeout,function(p) return W().https_probe(p,{url=url},path) end)
 end
 local ip_response,shared_exit
 if c.heartbeat_enabled then
  official=basic()
  result.connectivity_ok=official and official.ok or false
 else
  successes=0
  for _,target in ipairs(c.targets) do
   local response
   if c.exit_check and c.exit_provider=='text' and target.url==c.exit_url then
    if not shared_exit then ip_response=W().text_exit_probe(c,nil,text_ip);shared_exit=true end
    response=ip_response
   else
    local path=core.is_trace_url(target.url) and run..'/exit-response-'..require('nixio').getpid() or nil
    response=run_probe(c.timeout,function(p) return W().https_probe(p,target,path) end)
   end
   local url=response and response.fallback and c.exit_fallback_url or target.url
   local passed=response and response.rc==0 and response.code==target.code and
      (not core.is_trace_url(url) or core.trace(response.body)~=nil)
   add(response,target.host,passed)
   if response and response.fallback then result.checks[#result.checks].via=c.exit_fallback_host end
   if passed then successes=successes+1 end
  end
  result.connectivity_ok=successes>=c.min_success
 end
 if c.exit_check and c.exit_provider=='public' then
  if c.heartbeat_enabled then ip_response=official else ip_response=basic() end
 elseif c.exit_check and (not c.heartbeat_enabled or result.connectivity_ok) then
  if not shared_exit then ip_response=W().text_exit_probe(c,nil,text_ip) end
  if not ip_response then result.complete=false end
 end
 local outcome,observed,reason=core.exit_outcome(c,ip_response)
 result.exit_check={enabled=c.exit_check,outcome=outcome,observed=observed,reason=reason,expected=c.expected_exit4}
 result.observed_exit4=observed or (official and official.ok and core.cidr(official.observed,4) and official.observed or nil)
 result.milliseconds=math.floor((now()-started)*1000)
 return result
end

function M.api_config()
 local raw=api_auth.config()
 assert(type(raw)=='table' and raw.api_enabled=='1','api_disabled')
 local c,stamp=context(raw)
 if not c.enabled then
  c.api_enabled=true
  c.diagnostics_enabled=raw.diagnostics_enabled=='1'
  c.diagnostics_interval=tonumber(raw.diagnostics_interval) or c.diagnostics_interval
  c.diagnostics_ttl=tonumber(raw.diagnostics_ttl) or c.diagnostics_ttl
  c.api_default_seconds=tonumber(raw.api_default_seconds) or 300
  c.api_max_seconds=tonumber(raw.api_max_seconds) or 3600
 end
 return c,stamp,raw
end
local function requests(stamp)
 local state=decode(run..'/api-requests.json')
 if not state or state.stamp~=stamp or state.boot~=boot() or state.generation~=generation() then
  state={stamp=stamp,boot=boot(),generation=generation(),items={}}
 end
 local items={}
 local current=api_auth.current()
 for _,v in ipairs(state.items or {}) do
  if current and type(v)=='table' and v.owner==current and type(v.until_uptime)=='number' and v.until_uptime>now() then
   items[#items+1]=v
  end
 end
 state.items=items;return state
end
local function api_apply(c,state)
 local remaining=0
 for _,v in ipairs(state.items) do remaining=math.max(remaining,v.until_uptime-now()) end
 local script='flush set inet proxy_guard api_blocks\n'
 if remaining>0 then
  local values={};for _,v in ipairs(c.interfaces)do values[#values+1]='"'..v..'" timeout '..math.max(1,math.ceil(remaining))..'s' end
  script=script..'add element inet proxy_guard api_blocks { '..table.concat(values,', ')..' }\n'
 end
 return nft(script,'api')
end
function M.api_sync()
 local c,stamp=context()
 if not c.api_enabled or not c.enabled or c.mode~='guard' then os.remove(run..'/api-requests.json');return {ok=true} end
 if stopped() then return {ok=false,error='policy_not_ready'} end
 local fw=W().table_state(stamp)
 if not fw.complete then return {ok=false,error='policy_not_ready'} end
 local state=requests(stamp)
 if not next(state.items) and not next(fw.api_blocked) then return {ok=true} end
 if not decode(run..'/api-requests.json') then return {ok=true,orphaned=true} end
 if not api_apply(c,state) then return {ok=false,error='firewall_failed'} end
 save(run..'/api-requests.json',state);return {ok=true}
end
function M.api_summary(c,stamp)
 local count,remaining=0,0
 if c.api_enabled then for _,v in ipairs(requests(stamp).items)do count=count+1;remaining=math.max(remaining,v.until_uptime-now()) end end
 return {enabled=c.api_enabled,count=count,remaining=math.max(0,math.ceil(remaining))}
end
function M.api_log(c,action,who)
 local messages={
  status='API 查询状态', diagnostics='API 请求诊断',
  block='API 请求限时断网', cancel='API 撤回断网请求'
 }
 local lock=assert(require('nixio').open('/var/lock/proxy-guard-api-log.lock','a','600'))
 assert(lock:lock('lock'))
 local ok,err=pcall(event,c,'api_request',messages[action],nil,who)
 lock:close()
 if not ok then error(err) end
end

function M.api_diagnostics(c,stamp,raw,who)
 local initial_generation=generation()
 local key=diagnostic_stamp(c,stamp)
 local previous=current_record(run..'/diagnostics.json',key)
 local up=now()
 if previous and type(previous.checked_uptime)=='number' and previous.checked_uptime<=up then
  local remaining=math.ceil(previous.checked_uptime+c.diagnostics_interval-up)
  if remaining>0 then return {ok=false,error='diagnostic_cooldown',retry_after=remaining} end
 end

 -- Run the same SOCKS probe as the LuCI diagnostic without touching permits.
 local probe=diagnostic_config(raw)
 local response=M.public_probe(probe,{full=c.diagnostics_enabled,headers=true})
 assert(api_auth.matches(who),'authentication_required')
 local latest,new_stamp=M.api_config()
 assert(api_auth.ready() and initial_generation==generation() and diagnostic_stamp(latest,new_stamp)==key,'configuration_changed')
 local result=diagnostic_result(response)
 result.stamp=key;result.boot=boot();result.generation=generation()
 result.checked_uptime=response.checked_uptime
 result.last_tls_version=response.tls_version or previous and previous.last_tls_version
 save(run..'/diagnostics.json',result)
 if response.tls_version=='1.2' and (not previous or previous.last_tls_version~='1.2') then
  event(c,'diagnostic',M.tls_fallback_message,'warning')
 end
 return {ok=response.ok,diagnostics=diagnostic_result(response)}
end

function M.api_status(c,stamp,who,raw)
 local s=W().status(false,raw)
 local own={};for _,v in ipairs(requests(stamp).items)do
  if v.owner==who then own[#own+1]={request_id=v.id,remaining=math.ceil(v.until_uptime-now())} end
 end
 local result={ok=true,api_version=2,enabled=c.enabled,mode=c.mode,check_mode=c.check_mode,phase=s.phase,enforcement=s.enforcement,
    blocked=s.blocked,reason=s.reason,block_reasons=s.block_reasons,failure_progress=s.failure_progress,stale=s.stale,
    last_check=s.heartbeat and s.heartbeat.checked_at or s.last_probe_at,
    heartbeat=s.heartbeat,api=M.api_summary(c,stamp),requests=own,default_seconds=c.api_default_seconds,max_seconds=c.api_max_seconds}
 -- Preserve diagnostics only in the explicit diagnostics response.
 if result.heartbeat then result.heartbeat.exit_check=nil end
 result.exit_check=s.exit_check
 local basic=c.check_mode=='public' and current_record(run..'/heartbeat.json',stamp)
 basic=basic and basic.public or current_record(run..'/public-observation.json',stamp)
 if basic then
  local up=now();local when=basic.checked_uptime
  result.public_observation={ok=basic.ok,reason=basic.reason,source=basic.source,checked_at=basic.checked_at,
    metadata=basic.metadata,age_seconds=type(when)=='number' and math.max(0,math.floor(up-when)) or nil,
    stale=type(when)~='number' or up<when or up-when>c.diagnostics_ttl}
 end
 return result
end

function M.api_mutate(c,stamp,who,p,cancel)
 assert(c.enabled and c.api_enabled and c.mode=='guard' and not stopped(),'protection_not_active')
 local fw=W().table_state(stamp)
 assert(fw.complete and (decode(run..'/status.json') or {}).config_stamp==stamp,'policy_not_ready')
 assert(decode(run..'/api-requests.json') or not next(fw.api_blocked or {}),'request_state_unavailable')
 local state=requests(stamp)
 local id=p.request_id
 if not cancel and (id==nil or id=='') then id=uuid() end
 assert(type(id)=='string' and #id>=8 and #id<=64 and id:match('^[%w_-]+$'),'invalid_request_id')
 local match
 for i,v in ipairs(state.items)do if v.id==id and v.owner==who then match=i;break end end
 local seconds
 if cancel then
  if match then table.remove(state.items,match) end
 else
  seconds=(p.seconds==nil or p.seconds==0) and c.api_default_seconds or p.seconds
  assert(type(seconds)=='number' and seconds==math.floor(seconds) and seconds>=1 and seconds<=c.api_max_seconds,'invalid_duration')
  if match then
   assert(state.items[match].seconds==seconds,'request_conflict')
  else
   local own=0;for _,v in ipairs(state.items)do if v.owner==who then own=own+1 end end
   assert(#state.items<64 and own<8,'too_many_requests')
   state.items[#state.items+1]={id=id,owner=who,seconds=seconds,until_uptime=now()+seconds}
  end
 end
 assert(api_auth.matches(who),'authentication_required')
 -- Journal before applying; cancellation never changes healthy permits.
 -- A crash leaves at most the original bounded kernel block until resync.
 save(run..'/api-requests.json',state)
 assert(api_apply(c,state),'firewall_failed')
 local after=W().table_state(stamp)
 assert(after.complete,'policy_not_ready')
 local effective=false
 for _,name in ipairs(c.interfaces)do if (after.api_blocked or {})[name] then effective=true end end
 return {ok=true,request_id=id,cancelled=cancel or nil,effective=effective,
    remaining=M.api_summary(c,stamp).remaining,seconds=seconds}
end
return M
