"""Historical probe-pattern observations, not sender/GFW attribution.

References: gfw-report IMC 2020 R1-R5/NR1/NR2 and USENIX Security
2023 active-probe lengths. Passive traffic-risk features are diagnostic only.
"""
from __future__ import annotations
from collections import Counter, OrderedDict, deque
import hashlib, hmac, secrets

MASKS = {"R2": (0,), "R3": (*range(8),62,63), "R4": (16,), "R5": (6,16)}
CHANGED_BYTES = sorted(set().union(*map(set, MASKS.values())))
NR20 = {221} | {n+d for n in (8,12,16,22,33,41,49) for d in (-1,0,1)}
NR23 = {n+d for n in (16,64,256) for d in (-1,0,1)}


def passive_features(payload):
    """Describe the *historical passive classifier*, not an active-probe identity."""
    if not payload:
        return {"classified": False}
    printable = [32 <= value <= 126 for value in payload]
    leading = 0
    for value in printable:
        if not value: break
        leading += 1
    run = longest = 0
    for value in printable:
        run = run+1 if value else 0
        longest = max(longest,run)
    bits = sum(value.bit_count() for value in payload)/len(payload)
    fraction = sum(printable)/len(payload)
    protocol = ""
    # Use the paper's 00-09 version range; its artifact uses a broader 00-0f.
    if len(payload)>=3 and payload[0] in (22,23) and payload[1]==3 and payload[2]<=9:
        protocol="tls_prefix"
    elif payload.startswith((b"GET ",b"PUT ",b"POST ",b"HEAD ")):
        protocol="http_prefix"
    elif payload.startswith((b"SSH-",b"OPTIONS ",b"CONNECT ",b"DELETE ",b"PATCH ")):
        protocol="other_common_prefix"
    exempt = bool(leading>=6 or longest>20 or bits<=3.4 or bits>=4.6 or fraction>0.5 or protocol in ("tls_prefix","http_prefix"))
    return {"classified":True,"printable_fraction":round(fraction,4),"mean_set_bits":round(bits,4),
            "leading_printable":leading,"longest_printable_run":longest,"common_prefix":protocol,
            "historical_passive_nonexempt":not exempt}


