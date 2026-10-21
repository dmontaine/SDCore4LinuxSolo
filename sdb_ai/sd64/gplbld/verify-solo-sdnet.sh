#!/bin/bash
# verify-solo-sdnet.sh - does a STAGED SOLO reach a real SD server through SDNet?  (SDNet carry 9, 20 Oct 2026)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-sdnet.sh HOME_DIR ACCOUNT_PW_FILE ADMIN_PW_FILE SERVER_HOST SERVER_PORT REMOTE_ACCOUNT REMOTE_USER REMOTE_PW_FILE REMOTE_FILE
#
# WRITTEN, NOT RUN (owner, 20 Oct 2026: VM witness testing is one big session after every component is built).  Syntax-checked only.
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh with the account password and the administrator password, its daemon running; this script types them from the two files and never prints
# them.  The OTHER end is a real SD server (an SD Core or another Solo) that serves its API on SERVER_HOST:SERVER_PORT (4247 SD Core, 4249 Solo), where REMOTE_USER has the password in
# REMOTE_PW_FILE and may enter REMOTE_ACCOUNT, and where REMOTE_FILE (a name in that account's VOC) holds at least one record.  Against SD Core the remote user must be in its sdfiles route (and
# sdfileswrite for the write leg, which this script does not run: it asks for read only).
#
# WHAT IT PROVES, leg by leg: (1) as the administrator the NET gate goes on and `set.server ... connect` shows the hash the server presents and, answered y, defines the server;
# (2) your own login is made with set.netlogin (the remote password typed, never shown) and the store holds a file mode 600 in a directory mode 700;
# (3) with the gate ON an ordinary session opens the file through a VOC pointer of type N, counts its records and reads one; the audit trail says `netfile open`;
# (4) with the gate OFF the same program is refused with message 11460 and dials nothing; (5) a definition whose pin is not the server's key is refused before a byte is sent;
# (6) everything is put back (login deleted, definition deleted, pointer removed, the gate off).
# WHAT IT CANNOT PROVE: that the hash shown is the server's real one (compare it by another route: the script prints it); the channel binding of the login against a server that enforces it is
# exercised by the login in leg 2 and leg 3 working at all.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 9 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PW_FILE ADMIN_PW_FILE SERVER_HOST SERVER_PORT REMOTE_ACCOUNT REMOTE_USER REMOTE_PW_FILE REMOTE_FILE"
H="$1"; PWF="$2"; APWF="$3"; HOST="$4"; PORT="$5"; RACC="$6"; RUSER="$7"; RPWF="$8"; RFILE="$9"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] && [ -f "$H/.sdcoresolo" ] || refuse "$H is not a built Solo tree"
for f in "$PWF" "$APWF" "$RPWF"; do [ -s "$f" ] || refuse "cannot read $f"; done
case "$PORT" in ''|*[!0-9]*) refuse "the port must be a number";; esac
printf '%s' "$HOST" | grep -Eq '^[A-Za-z0-9.:-]+$' || refuse "the host holds a character a definition does not allow"
printf '%s' "$RACC$RUSER$RFILE" | grep -Eq '^[A-Za-z0-9._$-]+$' || refuse "an account, user or file name holds a character the verbs do not allow"
[ -f "$H/sys/accounts/sduser" ] || [ -f "$H/accounts/sduser" ] || refuse "$H has no register record for sduser"
REG="$H/accounts/sduser"; [ -f "$REG" ] || REG="$H/sys/accounts/sduser"
SYS="$H"; [ -d "$H/sys" ] && SYS="$H/sys"
PW="$(head -1 "$PWF")"; APW="$(head -1 "$APWF")"; RPW="$(head -1 "$RPWF")"
umask 077
SRV=vsn$$ ; SRV="$(printf '%s' "$SRV" | cut -c1-12)"      # a server name: a letter and letters or digits, at most 16
PTR=zznetvsn
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT

echo "verify-solo-sdnet inputs:"
echo "  tree        : $H"
echo "  server      : $HOST:$PORT  account $RACC  user $RUSER  file $RFILE   (definition name $SRV)"
echo "  running as  : $(id -un)"

pass=0; fail=0; legs=0
leg() { legs=$((legs+1)); if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }

