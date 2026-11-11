// Read committed upstream settings; never change a client's configuration.
import { readfile, glob, stat, open, unlink, rename } from 'fs';
import { cursor } from 'uci';
import { processes } from './services.uc';
const supported = ['passwall','passwall2','openclash','nikki','homeproxy'];
const logs = {passwall:'/tmp/log/passwall.log',passwall2:'/tmp/log/passwall2.log',
    openclash:'/tmp/openclash.log',nikki:'/var/log/nikki/app.log',homeproxy:'/var/run/homeproxy/homeproxy.log'};
function decode(text) { try { return json(text || ''); } catch (e) { return null; } };
function port(value) { let n=int(value); return n>0 && n<65536 ? n : null; };
// Only accept an explicit dnsmasq listening-port directive, not upstream
// server addresses or a number embedded in an unrelated option.
export function dnsmasq_port(text) {
    let value=null;
    for (let line in split(text || '', '\n')) {
        let found=match(trim(line), /^port\s*=\s*(\d+)$/);
        if (found) value=port(found[1]);
    }
    return value;
};
function add_proxy_port(profile,value) {
    let n=port(value); if (n && index(profile.proxy_ports,n)<0) push(profile.proxy_ports,n);
};
function collect(profile,name,value,protocols,config) {
    let n=port(value); if (!n) return;
    profile.required[name]=true;
    push(profile.checks[name],{port:n,protocols,config});
    if (name!='dns' && index(profile.proxy_ports,n)<0) push(profile.proxy_ports,n);
    if (name=='dns' && index(profile.dns_ports,n)<0) push(profile.dns_ports,n);
};
function tunnel(profile,name,device,config) {
    if (type(device)!='string' || !match(device,/^[A-Za-z0-9_.-]{1,15}$/)) return;
    profile.required[name]=true; push(profile.checks[name],{tun:device,config});
};
function credential(value) {
    if (type(value)!='string' || index(value,chr(0))>=0 || match(value,/[\x01-\x1f\x7f]/)) return null;
    let at=index(value,':');
    if (at<1) return null;
    let username=substr(value,0,at),password=substr(value,at+1);
    return length(username)<=255 && length(password)<=255 ? {username,password} : null;
};
function finish(profile) {
    let auth=profile._auth, required=profile._auth_required;
    delete profile._auth; delete profile._auth_required;
    if (!profile.available || !required) return profile;
    if (!auth) { profile.available=false; profile.error='client_socks_auth_unavailable'; return profile; }
    let token=trim(readfile('/proc/sys/kernel/random/uuid') || '');
    if (!match(token,/^[0-9a-f-]{36}$/)) { profile.available=false; profile.error='client_socks_auth_unavailable'; return profile; }
    let base='/var/run/proxy-guard/socks-'+profile.client+'-'+profile.socks_port;
    let contents={json:sprintf('%J',auth),conf:'proxy-user = '+sprintf('%J',auth.username+':'+auth.password)+'\n'};
    for (let suffix,content in contents) {
        let target=base+'.'+suffix,temp=target+'.'+token,f=open(temp,'wex',0o600);
        if (!f || !f.write(content) || !f.close() || !rename(temp,target)) {
            if (f) f.close(); unlink(temp);
            profile.available=false;profile.error='client_socks_auth_unavailable';return profile;
        }
    }
    profile.socks_auth_file=base+'.json';profile.socks_curl_file=base+'.conf';
    return profile;
};
function profile_stamp(path,info) {
    return sprintf('%s:%s:%s:%s',path,info.inode,info.mtime,info.size);
};
function profile_digest(path,output) {
    let tool=stat('/usr/bin/sha256sum') ? '/usr/bin/sha256sum' : stat('/bin/sha256sum') ? '/bin/sha256sum' : null;
    if (!tool) return null;
    let rc=system(['/bin/sh','-c','output="$1"; shift; exec "$@" >"$output" 2>/dev/null','pg-profile',output,tool,path],2000);
    let text=rc==0 ? readfile(output) : null;
    let found=text ? match(text,/^([0-9a-f]{64}) /) : null;
    return found ? found[1] : null;
};
function save_profile(path,token,stamp,up,value,digest) {
    let temp=path+'.'+token,f=open(temp,'wex',0o600);
    if (!f) return;
    let written=f.write(sprintf('%J',{version:3,stamp,updated:up,value,digest})), closed=f.close();
    if (!written || !closed || !rename(temp,path)) unlink(temp);
};
function yaml_metadata(client,path) {
    let info=stat(path);
    if (!info || info.type!='file' || info.size>8388608) return null;
    let cache_path='/var/run/proxy-guard/profile-'+client+'.json';
    let old=decode(readfile(cache_path)), stamp=profile_stamp(path,info), up=clock(true)[0];
    let known=old && old.version==3 && old.stamp==stamp && type(old.value)=='object' && old.updated<=up;
    if (known && up-old.updated<10) return old.value;
    let token=trim(readfile('/proc/sys/kernel/random/uuid') || '');
    if (!match(token,/^[0-9a-f-]{36}$/)) return null;
    let output='/var/run/proxy-guard/profile-'+token+'.tmp', f=open(output,'wex',0o600);
    if (!f) return null; f.close();
    let digest=profile_digest(path,output);
    if (known && digest && old.digest==digest) {
        unlink(output);
        save_profile(cache_path,token,stamp,clock(true)[0],old.value,digest);
        return old.value;
    }
    let command=client=='openclash' ? ['/usr/bin/ruby','/usr/lib/proxy-guard/read-mihomo.rb',path] :
        ['/usr/bin/yq','-o=json','-I=0','{"port": .port, "socks-port": ."socks-port", "mixed-port": ."mixed-port", "redir-port": ."redir-port", "tproxy-port": ."tproxy-port", "dns": (.dns | {"enable": .enable,"listen": .listen}), "tun": (.tun | {"enable": .enable,"device": .device}), "authentication": (.authentication // [] | .[0:1]), "listeners": [ .listeners[]? | {"name": .name,"type": .type,"port": .port,"device": .device,"udp": .udp,"users": (.users // [] | .[0:1])} ]}',path];
    // Parse cold or changed files only. Unchanged files are checked by content
    // digest; a slow interpreter must not invalidate a verified live profile.
    let rc=system(['/bin/sh','-c','output="$1"; shift; exec "$@" >"$output" 2>/dev/null','pg-profile',output,...command],5000);
    let meta=stat(output), text=meta && meta.size<=16384 ? readfile(output) : null;
    let value=rc==0 ? decode(text) : null, after=stat(path);
    if (type(value)!='object' || !after || profile_stamp(path,after)!=stamp) { unlink(output); return null; }
    if (digest && profile_digest(path,output)!=digest) { unlink(output); return null; }
    unlink(output);
    save_profile(cache_path,token,stamp,clock(true)[0],value,digest);
    return value;
};
function json_metadata(profile,path) {
    let meta=stat(path); if (!meta || meta.type!='file' || meta.size>8388608) return false;
    let data=decode(readfile(path)); if (type(data)!='object' || type(data.inbounds)!='array') return false;
    for (let row in data.inbounds) {
        let kind=row.type || row.protocol, tag=lc(row.tag || '');
        let value=row.listen_port || row.port;
        if ((kind=='socks' || kind=='mixed') && !profile.socks_port) {
            profile.socks_port=port(value);
            let settings=row.settings || row.socksSettings || {};
            let users=kind=='socks' && settings.auth=='password' ? settings.accounts : row.users;
            if (type(users)=='array' && length(users)) {
                profile._auth_required=true;
                let account=users[0];
                let name=account.user || account.username,secret=account.pass || account.password || '';
                profile._auth=type(name)=='string' && type(secret)=='string' ? credential(name+':'+secret) : null;
            } else if (settings.auth=='password') profile._auth_required=true;
        }
        if (kind=='socks' || kind=='mixed' || kind=='http') add_proxy_port(profile,value);
        if (kind=='tun') { tunnel(profile,'tcp',row.interface_name,path); tunnel(profile,'udp',row.interface_name,path); continue; }
        if (kind=='redirect') collect(profile,'tcp',value,['tcp'],path);
        if (kind=='tproxy') {
            let network=row.network || 'tcp,udp';
            if (index(network,'tcp')>=0) collect(profile,'tcp',value,['tcp'],path);
            if (index(network,'udp')>=0) collect(profile,'udp',value,['udp'],path);
        }
        if (kind=='dokodemo-door' || kind=='tunnel') {
            let settings=row.settings || row.tunnelSettings || row.dokodemoDoorSettings || {}, network=settings.allowedNetwork || settings.network || 'tcp';
            let name=index(tag,'dns')>=0 ? 'dns' : null;
            if (index(network,'tcp')>=0) collect(profile,name || 'tcp',value,['tcp'],path);
            if (index(network,'udp')>=0) collect(profile,name || 'udp',value,['udp'],path);
        }
        if ((kind=='direct' || kind=='dns') && index(tag,'dns')>=0) collect(profile,'dns',value,['tcp','udp'],path);
    }
    // A standalone SOCKS profile can still be observed without claiming UDP forwarding.
    if (!profile.required.tcp && profile.socks_port) collect(profile,'tcp',profile.socks_port,['tcp'],path);
    return true;
};
function listen_port(value) {
    if (type(value)!='string') return null;
    let found=match(value,/^(\[[0-9A-Fa-f:.%A-Za-z0-9_-]+\]|[A-Za-z0-9_.-]*):(\d+)$/);
    return found ? port(found[2]) : null;
};
// Current PassWall native cores do not use Xray/sing-box "inbounds".
// Read their generated listeners, never their remote node or server ports.
export function native_metadata(profile,path,kind) {
    let meta=stat(path);
    if (!meta || meta.type!='file' || meta.size>8388608) return false;
    let data=decode(readfile(path));
    if (type(data)!='object') return false;
    let found=false;
    function endpoint(name,value,protocols) {
        let n=listen_port(value);
        if (!n) { profile.native_invalid=true; return; }
        collect(profile,name,n,protocols,path); found=true;
    };
    function socks(value,account) {
        let n=listen_port(value);
        if (!n) { profile.native_invalid=true; return; }
        if (!profile.socks_port) {
            profile.socks_port=n;
            if (account && (account.username!=null || account.password!=null)) {
                profile._auth_required=true;
                profile._auth=type(account.username)=='string' && type(account.password)=='string' ?
                    credential(account.username+':'+account.password) : null;
            }
        }
        add_proxy_port(profile,n); found=true;
    };
    if (kind=='hysteria2') {
        for (let item in [['tcpRedirect','tcp'],['tcpTProxy','tcp'],['udpTProxy','udp']])
            if (data[item[0]]!=null) endpoint(item[1],data[item[0]].listen,[item[1]]);
        if (data.socks5!=null) socks(data.socks5.listen,data.socks5);
        if (data.http!=null) {
            let n=listen_port(data.http.listen);
            if (n) { add_proxy_port(profile,n); found=true; } else profile.native_invalid=true;
        }
    } else if (kind=='ss-rust') {
        if (type(data.locals)!='array' || length(data.locals)>32) return false;
        for (let row in data.locals) {
            if (type(row)!='object') { profile.native_invalid=true; continue; }
            let value=port(row.local_port), mode=row.mode || data.mode || 'tcp_only', protocol=row.protocol || 'socks';
            if (!value || index(['tcp_only','udp_only','tcp_and_udp'],mode)<0) { profile.native_invalid=true; continue; }
            if (protocol=='socks' || protocol=='http') {
                if (protocol=='socks') socks(':'+value,null); else add_proxy_port(profile,value);
                found=true;
            } else if (protocol=='redir') {
                if (index(mode,'tcp')>=0) collect(profile,'tcp',value,['tcp'],path);
                if (index(mode,'udp')>=0) collect(profile,'udp',value,['udp'],path);
                found=true;
            }
        }
    } else if (kind=='naiveproxy') {
        if (data.listen==null) return false;
        let values=type(data.listen)=='array' ? data.listen : [data.listen];
        if (length(values)>16) return false;
        for (let value in values) {
            if (type(value)!='string') { profile.native_invalid=true; continue; }
            let row=match(value,/^(socks|http|redir):\/\/(.+)$/);
            if (!row) { profile.native_invalid=true; continue; }
            if (row[1]=='socks') socks(row[2],null);
            else if (row[1]=='redir') endpoint('tcp',row[2],['tcp']);
            else {
                let n=listen_port(row[2]);
                if (n) { add_proxy_port(profile,n); found=true; } else profile.native_invalid=true;
            }
        }
    } else return false;
    if (!profile.required.tcp && profile.socks_port)
        collect(profile,'tcp',profile.socks_port,['tcp'],path);
    return found && profile.native_invalid!=true;
};

