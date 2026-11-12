# 障害時の復旧

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

通常版 `0.3.0-21` と Pro `0.3.1-5` が対象です。ルーターの保護と VPS のリモートポリシーは個別に操作します。

ルーターの無効化と確認のタイムアウトは隔離 OpenWrt 24.10.8 VM、VPS の削除は隔離 Ubuntu・Alpine VM と従来の 4 ディストリビューションのライフサイクル試験で確認しました。機器固有の復旧モードやファイルシステム破損には対応する手順を使います。[テストマトリクス](TEST-MATRIX.ja.md) を参照してください。

## 1. 管理経路を確保する

- SSH セッション、シリアル、VM コンソール、VPS 事業者のコンソールを確保します。ネットワーク管理がすべて失われた場合は独立したコンソールとファームウェア固有の復旧手順を使います。
- 保護を無効化すると対象端末が直接通信できる場合があります。必要なら先に端末の外部接続を切ります。
- システムのルール、ロックファイル、確認待ち状態を保持します。全ルールの消去やトランザクションの手動削除は管理・復旧に影響します。

## 2. LuCI が使えず、ルーターの SSH またはコンソールが使える場合

root で読み取り専用の確認を行います。

```sh
/usr/libexec/proxy-guard status
ubus list proxy_guard
nft list tables
logread -e proxy-guard
```

ubus オブジェクトの欠落、画面エラー、プロキシ停止は別々に調べます。エラーを保存し、既存 ACL は維持します。`/etc/init.d/proxy-guard stop` の後も nftables の遮断が残る場合があります。ログは再起動前に非公開で保存し、公開報告前に機密情報を除去します。RAM のログは通常、再起動で失われます。

### 通常版の保護を明示的に無効化

UCI が解析可能で、独立した管理経路を確保し、端末が直接通信できる可能性を受け入れた場合に実施します。まずバックアップします。

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery
```

バックアップを確認後に実行します。

```sh
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart
```

無効化を確認済み設定として登録し、保留中の有効化に優先してからサービスを再起動します。監視側が古い試行設定を再適用するのを防ぎます。UCI の編集や停止中のサービスの reload だけではトランザクションが完了しません。

続けて確認します。

```sh
uci -q get proxy_guard.main.enabled
/usr/libexec/proxy-guard status
nft list tables
```

`0`、`disabled`、実行状態 `off` を確認します。通常版の `inet proxy_guard` が消え、`fw4` と他のルールが残るのが期待結果です。実際の接続は既存のルーティング、ファイアウォール、プロキシ設定に従います。

設定が解析できない場合は、対応版の信頼できる自分のバックアップから `/etc/config/proxy_guard` を復元し、明示的に無効化します。プログラムや依存関係が壊れている場合はコンソールを確保して該当パッケージを修復します。

## 3. 確認期限切れ

自己診断成功後、ルーターが **30 秒の確認タイマー**を開始します。画面を閉じたり接続が切れたりしても独立した監視がロールバックします。再接続後に状態と以前の設定を照合し、実際のルールを確認してから下書きを直します。`pending.json` を保持します。監視、保存領域、実行状態に異常がある場合はコンソールで明示的に無効化し、ルールを確認します。

## 4. プロセス停止後も遮断が続く

プロセスが終了しても既存のルールをカーネルが実行し、許可は満了します。保護を維持しながらログ、保存領域、依存関係、UCI、インターフェースを確認し、修復後に再起動します。一時解除には第 2 節の手順を使います。複数の検査プロセスを手動で起動せず、ロックは保持します。再有効化・確認の前に端末 1 台で試します。

## 5. Pro の制御が失われ、VPS のルールが残る

同期を止めると更新が止まります。家庭 IP の動的リースは満了し、固定許可リストと選択したポートルールは残る場合があります。SSH 救済には事前の有効化と確認、および認証済み 2 経路の途絶条件が必要です。システムのファイアウォール、SSH 認証、事業者のセキュリティグループは有効です。試行結果が不明ならリモート状態を読み、リビジョンと操作 ID を維持します。プロキシとポートを共有する管理入口も影響を受けるため、別コンソールを確保します。

制御可能なら、同期停止前に Pro の削除・確認手順を使い、VPS の状態を検証します。

### VPS のコンソールから専用ルールを削除

ルーター側の自動同期を無効にして維持します。VPS のコンソールと元のファイアウォールを確保します。実際の `/etc/proxy-guard-access/agent.json`、鍵、証明書、永続状態を非公開でバックアップします。インストール済みの版に合う信頼できるソースの `companion/vps` で、OS に応じて実行します。

Ubuntu・Debian・Rocky Linux:

```sh
sudo sh ./uninstall.sh --remove
sudo systemctl status proxy-guard-access proxy-guard-access-policy --no-pager
sudo nft list tables
```

Alpine Linux は root で実行します。

```sh
sh ./uninstall.sh --remove
rc-service proxy-guard-access status
rc-service proxy-guard-access-policy status
nft list tables
```

削除後の状態照会はサービスなしや非ゼロ終了を返す場合があります。削除自体が失敗したらエラーを保存して止めます。削除対象は専用サービス、起動依存関係、専用ルールです。設定、鍵、プログラムを残し、NAT・FORWARD・他のルールを維持します。管理とサービスのポートを確認します。`pg_vps_access` は既定名です。実際の設定でテーブル名を確認し、破損で所有を特定できなければ設定を復旧します。

再インストールで保存済みポリシーが復元される場合があります。先に設定と状態を見直し、制御、動的許可、ポートモード、SSH を確認します。別インスタンスの状態をコピーせず、リビジョンの増加を維持します。

## 6. 復旧の確認

端末 1 台で LAN、DNS、管理、IPv4/IPv6、新規・既存接続、障害、復旧を確認します。起動時保護の検証では独立した管理経路を確保し、**Proxy Guard が動作するルーター**を再起動します。

[インストールと利用](USAGE.ja.md) · [Linux Agent](LINUX-AGENT-INSTALL.ja.md) · [制御経路と障害時の動作](PRO-COMPANION.ja.md) · [セキュリティ報告](SECURITY.ja.md)
