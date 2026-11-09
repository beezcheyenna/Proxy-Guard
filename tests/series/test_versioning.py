"""Independent package releases against an explicit stable base API."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

R = Path(__file__).resolve().parents[2]


def package_control(path):
    with tarfile.open(path, 'r:gz') as outer:
        data = outer.extractfile('./control.tar.gz').read()
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        return {Path(m.name).name: archive.extractfile(m).read()
                for m in archive if m.isfile()}


class IndependentVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pg-version-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'src'
        for name in ('package', 'tools'):
            shutil.copytree(R / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__', 'node_modules'))
        self.makefile = self.root / 'package/Makefile'

    def set_value(self, name, value):
        text, count = re.subn(r'^' + name + r':=.*$', name + ':=' + value,
                             self.makefile.read_text(), flags=re.M)
        self.assertEqual(count, 1)
        self.makefile.write_text(text)

    def build(self, name, only=None, success=True):
        out = Path(self.tmp.name) / name
        args = [sys.executable, '-B', str(self.root / 'tools/build_ipk.py'),
                '--edition', 'pro', '--output', str(out)]
        if only:
            args += ['--only', only]
        done = subprocess.run(args, capture_output=True, text=True, timeout=180)
        if success:
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        else:
            self.assertNotEqual(done.returncode, 0)
            self.assertIn('Base API manifest differs from Makefile', done.stderr)
            self.assertFalse(any(out.glob('*.ipk')))
        return out

    def by_name(self, out, package):
        matches = [p for p in out.glob('*.ipk')
                   if package_control(p)['control'].decode().splitlines()[0] == 'Package: ' + package]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_pro_release_does_not_change_base_and_sdk_matches(self):
        before = self.build('before')
        base = self.by_name(before, 'luci-app-proxy-guard').read_bytes()
        self.set_value('PG_PRO_VERSION', '0.3.2')
        self.set_value('PG_PRO_RELEASE', '7')
        after = self.build('after')
        self.assertEqual(base, self.by_name(after, 'luci-app-proxy-guard').read_bytes())
        pro = self.by_name(after, 'luci-app-proxy-guard-pro')
        ctl = package_control(pro)
        self.assertEqual(pro.name, 'luci-app-proxy-guard-pro_0.3.2-7_all.ipk')
        self.assertIn('Version: 0.3.2-7', ctl['control'].decode())
        self.assertIn('Depends: luci-app-proxy-guard (>= 0.3.0-13)', ctl['control'].decode())
        self.assertNotIn('core").VERSION', ctl['preinst'].decode())
        self.assertNotIn('$(PG_', ctl['preinst'].decode())
        self.assertIn('base API 1', ctl['preinst'].decode())
        sdk = subprocess.run([sys.executable, '-B', str(self.root / 'tools/test_sdk_staging.py'),
                              '--packages', str(after)], capture_output=True, text=True, timeout=180)
        self.assertEqual(sdk.returncode, 0, sdk.stdout + sdk.stderr)
        single = self.build('pro-only', only='pro')
        self.assertEqual(sorted(p.name for p in single.glob('*.ipk')), [pro.name])
        self.assertEqual(pro.read_bytes(), (single / pro.name).read_bytes())
        manifest = json.loads((single / 'files.json').read_text())
        self.assertEqual(set(manifest), {'luci-app-proxy-guard-pro'})
        self.assertEqual(manifest['luci-app-proxy-guard-pro']['version'], '0.3.2-7')
        self.assertEqual((single / 'SHA256SUMS').read_text().strip(),
                         hashlib.sha256(pro.read_bytes()).hexdigest() + '  ' + pro.name)

    def test_compatible_base_release_does_not_change_pro(self):
        before = self.build('before')
        pro = self.by_name(before, 'luci-app-proxy-guard-pro').read_bytes()
        self.set_value('PKG_VERSION', '9.9.9')
        self.set_value('PKG_RELEASE', '7')
        core = self.root / 'package/root/usr/lib/proxy-guard/core.lua'
        core.write_text(re.sub(r"M.VERSION = '[^']+'", "M.VERSION = '9.9.9'", core.read_text()))
        after = self.build('after')
        self.assertEqual(pro, self.by_name(after, 'luci-app-proxy-guard-pro').read_bytes())
        self.assertEqual(self.by_name(after, 'luci-app-proxy-guard').name,
                         'luci-app-proxy-guard_9.9.9-7_all.ipk')
        sdk = subprocess.run([sys.executable, '-B', str(self.root / 'tools/test_sdk_staging.py'),
                              '--packages', str(after)], capture_output=True, text=True, timeout=180)
        self.assertEqual(sdk.returncode, 0, sdk.stdout + sdk.stderr)

    def test_api_manifest_drift_cannot_build_a_misleading_package(self):
        for key in ('PG_BASE_API', 'PG_PRO_BASE_API'):
            with self.subTest(key=key):
                self.set_value(key, '2')
                self.build('invalid-' + key, success=False)
                self.set_value(key, '1')

    def test_pro_only_rejects_files_owned_by_base(self):
        overlap = self.root / 'package/pro/root/usr/share/proxy-guard/pro-api'
        overlap.parent.mkdir(parents=True, exist_ok=True)
        overlap.write_text('1\n')
        out = Path(self.tmp.name) / 'overlapping-pro'
        p = subprocess.run([sys.executable, '-B', str(self.root / 'tools/build_ipk.py'),
                            '--only', 'pro', '--output', str(out)],
                           capture_output=True, text=True, timeout=180)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('Duplicate package ownership', p.stderr)
        self.assertFalse(any(out.glob('*.ipk')))
