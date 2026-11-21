#!/bin/bash
# test-install-restorewarn.sh (SOLO) - S.292 (22 Nov 2026), carried from SD Core: what an install or an uninstall could not put back is collected and printed
# ONCE, as a boxed bold red block with the exact command for each (owner, 21 Nov 2026, Windows chat, relayed T0800: "if the admin says not to delete during a
# deletion then the system should be put back exactly as it was before the uninstall.  If that is impossible then the admin needs to be warned during the install
# the exact steps they must take to restore the system exactly as it was." and "If there are warnings they should not be buried in other text.  They need to be
# explicit, stand out so that they can not be missed.").  No sudo, no install, no systemd.  Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-restorewarn.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh and deletesdsolo.sh each hold the text between "# RESTORE-WARN-BEGIN" and "# RESTORE-WARN-END".  The two copies must be byte for
# byte equal (B1), and equal to SD Core's (B2, skipped with a notice when /home/don/Projects/SDCore4Linux is not there).  F rows cut the block out and run it under
# the installer's own `set -euo pipefail` and IFS; T rows read every CALL SITE as text: the closing block under the banner, the jobs, the register, the two firewall
# rules, the two door notes of the uninstaller and its closing block.  It cannot say what a real terminal shows: that is a real-install row.
#
# --selftest breaks the scripts in the ways listed at the end and requires the rows to notice each one.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
CORE_INSTALLER="${CORE_INSTALLER:-/home/don/Projects/SDCore4Linux/installsdcore.sh}"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, file (i or r), sed expression
    local f="$T/$1.sh" ei="$ROOT/installsdsolo.sh" er="$ROOT/deletesdsolo.sh" src
    if [ "$2" = i ]; then src="$ei"; else src="$er"; fi
    sed -e "$3" "$src" > "$f"
    if cmp -s "$src" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if [ "$2" = i ]; then ei="$f"; else er="$f"; fi
    if INSTALLER="$ei" REMOVER="$er" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real scripts first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real scripts do not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real scripts pass"
  mutant copies-differ       r 's/printf .\\n\\033\[1;31m%s\\n# %s\\n%s\\n. "\$rule"/printf "\\n\\033[1;31m%s\\n# %s\\n%s\\n" "$rule"/'
  mutant not-bold-red        i 's/\\033\[1;31m%s/\\033[0;31m%s/'
  mutant no-reset            i 's/printf .%s\\033\[0m\\n\\n. "\$rule"/printf "%s\\n\\n" "$rule"/'
  mutant prints-when-empty   i 's/^    \[ "\${#restore_warns\[@\]}" -gt 0 \] || return 0$/    :/'
  mutant no-numbering        i 's/printf .%s. %s\\n. "\$n" /printf "%s %s\\n" "-" /'
  mutant install-block-gone  i 's/^restore_warn_block "THE INSTALL COULD NOT PUT BACK.*$/:/'
  mutant jobs-silent         i 's/^  "the kept definitions were NOT given their timers"\*)$/  "never matches")/'
  mutant register-silent     i 's/^  "NOT carried"\*)$/  "never matches")/'
  mutant ufw-failure-silent  i 's/|| restore_warn "The ufw rule for \$what/|| : "The ufw rule for $what/'
  mutant fwd-failure-silent  i 's/|| restore_warn "The firewalld rule for \$what/|| : "The firewalld rule for $what/'
  mutant deleter-no-block    r 's/^restore_warn_block "THE UNINSTALL COULD NOT SAVE.*$/:/'
  mutant deleter-read-silent r 's/^    restore_warn "the API or ssh door could not be read/    : "the API or ssh door could not be read/'
  mutant deleter-note-silent r 's/^    restore_warn "the API (\$a) and ssh (\$s) doors could not be noted/    : "the API ($a) and ssh ($s) doors could not be noted/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

