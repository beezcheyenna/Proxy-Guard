-- An interrupted update must not silently remove a required Pro gate.
local M={}
local function read(path,max)
 local f=io.open(path,'r');if not f then return nil end
 local s=f:read(max or 8192);f:close();return s
end
function M.state()
 local marker=read('/var/run/proxy-guard-access/updating',128)
 if not marker then return 'none' end
 local pid,started=marker:match('^(%d+) (%d+)%s*$')
 if not pid or not started then return 'invalid' end
 local stat=read('/proc/'..pid..'/stat')
 if not stat then return 'interrupted' end
 local fields={}
 for part in (stat:match('^.*%) (.*)$') or ''):gmatch('%S+') do fields[#fields+1]=part end
 return fields[20]==started and 'active' or 'interrupted'
end
function M.in_progress()
 return M.state()~='none'
end
return M
