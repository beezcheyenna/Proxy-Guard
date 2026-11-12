# Runtime log compatibility

[English](LOG_COMPATIBILITY.md) · [简体中文](LOG_COMPATIBILITY.zh-CN.md) · [日本語](LOG_COMPATIBILITY.ja.md) · [Русский](LOG_COMPATIBILITY.ru.md) · [فارسی](LOG_COMPATIBILITY.fa.md)

The LuCI interface supports Simplified Chinese, English, Japanese, Russian and Persian. **The interface language does not determine the language of upstream runtime logs.** Recognition follows the verified messages and formats of each supported client.

## Reviewed clients and messages

| Client | Recognized log format | Language coverage at the reviewed revision |
| --- | --- | --- |
| PassWall | `YYYY-MM-DD HH:MM:SS: message` | Fixed Chinese lifecycle messages and retained legacy identifiers. |
| PassWall2 | `YYYY-MM-DD HH:MM:SS: message` | English, Simplified Chinese, Traditional Chinese, Russian and Persian lifecycle messages. |
| OpenClash | `YYYY-MM-DD HH:MM:SS [level] message` | Reviewed English lifecycle identifiers, with supported dynamic firewall-reload messages. |
| Nikki | `[YYYY-MM-DD HH:MM:SS] [component] message` | Reviewed English App/Core/Proxy/Profile lifecycle identifiers and delayed-start messages. |
| HomeProxy | `YYYY-MM-DD HH:MM:SS [DAEMON] message` | Reviewed English lifecycle identifiers and the versioned sing-box startup-completed message. |

The reviewed upstream revisions are:

- [PassWall — 5e2bbfa8](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52)
- [PassWall2 — 896c586a](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945)
- [OpenClash — e553e82e](https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd)
- [Nikki — 78e1a751](https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8)
- [HomeProxy — fadaa676](https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec)

The PassWall and PassWall2 catalogs were also regenerated against the **26.11.3-1** release sources ([PassWall 0b969d5a](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/0b969d5a49743a9725c8dc283b01753c5217dd0d), [PassWall2 176e27cb](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/176e27cb8d9852ce9b30d2e180810b544d8fc9dc)). The 55 exact lifecycle signatures and 74 regression fixtures are unchanged. OpenClash 0.48.002 and the HomeProxy source used in this compatibility round match the revisions above. Nikki 1.26.2 and the reviewed revision emit the same recognized lifecycle messages.

A Japanese interface can recognize supported Chinese, English or other upstream messages. It does not require an invented Japanese translation of backend messages. Unreviewed forks, translated log formats and future wording require separate verification; this is not a promise to recognize arbitrary messages in every language.

## Triggers and recovery

Log monitoring is enabled separately under client service monitoring. Verified restart, rule removal/clearing/loading, stop and global startup-failure messages can trigger protection. Scheduled-task setup, downloads, routine rule updates, log truncation and auxiliary-node errors do not by themselves prove that the main proxy is stopping.

A rules-loaded message alone cannot authorize recovery. A fresh top-level startup-completed message must belong to the pending cycle, required services must recover, and new proxy validation must pass. Cancellation can end a queued restart, not undo a rule removal. An already required blocking wait during enhanced monitoring is not cancelled by a later completion message.

## Time, reading limits and detection boundaries

Timestamps are interpreted in the router's local time zone. The schedule's fixed UTC offset does not change log timestamp parsing. Delays use monotonic time.

The reader processes at most 64 KiB per round and supports CRLF, partial lines, truncation and rotation. Unknown formats, invalid or future timestamps and missing logs require attention. Polling cannot observe rule deletion before its message is written, and short changes between samples can be missed.

Service monitoring and connectivity checks remain separate. Matching a log message does not prove that a process, listener or proxy route is healthy. See [compatibility](COMPATIBILITY.en.md) and [detection behavior](USAGE.en.md).

## Source material and regression fixtures

PassWall/PassWall2 provenance and message cases are in `tests/passwall_log_corpus.json`. The generator `tools/sync_passwall_log_messages.py` reads pinned source trees and their manifest; it does not execute upstream scripts.

Other client signatures are in `package/root/usr/lib/proxy-guard/passwall-log.uc`. Related fixtures include `tests/client_adapters_test.uc`, `tests/passwall_log_languages.uc` and `tests/passwall_log_test.uc`. Regression cases cover supported messages, mixed-language restarts, stale/future completion, cancellation, malformed text and catalog changes.

Upstream-derived message material retains its applicable license; see [third-party notices](THIRD_PARTY_NOTICES.md).
