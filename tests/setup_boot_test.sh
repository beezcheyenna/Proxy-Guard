#!/bin/sh
set -eu
[ -f /etc/pgvm-fixture ] || [ -f /.proxy-guard-test-root ] || { echo 'isolated Linux fixture required' >&2; exit 99; }
pg_init="${1:-${PG_SOURCE:-.}/package/root/etc/init.d/proxy-guard-setup}"
for pg_case in ready retry busy; do
 case "$pg_case" in ready) pg_boot_rc=0;; retry) pg_boot_rc=1;; busy) pg_boot_rc=75;; esac
 PG_BOOT_RC="$pg_boot_rc" sh -s "$pg_init" <<'PG_CHILD'
. "$1"
pg_opened=0
# Exercise the real init function; external effects are replaced in this process.
mkdir() { return 0; }
ucode() { return "$PG_BOOT_RC"; }
logger() { return 0; }
procd_open_instance() { pg_opened=$((pg_opened + 1)); }
procd_set_param() { :; }
procd_close_instance() { :; }
if ! start_service; then echo "initial recovery rc=$PG_BOOT_RC prevented retry supervision" >&2; exit 1; fi
[ "$pg_opened" -eq 1 ] || exit 2
PG_CHILD
 echo "PASS independent configuration watcher starts after initial boot recovery rc=$pg_boot_rc"
done
