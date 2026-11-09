"""Bounded local service inspection. No commands from API callers are executed."""
from __future__ import annotations
from collections import Counter, deque
import hashlib, json, os, re, threading, time
from pathlib import Path

def bounded_int(value, default, low, high):
    value = default if value is None else value
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid_monitor_number")
    return value

def service_config(rows):
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError("invalid_services")
    result, names = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_service_name")
        name = row.get("name", "")
        binaries = row.get("process_names", [])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or name in names:
            raise ValueError("invalid_service_name")
        if not isinstance(binaries, list) or not 1 <= len(binaries) <= 8:
            raise ValueError("invalid_process_names")
        if any(not isinstance(s,str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}",s) for s in binaries):
            raise ValueError("invalid_process_names")
        ports = {}
        for proto in ("tcp","udp"):
            values = row.get(proto+"_ports",[])
            if not isinstance(values,list) or len(values)>32 or any(type(v)is not int or not 1<=v<=65535 for v in values):
                raise ValueError("invalid_service_ports")
            ports[proto] = sorted(set(values))
        required = row.get("required",True)
        if type(required)is not bool:
            raise ValueError("invalid_required")
        names.add(name)
        result.append({"name":name,"process_names":binaries,"required":required,**ports})
    return result

class EventStore:
    def __init__(self, limit=512, retention=86400, clock=time.time):
        self.items = deque(maxlen=bounded_int(limit,512,64,4096))
        self.retention = bounded_int(retention,86400,60,2592000)
        self.clock, self.lock, self.sequence = clock, threading.RLock(), 0
        self.counts = Counter()

    def add(self, kind, severity="info", **evidence):
        # No request body, credentials, raw addresses or packet payload in this store.
        if not re.fullmatch(r"[a-z0-9_]{1,48}",kind):
            raise ValueError("invalid_event")
        safe = {}
        for key,value in evidence.items():
            if not re.fullmatch(r"[a-z0-9_]{1,40}",key): continue
            if isinstance(value,(bool,int,float)) and not (isinstance(value,float) and not __import__("math").isfinite(value)):
                safe[key] = value
            elif isinstance(value,str):
                safe[key] = re.sub(r"[\x00-\x1f\x7f]","",value)[:160]
        with self.lock:
            self.sequence += 1
            row = {"id":self.sequence,"time":self.clock(),"kind":kind,
                   "severity":severity if severity in ("info","warning","error") else "info","evidence":safe}
            self.items.append(row)
            self.counts[kind] += 1
            self._prune()
            return dict(row)

    def _prune(self):
        cutoff = self.clock()-self.retention
        while self.items and self.items[0]["time"]<cutoff: self.items.popleft()

    def snapshot(self, after=0, limit=100):
        with self.lock:
            self._prune()
            rows=[dict(x) for x in self.items if x["id"]>after]
            return {"events":rows[-min(200,max(1,limit)):],"counts":dict(self.counts),
                    "latest_id":self.sequence,"retained":len(self.items),"retention_seconds":self.retention,
                    "history_scope":"current_process","truncated":len(rows)>min(200,max(1,limit))}

    def clear(self):
        with self.lock:
            self.items.clear()
            self.counts.clear()

class Monitor:
    def __init__(self, config, events=None, proc=Path("/proc")):
        self.services = service_config(config.get("services",[]))
        self.interval = bounded_int(config.get("monitor_interval"),5,2,60)
        self.events = events or EventStore()
        self.proc, self.lock = Path(proc), threading.Lock()
        self.current, self.previous = None, {}
        self.stop_event = threading.Event()
        self.thread = None

    def _processes(self):
        processes={}
        for directory in self.proc.glob("[0-9]*"):
            try:
                state=(directory/"stat").read_text().rsplit(") ",1)[1].split()
                if state[0] in ("Z","X"): continue
                executable=Path(os.readlink(directory/"exe")).name
                # starttime prevents a PID reuse from appearing as continuity.
                identity=directory.name+":"+state[19]
                processes.setdefault(executable,[]).append((identity,directory))
            except (OSError,IndexError): continue
        return processes

    def _sockets(self):
        rows = {"tcp":{},"udp":{}}
        states=Counter()
        for proto in ("tcp","udp"):
            for family in ("","6"):
                try: lines=(self.proc/"net"/(proto+family)).read_text().splitlines()[1:]
                except OSError: continue
                for line in lines:
                    fields=line.split()
                    if len(fields)<10: continue
                    try: port=int(fields[1].rsplit(":",1)[1],16)
                    except (ValueError,IndexError): continue
                    states[proto+"_"+fields[3]]+=1
                    if fields[3] == ("0A" if proto=="tcp" else "07"):
                        rows[proto].setdefault(port,set()).add(fields[9])
        return rows,dict(states)

    def sample(self):
        processes=self._processes()
        sockets,states=self._sockets()
        result=[]
        for service in self.services:
            matches=[item for name in service["process_names"] for item in processes.get(name,[])]
            inodes=set()
            for _,directory in matches:
                for fd in (directory/"fd").glob("*"):
                    try:
                        link=os.readlink(fd)
                        if link.startswith("socket:["): inodes.add(link[8:-1])
                    except OSError: pass
            ports={proto:{str(p):bool(sockets[proto].get(p,set())&inodes) for p in service[proto]}
                   for proto in ("tcp","udp")}
            good=bool(matches) and all(all(v.values()) for v in ports.values())
            identity=",".join(sorted(x[0] for x in matches))
            old=self.previous.get(service["name"])
            if old is not None and old!=(good,identity):
                self.events.add("service_ready" if good else "service_down",
                                "info" if good else "warning",service=service["name"],
                                restarted=good and old[1]!=identity)
            self.previous[service["name"]]=(good,identity)
            result.append({"name":service["name"],"ok":good,"required":service["required"],
                           "process_count":len(matches),"generation":__import__("hashlib").sha256(identity.encode()).hexdigest() if matches else "","ports":ports})
        required=[s for s in result if s["required"]]
        status={"configured":bool(required),"ok":bool(required) and all(x["ok"] for x in required),
                "services":result,"socket_states":states,"checked_at":time.time(),
                "checked_uptime":time.monotonic(),"interval":self.interval}
        with self.lock: self.current=status
        return status

    def status(self):
        with self.lock: result=dict(self.current) if self.current else None
        if result is None: return {"configured":bool(self.services),"ok":False,"stale":True,"services":[]}
        result["stale"]=time.monotonic()-result["checked_uptime"]>self.interval*3
        if result["stale"]: result["ok"]=False
        return result

    def start(self):
        self.sample()
        def loop():
            while not self.stop_event.wait(self.interval):
                try: self.sample()
                except Exception: self.events.add("monitor_error","error")
        self.thread=threading.Thread(target=loop,name="pg-service-monitor",daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)
