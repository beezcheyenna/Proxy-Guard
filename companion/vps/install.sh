#!/bin/sh
# Explicit opt-in installer. Development tests never execute this on the host.
set -eu
[ "${1:-}" = --install ] && [ -n "${2:-}" ] || {
    printf '%s\n' 'Usage: sudo sh install.sh --install /path/to/agent.json' >&2; exit 2;
}
[ "$(id -u)" = 0 ] || exit 1
command -v python3 >/dev/null
command -v nft >/dev/null
if [ -d /run/systemd/system ] && command -v systemctl >/dev/null; then
    pg_init=systemd
elif [ -d /run/openrc ] && command -v rc-service >/dev/null && command -v rc-update >/dev/null; then
    pg_init=openrc
else
    printf "%s\n" "Unsupported service manager: systemd or running OpenRC is required." >&2
    exit 1
fi
pg_source_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
test -f "$2"
python3 - "$2" <<'PY'
import json,re,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
assert re.fullmatch(r'[A-Za-z0-9_-]{32,256}',c.get('agent_secret','')) and not c['agent_secret'].startswith('REPLACE_')
assert re.fullmatch(r'[A-Za-z0-9_-]{1,64}',c.get('device_id',''))
PY
# Validate the configuration that will actually run after a retained-config upgrade.
pg_effective_config="$2"
if [ -e /etc/proxy-guard-access/agent.json ]; then
    pg_effective_config=/etc/proxy-guard-access/agent.json
fi
python3 "$pg_source_dir/agent.py" --config "$pg_effective_config" --check-config
python3 "$pg_source_dir/agent.py" --config "$pg_effective_config" --check-kernel
install -d -m 700 /etc/proxy-guard-access
install -d -m 755 /opt/proxy-guard-access
for pg_module in agent.py egress.py monitor.py research.py probes.py discovery.py sensors.py control.py audit.py manage_units.py bootstrap.nft protection.py policy_trial.py safety.py maintenance.py reality_check.py telemetry.py LICENSE THIRD_PARTY_NOTICES.md LICENSING.md; do
    install -m 644 "$pg_source_dir/$pg_module" "/opt/proxy-guard-access/$pg_module"
done
if [ ! -e /etc/proxy-guard-access/agent.json ]; then
    install -m 600 "$2" /etc/proxy-guard-access/agent.json
fi
python3 /opt/proxy-guard-access/agent.py --config /etc/proxy-guard-access/agent.json --check-config
if [ "$pg_init" = systemd ]; then
    install -d -m 755 /etc/systemd/system
    install -m 644 "$pg_source_dir/proxy-guard-access.service" /etc/systemd/system/proxy-guard-access.service
    install -m 644 "$pg_source_dir/proxy-guard-access-policy.service" /etc/systemd/system/proxy-guard-access-policy.service
    python3 /opt/proxy-guard-access/manage_units.py --config /etc/proxy-guard-access/agent.json --init systemd
    systemctl daemon-reload
    systemctl enable --now proxy-guard-access-policy.service
    systemctl enable proxy-guard-access.service
    # enable --now leaves an already running old Python process untouched.
    systemctl restart proxy-guard-access.service
else
    install -d -m 755 /etc/init.d /etc/conf.d
    install -m 755 "$pg_source_dir/proxy-guard-access.openrc" /etc/init.d/proxy-guard-access
    install -m 755 "$pg_source_dir/proxy-guard-access-policy.openrc" /etc/init.d/proxy-guard-access-policy
    python3 /opt/proxy-guard-access/manage_units.py --config /etc/proxy-guard-access/agent.json --init openrc
    rc-update add proxy-guard-access-policy boot
    rc-update add proxy-guard-access default
    if ! rc-service proxy-guard-access-policy status >/dev/null 2>&1; then
        rc-service proxy-guard-access-policy start
    fi
    if rc-service proxy-guard-access status >/dev/null 2>&1; then
        rc-service proxy-guard-access restart
    else
        rc-service proxy-guard-access start
    fi
fi
