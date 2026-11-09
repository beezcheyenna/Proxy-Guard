-- One auxiliary Cloudflare attempt per boot/outage; all times are RAM-only.
-- The caller owns locking and must persist begin() before performing any I/O.
local M={}
local function integer(v) return type(v)=='number' and v>=0 and v==math.floor(v) and v<1000000000 end
local outcomes={ok=true,unavailable=true,mismatch=true,interrupted=true}
local function identifier(v) return type(v)=='string' and #v<=160 and not v:find('[%c]') end
function M.load(old,boot_id)
    if type(old)=='table' and old.schema==1 and old.boot_id==boot_id and
        integer(old.sequence) and old.sequence>=1 and type(old.pending)=='boolean' and
        type(old.attempted)=='boolean' and type(old.armed)=='boolean' and type(old.network_fault)=='boolean' and
        (old.last_fault_id==nil or identifier(old.last_fault_id)) and
        integer(old.confirmations or 0) and (old.confirmations or 0)<=10 and
        integer(old.mismatch_required or 0) and (old.mismatch_required or 0)<=10 and
        (old.pending or old.attempted) then
        local r=old.result
        if type(r)~='table' or not outcomes[r.outcome] or
            (r.checked_at~=nil and (type(r.checked_at)~='number' or r.checked_at<0 or r.checked_at>9007199254740991)) or
            (r.expected~=nil and (type(r.expected)~='string' or #r.expected>64)) or
            (r.observed~=nil and (type(r.observed)~='string' or #r.observed>64)) or
            (r.colo~=nil and (type(r.colo)~='string' or not r.colo:match('^%u%u%u$'))) or
            (r.http_code~=nil and (not integer(r.http_code) or r.http_code>999)) or
            (r.curl_code~=nil and (not integer(r.curl_code) or r.curl_code>255)) then
            old.result=old.attempted and {outcome='interrupted'} or nil
        end
        return old
    end
    return {schema=1,boot_id=boot_id,sequence=1,pending=true,attempted=false,armed=false,
        network_fault=false,confirmations=0,mismatch_required=0}
end
local function incident(s)
    s.sequence=s.sequence+1;s.pending=true;s.attempted=false;s.armed=false
    -- A previous contradictory response still needs fresh primary validation.
    s.confirmations=0
end
function M.observe(s,o)
    local new_local=identifier(o.fault_id) and o.fault_id~=s.last_fault_id
    if new_local then
        s.last_fault_id=o.fault_id
        if not s.pending then incident(s) end
    end
    if o.primary_fault and not s.network_fault then
        if s.armed and not s.pending then incident(s) end
        s.network_fault=true
    end
    if o.recovered then s.armed=true;s.network_fault=false end
    return s
end
function M.pending(s) return s.pending==true end
function M.begin(s,wall,expected)
    if not s.pending then return false end
    s.pending=false;s.attempted=true
    s.result={outcome='interrupted',checked_at=wall,expected=expected}
    return true
end
function M.finish(s,result,wall,required)
    s.result={outcome=result.outcome,observed=result.observed,colo=result.colo,
        http_code=result.http_code,curl_code=result.curl_code,checked_at=wall,
        expected=s.result and s.result.expected or nil}
    if result.outcome=='mismatch' then
        s.mismatch_required=math.max(2,required or 2);s.confirmations=0
    end
    return s
end
function M.qualify(s,primary_ok)
    if (s.mismatch_required or 0)==0 then return true end
    if not primary_ok then s.confirmations=0;return false end
    s.confirmations=math.min(s.mismatch_required,(s.confirmations or 0)+1)
    if s.confirmations<s.mismatch_required then return false end
    s.mismatch_required=0
    return true
end
function M.status(s,enabled)
    local out={enabled=enabled==true,pending=s.pending==true,attempted=s.attempted==true,
        event_id=s.sequence,rechecking=(s.mismatch_required or 0)>0,
        confirmations=s.confirmations or 0,required=s.mismatch_required or 0}
    for k,v in pairs(s.result or {}) do
        if k=='outcome' or k=='checked_at' or k=='expected' or k=='observed' or k=='colo' or k=='http_code' or k=='curl_code' then out[k]=v end
    end
    return out
end
return M
