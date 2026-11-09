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
function field(label,input,description){return E('div',{class:'cbi-value'},[E('label',{class:'cbi-value-title',for:input.id},[label]),E('div',{class:'cbi-value-field'},[input,description?E('p',{class:'cbi-value-description'},[description]):''])]);}
function select(id,options,value){return E('select',{id,class:'cbi-input-select'},options.map(row=>E('option',{value:row[0],selected:row[0]===value?true:null},[row[1]])));}
return baseclass.extend({
 attach:function(view,options){
  this.view=view;this.rawView=options&&options.raw===true;
  return infoCall().then(assertResult).then(info=>{
   this.info=info;
   poll.add(()=>this.pollTransaction(),1);
   if(info.transaction){
    if(info.transaction.claimable)return claimCall().then(assertResult).then(r=>{this.active=r.transaction;this.showTransaction();});
    this.active=info.transaction;this.showTransaction();
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
  this.lastInfoAt=performance.now();const epoch=this.epoch||0;
  this.request=infoCall().then(assertResult).then(async info=>{
   if(epoch!==(this.epoch||0))return;
   this.info=info;
   if(info.transaction){
    if(!this.active){
     if(info.transaction.claimable){
      const claimed=assertResult(await claimCall());
      if(epoch!==(this.epoch||0))return;
      info.transaction=claimed.transaction;
     }
     this.epoch=(this.epoch||0)+1;this.active=info.transaction;this.showTransaction();return;
    }
    if(info.transaction.id!==this.active.id){this.active=null;throw new Error(_('Another configuration transaction is active'));}
    this.active=Object.assign({},this.active,info.transaction);this.renderTransaction();
   }else if(this.active){
    const old=this.active;this.active=null;this.epoch=(this.epoch||0)+1;ui.hideModal();
    const result=info.last_result;
    await this.reloadForm();
    if(result&&result.id===old.id&&result.phase!=='confirmed')this.view.showActionError(new Error(_('Settings were restored: ')+(result.reason||result.phase)));
   }
  }).catch(e=>{if(this.active&&this.transactionMessage)this.transactionMessage.textContent=errorText(e);}).finally(()=>{this.request=null;});
  return this.request;
 },
 begin:function(result){
  assertResult(result);this.epoch=(this.epoch||0)+1;
  if(result.confirmation_required){this.active=Object.assign({owned:true},result.transaction);this.showTransaction();}
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
  const t=this.active;
  this.transactionMessage.textContent=t.owned===false?_('Another session is checking configuration'):t.phase==='confirming'?_('Self-check passed. Seconds remaining to confirm: ')+t.remaining:_('Checking the applied configuration and protection rules...');
  this.confirmButton.disabled=t.owned===false||t.phase!=='confirming'||!(t.remaining>0);
  this.cancelButton.disabled=t.owned===false||t.phase==='rollback_pending';
 },
 finish:function(cancel){
  if(!this.active||this.finishing)return;
  this.finishing=true;this.epoch=(this.epoch||0)+1;this.confirmButton.disabled=true;this.cancelButton.disabled=true;
  const t=this.active;
  return (cancel?cancelCall:confirmCall)(t.id,t.token).then(assertResult).then(()=>{
   this.active=null;ui.hideModal();return this.reloadForm();
  }).catch(e=>{this.transactionMessage.textContent=errorText(e);}).finally(()=>{this.finishing=false;this.renderTransaction();});
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
   this.discovery=data;this.ipv6Choice=null;this.ipv6Acknowledged=false;
   if(reset)this.draft=Object.assign({},data.defaults||{});
   this.renderWizard();
  }).catch(e=>this.view.showActionError(e));
 },
 capture:function(validate){
  if(this.step===0){
   const selected=this.discovery.interfaces.filter(row=>this.inputs[row.device].checked);
   if(!selected.length)throw new Error(_('Select at least one LAN ingress device'));
   const devices=selected.map(row=>row.device);
   const changed=!this.scopeChosen||devices.join('\0')!==list(this.draft.interfaces).join('\0');
   this.draft.interfaces=devices;this.scopeChosen=true;
   if(changed){
    for(const key of ['sources4','sources6'])this.draft[key]=Array.from(new Set(selected.flatMap(row=>row[key]||[])));
    const local=this.discovery.interfaces.filter(row=>row.recommended||selected.includes(row));
    for(const key of ['local4','local6'])this.draft[key]=Array.from(new Set(local.flatMap(row=>row[key]||[])));
    // Preserve reported IPv6 prefixes; explicit scope selection follows.
    this.ipv6Choice='';this.ipv6Acknowledged=false;
   }
  }else if(this.step===1){
   if(this.mode.value==='boot')this.watch.checked=true;
   this.draft.mode=this.mode.value==='monitor'?'monitor':'guard';
   this.draft.boot_guard=this.mode.value==='boot'?'1':'0';
   this.draft.enabled=this.enable.checked?'1':'0';
   this.draft.socks_port=this.socks.value;
   this.draft.proxy_client=this.client.value;
   this.draft.passwall_watch=this.watch.checked?'1':'0';
   this.draft.passwall_log_watch=this.watch.checked?'1':'0';
   this.draft.client_auto_ports=this.watch.checked?'1':'0';
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
   this.draft.ipv6_protect=choice==='none'?'0':'1';
   if(choice==='none')this.draft.sources6=[];
   else if(validate!==false&&!this.draft.sources6.length)throw new Error(_('Enter IPv6 addresses or prefixes, or explicitly choose no IPv6 matching.'));
   this.ipv6Choice=choice;this.ipv6Acknowledged=this.ipv6Acknowledge.checked;
   this.draft.exit_check=this.exitCheck.checked?'1':'0';
   this.draft.expected_exit4=this.expected.value;
   this.draft.exit_source='manual';
  }
 },
 renderWizard:function(){
  this.renderEpoch=(this.renderEpoch||0)+1;this.nextPending=false;
  this.inputs=Object.create(null);const body=[];
  const names=[_('LAN ingress devices'),_('Protection preset'),_('Scope and exceptions'),_('Review settings')];
  body.push(E('p',{},[(this.step+1)+' / 4 · '+names[this.step]]));
  body.push(E('p',{},[_('Only traffic passing through this router can be protected. Settings take effect only after Save & Apply.')]));
  if(this.step===0){
   for(const row of this.discovery.interfaces){
    const current=list(this.draft.interfaces);
    const checked=!this.scopeChosen&&(this.reset||this.info&&!this.info.wizard_complete)?row.recommended:current.includes(row.device);
    const input=E('input',{id:'pg-setup-if-'+row.device,type:'checkbox',checked:checked?true:null});
    this.inputs[row.device]=input;
    body.push(field(row.device+' ('+row.name+')',input,(row.up?_('Interface is up'):_('Interface is down'))+' · '+row.sources4.concat(row.sources6).join(', ')));
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
   this.mode=select('pg-setup-mode',[['monitor',_('Monitor only')],['guard',_('Block Internet access on proxy failure')],['boot',_('Block during startup and proxy failures')]],this.draft.boot_guard==='1'?'boot':this.draft.mode||'monitor');
   this.enable=E('input',{id:'pg-setup-enabled',type:'checkbox',checked:this.draft.enabled==='1'?true:null});
   this.client=select('pg-setup-client',['auto','passwall','passwall2','openclash','nikki','homeproxy'].map(v=>[v,v==='auto'?_('Automatic detection'):v]),this.draft.proxy_client||'auto');
   this.socks=E('input',{id:'pg-setup-socks',type:'number',min:1,max:65535,value:this.draft.socks_port||'1070'});
   this.watch=E('input',{id:'pg-setup-watch',type:'checkbox',checked:this.draft.passwall_watch==='1'?true:null});
   this.mode.addEventListener('change',()=>{if(this.mode.value==='boot')this.watch.checked=true;});
   this.schedule=E('input',{id:'pg-setup-schedule',type:'checkbox',checked:this.draft.schedule_enabled==='1'?true:null});
   body.push(field(_('Preset'),this.mode),field(_('Enable after Save & Apply'),this.enable),field(_('Proxy client'),this.client),field(_('Local SOCKS port'),this.socks),field(_('Monitor client services and lifecycle logs'),this.watch),field(_('Keep scheduled protection enabled'),this.schedule));
   if(!profile.available)body.push(E('p',{},[_('Automatic client detection is ambiguous or unavailable. Select the client and verify the listener ports.')]));
  }else if(this.step===2){
   for(const [key,label]of [['sources4',_('Protected IPv4 addresses')],['sources6',_('Protected IPv6 addresses')],['local4',_('Allowed LAN IPv4 networks')],['local6',_('Allowed LAN IPv6 networks')],['proxy_ports',_('Local proxy ingress ports')],['dns_ports',_('DNS redirect destination ports')]]){
    const input=E('textarea',{id:'pg-setup-'+key,rows:2,dir:'ltr',style:'width:100%;'},[list(this.draft[key]).join('\n')]);this.inputs[key]=input;body.push(field(label,input));
   }
   const existing=this.info&&this.info.wizard_complete&&!this.reset;
   const mode=this.ipv6Choice||(existing?(this.draft.ipv6_protect==='0'?'none':list(this.draft.sources6).length?'custom':'none'):'');
   this.ipv6Mode=select('pg-setup-ipv6-scope',[
    ['',_('Choose IPv6 scope')],['detected',_('IPv6 prefixes reported by selected interfaces')],
    ['custom',_('Specify IPv6 addresses or prefixes')],['all',_('All IPv6 sources on selected ingress devices')],
    ['none',_('Do not match IPv6 sources')]],mode);
   this.ipv6Acknowledge=E('input',{id:'pg-setup-ipv6-confirm',type:'checkbox',checked:this.ipv6Acknowledged?true:null});
   this.ipv6Mode.addEventListener('change',()=>{
    const choice=this.ipv6Mode.value;
    if(choice==='all')this.inputs.sources6.value='::/0';
    else if(choice==='none')this.inputs.sources6.value='';
    else if(choice==='detected')this.inputs.sources6.value=Array.from(new Set(this.discovery.interfaces.filter(row=>list(this.draft.interfaces).includes(row.device)).flatMap(row=>row.sources6||[]))).join('\n');
    this.ipv6Acknowledge.checked=false;
   });
   this.inputs.sources6.addEventListener('input',()=>{this.ipv6Mode.value='custom';this.ipv6Acknowledge.checked=false;});
   body.push(field(_('IPv6 protection scope'),this.ipv6Mode),
    E('p',{class:'alert-message warning'},[_('IPv4 and IPv6 scopes are independent. Selecting one IPv4 device does not select the same device in IPv6. All-source IPv6 matching includes other devices routed through these ingress interfaces; no IPv6 matching leaves that traffic unprotected.')]),
    field(_('I have checked the IPv6 scope independently of IPv4'),this.ipv6Acknowledge));
   this.exitCheck=E('input',{id:'pg-setup-exit-check',type:'checkbox',checked:this.draft.exit_check==='1'?true:null});
   this.expected=E('input',{id:'pg-setup-expected',type:'text',dir:'ltr',value:this.draft.expected_exit4||''});
   body.push(field(_('Verify proxy exit IPv4'),this.exitCheck),field(_('Expected proxy exit IPv4'),this.expected),E('p',{},[_('Exit IP verification is optional. Pro can import an expected address from the VPS in General settings.')]));
  }else{
   this.draft.setup_complete='1';
   const yes=value=>value==='1'?_('Enabled'):_('Disabled');
   const mode=this.draft.mode==='monitor'?_('Monitor only'):_('Block Internet access on proxy failure');
   const summary=[
    [_('Enable protection'),yes(this.draft.enabled)],[_('Operating mode'),mode],
    [_('Ingress devices'),list(this.draft.interfaces).join(', ')],
    [_('Protected IPv4 addresses'),list(this.draft.sources4).join(', ')],
    [_('Protected IPv6 addresses'),list(this.draft.sources6).join(', ')],
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
  body.push(E('div',{class:'right'},[
   E('button',{type:'button',class:'cbi-button',click:later},[_('Set up later')]),' ',
   this.step?E('button',{type:'button',class:'cbi-button',click:()=>{try{this.capture(false);this.step--;this.renderWizard();}catch(e){this.wizardError.textContent=errorText(e);}}},[_('Back')]):'',' ',
   this.nextButton=E('button',{type:'button',class:'cbi-button cbi-button-action',disabled:this.step===0&&!this.discovery.interfaces.length?true:null,click:this.step===3?apply:next},[this.step===3?_('Save & Apply'):_('Next')])
  ]));
  pgI18n.modal(ui,_('Protection setup wizard'),body);
 }
});

