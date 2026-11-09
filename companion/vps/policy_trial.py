"""Server-owned, crash-safe selected-port policy trials. No lease resurrection."""
from __future__ import annotations
import copy,json,math,time,uuid
from pathlib import Path

class PolicyTrial:
    def __init__(self,engine,clock=None,boot=None):
        self.engine,self.clock=engine,clock or time.monotonic
        self.boot=boot or (lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        self.path=Path(str(engine.path)+'.trial');self.record=None;self.safety_changed=False;self.restoration_epoch=0
        if self.path.exists():
            data=self.path.read_bytes()
            if len(data)>131072:raise ValueError('policy_trial_state_unavailable')
            try:self.record=json.loads(data)
            except (ValueError,UnicodeError):raise ValueError('policy_trial_state_unavailable')from None
            r=self.record
            if not isinstance(r,dict)or r.get('phase')not in('applying','confirming','restoring','confirmed','rolled_back','conflict')or not isinstance(r.get('revision'),int):raise ValueError('policy_trial_state_unavailable')
            if r['phase']in('applying','confirming','restoring'):
                from agent import normalize_policy
                q=r.get('previous');r['previous']=normalize_policy(q['enabled'],q['rules'],False,False,q.get('address_families'),q.get('mode','standard'),q.get('ssh'))
                if type(r.get('deadline'))not in(int,float)or not math.isfinite(r['deadline'])or r['deadline']<0 or not isinstance(r.get('candidate_hash'),str):raise ValueError('policy_trial_state_unavailable')
    def save(self):
        from agent import write_private_json
        write_private_json(self.path,self.record,unchanged_ok=True)
    @staticmethod
    def request(value):
        if not isinstance(value,dict)or set(value)!={'id','seconds'}or type(value.get('seconds'))is not int or not 30<=value['seconds']<=300:raise ValueError('invalid_policy_trial')
        try:
            if str(uuid.UUID(value['id']))!=value['id']:raise ValueError()
        except (ValueError,TypeError,KeyError,AttributeError):raise ValueError('invalid_policy_trial')from None
        return value
    def pending(self):return self.record and self.record['phase']in('applying','confirming','restoring')
    def begin(self,policy,revision,value):
        from agent import policy_hash
        r=self.record;digest=policy_hash(policy)
        if self.pending():
            if r['revision']!=revision or r['candidate_hash']!=digest:raise ValueError('policy_trial_busy')
            if value is not None and self.request(value)['id']!=r['id']:raise ValueError('policy_trial_busy')
            return
        if value is None:return
        value=self.request(value)
        if r and value['id']==r.get('id'):
            if r['phase']=='confirmed'and r['revision']==revision and r.get('candidate_hash')==digest:return
            raise ValueError('policy_trial_expired')
        if digest==policy_hash(self.engine.state['policy']):
            self.record=dict(id=value['id'],phase='confirmed',revision=revision,candidate_hash=digest,reason='unchanged_policy');self.save();return
        from safety import heartbeat_path
        backups={}
        for name,path in [('rescue',Path(str(self.engine.path)+'.rescue')),('heartbeat',heartbeat_path(self.engine.path))]:
            if path.exists():
                data=path.read_text()
                if len(data)>8192:raise ValueError('policy_trial_state_unavailable')
                backups[name]=data
            else:backups[name]=None
        self.record=dict(id=value['id'],phase='applying',revision=revision,candidate_hash=digest,
            previous=copy.deepcopy(self.engine.state['policy']),seconds=value['seconds'],boot=self.boot(),deadline=self.clock()+120,backups=backups)
        self.save()
    def applied(self):
        if self.pending()and self.record['phase']=='applying':
            self.record.update(phase='confirming',deadline=self.clock()+self.record['seconds']);self.save()
    def rollback(self,reason,live=True):
        from agent import policy_hash,write_private_json
        r=self.record
        if not self.pending():return False
        current=policy_hash(self.engine.state['policy'])
        if current not in(r['candidate_hash'],policy_hash(r['previous']))or self.engine.state['revision']>r['revision']:
            r.update(phase='conflict',reason='policy_changed');r.pop('previous',None);r.pop('backups',None);self.save();return False
        before=copy.deepcopy(r['previous']);ssh_changed=r.get('ssh_changed',before.get('ssh')!=self.engine.state['policy'].get('ssh'))
        if r['phase']!='restoring':
            r.update(phase='restoring',restore_reason=reason,ssh_changed=ssh_changed);self.save()
        reason=r.get('restore_reason',reason)
        if ssh_changed:
            from safety import heartbeat_path
            for name,path in [('rescue',Path(str(self.engine.path)+'.rescue')),('heartbeat',heartbeat_path(self.engine.path))]:
                data=r.get('backups',{}).get(name)
                if data is None:path.unlink(missing_ok=True)
                else:
                    value=json.loads(data);write_private_json(path,value)
        state=dict(self.engine.state,policy=before,revision=max(self.engine.state['revision'],r['revision']))
        self.engine.save(state);self.engine.state=state
        if live:
            if ssh_changed:
                from safety import boot_runtime
                self.engine.runtime=boot_runtime(self.engine.path,before,persist=True)
            else:
                self.engine.runtime=dict(self.engine.runtime,trusted={},fallback_restricted={})
            self.engine.ready=False
            self.engine.driver.apply(self.engine.effective_policy(),self.engine.leases)
            self.engine.ready=True
        self.safety_changed=ssh_changed
        if live:self.restoration_epoch+=1
        r.update(phase='rolled_back',reason=reason);r.pop('previous',None);r.pop('backups',None);self.save();return True
    def tick(self,live=True):
        if self.pending()and(self.record['phase']=='restoring'or self.record.get('boot')!=self.boot()or self.clock()>=self.record['deadline']):
            return self.rollback('restart_before_confirmation'if self.record.get('boot')!=self.boot()else'confirmation_timeout',live)
        return False
    def action(self,action,ident,revision):
        if type(revision)is not int or not 1<=revision<=9007199254740991:raise ValueError('invalid_revision')
        self.tick()
        r=self.record
        if not r or r.get('id')!=ident or r['revision']!=revision:raise ValueError('policy_trial_mismatch')
        if self.engine.state['revision']>r['revision']:
            r.update(phase='conflict',reason='policy_changed');r.pop('previous',None);r.pop('backups',None);self.save();return self.status()
        if r['phase']=='confirmed'and action=='confirm':return self.status()
        if r['phase']=='rolled_back'and action=='cancel':return self.status()
        if not self.pending():raise ValueError('policy_trial_expired')
        if action=='cancel':self.rollback('user_cancelled');return self.status()
        if action!='confirm'or r['phase']!='confirming'or not self.engine.ready:raise ValueError('policy_trial_not_ready')
        from agent import policy_hash
        if policy_hash(self.engine.state['policy'])!=r['candidate_hash']:raise ValueError('policy_trial_not_ready')
        r.update(phase='confirmed',reason='user_confirmed');r.pop('previous',None);r.pop('backups',None);self.save();return self.status()
    def status(self):
        r=self.record
        if not r:return {'supported':True,'phase':'idle'}
        return dict(supported=True,**{k:r[k]for k in('id','phase','revision','reason')if k in r},
            remaining=max(0,math.ceil(r.get('deadline',0)-self.clock()))if self.pending()else 0)

def recover_bootstrap_policy(path,state):
    """Resolve a boot-expired trial before the first nft bootstrap transaction."""
    from agent import write_private_json
    class SavedState:
        def __init__(self):self.path,self.state=Path(path),state
        def save(self,value):
            write_private_json(self.path.with_name(self.path.name+'.policy'),value['policy'],unchanged_ok=True)
            write_private_json(self.path,value)
    saved=SavedState();trial=PolicyTrial(saved);trial.tick(live=False)
    return saved.state['policy']
