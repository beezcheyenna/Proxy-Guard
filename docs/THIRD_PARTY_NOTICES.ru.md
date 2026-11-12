# Сторонние уведомления

[English](THIRD_PARTY_NOTICES.md) · [简体中文](THIRD_PARTY_NOTICES.zh-CN.md) · [日本語](THIRD_PARTY_NOTICES.ja.md) · [Русский](THIRD_PARTY_NOTICES.ru.md) · [فارسی](THIRD_PARTY_NOTICES.fa.md)

Дата записи 2026-11-08. Охватывает открытые исходники Standard, Pro, Agent и Worker. Условия берутся из оригинальных уведомлений исходных проектов.

## Собственный код

Copyright (c) 2026 Proxy Guard contributors.

Оригинальный код и документация доступны по корневой [лицензии MIT](../LICENSE). Политика одинакова для Standard и Pro. Строки, патчи, библиотеки, интерпретаторы, инструменты, ядра и прошивки сохраняют свои условия.

## Сообщения журналов

`package/root/usr/lib/proxy-guard/passwall-log.uc` и регрессионные примеры используют строки и переводы следующих ревизий. Разбор и управление оригинальные. Охраняемый заимствованный материал сохраняет лицензию источника. Короткие идентификаторы и сочетания оцениваются по фактическому составу.

| Проект | Ревизия | Условия источника | Использование |
| --- | --- | --- | --- |
| PassWall | 5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52 | GNU GPL v3 по заявлению проекта | Жизненный цикл и тесты |
| PassWall2 | 896c586a27c9a7c0b9e3d75b631965dea86b9945 | GNU GPL v3 по заявлению проекта | Английские, китайские, русские и персидские сообщения и тесты |
| OpenClash | e553e82e01c697aefbe1555261a503f425e00ccd | MIT с уведомлениями файлов | Идентификаторы жизненного цикла |
| Nikki | 78e1a751d55ed0762811f054ee699049473da7b8 | GPL-3.0-or-later из рецепта | Идентификаторы жизненного цикла |
| HomeProxy | fadaa676104f59ff6ace480a780a258d846d0aec | GPL-2.0-only из init | Идентификаторы жизненного цикла |

Суммы архивов и случаи PassWall/PassWall2 записаны в `tests/passwall_log_corpus.json`. URL, копии и суммы всех пяти проектов находятся в [перечне](THIRD_PARTY_COMPONENTS.json) и [указателе](../LICENSES/README.ru.md). IPK/APK используют выбранные строки и их соответствия событиям.

Ниже авторство из закреплённых рецептов. Остальные уведомления и права сохраняются в исходниках.

PassWall: Copyright (C) 2018-2020 L-WRT Team, Copyright (C) 2021-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization. PassWall2: Copyright (C) 2022-2025 xiaorouji, Copyright (C) 2026 Openwrt-Passwall Organization.

- https://github.com/Openwrt-Passwall/openwrt-passwall/tree/5e2bbfa8e6a32f7e54a7fe29891a28fb05439e52
- https://github.com/Openwrt-Passwall/openwrt-passwall2/tree/896c586a27c9a7c0b9e3d75b631965dea86b9945
- https://github.com/vernesong/OpenClash/tree/e553e82e01c697aefbe1555261a503f425e00ccd
- https://github.com/nikkinikki-org/OpenWrt-nikki/tree/78e1a751d55ed0762811f054ee699049473da7b8
- https://github.com/immortalwrt/homeproxy/tree/fadaa676104f59ff6ace480a780a258d846d0aec

## Зависимости OpenWrt

Компоненты предоставляются прошивкой и её источниками. Данные о лицензиях относятся к проверенным версиям и файлам.

| Компонент | Применение | Подтверждение |
| --- | --- | --- |
| LuCI, luci-lib-jsonc, luci-lib-nixio | Интерфейс, JSON, POSIX и сокеты | Apache-2.0 / NOTICE · Проверенные рецепты 24.10 |
| Lua | Интерпретатор | MIT · Версия установленного Lua |
| ucode, fs/uci | Интерпретатор, блокировки, конфигурация | ISC · Отдельные условия подключённых библиотек |
| libuci | Библиотека конфигурации | LGPL v2.1 (`libuci.c`) · Заголовок библиотеки |
| libuci-lua | Импорт `require('uci')` в Lua | GPL v2 (`lua/uci.c`) · Заголовок привязки Lua |
| rpcd | RPC и ACL | ISC · Проверенный рецепт 24.10 |
| ubus | Системная шина | LGPL-2.1 · Рецепт и уведомления файлов |
| procd, netifd, BusyBox | Сторож, интерфейсные события, утилиты | GPL-2.0 · Рецепты и уведомления файлов |
| firewall4 | Загрузка и согласование правил | ISC · Проверенный рецепт |
| nftables / Linux Netfilter | Фильтрация и учёт соединений | GPL · Сохраняйте уведомления при распространении |
| curl / CA bundle | Проверки SOCKS/HTTPS | curl / CA · Условия отдельных пакетов |
| Ruby / YAML (OpenClash) | Безопасный разбор существующих настроек | Установленные версии и библиотеки |

Метаданные LGPL пакета UCI и заголовок GPL v2 привязки Lua учитываются отдельно. Внешний вызов и импорт в процесс различаются. При распространении сочетаний проверяйте реальные версии, интеграцию и применимые исключения.

## Agent Pro и Cloudflare

Agent использует стандартную библиотеку Python и внешние средства Linux. Python, nftables, iproute2, systemd/OpenRC, прокси и панели поставляются отдельно. cloudflared — отдельная программа Apache-2.0. Worker использует размещённые API Cloudflare на условиях сервиса. Зависимости разработки из lockfile:

- Wrangler 4.156.0 — MIT OR Apache-2.0
- Miniflare 5.20261023.3-beta — MIT
- workerd 1.20261023.1 — Apache-2.0

<https://github.com/cloudflare/cloudflared/blob/master/LICENSE>

[Перечень](../companion/worker/THIRD_PARTY_DEPENDENCIES.json) содержит 91 некорневую запись с необязательными платформенными пакетами. Инструменты, node_modules и cloudflared не входят в пакеты приложения. Для отдельного распространения соблюдайте уведомления и требования исходного кода фактически включённых пакетов.

## Клиенты, ядра и панели

PassWall, PassWall2, OpenClash, Nikki, HomeProxy, Xray, sing-box, Mihomo и 3x-ui поддерживаются отдельно. Плагин читает их настройки, журналы и состояние или вызывает разрешённое управление. При включении чужого кода или бинарников проверьте уведомления и исходники по каждому компоненту.

## Область лицензии

Проверяйте фактическое содержимое и способ сочетания при распространении. Определяющими остаются оригиналы для компонентов и файлов. См. [лицензирование](LICENSING.ru.md).
