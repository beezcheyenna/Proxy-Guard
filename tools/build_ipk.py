#!/usr/bin/env python3
"""Build the reproducible Proxy Guard IPK from the SDK hook bodies."""
from pathlib import Path
import argparse,gzip,hashlib,io,json,re,sys,tarfile
sys.dont_write_bytecode=True
from build_translations import verify as verify_translations
ROOT=Path(__file__).resolve().parents[1]
MAKEFILE=(ROOT/'package/Makefile').read_text()
PACKAGE_VERSION=re.search(r'^PKG_VERSION:=(\S+)$',MAKEFILE,re.M).group(1)
PACKAGE_RELEASE=re.search(r'^PKG_RELEASE:=(\S+)$',MAKEFILE,re.M).group(1)
VERSION=PACKAGE_VERSION+'-'+PACKAGE_RELEASE
MAKE_VALUES={'PKG_VERSION':PACKAGE_VERSION,'PKG_RELEASE':PACKAGE_RELEASE}
EPOCH=1792108800
BASE_DEPENDS='luci-base, lua, libuci-lua, luci-lib-jsonc, luci-lib-nixio, rpcd-mod-file, firewall4, curl, ca-bundle, ucode, ucode-mod-fs, ucode-mod-uci'
SPECS=[
 ('luci-app-proxy-guard',VERSION,'package/root',BASE_DEPENDS,['/etc/config/proxy_guard'],'Local proxy fault protection'),
]
def tar_gz(files):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.GNU_FORMAT) as archive:
        directories={'.'}
        for name,_,_ in files:
            parent=name.rsplit('/',1)[0] if '/'in name else '.'
            while parent and parent!='.':
                directories.add(parent);parent=parent.rsplit('/',1)[0] if '/'in parent else '.'
        for name in sorted(directories,key=lambda n:(n.count('/'),n)):
            info=tarfile.TarInfo(name+'/');info.type=tarfile.DIRTYPE;info.mode=0o755;info.mtime=EPOCH
            info.uid=info.gid=0;info.uname=info.gname='root';archive.addfile(info)
        for name,content,mode in sorted(files):
            info=tarfile.TarInfo(name);info.size=len(content);info.mode=mode;info.mtime=EPOCH
            info.uid=info.gid=0;info.uname=info.gname='root';archive.addfile(info,io.BytesIO(content))
    return gzip.compress(stream.getvalue(),mtime=EPOCH)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--only",choices=("standard",),help=argparse.SUPPRESS)
    args=parser.parse_args()
    core=(ROOT/'package/root/usr/lib/proxy-guard/core.lua').read_text()
    assert re.search(r"M\.VERSION\s*=\s*['\"]([^'\"]+)['\"]",core).group(1)==PACKAGE_VERSION
    dest=args.output or ROOT/'dist';dest.mkdir(parents=True,exist_ok=True)
    sums=[];manifest={}
    verify_translations()
    selected=SPECS
    for name,version,relative,dependencies,conffiles,description in selected:
        root=ROOT/relative;files=[]
        for path in root.rglob('*'):
            if not path.is_file():continue
            key=path.relative_to(root).as_posix()
            mode=0o755 if key.startswith(('etc/init.d/','etc/hotplug.d/','usr/libexec/','www/cgi-bin/')) else 0o644
            if key in ('etc/config/proxy_guard_access','etc/config/proxy_guard'):mode=0o600
            files.append(('./'+key,path.read_bytes(),mode))
        control=(f'Package: {name}\nVersion: {version}\nArchitecture: all\nMaintainer: Proxy Guard contributors\n'
                 f'Section: luci\nPriority: optional\nLicense: MIT\nDepends: {dependencies}\n'
                 f'Installed-Size: {sum(len(x[1]) for x in files)}\nDescription: {description}\n').encode()
        controls=[('./control',control,0o644),('./conffiles',('\n'.join(conffiles)+'\n' if conffiles else '').encode(),0o644)]
        for hook in ('preinst','postinst','prerm','postrm'):
            match=re.search(r'define Package/'+re.escape(name)+'/'+hook+r'\n(.*?)\nendef',MAKEFILE,re.S)
            if match:
                body=match[1]
                for variable,value in MAKE_VALUES.items():body=body.replace('$('+variable+')',value)
                controls.append(('./'+hook,(body.replace('$$','$').strip()+'\n').encode(),0o755))
        blob=tar_gz([('./debian-binary',b'2.0\n',0o644),('./control.tar.gz',tar_gz(controls),0o644),('./data.tar.gz',tar_gz(files),0o644)])
        target=dest/f'{name}_{version}_all.ipk';target.write_bytes(blob)
        sums.append(f'{hashlib.sha256(blob).hexdigest()}  {target.name}')
        manifest[name]={'files':{key[2:]:hashlib.sha256(data).hexdigest() for key,data,_ in files},
                        'conffiles':conffiles,'depends':dependencies,'version':version}
        print(target)
    (dest/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    (dest/'files.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
