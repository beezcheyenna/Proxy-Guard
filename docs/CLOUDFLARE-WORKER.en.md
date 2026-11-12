# Cloudflare Worker for Pro

[English](CLOUDFLARE-WORKER.en.md) · [简体中文](CLOUDFLARE-WORKER.md) · [日本語](CLOUDFLARE-WORKER.ja.md) · [Русский](CLOUDFLARE-WORKER.ru.md) · [فارسی](CLOUDFLARE-WORKER.fa.md)

The Worker authenticates devices, observes the household public IP, and relays policies using Agent protocol v3. It requires compatible Pro and VPS Agent versions. Each Worker uses one device identity and a fixed `VPS_API` binding.

## Reproducible dependencies and local checks

Use Node.js 22+. `package-lock.json` pins Wrangler 4.156.0 and Miniflare 5.20261023.3-beta. Deployment uses the installed Wrangler. Check the runtime again after changing the tooling or the compatibility date in `wrangler.jsonc` (currently `2026-11-01`).

From `companion/worker` in a dedicated Linux test checkout:

```sh
npm ci
npm test
npm run test:persistence
npm run check:bundle
```

`npm ci` normally downloads packages on first use. Once the dependencies are installed, local tests can run without contacting Cloudflare. Deployment and live verification require authorized cloud resources.

Real nftables checks run in private network namespaces in a disposable VM. `test/run_checks.sh` and `test/run_final.sh` require matching fixtures and a working directory. Maintenance tests record actions without restarting the system. `kernel_lease_test.py` verifies that a 120-second kernel lease is gone after 125 seconds and is absent after a cold boot.

## Deployment

Install and verify the [Linux Agent](LINUX-AGENT-INSTALL.en.md) separately. Run `cloudflared` for a dedicated Tunnel on the same VPS. The VPC Service points to the Agent's loopback listener, typically HTTP `127.0.0.1:8788`. Bind `VPS_API` to the Service ID.

- Set `DEVICE_ID` to match the Agent.
- Use a random `DEVICE_TOKEN` for device-to-Worker authentication and a separate `AGENT_SECRET` for Worker-to-Agent authentication.
- Both secrets require 32–256 letters, digits, underscores, or hyphens. `REPLACE_` placeholders are rejected.
- `.dev.vars.example` names the required secrets. Keep real values in private secret storage. Keep `.dev.vars`, `.env`, and secret files out of version control.
- Set the Service ID in `wrangler.jsonc`. Configure secrets first, or pass test secrets with `npm run deploy -- --secrets-file /path/to/private-secrets.json`. The JSON file has `DEVICE_TOKEN` and `AGENT_SECRET` fields. The example has no live resource ID.

The Service's configured host and port determine the destination even if a fetch URL specifies another host or port. Verify the Service configuration and binding in Cloudflare.

## API and data

Send a distinct application User-Agent such as `ProxyGuardPro/0.2.0`. For Cloudflare error `1010`, check the client identity and account security policy. Keep security checks enabled.

All routes require HTTPS and a device Bearer token. Query strings are rejected.

| Route | Behavior |
| --- | --- |
| `/v1/observe` | Reports the public IP seen by Cloudflare. Rejects Worker subrequest sources and reserved addresses. Leaves the Agent lease as it was. |
| `/v1/sync` | Requires the same IP just observed. Signs the exact JSON bytes with a separate HMAC-SHA256 secret and a new request ID. The Agent checks signature, freshness, replay, and revision. An unchanged revision can renew only the same policy. IPv4 and IPv6 renew independently for 120–86400 seconds. Leases expire after synchronization stops. |
| `/v1/status` | Returns fields needed to confirm policy, lease, health, and maintenance. Requests `include_analysis=false` and excludes management addresses, listener lists, events, authentication-source details, and unknown extensions. Reading status leaves leases as they were. |
| `/v1/command` | Accepts `restart_xray` and `reboot_vps`, with a fixed operation ID, policy revision, and a 1–60-second validity window. Enable each action on the Agent. If the outcome is unknown, query or retry with the same ID to use deduplication. The Worker returns fixed rejection codes and limits upstream response bodies to 32768 streamed bytes. |

The Agent computes `expires_at` from the monotonic lease remaining after firewall application, so a slow apply cannot inflate the reported lease.

## Verification

The Worker, VPC Service, Tunnel, Agent, and OpenWrt client have been tested together. Verify your own bindings, credentials, and real client requests after deployment. Create the Tunnel and VPC Service and configure the binding before running the Wrangler deployment from `companion/worker/`.

Official Cloudflare references:

- <https://developers.cloudflare.com/workers-vpc/api/>
- <https://developers.cloudflare.com/workers-vpc/get-started/>
- <https://developers.cloudflare.com/workers/platform/deploy-buttons/>
- <https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/>

## Versions and deployment scope

The [Worker tooling project](../companion/worker/package.json) has npm version `0.2.0`. Pro uses its own package revision. Check the manifest and lockfile for Node.js and tool requirements. Set up the VPS, Agent, Tunnel, and VPC Service separately.

## Read-only egress candidates

`POST /v1/egress-info` uses the device Bearer token and nonempty JSON `{ "device_id": "home" }`. It relays only to the corresponding HMAC endpoint on the fixed `VPS_API`. The result contains only `interface`, `panel`, and `measured` evidence. Empty, stale, or ambiguous results carry warnings. Select an expected egress value explicitly. Measurement defaults to off. The route leaves leases, control heartbeats, and pending policy confirmations as they were. Older Agents return 501 `egress_info_unsupported`. See [the Agent API](VPS-EGRESS-INFO.md) for the protocol, fixed measurement target, and integration.

[Worker directory guide](../companion/worker/README.md)
