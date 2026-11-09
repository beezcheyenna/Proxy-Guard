"""Run ONLY in this lab VM in a new private network namespace."""
import sys,tempfile,json,time,uuid,hmac,hashlib,os
from pathlib import Path
assert os.uname().nodename=='cf-offline','dedicated lab VM required'
assert os.stat('/proc/self/ns/net').st_ino!=os.stat('/proc/1/ns/net').st_ino,'private net namespace required'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'vps'))
from agent import Engine,Nft
root=Path(tempfile.mkdtemp(prefix='pg-cf-expiry-'));driver=Nft();engine=Engine('a'*40,'home',root/'state',driver)
body=dict(device_id='home',observed_ip='8.8.8.8',policy_enabled=True,mode='whitelist',rules=[dict(id='selected',name='Fixture',enabled=True,protocol='tcp',ports=['18443'],source_mode='dynamic',sources=[])],revision=1,ttl=120,issued_at=int(time.time()*1000),request_id=str(uuid.uuid4()))
raw=json.dumps(body).encode();engine.sync(raw,hmac.new(b'a'*40,raw,hashlib.sha256).hexdigest())
def dynamic():
    return [x['set']for x in driver.snapshot()['nftables']if'set'in x and x['set']['name'].startswith('dynamic')]
first=dynamic();assert '8.8.8.8'in json.dumps(first),first
print(json.dumps({'phase':'kernel_lease_present','sets':first}),flush=True)
time.sleep(125)
last=dynamic();assert '8.8.8.8'not in json.dumps(last),last
print(json.dumps({'phase':'kernel_lease_expired_after_125_seconds','sets':last}),flush=True)
new=Engine('a'*40,'home',root/'state',driver);assert new.leases=={}
print(json.dumps({'phase':'cold_restart_no_dynamic_authorization','ok':True}),flush=True)
