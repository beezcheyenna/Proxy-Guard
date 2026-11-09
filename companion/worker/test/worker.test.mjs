import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {publicIP, sign} from '../src/index.mjs';
const token = 'd'.repeat(40), secret = 'a'.repeat(40);
function fixture() {
  const calls = [];
  const env = { DEVICE_ID:'home', DEVICE_TOKEN:token, AGENT_SECRET:secret,
    VPS_API:{async fetch(url, init) {
      calls.push({url,init});
      const input = JSON.parse(init.body);
      assert.equal(init.headers['x-pg-signature'], await sign(secret, init.body));
      return Response.json({ok:true,protocol:3,policy:{enabled:true,default_deny:false,auto_discover:false,address_families:[4,6],mode:'standard',ssh:{}},observed_ip:input.observed_ip,expires_at:123,applied_at:120,policy_hash:'a'.repeat(64)});
    }}
  };
  const data = { device_id:'home', observed_ip:'8.8.8.8', policy_enabled:true,
    revision:1, ttl:900, rules:[] };
  const req = (path='/v1/sync', extra={}) => new Request('https://worker.example'+path, {
    method:path==='/v1/observe'?'GET':'POST',
    headers:{authorization:'Bearer '+token,'content-type':'application/json','cf-connecting-ip':'8.8.8.8',...extra.headers},
    ...(path==='/v1/observe'?{}:{body:JSON.stringify({...data,...extra.data})})
  });
  return {env,calls,data,req};
}
test('source observed at Cloudflare, fixed VPC binding, separate agent signature, safe acknowledgement',async()=>{
  const f=fixture();const response=await worker.fetch(f.req(),f.env);
  assert.equal(response.status,200);assert.equal((await response.json()).observed_ip,'8.8.8.8');
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].url,'http://vps-agent.internal/v1/sync');
  assert.ok(!f.calls[0].init.body.includes(token));
});
test('observe does not update VPS',async()=>{
  const f=fixture();const r=await worker.fetch(f.req('/v1/observe'),f.env);
  assert.deepEqual(await r.json(),{ok:true,observed_ip:'8.8.8.8',family:4});assert.equal(f.calls.length,0);
});
test('forged source and configuration revision rejected before relay',async()=>{
  for(const data of [{observed_ip:'1.1.1.1'},{revision:0},{revision:1.5},{ttl:1},{ttl:86401},{device_id:'other'},{rules:Array(33).fill({})}]) {
    const f=fixture();const r=await worker.fetch(f.req('/v1/sync',{data}),f.env);
    assert.ok(r.status>=400);assert.equal(f.calls.length,0);
  }
});
test('no auth, another token, Worker subrequest and local source cannot enroll',async()=>{
  for(const headers of [{authorization:''},{authorization:'Bearer '+secret},{'cf-worker':'attacker.example'},{'cf-connecting-ip':'127.0.0.1'},{'cf-connecting-ip':'2a06:98c0:3600::103'}]) {
    const f=fixture();const r=await worker.fetch(f.req('/v1/sync',{headers}),f.env);
    assert.ok(r.status>=400);assert.equal(f.calls.length,0);
  }
});
test('IPv6 normalization and reserved addresses',()=>{
  assert.equal(publicIP('2606:4700:4700:0000:0000:0000:0000:1111'),'2606:4700:4700::1111');
  for(const ip of ['::1','fc00::1','fe80::1','ff02::1','2001:db8::1','::ffff:8.8.8.8',':::','8.8.8.8;id','100.64.1.1','192.168.1.1','203.0.113.1','300.1.1.1'])
    assert.throws(()=>publicIP(ip),ip);
});
test('unavailable binding or backend is explicit and never bypasses authentication',async()=>{
  for(const backend of [undefined,{fetch:async()=>{throw Error('private details')}},{fetch:async()=>new Response('secret',{status:500})}]) {
    const f=fixture();f.env.VPS_API=backend;
    const r=await worker.fetch(f.req(),f.env);assert.ok(r.status>=500);
    assert.ok(!(await r.text()).includes('private details'));
  }
});
test('oversized or malformed input and query paths are rejected',async()=>{
  const f=fixture();
  for(const request of [
    new Request('https://worker.example/v1/sync',{method:'POST',headers:{authorization:'Bearer '+token,'cf-connecting-ip':'8.8.8.8','content-type':'application/json'},body:'x'.repeat(25000)}),
    f.req('/v1/sync?destination=http://evil'),
    f.req('/other')
  ]) assert.ok((await worker.fetch(request,f.env)).status>=400);
  assert.equal(f.calls.length,0);
});

test('example secrets cannot accidentally enable a deployment',async()=>{
 const f=fixture();f.env.DEVICE_TOKEN='REPLACE_WITH_RANDOM_DEVICE_SECRET_AT_LEAST_32_CHARACTERS';
 const r=await worker.fetch(f.req(),f.env);assert.equal(r.status,503);assert.equal(f.calls.length,0);
});
