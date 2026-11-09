"""Agent persistence/lease contract; no firewall or host maintenance execution."""
import sys,tempfile,json,hmac,hashlib,time,uuid,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'vps'))
from agent import Engine,Invalid
class Driver:
    def apply(self,policy,leases):self.leases=dict(leases)
class Contract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'state';self.driver=Driver();self.engine=Engine('a'*40,'home',self.path,self.driver)
    def payload(self,**changes):
        data=dict(device_id='home',observed_ip='8.8.8.8',policy_enabled=True,rules=[],revision=1,ttl=120,issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()));data.update(changes)
        raw=json.dumps(data).encode();return raw,hmac.new(b'a'*40,raw,hashlib.sha256).hexdigest()
    def test_durable_replay_reservation_and_no_cold_lease_restore(self):
        raw,sig=self.payload();self.engine.sync(raw,sig);new=Engine('a'*40,'home',self.path,Driver())
        self.assertEqual(new.leases,{});self.assertEqual(new.state['revision'],1)
        with self.assertRaisesRegex(Invalid,'replayed_or_stale_request'):new.sync(raw,sig)
    def test_acknowledged_expiry_does_not_overstate_kernel_lease_after_slow_apply(self):
        raw,sig=self.payload()
        with patch('agent.time.monotonic',side_effect=[100.0,110.0]):result=self.engine.sync(raw,sig)
        self.assertLessEqual(result['expires_at']-result['applied_at'],110)
    def test_invalid_ttl_and_future_or_old_timestamp(self):
        for changes in [{'ttl':119},{'ttl':86401},{'ttl':True},{'issued_at':int(time.time()*1000)-120001},{'issued_at':int(time.time()*1000)+130000}]:
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.engine.sync(*self.payload(**changes))
        self.assertEqual(self.engine.leases,{})
    def test_monotonic_expiry_and_ipv4_ipv6_independence(self):
        with patch('agent.time.monotonic',return_value=100):self.engine.sync(*self.payload())
        self.assertEqual(self.engine.leases[4],('8.8.8.8',220))
        with patch('agent.time.monotonic',return_value=110):self.engine.sync(*self.payload(observed_ip='2606:4700:4700::1111'))
        self.assertEqual(self.engine.leases[4][1],220);self.assertEqual(self.engine.leases[6][1],230)
    def test_failed_apply_reserves_signed_message_without_rollback_to_old_source(self):
        raw,sig=self.payload()
        with patch.object(self.driver,'apply',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.engine.sync(raw,sig)
        self.assertFalse(self.engine.ready)
        with self.assertRaisesRegex(Invalid,'replayed_or_stale_request'):self.engine.sync(raw,sig)
    def test_unselected_address_family_never_gets_lease(self):
        with self.assertRaisesRegex(Invalid,'source_family_not_selected'):self.engine.sync(*self.payload(address_families=[6]))
        self.assertEqual(self.engine.leases,{})
if __name__=='__main__':unittest.main(verbosity=2)
