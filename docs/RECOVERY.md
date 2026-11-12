# 故障救援

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

适用于普通版 `0.3.0-21` 与 Pro `0.3.1-5`。先区分**路由器上的本地保护**和 **VPS 上的远端策略**；停用一端不会自动撤销另一端。

本页的路由器停用与确认超时步骤已在 OpenWrt 24.10.8 隔离 VM 验证，VPS 卸载路径在 Ubuntu、Alpine 隔离 VM 及此前四发行版生命周期测试中验证。其他固件、损坏的文件系统和厂商恢复模式不能据此推定适用。测试范围见[矩阵](TEST-MATRIX.md)。

## 1. 先保留管理通路

- 保留可用的 SSH 会话、本地串口、虚拟机控制台或 VPS 服务商控制台。
- 如果所有网络管理入口都不可达，先用独立控制台。路由器的 failsafe/恢复方式依固件与硬件而异，应按对应固件说明操作；不要远程反复重启或直接恢复出厂设置。
- 停用保护会撤销本插件的防护，受保护客户端可能恢复直连。必要时先断开这些客户端的上网路径，再救援。
- 不要运行 `nft flush ruleset`、`iptables -F`，也不要删除锁文件或手工清空待确认事务。这些操作可能影响管理访问、其他服务或并发恢复。

## 2. LuCI 不可用，但路由器 SSH／控制台可用

以 root 执行只读检查：

```sh
/usr/libexec/proxy-guard status
ubus list proxy_guard
nft list tables
logread -e proxy-guard
```

`ubus list` 没有对象、LuCI 页面无法加载和代理故障是不同问题。先保留报错；不要通过给普通用户扩大 ACL 来“修复”页面。插件正常停止后也可能保留 nftables 阻断，`/etc/init.d/proxy-guard stop` **不是解除保护的命令**。

日志与配置可能包含敏感地址和凭据，只在本地保存；公开反馈前脱敏。RAM 日志通常不会跨重启保留。

### 明确关闭普通版保护

此步骤要求 UCI 配置仍能正常解析，已具备独立管理通路，并接受客户端可能恢复直连。

先备份：

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery
```

确认备份成功后执行：

```sh
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart
```

这里调用配置事务入口，将“明确关闭”登记为已确认配置；它也可以覆盖尚未确认的试运行，防止后台观察器把旧配置重新应用。随后启动／重启服务以处理关闭状态。仅改 UCI 文件或只 reload 一个已经停止的服务，不能替代此过程。

再核对：

```sh
uci -q get proxy_guard.main.enabled
/usr/libexec/proxy-guard status
nft list tables
```

预期：开关为 `0`，状态为 `disabled`、执行状态为 `off`，普通版专属的 `inet proxy_guard` 表已移除；系统的 `fw4` 和其他插件规则仍在。实际联网还受原系统路由、防火墙与代理配置影响。不要仅以命令退出码或页面文字判断已经恢复。

如果配置无法解析，先从自己保存的、可信且匹配版本的备份恢复 `/etc/config/proxy_guard`，再执行上述“明确关闭”流程。不要用别人的配置或手工拼接字段覆盖现场。若程序／依赖已损坏，保留控制台并修复对应包；本页不提供清空全机防火墙的替代方案。

## 3. 配置确认超时

自检阶段有自己的超时；自检通过后才进入 **30 秒确认倒计时**。关闭浏览器、断开管理连接或未确认时，由路由器上的独立观察器回退，计时不依赖浏览器继续运行。自检并不等同于真实拓扑验收。

重新连接后查看状态与原配置，确认回退完成，再修正草稿。不要把“配置已提交”当作已确认，也不要删除 `pending.json` 来绕过确认。若观察器、存储或运行状态也异常，自动回退可能无法完成；从控制台执行上一节的明确关闭流程并核验实际规则。

## 4. 插件进程异常，阻断仍存在

保护规则由内核执行，进程退出不会自动删除规则；已有放行许可也会到期。这是故障时保持保护的行为，不表示页面读到的最后一次成功检测仍然有效。

保持保护时，先保存日志并检查磁盘、依赖、UCI 与接口，再修复和重启插件；需要临时解除时，使用第 2 节的明确关闭流程。不要同时启动多个手动检测进程、杀光 Lua/ucode 进程或强删锁文件。确认恢复后，先在一台受保护客户端上验证，再重新启用并完成确认。

## 5. Pro 失联与 VPS 遗留规则

本地停用 Pro、关闭浏览器、停止同步或停止 Agent，**不等于远端专属策略已经删除**：

- 动态家庭 IP 租约不再续期后会过期；静态白名单及选定端口规则仍可能存在。
- SSH 应急需要事先启用并确认，且两路认证心跳满足失联条件。应急只放宽本组件限制，不绕过 SSH 认证、系统防火墙或服务商安全组。
- 待确认策略可能自动回退；状态未知时先读回，不降低修订号、不重放旧操作 ID。
- 管理入口与代理共用同一端口时也可能受策略影响，优先使用独立控制台。

能够恢复正常控制时，优先通过 Pro 的确认流程撤销不再需要的远端规则，检查 VPS 实际状态后再停用同步。

### 无法通过 LuCI 撤销：从 VPS 控制台移除组件策略

先停用路由器端 Pro 的自动同步，并保持其停用，避免链路恢复后再次下发。保留 VPS 控制台和原系统防火墙。备份实际 `/etc/proxy-guard-access/agent.json` 及该实例使用的密钥、证书和持久状态；备份含秘密，不能公开上传。

进入**匹配安装版本的可信源码** `companion/vps` 目录，按实际发行版选择一组命令。

Ubuntu / Debian / Rocky Linux：

```sh
sudo sh ./uninstall.sh --remove
sudo systemctl status proxy-guard-access proxy-guard-access-policy --no-pager
sudo nft list tables
```

Alpine Linux，以 root 执行：

```sh
sh ./uninstall.sh --remove
rc-service proxy-guard-access status
rc-service proxy-guard-access-policy status
nft list tables
```

卸载后的服务查询可能返回“找不到服务”或非零状态，这是核对步骤；卸载命令自身若失败，应保留错误并停止后续操作。卸载器只清理本组件拥有的服务、启动依赖和专属规则，保留配置、密钥和程序，不修改 NAT/FORWARD 或清空其他规则。核对本组件规则已移除、其他规则仍在，再测试管理与业务端口。

配置可能自定义专属表名，应结合实际配置核对，不能只搜索默认的 `pg_vps_access`。如果配置损坏导致卸载器无法识别归属，不应猜测表名批量删除。

重新安装可能从保留的配置与持久状态恢复原策略。重装前检查它们是否仍符合需求，重新核对控制、动态授权、端口模式和 SSH 设置；不要复制其他实例的状态或把旧策略修订号强行改小。

## 6. 恢复后的验收

先用一台受保护客户端检查 LAN、DNS、管理、IPv4/IPv6、新建与已有连接，以及代理故障和恢复。验收开机保护时，保留独立管理通路后，重启**运行 Proxy Guard 的路由器**再观察；重启客户端不能完成此项验收。

[安装与使用](USAGE.md) · [Linux Agent 安装](LINUX-AGENT-INSTALL.md) · [控制链路与故障行为](PRO-COMPANION.md) · [安全反馈](SECURITY.md)
