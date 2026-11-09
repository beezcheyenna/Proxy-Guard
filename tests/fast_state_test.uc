import { step } from './fast-state.uc';
let n = 0;
function check(condition, message) {
    if (!condition) die(message);
    n++;
}
function config() {
    return { stamp: 'test', wait_enabled: true, wait_seconds: 15,
        stable_enabled: true, stable_seconds: 60, interval: 10, probe_freshness: 37 };
}
function observation(t) {
    return {up:t,tcp:true,udp:true,dns:true,probe:t,probe_started:t-1,
        probe_ok:true,network_blocked:false,network_healthy:true};
}
let c=config(), s=null;
let o=observation(100); o.tcp=o.udp=o.dns=false;
s=step(c,s,o);
check(s.holding && s.phase=='delay' && s.delay_until==115, 'all-down must block immediately and start 15s delay');
for(let t=101;t<115;t++) {
    s=step(c,s,observation(t));
    check(s.holding && s.phase=='delay','services returning must not shorten delay');
}
s=step(c,s,observation(115));
check(s.holding && s.stable_since==null,'pre-delay probe cannot establish recovery');
for(let t=116;t<176;t++) {
    s=step(c,s,observation(t));
    check(!s.holding && s.phase=='sensitive' && s.interval==1,'healthy traffic is allowed during one-second sensitive observation');
}
s=step(c,s,observation(176));
check(!s.holding && s.phase=='normal' && s.interval==10,'fresh success after 60 seconds ends sensitive observation');
for(let t=177;t<=206;t++) s=step(c,s,observation(t));
check(s.phase=='normal' && s.interval==10,'gradually return to normal interval');

c=config(); s=null; o=observation(1); o.udp=o.dns=false;
s=step(c,s,o);
check(!s.holding && s.phase=='normal','normal fast trigger requires all three down');
o=observation(2); o.probe_ok=false;
s=step(c,s,o);
check(!s.holding,'normal network checks retain failure threshold');
o=observation(3); o.network_blocked=true;
s=step(c,s,o);
check(s.holding,'confirmed network failure also enters sensitive recovery');
for(let t=4;t<=25;t++) s=step(c,s,observation(t));
o=observation(26); o.dns=false;
s=step(c,s,o);
check(s.holding && s.stable_since==null && s.delay_until==41,'one local interruption resets wait and stability');
for(let t=27;t<=45;t++) s=step(c,s,observation(t));
o=observation(46); o.probe_ok=false;
s=step(c,s,o);
check(s.phase=='delay' && s.delay_until==61,'one sensitive network failure blocks and resets countdown');
o=observation(47); o.probe=46; o.probe_ok=false;
s=step(c,s,o);
check(s.delay_until==61,'same failed result must not perpetually restart delay');

c=config(); c.wait_enabled=false; c.stable_enabled=false;
o=observation(100); o.tcp=o.udp=o.dns=false;
s=step(c,null,o);
check(s.phase=='sensitive' && s.holding,'disabled wait starts sensitive checks immediately');
o=observation(101); o.network_healthy=false;
s=step(c,s,o);
check(s.holding,'disabled stability still requires ordinary recovery confirmation');
s=step(c,s,observation(102));
check(!s.holding && s.phase=='normal','both switches off permit recovery after verified checks');
s=step(c,s,observation(110));
check(s.holding && s.cause=='watchdog','watcher interruption cannot silently reuse old health');

