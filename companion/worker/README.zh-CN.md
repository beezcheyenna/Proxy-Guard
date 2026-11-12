# Proxy Guard Cloudflare Worker

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

可选的 Pro 控制中继，通过配置好的 Tunnel/VPC Service 连接 OpenWrt 和 VPS Agent，用于认证、策略和状态。代理数据和独立 SOCKS 心跳走各自的路径。

- [部署与绑定](../../docs/CLOUDFLARE-WORKER.md)
- [架构与故障行为](../../docs/PRO-COMPANION.md)
- [协议与升级兼容](../../docs/EDITION-MATRIX.md)
- [安装 VPS Agent](../../docs/LINUX-AGENT-INSTALL.md)

npm 项目版本是 0.2.0，Agent 控制协议是 v3。使用同一发行源码，核对绑定、分离的凭据和实际响应。云端与本地测试应分别验证。直接 HTTPS 不需要 Worker。

[参与贡献](../../docs/CONTRIBUTING.zh-CN.md) · [安全政策](../../docs/SECURITY.md) · [第三方声明](THIRD_PARTY_NOTICES.zh-CN.md)
