-- Pure configuration, state and firewall policy; no network or filesystem effects.
local M = {}
M.VERSION = '0.3.0'

function M.quote(value)
    return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function list(value)
    if type(value) == 'table' then return value end
    if value == nil or value == '' then return {} end
    return {value}
end

local function number(value, default, low, high, label)
    local n = tonumber(value == nil and default or value)
    assert(n and n == math.floor(n) and n >= low and n <= high, label .. ' 超出允许范围')
    return n
end

local function clock_seconds(value)
    assert(type(value)=='string','定时时间须为 HH:MM:SS')
    local h,m,s=value:match('^(%d%d):(%d%d):(%d%d)$')
    assert(h and tonumber(h)<24 and tonumber(m)<60 and tonumber(s)<60,'定时时间须为 HH:MM:SS（00:00:00 至 23:59:59）')
    return tonumber(h)*3600+tonumber(m)*60+tonumber(s)
end

local function hour(seconds)
    return string.format('%02d:%02d:%02d',math.floor(seconds/3600),math.floor(seconds/60)%60,seconds%60)
end

local function utc_offset(value)
    assert(type(value)=='string','UTC 时区偏移无效')
    local sign,h,m=value:match('^([+-])(%d%d):(%d%d)$')
    assert(sign and tonumber(m)<60 and tonumber(m)%15==0,'UTC 时区偏移须为 ±HH:MM，分钟为 00、15、30 或 45')
    local minutes=(tonumber(h)*60+tonumber(m))*(sign=='-' and -1 or 1)
    assert(minutes>=-720 and minutes<=840,'UTC 时区偏移须在 -12:00 至 +14:00 之间')
    return minutes*60
end

local function weekday(local_day)
    -- ISO weekday: Monday=1 ... Sunday=7; Unix epoch began on Thursday.
    return (math.floor(local_day/86400)+3)%7+1
end

local function ipv4(s)
    local a,b,c,d = s:match('^(%d+)%.(%d+)%.(%d+)%.(%d+)$')
    if not a then return false end
    for _,v in ipairs({a,b,c,d}) do
        if #v > 3 or tonumber(v) > 255 or (#v > 1 and v:sub(1,1) == '0') then return false end
    end
    return true
end

local function ipv6(s)
    if not s:match('^[%x:]+$') or not s:find(':',1,true) or s:find(':::',1,true) then return false end
    if (s:sub(1,1)==':' and s:sub(1,2)~='::') or (s:sub(-1)==':' and s:sub(-2)~='::') then return false end
    local _,compressed = s:gsub('::','')
    if compressed > 1 then return false end
    local count = 0
    for part in s:gmatch('[^:]+') do
        if #part > 4 then return false end
        count = count + 1
    end
    if compressed == 1 then return count < 8 end
    return count == 8 and s:sub(1,1) ~= ':' and s:sub(-1) ~= ':'
end

