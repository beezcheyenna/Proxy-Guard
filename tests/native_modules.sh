#!/bin/sh
# Only inside a disposable disconnected OpenWrt test VM/container.
set -eu
test -f /etc/pgvm-fixture
export PG_SOURCE="${PG_SOURCE:-/src}"
for script in core_test.lua client_binding_test.lua feature014_test.lua resource_metrics_test.lua native016_test.lua heartbeat_api_test.lua heartbeat_log_test.lua public_heartbeat_test.lua; do
    lua "$PG_SOURCE/tests/$script"
done
stage=/tmp/pg-log-languages
mkdir -p "$stage"
cp "$PG_SOURCE/package/root/usr/lib/proxy-guard/fast-state.uc" "$stage/"
cp "$PG_SOURCE/package/root/usr/lib/proxy-guard/passwall-log.uc" "$stage/"
for script in fast_state_test.uc heartbeat_fast_test.uc passwall_log_test.uc passwall_log_languages.uc passwall_log_corpus.json; do
    cp "$PG_SOURCE/tests/$script" "$stage/"
done
for script in fast_state_test.uc heartbeat_fast_test.uc passwall_log_test.uc passwall_log_languages.uc; do
    ucode "$stage/$script"
done
