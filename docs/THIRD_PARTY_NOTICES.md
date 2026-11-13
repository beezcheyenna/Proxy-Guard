# Third-party notices

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

This notice covers the router application.

## Project-owned code

Copyright (c) 2026 Proxy Guard contributors.

Original project code and documentation use the [MIT license](../LICENSE). Upstream message strings, patches, libraries, interpreters, tools, proxy cores and firmware retain their original terms.

## Upstream message material

The lifecycle recognizer in package/root/usr/lib/proxy-guard/passwall-log.uc and its test corpora contain message identifiers and translated message strings taken from the following upstream revisions. The parser and control logic are authored in this project. Any copyrightable upstream-derived material retains its upstream terms. We do not assert that every short functional identifier is independently copyrightable, or that reproducing a notice alone resolves all combination/licensing questions.

| Project | Revision | Upstream notice | Use here |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | GNU GPL v3, as stated by upstream | Lifecycle messages and test corpus |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | GNU GPL v3, as stated by upstream | English, Chinese, Russian and Persian message identifiers and test corpus |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT in the upstream root LICENSE; retain any applicable per-file notices | Lifecycle message identifiers |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | GPL-3.0-or-later in the pinned package recipe; retain per-file notices | Lifecycle message identifiers |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | GPL-2.0-only in the pinned init script | Lifecycle message identifiers |

The exact PassWall/PassWall2 archive hashes and cases are recorded in tests/passwall_log_corpus.json. Source URLs, license copies and retrieval hashes for all five projects are recorded in docs/THIRD_PARTY_COMPONENTS.json and LICENSES/UPSTREAM/. Recognition material has been selected and mapped to Proxy Guard events; entire upstream scripts, UI packages and proxy cores are not bundled in the LuCI IPK/APK packages.

PassWall acknowledgements: Copyright (C) 2018-2020 L-WRT Team; Copyright (C) 2021-2025 xiaorouji; Copyright (C) 2026 Openwrt-Passwall Organization, as stated in the pinned upstream package recipe. PassWall2 acknowledgements: Copyright (C) 2022-2025 xiaorouji; Copyright (C) 2026 Openwrt-Passwall Organization. Additional upstream notices are preserved with the license/source references; this list does not remove other contributors' rights.

Upstreams:
- https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52
- https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945
- https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd
- https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8
- https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec

## OpenWrt runtime components / OpenWrt 运行依赖

These components are supplied by the target firmware/package feeds, not copied into this application package:

| Component | Use | License evidence |
| --- | --- | --- |
| LuCI, luci-lib-jsonc, luci-lib-nixio | UI, JSON and POSIX/socket facilities | Apache-2.0 in the OpenWrt 24.10 LuCI recipes; retain upstream NOTICE |
| Lua | Interpreter | MIT; see the license of the installed Lua version |
| ucode, fs/uci modules | Interpreter, file locks, configuration access | ISC for ucode; linked libraries retain their own terms |
| UCI library | Configuration library | LGPL v2.1 in libuci.c |
| UCI Lua binding (libuci-lua) | Imported into the Lua process with require('uci') | GPL v2 in lua/uci.c; this is distinct from the LGPL library |
| rpcd | RPC and ACL services | ISC in the checked OpenWrt 24.10 recipe |
| ubus | System message bus | LGPL-2.1 as declared in the checked recipe; inspect per-file notices |
| procd, netifd, BusyBox | Supervision, interface events and shell utilities | GPL-2.0 as declared in the checked recipes; inspect per-file notices |
| firewall4 | Fixed firewall loading and reconciliation | ISC in the checked recipe |
| nftables / Linux Netfilter | Packet filtering and connection tracking | Separate upstream programs/kernel components; retain their own GPL and per-file notices if redistributed |
| curl and the firmware CA bundle | SOCKS/HTTPS checks | Separate system packages; curl's own license and the CA bundle's applicable upstream terms |
| Ruby/YAML facilities, when used by the OpenClash adapter | Safe parsing of an existing client configuration | Supplied by the target firmware; installed-version and incorporated-library licenses apply |

Recipe metadata is not a substitute for a file-level license declaration. In particular, the UCI package-level LGPL declaration does not erase the GPL-v2 header on the Lua binding. Calling external commands and importing an in-process binding are different integration mechanisms. This document records the distinction and does not declare a blanket GPL linking exception or grant permission on behalf of upstream authors. Redistributors of combined runtimes or firmware must assess the actual versions, combination and applicable exceptions.

## Proxy clients and cores

PassWall, PassWall2, OpenClash, Nikki, HomeProxy, Xray, sing-box and Mihomo are separately maintained projects. Proxy Guard reads supported client settings, logs and service state. Install proxy clients and their cores through the appropriate firmware feeds or upstream instructions. Inclusion of a third-party binary or source in another distribution requires a separate component-specific notice/source check.

## Licensing scope

Original code uses MIT. Keep applicable third-party notices, copyright, and source records for the actual distribution. The original declarations for each component and file govern their terms. See [licensing scope](LICENSING.en.md).
