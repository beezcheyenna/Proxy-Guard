import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {readFileSync} from 'node:fs';
import {createHmac} from 'node:crypto';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';

test('workerd egress route uses real Agent HMAC without source-IP or target input',async t=>{
 const child=spawn('python3',['-B',fileURLToPath(new URL('./agent_fixture.py',import.meta.url))],{stdio:['ignore','pipe','inherit']});
 const lines=createInterface({input:child.stdout});t.after(()=>{child.kill('SIGTERM');lines.close();});
 const [line]=await Promise.race([once(lines,'line'),once(child,'exit').then(([code])=>{throw Error('Agent fixture exited '+code);})]);
 const base='http://127.0.0.1:'+JSON.parse(line).port,seen=[];
 const {Miniflare,convertV4MiniflareOptions}=await import('miniflare');
 const mf=new Miniflare(convertV4MiniflareOptions({modules:true,script:readFileSync(new URL('../src/index.mjs',import.meta.url),'utf8'),
  compatibilityDate:'2026-10-30',bindings:{DEVICE_ID:'home',DEVICE_TOKEN:'d'.repeat(40),AGENT_SECRET:'a'.repeat(40)},
  serviceBindings:{VPS_API:async req=>{
   // Copy proxy-backed metadata before consuming the request body. The local
   // adapter must pass native Headers, not a Miniflare proxy lifetime, to fetch.
   const path=new URL(req.url).pathname,method=req.method,headers=new Headers(req.headers);
   const body=await req.text();const forwarded=new Headers();
   for(const key of ['content-type','x-pg-signature'])if(headers.has(key))forwarded.set(key,headers.get(key));
   const row={path,body,headers:Object.fromEntries(forwarded),diagnostics:{
    omitted_transport_headers:[...headers.keys()].filter(k=>!forwarded.has(k)),
    node_signature_matches:createHmac('sha256','a'.repeat(40)).update(body).digest('hex')===headers.get('x-pg-signature'),
    request_age_ms:Date.now()-JSON.parse(body).issued_at,request_keys:Object.keys(JSON.parse(body))}};seen.push(row);
   try {
    const response=await fetch(base+path,{method,headers:forwarded,body});
    const raw=await response.clone().text();let data;try{data=JSON.parse(raw);}catch{data={code:'non_json'};}
    Object.assign(row.diagnostics,{upstream_status:response.status,upstream_code:data.code});return response;
   }catch(error){Object.assign(row.diagnostics,{error:error.name,cause:error.cause?.code});throw error;}
  }}}));
 try{
  const headers={authorization:'Bearer '+'d'.repeat(40),'cf-connecting-ip':'1.1.1.1','content-type':'application/json'};
  const r=await mf.dispatchFetch('https://worker.example/v1/egress-info',{method:'POST',headers,body:JSON.stringify({device_id:'home'})});
  const body=await r.json();assert.equal(r.status,200,JSON.stringify({response:body,relay:seen.map(x=>x.diagnostics)}));assert.equal(body.egress_info_schema,1);
  assert.equal(body.business_egress_verified,false);assert.equal(seen.length,1);assert.equal(seen[0].path,'/v1/egress-info');
  const signed=JSON.parse(seen[0].body);assert.equal(signed.purpose,'egress-info');assert.equal(signed.device_id,'home');assert.equal(signed.observed_ip,undefined);
  const rejected=await mf.dispatchFetch('https://worker.example/v1/egress-info',{method:'POST',headers,body:JSON.stringify({device_id:'home',url:'http://127.0.0.1/'})});
  assert.equal(rejected.status,400);assert.equal(seen.length,1);
  const replay=await fetch(base+'/v1/status',{method:'POST',headers:seen[0].headers,body:seen[0].body});assert.equal(replay.status,400);
 }finally{await mf.dispose();}
});
