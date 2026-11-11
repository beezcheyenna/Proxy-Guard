import { writefile, unlink } from 'fs';
import { dnsmasq_port, native_metadata } from '../package/root/usr/lib/proxy-guard/clients.uc';
import { tunnel_fdinfo } from '../package/root/usr/lib/proxy-guard/services.uc';
import { parse, consume } from '../package/root/usr/lib/proxy-guard/passwall-log.uc';
import { step } from '../package/root/usr/lib/proxy-guard/fast-state.uc';
let count=0;
function check(value,label) { count++; if (!value) die(label); };
check(dnsmasq_port('port=11400\nserver=127.0.0.1#15353\n')==11400,'PassWall dedicated DNS redirect listener is read');
check(dnsmasq_port('  port = 11401 \n')==11401,'dnsmasq port whitespace');
check(dnsmasq_port('server=127.0.0.1#11400\n')==null,'an upstream DNS target is not a local listening port');
check(dnsmasq_port('#port=11400\n')==null,'commented listener is ignored');
check(dnsmasq_port('port=11400\nport=0\n')==null,'disabled DNS listening does not retain an earlier port');
check(dnsmasq_port('port=65536\n')==null,'invalid DNS listening port rejected');
check(dnsmasq_port('port=11400; touch /tmp/not-run\n')==null,'configuration text is parsed as data');
let wall=1793448000, d=localtime(wall);
let stamp=sprintf('%04d-%02d-%02d %02d:%02d:%02d',d.year,d.mon,d.mday,d.hour,d.min,d.sec);
const cases={
 openclash:[['[Tip] OpenClash Restart...','restart'],['[Info] Step 2: Delete OpenClash Firewall Rules...','rules_removed'],['[Tip] OpenClash Start Successful!','complete'],['[Tip] Firewall Reload Successful!','complete'],['[Error] Core Start Failed, Please Check The Log Infos!','start_failed']],
 nikki:[['[App] Start.','restart'],['[Core] Start.','rules_loading'],['[Proxy] Hijack successful.','complete'],['[Proxy] Hijack failed.','start_failed'],['[App] Exit.','start_failed']],
 homeproxy:[['[DAEMON] Reloading service...','restart'],['[DAEMON] Service stopped.','stopped'],['[DAEMON] sing-box 1.12.3 started.','complete'],['[DAEMON] Error: wrong client configuration detected.','start_failed']]
};
for (let client,caseset in cases) {
 for (let row in caseset) {
  let line=client=='nikki' ? '['+stamp+'] '+row[0] : stamp+' '+row[0];
  let event=parse(line,client);
  check(event && event.kind==row[1],client+': '+row[0]);
  check(event.time==wall,'native timestamp for '+client);
  check(!parse('subscription node: '+line,client),'embedded log must not authorize '+client);
  check(!parse(line+'\x00',client),'control byte is rejected '+client);
 }
 let s={trip:0,pending:false,recent:[]};
 let stop=client=='nikki' ? '['+stamp+'] [App] Start.\n' : stamp+' '+caseset[0][0]+'\n';
 consume(s,stop,wall,100,false,false,client);
 check(s.pending && s.trip==1,'native client lifecycle trips '+client);
 let complete=client=='nikki' ? '['+stamp+'] [Proxy] Hijack successful.\n' :
  stamp+' '+(client=='openclash' ? '[Tip] OpenClash Start Successful!' : '[DAEMON] sing-box 1.12.3 started.')+'\n';
 consume(s,complete,wall+40,140,false,false,client);
 check(s.pending && s.clock_error,'stale completion never releases '+client);
 consume(s,complete,wall,141,false,false,client);
 check(!s.pending,'fresh completion clears the same cycle '+client);
}
check(!parse(stamp+' [Info] sing-box 1.12.3 started.','homeproxy'),'foreign prefix is not HomeProxy completion');
check(!parse(stamp+' [DAEMON] OpenClash Start Successful!','openclash'),'foreign prefix is not OpenClash completion');
check(!parse('['+stamp+'] [Profile] Hijack successful.','nikki'),'subscription/profile output cannot authorize Nikki');
let c={stamp:'test',trigger_any:true,boot_guard:false,log_watch:false,wait_enabled:true,wait_seconds:15,stable_enabled:true,stable_seconds:60,interval:10,probe_freshness:30};
function observation() { return {up:100,wall,generation:'g',tcp:true,udp:null,dns:null,required:{tcp:true,udp:false,dns:false},available:true,identities:{tcp:'one'},probe:99,probe_started:98,probe_ok:true,network_healthy:true}; };
let o=observation(),s=step(c,null,o);
check(s.phase=='normal' && !s.holding,'unconfigured UDP and DNS do not trigger false blocking');
o.up++;o.udp=false;s=step(c,s,o);
check(!s.holding,'a disabled capability stays distinct from a stopped service');
o.up++;o.tcp=false;s=step(c,s,o);
check(s.holding && s.phase=='delay','a required TCP failure blocks');
o=observation();s=step(c,null,o);o=observation();o.up=101;o.identities.tcp='two';s=step(c,s,o);
check(s.holding,'required process generation changes trigger protection');
c.trigger_any=false;o=observation();s=step(c,null,o);o=observation();o.up=101;o.identities.tcp='two';s=step(c,s,o);
check(s.holding,'all-services trigger considers only required services');
c.trigger_any=true;o=observation();o.available=false;s=step(c,null,o);
check(s.holding,'an unavailable adapter cannot claim healthy capabilities');
o=observation();o.required={tcp:false,udp:false,dns:false};s=step(c,null,o);
check(s.holding,'an empty capability set cannot authorize access');
check(tunnel_fdinfo('pos:\t0\nflags:\t0100002\niff:\tnikki\nqueues:\t1\n','nikki'),'native multi-line TUN fdinfo');
check(tunnel_fdinfo('iff:\tpg.tun-0\n','pg.tun-0'),'literal interface punctuation');
check(!tunnel_fdinfo('other_iff:\tnikki\n','nikki'),'unrelated fdinfo key cannot identify a TUN owner');
check(!tunnel_fdinfo('iff:\tnikki-extra\n','nikki'),'TUN owner must match the whole interface name');
check(!tunnel_fdinfo('iff:\tnikki\n','other'),'a different interface is not the selected TUN owner');
let native_path='/tmp/pg-native-metadata-test.json';
function native_profile() { return {required:{tcp:false,udp:false,dns:false},checks:{tcp:[],udp:[],dns:[]},proxy_ports:[],dns_ports:[]}; };
function native_case(data,kind) {
    writefile(native_path,sprintf('%J',data));
    let p=native_profile(), valid=native_metadata(p,native_path,kind);
    return {p,valid};
};
let row=native_case({server:'10.88.0.2:18444',socks5:{listen:'127.0.0.1:1070'},tcpTProxy:{listen:'0.0.0.0:1041'},udpTProxy:{listen:'0.0.0.0:1041'}},'hysteria2');
check(row.valid && row.p.socks_port==1070,'Hysteria native SOCKS listener is discovered');
check(row.p.required.tcp && row.p.required.udp && !row.p.required.dns,'Hysteria configured capabilities are read without inventing DNS');
check(row.p.checks.tcp[0].port==1041 && row.p.checks.udp[0].port==1041,'Hysteria transparent TCP and UDP listeners are checked');
check(index(row.p.proxy_ports,18444)<0,'Hysteria remote server port is never protected as a local listener');
row=native_case({socks5:{listen:'[::1]:1077',username:'user',password:'fixture'},tcpRedirect:{listen:':1042'}},'hysteria2');
check(row.valid && row.p.socks_port==1077 && row.p._auth_required,'IPv6 and native SOCKS credentials are retained privately');
check(!row.p.required.udp,'Hysteria TCP-only setup does not invent a UDP listener');
row=native_case({locals:[{protocol:'redir',local_port:1043,mode:'tcp_and_udp'},{local_port:1071,mode:'tcp_and_udp'},{protocol:'http',local_port:1082}],server_port:18445},'ss-rust');
check(row.valid && row.p.socks_port==1071,'Shadowsocks Rust default SOCKS protocol is discovered without an explicit protocol field');
check(row.p.required.tcp && row.p.required.udp && row.p.checks.udp[0].port==1043,'Shadowsocks Rust redirection mode covers both protocols');
check(index(row.p.proxy_ports,18445)<0 && index(row.p.proxy_ports,1082)>=0,'SS remote port stays separate from native local HTTP');
row=native_case({listen:['redir://0.0.0.0:1044','socks://127.0.0.1:1072'],proxy:'https://fixture@10.88.0.2:18443'},'naiveproxy');
check(row.valid && row.p.socks_port==1072 && row.p.required.tcp,'Naive native redirection and SOCKS listeners are discovered');
check(!row.p.required.udp && !row.p.required.dns,'Naive does not claim unsupported UDP forwarding');
check(index(row.p.proxy_ports,18443)<0,'Naive upstream proxy port is not a local interception port');
row=native_case({socks5:{listen:'127.0.0.1:1070'},tcpTProxy:{listen:'malformed'}},'hysteria2');
check(!row.valid && row.p.native_invalid,'invalid transparent listener cannot fall back to a healthy SOCKS claim');
row=native_case({listen:'socks://127.0.0.1:1070; command'},'naiveproxy');
check(!row.valid,'native listener values are parsed as data with exact ports');
row=native_case({inbounds:[]},'naiveproxy');
check(!row.valid && !row.p.native_invalid,'unrelated JSON cannot invalidate another native config');
row=native_case({locals:[{protocol:'redir',local_port:1044,mode:'unknown'}]},'ss-rust');
check(!row.valid && row.p.native_invalid,'unknown SS Rust mode is rejected');
unlink(native_path);

print(sprintf('PASS %d native multi-client parser and state assertions\n',count));
