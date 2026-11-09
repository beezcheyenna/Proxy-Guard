#!/bin/sh
[ "$(hostname)" = cf-offline ] || exit 90
cd /opt/cf/src/companion/worker || exit 91
export WRANGLER_SEND_METRICS=false
unshare -n sh -c 'ip link set lo up; PG_CF_REAL_NFT=1 node --test test/contract.test.mjs' > /opt/cf/nft-final.log 2>&1
printf 'nft_contract_final:%s\n' "$?" > /opt/cf/final-status
node /opt/cf/node_modules/wrangler/bin/wrangler.js deploy --dry-run --minify --outdir /opt/cf/deploy-bundle > /opt/cf/minified-bundle.log 2>&1
printf 'minified_bundle:%s\n' "$?" >> /opt/cf/final-status
touch /opt/cf/final-done
