import json,subprocess,sys,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"companion/vps"))
import manage_units

class InstallContracts(unittest.TestCase):
 def test_ordering_only_touches_owned_dropins(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   foreign=root/"etc/systemd/system/xray.service.d/user.conf"
   foreign.parent.mkdir(parents=True);foreign.write_text("[Service]\nNice=5\n")
   manage_units.apply(root,["xray.service"])
   owned=foreign.parent/"50-proxy-guard-access.conf"
   self.assertIn("Requires=proxy-guard-access-policy.service",owned.read_text())
   manage_units.apply(root,[],remove=True)
   self.assertFalse(owned.exists());self.assertTrue(foreign.exists())
 def test_ssh_and_path_injection_are_not_managed(self):
  for name in ("ssh.service","sshd.service","dropbear.service","../../network.service","x.service;id"):
   with self.assertRaises(ValueError):manage_units.names([name])
 def test_foreign_file_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/"etc/systemd/system/xray.service.d/50-proxy-guard-access.conf"
   p.parent.mkdir(parents=True);p.write_text("foreign")
   with self.assertRaises(ValueError):manage_units.apply(directory,["xray.service"])
   self.assertEqual(p.read_text(),"foreign")
 def check_config(self,config):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);p=root/"agent.json";p.write_text(json.dumps(config))
   result=subprocess.run([sys.executable,"-B",str(R/"companion/vps/agent.py"),"--config",str(p),"--state",str(root/"state.json"),"--check-config"],capture_output=True,text=True)
   self.assertFalse((root/"state.json").exists(),"preflight must not change firewall state")
   return result
 def test_config_check_is_read_only_and_hides_secrets(self):
  result=self.check_config({"device_id":"home","agent_secret":"a"*40,"services":[]})
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertNotIn("a"*40,result.stdout)
 def test_external_http_is_rejected_before_firewall_changes(self):
  result=self.check_config({"device_id":"home","agent_secret":"a"*40,"bind":"0.0.0.0","direct_token":"d"*40})
  self.assertNotEqual(result.returncode,0)
  self.assertIn("external_bind_requires_https",result.stderr)
 def test_pro_cannot_silently_enable_max_sensors(self):
  result=self.check_config({"device_id":"home","agent_secret":"a"*40,"edition":"pro","analysis":{"honeypot":{"enabled":True}}})
  self.assertNotEqual(result.returncode,0)
  self.assertIn("evidence_capture_requires_pro_max",result.stderr)

 def test_public_https_control_requires_explicit_local_confirmation(self):
  result=self.check_config({"device_id":"home","agent_secret":"a"*40,"bind":"0.0.0.0","direct_token":"d"*40,"tls_cert":"fixture.crt","tls_key":"fixture.key"})
  self.assertNotEqual(result.returncode,0)
  self.assertIn("public_control_confirmation_required",result.stderr)

 def test_custom_control_port_is_shared_by_preflight_and_boot_policy(self):
  result=self.check_config({"device_id":"home","agent_secret":"a"*40,"port":9443})
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(json.loads(result.stdout)["port"],9443)
 def test_invalid_configured_control_ports_are_rejected(self):
  for port in [True,0,65536,"9443"]:
   result=self.check_config({"device_id":"home","agent_secret":"a"*40,"port":port})
   self.assertNotEqual(result.returncode,0)
   self.assertIn("invalid_control_port",result.stderr)

 def test_malformed_service_rows_fail_without_traceback(self):
  for row in (None,False,1,[],"xray"):
   result=self.check_config({"device_id":"home","agent_secret":"a"*40,"services":[row]})
   self.assertNotEqual(result.returncode,0)
   self.assertNotIn("Traceback",result.stderr)

 def test_kernel_check_does_not_print_success_before_validation(self):
  import agent,contextlib,io
  from unittest.mock import patch
  with tempfile.TemporaryDirectory()as tmp:
   config=Path(tmp)/'agent.json';config.write_text(json.dumps({"device_id":"home","agent_secret":"a"*40}))
   output=io.StringIO()
   with patch.object(sys,'argv',['agent','--config',str(config),'--check-kernel']),patch.object(agent.os,'geteuid',return_value=0),patch.object(agent.Nft,'call',return_value=subprocess.CompletedProcess([],1)),contextlib.redirect_stdout(output):
    with self.assertRaisesRegex(agent.Invalid,'kernel_resource_limits_unavailable'):agent.main()
   self.assertEqual(output.getvalue(),'')

