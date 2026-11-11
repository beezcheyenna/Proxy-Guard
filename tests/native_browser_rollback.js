async page => {
 const sid=await page.evaluate(()=>L.env.sessionid),states=[];
 const call=async(o,m,p={})=>{const r=await page.request.post('http://10.77.0.1/ubus',{data:{jsonrpc:'2.0',id:3,method:'call',params:[sid,o,m,p]}});const b=await r.json();if(b.error||b.result?.[0]!==0)throw Error(JSON.stringify(b));return b.result[1]||{};};
 const before=(await call('uci','get',{config:'proxy_guard',section:'main'})).values;
 await page.getByRole('link',{name:'Connection checks',exact:true}).click();
 await page.getByRole('textbox',{name:'Consecutive failed rounds',exact:true}).fill(before.fail_threshold==='2'?'3':'2');
 await page.getByText('Save & Apply',{exact:true}).last().click();
 let tx=null,deadline=Date.now()+80000;
 while(Date.now()<deadline){
  const info=await call('proxy_guard','setup_info');
  tx=info.transaction||null;states.push(tx?{phase:tx.phase,remaining:tx.remaining}:null);
  if(tx?.phase==='confirming')break;
  await page.waitForTimeout(1000);
 }
 if(tx?.phase!=='confirming')throw Error('UI apply did not reach confirmation '+JSON.stringify(states));
 const dialog=await page.getByRole('dialog').filter({visible:true}).innerText();
 deadline=Date.now()+65000;
 while(Date.now()<deadline){
  if(!(await call('proxy_guard','setup_info')).transaction)break;
  await page.waitForTimeout(1500);
 }
 if((await call('proxy_guard','setup_info')).transaction)throw Error('unconfirmed trial was not rolled back');
 const after=(await call('uci','get',{config:'proxy_guard',section:'main'})).values;
 const keys=new Set([...Object.keys(before),...Object.keys(after)]);
 const changed=[...keys].filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k]));
 if(changed.length)throw Error('timeout rollback changed saved config '+JSON.stringify(changed));
 return {ok:true,realUiApply:true,unconfirmedTrialRolledBack:true,configRestored:true,states,dialog};
}
