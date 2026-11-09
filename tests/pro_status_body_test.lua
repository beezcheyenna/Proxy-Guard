-- Exercise the request expression with real native luci.jsonc, not a stub.
local root=os.getenv('PG_SOURCE') or '/src'
local json=require 'luci.jsonc'
local f=assert(io.open(root..'/package/pro/root/usr/lib/proxy-guard/access.lua'))
local source=f:read('*a');f:close()
local expression=assert(source:match('local status_body=(%b{})'),'missing status body')
local c={device_id='native_status_regression'}
local eval=assert(loadstring('return function(c) return '..expression..' end'))()
local encoded=json.stringify(eval(c))
assert(encoded:sub(1,1)=='{','Worker status body must be a JSON object: '..encoded)
local value=json.parse(encoded)
assert(value.device_id==c.device_id,'Worker status body must bind the configured device')
assert(json.stringify({})=='[]','test must use the actual OpenWrt empty-table encoding')
print('PASS native status JSON object and configured device binding; empty table reproduces []')
