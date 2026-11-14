# Сигнал PGHB и диагностика

[English](PGHB.en.md) · [简体中文](PGHB.md) · [日本語](PGHB.ja.md) · [Русский](PGHB.ru.md) · [فارسی](PGHB.fa.md)

## Какую точку доступа использовать

| Точка доступа | Назначение |
| --- | --- |
| Официальная PGHB `https://hb.pghb.app/` | Короткая проверка связи через локальный SOCKS. Тот же ответ можно использовать для сверки выходного IPv4. |
| Официальная PGHB `https://hb.pghb.app/f` | Подробная диагностика по запросу. В LuCI откройте «Проверить текущий прокси» и запустите подробную диагностику. Этот адрес можно выбрать и для диагностики через API роутера. |
| `/cgi-bin/proxy-guard-api/*` на роутере | Локальный API с аутентификацией. Позволяет читать состояние, запускать диагностику, создавать и отменять временную блокировку. Используйте HTTPS-адрес роутера и UUID его API. [Запросы и ответы API](USAGE.ru.md#local-api) |

«Проверить текущий прокси» использует несохранённые настройки формы. «Запустить подробную диагностику» использует уже применённые настройки прокси. Успех диагностики подтверждает прохождение конкретного запроса через SOCKS. Фактический доступ проверяйте по текущему состоянию защиты.

## Правила проверки в Proxy Guard 1.0

- PGHB должен вернуть HTTP `200` и тело, в точности совпадающее с `ネットは広大だわ`. Это 24 байта UTF-8 без перевода строки и BOM.
- Для `/f` Proxy Guard отправляет новый `X-PGHB-Nonce` и считает диагностику успешной только при совпадении значения в ответе. Одноразовое значение диагностики генерируется отдельно. UUID API отправляется только в HTTPS API роутера.
- Регистр в именах заголовков не важен. Повтор `X-PGHB-IP` или `X-PGHB-Nonce` в одном блоке заголовков приводит к ошибке проверки. Другие повторы могут передаваться отдельными записями. Неоднозначные дополнительные поля сводки пропускаются.
- Лимит чтения блока HTTP-заголовков составляет **32 КиБ (32 768 байт)**. В режиме диагностики массив заголовков в формате JSON также должен занимать не более **32 КиБ**. В обоих случаях учитывается весь блок или массив с оформлением.
- Для включённой сверки IPv4 через PGHB поле `X-PGHB-IP` должно содержать ожидаемый IPv4. Страна, ASN и заголовки браузера служат для диагностики. Их отсутствие само по себе не означает сбой связи.

Значения `X-PGHB-*` в диагностике возвращаются строками в порядке ответа. Для данных вне UTF-8 добавляется `"encoding":"base64"`. Новые корректные заголовки `X-PGHB-*` могут появляться без обновления плагина. Здесь описано текущее использование PGHB плагином.

## Поля подробного ответа

В списке настроек `/f` **102 заголовка**. В отдельном ответе их может быть меньше. Cloudflare может убрать динамический заголовок с пустым или неопределённым значением. Некоторые недоступные измерения возвращают `0`. Столбец «Отсутствие данных» описывает условия, в которых поле может быть пропущено или бесполезно для диагностики. Тире обозначает отсутствие единицы измерения. [Правила заголовков Cloudflare](https://developers.cloudflare.com/rules/transform/response-header-modification/#important-remarks) · [Справочник полей](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/)

Краткий ответ `/` использует пять основных полей: IP, код страны или региона, ASN, TLS и Ray. IP относится к источнику, наблюдаемому Cloudflare. Для запроса через SOCKS он отражает выход прокси.

Перед публикацией уберите конфиденциальные сведения из результата. В нём могут быть адреса, приблизительное местоположение, идентификаторы TLS и данные из запроса, например Cookie, Authorization или параметры URL. [Конфиденциальность](PRIVACY.ru.md)

### Соединение, маршрут и TLS

| Заголовок | Выражение Cloudflare или константа | Единица | Отсутствие данных | Участие в проверке |
| --- | --- | --- | --- | --- |
| `X-PGHB-IP` | `to_string(ip.src)` | — | Ответ только с IPv6 не позволяет сверить IPv4 | Необязательная сверка выходного IPv4 |
| `X-PGHB-Country` | `ip.src.country` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-ASN` | `to_string(ip.src.asnum)` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-City` | `ip.src.city` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Region` | `ip.src.region` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Region-Code` | `ip.src.region_code` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Continent` | `ip.src.continent` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Latitude` | `ip.src.lat` | градусы | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Longitude` | `ip.src.lon` | градусы | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Metro-Code` | `ip.src.metro_code` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Postal-Code` | `ip.src.postal_code` | — | Нет геоданных IP или ASN | Нет |
| `X-PGHB-Client-Port` | `to_string(cf.edge.client_port)` | — | Нет данных транспорта | Нет |
| `X-PGHB-Client-TCP` | `to_string(cf.edge.client_tcp)` | — | Нет данных транспорта | Нет |
| `X-PGHB-Edge-IP` | `to_string(cf.edge.server_ip)` | — | Нет данных пограничного узла | Нет |
| `X-PGHB-Edge-Port` | `to_string(cf.edge.server_port)` | — | Нет данных пограничного узла | Нет |
| `X-PGHB-HTTP` | `http.request.version` | — | Обычно заполнен | Нет |
| `X-PGHB-SSL` | `to_string(ssl)` | — | Обычно заполнен | Нет |
| `X-PGHB-Delivery-Rate` | `to_string(cf.edge.l4.delivery_rate)` | байт/с | Без статистики L4 возвращается `0` | Нет |
| `X-PGHB-TCP-RTT` | `to_string(cf.timings.client_tcp_rtt_msec)` | мс | Для соединений без TCP возвращается `0` | Нет |
| `X-PGHB-QUIC-RTT` | `to_string(cf.timings.client_quic_rtt_msec)` | мс | Для соединений без QUIC возвращается `0` | Нет |
| `X-PGHB-Edge-Time` | `to_string(cf.timings.edge_msec)` | мс | Нет данных пограничного узла | Нет |
| `X-PGHB-Origin-TTFB` | `to_string(cf.timings.origin_ttfb_msec)` | мс | Нет замера до исходного сервера, например при попадании в кэш | Нет |
| `X-PGHB-Worker-Time` | `to_string(cf.timings.worker_msec)` | мс | Нет выполнения Worker или его замера | Нет |
| `X-PGHB-Ray` | `cf.ray_id` | — | Обычно заполнен | Нет |
| `X-PGHB-Zone` | `cf.zone.name` | — | Нет данных пограничного узла | Нет |
| `X-PGHB-TLS` | `cf.tls_version` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-Cipher` | `cf.tls_cipher` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-TLS-Hello` | `to_string(cf.tls_client_hello_length)` | байты | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-Ciphers-SHA1` | `cf.tls_client_ciphers_sha1` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-TLS-Extensions` | `cf.tls_client_extensions_sha1` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-Extensions-LE` | `cf.tls_client_extensions_sha1_le` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-TLS-Client-Random` | `cf.tls_client_random` | — | Нет данных рукопожатия TLS | Нет |
| `X-PGHB-MTLS-Presented` | `to_string(cf.tls_client_auth.cert_presented)` | — | Без mTLS обычно `false` | Нет |
| `X-PGHB-MTLS-Verified` | `to_string(cf.tls_client_auth.cert_verified)` | — | Без mTLS обычно `false` | Нет |

### Информация запроса и отражённые значения

| Заголовок | Выражение Cloudflare или константа | Единица | Отсутствие данных | Участие в проверке |
| --- | --- | --- | --- | --- |
| `X-PGHB-Host` | `http.host` | — | Обычно заполнен | Нет |
| `X-PGHB-Method` | `http.request.method` | — | Обычно заполнен | Нет |
| `X-PGHB-Path` | `http.request.uri.path` | — | Обычно заполнен | Нет |
| `X-PGHB-URI` | `http.request.uri` | — | Обычно заполнен | Нет |
| `X-PGHB-Full-URI` | `http.request.full_uri` | — | Обычно заполнен | Нет |
| `X-PGHB-Raw-Path` | `raw.http.request.uri.path` | — | Обычно заполнен | Нет |
| `X-PGHB-Raw-URI` | `raw.http.request.uri` | — | Обычно заполнен | Нет |
| `X-PGHB-Raw-Full-URI` | `raw.http.request.full_uri` | — | Обычно заполнен | Нет |
| `X-PGHB-Query` | `http.request.uri.query` | — | Нет строки запроса | Нет |
| `X-PGHB-Raw-Query` | `raw.http.request.uri.query` | — | Нет строки запроса | Нет |
| `X-PGHB-URI-Extension` | `http.request.uri.path.extension` | — | У пути нет расширения | Нет |
| `X-PGHB-Timestamp` | `to_string(http.request.timestamp.sec)` | секунды Unix | Нет данных пограничного узла | Нет |
| `X-PGHB-Received-MS` | `to_string(http.request.timestamp.msec)` | мс внутри секунды (0–999) | Нет данных пограничного узла | Нет |
| `X-PGHB-Request-ID` | `uuidv4(cf.random_seed)` | — | Обычно заполнен | Нет |
| `X-PGHB-Headers-Truncated` | `to_string(http.request.headers.truncated)` | — | Обычно заполнен | Нет |
| `X-PGHB-Verified-Bot` | `to_string(cf.client.bot)` | — | Обычно заполнен | Нет |
| `X-PGHB-Verified-Bot-Category` | `cf.verified_bot_category` | — | Категория бота недоступна | Нет |
| `X-PGHB-Nonce` | `http.request.headers["x-pghb-nonce"][0]` | — | Нет Nonce в запросе | Сверка Nonce для `/f` |
| `X-PGHB-Accept` | `http.request.headers["accept"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Accept-Encoding` | `http.request.headers["accept-encoding"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Accept-Language` | `http.request.headers["accept-language"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Authorization` | `http.request.headers["authorization"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Cookie` | `http.cookie` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-User-Agent` | `http.user_agent` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Origin` | `http.request.headers["origin"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Referer` | `http.referer` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Range` | `http.request.headers["range"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-DNT` | `http.request.headers["dnt"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-GPC` | `http.request.headers["sec-gpc"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Save-Data` | `http.request.headers["save-data"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Upgrade-Insecure` | `http.request.headers["upgrade-insecure-requests"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Sec-Purpose` | `http.request.headers["sec-purpose"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Fetch-Dest` | `http.request.headers["sec-fetch-dest"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Fetch-Mode` | `http.request.headers["sec-fetch-mode"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Fetch-Site` | `http.request.headers["sec-fetch-site"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Fetch-User` | `http.request.headers["sec-fetch-user"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Client-Hints-UA` | `http.request.headers["sec-ch-ua"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Client-Hints-Mobile` | `http.request.headers["sec-ch-ua-mobile"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Client-Hints-Platform` | `http.request.headers["sec-ch-ua-platform"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-UA-Arch` | `http.request.headers["sec-ch-ua-arch"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-UA-Bitness` | `http.request.headers["sec-ch-ua-bitness"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-UA-Full-Version-List` | `http.request.headers["sec-ch-ua-full-version-list"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-UA-Platform-Version` | `http.request.headers["sec-ch-ua-platform-version"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Top-Language` | `http.request.accepted_languages[0]` | — | Предпочтительный язык недоступен | Нет |
| `X-PGHB-If-Match` | `http.request.headers["if-match"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-If-Modified-Since` | `http.request.headers["if-modified-since"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-If-None-Match` | `http.request.headers["if-none-match"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-If-Unmodified-Since` | `http.request.headers["if-unmodified-since"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Request-Cache-Control` | `http.request.headers["cache-control"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Request-Content-Length` | `http.request.headers["content-length"][0]` | байты | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Request-Content-Type` | `http.request.headers["content-type"][0]` | — | В запросе нет заголовка или значения | Нет |
| `X-PGHB-Request-Priority` | `http.request.headers["priority"][0]` | — | В запросе нет заголовка или значения | Нет |

### Данные ответа и константы

| Заголовок | Выражение Cloudflare или константа | Единица | Отсутствие данных | Участие в проверке |
| --- | --- | --- | --- | --- |
| `X-PGHB-Response-Code` | `to_string(http.response.code)` | — | Обычно заполнен | Нет |
| `X-PGHB-Response-Type` | `http.response.content_type.media_type` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Cache-Control` | `http.response.headers["cache-control"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Content-Length` | `http.response.headers["content-length"][0]` | байты | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Encoding` | `http.response.headers["content-encoding"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-ETag` | `http.response.headers["etag"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Age` | `http.response.headers["age"][0]` | секунды | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Last-Modified` | `http.response.headers["last-modified"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Location` | `http.response.headers["location"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Response-Vary` | `http.response.headers["vary"][0]` | — | Нет исходного поля ответа | Нет |
| `X-PGHB-Error-Code` | `to_string(cf.response.1xxx_code)` | — | Без ошибки Cloudflare 1xxx возвращается `0` | Нет |
| `X-PGHB-Error-Type` | `cf.response.error_type` | — | Нет типа ошибки Cloudflare | Нет |
| `X-PGHB-Endpoint` | `full` | — | Константа `/f` | Нет |
| `X-PGHB-Heartbeat-Version` | `1` | — | Константа `/f` | Нет |
| `X-PGHB-Schema-Version` | `1` | — | Константа `/f` | Нет |
| `X-PGHB-Service` | `PGHB` | — | Константа `/f` | Нет |

Два поля, участвующие в проверке, имеют разные роли. Правило об отклонении повторов действует для обоих. Фактический HTTP-статус проверяется отдельно, а строка `X-PGHB-Response-Code` служит диагностической подсказкой.

TCP и QUIC RTT характеризуют соединение до Cloudflare, а `milliseconds` в API роутера измеряет время проверки с роутера. Время получения запроса Cloudflare состоит из `Timestamp` в секундах и `Received-MS` в миллисекундах внутри секунды. `Edge-IP` относится к узлу Cloudflare, а `IP` содержит наблюдаемый адрес источника.

[Руководство пользователя](USER-GUIDE.ru.md) · [Локальный API](USAGE.ru.md#local-api) · [Код разбора ответа](../package/root/usr/lib/proxy-guard/public-heartbeat.lua#L45-L95)
