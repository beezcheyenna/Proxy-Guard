import copy,hashlib,hmac,json,os,sys,tempfile,threading,time,unittest,uuid
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'companion/vps'))
import agent
from protection import normalize_limits
from safety import Safety,boot_runtime,management_session
from maintenance import Maintenance
from reality_check import RealityCheck
from telemetry import Telemetry,Tail
from monitor import EventStore

RULE=dict(id='proxy',name='Proxy',enabled=True,protocol='both',ports=['24443'],source_mode='dynamic',sources=[])
class Driver:
    def __init__(self):self.calls=[]
    def apply(self,p,l):self.calls.append((copy.deepcopy(p),copy.deepcopy(l)))
class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.now=100.0;self.wall=1000.0;self.events=EventStore()
        self.engine=agent.Engine('a'*40,'home',self.root/'state.json',Driver())
        self.engine.state['policy']=agent.normalize_policy(True,[RULE])
        self.engine.runtime={};self.engine.leases={4:('8.8.8.8',10000)}
    def clock(self):return self.now
class Policy(Fixture):
    def test_three_modes_and_legacy_flags_have_selected_scope(self):
        for mode in ('standard','whitelist','observe'):
            p=agent.normalize_policy(True,[RULE],True,True,mode=mode)
            self.assertEqual(p['mode'],mode);self.assertFalse(p['default_deny']);self.assertFalse(p['auto_discover'])
            text=agent.render(p,{})
            self.assertNotIn('proxy-guard-default-deny',text)
            if mode=='observe':self.assertNotIn('counter drop',text)
            if mode=='whitelist':self.assertIn('tcp dport { 24443 } counter drop',text)
        self.assertEqual(agent.DEFAULT_POLICY['mode'],'standard');self.assertEqual(agent.DEFAULT_POLICY['rules'],[])
    def test_limits_and_ssh_conflicts_are_validated(self):
        for patch in ({'rate':0},{'rate':True},{'burst':1,'rate':2},{'connections':'10'},{'cooldown':3601}):
            with self.assertRaises(ValueError):normalize_limits(patch)
        with self.assertRaises(ValueError):agent.normalize_policy(True,[RULE],ssh={'managed':True,'port':24443})
        with self.assertRaises(ValueError):agent.normalize_policy(True,[RULE],mode='allow_everything')
        with self.assertRaises(ValueError):agent.normalize_policy(True,[],ssh={'managed':True,'managers':['0.0.0.0/0']})
    def test_runtime_changes_do_not_rebuild_the_port_policy(self):
        p=copy.deepcopy(self.engine.state['policy']);before=agent.policy_hash(p)
        p['_runtime']={'ssh_hold_until':42,'trusted':{'proxy':{'8.8.8.8':500}}}
        self.assertEqual(agent.policy_hash(p),before)
    def test_bandwidth_rules_only_match_verified_fallback_tuples(self):
        p=agent.normalize_policy(True,[dict(RULE,limits={'bandwidth_enabled':True})])
        p['_runtime']={'fallback_restricted':{'proxy':[dict(source='9.9.9.9',sport=50001,port=24443,protocol='tcp',until=200)]}}
        text=agent.render(p,{},mono=100)
        self.assertIn('9.9.9.9 . 50001 . 24443 timeout 100s',text)
        self.assertIn('tcp sport . tcp dport @fallback4_0_tcp',text);self.assertIn('tcp dport . tcp sport @fallback4_0_tcp',text)
        p['mode']='observe';self.assertNotIn('counter drop',agent.render(p,{},mono=100))
