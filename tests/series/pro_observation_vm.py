#!/usr/bin/env python3
"""Pro summaries and continuous observation: actual sockets, offline VM only."""
from pathlib import Path
import json,os,socket,subprocess,sys,tempfile,threading,time
assert Path("/.proxy-guard-test-root").is_file()
assert os.geteuid()==0 and os.readlink('/proc/self/ns/net')!=os.readlink('/proc/1/ns/net')
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R/'companion/vps'))
from agent import Engine,Nft
from control import Server
from sensors import Sensors
from monitor import EventStore
subprocess.run(['ip','link','set','lo','up'],check=True)
passed=[]
def check(value,label):
    assert value,label
    passed.append(label);print('PASS',label,flush=True)
def wait(predicate,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return True
        time.sleep(.05)
    return False
listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('127.0.0.1',16043));listener.listen();listener.settimeout(.1)
stop=threading.Event()
def serve():
    while not stop.is_set():
        try:
            client,_=listener.accept()
            with client:client.settimeout(1);client.recv(2048)
        except socket.timeout:pass
        except OSError:break
threading.Thread(target=serve,daemon=True).start()
with tempfile.TemporaryDirectory() as directory:
    engine=Engine('a'*40,'home',Path(directory)/'state.json',Nft())
    pro=Server(('127.0.0.1',0),engine,{'direct_token':'d'*40,'analysis':{'enabled':True,'ports':[16043],'interface':'lo','duration':1}},'pro')
    try:
        check(wait(lambda:pro.sensors.capture.state=='running'),'Pro starts optional passive observations')
        check(not pro.sensors.honeypot.enabled and not pro.sensors.capture.config['save_pcap'],'Pro does not enable raw evidence or a honeypot')
        check(pro.status()['analysis']['capture']['state']=='running','Pro status exports actual observation state')
    finally:pro.server_close()
    check(pro.sensors.capture.process.poll()is not None,'Pro shutdown reaps its capture')
    events=EventStore()
    continuous=Sensors({'enabled':True,'interface':'lo','ports':[16043],'duration':2,'continuous':True,'pause':1},events)
    continuous.start()
    try:
        check(wait(lambda:continuous.capture.state=='running'),'continuous first bounded session starts')
        analyzer=continuous.capture.analyzer;first_process=continuous.capture.process
        with socket.create_connection(('127.0.0.1',16043),2) as client:client.sendall(bytes(range(256)))
        check(wait(lambda:analyzer.counts['tcp_packets']>0),'first session observes real packets')
        check(wait(lambda:continuous.sessions>=2 and continuous.capture.state=='running',10),'continuous mode starts its next bounded session after a pause')
        check(continuous.capture.analyzer is analyzer,'bounded evidence window survives a capture-session boundary')
        with socket.create_connection(('127.0.0.1',16043),2) as client:client.sendall(bytes(range(256)))
        check(wait(lambda:analyzer.counts['repeated_prefixes']>0),'real repeated data is correlated across sessions')
        check(first_process.poll()is not None,'previous capture process is reaped before the next session')
    finally:continuous.close();stop.set();listener.close();engine.driver.cleanup()
    check(continuous.capture.process.poll()is not None,'continuous shutdown leaves no capture process')
print(json.dumps({'passed':len(passed),'checks':passed,'cloudflare':'not_tested'}))
