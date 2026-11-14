# 故障排查与恢复

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

**停止 Proxy Guard 服务后，防火墙规则可能仍在阻断。** 要解除插件的阻断，请按下文明确关闭保护。

**「测试当前代理」通过仅说明本次探测成功。** 定时保护、API 限时断网或另一路检测故障仍可能阻断外网。

## 查看恢复状态

状态区分别显示当前放行情况和最近一次完成的检测。规则待核验时，使用「检查配置与运行环境」查看具体原因。使用「测试当前代理」检查 SOCKS 通路。

代理连接失败时，检查客户端的本机 SOCKS 监听。防火墙重载或代理重启后，等待已配置的恢复检查。

测试恢复前，保留控制台或独立的管理通路。新配置导致失联时，等待确认超时。超时或在未确认期间重启，系统会恢复之前的配置。

如能通过控制台管理路由器，可用下面的命令明确关闭保护。确认执行状态为关闭，再从受保护客户端验证访问。

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery &&
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart &&
ubus call proxy_guard status
```

保护覆盖实际经过路由器的流量。扩大范围前先用一台设备核对入口、IPv4 和 IPv6 路径、DNS 和管理访问。同网段旁路由的回程可能绕开本机。

[安装与使用](USAGE.md)
