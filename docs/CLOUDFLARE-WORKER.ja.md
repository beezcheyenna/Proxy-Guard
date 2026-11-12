# Pro 用 Cloudflare Worker

[English](CLOUDFLARE-WORKER.en.md) · [简体中文](CLOUDFLARE-WORKER.md) · [日本語](CLOUDFLARE-WORKER.ja.md) · [Русский](CLOUDFLARE-WORKER.ru.md) · [فارسی](CLOUDFLARE-WORKER.fa.md)

Worker は機器を認証し、家庭側の公開 IP を観測して、Agent プロトコル v3 でポリシーを中継します。互換性のある Pro と VPS Agent が必要です。Worker 1 つにつき機器 ID は 1 組で、`VPS_API` のバインディング先も固定です。

## 依存関係とローカル検証

Node.js 22 以降を使います。`package-lock.json` は Wrangler 4.156.0 と Miniflare 5.20261023.3-beta を固定しています。配備にはインストール済みの Wrangler を使います。ツールや `wrangler.jsonc` の互換性日付（現在は `2026-11-01`）を変更したら、実行環境を再確認してください。

専用の Linux テスト環境で `companion/worker` に移動し、以下を実行します。

```sh
npm ci
npm test
npm run test:persistence
npm run check:bundle
```

初回の `npm ci` は通常、依存パッケージをダウンロードします。導入後のローカルテストは Cloudflare に接続せずに実行できます。配備やクラウドでの確認には、権限のあるクラウドリソースが必要です。

実際の nftables は、使い捨て VM のプライベートネットワーク名前空間で検証します。`test/run_checks.sh` と `test/run_final.sh` には所定のテスト環境と作業ディレクトリが必要です。メンテナンスのテストは操作を記録し、システムを再起動しません。`kernel_lease_test.py` では 120 秒のカーネルリースが 125 秒後に消え、コールドスタートでも復元されないことを確認します。

## 配備

[Linux Agent](LINUX-AGENT-INSTALL.ja.md) は別途インストールして検証します。同じ VPS 上で専用 Tunnel の `cloudflared` を動かします。VPC Service は Agent のループバックリスナー（通常は HTTP `127.0.0.1:8788`）を指し、`VPS_API` をその Service ID に結び付けます。

- `DEVICE_ID` を Agent と一致させます。
- 機器から Worker にはランダムな `DEVICE_TOKEN`、Worker から Agent には別の `AGENT_SECRET` を使います。
- どちらの秘密情報も英数字、アンダースコア、ハイフンから成る 32～256 文字です。`REPLACE_` のプレースホルダーは拒否されます。
- `.dev.vars.example` に必要なキーがあります。実際の値は非公開の秘密情報ストアに保管し、`.dev.vars`、`.env`、秘密情報ファイルはコミットしないでください。
- `wrangler.jsonc` に Service ID を設定します。秘密情報を事前登録するか、テスト時は `npm run deploy -- --secrets-file /path/to/private-secrets.json` で渡します。JSON のキーは `DEVICE_TOKEN` と `AGENT_SECRET` です。設定例に実際のリソース ID はありません。

接続先は VPC Service のホストとポートで決まります。fetch URL で別の宛先を指定しても変わりません。Cloudflare 上で Service の設定とバインディングを照合してください。

## API とデータ

クライアントは `ProxyGuardPro/0.2.0` など、アプリケーション固有の User-Agent を送信します。Cloudflare の `1010` が返る場合は、クライアント識別情報とアカウントのセキュリティ設定を確認します。

すべての経路で HTTPS と機器用 Bearer トークンが必要です。クエリ文字列は受け付けません。

| 経路 | 動作 |
| --- | --- |
| `/v1/observe` | Cloudflare が観測した公開 IP を返します。Worker のサブリクエストや予約アドレスは拒否し、Agent のリースは更新しません。 |
| `/v1/sync` | 直前に観測した IP が必要です。別の HMAC-SHA256 秘密情報で JSON の生バイト列を署名し、新しいリクエスト ID を発行します。Agent が署名、時効、リプレイ、リビジョンを検査します。同じリビジョンで延長できるのは同じポリシーだけです。IPv4 と IPv6 は個別に 120～86400 秒更新します。同期を止めるとリースは満了します。 |
| `/v1/status` | ポリシー、リース、ヘルス、メンテナンスの確認に必要な項目を返します。`include_analysis=false` を指定し、管理アドレス、リスナー一覧、イベント、認証元の詳細、未知の拡張項目は除外します。リースは更新しません。 |
| `/v1/command` | `restart_xray` と `reboot_vps` のみ。固定の操作 ID、ポリシーのリビジョン、有効期間 1～60 秒を指定し、Agent 側でも個別に許可します。結果が不明なら同じ ID で照会・再試行します。拒否は固定コードで返し、上流応答はストリームで 32768 バイトに制限します。 |

Agent はファイアウォール適用後の単調時計による残りリースから `expires_at` を計算します。適用が遅くても表示上のリースは延びません。

## 動作確認

Worker、VPC Service、Tunnel、Agent、OpenWrt クライアントの連携をテスト済みです。配備後は自分のバインディング、認証情報、実際のクライアント要求を確認します。`companion/worker/` から Wrangler で配備する前に、Tunnel、VPC Service、バインディングを準備します。

Cloudflare の公式資料（英語）:

- <https://developers.cloudflare.com/workers-vpc/api/>
- <https://developers.cloudflare.com/workers-vpc/get-started/>
- <https://developers.cloudflare.com/workers/platform/deploy-buttons/>
- <https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/>

## バージョンと配備範囲

[Worker のツールプロジェクト](../companion/worker/package.json) の npm バージョンは `0.2.0` です。Pro のパッケージリビジョンとは独立しています。Node.js とツールの要件はマニフェストとロックファイルを参照します。VPS、Agent、Tunnel、VPC Service は別途準備します。

## 読み取り専用の出口候補

`POST /v1/egress-info` は機器用 Bearer トークンと空でない JSON `{ "device_id": "home" }` を使い、固定 `VPS_API` の HMAC 対応エンドポイントに転送します。返す根拠は `interface`、`panel`、`measured` に限ります。候補なし、期限切れ、複数候補には警告が付き、期待する出口は利用者が指定します。測定は初期状態で無効です。リース、制御ハートビート、確認待ちポリシーには影響しません。旧 Agent は 501 `egress_info_unsupported` を返します。プロトコル、固定測定先、連携方法は [Agent API](VPS-EGRESS-INFO.ja.md) を参照してください。

[Worker ディレクトリの案内](../companion/worker/README.ja.md)
