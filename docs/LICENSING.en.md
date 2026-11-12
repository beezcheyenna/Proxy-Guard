# Licensing scope and third-party material

[English](LICENSING.en.md) · [简体中文](LICENSING.md) · [日本語](LICENSING.ja.md) · [Русский](LICENSING.ru.md) · [فارسی](LICENSING.fa.md)

Original project code and documentation use the root [MIT license](../LICENSE). That policy applies to Standard, Pro, and original companion code. Third-party material keeps its applicable authorship, terms, and distribution conditions.

## License records

[Third-party notices](THIRD_PARTY_NOTICES.md) record the material, runtime dependencies, and development tools. The [component inventory](THIRD_PARTY_COMPONENTS.json) and [source records](../LICENSES/SOURCES.json) record versions or revisions, provenance, and checksums of the license copies. See the [license index](../LICENSES/README.md) for original texts. The component's own copyright, NOTICE, file-level terms, and corresponding-source obligations still apply.

## UCI and firmware dependencies

Lua, ucode, LuCI, UCI, rpcd, firewall4, and curl come from the firmware feeds. The application IPK and APK contain the application files. At UCI revision `16ff0badbde7e17ec3bd1f827ffe45922956cf86`, `libuci.c` has an LGPL v2.1 header and `lua/uci.c` a GPL v2 header. Cached package metadata uses LGPL-2.1. The Lua backend imports the Lua binding directly. The frontend JavaScript UCI module and the ucode UCI module are separate components.

These records preserve the upstream declarations. Where a distribution constitutes a GPL-covered combination, comply with the terms and applicable corresponding-source requirements for that combination. Assess the actual material and integration.

## Log recognition material

Messages and translations are taken from pinned upstream revisions. The exact catalog has 55 PassWall family, 15 OpenClash, 11 Nikki, and 4 HomeProxy strings. Dynamic patterns are separate.

- PassWall and PassWall2 retain upstream GPL v3 notices.
- OpenClash material retains its MIT copyright notice.
- Nikki's recipe declares GPL-3.0-or-later.
- The HomeProxy source init script declares GPL-2.0-only.

The parser and control logic are original. Copyrightable upstream-derived material retains its upstream terms. Assess short functional strings, translations, and arrangement individually. Log monitoring runs in a separate ucode process and exchanges JSON state files with the Lua backend. Distribution obligations depend on the files, dependencies, and actual combination.

## Companions

The VPS Agent uses Python's standard library and external Linux tools. The Worker uses hosted platform APIs. Its [dependency inventory](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) lists 91 non-root lockfile entries including development and platform-specific optional dependencies. Cloudflare operates its hosted service under its own terms.

## Distribution

Keep MIT, copyright, and applicable third-party notices with original project code. For copied or modified upstream material retain source notices and modification records and follow applicable requirements. If distributing additional system libraries, firmware, proxy cores, `node_modules`, or binaries, review the actual contents and source obligations. See the [disclaimer](DISCLAIMER.en.md) for project terms.

Upstream references:

[GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html) · [GNU license compatibility](https://www.gnu.org/licenses/license-compatibility.en.html) · [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
