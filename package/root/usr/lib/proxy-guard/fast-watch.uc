// Independent of the slow probe lock: process exits must be noticed while
// curl is still waiting. This worker can only renew its own short-lived gate.
import { open, readfile, glob, rename, unlink } from 'fs';
import { step } from './fast-state.uc';
import { poll as poll_log } from './passwall-log.uc';
import { services } from './services.uc';

let run = '/var/run/proxy-guard';
function read_json(path) {
    try { return json(readfile(path) || ''); } catch (e) { return null; }
}
function write(path, value) {
    let f = open(path + '.new', 'w', 0o600);
    if (!f) die('Cannot write fast protection state');
    f.write(value); f.close();
    if (!rename(path + '.new', path)) die('Cannot publish fast protection state');
}
function event(s, c) {
    if (!s.notice) return;
    let messages = {
        boot_wait: '开机保护等待代理客户端已配置的服务运行',
        boot_ready: '代理客户端已配置的服务均已运行，开始开机保护等待',
        blocked: s.cause == 'services' ? '代理客户端的必需服务中断或重启，已触发快速保护' :
            s.cause == 'log' ? '代理客户端日志显示服务或规则正在变更，已阻断并等待恢复' :
            s.cause == 'watchdog' ? '快速检查进程曾中断，重新确认稳定状态' :
            s.cause == 'worker' ? '网络检测状态已过期，重新等待并确认稳定状态' : '检测到服务或代理中断，重新等待并确认稳定状态',
        sensitive: '快速保护等待结束，开始敏感检测',
        log_ready: '代理客户端本轮运行完成且已配置服务正常，直接验证恢复，不叠加故障等待',
        restored: '代理验证通过，已放行并进入敏感观察',
        schedule_sensitive: '定时保护结束，已放行并进入敏感观察，不执行故障等待',
        normal: '快速保护观察结束，已恢复日常检测频率'
    };
    let message = messages[s.notice];
    let source = s.notice == 'blocked' && s.cause == 'log' && s.log_watch;
    let labels = {restart:'收到服务重启请求',rules_removed:'代理规则已删除',
        sets_cleared:'规则集合已清空',stopped:'代理程序已停止',rules_loading:'正在加载代理规则',
        start_failed:'代理启动失败',gap:'日志记录存在读取缺口'};
    if (source && labels[source.trigger_event]) {
        message += '：' + labels[source.trigger_event];
        if (source.trigger_time != null) {
            let d = localtime(source.trigger_time);
            message += sprintf(' [%04d-%02d-%02d %02d:%02d:%02d]',d.year,d.mon,d.mday,d.hour,d.min,d.sec);
        }
    }
    if (c.mode == 'monitor') message += '（仅监测，未阻断）';
    let path = run + '/fast-events.jsonl';
    if (length(readfile(path) || '') > c.log_kib * 1024) rename(path, path + '.1');
    let f = open(path, 'a', 0o600);
    if (!f) die('Cannot append fast protection event');
    let level = s.notice == 'blocked' && c.mode == 'guard' ? 'error' : 'info';
    f.write(sprintf('%J\n', { time: time(), level, event: 'fast_' + s.notice, message,
        incident:s.episode,stage:s.notice,
        passwall_event: source && source.trigger_event, passwall_time: source && source.trigger_time }));
    f.close();
    system(['logger', '-t', 'proxy-guard', '-p', level == 'error' ? 'daemon.err' : 'daemon.notice', '--', message]);
}

