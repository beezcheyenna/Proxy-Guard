local root=assert(os.getenv('PG_SOURCE'))
package.path=root..'/package/root/usr/lib/?.lua;'..root..'/package/pro/root/usr/lib/?.lua;'..package.path
local fs=require 'nixio.fs';local nixio=require 'nixio';local json=require 'luci.jsonc';local uci=require 'uci'
assert(fs.access('/etc/pgvm-fixture'),'offline fixture required')
local T=require 'proxy-guard.access-trial';local access=require 'proxy-guard.access'
local dir='/etc/proxy-guard-access/trial';local config='/etc/config/proxy_guard_access'
local function read(p)local f=io.open(p);if not f then return nil end;local s=f:read('*a');f:close();return s end
local function write(p,s)local f=assert(io.open(p,'w'));assert(f:write(s));f:close()end
local n=0;local function check(v,label)assert(v,label);n=n+1;print('PASS '..label)end
local files={config,'/etc/proxy-guard-access/device.key','/etc/proxy-guard-access/path.key',dir..'/pending.json',dir..'/result.json',dir..'/pending.json.corrupt',dir..'/result.json.corrupt','/var/run/proxy-guard-access/trial-reload'}
local saved={};for _,p in ipairs(files)do saved[p]=read(p)or false end
assert(not T.pending(),'existing trial must finish before testing')
os.execute('umask 077; mkdir -p '..dir..' /var/run/proxy-guard-access; chmod 700 '..dir)
local owner=string.rep('a',32);local base="config access 'main'\n option enabled '0'\n option revision '10'\n option policy_enabled '0'\n"
local function reset()
 for _,p in ipairs({dir..'/pending.json',dir..'/result.json'})do os.remove(p)end
 write(config,base);write('/etc/proxy-guard-access/device.key',string.rep('d',40));write('/etc/proxy-guard-access/path.key',string.rep('p',40))
end
local function desired()
 return {main={['.type']='access',enabled='0',revision='10',policy_enabled='1'}}
end
local function candidate()
 write(config,"config access 'main'\n option enabled '0'\n option revision '11'\n option policy_enabled '1'\n")
