# Recovery

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

Applies to Standard `0.3.0-21` and Pro `0.3.1-5`. Router protection and the remote VPS policy have separate controls.

Router disable and confirmation-timeout procedures were verified in an isolated OpenWrt 24.10.8 VM. VPS removal was verified in isolated Ubuntu and Alpine VMs and in the earlier four-distribution lifecycle tests. For firmware-specific rescue modes or filesystem damage, use the relevant vendor procedure. See the [test matrix](TEST-MATRIX.en.md).

## 1. Keep management access

- Keep an SSH session, serial console, VM console, or VPS provider console available. If all network management is unavailable, use an independent console and the firmware's documented failsafe procedure.
- Disabling protection can let affected clients connect directly. Disconnect those clients from the external network first when appropriate.
- Keep system firewall tables, lock files, and pending transaction files intact. A global firewall flush or deleting transaction state can interrupt management and recovery.

## 2. LuCI is unavailable, but router SSH or console works

Run these read-only checks as root:

```sh
/usr/libexec/proxy-guard status
ubus list proxy_guard
nft list tables
logread -e proxy-guard
```

A missing ubus object, a failed LuCI page, and an unavailable proxy have different causes. Preserve the errors and keep existing ACLs. `/etc/init.d/proxy-guard stop` may leave nftables blocking in place. Save logs privately before reboot and redact them before public reporting. RAM logs are generally lost on reboot.

### Explicitly disable Standard protection

Use this procedure with a parseable UCI configuration, an independent management path, and acceptance of possible direct client traffic. Back up first:

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery
```

After checking that the backup succeeded:

```sh
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart
```

This registers the explicit disable as a confirmed configuration, supersedes any pending enable, then restarts the service. That prevents a background observer from reapplying the old trial. An edit to UCI or reload of a stopped service alone leaves the transaction unresolved.

Verify:

```sh
uci -q get proxy_guard.main.enabled
/usr/libexec/proxy-guard status
nft list tables
```

Expect `0`, `disabled`, and enforcement `off`. Standard's `inet proxy_guard` table should be gone, with `fw4` and other components' rules present. Verify actual access against the existing routing, firewall, and proxy configuration.

For an unparseable configuration, restore your own trusted backup of `/etc/config/proxy_guard` from the matching version, then disable explicitly. If the program or a dependency is damaged, keep the console and repair the relevant package.

## 3. Configuration confirmation expired

After the self-check succeeds, the router starts a **30-second confirmation timer**. Its independent observer rolls back an unconfirmed change even if the browser closes or loses its connection. Reconnect, compare the state and previous configuration, and verify the live rules before revising the draft. Keep `pending.json` intact. If the observer, storage, or runtime has failed, use the explicit disable from the console and inspect the rules.

## 4. Blocking remains after a process failure

The kernel enforces existing rules when a process exits. Allowances can expire. Save logs, check storage, dependencies, UCI, and interfaces, then repair and restart the plugin while retaining protection. For a temporary release, use the explicit disable in section 2. Avoid competing manual processes and preserve lock files. Test with one client before re-enabling and confirming.

## 5. Pro is unreachable and VPS rules remain

Stopping synchronization stops renewals. Household leases can expire while static allowlists and selected-port policies remain. SSH rescue needs prior enablement and confirmation and the configured loss of both authenticated heartbeats. System firewall rules, SSH authentication, and provider security groups still apply. Read remote state when a trial outcome is unknown. Keep policy revisions and operation IDs intact. A management endpoint that shares the proxy port can be affected, so keep a separate console.

If control is available, use Pro's removal and confirmation flow before stopping synchronization. Verify the actual state on the VPS.

### Remove the component's rules from the VPS console

Disable automatic synchronization on the router and keep it disabled during recovery. Keep VPS console access and the system firewall. Privately back up the effective `/etc/proxy-guard-access/agent.json`, keys, certificates, and state. From `companion/vps` in trusted source matching the installed version, choose your system.

Ubuntu, Debian, or Rocky Linux:

```sh
sudo sh ./uninstall.sh --remove
sudo systemctl status proxy-guard-access proxy-guard-access-policy --no-pager
sudo nft list tables
```

Alpine Linux as root:

```sh
sh ./uninstall.sh --remove
rc-service proxy-guard-access status
rc-service proxy-guard-access-policy status
nft list tables
```

The post-removal status query can report an absent service or return a nonzero status. If removal itself fails, retain the error and stop. The remover cleans this component's services, startup dependencies, and owned rules. It keeps the configuration, keys, and programs, and leaves NAT, FORWARD, and other rules intact. Verify the rules and test management and service ports. Check the table name in the effective configuration. `pg_vps_access` is the default. If ownership cannot be established from a damaged configuration, recover it before deleting tables.

Reinstalling can restore the retained policy. Review the configuration and state first, then verify control, dynamic leases, selected-port modes, and SSH. Keep each instance's own state and increasing policy revision.

## 6. Verify recovery

From one protected client check LAN, DNS, management, IPv4/IPv6, new and existing connections, failure, and recovery. Keep independent management access, then reboot the **router running Proxy Guard** to verify boot protection.

[Installation and use](USAGE.en.md) · [Linux Agent installation](LINUX-AGENT-INSTALL.en.md) · [Control paths and failure behavior](PRO-COMPANION.en.md) · [Security reporting](SECURITY.en.md)
