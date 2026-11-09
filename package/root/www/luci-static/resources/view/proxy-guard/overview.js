'use strict';
'require view';
'require form';
'require rpc';
'require poll';
'require ui';
'require uci';
'require proxy_guard_i18n as pgI18n';
'require proxy_guard_setup as pgSetup';

// Keep status separate from logs in LuCI's HTTP batcher as well as the UI.
const setupInfoCall=rpc.declare({object:'proxy_guard',method:'setup_info',expect:{'':{}},reject:true,nobatch:true});
const egressInfoCall=rpc.declare({object:'proxy_guard_access',method:'egress_info',params:['refresh'],expect:{'':{}},reject:true,nobatch:true});
const statusCall = rpc.declare({ object: 'proxy_guard', method: 'status', expect: { '': {} }, reject: true, nobatch: true });
const logsCall = rpc.declare({ object: 'proxy_guard', method: 'logs', expect: { '': {} }, reject: true, nobatch: true });
const applyCall = rpc.declare({ object: 'proxy_guard', method: 'apply', params:['confirm_flow'], expect: { '': {} }, reject: true });
const clearCall = rpc.declare({ object: 'proxy_guard', method: 'clear_logs', expect: { '': {} }, reject: true });
const preflightCall = rpc.declare({ object: 'proxy_guard', method: 'preflight', params: ['draft'], expect: { '': {} }, reject: true });
const phases = {
    waiting_interface: _("Waiting for LAN interface"), disabled: _("Disabled"), starting: _("Waiting for proxy startup"), healthy: _("Proxy healthy"),
    suspect: _("Possible failure"), blocked: _("Internet blocked"), down: _("Proxy failure (monitor only)"),
    recovering: _("Confirming recovery"), scheduled: _("Scheduled protection active"), error: _("Attention required"), unavailable: _("Service not started")
};
const enforcement = {
    off: _("Blocking is off"), allowing: _("Protected devices can access the Internet"), blocked: _("Internet access is blocked for protected devices"),
    missing: _("Protection rules are missing; protection cannot be confirmed"), unknown: _("Cannot verify firewall state"),
    unverified: _("Configuration or environment error; protection is unverified")
};
const weekdays = [_("Monday"), _("Tuesday"), _("Wednesday"), _("Thursday"), _("Friday"), _("Saturday"), _("Sunday")];

function scheduleText(schedule) {
    if (!schedule || !schedule.enabled) return _("Scheduled protection is off");
    const repeat = schedule.repeat_mode === 'weekdays' ?
        (schedule.weekdays || []).map(day => weekdays[day - 1]).filter(Boolean).join(_(", ")) : _("Every day");
    return _("Schedule: ") + repeat + ' ' + schedule.start + '–' + schedule.finish +
        _(" (") + (schedule.timezone || 'UTC+00:00') + _(")");
}

function formatTime(epoch) {
    return epoch ? new Date(epoch * 1000).toLocaleString() : _("Not available");
}

function fastText(f) {
    if (!f || !f.enabled) return '';
    if (f.stale) return _("Service monitor status is unavailable; awaiting verification");
    const running = name => f.required && f.required[name] === false ? _("Not configured") : f[name] ? _("Running") : _("Not running");
    let text = (f.client || '') + ' TCP: ' + running('tcp') + ' · UDP: ' + running('udp') + ' · DNS: ' + running('dns');
    return text;
}

function clientText(c) {
    if (!c) return _("Service monitoring is disabled");
    const errors = {
        multiple_clients_select_one:_("Multiple clients found; select one"),
        no_supported_client_installed:_("No supported proxy client found"),
        selected_client_not_installed:_("Selected proxy client is not installed"),
        unsupported_proxy_client:_("Unsupported proxy client"),
        client_socks_auth_unavailable:_("Client SOCKS authentication could not be prepared"),
        client_runtime_profile_unavailable:_("Client runtime configuration is unavailable"),
        client_listener_configuration_unavailable:_("Client listener configuration could not be verified"),
        client_dns_listener_unavailable:_("Client DNS listener could not be verified"),
        client_adapter_unavailable:_("Client adapter is unavailable"),
        multiple_client_profiles:_("Multiple active profiles require verification"),
        too_many_client_profiles:_("Client profile limit exceeded")
    };
    return (c.name === 'auto' ? _("Automatic detection") : c.name || _("Unknown")) +
        (c.error ? ' · ' + (errors[c.error] || _("Unavailable")) : '');
}

function passwallLogText(f) {
    if (f && f.enabled && f.stale) return _("Service monitor status is unavailable; awaiting verification");
    const log = f && f.log_watch;
    if (!log || !log.enabled) return _("Client log monitoring is off");
    if (!log.available) return _("Cannot read client log; service and proxy checks continue");
    if (log.clock_error) return _("Log time is invalid or outdated; it cannot confirm recovery");
    const events = {restart:_("Service restart requested"), rules_removed:_("Proxy rules removed"),
        sets_cleared:_("Rule sets cleared"), stopped:_("Proxy programs stopped"),
        rules_loading:_("Proxy rules are being loaded"), start_failed:_("Proxy startup failed"),
        complete:_("Startup completed"), cancelled:_("Restart cancelled"), gap:_("Log records were missed")};
    return (log.pending ? _("Waiting for this restart to finish") : _("Monitoring new log entries")) +
        (log.event ? _("; last event: ") + (events[log.event] || _("Unknown state")) + ' · ' + formatTime(log.event_time || log.observed_at) : '') +
        _("; last read: ") + formatTime(log.checked_at);
}

function activityText(s) {
    if (s.phase === "waiting_interface") return _("Waiting for LAN interface");
    const f = s.fast_watch;
    const monitor = s.mode === 'monitor';
    if (f && f.stale) return _("Service monitor status is unavailable; awaiting verification");
    if (!monitor && s.schedule && s.schedule.active) return phases.scheduled;
    if (f && !f.stale) {
        if (f.phase === 'log_wait' || (f.log_watch && f.log_watch.pending)) return _("Waiting for client startup and configured services to recover");
        if (f.phase === 'boot_wait') return _("Waiting for configured proxy services to start");
        if (f.phase === 'delay') return (monitor ? _("Monitoring only; checks resume in ") : _("Internet blocked; validation starts in ")) + f.wait_remaining + _(" seconds");
        if (f.phase === 'sensitive') return f.holding ?
            (monitor ? _("Monitoring only; confirming proxy recovery") : _("Validating the proxy before restoring access")) :
            (monitor ? _("Monitoring only; observing proxy stability: ") : _("Internet restored; enhanced monitoring: ")) + Math.min(f.stable_elapsed, f.stable_required) + '/' + f.stable_required + _(" seconds");
    }
    return pgI18n.runtime(s.reason) || phases[s.phase] || _("Unknown state");
}

