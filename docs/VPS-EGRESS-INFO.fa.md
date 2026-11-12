# نامزدهای IPv4 خروجی فقط‌خواندنی (طرح ۱)

[English](VPS-EGRESS-INFO.md) · [简体中文](VPS-EGRESS-INFO.zh-CN.md) · [日本語](VPS-EGRESS-INFO.ja.md) · [Русский](VPS-EGRESS-INFO.ru.md) · [فارسی](VPS-EGRESS-INFO.fa.md)

<div dir="rtl" lang="fa">

API به راهنما شواهد نامزد می‌دهد. خروجی مورد انتظار، سیاست، مجوز خانه، ضربان کنترل یا مسیر SSH، نگهداری و مهلت اجرای آزمایشی را تغییر نمی‌دهد. نشانی رابط، سرنخ پنل و سنجش مسیر پیش‌فرض میزبان شواهد جداگانه‌اند. مسیر واقعی پروکسی مستقل بررسی می‌شود.

## API

- Cloudflare: `POST /v1/egress-info`، Bearer دستگاه و JSON `{"device_id":"home"}`. جدول خالی Lua در `luci.jsonc` آرایه می‌شود، پس شیء ناتهی بدهید.
- رلهٔ Agent: `POST /v1/egress-info` با HMAC موجود برای `device_id`، `issued_at`، `request_id` یکتا و `purpose:"egress-info"` امضا می‌شود. کاربرد روی مسیر دیگر رد می‌شود. تکرار یا nonce منقضی رد می‌شود.
- مستقیم: `GET /v1/direct/egress-info` با Bearer مستقیم و شرط HTTPS و شنوندهٔ عمومی. IP طرف مقابل نامزد نمی‌شود.

نمونهٔ بدون نامزد عمومی:

```json
{
  "ok": true,
  "protocol": 3,
  "egress_info_schema": 1,
  "generated_at": 1700000000,
  "status": "unavailable",
  "candidates": [],
  "ambiguous": false,
  "business_egress_verified": false,
  "warnings": [
    "measurement_disabled",
    "no_public_ipv4_candidate"
  ],
  "measurement": {
    "state": "disabled",
    "checked_at": null,
    "stale": true
  }
}
```

قالب نامزد `{"ipv4":"8.8.8.8","evidence":[{"source":"interface","checked_at":1700000000,"scope":"host_interface"}]}` است. نشانی نمونه فقط برای نشان دادن قالب است. `source` از `interface`، `panel` یا `measured` و `scope` متناظر از `host_interface`، `panel_config` یا `host_default_ipv4` است. زمان‌ها و `generated_at` ثانیهٔ Unix به UTC و تازگی با ساعت یکنواخت‌اند. حداکثر ۸ IPv4 یکتا، هر کدام ۳ شاهد دارند. هنگام کوتاه‌شدن فهرست، اندازه‌گیری اولویت دارد. بیش از یک IPv4 عمومی هشدار ابهام می‌دهد. `business_egress_verified` در طرح ۱ همیشه false است. نامزد اول، `/observe` خود، نام پنل یا مقصد REALITY را خودکار وارد نکنید.

`status` یکی از `available`، `partial`، `unavailable` و مستقل از سلامت سرویس است. `measurement.state` یکی از `disabled`، `pending`، `fresh`، `stale`، `unavailable`، `conflict` است. پس از خطا یا دو برابر فاصله، آخرین نتیجه کهنه نشان داده می‌شود. خاموش بودن سنجش محافظت موجود را تغییر نمی‌دهد.

کدهای ثابت هشدار: `non_public_ipv4_omitted`, `no_public_ipv4_candidate`, `interface_unavailable`, `panel_unavailable`, `panel_hint_unverified`, `panel_hint_ignored`, `measurement_disabled`, `measurement_pending`, `measurement_failed`, `measurement_stale`, `measurement_disagreement`, `multiple_public_ipv4_candidates`, `host_default_not_business_egress`, `candidates_truncated`. ترجمه از فهرست رابط می‌آید.

