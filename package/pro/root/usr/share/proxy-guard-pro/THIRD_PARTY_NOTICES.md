# Proxy Guard Pro — third-party notices

Original Pro application code is MIT, Copyright (c) 2026 Proxy Guard contributors; see the accompanying LICENSE.

Pro uses firmware-provided LuCI/UCI libraries, each retaining its upstream license. The UCI Lua binding has a GPL-v2 file header, while the libuci library header says LGPL-v2.1. This notice does not add a linking exception or relicense either component. Neither library is included in this Pro IPK.

Recent base packages also include shared notices under /usr/share/proxy-guard/. An older API-compatible base may not include those newer documentation files; updating Pro does not require a base update solely to obtain them. The complete public source includes LICENSES/, THIRD_PARTY_NOTICES.md and docs/LICENSING.md. Base-owned log material retains its own source notices.

The separately deployed VPS Agent, Worker, cloudflared and managed proxy/panel have distinct distribution scopes. Their upstream rights remain unchanged.

Upstream references:
- https://github.com/openwrt/uci/blob/16ff0badbde7e17ec3bd1f827ffe45922956cf86/lua/uci.c
- https://github.com/openwrt/uci/blob/16ff0badbde7e17ec3bd1f827ffe45922956cf86/libuci.c
- https://github.com/openwrt/luci
