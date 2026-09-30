#!/bin/bash
# verify-solo-service.sh - does solo-service.sh do what it says?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-service.sh HOME_DIR ACCOUNT_PASSWORD_FILE
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh with
# --account-password-file ACCOUNT_PASSWORD_FILE.  It installs the user units
# for that tree, exercises them, and REMOVES them again - it changes the user's
# systemd configuration while it runs and puts it back, and it never touches
# linger (a persistent account setting; reported, not changed).
#
# EVERY LEG ANCHORS ON WHAT THE TOOL SAID, NOT ON AN EXIT CODE.  A leg that
# could not have reached its condition refuses (exit 2): the daemon it stops is
# proven to be running first, the socket it probes is proven to be listening.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE"
H="$1"; PWF="$2"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd" ] || refuse "$H/bin/sd is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -s "$PWF" ] || refuse "cannot read the password file $PWF"
GOOD="$(head -1 "$PWF")"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC="$here/solo-service.sh"
[ -f "$SVC" ] || refuse "$SVC is missing"
SD="$H/bin/sd"
PORT=14243
UNITDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
command -v systemctl >/dev/null || refuse "systemctl is not available"
for u in sd-solo.service sd-solo-api.socket sd-solo-api@.service; do
  [ -e "$UNITDIR/$u" ] && refuse "$UNITDIR/$u already exists - another Solo service is installed; remove it first (this run would overwrite it)"
done
ss -ltn 2>/dev/null | grep -q ":$PORT " && refuse "port $PORT is already in use"

echo "verify-solo-service inputs:"
echo "  tree       : $H"
echo "  script     : $SVC"
echo "  unit dir   : $UNITDIR"
echo "  api port   : $PORT (127.0.0.1)"
echo "  linger     : $(loginctl show-user "$USER" -p Linger --value 2>/dev/null) (never changed here)"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}
who_line() { printf '%s\nWHO\nOFF\n' "$GOOD" | timeout 60 "$SD" 2>&1 | strip | grep -E '^[0-9]+ sduser$' | head -1; }

cleanup() { bash "$SVC" remove >/dev/null 2>&1; "$SD" -stop >/dev/null 2>&1; }
trap cleanup EXIT

# The stage leaves a daemon of its own running; start from a known state.
"$SD" -stop >/dev/null 2>&1

# ---- S1. install says READY with the daemon active and the API local.
out="$(bash "$SVC" install "$H" --api local --api-port "$PORT" 2>&1)"
last="$(printf '%s\n' "$out" | strip | grep -E '^SOLO SERVICE READY' | tail -1)"
case "$last" in
  "SOLO SERVICE READY daemon=active api=local linger="*) leg "S1 install" "'SOLO SERVICE READY daemon=active api=local linger=...'" 0 "$last" ;;
  *) leg "S1 install" "'SOLO SERVICE READY daemon=active api=local ...'" 1 "$(printf '%s\n' "$out" | tail -2 | tr '\n' ' ')"; exit 1 ;;
esac

# ---- S2. the unit files name THIS tree and no other path.
if grep -qF "ExecStart=$H/bin/sd -start" "$UNITDIR/sd-solo.service" \
   && grep -qF "ExecStop=$H/bin/sd -stop" "$UNITDIR/sd-solo.service" \
   && grep -qF "ExecStart=$H/bin/sd -n -q" "$UNITDIR/sd-solo-api@.service" \
   && grep -qF "ListenStream=127.0.0.1:$PORT" "$UNITDIR/sd-solo-api.socket" \
   && ! grep -rqE '/usr/local|/etc/sd|sdsys' "$UNITDIR/sd-solo.service" "$UNITDIR/sd-solo-api@.service" "$UNITDIR/sd-solo-api.socket"; then
  leg "S2 unit files" "name this tree; no /usr/local, /etc/sd or sdsys" 0 "as expected"
else
  leg "S2 unit files" "name this tree; no /usr/local, /etc/sd or sdsys" 1 "$(cat "$UNITDIR"/sd-solo*.service "$UNITDIR"/sd-solo-api.socket 2>&1 | grep -E 'Exec|Listen' | tr '\n' ' ')"