end
local function mutate(fn)local p=json.parse(assert(read(dir..'/pending.json')));fn(p);write(dir..'/pending.json',json.stringify(p))end
local ok,why=pcall(function()
 reset();local p=T.prepare(owner,11,60,desired())
 check(T.public(owner).owned and not T.public(string.rep('b',32)).owned,'trial ownership is session specific')
 check(not T.recover_preparing(),'a live writer is not rolled back')
 check(not pcall(T.prepare,owner,12,60,desired()),'parallel Apply cannot replace a pending snapshot')
 mutate(function(v)v.writer='2147483647'end)
 check(T.recover_preparing()and not T.pending(),'killed writer before commit releases unchanged configuration')
 check(read(config)==base,'unchanged configuration bytes stay unchanged after failed prepare')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed()
 check(not pcall(T.action,'confirm',string.rep('b',32),T.pending().id),'another session cannot confirm')
 check(not pcall(T.action,'confirm',owner,T.pending().id),'a policy cannot be confirmed before remote readiness')
 p=T.pending();T.observe({policy_trial={id=p.id,revision=11,phase='confirming',remaining=60}})
 check(T.public(owner).phase=='confirming'and T.public(owner).remaining>0,'remote readiness starts the displayed confirmation window')
 T.action('confirm',owner,p.id)
 check(T.pending().action=='confirm','confirmation is durably queued')
 mutate(function(v)v.boot='old-boot'end)
 local spec,phase=T.spec({revision=11})
 check(spec and phase=='uncertain'and T.pending().phase=='uncertain','a lost confirmation reply is not assumed to be unconfirmed on reboot')
 T.observe({policy_trial={id=p.id,revision=11,phase='confirmed'}})
 check(not T.pending()and T.public(owner).last_result.phase=='confirmed','idempotent remote confirmation finalizes local snapshot')
 check(read(config):find("policy_enabled '1'",1,true),'confirmed candidate stays saved')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();p=T.pending()
 T.observe({policy_trial={id=p.id,revision=11,phase='rolled_back',reason='confirmation_timeout'}})
 local c=uci.cursor();c:load('proxy_guard_access')
 check(c:get('proxy_guard_access','main','policy_enabled')=='0','server timeout restores previous policy')
 check(c:get('proxy_guard_access','main','revision')=='11','rollback keeps the revision high water mark')
 check(read('/var/run/proxy-guard-access/trial-reload')=='1\n','rollback schedules restart outside the metadata lock')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();p=T.pending()
 T.observe({policy_trial={id=p.id,revision=11,phase='restoring',remaining=40}})
 check(T.public(owner).phase=='remote_restoring','server restoration is distinct from confirmable policy')
 local pending_spec,pending_reason=T.spec({revision=11})
 check(not pending_spec and pending_reason=='remote_restoring','ordinary sync cannot reapply a candidate while the server restores it')
 T.observe({policy_trial={id=p.id,revision=11,phase='rolled_back',reason='user_cancelled'}})
 check(not T.pending(),'completed server restoration finalizes local restoration')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();write(config,assert(read(config))..'\n# another writer\n')
 check(T.restore('timeout',true).phase=='conflict','concurrent saved edit prevents blind restore')
 check(read(config):find('# another writer',1,true),'external configuration is preserved')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();write('/etc/proxy-guard-access/device.key',string.rep('x',40))
 check(T.restore('timeout',true).phase=='conflict','concurrent private credential edit prevents blind restore')
 check(read('/etc/proxy-guard-access/device.key')==string.rep('x',40),'external private key is preserved')
 reset();T.prepare(owner,11,60,desired());candidate()
 mutate(function(v)v.writer='2147483647'end)
 T.recover_preparing();c=uci.cursor();c:load('proxy_guard_access')
 check(not T.pending()and c:get('proxy_guard_access','main','policy_enabled')=='0','killed writer after UCI commit restores matching candidate')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();p=T.pending()
 local work=dir..'/restore-'..p.id;assert(fs.mkdir(work,'700'));assert(fs.mkdir(work..'/savedir','700'));write(work..'/proxy_guard_access','interrupted')
 check(T.restore('user_cancelled',true).phase=='rolled_back','interrupted restore resumes safely from its owned temporary directory')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();p=T.pending()
 T.observe({revision=12,policy_trial={id='another-trial',revision=12,phase='confirmed'}})
 check(T.public(owner).last_result.phase=='conflict','a newer external VPS policy is reported as a conflict, not as confirmation')
 check(read(config):find("policy_enabled '1'",1,true),'remote conflict does not overwrite local candidate settings')
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();T.stop()
 check(not T.pending()and T.public(owner).last_result.phase=='stopped','explicit synchronization stop wins over rollback')
 check(read(config):find("policy_enabled '1'",1,true),'stopping synchronization does not silently undo saved configuration')
 reset();local zombie_ready='/tmp/pg-access-zombie-ready';os.remove(zombie_ready);io.stdout:flush()
 local zombie=nixio.fork();assert(zombie)
 if zombie==0 then T.prepare(owner,11,60,desired());write(zombie_ready,'ready');nixio.nanosleep(30,0);os.exit(0)end
 for i=1,1000 do if read(zombie_ready)then break end;nixio.nanosleep(0,10000000)end
 assert(read(zombie_ready));nixio.kill(zombie,9)
 local zombie_state
 for i=1,100 do zombie_state=(read('/proc/'..zombie..'/stat')or''):match('^%d+ %b() (%S+)');if zombie_state=='Z'then break end;nixio.nanosleep(0,10000000)end
 check(zombie_state=='Z','killed writer exists as an unreaped zombie')
 check(T.recover_preparing()and not T.pending(),'a zombie writer is recovered before its parent reaps it')
 check(read(config)==base,'zombie recovery preserves an uncommitted configuration')
 nixio.waitpid(zombie);os.remove(zombie_ready)
 reset();T.prepare(owner,11,60,desired());candidate();T.committed();local orphan=T.pending();local orphan_bytes=read(dir..'/pending.json')
 T.observe({policy_trial={id=orphan.id,revision=11,phase='confirmed'}});write(dir..'/pending.json',orphan_bytes)
 check(not T.pending(),'a durable completed outcome remains authoritative after an interrupted unlink')
 check(access.recover_trial()and not fs.access(dir..'/pending.json'),'independent recovery removes only the completed orphan snapshot')
 for _,after_commit in ipairs({false,true})do
  reset();local ready='/tmp/pg-access-trial-writer-ready';os.remove(ready);io.stdout:flush()
  local writer=nixio.fork();assert(writer)
  if writer==0 then
   local success,error=pcall(function()T.prepare(owner,11,60,desired());if after_commit then candidate()end;write(ready,'ready');nixio.nanosleep(30,0)end)
   if not success then io.stderr:write(tostring(error)..'\n')end;os.exit(success and 0 or 2)
  end
  for i=1,1000 do if read(ready)then break end;nixio.nanosleep(0,10000000)end
  check(read(ready)=='ready','real writer reached crash boundary '..tostring(after_commit))
  nixio.kill(writer,9);nixio.waitpid(writer);os.remove(ready)
  check(T.recover_preparing()and not T.pending(),'SIGKILL releases writer lock and interrupted transaction '..tostring(after_commit))
  local current=uci.cursor();current:load('proxy_guard_access')
  check(current:get('proxy_guard_access','main','policy_enabled')=='0','SIGKILL recovery restores original policy '..tostring(after_commit))
 end
 reset();local target=desired();target.main.device_token=string.rep('e',40);target.main.path_token=string.rep('q',40)
 T.prepare(owner,11,60,target);candidate();write('/etc/proxy-guard-access/device.key',string.rep('e',40));write('/etc/proxy-guard-access/path.key',string.rep('q',40));T.committed()
 local marker='/tmp/pg-access-restore-mid-key';os.remove(marker);io.stdout:flush()
 local child=nixio.fork();assert(child)
 if child==0 then
  local rename=os.rename;local signalled=false
  os.rename=function(from,to)
   local result,error=rename(from,to)
   if result and not signalled and (to=='/etc/proxy-guard-access/device.key'or to=='/etc/proxy-guard-access/path.key')then signalled=true;write(marker,'ready');nixio.nanosleep(30,0)end
   return result,error
  end
  local success,error=pcall(T.restore,'user_cancelled',true);if not success then io.stderr:write(tostring(error)..'\n')end;os.exit(success and 0 or 2)
 end
 for i=1,1000 do if read(marker)then break end;nixio.nanosleep(0,10000000)end
 check(read(marker)=='ready','restore reached a real partial credential-write boundary')
 check(not pcall(access.load_current),'network configuration cannot observe a partial credential pair')
 local sid=os.getenv('PG_RPC_SID')
 if sid then
  local request=json.stringify({ubus_rpc_session=sid});local unchanged=read(config)
  local f=assert(io.popen('ubus -t 10 call proxy_guard_access apply '..require('proxy-guard.core').quote(request)..' 2>/dev/null'))
  local reply=json.parse(f:read('*a'));f:close()
  check(reply and reply.error=='policy_trial_busy'and read(config)==unchanged,'real concurrent Apply is rejected before committing over a running restore')
 end

 nixio.kill(child,9);nixio.waitpid(child);os.remove(marker)
 check(T.pending().phase=='restoring','restore intent was durable before credentials changed')
 check(T.restore('interrupted_restore',true).phase=='rolled_back','SIGKILL during restore resumes without a false external-edit conflict')
 check(read('/etc/proxy-guard-access/device.key')==string.rep('d',40)and read('/etc/proxy-guard-access/path.key')==string.rep('p',40),'interrupted restore recovers both previous private credentials')
 local restored=uci.cursor();restored:load('proxy_guard_access');check(restored:get('proxy_guard_access','main','policy_enabled')=='0','interrupted restore recovers its matching previous configuration')
 reset()
 local flag='/tmp/pg-access-trial-lock-ready';os.remove(flag)
 io.stdout:flush();local pid=nixio.fork();assert(pid)
 if pid==0 then
  local f=assert(nixio.open('/var/lock/proxy-guard-access-trial.lock','a+',600));assert(f:lock('tlock'));write(flag,'ready');nixio.nanosleep(1,0);f:lock('ulock');f:close();os.exit(0)
 end
 for i=1,100 do if read(flag)then break end;nixio.nanosleep(0,10000000)end
 check(read(flag)=='ready','concurrent process owns real nixio lock')
 check(not pcall(T.prepare,owner,11,60,desired()),'metadata contention fails promptly rather than waiting for RPC timeout')
 nixio.waitpid(pid);os.remove(flag)
 check(T.prepare(owner,11,60,desired())~=nil,'metadata lock is available after the child exits')
 T.discard_uncommitted()
 local st=assert(fs.stat(dir));check(st.modestr=='rwx------','private snapshots directory is owner-only')
 reset();local public=T.public;T.public=function()error('policy_trial_storage_invalid')end
 local raced_status=access.status(owner);T.public=public
 check(raced_status.phase=='error'and raced_status.error=='policy_trial_storage_invalid','a failed confirmation read after the configuration snapshot cannot crash status RPC')
 reset();write(dir..'/pending.json','{broken')
 local sid=os.getenv('PG_RPC_SID')
 if sid then
  local f=assert(io.popen('ubus -t 15 call proxy_guard_access apply '..require('proxy-guard.core').quote(json.stringify({ubus_rpc_session=sid}))..' 2>/dev/null'))
  local reply=json.parse(f:read('*a'));f:close();check(reply and reply.ok,'explicit off remains applicable even with a corrupt trial journal')
 else T.stop()end
 check(not T.pending()and T.public(owner).last_result.remote_known==false,'corrupt stop cannot claim that the remote rules were removed')
 check(read(dir..'/pending.json.corrupt')=='{broken','corrupt private journal is retained privately for diagnosis')
 write(dir..'/result.json','{broken')
 local status=access.status(owner)
 check(status.phase=='error'and status.error=='policy_trial_storage_invalid','corrupt result-only history returns a structured status error')
 local unchanged=read(config)
 check(not pcall(T.prepare,owner,11,60,desired())and read(config)==unchanged and not fs.access(dir..'/pending.json'),'corrupt history prevents a new transaction before any commit')
 if sid then
  local f=assert(io.popen('ubus -t 10 call proxy_guard_access status '..require('proxy-guard.core').quote(json.stringify({ubus_rpc_session=sid}))..' 2>/dev/null'))
  local reply=json.parse(f:read('*a'));f:close()
  check(reply and reply.phase=='error'and reply.error=='policy_trial_storage_invalid','real status RPC responds normally to corrupt result-only history')
 end
 T.stop();check(T.public(owner).last_result.phase=='stopped','explicit off also recovers a corrupt result-only record')

end)
for _,p in ipairs(files)do if saved[p]then write(p,saved[p])else os.remove(p)end end
os.remove(dir..'/pending.json.new');os.remove(dir..'/result.json.new')
assert(ok,why);print('PASS '..n..' native local policy-trial checks')
