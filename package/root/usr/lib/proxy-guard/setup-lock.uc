import { open } from 'fs';
let action=ARGV[0];
if (length(ARGV)!=1 || !({apply:true,setup_info:true,setup_discover:true,setup_confirm:true,setup_cancel:true,setup_previous:true,setup_claim:true,observe:true,tick:true,boot:true,installed:true})[action]) exit(2);
if (action=='setup_info' || action=='setup_discover') {
 let rc=system(['lua','/usr/lib/proxy-guard/setup-main.lua',action]);
 exit(rc==null?1:rc<0?128-rc:rc);
}
let lock=open('/var/lock/proxy-guard-setup.lock','a',0o600);
let deadline=clock(true)[0]+((action=='setup_confirm'||action=='setup_cancel'||action=='setup_claim'||action=='installed'||action=='boot')?2:0);
while (lock && !lock.lock('xn') && clock(true)[0]<deadline) sleep(50);
if (!lock || !lock.lock('xn')) {print('{"ok":false,"error":"setup_transaction_busy"}\n');exit(75);}
let result=system(['lua','/usr/lib/proxy-guard/setup-main.lua',action]);
lock.close();exit(result==null?1:result<0?128-result:result);

