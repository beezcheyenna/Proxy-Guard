# Compatibility and limits

[English](COMPATIBILITY.en.md) · [简体中文](COMPATIBILITY.md) · [日本語](COMPATIBILITY.ja.md) · [Русский](COMPATIBILITY.ru.md) · [فارسی](COMPATIBILITY.fa.md)

Use firewall4 and nftables with LuCI. OpenWrt 24 uses IPK and OpenWrt 25.12 uses APK. For iStoreOS and ImmortalWrt, match the firmware’s package manager and kernel dependencies.

Only traffic that actually crosses the router can be protected. Verify your selected ingress, IPv4 and IPv6 paths, DNS and management access on one client before expanding the scope. Same-subnet routing may return directly around the router.

Official HTTPS is selected by default and uses a fixed address through local SOCKS. Third-party HTTPS is selectable and has independent timing and thresholds. Exit IPv4 verification is off initially. When enabled, the official response supplies the IPv4 by default. A third-party IP lookup retries its backup only after the primary times out.

Use the client’s supported forwarding modes and check both IP families on the devices you plan to protect. The [test matrix](TEST-MATRIX.en.md) lists the firmware, proxy clients and forwarding combinations, along with targeted results for the 1.0 packages.

| Proxy client | Forwarding modes | What to check |
| --- | --- | --- |
| PassWall | TCP REDIRECT with UDP TPROXY, or TCP/UDP TPROXY | Enable the client's IPv6 TPROXY support if you need IPv6 to go through the proxy. Check routed IPv6 traffic separately. |
| PassWall2 | TCP/UDP TPROXY | Confirm which local SOCKS listener is active. Verify any other forwarding mode on your setup. |
| OpenClash | REDIRECT with TPROXY, or TUN | Keep SOCKS authentication configured. Enable IPv6 UDP proxying in the client if you need UDP over IPv6. |
| Nikki | REDIRECT with TPROXY, or TUN | Keep the configured SOCKS credentials and verify both IP families in the selected mode. |
| HomeProxy | REDIRECT with TPROXY, or system TUN | Verify IPv6 UDP on your installed sing-box and firmware. |

A proxy core can affect results even when the client is detected correctly. NaiveProxy does not relay UDP. Native IPv4-only listeners do not establish IPv6 proxying. When diagnosing Xray SOCKS5 UDP, compare behavior with protection off and check the upstream core and forwarding mode.

For IPv6 UDP, verify that the client is actually proxying it. Proxied TCP and a working SOCKS handshake alone do not establish that the UDP path is working.

The LuCI application is available in English, Simplified Chinese, Japanese, Russian and Persian. The router theme and other applications supply their own translations. [Client log support](LOG_COMPATIBILITY.md)

## Protection mode prerequisites

Confirmation is blocked when software or hardware offload is enabled in UCI or an nft flowtable remains active, when `bridge-nf-call-iptables` or `bridge-nf-call-ip6tables` sends pure switched traffic through the IP firewall, or when ingress, kernel, bridge state, or the installed policy cannot be verified. Review those settings on the device.

Check vendor acceleration and switch-chip bypass on hardware. Verified no-NAT cases had a return path through the router. A same-subnet gateway may see only outbound traffic. Devices using another gateway over switching should remain unaffected. Inspect inter-subnet LANs, VPNs, containers, multiple bridges, and the IPv6 default route in your topology.
