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

ファームウェアに対応するコマンドを使います。以下の APK インストール例は `--no-network` を使用します。依存パッケージは事前にインストールするか、ローカルリポジトリに用意してください。設定済みの対応フィードから不足する依存パッケージを取得する場合は、`--no-network` を外します。保護を確認する前に、独立した管理経路を確保してください。

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="from-0-3"></a>

## 0.3 から 1.0 への移行

1.0 は新しい設定で使い始めてください。公開済みの 0.3 パッケージから 1.0 への上書き更新と、1.0 から 0.3 へのダウングレードは、サポート対象の移行手順として検証されていません。どちらのパッケージも `/etc/config/proxy_guard` を設定ファイルとして扱うため、変更済みの 0.3 のファイルが残る場合があります。インストーラーは判別できる一部の旧既定値を更新し、一部の不足項目を補います。残った設定を 1.0 で使う前に内容を確認してください。

独立した管理経路を確保し、0.3 の設定をバックアップしてください。旧環境を復元するために必要な認証情報と対応するパッケージは安全な場所に保管します。旧版のルーター保護を明示的に無効にし、Pro を導入している場合は下記の VPS ポリシーを処理してから先に Pro を削除します。その後で 0.3 Standard を削除し、1.0 をインストールします。旧設定が残っている場合は「設定と診断 → 初期設定に戻して再設定」を選びます。確認済みの保護範囲、例外、SOCKS 設定、スケジュールだけを入力し直してください。

1.0 の初期設定では公式 HTTPS が選ばれ、出口 IPv4 の照合は無効です。残った旧設定に接続確認方式がなければ、1.0 は公式 HTTPS を使います。以前の gstatic と Ubuntu を継続して使う場合は、接続確認の設定でサードパーティー HTTPS を選択します。

