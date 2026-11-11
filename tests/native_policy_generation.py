#!/usr/bin/env python3
"""Native regression for generation-bound fast leases in a disconnected VM.
Requires the marked two-namespace traffic fixture and a running proxy client.
Does not start a remote job or contact Cloudflare.
"""
from pathlib import Path
import subprocess,json,time,fcntl,uuid,traceback
assert Path("/etc/pgvm-fixture").exists() and Path("/.proxy-guard-test-root").exists()
checks=[];started=time.monotonic();marker="policy-generation-"+str(uuid.uuid4())
def command(*args,timeout=75):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 assert p.returncode==0,(args,p.returncode,p.stdout,p.stderr)
 return p.stdout
def rpc(obj,method,values):
 return json.loads(command("ubus","-t","60","call",obj,method,json.dumps(values)) or "{}")
def ok(condition,message):
 assert condition,message
 checks.append(message);print("PASS "+message,flush=True)
def status():return rpc("proxy_guard","status",{})
def wait(predicate,message,timeout=90):
 deadline=time.monotonic()+timeout;last=None
 while time.monotonic()<deadline:
  last=status()
  if predicate(last):ok(True,message);return last
  time.sleep(.4)
 raise AssertionError((message,last))
def apply(values):
 rpc("uci","set",{"ubus_rpc_session":sid,"config":"proxy_guard","section":"main","values":values})
 result=rpc("proxy_guard","apply",{"ubus_rpc_session":sid,"confirm_flow":True})
 assert result.get("ok") is True,result
 if result.get("confirmation_required"):
  tx=result["transaction"];deadline=time.monotonic()+105
  while time.monotonic()<deadline:
   if rpc("proxy_guard","setup_info",{"ubus_rpc_session":sid}).get("transaction",{}).get("phase")=="confirming":break
   time.sleep(.4)
  else:raise AssertionError("configuration self-check did not finish")
  result=rpc("proxy_guard","setup_confirm",{"ubus_rpc_session":sid,"id":tx["id"],"token":tx["token"]})
  assert result.get("ok") is True,result
 return result
def logs():return command("logread").rsplit(marker,1)[-1]
def no_gate_error():
 text=logs()
 return not ("fast-transaction.nft" in text and ("No such file" in text or "Error:" in text))
try:
 auth=json.loads(Path("/tmp/pg-latest-login.json").read_text())
 sid=rpc("session","login",{"username":"root","password":auth["password"]})["ubus_rpc_session"]
 profile=json.loads(command("ucode","/usr/lib/proxy-guard/inspect-client.uc",command("uci","get","proxy_guard.main.proxy_client").strip()))
 assert profile.get("available") and profile.get("socks_port"),profile
 # Explicit manual endpoint keeps the generation-only test independent of auto-binding.
 apply({"enabled":"1","socks_port":str(profile["socks_port"]),"passwall_watch":"1","passwall_log_watch":"0","client_auto_ports":"1","boot_guard":"0","fast_wait_enabled":"0","fast_stable_enabled":"0"})
 wait(lambda s:s.get("enforcement")=="allowing","watched configuration permits real traffic before regression")
 command("logger","-t","PG_REGRESSION",marker)
 apply({"passwall_watch":"0","passwall_log_watch":"0","boot_guard":"0"})
 wait(lambda s:s.get("enforcement")=="allowing","public service-monitor disable finishes without losing connectivity")
 time.sleep(5)
 ok(no_gate_error(),"no stale service-set write during the public configuration change")
 native=command("nft","-j","list","table","inet","proxy_guard")
 ok("service_ifaces" not in native,"service-disabled rules do not contain the optional service gate")
 # Exercise the actual local pre-maintenance hook, with a local queue fixture.
 # No remote sender is started. The job expires naturally after 30 seconds.
 queue=Path("/var/run/proxy-guard-access/pending");queue.mkdir(parents=True,exist_ok=True)
 job=queue/"job.json";assert not job.exists(),"unexpected live job"
 job.write_text(json.dumps({"action":"restart_xray","operation_id":str(uuid.uuid4()),"created_uptime":float(Path("/proc/uptime").read_text().split()[0]),"timeout":30}))
 try:
  response=json.loads(command("/usr/libexec/proxy-guard","maintenance"))
  ok(response.get("protection_required") is True,"maintenance hook revokes local access even with service monitoring disabled")
  wait(lambda s:s.get("enforcement")=="blocked","maintenance state is genuinely blocking",15)
  time.sleep(6)
  fast=json.loads(Path("/var/run/proxy-guard/fast.json").read_text())
  config=json.loads(Path("/var/run/proxy-guard/status.json").read_text())["fast_config"]
  ok(config["enabled"] and not config["services_watch"],"remote hold still runs the independent state machine")
  ok(fast.get("gate_ok") is True and no_gate_error(),"remote hold never writes an absent service set")
  wait(lambda s:s.get("enforcement")=="allowing","expired maintenance hold requires successful local probes before recovery",80)
 finally:job.unlink(missing_ok=True)
 apply({"passwall_watch":"1","client_auto_ports":"1"})
 wait(lambda s:s.get("enforcement")=="allowing","service gate is recreated after enabling monitoring")
 fast_path=Path("/var/run/proxy-guard/fast.json")
 first=json.loads(fast_path.read_text())["updated_uptime"]
 with open("/var/run/fw4.lock","a") as lock:
  deadline=time.monotonic()+15
  while True:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    assert time.monotonic()<deadline,"fw4 lock acquisition deadline"
    time.sleep(.1)
  time.sleep(6)
  latest=json.loads(fast_path.read_text())
  ok(latest["updated_uptime"]>first+3,"busy firewall does not stall independent service monitoring")
  ok(latest.get("gate_ok") is False,"busy firewall cannot be represented as a renewed permit")
  rules=json.loads(command("nft","-j","list","set","inet","proxy_guard","service_ifaces"))
  values=[x["set"].get("elem",[]) for x in rules["nftables"] if "set" in x]
  ok(values==[[]],"service permit expires in the kernel while fw4 lock is busy")
  probe="import socket;s=socket.socket();s.settimeout(2);r=s.connect_ex(('9.9.9.9',23456));print(r)"
  ok(command("ip","netns","exec","pglan","python3","-c",probe).strip()!="0","real client connection is blocked by the expired permit")
  fcntl.flock(lock,fcntl.LOCK_UN)
 wait(lambda s:s.get("enforcement")=="allowing","permit renews only after firewall becomes available",30)
 command("/etc/init.d/firewall","reload")
 wait(lambda s:s.get("enforcement")=="allowing","native firewall4 reload retains and reconciles protection",45)
 ok(no_gate_error(),"configuration changes and firewall reload produce no stale-gate errors")
 apply({"enabled":"0"})
 wait(lambda s:s.get("enforcement")=="off","public emergency off removes only the owned policy",30)
 result={"ok":True,"checks":checks,"seconds":time.monotonic()-started}
except Exception:
 result={"ok":False,"checks":checks,"error":traceback.format_exc(),"seconds":time.monotonic()-started}
 print(result["error"],flush=True)
finally:
 result["log_after_marker"]=logs()
 Path("/tmp/pg-policy-generation-result.json").write_text(json.dumps(result,indent=2))
raise SystemExit(0 if result["ok"] else 1)
