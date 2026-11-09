package.path=(os.getenv('PG_SOURCE') or '/src')..'/package/root/usr/lib/?.lua;'..package.path
local m=require 'proxy-guard.resource-metrics';local n=0
local function check(v,why) assert(v,why);n=n+1 end
local total,cores=m.cpu_snapshot('cpu 100 20 30 400 5 6 7 8 50 10\ncpu0 1 2 3 4\ncpu1 1 2 3 4\n')
check(total==576 and cores==2,'guest counters are not counted twice')
for _,s in ipairs({'','cpu 1 2 3 4\ncpu0 1\n','cpu 1 2 3 4 5 6 7 8\n','cpu 1 2 -3 4 5 6 7 8\ncpu0 1\n','cpu 1 2 junk 4 5 6 7 8 9 10\ncpu0 1\n','cpu 1 2 3.5 4 5 6 7 8\ncpu0 1\n'}) do check(m.cpu_snapshot(s)==nil,'invalid CPU input waits for a sample') end
local function sample(c,t,u,identity,up) return {cpu_cores=c,system_ticks=t,cpu_ticks=u,identity=identity or 'root:1',sample_uptime=up or 10,cpu_basis='all_online_cpus'} end
for _,case in ipairs({{1,100,25,25,25},{4,400,100,25,100},{20,2000,40,2,40},{20,2000,2000,100,2000},{64,6400,64,1,64}}) do
 local before=sample(case[1],1000,100,nil,5);local after=sample(case[1],1000+case[2],100+case[3])
 local overall,one=m.cpu_usage(before,after);check(overall==case[4] and one==case[5],'aggregate CPU capacity '..case[1])
end
local before=sample(4,1000,100,nil,5)
for _,after in ipairs({sample(8,2000,200),sample(4,2000,200,'new:2'),sample(4,1000,200),sample(4,2000,99),sample(4,2000,200,nil,4)}) do check(m.cpu_usage(before,after)==nil,'counter restart/hotplug/stale sample cannot show a false number') end
before.cpu_basis=nil;check(m.cpu_usage(before,sample(4,2000,200))==nil,'upgrade from single-core accounting starts a fresh sample')
check(m.cpu_usage(nil,sample(4,2000,200))==nil,'first sample is pending')
print('PASS '..n..' multi-core resource accounting assertions')