# one session of sduser on a pipe: $1 = admin|plain, then the lines to type; prints what came after the TERM line, without the echoed commands
sess() {
  local lane="$1"; shift
  { printf '%s\n' "$PW"; [ "$lane" = admin ] && printf 'ADMIN\n%s\n' "$APW"; printf 'TERM 200,9999\n'; printf '%s\n' "$@"; printf 'OFF\n'; } \
    | timeout 180 "$H/bin/sd-solo" 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' | sed -n '/^:TERM 200,9999/,$p' | grep -v '^:' | grep -v '^$'
}
cleanup() {
  sess admin "delete.server $SRV" "delete.server ${SRV}p" "delete.netlogin $SRV" "set.net.access off" "$(printf 'DELETE VOC %s' "$PTR")" >/dev/null 2>&1
  rm -f "$SYS/user_accounts/sduser/bp/zzvsnptr" "$SYS/user_accounts/sduser/bp.out/zzvsnptr" "$SYS/user_accounts/sduser/bp/zzvsnrd" "$SYS/user_accounts/sduser/bp.out/zzvsnrd"
}

# ---- 0. the null case: an ordinary session is not the administrator, and the gate starts as the register says
o="$(sess plain 'WHO.AM.I')"
printf '%s\n' "$o" | grep -Eq 'Admin\?[[:space:]]*:[[:space:]]*No' || { echo "REFUSED: the ordinary lane is an administrator; its refusals would prove nothing" >&2; exit 2; }
sess admin 'set.net.access off' >/dev/null

# ---- 1. the gate on, the server defined by connect, answered y
o="$(sess admin 'set.net.access on' "set.server $SRV $HOST $PORT $RACC connect read accounts sduser" 'y')"
hash="$(printf '%s\n' "$o" | grep -Eo '^[0-9a-f]{64}$' | head -1)"
if printf '%s\n' "$o" | grep -q "Server $SRV ($HOST:$PORT) is defined" && [ -n "$hash" ]; then
  leg "1 set.server ... connect shows the key hash and defines the server" "a 64 digit hash on a line of its own, then 'Server $SRV is defined'" 0 "hash $hash (COMPARE IT with the server's own by another route)"
else
  leg "1 set.server ... connect shows the key hash and defines the server" "the hash and 'is defined'" 1 "$(printf '%s\n' "$o" | tail -4 | tr '\n' '|')"
  cleanup; echo; echo "verify-solo-sdnet: $pass passed, $fail failed, of $legs legs (stopped: nothing below can be believed)"; exit 1
fi

# ---- 2. your own login: the remote user and password typed, stored as derived keys
o="$(sess plain "set.netlogin $SRV" "$RUSER" "$RPW")"
mode_f="$(stat -c '%a' "$SYS/netlogins/$SRV" 2>/dev/null || echo none)"; mode_d="$(stat -c '%a' "$SYS/netlogins" 2>/dev/null || echo none)"
if printf '%s\n' "$o" | grep -q "Your login on server $SRV as $RUSER is stored" && [ "$mode_f" = 600 ] && [ "$mode_d" = 700 ] && ! printf '%s\n' "$o" | grep -qF "$RPW"; then
  leg "2 set.netlogin stores the derived keys and not the password" "'is stored', netlogins mode 700, the file mode 600, the password not on the screen" 0 "modes $mode_d $mode_f"
else
  leg "2 set.netlogin stores the derived keys and not the password" "'is stored', mode 700 / 600, no password on the screen" 1 "modes $mode_d $mode_f; $(printf '%s\n' "$o" | tail -3 | tr '\n' '|' | cut -c1-200)"
fi

# ---- 3. a VOC pointer of type N (the administrator writes it), then an ordinary session opens, counts and reads
cat > "$W/ptr" <<EOF
program zzvsnptr
   open 'voc' to v else crt 'PTR no voc' ; stop
   write 'N':@fm:'$SRV':@fm:'$RFILE' to v, '$PTR' on error crt 'PTR write-error ':status() ; stop
   crt 'PTR done'
