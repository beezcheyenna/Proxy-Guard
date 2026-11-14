# Build and verify

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

Build Proxy Guard with the SDK for your target firmware, or use the standalone IPK builder for an opkg system.

To regenerate translations, use LuCI’s po2lmo tool. The source includes the compiled catalogs, so the IPK can also be built directly.

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
python3 -B tools/build_ipk.py
```

For an APK, copy the `package` directory into the matching OpenWrt SDK as `package/proxy-guard`. Prepare the feeds for the listed dependencies. From the SDK root, run `make menuconfig` and confirm that `luci-app-proxy-guard` is selected under **LuCI → 3. Applications**. Select `<M>` if it is unset, save the configuration, then build the package.

```sh
make package/proxy-guard/compile V=s
find bin/packages -name 'luci-app-proxy-guard-*.apk'
```

Use firewall4 and nftables with LuCI. OpenWrt 24 uses IPK and OpenWrt 25.12 uses APK. For iStoreOS and ImmortalWrt, match the firmware’s package manager and kernel dependencies.

[Test matrix](TEST-MATRIX.en.md)
