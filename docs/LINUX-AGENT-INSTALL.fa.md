# نصب Linux VPS Agent برای Pro

[English](LINUX-AGENT-INSTALL.en.md) · [简体中文](LINUX-AGENT-INSTALL.md) · [日本語](LINUX-AGENT-INSTALL.ja.md) · [Русский](LINUX-AGENT-INSTALL.ru.md) · [فارسی](LINUX-AGENT-INSTALL.fa.md)

<div dir="rtl" lang="fa">

امکانات راه‌دور Pro به استاندارد و Pro روی OpenWrt و Agent روی VPS لینوکس نیاز دارند. HTTPS مستقیم یا Cloudflare Worker همراه Tunnel/VPC را انتخاب کنید. IPK/APK روی روتر و نصب‌کنندهٔ Python روی VPS اجرا می‌شود. Python 3.10 یا بالاتر، nftables، قابلیت متناظر هسته و systemd یا OpenRC لازم‌اند. [سازگاری](COMPATIBILITY.fa.md) و [ماتریس آزمون](TEST-MATRIX.fa.md) را ببینید.

## ۱. نصب وابستگی‌ها

دستور مناسب توزیع خود را انتخاب کنید.

**Ubuntu / Debian**

```sh
sudo apt update
sudo apt install -y python3 nftables iproute2 ca-certificates
```

**Rocky Linux**

```sh
sudo dnf install -y python3 nftables iproute ca-certificates
```

**Alpine Linux با root**

```sh
apk add python3 nftables iproute2 coreutils ca-certificates
```

مفسر سرویس را بررسی کنید.

```sh
/usr/bin/python3 --version
```

`/usr/bin/python3` باید نسخهٔ 3.10 یا بالاتر باشد. Python در مسیر دیگر یا محیط مجازی، مفسر سرویس را تغییر نمی‌دهد. نصب‌کننده پیکربندی و قابلیت nftables از جمله مجموعهٔ پویا و محدودیت اتصال را می‌سنجد. ماژول هسته باید متناظر باشد. Agent سرویس سیاست اختصاصی نصب می‌کند.

## ۲. استخراج و آماده‌سازی پیکربندی

`proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz` را به VPS منتقل و در پوشهٔ بایگانی اجرا کنید:

```sh
tar -xzf proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz
cd Proxy-Guard/companion/vps
cp agent.example.json agent.json
chmod 600 agent.json
python3 - <<'PY'
from pathlib import Path
import json
import secrets

path = Path('agent.json')
config = json.loads(path.read_text())
config['agent_secret'] = secrets.token_urlsafe(32)
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o600)
PY
```

| تنظیم | مقدار |
| --- | --- |
| `device_id` | شناسهٔ دستگاه مانند `home`، یکسان در روتر و Worker مورد استفاده. |
| `agent_secret` | رمز تصادفی جداگانه برابر `AGENT_SECRET` Worker. روی روتر قرار نگیرد. |
| `services` | نام فرایند و پورت‌های TCP/UDP واقعی پروکسی. |
| `managed_units` | وابستگی شروع با شکل `name.service`. در OpenRC نام بدون `.service` است. SSH پذیرفته نمی‌شود. |
| `egress.panel_config_path` | مسیر اختیاری JSON محلی مورد اعتماد Xray. سنجش بیرونی پیش‌فرض خاموش است. |
| SSH، ضربان مسیر، نگهداری | جداگانه تنظیم و فعال شوند. |

Agent پروکسی نصب‌شده را پایش و مدیریت می‌کند. برای Xray تحت 3x-ui، نام فرایند و رفتار USR1 نسخهٔ مربوط را بررسی و مبدل مناسب انتخاب کنید.

## ۳. انتخاب مسیر کنترل

### Cloudflare Worker و Tunnel/VPC

معمولاً `bind=127.0.0.1`، `port=8788` و `public_control=false` بمانند تا `cloudflared` همان VPS به API محلی دسترسی یابد. Tunnel، VPC Service و `VPS_API` را طبق [راهنمای Worker](CLOUDFLARE-WORKER.fa.md) تنظیم کنید. `DEVICE_ID` یکسان باشد. `DEVICE_TOKEN` بین دستگاه و Worker و `AGENT_SECRET` جداگانه بین Worker و Agent است. در تنظیمات VPS روتر، Cloudflare را انتخاب و URL پایهٔ HTTPS Worker، شناسه و توکن دستگاه را وارد کنید.

### HTTPS مستقیم

`public_control=true`، شنونده، `tls_cert` و `tls_key` معتبر و `direct_token` جداگانه تنظیم کنید. در روتر HTTPS مستقیم و URL پایهٔ Agent، شناسه و `direct_token` را وارد کنید. رمز ۳۲ تا ۲۵۶ حرف، رقم، زیرخط یا خط تیره دارد. مقدار نمونه را جایگزین کنید.

