# インストールと利用

[English](USAGE.en.md) · [简体中文](USAGE.md) · [日本語](USAGE.ja.md) · [Русский](USAGE.ru.md) · [فارسی](USAGE.fa.md)

通常版 `0.3.0-21` と Pro `0.3.1-5` のインストール、設定、保守を説明します。[互換性](COMPATIBILITY.ja.md) と [テストマトリクス](TEST-MATRIX.ja.md) を確認してください。日常の設定は [ユーザーガイド](USER-GUIDE.ja.md) にあります。

## ダウンロードの照合

対象パッケージと `SHA256SUMS` を [同じ正式リリース（英語）](https://github.com/beezcheyenna/Proxy-Guard/releases/tag/v0.3.0-21-pro-0.3.1-5) から同じディレクトリに保存します。エディション、形式、バージョン、ファイル名を照合します。例は通常版 IPK です。通常版 APK なら `PG_PACKAGE=luci-app-proxy-guard-0.3.0-r21.apk` にします。

```sh
PG_PACKAGE=luci-app-proxy-guard_0.3.0-21_all.ipk
awk -v f="$PG_PACKAGE" '$2 == f { print; n++ } END { if (n != 1) exit 1 }' SHA256SUMS > SHA256SUMS.selected &&
sha256sum -c SHA256SUMS.selected
```

対象ファイルが `OK` となり、コマンドが成功したことを確認します。項目の欠落・重複、ファイルなし、不一致ならインストールを中止します。全ファイルを取得した場合は `sha256sum -c SHA256SUMS` を使えます。一部のみでは未取得分のエラーが出ます。

macOS は `shasum -a 256 <ファイル名>` を使い、64 桁すべてを照合します。SHA256 は一覧との一致を確認します。両方をプロジェクトの HTTPS リリースから取得します。配布者認証には別途検証できる署名などが必要です。

<a id="installation"></a>

## インストール、更新、削除

ファームウェアに合う形式を選びます。24 系の opkg は IPK、25.12 の apk は APK を使います。LuCI でアップロードするか、ルーターに置いて対応するコマンドを実行します。

**opkg / IPK**

```sh
opkg install /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-0.3.0-r21.apk
```

`--allow-untrusted` は照合済みローカル APK 用です。依存検査は行われます。`--no-network` には依存関係の導入が必要です。不足分は対応フィードから先に導入します。

Pro は互換通常版の拡張で、版番号は独立です。同じトランザクションで両方導入できます。

**opkg / IPK**

```sh
opkg install /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk /tmp/luci-app-proxy-guard-pro_0.3.1-5_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-0.3.0-r21.apk /tmp/luci-app-proxy-guard-pro-0.3.1-r5.apk
```

既存の通常版が最低バージョンと基本 API を満たせば Pro のみ更新できます。非互換は理由を表示して拒否されます。互換範囲では通常版の修正も独立して導入できます。[エディション比較](EDITION-MATRIX.ja.md) を参照してください。遠隔機能には [Linux Agent](LINUX-AGENT-INSTALL.ja.md) を別に配備し、直接 HTTPS または Cloudflare Worker/Tunnel/VPC を選びます。

Pro 0.3.1-2 以降は、無効時もインストールと起動で旧 UCI の `device_token` と `path_token` を root 専用の鍵ファイルへ移します。新しい秘密情報は LuCI で一時保存して適用します。以前に信頼できないアカウントが読めた場合は機器と配備先で更新してください。

通常版は `luci-base`、`lua`、`libuci-lua`、`luci-lib-jsonc`、`luci-lib-nixio`、`rpcd-mod-file`、`firewall4`、`curl`、`ca-bundle`、`ucode`、`ucode-mod-fs`、`ucode-mod-uci` に依存します。ファームウェアに合う依存関係を使い、オフライン導入前に準備します。独立 `flock` パッケージは不要です。依存検査は維持してください。

同じ版の再ビルドは通常導入で省略される場合があります。設定をバックアップし、配布元と SHA256 を照合します。2 行目はインストール済み Pro を置換する場合だけ実行します。APK は実ファイルを指定します。

**opkg / IPK**

```sh
opkg install --force-reinstall /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk
opkg install --force-reinstall /tmp/luci-app-proxy-guard-pro_0.3.1-5_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add --force-reinstall /tmp/luci-app-proxy-guard-0.3.0-r21.apk
apk --no-network --allow-untrusted add --force-reinstall /tmp/luci-app-proxy-guard-pro-0.3.1-r5.apk
```

`apk fix` の `unavailable, skipped` は置換されていないことを示します。更新前に試行を確認または取り消します。インストーラーは未確認の変更を戻して確認済み設定を保持します。上書き更新を行い、出力を保存し、操作は 1 セッションずつ実施します。

LuCI の **サービス → Proxy Guard** を開きます。フックがキャッシュ削除、rpcd 再読み込み、必要な再起動を行います。再ログイン後もメニューや RPC がない場合は出力を残し、依存関係とフックを調べます。既存の ACL を維持します。

新規は無効・監視のみです。更新は `/etc/config/proxy_guard`、スイッチ、独自の待ち時間を保持します。認識した旧 Google/Cloudflare プリセットに完全一致した場合のみ gstatic と Ubuntu、旧出口は ipify に移行します。実際のターゲットと `proxy_guard-opkg`・`.apk-new` の設定控えを確認します。

`/etc/config/proxy_guard` をバックアップします。Pro は `/etc/config/proxy_guard_access`、存在する `/etc/proxy-guard-access/device.key` と `/etc/proxy-guard-access/path.key` も保存します。UCI エクスポートに秘密鍵は含まれません。ルーターの控えは非公開にし、Agent 設定、証明書、Worker の秘密情報は別に保存します。

Pro の同期停止や拡張削除後もリモート規則は残ります。制御が使えるうちに削除準備、適用、確認を行い、VPS の規則を照合します。[リモートポリシー確認](GUIDED-SETUP.ja.md#remote-policy-confirmation) を参照してください。

パッケージ管理方式に応じて実行します。1 行目は Pro が入っている場合だけです。

**opkg / IPK**

```sh
opkg remove luci-app-proxy-guard-pro
opkg remove luci-app-proxy-guard
```

**apk / APK**

```sh
apk del luci-app-proxy-guard-pro
apk del luci-app-proxy-guard
```

削除フックは専用ルール、RPC、メニュー、起動リンクを削除します。変更済み設定はパッケージ管理方式によって残ります。削除は専用遮断を解除します。保守時は [明示的な無効化](RECOVERY.ja.md) を使ってください。

## 初回設定

[ウィザード](GUIDED-SETUP.ja.md) で実際の LAN レイヤー 3 入口を選び、[設定項目](USER-GUIDE.ja.md#guide-options) を確認します。IPv4 と IPv6 は端末 1 台から始めます。配布のアドレスは例です。`127.0.0.1` の実 SOCKS5、クライアント向けプロキシ入口と DNS の宛先ポートを照合します。検査用ポートと入口は別です。DNS の既定は `53` です。例外を必要な範囲に絞り、対象外にする IPv6 は明示します。**監視のみ**で適用し、実経路を確認してから遮断します。

## 保存・適用・状態

編集は下書き、**保存**はセッションへの一時保存、**保存して適用**は検証とコミットです。自己診断成功から **30 秒以内**に確認します。リセットは保存済み、または一時保存済みのフォームに戻します。ログ消去は本プラグインのイベントと検査履歴のみです。状態は約 1 秒、ログは約 5 秒ごとで、RPC が遅いと表示も遅れます。古い状態や権限変更後はルールを確認し、必要なら再ログインします。[状態と診断](USER-GUIDE.ja.md#guide-troubleshooting) を参照してください。

## 遮断と復旧

### 通常検査

HTTPS はローカル SOCKS 経由です。出口 IPv4 と SOCKS5 UDP は任意です。既定のターゲットは `https://www.gstatic.com/generate_204|204` と `https://connectivity-check.ubuntu.com/|204` です。通常の既定は HTTPS 1 件以上と有効な出口・UDP 検査すべての成功、失敗 3 回・復旧 2 回です。各回の終了後に 10 秒待ちます。固定の起動猶予は起動後 150 秒までで、保護モードはその間遮断します。起動時保護ではサービス待ちに切り替わります。

出口照合では主 URL がタイムアウトしたときのみ同じ SOCKS で予備 HTTPS を 1 回使います。次の回は主 URL からです。空欄なら ipify は `https://4.ident.me/`、他のドメインは予備なしです。不一致や検証失敗は設定した障害判定に従います。

### クライアントのサービス監視

約 1 秒ごとにプロセスとリスナーの識別を調べます。既定では必要な TCP、UDP、DNS のどれかが停止・再起動すると保護します。全対象の失敗を条件にもできます。対象は実際のクライアント構成に従います。

遮断待ちの既定は 15 秒で、ローカルサービスだけを監視します。経過後、必要なサービスが準備できたら新規検査を行い、成功後に通信を許可します。既定 60 秒の強化監視では正常な通信を許可し、各回終了から約 1 秒後に次を開始します。復旧と強化監視は全 HTTPS と有効な出口・UDP の成功が必要です。再障害は通常の回数判定を待たず再遮断します。待ちと強化監視は個別に無効化でき、各 1～3600 秒に設定できます。復旧検査は残ります。

### 実行ログ

サービス監視の下でログ監視を別に有効にし、1～10 秒間隔を選びます。[実行ログの互換性](LOG_COMPATIBILITY.ja.md) に記載の再起動、ルール削除、停止、起動失敗、完了を認識します。初回ログ障害では、今回の新しい完了、サービス復帰、新規検査で強化監視へ直接移れます。強化監視中の再障害は設定した待ちを行います。欠けたログ、古い・未来の時刻、無関係な取り消しで待ちを解除しません。待ちは単調時計、ログはルーターのローカル時刻を使います。

### 起動時と定時保護

起動時保護には全体スイッチ、保護モード、サービス監視、起動時設定が必要です。有効な構成では機器名の初期ルールを設置し、検証後に置き換えます。必要な TCP、UDP、DNS がそろってから遮断待ちと復旧を行います。実経路で確認してください。

毎日または曜日を選び、異なる開始・終了と固定 UTC オフセットを指定します。日をまたぐ場合は開始日の予定です。外部を遮断し、例外を維持します。終了時にサービス監視が有効で他の障害や待ちがなければ、新規の厳密な検査後に追加の 15 秒なしで強化監視に移れます。サービス監視なしでは通常の連続復旧判定を使います。

## 更新・再起動後の確認

1. バージョン、SHA256、依存、フックを確認し、再ログインしてページと状態・ログを開きます。
2. 実際のスイッチ、モード、入口、範囲、例外、予定を保存設定と照合します。
3. 端末 1 台で遮断、復旧、LAN、DNS、管理、別ゲートウェイ、新規と既存の通信を確認します。
4. RAM ログを保存し、独立した管理経路を確保します。起動時保護は **Proxy Guard のルーター**を再起動して対象端末で確認します。
5. Pro では制御、更新された家庭許可、選択ポート、Agent を確認します。ファームウェア、コア、構成を変更したときも関連項目を再確認します。

## ログと診断

最新 200 件のイベントと 100 件の検査詳細を表示します。ファイルは RAM でサイズに従ってローテーションし、`logger` はシステムログにも記録します。error の保護イベントは障害への正しい応答の場合があります。復旧、ルールエラー、現在の状態を確認します。[状態](USER-GUIDE.ja.md#guide-troubleshooting)、[プライバシー](PRIVACY.ja.md)、[復旧](RECOVERY.ja.md) を参照してください。

ルーターでの読み取り専用確認:

```sh
if command -v opkg >/dev/null 2>&1; then
    opkg status luci-app-proxy-guard
else
    apk info -a luci-app-proxy-guard
fi
/usr/libexec/proxy-guard status
/usr/libexec/proxy-guard logs
```

## 任意の UDP 経路検査

到達可能な IPv4 UDP DNS、ポート、問い合わせ名、タイムアウトを設定します。`luci-lib-nixio` がロックと UDP を提供します。未対応なら有効化を拒否します。SOCKS5 UDP ASSOCIATE、ループバック中継、ランダムな DNS トランザクション ID を使い、応答元、ID、質問、コードを検査します。クライアントの対応が必要です。LAN 宛ては LAN の経路だけを検証します。

UDP 失敗は通常の失敗回数に入り、強化監視では 1 回で遮断します。遮断待ち中は送信しません。HTTPS と有効な出口照合は別に使います。

## プロセス復旧と使用量

ハートビート、最短再試行間隔、回数と集計窓を設定できます。自動復旧が無効でも procd は終了プロセスを起動します。明示的な init stop は自動で有効化されず、遮断が残ります。[明示的な無効化](RECOVERY.ja.md) を使います。

5 秒ごとに全オンライン論理 CPU の総容量を 100% として表示します。20 個中 1 個を使い切ると 5% です。カウンター、CPU 数、プロセスが変わると再サンプルします。監視 3 プロセスと子を集計し、LuCI/rpcd、カーネル、他のプロキシは含みません。集計停止とハートビートは独立です。システム設定によってログが保存・転送されます。

## Pro の VPS アクセス管理

[構成と動作](PRO-COMPANION.ja.md)、[Agent](LINUX-AGENT-INSTALL.ja.md)、[リモート確認](GUIDED-SETUP.ja.md#remote-policy-confirmation) を参照してください。

- ローカルサービスポートを明示的に選びます。独立した未選択パネル、API、購読はシステムに従い、共用 IP・プロトコル・ポートは URL や SNI で分離できません。SSH は個別です。
- 規則は既定を継承するか、`standard`、`whitelist`、`observe` を選びます。TCP/UDP、範囲、家庭・固定・混合送信元、接続レート、バースト、同時接続、フォールバックしきい値、超過時間、クールダウン、観察窓を個別に設定します。同一プロトコルの有効規則は重ねません。標準は正常な既存接続を維持し、許可取り消しは既存着信にも影響します。
- SSH は制御と SOCKS 経由の独立 HTTPS 経路を確認し、有効な管理セッションを確保します。新規の公開救済は `0` で家庭許可復帰まで、または `30`～`3600` 秒です。既存の明示値、SSH 認証、システム規則は維持します。[接続設定](LINUX-AGENT-INSTALL.ja.md#control-and-path) を参照します。
- メンテナンスには Agent の `maintenance.enabled` と LuCI の対応許可が必要です。`adapter=systemd` は指定ユニット、`adapter=3x-ui` は `xui_usr1_confirmed` を検証します。`service` は監視名に合わせます。キューはハートビートと独立です。
- 厳密なフォールバック帯域制限は非公開の通常 JSONL `reality.telemetry_file` を使います。ハートビートは `{"kind":"heartbeat","time":...}`、新鮮な接続は Unix 秒 `time`、`kind`（`authenticated` または `fallback`）、`source_ip`、`source_port`、`port`、`protocol` を持ちます。フォールバックは増加する `bytes_in` と `bytes_out` も必要です。選択ポートを照合し、方向、送信元、ポート別に制限します。信頼する非 root 所有者は `reality.log_uid` に指定し、グループと他ユーザーの書き込みは許可しません。

## 原文設定と実際のポリシー

各 UCI エディターは専用ファイル、現在セッションの一時保存、既定テンプレート、下書きの取得を扱います。構文と有効化条件は別に検証します。保存は下書きで、適用時にローカル確認またはリモート機能・確認が必要です。他画面が変更したら再読込します。不明項目は警告して保持します。旧 `default_deny` と `auto_discover` は全体遮断に使いません。

`__KEEP_SAVED_SECRET__` は保存済みの値を保持し、秘密鍵を出力しません。変更は新しい値を入力します。再送防止の `revision` はバックエンドが増加させます。再インストールではペアリングとリビジョンを保持します。テンプレートは下書きだけを変更します。

`source_mode=all` は選択モード下で全送信元を許可し、標準制限と家庭・固定の自動例外なしを意味します。許可リストとは併用しません。旧 `source_mode=any` は無保護の動作を維持します。実動作は確認済みリモート状態を確認します。LuCI が使えない場合は [復旧](RECOVERY.ja.md) を参照してください。
