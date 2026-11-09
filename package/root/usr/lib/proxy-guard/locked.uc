// OpenWrt lock runner without a dependency on the optional util-linux flock.
// fs.lock uses the same kernel flock lock, so old/new runners interoperate.
import { open, error } from 'fs';

function fail(message, code) {
    print(sprintf('%J\n', { ok: false, error: message }));
    system(['logger', '-t', 'proxy-guard', '-p', 'daemon.err', '--', message]);
    exit(code);
}

let action = ARGV[0];
if (length(ARGV) != 1 || !({ tick: true, apply: true, try_apply: true, clear_logs: true, stop: true, cleanup: true, supervise: true, maintenance: true })[action])
    fail('不支持的插件操作', 2);

// Do not use CLOEXEC: the worker inherits the descriptor and keeps the lock
// even if this supervising process is killed. Never unlink the lock inode.
let handle = open(action == 'supervise' ? '/var/lock/proxy-guard-supervision.lock' : '/var/lock/proxy-guard.lock', 'a', 0o600);
if (!handle)
    fail('无法打开插件操作锁：' + error(), 1);

// Log clearing is a synchronous RPC. Fail promptly, without a late mutation,
// while a long probe owns the lock; do not outlive the RPC/browser deadline.
let deadline = clock(true)[0] + (action == 'supervise' || action == 'try_apply' ? 0 : action == 'clear_logs' ? 2 : 120);
while (!handle.lock('xn')) {
    if (clock(true)[0] >= deadline)
        fail('插件正在执行其他操作，本次操作未执行，请稍后重试', 75);
    sleep(200);
}

// Clearing both journals must serialize with the independent fast writer.
// Main lock first; the fast watcher never takes the main lock.
let fast_handle, supervision_handle;
if (action == 'clear_logs') {
    fast_handle = open('/var/lock/proxy-guard-fast.lock', 'a', 0o600);
    if (!fast_handle) fail('无法打开快速保护日志锁', 1);
    while (!fast_handle.lock('xn')) {
        if (clock(true)[0] >= deadline)
            fail('插件正在执行其他操作，本次操作未执行，请稍后重试', 75);
        sleep(100);
    }
}
if (action == 'clear_logs') {
    supervision_handle = open('/var/lock/proxy-guard-supervision.lock', 'a', 0o600);
    if (!supervision_handle) fail('无法打开自检日志锁', 1);
    while (!supervision_handle.lock('xn')) {
        if (clock(true)[0] >= deadline) fail('插件正在执行其他操作，本次操作未执行，请稍后重试', 75);
        sleep(100);
    }
}
// A fixed executable and whitelisted action: no shell interpretation.
let result = system(['lua', '/usr/lib/proxy-guard/main.lua', action == 'try_apply' ? 'apply' : action]);
if (supervision_handle) supervision_handle.close();
if (fast_handle) fast_handle.close();
handle.close();
exit(result == null ? 1 : result < 0 ? 128 - result : result);
