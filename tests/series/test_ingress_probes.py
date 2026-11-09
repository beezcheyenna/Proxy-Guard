import copy, json, os, sys, tempfile, unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"companion/vps"))
from discovery import Inventory,effective_policy
from probes import ProbeDetector,passive_features,MASKS
from monitor import EventStore
from research import Analyzer
from agent import DEFAULT_POLICY,normalize_policy,render

class Discovery(unittest.TestCase):
    def fixture(self,root):
        (root/"net").mkdir()
        (root/"net/tcp").write_text("header\n0: 00000000:01BB 00000000:0000 0A 0 0 0 0 0 901\n1: 0100007F:2222 00000000:0000 0A 0 0 0 0 0 902\n2: 00000000:3333 00000000:0000 01 0 0 0 0 0 903\n")
        (root/"net/udp").write_text("header\n0: 00000000:0035 00000000:0000 07 0 0 0 0 0 904\n1: 00000000:9999 0100007F:0035 01 0 0 0 0 0 905\n")
        (root/"net/tcp6").write_text("header\n0: 00000000000000000000000000000000:01BB 00000000000000000000000000000000:0000 0A 0 0 0 0 0 906\n")
        p=root/"101";(p/"fd").mkdir(parents=True)
        (p/"exe").symlink_to("/usr/bin/xray")
        (p/"fd/0").symlink_to("socket:[901]")
    def test_listeners_exclude_loopback_tcp_clients_connected_udp(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root)
            rows=Inventory(root).refresh()
            self.assertEqual({(x["protocol"],x["family"],x["port"]) for x in rows},{("tcp",4,443),("tcp",6,443),("udp",4,53)})
            self.assertEqual(next(x for x in rows if x["family"]==4 and x["protocol"]=="tcp")["processes"],[{"pid":101,"name":"xray"}])
            self.assertNotIn("inode",json.dumps(rows))
    def test_inventory_refresh_and_bounds_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);clock=[0]
            i=Inventory(root,limit=2,clock=lambda:clock[0]);self.assertEqual(len(i.refresh()),2)
            self.assertTrue(i.report()["truncated"])
            (root/"net/tcp").write_text("header\n")
            self.assertEqual(len(i.refresh()),2)
            clock[0]=20;self.assertEqual(len(i.refresh()),2)
            self.assertFalse(i.report()["public_reachability_verified"])
    def test_missing_inventory_keeps_explicit_port_protection(self):
        with tempfile.TemporaryDirectory() as d:
            i=Inventory(d);self.assertEqual(i.refresh(),[])
            self.assertIsNotNone(i.report()["error"])
            rule=dict(id="proxy",name="Proxy",enabled=True,protocol="both",ports=["443"],source_mode="dynamic",sources=[])
            text=render(effective_policy(normalize_policy(True,[rule],mode="whitelist"),[]),{})
            self.assertIn('tcp dport { 443 } counter drop',text)
            self.assertIn('udp dport { 443 } counter drop',text)
            self.assertNotIn('proxy-guard-default-deny',text)
    def test_discovery_never_enrolls_disabled_or_unselected_ports(self):
        rules=[dict(id="off",name="Off",enabled=False,protocol="tcp",ports=["443"],source_mode="dynamic",sources=[])]
        p=normalize_policy(True,rules,True,True)
        result=effective_policy(p,[dict(protocol="tcp",port=v) for v in [22,443,8443]])
        self.assertEqual([(x["id"],x["enabled"],x["ports"])for x in result["rules"]],[("off",False,["443"])])
        self.assertNotIn('drop',render(result,{}))
    def test_legacy_flags_do_not_expand_scope(self):
        p=normalize_policy(True,[],True,True)
        self.assertFalse(p["default_deny"]);self.assertFalse(p["auto_discover"])
        p.update(default_deny=True,auto_discover=True)
        self.assertNotIn('drop',render(p,{}))
        self.assertEqual(effective_policy(p,[dict(protocol="udp",port=34567)])["rules"],[])
    def test_policy_flags_reject_truthy_strings(self):
        for a,b in [("true",True),(True,1),(None,False)]:
            with self.assertRaises(ValueError):normalize_policy(True,[],a,b)

