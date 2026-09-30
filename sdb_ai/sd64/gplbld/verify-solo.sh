#!/bin/bash
# verify-solo.sh - does an SD Core for Linux Solo tree behave as ruled?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo.sh HOME_DIR ACCOUNT_PASSWORD_FILE ADMIN_PASSWORD_FILE
#
# No sudo.  Run as the person who owns the tree.  HOME_DIR is a tree that
# solo-stage.sh built with --account-password-file and --admin-password-file
# (the same two files) and whose daemon is running (solo-stage.sh leaves it
# running).  The Linux counterpart of SD Core Solo for Windows' verify-solo.ps1,
# which has 19 legs; this has the legs LSOLO 6 built and grows with it (LSOLO 10).
#
# EVERY LEG PRINTS THE COMMAND IT RAN, WHAT IT SAW, AND WHAT IT EXPECTED, AND
# ANCHORS ON THE SUCCESS WORDING - never on an exit code (sd exits 0 when the
# command never ran) and never on a string the refusal also prints.  A leg
# whose input could not have reached the condition refuses to run (exit 2).
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 3 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE ADMIN_PASSWORD_FILE"
H="$1"; PWF="$2"; ADF="$3"
[ -s "$ADF" ] || refuse "cannot read the administrator password file $ADF"
ADMINPW="$(head -1 "$ADF")"
[ -n "$ADMINPW" ] || refuse "the administrator password file's first line is empty"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd" ] || refuse "$H/bin/sd is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -s "$PWF" ] || refuse "cannot read the password file $PWF"
GOOD="$(head -1 "$PWF")"
[ -n "$GOOD" ] || refuse "the password file's first line is empty"
SD="$H/bin/sd"
cd "$H" || refuse "cannot enter $H"

echo "verify-solo inputs:"
echo "  tree       : $H"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  password   : from $PWF (length ${#GOOD}, never printed)"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {   # leg NAME EXPECT-DESCRIPTION OK(0/1) SAW
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}
last() { printf '%s\n' "$1" | strip | grep -v '^[[:space:]]*$' | tail -1; }

# ---- 1. the account is sduser whatever the Linux user is called.
out="$(printf '%s\n' "$GOOD" | timeout 60 "$SD" WHO 2>&1)"
l="$(last "$out")"
case "$l" in
  [0-9]*" sduser") leg "1 WHO says sduser" "a line '<n> sduser'" 0 "$l" ;;
  *) leg "1 WHO says sduser" "a line '<n> sduser'" 1 "$l" ;;
esac

# ---- 2. the kept password: a one-shot with NOTHING on its input still runs.
out="$(echo "" | timeout 60 "$SD" WHO 2>&1)"
l="$(last "$out")"
case "$l" in
  [0-9]*" sduser") leg "2 one-shot uses the kept password" "'<n> sduser' with an empty input" 0 "$l" ;;
  *) leg "2 one-shot uses the kept password" "'<n> sduser' with an empty input" 1 "$l" ;;
esac

# ---- 3. a wrong password on an interactive session is refused, and says so.
out="$(printf 'not-the-password\n' | timeout 60 "$SD" 2>&1 | strip)"
if printf '%s\n' "$out" | grep -qx 'Wrong password' && printf '%s\n' "$out" | grep -qx 'Connection terminated'; then
  leg "3 wrong password refused" "'Wrong password' then 'Connection terminated'" 0 "both lines"
else
  leg "3 wrong password refused" "'Wrong password' then 'Connection terminated'" 1 "$(last "$out")"
fi

# ---- 4. the right password on an interactive session gets a session.
out="$(printf '%s\nWHO\nOFF\n' "$GOOD" | timeout 60 "$SD" 2>&1 | strip)"
if printf '%s\n' "$out" | grep -qE '^[0-9]+ sduser$'; then
  leg "4 right password gets a session" "WHO answers '<n> sduser'" 0 "$(printf '%s\n' "$out" | grep -E '^[0-9]+ sduser$' | head -1)"
