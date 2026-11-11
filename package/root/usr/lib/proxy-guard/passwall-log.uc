// Read only the selected client lifecycle journal. Never execute or echo log contents.
// Exact message identifiers are generated from pinned upstream lifecycle calls
// and all their available PO catalogs; see tests/passwall_log_corpus.json.
// Additional client signatures are pinned to their audited upstream init scripts.
import { open, lstat, stat } from 'fs';

const messages = {
    "Clear IPSet.": "sets_cleared",
    "Clear NFTSet.": "sets_cleared",
    "Clearing and closing related programs and cache complete.": "stopped",
    "DNS 启动失败，停止服务。": "start_failed",
    "Delete iptables rules is complete.": "rules_removed",
    "Delete nftables rules is complete.": "rules_removed",
    "Failed or timed out waiting for subscription/rule updates. Restart cancelled.": "cancelled",
    "Restart the service and apply the new rules.": "restart",
    "Running complete!": "complete",
    "Starting to load iptables firewall rules...": "rules_loading",
    "Starting to load nftables firewall rules...": "rules_loading",
    "Выполнение завершено!": "complete",
    "Начало загрузки правил фаервола iptables...": "rules_loading",
    "Начало загрузки правил фаервола nftables...": "rules_loading",
    "Очистка IPSet.": "sets_cleared",
    "Очистка NFTSet.": "sets_cleared",
    "Очистка и завершение связанных процессов и кэша завершена.": "stopped",
    "Ошибка или превышено время ожидания обновления подписок/правил. Перезапуск отменён.": "cancelled",
    "Перезапуск службы для применения новых правил.": "restart",
    "Удаление правил iptables завершено.": "rules_removed",
    "Удаление правил nftables завершено.": "rules_removed",
    "اجرا کامل شد!": "complete",
    "انتظار برای به‌روزرسانی اشتراک/قوانین ناموفق بود یا مهلت آن به پایان رسید. راه‌اندازی مجدد لغو شد.": "cancelled",
    "حذف قوانین iptables کامل شد.": "rules_removed",
    "حذف قوانین nftables کامل شد.": "rules_removed",
    "راه‌اندازی مجدد سرویس و اعمال قوانین جدید.": "restart",
    "شروع بارگذاری قوانین فایروال iptables...": "rules_loading",
    "شروع بارگذاری قوانین فایروال nftables...": "rules_loading",
    "پاک کردن IPSet.": "sets_cleared",
    "پاک کردن NFTSet.": "sets_cleared",
    "پاک‌سازی و بستن برنامه‌های مرتبط و کش کامل شد.": "stopped",
    "全局节点启动失败，停止服务。": "start_failed",
    "删除 iptables 规则完成。": "rules_removed",
    "删除 nftables 规则完成。": "rules_removed",
    "刪除 iptables 規則完成。": "rules_removed",
    "刪除 nftables 規則完成。": "rules_removed",
    "开始加载 iptables 防火墙规则...": "rules_loading",
    "开始加载 nftables 防火墙规则...": "rules_loading",
    "清空 IPSet。": "sets_cleared",
    "清空 NFTSet。": "sets_cleared",
    "清空並關閉相關程序和缓存完成。": "stopped",
    "清空并关闭相关程序和缓存完成。": "stopped",
    "清除 IPSet。": "sets_cleared",
    "清除 NFTSet。": "sets_cleared",
    "等待訂閱/規則更新失敗或逾時，已取消重新啟動。": "cancelled",
    "等待订阅/规则更新失败或超时，已取消重启。": "cancelled",
    "等待订阅/规则更新结束失败或超时，取消重启.": "cancelled",
    "运行完成!": "complete",
    "运行完成！": "complete",
    "運行完成！": "complete",
    "重启服务，应用新的规则。": "restart",
    "重啟服務，應用新的規則。": "restart",
    "開始加载 iptables 防火墙規則...": "rules_loading",
    "開始加载 nftables 防火墙規則...": "rules_loading",
    "防火墙规则加载完成！": "rules_ready"
};
const catalog_id = '9946bb04ed02c3ed';

