"""Opt-in bounded packet capture and isolated low-interaction honeypot."""
from __future__ import annotations
from collections import Counter
import ipaddress,os,re,secrets,shutil,socket,socketserver,struct,subprocess,threading,time
from pathlib import Path
from monitor import bounded_int
from research import Analyzer,packet

def capture_config(value):
    if not isinstance(value,dict):raise ValueError("invalid_analysis")
    enabled=value.get("enabled",False)
    if type(enabled)is not bool:raise ValueError("invalid_analysis")
    interface=value.get("interface","any")
    if not isinstance(interface,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}",interface):raise ValueError("invalid_capture_interface")
    ports=value.get("ports",[])
    if not isinstance(ports,list) or len(ports)>32 or any(type(x)is not int or not 1<=x<=65535 for x in ports):
        raise ValueError("invalid_capture_ports")
    if enabled and not ports:raise ValueError("capture_requires_explicit_ports")
    probes=value.get("probe_detection",True)
    if type(probes)is not bool:raise ValueError("invalid_probe_detection")
    continuous=value.get("continuous",False)
    if type(continuous)is not bool:raise ValueError("invalid_continuous_option")
    raw=value.get("save_pcap",False)
    if type(raw)is not bool:raise ValueError("invalid_pcap_option")
    return {"enabled":enabled,"interface":interface,"ports":sorted(set(ports)),"save_pcap":raw,"probe_detection":probes,"continuous":continuous,
            "pause":bounded_int(value.get("pause"),30,1,3600),
            "duration":bounded_int(value.get("duration"),60,1,3600),
            "file_bytes":bounded_int(value.get("file_bytes"),4194304,65536,16777216),
            "file_count":bounded_int(value.get("file_count"),2,1,8),
            "retention":bounded_int(value.get("retention"),3600,60,604800),
            "max_pps":bounded_int(value.get("max_pps"),1000,10,5000),
            "max_packets":bounded_int(value.get("max_packets"),60000,100,1000000),
            "directory":str(value.get("directory","/var/lib/proxy-guard-access/capture")),
            "max_flows":bounded_int(value.get("max_flows"),512,16,4096),
            "window":bounded_int(value.get("window"),300,10,86400)}

