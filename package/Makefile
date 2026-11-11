include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-proxy-guard
PKG_VERSION:=0.3.0
PKG_RELEASE:=21

# Pro is independently released against a stable base interface.
PG_PRO_VERSION:=0.3.1
PG_PRO_RELEASE:=5
PG_BASE_API:=1
PG_PRO_BASE_API:=1
PG_PRO_MIN_BASE:=0.3.0-13
PG_PRO_MIN_BASE_APK:=0.3.0-r20
PKG_LICENSE:=MIT
PKG_MAINTAINER:=Proxy Guard contributors

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-proxy-guard
  VERSION:=$(PKG_VERSION)$(if $(CONFIG_USE_APK),-r,-)$(PKG_RELEASE)
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=Proxy connection protection
  DEPENDS:=+luci-base +lua +libuci-lua +luci-lib-jsonc +luci-lib-nixio +rpcd-mod-file +firewall4 +curl +ca-bundle +ucode +ucode-mod-fs +ucode-mod-uci
  PKGARCH:=all
endef

define Package/luci-app-proxy-guard/description
  Disabled-by-default proxy health monitor with scoped firewall blocking,
  automatic recovery, LuCI controls and bounded event logs.
endef

define Build/Compile
endef

define Package/luci-app-proxy-guard/conffiles
/etc/config/proxy_guard
endef

# Match the canonical data/executable modes used by tools/build_ipk.py even
# when a shared development checkout uses a group-writable umask.
define ProxyGuard/FixPermissions
	find $(1) -type d -exec chmod 00755 {} +
	find $(1) -type f -exec chmod 644 {} +
	[ ! -d $(1)/etc/init.d ] || find $(1)/etc/init.d -type f -exec chmod 755 {} +
	[ ! -d $(1)/etc/hotplug.d ] || find $(1)/etc/hotplug.d -type f -exec chmod 755 {} +
	[ ! -d $(1)/usr/libexec ] || find $(1)/usr/libexec -type f -exec chmod 755 {} +
endef

