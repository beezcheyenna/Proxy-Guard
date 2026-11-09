import contextlib
import copy
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'companion/vps'))
import agent

class BootstrapRetry(unittest.TestCase):
    def setUp(self):
        self.driver = agent.Nft()
        self.policy = copy.deepcopy(agent.DEFAULT_POLICY)
        self.policy = agent.normalize_policy(True, [{'id':'selected','name':'Selected proxy port','enabled':True,
            'protocol':'tcp','ports':['24443'],'source_mode':'dynamic','sources':[]}])

    def test_transient_startup_timeout_retries_identical_static_policy(self):
        committed=[]
        def commit(text):
            committed.append(text)
            if len(committed)==1:raise subprocess.TimeoutExpired(['/usr/sbin/nft','-c'],8)
        with patch.object(self.driver,'commit',side_effect=commit),patch.object(agent.time,'sleep')as sleep,contextlib.redirect_stderr(io.StringIO()):
            self.driver.bootstrap(self.policy)
        self.assertEqual(len(committed),2)
        self.assertEqual(committed[0],committed[1])
        self.assertIn('24443',committed[1])
        self.assertNotIn('pg_vps_access_update',committed[1])
        sleep.assert_called_once_with(1)

    def test_permanent_timeouts_are_bounded_and_propagated(self):
        with patch.object(self.driver,'commit',side_effect=subprocess.TimeoutExpired(['nft'],8))as commit,patch.object(agent.time,'sleep')as sleep,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.TimeoutExpired):self.driver.bootstrap(self.policy)
        self.assertEqual(commit.call_count,3)
        self.assertEqual(sleep.call_count,2)

    def test_invalid_firewall_transaction_is_not_retried(self):
        with patch.object(self.driver,'commit',side_effect=RuntimeError('firewall_update_failed'))as commit,patch.object(agent.time,'sleep')as sleep:
            with self.assertRaisesRegex(RuntimeError,'firewall_update_failed'):self.driver.bootstrap(self.policy)
        commit.assert_called_once();sleep.assert_not_called()

    def test_retry_rerenders_relative_deadlines_without_dynamic_leases(self):
        timeout = subprocess.TimeoutExpired(['nft'],8)
        with patch.object(agent,'render',side_effect=['first_deadline','current_deadline'])as render,patch.object(self.driver,'commit',side_effect=[timeout,None])as commit,patch.object(agent.time,'sleep'),contextlib.redirect_stderr(io.StringIO()):
            self.driver.bootstrap(self.policy)
        self.assertTrue(commit.call_args.args[0].endswith('current_deadline'))
        self.assertEqual(render.call_args.args,(self.policy,{},agent.BOOT))
        self.assertEqual(render.call_count,2)

    def test_normal_policy_commit_timeout_is_not_replayed(self):
        with patch.object(self.driver,'call',side_effect=subprocess.TimeoutExpired(['nft'],8))as call:
            with self.assertRaises(subprocess.TimeoutExpired):self.driver.commit('add table inet test')
        call.assert_called_once_with(['-c','-f','-'],'add table inet test')

if __name__=='__main__':unittest.main()
