"""Read-only REALITY configuration and optional bounded TLS readiness checks."""
from __future__ import annotations
import base64,ipaddress,json,re,socket,ssl,time
from pathlib import Path

def config(value):
    value={}if value is None else value
    if not isinstance(value,dict):raise ValueError("invalid_reality_config")
    result={"config_path":value.get("config_path",""),"access_log":value.get("access_log",""),"telemetry_file":value.get("telemetry_file",""),"probe_enabled":value.get("probe_enabled",False),"interval":value.get("interval",300),"log_uid":value.get("log_uid",0)}
    if type(result["log_uid"])is not int or not 0<=result["log_uid"]<=2147483647:raise ValueError("invalid_log_owner")
    for key in ("config_path","access_log","telemetry_file"):
        path=result[key]
        if not isinstance(path,str)or len(path)>512 or(path and(not path.startswith('/')or any(ord(c)<32 for c in path)or path.startswith(('/proc/','/sys/','/dev/')))):
            raise ValueError("invalid_reality_path")
    if type(result["probe_enabled"])is not bool or type(result["interval"])is not int or not 60<=result["interval"]<=3600:raise ValueError("invalid_reality_config")
    return result

def target_parts(value):
    if not isinstance(value,str)or len(value)>300:raise ValueError("invalid_reality_target")
    m=re.fullmatch(r"(?:\[([0-9a-fA-F:]+)\]|([A-Za-z0-9.-]+)):([1-9][0-9]{0,4})",value)
    if not m or int(m[3])>65535:raise ValueError("invalid_reality_target")
    return m[1]or m[2],int(m[3])

def tls_check(target,sni):
    host,port=target_parts(target)
    context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3
    with socket.create_connection((host,port),timeout=3)as raw:
        with context.wrap_socket(raw,server_hostname=sni)as client:
            return {"ok":client.version()=="TLSv1.3","tls":"TLSv1.3"}

class RealityCheck:
    def __init__(self,value,clock=time.monotonic,probe=tls_check):
        self.config=config(value);self.clock,self.probe=clock,probe;self.checked=None
        self.current={"configured":False,"ok":False,"reason":"reality_config_not_configured","inbounds":[]}
        self.tags={}
    def sample(self):
        now=self.clock()
        if self.checked is not None and now-self.checked<self.config["interval"]:return self.current
        self.checked=now;path=self.config["config_path"];self.tags={}
        if not path:return self.current
        try:
            raw=Path(path).read_bytes()
            if len(raw)>2097152:raise ValueError()
            value=json.loads(raw);inbounds=value.get("inbounds",[])
            if not isinstance(inbounds,list)or len(inbounds)>128:raise ValueError()
            result=[];probe_budget=2
            for inbound in inbounds:
                stream=inbound.get("streamSettings",{})
                if stream.get("security")!="reality":continue
                settings=stream.get("realitySettings",{});target=settings.get("target",settings.get("dest",""));target_parts(target)
                port=inbound.get("port")
                if isinstance(port,str)and port.isdigit():port=int(port)
                names=settings.get("serverNames",[]);tag=inbound.get("tag","")
                good=type(port)is int and 1<=port<=65535 and isinstance(names,list)and 1<=len(names)<=32
                good=good and all(isinstance(n,str)and len(n)<=253 and re.fullmatch(r"[A-Za-z0-9.-]*",n)is not None for n in names)
                key=settings.get("privateKey","")
                try:key_ok=isinstance(key,str)and re.fullmatch(r"[A-Za-z0-9_-]{43}=?",key)is not None and len(base64.urlsafe_b64decode(key+"="*((-len(key))%4)))==32
                except (ValueError,TypeError):key_ok=False
                ids=settings.get("shortIds",[])
                good=good and key_ok and isinstance(ids,list)and bool(ids)and all(isinstance(x,str)and len(x)<=16 and len(x)%2==0 and re.fullmatch(r"[0-9a-fA-F]*",x)is not None for x in ids)
                native={}
                for name in("limitFallbackUpload","limitFallbackDownload"):
                    limits=settings.get(name,{})
                    if not isinstance(limits,dict):good=False;limits={}
                    rate=limits.get("bytesPerSec",0);after=limits.get("afterBytes",0)
                    native[name]={"enabled":type(rate)is int and rate>0,"bytes_per_second":rate if type(rate)is int and 0<=rate<=1073741824 else 0,"after_bytes":after if type(after)is int and after>=0 else 0}
                entry={"port":port,"tag":tag[:64]if isinstance(tag,str)else"","target":target,"server_names":names[:4] if good else[],"config_ok":bool(good),"native_fallback_limits":native,"tls_checks":[]}
                if self.config["probe_enabled"]and good:
                    for name in names[:2]:
                        if probe_budget<=0:break
                        probe_budget-=1
                        if not name:entry["tls_checks"].append({"sni":"","ok":False,"reason":"empty_sni_not_probed"});continue
                        try:check=self.probe(target,name)
                        except Exception:check={"ok":False,"reason":"target_tls_check_failed"}
                        entry["tls_checks"].append(dict(sni=name,**check))
                if good and isinstance(tag,str)and tag:self.tags[tag]=port
                result.append(entry)
                if len(result)>=16:break
            self.current={"configured":True,"ok":bool(result)and all(e["config_ok"]and all(t["ok"]for t in e["tls_checks"])for e in result),"inbounds":result,"checked_uptime":now,"network_checks_enabled":self.config["probe_enabled"],"authentication_not_inferred_from_sni":True}
        except (OSError,ValueError,TypeError,AttributeError):self.current={"configured":True,"ok":False,"reason":"reality_config_unreadable_or_invalid","inbounds":[]}
        return self.current
    def status(self):return dict(self.current)
