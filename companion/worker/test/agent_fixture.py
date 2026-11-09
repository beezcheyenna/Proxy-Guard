"""Actual Agent HTTP fixture; maintenance executor only records simulated actions."""
import sys,os,json,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'vps'))
from agent import Engine,Nft
from control import Server
class MemoryDriver:
    def apply(self,policy,leases):
        if (root/'fail-nft').exists():raise RuntimeError('injected_nft_failure')
        self.policy,self.leases=policy,leases
root=Path(tempfile.mkdtemp(prefix='pg-cf-contract-'))
driver=Nft()if os.getenv('PG_CF_REAL_NFT')=='1'else MemoryDriver()
engine=Engine('a'*40,'home',root/'state.json',driver)
config={'services':[{'name':'python','process_names':['python3'],'tcp_ports':[],'udp_ports':[],'required':True}],'monitor_interval':2,'maintenance':{'enabled':True,'allow_restart_xray':True,'allow_reboot':False,'service':'fixture','verify_seconds':15}}
server=Server(('127.0.0.1',0),engine,config,'pro')
class SimulatedHealth:
    generation=0
    def status(self):return {'configured':True,'ok':True,'stale':False,'services':[{'name':'fixture','ok':True,'generation':str(self.generation)}]}
health=SimulatedHealth();server.maintenance.monitor=health
server.dispatches=[]
def execute(action,config):
    server.dispatches.append(action);health.generation+=1
    (root/'dispatches.json').write_text(json.dumps(server.dispatches))
server.maintenance.executor=execute
server.monitor.sample()
print(json.dumps({'port':server.server_port,'directory':str(root),'real_nft':isinstance(driver,Nft)}),flush=True)
try:server.serve_forever(poll_interval=.1)
finally:server.server_close()