else
  leg "4 right password gets a session" "WHO answers '<n> sduser'" 1 "$(last "$out")"
fi

# ---- 5. a stale kept password falls back to the input; both outcomes.
STORED="$H/\$cred/\$stored"    # lower case: a case-sensitive filesystem (see gpl.bp/admin)
[ -f "$STORED" ] || refuse "$STORED is missing - the tree has no kept password to make stale"
cp "$STORED" "$STORED.verify-solo.bak" || refuse "cannot back up $STORED"
printf 'SDUSER\376Stale-Old-Pw-1!\n' > "$STORED"
out_ok="$(printf '%s\n' "$GOOD" | timeout 60 "$SD" WHO 2>&1)"
out_bad="$(printf 'bad\n' | timeout 60 "$SD" WHO 2>&1)"
cp "$STORED.verify-solo.bak" "$STORED"; rm -f "$STORED.verify-solo.bak"
l1="$(last "$out_ok")"; l2="$(printf '%s\n' "$out_bad" | strip | grep -cx 'Wrong password')"
case "$l1" in
  [0-9]*" sduser") if [ "$l2" -ge 1 ]; then leg "5 stale kept password falls back to the input" "right one accepted, wrong one refused" 0 "$l1 / refused"
                   else leg "5 stale kept password falls back to the input" "right one accepted, wrong one refused" 1 "wrong one was not refused: $(last "$out_bad")"; fi ;;
  *) leg "5 stale kept password falls back to the input" "right one accepted, wrong one refused" 1 "right one gave: $l1" ;;
esac

# ---- 6. the credential register is private.
m_dir="$(stat -c '%a' "$H/\$cred")"; m_file="$(stat -c '%a' "$STORED")"
if [ "$m_dir" = "700" ] && [ "$m_file" = "600" ]; then
  leg "6 \$cred is private" "directory 700, \$STORED 600" 0 "$m_dir / $m_file"
else
  leg "6 \$cred is private" "directory 700, \$STORED 600" 1 "$m_dir / $m_file"
fi

# ---- 7. sd will not run as root (a user namespace makes euid 0 without sudo).
if unshare -Ur true 2>/dev/null; then
  out="$(unshare -Ur "$SD" WHO 2>&1 | strip)"
  if printf '%s\n' "$out" | grep -qx 'SD Core for Linux Solo does not run as root.'; then
    leg "7 refuses uid 0" "the root refusal line" 0 "refused"
  else
    leg "7 refuses uid 0" "the root refusal line" 1 "$(last "$out")"
  fi
else
  echo "  [SKIP] 7 refuses uid 0 | user namespaces are not available here; NOT MEASURED"
fi

# ---- 8. the password is nowhere in the audit trail or the error log.
if [ -s "$H/audit" ]; then
  if grep -q -F -e "$GOOD" -e "$ADMINPW" "$H/audit" "$H/errlog" 2>/dev/null; then
    leg "8 passwords not logged" "neither password occurs in audit or errlog" 1 "FOUND in a log"
  else
    leg "8 passwords not logged" "neither password occurs in audit or errlog" 0 "none in $(wc -l < "$H/audit") audit lines"
  fi
else
  refuse "the audit trail is empty - leg 8 would measure nothing"
fi

# ---- 9. a weak password is refused by the program that sets it, and NOTHING
# is stored: the credential record is byte-identical afterwards.  The record
# is read before, so the leg refuses to run against a tree with none.
CREDREC="$H/\$cred/sduser"
[ -f "$CREDREC" ] || refuse "$CREDREC is missing - leg 9 would compare nothing"
before="$(md5sum < "$CREDREC")"
out="$(printf 'weak\n' | timeout 60 "$SD" -internal RUN gpl.bp solo_password ACCOUNT sduser 2>&1 | strip)"
after="$(md5sum < "$CREDREC")"
if printf '%s\n' "$out" | grep -qx 'solo_password: nothing was stored.' && [ "$before" = "$after" ] \
   && ! printf '%s\n' "$out" | grep -qx 'SOLO PASSWORD SET ACCOUNT'; then
  leg "9 a weak password is refused and nothing stored" "'nothing was stored', record unchanged, no success line" 0 "refused; record unchanged"
