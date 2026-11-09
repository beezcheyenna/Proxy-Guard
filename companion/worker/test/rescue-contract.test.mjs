import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import worker from '../src/index.mjs';
test('unchanged Worker preserves zero and positive SSH windows through actual Agent HTTP',async t=>{
 const child=spawn('python3',['-B',fileURLToPath(new URL('./agent_fixture.py',import.meta.url))],{stdio:['ignore','pipe','inherit']});
 const lines=createInterface({input:child.stdout});t.after(()=>{child.kill('SIGTERM');lines.close();});
 const [line]=await Promise.race([once(lines,'line'),once(child,'exit').then(([c])=>{throw Error('Agent exited '+c);})]);
 const base='http://127.0.0.1:'+JSON.parse(line).port,token='d'.repeat(40);
 const env={DEVICE_ID:'home',DEVICE_TOKEN:token,AGENT_SECRET:'a'.repeat(40),VPS_API:{fetch:(url,init)=>fetch(base+new URL(url).pathname,init)}};
 const send=(path,body)=>worker.fetch(new Request('https://worker.example'+path,{method:'POST',headers:{authorization:'Bearer '+token,'cf-connecting-ip':'8.8.8.8','content-type':'application/json'},body:JSON.stringify(body)}),env);
 let revision=1;
 for(const seconds of [0,600,30,3600,0]){
  const policy={device_id:'home',observed_ip:'8.8.8.8',policy_enabled:true,mode:'whitelist',rules:[],revision:++revision,ttl:120,ssh:{managed:false,open_seconds:seconds,managers:['1.1.1.1/32']}};
  const response=await send('/v1/sync',policy),value=await response.json();
  assert.equal(response.status,200,JSON.stringify(value));assert.equal(value.policy.ssh.open_seconds,seconds);
  assert.ok(!JSON.stringify(value).includes('1.1.1.1/32'));
  const status=await(await send('/v1/status',{})).json();
  assert.equal(status.ingress.ssh.open_seconds,seconds);
 }
 const invalid=await send('/v1/sync',{device_id:'home',observed_ip:'8.8.8.8',policy_enabled:true,mode:'whitelist',rules:[],revision:++revision,ttl:120,ssh:{open_seconds:29}});
 assert.ok(invalid.status>=400);
});
