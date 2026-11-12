# Proxy Guard User Guide

[简体中文](USER-GUIDE.md) · [English](USER-GUIDE.en.md) · [日本語](USER-GUIDE.ja.md) · [Русский](USER-GUIDE.ru.md) · [فارسی](USER-GUIDE.fa.md)

[Project home](README.en.md)

<a id="guide-editions"></a>

This guide covers configuration and everyday operation. See the [project home](README.en.md#guide-editions) for version roles and feature differences.

<a id="guide-setup"></a>

## Installation and first setup

1. Install the matching Standard package through LuCI: IPK for opkg firmware, APK for apk firmware. Add a compatible Pro package if you need VPS features.
2. Open “Services → Proxy Guard”, complete the wizard and review SOCKS, the client, ingress interfaces, IPv4 / IPv6 scope and exceptions. Enable checks in “Monitor only”, save and apply, confirm as prompted, then review the results.
3. When ready to enable blocking, select protection mode and “Save & Apply” again. After the self-check passes, **confirm within 30 seconds**. A failed self-check or missing confirmation rolls back the settings. An ordinary proxy outage follows the blocking protection process.

On first installation, protection, exit IPv4 verification and scheduled protection are off. Editing changes the draft; “Save” stages it, and **“Save & Apply” submits it**. The settings page also lets you rerun the wizard, load the last confirmed configuration or edit raw UCI.

## Requirements and protection scope

<a id="guide-requirements"></a>

### Which systems and proxy clients are supported?

The router needs **opkg or apk + LuCI + firewall4/nftables**, with Lua, ucode, curl and other dependencies available from matching firmware feeds. Use IPK for the 24 series and APK for the 25.12 series; see the [compatibility table](COMPATIBILITY.md) for firmware and client combinations.

Adapters are provided for PassWall, PassWall2, OpenClash, Nikki and HomeProxy. Support depends on the client version, core and forwarding mode. Proxy cores and forwarding modes have specific limitations; consult the [compatibility table](COMPATIBILITY.md). IPK and APK packages are not interchangeable, and fw3/iptables-only systems are unsupported. An `all` package does not mean every architecture or device has been tested.

The Pro Linux Agent requires Python `3.10+`, nftables and the necessary kernel capabilities. It supports systemd / OpenRC. Specific Ubuntu, Debian, Rocky Linux and Alpine Linux releases have been compatibility-tested; see [Linux installation](LINUX-AGENT-INSTALL.md).

<a id="guide-scope"></a>

### Which traffic can be protected, and what topology limits apply?

- **Only traffic traversing this router can be blocked.** A same-subnet gateway without NAT may have return traffic that bypasses it. Such traffic cannot be intercepted. Devices merely switched through it while using another gateway are outside the protected route.
- For selected clients or subnets, protection can cover IPv4/IPv6 TCP/UDP traffic in both directions and established connections that actually traverse this router. Traffic initiated by the router itself is outside those clients' protection scope.
- The plugin does not change NAT, interfaces, system routes, DNS or proxy-client configuration. Preserving LAN, DNS and management access requires correct scopes and exceptions.
- Flow offloading, bridge filtering or missing kernel capabilities can prevent protection from being enabled. Vendor acceleration, physical interfaces, multiple ingress paths, VPNs and containers need checks on the actual device.
- One successful check does not prove every website, UDP application or IPv6 exit works. Sampling intervals, unsupported log messages and new upstream versions limit detection.
- Verify your actual topology and traffic paths before enabling protection. Start with one client and verify failure blocking, recovery, LAN, DNS, management and devices using another gateway before expanding the scope.

### What does Pro require, and can it update separately?

Pro requires compatible Standard and a separately deployed Linux VPS Agent. The control channel can use direct HTTPS or Cloudflare; installing the extension does not create cloud resources. Pro can update separately while interfaces remain compatible. Security, state-machine, firmware compatibility or shared translation fixes in Standard may still require updating Standard.

<a id="advanced-settings"></a>

## Configuration and operation

<a id="guide-options"></a>

### Choosing the key settings

| Setting | What to choose |
| --- | --- |
| Operating mode | Monitor only checks and records results without blocking. Protection mode restricts traffic when a fault or schedule requires it. |
| Local SOCKS | Use the SOCKS5 port actually provided by your local proxy client. The default `1070` is an example; the plugin does not create a proxy. |
| Ingress device | Select the Layer 3 device through which protected traffic enters, such as the routed LAN bridge. Do not select every physical port by default. |
| Protected addresses | Enter actual IPv4 clients or subnets and confirm IPv6 separately. Selecting one IPv4 client does not automatically select all of its IPv6 addresses. |
| LAN exceptions | Include only LAN networks that must remain reachable, including required services across subnets. Overly broad exceptions weaken protection. |
| Proxy ingress and DNS ports | Enter the ports actually used. Proxy ingress rules prevent explicit-proxy bypass; DNS exceptions must match the real destination ports. The two lists must not overlap. |
| Exit IPv4 verification | Off by default. When enabled, use a trusted expected exit; do not automatically trust an arbitrary newly observed address. |
| Service, log and boot protection | These features are off in the saved configuration on a fresh install. The wizard may recommend service monitoring for a detected client; review its summary and the applied configuration. Boot protection also requires the main switch, protection mode and service monitoring. |
| Scheduled protection | Off with no preset schedule. Check the times, repeat days and fixed UTC offset before applying. |

Enter one HTTPS target per line as `https://host/path|expected_status`, for example `https://www.gstatic.com/generate_204|204`. The `204` after the separator is the expected HTTP status, not part of the URL. Configure 2–4 targets and the minimum number that must succeed per round in normal mode; the default minimum is 1. Enhanced monitoring requires every target to succeed. Requests use local SOCKS, so a target outage or rate limit can affect the result.

Fresh installs use `https://www.gstatic.com/generate_204|204` and `https://connectivity-check.ubuntu.com/|204` by default. Upgrading preserves saved custom targets.

Set a backup HTTPS URL for exit verification under Connection checks. The backup is tried once over the same SOCKS route only if the primary times out. Each new round starts with the primary. If the field is blank, ipify uses https://4.ident.me/ and other primary hosts have no backup. The existing failure rules apply if neither service verifies the exit.

With exit verification enabled, routine address checks use ipify by default. The optional Cloudflare check makes one additional attempt when the proxy first becomes ready after boot and once after each interruption recovers. Signals for the same interruption are combined; there is no daily or continuous polling. This option also depends on exit verification. Keep Cloudflare trace URLs out of recurring target lists; no third-party endpoint is guaranteed to remain available or free of rate limits.

A Cloudflare timeout or unavailable response does not by itself trigger blocking; the routine checks must still pass. A returned exit address that differs from the expected address is treated as a fault.

**Suggested first-use checks:**

1. Start with one client you control. Verify its gateway, IPv4 / IPv6 paths and LAN, DNS and management exceptions.
2. Enable monitor-only mode, save and apply, and confirm if prompted. Review website results, optional exit verification and enabled client-service checks.
3. Switch to protection mode and save and apply. Confirm within 30 seconds after self-check succeeds, keeping a separate management or console path.
4. During a maintenance window you control, simulate a proxy failure and recovery. Check new and established connections over the IPv4 / IPv6 and TCP / UDP paths you use, as well as LAN, DNS, management and devices using another gateway.
5. Expand the scope or enable schedules and boot protection after these checks. To test boot protection, retain an independent management path, reboot the router running Proxy Guard, then verify startup blocking and recovery from a protected client. Rebooting only the client is insufficient; self-check does not replace real traffic-path validation.

Complete or cancel any unconfirmed configuration trial before upgrading. The installer first rolls back an unconfirmed trial, then preserves the confirmed settings. Direct edits to UCI files also require the apply-and-confirm flow.

<a id="guide-detection"></a>

### Checks, blocking and recovery

#### Normal connectivity checks

Connectivity checks always use the configured local SOCKS proxy, without direct fallback. Exit IPv4 matching is off by default; enabling it requires a trusted expected address. Pro can import VPS address candidates, but an interface or panel address may differ from the actual proxy exit. Review the candidate, then save and apply.

Automatic listener-port detection requires client service monitoring. If you turn service monitoring off, make sure the manual SOCKS port matches the client’s actual listening port. SOCKS authentication remains supported.

Normal connectivity checks wait 10 seconds after each round finishes by default, with request time added separately. Three failed rounds confirm a fault, and two successful rounds confirm recovery. These values are configurable. The page refreshing about once a second does not mean normal external checks run every second.

The fixed startup grace period ends 150 seconds after the router boots by default; protection mode keeps traffic blocked during this wait. Boot protection replaces that deadline with waiting for required services, followed by the configured blocking wait and recovery checks.

#### Service and log monitoring

With client service monitoring enabled, any monitored TCP, UDP or DNS component stopping or restarting can trigger protection by default. Runtime log monitoring must be enabled separately under service monitoring and recognizes supported upstream messages; the UI language does not change its coverage. Optional UDP path checks require SOCKS5 UDP ASSOCIATE support.

Service monitoring follows the components required by the current client configuration. Unconfigured or unnecessary UDP / DNS components are not automatically treated as failures. If the client cannot be identified, check its adapter and configuration; a component excluded from checks has not been verified healthy.

#### Blocking and recovery

When service monitoring triggers protection, the default recovery sequence is:

1. **Block for 15 seconds**, without external validation during the wait.
2. Once the wait has elapsed and services are ready, validate the proxy again. Allow traffic only after the recovery conditions pass.
3. Run **60 seconds of enhanced monitoring after access resumes**. Healthy traffic is allowed during these 60 seconds. A new detected fault blocks traffic again and restarts the wait.

During enhanced monitoring, the next round starts about one second after the previous round finishes; request time is additional. Every HTTPS target, and any enabled exit IPv4 and UDP checks, must pass. Any failure blocks traffic again without using normal mode's minimum-success setting or consecutive-failure threshold.

The wait, enhanced monitoring and their durations are configurable. After a log-triggered fault, initial recovery skips the extra wait only after a fresh startup-completed message, service recovery and new proxy validation. The end of a scheduled window uses this recovery flow only with service monitoring enabled and no other fault or unfinished wait. A new fault during enhanced monitoring still blocks traffic and restarts the wait. Boot protection must be enabled separately. See [detection behavior](USAGE.md) and [log compatibility](LOG_COMPATIBILITY.md).

<a id="guide-schedule"></a>

### Schedules, status and languages

#### Schedules

Scheduled protection is disabled on a fresh installation, with **no prefilled times or weekdays**. Choose daily repetition or any combination of weekdays. An overnight window belongs to its starting day. Time uses a fixed UTC offset, defaulting to `UTC+00:00`; daylight saving time is not adjusted automatically. Upgrades preserve your saved UTC offset and schedule.

For example, selecting Monday only, with a start of `22:00` and end of `06:00`, blocks access from Monday evening to Tuesday morning in the selected UTC offset. You do not also select Tuesday. This example does not create a schedule automatically. Only the selected clients' Internet traffic is blocked; LAN, DNS and management remain subject to the configured exceptions.

#### Status and logs

The page refreshes status, events and check details automatically. Process supervision and bounded automatic recovery address failures of the plugin itself; proxy outages follow the protection flow. Plugin logs are held in RAM and lost on reboot. Separately configured persistent system logging is outside this setting.

#### Interface languages

The UI follows LuCI's language setting and supports **Simplified Chinese, English, Japanese, Russian and Persian**. Use the links at the top of this page to switch the documentation language.

<a id="guide-troubleshooting"></a>

#### Understanding the status

Current protection status reflects actual kernel enforcement. A previously passed check is historical and does not guarantee that access is currently allowed. If an access permit expires, the page reports blocking or pending revalidation.

| Status or message | Meaning and next action |
| --- | --- |
| Disabled | This plugin is not providing blocking protection. Check the main switch and applied configuration. |
| Monitor only | Observing without restricting access. Faults in the log do not install a blocking policy. |
| Blocked or scheduled protection active | Check the cause, schedule and service state. A warning can mean the plugin correctly responded to a fault. |
| Blocking-wait countdown | Internet access remains blocked and external checks have not started. Recovery checks must still pass after the wait. |
| Access restored; enhanced monitoring | Access is allowed while healthy. A new fault blocks it again and starts the waiting period. |
| Waiting for LAN interface | Check the selected device name and actual interface state. The plugin does not create or enable interfaces. |
| Stale, unavailable or unverified rules | Protection cannot currently be confirmed. Preserve the error and inspect processes, rules and configuration instead of relying on an old green status. |

#### Upgrades, reinstalls and troubleshooting

Back up the plugin configuration before upgrading. Securely back up Pro pairing secrets, the private Agent configuration and certificates separately. Upgrades preserve switches, custom timing and other settings. Detection endpoints that exactly match recognized legacy presets are migrated to the new presets, so check the actual endpoints after installation. For a revised package with the same version, opkg / apk may report it is already installed. Verify its source and checksum, then use the same-version reinstall procedure in the [installation reference](USAGE.md#安装升级和卸载); do not bypass dependency checks. Pro can be upgraded independently when the base API is compatible, while new remote features may require an Agent or Worker update.

If the menu is missing, the page fails or an RPC object is not found, keep the complete installation output, then sign in to LuCI again and refresh. Package hooks should handle cache cleanup and RPC reload during a normal installation. If the issue remains after signing in again, investigate installation failures and dependencies; do not broaden ACLs or count a manual service reload as proof of a successful installation.

Read-only checks on your own router:

```sh
if command -v opkg >/dev/null 2>&1; then
    opkg status luci-app-proxy-guard
else
    apk list --installed luci-app-proxy-guard
fi
/usr/libexec/proxy-guard status
/usr/libexec/proxy-guard logs
```

Clear logs removes only this plugin's logs. It does not clear the client's source log or restore access. To release this plugin's protection, turn off the main switch and save and apply. Killing processes or uninstalling is not a safe temporary-release procedure. Remove real addresses, secrets, subscription links and authentication headers before sharing diagnostics; use the private reporting email below for security issues.

<a id="guide-pro"></a>

### Pro: VPS access, SSH and remote maintenance

Pro synchronizes the authenticated household public IP and applies policies to selected VPS service ports. VPS service health can be an additional condition for local recovery; local proxy checks must still pass. Optional bandwidth limits apply only to fallback connections identified by trusted telemetry.

#### Ports and policies

Pro manages only VPS local service ports that you explicitly add and enable. Listener discovery suggests candidates. Unselected ports remain governed by the existing firewall; Docker forwarding and all other machine ports are not automatically taken over.

Each rule can use **whitelist only, standard anti-abuse, or observation only**, with individual sources, connection thresholds and times. Remote policy changes have a separate confirmation period, **60 seconds by default**; without confirmation, the previous policy is restored. A panel, API or subscription endpoint sharing a selected proxy port may be restricted by the same rule.

Operating mode and source selection are separate choices. All sources still receive resource limits in standard mode; the legacy unrestricted choice completely bypasses protection for that port. Whitelist mode cannot be combined with all sources. Whether household or static allowlists are exempt from standard limits depends on the rule's source selection.

Observation mode does not block the selected service ports. Separately enabled SSH management still follows its own settings.

#### Emergency SSH access

SSH is unmanaged by default, and remote maintenance is disabled. If you enable SSH management, loss of both authenticated heartbeat channels for the configured time (60 seconds by default) can trigger emergency access. New configurations default to public emergency access until household authorization returns; a time limit or restricted management sources can be selected instead. Continuous opening increases exposure, while an expired time limit with no usable management source can prevent a new login. SSH authentication, the system firewall and upstream security groups still apply.

#### Control connection

Control can use direct HTTPS or a Cloudflare Worker with Tunnel/VPC. It handles authentication and policy coordination, not proxy traffic. Control requests must bypass the proxy, and you must confirm the direct routing; the plugin does not change routing or traffic-splitting rules. The independent proxy-path heartbeat instead uses local SOCKS to check the proxy route. Control defaults to IPv4. IPv6 traffic filtering does not imply validated IPv6 cloud control. See [Pro companion setup](PRO-COMPANION.md).

The independent proxy path has its own heartbeat secret and Agent HTTPS entry. Direct HTTPS mode can reuse the same Agent base URL, but control requests must go directly and path heartbeats through SOCKS. In Cloudflare mode, the Worker URL cannot serve as this independent entry. See the [connection mapping](LINUX-AGENT-INSTALL.md#control-and-path).

#### Fixed remote maintenance

Remote maintenance is off by default. The operation must be authorized both on the router and in the VPS Agent before requesting a VPS reboot or a supported Xray core restart. An accepted request does not mean recovery is complete; check subsequent verification results. Arbitrary remote commands are not provided.

#### First Pro deployment

1. Validate Standard's local protection, then install a compatible Pro extension.
2. Install the Agent on the intended Linux VPS. Verify actual services, ports, dependencies and the existing firewall, keeping SSH or console access.
3. Choose direct HTTPS or Cloudflare control and pair the required credentials separately. Verify that control requests bypass the proxy. For SSH rescue, also configure an independent HTTPS heartbeat through the proxy path.
4. Read authentication, authorization and service status first. Listener discovery only supplies candidates. Add only intended ports, checking whether the panel, subscriptions or SSH share an entry point.
5. Save and apply, inspect the VPS trial-policy result and confirm before the remote deadline, 60 seconds by default. This is separate from Standard's local 30-second confirmation.
6. Enable SSH management, the additional remote-health condition or remote maintenance only as needed, completing their checks separately. Stopping synchronization does not remove VPS rules; removal has its own prepare, apply and confirm workflow.

<a id="guide-docs"></a>

## Support and licensing

Report security vulnerabilities privately first to [beezcheyenna268@gmail.com](mailto:beezcheyenna268@gmail.com). For VPS, authentication, SSH or protection-bypass issues, do not publish unpatched exploit details, live addresses or credentials. Ordinary issues may be reported publicly after removing private information.

**This project is intended for development, testing and technical research.** Use it on authorized devices and networks, and comply with the laws applicable where it is used and deployed. The software is provided “as is” under the existing [MIT License](../LICENSE), without a guarantee of suitability for every situation. Risks and liability are governed by the applicable licenses and law. This notice does not modify the existing licenses or exclude liability that cannot legally be excluded.

[Security policy](SECURITY.en.md) · [Disclaimer](DISCLAIMER.en.md) · [Privacy](PRIVACY.en.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

### Related documentation

Further installation, compatibility and development documentation:

- [Compatibility](COMPATIBILITY.md)
- [Exact test matrix](TEST-MATRIX.md)
- [Recovery](RECOVERY.md)
- [Linux Agent installation](LINUX-AGENT-INSTALL.md)
- [Cloudflare components](CLOUDFLARE-WORKER.md)
- [Build from source](BUILDING.md)
- [Installation reference](USAGE.md)
- [Wizard reference](GUIDED-SETUP.md)
- [Log compatibility](LOG_COMPATIBILITY.md)
- [Licensing](LICENSING.md)

- [Changelog](CHANGELOG.en.md)

[Contributing](../CONTRIBUTING.md)
