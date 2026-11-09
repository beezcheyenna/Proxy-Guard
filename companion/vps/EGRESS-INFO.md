# Read-only IPv4 egress candidates (schema 1)

This endpoint provides advisory evidence for the setup wizard. It never chooses or writes an expected IPv4, applies a policy, renews a household lease, notes an SSH control/proxy heartbeat, performs maintenance, or confirms/extends a pending configuration rollback. A network-interface address, a panel bind hint and a host-default-route source-IP observation are different evidence. They do not establish the selected proxy business path.

## API

* Cloudflare: `POST /v1/egress-info`, existing device Bearer token and JSON `{"device_id":"home"}`. Use a nonempty object with native `luci.jsonc`; an empty Lua table serializes as an array.
* Agent relay: signed `POST /v1/egress-info`, existing HMAC key over `device_id`, `issued_at`, unique `request_id`, and `purpose:"egress-info"`. The purpose is rejected on other routes, so an advisory request cannot be replayed as a status heartbeat. A replay or expired nonce is rejected under the existing authentication rules.
* Direct: `GET /v1/direct/egress-info`, existing direct Bearer token and existing HTTPS/public-bind requirements. It does not use the peer IP as a candidate.

An example with no public candidate:

```json
{
  "ok": true,
  "protocol": 3,
  "egress_info_schema": 1,
  "generated_at": 1700000000,
  "status": "unavailable",
  "candidates": [],
  "ambiguous": false,
  "business_egress_verified": false,
  "warnings": [
    "measurement_disabled",
    "no_public_ipv4_candidate"
  ],
  "measurement": {
    "state": "disabled",
    "checked_at": null,
    "stale": true
  }
}
```

Each candidate is `{"ipv4":"8.8.8.8","evidence":[{"source":"interface","checked_at":1700000000,"scope":"host_interface"}]}`. Example addresses in this document are schema illustrations, not detected values or configuration recommendations.

`source` is `interface`, `panel`, or `measured`; its matching `scope` is `host_interface`, `panel_config`, or `host_default_ipv4`. Detection times and `generated_at` are UTC Unix seconds. Freshness uses monotonic time. Candidates are deduplicated by IPv4, at most eight are returned, and each has at most three evidence entries. Measured candidates survive truncation ahead of interface/panel-only hints. More than one distinct public IPv4 produces an ambiguity warning. `business_egress_verified` is always false in schema 1. Consumers must not automatically copy the first candidate, their own `/observe` result, a panel hostname, or a REALITY target into expected-exit configuration.

`status` is `available`, `partial`, or `unavailable`. It describes advisory data, independently of service health. `measurement.state` is `disabled`, `pending`, `fresh`, `stale`, `unavailable`, or `conflict`. The last successful measurement remains explicitly stale after an error or after twice its sampling interval. A disabled measurement is not a reason to disable working service protection.

Warnings are fixed codes: `non_public_ipv4_omitted`, `no_public_ipv4_candidate`, `interface_unavailable`, `panel_unavailable`, `panel_hint_unverified`, `panel_hint_ignored`, `measurement_disabled`, `measurement_pending`, `measurement_failed`, `measurement_stale`, `measurement_disagreement`, `multiple_public_ipv4_candidates`, `host_default_not_business_egress`, and `candidates_truncated`. UI translations belong in the existing catalogs.

Authenticated empty/stale/ambiguous reports return 200. Direct authentication fails with 401; signed authentication/nonce failures use the existing 403 response. Bad bodies return 400. Worker relay to an older Agent returns 501 `egress_info_unsupported`; unavailable VPC or invalid upstream data returns a safe 502. A collector exception returns a safe 503. No errors contain raw paths, panel data, interface names, measurement bodies or credentials. HTTP responses retain `Cache-Control: no-store`; internal advisory caches are memory-only.

## Agent configuration and limits

The optional `egress` object has only these keys:

```json
{
  "panel_config_path": "",
  "measure_enabled": false,
  "measure_interval": 300
}
```

Panel collection defaults off. An explicitly configured regular JSON file must belong to the Agent user, have no group/world write permission, and not be a final-component symlink. Reading is limited to 64 KiB. For 3x-ui's generated Xray configuration, only numeric IPv4 values in `inbounds[].listen` and `outbounds[].sendThrough` are considered unverified hints. REALITY targets/destinations, outbound remote servers, domains and credentials are never searched or resolved.

Interface collection executes fixed `ip -j -4 address show` arguments with a two-second timeout and a 64 KiB accepted-output limit. Missing tools or nonpublic-only/NAT interfaces return warnings instead of guessed Internet addresses. Local collection is cached for fifteen seconds.

Measurement is disabled by default. If enabled, a background sampler contacts only the fixed `https://api.ipify.org/` IPv4 plaintext API documented by [ipify](https://www.ipify.org/). No URL, shell command, refresh or target argument is accepted from requests or configuration. DNS results are filtered to public IPv4 and the selected address is pinned to a TLS socket with the fixed hostname for SNI and certificate verification. The implementation does not use proxy environment variables, redirects, retries or credentials. Socket operations have a two-second timeout, response bodies are limited to 256 bytes, and the isolated measurement child has a five-second total timeout, including DNS. Sampling interval is 60–3600 seconds (default 300). Endpoint reads never start measurements. The result is labelled host-default IPv4, not actual Xray/client business egress.

## Integration

The Agent entry point validates `egress` configuration during `--check-config`. The installer includes `egress.py`, and `control.Server` owns the collector lifecycle.

Wizard reads use the connection-only configuration path, including when synchronization is disabled. They retain endpoint confirmation, session-scoped staged credentials and existing RPC permissions. Reading candidates does not apply or commit a policy, queue maintenance, or perform network requests inside the RPC handler.

## Isolated basic tests

Run only in an owned test VM, using the candidate/frozen files being evaluated:

```sh
python3 -B companion/vps/test_egress.py
cd companion/worker
node --test test/egress.test.mjs test/worker.test.mjs test/regression.test.mjs test/contract.test.mjs
```

Collector tests use controlled injected measurements and make no live reflector requests. The HTTP contract uses the actual Agent server with a temporary in-memory firewall driver; it does not modify real nft rules. These are isolated logic and API-contract tests; they do not replace installation, real proxy-path or Cloudflare deployment checks.
