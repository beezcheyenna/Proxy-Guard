# Compatibility test matrix

[English](TEST-MATRIX.en.md) · [简体中文](TEST-MATRIX.md) · [日本語](TEST-MATRIX.ja.md) · [Русский](TEST-MATRIX.ru.md) · [فارسی](TEST-MATRIX.fa.md)

This matrix lists router firmware, proxy clients and forwarding modes for Proxy Guard. The full combination tables carry forward the isolated compatibility results from 2026-11-11 (UTC). The sections below record the integration and API checks for the 1.0 packages.

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

Separate runs covered installation and removal, cold boot, log parsing and rotation, trial rollback, five LuCI languages, permissions and errors. See [runtime log compatibility](LOG_COMPATIBILITY.md) for the upstream message languages.

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

## 1.0.0-7 / 1.0.0-r7 integration tests

The following cases used Proxy Guard `1.0.0-7` (IPK) or `1.0.0-r7` (APK) on x86_64. Isolated virtual machines used real LuCI, SOCKS, TLS and nftables, with local HTTPS peers.

Tested on 2026-11-14 (UTC+08:00).

| Router firmware | Kernel | Checks | Result |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK install, configuration retention, reboot and uninstall. LuCI Save & Apply, confirmation timeout, rollback, proxy diagnostics and log clearing. | Passed |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK install, configuration retention, reboot and uninstall. HTTPS and IPv4 checks, TLS fallback, LAN API, timed and scheduled blocking, and real IPv4/IPv6 TCP/UDP recovery. | Passed |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | PassWall 26.11.3-r1. Short firewall-lock contention, expiry of an unrenewed permit, firewall reload, and IPv4/IPv6 TCP and UDP blocking and recovery. | Passed |

The table records verified configurations and traffic paths. Firmware builds, architectures and modes outside these rows should be checked on the target router.

### Package replacement checks

- **IPK `1.0.0-6` → `1.0.0-7`.** The LuCI test environment installed the new package. opkg kept the modified `/etc/config/proxy_guard` and wrote the incoming file to `/etc/config/proxy_guard-opkg`.
- **APK `1.0.0-r7` → `1.0.0-r7`.** The OpenWrt 25.12.6 test environment reinstalled the same revision, ran the upgrade hooks and verified the installed files.

Moving directly from a published 0.3 package to 1.0, or rolling back from 1.0 to 0.3, remains outside the validated paths. [Migration guide](USAGE.en.md#from-0-3)

## 1.0.0-8 / 1.0.0-r8 API verification

These checks ran on 2026-11-14 (UTC+08:00) in isolated x86_64 virtual machines with the matching final packages. The tested package hashes match the [release manifest](https://github.com/beezcheyenna/Proxy-Guard/releases/download/v1.0.0/SHA256SUMS).

| Router firmware | Kernel | Package | Result |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK | 65 checks passed |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK | 65 checks passed |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | IPK | 65 checks passed |

The r8 checks exercised UUID authentication and rotation after disabling and re-enabling the API, administrator-only access to the UUID and API logs, immediate diagnostic responses with nonce and raw header handling, timeouts and cooldowns, and actual IPv4/IPv6 TCP and UDP blocking, including established flows. Timed requests were tested for expiry, repeated IDs, and cancellation while other protection remained active. HTTPS responses came from local test peers.

[Compatibility and limits](COMPATIBILITY.en.md)
