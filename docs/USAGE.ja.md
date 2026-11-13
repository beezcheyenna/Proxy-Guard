# インストールと使用

[English](USAGE.en.md) · [简体中文](USAGE.md) · [日本語](USAGE.ja.md) · [Русский](USAGE.ru.md) · [فارسی](USAGE.fa.md)

LuCI と firewall4/nftables を使うルーターに Proxy Guard をインストールします。パッケージ形式はファームウェアに合わせてください。

## ダウンロードと照合

同じリリースからパッケージとチェックサムを取得します。opkg を使う機種には IPK、apk を使う機種には APK を選びます。依存関係はファームウェアに合うフィードから取得してください。

[GitHub Releases](https://github.com/beezcheyenna/Proxy-Guard/releases)

ダウンロードしたファイル名を指定します。最初の行は IPK 用です。APK の場合は次のコメント行にあるファイル名を使います。

```sh
PG_PACKAGE=luci-app-proxy-guard_1.0.0-8_all.ipk
# PG_PACKAGE=luci-app-proxy-guard-1.0.0-r8.apk
awk -v f="$PG_PACKAGE" '$2 == f { print; n++ } END { if (n != 1) exit 1 }' SHA256SUMS > SHA256SUMS.selected &&
sha256sum -c SHA256SUMS.selected
```

選択したパッケージの検証結果が OK であることを確認します。macOS では `shasum -a 256 "$PG_PACKAGE"` を実行し、完全なハッシュを `SHA256SUMS` の該当行と比較できます。

SHA256 でファイルと一覧の一致を確認します。配布元の本人性は別途確認し、信頼できる同一リリースから一覧とパッケージを入手してください。apk 対応機でオフラインインストールする場合は、対応する依存関係を先に用意します。

<a id="installation"></a>

## インストールと削除

ファームウェアに対応するコマンドを使います。保護の確認中は独立した管理経路を確保してください。

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="guide-setup"></a>

## 初回設定

「サービス → プロキシ接続保護」でウィザードを開き、入口インターフェース、IPv4 と IPv6 の範囲、ローカル例外、SOCKS ポートを確認します。最初は監視専用で試します。保存して適用すると自己検査が実行され、確認時間は 30 秒です。検査に失敗した場合や確認しなかった場合は元の設定に戻ります。

既定の公式 HTTPS はローカル SOCKS 経由で固定アドレスへ接続します。外部 HTTPS には独立した間隔としきい値があります。出口 IPv4 の照合は初期状態では無効で、有効にすると既定で公式応答のアドレスを使います。外部 IP サービスは主アドレスがタイムアウトした場合だけ予備を試します。

公式 HTTPS の既定値は、間隔 3 秒、タイムアウト 2 秒、失敗と成功の判定がそれぞれ連続 2 回です。外部 HTTPS の既定値は間隔 10 秒、各接続先のタイムアウト 4 秒、連続失敗 3 回と連続成功 2 回です。既定で gstatic と Ubuntu を使い、通常時は各回で少なくとも一方の応答が必要です。

外部のテキスト IP 取得先が両方タイムアウトしても、接続確認に合格していれば通信を継続できます。すでに不一致を確認した場合は、一致する IPv4 を取得して復旧します。

ルールの確認が済むまで「この設定を維持」ボタンは無効です。元のカウントダウンは続きます。時間切れになると、ページを閉じていてもルーターが以前の設定に戻します。

<a id="test-current-proxy"></a>

## 現在のプロキシをテスト

「現在のプロキシをテスト」は保存前のフォームの設定で SOCKS 経由の接続を試し、結果、応答時間、取得できた出口 IPv4 を表示します。保護設定は「保存して適用」で反映されます。

状態欄には連続失敗回数と有効な遮断理由が表示されます。しきい値未満の失敗では通信が継続する場合があります。定時保護、API による一時遮断、接続障害は同時に起こり得ます。

ローカル API は新規インストール時に無効です。有効にすると、LuCI に表示される UUID で状態照会、診断、時間制限付き遮断とその取り消しができます。

## 起動時の保護を確認する

独立した管理経路を確保し、Proxy Guard を実行しているルーターを再起動します。保護対象端末から、ルーターの起動中はインターネット通信が遮断され、設定した復旧チェックに合格すると再開することを確認します。

<a id="local-api"></a>

## ローカル API

LuCI の「LAN 制御 API」を有効にし、「保存して適用」を選びます。確認画面が表示された場合は設定を確定してください。同じタブに表示される **API UUID** をコピーします。この UUID は 4 つのエンドポイントの認証に使用します。API を無効にして再び有効にすると UUID が変わります。

LAN 内からルーターの既存の管理用 HTTPS アドレスにリクエストを送ります。「API 更新先」で標準ハートビートまたは詳細診断の `/f` を選択できます。

| HTTP メソッド | `/cgi-bin/proxy-guard-api` に続くパス | 用途 |
| --- | --- | --- |
| GET | `/status` | 保護状態と有効な API 遮断を取得 |
| GET | `/diagnostics` | 選択したハートビートを SOCKS 経由で確認し、結果を返す |
| POST | `/block` | 時間制限付き遮断を開始 |
| POST | `/cancel` | リクエスト ID を指定して遮断を取り消す |

`router.example` をルーターの管理用 HTTPS アドレスに、`YOUR_UUID` を LuCI に表示された UUID に置き換えます。

```http
GET /cgi-bin/proxy-guard-api/diagnostics HTTP/1.1
Host: router.example
Authorization: Bearer YOUR_UUID
```

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

両方の POST で `Content-Type: application/json` を指定します。`/block` の本文は `{"seconds":120,"request_id":"sample-block-01"}`、`/cancel` の本文は `{"request_id":"sample-block-01"}` です。時間を省略するか 0 を指定すると既定値を使用します。ID を省略するとルーターが発行します。時間制限付き遮断には保護モードが必要です。有効な ID を同じ時間で再送しても当初の終了時刻を維持します。取り消し後も他の遮断条件は適用されます。

認証済みの応答には `uuid` が含まれます。診断に成功すると `diagnostics.headers` に `X-PGHB-*` の `name` と `value` が順に入り、同名のヘッダーと文字列の値も保持されます。UTF-8 以外の値には `encoding: "base64"` が付きます。HTTP 401 は UUID がないか無効、403 は無効化または現在のネットワークから利用不可、429 は待機時間中または要求数の上限、502/504 は検査失敗またはタイムアウトを表します。

プラグインの設定権限を持つ LuCI ユーザーは、イベントログで認証済みリクエストの UUID を確認できます。ログを共有するときは UUID を伏せてください。

[ユーザーガイド](USER-GUIDE.ja.md) · [復旧](RECOVERY.ja.md)