c=config(); c.wait_seconds=2; c.stable_seconds=3;
o=observation(1); o.tcp=o.udp=o.dns=false;
s=step(c,null,o);
for(let t=2;t<=6;t++) s=step(c,s,observation(t));
check(!s.holding && s.phase=='sensitive','custom observation allows traffic before its timer finishes');
s=step(c,s,observation(7));
check(!s.holding,'custom delay and stability values must be honored');
c=config(); c.trigger_any=true;
o=observation(1); o.identities={tcp:'1',udp:'1',dns:'2'};
s=step(c,null,o);
o=observation(2); o.identities={tcp:'1',udp:'1',dns:'3'};
s=step(c,s,o);
check(s.holding && s.phase=='delay','DNS restart between polls must trigger any-service mode');
o=observation(3); o.identities={tcp:'1',udp:'1',dns:'3'};
c.stamp='new'; c.wait_seconds=5;
s=step(c,s,o);
check(s.holding && s.delay_until==8,'changing settings during a fault cannot silently cancel protection');
c=config(); c.trigger_any=true;
o=observation(10); o.dns=false;
s=step(c,null,o);
check(s.holding,'any-service mode also blocks on a single missing service');
c=config(); c.trigger_any=true; c.wait_enabled=false; c.stable_enabled=false;
o=observation(10); o.identities={tcp:'1',udp:'1',dns:'2'};
s=step(c,null,o);
o=observation(11); o.identities={tcp:'1',udp:'1',dns:'3'}; o.probe_started=11;
s=step(c,s,o);
check(s.holding,'a successful result already present at the trigger cannot release the gate');
o=observation(12); o.identities={tcp:'1',udp:'1',dns:'3'};
s=step(c,s,o);
check(!s.holding,'a new successful post-trigger round can confirm recovery');
o=observation(13); o.stale=true; o.identities={tcp:'1',udp:'1',dns:'3'};
s=step(c,s,o);
check(s.holding && s.tcp && s.udp && s.dns && s.cause=='worker','stale network status must block without falsifying local service states');
c=config(); c.trigger_any=true;
o=observation(100); o.dns=false; s=step(c,null,o);
s=step(c,s,observation(101));
o=observation(102); o.dns=false; s=step(c,s,o);
check(s.delay_until==117 && s.trip==2,'a second local interruption during the delay restarts the full wait');
// A boot with already-running services must still qualify from scratch.
c=config(); c.boot_guard=true; c.trigger_any=false;
o=observation(10); o.generation='boot-A'; s=step(c,null,o);
check(s.boot_pending && s.holding && s.phase=='delay' && s.delay_until==25,'already-running services cannot bypass boot qualification');
check(s.generation=='boot-A','a new watcher state identifies its health generation');
for(let t=11;t<25;t++) {
    s=step(c,s,observation(t));
    check(s.holding && s.phase=='delay','boot delay remains closed');
}
s=step(c,s,observation(25));
check(s.stable_since==null,'pre-delay success cannot start boot stability');
for(let t=26;t<86;t++) {
    s=step(c,s,observation(t));
    check(!s.holding && !s.boot_pending && s.phase=='sensitive','boot recovery releases traffic before the 60-second observation finishes');
}
s=step(c,s,observation(86));
check(!s.holding && !s.boot_pending && s.phase=='normal','boot observation ends after 60 seconds of fresh successes');

// Delay starts when the last missing service appears, not at power-on.
for (let missing in ['tcp','udp','dns']) {
    c=config(); c.boot_guard=true; s=null;
    for(let t=1;t<=170;t++) {
        o=observation(t); o[missing]=false; s=step(c,s,o);
    }
    check(s.holding && s.phase=='boot_wait' && s.stable_since==null && s.delay_until==null,'one absent service keeps boot blocked beyond old startup wait');
    s=step(c,s,observation(171));
    check(s.phase=='delay' && s.delay_until==186,'full wait begins only after all three are ready');
    o=observation(172); o[missing]=false; s=step(c,s,o);
    check(s.phase=='boot_wait' && s.delay_until==null,'a drop during boot delay returns to waiting for readiness');
    s=step(c,s,observation(173));
    check(s.delay_until==188,'service recovery restarts the full delay');
}

c=config(); c.boot_guard=true; c.wait_seconds=2; c.stable_seconds=3;
s=step(c,null,observation(1));
for(let t=2;t<=5;t++) s=step(c,s,observation(t));
o=observation(6); o.probe_ok=false; s=step(c,s,o);
check(s.holding && s.stable_since==null && s.delay_until==8,'failed HTTPS during observation immediately blocks and restarts delay');
for(let t=7;t<=11;t++) s=step(c,s,observation(t));
check(!s.holding && s.phase=='sensitive' && s.stable_since==9,'recovery releases traffic with a new observation timer');
s=step(c,s,observation(12));
check(!s.holding,'continuous recovery after the reset can restore access');

c=config(); c.boot_guard=true;
o=observation(1); o.identities={tcp:'1',udp:'1',dns:'2'}; s=step(c,null,o);
o=observation(2); o.identities={tcp:'1',udp:'1',dns:'3'}; s=step(c,s,o);
check(s.holding && s.delay_until==17,'a restart between boot polls restarts the wait even when all appear running');
o=observation(3); o.identities={tcp:'1',udp:'1',dns:'3'}; c.stamp='new-boot'; s=step(c,s,o);
check(s.boot_pending && s.holding && s.delay_until==18,'policy reconfiguration cannot bypass boot confirmation');