نتیجهٔ احراز هویت‌شدهٔ خالی، کهنه یا مبهم 200 است. خطای مستقیم 401، امضا یا nonce برابر 403، بدنهٔ نامعتبر 400، Agent قدیمی 501 `egress_info_unsupported`، VPC در دسترس نیست یا داده نامعتبر 502، و خطای جمع‌آوری 503 است. خطا مسیر خام، اطلاعات پنل، نام رابط، بدنهٔ سنجش و رمز ندارد. `Cache-Control: no-store` برقرار و حافظهٔ نهان فقط در RAM است.

## تنظیمات و محدودیت Agent

شیء اختیاری `egress` فقط کلیدهای زیر را می‌گیرد:

```json
{
  "panel_config_path": "",
  "measure_enabled": false,
  "measure_interval": 300
}
```

جمع‌آوری پنل پیش‌فرض خاموش است. JSON عادی تعیین‌شده باید مالکیت کاربر Agent را داشته باشد، برای گروه و دیگران نوشتنی نباشد و جزء آخر پیوند نمادین نباشد. خواندن تا ۶۴ KiB است. برای Xray تولیدشدهٔ 3x-ui فقط IPv4 عددی `inbounds[].listen` و `outbounds[].sendThrough` سرنخ تأییدنشده است. مقصد REALITY، سرور دوردست، دامنه و اسرار جست‌وجو یا resolve نمی‌شوند.

رابط با `ip -j -4 address show` ثابت، مهلت ۲ ثانیه و ۶۴ KiB خوانده می‌شود و ۱۵ ثانیه در حافظه می‌ماند. نبود ابزار یا فقط IP غیرعمومی/NAT هشدار می‌دهد.

سنجش پیش‌فرض خاموش است. در حالت روشن نمونه‌بردار فقط [API ثابت IPv4 ipify](https://api.ipify.org/) را می‌خواند. درخواست و تنظیم، URL، فرمان، به‌روزرسانی اجباری یا مقصد نمی‌پذیرند. DNS به IPv4 عمومی محدود و سوکت TLS به همان IP با نام ثابت SNI و اعتبارسنجی گواهی متصل است. متغیر پروکسی، تغییر مسیر، تکرار و رمز استفاده نمی‌شوند. سوکت ۲ ثانیه، بدنه ۲۵۶ بایت و فرایند جدا با DNS مجموعاً ۵ ثانیه مهلت دارد. فاصله ۶۰ تا ۳۶۰۰، پیش‌فرض ۳۰۰ ثانیه است. خواندن API سنجش تازه آغاز نمی‌کند و نتیجه با برچسب IPv4 پیش‌فرض میزبان است.

## یکپارچه‌سازی

`--check-config` بخش `egress` را می‌سنجد. نصب‌کننده `egress.py` و `control.Server` چرخهٔ جمع‌آوری را دارد. راهنما از تنظیم فقط اتصال حتی با همگام‌سازی خاموش استفاده می‌کند و تأیید ورودی، رمز نشست و مجوز RPC را حفظ می‌کند. خواندن، سیاست را ذخیره یا اعمال نمی‌کند، نگهداری را صف نمی‌کند و در RPC سنجش نمی‌فرستد.

## آزمون پایهٔ ایزوله

فقط در ماشین مجازی آزمایشی خود و روی پروندهٔ نامزد یا تثبیت‌شده اجرا کنید:

```sh
python3 -B companion/vps/test_egress.py
cd companion/worker
node --test test/egress.test.mjs test/worker.test.mjs test/regression.test.mjs test/contract.test.mjs
```

آزمون جمع‌آوری دادهٔ تزریقی می‌گیرد و درخواست بیرونی ندارد. آزمون HTTP از Agent واقعی و درایور فایروال در حافظه استفاده می‌کند و nft واقعی را تغییر نمی‌دهد. نصب، مسیر پروکسی واقعی و Cloudflare جدا بررسی می‌شوند.

</div>
