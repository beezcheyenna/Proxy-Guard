# Proxy Guard VPS Agent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

Pro の VPS 用コンポーネントです。選択したローカルサービスポートに認証済み家庭 IP リース、ポートごとの規則、任意の SSH 救済、許可された保守を提供します。通常版には不要です。

- [導入・更新・削除](../../docs/LINUX-AGENT-INSTALL.ja.md)
- [構成と障害時の動作](../../docs/PRO-COMPANION.ja.md)
- [コンポーネントの互換性](../../docs/EDITION-MATRIX.ja.md)
- [検証したシステムと制限](../../docs/TEST-MATRIX.ja.md)
- [LuCI なしでの復旧](../../docs/RECOVERY.ja.md)

Python 3.10 以降、nftables、systemd または OpenRC が必要です。制御は直接 HTTPS または Cloudflare を選びます。コアと 3x-ui は別に導入します。有効化前に管理経路を確保します。未選択ポートは元のファイアウォールに従います。

[貢献方法](../../docs/CONTRIBUTING.ja.md) · [セキュリティ方針](../../docs/SECURITY.ja.md) · [第三者通知](THIRD_PARTY_NOTICES.ja.md) · [ライセンスの範囲](LICENSING.ja.md)
