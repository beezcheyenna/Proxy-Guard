# Source, builds, and verification

[English](BUILDING.en.md) · [简体中文](BUILDING.md) · [日本語](BUILDING.ja.md) · [Русский](BUILDING.ru.md) · [فارسی](BUILDING.fa.md)

The package recipes declare Standard `0.3.0-21` and Pro `0.3.1-5`. This page covers the source tree, IPK and APK builds, and development tests. Verify each build using the SHA256 sums for its own artifacts.

## Source layout

| Path | Contents |
| --- | --- |
| `package/root/` | Standard package files |
| `package/pro/root/` | Pro package files |
| `package/Makefile` | OpenWrt package metadata and installation/removal hooks |
| `package/i18n/` | Message sources, PO catalogs, and generation metadata for the five languages |
| `companion/vps/` | Linux Agent, example configuration, and scoped installer |
| `companion/worker/` | Worker template, dependency lockfile, and tests |
| `tests/` | Unit, frontend, and native or network regressions requiring a dedicated environment |
| `LICENSES/` | License texts and copies of upstream notices |

Standard and Pro have separate build entry points. The Linux Agent and Worker are under `companion/`.

## Build IPKs separately

Use Python 3 in a Linux build checkout. The source includes generated translations. If the message sources are unchanged, the build needs neither a LuCI download nor the translation tools. Choose one command below to build Standard, Pro, or both, respectively.

```sh
python3 -B tools/build_ipk.py --only standard
python3 -B tools/build_ipk.py --only pro
python3 -B tools/build_ipk.py
```

The Pro-only build checks for file ownership conflicts with the base package. `dist/` contains the packages, `SHA256SUMS`, and file manifests. The builder writes artifacts without running installation hooks or contacting a device.

If you edit the message sources, obtain `po2lmo` from the matching official LuCI source. Add `--only pro` to regenerate only the Pro catalogs and dedicated pages.

```sh
python3 -B tools/build_translations.py /path/to/po2lmo
```

Regenerate the metadata with the catalogs and diagnostic mappings. LuCI tools, SDKs, cross-compilers, and proxy cores come from their respective upstreams.

## OpenWrt SDK

Place `package/` under the matching OpenWrt SDK's `package/` directory and select `luci-app-proxy-guard` or `luci-app-proxy-guard-pro` through the standard SDK workflow. Get dependencies from the matching target feeds. The `all` architecture label identifies a script package.

Build APKs for 25.12 natively with the matching official SDK. `tools/build_ipk.py` builds IPKs only. The APK revisions are `0.3.0-r21` and `0.3.1-r5`. The SDK recipe preserves the APK installation, upgrade, and removal hooks and expresses Pro's minimum Standard version in the package manager's format.

The SDK recipe and Python builder use the same installation trees and select the hooks for their package manager. `tools/test_sdk_staging.py` compares staging, permissions, and hooks for both built packages in a dedicated VM with the fixture marker. A full SDK build exercises the toolchain separately.

Package installation trees contain their licenses and notices. Pro installs its licensing files separately from Standard.

## Basic tests

Run this entry point in a prepared, dedicated Linux or OpenWrt test VM:

```sh
python3 -B tools/test_standard_pro.py
```

The entry point requires Python 3, Node.js, and make, among other dependencies. Some version and SDK-staging contracts require the VM's `/etc/pgvm-fixture` marker, supplied by the dedicated image. Keep this marker confined to the fixture image.

Native Lua/ucode, package hooks, real LuCI/UCI/RPC, browsers, network namespaces, TCP/UDP packets, and cold boot require the corresponding OpenWrt images and fixtures. Some drivers also require a particular working directory. Prepare the environment specified by the scripts. The repository does not supply VM disks or deployment credentials.

The LMO and real LuCI gettext checks require upstream `cbi.js` from the matching official source, set through `PG_LUCI_CBI`. Record mock and real-environment integration results separately.

## Worker

Install tooling from the lockfile in a separate Linux development checkout. Use controlled test resources for cloud checks.

```sh
cd companion/worker
npm ci
npm test
```

Local `npm test` covers the local runtime. See the [Worker guide](CLOUDFLARE-WORKER.en.md) for deployment commands, secrets, and bindings. Verify the bindings, credentials, and connections for the chosen account before deployment.

## Test coverage

The project has exercised logic, installation, UI, recovery, IPv4/IPv6, cold startup, multiple systems, and Cloudflare integration. Run the applicable checks after changing behavior. See [compatibility](COMPATIBILITY.en.md) and the [test matrix](TEST-MATRIX.en.md).
