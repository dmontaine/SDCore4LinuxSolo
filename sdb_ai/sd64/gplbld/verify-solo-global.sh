#!/bin/bash
# verify-solo-global.sh - the MANAGED-mode server controls of SD Core for Linux Solo
# (LSOLO 12; rulings 33, 34 and 36 of Solo for Windows, its verify-solo legs 16 and 17).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-global.sh HOME_DIR ACCOUNT_PW_FILE ADMIN_PW_FILE GLOBAL_PW_FILE
#
# No sudo.  Run as the person who owns the tree.  HOME_DIR is a tree that solo-stage.sh
# built with all three password files (managed mode) and whose daemon is running.  Do NOT
# use a tree staged with --deny-verbs naming WHO: the legs add and remove WHO themselves.
#
# EVERY LEG PRINTS WHAT IT RAN AND WHAT IT SAW, AND ANCHORS ON THE SUCCESS WORDING.
# The deny list and GLOBAL.BP.OUT are put back as they were, also on a failed run.
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 4 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PW_FILE ADMIN_PW_FILE GLOBAL_PW_FILE"
H="$1"; PWF="$2"; ADF="$3"; GLF="$4"
for f in "$PWF" "$ADF" "$GLF"; do [ -s "$f" ] || refuse "cannot read the password file $f"; done
GOOD="$(head -1 "$PWF")"; ADMINPW="$(head -1 "$ADF")"; GLOBALPW="$(head -1 "$GLF")"
[ -n "$GOOD" ] && [ -n "$ADMINPW" ] && [ -n "$GLOBALPW" ] || refuse "a password file's first line is empty"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -f "$H/\$cred/\$global" ] || refuse "$H is standalone (no \$cred/\$global) - these legs need managed mode"
SD="$H/bin/sd-solo"
cd "$H" || refuse "cannot enter $H"

echo "verify-solo-global inputs:"
echo "  tree       : $H"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
leg() {   # leg NAME EXPECT OK(0/1) SAW
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}
clean() {
  sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' \
    | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core for Linux Solo, the'
}
last() { printf '%s\n' "$1" | tail -1; }
# sess PW CMD... : one session, signed in with PW, ended with OFF.
sess() { local pw="$1"; shift; printf '%s\n' "$pw" "$@" OFF | timeout 120 "$SD" 2>&1 | clean; }
asuser()  { sess "$GOOD" "$@"; }
asadmin() { sess "$GOOD" ADMIN "$ADMINPW" "$@"; }
asglobal() { sess "$GLOBALPW" "$@"; }
count() { printf '%s\n' "$1" | grep -c -x -- "$2" || true; }

NEEDS='Command requires administrator privileges'
M28='The global catalogue can only be changed by the SD Core server'
M29="The global catalogue holds the SD Core server's programs from global.bp.out and is changed only by sync.global.catalog"
M30='The denied verbs can only be listed or changed by the SD Core server'

GBP="$H/global.bp.out"; GCAT="$H/gcat"; SUB=zzgsub; CALL=zzgcall
BP="$H/user_accounts/sduser/bp"; OUT="$H/user_accounts/sduser/bp.out"
[ -d "$GBP" ] || refuse "$GBP is not a directory - the tree predates LSOLO 12"
[ -d "$H/solo.policy" ] || refuse "$H/solo.policy is not a directory - the tree predates LSOLO 12"
[ -d "$BP" ] || refuse "$BP is not there"

# The on-disk name of the catalogue entry '*ZZGSUB' is SD's own encoding of the
# '*', so it is found by name, not spelled.
incat() { ls -A "$GCAT" | grep -i -c -- "$SUB" || true; }

cleanup() {
  rm -f "$BP/$SUB" "$BP/$CALL" "$OUT/$SUB" "$OUT/$CALL" "$GBP/$SUB" "$GBP/who" "$BP/zzgw"
  ls -A "$GCAT" | grep -i -- "$SUB" | while IFS= read -r f; do rm -f -- "$GCAT/$f"; done
  printf '%s\n' "$GLOBALPW" 'DENY.VERBS REMOVE WHO,SH,TIME' OFF | timeout 60 "$SD" >/dev/null 2>&1
}
trap cleanup EXIT

# The deny list the install set, so the legs can say it was put back.
base="$(asglobal DENY.VERBS | grep -E '^deny\.verbs [0-9]+:' | head -1)"
[ -n "$base" ] || refuse "a global session got no 'DENY.VERBS n:' line - cannot read the list"
echo "  deny list at the start: $base"
case "$base" in *who*|*sh*|*time*) refuse "WHO, SH or TIME is already on the deny list - the legs would remove it" ;; esac

