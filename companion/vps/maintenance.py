"""Allowlisted maintenance with durable idempotency and recovery verification."""
from __future__ import annotations
import copy,json,re,subprocess,threading,time,uuid
from pathlib import Path

def config(value):
    value={}if value is None else value
    if not isinstance(value,dict):raise ValueError("invalid_maintenance_config")
    out={}
    for key in ("enabled","allow_reboot","allow_restart_xray","xui_usr1_confirmed"):
        out[key]=value.get(key,False)
        if type(out[key])is not bool:raise ValueError("invalid_maintenance_config")
    out["adapter"]=value.get("adapter","systemd")
    if out["adapter"]not in("systemd","openrc","3x-ui","3x-ui-openrc"):raise ValueError("invalid_maintenance_adapter")
    out["unit"]=value.get("unit","x-ui.service"if out["adapter"]in("3x-ui","3x-ui-openrc")else"xray.service")
    if not isinstance(out["unit"],str)or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,80}\.service",out["unit"])or out["unit"].split('.')[0]in("ssh","sshd","dropbear","proxy-guard-access","network","systemd"):
        raise ValueError("invalid_maintenance_unit")
    out["service"]=value.get("service","xray")
    if not isinstance(out["service"],str)or not 1<=len(out["service"])<=64 or any(ord(x)<32 for x in out["service"]):raise ValueError("invalid_maintenance_service")
    out["verify_seconds"]=value.get("verify_seconds",180)
    if type(out["verify_seconds"])is not int or not 15<=out["verify_seconds"]<=600:raise ValueError("invalid_maintenance_timeout")
    return out

def boot_id():return Path("/proc/sys/kernel/random/boot_id").read_text().strip()

def execute(action,c):
    if action=="reboot_vps":command=["/sbin/reboot"]if c["adapter"]in("openrc","3x-ui-openrc")else["/usr/bin/systemctl","--no-block","reboot"]
    elif c["adapter"]=="openrc":command=["/sbin/rc-service",c["unit"].removesuffix(".service"),"restart"]
    elif c["adapter"]in("3x-ui","3x-ui-openrc"):
        if not c["xui_usr1_confirmed"]:raise ValueError("xui_usr1_not_confirmed")
        command=["/sbin/rc-service",c["unit"].removesuffix(".service"),"reload"]if c["adapter"]=="3x-ui-openrc"else["/usr/bin/systemctl","kill","--kill-whom=main","--signal=USR1",c["unit"]]
    else:command=["/usr/bin/systemctl","--no-block","restart",c["unit"]]
    subprocess.run(command,check=True,capture_output=True,timeout=8)

