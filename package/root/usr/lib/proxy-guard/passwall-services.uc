import { readfile, glob } from 'fs';

function port_identity(port) {
    let sockets = [];
    for (let name in ['tcp', 'tcp6', 'udp', 'udp6']) {
        for (let line in split(readfile('/proc/net/' + name) || '', '\n')) {
            let fields = split(trim(line), /\s+/);
            if (length(fields) > 9 && match(fields[1], ':' + sprintf('%04X', port) + '$') &&
                (fields[3] == '0A' || fields[3] == '07')) push(sockets, fields[9]);
        }
    }
    return join(',', sort(sockets));
}
export function services(dns_mode) {
    let tcp = false, udp = false, dns = false;
    let ids = {tcp:[],udp:[],dns:[]};
    for (let path in glob('/proc/[0-9]*/cmdline') || []) {
        let argv = split(readfile(path) || '', '\x00');
        let args = join(' ', argv);
        if (!length(args)) continue;
        let executable = argv[0];
        // Keep full command-line discovery, but read identity only for candidates.
        if (index(executable, '/tmp/etc/passwall/bin/') != 0 &&
            !(dns_mode == 'smartdns' && index(executable, 'smartdns') >= 0)) continue;
        let stat = readfile(replace(path, /cmdline$/, 'stat')) || '';
        if (match(stat, /\) [ZX] /)) continue;
        let fields = split(trim(replace(stat, /^\d+ \(.*\) /, '')), /\s+/);
        let identity = path + ':' + (fields[19] || '');
        let pw = index(executable, '/tmp/etc/passwall/bin/') == 0;
        let global = pw && index(args, 'default') >= 0 && index(args, 'global') >= 0;
        if (global) {
            tcp = true;
            push(ids.tcp, identity);
            if (index(executable, 'naive') < 0) { udp = true; push(ids.udp, identity); }
        }
        // Older PassWall layouts use separate TCP/UDP commands in default ACL.
        if (pw && index(args, '/acl/default/') >= 0) {
            if (match(args, /[\/_]TCP([\._ ]|$)/)) { tcp = true; push(ids.tcp, identity); }
            if (match(args, /[\/_]UDP([\._ ]|$)/)) { udp = true; push(ids.udp, identity); }
        }
        if (dns_mode == 'chinadns-ng' && pw && index(args, 'default') >= 0 && index(args, 'chinadns_ng') >= 0) { dns = true; push(ids.dns, identity); }
        if (dns_mode == 'smartdns' && index(executable, 'smartdns') >= 0 &&
            index(args, '/tmp/etc/passwall/acl/default/smartdns.conf') >= 0) { dns = true; push(ids.dns, identity); }
    }
    let identities = {tcp:join(',',sort(ids.tcp)),udp:join(',',sort(ids.udp)),dns:join(',',sort(ids.dns))};
    if (dns_mode != 'chinadns-ng' && dns_mode != 'smartdns') {
        identities.dns = port_identity(15353); dns = length(identities.dns) > 0;
    }
    return { tcp, udp, dns, identities };
};
