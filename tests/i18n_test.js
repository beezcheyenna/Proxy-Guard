const fs=require('fs'), assert=require('assert');
const root=process.env.PG_SOURCE || require('path').resolve(__dirname,'..');
const readRows=folder=>fs.readFileSync(root+'/'+folder+'/messages.tsv','utf8').split('\n').filter(line=>line&&!line.startsWith('#')).map(line=>line.split('\t'));
const rows=readRows('package/i18n');
const runtimeSource=fs.readFileSync(root+'/package/root/www/luci-static/resources/proxy_guard_i18n.js','utf8');
const keys=new Set(rows.map(row=>row[1]));
const basePath='package/root/www/luci-static/resources/';
for (const file of [
    basePath+'view/proxy-guard/raw.js',
    basePath+'proxy_guard_setup.js',
    basePath+'view/proxy-guard/overview.js'
]) {
    const source=fs.readFileSync(root+'/'+file,'utf8');
    for(const match of source.matchAll(/\b(?:_|t|pgI18n\.gettext)\(((?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'))\)/g)) {
        const key=require('vm').runInNewContext(match[1]);
        assert(keys.has(key),file+': '+key);
    }
}
for(const [locale,index] of [['zh-CN',0],['en',1],['ja',2],['ru',null],['fa',null]]) {
    const extra=index===null?JSON.parse(fs.readFileSync(root+'/package/i18n/'+locale+'.json','utf8')):null;
    const catalog=Object.fromEntries(rows.map(row=>[row[1],index===null?extra[row[1]]:row[index]]));
    const formatTokens=value=>(value.match(/%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?[sdifgeuxX]/g)||[]).sort();
    const ipTokens=value=>value.match(/\b(?:\d{1,3}\.){3}\d{1,3}(?:\/\d{1,2})?/g)||[];
    for(const row of rows){
        assert.deepStrictEqual(formatTokens(catalog[row[1]]),formatTokens(row[1]),locale+' format placeholders: '+row[1]);
        for(const ip of ipTokens(row[1]))assert(catalog[row[1]].includes(ip),locale+' technical address: '+ip);
        for(const token of row[1].match(/HH:MM:SS|±HH:MM|::\/0|\/tmp\/log\/passwall\.log|65535/g)||[])assert(catalog[row[1]].includes(token),locale+' technical format: '+row[1]);

    }
    const pg=new Function('baseclass','_',runtimeSource)({extend:x=>x},key=>catalog[key] || key);
    assert.equal(pg.runtime('代理检测正常'),catalog['Proxy check passed']);
    const error=pg.runtime('/usr/lib/proxy-guard/worker.lua:68: 入口设备不存在：br-lan');
    assert(error.includes('worker.lua:68: ') && error.endsWith('br-lan'));
    assert(error.includes(catalog['Ingress device does not exist: ']));
    assert.equal(pg.runtime('<img onerror=bad()> curl=7 IP=203.0.113.7'),'<img onerror=bad()> curl=7 IP=203.0.113.7');
    assert(pg.runtime('定时保护窗口 23:00:00–01:00:00（UTC-03:30），局域网和 DNS 保留').includes('UTC-03:30'));
    const fast=fs.readFileSync(root+'/package/root/usr/lib/proxy-guard/fast-watch.uc','utf8');
    const eventBlock=fast.slice(fast.indexOf('let messages ='),fast.indexOf('let message = messages'));
    for(const match of eventBlock.matchAll(/'([^'\n]*[\u3400-\u9fff][^'\n]*)'/g)) {
        const row=rows.find(value=>value[0]===match[1]);
        assert(row,'Full runtime event has no translation: '+match[1]);
        assert.equal(pg.runtime(match[1]),catalog[row[1]],'full lifecycle event '+locale+': '+match[1]);
    }
    assert.equal(pg.runtime(null),null);
}
console.log('PASS translation coverage and Chinese/English/Japanese/Russian/Persian runtime diagnostics preserve technical details');
{
    const vm=require('vm');
    const cbi=process.env.PG_LUCI_CBI || root+'/tests/native-cbi.js';
    assert(fs.existsSync(cbi),'Actual LuCI cbi.js is required; set PG_LUCI_CBI to a matching LuCI file');
    const gettextSource=fs.readFileSync(cbi,'utf8').split('function cbi_d_add')[0];
    const viewChecks=[];
    for (const [locale,column] of [['zh-cn',0],['en',1],['ja',2],['ru',null],['fa',null]]) {
        function lmo(path) {
            const data=fs.readFileSync(root+'/'+path+'.'+locale+'.lmo');
            const offset=data.readUInt32BE(data.length-4), catalog={};
            for (let at=offset;at<data.length-4;at+=16) {
                const key=data.readUInt32BE(at).toString(16).padStart(8,'0');
                const start=data.readUInt32BE(at+8),length=data.readUInt32BE(at+12);
                catalog[key]=data.subarray(start,start+length).toString('utf8');
            }
            return catalog;
        }
        const catalog=lmo('package/root/usr/lib/lua/luci/i18n/proxy-guard');
        const context={window:{TR:catalog},TR:catalog};
        vm.createContext(context);vm.runInContext(gettextSource,context);
        const extra=column===null?JSON.parse(fs.readFileSync(root+'/package/i18n/'+locale+'.json','utf8')):null;
        for(const row of rows) assert.equal(context._(row[1]),column===null?extra[row[1]]:row[column],locale+': '+row[1]);
        viewChecks.push(checkLocalizedViews(locale,key=>context._(key)));
    }
    console.log('PASS all packaged LMO entries using actual LuCI gettext and hash implementation');
    Promise.all(viewChecks).then(locales=>console.log('PASS all localized settings groups, raw editor, wizard steps, RTL and technical inputs (actual LuCI gettext; form/RPC stubs): '+locales.join(', '))).catch(e=>{console.error(e);process.exitCode=1;});

}

async function checkLocalizedViews(locale, gettext) {
    const vm = require('vm');
    const tabs = [], sections = [], fields = [], rpcCalls = [];
    let modal;
    const lang = locale === 'zh-cn' ? 'zh-CN' : locale;
    const direction = locale === 'fa' ? 'rtl' : 'ltr';
    const draft = { enabled:'0', mode:'monitor', interfaces:['br-lan'], proxy_client:'auto', socks_port:'1080', exit_check:'0', passwall_watch:'0', schedule_enabled:'0' };
    function walk(node) {
        if (!node || typeof node !== 'object') return [];
        return [node, ...(node.children || []).flatMap(walk)];
    }
    function E(tag, attrs = {}, children = []) {
        if (!Array.isArray(children)) children = [children];
        const node = { tag, attrs, children, id:attrs.id, dir:attrs.dir, textContent:'', className:attrs.class || '',
            value:attrs.value == null ? '' : String(attrs.value), checked:attrs.checked != null,
            disabled:attrs.disabled != null, classList:{add(){}}, addEventListener(){},
            replaceChildren(...values){this.children=values;this.textContent='';},
            appendChild(value){this.children.push(value);return value;},
            hasAttribute(name){return this.attrs[name]!=null;},
            querySelectorAll(selector){return walk(this).slice(1).filter(n => selector === 'input,textarea' && ['input','textarea'].includes(n.tag));} };
        if (tag === 'textarea') node.value = children.join('');
        if (tag === 'select') node.value = (children.find(n => n.attrs.selected != null) || children[0]).value;
        return node;
    }
    class FormMap {
        constructor(name, title, description){this.name=name;this.children=[];this.description=description;}
        section(kind,...args){
            const list = [];
            const option = (type,name,title,description) => {
                const item={option:name,name,title,description,choices:[],value(key,label){this.choices.push([key,label]);},depends(){},formvalue(){return this.default ?? null;}};
                list.push(item);fields.push(item);return item;
            };
            const section={children:list,option,getOption(name){return list.find(field=>field.name===name);},tab(id,title){tabs.push([id,title]);},taboption(id,...values){const field=option(...values);field.tab=id;return field;}};
            this.children.push(section);sections.push(args);return section;
        }
        async render(){return E('form',{},this.children.flatMap(s => s.children.map(f => E('label',{},[f.title || '',E('input',{id:f.name}),...f.choices.map(v=>E('option',{},[v[1]]))]))));}
    }
    const form={Map:FormMap,NamedSection:{},GridSection:{},Flag:{},Value:{},ListValue:{},DynamicList:{},MultiValue:{}};
    const discovery={ok:true,client:{available:true,client:'passwall2',socks_port:1080,proxy_ports:[1041],dns_ports:[15353]},
        interfaces:[{name:'lan',device:'br-lan',up:true,recommended:true,sources4:['192.0.2.0/24'],sources6:[],local4:['192.0.2.0/24'],local6:[]}]};
    const ui={showModal(title,body){modal={title,body};},hideModal(){},createHandlerFn:(self,fn)=>fn.bind(self),showIndicator(){},hideIndicator(){},addNotification(){},changes:{init:async()=>{}}};
    const rpc={declare:spec=>async()=>{rpcCalls.push(spec.method);
        if(spec.method==='setup_discover')return discovery;
        if(spec.method==='raw_info')return {ok:true,text:"config proxy_guard 'main'\n",template:"config proxy_guard 'main'\n",token:'fixture',validation:{activation_parameters_valid:true}};
        if(spec.method==='status')return {phase:'disabled',enforcement:'off',enabled:false};
        return {ok:true,entries:[]};
    }};
    const ctx={view:{extend:x=>x},baseclass:{extend:x=>x},form,rpc,ui,poll:{add(){}},
        uci:{load:async()=>{},get:(config,section,key)=>key?draft[key]:draft},
        E,_:gettext,document:{documentElement:{lang}},window:{location:{pathname:'/admin/services/proxy-guard'}},
        Date,URL,Blob,TextEncoder,performance,setTimeout:()=>0,clearTimeout:()=>{},
        pgSetup:{attach:async()=>{}}};
    vm.createContext(ctx);
    const load = name => vm.runInContext('(function(){'+fs.readFileSync(root+'/'+name,'utf8')+'\n})()',ctx);
    ctx.pgI18n=load('package/root/www/luci-static/resources/proxy_guard_i18n.js');
    const overview=load('package/root/www/luci-static/resources/view/proxy-guard/overview.js');
    const page=await overview.render();await overview.statusRequest;
    assert.equal(page.dir,direction,locale+' main direction');
    const labels=['General settings','Protection scope','Connection checks','Scheduled protection','Failure protection and recovery','Plugin health, logs and recovery','Local control API'];
    assert.deepStrictEqual(tabs.map(v=>v[1]),labels.map(gettext),locale+' all settings groups');
    assert(fields.some(f=>f.name==='expected_exit4')&&fields.some(f=>f.name==='schedule_utc_offset'));
    assert.equal(fields.find(f=>f.name==='schedule_utc_offset').default,'+00:00');
    assert.equal(fields.find(f=>f.name==='exit_check').default,'0');
    assert.equal(fields.find(f=>f.name==='check_mode').default,'public');
    assert.deepStrictEqual(fields.filter(f=>f.tab==='connection'&&f.name.startsWith('_')).map(f=>f.renderWidget().children[0]),
        ['Official HTTPS settings','Third-party HTTPS settings','Exit IPv4 verification'].map(gettext));
    assert(walk(page).some(n=>n.tag==='h3'&&n.children[0]===gettext('Event log')),locale+' event heading');
    assert.equal(page.children.at(-1).children[0].children[0],gettext('Clear logs and recovery history'));
    assert.equal(page.children.at(-2).children[0].children[0],gettext('Recovery history'),locale+' recovery history heading');
    assert.equal(walk(page).find(n=>n.id==='pg-tools').children[0].children[0],gettext('Configuration and diagnostics'));
    assert.equal(fields.find(f=>f.name==='_api_advanced').renderWidget().children[0].children[0],gettext('Advanced diagnostics'));
    for (const name of ['log_kib','debug']) assert.equal(fields.find(f=>f.name===name).tab,'health');
    assert.equal(walk(page).find(n=>n.id==='expected_exit4').dir,'ltr',locale+' technical input direction');
    ctx.window.location.pathname='/admin/services/proxy-guard-raw';
    const raw=load(basePath+'view/proxy-guard/raw.js');
    const editor=raw.render(await raw.load());
    assert.equal(editor.dir,direction,locale+' raw direction');
    assert.equal(raw.editor.value,"config proxy_guard 'main'\n");
    assert(raw.editor.attrs.style.includes('direction:ltr'),locale+' UCI syntax remains LTR');
    assert.equal(raw.editor.dir,'ltr',locale+' decoration preserves the explicit raw editor direction');
    for(const key of ['Validate configuration','Load default template','Download configuration']) {
        assert(walk(editor).some(n=>n.children.includes(gettext(key))),locale+' raw action '+key);
    }
    const setup=load(basePath+'proxy_guard_setup.js');
    setup.info={wizard_complete:true};setup.view={showActionError(e){throw e;}};
    const button=key=>{
        const result=modal.body.flatMap(walk).find(n=>n.tag==='button'&&n.children[0]===gettext(key));
        assert(result,locale+' wizard button '+key);return result;
    };
    const titles=['LAN ingress devices','Protection preset','Scope and exceptions','Review settings'];
    const before=rpcCalls.length;await setup.open(false);
    for(let step=0;step<4;step++){
        assert.equal(setup.step,step);
        assert.equal(modal.title,gettext('Protection setup wizard')+' · \u2066'+(step+1)+' / 4\u2069 · '+gettext(titles[step]));
        assert.equal(modal.body[0].dir,direction);
        assert(!button(step===3?'Save & Apply':'Next').disabled);
        if(step===2){setup.ipv6Mode.value='none';setup.ipv6Acknowledge.checked=true;}
        if(step<3) await button('Next').attrs.click();
    }
    assert(rpcCalls.slice(before).every(name=>name==='setup_discover'),locale+' wizard remains draft only');
    setup.setTransaction({id:'test',token:'test-token',owned:true,phase:'confirming',remaining_ms:30000,verification:'blocked'},performance.now());
    setup.showTransaction();
    assert.equal(modal.title,gettext('Confirm protection settings'));assert(!setup.confirmButton.disabled);
    assert(setup.transactionMessage.textContent.includes(gettext('Protection rules verified. Internet access is blocked.')));
    setup.active.verification='unverified';setup.renderTransaction();assert(setup.confirmButton.disabled);
    assert(setup.transactionMessage.textContent.includes(gettext('Protection status needs verification. You can keep these settings once the check passes.')));
    return locale;
}
