// Monotonic-time state machine. No network, filesystem or firewall side effects.
export function step(c, old, o) {
    let reconfigured = old && old.stamp != c.stamp && old.holding;
    let boot_start = c.boot_guard && (!old || old.stamp != c.stamp);
    let s = old && old.stamp == c.stamp ? old : {
        stamp: c.stamp, phase: 'normal', holding: false,
        probe_seen: 0, stable_since: null, probe_after: 0,
        boot_pending: c.boot_guard == true, generation: o.generation,
        must_wait: reconfigured && old.must_wait == true,
        log_seen: old ? (old.log_seen || 0) : 0,
        schedule_release: o.schedule_release || 0,
        cf_event_id: old ? old.cf_event_id : null
    };
    let restarted = s.updated_uptime != null && (o.up - s.updated_uptime > 4 ||
        (s.generation && o.generation && s.generation != o.generation));
    let remote_up = o.remote_ok == null || o.remote_ok == true;
    let remote_fell = s.remote_up != false && !remote_up;
    let was_holding = s.holding;
    let required=o.required || {tcp:true,udp:true,dns:true};
    let all_down=true, all_up=remote_up && o.available!=false, count=0;
    for (let name in ['tcp','udp','dns']) if (required[name]!=false) {
        count++; if (o[name]) all_down=false; else all_up=false;
    }
    all_up=all_up && count>0;
    s.required=required; s.client=o.client; s.client_error=o.error; s.client_available=o.available;

    let fresh_probe = o.probe > s.probe_seen;
    let local_fell = s.all_up && !all_up;
    let changed = {};
    for (let name in ['tcp','udp','dns'])
        changed[name] = required[name]!=false && s.identities && o.identities && s[name] && o[name] &&
            s.identities[name] != o.identities[name];
    let any_restart = changed.tcp || changed.udp || changed.dns;
    let local_trigger = c.trigger_any ? (!all_up || any_restart) :
        (all_down || ((required.tcp==false || changed.tcp) && (required.udp==false || changed.udp) && (required.dns==false || changed.dns)));
    local_trigger = local_trigger || !remote_up;
    let log = c.log_watch && o.log;
    let log_pending = log && log.pending == true;
    let log_trigger = log && ((log.trip || 0) != (s.log_seen || 0) || (log_pending && !s.log_pending));
    let was_observing = s.phase == 'sensitive' && !s.holding;
    s.notice = null;
    let schedule_release = (o.schedule_release || 0) != s.schedule_release;
    s.schedule_release = o.schedule_release || 0;
    let schedule_started = schedule_release && all_up && !any_restart && !restarted && !o.stale &&
        !log_pending && !log_trigger && !s.must_wait && !(s.holding && s.log_recovery);
    function episode(cause) {
        if (!s.episode || s.episode.completed_uptime != null)
            s.episode = {id:(o.generation || 'local')+':'+o.up,started_at:o.wall,
                started_uptime:o.up,resets:0,causes:{}};
        else if (!was_holding) s.episode.resets++;
        s.episode.causes[cause]=true;
    }
    if (s.holding && s.episode && remote_fell) s.episode.causes[o.manual_block ? 'maintenance' : 'remote'] = true;
    if (schedule_started) {
        episode('schedule');
        // A planned window ending is not a proxy failure. Release immediately
        // into strict observation; only a newly observed failure starts delay.
        s.phase = 'sensitive'; s.holding = false; s.boot_pending = false;
        s.stable_since = o.up; s.probe_after = o.up; s.probe_floor = o.probe;
        s.delay_until = null; s.notice = 'schedule_sensitive'; s.log_recovery = false;
    }
    let bad_probe = fresh_probe && !o.probe_ok && !schedule_started;

    // Normal operation retains the original network failure threshold. After
    // a local outage, any local or network failure restarts sensitive recovery.
    let log_trip = log_trigger && !(s.phase == 'delay' && s.holding && s.must_wait);
    let trigger = log_trip || (!schedule_started && (boot_start || reconfigured)) || restarted || (o.stale && !s.stale) ||
        (schedule_release && !schedule_started && !s.holding) || (s.phase == 'normal' && (local_trigger || o.network_blocked)) ||
        (s.phase != 'normal' && (local_fell || any_restart || (s.phase != 'delay' && s.phase != 'boot_wait' && bad_probe)));
    if (trigger) {
        // Only a genuine new local outage after release creates a CF event.
        // Network outages are deduplicated by the main probe worker; its CF
        // mismatch result must not recursively schedule another CF request.
        if (!s.holding && !boot_start && !reconfigured && (log_trigger || local_trigger))
            s.cf_event_id = (o.generation || 'local')+':'+o.up+':'+((s.trip || 0)+1);
        // A failure during the 60-second open observation always retains the
        // ordinary 15-second hold, even if a completion/schedule follows it.
        if (was_observing || (s.phase == 'sensitive' && bad_probe) || restarted || o.stale ||
            (s.phase == 'normal' && o.network_blocked)) s.must_wait = true;
        if (log_trigger && !s.must_wait) s.log_recovery = true;
        s.trip = (s.trip || 0) + 1;
        s.phase = s.boot_pending ? 'boot_wait' : s.log_recovery && !s.must_wait ? 'log_wait' : 'delay';
        s.holding = true; s.stable_since = null;
        s.delay_until = s.phase == 'delay' ? o.up + (c.wait_enabled ? c.wait_seconds : 0) : null;
        s.probe_after = s.delay_until == null ? o.up : s.delay_until;
        s.probe_floor = o.probe;
        s.cause = boot_start ? 'boot' : restarted ? 'watchdog' : o.stale ? 'worker' : log_trigger ? 'log' : !remote_up ? (o.manual_block ? 'maintenance' : 'remote') : all_down ? 'services' : 'interruption';
        episode(s.cause);
        s.notice = boot_start ? 'boot_wait' : 'blocked';
    }
    // Boot qualification always waits for all three services, even when the
    // ordinary trigger is "all" or the first sample already sees them running.
    if (s.phase == 'boot_wait' && all_up && !log_pending) {
        s.phase = 'delay';
        s.delay_until = o.up + (c.wait_enabled ? c.wait_seconds : 0);
        s.probe_after = s.delay_until; s.probe_floor = o.probe;
        s.notice = 'boot_ready';
    }
    if (log_pending) {
        // A slow request spanning rule deletion/rebuild cannot qualify later.
        s.probe_after = max(s.probe_after || 0, o.up); s.probe_floor = o.probe;
    }
    if (s.phase == 'log_wait' && all_up && !log_pending) {
        s.phase = 'sensitive'; s.probe_after = o.up; s.probe_floor = o.probe;
        s.notice = 'log_ready';
    }
    if (s.phase == 'delay' && o.up >= s.delay_until && !log_pending) {
        s.phase = 'sensitive'; s.notice = s.notice || 'sensitive';
    }
    if (s.phase == 'sensitive') {
        if (!all_up) {
            s.stable_since = null;
            // Results from a round begun before the local failure cannot be
            // used to establish recovery, even if they finish afterwards.
            s.probe_after = o.up;
        }
        let eligible = !o.stale && !log_pending && all_up && o.probe_ok && o.probe > (s.probe_floor || 0) && o.probe_started >= s.probe_after &&
            o.probe >= s.probe_after && o.up - o.probe <= c.probe_freshness;
        if (eligible && o.network_healthy && s.holding) {
            s.holding = false; s.boot_pending = false;
            s.stable_since = o.up; s.notice = 'restored'; s.must_wait = false; s.log_recovery = false;
        }
        let duration = c.stable_enabled ? c.stable_seconds : 0;
        // Traffic is already allowed during observation. Require a fresh
        // success before returning to the ordinary detection interval.
        if (!s.holding && eligible && o.network_healthy && s.stable_since != null &&
            o.probe >= s.stable_since + duration) {
            s.phase = 'normal'; s.notice = s.notice || 'normal';
        }
    }
    if (s.phase == 'ramp' && o.up >= s.ramp_until) {
        s.phase = 'normal'; s.notice = 'normal';
    }
    s.all_up = all_up;s.remote_up=remote_up;
    s.tcp = o.tcp; s.udp = o.udp; s.dns = o.dns;
    s.identities = o.identities;
    s.log_pending = log_pending == true;
    s.log_seen = log ? (log.trip || 0) : 0;
    if (o.generation) s.generation = o.generation;
    s.stale = o.stale == true;
    s.probe_seen = o.probe > s.probe_seen ? o.probe : s.probe_seen;
    s.wait_remaining = s.phase == 'delay' ? s.delay_until - o.up : 0;
    s.stable_elapsed = s.stable_since == null ? 0 : o.up - s.stable_since;
    s.stable_required = c.stable_enabled ? c.stable_seconds : 0;
    s.interval = s.phase == 'sensitive' ? 1 : s.phase == 'ramp' ? 5 : c.interval;
    if (s.interval > c.interval) s.interval = c.interval;
    if (s.episode) {
        s.episode.phase=s.phase;s.episode.holding=s.holding;
        if (s.phase=='normal' && s.episode.completed_uptime==null) s.episode.completed_uptime=o.up;
        s.episode.elapsed=max(0,(s.episode.completed_uptime==null ? o.up : s.episode.completed_uptime)-s.episode.started_uptime);
        s.episode.wait_remaining=max(0,s.wait_remaining);
        s.episode.stable_elapsed=s.episode.completed_uptime==null ? s.stable_elapsed : min(s.stable_elapsed,s.stable_required);s.episode.stable_required=s.stable_required;
    }
    s.updated_uptime = o.up;
    return s;
};
