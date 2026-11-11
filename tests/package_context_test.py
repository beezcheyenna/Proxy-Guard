#!/usr/bin/env python3
"""Native /proc ancestor classification; the parent only forks ucode.
No package manager operations or network changes are performed by this test.
"""
from pathlib import Path
import argparse,subprocess,os,json
assert Path("/etc/pgvm-fixture").is_file()
p=argparse.ArgumentParser();p.add_argument("--parent",required=True);a=p.parse_args()
env=os.environ.copy();env["PG_CONTEXT_SCRIPT"]="/usr/lib/proxy-guard/opkg-context.uc"
cases=[
 ("opkg",["install","remove"],0),
 ("opkg",["--force-reinstall","install","luci-app-proxy-guard"],0),
 ("opkg-cl",["-f","install","remove","luci-app-proxy-guard"],2),
 ("opkg",["remove","install"],2),
 ("opkg",["list","install"],75),
 ("apk",["add","del"],0),
 ("apk",["del","add"],2),
 ("apk",["--no-network","--allow-untrusted","fix","--reinstall","luci-app-proxy-guard"],0),
 ("apk",["--repository-config","add","del","luci-app-proxy-guard"],2),
 ("apk",["--repository-config=del","--no-network","add","pkg"],0),
 ("apk",["--root","del","add","pkg"],0),
 ("apk",["--preupgrade-depends","upgrade","--no-network","fix","pkg"],0),
 ("apk",["--uvol-manager","add","del","pkg"],2),
 ("apk",["--timeout","2","--no-network","del","pkg"],2),
 ("apk",["upgrade","del"],0),
 ("apk",["search","del"],75),
 ("unrelated-parent",["apk","add"],75),
]
for name,args,expected in cases:
 child=subprocess.Popen([name,*args],executable=a.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
 out,err=child.communicate(timeout=8)
 assert child.returncode==expected,(name,args,child.returncode,expected,out,err)
 if expected==0:
  fields=out.split();assert len(fields)==2 and int(fields[0])==child.pid and int(fields[1])>0
 else:assert not out.strip(),(name,args,out)
print("PASS native package-manager ancestor classification",len(cases),"cases")
