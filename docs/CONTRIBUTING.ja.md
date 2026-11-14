# 貢献方法

[English](../CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md) · [日本語](CONTRIBUTING.ja.md) · [Русский](CONTRIBUTING.ru.md) · [فارسی](CONTRIBUTING.fa.md)

再現可能な問題、互換性の結果、文書修正、目的を絞ったプルリクエストを歓迎します。

- [不具合の報告](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=bug_report.yml)
- [互換性の報告](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=compatibility.yml)
- [機能の提案](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=feature_request.yml)
- [文書へのフィードバック](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=documentation.yml)

一般的な不具合は機密情報を除いて公開 Issue に投稿できます。未修正の脆弱性の詳細は公開しないでください。 [セキュリティ方針](SECURITY.ja.md)

## 動作を変更する前に

1. 発生条件、期待結果、実結果を示します。文書用アドレスと最小限の匿名化した構成を使います。
2. ファームウェア、カーネル、アーキテクチャ、形式、インストール済みの Proxy Guard のバージョン、稼働コア、転送モードを記録します。パッケージ情報と実行バイナリを区別します。
3. 許可された隔離環境を使います。サービス、経路、ファイアウォールを変更する試験は使い捨て VM 内で実行します。
4. 変更を対象に絞り、ACL、証明書検証、無関係な NAT/DNS/ネットワーク設定を保持します。

[ビルド](BUILDING.ja.md) と[テストマトリクス](TEST-MATRIX.ja.md) を参照してください。実インストールと通信経路は別に検証します。

## 文書と翻訳

既定のホームは英語です。続いて簡体字中国語、日本語、ロシア語、ペルシャ語です。動作変更時は関連する 5 言語の本文とリンクをそろえます。変更履歴は英語です。旧 URL でも英語の履歴を表示します。ライセンス原文と通知を保持します。

リポジトリのルートから検査を実行します。

```sh
python3 tools/check_docs.py
python3 -m unittest discover -s tools/tests -p 'test_check_docs.py'
```

文書の有無、リンクの言語、アンカー、版、パッケージ名を検査します。翻訳内容は別途確認してください。PR はオフライン検査、既定ブランチとリリースイベントは最新正式版との比較も行います。バージョン変更を先にマージした場合は正式リリース後に再確認します。

## プルリクエストと証拠

問題、変更、検証、残る制限を説明します。互換性は版と日付を正確に記録し、模擬、隔離 VM、実配備を区別して初回失敗も保持します。文書 PR に生成パッケージ、非公開ログ、無関係な書式変更を含めないでください。[ライセンス](LICENSING.ja.md) を参照してください。
