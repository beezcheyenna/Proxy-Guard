# Сборка и проверка

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

Для сборки Proxy Guard используйте SDK целевой прошивки. Для систем с opkg доступна отдельная утилита сборки IPK.

Для пересборки переводов используйте po2lmo из LuCI. Готовые каталоги включены в исходники, поэтому IPK можно собрать сразу.

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
python3 -B tools/build_ipk.py
```

Для сборки APK скопируйте каталог package в package/proxy-guard подходящего OpenWrt SDK. Подготовьте фиды с зависимостями и выполните сборку из корня SDK.

```sh
make package/proxy-guard/compile V=s
```

Требуются LuCI, firewall4 и nftables. Для OpenWrt 24 используется IPK, для OpenWrt 25.12 — APK. Для iStoreOS и ImmortalWrt сверяйте пакетный менеджер и зависимости ядра своей прошивки.

[Матрица тестирования](TEST-MATRIX.ru.md)
