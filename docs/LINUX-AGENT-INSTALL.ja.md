# Linux VPS Agent の導入（Pro）

[English](LINUX-AGENT-INSTALL.en.md) · [简体中文](LINUX-AGENT-INSTALL.md) · [日本語](LINUX-AGENT-INSTALL.ja.md) · [Русский](LINUX-AGENT-INSTALL.ru.md) · [فارسی](LINUX-AGENT-INSTALL.fa.md)

Pro のリモート機能には OpenWrt 上の通常版と Pro、Linux VPS 上の Agent が必要です。直接 HTTPS または Cloudflare Worker と Tunnel/VPC を選べます。ルーターには IPK/APK、VPS には Python インストーラーを使います。Python 3.10 以降、nftables、対応カーネル機能、systemd または OpenRC が必要です。[互換性](COMPATIBILITY.ja.md) と [テストマトリクス](TEST-MATRIX.ja.md) を参照してください。

## 1. 依存関係の導入

ディストリビューションに対応するコマンドを選びます。

**Ubuntu / Debian**

```sh
sudo apt update
sudo apt install -y python3 nftables iproute2 ca-certificates
```

**Rocky Linux**

```sh
sudo dnf install -y python3 nftables iproute ca-certificates
```

**Alpine Linux（root）**

```sh
apk add python3 nftables iproute2 coreutils ca-certificates
```

サービスが使うインタープリターを確認します。

```sh
/usr/bin/python3 --version
```

`/usr/bin/python3` は 3.10 以降が必要です。別パスや仮想環境の Python はサービスには使われません。インストーラーは設定と nftables の動的セット・接続数制限などを確認します。稼働カーネルと一致するモジュールを使います。Agent は専用ポリシーサービスを導入します。

## 2. ソースの展開と設定

`proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz` を VPS に転送し、アーカイブのあるディレクトリで実行します。

```sh
tar -xzf proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz
cd Proxy-Guard/companion/vps
cp agent.example.json agent.json
chmod 600 agent.json
python3 - <<'PY'
from pathlib import Path
import json
import secrets

path = Path('agent.json')
config = json.loads(path.read_text())
config['agent_secret'] = secrets.token_urlsafe(32)
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o600)
PY
```

| 設定 | 内容 |
| --- | --- |
| `device_id` | `home` などの機器 ID。ルーターと使用する Worker で一致させます。 |
| `agent_secret` | 独立したランダムな秘密情報。Worker の `AGENT_SECRET` と一致させ、ルーターには渡しません。 |
| `services` | 実際のプロキシのプロセス名と TCP/UDP リスナー。 |
| `managed_units` | 起動依存の `name.service`。OpenRC では `.service` を除いた名前に対応。SSH は対象外。 |
| `egress.panel_config_path` | 任意の信頼できるローカル Xray JSON。外部測定は既定で無効。 |
| SSH、経路ハートビート、メンテナンス | 個別に設定して有効化。 |

Agent は既存のプロキシを監視・管理します。3x-ui 管理の Xray は、実プロセス名と対応バージョンの USR1 の動作を確認し、適切なアダプターを選びます。

## 3. 制御経路の選択

### Cloudflare Worker と Tunnel/VPC

通常は `bind=127.0.0.1`、`port=8788`、`public_control=false` とし、同じ VPS の `cloudflared` がループバック API に接続します。[Worker の手順](CLOUDFLARE-WORKER.ja.md) に従って Tunnel、VPC Service、`VPS_API` を設定します。`DEVICE_ID` は全体で一致させ、機器と Worker 間は `DEVICE_TOKEN`、Worker と Agent 間は別の `AGENT_SECRET` を使います。ルーターの VPS アクセス設定で Cloudflare を選び、Worker HTTPS ベース URL、機器 ID、機器用トークンを入力します。

### 直接 HTTPS

`public_control=true`、リスナー、有効な `tls_cert` と `tls_key`、別の `direct_token` を設定します。ルーター側は直接 HTTPS を選び、Agent HTTPS ベース URL、機器 ID、`direct_token` を入力します。秘密情報は英数字・下線・ハイフン 32～256 文字です。例の値は置き換えます。

**どちらの制御もプロキシを経由しないことを確認します。** 独立した経路ハートビートはローカル SOCKS を経由させます。

<a id="control-and-path"></a>

### URL、秘密情報、独立したプロキシ経路

| 用途 | ルーター | サーバー |
| --- | --- | --- |
| Cloudflare 制御 | Worker HTTPS ベース URL、機器 ID とトークン | `DEVICE_ID`、`DEVICE_TOKEN`。`AGENT_SECRET` は Agent の `agent_secret` と対応。 |
| 直接 HTTPS 制御 | Agent HTTPS ベース URL、機器 ID とトークン | `device_id`、`direct_token`、公開リスナー、TLS。 |
| 経路ハートビート | 経路監視を有効にし、Agent HTTPS ベース URL と専用トークン | `path_token`。SOCKS 経由で `/v1/direct/path-heartbeat`。 |

ベース URL には `/v1/...` を付けません。用途ごとに秘密情報を分け、SSH 管理前に両経路の認証を確認します。

- 直接制御は家庭側の実公開送信元 IP を必要とし、転送ヘッダーから復元しません。実 IP が見える入口を使います。同じ HTTPS ベース URL でも、経路ハートビートは SOCKS と専用トークンを使います。
- Cloudflare のループバック HTTP API はローカル Tunnel 用です。プロキシから到達できる別の HTTPS 経路入口が必要です。TLS リバースプロキシを使う場合は `/v1/direct/path-heartbeat` のみ転送し、Bearer ヘッダーを維持します。直接制御には実送信元が必要です。
- Agent 自体を公開 HTTPS にする場合はフラグ、直接トークン、証明書を設定し、Tunnel/VPC のプロトコルとポートも合わせます。証明書の発行、更新、リバースプロキシは別に管理します。

