local root=os.getenv('PG_SOURCE') or '/src'
package.path=root..'/package/pro/root/usr/lib/?.lua;'..root..'/package/root/usr/lib/?.lua;'..package.path
local m=require 'proxy-guard.access'
local ssh={managed=false,confirmed=false,port=22,rescue_enabled=true,after=60,scope='public',open_seconds=600,managers={}}
local c={policy_enabled=true,default_deny=false,auto_discover=false,address_families={4},mode='standard',ssh=ssh}
local n=0
local function check(v,s) assert(v,s);n=n+1 end
local function r() return {protocol=3,policy={enabled=true,default_deny=false,auto_discover=false,address_families={4},mode='standard',ssh=require('luci.jsonc').parse(require('luci.jsonc').stringify(ssh))}} end
check(m.confirms(c,r()),'explicit matching policy confirmation')
local s=r();s.protocol=2;check(not m.confirms(c,s),'old protocol cannot silently ignore settings')
s=r();s.policy.default_deny=true;check(not m.confirms(c,s),'whole-host policy cannot claim selected-port protection')
s=r();s.policy.auto_discover=true;check(not m.confirms(c,s),'automatic enrollment must be rejected')
s=r();s.policy.address_families={4,6};check(not m.confirms(c,s),'unexpected authorized family must be rejected')
s=r();s.policy.enabled=false;check(not m.confirms(c,s),'disabled policy cannot claim active protection')
s=r();s.ingress=s.policy;s.policy=nil;check(m.confirms(c,s),'status confirmation uses actual ingress metadata')
local loaded=m.load({main={enabled='1',endpoint='https://agent.test',device_id='home',device_token=string.rep('d',40),direct_confirmed='1',default_deny='1',auto_discover='1'}})
check(loaded.default_deny==false and loaded.auto_discover==false,'legacy UCI flags cannot expand scope')
check(#loaded.rules==0,'an empty service list must not enroll SSH')
check(require('luci.jsonc').stringify({rules=loaded.rules})=='{"rules":[]}','native JSON preserves the empty rule array')
check(loaded.ssh.open_seconds==0,'new policy defaults to unlimited rescue')
local base={enabled='1',endpoint='https://agent.test',device_id='home',device_token=string.rep('d',40),direct_confirmed='1'}
base.ssh_open_seconds='600';check(m.load({main=base}).ssh.open_seconds==600,'existing positive window is preserved')
base.ssh_open_seconds='0';check(m.load({main=base}).ssh.open_seconds==0,'explicit zero is accepted')
base.ssh_open_seconds='29';check(not pcall(m.load,{main=base}),'invalid short window is rejected')
ssh.open_seconds=0;check(m.confirms(c,r()),'zero is compared without falling back to 600')
local mismatch=r();mismatch.policy.ssh.open_seconds=600;check(not m.confirms(c,mismatch),'old positive acknowledgement cannot confirm unlimited rescue')
base.ssh_open_seconds='0'
local configured=m.load({main=base,one={['.type']='rule',name='One',ports={'443'},protection_mode='observe'}})
check(configured.requires_rule_modes==true and configured.rules[1].mode=='observe','per-rule UCI mode is loaded and requires capability')
c.requires_rule_modes=true;c.rules={{id='one',mode='whitelist'}}
s=r();check(not m.confirms(c,s),'old service cannot confirm independent modes')
s.policy.per_rule_modes=true;s.policy.rule_modes={one='whitelist'};check(m.confirms(c,s),'actual matching mode acknowledgement is accepted')
s.policy.rule_modes.one='observe';check(not m.confirms(c,s),'wrong per-port mode cannot claim success')
s.policy.rule_modes={one='whitelist',extra='standard'};check(not m.confirms(c,s),'unexpected remote port rule is rejected')
s.policy.rule_modes={};check(not m.confirms(c,s),'missing mode acknowledgement is rejected')
print('PASS '..n..' native Pro policy confirmation checks')
