# Compatibility test matrix

[English](TEST-MATRIX.en.md) · [简体中文](TEST-MATRIX.md) · [日本語](TEST-MATRIX.ja.md) · [Русский](TEST-MATRIX.ru.md) · [فارسی](TEST-MATRIX.fa.md)

The following cases were verified with Proxy Guard 1.0.0-r7 on x86_64. Isolated virtual machines used real LuCI, SOCKS, TLS and nftables, with local HTTPS peers.

Tested on 2026-11-14 (UTC+08:00).

| Router firmware | Kernel | Checks | Result |
| --- | --- | --- | --- |
| OpenWrt 24.10.8 (r29233-443ec4032a) | 6.6.144 | IPK install, configuration retention, reboot and uninstall. LuCI Save & Apply, confirmation timeout, rollback, proxy diagnostics and log clearing. | Passed |
| OpenWrt 25.12.6 (r33311-981c978eff) | 6.12.112 | APK install, configuration retention, reboot and uninstall. HTTPS and IPv4 checks, TLS fallback, LAN API, timed and scheduled blocking, and real IPv4/IPv6 TCP/UDP recovery. | Passed |
| iStoreOS 24.10.8 (2026073111) | 6.6.144 | PassWall 26.11.3-r1. Short firewall-lock contention, expiry of an unrenewed permit, firewall reload, and IPv4/IPv6 TCP and UDP blocking and recovery. | Passed |

The table records verified configurations and traffic paths. Firmware builds, architectures and modes outside these rows should be checked on the target router.

[Compatibility and limits](COMPATIBILITY.en.md)
