# Кандидаты выходного IPv4 только для чтения (схема 1)

[English](VPS-EGRESS-INFO.md) · [简体中文](VPS-EGRESS-INFO.zh-CN.md) · [日本語](VPS-EGRESS-INFO.ja.md) · [Русский](VPS-EGRESS-INFO.ru.md) · [فارسی](VPS-EGRESS-INFO.fa.md)

API даёт мастеру данные для выбора. Он не изменяет ожидаемый адрес, политику, домашнее разрешение, сигналы SSH, обслуживание или срок пробной конфигурации. Адрес интерфейса, подсказка панели и измерение маршрута хоста представляют разные данные. Реальный маршрут прокси проверяется отдельно.

## API

- Cloudflare: `POST /v1/egress-info`, Bearer устройства и JSON `{"device_id":"home"}`. В `luci.jsonc` пустая таблица Lua становится массивом, используйте непустой объект.
- Agent: подписанный `POST /v1/egress-info` с HMAC для `device_id`, `issued_at`, уникального `request_id` и `purpose:"egress-info"`. Другие маршруты отвергают это назначение. Повтор и просроченный nonce отклоняются.
- Прямой канал: `GET /v1/direct/egress-info` с прямым Bearer и действующими требованиями HTTPS и публичной привязки. IP клиента запроса не становится кандидатом.

Пример без публичного кандидата:

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

Формат кандидата: `{"ipv4":"8.8.8.8","evidence":[{"source":"interface","checked_at":1700000000,"scope":"host_interface"}]}`. Адрес приведён для иллюстрации. `source` — `interface`, `panel` или `measured` с `scope` соответственно `host_interface`, `panel_config` или `host_default_ipv4`. Время и `generated_at` — секунды Unix UTC, свежесть монотонная. До 8 уникальных IPv4 и до 3 свидетельств на адрес. При усечении измеренные имеют приоритет. Несколько публичных IPv4 дают предупреждение. В схеме 1 `business_egress_verified` всегда false. Не переносите автоматически первый результат, собственный `/observe`, имя панели или цель REALITY.

`status`: `available`, `partial`, `unavailable` независимо от здоровья службы. `measurement.state`: `disabled`, `pending`, `fresh`, `stale`, `unavailable`, `conflict`. После ошибки или двух интервалов прошлый результат помечается устаревшим. Выключенное измерение оставляет защиту в действии.

Коды предупреждений: `non_public_ipv4_omitted`, `no_public_ipv4_candidate`, `interface_unavailable`, `panel_unavailable`, `panel_hint_unverified`, `panel_hint_ignored`, `measurement_disabled`, `measurement_pending`, `measurement_failed`, `measurement_stale`, `measurement_disagreement`, `multiple_public_ipv4_candidates`, `host_default_not_business_egress`, `candidates_truncated`. Интерфейс использует свои каталоги.

Аутентифицированный пустой, старый или неоднозначный результат — 200. Прямой отказ 401, подпись или nonce 403, неверное тело 400, старый Agent 501 `egress_info_unsupported`, недоступный VPC или неверные данные 502, сбой сбора 503. Ошибки не содержат исходных путей, данных панели, интерфейсов, тела измерения или секретов. Ответ использует `Cache-Control: no-store`, кеш только в памяти.

## Настройки Agent и ограничения

Необязательный `egress` содержит только эти ключи:

```json
{
  "panel_config_path": "",
  "measure_enabled": false,
  "measure_interval": 300
}
```

Панель по умолчанию не читается. Явно указанный обычный JSON должен принадлежать пользователю Agent, быть недоступен для записи группе и остальным и не быть символьной ссылкой в конечном компоненте. Лимит 64 КиБ. В конфигурации Xray от 3x-ui числовые IPv4 из `inbounds[].listen` и `outbounds[].sendThrough` считаются неподтверждёнными подсказками. Цели REALITY, внешние серверы, домены и секреты не ищутся и не разрешаются.

Для интерфейсов выполняется фиксированное `ip -j -4 address show` с лимитом 2 секунды и 64 КиБ. Кеш 15 секунд. Отсутствие инструмента и только непубличные/NAT адреса возвращают предупреждения.

Измерение по умолчанию выключено. Фоновый замер использует только фиксированный [IPv4 API ipify](https://api.ipify.org/). Запросы и конфигурация не принимают URL, команды, принудительное обновление и цель. DNS фильтруется до публичных IPv4, TLS подключается к выбранному IP с фиксированным именем для SNI и сертификата. Переменные прокси, редиректы, повторы и секреты не используются. Сокет ограничен 2 секундами, ответ 256 байтами, изолированный процесс 5 секундами вместе с DNS. Интервал 60–3600 секунд, по умолчанию 300. Чтение не запускает измерение. Результат маркируется как IPv4 маршрута хоста.

## Интеграция

`--check-config` проверяет `egress`. Установщик включает `egress.py`, жизненным циклом управляет `control.Server`. Мастер читает через настройки только подключения, даже при остановленной синхронизации. Сохраняются подтверждение адреса, секреты сеанса и права RPC. Чтение не фиксирует и не применяет политику, не ставит операции в очередь и не запускает измерение из RPC.

## Базовые изолированные тесты

Запускайте в своей тестовой ВМ для проверяемого снимка:

```sh
python3 -B companion/vps/test_egress.py
cd companion/worker
node --test test/egress.test.mjs test/worker.test.mjs test/regression.test.mjs test/contract.test.mjs
```

Сбор проверяется подставными измерениями без реальных запросов. HTTP использует настоящий Agent и временный драйвер правил в памяти. Реальный nftables не меняется. Установка, фактический прокси и развёртывание Cloudflare проверяются отдельно.
