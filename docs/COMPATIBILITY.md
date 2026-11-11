# 兼容范围与限制

本项目已进行安装、升级、LuCI/RPC、故障阻断、恢复和冷启动等功能测试。下文列出支持条件与已知限制。包名中的 `all` 表示脚本包，不代表任意硬件、内核和架构都可直接使用。

## 路由器与客户端

本版要求路由器使用 LuCI 和 firewall4/nftables；opkg 固件安装 IPK，apk 固件安装由匹配 SDK 生成的 APK，依赖包与内核模块须来自匹配的固件软件源。已进行安装、升级、故障阻断、恢复和冷启动等功能测试，兼容模式与已知限制见下表。

| 客户端 | 已纳入验证的模式 | 必须注意 |
| --- | --- | --- |
| PassWall / Xray、sing-box | TCP redirect + UDP tproxy；TCP/UDP tproxy | IPv6 代理须开启上游支持的 IPv6 TPROXY；本轮 REDIRECT 用例的 IPv6 是受保护的直连路由，不能算作 IPv6 代理验收 |
| PassWall2 / Xray、sing-box | tproxy | redirect 等其他组合须单独验证，不能从 tproxy 结果推定 |
| OpenClash / Mihomo | redirect + tproxy、TUN | 保留实际 SOCKS 认证；关闭服务监视不应丢失连接认证。IPv6 UDP 代理需在上游明确启用，已验证其 TPROXY 与 TUN 路径。未启用时 IPv6 UDP 可能走路由直连，直连阻断结果不能当作代理路径通过 |
| Nikki / Mihomo | redirect + tproxy、TUN | 保留默认 SOCKS 认证，按所选模式检查 |
| HomeProxy / sing-box | redirect + tproxy、system TUN | 新版官方 sing-box 1.14.4 已重新进行真实 IPv4/IPv6 TCP/UDP 检查，不再使用旧 sing-tun 补丁 |
| PassWall / 原生 Hysteria2、Shadowsocks-Rust、NaiveProxy | 原生监听识别、受支持路径的故障阻断与恢复 | 已验证 Hysteria2、Shadowsocks-Rust、Naive HTTPS 与 QUIC；NaiveProxy 不提供 UDP 代理，其测试中的 IPv6 为受保护直连。Shadowsocks-Rust 的默认 IPv4 监听不能视为已支持 IPv6 代理 |
| PassWall / sing-box ShadowTLS v3 客户端 + 原生 ShadowTLS 服务端 | 实际 TCP 代理通流、故障阻断与恢复 | 已使用有效私有测试证书验证 TLS，未关闭证书校验。UDP 是独立的受保护路由流量，不代表 ShadowTLS 提供 UDP 传输 |
| 原生 ShadowTLS 客户端 | 进程与端口检查 | 官方内置公共根不信任本轮私有测试 CA；原生客户端尚未完成端到端验收，不从 sing-box 客户端结果推定 |

依赖与内核模块必须匹配固件来源。内核版本号和包管理器中的 ABI 标记相同，也不能据此混用不同厂商的内核模块；不要用离线包全集覆盖固件自带模块。

已在未安装 Proxy Guard 的环境中复现：Xray 26.11.9 作为 SOCKS5 UDP 上游时，多个关联同时存活可能产生重复的临时 UDP 监听端口和请求超时。该组合不能视为稳定 UDP 转发验收通过；这不等于 Xray 的其他传输协议均有此问题，也不应通过关闭 UDP 检测来掩盖已经存在的链路故障。

插件不会自动替换代理内核。界面版本、已安装软件包版本和实际运行的内核版本应分别核对。历史版本或不同核心配置的测试结果不自动适用于新版组合。

功能测试涵盖新建和已有的 IPv4/IPv6 TCP/UDP 流量、故障阻断与恢复、增强监测中再次故障，以及 DNS、管理和路由器本机访问的保留。

IPK 与 APK 不能互换。本轮覆盖 OpenWrt、ImmortalWrt、iStoreOS 的 24 系列与 25.12 系列；仍不支持仅有 fw3/iptables 的固件。其他固件、内核和 CPU 架构需要核对所需能力与实际流量路径。