class Capture:
    def __init__(self,config,events,analyzer=None):
        self.config,self.events=capture_config(config),events
        self.analyzer=analyzer or Analyzer(events,self.config["max_flows"],self.config["window"],probe_detection=self.config["probe_detection"])
        self.lock=threading.RLock()
        self.process,self.thread=None,None
        self.state="disabled"
        self.stop_event=threading.Event()
        self.metrics=Counter()
        self.file=None
        self.file_size=0
        self.deadline=0
        self.global_header=None
        self.sequence=0

    def _cleanup(self):
        directory=Path(self.config["directory"])
        if not directory.exists():return
        paths=sorted(directory.glob("capture-*.pcap"),key=lambda x:x.stat().st_mtime)
        for path in list(paths):
            if time.time()-path.stat().st_mtime>self.config["retention"]:
                path.unlink(missing_ok=True);paths.remove(path)
        for path in paths[:-self.config["file_count"]]:path.unlink(missing_ok=True)

    def _save(self,header,frame):
        if not self.config["save_pcap"]:return
        if self.file is None or self.file_size+len(header)+len(frame)>self.config["file_bytes"]:
            if self.file:self.file.close()
            directory=Path(self.config["directory"]);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.chmod(directory,0o700)
            self.sequence+=1
            name=f"capture-{time.time_ns()}-{self.sequence}.pcap"
            fd=os.open(directory/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            self.file=os.fdopen(fd,"wb");self.file.write(self.global_header);self.file_size=len(self.global_header)
            self._cleanup()
        self.file.write(header);self.file.write(frame)
        self.file_size+=len(header)+len(frame)

    def start(self):
        self._cleanup()
        if not self.config["enabled"]:return
        binary=shutil.which("tcpdump")
        if not binary:raise ValueError("tcpdump_required_for_capture")
        expression="(tcp or udp) and ("+" or ".join("port "+str(p) for p in self.config["ports"])+")"
        self.process=subprocess.Popen([binary,"-i",self.config["interface"],"-c",str(self.config["max_packets"]),"-nn","-Z","root","-s","8192","-U","-w","-",expression],
                                      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.state="starting";self.deadline=time.monotonic()+self.config["duration"]
        self.thread=threading.Thread(target=self._run,name="pg-packet-audit",daemon=True);self.thread.start()
        threading.Thread(target=self._timer,name="pg-capture-timer",daemon=True).start()

    def _timer(self):
        if not self.stop_event.wait(self.config["duration"]):self.close()

    def _run(self):
        try:
            self.global_header=self.process.stdout.read(24)
            if len(self.global_header)!=24:raise ValueError("capture_start_failed")
            magic=self.global_header[:4]
            if magic in (b"\xd4\xc3\xb2\xa1",b"\x4d\x3c\xb2\xa1"):endian="<"
            elif magic in (b"\xa1\xb2\xc3\xd4",b"\xa1\xb2\x3c\x4d"):endian=">"
            else:raise ValueError("unsupported_pcap")
            linktype=struct.unpack(endian+"I",self.global_header[20:24])[0]
            self.state="running";self.events.add("capture_started",seconds=self.config["duration"],raw_saved=self.config["save_pcap"])
            tick,seen=time.monotonic(),0
            while not self.stop_event.is_set():
                header=self.process.stdout.read(16)
                if not header:break
                if len(header)!=16:raise ValueError("truncated_pcap")
                _,_,size,original=struct.unpack(endian+"IIII",header)
                if size>262144 or size>original:raise ValueError("invalid_pcap_record")
                frame=self.process.stdout.read(size)
                if len(frame)!=size:raise ValueError("truncated_pcap")
                now=time.monotonic()
                if now-tick>=1:tick,seen=now,0
                seen+=1
                with self.lock:
                    self.metrics["captured_packets"]+=1
                    if seen>self.config["max_pps"]:
                        self.metrics["sampled_out_packets"]+=1;continue
                    self._save(header,frame)
                    item=packet(frame,linktype)
                    if item and size<original:item["truncated"]=True
                    self.analyzer.feed(item)
        except Exception:
            self.state="error";self.events.add("capture_error","error")
        finally:
            if self.file:self.file.close();self.file=None
            if self.process and self.process.poll() is None:self.process.terminate()
            if self.state!="error":self.state="stopped"
            self.events.add("capture_stopped",packets=self.metrics["captured_packets"])
            self.stop_event.set()

    def status(self):
        with self.lock:
            result={"state":self.state,"metrics":dict(self.metrics),"raw_pcap":self.config["save_pcap"],
                    "remaining_seconds":max(0,int(self.deadline-time.monotonic())) if self.state=="running" else 0,
                    "storage_limit_bytes":self.config["file_bytes"]*self.config["file_count"],
                    "summary":self.analyzer.summary()}
        return result

    def close(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)

class BoundedHoney:
    def process_request(self,request,address):
        if not self.owner.admit():
            self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except BaseException:
            self.owner.slots.release()
            raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.owner.slots.release()

class HoneyTCP(BoundedHoney,socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True
    block_on_close=False
    request_queue_size=8

class HoneyUDP(BoundedHoney,socketserver.ThreadingUDPServer):
    allow_reuse_address=True
    daemon_threads=True
    block_on_close=False

class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        owner=self.server.owner
        try:
            self.request.settimeout(2)
            data=self.request.recv(2048)
            owner.record("tcp",data,self.client_address[0])
            # Unknown encrypted bytes never receive a pretend HTTP response.
            if re.match(rb"^(GET|HEAD) /[^ \r\n]* HTTP/1\.[01]\r\n",data):
                body=b"Service ready\n"
                response=b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 14\r\nConnection: close\r\n\r\n"
                self.request.sendall(response+(b"" if data.startswith(b"HEAD ") else body))
        except (OSError,TimeoutError):pass

class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        owner=self.server.owner
        owner.record("udp",self.request[0][:2048],self.client_address[0])

class Honeypot:
    def __init__(self,config,events):
        if not isinstance(config,dict):raise ValueError("invalid_honeypot")
        self.enabled=config.get("enabled",False)
        if type(self.enabled)is not bool:raise ValueError("invalid_honeypot")
        self.bind=str(config.get("bind","127.0.0.1"))
        try:ipaddress.ip_address(self.bind)
        except ValueError:raise ValueError("invalid_honeypot_bind") from None
        self.tcp=bounded_int(config.get("tcp_port"),18080,1024,65535)
        self.udp=bounded_int(config.get("udp_port"),18081,1024,65535)
        self.events,self.servers,self.threads=events,[],[]
        self.slots=threading.BoundedSemaphore(8)
        self.lock=threading.Lock()
        self.counts=Counter()
        self.salt=secrets.token_bytes(32)
        self.tick,self.requests=time.monotonic(),0

    def admit(self):
        with self.lock:
            now=time.monotonic()
            if now-self.tick>=1:self.tick,self.requests=now,0
            self.requests+=1
            if self.requests>20 or not self.slots.acquire(False):
                self.counts["limited"]+=1;return False
        return True

    def record(self,proto,payload,source):
        with self.lock:self.counts[proto]+=1
        self.events.add("honeypot_connection","warning",protocol=proto,length=len(payload),
                        source_tag=__import__("hmac").new(self.salt,source.encode(),"sha256").hexdigest()[:16],
                        payload_digest=__import__("hashlib").sha256(payload).hexdigest(),
                        attribution="unknown",confidence="low")

    def start(self):
        if not self.enabled:return
        family=socket.AF_INET6 if ":" in self.bind else socket.AF_INET
        try:
            for base,port,handler in ((HoneyTCP,self.tcp,TCPHandler),(HoneyUDP,self.udp,UDPHandler)):
                cls=type("BoundHoney",(base,),{"address_family":family})
                server=cls((self.bind,port),handler);server.owner=self
                thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.1},daemon=True)
                self.servers.append(server);self.threads.append(thread);thread.start()
        except BaseException:self.close();raise
        self.events.add("honeypot_started",tcp_port=self.tcp,udp_port=self.udp)

    def status(self):
        with self.lock:return {"enabled":self.enabled,"running":len(self.servers)==2,"counts":dict(self.counts),
                               "mode":"isolated_listener","raw_payload_saved":False}

    def close(self):
        for server in self.servers:server.shutdown();server.server_close()
        for thread in self.threads:thread.join(timeout=2)
        self.servers.clear();self.threads.clear()

class Sensors:
    def __init__(self,config,events):
        self.config,self.events=config,events
        self.capture=Capture(config,events)
        self.honeypot=Honeypot(config.get("honeypot",{}),events)
        self.maintenance_stop=threading.Event()
        self.lock=threading.RLock()
        self.sessions=0
        self.next_capture=None
    def start(self):
        try:
            self.honeypot.start();self.capture.start()
            self.sessions=int(self.capture.config["enabled"])
        except BaseException:self.close();raise
        def maintenance():
            cleanup_at=0
            tick=1 if self.capture.config["enabled"] and self.capture.config["continuous"] else 30
            while not self.maintenance_stop.wait(tick):
                with self.lock:
                    if self.maintenance_stop.is_set():break
                    now=time.monotonic();capture=self.capture
                    if now>=cleanup_at:
                        try:capture._cleanup()
                        except OSError:pass
                        with capture.lock:capture.analyzer.expire(now)
                        self.events.snapshot(limit=1)
                        cleanup_at=now+30
                    if not capture.config["enabled"] or not capture.config["continuous"]:continue
                    if capture.state not in ("stopped","error"):continue
                    if self.next_capture is None:
                        self.next_capture=now+max(capture.config["pause"],30 if capture.state=="error" else 1)
                    if now<self.next_capture:continue
                    capture.close()
                    self.capture=Capture(self.config,self.events,analyzer=capture.analyzer)
                    try:self.capture.start();self.sessions+=1
                    except (OSError,ValueError):self.capture.state="error"
                    self.next_capture=None
        self.thread=threading.Thread(target=maintenance,name="pg-evidence-maintenance",daemon=True)
        self.thread.start()
    def status(self):
        with self.lock:return {"capture":self.capture.status(),"honeypot":self.honeypot.status(),
                               "sessions":self.sessions,"continuous":self.capture.config["continuous"]}
    def close(self):
        self.maintenance_stop.set()
        with self.lock:self.capture.close();self.honeypot.close()
        if hasattr(self,"thread") and self.thread is not threading.current_thread():self.thread.join(timeout=4)
