# Compatibility test matrix

[English](TEST-MATRIX.en.md) · [简体中文](TEST-MATRIX.md) · [日本語](TEST-MATRIX.ja.md) · [Русский](TEST-MATRIX.ru.md) · [فارسی](TEST-MATRIX.fa.md)

These are the combinations actually exercised. Current release: Standard `0.3.0-21` and Pro `0.3.1-5`. See [compatibility](COMPATIBILITY.en.md) and the [edition matrix](EDITION-MATRIX.en.md).

## How to read the results

- **Mocks and unit tests** substitute clocks, interfaces, or system calls to check parsing and transitions.
- **Isolated VM integration** runs the guest kernel, init, package manager, and real proxy programs with controlled peers. Pass applies to the listed cases.
- **Deployment acceptance** covers actual hardware, physical NICs, switching, ISP paths, asymmetric return routes, and sustained load.
- **Cloud integration** covers live Worker/Tunnel authentication and control. Data forwarding and cold boot have separate checks.

Dates are UTC. Historical Linux dates are the saved result dates. Installation, starting a process, or opening a page alone does not establish functionality.

## Router systems

All six guests are `x86_64` and each exercises the 12 client/mode combinations below. Kernel versions are from the guests.

| System and revision | Kernel | Packages | Date | Result |
| --- | --- | --- | --- | --- |
| OpenWrt 24.10.8, r29233-443ec4032a | 6.6.144 | IPK / opkg | 2026-11-11 | 12 passed |
| ImmortalWrt 24.10.6, r33869-cf234f8de6d5 | 6.6.133 | IPK / opkg | 2026-11-11 | 12 passed |
| iStoreOS 24.10.8-2026073111 | 6.6.144 | IPK / opkg | 2026-11-11 | 12 passed |
| OpenWrt 25.12.6, r33311-981c978eff | 6.12.112 | APK / apk | 2026-11-11 | 12 passed |
| ImmortalWrt 25.12.2, r38135-0c4cd0f9920a | 6.12.103 | APK / apk | 2026-11-11 | 11 passed first; OpenClash REDIRECT passed a rerun |
| iStoreOS 25.12.6-2026110611 | 6.12.112 | APK / apk | 2026-11-11 | 12 passed |

The complete 12-combination run used Standard `0.3.0-20` candidate C10 with Pro `0.3.1-5`. C11 added targeted runtime-log recovery checks. Standard `0.3.0-21` fixed the status shown when the kernel was already blocking and had targeted regressions, packaging, and UI checks.

The first ImmortalWrt 25.12 OpenClash REDIRECT run failed its IPv6 TCP baseline before protection was enabled. All 36 checks passed on a full replay of that combination. The original failure is retained.

## Clients, cores, and forwarding modes

| Client version | Core | Mode | Combinations |
| --- | --- | --- | --- |
| PassWall 26.11.3-r1 | Xray 26.11.9 / sing-box 1.14.4 | TCP REDIRECT + UDP TPROXY / TCP/UDP TPROXY | 4 |
| PassWall2 26.11.3-r1 | Xray 26.11.9 / sing-box 1.14.4 | TCP/UDP TPROXY | 2 |
| OpenClash 0.48.002 | Mihomo 1.19.32 | REDIRECT + TPROXY / TUN | 2 |
| Nikki LuCI 1.26.2-r1 / Nikki 2026.10.10-r1 | Mihomo 1.19.32 | REDIRECT + TPROXY / TUN | 2 |
| HomeProxy 0.261002.28698 | sing-box 1.14.4 | REDIRECT + TPROXY / system TUN | 2 |

Tests covered native install and confirmed RPC apply, real listeners and identities, new and existing IPv4/IPv6 TCP/UDP connections, outages, service stops/restarts, recovery and 60 seconds of enhanced monitoring, a repeat outage in that period, and continued LAN/DNS/management/router access. OpenClash and Nikki also used real SOCKS credentials.

Separate runs covered install/upgrade/removal, cold boot, log parsing/rotation, trial rollback, five LuCI languages, permissions, and errors. See [runtime log compatibility](LOG_COMPATIBILITY.md) for the upstream message languages.

### Additional cores and follow-up tests

