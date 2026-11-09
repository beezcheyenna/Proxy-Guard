# Third-party notices / 第三方声明

Updated: 2026-11-08. Scope: Proxy Guard Standard, Pro, the VPS Agent and the companion Worker source. This is a component and provenance notice, not a replacement for the upstream license texts.

## Project-owned code / 自有代码

Copyright (c) 2026 Proxy Guard contributors.

Original Proxy Guard code and original documentation are offered under the MIT license in LICENSE. This statement does not relicense upstream message strings, patches, libraries, interpreters, tools, proxy cores or firmware. Standard and Pro use the same licensing policy; the name “Pro” does not imply a proprietary license.

## Upstream message material / 上游日志消息

The lifecycle recognizer in package/root/usr/lib/proxy-guard/passwall-log.uc and its test corpora contain message identifiers and translated message strings taken from the following upstream revisions. The parser and control logic are authored in this project. Any copyrightable upstream-derived material retains its upstream terms. We do not assert that every short functional identifier is independently copyrightable, or that reproducing a notice alone resolves all combination/licensing questions.

| Project | Revision | Upstream notice | Use here |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | GNU GPL v3, as stated by upstream | Lifecycle messages and test corpus |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | GNU GPL v3, as stated by upstream | English, Chinese, Russian and Persian message identifiers and test corpus |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT in the upstream root LICENSE; retain any applicable per-file notices | Lifecycle message identifiers |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | GPL-3.0-or-later in the pinned package recipe; retain per-file notices | Lifecycle message identifiers |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | GPL-2.0-only in the pinned init script | Lifecycle message identifiers |

The exact PassWall/PassWall2 archive hashes and cases are recorded in tests/passwall_log_corpus.json. Source URLs, license copies and retrieval hashes for all five projects are recorded in docs/THIRD_PARTY_COMPONENTS.json and LICENSES/UPSTREAM/. Recognition material has been selected and mapped to Proxy Guard events; entire upstream scripts, UI packages and proxy cores are not bundled in the LuCI IPKs.

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

## Pro Agent and Cloudflare companion / Pro 配套

The VPS Agent is original project code using Python's standard library and external Linux facilities. Python, nftables, iproute2, systemd/OpenRC and any managed proxy/panel are supplied separately and keep their upstream licenses.

cloudflared is a separate Apache-2.0 tunnel program:
https://github.com/cloudflare/cloudflared/blob/master/LICENSE

The Worker uses Cloudflare platform APIs. Cloudflare's hosted service is subject to its service terms; it is not relicensed by this project.

The Worker package declares development dependencies, not production npm dependencies:
- Wrangler 4.156.0: MIT OR Apache-2.0, as declared by the lockfile.
- Miniflare 5.20261023.3-beta: MIT, as declared by the lockfile.
- workerd 1.20261023.1: Apache-2.0, as declared by the lockfile.

The lockfile has 91 non-root package entries, including platform-specific optional entries. Their exact versions, integrity values and declared licenses are listed in companion/worker/THIRD_PARTY_DEPENDENCIES.json. That is a lockfile inventory, not a claim that all entries are installed or shipped. node_modules, Wrangler, Miniflare, workerd and cloudflared binaries are not bundled in the application's LuCI IPKs. A future vendored or bundled distribution must preserve the actual packages' notices, including transitive and native-library notices; generic license texts alone are insufficient.

## Proxy cores and panels / 对接项目

PassWall, PassWall2, OpenClash, Nikki, HomeProxy, Xray, sing-box, Mihomo and 3x-ui are separately maintained projects. Reading their configuration/logs, observing their services or invoking an authorized management interface does not transfer their copyright to Proxy Guard. The LuCI IPKs do not contain or automatically replace these proxy cores or panels. Inclusion of a third-party binary or source in another distribution requires a separate component-specific notice/source check.

## Optional sing-tun patch / 可选补丁

This source tree includes compat/sing-tun-v0.7.13/ as optional source patch material. It does not contain a compiled replacement core or automatically install that patch.

Where included, the patch modifies SagerNet/sing-tun v0.7.13, Copyright (C) 2022 nekohasekai, under GPL-3.0-or-later. Preserve that directory's LICENSE.sing-tun, COPYING.GPL-3.0, patch, source/version hashes and build/validation notes. GPL v3 and “or later” wording must not be replaced by MIT.

The application's LuCI IPKs do not include this patched core. If distributing a compiled patched core, provide the corresponding source and build material required by its license; merely attaching this notice or linking to an unrelated upstream version is insufficient.

Upstream: https://github.com/SagerNet/sing-tun/tree/v0.7.13

## Licensing scope / 许可范围

自有代码采用 MIT 授权，第三方材料、运行依赖、开发工具和可选补丁按各自来源保留原许可。再分发时应核查实际包含的内容与组合方式，保留相关版权、NOTICE 和适用源码材料。具体组件和文件的原始声明优先。