function cfEventText(c) {
    if (!c || typeof c !== 'object' || !c.enabled) return _("Cloudflare event verification is off");
    const outcomes = {ok:_("Passed"), unavailable:_("Unavailable; routine exit verification continues"),
        mismatch:_("Exit mismatch; protection requires verification"), interrupted:_("Attempt interrupted; routine exit verification continues")};
    if (c.outcome === 'mismatch' && c.rechecking === false) outcomes.mismatch = _("Previous exit mismatch; routine verification has since passed");
    const pending = c.pending ? _("Waiting to verify after proxy recovery") : '';
    if (!c.attempted && !c.checked_at) return pending || _("No Cloudflare event check yet");
    return (pending ? pending + ' · ' : '') + (outcomes[c.outcome] || _("Awaiting verification")) +
        ' · ' + formatTime(c.checked_at) + (typeof c.observed === 'string' ? _("; observed ") + c.observed : '') +
        (typeof c.colo === 'string' ? ' · ' + _("Cloudflare data center") + ': ' + c.colo : '');
}

const recoveryReasons = {main_heartbeat:_("Connectivity monitor heartbeat expired"),fast_heartbeat:_("Service monitor heartbeat expired"),
    execution_errors:_("Repeated plugin execution errors"),recovery_timeout:_("Previous restart did not complete"),configuration:_("Configuration requires attention")};
function checkResultText(s) {
    if (!s.last_probe_at) return _("No completed checks yet");
    const failed=(s.probes || []).some(p => p.ok === false) || s.exit_check && s.exit_check.ok === false || s.udp_probe && s.udp_probe.enabled && s.udp_probe.ok === false;
    const confirmed=(s.probes || []).length>0 && s.probes.every(p => p.ok === true) && s.exit_check && (s.exit_check.enabled === false || s.exit_check.ok === true) && !(s.udp_probe && s.udp_probe.enabled && s.udp_probe.ok !== true);
    return (failed ? _("Failed") : confirmed ? _("Passed") : _("Awaiting verification")) + ' · ' + formatTime(s.last_probe_at) + (s.stale ? _(" · No recent update from the monitor") : '');
}
function recoveryText(s) {
    if (s.phase === 'disabled') return _("Protection is disabled; no recovery is pending");
    if (s.interface_waiting || s.phase === 'waiting_interface') return _("Waiting for LAN interface");
    if (s.mode === 'monitor' || s.enforcement === 'off') return _("Monitoring only; no access restrictions");
    if (['missing','unknown','unverified'].includes(s.enforcement)) return _("Resolve the reported error before protection can be confirmed");
    if (s.schedule && s.schedule.active) return _("Waiting for the scheduled window to end") + ' · ' + s.schedule.finish + ' ' + (s.schedule.timezone || '');
    const f=s.fast_watch || {};
    if (f.phase === 'delay') return _("Internet remains blocked during the waiting period; external checks have not started");
    if (f.phase === 'boot_wait' || f.phase === 'log_wait' || f.log_watch && f.log_watch.pending) return _("Waiting for client startup and configured services to recover");
    if (f.phase === 'sensitive' && f.holding) return _("Waiting for proxy verification before restoring access");
    if (f.phase === 'sensitive') return _("Access is allowed during enhanced monitoring; a failure blocks it again");
    return s.enforcement === 'blocked' ? _("Waiting for the required successful proxy checks") : _("No recovery is pending");
}

function supervisionText(s) {
    if (!s) return _("Self-check is waiting for its first update");
    if (s.stale) return _("Self-check heartbeat is delayed; check plugin services");
    const labels = {disabled:_("Protection is off"),stopped:_("Stopped by user"),watching:_("Automatic recovery is off"),
        starting:_("Allowing time for checks to start"),healthy:_("Plugin monitors are responding"),suspect:_("Rechecking a delayed heartbeat"),
        queued:_("Restarting this plugin"),cooldown:_("Waiting before another restart"),limited:_("Automatic restart limit reached"),
        config_error:_("Check configuration; automatic recovery is paused"),control_error:_("Service control state needs verification")};
    return (labels[s.state] || _("Unknown state")) + (s.restart_count != null ? _("; restarts in this window: ") + s.restart_count : '') +
        (s.restart_limit != null ? '/' + s.restart_limit : '') +
        (s.reason ? ' · ' + (recoveryReasons[s.reason] || _("Check plugin services")) : '') +
        (s.last_reason ? _("; last restart: ") + (recoveryReasons[s.last_reason] || _("Check plugin services")) + ' · ' + formatTime(s.last_restart_at) : '') +
        (s.last_restart_result === 'recovered' ? _("; monitors recovered after restart") : '') +
        (s.retry_in ? _("; seconds until retry: ") + Math.ceil(s.retry_in) : '');
}
const causeLabels = {boot:_("Startup"),watchdog:_("Service monitor interrupted"),worker:_("Connectivity monitor delayed"),
    log:_("Client lifecycle log changed"),services:_("Configured proxy service interrupted"),interruption:_("Service or proxy interruption"),schedule:_("Scheduled window ended")};
function incidentText(e) {
    if (!e) return _("No recovery event recorded");
    return formatTime(e.started_at) + ' · ' + Object.keys(causeLabels).filter(k => e.causes && e.causes[k]).map(k => causeLabels[k]).join(' / ') +
        _("; wait resets: ") + (e.resets || 0) + _("; elapsed seconds: ") + Math.floor(e.elapsed || 0) +
        (e.superseded ? _("; superseded by a later recovery record") : e.completed_uptime != null ? _("; observation completed") : e.holding ? _("; waiting to restore access") : _("; access restored, monitoring"));
}
function readStatus() {
    return statusCall().then(s => {
        if (s.ok === false)
            throw new Error(pgI18n.runtime(s.error) || _("Cannot read plugin status or logs"));
        if (!Object.prototype.hasOwnProperty.call(phases, s.phase) ||
            !Object.prototype.hasOwnProperty.call(enforcement, s.enforcement))
            throw new Error(_("Invalid status or log response"));
        return s;
    });
}

