#!/bin/bash
# verify-solo-interactive.sh - the installer's own questions, answered at a (pseudo-)terminal.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-interactive.sh
#
# No sudo.  Run as an ordinary user with a clean git tree (the installer builds the
# COMMITTED head of this repository, as verify-solo-install.sh does).  It drives
# installsolo.sh through ptyrun.py exactly as a person at a keyboard would: the mode
# question, a weak account password (refused, asked again), a confirmation that does not
# match (asked again), the administrator password, the API question, ssh, linger and
# "Continue?".  First a run answered "n" at "Continue?", which must change nothing; then
# a run answered "y", which does a real install (about three minutes), and is checked by a
# session with the passwords the pty typed.  Linger is answered n: it is a persistent
# account setting and this is a test.  Removes what it installed and its scratch directory.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$here/../../.." && pwd)"
INSTALL="$REPO/installsolo.sh"
[ -f "$INSTALL" ] || refuse "$INSTALL is missing"
command -v python3 >/dev/null || refuse "python3 is required"
git -C "$REPO" diff --quiet && git -C "$REPO" diff --cached --quiet || refuse "the working tree has uncommitted changes; the installer would install HEAD, not them"
systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is running for this user"
ss -ltn 2>/dev/null | grep -q ':14245 ' && refuse "port 14245 is in use"
[ ! -e "$HOME/.sdsolotmp" ] || refuse "$HOME/.sdsolotmp exists; remove it"

W="$(mktemp -d)"; chmod 700 "$W"
H="$W/inst"
cleanup() {
  [ -f "$H/tools/deletesolo.sh" ] && bash "$H/tools/deletesolo.sh" --delete-data --yes >/dev/null 2>&1
  rm -rf "$W"
}
trap cleanup EXIT
umask 077

ACC='Acct-Ia-Test-4711!'; ADM='Admin-Ia-Test-4712!'; WEAK='weak'; OTHER='Other-Ia-Test-9999!'
export SDSOLO_REPO_URL="$REPO"

echo "verify-solo-interactive inputs:"
echo "  installer  : $INSTALL"
echo "  source     : $REPO (HEAD $(git -C "$REPO" rev-parse --short HEAD)) via SDSOLO_REPO_URL"
echo "  scratch    : $W"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
leg() { legs=$((legs+1)); if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
# LSOLO 23: there is no --api-port; the private port goes through the installer's announced test
# hook, which ptyrun.py hands on in its environment.
export SDSOLO_TEST_API_PORT=14245
IA() { local t="$1"; shift; python3 "$here/ptyrun.py" --timeout "$t" --arg --home --arg "$H" --arg --skip-packages "$INSTALL" "$@"; }

# The answers, in the installer's order.  Each send waits for its prompt.
answers() {   # answers CONTINUE-ANSWER
  printf '%s\n' expect:'managed by an SD Core server\? \[y/N\]' send:n
  printf '%s\n' expect:'Choose the account password: ' send:"$WEAK"
  printf '%s\n' expect:'The password must be'
  printf '%s\n' expect:'Choose the account password: ' send:"$ACC"
  printf '%s\n' expect:'Confirm the account password: ' send:"$OTHER"
  printf '%s\n' expect:'The two did not match'
  printf '%s\n' expect:'Choose the account password: ' send:"$ACC"
  printf '%s\n' expect:'Confirm the account password: ' send:"$ACC"
  printf '%s\n' expect:'Choose the administrator password: ' send:"$ADM"
  printf '%s\n' expect:'Confirm the administrator password: ' send:"$ADM"
  printf '%s\n' expect:'API listener \[off/local/open\] \(default off\): ' send:local
  printf '%s\n' expect:'Set up ssh straight into sd .*\[y/N\]' send:n
  printf '%s\n' expect:'Enable it now\? \[Y/n\]' send:n
  printf '%s\n' expect:'Ready to install:'
  printf '%s\n' expect:'Continue\? \[Y/n\]' send:"$1"
}

# ---- 1. answered "n" at "Continue?": nothing is created, and it says so.
mapfile -t steps < <(answers n; printf '%s\n' expect:'cancelled by you; nothing was changed')
t="$(IA 60 "${steps[@]}" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && [ ! -e "$H" ] && [ ! -e "$HOME/.sdsolotmp" ]; then
  leg "1 answering n at Continue? changes nothing" "every question answered at the terminal, 'cancelled by you', no tree, no download" 0 "cancelled"
else
  leg "1 answering n at Continue? changes nothing" "'cancelled by you; nothing was changed', no tree" 1 "rc=$rc; $(printf '%s\n' "$t" | grep -E 'ptyrun:' | tr '\n' '|')"
  printf '%s\n' "$t" | tail -20
fi
if printf '%s\n' "$t" | grep -qF -e "$ACC" -e "$ADM" -e "$OTHER" -e "$WEAK"; then
  leg "1b no typed password is echoed" "none on the screen" 1 "one is"
else
  leg "1b no typed password is echoed" "none of the four typed passwords on the screen (stars only)" 0 "stars"
fi

# ---- 2. answered "y": a real install.
mapfile -t steps < <(answers y; printf '%s\n' expect:'SOLO INSTALL COMPLETE')
t="$(IA 900 "${steps[@]}" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && [ -f "$H/.sdcoresolo" ]; then
  leg "2 answering y installs" "the questions answered, 'SOLO INSTALL COMPLETE'" 0 "installed"
else
  leg "2 answering y installs" "'SOLO INSTALL COMPLETE'" 1 "rc=$rc; $(printf '%s\n' "$t" | grep -E 'ptyrun:|REFUSED|FAILED' | tr '\n' '|')"
  printf '%s\n' "$t" | tail -25
  echo; echo "verify-solo-interactive: $pass passed, $fail failed, of $legs legs"; exit 1
fi

# ---- 3. what the person typed is what was installed.
chk() { printf '%s\n' "$1" WHO OFF | timeout 60 "$H/bin/sd" 2>&1 | strip; }
o1="$(chk "$ACC")"; o2="$(printf '%s\n' "$ACC" ADMIN "$ADM" LISTU OFF | timeout 60 "$H/bin/sd" 2>&1 | strip)"; o3="$(chk "$OTHER")"
if printf '%s\n' "$o1" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$o2" | grep -qx 'Administrator commands unlocked for this session' \
   && ! printf '%s\n' "$o3" | grep -qE '^[0-9]+ sduser$'; then
  leg "3 the typed passwords are the installed ones" "the account and administrator passwords work; the mismatched one does not" 0 "as typed"
else
  leg "3 the typed passwords are the installed ones" "account pw and admin pw work; the mismatched one does not" 1 "$(printf '%s\n' "$o1" | tail -1) / $(printf '%s\n' "$o2" | tail -1)"
fi

# ---- 4. the API answer took: a local listener on the port given.
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:14245 '; then
  leg "4 the API answer 'local' took" "listening on 127.0.0.1:14245" 0 "listening"
else
  leg "4 the API answer 'local' took" "listening on 127.0.0.1:14245" 1 "$(ss -ltn 2>/dev/null | grep ':14245' | head -1)"
fi

echo
echo "verify-solo-interactive: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
