import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.mjs';
const token='d'.repeat(40),secret='a'.repeat(40),id='12345678-1234-4234-8234-123456789abc';
const command=()=>({action:'restart_xray',operation_id:id,revision:1,issued_at:Date.now()-100,expires_at:Date.now()+30000});
function fixture(path='/v1/command', data=command(), response=Response.json({ok:true,operation:{operation_id:id,action:'restart_xray',phase:'accepted'}})) {
 const calls=[]; const env={DEVICE_ID:'home',DEVICE_TOKEN:token,AGENT_SECRET:secret,VPS_API:{fetch:async(u,i)=>{calls.push([u,i]);return response;}}};
 const req=new Request('https://worker.example'+path,{method:'POST',headers:{authorization:'Bearer '+token,'cf-connecting-ip':'8.8.8.8','content-type':'application/json'},body:JSON.stringify(data)});
 return {env,req,calls};
}
test('command internal errors are sanitized and known denials survive',async()=>{
 for(const [status,body,code]of [[500,{ok:false,code:'secret-internal-address'},'command_result_unknown'],[403,{ok:false,code:'operation_or_authentication_denied',private:'private-marker'},'operation_or_authentication_denied'],[400,{ok:false,code:'operation_busy',private:'private-marker'},'operation_busy']]){
 const f=fixture('/v1/command',command(),Response.json(body,{status}));const r=await worker.fetch(f.req,f.env);assert.ok(r.status>=400);const result=await r.json();assert.equal(result.code,code);assert.ok(!JSON.stringify(result).includes('private-marker')); }
});
test('command validates upstream operation identity and phase',async()=>{
 for(const body of [{ok:true},{ok:true,operation:{operation_id:'wrong',action:'restart_xray',phase:'accepted'}},{ok:true,operation:{operation_id:id,action:'reboot_vps',phase:'accepted'}},{ok:true,operation:{operation_id:id,action:'restart_xray',phase:'made_up'}}]){
 const f=fixture('/v1/command',command(),Response.json(body));const r=await worker.fetch(f.req,f.env);assert.equal(r.status,502); }
});
test('accepted operation exports only public record fields',async()=>{
 const f=fixture('/v1/command',command(),Response.json({ok:true,private:'private-marker',operation:{operation_id:id,action:'restart_xray',phase:'accepted',boot:'private-marker',before:['private-marker']}}));
 const r=await worker.fetch(f.req,f.env);assert.equal(r.status,200);assert.ok(!(await r.text()).includes('private-marker'));
});
test('Agent operation window contract rejects future start and too-short windows before dispatch',async()=>{
 const now=Date.now();for(const data of [{...command(),issued_at:now+4000,expires_at:now+30000},{...command(),issued_at:now,expires_at:now+500},{...command(),operation_id:'-'.repeat(36)},{...command(),device_id:'wrong'}]){
 const f=fixture('/v1/command',data);const r=await worker.fetch(f.req,f.env);assert.equal(r.status,400);assert.equal(f.calls.length,0); }
});
test('upstream response is byte bounded while streaming and canceled',async()=>{
 let pulls=0,canceled=false;const stream=new ReadableStream({pull(c){pulls++;if(pulls>100)throw Error('read too far');c.enqueue(new Uint8Array(4096).fill(32));},cancel(){canceled=true;}});
 const f=fixture('/v1/command',command(),new Response(stream));const r=await worker.fetch(f.req,f.env);assert.equal(r.status,502);assert.ok(pulls<15);assert.equal(canceled,true);
});
test('malformed upstream response is backend error, never client error',async()=>{
 for(const path of ['/v1/command','/v1/status','/v1/sync']){
 const data=path.endsWith('sync')?{device_id:'home',observed_ip:'8.8.8.8',policy_enabled:true,rules:[],revision:1,ttl:900}:path.endsWith('command')?command():{};
 const f=fixture(path,data,new Response('private-marker'));const r=await worker.fetch(f.req,f.env);assert.equal(r.status,502);assert.ok(!(await r.text()).includes('private-marker')); }
});
test('status validates protocol and required health shape',async()=>{
 for(const body of [{ok:true,edition:'pro'},{ok:true,edition:'pro',protocol:2,agent_ready:true,revision:1,health:{configured:true,ok:true,stale:false},leases:{},ingress:{}}]){
 const f=fixture('/v1/status',{},Response.json(body));const r=await worker.fetch(f.req,f.env);assert.equal(r.status,502); }
});
test('same device and agent credential cannot enable deployment',async()=>{
 const f=fixture();f.env.AGENT_SECRET=token;const r=await worker.fetch(f.req,f.env);assert.equal(r.status,503);assert.equal(f.calls.length,0);
});
test('JSON suffix lookalike media type rejected',async()=>{
 const f=fixture();const req=new Request(f.req,{headers:{authorization:'Bearer '+token,'cf-connecting-ip':'8.8.8.8','content-type':'application/json-malicious'}});assert.equal((await worker.fetch(req,f.env)).status,415);
});

test('status strips unknown fields, manager addresses and optional analysis even when requested',async()=>{
 const body={ok:true,protocol:3,edition:'pro',agent_ready:true,revision:1,health:{configured:true,ok:true,stale:false,secret:'private-marker',services:[{name:'xray',ok:true,required:true,ports:{secret:'private-marker'}}]},leases:{'4':{expires_in:100,source:'private-marker'}},ingress:{enabled:true,mode:'standard',address_families:[4,6],ssh:{managed:false,managers:['private-marker']}},events:{secret:'private-marker'},inventory:{secret:'private-marker'},analysis_exported:true,secret:'private-marker',resources:{sources:['private-marker'],native_checks:{configured:true,ok:true,inbounds:['private-marker']}}};
 const f=fixture('/v1/status',{},Response.json(body));f.env.ALLOW_ANALYSIS_EXPORT='true';const r=await worker.fetch(f.req,f.env);assert.equal(r.status,200);const b=await r.json();assert.equal(b.analysis_exported,false);assert.ok(!JSON.stringify(b).includes('private-marker'));assert.equal(JSON.parse(f.calls[0][1].body).include_analysis,false);
});