const client_messages = {
    openclash: {
        'OpenClash Restart...':'restart','OpenClash Start Running...':'restart',
        'OpenClash Stoping...':'stopped','Step 2: Delete OpenClash Firewall Rules...':'rules_removed',
        'Step 3: Close The OpenClash Services...':'stopped','OpenClash Already Stop!':'stopped',
        'Step 6: Core Status Checking and Firewall Rules Setting...':'rules_loading',
        'Manually Reload Firewall Rules...':'rules_loading',
        'OpenClash Start Successful!':'complete','Firewall Reload Successful!':'complete',
        'Core Start Failed, Please Check The Log Infos!':'start_failed',
        'Core Initial Configuration Timeout, Please Check The Log Infos!':'start_failed',
        'TUN Interface Start Failed, Please Check The Dependence or Try to Restart Again!':'start_failed',
        'Config Not Found':'start_failed','Config File Format Validation Failed...':'start_failed'
    },
    nikki: {
        '[App] Start.':'restart','[App] Disabled.':'stopped','[App] Exit.':'start_failed',
        '[Core] Start.':'rules_loading','[Proxy] Enabled.':'rules_loading',
        '[Proxy] Hijack successful.':'complete','[Proxy] Hijack failed.':'start_failed',
        '[Profile] Check failed.':'start_failed','[Profile] Test failed.':'start_failed',
        '[App] Core is not executable.':'start_failed',
        '[Proxy] Timeout, TUN device is not online.':'start_failed'
    },
    homeproxy: {
        'Reloading service...':'restart','Service stopped.':'stopped',
        'Error: failed to generate client configuration.':'start_failed',
        'Error: wrong client configuration detected.':'start_failed'
    }
};
function client_line(line, client) {
    let m, body, kind;
    if (client=='nikki') {
        m=match(line,/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\[(App|Core|Proxy|Profile)\] .*)$/);
        if (!m) return null;
        kind=client_messages.nikki[m[2]];
        if (!kind && match(m[2],/^\[App\] Start after \d{1,5} seconds\.$/)) kind='restart';
    } else {
        m=match(line,/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(Info|Tip|Warning|Error|Watchdog|DAEMON)\] (.*)$/);
        if (!m || client=='homeproxy' && m[2]!='DAEMON' || client=='openclash' && m[2]=='DAEMON') return null;
        kind=client_messages[client][m[3]];
        if (!kind && client=='homeproxy' && match(m[3],/^sing-box [0-9]+\.[0-9]+\.[0-9]+([-+._A-Za-z0-9]*)? started\.$/)) kind='complete';
        if (!kind && client=='openclash' && match(m[3],/^【[0-9]+\/[0-9]+】Reload OpenClash Firewall Rules\.\.\.$/)) kind='rules_loading';
    }
    return kind ? {line:m[1]+': '+(kind=='complete' ? 'Running complete!' : 'x'),kind} : null;
};

export function parse(line, client) {
    // Reject binary NUL before regex normalization: POSIX replacement truncates it.
    if (length(line) > 1024 || index(line, chr(0)) >= 0) return null;
    line = replace(line, /\r$/, '');
    if (match(line, /[[:cntrl:]]/)) return null;
    let forced=null;
    if (client && client!='passwall' && client!='passwall2') {
        if (!client_messages[client]) return null;
        let event=client_line(line,client);
        if (!event) return null;
        forced=event.kind; line=event.line;
    }
    let m = match(line, /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}): ?(.*)$/);
    if (!m) return null;
    let original = replace(m[7], / +$/, ''), message = replace(original, /^ +/, '');
    message = replace(message, /^- +/, '');
    let kind = forced || messages[message];
    if (!kind && match(message, /^执行启动延时 \d{1,5} 秒后再启动!$/)) kind = 'restart';
    if (!kind && match(message, /^全局节点：\[[^\r\n]+\].+ 是非法的服务器地址，无法启动！$/)) kind = 'start_failed';
    // Completion/cancellation is emitted at level zero in the audited sources.
    // Node names and indented diagnostic text must not authorize recovery.
    if (!kind || (kind == 'complete' || kind == 'cancelled') && message != original) return null;
    let date = {year:int(m[1]), mon:int(m[2]), mday:int(m[3]),
        hour:int(m[4]), min:int(m[5]), sec:int(m[6]), isdst:-1};
    let epoch = timelocal(date);
    let back = epoch == null ? null : localtime(epoch);
    let valid = back && date.year >= 2020;
    for (let field in ['year','mon','mday','hour','min','sec'])
        if (!back || back[field] != date[field]) valid = false;
    return {kind, time:valid ? epoch : null,
        key:substr(line,0,19) + ':' + kind};
};

