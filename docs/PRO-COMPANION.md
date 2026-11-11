# Pro VPS Agent 与控制链路

Pro 的 Linux VPS Agent 与可选 Cloudflare Worker 源码位于仓库的 `companion/` 目录。远程功能支持直接 HTTPS，或 Cloudflare Worker 与 Tunnel/VPC 控制链路；组件须另行部署，不随路由器安装包自动安装。当前路由器包版本为普通版 `0.3.0-21`、Pro `0.3.1-5`；配套协议和 Worker 工具项目的版本独立编号。

## 准备与安装

需要 Linux、Python 3.10+、nftables，以及 nf_conntrack、nf_conncount、nft_connlimit 内核支持。安装器按目标系统使用 systemd 或 OpenRC；只在明确选定的 VPS 上执行安装。安装前会执行规则及内核能力检查；缺失依赖时给出错误，不先启用限制。

在解压后的 `companion/` 目录中，将 `vps/agent.example.json` 复制为私有配置。完整步骤见 [Linux Agent 安装](LINUX-AGENT-INSTALL.md)。

- 设置 `device_id` 和至少 32 字符的独立随机 `agent_secret`。
- 直接 HTTPS 控制另外设置 `direct_token`，与路由器“设备密钥”配对；`agent_secret` 不交给路由器。
- 对外监听须显式设置 `public_control=true`、`bind`、`tls_cert` 和 `tls_key`，并使用有效证书。回环监听才允许 HTTP。
- `services` 填写实际 `process_names`、`tcp_ports` 和 `udp_ports`。空端口列表仅检查进程，不能证明端口已就绪。
- `managed_units` 填写实际代理服务，并使用 `name.service` 格式。systemd 对应真实单元；OpenRC 去掉 `.service` 后对应服务名，例如 `xray.service` 对应 `xray`。只给这些服务添加保护恢复依赖，不接受 SSH 服务。
- `path_token` 是独立的代理路径心跳密钥，不能与控制凭据共用。心跳必须经 OpenWrt 本地 SOCKS 发往可由代理访问的 Agent HTTPS 入口。直接 HTTPS 模式可以复用同一 Agent 根地址，但使用不同接口、密钥和流量路径；Cloudflare 模式不能用 Worker 控制入口代替。具体地址与凭据对应关系见[连接配置](LINUX-AGENT-INSTALL.md#control-and-path)。

先校验，再在目标 VPS 安装。以下以支持 `sudo` 的 systemd 环境为例；Alpine root 命令见安装指南。

```sh
python3 vps/agent.py --config /path/to/private-agent.json --check-config
sudo python3 vps/agent.py --config /path/to/private-agent.json --check-kernel
sudo sh vps/install.sh --install /path/to/private-agent.json
```

安装保留已有配置，不会用示例覆盖私有配置。独立 policy 服务在已配置的代理单元前恢复最后有效策略，动态授权不跨冷启动恢复。发行版启动顺序、initrd 提前联网、未列入 managed_units 的服务及系统防火墙清空规则仍需目标系统验收。

卸载：

```sh
sudo sh vps/uninstall.sh --remove
```

只删除本组件服务和专属规则；保留私有配置、密钥和程序。不会刷新系统全部防火墙。

## 端口与三种工作方式

监听发现只列候选，不自动纳管。仅管理用户明确启用的本机 INPUT 服务端口，不管理 Docker 转发端口；未选端口继续由系统原有防火墙决定，不修改路由或 NAT。

- 白名单：只允许家庭动态授权、静态来源或该规则明确允许的来源；授权撤回后已有入站连接也受限。
- 标准（默认）：对未知来源按来源 IP、目的端口和协议限制新连接速率及并发连接；家庭或静态来源的豁免取决于该规则的来源模式，可信认证业务按既有策略处理。选择“所有来源”仍会执行标准限制；正常的大流量不等于滥用。
- 观察：记录所选代理端口的事件，不拦截这些端口。单独开启的 SSH 托管仍按其自身配置工作。

直接 HTTPS 配对时，在 LuCI 选择直接 HTTPS 控制，填写 Agent 根地址、`device_id`，并将 `direct_token` 填入“设备密钥”。两种控制链路均须绕过代理，并由用户确认直连分流；插件不自动调整分流。Agent 使用请求的实际来源；动态授权默认900秒、同步300秒，停止同步后内核按时过期。默认管理/授权配置采用 IPv4；可选 IPv6 行为依配置和链路另行验证，不据此声明 IPv6 云端控制链路已验收。静态规则不受动态租期影响。

可选远端健康条件默认关闭。报告缺失、过期或服务异常时不发放本地联网许可；恢复还须通过原有 SOCKS 外网核验。服务监听存在不能替代真实业务请求。

### 面板与订阅端口

面板与订阅端口仍遵循“只管理已选端口”的边界：未选中的独立端口不由本组件过滤；选中面板端口，或面板通过已选中的同一个 IP、协议、端口反向代理时，也会被相应规则限制，不能按 URL 路径或 SNI 区分。

## SSH 托管与应急访问

SSH 默认不纳管。启用前必须明确确认，且通过真实 SSH 服务监听、已授权管理连接、当前家庭地址和两路新鲜认证心跳检查。不会停止 SSH 服务或改变 SSH 认证方式。

只有控制心跳和独立代理路径心跳都连续失联，才在配置时间（默认60秒）后进入应急窗口。默认临时向公网解除本组件的 SSH 限制，也可选预设管理地址与最后认证家庭地址。新配置的公网应急时长默认为 `0`：保持开放，直到家庭授权恢复；也可设置 `30`–`3600` 秒，到期后恢复限制。旧配置的显式时长保留，升级后如需持续开放，请将其改为 `0`。已有管理连接保留。Agent 暂停时内核仍会在等待时间后放行；同一次系统启动中的进程重启不会无限推迟失联计时。

警告：限时结束、家庭 IP 已变化且无其他可用管理来源时，可能无法新建 SSH 登录。持续开放会延长 SSH 公网暴露时间，SSH 身份验证和系统防火墙仍然生效。

公网应急不能覆盖系统防火墙或上游安全组的拒绝规则。正常恢复需要认证控制恢复并重新确认家庭授权，单独状态查询或代理心跳不能撤回应急。

## 固定远程维护

LuCI 可请求重启 VPS 或重启 Xray 内核，路由器与 Agent 都须分别允许对应动作。配置 `maintenance` 的 `adapter`、`unit`、`service` 和 `verify_seconds`。systemd 适配器只管理允许的 Xray 单元；3x-ui 适配器使用经核对版本的 USR1 机制，必须显式确认该版本支持，不重启面板。

操作 ID 持久化去重，不接受任意命令；执行中断或结果不确定时不自动重做。内核重启需进程代际改变且恢复健康，整机重启需 boot ID 改变且恢复健康。提交维护前本地先进入保护，待真实恢复检查后进入敏感观察。敏感观察正常时联网，期间失败仍进入原有阻断等待。

## REALITY 与日志数据

`reality.config_path` 用于只读核对入站、目标与 SNI；`probe_enabled` 允许按预算执行 TLS 目标检查，不探测任意来源。不会输出私钥或修改 Xray 配置。

`access_log` 仅在入站标签及认证字段可对应时确认已认证来源，不能把普通 SNI 当作身份。对已确认回落连接的带宽限制需要由可信本机程序提供新鲜、私有的 `telemetry_file` JSONL，按来源地址、来源端口、服务端口及协议精确匹配。原生 access log 不能可靠识别所有回落连接；没有该数据源时显示不可用，不猜测、不扩大限制。非 root 日志可通过 `log_uid` 指定可信写入者。

事件、日志游标、内核跟踪集合和 API 请求均有容量上限。心跳运行状态写入 RAM；操作去重记录持久保存。

## Cloudflare 配套

[Worker 配套](CLOUDFLARE-WORKER.md)提供设备认证、来源地址观察、签名授权及控制转发。VPS 上运行 `cloudflared`，Worker 通过 VPC Service 绑定连接 Agent。`DEVICE_TOKEN` 与 `AGENT_SECRET` 分别用于两段认证。

仓库提供 Worker 项目与密钥模板，可通过 Wrangler 部署；Agent、Tunnel 和 VPC Service 仍须分别安装或创建。Worker 部署不等于整套 Pro 已可用，完成配置后应检查认证、家庭授权、控制入口和独立代理路径。

## 测试与兼容

已进行多系统兼容、安装、冷启动、3x-ui / Xray 对接、选定端口策略、认证 API 和 Cloudflare 联调测试。支持条件和已知限制见[兼容范围](COMPATIBILITY.md)。

覆盖安装期间由安装钩子保留已有保护；异常中断后应检查实际规则和服务状态。

官方机制参考：

- https://xtls.github.io/en/config/transports/reality.html
- https://github.com/MHSanaei/3x-ui/tree/v3.11.0
- https://developers.cloudflare.com/workers-vpc/get-started/
- https://developers.cloudflare.com/workers/platform/deploy-buttons/
