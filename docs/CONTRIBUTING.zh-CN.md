# 参与贡献

[English](../CONTRIBUTING.md) · [简体中文](CONTRIBUTING.zh-CN.md) · [日本語](CONTRIBUTING.ja.md) · [Русский](CONTRIBUTING.ru.md) · [فارسی](CONTRIBUTING.fa.md)

欢迎提交可复现的问题、兼容性结果、文档修正和目标明确的拉取请求。

- [报告问题](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=bug_report.yml)
- [反馈兼容性](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=compatibility.yml)
- [建议功能](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=feature_request.yml)
- [反馈文档](https://github.com/beezcheyenna/Proxy-Guard/issues/new?template=documentation.yml)

普通问题可在脱敏后公开反馈。请勿公开未修复的漏洞细节。 [安全问题报告](SECURITY.md)

## 修改行为前

1. 说明触发条件、预期和实际结果。用文档地址和最小脱敏拓扑。
2. 记录固件、内核、架构、包格式、已安装的 Proxy Guard 版本、实际代理内核及转发模式。区分包元数据与正在运行的程序。
3. 使用获授权的隔离环境。管理服务、路由和防火墙的脚本在一次性 VM 内执行。
4. 保持修改聚焦。保留 ACL、证书校验和无关的 NAT/DNS/网络配置。

参见[构建](BUILDING.md)和[测试矩阵](TEST-MATRIX.md)。实机安装与数据路径另行验证。

## 文档与翻译

英文是首页默认语言，随后为简体中文、日语、俄语和波斯语。功能改变时同步更新五种语言的相关页面和链接。更新日志为英文，旧的本地化日志 URL 保留英文内容。保留原始许可证和第三方声明。

在仓库根目录运行以下检查。

```sh
python3 tools/check_docs.py
python3 -m unittest discover -s tools/tests -p 'test_check_docs.py'
```

检查文档完整性、链接语言、锚点、版本和包名。准确性仍需要阅读译文。PR 执行离线检查，主分支与发布事件也核对 GitHub 的最新正式版。先合并版本升级时，发布对应正式版后重新检查。

## 拉取请求与证据

说明问题、改动、验证及剩余限制。兼容结果提供确切版本和日期，区分模拟、隔离 VM 和实际部署，并保留初次失败。提交文档时去掉生成包、私有日志和无关格式修改。保留仓库许可与第三方声明，详见[许可说明](LICENSING.md)。
