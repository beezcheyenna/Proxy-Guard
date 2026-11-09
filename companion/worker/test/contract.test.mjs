import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {readFileSync} from 'node:fs';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import worker,{sign} from '../src/index.mjs';
const token='d'.repeat(40),secret='a'.repeat(40);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
test('Worker to actual Pro Agent v3 HTTP contract in isolated VM',async t=>{
 const child=spawn('python3',['-B',fileURLToPath(new URL('./agent_fixture.py',import.meta.url))],{stdio:['ignore','pipe','inherit']});
 const lines=createInterface({input:child.stdout}); t.after(()=>{child.kill('SIGTERM');lines.close();}); const [line]=await Promise.race([once(lines,'line'),once(child,'exit').then(([code])=>{throw Error('Agent fixture exited '+code);})]);const info=JSON.parse(line);const base='http://127.0.0.1:'+info.port;
 const calls=[];
 const env={DEVICE_ID:'home',DEVICE_TOKEN:token,AGENT_SECRET:secret,ALLOW_ANALYSIS_EXPORT:'true',VPS_API:{fetch:async(url,init)=>{calls.push({url,init});return fetch(base+new URL(url).pathname,init);}}};
 let ip='8.8.8.8';
 const send=(path,data={},headers={})=>worker.fetch(new Request('https://worker.example'+path,{method:path==='/v1/observe'?'GET':'POST',headers:{authorization:'Bearer '+token,'cf-connecting-ip':ip,'content-type':'application/json',...headers},...(path==='/v1/observe'?{}:{body:JSON.stringify(data)})}),env);
 const rule={id:'selected',name:'Fixture',enabled:true,protocol:'tcp',ports:['18443'],source_mode:'dynamic',sources:[]};
 let policy={device_id:'home',observed_ip:ip,policy_enabled:true,mode:'whitelist',ssh:{managers:['1.1.1.0/24']},rules:[rule],revision:2,ttl:120};
 let raw;
 await t.test('IPv4 policy signed across real HTTP and bounded lease acknowledged',async()=>{
  const r=await send('/v1/sync',policy);const b=await r.json();assert.equal(r.status,200,JSON.stringify(b));assert.equal(b.protocol,3);assert.equal(b.policy.mode,'whitelist');assert.ok(b.expires_at>b.applied_at && b.expires_at-b.applied_at<=120);assert.ok(!JSON.stringify(b).includes('1.1.1.0/24'));raw=calls.at(-1);
 });
 await t.test('signed replay and tampering rejected by Agent without renewal',async()=>{
  const replay=await fetch(base+'/v1/sync',{...raw.init,signal:AbortSignal.timeout(8000)});assert.equal(replay.status,400);assert.equal((await replay.json()).code,'replayed_or_stale_request');
  const changed={...raw.init,signal:AbortSignal.timeout(8000),body:raw.init.body.replace('8.8.8.8','9.9.9.9')};assert.equal((await fetch(base+'/v1/sync',changed)).status,403);
 });
 await t.test('lower revision and same revision policy mutation rejected',async()=>{
  for(const data of [{...policy,revision:1},{...policy,mode:'observe'}])assert.equal((await send('/v1/sync',data)).status,502);
 });
 await t.test('same revision renewal allowed and IPv6 leases independent',async()=>{
  assert.equal((await send('/v1/sync',policy)).status,200);ip='2606:4700:4700::1111';policy={...policy,observed_ip:ip};assert.equal((await send('/v1/sync',policy)).status,200);
  const r=await send('/v1/status');const b=await r.json();assert.equal(r.status,200,JSON.stringify(b));assert.ok(b.leases['4'].expires_in>0);assert.ok(b.leases['6'].expires_in>0);assert.equal(b.revision,2);assert.equal(b.analysis_exported,false);assert.ok(!JSON.stringify(b).includes('1.1.1.0/24'));assert.equal(b.inventory,undefined);assert.equal(b.events,undefined);assert.equal(b.resources.sources,undefined);assert.equal(JSON.parse(calls.at(-1).init.body).include_analysis,false);
 });
 await t.test('signed status nonce replay and expired signed requests rejected',async()=>{
  const last=calls.at(-1);assert.equal((await fetch(base+'/v1/status',{...last.init,signal:AbortSignal.timeout(8000)})).status,403);
  for(const path of ['/v1/sync','/v1/status']){const body=JSON.stringify({...policy,issued_at:Date.now()-180000,request_id:crypto.randomUUID()});const r=await fetch(base+path,{method:'POST',headers:{'x-pg-signature':await sign(secret,body)},body});assert.ok(r.status>=400);}
 });
 await t.test('device authentication and Cloudflare source gates precede private HTTP',async()=>{
  const count=calls.length;for(const headers of [{authorization:'Bearer wrong'},{'cf-worker':'other.example'},{'cf-connecting-ip':'127.0.0.1'}])assert.ok((await send('/v1/sync',policy,headers)).status>=400);assert.equal(calls.length,count);
 });
 const operation_id=crypto.randomUUID();const cmd=()=>({device_id:'home',operation_id,action:'restart_xray',revision:2,issued_at:Date.now()-50,expires_at:Date.now()+30000});
 await t.test('fixed maintenance dispatch recorded once, verified and deduplicated',async()=>{
  const r=await send('/v1/command',cmd());const b=await r.json();assert.equal(r.status,200,JSON.stringify(b));assert.equal(b.operation.operation_id,operation_id);await pause(2500);
  const status=await(await send('/v1/status')).json();assert.equal(status.maintenance.operations.at(-1).phase,'complete');assert.equal((await send('/v1/command',cmd())).status,200);await pause(1200);assert.deepEqual(JSON.parse(readFileSync(info.directory+'/dispatches.json')),['restart_xray']);assert.equal((await send('/v1/command',{...cmd(),action:'reboot_vps'})).status,400);
 });
 await t.test('Agent-side disabled reboot is denied without dispatch',async()=>{assert.equal((await send('/v1/command',{...cmd(),operation_id:crypto.randomUUID(),action:'reboot_vps'})).status,403);});
 await t.test('arbitrary commands, expired operations and stale revision cannot dispatch',async()=>{
  for(const change of [{action:'sh -c id'},{issued_at:Date.now()-50000,expires_at:Date.now()-1000},{revision:1}])assert.ok((await send('/v1/command',{...cmd(),...change})).status>=400);assert.deepEqual(JSON.parse(readFileSync(info.directory+'/dispatches.json')),['restart_xray']);
 });
 await t.test('Miniflare/workerd uses the same actual Agent HTTP contract',async()=>{
  const {Miniflare,convertV4MiniflareOptions}=await import('miniflare');const mf=new Miniflare(convertV4MiniflareOptions({modules:true,script:readFileSync(new URL('../src/index.mjs',import.meta.url),'utf8'),compatibilityDate:'2026-10-30',bindings:{DEVICE_ID:'home',DEVICE_TOKEN:token,AGENT_SECRET:secret},serviceBindings:{VPS_API:async req=>fetch(base+new URL(req.url).pathname,{method:req.method,headers:req.headers,body:await req.text()})}}));
  try{const headers={authorization:'Bearer '+token,'cf-connecting-ip':'8.8.8.8','content-type':'application/json'};const observation=await(await mf.dispatchFetch('https://worker.example/v1/observe',{headers})).json();assert.equal(observation.ok,true,JSON.stringify(observation));const synced=await mf.dispatchFetch('https://worker.example/v1/sync',{method:'POST',headers,body:JSON.stringify({...policy,observed_ip:observation.observed_ip,revision:3})});assert.equal(synced.status,200,await synced.text());const status=await mf.dispatchFetch('https://worker.example/v1/status',{method:'POST',headers,body:'{}'});const data=await status.json();assert.equal(status.status,200,JSON.stringify(data));assert.equal(data.protocol,3);assert.equal(data.analysis_exported,false);assert.equal((await mf.dispatchFetch('https://worker.example/v1/observe')).status,401);}finally{await mf.dispose();}
 });
});