class Rescue(Fixture):
    def safety(self,ready=True,**ssh):
        self.engine.state['policy']=agent.normalize_policy(True,[RULE],ssh=dict(managed=True,confirmed=True,managers=['9.9.9.9/32'],**ssh))
        return Safety(self.engine,self.events,clock=self.clock,preflight=lambda p,s:{'ok':ready,'reason':'fixture'},journal=self.root/'heartbeat')
    def arm(self,s):s.note_control(synced=True);s.note_path();self.assertTrue(s.armed)
    def test_no_close_before_management_and_both_heartbeats(self):
        s=self.safety(False);s.note_control(synced=True);self.assertFalse(s.armed);s.note_path();self.assertFalse(s.armed)
        s.preflight=lambda p,a:{'ok':True};s.tick();self.assertTrue(s.armed)
    def test_one_channel_failure_never_triggers_dual_failure_rescue(self):
        s=self.safety();self.arm(s)
        self.now=159;s.note_control();self.now=200;s.tick();self.assertFalse(s.emergency)
        self.now=219;s.tick();self.assertTrue(s.emergency)
    def test_recovery_needs_current_authorization_not_just_path_or_status(self):
        s=self.safety();self.arm(s);self.now=160;s.tick();self.assertTrue(s.emergency)
        s.note_path();self.assertTrue(s.emergency);s.note_control();self.assertTrue(s.emergency)
        s.note_control(synced=True);self.assertFalse(s.emergency)
    def test_public_window_expires_without_resetting_it(self):
        s=self.safety(open_seconds=600);self.arm(s);self.now=160;s.tick();deadline=self.engine.runtime['ssh_public_until']
        self.now=deadline+1;s.tick();self.assertEqual(s.status()['effective_scope'],'restricted')
        self.assertEqual(self.engine.runtime['ssh_public_until'],deadline)
    def test_restart_restores_only_an_armed_matching_policy(self):
        s=self.safety();self.arm(s);value=boot_runtime(self.engine.path,self.engine.state['policy'],now=0)
        self.assertTrue(value['ssh_armed']);self.assertEqual(value['ssh_hold_until'],60)
        self.engine.state['policy']['ssh']['port']=2222
        self.assertFalse(boot_runtime(self.engine.path,self.engine.state['policy'],now=0)['ssh_armed'])
        s.tick();self.assertTrue(s.armed) # fixture preflight explicitly accepts the new port
    def test_agent_restart_does_not_renew_missing_heartbeats(self):
        s=self.safety();self.arm(s);self.now=110
        runtime=boot_runtime(self.engine.path,self.engine.state['policy'],now=self.now,journal=self.root/'heartbeat')
        self.assertEqual(runtime['ssh_hold_until'],160)
        again=Safety(self.engine,self.events,clock=self.clock,preflight=lambda p,a:{'ok':True},journal=self.root/'heartbeat')
        self.assertEqual(again.last_control,100);self.assertEqual(again.last_path,100)
        self.now=160;again.tick();self.assertTrue(again.emergency)
    def test_unlimited_default_survives_long_outage_and_only_home_sync_closes_it(self):
        s=self.safety();self.arm(s)
        self.assertEqual(self.engine.state['policy']['ssh']['open_seconds'],0)
        self.assertEqual(s.status()['effective_scope'],'restricted')
        self.assertFalse(s.status()['public_unlimited'])
        self.now=160;s.tick()
        self.assertTrue(s.status()['public_unlimited'])
        self.assertEqual(self.engine.runtime['ssh_public_until'],0)
        self.now=100000;s.tick()
        self.assertTrue(s.status()['public_unlimited'])
        s.note_path();s.note_control()
        self.assertTrue(s.status()['public_unlimited'])
        s.note_control(synced=True) # Expired household authorization cannot close rescue.
        self.assertTrue(s.status()['public_unlimited'])
        self.engine.leases={4:('1.1.1.1',self.now+120)}
        s.note_control(synced=True)
        self.assertFalse(s.emergency)
        self.assertEqual(s.last_home,['1.1.1.1'])
        self.assertEqual(s.status()['effective_scope'],'restricted')
    def test_unlimited_emergency_survives_agent_restart_without_reset(self):
        s=self.safety();self.arm(s);self.now=160;s.tick();s.heartbeat()
        self.now=1000
        runtime=boot_runtime(self.engine.path,self.engine.state['policy'],now=self.now,journal=self.root/'heartbeat')
        self.assertEqual(runtime['ssh_hold_until'],0)
        self.assertEqual(runtime['ssh_public_until'],0)
        again=Safety(self.engine,self.events,clock=self.clock,preflight=lambda p,a:{'ok':True},journal=self.root/'heartbeat')
        self.assertTrue(again.emergency)
        self.assertTrue(again.status()['public_unlimited'])
        self.assertEqual(again.last_control,100)
    def test_restricted_or_disabled_rescue_never_reports_public(self):
        for patch in ({'scope':'restricted'},{'rescue_enabled':False}):
            s=self.safety(**patch);self.arm(s);self.now+=61;s.tick()
            self.assertEqual(s.status()['effective_scope'],'restricted')
            self.assertFalse(s.status()['public_unlimited'])
    def test_duration_validation_and_explicit_upgrade_values(self):
        from protection import normalize_ssh
        self.assertEqual(normalize_ssh({})['open_seconds'],0)
        for value in (0,30,600,3600):
            self.assertEqual(normalize_ssh({'open_seconds':value})['open_seconds'],value)
        for value in (-1,1,29,3601,False,True,'0',None):
            with self.assertRaises(ValueError):normalize_ssh({'open_seconds':value})
    def test_preflight_checks_owned_listener_and_session(self):
        proc=self.root/'proc';(proc/'net').mkdir(parents=True);p=proc/'12';(p/'fd').mkdir(parents=True)
        (p/'exe').symlink_to('/usr/sbin/sshd');(p/'fd/0').symlink_to('socket:[111]');(p/'fd/1').symlink_to('socket:[222]')
        (proc/'net/tcp').write_text('header\n0: 00000000:0016 00000000:0000 0A 0 0 0 0 0 111\n1: 0100007F:0016 08080808:C350 01 0 0 0 0 0 222\n')
        self.assertTrue(management_session(22,['8.8.8.8/32'],proc)['ok'])
        self.assertFalse(management_session(22,['9.9.9.9/32'],proc)['ok'])
        (p/'exe').unlink();(p/'exe').symlink_to('/usr/bin/other')
        self.assertFalse(management_session(22,['8.8.8.8/32'],proc)['ok'])
