#!/bin/bash
#
# test-install-start.sh - where a session starts, chosen at install: installsdsolo.sh's START-ASK, START-KEEP and START-SET blocks (12 Nov 2026, S.221, the
# Core-Solo parity audit's finding 8; SD Core's test of the same name holds its START-ASK / START-SET / START-SAVE blocks; owner, 3 Nov 2026: "Can that be a
# question asked during the install?", then "the home/prompt question", and "for existing users where all installs go to the prompt by default ... that will be
# retained on upgrade").
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-start.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-start.sh --selftest
#
# FREE CHECK: no sudo (Solo's installer uses none here), no install, no running sd.  Everything happens in a scratch directory.  Exit 0 every row passed, 1 a row
# failed, 2 it could not run (a block or the installer's set line missing).
#
# WHAT IT RUNS.  Each block cut out between its markers and evaluated under the installer's own "set" line (and IFS=$'\n\t', the stricter of the two, as the other
# installer tests here).  The question reads /dev/tty; here the block's "< /dev/tty" is replaced by a scratch answer file (that one substitution, nothing else).
# sd-solo is a stub that plays "-internal set.start.default WORD": it writes <home>/start.default only when the internal marker is there, as LOGIN admits only then.
#
#   A1  no answer given, no terminal: the home screen (menu), nothing asked;  A2  --yes: menu, nothing asked
#   A3  a terminal, Enter: menu;  A4  p: terminal;  A5  "prompt": terminal;  A6  "x": menu (only p or prompt count);  A7  --start terminal given: not asked, kept
#   K1  an upgrade of a tree with no gpl.bp/tool_home and no start.default: start.default says terminal, and the line says so
#   K2  a tree that has gpl.bp/tool_home: nothing written;  K3  a tree with start.default (menu): left as it is
#   S1  terminal: set.start.default terminal is run through the internal door (a marker, then none), the file says terminal, the line says the prompt
#   S2  the verb writes nothing: a WARNING with the command, the block ends 0;  S3  menu: the verb is not run, the line says the home screen
#   S4  start_choice empty (an upgrade): nothing run, nothing said;  S5  the door refuses and consumes no marker: the block takes it away itself
#   P   START-ASK is in the fresh-install branch after the control file and before the passwords; START-KEEP is before the stage's --upgrade;
#       START-SET follows MANUALS-PDF and precedes the stop of the stage's daemon; no block has an exit; --start is refused on an --upgrade
#
# NOT MEASURED HERE: the real set.start.default and the internal door (the host install from a package), and a real upgrade of an LS1.1-3 tree.

HERE="$(cd "$(dirname "$0")" && pwd)"
THIS="$HERE/$(basename "$0")"
INST="${INSTALLER:-$(cd "$HERE/../../.." && pwd)/installsdsolo.sh}"