# ---- 1. GLOBAL.BP.OUT is installed and empty, and nothing is catalogued from it.
n_obj="$(ls -A "$GBP" | wc -l)"
if [ "$n_obj" -eq 0 ] && [ "$(incat)" -eq 0 ]; then
  leg "1 GLOBAL.BP.OUT is installed and empty" "an empty directory and no *$SUB" 0 "0 objects"
else
  leg "1 GLOBAL.BP.OUT is installed and empty" "an empty directory and no *$SUB" 1 "$n_obj objects (left by an earlier run?)"
fi

# ---- 2. with ADMIN, sduser still cannot touch the global catalogue.
out="$(asadmin "CATALOG BP $SUB GLOBAL" "DELETE.CATALOG *$SUB" SYNC.GLOBAL.CATALOG 'COPY FROM VOC TO GLOBAL.BP.OUT who')"
n29="$(count "$out" "$M29")"; n28="$(count "$out" "$M28")"
n_obj="$(ls -A "$GBP" | wc -l)"
if [ "$n29" -eq 2 ] && [ "$n28" -eq 2 ] && ! printf '%s\n' "$out" | grep -q 'SYNC GLOBAL CATALOG DONE' \
   && [ "$n_obj" -eq 0 ]; then
  leg "2 with ADMIN the global catalogue is still refused" "CATALOG GLOBAL and DELETE.CATALOG (11029) x2, SYNC and COPY (11028) x2, GLOBAL.BP.OUT empty" 0 "2 + 2 refusals"
else
  leg "2 with ADMIN the global catalogue is still refused" "11029 x2, 11028 x2, no DONE line, GLOBAL.BP.OUT empty" 1 "11029=$n29 11028=$n28 objects=$n_obj; $(last "$out")"
fi

# ---- 3. a user program's own write to GLOBAL.BP.OUT is refused in C, ADMIN or not.
cat > "$BP/zzgw" <<'BASIC'
   openpath @sdsys:@ds:'global.bp.out' to g else display 'ZZGW cannot open' ; stop
   write 'X' to g, 'zzgw' on error
      display 'ZZGW WRITE refused, status ' : status()
      stop
   end
   display 'ZZGW WRITE done'
   delete g, 'zzgw' on error null
BASIC
out="$(asadmin 'BASIC BP zzgw' 'RUN BP zzgw')"
if printf '%s\n' "$out" | grep -q '^ZZGW WRITE refused, status ' && [ ! -e "$GBP/zzgw" ]; then
  leg "3 a program's own write to GLOBAL.BP.OUT is refused" "'ZZGW WRITE refused', nothing written" 0 "$(printf '%s\n' "$out" | grep 'ZZGW')"
else
  leg "3 a program's own write to GLOBAL.BP.OUT is refused" "'ZZGW WRITE refused', nothing written" 1 "$(printf '%s\n' "$out" | tail -4 | tr '\n' '|')"
fi
rm -f "$BP/zzgw" "$GBP/zzgw"

# ---- 4. the SD Core server adds a program, sduser CALLs it, the server removes it.
cat > "$BP/$SUB" <<'BASIC'
* ZZGSUB - written by gplbld/verify-solo-global.sh, leg 4.  Safe to delete.
      SUBROUTINE zzgsub(X)
      X = 'GLOBAL.OK'
      RETURN
   END
BASIC
cat > "$BP/$CALL" <<'BASIC'
* ZZGCALL - written by gplbld/verify-solo-global.sh, leg 4.  Safe to delete.
      X = ''
      CALL *zzgsub(X)
      CRT 'GCALL=':X
   END
BASIC
out="$(asuser "BASIC BP $SUB $CALL")"
if [ "$(count "$out" '0 error(s)')" -ge 2 ]; then
  leg "4a setup: both probe programs compile" "0 error(s) twice" 0 "compiled"
else
  leg "4a setup: both probe programs compile" "0 error(s) twice" 1 "$(printf '%s\n' "$out" | tail -4 | tr '\n' '|')"
fi
out="$(asglobal "COPY FROM BP.OUT TO GLOBAL.BP.OUT $SUB" SYNC.GLOBAL.CATALOG)"
if printf '%s\n' "$out" | grep -q '1 record(s) copied' \
   && printf '%s\n' "$out" | grep -qx 'SYNC GLOBAL CATALOG DONE 1 catalogued 0 removed 0 refused' \
   && [ "$(incat)" -eq 1 ]; then
  leg "4b the global session adds an object and syncs" "'1 record(s) copied', DONE 1 catalogued, *$SUB in gcat" 0 "added"
