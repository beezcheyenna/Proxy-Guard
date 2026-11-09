import { parse, consume, poll } from './passwall-log.uc';
import { readfile, writefile, open, unlink, rename, symlink } from 'fs';
if (readfile('/etc/pgvm-fixture') == null) die('Use the isolated OpenWrt VM');
let n = 0;
function check(ok, why) { if (!ok) die(why); n++; }
let wall = time(), up = 100;
function line(message, when) {
    let d=localtime(when == null ? wall : when);
    return sprintf('%04d-%02d-%02d %02d:%02d:%02d: %s\n',d.year,d.mon,d.mday,d.hour,d.min,d.sec,message);
}
function fresh() { return {trip:0,pending:false,recent:[]}; }
for (let message in ['重启服务，应用新的规则。','删除 nftables 规则完成。',
    '删除 iptables 规则完成。','清空 NFTSet。','清空 IPSet。',
    '清空并关闭相关程序和缓存完成。','开始加载 nftables 防火墙规则...',
    '全局节点启动失败，停止服务。','DNS 启动失败，停止服务。',
    'Restart the service and apply the new rules.','  - Restart the service and apply the new rules.','Delete nftables rules is complete.',
    'Clear NFTSet.','Clearing and closing related programs and cache complete.']) {
    let s = consume(fresh(), line(message), wall, up, false, false);
    check(s.pending && s.trip == 1, 'exact lifecycle message must trigger: ' + message);
}
for (let message in ['规则更新完毕...','防火墙规则加载完成！','日志文件过长，清空处理！',
    '这是错误 DNS 流程可能导致分流失效的配置说明', 'node name: 删除 nftables 规则完成。',
    '运行完成！ <script>bad()</script>', '- Running complete!']) {
    let s = consume(fresh(), line(message), wall, up, false, false);
    check(!s.pending && s.trip == 0, 'unrelated text cannot become a lifecycle event');
}
check(parse('2026-02-30 08:09:10: 运行完成！')?.time == null, 'invalid calendar dates cannot confirm recovery');
check(parse('2026-10-18 08:09:10: 运行完成！')?.time != null, 'leading-zero decimal month/day/time is supported');
let s = consume(fresh(), line('删除 nftables 规则完成。') + line('清空 NFTSet。') + line('开始加载 nftables 防火墙规则...'),wall,up,false,false);
check(s.pending && s.trip == 1 && s.trigger_kind=='rules_removed', 'multiple messages in one cycle preserve the first trigger');
s = consume(s, line('运行完成！',wall-300),wall,up+1,false,false);
check(s.pending && s.clock_error, 'stale completion cannot clear the pending cycle');
s = consume(s, line('运行完成！',wall+3600),wall,up+2,false,false);
check(s.pending && s.clock_error, 'future completion cannot clear the pending cycle');
s = consume(s, line('运行完成！',wall-1),wall,up+2,false,false);
check(s.pending && s.clock_error, 'a recent completion older than this cycle cannot clear it');
s = consume(s, line('Running complete!'),wall,up+3,false,false);
check(!s.pending && !s.clock_error && s.trip == 1 && s.trigger_kind=='rules_removed', 'completion preserves the historical trigger reason');
s = consume(s,line('删除 nftables 规则完成。')+line('运行完成！'),wall,up+4,false,false);
check(s.trip == 2 && !s.pending, 'another full cycle in the same second is a new trigger');
s = consume(fresh(),line('删除 nftables 规则完成。')+line('运行完成！'),wall,up,true,false);
check(s.trip == 0 && !s.pending, 'completed history at attachment must not replay');
s = consume(fresh(),line('删除 nftables 规则完成。'),wall,up,true,false);
check(s.trip == 1 && s.pending, 'attachment during a recent unfinished restart must block');
s = consume(fresh(),line('删除 nftables 规则完成。',wall-300),wall,up,true,false);
check(s.trip == 0 && !s.pending, 'old history is not a current event');
s = consume(fresh(),line('Restart the service and apply the new rules.'),wall,up,false,false);
s = consume(s,line('Failed or timed out waiting for subscription/rule updates. Restart cancelled.'),wall,up+1,false,false);
check(!s.pending, 'cancelling only a queued restart can finish that cycle');
s = consume(fresh(),line('Delete nftables rules is complete.')+line('Restart the service and apply the new rules.')+
    line('Failed or timed out waiting for subscription/rule updates. Restart cancelled.'),wall,up,false,false);
