#!/usr/bin/env python3
"""Standard/Pro checks for a prepared disposable Linux test VM; no cloud deployment."""
from pathlib import Path
import ast,json,os,platform,subprocess,sys,unittest
R=Path(__file__).resolve().parents[1]
def main():
    if platform.system()!='Linux' or not (Path('/etc/pgvm-fixture').is_file() or Path('/.proxy-guard-test-root').is_file()):raise SystemExit('Prepared disposable Linux VM required; do not create the fixture marker on a normal host.')
    os.chdir(R);sys.dont_write_bytecode=True
    sys.path[:0]=[str(R/'tests/series'),str(R/'companion/vps')]
    for name in ('agent','protection','safety','maintenance','reality_check','telemetry','control','monitor','egress','policy_trial'):ast.parse((R/f'companion/vps/{name}.py').read_text())
    names=['test_versioning','test_bootstrap_retry','test_policy_trial','test_compatibility','test_pro_features','test_install.InstallContracts','test_ingress_probes.Discovery','test_ingress_probes.OwnershipAndBootstrap','test_ingress_probes.ReportBounds']
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    if not result.wasSuccessful():raise SystemExit(1)
    subprocess.run([sys.executable,'-B','tests/access/agent_test.py'],check=True)
    subprocess.run([sys.executable,'-B','companion/vps/test_egress.py'],check=True)
    subprocess.run(['node','--test','--test-name-pattern','Pro','tests/series/ui.test.mjs'],check=True)
    if Path('/etc/pgvm-fixture').is_file()or Path('/.proxy-guard-test-root').is_file():
        subprocess.run(['sh','tests/setup_boot_test.sh'],check=True)
    from build_translations import verify
    verify()
    print('PASS basic Standard/Pro logic, UI and catalogs; no Cloudflare or production actions.')
    print('Native Lua/ucode and real packet checks run separately in the offline VM.')
if __name__=='__main__':main()
