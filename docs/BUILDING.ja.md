# ソース、ビルド、検証

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

パッケージレシピのバージョンは通常版が `0.3.0-21`、Pro が `0.3.1-5` です。ここではソース構成、IPK・APK のビルド、開発時のテストを説明します。ビルドした成果物は、そのビルドで生成した SHA256 チェックサムで照合してください。

## ソース構成

| パス | 内容 |
| --- | --- |
| `package/root/` | 通常版のインストールファイル |
| `package/pro/root/` | Pro のインストールファイル |
| `package/Makefile` | OpenWrt パッケージのメタデータとインストール・削除フック |
| `package/i18n/` | 5 言語のメッセージ原文、PO、生成情報 |
| `companion/vps/` | Linux Agent、設定例、対象を限定したインストーラー |
| `companion/worker/` | Worker テンプレート、依存関係ロックファイル、テスト |
| `tests/` | 単体・フロントエンドテストと、専用環境が必要なネイティブ・ネットワーク回帰テスト |
| `LICENSES/` | ライセンス原文と上流通知の写し |

通常版と Pro は別々にビルドできます。Linux Agent と Worker は `companion/` にあります。

## IPK の個別ビルド

Linux のビルド用作業ツリーに Python 3 を用意します。生成済み翻訳はソースに含まれ、メッセージ原文を変更していなければ LuCI のダウンロードや翻訳ツールの実行は不要です。以下は順に通常版のみ、Pro のみ、両方をビルドするコマンドです。

```sh
python3 -B tools/build_ipk.py --only standard
python3 -B tools/build_ipk.py --only pro
python3 -B tools/build_ipk.py
```

Pro のみをビルドする場合は基本パッケージとのファイル所有権の重複も検査します。`dist/` にパッケージ、`SHA256SUMS`、ファイル一覧を出力します。インストールフックの実行や機器への接続は行いません。

原文を変更した場合は、対応する公式 LuCI ソースの `po2lmo` を用意します。Pro の辞書と専用ページだけを再生成する場合は `--only pro` を指定します。

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
```

LMO や診断マッピングを変更したときは生成情報も更新してください。LuCI ツール、SDK、クロスコンパイラー、プロキシコアはそれぞれの上流から入手します。

## OpenWrt SDK

対応する OpenWrt SDK の `package/` 以下にこのリポジトリの `package/` を配置し、SDK の標準手順で `luci-app-proxy-guard` または `luci-app-proxy-guard-pro` を選択してビルドします。依存関係は対象に合ったフィードから取得します。`all` はスクリプトパッケージを表します。

25.12 用 APK は対応する公式 SDK でネイティブにビルドします。`tools/build_ipk.py` が生成するのは IPK です。APK の版表記は `0.3.0-r21` と `0.3.1-r5` です。レシピは APK のインストール、更新、削除フックを保ち、Pro が要求する通常版の下限をパッケージ管理方式に合わせて表現します。

SDK レシピと Python ビルダーは同じインストールツリーを使い、パッケージ管理方式に応じてフックを選択します。`tools/test_sdk_staging.py` は専用のマーカーを持つ隔離 VM でビルド済みの両パッケージのステージング、権限、フックを比較します。ツールチェーン全体は SDK ビルドで別途確認します。

ライセンスと通知はインストールツリーに含まれます。Pro のライセンスファイルは通常版と別の場所にインストールされます。

## 基本テスト

準備済みの専用 Linux/OpenWrt テスト VM で以下を実行します。

```sh
python3 -B tools/test_standard_pro.py
```

Python 3、Node.js、make などが必要です。一部のバージョン・SDK ステージングの確認は、専用イメージが用意する `/etc/pgvm-fixture` マーカーを使います。開発ホストにこのマーカーを手動で作成しないでください。

ネイティブ Lua/ucode、パッケージフック、実際の LuCI/UCI/RPC、ブラウザー、ネットワーク名前空間、TCP/UDP パケット、コールドスタートには対応するイメージとフィクスチャが必要です。スクリプトごとに必要な作業ディレクトリも確認してください。VM ディスクや実配備の認証情報はリポジトリに含まれません。

LMO と実際の LuCI gettext の確認には、対応する公式ソースの `cbi.js` を `PG_LUCI_CBI` で指定します。模擬テストと実環境の結合テストの結果は分けて記録してください。

## Worker

独立した Linux の開発用作業ツリーで、ロックファイルに従いツールを導入します。クラウドの確認には管理されたテストリソースを使います。

```sh
cd companion/worker
npm ci
npm test
```

`npm test` はローカル実行環境を確認します。配備コマンド、秘密情報、バインディングは [Worker の手順](CLOUDFLARE-WORKER.ja.md) を参照し、配備前に対象アカウントの設定と接続を照合してください。

## テスト範囲

ロジック、インストール、画面、復旧、IPv4/IPv6、コールドスタート、複数のシステム、Cloudflare 連携を確認しています。変更に応じて該当するテストを実施してください。[互換性](COMPATIBILITY.ja.md) と [テストマトリクス](TEST-MATRIX.ja.md) を参照してください。
