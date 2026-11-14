# ビルドと検証

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

対象ファームウェアに合う SDK で Proxy Guard をビルドします。opkg を使用する環境では、独立した IPK ビルドツールも使用できます。

翻訳を再生成する場合は LuCI の po2lmo を使います。コンパイル済みの翻訳も同梱しているため、IPK はそのままビルドできます。

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
python3 -B tools/build_ipk.py
```

APK を作る場合は、`package` ディレクトリを対応する OpenWrt SDK の `package/proxy-guard` にコピーします。依存パッケージのフィードを準備し、SDK のルートで `make menuconfig` を実行します。「LuCI → 3. Applications」で `luci-app-proxy-guard` が選択済みか確認します。未選択の場合は `<M>` を選び、設定を保存してからビルドします。

```sh
make package/proxy-guard/compile V=s
find bin/packages -name 'luci-app-proxy-guard-*.apk'
```

LuCI、firewall4、nftables が必要です。OpenWrt 24 は IPK、25.12 は APK を使います。iStoreOS と ImmortalWrt は各ファームウェアのパッケージ管理とカーネル依存関係に合わせてください。

[テストマトリクス](TEST-MATRIX.ja.md)