// Pure event reducer, shared by the file reader and native regression tests.
export function consume(s, text, wall, up, baseline, reset, client, interval_start) {
    let old_trip = s.trip || 0, was_pending = s.pending == true;
    // Preserve the last known stage when upgrading an older saved cursor.
    if (s.pending && s.pending_time == null && s.event_time != null && s.event_time <= wall + 2)
        s.pending_time = s.event_time;
    let previous = s.recent || [], recent = [];
    for (let line in split(text, '\n')) {
        let e = parse(line,client);
        if (!e) continue;
        // At attachment/reset, timestamps and the old cursor prevent history
        // copied into a replacement journal from replaying as a new restart.
        // Newly appended bytes can span a monitor restart. Accept timestamps
        // within that observed interval only when poll() has verified that
        // wall and monotonic time advanced together. Rotation/attachment
        // and clock jumps retain the strict thirty-second freshness rule.
        let fresh = e.time != null && wall >= 1577836800 && e.time <= wall + 2 &&
            (wall - e.time <= 30 || interval_start != null && e.time >= interval_start);
        if ((baseline || reset) && !fresh) continue;
        if (reset && index(previous, e.key) >= 0) continue;
        push(recent, e.key);
        if (e.kind == 'rules_ready') {
            // Keep the cycle pending until its real completion and service checks.
            if (s.pending) { s.rules_ready_at = e.time; }
            continue;
        }
        if (e.kind == 'complete' || e.kind == 'cancelled') {
            // A stale/invalid completion must never authorize a release.
            if (!fresh || s.pending && s.pending_time != null && e.time < s.pending_time) {
                s.clock_error = true; continue;
            }
            // Cancelling a queued updater restart cannot undo a concurrent
            // rule deletion or stop which has already begun.
            if (e.kind == 'cancelled' && s.pending && s.cancellable != true) continue;
            s.pending = false;
            s.pending_time = null; s.cancellable = false;
        }
        else {
            if (!s.pending) {
                s.trip = (s.trip || 0) + 1;
                s.trigger_kind = e.kind; s.trigger_time = e.time;
                s.pending_time = null; s.cancellable = e.kind == 'restart';
            }
            if (e.kind != 'restart') s.cancellable = false;
            if (e.time != null && e.time <= wall + 2)
                s.pending_time = max(s.pending_time || 0, e.time);
            s.pending = true;
        }
        s.kind = e.kind; s.event_time = e.time; s.observed_at = wall;
        s.event_uptime = up; s.clock_error = !fresh;
    }
    if (baseline) {
        // A historical, fully completed cycle is a baseline, not a new trip.
        s.trip = old_trip + (s.pending && !was_pending ? 1 : 0);
    }
    s.recent = slice(previous, -16);
    for (let key in recent) push(s.recent, key);
    s.recent = slice(s.recent, -32);
    return s;
};

