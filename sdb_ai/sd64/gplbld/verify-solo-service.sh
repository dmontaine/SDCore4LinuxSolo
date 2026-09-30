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
[ "$#" -ge 2 ] && [ "$#" -le 4 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE [ADMIN_PASSWORD_FILE [GLOBAL_PASSWORD_FILE]]"
H="$1"; PWF="$2"; ADF="${3:-}"; GLF="${4:-}"
[ -z "$ADF" ] || [ -s "$ADF" ] || refuse "cannot read the administrator password file $ADF"
[ -z "$GLF" ] || [ -s "$GLF" ] || refuse "cannot read the global password file $GLF"
[ -z "$GLF" ] || [ -n "$ADF" ] || refuse "a global password file needs the administrator password file before it"
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

# ---- The API LOGIN (LSOLO 6): SCRAM-SHA-256 over TLS, driven by gplbld/scram-probe.py,
# a client that shares no code with SD.  api_login PASSWORD_VAR USER ACCOUNT COMMAND
# prints the probe's verdict lines; the password goes through the environment.
PROBE="$here/scram-probe.py"
[ -f "$PROBE" ] || refuse "$PROBE is missing"
command -v python3 >/dev/null || refuse "python3 is required for the API legs"
api_login() {
  local pw="$1" user="$2" acct="$3"; shift 3
  SD_SCRAM_PASSWORD="$pw" timeout 90 python3 "$PROBE" --port "$PORT" --user "$user" --account "$acct" -- "$@" 2>&1 | strip
}
VERIFIED='SCRAM: server signature VERIFIED'
REFUSED='SCRAM: login REFUSED'

# ---- S6a. the account password logs in over the API and the session is sduser.
o="$(api_login "$GOOD" sduser sduser WHO)"
if printf '%s\n' "$o" | grep -qx "$VERIFIED" && printf '%s\n' "$o" | grep -q '^account sduser: entered' && printf '%s\n' "$o" | grep -qE '^\| [0-9]+ sduser'; then
  leg "S6a API login as sduser" "server signature VERIFIED, account entered, WHO answers sduser" 0 "$(printf '%s\n' "$o" | grep -E '^\| [0-9]+ sduser' | head -1)"
else
  leg "S6a API login as sduser" "VERIFIED, entered, WHO answers sduser" 1 "$(printf '%s\n' "$o" | grep -E '^SCRAM|REFUSED' | head -1)"
fi

# ---- S6b. a wrong password, and the names that are not API logins.
o1="$(api_login 'Wrong-Pass-9!' sduser sduser WHO)"
o2="$(api_login "$GOOD" sdsys sdsys WHO)"
o3="$(api_login "$GOOD" '$admin' sduser WHO)"
n=0
for o in "$o1" "$o2" "$o3"; do printf '%s\n' "$o" | grep -q "^$REFUSED" && n=$((n+1)); done
if [ "$n" -eq 3 ] && ! printf '%s\n%s\n%s\n' "$o1" "$o2" "$o3" | grep -q "$VERIFIED"; then
  leg "S6b refused: wrong password, sdsys, \$admin" "3 refusals and no VERIFIED" 0 "3 of 3"
else
  leg "S6b refused: wrong password, sdsys, \$admin" "3 refusals and no VERIFIED" 1 "refusals=$n"
fi

# ---- S6c. sduser can enter no other account - not SDSYS, not one that does not exist.
o1="$(api_login "$GOOD" sduser sdsys WHO)"
o2="$(api_login "$GOOD" sduser other WHO)"
if printf '%s\n' "$o1" | grep -q '^account sdsys: REFUSED: User not allowed in requested account' \
   && printf '%s\n' "$o2" | grep -q '^account other: REFUSED: User not allowed in requested account'; then
  leg "S6c only its own account" "sdsys and 'other' both 'User not allowed in requested account'" 0 "refused"
else
  leg "S6c only its own account" "sdsys and 'other' both refused" 1 "$(printf '%s\n%s\n' "$o1" "$o2" | grep -E '^account' | tr '\n' ' ')"
fi

# ---- S6d. the administrator password is not an API login (needs ADMIN_PASSWORD_FILE).
if [ -n "$ADF" ]; then
  ADMINPW="$(head -1 "$ADF")"
  o="$(api_login "$ADMINPW" sduser sduser WHO)"
  if printf '%s\n' "$o" | grep -q "^$REFUSED" && ! printf '%s\n' "$o" | grep -qx "$VERIFIED"; then
    leg "S6d admin password is not an API login" "REFUSED, never VERIFIED" 0 "refused"
  else
    leg "S6d admin password is not an API login" "REFUSED, never VERIFIED" 1 "$(printf '%s\n' "$o" | grep -E '^SCRAM' | head -1)"
  fi
else
  echo "  [SKIP] S6d admin password is not an API login | no ADMIN_PASSWORD_FILE given; NOT MEASURED"
fi

# ---- S6e. MANAGED MODE (needs a global password file and a tree that has one).
# The master logs in under the account's name with the global password: it gets the
# administrator commands (LISTU lists); the account password on the same name does not.
if [ -n "$GLF" ]; then
  GLOBALPW="$(head -1 "$GLF")"
  [ -f "$H/\$cred/\$global" ] || refuse "$H has no \$cred/\$global - it was not built in managed mode; leg S6e would measure nothing"
  og="$(api_login "$GLOBALPW" sduser sduser LISTU)"
  oa="$(api_login "$GOOD" sduser sduser LISTU)"
  if printf '%s\n' "$og" | grep -qx "$VERIFIED" && printf '%s\n' "$og" | grep -q 'Username' \
     && printf '%s\n' "$oa" | grep -qx "$VERIFIED" && printf '%s\n' "$oa" | grep -q 'Command requires administrator privileges'; then
    leg "S6e managed: global password carries ADMIN" "global: LISTU lists; account: LISTU refused" 0 "as expected"
  else
    leg "S6e managed: global password carries ADMIN" "global: LISTU lists; account: LISTU refused" 1 "global: $(printf '%s\n' "$og" | grep -E '^SCRAM|Command' | head -1) / account: $(printf '%s\n' "$oa" | grep -E '^SCRAM|Command' | head -1)"
  fi
else
  echo "  [SKIP] S6e managed-mode API login | no GLOBAL_PASSWORD_FILE given; NOT MEASURED"
fi

# ---- S6f. SDConnectLocal is disabled and FAILS AT ONCE (Windows Solo bd59940; LSOLO 15).
# Before the change it hung for ever: the client library's sysdir() reads /etc/sd.conf, which a
# Solo tree does not have.  Judged on the library's own error text; a hang is a failed leg.
if command -v gcc >/dev/null 2>&1 && [ -f "$H/bin/sdclilib.so" ]; then
  LCT="$(mktemp -d)"
  if gcc -o "$LCT/lct" "$(dirname "$SVC")/local-connect-test.c" -ldl 2>/dev/null; then
    lo="$(cd "$H" && timeout 30 "$LCT/lct" "$H/bin/sdclilib.so" 2>&1)"; lrc=$?
    if [ "$lrc" -eq 0 ] && printf '%s\n' "$lo" | grep -q "^SDConnectLocal -> 0 error='SDConnectLocal is not available in SD Core for Linux Solo - connect with SDConnect and the account password'$"; then
      leg "S6f SDConnectLocal is refused, not hung" "returns 0 with the 'not available ... use SDConnect' error" 0 "refused at once"
    else
      leg "S6f SDConnectLocal is refused, not hung" "returns 0 with the 'not available' error, within 30 s" 1 "rc=$lrc; $lo"
    fi
  else
    echo "  [SKIP] S6f SDConnectLocal | local-connect-test.c did not compile; NOT MEASURED"
  fi
  rm -rf "$LCT"
else
  echo "  [SKIP] S6f SDConnectLocal | no gcc or no sdclilib.so; NOT MEASURED"
fi

# ---- S7. the server identity is private and inside the tree.
mode_dir="$(stat -c '%a' "$H/sd-tls" 2>/dev/null)"; mode_key="$(stat -c '%a' "$H/sd-tls/api.pem" 2>/dev/null)"
if [ "$mode_dir" = "700" ] && [ "$mode_key" = "600" ]; then
  leg "S7 server identity is private" "sd-tls 700, api.pem 600, in the tree" 0 "$mode_dir / $mode_key"
else
  leg "S7 server identity is private" "sd-tls 700, api.pem 600" 1 "$mode_dir / $mode_key"
fi

# ---- S7b. the API can be CHANGED by running install again: open, then off, then local.
# (A first version left the old listener behind: after "--api off" systemd still called the
# removed socket unit active.)  Each step is judged by the listener itself.
api_seen() { ss -ltn 2>/dev/null | awk -v p=":$PORT\$" '$4 ~ p {print $4}' | head -1; }
bash "$SVC" install "$H" --api open --api-port "$PORT" >/dev/null 2>&1; sleep 1; a_open="$(api_seen)"
bash "$SVC" install "$H" --api off >/dev/null 2>&1; sleep 1; a_off="$(api_seen)"; u_off="$(systemctl --user is-active sd-solo-api.socket 2>&1)"
bash "$SVC" install "$H" --api local --api-port "$PORT" >/dev/null 2>&1; sleep 1; a_local="$(api_seen)"
if [ "$a_open" = "0.0.0.0:$PORT" ] && [ -z "$a_off" ] && [ "$u_off" != "active" ] && [ "$a_local" = "127.0.0.1:$PORT" ]; then
  leg "S7b re-running install changes the API" "open -> 0.0.0.0, off -> nothing listening and the unit not active, local -> 127.0.0.1" 0 "$a_open / none / $a_local"
else
  leg "S7b re-running install changes the API" "0.0.0.0:$PORT / nothing / 127.0.0.1:$PORT" 1 "open='$a_open' off='$a_off' unit-after-off='$u_off' local='$a_local'"
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
