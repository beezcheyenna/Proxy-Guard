#!/usr/bin/env python3
"""Replay SDK install recipes and compare staged data/hooks to built IPKs.
This is not a full OpenWrt SDK toolchain build. Run only in the marked lab VM.
"""
from pathlib import Path
import argparse,io,os,stat,subprocess,sys,tarfile,tempfile,json
assert sys.platform=='linux' and Path('/etc/pgvm-fixture').is_file(),'isolated Linux VM required'
p=argparse.ArgumentParser();p.add_argument('--packages',type=Path,required=True);a=p.parse_args()
S=Path(__file__).resolve().parents[1]
packages={}
for ipk in a.packages.glob('*.ipk'):
 if 'pro-max'in ipk.name:continue
 with tarfile.open(ipk,'r:*')as outer:
  blobs={Path(m.name).name:outer.extractfile(m).read()for m in outer if m.isfile()}
 with tarfile.open(fileobj=io.BytesIO(blobs['control.tar.gz']),mode='r:gz')as ctl:
  files={Path(m.name).name:ctl.extractfile(m).read()for m in ctl if m.isfile()}
  name=next(line.split(': ',1)[1]for line in files['control'].decode().splitlines()if line.startswith('Package: '))
 packages[name]=(blobs['data.tar.gz'],files)
assert set(packages)=={'luci-app-proxy-guard','luci-app-proxy-guard-pro'}
with tempfile.TemporaryDirectory(prefix='pg-sdk-stage-')as raw:
 D=Path(raw);sdk=D/'sdk';(sdk/'include').mkdir(parents=True)
 (sdk/'rules.mk').write_text('CP:=cp -fpR\nINCLUDE_DIR:=$(TOPDIR)/include\n')
 (sdk/'include/package.mk').write_text('')
 wrapper=D/'replay.mk';hooks=[];metadata=[];lines=['TOPDIR:='+str(sdk),'include '+str(S/'package/Makefile'),'define ProxyGuard/TestStage','.PHONY: stage','stage:']
 for index,name in enumerate(packages):
  dest=D/('stage'+str(index));dest.mkdir()
  lines.append('\t$(call Package/'+name+'/install,'+str(dest)+')')
  metadata.extend(['DEPENDS:=','EXTRA_DEPENDS:=','VERSION:=','$(eval $(Package/'+name+'))','$(file >'+str(D/(name+'-depends'))+',$(DEPENDS))','$(file >'+str(D/(name+'-extra-depends'))+',$(EXTRA_DEPENDS))','$(file >'+str(D/(name+'-version'))+',$(VERSION))'])
  for hook in ('preinst','postinst','prerm','postrm'):
   hooks.append('$(file >'+str(D/(name+'-'+hook))+',$(Package/'+name+'/'+hook+'))')
 wrapper.write_text('\n'.join(lines+['endef','$(eval $(ProxyGuard/TestStage))']+hooks+metadata)+'\n')
 done=subprocess.run(['make','--no-print-directory','-f',str(wrapper),'stage'],cwd=S/'package',capture_output=True,text=True,timeout=90)
 assert done.returncode==0,(done.stdout+done.stderr)[-3000:]
 counts={}
 for index,(name,(data,control))in enumerate(packages.items()):
  dest=D/('stage'+str(index));expected=set();count=0
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz')as archive:
   for m in archive:
    relative=m.name.removeprefix('./').rstrip('/')
    if relative in ('','.'):continue
    path=dest/relative;expected.add(relative)
    assert path.exists(),('SDK missing',name,relative)
    assert stat.S_IMODE(path.stat().st_mode)==m.mode,('SDK/IPK mode differs',name,relative,oct(stat.S_IMODE(path.stat().st_mode)),oct(m.mode))
    if m.isfile():assert path.read_bytes()==archive.extractfile(m).read(),('SDK/IPK data differs',name,relative);count+=1
  # SDK cp may retain empty checkout directories. Compare files and the
  # directories required by those files; empty scaffolding carries no payload.
  actual={str(x.relative_to(dest))for x in dest.rglob('*')if x.is_file()or any(y.is_file()for y in x.rglob('*'))}
  assert actual==expected,(name,'SDK-only',sorted(actual-expected),'IPK-only',sorted(expected-actual))
  for hook in ('preinst','postinst','prerm','postrm'):
   if hook in control:
    rendered=(D/(name+'-'+hook)).read_bytes().strip()
    assert rendered==control[hook].strip(),('SDK/IPK hook differs',name,hook)
  # Compare effective constraints as well as files and scripts. SDK EXTRA_DEPENDS
  # may repeat a bare build dependency; its versioned constraint wins.
  deps={part.lstrip('+'):part.lstrip('+')for part in(D/(name+'-depends')).read_text().split()}
  for extra in(D/(name+'-extra-depends')).read_text().strip().split(','):
   if extra.strip():deps[extra.strip().split(' ',1)[0]]=extra.strip()
  expected_deps=next(line.split(': ',1)[1]for line in control['control'].decode().splitlines()if line.startswith('Depends: '))
  assert set(deps.values())==set(expected_deps.split(', ')),('SDK/IPK dependency constraints differ',name,deps,expected_deps)
  expected_version=next(line.split(': ',1)[1]for line in control['control'].decode().splitlines()if line.startswith('Version: '))
  assert (D/(name+'-version')).read_text().strip()==expected_version,('SDK/IPK package versions differ',name)
  counts[name]=count
 print('PASS SDK install recipe data, inventory, permissions and expanded hook equivalence:',json.dumps(counts))