class PerRuleModes(Fixture):
    def test_modes_inherit_and_override_without_expanding_scope(self):
        from protection import mode_metadata
        rules=[dict(RULE,id='white',protocol='tcp',ports=['24443'],mode='whitelist'),dict(RULE,id='standard',protocol='udp',ports=['24443'],mode='standard',limits={'bandwidth_enabled':True}),dict(RULE,id='observe',ports=['25000'],mode='observe')]
        p=agent.normalize_policy(True,rules,mode='observe');text=agent.render(p,{})
        self.assertEqual(mode_metadata(p)['rule_modes'],{'white':'whitelist','standard':'standard','observe':'observe'})
        self.assertIn('tcp dport { 24443 } counter drop',text)
        self.assertIn('meter rate4_1_udp',text)
        self.assertIn('meter bwout4_1_udp',text)
        self.assertNotIn('meter rate4_2_tcp',text)
        self.assertNotIn('meter bwout4_2_tcp',text)
        self.assertNotIn('25000 } counter drop',text)
        old=agent.normalize_policy(True,[RULE],mode='whitelist')
        self.assertEqual(old['rules'][0]['mode'],'inherit')
        self.assertEqual(mode_metadata(old)['rule_modes'],{'proxy':'whitelist'})
        for bad in (None,False,0,[],{},'block_all'):
            with self.assertRaises(agent.Invalid):agent.normalize_policy(True,[dict(RULE,mode=bad)])
    def test_actual_nft_concat_statistics_are_split_by_source_port_and_family(self):
        from unittest.mock import Mock
        t=Telemetry(self.engine,RealityCheck({'config_path':'','access_log':'','telemetry_file':''},clock=self.clock),Mock(),clock=self.clock,wall=lambda:self.wall)
        snapshot={'nftables':[{'set':{'name':'seen4_0_tcp','elem':[{'elem':{'val':{'concat':['9.9.9.9',24443]},'counter':{'packets':10,'bytes':5400}}}]}},{'set':{'name':'seen6_0_udp','elem':[{'elem':{'val':{'concat':['2001:4860::1',24443]},'counter':{'packets':5,'bytes':1000}}}]}}]}
        t.sample_counters(snapshot)
        self.assertEqual({(r['source_ip'],r['port'],r['protocol'])for r in t.observations},{('9.9.9.9',24443,'tcp'),('2001:4860::1',24443,'udp')})
        self.now+=2;snapshot['nftables'][0]['set']['elem'][0]['elem']['counter']['bytes']+=200
        t.sample_counters(snapshot)
        self.assertEqual(next(r['bytes_per_second']for r in t.observations if r['protocol']=='tcp'),100)
    def test_reserved_control_rule_does_not_shift_or_pollute_user_statistics(self):
        from unittest.mock import Mock
        self.engine.local_rules=[dict(id='_local_control',name='Control',enabled=True,protocol='tcp',ports=['9443'],source_mode='any',sources=[])]
        for ident in ('proxy','_local_control'):
            self.engine.state['policy']=agent.normalize_policy(True,[dict(RULE,id=ident)])
            t=Telemetry(self.engine,RealityCheck({'config_path':'','access_log':'','telemetry_file':''},clock=self.clock),Mock(),clock=self.clock)
            rows=[]
            for index,port in enumerate((9443,24443)):
                rows.append({'set':{'name':'seen4_'+str(index)+'_tcp','elem':[{'elem':{'val':{'concat':['9.9.9.9',port]},'counter':{'packets':1,'bytes':200}}}]}})
            t.sample_counters({'nftables':rows})
            self.assertEqual([(r['service'],r['port'])for r in t.observations],[(ident,24443)])
    def test_observation_never_creates_a_bandwidth_restriction(self):
        from unittest.mock import Mock
        for mode,expected in [('observe',False),('standard',True),('whitelist',False)]:
            self.engine.state['policy']=agent.normalize_policy(True,[dict(RULE,mode=mode,limits={'bandwidth_enabled':True,'bandwidth':1024,'sustain':1})],mode='observe')
            events=Mock();t=Telemetry(self.engine,RealityCheck({'config_path':'','access_log':'','telemetry_file':''},clock=self.clock),events,clock=self.clock,wall=lambda:self.wall)
            start=self.now
            for second in range(4):
                self.now=start+second;self.wall=1000+second
                t.event(dict(time=self.wall,source_ip='9.9.9.9',source_port=50000,port=24443,kind='fallback',protocol='tcp',bytes_in=second*4096,bytes_out=0))
            self.assertEqual(bool(t.restricted.get('proxy')),expected)
            self.assertTrue(events.add.called)
    def test_anomalies_on_two_ports_are_not_deduplicated_together(self):
        from unittest.mock import Mock
        events=Mock();t=Telemetry(self.engine,RealityCheck({'config_path':'','access_log':'','telemetry_file':''},clock=self.clock),events,clock=self.clock)
        for port in (24443,24444):t.alert('connection_rate_threshold','proxy','tcp','9.9.9.9',port)
        self.assertEqual(events.add.call_count,2)