**در هر دو حالت، مسیر مستقیم کنترل را بررسی کنید.** ضربان مستقل مسیر باید از SOCKS محلی بگذرد.

<a id="control-and-path"></a>

### نشانی، رمز و مسیر مستقل پروکسی

| کاربرد | تنظیم روتر | تنظیم سمت سرور |
| --- | --- | --- |
| کنترل Cloudflare | URL پایهٔ HTTPS Worker، شناسه و توکن | `DEVICE_ID` و `DEVICE_TOKEN`. `AGENT_SECRET` با `agent_secret` عامل جفت می‌شود. |
| کنترل HTTPS مستقیم | URL پایهٔ HTTPS عامل، شناسه و توکن | `device_id`، `direct_token`، شنوندهٔ عمومی و TLS. |
| ضربان مسیر | پایش مسیر، URL پایهٔ HTTPS عامل و توکن جداگانه | `path_token` از مسیر SOCKS به `/v1/direct/path-heartbeat`. |

`/v1/...` را به URL پایه اضافه نکنید. رمزها جدا باشند و پیش از مدیریت SSH، احراز هویت هر دو مسیر را بسنجید.

- کنترل مستقیم نیازمند IP عمومی واقعی مبدأ خانه است. Agent آن را از سرآیند ارسال مجدد بازیابی نمی‌کند. همان HTTPS پایه می‌تواند ضربان را از SOCKS با توکن جدا بپذیرد.
- API محلی HTTP در Cloudflare برای Tunnel همان میزبان است. ضربان از پروکسی به ورودی جداگانهٔ HTTPS نیاز دارد. در صورت استفاده از پروکسی معکوس TLS، فقط `/v1/direct/path-heartbeat` را با حفظ Bearer بفرستید. کنترل مستقیم همچنان به مبدأ واقعی نیاز دارد.
- اگر شنوندهٔ Agent عمومی و HTTPS شد، پرچم عمومی، توکن مستقیم و گواهی را تنظیم و پروتکل و پورت Tunnel/VPC را هماهنگ کنید. صدور و تمدید گواهی و پروکسی معکوس جدا مدیریت می‌شوند.

ورودی کنترل و ضربان باید پیش از تمدید مجوز هم دسترس‌پذیر باشد. مسیر مستقیم و SOCKS را جداگانه بیازمایید.

## ۴. نصب و بررسی

از `companion/vps` اجرا کنید.

**Ubuntu / Debian / Rocky Linux**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
sudo python3 agent.py --config "$PWD/agent.json" --check-kernel
sudo sh ./install.sh --install "$PWD/agent.json"

sudo systemctl status proxy-guard-access-policy proxy-guard-access --no-pager
sudo journalctl -u proxy-guard-access -n 50 --no-pager
```

**Alpine Linux با root**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
python3 agent.py --config "$PWD/agent.json" --check-kernel
sh ./install.sh --install "$PWD/agent.json"

rc-service proxy-guard-access-policy status
rc-service proxy-guard-access status
```

برنامه در `/opt/proxy-guard-access` و پیکربندی فعال در `/etc/proxy-guard-access/agent.json` است. نصب‌کننده سرویس عامل و سیاست را اجرا و تنظیم قبلی را حفظ می‌کند. برای تغییر، پیکربندی فعال را ویرایش و دوباره بررسی کنید. در LuCI ذخیره و اعمال کنید و همگام‌سازی، مجوز و سرویس را بسنجید و پورت‌های مدیریتی را صریح انتخاب کنید.

## ۵. نجات SSH و پورت پنل

مدیریت SSH پیش‌فرض خاموش است. پس از فعال‌سازی و بررسی نشست مدیریت و هر دو مسیر، قطع پیوستهٔ هر دو ضربان احراز هویت‌شده نجات را فعال می‌کند. تأخیر پیش‌فرض **۶۰ ثانیه** است.

تنظیم تازه نجات عمومی دارد. مدت `0` تا بازیابی مجوز خانگی ادامه دارد و `30` تا `3600` ثانیه زمان‌دار است. می‌توان به مبدأ مدیریت محدود کرد. مدت صریح قبلی از جمله `600` حفظ می‌شود. نجات عمومی زمان در معرض بودن را افزایش می‌دهد. بعد از پایان مهلت، اگر IP خانه عوض شود و مبدأ مجاز دیگری نباشد، ورود SSH تازه ممکن است ناموفق باشد. فایروال سیستم، احراز هویت SSH و گروه امنیتی ارائه‌دهنده برقرارند.

