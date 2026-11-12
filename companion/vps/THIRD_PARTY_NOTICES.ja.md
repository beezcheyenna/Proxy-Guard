# VPS Agent の第三者通知

[English](THIRD_PARTY_NOTICES.en.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

Copyright (c) 2026 Proxy Guard contributors.

独自ソースは同梱の [MIT](LICENSE) に従います。Agent は Python 標準ライブラリーと外部 Linux ツールを使います。Python、nftables/Linux Netfilter、iproute2、systemd/OpenRC は別に導入し、各通知を保持します。第三者 pip パッケージやインタープリターは含まれません。

任意の管理対象 Xray、sing-box、Mihomo、3x-ui は別プロジェクトで個別に導入します。cloudflared は別の Apache-2.0 プログラムです。<https://github.com/cloudflare/cloudflared/blob/master/LICENSE>

インタープリター、トンネル、コア、パネル、システムイメージ、依存関係を配布する場合は各通知と必要な対応ソース・ビルド素材を保持してください。OpenWrt 側は [全体の通知](../../docs/THIRD_PARTY_NOTICES.ja.md)、Agent の同梱文書は [範囲](LICENSING.ja.md) を参照してください。
