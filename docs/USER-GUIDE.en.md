# User guide

[English](USER-GUIDE.en.md) · [简体中文](USER-GUIDE.md) · [日本語](USER-GUIDE.ja.md) · [Русский](USER-GUIDE.ru.md) · [فارسی](USER-GUIDE.fa.md)

<a id="guide-editions"></a>
<a id="guide-setup"></a>
<a id="guide-requirements"></a>
<a id="guide-scope"></a>
<a id="advanced-settings"></a>
<a id="guide-options"></a>
<a id="guide-docs"></a>

Install Proxy Guard on a router that uses LuCI and firewall4/nftables. Choose the package format used by your firmware.

## First configuration

Open Services → Proxy Guard. Use the wizard to review ingress devices, the IPv4 and IPv6 scope, local exceptions, and your SOCKS port. Enable Monitor only first. Save & Apply runs a self-check and opens a 30-second confirmation window. A failed or unconfirmed change rolls back.

Use firewall4 and nftables with LuCI. OpenWrt 24 uses IPK and OpenWrt 25.12 uses APK. For iStoreOS and ImmortalWrt, match the firmware’s package manager and kernel dependencies.

Only traffic that actually crosses the router can be protected. Verify your selected ingress, IPv4 and IPv6 paths, DNS and management access on one client before expanding the scope. Same-subnet routing may return directly around the router.

When the rules still need verification, **Keep these settings** is temporarily disabled. The original countdown continues. If the timer expires, the router restores the previous settings even if the page has been closed.

## Protection modes

- **Monitor only** records problems and leaves Internet access available.
- **Protect** blocks Internet traffic for the selected scope after confirmed failure. Enable the startup protection preset if the scope should remain blocked while the router is starting.
- **Scheduled protection** can block access every day or on selected weekdays. The schedule uses a fixed UTC offset, initially UTC+00:00.

The service and log monitor can detect a client restart and start recovery checks. The watchdog supervises Proxy Guard itself. Enable the optional UDP path check if you need a separate UDP health signal.

## Test current proxy

Official HTTPS is selected by default and uses a fixed address through local SOCKS. Third-party HTTPS is selectable and has independent timing and thresholds. Exit IPv4 verification is off initially. When enabled, the official response supplies the IPv4 by default. A third-party IP lookup retries its backup only after the primary times out.

In LuCI, Test current proxy uses the unsaved form settings through SOCKS. It reports the result, latency and available exit IPv4. Only Save & Apply changes configuration and enforcement.

Below the settings, open **Configuration and diagnostics** to check the settings and runtime environment, test the current proxy or view a sanitized report. You can also rerun the setup wizard, edit raw UCI, load the last confirmed settings or start over with defaults.

Under **Configuration and diagnostics**, open **Test current proxy**, then click **Run detailed diagnostics** in the dialog to request `/f` once through the router’s local SOCKS proxy and view the `X-PGHB-*` response headers.

## Detection and recovery settings

Official HTTPS uses a 3-second interval and a 2-second request timeout. Two consecutive failures confirm a fault and two consecutive successes confirm recovery. Third-party HTTPS defaults to a 10-second interval, a 4-second timeout per target, three failed rounds and two successful rounds. In a normal third-party round, at least one target must succeed.

When client monitoring is enabled, the configured service or a recognized interruption in its log can trigger blocking independently of HTTPS. Recovery checks start after the configured conditions are met. Once access returns, enhanced monitoring can continue at a shorter interval. A new failure can block access again during that period.

A schedule requires the main switch and protection mode. If a scheduled block, an API block and a failed health check overlap, access resumes after all active reasons have cleared.

## Blocking and recovery

The status shows consecutive failed checks and all applicable blocking reasons. A single failed sample below the configured threshold can still leave access available. Scheduled blocks, API requests and failed health checks can overlap.

The local API uses a UUID displayed in LuCI. It is disabled by default. [Local API requests](USAGE.en.md#local-api)

Under **Event log**, you can expand recent connection checks and recovery history. **Clear logs and recovery history** clears all three plugin views. The current recovery status remains visible and the event log records the clear.

[Installation and use](USAGE.en.md) · [First configuration](GUIDED-SETUP.en.md) · [Compatibility and limits](COMPATIBILITY.en.md) · [Recovery](RECOVERY.en.md)
