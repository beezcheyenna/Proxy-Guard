#!/bin/sh
set -eu
test -f /etc/pgvm-fixture
test "$(cat /proc/1/comm)" = procd
kill -STOP "$(cat /var/run/proxy-guard/daemon.pid)"
# Freezing the shell does not stop its already-running probe child. Wait for
# that child to release the lock before making the next manual round due.
ucode -e 'import * as fs from "fs"; let f=fs.open("/var/lock/proxy-guard.lock","a");let deadline=clock(true)[0]+30;while(!f.lock("xn")){assert(clock(true)[0]<deadline);sleep(50);} f.close();'
lua -e 'local j=require "luci.jsonc";local p="/var/run/proxy-guard/status.json";local f=assert(io.open(p));local s=j.parse(f:read("*a"));f:close();s.next_probe=0;f=assert(io.open(p..".new","w"));f:write(j.stringify(s));f:close();assert(os.rename(p..".new",p))'
# A separate session prevents shell job-control SIGHUP/SIGCONT after parent death.
setsid /usr/libexec/proxy-guard tick </dev/null >/tmp/pg014-orphan.log 2>&1 &
r=$!
printf '%s\n' "$r" >/tmp/pg014-runner.pid
for attempt in $(seq 1 200); do
 for child in $(ucode -e 'import * as fs from "fs"; for(let p in fs.glob("/proc/[0-9]*/stat") || []) {let m=match(fs.readfile(p)||"",/^(\d+) \(.+\) \S+ (\d+) /);if(m && m[2]==ARGV[0]) print(m[1]+"\n");}' "$r"); do
  if tr '\000' ' ' </proc/$child/cmdline | grep -q '/usr/lib/proxy-guard/main.lua tick'; then
   kill -STOP "$child"
   ucode -e 'import * as fs from "fs"; assert(match(fs.readfile("/proc/"+ARGV[0]+"/status") || "",/State:\s+T/));let f=fs.open("/var/lock/proxy-guard.lock","a");assert(!f.lock("xn"));' "$child"
   printf '%s\n' "$child" >/tmp/pg014-orphan.pid; kill -KILL "$r"
   ucode -e 'sleep(100)'
   ucode -e 'import * as fs from "fs";assert(match(fs.readfile("/proc/"+ARGV[0]+"/status")||"",/State:\s+T/));let f=fs.open("/var/lock/proxy-guard.lock","a");assert(!f.lock("xn"));' "$child"
   exit 0
  fi
 done
 ucode -e 'sleep(50)'
done
exit 1