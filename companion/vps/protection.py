"""Selected-port policy, bounded resource guards and kernel SSH rescue leases."""
from __future__ import annotations
import copy,ipaddress,math,time

MODES=("whitelist","standard","observe")
DEFAULT_LIMITS={"rate_enabled":True,"rate":40,"burst":80,"connections_enabled":True,
                "connections":128,"bandwidth_enabled":False,"bandwidth":1048576,
                "sustain":10,"cooldown":30,"window":60}
DEFAULT_SSH={"managed":False,"confirmed":False,"port":22,"rescue_enabled":True,
             "after":60,"scope":"public","open_seconds":0,"managers":[]}

def mode_for(policy,rule):
    selected=rule.get("mode","inherit")
    return policy.get("mode","standard")if selected=="inherit"else selected

def rule_effect(policy,rule):
    if not rule.get("enabled",True):return "disabled"
    mode=mode_for(policy,rule)
    return "bypass"if mode!="observe"and rule.get("source_mode")=="any"else mode

def mode_metadata(policy):
    return {"per_rule_modes":True,"rule_modes":{r["id"]:mode_for(policy,r)for r in policy["rules"]},
            "source_modes_v2":True,"rule_effects":{r["id"]:rule_effect(policy,r)for r in policy["rules"]}}

def integer(value,lo,hi,code):
    if type(value)is not int or not lo<=value<=hi:raise ValueError(code)
    return value

def normalize_limits(value):
    if value is None:value={}
    if not isinstance(value,dict):raise ValueError("invalid_limits")
    out=dict(DEFAULT_LIMITS)
    for key in ("rate_enabled","connections_enabled","bandwidth_enabled"):
        if key in value:
            if type(value[key])is not bool:raise ValueError("invalid_limits")
            out[key]=value[key]
    for key,lo,hi in (("rate",1,10000),("burst",1,20000),("connections",1,10000),
                      ("bandwidth",1024,1073741824),("sustain",1,300),("cooldown",1,3600),("window",5,600)):
        out[key]=integer(value.get(key,out[key]),lo,hi,"invalid_limits")
    if out["burst"]<out["rate"]:raise ValueError("burst_below_rate")
    return out

def normalize_ssh(value):
    if value is None:value={}
    if not isinstance(value,dict):raise ValueError("invalid_ssh_policy")
    out=copy.deepcopy(DEFAULT_SSH)
    for key in ("managed","confirmed","rescue_enabled"):
        if key in value:
            if type(value[key])is not bool:raise ValueError("invalid_ssh_policy")
            out[key]=value[key]
    for key,lo,hi in (("port",1,65535),("after",10,3600),("open_seconds",0,3600)):
        out[key]=integer(value.get(key,out[key]),lo,hi,"invalid_ssh_policy")
    if 0<out["open_seconds"]<30:raise ValueError("invalid_ssh_policy")
    out["scope"]=value.get("scope","public")
    if out["scope"]not in ("public","restricted"):raise ValueError("invalid_ssh_policy")
    managers=value.get("managers",[])
    if not isinstance(managers,list)or len(managers)>32:raise ValueError("invalid_management_sources")
    out["managers"]=[]
    for entry in managers:
        try:net=ipaddress.ip_network(entry,strict=False)
        except (ValueError,TypeError):raise ValueError("invalid_management_sources")from None
        if net.prefixlen==0 or net.is_multicast:raise ValueError("invalid_management_sources")
        out["managers"].append(str(net))
    out["managers"]=sorted(set(out["managers"]))
    return out

def timeout_element(value,deadline,now):
    return f"{value} timeout {max(1,math.ceil(deadline-now))}s" if deadline>now else None

