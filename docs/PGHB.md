# PGHB 心跳与诊断

[English](PGHB.en.md) · [简体中文](PGHB.md) · [日本語](PGHB.ja.md) · [Русский](PGHB.ru.md) · [فارسی](PGHB.fa.md)

## 三个入口分别做什么

| 入口 | 用途 |
| --- | --- |
| 官方 PGHB `https://hb.pghb.app/` | 通过本机 SOCKS 做轻量连通性检测，开启出口 IPv4 校验后也可复用这份响应。 |
| 官方 PGHB `https://hb.pghb.app/f` | 按需返回详细连接信息。在 LuCI 打开「测试当前代理」，再点击「运行详细诊断」。也可在路由器设置中将其设为内网 API 的诊断目标。 |
| 路由器 `/cgi-bin/proxy-guard-api/*` | 需要认证的内网控制接口，可查状态、执行诊断、发起或撤回限时断网。请求路由器的 HTTPS 地址并使用 API UUID。 [内网 API 请求与响应](USAGE.md#local-api) |

「测试当前代理」使用未保存的表单设置。「运行详细诊断」使用已应用的代理设置。详细诊断通过只说明这次经 SOCKS 的请求成功，是否放行以当前保护状态为准。

## Proxy Guard 1.0 的校验规则

- PGHB 必须返回 HTTP `200`，正文逐字节匹配 `ネットは広大だわ`。正文是 24 字节的 UTF-8，无换行或 BOM。
- 请求 `/f` 时，Proxy Guard 发送新生成的 `X-PGHB-Nonce`，服务端原样回显后诊断才会通过。诊断随机数和 API UUID 分别使用，API UUID 只发给路由器。
- 标头名不区分大小写。同一个标头块内重复的 `X-PGHB-IP` 或 `X-PGHB-Nonce` 会使校验失败。其他诊断标头的重复项可分别返回，有歧义的可选摘要字段会省略。
- 插件读取的 HTTP 响应头上限为 **32 KiB（32,768 字节）**。捕获诊断标头时，标头数组序列化后的 JSON 也须在 **32 KiB** 以内。两处都是总量限制，计入格式开销。
- 启用出口 IPv4 校验并选择 PGHB 时，`X-PGHB-IP` 必须提供匹配预期的 IPv4。国家或地区、ASN、浏览器标头等可选字段用于诊断，缺失时不会因此判定连接故障。

诊断中的 `X-PGHB-*` 值按响应顺序以字符串返回，非 UTF-8 值带有 `"encoding":"base64"`。服务端新增格式有效的 `X-PGHB-*` 标头时，诊断可以直接返回。本页记录插件当前如何使用 PGHB。

## 详细响应字段

所列 `/f` 配置清单有 **102 项标头**。单次响应可能少于这个数量。动态值为空或未定义时，Cloudflare 可能省略对应标头。部分数值不可用时会返回 `0`。「缺失或不可用」说明可能省略或没有诊断意义的条件。单位栏的横线表示无数值单位。 [Cloudflare 响应头规则](https://developers.cloudflare.com/rules/transform/response-header-modification/#important-remarks) · [字段参考](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/)

轻量 `/` 使用 IP、国家或地区、ASN、TLS 和 Ray 五个基础字段。PGHB 返回的地址是 Cloudflare 看到的请求来源。路由器经 SOCKS 请求时，这些信息反映的是代理出口路径。

分享诊断前请检查并遮盖敏感值。结果可能含地址、近似地理位置、TLS 标识或请求回显，如 Cookie、Authorization 和 URL 查询参数。 [隐私说明](PRIVACY.md)

### 连接、路由与 TLS

| 标头 | Cloudflare 表达式或固定值 | 单位 | 缺失或不可用 | 是否参与校验 |
| --- | --- | --- | --- | --- |
| `X-PGHB-IP` | `to_string(ip.src)` | — | 只返回 IPv6 时无法校验 IPv4 | 可选出口 IPv4 校验 |
| `X-PGHB-Country` | `ip.src.country` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-ASN` | `to_string(ip.src.asnum)` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-City` | `ip.src.city` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Region` | `ip.src.region` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Region-Code` | `ip.src.region_code` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Continent` | `ip.src.continent` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Latitude` | `ip.src.lat` | 度 | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Longitude` | `ip.src.lon` | 度 | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Metro-Code` | `ip.src.metro_code` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Postal-Code` | `ip.src.postal_code` | — | IP 地理位置或 ASN 不可用 | 否 |
| `X-PGHB-Client-Port` | `to_string(cf.edge.client_port)` | — | 传输层信息不可用 | 否 |
| `X-PGHB-Client-TCP` | `to_string(cf.edge.client_tcp)` | — | 传输层信息不可用 | 否 |
| `X-PGHB-Edge-IP` | `to_string(cf.edge.server_ip)` | — | 边缘数据不可用 | 否 |
| `X-PGHB-Edge-Port` | `to_string(cf.edge.server_port)` | — | 边缘数据不可用 | 否 |
| `X-PGHB-HTTP` | `http.request.version` | — | 通常有值 | 否 |
| `X-PGHB-SSL` | `to_string(ssl)` | — | 通常有值 | 否 |
| `X-PGHB-Delivery-Rate` | `to_string(cf.edge.l4.delivery_rate)` | 字节/秒 | 无 L4 统计时为 `0` | 否 |
| `X-PGHB-TCP-RTT` | `to_string(cf.timings.client_tcp_rtt_msec)` | 毫秒 | 非 TCP 连接时为 `0` | 否 |
| `X-PGHB-QUIC-RTT` | `to_string(cf.timings.client_quic_rtt_msec)` | 毫秒 | 非 QUIC 连接时为 `0` | 否 |
| `X-PGHB-Edge-Time` | `to_string(cf.timings.edge_msec)` | 毫秒 | 边缘数据不可用 | 否 |
| `X-PGHB-Origin-TTFB` | `to_string(cf.timings.origin_ttfb_msec)` | 毫秒 | 源站计时不可用，例如缓存命中 | 否 |
| `X-PGHB-Worker-Time` | `to_string(cf.timings.worker_msec)` | 毫秒 | 无 Worker 执行或计时数据 | 否 |
| `X-PGHB-Ray` | `cf.ray_id` | — | 通常有值 | 否 |
| `X-PGHB-Zone` | `cf.zone.name` | — | 边缘数据不可用 | 否 |
| `X-PGHB-TLS` | `cf.tls_version` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-Cipher` | `cf.tls_cipher` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-TLS-Hello` | `to_string(cf.tls_client_hello_length)` | 字节 | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-Ciphers-SHA1` | `cf.tls_client_ciphers_sha1` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-TLS-Extensions` | `cf.tls_client_extensions_sha1` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-Extensions-LE` | `cf.tls_client_extensions_sha1_le` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-TLS-Client-Random` | `cf.tls_client_random` | — | 无可用 TLS 握手数据 | 否 |
| `X-PGHB-MTLS-Presented` | `to_string(cf.tls_client_auth.cert_presented)` | — | 未使用 mTLS 时通常为 `false` | 否 |
| `X-PGHB-MTLS-Verified` | `to_string(cf.tls_client_auth.cert_verified)` | — | 未使用 mTLS 时通常为 `false` | 否 |

### 请求信息与回显

| 标头 | Cloudflare 表达式或固定值 | 单位 | 缺失或不可用 | 是否参与校验 |
| --- | --- | --- | --- | --- |
| `X-PGHB-Host` | `http.host` | — | 通常有值 | 否 |
| `X-PGHB-Method` | `http.request.method` | — | 通常有值 | 否 |
| `X-PGHB-Path` | `http.request.uri.path` | — | 通常有值 | 否 |
| `X-PGHB-URI` | `http.request.uri` | — | 通常有值 | 否 |
| `X-PGHB-Full-URI` | `http.request.full_uri` | — | 通常有值 | 否 |
| `X-PGHB-Raw-Path` | `raw.http.request.uri.path` | — | 通常有值 | 否 |
| `X-PGHB-Raw-URI` | `raw.http.request.uri` | — | 通常有值 | 否 |
| `X-PGHB-Raw-Full-URI` | `raw.http.request.full_uri` | — | 通常有值 | 否 |
| `X-PGHB-Query` | `http.request.uri.query` | — | 没有查询参数 | 否 |
| `X-PGHB-Raw-Query` | `raw.http.request.uri.query` | — | 没有查询参数 | 否 |
| `X-PGHB-URI-Extension` | `http.request.uri.path.extension` | — | 路径没有扩展名 | 否 |
| `X-PGHB-Timestamp` | `to_string(http.request.timestamp.sec)` | Unix 秒 | 边缘数据不可用 | 否 |
| `X-PGHB-Received-MS` | `to_string(http.request.timestamp.msec)` | 秒内毫秒数（0–999） | 边缘数据不可用 | 否 |
| `X-PGHB-Request-ID` | `uuidv4(cf.random_seed)` | — | 通常有值 | 否 |
| `X-PGHB-Headers-Truncated` | `to_string(http.request.headers.truncated)` | — | 通常有值 | 否 |
| `X-PGHB-Verified-Bot` | `to_string(cf.client.bot)` | — | 通常有值 | 否 |
| `X-PGHB-Verified-Bot-Category` | `cf.verified_bot_category` | — | 没有可用的 Bot 分类 | 否 |
| `X-PGHB-Nonce` | `http.request.headers["x-pghb-nonce"][0]` | — | 请求未携带随机数时缺失 | `/f` 随机数匹配 |
| `X-PGHB-Accept` | `http.request.headers["accept"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Accept-Encoding` | `http.request.headers["accept-encoding"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Accept-Language` | `http.request.headers["accept-language"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Authorization` | `http.request.headers["authorization"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Cookie` | `http.cookie` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-User-Agent` | `http.user_agent` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Origin` | `http.request.headers["origin"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Referer` | `http.referer` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Range` | `http.request.headers["range"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-DNT` | `http.request.headers["dnt"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-GPC` | `http.request.headers["sec-gpc"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Save-Data` | `http.request.headers["save-data"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Upgrade-Insecure` | `http.request.headers["upgrade-insecure-requests"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Sec-Purpose` | `http.request.headers["sec-purpose"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Fetch-Dest` | `http.request.headers["sec-fetch-dest"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Fetch-Mode` | `http.request.headers["sec-fetch-mode"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Fetch-Site` | `http.request.headers["sec-fetch-site"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Fetch-User` | `http.request.headers["sec-fetch-user"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Client-Hints-UA` | `http.request.headers["sec-ch-ua"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Client-Hints-Mobile` | `http.request.headers["sec-ch-ua-mobile"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Client-Hints-Platform` | `http.request.headers["sec-ch-ua-platform"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-UA-Arch` | `http.request.headers["sec-ch-ua-arch"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-UA-Bitness` | `http.request.headers["sec-ch-ua-bitness"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-UA-Full-Version-List` | `http.request.headers["sec-ch-ua-full-version-list"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-UA-Platform-Version` | `http.request.headers["sec-ch-ua-platform-version"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Top-Language` | `http.request.accepted_languages[0]` | — | 没有可用的首选语言 | 否 |
| `X-PGHB-If-Match` | `http.request.headers["if-match"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-If-Modified-Since` | `http.request.headers["if-modified-since"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-If-None-Match` | `http.request.headers["if-none-match"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-If-Unmodified-Since` | `http.request.headers["if-unmodified-since"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Request-Cache-Control` | `http.request.headers["cache-control"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Request-Content-Length` | `http.request.headers["content-length"][0]` | 字节 | 请求未携带该标头或值 | 否 |
| `X-PGHB-Request-Content-Type` | `http.request.headers["content-type"][0]` | — | 请求未携带该标头或值 | 否 |
| `X-PGHB-Request-Priority` | `http.request.headers["priority"][0]` | — | 请求未携带该标头或值 | 否 |

### 响应信息与常量

| 标头 | Cloudflare 表达式或固定值 | 单位 | 缺失或不可用 | 是否参与校验 |
| --- | --- | --- | --- | --- |
| `X-PGHB-Response-Code` | `to_string(http.response.code)` | — | 通常有值 | 否 |
| `X-PGHB-Response-Type` | `http.response.content_type.media_type` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Cache-Control` | `http.response.headers["cache-control"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Content-Length` | `http.response.headers["content-length"][0]` | 字节 | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Encoding` | `http.response.headers["content-encoding"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-ETag` | `http.response.headers["etag"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Age` | `http.response.headers["age"][0]` | 秒 | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Last-Modified` | `http.response.headers["last-modified"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Location` | `http.response.headers["location"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Response-Vary` | `http.response.headers["vary"][0]` | — | 源响应字段缺失 | 否 |
| `X-PGHB-Error-Code` | `to_string(cf.response.1xxx_code)` | — | 无 Cloudflare 1xxx 错误时为 `0` | 否 |
| `X-PGHB-Error-Type` | `cf.response.error_type` | — | 没有 Cloudflare 错误分类 | 否 |
| `X-PGHB-Endpoint` | `full` | — | `/f` 固定值 | 否 |
| `X-PGHB-Heartbeat-Version` | `1` | — | `/f` 固定值 | 否 |
| `X-PGHB-Schema-Version` | `1` | — | `/f` 固定值 | 否 |
| `X-PGHB-Service` | `PGHB` | — | `/f` 固定值 | 否 |

表中两项参与校验的字段各有用途。上述重复标头规则对两者均生效。插件独立检查实际 HTTP 状态，`X-PGHB-Response-Code` 字符串仅供诊断。

TCP 和 QUIC RTT 反映到 Cloudflare 的连接，路由器 API 的 `milliseconds` 是路由器自身的探测耗时。Cloudflare 收到请求的时间由 `Timestamp` 的秒数和 `Received-MS` 的秒内毫秒数组成。`Edge-IP` 是 Cloudflare 边缘地址，`IP` 是观测到的请求来源地址。

[使用指南](USER-GUIDE.md) · [内网 API](USAGE.md#local-api) · [响应解析源码](../package/root/usr/lib/proxy-guard/public-heartbeat.lua#L45-L95)
