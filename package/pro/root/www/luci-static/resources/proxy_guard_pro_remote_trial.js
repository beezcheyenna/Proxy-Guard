// Generated from proxy_guard_remote_trial.js by tools/build_translations.py.
'use strict';
'require baseclass';
'require rpc';
'require ui';
'require poll';
'require proxy_guard_pro_i18n as pgI18n';
const statusCall=rpc.declare({object:'proxy_guard_access',method:'status',expect:{'':{}},reject:true,nobatch:true});
const errors={policy_trial_busy:pgI18n.gettext('Another VPS policy change is awaiting confirmation.'),policy_trial_owner_mismatch:pgI18n.gettext('Only the session that applied this policy can confirm it.'),policy_trial_not_ready:pgI18n.gettext('Wait until the VPS finishes applying the policy.'),policy_trial_action_pending:pgI18n.gettext('A confirmation action is already being verified.'),policy_confirmation_unavailable:pgI18n.gettext('Update the VPS Agent and Worker to use policy confirmation.')};
const actions={confirm:rpc.declare({object:'proxy_guard_access',method:'policy_confirm',params:['id'],expect:{'':{}},reject:true,nobatch:true}),cancel:rpc.declare({object:'proxy_guard_access',method:'policy_cancel',params:['id'],expect:{'':{}},reject:true,nobatch:true})};
return baseclass.extend({
 attach:function(view){this.view=view;this.active=null;poll.add(()=>this.refresh(),2);return this.refresh();},
 begin:function(value){if(value&&value.pending){this.active=value;this.show();}return this.refresh();},
 refresh:function(){
  if(this.request)return this.request;
  this.request=statusCall().then(async state=>{
   const trial=state.policy_trial;if(!trial){if(this.active)throw new Error('policy_trial_status_unavailable');return;}
   if(trial.pending){const fresh=!this.active||this.active.id!==trial.id;this.active=trial;if(fresh)this.show();else this.renderState();}
   else if(this.active){
    const old=this.active;this.active=null;ui.hideModal();
    const result=trial.last_result;
    if(result&&result.id===old.id){
     if(result.phase!=='confirmed'){
      if(this.view.reloadAccessConfig)await this.view.reloadAccessConfig();else if(this.view.reloadRaw)await this.view.reloadRaw();
      ui.addNotification(null,E('p',{},[result.phase==='conflict'?pgI18n.gettext('Configuration changed elsewhere. Review saved settings and VPS state before applying again.'):result.remote_known?pgI18n.gettext('VPS policy was restored. Review the reloaded settings.'):pgI18n.gettext('Local settings were restored or synchronization stopped. The remote policy still needs verification.')]),'warning');
     }
     if(this.view.refresh)await this.view.refresh();
    }
   }
  }).catch(()=>{if(this.active&&this.message){this.message.textContent=pgI18n.gettext('Cannot read confirmation status. The VPS rollback timer continues.');this.keep.disabled=true;this.cancel.disabled=true;}}).finally(()=>{this.request=null;});return this.request;
 },
 show:function(){
  this.message=E('p',{role:'status','aria-live':'polite'});
  this.keep=E('button',{type:'button',class:'cbi-button cbi-button-action',disabled:true,click:()=>this.send('confirm')},[pgI18n.gettext('Keep VPS policy')]);
  this.cancel=E('button',{type:'button',class:'cbi-button',disabled:true,click:()=>this.send('cancel')},[pgI18n.gettext('Restore previous VPS policy')]);
  pgI18n.modal(ui,pgI18n.gettext('Confirm VPS policy'),[this.message,E('p',{},[pgI18n.gettext('The VPS owns this timer. Closing this page, losing the control link or rebooting before confirmation does not keep an unconfirmed policy.')]),E('div',{class:'right'},[E('button',{type:'button',class:'cbi-button',click:ui.hideModal},[pgI18n.gettext('Close')]),' ',this.cancel,' ',this.keep])]);this.renderState();
 },
 renderState:function(){
  const t=this.active;if(!t)return;
  this.message.textContent=(t.phase==='restoring'||t.phase==='remote_restoring')?pgI18n.gettext('Restore previous VPS policy')+'…':t.phase==='uncertain'?pgI18n.gettext('Confirmation result is unknown. Checking again without repeating policy changes.'):!t.owned?pgI18n.gettext('Another session is confirming the VPS policy.'):t.action?pgI18n.gettext('Waiting for the VPS to confirm the result.'):t.phase==='confirming'?pgI18n.gettext('VPS policy applied. Seconds remaining to confirm: ')+(t.remaining==null?'…':t.remaining):pgI18n.gettext('Checking the VPS capability and applying a temporary policy...');
  this.keep.disabled=!t.owned||!!t.action||t.phase!=='confirming'||!(t.remaining>0);
  this.cancel.disabled=!t.owned||!!t.action||t.phase==='restoring'||t.phase==='remote_restoring';
 },
 send:function(action){
  if(!this.active||this.sending)return;
  this.sending=true;this.keep.disabled=true;this.cancel.disabled=true;
  return actions[action](this.active.id).then(r=>{if(!r||r.ok!==true)throw new Error(r&&r.error||'policy_trial_failed');this.active=r.policy_trial;this.renderState();}).catch(e=>{ui.addNotification(null,E('p',{},[errors[e.message]||pgI18n.runtime(e.message)||pgI18n.gettext('Operation failed')]),'error');}).finally(()=>{this.sending=false;this.refresh();});
 }
});
