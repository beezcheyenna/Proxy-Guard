# Install the Linux VPS Agent for Pro

[English](LINUX-AGENT-INSTALL.en.md) · [简体中文](LINUX-AGENT-INSTALL.md) · [日本語](LINUX-AGENT-INSTALL.ja.md) · [Русский](LINUX-AGENT-INSTALL.ru.md) · [فارسی](LINUX-AGENT-INSTALL.fa.md)

Pro remote features require Standard and Pro on OpenWrt and the Agent on Linux. Choose direct HTTPS or a Cloudflare Worker with Tunnel/VPC. Install IPK/APK on the router and use the Python installer on the VPS. Linux requires Python 3.10+, nftables, the matching kernel features, and systemd or OpenRC. See [compatibility](COMPATIBILITY.en.md) and the [test matrix](TEST-MATRIX.en.md).

## 1. Install dependencies

Choose the commands for your distribution.

**Ubuntu / Debian**

```sh
sudo apt update
sudo apt install -y python3 nftables iproute2 ca-certificates
```

**Rocky Linux**

```sh
sudo dnf install -y python3 nftables iproute ca-certificates
```

**Alpine Linux, as root**

```sh
apk add python3 nftables iproute2 coreutils ca-certificates
```

Check the interpreter used by the services.

```sh
/usr/bin/python3 --version
```

`/usr/bin/python3` must be at least 3.10. A different Python on your PATH or in a virtual environment does not change the service interpreter. The installer checks the config and nftables kernel features, including dynamic sets and connection limits. Use modules for the installed kernel. The Agent installs its own policy service.

## 2. Unpack the release and prepare configuration

Upload `proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz` to the VPS. In the directory containing the archive:

```sh
tar -xzf proxy-guard-source-0.3.0-21-pro-0.3.1-5.tar.gz
cd Proxy-Guard/companion/vps
cp agent.example.json agent.json
chmod 600 agent.json
python3 - <<'PY'
from pathlib import Path
import json
import secrets

path = Path('agent.json')
config = json.loads(path.read_text())
config['agent_secret'] = secrets.token_urlsafe(32)
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o600)
PY
```

| Setting | Value |
| --- | --- |
| `device_id` | Device identity, such as `home`, shared with the router and the Worker when used. |
| `agent_secret` | Independent random secret matching the Worker's `AGENT_SECRET`. Keep it off the router. |
| `services` | Actual process names and TCP/UDP listeners for the deployed proxy. |
| `managed_units` | Dependencies named `name.service`. On OpenRC this maps to the name without `.service`. SSH is excluded. |
| `egress.panel_config_path` | Optional trusted local Xray JSON path. External measurement defaults to off. |
| SSH, path heartbeat, maintenance | Configure and enable separately. |

The Agent monitors and manages an already installed proxy. For a 3x-ui-managed Xray, check the actual process name and supported USR1 behavior and select the appropriate adapter.

## 3. Choose a control path

### Cloudflare Worker with Tunnel/VPC

Normally set `bind=127.0.0.1`, `port=8788`, and `public_control=false`. The local `cloudflared` connects to the loopback API. Follow the [Worker guide](CLOUDFLARE-WORKER.en.md) for Tunnel, VPC Service, and `VPS_API`. Use the same `DEVICE_ID` throughout, a separate `DEVICE_TOKEN` on the device and Worker, and `AGENT_SECRET` only between Worker and Agent. Select Cloudflare on the router's VPS access page and enter the Worker HTTPS base URL, device identity, and device token.

### Direct HTTPS

Set `public_control=true`, the listener address, a valid `tls_cert` and `tls_key`, and an independent `direct_token`. On the router choose direct HTTPS and enter the Agent HTTPS base URL, device identity, and `direct_token`. Credentials use 32–256 letters, digits, underscores, or hyphens. Replace example values.

**Verify that either control path goes directly, outside the proxy.** Route the independent path heartbeat through local SOCKS.

<a id="control-and-path"></a>

### URLs, secrets, and the independent proxy path

| Purpose | Router settings | Matching server settings |
| --- | --- | --- |
| Cloudflare control | Worker HTTPS base URL, device identity and token | `DEVICE_ID` and `DEVICE_TOKEN`. `AGENT_SECRET` pairs with Agent `agent_secret`. |
| Direct HTTPS control | Agent HTTPS base URL, device identity and token | `device_id`, `direct_token`, public listener and TLS. |
| Independent path heartbeat | Enable path monitoring, Agent HTTPS base URL, separate path token | `path_token`, through SOCKS to `/v1/direct/path-heartbeat`. |

Enter base URLs without `/v1/...`. Use separate secrets. Verify authentication on both paths before enabling managed SSH.

- Direct control needs the actual public source IP of the household connection. The Agent does not recover it from forwarding headers. Use a direct endpoint with source visibility. The same HTTPS base URL can serve the path heartbeat over SOCKS with its own token.
- With Cloudflare, the loopback HTTP API is for the local Tunnel. Provide a separate HTTPS path endpoint reachable through the proxy. If a TLS reverse proxy forwards it, expose only `/v1/direct/path-heartbeat` and preserve the Bearer header. Direct control still needs its actual source IP.
- If the Agent listens on public HTTPS, configure the public flag, direct token and certificates, and match the Tunnel/VPC target protocol and port. Certificate issuance, renewal, and reverse proxy configuration are external.

