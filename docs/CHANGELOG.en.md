# Changelog

[简体中文](CHANGELOG.md) · [English](CHANGELOG.en.md) · [日本語](CHANGELOG.ja.md) · [Русский](CHANGELOG.ru.md) · [فارسی](CHANGELOG.fa.md)

## Standard 0.3.0-21 · Pro 0.3.1-5

This delivery includes the recent compatibility fixes and the status-display fix. Pro retains its independent version; updating Standard does not require reinstalling Pro.

### Fixes

- Corrected status text that could still say healthy or restored after the kernel access permit expired and traffic was already blocked. Current status follows kernel enforcement; completed check results remain historical.
- Prevented an old service-monitor task from writing to a removed rule set after a configuration change. Optional service permits are no longer updated when service monitoring is disabled.
- Fixed recovery remaining pending after log monitoring paused past a completed startup record. Timeline continuity is checked so old records cannot incorrectly confirm recovery.
- Fixed invalid UTF-8 in internal cursor state when a read split a non-ASCII log character.
- Corrected native Hysteria2, Shadowsocks-Rust and NaiveProxy listener detection to avoid false blocking caused by selecting the wrong SOCKS port.
- Prevented intentional service shutdown from consuming procd's crash-restart budget and interfering with later recovery from a real crash.
- Fixed SDK recipe indentation and APK minimum-version dependency syntax.

### Compatibility and documentation

- IPK and APK packages are provided for their respective package managers. Functional tests cover installation, upgrades, retained configuration, UI, fault blocking and recovery, IPv4/IPv6, established connections and cold boot.
- Added actual traffic, failure and recovery checks for a PassWall-managed sing-box ShadowTLS v3 client with a native ShadowTLS server. The native ShadowTLS client is not end-to-end accepted. UDP checks use a separate routed path and do not imply UDP transport through ShadowTLS.
- Refreshed the homepages, user guides, privacy pages and screenshots in five languages. Documentation is under `docs/`, with images under `docs/images/`.
- Exit IPv4 fallback behavior is unchanged: only a primary timeout triggers the backup; every new round starts with the primary, and an explicitly wrong IP remains a fault.
- Concurrent SOCKS5 UDP port collisions in Xray 26.11.9 remain a reproduced upstream limitation. This release does not modify or fix Xray. See [compatibility](COMPATIBILITY.md).

### Upgrading

Back up your configuration and choose IPK or APK to match the firmware. Normal upgrades preserve confirmed settings. Fresh installations leave protection, exit IPv4 matching and schedules off, with UTC+00:00 as the default offset. Pro still requires a compatible Standard installation; subsequent upgrades can be separate within the supported interface contract.

[User guide](USER-GUIDE.en.md) · [Privacy](PRIVACY.en.md)
