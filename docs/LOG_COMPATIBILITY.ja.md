# 実行ログの互換性

[English](LOG_COMPATIBILITY.md) · [简体中文](LOG_COMPATIBILITY.zh-CN.md) · [日本語](LOG_COMPATIBILITY.ja.md) · [Русский](LOG_COMPATIBILITY.ru.md) · [فارسی](LOG_COMPATIBILITY.fa.md)

LuCI は簡体字中国語、英語、日本語、ロシア語、ペルシャ語に対応します。ログの認識は、各クライアントで確認した元のメッセージと形式に基づきます。

## 確認したクライアントとメッセージ

| クライアント | ログ形式 | 確認した版の言語範囲 |
| --- | --- | --- |
| PassWall | `YYYY-MM-DD HH:MM:SS: message` | 中国語の固定ライフサイクルメッセージと旧識別子。 |
| PassWall2 | `YYYY-MM-DD HH:MM:SS: message` | 英語、簡体字中国語、繁体字中国語、ロシア語、ペルシャ語のライフサイクルメッセージ。 |
| OpenClash | `YYYY-MM-DD HH:MM:SS [level] message` | 確認済みの英語ライフサイクル識別子と動的なファイアウォール再読み込みメッセージ。 |
| Nikki | `[YYYY-MM-DD HH:MM:SS] [component] message` | 確認済みの英語 App/Core/Proxy/Profile 識別子と遅延開始メッセージ。 |
| HomeProxy | `YYYY-MM-DD HH:MM:SS [DAEMON] message` | 確認済みの英語ライフサイクル識別子と、バージョンを含む sing-box の起動完了メッセージ。 |

確認した上流リビジョンは以下のとおりです。

- [PassWall — 5e2bbfa8](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52)
- [PassWall2 — 896c586a](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945)
- [OpenClash — e553e82e](https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd)
- [Nikki — 78e1a751](https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8)
- [HomeProxy — fadaa676](https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec)

PassWall と PassWall2 の辞書は **26.11.3-1** のソースでも再生成しました。完全一致する 55 件のシグネチャと 74 件の回帰ケースは同じです。OpenClash 0.48.002 と今回の HomeProxy ソースは上記のリビジョンに対応します。Nikki 1.26.2 も同じメッセージを出力します。日本語 UI でも対応する中国語や英語の上流メッセージを認識します。未確認のフォーク、訳文、新しい文言は別途検証が必要です。

[PassWall 0b969d5a](https://github.com/Openwrt-Passwall/openwrt-passwall/tree/0b969d5a49743a9725c8dc283b01753c5217dd0d) · [PassWall2 176e27cb](https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/176e27cb8d9852ce9b30d2e180810b544d8fc9dc)

## 保護を開始する条件と復旧

ログ監視はクライアントのサービス監視内で個別に有効にします。確認済みの再起動、ルール削除・消去・読み込み、停止、全体起動エラーは保護を開始できます。予定登録、ダウンロード、通常の更新、ログ切り詰め、補助ノードのエラーだけでは主プロキシ停止と判断しません。

ルール読み込みだけでは復旧しません。処理中のサイクルに属する新しい全体の起動完了、必要サービスの復帰、新規プロキシ検証が必要です。取り消しは待機中の再起動に有効です。削除済みルールや、強化監視中に確定した遮断待ちは通常手順で扱います。

## 時刻、読み取り上限、検知範囲

タイムスタンプはルーターのローカルタイムゾーンで解釈します。スケジュールの固定 UTC オフセットとは独立です。待ち時間には単調時計を使います。1 回最大 64 KiB を読み、CRLF、未完の行、切り詰め、ローテーションに対応します。不明な形式、無効・未来の時刻、欠けたログを確認してください。書き込まれる前の削除イベントやサンプル間の短時間の変化は見えない場合があります。

サービス監視、ログ認識、接続性検査は独立しています。メッセージ一致だけではプロセス、リスナー、プロキシ経路の正常性は確認できません。[互換性](COMPATIBILITY.ja.md) と [検査動作](USAGE.ja.md) を参照してください。

## ソースと回帰ケース

PassWall/PassWall2 の出典とケースは `tests/passwall_log_corpus.json` にあります。`tools/sync_passwall_log_messages.py` は固定ソースとマニフェストを読み、上流スクリプトは実行しません。他のシグネチャは `package/root/usr/lib/proxy-guard/passwall-log.uc` にあります。`tests/client_adapters_test.uc`、`tests/passwall_log_languages.uc`、`tests/passwall_log_test.uc` は対応メッセージ、複数言語の再起動、古い・未来の完了、取り消し、不正なテキスト、辞書変更を検証します。派生素材には上流ライセンスが適用されます。[第三者通知](THIRD_PARTY_NOTICES.ja.md) を参照してください。
