import { open } from 'fs';
if (length(ARGV)!=2 || ARGV[0]!='call' || !({apply:true,egress_info:true,policy_confirm:true,policy_cancel:true})[ARGV[1]]) exit(2);
let lock=open('/var/lock/proxy-guard-access-apply.lock','a',0o600);
if (!lock || !lock.lock('xn')) {
    print('{"ok":false,"error":"apply_busy"}\n');
    exit(0);
}
// Stdin and the descriptor are inherited; a killed wrapper cannot release a
// commit still running in its child. Network polling uses a different lock.
let rc=system(['lua','/usr/lib/proxy-guard/access-rpc.lua','call',ARGV[1]]);
lock.close();
exit(rc==null ? 1 : rc<0 ? 128-rc : rc);