| Combination | Version | Environment and date | Result and scope |
| --- | --- | --- | --- |
| PassWall / Hysteria2 | 2.13.0 | ImmortalWrt 24.10.6 / 25.12.2, 2026-11-11 | Native client, blocking and recovery on supported paths |
| PassWall / Shadowsocks-Rust | 1.25.0 | ImmortalWrt 24.10.6 / 25.12.2, 2026-11-11 | Supported paths passed. Default IPv4 listening does not establish IPv6 proxying. |
| PassWall / NaiveProxy | 154.0.8037.49-r5 / ImmortalWrt 25: 154.0.8037.49.5-r1 | ImmortalWrt 24.10.6 / 25.12.2, 2026-11-11 | HTTPS and QUIC passed. No UDP relay. |
| PassWall / sing-box ShadowTLS v3 → ShadowTLS | sing-box 1.14.4 / shadow-tls 0.2.25 | ImmortalWrt 24.10.6 / 25.12.2, 2026-11-11 | Proxied TCP, blocking, recovery and enhanced monitoring passed with a valid private test CA and TLS validation. |
| ShadowTLS (native) | 0.2.25 | ImmortalWrt 24.10.6 / 25.12.2, 2026-11-11 | End-to-end pending. Stock trust roots rejected the private CA. |
| Xray SOCKS5 UDP | 26.11.9 | Control lab without Proxy Guard, 2026-11-11 | Concurrent associations reproduced an upstream ephemeral UDP port collision. Stable UDP relay is unverified. |

IPv6 with REDIRECT, unsupported NaiveProxy protocols, and UDP in the ShadowTLS follow-up can use protected routed paths. HomeProxy used the current sing-box without the old sing-tun patch. OpenClash needs IPv6 UDP proxying enabled in the client.

## Linux VPS Agent

Historical `x86_64` isolated VM runs with native service management and nftables.

| Distribution | Guest kernel | Init | Cases | Saved result |
| --- | --- | --- | --- | --- |
| Ubuntu 24.04.5 LTS | 6.8.0-147-generic | systemd | A / B / C | Pass, 2026-11-02 |
| Debian 13.7 | 6.12.113+deb13-amd64 | systemd | A / B / C | Pass, 2026-11-02 |
| Rocky Linux 10.2 | 6.12.0-211.16.1.el10_2.0.1.x86_64 | systemd | A / B / C | Pass, 2026-11-02 |
| Alpine Linux 3.23.7 | 6.18.58-0-virt | OpenRC | A / B / C | Pass, 2026-11-02 |

- **A — Installation and policy:** native install and same-version reinstall, retained configuration and permissions, authenticated API, three port modes, IPv4/IPv6 TCP/UDP, and unrelated rules preserved.
- **B — Live proxy and maintenance:** 3x-ui **3.11.0** and **Xray 26.10.21** passed VLESS traffic, listeners, authorized core restart, and recovery. The retained VM binary matched the checked 3x-ui archive by SHA256.
- **C — Lifecycle:** startup after authorized reboot, pending policy rollback, deduplication, removal/reinstall, and preservation of 3x-ui and other firewall rules.

The recorded `agent.py` SHA256 is `3896c1c2d528aab70a9e071ab7c23a18831bfe5f111d906da5925e1af4689d90` and the protocol is v3. Use compatible Agent/Worker release source and verify new capabilities. The Agent manages selected local INPUT ports. Docker mappings, other namespaces, upstream security groups, and unlisted systems are outside these results.

## Recovery procedure checks

The 2026-11-12 UTC follow-up exercised the procedures in the [recovery guide](RECOVERY.en.md).

| Environment | Check | Result |
| --- | --- | --- |
| OpenWrt 24.10.8 / 6.6.144 / x86_64 / Standard 0.3.0-21 | Stopped service retained blocking. Explicit disable removed the owned table, and trial expiry or disable during confirmation behaved as documented. Other rules remained. | Pass |
| Ubuntu 24.04.5 / 6.8.0-147-generic / x86_64 | Stopping the Agent left rules in place. Removal preserved config, other rules, and running 3x-ui. | Pass |
| Alpine 3.23.7 / 6.18.58-0-virt / x86_64 | The same removal path worked under OpenRC. | Pass |
| Ubuntu VM | Single-file IPK/APK checksums, rejection of damaged files or missing manifest entries, and valid/invalid documentation checker inputs. | Pass |

## Cloud and production

Prior live Cloudflare tests covered authentication, policy, and Tunnel disconnects. The recovery follow-up was isolated. Record the deployed revision and full run before assigning a cloud pass. The Worker npm version alone cannot identify a deployment. Before expanding coverage, try one client on the actual hardware and check both traffic directions, offload, and boot. Reboot the router that runs Proxy Guard for boot acceptance. See [installation and use](USAGE.en.md).

## Updating this matrix

Record image version, `uname -r`, architecture, package, running core, mode, cases, outcome, and date. Retain initial failures alongside reruns. Mark unknown values explicitly. Redact addresses, keys, tokens, and configuration before sharing.
