import { open } from 'fs';
let action=ARGV[0] || 'once';
if (length(ARGV)>1 || !({once:true,jobs:true,egress:true})[action]) exit(2);
let lock=open(action=='jobs' ? '/var/lock/proxy-guard-access-jobs.lock' : action=='egress' ? '/var/lock/proxy-guard-access-egress.lock' : '/var/lock/proxy-guard-access.lock','a',0o600);
if (!lock || !lock.lock('xn')) exit(75);
let rc=system(['lua','/usr/lib/proxy-guard/access-main.lua',action]);
lock.close();
exit(rc==null ? 1 : rc<0 ? 128-rc : rc);
