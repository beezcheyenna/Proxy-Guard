import { open } from 'fs';

let action=ARGV[0];
let allowed={heartbeat:true,run_diagnostics:true,test_proxy:true,heartbeat_gate:true,
    api_diagnostics:true,api_block:true,api_cancel:true,api_sync:true};
if (!allowed[action]) exit(2);

let diagnostic=action=='run_diagnostics' || action=='api_diagnostics';
let mutation=action=='api_block' || action=='api_cancel';
let path=action=='heartbeat' ? '/var/lock/proxy-guard-heartbeat.lock' :
    diagnostic ? '/var/lock/proxy-guard-diagnostic.lock' :
    action=='test_proxy' ? '/var/lock/proxy-guard-test-proxy.lock' :
    action=='heartbeat_gate' ? '/var/run/fw4.lock' : '/var/lock/proxy-guard-api.lock';
let deadline=clock(true)[0]+(action=='heartbeat'||diagnostic||action=='test_proxy'||mutation?0:2);
function acquire(path,mode) {
    let file=open(path,'a',0o600);
    if (!file) return null;
    while (!file.lock(mode)) {
        if (clock(true)[0]>=deadline) { file.close(); return null; }
        sleep(20);
    }
    return file;
}
function busy() {
    print('{"ok":false,"error":"busy"}\n');
    exit(75);
}
// Configuration applies take the setup lock before calling the API sync path.
let setup=mutation && acquire('/var/lock/proxy-guard-setup.lock','sn');
if (mutation && !setup) busy();
let lock=acquire(path,action=='heartbeat_gate'?'sn':'xn');
if (!lock) busy();
let fw;
if (mutation || action=='api_sync') {
    fw=acquire('/var/run/fw4.lock','sn');
    if (!fw) busy();
}
let cmd=['lua','/usr/lib/proxy-guard/extension-main.lua',action];
if (mutation && ARGV[1]) push(cmd,ARGV[1]);
let rc=system(cmd);
if(fw)fw.close();
lock.close();
if(setup)setup.close();
exit(rc==null?1:rc<0?128-rc:rc);
