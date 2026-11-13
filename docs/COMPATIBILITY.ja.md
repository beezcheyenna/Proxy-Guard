# 互換性と制限

[English](COMPATIBILITY.en.md) · [简体中文](COMPATIBILITY.md) · [日本語](COMPATIBILITY.ja.md) · [Русский](COMPATIBILITY.ru.md) · [فارسی](COMPATIBILITY.fa.md)

LuCI、firewall4、nftables が必要です。OpenWrt 24 は IPK、25.12 は APK を使います。iStoreOS と ImmortalWrt は各ファームウェアのパッケージ管理とカーネル依存関係に合わせてください。

保護の対象は実際にルーターを経由する通信です。範囲を広げる前に一台で入口、IPv4 と IPv6、DNS、管理経路を確認します。同一サブネットでは戻りの通信がルーターを迂回する場合があります。

既定の公式 HTTPS はローカル SOCKS 経由で固定アドレスへ接続します。外部 HTTPS には独立した間隔としきい値があります。出口 IPv4 の照合は初期状態では無効で、有効にすると既定で公式応答のアドレスを使います。外部 IP サービスは主アドレスがタイムアウトした場合だけ予備を試します。

クライアントが対応する転送モードを使い、対象端末の IPv4 と IPv6 の経路を確認してください。本バージョンで検証した環境と項目は[テストマトリクス](TEST-MATRIX.ja.md)に掲載しています。

| プロキシクライアント | 転送モード | 確認事項 |
| --- | --- | --- |
| PassWall | TCP REDIRECT + UDP TPROXY、または TCP/UDP TPROXY | IPv6 をプロキシ経由にする場合はクライアントで IPv6 TPROXY を有効にします。ルーティングされる IPv6 は別に確認します。 |
| PassWall2 | TCP/UDP TPROXY | 有効なローカル SOCKS の待受を確認します。他の転送モードは使用環境で検証してください。 |
| OpenClash | REDIRECT + TPROXY、または TUN | SOCKS 認証を維持します。IPv6 の UDP をプロキシ経由にする場合はクライアント側で有効にします。 |
| Nikki | REDIRECT + TPROXY、または TUN | 設定した SOCKS 認証を維持し、選択したモードで IPv4 と IPv6 を確認します。 |
| HomeProxy | REDIRECT + TPROXY、または system TUN | インストール済みの sing-box とファームウェアで IPv6 UDP を確認します。 |

検出に成功しても、転送はプロキシコアの動作に左右されます。NaiveProxy は UDP を中継しません。IPv4 専用の待受だけでは IPv6 のプロキシ経由を確認できません。Xray の SOCKS5 UDP を調べる際は、保護を無効にした対照環境でコアと転送モードも確認します。

IPv6 の UDP をプロキシ経由にする場合は、その UDP 経路を実際の通信で確認してください。TCP や SOCKS の接続結果は、それぞれの経路についての結果です。

LuCI のプラグインは英語、簡体字中国語、日本語、ロシア語、ペルシア語に対応します。テーマや他のアプリにはそれぞれの翻訳が使われます。[ログの互換性](LOG_COMPATIBILITY.ja.md)

## 保護モードの前提条件

UCI でソフトウェア・ハードウェアオフロードが有効、nft flowtable が残存、`bridge-nf-call-iptables` または `bridge-nf-call-ip6tables` でスイッチングのみの通信が IP ファイアウォールに流入、または入口・カーネル・ブリッジ・ルールを検証できない場合は確認を止めます。設定は機器側で確認してください。

ベンダー独自の高速化やスイッチチップのバイパスは実機で確認します。NAT なしの検証では戻りも同じルーターを通りました。同一サブネットのゲートウェイには行きの通信しか届かない場合があります。スイッチ経由で別ゲートウェイを使う端末は影響を受けないことを確認してください。サブネット間 LAN、VPN、コンテナー、複数ブリッジ、IPv6 既定経路も実構成で確認します。