export function poll(old, wall, up, boot_id, path, client) {
    path = path || '/tmp/log/passwall.log';
    client=client || 'passwall';
    let s = old && old.boot_id == boot_id && (!old.client || old.client==client) && (!old.path || old.path==path) ? old :
        {boot_id, trip:0, pending:false, partial:'', recent:[]};
    if (s.catalog_id != catalog_id) {
        s.offset = null; s.partial = ''; s.anchor = ''; s.overlong = false; s.recent = [];
    }
    s.catalog_id = catalog_id;
    // Offsets and incomplete lines are byte-oriented. A 128-byte tail or an
    // unfinished write can split UTF-8, so raw buffers must never enter JSON.
    let partial = type(s.partial) == 'string' ? s.partial : '';
    let anchor = type(s.anchor) == 'string' ? s.anchor : '';
    if (s.buffer_encoding == 'base64') {
        try { partial = b64dec(partial); anchor = b64dec(anchor); }
        catch (e) { partial = null; anchor = null; }
    }
    else if (s.buffer_encoding != null) {
        partial = null; anchor = null;
    }
    if (partial == null || anchor == null) {
        // A corrupt saved buffer cannot authorize completion from a gap.
        partial = ''; anchor = ''; s.offset = null; s.overlong = false;
    }
    // Also migrate legacy raw buffers on early returns (missing/rotated log).
    s.partial = b64enc(partial); s.anchor = b64enc(anchor);
    s.buffer_encoding = 'base64';
    s.client=client; s.path=path;
    let last_wall = s.checked_at, last_up = s.checked_uptime;
    let meta = lstat(path);
    s.checked_at = wall; s.checked_uptime = up;
    // Reject special files before opening: a FIFO must not stall protection.
    if (!meta || meta.type != 'file') { s.available = false; return s; }
    let f = open(path, 're');
    if (!f) { s.available = false; return s; }
    let info = stat('/proc/self/fd/' + f.fileno());
    if (!info || info.type != 'file') { f.close(); s.available = false; return s; }
    let device = sprintf('%d:%d', info.dev.major, info.dev.minor);
    let baseline = s.offset == null;
    let reset = !baseline && (s.inode != info.inode || s.device != device || info.size < s.offset);
    if (!baseline && !reset && length(anchor)) {
        f.seek(s.offset - length(anchor), 0);
        reset = f.read(length(anchor)) != anchor;
    }
    let at = baseline || reset ? 0 : s.offset;
    let gap = info.size - at > 65536;
    if (gap) at = info.size - 65536;
    if (baseline || reset || gap) { partial = ''; s.overlong = false; }
    if (gap && !baseline && !s.pending) {
        s.pending = true; s.trip = (s.trip || 0) + 1;
        s.trigger_kind = 'gap'; s.trigger_time = null;
        s.kind = 'gap'; s.observed_at = wall; s.event_time = null;
    }
    f.seek(at, 0);
    let chunk = info.size == at ? '' : f.read(min(65536, info.size - at));
    if (chunk == null) { f.close(); s.available = false; return s; }
    let bytes = length(chunk);
    if (gap) {
        let first = index(chunk, '\n');
        chunk = first < 0 ? '' : substr(chunk, first + 1);
    }
    let text = partial + chunk;
    let last = rindex(text, '\n');
    partial = last < 0 ? text : substr(text, last + 1);
    // Keep bounded state and ignore a split overlong line through its newline.
    let complete = last < 0 ? '' : substr(text, 0, last + 1);
    if (s.overlong && length(complete)) {
        complete = substr(complete, index(complete, '\n') + 1); s.overlong = false;
    }
    if (length(partial) > 1024) { partial = ''; s.overlong = true; }
    let interval_start = null;
    if (!baseline && !reset && last_wall != null && last_up != null &&
        last_wall >= 1577836800 && up >= last_up && wall >= last_wall) {
        let drift = (wall - last_wall) - (up - last_up);
        if (drift >= -2 && drift <= 2) interval_start = last_wall - 2;
    }
    consume(s, complete, wall, up, baseline, reset, client, interval_start);
    s.offset = at + bytes;
    s.inode = info.inode; s.device = device;
    let size = min(128, s.offset);
    f.seek(s.offset - size, 0);
    s.partial = b64enc(partial);
    s.anchor = b64enc(size ? (f.read(size) || '') : '');
    f.close(); s.available = true;
    return s;
};
