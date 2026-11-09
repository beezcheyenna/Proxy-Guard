// Share fw4's lock so an old include cannot recreate a disabled policy.
import { open, readfile, mkdir, chmod, rename, unlink } from 'fs';
let mode = ARGV[0];
if (mode != 'install' && mode != 'persist' && mode != 'disable') exit(2);
let run = '/var/run/proxy-guard';
let transaction = run + '/transaction.nft';
let next = readfile(run + '/fw4-next.nft');
let marker=run + '/update-guard.active';
let guard=run + '/update-guard.nft';
if (mode != 'disable' && (next == null || length(next) > 131072)) exit(1);
let lock = open('/var/run/fw4.lock', 'a', 0o600);
if (!lock) exit(1);
let deadline = clock(true)[0] + 10;
while (!lock.lock('xn')) {
    if (clock(true)[0] >= deadline) { warn('系统防火墙正忙，稍后重试\n'); exit(75); }
    sleep(50);
}
function nft(action, path) {
    let rc = system(['sh', '-c', 'TZ=UTC0 exec nft ' + action + ' -f "$1"', 'proxy-guard', path]);
    if (rc != 0) warn(sprintf('Native firewall command failed: %J\n', rc));
    return rc == 0;
}
function guarded() {
    return system(['sh','-c','nft list table inet proxy_guard_update >/dev/null 2>&1']) == 0;
}
function release_guard() {
    if (guarded() && system(['nft','delete','table','inet','proxy_guard_update']) != 0) return false;
    if (system(['sh','-c','nft list tables >/dev/null 2>&1']) != 0) return false;
    if (readfile(marker) != null && !unlink(marker)) return false;
    return true;
}
if (mode != 'persist' && !nft('-c', transaction)) exit(1);
if (mode == 'install') {
    let text=readfile(guard);
    if (text == null || length(text)>131072 || !nft('-c',guard)) exit(1);
    let f=open(marker,'w',0o600);
    if (!f || f.write('active\n') != 7 || !f.close()) exit(1);
    // A separate committed transaction makes this guard effective before any
    // main-table rule replacement. Keep an existing crash-surviving guard.
    if (!guarded() && !nft('',guard)) exit(1);
}

if (mode == 'disable') {
    if (!nft('', transaction)) exit(1);
    unlink('/etc/proxy-guard/fw4-guard.nft');
    unlink('/etc/proxy-guard/fw4-guard.nft.new');
    if (!release_guard()) exit(1);
}
else {
    if (mode == 'install' && !nft('', transaction)) exit(1);
    // nft 1.1.1 crashes when a replacement and repeated declarations are
    // combined in one check. Validate the idempotent include separately.
    if (!nft('-c', run + '/fw4-next.nft')) exit(1);
    mkdir('/etc/proxy-guard', 0o700);
    if (!chmod('/etc/proxy-guard', 0o700)) exit(1);
    let path = '/etc/proxy-guard/fw4-guard.nft';
    let f = open(path + '.new', 'w', 0o600);
    if (!f || f.write(next) != length(next) || !f.close() || !rename(path + '.new', path)) exit(1);
}
if (mode == 'install' && !release_guard()) exit(1);
lock.close();
exit(0);
