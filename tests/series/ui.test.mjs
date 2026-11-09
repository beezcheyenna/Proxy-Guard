import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const root=new URL('../../',import.meta.url);
function load(path,call,extra={}){
 const source=fs.readFileSync(new URL(path,root),'utf8');
 const ctx={view:{extend:x=>x},rpc:{declare:()=>call,getSessionID:()=>'a'.repeat(32)},poll:{add:()=>{}},
  _:x=>x,E:(tag,attrs={},children=[])=>({tag,attrs,children,textContent:'',classList:{add(){}},querySelectorAll(){return[];},replaceChildren(...x){this.children=x;},appendChild(x){this.children.push(x);return x;}}),
  ui:{changes:{init:async()=>{}},addNotification:()=>{},showIndicator:()=>{},hideIndicator:()=>{}},uci:{},form:{},pgTrial:{begin:()=>Promise.resolve(),attach:()=>Promise.resolve()},pgRemoteTrial:{begin:()=>Promise.resolve(),attach:()=>Promise.resolve()},URL,Blob,Date,setTimeout,Promise,JSON,performance};
 Object.assign(ctx,extra);
 ctx.baseclass={extend:x=>x};
 const i18n=fs.readFileSync(new URL('package/root/www/luci-static/resources/proxy_guard_i18n.js',root),'utf8');
 ctx.pgI18n=vm.runInNewContext('(function(){'+i18n+'\n})()',ctx);
 return vm.runInNewContext('(function(){'+source+'\n})()',ctx);
}
test('Pro Save only stages the form',async()=>{
 let saved=0,applied=0;
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>{applied++;return{ok:true};});
 v.map={save:async()=>saved++};await v.handleSave();
 assert.equal(saved,1);assert.equal(applied,0);
});
test('Pro Save and Apply commits through the explicit RPC action',async()=>{
 let saved=0,applied=0,refreshed=0;
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>{applied++;return{ok:true};});
 v.map={save:async()=>saved++};v.refresh=async()=>refreshed++;
 await v.handleSaveApply();assert.equal(saved,1);assert.equal(applied,1);assert.equal(refreshed,1);
});
test('Pro offers only explicit selected-port service rules',async()=>{
  const fields=[],sections=[];
  class Map {
    section(type,...args){
      sections.push(args);
      return {option(kind,name){fields.push(name);return {value(){},depends(){}};}};
    }
    render(){return Promise.resolve({});}
  }
  const form={Map,NamedSection:{},GridSection:{},Flag:{},Value:{},ListValue:{},DynamicList:{}};
  const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>({ok:true}),{form});
  v.refresh=async()=>{};await v.render();
  assert.ok(fields.includes('ports')&&fields.includes('source_mode'));
  assert.ok(!fields.includes('default_deny')&&!fields.includes('auto_discover'));
  assert.ok(sections.some(s=>String(s.at(-1)).includes('Other ports keep the existing system firewall')));
});

test('Pro maintenance uses the HTTP ubus session context without a reserved parameter',async()=>{
 const calls=[];const sid='b'.repeat(32);
 const rpc={getSessionID:()=>sid,declare:options=>async(...args)=>{calls.push({method:options.method,params:options.params,args});return{ok:true};}};
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>({ok:true}),{rpc});
 v.refresh=async()=>{};await v.sendAction('restart_xray');
 assert.equal(calls.length,1);assert.equal(calls[0].method,'restart_xray');assert.equal(calls[0].args.length,0);assert.equal(calls[0].params,undefined);
});
test('Pro preview parses fields without saving or invoking Apply',async()=>{
 let parsed=0;const calls=[];const dialogs=[];
 const uci={get:()=> 'standard',sections:(name,type,fn)=>fn({'.name':'proxy',name:'Example',enabled:'1',protocol:'tcp',ports:['443'],source_mode:'dynamic',sources:[]})};
 const ui={showModal:(title,nodes)=>dialogs.push({title,nodes}),hideModal(){},addNotification(){}};
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>{calls.push(1);return{ok:true};},{uci,ui});
 v.map={parse:async()=>parsed++,save:()=>{throw new Error('unexpected save');}};await v.previewRules();
 assert.equal(parsed,1);assert.equal(calls.length,0);assert.equal(dialogs.length,1);
});

