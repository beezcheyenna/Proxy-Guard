# Proxy Guard VPS Agent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

Pro 的 VPS 配套。对选定的本机服务端口提供认证家庭 IP 授权、按端口策略、可选 SSH 应急与明确授权的维护。普通版不需要安装。

- [安装、升级与卸载](../../docs/LINUX-AGENT-INSTALL.md)
- [架构与故障行为](../../docs/PRO-COMPANION.md)
- [版本兼容](../../docs/EDITION-MATRIX.md)
- [测试发行版与限制](../../docs/TEST-MATRIX.md)
- [不经 LuCI 的救援](../../docs/RECOVERY.md)

需要 Python 3.10+、nftables、systemd 或 OpenRC。控制选直连 HTTPS 或 Cloudflare。代理内核和 3x-ui 另行部署。启用策略前保留管理通路，未选端口沿用原防火墙。

[参与贡献](../../docs/CONTRIBUTING.zh-CN.md) · [安全政策](../../docs/SECURITY.md) · [第三方声明](THIRD_PARTY_NOTICES.zh-CN.md) · [许可范围](LICENSING.zh-CN.md)
