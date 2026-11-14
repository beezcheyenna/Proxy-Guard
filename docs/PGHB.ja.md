# PGHB ハートビートと診断

[English](PGHB.en.md) · [简体中文](PGHB.md) · [日本語](PGHB.ja.md) · [Русский](PGHB.ru.md) · [فارسی](PGHB.fa.md)

## どのエンドポイントを使うか

| エンドポイント | 用途 |
| --- | --- |
| 公式 PGHB `https://hb.pghb.app/` | ローカル SOCKS 経由の簡易接続確認。出口 IPv4 の照合を有効にすると同じ応答を利用できます。 |
| 公式 PGHB `https://hb.pghb.app/f` | 必要なときに詳しい接続情報を取得します。LuCI の「現在のプロキシをテスト」から「詳細診断を実行」を選びます。ルーターの設定で LAN API の診断先にも選べます。 |
| ルーターの `/cgi-bin/proxy-guard-api/*` | 認証付きの LAN 制御 API。状態取得、診断、一時遮断の開始と取り消しに使います。ルーターの HTTPS アドレスと API UUID を指定します。 [LAN API のリクエストと応答](USAGE.ja.md#local-api) |

「現在のプロキシをテスト」は保存前のフォームの設定を使い、「詳細診断を実行」は適用済みのプロキシ設定を使います。診断の成功で確認できるのは、SOCKS を経由したそのリクエストです。通信を通しているかは現在の保護状態で確認してください。

## Proxy Guard 1.0 の検証規則

- PGHB が HTTP `200` と、`ネットは広大だわ` に完全一致する本文を返す必要があります。UTF-8 で 24 バイト、改行と BOM は含みません。
- `/f` では新しい `X-PGHB-Nonce` を送り、同じ値が応答に含まれることを診断の合格条件にします。診断用の乱数は別に生成し、API UUID はルーターの HTTPS API にのみ送ります。
- ヘッダー名の大文字と小文字は区別しません。同じブロック内に `X-PGHB-IP` または `X-PGHB-Nonce` が重複すると検証に失敗します。他の診断ヘッダーの重複は別の項目として返せます。値が曖昧な任意の概要項目は省略します。
- 読み取る HTTP 応答ヘッダーの上限は **32 KiB（32,768 バイト）** です。取得した診断ヘッダーの配列も JSON 化した状態で **32 KiB** 以内に収まる必要があります。どちらも書式を含めた全体の制限です。
- PGHB で出口 IPv4 を照合するときは、`X-PGHB-IP` に期待値と一致する IPv4 が必要です。国や地域、ASN、ブラウザーのヘッダーなどは任意の診断情報で、欠落しても接続確認には影響しません。

診断の `X-PGHB-*` は応答順の文字列として返り、UTF-8 以外には `"encoding":"base64"` が付きます。サーバーで追加した正しい形式の `X-PGHB-*` も診断結果に含められます。このページはプラグインが現在使っている応答の仕様を記録しています。

## 詳細応答の項目

`/f` の設定一覧には **102 個のヘッダー** があります。実際に返る項目はリクエストによって少なくなります。動的な値が空または未定義の場合、Cloudflare がヘッダーを省略することがあります。一部の計測値は取得できない場合に `0` を返します。「欠落・取得不可」は値が省略されたり、診断に使えなかったりする条件を示します。ダッシュは数値の単位がないことを示します。 [Cloudflare の応答ヘッダー規則](https://developers.cloudflare.com/rules/transform/response-header-modification/#important-remarks) · [フィールドの一覧](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/)

簡易応答の `/` は IP、国・地域、ASN、TLS、Ray の五項目を使います。IP は Cloudflare が接続元として観測したアドレスです。SOCKS 経由の要求ではプロキシの出口が反映されます。

結果を共有する前に、アドレス、推定位置、TLS 識別子、Cookie・Authorization・URL のクエリなどリクエストから返された値を確認し、機密情報を伏せてください。 [プライバシー](PRIVACY.ja.md)

### 接続、経路、TLS

| ヘッダー | Cloudflare の式または固定値 | 単位 | 欠落・取得不可 | 検証での用途 |
| --- | --- | --- | --- | --- |
| `X-PGHB-IP` | `to_string(ip.src)` | — | IPv6 のみでは IPv4 を照合できない | 任意の出口 IPv4 照合 |
| `X-PGHB-Country` | `ip.src.country` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-ASN` | `to_string(ip.src.asnum)` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-City` | `ip.src.city` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Region` | `ip.src.region` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Region-Code` | `ip.src.region_code` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Continent` | `ip.src.continent` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Latitude` | `ip.src.lat` | 度 | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Longitude` | `ip.src.lon` | 度 | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Metro-Code` | `ip.src.metro_code` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Postal-Code` | `ip.src.postal_code` | — | IP の位置情報または ASN を取得できない | なし |
| `X-PGHB-Client-Port` | `to_string(cf.edge.client_port)` | — | トランスポート情報を取得できない | なし |
| `X-PGHB-Client-TCP` | `to_string(cf.edge.client_tcp)` | — | トランスポート情報を取得できない | なし |
| `X-PGHB-Edge-IP` | `to_string(cf.edge.server_ip)` | — | エッジのデータを取得できない | なし |
| `X-PGHB-Edge-Port` | `to_string(cf.edge.server_port)` | — | エッジのデータを取得できない | なし |
| `X-PGHB-HTTP` | `http.request.version` | — | 通常は取得可能 | なし |
| `X-PGHB-SSL` | `to_string(ssl)` | — | 通常は取得可能 | なし |
| `X-PGHB-Delivery-Rate` | `to_string(cf.edge.l4.delivery_rate)` | バイト/秒 | L4 統計がない場合は `0` | なし |
| `X-PGHB-TCP-RTT` | `to_string(cf.timings.client_tcp_rtt_msec)` | ミリ秒 | TCP 以外では `0` | なし |
| `X-PGHB-QUIC-RTT` | `to_string(cf.timings.client_quic_rtt_msec)` | ミリ秒 | QUIC 以外では `0` | なし |
| `X-PGHB-Edge-Time` | `to_string(cf.timings.edge_msec)` | ミリ秒 | エッジのデータを取得できない | なし |
| `X-PGHB-Origin-TTFB` | `to_string(cf.timings.origin_ttfb_msec)` | ミリ秒 | キャッシュヒットなどでオリジン計測がない | なし |
| `X-PGHB-Worker-Time` | `to_string(cf.timings.worker_msec)` | ミリ秒 | Worker の実行または計測データがない | なし |
| `X-PGHB-Ray` | `cf.ray_id` | — | 通常は取得可能 | なし |
| `X-PGHB-Zone` | `cf.zone.name` | — | エッジのデータを取得できない | なし |
| `X-PGHB-TLS` | `cf.tls_version` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-Cipher` | `cf.tls_cipher` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-TLS-Hello` | `to_string(cf.tls_client_hello_length)` | バイト | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-Ciphers-SHA1` | `cf.tls_client_ciphers_sha1` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-TLS-Extensions` | `cf.tls_client_extensions_sha1` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-Extensions-LE` | `cf.tls_client_extensions_sha1_le` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-TLS-Client-Random` | `cf.tls_client_random` | — | TLS ハンドシェイク情報を取得できない | なし |
| `X-PGHB-MTLS-Presented` | `to_string(cf.tls_client_auth.cert_presented)` | — | mTLS を使わない場合は通常 `false` | なし |
| `X-PGHB-MTLS-Verified` | `to_string(cf.tls_client_auth.cert_verified)` | — | mTLS を使わない場合は通常 `false` | なし |

### リクエスト情報と反映値

| ヘッダー | Cloudflare の式または固定値 | 単位 | 欠落・取得不可 | 検証での用途 |
| --- | --- | --- | --- | --- |
| `X-PGHB-Host` | `http.host` | — | 通常は取得可能 | なし |
| `X-PGHB-Method` | `http.request.method` | — | 通常は取得可能 | なし |
| `X-PGHB-Path` | `http.request.uri.path` | — | 通常は取得可能 | なし |
| `X-PGHB-URI` | `http.request.uri` | — | 通常は取得可能 | なし |
| `X-PGHB-Full-URI` | `http.request.full_uri` | — | 通常は取得可能 | なし |
| `X-PGHB-Raw-Path` | `raw.http.request.uri.path` | — | 通常は取得可能 | なし |
| `X-PGHB-Raw-URI` | `raw.http.request.uri` | — | 通常は取得可能 | なし |
| `X-PGHB-Raw-Full-URI` | `raw.http.request.full_uri` | — | 通常は取得可能 | なし |
| `X-PGHB-Query` | `http.request.uri.query` | — | クエリ文字列がない | なし |
| `X-PGHB-Raw-Query` | `raw.http.request.uri.query` | — | クエリ文字列がない | なし |
| `X-PGHB-URI-Extension` | `http.request.uri.path.extension` | — | パスに拡張子がない | なし |
| `X-PGHB-Timestamp` | `to_string(http.request.timestamp.sec)` | Unix 秒 | エッジのデータを取得できない | なし |
| `X-PGHB-Received-MS` | `to_string(http.request.timestamp.msec)` | 秒未満のミリ秒（0〜999） | エッジのデータを取得できない | なし |
| `X-PGHB-Request-ID` | `uuidv4(cf.random_seed)` | — | 通常は取得可能 | なし |
| `X-PGHB-Headers-Truncated` | `to_string(http.request.headers.truncated)` | — | 通常は取得可能 | なし |
| `X-PGHB-Verified-Bot` | `to_string(cf.client.bot)` | — | 通常は取得可能 | なし |
| `X-PGHB-Verified-Bot-Category` | `cf.verified_bot_category` | — | Bot の分類を取得できない | なし |
| `X-PGHB-Nonce` | `http.request.headers["x-pghb-nonce"][0]` | — | リクエストに Nonce がない場合は省略 | `/f` の Nonce 照合 |
| `X-PGHB-Accept` | `http.request.headers["accept"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Accept-Encoding` | `http.request.headers["accept-encoding"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Accept-Language` | `http.request.headers["accept-language"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Authorization` | `http.request.headers["authorization"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Cookie` | `http.cookie` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-User-Agent` | `http.user_agent` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Origin` | `http.request.headers["origin"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Referer` | `http.referer` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Range` | `http.request.headers["range"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-DNT` | `http.request.headers["dnt"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-GPC` | `http.request.headers["sec-gpc"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Save-Data` | `http.request.headers["save-data"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Upgrade-Insecure` | `http.request.headers["upgrade-insecure-requests"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Sec-Purpose` | `http.request.headers["sec-purpose"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Fetch-Dest` | `http.request.headers["sec-fetch-dest"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Fetch-Mode` | `http.request.headers["sec-fetch-mode"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Fetch-Site` | `http.request.headers["sec-fetch-site"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Fetch-User` | `http.request.headers["sec-fetch-user"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Client-Hints-UA` | `http.request.headers["sec-ch-ua"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Client-Hints-Mobile` | `http.request.headers["sec-ch-ua-mobile"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Client-Hints-Platform` | `http.request.headers["sec-ch-ua-platform"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-UA-Arch` | `http.request.headers["sec-ch-ua-arch"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-UA-Bitness` | `http.request.headers["sec-ch-ua-bitness"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-UA-Full-Version-List` | `http.request.headers["sec-ch-ua-full-version-list"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-UA-Platform-Version` | `http.request.headers["sec-ch-ua-platform-version"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Top-Language` | `http.request.accepted_languages[0]` | — | 優先言語を取得できない | なし |
| `X-PGHB-If-Match` | `http.request.headers["if-match"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-If-Modified-Since` | `http.request.headers["if-modified-since"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-If-None-Match` | `http.request.headers["if-none-match"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-If-Unmodified-Since` | `http.request.headers["if-unmodified-since"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Request-Cache-Control` | `http.request.headers["cache-control"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Request-Content-Length` | `http.request.headers["content-length"][0]` | バイト | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Request-Content-Type` | `http.request.headers["content-type"][0]` | — | リクエストにヘッダーまたは値がない | なし |
| `X-PGHB-Request-Priority` | `http.request.headers["priority"][0]` | — | リクエストにヘッダーまたは値がない | なし |

### 応答情報と定数

| ヘッダー | Cloudflare の式または固定値 | 単位 | 欠落・取得不可 | 検証での用途 |
| --- | --- | --- | --- | --- |
| `X-PGHB-Response-Code` | `to_string(http.response.code)` | — | 通常は取得可能 | なし |
| `X-PGHB-Response-Type` | `http.response.content_type.media_type` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-Cache-Control` | `http.response.headers["cache-control"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-Content-Length` | `http.response.headers["content-length"][0]` | バイト | 応答に元の項目がない | なし |
| `X-PGHB-Response-Encoding` | `http.response.headers["content-encoding"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-ETag` | `http.response.headers["etag"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-Age` | `http.response.headers["age"][0]` | 秒 | 応答に元の項目がない | なし |
| `X-PGHB-Response-Last-Modified` | `http.response.headers["last-modified"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-Location` | `http.response.headers["location"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Response-Vary` | `http.response.headers["vary"][0]` | — | 応答に元の項目がない | なし |
| `X-PGHB-Error-Code` | `to_string(cf.response.1xxx_code)` | — | Cloudflare 1xxx エラーがなければ `0` | なし |
| `X-PGHB-Error-Type` | `cf.response.error_type` | — | Cloudflare のエラー種別がない | なし |
| `X-PGHB-Endpoint` | `full` | — | `/f` の固定値 | なし |
| `X-PGHB-Heartbeat-Version` | `1` | — | `/f` の固定値 | なし |
| `X-PGHB-Schema-Version` | `1` | — | `/f` の固定値 | なし |
| `X-PGHB-Service` | `PGHB` | — | `/f` の固定値 | なし |

検証に使う二項目にはそれぞれ役割があります。どちらも上記の重複ヘッダー規則の対象です。実際の HTTP ステータスは別に検証し、`X-PGHB-Response-Code` の文字列は診断にのみ使います。

TCP と QUIC の RTT は Cloudflare までの接続に関する測定です。ルーター API の `milliseconds` はルーターからの検査にかかった時間です。Cloudflare の受信時刻は秒単位の `Timestamp` と秒未満の `Received-MS` を組み合わせます。`Edge-IP` は Cloudflare のエッジ側アドレス、`IP` は観測した送信元アドレスです。

[ユーザーガイド](USER-GUIDE.ja.md) · [LAN API](USAGE.ja.md#local-api) · [応答解析のソース](../package/root/usr/lib/proxy-guard/public-heartbeat.lua#L45-L95)
