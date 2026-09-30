#!/bin/bash
# verify-solo.sh - does an SD Core for Linux Solo tree behave as ruled?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo.sh HOME_DIR PASSWORD_FILE
#
# No sudo.  Run as the person who owns the tree.  HOME_DIR is a tree that
# solo-stage.sh built with --account-password-file PASSWORD_FILE and whose
# daemon is running (solo-stage.sh leaves it running).  The Linux counterpart
# of SD Core Solo for Windows' verify-solo.ps1, which has 19 legs; this has the
# legs LSOLO 6 part 2 built and grows with it (LSOLO 10).
#
# EVERY LEG PRINTS THE COMMAND IT RAN, WHAT IT SAW, AND WHAT IT EXPECTED, AND
# ANCHORS ON THE SUCCESS WORDING - never on an exit code (sd exits 0 when the
# command never ran) and never on a string the refusal also prints.  A leg
# whose input could not have reached the condition refuses to run (exit 2).
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse "usage: bash $0 HOME_DIR PASSWORD_FILE"
H="$1"; PWF="$2"
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
STORED="$H/\$cred/\$STORED"
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
  if grep -q -F -- "$GOOD" "$H/audit" "$H/errlog" 2>/dev/null; then
    leg "8 password not logged" "no occurrence in audit or errlog" 1 "FOUND in a log"
  else
    leg "8 password not logged" "no occurrence in audit or errlog" 0 "none in $(wc -l < "$H/audit") audit lines"
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

echo
echo "verify-solo: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
