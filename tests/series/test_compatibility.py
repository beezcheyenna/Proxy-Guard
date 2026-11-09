import importlib.util,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'companion/vps'))
import manage_units,maintenance
class OpenRC(unittest.TestCase):
 def test_existing_configuration_and_mode_survive_add_remove(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);p=root/'etc/conf.d/xray';p.parent.mkdir(parents=True)
   original='command_args="--private-config /etc/xray/config.json"\n'
   p.write_text(original);p.chmod(0o600)
   manage_units.apply_openrc(root,['xray.service'])
   self.assertTrue(p.read_text().startswith(original));self.assertEqual(p.stat().st_mode&0o777,0o600)
   manage_units.apply_openrc(root,[],True);self.assertEqual(p.read_text(),original)
 def test_install_is_idempotent(self):
  with tempfile.TemporaryDirectory()as tmp:
   manage_units.apply_openrc(tmp,['xray.service']);p=Path(tmp)/'etc/conf.d/xray';old=p.read_bytes()
   manage_units.apply_openrc(tmp,['xray.service']);self.assertEqual(old,p.read_bytes())
 def test_foreign_block_is_rejected_without_overwrite(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'etc/conf.d/xray';p.parent.mkdir(parents=True);p.write_text(manage_units.OPENRC_MARKER+'\nuser change\n')
   before=p.read_bytes()
   with self.assertRaisesRegex(ValueError,'foreign_openrc_block'):manage_units.apply_openrc(tmp,['xray.service'])
   self.assertEqual(before,p.read_bytes())
 def test_ssh_is_never_a_managed_openrc_dependency(self):
  with tempfile.TemporaryDirectory()as tmp:
   with self.assertRaises(ValueError):manage_units.apply_openrc(tmp,['sshd.service'])
   self.assertFalse((Path(tmp)/'etc/conf.d').exists())
 def test_missing_final_newline_does_not_merge_shell_directives(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'etc/conf.d/xray';p.parent.mkdir(parents=True);p.write_text('secret=private')
   with self.assertRaisesRegex(ValueError,'unterminated_openrc_config'):manage_units.apply_openrc(tmp,['xray.service'])
   self.assertEqual(p.read_text(),'secret=private')
 def test_fixed_openrc_restart_has_no_shell_or_user_command(self):
  cfg=maintenance.config({'adapter':'openrc','unit':'xray.service'})
  with patch.object(maintenance.subprocess,'run')as run:
   maintenance.execute('restart_xray',cfg)
   self.assertEqual(run.call_args.args[0],['/sbin/rc-service','xray','restart'])
   self.assertNotIn('shell',run.call_args.kwargs)
 def test_fixed_openrc_reboot(self):
  cfg=maintenance.config({'adapter':'openrc'})
  with patch.object(maintenance.subprocess,'run')as run:
   maintenance.execute('reboot_vps',cfg);self.assertEqual(run.call_args.args[0],['/sbin/reboot'])
 def test_native_xui_openrc_uses_reload_without_restarting_panel(self):
  cfg=maintenance.config({'adapter':'3x-ui-openrc','xui_usr1_confirmed':True})
  with patch.object(maintenance.subprocess,'run')as run:
   maintenance.execute('restart_xray',cfg)
   self.assertEqual(run.call_args.args[0],['/sbin/rc-service','x-ui','reload'])
 def test_xui_openrc_signal_still_requires_explicit_confirmation(self):
  cfg=maintenance.config({'adapter':'3x-ui-openrc'})
  with patch.object(maintenance.subprocess,'run')as run:
   with self.assertRaisesRegex(ValueError,'xui_usr1_not_confirmed'):maintenance.execute('restart_xray',cfg)
   run.assert_not_called()
 def test_xui_openrc_reboots_with_native_init(self):
  cfg=maintenance.config({'adapter':'3x-ui-openrc'})
  with patch.object(maintenance.subprocess,'run')as run:
   maintenance.execute('reboot_vps',cfg);self.assertEqual(run.call_args.args[0],['/sbin/reboot'])
 def test_unknown_service_backend_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'invalid_maintenance_adapter'):maintenance.config({'adapter':'custom shell'})
if __name__=='__main__':unittest.main(verbosity=2)