class MonitorStub:
    generation='before'
    def status(self):return {'configured':True,'ok':True,'services':[{'name':'Xray','required':True,'ok':True,'generation':self.generation}]}
class Operations(Fixture):
    def manager(self,executor=None,boot=lambda:'boot-a',path=None):
        m=Maintenance(dict(enabled=True,allow_reboot=True,allow_restart_xray=True,service='Xray'),path or self.root/'operations',self.monitor,self.events,executor=executor or(lambda a,c:None),wall=lambda:self.wall,boot=boot)
        self.addCleanup(m.close);return m
    def setUp(self):super().setUp();self.monitor=MonitorStub()
    def body(self,**kw):
        v=dict(operation_id=str(uuid.uuid4()),action='restart_xray',issued_at=1000000,expires_at=1030000);v.update(kw);return v
    def test_disallowed_arbitrary_and_expired_actions(self):
        m=self.manager()
        for value in (self.body(action='restart_xray;id'),self.body(issued_at=1,expires_at=2)):
            with self.assertRaises(ValueError):m.submit(value)
        m.config['allow_reboot']=False
        with self.assertRaises(PermissionError):m.submit(self.body(action='reboot_vps'))
    def test_idempotency_executes_once_and_verifies_new_core(self):
        calls=[]
        def execute(action,c):calls.append(action);self.monitor.generation='after'
        m=self.manager(execute);body=self.body();m.submit(body);m.submit(body)
        m.thread.join(4);self.assertEqual(calls,['restart_xray']);self.assertEqual(m.status()['operations'][-1]['phase'],'complete')
        self.assertEqual((self.root/'operations').stat().st_mode&0o777,0o600)
    def test_interrupted_dispatch_is_not_replayed_after_agent_restart(self):
        m=self.manager();body=self.body();m.submit(body);m.close()
        calls=[];again=self.manager(lambda a,c:calls.append(a));result=again.submit(body)
        self.assertEqual(result['phase'],'indeterminate');self.assertEqual(calls,[])
    def test_reboot_success_needs_a_new_boot_and_healthy_service(self):
        m=self.manager();body=self.body(action='reboot_vps');m.submit(body);m.close()
        again=self.manager(boot=lambda:'boot-b');self.assertEqual(again.status()['operations'][-1]['phase'],'complete')
    def test_corrupt_operation_state_disables_commands_without_overwriting_history(self):
        p=self.root/'bad-operations';p.write_text('{')
        m=self.manager(path=p)
        self.assertFalse(m.status()['enabled']);self.assertEqual(p.read_text(),'{')
        with self.assertRaises(PermissionError):m.submit(self.body())
    def test_policy_change_before_dispatch_cancels_the_operation(self):
        calls=[];m=self.manager(lambda a,c:calls.append(a));m.authorized=lambda r:False
        m.submit(self.body());m.thread.join(3)
        self.assertEqual(calls,[]);self.assertEqual(m.status()['operations'][-1]['phase'],'failed')
    def test_concurrent_requests_do_not_dispatch_twice(self):
        m=self.manager();m.submit(self.body())
        with self.assertRaises(ValueError):m.submit(self.body())
