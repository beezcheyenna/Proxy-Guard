# 只读 IPv4 出口候选（模式 1）

[English](VPS-EGRESS-INFO.md) · [简体中文](VPS-EGRESS-INFO.zh-CN.md) · [日本語](VPS-EGRESS-INFO.ja.md) · [Русский](VPS-EGRESS-INFO.ru.md) · [فارسی](VPS-EGRESS-INFO.fa.md)

接口给引导页提供候选证据。它不会选择或写入预期 IPv4，不应用策略、不续期、不记录 SSH 两路心跳、不执行维护，也不确认或延长配置试运行。接口地址、面板监听提示、主机默认路由测量分别说明不同事实，实际代理业务路径要另行验证。

## API

- Cloudflare：`POST /v1/egress-info`，设备 Bearer 和 JSON `{"device_id":"home"}`。原生 `luci.jsonc` 要用非空对象，Lua 空表会序列化成数组。
- Agent 中继：签名 `POST /v1/egress-info`。现有 HMAC 校验 `device_id`、`issued_at`、唯一 `request_id` 和 `purpose:"egress-info"`。其他路由拒绝这个用途。重放或过期请求按现有认证拒绝。
- 直连：`GET /v1/direct/egress-info`，现有直连 Bearer 与 HTTPS、公网绑定要求。不把对端 IP 当候选。

无公网候选时的示例：

```json
{
  "ok": true,
  "protocol": 3,
  "egress_info_schema": 1,
  "generated_at": 1700000000,
  "status": "unavailable",
  "candidates": [],
  "ambiguous": false,
  "business_egress_verified": false,
  "warnings": [
    "measurement_disabled",
    "no_public_ipv4_candidate"
  ],
  "measurement": {
    "state": "disabled",
    "checked_at": null,
    "stale": true
  }
}
```

候选格式为 `{"ipv4":"8.8.8.8","evidence":[{"source":"interface","checked_at":1700000000,"scope":"host_interface"}]}`。示例地址只用于说明字段。`source` 为 `interface`、`panel` 或 `measured`，对应 `scope` 为 `host_interface`、`panel_config` 或 `host_default_ipv4`。探测时间和 `generated_at` 为 UTC Unix 秒，时效用单调时间。IPv4 去重后最多 8 个候选，每个最多 3 条证据。截断时优先保留测量值。多个不同公网 IPv4 会给出歧义警告。模式 1 的 `business_egress_verified` 始终是 false。消费者须手动选择，不能自动复制首条、自己的 `/observe` 结果、面板域名或 REALITY 目标。

`status` 为 `available`、`partial` 或 `unavailable`，独立于服务健康。`measurement.state` 为 `disabled`、`pending`、`fresh`、`stale`、`unavailable` 或 `conflict`。错误或超过两倍采样间隔后，上次成功值标为过期。关闭测量不会改变正常的服务保护。

固定警告码：`non_public_ipv4_omitted`, `no_public_ipv4_candidate`, `interface_unavailable`, `panel_unavailable`, `panel_hint_unverified`, `panel_hint_ignored`, `measurement_disabled`, `measurement_pending`, `measurement_failed`, `measurement_stale`, `measurement_disagreement`, `multiple_public_ipv4_candidates`, `host_default_not_business_egress`, `candidates_truncated`。界面翻译使用已有词库。

已认证的空、过期或歧义结果返回 200。直连认证失败为 401，签名或 nonce 失败为 403，请求体错误为 400，旧 Agent 为 501 `egress_info_unsupported`，VPC 不可用或上游数据无效为 502，采集异常为 503。错误不含原始路径、面板内容、网口名、测量响应体或凭据。响应保留 `Cache-Control: no-store`，采集缓存仅存在内存。

## Agent 配置与限制

可选 `egress` 对象仅接受下列字段：

```json
{
  "panel_config_path": "",
  "measure_enabled": false,
  "measure_interval": 300
}
```

面板采集默认关闭。显式配置的常规 JSON 文件须由 Agent 用户所有，禁止组和其他用户写入，末级不能是符号链接。最多读取 64 KiB。3x-ui 生成的 Xray 配置中，只把 `inbounds[].listen` 和 `outbounds[].sendThrough` 中的数字 IPv4 当未验证提示。不会解析 REALITY 目标、远端服务器、域名或凭据。

接口采集用固定命令 `ip -j -4 address show`，2 秒超时，输出限 64 KiB。本地缓存 15 秒。工具缺失或仅有非公网/NAT 接口时返回警告。

测量默认关闭。启用后后台只访问固定的 [ipify IPv4 API](https://api.ipify.org/)。请求及配置不接受自定义 URL、命令、刷新或目标参数。DNS 只保留公网 IPv4，TLS 固定连接该地址，并用固定域名校验 SNI 和证书。不使用代理环境变量、重定向、重试或凭据。套接字操作限 2 秒、响应体限 256 字节，隔离子进程含 DNS 总限 5 秒。间隔 60–3600 秒，默认 300。读取接口不会触发测量。标记为主机默认 IPv4，业务代理出口需独立确认。

## 集成

`--check-config` 校验 `egress`。安装器包含 `egress.py`，由 `control.Server` 管理采集周期。引导读候选走仅连接配置，支持同步关闭时调用，并保留端点确认、会话暂存凭据和 RPC 权限。读操作不提交、不应用、不排队维护，也不在 RPC 处理器里发测量请求。

## 隔离基础测试

只在自有测试 VM 中对候选或冻结文件运行：

```sh
python3 -B companion/vps/test_egress.py
cd companion/worker
node --test test/egress.test.mjs test/worker.test.mjs test/regression.test.mjs test/contract.test.mjs
```

采集测试注入测量数据，不连接真实反射服务。HTTP 契约测试运行真实 Agent、内存防火墙驱动，不修改实际 nft 规则。安装、真实代理路径和 Cloudflare 另行验证。
