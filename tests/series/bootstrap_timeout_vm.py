#!/usr/bin/env python3
"""Run only as root in an isolated VM and a fresh network namespace."""
from pathlib import Path
import copy,hashlib,json,os,subprocess,sys,tempfile,time
assert os.geteuid()==0 and Path('/etc/pgvm-fixture').exists()
assert os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net'),'Use unshare -m -n -f'
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'companion/vps'))
import agent
checks=[]
def good(value,label):
 assert value,label
 checks.append(label);print('PASS '+label,flush=True)
def nft(*args):return subprocess.run(['/usr/sbin/nft',*args],capture_output=True,text=True,check=True,timeout=20)
with tempfile.TemporaryDirectory(prefix='pg-bootstrap-timeout-')as directory:
 D=Path(directory);D.chmod(0o700);wrapper=D/'nft';mode=D/'mode';marker=D/'delayed';calls=D/'calls'
 script=r"""#!/usr/bin/python3
from pathlib import Path
import os,subprocess,sys,time
D=Path(__file__).parent;args=sys.argv[1:];kind='check'if '-c'in args else'commit'
with(D/'calls').open('a')as f:f.write(kind+chr(10))
if kind==(D/'mode').read_text()and not(D/'delayed').exists():
 (D/'delayed').touch()
 if kind=='commit':
  p=subprocess.run(['/usr/sbin/nft',*args],input=sys.stdin.read(),text=True,capture_output=True)
  if p.returncode:sys.stderr.write(p.stderr);raise SystemExit(p.returncode)
 time.sleep(9.5)
 if kind=='commit':raise SystemExit(0)
os.execv('/usr/sbin/nft',['/usr/sbin/nft',*args])
"""
 wrapper.write_text(script);wrapper.chmod(0o700)
 nft('add','table','inet','pg_foreign_boot_test')
 foreign=nft('-j','list','table','inet','pg_foreign_boot_test').stdout
 policy=agent.normalize_policy(True,[{'id':'selected','name':'Selected proxy port','enabled':True,'protocol':'both','ports':['24443'],'source_mode':'dynamic','sources':[]}])
 driver=agent.Nft(binary=str(wrapper));prior=None
 for failure in ['check','commit']:
  mode.write_text(failure);marker.unlink(missing_ok=True);calls.write_text('');started=time.monotonic();driver.bootstrap(copy.deepcopy(policy));elapsed=time.monotonic()-started
  rows=calls.read_text().splitlines();snapshot=driver.snapshot(agent.BOOT);fingerprint=agent.stable_rules(snapshot)
  good(marker.exists()and rows.count(failure)>=2,'real timed-out '+failure+' command is retried at startup')
  good(snapshot is not None and '24443'in json.dumps(snapshot),'startup retry installs the selected-port policy')
  good(nft('-j','list','table','inet','pg_foreign_boot_test').stdout==foreign,'startup retry preserves unrelated kernel rules')
  good(not any(row.get('set',{}).get('elem')for row in snapshot['nftables']if row.get('set',{}).get('name','').startswith('dynamic')),'startup retry does not restore dynamic permissions')
  if prior is not None:good(fingerprint==prior,'retry after an applied-but-timed-out transaction is idempotent')
  prior=fingerprint;print('TIMING',failure,round(elapsed,3),'seconds',flush=True)
 print(json.dumps({'ok':True,'checks':checks,'source_sha256':hashlib.sha256((ROOT/'companion/vps/agent.py').read_bytes()).hexdigest()}))
