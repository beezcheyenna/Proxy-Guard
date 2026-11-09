#!/usr/bin/env python3
"""Exercise tcpdump under the exact systemd capability bound, offline VM only."""
import ctypes,json,os,select,subprocess,sys,time
from pathlib import Path
assert Path("/.proxy-guard-test-root").is_file()
assert os.geteuid()==0
assert os.readlink("/proc/self/ns/net")!=os.readlink("/proc/1/ns/net")

def bound(allowed):
    libc=ctypes.CDLL(None,use_errno=True)
    for cap in range(41):
        if cap not in allowed:libc.prctl(24,cap,0,0,0)
    class Header(ctypes.Structure):_fields_=[("version",ctypes.c_uint32),("pid",ctypes.c_int)]
    class Data(ctypes.Structure):_fields_=[("effective",ctypes.c_uint32),("permitted",ctypes.c_uint32),("inheritable",ctypes.c_uint32)]
    h=Header(0x20080522,0);d=(Data*2)()
    for cap in allowed:d[cap//32].effective|=1<<(cap%32);d[cap//32].permitted|=1<<(cap%32)
    if libc.capset(ctypes.byref(h),d)!=0:raise OSError(ctypes.get_errno(),"capset")
    if libc.prctl(38,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),"no_new_privileges")

if len(sys.argv)>1:
    caps=[int(x) for x in sys.argv[1].split(',')]
    bound(caps)
    if len(sys.argv)>2 and sys.argv[2]=='monitor':
        sys.path.insert(0,'/work/companion/vps')
        from monitor import Monitor
        m=Monitor({'services':[{'name':'unprivileged-fixture','process_names':['python3','python3.12'],'tcp_ports':[18090],'udp_ports':[18091]}]})
        print(json.dumps({'caps':caps,'healthy':m.sample()['ok']}));raise SystemExit(0)
    process=subprocess.Popen(['tcpdump' ,'-i','lo','-c','1','-nn','-Z','root','-U','-w','-','tcp port 18080'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    readable=select.select([process.stdout],[],[],4)[0]
    header=process.stdout.read(24) if readable else b''
    if process.poll() is None:process.terminate()
    _,error=process.communicate(timeout=4)
    print(json.dumps({'caps':caps,'started':len(header)==24,'stderr':error.decode(errors='replace')[:500]}))
else:
    subprocess.run(['ip','link','set','lo','up'],check=True)
    service_code="""import os,socket,time,ctypes
os.setgroups([]);os.setgid(65534);os.setuid(65534);ctypes.CDLL(None).prctl(4,1,0,0,0)
t=socket.socket();t.bind(('127.0.0.1',18090));t.listen()
u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.bind(('127.0.0.1',18091))
print('ready',flush=True);time.sleep(60)
"""
    service=subprocess.Popen([sys.executable,'-u','-c',service_code],stdout=subprocess.PIPE,text=True)
    assert service.stdout.readline().strip()=='ready'
    results=[]
    try:
        for caps in ['12,13','12,13,19','2,12,13','2,12,13,19']:
            for mode in ['capture','monitor']:
                p=subprocess.run([sys.executable,__file__,caps,mode],capture_output=True,text=True,timeout=12)
                if p.returncode:raise AssertionError(p.stderr)
                results.append(json.loads(p.stdout))
        print(json.dumps(results,indent=2))
        assert next(x for x in results if x['caps']==[2,12,13,19] and 'healthy'in x)['healthy'], 'configured cross-user process inspection must work'
        assert next(x for x in results if x['caps']==[2,12,13,19] and 'started'in x)['started'], 'configured capture capabilities must work'
    finally:
        service.terminate();service.wait(timeout=3)
