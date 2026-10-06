#!/bin/bash
# verify-solo-backup.sh - LSOLO 20 (S.50): BACKUP.ACCOUNT, RESTORE.ACCOUNT and
# SETTINGS.REPORT on SD Core for Linux Solo, including the start-up swap.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-backup.sh HOME_DIR ACCOUNT_PASSWORD_FILE ADMIN_PASSWORD_FILE
#
# On a tree solo-stage.sh built with --account-password-file and
# --admin-password-file (standalone), with SD running.  No sudo.  THE TREE'S
# ACCOUNT IS CHANGED: it gets a file zzbk, a program and a restore - use a
# scratch tree, never an installed one.  Exit 0 every leg passed, 1 a leg
# failed, 2 it could not run.  Every leg prints what it expected and, on a
# failure, what it saw; passwords are never printed.
#
# WHAT IT MEASURES
#   1  BACKUP.ACCOUNT without ADMIN is refused (an administrator verb)
#   2  with ADMIN: BACKUP.ACCOUNT ALL TO <dir> reports one account and a zip
#   3  the zip's manifest says product: linux-solo, type: USER, and carries no
#      route.* / os.group (agreed with Windows Solo, 2026-10-02T1000), and its
#      files/bytes/dirs equal what the archive holds
#   4  SETTINGS.REPORT prints [system] product: linux-solo, [mode] and [policy]
#   5  RESTORE.ACCOUNT of the account: "restored and waiting", the marker is
#      written, and NOTHING has changed yet (the damage done before is still
#      there) - Solo cannot replace the session's own account in place
#   6  sd -stop, sd -start: the start prints RESTORED, the marker is gone,
#      .sdrestore.previous holds the old tree, sdrestore.log says DONE
#   7  after the swap the data is back: 52 records, MyRec and myrec both
#   8  another session logged in: BACKUP.ACCOUNT refuses (13000) and names it
# WHAT IT DOES NOT MEASURE
#   A managed tree, a restore from another Linux user's backup (ruling 5, the
#   path rewrite is the multi-user product's tested code), the API refusal
#   while a hold is set, and the systemd unit (sd -start is what it runs).

set -uo pipefail
refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 3 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE ADMIN_PASSWORD_FILE"
H="$1"; PWF="$2"; ADF="$3"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -x "$H/bin/sd-accarchive" ] || refuse "$H/bin/sd-accarchive is not there - staged before LSOLO 20?"
[ -s "$PWF" ] && [ -s "$ADF" ] || refuse "cannot read the password files"
GOOD="$(head -1 "$PWF")"; ADMINPW="$(head -1 "$ADF")"
[ -n "$GOOD" ] && [ -n "$ADMINPW" ] || refuse "a password file's first line is empty"
SD="$H/bin/sd-solo"
cd "$H" || refuse "cannot enter $H"
BK="$H/zz-backups"
rm -rf "$BK"; mkdir -p "$BK"

echo "verify-solo-backup inputs:"
echo "  tree       : $H"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  backups to : $BK"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
leg() {   # leg NAME EXPECT OK(0/1) SAW
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}
sess() {
  printf '%s\n' "$GOOD" "$@" OFF | timeout 300 "$SD" 2>&1 \
    | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' \
    | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core for Linux Solo, the'
}
one() { printf '%s\n' "$1" | tail -3 | tr '\n' ' '; }

# The test data: a file of 52 records, two of them a case-only pair.
mkdir -p "$H/user_accounts/sduser/bp"
cat > "$H/user_accounts/sduser/bp/zzfill" <<'EOF'
open 'zzbk' to f else stop 'ZZFILL: no zzbk'
clearfile f
for i = 1 to 50
   write 'value ':i to f, 'rec':i
next i
write 'upper' to f, 'MyRec'
write 'lower' to f, 'myrec'
crt 'ZZFILL wrote 52'
end
EOF
out="$(sess 'CREATE.FILE zzbk' 'BASIC BP ZZFILL' 'RUN BP ZZFILL' 'COUNT zzbk')"
printf '%s\n' "$out" | grep -q '^52 record(s) counted' || refuse "could not set up the test data: $(one "$out")"
echo "  test data  : zzbk, 52 records (MyRec and myrec among them)"

# ---- 1
out="$(sess "BACKUP.ACCOUNT ALL TO $BK")"
if printf '%s\n' "$out" | grep -q 'Command requires administrator privileges' && [ -z "$(ls "$BK")" ]; then
  leg "1 BACKUP.ACCOUNT needs ADMIN" "refused, no zip" 0 ""
else leg "1 BACKUP.ACCOUNT needs ADMIN" "refused, no zip" 1 "$(one "$out"); $(ls "$BK")"; fi

# ---- 2
out="$(sess ADMIN "$ADMINPW" "BACKUP.ACCOUNT ALL TO $BK")"
Z="$(ls "$BK"/SD-*-all-*.zip 2>/dev/null | head -1)"
if printf '%s\n' "$out" | grep -q '^Backed up 1 account(s) to ' && [ -n "$Z" ]; then
  leg "2 BACKUP.ACCOUNT ALL" "'Backed up 1 account(s)' and a zip" 0 ""
else leg "2 BACKUP.ACCOUNT ALL" "'Backed up 1 account(s)' and a zip" 1 "$(one "$out")"; fi

# ---- 3
if [ -n "$Z" ]; then
  m="$(python3 - "$Z" <<'EOF'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
