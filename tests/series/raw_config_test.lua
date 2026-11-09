local root=os.getenv('PG_SOURCE') or '/src'
package.path=root..'/package/root/usr/lib/?.lua;'..root..'/package/pro/root/usr/lib/?.lua;'..package.path
local raw=require 'proxy-guard.raw'
local fs=require 'nixio.fs'
local n=0
local function check(v,label)assert(v,label);n=n+1 end
local function read(p)local f=assert(io.open(p));local t=f:read('*a');f:close();return t end
local function write(p,t)local f=assert(io.open(p,'w'));assert(f:write(t));f:close() end
assert(fs.access('/etc/pgvm-fixture'),'offline fixture required')
local core_before=read('/etc/config/proxy_guard')
local pro_before=read('/etc/config/proxy_guard_access')
local ok,err=pcall(function()
 for _,name in ipairs({'proxy_guard','proxy_guard_access'}) do
  local info=raw.info(name);check(info.ok and #info.token==36 and #info.text>0,'masked configuration read '..name)
  local parsed=raw.parse(name,info.text,info.token);check(parsed.ok and parsed.sections.main,'valid source round trip '..name)
  check(not pcall(raw.parse,name,"config 'broken",info.token),'invalid syntax rejected '..name)
  check(not pcall(raw.parse,name,info.text..string.char(0),info.token),'NUL rejected '..name)
  check(not pcall(raw.parse,name,string.rep('x',65537),info.token),'oversized text rejected '..name)
  check(not pcall(raw.parse,name,info.text,'../../etc/passwd'),'foreign path token rejected '..name)
 end
 check(not pcall(raw.info,'network'),'foreign config cannot be read')
 local info=raw.info('proxy_guard')
 local payload="a'b\\c ; $(touch /tmp/pg-raw-injected)"
 local quote=require('proxy-guard.core').quote
 local injected=info.text..'\nconfig proxy_guard main\n option enabled 0\n option note '..quote(payload)..'\n'
 -- A duplicate main may be rejected by UCI; use a complete independent document.
 injected='config proxy_guard main\n option enabled 0\n option note '..quote(payload)..'\n'
 local parsed=raw.parse('proxy_guard',injected,info.token)
 check(parsed.sections.main.options.note==payload,'apostrophe and backslash round trip without execution')
 check(parsed.validation and parsed.validation.syntax_valid and not parsed.validation.activation_parameters_valid,'disabled incomplete configuration is not reported as activation-ready')
 check(parsed.validation.unknown_fields[1]=='main.note','unknown raw values are preserved but explicitly warned')
 local invalid=raw.parse('proxy_guard',"config proxy_guard main\n option enabled 0\n option interval nope\n",info.token)
 check(not invalid.validation.activation_parameters_valid,'invalid disabled numbers fail activation assessment')
 local core=require 'proxy-guard.core'
 local disabled6=core.config({enabled='0',ipv6_protect='0'})
 check(disabled6.ipv6_protect==false and #disabled6.sources6==0,'explicit IPv6 exclusion survives an absent UCI list')
 check(core.config({enabled='0'}).schedule_enabled==false,'new or missing public schedule defaults off')
 check(core.config({enabled='0',schedule_enabled='1'}).schedule_enabled==true,'existing explicit schedules remain enabled')
 check(not fs.access('/tmp/pg-raw-injected'),'raw values are never executed')
 check(read('/etc/config/proxy_guard')==core_before,'validation leaves saved core configuration unchanged')
 local secret=string.rep('s',40)
 write('/etc/config/proxy_guard_access',"config access main\n option enabled 0\n option device_token '"..secret.."'\n")
 write('/etc/config/proxy_guard_access',"config access main\n option enabled 0\n option endpoint 'https://example.test'\n option device_id home\n option direct_confirmed 1\n option device_token '"..secret.."'\n")
 local masked=raw.info('proxy_guard_access')
 check(not masked.text:find(secret,1,true) and masked.text:find('__KEEP_SAVED_SECRET__',1,true),'legacy secret is masked')
 check(raw.parse('proxy_guard_access',masked.text,masked.token).sections.main.options.device_token=='__KEEP_SAVED_SECRET__','secret placeholder remains opaque in parse reply')
 check(raw.parse('proxy_guard_access',masked.text,masked.token).validation.activation_parameters_valid,'activation assessment resolves existing secret placeholders without exporting them')
 write('/etc/config/proxy_guard_access',pro_before)
 local baseline=raw.info('proxy_guard_access')
 write('/etc/config/proxy_guard_access',pro_before..'\n# concurrent change\n')
 check(not pcall(raw.parse,'proxy_guard_access',baseline.text,baseline.token),'concurrent saved update rejected')
 write('/etc/config/proxy_guard_access',pro_before)
 check(raw.check('proxy_guard_access',baseline.token),'matching saved configuration accepted')
 check(not pcall(raw.parse,'proxy_guard',info.text,baseline.token),'tokens cannot cross config boundaries')
end)
write('/etc/config/proxy_guard',core_before);write('/etc/config/proxy_guard_access',pro_before)
assert(ok,err)
print('PASS '..n..' native raw-config syntax, secret, scope, concurrency and no-execution checks')
