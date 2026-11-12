# Guided setup and confirmation rollback

[English](GUIDED-SETUP.en.md) · [简体中文](GUIDED-SETUP.md) · [日本語](GUIDED-SETUP.ja.md) · [Русский](GUIDED-SETUP.ru.md) · [فارسی](GUIDED-SETUP.fa.md)

The wizard opens on the first visit after a fresh installation. Closing it or choosing to set up later keeps protection disabled. You can reopen it from Settings.

1. Select an existing Layer 3 LAN ingress. Recommendations use netifd addresses and LAN firewall zones and can recognize LAN masquerading. NAT is preserved.
2. Select monitoring only, outage protection, or boot protection. Review the client, SOCKS port, service monitoring, and scheduling. Form edits are drafts.
3. Review source ranges, local exceptions, proxy inlets, and DNS redirect ports. Add entries for routed LANs and special ports where necessary.
4. Review the summary and select **Save & Apply**. Leaving the wizard, going back, and restoring a preset leave the active configuration alone.

Choose IPv6 independently: discovered prefixes, a manual range, all sources on the selected ingress (`::/0`), or no IPv6 matching. Check temporary addresses and future prefix changes. Excluding IPv6 saves `ipv6_protect=0` so an omitted empty UCI list cannot expand scope. System IPv6 remains active. Detected LAN IPv6 prefixes become local exceptions. Keep public ranges and unidentified upstream ports out of LAN exceptions.

## Presets

| Preset | When to use it | Check |
| --- | --- | --- |
| Monitoring only | First identify the ingress and client and observe detection | External access remains available. Verify the real traffic path before enabling blocking. |
| Outage protection | Ingress, scope, and exceptions are understood | Confirm the client, SOCKS, enabled checks, and management path. |
| Boot protection | Outage protection has been tested and startup traffic must be held | Enable the protection switch, protection mode, service monitoring, and boot protection. Reboot the router as a separate acceptance test. |

Verify multiple LANs, routed local networks, dynamic IPv6 prefixes, VPNs, and containers individually. The wizard uses existing interfaces, gateways, NAT, DNS, and proxy routing. Check whether packets on a switch-only interface really route through this device.

Scheduling is configured separately. Enter different start/end times, days of the week, and the fixed UTC offset. Review the summary before applying. Restoring the preset prepares a draft and leaves the router's factory settings alone.

## Local confirmation and rollback

The backend validates configuration and kernel support, then checks the detection process and active rules. The self-check can wait about 120 seconds. On success, the router starts a 30-second timer. Only the applying session can confirm or cancel. Other sessions cannot read the confirmation token or replace the pending enable operation.

Reloading or closing the browser, losing the connection, or changing the wall clock leaves the router's timer running. Reboot before confirmation triggers rollback. The backend attempts recovery from a separate backup if transaction state is damaged. Verify the live rules before calling rollback successful.

An unavailable proxy should keep protection blocked while it recovers. A genuine configuration or rule error rolls back to disabled for first enable or to the last confirmed configuration. An explicit disable takes precedence over a pending enable.

Loading the last confirmed settings and starting again from defaults only fill the form. Going back retains choices. Reset clears unsaved fields and the wizard draft. Upgrades retain configuration and do not force the first-run wizard.

## Expected egress in Pro

Save the authenticated Pro connection, then enable egress checking, choose a source, and read VPS addresses in basic settings. Public interfaces, panel configuration hints, and optional default-route measurements are available. Select among multiple candidates yourself or enter a known address manually.

The panel source reads a trusted, explicitly configured local Xray configuration on the Agent. It treats REALITY destinations and remote servers separately from egress and does not export private keys. Panel APIs and multi-hop routes require separate verification. Measurement is off by default and uses a fixed target, timeout, and minimum interval. Reading status uses the existing sample.

Importing prepares a draft. With NAT, WARP, multiple exits, or chained proxies, interface and panel addresses may differ from the actual exit. Verify the SOCKS path independently. A newly observed unknown IP does not become the trusted expected IP automatically. See the [egress API](VPS-EGRESS-INFO.md).

## Verify the actual path

Use one protected device to check new and established IPv4/IPv6 TCP/UDP traffic. During an outage, verify external blocking and continued LAN, DNS, management, and router-originated access. Check a device using another gateway too. Return and switched traffic that bypasses the router are outside its reach. Local self-checks cover configuration, process, and rules. Validate the browser, hardware offload, and deployed topology separately.

<a id="remote-policy-confirmation"></a>

## Remote policy confirmation in Pro

By default, **Save & Apply** requests a VPS Agent trial. After the VPS applies the policy, the applying login session has 60 seconds by default to confirm, configurable from 30 to 300 seconds. Closing the page leaves the timer running. On expiry the VPS restores the previous port and SSH policy while retaining the increasing revision and current authenticated IP. Expired leases stay expired. A process restart keeps the remaining time. A VPS boot restores an unconfirmed policy first. Expiry is normally processed on an Agent loop running every five seconds. A stopped Agent needs its supervisor. Kernel and storage failures can delay recovery.

The router keeps a private snapshot until the result is known. If confirmation was sent but its reply was lost, inspect remote state again. Changes from another session to configuration or secrets produce a conflict instead of overwriting them. New capabilities require a matching Agent and, for Cloudflare control, a matching Worker. Sign in again if an older session lacks the new permissions. Disabling policy confirmation or using the older/root CLI sync applies immediately. Keep a separate management path.

**Stop synchronization** stops heartbeats and renewals. To remove plugin rules, prepare removal, review the draft, save and apply, then confirm removal of the proxy-port and SSH policies before stopping synchronization. The proxy and SSH services continue running and the system firewall still applies. After an interruption, read remote status and resolve any unknown result or conflict. See [recovery](RECOVERY.en.md).
