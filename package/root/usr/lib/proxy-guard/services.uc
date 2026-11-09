// Local observation only. Profiles are resolved outside this one-second loop.
import { readfile, glob, readlink, stat } from 'fs';
import { services as legacy } from './passwall-services.uc';

export function processes(client) {
    let result = [];
    for (let path in glob('/proc/[0-9]*/cmdline') || []) {
        let argv = split(readfile(path) || '', '\x00'), executable = argv[0] || '';
        let candidate = client == 'passwall2' ? index(executable, '/tmp/etc/passwall2/bin/') == 0 :
            client == 'nikki' ? executable == '/usr/bin/mihomo' :
            client == 'homeproxy' ? executable == '/usr/bin/sing-box' :
            client == 'openclash' ? index(executable, '/etc/openclash/') == 0 || index(executable, '/tmp/etc/openclash/') == 0 : false;
        if (!candidate) continue;
        let base = replace(path, /\/cmdline$/, ''), real = readlink(base + '/exe') || '';
        if (client == 'passwall2' && !match(real, /\/(xray|sing-box|dnsmasq)$/) ||
            client == 'homeproxy' && !match(real, /\/sing-box$/) ||
            client == 'nikki' && !match(real, /\/mihomo(-meta|-alpha)?$/) ||
            client == 'openclash' && !match(real, /\/(clash_meta|mihomo)$/)) continue;
        let text = readfile(base + '/stat') || '';
        if (match(text, /\) [ZX] /)) continue;
        let fields = split(trim(replace(text, /^\d+ \(.*\) /, '')), /\s+/), config = null, directory = null;
        for (let i = 1; i < length(argv) - 1; i++) {
            if (argv[i] == '-C' || argv[i] == '-c' || argv[i] == '-config' || argv[i] == '--config' || argv[i] == '-f') config = argv[i+1];
            if (argv[i] == '-d') directory = argv[i+1];
        }
        if (client == 'nikki' && !config && directory == '/etc/nikki/run') config = directory + '/config.yaml';
        if (client == 'homeproxy' && config != '/var/run/homeproxy/sing-box-c.json' && config != '/tmp/run/homeproxy/sing-box-c.json') continue;
        if (client == 'passwall2' && index(config || '', '/tmp/etc/passwall2/acl/') != 0) continue;
        if (client == 'nikki' && config != '/etc/nikki/run/config.yaml') continue;
        if (client == 'openclash' && (directory != '/etc/openclash' || index(config || '', '/etc/openclash/') != 0 ||
            !match(config, /\.(yaml|yml)$/))) continue;
        if (!fields[19]) continue;
        push(result, {base, config, identity:base+':'+fields[19], real});
    }
    return result;
};

let owner_cache = {};
function owned(process, inode) {
    let key = process.identity + ':' + inode, cached = owner_cache[key];
    if (cached && readlink(cached) == 'socket:[' + inode + ']') return true;
    let count = 0;
    for (let path in glob(process.base + '/fd/*') || []) {
        if (++count > 32768) break;
        if (readlink(path) == 'socket:[' + inode + ']') {
            if (length(keys(owner_cache)) > 128) owner_cache = {};
            owner_cache[key] = path; return true;
        }
    }
    return false;
};
export function tunnel_fdinfo(text,device) {
    for (let line in split(text || '', '\n')) {
        let value=match(line,/^iff:[ \t]*(.*)$/);
        if (value && trim(value[1])==device) return true;
    }
    return false;
};
function owns_tunnel(process,device) {
    let key=process.identity+':tun:'+device, cached=owner_cache[key];
    if (cached && tunnel_fdinfo(readfile(cached),device)) return true;
    let count=0;
    for (let path in glob(process.base+'/fdinfo/*') || []) {
        if (++count>32768) break;
        if (tunnel_fdinfo(readfile(path),device)) { owner_cache[key]=path; return true; }
    }
    return false;
};
function sockets() {
    let result = {tcp:{},udp:{}};
    for (let name in ['tcp','tcp6','udp','udp6']) {
        let protocol = substr(name,0,3);
        for (let line in split(readfile('/proc/net/'+name) || '', '\n')) {
            let f = split(trim(line), /\s+/);
            if (length(f) <= 9 || (protocol == 'tcp' ? f[3] != '0A' : f[3] != '07')) continue;
            let parts = split(f[1], ':'), port = int(parts[1],16);
            if (!port) continue;
            if (!result[protocol][port]) result[protocol][port] = [];
            push(result[protocol][port], f[9]);
        }
    }
    return result;
};
function endpoint(item, candidates, ports) {
    let ids = [];
    for (let protocol in item.protocols || ['tcp']) {
        let found = false;
        for (let inode in ports[protocol][item.port] || [])
            for (let p in candidates)
                if ((!item.config || p.config == item.config) && owned(p,inode)) {
                    found = true; push(ids,p.identity+':'+protocol+':'+inode);
                }
        if (!found) return null;
    }
    return join(',',sort(ids));
};
export function services(dns_mode, profile) {
    if (!profile || profile.client == 'passwall') {
        let value = legacy(dns_mode);
        value.client = 'passwall'; value.required = {tcp:true,udp:true,dns:true};
        value.available = !profile || profile.available != false;
        if (!value.available) { value.tcp=false; value.udp=false; value.dns=false; }
        return value;
    }
    let result = {client:profile.client,available:profile.available == true,error:profile.error,
        required:profile.required || {tcp:true,udp:true,dns:true},tcp:false,udp:false,dns:false,identities:{}};
    if (!result.available) return result;
    let candidates = processes(profile.client), ports = sockets();
    for (let name in ['tcp','udp','dns']) {
        if (result.required[name] == false) { result[name] = null; continue; }
        let items = profile.checks[name] || [], identities = [], good = length(items) > 0;
        for (let item in items) {
            if (item.tun) {
                let flags = int(trim(readfile('/sys/class/net/'+item.tun+'/flags') || '0'),16);
                let ids = [];
                for (let p in candidates) if ((!item.config || p.config == item.config) && owns_tunnel(p,item.tun)) push(ids,p.identity);
                if (!(flags & 1) || !length(ids)) { good=false; continue; }
                push(identities,join(',',sort(ids))+':tun:'+item.tun+':'+trim(readfile('/sys/class/net/'+item.tun+'/ifindex') || ''));
            } else {
                let id = endpoint(item,candidates,ports);
                if (!id) good=false; else push(identities,id);
            }
        }
        result[name] = good;
        result.identities[name] = join(',',sort(identities));
    }
    return result;
};
