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
const statusCall = rpc.declare({ object: 'proxy_guard', method: 'status', expect: { '': {} }, reject: true, nobatch: true });
const apiCredentialsCall = rpc.declare({ object: 'proxy_guard', method: 'api_credentials', expect: { '': {} }, reject: true, nobatch: true });
const logsCall = rpc.declare({ object: 'proxy_guard', method: 'logs', expect: { '': {} }, reject: true, nobatch: true });
const applyCall = rpc.declare({ object: 'proxy_guard', method: 'apply', params:['confirm_flow'], expect: { '': {} }, reject: true });
const clearCall = rpc.declare({ object: 'proxy_guard', method: 'clear_logs', expect: { '': {} }, reject: true });
const preflightCall = rpc.declare({ object: 'proxy_guard', method: 'preflight', params: ['draft'], expect: { '': {} }, reject: true });
const testProxyCall = rpc.declare({ object: 'proxy_guard', method: 'test_proxy', params: ['draft'], expect: { '': {} }, reject: true, nobatch: true });
const runDiagnosticsCall = rpc.declare({ object: 'proxy_guard', method: 'run_diagnostics', expect: { '': {} }, reject: true, nobatch: true });
const blockLabels = {
    schedule: _("Scheduled protection active"), schedule_confirmation: _("Waiting for a check after the scheduled window"),
    api: _("Timed API block"), services: _("Waiting for proxy client services"),
    exit_mismatch: _("Exit IPv4 differs from the expected address"), exit_unavailable: _("Exit IPv4 could not be verified"),
    connectivity: _("Connectivity check failed"), udp: _("UDP proxy path check failed"), permit: _("Waiting for a new access permit")
};
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
const apiUuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
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
        if (f.phase === 'sensitive') return f.holding || (!monitor && s.enforcement !== 'allowing') ?
            (monitor ? _("Monitoring only; confirming proxy recovery") : _("Validating the proxy before restoring access")) :
            (monitor ? _("Monitoring only; observing proxy stability: ") : _("Internet restored; enhanced monitoring: ")) + Math.min(f.stable_elapsed, f.stable_required) + '/' + f.stable_required + _(" seconds");
    }
    // Kernel permits can expire before the next worker/watch snapshot is published.
    // Completed check results stay historical; current access text follows enforcement.
    if (!monitor && s.enforcement === 'blocked' && ['healthy','suspect'].includes(s.phase))
        return _("Waiting for the required successful proxy checks");
    return pgI18n.runtime(s.reason) || phases[s.phase] || _("Unknown state");
}

function exitResultText(exit, observed) {
    if (!exit || !exit.enabled)
        return observed ? observed + ' · ' + _("Exit IP verification is disabled") : _("Exit IP verification is disabled");
    const labels = {
        match: _("Passed"), mismatch: _("Exit IPv4 differs from the expected address"),
        timeout: _("Exit IPv4 lookup timed out"), unavailable: _("Exit IPv4 could not be verified"),
        skipped: _("Exit has not been checked")
    };
    const unavailable = {missing_ip: _("No exit IP address in the response"), invalid_ip: _("Invalid exit IP address in the response"),
        ipv6_only: _("Only IPv6 was returned")};
    const value = (exit.outcome === 'unavailable' && unavailable[exit.reason]) || labels[exit.outcome] || _("Exit has not been checked");
    const addresses = exit.observed ? _("; observed ") + exit.observed + _("; expected ") + exit.expected : '';
    const pending = exit.mismatch_pending && exit.outcome !== 'mismatch' ? ' · ' + _("Waiting for a matching exit IPv4") : '';
    return value + addresses + pending + (exit.via ? ' · ' + exit.via : '');
}

const recoveryReasons = {heartbeat_monitor:_("Official HTTPS monitor heartbeat expired"),main_heartbeat:_("Connectivity monitor heartbeat expired"),fast_heartbeat:_("Service monitor heartbeat expired"),
    execution_errors:_("Repeated plugin execution errors"),recovery_timeout:_("Previous restart did not complete"),configuration:_("Configuration requires attention")};