export function resolve(requested) {
    requested=requested || 'auto';
    let installed=[];
    for (let name in supported)
        if (stat('/etc/init.d/'+name) && stat('/etc/config/'+name)) push(installed,name);
    let client=requested=='auto' && length(installed)==1 ? installed[0] : requested;
    let p={client,requested,installed,available:false,error:null,required:{tcp:true,udp:true,dns:true},
        checks:{tcp:[],udp:[],dns:[]},proxy_ports:[],dns_ports:[],log_path:logs[client]};
    if (requested=='auto' && length(installed)!=1) { p.error=length(installed) ? 'multiple_clients_select_one' : 'no_supported_client_installed'; return p; }
    if (index(supported,client)<0) { p.error='unsupported_proxy_client'; return p; }
    if (index(installed,client)<0) { p.error='selected_client_not_installed'; return p; }
    let u=cursor();
    if (client=='passwall') {
        p.dns_mode='dnsmasq';
        let selected=null;
        u.foreach('passwall','global',s=>{ if (s.dns_shunt) p.dns_mode=s.dns_shunt; selected=s.node || s.tcp_node; });
        let kind=lc(selected ? u.get('passwall',selected,'type') || '' : '');
        if (index(['hysteria2','ss-rust','naiveproxy'],kind)>=0) {
            p.native_core=kind; p.required={tcp:false,udp:false,dns:false};
        }
        if (p.dns_mode!='smartdns' && p.dns_mode!='chinadns-ng') p.dns_mode='dnsmasq';
        // The current default ACL redirects LAN DNS to a dedicated dnsmasq
        // listener. Preserve that verified role when protection blocks Internet.
        // Read the default core first so another ACL cannot choose the probe.
        let base='/tmp/etc/passwall/acl/default/';
        let count=0;
        function metadata(path) {
            if (p.native_core) { if (native_metadata(p,path,kind)) count++; }
            else json_metadata(p,path);
        };
        metadata(base+'global.json');
        let files=glob(base+'*.json') || [];
        if (length(files)>32) { p.error='too_many_client_profiles'; return p; }
        for (let path in files) if (path!=base+'global.json') metadata(path);
        let conf=base+'dnsmasq.conf',info=stat(conf);
        if (info && info.type=='file' && info.size<=65536) {
            let value=dnsmasq_port(readfile(conf));
            if (value) collect(p,'dns',value,['tcp','udp'],conf);
        }
        p.available=!p.native_core || count>0 && p.required.tcp && p.native_invalid!=true;
        delete p.native_invalid;
        if (!p.available) p.error='client_runtime_profile_unavailable';
        return finish(p);
    }
    p.required={tcp:false,udp:false,dns:false};
    if (client=='passwall2' || client=='homeproxy') {
        let files=client=='homeproxy' ? ['/var/run/homeproxy/sing-box-c.json'] : glob('/tmp/etc/passwall2/acl/*.json') || [];
        if (length(files)>32) { p.error='too_many_client_profiles'; return p; }
        let count=0;
        for (let path in files) if (json_metadata(p,path)) {
            count++;
            if (client=='passwall2') {
                let conf=replace(path,/\.json$/,'_dnsmasq.conf'),info=stat(conf);
                if (info && info.type=='file' && info.size<=65536) {
                    let dns_port=null;
                    for (let line in split(readfile(conf) || '', '\n')) {
                        let found=match(line,/^port=(\d+)$/);
                        if (found) dns_port=port(found[1]);
                    }
                    if (dns_port) collect(p,'dns',dns_port,['tcp','udp'],conf);
                }
            }
        }
        p.available=count>0 && p.required.tcp;
        if (!p.available) p.error='client_runtime_profile_unavailable';
        return finish(p);
    }
    let path=client=='nikki' ? '/etc/nikki/run/config.yaml' : null;
    if (!path) {
        for (let process in processes('openclash')) {
            if (path && path!=process.config) { p.error='multiple_client_profiles'; return p; }
            path=process.config;
        }
        if (!path) {
            let configured=u.get('openclash','config','config_path') || '';
            let name=replace(configured,/^.*\//,'');
            if (match(name,/^[A-Za-z0-9_. -]{1,128}\.(yaml|yml)$/)) path='/etc/openclash/'+name;
        }
    }
    let meta=path ? yaml_metadata(client,path) : null;
    if (!meta) { p.error='client_runtime_profile_unavailable'; return p; }
    p.socks_port=port(meta['socks-port']) || port(meta['mixed-port']);
    if (p.socks_port && type(meta.authentication)=='array' && length(meta.authentication)) {
        p._auth_required=true;p._auth=credential(meta.authentication[0]);
    }
    for (let key in ['socks-port','mixed-port','port']) add_proxy_port(p,meta[key]);
    let enabled_udp=client!='openclash' || u.get('openclash','config','enable_udp_proxy')!='0';
    let mode=client=='openclash' ? u.get('openclash','config','en_mode') || '' : null;
    let tcp_mode=client=='nikki' ? u.get('nikki','proxy','tcp_mode') || 'redirect' : index(mode,'-tun')>=0 ? 'tun' : 'redirect';
    let udp_mode=client=='nikki' ? u.get('nikki','proxy','udp_mode') || 'tproxy' : index(mode,'-tun')>=0 || index(mode,'-mix')>=0 ? 'tun' : 'tproxy';
    p.core_only=client=='nikki' && (u.get('nikki','config','core_only')=='1' || u.get('nikki','proxy','enabled')=='0');
    if (p.core_only) {
        if (p.socks_port) collect(p,'tcp',p.socks_port,['tcp'],path);
    } else {
        if (tcp_mode=='tun') tunnel(p,'tcp',meta.tun && meta.tun.enable==true ? meta.tun.device : null,path);
        else collect(p,'tcp',tcp_mode=='tproxy' ? meta['tproxy-port'] : meta['redir-port'],['tcp'],path);
        if (enabled_udp) {
            if (udp_mode=='tun') tunnel(p,'udp',meta.tun && meta.tun.enable==true ? meta.tun.device : null,path);
            else collect(p,'udp',meta['tproxy-port'],['udp'],path);
        }
    }
    for (let row in meta.listeners || []) {
        if (row.type=='mixed' || row.type=='socks') { if (!p.socks_port) p.socks_port=port(row.port); }
        if (row.type=='mixed' || row.type=='socks' || row.type=='http') add_proxy_port(p,row.port);
        if (row.type=='redir' && tcp_mode=='redirect' && !length(p.checks.tcp)) collect(p,'tcp',row.port,['tcp'],path);
        if (row.type=='tproxy') {
            if (tcp_mode=='tproxy' && !length(p.checks.tcp)) collect(p,'tcp',row.port,['tcp'],path);
            if (enabled_udp && udp_mode=='tproxy' && !length(p.checks.udp)) collect(p,'udp',row.port,['udp'],path);
        }
        if (row.type=='tun') {
            if (tcp_mode=='tun' && !length(p.checks.tcp)) tunnel(p,'tcp',row.device,path);
            if (enabled_udp && udp_mode=='tun' && !length(p.checks.udp)) tunnel(p,'udp',row.device,path);
        }
    }
    if (meta.dns && meta.dns.enable==true) {
        let m=match(meta.dns.listen || '',/:(\d+)$/);
        if (m) collect(p,'dns',m[1],['tcp','udp'],path);
        else { p.error='client_dns_listener_unavailable'; return p; }
    }
    p.available=p.required.tcp && (p.core_only || !enabled_udp || p.required.udp);
    if (!p.available) p.error='client_listener_configuration_unavailable';
    return finish(p);
};
