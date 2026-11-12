# Cloudflare Worker برای Pro

[English](CLOUDFLARE-WORKER.en.md) · [简体中文](CLOUDFLARE-WORKER.md) · [日本語](CLOUDFLARE-WORKER.ja.md) · [Русский](CLOUDFLARE-WORKER.ru.md) · [فارسی](CLOUDFLARE-WORKER.fa.md)

<div dir="rtl" lang="fa">

Worker دستگاه را احراز هویت می‌کند، IP عمومی شبکهٔ خانگی را مشاهده می‌کند و سیاست را با پروتکل v3 به Agent می‌فرستد. نسخه‌های سازگار Pro و VPS Agent لازم‌اند. هر Worker یک شناسهٔ دستگاه و یک اتصال ثابت `VPS_API` دارد.

## وابستگی‌ها و آزمون محلی

از Node.js 22 یا جدیدتر استفاده کنید. `package-lock.json` نسخه‌های Wrangler 4.156.0 و Miniflare 5.20261023.3-beta را ثابت نگه می‌دارد. استقرار با Wrangler نصب‌شده انجام می‌شود. پس از تغییر ابزارها یا تاریخ سازگاری در `wrangler.jsonc` (فعلاً `2026-11-01`)، محیط اجرا را دوباره بررسی کنید.

در محیط اختصاصی آزمون لینوکس، به `companion/worker` بروید و اجرا کنید:

```sh
npm ci
npm test
npm run test:persistence
npm run check:bundle
```

`npm ci` بار اول معمولاً وابستگی‌ها را دانلود می‌کند. پس از نصب، آزمون محلی بدون اتصال به Cloudflare انجام می‌شود. استقرار و بررسی ابری به منابع مجاز نیاز دارند.

آزمون واقعی nftables در فضای نام شبکهٔ خصوصی ماشین مجازی یک‌بارمصرف اجرا می‌شود. `test/run_checks.sh` و `test/run_final.sh` به داده‌های آزمون و پوشهٔ کاری متناظر نیاز دارند. آزمون نگهداری عملیات را ثبت می‌کند و سیستم را واقعاً راه‌اندازی مجدد نمی‌کند. `kernel_lease_test.py` بررسی می‌کند که مجوز ۱۲۰ ثانیه‌ای هسته پس از ۱۲۵ ثانیه حذف شود و پس از راه‌اندازی سرد بازنگردد.

## استقرار

[Linux Agent](LINUX-AGENT-INSTALL.fa.md) را جداگانه نصب و بررسی کنید. `cloudflared` را برای Tunnel اختصاصی روی همان VPS اجرا کنید. VPC Service به شنوندهٔ loopback عامل، معمولاً HTTP `127.0.0.1:8788`، اشاره می‌کند. `VPS_API` را به شناسهٔ همین Service متصل کنید.

- `DEVICE_ID` باید با Agent یکی باشد.
- برای دستگاه به Worker از `DEVICE_TOKEN` تصادفی و برای Worker به Agent از `AGENT_SECRET` جداگانه استفاده کنید.
- هر دو رمز باید ۳۲ تا ۲۵۶ حرف، رقم، زیرخط یا خط تیره داشته باشند. مقدار نمونهٔ `REPLACE_` رد می‌شود.
- `.dev.vars.example` کلیدهای لازم را نشان می‌دهد. مقدار واقعی را در محل خصوصی اسرار نگه دارید و `.dev.vars`، `.env` یا فایل رمز را در مخزن ثبت نکنید.
- شناسهٔ Service را در `wrangler.jsonc` ثبت کنید. رمزها را پیشاپیش تنظیم کنید یا برای آزمایش با `npm run deploy -- --secrets-file /path/to/private-secrets.json` بدهید. فیلدهای JSON عبارت‌اند از `DEVICE_TOKEN` و `AGENT_SECRET`. نمونه شناسهٔ فعال ندارد.

میزبان و پورت VPC Service مقصد را تعیین می‌کنند. تغییر میزبان یا پورت در URL درخواست fetch مقصد را عوض نمی‌کند. تنظیم Service و اتصال را در Cloudflare بررسی کنید.

## API و داده‌ها

User-Agent مشخصی مانند `ProxyGuardPro/0.2.0` ارسال کنید. در صورت خطای `1010` از Cloudflare، شناسهٔ کلاینت و سیاست امنیتی حساب را بررسی کنید.

