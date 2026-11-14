# Troubleshooting and recovery

[English](RECOVERY.en.md) · [简体中文](RECOVERY.md) · [日本語](RECOVERY.ja.md) · [Русский](RECOVERY.ru.md) · [فارسی](RECOVERY.fa.md)

**Stopping the Proxy Guard service can leave its firewall rules blocking traffic.** Use the explicit disable procedure below to release the plugin’s block.

**A passing “Test current proxy” result confirms the test traffic only.** A schedule, API request or separate failed health check can still keep protection blocking.

## Read the recovery status

The status panel shows current enforcement separately from the latest completed probe. If the firewall rules need verification, use **Check settings and runtime environment** before relying on the status. Use **Test current proxy** to check the SOCKS route.

If the proxy connection fails, check whether your client still exposes its local SOCKS listener. After a firewall reload or proxy restart, allow the configured checks to confirm recovery.

Use the router console or a separate management route before testing recovery. If a new configuration loses connectivity, let the confirmation window expire. The previous configuration is restored after timeout or reboot during an unconfirmed trial.

If you can reach the console and need to explicitly disable protection, run the commands below on the router. Confirm the reported enforcement is off and test access from a protected client.

```sh
umask 077
cp /etc/config/proxy_guard /root/proxy_guard.before-recovery &&
uci set proxy_guard.main.enabled='0' &&
uci commit proxy_guard &&
printf '%s\n' '{}' | ucode /usr/lib/proxy-guard/setup-lock.uc apply &&
/etc/init.d/proxy-guard restart &&
ubus call proxy_guard status
```

Only traffic that actually crosses the router can be protected. Verify your selected ingress, IPv4 and IPv6 paths, DNS and management access on one client before expanding the scope. Same-subnet routing may return directly around the router.

[Installation and use](USAGE.en.md)
