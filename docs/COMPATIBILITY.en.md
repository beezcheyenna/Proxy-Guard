# Compatibility and limits

[English](COMPATIBILITY.en.md) · [简体中文](COMPATIBILITY.md) · [日本語](COMPATIBILITY.ja.md) · [Русский](COMPATIBILITY.ru.md) · [فارسی](COMPATIBILITY.fa.md)

See the [test matrix](TEST-MATRIX.en.md) for exact firmware and OS versions, kernels, architectures, clients, dates, and outstanding verification. Functional tests covered installation, upgrades, LuCI/RPC, outage blocking, recovery, and cold boot. The `all` package label identifies a script package.

## Routers and clients

The router needs LuCI and firewall4/nftables. Use IPK with opkg and APK built with the matching SDK with apk. Install dependencies and kernel modules from the matching firmware feeds. Matching kernel versions or ABI labels alone do not justify mixing vendor modules or replacing firmware modules with an offline bundle.

| Client | Tested mode or scope | Conditions |
| --- | --- | --- |
| PassWall / Xray, sing-box | TCP REDIRECT + UDP TPROXY, TCP/UDP TPROXY | Enable upstream IPv6 TPROXY for IPv6 proxying. The tested IPv6 traffic in REDIRECT mode was protected routed traffic. |
| PassWall2 / Xray, sing-box | TPROXY | Test REDIRECT and other combinations separately. |
| OpenClash / Mihomo | REDIRECT + TPROXY, TUN | Retain SOCKS authentication even with service monitoring disabled. Explicitly enable IPv6 UDP proxying. TPROXY and TUN were tested. Without it, IPv6 UDP may route directly. |
| Nikki / Mihomo | REDIRECT + TPROXY, TUN | Retain default SOCKS authentication and verify the chosen mode. |
| HomeProxy / sing-box | REDIRECT + TPROXY, system TUN | IPv4/IPv6 TCP and UDP were retested with official sing-box 1.14.4, without the old sing-tun patch. |
| PassWall / Hysteria2, Shadowsocks-Rust, NaiveProxy | Native listener recognition, blocking and recovery on supported paths | Tested Hysteria2, Shadowsocks-Rust, and NaiveProxy over HTTPS and QUIC. NaiveProxy has no UDP relay. Its IPv6 cases covered protected routed traffic. The default Shadowsocks-Rust IPv4 listener does not cover IPv6 proxying. |
| PassWall / sing-box ShadowTLS v3 → ShadowTLS | Proxied TCP, blocking and recovery | TLS verification used a valid private test CA. The UDP checks exercised a separate protected routed path. |
| ShadowTLS | Process and listener checks for the native client | The stock client did not trust the private lab CA. End-to-end verification for that client remains open. |

In a lab without Proxy Guard, concurrent Xray 26.11.9 upstream SOCKS5 UDP associations reused temporary UDP ports and timed out. Treat that combination as unverified for stable UDP forwarding. Keep UDP checks enabled when investigating the failure. Other Xray transports require their own evidence.

Verify the UI version, installed package version, and running core separately. The plugin leaves proxy core installation to the client. The tested firmware families are OpenWrt, ImmortalWrt, and iStoreOS 24 and 25.12. Use the correct package format. Firmware with only fw3/iptables is unsupported. Test the actual path on other firmware, kernels, and architectures.

Traffic checks included new and established IPv4/IPv6 TCP/UDP sessions, failures during enhanced monitoring, and preservation of DNS, management, and router-originated access.

## LuCI languages and themes

LuCI pages are available in Simplified Chinese, English, Japanese, Russian, and Persian for both editions. With Argon on iStoreOS 24, PassWall2 26.11.3-r1 was observed resetting LuCI's Auto language to English. Select a language explicitly in LuCI system settings. Firmware menus and other plugins use their own catalogs.

## VPS Agent

Ubuntu, Debian, Rocky Linux, and Alpine Linux tests covered installation, configuration retention, the authenticated API, IPv4/IPv6 TCP/UDP, and supported maintenance. Match the 3x-ui and Xray versions and the adapter.

The Agent needs Python 3.10+, nftables, dynamic sets, rate limits, connlimit, and matching kernel modules. Run `--check-kernel` before installation. systemd and Alpine OpenRC are supported. The Agent handles selected local INPUT ports and some corresponding OUTPUT replies for confirmed fallback rate limiting. NAT, FORWARD, Docker published ports, other namespaces, and upstream security groups are outside that scope.

Discovery suggests ports. Select them explicitly and authorize SSH management and maintenance separately. SNI/REALITY configuration alone does not establish authentication. Precise fallback rate limits require trusted, fresh structured telemetry.

## Protection mode prerequisites

Confirmation is blocked when software or hardware offload is enabled in UCI or an nft flowtable remains active, when `bridge-nf-call-iptables` or `bridge-nf-call-ip6tables` sends pure switched traffic through the IP firewall, or when ingress, kernel, bridge state, or the installed policy cannot be verified. Review those settings on the device.

Check vendor acceleration and switch-chip bypass on hardware. Verified no-NAT cases had a return path through the router. A same-subnet gateway may see only outbound traffic. Devices using another gateway over switching should remain unaffected. Inspect inter-subnet LANs, VPNs, containers, multiple bridges, and the IPv6 default route in your topology.

## Detection and automatic recovery limits

HTTPS, optional IPv4 egress validation, service checks, and optional IPv4 DNS UDP probes cover different paths. A successful probe establishes only the measured path. IPv4 egress validation defaults to off for new installs and keeps its configured value during upgrades.

Services are sampled about once a second and logs incrementally every 1–10 seconds as configured. Short transients can escape sampling. Recognition depends on reviewed messages, timestamps, and lifecycle stages. An invalid clock prevents log-based recovery. Schedules use a fixed UTC offset. See [runtime log compatibility](LOG_COMPATIBILITY.md).

procd restarts exited processes. The plugin watchdog can perform limited restarts of the plugin after heartbeat failures. An ordinary proxy outage follows the protection flow. After a long disabled period, re-enabling allows a new startup grace period. When retries are exhausted, protection stays in effect and the UI requests inspection. Automatic recovery depends on the filesystem, kernel, scheduler, procd, and watchdog. Plugin logs use RAM, while system logging follows firmware settings.

## Deployment checklist

Verify physical NICs, acceleration, asymmetric routing, long runs, and new client versions in the deployment. After the home public IP changes, check the new lease and expiry of the old one. For Cloudflare, also inspect the binding and connection. Start in monitoring mode with one device. Check LAN, DNS, management, other gateways, IPv4/IPv6, established connections, and recovery. Keep a management path or console available before testing boot protection.
