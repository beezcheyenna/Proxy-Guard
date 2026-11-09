import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import worker,{sign} from '../src/index.mjs';
const token='d'.repeat(40),secret='a'.repeat(40);
const snapshot=()=>({ok:true,protocol:3,egress_info_schema:1,generated_at:1700000000,status:'available',
  candidates:[{ipv4:'8.8.8.8',evidence:[{source:'interface',checked_at:1700000000,scope:'host_interface'}]}],
  ambiguous:false,business_egress_verified:false,warnings:['measurement_disabled'],
  measurement:{state:'disabled',checked_at:null,stale:true}});
function fixture(body={device_id:'home'},upstream=()=>Response.json(snapshot()),headers={}) {
 const calls=[];const env={DEVICE_ID:'home',DEVICE_TOKEN:token,AGENT_SECRET:secret,
  VPS_API:{fetch:async(u,i)=>{calls.push({u,i});return upstream();}}};
 const request=new Request('https://worker.example/v1/egress-info',{method:'POST',
  headers:{authorization:'Bearer '+token,'cf-connecting-ip':'1.1.1.1','content-type':'application/json',...headers},body:JSON.stringify(body)});
 return {env,request,calls};
}
test('egress signs a purpose-bound read-only fixed relay, never caller source IP',async()=>{
 const f=fixture();const r=await worker.fetch(f.request,f.env);assert.equal(r.status,200);const b=await r.json();
 assert.equal(b.candidates[0].ipv4,'8.8.8.8');assert.equal(b.business_egress_verified,false);assert.match(r.headers.get('cache-control'),/no-store/);
 assert.equal(f.calls[0].u,'http://vps-agent.internal/v1/egress-info');const raw=f.calls[0].i.body;const data=JSON.parse(raw);
 assert.deepEqual(Object.keys(data).sort(),['device_id','issued_at','purpose','request_id']);assert.equal(data.purpose,'egress-info');
 assert.equal(f.calls[0].i.headers['x-pg-signature'],await sign(secret,raw));assert.ok(!raw.includes('1.1.1.1'));
});
test('egress device auth and exact body reject before VPC work',async()=>{
 for(const [body,headers]of [[{device_id:'home'},{authorization:'Bearer wrong'}],[{device_id:'other'},{}],[{},{}],[[],{}],
  [{device_id:'home',url:'http://localhost'},{}],[{device_id:'home',observed_ip:'1.1.1.1'},{}],
  [{device_id:'home',command:'id'},{}],[{device_id:'home'},{'cf-worker':'other.example'}]]){
  const f=fixture(body,undefined,headers);const r=await worker.fetch(f.request,f.env);assert.ok(r.status>=400);assert.equal(f.calls.length,0);
 }
});
test('egress exports only explicit source evidence and safe fields',async()=>{
 const v=snapshot();v.secret='private-marker';v.candidates[0].token='private-marker';v.candidates[0].evidence[0].path='private-marker';v.measurement.url='private-marker';
 const f=fixture(undefined,()=>Response.json(v));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,200);assert.ok(!(await r.text()).includes('private-marker'));
});
test('private, reserved, IPv6 and noncanonical upstream IPv4 candidates are backend errors',async()=>{
 for(const ip of ['127.0.0.1','10.0.0.1','100.64.1.1','192.0.2.1','192.88.99.1','198.51.100.1','203.0.113.1',
  '224.0.0.1','240.0.0.1','008.8.8.8','8.8.8.8:443','::ffff:8.8.8.8','2606:4700::1111']){
  const v=snapshot();v.candidates[0].ipv4=ip;const f=fixture(undefined,()=>Response.json(v));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,502,ip);
 }
});
test('egress validates provenance bounds and never certifies the business egress',async()=>{
 for(const mutate of [v=>v.business_egress_verified=true,v=>v.candidates[0].evidence[0].source='reality',
  v=>v.candidates[0].evidence[0].source={toString:'bad'},v=>v.candidates[0].evidence[0].scope='business',
  v=>v.candidates[0].evidence[0].checked_at='now',v=>v.warnings=['secret raw warning'],
  v=>v.candidates=Array(9).fill(v.candidates[0]),v=>v.candidates[0].evidence=Array(4).fill(v.candidates[0].evidence[0]),
  v=>v.measurement.state='made_up',v=>v.egress_info_schema=2]){
  const v=snapshot();mutate(v);const f=fixture(undefined,()=>Response.json(v));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,502);
 }
});
test('empty NAT and ambiguous snapshots are advisory, not failed service status',async()=>{
 for(const v of [{...snapshot(),status:'unavailable',candidates:[],warnings:['no_public_ipv4_candidate','measurement_disabled']},
  {...snapshot(),status:'partial',ambiguous:true,candidates:[snapshot().candidates[0],{ipv4:'9.9.9.9',evidence:[{source:'panel',scope:'panel_config',checked_at:1700000000}]}],warnings:['multiple_public_ipv4_candidates']}]){
  const f=fixture(undefined,()=>Response.json(v));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,200);assert.equal((await r.json()).business_egress_verified,false);
 }
});
test('old Agent, missing VPC, upstream exceptions and error pages stay safe',async()=>{
 for(const [status,expected]of [[404,501],[501,501],[401,502],[500,502]]){
  const f=fixture(undefined,()=>new Response('private-marker',{status}));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,expected);assert.ok(!(await r.text()).includes('private-marker'));
 }
 const f=fixture(undefined,()=>{throw Error('private-marker')});const r=await worker.fetch(f.request,f.env);assert.equal(r.status,502);assert.ok(!(await r.text()).includes('private-marker'));
 const missing=fixture();delete missing.env.VPS_API;assert.equal((await worker.fetch(missing.request,missing.env)).status,503);
});
test('malformed and oversized egress upstream data are bounded backend errors',async()=>{
 for(const raw of ['not json',' '.repeat(40000)]){
  const f=fixture(undefined,()=>new Response(raw));const r=await worker.fetch(f.request,f.env);assert.equal(r.status,502);
 }
});
test('egress actual Agent HTTP contract authenticates and rejects signed cross-path replay',async t=>{
 const child=spawn('python3',['-B',fileURLToPath(new URL('./agent_fixture.py',import.meta.url))],{stdio:['ignore','pipe','inherit']});
 const lines=createInterface({input:child.stdout});t.after(()=>{child.kill('SIGTERM');lines.close();});
 const [line]=await Promise.race([once(lines,'line'),once(child,'exit').then(([code])=>{throw Error('Agent fixture exited '+code);})]);
 const info=JSON.parse(line);const base='http://127.0.0.1:'+info.port;const f=fixture();
 f.env.VPS_API.fetch=async(url,init)=>{f.calls.push({u:url,i:init});return fetch(base+new URL(url).pathname,init);};
 const r=await worker.fetch(f.request,f.env);const data=await r.json();assert.equal(r.status,200,JSON.stringify(data));assert.equal(data.egress_info_schema,1);
 assert.equal(data.business_egress_verified,false);assert.ok(!JSON.stringify(data).includes('10.0.2.15'));
 const call=f.calls.at(-1);assert.equal((await fetch(base+'/v1/egress-info',call.i)).status,403);
 assert.equal((await fetch(base+'/v1/status',call.i)).status,400);
});
