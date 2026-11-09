# Linux VPS Agent 安装（Pro 配套）

普通版无需安装本组件。使用 Pro 的远程功能时，需要路由器上的基础包和 Pro 扩展，以及 Linux VPS 上的 Agent。控制链路可选**直接 HTTPS**，或 **Cloudflare Worker 与 Tunnel/VPC**；Cloudflare 并非必需。

IPK 安装到 OpenWrt；Linux 使用本文的 Python Agent 安装器。已测试的发行版与条件见[兼容范围](COMPATIBILITY.md)。需要 Python `3.10+`、nftables、相应内核能力，以及 systemd 或 OpenRC。

## 1. 安装依赖

根据实际发行版选择一组命令。

**Ubuntu / Debian：**

```sh
sudo apt update
sudo apt install -y python3 nftables iproute2 ca-certificates
```

**Rocky Linux：**

```sh
sudo dnf install -y python3 nftables iproute ca-certificates
```

**Alpine Linux，以 root 执行：**

```sh
apk add python3 nftables iproute2 coreutils ca-certificates
```

上述命令安装发行版软件源中的 Python，不会自动保证版本达到 `3.10+`。本项目的 systemd 和 OpenRC 服务均固定使用 `/usr/bin/python3`，安装前应核对：

```sh
/usr/bin/python3 --version
```

该解释器须为 Python `3.10+`；仅在其他路径安装新版 Python，或在终端激活虚拟环境，不会改变服务使用的解释器。若版本不满足要求，先准备符合要求的系统运行环境，再继续安装。

安装器会检查配置和 nftables 内核能力。缺少动态集合、连接数限制等所需功能时，会拒绝安装。内核模块必须与目标系统匹配；安装 nftables 软件包不等于需要启用发行版通用的 `nftables.service`，本组件使用自己的策略服务。

## 2. 解压源码并准备配置

将项目源码归档 `proxy-guard-source.tar.gz` 上传到 VPS，在归档所在目录执行：

```sh
tar -xzf proxy-guard-source.tar.gz
cd proxy-guard/companion/vps
cp agent.example.json agent.json
chmod 600 agent.json
python3 - <<'PY'
from pathlib import Path
import json
import secrets

path = Path('agent.json')
config = json.loads(path.read_text())
config['agent_secret'] = secrets.token_urlsafe(32)
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o600)
PY
```

编辑 `agent.json`，核对以下项目：

| 配置项 | 要求 |
| --- | --- |
| `device_id` | 设备身份，例如 `home`；与路由器及所用 Worker 一致。 |
| `agent_secret` | 独立随机密钥；使用 Worker 时与其 `AGENT_SECRET` 一致，不交给路由器。 |
| `services` | 填实际代理进程名和 TCP/UDP 监听端口，不能直接把示例当作检测结果。 |
| `managed_units` | 填需要建立启动依赖的实际代理服务，格式为 `name.service`。systemd 对应单元名；OpenRC 对应去掉 `.service` 的服务名。不接受 SSH 服务。 |
| `egress.panel_config_path` | 可选的本机可信 Xray JSON 配置路径，不是面板网页地址；外部出口测量默认关闭。 |
| SSH、代理路径心跳、远程维护 | 分别配置并明确启用，安装不会自动开启。 |

Agent 不安装 Xray、3x-ui 或其他代理服务，它只对已经部署的服务执行所配置的检查与管理。3x-ui 是管理面板，实际代理内核是 Xray；其进程名可能与独立 Xray 不同。使用 3x-ui 远程内核重启时，应选对应适配器，并确认目标版本的 USR1 机制；不要直接照抄独立 `xray.service` 设置。

## 3. 选择控制链路

### Cloudflare Worker 与 Tunnel/VPC

Agent 通常保持 `bind=127.0.0.1`、`port=8788`、`public_control=false`，由同机 `cloudflared` 访问回环 API。

按 [Worker 配套说明](../companion/worker/README.md)设置 Tunnel、VPC Service、`VPS_API` 绑定和凭据：

- `AGENT_SECRET` 与 Agent 的 `agent_secret` 相同。
- `DEVICE_TOKEN` 是另一枚独立凭据，不能与 `AGENT_SECRET` 共用。
- `DEVICE_ID` 在 Agent、Worker 和路由器上一致。

在路由器“VPS 访问规则”中选择 Cloudflare 控制链路，填写 Worker HTTPS 地址、设备身份和设备密钥。

### 直接 HTTPS 连接 Agent

无需 Worker 或 Tunnel。设置独立的 `direct_token`，并明确配置 `public_control=true`、监听地址、`tls_cert` 和 `tls_key`；对外控制入口必须使用有效的 HTTPS 证书。

在路由器中选择“直接 HTTPS 连接 Agent”，控制服务地址填写 Agent HTTPS 根地址，“设备密钥”填写 Agent 的 `direct_token`。凭据使用 32–256 个字母、数字、下划线或短横线字符，不能沿用示例占位值。

