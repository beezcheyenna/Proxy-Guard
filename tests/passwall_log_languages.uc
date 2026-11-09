import { parse, consume, poll } from './passwall-log.uc';
import { readfile, writefile, open, unlink } from 'fs';
if (readfile('/etc/pgvm-fixture') == null) die('Use the isolated OpenWrt VM');
let n=0, wall=time(), up=100;
function check(ok,why) { if (!ok) die(why); n++; }
function fresh() { return {trip:0,pending:false,recent:[]}; }
function line(message,when) {
    let d=localtime(when==null?wall:when);
    return sprintf('%04d-%02d-%02d %02d:%02d:%02d: %s\n',d.year,d.mon,d.mday,d.hour,d.min,d.sec,message);
}
let root=getenv('PG_SOURCE');
let corpus=json(readfile(root ? root+'/tests/passwall_log_corpus.json' : '/tmp/pg-log-languages/passwall_log_corpus.json'));
let starts={},ends={},cancels={};
for (let item in corpus.cases) {
    let raw=line(item.message),e=parse(substr(raw,0,length(raw)-1));
    check(e?.kind==item.kind && e.time==wall,'actual source message: '+item.language+' '+item.message);
    check(parse(replace(raw,/\n$/,'\r'))?.kind==item.kind,'CRLF log: '+item.language);
    if (item.kind=='complete') {
        ends[item.language]=item.message;
        check(parse(substr(line('  - '+item.message),0,-1))==null,'indented completion cannot release');
        let s=consume(fresh(),line('删除 nftables 规则完成。'),wall,up,false,false);
        s=consume(s,line(item.message,wall-1),wall,up+1,false,false);
        check(s.pending,'older completion must not release');
        s=consume(s,line(item.message,wall+3600),wall,up+1,false,false);
        check(s.pending,'future completion must not release');
        s=consume(s,line(item.message),wall,up+2,false,false);
        check(!s.pending && s.trip==1,'current completion ends log wait only');
    }
    else if (item.kind=='cancelled') {
        cancels[item.language]=item.message;
        let s=consume(fresh(),line('删除 nftables 规则完成。')+line(item.message),wall,up,false,false);
        check(s.pending,'cancellation cannot undo removal: '+item.language);
    }
    else if (item.kind=='rules_ready') {
        let s=consume(fresh(),line('删除 nftables 规则完成。')+raw,wall,up,false,false);
        check(s.pending && s.trip==1,'rule loading completion is not service startup completion');
    }
    else {
        starts[item.language]=item.message;
        let s=consume(fresh(),raw,wall,up,false,false);
        check(s.pending && s.trip==1,'all audited failure stages block: '+item.language);
        check(consume(fresh(),line(item.message,wall-300),wall,up,true,false).trip==0,'old history does not replay');
    }
    check(parse(substr(line('node name: '+item.message),0,-1))==null,'node names cannot become lifecycle messages');
}
for (let language in corpus.languages) {
    check(starts[language]!=null && ends[language]!=null && cancels[language]!=null,'complete catalog '+language);
    for (let other in corpus.languages) {
        let s=consume(fresh(),line(starts[language])+line(ends[other]),wall,up,false,false);
        check(!s.pending && s.trip==1,'language changes during one restart '+language+' -> '+other);
    }
}
for (let message in ['Scheduled tasks: Auto restart service.','Scheduled tasks: Auto stop service.',
 '配置定时任务：自动更新规则。','日志文件过长，清空处理！','规则更新完毕...',
 'Delete nftables rules is complete. extra','Running complete! <script>','  Running complete!',
 '运行完成！\rDELETE','全局节点：[运行完成！]','删除 nftables 规则完成。\u001b[0m']) {
 check(parse(substr(line(message),0,-1))==null,'benign/malformed/lookalike text: '+message);
}
check(parse(substr(line('执行启动延时 15 秒后再启动!'),0,-1))?.kind=='restart','real startup delay');
check(parse(substr(line('执行启动延时 invalid 秒后再启动!'),0,-1))==null,'delay must be numeric');
check(parse(substr(line('全局节点：[node]example.invalid 是非法的服务器地址，无法启动！'),0,-1))?.kind=='start_failed','real global node address failure');
for (let code in [0,1,9,10,13,27,31,127])
    check(parse(substr(line('Running'+chr(code)+' complete!'),0,-1))==null,'embedded control byte cannot authorize recovery');
let path='/tmp/pg-log-language-upgrade.log';unlink(path);
writefile(path,line('运行完成！'));
let s=poll(null,wall,up,'test',path);s.catalog_id='older';
let f=open(path,'a');f.write(line(starts.ru));f.close();
s=poll(s,wall,up+1,'test',path);
check(s.pending && s.trip==1,'catalog upgrade reads newly supported unfinished restart');
s.catalog_id='older-again';s=poll(s,wall,up+2,'test',path);
check(s.pending && s.trip==1,'catalog refresh preserves existing pending cycle');
f=open(path,'a');f.write(line(ends.fa));f.close();
s=poll(s,wall,up+3,'test',path);check(!s.pending && s.trip==1,'mixed-language file completion');
s.catalog_id='older-third';s=poll(s,wall,up+4,'test',path);
check(!s.pending && s.trip==1,'completed history is not replayed after catalog upgrade');
unlink(path);
print(sprintf('PASS %d upstream log language assertions\n',n));
