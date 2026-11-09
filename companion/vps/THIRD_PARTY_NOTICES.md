# Proxy Guard VPS Agent — third-party notices

Original Proxy Guard Agent source is offered under the accompanying MIT LICENSE, Copyright (c) 2026 Proxy Guard contributors.

The Agent uses Python's standard library and external Linux programs/facilities. Python, nftables/Linux Netfilter, iproute2 and systemd/OpenRC are installed separately and retain their own licenses and incorporated notices. No third-party pip packages or Python interpreter are bundled with this directory.

Xray, sing-box, Mihomo and 3x-ui, where configured for observation or authorized maintenance, remain separate upstream projects. Their source or binaries are not included by the Agent installer. cloudflared, if used, is a separately installed Apache-2.0 program:
https://github.com/cloudflare/cloudflared/blob/master/LICENSE

If redistributing an interpreter, tunnel program, proxy core, panel, system image or other bundled dependency, retain its own notices and provide corresponding source/build material where required. The MIT license on this Agent does not relicense those components.

The full project's THIRD_PARTY_NOTICES.md records the OpenWrt-side log material and runtime binding distinctions. Those materials are not added to the Agent by copying this notice. LICENSING.md describes the Agent's licensing scope and the notice files copied by its installer.
