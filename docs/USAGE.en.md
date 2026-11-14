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

Run the command for your firmware. The APK example uses `--no-network` for offline installation, so dependencies must already be installed or available in a local repository. To resolve missing dependencies online from the configured feeds for your firmware, omit `--no-network`. Keep a separate management connection available while testing protection.

```sh
opkg install /tmp/luci-app-proxy-guard_1.0.0-8_all.ipk
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-1.0.0-r8.apk
```

```sh
opkg remove luci-app-proxy-guard
apk --no-network del luci-app-proxy-guard
```

<a id="from-0-3"></a>

## Moving from 0.3 to 1.0

Start with a clean 1.0 configuration. Upgrading in place from the published 0.3 packages and downgrading from 1.0 to 0.3 have not been validated as supported migration paths. Both router packages declare `/etc/config/proxy_guard` as a configuration file, so the package manager may retain a modified 0.3 file. The installer can normalize known old probe defaults and fill some missing options. Review any retained settings before using them with 1.0.

Keep an independent management path. Back up the 0.3 configuration and privately retain the credentials and matching packages if you need to restore the old setup. Disable the old router protection. If 0.3 Pro is installed, handle the VPS policy as described below before removing Pro. Remove 0.3 Standard before installing 1.0. If old settings remain, open **Configuration and diagnostics → Restore defaults and set up again**. Re-enter only the scope, exceptions, SOCKS settings and schedules you have reviewed.

A clean 1.0 configuration selects official HTTPS and leaves exit IPv4 verification off. If a retained file has no connection check mode, 1.0 uses official HTTPS. Select third-party HTTPS in Connection checks if you want to keep the old gstatic and Ubuntu targets.

