// Independent heartbeat results must not deadlock fast recovery.
import { step } from './fast-state.uc';
let n=0;
function check(v,label){if(!v)die(label);n++;}
function observation(t){return {up:t,wall:t,tcp:true,udp:true,dns:true,probe:t,probe_started:t,probe_ok:true,network_blocked:true,network_healthy:false,heartbeat_probe:0,heartbeat_ok:false,heartbeat_allowed:false};}
let c={stamp:'cf-boundary',boot_guard:true,wait_enabled:true,wait_seconds:15,stable_enabled:true,stable_seconds:60,interval:10,probe_freshness:40},s=null;
for(let t=1;t<=16;t++)s=step(c,s,observation(t));
check(s.holding && s.phase=='sensitive','boot wait ends in sensitive verification');
let trip=s.trip;
for(let t=17;t<=20;t++){let o=observation(t);o.heartbeat_probe=t;o.heartbeat_ok=true;s=step(c,s,o);check(s.holding && s.phase=='sensitive' && s.trip==trip,'successful heartbeat pending its threshold must not restart delay or release');}
let o=observation(21);o.heartbeat_probe=21;o.heartbeat_ok=true;o.heartbeat_allowed=true;o.network_blocked=false;o.network_healthy=true;s=step(c,s,o);
check(!s.holding && s.phase=='sensitive','all gates healthy release into sensitive observation');
o=observation(22);o.probe=21;o.heartbeat_probe=22;o.heartbeat_ok=false;s=step(c,s,o);
check(s.holding && s.phase=='delay' && s.delay_until==37,'new heartbeat failure interrupts even without a new website result');
for(let t=23;t<=38;t++){o=observation(t);o.heartbeat_probe=22;o.heartbeat_ok=false;s=step(c,s,o);}
check(s.phase=='sensitive' && s.delay_until==37,'same heartbeat failure cannot perpetually restart delay');
o=observation(39);o.heartbeat_probe=39;o.heartbeat_ok=true;s=step(c,s,o);
check(s.holding && s.phase=='sensitive','pending recovery still withholds traffic');
o=observation(40);o.heartbeat_probe=40;o.heartbeat_ok=true;o.heartbeat_allowed=true;o.network_blocked=false;o.network_healthy=true;s=step(c,s,o);
check(!s.holding,'fresh completed heartbeat recovery releases traffic');
o=observation(41);o.heartbeat_probe=40;o.heartbeat_ok=true;o.heartbeat_allowed=true;o.network_blocked=false;o.network_healthy=true;o.probe_ok=false;s=step(c,s,o);
check(s.holding && s.phase=='delay','ordinary website failure still triggers sensitive protection');
print(sprintf('PASS %d independent heartbeat recovery assertions\n',n));