همهٔ مسیرها HTTPS و توکن Bearer دستگاه می‌خواهند. پارامترهای query پذیرفته نمی‌شوند.

| مسیر | رفتار |
| --- | --- |
| `/v1/observe` | IP عمومی مشاهده‌شده در Cloudflare را برمی‌گرداند. منشأ درخواست فرعی Worker و نشانی رزروشده رد می‌شوند. مجوز Agent تمدید نمی‌شود. |
| `/v1/sync` | همان IP تازه مشاهده‌شده لازم است. Worker بایت‌های دقیق JSON را با رمز مستقل HMAC-SHA256 امضا و شناسهٔ تازه تولید می‌کند. Agent امضا، زمان، تکرار و بازبینی سیاست را می‌سنجد. بازبینی یکسان فقط همان سیاست را تمدید می‌کند. IPv4 و IPv6 جداگانه برای ۱۲۰ تا ۸۶۴۰۰ ثانیه تمدید می‌شوند. پس از توقف همگام‌سازی، مجوزها منقضی می‌شوند. |
| `/v1/status` | فیلدهای لازم برای تأیید سیاست، مهلت، سلامت و نگهداری را برمی‌گرداند. همیشه `include_analysis=false` می‌خواهد و نشانی‌های مدیریت، فهرست شنونده‌ها، رویدادها، جزئیات منشأ احراز هویت و فیلدهای ناشناخته را حذف می‌کند. مجوز تمدید نمی‌شود. |
| `/v1/command` | فقط `restart_xray` و `reboot_vps` را با شناسهٔ ثابت عملیات، بازبینی سیاست و اعتبار ۱ تا ۶۰ ثانیه می‌پذیرد. هر عملیات در Agent جداگانه مجاز می‌شود. در صورت نامشخص بودن نتیجه، برای استعلام یا تکرار همان شناسه را به‌کار ببرید. Worker کد ثابت رد را برمی‌گرداند و اندازهٔ جریان پاسخ بالادست را به ۳۲۷۶۸ بایت محدود می‌کند. |

Agent مقدار `expires_at` را بر پایهٔ مهلت باقی‌مانده در ساعت یکنواخت پس از اعمال فایروال محاسبه می‌کند تا تأخیر اعمال، مهلت گزارش‌شده را افزایش ندهد.

## بررسی استقرار

Worker، VPC Service، Tunnel، Agent و کلاینت OpenWrt با هم آزموده شده‌اند. پس از استقرار، اتصال‌ها، رمزها و درخواست واقعی کلاینت خود را بررسی کنید. پیش از اجرای Wrangler از `companion/worker/`، Tunnel و VPC Service را بسازید و اتصال را تنظیم کنید.

مستندات رسمی Cloudflare (انگلیسی):

- <https://developers.cloudflare.com/workers-vpc/api/>
- <https://developers.cloudflare.com/workers-vpc/get-started/>
- <https://developers.cloudflare.com/workers/platform/deploy-buttons/>
- <https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/>

## نسخه و اجزای استقرار

[پروژهٔ ابزار Worker](../companion/worker/package.json) نسخهٔ npm مستقل `0.2.0` دارد. نسخهٔ بستهٔ Pro جداست. نیازمندی Node.js و ابزارها در فایل مشخصات و فایل قفل آمده است. VPS، Agent، Tunnel و VPC Service را جداگانه آماده کنید.

## نامزدهای خروجی فقط‌خواندنی

`POST /v1/egress-info` با توکن Bearer و JSON ناتهی `{ "device_id": "home" }` فقط به مسیر HMAC هم‌نام در `VPS_API` ثابت می‌رود. منابع داده محدود به `interface`، `panel` و `measured` هستند. نبود، کهنگی یا ابهام با هشدار مشخص می‌شود. خروجی مورد انتظار را خودتان انتخاب کنید. اندازه‌گیری در حالت پیش‌فرض خاموش است. این مسیر مهلت، ضربان کنترل و تأیید سیاست را تغییر نمی‌دهد. Agent قدیمی 501 `egress_info_unsupported` می‌دهد. پروتکل، مقصد ثابت اندازه‌گیری و یکپارچه‌سازی در [API عامل](VPS-EGRESS-INFO.fa.md) آمده‌اند.

[راهنمای پوشهٔ Worker](../companion/worker/README.fa.md)

</div>
