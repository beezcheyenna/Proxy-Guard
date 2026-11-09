#!/bin/sh
set -eu
[ "$#" = 1 ] && [ "$1" = --remove ] || { printf '%s\n' 'Usage: sudo sh uninstall.sh --remove'; exit 2; }
[ "$(id -u)" = 0 ] || exit 1
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null; then
    systemctl stop proxy-guard-access.service
    python3 /opt/proxy-guard-access/agent.py --config /etc/proxy-guard-access/agent.json --cleanup
    python3 /opt/proxy-guard-access/manage_units.py --config /etc/proxy-guard-access/agent.json --init systemd --remove
    systemctl disable proxy-guard-access.service proxy-guard-access-policy.service
    systemctl stop proxy-guard-access-policy.service
    rm -f /etc/systemd/system/proxy-guard-access.service /etc/systemd/system/proxy-guard-access-policy.service
    systemctl daemon-reload
elif [ -d /run/openrc ] && command -v rc-service >/dev/null; then
    rc-service proxy-guard-access stop
    python3 /opt/proxy-guard-access/agent.py --config /etc/proxy-guard-access/agent.json --cleanup
    python3 /opt/proxy-guard-access/manage_units.py --config /etc/proxy-guard-access/agent.json --init openrc --remove
    rc-update del proxy-guard-access default
    rc-update del proxy-guard-access-policy boot
    rc-service proxy-guard-access-policy stop
    rm -f /etc/init.d/proxy-guard-access /etc/init.d/proxy-guard-access-policy
else
    printf '%s\n' 'Unsupported service manager; owned rules have not been changed.' >&2
    exit 1
fi
printf '%s\n' 'Owned services and firewall tables removed. Private configuration, keys and program files retained.'