0.3 Pro が VPS を管理している場合は、制御できるうちに削除したいポリシーを 0.3 Pro で解除し、VPS 上で結果を確認します。1.0 には 0.3 Pro との連携機能がありません。VPS のルール、Agent、Cloudflare リソースは個別に扱ってください。 [旧版の復旧ガイド](https://github.com/beezcheyenna/Proxy-Guard/blob/987ff38a25c1a00f2c05753f7503e134391a4a3a/docs/RECOVERY.ja.md)

[0.3 のソース、パッケージ、ドキュメント](../archive/0.3/README.md)


<a id="guide-setup"></a>

## 初回設定

**Proxy Guard のサービスを停止しても、ファイアウォールによる遮断は続くことがあります。** 遮断を解除するには、保護を明示的に無効にするか、[復旧手順](RECOVERY.ja.md)に従ってください。

**「現在のプロキシをテスト」が成功しても、確認できるのはそのテストの通信です。** スケジュール、API による一時遮断、別の稼働確認の失敗によって、遮断が続くことがあります。

「サービス → プロキシ接続保護」でウィザードを開き、入口インターフェース、IPv4 と IPv6 の範囲、ローカル例外、SOCKS ポートを確認します。最初は監視専用で試します。保存して適用すると自己検査が実行され、確認時間は 30 秒です。検査に失敗した場合や確認しなかった場合は元の設定に戻ります。

既定の公式 HTTPS はローカル SOCKS 経由で固定アドレスへ接続します。外部 HTTPS には独立した間隔としきい値があります。出口 IPv4 の照合は初期状態では無効で、有効にすると既定で公式応答のアドレスを使います。外部 IP サービスは主アドレスがタイムアウトした場合だけ予備を試します。

既定では、公式 HTTPS は検査終了後に 3 秒待ち、リクエストは 2 秒でタイムアウトします。外部 HTTPS は 1 ラウンドの検査終了後に 10 秒待ち、接続先ごとのタイムアウトは 4 秒です。既定の接続先は gstatic と Ubuntu で、通常時は各ラウンドで少なくとも一方の検査に成功する必要があります。保護モードの通常監視では、公式は 2 回、外部は 3 ラウンドの連続失敗で障害と判定します。復旧の既定値は、どちらも 2 回または 2 ラウンドの連続成功です。重点監視中は、1 回の失敗で遮断されることがあります。

外部のテキスト IP 取得先が両方タイムアウトしても、接続検査が成功し、未解消の IP 不一致がなければ、今回の IP 照合だけを理由に遮断することはありません。既定の `https://api.ipify.org/` がタイムアウトした場合は `https://4.ident.me/` を使用します。主アドレスを変更して予備を設定していない場合、タイムアウトは照合不能として設定中のモードと失敗しきい値で処理されます。確認済みの不一致から復旧するには、期待値と一致する IPv4 が必要です。

ルールの確認が済むまで「この設定を維持」ボタンは無効です。元のカウントダウンは続きます。時間切れになると、ページを閉じていてもルーターが以前の設定に戻します。

<a id="test-current-proxy"></a>

## 現在のプロキシをテスト

「現在のプロキシをテスト」は保存前のフォームの設定で SOCKS 経由の接続を試し、結果、応答時間、取得できた出口 IPv4 を表示します。同じダイアログの「詳細診断を実行」は適用済みのプロキシ設定を使用します。保護設定は「保存して適用」で反映されます。

状態欄には連続失敗回数と有効な遮断理由が表示されます。しきい値未満の失敗では通信が継続する場合があります。定時保護、API による一時遮断、接続障害は同時に起こり得ます。

ローカル API は新規インストール時に無効です。有効にすると、LuCI に表示される UUID で状態照会、診断、時間制限付き遮断とその取り消しができます。

## 起動時の保護を確認する

独立した管理経路を確保し、Proxy Guard を実行しているルーターを再起動します。保護対象端末から、ルーターの起動中はインターネット通信が遮断され、設定した復旧チェックに合格すると再開することを確認します。

<a id="local-api"></a>

## ローカル API

LuCI の「LAN 制御 API」で API を有効にし、「保存して適用」を選びます。確認が表示されたら設定を確定し、同じタブの **API UUID** をコピーします。各リクエストに `Authorization: Bearer YOUR_UUID` を付けます。

**UUID はアクセス用の認証情報です。** API を無効にして再度有効にすると、新しい UUID が生成されます。API を有効にしたままルーターを再起動した場合も変わります。呼び出し元の設定を更新してください。呼び出しに LuCI へのログインは不要です。認証と送信元の確認を通過した応答には UUID が含まれ、管理者は LuCI のイベントログでも確認できます。応答やログを共有する前に UUID を伏せてください。

**ルーターで既に使っている管理用 HTTPS アドレスにアクセスします。** ループバック、または `lan` という名前のファイアウォールゾーンに属するデバイスから送信元へ直接戻れる通信を受け付けます。戻り経路に別のゲートウェイが必要な送信元は拒否されます。別の LAN ゾーン、ルーティングされた VLAN、VPN からの通信には `403 lan_required` が返る場合があります。証明書に記載されたホスト名を使ってください。プライベート CA または自己署名証明書を使う場合は、curl の `--cacert` で信頼する CA またはルーターの証明書を指定できます。

`router.example` をルーターの管理用 HTTPS ホスト名、`YOUR_UUID` を現在の API UUID に置き換えます。以下の JSON は例です。POST は設定した保護範囲のインターネット接続を変更するため、必要なときだけ実行してください。

| メソッド | パス | 用途 |
| --- | --- | --- |
| GET | [`/status`](#api-status) | 保護状態を取得 |
| GET | [`/diagnostics`](#api-diagnostics) | 一度だけ診断 |
| POST | [`/block`](#api-block) | 一時遮断を開始 |
| POST | [`/cancel`](#api-cancel) | 一時遮断を取り消す |

<a id="api-status"></a>

### 保護状態を取得する

`GET /status` はファイアウォールによる現在の遮断状態と有効な API 遮断要求を返します。以下は一件の一時遮断が有効な例です。プログラムでは `enforcement` と `block_reasons` を使います。`reason` は表示用です。`last_check` は直近の完了した検査の Unix 時刻（秒）で、検査の記録がなければ省略される場合があります。状態が不明、ルールが欠落、または未確認の場合は `blocked` も省略される場合があります。これらの状態は `enforcement` で判別します。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/status'
```

HTTP 200

```json
{
  "ok": true,
  "api_version": 2,
  "uuid": "YOUR_UUID",
  "enabled": true,
  "mode": "guard",
  "check_mode": "web",
  "phase": "blocked",
  "enforcement": "blocked",
  "blocked": true,
  "reason": "API 限时断网生效中",
  "block_reasons": [
    "api"
  ],
  "failure_progress": {
    "count": 0,
    "threshold": 3
  },
  "last_check": 1794628800,
  "stale": false,
  "heartbeat": {
    "enabled": false,
    "allowed": true
  },
  "api": {
    "enabled": true,
    "count": 1,
    "remaining": 95
  },
  "requests": [
    {
      "request_id": "example-block-01",
      "remaining": 95
    }
  ],
  "default_seconds": 300,
  "max_seconds": 3600,
  "exit_check": {
    "enabled": false
  }
}
```

<a id="api-diagnostics"></a>

### 診断を実行する

`GET /diagnostics` はローカル SOCKS を経由して検査を実行し、同じリクエストの応答に結果を返します。「API 更新先」は既定で PGHB `/` です。例の詳細ヘッダーを取得するには、先に `/f` を選んで適用してください。 [PGHB の応答仕様](PGHB.ja.md)

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "diagnostics": {
    "ok": true,
    "source": "https://hb.pghb.app/f",
    "checked_at": 1794628800,
    "http_code": 200,
    "curl_code": 0,
    "milliseconds": 117,
    "nonce_verified": true,
    "headers": [
      {
        "name": "x-pghb-ip",
        "value": "203.0.113.10"
      },
      {
        "name": "x-pghb-tls",
        "value": "TLSv1.3"
      },
      {
        "name": "x-pghb-nonce",
        "value": "0123456789abcdef0123456789abcdef"
      }
    ]
  }
}
```

`diagnostics.headers` は `X-PGHB-*` の名前と値を応答の順序で返します。値は文字列です。`X-PGHB-IP` または `X-PGHB-Nonce` が重複すると検証に失敗します。その他の重複ヘッダーは別の項目として返せます。UTF-8 以外の値には `"encoding":"base64"` が付きます。`checked_at` は Unix 時刻（秒）です。

<a id="api-block"></a>

### 一時遮断を開始する

`POST /block` は保護モードが有効な状態で、設定した保護範囲を遮断します。既定は 300 秒、初期上限は 3600 秒です。`seconds` の省略または `0` で設定済みの既定値を使います。`request_id` の省略時はルーターが ID を生成します。指定する場合は英数字、ハイフン、アンダースコアの 8〜64 文字を使います。有効な ID を同じ時間で再送しても期限は変わりません。時間が異なると `409 request_conflict` になります。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"seconds":120,"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/block'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "effective": true,
  "remaining": 120,
  "seconds": 120
}
```

<a id="api-cancel"></a>

### 一時遮断を取り消す

`POST /cancel` には取り消す要求の ID が必要です。所有者は認証済み UUID と要求 ID の組み合わせで識別します。同じ UUID を使う端末やプログラムは同じ所有者として扱われます。有効な形式の ID で、要求が期限切れまたは見つからない場合も、`cancelled: true` が返ることがあります。`effective` と `remaining` は残っている API の遮断を表します。スケジュールや稼働確認の失敗による遮断は継続する場合があります。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/cancel'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "cancelled": true,
  "effective": false,
  "remaining": 0
}
```

### よくあるエラー

| HTTP ステータスとエラー | 確認項目 |
| --- | --- |
| 401 `authentication_required` | UUID がないか無効です。LuCI に表示される現在の値を確認してください。 |
| 403 `https_required`、`api_disabled`、`lan_required` | HTTPS、API の有効化、または `lan` ゾーンへの経路を確認してください。 |
| 409 `configuration_pending`、`configuration_changed`、`protection_not_active`、`request_conflict` | 設定を確定してから診断をやり直すか、保護モードと要求 ID に対応する遮断時間を確認してください。 |
| 429 | 診断の間隔制限か有効な要求数の上限です。`Retry-After` があれば指定された時間だけ待ってください。 |
| 502 / 504 | 診断の検査に失敗したかタイムアウトしました。`diagnostics` があれば詳細を確認してください。 |
| 503 `busy` | 別の処理を実行中です。`Retry-After` で指定された秒数を待ってから再試行してください。 |
| 503 `policy_not_ready`、`request_state_unavailable`、`firewall_failed` | ファイアウォールのポリシーが未準備、要求の状態が取得不能、またはルールの更新に失敗しました。保護状態とイベントログを確認してから、同じ要求 ID で再試行してください。 |

[ユーザーガイド](USER-GUIDE.ja.md) · [障害からの復旧](RECOVERY.ja.md)
