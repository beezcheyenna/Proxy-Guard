#!/usr/bin/env python3
"""Boot protection acceptance on the authorized Ubuntu offline OpenWrt VM."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import socket
import struct
import sys
import tarfile
import time

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('lab', type=Path)
ap.add_argument('--stage', choices=['prepare', 'cold', 'faults', 'powerloss', 'lifecycle', 'all'], default='all')
args = ap.parse_args()
assert sys.platform == 'linux', 'Run only on the Ubuntu test host'
lab = args.lab.resolve()
sys.path.insert(0, str(lab))
import vmctl
import boot_suite as b
assert vmctl.ROOT == lab
root = Path(__file__).resolve().parents[1]
result_file = lab/'logs/boot-019-results.json'
results = json.loads(result_file.read_text()) if result_file.exists() else []


def cmd(script, timeout=60):
    rc, out = vmctl.cmd('set -eu\ntest -f /etc/pgvm-fixture\n'+script, timeout)
    assert rc == 0, out
    return out


def decode(text):
    # Kernel boot messages can precede a JSON response on the serial console.
    # Keep JSON parsing strict once the response begins.
    lines = text.splitlines()
    for pos, line in enumerate(lines):
        if line.lstrip().startswith('{'):
            return json.JSONDecoder().raw_decode('\n'.join(lines[pos:]).lstrip())[0]
    raise AssertionError('No JSON response: '+text)


def put(path, data):
    existing = cmd('if test -f '+path+'; then sha256sum '+path+'; fi').split()
    if existing and existing[0] == hashlib.sha256(data).hexdigest():
        return
    value = base64.b64encode(data).decode()
    cmd('rm -f '+path+'.b64')
    for pos in range(0, len(value), 1600):
        cmd('printf %s '+shlex.quote(value[pos:pos+1600])+' >> '+path+'.b64')
    script = "import * as fs from 'fs'; assert(fs.writefile(%s, b64dec(fs.readfile(%s))) != null);" % (repr(path), repr(path+'.b64'))
    cmd('ucode -e '+shlex.quote(script))
    assert cmd('sha256sum '+path).split()[0] == hashlib.sha256(data).hexdigest()
    cmd('rm -f '+path+'.b64')


def record(case, **details):
    results.append({'case': case, **details})
    result_file.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
    summary = {k: v for k, v in details.items() if k not in ('samples', 'events')}
    print('PASS '+case, json.dumps(summary, ensure_ascii=False), flush=True)


def state():
    return decode(cmd('/usr/libexec/proxy-guard status'))


def fast():
    return decode(cmd('cat /var/run/proxy-guard/fast.json'))


def wait_for(predicate, timeout=90):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        s = state()
        if predicate(s):
            return s
        time.sleep(.3)
    raise AssertionError(s)


def tag():
    value = (lab/'vm/tag').read_text().strip()
    command = json.loads((lab/f'logs/{value}-command.json').read_text())
    backends = [command[i+1] for i, v in enumerate(command) if v == '-netdev']
    assert len(backends) == 3 and all('addr.type=unix' in v for v in backends)
    return value


external = [f'{link}:{direction}{family}_{protocol}'
            for link, direction in [('wan', 'out'), ('lan', 'in')]
            for family in (4, 6) for protocol in ('tcp', 'udp')]
preserved = ['lan:management4', 'lan:management6', 'lan:dns4', 'lan:dns6',
             'bypass:bypass4', 'bypass:bypass6']


def traffic(blocked, duration=2):
    boundary = time.time()
    while b.counts(tag())['time'] < boundary:
        time.sleep(.05)
    before = b.counts(tag())
    while b.counts(tag())['time'] < before['time']+duration:
        time.sleep(.05)
    after = b.counts(tag())['received']
    delta = {k: after.get(k, 0)-before['received'].get(k, 0) for k in external+preserved}
    assert all(delta[k] > 0 for k in preserved), delta
    assert all(delta[k] == 0 if blocked else delta[k] > 0 for k in external), delta
    return delta


def router_self():
    start = time.time()
    cmd("curl --disable -s --max-time 4 http://198.51.100.10:49319/ >/dev/null || test $? = 28\n"
        "curl --disable -g -s --max-time 4 'http://[2001:db8:2::10]:49319/' >/dev/null || test $? = 28")
    raw = (lab/f'logs/{tag()}-wire.pcap').read_bytes()
    at = 24
    counts = {'IPv4': 0, 'IPv6': 0}
    while at+16 <= len(raw):
        sec, micro, size, _ = struct.unpack_from('<IIII', raw, at)
        at += 16
        packet = raw[at:at+size]
        at += size
        if sec+micro/1e6 < start or len(packet) < 54:
            continue
        ip = packet[14:]
        if packet[12:14] == b'\x08\x00' and ip[9] == 6:
            src = socket.inet_ntoa(ip[12:16]); tcp = ip[(ip[0] & 15)*4:]; family = 'IPv4'
        elif packet[12:14] == b'\x86\xdd' and ip[6] == 6:
            src = socket.inet_ntop(socket.AF_INET6, ip[8:24]); tcp = ip[40:]; family = 'IPv6'
        else:
            continue
        if len(tcp) > 13 and int.from_bytes(tcp[2:4], 'big') == 49319 and tcp[13] & 2 and src in ('198.51.100.1', '2001:db8:2::1'):
            counts[family] += 1
    assert all(counts.values()), counts
    return counts


def rpc(sid, obj, method, values):
    data = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'call', 'params': [sid, obj, method, values]}, separators=(',', ':'))
    value = decode(cmd("curl -fsS --max-time 25 -H 'Content-Type: application/json' --data "+shlex.quote(data)+' http://127.0.0.1/ubus/'))
    assert value.get('result', [None])[0] == 0, value
    return value['result'][1] if len(value['result']) > 1 else {}


def prepare():
    pkg = root/'dist/luci-app-proxy-guard_0.1.9-1_all.ipk'
    put('/opt/pgvm/boot019.ipk', pkg.read_bytes())
    before = cmd('sha256sum /etc/config/proxy_guard').split()[0]
    sid = decode(cmd("ubus call session login '{\"username\":\"root\",\"password\":\"proxy-guard-fixture\"}'"))['ubus_rpc_session']
    output = cmd('opkg install /opt/pgvm/boot019.ipk', 90)
    assert cmd('sha256sum /etc/config/proxy_guard').split()[0] == before
    s = rpc(sid, 'proxy_guard', 'status', {})
    assert s['enforcement'] == 'off', s
    assert cmd("lua -e 'print(dofile(\"/usr/lib/proxy-guard/core.lua\").VERSION)'").strip() == '0.1.9'
    record('package registration preserves configuration and existing RPC session without manual refresh', output=output)
    rpc(sid, 'uci', 'set', {'config': 'proxy_guard', 'section': 'main', 'values': {'enabled': '1', 'mode': 'guard', 'boot_guard': '1;touch /tmp/boot-injected'}})
    error = rpc(sid, 'proxy_guard', 'apply', {})
    assert error.get('ok') is False and error.get('error'), error
    assert cmd('sha256sum /etc/config/proxy_guard').split()[0] == before
    cmd('test ! -e /tmp/boot-injected\nubus call session destroy '+shlex.quote(json.dumps({'ubus_rpc_session': sid})))
    record('invalid boot option is rejected before committing configuration', error=error['error'])
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode='w:gz') as archive:
        for name, data in [('core_test.lua', (root/'tests/core_test.lua').read_bytes().replace(b'/src/package/root/usr/lib/?.lua', b'/usr/lib/?.lua')),
                           ('fast_state_test.uc', (root/'tests/fast_state_test.uc').read_bytes()),
                           ('fast-state.uc', (root/'package/root/usr/lib/proxy-guard/fast-state.uc').read_bytes())]:
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    put('/tmp/boot019-tests.tgz', bundle.getvalue())
    output = cmd('mkdir -p /tmp/boot019-tests\ntar -xzf /tmp/boot019-tests.tgz -C /tmp/boot019-tests\n'
                 'cmp /tmp/boot019-tests/fast-state.uc /usr/lib/proxy-guard/fast-state.uc\n'
                 'ucode /tmp/boot019-tests/fast_state_test.uc\nlua /tmp/boot019-tests/core_test.lua')
    record('native ucode state and Lua configuration regressions', output=output)
    fixture = '''#!/bin/sh /etc/rc.common
START=17
start() {
    test -f /etc/pgvm-fixture || return 1
    mkdir -p /tmp/etc/passwall/bin /tmp/etc/passwall/acl/default
    ln -sf /usr/bin/ucode /tmp/etc/passwall/bin/xray
    ln -sf /usr/bin/ucode /tmp/etc/passwall/bin/chinadns-ng
    printf '%s\\n' 'while (true) sleep(1000);' > /tmp/etc/passwall/acl/default/global.uc
    cp /tmp/etc/passwall/acl/default/global.uc /tmp/etc/passwall/acl/default/chinadns_ng.uc
    mode="$(cat /opt/pgvm/boot-services-mode)"
    if test "$mode" != none; then
        /tmp/etc/passwall/bin/xray /tmp/etc/passwall/acl/default/global.uc >/tmp/fast-tcp.log 2>&1 &
        echo $! > /tmp/fast-tcp.pid
    fi
    if test "$mode" = all; then
        /tmp/etc/passwall/bin/chinadns-ng /tmp/etc/passwall/acl/default/chinadns_ng.uc >/tmp/fast-dns.log 2>&1 &
        echo $! > /tmp/fast-dns.pid
    fi
}
'''
    put('/etc/init.d/pgvm-boot-services', fixture.encode())
    cmd('chmod 755 /etc/init.d/pgvm-boot-services\n/etc/init.d/pgvm-boot-services enable\n'
        'printf all > /opt/pgvm/boot-services-mode\n/etc/init.d/pgvm-fixture enable\n'
        'touch /etc/config/passwall\nuci set passwall.fixture=global\nuci set passwall.fixture.dns_shunt=chinadns-ng\nuci commit passwall\n'
        'uci set proxy_guard.main.passwall_watch=1\nuci set proxy_guard.main.boot_guard=1\nuci set proxy_guard.main.passwall_trigger=any\n'
        'uci set proxy_guard.main.fast_wait_enabled=1\nuci set proxy_guard.main.fast_wait_seconds=15\n'
        'uci set proxy_guard.main.fast_stable_enabled=1\nuci set proxy_guard.main.fast_stable_seconds=60\n'
        'uci set proxy_guard.main.schedule_enabled=0')
    # A deliberately long legacy wait proves that readiness, not the fixed
    # startup timer, controls this mode. Fixture setup is confined to the VM.
    b.configure_guard(600)
    cmd('sha256sum -c /opt/pgvm/system-config.sha256\nsync')
    record('offline boot fixture prepared; services can precede the S18 plugin')


def cold():
    b.down(); b.boot('boot019-ready'); b.wait_rpc()
    samples = []
    deadline = time.monotonic()+200
    while time.monotonic() < deadline:
        s = state(); f = s.get('fast_watch', {})
        samples.append({'time': time.time(), 'enforcement': s['enforcement'], 'fast': f, 'probe_started': s.get('probe_started')})
        if s['enforcement'] == 'allowing':
            assert f.get('phase') == 'ramp' and f.get('stable_elapsed', 0) >= 60 and not f.get('boot_pending'), s
            assert 0 < s['probe_started'] < 600, s
            break
        assert s['enforcement'] in ('blocked', 'unverified'), s
        if f.get('phase') != 'sensitive' or f.get('stable_elapsed', 0) < 54:
            counts = b.counts(tag())['received']
            assert all(counts.get(k, 0) == 0 for k in external), counts
        time.sleep(1)
    else:
        raise AssertionError(s)
    assert any(row['fast'].get('boot_pending') for row in samples), samples
    events = [json.loads(line) for line in cmd('cat /var/run/proxy-guard/fast-events.jsonl').splitlines() if line.startswith('{')]
    ready = [e for e in events if e['event'] == 'fast_boot_ready']
    restored = [e for e in events if e['event'] == 'fast_restored']
    assert ready and restored and restored[-1]['time']-ready[-1]['time'] >= 75, events
    first = next(json.loads(line) for line in (lab/f'logs/{tag()}-packets.jsonl').read_text().splitlines()
                 if (lambda e: e['link']+':'+e['flow'] in external)(json.loads(line)))
    # Epoch seconds in the guest event are truncated; permit 1s precision.
    assert first['time'] >= restored[-1]['time']-1, (first, restored[-1])
    record('cold boot with services already up still performs full 15+60 verification; no early external packets',
           samples=samples, events=events, first_external=first, traffic=traffic(False))


def faults():
    wait_for(lambda s: s.get('successes', 0) >= 2 and s.get('last_probe_ok') is True, 90)
    previous = fast()
    service = decode(cmd('ubus call service list \'{"name":"proxy-guard"}\''))
    pid = service['proxy-guard']['instances']['fast_watch']['pid']
    cmd('kill -STOP '+str(pid)+'\nrm -f /var/run/proxy-guard/fast.json\nkill -KILL '+str(pid))
    s = wait_for(lambda s: s['enforcement'] == 'blocked' and s.get('fast_watch', {}).get('boot_pending') and s.get('successes') == 0, 20)
    current = fast()
    assert current['generation'] != previous['generation'] and current['holding'], current
    assert s['successes'] == 0 and s['fast_watch']['phase'] == 'delay', s
    record('lost watcher state cannot reuse previous healthy results, even if the trip counter restarts',
           old_trip=previous['trip'], new_trip=current['trip'], successes=s['successes'], traffic=traffic(True))


def powerloss():
    cmd('printf tcp > /opt/pgvm/boot-services-mode\nsync')
    vmctl.hard_stop(); b.boot('boot019-powerloss-final'); b.wait_rpc()
    s = wait_for(lambda s: s['enforcement'] == 'blocked' and s.get('fast_watch', {}).get('phase') == 'boot_wait', 90)
    for _ in range(10):
        time.sleep(2)
        s = state(); f = s.get('fast_watch', {})
        assert s['enforcement'] == 'blocked' and f.get('phase') == 'boot_wait' and f.get('tcp') and f.get('udp') and not f.get('dns'), s
    counts = b.counts(tag())['received']
    assert all(counts.get(k, 0) == 0 for k in external), counts
    record('power-loss reboot waits indefinitely for missing DNS; LAN/DNS/bypass and router own traffic remain available',
           counters=counts, traffic=traffic(True), router_self=router_self())
    cmd('/tmp/etc/passwall/bin/chinadns-ng /tmp/etc/passwall/acl/default/chinadns_ng.uc >/tmp/fast-dns.log 2>&1 &\necho $! > /tmp/fast-dns.pid')
    wait_for(lambda s: s.get('fast_watch', {}).get('phase') == 'delay')
    first_deadline = fast()['delay_until']
    cmd('kill "$(cat /tmp/fast-dns.pid)"')
    wait_for(lambda s: s.get('fast_watch', {}).get('phase') == 'boot_wait')
    time.sleep(2)
    cmd('/tmp/etc/passwall/bin/chinadns-ng /tmp/etc/passwall/acl/default/chinadns_ng.uc >/tmp/fast-dns.log 2>&1 &\necho $! > /tmp/fast-dns.pid')
    wait_for(lambda s: s.get('fast_watch', {}).get('phase') == 'delay')
    assert fast()['delay_until'] > first_deadline
    record('drop during boot delay returns to readiness wait and restarts a full 15 seconds', traffic=traffic(True))
    fixture = '#!/bin/sh\nif test -e /tmp/pgboot-bad; then printf "Status: 500 Error\\r\\n\\r\\n"; else printf "Status: 204 No Content\\r\\n\\r\\n"; fi\n'
    put('/opt/pgvm/www/cgi-bin/boot-check', fixture.encode())
    cmd('chmod 755 /opt/pgvm/www/cgi-bin/boot-check\n'
        'uci set proxy_guard.main.fast_wait_seconds=2\nuci set proxy_guard.main.fast_stable_seconds=8\n'
        'uci -q delete proxy_guard.main.targets\n'
        "uci add_list proxy_guard.main.targets='https://fixture.test/cgi-bin/boot-check|204'\n"
        "uci add_list proxy_guard.main.targets='https://fixture.test/exit.txt|200'\n"
        'uci commit proxy_guard\n/usr/libexec/proxy-guard apply')
    wait_for(lambda s: s.get('fast_watch', {}).get('phase') == 'sensitive' and s['fast_watch'].get('stable_elapsed', 0) >= 1)
    old_trip = fast()['trip']
    cmd('touch /tmp/pgboot-bad')
    wait_for(lambda s: s['enforcement'] == 'blocked' and s.get('last_probe_ok') is False)
    f = fast(); assert f['trip'] > old_trip and f['boot_pending'] and f['holding'], f
    record('one failed HTTPS check during boot stability resets qualification despite normal min_success=1', fast=f, traffic=traffic(True))
    cmd('rm -f /tmp/pgboot-bad')
    s = wait_for(lambda s: s['enforcement'] == 'allowing')
    assert s['fast_watch']['stable_elapsed'] >= 8
    record('fresh stability after interruption restores forwarding', traffic=traffic(False))
    cmd('uci set proxy_guard.main.mode=monitor\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply')
    s = wait_for(lambda s: s['enforcement'] == 'off' and s.get('fast_watch', {}).get('boot_pending'))
    assert not s['firewall_present'], s
    record('boot option in monitor mode never installs blocking rules', traffic=traffic(False))
    # Keep the guest ready for real browser Save/Apply acceptance. No network
    # configuration or external production service has been changed.
    cmd('uci set proxy_guard.main.enabled=0\nuci set proxy_guard.main.fast_wait_seconds=15\n'
        'uci set proxy_guard.main.fast_stable_seconds=60\nuci commit proxy_guard\n/usr/libexec/proxy-guard apply\n'
        'sha256sum -c /opt/pgvm/system-config.sha256')
    assert state()['enforcement'] == 'off'
    record('explicit off removes rules and preserves unrelated system configuration')


def lifecycle():
    cmd('uci set proxy_guard.main.enabled=1\nuci set proxy_guard.main.mode=guard\n'
        'uci set proxy_guard.main.passwall_watch=1\nuci set proxy_guard.main.boot_guard=1\n'
        'uci commit proxy_guard\n/usr/libexec/proxy-guard apply')
    wait_for(lambda s: s['enforcement'] == 'blocked')
    saved = cmd('sha256sum /etc/config/proxy_guard').split()[0]
    sid = decode(cmd("ubus call session login '{\"username\":\"root\",\"password\":\"proxy-guard-fixture\"}'"))['ubus_rpc_session']
    output = cmd('opkg remove luci-app-proxy-guard', 90)
    assert cmd('sha256sum /etc/config/proxy_guard').split()[0] == saved
    cmd('test ! -e /usr/libexec/rpcd/proxy_guard\n'
        'test ! -e /usr/share/luci/menu.d/luci-app-proxy-guard.json\n'
        'test -z "$(ubus list proxy_guard)"\n'
        'if nft list table inet proxy_guard >/dev/null 2>&1; then exit 1; fi\n'
        'test ! -e /etc/rc.d/S18proxy-guard')
    record('final package uninstall during protection removes rules, RPC, menu and autostart; configuration retained', output=output)
    # Explicit fixture reset to exercise an actual fresh install, not a manual
    # service/permission repair. Preserve the modified configuration separately.
    cmd('mv /etc/config/proxy_guard /opt/pgvm/boot019-before-fresh.conf')
    output = cmd('opkg install /opt/pgvm/boot019-final.ipk', 90)
    s = rpc(sid, 'proxy_guard', 'status', {})
    assert s['enforcement'] == 'off' and s['phase'] == 'disabled', s
    assert cmd('uci get proxy_guard.main.boot_guard').strip() == '0'
    manifest = json.loads((root/'dist/files.json').read_text())
    for name, expected in manifest.items():
        assert cmd('sha256sum /'+name).split()[0] == expected, name
    cmd('/etc/init.d/proxy-guard enabled\n'
        'sha256sum -c /opt/pgvm/system-config.sha256\n'
        'ubus call session destroy '+shlex.quote(json.dumps({'ubus_rpc_session': sid})))
    record('fresh final package defaults off; all payload hashes match; existing HTTP/RPC session works without manual refresh',
           files=len(manifest), output=output)


if __name__ == '__main__':
    tag()
    if args.stage in ('prepare', 'all'):
        prepare()
    if args.stage in ('cold', 'all'):
        cold()
    if args.stage in ('faults', 'all'):
        faults()
    if args.stage in ('powerloss', 'faults', 'all'):
        powerloss()
    if args.stage == 'lifecycle':
        lifecycle()