if [ "${1:-}" = "--selftest" ]; then
  REAL="$(cd "$HERE/../../.." && pwd)/installsdsolo.sh"
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  caught=0; missed=0; total=0
  mutant() {   # name, sed expression
    local name="$1" expr="$2" f="$T/$1.sh" rc
    total=$((total+1))
    sed -e "$expr" "$REAL" > "$f"
    if cmp -s "$REAL" "$f"; then echo "  [MISSED] $name: the mutation changed nothing"; missed=$((missed+1)); return; fi
    INSTALLER="$f" bash "$THIS" > "$T/$name.out" 2>&1; rc=$?
    if [ "$rc" -ne 0 ]; then echo "  [caught] $name (exit $rc)"; caught=$((caught+1))
    else echo "  [MISSED] $name: the check still passed"; missed=$((missed+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  INSTALLER="$REAL" bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  A='/^# START-ASK-BEGIN/,/^# START-ASK-END/'
  K='/^  # START-KEEP-BEGIN/,/^  # START-KEEP-END/'
  S='/^# START-SET-BEGIN/,/^# START-SET-END/'
  mutant default-prompt      "$A s/^  start_choice=menu\$/  start_choice=terminal/"
  mutant asks-with-yes       "$A s/ \&\& \[ \"\$assume_yes\" -eq 0 \]//"
  mutant any-answer-prompt   "$A s/\[pP\]|\[pP\]\[rR\]\[oO\]\[mM\]\[pP\]\[tT\] )/*)/"
  mutant overrides-option    "$A s/^if \[ -z \"\$start_choice\" \]; then\$/if true; then/"
  mutant keep-always         "$K s/\[ ! -e \"\$HOME_DIR\/gpl.bp\/tool_home\" \]/true/"
  mutant keep-overwrites     "$K s/\[ ! -e \"\$HOME_DIR\/start.default\" \] \&\& //"
  mutant keep-never          "$K s/^    printf 'terminal\\\\n'/    printf ''/"
  mutant set-no-marker       "$S{/^    printf 'installsdsolo pid=/d}"
  mutant set-marker-left     "$S{/^    rm -f \"\$HOME_DIR\/\\\\\\\$internal\"\$/d}"
  mutant set-judged-on-exit  "$S s/if grep -qsx 'terminal' \"\$HOME_DIR\/start.default\"; then/if true; then/"
  mutant set-runs-for-menu   "$S s/^if \[ \"\$start_choice\" = terminal \]; then\$/if [ -n \"\$start_choice\" ]; then/"
  mutant set-aborts          "$S s/set.start.default terminal < \/dev\/null > \/dev\/null 2>\&1 || true/set.start.default terminal < \/dev\/null > \/dev\/null 2>\&1 || exit 3/"
  mutant upgrade-takes-start "s/\$linger_cli\$start_choice\" \]/\$linger_cli\" ]/"
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

IFS_LINE="IFS=\$'\\n\\t'"
OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-start: CANNOT RUN - no set line in the installer"; exit 2; }
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-$IFS_LINE}"
cut_block() { awk -v b="$1" -v e="$2" '$0 ~ b {f=1; next} $0 ~ e {f=0} f {print}' "$INST"; }
ASK=$(cut_block '^# START-ASK-BEGIN' '^# START-ASK-END')
KEEP=$(cut_block '^  # START-KEEP-BEGIN' '^  # START-KEEP-END')
SET=$(cut_block '^# START-SET-BEGIN' '^# START-SET-END')
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ';')"
for n in ASK KEEP SET; do
  [ -n "${!n}" ] || { echo "test-install-start: CANNOT RUN - no START-$n block in the installer (nothing to check)"; exit 2; }
  echo "block     : START-$n $(printf '%s\n' "${!n}" | wc -l) lines"
done
ASK="${ASK//< \/dev\/tty/< \"\$T/answer\"}"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export ASK KEEP SET OPTS T
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}
ok() { [ "$1" = yes ] && echo 0 || echo 1; }

ask() {   # ask INTERACTIVE ASSUME_YES PRESET ANSWER-or-"-" -> START=<choice>, then RC=n
  if [ "$4" = - ]; then rm -f "$T/answer"; else printf '%s\n' "$4" > "$T/answer"; fi
  I="$1" Y="$2" P="$3" bash -c '
      eval "$OPTS"
      interactive="$I"; assume_yes="$Y"; start_choice="$P"
      eval "$ASK"
      echo "START=$start_choice"' 2>&1
  echo "RC=$?"
}
keep() {   # keep TOOLHOME(yes|no) EXISTING(word or -) -> the block'"'"'s output, then RC=n
  rm -rf "$T/home"; mkdir -p "$T/home/gpl.bp"
  [ "$1" = yes ] && : > "$T/home/gpl.bp/tool_home"
  [ "$2" = - ] || printf '%s\n' "$2" > "$T/home/start.default"
  HOMEDIR="$T/home" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"
      say() { printf "%s\n" "$*"; }
      eval "$KEEP"' 2>&1
  echo "RC=$?"
}
setb() {   # setb CHOICE MODE(writes|nothing) -> the block'"'"'s output, then RC=n; the stub'"'"'s log is $T/solo.log
  rm -rf "$T/home"; mkdir -p "$T/home/bin"; : > "$T/solo.log"
  cat > "$T/home/bin/sd-solo" <<'EOS'
#!/bin/bash
{ printf 'sd-solo'; printf ' %s' "$@"; echo; } >> "$SOLO_LOG"
[ "$1" = -internal ] && [ "$2" = set.start.default ] || exit 1
if [ -f "$SOLO_HOME/\$internal" ]; then echo "marker=yes" >> "$SOLO_LOG"; else echo "marker=no" >> "$SOLO_LOG"; exit 0; fi
[ "$SOLO_MODE" = refuse ] && { echo "Connection terminated"; exit 0; }   # the door refused: LOGIN consumed no marker
rm -f "$SOLO_HOME/\$internal"
[ "$SOLO_MODE" = nothing ] && exit 0
printf '%s\n' "$3" > "$SOLO_HOME/start.default"
EOS
  chmod +x "$T/home/bin/sd-solo"
  SOLO_LOG="$T/solo.log" SOLO_HOME="$T/home" SOLO_MODE="$2" HOMEDIR="$T/home" C="$1" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"; start_choice="$C"
      say()  { printf "%s\n" "$*"; }
      warn() { printf "%s\n" "$*"; }
      eval "$SET"
      echo "END-OF-BLOCK"' 2>&1
  echo "RC=$?"
}