for f in "$INSTALLER" "$REMOVER"; do [ -r "$f" ] || { echo "test-install-restorewarn: CANNOT RUN - $f is not there"; exit 2; }; done
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
echo "installer : $INSTALLER"; echo "remover   : $REMOVER"
awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$INSTALLER" > "$T/inst-block.sh"
awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$REMOVER" > "$T/del-block.sh"
for b in inst-block del-block; do
  grep -q '^restore_warn_block()' "$T/$b.sh" || { echo "test-install-restorewarn: CANNOT RUN - no RESTORE-WARN block in $b"; exit 2; }
done
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }
run_block() {   # run_block FILE 'script' -> output: the block under the installer's own options, then the script
  BLOCKFILE="$1" SCRIPT="$2" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    . "$BLOCKFILE"
    eval "$SCRIPT"
  ' 2>&1
}
ESC=$'\033'

row "B1 the two copies of the block (installer and remover) are byte for byte equal" "$(cmp -s "$T/inst-block.sh" "$T/del-block.sh" && echo 0 || echo 1)" "$(diff "$T/inst-block.sh" "$T/del-block.sh" | head -4)"
if [ -r "$CORE_INSTALLER" ]; then
  awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$CORE_INSTALLER" > "$T/core-block.sh"
  row "B2 the block equals SD Core's (one text for both products)" "$(cmp -s "$T/inst-block.sh" "$T/core-block.sh" && echo 0 || echo 1)" "$(diff "$T/inst-block.sh" "$T/core-block.sh" | head -4)"
else
  echo "  [SKIP] B2 SD Core's installer is not at $CORE_INSTALLER"
fi

out="$(run_block "$T/inst-block.sh" 'restore_warn_block "H"')"
row "F1 NULL CASE: no records, so the block prints NOTHING at all" "$([ -z "$out" ] && echo 0 || echo 1)" "[$out]"
out="$(run_block "$T/inst-block.sh" 'restore_warn "API was open" "remote.api open"; restore_warn_block "THE HEADING"')"
nb="$(printf '%s\n' "$out" | grep -c -E '^(.\[1;31m)?#{80}(.\[0m)?$' || true)"   # the first rule carries the colour start, the last one the reset
row "F2 one record with a command: the heading, '1. what', 'Type:  command', three rules, bold red at the start and a reset at the end" \
  "$(has "$out" "# THE HEADING" && has "$out" "1. API was open" && has "$out" "       Type:  remote.api open" && has "$out" "${ESC}[1;31m" && printf '%s' "$out" | grep -qF "${ESC}[0m" && [ "$nb" = 3 ] && echo 0 || echo 1)" "rules=$nb out=$out"
out="$(run_block "$T/inst-block.sh" 'restore_warn "only words"; restore_warn_block "H"')"
row "F3 a record with no command prints no 'Type:' line" "$(has "$out" "1. only words" && ! has "$out" "Type:" && echo 0 || echo 1)" "$out"
out="$(run_block "$T/inst-block.sh" 'restore_warn "first" "c1"; restore_warn "second" "c2"; restore_warn_block "H"')"
l1="$(printf '%s\n' "$out" | grep -n -F '1. first' | cut -d: -f1)"; l2="$(printf '%s\n' "$out" | grep -n -F '2. second' | cut -d: -f1)"
row "F4 two records are numbered 1 and 2 in the order collected, each with its command" "$([ -n "$l1" ] && [ -n "$l2" ] && [ "$l1" -lt "$l2" ] && has "$out" "Type:  c1" && has "$out" "Type:  c2" && echo 0 || echo 1)" "$out"
CMD='sudo x job-set a\ b ;"q" $HOME %s %d \n'
out="$(CMD="$CMD" run_block "$T/inst-block.sh" 'restore_warn "w" "$CMD"; restore_warn_block "H"')"
row "F5 a command with spaces, quotes, a semicolon, \$, % and backslashes is printed exactly as given" "$(has "$out" "Type:  $CMD" && echo 0 || echo 1)" "$out"
WH='50% done %s \n and %d'
out="$(WH="$WH" run_block "$T/inst-block.sh" 'restore_warn "$WH" "c"; restore_warn_block "H"')"
row "F6 the WHAT text is printed literally too (no format characters acted on)" "$(has "$out" "1. $WH" && echo 0 || echo 1)" "$out"

