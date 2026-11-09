const fs = require('fs');
const assert = require('assert');
let status = { phase: 'blocked', enforcement: 'blocked', reason: '<script>bad()</script>', last_probe_at: 1 };
let fail = false;
let saveFailure = false;
let applyResult = { ok: true };
let delayedStatus = null, delayedLogs = null;
let logs = { entries: [{ level: 'error', time: 1, message: '<img onerror=bad()>' }] };
const calls = [], fields = [], notifications = [];
const indicators = new Set();
const declarations = [];
const rpc = { declare: spec => { declarations.push(spec); return async () => {
    calls.push(spec.method);
    if (spec.method === 'status' && delayedStatus) await delayedStatus;
    if (spec.method === 'logs' && delayedLogs) await delayedLogs;
    if (fail) throw new Error('offline');
    if (spec.method === 'status') return status;
    if (spec.method === 'logs') return logs;
    if (spec.method === 'apply') return applyResult;
    return { ok: true };
}; }};
function E(tag, attrs={}, children=[]) {
    const listeners = {};
    return { tag, attrs, children, textContent: '', className: attrs.class || '', classList:{add(){}}, querySelectorAll(){return [];},
        replaceChildren(...items) { this.children=items; this.textContent=''; },
        addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
        dispatchEvent(event) { for (const handler of listeners[event.type] || []) handler(event); }
    };
}
class Map {
    section() { return { children:fields, tab() {}, taboption(tab, type, name) { const item={name, option:name, choices:[], value(key,label) {this.choices.push([key,label]);}, depends() {}, formvalue() {return this.current ?? this.default ?? null;}}; fields.push(item); return item; } }; }
    async render() { return E('form'); }
    async save() { calls.push('map.save'); if (saveFailure) throw new Error('invalid form'); }
    async reset() { calls.push('map.reset'); }
}
const uci = { load: async () => {}, save: async () => calls.push('uci.save'), apply: async () => calls.push('uci.apply') };
const ui = { createHandlerFn: (self, fn) => fn.bind(self), addNotification: (...args) => notifications.push(args),
    showIndicator: id => indicators.add(id), hideIndicator: id => indicators.delete(id),
    changes: { init: async () => calls.push('changes.init') } };
const form = { Map, NamedSection: 0, Flag: 0, ListValue: 0, Value: 0, DynamicList: 0, MultiValue: 0 };
const root = process.env.PG_SOURCE || '/src';
const translations = Object.fromEntries(fs.readFileSync(root+'/package/i18n/messages.tsv','utf8').split('\n').filter(line=>line && !line.startsWith('#')).map(line=>{ const [zh,en]=line.split('\t'); return [en,zh]; }));
const gettext = key => translations[key] || key;
const i18nSource = fs.readFileSync(root+'/package/root/www/luci-static/resources/proxy_guard_i18n.js','utf8');
const pgI18n = new Function('baseclass','_',i18nSource)({extend:x=>x},gettext);
const source = fs.readFileSync(root + '/package/root/www/luci-static/resources/view/proxy-guard/overview.js', 'utf8');
const pollers = [];
const screen = new Function('view','form','rpc','poll','ui','uci','E','_','pgI18n','pgSetup',source)({ extend:x=>x },form,rpc,{ add(fn,interval){pollers.push({fn,interval});} },ui,uci,E,gettext,pgI18n,{attach:()=>Promise.resolve(),begin(){}});
(async () => {
    await screen.load(); await screen.render();
    const flag=fields.find(f=>f.name==='cf_event_check');
    assert(flag && flag.default==='1' && flag.rmempty===false);
    const text=()=>JSON.stringify(screen.statusBox);
    for(const bad of [undefined,null,false,0,'bad',[]]) {
        screen.updateStatus({phase:'healthy',enforcement:'allowing',cf_event:bad});
        assert(text().includes('Cloudflare'));
    }
    screen.updateStatus({phase:'healthy',enforcement:'allowing',exit_check:{ok:true,observed:'203.0.113.10',expected:'203.0.113.10'},cf_event:{enabled:true,attempted:true,checked_at:1,outcome:'ok',observed:'203.0.113.20',colo:'NRT'}});
    assert(text().includes('最近一次 Cloudflare 事件验证') && text().includes('203.0.113.20') && text().includes('203.0.113.10'));
    for(const outcome of ['unavailable','interrupted','mismatch']) {
        screen.updateStatus({phase:'healthy',enforcement:'allowing',cf_event:{enabled:true,attempted:true,checked_at:1,outcome,rechecking:false,pending:true}});
        assert(text().includes('等待代理恢复后验证'));
        if(outcome==='mismatch')assert(text().includes('日常验证现已重新通过'));
    }
    screen.updateStatus({phase:'healthy',enforcement:'allowing',cf_event:{enabled:true,attempted:true,checked_at:1,outcome:'ok',observed:'<img onerror=bad()>',colo:'<script>bad()</script>'}});
    assert(!source.includes('innerHTML'));
    const before=calls.filter(x=>x==='apply').length;flag.current='0';
    assert.equal(calls.filter(x=>x==='apply').length,before);
    console.log('PASS 11 CF event UI states, historical/current exit separation, resolved mismatch and draft-only toggle (LuCI API stubs)');
})().catch(e=>{console.error(e);process.exit(1);});