man = z.read("manifest.txt").decode()
keys = dict(l.split(": ", 1) for l in man.splitlines() if ": " in l)
names = z.namelist()
files = [n for n in names if n.startswith("accounts/sduser/") and not n.endswith("/")]
dirs = [n for n in names if n.startswith("accounts/sduser/") and n.endswith("/") and n != "accounts/sduser/"]
size = sum(z.getinfo(n).file_size for n in files)
ok = (keys.get("product") == "linux-solo" and keys.get("type") == "USER"
      and not any(k.startswith("route.") or k == "os.group" for k in keys)
      and int(keys.get("files", -1)) == len(files) and int(keys.get("bytes", -1)) == size
      and int(keys.get("dirs", -1)) == len(dirs))
print("OK" if ok else "BAD", "product=%s type=%s files=%s/%d bytes=%s/%d dirs=%s/%d" % (
    keys.get("product"), keys.get("type"), keys.get("files"), len(files), keys.get("bytes"), size,
    keys.get("dirs"), len(dirs)))
EOF
)"
  case "$m" in OK*) leg "3 the manifest is Solo's and matches the zip" "linux-solo, USER, no route keys, counts equal" 0 "" ;;
               *) leg "3 the manifest is Solo's and matches the zip" "linux-solo, USER, no route keys, counts equal" 1 "$m" ;; esac
else leg "3 the manifest is Solo's and matches the zip" "a zip to read" 1 "no zip"; fi

# ---- 4
out="$(sess ADMIN "$ADMINPW" SETTINGS.REPORT)"
if printf '%s\n' "$out" | grep -q '^product: linux-solo' && printf '%s\n' "$out" | grep -q '^\[mode\]' \
   && printf '%s\n' "$out" | grep -qx 'not managed (no global password)' \
   && ! printf '%s\n' "$out" | grep -qi 'standalone' \
   && printf '%s\n' "$out" | grep -q '^\[policy\]'; then
  leg "4 SETTINGS.REPORT" "product: linux-solo, [mode] 'not managed (no global password)' (LSOLO 38; never 'standalone'), [policy]" 0 ""
else leg "4 SETTINGS.REPORT" "product: linux-solo, [mode] 'not managed (no global password)', [policy]" 1 "$(one "$out")"; fi

# ---- 5: damage, then restore - which must change nothing yet
cat > "$H/user_accounts/sduser/bp/zzdamage" <<'EOF'
open 'zzbk' to f else stop
for i = 1 to 40 ; delete f, 'rec':i ; next i
delete f, 'MyRec'
crt 'ZZDAMAGE done'
end
EOF
sess 'BASIC BP ZZDAMAGE' 'RUN BP ZZDAMAGE' >/dev/null
out="$(sess ADMIN "$ADMINPW" "RESTORE.ACCOUNT $Z ALL NO.QUERY" 'COUNT zzbk')"
if printf '%s\n' "$out" | grep -q 'sduser is restored and waiting' && [ -f "$H/.sdrestore.pending" ] \
   && printf '%s\n' "$out" | grep -q '^11 record(s) counted'; then
  leg "5 RESTORE.ACCOUNT waits for the next start" "'restored and waiting', the marker, data unchanged (11)" 0 ""
else leg "5 RESTORE.ACCOUNT waits for the next start" "'restored and waiting', the marker, data unchanged (11)" 1 \
  "$(one "$out"); marker: $(ls -a "$H" | grep -c sdrestore.pending)"; fi

# ---- 6: the start-up swap
"$SD" -stop >/dev/null 2>&1
# To a FILE, never $(...): sd -start's sdlnxd daemonizes with its stdout still
# open, so a command substitution waits for an EOF that never comes (measured:
# the first run of this script hung here, though the swap had completed).
start_log="$(mktemp)"
"$SD" -start > "$start_log" 2>&1
start_out="$(cat "$start_log")"; rm -f "$start_log"
if printf '%s\n' "$start_out" | grep -q '^RESTORED ' && [ ! -e "$H/.sdrestore.pending" ] \
   && [ -d "$H/.sdrestore.previous" ] && grep -q 'DONE' "$H/sdrestore.log" 2>/dev/null; then
  leg "6 sd -start applies the waiting restore" "RESTORED, marker gone, .sdrestore.previous, log DONE" 0 ""
else leg "6 sd -start applies the waiting restore" "RESTORED, marker gone, .sdrestore.previous, log DONE" 1 \
  "$(printf '%s' "$start_out" | tr '\n' ' ')"; fi

# ---- 7
out="$(sess 'COUNT zzbk' 'CT zzbk MyRec myrec')"
if printf '%s\n' "$out" | grep -q '^52 record(s) counted' && printf '%s\n' "$out" | grep -q 'upper' \
   && printf '%s\n' "$out" | grep -q 'lower'; then
  leg "7 the data is back after the swap" "52 records, MyRec=upper, myrec=lower" 0 ""
else leg "7 the data is back after the swap" "52 records, MyRec=upper, myrec=lower" 1 "$(one "$out")"; fi

# ---- 8: another session in
( printf '%s\nSLEEP 20\nOFF\n' "$GOOD" | timeout 60 "$SD" >/dev/null 2>&1 ) &
bg=$!
sleep 4
out="$(sess ADMIN "$ADMINPW" "BACKUP.ACCOUNT ALL TO $BK")"
wait "$bg" 2>/dev/null
if printf '%s\n' "$out" | grep -q 'other session(s) are logged in' && printf '%s\n' "$out" | grep -q '^  user '; then
  leg "8 another session in: BACKUP refuses and names it" "13000 and a '  user ...' line" 0 ""
else leg "8 another session in: BACKUP refuses and names it" "13000 and a '  user ...' line" 1 "$(one "$out")"; fi

echo
[ "$legs" -gt 0 ] || refuse "no leg ran"
echo "verify-solo-backup: $pass of $legs legs passed"
[ "$fail" -eq 0 ] && exit 0 || exit 1