define Package/luci-app-proxy-guard/install
	$(CP) ./root/* $(1)/
	$(call ProxyGuard/FixPermissions,$(1))
endef

define Package/luci-app-proxy-guard/preinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
# Refuse incompatible base updates before stopping any installed service.
if [ -f /usr/share/proxy-guard/pro-requires-api ]; then
 pg_pro_api=$$(cat /usr/share/proxy-guard/pro-requires-api 2>/dev/null) || exit 1
 if [ "$$pg_pro_api" != "$(PG_BASE_API)" ]; then
  printf '%s\n' 'Installed Pro requires an incompatible base API; keep the current base or install a compatible Pro release.' >&2
  exit 1
 fi
fi
umask 077
mkdir -p /var/run/proxy-guard /var/lock || exit 1
chmod 700 /var/run/proxy-guard || exit 1
# An installed pre-split Pro still looks up unscoped gettext keys. Preserve
# the local catalog until postinst can retain only keys the new base dropped.
if [ -f /usr/share/proxy-guard/pro-requires-api ] && [ ! -s /usr/lib/lua/luci/i18n/proxy-guard-pro.en.lmo ]; then
    pg_lmo_dir=/usr/lib/lua/luci/i18n
    pg_lmo_saved=/var/run/proxy-guard/legacy-lmo
    mkdir -p "$$pg_lmo_saved" || exit 1
    for pg_lang in en zh-cn ja ru fa; do
        pg_old="$$pg_lmo_dir/proxy-guard-legacy-pro.$$pg_lang.lmo"
        [ -s "$$pg_old" ] || pg_old="$$pg_lmo_dir/proxy-guard.$$pg_lang.lmo"
        [ -s "$$pg_old" ] || continue
        cp "$$pg_old" "$$pg_lmo_saved/$$pg_lang.new" || exit 1
        mv -f "$$pg_lmo_saved/$$pg_lang.new" "$$pg_lmo_saved/$$pg_lang.lmo" || exit 1
    done
fi
pg_pkg_done=0
pg_pkg_setup_stopped=0
pg_pkg_main_stopped=0
pg_pkg_access_stopped=0
pg_pkg_main_running=0
pg_pkg_access_running=0
[ ! -x /etc/init.d/proxy-guard ] || ! /etc/init.d/proxy-guard running || pg_pkg_main_running=1
[ ! -x /etc/init.d/proxy-guard-access ] || ! /etc/init.d/proxy-guard-access running || pg_pkg_access_running=1
pg_pkg_abort() {
    [ "$$pg_pkg_done" = 1 ] && return 0
    rm -f /var/run/proxy-guard/removing
    if [ "$$pg_pkg_setup_stopped" = 1 ]; then /etc/init.d/proxy-guard-setup start >/dev/null 2>&1 || true; fi
    if [ "$$pg_pkg_main_stopped:$$pg_pkg_main_running" = 1:1 ]; then /etc/init.d/proxy-guard start >/dev/null 2>&1 || true; fi
    if [ "$$pg_pkg_access_stopped:$$pg_pkg_access_running" = 1:1 ]; then /etc/init.d/proxy-guard-access start >/dev/null 2>&1 || true; fi
}
trap pg_pkg_abort EXIT
pg_pkg_drain_setup() {
    if [ ! -f /usr/lib/proxy-guard/setup-main.lua ]; then
        touch /var/run/proxy-guard/removing
        return $$?
    fi
    pg_pkg_attempt=0
    while :; do
        # Restore a pending trial before marking removal: the worker refuses
        # rule reconciliation while that marker exists. Hold the setup lock
        # until the marker is durable in runtime to exclude concurrent applies.
        if PG_SETUP_PREINSTALL=1 ucode -e '
import { open } from "fs";
let lock=open("/var/lock/proxy-guard-setup.lock","a",0o600);
let deadline=clock(true)[0]+2;
while (lock && !lock.lock("xn") && clock(true)[0]<deadline) sleep(50);
if (!lock || !lock.lock("xn")) exit(75);
let rc=system(["lua","/usr/lib/proxy-guard/setup-main.lua","boot"]);
if (rc==0) {
 let marker=open("/var/run/proxy-guard/removing","w",0o600);
 if (!marker) rc=1; else marker.close();
}
lock.close();exit(rc==null?1:rc<0?128-rc:rc);
' >/dev/null 2>&1; then return 0; else pg_pkg_rc=$$?; fi
        [ "$$pg_pkg_rc" = 75 ] || return "$$pg_pkg_rc"
        pg_pkg_attempt=$$((pg_pkg_attempt + 1))
        [ "$$pg_pkg_attempt" -lt 100 ] || return 75
        ucode -e 'sleep(100)'
    done
}
# Drain pending setup before stopping its independent observer. It must not
# mistake a package manager's temporary default conffile for a user edit.
pg_pkg_drain_setup || exit 1
if [ -x /etc/init.d/proxy-guard-setup ]; then
    /etc/init.d/proxy-guard-setup stop || exit 1
    pg_pkg_setup_stopped=1
fi
if [ -x /etc/init.d/proxy-guard-access ]; then
    /etc/init.d/proxy-guard-access stop || exit 1
    pg_pkg_access_stopped=1
fi
if [ -x /etc/init.d/proxy-guard ]; then
    /etc/init.d/proxy-guard stop || exit 1
    pg_pkg_main_stopped=1
    ucode -e 'import { open } from "fs"; let f=open("/var/lock/proxy-guard.lock","a",0o600); if (!f) exit(75); let deadline=clock(true)[0]+15; while (!f.lock("xn")) { if (clock(true)[0]>=deadline) exit(75); sleep(100); } f.close();' || exit 1
fi
# Reuse the interrupted-commit format for an interrupted package transaction.
if [ -f /etc/config/proxy_guard ]; then
    mkdir -p /etc/proxy-guard/setup || exit 1
    chmod 700 /etc/proxy-guard/setup || exit 1
    lua - <<'PG_INSTALL_JOURNAL' || exit 1
local json=require 'luci.jsonc'
local function read(path,limit)
 local f=io.open(path,'r');if not f then return nil end
 local value=f:read((limit or 65536)+1);f:close();assert(#value<=(limit or 65536));return value
end
local function write(path,text)
 local f=assert(io.open(path..'.new','w'));assert(f:write(text));assert(f:close());assert(os.rename(path..'.new',path))
end
local function uuid()return assert(read('/proc/sys/kernel/random/uuid',128)):gsub('%s','')end
local before=assert(read('/etc/config/proxy_guard'));assert(#before>0)
local installer_pid,installer_started
local pid=assert(read('/proc/self/stat',8192)):match('^(%d+)')
for _=1,32 do
 local text=pid and read('/proc/'..pid..'/stat',8192)
 if not text then break end
 local fields={};for value in (text:match('^.*%) (.*)$$')or''):gmatch('%S+')do fields[#fields+1]=value end
 local command=(read('/proc/'..pid..'/cmdline',8192)or''):match('^[^%z]+')or''
 local name=command:match('[^/]+$$')
 if name=='opkg' or name=='opkg-cl' or name=='apk' then installer_pid=pid;installer_started=fields[20];break end
 pid=fields[2]
end
assert(installer_pid and installer_started,'package manager identity unavailable')
local p={id=uuid(),token=uuid(),owner='local',previous=before,boot=assert(read('/proc/sys/kernel/random/boot_id',128)):gsub('%s',''),phase='checking',deadline=assert(tonumber(assert(read('/proc/uptime',512)):match('^[%d%.]+')))+120,generation=(read('/var/run/proxy-guard/control-generation',128)or'initial'):gsub('%s',''),package_install=true,installer_pid=installer_pid,installer_started=installer_started}
write('/etc/proxy-guard/setup/trial-previous',before)
write('/etc/proxy-guard/setup/pending.json',json.stringify(p)..string.char(10))
assert(os.execute('/bin/sync')==0)
PG_INSTALL_JOURNAL
fi
# A fragment left by a prior downgrade must not override a legacy policy
# with different source ranges when the new fw4 drop-in is unpacked.
if [ ! -e /usr/lib/proxy-guard/firewall-sync.uc ]; then
    rm -f /etc/proxy-guard/fw4-guard.nft /etc/proxy-guard/fw4-guard.nft.new || exit 1
fi
pg_pkg_done=1
exit 0
endef

define Package/luci-app-proxy-guard/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
rm -f /var/run/proxy-guard/removing
/usr/libexec/proxy-guard-migrate || exit 1
/etc/init.d/proxy-guard enable
/etc/init.d/proxy-guard-setup enable || exit 1
/etc/init.d/proxy-guard-setup start || exit 1
/usr/libexec/proxy-guard-languages || exit 1
if [ -d /var/run/proxy-guard/legacy-lmo ]; then
    /usr/libexec/proxy-guard-legacy-catalogs
fi
(umask 077; /usr/libexec/proxy-guard-policy-refresh) || exit 1
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.*
rm -rf /tmp/luci-modulecache/
/etc/init.d/rpcd reload 2>/dev/null || exit 1
/usr/libexec/proxy-guard-rpc-ready proxy_guard || exit 1
# Clear stale owned policy even when a disabled installation has no daemon.
if [ "$$(uci -q get proxy_guard.main.enabled)" = 0 ]; then
    /usr/libexec/proxy-guard apply >/dev/null 2>&1 || exit 1
fi
if /etc/init.d/proxy-guard running; then
    /etc/init.d/proxy-guard restart || exit 1
elif [ "$$(uci -q get proxy_guard.main.enabled)" = 1 ]; then
    /etc/init.d/proxy-guard start || exit 1
fi
if [ -x /etc/init.d/proxy-guard-access ] && [ "$$(uci -q get proxy_guard_access.main.enabled)" = 1 ]; then
    /etc/init.d/proxy-guard-access restart || exit 1
fi
ucode /usr/lib/proxy-guard/setup-lock.uc installed || exit 1
rm -f /var/run/proxy-guard/opkg-context.uc
# Flush newly installed executables and catalogs before reporting success.
/bin/sync || exit 1
exit 0
endef

define Package/luci-app-proxy-guard/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
if [ "$${PKG_UPGRADE:-0}" != 1 ]; then
    pg_context_rc=0
    ucode /usr/lib/proxy-guard/opkg-context.uc >/dev/null || pg_context_rc=$$?
    if [ "$$pg_context_rc" = 0 ]; then
        # force-reinstall reports "remove", PKG_UPGRADE=0. Keep the owned
        # kernel policy while opkg removes/replaces the program files.
        umask 077
        mkdir -p /var/run/proxy-guard || exit 1
        chmod 700 /var/run/proxy-guard || exit 1
        cp /usr/lib/proxy-guard/opkg-context.uc /var/run/proxy-guard/opkg-context.uc || exit 1
        chmod 600 /var/run/proxy-guard/opkg-context.uc || exit 1
        touch /var/run/proxy-guard/removing || exit 1
        if [ -x /etc/init.d/proxy-guard-access ]; then /etc/init.d/proxy-guard-access stop || exit 1; fi
        /etc/init.d/proxy-guard stop || exit 1
        ucode -e 'import { open } from "fs"; let f=open("/var/lock/proxy-guard.lock","a",0o600); if (!f) exit(75); let deadline=clock(true)[0]+15; while (!f.lock("xn")) { if (clock(true)[0]>=deadline) exit(75); sleep(100); } f.close();' || exit 1
        exit 0
    elif [ "$$pg_context_rc" != 2 ]; then
        exit "$$pg_context_rc"
    fi
    mkdir -p /var/run/proxy-guard || exit 1
    chmod 700 /var/run/proxy-guard || exit 1
    touch /var/run/proxy-guard/removing || exit 1
    /etc/init.d/proxy-guard-setup stop || exit 1
    /etc/init.d/proxy-guard-setup disable || exit 1
    rm -rf /etc/proxy-guard/setup /var/run/proxy-guard/legacy-lmo
    rm -f /usr/lib/lua/luci/i18n/proxy-guard-legacy-pro.*.lmo
    if ! /etc/init.d/proxy-guard stop ||
       ! /usr/libexec/proxy-guard cleanup ||
       ! /etc/init.d/proxy-guard disable; then
        rm -f /var/run/proxy-guard/removing
        exit 1
    fi
fi
exit 0
endef

define Package/luci-app-proxy-guard/postrm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
rm -f /var/run/proxy-guard-access/headers /var/run/proxy-guard-access/headers.new /var/run/proxy-guard-access/request /var/run/proxy-guard-access/request.new /var/run/proxy-guard-access/response-4 /var/run/proxy-guard-access/response-6
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.*
rm -rf /tmp/luci-modulecache/
/etc/init.d/rpcd reload 2>/dev/null
exit 0
endef



define Package/luci-app-proxy-guard-pro
  VERSION:=$(PG_PRO_VERSION)$(if $(CONFIG_USE_APK),-r,-)$(PG_PRO_RELEASE)
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=Proxy Guard Pro
  DEPENDS:=+luci-app-proxy-guard
  # APK SDK FormatDepends treats the parenthesized constraint as one word.
  EXTRA_DEPENDS:=luci-app-proxy-guard ($(if $(CONFIG_USE_APK),>=$(PG_PRO_MIN_BASE_APK),>= $(PG_PRO_MIN_BASE)))
  PKGARCH:=all
endef

define Package/luci-app-proxy-guard-pro/install
	$(CP) ./pro/root/* $(1)/
	$(call ProxyGuard/FixPermissions,$(1))
	chmod 600 $(1)/etc/config/proxy_guard_access
endef

define Package/luci-app-proxy-guard-pro/conffiles
/etc/config/proxy_guard_access
endef

define Package/luci-app-proxy-guard-pro/preinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
pg_base_api=$$(cat /usr/share/proxy-guard/pro-api 2>/dev/null) || pg_base_api=
if [ "$$pg_base_api" != "$(PG_PRO_BASE_API)" ]; then
 printf '%s\n' 'This Pro release requires Proxy Guard base API $(PG_PRO_BASE_API) (base >= $(PG_PRO_MIN_BASE)); the installed base API is missing or incompatible.' >&2
 exit 1
fi
# The old preinst may already have been removed by force-reinstall. The
# prerm copy below sets the same live transaction marker before removal.
if [ -x /usr/libexec/proxy-guard-access-update ]; then
 /usr/libexec/proxy-guard-access-update || exit 1
fi
[ ! -x /etc/init.d/proxy-guard-access ] || /etc/init.d/proxy-guard-access stop || exit 1
exit 0
endef

define Package/luci-app-proxy-guard-pro/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
chmod 600 /etc/config/proxy_guard_access || exit 1
/usr/libexec/proxy-guard-access-migrate-secrets || exit 1
rm -f /usr/lib/lua/luci/i18n/proxy-guard-legacy-pro.*.lmo
rm -rf /var/run/proxy-guard/legacy-lmo
/etc/init.d/proxy-guard-access enable || exit 1
if [ "$$(uci -q get proxy_guard_access.main.enabled)" = 1 ]; then /etc/init.d/proxy-guard-access restart || exit 1; fi
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.*
rm -rf /tmp/luci-modulecache/
/etc/init.d/rpcd reload 2>/dev/null || exit 1
/usr/libexec/proxy-guard-rpc-ready proxy_guard_access || exit 1
rm -f /var/run/proxy-guard-access/updating /var/run/proxy-guard-access/updating.new /var/run/proxy-guard-access/installing /var/run/proxy-guard-access/installing.new
# RPC registration alone can succeed while new executables are still cached.
/bin/sync || exit 1
exit 0
endef

define Package/luci-app-proxy-guard-pro/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
if [ "$${PKG_UPGRADE:-0}" != 1 ]; then
 pg_context=/usr/lib/proxy-guard/opkg-context.uc
 [ -r "$$pg_context" ] || pg_context=/var/run/proxy-guard/opkg-context.uc
 pg_context_rc=0
 ucode "$$pg_context" >/dev/null || pg_context_rc=$$?
 if [ "$$pg_context_rc" = 0 ]; then
  /usr/libexec/proxy-guard-access-update || exit 1
  /etc/init.d/proxy-guard-access stop || exit 1
 elif [ "$$pg_context_rc" = 2 ]; then
  umask 077
  mkdir -p /var/run/proxy-guard-access || exit 1
  touch /var/run/proxy-guard-access/installing || exit 1
  /etc/init.d/proxy-guard-access stop || exit 1
  /etc/init.d/proxy-guard-access disable || exit 1
  rm -f /var/run/proxy-guard-access/updating /var/run/proxy-guard-access/updating.new
 else
  exit "$$pg_context_rc"
 fi
fi
exit 0
endef

define Package/luci-app-proxy-guard-pro/postrm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
# Keep the file-replacement barrier through an upgrade or force-reinstall.
pg_context=/usr/lib/proxy-guard/opkg-context.uc
[ -r "$$pg_context" ] || pg_context=/var/run/proxy-guard/opkg-context.uc
pg_context_rc=0
ucode "$$pg_context" >/dev/null 2>&1 || pg_context_rc=$$?
if [ "$$pg_context_rc" = 2 ]; then
 rm -f /var/run/proxy-guard-access/installing /var/run/proxy-guard-access/installing.new
fi
rm -f /tmp/luci-indexcache /tmp/luci-indexcache.*
rm -rf /tmp/luci-modulecache/
/etc/init.d/rpcd reload 2>/dev/null
exit 0
endef

$(eval $(call BuildPackage,luci-app-proxy-guard))

$(eval $(call BuildPackage,luci-app-proxy-guard-pro))

