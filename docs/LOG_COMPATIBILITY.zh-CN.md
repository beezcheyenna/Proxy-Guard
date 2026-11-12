# 运行日志兼容说明

[English](LOG_COMPATIBILITY.md) · [简体中文](LOG_COMPATIBILITY.zh-CN.md) · [日本語](LOG_COMPATIBILITY.ja.md) · [Русский](LOG_COMPATIBILITY.ru.md) · [فارسی](LOG_COMPATIBILITY.fa.md)

LuCI 提供简体中文、英语、日语、俄语和波斯语。日志识别取决于客户端经验证的原始消息和格式，与界面语言无关。

## 已审查的客户端与消息

| 客户端 | 识别的日志格式 | 审查版本的语言范围 |
| --- | --- | --- |
| PassWall | `YYYY-MM-DD HH:MM:SS: message` | 固定的中文生命周期消息和保留的旧标识。 |
| PassWall2 | `YYYY-MM-DD HH:MM:SS: message` | 英语、简体中文、繁体中文、俄语和波斯语的生命周期消息。 |
| OpenClash | `YYYY-MM-DD HH:MM:SS [level] message` | 经审查的英语生命周期标识及支持的动态防火墙重载消息。 |
| Nikki | `[YYYY-MM-DD HH:MM:SS] [component] message` | 经审查的英语 App/Core/Proxy/Profile 生命周期标识及延迟启动消息。 |
| HomeProxy | `YYYY-MM-DD HH:MM:SS [DAEMON] message` | 经审查的英语生命周期标识及带版本的 sing-box 启动完成消息。 |

已审查的上游修订如下。

- [PassWall — 5e2bbfa8](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52)
- [PassWall2 — 896c586a](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945)
- [OpenClash — e553e82e](https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd)
- [Nikki — 78e1a751](https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8)
- [HomeProxy — fadaa676](https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec)

PassWall 和 PassWall2 的词库也对照 **26.11.3-1** 版重新生成。55 条精确签名和 74 个回归用例保持一致。OpenClash 0.48.002 和本轮使用的 HomeProxy 源码对应上述修订。Nikki 1.26.2 发出相同的已识别消息。日语界面可以识别受支持的中文、英语等上游原始消息。其他分支、新译法和后续版本需单独核验。

[PassWall 0b969d5a](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/0b969d5a49743a9725c8dc283b01753c5217dd0d) · [PassWall2 176e27cb](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/176e27cb8d9852ce9b30d2e180810b544d8fc9dc)

## 触发与恢复

日志监视在客户端服务监视下单独启用。已验证的重启、规则移除、清除或加载、停止和全局启动失败可触发保护。安排任务、下载、例行更新、日志截断和辅助节点错误本身不足以判断主代理停止。

仅有规则加载消息不足以恢复。需要本轮新鲜的顶层启动完成消息、所需服务恢复以及新一轮代理验证通过。取消消息可取消排队的重启。已删除的规则和增强监测中已经进入的阻断等待仍需按原流程处理。

## 时间、读取上限与边界

使用路由器本地时区解析时间戳。定时任务的固定 UTC 偏移独立于日志时区。延迟用单调时间。每轮最多读取 64 KiB，支持 CRLF、半行、截断和轮转。未知格式、无效或未来时间、缺日志需检查。轮询只能看到已经写入的消息，采样间的短暂变化可能漏过。

服务监视、日志识别和连通性检查彼此独立。识别一条消息不足以确认进程、监听端口或代理路径正常。见[兼容性](COMPATIBILITY.md)和[检测行为](USAGE.md)。

## 来源与回归用例

PassWall/PassWall2 的来源和消息用例在 `tests/passwall_log_corpus.json`。`tools/sync_passwall_log_messages.py` 读取固定源码树和清单，不执行上游脚本。其他签名在 `package/root/usr/lib/proxy-guard/passwall-log.uc`。`tests/client_adapters_test.uc`、`tests/passwall_log_languages.uc`、`tests/passwall_log_test.uc` 覆盖受支持消息、混合语言重启、过期及未来完成消息、取消、畸形文本和词库变更。上游衍生材料保留其适用许可。参见[第三方声明](THIRD_PARTY_NOTICES.zh-CN.md)。
