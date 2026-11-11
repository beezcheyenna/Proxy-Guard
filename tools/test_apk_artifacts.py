#!/usr/bin/env python3
"""Compare actual SDK-built APK payloads, dependencies and hooks with IPKs.
Run inside a marked offline Linux test VM with the native SDK apk utility.
"""
from pathlib import Path
import argparse,hashlib,io,json,re,subprocess,sys,tarfile,tempfile
assert sys.platform=="linux" and Path("/etc/pgvm-fixture").is_file()
p=argparse.ArgumentParser()
p.add_argument("--apk-tool",type=Path,required=True)
p.add_argument("--apks",type=Path,required=True)
p.add_argument("--ipks",type=Path,required=True)
a=p.parse_args()
S=Path(__file__).resolve().parents[1]
make=(S/"package/Makefile").read_text()
values=dict(re.findall(r"^(PKG_VERSION|PKG_RELEASE|PG_PRO_VERSION|PG_PRO_RELEASE|PG_PRO_MIN_BASE_APK):=(\S+)$",make,re.M))
counts={}
for name,prefix in [("luci-app-proxy-guard","PKG"),("luci-app-proxy-guard-pro","PG_PRO")]:
    version=values[prefix+"_VERSION"]+"-r"+values[prefix+"_RELEASE"]
    apk=a.apks/(name+"-"+version+".apk")
    ipk=next(x for x in a.ipks.glob(name+"_*.ipk"))
    meta=json.loads(subprocess.check_output([str(a.apk_tool),"adbdump","--format","json",str(apk)],text=True))
    assert meta["info"]["name"]==name and meta["info"]["version"]==version
    assert meta["info"]["arch"]=="noarch"
    with tarfile.open(ipk)as t:
        parts={Path(m.name).name:t.extractfile(m).read()for m in t if m.isfile()}
    with tarfile.open(fileobj=io.BytesIO(parts["control.tar.gz"]),mode="r:gz")as t:
        control={Path(m.name).name:t.extractfile(m).read()for m in t if m.isfile()}
    with tarfile.open(fileobj=io.BytesIO(parts["data.tar.gz"]),mode="r:gz")as t:
        expected={m.name.removeprefix("./"):(hashlib.sha256(t.extractfile(m).read()).hexdigest(),m.mode)for m in t if m.isfile()}
    actual={}
    for directory in meta["paths"]:
        for item in directory.get("files",[]):
            key="/".join(x for x in [directory.get("name",""),item["name"]]if x)
            if key.startswith("lib/apk/packages/"):continue
            assert key not in actual
            actual[key]=(item["hash"],item["acl"]["mode"])
            assert item["acl"]["user"]=="root" and item["acl"]["group"]=="root"
    assert actual==expected,(name,"APK/IPK content or permission mismatch",sorted(set(actual)^set(expected)))
    deps=next(x.removeprefix("Depends: ")for x in control["control"].decode().splitlines()if x.startswith("Depends: "))
    expected_deps=set(deps.split(", "))|{"libc"}
    if name.endswith("-pro"):expected_deps={"libc","luci-app-proxy-guard>="+values["PG_PRO_MIN_BASE_APK"]}
    assert set(meta["info"]["depends"])==expected_deps,(name,meta["info"]["depends"],expected_deps)
    mapping={"preinst":"pre-install","postinst":"post-install","prerm":"pre-deinstall","postrm":"post-deinstall"}
    for hook,native in mapping.items():
        body=control[hook].decode().strip().removeprefix("#!/bin/sh\n")
        assert meta["scripts"][native].rstrip().endswith(body),(name,hook,"SDK hook changed")
        assert "export PKG_UPGRADE=1" not in meta["scripts"][native]
    for hook,native in [("preinst","pre-upgrade"),("postinst","post-upgrade")]:
        body=control[hook].decode().strip().removeprefix("#!/bin/sh\n")
        assert meta["scripts"][native].rstrip().endswith(body)
        assert meta["scripts"][native].startswith("#!/bin/sh\nexport PKG_UPGRADE=1\n")
    with tempfile.TemporaryDirectory(prefix="pg-apk-extract-")as raw:
        subprocess.run([str(a.apk_tool),"--allow-untrusted","extract","--destination",raw,str(apk)],check=True,capture_output=True)
        base=Path(raw)/"lib/apk/packages"
        assert (base/(name+".conffiles")).read_bytes()==control["conffiles"]
        for line in (base/(name+".conffiles_static")).read_text().splitlines():
            config,digest=line.split()
            assert expected[config.removeprefix("/")][0]==digest
    counts[name]=len(actual)
print("PASS actual SDK APK payload, ownership, dependencies, conffiles and six hooks match IPK contracts",json.dumps(counts))
