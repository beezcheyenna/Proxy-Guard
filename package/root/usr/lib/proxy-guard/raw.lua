-- Fixed-scope UCI editor. Secrets stay masked; drafts use the existing UCI session.
local M={}
local uci=require 'uci'
local json=require 'luci.jsonc'
local fs=require 'nixio.fs'
local core=require 'proxy-guard.core'
local base='/var/run/proxy-guard/raw'
local marker='__KEEP_SAVED_SECRET__'
local max=65536
local function target(name)
 assert(name=='proxy_guard' or name=='proxy_guard_access','raw_target_invalid');return name
end
local function read(path,limit)
 local f=io.open(path,'r');if not f then return nil end
 local text=f:read((limit or max)+1);f:close();assert(not text or #text<=(limit or max),'raw_too_large');return text or ''
end
local function write(path,text)
 local f=assert(io.open(path,'w'),'raw_storage_unavailable');assert(f:write(text));assert(f:close());fs.chmod(path,'600')
end
local function uuid()
 local v=(read('/proc/sys/kernel/random/uuid',100) or ''):gsub('%s','')
 assert(#v==36 and v:match('^[a-f0-9%-]+$'),'raw_random_unavailable');return v
end
local function uptime() return tonumber((read('/proc/uptime',100) or ''):match('^[%d%.]+')) or 0 end
local function boot() return (read('/proc/sys/kernel/random/boot_id',100) or ''):gsub('%s','') end
local function private_dir(path)
 assert(os.execute('umask 077; mkdir -p '..core.quote(path)..'; chmod 700 '..core.quote(path))==0,'raw_storage_unavailable')
end
local function secret(key) key=key:lower();return key:match('password') or key:match('secret') or key:match('token') or key:match('_key$') end
local function parse_file(path,name)
 local directory=assert(path:match('^(.*)/[^/]+$'),'raw_target_invalid')
 local c=uci.cursor(directory,base..'/empty');local ok=c:load(name);assert(ok,'raw_syntax_invalid')
 local result={};local count=0
 c:foreach(name,nil,function(v)
  count=count+1;assert(count<=64,'raw_too_many_sections')
  assert(type(v['.name'])=='string' and #v['.name']<=64 and v['.name']:match('^[A-Za-z0-9_%-]+$'),'raw_section_invalid')
  local options={};for k,value in pairs(v) do if k:sub(1,1)~='.' then options[k]=value end end
  result[v['.name']]={section_type=v['.type'],options=options}
 end)
 c:unload(name)
 assert(result.main and result.main.section_type==(name=='proxy_guard' and 'proxy_guard' or 'access'),'raw_main_required')
 for id,v in pairs(result) do
  assert(id=='main' or name=='proxy_guard_access' and v.section_type=='rule','raw_section_invalid')
  for key,value in pairs(v.options) do
   assert(type(key)=='string' and #key<=64 and key:match('^[A-Za-z0-9_%-]+$'),'raw_option_invalid')
   if type(value)=='table' then assert(#value<=256,'raw_list_invalid');for _,item in ipairs(value) do assert(type(item)=='string' and not item:find('%z'),'raw_value_invalid') end
   else assert(type(value)=='string' and not value:find('%z'),'raw_value_invalid') end
  end
 end
 return result
end
local function canonical(sections,masked)
 local names={};for id in pairs(sections) do names[#names+1]=id end
 table.sort(names,function(a,b)if a=='main' then return b~='main' elseif b=='main' then return false else return a<b end end)
 local lines={}
 for _,id in ipairs(names) do
  local section=sections[id];lines[#lines+1]='config '..section.section_type..' '..core.quote(id)
  local keys={};for key in pairs(section.options) do keys[#keys+1]=key end;table.sort(keys)
  for _,key in ipairs(keys) do
   local value=section.options[key]
   if masked and secret(key) and value~='' then value=marker end
   if type(value)=='table' then for _,v in ipairs(value) do lines[#lines+1]='\tlist '..key..' '..core.quote(v) end
   else lines[#lines+1]='\toption '..key..' '..core.quote(value) end
  end
  lines[#lines+1]=''
 end
 return table.concat(lines,'\n')
end
local function clone(value) return json.parse(json.stringify(value)) end
local function config_path(name) return '/etc/config/'..target(name) end
local function session_sections(name,sid)
 if sid==nil then return parse_file(config_path(name),name) end
 assert(type(sid)=='string' and #sid==32 and sid:match('^%x+$') and sid~=string.rep('0',32),'raw_session_invalid')
 local query=json.stringify({ubus_rpc_session=sid,config=name})
 local f=assert(io.popen('ubus -t 3 call uci get '..core.quote(query)..' 2>/dev/null','r'),'raw_session_unavailable')
 local text=f:read(262145) or '';f:close();assert(#text<=262144,'raw_too_large')
 local response=json.parse(text);assert(type(response)=='table' and type(response.values)=='table','raw_session_unavailable')
 local sections={}
 for id,v in pairs(response.values) do
  assert(type(v)=='table' and type(v['.type'])=='string','raw_section_invalid')
  local options={};for key,value in pairs(v) do if key:sub(1,1)~='.' then options[key]=value end end
  sections[id]={section_type=v['.type'],options=options}
 end
 return sections
end
function M.check(name,token,sid)
 target(name);assert(type(token)=='string' and #token==36 and token:match('^[a-f0-9%-]+$'),'raw_token_invalid')
 local text=read(base..'/'..name..'/'..token,524288);assert(text,'raw_snapshot_expired')
 local record=json.parse(text)
 assert(type(record)=='table' and record.name==name and record.boot==boot() and type(record.at)=='number' and uptime()>=record.at and uptime()-record.at<=3600,'raw_snapshot_expired')
 assert(record.sid==sid,'raw_session_invalid')
 assert(record.text==read(config_path(name)),'raw_configuration_changed')
 if sid then assert(canonical(session_sections(name,sid),false)==record.staged,'raw_staged_configuration_changed') end
 return record
end
function M.info(name,sid)
 target(name);private_dir(base..'/'..name);private_dir(base..'/empty')
 local entries={};for f in fs.dir(base..'/'..name) do
  if #f==36 and f:match('^[a-f0-9%-]+$') then local st=fs.stat(base..'/'..name..'/'..f);entries[#entries+1]={name=f,time=st and st.mtime or 0} end
 end
 table.sort(entries,function(a,b)return a.time<b.time end)
 for i=1,math.max(0,#entries-7) do os.remove(base..'/'..name..'/'..entries[i].name) end
 local text=assert(read(config_path(name)),'raw_configuration_unavailable')
 local template_path='/usr/share/proxy-guard/defaults/'..name
 local template=read(template_path) or ''
 local ok,sections=pcall(session_sections,name,sid)
 local token=uuid();write(base..'/'..name..'/'..token,json.stringify({name=name,text=text,at=uptime(),boot=boot(),sid=sid,sections=ok and sections or nil,staged=ok and canonical(sections,false) or nil}))
 return {ok=true,name=name,token=token,text=ok and canonical(sections,true) or template,template=template,template_loaded=not ok,secret_marker=marker,validation=ok and require('proxy-guard.config-schema').assess(name,sections) or nil}
end
function M.parse(name,text,token,sid)
 target(name);local record=M.check(name,token,sid)
 assert(type(text)=='string' and #text<=max and not text:find('%z'),'raw_text_invalid')
 private_dir(base)
 local dir=base..'/parse-'..uuid();assert(fs.mkdir(dir,'700'),'raw_storage_unavailable')
 local path=dir..'/'..name
 local ok,result=pcall(function()
  write(path,text)
  local sections=parse_file(path,name)
  local validation={}
  for id,section in pairs(sections) do
   local v=clone(section.options);v['.type']=section.section_type
   for key,value in pairs(v) do if value==marker then
    assert(secret(key),'raw_secret_marker_invalid');local old=record.sections and record.sections[id];v[key]=old and old.options[key] or nil
   end end
   validation[id]=v
  end
  if name=='proxy_guard' then core.load_config(validation.main)
  else require('proxy-guard.access').load(validation) end
  M.check(name,token,sid)
  return {ok=true,sections=sections,token=token,text=canonical(sections,true),validation=require('proxy-guard.config-schema').assess(name,sections,validation)}
 end)
 os.remove(path);fs.rmdir(dir)
 assert(ok,result);return result
end
M.serialize=canonical
return M