test('Pro rejects failed or unknown status instead of showing waiting success',async()=>{
 for(const result of [{ok:false,error:'secret-error'},{phase:'not-a-real-phase'}]) {
  const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>result);
  v.status={replaceChildren(...nodes){this.nodes=nodes;}};v.actionButtons={restart_xray:{disabled:false}};
  await v.refresh();assert.equal(v.status.className,'alert-message warning');assert.equal(v.actionButtons.restart_xray.disabled,true);
  assert.ok(!JSON.stringify(v.status.nodes).includes('secret-error'));
 }
});
test('Pro serializes slow status RPCs and marks stale state while waiting',async()=>{
 let release,calls=0;const delayed=new Promise(resolve=>release=resolve);
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>{calls++;await delayed;return{phase:'synced'};});
 v.status={replaceChildren(...nodes){this.nodes=nodes;}};v.statusUpdatedAt=performance.now()-11000;
 const a=v.refresh(),b=v.refresh();assert.equal(a,b);assert.equal(calls,1);assert.equal(v.status.className,'alert-message warning');
 release();await a;assert.equal(v.status.className,'alert-message notice');assert.equal(v.statusRequest,null);
});

test('Pro rescue duration zero remains a draft and warns about expiry and panel ports',async()=>{
 const fields=new Map(),sections=[];
 class FormMap {
  section(type,...args){sections.push(args);return {option(kind,name){const item={value(){},depends(){}};fields.set(name,item);return item;}};}
  render(){return Promise.resolve({});}
 }
 const form={Map:FormMap,NamedSection:{},GridSection:{},Flag:{},Value:{},ListValue:{},DynamicList:{}};
 let calls=0;
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>{calls++;return{ok:true};},{form});
 v.refresh=async()=>{};await v.render();
 const duration=fields.get('ssh_open_seconds');
 assert.equal(duration.default,'0');
 for(const x of ['0','30','600','3600'])assert.equal(duration.validate('main',x),true);
 for(const x of ['','-1','1','29','3601','30.5','abc'])assert.notEqual(duration.validate('main',x),true);
 assert.match(duration.description,/lose SSH access/);assert.match(duration.description,/SSH authentication/);
 assert.ok(sections.some(x=>String(x.at(-1)).includes('subscription port filters that service too')));
 assert.equal(calls,0);
});
test('Pro rescue status explains unlimited access with direct or unchanged Worker metadata',async()=>{
 for(const direct of [false,true]){
  const result={phase:'synced',remote_health:{ok:true,remote:{ssh_rescue:{managed:true,armed:true,emergency:true,effective_scope:'public',public_remaining:0,...(direct?{public_unlimited:true}:{})},ingress:{ssh:{open_seconds:0}}}}};
  const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>result);
  v.status={replaceChildren(...nodes){this.nodes=nodes;}};await v.refresh();
  const text=JSON.stringify(v.status.nodes);
  assert.match(text,/Open until household authorization is restored/);
  assert.ok(!text.includes('Public access remaining'));
 }
});

test('Pro per-port modes inherit old defaults and expose exactly three independent choices',async()=>{
 const fields=[];
 class Map {section(type,...args){return {option(kind,name){const o={section:args[0],name,choices:[],value(k,v){this.choices.push(k);},depends(){}};fields.push(o);return o;}};}render(){return Promise.resolve({});}}
 const form={Map,NamedSection:{},GridSection:{},Flag:{},Value:{},ListValue:{},DynamicList:{}};
 const v=load('package/pro/root/www/luci-static/resources/view/proxy-guard/access.js',async()=>({ok:true}),{form});v.refresh=async()=>{};await v.render();
 const global=fields.find(f=>f.section==='main'&&f.name==='protection_mode'),port=fields.find(f=>f.section==='rule'&&f.name==='protection_mode');
 assert.equal(global.default,'standard');assert.equal(port.default,'inherit');assert.deepEqual(port.choices,['inherit','whitelist','standard','observe']);
 for(const name of ['rate_enabled','connections_enabled','bandwidth_enabled','rate','burst','connections','bandwidth','sustain','cooldown','window'])assert.ok(fields.some(f=>f.section==='rule'&&f.name===name));
});

