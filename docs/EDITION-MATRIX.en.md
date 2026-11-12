# Standard and Pro feature matrix

[English](EDITION-MATRIX.en.md) · [简体中文](EDITION-MATRIX.md) · [日本語](EDITION-MATRIX.ja.md) · [Русский](EDITION-MATRIX.ru.md) · [فارسی](EDITION-MATRIX.fa.md)

Standard `0.3.0-21` protects connections on the router. Pro `0.3.1-5` adds access management for selected VPS service ports. Packages and revisions are independent.

| Area | Standard | Pro |
| --- | --- | --- |
| Deployment | OpenWrt router | Router extension plus a Linux Agent, with optional Worker/Tunnel |
| Proxy checks | HTTPS through local SOCKS, optional IPv4 egress and SOCKS5 UDP | Standard checks plus import of VPS egress candidates |
| Local filtering | Selected ingress, source ranges, exceptions, IPv4/IPv6 TCP/UDP | Uses Standard |
| Clients | PassWall, PassWall2, OpenClash, Nikki, HomeProxy, by verified version and mode | Uses Standard |
| Protection flow | Failure thresholds, blocking wait, enhanced monitoring, boot and scheduled protection | Optional remote health condition and maintenance recovery |
| Interface | State, event/check logs, five languages, wizard, raw configuration, self-check and limited recovery | Selected ports, authenticated link, remote state and fixed operations |
| Remote ports | — | Per-rule allowlist, rate limits or observation, with source and threshold settings |
| SSH | — | Opt-in management and persistent or timed rescue after both heartbeats fail |
| Maintenance | — | Separately authorized VPS reboot or supported Xray restart, including supported 3x-ui adapters |

## Independent upgrades

Pro checks the minimum Standard version and the base API. Upgrade Pro alone when both requirements are met. Upgrade Standard for its security, state machine, or firmware fixes. Pro includes its own five-language pages, policy confirmation, and raw editor.

If Standard is upgraded first, its hook preserves the old catalog entries required by an installed older Pro. Installing the newer Pro removes this temporary catalog. Agent and Worker capabilities are verified separately. New remote features can require both companion updates.

## Current scope

New installs leave Standard and Pro disabled. SSH and maintenance are separately authorized. Discovery suggests ports and existing system rules govern unselected ports. The default control path and home IP synchronization are IPv4. IPv6 data-plane coverage is documented separately.

The deployment centers on one router identity and Agent. Check each topology and client. Precise fallback classification requires trusted structured data. Validate with actual proxy requests after checking the process, port, and startup log. See [compatibility](COMPATIBILITY.en.md).

## Minimum compatibility for this release

| Component | Release or identifier | Requirement |
| --- | --- | --- |
| Standard IPK | 0.3.0-21 | LuCI, opkg, firewall4/nftables, matching dependencies |
| Pro IPK | 0.3.1-5 | Standard **≥ 0.3.0-13**, base **API 1** |
| Standard APK | 0.3.0-r21 | Matching firmware SDK, apk, LuCI, firewall4/nftables |
| Pro APK | 0.3.1-r5 | Standard **≥ 0.3.0-r20**, base **API 1** |
| VPS Agent | **v3** | Control protocol, capabilities, and policy confirmation are checked |
| Worker npm project | **0.2.0** | Relays and validates v3 responses. Its npm version identifies tooling. |

See [package/Makefile](../package/Makefile) for dependencies and API constants. IPK and APK revisions use their own package formats. Minimum versions are installation floors. Get the Agent and optional Worker from the [matching release source](https://github.com/beezcheyenna/Proxy-Guard/releases/tag/v0.3.0-21-pro-0.3.1-5) and record the deployed tag or commit. Verify deployed Worker code separately from `package.json`.

### What to upgrade

| Change | Action | If incompatible |
| --- | --- | --- |
| Pro UI, translations, API 1 fixes | Upgrade Pro alone with a compatible base | Installer or startup rejects an incompatible base |
| Standard fix retaining API 1 | Upgrade Standard alone | Check new major APIs separately |
| Port rules, source modes or trial support | Update the Agent first. For Cloudflare, also update and verify the Worker | Missing `per_rule_modes`, `source_modes_v2`, or `policy_confirmation` rejects the apply |
| Protocol or relay response mismatch | Use matching source and test end to end. Direct HTTPS uses the Agent | Report failure and inspect the applied policy |
| Import VPS egress | Require egress schema 1 on Agent and control path | Reject unsupported or invalid candidates. Standard connectivity checks continue |

Keep a compatible Standard installed for Pro. A failed apply can leave the previous rules active. Check revision, pending confirmation, and live policy in [recovery](RECOVERY.en.md).
