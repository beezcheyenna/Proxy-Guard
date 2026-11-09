import { dnsmasq_port } from '../package/root/usr/lib/proxy-guard/clients.uc';
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
print(sprintf('PASS %d native multi-client parser and state assertions\n',count));
