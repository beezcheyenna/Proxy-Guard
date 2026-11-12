# Proxy Guard Worker — third-party notices

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

Original Worker source is offered under the accompanying MIT LICENSE, Copyright (c) 2026 Proxy Guard contributors.

The Worker uses hosted Cloudflare platform APIs. The hosted platform is governed by its service terms; this project's license does not license that service.

package.json declares Wrangler 4.156.0 and Miniflare 5.20261023.3-beta as development dependencies. The lockfile declares Wrangler as MIT OR Apache-2.0, Miniflare as MIT, and workerd 1.20261023.1 as Apache-2.0. No production npm dependency is declared and no node_modules or tooling binary is included in this source directory.

THIRD_PARTY_DEPENDENCIES.json records all 91 non-root lockfile package entries, their declared licenses, versions and integrity values, including optional platform-specific entries. It is not a list of packages necessarily installed or shipped. Some development/native dependency metadata includes LGPL and other licenses; the MIT license on the Worker does not relicense those dependencies.

When installing tooling, retain the packages' included license and NOTICE files. If distributing tooling, a vendored node_modules tree or a bundle containing third-party code, audit the actual output and preserve complete upstream notices and corresponding-source obligations; the lockfile inventory and generic license texts alone are insufficient.

cloudflared and the VPS Agent are deployed separately. cloudflared is Apache-2.0:
https://github.com/cloudflare/cloudflared/blob/master/LICENSE
