-- SPDX-License-Identifier: MIT
-- Bounded protocol parser. Optional diagnostic fields never determine health.
local core=require 'proxy-guard.core'
local M={body='ネットは広大だわ'}
local schema={
 ['x-pghb-ip']={'ip','ip'},['x-pghb-country']={'country','country'},['x-pghb-asn']={'asn','integer'},
 ['x-pghb-tls']={'tls','text'},['x-pghb-ray']={'ray','text'},['x-pghb-nonce']={'nonce','nonce'}
}
local function ip(v)
 return not v:find('/',1,true) and (core.cidr(v,4) or core.cidr(v,6))
end
local function typed(value,kind)
 if #value>256 or value:find('[%z\1-\31\127]') then return nil end
 if kind=='ip' then return ip(value) and value or nil end
 if kind=='country' then return #value==2 and value:match('^[A-Z0-9]+$') and value or nil end
 if kind=='nonce' then return #value>=1 and #value<=128 and value:match('^[%w_-]+$') and value or nil end
 if kind=='integer' then
  if not value:match('^%d+%.?%d*$') or #value>20 then return nil end
  local n=tonumber(value)
  return n<=9007199254740991 and n==math.floor(n) and n or nil
 end
 return value~='' and value or nil
end
-- JSON strings carry UTF-8. Preserve any other header bytes with explicit encoding.
local function utf8(value)
 if not value:find('[\128-\255]') then return true end
 if value:find('^[\128-\191]') then return false end
 for sequence in value:gmatch('[^\128-\191][\128-\191]*') do
  local lead,next_byte=sequence:byte(1,2)
  local length=#sequence
  if lead<128 and length==1 then
  elseif lead>=194 and lead<=223 and length==2 then
  elseif lead>=224 and lead<=239 and length==3 and
         (lead~=224 or next_byte>=160) and (lead~=237 or next_byte<=159) then
  elseif lead>=240 and lead<=244 and length==4 and
         (lead~=240 or next_byte>=144) and (lead~=244 or next_byte<=143) then
  else return false end
 end
 return true
end
local function diagnostic_header(name,value)
 if utf8(value) then return {name=name,value=value} end
 return {name=name,value=require('nixio').bin.b64encode(value),encoding='base64'}
end
function M.headers(raw,capture)
 if type(raw)~='string' or #raw>32768 or raw:find('[%z\1-\8\11\12\14-\31\127]') then return nil,'invalid_headers' end
 raw=raw:gsub('\r\n','\n')
 if raw:find('\r',1,true) then return nil,'invalid_headers' end
 local fields,seen,headers,code,closed=nil,nil,nil,nil,true
 for line in (raw..'\n'):gmatch('(.-)\n') do
  if line:match('^HTTP/') then
   if not closed then return nil,'invalid_headers' end
   code=tonumber(line:match('^HTTP/[%d%.]+ (%d%d%d)'))
   if not code then return nil,'invalid_status' end
   fields={};seen={};headers=capture and {} or nil;closed=false
  elseif line=='' then closed=true
  else
   if not fields or closed or line:match('^[ \t]') then return nil,'invalid_headers' end
   local name,value=line:match('^([%w!#$%%&\'*+%.%^_`|~%-]+):[ \t]*(.-)[ \t]*$')
   if not name then return nil,'invalid_headers' end
   local lower=name:lower()
   if headers and lower:match('^x%-pghb%-.+') then
    headers[#headers+1]=diagnostic_header(name,value)
   end
   name=lower;local def=schema[name]
   if def then
    if seen[name] and (name=='x-pghb-ip' or name=='x-pghb-nonce') then return nil,'duplicate_security_header' end
    -- Ambiguous optional metadata is omitted instead of affecting protection.
    if seen[name] then fields[def[1]]=nil else fields[def[1]]=typed(value,def[2]) end
    seen[name]=true
   end
  end
 end
 if not fields or not closed then return nil,'invalid_headers' end
 local ip_reason=not fields.ip and (seen['x-pghb-ip'] and 'invalid_ip' or 'missing_ip') or nil
 return fields,nil,code,ip_reason,headers
end
function M.verify(rc,code,body,raw,nonce,expected,capture)
 local fields,why,header_code,ip_reason,headers=M.headers(raw,capture)
 -- A complete HTTP error response can contain useful diagnostics even if
 -- the endpoint could not echo the nonce or curl declined an oversized body.
 if capture and code>=400 and header_code==code and (rc==0 or rc==63) then
  return false,'http_status',fields,nil,headers
 end
 if rc~=0 then return false,'transport_error',fields end
 if code~=200 or header_code and header_code~=200 then return false,'http_status' end
 if not fields then return false,why end
 local nonce_matches=not nonce or fields.nonce==nonce
 local received=nonce_matches and headers or nil
 if body~=M.body then return false,'body_mismatch',fields,nil,received end
 if not nonce_matches then return false,'nonce_mismatch',fields end
 if expected and fields.ip~=expected then
  return false,fields.ip and 'ip_mismatch' or 'ip_unavailable',fields,ip_reason,received
 end
 return true,nil,fields,ip_reason,received
end
function M.metadata(fields)
 local out={}
 for k,v in pairs(fields or {})do if k~='nonce' then out[k]=v end end
 return out
end
return M
