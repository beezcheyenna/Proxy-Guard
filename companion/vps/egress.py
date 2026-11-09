"""Advisory IPv4 candidates. No policy, lease, heartbeat or transaction mutations.

Optional measurement uses one fixed HTTPS source-IP reflector. It is disabled by
 default, runs outside request handlers, and never verifies a proxy business path.
"""
from __future__ import annotations
import copy, http.client, ipaddress, json, os, re, socket, ssl, stat
import subprocess, sys, threading, time
from pathlib import Path

MAX_CANDIDATES = 8
MAX_LOCAL_BYTES = 65536
MAX_MEASURE_BYTES = 256
MEASURE_HOST = "api.ipify.org"
MEASURE_PATH = "/"
SOURCES = {"interface": "host_interface", "panel": "panel_config", "measured": "host_default_ipv4"}
WARNINGS = frozenset({"non_public_ipv4_omitted", "no_public_ipv4_candidate", "interface_unavailable",
    "panel_unavailable", "panel_hint_unverified", "panel_hint_ignored", "measurement_disabled",
    "measurement_pending", "measurement_failed", "measurement_stale", "measurement_disagreement",
    "multiple_public_ipv4_candidates", "host_default_not_business_egress", "candidates_truncated"})
EXCLUDED = tuple(ipaddress.IPv4Network(v) for v in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4"))


def public_ipv4(value):
    if not isinstance(value, str) or len(value) > 15 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", value):
        return None
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return None
    if str(address) != value or any(address in network for network in EXCLUDED):
        return None
    return str(address)


def config(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {"panel_config_path", "measure_enabled", "measure_interval"}:
        raise ValueError("invalid_egress_config")
    result = {"panel_config_path": value.get("panel_config_path", ""),
              "measure_enabled": value.get("measure_enabled", False),
              "measure_interval": value.get("measure_interval", 300)}
    path = result["panel_config_path"]
    if not isinstance(path, str) or len(path) > 512 or (path and (
        not path.startswith("/") or any(ord(c) < 32 for c in path) or
        path.startswith(("/proc/", "/sys/", "/dev/")) or ".." in Path(path).parts)):
        raise ValueError("invalid_egress_config")
    if type(result["measure_enabled"]) is not bool or type(result["measure_interval"]) is not int or not 60 <= result["measure_interval"] <= 3600:
        raise ValueError("invalid_egress_config")
    return result


def interface_addresses():
    # The command and its arguments are fixed. Neither caller input nor shell is used.
    p = subprocess.run(["ip", "-j", "-4", "address", "show"], stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=2, check=True)
    if len(p.stdout) > MAX_LOCAL_BYTES:
        raise ValueError("interface_inventory_too_large")
    rows = json.loads(p.stdout)
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("invalid_interface_inventory")
    addresses = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("addr_info", []), list):
            raise ValueError("invalid_interface_inventory")
        for item in row.get("addr_info", [])[:256]:
            if isinstance(item, dict) and item.get("family") == "inet":
                addresses.append(item.get("local"))
    return addresses


def panel_addresses(path):
    if not path:
        return []
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o022:
            raise ValueError("unsafe_panel_config")
        raw = f.read(MAX_LOCAL_BYTES + 1)
    if len(raw) > MAX_LOCAL_BYTES:
        raise ValueError("panel_config_too_large")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid_panel_config")
    addresses = []
    # Only explicit bind hints in 3x-ui's generated Xray JSON. No recursive
    # string/IP scan, DNS lookup, REALITY target, routing destination or credential.
    for group, field in (("inbounds", "listen"), ("outbounds", "sendThrough")):
        rows = data.get(group, [])
        if not isinstance(rows, list) or len(rows) > 256:
            raise ValueError("invalid_panel_config")
        addresses.extend(row[field] for row in rows if isinstance(row, dict) and row.get(field) not in (None, ""))
    return addresses


def _measure_fixed_target():
    # This function only runs in a bounded child. Pin a validated public A record
    # to the TLS socket while preserving the fixed hostname for SNI/verification.
    choices = sorted({row[4][0] for row in socket.getaddrinfo(
        MEASURE_HOST, 443, socket.AF_INET, socket.SOCK_STREAM) if public_ipv4(row[4][0])})
    if not choices:
        raise ValueError("measurement_peer_unavailable")
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(MEASURE_HOST, 443, timeout=2, context=context)
    def connect():
        raw = socket.create_connection((choices[0], 443), timeout=2)
        try:
            connection.sock = context.wrap_socket(raw, server_hostname=MEASURE_HOST)
        except BaseException:
            raw.close()
            raise
    connection.connect = connect
    try:
        connection.request("GET", MEASURE_PATH, headers={"Accept": "text/plain", "User-Agent": "ProxyGuard-egress-info/1"})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("measurement_http_failed")  # No redirects or retries.
        size = response.getheader("Content-Length")
        if size is not None and (not size.isdigit() or int(size) > MAX_MEASURE_BYTES):
            raise ValueError("measurement_response_too_large")
        body = response.read(MAX_MEASURE_BYTES + 1)
        if len(body) > MAX_MEASURE_BYTES:
            raise ValueError("measurement_response_too_large")
        ip = public_ipv4(body.decode("ascii").strip())
        if not ip:
            raise ValueError("measurement_invalid_ipv4")
        return [ip]
    finally:
        connection.close()


class EgressInfo:
    def __init__(self, settings=None, *, interfaces=interface_addresses, panel=panel_addresses,
                 measurement=None, monotonic=time.monotonic, wall=time.time):
        self.config = config(settings)
        self.interfaces, self.panel, self.measurement = interfaces, panel, measurement
        self.monotonic, self.wall = monotonic, wall
        self.lock = threading.Lock()
        self.local_lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.child = None
        self.local_at = None
        self.local_rows, self.local_warnings = [], set()
        self.measured = None
        self.measure_failed = False
        self.measure_attempted = False

    def start(self):
        if self.config["measure_enabled"] and self.thread is None:
            self.thread = threading.Thread(target=self._loop, name="pg-egress-info", daemon=True)
            self.thread.start()

    def _run_measurement(self):
        if self.measurement is not None:
            return self.measurement()  # In-process trusted test dependency only.
        child = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), "--measure"],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with self.lock:
            self.child = child
            if self.stop.is_set():
                child.kill()
        try:
            out, _ = child.communicate(timeout=5)
            if child.returncode or len(out) > 256:
                raise ValueError("measurement_failed")
            return json.loads(out)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate()
            with self.lock:
                if self.child is child:
                    self.child = None

    def sample_measurement(self):
        if not self.config["measure_enabled"] or self.stop.is_set():
            return
        try:
            result = self._run_measurement()
            if not isinstance(result, list) or not 1 <= len(result) <= 2:
                raise ValueError("invalid_measurement")
            addresses = sorted({public_ipv4(ip) for ip in result} - {None})
            if not addresses or len(addresses) != len(set(result)):
                raise ValueError("invalid_measurement")
            with self.lock:
                self.measured = {"ips": addresses, "checked_at": int(self.wall()), "at": self.monotonic()}
                self.measure_failed = False
                self.measure_attempted = True
        except Exception:
            with self.lock:
                self.measure_failed = True
                self.measure_attempted = True

    def _loop(self):
        while not self.stop.is_set():
            self.sample_measurement()
            if self.stop.wait(self.config["measure_interval"]):
                break

    def _locals(self):
        with self.local_lock:
            now = self.monotonic()
            if self.local_at is not None and now - self.local_at < 15:
                return copy.deepcopy(self.local_rows), set(self.local_warnings)
            checked, rows, warnings = int(self.wall()), [], set()
            for source, read in (("interface", self.interfaces),
                                 ("panel", lambda: self.panel(self.config["panel_config_path"]))):
                try:
                    values = read()
                    if not isinstance(values, list) or len(values) > 512:
                        raise ValueError("candidate_inventory_too_large")
                    for value in values:
                        ip = public_ipv4(value)
                        if ip:
                            rows.append((ip, source, checked))
                        elif value not in (None, ""):
                            warnings.add("non_public_ipv4_omitted")
                            if source == "panel":
                                warnings.add("panel_hint_ignored")
                except Exception:
                    warnings.add(source + "_unavailable")
            if any(source == "panel" for _, source, _ in rows):
                warnings.add("panel_hint_unverified")
            self.local_at, self.local_rows, self.local_warnings = now, rows, warnings
            return copy.deepcopy(rows), set(warnings)

    def report(self):
        # Never holds an Engine lock or invokes any policy/activity/confirmation.
        rows, warnings = self._locals()
        with self.lock:
            measured, failed, attempted = copy.deepcopy(self.measured), self.measure_failed, self.measure_attempted
        now = self.monotonic()
        if not self.config["measure_enabled"]:
            state, stale = "disabled", True
            warnings.add("measurement_disabled")
        elif measured is None:
            state, stale = ("unavailable" if attempted else "pending"), True
            warnings.add("measurement_failed" if attempted else "measurement_pending")
        else:
            stale = failed or now - measured["at"] > 2 * self.config["measure_interval"]
            state = "stale" if stale else "conflict" if len(measured["ips"]) > 1 else "fresh"
            if stale:
                warnings.add("measurement_stale")
            if failed:
                warnings.add("measurement_failed")
            if len(measured["ips"]) > 1:
                warnings.add("measurement_disagreement")
            rows.extend((ip, "measured", measured["checked_at"]) for ip in measured["ips"])
            warnings.add("host_default_not_business_egress")
        by_ip = {}
        for ip, source, checked in rows:
            evidence = by_ip.setdefault(ip, {})
            evidence[source] = {"source": source, "checked_at": checked, "scope": SOURCES[source]}
        ambiguous = len(by_ip) > 1
        if ambiguous:
            warnings.add("multiple_public_ipv4_candidates")
        if len(by_ip) > MAX_CANDIDATES:
            warnings.add("candidates_truncated")
        candidates = [{"ipv4": ip, "evidence": list(evidence.values())}
                      for ip, evidence in sorted(by_ip.items(), key=lambda row: ("measured" not in row[1], int(ipaddress.IPv4Address(row[0]))))[:MAX_CANDIDATES]]
        if not candidates:
            warnings.add("no_public_ipv4_candidate")
        status = "unavailable" if not candidates else "partial" if ambiguous or (self.config["measure_enabled"] and stale) or warnings.intersection({"interface_unavailable", "panel_unavailable", "candidates_truncated"}) else "available"
        return {"ok": True, "protocol": 3, "egress_info_schema": 1, "generated_at": int(self.wall()),
                "status": status, "candidates": candidates, "ambiguous": ambiguous,
                "business_egress_verified": False, "warnings": sorted(warnings),
                "measurement": {"state": state, "checked_at": measured["checked_at"] if measured else None, "stale": stale}}

    def close(self):
        self.stop.set()
        with self.lock:
            if self.child is not None and self.child.poll() is None:
                self.child.kill()
        if self.thread is not None:
            self.thread.join(timeout=2)


if __name__ == "__main__":
    if sys.argv[1:] != ["--measure"]:
        raise SystemExit(2)
    try:
        print(json.dumps(_measure_fixed_target(), separators=(",", ":")))
    except Exception:
        raise SystemExit(1)