else
  leg "9 a weak password is refused and nothing stored" "'nothing was stored', record unchanged, no success line" 1 "$(last "$out") / record $( [ "$before" = "$after" ] && echo unchanged || echo CHANGED )"
fi

# ======================================================================
# The ADMIN gate (LSOLO 6 part 3).  sess LINES... feeds a session: the account
# password first, then each line, then OFF; the output is stripped of screen
# noise and the sign-on banner.

sess() {
  printf '%s\n' "$GOOD" "$@" OFF | timeout 120 "$SD" 2>&1 \
    | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' \
    | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core, the'
}
NEEDS='Command requires administrator privileges'

# ---- 10. a wrong administrator password is refused, and the session stays locked.
out="$(sess ADMIN 'not-the-admin-password' LISTU)"
if printf '%s\n' "$out" | grep -qx 'Wrong password - administrator commands stay locked' \
   && printf '%s\n' "$out" | grep -qx "$NEEDS" \
   && ! printf '%s\n' "$out" | grep -q 'Administrator commands unlocked'; then
  leg "10 wrong ADMIN password refused" "'Wrong password...' then LISTU still refused" 0 "refused; still locked"
else
  leg "10 wrong ADMIN password refused" "'Wrong password...' then LISTU still refused" 1 "$(last "$out")"
fi

# ---- 11. the ACCOUNT password does not unlock ADMIN (two different secrets).
out="$(sess ADMIN "$GOOD" LISTU)"
if printf '%s\n' "$out" | grep -qx 'Wrong password - administrator commands stay locked' \
   && ! printf '%s\n' "$out" | grep -q 'Administrator commands unlocked'; then
  leg "11 account password does not unlock ADMIN" "'Wrong password...'" 0 "refused"
else
  leg "11 account password does not unlock ADMIN" "'Wrong password...'" 1 "$(last "$out")"
fi

# ---- 12. the maintenance verbs are refused without ADMIN - each on its own line.
# Anchored per verb: the verb's echo line, then the refusal on the next line.
bad=""
for v in "LISTU" "CONFIG" "LIST.LOCKS" "LIST.READU" "LOCK 1" "CLEAR.LOCKS" "SET.DATE 1" "CLEAN.ACCOUNT" "UPDATE.ACCOUNTS"; do
  o="$(sess "$v")"
  printf '%s\n' "$o" | grep -qx "$NEEDS" || bad="$bad [$v: $(last "$o")]"
done
if [ -z "$bad" ]; then leg "12 maintenance verbs refused without ADMIN" "9 verbs each say '$NEEDS'" 0 "9 of 9"
else leg "12 maintenance verbs refused without ADMIN" "9 verbs each say '$NEEDS'" 1 "$bad"; fi

# ---- 13. CONFIG GPL needs no ADMIN (the sign-on banner tells every session to type it).
out="$(sess 'CONFIG GPL')"
if printf '%s\n' "$out" | grep -qx 'Most of SD is licensed under the GPL v3.0.' \
   && ! printf '%s\n' "$out" | grep -qx "$NEEDS"; then
  leg "13 CONFIG GPL needs no ADMIN" "the licence text, no refusal" 0 "shown"
else
  leg "13 CONFIG GPL needs no ADMIN" "the licence text, no refusal" 1 "$(last "$out")"
fi

