# Proxy Guard Cloudflare Worker

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

Pro の任意の制御中継です。設定済み Tunnel/VPC Service で OpenWrt と VPS Agent を接続し、認証・ポリシー・状態を中継します。プロキシデータと独立 SOCKS ハートビートは個別の経路です。

- [配備とバインディング](../../docs/CLOUDFLARE-WORKER.ja.md)
- [構成と障害時の動作](../../docs/PRO-COMPANION.ja.md)
- [プロトコルと更新](../../docs/EDITION-MATRIX.ja.md)
- [VPS Agent の導入](../../docs/LINUX-AGENT-INSTALL.ja.md)

npm 版は 0.2.0、Agent 制御プロトコルは v3 です。同一リリースのソースを使い、バインディング、個別の秘密情報、実応答を確認します。クラウドとローカルは別に検証します。直接 HTTPS では Worker は不要です。

[貢献方法](../../docs/CONTRIBUTING.ja.md) · [セキュリティ方針](../../docs/SECURITY.ja.md) · [第三者通知](THIRD_PARTY_NOTICES.ja.md)