let lock = open('/var/lock/proxy-guard-fast.lock', 'a', 0o600);
if (!lock) die('Cannot open fast protection lock');
let firewall_lock = open('/var/run/fw4.lock', 'a', 0o600);
if (!firewall_lock) die('Cannot open system firewall lock');
let state = read_json(run + '/fast.json');
let log_cursor = state && state.log_cursor;
let boot_id = trim(readfile('/proc/sys/kernel/random/boot_id') || '');
let generation = trim(readfile('/proc/sys/kernel/random/uuid') || '');
if (!length(generation)) die('Cannot identify fast protection generation');
let cleared = false;
while (readfile(run + '/removing') == null) {
    if (!lock.lock('xn')) { sleep(100); continue; }
    let snapshot = read_json(run + '/status.json');
    let c = snapshot && snapshot.fast_config;
    let up = clock(true)[0];
    if (!c || !c.enabled || !snapshot.enabled) {
        state = null; cleared = false;
        log_cursor = null;
        unlink(run + '/fast.json'); unlink(run + '/fast-poll');
    }
    else {
        c.stamp = snapshot.config_stamp;
        let observed = c.services_watch == false ? {tcp:true,udp:true,dns:true,identities:{}} : services(c.dns_mode,c.client_profile);
        observed.remote_ok = !snapshot.remote_health || !snapshot.remote_health.required || snapshot.remote_health.ok == true;
        observed.manual_block = snapshot.maintenance && snapshot.maintenance.active == true;
        if (c.log_watch) {
            if (!log_cursor || up - log_cursor.checked_uptime >= c.log_interval)
                log_cursor = poll_log(log_cursor, time(), up, boot_id, c.client_profile && c.client_profile.log_path, c.client_profile && c.client_profile.client);
            observed.log = log_cursor;
        }
        else log_cursor = null;
        observed.wall = time();
        observed.generation = generation;
        observed.up = up;
        observed.probe = snapshot.last_probe || 0;
        observed.probe_started = snapshot.probe_started || 0;
        observed.probe_ok = snapshot.last_probe_ok == true;
        observed.network_blocked = snapshot.phase == 'blocked';
        observed.network_healthy = snapshot.phase == 'healthy';
        observed.schedule_release = snapshot.schedule_release || 0;
        let stale = readfile(run + '/recovery-hold.json') != null || snapshot.updated_uptime == null || up - snapshot.updated_uptime > c.probe_freshness;
        observed.stale = stale;
        state = step(c, state, observed);
        state.log_cursor = log_cursor;
        state.log_watch = {enabled:c.log_watch == true, available:log_cursor && log_cursor.available == true,
            pending:log_cursor && log_cursor.pending == true, event:log_cursor && log_cursor.kind,
            event_time:log_cursor && log_cursor.event_time, observed_at:log_cursor && log_cursor.observed_at,
            trigger_event:log_cursor && log_cursor.trigger_kind,trigger_time:log_cursor && log_cursor.trigger_time,
            checked_at:log_cursor && log_cursor.checked_at, clock_error:log_cursor && log_cursor.clock_error == true,
            interval:c.log_interval};
        if (stale) state.holding = true;
        let allow = !state.holding;
        state.gate_ok = true;
        if (c.mode == 'guard' && c.services_watch != false && (allow || !cleared)) {
            // A configuration change may replace the gate before the slow
            // worker publishes its next snapshot. Never renew a different
            // policy using the old snapshot, and do not race fw4 reload.
            // Nonblocking: a busy firewall must not delay service monitoring.
            state.gate_ok = false;
            if (firewall_lock.lock('xn')) {
                let policy = read_json(run + '/firewall.json');
                if (policy && policy.stamp == c.stamp) {
                    let script = 'flush set inet proxy_guard service_ifaces\n';
                    if (allow) {
                        let names = [];
                        for (let name in c.interfaces) push(names, sprintf('"%s" timeout 4s', name));
                        script += 'add element inet proxy_guard service_ifaces { ' + join(', ', names) + ' }\n';
                    }
                    write(run + '/fast-transaction.nft', script);
                    state.gate_ok = system(['nft', '-f', run + '/fast-transaction.nft']) == 0;
                    unlink(run + '/fast-transaction.nft');
                }
                firewall_lock.lock('u');
            }
            cleared = !allow && state.gate_ok;
        }
        else if (c.mode != 'guard' || c.services_watch == false) cleared = false;
        event(state, c);
        write(run + '/fast.json', sprintf('%J\n', state));
        if (state.phase != 'normal' || (snapshot.schedule && snapshot.schedule.active)) { if (readfile(run + '/fast-poll') == null) write(run + '/fast-poll', '1\n'); }
        else unlink(run + '/fast-poll');
    }
    lock.lock('u');
    sleep(1000);
}
