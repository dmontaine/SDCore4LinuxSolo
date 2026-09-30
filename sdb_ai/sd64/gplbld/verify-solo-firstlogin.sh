#!/bin/bash
# verify-solo-firstlogin.sh - the account password chosen at the console on first login
# (LSOLO 14; Windows Solo SOLO 18, owner 27 Sep 2026).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-firstlogin.sh
#
# No sudo.  Run as an ordinary user after "make" in sdb_ai/sd64.  It stages its own
# MANAGED scratch tree with NO account password (test passwords it writes itself,
# 0600, deleted when it ends) and drives sd over a pseudo-terminal (ptyrun.py) the way
# a person at the keyboard does.  About two minutes.  Removes its scratch directory.
#
# WHAT IT PROVES: a piped session and a session over "ssh" (SSH_CONNECTION set) are
# NOT offered the first-password prompt and only the global password opens them; at
# the console a weak password, the global password and a mismatch are each refused,
# a good one is accepted; afterwards the new password, the global password and a
# one-shot command all work, the master's salt is shared, and the account's record
# exists.  THE NULL CASES: the tree has no $cred/sduser before (else the prompt could
# never have been offered) and every pty step must have matched.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sd64="$(dirname "$here")"
[ -x "$sd64/bin/sd" ] || refuse "$sd64/bin/sd is not built - run make first"
command -v python3 >/dev/null || refuse "python3 is required"
systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is running for this user; its daemon would collide with this test's"

W="$(mktemp -d)"; chmod 700 "$W"
H="$W/tree"
cleanup() { [ -x "$H/bin/sd" ] && "$H/bin/sd" -stop >/dev/null 2>&1; rm -rf "$W"; }
trap cleanup EXIT
umask 077

ADM='Admin-Fl-Test-4712!'; GLB='Glob-Fl-Test-4713!'
NEWPW='First-Fl-Test-4714!'; WEAK='weak'
printf '%s\n' "$ADM" > "$W/b.pw"; printf '%s\n' "$GLB" > "$W/c.pw"