c=config(); c.boot_guard=true; c.wait_enabled=false; c.stable_enabled=false;
o=observation(1); o.dns=false; s=step(c,null,o);
check(s.phase=='boot_wait' && s.holding,'disabled timers still wait for all services');
o=observation(2); o.network_healthy=false; s=step(c,s,o);
check(s.holding && s.phase=='sensitive','existing success before readiness is not sufficient');
o=observation(3); o.network_healthy=false; s=step(c,s,o);
check(s.holding,'ordinary consecutive recovery threshold still applies with timers disabled');
s=step(c,s,observation(4));
check(!s.holding && !s.boot_pending,'fresh ordinary confirmation releases disabled timers');
o=observation(10); o.generation='boot-B'; s=step(c,null,o);
check(s.holding && s.boot_pending && s.generation=='boot-B','missing state/new boot never reuses an old healthy result');

// Planned releases never inherit the failure delay or reuse old probe results.
c=config(); c.boot_guard=true;
o=observation(1); s=step(c,null,o);
o=observation(2); o.schedule_release=1; o.probe_ok=false; o.network_healthy=false;
s=step(c,s,o);
check(!s.holding && s.phase=='sensitive' && s.delay_until==null && s.interval==1,'schedule release skips delay even while an earlier boot delay was pending');
check(s.stable_since==2 && s.probe_floor==2,'schedule observation starts a fresh 60-second interval');
o=observation(3); o.schedule_release=1; o.probe=2; o.probe_ok=false;
s=step(c,s,o);
check(!s.holding,'a pre-window result cannot cause a new failure wait');
o=observation(4); o.schedule_release=1; o.probe_ok=false;
s=step(c,s,o);
check(s.holding && s.delay_until==19,'first new failure after a planned release starts the normal 15-second block');
o=observation(5); o.schedule_release=1; o.probe=4; o.probe_ok=false;
s=step(c,s,o);
check(s.delay_until==19,'repeated schedule marker and failed result cannot restart the delay');
c=config(); s=step(c,null,observation(1));
o=observation(2); o.schedule_release=1; s=step(c,s,o);
for(let t=3;t<62;t++) { o=observation(t); o.schedule_release=1; s=step(c,s,o); }
check(!s.holding && s.phase=='sensitive','scheduled observation remains open for its full duration');
o=observation(62); o.schedule_release=1; s=step(c,s,o);
check(s.phase=='normal' && !s.holding,'scheduled observation returns directly to normal frequency');
c=config(); s=step(c,null,observation(1));
o=observation(2); o.schedule_release=1; o.dns=false; s=step(c,s,o);
check(s.holding && s.phase=='delay','a real local failure at scheduled release still blocks');

// Log and service monitoring share a gate and one recovery sequence.
function logged(t, trip, pending) {
    let value=observation(t); value.log={trip,pending}; return value;
}
c=config(); c.trigger_any=true; c.log_watch=true;
s=step(c,null,logged(100,0,false));
s=step(c,s,logged(101,1,true));
check(s.holding && s.phase=='log_wait' && s.delay_until==null,'first log restart blocks without scheduling an extra 15 seconds');
o=logged(102,1,true); o.udp=false; s=step(c,s,o);
check(s.holding && s.phase=='log_wait','a related UDP stop merges into the same log recovery');
o=logged(103,1,false); o.udp=false; s=step(c,s,o);
check(s.holding && s.phase=='log_wait','completion alone cannot override an absent UDP service');
s=step(c,s,logged(104,1,false));
check(s.holding && s.phase=='sensitive' && s.probe_after==104,'all readiness conditions start fresh checks without 15-second delay');
s=step(c,s,logged(105,1,false));
check(!s.holding && s.stable_since==105,'a fresh post-ready success allows traffic for the observation period');
s=step(c,s,logged(106,2,true));
check(s.holding && s.phase=='delay' && s.delay_until==121 && s.must_wait,'a LOG failure inside observation must keep the original full 15-second block');
s=step(c,s,logged(107,2,false));
check(s.holding && s.delay_until==121,'a new completion cannot bypass the sensitive-failure delay');
o=logged(108,2,false); o.schedule_release=1; s=step(c,s,o);
check(s.holding && s.delay_until==121,'a scheduled release cannot bypass a sensitive-failure delay either');
for(let t=109;t<121;t++) {
    o=logged(t,2,false); o.schedule_release=1; s=step(c,s,o);
    check(s.holding && s.phase=='delay' && s.delay_until==121,'the merged delay is not shortened or queued twice');
}
o=logged(121,2,false); o.schedule_release=1; s=step(c,s,o);
check(s.holding && s.phase=='sensitive','a pre-deadline success cannot release after the 15-second delay');
o=logged(122,2,false); o.schedule_release=1; s=step(c,s,o);
check(!s.holding && s.stable_since==122,'fresh recovery restarts the full 60-second period');
o=logged(123,3,false); o.schedule_release=1; s=step(c,s,o);
check(s.holding && s.delay_until==138,'a whole stop/start cycle between polls still triggers the observation failure delay');
c.stamp='edited-during-sensitive-fault';
o=logged(124,4,false); o.schedule_release=1; s=step(c,s,o);
check(s.holding && s.phase=='delay' && s.must_wait,'configuration changes cannot turn a sensitive fault into a first log recovery');

