# Reporting security vulnerabilities

[English](SECURITY.en.md) · [简体中文](SECURITY.md) · [日本語](SECURITY.ja.md) · [Русский](SECURITY.ru.md) · [فارسی](SECURITY.fa.md)

**Security contact: [beezcheyenna268@gmail.com](mailto:beezcheyenna268@gmail.com)**

This policy covers security issues in Proxy Guard Standard, Pro, the VPS Agent, the Cloudflare companion and their deployment.

## Report privately first

For issues involving VPS access, proxy-port policies, emergency SSH, authentication, authorization, exposed credentials or protection bypasses, email first. Please do not initially publish unpatched exploit details, live deployment addresses, valid credentials or reproduction scripts targeting an online VPS in public GitHub Issues, pull requests, Discussions, Gists or elsewhere. These details could expose other users' servers to attack.

Sanitized ordinary bugs may be reported publicly. If you are unsure whether an issue is security-sensitive, use email first.

## What to include

- The actual Standard, Pro, Agent and Worker versions, plus relevant firmware, kernel, client and mode.
- Observed and expected behavior, affected scope and triggering conditions.
- A minimal reproduction on an isolated system you own or are authorized to test, with necessary redacted logs.
- Any known mitigation and a way to continue the discussion.

An initial report need not contain real public IPs, production configuration, full HAR files or complete logs. Do not send active passwords, private keys, tokens, cookies or other credentials. Agree on an appropriate transfer method first if sensitive material is necessary. This email address does not imply that PGP or end-to-end encryption has been configured.

## Fixes and coordinated disclosure

Maintainers will assess the report, discuss mitigation and fixes, and coordinate the timing and scope of public details with the reporter. Please avoid publishing directly exploitable information until a fix or mitigation is ready and disclosure has been coordinated.

The project currently promises no fixed response time, remediation deadline or bounty. Report unrelated operating-system, panel or third-party vulnerabilities privately to their respective maintainers as well. Revoke or rotate exposed credentials before addressing public content and history.

## Public-reporting boundaries

A normal issue form in a public repository does not become private when an acknowledgment box is checked. Documentation and templates guide reporting; they cannot guarantee that nobody publishes details or replace VPS security controls.

See [privacy and redaction](PRIVACY.en.md), the [disclaimer](DISCLAIMER.en.md) and the [project homepage](../README.md).