# ---- the call sites, read as text ---------------------------------------------------------------------------------------------
l_ban="$(grep -n -x -F -m1 -- '  say "SD Core Solo for Linux is installed."' "$INSTALLER" | cut -d: -f1)"
l_call="$(grep -n -F -m1 'restore_warn_block "THE INSTALL COULD NOT PUT BACK EVERYTHING YOU KEPT.' "$INSTALLER" | cut -d: -f1)"
l_home="$(awk -v s="${l_call:-0}" 'NR>s && $0 ~ /^say "  home / {print NR; exit}' "$INSTALLER")"
row "T1 the install prints the block right under its banner, before the 'home' line of the summary" \
  "$([ -n "$l_ban" ] && [ -n "$l_call" ] && [ -n "$l_home" ] && [ "$l_ban" -lt "$l_call" ] && [ $((l_home - l_call)) -le 2 ] && echo 0 || echo 1)" "banner $l_ban, call $l_call, home $l_home"
row "T2 a reload's jobs failure is collected with 'set.job restore', and only the stage's own failure wording counts" \
  "$(grep -qF '"the kept definitions were NOT given their timers"*)' "$INSTALLER" && grep -qF '" "set.job restore" ;;' "$INSTALLER" && echo 0 || echo 1)"
row "T3 a register that was NOT carried is collected with the set.os.access commands" \
  "$(grep -qF '"NOT carried"*)' "$INSTALLER" && grep -qF '" "set.os.access sh on   and   set.os.access os on" ;;' "$INSTALLER" && echo 0 || echo 1)"
fw="$(awk '/^fw_open\(\)/,/^}/' "$INSTALLER")"
row "T4 a firewall rule that fails (ufw or firewalld) is collected with the tool's own command, never a plain yellow warn" \
  "$(printf '%s\n' "$fw" | grep -qF 'restore_warn "The ufw rule for $what' && printf '%s\n' "$fw" | grep -qF '"sudo ufw allow $port/tcp"' && printf '%s\n' "$fw" | grep -qF 'restore_warn "The firewalld rule for $what' && printf '%s\n' "$fw" | grep -qF '"sudo firewall-cmd --permanent --add-port=$port/tcp && sudo firewall-cmd --reload"' && ! printf '%s\n' "$fw" | grep -qF 'warn "could not add' && echo 0 || echo 1)"
dn="$(awk '/^# DOORS-NOTE-BEGIN$/,/^# DOORS-NOTE-END$/' "$REMOVER")"
l_done="$(grep -n -x -F -m1 'say "SOLO DELETE COMPLETE $H"' "$REMOVER" | cut -d: -f1)"; l_dblk="$(grep -n -F -m1 'restore_warn_block "THE UNINSTALL COULD NOT SAVE' "$REMOVER" | cut -d: -f1)"
row "T5 the remover collects both door-note failures (unreadable, not written) with the remote.api / remote.ssh commands and prints its block after 'SOLO DELETE COMPLETE'" \
  "$([ "$(printf '%s\n' "$dn" | grep -c 'restore_warn "')" = 2 ] && printf '%s\n' "$dn" | grep -qF 'remote.api' && printf '%s\n' "$dn" | grep -qF 'remote.ssh' && [ -n "$l_done" ] && [ -n "$l_dblk" ] && [ "$l_done" -lt "$l_dblk" ] && echo 0 || echo 1)" "complete $l_done, block $l_dblk"
hi="$(sed -n 's/^restore_warn_block "\(THE INSTALL[^"]*\)"$/\1/p' "$INSTALLER" | head -1)"; hr="$(sed -n 's/^restore_warn_block "\(THE UNINSTALL[^"]*\)"$/\1/p' "$REMOVER" | head -1)"
row "T6 both headings are in CAPITAL LETTERS and say what to do" "$([ -n "$hi" ] && [ -n "$hr" ] && [ "$hi" = "${hi^^}" ] && [ "$hr" = "${hr^^}" ] && has "$hi" "DO THESE STEPS" && has "$hr" "DO THESE STEPS" && echo 0 || echo 1)" "[$hi] [$hr]"

echo
echo "test-install-restorewarn: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
