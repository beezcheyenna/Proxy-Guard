# 安装与使用

[English](USAGE.en.md) · [简体中文](USAGE.md) · [日本語](USAGE.ja.md) · [Русский](USAGE.ru.md) · [فارسی](USAGE.fa.md)

在使用 LuCI 和 firewall4/nftables 的路由器上安装 Proxy Guard。安装包格式须与固件的包管理器匹配。

## 下载与校验

从同一个 Release 下载安装包与校验清单。opkg 固件用 IPK，apk 固件用 APK。依赖请从与当前固件匹配的软件源安装。

[GitHub Releases](https://github.com/beezcheyenna/Proxy-Guard/releases)

请选择实际下载的文件名。第一行选择 IPK。使用 APK 时，将变量改为下一行注释中的文件名。

```sh
PG_PACKAGE=luci-app-proxy-guard_1.0.0-8_all.ipk
# PG_PACKAGE=luci-app-proxy-guard-1.0.0-r8.apk
awk -v f="$PG_PACKAGE" '$2 == f { print; n++ } END { if (n != 1) exit 1 }' SHA256SUMS > SHA256SUMS.selected &&
sha256sum -c SHA256SUMS.selected
```

确认所选包的校验结果为 OK。在 macOS 上也可以运行 `shasum -a 256 "$PG_PACKAGE"`，将完整摘要与 `SHA256SUMS` 的对应条目比较。

SHA256 用于核对文件与清单是否一致。发布者身份需另行确认，安装包和清单应来自同一个可信发行。若在 apk 固件离线安装，先备齐匹配的依赖。

<a id="installation"></a>

## 安装与卸载

根据固件选择对应的安装和卸载命令。测试保护前，保留一条独立的管理通路。

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="guide-setup"></a>

## 首次设置

打开「服务 → 代理连接保护」。通过引导核对入口设备、IPv4 和 IPv6 范围、局域网例外及 SOCKS 端口。先使用「仅监测」，保存并应用后系统自检，通过后有 30 秒确认。自检失败或未确认时会回退配置。

默认通过本机 SOCKS 请求固定的官方 HTTPS 地址。第三方 HTTPS 可单独选择，间隔与阈值独立。出口 IPv4 校验初始关闭，开启后默认读取官方响应里的地址。使用第三方 IP 服务时，主地址超时才尝试备用地址。

官方 HTTPS 默认每 3 秒检查一次，超时 2 秒，连续失败 2 次才阻断、连续成功 2 次才恢复。第三方 HTTPS 默认间隔 10 秒，每个目标超时 4 秒，连续失败 3 轮阻断、成功 2 轮恢复。默认检测 gstatic 和 Ubuntu，常规轮至少需要一个站点成功。

第三方文本 IP 的主、备用地址都超时，而连通性仍正常时，可以继续放行。若此前已确认出口地址不符，仍需取得匹配的 IPv4 才能恢复。

若规则待核验，「确认保留此配置」暂不可用，原倒计时继续。超时后路由器会自动恢复之前的配置，即使网页已经关闭。

<a id="test-current-proxy"></a>

## 测试当前代理

在 LuCI 点击「测试当前代理」，可以用尚未保存的表单参数通过 SOCKS 检测，查看连通性、耗时和取得的出口 IPv4。保护设置在点「保存并应用」后生效。

主页显示连续失败次数和当前生效的阻断原因。一次失败尚未达到阈值时仍可能放行。定时保护、API 限时断网和代理检测故障可以同时存在。

内网 API 在全新安装时关闭。启用后使用页面显示的 UUID 查询状态、执行诊断、发起或撤回限时断网。

## 验收开机保护

保留独立管理通路后，重启运行 Proxy Guard 的路由器。用受保护客户端验证路由器启动期间外网被阻断，且只在通过配置的恢复检查后重新放行。

<a id="local-api"></a>

## 内网 API

在 LuCI 的「内网控制 API」启用接口，点「保存并应用」，如有提示再确认保留设置。同一页会显示可复制的 **API UUID**。这个 UUID 是四个接口共用的凭据。关闭接口后再开启会生成新的 UUID。

从内网访问路由器原有的 HTTPS 管理地址。用「API 刷新地址」选择普通心跳或详细诊断 `/f`。

| HTTP 方法 | `/cgi-bin/proxy-guard-api` 后的路径 | 用途 |
| --- | --- | --- |
| GET | `/status` | 查询保护状态和生效的 API 阻断 |
| GET | `/diagnostics` | 经 SOCKS 执行所选心跳检测并直接返回结果 |
| POST | `/block` | 发起限时断网 |
| POST | `/cancel` | 根据请求 ID 撤回限时断网 |

将 `router.example` 换成路由器 HTTPS 管理地址，将 `YOUR_UUID` 换成页面显示的 UUID。

```http
GET /cgi-bin/proxy-guard-api/diagnostics HTTP/1.1
Host: router.example
Authorization: Bearer YOUR_UUID
```

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

两个 POST 接口均使用 `Content-Type: application/json`。`/block` 的正文可以是 `{"seconds":120,"request_id":"sample-block-01"}`，`/cancel` 的正文是 `{"request_id":"sample-block-01"}`。省略时长或填 0 使用设置中的默认时长。省略请求 ID 由路由器生成。限时断网需要已启用保护模式。使用相同 ID 和相同时长重试生效中的请求，保留原到期时间。撤回请求后，其他生效的保护规则继续决定是否放行。

认证成功的响应带 `uuid`。诊断成功时，`diagnostics.headers` 按顺序返回 `X-PGHB-*` 标头的 `name` 和 `value`，保留同名标头和字符串原值。非 UTF-8 值带 `encoding: "base64"`。HTTP 401 表示 UUID 缺失或无效，403 表示 API 关闭或当前网络无法使用接口，429 表示冷却中或达到请求上限，502/504 表示心跳检测失败或超时。

有插件配置权限的 LuCI 用户能在事件日志中看到已认证请求的完整 UUID。分享日志前请遮盖 UUID。

[使用指南](USER-GUIDE.md) · [故障救援](RECOVERY.md)
