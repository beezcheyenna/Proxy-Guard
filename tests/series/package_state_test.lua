local source=assert(os.getenv('PG_SOURCE'))
local original=io.open
local values={}
io.open=function(path)
 local value=values[path]
 if value==nil then return nil end
 return {read=function(_,n)return value:sub(1,n)end,close=function()end}
end
local state=assert(loadfile(source..'/package/root/usr/lib/proxy-guard/package-state.lua'))()
assert(state.in_progress()==false,'no package marker')
values['/var/run/proxy-guard-access/updating']='1234 99\n'
local fields={'S','1'}
for i=3,19 do fields[i]='0' end
fields[20]='99'
values['/proc/1234/stat']='1234 (opkg) '..table.concat(fields,' ')
assert(state.in_progress()==true,'live transaction must hold gate')
fields[20]='100';values['/proc/1234/stat']='1234 (opkg) '..table.concat(fields,' ')
assert(state.in_progress()==true and state.state()=='interrupted','PID reuse must not authorize an interrupted update')
values['/proc/1234/stat']=nil
assert(state.in_progress()==true and state.state()=='interrupted','dead transaction must remain closed until reinstall/removal')
values['/var/run/proxy-guard-access/updating']='damaged'
assert(state.in_progress()==true,'damaged marker must fail closed')
io.open=original
print('PASS live/dead/reused/corrupt package transaction markers')
