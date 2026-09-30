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
printf 'verify-solo pid=%s\n' "$$" > "$H/\$internal"     # the internal door is one-shot (ruling 13)
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

# ======================================================================
# SET.PASSWORD (ruling 39).  sess_as PW LINES... is sess() with a chosen first
# line (the password the session signs in with).  Every leg that changes a
# password changes it BACK before it ends, and says so, so a failed leg cannot
# leave the tree with a password nobody knows: if the restore fails the run
# stops with exit 2 and names the password that is now in force.
sess_as() {
  local first="$1"; shift
  printf '%s\n' "$first" "$@" OFF | timeout 120 "$SD" 2>&1 \
    | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' \
    | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core, the'
}
NEWPW='New-Pass-3!'

# ---- 17. SET.PASSWORD (account): the current password is asked first; a wrong
# one changes nothing; the right one changes it, the old stops working, the new
# works, the kept copy for one-shot commands follows; then it is put back.
# INTERACTIVE sessions check the password typed; a ONE-SHOT ("sd WHO") tries the
# kept copy first and never looks at its input when that verifies, so it cannot
# tell an old password from the new one - it is used only for the kept-copy check.
o_wrong="$(sess_as "$GOOD" SET.PASSWORD 'not-the-current' "$NEWPW" "$NEWPW")"
w_old="$(sess_as "$GOOD" WHO | grep -cE '^[0-9]+ sduser$')"
o_ok="$(sess_as "$GOOD" SET.PASSWORD "$GOOD" "$NEWPW" "$NEWPW")"
n_old="$(printf '%s\nOFF\n' "$GOOD" | timeout 60 "$SD" 2>&1 | strip | grep -cx 'Wrong password')"
n_new="$(sess_as "$NEWPW" WHO | grep -cE '^[0-9]+ sduser$')"
n_kept="$(echo "" | timeout 60 "$SD" WHO 2>&1 | strip | grep -cE '^[0-9]+ sduser$')"
o_back="$(sess_as "$NEWPW" SET.PASSWORD "$NEWPW" "$GOOD" "$GOOD")"
b_ok="$(sess_as "$GOOD" WHO | grep -cE '^[0-9]+ sduser$')"
if [ "$b_ok" -ne 1 ]; then
  echo "FATAL: the account password could not be put back; the tree's account password is now: $NEWPW" >&2
  exit 2
fi
if printf '%s\n' "$o_wrong" | grep -qx 'Wrong password - the password is unchanged' && [ "$w_old" -eq 1 ] \
   && printf '%s\n' "$o_ok" | grep -qx 'Password changed' \
   && [ "$n_old" -eq 1 ] && [ "$n_new" -eq 1 ] && [ "$n_kept" -eq 1 ] \
   && printf '%s\n' "$o_back" | grep -qx 'Password changed'; then
  leg "17 SET.PASSWORD changes the account password" "wrong current refused; right one changes it, old stops, new works, one-shot follows; put back" 0 "as expected"
else
  leg "17 SET.PASSWORD changes the account password" "wrong current refused; right one changes it, old stops, new works, one-shot follows; put back" 1 "wrong: $(last "$o_wrong") old-still-works=$w_old / ok: $(last "$o_ok") old-refused=$n_old new-works=$n_new kept=$n_kept"
fi

# ---- 18. SET.PASSWORD ADMIN needs ADMIN; a weak password is refused and the
# administrator password is unchanged; a good one changes it and is put back.
o_no="$(sess_as "$GOOD" 'SET.PASSWORD ADMIN')"
o_weak="$(sess_as "$GOOD" ADMIN "$ADMINPW" 'SET.PASSWORD ADMIN' weak weak)"
still="$(sess_as "$GOOD" ADMIN "$ADMINPW" | grep -cx 'Administrator commands unlocked for this session')"
NEWADMIN='Admin-New-4!'
o_chg="$(sess_as "$GOOD" ADMIN "$ADMINPW" 'SET.PASSWORD ADMIN' "$NEWADMIN" "$NEWADMIN")"
new_unlocks="$(sess_as "$GOOD" ADMIN "$NEWADMIN" | grep -cx 'Administrator commands unlocked for this session')"
o_back="$(sess_as "$GOOD" ADMIN "$NEWADMIN" 'SET.PASSWORD ADMIN' "$ADMINPW" "$ADMINPW")"
back_unlocks="$(sess_as "$GOOD" ADMIN "$ADMINPW" | grep -cx 'Administrator commands unlocked for this session')"
if [ "$back_unlocks" -ne 1 ]; then
  echo "FATAL: the administrator password could not be put back; it is now: $NEWADMIN" >&2
  exit 2
fi
if printf '%s\n' "$o_no" | grep -qx "$NEEDS" \
   && printf '%s\n' "$o_weak" | grep -qx 'A password needs at least 8 characters, with a lower-case letter, an upper-case letter, a digit and a symbol.' \
   && [ "$still" -eq 1 ] \
   && printf '%s\n' "$o_chg" | grep -qx 'Password changed' && [ "$new_unlocks" -eq 1 ] \
   && printf '%s\n' "$o_back" | grep -qx 'Password changed'; then
  leg "18 SET.PASSWORD ADMIN" "needs ADMIN; weak refused, old still unlocks; good changes it; put back" 0 "as expected"
