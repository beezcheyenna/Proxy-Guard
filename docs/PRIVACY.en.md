# Privacy and network activity

[English](PRIVACY.en.md) · [简体中文](PRIVACY.md) · [日本語](PRIVACY.ja.md) · [Русский](PRIVACY.ru.md) · [فارسی](PRIVACY.fa.md)

## Requests made by the plugin

The default connectivity check and optional official exit lookup use the project HTTPS endpoint through the local SOCKS proxy. Endpoint operators can see the proxy exit address, request time and requested path. The **Run detailed diagnostics** button requests `/f` through local SOCKS. Authorized API refreshes can use `/f` if selected. The response can include the exit address, approximate location and network diagnostics.

Selected third-party connectivity or exit IPv4 services can also see the request source and time.

Optional UDP DNS checks run only when their switches and prerequisites allow them. A DNS check discloses the configured query name to its destination. Intervals, waiting periods, enhanced monitoring and request duration affect request frequency. No third-party service is guaranteed to remain available or free from rate limits.

Process, socket, interface and client-log monitoring reads local information. The plugin does not send these readings to the project maintainer.

## Stored information

The plugin stores its UCI settings, confirmation/rollback state, runtime status, events and check logs. Runtime logs normally reside in RAM and are lost on reboot; separately configured persistent or remote system logging may retain or forward them.

The API UUID is stored in runtime memory and regenerated on reboot if the API is enabled. The UUID is included in authenticated API responses and in event logs visible to plugin administrators. The heartbeat request to the external service carries its own diagnostic nonce when applicable.

## Sharing reports and screenshots

Report security issues privately according to the security policy. Share redacted evidence in public issues.

Check IP addresses, domains, account names, device IDs, tokens, SOCKS authentication, panel and subscription URLs, query parameters, Cookies, Authorization headers, HAR files and private keys before sharing. Documentation can use `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` and `2001:db8::/32` as example networks.

The README screenshots use the actual interface with example values for the client name, addresses, time, resource usage and log entries. They are illustrations, not measurements of a user's deployment or proof of client compatibility. See the [compatibility notes](COMPATIBILITY.en.md) for supported configurations. Do not copy placeholder addresses into a working configuration.

## Protecting configuration and keys

Keep real configuration, device keys, certificate keys and log backups in restricted storage outside public repositories. Test credentials and example values are not suitable for deployment. Preserve third-party copyright notices; public author information is not a user secret.

Before sharing a repository, check both new files and Git history. If credentials have leaked, revoke or rotate them first, then remove the exposed content and history.
