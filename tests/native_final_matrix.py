from pathlib import Path
import sys,json,time,subprocess,traceback,os,hashlib,shutil
assert Path("/etc/pgvm-fixture").is_file()
sys.path.insert(0,"/tmp")
from pg_latest_fixture import cmd,setuci,client
D=Path("/root/pg-acceptance/candidate8-matrix");D.mkdir(parents=True)
names={"pwxr":"passwall","pwsr":"passwall","pwx":"passwall","pws":"passwall","p2x":"passwall2","p2s":"passwall2","ocr":"openclash","oct":"openclash","nkr":"nikki","nkt":"nikki","hpr":"homeproxy","hpt":"homeproxy"}
previous=sys.argv[1]
Path("/tmp/pg-latest-login.json").write_text(json.dumps({"password":""}))
# The fixture uses the existing blank root password; successful login is checked by the native session API.
expected=json.loads(Path("/tmp/pg-final-runtime-manifest.json").read_text())
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in expected["files"].items())
boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
results=[]
for case in sys.argv[2:]:
 out=D/case;out.mkdir(exist_ok=True)
 if (out/"complete.json").exists():raise RuntimeError("Do not overwrite an existing case")
 (D/"current.json").write_text(json.dumps({"case":case,"phase":"preparing","started":time.time()}))
 began=time.monotonic();result={"ok":False,"case":case,"boot_id":boot_id};capture=None;capture_log=None
 try:
  session=json.loads(cmd("ubus","call","session","login",json.dumps({"username":"root","password":""})).stdout)["ubus_rpc_session"]
  cmd("ubus","call","uci","set",json.dumps({"ubus_rpc_session":session,"config":"proxy_guard","section":"main","values":{"enabled":"0"}}))
  applied=json.loads(cmd("ubus","-t","60","call","proxy_guard","apply",json.dumps({"ubus_rpc_session":session,"confirm_flow":True}),timeout=75).stdout)
  assert applied.get("ok")is True,("public disable RPC",applied)
  off_until=time.monotonic()+60
  while time.monotonic()<off_until:
   state=json.loads(cmd("ubus","call","proxy_guard","status","{}").stdout)
   if state.get("enforcement")=="off":break
   time.sleep(.2)
  assert state.get("enforcement")=="off",("public disable state",state)
  cmd("ip","netns","exec","pgwan","nft","delete","table","inet","pg_fixture_outage",check=False)
  if previous:
   cmd("/etc/init.d/"+previous,"stop",timeout=240)
   cmd("/etc/init.d/"+previous,"disable",timeout=30)
  assert Path("/etc/init.d/"+names[case]).exists(),"upstream client not installed"
  # One upstream service at a time. A previous case never grants the next one.
  for path in [Path("/tmp/pg_latest_fixture.py"),Path("/tmp/pg_latest_guard_test.py"),Path("/tmp/pg_latest_matrix.py")]:
   (out/path.name).write_bytes(path.read_bytes())
  client(case);previous=names[case]
  if case=="ocr" and Path('/tmp/pg_packet_capture.py').is_file():
   capture_log=(out/'private-packet-capture.log').open('w')
   capture=subprocess.Popen(['python3','-u','/tmp/pg_packet_capture.py',str(out/'private-packets.json')],stdout=capture_log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
   ready=out/'private-packets.json.ready';until=time.monotonic()+15
   while not ready.exists():
    assert capture.poll()is None,'mandatory packet capture process failed'
    assert time.monotonic()<until,'mandatory packet capture readiness timeout'
    time.sleep(.1)
  elif case=="ocr"and shutil.which("tcpdump"):
   capture_log=(out/"private-dns-udp-packets.log").open("w")
   capture=subprocess.Popen(["ip","netns","exec","pgwan","tcpdump","-i","any","-l","-tt","-nn","udp or tcp port 53 or tcp port 23456 or tcp port 18080"],stdout=capture_log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)

  (D/"current.json").write_text(json.dumps({"case":case,"phase":"testing","started":time.time()}))
  for file in ["/tmp/pg-integration-result.json","/tmp/pg-runtime71.json","/tmp/pg-first-blocked-status.json","/tmp/pg-completed-failure-status.json","/tmp/pg-native-status-history.jsonl","/tmp/pg-native-dns-history.jsonl","/tmp/pg-native-flow-history.jsonl"]:Path(file).unlink(missing_ok=True)
  with(out/"test.log").open("w")as log:
   p=subprocess.run(["python3","-u","-B","/tmp/pg_latest_guard_test.py",case,names[case]],stdout=log,stderr=subprocess.STDOUT,timeout=1400)
  result=json.loads(Path("/tmp/pg-integration-result.json").read_text())if Path("/tmp/pg-integration-result.json").exists()else result
  result["process_rc"]=p.returncode;result["ok"]=p.returncode==0 and result.get("ok")is True
 except Exception:result["error"]=traceback.format_exc()
 finally:
  if capture is not None:
   capture.terminate()
   try:capture.wait(timeout=5)
   except subprocess.TimeoutExpired:capture.kill();capture.wait(timeout=5)
   capture_log.close()
  for src in [Path("/tmp/pg-upstream-ready.json"),Path("/tmp/pg-runtime71.json"),Path("/tmp/pg-first-blocked-status.json"),Path("/tmp/pg-completed-failure-status.json"),Path("/tmp/pg-native-status-history.jsonl"),Path("/tmp/pg-native-dns-history.jsonl"),Path("/tmp/pg-native-flow-history.jsonl")]:
   if src.exists():(out/src.name).write_bytes(src.read_bytes())
  # Capture upstream generated configuration and kernel rules at each case
  # boundary so a failed baseline remains diagnosable after the next client.
  native={}
  for path in Path('/tmp/etc/passwall').rglob('*.json'):
   if path.is_file() and path.stat().st_size<1000000:
    native[str(path)]=path.read_text(errors='replace')
  for directory in [Path('/etc/openclash'),Path('/etc/nikki/run')]:
   for path in directory.rglob('*'):
    if path.is_file()and path.suffix in ['.yaml','.yml','.json']and path.stat().st_size<1000000:native[str(path)]=path.read_text(errors='replace')
  for label,args in [('ruleset',['nft','list','ruleset']),('ip6-rules',['ip','-6','rule','show']),('ip6-routes',['ip','-6','route','show','table','all'])]:
   try:native[label]=cmd(*args,check=False,timeout=30).stdout
   except Exception as error:native[label]=str(error)
  (out/'upstream-kernel-snapshot.json').write_text(json.dumps(native,indent=2))
  result["total_seconds"]=time.monotonic()-began
  result["installed_file_sha256"]={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path("/usr/lib/proxy-guard/fast-watch.uc"),Path("/usr/lib/proxy-guard/firewall-sync.uc"),Path("/usr/lib/proxy-guard/clients.uc"),Path("/usr/lib/proxy-guard/core.lua"),Path("/usr/lib/proxy-guard/worker.lua")] if path.is_file()}
  (out/"complete.json").write_text(json.dumps(result,indent=2))
  results.append({"case":case,"ok":result["ok"],"checks":len(result.get("checks",[])),"error":result.get("error")})
  (D/"results.json").write_text(json.dumps(results,indent=2))
  print(json.dumps(results[-1]),flush=True)
(D/"current.json").write_text(json.dumps({"phase":"finished","finished":time.time()}))

(D/"complete.json").write_text(json.dumps({"ok":len(results)==len(sys.argv[2:]) and all(r["ok"]for r in results),"candidate":"candidate8","cases":results},indent=2))