class Probes(unittest.TestCase):
    def setUp(self):
        self.e=EventStore();self.d=ProbeDetector(self.e,max_records=16,window=60)
        self.payload=bytes(range(256))
    def observe(self,payload,source="a",flow="first",now=1,complete=True):
        self.d.observe(payload,source,flow,("server",443),now,complete)
    def test_all_documented_replay_variants_match_only_their_offsets(self):
        for kind,positions in {"R1":(),**MASKS}.items():
            with self.subTest(kind=kind):
                self.setUp();self.observe(self.payload)
                modified=bytearray(self.payload)
                for i in positions:modified[i]^=255
                self.observe(bytes(modified),"b","second",2)
                events=self.e.snapshot()["events"]
                self.assertEqual(events[-1]["evidence"]["pattern"],kind)
                self.assertEqual(events[-1]["evidence"]["confidence"],"medium")
                self.assertEqual(events[-1]["evidence"]["attribution"],"unknown")
    def test_extra_modification_is_not_documented_replay(self):
        self.observe(self.payload);p=bytearray(self.payload);p[0]^=255;p[20]^=255
        self.observe(bytes(p),"b","second",2)
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_same_connection_retransmission_has_no_replay_alert(self):
        self.observe(self.payload);self.observe(self.payload,now=2)
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_common_protocol_repetition_is_not_probe_alert(self):
        for p in [b"GET / HTTP/1.1\r\n"+b"x"*100,b"\x16\x03\x03"+bytes(range(200)),b"SSH-2.0-OpenSSH_9.0"+b"x"*100]:
            self.observe(p);self.observe(p,"b","other",2)
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_one_historical_length_is_not_an_alert(self):
        self.observe(bytes(range(221)))
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_multiple_distinct_historical_lengths_form_weak_evidence(self):
        for i,n in enumerate([63,64,65]):self.observe(bytes((j+i)%256 for j in range(n)),flow=str(i),now=i+1)
        row=self.e.snapshot()["events"][-1]
        self.assertEqual(row["kind"],"historical_probe_length_cluster")
        self.assertEqual(row["evidence"]["confidence"],"low")
    def test_ciphertext_risk_alone_is_not_active_probe_alert(self):
        p=bytes([0x55,0xaa,0x96,0x69])*70
        self.assertTrue(passive_features(p)["historical_passive_nonexempt"])
        self.observe(p);self.assertEqual(self.e.snapshot()["retained"],0)
    def test_incomplete_payload_never_matches(self):
        self.observe(self.payload,complete=False);self.observe(self.payload,"b","second",2)
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_reference_expires_and_cache_is_bounded(self):
        self.observe(self.payload);self.observe(self.payload,"b","second",100)
        self.assertEqual(self.e.snapshot()["retained"],0)
        for i in range(100):self.observe(bytes([i])*200,source=str(i),flow=str(i),now=101+i)
        self.assertLessEqual(len(self.d.records),16);self.assertLessEqual(len(self.d.index),80)
        self.assertLessEqual(len(self.d.sources),17)
    def test_burst_events_are_deduplicated_and_addresses_not_exported(self):
        for i in range(40):self.d.syn("192.0.2.1",("server",443),i/10)
        events=self.e.snapshot()["events"]
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]["kind"],"connection_attempt_burst")
        self.assertNotIn("192.0.2.1",json.dumps(events))
    def test_idle_expiry_removes_old_payload_evidence(self):
        a=Analyzer(self.e,window=10,probe_detection=True)
        base=dict(protocol="tcp",src="a",dst="b",sport=1000,dport=443,truncated=False)
        a.feed(dict(base,seq=100,flags=2,payload=b""),1)
        a.feed(dict(base,seq=101,flags=16,payload=self.payload),2)
        a.expire(20)
        self.assertEqual(len(a.flows),0);self.assertEqual(len(a.digests),0);self.assertEqual(len(a.probes.records),0)

    def test_syn_only_activity_does_not_evict_unexpired_payload_references(self):
        for i in range(16):self.observe(bytes([i])*200,flow=str(i),now=1)
        self.assertEqual(len(self.d.records),16)
        for i in range(30):self.d.syn("scan",("server",443),2+i/100)
        self.assertEqual(len(self.d.records),16)

    def test_diagnostic_passive_rules_remain_distinct_from_noise_exclusions(self):
        features=passive_features(b"SSH-"+b"\x96"*100)
        self.assertEqual(features["common_prefix"],"other_common_prefix")
        self.assertTrue(features["historical_passive_nonexempt"])
        self.observe(b"SSH-"+b"\x96"*100)
        self.assertEqual(self.e.snapshot()["retained"],0)

    def test_missing_syn_does_not_create_payload_replay_evidence(self):
        a=Analyzer(self.e,probe_detection=True)
        for sport in [1000,1001]:
            a.feed(dict(protocol="tcp",src="a",dst="b",sport=sport,dport=443,seq=1,flags=16,payload=self.payload,truncated=False),1)
        self.assertEqual(self.e.snapshot()["retained"],0)
    def test_common_protocol_prefixes_do_not_create_generic_alerts_in_probe_mode(self):
        a=Analyzer(self.e,probe_detection=True)
        for sport in [1000,1001]:
            base=dict(protocol="tcp",src="a",dst="b",sport=sport,dport=443,truncated=False)
            a.feed(dict(base,seq=100,flags=2,payload=b""),sport)
            a.feed(dict(base,seq=101,flags=16,payload=b"GET / HTTP/1.1"+b"x"*300),sport+1)
        self.assertEqual(self.e.snapshot()["retained"],0)

    def test_reordered_segments_keep_prefix_analysis_separate_from_packet_lengths(self):
        a=Analyzer(self.e,probe_detection=True)
        for sport,now in [(1000,1),(1001,10)]:
            base=dict(protocol="tcp",src="a",dst="b",sport=sport,dport=443,truncated=False)
            a.feed(dict(base,seq=100,flags=2,payload=b""),now)
            a.feed(dict(base,seq=229,flags=16,payload=self.payload[128:]),now+1)
            a.feed(dict(base,seq=101,flags=16,payload=self.payload[:128]),now+2)
        self.assertEqual(a.counts["repeated_prefixes"],1)
        self.assertEqual(a.probes.counts["first_payloads"],2)



