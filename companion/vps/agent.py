#!/usr/bin/env python3
"""Loopback-only, authenticated VPS input-port policy agent. No shell execution."""
from __future__ import annotations
import argparse
import sys
import contextlib
import fcntl
import copy
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from protection import mode_metadata

TABLE = "pg_vps_access"
GUARD = "pg_vps_access_update"
BOOT = "pg_vps_access_boot"
MAX_BODY = 32768
PROTOCOL = 3
# Legacy flags remain in signed replies for compatibility; they never expand
# enforcement beyond explicitly configured service rules.
DEFAULT_POLICY = {"enabled": True, "default_deny": False, "auto_discover": False,
                  "address_families": [4,6], "rules": [], "mode":"standard", "ssh":__import__("protection").normalize_ssh({})}

class Invalid(ValueError):
    pass

def normalize_policy(enabled, rules, default_deny=False, auto_discover=False, address_families=None, mode="standard", ssh=None):
    from protection import MODES,normalize_ssh,normalize_limits
    if mode not in MODES:raise Invalid("invalid_protection_mode")
    try:ssh=normalize_ssh(ssh)
    except ValueError as error:raise Invalid(str(error))from None
    address_families=[4,6] if address_families is None else address_families
    if not isinstance(address_families,list) or not 1<=len(address_families)<=2 or any(type(v)is not int or v not in (4,6) for v in address_families) or len(set(address_families))!=len(address_families):
        raise Invalid("invalid_address_families")
    if type(default_deny) is not bool or type(auto_discover) is not bool:
        raise Invalid("invalid_ingress_policy")
    if type(enabled) is not bool or not isinstance(rules, list) or len(rules) > 32:
        raise Invalid("invalid_policy")
    out, used, ids = [], {"tcp": [], "udp": []}, set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise Invalid("invalid_rule")
        ident = rule.get("id", "")
        name = rule.get("name", "")
        active = rule.get("enabled")
        proto, source_mode = rule.get("protocol"), rule.get("source_mode")
        if (not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", ident)
            or ident in ids or not isinstance(name, str) or not 1 <= len(name) <= 64
            or any(ord(x) < 32 for x in name) or type(active) is not bool
            or proto not in ("tcp", "udp", "both")
            or source_mode not in ("any", "all", "dynamic", "static", "mixed")):
            raise Invalid("invalid_rule")
        selected_mode=rule.get("mode","inherit")
        if not isinstance(selected_mode,str)or selected_mode not in (*MODES,"inherit"):raise Invalid("invalid_rule_mode")
        if active and source_mode=="all"and (mode if selected_mode=="inherit"else selected_mode)=="whitelist":
            raise Invalid("whitelist_requires_authorized_sources")
        ids.add(ident)
        ports, spans = rule.get("ports"), []
        if not isinstance(ports, list) or not 1 <= len(ports) <= 32:
            raise Invalid("invalid_ports")
        for port in ports:
            if not isinstance(port, str) or not re.fullmatch(r"[1-9][0-9]{0,4}(?:-[1-9][0-9]{0,4})?", port):
                raise Invalid("invalid_ports")
            a, _, b = port.partition("-"); a, b = int(a), int(b or a)
            if not 1 <= a <= b <= 65535 or any(a <= y and b >= x for x, y in spans):
                raise Invalid("overlapping_ports")
            spans.append((a, b))
        sources = rule.get("sources", [])
        if not isinstance(sources, list) or len(sources) > 64:
            raise Invalid("invalid_sources")
        canonical = []
        for source in sources:
            if not isinstance(source, str) or len(source) > 64:
                raise Invalid("invalid_sources")
            try:
                net = ipaddress.ip_network(source, strict=False)
            except ValueError:
                raise Invalid("invalid_sources") from None
            canonical.append(str(net))
        if source_mode == "static" and not canonical and active:
            raise Invalid("empty_static_whitelist")
        if active:
            for family in (("tcp", "udp") if proto == "both" else (proto,)):
                for a, b in spans:
                    if any(a <= y and b >= x for x, y in used[family]):
                        raise Invalid("overlapping_rules")
                used[family].extend(spans)
        try:limits=normalize_limits(rule.get("limits"))
        except ValueError as error:raise Invalid(str(error))from None
        if active and ssh["managed"]and proto in("tcp","both")and any(a<=ssh["port"]<=b for a,b in spans):raise Invalid("ssh_port_overlaps_service")
        out.append({"id": ident, "name": name, "enabled": active, "protocol": proto,
                    "ports": [str(a) if a == b else f"{a}-{b}" for a, b in spans],
                    "source_mode": source_mode, "sources": sorted(set(canonical)), "limits":limits,"mode":selected_mode})
    return {"enabled": enabled, "rules": out, "default_deny": False, "auto_discover": False, "address_families": sorted(address_families), "mode":mode, "ssh":ssh}

