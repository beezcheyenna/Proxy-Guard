# 兼容性测试矩阵

[English](TEST-MATRIX.en.md) · [简体中文](TEST-MATRIX.md) · [日本語](TEST-MATRIX.ja.md) · [Русский](TEST-MATRIX.ru.md) · [فارسی](TEST-MATRIX.fa.md)

以下场景使用 Proxy Guard 1.0.0-r7 在 x86_64 隔离虚拟机中完成。测试使用真实的 LuCI、SOCKS、TLS 和 nftables，HTTPS 响应由隔离环境中的测试服务提供。

测试日期为 2026-11-14（UTC+08:00）。

| 路由器固件 | 内核 | 测试项目 | 结果 |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK 安装、配置保留、重启与卸载。LuCI 保存并应用、确认超时、回退、代理诊断与清空日志。 | 通过 |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK 安装、配置保留、重启与卸载。HTTPS 和出口 IPv4 校验、TLS 回退、内网 API、限时与定时阻断，以及真实 IPv4/IPv6 TCP/UDP 的阻断和恢复。 | 通过 |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | PassWall 26.11.3-r1。短时防火墙争锁、许可停止续期后到期、防火墙重载，以及 IPv4/IPv6 TCP 和 UDP 的阻断与恢复。 | 通过 |

结果适用于表中列出的配置与流量路径。其他固件、架构和转发方式请在目标路由器上核验。

[兼容范围与限制](COMPATIBILITY.md)