class ReportBounds(unittest.TestCase):
    def test_optional_evidence_never_overflows_the_health_response_budget(self):
        import threading
        from control import Server
        server=object.__new__(Server)
        server.engine=type("E",(),{"lock":threading.Lock(),"leases":{},"ready":True,"state":{"revision":1,"policy":DEFAULT_POLICY}})()
        rows=[{"protocol":"tcp","port":10000+i,"bind":"::","family":6,"processes":[{"pid":j,"name":"x"*64} for j in range(4)]} for i in range(48)]
        server.engine.inventory=type("I",(),{"report":lambda _:{"listeners":rows.copy(),"count":48,"truncated":False}})()
        server.edition="pro";server.firewall={"verified":True};server.sensors=None
        server.monitor=type("M",(),{"status":lambda _:{"ok":True,"configured":True}})()
        server.events=EventStore()
        for _ in range(20):server.events.add("test",**{"field_"+str(j):"x"*160 for j in range(8)})
        server.engine.trials=type('TrialStatus',(),{'status':lambda self:{'supported':True,'phase':'idle'}})()
        report=server.status()
        self.assertLessEqual(len(json.dumps(report,separators=(",",":")).encode()),30000)
        self.assertTrue(report["health"]["ok"]);self.assertTrue(report["report_truncated"])
        self.assertTrue(report["events"]["truncated"] or report["inventory"]["truncated"])

class OwnershipAndBootstrap(unittest.TestCase):
    def test_owner_is_unique_and_recovers_after_release(self):
        from agent import claim_owner,Invalid
        with tempfile.TemporaryDirectory() as d:
            with claim_owner(d):
                with self.assertRaises(Invalid):
                    with claim_owner(d):pass
            with claim_owner(d) as fd:self.assertGreaterEqual(fd,0)
    def test_nft_child_holds_owner_until_the_transaction_finishes(self):
        import threading,time
        from agent import claim_owner,Nft,Invalid
        with tempfile.TemporaryDirectory() as d:
            ready=Path(d)/'ready';release=Path(d)/'release';result=[]
            # A shell handshake avoids timing a Python interpreter startup or
            # racing a fixed sleep under software-emulated VM CPU load.
            code='test -e "/proc/$$/fd/$1" || exit 2; : > "$2"; while [ ! -e "$3" ]; do sleep 0.02; done'
            with claim_owner(d) as fd:
                driver=Nft(binary='/bin/sh',owner_fd=fd)
                worker=threading.Thread(target=lambda:result.append(driver.call(['-c',code,'pg-owner',str(fd),str(ready),str(release)])))
                worker.start()
                end=time.monotonic()+5
                while not ready.exists() and time.monotonic()<end:time.sleep(.01)
                self.assertTrue(ready.exists())
            try:
                with self.assertRaises(Invalid):
                    with claim_owner(d):pass
            finally:release.touch()
            worker.join(5);self.assertFalse(worker.is_alive());self.assertEqual(result[0].returncode,0)
            with claim_owner(d):pass

    def test_static_bootstrap_matches_the_config_independent_policy(self):
        import agent
        expected=f"add table inet {agent.BOOT}\ndelete table inet {agent.BOOT}\n"+agent.render(agent.DEFAULT_POLICY,{},agent.BOOT)
        self.assertEqual((R/'companion/vps/bootstrap.nft').read_text(),expected)

if __name__=="__main__":unittest.main()
