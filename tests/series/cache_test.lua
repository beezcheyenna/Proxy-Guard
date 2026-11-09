local source=assert(os.getenv('PG_SOURCE'))
package.path=source..'/package/root/usr/lib/?.lua;'..package.path
local real_open=io.open
local json=require 'luci.jsonc'
local payload=json.stringify({ok=true,generation='cache-unit',checked_uptime=950,padding=string.rep('x',32768)})
package.loaded.uci={cursor=function() return {
 load=function() return true end,
 get=function(_,_,_,option) return ({enabled='1',health_guard='1',health_interval='60'})[option] end
} end}
io.open=function(path,mode)
 if path=="/var/run/proxy-guard-access/updating" then return nil end
 local value=path:match('health.json$') and payload or path:match('/generation$') and 'cache-unit' or path=='/proc/uptime' and '1000.0 0.0' or nil
 if value then return {read=function(_,n) return value:sub(1,n) end,close=function()end} end
 return real_open(path,mode)
end
local ok,result=pcall(function() return assert(loadfile(source..'/package/pro/root/usr/lib/proxy-guard/remote.lua'))().status() end)
io.open=real_open
assert(ok and result.required and result.ok and not result.stale,'bounded health response with framing was truncated')
print('PASS Pro cache parser accepts a bounded response plus local metadata')
