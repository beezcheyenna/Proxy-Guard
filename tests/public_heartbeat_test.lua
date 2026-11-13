-- Pure protocol and configuration tests; run in the isolated OpenWrt VM.
package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local core=require 'proxy-guard.core'
local parser=require 'proxy-guard.public-heartbeat'
local n=0
local function check(ok,label)assert(ok,label);n=n+1 end
local function headers(extra,ip)
 return 'HTTP/2 200\r\ncontent-type: text/plain; charset=utf-8\r\nx-pghb-ip: '..(ip or '198.51.100.10')..'\r\nX-PGHB-Country: JP\r\nX-PGHB-ASN: 64501\r\nx-pghb-tls: TLSv1.3\r\nX-PGHB-Ray: abc123-NRT\r\n'..(extra or '')..'\r\n'
end
local function public(change)
 local raw={enabled='1',mode='guard',check_mode='public'}
 for k,v in pairs(change or {})do raw[k]=v end
 return core.config(raw)
end
check(#parser.body==24,'body is exactly 24 UTF-8 bytes')
check(parser.verify(0,200,parser.body,headers()),'root needs neither nonce nor optional telemetry')
check(not parser.verify(0,200,parser.body..'\n',headers()),'trailing newline rejected')
check(not parser.verify(0,200,parser.body..' ',headers()),'trailing space rejected')
check(not parser.verify(0,200,'ネットは広大だ&#x308F;',headers()),'HTML entity is not literal UTF-8')
check(not parser.verify(0,200,'\239\187\191'..parser.body,headers()),'BOM rejected')
check(not parser.verify(28,200,parser.body,headers()),'transport timeout fails even with partial good body')
check(not parser.verify(0,403,parser.body,headers()),'error HTTP status cannot be hidden by metadata')
check(not parser.verify(0,200,parser.body,headers():gsub('HTTP/2 200','HTTP/2 302')),'final header status must agree')
check(not parser.verify(0,200,parser.body,headers(),'nonce-one'),'full diagnostic requires its nonce')
check(parser.verify(0,200,parser.body,headers('x-pghb-nonce: nonce-one\r\n'),'nonce-one'),'matching echoed nonce accepted')
check(not parser.verify(0,200,parser.body,headers('x-pghb-nonce: nonce-old\r\n'),'nonce-one'),'old nonce rejected')
check(not parser.verify(0,200,parser.body,headers('X-PGHB-IP: 198.51.100.10\r\n')),'duplicate IP rejected case-insensitively')
check(not parser.verify(0,200,parser.body,headers('x-pghb-nonce: nonce-one\r\nX-PGHB-Nonce: nonce-one\r\n'),'nonce-one'),'duplicate nonce rejected')
check(parser.verify(0,200,parser.body,headers(),nil,'198.51.100.10'),'one response can verify expected IPv4')
check(not parser.verify(0,200,parser.body,headers(),nil,'198.51.100.11'),'explicit wrong IP rejected')
check(not parser.verify(0,200,parser.body,headers(nil,'not-an-ip'),nil,'198.51.100.10'),'missing usable IP cannot satisfy optional IP check')
local malformed=parser.body
local healthy,_,metadata,ip_reason=parser.verify(0,200,malformed,
 headers('X-PGHB-Edge-IP: invalid-edge\r\n', 'not-an-ip'))
check(healthy and not metadata.ip and not metadata.edge_ip and ip_reason=='invalid_ip',
 'malformed addresses are omitted from diagnostics while connectivity still passes')
local absent,_,_,missing=parser.verify(0,200,parser.body,'HTTP/2 200\r\n\r\n')
check(absent and missing=='missing_ip','missing IP is identified separately')
local _,duplicate=parser.verify(0,200,parser.body,headers('X-PGHB-IP: 198.51.100.10\r\n'))
check(duplicate=='duplicate_security_header','duplicate IP reason survives header validation')
check(not parser.headers(string.rep('x',32769)),'header size bounded')
check(not parser.headers('HTTP/2 200\r\n folded: invalid\r\n\r\n'),'obsolete header folding rejected')
check(not parser.headers('HTTP/2 200\r\nx-pghb-city: bad\0city\r\n\r\n'),'NUL rejected')
local diagnostic_headers=table.concat({
 'X-PGHB-Nonce: nonce-one',
 'X-PGHB-Delivery-Rate: 000',
 'X-PGHB-Client-TCP: false',
 'X-PGHB-Unknown: テスト',
 'X-PGHB-Empty:',
 'x-pghb-unknown: second value',
 'X-PGHB-Binary: '..string.char(255),
 'CF-Access-Client-Secret: never-copy',
 'Set-Cookie: never-copy'
},'\r\n')..'\r\n'
local interim='HTTP/1.1 100 Continue\r\nX-PGHB-Interim: never-copy\r\n\r\n'
local good,_,fields,_,raw=parser.verify(0,200,parser.body,interim..headers(diagnostic_headers),'nonce-one',nil,true)
check(good and fields.ip=='198.51.100.10' and parser.metadata(fields).nonce==nil,'IP and nonce still use the typed validation')
check(#raw==12 and raw[6].name=='X-PGHB-Nonce' and raw[6].value=='nonce-one','raw output keeps the echoed nonce and counts only PGHB fields in the final response')
check(raw[7].name=='X-PGHB-Delivery-Rate' and raw[7].value=='000' and raw[8].value=='false','diagnostics retain leading zeroes and literal boolean strings')
check(raw[9].name=='X-PGHB-Unknown' and raw[9].value=='テスト' and raw[10].value=='' and
 raw[11].name=='x-pghb-unknown' and raw[11].value=='second value','diagnostics preserve UTF-8, case, blank values, order and repeated headers')
check(raw[12].encoding=='base64' and raw[12].value=='/w==','non-UTF-8 field value has reversible encoding')
local basic,_,basic_fields,_,uncaptured=parser.verify(0,200,parser.body,headers(diagnostic_headers))
check(basic and uncaptured==nil and basic_fields['X-PGHB-Unknown']==nil,'background heartbeat does not capture diagnostic fields')
local stale,reason,_,_,stale_headers=parser.verify(0,200,parser.body,headers(diagnostic_headers),'different',nil,true)
check(not stale and reason=='nonce_mismatch' and not stale_headers,'a different nonce does not expose cached diagnostics')
local denied,denied_reason,_,_,denied_headers=parser.verify(0,403,'denied',
 headers(diagnostic_headers):gsub('HTTP/2 200','HTTP/2 403'),'nonce-one',nil,true)
check(not denied and denied_reason=='http_status' and #denied_headers==12,'current HTTP failures can report raw fields')
local cloud_error='HTTP/2 403\r\nX-PGHB-Error-Code: 1020\r\n\r\n'
local oversized,oversized_reason,_,_,error_fields=parser.verify(63,403,'',cloud_error,'nonce-one',nil,true)
check(not oversized and oversized_reason=='http_status' and error_fields[1].value=='1020',
 'diagnostics keep complete error headers without a nonce when curl rejects the error body')
local bad_body,body_reason,_,_,body_headers=parser.verify(0,200,'denied',headers(diagnostic_headers),'nonce-one',nil,true)
check(not bad_body and body_reason=='body_mismatch' and #body_headers==12,'raw headers cannot make a wrong body pass')
local c=core.config()
check(c.heartbeat_enabled and #c.targets==0 and not c.exit_check,'official mode independent of websites and optional IP checks')
check(c.public_hb_url=='https://hb.pghb.app/' and c.public_diag_url=='https://hb.pghb.app/f','default basic and diagnostic routes differ')
check(c.public_hb_interval==3 and c.public_hb_timeout==2 and c.public_hb_fail==2 and c.public_hb_recover==2,'official defaults')
local pinned=public({public_hb_url='https://ignored.example/',public_diag_url='https://ignored.example/f',
    exit_check='1',exit_provider='public',exit_url='https://ignored.example/',expected_exit4='198.51.100.10'})
check(pinned.public_hb_url=='https://hb.pghb.app/' and pinned.public_diag_url=='https://hb.pghb.app/f' and
    pinned.exit_url=='https://hb.pghb.app/','raw UCI cannot replace any official endpoint')
c=public({exit_check='1',expected_exit4='198.51.100.10'})
check(c.exit_provider=='public' and c.exit_url==c.public_hb_url and not c.exit_fallback_url,'official IP lookup is the default')
local function public_ip(response,expected)
 local verdict,observed=core.exit_outcome(c,response)
 check(verdict==expected,'exit outcome '..expected..' got '..verdict)
 return observed
end
check(public_ip({rc=0,code=200,public=true,ok=true,observed='198.51.100.10'},'match')=='198.51.100.10','matching IPv4 returned')
public_ip({rc=0,code=200,public=true,ok=true,observed='198.51.100.11'},'mismatch')
public_ip({rc=0,code=200,public=true,ok=true,observed='2001:db8::1'},'unavailable')
public_ip({rc=0,code=200,public=true,ok=false,observed='198.51.100.10'},'unavailable')
public_ip({rc=0,code=200,public=true,ok=true},'unavailable')
for _,case in ipairs({
 {observed='2001:db8::1',reason='ipv6_only'},
 {ip_reason='invalid_ip',reason='invalid_ip'},
 {reason='missing_ip'},
}) do
 local verdict,value,reason=core.exit_outcome(c,{rc=0,code=200,public=true,ok=true,observed=case.observed,ip_reason=case.ip_reason})
 check(verdict=='unavailable' and value==nil and reason==case.reason,'unavailable IPv4 reason: '..case.reason)
end
public_ip({rc=28,code=200,public=true},'unavailable')
public_ip(nil,'skipped')
c=core.config({enabled='1',check_mode='web',exit_check='1',expected_exit4='198.51.100.10'})
check(c.exit_url==c.public_hb_url and #c.targets==2 and not c.exit_fallback_url,'web IP lookup does not enable the official detector')
c=public({exit_check='1',expected_exit4='198.51.100.10',exit_provider='text'})
check(c.exit_fallback_url=='https://4.ident.me/','official connectivity can select the third-party IP provider')
check(core.exit_outcome(c,{rc=28,code=0,fallback=true})=='timeout','only the fallback timeout identifies a double timeout')
check(core.exit_outcome(c,{rc=28,code=0})=='unavailable','standalone timeout is not a double timeout')
check(core.exit_outcome(c,{rc=0,code=200,fallback=true,body='198.51.100.10'})=='match','valid IPv4 from fallback matches')
check(core.exit_outcome(c,{rc=0,code=500,fallback=true,body='198.51.100.10'})=='unavailable','fallback HTTP error is not a match')
check(public({diagnostics_enabled='1'}).heartbeat_lease==public().heartbeat_lease,'optional diagnostics do not extend the permit')
check(core.config({check_mode='web',diagnostics_enabled='1'}).public_diag_url=='https://hb.pghb.app/f','API diagnostics are available in website mode')
check(public({public_hb_sensitive_interval='3'}).sensitive_interval==3,'official sensitive cadence configurable')
check(core.config({check_mode='web',web_sensitive_interval='2'}).sensitive_interval==2,'web sensitive cadence configurable')
for _,bad in ipairs({
 {check_mode='cf'},{check_mode='both'},{check_mode='unknown'},
 {exit_provider='auto'},{diagnostics_enabled='yes'},{diagnostics_interval='0'},{diagnostics_ttl='0'},
 {public_hb_interval='0'},{public_hb_timeout='16'},{public_hb_sensitive_interval='6'},{public_hb_fail='0'},{public_hb_recover='11'},
 {check_mode='web',targets={'https://hb.pghb.app/f|200','https://web.example/|204'}},
 {check_mode='web',targets={'https://HB.PGHB.APP/check/../%66|200','https://web.example/|204'}},
 {exit_check='1',exit_provider='text',expected_exit4='198.51.100.10',exit_fallback_url='https://hb.pghb.app/f?test=1'}
}) do check(not pcall(public,bad),'invalid public configuration rejected') end
print('PASS '..n..' official HTTPS protocol, defaults and exit IPv4 assertions')
