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

根据固件选择对应的安装和卸载命令。下方 APK 安装示例使用 `--no-network`，需要依赖已安装或可从本地软件源获取。要从匹配当前固件的已配置软件源在线安装缺少的依赖，去掉 `--no-network`。测试保护前，保留一条独立的管理通路。

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="from-0-3"></a>

## 从 0.3 迁移到 1.0

请用 1.0 的全新配置开始。已发布的 0.3 安装包直接覆盖到 1.0，以及从 1.0 降回 0.3，均未作为受支持的迁移路径验收。两代路由器安装包均将 `/etc/config/proxy_guard` 声明为配置文件，包管理器可能保留修改过的 0.3 文件。安装程序会调整部分已识别的旧检测默认值，并补齐部分缺失选项。旧文件即使保留，也要重新核对设置是否适用。

先保留独立管理通路，备份 0.3 配置，并妥善保存恢复旧部署所需的凭据和对应安装包。明确关闭旧路由器保护。已安装 0.3 Pro 时，在处理好下文的远端策略后先卸载 Pro，再卸载 0.3 普通版并安装 1.0。如果旧设置仍在，在「配置与诊断」选择「恢复默认并重新引导」。手动录入已核对的保护范围、例外、SOCKS 设置和定时规则。

1.0 全新配置默认使用官方 HTTPS，出口 IPv4 校验关闭。保留下来的旧配置若未指定检测方式，1.0 会使用官方 HTTPS。想继续使用原来的 gstatic 和 Ubuntu 目标，可在「连接检测」选择第三方 HTTPS。

