# Proxy Guard Cloudflare Worker

Optional **Pro control-plane** relay between OpenWrt and the VPS Agent through a configured Tunnel/VPC Service. It synchronizes authenticated policy and status; it does not carry ordinary proxy traffic and does not replace the independent SOCKS-path heartbeat.

- [Deployment and bindings](../../docs/CLOUDFLARE-WORKER.md)
- [Architecture and failure behavior](../../docs/PRO-COMPANION.md)
- [Protocol and upgrade compatibility](../../docs/EDITION-MATRIX.md)
- [VPS Agent installation](../../docs/LINUX-AGENT-INSTALL.md)

The npm project version is 0.2.0; Agent control responses use protocol v3. Neither number alone proves capability compatibility. Use the matching release source and verify bindings, independent secrets and the Agent response before applying policy.

Local tests and a deployed-cloud test are different. Follow [contributing](../../CONTRIBUTING.md); do not commit Wrangler secrets or live deployment identifiers. Direct HTTPS control does not require this Worker.