else
  leg "18 SET.PASSWORD ADMIN" "needs ADMIN; weak refused, old still unlocks; good changes it; put back" 1 "no-admin: $(last "$o_no") weak: $(last "$o_weak") still=$still chg: $(last "$o_chg") new-unlocks=$new_unlocks"
fi

# ---- 19. SET.PASSWORD GLOBAL on a standalone tree says so (no global password).
out="$(sess_as "$GOOD" 'SET.PASSWORD GLOBAL')"
if printf '%s\n' "$out" | grep -qx 'This computer is standalone - it has no global password'; then
  leg "19 SET.PASSWORD GLOBAL is refused when standalone" "'This computer is standalone...'" 0 "refused"
else
  leg "19 SET.PASSWORD GLOBAL is refused when standalone" "'This computer is standalone...'" 1 "$(last "$out")"
fi

# ======================================================================
# THE INTERNAL DOOR (ruling 13, LSOLO 9): "sd -internal" is closed on a delivered
# system and opened one session at a time by a marker file $internal, which LOGIN
# deletes on admission and refuses when older than ten minutes.
MARK="$H/\$internal"
int_try() { timeout 90 "$SD" -internal WHO 2>&1 | strip; }
audit_lines_before="$(wc -l < "$H/audit")"
rm -f "$MARK"

# ---- 20. no marker: refused, and it says nothing about why (it is not published).
o="$(int_try)"
if printf '%s\n' "$o" | grep -qx 'Connection terminated' && ! printf '%s\n' "$o" | grep -qE '^[0-9]+ sdsys$' \
   && ! printf '%s\n' "$o" | grep -qi 'marker'; then
  leg "20 sd -internal with no marker is refused" "'Connection terminated', no session, the screen does not name the marker" 0 "refused"
else
  leg "20 sd -internal with no marker is refused" "'Connection terminated', no session" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

# ---- 21. a fresh marker admits ONE session, announces itself, and is consumed.
printf 'verify-solo pid=%s\n' "$$" > "$MARK"
o1="$(int_try)"
gone=0; [ -e "$MARK" ] && gone=1
o2="$(int_try)"
if printf '%s\n' "$o1" | grep -qx 'Internal session admitted (opened by verify-solo pid='"$$"')' \
   && printf '%s\n' "$o1" | grep -qE '^[0-9]+ sdsys$' && [ "$gone" -eq 0 ] \
   && printf '%s\n' "$o2" | grep -qx 'Connection terminated' && ! printf '%s\n' "$o2" | grep -qE '^[0-9]+ sdsys$'; then
  leg "21 a marker admits one session and is consumed" "announced, WHO answers sdsys, marker gone, the next attempt refused" 0 "as expected"
else
  leg "21 a marker admits one session and is consumed" "announced; WHO sdsys; marker gone; next refused" 1 "first: $(printf '%s\n' "$o1" | grep -E 'admitted|sdsys' | tr '\n' ' ') marker-left=$gone second: $(last "$o2")"
fi

# ---- 22. a stale marker (older than ten minutes) is refused - and still consumed.
printf 'verify-solo stale pid=%s\n' "$$" > "$MARK"
touch -d '20 minutes ago' "$MARK" 2>/dev/null || refuse "touch -d is not available - leg 22 would measure nothing"
o="$(int_try)"
left=0; [ -e "$MARK" ] && left=1
if printf '%s\n' "$o" | grep -qx 'Connection terminated' && ! printf '%s\n' "$o" | grep -qE '^[0-9]+ sdsys$' && [ "$left" -eq 0 ]; then
  leg "22 a stale marker is refused" "'Connection terminated', no session, marker consumed" 0 "refused"
else
  leg "22 a stale marker is refused" "refused, no session, marker consumed" 1 "$(last "$o") marker-left=$left"
fi

# ---- 23. every use is audited: the admission, and both kinds of refusal.
new_audit="$(tail -n +"$((audit_lines_before + 1))" "$H/audit")"
if printf '%s\n' "$new_audit" | grep -q 'INTERNAL SESSION ADMITTED account=sdsys writer=verify-solo pid=' \
   && printf '%s\n' "$new_audit" | grep -q 'reason=no internal marker' \
   && printf '%s\n' "$new_audit" | grep -q 'reason=the internal marker had expired'; then
  leg "23 the internal door is audited" "admitted, 'no internal marker', 'had expired'" 0 "3 kinds present"
else
  leg "23 the internal door is audited" "admitted, 'no internal marker', 'had expired'" 1 "$(printf '%s\n' "$new_audit" | grep -E 'INTERNAL|internal marker' | cut -c1-90 | tr '\n' '|')"
fi

echo
echo "verify-solo: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