پورت جداگانهٔ انتخاب‌نشدهٔ 3x-ui، API و اشتراک تابع فایروال سیستم است. پورت انتخاب‌شده یا ورودی با IP، پروتکل و پورت مشترک تابع قانون منتخب است. شنونده‌ها را بررسی کنید.

## ۶. حالت پورت و پیکربندی خام

قانون از پیش‌فرض پیروی می‌کند یا فهرست مجاز، محدودیت استاندارد یا مشاهده را انتخاب می‌کند. مبدأ، آستانه و مدت جداگانه‌اند. قابلیت راه‌دور پیش از اعمال بررسی می‌شود. قابلیت تازه ممکن است به ارتقای Agent و در Cloudflare به Worker نیاز داشته باشد. دو ویرایشگر روتر برای UCI محافظت محلی و VPS هستند. شنونده، TLS و مجوز نگهداری در Agent تنظیم می‌شوند. [راهنمای Worker](CLOUDFLARE-WORKER.fa.md) را ببینید.

## ۷. ارتقا و پشتیبان

SSH یا کنسول را نگه دارید. از پیکربندی فعال، گواهی و کلید TLS، منبع سازگار، وضعیت پایدار و سابقهٔ عملیات خصوصی پشتیبان بگیرید. وضعیت و شمارهٔ بازبینی هر نمونه را حفظ کنید.

از `companion/vps` منبع تازه، خط اول برای systemd یا خط دوم را روی Alpine با root اجرا کنید.

```sh
# Ubuntu / Debian / Rocky Linux
sudo sh ./install.sh --install /etc/proxy-guard-access/agent.json

sh ./install.sh --install /etc/proxy-guard-access/agent.json
```

نصب‌کننده پیکربندی و هسته را می‌سنجد، برنامه و سرویس را به‌روز می‌کند و Agent را دوباره راه می‌اندازد. سرویس، احراز هویت، شمارهٔ سیاست، قابلیت و پورت را بسنجید. پیش از بازگشت نسخه، سازگاری وضعیت و تنظیم را بررسی کنید.

## ۸. بررسی انتهابه‌انتها

- Agent، سرویس سیاست، فرایند واقعی پروکسی، شنوندهٔ TCP/UDP و درخواست واقعی را بسنجید.
- TLS، شناسه، رمز مستقل، مسیر مستقیم و در Cloudflare اتصال ثابت VPC و Tunnel را کنترل کنید. IP تازهٔ خانه مشاهده و همگام شود. مجوز تازه را در LuCI ببینید.
- نخست یک قانون را آزمایش و تأیید کنید. مبدأ مجاز و محدود، پورت انتخاب‌نشده، پنل، اشتراک، SSH و Docker را جدا بررسی کنید.
- ضربان مسیر، نجات و نگهداری را جدا بیازمایید. قانون‌ها را پس از قطع کنترل یا پروکسی، انقضای اجرای آزمایشی و راه‌اندازی دوباره بررسی کنید.

| نشانه | مورد بررسی |
| --- | --- |
| بررسی پیش از نصب ناموفق است | Python، init در حال اجرا، عبارت nftables و ماژول. |
| HTTPS یا احراز هویت ناموفق است | زنجیره و اعتبار گواهی، ساعت، شنونده، شناسه و توکن. بررسی TLS را حفظ کنید. |
| Worker پاسخ می‌دهد و Agent در دسترس نیست | Tunnel، مقصد ثابت، شناسهٔ اتصال و شنوندهٔ محلی. |
| کنترل درست است و ضربان مسیر ناموفق | ورودی HTTPS مستقل، توکن مسیر، SOCKS و خروجی واقعی. |
| پنل یا اشتراک محدود شده | قانون منتخب یا IP، پروتکل و پورت مشترک. |
| نجات فعال است و SSH کار نمی‌کند | سرویس و احراز هویت SSH، فایروال و گروه امنیتی. |
| تنظیم عوض شده و وضعیت ثابت است | فایل فعال، بررسی و راه‌اندازی مجدد، اجرای آزمایشی یا نتیجهٔ نامعلوم. |

[معماری و رفتار Pro](PRO-COMPANION.fa.md) و [بازیابی](RECOVERY.fa.md) را ببینید.

## ۹. حذف

در `companion/vps` منبع متناظر نگه‌داری‌شده، خط اول را برای systemd یا خط دوم را در Alpine با root اجرا کنید.

```sh
sudo sh ./uninstall.sh --remove

sh ./uninstall.sh --remove
```

سرویس‌ها و قانون‌های مؤلفه حذف می‌شوند. پیکربندی، اسرار و برنامه حفظ می‌شوند. [بازیابی](RECOVERY.fa.md) روش تأیید را توضیح می‌دهد.

[راهنمای پوشهٔ VPS Agent](../companion/vps/README.fa.md)

</div>
