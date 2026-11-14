# 兼容性测试矩阵

[English](TEST-MATRIX.en.md) · [简体中文](TEST-MATRIX.md) · [日本語](TEST-MATRIX.ja.md) · [Русский](TEST-MATRIX.ru.md) · [فارسی](TEST-MATRIX.fa.md)

本页列出 Proxy Guard 的路由器固件、代理客户端和转发模式兼容性。完整组合沿用 2026-11-11（UTC）的隔离测试结果。1.0 发布包的集成与 API 专项结果见下文。

## 路由器系统

以下六套系统均为 `x86_64`，每套覆盖下一节的 12 个主要客户端／模式组合。内核来自对应测试镜像，不是虚拟机宿主内核。

| 系统与精确版本 | 内核 | 包格式 | 测试日期 | 结果 |
| --- | --- | --- | --- | --- |
| OpenWrt 24.10.8，r29233-443ec4032a | 6.6.144 | IPK / opkg | 2026-11-11 | 12 组合通过 |
| ImmortalWrt 24.10.6，r33869-cf234f8de6d5 | 6.6.133 | IPK / opkg | 2026-11-11 | 12 组合通过 |
| iStoreOS 24.10.8-2026073111 | 6.6.144 | IPK / opkg | 2026-11-11 | 12 组合通过 |
| OpenWrt 25.12.6，r33311-981c978eff | 6.12.112 | APK / apk | 2026-11-11 | 12 组合通过 |
| ImmortalWrt 25.12.2，r38135-0c4cd0f9920a | 6.12.103 | APK / apk | 2026-11-11 | 11 组合首轮通过；OpenClash redirect 组合复测通过，见下文 |
| iStoreOS 25.12.6-2026110611 | 6.12.112 | APK / apk | 2026-11-11 | 12 组合通过 |

ImmortalWrt 25.12 的 OpenClash redirect 首轮在启用保护前的 IPv6 TCP 基线失败，保留了失败记录；随后完整重放该组合的 36 项检查通过。复测通过不抹去首次失败，也不证明任意网络波动都不存在。

## 客户端、内核与转发模式

本表版本对应上述隔离 VM 矩阵。客户端界面版本与实际代理内核版本分别列出。

| 客户端版本 | 内核版本 | 转发模式 | 组合数 |
| --- | --- | --- | --- |
| PassWall 26.11.3-r1 | Xray 26.11.9；sing-box 1.14.4 | 各自 TCP REDIRECT + UDP TPROXY；各自 TCP/UDP TPROXY | 4 |
| PassWall2 26.11.3-r1 | Xray 26.11.9；sing-box 1.14.4 | TCP/UDP TPROXY | 2 |
| OpenClash 0.48.002 | Mihomo 1.19.32 | redirect + tproxy；TUN | 2 |
| Nikki LuCI 1.26.2-r1，服务包 2026.10.10-r1 | Mihomo 1.19.32 | redirect + tproxy；TUN | 2 |
| HomeProxy 0.261002.28698 | sing-box 1.14.4 | redirect + tproxy；system TUN | 2 |

主要测试项目：原生安装与 RPC 应用确认、真实客户端监听与身份、IPv4/IPv6 TCP/UDP 新连接及已有连接、故障阻断、服务停止／重启、恢复等待与 60 秒增强监测、增强监测中再次故障、LAN/DNS/管理和路由器本机流量保留。OpenClash、Nikki 还检查实际 SOCKS 认证文件。

另有安装与卸载、冷启动、日志解析与轮转、配置试运行回退、LuCI 五种语言、权限与错误处理的专项检查。上游日志语言覆盖见[日志适配](LOG_COMPATIBILITY.zh-CN.md)。

### 其他内核与补测