function readLogs() {
    return logsCall().then(logs => {
        if (logs.ok === false)
            throw new Error(pgI18n.runtime(logs.error) || _("Cannot read plugin status or logs"));
        if (!Array.isArray(logs.entries)) throw new Error(_("Invalid status or log response"));
        if (logs.details != null && !Array.isArray(logs.details)) throw new Error(_("Invalid status or log response"));
        return logs;
    });
}

return view.extend({
    load: function() {
        // A temporary status/log failure must not prevent rendering the page
        // and registering its automatic retries.
        return Promise.all([uci.load('proxy_guard'),setupInfoCall().then(info=>{this.proAvailable=info.pro_available===true;}).catch(()=>{this.proAvailable=false;})]);
    },

    updateStatus: function(s) {
        this.lastStatus = s;
        const log = s.fast_watch && s.fast_watch.log_watch;
        const waiting = s.interface_waiting === true;
        const fault = (['missing', 'unknown', 'unverified'].includes(s.enforcement) && !waiting) || s.stale ||
            (s.fast_watch && s.fast_watch.enabled && s.fast_watch.stale) ||
            (s.phase !== 'disabled' && s.supervision && s.supervision.enabled && s.supervision.stale) ||
            (log && log.enabled && (!log.available || log.clock_error));
        const titles = {off: s.phase === 'disabled' ? _("Protection is turned off") : _("Monitoring only; Internet access allowed"),
            allowing: _("Internet access allowed"), blocked: _("Internet access blocked")};
        const row = (label, value) => E('div', { class: 'pg-status-row', style: 'display:flex;flex-wrap:wrap;gap:.3em 1em;margin:.5em 0;overflow-wrap:anywhere;' },
            [E('strong', {style:'flex:0 0 11em;'}, [label]), E('span', {style:'flex:1 1 16em;min-width:0;'}, [value])]);
        this.statusBox.className = 'alert-message ' + (fault ? 'danger' : waiting || s.enforcement === 'blocked' ? 'warning' : 'notice');
        this.statusBox.replaceChildren(
            E('strong', {id:'pg-access-state'}, [fault ? _("Protection status needs verification") : waiting ? _("Waiting for LAN interface") : titles[s.enforcement] || _("Awaiting verification")]),
            row(_("Internet access"), waiting ? _("Interface not ready; protection coverage is unverified") : enforcement[s.enforcement] || _("Awaiting verification")),
            row(_("Latest connectivity check"), checkResultText(s)),
            row(_("Current protection reason"), pgI18n.runtime(s.firewall_error) || activityText(s)),
            row(_("Access recovery"), recoveryText(s)),
            ...(s.remote_health && s.remote_health.required ? [row(_("VPS service health"),s.remote_health.ok?_("Ready"):_("Unavailable"))] : []),
            row(_("Proxy client"), clientText(s.client)),
            row(_("Proxy client services"), fastText(s.fast_watch) || _("Service monitoring is disabled")),
            row(_("Proxy client runtime log"), passwallLogText(s.fast_watch)),
            row(_("Schedule"), s.phase === 'disabled' ? _("Protection is disabled; schedules will not run") : scheduleText(s.schedule) +
                (s.schedule && s.schedule.enabled ? (s.mode === 'monitor' ? _(" · Monitor only; no blocking") : s.schedule.active ? _(" · Within the scheduled window") : '') : '')),
            row(_("Observed proxy exit"), s.exit_check && s.exit_check.enabled === false ? _("Exit IP verification is disabled") : s.exit_check ? (s.exit_check.ok ? _("Passed") : _("Failed")) + _("; observed ") + (s.exit_check.observed || _("Unknown")) + _("; expected ") + (s.exit_check.expected || _("Not configured")) : _("Exit has not been checked")),
            row(_("Last Cloudflare event verification"), cfEventText(s.cf_event)),
            row(_("HTTPS connectivity checks"), (s.probes || []).map(p => p.host + _(": ") + (p.ok ? _("Success") : _("Failed")) + _(", ") + p.milliseconds + ' ms').join(_("; ")) || _("No completed checks yet")),
            row(_("UDP proxy path check"), s.udp_probe && s.udp_probe.enabled ? (s.udp_probe.ok ? _("Passed") : _("Failed")) + ' · ' + (s.udp_probe.milliseconds || 0) + ' ms' : _("UDP proxy path check is disabled")),
            row(_("Plugin self-check"), supervisionText(s.supervision)),
            row(_("Plugin resource usage"), s.supervision && s.supervision.resources ?
                _("Memory (RSS)") + ': ' + s.supervision.resources.rss_kib + ' KiB · ' + _("CPU (total)") + ': ' + (s.supervision.resources.cpu_percent == null || s.supervision.resources.cpu_basis !== 'all_online_cpus' ? _("Sampling") : s.supervision.resources.cpu_percent + '%') +
                ' · ' + _("Logical processors") + ': ' + (s.supervision.resources.cpu_cores || _("Unknown")) +
                ' · ' + _("Process count") + ': ' + s.supervision.resources.process_count + ' · ' + _("Logs in RAM") + ': ' + s.supervision.resources.log_bytes + ' B' : _("Resource statistics are disabled or awaiting the first sample")),
            row(_("Current recovery event"), incidentText(s.fast_watch && s.fast_watch.episode)),
            row(_("Last completed check"), formatTime(s.last_probe_at) + (s.stale ? _(" · No recent update from the monitor") : '')),
            E('small', {}, [_("Status refreshes automatically every second. Last update: ") + new Date().toLocaleTimeString()])
        );
    },

    updateLogs: function(logs) {
        this.lastLogs = logs;
        const stages={boot_wait:_("Waiting for startup"),boot_ready:_("Startup wait begins"),blocked:_("Interruption detected"),
            sensitive:_("Recovery checks begin"),log_ready:_("Startup log and services indicate recovery"),restored:_("Internet restored; observation begins"),
            schedule_sensitive:_("Scheduled window ended; observation begins"),normal:_("Enhanced monitoring completed")};
        if (this.incidentBox) this.incidentBox.textContent = (logs.incidents || []).slice(-10).map(item =>
            incidentText(item.summary) + '\n  ' + (item.steps || []).filter(step => Object.prototype.hasOwnProperty.call(stages,step.stage))
                .map(step => '+' + Math.floor(step.elapsed || 0) + 's ' + stages[step.stage]).join(' → ')).join('\n\n') || _("No recovery event recorded");
        const format = entries => entries.map(e => formatTime(e.time) + ' [' + e.level + '] ' + pgI18n.runtime(e.message)).join('\n') || _("No log entries");
        this.logBox.textContent = format(logs.entries);
        this.checkLogBox.textContent = format(logs.details || []);
        this.logWarning.textContent = logs.skipped ? _("Some damaged log entries were skipped: ") + logs.skipped : '';
    },

    refreshStatus: function() {
        // The poll callback remains runnable during slow RPCs. Only one
        // status request is in flight; stale success must not remain green.
        if (performance.now() - this.statusUpdatedAt > 5000) {
            this.statusBox.className = 'alert-message danger';
            this.statusBox.textContent = _("Status updates are delayed; retrying automatically. Protection cannot be confirmed.");
        }
        if (this.statusRequest) return this.statusRequest;
        this.statusRequest = readStatus().then(s => {
            this.updateStatus(s);
            this.statusUpdatedAt = performance.now();
        }).catch(err => {
            this.statusBox.className = 'alert-message danger';
            this.statusBox.textContent = _("Cannot read status; protection cannot be confirmed: ") + pgI18n.runtime(err.message);
        }).finally(() => { this.statusRequest = null; });
        return this.statusRequest;
    },

    refreshLogs: function() {
        if (this.logsRequest) return this.logsRequest;
        this.logsRequest = readLogs().then(logs => this.updateLogs(logs)).catch(err => {
            this.logBox.textContent = _("Cannot read plugin logs: ") + pgI18n.runtime(err.message);
            this.checkLogBox.textContent = ''; this.logWarning.textContent = '';
        }).finally(() => { this.logsRequest = null; });
        return this.logsRequest;
    },

    refresh: function() {
        return Promise.all([this.refreshStatus(), this.refreshLogs()]);
    },

    fetchExit: function() {
        if(this.exitRequest)return this.exitRequest;
        const sourceOption=this.formSection.children.find(o=>o.option==='exit_source');
        const source=sourceOption&&sourceOption.formvalue('main');
        const read=async()=>{
            let result=await egressInfoCall(true);
            const deadline=performance.now()+35000;
            while(result&&result.ok===true&&result.phase==='pending'&&performance.now()<deadline){
                await new Promise(resolve=>setTimeout(resolve,1000));
                result=await egressInfoCall(false);
            }
            if(result&&result.phase==='pending')throw new Error(_("VPS address read timed out"));
            return result;
        };
        this.exitRequest=read().then(result=>{
            if(!result||result.ok!==true||!Array.isArray(result.candidates))throw new Error(result&&result.error||_("Unable to read VPS address candidates"));
            const candidates=result.candidates.filter(row=>Array.isArray(row.evidence)&&row.evidence.some(e=>e.source===String(source).replace('vps_','')));
            let selected=candidates.length===1?candidates[0].ipv4:null;
            const use=E('button',{type:'button',class:'cbi-button cbi-button-action',disabled:!selected?true:null,click:()=>{
                const field=this.formSection.children.find(o=>o.option==='expected_exit4');
                field.getUIElement('main').setValue(selected);
                this.extraDraft=Object.assign({},this.extraDraft,{exit_fetched_at:String(result.generated_at)});
                this.updateDraftIndicator();ui.hideModal();
            }},[_("Use this address")]);
            const choices=candidates.map(row=>E('label',{style:'display:block;margin:.6em 0;'},[
                E('input',{type:'radio',name:'pg-vps-exit-candidate',value:row.ipv4,checked:selected===row.ipv4?true:null,change:()=>{selected=row.ipv4;use.disabled=false;}}),' ',
                E('bdi',{dir:'ltr'},[row.ipv4])
            ]));
            pgI18n.modal(ui,_("Review VPS address candidates"),[
                E('p',{},[_("Interface and panel addresses, and the VPS default-route address, may differ from the proxy exit. This import does not verify proxy traffic.")]),
                E('p',{},[_("Retrieved at: ")+formatTime(result.generated_at)]),
                ...choices,
                candidates.length?'':E('p',{},[_("No usable IPv4 candidate exists for this source. Check the Agent settings or enter the expected address manually.")]),
                E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[_("Cancel")]),' ',use
            ]);
        }).catch(err=>this.showActionError(err)).finally(()=>{this.exitRequest=null;});
        return this.exitRequest;
    },

    preflight: function() {
        const draft = Object.assign({}, uci.get ? uci.get('proxy_guard', 'main') : {});
        this.formSection.children.forEach(option => {
            const value = option.formvalue('main');
            if (value != null) draft[option.option] = value;
        });
        this.preflightBox.textContent = _("Checking unsaved settings without saving or probing the Internet...");
        return preflightCall(JSON.stringify(draft)).then(result => {
            const labels = {configured_offload:_("Configured flow offloading"),running_offload:_("Active kernel flowtables"),bridge_filtering:_("Bridge filtering"),kernel_features:_("Required nftables kernel features"),client_mode:_("Proxy client forwarding mode"),homeproxy_tun_ipv6_udp:_("HomeProxy TUN IPv6 UDP compatibility"),configuration:_("Configuration format"),interfaces:_("Ingress devices"),compatibility:_("Firewall compatibility"),
                socks_listener:_("Local SOCKS listener"),udp_runtime:_("UDP check support library"),passwall_services:_("Proxy client services"),
                ipv6_scope:_("IPv6 covers all sources on the selected devices"),schedule_clock:_("System clock"),
                topology:_("Traffic bypassing this router cannot be protected; validate the actual topology")};
            const levels = {ok:_("Passed"),warning:_("Please verify"),error:_("Needs attention"),off:_("Disabled")};
            this.preflightBox.textContent = (result.checks || []).map(row => (labels[row.code] || _("Unknown state")) + ': ' + (levels[row.level] || _("Unknown state")) + (row.detail ? ' · ' + pgI18n.runtime(row.detail) : '')).join('\n') +
                (result.error ? '\n' + pgI18n.runtime(result.error) : '') + '\n' + _("Read-only check: settings have not been saved or applied, and proxy Internet connectivity has not been tested.");
        }).catch(err => { this.preflightBox.textContent = pgI18n.runtime(err.message) || _("Cannot complete self-check"); });
    },

    diagnosticData: function() {
        // Export a whitelist only. Never copy status, configuration, raw logs,
        // URLs, addresses, identifiers or arbitrary strings into the report.
        const s=this.lastStatus || {}, watch=s.fast_watch || {}, heal=s.supervision || {}, resources=heal.resources || {};
        const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value < 1e12 ? Math.round(value * 10) / 10 : null;
        const pick = (object,keys) => Object.fromEntries(keys.map(key => [key,number(object[key])]));
        return {format:'proxy-guard-diagnostic-v1',version:typeof s.version === 'string' && /^\d+\.\d+\.\d+$/.test(s.version) ? s.version : null,
            phase:Object.prototype.hasOwnProperty.call(phases,s.phase) ? s.phase : null,
            enforcement:Object.prototype.hasOwnProperty.call(enforcement,s.enforcement) ? s.enforcement : null,
            stale:s.stale === true,services:{enabled:watch.enabled === true,available:watch.enabled === true && !watch.stale,tcp:watch.tcp === true,udp:watch.udp === true,dns:watch.dns === true},
            checks:pick(s,['successes','failures','lease_seconds','probe_budget','probe_cpu_ms']),
            resources:pick(resources,['rss_kib','cpu_percent','cpu_core_percent','cpu_cores','process_count','log_bytes']),
            recovery:Object.assign(pick(heal,['restart_count','restart_limit','retry_in','failures','main_threshold']), {state:['disabled','stopped','watching','starting','healthy','suspect','queued','cooldown','limited','config_error','control_error'].includes(heal.state) ? heal.state : null,reason:Object.prototype.hasOwnProperty.call(recoveryReasons,heal.last_reason) ? heal.last_reason : null,result:['queued','recovered'].includes(heal.last_restart_result) ? heal.last_restart_result : null}),
            udp:{enabled:s.udp_probe && s.udp_probe.enabled === true || false,ok:s.udp_probe && s.udp_probe.ok === true || false},
            incidents:(this.lastLogs && this.lastLogs.incidents || []).slice(-10).map(item => {
                const e=item.summary || {};
                return Object.assign(pick(e,['elapsed','resets','stable_elapsed','stable_required']),
                    {holding:e.holding === true,completed:e.completed_uptime != null,superseded:e.superseded === true,
                    causes:Object.keys(causeLabels).filter(k => e.causes && e.causes[k] === true)});
            })};
    },

    showDiagnostics: function() {
        const text = JSON.stringify(this.diagnosticData(),null,2);
        const download = () => {
            const url=URL.createObjectURL(new Blob([text+'\n'],{type:'application/json'}));
            const anchor=E('a',{href:url,download:'proxy-guard-diagnostic.json'});anchor.click();
            setTimeout(() => URL.revokeObjectURL(url),1000);
        };
        pgI18n.modal(ui,_("Local diagnostic report"),[
            E('p',{},[_("This report contains only state names and measurements. It excludes IP addresses, URLs, configuration and raw logs. Review it before sharing. Nothing is uploaded.")]),
            E('pre',{style:'max-height:50vh;overflow:auto;white-space:pre-wrap;'},[text]),
            E('button',{type:'button',class:'cbi-button cbi-button-action',click:download},[_("Download report")]),
            E('button',{type:'button',class:'cbi-button cbi-button-neutral',click:ui.hideModal},[_("Close")])]);
    },

    formSnapshot: function() {
        return JSON.stringify([this.extraDraft||{},this.formSection.children.map(option =>
            [option.option, option.formvalue('main')])]);
    },

    updateDraftIndicator: function() {
        // Browser-only edits must not be written to UCI just to show a badge.
        if (this.formSnapshot() !== this.savedFormSnapshot)
            ui.showIndicator('proxy-guard-draft', _("Unsaved changes"));
        else
            ui.hideIndicator('proxy-guard-draft');
    },

    render: function() {
        const m = new form.Map('proxy_guard');
        const s = m.section(form.NamedSection, 'main', 'proxy_guard');
        s.addremove = false;
        s.tab('general', _("General settings"));
        s.tab('scope', _("Protection scope"));
        s.tab('schedule', _("Scheduled protection"));
        s.tab('health', _("Plugin self-check and recovery"));
        s.tab('advanced', _("Connection checks"));
        s.tab('fast', _("Failure protection and recovery"));
        let o = s.taboption('general', form.Flag, 'enabled', _("Enable protection"));
        o.rmempty = false;
        o = s.taboption('general', form.ListValue, 'mode', _("Operating mode"));
        o.value('monitor', _("Monitor only: log failures without blocking"));
        o.value('guard', _("Protect: block Internet traffic in both directions on failure"));
        o.default = 'monitor'; o.rmempty = false;
        o = s.taboption('general', form.Value, 'socks_port', _("Local SOCKS port"), _("Checks always use the SOCKS5 proxy on 127.0.0.1, with no direct fallback."));
        o.datatype = 'port'; o.default = '1070'; o.rmempty = false;
        o = s.taboption('general', form.Flag, 'exit_check', _("Verify proxy exit IPv4"), _("Optional. When off, connectivity checks continue without requiring or comparing an expected exit address."));
        o.default='0';o.rmempty=false;
        o = s.taboption('general', form.Value, 'expected_exit4', _("Expected proxy exit IPv4"), _("Required only when exit IP verification is enabled. A different exit or an unreachable verification service is treated as a failure."));
        o.datatype = 'ip4addr("nomask")'; o.rmempty = false; o.depends('exit_check','1');o.retain=true;
        if(this.proAvailable){
            o=s.taboption('general',form.ListValue,'exit_source',_("Expected IPv4 source"));
            o.value('manual',_("Enter manually"));
            o.value('vps_interface',_("VPS public interface address"));
            o.value('vps_panel',_("IPv4 hints from panel configuration"));
            o.value('vps_measured',_("VPS default-route measurement"));
            o.default='manual';o.rmempty=false;o.depends('exit_check','1');o.retain=true;
            o=s.taboption('general',form.Button,'_read_vps_exit',_("Import expected IPv4 from VPS"));
            o.inputtitle=_("Read saved VPS connection");
            o.description=_("Uses the saved Pro connection. Importing an address only edits this form; Save & Apply is still required.");
            for(const value of ['vps_interface','vps_panel','vps_measured'])o.depends({exit_check:'1',exit_source:value});
            o.onclick=()=>this.fetchExit();
        }


        o = s.taboption('fast', form.ListValue, 'proxy_client', _("Proxy client"),
            _("Detect one installed client automatically. When several are installed, select the client to monitor. This does not modify the client configuration."));
        o.value('auto', _("Automatic detection"));
        for (const name of ['passwall', 'passwall2', 'openclash', 'nikki', 'homeproxy'])
            o.value(name, {passwall:'PassWall',passwall2:'PassWall2',openclash:'OpenClash',nikki:'Nikki',homeproxy:'HomeProxy'}[name]);
        o.default = 'auto'; o.rmempty = false;
        o = s.taboption('fast', form.Flag, 'client_auto_ports', _("Use detected client listener ports"),
            _("Use verified SOCKS, proxy listener and DNS redirect exception ports for this plugin. Keep this off to use manual ports. Client, DNS, route and NAT settings are not changed."));
        o.default = '0'; o.rmempty = false; o.depends('passwall_watch', '1');
        o = s.taboption('fast', form.Flag, 'passwall_watch', _("Monitor proxy client services"),
            _("Check the selected client every second using its configured TCP, UDP and DNS capabilities. Unconfigured capabilities are shown separately. Keep the existing real proxy checks and preserve router, LAN and DNS access."));
        o.default = '0'; o.rmempty = false;
        o = s.taboption('fast', form.Flag, 'boot_guard', _("Enable boot protection"),
            _("At boot or activation, block protected devices until the selected client configured services start, then wait without external probes. Validate the proxy before restoring access and beginning enhanced monitoring. Router, LAN and DNS remain available."));
        o.depends('passwall_watch', '1'); o.default = '0'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.ListValue, 'passwall_trigger', _("Service failure trigger"));
        o.value('any', _("Any service stops or restarts"));
        o.value('all', _("All configured services stop or restart"));
        o.depends('passwall_watch', '1'); o.default = 'any'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Flag, 'passwall_log_watch', _("Watch proxy client runtime log"),
            _("Read the selected client lifecycle log using audited source-specific messages and timestamps. Log recovery still requires healthy configured services and a real proxy check. Initial recovery skips the extra delay; failures during enhanced monitoring retain the configured delay."));
        o.depends('passwall_watch', '1'); o.default = '0'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Value, 'passwall_log_interval', _("Read client log every (seconds)"),
            _("Read only added log data, every 1–10 seconds. Local service checks continue every second. Apply changes with Save & Apply."));
        o.depends({passwall_watch:'1', passwall_log_watch:'1'});
        o.datatype = 'range(1,10)'; o.default = '1'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Flag, 'fast_wait_enabled', _("Block before recovery checks"),
            _("Block Internet access without external probes during this delay; local service monitoring continues. Disabling this option starts verification immediately."));
        o.depends('passwall_watch', '1'); o.default = '1'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Value, 'fast_wait_seconds', _("Blocking delay (seconds)"));
        o.depends({ passwall_watch: '1', fast_wait_enabled: '1' });
        o.datatype = 'range(1,3600)'; o.default = '15'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Flag, 'fast_stable_enabled', _("Enable enhanced monitoring after recovery"),
            _("Restore Internet access after proxy validation. During enhanced monitoring, start each round one second after the previous round completes; request time is additional. Any failed round blocks access and restarts the delay. Disabling enhanced monitoring still requires recovery validation."));
        o.depends('passwall_watch', '1'); o.default = '1'; o.rmempty = false; o.retain = true;
        o = s.taboption('fast', form.Value, 'fast_stable_seconds', _("Enhanced monitoring duration (seconds)"));
        o.depends({ passwall_watch: '1', fast_stable_enabled: '1' });
        o.datatype = 'range(1,3600)'; o.default = '60'; o.rmempty = false; o.retain = true;

        o = s.taboption('schedule', form.Flag, 'schedule_enabled', _("Enable scheduled protection"),
            _("No schedule is prefilled. Set the time and repeat pattern before enabling scheduled protection. Blocking requires the main switch and protection mode. DNS, LAN and management remain available. With service protection enabled, the window ends into enhanced monitoring without an extra delay; otherwise recovery checks are required."));
        o.default = '0'; o.rmempty = false;
        o = s.taboption('schedule', form.ListValue, 'schedule_utc_offset', _("Time zone"),
            _("Time and weekdays use the selected fixed UTC offset. Router time zone is unchanged; daylight saving time is not automatic. The default is UTC+00:00."));
        for (let minutes = -720; minutes <= 840; minutes += 15) {
            const absolute = Math.abs(minutes);
            const offset = (minutes < 0 ? '-' : '+') + String(Math.floor(absolute / 60)).padStart(2, '0') + ':' + String(absolute % 60).padStart(2, '0');
            o.value(offset, 'UTC' + offset + (minutes === 480 ? _(" (Beijing time)") : ''));
        }
        o.default = '+00:00'; o.rmempty = false;
        o = s.taboption('schedule', form.ListValue, 'schedule_repeat', _("Repeat"));
        o.value('', '—');
        o.value('daily', _("Every day"));
        o.value('weekdays', _("Weekly (choose days)"));
        o.default = ''; o.rmempty = false; o.retain = true;
        o.depends('schedule_enabled', '1');
        o.validate = function(section, value) {
            return value === 'daily' || value === 'weekdays' ||
                _("Repeat") + ': ' + _("Every day") + ' / ' + _("Weekly (choose days)");
        };
        o = s.taboption('schedule', form.MultiValue, 'schedule_weekdays', _("Days of the week"),
            _("Choose any combination of days. An overnight window belongs to its start day: Monday 23:00–01:00 continues into Tuesday morning."));
        o.display_size = 7; o.dropdown_size = 7; o.rmempty = false;
        o.retain = true;
        weekdays.forEach((label, index) => o.value(String(index + 1), label));
        o.default = [];
        o.depends({ schedule_enabled: '1', schedule_repeat: 'weekdays' });
        o.validate = function(section, value) {
            return (Array.isArray(value) ? value.length > 0 : !!value) || _("Select at least one day");
        };
        [['schedule_start', _("Start time")],
         ['schedule_end', _("End time")]].forEach(item => {
            const option = s.taboption('schedule', form.Value, item[0], item[1],
                _("Use HH:MM:SS in the selected time zone. Overnight windows are supported. Keep the router clock accurate; start and end must differ."));
            option.default = ''; option.placeholder = 'HH:MM:SS'; option.rmempty = false; option.retain = true;
            option.depends('schedule_enabled', '1');
            option.validate = function(section, value) {
                return /^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(value) || _("Enter a valid HH:MM:SS time");
            };
        });

        o=s.taboption('scope',form.Flag,'ipv6_protect',_('Protect IPv6 traffic'),_('IPv6 matching is independent of IPv4. Turning this off leaves IPv6 traffic outside plugin protection.'));o.default='1';o.rmempty=false;
        const lists = [
            ['interfaces', _("Ingress devices"), _("For example, br-lan. Use existing, enabled layer-3 devices, not switch ports within a bridge. WireGuard and Docker are not included automatically."), null],
            ['sources4', _("Protected IPv4 addresses"), _("Use 192.0.2.100/32 for a single-device trial, or 192.0.2.0/24 for the subnet."), 'ip4addr'],
            ['sources6', _("Protected IPv6 addresses"), _("For a single-device trial, specify its IPv6 addresses or prefixes separately. ::/0 matches all IPv6 sources routed through selected ingress devices. Use the IPv6 switch to exclude this family explicitly."), 'ip6addr'],
            ['local4', _("Allowed LAN IPv4 networks"), _("These networks remain reachable during failures. Do not enter 0.0.0.0/0."), 'ip4addr'],
            ['local6', _("Allowed LAN IPv6 networks"), _("Link-local, multicast and the router's own management addresses remain accessible."), 'ip6addr'],
            ['proxy_ports', _("Local proxy ingress ports"), _("Block these local ports as well, preventing devices with explicit SOCKS settings from bypassing protection."), 'port'],
            ['dns_ports', _("DNS redirect destination ports"), _("Default: 53. Enter the actual port if existing DNS redirection uses another port. Only requests and replies redirected to local or allowed LAN DNS are exempt. DNS settings are unchanged. Do not overlap proxy ingress ports."), 'port']
        ];
        lists.forEach(item => {
            const option = s.taboption('scope', form.DynamicList, item[0], item[1], item[2]);
            if (item[3]) option.datatype = item[3];
            if(item[0]==='sources6'){option.depends('ipv6_protect','1');option.retain=true;option.rmempty=false;}
            if (item[0] === 'dns_ports') { option.default = ['53']; option.rmempty = false; }
        });
        const fields = [
            ['interval', _("Interval after each check round (seconds)"), '10', 5, 300],
            ['timeout', _("Timeout per target (seconds)"), '4', 1, 15],
            ['fail_threshold', _("Consecutive failed rounds"), '3', 1, 10],
            ['recover_threshold', _("Consecutive successful rounds for recovery"), '2', 1, 10],
            ['startup_grace', _("Startup grace deadline (seconds since boot)"), '150', 0, 600],
            ['min_success', _("Minimum successful targets per round"), '1', 1, 4],
            ['log_kib', _("Maximum size per log file (KiB)"), '64', 16, 512]
        ];
        fields.forEach(item => {
            const option = s.taboption('advanced', form.Value, item[0], item[1]);
            option.default = item[2]; option.datatype = 'range(' + item[3] + ',' + item[4] + ')'; option.rmempty = false;
            if (item[0] === 'startup_grace') option.description = _("Boot protection replaces this fixed startup grace period.");
        });
        o = s.taboption('advanced', form.DynamicList, 'targets', _("HTTPS check targets"), _("Configure 2–4 targets as https://domain/path|expected_status. Connections use the proxy. This does not test the health of every UDP service."));
        o.rmempty = false;
        o = s.taboption('advanced', form.Value, 'exit_url', _("Exit verification HTTPS URL"), _("Routine exit verification uses ipify by default. Accepts a plain-text IPv4 address or a compatible trace response. Requests always use the local SOCKS proxy. Keep Cloudflare trace out of recurring targets to avoid frequent Cloudflare requests."));
        o.rmempty = false;o.depends('exit_check','1');o.retain=true;
        o = s.taboption('advanced', form.Flag, 'cf_event_check', _("Verify with Cloudflare after startup or an interruption"),
            _("Make one extra request when the proxy first becomes ready after boot, and once after each interruption recovers. Signals from the same interruption are combined. No daily timer or repeated polling. A Cloudflare timeout does not replace the required routine exit check; a mismatching exit requires protection."));
        o.default='1';o.rmempty=false;o.depends('exit_check','1');o.retain=true;
        o = s.taboption('advanced', form.Flag, 'udp_check', _("Verify UDP through the proxy"),
            _("Optional check: send a DNS-format UDP request through local SOCKS5 UDP ASSOCIATE. Requires luci-lib-nixio and a proxy with UDP support; never falls back to a direct connection. Failure counts as a failed check round. The result covers only this target, not every UDP service."));
        o.default='0';o.rmempty=false;
        [['udp_server',_("UDP check target IPv4"),'','ip4addr("nomask")'],
         ['udp_port',_("UDP check target port"),'53','port'],['udp_query',_("UDP query domain"),'example.com','hostname'],
         ['udp_timeout',_("UDP check timeout (seconds)"),'3','range(1,10)']].forEach(item => {
            const option=s.taboption('advanced',form.Value,item[0],item[1]);option.depends('udp_check','1');option.retain=true;
            option.default=item[2];option.datatype=item[3];option.rmempty=false;
        });
        o=s.taboption('health',form.Flag,'self_heal',_("Automatically restart unresponsive plugin monitors"),
            _("An independent watchdog checks plugin heartbeats every five seconds using a clock unaffected by wall-clock adjustments. It restarts this plugin after persistent heartbeat or execution failures. Proxy outages and configuration errors do not trigger restart loops. Manual stop and disabling protection take precedence."));
        o.default='1';o.rmempty=false;
        [['self_heal_stale',_("Minimum heartbeat timeout (seconds)"),'30',15,600],
         ['self_heal_cooldown',_("Minimum time between restarts (seconds)"),'60',30,3600],
         ['self_heal_limit',_("Maximum restarts within the window"),'3',1,10],
         ['self_heal_window',_("Restart counting window (seconds)"),'600',60,3600]].forEach(item => {
            const option=s.taboption('health',form.Value,item[0],item[1]);option.default=item[2];option.datatype='range('+item[3]+','+item[4]+')';
            option.depends('self_heal','1');option.retain=true;option.rmempty=false;
            if (item[0]==='self_heal_stale') option.description=_("The effective timeout also allows for a complete check round and the access permit lifetime, so it may exceed this minimum.");
        });
        o=s.taboption('health',form.Flag,'resource_monitor',_("Show plugin resource use"),
            _("Sample plugin resources every five seconds. CPU usage is a percentage of the combined capacity of all online logical processors; 100% means all of them are fully used. Memory is the sum of process RSS and may include shared pages more than once. Sampling stores no history on flash. Heartbeat monitoring continues when resource sampling is off."));
        o.default='1';o.rmempty=false;
        o = s.taboption('advanced', form.Flag, 'debug', _("Detailed check logs"), _("Changing only logging options does not restart checks or reset permits. Logs are stored in memory, cleared on reboot, and also sent to the system log."));
        o.rmempty = false;

        this.map = m;
        this.formSection = s;
        this.statusBox = E('div', { id: 'proxy-guard-status', class: 'alert-message notice', role: 'status', 'aria-live': 'polite' }, [_("Awaiting verification")]);
        this.logBox = E('pre', { style: 'max-height:22em;overflow:auto;white-space:pre-wrap;' });
        this.checkLogBox = E('pre', { style: 'max-height:16em;overflow:auto;white-space:pre-wrap;' });
        this.logWarning = E('p', {role:'status'});
        this.preflightBox=E('pre',{id:'pg-preflight',role:'status',style:'white-space:pre-wrap;'});
        this.incidentBox=E('pre',{id:'pg-incidents',style:'max-height:12em;overflow:auto;white-space:pre-wrap;'});
        this.statusUpdatedAt = performance.now();
        // Keep the heading/status outside the rerendered form so Save does
        // not remove the status node. Editing fields has no service action.
        return m.render().then(node => {
            this.refresh();
            poll.add(() => { this.refreshStatus(); }, 1);
            poll.add(() => this.refreshLogs(), 5);
            this.savedFormSnapshot = this.formSnapshot();
            this.updateDraftIndicator();
            setTimeout(()=>pgSetup.attach(this),0);
            ['input', 'change', 'widget-change'].forEach(event =>
                node.addEventListener(event, () => this.updateDraftIndicator()));
            return pgI18n.decorate(E('div', {}, [
                E('style',{},['.pg-guard[dir=rtl] .cbi-value{display:flex;flex-wrap:wrap;gap:.4em}.pg-guard[dir=rtl] .cbi-value-title{float:none;text-align:start;flex:0 0 12em}.pg-guard[dir=rtl] .cbi-value-field{margin:0;flex:1;min-width:14em}.pg-guard .pg-status-row span{unicode-bidi:plaintext}@media(max-width:600px){.pg-guard[dir=rtl] .cbi-value-title{flex-basis:100%}}']),
                E('h2', {}, [_("Proxy Guard")]), this.statusBox,
                E('div', { class: 'cbi-map-descr' }, [
                    _("On proxy failure, block Internet traffic in both directions for selected devices where traffic actually passes through this router or proxy. LAN access remains available. Return traffic bypassing this device cannot be blocked. Disabled on first install; start with monitoring, then test one device.")
                ]),
                E('div',{class:'cbi-section'},[
                    E('button',{type:'button',class:'cbi-button cbi-button-action',click:()=>pgSetup.open(false)},[_("Run setup wizard")]),' ',E('a',{class:'cbi-button',href:'proxy-guard-raw'},[_('Raw UCI configuration')]),' ',
                    E('button',{type:'button',class:'cbi-button',click:()=>pgSetup.restorePrevious()},[_("Load previous confirmed settings")]),' ',
                    E('button',{type:'button',class:'cbi-button',click:()=>pgI18n.modal(ui,_("Restore defaults and set up again"),[
                        E('p',{},[_("This prepares default plugin settings for review. Existing protection continues until you Save & Apply.")]),
                        E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[_("Cancel")]),' ',
                        E('button',{type:'button',class:'cbi-button cbi-button-action',click:()=>pgSetup.open(true)},[_("Continue")])
                    ])},[_("Restore defaults and set up again")])
                ]), node,
                E('div',{class:'cbi-section'},[
                    E('button',{type:'button',class:'cbi-button cbi-button-neutral',click:ui.createHandlerFn(this,this.preflight)},[_("Check settings and runtime environment")]),
                    E('button',{type:'button',class:'cbi-button cbi-button-neutral',click:ui.createHandlerFn(this,this.showDiagnostics)},[_("View sanitized diagnostic report")]),
                    this.preflightBox]),
                E('details',{},[E('summary',{},[_("Recovery history")]),this.incidentBox]),
                E('h3', {}, [_("Event log")]),
                E('p', {}, [_("Protection events stay here. Frequent website checks are listed separately below.")]),
                this.logWarning, this.logBox,
                E('details', {id:'pg-check-details'}, [E('summary', {}, [_("Recent connectivity check details")]), this.checkLogBox]),
                E('button', { type: 'button', class: 'cbi-button cbi-button-neutral', click: ui.createHandlerFn(this, function() {
                    return clearCall().then(result => {
                        if (!result.ok) throw new Error(pgI18n.runtime(result.error) || _("Failed to clear logs"));
                        return this.refresh();
                    }).catch(err => this.showActionError(err));
                }) }, [_("Clear logs")])
            ]));
        });
    },

    saveForm: function() {
        // Save stages this session's UCI changes; it does not start the service.
        for(const [key,value]of Object.entries(this.extraDraft||{}))uci.set('proxy_guard','main',key,value);
        return this.map.save().then(() => {
            this.savedFormSnapshot = this.formSnapshot();
            this.updateDraftIndicator();
        });
    },

    showActionError: function(err) {
        // LuCI's button handler restores the button but does not display rejected
        // promises. Render the diagnostic as text, never as notification HTML.
        ui.addNotification(null, E('p', {}, [_(pgI18n.runtime(err.message) || _("Apply failed"))]), 'error');
    },

    handleSave: function() {
        return this.saveForm().catch(err => this.showActionError(err));
    },

    handleReset: function() {
        this.extraDraft={};
        return this.map.reset().then(() => {
            this.savedFormSnapshot = this.formSnapshot();
            this.updateDraftIndicator();
        }).catch(err => this.showActionError(err));
    },

    handleSaveApply: function() {
        return this.saveForm().then(() => applyCall(true)).then(result => {
            if (!result.ok) {
                if(result.active_enabled===false){
                    const option=this.formSection.children.find(o=>o.option==='enabled');
                    option.getUIElement('main').setValue('0');uci.set('proxy_guard','main','enabled','0');this.updateDraftIndicator();
                }
                throw new Error(pgI18n.runtime(result.error) || _("Apply failed"));
            }
            pgSetup.begin(result);
            // Reload the indicator from rpcd: other pages may still have
            // pending changes, so never clear the global counter blindly.
            return Promise.all([this.refresh(), ui.changes.init()]);
        }).catch(err => this.showActionError(err));
    }
});
