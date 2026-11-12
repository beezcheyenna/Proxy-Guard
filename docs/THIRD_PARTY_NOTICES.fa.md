# اطلاعیه‌های طرف ثالث

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

<div dir="rtl" lang="fa">

تاریخ ثبت 2026-11-08. دامنه شامل کد عمومی استاندارد، Pro، Agent و Worker است. شرایط را از اعلامیهٔ اصلی بالادست بخوانید.

## کد اصیل

Copyright (c) 2026 Proxy Guard contributors.

کد و مستندات اصیل زیر [مجوز MIT](../LICENSE) ریشه عرضه می‌شوند. استاندارد و Pro سیاست یکسان دارند. رشته، وصله، کتابخانه، مفسر، ابزار، هسته و فریم‌ور بالادست شرایط خود را حفظ می‌کنند.

## پیام‌های گزارش بالادست

`package/root/usr/lib/proxy-guard/passwall-log.uc` و نمونه‌های بازگشتی، شناسه و ترجمهٔ بازبینی‌های زیر را دارند. تجزیه و کنترل اصیل‌اند. مواد مشتق مشمول حق نشر شرایط بالادست را حفظ می‌کنند. شناسهٔ کوتاه و ترکیب توزیع را بر اساس مواد واقعی بسنجید.

| پروژه | بازبینی | شرایط بالادست | کاربرد |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | GNU GPL v3 طبق منبع | چرخهٔ اجرا و آزمون |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | GNU GPL v3 طبق منبع | چرخهٔ اجرا به انگلیسی، چینی، روسی و فارسی و آزمون |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT و اطلاعیهٔ فایل | شناسهٔ چرخهٔ اجرا |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | GPL-3.0-or-later در دستور بسته | شناسهٔ چرخهٔ اجرا |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | GPL-2.0-only در init | شناسهٔ چرخهٔ اجرا |

جمع بایگانی و موارد PassWall/PassWall2 در `tests/passwall_log_corpus.json` هستند. URL، نسخهٔ مجوز و جمع پنج پروژه در [فهرست](THIRD_PARTY_COMPONENTS.json) و [اصل منابع](../LICENSES/README.fa.md) آمده‌اند. IPK/APK پیام منتخب و نگاشت رویداد را دارند.

حق نشر زیر از دستور بستهٔ ثابت است. دیگر حقوق و اعلامیه‌ها در منبع باقی می‌مانند.

PassWall: Copyright (C) 2018-2020 L-WRT Team, Copyright (C) 2021-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization. PassWall2: Copyright (C) 2022-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization.

- https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52
- https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945
- https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd
- https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8
- https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec

## وابستگی‌های اجرای OpenWrt

فریم‌ور و مخزن مقصد این مؤلفه‌ها را فراهم می‌کنند. شواهد مجوز به نسخه و فایل بررسی‌شده مربوط است.

| مؤلفه | کاربرد | شاهد مجوز |
| --- | --- | --- |
| LuCI, luci-lib-jsonc, luci-lib-nixio | رابط، JSON، POSIX و سوکت | Apache-2.0 / NOTICE · دستور بررسی‌شدهٔ 24.10 |
| Lua | مفسر | MIT · نسخهٔ نصب‌شده |
| ucode, fs/uci | مفسر، قفل و تنظیم | ISC · شرایط جداگانهٔ کتابخانه‌های پیوندی |
| libuci | کتابخانهٔ UCI | LGPL v2.1 (`libuci.c`) · سرآیند کتابخانه |
| libuci-lua | بارگیری در Lua با `require('uci')` | GPL v2 (`lua/uci.c`) · سرآیند اتصال Lua |
| rpcd | RPC و ACL | ISC · دستور بررسی‌شدهٔ 24.10 |
| ubus | گذرگاه سیستم | LGPL-2.1 · دستور و اعلامیهٔ فایل |
| procd, netifd, BusyBox | نگهبان، رخداد رابط و ابزار پوسته | GPL-2.0 · دستور و اعلامیهٔ فایل |
| firewall4 | بارگذاری و هماهنگی قانون | ISC · دستور بررسی‌شده |
| nftables / Linux Netfilter | پالایش بسته و رهگیری اتصال | GPL · حفظ اعلامیه در توزیع |
| curl / CA bundle | بررسی SOCKS/HTTPS | curl / CA · شرایط بسته‌های جدا |
| Ruby / YAML (OpenClash) | تجزیهٔ امن تنظیم موجود | نسخهٔ نصب و کتابخانه‌ها |

فرادادهٔ LGPL بستهٔ UCI و سرآیند GPL v2 اتصال Lua جدا هستند. فرمان بیرونی با وارد کردن در فرایند فرق دارد. در توزیع ترکیب، نسخه، شیوهٔ اتصال و استثناهای قابل اعمال را بسنجید.

## Agent Pro و Cloudflare

Agent کتابخانهٔ استاندارد Python و ابزار بیرونی لینوکس را دارد. Python، nftables، iproute2، systemd/OpenRC، پروکسی و پنل جدا عرضه می‌شوند. cloudflared برنامهٔ جداگانهٔ Apache-2.0 است. Worker از API میزبانی‌شدهٔ Cloudflare با شرایط سرویس استفاده می‌کند. وابستگی توسعهٔ فایل قفل:

- Wrangler 4.156.0 — MIT OR Apache-2.0
- Miniflare 5.20261023.3-beta — MIT
- workerd 1.20261023.1 — Apache-2.0

<https://github.com/cloudflare/cloudflared/blob/master/LICENSE>

[فهرست قفل](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) ۹۱ مدخل غیرریشه و بستهٔ اختیاری بستر دارد. ابزار، node_modules و cloudflared همراه بستهٔ برنامه نیستند. برای توزیع جدا، اعلامیه و تعهد منبع بسته‌های واقعی را حفظ کنید.

## کلاینت، هسته و پنل

PassWall، PassWall2، OpenClash، Nikki، HomeProxy، Xray، sing-box، Mihomo و 3x-ui جدا نگه‌داری می‌شوند. افزونه تنظیم، گزارش و سرویس را می‌خواند یا مدیریت مجاز را فراخوانی می‌کند. در افزودن منبع یا فایل اجرایی ثالث، اعلامیه و منبع لازم هر مؤلفه را بررسی کنید.

## دامنهٔ مجوز

در بازتوزیع محتوای واقعی و ترکیب را بررسی کنید. اصل اعلامیهٔ هر مؤلفه و فایل اولویت دارد. [دامنهٔ مجوز](LICENSING.fa.md) را ببینید.

</div>