| 组合或项目 | 精确版本 | 环境／日期 | 结果与范围 |
| --- | --- | --- | --- |
| PassWall / Hysteria2 | 2.13.0 | ImmortalWrt 24.10.6 / 25.12.2，2026-11-11 | 原生程序、支持路径的阻断与恢复已验证 |
| PassWall / Shadowsocks-Rust | 1.25.0 | ImmortalWrt 24.10.6 / 25.12.2，2026-11-11 | 已验证；默认 IPv4 监听不代表 IPv6 代理通过 |
| PassWall / NaiveProxy | 154.0.8037.49，包修订 r5；ImmortalWrt 25 包为 154.0.8037.49.5-r1 | ImmortalWrt 24.10.6 / 25.12.2，2026-11-11 | HTTPS、QUIC 支持路径已验证；不提供 UDP 代理 |
| PassWall / sing-box ShadowTLS v3 客户端 → 原生 ShadowTLS 服务端 | sing-box 1.14.4；shadow-tls 0.2.25 | ImmortalWrt 24.10.6、ImmortalWrt 25.12.2，2026-11-11 | 实际 TCP 通流、链路故障阻断、恢复与增强监测通过；使用有效私有测试 CA，未关闭 TLS 校验 |
| 原生 ShadowTLS 客户端 | shadow-tls 0.2.25 | 同上 | **端到端未验收**：官方内置根不信任该私有测试 CA，不能用 sing-box 结果代替 |
| Xray SOCKS5 UDP 多个并发关联 | Xray 26.11.9 | 不安装 Proxy Guard 的对照环境，2026-11-11 | **已复现上游临时 UDP 端口冲突**；该组合不能列为稳定 UDP 代理通过 |

REDIRECT 用例中的 IPv6、NaiveProxy 不支持的协议和 ShadowTLS 补测中的 UDP，可能是受保护的路由流量。**路由流量被阻断，不等于该代理协议已支持或成功代理了这些流量。** HomeProxy 新版测试未使用旧 sing-tun 补丁；OpenClash 的 IPv6 UDP 代理还要求启用对应上游能力。

## 1.0.0-7 / 1.0.0-r7 集成测试

以下场景在 x86_64 隔离虚拟机中完成，使用 Proxy Guard `1.0.0-7`（IPK）或 `1.0.0-r7`（APK）。测试使用真实的 LuCI、SOCKS、TLS 和 nftables，HTTPS 响应由隔离环境中的测试服务提供。

测试日期为 2026-11-14（UTC+08:00）。

| 路由器固件 | 内核 | 测试项目 | 结果 |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK 安装、配置保留、重启与卸载。LuCI 保存并应用、确认超时、回退、代理诊断与清空日志。 | 通过 |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK 安装、配置保留、重启与卸载。HTTPS 和出口 IPv4 校验、TLS 回退、内网 API、限时与定时阻断，以及真实 IPv4/IPv6 TCP/UDP 的阻断和恢复。 | 通过 |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | PassWall 26.11.3-r1。短时防火墙争锁、许可停止续期后到期、防火墙重载，以及 IPv4/IPv6 TCP 和 UDP 的阻断与恢复。 | 通过 |

结果适用于表中列出的配置与流量路径。其他固件、架构和转发方式请在目标路由器上核验。

### 覆盖安装与重装检查

- **IPK `1.0.0-6` → `1.0.0-7`。** LuCI 测试环境完成换包。opkg 保留修改过的 `/etc/config/proxy_guard`，把新包的默认配置写到 `/etc/config/proxy_guard-opkg`。
- **APK `1.0.0-r7` → `1.0.0-r7`。** OpenWrt 25.12.6 测试环境重装同一修订，执行了升级钩子并核对安装文件。

已发布的 0.3 包直接覆盖到 1.0，以及从 1.0 降回 0.3，均未作为迁移路径验收。 [迁移说明](USAGE.md#from-0-3)

## 1.0.0-8 / 1.0.0-r8 API 专项测试

2026-11-14（UTC+08:00），使用对应的最终安装包，在 x86_64 隔离虚拟机中完成下列检查。测试包的校验值与[发布清单](https://github.com/beezcheyenna/Proxy-Guard/releases/download/v1.0.0/SHA256SUMS)一致。

| 路由器固件 | 内核 | 安装包 | 结果 |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK | 65 项通过 |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK | 65 项通过 |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | IPK | 65 项通过 |

r8 检查覆盖 UUID 认证、关闭再开启后的轮换、UUID 和 API 日志的管理员权限、诊断直返、随机数校验、原始标头、超时和冷却，以及 IPv4/IPv6 TCP、UDP 的实际流量阻断（含已有连接）。还验证了限时请求到期、同 ID 重试以及撤回后其他保护继续生效。HTTPS 响应由本地测试服务提供。

[兼容范围与限制](COMPATIBILITY.md)
