async page => {
 const states=[];let sid=null,t1=null,t2=null;
 const call=async (session,object,method,params={})=>{
  const response=await page.request.post('http://10.77.0.1/ubus',{data:{jsonrpc:'2.0',id:Math.floor(Math.random()*1e8),method:'call',params:[session,object,method,params]}});
  const body=await response.json();
  if(!response.ok()||body.error||!body.result||body.result[0]!==0)throw new Error(object+'/'+method+' failed '+JSON.stringify(body));
  const result=body.result[1]||{};
  if(result.ok===false)throw new Error(object+'/'+method+' rejected '+JSON.stringify(result));
  return result;
 };
 const pollOnce=()=>page.evaluate(async()=>{
  const s=await L.require('proxy_guard_setup');s.lastInfoAt=0;await s.pollTransaction();
  const r=s.active?{id:s.active.id,owned:s.active.owned,phase:s.active.phase}:null;
  const d=document.querySelector('[role="dialog"]'),b=d?.getBoundingClientRect(),css=d?getComputedStyle(d):null;const modalInViewport=!!b&&css.visibility!=='hidden'&&css.display!=='none'&&b.width>0&&b.height>0&&b.bottom>0&&b.right>0&&b.top<innerHeight&&b.left<innerWidth;
  return {active:r,modalInViewport,modalVisibility:css?.visibility,modalOpen:document.body.classList.contains('modal-overlay-active'),message:s.transactionMessage?.textContent||''};
 });
 const change=async value=>{
  await call(sid,'uci','set',{config:'proxy_guard',section:'main',values:{fail_threshold:value}});
  const r=await call(sid,'proxy_guard','apply',{confirm_flow:true});
  if(!r.confirmation_required||!r.transaction)throw new Error('real apply did not create a transaction');
  return r.transaction;
 };
 try {
  await page.evaluate(async()=>{
   const p=await L.require('poll');p.stop();
   const s=await L.require('proxy_guard_setup');if(s.request)await s.request;
   if(s.active)throw new Error('existing transaction');
  });
  const login=await call('00000000000000000000000000000000','session','login',{username:'root',password:''});
  sid=login.ubus_rpc_session;if(!sid)throw new Error('foreign native login unavailable');
  const before=await call(sid,'uci','get',{config:'proxy_guard',section:'main'});
  const original=before.values.fail_threshold||'3';const changed=original==='2'?'3':'2';
  t1=await change(changed);
  let s=await pollOnce();states.push({step:'first_foreign_transaction',...s});
  if(s.active?.id!==t1.id||s.active?.owned!==false)throw new Error('first foreign state not visible');
  await call(sid,'proxy_guard','setup_cancel',{id:t1.id,token:t1.token});t1=null;
  t2=await change(changed);
  s=await pollOnce();states.push({step:'replacement_between_polls',...s});
  if(s.active?.id!==t2.id||s.active?.owned!==false)throw new Error('second transaction was not adopted');
  await call(sid,'proxy_guard','setup_cancel',{id:t2.id,token:t2.token});t2=null;
  s=await pollOnce();states.push({step:'replacement_finished',...s});
  if(s.active!==null||s.modalInViewport)throw new Error('orphaned active transaction or visible modal');
  const after=await call(sid,'uci','get',{config:'proxy_guard',section:'main'});
  if(JSON.stringify(before.values)!==JSON.stringify(after.values)){
   const keys=new Set([...Object.keys(before.values),...Object.keys(after.values)]);
   if([...keys].some(k=>JSON.stringify(before.values[k])!==JSON.stringify(after.values[k])))throw new Error('cancel did not restore config');
  }
  return {ok:true,states,config_restored:true,real_rpc:true,poll_pause:'simulates browser scheduling gap; no response mocks'};
 } finally {
  for(const t of [t1,t2])if(t&&sid)try{await call(sid,'proxy_guard','setup_cancel',{id:t.id,token:t.token});}catch(e){}
  await page.evaluate(async()=>{const s=await L.require('proxy_guard_setup');s.lastInfoAt=0;await s.pollTransaction();(await L.require('poll')).start();});
  if(sid)try{await call(sid,'session','destroy',{ubus_rpc_session:sid});}catch(e){}
 }
}
