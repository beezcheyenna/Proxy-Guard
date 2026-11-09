-- Optional DNS-format UDP check through SOCKS5 UDP ASSOCIATE. No direct fallback.
local M={}
local function uptime()
    local f=assert(io.open('/proc/uptime','r'));local value=f:read('*l');f:close();return assert(tonumber(value:match('^[%d%.]+')))
end
local function u16(n) return string.char(math.floor(n/256)%256,n%256) end
local function value16(s,p) return assert(s:byte(p))*256+assert(s:byte(p+1)) end
local function ipv4(s) local t={};for v in s:gmatch('%d+') do t[#t+1]=tonumber(v) end;return string.char(unpack(t)) end
local function question(name)
    local out={};for label in name:lower():gmatch('[^.]+') do out[#out+1]=string.char(#label)..label end
    return table.concat(out)..'\0'..u16(1)..u16(1)
end
local function dns_name(data,start)
    local labels,seen={},{};local at,ending=start,nil
    for _=1,128 do
        assert(not seen[at]);seen[at]=true
        local length=assert(data:byte(at));at=at+1
        if length==0 then return table.concat(labels,'.'):lower(),ending or at end
        if length>=192 then
            local other=assert(data:byte(at));ending=ending or at+1;at=(length-192)*256+other+1
        else
            assert(length<=63 and at+length-1<=#data)
            labels[#labels+1]=data:sub(at,at+length-1);at=at+length
        end
    end
    error('name_loop')
end
function M.valid_dns(data,id,name)
    local ok,valid=pcall(function()
        assert(#data>=12 and data:sub(1,2)==id)
        local hi,lo=data:byte(3,4)
        assert(hi>=128 and math.floor((hi%128)/8)==0 and math.floor(hi/2)%2==0 and lo%16==0)
        assert(value16(data,5)==1)
        local q,at=dns_name(data,13)
        return q==name:lower() and value16(data,at)==1 and value16(data,at+2)==1
    end)
    return ok and valid==true
end
function M.available()
    local ok,n=pcall(require,'nixio')
    return ok and type(n.socket)=='function' and type(n.poll)=='function' and type(n.poll_flags)=='function'
end
function M.probe(c)
    if not M.available() then return {enabled=true,ok=false,code='module_unavailable'} end
    local n=require 'nixio';local sockets={};local began=uptime();local deadline=began+c.udp_timeout
    local stage='socket'
    local function socket(family,kind)
        local s=assert(n.socket(family,kind));sockets[#sockets+1]=s;assert(s:setblocking(false));return s
    end
    local function wait(s,kind)
        local left=deadline-uptime();assert(left>0,'deadline')
        local count=n.poll({{fd=s,events=n.poll_flags(kind)}},math.max(1,math.ceil(left*1000)))
        assert(count and count>0,'timeout')
    end
    local function connect(s,host,port)
        local ok=s:connect(host,port)
        if not ok then wait(s,'out');assert(s:getopt('socket','error')==0,'connect') end
    end
    local function send(s,data)
        local at=1
        while at<=#data do wait(s,'out');local sent=s:send(data:sub(at));assert(sent and sent>0);at=at+sent end
    end
    local function exact(s,length)
        local out=''
        while #out<length do wait(s,'in');local part=s:recv(length-#out);assert(part and #part>0,'eof');out=out..part end
        return out
    end
    local ok,why=pcall(function()
        stage='socks_connect';local control=socket('inet','stream');connect(control,'127.0.0.1',c.socks_port)
        stage='socks_method'
        local auth
        if c._socks_auth_file then
            assert(c._socks_auth_file:match('^/var/run/proxy%-guard/socks%-[a-z0-9]+%-%d+%.json$'),'auth_path')
            local file=assert(io.open(c._socks_auth_file,'rb'));local text=file:read(2049);file:close();assert(text and #text<=2048)
            auth=require('luci.jsonc').parse(text)
            assert(type(auth)=='table' and type(auth.username)=='string' and type(auth.password)=='string')
            assert(#auth.username>=1 and #auth.username<=255 and #auth.password<=255)
        end
        send(control,auth and '\5\2\0\2' or '\5\1\0')
        local method=exact(control,2)
        if method=='\5\2' and auth then
            stage='socks_authentication'
            send(control,'\1'..string.char(#auth.username)..auth.username..string.char(#auth.password)..auth.password)
            assert(exact(control,2)=='\1\0')
        else assert(method=='\5\0') end
        stage='socks_associate';send(control,'\5\3\0\1'..string.rep('\0',6))
        local header=exact(control,4);assert(header:sub(1,3)=='\5\0\0')
        local atyp=header:byte(4);local family,address
        if atyp==1 then
            local raw=exact(control,4);local a,b,d,e=raw:byte(1,4)
            assert(a==127 or raw==string.rep('\0',4),'nonlocal_relay')
            family='inet';address=raw==string.rep('\0',4) and '127.0.0.1' or table.concat({a,b,d,e},'.')
        elseif atyp==4 then
            local raw=exact(control,16);assert(raw==string.rep('\0',16) or raw==string.rep('\0',15)..'\1','nonlocal_relay')
            family='inet6';address='::1'
        else error('unsupported_relay') end
        local port=value16(exact(control,2),1);assert(port>0)
        local udp=socket(family,'dgram');connect(udp,address,port)
        local random=assert(io.open('/dev/urandom','rb'));local id=random:read(2);random:close();assert(id and #id==2)
        local request=id..'\1\0'..u16(1)..string.rep('\0',6)..question(c.udp_query)
        local packet='\0\0\0\1'..ipv4(c.udp_server)..u16(c.udp_port)..request
        stage='udp_send';wait(udp,'out');assert(udp:send(packet)==#packet)
        stage='udp_reply';wait(udp,'in');local reply=assert(udp:recv(4096));assert(#reply>=22)
        stage='udp_envelope';assert(reply:sub(1,4)=='\0\0\0\1' and reply:sub(5,8)==ipv4(c.udp_server) and value16(reply,9)==c.udp_port)
        stage='dns_response';assert(M.valid_dns(reply:sub(11),id,c.udp_query))
    end)
    for _,s in ipairs(sockets) do pcall(s.close,s) end
    return {enabled=true,ok=ok,code=ok and 'passed' or stage,milliseconds=math.floor((uptime()-began)*1000)}
end
return M
