'use strict';
'require baseclass';
'require ui';
'require rpc';
'require poll';
'require uci';
'require proxy_guard_i18n as pgI18n';

const infoCall=rpc.declare({object:'proxy_guard',method:'setup_info',expect:{'':{}},reject:true,nobatch:true});
const discoverCall=rpc.declare({object:'proxy_guard',method:'setup_discover',params:['proxy_client'],expect:{'':{}},reject:true});
const claimCall=rpc.declare({object:'proxy_guard',method:'setup_claim',expect:{'':{}},reject:true});
const previousCall=rpc.declare({object:'proxy_guard',method:'setup_previous',expect:{'':{}},reject:true});
const confirmCall=rpc.declare({object:'proxy_guard',method:'setup_confirm',params:['id','token'],expect:{'':{}},reject:true});
const cancelCall=rpc.declare({object:'proxy_guard',method:'setup_cancel',params:['id','token'],expect:{'':{}},reject:true});
const errorText=e=>pgI18n.runtime(e && (e.message||e.error)) || _('Unable to complete setup');
const list=value=>Array.isArray(value)?value:value?[value]:[];
const lines=value=>Array.from(new Set(String(value||'').split(/[\s,]+/).filter(Boolean)));
const assertResult=r=>{if(!r||r.ok!==true)throw new Error(r&&r.error||_('Invalid setup response'));return r;};
function field(label,input) {
 return E('div',{class:'pg-setup-field'},[E('label',{for:input.id},[label]),input]);
}
function toggle(label,input,description) {
 return E('div',{class:'pg-setup-toggle'},[
  E('label',{class:'cbi-checkbox',for:input.id},[input,E('span',{},[label])]),
  ...(description ? [E('p',{class:'cbi-value-description'},[description])] : [])
 ]);
}
function select(id,options,value){return E('select',{id,class:'cbi-input-select'},options.map(row=>E('option',{value:row[0],selected:row[0]===value?true:null},[row[1]])));}
function presets() {
 return [['monitor',_('Monitor only')],['guard',_('Block Internet access on proxy failure')],
         ['boot',_('Block during startup and proxy failures')]];
}
const wizardStyles = [
 '.pg-setup-wizard{min-width:0;overflow-wrap:anywhere}',
 '.pg-setup-wizard .pg-setup-field{display:grid;grid-template-columns:minmax(0,38%) minmax(0,1fr);align-items:center;gap:.35em 1em;margin:.65em 0}',
 '.pg-setup-wizard .pg-setup-field[hidden]{display:none}',
 '.pg-setup-wizard .pg-setup-field>label{margin:0;text-align:start}',
 '.pg-setup-wizard .pg-setup-field>input,.pg-setup-wizard .pg-setup-field>select,.pg-setup-wizard .pg-setup-field>textarea{width:100%;min-width:0;max-width:100%;box-sizing:border-box;margin:0}',
 '.pg-setup-wizard textarea{resize:vertical}',
 '.pg-setup-wizard .pg-setup-toggle{margin:.65em 0}',
 '.pg-setup-wizard .pg-setup-toggle>label{display:flex;align-items:center;gap:.55em;margin:0}',
 '.pg-setup-wizard .pg-setup-toggle input{flex:none}',
 '.pg-setup-wizard .pg-setup-footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.5em;margin-block-start:1em}',
 '.pg-setup-wizard .pg-setup-footer>button{margin:0;max-width:100%;white-space:normal}',
 '@media(max-width:560px){.pg-setup-wizard .pg-setup-field{grid-template-columns:minmax(0,1fr)}}'
].join('');
return baseclass.extend({
 attach:function(view,options){
  this.view=view;this.rawView=options&&options.raw===true;
  const requested=performance.now();
  return infoCall().then(assertResult).then(info=>{
   this.info=info;
   poll.add(()=>this.pollTransaction(),1);
   if(info.transaction){
    if(info.transaction.claimable){
     const claimRequested=performance.now();
     return claimCall().then(assertResult).then(r=>{this.setTransaction(r.transaction,claimRequested);this.showTransaction();});
    }
    this.setTransaction(info.transaction,requested);this.showTransaction();
   }
   else if(!this.rawView&&!info.wizard_complete&&!this.shown){this.shown=true;setTimeout(()=>this.open(false),0);}
  }).catch(e=>view.showActionError(e));
 },
 reloadForm:function(){
  const view=this.view;
  if(this.rawView)return view.reloadRaw().then(()=>Promise.all([view.refresh(),ui.changes.init()]));
  view.extraDraft={};uci.unload('proxy_guard');
  return view.map.load().then(()=>view.map.reset()).then(()=>{
   view.savedFormSnapshot=view.formSnapshot();view.updateDraftIndicator();
   return Promise.all([view.refresh(),ui.changes.init()]);
  });
 },
 pollTransaction:function(){
  if(this.request||this.finishing)return Promise.resolve();
  if(!this.active&&performance.now()-(this.lastInfoAt||0)<5000)return Promise.resolve();
  const requested=this.lastInfoAt=performance.now();const epoch=this.epoch||0;
  this.request=infoCall().then(assertResult).then(async info=>{
   if(epoch!==(this.epoch||0))return;
   this.info=info;
   if(info.transaction){
    if(!this.active||info.transaction.id!==this.active.id){
     // A second session can finish one transaction and start another between
     // polls. Follow the current transaction so its modal can also close.
     let since=requested;
     if(info.transaction.claimable){
      since=performance.now();
      const claimed=assertResult(await claimCall());
      if(epoch!==(this.epoch||0))return;
      info.transaction=claimed.transaction;
     }
     this.epoch=(this.epoch||0)+1;this.setTransaction(info.transaction,since);this.showTransaction();return;
    }
    this.setTransaction(info.transaction,requested);this.renderTransaction();
   }else if(this.active){
    const old=this.active;this.active=null;clearTimeout(this.transactionTimer);this.epoch=(this.epoch||0)+1;ui.hideModal();
    const result=info.last_result;
    await this.reloadForm();
    if(result&&result.id===old.id&&result.phase!=='confirmed')this.view.showActionError(new Error(_('Settings were restored: ')+(result.reason||result.phase)));
   }
  }).catch(()=>{
   if(epoch===(this.epoch||0)&&this.active){
    this.active.verification='unverified';this.renderTransaction();
   }
  }).finally(()=>{this.request=null;});
  return this.request;
 },
 setTransaction:function(transaction,requested){
  this.active=transaction;
  const remaining=Number(transaction.remaining_ms);
  const deadline=requested+(Number.isFinite(remaining)&&remaining>0?remaining:0);
  // Once the server starts the confirmation window, subsequent responses
  // may shorten our estimate but may not restart the same countdown.
  const previous=this.transactionDeadline;
  this.transactionDeadline=transaction.phase==='confirming'
   ? {id:transaction.id,at:previous&&previous.id===transaction.id?Math.min(previous.at,deadline):deadline} : null;
  // setup_info samples runtime immediately before replying. Let the latest
  // response remain usable while another poll is in progress.
  this.verificationUntil=performance.now()+3500;
 },
 begin:function(result){
  assertResult(result);this.epoch=(this.epoch||0)+1;
  if(result.confirmation_required){this.setTransaction(Object.assign({owned:true},result.transaction),performance.now());this.showTransaction();}
 },
 showTransaction:function(){
  this.transactionMessage=E('p',{role:'status','aria-live':'polite'});
  this.confirmButton=E('button',{type:'button',class:'cbi-button cbi-button-action',disabled:true,click:()=>this.finish(false)},[_('Keep these settings')]);
  this.cancelButton=E('button',{type:'button',class:'cbi-button cbi-button-neutral',click:()=>this.finish(true)},[_('Restore previous settings')]);
  pgI18n.modal(ui,_('Confirm protection settings'),[this.transactionMessage,E('p',{},[_('The router restores the previous configuration if you do not confirm. Closing this page does not stop the rollback timer.')]),E('div',{class:'right'},[this.cancelButton,' ',this.confirmButton])]);
  this.renderTransaction();
 },
 renderTransaction:function(){
  if(!this.active||!this.transactionMessage)return;
  clearTimeout(this.transactionTimer);
  const t=this.active,now=performance.now();
  const deadline=this.transactionDeadline?.at||0;
  const remaining=Math.max(0,Math.ceil((deadline-now)/1000));
  const fresh=now<this.verificationUntil;
  const labels={
   allowing:_('Protection rules verified. Internet access is allowed.'),
   blocked:_('Protection rules verified. Internet access is blocked.'),
   monitor:_('Monitoring configuration verified.')
  };
  const verified=fresh&&Object.prototype.hasOwnProperty.call(labels,t.verification);
  if(t.owned!==true)this.transactionMessage.textContent=_('Another session is checking configuration');
  else if(t.phase==='confirming'){
   const message=verified?labels[t.verification]:_('Protection status needs verification. You can keep these settings once the check passes.');
   this.transactionMessage.textContent=message+' '+_('Seconds remaining to confirm: %s').replace('%s',remaining);
   if(remaining>0){
    const nextTick=deadline-(remaining-1)*1000-now;
    this.transactionTimer=setTimeout(()=>this.renderTransaction(),Math.max(20,verified?Math.min(nextTick,this.verificationUntil-now):nextTick));
   }
  }
  else if(t.phase==='rollback_pending')this.transactionMessage.textContent=_('Restoring the previous configuration…');
  else this.transactionMessage.textContent=_('Checking the applied configuration and protection rules...');
  this.confirmButton.disabled=this.finishing||t.owned!==true||t.phase!=='confirming'||!verified||!remaining||!t.token;
  this.cancelButton.disabled=this.finishing||t.owned!==true||t.phase==='rollback_pending'||!t.token;
 },
 finish:function(cancel){
  if(!this.active||this.finishing)return;
  this.renderTransaction();
  if((cancel?this.cancelButton:this.confirmButton).disabled)return;
  this.finishing=true;this.epoch=(this.epoch||0)+1;this.confirmButton.disabled=true;this.cancelButton.disabled=true;
  const t=this.active;
  return (cancel?cancelCall:confirmCall)(t.id,t.token).then(assertResult).then(()=>{
   this.active=null;clearTimeout(this.transactionTimer);ui.hideModal();return this.reloadForm();
  }).catch(e=>{
   if(this.active)this.active.verification='unverified';
   this.view.showActionError(e);
  }).finally(()=>{this.finishing=false;this.renderTransaction();});
 },
 fill:function(draft){
  const view=this.view;view.extraDraft=view.extraDraft||{};
  for(const key of Object.keys(draft)){
   if(key.charAt(0)==='.')continue;
   const option=view.formSection.children.find(o=>o.option===key);
   if(option){const widget=option.getUIElement('main');if(widget)widget.setValue(draft[key]);}
   else view.extraDraft[key]=draft[key];
  }
  if(view.map.checkDepends)view.map.checkDepends();
  view.updateDraftIndicator();
 },
 restorePrevious:function(){
  if(this.active)return this.showTransaction();
  return previousCall().then(assertResult).then(r=>{
   this.fill(r.draft);
   pgI18n.modal(ui,_('Review restored settings'),[E('p',{},[_('The previous settings are loaded into the form. Review them and use Save & Apply to activate them.')]),E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[_('Close')])]);
  }).catch(e=>this.view.showActionError(e));
 },
 open:function(reset){
  if(this.active)return this.showTransaction();
  this.step=0;this.scopeChosen=false;this.presetInitialized=false;this.portsKey=null;this.renderEpoch=(this.renderEpoch||0)+1;this.reset=reset;this.draft=Object.assign({},uci.get('proxy_guard','main')||{});
  const epoch=this.renderEpoch;
  return discoverCall(this.draft.proxy_client||'auto').then(assertResult).then(data=>{
   if(epoch!==this.renderEpoch)return;
   this.discovery=data;this.ipv6Choice=null;this.ipv6Acknowledged=false;this.ipv6CustomSources=null;
   if(reset)this.draft=Object.assign({},data.defaults||{});
   else if(this.info?.wizard_complete) this.portsKey=(this.draft.proxy_client||'auto')+':'+data.client.client;
   this.renderWizard();
  }).catch(e=>this.view.showActionError(e));
 },
 capture:function(validate){
  if(this.step===0){
   const selected=this.discovery.interfaces.filter(row=>this.inputs[row.device].checked);
   if(!selected.length)throw new Error(_('Select at least one LAN ingress device'));
   const devices=selected.map(row=>row.device);
   const initialize=!this.scopeChosen && (this.reset || !this.info || !this.info.wizard_complete);
   const changed=initialize || devices.slice().sort().join('\0')!==list(this.draft.interfaces).slice().sort().join('\0');
   this.draft.interfaces=devices;this.scopeChosen=true;
   if(changed){
    for(const key of ['sources4','sources6'])this.draft[key]=Array.from(new Set(selected.flatMap(row=>row[key]||[])));
    const local=this.discovery.interfaces.filter(row=>row.recommended||selected.includes(row));
    for(const key of ['local4','local6'])this.draft[key]=Array.from(new Set(local.flatMap(row=>row[key]||[])));
    // Preserve reported IPv6 prefixes; explicit scope selection follows.
    this.ipv6Choice='';this.ipv6Acknowledged=false;this.ipv6CustomSources=null;
   }
  }else if(this.step===1){
   if(this.mode.value==='boot')this.watch.checked=true;
   this.draft.mode=this.mode.value==='monitor'?'monitor':'guard';
   this.draft.boot_guard=this.mode.value==='boot'?'1':'0';
   this.draft.enabled=this.enable.checked?'1':'0';
   this.draft.socks_port=this.socks.value;
   this.draft.proxy_client=this.client.value;
   const watch=this.watch.checked?'1':'0';
   if(this.reset||!this.info?.wizard_complete||watch!==(this.draft.passwall_watch||'0')){
    this.draft.passwall_log_watch=watch;
    this.draft.client_auto_ports=watch;
   }
   this.draft.passwall_watch=watch;
   this.draft.schedule_enabled=this.schedule.checked?'1':'0';
   const portsKey=this.client.value+':'+this.discovery.client.client;
   if(this.portsKey!==portsKey&&this.discovery.client.available&&(this.client.value==='auto'||this.client.value===this.discovery.client.client)){
    this.draft.proxy_ports=list(this.discovery.client.proxy_ports).map(String);
    this.draft.dns_ports=Array.from(new Set(['53',...list(this.discovery.client.dns_ports).map(String)]));
    this.portsKey=portsKey;
   }
  }else if(this.step===2){
   for(const key of ['sources4','sources6','local4','local6','proxy_ports','dns_ports'])this.draft[key]=lines(this.inputs[key].value);
   const choice=this.ipv6Mode.value;
   if(validate!==false&&!choice)throw new Error(_('Choose an IPv6 protection scope explicitly.'));
   if(validate!==false&&!this.ipv6Acknowledge.checked)throw new Error(_('Confirm the IPv6 scope independently of IPv4.'));
   if (choice) this.draft.ipv6_protect=choice==='none'?'0':'1';
   if (choice==='none') this.draft.sources6=[];
   else if (validate!==false&&!this.draft.sources6.length) throw new Error(_('Enter IPv6 addresses or prefixes, or explicitly choose no IPv6 matching.'));
   if (choice==='custom') this.ipv6CustomSources=this.inputs.sources6.value;
   this.ipv6Choice=choice;this.ipv6Acknowledged=this.ipv6Acknowledge.checked;
   this.draft.exit_check=this.exitCheck.checked?'1':'0';
   this.draft.expected_exit4=this.expected.value;
  }
 },
 renderWizard:function(){
  this.renderEpoch=(this.renderEpoch||0)+1;this.nextPending=false;
  this.inputs=Object.create(null);const body=[];
  const names=[_('LAN ingress devices'),_('Protection preset'),_('Scope and exceptions'),_('Review settings')];
  // Keep the step number and total in order inside right-to-left titles.
  const progress='\u2066'+(this.step+1)+' / '+names.length+'\u2069';
  const title=_('Protection setup wizard')+' · '+progress+' · '+names[this.step];
  body.push(E('p',{},[_('Only traffic passing through this router can be protected. Settings take effect only after Save & Apply.')]));
  if(this.step===0){
   for(const row of this.discovery.interfaces){
    const current=list(this.draft.interfaces);
    const checked=!this.scopeChosen&&(this.reset||this.info&&!this.info.wizard_complete)?row.recommended:current.includes(row.device);
    const input=E('input',{id:'pg-setup-if-'+row.device,type:'checkbox',checked:checked?true:null});
    this.inputs[row.device]=input;
    body.push(toggle(row.device+' ('+row.name+')',input,(row.up?_('Interface is up'):_('Interface is down'))+' · '+row.sources4.concat(row.sources6).join(', ')));
   }
   if(!this.discovery.interfaces.length)body.push(E('p',{},[_('No eligible LAN device was found. Configure the existing network first; this wizard does not create interfaces.')]));
  }else if(this.step===1){
   const profile=this.discovery.client;
   if(!this.presetInitialized){
    if(this.reset||!this.info||!this.info.wizard_complete){
     this.draft.enabled='1';
     this.draft.passwall_watch=profile.available?'1':'0';
     if(profile.available){this.draft.proxy_client=profile.client;this.draft.socks_port=String(profile.socks_port);}
    }
    this.presetInitialized=true;
   }
   this.mode=select('pg-setup-mode',presets(),this.draft.boot_guard==='1'?'boot':this.draft.mode||'monitor');
   this.enable=E('input',{id:'pg-setup-enabled',type:'checkbox',checked:this.draft.enabled==='1'?true:null});
   this.client=select('pg-setup-client',['auto','passwall','passwall2','openclash','nikki','homeproxy'].map(v=>[v,v==='auto'?_('Automatic detection'):v]),this.draft.proxy_client||'auto');
   this.socks=E('input',{id:'pg-setup-socks',type:'number',min:1,max:65535,value:this.draft.socks_port||'1070'});
   this.watch=E('input',{id:'pg-setup-watch',type:'checkbox',checked:this.draft.passwall_watch==='1'?true:null});
   this.mode.addEventListener('change',()=>{if(this.mode.value==='boot')this.watch.checked=true;});
   this.schedule=E('input',{id:'pg-setup-schedule',type:'checkbox',checked:this.draft.schedule_enabled==='1'?true:null});
   body.push(field(_('Preset'),this.mode),toggle(_('Enable after Save & Apply'),this.enable),
    field(_('Proxy client'),this.client),field(_('Local SOCKS port'),this.socks),
    toggle(_('Monitor client services and lifecycle logs'),this.watch),toggle(_('Keep scheduled protection enabled'),this.schedule));
   if(!profile.available)body.push(E('p',{},[_('Automatic client detection is ambiguous or unavailable. Select the client and verify the listener ports.')]));
  }else if(this.step===2){
   const scopeFields=[
    ['sources4',_('Protected IPv4 addresses')],['sources6',_('Protected IPv6 addresses')],
    ['local4',_('Allowed LAN IPv4 networks')],['local6',_('Allowed LAN IPv6 networks')],
    ['proxy_ports',_('Local proxy ingress ports')],['dns_ports',_('DNS redirect destination ports')]
   ];
   const rows={};
   for (const [key,label] of scopeFields) {
    const input=E('textarea',{id:'pg-setup-'+key,rows:2,dir:'ltr'},[list(this.draft[key]).join('\n')]);
    this.inputs[key]=input;
    rows[key]=field(label,input);
   }
   const existing=this.info && this.info.wizard_complete && !this.reset;
   const prefixes=list(this.draft.sources6);
   const existingScope=this.draft.ipv6_protect==='0' || !prefixes.length ? 'none' :
     prefixes.length===1 && prefixes[0]==='::/0' ? 'all' : 'custom';
   const scope=this.ipv6Choice ?? (existing ? existingScope : '');
   this.ipv6Mode=select('pg-setup-ipv6-scope',[
    ['',_('Choose IPv6 scope')],['detected',_('IPv6 prefixes reported by selected interfaces')],
    ['custom',_('Specify IPv6 addresses or prefixes')],['all',_('All IPv6 sources on selected ingress devices')],
    ['none',_('Do not match IPv6 sources')]],scope);
   this.ipv6Acknowledge=E('input',{id:'pg-setup-ipv6-confirm',type:'checkbox',checked:this.ipv6Acknowledged?true:null});
   const ipv6Input=this.inputs.sources6;
   const updateScope=choice=>{
    rows.sources6.hidden=choice==='' || choice==='none';
    ipv6Input.readOnly=choice!=='custom';
    if (choice==='all') ipv6Input.value='::/0';
    else if (choice==='detected') {
     const selected=this.discovery.interfaces.filter(row=>list(this.draft.interfaces).includes(row.device));
     ipv6Input.value=Array.from(new Set(selected.flatMap(row=>row.sources6||[]))).join('\n');
    } else if (choice==='custom') ipv6Input.value=this.ipv6CustomSources ?? prefixes.join('\n');
   };
   this.ipv6Mode.addEventListener('change',()=>{
    if (!ipv6Input.readOnly) this.ipv6CustomSources=ipv6Input.value;
    updateScope(this.ipv6Mode.value);
    this.ipv6Acknowledge.checked=false;
   });
   ipv6Input.addEventListener('input',()=>{this.ipv6Acknowledge.checked=false;});
   updateScope(scope);
   body.push(rows.sources4,field(_('IPv6 protection scope'),this.ipv6Mode),rows.sources6,
    E('p',{class:'alert-message warning'},[_('IPv4 and IPv6 scopes are independent. Selecting one IPv4 device does not select the same device in IPv6. All-source IPv6 matching includes other devices routed through these ingress interfaces; no IPv6 matching leaves that traffic unprotected.')]),
    toggle(_('I have checked the IPv6 scope independently of IPv4'),this.ipv6Acknowledge),
    rows.local4,rows.local6,rows.proxy_ports,rows.dns_ports);
   this.exitCheck=E('input',{id:'pg-setup-exit-check',type:'checkbox',checked:this.draft.exit_check==='1'?true:null});
   this.expected=E('input',{id:'pg-setup-expected',type:'text',dir:'ltr',value:this.draft.expected_exit4||''});
   const expectedRow=field(_('Expected proxy exit IPv4'),this.expected);
   expectedRow.hidden=!this.exitCheck.checked;
   this.exitCheck.addEventListener('change',()=>{expectedRow.hidden=!this.exitCheck.checked;});
   body.push(toggle(_('Verify proxy exit IPv4'),this.exitCheck,
    _('Exit IPv4 verification uses the official HTTPS endpoint by default.')),expectedRow);
  }else{
   this.draft.setup_complete='1';
   const yes=value=>value==='1'?_('Enabled'):_('Disabled');
   const preset=this.draft.boot_guard==='1'?'boot':this.draft.mode;
   const mode=(presets().find(option=>option[0]===preset) || presets()[0])[1];
   const ipv6Scope=this.draft.ipv6_protect==='0' ? _('IPv6 traffic is outside this protection scope') :
      list(this.draft.sources6).join(', ');
   const summary=[
    [_('Enable protection'),yes(this.draft.enabled)],[_('Operating mode'),mode],
    [_('Ingress devices'),list(this.draft.interfaces).join(', ')],
    [_('Protected IPv4 addresses'),list(this.draft.sources4).join(', ')],
    [_('IPv6 protection scope'),ipv6Scope],
    [_('Allowed LAN IPv4 networks'),list(this.draft.local4).join(', ')],
    [_('Allowed LAN IPv6 networks'),list(this.draft.local6).join(', ')],
    [_('Proxy client'),this.draft.proxy_client],[_('Local SOCKS port'),this.draft.socks_port],
    [_('Local proxy ingress ports'),list(this.draft.proxy_ports).join(', ')],
    [_('DNS redirect destination ports'),list(this.draft.dns_ports).join(', ')],
    [_('Monitor client services and lifecycle logs'),yes(this.draft.passwall_watch)],
    [_('Block during startup and proxy failures'),yes(this.draft.boot_guard)],
    [_('Scheduled protection'),yes(this.draft.schedule_enabled)+(this.draft.schedule_enabled==='1'?' · '+this.draft.schedule_start+'–'+this.draft.schedule_end+' UTC'+this.draft.schedule_utc_offset:'')],
    [_('Verify proxy exit IPv4'),yes(this.draft.exit_check)+(this.draft.exit_check==='1'?' · '+this.draft.expected_exit4:'')]
   ];
   body.push(E('table',{class:'table','aria-label':_('Review settings')},summary.map(row=>E('tr',{},[E('th',{scope:'row'},[row[0]]),E('td',{style:'overflow-wrap:anywhere;',dir:'auto'},[row[1]||'—'])]))));
   body.push(E('p',{},[_('Self-check validates configuration and real rule state. A proxy outage keeps protection blocked; it does not disable protection.')]));
  }
  this.wizardError=E('p',{class:'error',role:'alert'});body.push(this.wizardError);
  const next=async()=>{
   if(this.nextPending)return;
   const epoch=this.renderEpoch,button=this.nextButton,step=this.step;
   this.nextPending=true;button.disabled=true;
   if(step===1)this.client.disabled=true;
   try{
    if(step===1){
     const previousPort=String(this.discovery.client.socks_port||this.draft.socks_port||'');
     const manualPort=this.socks.value!==previousPort;
     const result=assertResult(await discoverCall(this.client.value));
     if(epoch!==this.renderEpoch)return;
     this.discovery.client=result.client;
     if(result.client.available&&!manualPort)this.socks.value=String(result.client.socks_port);
    }
    this.capture();this.step++;this.renderWizard();
   }catch(e){if(epoch===this.renderEpoch)this.wizardError.textContent=errorText(e);}
   finally{if(epoch===this.renderEpoch){this.nextPending=false;button.disabled=false;if(step===1)this.client.disabled=false;}}
  };
  const later=()=>{this.renderEpoch++;this.nextPending=false;ui.hideModal();};
  const apply=()=>{this.fill(this.draft);ui.hideModal();return this.view.handleSaveApply();};
  body.push(E('div',{class:'pg-setup-footer'},[
   E('button',{type:'button',class:'cbi-button cbi-button-neutral',click:later},[_('Set up later')]),
   ...(this.step ? [E('button',{type:'button',class:'cbi-button cbi-button-neutral',
    click:()=>{try{this.capture(false);this.step--;this.renderWizard();}catch(e){this.wizardError.textContent=errorText(e);}}},[_('Back')])] : []),
   this.nextButton=E('button',{type:'button',class:'cbi-button cbi-button-action',disabled:this.step===0&&!this.discovery.interfaces.length?true:null,click:this.step===3?apply:next},[this.step===3?_('Save & Apply'):_('Next')])
  ]));
  pgI18n.modal(ui,title,[E('div',{class:'pg-setup-wizard'},[E('style',{},[wizardStyles]),...body])]);
 }
});