class ProbeDetector:
    def __init__(self, events, max_records=512, window=300, salt=None):
        self.events,self.limit,self.window = events,max_records,window
        self.salt = salt or secrets.token_bytes(32)
        self.records,self.index = OrderedDict(),{}
        self.sources,self.cooldowns = OrderedDict(),OrderedDict()
        self.counts = Counter()
        self.sequence = 0

    def tag(self,value):
        return hmac.new(self.salt,value.encode(),hashlib.sha256).hexdigest()[:16]

    def _discard_oldest(self):
        ident,row=self.records.popitem(last=False)
        for key in row["keys"]:
            if self.index.get(key)==ident:self.index.pop(key,None)

    def _expire(self,now):
        while self.records and next(iter(self.records.values()))["time"]<now-self.window:
            self._discard_oldest()
        while self.sources and (len(self.sources)>self.limit or next(iter(self.sources.values()))["time"]<now-60):
            self.sources.popitem(last=False)
        while self.cooldowns and (len(self.cooldowns)>self.limit or next(iter(self.cooldowns.values()))<now-30):
            self.cooldowns.popitem(last=False)

    def _emit(self,kind,source,service,now,**evidence):
        key=(kind,evidence.get("pattern"),source,service)
        if now-self.cooldowns.get(key,-1e20)<30:
            self.counts["events_deduplicated"]+=1
            return
        self.cooldowns[key]=now;self.cooldowns.move_to_end(key)
        self.events.add(kind,"warning",source_tag=self.tag(source),service_tag=self.tag(str(service)),
                        attribution="unknown",**evidence)

    def syn(self,source,service,now):
        self._expire(now)
        key=(source,service)
        row=self.sources.setdefault(key,{"time":now,"syn":deque(maxlen=64),"lengths":deque(maxlen=32)})
        row["time"]=now;self.sources.move_to_end(key)
        row["syn"].append(now)
        count=sum(now-t<=10 for t in row["syn"])
        if count>=20:
            self.counts["connection_bursts"]+=1
            self._emit("connection_attempt_burst",source,service,now,confidence="low",attempts=count,window_seconds=10,
                       basis="repeated_connection_attempts_not_actor_identity")

    @staticmethod
    def keys(payload,service):
        n=len(payload)
        yield (service,"R1",n,hashlib.sha256(payload).digest())
        for kind,positions in MASKS.items():
            masked=bytearray(payload)
            for index in positions:masked[index]=0
            yield (service,kind,n,hashlib.sha256(masked).digest())

    def observe(self,payload,source,flow,service,now,complete=True):
        self._expire(now)
        self.counts["first_payloads"]+=1
        if not complete or not 1<=len(payload)<=2048:
            self.counts["incomplete_or_large_payloads"]+=1
            return
        features=passive_features(payload)
        if features["historical_passive_nonexempt"]:
            # Ciphertext is ordinary proxy traffic: this never raises an alarm.
            self.counts["historical_passive_nonexempt"]+=1
        if features["common_prefix"]:
            self.counts["common_protocol_payloads"]+=1
            return
        length=len(payload)
        if length in NR20 or length in NR23:
            key=(source,service)
            row=self.sources.setdefault(key,{"time":now,"syn":deque(maxlen=64),"lengths":deque(maxlen=32)})
            row["time"]=now;self.sources.move_to_end(key)
            row["lengths"].append((now,length,hashlib.sha256(payload).digest()))
            recent=[item for item in row["lengths"] if now-item[0]<=60]
            self.counts["historical_length_matches"]+=1
            # A single matching length is never sufficient for an alert.
            if len(recent)>=3 and len({item[2] for item in recent})>=2:
                self._emit("historical_probe_length_cluster",source,service,now,confidence="low",
                           observations=len(recent),lengths=",".join(map(str,sorted({x[1] for x in recent}))),
                           research="IMC2020_or_USENIX2023",basis="historical_lengths_and_repetition")
        if length<64:
            return
        keys=list(self.keys(payload,service))
        match=None
        for key in keys:
            previous=self.records.get(self.index.get(key))
            if not previous or previous["flow"]==flow:
                continue
            if key[1]!="R1":
                changed={i for i in CHANGED_BYTES if previous["changed"][i]!=payload[i]}
                if changed!=set(MASKS[key[1]]):continue
            match=(key[1],previous)
            break
        if match:
            kind,previous=match
            confidence="medium" if previous["source"]!=source else "low"
            self.counts["replay_pattern_"+kind]+=1
            self._emit("historical_replay_pattern",source,service,now,confidence=confidence,pattern=kind,
                       payload_bytes=length,interval_seconds=round(now-previous["time"],3),
                       reference_tag=self.tag(previous["source"]),different_source=previous["source"]!=source,
                       digest=hashlib.sha256(payload).hexdigest(),research="IMC2020",
                       basis="equal_payload" if kind=="R1" else "equal_payload_except_documented_offsets")
        while len(self.records)>=self.limit:self._discard_oldest()
        self.sequence+=1
        row={"time":now,"source":source,"flow":flow,"keys":keys,
             "changed":{i:payload[i] for i in CHANGED_BYTES}}
        self.records[self.sequence]=row
        for key in keys:self.index[key]=self.sequence

    def summary(self):
        return {"enabled":True,"counts":dict(self.counts),"reference_records":len(self.records),
                "max_records":self.limit,"window_seconds":self.window,"attribution":"unknown",
                "automatic_source_blocking":False,
                "limitations":["historical_patterns_not_current_actor_identity","packet_boundaries_affect_length_features",
                               "short_patterns_are_weak","inbound_drops_may_hide_payload","bounded_capture_can_miss_events"]}
