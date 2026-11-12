# 第三者通知

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

記録日 2026-11-08。通常版、Pro、VPS Agent、Worker の公開ソースが対象です。適用条件は各上流の原文を参照してください。

## 独自コード

Copyright (c) 2026 Proxy Guard contributors.

独自コードと文書はルートの [MIT ライセンス](../LICENSE) で公開します。通常版と Pro に共通です。上流の文字列、パッチ、ライブラリー、インタープリター、ツール、コア、ファームウェアは各自の許諾条件を維持します。

## 上流のログメッセージ

`package/root/usr/lib/proxy-guard/passwall-log.uc` と回帰ケースは以下のリビジョンから識別子と翻訳を取得します。解析と制御は独自で、著作権のある派生素材は上流条件を保持します。短い機能識別子や配布時の結合は素材ごとに評価します。

| プロジェクト | リビジョン | 上流ライセンスの記録 | 用途 |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | 上流の GNU GPL v3 | ライフサイクルとテスト |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | 上流の GNU GPL v3 | 英語、中国語、ロシア語、ペルシャ語のライフサイクルとテスト |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT、ファイル別表示を保持 | ライフサイクル識別子 |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | レシピの GPL-3.0-or-later | ライフサイクル識別子 |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | init の GPL-2.0-only | ライフサイクル識別子 |

PassWall/PassWall2 のアーカイブハッシュとケースは `tests/passwall_log_corpus.json` にあります。5 プロジェクトの出典、ライセンス写し、ハッシュは [一覧](THIRD_PARTY_COMPONENTS.json) と [上流原文](../LICENSES/README.ja.md) を参照してください。IPK/APK は選択したメッセージとイベントの対応を使います。

以下は固定レシピの著作権表示です。その他の著作権は上流通知を参照してください。

PassWall: Copyright (C) 2018-2020 L-WRT Team, Copyright (C) 2021-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization. PassWall2: Copyright (C) 2022-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization.

- https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52
- https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945
- https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd
- https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8
- https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec

## OpenWrt のランタイム依存関係

対象ファームウェアやフィードが提供します。ライセンスの根拠は確認した版・ファイルに基づきます。

| コンポーネント | 用途 | 根拠 |
| --- | --- | --- |
| LuCI, luci-lib-jsonc, luci-lib-nixio | 画面、JSON、POSIX とソケット | Apache-2.0 / NOTICE · 確認した 24.10 レシピ |
| Lua | インタープリター | MIT · 導入版を参照 |
| ucode, fs/uci | インタープリター、ロック、設定 | ISC · リンク先の条項は個別 |
| libuci | UCI 設定ライブラリー | LGPL v2.1 (`libuci.c`) · ライブラリーヘッダー |
| libuci-lua | Lua 内で `require('uci')` により読み込む | GPL v2 (`lua/uci.c`) · Lua バインディングヘッダー |
| rpcd | RPC と ACL | ISC · 確認した 24.10 レシピ |
| ubus | システムバス | LGPL-2.1 · レシピとファイル別表示 |
| procd, netifd, BusyBox | 監視、インターフェースイベント、シェル | GPL-2.0 · レシピとファイル別表示 |
| firewall4 | 規則の読み込みと調整 | ISC · 確認したレシピ |
| nftables / Linux Netfilter | パケットフィルターと接続追跡 | GPL · 再配布時は上流通知を保持 |
| curl / CA bundle | SOCKS/HTTPS 検査 | curl / CA · 各パッケージに従う |
| Ruby / YAML (OpenClash) | 既存設定の安全な解析 | 導入版・組込ライブラリーに従う |

UCI のパッケージ単位 LGPL 表記と Lua バインディングの GPL v2 ヘッダーは区別します。外部コマンドとプロセス内読み込みは異なります。複合ランタイムやファームウェア配布は実際の版、結合方式、適用例外を確認します。

## Pro Agent と Cloudflare

Agent は Python 標準ライブラリーと外部 Linux ツールを使用します。Python、nftables、iproute2、systemd/OpenRC、プロキシ、パネルは別に提供されます。cloudflared は別の Apache-2.0 プログラムです。Worker は Cloudflare のサービス条件に従うホスト API を使います。開発依存関係は以下のとおりです。

- Wrangler 4.156.0 — MIT OR Apache-2.0
- Miniflare 5.20261023.3-beta — MIT
- workerd 1.20261023.1 — Apache-2.0

<https://github.com/cloudflare/cloudflared/blob/master/LICENSE>

[ロックファイル一覧](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) のルート以外の 91 件には、プラットフォーム別の任意項目が含まれます。ツール、node_modules、cloudflared はアプリパッケージに収録しません。別途配布する場合は実際のパッケージの通知と対応ソースの義務を保持します。

## プロキシクライアント、コア、パネル

PassWall、PassWall2、OpenClash、Nikki、HomeProxy、Xray、sing-box、Mihomo、3x-ui は別プロジェクトです。本プラグインは設定・ログ・サービスを参照し、許可された管理操作を行います。別途再配布するソースやバイナリは、個別の通知とソース要件を確認します。

## ライセンスの範囲

再配布では実ファイルと構成を確認し、各コンポーネントの原文を優先します。[ライセンスの範囲](LICENSING.ja.md) を参照してください。
