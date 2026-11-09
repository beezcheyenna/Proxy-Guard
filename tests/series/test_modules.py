import importlib.util,json,os,struct,sys,tempfile,time,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"companion/vps"))
from monitor import EventStore,Monitor,service_config
from research import Analyzer,Prefix,packet
from sensors import capture_config,Honeypot
from audit import aggregate,analyze
import agent

def tcp(seq,payload=b"",sport=4000,flags=16,src="8.8.8.8",dst="8.8.4.4"):
    return {"protocol":"tcp","src":src,"dst":dst,"sport":sport,"dport":443,"seq":seq,
            "flags":flags,"payload":payload,"truncated":False}

def frame(seq,payload=b"",sport=4000,flags=16):
    import ipaddress
    segment=struct.pack("!HHIIBBHHH",sport,443,seq,0,80,flags,4096,0,0)+payload
    ip=struct.pack("!BBHHHBBH4s4s",69,0,20+len(segment),0,0,64,6,0,
                   ipaddress.ip_address("8.8.8.8").packed,ipaddress.ip_address("8.8.4.4").packed)+segment
    return b"\0"*12+b"\x08\x00"+ip

class Modules(unittest.TestCase):
    def test_services_are_explicit_and_not_shell_commands(self):
        for value in ([{"name":"x;id","process_names":["xray"]}],
                      [{"name":"x","process_names":["xray;id"]}],
                      [{"name":"x","process_names":["xray"],"tcp_ports":[True]}]):
            with self.assertRaises(ValueError):service_config(value)
        self.assertEqual(service_config([{"name":"x","process_names":["xray"],"tcp_ports":[443,443]}])[0]["tcp"],[443])

    def test_monitor_checks_process_socket_ownership_and_start_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"net").mkdir();p=root/"101";(p/"fd").mkdir(parents=True)
            (p/"exe").symlink_to("/usr/bin/xray")
            fields=["S"]+["0"]*18+["123"]
            (p/"stat").write_text("101 (a name) "+" ".join(fields))
            (p/"fd/1").symlink_to("socket:[900]")
            (root/"net/tcp").write_text("header\n 0: 00000000:01BB 00000000:0000 0A 0 0 0 0 0 900\n")
            m=Monitor({"services":[{"name":"x","process_names":["xray"],"tcp_ports":[443]}]},proc=root)
            self.assertTrue(m.sample()["ok"])
            (p/"fd/1").unlink()
            self.assertFalse(m.sample()["ok"])
            self.assertEqual(m.events.snapshot()["counts"]["service_down"],1)

    def test_empty_monitor_is_not_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            m=Monitor({"services":[]},proc=directory)
            self.assertFalse(m.sample()["ok"]);self.assertFalse(m.status()["configured"])

    def test_event_count_retention_and_clear(self):
        clock=[1000]
        events=EventStore(64,60,lambda:clock[0])
        for _ in range(80):events.add("test",value=1)
        self.assertEqual(events.snapshot()["retained"],64)
        clock[0]+=61
        self.assertEqual(events.snapshot()["retained"],0)
        events.clear();self.assertEqual(events.snapshot()["counts"],{})

    def test_event_payload_does_not_accept_containers_or_control_characters(self):
        e=EventStore();e.add("test",message="a\nb",bad={"secret":"x"})
        row=e.snapshot()["events"][0]
        self.assertEqual(row["evidence"]["message"],"ab")
        self.assertNotIn("bad",row["evidence"])

    def test_capture_requires_explicit_ports_and_bounded_options(self):
        for c in ({"enabled":True},{"interface":"any; id"},{"ports":[True]},{"duration":0},{"file_count":100}):
            with self.assertRaises(ValueError):capture_config(c)
        self.assertFalse(capture_config({})["enabled"])
        self.assertFalse(capture_config({})["save_pcap"])

    def test_honeypot_rejects_privileged_ports(self):
        for c in ({"tcp_port":22},{"bind":"0.0.0.0;id"},{"udp_port":True}):
            with self.assertRaises(ValueError):Honeypot(c,EventStore())

    def test_tcp_reassembly_reordering_and_retransmission(self):
        e=EventStore();a=Analyzer(e)
        payload=bytes(range(256))
        a.feed(tcp(100,flags=2),1)
        a.feed(tcp(229,payload[128:]),2)
        a.feed(tcp(101,payload[:128]),3)
        a.feed(tcp(101,payload),4)
        self.assertEqual(len(a.digests),1)
        self.assertEqual(e.snapshot()["retained"],0)

    def test_cross_connection_prefix_is_suspicion_not_attribution(self):
        e=EventStore();a=Analyzer(e)
        for sport,offset in ((4000,1),(4001,10)):
            a.feed(tcp(100,flags=2,sport=sport),offset)
            a.feed(tcp(101,bytes(range(256)),sport=sport),offset+1)
        event=e.snapshot()["events"][0]
        self.assertEqual(event["kind"],"repeated_tcp_prefix")
        self.assertEqual(event["evidence"]["confidence"],"low")
        self.assertEqual(event["evidence"]["attribution"],"unknown")
        self.assertNotIn("8.8.8.8",json.dumps(event))

    def test_echo_in_one_connection_is_not_cross_connection_replay(self):
        e=EventStore();a=Analyzer(e)
        a.feed(tcp(100,flags=2),1);a.feed(tcp(101,b"x"*256),2)
        reverse=tcp(200,flags=18,src="8.8.4.4",dst="8.8.8.8",sport=443);reverse["dport"]=4000
        a.feed(reverse,3);a.feed(dict(reverse,seq=201,flags=16,payload=b"x"*256),4)
        self.assertEqual(e.snapshot()["retained"],0)

    def test_midstream_capture_and_udp_not_mislabelled_as_replay(self):
        e=EventStore();a=Analyzer(e)
        for p in (4000,4001):a.feed(tcp(101,b"x"*256,sport=p),p)
        for _ in range(2):a.feed({"protocol":"udp","src":"8.8.8.8","dst":"8.8.4.4","sport":12,"dport":53,"payload":b"x"*256,"truncated":False})
        self.assertEqual(e.snapshot()["retained"],0)

    def test_sequence_wrap_and_conflicting_retransmission(self):
        p=Prefix(0xfffffff0)
        self.assertIsNotNone(p.feed(0xfffffff0,b"x"*256))
        q=Prefix(100)
        self.assertIsNone(q.feed(100,b"x"*128))
        self.assertIsNone(q.feed(100,b"y"*256))
        self.assertTrue(q.conflict)

    def test_packet_parser_truncated_fragment_and_tcp(self):
        data=frame(101,b"x"*256)
        item=packet(data);self.assertEqual(item["payload"],b"x"*256)
        self.assertTrue(packet(data[:-4])["truncated"])
        fragmented=bytearray(data);fragmented[20:22]=b"\x20\x00"
        self.assertEqual(packet(fragmented),{"skipped":"fragment"})
        for length in range(35):packet(data[:length])

    def test_flow_and_digest_memory_bounded(self):
        a=Analyzer(EventStore(),max_flows=16)
        for sport in range(100,200):
            a.feed(tcp(100,flags=2,sport=sport),1)
            a.feed(tcp(101,bytes([sport])*256,sport=sport),2)
        self.assertLessEqual(len(a.flows),16);self.assertLessEqual(len(a.digests),16)

    def test_pcap_roundtrip_and_two_node_report(self):
        records=[]
        for sport in (4000,4001):
            for seq,payload,flags in ((100,b"",2),(101,bytes(range(256)),16)):
                data=frame(seq,payload,sport,flags)
                records.append(struct.pack("<IIII",1000+sport,0,len(data),len(data))+data)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"fixture.pcap"
            path.write_bytes(struct.pack("<IHHIIII",0xa1b2c3d4,2,4,0,0,8192,1)+b"".join(records))
            first=analyze(path,"a");second=analyze(path,"b")
            merged=aggregate([first,second])
            self.assertEqual(first["packets"],4)
            self.assertTrue(merged["prefix_matches"])
            self.assertNotIn("8.8.8.8",json.dumps(first))
            self.assertFalse(first["privacy"]["raw_packets"])

    def test_aggregate_rejects_duplicate_nodes_or_bad_digest(self):
        with self.assertRaises(ValueError):aggregate([{"node":"a"},{"node":"a"}])
        with self.assertRaises(ValueError):aggregate([{"node":"a","prefix_observations":[{"digest":"bad"}]}])

    def test_health_only_export_omits_analysis_and_event_logs(self):
        from control import Server
        import threading
        server=object.__new__(Server)
        server.engine=type("EngineStub",(),{"lock":threading.Lock(),"leases":{},"state":{"revision":1,"policy":agent.DEFAULT_POLICY},"ready":True})()
        server.engine.inventory=type("InventoryStub",(),{"report":lambda _:{"listeners":[],"count":0}})()
        server.edition="pro-max";server.firewall={"verified":True}
        server.monitor=type("MonitorStub",(),{"status":lambda _:{"ok":True}})()
        server.events=EventStore();server.events.add("service_down",service="test")
        server.sensors=type("SensorsStub",(),{"status":lambda _:{"capture":{"state":"running"}}})()
        health=server.status(include_analysis=False)
        self.assertNotIn("events",health);self.assertNotIn("analysis",health)
        self.assertFalse(health["analysis_exported"])
        full=server.status(include_analysis=True)
        self.assertIn("events",full);self.assertIn("analysis",full)

    def test_agent_template_leaves_ssh_and_unselected_ports_to_system_firewall(self):
        p=agent.normalize_policy(**{"enabled":True,"rules":agent.DEFAULT_POLICY["rules"]})
        script=agent.render(p,{})
        self.assertEqual(p["rules"],[])
        self.assertNotIn("drop",script)
        self.assertNotIn("dport",script)
        self.assertNotIn("flush ruleset",script)
        self.assertIn("hook input priority -150",script)

if __name__=="__main__":unittest.main()