# ---- 14. the right administrator password unlocks, LISTU then runs, ADMIN OFF locks.
out="$(sess ADMIN "$ADMINPW" LISTU 'ADMIN OFF' LISTU)"
n_refused="$(printf '%s\n' "$out" | grep -cx "$NEEDS")"
if printf '%s\n' "$out" | grep -qx 'Administrator commands unlocked for this session' \
   && printf '%s\n' "$out" | grep -q 'Username' \
   && printf '%s\n' "$out" | grep -qx 'Administrator commands locked' \
   && [ "$n_refused" -eq 1 ]; then
  leg "14 ADMIN unlocks, ADMIN OFF locks" "unlocked, LISTU lists, locked, LISTU refused once" 0 "as expected"
else
  leg "14 ADMIN unlocks, ADMIN OFF locks" "unlocked, LISTU lists, locked, LISTU refused once" 1 "refusals=$n_refused; $(last "$out")"
fi

# ---- 15. direct VOC edits are refused without ADMIN and allowed with it.
# 'who' is a real VOC record; 'zzcopy' is the scratch id, absent before and after.
VOCMSG='The VOC can only be changed after ADMIN (the administrator password)'
before="$(sess 'COUNT VOC' | grep -E 'record\(s\) counted')"
[ -n "$before" ] || refuse "COUNT VOC printed no count - leg 15 would compare nothing"
out="$(sess 'DELETE VOC who' 'COPY FROM VOC TO VOC who,zzcopy' 'CLEAR.FILE VOC' '.S zzsave 1' 'COUNT VOC')"
n_msg="$(printf '%s\n' "$out" | grep -cx "$VOCMSG")"
after="$(printf '%s\n' "$out" | grep -E 'record\(s\) counted')"
out2="$(sess ADMIN "$ADMINPW" 'COPY FROM VOC TO VOC who,zzcopy' 'DELETE VOC zzcopy' 'COUNT VOC')"
after2="$(printf '%s\n' "$out2" | grep -E 'record\(s\) counted')"
if [ "$n_msg" -eq 4 ] && [ "$before" = "$after" ] \
   && printf '%s\n' "$out2" | grep -qx '1 record(s) copied.' \
   && printf '%s\n' "$out2" | grep -qx '1 record(s) deleted' && [ "$before" = "$after2" ]; then
  leg "15 VOC edits need ADMIN" "4 refusals, VOC unchanged; with ADMIN a scratch copy and delete work" 0 "$n_msg refusals; $before"
else
  leg "15 VOC edits need ADMIN" "4 refusals, VOC unchanged; with ADMIN a scratch copy and delete work" 1 "refusals=$n_msg; before='$before' after='$after' after-admin='$after2'"
fi

# ---- 16. a user program's own WRITE to the VOC is refused in C without ADMIN.
PROG="$H/user_accounts/sduser/bp/verify_t3"
cat > "$PROG" <<'BASIC'
   open 'voc' to v else display 'T3 cannot open voc' ; stop
   write 'X' to v, 'zztest' on error
      display 'T3 WRITE refused, status ' : status()
      stop
   end
   display 'T3 WRITE done'
   delete v, 'zztest' on error
      display 'T3 DELETE refused, status ' : status()
      stop
   end
   display 'T3 DELETE done'
end
BASIC
comp="$(sess 'BASIC BP verify_t3')"
printf '%s\n' "$comp" | grep -qx 'Compiled 1 program(s) with no errors' || refuse "leg 16's probe program did not compile: $(last "$comp")"
o1="$(sess 'RUN BP verify_t3')"
o2="$(sess ADMIN "$ADMINPW" 'RUN BP verify_t3')"
if printf '%s\n' "$o1" | grep -qx 'T3 WRITE refused, status 3035' \
   && printf '%s\n' "$o2" | grep -qx 'T3 WRITE done' && printf '%s\n' "$o2" | grep -qx 'T3 DELETE done'; then
  leg "16 a program's own VOC write needs ADMIN" "refused (status 3035) without, done with" 0 "as expected"
else
  leg "16 a program's own VOC write needs ADMIN" "refused (status 3035) without, done with" 1 "without: $(last "$o1") / with: $(last "$o2")"
fi
rm -f "$PROG"

echo
echo "verify-solo: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
