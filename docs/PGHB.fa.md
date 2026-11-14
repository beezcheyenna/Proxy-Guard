# ضربان PGHB و عیب‌یابی

[English](PGHB.en.md) · [简体中文](PGHB.md) · [日本語](PGHB.ja.md) · [Русский](PGHB.ru.md) · [فارسی](PGHB.fa.md)

## از کدام نشانی استفاده کنیم؟

| نشانی | کاربرد |
| --- | --- |
| PGHB رسمی `https://hb.pghb.app/` | بررسی سبک اتصال از طریق SOCKS محلی. در صورت فعال بودن تطبیق IPv4 خروجی، می‌توان از همان پاسخ استفاده کرد. |
| PGHB رسمی `https://hb.pghb.app/f` | دریافت جزئیات اتصال در صورت نیاز. در LuCI «آزمایش پراکسی فعلی» و سپس «اجرای عیب‌یابی کامل» را انتخاب کنید. این نشانی را می‌توان برای مقصد عیب‌یابی API هم انتخاب کرد. |
| مسیر `/cgi-bin/proxy-guard-api/*` روی روتر | رابط کنترل محلی با احراز هویت برای خواندن وضعیت، اجرای عیب‌یابی، درخواست یا لغو مسدودی موقت. از نشانی HTTPS روتر و UUID رابط استفاده کنید. [درخواست‌ها و پاسخ‌های API محلی](USAGE.fa.md#local-api) |

«آزمایش پراکسی فعلی» از تنظیمات ذخیره‌نشدهٔ فرم استفاده می‌کند. «اجرای عیب‌یابی کامل» از تنظیمات اعمال‌شدهٔ پراکسی استفاده می‌کند. موفقیت عیب‌یابی فقط همان درخواست از طریق SOCKS را تأیید می‌کند. برای تشخیص دسترسی، وضعیت فعلی محافظت را بررسی کنید.

## قواعد اعتبارسنجی در Proxy Guard 1.0

- PGHB باید HTTP `200` و متن دقیق `ネットは広大だわ` را برگرداند. متن ۲۴ بایت UTF-8 است و پایان خط یا BOM ندارد.
- برای `/f`، افزونه یک `X-PGHB-Nonce` تازه می‌فرستد و موفقیت عیب‌یابی را به بازگشت همان مقدار در پاسخ مشروط می‌کند. مقدار یک‌بارمصرف عیب‌یابی جداگانه ساخته می‌شود. UUID رابط فقط به API روی HTTPS روتر فرستاده می‌شود.
- بزرگی و کوچکی حروف نام سرآیند تفاوتی ندارد. تکرار `X-PGHB-IP` یا `X-PGHB-Nonce` در یک بلوک سرآیند باعث رد پاسخ می‌شود. تکرار سرآیندهای دیگر می‌تواند در رکوردهای جدا نمایش داده شود. فیلدهای اختیاری مبهم از خلاصه حذف می‌شوند.
- سقف خواندن سرآیندهای HTTP برابر **۳۲ کیبی‌بایت (۳۲٬۷۶۸ بایت)** است. آرایهٔ سرآیندهای عیب‌یابی پس از تبدیل به JSON نیز باید در **۳۲ کیبی‌بایت** جا شود. هر دو سقف برای مجموع داده و قالب‌بندی آن است.
- با فعال بودن تطبیق IPv4 خروجی از PGHB، مقدار `X-PGHB-IP` باید همان IPv4 مورد انتظار باشد. کشور، ASN و سرآیندهای مختص مرورگر دادهٔ اختیاری عیب‌یابی هستند. نبود آن‌ها به‌خودی‌خود نشانهٔ خرابی اتصال نیست.

مقدارهای `X-PGHB-*` به ترتیب پاسخ و به‌صورت رشته برمی‌گردند. مقدارهای خارج از UTF-8 با `"encoding":"base64"` مشخص می‌شوند. سرآیندهای تازهٔ `X-PGHB-*` با قالب معتبر می‌توانند بدون به‌روزرسانی افزونه در نتیجه دیده شوند. این صفحه رفتار فعلی افزونه در استفاده از PGHB را توضیح می‌دهد.

## فیلدهای پاسخ کامل

در فهرست تنظیمات `/f` **۱۰۲ سرآیند** تعریف شده است. هر پاسخ ممکن است سرآیندهای کمتری داشته باشد. Cloudflare می‌تواند سرآیند دارای مقدار خالی یا تعریف‌نشده را حذف کند. بعضی سنجه‌های ناموجود `0` برمی‌گردانند. ستون «نبود داده» شرایطی را نشان می‌دهد که فیلد ممکن است حذف شود یا برای عیب‌یابی معنی‌دار نباشد. خط تیره یعنی فیلد واحد عددی ندارد. [قواعد سرآیندهای پاسخ Cloudflare](https://developers.cloudflare.com/rules/transform/response-header-modification/#important-remarks) · [مرجع فیلدها](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/)

پاسخ سبک `/` از پنج فیلد پایهٔ IP، کشور یا منطقه، ASN، TLS و Ray استفاده می‌کند. نشانی IP مربوط به مبدأیی است که Cloudflare می‌بیند. برای درخواست از SOCKS، این اطلاعات به خروجی پراکسی مربوط است.

پیش از انتشار نتیجه، داده‌های حساس را بپوشانید. نتیجه ممکن است نشانی، موقعیت تقریبی، شناسه‌های TLS و داده‌های بازتاب‌داده‌شدهٔ درخواست مانند کوکی، Authorization یا پارامترهای URL را در بر داشته باشد. [حریم خصوصی](PRIVACY.fa.md)

### اتصال، مسیر و TLS

| سرآیند | عبارت Cloudflare یا مقدار ثابت | واحد | نبود داده | کاربرد در اعتبارسنجی |
| --- | --- | --- | --- | --- |
| `X-PGHB-IP` | `to_string(ip.src)` | — | پاسخِ فقط IPv6 برای تطبیق IPv4 کافی نیست | تطبیق اختیاری IPv4 خروجی |
| `X-PGHB-Country` | `ip.src.country` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-ASN` | `to_string(ip.src.asnum)` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-City` | `ip.src.city` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Region` | `ip.src.region` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Region-Code` | `ip.src.region_code` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Continent` | `ip.src.continent` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Latitude` | `ip.src.lat` | درجه | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Longitude` | `ip.src.lon` | درجه | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Metro-Code` | `ip.src.metro_code` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Postal-Code` | `ip.src.postal_code` | — | مکان‌یابی IP یا ASN در دسترس نیست | خیر |
| `X-PGHB-Client-Port` | `to_string(cf.edge.client_port)` | — | دادهٔ لایهٔ انتقال در دسترس نیست | خیر |
| `X-PGHB-Client-TCP` | `to_string(cf.edge.client_tcp)` | — | دادهٔ لایهٔ انتقال در دسترس نیست | خیر |
| `X-PGHB-Edge-IP` | `to_string(cf.edge.server_ip)` | — | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-Edge-Port` | `to_string(cf.edge.server_port)` | — | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-HTTP` | `http.request.version` | — | معمولاً موجود است | خیر |
| `X-PGHB-SSL` | `to_string(ssl)` | — | معمولاً موجود است | خیر |
| `X-PGHB-Delivery-Rate` | `to_string(cf.edge.l4.delivery_rate)` | بایت بر ثانیه | بدون آمار L4 مقدار `0` | خیر |
| `X-PGHB-TCP-RTT` | `to_string(cf.timings.client_tcp_rtt_msec)` | میلی‌ثانیه | برای اتصال غیر TCP مقدار `0` | خیر |
| `X-PGHB-QUIC-RTT` | `to_string(cf.timings.client_quic_rtt_msec)` | میلی‌ثانیه | برای اتصال غیر QUIC مقدار `0` | خیر |
| `X-PGHB-Edge-Time` | `to_string(cf.timings.edge_msec)` | میلی‌ثانیه | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-Origin-TTFB` | `to_string(cf.timings.origin_ttfb_msec)` | میلی‌ثانیه | زمان مبدأ در دسترس نیست، مثلاً در پاسخ کش‌شده | خیر |
| `X-PGHB-Worker-Time` | `to_string(cf.timings.worker_msec)` | میلی‌ثانیه | اجرای Worker یا زمان‌سنجی آن موجود نیست | خیر |
| `X-PGHB-Ray` | `cf.ray_id` | — | معمولاً موجود است | خیر |
| `X-PGHB-Zone` | `cf.zone.name` | — | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-TLS` | `cf.tls_version` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-Cipher` | `cf.tls_cipher` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-TLS-Hello` | `to_string(cf.tls_client_hello_length)` | بایت | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-Ciphers-SHA1` | `cf.tls_client_ciphers_sha1` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-TLS-Extensions` | `cf.tls_client_extensions_sha1` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-Extensions-LE` | `cf.tls_client_extensions_sha1_le` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-TLS-Client-Random` | `cf.tls_client_random` | — | دادهٔ دست‌دهی TLS موجود نیست | خیر |
| `X-PGHB-MTLS-Presented` | `to_string(cf.tls_client_auth.cert_presented)` | — | بدون mTLS معمولاً `false` | خیر |
| `X-PGHB-MTLS-Verified` | `to_string(cf.tls_client_auth.cert_verified)` | — | بدون mTLS معمولاً `false` | خیر |

### اطلاعات درخواست و مقدارهای بازتابی

| سرآیند | عبارت Cloudflare یا مقدار ثابت | واحد | نبود داده | کاربرد در اعتبارسنجی |
| --- | --- | --- | --- | --- |
| `X-PGHB-Host` | `http.host` | — | معمولاً موجود است | خیر |
| `X-PGHB-Method` | `http.request.method` | — | معمولاً موجود است | خیر |
| `X-PGHB-Path` | `http.request.uri.path` | — | معمولاً موجود است | خیر |
| `X-PGHB-URI` | `http.request.uri` | — | معمولاً موجود است | خیر |
| `X-PGHB-Full-URI` | `http.request.full_uri` | — | معمولاً موجود است | خیر |
| `X-PGHB-Raw-Path` | `raw.http.request.uri.path` | — | معمولاً موجود است | خیر |
| `X-PGHB-Raw-URI` | `raw.http.request.uri` | — | معمولاً موجود است | خیر |
| `X-PGHB-Raw-Full-URI` | `raw.http.request.full_uri` | — | معمولاً موجود است | خیر |
| `X-PGHB-Query` | `http.request.uri.query` | — | رشتهٔ پرس‌وجو وجود ندارد | خیر |
| `X-PGHB-Raw-Query` | `raw.http.request.uri.query` | — | رشتهٔ پرس‌وجو وجود ندارد | خیر |
| `X-PGHB-URI-Extension` | `http.request.uri.path.extension` | — | مسیر پسوند ندارد | خیر |
| `X-PGHB-Timestamp` | `to_string(http.request.timestamp.sec)` | ثانیهٔ یونیکس | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-Received-MS` | `to_string(http.request.timestamp.msec)` | میلی‌ثانیه در همان ثانیه (۰ تا ۹۹۹) | دادهٔ لبه در دسترس نیست | خیر |
| `X-PGHB-Request-ID` | `uuidv4(cf.random_seed)` | — | معمولاً موجود است | خیر |
| `X-PGHB-Headers-Truncated` | `to_string(http.request.headers.truncated)` | — | معمولاً موجود است | خیر |
| `X-PGHB-Verified-Bot` | `to_string(cf.client.bot)` | — | معمولاً موجود است | خیر |
| `X-PGHB-Verified-Bot-Category` | `cf.verified_bot_category` | — | دسته‌بندی ربات موجود نیست | خیر |
| `X-PGHB-Nonce` | `http.request.headers["x-pghb-nonce"][0]` | — | اگر درخواست Nonce نداشته باشد، این فیلد غایب است | تطبیق Nonce برای `/f` |
| `X-PGHB-Accept` | `http.request.headers["accept"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Accept-Encoding` | `http.request.headers["accept-encoding"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Accept-Language` | `http.request.headers["accept-language"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Authorization` | `http.request.headers["authorization"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Cookie` | `http.cookie` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-User-Agent` | `http.user_agent` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Origin` | `http.request.headers["origin"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Referer` | `http.referer` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Range` | `http.request.headers["range"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-DNT` | `http.request.headers["dnt"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-GPC` | `http.request.headers["sec-gpc"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Save-Data` | `http.request.headers["save-data"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Upgrade-Insecure` | `http.request.headers["upgrade-insecure-requests"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Sec-Purpose` | `http.request.headers["sec-purpose"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Fetch-Dest` | `http.request.headers["sec-fetch-dest"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Fetch-Mode` | `http.request.headers["sec-fetch-mode"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Fetch-Site` | `http.request.headers["sec-fetch-site"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Fetch-User` | `http.request.headers["sec-fetch-user"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Client-Hints-UA` | `http.request.headers["sec-ch-ua"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Client-Hints-Mobile` | `http.request.headers["sec-ch-ua-mobile"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Client-Hints-Platform` | `http.request.headers["sec-ch-ua-platform"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-UA-Arch` | `http.request.headers["sec-ch-ua-arch"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-UA-Bitness` | `http.request.headers["sec-ch-ua-bitness"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-UA-Full-Version-List` | `http.request.headers["sec-ch-ua-full-version-list"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-UA-Platform-Version` | `http.request.headers["sec-ch-ua-platform-version"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Top-Language` | `http.request.accepted_languages[0]` | — | زبان ترجیحی در دسترس نیست | خیر |
| `X-PGHB-If-Match` | `http.request.headers["if-match"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-If-Modified-Since` | `http.request.headers["if-modified-since"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-If-None-Match` | `http.request.headers["if-none-match"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-If-Unmodified-Since` | `http.request.headers["if-unmodified-since"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Request-Cache-Control` | `http.request.headers["cache-control"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Request-Content-Length` | `http.request.headers["content-length"][0]` | بایت | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Request-Content-Type` | `http.request.headers["content-type"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |
| `X-PGHB-Request-Priority` | `http.request.headers["priority"][0]` | — | سرآیند یا مقدار در درخواست نیست | خیر |

### اطلاعات پاسخ و مقدارهای ثابت

| سرآیند | عبارت Cloudflare یا مقدار ثابت | واحد | نبود داده | کاربرد در اعتبارسنجی |
| --- | --- | --- | --- | --- |
| `X-PGHB-Response-Code` | `to_string(http.response.code)` | — | معمولاً موجود است | خیر |
| `X-PGHB-Response-Type` | `http.response.content_type.media_type` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Cache-Control` | `http.response.headers["cache-control"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Content-Length` | `http.response.headers["content-length"][0]` | بایت | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Encoding` | `http.response.headers["content-encoding"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-ETag` | `http.response.headers["etag"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Age` | `http.response.headers["age"][0]` | ثانیه | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Last-Modified` | `http.response.headers["last-modified"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Location` | `http.response.headers["location"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Response-Vary` | `http.response.headers["vary"][0]` | — | فیلد اصلی در پاسخ نیست | خیر |
| `X-PGHB-Error-Code` | `to_string(cf.response.1xxx_code)` | — | بدون خطای 1xxx در Cloudflare مقدار `0` | خیر |
| `X-PGHB-Error-Type` | `cf.response.error_type` | — | نوع خطای Cloudflare وجود ندارد | خیر |
| `X-PGHB-Endpoint` | `full` | — | مقدار ثابت `/f` | خیر |
| `X-PGHB-Heartbeat-Version` | `1` | — | مقدار ثابت `/f` | خیر |
| `X-PGHB-Schema-Version` | `1` | — | مقدار ثابت `/f` | خیر |
| `X-PGHB-Service` | `PGHB` | — | مقدار ثابت `/f` | خیر |

دو فیلدی که در اعتبارسنجی به کار می‌روند نقش‌های جداگانه دارند. قاعدهٔ رد سرآیند تکراری برای هر دو اعمال می‌شود. وضعیت واقعی HTTP جداگانه بررسی می‌شود و رشتهٔ `X-PGHB-Response-Code` برای عیب‌یابی است.

رفت‌وبرگشت TCP و QUIC به اتصال تا Cloudflare مربوط است. `milliseconds` در API روتر زمان آزمون از روتر را نشان می‌دهد. زمان دریافت درخواست در Cloudflare از `Timestamp` بر حسب ثانیه و `Received-MS` بر حسب میلی‌ثانیه در همان ثانیه ساخته می‌شود. `Edge-IP` نشانی لبهٔ Cloudflare و `IP` نشانی مبدأ مشاهده‌شده است.

[راهنمای کاربر](USER-GUIDE.fa.md) · [API محلی](USAGE.fa.md#local-api) · [کد تحلیل پاسخ](../package/root/usr/lib/proxy-guard/public-heartbeat.lua#L45-L95)
