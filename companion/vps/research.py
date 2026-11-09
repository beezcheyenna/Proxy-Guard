"""Bounded passive metadata and TCP-prefix analysis; never identifies an actor."""
from __future__ import annotations
from collections import Counter, OrderedDict
import hashlib, ipaddress, json, math, struct, time

MAX_PREFIX=256

def packet(frame, linktype=1):
    """Decode Ethernet, Linux SLL/SLL2 or raw IP. Fragments/truncation stay explicit."""
    if linktype==1:
        if len(frame)<14: return None
        offset=14; et=int.from_bytes(frame[12:14],"big")
        for _ in range(2):
            if et not in (0x8100,0x88a8): break
            if len(frame)<offset+4: return None
            et=int.from_bytes(frame[offset+2:offset+4],"big");offset+=4
    elif linktype==113:
        if len(frame)<16:return None
        offset=16;et=int.from_bytes(frame[14:16],"big")
    elif linktype==276:
        if len(frame)<20:return None
        offset=20;et=int.from_bytes(frame[:2],"big")
    elif linktype in (101,228,229):
        if not frame:return None
        offset=0;et=0x800 if frame[0]>>4==4 else 0x86dd
    else: return None
    ip=frame[offset:]
    if et==0x800:
        if len(ip)<20 or ip[0]>>4!=4:return None
        h=(ip[0]&15)*4;length=int.from_bytes(ip[2:4],"big")
        if h<20 or len(ip)<h or length<h:return None
        frag=int.from_bytes(ip[6:8],"big")
        if frag&0x3fff:return {"skipped":"fragment"}
        proto=ip[9];src=str(ipaddress.ip_address(ip[12:16]));dst=str(ipaddress.ip_address(ip[16:20]))
        data=ip[h:min(length,len(ip))];truncated=len(ip)<length
    elif et==0x86dd:
        if len(ip)<40 or ip[0]>>4!=6:return None
        end=40+int.from_bytes(ip[4:6],"big");proto=ip[6];pos=40
        for _ in range(8):
            if proto==44:return {"skipped":"fragment"}
            if proto not in (0,43,60,51):break
            if len(ip)<pos+2:return None
            size=(ip[pos+1]+2)*4 if proto==51 else (ip[pos+1]+1)*8
            next_proto=ip[pos];pos+=size;proto=next_proto
            if pos>len(ip) or pos>end:return None
        src=str(ipaddress.ip_address(ip[8:24]));dst=str(ipaddress.ip_address(ip[24:40]))
        data=ip[pos:min(end,len(ip))];truncated=len(ip)<end
    else:return None
    if proto==6:
        if len(data)<20:return None
        h=(data[12]>>4)*4
        if h<20 or h>len(data):return None
        return {"protocol":"tcp","src":src,"dst":dst,"sport":int.from_bytes(data[:2],"big"),
                "dport":int.from_bytes(data[2:4],"big"),"seq":int.from_bytes(data[4:8],"big"),
                "flags":data[13],"payload":data[h:],"truncated":truncated}
    if proto==17:
        if len(data)<8:return None
        length=int.from_bytes(data[4:6],"big")
        if length<8:return None
        return {"protocol":"udp","src":src,"dst":dst,"sport":int.from_bytes(data[:2],"big"),
                "dport":int.from_bytes(data[2:4],"big"),"payload":data[8:min(length,len(data))],
                "truncated":truncated or len(data)<length}
    return None

class Prefix:
    def __init__(self, seq=None):
        self.base=seq
        self.bytes={}
        self.conflict=False
        self.partial=seq is None
        self.digest=None

    def feed(self, seq, payload):
        if self.base is None:self.base=seq
        for index,value in enumerate(payload[:MAX_PREFIX*2]):
            offset=((seq+index)-self.base)&0xffffffff
            if offset>=MAX_PREFIX: continue
            if offset in self.bytes and self.bytes[offset]!=value:self.conflict=True
            self.bytes[offset]=value
        if self.conflict or len(self.bytes)<MAX_PREFIX:return None
        if any(i not in self.bytes for i in range(MAX_PREFIX)):return None
        digest=hashlib.sha256(bytes(self.bytes[i] for i in range(MAX_PREFIX))).hexdigest()
        if digest==self.digest:return None
        self.digest=digest
        return digest