else
  leg "4b the global session adds an object and syncs" "copied, DONE 1/0/0, *$SUB in gcat" 1 "$(printf '%s\n' "$out" | tail -4 | tr '\n' '|')"
fi
out="$(asuser "RUN BP $CALL")"
if [ "$(count "$out" 'GCALL=GLOBAL.OK')" -eq 1 ]; then
  leg "4c sduser without ADMIN CALLs the global program" "GCALL=GLOBAL.OK" 0 "ran"
else
  leg "4c sduser without ADMIN CALLs the global program" "GCALL=GLOBAL.OK" 1 "$(last "$out")"
fi
out="$(asglobal "DELETE GLOBAL.BP.OUT $SUB" SYNC.GLOBAL.CATALOG)"
if printf '%s\n' "$out" | grep -qx 'SYNC GLOBAL CATALOG DONE 0 catalogued 1 removed 0 refused' && [ "$(incat)" -eq 0 ] \
   && [ ! -e "$GBP/$SUB" ]; then
  leg "4d deleted and synced, the catalogue entry is gone" "DONE 0/1/0, no *$SUB, no object" 0 "removed"
else
  leg "4d deleted and synced, the catalogue entry is gone" "DONE 0/1/0, no *$SUB, no object" 1 "$(printf '%s\n' "$out" | tail -4 | tr '\n' '|')"
fi
rm -f "$BP/$SUB" "$BP/$CALL" "$OUT/$SUB" "$OUT/$CALL"

# ---- 5. DENY.VERBS is refused to sduser even with ADMIN.
out="$(asadmin DENY.VERBS 'DENY.VERBS ADD WHO')"
if [ "$(count "$out" "$M30")" -eq 2 ] && ! printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+:'; then
  leg "5 with ADMIN, DENY.VERBS is refused" "11030 x2, no 'DENY.VERBS n:' line" 0 "refused twice"
else
  leg "5 with ADMIN, DENY.VERBS is refused" "11030 x2, no 'DENY.VERBS n:' line" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi

# ---- 6. the server denies WHO, sduser is refused it, ADMIN runs it, the server allows it again.
# TIME goes on first, so WHO is added to a list of TWO or more - the case a search by
# field (LOCATE list<1>) silently missed on Windows Solo (its leg 17c).
out="$(asglobal 'DENY.VERBS ADD TIME,WHO')"
if printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+: .*who'; then
  leg "6a a global session adds WHO to the list" "'DENY.VERBS n: ...WHO'" 0 "$(printf '%s\n' "$out" | grep -E '^deny\.verbs [0-9]+:' | tail -1)"
else
  leg "6a a global session adds WHO to the list" "'DENY.VERBS n: ...WHO'" 1 "$(last "$out")"
fi
out="$(asuser WHO)"
if [ "$(count "$out" "$NEEDS")" -eq 1 ] && ! printf '%s\n' "$out" | grep -qE '^[0-9]+ sduser$'; then
  leg "6b sduser without ADMIN is refused WHO" "one 2001, no WHO answer" 0 "refused"
else
  leg "6b sduser without ADMIN is refused WHO" "one 2001, no WHO answer" 1 "$(last "$out")"
fi
out="$(asadmin WHO)"
if [ "$(count "$out" "$NEEDS")" -eq 0 ] && printf '%s\n' "$out" | grep -qE '^[0-9]+ sduser$'; then
  leg "6c with ADMIN, WHO runs" "a WHO answer and no 2001" 0 "ran"
else
  leg "6c with ADMIN, WHO runs" "a WHO answer and no 2001" 1 "$(last "$out")"
fi
out="$(asglobal 'DENY.VERBS REMOVE WHO')"
if printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+:' && ! printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+: .*who'; then
  leg "6d the server removes WHO" "a 'DENY.VERBS n:' line without WHO" 0 "removed"
else
  leg "6d the server removes WHO" "a 'DENY.VERBS n:' line without WHO" 1 "$(last "$out")"
fi
out="$(asuser WHO)"
if [ "$(count "$out" "$NEEDS")" -eq 0 ] && printf '%s\n' "$out" | grep -qE '^[0-9]+ sduser$'; then
  leg "6e CONTROL: sduser runs WHO again" "a WHO answer and no 2001" 0 "ran"
else
  leg "6e CONTROL: sduser runs WHO again" "a WHO answer and no 2001" 1 "$(last "$out")"
fi

