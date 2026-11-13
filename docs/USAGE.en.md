# Installation and use

[English](USAGE.en.md) · [简体中文](USAGE.md) · [日本語](USAGE.ja.md) · [Русский](USAGE.ru.md) · [فارسی](USAGE.fa.md)

Install Proxy Guard on a router that uses LuCI and firewall4/nftables. Choose the package format used by your firmware.

## Download and verify

Download the package and its checksum file from the same release. Use the IPK on opkg firmware or the APK on apk firmware. Check that your chosen filename prints OK. Install dependencies from feeds that match your firmware.

[GitHub Releases](https://github.com/beezcheyenna/Proxy-Guard/releases)

Use the filename you downloaded. The first line below selects IPK. For APK, use the filename in the following commented line.

```sh
PG_PACKAGE=luci-app-proxy-guard_1.0.0-8_all.ipk
# PG_PACKAGE=luci-app-proxy-guard-1.0.0-r8.apk
awk -v f="$PG_PACKAGE" '$2 == f { print; n++ } END { if (n != 1) exit 1 }' SHA256SUMS > SHA256SUMS.selected &&
sha256sum -c SHA256SUMS.selected
```

The check must report OK for that package. On macOS you can run `shasum -a 256 "$PG_PACKAGE"` and compare the full digest with the matching entry in `SHA256SUMS`.

SHA256 checks file integrity against this list. Verify the publisher separately and get the list and the package from the same trusted release. On apk firmware, install the matching dependencies first when working offline.

<a id="installation"></a>

## Install and remove

Run the command for your firmware. To remove the application, use the corresponding remove command. Keep a separate management connection available while testing protection.

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="guide-setup"></a>

## First configuration

Open Services → Proxy Guard. Use the wizard to review ingress devices, the IPv4 and IPv6 scope, local exceptions, and your SOCKS port. Enable Monitor only first. Save & Apply runs a self-check and opens a 30-second confirmation window. A failed or unconfirmed change rolls back.

Official HTTPS is selected by default and uses a fixed address through local SOCKS. Third-party HTTPS is selectable and has independent timing and thresholds. Exit IPv4 verification is off initially. When enabled, the official response supplies the IPv4 by default. A third-party IP lookup retries its backup only after the primary times out.

Official HTTPS defaults to a 3-second interval, a 2-second timeout, two consecutive failures and two consecutive successes. Third-party HTTPS defaults to a 10-second interval and a 4-second timeout per target, with three failed rounds and two successful rounds. It uses gstatic and Ubuntu by default, with at least one website succeeding in an ordinary round.

Two text-IP timeouts can leave access available while the connectivity checks pass. A previously observed mismatch still needs a matching IPv4 to recover.

When the rules still need verification, **Keep these settings** is temporarily disabled. The original countdown continues. If the timer expires, the router restores the previous settings even if the page has been closed.

<a id="test-current-proxy"></a>

## Test current proxy

In LuCI, Test current proxy uses the unsaved form settings through SOCKS. It reports the result, latency and available exit IPv4. Only Save & Apply changes configuration and enforcement.

The status shows consecutive failed checks and all applicable blocking reasons. A single failed sample below the configured threshold can still leave access available. Scheduled blocks, API requests and failed health checks can overlap.

The optional local API is off on a clean install. Enable it to query status, run diagnostics, or start and cancel timed blocks using the UUID displayed in LuCI.

## Test startup protection

Keep an independent management path available. Restart the router running Proxy Guard. From a protected client, verify that Internet traffic stays blocked during router startup and resumes only after the configured recovery checks pass.

<a id="local-api"></a>

## Local API

Enable **Local control API** in LuCI, click **Save & Apply**, and confirm the settings if prompted. Copy the **API UUID** displayed in the same tab. The UUID serves as the credential for all four endpoints. Turning the API off and on generates a new UUID.

Send requests to the router’s existing management HTTPS address from the LAN. Use **API refresh endpoint** in LuCI to choose the standard heartbeat or detailed diagnostics `/f`.

| Method | Path after `/cgi-bin/proxy-guard-api` | Purpose |
| --- | --- | --- |
| GET | `/status` | Read protection status and active API blocks |
| GET | `/diagnostics` | Run the selected heartbeat check through SOCKS and return its result |
| POST | `/block` | Start a timed Internet block |
| POST | `/cancel` | Cancel a timed block by request ID |

Replace `router.example` with your router’s HTTPS management address and `YOUR_UUID` with the UUID shown in LuCI.

```http
GET /cgi-bin/proxy-guard-api/diagnostics HTTP/1.1
Host: router.example
Authorization: Bearer YOUR_UUID
```

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

Both POST endpoints accept `Content-Type: application/json`. Use `{"seconds":120,"request_id":"sample-block-01"}` for `/block` and `{"request_id":"sample-block-01"}` for `/cancel`. An omitted or zero duration uses the configured default. The router generates a request ID when omitted. Blocks require active protection mode. Reusing a live request ID with the same duration leaves the original expiry intact. Other active protection reasons continue to apply after cancellation.

Authenticated responses include `uuid`. Successful diagnostics include `diagnostics.headers`, an ordered list of `name` and `value` pairs for `X-PGHB-*` headers. Duplicate headers and string values are preserved. Non-UTF-8 values use `encoding: "base64"`. HTTP 401 indicates a missing or invalid UUID, 403 indicates a disabled or unavailable endpoint from the current network, 429 indicates a cooldown or request limit, and 502/504 indicate a failed or timed-out heartbeat check.

Authenticated requests appear with their UUID in the LuCI event log for users with plugin configuration permissions. Treat the UUID and those log entries as credentials when sharing diagnostics.

[User guide](USER-GUIDE.en.md) · [Recovery](RECOVERY.en.md)
