# 许可范围与第三方材料

自有代码和原创文档采用根目录[MIT 许可证](LICENSE)。普通版、Pro 与配套自有代码使用相同授权政策。第三方材料继续保留各自的作者、许可和适用分发条件，不将全部文件或整个运行环境概称为纯 MIT。

## 许可文件

[第三方声明](THIRD_PARTY_NOTICES.md)记录材料、运行依赖与开发工具的使用方式。[组件清单](THIRD_PARTY_COMPONENTS.json)和 LICENSES/SOURCES.json 记录来源、版本/修订及许可副本校验值。许可原文在 LICENSES/ 中。

提供通用许可原文不替代具体作者、NOTICE、逐文件声明或适用的对应源码要求。项目主许可也不改变上游材料的授权。

## UCI 与系统依赖

插件依赖固件提供的 Lua、ucode、LuCI、UCI、rpcd、firewall4、curl 等，没有把这些系统库/解释器打进应用 IPK。

已核对 UCI 修订 16ff0badbde7e17ec3bd1f827ffe45922956cf86：libuci.c 文件头标 LGPL v2.1，lua/uci.c 标 GPL v2；缓存包元数据统一写 LGPL-2.1，与逐文件声明存在差异。Lua 后端会直接加载该 Lua 绑定；前端 JavaScript UCI 模块和 ucode 的 UCI 模块是不同组件。

本项目保留这一事实记录，不擅自改写上游授权或添加链接例外。自有 MIT 文件可保留其许可；若某种分发构成受 GPL 约束的组合，仍须遵守适用的组合与源码要求。组合的适用条件取决于实际材料和结合方式。

## 日志兼容材料

日志识别包含从固定上游修订提取的消息和译文。当前固定消息表包括 PassWall 家族 55、OpenClash 15、Nikki 11、HomeProxy 4 条；不包含动态匹配模式。

- PassWall/PassWall2：保留对应 GPL v3 来源声明。
- OpenClash：MIT，保留原作者声明。
- Nikki：配方标 GPL3.0+，保留 GPL-3.0-or-later。
- HomeProxy：来源 init 脚本明确标 GPL-2.0-only。

解析和控制逻辑属于本项目；受到版权保护的上游衍生部分保留上游条款。短功能消息是否受到版权保护、译文或编排是否具备独创性，需要具体判断；这里不一律宣称全部消息都受保护，也不把整份材料统一重授权为 MIT。

日志监听在独立 ucode 实例中运行，通过 JSON 状态文件与 Lua 后端交互。分发时应结合实际包含的文件、运行依赖和结合方式履行适用许可要求。

## 配套组件

VPS Agent 使用 Python 标准库和外部 Linux 工具。Worker 使用托管平台 API，开发工具依赖单独列在 companion/worker/THIRD_PARTY_DEPENDENCIES.json；91 个锁文件条目包括可选平台和开发依赖，不等于 91 个运行时捆绑组件。Cloudflare 托管服务受其服务条款约束。

## 发布与再分发

发布自有源码时保留 MIT、版权及适用第三方说明。复制或修改上游材料时，保留原声明和修改记录，并履行相关许可要求。若再捆绑系统库、固件、代理内核、node_modules 或其他外部二进制，需要按实际内容另行核查，不能仅复用应用脚本包的清单。

本页解释许可范围，不构成法律认证，也不代替功能与兼容检查。公开仓库能够显示主许可证，也不代表平台替发布者核验了所有第三方组合。

原文参考：[GNU 许可 FAQ](https://www.gnu.org/licenses/gpl-faq.en.html)、[GNU 许可兼容说明](https://www.gnu.org/licenses/license-compatibility.en.html)、[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)。
