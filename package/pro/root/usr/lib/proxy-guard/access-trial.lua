-- Private local counterpart of the VPS-owned confirmation timer.
local M={}
local json=require 'luci.jsonc'
local fs=require 'nixio.fs'
local core=require 'proxy-guard.core'
local uci=require 'uci'
local dir='/etc/proxy-guard-access/trial'
local path=dir..'/pending.json'
local config='/etc/config/proxy_guard_access'
local function read(p,limit)local f=io.open(p);if not f then return nil end;local s=f:read((limit or 65536)+1);f:close();assert(#s<=(limit or 65536),'policy_trial_storage_invalid');return s end
local function write(p,s)local f=assert(io.open(p..'.new','w'),'policy_trial_storage_unavailable');assert(f:write(s));assert(f:close());fs.chmod(p..'.new','600');assert(os.rename(p..'.new',p))end
local function init()assert(os.execute('umask 077; mkdir -p '..dir..' /var/run/proxy-guard-access; chmod 700 '..dir..' /var/run/proxy-guard-access')==0,'policy_trial_storage_unavailable')end
local function up()return tonumber((read('/proc/uptime',128)or''):match('^[%d%.]+'))or 0 end
local function boot()return(read('/proc/sys/kernel/random/boot_id',128)or''):gsub('%s','')end
local function decoded(p)local s=read(p,1048576);if not s then return nil end;local v=json.parse(s);assert(type(v)=='table','policy_trial_storage_invalid');return v end
local function load()
 local p=decoded(path);local finished=decoded(dir..'/result.json')
 if not p then return nil end
 if finished and finished.id==p.id then return nil end
 assert(type(p.id)=='string'and #p.id==36 and p.id:match('^[a-f0-9%-]+$')and type(p.revision)=='number'and type(p.previous)=='string'and type(p.owner)=='string','policy_trial_storage_invalid');return p
end
local function save(p)init();local encoded=json.stringify(p);assert(#encoded<=1048576,'policy_trial_storage_invalid');write(path,encoded);assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed')end
local function keys()return{device=read('/etc/proxy-guard-access/device.key',256),proxy=read('/etc/proxy-guard-access/path.key',256)}end
local function equal(a,b)return(a.device or'')==(b.device or'')and(a.proxy or'')==(b.proxy or'')end
local function outcome(p,phase,reason,remote_known)
 local r={id=p.id,revision=p.revision,phase=phase,reason=reason,remote_known=remote_known==true,at=os.time()}
 write(dir..'/result.json',json.stringify(r));assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed');os.remove(path);os.remove(path..'.new');assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed');return r
end
function M.pending()return load()end
local function canonical_values(values)
 local sections={};for id,row in pairs(values)do
  local options={};for k,v in pairs(row)do if k:sub(1,1)~='.'then options[k]=v end end
  sections[id]={section_type=row['.type'],options=options}
 end
 return require('proxy-guard.raw').serialize(sections,false)
end
local function process_stat(text)
 if not text then return nil end
 local pid=text:match('^(%d+)');local rest=text:match('^%d+ %b() (.*)$');if not rest then return nil end
 local fields={};for v in rest:gmatch('%S+')do fields[#fields+1]=v end
 return pid,fields[20],fields[1]
end
function M.prepare(owner,revision,seconds,desired)
 init();assert(not load(),'policy_trial_busy')
 local id=(read('/proc/sys/kernel/random/uuid',128)or''):gsub('%s','')
 local p={id=id,owner=owner or'local',revision=revision,seconds=seconds,previous=assert(read(config)),previous_keys=keys(),boot=boot(),started=up(),phase='preparing'}
 p.writer,p.writer_start=process_stat(read('/proc/self/stat',8192));assert(p.writer and p.writer_start,'policy_trial_writer_unavailable')
 if desired then
  local target=json.parse(json.stringify(desired));target.main.revision=tostring(revision)
  local submitted=target.main.device_token;local proxy=target.main.path_token
  p.target_keys={device=submitted and submitted~=''and submitted or p.previous_keys.device,proxy=proxy and proxy~=''and proxy or p.previous_keys.proxy}
  if submitted and submitted~=''then target.main.device_token=nil end
  if proxy and proxy~=''then target.main.path_token=nil end
  p.expected=canonical_values(target)
 end
 save(p);return p
end
function M.committed()
 local p=assert(load(),'policy_trial_missing');p.candidate=assert(read(config));p.candidate_keys=keys();p.phase='waiting';save(p)
end
function M.discard_uncommitted()
 local p=load();if p and read(config)==p.previous then os.remove(path)end
end
function M.stop()
 local ok,p=pcall(function()local current=load();decoded(dir..'/result.json');return current end)
 if not ok then
  init()
  for _,file in ipairs({'pending.json','result.json'})do
   if fs.lstat(dir..'/'..file)then assert(os.rename(dir..'/'..file,dir..'/'..file..'.corrupt'),'policy_trial_storage_unavailable');fs.chmod(dir..'/'..file..'.corrupt','600')end
  end
  write(dir..'/result.json',json.stringify({phase='stopped',reason='policy_trial_storage_invalid',remote_known=false,at=os.time()}))
  assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed');return
 end
 if p then outcome(p,'stopped','synchronization_stopped',false)end
end
function M.restore(reason,remote_known)
 local p=assert(load(),'policy_trial_missing')
 local actual,k=read(config),keys()
 if not p.candidate and actual==p.previous and equal(k,p.previous_keys or{})then return outcome(p,'rolled_back',reason,remote_known)end
 if not p.candidate and p.expected then
  local access=require 'proxy-guard.access';local current=access.sections()
  local valid=canonical_values(current)==p.expected
  for _,key in ipairs({'device','proxy'})do valid=valid and((k[key]or'')==((p.previous_keys or{})[key]or'')or(k[key]or'')==((p.target_keys or{})[key]or''))end
  if valid then p.candidate=actual;p.candidate_keys=k end
 end
 local valid=p.candidate and actual==p.candidate and equal(k,p.candidate_keys or{})
 if p.phase=='restoring'and type(p.restore_target)=='string'then
  valid=actual==p.candidate or actual==p.restore_target
  for _,key in ipairs({'device','proxy'})do valid=valid and((k[key]or'')==((p.previous_keys or{})[key]or'')or(k[key]or'')==((p.candidate_keys or{})[key]or''))end
 end
 if not valid then return outcome(p,'conflict','configuration_changed',remote_known)end
 local previous=p.restore_target
 if not previous then
  local work=dir..'/restore-'..p.id
  local st=fs.lstat(work)
  if st then
   assert(st.type=='dir','policy_trial_storage_invalid')
   for _,file in ipairs({'proxy_guard_access','proxy_guard_access.new','savedir/proxy_guard_access'})do os.remove(work..'/'..file)end
   fs.rmdir(work..'/savedir');assert(fs.rmdir(work),'policy_trial_storage_unavailable')
  end
  assert(fs.mkdir(work,'700'),'policy_trial_storage_unavailable');assert(fs.mkdir(work..'/savedir','700'),'policy_trial_storage_unavailable')
  local ok,result=pcall(function()
   write(work..'/proxy_guard_access',p.previous)
   local c=uci.cursor(work,work..'/savedir');assert(c:load('proxy_guard_access'));c:set('proxy_guard_access','main','revision',tostring(p.revision));assert(c:commit('proxy_guard_access'));c:unload('proxy_guard_access')
   return assert(read(work..'/proxy_guard_access'))
  end)
  os.remove(work..'/proxy_guard_access');fs.rmdir(work..'/savedir');fs.rmdir(work)
  assert(ok,result);previous=result
  -- Persist the exact restore target before rewriting either credential.
  -- A killed restore may leave a mix of its old/new values, but unrelated
  -- values still cause a conflict instead of being overwritten.
  p.restore_target=previous;p.restore_reason=reason;p.restore_remote=remote_known==true;p.phase='restoring';save(p)
 end
 for name,file in pairs({device='device.key',proxy='path.key'})do
  local value=(p.previous_keys or{})[name];local target='/etc/proxy-guard-access/'..file
  if value then write(target,value)else os.remove(target)end
 end
 write(config,previous);assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed')
 write('/var/run/proxy-guard-access/trial-reload','1\n')
 return outcome(p,'rolled_back',p.restore_reason or reason,p.restore_remote==true or remote_known==true)
end
function M.recover_preparing()
 local p=load()
 if not p then
  -- A kill after the durable outcome but before unlink leaves a completed
  -- private snapshot. Remove it under the same metadata lock, once only.
  if fs.access(path)then assert(os.remove(path),'policy_trial_storage_unavailable');os.remove(path..'.new');assert(os.execute('/bin/sync')==0,'policy_trial_sync_failed')end
  return true
 end
 if p.phase~='preparing'then return true end
 if p.boot==boot()and type(p.writer)=='string'and p.writer:match('^%d+$')then
  local pid,started,state=process_stat(read('/proc/'..p.writer..'/stat',8192))
  if pid==p.writer and started==p.writer_start and state~='Z'and state~='X'and state~='x'then return false end
 end
 M.restore('interrupted_commit',true);return true
end
function M.spec(c)
 local p=load();if not p then return nil end
 if p.phase=='restoring'then M.restore(p.restore_reason or'interrupted_restore',p.restore_remote);return nil,'restored'end
 if p.phase=='preparing'then M.recover_preparing();return nil,'preparing'end
 assert(p.phase~='preparing'and p.candidate==read(config)and p.revision==c.revision and equal(keys(),p.candidate_keys or{}),'policy_trial_configuration_changed')
 if p.phase=='uncertain'and p.action=='confirm'then return{id=p.id,seconds=p.seconds},'uncertain'end
 if p.boot~=boot()or up()-p.started>p.seconds+120 then
  -- An accepted confirmation may have lost its response. Never undo local
  -- settings by assuming that the remote side is still unconfirmed.
  if p.action=='confirm'then p.phase='uncertain';save(p);return{id=p.id,seconds=p.seconds},'uncertain'end
  M.restore(p.boot~=boot()and'restart_before_confirmation'or'control_result_unknown',false);return nil,'restored'
 end
 if p.phase=='remote_restoring'then return nil,'remote_restoring'end
 return{id=p.id,seconds=p.seconds}
end
function M.sent()
 local p=assert(load());if not p.sent then p.sent=up();save(p)end
end
function M.observe(remote)
 local p=load();if not p or type(remote)~='table'or type(remote.policy_trial)~='table'then return nil end
 local t=remote.policy_trial
 if type(remote.revision)=='number'and remote.revision>p.revision then return outcome(p,'conflict','remote_policy_changed',true)end
 if t.id~=p.id or t.revision~=p.revision then return nil end
 if t.phase=='confirmed'then return outcome(p,'confirmed',t.reason or'user_confirmed',true)end
 if t.phase=='rolled_back'then return M.restore(t.reason or'confirmation_timeout',true)end
 if t.phase=='conflict'then return outcome(p,'conflict','remote_policy_changed',true)end
 if t.phase=='restoring'then
  if p.phase~='remote_restoring'then p.phase='remote_restoring';p.remote_known=true;save(p)end
  return nil
 end
 if t.phase=='confirming'or t.phase=='applying'then
  local changed=p.phase~=t.phase;p.phase=t.phase;p.remote_known=true
  if type(t.remaining)=='number'then p.remote_deadline=up()+math.max(0,math.min(300,t.remaining))end
  -- Remaining time is derived from one receipt, not persisted every health poll.
  if changed or not p.deadline_saved then p.deadline_saved=true;save(p)end
 end
 return nil
end
function M.action(action,owner,id)
 local p=assert(load(),'policy_trial_missing');assert(p.owner==(owner or'local')and p.id==id,'policy_trial_owner_mismatch')
 assert(action=='confirm'or action=='cancel','invalid_policy_trial');assert(not p.action,'policy_trial_action_pending')
 assert(action=='cancel'or p.phase=='confirming','policy_trial_not_ready')
 p.action=action;save(p);write('/var/run/proxy-guard-access/wake','1\n');return M.public(owner)
end
function M.requested()local p=load();return p and p.action,p end
function M.public(owner)
 local p=load();local result=decoded(dir..'/result.json')
 if not p then return{pending=false,last_result=result}end
 return{pending=true,id=p.id,revision=p.revision,phase=p.phase,seconds=p.seconds,owned=p.owner==(owner or'local'),
  action=p.action,remaining=p.remote_deadline and math.max(0,math.ceil(p.remote_deadline-up()))or nil,last_result=result}
end
-- lockf is part of the existing nixio dependency, with no external flock tool.
-- Only short metadata operations hold it; HTTPS requests never hold this lock.
local held=false
local function locked(action,...)
 if held then return action(...)end
 local nixio=require 'nixio';fs.mkdir('/var/lock','700')
 local lock=assert(nixio.open('/var/lock/proxy-guard-access-trial.lock','a+',600),'policy_trial_storage_unavailable')
 if not lock:lock('tlock')then lock:close();error('policy_trial_busy')end
 held=true;local ok,a,b=pcall(action,...);held=false;lock:lock('ulock');lock:close();assert(ok,a);return a,b
end
M.locked=locked
for _,name in ipairs({'prepare','committed','discard_uncommitted','stop','restore','spec','sent','observe','action','recover_preparing'})do
 local action=M[name];M[name]=function(...)return locked(action,...)end
end
return M
