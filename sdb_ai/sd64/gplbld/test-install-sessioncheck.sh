#!/bin/bash
# test-install-sessioncheck.sh - installsdsolo.sh's last check, "a session as sduser works" (21 Nov 2026, S.289, found on a VM).
# The check types WHO and wants its answer ("<n> sduser").  An administrator who names who in the control file's deny-verbs gave a COMPLETE install
# that ended "FAILED at: a session as sduser did not work", because WHO's answer was the refusal.  Where the check types a verb (a new install) it now
# also passes the refusal line of the deny list - the WHOLE line, which only a session that signed in and reached the command prompt prints - and
# says so; the kept-password branch types no verb of the list and keeps its one sentence.  No install, no sudo, no sd.  Exit 0 every row held,
# 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-sessioncheck.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh keeps session_check_ok between "# SESSION-CHECK-BEGIN" and "# SESSION-CHECK-END".  This cuts it out and runs it under the
# installer's own `set -euo pipefail` and IFS on what a session printed.  The inputs are what sd-solo printed on a real Solo on 21 Nov 2026 (the banner,
# WHO's answer, the refusal of a denied verb, and the failed sign-in).  The call sites in the self-check are read as TEXT.  It cannot say that a
# future sd-solo prints the same lines: that is the real-install row, run on three installs on 21 Nov 2026 (S.289).
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.
set -euo pipefail
IFS=$'\n\t'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
MSG2001="$ROOT/sdb_ai/sd64/sdsys/messages/2001"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, sed expression applied to the installer's whole text
    local f="$T/$1.sh"
    sed -e "$2" "$ROOT/installsdsolo.sh" > "$f"
    if cmp -s "$ROOT/installsdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if INSTALLER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  mutant denied-always-ok    's/\[ "\$denied_ok" -eq 1 \] \&\& printf/true \&\& printf/'
  mutant no-denied-path      's/echo denied; return 0/return 1/'
  mutant substring-line      "s/grep -qxF 'Command requires administrator privileges'/grep -qF 'Command requires administrator privileges'/"
  mutant kept-branch-ok      's/^denied_ok=0$/denied_ok=1/'
  mutant new-install-strict  's/^  denied_ok=1$/  :/'
  mutant wrong-wording       's/Command requires administrator privileges/Command requires administrators/'
  mutant bare-grep-back      's/^verdict="\$(session_check_ok "\$chk" "\$want" "\$denied_ok")" ||/printf "%s\\n" "$chk" | grep -qE "$want" ||/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

