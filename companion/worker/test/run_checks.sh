#!/bin/sh
# Dedicated VM only. Native nft checks additionally use fresh network namespaces.
[ "$(hostname)" = cf-offline ] || exit 90
cd /opt/cf/src/companion/worker || exit 91
export WRANGLER_SEND_METRICS=false
python3 -B test/persistence_test.py > /opt/cf/persistence.log 2>&1
printf 'persistence:%s\n' "$?" > /opt/cf/check-status
node --test test/*.test.mjs > /opt/cf/fixed-v2.log 2>&1
printf 'unit_contract:%s\n' "$?" >> /opt/cf/check-status
unshare -n sh -c 'ip link set lo up; PG_CF_REAL_NFT=1 node --test test/contract.test.mjs' > /opt/cf/nft-contract.log 2>&1
printf 'nft_contract:%s\n' "$?" >> /opt/cf/check-status
npm run check:bundle > /opt/cf/bundle.log 2>&1
printf 'bundle:%s\n' "$?" >> /opt/cf/check-status
unshare -n python3 -B test/kernel_lease_test.py > /opt/cf/kernel-lease.log 2>&1
printf 'kernel_lease:%s\n' "$?" >> /opt/cf/check-status
touch /opt/cf/checks-done