function checkResultText(s) {
    if (s.check_mode === 'public') {
        const h=s.heartbeat || {}, udp=s.udp_probe || {};
        const failed=h.last_ok === false || s.exit_check && s.exit_check.ok === false || udp.enabled && udp.ok === false;
        const passed=h.allowed === true && h.last_ok === true && (!udp.enabled || udp.ok === true);
        return (!h.checked_at ? _("No completed checks yet") : (failed ? _("Failed") : passed ? _("Passed") : _("Awaiting verification")) + ' · ' + formatTime(h.checked_at)) + (h.stale ? _(" · No recent update from the monitor") : '');
    }
    if (!s.last_probe_at) return _("No completed checks yet");
    return (s.last_probe_ok === false ? _("Failed") : s.last_probe_ok === true ? _("Passed") : _("Awaiting verification")) + ' · ' + formatTime(s.last_probe_at) + (s.stale ? _(" · No recent update from the monitor") : '');
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
    if (f.phase === 'sensitive' && (f.holding || s.enforcement !== 'allowing')) return _("Waiting for proxy verification before restoring access");
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

function apiRequestsText(status) {
    if (!status || status.stale || !status.api)
        return _("Awaiting verification");
    if (!status.api.enabled)
        return _("Disabled");
    const { count, remaining } = status.api;
    const requests = _("Active timed block requests: %s").replace('%s', count);
    return count > 0 ? requests + ' · ' + _("Up to %s seconds remaining").replace('%s', remaining) : requests;
}

return view.extend({
    load: function() {
        // A temporary status/log failure must not prevent rendering the page
        // and registering its automatic retries.
        return uci.load('proxy_guard');
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
            [E('strong', {style:'flex:0 0 15em;max-width:100%;'}, [label]), E('span', {style:'flex:1 1 16em;min-width:0;'}, [value])]);
        this.statusBox.className = 'alert-message ' + (fault ? 'danger' : waiting || s.enforcement === 'blocked' ? 'warning' : 'notice');
        const failures=s.failure_progress;
        const reasons=(s.block_reasons || []).map(code => Object.prototype.hasOwnProperty.call(blockLabels,code) ? blockLabels[code] : null).filter(Boolean);
        this.statusBox.replaceChildren(
            E('strong', {id:'pg-access-state'}, [fault ? _("Protection status needs verification") : waiting ? _("Waiting for LAN interface") : titles[s.enforcement] || _("Awaiting verification")]),
            row(_("Internet access"), waiting ? _("Interface not ready; protection coverage is unverified") : enforcement[s.enforcement] || _("Awaiting verification")),
            row(_("Latest connectivity check"), checkResultText(s)),
            ...(failures && failures.count > 0 && failures.threshold > 0 && !s.stale ? [
                row(_("Consecutive failed checks"), failures.count + ' / ' + failures.threshold)
            ] : []),
            ...(reasons.length && s.enforcement === 'blocked' ? [row(_("Active block reasons"), reasons.join(_("; ")))] : []),
            row(_("Current protection reason"), pgI18n.runtime(s.firewall_error) || activityText(s)),
            row(_("Access recovery"), recoveryText(s)),
            row(_("Proxy client"), clientText(s.client)),
            row(_("Proxy client services"), fastText(s.fast_watch) || _("Service monitoring is disabled")),
            row(_("Proxy client runtime log"), passwallLogText(s.fast_watch)),
            row(_("Schedule"), s.phase === 'disabled' ? _("Protection is disabled; schedules will not run") : scheduleText(s.schedule) +
                (s.schedule && s.schedule.enabled ? (s.mode === 'monitor' ? _(" · Monitor only; no blocking") : s.schedule.active ? _(" · Within the scheduled window") : '') : '')),
            row(_("Observed proxy exit"), exitResultText(s.exit_check, s.observed_exit4)),
            row(_("Local control API"), apiRequestsText(s)),
            ...(s.check_mode === 'public' ? [] : [row(_("HTTPS connectivity checks"), (s.probes || []).map(p => p.host + (p.via ? ' → ' + p.via : '') + _(": ") + (p.ok ? _("Success") : _("Failed")) + _(", ") + p.milliseconds + ' ms').join(_("; ")) || _("No completed checks yet"))]),
            row(_("UDP proxy path check"), s.udp_probe && s.udp_probe.enabled ? (s.udp_probe.ok ? _("Passed") : _("Failed")) + ' · ' + (s.udp_probe.milliseconds || 0) + ' ms' : _("UDP proxy path check is disabled")),
            row(_("Plugin self-check"), supervisionText(s.supervision)),
            row(_("Plugin resource usage"), s.supervision && s.supervision.resources ?
                _("Memory (RSS)") + ': ' + s.supervision.resources.rss_kib + ' KiB · ' + _("CPU (total)") + ': ' + (s.supervision.resources.cpu_percent == null || s.supervision.resources.cpu_basis !== 'all_online_cpus' ? _("Sampling") : s.supervision.resources.cpu_percent + '%') +
                ' · ' + _("Logical processors") + ': ' + (s.supervision.resources.cpu_cores || _("Unknown")) +
                ' · ' + _("Process count") + ': ' + s.supervision.resources.process_count + ' · ' + _("Logs in RAM") + ': ' + s.supervision.resources.log_bytes + ' B' : _("Resource statistics are disabled or awaiting the first sample")),
            row(_("Current recovery event"), incidentText(s.fast_watch && s.fast_watch.episode)),
            row(_("Last completed check"), formatTime(s.check_mode === 'public' && s.heartbeat ? s.heartbeat.checked_at : s.last_probe_at) + (s.stale ? _(" · No recent update from the monitor") : '')),
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
        const format = entries => entries.map(e => formatTime(e.time) + ' [' + e.level + '] ' + pgI18n.runtime(e.message) +
            (apiUuidPattern.test(e.api_uuid || '') ? ' · UUID ' + e.api_uuid : '')).join('\n') || _("No log entries");
        this.logBox.textContent = format(logs.entries);
        this.checkLogBox.textContent = format(logs.details || []);
        this.logWarning.textContent = logs.skipped ? _("Some damaged log entries were skipped: ") + logs.skipped : '';
    },

    refreshApiCredentials: function() {
        const field = this.apiUuidField;
        if (!field || this.apiCredentialsRequest) return this.apiCredentialsRequest;
        const hint = this.apiUuidHint;
        const unavailable = () => {
            field.value = '';
            hint.textContent = _("Cannot read the current API UUID");
        };
        this.apiCredentialsRequest = apiCredentialsCall().then(result => {
            if (!result.ok) return unavailable();
            field.value = apiUuidPattern.test(result.uuid || '') ? result.uuid : '';
            hint.textContent = field.value ? '' : result.enabled ?
                _("Waiting for the API UUID after settings are confirmed") : _("The API is disabled");
        }).catch(unavailable).finally(() => { this.apiCredentialsRequest = null; });
        return this.apiCredentialsRequest;
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

    readLogSnapshot: function() {
        if (this.logsRequest) return this.logsRequest;
        const request = readLogs().then(logs => {
            if (this.logsRequest === request) this.updateLogs(logs);
        }).catch(err => {
            if (this.logsRequest !== request) return;
            this.lastLogs = null;
            this.logBox.textContent = _("Cannot read plugin logs: ") + pgI18n.runtime(err.message);
            this.checkLogBox.textContent = '';
            this.incidentBox.textContent = '';
            this.logWarning.textContent = '';
        }).finally(() => {
            if (this.logsRequest === request) this.logsRequest = null;
        });
        this.logsRequest = request;
        return request;
    },

    refreshLogs: function() {
        return this.clearLogsRequest || this.readLogSnapshot();
    },

    clearLogs: function() {
        if (this.clearLogsRequest) return this.clearLogsRequest;
        this.clearLogsRequest = clearCall().then(result => {
            if (!result.ok) throw new Error(pgI18n.runtime(result.error) || _("Failed to clear logs"));
            // A read started before the clear can still return the old log.
            this.logsRequest = null;
            this.updateLogs({entries: []});
            return this.readLogSnapshot();
        }).catch(err => this.showActionError(err)).finally(() => { this.clearLogsRequest = null; });
        return this.clearLogsRequest;
    },

    refresh: function() {
        return Promise.all([this.refreshStatus(), this.refreshLogs()]);
    },

    currentDraft: function() {
        const draft = Object.assign({}, uci.get ? uci.get('proxy_guard', 'main') : {}, this.extraDraft || {});
        this.formSection.children.forEach(option => {
            const value = option.formvalue('main');
            if (value != null) draft[option.option] = value;
        });
        return draft;
    },

    diagnosticResult: function(id, message) {
        return E('pre', {id, role:'status', dir:'auto',
            style:'max-height:50vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;'}, message ? [message] : []);
    },

    showDiagnosticModal: function(title, children) {
        pgI18n.modal(ui, title, [E('style', {}, [
            '.pg-guard .pg-diagnostic-raw[hidden]{display:none}'
        ]), ...children].concat(
            E('button', {type:'button', class:'cbi-button cbi-button-neutral', click:ui.hideModal}, [_("Close")])
        ));
    },

    testProxy: function() {
        if (this.testProxyRequest) return this.testProxyRequest;
        const draft = JSON.stringify(this.currentDraft());
        const box = this.diagnosticResult('pg-test-proxy', _("Testing the proxy with the current settings..."));
        const detail = this.diagnosticResult('pg-run-diagnostics');
        detail.dir = 'ltr';
        detail.hidden = true;
        detail.classList.add('pg-diagnostic-raw');
        const run = E('button', {type:'button', class:'cbi-button cbi-button-action important',
            'aria-controls':'pg-run-diagnostics',
            click:ui.createHandlerFn(this, () => this.runDiagnostics(detail))}, [_("Run detailed diagnostics")]);
        this.showDiagnosticModal(_("Test current proxy"), [
            E('p', {}, [_("Tests the current form through SOCKS. Apply the settings separately to change protection.")]),
            box,
            E('p', {class:'cbi-value-description'}, [_("Detailed diagnostics use the applied proxy settings.")]),
            run, detail
        ]);
        const errors={busy:_("A proxy test is already running"), invalid_draft:_("Check the connection settings and try again")};
        this.testProxyRequest=testProxyCall(draft).then(result => {
            if (!result.ok) {
                box.textContent=(errors[result.error] || _("The proxy test could not run")) + (result.detail ? ' · ' + pgI18n.runtime(result.detail) : '');
                return;
            }
            const lines=[(result.connectivity_ok ? _("Proxy connectivity passed") : _("Proxy connectivity failed")) + ' · ' + result.milliseconds + ' ms'];
            for (const check of result.checks || []) {
                lines.push(check.host + ' · ' + (check.ok ? _("Passed") : _("Failed")) + ' · HTTP ' + check.http_code + ' · curl ' + check.curl_code + ' · ' + check.milliseconds + ' ms');
            }
            if (result.exit_check && result.exit_check.enabled || result.observed_exit4) {
                lines.push(_("Observed proxy exit") + ' · ' + exitResultText(result.exit_check,result.observed_exit4));
            }
            if (!result.complete) lines.push(_("The test time limit was reached before all checks finished"));
            box.textContent=lines.join('\n');
        }).catch(() => { box.textContent=_("The proxy test could not run"); })
            .finally(() => { this.testProxyRequest=null; });
        return this.testProxyRequest;
    },

    runDiagnostics: function(box) {
        box.hidden = false;
        box.textContent = _("Running detailed diagnostics...");
        if (!this.diagnosticRequest) {
            this.diagnosticRequest = runDiagnosticsCall().finally(() => {
                this.diagnosticRequest = null;
            });
        }
        return this.diagnosticRequest.then(result => {
            if (!result.ok || !result.diagnostics) {
                box.textContent = result.error === 'busy' ?
                    _("A diagnostic request is already running") : _("The detailed diagnostic could not run");
                return;
            }
            const diagnostic = result.diagnostics;
            const lines = [diagnostic.ok ? _("Passed") : _("Failed")];
            const reason = {
                http_status: _("Unexpected HTTP status"),
                transport_error: _("Could not reach the heartbeat endpoint through the proxy"),
                invalid_headers: _("Invalid heartbeat response headers"),
                invalid_status: _("Unexpected HTTP status"),
                duplicate_security_header: _("Duplicate heartbeat validation header"),
                body_mismatch: _("Unexpected heartbeat response body"),
                nonce_mismatch: _("Heartbeat verification token does not match")
            };
            if (diagnostic.reason) lines.push(reason[diagnostic.reason] || diagnostic.reason);
            if (diagnostic.http_code) lines.push('HTTP ' + diagnostic.http_code);
            if (Number.isFinite(diagnostic.milliseconds)) lines.push(diagnostic.milliseconds + ' ms');
            const headers = Array.isArray(diagnostic.headers) ? diagnostic.headers.map(header =>
                header.name + ': ' + header.value + (header.encoding === 'base64' ? ' [Base64]' : '')) : [];
            box.textContent = lines.join(' · ') + (headers.length ? '\n\n' + headers.join('\n') : '');
        }).catch(() => {
            box.textContent = _("The detailed diagnostic could not run");
        });
    },

    preflight: function() {
        const draft = JSON.stringify(this.currentDraft());
        const box = this.diagnosticResult('pg-preflight',
            _("Checking unsaved settings without saving or probing the Internet..."));
        this.showDiagnosticModal(_("Check settings and runtime environment"), [box]);
        return preflightCall(draft).then(result => {
            const labels = {configured_offload:_("Configured flow offloading"),running_offload:_("Active kernel flowtables"),bridge_filtering:_("Bridge filtering"),kernel_features:_("Required nftables kernel features"),client_mode:_("Proxy client forwarding mode"),homeproxy_tun_ipv6_udp:_("HomeProxy TUN IPv6 UDP compatibility"),configuration:_("Configuration format"),interfaces:_("Ingress devices"),compatibility:_("Firewall compatibility"),
                socks_listener:_("Local SOCKS listener"),udp_runtime:_("UDP check support library"),passwall_services:_("Proxy client services"),
                ipv6_scope:_("IPv6 covers all sources on the selected devices"),schedule_clock:_("System clock"),
                topology:_("Traffic bypassing this router cannot be protected; validate the actual topology")};
            const levels = {ok:_("Passed"),warning:_("Please verify"),error:_("Needs attention"),off:_("Disabled")};
            box.textContent = (result.checks || []).map(row => (labels[row.code] || _("Unknown state")) + ': ' + (levels[row.level] || _("Unknown state")) + (row.detail ? ' · ' + pgI18n.runtime(row.detail) : '')).join('\n') +
                (result.error ? '\n' + pgI18n.runtime(result.error) : '') + '\n' + _("Read-only check: settings have not been saved or applied, and proxy Internet connectivity has not been tested.");
        }).catch(err => { box.textContent = pgI18n.runtime(err.message) || _("Cannot complete self-check"); });
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
        this.showDiagnosticModal(_("Local diagnostic report"), [
            E('p',{},[_("This report contains only state names and measurements. It excludes IP addresses, URLs, configuration and raw logs. Review it before sharing. Nothing is uploaded.")]),
            E('pre',{style:'max-height:50vh;overflow:auto;white-space:pre-wrap;'},[text]),
            E('button',{type:'button',class:'cbi-button cbi-button-action',click:download},[_("Download report")])
        ]);
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
        s.tab('connection', _("Connection checks"));
        s.tab('schedule', _("Scheduled protection"));
        s.tab('fast', _("Failure protection and recovery"));
        s.tab('health', _("Plugin health, logs and recovery"));
        s.tab('api', _("Local control API"));
        let o = s.taboption('general', form.Flag, 'enabled', _("Enable protection"));
        o.rmempty = false;
        o = s.taboption('general', form.ListValue, 'mode', _("Operating mode"));
        o.value('monitor', _("Monitor only: log failures without blocking"));
        o.value('guard', _("Protect: block Internet traffic in both directions on failure"));
        o.default = 'monitor'; o.rmempty = false;
        o = s.taboption('general', form.Value, 'socks_port', _("Local SOCKS port"), _("Checks always use the SOCKS5 proxy on 127.0.0.1, with no direct fallback."));
        o.datatype = 'port'; o.default = '1070'; o.rmempty = false;
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
        o = s.taboption('connection', form.ListValue, 'check_mode', _("Connection check method"),
            _("Choose a connection check method. Both methods use the local SOCKS proxy. Changes take effect after Save & Apply."));
        o.value('public', _("Official HTTPS"));
        o.value('web', _("Third-party HTTPS"));
        o.default='public'; o.rmempty=false;

        const heading = (name, title, method) => {
            const option = s.taboption('connection', form.DummyValue, name);
            option.renderWidget = () => E('h4', {class:'pg-detection-heading'}, [title]);
            option.parse = () => Promise.resolve();
            if (method) option.depends('check_mode',method);
        };
        const numbers = (tab, fields, dependencies) => {
            for (const [key, label, value, min, max] of fields) {
                const option = s.taboption(tab, form.Value, key, label);
                option.default=value; option.datatype='and(uinteger,range('+min+','+max+'))';
                option.rmempty=false; option.retain=true;
                if (dependencies) option.depends(dependencies);
            }
        };

        heading('_official_https', _("Official HTTPS settings"), 'public');
        numbers('connection', [
            ['public_hb_interval', _("Interval after each HTTPS check (seconds)"), '3', 1, 300],
            ['public_hb_timeout', _("Timeout per HTTPS request (seconds)"), '2', 1, 15],
            ['public_hb_fail', _("Consecutive failures to confirm an outage"), '2', 1, 10],
            ['public_hb_recover', _("Consecutive successes to confirm recovery"), '2', 1, 10],
            ['public_hb_sensitive_interval', _("Interval during enhanced monitoring (seconds)"), '1', 1, 5]
        ], {check_mode:'public'});

        heading('_third_party_https', _("Third-party HTTPS settings"), 'web');
        o = s.taboption('connection', form.DynamicList, 'targets', _("HTTPS check targets"),
            _("Configure 2–4 targets as https://domain/path|expected_status. Connections use the proxy. This does not test the health of every UDP service."));
        o.default=['https://www.gstatic.com/generate_204|204','https://connectivity-check.ubuntu.com/|204'];
        o.rmempty=false; o.retain=true; o.depends('check_mode','web');
        numbers('connection', [
            ['interval', _("Interval after each check round (seconds)"), '10', 5, 300],
            ['timeout', _("Timeout per target (seconds)"), '4', 1, 15],
            ['min_success', _("Minimum successful targets per round"), '1', 1, 4],
            ['fail_threshold', _("Consecutive failed rounds"), '3', 1, 10],
            ['recover_threshold', _("Consecutive successful rounds for recovery"), '2', 1, 10],
            ['web_sensitive_interval', _("Interval during enhanced monitoring (seconds)"), '1', 1, 5]
        ], {check_mode:'web'});

        heading('_exit_ipv4', _("Exit IPv4 verification"));
        o = s.taboption('connection', form.Flag, 'exit_check', _("Verify proxy exit IPv4"),
            _("Optional. When off, connectivity checks continue without requiring or comparing an expected exit address."));
        o.default='0'; o.rmempty=false;
        o = s.taboption('connection', form.Value, 'expected_exit4', _("Expected proxy exit IPv4"));
        o.datatype='ip4addr("nomask")'; o.rmempty=false; o.retain=true; o.depends('exit_check','1');
        o = s.taboption('connection', form.ListValue, 'exit_provider', _("Exit IP response source"),
            _("Official HTTPS uses the IPv4 reported by the official service. Enter the expected IPv4 to compare against it. No URL is required."));
        o.value('public', _("Official HTTPS")); o.value('text', _("Third-party HTTPS"));
        o.default='public'; o.rmempty=false; o.retain=true; o.depends('exit_check','1');
        o = s.taboption('connection', form.Value, 'exit_url', _("Exit verification HTTPS URL"));
        o.default='https://api.ipify.org/'; o.rmempty=false; o.retain=true;
        o.depends({exit_check:'1',exit_provider:'text'});
        o = s.taboption('connection', form.Value, 'exit_fallback_url', _("Backup HTTPS URL for exit verification"),
            _("Queried through the same SOCKS proxy only if the primary URL times out. Leave blank to use https://4.ident.me/ when the primary host is api.ipify.org. With a different primary host, leaving this blank disables the backup."));
        o.placeholder='https://4.ident.me/'; o.rmempty=true; o.retain=true;
        o.depends({exit_check:'1',exit_provider:'text'});

        o = s.taboption('fast', form.Value, 'startup_grace', _("Startup grace deadline (seconds since boot)"),
            _("Boot protection replaces this fixed startup grace period."));
        o.default='150'; o.datatype='range(0,600)'; o.rmempty=false;
        o = s.taboption('fast', form.Flag, 'udp_check', _("Verify UDP through the proxy"),
            _("Optional check: send a DNS-format UDP request through local SOCKS5 UDP ASSOCIATE. Requires luci-lib-nixio and a proxy with UDP support; never falls back to a direct connection. Failure counts as a failed check round. The result covers only this target, not every UDP service."));
        o.default='0';o.rmempty=false;
        [['udp_server',_("UDP check target IPv4"),'','ip4addr("nomask")'],
         ['udp_port',_("UDP check target port"),'53','port'],['udp_query',_("UDP query domain"),'example.com','hostname'],
         ['udp_timeout',_("UDP check timeout (seconds)"),'3','range(1,10)']].forEach(item => {
            const option=s.taboption('fast',form.Value,item[0],item[1]);option.depends('udp_check','1');option.retain=true;
            option.default=item[2];option.datatype=item[3];option.rmempty=false;
        });
        o=s.taboption('api',form.Flag,'api_enabled',_("Enable local control API"),
            _("Disabled by default. Save and Apply enables the API and generates a UUID. Authenticated API requests show the UUID in the event log. Turning the API off and on generates a new UUID."));
        o.default='0';o.rmempty=false;
        o=s.taboption('api',form.DummyValue,'_api_uuid',_("API UUID"),
            _("Send this UUID in the Authorization header. It grants access to the local API."));
        o.depends('api_enabled','1');
        o.renderWidget = () => {
            const field = E('input', {id:'pg-api-uuid', type:'text', class:'cbi-input-text',
                readonly:'readonly', dir:'ltr', autocomplete:'off',
                'aria-label':_("API UUID"), style:'width:100%;max-width:26em;'});
            const hint = E('span', {id:'pg-api-uuid-status', role:'status', class:'cbi-value-description'});
            this.apiUuidField = field;
            this.apiUuidHint = hint;
            const copy = E('button', {type:'button', class:'cbi-button cbi-button-neutral',
                click:ui.createHandlerFn(this, async () => {
                    if (!field.value) return;
                    if (navigator.clipboard) await navigator.clipboard.writeText(field.value);
                    else { field.focus(); field.select(); document.execCommand('copy'); }
                })}, [_("Copy UUID")]);
            return E('div', {}, [field, ' ', copy, hint]);
        };
        o.parse = () => Promise.resolve();
        numbers('api', [
            ['api_default_seconds', _("Default API block duration (seconds)"), '300', 1, 86400],
            ['api_max_seconds', _("Maximum API block duration (seconds)"), '3600', 1, 86400]
        ], {api_enabled:'1'});
        const defaultDuration = s.getOption('api_default_seconds');
        const maximumDuration = s.getOption('api_max_seconds');
        defaultDuration.validate = (section, value) => {
            const maximum = Number(maximumDuration.formvalue(section));
            return !Number.isInteger(maximum) || maximum < 1 || maximum > 86400 ||
                Number(value) <= maximum || _("Default API block duration must not exceed the maximum.");
        };
        o = s.taboption('api', form.ListValue, 'diagnostics_enabled', _("API refresh endpoint"),
            _("The diagnostics endpoint returns this heartbeat response in the same request."));
        const heartbeatOrigin = 'https://hb.pghb.app';
        const apiEndpointLabel = (label, path) => label.replace('%s', '\u2066' + heartbeatOrigin + path + '\u2069');
        o.value('0', apiEndpointLabel(_("Standard heartbeat (%s)"), '/'));
        o.value('1', apiEndpointLabel(_("Detailed diagnostics (%s)"), '/f'));
        o.default='0'; o.rmempty=false; o.retain=true; o.depends('api_enabled','1');
        o = s.taboption('api', form.DummyValue, '_api_advanced');
        o.renderWidget = () => E('details', {id:'pg-api-advanced'}, [
            E('summary', {}, [_("Advanced diagnostics")])
        ]);
        o.parse = () => Promise.resolve();
        o.depends('api_enabled','1');
        numbers('api', [
            ['diagnostics_interval', _("Minimum time between diagnostic requests (seconds)"), '60', 10, 3600],
            ['diagnostics_ttl', _("Diagnostic freshness limit (seconds)"), '300', 30, 3600]
        ], {api_enabled:'1'});
        const renderOptions = s.renderOptions;
        s.renderOptions = function(tab, section) {
            const options = renderOptions.call(this, tab, section);
            if (tab !== 'api') return options;
            return options.then(rows => {
                const details = rows.querySelector('#pg-api-advanced');
                const fields = rows.querySelectorAll('[data-name="diagnostics_interval"], [data-name="diagnostics_ttl"]');
                for (const field of fields) details.appendChild(field);
                return rows;
            });
        };
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
        numbers('health', [['log_kib', _("Maximum size per log file (KiB)"), '64', 16, 512]]);
        o = s.taboption('health', form.Flag, 'debug', _("Detailed check logs"), _("Changing only logging options does not restart checks or reset permits. Logs are stored in memory, cleared on reboot, and also sent to the system log."));
        o.rmempty = false;

        this.map = m;
        this.formSection = s;
        this.statusBox = E('div', { id: 'proxy-guard-status', class: 'alert-message notice', role: 'status', 'aria-live': 'polite' }, [_("Awaiting verification")]);
        this.logBox = E('pre', { style: 'max-height:22em;overflow:auto;white-space:pre-wrap;' });
        this.checkLogBox = E('pre', { style: 'max-height:16em;overflow:auto;white-space:pre-wrap;' });
        this.logWarning = E('p', {role:'status'});
        this.incidentBox=E('pre',{id:'pg-incidents',style:'max-height:12em;overflow:auto;white-space:pre-wrap;'});
        this.statusUpdatedAt = performance.now();
        // Keep the heading/status outside the rerendered form so Save does
        // not remove the status node. Editing fields has no service action.
        return m.render().then(node => {
            this.refresh();
            poll.add(() => { this.refreshStatus(); }, 1);
            poll.add(() => { this.refreshLogs(); this.refreshApiCredentials(); }, 5);
            setTimeout(() => this.refreshApiCredentials(), 0);
            this.savedFormSnapshot = this.formSnapshot();
            this.updateDraftIndicator();
            setTimeout(()=>pgSetup.attach(this),0);
            ['input', 'change', 'widget-change'].forEach(event =>
                node.addEventListener(event, () => this.updateDraftIndicator()));
            return pgI18n.decorate(E('div', {}, [
                E('style', {}, [
                    '.pg-guard[dir=rtl] .cbi-value{display:flex;flex-wrap:wrap;gap:.4em}' +
                    '.pg-guard[dir=rtl] .cbi-value.hidden{display:none}' +
                    '.pg-guard[dir=rtl] .cbi-value-title{float:none;text-align:start;flex:0 0 12em}' +
                    '.pg-guard[dir=rtl] .cbi-value-field{margin:0;flex:1;min-width:min(14em,100%)}' +
                    '.pg-guard .pg-status-row span{unicode-bidi:plaintext}' +
                    '.pg-guard[dir=rtl] .pg-status-row span{text-align:right}' +
                    '.pg-guard [data-name="mode"] .cbi-value-field select,.pg-guard [data-tab="connection"] .cbi-value-field select,.pg-guard [data-tab="api"] .cbi-value-field select{width:auto;min-width:min(15em,100%);max-width:100%}' +
                    '.pg-guard .pg-detection-heading{background:rgba(127,127,127,.12);border-radius:.35em;padding:.55em .8em;margin:.75em 0 .15em;font-size:1em}' +
                    '.pg-guard .pg-tools-row{display:flex;flex-wrap:nowrap;align-items:stretch;gap:.45em;max-width:100%;overflow-x:auto;padding:.2em .1em .4em}' +
                    '.pg-guard .pg-tools-row .cbi-button{flex:1 0 8em;min-width:0;box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;margin:0;padding:.3em .55em;white-space:normal;word-break:normal;overflow-wrap:anywhere;text-align:center;line-height:1.3}' +
                    '.pg-guard .pg-tools-row .cbi-button{color:#1f1f1f;background:#f0f0f0;border:1px solid transparent;border-radius:6px;box-shadow:none;text-shadow:none}' +
                    '.pg-guard .pg-tools-row .cbi-button:not([disabled]):hover{color:#1f1f1f;background:#e4e4e4;text-decoration:none}' +
                    '.pg-guard .pg-tools-row .cbi-button:focus-visible{outline:2px solid #125ab1;outline-offset:-3px}' +
                    '.pg-guard summary{cursor:pointer}' +
                    '.pg-guard .pg-log-actions{margin-block:.9em}' +
                    '@media(max-width:600px){.pg-guard[dir=rtl] .cbi-value-title{flex-basis:100%}}'
                ]),
                E('h2', {}, [_("Proxy Guard")]), this.statusBox,
                E('div', { class: 'cbi-map-descr' }, [
                    _("On proxy failure, block Internet traffic in both directions for selected devices where traffic actually passes through this router or proxy. LAN access remains available. Return traffic bypassing this device cannot be blocked. Disabled on first install; start with monitoring, then test one device.")
                ]),
                node,
                E('section', {id:'pg-tools', class:'cbi-section'}, [
                    E('h3', {}, [_("Configuration and diagnostics")]),
                    E('div', {class:'pg-tools-row', role:'group', 'aria-label':_("Configuration and diagnostics"), tabindex:'0'}, [
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', click:()=>pgSetup.open(false)}, [_("Run setup wizard")]),
                        E('a', {class:'cbi-button cbi-button-neutral', href:'proxy-guard-raw'}, [_("Raw UCI configuration")]),
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', click:()=>pgSetup.restorePrevious()}, [_("Load previous confirmed settings")]),
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', click:()=>pgI18n.modal(ui,_("Restore defaults and set up again"),[
                            E('p', {}, [_("This prepares default plugin settings for review. Existing protection continues until you Save & Apply.")]),
                            E('button', {type:'button', class:'cbi-button', click:ui.hideModal}, [_("Cancel")]), ' ',
                            E('button', {type:'button', class:'cbi-button cbi-button-action', click:()=>pgSetup.open(true)}, [_("Continue")])
                        ])}, [_("Restore defaults and set up again")]),
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', 'aria-haspopup':'dialog',
                            click:ui.createHandlerFn(this,this.preflight)}, [_("Check settings and runtime environment")]),
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', 'aria-haspopup':'dialog',
                            click:ui.createHandlerFn(this,this.testProxy)}, [_("Test current proxy")]),
                        E('button', {type:'button', class:'cbi-button cbi-button-neutral', 'aria-haspopup':'dialog',
                            click:ui.createHandlerFn(this,this.showDiagnostics)}, [_("View sanitized diagnostic report")])
                    ])
                ]),
                E('h3', {}, [_("Event log")]),
                E('p', {}, [_("Protection events stay here. Frequent website checks are listed separately below.")]),
                this.logWarning, this.logBox,
                E('details', {id:'pg-check-details'}, [E('summary', {}, [_("Recent connectivity check details")]), this.checkLogBox]),
                E('details', {id:'pg-recovery-history'}, [E('summary', {}, [_("Recovery history")]), this.incidentBox]),
                E('div', {class:'pg-log-actions'}, [
                    E('button', {type:'button', class:'cbi-button cbi-button-neutral', click:ui.createHandlerFn(this,this.clearLogs)}, [_("Clear logs and recovery history")]),
                    E('p', {}, [_("Clears plugin events, connection check details and recovery history.")])
                ])
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
            return Promise.all([this.refresh(), this.refreshApiCredentials(), ui.changes.init()]);
        }).catch(err => this.showActionError(err));
    }
});
