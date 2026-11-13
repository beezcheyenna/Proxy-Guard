# Changelog

[Home](../README.md) · [User guide](USER-GUIDE.en.md)

## 1.0.0

### r8 local API

- Authenticate direct HTTPS requests with a UUID generated in LuCI. Turning the API off and on rotates the UUID.
- Return status, diagnostics and timed-block results in one request. Show authenticated request UUIDs in the administrator event log.

### r7 fixes

- Retry brief firewall4 lock contention during permission renewal to avoid unnecessary interruptions. If the four-second service permit still expires, protected traffic is blocked.
- Recheck live enforcement in the 30-second confirmation dialog. Keep is disabled while rules need verification. The original deadline still applies and unconfirmed settings roll back.

### 1.0 changes

- Provide one LuCI application with an optional authenticated local API.
- Default to the fixed official HTTPS endpoint, with no URL to enter. Third-party website checks remain selectable.
- Require TLS 1.2 or newer for HTTPS checks. Official requests try TLS 1.3 first and log a recommendation if they use TLS 1.2 after a handshake compatibility failure.
- Use the official endpoint for optional exit IPv4 verification by default. Report lookup timeouts separately from address mismatches.
- Use the selected HTTPS mode during startup and recovery. Authorized API clients can request an on-demand diagnostic refresh.
- Let the local API refresh the standard heartbeat or the detailed endpoint. Add a one-shot LuCI diagnostic and return the original `X-PGHB-*` response headers.
- Place the configuration and diagnostic tools on one row, show results in LuCI dialogs and keep live API status in the main status panel.
- Add status, timed block requests and withdrawal of the caller's own requests to the optional LAN API.
- Correct firewall status when a kernel permit has expired while the firewall lock is busy.
- Display failed-check progress and overlapping blocking reasons from the active policy.
- Distinguish missing, malformed and IPv6-only responses during IPv4 verification.
- Preserve active firewall permits and timed API blocks when changing diagnostic settings.
- Test the current LuCI draft through local SOCKS, with results kept separate from live enforcement.
- Group connection settings by check method and exit IPv4 verification. Move setup and troubleshooting tools below the settings.
- Show active timed block requests in the local API tab and group detailed diagnostic settings under Advanced diagnostics.
- Validate whole-second API and diagnostic settings in LuCI, including the relationship between the default and maximum block duration.
- Clear event logs, recent check details and recovery history together. An older refresh can no longer restore cleared entries on screen.
