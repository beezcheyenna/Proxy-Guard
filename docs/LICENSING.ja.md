# ライセンスの範囲と第三者の素材

[English](LICENSING.en.md) · [简体中文](LICENSING.md) · [日本語](LICENSING.ja.md) · [Русский](LICENSING.ru.md) · [فارسی](LICENSING.fa.md)

本プロジェクトの独自コードと文書はルートの [MIT ライセンス](../LICENSE)に従います。通常版、Pro、配備用の独自コードにも適用します。第三者素材には各著作権表示、許諾条件、配布条件が引き続き適用されます。

## ライセンスの記録

[第三者通知](THIRD_PARTY_NOTICES.ja.md) に素材、ランタイム依存関係、開発ツールを記載します。[コンポーネント一覧](THIRD_PARTY_COMPONENTS.json) と [出典記録](../LICENSES/SOURCES.json) は版・リビジョン、出典、ライセンス写しのチェックサムを記録します。[ライセンス一覧](../LICENSES/README.ja.md) に原文があります。各コンポーネントの著作権、NOTICE、ファイル別条件、対応するソースの義務は別途適用されます。

## UCI とファームウェア依存関係

Lua、ucode、LuCI、UCI、rpcd、firewall4、curl は対応ファームウェアから取得します。アプリの IPK/APK はアプリファイルを収録します。UCI リビジョン `16ff0badbde7e17ec3bd1f827ffe45922956cf86` の `libuci.c` は LGPL v2.1、`lua/uci.c` は GPL v2 のヘッダーです。パッケージのキャッシュされたメタデータは LGPL-2.1 表記です。Lua バックエンドは Lua バインディングを直接読み込みます。JavaScript と ucode の UCI モジュールは別です。

上流の宣言をそのまま記録します。配布物が GPL の適用を受ける組み合わせなら、その条件と該当する対応ソースの義務に従います。実際に含まれる素材と結合方式を確認してください。

## ログ認識素材

固定上流リビジョンからメッセージと翻訳を取得します。完全一致は PassWall 系 55 件、OpenClash 15 件、Nikki 11 件、HomeProxy 4 件です。動的パターンは別です。

- PassWall と PassWall2 の GPL v3 の通知を保持します。
- OpenClash の MIT の著作権表示を保持します。
- Nikki レシピは GPL-3.0-or-later です。
- HomeProxy の起動スクリプトは GPL-2.0-only です。

解析・制御は独自コードです。著作権の対象となる上流由来素材は上流条件を保ちます。短い機能識別子、翻訳、配列は個別に評価します。ログ監視は別 ucode プロセスで動き、Lua と JSON 状態ファイルで連携します。配布時は実ファイル、依存関係、構成を確認してください。

## 配備用コンポーネント

Agent は Python 標準ライブラリーと外部 Linux ツールを使います。Worker はホスト型 API を使用します。[依存関係一覧](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) の 91 件はルート以外の開発用・プラットフォーム固有の任意項目を含むロックファイルの記録です。Cloudflare のサービスには利用条件が適用されます。

## 配布

自作ソースの配布では MIT、著作権、該当通知を保持します。上流の複製・変更では元の通知と変更記録を保ち、該当条件に従います。システムライブラリー、ファームウェア、コア、`node_modules`、外部バイナリを含める場合は実際の内容とソース要件を確認します。[免責事項](DISCLAIMER.ja.md) を参照してください。

上流資料（英語）:

[GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html) · [GNU license compatibility](https://www.gnu.org/licenses/license-compatibility.en.html) · [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)
