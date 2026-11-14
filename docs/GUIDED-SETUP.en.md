# First configuration

[English](GUIDED-SETUP.en.md) · [简体中文](GUIDED-SETUP.md) · [日本語](GUIDED-SETUP.ja.md) · [Русский](GUIDED-SETUP.ru.md) · [فارسی](GUIDED-SETUP.fa.md)

## Guided setup

Open **Services → Proxy Guard** in LuCI to start the wizard.

1. **LAN ingress devices.** Select the LAN interfaces that carry traffic from the devices to protect. Verify the real device, for example `br-lan`, when a bridge contains several physical ports.
2. **Protection preset.** Choose monitoring, protection on proxy failure, or protection during startup and on failure. Select your proxy client if automatic detection cannot identify a single client.
3. **Scope and exceptions.** Review the source IPv4 ranges and the IPv6 scope. Confirm whether IPv6 protection should apply. Check local network, DNS and proxy port exceptions against the actual setup.
4. **Review settings.** Verify the SOCKS listener, selected scope and exceptions. Apply the settings and confirm in the dialog once the checks pass. Until you are ready to block, use the monitoring preset.

Run the wizard again from **Configuration and diagnostics**. You can also load the last confirmed settings or prepare defaults for review.

Open Services → Proxy Guard. Use the wizard to review ingress devices, the IPv4 and IPv6 scope, local exceptions, and your SOCKS port. Enable Monitor only first. Save & Apply runs a self-check and opens a 30-second confirmation window. A failed or unconfirmed change rolls back.

Only traffic that actually crosses the router can be protected. Verify your selected ingress, IPv4 and IPv6 paths, DNS and management access on one client before expanding the scope. Same-subnet routing may return directly around the router.

[Installation and use](USAGE.en.md#test-current-proxy) · [Troubleshooting and recovery](RECOVERY.en.md)
