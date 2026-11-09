"""Bounded trusted log adapters and per-source resource observations; no payload capture."""
from __future__ import annotations
import collections,datetime,ipaddress,json,os,re,stat,time
from pathlib import Path
from protection import DEFAULT_LIMITS,mode_for

class Tail:
    def __init__(self,path,owner_uid=0):self.owner_uid=owner_uid;self.path=path;self.identity=None;self.offset=0;self.pending=b'';self.available=False
    def poll(self):
        if not self.path:return []
        try:
            fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb')as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode)or info.st_mode&0o022 or info.st_uid not in(0,os.geteuid(),self.owner_uid):raise OSError('untrusted_log')
                identity=(info.st_dev,info.st_ino)
                if identity!=self.identity or info.st_size<self.offset:
                    self.identity=identity;self.offset=max(0,info.st_size-65536);self.pending=b''
                stream.seek(self.offset);data=stream.read(65536);self.offset=stream.tell()
            self.available=True
            parts=(self.pending+data).split(b'\n');self.pending=parts.pop()[-8192:]
            return [line.decode('utf-8','replace')for line in parts if len(line)<=8192]
        except OSError:self.available=False;return []

class Telemetry:
    def __init__(self,engine,reality,events,clock=time.monotonic,wall=time.time):
        self.engine,self.reality,self.events=engine,reality,events;self.clock,self.wall=clock,wall
        self.access=Tail(reality.config['access_log'],reality.config['log_uid']);self.feed=Tail(reality.config['telemetry_file'],reality.config['log_uid'])
        self.trusted={};self.restricted={};self.flows=collections.OrderedDict();self.previous={};self.observations=[]
        self.last_sample=None;self.last_feed=None;self.alerted={}
    def _rule(self,port,protocol):
        for rule in self.engine.state['policy']['rules']:
            if not rule['enabled']or rule['protocol']not in(protocol,'both'):continue
            if any(int(span.split('-')[0])<=port<=int(span.split('-')[-1])for span in rule['ports']):return rule
        return None
    def event(self,value):
        try:
            stamp=value['time'];address=ipaddress.ip_address(value['source_ip']);sport=value['source_port'];port=value['port'];proto=value.get('protocol','tcp');kind=value['kind']
            if not isinstance(stamp,(int,float))or isinstance(stamp,bool)or not 0<=self.wall()-stamp<=60 or not address.is_global or address.is_multicast:return
            if type(sport)is not int or not 1<=sport<=65535 or type(port)is not int or proto not in('tcp','udp'):return
            rule=self._rule(port,proto)
            if not rule:return
            source=str(address);now=self.clock()
            if kind=='authenticated':
                self.trusted.setdefault(rule['id'],{})[(proto,source,port)]=now+120;return True
            if kind!='fallback':return
            incoming=value.get('bytes_in',0);outgoing=value.get('bytes_out',0)
            if any(type(n)is not int or not 0<=n<=1099511627776 for n in(incoming,outgoing)):return
            total=incoming+outgoing
            key=(rule['id'],proto,source,sport,port);old=self.flows.get(key)
            limit=rule.get('limits',DEFAULT_LIMITS);above=None
            if old and limit["bandwidth_enabled"]:
                elapsed=now-old['time'];delta=max(incoming-old['incoming'],outgoing-old['outgoing'])
                if 0<elapsed<=60 and incoming>=old['incoming'] and outgoing>=old['outgoing'] and delta>=0 and delta/elapsed>limit['bandwidth']:above=old['above']if old['above']is not None else now
                if above is not None and now-above>=limit['sustain']:
                    if mode_for(self.engine.state['policy'],rule)=='standard':self.restricted.setdefault(rule['id'],{})[(proto,source,sport,port)]=now+limit['cooldown']
                    self.alert('fallback_bandwidth',rule['id'],proto,source,port)
            self.flows[key]={'time':now,'bytes':total,'incoming':incoming,'outgoing':outgoing,'above':above};self.flows.move_to_end(key)
            while len(self.flows)>2048:self.flows.popitem(last=False)
            return True
        except (KeyError,ValueError,TypeError,OverflowError):return
    def access_line(self,line):
        # Xray accepted + an explicit configured inbound tag + authenticated
        # email is evidence of acceptance; SNI or a generic error is not.
        match=re.match(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)? from (?:tcp:|udp:)?(\[[0-9a-fA-F:]+\]|[0-9.]+):([0-9]+) accepted \S+ \[([^] ]+)(?: -> [^]]+)?\].* email: \S+',line)
        if not match:return
        try:
            stamp=datetime.datetime.strptime(match[1],'%Y/%m/%d %H:%M:%S').timestamp()
            port=self.reality.tags.get(match[4]);source=match[2].strip('[]')
            if port:self.event(dict(time=stamp,source_ip=source,source_port=int(match[3]),port=port,kind='authenticated',protocol='tcp'))
        except (ValueError,OverflowError):pass
    def alert(self,kind,rule,proto,source,port):
        key=(kind,rule,proto,source,port);now=self.clock()
        if now-self.alerted.get(key,-1000)<30:return
        self.alerted[key]=now
        self.events.add('resource_anomaly','warning',reason=kind,service=rule,protocol=proto,source_ip=source,port=port)
        if len(self.alerted)>2048:self.alerted={k:v for k,v in self.alerted.items()if now-v<60}
    def poll(self,current=None):
        self.reality.sample()
        for line in self.access.poll():self.access_line(line)
        for line in self.feed.poll():
            try:value=json.loads(line)
            except ValueError:continue
            if isinstance(value,dict):
                stamp=value.get('time')
                heartbeat=value.get('kind')=='heartbeat'and type(stamp)in(int,float)and 0<=self.wall()-stamp<=60
                if heartbeat or self.event(value):self.last_feed=self.clock()
        now=self.clock();active={r['id']for r in self.engine.state['policy']['rules']if r['enabled']}
        self.trusted={k:{ip:until for ip,until in values.items()if until>now}for k,values in self.trusted.items()if k in active}
        self.restricted={k:{flow:until for flow,until in values.items()if until>now}for k,values in self.restricted.items()if k in active}
        self.flows=collections.OrderedDict((k,v)for k,v in self.flows.items()if now-v['time']<120 and k[0]in active)
        for groups in(self.trusted,self.restricted):
            entries=sorted((until,service,key)for service,values in groups.items()for key,until in values.items())
            for _,service,key in entries[:-4096]:groups[service].pop(key,None)
        runtime=dict(self.engine.runtime);runtime['trusted']={k:[dict(protocol=f[0],source=f[1],port=f[2],until=t)for f,t in values.items()]for k,values in self.trusted.items()};runtime['fallback_restricted']={k:[dict(protocol=f[0],source=f[1],sport=f[2],port=f[3],until=t)for f,t in values.items()]for k,values in self.restricted.items()}
        changed=runtime!=self.engine.runtime;self.engine.runtime=runtime
        if current:self.sample_counters(current)
        return changed
    def sample_counters(self,current):
        now=self.clock();rows=[];rules=self.engine.effective_policy()['rules']
        internal_count=len(rules)-len(self.engine.state['policy']['rules'])
        for item in current.get('nftables',[]):
            value=item.get('set',{});name=value.get('name','')
            extra=re.fullmatch(r'(cool|capacity|newflow)([46])_([0-9]+)_(tcp|udp)',name)
            if extra and int(extra[3])<len(rules):
                rule=rules[int(extra[3])]
                if int(extra[3])<internal_count:continue
                limits=rule.get('limits',DEFAULT_LIMITS)
                for element in value.get('elem',[])[:128]:
                    e=element.get('elem',element)if isinstance(element,dict)else{'val':element};value=e.get('val');parts=value.get('concat',[])if isinstance(value,dict)else[]
                    if len(parts)!=2 or not isinstance(parts[0],str):continue
                    address,port=parts
                    if extra[1]in('cool','capacity'):self.alert('temporary_connection_limit'if extra[1]=='cool'else'concurrency_threshold',rule['id'],extra[4],address,port)
                    else:
                        key=('newflow',rule['id'],extra[4],address,port);count=e.get('counter',{}).get('packets',0);old=self.previous.get(key)
                        if old and now>old[0]and count>=old[1]and(count-old[1])/(now-old[0])>limits['rate']:self.alert('connection_rate_threshold',rule['id'],extra[4],address,port)
                        self.previous[key]=(now,count,0)
                continue
            m=re.fullmatch(r'seen([46])_([0-9]+)_(tcp|udp)',value.get('name',''))
            if not m:continue
            index=int(m[2])
            if index>=len(rules):continue
            rule=rules[index]
            if index<internal_count:continue
            limits=rule.get('limits',DEFAULT_LIMITS)
            for element in value.get('elem',[])[:128]:
                e=element.get('elem',element)if isinstance(element,dict)else{}
                value=e.get('val');parts=value.get('concat',[])if isinstance(value,dict)else[]
                if len(parts)!=2 or not isinstance(parts[0],str)or type(parts[1])is not int or not 1<=parts[1]<=65535:continue
                try:address=str(ipaddress.ip_address(parts[0]))
                except ValueError:continue
                port=parts[1];counter=e.get('counter',{})
                packets=counter.get('packets',0);bytes_=counter.get('bytes',0);key=(rule['id'],m[3],address,port);old=self.previous.get(key)
                rate=None
                if old and now>old[0]and bytes_>=old[2]:rate=(bytes_-old[2])/(now-old[0])
                self.previous[key]=(now,packets,bytes_)
                rows.append(dict(service=rule['id'],protocol=m[3],source_ip=address,port=port,packets=packets,bytes=bytes_,bytes_per_second=int(rate)if rate is not None else None))
        self.observations=sorted(rows,key=lambda v:v['bytes'],reverse=True)[:64]
        self.previous={k:v for k,v in self.previous.items()if now-v[0]<600}
    def status(self):
        return {'bandwidth_requested':any(r.get('limits',DEFAULT_LIMITS)['bandwidth_enabled']for r in self.engine.state['policy']['rules']if r['enabled']),'access_log_available':self.access.available,'fallback_telemetry_available':bool(self.feed.available and self.last_feed is not None and self.clock()-self.last_feed<=60),
                'native_checks':self.reality.status(),'sources':self.observations,
                'trusted_source_count':sum(len(v)for v in self.trusted.values()),
                'fallback_restrictions':sum(len(v)for v in self.restricted.values())}
