"""Two independent authenticated heartbeats and kernel-timed SSH rescue."""
from __future__ import annotations
import hashlib,ipaddress,json,os,time
from pathlib import Path
from protection import DEFAULT_SSH

def fingerprint(ssh):return hashlib.sha256(json.dumps(ssh,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def read_saved(path):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>8192:raise ValueError()
        value=json.loads(raw)
        if not isinstance(value,dict)or type(value.get("armed"))is not bool:raise ValueError()
        addresses=value.get("last_home",[])
        if not isinstance(addresses,list)or len(addresses)>2:raise ValueError()
        for address in addresses:
            ip=ipaddress.ip_address(address)
            if not ip.is_global or ip.is_multicast:raise ValueError()
        return {"armed":value["armed"],"last_home":addresses,"policy":value.get("policy")}
    except (OSError,ValueError,TypeError):return {"armed":False,"last_home":[],"policy":None}

def heartbeat_path(state_path):
    ident=hashlib.sha256(str(Path(state_path).resolve()).encode()).hexdigest()[:16]
    return Path('/run/proxy-guard-access')/('heartbeats-'+ident+'.json')

def heartbeat_saved(path,ssh,now):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>8192:raise ValueError()
        value=json.loads(raw)
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if value.get('boot')!=boot or value.get('policy')!=fingerprint(ssh):raise ValueError()
        for key in('control','proxy'):
            t=value[key]
            if type(t)not in(int,float)or not 0<=t<=now:raise ValueError()
        return value
    except (OSError,ValueError,TypeError,KeyError):return None

def save_heartbeat(path,value,ssh):
    from agent import write_private_json
    value=dict(value,boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),policy=fingerprint(ssh))
    write_private_json(path,value,unchanged_ok=True)

def boot_runtime(state_path,policy,now=None,persist=False,journal=None):
    now=time.monotonic()if now is None else now
    saved=read_saved(str(state_path)+'.rescue');ssh=policy.get('ssh',DEFAULT_SSH)
    armed=policy.get('enabled',False)and ssh['managed']and saved['armed']and saved['policy']==fingerprint(ssh)
    path=Path(journal)if journal is not None else heartbeat_path(state_path)
    heartbeats=heartbeat_saved(path,ssh,now)
    if heartbeats is None:
        heartbeats={'control':now,'proxy':now,'seen_control':False,'seen_proxy':False,'emergency':False,'public_until':now+ssh['after']+ssh['open_seconds'] if ssh['open_seconds'] else 0}
        if armed and persist:save_heartbeat(path,heartbeats,ssh)
    deadline=max(heartbeats['control'],heartbeats['proxy'])+ssh['after']
    return {'ssh_armed':armed,'last_home':saved['last_home'],
            'ssh_hold_until':0 if heartbeats.get('emergency')else deadline if armed else 0,
            'ssh_public_until':heartbeats.get('public_until',deadline+ssh['open_seconds'])if armed and ssh['open_seconds'] else 0}

def management_session(port,sources,proc=Path("/proc")):
    """Require a listening SSH daemon and its established authorized session."""
    from discovery import Inventory
    inventory=Inventory(proc=proc);rows=inventory.refresh()
    names={"sshd","sshd-session","dropbear"}
    listening=any(row["protocol"]=="tcp"and row["port"]==port and any(p["name"]in names for p in row["processes"])for row in rows)
    if not listening:return {"ok":False,"reason":"ssh_listener_not_verified"}
    networks=[ipaddress.ip_network(v,strict=False)for v in sources]
    owned=set();budget=20000
    for directory in list(proc.glob("[0-9]*"))[:2048]:
        try:
            if Path(os.readlink(directory/"exe")).name not in names:continue
            descriptors=list((directory/"fd").iterdir())[:512]
        except OSError:continue
        for fd in descriptors:
            budget-=1
            if budget<=0:break
            try:
                text=os.readlink(fd)
                if text.startswith("socket:["):owned.add(text[8:-1])
            except OSError:pass
        if budget<=0:break
    for family in (4,6):
        try:lines=(proc/"net"/("tcp"if family==4 else"tcp6")).read_text().splitlines()[1:8193]
        except OSError:continue
        for line in lines:
            try:
                fields=line.split()
                if fields[3]!="01"or int(fields[1].rsplit(":",1)[1],16)!=port or fields[9]not in owned:continue
                ip=Inventory.address(fields[2].split(":")[0],family)
                if getattr(ip,"ipv4_mapped",None):ip=ip.ipv4_mapped
                if any(ip.version==net.version and ip in net for net in networks):return {"ok":True,"reason":"management_session_verified"}
            except (ValueError,IndexError):continue
    return {"ok":False,"reason":"authorized_ssh_session_required"}

class Safety:
    def __init__(self,engine,events,clock=time.monotonic,preflight=management_session,journal=None):
        self.engine,self.events,self.clock,self.preflight=engine,events,clock,preflight
        self.path=Path(str(engine.path)+".rescue");saved=read_saved(self.path)
        self.armed=saved["armed"]and saved["policy"]==fingerprint(engine.state["policy"].get("ssh",DEFAULT_SSH));self.last_home=saved["last_home"]
        self.journal=Path(journal)if journal is not None else heartbeat_path(engine.path)
        cached=heartbeat_saved(self.journal,engine.state['policy'].get('ssh',DEFAULT_SSH),clock())or{}
        self.last_control=cached.get('control',clock());self.last_path=cached.get('proxy',clock())
        self.seen_control=cached.get('seen_control',False);self.seen_path=cached.get('seen_proxy',False)
        self.emergency=cached.get('emergency',False);self.preflight_result={"ok":False,"reason":"both_heartbeats_required"};self.last_policy=fingerprint(engine.state["policy"].get("ssh",DEFAULT_SSH))
        self.tick()
    def home(self):
        now=self.clock()
        return [value[0]for family,value in self.engine.leases.items()if family in self.engine.state["policy"]["address_families"]and value[1]>now+2]
    def persist(self):
        from agent import write_private_json
        write_private_json(self.path,{"armed":self.armed,"last_home":self.last_home,"policy":fingerprint(self.engine.state["policy"].get("ssh",DEFAULT_SSH))},unchanged_ok=True)
    def note_control(self,synced=False):
        with self.engine.lock:
            self.last_control=self.clock();self.seen_control=True
            home=self.home()
            if synced and home:
                self.last_home=home;self.persist()
                # An authenticated status response alone cannot withdraw public
                # rescue: the current household authorization must be updated.
                if self.emergency:self.emergency=False;self.events.add("ssh_rescue_recovered")
            changed=self.tick();self.heartbeat();return changed
    def note_path(self):
        with self.engine.lock:
            self.last_path=self.clock();self.seen_path=True
            changed=self.tick();self.heartbeat();return changed
    def heartbeat(self):
        ssh=self.engine.state['policy'].get('ssh',DEFAULT_SSH)
        if ssh['managed']:
            save_heartbeat(self.journal,dict(control=self.last_control,proxy=self.last_path,
                seen_control=self.seen_control,seen_proxy=self.seen_path,emergency=self.emergency,
                public_until=self.engine.runtime.get('ssh_public_until',0)),ssh)
    def tick(self):
        policy=self.engine.state["policy"];ssh=policy.get("ssh",DEFAULT_SSH);now=self.clock()
        signature=fingerprint(ssh)
        if self.last_policy!=signature:
            self.armed=False;self.emergency=False;self.last_policy=signature;self.persist()
        if not policy["enabled"]or not ssh["managed"]:
            if self.armed:self.armed=False;self.persist()
            self.emergency=False
        elif not self.armed:
            if not ssh["confirmed"]:self.preflight_result={"ok":False,"reason":"management_confirmation_required"}
            elif not self.seen_control or not self.seen_path or now-self.last_control>min(ssh["after"],30)or now-self.last_path>min(ssh["after"],30):self.preflight_result={"ok":False,"reason":"both_heartbeats_required"}
            elif not self.home():self.preflight_result={"ok":False,"reason":"fresh_household_authorization_required"}
            else:
                self.preflight_result=self.preflight(ssh["port"],ssh["managers"]+self.home())
                if self.preflight_result["ok"]:
                    self.armed=True;self.last_home=self.home();self.persist();self.events.add("ssh_management_armed")
        deadline=max(self.last_control,self.last_path)+ssh["after"]
        if self.armed and ssh["rescue_enabled"]and now>=deadline and not self.emergency:
            self.emergency=True;self.events.add("ssh_rescue_open","warning",scope=ssh["scope"]);self.heartbeat()
        runtime=dict(self.engine.runtime)
        # Once rescue begins, a lone path heartbeat must not close it again.
        if self.emergency:
            hold=0;public=self.engine.runtime.get("ssh_public_until",deadline+ssh["open_seconds"])
        else:hold=deadline;public=deadline+ssh["open_seconds"]
        if ssh["open_seconds"]==0:public=0
        if not ssh["managed"]or not policy["enabled"]:hold=0;public=0
        runtime.update(ssh_armed=self.armed and ssh["managed"]and policy["enabled"],last_home=list(self.last_home),
                       ssh_hold_until=hold,ssh_public_until=public)
        changed=runtime!=self.engine.runtime;self.engine.runtime=runtime
        return changed
    def status(self):
        with self.engine.lock:
            ssh=self.engine.state["policy"].get("ssh",DEFAULT_SSH);now=self.clock()
            unlimited=ssh["open_seconds"]==0
            public=self.emergency and ssh["scope"]=="public" and (unlimited or self.engine.runtime.get("ssh_public_until",0)>now)
            return {"managed":ssh["managed"],"armed":self.armed,"port":ssh["port"],"rescue_enabled":ssh["rescue_enabled"],
                    "scope":ssh["scope"],"effective_scope":"public"if public else"restricted","emergency":self.emergency,
                    "public_unlimited":bool(public and unlimited),"public_remaining":max(0,int(self.engine.runtime.get("ssh_public_until",0)-now))if public and not unlimited else 0,
                    "control_age":int(now-self.last_control)if self.seen_control else None,
                    "proxy_age":int(now-self.last_path)if self.seen_path else None,
                    "preflight":self.preflight_result,"system_firewall_still_applies":True}
