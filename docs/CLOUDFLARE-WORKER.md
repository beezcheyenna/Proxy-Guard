# Cloudflare Worker 配套（Pro）

[English](CLOUDFLARE-WORKER.en.md) · [简体中文](CLOUDFLARE-WORKER.md) · [日本語](CLOUDFLARE-WORKER.ja.md) · [Русский](CLOUDFLARE-WORKER.ru.md) · [فارسی](CLOUDFLARE-WORKER.fa.md)

Worker 为 Pro 提供设备认证、家庭公网地址观察和策略转发，使用 Agent v3 协议。部署时需要兼容的 Pro 扩展和 VPS Agent。一个 Worker 对应一组设备身份和一个固定 `VPS_API` 绑定。

## 可复现的依赖和离线检查

使用 Node.js 22+，通过 package-lock.json 固定 Wrangler 4.156.0 与 Miniflare 5.20261023.3-beta。部署命令使用本地依赖，不在部署时浮动获取任意 Wrangler 4 版本。兼容日期以 `wrangler.jsonc` 为准，当前为 `2026-11-01`；变更日期或工具版本后应重新核对对应运行时。

在专用隔离 Linux 测试环境中，先进入解压后的 `companion/worker` 目录，再执行：

```sh
npm ci
npm test
npm run test:persistence
npm run check:bundle
```

`npm ci` 会按锁文件准备依赖，首次执行通常需要联网下载；依赖准备好后，本地测试不需要连接 Cloudflare。部署需要另行联网和授权，不能将本地测试当作云端部署验收。

真实 nftables 检查只在一次性测试 VM 的私有网络命名空间运行，`test/run_checks.sh`、`test/run_final.sh` 需要匹配的专用测试夹具和工作目录。维护契约测试用记录执行器，不执行真实系统重启。kernel_lease_test.py 额外核对 120 秒内核授权在 125 秒后消失、冷启动不恢复动态授权。

## 部署配置

先在目标测试或正式环境独立安装并验收 Pro Agent。Worker 不是 Agent 安装器。创建专用 Tunnel，在同一目标机器运行 cloudflared；VPC Service 只指向该机器回环 Agent 端口，通常是 HTTP 127.0.0.1:8788。Worker 的 VPS_API 绑定指向这个 Service 的 ID，不绑定整个 VPC Network。

- DEVICE_ID 必须与 Agent 一致。
- DEVICE_TOKEN 是设备到 Worker 的独立随机凭据。
- AGENT_SECRET 是 Worker 到 Agent 的另一随机凭据，不能与 DEVICE_TOKEN 相同。
- 两个凭据均由 32 至 256 个字母、数字、下划线或短横线字符组成，不接受 REPLACE_ 占位值。
- .dev.vars.example 用于部署模板识别所需密钥；只把实际值写入私有秘密配置，不能提交 .dev.vars 或 .env。
- 替换 wrangler.jsonc 中的 Service ID，预先设置所需密钥，或使用 npm run deploy -- --secrets-file /path/to/private-secrets.json 同时提交测试密钥。密钥文件使用 DEVICE_TOKEN、AGENT_SECRET 两个 JSON 字段；不得提交该文件。当前默认示例没有可用的线上资源 ID。

VPC Service 的固定 host/port 决定连接目标；fetch URL 中的主机和端口不能扩张到其他目的地址。服务配置和绑定仍须在 Cloudflare 上核对。

## 接口与数据

自定义客户端应使用明确的应用 User-Agent，例如 `ProxyGuardPro/0.2.0`。如果收到 Cloudflare `1010`，应检查客户端标识与账户安全策略；不要直接关闭安全检查。

所有接口要求 HTTPS 和 Bearer 设备凭据；不接受查询参数。/v1/observe 只观察 Cloudflare 看到的公网地址，不续期 Agent 授权。Worker 子请求来源和保留地址会被拒绝。

/v1/sync 必须携带刚观察到的相同地址。Worker 用独立 HMAC-SHA256 签名精确 JSON 字节，生成新请求 ID；Agent 校验签名、时效、重放与修订号。相同修订号只能续期相同策略。IPv4/IPv6 分别续期，租期 120 至 86400 秒；停止同步后授权到期，状态查询不续期。

/v1/status 仅返回 Pro 客户端确认策略、租期、健康与维护结果所需的字段。始终请求 include_analysis=false，剔除管理来源地址、监听清单、事件、认证来源详情和未知扩展字段。

/v1/command 仅允许 restart_xray 和 reboot_vps，使用固定操作 ID、策略修订号及 1 至 60 秒有效窗口。Agent 仍必须单独启用相应动作。未知结果不能当作执行失败而重新生成操作 ID；只用原 ID 查询或重试去重结果。Worker 不转发任意上游错误对象，保留客户端可识别的固定拒绝码。上游响应按流式字节数限制为 32768 字节。

Agent 同步确认按应用防火墙后的实际剩余单调时钟租期计算 expires_at，避免慢应用延长客户端看到的授权时间。

## 验证边界

已进行 Worker、VPC Service、Tunnel、Agent 和 OpenWrt 客户端的联合测试。部署后仍需核对自己的绑定、凭据与实际客户端请求。

仓库的 `companion/worker/` 目录提供独立的 Wrangler 项目和密钥模板。通过 Wrangler 部署 Worker 前，先创建 Tunnel/VPC Service 并设置绑定；部署命令不会安装 Agent 或自动创建整套配套资源。

参考：

- https://developers.cloudflare.com/workers-vpc/api/
- https://developers.cloudflare.com/workers-vpc/get-started/
- https://developers.cloudflare.com/workers/platform/deploy-buttons/

客户端兼容参考：https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/

## 版本与部署范围

路由器 Pro 安装包 与 [Worker 工具项目](../companion/worker/package.json)独立编号。npm 项目 version=0.2.0 不是当前 Pro 安装包版本；Node.js 及工具要求以 package.json 和锁文件为准。只部署 Worker 不会自动创建 VPS、Tunnel 或 VPC Service。

## 只读出口候选接口

`POST /v1/egress-info` 使用现有设备 Bearer 及非空 JSON `{ "device_id": "home" }`，只转发到固定 VPS_API 的同名 HMAC 接口。来源仅为 interface/panel/measured，未知内部字段不导出；空候选、过期及歧义以带警告的快照返回，不能自动写成预期出口。测量默认关闭，接口不续租、不记控制心跳、不确认配置。旧 Agent 返回 501 `egress_info_unsupported`。接口协议、固定测量目标和集成方式见 [Agent 接口说明](VPS-EGRESS-INFO.zh-CN.md)。

[Worker 目录指南](../companion/worker/README.zh-CN.md)
