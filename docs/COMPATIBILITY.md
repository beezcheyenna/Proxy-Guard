# 兼容范围与限制

[English](COMPATIBILITY.en.md) · [简体中文](COMPATIBILITY.md) · [日本語](COMPATIBILITY.ja.md) · [Русский](COMPATIBILITY.ru.md) · [فارسی](COMPATIBILITY.fa.md)

使用 LuCI、firewall4 和 nftables。OpenWrt 24 使用 IPK，OpenWrt 25.12 使用 APK。iStoreOS 和 ImmortalWrt 按各自固件的包管理器及内核依赖选择。

保护覆盖实际经过路由器的流量。扩大范围前先用一台设备核对入口、IPv4 和 IPv6 路径、DNS 和管理访问。同网段旁路由的回程可能绕开本机。

默认通过本机 SOCKS 请求固定的官方 HTTPS 地址。第三方 HTTPS 可单独选择，间隔与阈值独立。出口 IPv4 校验初始关闭，开启后默认读取官方响应里的地址。使用第三方 IP 服务时，主地址超时才尝试备用地址。

请按客户端支持的转发方式配置，并在受保护设备上核对 IPv4 和 IPv6 的实际路径。[测试矩阵](TEST-MATRIX.md)列出了固件、代理客户端和转发组合，也收录了 1.0 发布包的专项结果。

| 代理客户端 | 转发方式 | 配置要点 |
| --- | --- | --- |
| PassWall | TCP REDIRECT + UDP TPROXY，或 TCP/UDP TPROXY | 需要代理 IPv6 时，在客户端开启 IPv6 TPROXY。经路由转发的 IPv6 流量单独核验。 |
| PassWall2 | TCP/UDP TPROXY | 核对实际生效的本机 SOCKS 监听。其他转发方式按设备配置验证。 |
| OpenClash | REDIRECT + TPROXY，或 TUN | 保留 SOCKS 认证。需要代理 IPv6 UDP 时，在客户端启用对应选项。 |
| Nikki | REDIRECT + TPROXY，或 TUN | 保留已配置的 SOCKS 认证，并核对所选模式的 IPv4 和 IPv6 流量。 |
| HomeProxy | REDIRECT + TPROXY，或 system TUN | 在已安装的 sing-box 和固件上核对 IPv6 UDP。 |

代理内核会影响检测和转发结果。NaiveProxy 不提供 UDP 中继。仅监听 IPv4 的服务无法证明 IPv6 已走代理。排查 Xray SOCKS5 UDP 时，可在关闭保护的对照环境中核对实际内核和转发模式。

需要代理 IPv6 UDP 时，请确认实际的 UDP 流量走代理。TCP 已走代理或 SOCKS 握手成功，只能说明各自的通路可用。

LuCI 插件支持英语、简体中文、日语、俄语和波斯语。固件主题和其他插件使用各自的语言包。[客户端日志适配](LOG_COMPATIBILITY.zh-CN.md)

## 保护模式的环境条件

以下情况会阻止确认保护，插件不会擅自代改系统设置：

- UCI 开启软件或硬件流量卸载，或运行规则仍存在 nft flowtable。
- `bridge-nf-call-iptables` / `bridge-nf-call-ip6tables` 把纯交换流量送进 IP 防火墙，可能影响其他网关设备。
- 无法核验入口设备、内核能力、桥接状态或已安装策略。

平台私有硬件加速、交换芯片旁路和厂商快转仍需实机检查。已验证的无 NAT 用例要求回程明确经过测试路由器；同网段旁路由可能只有出站经过本机，绕过本机的回复无法拦截。仅经交换使用其他网关的设备不应被误伤。跨网段 LAN、VPN、容器、多个桥与 IPv6 默认路由必须按实际拓扑核对。
