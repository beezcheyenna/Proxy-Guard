#!/bin/sh
set -eu
# Only a disposable offline container or our explicitly marked QEMU guest.
if [ "${1:-}" = --offline-vm ]; then
    test -f /etc/pgvm-fixture
    test "$(cat /proc/1/comm)" = procd
else
    test -f /.dockerenv
    test "$(ls /sys/class/net)" = lo
fi
if opkg status flock | grep -q '^Status: .* installed$'; then echo 'flock fixture still installed'; exit 1; fi
fixture=/tmp/pg-lock-test
mkdir -p "$fixture"
first=''; second=''; worker=''
cleanup() {
    touch "$fixture/release"
    for pid in "$first" "$second" "$worker"; do
        test -z "$pid" || kill "$pid" 2>/dev/null || true
    done
    rm -rf "$fixture"
}
trap cleanup EXIT INT TERM
wait_file() {
    count=0
    while [ ! -f "$1" ]; do
        count=$((count + 1))
        test "$count" -lt 50 || { echo "Fixture timeout: $1"; exit 1; }
        ucode -e 'sleep(100)'
    done
}
cat > "$fixture/lua" <<'EOF'
#!/bin/sh
set -eu
fixture=/tmp/pg-lock-test
test "$1" = /usr/lib/proxy-guard/main.lua
case "$2" in
    tick)
        mkdir "$fixture/busy" || { touch "$fixture/overlap"; exit 99; }
        echo "$$" > "$fixture/worker"
        touch "$fixture/entered"
        while [ ! -f "$fixture/release" ]; do ucode -e 'sleep(100)'; done
        rmdir "$fixture/busy"
        touch "$fixture/done"
        exit 17
        ;;
    apply)
        test ! -d "$fixture/busy" || { touch "$fixture/overlap"; exit 99; }
        touch "$fixture/second"
        ;;
    status) echo '{"ok":true}' ;;
    *) exit 2 ;;
esac
EOF
chmod 755 "$fixture/lua"
# Ensure even a present, incompatible flock command is never chosen on OpenWrt.
cat > "$fixture/flock" <<'EOF'
#!/bin/sh
touch /tmp/pg-lock-test/wrong-runner
exit 99
EOF
chmod 755 "$fixture/flock"

PATH="$fixture:$PATH" /usr/libexec/proxy-guard tick &
first=$!
wait_file "$fixture/entered"
worker="$(cat "$fixture/worker")"
PATH="$fixture:$PATH" /usr/libexec/proxy-guard apply &
second=$!
ucode -e 'sleep(300)'
test ! -e "$fixture/second"
# An init reload must promptly release its service lock while the daemon owns
# the worker lock; the daemon will consume committed UCI on its next tick.
if PATH="$fixture:$PATH" /usr/libexec/proxy-guard try_apply > "$fixture/reload"; then exit 1; else code=$?; fi
test "$code" = 75
test ! -e "$fixture/second"
PATH="$fixture:$PATH" /usr/libexec/proxy-guard status | jsonfilter -e '@.ok' | grep -qx true
touch "$fixture/release"
if wait "$first"; then code=0; else code=$?; fi
test "$code" = 17
first=''; worker=''
wait_file "$fixture/second"
wait "$second"; second=''
test ! -e "$fixture/overlap"
test ! -e "$fixture/wrong-runner"
echo 'PASS ucode runner serializes writes, preserves child exit code and keeps status readable'

rm -f "$fixture/release" "$fixture/entered" "$fixture/done" "$fixture/second"
PATH="$fixture:$PATH" /usr/libexec/proxy-guard tick &
first=$!
wait_file "$fixture/entered"
worker="$(cat "$fixture/worker")"
kill -KILL "$first"
wait "$first" 2>/dev/null || true
first=''
PATH="$fixture:$PATH" /usr/libexec/proxy-guard apply &
second=$!
ucode -e 'sleep(300)'
test ! -e "$fixture/second"
touch "$fixture/release"
wait_file "$fixture/done"
wait_file "$fixture/second"
wait "$second"; second=''; worker=''
test ! -e "$fixture/overlap"
echo 'PASS a surviving worker retains the lock after supervisor SIGKILL and releases it on exit'

rm -f "$fixture/second" /var/lock/proxy-guard.lock
mkdir /var/lock/proxy-guard.lock
if PATH="$fixture:$PATH" /usr/libexec/proxy-guard apply > "$fixture/error"; then exit 1; fi
test ! -e "$fixture/second"
jsonfilter -i "$fixture/error" -e '@.ok' | grep -qx false
rmdir /var/lock/proxy-guard.lock
PATH="$fixture:$PATH" /usr/libexec/proxy-guard apply
test -f "$fixture/second"
if ucode /usr/lib/proxy-guard/locked.uc 'apply;touch /tmp/pg-lock-injected' >/dev/null; then exit 1; fi
test ! -e /tmp/pg-lock-injected
test ! -e "$fixture/wrong-runner"
echo 'PASS lock failures do not execute mutations and runner rejects unlisted actions'
