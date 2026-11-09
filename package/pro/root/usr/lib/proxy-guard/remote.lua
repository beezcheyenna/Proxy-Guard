-- Optional Pro gate. Cached health never replaces local proxy verification.
local M={}
local json=require 'luci.jsonc'
local function read(path)
 local f=io.open(path,'r');if not f then return nil end
 local s=f:read(65537);f:close();return s
end
function M.status()
 if require('proxy-guard.package-state').in_progress() then return {required=true,ok=false,stale=true,reason='VPS 健康状态不可用'} end
 local cursor=require('uci').cursor()
 local loaded=cursor:load('/etc/config/proxy_guard_access')
 if not loaded then return {required=true,ok=false,stale=true,reason='VPS 健康状态不可用'} end
 local enabled=cursor:get('proxy_guard_access','main','enabled')
 local gate=cursor:get('proxy_guard_access','main','health_guard')
 if (enabled~='0' and enabled~='1') or (gate~=nil and gate~='0' and gate~='1') then
  return {required=true,ok=false,stale=true,reason='VPS 健康状态不可用'}
 end
 local required=enabled=='1' and gate=='1'
 if not required then return {required=false} end
 local text=read('/var/run/proxy-guard-access/health.json')
 local ok,data=pcall(json.parse,text or '')
 local generation=read('/var/run/proxy-guard-access/generation')
 local up=tonumber((read('/proc/uptime') or ''):match('^[%d%.]+')) or 0
 local interval=tonumber(cursor:get('proxy_guard_access','main','health_interval')) or 10
 local fresh=ok and type(data)=='table' and data.generation==generation and type(data.checked_uptime)=='number' and
  data.checked_uptime<=up and up-data.checked_uptime<=math.max(15,interval*3)
 return {required=true,ok=fresh and data.ok==true or false,stale=not fresh,
  reason=not fresh and 'VPS 健康状态不可用' or data.ok and 'VPS 服务已就绪' or 'VPS 服务验证失败'}
end
return M