fi

# ---- S3. a session works against the service-started daemon.
l="$(who_line)"
[ -n "$l" ] && leg "S3 session against the service" "WHO answers '<n> sduser'" 0 "$l" || leg "S3 session against the service" "WHO answers '<n> sduser'" 1 "no WHO line"

# ---- S4. restart, and the daemon comes back.
systemctl --user restart sd-solo.service 2>&1 | tail -1
l="$(who_line)"
[ -n "$l" ] && leg "S4 restart" "a session works after 'systemctl --user restart'" 0 "$l" || leg "S4 restart" "a session works after restart" 1 "no WHO line"

# ---- S5. stop really stops SD (the daemon was proven running by S4).
systemctl --user stop sd-solo.service 2>&1 | tail -1
o="$(printf '%s\n' "$GOOD" | timeout 60 "$SD" WHO 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qE 'has not been started|not been started|not running' && [ -z "$(printf '%s\n' "$o" | grep -E '^[0-9]+ sduser$')" ]; then
  leg "S5 stop stops SD" "a session is refused with 'has not been started'" 0 "$(printf '%s\n' "$o" | grep -E 'started|running' | head -1)"
else
  leg "S5 stop stops SD" "a session is refused with 'has not been started'" 1 "$(printf '%s\n' "$o" | tail -1)"
fi
systemctl --user start sd-solo.service 2>&1 | tail -1

# ---- S6. the API socket is listening and completes a TLS 1.3 handshake.
if ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT "; then
  if command -v openssl >/dev/null; then
    hs="$(echo | timeout 30 openssl s_client -connect 127.0.0.1:$PORT -tls1_3 2>&1 | strip)"
    if printf '%s\n' "$hs" | grep -qE 'Protocol *: TLSv1.3'; then
      leg "S6 API socket" "listening on 127.0.0.1:$PORT and answers TLS 1.3" 0 "$(printf '%s\n' "$hs" | grep -E 'Cipher is' | head -1)"
    else
      leg "S6 API socket" "TLS 1.3 handshake completes" 1 "$(printf '%s\n' "$hs" | tail -2 | tr '\n' ' ')"
    fi
  else
    echo "  [SKIP] S6 API socket | openssl is not installed; only 'listening' was checked"
  fi
else
  leg "S6 API socket" "listening on 127.0.0.1:$PORT" 1 "not listening"
fi

# ---- S7. the server identity is private and inside the tree.
mode_dir="$(stat -c '%a' "$H/sd-tls" 2>/dev/null)"; mode_key="$(stat -c '%a' "$H/sd-tls/api.pem" 2>/dev/null)"
if [ "$mode_dir" = "700" ] && [ "$mode_key" = "600" ]; then
  leg "S7 server identity is private" "sd-tls 700, api.pem 600, in the tree" 0 "$mode_dir / $mode_key"
else
  leg "S7 server identity is private" "sd-tls 700, api.pem 600" 1 "$mode_dir / $mode_key"
fi

# ---- S8. remove leaves nothing: files gone, daemon down, socket closed.
rm_out="$(bash "$SVC" remove 2>&1 | strip | tail -1)"
gone=0
for u in sd-solo.service sd-solo-api.socket sd-solo-api@.service; do [ -e "$UNITDIR/$u" ] && gone=1; done
o="$(printf '%s\n' "$GOOD" | timeout 60 "$SD" WHO 2>&1 | strip)"
down=0; printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && down=1
listen=0; ss -ltn 2>/dev/null | grep -q ":$PORT " && listen=1
if [ "$rm_out" = "SOLO SERVICE REMOVED" ] && [ $gone -eq 0 ] && [ $down -eq 0 ] && [ $listen -eq 0 ]; then
  leg "S8 remove" "'SOLO SERVICE REMOVED', unit files gone, SD down, port closed" 0 "$rm_out"
else
  leg "S8 remove" "'SOLO SERVICE REMOVED', unit files gone, SD down, port closed" 1 "said '$rm_out'; files-left=$gone session-still-works=$down port-open=$listen"
fi

echo
echo "verify-solo-service: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