# ---- 6f. ADMIN can never be denied, and the two-verb list can be emptied again.
out="$(asglobal 'DENY.VERBS ADD ADMIN')"
if printf '%s\n' "$out" | grep -qx 'deny.verbs: admin is never denied - dropped' && ! printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+: .*admin'; then
  leg "6f ADMIN is never denied" "'ADMIN is never denied - dropped', ADMIN not on the list" 0 "dropped"
else
  leg "6f ADMIN is never denied" "'ADMIN is never denied - dropped', ADMIN not on the list" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi
out="$(asglobal 'DENY.VERBS REMOVE TIME')"
if printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+:' && ! printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+: .*time'; then
  leg "6g the server removes TIME" "a 'DENY.VERBS n:' line without TIME" 0 "removed"
else
  leg "6g the server removes TIME" "a 'DENY.VERBS n:' line without TIME" 1 "$(last "$out")"
fi

# ---- 7. a verb is denied by what it runs: denying SH denies ! too (Windows SOLO 22).
TAG="zzbang-ran-$$"
out="$(asglobal 'DENY.VERBS ADD SH')"
if printf '%s\n' "$out" | grep -qE '^deny\.verbs [0-9]+: .*sh' \
   && printf '%s\n' "$out" | grep -qE '^deny\.verbs also denies, as the same command: .*!'; then
  leg "7a DENY.VERBS ADD SH names ! as also denied" "SH on the list and an 'also denies' line naming !" 0 "named"
else
  leg "7a DENY.VERBS ADD SH names ! as also denied" "SH on the list and an 'also denies' line naming !" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi
out="$(asuser "! echo $TAG")"
if [ "$(count "$out" "$NEEDS")" -eq 1 ] && [ "$(count "$out" "$TAG")" -eq 0 ]; then
  leg "7b with SH denied, ! is refused without ADMIN" "one 2001 and the echo text not printed" 0 "refused"
else
  leg "7b with SH denied, ! is refused without ADMIN" "one 2001 and the echo text not printed" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi
asglobal 'DENY.VERBS REMOVE SH' >/dev/null
out="$(asuser "! echo $TAG")"
if [ "$(count "$out" "$TAG")" -eq 1 ] && [ "$(count "$out" "$NEEDS")" -eq 0 ]; then
  leg "7c CONTROL: with SH allowed, ! runs" "the echo text and no 2001" 0 "ran"
else
  leg "7c CONTROL: with SH allowed, ! runs" "the echo text and no 2001" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi

# ---- 8. the list is as the install left it.
now="$(asglobal DENY.VERBS | grep -E '^deny\.verbs [0-9]+:' | head -1)"
if [ "$now" = "$base" ]; then
  leg "8 the deny list is put back" "$base" 0 "$now"
else
  leg "8 the deny list is put back" "$base" 1 "$now"
fi

# ---- 9. SET.PASSWORD GLOBAL: refused with ADMIN, allowed to a global session, put back.
out="$(asadmin 'SET.PASSWORD GLOBAL')"
if [ "$(count "$out" 'The global password can only be changed by the SD Core server')" -eq 1 ] \
   && ! printf '%s\n' "$out" | grep -qx 'Password changed'; then
  leg "9a with ADMIN, SET.PASSWORD GLOBAL is refused" "11033, no 'Password changed'" 0 "refused"
else
  leg "9a with ADMIN, SET.PASSWORD GLOBAL is refused" "11033, no 'Password changed'" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi
TMPG="${GLOBALPW}Zz9!"
out="$(asglobal 'SET.PASSWORD GLOBAL' "$TMPG" "$TMPG")"
if [ "$(count "$out" 'Password changed')" -eq 1 ]; then
  leg "9b a global session changes the global password" "'Password changed'" 0 "changed"
  out="$(sess "$TMPG" WHERE)"
  if printf '%s\n' "$out" | grep -q 'user_accounts/sduser'; then
    leg "9c the new global password signs in" "a WHERE line naming user_accounts/sduser" 0 "signed in"
  else
    leg "9c the new global password signs in" "a WHERE line naming user_accounts/sduser" 1 "$(last "$out")"
  fi
  out="$(sess "$TMPG" 'SET.PASSWORD GLOBAL' "$GLOBALPW" "$GLOBALPW")"
  if [ "$(count "$out" 'Password changed')" -eq 1 ]; then
    leg "9d the global password is put back" "'Password changed'" 0 "put back"
  else
    leg "9d the global password is put back" "'Password changed'" 1 "RECOVER BY HAND: the global password is now your usual one followed by Zz9! - $(last "$out")"
  fi
else
  leg "9b a global session changes the global password" "'Password changed'" 1 "$(printf '%s\n' "$out" | tail -3 | tr '\n' '|')"
fi

echo
echo "verify-solo-global: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