c=config(); c.trigger_any=true; c.log_watch=true;
s=step(c,null,logged(1,0,false));s=step(c,s,logged(2,1,true));
s=step(c,s,logged(3,1,false));
o=logged(4,1,false);o.schedule_release=1;o.network_healthy=false;s=step(c,s,o);
check(s.holding && s.stable_since==null,'schedule end cannot start observation before first log recovery has been verified');
o=logged(5,1,false);o.schedule_release=1;s=step(c,s,o);
check(!s.holding && s.stable_since==5,'overlapping initial recovery starts the full observation clock only when access is restored');
c=config(); c.trigger_any=true; c.log_watch=true;
s=step(c,null,logged(1,0,false));s=step(c,s,logged(2,1,true));
s=step(c,s,logged(3,1,false));
o=logged(4,1,false);o.probe_ok=false;o.network_healthy=false;s=step(c,s,o);
check(s.holding && s.phase=='delay' && s.delay_until==19,'failed first log recovery verification backs off through the original 15-second wait');
s=step(c,s,logged(5,1,false));
check(s.holding && s.delay_until==19,'another completion cannot bypass initial failed-verification backoff');
c=config(); c.trigger_any=true; c.log_watch=true;
s=step(c,null,logged(10,0,false));
o=logged(11,0,false); o.dns=false; s=step(c,s,o);
check(s.phase=='delay' && s.delay_until==26,'service-only failure keeps the ordinary delay');
s=step(c,s,logged(12,1,true));
check(s.phase=='log_wait' && s.delay_until==null,'a first lifecycle event merges with an already noticed local restart');
s=step(c,s,logged(13,1,false)); s=step(c,s,logged(14,1,false));
check(!s.holding && s.phase=='sensitive','merged first recovery does not queue a second service delay');
c=config(); c.log_watch=false;
s=step(c,null,logged(10,99,true));
check(!s.holding && s.phase=='normal','disabled log monitoring cannot affect protection');
c=config(); c.trigger_any=true; c.log_watch=true; c.boot_guard=true;
s=step(c,null,logged(10,1,true));
check(s.holding && s.phase=='boot_wait','log recovery does not weaken explicitly enabled boot qualification');
s=step(c,s,logged(11,1,false));
check(s.holding && s.delay_until==26,'boot still retains its configured wait after all startup conditions');
c=config(); o=observation(10); o.generation='watcher-A'; s=step(c,null,o);
o=observation(11); o.generation='watcher-B'; s=step(c,s,o);
check(s.holding && s.cause=='watchdog' && s.generation=='watcher-B','even a quick watcher respawn invalidates an old permit generation');
// Remote and local faults share one incident and one waiting deadline.
c=config();c.trigger_any=false;s=step(c,null,observation(1));
o=observation(2);o.remote_ok=false;s=step(c,s,o);
check(s.holding && s.delay_until==17 && s.cause=='remote','remote failure starts the ordinary wait');
let remote_episode=s.episode.id;
for(let t=3;t<17;t++) {
    o=observation(t);o.remote_ok=false;if(t==5)o.tcp=false;s=step(c,s,o);
    check(s.delay_until==17 && s.episode.id==remote_episode,'overlapping remote and local reports do not restart the same wait');
}
s=step(c,s,observation(17));s=step(c,s,observation(18));
check(!s.holding && s.phase=='sensitive','remote recovery joins the open sensitive observation after fresh verification');
o=observation(19);o.remote_ok=false;s=step(c,s,o);
check(s.holding && s.delay_until==34 && s.must_wait,'remote failure during observation retains the 15-second block');
c=config();s=step(c,null,observation(10));o=observation(11);o.remote_ok=false;o.manual_block=true;s=step(c,s,o);
check(s.holding && s.cause=='maintenance','planned remote maintenance shares the protection state machine');
print(sprintf('PASS %d fast state assertions\n',n));