**两种控制方式都必须绕过代理，并由用户确认直连分流。** 插件不会代改路由或代理分流设置。独立代理路径心跳则经本机 SOCKS 验证代理通路，与控制心跳分开。

<a id="control-and-path"></a>

### 地址、密钥与独立代理路径

| 用途 | 路由器侧填写 | 对应的远端设置 |
| --- | --- | --- |
| Cloudflare 控制 | Worker HTTPS 根地址、设备身份、设备密钥 | `DEVICE_ID`、`DEVICE_TOKEN`；Worker 的 `AGENT_SECRET` 另与 Agent 的 `agent_secret` 配对，不填到路由器。 |
| 直接 HTTPS 控制 | Agent HTTPS 根地址、设备身份、设备密钥 | Agent 的 `device_id`、`direct_token`、公网监听及 TLS 配置。 |
| 独立代理路径心跳 | 开启路径监视，填写 Agent HTTPS 根地址和独立路径密钥 | Agent 的 `path_token`；请求经 SOCKS，后端使用 `/v1/direct/path-heartbeat`。 |

根地址不要填写完整的 `/v1/...` 接口路径，插件会追加路径。不同用途的密钥应分别生成和保存，不能把 Worker 的 `AGENT_SECRET` 当作设备密钥或路径密钥。启用 SSH 托管前，需要控制和独立代理路径两路均已通过认证。

- **直接 HTTPS 控制**：Agent 必须直接看到家庭连接的实际公网来源地址，当前不从转发头恢复来源。不要把这一控制入口简单放到终止连接的反向代理后，否则可能只观察到回环/中间地址，无法正确完成家庭地址授权。同一 Agent HTTPS 根地址可用于路径心跳，但控制请求走直连，路径心跳走 SOCKS，并使用独立路径密钥。
- **Cloudflare 控制**：默认回环 HTTP Agent 只能由同机 Tunnel/VPC 访问，不能直接作为外部 SOCKS 路径心跳入口。需要另行准备可由代理访问的有效 HTTPS 入口。例如可由部署者配置 HTTPS 反向代理，仅把 `/v1/direct/path-heartbeat` 转发到同机回环 Agent，并保留 Bearer 头；其他 Agent API 不应因此公开。此方式只转发路径心跳，不提供直接控制的来源地址观察。
- 若将 Agent 监听本身改为公网 HTTPS，须同时配置 `public_control`、`direct_token` 和证书；Tunnel/VPC 的目标协议和端口也要相应核对，不能继续把 HTTPS 监听当成 HTTP 使用。Agent 不会自动申请、续期证书或替你配置反向代理。

控制和心跳入口应独立规划，避免把它们纳入“只有同步成功后才允许访问”的端口规则，形成无法重新认证的循环。普通控制地址的实际直连分流，以及路径心跳是否真的经过本机 SOCKS，均需部署者验证。

## 4. 安装与检查

### Ubuntu / Debian / Rocky Linux

在 `companion/vps` 目录执行：

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
sudo python3 agent.py --config "$PWD/agent.json" --check-kernel
sudo sh ./install.sh --install "$PWD/agent.json"

sudo systemctl status proxy-guard-access-policy proxy-guard-access --no-pager
sudo journalctl -u proxy-guard-access -n 50 --no-pager
```

### Alpine Linux，以 root 执行

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
python3 agent.py --config "$PWD/agent.json" --check-kernel
sh ./install.sh --install "$PWD/agent.json"

rc-service proxy-guard-access-policy status
rc-service proxy-guard-access status
```

程序安装到 `/opt/proxy-guard-access`，实际配置位于 `/etc/proxy-guard-access/agent.json`。安装器注册并启动自己的策略服务和 Agent；已有安装会保留原配置。修改另一个示例文件后再次安装，不会覆盖实际配置，应修改实际配置并通过安装器重新核验、重启。

随后在 LuCI 保存并应用，核对同步、授权和服务状态。监听发现只提供候选；先选择确实需要管理的端口，未选端口仍由原系统防火墙决定。

## 5. SSH 应急访问与面板端口

SSH 托管默认关闭。明确启用并通过管理会话及双通道检查后，只有控制心跳和独立代理路径心跳都连续失联，才在配置的等待时间后触发应急访问，默认等待 **60 秒**。

新配置默认允许公网应急访问；开放时长 `0` 表示持续到家庭授权恢复，也可选择限定管理来源或设置 `30`–`3600` 秒的时限。升级保留已有显式时长，不会自动把旧的 `600` 改为 `0`。

> **SSH 访问提示：** 持续开放会增加公网暴露时间；限时到期且家庭 IP 已变化、没有其他允许来源时，可能无法新建 SSH 登录。SSH 身份验证、系统防火墙及上游安全组仍然生效。

未选中的独立 3x-ui 面板、API、订阅端口不由插件过滤。选中这些端口，或它们与代理共用同一 IP、协议和端口时，也会受相应规则影响。配置前应核对实际监听端口，避免把管理入口误纳入业务端口策略。