echo "--- A: the question"
o=$(ask 0 0 "" -);         row "A1 no terminal, no answer given: menu"                       "$(ok "$(printf '%s' "$o" | grep -qx 'START=menu' && printf '%s' "$o" | grep -qx 'RC=0' && echo yes)")" "$o"
o=$(ask 1 1 "" p);         row "A2 --yes: menu, the answer file is not read"                 "$(ok "$(printf '%s' "$o" | grep -qx 'START=menu' && echo yes)")" "$o"
o=$(ask 1 0 "" "");        row "A3 a terminal, Enter: menu"                                  "$(ok "$(printf '%s' "$o" | grep -qx 'START=menu' && echo yes)")" "$o"
o=$(ask 1 0 "" p);         row "A4 p: terminal"                                              "$(ok "$(printf '%s' "$o" | grep -qx 'START=terminal' && echo yes)")" "$o"
o=$(ask 1 0 "" prompt);    row "A5 prompt: terminal"                                         "$(ok "$(printf '%s' "$o" | grep -qx 'START=terminal' && echo yes)")" "$o"
o=$(ask 1 0 "" x);         row "A6 x: menu (only p or prompt count)"                         "$(ok "$(printf '%s' "$o" | grep -qx 'START=menu' && echo yes)")" "$o"
o=$(ask 1 0 terminal "");  row "A7 --start terminal given: kept, not asked"                  "$(ok "$(printf '%s' "$o" | grep -qx 'START=terminal' && echo yes)")" "$o"

echo "--- K: an upgrade keeps where sessions start"
o=$(keep no -);            row "K1 a tree from before the home screen (no gpl.bp/tool_home): start.default says terminal, and the line says so" \
                               "$(ok "$(grep -qsx terminal "$T/home/start.default" && printf '%s' "$o" | grep -q 'keep starting at the command prompt' && printf '%s' "$o" | grep -qx 'RC=0' && echo yes)")" "$o / $(cat "$T/home/start.default" 2>&1)"
o=$(keep yes -);           row "K2 a tree that has the home screen: nothing written"         "$(ok "$([ ! -e "$T/home/start.default" ] && echo yes)")" "$o"
o=$(keep no menu);         row "K3 a tree with start.default (menu): left as it is"          "$(ok "$(grep -qsx menu "$T/home/start.default" && echo yes)")" "$o / $(cat "$T/home/start.default" 2>&1)"

echo "--- S: the answer applied"
o=$(setb terminal writes); row "S1 terminal: set.start.default terminal through the internal door, the file says terminal, the marker is gone, the line says the prompt" \
                               "$(ok "$(grep -qx 'sd-solo -internal set.start.default terminal' "$T/solo.log" && grep -qx 'marker=yes' "$T/solo.log" && [ ! -e "$T/home/\$internal" ] && grep -qsx terminal "$T/home/start.default" && printf '%s' "$o" | grep -q 'start at the command prompt' && echo yes)")" "$o / $(cat "$T/solo.log")"