class Data(Fixture):
    def telemetry(self):
        c={'config_path':'','access_log':'','telemetry_file':''};reality=RealityCheck(c,clock=self.clock)
        reality.tags={'inbound':24443};return Telemetry(self.engine,reality,self.events,clock=self.clock,wall=lambda:self.wall)
    def test_fallback_needs_fresh_explicit_classification_and_selected_port(self):
        t=self.telemetry();self.engine.state['policy']['rules'][0]['limits'].update(bandwidth_enabled=True,bandwidth=1024,sustain=2)
        base=dict(time=1000,source_ip='9.9.9.9',source_port=50000,port=24443,kind='fallback',protocol='tcp',bytes_in=0,bytes_out=0)
        for second in range(5):self.now=100+second;self.wall=1000+second;t.event(dict(base,time=self.wall,bytes_in=second*4096))
        self.assertTrue(t.restricted.get('proxy'))
        t.event(dict(base,kind='authenticated',time=self.wall));self.assertIn(('tcp','9.9.9.9',24443),t.trusted['proxy'])
        t.event(dict(base,source_ip='8.8.4.4',port=22,time=self.wall));self.assertNotIn('8.8.4.4',str(t.flows))
    def test_log_tail_rotation_and_untrusted_writes(self):
        p=self.root/'log';p.write_text('a\n');p.chmod(0o600);tail=Tail(str(p));self.assertEqual(tail.poll(),['a'])
        p.rename(self.root/'old');p.write_text('b\n');p.chmod(0o600);self.assertEqual(tail.poll(),['b'])
        p.chmod(0o666);self.assertEqual(tail.poll(),[]);self.assertFalse(tail.available)
    def test_reality_config_never_exports_private_keys(self):
        p=self.root/'xray.json';key='a'*43
        p.write_text(json.dumps({'inbounds':[{'tag':'inbound','port':24443,'streamSettings':{'security':'reality','realitySettings':{'privateKey':key,'shortIds':['00'],'target':'example.test:443','serverNames':['example.test']}}}]}))
        checker=RealityCheck({'config_path':str(p)},clock=self.clock);report=checker.sample()
        self.assertTrue(report['ok']);self.assertNotIn(key,json.dumps(report));self.assertEqual(checker.tags['inbound'],24443)
    def test_unsigned_status_replay_cannot_refresh_control_heartbeat(self):
        from control import Server
        server=object.__new__(Server);server.engine=self.engine;server.nonces={};server.nonces=__import__('collections').OrderedDict();server.nonce_lock=threading.Lock()
        body=dict(device_id='home',issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()))
        server.claim_nonce(body)
        with self.assertRaises(PermissionError):server.claim_nonce(body)

class ConnectionFailures(unittest.TestCase):
    def test_invalid_tls_connections_do_not_dump_tracebacks_or_source_addresses(self):
        from control import Server
        from unittest.mock import patch
        import ssl
        server=object.__new__(Server);server.nonce_lock=threading.Lock();server.events=EventStore()
        with patch('control.time.monotonic',return_value=100):
            for _ in range(10):
                try:raise ssl.SSLError('HTTP_REQUEST private-address')
                except ssl.SSLError:server.handle_error(None,('8.8.8.8',9999))
        report=server.events.snapshot();self.assertEqual(len(report['events']),1)
        self.assertEqual(report['events'][0]['kind'],'control_connection_failed')
        self.assertNotIn('private-address',str(report));self.assertNotIn('8.8.8.8',str(report))

if __name__=='__main__':unittest.main(verbosity=2)
