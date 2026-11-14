# PGHB heartbeat and diagnostics

[English](PGHB.en.md) · [简体中文](PGHB.md) · [日本語](PGHB.ja.md) · [Русский](PGHB.ru.md) · [فارسی](PGHB.fa.md)

## Which endpoint should I use?

| Endpoint | Use |
| --- | --- |
| Official PGHB `https://hb.pghb.app/` | Lightweight connectivity check through the local SOCKS proxy. Optional exit IPv4 verification can use the same response. |
| Official PGHB `https://hb.pghb.app/f` | On-demand connection diagnostics. In LuCI, open **Test current proxy → Run detailed diagnostics**. The router’s **API refresh endpoint** setting also lets you select it for local API diagnostics. |
| Router `/cgi-bin/proxy-guard-api/*` | Authenticated LAN control. Read status, run diagnostics or request and cancel a timed block. Use the router’s HTTPS address and its API UUID. [Local API requests and responses](USAGE.en.md#local-api) |

**Test current proxy** uses the unsaved form settings. **Run detailed diagnostics** uses the applied proxy settings. A passing diagnostic confirms that particular request through SOCKS. Use the current protection status to check whether the router is allowing traffic.

## Validation in Proxy Guard 1.0

- PGHB must return HTTP `200` and the exact body `ネットは広大だわ`. It is 24 bytes of UTF-8, with no newline or BOM.
- For `/f`, Proxy Guard sends a fresh `X-PGHB-Nonce` and requires an identical echo for the diagnostic to pass. It sends its own diagnostic nonce. The router API UUID is used only on the router’s HTTPS API.
- The parser treats header names case-insensitively. Repeated `X-PGHB-IP` or `X-PGHB-Nonce` in a header block invalidate the response. Other repeated diagnostic headers are returned as separate records, and ambiguous optional summary fields are omitted.
- Proxy Guard reads up to **32 KiB (32,768 bytes)** of HTTP response headers. When capturing diagnostic headers, the serialized JSON header array must also fit within **32 KiB**. Both limits apply to the whole block or array, including its formatting.
- When exit IPv4 verification uses PGHB, `X-PGHB-IP` must supply the expected IPv4. Optional fields such as country, ASN and browser headers are diagnostic data. Missing optional fields do not count as a connection failure.

Diagnostic `X-PGHB-*` values are returned as strings in response order. Values outside UTF-8 carry `"encoding":"base64"`. Additional well-formed `X-PGHB-*` fields can appear in diagnostics without a plugin update. These details describe the plugin’s current use of PGHB.

## Detailed response fields

The `/f` configuration inventory lists **102 headers**. A response can contain fewer. Cloudflare can remove a header when its dynamic value is empty or undefined. Some numeric metrics yield `0` when unavailable. “Missing or unavailable” below describes when a value may be absent or has no diagnostic meaning. A dash means the field has no numeric unit. [Cloudflare response header rules](https://developers.cloudflare.com/rules/transform/response-header-modification/#important-remarks) · [Field reference](https://developers.cloudflare.com/ruleset-engine/rules-language/fields/reference/)

The lightweight `/` response uses the basic IP, country, ASN, TLS and Ray fields. Addresses reported by PGHB describe the request as seen by Cloudflare. For a request through SOCKS, those are observations of the proxy path.

Treat diagnostic output as sensitive when sharing it. It may include addresses, approximate location, TLS identifiers and fields echoed from the request, such as cookies, authorization or URL queries. [Privacy](PRIVACY.en.md)

### Connection, routing and TLS

| Header | Cloudflare expression or literal | Unit | Missing or unavailable | Used in validation |
| --- | --- | --- | --- | --- |
| `X-PGHB-IP` | `to_string(ip.src)` | — | An IPv6-only result cannot verify IPv4 | Optional exit IPv4 verification |
| `X-PGHB-Country` | `ip.src.country` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-ASN` | `to_string(ip.src.asnum)` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-City` | `ip.src.city` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Region` | `ip.src.region` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Region-Code` | `ip.src.region_code` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Continent` | `ip.src.continent` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Latitude` | `ip.src.lat` | degrees | IP geolocation or ASN unavailable | No |
| `X-PGHB-Longitude` | `ip.src.lon` | degrees | IP geolocation or ASN unavailable | No |
| `X-PGHB-Metro-Code` | `ip.src.metro_code` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Postal-Code` | `ip.src.postal_code` | — | IP geolocation or ASN unavailable | No |
| `X-PGHB-Client-Port` | `to_string(cf.edge.client_port)` | — | Transport details unavailable | No |
| `X-PGHB-Client-TCP` | `to_string(cf.edge.client_tcp)` | — | Transport details unavailable | No |
| `X-PGHB-Edge-IP` | `to_string(cf.edge.server_ip)` | — | Edge data unavailable | No |
| `X-PGHB-Edge-Port` | `to_string(cf.edge.server_port)` | — | Edge data unavailable | No |
| `X-PGHB-HTTP` | `http.request.version` | — | Usually present | No |
| `X-PGHB-SSL` | `to_string(ssl)` | — | Usually present | No |
| `X-PGHB-Delivery-Rate` | `to_string(cf.edge.l4.delivery_rate)` | B/s | L4 statistics unavailable → `0` | No |
| `X-PGHB-TCP-RTT` | `to_string(cf.timings.client_tcp_rtt_msec)` | ms | Non-TCP connection → `0` | No |
| `X-PGHB-QUIC-RTT` | `to_string(cf.timings.client_quic_rtt_msec)` | ms | Non-QUIC connection → `0` | No |
| `X-PGHB-Edge-Time` | `to_string(cf.timings.edge_msec)` | ms | Edge data unavailable | No |
| `X-PGHB-Origin-TTFB` | `to_string(cf.timings.origin_ttfb_msec)` | ms | Origin timing unavailable, such as a cache hit | No |
| `X-PGHB-Worker-Time` | `to_string(cf.timings.worker_msec)` | ms | Worker timing unavailable or no Worker execution | No |
| `X-PGHB-Ray` | `cf.ray_id` | — | Usually present | No |
| `X-PGHB-Zone` | `cf.zone.name` | — | Edge data unavailable | No |
| `X-PGHB-TLS` | `cf.tls_version` | — | TLS handshake data unavailable | No |
| `X-PGHB-Cipher` | `cf.tls_cipher` | — | TLS handshake data unavailable | No |
| `X-PGHB-TLS-Hello` | `to_string(cf.tls_client_hello_length)` | bytes | TLS handshake data unavailable | No |
| `X-PGHB-Ciphers-SHA1` | `cf.tls_client_ciphers_sha1` | — | TLS handshake data unavailable | No |
| `X-PGHB-TLS-Extensions` | `cf.tls_client_extensions_sha1` | — | TLS handshake data unavailable | No |
| `X-PGHB-Extensions-LE` | `cf.tls_client_extensions_sha1_le` | — | TLS handshake data unavailable | No |
| `X-PGHB-TLS-Client-Random` | `cf.tls_client_random` | — | TLS handshake data unavailable | No |
| `X-PGHB-MTLS-Presented` | `to_string(cf.tls_client_auth.cert_presented)` | — | No applicable mTLS → normally `false` | No |
| `X-PGHB-MTLS-Verified` | `to_string(cf.tls_client_auth.cert_verified)` | — | No applicable mTLS → normally `false` | No |

### Request information and echoes

| Header | Cloudflare expression or literal | Unit | Missing or unavailable | Used in validation |
| --- | --- | --- | --- | --- |
| `X-PGHB-Host` | `http.host` | — | Usually present | No |
| `X-PGHB-Method` | `http.request.method` | — | Usually present | No |
| `X-PGHB-Path` | `http.request.uri.path` | — | Usually present | No |
| `X-PGHB-URI` | `http.request.uri` | — | Usually present | No |
| `X-PGHB-Full-URI` | `http.request.full_uri` | — | Usually present | No |
| `X-PGHB-Raw-Path` | `raw.http.request.uri.path` | — | Usually present | No |
| `X-PGHB-Raw-URI` | `raw.http.request.uri` | — | Usually present | No |
| `X-PGHB-Raw-Full-URI` | `raw.http.request.full_uri` | — | Usually present | No |
| `X-PGHB-Query` | `http.request.uri.query` | — | No query string | No |
| `X-PGHB-Raw-Query` | `raw.http.request.uri.query` | — | No query string | No |
| `X-PGHB-URI-Extension` | `http.request.uri.path.extension` | — | No path extension | No |
| `X-PGHB-Timestamp` | `to_string(http.request.timestamp.sec)` | Unix seconds | Edge data unavailable | No |
| `X-PGHB-Received-MS` | `to_string(http.request.timestamp.msec)` | ms within second (0–999) | Edge data unavailable | No |
| `X-PGHB-Request-ID` | `uuidv4(cf.random_seed)` | — | Usually present | No |
| `X-PGHB-Headers-Truncated` | `to_string(http.request.headers.truncated)` | — | Usually present | No |
| `X-PGHB-Verified-Bot` | `to_string(cf.client.bot)` | — | Usually present | No |
| `X-PGHB-Verified-Bot-Category` | `cf.verified_bot_category` | — | Bot category unavailable | No |
| `X-PGHB-Nonce` | `http.request.headers["x-pghb-nonce"][0]` | — | Absent if the request sent no nonce | Nonce match for `/f` |
| `X-PGHB-Accept` | `http.request.headers["accept"][0]` | — | Input header or value absent | No |
| `X-PGHB-Accept-Encoding` | `http.request.headers["accept-encoding"][0]` | — | Input header or value absent | No |
| `X-PGHB-Accept-Language` | `http.request.headers["accept-language"][0]` | — | Input header or value absent | No |
| `X-PGHB-Authorization` | `http.request.headers["authorization"][0]` | — | Input header or value absent | No |
| `X-PGHB-Cookie` | `http.cookie` | — | Input header or value absent | No |
| `X-PGHB-User-Agent` | `http.user_agent` | — | Input header or value absent | No |
| `X-PGHB-Origin` | `http.request.headers["origin"][0]` | — | Input header or value absent | No |
| `X-PGHB-Referer` | `http.referer` | — | Input header or value absent | No |
| `X-PGHB-Range` | `http.request.headers["range"][0]` | — | Input header or value absent | No |
| `X-PGHB-DNT` | `http.request.headers["dnt"][0]` | — | Input header or value absent | No |
| `X-PGHB-GPC` | `http.request.headers["sec-gpc"][0]` | — | Input header or value absent | No |
| `X-PGHB-Save-Data` | `http.request.headers["save-data"][0]` | — | Input header or value absent | No |
| `X-PGHB-Upgrade-Insecure` | `http.request.headers["upgrade-insecure-requests"][0]` | — | Input header or value absent | No |
| `X-PGHB-Sec-Purpose` | `http.request.headers["sec-purpose"][0]` | — | Input header or value absent | No |
| `X-PGHB-Fetch-Dest` | `http.request.headers["sec-fetch-dest"][0]` | — | Input header or value absent | No |
| `X-PGHB-Fetch-Mode` | `http.request.headers["sec-fetch-mode"][0]` | — | Input header or value absent | No |
| `X-PGHB-Fetch-Site` | `http.request.headers["sec-fetch-site"][0]` | — | Input header or value absent | No |
| `X-PGHB-Fetch-User` | `http.request.headers["sec-fetch-user"][0]` | — | Input header or value absent | No |
| `X-PGHB-Client-Hints-UA` | `http.request.headers["sec-ch-ua"][0]` | — | Input header or value absent | No |
| `X-PGHB-Client-Hints-Mobile` | `http.request.headers["sec-ch-ua-mobile"][0]` | — | Input header or value absent | No |
| `X-PGHB-Client-Hints-Platform` | `http.request.headers["sec-ch-ua-platform"][0]` | — | Input header or value absent | No |
| `X-PGHB-UA-Arch` | `http.request.headers["sec-ch-ua-arch"][0]` | — | Input header or value absent | No |
| `X-PGHB-UA-Bitness` | `http.request.headers["sec-ch-ua-bitness"][0]` | — | Input header or value absent | No |
| `X-PGHB-UA-Full-Version-List` | `http.request.headers["sec-ch-ua-full-version-list"][0]` | — | Input header or value absent | No |
| `X-PGHB-UA-Platform-Version` | `http.request.headers["sec-ch-ua-platform-version"][0]` | — | Input header or value absent | No |
| `X-PGHB-Top-Language` | `http.request.accepted_languages[0]` | — | No accepted language available | No |
| `X-PGHB-If-Match` | `http.request.headers["if-match"][0]` | — | Input header or value absent | No |
| `X-PGHB-If-Modified-Since` | `http.request.headers["if-modified-since"][0]` | — | Input header or value absent | No |
| `X-PGHB-If-None-Match` | `http.request.headers["if-none-match"][0]` | — | Input header or value absent | No |
| `X-PGHB-If-Unmodified-Since` | `http.request.headers["if-unmodified-since"][0]` | — | Input header or value absent | No |
| `X-PGHB-Request-Cache-Control` | `http.request.headers["cache-control"][0]` | — | Input header or value absent | No |
| `X-PGHB-Request-Content-Length` | `http.request.headers["content-length"][0]` | bytes | Input header or value absent | No |
| `X-PGHB-Request-Content-Type` | `http.request.headers["content-type"][0]` | — | Input header or value absent | No |
| `X-PGHB-Request-Priority` | `http.request.headers["priority"][0]` | — | Input header or value absent | No |

### Response information and constants

| Header | Cloudflare expression or literal | Unit | Missing or unavailable | Used in validation |
| --- | --- | --- | --- | --- |
| `X-PGHB-Response-Code` | `to_string(http.response.code)` | — | Usually present | No |
| `X-PGHB-Response-Type` | `http.response.content_type.media_type` | — | Source response field absent | No |
| `X-PGHB-Response-Cache-Control` | `http.response.headers["cache-control"][0]` | — | Source response field absent | No |
| `X-PGHB-Response-Content-Length` | `http.response.headers["content-length"][0]` | bytes | Source response field absent | No |
| `X-PGHB-Response-Encoding` | `http.response.headers["content-encoding"][0]` | — | Source response field absent | No |
| `X-PGHB-Response-ETag` | `http.response.headers["etag"][0]` | — | Source response field absent | No |
| `X-PGHB-Response-Age` | `http.response.headers["age"][0]` | seconds | Source response field absent | No |
| `X-PGHB-Response-Last-Modified` | `http.response.headers["last-modified"][0]` | — | Source response field absent | No |
| `X-PGHB-Response-Location` | `http.response.headers["location"][0]` | — | Source response field absent | No |
| `X-PGHB-Response-Vary` | `http.response.headers["vary"][0]` | — | Source response field absent | No |
| `X-PGHB-Error-Code` | `to_string(cf.response.1xxx_code)` | — | No Cloudflare 1xxx error → `0` | No |
| `X-PGHB-Error-Type` | `cf.response.error_type` | — | No Cloudflare error type | No |
| `X-PGHB-Endpoint` | `full` | — | Static on `/f` | No |
| `X-PGHB-Heartbeat-Version` | `1` | — | Static on `/f` | No |
| `X-PGHB-Schema-Version` | `1` | — | Static on `/f` | No |
| `X-PGHB-Service` | `PGHB` | — | Static on `/f` | No |

The two fields marked as used in validation have distinct roles. The duplicate-header rule above applies to both regardless of their values. The actual HTTP status is checked independently of the diagnostic `X-PGHB-Response-Code` string.

TCP and QUIC RTT describe the connection to Cloudflare, while `milliseconds` in the router API describes the probe from the router. Combine `Timestamp` (seconds) and `Received-MS` (milliseconds within that second) for Cloudflare’s request time. `Edge-IP` belongs to Cloudflare and `IP` is the observed source address.

[User guide](USER-GUIDE.en.md) · [Local API](USAGE.en.md#local-api) · [Response parser](../package/root/usr/lib/proxy-guard/public-heartbeat.lua#L45-L95)
