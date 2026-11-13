# 构建与校验

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

使用目标固件对应的 SDK 构建 Proxy Guard。使用 opkg 的系统也可以用独立工具构建 IPK。

需要重新生成翻译时，使用 LuCI 的 po2lmo。源码已带编译好的语言目录，也可以直接构建 IPK。

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
python3 -B tools/build_ipk.py
```

构建 APK 时，将 package 目录复制到对应 OpenWrt SDK 的 package/proxy-guard。先准备所需依赖的软件源，再从 SDK 根目录构建。

```sh
make package/proxy-guard/compile V=s
```

使用 LuCI、firewall4 和 nftables。OpenWrt 24 使用 IPK，OpenWrt 25.12 使用 APK。iStoreOS 和 ImmortalWrt 按各自固件的包管理器及内核依赖选择。

[测试矩阵](TEST-MATRIX.md)