def runtime_elements(policy,leases,now):
    runtime=policy.get("_runtime",{});ssh=policy.get("ssh",DEFAULT_SSH)
    result={"dynamic4":[],"dynamic6":[],"ssh_managed":[],"ssh_hold":[],"ssh_public":[],"ssh_last4":[],"ssh_last6":[]}
    for family in (4,6):
        lease=leases.get(family)if family in policy.get("address_families",[4,6])else None
        if lease and lease[1]>now:result[f"dynamic{family}"]=[timeout_element(str(ipaddress.ip_address(lease[0])),lease[1],now)]
        for value in runtime.get("last_home",[]):
            address=ipaddress.ip_address(value)
            if address.version==family:result[f"ssh_last{family}"].append(str(address))
    if policy.get("enabled")and ssh["managed"]and runtime.get("ssh_armed"):
        result["ssh_managed"]=[str(ssh["port"])]
        if not ssh["rescue_enabled"]:result["ssh_hold"]=[str(ssh["port"])]
        else:
            for key,name in (("ssh_hold_until","ssh_hold"),("ssh_public_until","ssh_public")):
                item=timeout_element(ssh["port"],runtime.get(key,0),now)
                if item:result[name]=[item]
            # A permanent public element remains behind the kernel-timed hold
            # gate. It becomes reachable after dual-heartbeat expiry even if
            # the Agent stops, and has no hidden timeout in unlimited mode.
            if ssh["scope"]=="public" and ssh["open_seconds"]==0:
                result["ssh_public"]=[str(ssh["port"])]
    for index,rule in enumerate(policy["rules"]):
        for family in (4,6):
            for proto in (("tcp","udp")if rule["protocol"]=="both"else(rule["protocol"],)):
                trusted=f"trusted{family}_{index}_{proto}";result[trusted]=[]
                for row in runtime.get("trusted",{}).get(rule["id"],[]):
                    address=ipaddress.ip_address(row["source"])
                    if row['protocol']==proto and address.version==family and row['until']>now:
                        result[trusted].append(timeout_element(f"{address} . {row['port']}",row['until'],now))
                name=f"fallback{family}_{index}_{proto}";result[name]=[]
                if mode_for(policy,rule)=="standard"and rule.get("limits",DEFAULT_LIMITS)["bandwidth_enabled"]:
                    for row in runtime.get("fallback_restricted",{}).get(rule["id"],[]):
                        address=ipaddress.ip_address(row["source"])
                        if row["protocol"]==proto and address.version==family and row["until"]>now:
                            result[name].append(timeout_element(f"{address} . {row['sport']} . {row['port']}",row["until"],now))
    return result

def runtime_updates(policy,leases,table,now=None):
    now=time.monotonic()if now is None else now
    lines=[]
    for name,elements in runtime_elements(policy,leases,now).items():
        lines.append(f"flush set inet {table} {name}")
        if elements:lines.append(f"add element inet {table} {name} {{ "+", ".join(elements)+" }")
    return "\n".join(lines)+"\n"