function M.cidr(s, family)
    if type(s) ~= 'string' then return false end
    local addr,mask = s:match('^([^/]+)/(%d+)$')
    if not addr then addr,mask = s, family == 4 and '32' or '128' end
    local max = family == 4 and 32 or 128
    return (#mask==1 or mask:sub(1,1)~='0') and tonumber(mask) <= max
        and (family == 4 and ipv4(addr) or family == 6 and ipv6(addr))
end

local function networks(value, family, label)
    local result = list(value)
    assert(#result <= 64, label .. ' 最多 64 项')
    for _,v in ipairs(result) do assert(M.cidr(v,family), label .. ' 地址无效') end
    return result
end

local implicit_local={
    [4]={'224.0.0.0/4','255.255.255.255/32','169.254.0.0/16'},
    [6]={'fe80::/10','ff00::/8'}
}

local function network_bits(value,family)
    local address,mask=value:match('^([^/]+)/(%d+)$')
    address=address or value
    local words={}
    if family==4 then
        for word in address:gmatch('%d+') do words[#words+1]=tonumber(word) end
    else
        local left,right=address:match('^(.-)::(.-)$')
        local tail={}
        for word in (left or address):gmatch('[^:]+') do words[#words+1]=tonumber(word,16) end
        if left then
            for word in right:gmatch('[^:]+') do tail[#tail+1]=tonumber(word,16) end
            for _=1,8-#words-#tail do words[#words+1]=0 end
            for _,word in ipairs(tail) do words[#words+1]=word end
        end
    end
    local bits={}
    for _,word in ipairs(words) do
        for bit=(family==4 and 7 or 15),0,-1 do bits[#bits+1]=math.floor(word/2^bit)%2 end
    end
    return bits,tonumber(mask) or #bits
end

local function full_exemption(values,family)
    -- A prefix trie normalizes host bits, overlaps and compressed IPv6, then
    -- merges sibling prefixes. Include automatically preserved ranges too.
    local root={}
    local function insert(node,bits,length,at)
        if node.full then return end
        if at>length then node.full=true; node[0]=nil; node[1]=nil; return end
        local bit=bits[at]
        node[bit]=node[bit] or {}
        insert(node[bit],bits,length,at+1)
        if node[0] and node[0].full and node[1] and node[1].full then
            node.full=true; node[0]=nil; node[1]=nil
        end
    end
    for _,group in ipairs({values,implicit_local[family]}) do
        for _,value in ipairs(group) do
            local bits,length=network_bits(value,family)
            insert(root,bits,length,1)
        end
    end
    return root.full
end

local function https_host(url)
    assert(type(url)=='string' and not url:find('[%c%s]') and #url<=512,'HTTPS 地址无效')
    local host=url:match('^https://([^/]+)/')
    assert(host and host:match('^[%w%.%-]+$') and host:find('%.') and not ipv4(host),'检测目标必须使用 HTTPS 域名，不支持认证信息或自定义端口')
    for label in host:gmatch('[^.]+') do
        assert(#label<=63 and label:match('^[%w]') and label:match('[%w]$'),'检测域名无效')
    end
    assert(not host:find('%.%.') and not host:find('^%.') and not host:find('%.$'),'检测域名无效')
    return host
end

function M.config(raw)
    raw = raw or {}
    local c = {
        enabled = raw.enabled == '1' or raw.enabled == true,
        mode = raw.mode or 'monitor',
        interfaces = list(raw.interfaces or {'br-lan'}),
        sources4 = networks(raw.sources4 or {'192.0.2.0/24'},4,'保护 IPv4'),
        ipv6_protect = raw.ipv6_protect~='0' and raw.ipv6_protect~=false,
        sources6 = (raw.ipv6_protect=='0' or raw.ipv6_protect==false) and {} or networks(raw.sources6 or {'::/0'},6,'保护 IPv6'),
        local4 = networks(raw.local4 or {'192.0.2.0/24','198.51.100.0/24','10.20.0.0/24'},4,'局域网 IPv4'),
        local6 = networks(raw.local6 or {'fd00::/64'},6,'局域网 IPv6'),
        interval = number(raw.interval,10,5,300,'检测间隔'),
        timeout = number(raw.timeout,4,1,15,'单目标超时'),
        fail_threshold = number(raw.fail_threshold,3,1,10,'失败次数'),
        recover_threshold = number(raw.recover_threshold,2,1,10,'恢复次数'),
        startup_grace = number(raw.startup_grace,150,0,600,'启动等待'),
        socks_port = number(raw.socks_port,1070,1,65535,'SOCKS 端口'),
        log_kib = number(raw.log_kib,64,16,512,'日志大小'),
        debug = raw.debug == '1' or raw.debug == true,
        self_heal = raw.self_heal == nil or raw.self_heal == '1' or raw.self_heal == true,
        self_heal_stale = number(raw.self_heal_stale,30,15,600,'异常心跳等待秒数'),
        self_heal_cooldown = number(raw.self_heal_cooldown,60,30,3600,'自动恢复冷却秒数'),
        self_heal_limit = number(raw.self_heal_limit,3,1,10,'自动恢复次数上限'),
        self_heal_window = number(raw.self_heal_window,600,60,3600,'自动恢复统计窗口'),
        resource_monitor = raw.resource_monitor == nil or raw.resource_monitor == '1' or raw.resource_monitor == true,
        udp_check = raw.udp_check == '1' or raw.udp_check == true,
        udp_server = raw.udp_server or '',
        udp_port = number(raw.udp_port,53,1,65535,'UDP 检查端口'),
        udp_query = raw.udp_query or 'example.com',
        udp_timeout = number(raw.udp_timeout,3,1,10,'UDP 检查超时'),
        proxy_client = raw.proxy_client or ((raw.passwall_watch=='1' or raw.passwall_watch==true) and 'passwall' or 'auto'),
        client_auto_ports = raw.client_auto_ports == '1' or raw.client_auto_ports == true,
        passwall_watch = raw.passwall_watch == '1' or raw.passwall_watch == true,
        passwall_log_watch = raw.passwall_log_watch == '1' or raw.passwall_log_watch == true,
        passwall_log_interval = number(raw.passwall_log_interval,1,1,10,'运行日志检查间隔'),
        boot_guard = raw.boot_guard == '1' or raw.boot_guard == true,
        passwall_trigger = raw.passwall_trigger or 'any',
        fast_wait_enabled = raw.fast_wait_enabled == nil or raw.fast_wait_enabled == '1' or raw.fast_wait_enabled == true,
        fast_wait_seconds = number(raw.fast_wait_seconds,15,1,3600,'快速保护等待秒数'),
        fast_stable_enabled = raw.fast_stable_enabled == nil or raw.fast_stable_enabled == '1' or raw.fast_stable_enabled == true,
        fast_stable_seconds = number(raw.fast_stable_seconds,60,1,3600,'快速保护稳定秒数'),
        schedule_enabled = raw.schedule_enabled == '1' or raw.schedule_enabled == true,
        schedule_start = raw.schedule_start or '',
        schedule_end = raw.schedule_end or '',
        schedule_utc_offset = raw.schedule_utc_offset or '+00:00',
        schedule_repeat = raw.schedule_repeat or ((raw.schedule_start and raw.schedule_start~='' and raw.schedule_end and raw.schedule_end~='') and 'daily' or ''),
        schedule_weekdays = {},
        exit_url = raw.exit_url or 'https://api.ipify.org/',
        cf_event_check = raw.cf_event_check == nil or raw.cf_event_check == '1' or raw.cf_event_check == true,
        expected_exit4 = raw.expected_exit4 or '',
        exit_check = raw.exit_check == '1' or raw.exit_check == true or raw.exit_check == nil and type(raw.expected_exit4)=='string' and raw.expected_exit4~='',
        exit_source = raw.exit_source or 'manual',
        proxy_ports = {}, dns_ports = {}, targets = {}
    }
    assert(c.mode == 'monitor' or c.mode == 'guard','模式无效')
    assert(({auto=true,passwall=true,passwall2=true,openclash=true,nikki=true,homeproxy=true})[c.proxy_client],'代理客户端类型无效')
    assert(raw.client_auto_ports==nil or raw.client_auto_ports=='0' or raw.client_auto_ports=='1' or type(raw.client_auto_ports)=='boolean','客户端端口开关无效')
    assert(c.passwall_trigger=='any' or c.passwall_trigger=='all','快速保护触发条件无效')
    for _,key in ipairs({'passwall_watch','passwall_log_watch','boot_guard','fast_wait_enabled','fast_stable_enabled'}) do
        assert(raw[key]==nil or raw[key]=='0' or raw[key]=='1' or type(raw[key])=='boolean','快速保护开关无效')
    end
    for _,key in ipairs({'self_heal','resource_monitor','udp_check','cf_event_check','exit_check','ipv6_protect'}) do
        assert(raw[key]==nil or raw[key]=='0' or raw[key]=='1' or type(raw[key])=='boolean','自检或 UDP 开关无效')
    end
    assert(type(c.udp_server)=='string' and (c.udp_server=='' or ipv4(c.udp_server)),'UDP 检查目标须为 IPv4 地址')
    assert(not c.udp_check or c.udp_server~='','启用 UDP 检查须填写自己的 DNS 目标')
    assert(type(c.udp_query)=='string' and #c.udp_query>0 and #c.udp_query<=253,'UDP 查询域名无效')
    assert(not c.udp_query:find('[^%w%.%-]') and not c.udp_query:find('%.%.') and not c.udp_query:match('^%.') and not c.udp_query:match('%.$'),'UDP 查询域名无效')
    for label in c.udp_query:gmatch('[^.]+') do assert(#label<=63 and not label:match('^%-') and not label:match('%-$'),'UDP 查询域名无效') end
    assert(raw.schedule_enabled==nil or raw.schedule_enabled=='0' or raw.schedule_enabled=='1' or type(raw.schedule_enabled)=='boolean','定时开关无效')
    -- A new installation has no schedule. Retained explicit times without a
    -- repeat field keep the daily behavior of older releases.
    if c.schedule_enabled or c.schedule_start~='' then c.schedule_start_seconds=clock_seconds(c.schedule_start) end
    if c.schedule_enabled or c.schedule_end~='' then c.schedule_end_seconds=clock_seconds(c.schedule_end) end
    if c.schedule_start_seconds and c.schedule_end_seconds then
        c.schedule_duration=(c.schedule_end_seconds-c.schedule_start_seconds)%86400
        assert(c.schedule_duration>0,'定时开始和结束时间不能相同')
    end
    c.schedule_offset_seconds=utc_offset(c.schedule_utc_offset)
    assert(c.schedule_repeat=='daily' or c.schedule_repeat=='weekdays' or not c.schedule_enabled and c.schedule_repeat=='','定时重复方式无效')
    local days=c.schedule_repeat=='daily' and {1,2,3,4,5,6,7} or c.schedule_repeat=='weekdays' and list(raw.schedule_weekdays) or {}
    assert(c.schedule_repeat~='weekdays' or #days>0 and #days<=7,'每周定时须选择至少一天，最多七天')
    local seen={}
    for _,value in ipairs(days) do
        local day=tonumber(value)
        assert((type(value)=='number' or type(value)=='string' and value:match('^[1-7]$')) and day and day==math.floor(day) and day>=1 and day<=7,'定时星期无效')
        assert(not seen[day],'定时星期不能重复')
        seen[day]=true; c.schedule_weekdays[#c.schedule_weekdays+1]=day
    end
    table.sort(c.schedule_weekdays)
    assert(#c.interfaces > 0 and #c.interfaces <= 8,'至少选择一个入口设备，最多 8 个')
    for _,v in ipairs(c.interfaces) do
        assert(type(v)=='string' and #v<=15 and v:match('^[%w_%.%-]+$'),'入口设备名无效')
    end
    assert(#c.sources4 + #c.sources6 > 0,'必须指定保护源地址')
    for _,family in ipairs({4,6}) do
        assert(not full_exemption(c['local'..family],family),'局域网豁免合并后不能覆盖整个互联网')
    end
    for _,v in ipairs(list(raw.proxy_ports or {'1070'})) do
        c.proxy_ports[#c.proxy_ports+1] = number(v,1070,1,65535,'本机代理端口')
    end
    assert(#c.proxy_ports<=16,'本机代理端口过多')
    for _,v in ipairs(list(raw.dns_ports or {'53'})) do
        local port=number(v,53,1,65535,'DNS 服务端口')
        for _,proxy in ipairs(c.proxy_ports) do assert(port~=proxy,'DNS 服务端口不能与代理入口端口重叠') end
        c.dns_ports[#c.dns_ports+1]=port
    end
    assert(#c.dns_ports>=1 and #c.dns_ports<=16,'配置 1 至 16 个 DNS 服务端口')
    local targets=list(raw.targets or {
        'https://www.gstatic.com/generate_204|204',
        'https://www.google.com/generate_204|204'
    })
    assert(#targets>=2 and #targets<=4,'配置 2 至 4 个 HTTPS 检测目标')
    for _,v in ipairs(targets) do
        local url,code=v:match('^(https://[^|]+)|(%d%d%d)$')
        assert(url and not url:find('[%c%s]') and #url<=512,'检测目标格式须为 https://域名/路径|状态码')
        local host=https_host(url)
        c.targets[#c.targets+1]={url=url,host=host,code=number(code,204,200,299,'成功状态码')}
    end
    assert(({manual=true,vps_interface=true,vps_panel=true,vps_measured=true})[c.exit_source],'出口 IPv4 来源无效')
    c.exit_host=c.exit_check and https_host(c.exit_url) or nil
    assert(not c.exit_check or ipv4(c.expected_exit4),'预期出口必须填写一个 IPv4 地址')
    c.cf_event_check=c.exit_check and c.cf_event_check
    c.min_success=number(raw.min_success,1,1,#c.targets,'每轮最少成功目标数')
    -- Covers one complete sequential probe round plus scheduling margin.
    c.lease_seconds=math.max(30,c.interval+c.timeout*(#c.targets+1+(c.cf_event_check and 1 or 0))+(c.udp_check and c.udp_timeout or 0)+15)
    return c
end

function M.load_config(raw)
    assert(type(raw)=='table','找不到插件配置')
    -- Only an explicit off value may remove an existing protection policy.
    -- Missing/corrupt activation fields are faults, not requests to disable it.
    assert(raw.enabled=='0' or raw.enabled=='1','总开关无效，必须明确设置为 0 或 1')
    if raw.enabled=='0' then return M.config({enabled=false}) end
    assert(raw.mode=='monitor' or raw.mode=='guard','模式无效')
    assert(raw['.type']==nil or raw['.type']=='proxy_guard','插件配置类型无效')
    local values={}
    for key,value in pairs(raw) do values[key]=value end
    for _,key in ipairs({'interfaces','sources4','sources6','local4','local6','proxy_ports','targets'}) do
        values[key]=values[key] or {}
    end
    return M.config(values)
end

function M.schedule(c, wall)
    if not c.schedule_enabled then
        return {enabled=false,active=false,start=c.schedule_start,finish=c.schedule_end,
            timezone='UTC'..c.schedule_utc_offset,utc_offset=c.schedule_utc_offset,
            repeat_mode=c.schedule_repeat,weekdays=c.schedule_weekdays,clock_valid=wall>=1577836800}
    end
    -- A fixed UTC offset, independent of system/browser TZ and DST. Weekdays
    -- belong to the local start date, including windows crossing midnight.
    local day=wall-(wall+c.schedule_offset_seconds)%86400
    local selected={}
    for _,d in ipairs(c.schedule_weekdays) do selected[d]=true end
    local start,next_start
    for distance=-7,7 do
        local candidate=day+distance*86400+c.schedule_start_seconds
        if selected[weekday(candidate+c.schedule_offset_seconds)] then
            if candidate<=wall then start=candidate
            elseif not next_start then next_start=candidate end
        end
    end
    assert(start and next_start,'无法计算定时窗口')
    local finish=start+c.schedule_duration
    return {enabled=c.schedule_enabled,start=c.schedule_start,finish=c.schedule_end,
        timezone='UTC'..c.schedule_utc_offset,utc_offset=c.schedule_utc_offset,
        repeat_mode=c.schedule_repeat,weekdays=c.schedule_weekdays,clock_valid=wall>=1577836800,
        active=c.schedule_enabled and wall>=start and wall<finish,
        last_start=start,next_start=next_start,
        next_end=finish>wall and finish or next_start+c.schedule_duration}
end

function M.startup_deadline(c)
    return c.passwall_watch and c.boot_guard and 0 or c.startup_grace
end

function M.initial(c, now)
    return {phase=c.enabled and 'starting' or 'disabled', failures=0, successes=0,
        started_at=now, next_probe=math.max(now,M.startup_deadline(c)), last_success=0, last_probe=0,
        blocked=c.enabled and c.mode=='guard', reason=c.enabled and '等待代理启动' or '保护已关闭'}
end

function M.step(c, s, ok, now)
    s.last_probe=now
    s.next_probe=now+c.interval
    if ok then
        s.last_success=now
        s.failures=0
        s.successes=math.min((s.successes or 0)+1,c.recover_threshold)
        if s.phase=='healthy' or s.phase=='suspect' or s.successes>=c.recover_threshold then
            s.phase,s.blocked,s.reason='healthy',false,'代理检测正常'
        else
            s.phase,s.blocked,s.reason='recovering',c.mode=='guard','代理恢复确认中'
        end
    else
        s.successes=0
        s.failures=math.min((s.failures or 0)+1,c.fail_threshold)
        if s.blocked or s.phase=='starting' or s.phase=='recovering' or s.phase=='blocked' or s.phase=='down' or s.failures>=c.fail_threshold then
            s.phase=c.mode=='guard' and 'blocked' or 'down'
            s.blocked=c.mode=='guard'
            s.reason='代理检测失败'
        else
            s.phase,s.blocked,s.reason='suspect',false,'连续失败确认中'
        end
    end
    return s
end

local function elements(values, quoted)
    local result={}
    for _,v in ipairs(values) do result[#result+1]=quoted and ('"'..v..'"') or tostring(v) end
    return table.concat(result,', ')
end

function M.rules(c, devices)
    assert(c.enabled and c.mode=='guard','Only guard mode may install rules')
    assert(devices,'Resolved ingress devices are required')
    local lines={
        'add table inet proxy_guard', 'delete table inet proxy_guard', 'table inet proxy_guard {',
        ' set interfaces { type ifname; elements = { '..elements(c.interfaces,true)..' }; }',
        ' set healthy_ifaces { type ifname; flags timeout; timeout '..c.lease_seconds..'s; }'
    }
    if c.passwall_watch then
        lines[#lines+1]=' set service_ifaces { type ifname; flags timeout; timeout 4s; }'
    end
    if c.schedule_enabled then
        lines[#lines+1]=' set healthy_times { typeof meta time; flags interval; }'
        lines[#lines+1]=' chain schedule_gate {'
        -- nft is always invoked with TZ=UTC0. The kernel uses realtime here,
        -- so a hung probe/lock cannot postpone the beginning of the window.
        local first=(c.schedule_start_seconds-c.schedule_offset_seconds)%86400
        local last=(c.schedule_end_seconds-c.schedule_offset_seconds)%86400
        if c.schedule_repeat=='weekdays' then
            for _,day in ipairs(c.schedule_weekdays) do
                local position=(day-1)*86400+c.schedule_start_seconds-c.schedule_offset_seconds
                local finish=position+c.schedule_duration
                while position<finish do
                    local utc_day=math.floor(position/86400)
                    local boundary=math.min(finish,(utc_day+1)*86400)
                    local from,to=position-utc_day*86400,boundary-utc_day*86400
                    -- nft day uses Sunday=0. Split at UTC midnight so an
                    -- offset/cross-midnight window cannot match the wrong day.
                    local rule='  meta day '..((utc_day+1)%7)
                    if from>0 then rule=rule..' meta hour >= "'..hour(from)..'"' end
                    if to<86400 then rule=rule..' meta hour < "'..hour(to)..'"' end
                    lines[#lines+1]=rule..' counter drop'
                    position=boundary
                end
            end
        elseif first<last then
            lines[#lines+1]='  meta hour >= "'..hour(first)..'" meta hour < "'..hour(last)..'" counter drop'
        else
            lines[#lines+1]='  meta hour >= "'..hour(first)..'" counter drop'
            if last>0 then lines[#lines+1]='  meta hour < "'..hour(last)..'" counter drop' end
        end
        lines[#lines+1]='  meta time @healthy_times return'
        lines[#lines+1]='  counter drop'
        lines[#lines+1]=' }'
    end
    for _,family in ipairs({4,6}) do
        local kind=family==4 and 'ipv4_addr' or 'ipv6_addr'
        local source=c['sources'..family]
        local allowed={}
        for _,v in ipairs(c['local'..family]) do allowed[#allowed+1]=v end
        for _,v in ipairs(implicit_local[family]) do allowed[#allowed+1]=v end
        lines[#lines+1]=' set sources'..family..' { type '..kind..'; flags interval; auto-merge;'..(#source>0 and (' elements = { '..elements(source)..' };') or '')..' }'
        lines[#lines+1]=' set local'..family..' { type '..kind..'; flags interval; auto-merge; elements = { '..elements(allowed)..' }; }'
    end
    local schedule=c.schedule_enabled and 'jump schedule_gate; ' or ''
    lines[#lines+1]=' chain decision { '..(c.passwall_watch and 'iifname != @service_ifaces counter drop; ' or '')..schedule..'iifname @healthy_ifaces return; counter drop; }'
    lines[#lines+1]=' chain reply_decision { '..(c.passwall_watch and 'oifname != @service_ifaces counter drop; ' or '')..schedule..'oifname @healthy_ifaces return; counter drop; }'
    for _,family in ipairs({4,6}) do
        local selector=family==4 and 'ip' or 'ip6'
        lines[#lines+1]=' chain guard'..family..' {'
        if #c.proxy_ports>0 then
            lines[#lines+1]='  fib daddr type local meta l4proto { tcp, udp } th dport { '..elements(c.proxy_ports)..' } jump decision'
        end
        lines[#lines+1]='  '..selector..' daddr @local'..family..' return'
        lines[#lines+1]='  fib daddr type local return'
        lines[#lines+1]='  jump decision'
        lines[#lines+1]=' }'
        lines[#lines+1]=' chain reply'..family..' {'
        if #c.proxy_ports>0 then
            lines[#lines+1]='  fib saddr type local meta l4proto { tcp, udp } th sport { '..elements(c.proxy_ports)..' } jump reply_decision'
        end
        lines[#lines+1]='  '..selector..' saddr @local'..family..' return'
        lines[#lines+1]='  fib saddr type local return'
        lines[#lines+1]='  jump reply_decision'
        lines[#lines+1]=' }'
        lines[#lines+1]=' chain output'..family..' {'
        -- Permit only replies to original DNS requests redirected to an
        -- approved local DNS port, before the general proxy DNAT reply check.
        for _,protocol in ipairs({'tcp','udp'}) do
            lines[#lines+1]='  meta l4proto '..protocol..' ct direction reply ct status dnat ct original proto-dst 53 fib saddr type local '..protocol..' sport { '..elements(c.dns_ports)..' } return'
        end
        -- REDIRECT restores a public source only later, in postrouting. Check
        -- the original destination now so a locally generated proxy reply
        -- cannot be mistaken for a LAN service reply before reverse NAT.
        lines[#lines+1]='  ct direction reply ct status dnat ct original '..selector..' daddr != @local'..family..' jump reply_decision'
        lines[#lines+1]='  jump reply'..family
        lines[#lines+1]=' }'
        lines[#lines+1]=' chain dns'..family..' {'
        lines[#lines+1]='  ct status dnat fib daddr type local th dport { '..elements(c.dns_ports)..' } return'
        lines[#lines+1]='  ct status dnat '..selector..' daddr @local'..family..' th dport { '..elements(c.dns_ports)..' } return'
        -- An unapproved translation must not inherit the ordinary LAN/local
        -- service exemptions just because DNAT changed its destination.
        lines[#lines+1]='  ct status dnat jump decision'
        lines[#lines+1]='  jump guard'..family
        lines[#lines+1]=' }'
    end
    lines[#lines+1]=' chain prerouting { type filter hook prerouting priority -310; policy accept;'
    for _,iface in ipairs(c.interfaces) do
        local d=assert(devices[iface],'Missing ingress device')
        local match='iifname "'..iface..'"'
        if d.bridge_filter_mac then match=match..' ether daddr '..d.bridge_filter_mac
        elseif d.mac or d.pending or d.kind==1 then match=match..' meta pkttype host' end
        -- Defer DNS until after existing destination NAT. This is not an
        -- unconditional DNS allow: dns_prerouting checks the final endpoint.
        lines[#lines+1]='  '..match..' ip saddr @sources4 meta l4proto { tcp, udp } th dport 53 return'
        lines[#lines+1]='  '..match..' ip6 saddr @sources6 meta l4proto { tcp, udp } th dport 53 return'
        lines[#lines+1]='  '..match..' ip saddr @sources4 jump guard4'
        lines[#lines+1]='  '..match..' ip6 saddr @sources6 jump guard6'
    end
    lines[#lines+1]=' }'
    lines[#lines+1]=' chain dns_prerouting { type filter hook prerouting priority -90; policy accept;'
    for _,iface in ipairs(c.interfaces) do
        local match='iifname "'..iface..'"'
        if devices[iface].bridge_filter_mac then match=match..' ether daddr '..devices[iface].bridge_filter_mac
        elseif devices[iface].mac or devices[iface].pending or devices[iface].kind==1 then match=match..' meta pkttype host' end
        for _,family in ipairs({4,6}) do
            local selector=family==4 and 'ip' or 'ip6'
            -- Use one protocol per original-tuple expression so older nft
            -- versions retain the service-port datatype and byte order.
            for _,protocol in ipairs({'tcp','udp'}) do
                lines[#lines+1]='  '..match..' '..selector..' saddr @sources'..family..' meta l4proto '..protocol..' ct direction original ct original proto-dst 53 jump dns'..family
            end
            -- NOTRACK/invalid packets have no original tuple. They still need
            -- the ordinary destination check after the early DNS deferral.
            lines[#lines+1]='  '..match..' '..selector..' saddr @sources'..family..' meta l4proto { tcp, udp } th dport 53 jump dns'..family
        end
    end
    lines[#lines+1]=' }'
    -- The inet postrouting hook cannot distinguish bridge transit from routed
    -- traffic by its input interface. Forward has both interfaces; output is
    -- exclusively locally generated traffic. Neither changes packet/ct marks.
    lines[#lines+1]=' chain forward { type filter hook forward priority -10; policy accept;'
    for _,iface in ipairs(c.interfaces) do
        local d=devices[iface]
        if d.mac or d.pending or d.kind==1 then
            -- Kernel packet type identifies traffic addressed to this gateway
            -- even when netifd changes the bridge MAC or recreates the device.
            local transit=d.bridge_filter_mac and ('ether daddr != '..d.bridge_filter_mac) or 'meta pkttype != host'
            lines[#lines+1]='  iifname "'..iface..'" oifname "'..iface..'" '..transit..' return'
        end
    end
    lines[#lines+1]='  oifname @interfaces ip daddr @sources4 jump reply4'
    lines[#lines+1]='  oifname @interfaces ip6 daddr @sources6 jump reply6'
    lines[#lines+1]=' }'
    lines[#lines+1]=' chain output { type filter hook output priority -10; policy accept;'
    lines[#lines+1]='  oifname @interfaces ip daddr @sources4 jump output4'
    lines[#lines+1]='  oifname @interfaces ip6 daddr @sources6 jump output6'
    lines[#lines+1]=' }'
    lines[#lines+1]='}'
    return table.concat(lines,'\n')..'\n'
end

function M.lease(c, allow, wall)
    local lines={'flush set inet proxy_guard healthy_ifaces'}
    if c.schedule_enabled then
        lines[#lines+1]='flush set inet proxy_guard healthy_times'
        if allow then
            assert(type(wall)=='number','定时许可缺少系统时间')
            local schedule=M.schedule(c,wall)
            allow=schedule.clock_valid and not schedule.active
            if allow then
                -- Bind the permit to this real-time interval as well as its
                -- monotonic timeout. It cannot survive a skipped window or a
                -- clock jump past the boundary. The hour gate excludes the
                -- inclusive interval endpoint at the exact scheduled start.
                local deadline=math.min(wall+c.lease_seconds,schedule.next_start)
                lines[#lines+1]='add element inet proxy_guard healthy_times { '..string.format('%.0f-%.0f',wall,deadline)..' }'
            end
        end
    end
    if allow then
        local items={}
        for _,v in ipairs(c.interfaces) do items[#items+1]='"'..v..'" timeout '..c.lease_seconds..'s' end
        lines[#lines+1]='add element inet proxy_guard healthy_ifaces { '..table.concat(items,', ')..' }'
    end
    return table.concat(lines,'\n')..'\n',allow
end

function M.proxy_options(c)
    local options='--proxy '..M.quote('socks5h://127.0.0.1:'..c.socks_port)
    if c._socks_curl_file then
        assert(c._socks_curl_file:match('^/var/run/proxy%-guard/socks%-[a-z0-9]+%-%d+%.conf$'),'Invalid private SOCKS authentication path')
        options=options..' --config '..M.quote(c._socks_curl_file)
    end
    return options
end
function M.probe_command(c,t,body_path)
    return 'curl -q --globoff --silent --show-error '..M.proxy_options(c)..
        ' --noproxy '..M.quote('')..' --proto =https --connect-timeout '..c.timeout..
        ' --max-time '..c.timeout..' --retry 0 --max-filesize 4096 --output '..M.quote(body_path or '/dev/null')..
        ' --write-out '..M.quote('%{http_code} %{time_total}')..' '..M.quote(t.url)
end


-- Trace is a bounded key=value response, never HTML or a bare status-code check.
function M.is_trace_url(url)
    return type(url)=='string' and (url:match('^https://[^/]+/cdn%-cgi/trace$')~=nil or url:match('^https://[^/]+/cdn%-cgi/trace%?[^#]*$')~=nil)
end

function M.trace(body)
    if type(body)~='string' or #body>4096 or body:find('[%z\1-\8\11\12\14-\31\127]') then return nil end
    body=body:gsub('\r\n','\n')
    if body:find('\r',1,true) then return nil end
    local fields={}
    for line in (body..'\n'):gmatch('(.-)\n') do
        if line~='' then
            local key,value=line:match('^([%a_][%w_]*)=(.*)$')
            if not key or fields[key]~=nil then return nil end
            fields[key]=value
        end
    end
    local ip=fields.ip
    if not ip or ip:find('/',1,true) or not (M.cidr(ip,4) or M.cidr(ip,6)) then return nil end
    if not fields.colo or not fields.colo:match('^%u%u%u$') then return nil end
    return {ip=ip,colo=fields.colo}
end

function M.exit_response(url,body)
    if M.is_trace_url(url) then return M.trace(body) end
    local value=type(body)=='string' and body:match('^%s*(.-)%s*$') or ''
    if value:find('/',1,true) or not (M.cidr(value,4) or M.cidr(value,6)) then return nil end
    return {ip=value}
end

-- Idempotent fw4 include: refresh static rules atomically, preserve the
-- permission elements and their original deadlines without renewing them.
function M.bootstrap(c,devices)
    local out={'# Generated Proxy Guard policy; permission sets start empty.', 'add table inet proxy_guard'}
    local chain
    local function rule(name,value)
        value=value:match('^%s*(.-)%s*$')
        if value=='' then return end
        value=value:gsub('"(%d%d):(%d%d):(%d%d)"',function(h,m,s) return tostring(tonumber(h)*3600+tonumber(m)*60+tonumber(s)) end)
        out[#out+1]='add rule inet proxy_guard '..name..' '..value
    end
    for line in M.rules(c,devices):gmatch('[^\n]+') do
        local name,body=line:match('^ set ([%w_]+) { (.*) }$')
        if name then
            local definition,items=body:match('^(.-) elements = { (.-) };%s*$')
            out[#out+1]='add set inet proxy_guard '..name..' { '..(definition or body)..' }'
            if name~='healthy_ifaces' and name~='service_ifaces' and name~='healthy_times' then
                out[#out+1]='flush set inet proxy_guard '..name
                if items then out[#out+1]='add element inet proxy_guard '..name..' { '..items..' }' end
            end
        else
            local cname,rest=line:match('^ chain ([%w_]+) {(.*)$')
            if cname then
                chain=cname
                local closed=rest:match('^(.-)}%s*$')
                if closed then rest=closed end
                if rest:match('^%s*type ') then out[#out+1]='add chain inet proxy_guard '..chain..' { '..rest..' }'
                else out[#out+1]='add chain inet proxy_guard '..chain end
                out[#out+1]='flush chain inet proxy_guard '..chain
                if not rest:match('^%s*type ') then for item in rest:gmatch('[^;]+') do rule(chain,item) end end
                if closed then chain=nil end
            elseif line:match('^ }%s*$') then chain=nil
            elseif chain then rule(chain,line) end
        end
    end
    return table.concat(out,'\n')..'\n'
end

return M