class Analyzer:
    def __init__(self, events, max_flows=512, window=300, salt=None, probe_detection=False):
        if type(max_flows)is not int or not 16<=max_flows<=4096:raise ValueError("invalid_flow_limit")
        if type(window)is not int or not 10<=window<=86400:raise ValueError("invalid_analysis_window")
        self.events,self.max_flows,self.window=events,max_flows,window
        self.salt=salt or __import__("secrets").token_bytes(32)
        self.flows,self.digests=OrderedDict(),OrderedDict()
        self.counts=Counter()
        self.lengths=Counter()
        self.first_seen=time.time()
        from probes import ProbeDetector
        self.probes=ProbeDetector(events,max_flows,window,self.salt) if probe_detection else None

    def tag(self,value):
        return __import__("hmac").new(self.salt,value.encode(),hashlib.sha256).hexdigest()[:16]

    def feed(self, item, timestamp=None):
        now=time.monotonic() if timestamp is None else timestamp
        if not item:return
        if "skipped"in item:self.counts["skipped_"+item["skipped"]]+=1;return
        self.counts[item["protocol"]+"_packets"]+=1
        payload=item["payload"];self.counts["payload_bytes"]+=len(payload)
        self.lengths[str(min(8,len(payload)//128)*128)]+=1
        if item.get("truncated"):self.counts["truncated_packets"]+=1;return
        key=(item["protocol"],item["src"],item["sport"],item["dst"],item["dport"])
        connection=(item["protocol"],tuple(sorted(((item["src"],item["sport"]),(item["dst"],item["dport"])))))
        while self.flows and (key not in self.flows and len(self.flows)>=self.max_flows or next(iter(self.flows.values()))["last"]<now-self.window):
            self.flows.popitem(last=False)
        while self.digests and next(iter(self.digests.values()))["time"]<now-self.window:
            self.digests.popitem(last=False)
        if item["protocol"]=="udp":
            # Repeated DNS and other normal UDP payloads are not classified as replay.
            if len(payload)>=MAX_PREFIX:self.counts["udp_large_datagrams"]+=1
            return
        syn=bool(item["flags"]&2)
        if syn and not item["flags"]&16:
            self.counts["tcp_starts"]+=1
            if self.probes:self.probes.syn(item["src"],(item["dst"],item["dport"]),now)
            self.flows.pop(key,None)
        if key not in self.flows:
            self.flows[key]={"last":now,"prefix":Prefix((item["seq"]+1)&0xffffffff if syn else None),"first_observed":False}
            self.counts["tcp_directions"]+=1
        flow=self.flows[key];flow["last"]=now;self.flows.move_to_end(key)
        if item["flags"]&5:self.counts["tcp_closes"]+=1
        if not payload:return
        prefix=flow["prefix"]
        if self.probes and not flow["first_observed"] and not prefix.partial and item["seq"]==prefix.base:
            flow["first_observed"]=True
            self.probes.observe(payload,item["src"],connection,(item["dst"],item["dport"]),now)
        digest=prefix.feed((item["seq"]+1)&0xffffffff if syn else item["seq"],payload)
        if not digest:return
        if prefix.partial:
            self.counts["partial_streams"]+=1
            return
        existing=self.digests.get(digest)
        from probes import passive_features
        common=bool(passive_features(bytes(prefix.bytes[i] for i in range(MAX_PREFIX)))["common_prefix"]) if self.probes else False
        if existing and existing["connection"]!=connection and not common:
            self.counts["repeated_prefixes"]+=1
            self.events.add("repeated_tcp_prefix","warning",confidence="low",digest=digest,
                            prefix_bytes=MAX_PREFIX,interval_seconds=round(now-existing["time"],3),
                            source_tag=self.tag(item["src"]),flow_tag=self.tag(str(key)),
                            attribution="unknown",basis="cross_connection_equal_tcp_prefix")
        self.digests[digest]={"flow":key,"connection":connection,"time":now}
        self.digests.move_to_end(digest)
        while len(self.digests)>self.max_flows:self.digests.popitem(last=False)

    def expire(self,now=None):
        now=time.monotonic() if now is None else now
        while self.flows and next(iter(self.flows.values()))["last"]<now-self.window:self.flows.popitem(last=False)
        while self.digests and next(iter(self.digests.values()))["time"]<now-self.window:self.digests.popitem(last=False)
        if self.probes:self.probes._expire(now)

    def summary(self):
        return {"enabled":True,"counts":dict(self.counts),"length_buckets":dict(self.lengths),
                "active_directions":len(self.flows),"prefix_bytes":MAX_PREFIX,
                "window_seconds":self.window,"max_flows":self.max_flows,
                "started_at":self.first_seen,"attribution":"unknown",
                "probe_detection":self.probes.summary() if self.probes else {"enabled":False},
                "limitations":["prefix_only","capture_gaps_not_reassembled","not_protocol_authentication",
                               "not_gfw_attribution","tcp_tuple_reuse_may_be_ambiguous","no_live_cross_node_correlation"]}