## 6. 端口模式与原始配置

每条规则可继承默认模式，或单独选择仅白名单、标准防滥用、仅观察，并配置来源、阈值和时长。使用新增远端能力时，需要匹配的 Agent；通过 Cloudflare 管理时，也需要匹配的 Worker。控制端会先检查能力，不支持时拒绝应用。

OpenWrt 的两个原始 UCI 编辑器分别编辑本地代理保护和 VPS 访问规则，不编辑 Agent 的本机配置。监听、证书和维护授权仍通过 Agent 配置文件设置。

仓库中的 Wrangler 项目用于部署 Worker；Agent、Tunnel 和 VPC Service 仍须分别安装或创建。当前未提供已配置的一键部署入口，具体步骤见 [Worker 配套说明](../companion/worker/README.md)。

## 7. 升级与配置备份

Agent 升级与路由器 IPK 安装是两件事。使用兼容的新版源码，在保留 SSH 或控制台的情况下重新运行安装器；它会检查并保留现有 `/etc/proxy-guard-access/agent.json`，而不是用新解压的示例覆盖它。只改源码目录中的 `agent.json` 不会更新实际运行配置。

升级前，安全备份实际配置、TLS 证书/私钥和保留的兼容源码；如需灾难恢复，还应保留该实例配置所指定的持久状态与操作记录。备份含凭据，不应放入公开问题附件。不要把另一台 VPS 的状态或已用操作 ID 复制过来，也不要降低策略修订号来强行恢复同步。

在新源码的 `companion/vps` 目录内执行：

```sh
# Ubuntu / Debian / Rocky Linux
sudo sh ./install.sh --install /etc/proxy-guard-access/agent.json

# Alpine Linux，以 root 执行
sh ./install.sh --install /etc/proxy-guard-access/agent.json
```

按实际发行版只选择其中一行。安装器会校验实际配置、核验内核、更新程序与服务并重启 Agent；不应把只复制文件当作已更新运行进程。完成后重复安装后的状态检查，核对路由器报告的远端能力、认证、策略版本和实际选定端口。需要回退程序时也要核对旧程序能否读取当前配置与状态，不能承诺任意跨版本自动降级。

## 8. 端到端核对与排错

1. **本机服务**：Agent 与 policy 服务正常，实际代理进程和所配置 TCP/UDP 端口就绪；端口监听不代表代理业务一定成功。
2. **控制链路**：证书、设备身份、独立凭据和直连分流正确。Cloudflare 部署还须核对固定 VPC Service 绑定与 Tunnel 连接。
3. **动态授权**：LuCI 中看到新鲜的认证和家庭地址授权；仅查询状态不会续期。家庭地址变化后须重新观察并同步，不能把旧地址永久当作当前地址。
4. **所选端口**：先用一条可控规则试运行并确认，验证允许来源、受限来源和未选端口。面板、订阅、SSH 与 Docker 转发各自核对。
5. **应急与维护**：SSH 托管、独立路径心跳和维护动作均先单独验收，再在双端授权后使用。接受维护请求并不等于内核或 VPS 已恢复。
6. **故障恢复**：验证控制失联、代理失联、策略未确认到期和重启恢复；保留独立控制台，确认实际规则与页面结果一致。

| 现象 | 应检查的项目 |
| --- | --- |
| 安装前置检查失败 | Python 版本、运行中的 init 系统、nftables 表达式与目标内核模块，先解决依赖与能力错误。 |
| HTTPS 或认证失败 | 证书链/有效期、路由器与 VPS 的系统时间、实际监听、设备身份和对应链路密钥；不应禁用证书验证来绕过错误。 |
| Worker 可访问但 Agent 失联 | Tunnel 连接、VPC Service 固定目标、绑定 ID 和 Agent 回环监听；网页能打开不代表后端已连通。 |
| 有控制心跳但代理路径心跳失败 | 独立 HTTPS 入口、路径密钥、本机 SOCKS 和实际代理出口；两路心跳不能互相冒充。 |
| 面板或订阅也受限 | 是否把它们的独立端口纳入规则，或与代理共用相同 IP、协议及端口。 |
| 应急已开放仍不能 SSH | SSH 服务、认证、系统防火墙和上游安全组仍须允许；本组件只撤销自己的相应限制。 |
| 配置已改但状态不变 | 是否修改实际配置、重新通过检查并重启 Agent，是否误改了示例文件，是否有待确认或未知结果事务。 |

完成配置后应核对实际规则与流量。更多边界见[兼容范围](COMPATIBILITY.md)，共享入口和心跳行为见[Pro 配套说明](../companion/README.md)。

## 9. 卸载

在保留的源码 `companion/vps` 目录中执行：

```sh
# systemd 系统
sudo sh ./uninstall.sh --remove

# Alpine Linux，以 root 执行
sh ./uninstall.sh --remove
```

卸载只移除本组件的服务和专属规则，保留配置、密钥和程序；不会刷新系统全部防火墙。详见 [Pro 配套说明](../companion/README.md)。
