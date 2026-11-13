-- Exercise the real log writer at both ends of the supported size range.
package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
assert(io.open('/etc/pgvm-fixture','r'),'isolated fixture required')
local ext=require 'proxy-guard.extensions'
local function up(f,key)
 for i=1,64 do local n,v=debug.getupvalue(f,i);if n==key then return v,i end end
 error('missing upvalue '..key)
end
local mutate=up(ext.request_block,'mutate');local event=up(mutate,'event')
local old,index=up(event,'run');local root='/tmp/pg-heartbeat-log-test'
assert(os.execute('mkdir -p '..root)==0);debug.setupvalue(event,index,root)
for _,kib in ipairs({16,512})do
 local path=root..'/api-events.jsonl'
 local f=assert(io.open(path,'w'));assert(f:write(string.rep('x',kib*1024+1)));f:close()
 event({log_kib=kib},'api_block','rotation fixture')
 f=assert(io.open(path..'.1','r'));assert(f:seek('end')==kib*1024+1);f:close()
 f=assert(io.open(path,'r'));local line=f:read('*a');f:close()
 assert(#line<1024 and line:find('rotation fixture',1,true))
 os.remove(path);os.remove(path..'.1')
end
debug.setupvalue(event,index,old)
print('PASS 2 real heartbeat/API log rotation boundaries')
