"""Isolated-VM collector and authenticated HTTP invariants; no live IP reflectors."""
import copy, hashlib, hmac, json, os, tempfile, threading, time, unittest, uuid
from pathlib import Path
from unittest.mock import patch
import urllib.request, urllib.error
from egress import EgressInfo, config, public_ipv4, panel_addresses, _measure_fixed_target


class CollectorTests(unittest.TestCase):
    def test_public_ipv4_excludes_non_public_and_noncanonical(self):
        for value in ['8.8.8.8','1.1.1.1','9.9.9.9']:
            self.assertEqual(public_ipv4(value), value)
        for value in [None, 8, {}, '008.8.8.8','0.1.1.1','10.2.3.4','100.64.0.1','127.0.0.1',
                      '169.254.1.1','172.16.1.1','192.0.0.9','192.0.2.1','192.88.99.1','192.168.1.1',
                      '198.18.1.1','198.51.100.1','203.0.113.1','224.0.0.1','240.0.0.1','255.255.255.255',
                      '::ffff:8.8.8.8','2606:4700::1111','panel.example','8.8.8.8:443','8.8.8.8/32',' 8.8.8.8']:
            with self.subTest(value=value): self.assertIsNone(public_ipv4(value))

    def test_config_accepts_no_targets_commands_or_implicit_enabling(self):
        self.assertFalse(config()['measure_enabled'])
        for value in [[], {'url':'https://localhost'}, {'command':'ip addr'}, {'measure_enabled':1},
                      {'measure_interval':5}, {'measure_interval':True}, {'panel_config_path':'relative'},
                      {'panel_config_path':'/proc/self/environ'}, {'panel_config_path':'/etc/../secret'}]:
            with self.subTest(value=value), self.assertRaises(ValueError): config(value)

    def test_nat_is_valid_empty_advisory_without_measurement(self):
        called=[]
        c=EgressInfo(interfaces=lambda:['10.0.2.15','127.0.0.1'], panel=lambda _:[],
                     measurement=lambda:called.append(True))
        c.start();c.sample_measurement();r=c.report();c.close()
        self.assertEqual(r['status'],'unavailable');self.assertEqual(r['candidates'],[])
        self.assertIn('non_public_ipv4_omitted',r['warnings']);self.assertIn('measurement_disabled',r['warnings'])
        self.assertFalse(r['business_egress_verified']);self.assertEqual(called,[])

    def test_sources_deduplicate_and_freshness_uses_monotonic_time(self):
        clock=[1000.0,1700000000]
        c=EgressInfo({'measure_enabled':True,'measure_interval':60}, interfaces=lambda:['8.8.8.8'],
                     panel=lambda _:['8.8.8.8'], measurement=lambda:['8.8.8.8'],
                     monotonic=lambda:clock[0],wall=lambda:clock[1])
        c.sample_measurement();r=c.report()
        self.assertEqual(len(r['candidates']),1)
        self.assertEqual({e['source']for e in r['candidates'][0]['evidence']},{'interface','panel','measured'})
        self.assertEqual(r['measurement']['state'],'fresh');self.assertFalse(r['ambiguous'])
        clock[1]-=3600;self.assertEqual(c.report()['measurement']['state'],'fresh')
        clock[0]+=121;self.assertEqual(c.report()['measurement']['state'],'stale');c.close()

    def test_failure_retains_old_value_only_as_stale(self):
        def fail(): raise OSError('private-secret-path')
        c=EgressInfo({'measure_enabled':True},interfaces=lambda:[],panel=lambda _:[],measurement=lambda:['8.8.8.8'])
        c.sample_measurement();stamp=c.report()['measurement']['checked_at'];c.measurement=fail;c.sample_measurement();r=c.report()
        self.assertEqual(r['measurement']['state'],'stale');self.assertEqual(r['measurement']['checked_at'],stamp)
        self.assertEqual(r['candidates'][0]['ipv4'],'8.8.8.8');self.assertNotIn('private-secret-path',json.dumps(r));c.close()

    def test_ambiguity_bounds_and_measured_evidence_survives_truncation(self):
        c=EgressInfo({'measure_enabled':True}, interfaces=lambda:['9.0.0.'+str(n)for n in range(1,20)],
                     panel=lambda _:['1.1.1.1'], measurement=lambda:['200.1.1.1','201.1.1.1'])
        c.sample_measurement();r=c.report();c.close()
        self.assertTrue(r['ambiguous']);self.assertEqual(len(r['candidates']),8)
        self.assertEqual(r['candidates'][0]['ipv4'],'200.1.1.1')
        self.assertIn('measurement_disagreement',r['warnings']);self.assertIn('candidates_truncated',r['warnings'])
        self.assertFalse(r['business_egress_verified'])

    def test_panel_never_resolves_domains_or_promotes_reality_and_destinations(self):
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory)/'config.json'
            p.write_text(json.dumps({'inbounds':[{'listen':'panel.example','streamSettings':{'realitySettings':{'target':'8.8.8.8:443'}}}],
                                     'outbounds':[{'sendThrough':'10.0.0.1','settings':{'servers':[{'address':'9.9.9.9'}]}}]}));p.chmod(0o600)
            with patch('egress.socket.getaddrinfo',side_effect=AssertionError('DNS not permitted for panel')):
                c=EgressInfo({'panel_config_path':str(p)},interfaces=lambda:[])
                r=c.report();c.close()
            self.assertEqual(r['candidates'],[]);self.assertIn('panel_hint_ignored',r['warnings'])
            p.write_text(json.dumps({'inbounds':[{'listen':'8.8.8.8'}]}));self.assertEqual(panel_addresses(str(p)),['8.8.8.8'])
            link=Path(directory)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):panel_addresses(str(link))
            p.chmod(0o666)
            with self.assertRaises(ValueError):panel_addresses(str(p))

    def test_collector_errors_and_raw_data_never_escape(self):
        def fail(*_):raise RuntimeError('private-interface-token')
        c=EgressInfo(interfaces=fail,panel=fail);r=c.report();c.close()
        self.assertEqual(r['candidates'],[]);self.assertNotIn('private-interface-token',json.dumps(r))
        self.assertIn('interface_unavailable',r['warnings']);self.assertIn('panel_unavailable',r['warnings'])

    def test_measurement_never_connects_to_private_dns_result(self):
        with patch('egress.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('egress.socket.create_connection')as connect:
            with self.assertRaises(ValueError):_measure_fixed_target()
            connect.assert_not_called()

    def test_report_never_starts_an_enabled_measurement(self):
        calls=[];c=EgressInfo({'measure_enabled':True},interfaces=lambda:[],panel=lambda _:[],measurement=lambda:calls.append(True))
        for _ in range(3):self.assertEqual(c.report()['measurement']['state'],'pending')
        self.assertEqual(calls,[]);c.close()


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from agent import Engine
        from control import Server
        class Driver:
            def apply(self,*_):pass
        cls.directory=tempfile.TemporaryDirectory(prefix='pg-egress-http-')
        cls.engine=Engine('a'*40,'home',Path(cls.directory.name)/'state.json',Driver())
        cls.server=Server(('127.0.0.1',0),cls.engine,{'direct_token':'d'*40,'services':[]},'pro')
        cls.server.egress.close()
        cls.calls=[]
        cls.server.egress=EgressInfo(interfaces=lambda:cls.calls.append('inventory')or['8.8.8.8'],panel=lambda _:[])
        cls.server.activity=lambda *_args,**_kw:(_ for _ in ()).throw(AssertionError('egress must never note control/proxy activity'))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3);cls.directory.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=None if body is None else body,headers=headers or{})
        try:r=urllib.request.urlopen(req,timeout=4)
        except urllib.error.HTTPError as e:r=e
        return r.status,json.loads(r.read())

    def signed(self,**changes):
        body={'device_id':'home','issued_at':int(time.time()*1000),'request_id':str(uuid.uuid4()),'purpose':'egress-info',**changes}
        raw=json.dumps(body).encode();return raw,{'x-pg-signature':hmac.new(b'a'*40,raw,hashlib.sha256).hexdigest()}

    def test_direct_auth_precedes_collection(self):
        before=len(self.calls)
        self.assertEqual(self.request('/v1/direct/egress-info')[0],401)
        self.assertEqual(len(self.calls),before)
        code,data=self.request('/v1/direct/egress-info',headers={'authorization':'Bearer '+'d'*40})
        self.assertEqual(code,200);self.assertEqual(data['candidates'][0]['ipv4'],'8.8.8.8')
        self.assertEqual(self.request('/v1/direct/egress-info?url=http://localhost',headers={'authorization':'Bearer '+'d'*40})[0],404)

    def test_signed_auth_nonce_and_no_heartbeat_policy_or_lease_mutation(self):
        raw,headers=self.signed();before=(copy.deepcopy(self.engine.state),copy.deepcopy(self.engine.leases),(self.engine.path.read_bytes() if self.engine.path.exists() else None))
        self.assertEqual(self.request('/v1/egress-info',raw,{'x-pg-signature':'0'*64})[0],403)
        code,data=self.request('/v1/egress-info',raw,headers);self.assertEqual(code,200);self.assertFalse(data['business_egress_verified'])
        after=(self.engine.state,self.engine.leases,(self.engine.path.read_bytes() if self.engine.path.exists() else None));self.assertEqual(before,after)
        self.assertEqual(self.request('/v1/egress-info',raw,headers)[0],403)

    def test_readonly_signed_body_cannot_be_replayed_as_status_heartbeat(self):
        raw,headers=self.signed()
        self.assertEqual(self.request('/v1/status',raw,headers)[0],400)
        self.assertEqual(self.request('/v1/egress-info',raw,headers)[0],200)

    def test_signed_request_never_accepts_targets_or_old_nonce(self):
        for data in [{'url':'http://127.0.0.1'},{'issued_at':int(time.time()*1000)-180000},{'purpose':'status'}]:
            raw,headers=self.signed(**data);self.assertGreaterEqual(self.request('/v1/egress-info',raw,headers)[0],400)


if __name__=='__main__':unittest.main(verbosity=2)