若 0.3 Pro 还在管理 VPS，趁控制通路可用，通过 0.3 Pro 撤回需要移除的策略，并从 VPS 核对结果。1.0 未集成 0.3 Pro。远端规则、Agent 和 Cloudflare 资源需要通过独立管理通路另行处理。 [归档救援说明](https://github.com/beezcheyenna/Proxy-Guard/blob/987ff38a25c1a00f2c05753f7503e134391a4a3a/docs/RECOVERY.md)

[0.3 源码、安装包和文档](../archive/0.3/README.md)


<a id="guide-setup"></a>

## 首次设置

**停止 Proxy Guard 服务后，防火墙规则可能仍在阻断。** 需要解除阻断时，请明确关闭保护或按[故障救援步骤](RECOVERY.md)操作。

**「测试当前代理」通过仅说明本次探测成功。** 定时保护、API 限时断网或另一路检测故障仍可能阻断外网。

打开「服务 → 代理连接保护」。通过引导核对入口设备、IPv4 和 IPv6 范围、局域网例外及 SOCKS 端口。先使用「仅监测」，保存并应用后系统自检，通过后有 30 秒确认。自检失败或未确认时会回退配置。

默认通过本机 SOCKS 请求固定的官方 HTTPS 地址。第三方 HTTPS 可单独选择，间隔与阈值独立。出口 IPv4 校验初始关闭，开启后默认读取官方响应里的地址。使用第三方 IP 服务时，主地址超时才尝试备用地址。

官方 HTTPS 默认在检测完成后等待 3 秒，单次请求超时 2 秒。第三方 HTTPS 默认在每轮结束后等待 10 秒，每个目标超时 4 秒。默认检测 gstatic 和 Ubuntu，常规轮至少需要一个站点成功。启用保护且处于常规检测时，官方模式默认连续失败 2 次确认故障，第三方模式默认连续失败 3 轮确认故障。两种模式默认连续成功 2 次或 2 轮确认恢复。敏感检测期间，一次失败就可能触发阻断。

第三方文本 IP 的主、备用地址都超时，且连通性仍正常、没有待解除的出口地址不匹配时，本次出口校验不会单独触发阻断。默认主地址 `https://api.ipify.org/` 超时后使用 `https://4.ident.me/`。自定义主地址且未设备用地址时，主地址超时会记为「无法校验」，并按当前模式和故障阈值处理。若此前已确认出口地址不符，仍需取得匹配的 IPv4 才能恢复。

若规则待核验，「确认保留此配置」暂不可用，原倒计时继续。超时后路由器会自动恢复之前的配置，即使网页已经关闭。

<a id="test-current-proxy"></a>

## 测试当前代理

在 LuCI 点击「测试当前代理」，可以用尚未保存的表单参数通过 SOCKS 检测，查看连通性、耗时和取得的出口 IPv4。同一弹窗中的「运行详细诊断」使用已应用的代理设置。保护设置在点「保存并应用」后生效。

主页显示连续失败次数和当前生效的阻断原因。一次失败尚未达到阈值时仍可能放行。定时保护、API 限时断网和代理检测故障可以同时存在。

内网 API 在全新安装时关闭。启用后使用页面显示的 UUID 查询状态、执行诊断、发起或撤回限时断网。

## 验收开机保护

保留独立管理通路后，重启运行 Proxy Guard 的路由器。用受保护客户端验证路由器启动期间外网被阻断，且只在通过配置的恢复检查后重新放行。

<a id="local-api"></a>

## 内网 API

在 LuCI 的「内网控制 API」启用接口，点「保存并应用」，如有提示再确认保留设置。同一页会显示可复制的 **API UUID**。每次请求都要带 `Authorization: Bearer YOUR_UUID`。

**UUID 是访问凭据。** 关闭接口后重新启用，或在 API 启用时重启路由器，都会生成新 UUID。调用程序需要更新凭据。调用程序只需提供 API UUID。通过认证和来源检查的请求，响应会带上 UUID，管理员也可在 LuCI 事件日志查看。分享响应或日志前请遮盖 UUID。

**请求路由器原有的 HTTPS 管理地址。** API 接受本机回环，或能经名为 `lan` 的防火墙区域内的设备直接回程的来源。必须经其他网关才能到达的来源会被拒绝。其他内网区域、三层 VLAN 或 VPN 来源可能返回 `403 lan_required`。请使用证书对应的主机名。若路由器使用私有 CA 或自签证书，可用 curl 的 `--cacert` 指定可信的 CA 或路由器证书。

将 `router.example` 换成路由器的 HTTPS 管理主机名，将 `YOUR_UUID` 换成当前 API UUID。下方 JSON 使用示例值。两个 POST 操作会改变保护范围内的外网访问，请按需调用。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | [`/status`](#api-status) | 查询保护状态 |
| GET | [`/diagnostics`](#api-diagnostics) | 执行单次诊断 |
| POST | [`/block`](#api-block) | 发起限时断网 |
| POST | [`/cancel`](#api-cancel) | 撤回限时断网 |

<a id="api-status"></a>

### 查询保护状态

`GET /status` 读取当前防火墙状态和正在生效的 API 断网请求。示例显示已有一项限时断网。程序请读取 `enforcement` 和 `block_reasons`，`reason` 是显示用文本。`last_check` 是最近一次完成检测的 Unix 秒级时间戳，无记录时可省略。防火墙状态未知、规则缺失或尚未核实时，`blocked` 也可省略，此时应根据 `enforcement` 判断状态是否已确认。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/status'
```

HTTP 200

```json
{
  "ok": true,
  "api_version": 2,
  "uuid": "YOUR_UUID",
  "enabled": true,
  "mode": "guard",
  "check_mode": "web",
  "phase": "blocked",
  "enforcement": "blocked",
  "blocked": true,
  "reason": "API 限时断网生效中",
  "block_reasons": [
    "api"
  ],
  "failure_progress": {
    "count": 0,
    "threshold": 3
  },
  "last_check": 1794628800,
  "stale": false,
  "heartbeat": {
    "enabled": false,
    "allowed": true
  },
  "api": {
    "enabled": true,
    "count": 1,
    "remaining": 95
  },
  "requests": [
    {
      "request_id": "example-block-01",
      "remaining": 95
    }
  ],
  "default_seconds": 300,
  "max_seconds": 3600,
  "exit_check": {
    "enabled": false
  }
}
```

<a id="api-diagnostics"></a>

### 执行诊断

`GET /diagnostics` 通过本机 SOCKS 发起一次检测，并在同一次请求中返回结果。「API 刷新地址」默认使用 PGHB `/`。要取得示例里的详细标头，请先在设置里选择 `/f` 并应用。 [PGHB 响应说明](PGHB.md)

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "diagnostics": {
    "ok": true,
    "source": "https://hb.pghb.app/f",
    "checked_at": 1794628800,
    "http_code": 200,
    "curl_code": 0,
    "milliseconds": 117,
    "nonce_verified": true,
    "headers": [
      {
        "name": "x-pghb-ip",
        "value": "203.0.113.10"
      },
      {
        "name": "x-pghb-tls",
        "value": "TLSv1.3"
      },
      {
        "name": "x-pghb-nonce",
        "value": "0123456789abcdef0123456789abcdef"
      }
    ]
  }
}
```

`diagnostics.headers` 按响应顺序列出 `X-PGHB-*` 的名称和值。值以字符串返回。重复的 `X-PGHB-IP` 或 `X-PGHB-Nonce` 会使校验失败，其他同名标头可以分项返回。非 UTF-8 值带有 `"encoding":"base64"`。`checked_at` 是 Unix 秒级时间戳。

<a id="api-block"></a>

### 发起限时断网

`POST /block` 要求保护模式已启用，断网作用于配置的保护范围。默认时长 300 秒，初始上限 3600 秒。省略 `seconds` 或填 `0` 使用配置的默认时长。省略 `request_id` 时由路由器生成。自定义 ID 使用 8 至 64 个字母、数字、连字符或下划线。相同 ID 和时长重试仍在生效的请求，会保留原到期时间。时长不同会返回 `409 request_conflict`。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"seconds":120,"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/block'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "effective": true,
  "remaining": 120,
  "seconds": 120
}
```

<a id="api-cancel"></a>

### 撤回限时断网

`POST /cancel` 需要提供待撤回的请求 ID。归属按通过认证的 UUID 和请求 ID 匹配。使用同一 UUID 的设备或程序共享身份。有效的 ID 已过期或没有对应请求时，接口仍可返回 `cancelled: true`。`effective` 和 `remaining` 描述仍生效的 API 断网。定时保护和检测故障仍可继续阻断。

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/cancel'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "cancelled": true,
  "effective": false,
  "remaining": 0
}
```

### 常见错误

| HTTP 状态及错误 | 处理方法 |
| --- | --- |
| 401 `authentication_required` | UUID 缺失或无效，核对 LuCI 显示的当前值。 |
| 403 `https_required`、`api_disabled` 或 `lan_required` | 检查 HTTPS、API 开关或调用端到 `lan` 防火墙区域的路径。 |
| 409 `configuration_pending`、`configuration_changed`、`protection_not_active` 或 `request_conflict` | 完成并确认设置后重试诊断，或核对保护模式及请求 ID 对应的时长。 |
| 429 | 诊断仍在冷却，或有效请求数达到上限。有 `Retry-After` 时按响应给的时间等待。 |
| 502 / 504 | 诊断检测失败或超时。有 `diagnostics` 时可查看其中的详情。 |
| 503 `busy` | 另一个操作正在进行。按 `Retry-After` 给出的秒数等待后重试。 |
| 503 `policy_not_ready`、`request_state_unavailable` 或 `firewall_failed` | 防火墙策略未就绪、断网请求状态不可用或更新规则失败。先查看保护状态和事件日志，再重试同一请求 ID。 |

[使用指南](USER-GUIDE.md) · [故障救援](RECOVERY.md)
