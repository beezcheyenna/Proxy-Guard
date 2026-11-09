"""Read-only, bounded inventory of non-loopback TCP listeners and UDP sockets."""
from __future__ import annotations
import ipaddress, os, sys, time
from itertools import islice
from pathlib import Path

class Inventory:
    def __init__(self, proc="/proc", limit=256, interval=15, clock=time.monotonic):
        self.proc, self.limit, self.interval, self.clock = Path(proc), limit, interval, clock
        self.checked, self.rows, self.truncated, self.error = None, [], False, None

    @staticmethod
    def address(value, version):
        raw = bytes.fromhex(value)
        if version == 4:
            raw = raw[::-1] if sys.byteorder == "little" else raw
        elif sys.byteorder == "little":
            raw = b"".join(raw[i:i+4][::-1] for i in range(0, 16, 4))
        return ipaddress.ip_address(raw)

    def refresh(self, force=False):
        now = self.clock()
        if not force and self.checked is not None and now-self.checked < self.interval:
            return self.rows
        rows, truncated, readable = [], False, False
        for proto in ("tcp", "udp"):
            for version in (4, 6):
                path = self.proc / "net" / (proto + ("6" if version == 6 else ""))
                try:
                    with path.open() as stream:
                        text = stream.read(2097153)
                    readable = True
                except FileNotFoundError:
                    continue
                except OSError:
                    truncated = True
                    continue
                if len(text) > 2097152:
                    truncated = True
                for line in text[:2097152].splitlines()[1:8193]:
                    try:
                        fields = line.split()
                        local, remote = fields[1], fields[2]
                        if proto == "tcp" and fields[3] != "0A":
                            continue
                        if proto == "udp" and int(remote.replace(":", ""), 16) != 0:
                            continue  # Connected outgoing UDP is not a listener.
                        bind, port = local.split(":")
                        address, port = self.address(bind, version), int(port, 16)
                        if address.is_loopback or not 1 <= port <= 65535:
                            continue
                        rows.append({"protocol": proto, "family": version, "bind": str(address),
                                     "port": port, "inode": fields[9], "processes": []})
                    except (ValueError, IndexError):
                        continue
        if len(rows) > self.limit:
            truncated = True
        rows = sorted(rows, key=lambda x: (x["protocol"], x["port"], x["family"], x["bind"]))[:self.limit]
        by_inode = {}
        for row in rows:
            by_inode.setdefault(row["inode"], []).append(row)
        # A bounded best-effort owner lookup; never collect command-line arguments.
        budget = 20000
        try:
            processes = list(islice((p for p in self.proc.iterdir() if p.name.isdigit()),2048))
        except OSError:
            processes = []
        for process in processes:
            if budget <= 0:
                break
            try:
                name = Path(os.readlink(process / "exe")).name[:64]
                descriptors = list(islice((process / "fd").iterdir(),512))
            except OSError:
                continue
            for fd in descriptors:
                budget -= 1
                if budget < 0:
                    break
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                inode = target[8:-1] if target.startswith("socket:[") else None
                for row in by_inode.get(inode, []):
                    owner = {"pid": int(process.name), "name": name}
                    if owner not in row["processes"] and len(row["processes"]) < 4:
                        row["processes"].append(owner)
        for row in rows:
            row.pop("inode", None)
        self.checked, self.rows, self.truncated = now, rows, truncated
        self.error = None if readable else "listener_inventory_unavailable"
        return rows

    def report(self):
        self.refresh()
        return {"listeners": self.rows[:48], "count": len(self.rows),
                "truncated": self.truncated or len(self.rows) > 48,
                "error": self.error, "scope": "host_network_namespace", "public_reachability_verified": False}


def effective_policy(policy, listeners, local_rules=()):
    """Inventory is advisory. Only explicit service rules can restrict a port."""
    import copy
    result = copy.deepcopy(policy)
    result["default_deny"] = False
    result["auto_discover"] = False
    result["rules"] = list(copy.deepcopy(local_rules)) + result["rules"]
    return result