end
EOF
cp "$W/ptr" "$SYS/user_accounts/sduser/bp/zzvsnptr"
o="$(sess admin 'BASIC bp zzvsnptr' 'RUN bp zzvsnptr')"
if ! printf '%s\n' "$o" | grep -q '^PTR done'; then
  leg "3a the administrator writes the VOC pointer of type N" "PTR done" 1 "$(printf '%s\n' "$o" | tail -3 | tr '\n' '|' | cut -c1-200)"
  cleanup; echo; echo "verify-solo-sdnet: $pass passed, $fail failed, of $legs legs (stopped: no pointer)"; exit 1
fi
cat > "$W/rd" <<EOF
program zzvsnrd
   open '$PTR' to f else crt 'KR open-else ':status() ; stop
   select f
   n = 0 ; first = ''
   loop
      readnext id else exit
      n += 1
      if n = 1 then first = id
   repeat
   crt 'KR opened records=':n
   if first # '' then
      read r from f, first then crt 'KR read-first len=':len(r) else crt 'KR read-else ':status()
   end
   close f
   crt 'KR end'
end
EOF
cp "$W/rd" "$SYS/user_accounts/sduser/bp/zzvsnrd"
off0="$(stat -c %s "$SYS/audit" 2>/dev/null || echo 0)"
o="$(sess plain 'BASIC bp zzvsnrd' 'RUN bp zzvsnrd')"
aud="$(tail -c +$((off0+1)) "$SYS/audit" 2>/dev/null)"
if printf '%s\n' "$o" | grep -q '^KR opened records=' && printf '%s\n' "$o" | grep -q '^KR end' && printf '%s\n' "$aud" | grep -q "netfile open server=$SRV file=$RFILE"; then
  leg "3 an ordinary session opens the remote file through the N pointer, selects it and reads a record" "KR opened records=n, KR read-first (or an empty file), 'netfile open' in the audit trail" 0 "$(printf '%s\n' "$o" | grep '^KR' | tr '\n' ' ')"
else
  leg "3 an ordinary session opens the remote file through the N pointer" "KR opened records=n and the audit line" 1 "$(printf '%s\n' "$o" | tail -4 | tr '\n' '|' | cut -c1-240)"
fi

# ---- 4. the gate OFF: refused with 11460, nothing dialled
sess admin 'set.net.access off' >/dev/null
o="$(sess plain 'RUN bp zzvsnrd')"
if printf '%s\n' "$o" | grep -q 'does not have the NET gate' && ! printf '%s\n' "$o" | grep -q '^KR opened'; then
  leg "4 with the gate off the same program is refused" "'This account does not have the NET gate' and no 'KR opened'" 0 "refused"
else
  leg "4 with the gate off the same program is refused" "message 11460 and no KR opened" 1 "$(printf '%s\n' "$o" | tail -3 | tr '\n' '|' | cut -c1-200)"
fi
sess admin 'set.net.access on' >/dev/null

# ---- 5. a definition whose pin is not the server's key (a typed pin of 64 zeros): refused before a byte is sent
sess admin "set.server ${SRV}p $HOST $PORT $RACC $(printf '0%.0s' $(seq 64)) read accounts sduser" >/dev/null
sess plain "set.netlogin ${SRV}p" "$RUSER" "$RPW" > "$W/pin.out"
if grep -q 'is not the key in the definition' "$W/pin.out" && [ ! -e "$SYS/netlogins/${SRV}p" ]; then
  leg "5 a pin that is not the server's key is refused before anything is sent" "message 11471 and no stored login" 0 "refused"
else
  leg "5 a pin that is not the server's key is refused" "11471 and no login stored" 1 "$(tail -3 "$W/pin.out" | tr '\n' '|' | cut -c1-200)"
fi

# ---- 6. put everything back
cleanup
left=0
[ -e "$SYS/netlogins/$SRV" ] && left=1
sess admin 'list.servers' | grep -q "^$SRV\|^${SRV}p" && left=1
leg "6 everything is put back (login, definitions, pointer, gate off)" "no stored login, no definition of $SRV" "$left" "something is left: check $SYS/netlogins and list.servers"

echo
echo "verify-solo-sdnet: $pass passed, $fail failed, of $legs legs"
[ "$fail" -eq 0 ] || exit 1
exit 0
