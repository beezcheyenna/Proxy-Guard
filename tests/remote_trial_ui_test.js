const fs=require('fs'),assert=require('assert');
const root=process.env.PG_SOURCE||process.cwd();
const source=fs.readFileSync(root+'/package/root/www/luci-static/resources/proxy_guard_remote_trial.js','utf8');
const vm=require('vm');
function fixture(){
 const calls=[],notices=[];let state={policy_trial:{pending:false}},reply={ok:true},shows=0,hides=0,reloads=0,refreshes=0;
 const rpc={declare:spec=>async(...args)=>{calls.push({method:spec.method,args});return spec.method==='status'?state:reply;}};
 const E=(tag,attrs={},children=[])=>({tag,attrs,children,disabled:!!attrs.disabled,textContent:''});
 const ui={hideModal(){hides++;},addNotification:(...a)=>notices.push(a)};
 const pgI18n={runtime:x=>x,modal(){shows++;}};
 const ctx={baseclass:{extend:x=>x},rpc,ui,poll:{add(){}},pgI18n,_:x=>x,E};
 const helper=vm.runInNewContext('(function(){'+source+'})()',ctx);
 const view={reloadAccessConfig:async()=>reloads++,refresh:async()=>refreshes++};
 return{helper,view,calls,notices,setState:x=>state=x,setReply:x=>reply=x,counts:()=>({shows,hides,reloads,refreshes})};
}
(async()=>{
 const f=fixture(),h=f.helper;await h.attach(f.view);
 const t={pending:true,id:'trial',revision:2,phase:'waiting',owned:true};f.setState({policy_trial:t});await h.refresh();
 assert(h.keep.disabled&&!h.cancel.disabled,'waiting policy cannot be kept but may be cancelled');
 f.setState({phase:'error'});await h.refresh();assert(h.keep.disabled&&h.cancel.disabled,'a missing confirmation status cannot leave stale confirmation buttons enabled');
 f.setState({policy_trial:{...t,phase:'confirming',remaining:30,owned:false}});await h.refresh();assert(h.keep.disabled&&h.cancel.disabled,'foreign session cannot confirm or cancel');
 f.setState({policy_trial:{...t,phase:'confirming',remaining:30}});await h.refresh();assert(!h.keep.disabled&&!h.cancel.disabled);
 f.setReply({ok:true,policy_trial:{...t,phase:'confirming',remaining:30,action:'confirm'}});
 f.setState({policy_trial:{...t,phase:'confirming',remaining:30,action:'confirm'}});await h.send('confirm');
 assert.equal(f.calls.filter(c=>c.method==='policy_confirm').length,1);assert(h.keep.disabled&&h.cancel.disabled,'pending confirmation cannot dispatch twice');
 f.setState({policy_trial:{pending:false,last_result:{id:'trial',phase:'confirmed'}}});await h.refresh();assert.equal(f.counts().reloads,0,'confirmed form stays loaded');
 f.setState({policy_trial:t});await h.begin(t);f.setState({policy_trial:{pending:false,last_result:{id:'trial',phase:'rolled_back',remote_known:true}}});await h.refresh();
 assert.equal(f.counts().reloads,1,'timeout reloads saved configuration');assert.equal(f.notices.length,1);
 f.setState({policy_trial:{...t,phase:'remote_restoring'}});await h.refresh();assert(h.keep.disabled&&h.cancel.disabled,'ongoing server restoration cannot be confirmed');
 f.setState({policy_trial:{...t,phase:'uncertain',action:'confirm'}});await h.refresh();assert(h.keep.disabled&&h.cancel.disabled);assert.match(h.message.textContent,/unknown/);
 f.setState({policy_trial:{pending:false,last_result:{id:'trial',phase:'conflict',remote_known:true}}});await h.refresh();
 assert.match(f.notices.at(-1)[1].children[0],/changed elsewhere/,'conflict does not falsely claim restoration');
 console.log('PASS remote policy confirmation UI: ownership, readiness, repeated actions, rollback reload and unknown/conflicting results');
})().catch(e=>{console.error(e);process.exit(1);});
