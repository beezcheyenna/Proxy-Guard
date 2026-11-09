'use strict';
'require view';
'require rpc';
'require uci';
'require ui';
'require proxy_guard_i18n as pgI18n';
'require proxy_guard_setup as pgSetup';
'require proxy_guard_remote_trial as pgRemoteTrial';
const isPro=window.location.pathname.replace(/\/$/,'').endsWith('proxy-guard-access-raw');
const name=isPro?'proxy_guard_access':'proxy_guard';
const object=isPro?'proxy_guard_access':'proxy_guard';
const infoCall=rpc.declare({object,method:'raw_info',expect:{'':{}},reject:true,nobatch:true});
const parseCall=rpc.declare({object,method:'raw_parse',params:['text','token'],expect:{'':{}},reject:true,nobatch:true});
const applyCall=rpc.declare({object,method:'apply',params:isPro?['raw_token']:['confirm_flow','raw_token'],expect:{'':{}},reject:true,nobatch:true});
function result(r){if(!r||r.ok!==true)throw new Error(r&&r.error||'raw_validation_failed');return r;}
function diagnostic(error){
 const code=error&&error.message||'';
 if(code.includes('policy_trial_storage_invalid'))return _('Policy confirmation data could not be read. Review saved settings and VPS state.');
 if(code.includes('session_permissions_updated'))return _('Sign out of LuCI and sign in again to use updated permissions.');
 if(/access denied|permission denied/i.test(code))return _('Sign out and sign in again to load raw editor permissions.');
 if(code.includes('raw_configuration_changed')||code.includes('raw_staged_configuration_changed'))return _('Configuration changed elsewhere. Reload it before saving.');
 if(code.includes('raw_snapshot_expired'))return _('Configuration snapshot expired. Reload the configuration.');
 if(code.includes('raw_'))return _('Invalid UCI syntax or configuration values.');
 return pgI18n.runtime(code)||code||_('Apply failed');
}
return view.extend({
 load:function(){return infoCall().then(result).catch(e=>({error:diagnostic(e)}));},
 render:function(info){
  if(info.error){this.handleSave=null;this.handleSaveApply=null;this.handleReset=null;return pgI18n.decorate(E('div',{},[E('h2',{},[_('Raw UCI configuration')]),E('p',{class:'alert-message warning'},[info.error])]));}
  this.info=info;this.savedText=info.text;
  this.editor=E('textarea',{id:'pg-raw-editor','aria-label':_('Raw UCI configuration'),class:'cbi-input-textarea',rows:28,spellcheck:'false',autocomplete:'off',autocapitalize:'off',wrap:'off',dir:'ltr',style:'box-sizing:border-box;width:100%;min-height:28em;resize:vertical;direction:ltr;text-align:left;unicode-bidi:plaintext;font-family:monospace;',input:()=>{if(this.feedback)this.feedback.textContent='';if(this.validationFeedback)this.validationFeedback.replaceChildren();this.updateDraftIndicator();}},[info.text]);
  this.feedback=E('p',{role:'status','aria-live':'polite'},[]);
  this.validationFeedback=E('div',{role:'status','aria-live':'polite'},[]);this.showValidation(info.validation);
  const template=()=>ui.showModal(_('Default template'),[
   E('p',{},[_('Replace the editor draft with the default template? Changes take effect after Save & Apply.')]),
   E('div',{class:'right'},[E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[_('Cancel')]),' ',E('button',{type:'button',class:'cbi-button cbi-button-action',click:()=>{this.editor.value=this.info.template;this.feedback.textContent='';this.validationFeedback.replaceChildren();this.updateDraftIndicator();ui.hideModal();}},[_('Use template')])])]);
  const download=()=>{const url=URL.createObjectURL(new Blob([this.editor.value],{type:'text/plain;charset=utf-8'}));const link=E('a',{href:url,download:name+'.uci'});document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  const root=E('div',{class:'pg-guard'},[
   E('h2',{},[(isPro?_('VPS access rules'):_('Proxy Guard'))+' · '+_('Raw UCI configuration')]),
   E('p',{},[_('Edit the complete UCI configuration for this plugin. Save stages changes; Save & Apply validates and activates them. Existing secret values are preserved by placeholders.')]),
   E('p',{},[E('a',{href:isPro?'proxy-guard-access':'proxy-guard'},[isPro?_('VPS access rules'):_('Proxy Guard')])]),
   info.template_loaded?E('p',{class:'alert-message warning'},[_('This configuration could not be read. A default template is shown for review.')]):'',
   isPro?E('p',{class:'alert-message warning'},[_('Changes take effect after Save & Apply. Stopping synchronization does not remove VPS rules. Dynamic authorizations expire; configured resource limits and SSH rescue remain in effect.')]):'',
   this.editor,this.feedback,this.validationFeedback,E('div',{class:'cbi-page-actions'},[
    E('button',{type:'button',class:'cbi-button',click:()=>this.runAction(()=>this.validate())},[_('Validate configuration')]),' ',
    E('button',{type:'button',class:'cbi-button',click:template},[_('Load default template')]),' ',
    E('button',{type:'button',class:'cbi-button',click:download},[_('Download configuration')])])]);
  if(!isPro)setTimeout(()=>pgSetup.attach(this,{raw:true}),0);else setTimeout(()=>pgRemoteTrial.attach(this),0);
  this.root=root;return pgI18n.decorate(root);
 },
 showValidation:function(value){
  if(!this.validationFeedback)return;
  const rows=[];
  if(!value)rows.push(E('p',{},[_('UCI syntax checked. Activation parameters have not been verified.')]));
  else {
   rows.push(E('p',{class:value.activation_parameters_valid?'':'alert-message warning'},[value.activation_parameters_valid?_('Activation parameters are valid. The runtime environment is checked when applying.'):_('UCI syntax is valid, but activation parameters are incomplete or invalid. Check required fields, numbers, sources and ports.')]));
   for(const [key,label]of [['unknown_fields',_('Unrecognized options are preserved but may have no effect: ')],['ignored_fields',_('These legacy options are ignored: ')]]){
    if(Array.isArray(value[key])&&value[key].length)rows.push(E('p',{class:'alert-message warning'},[label,E('code',{},[value[key].join(', ')])]));
   }
  }
  this.validationFeedback.replaceChildren(...rows);
 },
 updateDraftIndicator:function(){
  if(this.editor.value!==this.savedText)ui.showIndicator('pg-raw-draft',_('Unsaved changes'));else ui.hideIndicator('pg-raw-draft');
 },
 showActionError:function(error){ui.addNotification(null,E('p',{},[diagnostic(error)]),'error');},
 validate:function(){
  // Prior validation belongs to the previous draft, not this request.
  this.validationFeedback.replaceChildren();
  const text=this.editor.value;
  if(new TextEncoder().encode(text).length>65536)return Promise.reject(new Error('raw_too_large'));
  return parseCall(text,this.info.token).then(result).then(r=>{if(this.editor.value===text){this.feedback.textContent='';this.showValidation(r.validation);}return r;});
 },
 reloadRaw:function(){
  uci.unload(name);
  return infoCall().then(result).then(info=>{this.info=info;this.editor.value=info.text;this.savedText=info.text;this.feedback.textContent='';this.showValidation(info.validation);this.updateDraftIndicator();});
 },
 refresh:function(){return Promise.resolve();},
 stage:function(){
  let expected;const draft=this.editor.value;
  return this.validate().then(parsed=>{expected=parsed.text;return uci.load(name).then(()=>{
   const wanted=parsed.sections;
   const current=[];uci.sections(name,null,section=>current.push(section));
   for(const section of current){const next=wanted[section['.name']];if(!next||next.section_type!==section['.type'])uci.remove(name,section['.name']);}
   for(const [id,section]of Object.entries(wanted)){
    const previous=uci.get(name,id);
    if(!previous)uci.add(name,section.section_type,id);
    const old=uci.get(name,id)||{};
    for(const key of Object.keys(old))if(key[0]!=='.'&&!Object.prototype.hasOwnProperty.call(section.options,key))uci.unset(name,id,key);
    for(const [key,value]of Object.entries(section.options)){
     if(value===this.info.secret_marker)continue;
     uci.set(name,id,key,value);
    }
   }
   return uci.save();
  });}).then(()=>this.reloadRaw()).then(()=>{if(this.info.text!==expected){this.editor.value=draft;this.updateDraftIndicator();throw new Error('raw_staged_configuration_changed');}return ui.changes.init();});
 },
 runAction:function(action){
  if(this.busy)return this.busy;
  const controls=this.root?Array.from(this.root.querySelectorAll('button')):[];
  this.editor.readOnly=true;for(const button of controls)button.disabled=true;
  this.busy=Promise.resolve().then(action).catch(e=>this.showActionError(e)).finally(()=>{this.busy=null;this.editor.readOnly=false;for(const button of controls)button.disabled=false;});return this.busy;
 },
 handleSave:function(){return this.runAction(()=>this.stage());},
 handleReset:function(){return this.runAction(()=>this.reloadRaw().then(()=>ui.changes.init()));},
 handleSaveApply:function(){return this.runAction(()=>this.stage().then(()=>isPro?applyCall(this.info.token):applyCall(true,this.info.token)).then(result).then(r=>{
  if(!isPro)pgSetup.begin(r);else pgRemoteTrial.begin(r.policy_trial);
  return Promise.all([this.reloadRaw(),ui.changes.init()]);
 }));}
});
