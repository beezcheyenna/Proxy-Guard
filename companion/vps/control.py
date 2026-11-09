"""Authenticated health/control API; optional direct HTTPS, optional CF signed relay."""
from __future__ import annotations
import sys,collections,copy,hashlib,hmac,ipaddress,json,re,secrets,socket,ssl,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from monitor import Monitor,EventStore
from egress import EgressInfo

class Server(ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=16

    def __init__(self,bind,engine,config,edition="pro"):
        self.engine,self.config,self.edition=engine,config,edition
        self.egress=EgressInfo(config.get("egress"))
        token=config.get("direct_token","")
        if token and (not isinstance(token,str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",token) or token.startswith("REPLACE_")):
            raise ValueError("invalid_direct_token")
        self.direct_token=token
        self.path_token=config.get("path_token",token)
        if self.path_token and(not isinstance(self.path_token,str)or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",self.path_token)or self.path_token.startswith("REPLACE_")):raise ValueError("invalid_path_token")
        self.nonces=collections.OrderedDict();self.nonce_lock=threading.Lock()
        self.events=EventStore(config.get("event_limit",512),config.get("event_retention",86400))
        self.monitor=Monitor(config,self.events)
        self.slots=threading.BoundedSemaphore(24)
        self.sensors=None
        self.honey_rule_ids=set()
        self.address_family=socket.AF_INET6 if ":" in bind[0] else socket.AF_INET
        super().__init__(bind,Handler)
        if bind[0]not in ("127.0.0.1","::1","localhost"):
            if not token or not config.get("tls_cert") or not config.get("tls_key"):
                self.server_close()
                raise ValueError("external_bind_requires_https_and_direct_token")
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config["tls_cert"],config["tls_key"])
            self.socket=context.wrap_socket(self.socket,server_side=True,do_handshake_on_connect=False)
        elif config.get("tls_cert"):
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(config["tls_cert"],config["tls_key"])
            self.socket=context.wrap_socket(self.socket,server_side=True,do_handshake_on_connect=False)
        self.monitor.start()
        from safety import Safety
        from maintenance import Maintenance
        from reality_check import RealityCheck
        from telemetry import Telemetry
        self.safety=Safety(engine,self.events)
        self.trial_epoch=engine.trials.restoration_epoch
        self.reality=RealityCheck(config.get("reality"))
        self.telemetry=Telemetry(engine,self.reality,self.events)
        self.maintenance=Maintenance(config.get("maintenance"),str(engine.path)+".operations",self.monitor,self.events)
        self.maintenance.authorized=lambda record:record.get("revision")==self.engine.state["revision"]
        if edition=="pro-max":
            from sensors import Sensors
            try:
                analysis=config.get("analysis",{})
                if edition=="pro" and (analysis.get("save_pcap") or analysis.get("honeypot",{}).get("enabled")):
                    raise ValueError("evidence_capture_requires_pro_max")
                self.sensors=Sensors(analysis,self.events)
                self.sensors.start()
                honey=self.sensors.honeypot
                if honey.enabled and not ipaddress.ip_address(honey.bind).is_loopback:
                    # Publish exceptions only after both isolated listeners bind.
                    # Never exempt a real service merely because binding failed.
                    with self.engine.lock:
                        for proto,port in (("tcp",honey.tcp),("udp",honey.udp)):
                            ident=f"_honey_{id(self):x}_{proto}"
                            self.honey_rule_ids.add(ident)
                            self.engine.local_rules.append({"id":ident,"name":"Explicit honeypot listener","enabled":True,
                                "protocol":proto,"ports":[str(port)],"source_mode":"any","sources":[]})
                        self.engine.driver.apply(self.engine.effective_policy(),self.engine.leases)
            except BaseException:
                self.server_close()
                raise
        self.reconcile_stop=threading.Event()
        self.firewall={"verified":False,"packets_dropped":0,"bytes_dropped":0}
        def reconcile():
            while not self.reconcile_stop.is_set():
                try:
                    self.reality.sample()
                    with self.engine.lock:
                        rolled=self.engine.trials.tick()
                        self.refresh_trial_runtime()
                        changed=self.safety.tick()or rolled
                        driver=self.engine.driver
                        if hasattr(driver,"snapshot"):
                            from agent import stable_rules,GUARD,BOOT,policy_hash
                            current=driver.snapshot()
                            changed=self.telemetry.poll(current) or changed
                            desired=self.engine.effective_policy()
                            good=current is not None and driver.fingerprint==stable_rules(current) and driver.snapshot(GUARD) is None and driver.snapshot(BOOT) is None and driver.last_hash==policy_hash(desired) and driver.runtime_matches(desired,self.engine.leases,current)
                            if not good or changed:
                                driver.apply(desired,self.engine.leases)
                                if not good:self.events.add("firewall_repaired","warning")
                                current=driver.snapshot()
                            packets=bytes_=0
                            for row in (current or {}).get("nftables",[]):
                                for expr in row.get("rule",{}).get("expr",[]):
                                    counter=expr.get("counter") if isinstance(expr,dict) else None
                                    if isinstance(counter,dict):
                                        packets+=counter.get("packets",0);bytes_+=counter.get("bytes",0)
                            self.firewall={"verified":current is not None,"packets_dropped":packets,"bytes_dropped":bytes_}
                            self.engine.ready=current is not None
                except Exception:
                    self.engine.ready=False;self.firewall={"verified":False}
                    self.events.add("firewall_verification_failed","error")
                if self.reconcile_stop.wait(5):break
        self.reconcile_thread=threading.Thread(target=reconcile,name="pg-firewall-monitor",daemon=True)
        self.reconcile_thread.start()
        self.egress.start()
        self.events.add("agent_started",edition=edition)

    def process_request(self,request,address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except BaseException:
            self.slots.release();raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

    def server_close(self):
        if hasattr(self,"reconcile_stop"):self.reconcile_stop.set()
        if hasattr(self,"reconcile_thread"):self.reconcile_thread.join(timeout=30)
        try:
            if getattr(self,"honey_rule_ids",None):
                with self.engine.lock:
                    self.engine.local_rules=[r for r in self.engine.local_rules if r["id"] not in self.honey_rule_ids]
                    self.honey_rule_ids.clear()
                    self.engine.driver.apply(self.engine.effective_policy(),self.engine.leases)
        finally:
            if hasattr(self,"egress"):self.egress.close()
            if hasattr(self,"maintenance"):self.maintenance.close()
            if hasattr(self,"monitor"):self.monitor.close()
            if self.sensors:self.sensors.close()
            super().server_close()

    def claim_nonce(self,body,channel="control"):
        if body.get("device_id")!=self.engine.device_id or type(body.get("issued_at"))is not int or abs(body["issued_at"]-int(time.time()*1000))>60000:
            raise PermissionError("expired_request")
        ident=body.get("request_id")
        try:
            if str(uuid.UUID(ident))!=ident:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise PermissionError("invalid_request_id")from None
        now=time.monotonic();key=(channel,ident)
        with self.nonce_lock:
            while self.nonces and next(iter(self.nonces.values()))<now-120:self.nonces.popitem(last=False)
            if key in self.nonces:raise PermissionError("replayed_request")
            if len(self.nonces)>=4096:raise PermissionError("too_many_requests")
            self.nonces[key]=now

    def handle_error(self,request,client_address):
        # Invalid TLS/plain HTTP and disconnected clients are expected on a
        # public control socket. Do not turn them into unbounded journal traces.
        if isinstance(sys.exc_info()[1],(ssl.SSLError,TimeoutError,ConnectionError)):
            with self.nonce_lock:
                now=time.monotonic()
                if now-getattr(self,'connection_failure_at',-1e20)>=5:
                    self.connection_failure_at=now
                    self.events.add('control_connection_failed','warning')
            return
        return super().handle_error(request,client_address)

    def refresh_trial_runtime(self):
        epoch=self.engine.trials.restoration_epoch
        if getattr(self,"trial_epoch",epoch)!=epoch:
            if hasattr(self,"telemetry"):
                self.telemetry.trusted.clear();self.telemetry.restricted.clear();self.telemetry.flows.clear()
            if self.engine.trials.safety_changed:
                from safety import Safety
                self.safety=Safety(self.engine,self.events)
            self.trial_epoch=epoch
            self.events.add("policy_trial_rolled_back","warning")

    def activity(self,channel,synced=False):
        with self.engine.lock:
            self.refresh_trial_runtime()
            changed=self.safety.note_path()if channel=="proxy"else self.safety.note_control(synced)
            if changed:self.engine.driver.apply(self.engine.effective_policy(),self.engine.leases)

    def status(self,include_analysis=True):
        from protection import mode_metadata
        with self.engine.lock:
            leases={str(family):{"expires_in":max(0,int(value[1]-time.monotonic()))}
                    for family,value in self.engine.leases.items() if value[1]>time.monotonic()}
            revision=self.engine.state["revision"]
            ready=self.engine.ready
            policy=copy.deepcopy(self.engine.state["policy"])
            trial_status=self.engine.trials.status()
        result={"ok":True,"protocol":3,"edition":self.edition,"agent_ready":ready,"health":self.monitor.status(),
                "leases":leases,"revision":revision,"firewall":self.firewall,"analysis_exported":include_analysis,
                "ingress":{"enabled":policy["enabled"],"default_deny":policy.get("default_deny",False),
                           "auto_discover":policy.get("auto_discover",False),
                           "address_families":policy.get("address_families",[4,6]),
                           "mode":policy.get("mode","standard"),"ssh":policy.get("ssh",{}),"outbound_replies_preserved":True,"scope":"selected_host_input_ports"}}
        result["ingress"].update(mode_metadata(policy))
        result["ingress"]["policy_confirmation"]=True
        result["policy_trial"]=trial_status
        if hasattr(self,"safety"):result["ssh_rescue"]=self.safety.status()
        if hasattr(self,"maintenance"):result["maintenance"]=self.maintenance.status()
        if hasattr(self,"telemetry"):
            result["resources"]=self.telemetry.status()
            if not include_analysis:
                result["resources"].pop("sources",None)
                native=result["resources"].get("native_checks",{})
                result["resources"]["native_checks"]={k:native[k]for k in("configured","ok","reason")if k in native}
                result["resources"]["details_exported"]=False
            else:result["resources"]["details_exported"]=True
        if include_analysis:
            result["events"]=self.events.snapshot(limit=20)
            result["inventory"]=self.engine.inventory.report()
            if self.sensors:result["analysis"]=self.sensors.status()
            # Optional evidence must not turn a healthy, authenticated report
            # into HTTP 503 just because listeners/events filled their bounds.
            def encoded_size():
                return len(json.dumps(result,separators=(",",":"),allow_nan=False).encode())
            optional=[(result["events"],"events"),(result["inventory"],"listeners")]
            if "resources"in result:
                optional.insert(0,(result["resources"],"sources"))
                native=result["resources"].get("native_checks",{})
                optional.insert(0,(native,"inbounds"))
            for section,key in optional:
                while section.get(key) and encoded_size()>30000:
                    section[key].pop(0)
                    section["truncated"]=True
                    result["report_truncated"]=True
        return result

class Handler(BaseHTTPRequestHandler):
    server_version="ProxyGuardAgent"
    sys_version=""
    protocol_version="HTTP/1.0"

    def log_message(self,*args):pass

    def setup(self):
        self.connection=self.request
        self.connection.settimeout(8)
        if isinstance(self.connection,ssl.SSLSocket):self.connection.do_handshake()
        super().setup()

    def send(self,code,payload):
        data=json.dumps(payload,separators=(",",":"),allow_nan=False).encode()
        if len(data)>32768:
            code,data=503,b'{"ok":false,"code":"response_limit"}'
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers();self.wfile.write(data)

    def direct_auth(self,path=False):
        token=self.server.path_token if path else self.server.direct_token
        expected="Bearer "+token
        supplied=self.headers.get("authorization","")
        good=bool(token) and len(supplied)<=300 and hmac.compare_digest(supplied.encode("utf-8"),expected.encode("ascii"))
        if not good:self.server.events.add("authentication_failed","warning",transport="direct")
        return good

    def egress_info(self):
        try:
            return self.send(200,self.server.egress.report())
        except Exception:
            return self.send(503,{"ok":False,"code":"egress_info_unavailable"})

    def do_GET(self):
        if self.path=="/health":
            return self.send(200,{"ok":self.server.engine.ready})
        if self.path not in ("/v1/direct/observe","/v1/direct/status","/v1/direct/egress-info"):
            return self.send(404,{"ok":False})
        if not self.direct_auth():return self.send(401,{"ok":False,"code":"unauthorized"})
        if self.path=="/v1/direct/egress-info":return self.egress_info()
        if self.path.endswith("/status"):
            self.server.activity("control");return self.send(200,self.server.status())
        try:
            address=ipaddress.ip_address(self.client_address[0])
            if getattr(address,"ipv4_mapped",None):address=address.ipv4_mapped
            if not address.is_global or address.is_multicast:raise ValueError()
            self.send(200,{"ok":True,"observed_ip":str(address),"family":address.version})
        except ValueError:self.send(400,{"ok":False,"code":"public_source_required"})

    def do_POST(self):
        signed=self.path in("/v1/sync","/v1/status","/v1/command","/v1/egress-info","/v1/policy-confirm","/v1/policy-cancel")
        direct=self.path in("/v1/direct/sync","/v1/direct/command","/v1/direct/path-heartbeat","/v1/direct/policy-confirm","/v1/direct/policy-cancel")
        path_heartbeat=self.path.endswith('/path-heartbeat')
        if not signed and not direct:return self.send(404,{"ok":False})
        if direct and not self.direct_auth(path_heartbeat):return self.send(401,{"ok":False,"code":"unauthorized"})
        size=self.headers.get("content-length","")
        if self.headers.get("transfer-encoding")or not size.isdigit()or not 1<=int(size)<=32768:return self.send(413,{"ok":False,"code":"invalid_size"})
        raw=self.rfile.read(int(size))
        if len(raw)!=int(size):return self.send(400,{"ok":False,"code":"incomplete_request"})
        try:
            if signed:
                expected=hmac.new(self.server.engine.secret,raw,hashlib.sha256).hexdigest()
                supplied=self.headers.get("x-pg-signature","")
                if len(supplied)!=64 or not hmac.compare_digest(expected.encode("ascii"),supplied.encode("utf-8")):raise PermissionError()
            body=json.loads(raw)
            if not isinstance(body,dict):raise ValueError()
            if self.path=="/v1/egress-info":
                if set(body)-{"device_id","issued_at","request_id","purpose"} or body.get("purpose")!="egress-info":raise ValueError("invalid_request")
                self.server.claim_nonce(body,"egress-info")
                return self.egress_info()
            if body.get('purpose')=='egress-info':raise ValueError('invalid_request')
            if not self.path.endswith('/sync'):
                self.server.claim_nonce(body,'proxy'if path_heartbeat else'control')
                if path_heartbeat:
                    if body.get('channel')!='proxy':raise ValueError('invalid_channel')
                    self.server.activity('proxy');return self.send(200,{'ok':True,'channel':'proxy'})
                if self.path.endswith(('/policy-confirm','/policy-cancel')):
                    with self.server.engine.lock:
                        trial=self.server.engine.trials.action('confirm'if self.path.endswith('/policy-confirm')else'cancel',body.get('trial_id'),body.get('revision'))
                    self.server.activity('control');return self.send(200,{'ok':True,'policy_trial':trial})
                if self.path.endswith('/command'):
                    if type(body.get('revision'))is not int or body.get('revision')!=self.server.engine.state['revision']:raise ValueError('invalid_revision')
                    result=self.server.maintenance.submit(body)
                    self.server.activity('control');return self.send(200,{'ok':True,'operation':result})
                self.server.activity('control')
                return self.send(200,self.server.status(include_analysis=body.get('include_analysis')is True))
            if direct:
                address=ipaddress.ip_address(self.client_address[0])
                if getattr(address,'ipv4_mapped',None):address=address.ipv4_mapped
                if str(address)!=body.get('observed_ip'):raise ValueError('source_changed')
                signature=hmac.new(self.server.engine.secret,raw,hashlib.sha256).hexdigest()
            else:signature=self.headers.get('x-pg-signature')
            result=self.server.engine.sync(raw,signature)
            self.server.activity('control',synced=True)
            self.server.events.add('authorization_applied',revision=body.get('revision'),family=ipaddress.ip_address(body['observed_ip']).version)
            return self.send(200,result)
        except PermissionError:
            self.server.events.add('authentication_failed','warning',transport='control')
            return self.send(403,{'ok':False,'code':'operation_or_authentication_denied'})
        except (ValueError,TypeError,KeyError)as error:
            code=str(error)
            allowed={'replayed_or_stale_request','expired_request','source_changed','invalid_revision','invalid_policy','invalid_protection_mode','invalid_ssh_policy','ssh_port_overlaps_service','operation_busy','operation_cooldown','expired_operation','unsupported_action','xui_usr1_not_confirmed','invalid_operation_id','operation_id_conflict','invalid_policy_trial','policy_trial_busy','policy_trial_expired','policy_trial_mismatch','policy_trial_not_ready'}
            return self.send(400,{'ok':False,'code':code if code in allowed else'invalid_request'})
        except Exception:
            self.server.events.add('control_update_failed','error')
            return self.send(503,{'ok':False,'code':'agent_update_failed'})
