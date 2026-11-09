import copy,hashlib,hmac,json,sys,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'companion/vps'))
import agent
from protection import DEFAULT_LIMITS,runtime_elements,rule_effect
SECRET='a'*40
RULE=dict(id='proxy',name='Proxy',enabled=True,protocol='both',ports=['24443'],source_mode='dynamic',sources=[])
class Driver:
 def __init__(self):self.calls=[];self.fail_next=False
 def apply(self,p,l):
  if self.fail_next:self.fail_next=False;raise RuntimeError('injected_nft_failure')
  self.calls.append((copy.deepcopy(p),copy.deepcopy(l)))
class Trials(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'state'
  self.now=100.0;self.clock_patch=patch('policy_trial.time.monotonic',lambda:self.now);self.clock_patch.start();self.addCleanup(self.clock_patch.stop)
  self.driver=Driver();self.engine=agent.Engine(SECRET,'home',self.path,self.driver)
  self.sync(mode='standard',revision=1)
 def sync(self,**kw):
  value=dict(device_id='home',observed_ip='8.8.8.8',policy_enabled=True,rules=[copy.deepcopy(RULE)],mode='whitelist',ttl=900,revision=2,issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()))
  value.update(kw);raw=json.dumps(value,separators=(',',':')).encode();return self.engine.sync(raw,hmac.new(SECRET.encode(),raw,hashlib.sha256).hexdigest())
 def trial(self,**kw):
  self.ident=str(uuid.uuid4());return self.sync(policy_trial=dict(id=self.ident,seconds=60),**kw)
 def test_changed_policy_requires_explicit_confirmation_and_timer_is_not_renewed(self):
  first=self.trial();self.assertEqual(first['policy_trial']['phase'],'confirming');self.assertEqual(first['policy_trial']['remaining'],60)
  self.now+=11
  again=self.sync(policy_trial=dict(id=self.ident,seconds=300))
  self.assertEqual(again['policy_trial']['remaining'],49)
  self.assertEqual(self.engine.trials.record['seconds'],60)
 def test_timeout_restores_previous_policy_keeps_revision_and_current_authenticated_ip(self):
  self.trial(observed_ip='1.1.1.1');self.now+=61;self.assertTrue(self.engine.trials.tick())
  self.assertEqual(self.engine.state['policy']['mode'],'standard');self.assertEqual(self.engine.state['revision'],2)
  self.assertEqual(self.engine.leases[4][0],'1.1.1.1');self.assertEqual(self.driver.calls[-1][1][4][0],'1.1.1.1')
  self.assertEqual(self.engine.trials.status()['phase'],'rolled_back')
  with self.assertRaises(agent.Invalid):self.sync()
  result=self.sync(revision=3,policy_trial=dict(id=str(uuid.uuid4()),seconds=60));self.assertEqual(result['policy_trial']['phase'],'confirming')
 def test_cancel_interrupted_after_state_write_resumes_before_bootstrap(self):
  self.trial()
  class Crash(BaseException):pass
  original=self.engine.save
  def cut(value):original(value);raise Crash()
  with patch.object(self.engine,'save',side_effect=cut):
   with self.assertRaises(Crash):self.engine.trials.action('cancel',self.ident,2)
  self.assertEqual(json.loads(Path(str(self.path)+'.trial').read_text())['phase'],'restoring')
  self.assertEqual(agent.load_bootstrap_policy(self.path)['mode'],'standard')
  again=agent.Engine(SECRET,'home',self.path,self.driver)
  self.assertEqual(again.trials.status()['phase'],'rolled_back');self.assertEqual(again.trials.status()['reason'],'user_cancelled')
 def test_failed_rollback_is_retried_without_waiting_for_original_deadline(self):
  self.trial(ssh={'managed':True,'confirmed':True})
  self.driver.fail_next=True
  with self.assertRaises(RuntimeError):self.engine.trials.action('cancel',self.ident,2)
  self.assertEqual(self.engine.trials.status()['phase'],'restoring');self.assertFalse(self.engine.ready)
  self.assertTrue(self.engine.trials.tick());self.assertTrue(self.engine.ready)
  self.assertTrue(self.engine.trials.safety_changed);self.assertEqual(self.engine.trials.status()['reason'],'user_cancelled')
 def test_confirmation_cannot_acknowledge_a_different_actual_policy(self):
  self.trial();self.engine.state['policy']=self.engine.trials.record['previous']
  with self.assertRaises(ValueError):self.engine.trials.action('confirm',self.ident,2)
  self.assertEqual(self.engine.trials.status()['phase'],'confirming')
 def test_bootstrap_rolls_back_before_the_first_kernel_policy(self):
  self.trial();self.engine.trials.record['boot']='previous-boot';self.engine.trials.save()
  before=copy.deepcopy(self.engine.state['seen'])
  policy=agent.load_bootstrap_policy(self.path)
  self.assertEqual(policy['mode'],'standard')
  state=json.loads(self.path.read_text());self.assertEqual(state['revision'],2);self.assertEqual(state['seen'],before)
  self.assertEqual(json.loads(Path(str(self.path)+'.trial').read_text())['phase'],'rolled_back')
 def test_large_nonce_state_still_recovers_before_bootstrap(self):
  self.trial();self.engine.state['seen'].update({str(uuid.uuid4()):int(time.time()*1000)for _ in range(1500)})
  self.engine.save(self.engine.state);self.assertGreater(self.path.stat().st_size,65536)
  self.engine.trials.record['boot']='previous-boot';self.engine.trials.save()
  self.assertEqual(agent.load_bootstrap_policy(self.path)['mode'],'standard')
  self.assertGreater(len(json.loads(self.path.read_text())['seen']),1500)
 def test_confirmation_is_idempotent_and_survives_restart(self):
  self.trial();result=self.engine.trials.action('confirm',self.ident,2);self.assertEqual(result['phase'],'confirmed')
  self.now+=1000;self.assertFalse(self.engine.trials.tick())
  self.assertEqual(self.engine.trials.action('confirm',self.ident,2)['phase'],'confirmed')
  again=agent.Engine(SECRET,'home',self.path,self.driver);self.assertEqual(again.state['policy']['mode'],'whitelist');self.assertEqual(again.leases,{})
 def test_process_restart_preserves_deadline_without_resurrecting_lease(self):
  self.trial();self.now+=20;again=agent.Engine(SECRET,'home',self.path,self.driver)
  self.assertEqual(again.trials.status()['remaining'],40);self.assertEqual(again.leases,{})
  self.now+=41;again.trials.tick();self.assertEqual(again.state['policy']['mode'],'standard')
 def test_new_boot_rolls_back_before_applying_candidate(self):
  self.trial();record=self.engine.trials.record;record['boot']='previous-boot';self.engine.trials.save()
  self.driver.calls=[];again=agent.Engine(SECRET,'home',self.path,self.driver)
  self.assertEqual(again.state['policy']['mode'],'standard');self.assertTrue(all(p['mode']=='standard'for p,l in self.driver.calls));self.assertEqual(again.leases,{})
 def test_cancellation_is_idempotent_and_wrong_owner_token_does_not_mutate(self):
  self.trial()
  for ident,rev in [(str(uuid.uuid4()),2),(self.ident,3)]:
   with self.assertRaises(ValueError):self.engine.trials.action('cancel',ident,rev)
  self.assertEqual(self.engine.state['policy']['mode'],'whitelist')
  self.assertEqual(self.engine.trials.action('cancel',self.ident,2)['phase'],'rolled_back')
  self.assertEqual(self.engine.trials.action('cancel',self.ident,2)['phase'],'rolled_back')
 def test_another_policy_cannot_replace_a_pending_trial(self):
  self.trial()
  with self.assertRaises(ValueError):self.sync(mode='observe',revision=3)
  with self.assertRaises(ValueError):self.sync(revision=3,policy_trial=dict(id=str(uuid.uuid4()),seconds=60))
  self.assertEqual(self.engine.state['revision'],2)
 def test_invalid_trial_request_does_not_change_policy(self):
  for value in [True,{},dict(id='x',seconds=60),dict(id=str(uuid.uuid4()),seconds=True),dict(id=str(uuid.uuid4()),seconds=29),dict(id=str(uuid.uuid4()),seconds=301)]:
   with self.assertRaises(ValueError):self.sync(policy_trial=value)
   self.assertEqual(self.engine.state['revision'],1)
 def test_unchanged_policy_only_refreshes_authorization(self):
  result=self.trial(mode='standard');self.assertEqual(result['policy_trial']['phase'],'confirmed');self.assertEqual(result['policy_trial']['reason'],'unchanged_policy')
 def test_failed_nft_apply_restores_before_reporting_failure(self):
  self.driver.fail_next=True
  with self.assertRaises(RuntimeError):self.trial()
  self.assertEqual(self.engine.state['policy']['mode'],'standard');self.assertEqual(self.engine.trials.status()['phase'],'rolled_back');self.assertTrue(self.engine.ready)
 def test_corrupt_trial_state_is_not_silently_discarded(self):
  self.trial();Path(str(self.path)+'.trial').write_text('{')
  with self.assertRaises(ValueError):agent.Engine(SECRET,'home',self.path,self.driver)
 def test_confirmed_trial_cannot_acknowledge_a_later_external_policy(self):
  self.trial();self.engine.trials.action('confirm',self.ident,2)
  self.sync(revision=3,mode='observe')
  result=self.engine.trials.action('confirm',self.ident,2)
  self.assertEqual(result['phase'],'conflict');self.assertEqual(self.engine.state['policy']['mode'],'observe')
 def test_confirmation_revision_has_strict_integer_type(self):
  self.trial(revision=1+1)
  for value in (True,2.0,'2',None):
   with self.assertRaises(ValueError):self.engine.trials.action('confirm',self.ident,value)
  self.assertEqual(self.engine.trials.status()['phase'],'confirming')
 def test_invalid_persisted_deadline_cannot_disable_timeout_forever(self):
  self.trial();self.engine.trials.record['deadline']=float('nan')
  Path(str(self.path)+'.trial').write_text(json.dumps(self.engine.trials.record))
  with self.assertRaises(ValueError):agent.Engine(SECRET,'home',self.path,self.driver)
 def test_new_source_mode_keeps_resource_limits_and_legacy_bypass_is_explicit(self):
  for global_mode in ('standard','observe','whitelist'):
   for source in ('all','any','dynamic'):
    p=agent.normalize_policy(True,[dict(RULE,mode='standard',source_mode=source,limits={'bandwidth_enabled':True})],mode=global_mode)
    p['_runtime']={'fallback_restricted':{'proxy':[dict(source='9.9.9.9',sport=50001,port=24443,protocol='tcp',until=200)]}}
    self.assertEqual(len(runtime_elements(p,{},100)['fallback4_0_tcp']),1)
    text=agent.render(p,{},mono=100);self.assertEqual('meter rate4_0_tcp'in text,source!='any');self.assertEqual(rule_effect(p,p['rules'][0]),'bypass'if source=='any'else'standard')
  with self.assertRaises(agent.Invalid):agent.normalize_policy(True,[dict(RULE,source_mode='all')],mode='whitelist')
if __name__=='__main__':unittest.main(verbosity=2)
