# 第三方声明

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

记录日期 2026-11-08。范围为普通版、Pro、VPS Agent 和 Worker 的公开源码。适用条款以各上游的原始声明为准。

## 自有代码

Copyright (c) 2026 Proxy Guard contributors.

自有代码和原创文档按根目录的 [MIT 许可](../LICENSE) 发布。普通版与 Pro 适用同一政策。上游消息、补丁、库、解释器、工具、代理内核和固件保留各自许可。

## 上游日志消息

`package/root/usr/lib/proxy-guard/passwall-log.uc` 和回归用例含下列修订的消息标识与译文。解析和控制逻辑为自有代码，具有版权的派生材料保留上游条款。短功能标识是否受保护、以及如何分发组合，应按实际材料判断。

| 项目 | 修订 | 上游许可记录 | 用途 |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | GNU GPL v3，上游声明 | 生命周期与测试 |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | GNU GPL v3，上游声明 | 英语、中文、俄语、波斯语生命周期与测试 |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT，保留文件声明 | 生命周期标识 |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | GPL-3.0-or-later，配方声明 | 生命周期标识 |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | GPL-2.0-only，启动脚本声明 | 生命周期标识 |

PassWall/PassWall2 归档哈希及用例见 `tests/passwall_log_corpus.json`。五个项目的 URL、许可副本与哈希见 [组件清单](THIRD_PARTY_COMPONENTS.json) 和 [上游原文](../LICENSES/README.zh-CN.md)。IPK/APK 使用选取的消息与事件映射。

以下是固定上游配方中的署名。其他作者权利与声明见各来源。

PassWall: Copyright (C) 2018-2020 L-WRT Team, Copyright (C) 2021-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization. PassWall2: Copyright (C) 2022-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization.

- https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52
- https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945
- https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd
- https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8
- https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec

## OpenWrt 运行依赖

这些组件由目标固件或软件源提供。表中许可证据按已检查版本和文件记录。

| 组件 | 用途 | 许可证据 |
| --- | --- | --- |
| LuCI, luci-lib-jsonc, luci-lib-nixio | 界面、JSON、POSIX 与套接字 | Apache-2.0 / NOTICE · 检查的 24.10 配方 |
| Lua | 解释器 | MIT · 按已安装版本 |
| ucode, fs/uci | 解释器、锁和配置 | ISC · 链接库另有条款 |
| libuci | UCI 配置库 | LGPL v2.1 (`libuci.c`) · 库文件头 |
| libuci-lua | Lua 进程中通过 `require('uci')` 加载 | GPL v2 (`lua/uci.c`) · Lua 绑定文件头 |
| rpcd | RPC 和 ACL | ISC · 检查的 24.10 配方 |
| ubus | 系统总线 | LGPL-2.1 · 配方，核对文件头 |
| procd, netifd, BusyBox | 守护、接口事件和 shell 工具 | GPL-2.0 · 配方，核对文件头 |
| firewall4 | 规则加载与协调 | ISC · 已检查配方 |
| nftables / Linux Netfilter | 数据包过滤与连接追踪 | GPL · 再分发时保留上游声明 |
| curl / CA bundle | SOCKS/HTTPS 检测 | curl / CA · 按各包条款 |
| Ruby / YAML (OpenClash) | 安全解析现有配置 | 按已安装版本和库条款 |

UCI 的包级 LGPL 元数据与 Lua 绑定的 GPL v2 文件头并存。外部命令与进程内导入不同。再分发固件或组合运行环境时核对实际版本、组合与适用例外。

## Pro Agent 与 Cloudflare 配套

Agent 使用 Python 标准库和外部 Linux 工具，Python、nftables、iproute2、systemd/OpenRC 及代理和面板单独提供。cloudflared 是单独的 Apache-2.0 程序。Cloudflare Worker 使用托管 API，服务适用平台条款。锁文件声明以下开发依赖：

- Wrangler 4.156.0 — MIT OR Apache-2.0
- Miniflare 5.20261023.3-beta — MIT
- workerd 1.20261023.1 — Apache-2.0

<https://github.com/cloudflare/cloudflared/blob/master/LICENSE>

[锁文件清单](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) 有 91 个非根条目，包含可选的平台包。工具、node_modules 与 cloudflared 不打进应用包。若再分发它们，保留实际包的版权、NOTICE 和适用源码。

## 代理客户端、内核与面板

PassWall、PassWall2、OpenClash、Nikki、HomeProxy、Xray、sing-box、Mihomo 和 3x-ui 独立维护。插件读取配置、日志与服务，或调用已授权接口。另行分发上述项目的源码或二进制须按组件核对声明和源码要求。

## 许可范围

再分发应核对实际包含的内容和组合方式。具体组件的原始声明优先。见[许可范围](LICENSING.md)。
