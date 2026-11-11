async page => {
 const sid=await page.evaluate(()=>L.env.sessionid);
 const call=async(o,m,p={})=>{const r=await page.request.post('http://10.77.0.1/ubus',{data:{jsonrpc:'2.0',id:2,method:'call',params:[sid,o,m,p]}});const b=await r.json();if(b.error||b.result?.[0]!==0)throw Error(JSON.stringify(b));return b.result[1]||{};};
 const flag=page.locator('#cbi-proxy_guard-main-enabled input[type=checkbox]');
 if(!await flag.isChecked())throw Error('enabled fixture baseline required');
 const before=await call('proxy_guard','status');
 await flag.uncheck();
 const draftIndicator=await page.getByText('Unsaved changes',{exact:true}).count();
 const afterToggle=await call('proxy_guard','status');
 if(afterToggle.enforcement!=='allowing')throw Error('toggle changed protection '+afterToggle.enforcement);
 await page.getByRole('button',{name:'Save',exact:true}).click();
 await page.waitForTimeout(6500);
 const afterSave=await call('proxy_guard','status');
 const pending=await call('uci','get',{config:'proxy_guard',section:'main'});
 if(pending.values.enabled!=='0'||afterSave.enforcement!=='allowing')throw Error('Save-only activated a draft '+JSON.stringify({pending:pending.values.enabled,enforcement:afterSave.enforcement}));
 await flag.check();
 await page.getByRole('button',{name:'Save',exact:true}).click();
 const restored=await call('uci','get',{config:'proxy_guard',section:'main'});
 if(restored.values.enabled!=='1')throw Error('restoring the form draft failed');
 return {ok:true,draftIndicatorPresent:draftIndicator>0,before:before.enforcement,afterToggle:afterToggle.enforcement,afterSave:afterSave.enforcement,savedSessionDraft:'0',formDraftRestored:true};
}
