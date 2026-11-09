// Classify the live opkg transaction, including SDK wrapper processes.
// 0: install/upgrade, 2: explicit removal, 75: unreadable context.
import { readfile } from 'fs';
function fields(pid) {
    let text=readfile('/proc/'+pid+'/stat') || '';
    return split(trim(replace(text,/^.*\) /,'')),/\s+/);
}
let own=fields('self');
let pid=int(own[1] || '0');
for (let depth=0; depth<16 && pid>1; depth++) {
    let stat=fields(pid);
    if (length(stat)<20) exit(75);
    let argv=split(readfile('/proc/'+pid+'/cmdline') || '', '\x00');
    let executable=replace(argv[0] || '',/^.*\//,'');
    if (executable=='opkg' || executable=='opkg-cl') {
        let takes_value={'-f':true,'--conf':true,'--config':true,'-o':true,'--offline-root':true,
                         '-d':true,'--dest':true,'-V':true,'--verbosity':true,'-t':true,'--tmp-dir':true,'--cache':true,
                         '--lists-dir':true,'--add-dest':true,'--add-arch':true,'--add-exclude':true};
        for (let i=1;i<length(argv);i++) {
            let arg=argv[i];
            if (takes_value[arg]) { i++; continue; }
            if (index(arg,'-')==0 || !length(arg)) continue;
            if (arg=='install' || arg=='upgrade') {
                print(sprintf('%d %s\n',pid,stat[19]));
                exit(0);
            }
            // The first command is authoritative. A package name cannot
            // convert an explicit remove into a replacement transaction.
            if (arg=='remove') exit(2);
            exit(75);
        }
        exit(75);
    }
    pid=int(stat[1] || '0');
}
exit(75);
