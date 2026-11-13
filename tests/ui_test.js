const fs = require('fs');
const assert = require('assert');
let status = { phase: 'blocked', enforcement: 'blocked', reason: '<script>bad()</script>', last_probe_at: 1 };
let fail = false;
let saveFailure = false;
let applyResult = { ok: true };
let diagnosticHeaders = [
    {name:'x-pghb-delivery-rate', value:'000'}, {name:'x-pghb-unknown', value:'<b>literal</b>'}
];
let delayedStatus = null, delayedLogs = null;
let logs = { entries: [{ level: 'error', time: 1, message: '<img onerror=bad()>' }] };
const calls = [], fields = [], notifications = [];
const indicators = new Set();
const declarations = [];
let modal;
const rpc = { declare: spec => { declarations.push(spec); return async () => {
    calls.push(spec.method);
    if (spec.method === 'status' && delayedStatus) await delayedStatus;
    if (spec.method === 'logs' && delayedLogs) {
        const snapshot = logs;
        await delayedLogs;
        if (!fail) return snapshot;
    }
    if (fail) throw new Error('offline');
    if (spec.method === 'status') return status;
    if (spec.method === 'logs') return logs;
    if (spec.method === 'apply') return applyResult;
    if (spec.method === 'test_proxy') return {ok:true,connectivity_ok:true,milliseconds:1,complete:true};
    if (spec.method === 'preflight') return {ok:true,checks:[]};
    if (spec.method === 'run_diagnostics') return {ok:true, diagnostics:{ok:true, http_code:200, headers:diagnosticHeaders}};
    return { ok: true };
}; }};
function E(tag, attrs={}, children=[]) {
    const listeners = {};
    return { tag, attrs, children, textContent: '', className: attrs.class || '', classList:{add(){}},querySelectorAll(){return[];},
        replaceChildren(...items) { this.children=items; this.textContent=''; },
        addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
        dispatchEvent(event) { for (const handler of listeners[event.type] || []) handler(event); }
    };
}
class Map {
    section() { return { children:fields, tab() {}, getOption(name) {return fields.find(field=>field.name===name);}, taboption(tab, type, name) { const item={name, option:name, choices:[], value(key,label) {this.choices.push([key,label]);}, depends() {}, formvalue() {return this.current ?? this.default ?? null;}}; fields.push(item); return item; } }; }
    async render() { return E('form'); }
    async save() { calls.push('map.save'); if (saveFailure) throw new Error('invalid form'); }
    async reset() { calls.push('map.reset'); }
}
const uci = { load: async () => {}, save: async () => calls.push('uci.save'), apply: async () => calls.push('uci.apply') };
const ui = { createHandlerFn: (self, fn) => fn.bind(self), addNotification: (...args) => notifications.push(args),
    showIndicator: id => indicators.add(id), hideIndicator: id => indicators.delete(id),
    showModal: (title, content) => { modal={title,content}; },
    hideModal: () => { modal=null; },
    changes: { init: async () => calls.push('changes.init') } };