echo "verify-solo-firstlogin inputs:"
echo "  source tree : $sd64  (bin/sd $(stat -c '%y' "$sd64/bin/sd" | cut -c1-19))"
echo "  scratch     : $W"
echo "  running as  : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
leg() { legs=$((legs+1)); if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
clean() { strip | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core for Linux Solo, the'; }
piped() { local pw="$1"; shift; printf '%s\n' "$pw" "$@" OFF | timeout 60 "$H/bin/sd" 2>&1 | clean; }
PRENV=()
PR() { python3 "$here/ptyrun.py" --timeout 25 ${PRENV[@]+"${PRENV[@]}"} "$H/bin/sd" "$@"; }

echo
echo "staging a managed tree WITH NO account password ..."
bash "$sd64/gplbld/solo-stage.sh" --admin-password-file "$W/b.pw" --global-password-file "$W/c.pw" "$H" > "$W/stage.log" 2>&1 \
  || { tail -15 "$W/stage.log"; refuse "the stage failed"; }
[ -f "$H/\$cred/\$global" ] && [ ! -e "$H/\$cred/sduser" ] || refuse "the staged tree is not 'global record only' - the test would measure nothing"
echo "  \$cred holds: $(ls "$H/\$cred" | tr '\n' ' ')"

# ---- 1. no first-password prompt without a console: a piped session says so and takes only the global password.
o="$(piped "$NEWPW" WHO)"
n_msg="$(printf '%s\n' "$o" | grep -c -x "This account has no password yet. Set it at this computer's keyboard first; until then only the global password is accepted.")"
if [ "$n_msg" -eq 1 ] && ! printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && [ ! -e "$H/\$cred/sduser" ]; then
  leg "1 a piped session is not offered the prompt" "11026 shown, the password refused, still no \$cred/sduser" 0 "refused"
else
  leg "1 a piped session is not offered the prompt" "11026 once, no WHO answer, no \$cred/sduser" 1 "msg=$n_msg; $(printf '%s\n' "$o" | tail -3 | tr '\n' '|')"
fi

# ---- 2. the global password opens the account, and setting nothing.
o="$(piped "$GLB" WHO)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && [ ! -e "$H/\$cred/sduser" ]; then
  leg "2 the global password still opens it, and sets no password" "a WHO answer, still no \$cred/sduser" 0 "global session"
else
  leg "2 the global password still opens it" "a WHO answer, no \$cred/sduser" 1 "$(printf '%s\n' "$o" | tail -3 | tr '\n' '|')"
fi

# ---- 3. over ssh (SSH_CONNECTION set) at a terminal: no prompt to choose one either.
PRENV=(--env SSH_CONNECTION="192.0.2.1 50000 192.0.2.2 22")
t="$(PR expect:'no password yet\. Set it at this' expect:'Password:' send:"$NEWPW" expect:'Wrong password' 2>&1)"
rc3=$?
PRENV=()
if [ "$rc3" -eq 0 ] && ! printf '%s\n' "$t" | grep -q 'Choose one now' && [ ! -e "$H/\$cred/sduser" ]; then
  leg "3 an ssh session is not offered the prompt" "11026, the ordinary Password: prompt, the new password refused, no \$cred/sduser" 0 "refused"
else
  leg "3 an ssh session is not offered the prompt" "11026 then Password: then Wrong password" 1 "rc=$rc3; $(printf '%s\n' "$t" | grep -E 'ptyrun:|Choose|Wrong' | tr '\n' '|')"
fi

# ---- 4. at the console: weak, global-equal and mismatched passwords are refused, a good one accepted.
# Three tries, and each of the three refusals in turn: weak, equal to the global password, mismatch.
tA="$(PR expect:'Choose one now' \
        expect:'New password:' send:"$WEAK" \
        expect:'That was attempt 1 of 3' \
        expect:'New password:' send:"$GLB" \
        expect:'different from the global password' \
        expect:'New password:' send:"$NEWPW" \
        expect:'Confirm the new password:' send:"Other-Fl-Test-9999!" \
        expect:'do not match' \
        expect:'No password was set, and one is required' 2>&1)"
rcA=$?
if [ "$rcA" -eq 0 ] && [ ! -e "$H/\$cred/sduser" ]; then
  leg "4a weak, equal-to-global and mismatched passwords are refused; three tries end it" "the three refusals, 'No password was set', still no \$cred/sduser" 0 "refused"
else
  leg "4a the three refusals" "weak, global-equal, mismatch, then 'No password was set'" 1 "rc=$rcA; $(printf '%s\n' "$tA" | grep -E 'ptyrun:' | tr '\n' '|')"
  printf '%s\n' "$tA" | tail -25
fi
t="$(PR expect:'Choose one now' \
        expect:'New password:' send:"$NEWPW" \
        expect:'Confirm the new password:' send:"$NEWPW" \
        expect:'Password set for account sduser' \
        send:'WHO' expect:'[0-9]+ sduser' send:'OFF' 2>&1)"
rc4=$?
if [ "$rc4" -eq 0 ] && [ -f "$H/\$cred/sduser" ]; then
  leg "4 the console chooses a password" "a good one is set and the session then runs" 0 "set"
else
  leg "4 the console chooses a password" "'Password set for account sduser' then a WHO answer" 1 "rc=$rc4; $(printf '%s\n' "$t" | grep -E 'ptyrun:' | tr '\n' '|')"
  printf '%s\n' "$t" | tail -25
fi
t="$t$tA"
if printf '%s\n' "$t" | grep -qF -e "$NEWPW" -e "$GLB" -e "$WEAK" -e 'Other-Fl-Test'; then
  leg "4b no password appears in the transcript" "none of the five typed passwords is echoed" 1 "one is on the screen"
else
  leg "4b no password appears in the transcript" "none of the typed passwords is echoed" 0 "hidden"
fi

# ---- 5. afterwards: the new password, the global password and a one-shot all work; the salt is shared.
o1="$(piped "$NEWPW" WHO)"; o2="$(piped "$GLB" WHO)"
o3="$(echo "" | timeout 60 "$H/bin/sd" WHO 2>&1 | clean)"
o4="$(piped "$WEAK" WHO)"
s_acc="$(sed -n 3p "$H/\$cred/sduser")"; s_glb="$(sed -n 3p "$H/\$cred/\$global")"
if printf '%s\n' "$o1" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$o2" | grep -qE '^[0-9]+ sduser$' \
   && printf '%s\n' "$o3" | grep -qE '^[0-9]+ sduser$' && ! printf '%s\n' "$o4" | grep -qE '^[0-9]+ sduser$' \
   && [ -n "$s_acc" ] && [ "$s_acc" = "$s_glb" ]; then
  leg "5 afterwards" "the new password, the global password and a one-shot sign in; a wrong one does not; one salt" 0 "all as expected"
else
  leg "5 afterwards" "new pw, global pw, one-shot sign in; wrong does not; one salt" 1 "new=$(last=$(printf '%s\n' "$o1" | tail -1); echo "$last") global=$(printf '%s\n' "$o2" | tail -1) oneshot=$(printf '%s\n' "$o3" | tail -1) salt-same=$([ "$s_acc" = "$s_glb" ] && echo yes || echo NO)"
fi

# ---- 6. the prompt is one-time: a console session now asks for the password as usual.
t="$(PR expect:'Password:' send:"$NEWPW" send:'WHO' expect:'[0-9]+ sduser' send:'OFF' 2>&1)"
if [ "$?" -eq 0 ] && ! printf '%s\n' "$t" | grep -q 'Choose one now'; then
  leg "6 the prompt is one-time" "an ordinary Password: prompt, no 'Choose one now'" 0 "ordinary"
else
  leg "6 the prompt is one-time" "an ordinary Password: prompt" 1 "$(printf '%s\n' "$t" | grep -E 'ptyrun:|Choose' | tr '\n' '|')"
fi

# ---- 7. the audit trail names it (and not the password).
if grep -q 'LOGIN FIRST PASSWORD SET account=sduser' "$H/audit" && ! grep -qF -e "$NEWPW" -e "$GLB" "$H/audit"; then
  leg "7 the first password is audited, the password is not" "'LOGIN FIRST PASSWORD SET account=sduser' present; no password in the trail" 0 "audited"
else
  leg "7 the first password is audited" "audit line present, no password in it" 1 "$(grep -c 'FIRST PASSWORD' "$H/audit") lines"
fi

echo
echo "verify-solo-firstlogin: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