Keep the control and heartbeat endpoints reachable before a lease is renewed. Verify actual direct routing and SOCKS routing separately.

## 4. Install and check

Run the commands from `companion/vps`.

**Ubuntu / Debian / Rocky Linux**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
sudo python3 agent.py --config "$PWD/agent.json" --check-kernel
sudo sh ./install.sh --install "$PWD/agent.json"

sudo systemctl status proxy-guard-access-policy proxy-guard-access --no-pager
sudo journalctl -u proxy-guard-access -n 50 --no-pager
```

**Alpine Linux, as root**

```sh
python3 agent.py --config "$PWD/agent.json" --check-config
python3 agent.py --config "$PWD/agent.json" --check-kernel
sh ./install.sh --install "$PWD/agent.json"

rc-service proxy-guard-access-policy status
rc-service proxy-guard-access status
```

The program is installed under `/opt/proxy-guard-access`. The active config is `/etc/proxy-guard-access/agent.json`. The installer starts the policy and Agent services and preserves an existing active configuration. Edit and validate the actual configuration to change an installed instance. Save and apply in LuCI, check synchronization, leases, and service state, and explicitly select the managed ports.

## 5. SSH rescue and panel ports

Managed SSH defaults to off. Once enabled and verified with a working management session and both paths, rescue follows continuous loss of both authenticated heartbeats. The default delay is **60 seconds**.

New configurations permit public rescue by default. Duration `0` lasts until household authorization recovers. You can limit rescue to management sources or choose `30`–`3600` seconds. An existing explicit duration, including `600`, is preserved. Public rescue increases exposure. After timed rescue expires, a changed household IP without a permitted management source can prevent a new SSH login. The system firewall, SSH authentication, and provider rules still apply.

Separate unselected 3x-ui panel, API, and subscription ports follow the system firewall. Selected or shared IP/protocol/port endpoints follow the selected rule. Check listeners before configuring.

## 6. Port modes and raw configuration

Rules inherit the default mode or choose allowlist, standard rate limits, or observation. Set sources, thresholds and durations per rule. The client checks remote capabilities before applying. New capabilities can require an Agent update and a Worker update for Cloudflare. The two router editors cover local protection and VPS access UCI. Agent listeners, TLS, and maintenance belong in the Agent config. The [Worker guide](CLOUDFLARE-WORKER.en.md) covers the separate cloud resources.

## 7. Upgrade and back up

Keep SSH or a console and back up the active config, TLS keys and certificates, matching source, and configured persistent state and operation records. Keep backups private. Keep each instance's state and revisions.

Run the installer from the new `companion/vps` source. Use the first command on systemd or the second as root on Alpine.

```sh
# Ubuntu / Debian / Rocky Linux
sudo sh ./install.sh --install /etc/proxy-guard-access/agent.json

sh ./install.sh --install /etc/proxy-guard-access/agent.json
```

The installer checks the active configuration and kernel, updates the files and services, and restarts the Agent. Verify service state, authenticated control, policy revision, capabilities, and selected ports. Check config and state compatibility before a downgrade.

## 8. Verify end to end

- Confirm the policy and Agent services, the actual proxy process and TCP/UDP listeners, and a real proxy request.
- Verify TLS, identity, independent secrets, direct control routing, and, if used, the fixed VPC binding and Tunnel. Check a fresh home-IP lease in LuCI. An address change requires observation and sync.
- Try one rule and confirm it. Check allowed and restricted sources, unselected ports, panel/subscription, SSH and Docker paths separately.
- Verify the path heartbeat, rescue, and maintenance individually before authorizing them. Inspect the actual rules and recovery after control and proxy loss, an unconfirmed trial, and reboot.

| Symptom | Check |
| --- | --- |
| Install preflight fails | Python version, running init, nftables expressions and modules. |
| HTTPS or authentication fails | Certificate chain and validity, clocks, listener, identity and matching token. Keep TLS verification enabled. |
| Worker answers, Agent is unreachable | Tunnel, fixed target, binding ID, and Agent loopback listener. |
| Control works, path heartbeat fails | Independent HTTPS entry, path token, local SOCKS, actual proxy exit. |
| Panel or subscription also restricted | Selected rules or a shared IP/protocol/port. |
| Rescue is active, SSH fails | SSH service/authentication, system firewall, provider security group. |
| Configuration changed, status did not | Active config rather than sample, validation and restart, pending trial or unknown result. |

See [Pro architecture and failure behavior](PRO-COMPANION.en.md) and [recovery](RECOVERY.en.md).

## 9. Remove the Agent

From the retained matching `companion/vps` source, choose the first command on systemd or the second as root on Alpine.

```sh
sudo sh ./uninstall.sh --remove

sh ./uninstall.sh --remove
```

Removal cleans only the component's services and rules, retaining configuration, secrets, and programs. See [recovery](RECOVERY.en.md) for verification.

[VPS Agent directory guide](../companion/vps/README.md)