check(s.pending, 'a separate restart cancellation cannot restore deleted rules');
s = consume(s,line('Starting to load nftables firewall rules...',wall+1)+line('Running complete!',wall),wall+1,up+1,false,false);
check(s.pending && s.clock_error, 'completion must follow the most recent stage, not just the first trigger');
s = consume(s,line('Running complete!',wall+1),wall+1,up+2,false,false);
check(!s.pending, 'same-second completion after the current stage remains valid');
s=consume({trip:1,pending:true,event_time:wall,kind:'rules_removed',recent:[]},line('Running complete!',wall-1),wall,up,false,false);
check(s.pending && s.clock_error,'upgrading an old pending cursor retains its completion time boundary');

let path = '/tmp/pg-log012-test.log'; unlink(path); unlink(path+'.old');
writefile(path,'');
s = poll(null,wall,up,'boot-A',path);
check(s.available && s.offset==0 && !s.pending,'empty readable journal is available, not a read error');
writefile(path,line('运行完成！'));
s = poll(null,wall,up,'boot-A',path);
check(s.available && !s.pending && s.trip == 0,'reader attaches without replaying history');
let f = open(path,'a'); f.write(line('删除 nftables 规则完成。')); f.close();
s = poll(s,wall,up+1,'boot-A',path);
check(s.pending && s.trip == 1,'reader notices append');
s = poll(s,wall,up+2,'boot-A',path);
check(s.trip == 1,'unchanged journal cannot retrigger');
f = open(path,'a'); f.write(substr(line('运行完成！'),0,12)); f.close();
s = poll(s,wall,up+3,'boot-A',path);
check(s.pending,'partial completion cannot release');
f = open(path,'a'); f.write(substr(line('运行完成！'),12)); f.close();
s = poll(s,wall,up+4,'boot-A',path);
check(!s.pending && s.trip == 1,'split line is processed exactly once');
rename(path,path+'.old'); writefile(path,line('清空 NFTSet。',wall+1));
s = poll(s,wall+1,up+5,'boot-A',path);
check(s.pending && s.trip == 2,'replacement journal is reopened');
unlink(path);
s = poll(s,wall+1,up+6,'boot-A',path);
check(!s.available && s.pending,'missing journal cannot clear an existing block');
writefile(path,line('运行完成！',wall+2));
s = poll(s,wall+2,up+7,'boot-A',path);
check(s.available && !s.pending,'fresh completion after replacement is accepted');
// Truncate then regrow past the old offset with unchanged inode.
let padding = ''; for (let i=0;i<40;i++) padding += 'ordinary text\n';
writefile(path,line('DNS 启动失败，停止服务。',wall+3) + padding);
s = poll(s,wall+3,up+8,'boot-A',path);
check(s.pending && s.trip == 3,'anchor detects truncate/regrow, not only file length');
writefile(path,sprintf('%070000s','x')+'\n'+line('运行完成！',wall+4));
s = poll(s,wall+4,up+9,'boot-A',path);
check(!s.pending && length(s.partial)<=1024 && length(s.recent)<=32,'large journals have bounded state and can read a fresh tail completion');
s = poll(s,wall+4,up+10,'boot-B',path);
check(s.trip == 0 && !s.pending,'a new boot discards the prior cursor and event history');
writefile(path,sprintf('%02000s','x'));
s=poll(null,wall+4,up+10,'boot-B',path);
check(s.overlong && !s.pending,'an unfinished overlong line is discarded until its newline');
writefile(path,line('Delete nftables rules is complete.',wall+4));
s=poll(s,wall+4,up+11,'boot-B',path);
check(s.pending && s.trip==1,'rotation after an overlong fragment must not skip the first new lifecycle event');
unlink(path); symlink('/dev/zero',path);
s = poll(s,wall+4,up+11,'boot-B',path);
check(!s.available,'special or symlinked files cannot stall the monitor');
unlink(path); writefile(path,b64dec('/wD/'));
s=poll(null,wall+4,up+12,'boot-B',path);
let restored=json(sprintf('%J',s));
check(restored.offset==s.offset,'binary junk in a partial line cannot corrupt the saved cursor');
unlink(path); unlink(path+'.old');
print(sprintf('PASS %d PassWall log assertions\n',n));