o=$(setb terminal nothing); row "S2 the verb writes nothing: a WARNING naming the command, the block ends 0" \
                               "$(ok "$(printf '%s' "$o" | grep -q 'WARNING: the start setting was not written.*set.start.default terminal' && printf '%s' "$o" | grep -q 'END-OF-BLOCK' && printf '%s' "$o" | grep -qx 'RC=0' && echo yes)")" "$o"
o=$(setb menu writes);     row "S3 menu: the verb is not run, the line says the home screen" "$(ok "$(! grep -q set.start.default "$T/solo.log" && printf '%s' "$o" | grep -q 'start at the home screen' && echo yes)")" "$o / $(cat "$T/solo.log")"
o=$(setb terminal refuse); row "S5 the door refuses and consumes no marker: the block removes it itself, WARNING, ends 0" \
                               "$(ok "$([ ! -e "$T/home/\$internal" ] && printf '%s' "$o" | grep -q 'WARNING: the start setting was not written' && printf '%s' "$o" | grep -qx 'RC=0' && echo yes)")" "marker: $(ls -A "$T/home" | tr '\n' ' ') / $o"
o=$(setb "" writes);       row "S4 empty (an upgrade): nothing run, nothing said"           "$(ok "$(! grep -q set.start.default "$T/solo.log" && [ "$(printf '%s\n' "$o" | grep -v -e END-OF-BLOCK -e '^RC=' | grep -c .)" = 0 ] && echo yes)")" "$o"

echo "--- P: the places"
ln_of() { grep -n -m1 -F -x -- "$1" "$INST" | cut -d: -f1; }
l_cf=$(grep -n -m1 -F '[ -n "$start_choice" ] || start_choice="${cf_start:-}"' "$INST" | cut -d: -f1)
l_ask=$(ln_of '# START-ASK-BEGIN'); l_pw=$(grep -n -m1 '^# passwords, in the owner' "$INST" | cut -d: -f1)
l_keep=$(ln_of '  # START-KEEP-BEGIN'); l_stage=$(grep -n -m1 'solo-stage.sh" --upgrade' "$INST" | cut -d: -f1)
l_mend=$(ln_of '# MANUALS-PDF-END'); l_set=$(ln_of '# START-SET-BEGIN'); l_send=$(ln_of '# START-SET-END')
l_stop=$(ln_of '"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true')
row "P1 START-ASK follows the control file's start and precedes the passwords" "$(ok "$([ -n "$l_cf" ] && [ -n "$l_pw" ] && [ "$l_cf" -lt "$l_ask" ] && [ "$l_ask" -lt "$l_pw" ] && echo yes)")" "lines $l_cf $l_ask $l_pw"
row "P2 START-KEEP precedes the stage's --upgrade"                             "$(ok "$([ -n "$l_keep" ] && [ -n "$l_stage" ] && [ "$l_keep" -lt "$l_stage" ] && echo yes)")" "lines $l_keep $l_stage"
row "P3 START-SET follows MANUALS-PDF and precedes the stop of the stage's daemon" "$(ok "$([ -n "$l_mend" ] && [ -n "$l_stop" ] && [ "$l_mend" -lt "$l_set" ] && [ "$l_send" -lt "$l_stop" ] && echo yes)")" "lines $l_mend $l_set $l_send $l_stop"
row "P4 no block has an exit" "$(ok "$(printf '%s\n%s\n%s\n' "$ASK" "$KEEP" "$SET" | grep -v '^\s*#' | grep -q -E '(^|[^a-z_])exit( |$)' && echo no || echo yes)")" "an exit is in a block"
row "P5 --start is refused on an --upgrade (it is in the upgrade's list of refused options)" "$(ok "$(grep -q -F '$linger_cli$start_choice" ]' "$INST" && grep -q -e '--no-linger or --start option' "$INST" && echo yes)")" ""

echo "test-install-start: $pass passed, $fail failed"
[ "$((pass + fail))" -eq 0 ] && { echo "test-install-start: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
