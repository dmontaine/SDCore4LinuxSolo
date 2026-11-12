#!/bin/bash
# test-install-linger.sh - is "loginctl enable-linger" ON by default in installsdsolo.sh, with --no-linger and the control file's
# enable-linger=no to turn it off?  (The owner, 9 Nov 2026: "linux and windows solo both need to be set up so that SD is accessible
# remotely even if the user is not logged in at the console", then "Yes, on by default".)  No install, no sudo, no sd.
# Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-linger.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh keeps linger_decide between "# BEGIN linger" and "# END linger".  This cuts the block out and runs it
# under the installer's own `set -euo pipefail` and IFS, with `say` a function, `refuse` exiting 2, and `ask_yn` a stub that answers
# from a variable and counts the times it was asked (the real one reads /dev/tty).  Then the places the decision travels - the
# default, the two options, the upgrade refusal, the one call, the service install's --enable-linger, the summary line - are read as
# text.  ***IT DOES NOT RUN THE INSTALLER*** and cannot say that systemd keeps SD running after a sign-out or a reboot.
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.
set -euo pipefail
IFS=$'\n\t'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="$ROOT/installsdsolo.sh"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

# run_case BLOCK CLI CF NO_SERVICE INTERACTIVE ANSWER -> prints "<enable_linger> <times asked> <exit>"
run_case() {
  local blk="$1"
  bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    say() { :; }
    refuse() { exit 2; }
    asked=0
    ask_yn() { asked=$((asked+1)); [ "$ANSWER" = y ]; }
    linger_cli="$1"; cf_linger="$2"; no_service="$3"; interactive="$4"; ANSWER="$5"; enable_linger=1
    source "$6"
    linger_decide
    echo "$enable_linger $asked"
  ' _ "$2" "$3" "$4" "$5" "$6" "$blk" 2>/dev/null && return 0
  echo "x x refused"
}

check() {   # check INSTALLER - every row, against this file
  local inst="$1" blk out
  blk="$(mktemp)"
  awk '/^# BEGIN linger$/,/^# END linger$/' "$inst" > "$blk"
  if ! grep -q '^linger_decide()' "$blk"; then
    row "B0 the block '# BEGIN linger' .. '# END linger' holds linger_decide" 1 "not found"
    rm -f "$blk"; return
  fi
  row "B0 the block '# BEGIN linger' .. '# END linger' holds linger_decide" 0

  out="$(run_case "$blk" "" "" 0 0 n)";      row "L1 nothing chosen, no terminal (an unattended install): linger ON, nothing asked" "$([ "$out" = "1 0" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" "" 0 1 y)";      row "L2 nothing chosen, a terminal, the answer yes: linger ON, asked once" "$([ "$out" = "1 1" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" "" 0 1 n)";      row "L3 nothing chosen, a terminal, the answer no: linger OFF, asked once" "$([ "$out" = "0 1" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" yes 0 1 n)";     row "L4 the control file's enable-linger=yes: ON, not asked" "$([ "$out" = "1 0" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" no 0 1 y)";      row "L5 the control file's enable-linger=no: OFF, not asked" "$([ "$out" = "0 0" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" no yes 0 1 y)";     row "L6 --no-linger wins over the file's yes: OFF, not asked" "$([ "$out" = "0 0" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" yes no 0 1 n)";     row "L7 --enable-linger wins over the file's no: ON, not asked" "$([ "$out" = "1 0" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" maybe 0 1 y)";   row "L8 the file's enable-linger=maybe is refused" "$([ "$out" = "x x refused" ] && echo 0 || echo 1)" "got $out"
  out="$(run_case "$blk" "" "" 1 1 n)";      row "L9 --no-service on a terminal: not asked (no service to keep)" "$([ "$out" = "1 0" ] && echo 0 || echo 1)" "got $out"
  rm -f "$blk"

  row "T1 the default is on: enable_linger=1 where the options are set" \
    "$(grep -qE '^ssh_key=""; enable_linger=1; ' "$inst" && echo 0 || echo 1)"
  row "T2 --enable-linger and --no-linger are options and set linger_cli yes / no" \
    "$(grep -qE '^ +--enable-linger\) +linger_cli=yes; shift ;;' "$inst" && grep -qE '^ +--no-linger\) +linger_cli=no; shift ;;' "$inst" && echo 0 || echo 1)"
  row "T3 an upgrade refuses either option (linger_cli in its emptiness test, both named in the message)" \
    "$(grep -q 'reload_ans\$linger_cli\$start_choice" \]' "$inst" && grep -q -- '--ssh-key, --enable-linger, --no-linger or --start option' "$inst" && echo 0 || echo 1)"   # 12 Nov 26: --start joined the list (S.221)
  row "T4 linger_decide is called exactly once, after its definition and ask_yn's" \
    "$([ "$(grep -c '^linger_decide$' "$inst")" = 1 ] && [ "$(grep -n '^linger_decide$' "$inst" | cut -d: -f1)" -gt "$(grep -n '^ask_yn()' "$inst" | cut -d: -f1)" ] && echo 0 || echo 1)"
  row "T5 the service install passes --enable-linger when it is on, and the summary says on or off" \
    "$(grep -q '\[ "\$enable_linger" -eq 1 \] && svc_args+=(--enable-linger)' "$inst" && grep -q 'linger on: SD keeps running when nobody is signed in' "$inst" && grep -q 'linger off: SD stops when you sign out' "$inst" && echo 0 || echo 1)"
}

if [ "${1:-}" = "--selftest" ]; then
  bad=0
  tmp="$(mktemp)"
  mutate() {   # mutate "name" sed-expression
    sed "$2" "$INSTALLER" > "$tmp"
    local before=$failed
    check "$tmp" > /dev/null
    if [ "$failed" -gt "$before" ]; then echo "  [PASS] mutant: $1 | caught"; else echo "  [FAIL] mutant: $1 | NOT CAUGHT"; bad=$((bad+1)); fi
    failed=$before
  }
  mutate "the default back to off"            's/^ssh_key=""; enable_linger=1; /ssh_key=""; enable_linger=0; /'
  mutate "the file's no ignored"              's/^    no)  enable_linger=0; return 0 ;;$/    no)  enable_linger=1; return 0 ;;/'
  mutate "the question no longer turns it off" 's/ask_yn "Keep SD running when you are signed out?" y || enable_linger=0/ask_yn "Keep SD running when you are signed out?" y || true/'
  rm -f "$tmp"
  echo "test-install-linger --selftest: $([ "$bad" = 0 ] && echo "PASSED, 3 of 3 mutants caught" || echo "FAILED, $bad not caught")"
  [ "$bad" = 0 ] && exit 0 || exit 1
fi

echo "test-install-linger inputs: installer $INSTALLER"
[ -f "$INSTALLER" ] || { echo "CANNOT RUN: $INSTALLER is not there"; exit 2; }
check "$INSTALLER"
echo "test-install-linger: $passed passed, $failed failed"
[ "$failed" = 0 ]
