# ساخت و راستی‌آزمایی

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

برای ساخت Proxy Guard از SDK متناظر با میان‌افزار مقصد استفاده کنید. برای سامانه‌های opkg می‌توان IPK را با ابزار مستقل هم ساخت.

برای ساخت دوبارهٔ ترجمه‌ها از po2lmo متعلق به LuCI استفاده کنید. فهرست‌های کامپایل‌شده همراه کد هستند و IPK را می‌توان مستقیم ساخت.

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
python3 -B tools/build_ipk.py
```

برای ساخت APK، پوشهٔ package را در SDK هم‌نسخهٔ OpenWrt به package/proxy-guard کپی کنید. خوراک وابستگی‌ها را آماده و از ریشهٔ SDK افزونه را بسازید.

```sh
make package/proxy-guard/compile V=s
```

LuCI، firewall4 و nftables لازم‌اند. OpenWrt 24 از IPK و OpenWrt 25.12 از APK استفاده می‌کند. در iStoreOS و ImmortalWrt، مدیر بسته و وابستگی‌های کرنل همان میان‌افزار را بررسی کنید.

[جدول آزمون‌ها](TEST-MATRIX.fa.md)
