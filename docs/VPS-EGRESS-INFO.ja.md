# 読み取り専用の IPv4 出口候補（スキーマ 1）

[English](VPS-EGRESS-INFO.md) · [简体中文](VPS-EGRESS-INFO.zh-CN.md) · [日本語](VPS-EGRESS-INFO.ja.md) · [Русский](VPS-EGRESS-INFO.ru.md) · [فارسی](VPS-EGRESS-INFO.fa.md)

ウィザードに候補と根拠を返す API です。想定 IPv4 の設定、ポリシー適用、家庭リース、SSH の制御・経路ハートビート、保守、確認待ちの期限は変更しません。インターフェース、パネル設定、ホスト既定経路の測定は別々の根拠です。実プロキシ経路を別途確認します。

## API

- Cloudflare は `POST /v1/egress-info` と機器 Bearer、JSON `{"device_id":"home"}` を使います。`luci.jsonc` では空 Lua テーブルが配列になるため、空でないオブジェクトを送ります。
- Agent 中継は `POST /v1/egress-info` を既存 HMAC で署名し、`device_id`、`issued_at`、一意の `request_id`、`purpose:"egress-info"` を指定します。この用途は他の経路で拒否されます。リプレイと期限切れ nonce も拒否します。
- 直接制御は `GET /v1/direct/egress-info`、既存の直接 Bearer と HTTPS・公開バインド条件を使います。対向 IP は候補にしません。

公開候補がない応答例:

```json
{
  "ok": true,
  "protocol": 3,
  "egress_info_schema": 1,
  "generated_at": 1700000000,
  "status": "unavailable",
  "candidates": [],
  "ambiguous": false,
  "business_egress_verified": false,
  "warnings": [
    "measurement_disabled",
    "no_public_ipv4_candidate"
  ],
  "measurement": {
    "state": "disabled",
    "checked_at": null,
    "stale": true
  }
}
```

候補の例は `{"ipv4":"8.8.8.8","evidence":[{"source":"interface","checked_at":1700000000,"scope":"host_interface"}]}` です。アドレスは形式の例です。`source` は `interface`、`panel`、`measured`、対応する `scope` は `host_interface`、`panel_config`、`host_default_ipv4` です。時刻と `generated_at` は UTC Unix 秒、鮮度は単調時計です。IPv4 で重複を除き、候補は 8 件まで、各根拠は 3 件までです。切り詰め時は測定値を優先します。異なる公開 IPv4 が複数なら警告を付けます。スキーマ 1 の `business_egress_verified` は常に false です。先頭候補、自分の `/observe`、パネル名、REALITY 宛先を自動入力しないでください。

`status` は `available`、`partial`、`unavailable` で、サービス正常性とは独立です。`measurement.state` は `disabled`、`pending`、`fresh`、`stale`、`unavailable`、`conflict` です。エラーまたは測定間隔の 2 倍を過ぎると前回値は期限切れです。測定無効でも稼働中の保護は維持します。

警告コード: `non_public_ipv4_omitted`, `no_public_ipv4_candidate`, `interface_unavailable`, `panel_unavailable`, `panel_hint_unverified`, `panel_hint_ignored`, `measurement_disabled`, `measurement_pending`, `measurement_failed`, `measurement_stale`, `measurement_disagreement`, `multiple_public_ipv4_candidates`, `host_default_not_business_egress`, `candidates_truncated`。UI は既存の辞書を使います。

認証済みの空・期限切れ・曖昧な結果は 200、直接認証失敗 401、署名・nonce 失敗 403、不正な本文 400、旧 Agent 501 `egress_info_unsupported`、VPC や応答の異常 502、収集エラー 503 です。エラーに生のパス、パネルデータ、機器名、測定本文、秘密情報は含めません。`Cache-Control: no-store` を維持し、キャッシュはメモリーのみです。

## Agent の設定と制限

任意の `egress` は次のキーだけを受け付けます。

```json
{
  "panel_config_path": "",
  "measure_enabled": false,
  "measure_interval": 300
}
```

パネル収集は既定で無効です。明示した通常 JSON は Agent ユーザーが所有し、グループ・他ユーザーは書き込めず、末尾要素はシンボリックリンク不可です。最大 64 KiB を読みます。3x-ui の Xray 設定では `inbounds[].listen`、`outbounds[].sendThrough` の数値 IPv4 だけを未検証ヒントとします。REALITY、リモート宛先、ドメイン、秘密情報を探索・解決しません。

インターフェースは固定の `ip -j -4 address show` を 2 秒、最大 64 KiB で読み、15 秒キャッシュします。ツールがないか非公開・NAT のアドレスだけなら警告を返します。

測定は既定で無効です。有効時はバックグラウンドで固定の [ipify IPv4 API](https://api.ipify.org/) のみを使います。URL、コマンド、更新、対象は指定できません。DNS は公開 IPv4 に絞り、選んだ IP の TLS ソケットで固定名を SNI と証明書に使います。プロキシ環境変数、転送、再試行、認証情報は使いません。ソケットは 2 秒、本文 256 バイト、子プロセスは DNS を含め 5 秒です。間隔は 60～3600 秒、既定 300 秒です。API 読み取りで測定は始まりません。測定はホスト既定 IPv4 として表示します。

## 連携

`--check-config` が `egress` を検証します。インストーラーは `egress.py` を含み、`control.Server` が収集を管理します。ウィザードは接続のみの設定で、同期停止中も読めます。入口確認、セッションの一時資格情報、RPC 権限を維持します。読み取りはコミット・適用・保守登録を行わず、RPC 内で測定要求を実行しません。

## 隔離環境の基本試験

所有するテスト VM で対象の候補・凍結版を使って実行します。

```sh
python3 -B companion/vps/test_egress.py
cd companion/worker
node --test test/egress.test.mjs test/worker.test.mjs test/regression.test.mjs test/contract.test.mjs
```

収集試験は測定値を注入し、外部に要求しません。HTTP 契約試験は実 Agent とメモリーのファイアウォールドライバーを使い、実 nft を変更しません。インストール、実プロキシ経路、Cloudflare は別途確認します。
