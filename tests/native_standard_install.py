#!/usr/bin/env python3
"""Native fresh install, uninstall and RPC checks for 1.0.0, offline."""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, traceback

assert Path('/etc/pgvm-fixture').exists() and Path('/.proxy-guard-test-root').exists()
stage=Path(sys.argv[1])
result_path=Path(sys.argv[2])
manifest=json.loads((stage/'files.json').read_text())['luci-app-proxy-guard']['files']
pkg='luci-app-proxy-guard'
version_label=json.loads((stage/'files.json').read_text())[pkg]['version']
apk=shutil.which('apk') is not None
apk_label=version_label.replace('-', '-r', 1)
artifact=stage/(pkg+'-'+apk_label+'.apk' if apk else pkg+'_'+version_label+'_all.ipk')
conf=Path('/etc/config/proxy_guard')
legacy=Path('/usr/share/proxy-guard/pro-requires-api')
before=conf.read_bytes() if conf.exists() else None
if before is not None:
    result_path.with_suffix(".before.uci").write_bytes(before)
    result_path.with_suffix(".before.uci").chmod(0o600)
rows=[]
cmd_log=result_path.with_suffix('.commands.log')

def run(*args,check=True,timeout=160):
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    with cmd_log.open('a') as log:
        log.write(repr(args)+' => '+str(p.returncode)+'\n'+p.stdout+p.stderr)
    if check:assert p.returncode==0,(args,p.returncode,(p.stdout+p.stderr)[-4500:])
    return p

def ok(condition,label):
    assert condition,label
    rows.append(label);print('PASS',label,flush=True)

def checksum(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def version():
    return run('apk','--no-network','--repositories-file','/dev/null','list','--installed',pkg,check=False).stdout if apk else run('opkg','status',pkg,check=False).stdout

def install(force=False,check=True):
    args=(['apk','--no-network','--repositories-file','/dev/null','--allow-untrusted','add'] if apk else ['opkg','install'])
    if force:args.insert(1,'--force-reinstall')
    return run(*args,str(artifact),check=check)

def remove(name):
    return run(*(['apk','--no-network','del',name] if apk else ['opkg','remove',name]))

def states():
    local=json.loads(run('ubus','-S','call','proxy_guard','status').stdout)
    return local,run('ubus','-v','list','proxy_guard').stdout

def other_configs():
    return {p.name:checksum(p)for p in Path('/etc/config').iterdir()if p.is_file()
            and p.name not in ('proxy_guard','luci') and not p.name.endswith(('-opkg','.apk-new','.apk-old'))}

def luci_config():
    output=run('uci','export','luci').stdout
    parts=output.split('\nconfig ')
    other=[p for p in parts if not p.startswith("internal 'languages'")]
    languages=next((p for p in parts if p.startswith("internal 'languages'")),'')
    return other, set(languages.splitlines()[1:])

initial_status={}
try:
    assert artifact.is_file()
    initial_status={'package_sha256':checksum(artifact),'package_format':'apk' if apk else 'ipk'}
    old_version=version()
    assert '1.0.0' not in old_version,'fresh fixture must not already have the test package'
    assert before is None and not legacy.exists(),'fresh fixture must not have the old package or settings'
    others=other_configs()
    luci_before,languages_before=luci_config()
    install()
    ok((apk_label if apk else version_label)in version(),'native package installed intended 1.0.0 version')
    current_configs=other_configs()
    changed={k for k in set(others)|set(current_configs) if others.get(k)!=current_configs.get(k)}
    ok(not changed,'no unrelated router configuration changed'+(f': {sorted(changed)}' if changed else ''))
    luci_after,languages_after=luci_config()
    allowed={'en','zh_cn','ja','ru','fa'}
    new_names={line.strip().split()[1] for line in languages_after-languages_before}
    ok(luci_before==luci_after and languages_before<=languages_after and new_names<=allowed,
       'LuCI changes only add supported language entries')
    for rel,digest in manifest.items():
        p=Path('/')/rel
        if rel=='etc/config/proxy_guard':assert p.stat().st_mode&0o777==0o600,rel
        else:assert checksum(p)==digest,(rel,'payload mismatch')
    ok(True,'all installed Standard payload hashes and configuration permissions match candidate')
    v,methods=states()
    ok('enforcement'in v and all(m in methods for m in ('status','api_credentials')),
       'package hooks register LuCI status and API credential management')
    ok(Path('/www/cgi-bin/proxy-guard-api').stat().st_mode&0o777==0o755 and
       run('ubus','-v','list','proxy_guard_api',check=False).returncode!=0,
       'direct HTTPS API is executable and legacy API RPC is absent')
    ok(v.get('enabled')is False and v.get('enforcement')=='off','fresh default displays disabled and does not block')
    ok(run('uci','-q','get','proxy_guard.main.api_enabled').stdout.strip()=='0','fresh default keeps API disabled')
    ok(run('/usr/libexec/proxy-guard','maintenance',check=False).returncode==2,'legacy private maintenance shortcut is absent')
    ok(not Path('/usr/share/proxy-guard/pro-api').exists() and not legacy.exists() and
       run('ubus','-v','list','proxy_guard_access',check=False).returncode!=0,
       '1.0.0 installs no extension compatibility marker or private RPC')
    initial_status['current_status']=v
    if '--reinstall-clean' in sys.argv:
        remove(pkg)
        ok(run('nft','list','table','inet','proxy_guard',check=False).returncode!=0,'uninstall removes only owned nft table')
        if conf.exists():conf.unlink()
        for path in ['/etc/config/proxy_guard-opkg','/etc/config/proxy_guard.apk-new','/etc/config/proxy_guard.apk-old']:
            Path(path).unlink(missing_ok=True)
        install()
        v,methods=states()
        ok(v.get('enabled')is False and v.get('enforcement')=='off' and 'api_credentials'in methods,
           'fresh reinstall returns to a disabled state and registers RPC via hooks')
    result={'ok':True,'checks':rows,**initial_status}
except Exception:
    result={'ok':False,'checks':rows,'error':traceback.format_exc(),**initial_status}
    print(result['error'],flush=True)
result_path.write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['ok'] else 1)