## LuCI 语言与主题

插件提供中文、英语、日语、俄语和波斯语。iStoreOS 24 的 Argon 主题与 PassWall2 26.11.3-r1 共存时，已观察到 LuCI 选择“自动”后被 PassWall2 的语言初始化改成英语。可在 LuCI 的系统设置中明确选择语言；五种语言下的普通版和 Pro 页面已分别检查。系统菜单和其他插件的翻译仍由各自语言包提供。

## VPS Agent

Linux Agent 已进行 Ubuntu、Debian、Rocky Linux 和 Alpine Linux 的兼容测试，覆盖安装、配置保留、认证 API、IPv4/IPv6 TCP/UDP 和受支持的维护操作。对接的 3x-ui / Xray 版本与适配器须匹配，不能将面板版本等同于代理内核版本。

需要 Python 3.10+、nftables、动态集合、速率限制及 connlimit 表达式和匹配内核模块。安装前通过 `--check-kernel` 检查；支持 systemd 和 Alpine OpenRC。仅管理本机 INPUT 的已选择端口，部分已确认回落流限速还匹配相应 OUTPUT 回复；不修改 NAT/FORWARD。Docker 发布端口、其他网络命名空间及上游安全组不在此范围。

Pro 只管理明确启用的选定端口。自动发现只提供候选；SSH 和维护动作单独选择、单独授权。SNI/REALITY 配置检查不能证明访客已认证；精确回落限速需要可信且新鲜的结构化数据源，缺失时不能猜测分类。

## 保护模式的环境条件

以下情况会阻止确认保护，插件不会擅自代改系统设置：

- UCI 开启软件或硬件流量卸载，或运行规则仍存在 nft flowtable。
- `bridge-nf-call-iptables` / `bridge-nf-call-ip6tables` 把纯交换流量送进 IP 防火墙，可能影响其他网关设备。
- 无法核验入口设备、内核能力、桥接状态或已安装策略。

平台私有硬件加速、交换芯片旁路和厂商快转仍需实机检查。已验证的无 NAT 用例要求回程明确经过测试路由器；同网段旁路由可能只有出站经过本机，绕过本机的回复无法拦截。仅经交换使用其他网关的设备不应被误伤。跨网段 LAN、VPN、容器、多个桥与 IPv6 默认路由必须按实际拓扑核对。

## 检测和自动恢复的边界

HTTPS 连通性、可选出口 IPv4、服务进程与可选 IPv4 DNS UDP 路径是不同检查。一个成功目标不能证明所有应用、UDP 目标或 IPv6 代理出口正常。新装出口 IPv4 校验默认关闭，升级保留原有选择。

服务约每秒采样，日志按配置的 1–10 秒增量读取；短于采样周期的波动可能漏过。日志适配以审查过的上游消息、时间戳及生命周期为依据，不能保证任意分支、翻译或未来版本都被识别。界面五种语言与上游日志的实际语言是两回事，详见 [运行日志兼容说明](LOG_COMPATIBILITY.md)。无效时钟不能用于日志恢复确认；定时使用固定 UTC 偏移，不自动跟随夏令时。

procd 负责进程退出后拉起，插件独立守护对心跳异常有限重启，只重启本插件。正常代理断线不作为重启插件的依据。长时间关闭后再启用会重新给予启动宽限期；超过恢复预算时保持保护并提示检查。文件系统、内核、调度、procd 或守护本身也失效时不能保证自愈。日志位于 RAM，但系统日志是否另存闪存仍由系统配置决定。

## 部署时需要确认

物理网卡、硬件加速、非对称回程、长期运行和新的上游客户端版本应在实际部署环境确认。家庭公网 IP 变化后，应检查新授权是否同步、旧授权是否过期；Cloudflare 配套还需核对实际绑定和连接状态。

新环境先仅监测，再用一台设备核对 LAN、DNS、管理、其他网关设备、IPv4/IPv6、已有连接和故障恢复；保留本地管理/控制台后再验收开机保护。