class Maintenance:
    def __init__(self,value,path,monitor,events,executor=execute,clock=time.monotonic,wall=time.time,boot=boot_id):
        self.config=config(value);self.path=Path(path);self.monitor=monitor;self.events=events
        self.executor,self.clock,self.wall,self.boot=executor,clock,wall,boot
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.last_submit=None
        self.records={};self.authorized=lambda record:True
        self.state_error=None;self.recovery_deadlines={}
        if self.path.exists():
            try:
                raw=self.path.read_bytes()
                if len(raw)>131072:raise ValueError("invalid_operation_state")
                records=json.loads(raw)
                if not isinstance(records,dict)or len(records)>32:raise ValueError("invalid_operation_state")
                self.records=records
                for item in self.records.values():
                    if not isinstance(item,dict)or item.get("action")not in("restart_xray","reboot_vps")or item.get("phase")not in("accepted","dispatching","verifying","complete","failed","indeterminate"):raise ValueError("invalid_operation_state")
                    if item.get("phase")in("accepted","dispatching","verifying"):
                        if item.get("action")=="reboot_vps"and item.get("boot")!=self.boot():item["phase"]="verifying"
                        else:item.update(phase="indeterminate",error="interrupted_operation_not_repeated")
                self.save()
            except (OSError,ValueError,TypeError,KeyError,AttributeError):
                # Losing deduplication history must disable commands, not
                # the proxy policy or the independent SSH rescue lease.
                self.records={};self.config['enabled']=False;self.state_error='operation_state_unavailable'
        for ident,item in self.records.items():
            if item.get('phase')=='verifying':self.recovery_deadlines[ident]=self.clock()+self.config['verify_seconds']
    def save(self):
        from agent import write_private_json
        write_private_json(self.path,self.records)
    def _generation(self):
        health=self.monitor.status()
        return sorted((x["name"],x.get("generation",""))for x in health.get("services",[])if x.get("name")==self.config["service"])
    def _healthy(self):
        h=self.monitor.status();return h.get("configured")is True and h.get("ok")is True and not h.get("stale")and any(x.get("name")==self.config["service"]and x.get("ok")and x.get("generation")for x in h.get("services",[]))
    def submit(self,body):
        ident=body.get("operation_id");action=body.get("action")
        try:
            if str(uuid.UUID(ident))!=ident:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ValueError("invalid_operation_id")from None
        if action not in("restart_xray","reboot_vps"):raise ValueError("unsupported_action")
        with self.lock:
            if ident in self.records:
                old=self.records[ident]
                if old["action"]!=action:raise ValueError("operation_id_conflict")
                return self.public(old)
            now=self.wall()*1000;issued=body.get("issued_at");expires=body.get("expires_at")
            if type(issued)is not int or type(expires)is not int or issued>now+5000 or not issued<=now<=expires or not 1000<=expires-issued<=60000:
                raise ValueError("expired_operation")
            c=self.config
            if not c["enabled"]or not c["allow_reboot"if action=="reboot_vps"else"allow_restart_xray"]:raise PermissionError("maintenance_not_allowed")
            if action=="restart_xray"and c["adapter"]in("3x-ui","3x-ui-openrc")and not c["xui_usr1_confirmed"]:raise ValueError("xui_usr1_not_confirmed")
            if any(x["phase"]in("accepted","dispatching","verifying")for x in self.records.values()):raise ValueError("operation_busy")
            if self.last_submit is not None and self.clock()-self.last_submit<30:raise ValueError("operation_cooldown")
            record=dict(operation_id=ident,action=action,phase="accepted",created_at=self.wall(),boot=self.boot(),before=self._generation(),revision=body.get("revision"))
            self.records[ident]=record
            while len(self.records)>32:self.records.pop(next(iter(self.records)))
            self.save();self.last_submit=self.clock()
            self.thread=threading.Thread(target=self._run,args=(ident,),name="pg-maintenance",daemon=True)
            self.thread.start();return self.public(record)
    def _run(self,ident):
        if self.stop_event.wait(1):return
        with self.lock:
            item=self.records[ident]
            if not self.authorized(item):item.update(phase="failed",error="policy_changed_before_dispatch");self.save();return
            item["phase"]="dispatching";self.save()
        try:self.executor(item["action"],self.config)
        except Exception:
            with self.lock:item.update(phase="failed",error="maintenance_dispatch_failed");self.save()
            self.events.add("maintenance_failed","error",action=item["action"]);return
        with self.lock:item["phase"]="verifying";self.save()
        deadline=self.clock()+self.config["verify_seconds"]
        while not self.stop_event.wait(1):
            if self.verify(item):return
            if self.clock()>=deadline:
                with self.lock:item.update(phase="failed",error="recovery_not_verified");self.save()
                return
    def verify(self,item):
        changed=self.boot()!=item["boot"]if item["action"]=="reboot_vps"else self._generation()!=[tuple(v)for v in item["before"]]
        if changed and self._healthy():
            with self.lock:item.update(phase="complete",completed_at=self.wall());self.save()
            self.events.add("maintenance_complete",action=item["action"]);return True
        return False
    @staticmethod
    def public(item):return {k:copy.deepcopy(v)for k,v in item.items()if k not in("boot","before")}
    def status(self):
        with self.lock:
            for item in self.records.values():
                if item.get("phase")=="verifying"and item.get("action")=="reboot_vps":
                    if not self.verify(item)and self.clock()>=self.recovery_deadlines.get(item['operation_id'],float('inf')):
                        item.update(phase='failed',error='recovery_not_verified');self.save()
            return {"enabled":self.config["enabled"],"state_error":self.state_error,"allow_restart_xray":self.config["allow_restart_xray"],
                    "allow_reboot":self.config["allow_reboot"],
                    "adapter":self.config["adapter"],"operations":[self.public(x)for x in list(self.records.values())[-8:]]}
    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
