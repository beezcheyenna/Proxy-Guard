# Proxy Guard

[English](../README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Русский](README.ru.md) · [فارسی](README.fa.md)

**代理故障时，阻止受保护设备意外直连。**

**支持的代理客户端：** PassWall · PassWall2 · OpenClash · Nikki · HomeProxy。支持情况取决于客户端版本和转发模式。[兼容说明](COMPATIBILITY.md)

Proxy Guard 是 OpenWrt 和 iStoreOS 的 LuCI 插件。启用保护后，确认代理故障时会自动阻断所选设备的外网流量，恢复检查通过后再放行。保护覆盖实际经过路由器的 IPv4、IPv6、TCP、UDP 流量，包括已建立的连接。

<a id="guide-editions"></a>

## 1.0.0 版本

按固件选择安装包。opkg 使用 IPK（`1.0.0-8`），apk 使用 APK（`1.0.0-r8`）。[GitHub Releases](https://github.com/beezcheyenna/Proxy-Guard/releases) · [安装指南](USAGE.md) · [更新日志（英文）](CHANGELOG.md)

## 主要功能

- **连接检测。** 默认经本机 SOCKS 使用官方 HTTPS，可切换到第三方 HTTPS，并分别调整检测间隔和失败阈值。可选的出口 IPv4 校验默认读取官方接口的结果。
- **开机、定时和故障保护。** 可在路由器启动、每天或指定星期的时段、确认代理故障时阻断外网。也可监测代理客户端服务和运行日志。
- **设置引导和自动回退。** 核对建议的 IPv4、IPv6 保护范围。应用后检查规则，在 30 秒内确认。确认弹窗会显示当前放行或阻断状态。
- **实时状态和诊断。** 查看事件日志和恢复记录，通过 SOCKS 测试当前表单，也可按需执行一次详细 HTTPS 诊断。
- **可选内网控制 API。** 经认证的客户端可查询状态、申请限时断网和撤回自己的请求。[API 使用说明](USAGE.md#local-api)
- **客户端监测和自动恢复。** 监测所配置的代理服务和运行日志。Proxy Guard 进程失去响应时，守护进程可按设定限制尝试重启。

<a href="images/luci-overview.png"><img src="images/luci-overview.png" alt="Proxy Guard 的 LuCI 首页，显示实时状态和基本设置" width="640"></a>

<a id="guide-setup"></a>

## 安装与首次设置

1. 通过 LuCI 或命令行安装与固件匹配的 1.0 安装包。
2. 在 LuCI 打开 **服务 → 代理连接保护**，通过引导核对代理客户端、SOCKS 端口、入口设备、地址范围和局域网例外。先选 **仅监测**，点击 **保存并应用** 并确认，再用一台设备核对实际流量路径。
3. 准备好后切换到保护模式，点击 **保存并应用**。自检通过后在 30 秒内确认。规则待核验时，保留按钮暂不可用，原倒计时继续。未确认会自动回退。

首次安装时，保护总开关、定时保护、出口 IPv4 校验和内网控制 API 默认关闭。**保存**只暂存编辑，**保存并应用**才会生效。

<a id="guide-requirements"></a>
<a id="guide-scope"></a>

## 兼容与保护范围

路由器需要 LuCI 和 firewall4/nftables。插件仅保护实际经过路由器的流量。同网段无 NAT 的旁路由可能收不到回程流量。局域网、DNS 和管理访问按配置保留。转发模式和流量卸载限制见[兼容说明](COMPATIBILITY.md)。

<a id="guide-docs"></a>

## 使用说明

[用户指南](USER-GUIDE.md) · [安装与卸载](USAGE.md) · [故障排查与恢复](RECOVERY.md) · [源码构建](BUILDING.md) · [隐私说明](PRIVACY.md) · [PGHB 心跳与诊断说明](PGHB.md)

[MIT 许可证](../LICENSE) · [第三方声明](THIRD_PARTY_NOTICES.zh-CN.md) · [免责声明](DISCLAIMER.md) · [参与贡献](CONTRIBUTING.zh-CN.md)

[Proxy Guard 0.3 归档](../archive/0.3/README.md)
