# 源码、构建与验证

普通版的配方版本为 `0.3.0-21`，Pro 为 `0.3.1-5`。本页介绍源码目录、IPK / APK 构建和开发测试。每次构建后应使用对应产物的 SHA256 校验值。

## 目录

| 路径 | 内容 |
| --- | --- |
| `package/root/` | 普通版安装文件 |
| `package/pro/root/` | Pro 安装文件 |
| `package/Makefile` | 两个 OpenWrt 包的元数据、安装/卸载钩子 |
| `package/i18n/` | 五种语言的消息源、PO、生成摘要 |
| `companion/vps/` | Linux Agent、示例配置和受限安装脚本 |
| `companion/worker/` | Worker 模板、固定依赖锁文件和测试 |
| `tests/` | 单元、前端和需要专门环境的原生/网络回归 |
| `LICENSES/` | 许可原文与上游声明副本 |

普通版和 Pro 使用独立构建入口；Linux Agent 与 Worker 位于 `companion/`。

## 独立构建 IPK

在 Linux 构建目录准备 Python 3。源码包含已生成翻译，消息源未变时无需下载 LuCI 或运行翻译工具：

```sh
# 只构建普通版
python3 -B tools/build_ipk.py --only standard
# 只构建 Pro
python3 -B tools/build_ipk.py --only pro
# 同时构建两个包
python3 -B tools/build_ipk.py
```

按需要选择上述一条命令。无参数时构建普通版与 Pro；`--only standard` 只输出普通版，`--only pro` 只输出 Pro，并检查与基础包的文件所有权冲突。输出位于 `dist/`，包含安装包、`SHA256SUMS` 和文件清单。构建只生成文件，不执行安装钩子，也不连接设备。

修改翻译时，先从匹配的官方 LuCI 源码自行准备 `po2lmo`：

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
# 只重新生成 Pro 词库和专属页面时加 --only pro
```

不得手工修改 LMO 或诊断映射后沿用旧生成摘要。LuCI 工具、SDK、交叉编译器和代理内核不随此源码捆绑。

## OpenWrt SDK

将 package/ 作为一个包目录放入匹配 OpenWrt SDK 的 package/ 目录，按 SDK 标准流程选择并编译 luci-app-proxy-guard 或 luci-app-proxy-guard-pro。依赖来自该目标匹配的软件源/SDK；all 不是任意固件兼容保证。

25.12 的 APK 应使用匹配的官方 SDK 原生生成；`tools/build_ipk.py` 只生成 IPK，不生成 APK。APK 版本写法为 `0.3.0-r21` / `0.3.1-r5`。配方保留 APK 的安装、升级、卸载脚本入口，Pro 最低基础版本约束也随包格式转换。

SDK 配方与 Python 构建器使用相同的两组安装目录，并按包管理器选择对应钩子。tools/test_sdk_staging.py 只比较配方暂存、权限与钩子，不是完整 SDK 工具链编译；必须在带专用测试标记的隔离 VM 中，针对已构建的两个包执行。

许可证和第三方声明保存在安装文件目录，后续构建会一起带入。Pro 的许可文件位于自己的目录，不覆盖普通版文件。

## 基础测试

以下是已有功能测试入口，只能在准备好的专用 Linux/OpenWrt 测试 VM 中运行：

```sh
python3 -B tools/test_standard_pro.py
```

该入口需要 Python 3、Node.js、make 等依赖。部分版本/SDK 暂存契约依赖受控 VM 的 /etc/pgvm-fixture 标记。标记由专门测试镜像提供；不要在开发宿主手工创建标记来绕过隔离限制。

原生 Lua/ucode、安装钩子、真实 LuCI/UCI/RPC、浏览器、网络命名空间、TCP/UDP 数据包和冷启动检查，需要相应 OpenWrt 镜像及测试夹具，不能仅凭上述入口推定全部通过。部分测试驱动需要专用镜像、网络夹具和匹配的工作目录；仓库不包含虚拟机磁盘或实际部署凭据，运行前应按脚本要求准备环境。

LMO 与真实 LuCI gettext 检查需要从匹配官方源码准备 cbi.js，通过 `PG_LUCI_CBI` 指定；本仓库不捆绑该上游文件。测试同时包含纯逻辑模拟与真实环境集成，两者范围应分别记录。

## Worker

在独立 Linux 开发目录按锁文件安装工具，云端测试使用受控测试资源：

```sh
cd companion/worker
npm ci
npm test
```

npm test 不等于真实 Cloudflare/VPC/Tunnel 通过。部署命令、密钥及绑定准备见[Worker 说明](CLOUDFLARE-WORKER.md)。部署前应单独核对目标账户的绑定、凭据和连接状态。

## 测试范围

项目已进行逻辑、安装、界面、故障恢复、IPv4/IPv6、冷启动、多系统兼容和 Cloudflare 联调测试。修改相关功能后，应执行对应检查。测试范围与支持条件见[兼容说明](COMPATIBILITY.md)。