[ -r "$INSTALLER" ] || { echo "test-install-sessioncheck: CANNOT RUN - no installer at $INSTALLER"; exit 2; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# SESSION-CHECK-BEGIN$/,/^# SESSION-CHECK-END$/' "$INSTALLER" > "$T/block.sh"
echo "installer : $INSTALLER"
grep -q '^session_check_ok()' "$T/block.sh" || { echo "test-install-sessioncheck: CANNOT RUN - no session_check_ok between # SESSION-CHECK-BEGIN and # SESSION-CHECK-END"; exit 2; }

WANT_NEW='^[0-9]+ sduser$'
WANT_KEPT='^0-install-check is not a job name: '
REFUSAL='Command requires administrator privileges'
BANNER=$'SD Core Solo for Linux, version LS2.0-0\n************'
OK_WHO="$BANNER"$'\n:WHO:WHO\n4 sduser\n:OFF:OFF'
DENIED="$BANNER"$'\n:WHO:WHO\n'"$REFUSAL"$'\n:OFF:OFF'
BAD_LOGIN=$'*************\nWrong password\nConnection terminated'   # measured on a real Solo, 21 Nov 2026: a wrong password, then WHO typed

# run_case CHK WANT DENIED_OK -> "V=<what the function printed> RC=<its status>"
run_case() {
  local v rc=0
  v="$(CHK="$1" WANT="$2" DOK="$3" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    . "'"$T"'/block.sh"
    session_check_ok "$CHK" "$WANT" "$DOK"
  ' 2>&1)" || rc=$?
  echo "V=${v:-none} RC=$rc"
}
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

out="$(run_case "$OK_WHO" "$WANT_NEW" 1)"
row "S1 WHO ran and answered '<n> sduser' (denied_ok on): passes as ran" "$(has "$out" "V=ran RC=0" && echo 0 || echo 1)" "$out"
out="$(run_case "$OK_WHO" "$WANT_NEW" 0)"
row "S1b the same with denied_ok off: still ran - the strong proof does not depend on the flag" "$(has "$out" "V=ran RC=0" && echo 0 || echo 1)" "$out"
out="$(run_case "$DENIED" "$WANT_NEW" 1)"
row "S2 WHO is on the deny list, so the session printed the refusal line and nothing else of WHO: passes as denied" "$(has "$out" "V=denied RC=0" && echo 0 || echo 1)" "$out"
out="$(run_case "$DENIED" "$WANT_NEW" 0)"
row "S3 the kept-password branch (denied_ok off) given the refusal: FAILS - it types no verb of the list, so a refusal there is a real fault" "$(has "$out" "RC=1" && ! has "$out" "V=denied" && echo 0 || echo 1)" "$out"
out="$(run_case "$BAD_LOGIN" "$WANT_NEW" 1)"
row "S4 a failed sign-in (the wording measured on a real Solo, 21 Nov 2026: 'Wrong password', 'Connection terminated'): FAILS" "$(has "$out" "RC=1" && echo 0 || echo 1)" "$out"
out="$(run_case "" "$WANT_NEW" 1)"
row "S5 NULL CASE: the session printed nothing: FAILS" "$(has "$out" "RC=1" && echo 0 || echo 1)" "$out"
out="$(run_case "x $REFUSAL y" "$WANT_NEW" 1)"
row "S6 a longer line that only CONTAINS the refusal does not count" "$(has "$out" "RC=1" && echo 0 || echo 1)" "$out"
out="$(run_case "$REFUSAL." "$WANT_NEW" 1)"
row "S6b the refusal with a full stop is not the line SD prints: FAILS" "$(has "$out" "RC=1" && echo 0 || echo 1)" "$out"
out="$(run_case $'Unknown command' "$WANT_NEW" 1)"
row "S7 a different refusal is not the deny list's: FAILS" "$(has "$out" "RC=1" && echo 0 || echo 1)" "$out"
out="$(run_case $'0-install-check is not a job name: a job name starts with a letter' "$WANT_KEPT" 0)"
row "S8 the kept-password branch's own sentence passes as ran" "$(has "$out" "V=ran RC=0" && echo 0 || echo 1)" "$out"
out="$(run_case "$OK_WHO"$'\n'"$REFUSAL" "$WANT_NEW" 1)"
row "S9 both lines present: ran takes precedence over denied" "$(has "$out" "V=ran RC=0" && echo 0 || echo 1)" "$out"

# ---- the call sites in the self-check, read as text ------------------------------------------------------------------
sc="$(awk '/^say "Checking the install\."$/,/^rm -f "\$HOME_DIR\/\\\$internal"$/' "$INSTALLER")"
msg1="$(head -1 "$MSG2001" 2>/dev/null || true)"
row "T1 the installer's refusal wording is message 2001, the one cproc prints for a denied verb ('$msg1')" \
  "$([ -n "$msg1" ] && [ "$msg1" = "$REFUSAL" ] && grep -qF "grep -qxF '$msg1'" "$T/block.sh" && echo 0 || echo 1)" "message 2001: [$msg1]"
n_off="$(printf '%s\n' "$sc" | grep -c '^denied_ok=0$' || true)"
n_on="$(printf '%s\n' "$sc" | grep -c '^  denied_ok=1$' || true)"
l_elif="$(printf '%s\n' "$sc" | grep -n '^elif \[ "\$first_login" -eq 1 \]; then$' | head -1 | cut -d: -f1)"
l_on1="$(printf '%s\n' "$sc" | grep -n '^  denied_ok=1$' | head -1 | cut -d: -f1)"
row "T2 denied_ok is 0 from the start, and set to 1 exactly twice, both AFTER the kept-password branch (the two branches that type WHO)" \
  "$([ "$n_off" = 1 ] && [ "$n_on" = 2 ] && [ -n "$l_elif" ] && [ -n "$l_on1" ] && [ "$l_on1" -gt "$l_elif" ] && echo 0 || echo 1)" "off=$n_off on=$n_on elif@$l_elif first-on@$l_on1"
row "T3 the verdict comes from session_check_ok and a failure still says 'a session as sduser did not work'; the bare grep of the old check is gone" \
  "$(printf '%s\n' "$sc" | grep -qF 'verdict="$(session_check_ok "$chk" "$want" "$denied_ok")" ||' && printf '%s\n' "$sc" | grep -qF 'fail "a session as sduser did not work"' && ! printf '%s\n' "$sc" | grep -qF 'grep -qE "$want" ||' && echo 0 || echo 1)"
row "T4 a denied verdict is SAID: the line names WHO as refused and the sign-in as what the check proves" \
  "$(printf '%s\n' "$sc" | grep -qF 'if [ "$verdict" = denied ]; then' && printf '%s\n' "$sc" | grep -qF 'WHO is on the list of denied verbs you gave, so it was refused' && echo 0 || echo 1)"
l_def="$(grep -n '^session_check_ok()' "$INSTALLER" | head -1 | cut -d: -f1)"
l_use="$(grep -n 'verdict="\$(session_check_ok' "$INSTALLER" | head -1 | cut -d: -f1)"
row "T5 session_check_ok is defined before the self-check calls it" "$([ -n "$l_def" ] && [ -n "$l_use" ] && [ "$l_def" -lt "$l_use" ] && echo 0 || echo 1)" "def@$l_def use@$l_use"

echo
echo "test-install-sessioncheck: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
