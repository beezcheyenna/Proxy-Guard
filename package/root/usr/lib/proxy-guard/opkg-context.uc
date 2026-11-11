// Classify a live opkg or apk transaction, including SDK wrapper processes.
// The filename is retained for installed Pro releases using base API 1.
// 0: install/upgrade/reinstall, 2: explicit removal, 75: unreadable context.
import { readfile } from 'fs';
function fields(pid) {
    let text=readfile('/proc/'+pid+'/stat') || '';
    return split(trim(replace(text,/^.*\) /,'')),/\s+/);
}
let own=fields('self');
let pid=int(own[1] || '0');
for (let depth=0; depth<32 && pid>1; depth++) {
    let stat=fields(pid);
    if (length(stat)<20) exit(75);
    let argv=split(readfile('/proc/'+pid+'/cmdline') || '', '\x00');
    let executable=replace(argv[0] || '',/^.*\//,'');
    if (executable=='opkg' || executable=='opkg-cl' || executable=='apk') {
        let apk=executable=='apk';
        let takes_value=apk ? {
            '-p':true,'--root':true,'-X':true,'--repository':true,
            '--repositories-file':true,'--repository-config':true,'--keys-dir':true,'--cache-dir':true,
            '--arch':true,'--wait':true,'--timeout':true,'--network-timeout':true,
            '--cache-max-age':true,'--progress-fd':true,
            '--preupgrade-depends':true,'--uvol-manager':true
        } : {
            '-f':true,'--conf':true,'--config':true,'-o':true,'--offline-root':true,
            '-d':true,'--dest':true,'-V':true,'--verbosity':true,'-t':true,
            '--tmp-dir':true,'--cache':true,'--lists-dir':true,
            '--add-dest':true,'--add-arch':true,'--add-exclude':true
        };
        for (let i=1;i<length(argv);i++) {
            let arg=argv[i];
            if (takes_value[arg]) { i++; continue; }
            if (index(arg,'-')==0 || !length(arg)) continue;
            if ((!apk && (arg=='install' || arg=='upgrade')) ||
                (apk && (arg=='add' || arg=='upgrade' || arg=='fix'))) {
                print(sprintf('%d %s\n',pid,stat[19]));
                exit(0);
            }
            // Only the first command is authoritative, never a package name.
            if ((!apk && arg=='remove') || (apk && arg=='del')) exit(2);
            exit(75);
        }
        exit(75);
    }
    pid=int(stat[1] || '0');
}
exit(75);
