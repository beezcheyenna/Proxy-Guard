# 復旧

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

## 復旧状態の確認

状態欄には現在の遮断状況と最後に完了した検査結果が表示されます。ルールの確認が必要な場合は「設定と動作環境を確認」を実行します。「現在のプロキシをテスト」で SOCKS 経路を調べられます。

プロキシに接続できない場合は、クライアントのローカル SOCKS の待受を確認します。ファイアウォールの再読み込みやプロキシの再起動後は、設定した復旧確認を待ちます。Proxy Guard のサービスが停止してもルールが遮断を続けることがあります。遮断を解除するには下記の手順で保護を明示的に無効にします。

復旧を試す前にコンソールか別の管理経路を確保します。設定変更で接続できなくなったら確認時間の終了を待ちます。確認前に時間切れまたは再起動が起きると、前の設定に戻ります。

ルーターのコンソールを使える場合は以下のコマンドで保護を明示的に停止できます。状態がオフになったことを確認してから、保護対象の端末で通信を確認します。

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery &&
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart &&
ubus call proxy_guard status
```

保護の対象は実際にルーターを経由する通信です。範囲を広げる前に一台で入口、IPv4 と IPv6、DNS、管理経路を確認します。同一サブネットでは戻りの通信がルーターを迂回する場合があります。

[インストールと使用](USAGE.ja.md)