If Pro manages a VPS, withdraw any policy you intend to remove through 0.3 Pro while you still have control, and verify the result from the VPS. The 1.0 package has no built-in 0.3 Pro integration. Existing VPS rules, the Agent and Cloudflare resources require separate handling using the [archived recovery guide](https://github.com/beezcheyenna/Proxy-Guard/blob/987ff38a25c1a00f2c05753f7503e134391a4a3a/docs/RECOVERY.en.md).

[0.3 source, packages and documentation](../archive/0.3/README.md)


<a id="guide-setup"></a>

## First configuration

**Stopping the Proxy Guard service can leave its firewall rules blocking traffic.** To release the block, explicitly disable protection or follow the [recovery procedure](RECOVERY.en.md).

**A passing “Test current proxy” result confirms the test traffic only.** A schedule, API request or separate failed health check can still keep protection blocking.

Open Services → Proxy Guard. Use the wizard to review ingress devices, the IPv4 and IPv6 scope, local exceptions, and your SOCKS port. Enable Monitor only first. Save & Apply runs a self-check and opens a 30-second confirmation window. A failed or unconfirmed change rolls back.

Official HTTPS is selected by default and uses a fixed address through local SOCKS. Third-party HTTPS is selectable and has independent timing and thresholds. Exit IPv4 verification is off initially. When enabled, the official response supplies the IPv4 by default. A third-party IP lookup retries its backup only after the primary times out.

Official HTTPS waits 3 seconds after each completed check by default, with a 2-second request timeout. Third-party HTTPS waits 10 seconds after a round, with a 4-second timeout per target. It uses gstatic and Ubuntu by default, with at least one website succeeding in an ordinary round. In protection mode, ordinary checks confirm failure after two consecutive official checks fail or three consecutive third-party rounds fail. Both modes require two consecutive successes for recovery by default. A single failure can trigger blocking during sensitive monitoring.

When both third-party text-IP lookups time out, the lookup alone does not trigger blocking if connectivity checks pass and no IP mismatch remains unresolved. The default primary `https://api.ipify.org/` falls back to `https://4.ident.me/` on timeout. If a custom primary has no backup, a timeout counts as verification unavailable and follows the configured mode and failure threshold. A previously observed mismatch still needs a matching IPv4 to recover.

When the rules still need verification, **Keep these settings** is temporarily disabled. The original countdown continues. If the timer expires, the router restores the previous settings even if the page has been closed.

<a id="test-current-proxy"></a>

## Test current proxy

In LuCI, **Test current proxy** uses the unsaved form settings through SOCKS. It reports the result, latency and available exit IPv4. **Run detailed diagnostics** in the same dialog uses the applied proxy settings. Use **Save & Apply** to put settings into effect.

The status shows consecutive failed checks and all applicable blocking reasons. A single failed sample below the configured threshold can still leave access available. Scheduled blocks, API requests and failed health checks can overlap.

The optional local API is off on a clean install. Enable it to query status, run diagnostics, or start and cancel timed blocks using the UUID displayed in LuCI.

## Test startup protection

Keep an independent management path available. Restart the router running Proxy Guard. From a protected client, verify that Internet traffic stays blocked during router startup and resumes only after the configured recovery checks pass.

<a id="local-api"></a>

## Local API

In LuCI, enable **Local control API**, click **Save & Apply**, and confirm if prompted. Copy the **API UUID** shown in the same tab. Send it as `Authorization: Bearer YOUR_UUID` with every request.

**The UUID is an access credential.** Turning the API off and back on, or rebooting the router while it is enabled, generates a new UUID. Update callers with the new value. Requests use the API UUID without a LuCI login. Responses to accepted requests echo it. Administrators can also see it in the LuCI event log. Redact it before sharing responses or logs.

**Use the router’s existing management HTTPS address.** The API allows loopback or a peer with a directly connected return route through a device in the firewall zone named `lan`. Sources reached through another gateway are rejected. Other LAN zones, routed VLANs and VPN clients may receive `403 lan_required`. Use a hostname covered by the router certificate. For a private CA or a self-signed router certificate, supply the trusted CA or certificate with curl’s `--cacert` option.

Replace `router.example` with the router’s HTTPS hostname and `YOUR_UUID` with its current API UUID. The JSON below shows example responses with placeholder values. Call the POST endpoints only when you intend to change Internet access for the configured protection scope.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | [`/status`](#api-status) | Read protection status |
| GET | [`/diagnostics`](#api-diagnostics) | Run a one-time check |
| POST | [`/block`](#api-block) | Start a timed Internet block |
| POST | [`/cancel`](#api-cancel) | Cancel a timed block |

<a id="api-status"></a>

### Read the protection status

`GET /status` reads live enforcement and existing API block requests. The example shows a timed block already active. Use `enforcement` and `block_reasons` in programs. `reason` is display text. `last_check` is the last completed check time in Unix seconds and may be absent if no check is recorded. `blocked` may also be absent when enforcement is unknown, missing or unverified. Read `enforcement` to distinguish these states.

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/status'
```

HTTP 200

```json
{
  "ok": true,
  "api_version": 2,
  "uuid": "YOUR_UUID",
  "enabled": true,
  "mode": "guard",
  "check_mode": "web",
  "phase": "blocked",
  "enforcement": "blocked",
  "blocked": true,
  "reason": "API 限时断网生效中",
  "block_reasons": [
    "api"
  ],
  "failure_progress": {
    "count": 0,
    "threshold": 3
  },
  "last_check": 1794628800,
  "stale": false,
  "heartbeat": {
    "enabled": false,
    "allowed": true
  },
  "api": {
    "enabled": true,
    "count": 1,
    "remaining": 95
  },
  "requests": [
    {
      "request_id": "example-block-01",
      "remaining": 95
    }
  ],
  "default_seconds": 300,
  "max_seconds": 3600,
  "exit_check": {
    "enabled": false
  }
}
```

<a id="api-diagnostics"></a>

### Run diagnostics

`GET /diagnostics` makes an on-demand request through local SOCKS and returns its result in the same response. **API refresh endpoint** defaults to PGHB `/`. To get the detailed headers in the example, select `/f` and apply the setting first. [PGHB response reference](PGHB.en.md)

```sh
curl -H 'Authorization: Bearer YOUR_UUID' 'https://router.example/cgi-bin/proxy-guard-api/diagnostics'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "diagnostics": {
    "ok": true,
    "source": "https://hb.pghb.app/f",
    "checked_at": 1794628800,
    "http_code": 200,
    "curl_code": 0,
    "milliseconds": 117,
    "nonce_verified": true,
    "headers": [
      {
        "name": "x-pghb-ip",
        "value": "203.0.113.10"
      },
      {
        "name": "x-pghb-tls",
        "value": "TLSv1.3"
      },
      {
        "name": "x-pghb-nonce",
        "value": "0123456789abcdef0123456789abcdef"
      }
    ]
  }
}
```

`diagnostics.headers` lists `X-PGHB-*` names and values in response order as strings. Repeated `X-PGHB-IP` or `X-PGHB-Nonce` headers fail validation. Other repeated headers can appear as separate entries. Non-UTF-8 values include `"encoding":"base64"`. `checked_at` is a Unix timestamp in seconds.

<a id="api-block"></a>

### Start a timed block

`POST /block` requires active protection mode. The block applies to the configured protection scope. The default is 300 seconds and the initial maximum is 3,600 seconds. Omit `seconds` or use `0` for the configured default. The router generates an ID if you omit `request_id`. A supplied ID must be 8–64 characters using letters, digits, hyphens or underscores. Retrying an active ID with the same duration keeps its original expiry. A different duration returns `409 request_conflict`.

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"seconds":120,"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/block'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "effective": true,
  "remaining": 120,
  "seconds": 120
}
```

<a id="api-cancel"></a>

### Cancel a timed block

`POST /cancel` requires the request ID. Request ownership is the authenticated UUID plus the ID. Devices or programs using the same UUID share one identity. The API can return `cancelled: true` for a valid ID that has already expired or has no matching request. `effective` and `remaining` describe any API block still active. Scheduled blocks and failed health checks can still block traffic.

```sh
curl -H 'Authorization: Bearer YOUR_UUID' \
  -H 'Content-Type: application/json' \
  --data '{"request_id":"example-block-01"}' \
  'https://router.example/cgi-bin/proxy-guard-api/cancel'
```

HTTP 200

```json
{
  "ok": true,
  "uuid": "YOUR_UUID",
  "request_id": "example-block-01",
  "cancelled": true,
  "effective": false,
  "remaining": 0
}
```

### Common errors

| HTTP status and error | What to check |
| --- | --- |
| 401 `authentication_required` | The UUID is missing or invalid. Check the value shown in LuCI. |
| 403 `https_required`, `api_disabled` or `lan_required` | Check HTTPS, the API switch or the peer’s route into the `lan` firewall zone. |
| 409 `configuration_pending`, `configuration_changed`, `protection_not_active` or `request_conflict` | Confirm settings before retrying a diagnostic, verify protection mode for timed blocks, or use an ID with a matching duration. |
| 429 | A diagnostic cooldown or active-request limit applies. Respect `Retry-After` when present. |
| 502 / 504 | The diagnostic request failed or timed out. Consult `diagnostics` for details when present. |
| 503 `busy` | Another operation is in progress. Wait the number of seconds in `Retry-After` before retrying. |
| 503 `policy_not_ready`, `request_state_unavailable` or `firewall_failed` | The firewall policy is not ready, request state is unavailable, or a rule update failed. Check protection status and the event log before retrying the same request ID. |

[User guide](USER-GUIDE.en.md) · [Recovery](RECOVERY.en.md)
