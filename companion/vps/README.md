# Proxy Guard VPS Agent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

Pro companion for **selected VPS service ports**: authenticated household IP leases, per-port access policies, optional SSH rescue and explicitly authorized maintenance. Standard users do not need this component.

- [Install, upgrade and remove](../../docs/LINUX-AGENT-INSTALL.en.md)
- [Architecture and failure behavior](../../docs/PRO-COMPANION.en.md)
- [Component compatibility](../../docs/EDITION-MATRIX.en.md)
- [Tested distributions and limits](../../docs/TEST-MATRIX.en.md)
- [Recovery without LuCI](../../docs/RECOVERY.en.md)

Requires Python 3.10+, nftables and systemd or OpenRC. Direct HTTPS and Cloudflare control are alternatives. Installation does not install a proxy core or 3x-ui. Keep management access before enabling policy; unselected ports remain governed by the existing firewall.

Development and security reporting: [contributing](../../CONTRIBUTING.md) · [security policy](../../docs/SECURITY.en.md).

[Licensing scope](LICENSING.en.md) · [Third-party notices](THIRD_PARTY_NOTICES.en.md)