制御とハートビートの入口を認証リースの更新前にも到達できるようにします。直接経路と SOCKS 経路をそれぞれ検証してください。

## 4. インストールと確認

`companion/vps` で実行します。

**Ubuntu / Debian / Rocky Linux**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
sudo python3 agent.py --config "$PWD/agent.json" --check-kernel
sudo sh ./install.sh --install "$PWD/agent.json"

sudo systemctl status proxy-guard-access-policy proxy-guard-access --no-pager
sudo journalctl -u proxy-guard-access -n 50 --no-pager
```

**Alpine Linux（root）**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
python3 agent.py --config "$PWD/agent.json" --check-kernel
sh ./install.sh --install "$PWD/agent.json"

rc-service proxy-guard-access-policy status
rc-service proxy-guard-access status
```

プログラムは `/opt/proxy-guard-access`、稼働設定は `/etc/proxy-guard-access/agent.json` です。インストーラーがポリシーと Agent のサービスを起動し、既存設定を保持します。変更は稼働設定に行い、再検証します。LuCI で保存して適用し、同期、リース、サービスを確認して管理ポートを選びます。

## 5. SSH 救済とパネルポート

SSH 管理は既定で無効です。管理セッションを確保して両経路を確認した後、認証済みハートビートが両方とも連続で途絶えると救済が始まります。既定の待ちは **60 秒**です。

新しい設定の既定は公開救済です。期間 `0` は家庭側の認証復旧まで、`30`～`3600` 秒なら期限付きです。管理送信元への限定も選べます。既存の明示値（`600` を含む）は保持します。公開期間が増え、期限後に家庭 IP が変わって管理元がなければ新しい SSH ログインができない場合があります。システムファイアウォール、SSH 認証、事業者規則は引き続き適用されます。

未選択の別 3x-ui パネル、API、購読ポートはシステムのルールに従います。選択済みまたは IP・プロトコル・ポート共用の入口にはポートルールが適用されます。先にリスナーを確認します。

## 6. ポートモードと原文設定

ルールごとに既定、許可リスト、標準制限、観察を選び、送信元・しきい値・期間を設定できます。適用前にリモート機能を確認します。新機能には Agent、Cloudflare 使用時は Worker の更新も必要な場合があります。2 つのルーターエディターはローカル保護と VPS アクセスの UCI 用です。Agent のリスナー、TLS、メンテナンスは Agent 設定で管理します。クラウド構成は [Worker の手順](CLOUDFLARE-WORKER.ja.md) を参照してください。

## 7. 更新とバックアップ

SSH またはコンソールを確保し、稼働設定、TLS 鍵と証明書、対応ソース、設定した永続状態と操作記録を非公開で保存します。各インスタンスの状態とリビジョンを保持します。

新しい `companion/vps` から実行します。systemd は 1 行目、Alpine は root で 2 行目を選びます。

```sh
# Ubuntu / Debian / Rocky Linux
sudo sh ./install.sh --install /etc/proxy-guard-access/agent.json

sh ./install.sh --install /etc/proxy-guard-access/agent.json
```

インストーラーは稼働設定とカーネルを確認し、プログラムとサービスを更新して Agent を再起動します。サービス、認証、リビジョン、機能、選択ポートを照合します。ダウングレード前に設定と状態の互換性を確認します。

## 8. エンドツーエンドの確認

- ポリシーと Agent のサービス、実プロキシ、TCP/UDP リスナー、実際のプロキシ要求を確認します。
- TLS、機器 ID、個別の秘密情報、直通制御、必要なら VPC の固定バインディングと Tunnel を確認します。新しい家庭 IP は観測・同期し、LuCI でリースを確認します。
- まず 1 ルールを試行・確認し、許可・制限された送信元、未選択ポート、パネル・購読、SSH、Docker の経路を個別に検証します。
- 経路ハートビート、救済、メンテナンスを個別に確認します。制御・プロキシの途絶、確認期限切れ、再起動の復旧と実ルールを照合します。

| 症状 | 確認点 |
| --- | --- |
| インストール前検査失敗 | Python、稼働 init、nftables の式とモジュール。 |
| HTTPS・認証失敗 | 証明書と有効期限、時計、リスナー、機器 ID、トークン。TLS 検証は維持。 |
| Worker は応答するが Agent に届かない | Tunnel、固定接続先、バインディング ID、Agent のループバック。 |
| 制御は正常だが経路が失敗 | 独立 HTTPS 入口、経路トークン、SOCKS、実出口。 |
| パネル・購読も制限 | 選択ポート、または共用 IP・プロトコル・ポート。 |
| 救済中も SSH 不可 | SSH サービスと認証、システムファイアウォール、事業者のセキュリティグループ。 |
| 設定変更後も状態が不変 | 稼働設定、再検証と再起動、試行中・結果不明の状態。 |

[Pro の構成と障害時の動作](PRO-COMPANION.ja.md) と [復旧](RECOVERY.ja.md) を参照してください。

## 9. 削除

保存した対応版の `companion/vps` で、systemd は 1 行目、Alpine は root で 2 行目を実行します。

```sh
sudo sh ./uninstall.sh --remove

sh ./uninstall.sh --remove
```

専用サービスとルールを削除し、設定、秘密情報、プログラムは保持します。[復旧](RECOVERY.ja.md) の確認手順を参照してください。

[VPS Agent ディレクトリの案内](../companion/vps/README.ja.md)
