# Sing-tun system 栈 IPv6 UDP 兼容修复

此补丁属于上游 GPL-3.0-or-later 组件，保留上游许可及完整 GPL v3 文本；Proxy Guard 自有代码继续使用 MIT。补丁不会随 LuCI IPK 自动安装或替换代理内核。

已定位到 Sing-box v1.12.25 所用 sing-tun v0.7.13 的 `System.processIPv6()`：UDP 分支处理数据后仍返回 `writeBack=true`，使原始请求再次注入 TUN。在受影响的 HomeProxy TUN/system 配置中，该重复包被原有防火墙拒绝，客户端收到连接拒绝。补丁让该分支与 IPv4 UDP 一样返回 `writeBack=false`；真正代理回包仍由 UDP packet writer 处理。

manifest.json 固定原文件、补丁与修正文件的 SHA256。必须核对原始版本后再应用；不要直接修改正在使用的 Go module cache。复制模块到构建目录，在副本中执行 `patch -p1 < 0001-system-ipv6-udp-no-writeback.patch`，再由 Sing-box 源码目录通过 `go mod edit -replace=github.com/sagernet/sing-tun=/absolute/path/to/patched-copy` 指向该副本。

离线验证构建使用 Go 1.23.12、Sing-box v1.12.25、CGO_ENABLED=0、GOOS=linux、GOARCH=amd64，保留上游默认功能标签：with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale。`go build -trimpath -buildvcs=false -tags <上述标签> ./cmd/sing-box`。有网络的开发宿主只准备官方源码与校验过的模块缓存；实际编译和测试在断网 VM 内进行。

源码版本、补丁和构建校验值见 `manifest.json`。此补丁只针对上述版本和问题，不能作为原版内核或其他 TUN 栈兼容性的保证。

补丁已进行 IPv6 UDP 回显、故障阻断与恢复、客户端停止与重启测试。使用前仍需核对所选固件、CPU 架构与代理核心；插件不会自动安装该补丁或替换内核。
