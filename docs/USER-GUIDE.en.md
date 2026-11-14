# User guide

[English](USER-GUIDE.en.md) · [简体中文](USER-GUIDE.md) · [日本語](USER-GUIDE.ja.md) · [Русский](USER-GUIDE.ru.md) · [فارسی](USER-GUIDE.fa.md)

<a id="guide-editions"></a>

See the [GitHub releases](https://github.com/beezcheyenna/Proxy-Guard/releases) for the current version.

<a id="guide-setup"></a>

Install Proxy Guard on a router that uses LuCI and firewall4/nftables. Choose the package format used by your firmware.

## First configuration

**Stopping the Proxy Guard service can leave its firewall rules blocking traffic.** To release the block, explicitly disable protection or follow the [recovery procedure](RECOVERY.en.md).

**A passing “Test current proxy” result confirms the test traffic only.** A schedule, API request or separate failed health check can still keep protection blocking.

Open Services → Proxy Guard. Use the wizard to review ingress devices, the IPv4 and IPv6 scope, local exceptions, and your SOCKS port. Enable Monitor only first. Save & Apply runs a self-check and opens a 30-second confirmation window. A failed or unconfirmed change rolls back.

When the rules still need verification, **Keep these settings** is temporarily disabled. The original countdown continues. If the timer expires, the router restores the previous settings even if the page has been closed.

<a id="guide-requirements"></a>

## System requirements and scope

Use firewall4 and nftables with LuCI. OpenWrt 24 uses IPK and OpenWrt 25.12 uses APK. For iStoreOS and ImmortalWrt, match the firmware’s package manager and kernel dependencies.

<a id="guide-scope"></a>

Only traffic that actually crosses the router can be protected. Verify your selected ingress, IPv4 and IPv6 paths, DNS and management access on one client before expanding the scope. Same-subnet routing may return directly around the router.

## Protection modes

- **Monitor only** records problems and leaves Internet access available.
- **Protect** blocks Internet traffic for the selected scope after confirmed failure. Enable the startup protection preset if the scope should remain blocked while the router is starting.
- **Scheduled protection** can block access every day or on selected weekdays. The schedule uses a fixed UTC offset, initially UTC+00:00.

The service and log monitor can detect a client restart and start recovery checks. The watchdog supervises Proxy Guard itself. Enable the optional UDP path check if you need a separate UDP health signal.

<a id="advanced-settings"></a>

## Test current proxy

| Setting | What it controls |
| --- | --- |
| Connection check mode | Uses the fixed official HTTPS heartbeat by default or the configured third-party HTTPS targets. Both use local SOCKS. |
| Exit IPv4 verification and source | Off by default. When enabled, the official PGHB response supplies the address by default, even with third-party HTTPS checks selected. A third-party IP lookup uses its backup only after the primary times out. |
| Detailed diagnostics | An on-demand request to PGHB `/f` from LuCI. The local API diagnostics endpoint uses PGHB `/` by default and can be set to `/f`. |

In LuCI, Test current proxy uses the unsaved form settings through SOCKS. It reports the result, latency and available exit IPv4. Only Save & Apply changes configuration and enforcement.

Below the settings, open **Configuration and diagnostics** to check the settings and runtime environment, test the current proxy or view a sanitized report. You can also rerun the setup wizard, edit raw UCI, load the last confirmed settings or start over with defaults.

Under **Configuration and diagnostics**, open **Test current proxy**, then click **Run detailed diagnostics**. This action uses the applied proxy settings to send one `/f` request through local SOCKS and display the `X-PGHB-*` response headers. [PGHB heartbeat and diagnostics](PGHB.en.md)

<a id="guide-options"></a>

## Detection and recovery settings

| Parameter | Official HTTPS | Third-party HTTPS | Effect and trade-off |
| --- | --- | --- | --- |
| Interval | 3 s | 10 s | Wait after a request or round. Shorter intervals increase request frequency. |
| Timeout | 2 s | 4 s per target | Longer limits tolerate slower responses but can delay a verdict. |
| Consecutive failures | 2 requests | 3 rounds | A larger number tolerates more brief failures before blocking. |
| Consecutive successes | 2 requests | 2 rounds | A larger number requires more evidence before restoring access. |
| Sensitive check interval | 1 s | 1 s | Used during sensitive checking and observation when client monitoring is enabled. |

An ordinary third-party round needs at least one successful target by default. Sensitive rounds require every configured target to pass.

The interval, timeout and consecutive failure count jointly determine how quickly a fault is confirmed. More tolerance can reduce unwanted blocks during a brief disruption and delay some fault confirmations.

When client monitoring is enabled, the configured service or a recognized interruption in its log can trigger blocking independently of HTTPS. Recovery checks start after the configured conditions are met. Once access returns, enhanced monitoring can continue at a shorter interval. A new failure can block access again during that period.

A schedule requires the main switch and protection mode. If a scheduled block, an API block and a failed health check overlap, access resumes after all active reasons have cleared.

## Blocking and recovery

The status shows consecutive failed checks and all applicable blocking reasons. A single failed sample below the configured threshold can still leave access available. Scheduled blocks, API requests and failed health checks can overlap.

The local API uses a UUID displayed in LuCI. It is disabled by default. [Local API requests](USAGE.en.md#local-api)

Under **Event log**, you can expand recent connection checks and recovery history. **Clear logs and recovery history** clears all three plugin views. The current recovery status remains visible and the event log records the clear.

<a id="guide-docs"></a>

[Installation and use](USAGE.en.md) · [First configuration](GUIDED-SETUP.en.md) · [Compatibility and limits](COMPATIBILITY.en.md) · [Recovery](RECOVERY.en.md)
