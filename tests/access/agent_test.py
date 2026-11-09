import copy,hashlib,hmac,importlib.util,json,sys,tempfile,time,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'companion/vps'))
spec=importlib.util.spec_from_file_location('pg_vps_agent',ROOT/'companion/vps/agent.py')
agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
SECRET='a'*40
RULE=dict(id='proxy',name='Proxy',enabled=True,protocol='tcp',ports=['24443'],source_mode='any',sources=[])
class Fake:
 def __init__(self):self.calls=[];self.fail=False
 def apply(self,policy,leases):
  if self.fail:raise RuntimeError('simulated nft failure')
  self.calls.append((copy.deepcopy(policy),dict(leases)))
class Cases(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.driver=Fake();self.path=Path(self.tmp.name)/'state.json'
  self.engine=agent.Engine(SECRET,'home',self.path,self.driver)
 def body(self,**kw):
  b=dict(device_id='home',observed_ip='8.8.8.8',policy_enabled=True,
   rules=copy.deepcopy([RULE]),mode='whitelist',ttl=900,revision=1,
   issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()))
  b.update(kw);return json.dumps(b,separators=(',',':')).encode()
 def sync(self,raw):
  return self.engine.sync(raw,hmac.new(SECRET.encode(),raw,hashlib.sha256).hexdigest())
 def test_empty_template_does_not_manage_ssh_or_other_ports(self):
  p,leases=self.driver.calls[0]
  self.assertTrue(p['enabled']);self.assertEqual(p['rules'],[]);self.assertEqual(leases,{})
  text=agent.render(p,{})
  self.assertNotIn('drop',text);self.assertNotIn('dport',text)
  self.assertFalse(p['default_deny']);self.assertFalse(p['auto_discover'])
 def test_legacy_flags_cannot_expand_a_signed_policy(self):
  result=self.sync(self.body(default_deny=True,auto_discover=True))
  self.assertFalse(result['policy']['default_deny']);self.assertFalse(result['policy']['auto_discover'])
  self.assertEqual([x['ports']for x in self.driver.calls[-1][0]['rules']],[RULE['ports']])
 def test_saved_port_policy_survives_main_state_corruption(self):
  rule=dict(RULE,source_mode='dynamic')
  self.sync(self.body(rules=[rule]))
  cache=self.path.with_name(self.path.name+'.policy')
  self.assertEqual(cache.stat().st_mode&0o777,0o600)
  before=cache.stat().st_mtime_ns
  self.sync(self.body(rules=[rule]))
  self.assertEqual(cache.stat().st_mtime_ns,before,'unchanged policy does not add disk writes')
  self.path.write_text('{')
  restored=agent.load_bootstrap_policy(self.path)
  self.assertEqual(restored['rules'][0]['ports'],rule['ports']);self.assertNotIn('leases',cache.read_text())
  text=agent.render(restored,{})
  self.assertIn('tcp dport { 24443 } counter drop',text)
  self.assertNotIn('proxy-guard-default-deny',text)
 def test_legacy_saved_state_migrates_to_selected_ports(self):
  self.sync(self.body())
  state=json.loads(self.path.read_text());state['policy'].update(default_deny=True,auto_discover=True)
  self.path.write_text(json.dumps(state))
  e=agent.Engine(SECRET,'home',self.path,self.driver)
  self.assertFalse(e.state['policy']['default_deny']);self.assertFalse(e.state['policy']['auto_discover'])
  self.assertEqual([x['ports']for x in self.driver.calls[-1][0]['rules']],[RULE['ports']])
 def test_auth_source_and_freshness(self):
  raw=self.body()
  with self.assertRaises(PermissionError):self.engine.sync(raw,'0'*64)
  for value in ['127.0.0.1','10.0.0.1','::1','fc00::1','ff02::1','203.0.113.1']:
   with self.subTest(value=value),self.assertRaises(agent.Invalid):self.sync(self.body(observed_ip=value))
  with self.assertRaises(agent.Invalid):self.sync(self.body(issued_at=1))
 def test_replay_survives_restart_without_restoring_dynamic_permits(self):
  raw=self.body();self.sync(raw)
  self.engine=agent.Engine(SECRET,'home',self.path,self.driver)
  self.assertEqual(self.driver.calls[-1][1],{})
  with self.assertRaises(agent.Invalid):self.sync(raw)
 def test_families_are_independent(self):
  self.sync(self.body());self.sync(self.body(observed_ip='2606:4700:4700::1111'))
  self.assertEqual(set(self.engine.leases),{4,6})
  self.sync(self.body(observed_ip='1.1.1.1'));self.assertEqual(self.engine.leases[4][0],'1.1.1.1')
  self.assertIn(6,self.engine.leases)
 def test_config_revisions_prevent_old_inflight_policy_overwrite(self):
  self.sync(self.body(revision=3))
  with self.assertRaises(agent.Invalid):self.sync(self.body(revision=2))
  changed=copy.deepcopy([RULE]);changed[0]['source_mode']='dynamic'
  with self.assertRaises(agent.Invalid):self.sync(self.body(revision=3,rules=changed))
  self.assertTrue(self.sync(self.body(revision=4,rules=changed))['ok'])
 def test_ports_sources_and_overlap_are_strict(self):
  base=copy.deepcopy(RULE)
  for patch in [{'ports':['22;flush ruleset']},{'ports':['0']},{'ports':['65536']},{'ports':['50-40']},
                {'protocol':'icmp'},{'source_mode':'static','sources':[]},
                {'source_mode':'static','sources':['1.2.3.4;id']}]:
   with self.subTest(patch=patch),self.assertRaises(agent.Invalid):
    agent.normalize_policy(True,[dict(base,**patch)])
  with self.assertRaises(agent.Invalid):agent.normalize_policy(True,[base,dict(base,id='other')])
  normalized=agent.normalize_policy(True,[dict(base,source_mode='static',sources=['8.8.8.8/24','2606:4700::/32'])])
  self.assertEqual(normalized['rules'][0]['sources'],['2606:4700::/32','8.8.8.0/24'])
 def test_dynamic_rules_drop_both_families_even_if_lease_empty(self):
  p=agent.normalize_policy(True,[dict(RULE,ports=['443'],source_mode='dynamic',protocol='both')],mode='whitelist')
  text=agent.render(p,{})
  for family in ['ipv4','ipv6']:
   for proto in ['tcp','udp']:self.assertIn('meta nfproto '+family+' '+proto+' dport { 443 } counter drop',text)
  self.assertNotIn('flush ruleset',text)
 def test_failed_update_never_acknowledges_and_reserves_nonce(self):
  raw=self.body();self.driver.fail=True
  with self.assertRaises(RuntimeError):self.sync(raw)
  self.assertFalse(self.engine.ready)
  self.driver.fail=False
  with self.assertRaises(agent.Invalid):self.sync(raw)
  self.assertTrue(self.sync(self.body())['ok'])
 def test_secret_and_saved_file_permissions(self):
  self.sync(self.body());self.assertEqual(self.path.stat().st_mode&0o777,0o600)
  self.assertNotIn(SECRET,self.path.read_text())
 def test_family_selection_revokes_other_dynamic_lease(self):
  self.sync(self.body());self.sync(self.body(observed_ip='2606:4700:4700::1111'))
  self.sync(self.body(observed_ip='2606:4700:4700::1111',revision=2,address_families=[6]))
  self.assertEqual(set(self.engine.leases),{6})
  self.assertEqual(self.driver.calls[-1][0]['address_families'],[6])
  with self.assertRaises(agent.Invalid):self.sync(self.body(revision=2,address_families=[4,6]))
 def test_failed_kernel_update_does_not_keep_old_source_for_repair(self):
  self.sync(self.body());self.driver.fail=True
  with self.assertRaises(RuntimeError):self.sync(self.body(observed_ip='9.9.9.9'))
  self.assertEqual(self.engine.leases[4][0],'9.9.9.9')
  self.assertFalse(self.engine.ready)
 def test_invalid_family_selection_never_reserves_or_authorizes(self):
  for value in [None,[],[True],[4,4],[5],['4']]:
   with self.assertRaises(agent.Invalid):self.sync(self.body(address_families=value))
if __name__=='__main__':unittest.main(verbosity=2)
