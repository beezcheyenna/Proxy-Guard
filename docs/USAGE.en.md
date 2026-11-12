# Installation and use

[English](USAGE.en.md) · [简体中文](USAGE.md) · [日本語](USAGE.ja.md) · [Русский](USAGE.ru.md) · [فارسی](USAGE.fa.md)

Install, configure, and maintain Standard `0.3.0-21` and Pro `0.3.1-5`. Review [compatibility](COMPATIBILITY.en.md) and the [test matrix](TEST-MATRIX.en.md). See the [user guide](USER-GUIDE.en.md) for day-to-day settings.

## Verify the download

Download the package and `SHA256SUMS` from the [same stable release](https://github.com/beezcheyenna/Proxy-Guard/releases/tag/v0.3.0-21-pro-0.3.1-5) into one directory. Match the edition, format, version and filename. The example verifies the Standard IPK. For the Standard APK, set `PG_PACKAGE=luci-app-proxy-guard-0.3.0-r21.apk`.

```sh
PG_PACKAGE=luci-app-proxy-guard_0.3.0-21_all.ipk
awk -v f="$PG_PACKAGE" '$2 == f { print; n++ } END { if (n != 1) exit 1 }' SHA256SUMS > SHA256SUMS.selected &&
sha256sum -c SHA256SUMS.selected
```

Require the selected file to report `OK` and the command to succeed. A missing or duplicate entry, missing file, or digest mismatch is a reason to stop installation. If you downloaded every file, use `sha256sum -c SHA256SUMS`. Checking the whole manifest with only some assets downloaded produces missing-file errors.

On macOS, run `shasum -a 256 <filename>` and compare all 64 hexadecimal digits to the matching entry. SHA256 checks the file against the manifest. Obtain both from the project's HTTPS release. Publisher authentication would require independently verified signatures or attestations.

<a id="installation"></a>

## Install, upgrade, and remove

Choose the matching firmware format. Use IPK with opkg on the 24 series and APK with apk on 25.12. Upload through LuCI or place the file on the router and run the corresponding command.

**opkg / IPK**

```sh
opkg install /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-0.3.0-r21.apk
```

`--allow-untrusted` allows this manually verified local APK. Dependency checks still apply. `--no-network` requires dependencies to be present. Install missing dependencies from matching firmware feeds first.

Pro extends a compatible Standard. Their version numbers are independent. You can install both in one transaction.

**opkg / IPK**

```sh
opkg install /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk /tmp/luci-app-proxy-guard-pro_0.3.1-5_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add /tmp/luci-app-proxy-guard-0.3.0-r21.apk /tmp/luci-app-proxy-guard-pro-0.3.1-r5.apk
```

Upgrade only Pro when the existing Standard meets its minimum version and base API. Incompatible installations are rejected with a reason. Standard fixes can be installed separately while compatible. See the [edition matrix](EDITION-MATRIX.en.md). Remote features also need the [Linux Agent](LINUX-AGENT-INSTALL.en.md). Choose direct HTTPS or Cloudflare Worker/Tunnel/VPC separately.

Since Pro 0.3.1-2, installation and startup migrate old `device_token` and `path_token` UCI values to root-only key files, even while disabled. Stage new secrets through LuCI, then apply. Rotate across the devices and companion services if untrusted accounts previously had read access.

Standard depends on `luci-base`, `lua`, `libuci-lua`, `luci-lib-jsonc`, `luci-lib-nixio`, `rpcd-mod-file`, `firewall4`, `curl`, `ca-bundle`, `ucode`, `ucode-mod-fs`, and `ucode-mod-uci`. Use firmware-matched dependencies and prepare them before an offline install. File locking is provided without a separate `flock` package. Keep dependency checks enabled.

A normal install can skip a same-version rebuild. Back up and verify source and SHA256. Run the second command only if replacing an installed Pro. Use the actual local APK file for apk.

**opkg / IPK**

```sh
opkg install --force-reinstall /tmp/luci-app-proxy-guard_0.3.0-21_all.ipk
opkg install --force-reinstall /tmp/luci-app-proxy-guard-pro_0.3.1-5_all.ipk
```

**apk / APK**

```sh
apk --no-network --allow-untrusted add --force-reinstall /tmp/luci-app-proxy-guard-0.3.0-r21.apk
apk --no-network --allow-untrusted add --force-reinstall /tmp/luci-app-proxy-guard-pro-0.3.1-r5.apk
```

An `apk fix` result of `unavailable, skipped` means the local files were not replaced. Complete or cancel pending trials before updating. The installer rolls back unconfirmed changes first and preserves the confirmed config. Use an in-place upgrade, retain the full output, and apply or reinstall from one session at a time.

In LuCI open **Services → Proxy Guard**. Package hooks clean LuCI caches, reload rpcd, and restart the plugin when needed. If the menu or RPC object is missing after signing in again, preserve the install output and inspect dependencies and hooks. Keep existing ACLs.

Fresh installs start disabled in monitoring mode. Upgrades preserve `/etc/config/proxy_guard`, switches and custom timings. Exact recognized Google/Cloudflare presets migrate to gstatic and Ubuntu, and the old Cloudflare exit endpoint to ipify. Review actual target values and any `proxy_guard-opkg` or `.apk-new` configuration copy.

Back up `/etc/config/proxy_guard`. For Pro also back up `/etc/config/proxy_guard_access` and the existing `/etc/proxy-guard-access/device.key` and `/etc/proxy-guard-access/path.key`. Raw UCI export omits those private keys. Keep router backups private. Back up Agent configuration, certificates, and Worker secrets separately.

Stopping Pro sync or removing the router extension leaves remote policy in place. With control available, prepare removal, apply, confirm, and verify the VPS rules first. See [remote policy confirmation](GUIDED-SETUP.en.md#remote-policy-confirmation).

Choose the commands for your package manager. Run the first line only if Pro is installed.

**opkg / IPK**

```sh
opkg remove luci-app-proxy-guard-pro
opkg remove luci-app-proxy-guard
```

**apk / APK**

```sh
apk del luci-app-proxy-guard-pro
apk del luci-app-proxy-guard
```

The uninstall hooks clean the plugin's rules, RPC registration, menu, and startup links. Modified configuration can be retained by the package manager. Removing the plugin releases its own blocking. Use the [explicit disable procedure](RECOVERY.en.md) for maintenance.

## First configuration

Use the [setup wizard](GUIDED-SETUP.en.md) to select a real Layer 3 LAN ingress, then review the [settings and examples](USER-GUIDE.en.md#guide-options). Start with one IPv4 and IPv6 client. The packaged addresses are examples. Confirm the local SOCKS5 listener on `127.0.0.1`, the client's actual proxy ingress, and DNS destination ports. The check port and client-facing proxy ingress have different purposes. DNS defaults to port `53`. Use precise local exceptions and exclude IPv6 explicitly if that is the intended scope. Start in **Monitor only**, save and apply, and check the real path before enabling blocking.

## Save, apply, and status

Edits change the draft. **Save** stages it for the session. **Save & Apply** validates and commits. Confirm within **30 seconds after the local self-check passes**. Reset restores the saved or staged form values. **Clear logs** clears only this plugin's event and check history. Status refreshes about once a second and log views about every five seconds. Slow RPC can delay display. For stale state or missing permissions, verify the kernel and sign in again after a permission change. See [status and troubleshooting](USER-GUIDE.en.md#guide-troubleshooting).

## Blocking and recovery

### Normal checks

Each round runs HTTPS through local SOCKS. Exit IPv4 matching and SOCKS5 UDP are optional. Fresh installs use `https://www.gstatic.com/generate_204|204` and `https://connectivity-check.ubuntu.com/|204`. The default minimum is one successful website, with all enabled exit and UDP checks passing. Default thresholds are 3 failed rounds and 2 successful rounds. The 10-second interval starts after the round finishes. Fixed startup grace lasts until 150 seconds after boot, with blocking in protection mode. Boot protection uses service readiness instead.

With exit matching on, a primary timeout can try a backup HTTPS URL once over the same SOCKS. Every new round starts with the primary. With an empty backup field, ipify uses `https://4.ident.me/` and other domains have no backup. Wrong addresses and failed verification follow the configured failure rules.

### Client service monitoring

The service check reads process and listener identity about once a second. By default, any required TCP, UDP, or DNS component stopping or restarting triggers protection. You can require all monitored components to fail. Required services depend on the actual client configuration.

The default block wait is 15 seconds with local service checks only. Once the wait ends and the required services are ready, run fresh checks and release traffic on success. Enhanced monitoring then allows healthy traffic for a default 60 seconds, with about one second between completed rounds. Every HTTPS target and enabled exit and UDP check must succeed during recovery and enhanced monitoring. A new fault restarts blocking and the wait without the normal failure count. Wait and enhanced monitoring each have a switch and a 1–3600-second duration. Disabling either leaves recovery validation in place.

### Runtime logs

Enable log monitoring separately under service monitoring, at a 1–10-second interval. The reader recognizes reviewed lifecycle messages, including restarts, rule removal, stop, startup failure, and completion. See [runtime log compatibility](LOG_COMPATIBILITY.md). On an initial log-triggered failure, a fresh completion for the current cycle, required services, and new checks can release traffic directly to enhanced monitoring. A fault during enhanced monitoring still incurs the configured wait. Missing logs, expired or future timestamps, and unrelated cancellations cannot clear a valid pending fault. Timers use monotonic time and log parsing uses the router's local clock and zone.

### Boot and scheduled protection

Boot protection requires the main switch, protection mode, service monitoring, and the boot switch. A valid setup installs early rules by interface name and reconciles them when the device can be verified. All required TCP, UDP, and DNS services must be ready before blocking wait and recovery. Test the actual forwarding path.

For schedules choose daily or weekly days, distinct start and end times, and a fixed UTC offset. Overnight windows belong to their starting day. During the window external traffic is blocked and configured exceptions apply. At expiry, with service monitoring and no other failure or pending wait, fresh strict verification can enter enhanced monitoring without another 15-second wait. Without service monitoring use normal consecutive recovery checks.

## Verify an upgrade or reboot

1. Verify the installed package and checksum, hooks and dependencies. Sign in again and check the page, status, and logs.
2. Compare actual switches, mode, ingress, scopes, exceptions and schedule with the saved settings.
3. From one client verify blocking, recovery, LAN, DNS, management and another gateway. Check both address families and new and existing connections where applicable.
4. Save relevant RAM logs and keep independent management access. For boot protection, reboot the **router running Proxy Guard**, then verify startup blocking and release from the protected client.
5. For Pro verify control, renewed household authorization, selected-port rules and Agent state. Repeat the relevant checks after firmware, core or topology changes.

## Logs and troubleshooting

The UI shows the latest 200 events and 100 check details. Files rotate by configured size in RAM. `logger` also writes system logs, which may have separate retention. An error-level protection event can indicate a successful response to a fault. Check subsequent recovery, rule errors and current state. See the [status guide](USER-GUIDE.en.md#guide-troubleshooting), [privacy](PRIVACY.en.md), and [recovery](RECOVERY.en.md).

Read-only router checks:

```sh
if command -v opkg >/dev/null 2>&1; then
    opkg status luci-app-proxy-guard
else
    apk info -a luci-app-proxy-guard
fi
/usr/libexec/proxy-guard status
/usr/libexec/proxy-guard logs
```

## Optional UDP path check

Configure a reachable IPv4 UDP DNS server, port, query name and timeout. `luci-lib-nixio` supplies locking and UDP support. The self-check rejects enabling UDP when support is missing. The check uses SOCKS5 UDP ASSOCIATE, a loopback relay, a random DNS transaction ID, and verifies the source, ID, question and reply code. It needs a client supporting UDP ASSOCIATE. There is no direct fallback. A LAN target verifies its LAN path.

UDP failure counts toward a failed round, or blocks on a single failure during enhanced monitoring. The blocking wait sends no UDP probe. Use this check alongside HTTPS and any enabled exit validation.

## Process recovery and resources

Automatic recovery has heartbeat, minimum retry interval, retry count, and observation-window settings. procd still restarts exited processes when automatic heartbeat recovery is off. Explicit init stop does not re-enable the plugin and can leave blocking in place. Use [explicit disable](RECOVERY.en.md) to release it.

Sampling runs every five seconds. CPU percentage uses total capacity of online logical CPUs, so one busy CPU out of 20 is 5%. A counter reset or a change in CPU count or process identity starts a new sample. The estimate covers the three supervised processes and their children. LuCI/rpcd, the kernel, and other proxies are outside that estimate. Sampling can be disabled independently. System logging may persist or forward RAM log events.

## Pro: VPS access management

See [architecture and behavior](PRO-COMPANION.en.md), [Agent installation](LINUX-AGENT-INSTALL.en.md), and [remote confirmation](GUIDED-SETUP.en.md#remote-policy-confirmation).

- Select and enable local service ports explicitly. Separate panel, API and subscription ports follow system rules unless selected. A shared IP/protocol/port cannot be split by URL or SNI. SSH has its own settings.
- A rule can inherit the default or choose `standard`, `whitelist`, or `observe`. Configure TCP/UDP, port ranges, household/static/mixed sources, connection rate, burst, concurrency, trusted fallback thresholds, duration above limit, cooldown, and observation window per rule. Enabled rules on the same protocol must not overlap. Standard retains normal established connections. Allowlist revocation can affect an established inbound connection. Observation only records events.
- Managed SSH needs an independent HTTPS path heartbeat through local SOCKS as well as control. Verify a usable management session before enabling. New public rescue defaults to duration `0` until renewed household authorization, with `30`–`3600` seconds available. Explicit older settings persist. System firewall and SSH authentication apply. See the [SSH prerequisites](LINUX-AGENT-INSTALL.en.md#control-and-path).
- Maintenance needs Agent `maintenance.enabled` and matching LuCI permissions. `adapter=systemd` targets the configured unit. `adapter=3x-ui` needs a verified `xui_usr1_confirmed`. `service` matches the service monitor name. The queue runs independently of heartbeats.
- For exact fallback bandwidth limits configure a private regular JSONL `reality.telemetry_file`. A heartbeat is `{"kind":"heartbeat","time":...}`. Fresh records use Unix seconds `time`, `kind` (`authenticated` or `fallback`), `source_ip`, `source_port`, `port`, and `protocol`. Fallback includes increasing `bytes_in` and `bytes_out`. Match selected ports only. Limits are per direction, source and port. If using a trusted non-root writer, configure `reality.log_uid` and keep the file non-writable by groups or other users.

## Raw configuration and effective policy

Each raw UCI editor covers only its own plugin file, with the current session's staged values, a default template and a draft download. Validation distinguishes UCI syntax from readiness to enable. Save stages a draft even while disabled. Save & Apply uses local self-check and confirmation or the remote capability and confirmation flow. Reload if another page changed the configuration. Unknown options are preserved with a warning. Legacy `default_deny` and `auto_discover` do not authorize host-wide filtering.

`__KEEP_SAVED_SECRET__` retains saved secrets without exporting private key files. Enter a fresh value to rotate. `revision` is assigned by the backend and increases for replay protection. Preserve the pairing and revision when reinstalling. Replacing a template edits the draft.

`source_mode=all` permits all sources under the selected mode, with Standard limits and no automatic household or static exemption. It cannot be combined with whitelist mode. Legacy `source_mode=any` preserves its explicit unprotected behavior. Check the confirmed remote state for effective policy. If LuCI is unavailable or rules remain after stopping, use [recovery](RECOVERY.en.md).
