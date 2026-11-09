#!/usr/bin/env python3
"""Create only owned startup-order drop-ins for explicitly selected proxy units."""
import argparse,json,re
from pathlib import Path
BLOCKED={"ssh.service","sshd.service","dropbear.service","proxy-guard-access.service","proxy-guard-access-policy.service"}
CONTENT="[Unit]\nRequires=proxy-guard-access-policy.service\nAfter=proxy-guard-access-policy.service\n"
def names(values):
    if not isinstance(values,list) or len(values)>16:raise ValueError("invalid_managed_units")
    for value in values:
        if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,96}\.service",value) or value in BLOCKED:
            raise ValueError("invalid_managed_unit")
    return sorted(set(values))
def apply(root,selected,remove=False):
    root=Path(root);selected=names(selected)
    state=root/"var/lib/proxy-guard-access/managed-units.json"
    old=names(json.loads(state.read_text())) if state.exists() else []
    if remove:selected=[]
    for name in old:
        if name not in selected:
            target=root/"etc/systemd/system"/(name+".d")/"50-proxy-guard-access.conf"
            if target.exists() and target.read_text()==CONTENT:target.unlink()
    for name in selected:
        target=root/"etc/systemd/system"/(name+".d")/"50-proxy-guard-access.conf"
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and target.read_text()!=CONTENT:raise ValueError("foreign_dropin_exists")
        target.write_text(CONTENT);target.chmod(0o644)
    state.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    state.write_text(json.dumps(selected)+"\n");state.chmod(0o600)
    return selected
OPENRC_MARKER="# Proxy Guard startup ordering; owned block."
def openrc_block():
    return OPENRC_MARKER+'\nrc_need="$rc_need proxy-guard-access-policy"\n# End Proxy Guard startup ordering.\n'
def apply_openrc(root,selected,remove=False):
    root=Path(root);selected=names(selected)
    state=root/"var/lib/proxy-guard-access/managed-openrc.json"
    old=names(json.loads(state.read_text()))if state.exists()else[]
    if remove:selected=[]
    for unit in sorted(set(old+selected)):
        name=unit.removesuffix(".service")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}",name):raise ValueError("invalid_openrc_service")
        target=root/"etc/conf.d"/name
        text=target.read_text()if target.exists()else""
        mode=target.stat().st_mode&0o777 if target.exists()else 0o644
        block=openrc_block()
        if OPENRC_MARKER in text and text.count(block)!=1:raise ValueError("foreign_openrc_block")
        clean=text.replace(block,"")
        wanted=clean
        if unit in selected:
            if wanted and not wanted.endswith("\n"):raise ValueError("unterminated_openrc_config")
            wanted+=block
        if wanted!=text:
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+".proxy-guard.new")
            if temp.exists():raise ValueError("openrc_update_busy")
            try:
                with temp.open("x")as f:f.write(wanted)
                temp.chmod(mode);temp.replace(target)
            finally:temp.unlink(missing_ok=True)
    state.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    state.write_text(json.dumps(selected)+"\n");state.chmod(0o600)
    return selected
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--root",default="/")
    p.add_argument("--config",required=True);p.add_argument("--remove",action="store_true")
    p.add_argument("--init",choices=("systemd","openrc"),default="systemd")
    args=p.parse_args();config=json.loads(Path(args.config).read_text())
    update=apply_openrc if args.init=="openrc"else apply
    print(json.dumps({"managed_units":update(args.root,config.get("managed_units",[]),args.remove),"init":args.init}))
if __name__=="__main__":main()
