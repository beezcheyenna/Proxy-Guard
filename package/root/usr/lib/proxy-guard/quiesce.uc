// Terminate only the verified daemon/fast worker and their descendants.
// Never unlink a lock file: killing its owner releases the original inode.
import { readfile, glob } from 'fs';
function identity(pid) {
    let stat=readfile('/proc/'+pid+'/stat') || '';
    let fields=match(stat, /^\d+ \(.+\) (.*)$/);
    return fields ? split(fields[1], ' ')[19] : null;
}
let seen={}, victims=[], children={};
// /proc/PID/task/PID/children is optional in OpenWrt kernels. PPID is not.
for (let path in glob('/proc/[0-9]*/stat') || []) {
    let pid=match(path,/^\/proc\/(\d+)\/stat$/);
    let tail=match(readfile(path) || '',/^\d+ \(.+\) (.*)$/);
    if (!pid || !tail) continue;
    let parent=split(tail[1],' ')[1];
    if (!children[parent]) children[parent]=[];
    push(children[parent],pid[1]);
}
function collect(pid) {
    if (seen[pid] || length(victims)>64 || +pid<=1) return;
    seen[pid]=true;
    let id=identity(pid);if (id==null) return;
    push(victims,{pid,id});
    for (let child in children[pid] || []) collect(child);
}
for (let role in ['daemon','fast_watch']) {
    let pid=trim(readfile('/var/run/proxy-guard/'+role+'.pid') || '');
    if (!match(pid,/^\d+$/)) continue;
    let argv=split(readfile('/proc/'+pid+'/cmdline') || '', '\x00');
    if (!(role=='daemon' && argv[1]=='/usr/libexec/proxy-guard' && argv[2]=='daemon') &&
        !(role=='fast_watch' && argv[1]=='/usr/lib/proxy-guard/fast-watch.uc')) continue;
    collect(pid);
}
// A killed lock runner may leave its worker reparented to PID 1. Select
// only exact plugin worker/runner paths and actions, then verify start time.
for (let path in glob('/proc/[0-9]*/cmdline') || []) {
    let argv=split(readfile(path) || '', '\x00');
    if ((argv[1]=='/usr/lib/proxy-guard/main.lua' || argv[1]=='/usr/lib/proxy-guard/locked.uc') &&
        (argv[2]=='tick' || argv[2]=='apply')) {
        let matched=match(path, /^\/proc\/(\d+)\/cmdline$/);
        if (matched) collect(matched[1]);
    }
}
// Children first, retaining PID start-time checks against PID reuse.
for (let i=length(victims)-1;i>=0;i--)
    if (identity(victims[i].pid)==victims[i].id)
        system(['kill','-KILL',victims[i].pid]);
