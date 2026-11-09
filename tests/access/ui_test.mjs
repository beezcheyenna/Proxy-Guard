import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../../package/root/www/luci-static/resources/view/proxy-guard/access.js',import.meta.url),'utf8');
function fixture() {
 const calls=[],options=[];
 const node=()=>({className:'',replaceChildren(){}});
 const E=()=>node();
 const map={save:async()=>calls.push('stage'),reset:async()=>{},
  render:async()=>node(),section(){return {option(type,key,...rest){const o={key,value(){},depends(){}};options.push(o);return o;}}}};
 const form={Map:function(){return map},NamedSection:1,GridSection:2,Flag:3,Value:4,ListValue:5,DynamicList:6};
 const rpc={declare(spec){return async()=>{calls.push(spec.method);return spec.method==='status'?{phase:'disabled'}:{ok:true};}}};
 const uci={load:async()=>{},set(){},unset(){}};
 const ui={changes:{init:async()=>calls.push('changes')},addNotification:()=>calls.push('error')};
 const poll={add(){}};
 const view={extend(o){return o;}};
 const module=new Function('view','form','uci','rpc','ui','poll','E','_',source)(view,form,uci,rpc,ui,poll,E,x=>x);
 return {module,calls,options};
}
test('render and editing do not apply; Save only stages; Save & Apply invokes exactly the access RPC',async()=>{
 const f=fixture();await f.module.render();await Promise.resolve();
 assert.equal(f.calls.includes('apply'),false);
 await f.module.handleSave();assert.equal(f.calls.filter(x=>x==='stage').length,1);assert.equal(f.calls.includes('apply'),false);
 await f.module.handleSaveApply();assert.equal(f.calls.filter(x=>x==='apply').length,1);assert.equal(f.calls.includes('changes'),true);
});
test('secret is never loaded from readable UCI and defaults preserve SSH semantics',async()=>{
 const f=fixture();await f.module.render();
 const key=f.options.find(x=>x.key==='device_token');assert.equal(key.password,true);assert.equal(key.cfgvalue(),'');
 const cfg=fs.readFileSync(new URL('../../package/root/etc/config/proxy_guard_access',import.meta.url),'utf8');
 assert.match(cfg,/config rule 'ssh'[\s\S]*option enabled '1'[\s\S]*list ports '22'[\s\S]*option source_mode 'any'/);
 assert.doesNotMatch(cfg,/device_token/);
 assert.equal(f.options.find(x=>x.key==='policy_enabled').default,'1');
});
