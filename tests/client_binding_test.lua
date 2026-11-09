package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local clients=require 'proxy-guard.clients'
local count=0
local function check(v,label) assert(v,label);count=count+1 end
local function base(auto) return {client_auto_ports=auto,socks_port=1070,proxy_ports={1041},dns_ports={53}} end
local profile={available=true,socks_port=1080,proxy_ports={1080,7891,7892},dns_ports={1053},
 socks_auth_file='/var/run/proxy-guard/socks-nikki-1080.json',socks_curl_file='/var/run/proxy-guard/socks-nikki-1080.conf'}
local c=base(true);clients.bind(c,profile)
check(c.socks_port==1080,'automatic probe follows the selected listener')
check(c.dns_ports[2]==1053,'redirected local DNS remains an explicit exception')
check(c.proxy_ports[2]==1080 and c.proxy_ports[4]==7892,'explicit and transparent proxy ports are protected')
check(c._socks_auth_file==profile.socks_auth_file,'matching automatic listener receives private authentication')
local manual=base(false);clients.bind(manual,profile)
check(#manual.dns_ports==1 and manual.socks_port==1070,'manual ports remain unchanged')
check(not manual._socks_auth_file,'credentials are not attached to a different manual socket')
manual.socks_port=1080;clients.bind(manual,profile)
check(manual._socks_curl_file==profile.socks_curl_file,'matching manual listener can authenticate')
local outage=base(true);clients.bind(outage,{available=false},c)
check(outage.socks_port==1080 and outage.dns_ports[2]==1053,'last verified ports retain DNS access during client restart')
local duplicate=base(true);clients.bind(duplicate,profile);clients.bind(duplicate,profile)
check(#duplicate.dns_ports==2,'automatic DNS bindings do not accumulate')
local auth_only=base(true);auth_only.socks_port=1080
clients.bind_auth(auth_only,profile)
check(auth_only._socks_auth_file==profile.socks_auth_file,'authentication survives disabled client service monitoring')
check(#auth_only.proxy_ports==1 and #auth_only.dns_ports==1,'authentication-only binding never expands protection or DNS ports')
local mismatch=base(false);clients.bind_auth(mismatch,profile)
check(not mismatch._socks_auth_file,'authentication-only binding never attaches credentials to a different socket')
print('PASS '..count..' native client binding and DNS preservation assertions')
