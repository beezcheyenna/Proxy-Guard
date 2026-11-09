// Only the offline VM test runner starts this fixture. It never deploys a Worker.
import https from 'node:https';
import fs from 'node:fs';
import worker from '../../companion/worker/src/index.mjs';
let syncCalls=0,observations=0,vpcCalls=0;
const env={DEVICE_ID:'home',DEVICE_TOKEN:'d'.repeat(40),AGENT_SECRET:'a'.repeat(40),
 VPS_API:{async fetch(url,options){vpcCalls++;return fetch('http://127.0.0.1:8788/v1/sync',options);}}};
async function handle(req,res) {
 if(req.url==='/fixture-metrics') {res.end(JSON.stringify({syncCalls,observations,vpcCalls}));return;}
 const chunks=[];for await(const chunk of req)chunks.push(chunk);
 const data=Buffer.concat(chunks);
 const headers=new Headers(req.headers);
 headers.set('cf-connecting-ip',req.socket.remoteFamily==='IPv6'?'2606:4700:4700::1111':'8.8.8.8');
 const request=new Request('https://pg-access.test:9443'+req.url,{
  method:req.method,headers,...(data.length?{body:data}:{}),duplex:'half'});
 if(req.url==='/v1/sync')syncCalls++;
 if(req.url==='/v1/observe')observations++;
 const response=await worker.fetch(request,env);
 res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
}
const tls={key:fs.readFileSync('/tmp/access-fixture.key'),cert:fs.readFileSync('/tmp/access-fixture.crt')};
for(const host of ['127.0.0.1','::1'])https.createServer(tls,(req,res)=>handle(req,res).catch(()=>{res.writeHead(500);res.end();})).listen(9443,host);
