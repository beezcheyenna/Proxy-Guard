# Privacy and network activity

[English](PRIVACY.en.md) · [简体中文](PRIVACY.md) · [日本語](PRIVACY.ja.md) · [Русский](PRIVACY.ru.md) · [فارسی](PRIVACY.fa.md)

## Requests made by the plugin

Standard checks the configured HTTPS targets through the local SOCKS proxy. Target operators can observe the proxy exit address, request time and requested URL. Exit IPv4 matching is off on a fresh installation. When enabled, it queries the configured primary address service; only a timeout triggers one attempt at the backup through the same SOCKS route. Each new round starts with the primary. With ipify as the primary and the backup field empty, the fallback is `https://4.ident.me/`. Other primary hosts have no implicit backup.

Optional Cloudflare event verification and UDP DNS checks run only when their switches and prerequisites allow them. A DNS check discloses the configured query name to its destination. Intervals, waiting periods, enhanced monitoring and request duration affect request frequency. No third-party service is guaranteed to remain available or free from rate limits.

Process, socket, interface and client-log monitoring reads local information. The plugin does not send these readings to the project maintainer. Pro connects to the control endpoint you configure. Your VPS, HTTPS endpoint and any enabled Cloudflare components can process connection addresses, authentication requests and relevant status. Control-channel and proxy-path heartbeats are separate settings. Household authorization addresses are sensitive operational data.

Optional VPS egress measurement is off by default. When enabled, the Agent contacts ipify from the VPS default IPv4 route. The service sees the request source and time. See the [egress API](VPS-EGRESS-INFO.md).

Public source and examples contain no usable account credentials, personal exit address or deployed Worker/VPC resource identifiers. Deployers must provide their own values. See [Pro components](PRO-COMPANION.en.md).

## Stored information

The plugin stores its UCI settings, confirmation/rollback state, runtime status, events and check logs. Runtime logs normally reside in RAM and are lost on reboot; separately configured persistent or remote system logging may retain or forward them.

Saved secrets use root-restricted files. Raw UCI export uses keep markers for existing sensitive fields rather than exporting their secret files. Newly entered values, backups, screenshots, shell history and error logs can still expose secrets. A keep marker is not a credential backup.

The VPS Agent stores authorization, policy and maintenance deduplication data according to its configuration. Optional diagnostic or trusted telemetry sources may contain visitor addresses. Worker logs and Cloudflare retention settings are controlled by the deployment account.

## Sharing reports and screenshots

Report security issues privately under the [security policy](SECURITY.en.md) to [beezcheyenna268@gmail.com](mailto:beezcheyenna268@gmail.com). Do not send live credentials even by email. Public Issues should contain only the minimum sanitized material needed to reproduce an ordinary problem.

Check IP addresses, domains, account names, device IDs, tokens, SOCKS authentication, panel and subscription URLs, query parameters, Cookies, Authorization headers, HAR files and private keys before sharing. Documentation can use `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` and `2001:db8::/32` as example networks.

The README screenshots use the actual interface with example values for the client name, addresses, time and resource usage. They are illustrations, not measurements of a user's deployment or proof of client compatibility. See the [compatibility notes](COMPATIBILITY.en.md) for supported configurations. Do not copy placeholder addresses into a working configuration.

## Protecting configuration and keys

Keep real configuration, device keys, Agent private settings, certificate keys and log backups in restricted storage outside public repositories. Test credentials and example values are not suitable for deployment. Preserve third-party copyright notices; public author information is not a user secret.

Before sharing a repository, check both new files and Git history. If credentials have leaked, revoke or rotate them first, then remove the exposed content and history.