function rawFixture(pro=true,{invalid=false,concurrent=false,delayed=false}={}){
 const calls=[],notifications=[];let infos=0,saved=0,release;const delay=delayed?new Promise(r=>release=r):Promise.resolve();
 const data={main:{'.name':'main','.type':pro?'access':'proxy_guard',enabled:'0',device_token:'private-existing',obsolete:'old'}};
 const info=()=>({ok:true,text:saved?(concurrent?'OTHER':'NEW'):'OLD',token:'token-'+(++infos),template:'DEFAULT',secret_marker:'__KEEP_SAVED_SECRET__'});
 const rpc={declare:spec=>async(...args)=>{
  calls.push({object:spec.object,method:spec.method,args});
  if(spec.method==='raw_info')return info();
  if(spec.method==='raw_parse'){await delay;return invalid?{ok:false,error:'raw_syntax_invalid'}:{ok:true,text:'NEW',sections:{main:{section_type:pro?'access':'proxy_guard',options:{enabled:'0',device_token:'__KEEP_SAVED_SECRET__'}}}};}
  if(spec.method==='apply')return {ok:true,confirmation_required:!pro,transaction:{id:'trial'}};
 }};
 const uci={load:async()=>{},unload(){},sections:(cfg,type,fn)=>Object.values(data).forEach(fn),get:(cfg,id)=>data[id],remove:(cfg,id)=>delete data[id],add:(cfg,type,id)=>data[id]={'.name':id,'.type':type},set:(cfg,id,key,value)=>{data[id][key]=value;},unset:(cfg,id,key)=>delete data[id][key],save:async()=>{saved++;}};
 const ui={changes:{init:async()=>{}},showIndicator(){},hideIndicator(){},addNotification:(...args)=>notifications.push(args)};
 const pgSetup={attach(){},begin(r){calls.push({method:'confirmation',result:r});}};
 const pgRemoteTrial={attach(){},begin(r){calls.push({method:'remote_confirmation',result:r});return Promise.resolve();}};
 const v=load('package/root/www/luci-static/resources/view/proxy-guard/raw.js',async()=>{}, {rpc,uci,ui,pgSetup,pgRemoteTrial,window:{location:{pathname:'/cgi-bin/luci/admin/services/'+(pro?'proxy-guard-access-raw':'proxy-guard-raw')}},TextEncoder});
 return {v,calls,notifications,data,info,saved:()=>saved,release:()=>release&&release()};
}
test('Pro raw editor Save stages the complete own configuration and preserves masked secrets',async()=>{
 const f=rawFixture();await f.v.render(await f.v.load());f.v.editor.value='NEW';f.v.updateDraftIndicator();
 assert.equal(f.calls.filter(c=>c.method==='apply').length,0);
 await f.v.handleSave();assert.equal(f.saved(),1);assert.equal(f.data.main.device_token,'private-existing');assert.equal(f.data.main.obsolete,undefined);
 assert.equal(f.calls.filter(c=>c.method==='apply').length,0);assert.equal(f.notifications.length,0);
 assert.ok(f.calls.every(c=>!c.object||c.object==='proxy_guard_access'));
});
test('Pro and local raw editors Apply use only their fixed scope and retain the confirmation flow',async()=>{
 for(const pro of [true,false]){
  const f=rawFixture(pro);await f.v.render(await f.v.load());f.v.editor.value='NEW';await f.v.handleSaveApply();
  const call=f.calls.find(c=>c.method==='apply');assert.ok(call);assert.equal(call.object,pro?'proxy_guard_access':'proxy_guard');
  assert.deepEqual(call.args,pro?['token-2']:[true,'token-2']);assert.equal(f.calls.filter(c=>c.method==='confirmation').length,pro?0:1);assert.equal(f.calls.filter(c=>c.method==='remote_confirmation').length,pro?1:0);
 }
});
test('Pro raw editor rejects invalid or competing changes before applying and retains the draft',async()=>{
 for(const opts of [{invalid:true},{concurrent:true}]){
  const f=rawFixture(true,opts);await f.v.render(await f.v.load());f.v.editor.value='NEW';await f.v.handleSaveApply();
  assert.equal(f.calls.filter(c=>c.method==='apply').length,0);assert.equal(f.v.editor.value,'NEW');assert.equal(f.notifications.length,1);
  if(opts.invalid)assert.equal(f.saved(),0);
 }
});

test('Pro raw editor protects the draft while an asynchronous Save is in progress',async()=>{
 const f=rawFixture(true,{delayed:true});await f.v.render(await f.v.load());f.v.editor.value='NEW';const promise=f.v.handleSave();
 assert.equal(f.v.editor.readOnly,true);f.release();await promise;assert.equal(f.v.editor.readOnly,false);assert.equal(f.saved(),1);
});