def render(policy,leases,table,mono=None):
    now=time.monotonic()if mono is None else mono
    ssh=policy.get("ssh",DEFAULT_SSH)
    tracking=max(32,min(512,4096//max(1,len(policy["rules"])*4)))
    current=runtime_elements(policy,leases,now)
    lines=[f"table inet {table} {{"]
    def named(name,kind,flags="",extra="",elements=None):
        text=f" set {name} {{ type {kind};"
        if flags:text+=" flags "+flags+";"
        if extra:text+=" "+extra
        values=current.get(name,[])if elements is None else elements
        if values:text+=" elements = { "+", ".join(values)+" };"
        lines.append(text+" }")
    for family in (4,6):
        named(f"dynamic{family}",f"ipv{family}_addr","timeout")
        named(f"ssh_last{family}",f"ipv{family}_addr")
        nets=[s for s in ssh["managers"]if ipaddress.ip_network(s).version==family]
        named(f"ssh_static{family}",f"ipv{family}_addr","interval","auto-merge;",nets)
    named("ssh_managed","inet_service")
    named("ssh_hold","inet_service","timeout")
    named("ssh_public","inet_service","timeout")
    for index,rule in enumerate(policy["rules"]):
        limit=rule.get("limits",DEFAULT_LIMITS)
        for family in (4,6):
            nets=[s for s in rule["sources"]if ipaddress.ip_network(s).version==family]
            named(f"static{family}_{index}",f"ipv{family}_addr","interval","auto-merge;",nets)
            for proto in (("tcp","udp")if rule["protocol"]=="both"else(rule["protocol"],)):
                named(f"trusted{family}_{index}_{proto}",f"ipv{family}_addr . inet_service","timeout")
                named(f"cool{family}_{index}_{proto}",f"ipv{family}_addr . inet_service","dynamic,timeout",f"timeout {limit['cooldown']}s; size {tracking};")
                named(f"seen{family}_{index}_{proto}",f"ipv{family}_addr . inet_service","dynamic,timeout",f"timeout {limit['window']}s; size {tracking}; counter;")
                named(f"newflow{family}_{index}_{proto}",f"ipv{family}_addr . inet_service","dynamic,timeout",f"timeout {limit['window']}s; size {tracking}; counter;")
                named(f"capacity{family}_{index}_{proto}",f"ipv{family}_addr . inet_service","dynamic,timeout",f"timeout {limit['window']}s; size {tracking};")
                named(f"fallback{family}_{index}_{proto}",f"ipv{family}_addr . inet_service . inet_service","timeout")
    lines += [" chain input {","  type filter hook input priority -150; policy accept;",'  iifname "lo" return']
    if policy["enabled"]:
        lines.append('  ct direction reply ct state established return')
        # The managed-port set stays empty until both heartbeats and a checked
        # management session qualify. Kernel TTLs work even if this process dies.
        if ssh["managed"]:
            lines.append('  tcp dport @ssh_managed ct state established return')
            for family in (4,6):
                ip="ip"if family==4 else"ip6"
                base=f"  meta nfproto ipv{family} tcp dport @ssh_managed"
                lines += [base+f" {ip} saddr @ssh_static{family} return",base+f" {ip} saddr @dynamic{family} return"]
            lines.append('  tcp dport @ssh_hold counter drop')
            for family in (4,6):
                ip="ip"if family==4 else"ip6"
                lines.append(f"  meta nfproto ipv{family} tcp dport @ssh_managed {ip} saddr @ssh_last{family} return")
            if ssh["scope"]=="public":lines.append('  tcp dport @ssh_public return')
            lines.append('  tcp dport @ssh_managed counter drop')
        for index,rule in enumerate(policy["rules"]):
            if not rule["enabled"]:continue
            mode=mode_for(policy,rule)
            limit=rule.get("limits",DEFAULT_LIMITS)
            ports="{ "+", ".join(rule["ports"])+" }"
            for proto in (("tcp","udp")if rule["protocol"]=="both"else(rule["protocol"],)):
                for family in (4,6):
                    ip="ip"if family==4 else"ip6";suffix=f"{family}_{index}_{proto}"
                    base=f"  meta nfproto ipv{family} {proto} dport {ports}"
                    new=base+' ct state new ct status != confirmed'
                    lines += [base+f" update @seen{suffix} {{ {ip} saddr . {proto} dport }}",new+f" update @newflow{suffix} {{ {ip} saddr . {proto} dport }}"]
                    if mode=="observe":
                        if limit["connections_enabled"]:
                            lines.append(new+f" meter watchconns{suffix} size {tracking} {{ {ip} saddr . {proto} dport ct count over {limit['connections']} }} add @capacity{suffix} {{ {ip} saddr . {proto} dport timeout {limit['window']}s }}")
                        continue
                    if rule["source_mode"]=="any":continue
                    if rule["source_mode"]in("static","mixed")and any(ipaddress.ip_network(s).version==family for s in rule["sources"]):
                        lines.append(base+f" {ip} saddr @static{family}_{index} return")
                    if rule["source_mode"]in("dynamic","mixed"):
                        lines.append(base+f" {ip} saddr @dynamic{family} return")
                    if mode=="whitelist":
                        lines.append(base+' counter drop');continue
                    lines.append(base+f" {ip} saddr . {proto} dport @trusted{family}_{index}_{proto} return")
                    if limit["bandwidth_enabled"]:
                        lines.append(base+f" {ip} saddr . {proto} sport . {proto} dport @fallback{suffix} meter bwin{suffix} size {tracking} {{ {ip} saddr . {proto} dport timeout {limit['window']}s limit rate over {limit['bandwidth']} bytes/second burst {limit['bandwidth']} bytes }} counter drop")
                    lines += [base+' ct state established return',base+' ct state invalid counter drop',new+f" {ip} saddr . {proto} dport @cool{suffix} counter drop"]
                    if limit["rate_enabled"]:
                        lines.append(new+f" meter rate{suffix} size {tracking} {{ {ip} saddr . {proto} dport timeout {limit['window']}s limit rate over {limit['rate']}/second burst {limit['burst']} packets }} add @cool{suffix} {{ {ip} saddr . {proto} dport timeout {limit['cooldown']}s }} counter drop")
                    if limit["connections_enabled"]:
                        lines.append(new+f" meter conns{suffix} size {tracking} {{ {ip} saddr . {proto} dport ct count over {limit['connections']} }} add @cool{suffix} {{ {ip} saddr . {proto} dport timeout {limit['cooldown']}s }} counter drop")
    if policy["enabled"]and any(r["enabled"]and mode_for(policy,r)=="standard"for r in policy["rules"]):
        lines += [" }"," chain output {","  type filter hook output priority -150; policy accept;","  ct direction original return"]
        for index,rule in enumerate(policy["rules"]):
            limit=rule.get("limits",DEFAULT_LIMITS)
            if not rule["enabled"]or mode_for(policy,rule)!="standard"or rule["source_mode"]=="any"or not limit["bandwidth_enabled"]:continue
            ports="{ "+", ".join(rule["ports"])+" }"
            for proto in (("tcp","udp")if rule["protocol"]=="both"else(rule["protocol"],)):
                for family in(4,6):
                    ip="ip"if family==4 else"ip6";suffix=f"{family}_{index}_{proto}"
                    base=f"  meta nfproto ipv{family} {proto} sport {ports}"
                    lines.append(base+f" {ip} daddr . {proto} dport . {proto} sport @fallback{suffix} meter bwout{suffix} size {tracking} {{ {ip} daddr . {proto} sport timeout {limit['window']}s limit rate over {limit['bandwidth']} bytes/second burst {limit['bandwidth']} bytes }} counter drop")
    lines += [" }","}",""]
    return "\n".join(lines)
