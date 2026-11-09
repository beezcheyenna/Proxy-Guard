import { step } from './fast-state.uc';
let n=0;
function check(ok,label) { if (!ok) die(label); n++; }
function conf() { return {stamp:'audit',wait_enabled:true,wait_seconds:2,stable_enabled:true,stable_seconds:60,interval:10,probe_freshness:37,trigger_any:true,log_watch:true}; }
function obs(t) { return {up:t,wall:1700000000+t,generation:'worker1',tcp:true,udp:true,dns:true,identities:{tcp:'t1',udp:'u1',dns:'d1'},probe:t,probe_started:t-1,probe_ok:true,network_blocked:false,network_healthy:true,log:{trip:0,pending:false}}; }
let c=conf(),s=step(c,null,obs(10)),baseline=s.cf_event_id;
let o=obs(11);o.log={trip:1,pending:true};s=step(c,s,o);
let first=s.cf_event_id;
check(s.holding && first!=baseline,'new log outage has one new CF event');
o=obs(12);o.tcp=o.udp=o.dns=false;o.log={trip:1,pending:true};s=step(c,s,o);
check(s.holding && s.cf_event_id==first,'service disappearance joins the same log outage');
o=obs(13);o.log={trip:1,pending:false};s=step(c,s,o);
check(s.holding && s.cf_event_id==first,'service and log readiness retain event while awaiting fresh probe');
o=obs(14);o.log={trip:1,pending:false};s=step(c,s,o);
check(!s.holding && s.phase=='sensitive' && s.cf_event_id==first,'fresh recovery opens observation without a duplicate CF event');
o=obs(15);o.udp=false;o.log={trip:2,pending:true};s=step(c,s,o);let second=s.cf_event_id;
check(s.holding && second!=first,'new outage while traffic allowed in sensitivity gets a new event');
o=obs(16);o.tcp=o.udp=o.dns=false;o.log={trip:3,pending:true};s=step(c,s,o);
check(s.cf_event_id==second,'extra log and service faults while already held are deduplicated');
c.stamp='edited';o=obs(17);o.log={trip:3,pending:true};s=step(c,s,o);
check(s.cf_event_id==second,'configuration edit during outage preserves event identity');
// Scheduled windows and plugin watcher restarts must not consume CF requests.
c=conf();s=step(c,null,obs(30));baseline=s.cf_event_id;
o=obs(31);o.schedule_release=1;s=step(c,s,o);
check(s.phase=='sensitive' && !s.holding && s.cf_event_id==baseline,'schedule-only release creates no proxy-fault CF event');
c=conf();s=step(c,null,obs(40));baseline=s.cf_event_id;
o=obs(41);o.generation='worker2';s=step(c,s,o);
check(s.holding && s.cf_event_id==baseline,'watcher generation restart alone is not a proxy outage event');
c=conf();s=step(c,null,obs(50));baseline=s.cf_event_id;
o=obs(51);o.probe_ok=false;s=step(c,s,o);
check(!s.holding && s.cf_event_id==baseline,'subthreshold ordinary probe failure creates no service-log event');
o=obs(52);o.probe_ok=false;o.network_blocked=true;s=step(c,s,o);
check(s.holding && s.cf_event_id==baseline,'network-fault feedback is tracked by the main event module, not double counted');
printf('PASS %d CF fast-event boundary assertions\n',n);
