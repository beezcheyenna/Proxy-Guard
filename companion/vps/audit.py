#!/usr/bin/env python3
"""Offline bounded PCAP analysis, evidence comparison and multi-node report aggregation."""
import argparse,json,struct,sys
from pathlib import Path
from monitor import EventStore
from research import Analyzer,packet

def analyze(path,node="local",max_packets=200000):
    events=EventStore(512,2592000)
    analyzer=Analyzer(events,probe_detection=True)
    total=0
    with Path(path).open("rb") as stream:
        header=stream.read(24)
        if len(header)!=24:raise ValueError("invalid_pcap")
        magic=header[:4]
        if magic in (b"\xd4\xc3\xb2\xa1",b"\x4d\x3c\xb2\xa1"):endian="<"
        elif magic in (b"\xa1\xb2\xc3\xd4",b"\xa1\xb2\x3c\x4d"):endian=">"
        else:raise ValueError("pcapng_not_supported")
        nano=magic in (b"\x4d\x3c\xb2\xa1",b"\xa1\xb2\x3c\x4d")
        linktype=struct.unpack(endian+"I",header[20:24])[0]
        while total<max_packets:
            record=stream.read(16)
            if not record:break
            if len(record)!=16:raise ValueError("truncated_pcap")
            sec,fraction,size,original=struct.unpack(endian+"IIII",record)
            if size>262144 or size>original:raise ValueError("invalid_pcap_record")
            data=stream.read(size)
            if len(data)!=size:raise ValueError("truncated_pcap")
            item=packet(data,linktype)
            if item and size<original:item["truncated"]=True
            analyzer.feed(item,sec+fraction/(1e9 if nano else 1e6))
            total+=1
    return {"schema":1,"node":node,"packets":total,"packet_limit_reached":total>=max_packets,
            "analysis":analyzer.summary(),"events":events.snapshot(limit=200),
            "prefix_observations":[{"digest":digest,"observed_at":row["time"]}
                                   for digest,row in analyzer.digests.items()],
            "privacy":{"raw_packets":False,"addresses":False},"attribution":"unknown"}

def aggregate(reports):
    if not isinstance(reports,list) or not 1<=len(reports)<=32:raise ValueError("invalid_report_count")
    nodes=set();index={};matches=[];summary=[]
    for report in reports:
        node=report.get("node")
        if not isinstance(node,str) or not 1<=len(node)<=64 or node in nodes:raise ValueError("duplicate_or_invalid_node")
        nodes.add(node)
        observations=report.get("prefix_observations",[])
        if not isinstance(observations,list) or len(observations)>4096:raise ValueError("invalid_observations")
        summary.append({"node":node,"packets":report.get("packets"),"analysis":report.get("analysis")})
        for item in observations:
            digest=item.get("digest")
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid_digest")
            for previous in index.get(digest,[]):
                if previous["node"]!=node:
                    matches.append({"digest":digest,"nodes":[previous["node"],node],
                                    "confidence":"low","meaning":"equal_observed_tcp_prefix",
                                    "attribution":"unknown"})
            index.setdefault(digest,[]).append({"node":node,"observed_at":item.get("observed_at")})
    return {"schema":1,"nodes":summary,"prefix_matches":matches[:4096],
            "truncated":len(matches)>4096,"attribution":"unknown",
            "limitations":["clock_alignment_required","prefix_equality_is_not_full_stream_equality",
                           "missing_match_is_not_proof_of_tampering"]}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("analyze");a.add_argument("pcap");a.add_argument("--node",default="local");a.add_argument("--max-packets",type=int,default=200000)
    a=sub.add_parser("aggregate");a.add_argument("reports",nargs="+")
    args=p.parse_args()
    if args.command=="analyze":
        if not 1<=args.max_packets<=1000000:p.error("max-packets out of range")
        result=analyze(args.pcap,args.node,args.max_packets)
    else:
        result=aggregate([json.loads(Path(name).read_text()) for name in args.reports])
    print(json.dumps(result,indent=2,allow_nan=False))
if __name__=="__main__":main()