const form = { Map, NamedSection: 0, Flag: 0, ListValue: 0, Value: 0, DynamicList: 0, MultiValue: 0 };
const root = process.env.PG_SOURCE || '/src';
const translations = Object.fromEntries(fs.readFileSync(root+'/package/i18n/messages.tsv','utf8').split('\n').filter(line=>line && !line.startsWith('#')).map(line=>{ const [zh,en]=line.split('\t'); return [en,zh]; }));
const gettext = key => translations[key] || key;
const i18nSource = fs.readFileSync(root+'/package/root/www/luci-static/resources/proxy_guard_i18n.js','utf8');
const pgI18n = new Function('baseclass','_','E',i18nSource)({extend:x=>x},gettext,E);
const source = fs.readFileSync(root + '/package/root/www/luci-static/resources/view/proxy-guard/overview.js', 'utf8');
const pollers = [];
const pgSetup={attach:async()=>{},begin:()=>{},open:async()=>{},restorePrevious:async()=>{}};
const screen = new Function('view','form','rpc','poll','ui','uci','E','_','pgI18n','pgSetup',source)({ extend:x=>x },form,rpc,{ add(fn,interval){pollers.push({fn,interval});} },ui,uci,E,gettext,pgI18n,pgSetup);
(async () => {
    for (const name of ['self_heal','self_heal_stale','self_heal_cooldown','self_heal_limit','self_heal_window','udp_check','udp_server','udp_port','udp_query','udp_timeout']) assert(source.includes("'"+name+"'"),name);
    screen.lastStatus={version:'0.1.14',phase:'blocked',enforcement:'blocked',reason:'private-password',exit_check:{observed:'203.0.113.222'},udp_probe:{enabled:true,ok:false},supervision:{resources:{identity:'secret-pid',rss_kib:123,cpu_percent:2,log_bytes:55}}};
    screen.lastLogs={entries:[{message:'password=private-password'}],incidents:[{id:'secret',summary:{started_at:1,id:'secret',resets:2,elapsed:20,causes:{log:true,'203.0.113.222':true}}}]};
    const report=JSON.stringify(screen.diagnosticData());
    assert(!/private-password|203\.0\.113\.222|secret|observed|started_at|identity/.test(report),report);
    assert(report.includes('123') && report.includes('log'),'whitelisted measurements and causes retained');

    fail=true;
    const data=await screen.load(); const layout=await screen.render(data);
    await screen.refresh();
    assert(screen.statusBox.className.includes('danger'),'initial RPC failure still renders the page and starts retries');
    assert.deepStrictEqual(pollers.map(p=>p.interval),[1,5]);
    fail=false;
    pollers[0].fn(); await screen.statusRequest; await screen.refreshLogs();
    assert(declarations.filter(s=>['status','logs'].includes(s.method)).every(s=>s.nobatch),'logs cannot hold up status in the HTTP batcher');
    const formNode=layout.children.find(n=>n.tag==='form');
    const heading=layout.children.find(n=>n.tag==='h2');
    const description=layout.children.find(n=>n.attrs&&n.attrs.class==='cbi-map-descr');
    assert(formNode&&heading&&description);
    assert(layout.children.indexOf(heading)<layout.children.indexOf(screen.statusBox));
    assert(layout.children.indexOf(screen.statusBox)<layout.children.indexOf(description));
    assert(layout.children.indexOf(description)<layout.children.indexOf(formNode));
    const tools = layout.children.find(node=>node.attrs?.id==='pg-tools');
    assert(layout.children.indexOf(tools)>layout.children.indexOf(formNode),'configuration tools follow the form');
    const [toolsHeading, toolRow] = tools.children;
    assert.equal(tools.children.length,2,'no result is inserted below the button row');
    assert.deepStrictEqual(toolsHeading.children,[gettext('Configuration and diagnostics')]);
    assert.deepStrictEqual(toolRow.children.map(node=>node.children[0]), [
        'Run setup wizard', 'Raw UCI configuration', 'Load previous confirmed settings',
        'Restore defaults and set up again', 'Check settings and runtime environment',
        'Test current proxy', 'View sanitized diagnostic report'
    ].map(gettext));
    assert(toolRow.children.every(node=>node.className===toolRow.children[0].className));
    const modalResult = id => modal.content[0].children.find(node=>node.attrs.id===id);
    await toolRow.children[4].attrs.click();
    assert.equal(modal.title,gettext('Check settings and runtime environment'));
    assert(modalResult('pg-preflight').textContent.includes(gettext('Read-only check: settings have not been saved or applied, and proxy Internet connectivity has not been tested.')));
    modal.content[0].children.at(-1).attrs.click();
    assert.equal(modal,null);
    await toolRow.children[5].attrs.click();
    assert.equal(modal.title,gettext('Test current proxy'));
    assert(modalResult('pg-test-proxy').textContent.includes(gettext('Proxy connectivity passed')));
    const diagnosticButton = modal.content[0].children.find(node=>node.children[0]===gettext('Run detailed diagnostics'));
    const beforeDiagnostic=calls.length;
    assert.equal(modalResult('pg-run-diagnostics').hidden,true);
    await Promise.all([diagnosticButton.attrs.click(),diagnosticButton.attrs.click()]);
    assert.equal(modal.title,gettext('Test current proxy'));
    assert.equal(modalResult('pg-run-diagnostics').hidden,false);
    assert.deepStrictEqual(calls.slice(beforeDiagnostic),['run_diagnostics']);
    assert(modalResult('pg-run-diagnostics').textContent.includes('x-pghb-delivery-rate: 000'));
    assert(modalResult('pg-run-diagnostics').textContent.includes('x-pghb-unknown: <b>literal</b>'));
    diagnosticHeaders = {};
    await diagnosticButton.attrs.click();
    assert(modalResult('pg-run-diagnostics').textContent.includes('HTTP 200'),'an empty response header object still shows the result');
    ui.hideModal();
    assert.equal(modal,null);
    const recoveryHistory = layout.children.at(-2);
    const clearLogs = layout.children.at(-1).children[0];
    assert.strictEqual(clearLogs.tag,'button');
    assert.strictEqual(clearLogs.attrs.type,'button');
    assert.deepStrictEqual(clearLogs.children,[gettext('Clear logs and recovery history')]);
    assert.strictEqual(recoveryHistory.tag,'details');
    assert.strictEqual(recoveryHistory.children[1],screen.incidentBox);
    assert(layout.children.indexOf(screen.logBox)<layout.children.indexOf(recoveryHistory));
    assert(!source.includes('设置已提交'));
    assert(!source.includes('saveNotice'));
    assert(screen.statusBox.className.includes('warning'));
    assert(screen.logBox.textContent.includes('<img onerror=bad()>'));
    assert(!source.includes('innerHTML'));
    const loggedUuid='00000000-0000-4000-8000-000000000001';
    logs={entries:[{time:1,level:'error',message:'important-event',api_uuid:loggedUuid}],details:[{time:2,level:'debug',message:'<img onerror=bad()>'}],skipped:2};
    await screen.refreshLogs();
    assert(screen.logBox.textContent.includes('important-event') && !screen.logBox.textContent.includes('onerror'));
    assert(screen.logBox.textContent.includes(loggedUuid));
    assert(screen.checkLogBox.textContent.includes('<img onerror=bad()>'));
    assert(screen.logWarning.textContent.includes('2'));
    let releaseOldLogs;
    delayedLogs = new Promise(resolve=>{releaseOldLogs=resolve;});
    const oldLogRequest = screen.refreshLogs();
    delayedLogs = null;
    logs = {entries:[],details:[],incidents:[]};
    const clearRequest = clearLogs.attrs.click();
    assert.strictEqual(screen.refreshLogs(),clearRequest,'poll shares the in-flight clear');
    assert.strictEqual(clearLogs.attrs.click(),clearRequest,'multiple clears share one RPC');
    await clearRequest;
    releaseOldLogs(); await oldLogRequest;
    assert(!screen.logBox.textContent.includes('important-event'),'an old reply cannot restore cleared events');
    assert.equal(screen.incidentBox.textContent,gettext('No recovery event recorded'));
    for (const name of ['enabled','mode','sources4','sources6','ipv6_protect','debug','expected_exit4','exit_fallback_url','targets','dns_ports','schedule_enabled','schedule_start','schedule_end','schedule_utc_offset','schedule_repeat','schedule_weekdays']) assert(fields.some(f=>f.name===name));
    assert.equal(fields.find(f=>f.name==='api_enabled').default,'0');
    const method=fields.find(f=>f.name==='check_mode');
    assert.equal(method.default,'public');
    assert.deepStrictEqual(method.choices.map(v=>v[0]),['public','web']);
    assert.deepStrictEqual(fields.filter(f=>f.name.startsWith('_')).map(f=>f.name),
        ['_official_https','_third_party_https','_exit_ipv4','_api_uuid','_api_advanced']);
    for(const key of ['public_hb_interval','public_hb_sensitive_interval','public_hb_timeout',
        'public_hb_fail','public_hb_recover','web_sensitive_interval','diagnostics_enabled',
        'diagnostics_interval','diagnostics_ttl','exit_provider','api_enabled','api_default_seconds','api_max_seconds']) {
        const field=fields.find(f=>f.name===key);assert(field,key);assert(!field.onchange,key+' does not auto apply');
    }
    assert.equal(fields.find(f=>f.name==='exit_provider').default,'public');
    assert.equal(fields.find(f=>f.name==='exit_check').default,'0');
    const apiEndpoint=fields.find(f=>f.name==='diagnostics_enabled');
    assert.equal(apiEndpoint.default,'0');
    assert.deepStrictEqual(apiEndpoint.choices.map(choice=>choice[0]),['0','1']);
    const apiDefault=fields.find(f=>f.name==='api_default_seconds');
    const apiMax=fields.find(f=>f.name==='api_max_seconds');
    for (const field of [apiDefault,apiMax,fields.find(f=>f.name==='diagnostics_interval'),fields.find(f=>f.name==='diagnostics_ttl')]) {
        assert(/^and\(uinteger,range\(/.test(field.datatype),'API and diagnostic seconds require whole numbers in range');
        assert(field.retain,'inactive fields retain their stored values');
    }
    apiMax.current='60';
    assert.equal(apiDefault.validate('main','60'),true);
    assert.equal(apiDefault.validate('main','61'),gettext('Default API block duration must not exceed the maximum.'));
    apiMax.current='bad';
    assert.equal(apiDefault.validate('main','61'),true,'invalid maximum has its own validation error');
    apiMax.current=null;

    assert(!fields.some(f=>/^cf_|^public_(hb|diag)_url$/.test(f.name)),'fixed official endpoints and removed CF controls have no input fields');
    screen.updateStatus({phase:'healthy',enforcement:'allowing',check_mode:'web',last_probe_ok:true,last_probe_at:1,
        exit_check:{enabled:true,attempted:true,outcome:'timeout',mismatch_pending:false},
        cf_event:{observed:'203.0.113.80',colo:'OLD'}});
    const statusText=JSON.stringify(screen.statusBox.children);
    assert(statusText.includes(gettext('Local control API')));
    assert(!fields.some(field=>field.name==='_api_summary'));
    assert(statusText.includes(gettext('Exit IPv4 lookup timed out')) && statusText.includes(gettext('Passed')));
    assert(!statusText.includes('203.0.113.80') && !statusText.includes('OLD'));
    assert(!declarations.some(d=>d.object==='proxy_guard_access'),'Standard has no private Pro RPC dependency');
    assert(!fields.some(f=>f.name==='exit_source'||f.name==='_read_vps_exit'),'Pro import controls stay outside Standard');
    assert.equal(fields.find(f=>f.name==='schedule_enabled').default,'0');
    assert.equal(fields.find(f=>f.name==='schedule_utc_offset').default,'+00:00');
    assert.equal(fields.find(f=>f.name==='schedule_repeat').default,'');
    assert.notStrictEqual(fields.find(f=>f.name==='schedule_repeat').validate('main',''),true);
    assert.strictEqual(fields.find(f=>f.name==='schedule_repeat').validate('main','weekdays'),true);
    for (const name of ['passwall_watch','passwall_log_watch','passwall_log_interval','boot_guard','passwall_trigger','fast_wait_enabled','fast_wait_seconds','fast_stable_enabled','fast_stable_seconds']) assert(fields.some(f=>f.name===name));
    assert.equal(fields.find(f=>f.name==='passwall_log_watch').default,'0');
    assert.equal(fields.find(f=>f.name==='passwall_log_interval').default,'1');
    assert.equal(fields.find(f=>f.name==='boot_guard').default,'0');
    assert.equal(fields.find(f=>f.name==='passwall_watch').default,'0');
    assert.deepStrictEqual(fields.find(f=>f.name==='proxy_client').choices.map(item=>item[0]),['auto','passwall','passwall2','openclash','nikki','homeproxy']);
    assert.equal(fields.find(f=>f.name==='client_auto_ports').default,'0');
    assert.equal(fields.find(f=>f.name==='passwall_trigger').default,'any');
    assert.equal(fields.find(f=>f.name==='fast_wait_enabled').default,'1');
    assert.equal(fields.find(f=>f.name==='fast_wait_seconds').default,'15');
    assert.equal(fields.find(f=>f.name==='fast_stable_enabled').default,'1');
    assert.equal(fields.find(f=>f.name==='fast_stable_seconds').default,'60');
    const days=fields.find(f=>f.name==='schedule_weekdays');
    assert.deepStrictEqual(days.choices.map(item=>item[0]),['1','2','3','4','5','6','7']);
    assert.strictEqual(days.validate('main',['1','2','6']),true);
    assert.notStrictEqual(days.validate('main',[]),true);
    for (const name of ['schedule_start','schedule_end']) {
        const field=fields.find(f=>f.name===name);
        assert.strictEqual(field.default,'');
        assert.strictEqual(field.placeholder,'HH:MM:SS');
        assert.notStrictEqual(field.validate('main',''),true);
        assert.strictEqual(field.validate('main','05:59:55'),true);
        assert.notStrictEqual(field.validate('main','24:00:00'),true);
        assert.notStrictEqual(field.validate('main','05:59:55;id'),true);
    }
    status={phase:'scheduled',enforcement:'blocked',schedule:{enabled:true,start:'05:59:55',finish:'06:01:00',active:true}};
    status.fast_watch={enabled:true,phase:'boot_wait',boot_pending:true,tcp:true,udp:true,dns:false};
    await screen.refresh(); assert(screen.statusBox.className.includes('warning'));
    assert(JSON.stringify(screen.statusBox).includes('定时保护中'));
    status.schedule.active=false; await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('等待已配置的代理服务启动'));
    status.schedule={enabled:true,start:'23:00:00',finish:'01:00:00',timezone:'UTC-03:30',repeat_mode:'weekdays',weekdays:[1,2,6]};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('星期一、星期二、星期六'));
    assert(JSON.stringify(screen.statusBox).includes('UTC-03:30'));
    calls.length=0;
    const enabled=fields.find(f=>f.name==='enabled');
    enabled.current='1';
    for (const type of ['input','change','widget-change']) formNode.dispatchEvent({type});
    assert.deepStrictEqual(calls,[],'editing must not save, apply or call RPC');
    assert(indicators.has('proxy-guard-draft'),'editing must show the native header indicator');
    enabled.current=null;
    formNode.dispatchEvent({type:'change'});
    assert(!indicators.has('proxy-guard-draft'),'reverting an edit removes the draft indicator');
    enabled.current='1'; formNode.dispatchEvent({type:'change'});
    assert.equal(notifications.length,0);
    await screen.handleSave();
    assert.deepStrictEqual(calls,['map.save'],'Save must only stage form changes');
    assert(!indicators.has('proxy-guard-draft'),'successful Save clears only the browser draft indicator');
    assert.equal(notifications.length,0);
    calls.length=0; await screen.handleSaveApply();
    assert.deepStrictEqual(calls.slice(0,2),['map.save','apply']);
    assert(!calls.includes('commit'));
    assert(!calls.includes('uci.apply'));
    assert(calls.indexOf('changes.init') > calls.indexOf('apply'),'refresh the pending-change indicator only after successful apply');
    assert.equal(notifications.length,0,'success must not cover the page heading');
    assert(!JSON.stringify(layout).includes('设置已提交'));
    calls.length=0;
    formNode.dispatchEvent({type:'change'});
    assert.deepStrictEqual(calls,[]);
    saveFailure=true;
    enabled.current='0'; formNode.dispatchEvent({type:'change'});
    await screen.handleSaveApply();
    assert.equal(notifications.length,1);
    assert.equal(notifications.at(-1)[2],'error');
    assert.deepStrictEqual(notifications.at(-1)[1].children,['invalid form']);
    assert.deepStrictEqual(calls,['map.save'],'invalid forms must never apply');
    assert(indicators.has('proxy-guard-draft'),'invalid Save retains the draft indicator');
    saveFailure=false; calls.length=0; applyResult={ok:false,error:'apply failed'};
    await screen.handleSaveApply();
    assert.equal(notifications.length,2,'failed apply must show a visible error');
    assert.deepStrictEqual(notifications.at(-1)[1].children,['apply failed']);
    assert.equal(notifications.at(-1)[2],'error');
    assert(!calls.includes('changes.init'),'failed apply must preserve the pending-change indicator');
    applyResult={ok:true};
    fail=true; calls.length=0;
    await screen.handleSaveApply();
    assert.deepStrictEqual(notifications.at(-1)[1].children,['offline']);
    assert(!calls.includes('changes.init'));
    fail=false; saveFailure=true; calls.length=0;
    await screen.handleSave();
    assert.deepStrictEqual(calls,['map.save']);
    assert.deepStrictEqual(notifications.at(-1)[1].children,['invalid form']);
    saveFailure=false;
    assert(declarations.every(spec=>spec.reject===true));
    status={phase:'healthy',enforcement:'allowing',supervision:{resources:{rss_kib:20480,cpu_percent:1.6,cpu_core_percent:32,cpu_basis:'all_online_cpus',cpu_cores:20,process_count:3,log_bytes:4096}}};
    await screen.refresh();
    let resourceText=JSON.stringify(screen.statusBox);
    assert(resourceText.includes('1.6%') && resourceText.includes('20') && !resourceText.includes('32%'),'show total CPU capacity, not single-core equivalent');
    delete status.supervision.resources.cpu_basis;
    await screen.refresh();
    assert(!JSON.stringify(screen.statusBox).includes('1.6%'),'legacy samples cannot be presented as whole-system CPU');
    for (const [heartbeat,expected] of [[{enabled:true,allowed:true,last_ok:true,checked_at:1},'Passed'],[{enabled:true,allowed:false,last_ok:true,checked_at:1},'Awaiting verification'],[{enabled:true,allowed:false,last_ok:false,checked_at:1},'Failed']]) {
        status={phase:'healthy',enforcement:'allowing',check_mode:'public',heartbeat,probes:[],last_probe_at:1};await screen.refresh();
        const row=screen.statusBox.children.find(item=>JSON.stringify(item).includes(gettext('Latest connectivity check')));
        assert(JSON.stringify(row).includes(gettext(expected)),'official HTTPS summary follows the actual heartbeat result');
    }
    status={phase:'disabled',enforcement:'off',stale:false}; await screen.refresh();
    assert(screen.statusBox.className.includes('notice'));
    assert(JSON.stringify(screen.statusBox).includes('总开关关闭，定时保护不执行'));
    status={phase:'healthy',enforcement:'missing'}; await screen.refresh();
    assert(screen.statusBox.className.includes('danger'));
    status={phase:'healthy',enforcement:'allowing',fast_watch:{enabled:true,stale:true}}; await screen.refresh();
    assert(screen.statusBox.className.includes('danger'),'expired local-service status cannot appear healthy');
    assert(!JSON.stringify(screen.statusBox).includes('PassWall 日志监视未开启'),'a crashed watcher must not be reported as intentionally disabled');
    status={phase:'down',enforcement:'off',mode:'monitor',fast_watch:{enabled:true,phase:'delay',wait_remaining:15},schedule:{enabled:true,active:true}};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('仅监测；将在 '));
    assert(!JSON.stringify(screen.statusBox).includes('外网已暂停；'));
    status.fast_watch={enabled:true,phase:'sensitive',holding:true}; await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('仅监测；正在确认代理恢复'));
    status.fast_watch={enabled:true,phase:'sensitive',holding:false,stable_elapsed:2,stable_required:60}; await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('仅监测；正在观察代理稳定性：'));
    // Reproduced on native ImmortalWrt: the kernel permit expired while the
    // last worker result and fast watcher still reported a successful probe.
    for (const phase of ['healthy','suspect','recovering']) {
        status={phase,enforcement:'blocked',mode:'guard',reason:'代理检测正常',last_probe_at:1,
            fast_watch:{enabled:true,phase:'sensitive',holding:false,stable_elapsed:15,stable_required:60}};
        await screen.refresh();
        const text=JSON.stringify(screen.statusBox);
        assert(screen.statusBox.className.includes('warning'));
        assert(!text.includes(gettext('Internet restored; enhanced monitoring: ')),
            'an expired kernel permit cannot claim access was restored');
        assert(!text.includes(gettext('Access is allowed during enhanced monitoring; a failure blocks it again')),
            'recovery text must use actual kernel enforcement');
        assert(text.includes(gettext('Validating the proxy before restoring access')));
        assert(text.includes(gettext('Waiting for proxy verification before restoring access')));
    }
    status={phase:'healthy',enforcement:'blocked',mode:'guard',reason:'代理检测正常',
        fast_watch:{enabled:true,phase:'normal',holding:false}};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes(gettext('Waiting for the required successful proxy checks')));
    status={phase:'healthy',enforcement:'allowing',mode:'guard',
        fast_watch:{enabled:true,phase:'sensitive',holding:false,stable_elapsed:15,stable_required:60}};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes(gettext('Internet restored; enhanced monitoring: ')),
        'confirmed allowing state still shows successful recovery');
    status={phase:'blocked',enforcement:'blocked',fast_watch:{enabled:true,phase:'log_wait',log_watch:{enabled:true,available:true,pending:true,event:'rules_removed',event_time:123,checked_at:124}}};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('等待客户端本轮启动及已配置服务恢复'));
    assert(JSON.stringify(screen.statusBox).includes('代理规则已删除'));
    status.fast_watch.log_watch.available=false; await screen.refresh();
    assert(screen.statusBox.className.includes('danger'),'unreadable watched logs must be visible');
    for (const invalid of [{}, { ok:false, error:'backend status failed' }]) {
        status=invalid; await screen.refresh();
        assert(screen.statusBox.className.includes('danger'));
    }
    status={phase:'disabled',enforcement:'off',stale:false};
    logs={ok:false,error:'backend logs failed'}; await screen.refresh();
    assert(screen.logBox.textContent.includes('backend logs failed'));
    assert(screen.statusBox.className.includes('notice'),'log errors cannot replace valid status');
    let releaseLogs;
    delayedLogs=new Promise(resolve=>{releaseLogs=resolve;});
    const waitingLogs=screen.refreshLogs();
    status={phase:'blocked',enforcement:'blocked',reason:'automatic status transition'};
    pollers[0].fn(); await screen.statusRequest;
    assert(JSON.stringify(screen.statusBox).includes('automatic status transition'),'slow logs cannot block automatic status updates');
    logs={entries:[]}; delayedLogs=null; releaseLogs(); await waitingLogs;
    let releaseStatus;
    delayedStatus=new Promise(resolve=>{releaseStatus=resolve;});
    calls.length=0;
    screen.statusUpdatedAt=performance.now()-6000;
    pollers[0].fn(); pollers[0].fn();
    assert.deepStrictEqual(calls,['status'],'slow status requests must not overlap or build up');
    assert(screen.statusBox.className.includes('danger'));
    assert(screen.statusBox.textContent.includes('状态更新延迟'));
    const waitingStatus=screen.statusRequest;
    status={phase:'healthy',enforcement:'allowing'}; delayedStatus=null; releaseStatus(); await waitingStatus;
    assert(screen.statusBox.className.includes('notice'),'a fresh response automatically restores the status display');
    assert(JSON.stringify(screen.statusBox).includes('状态每秒自动刷新'));
    fail=true; await screen.refresh();
    assert(screen.statusBox.textContent.includes('不能据此判断网络已受保护'));
    calls.length=0;await screen.preflight();assert.deepStrictEqual(calls,['preflight'],'draft preflight must never save or apply');
    fail=false;
    status={phase:'healthy',enforcement:'allowing',supervision:{enabled:true,state:'healthy',stale:true}};
    await screen.refresh();assert(screen.statusBox.className.includes('danger'),'stale self-check cannot remain healthy');
    status={phase:'waiting_interface',enforcement:'unverified',interface_waiting:true,stale:false};
    await screen.refresh();
    assert(screen.statusBox.className.includes('warning'),'the real startup interface state must render instead of failing RPC validation');
    assert(!screen.statusBox.textContent.includes('Invalid status'),'waiting for netifd is a supported backend state');
    status={phase:'healthy',enforcement:'blocked',last_probe_at:1,probes:[{ok:true}],fast_watch:{enabled:true,phase:'delay',wait_remaining:8}};
    await screen.refresh();
    assert(JSON.stringify(screen.statusBox).includes('外网仍在阻断'),'a successful old probe must not imply access is restored during the wait');
    screen.lastStatus={phase:'blocked',enforcement:'blocked',supervision:{state:'limited',last_reason:'main_heartbeat',last_restart_result:'queued',restart_limit:3,restart_count:3}};
    const limited=screen.diagnosticData();
    assert.strictEqual(limited.recovery.state,'limited');assert.strictEqual(limited.recovery.reason,'main_heartbeat');assert.strictEqual(limited.recovery.restart_limit,3);
    console.log('PASS UI automatic refresh/retry, independent slow/error logs, stale display, no overlapping requests, draft/save/apply, schedule and errors (LuCI API stubs)');
})().catch(e=>{console.error(e);process.exit(1);});