def policy_hash(policy):
    return hashlib.sha256(json.dumps({k:v for k,v in policy.items()if k!="_runtime"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def render(policy, leases, table=TABLE, mono=None):
    assert table in (TABLE, GUARD, BOOT)
    from protection import render as selected_render
    return selected_render(policy,leases,table,mono)

def stable_rules(data):
    """Fingerprint rules and static sets; counters and dynamic expiry vary."""
    def prune(value):
        if isinstance(value, list):
            return [prune(x) for x in value]
        if isinstance(value, dict):
            return {k: ({} if k == "counter" else prune(v)) for k, v in value.items()
                    if k not in ("handle", "index", "expires")}
        return value
    rows = []
    for row in data.get("nftables", []):
        if "metainfo" in row:
            continue
        row = copy.deepcopy(row)
        for kind in ("set", "element"):
            item = row.get(kind)
            if item and item.get("name","").startswith(("dynamic","ssh_managed","ssh_hold","ssh_public","ssh_last","trusted","seen","cool","rate","conns","fallback","bw","newflow","capacity","watchconns")):
                item.pop("elem", None)
        rows.append(prune(row))
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class Nft:
    def __init__(self, binary="/usr/sbin/nft", owner_fd=None):
        self.binary, self.last_hash, self.fingerprint = binary, None, None
        self.owner_fd = owner_fd

    def call(self, args, text=None, check=True):
        result = subprocess.run([self.binary, *args], input=text, text=True, capture_output=True, timeout=8, pass_fds=(() if self.owner_fd is None else (self.owner_fd,)))
        if check and result.returncode:
            # No payload, token, request body or arbitrary nft output in HTTP errors.
            raise RuntimeError("firewall_update_failed")
        return result

    def snapshot(self, table=TABLE):
        p = self.call(["-j", "list", "table", "inet", table], check=False)
        return json.loads(p.stdout) if p.returncode == 0 else None

    def commit(self, text):
        self.call(["-c", "-f", "-"], text)
        self.call(["-f", "-"], text)

    def runtime_matches(self,policy,leases,current):
        from protection import runtime_elements
        now=time.monotonic();expected=runtime_elements(policy,leases,now)
        sets={row['set']['name']:row['set']for row in current.get('nftables',[])if 'set'in row}
        def canonical(parts):
            result=[]
            for value in parts:
                try:value=str(ipaddress.ip_address(value))if isinstance(value,str)and(':'in value or'.'in value)else str(value)
                except ValueError:return None
                result.append(value)
            return tuple(result)
        for name,values in expected.items():
            if name not in sets:return False
            wanted={}
            for value in values:
                key,_,ttl=value.partition(' timeout ')
                wanted[canonical(key.split(' . '))]=int(ttl[:-1])if ttl else None
            actual={}
            for value in sets[name].get('elem',[]):
                item=value.get('elem',value)if isinstance(value,dict)else {'val':value}
                val=item.get('val')
                parts=val.get('concat',[])if isinstance(val,dict)else[val]
                key=canonical(parts)
                if key is None:return False
                actual[key]=item.get('expires')
            if set(wanted)!=set(actual):return False
            for key,ttl in wanted.items():
                if ttl is None and actual[key] not in (None,0):return False
                if ttl is not None and(type(actual[key])not in(int,float)or actual[key]>ttl+2):return False
        return True

    def bootstrap(self, policy=None):
        # No dynamic permissions survive startup. Unknown ports are left alone.
        # Cold boot can load nftables modules while the system is busy. Only
        # this idempotent startup transaction may be retried after a timeout;
        # normal HTTP policy/command mutations retain their existing semantics.
        for attempt in range(3):
            try:
                # Relative SSH rescue timers must reflect the current attempt.
                text = f"add table inet {BOOT}\ndelete table inet {BOOT}\n" + render(DEFAULT_POLICY if policy is None else policy, {}, BOOT)
                self.commit(text)
                return
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    raise
                print(f"Startup firewall command timed out; retrying ({attempt + 2}/3)", file=sys.stderr, flush=True)
                time.sleep(1)

    def apply(self, policy, leases):
        digest, current = policy_hash(policy), self.snapshot()
        guarded = self.snapshot(GUARD) is not None
        if current and not guarded and self.last_hash == digest and self.fingerprint == stable_rules(current):
            from protection import runtime_updates
            self.commit(runtime_updates(policy,leases,TABLE))
        else:
            # Separately committed coverage remains active during rule rewrites.
            if not guarded:
                self.commit(render(policy, leases, GUARD))
            self.commit(f"add table inet {TABLE}\ndelete table inet {TABLE}\n" + render(policy, leases))
            current = self.snapshot()
            if current is None:
                raise RuntimeError("firewall_verification_failed")
            self.fingerprint = stable_rules(current)
            self.call(["delete", "table", "inet", GUARD])
            self.last_hash = digest
        if self.snapshot(BOOT) is not None:
            self.call(["delete", "table", "inet", BOOT])

    def cleanup(self):
        for table in (TABLE, GUARD, BOOT):
            if self.snapshot(table) is not None:
                self.call(["delete", "table", "inet", table])

def write_private_json(path, value, unchanged_ok=False):
    path = Path(path)
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if unchanged_ok:
        try:
            with path.open("rb") as stream:
                if stream.read(len(data) + 1) == data and path.stat().st_mode & 0o777 == 0o600:
                    return
        except OSError:
            pass
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".access-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass


def load_bootstrap_policy(state_path):
    """Restore only known selected ports, before parsing the service config."""
    state_path = Path(state_path)
    for path, saved_state in ((state_path, True), (state_path.with_name(state_path.name + ".policy"), False)):
        try:
            limit=262144 if saved_state else 65536
            with path.open("rb") as stream:
                raw = stream.read(limit+1)
            if len(raw) > limit:
                continue
            value = json.loads(raw)
            policy = value["policy"] if saved_state else value
            policy=normalize_policy(policy["enabled"], policy["rules"],
                                    policy.get("default_deny", False), policy.get("auto_discover", False),
                                    policy.get("address_families", [4,6]),policy.get("mode","standard"),policy.get("ssh"))
            if saved_state and Path(str(state_path)+'.trial').exists():
                if not isinstance(value.get('seen'),dict)or type(value.get('latest'))is not int or type(value.get('revision',0))is not int:raise Invalid('invalid_saved_state')
                value['policy']=policy
                from policy_trial import recover_bootstrap_policy
                return recover_bootstrap_policy(state_path,value)
            return policy
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return copy.deepcopy(DEFAULT_POLICY)


class Engine:
    def __init__(self, secret, device_id, state_path, driver, inventory=None, local_rules=()):
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", secret or "") or secret.startswith("REPLACE_"):
            raise Invalid("configure_agent_secret")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id or ""):
            raise Invalid("invalid_device_id")
        self.secret, self.device_id = secret.encode(), device_id
        self.path, self.driver = Path(state_path), driver
        from discovery import Inventory
        self.inventory = inventory or Inventory()
        self.local_rules = list(local_rules)
        self.lock, self.leases, self.ready = threading.RLock(), {}, False
        self.state = {"seen": {}, "latest": 0, "revision": 0, "policy": copy.deepcopy(DEFAULT_POLICY)}
        if self.path.exists():
            previous = json.loads(self.path.read_text())
            previous["policy"] = normalize_policy(previous["policy"]["enabled"], previous["policy"]["rules"], previous["policy"].get("default_deny", False), previous["policy"].get("auto_discover", False), previous["policy"].get("address_families", [4,6]),previous["policy"].get("mode","standard"),previous["policy"].get("ssh"))
            if not isinstance(previous.get("seen"), dict) or type(previous.get("latest")) is not int:
                raise Invalid("invalid_saved_state")
            previous.setdefault("revision", 0)
            self.state = previous
            write_private_json(self.path.with_name(self.path.name + ".policy"), previous["policy"], unchanged_ok=True)
        from policy_trial import PolicyTrial
        self.trials=PolicyTrial(self)
        self.trials.tick(live=False)
        from safety import boot_runtime
        self.runtime=boot_runtime(self.path,self.state["policy"],persist=True)
        # Never resurrect a dynamic lease after restart or a clock correction.
        self.driver.apply(self.effective_policy(), {})
        self.ready = True

    def effective_policy(self):
        from discovery import effective_policy
        result=effective_policy(self.state["policy"], (), self.local_rules)
        result["_runtime"]=copy.deepcopy(self.runtime)
        return result

    def save(self, value):
        # Keep a separate last-valid port policy for config/state corruption.
        # This cache contains no keys, nonces or dynamic authorizations.
        write_private_json(self.path.with_name(self.path.name + ".policy"), value["policy"], unchanged_ok=True)
        write_private_json(self.path, value)

    def sync(self, raw, signature):
        if len(raw) > MAX_BODY:
            raise Invalid("body_too_large")
        expected = hmac.new(self.secret, raw, hashlib.sha256).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
            raise PermissionError("unauthorized")
        try: body = json.loads(raw)
        except (ValueError, UnicodeError): raise Invalid("invalid_json") from None
        if not isinstance(body, dict) or body.get("device_id") != self.device_id:
            raise Invalid("invalid_device")
        issued, nonce, ttl = body.get("issued_at"), body.get("request_id"), body.get("ttl")
        now = int(time.time() * 1000)
        if type(issued) is not int or abs(now - issued) > 120000:
            raise Invalid("expired_request")
        if not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9-]{36}", nonce):
            raise Invalid("invalid_request_id")
        if type(ttl) is not int or not 120 <= ttl <= 86400:
            raise Invalid("invalid_ttl")
        try: address = ipaddress.ip_address(body.get("observed_ip"))
        except (ValueError, TypeError): raise Invalid("invalid_source_ip") from None
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise Invalid("invalid_source_ip")
        if "address_families" in body and body["address_families"] is None:
            raise Invalid("invalid_address_families")
        policy = normalize_policy(body.get("policy_enabled"), body.get("rules"), body.get("default_deny", False), body.get("auto_discover", False), body.get("address_families", [4,6]),body.get("mode","standard"),body.get("ssh"))
        for local in self.local_rules:
            for rule in policy['rules']:
                if not rule['enabled']or rule['source_mode']=='any':continue
                protocols={'tcp','udp'}if rule['protocol']=='both'else{rule['protocol']}
                local_protocols={'tcp','udp'}if local['protocol']=='both'else{local['protocol']}
                if not protocols&local_protocols:continue
                for selected in rule['ports']:
                    lo,_,hi=selected.partition('-');lo,hi=int(lo),int(hi or lo)
                    for port in local['ports']:
                        start,_,end=port.partition('-');start,end=int(start),int(end or start)
                        if lo<=end and hi>=start:raise Invalid('reserved_control_port')
        if address.version not in policy["address_families"]:
            raise Invalid("source_family_not_selected")
        revision = body.get("revision")
        if type(revision) is not int or not 1 <= revision <= 9007199254740991:
            raise Invalid("invalid_revision")
        with self.lock:
            self.trials.tick()
            seen = {key: value for key, value in self.state["seen"].items() if value >= now - 120000}
            if (nonce in seen or issued < self.state["latest"] or revision < self.state["revision"]
                or revision == self.state["revision"] and policy_hash(policy) != policy_hash(self.state["policy"])):
                raise Invalid("replayed_or_stale_request")
            if len(seen) >= 2048:
                raise Invalid("too_many_requests")
            self.trials.begin(policy,revision,body.get('policy_trial'))
            seen[nonce] = issued
            reserved = {"seen": seen, "latest": issued, "revision": revision, "policy": policy}
            # Reserve before nft I/O; a killed agent cannot accept the same signed command again.
            self.save(reserved); self.state = reserved
            leases = {version:lease for version,lease in self.leases.items() if version in policy["address_families"]}
            leases[address.version] = (str(address), time.monotonic() + ttl)
            self.ready = False
            # Keep the last authenticated desired leases for bounded repair;
            # never restore an older source if a kernel update fails mid-flight.
            self.leases = leases
            try:self.driver.apply(self.effective_policy(), leases)
            except Exception:
                self.trials.rollback('apply_failed')
                raise
            self.ready = True
            self.trials.applied()
            # Report the remaining monotonic lease, including time spent applying nft.
            applied_at = int(time.time())
            remaining = max(0, int(leases[address.version][1] - time.monotonic()))
            return {"ok": True, "protocol":PROTOCOL,"policy":dict({key:policy[key] for key in ("enabled","default_deny","auto_discover","address_families","mode","ssh")},**mode_metadata(policy)), "observed_ip": str(address), "expires_at": applied_at + remaining,
                    "applied_at": applied_at, "policy_hash": policy_hash(policy),"policy_trial":self.trials.status()}

class Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8
    def __init__(self, bind, engine):
        self.engine = engine
        super().__init__(bind, Handler)

class Handler(BaseHTTPRequestHandler):
    server_version = "ProxyGuardAccess"
    def log_message(self, *args): pass
    def setup(self):
        super().setup(); self.connection.settimeout(10)
    def send(self, code, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.send(200 if self.path == "/health" else 404,
                  {"ok": bool(self.server.engine.ready)} if self.path == "/health" else {"ok": False})
    def do_POST(self):
        if self.path != "/v1/sync":
            return self.send(404, {"ok": False})
        size = self.headers.get("content-length", "")
        if self.headers.get("transfer-encoding") or not size.isdigit() or not 1 <= int(size) <= MAX_BODY:
            return self.send(413, {"ok": False, "code": "invalid_size"})
        raw = self.rfile.read(int(size))
        if len(raw) != int(size):
            return self.send(400, {"ok": False, "code": "incomplete_request"})
        try:
            result = self.server.engine.sync(raw, self.headers.get("x-pg-signature"))
            self.send(200, result)
        except PermissionError:
            self.send(401, {"ok": False, "code": "unauthorized"})
        except Invalid as error:
            self.send(400, {"ok": False, "code": str(error)})
        except Exception:
            self.send(503, {"ok": False, "code": "agent_update_failed"})

@contextlib.contextmanager
def claim_owner(directory="/run/proxy-guard-access"):
    directory=Path(directory)
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.is_symlink():raise Invalid("unsafe_owner_directory")
    os.chmod(directory,0o700)
    inode=os.stat("/proc/self/ns/net").st_ino
    fd=os.open(directory/f"owner-{inode}.lock",os.O_RDWR|os.O_CREAT|os.O_CLOEXEC|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(fd,0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Invalid("another_agent_running") from None
        yield fd
    finally:os.close(fd)

def run_configured(args, driver):
    config = json.loads(Path(args.config).read_text())
    configured_port=config.get("port",8788)
    if type(configured_port)is not int or not 1<=configured_port<=65535:
        raise Invalid("invalid_control_port")
    args.port=args.port if args.port is not None else configured_port
    edition = config.get("edition", "pro")
    if edition not in ("pro", "pro-max"):
        raise ValueError("invalid_edition")
    from monitor import service_config, bounded_int, EventStore
    from sensors import capture_config, Honeypot
    services=service_config(config.get("services", []))
    from maintenance import config as maintenance_config
    from reality_check import config as reality_config
    from egress import config as egress_config
    maintenance_config(config.get("maintenance"));reality_config(config.get("reality"));egress_config(config.get("egress"))
    from manage_units import names
    names(config.get("managed_units", []))
    analysis=capture_config(config.get("analysis", {}))
    if analysis["enabled"] and not __import__("shutil").which("tcpdump"):
        raise ValueError("tcpdump_required_for_capture")
    honey=Honeypot(config.get("analysis", {}).get("honeypot", {}),EventStore())
    for key,default,low,high in (("monitor_interval",5,2,60),("event_limit",512,64,4096),("event_retention",86400,60,2592000)):
        bounded_int(config.get(key),default,low,high)
    secret=config.get("agent_secret","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",secret) or secret.startswith("REPLACE_"):
        raise ValueError("configure_agent_secret")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",config.get("device_id","")):
        raise ValueError("invalid_device_id")
    path_token=config.get("path_token","")
    if path_token and(not isinstance(path_token,str)or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",path_token)or path_token.startswith("REPLACE_")):raise ValueError("invalid_path_token")
    direct=config.get("direct_token","")
    if direct and (not isinstance(direct,str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}",direct) or direct.startswith("REPLACE_")):
        raise ValueError("invalid_direct_token")
    bind=ipaddress.ip_address(config.get("bind","127.0.0.1"))
    if not bind.is_loopback and (not direct or not config.get("tls_cert") or not config.get("tls_key")):
        raise ValueError("external_bind_requires_https_and_direct_token")
    if edition=="pro" and (analysis["enabled"] or analysis["save_pcap"] or honey.enabled):
        raise ValueError("evidence_capture_requires_pro_max")
    if type(config.get("public_control",False)) is not bool:
        raise ValueError("invalid_public_control")
    if not bind.is_loopback and config.get("public_control") is not True:
        raise ValueError("public_control_confirmation_required")
    if honey.enabled and (honey.tcp==args.port or honey.udp==args.port or
        any(honey.tcp in service["tcp"] or honey.udp in service["udp"] for service in services)):
        raise ValueError("honeypot_must_use_separate_ports")
    if args.check_config or args.check_kernel:
        return {"ok": True, "edition": edition,"port":args.port}
    local_rules = []
    if config.get("bind", "127.0.0.1") not in ("127.0.0.1", "::1", "localhost"):
        if config.get("public_control") is not True:
            raise ValueError("public_control_confirmation_required")
        local_rules.append({"id":"_local_control", "name":"Authenticated HTTPS control", "enabled":True, "protocol":"tcp", "ports":[str(args.port)], "source_mode":"any", "sources":[]})
    engine = Engine(config.get("agent_secret"), config.get("device_id"), args.state, driver, local_rules=local_rules)
    if args.restore_policy:
        print(json.dumps({"ok":True,"policy_restored":True,"dynamic_permissions":0}))
        return
    from control import Server as ControlServer
    bind=config.get("bind", "127.0.0.1")
    server = ControlServer((bind, args.port), engine, config, edition)
    import signal
    def stop_server(*_):
        threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop_server)
    signal.signal(signal.SIGINT,stop_server)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--state", default="/var/lib/proxy-guard-access/state.json")
    parser.add_argument("--port", type=int)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--check-kernel", action="store_true")
    parser.add_argument("--restore-policy", action="store_true")
    parser.add_argument("--discover", action="store_true", help="Read local listeners without applying firewall rules")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    if args.discover:
        from discovery import Inventory
        print(json.dumps(Inventory().report(), sort_keys=True)); return
    if not args.check_config and os.geteuid() != 0:
        parser.error("CAP_NET_ADMIN/root required; use an isolated test VM for development")
    if not args.config and not args.cleanup:parser.error("--config is required unless using --discover or --cleanup")
    if args.check_config or args.check_kernel:
        result=run_configured(args, None)
        if args.check_kernel:
            rule={"id":"capability","name":"Kernel capability check","enabled":True,"protocol":"both","ports":["9"],"source_mode":"dynamic","sources":[]}
            from protection import render as capability_render
            policy=normalize_policy(True,[rule])
            probe=capability_render(policy,{},"pg_access_capability_"+str(os.getpid()))
            check=Nft().call(["-c","-f","-"],probe,check=False)
            if check.returncode:raise Invalid("kernel_resource_limits_unavailable_requires_nf_conncount_and_nft_connlimit")
        print(json.dumps(result))
        return result
    with claim_owner() as owner_fd:
        driver=Nft(owner_fd=owner_fd)
        if args.cleanup:
            driver.cleanup(); return
        initial=load_bootstrap_policy(args.state)
        from safety import boot_runtime
        initial["_runtime"]=boot_runtime(args.state,initial,persist=True)
        driver.bootstrap(initial)
        return run_configured(args, driver)

if __name__ == "__main__":
    try:
        main()
    except (ValueError,OSError) as error:
        code=str(error)
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,159}",code):code="configuration_or_runtime_unavailable"
        print(json.dumps({"ok":False,"code":code}),file=sys.stderr)
        sys.exit(2)
