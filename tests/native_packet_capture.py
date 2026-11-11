#!/usr/bin/env python3
"""Private, bounded capture for an isolated router regression fixture only."""
from pathlib import Path
import socket,struct,time,threading,signal,sys,json,base64,zlib,hashlib
assert Path('/etc/pgvm-fixture').is_file()
dest=Path(sys.argv[1]);stop=threading.Event();rows={};errors=[];workers=[]
def interested(data):
 if len(data)<14:return False
 typ=struct.unpack('!H',data[12:14])[0]
 if typ==0x800:
  off=14+4*(data[14]&15);proto=data[23]
 elif typ==0x86dd:
  if len(data)<54:return False
  off=54;proto=data[20]
 else:return False
 if proto not in [6,17]or len(data)<off+4:return False
 src,dst=struct.unpack('!HH',data[off:off+4])
 return proto==17 or src in [53,23456,18080]or dst in [53,23456,18080]
def worker(iface):
 sock=None
 try:
  sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));sock.bind((iface,0));sock.settimeout(.2)
  row={'ready':True,'pcap':bytearray(struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1)),'packets':0,'truncated':False}
  rows[iface]=row
  while not stop.is_set():
   try:data=sock.recv(65535)
   except socket.timeout:continue
   if not interested(data):continue
   if len(row['pcap'])+len(data)+16>3*1024*1024:row['truncated']=True;continue
   stamp=time.time();sec=int(stamp)
   row['pcap']+=struct.pack('<IIII',sec,int((stamp-sec)*1e6),len(data),len(data))+data;row['packets']+=1
 except Exception as error:errors.append({'interface':iface,'error':repr(error)})
 finally:
  if sock:sock.close()
for iface in ['br-lan','pgwan0','lo']:
 t=threading.Thread(target=worker,args=(iface,),daemon=True);workers.append(t);t.start()
end=time.monotonic()+10
while len(rows)<3:
 assert not errors,errors
 assert time.monotonic()<end,'capture sockets readiness'
 time.sleep(.05)
dest.with_suffix(dest.suffix+'.ready').write_text(json.dumps({'interfaces':list(rows),'pid':__import__('os').getpid()}))
signal.signal(signal.SIGTERM,lambda *_:stop.set())
signal.signal(signal.SIGINT,lambda *_:stop.set())
stop.wait(1500);stop.set()
for t in workers:t.join(2)
out={'private_test_data':True,'errors':errors,'interfaces':{}}
for iface,row in rows.items():
 raw=bytes(row.pop('pcap'));out['interfaces'][iface]={**row,'sha256':hashlib.sha256(raw).hexdigest(),'encoding':'zlib+base64-pcap-ethernet','pcap':base64.b64encode(zlib.compress(raw,9)).decode()}
dest.write_text(json.dumps(out))
print(json.dumps({k:{'packets':v['packets'],'truncated':v['truncated']}for k,v in out['interfaces'].items()}),flush=True)
raise SystemExit(1 if errors else 0)
