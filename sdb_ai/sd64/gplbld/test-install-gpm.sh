#!/bin/bash
# test-install-gpm.sh - installsdsolo.sh's install_gpm (17 Nov 2026, S.62, carried from SD Core's S.260 and its
# test-install-packages.sh rows P6-P8): gpm, the console mouse daemon, is not asked for where there is no console mouse
# device; where it is asked for and fails, the install warns, purges it (dpkg --purge --force-remove-reinstreq when
# apt-get cannot) and goes on, and names the command when dpkg still holds it.  No install, no sudo, no apt-get.
# Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-gpm.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh keeps install_gpm between "# GPM-BEGIN" and "# GPM-END".  This cuts it out and runs it under
# the installer's own `set -euo pipefail` and IFS, with `sudo` a function, `apt-get` and `dpkg` stubs that log their
# arguments, and `say` / `warn` printing.  ANCHORED ON THE ARGUMENTS the stubs were given and the function's exit status;
# the words are checked only for the lines a person reads.  It cannot say gpm works on a real console.
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.
set -euo pipefail
IFS=$'\n\t'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, sed expression applied to the installer's GPM block
    local f="$T/$1.sh"
    sed -e "/^# GPM-BEGIN/,/^# GPM-END/ $2" "$ROOT/installsdsolo.sh" > "$f"
    if cmp -s "$ROOT/installsdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if INSTALLER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  mutant no-device-test    's/if \[ ! -e "\$console_mouse" \]; then/if false; then/'
  mutant gpm-fatal         's/^    if dpkg -s gpm/    exit 1; if dpkg -s gpm/'
  mutant remove-not-purge  's/apt-get -y purge gpm/apt-get -y remove gpm/'
  mutant no-dpkg-fallback  's/ || sudo dpkg --purge --force-remove-reinstreq gpm > \/dev\/null 2>\&1 / /'
  mutant held-not-said     's/if dpkg -s gpm > \/dev\/null 2>\&1; then/if false; then/'
  mutant no-warning        's/WARNING: gpm could not be installed/gpm skipped/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

[ -r "$INSTALLER" ] || { echo "test-install-gpm: CANNOT RUN - no installer at $INSTALLER"; exit 2; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# GPM-BEGIN$/,/^# GPM-END$/' "$INSTALLER" > "$T/block.sh"
echo "installer : $INSTALLER"
grep -q '^install_gpm()' "$T/block.sh" || { echo "test-install-gpm: CANNOT RUN - no install_gpm between # GPM-BEGIN and # GPM-END"; exit 2; }
: > "$T/mice"   # a console mouse device that exists; "$T/no-mice" does not

# run_case LOG RC_GPM MOUSE RC_PURGE HELD -> the function's output, then RC=<its exit status>
run_case() {
  LOG="$1" RC_GPM="$2" SD_CONSOLE_MOUSE="$3" RC_PURGE="$4" HELD="$5" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    YELLOW=""; NC=""
    say()  { printf "%s\n" "$*"; }
    warn() { printf "%s\n" "$*"; }
    sudo() { "$@"; }
    apt-get() {
      { printf "apt-get"; printf " %s" "$@"; echo; } >> "$LOG"
      local IFS=" "
      case " $* " in
        *" purge "*) return "$RC_PURGE" ;;
        *" install gpm ") return "$RC_GPM" ;;
        *) return 0 ;;
      esac
    }
    dpkg() {
      { printf "dpkg"; printf " %s" "$@"; echo; } >> "$LOG"
      local IFS=" "
      case " $* " in
        *" -s gpm "*) [ "$HELD" = 1 ] ;;
        *) return 0 ;;
      esac
    }
    source "$1"
    install_gpm
    echo REACHED-END
  ' _ "$T/block.sh" 2>&1 && echo "RC=0" || echo "RC=$?"
}

: > "$T/g1.log"; out="$(run_case "$T/g1.log" 0 "$T/mice" 0 0)"
row "G1 a console mouse device and a working apt-get: one call, apt-get -y install gpm, nothing removed" \
    "$([[ "$out" == *RC=0* ]] && [[ "$out" == *REACHED-END* ]] && [ "$(cat "$T/g1.log")" = "apt-get -y install gpm" ] && echo 0 || echo 1)" "log: $(tr '\n' '|' < "$T/g1.log") out: $out"

: > "$T/g2.log"; out="$(run_case "$T/g2.log" 0 "$T/no-mice" 0 0)"
row "G2 no console mouse device: gpm is not asked for, the install says why and goes on" \
    "$([[ "$out" == *RC=0* ]] && [[ "$out" == *REACHED-END* ]] && [[ "$out" == *"has no console mouse device"* ]] && [ ! -s "$T/g2.log" ] && echo 0 || echo 1)" "log: $(tr '\n' '|' < "$T/g2.log") out: $out"

: > "$T/g3.log"; out="$(run_case "$T/g3.log" 100 "$T/mice" 0 0)"
row "G3 a failing gpm install warns, purges gpm and goes on with status 0; no dpkg fallback needed, nothing held said" \
    "$([[ "$out" == *RC=0* ]] && [[ "$out" == *REACHED-END* ]] && [[ "$out" == *"WARNING: gpm could not be installed"* ]] && grep -qx 'apt-get -y purge gpm' "$T/g3.log" && ! grep -q -- '--force-remove-reinstreq' "$T/g3.log" && [[ "$out" != *"still holds gpm"* ]] && echo 0 || echo 1)" "log: $(tr '\n' '|' < "$T/g3.log") out: $out"

: > "$T/g4.log"; out="$(run_case "$T/g4.log" 100 "$T/mice" 100 1)"
row "G4 a purge apt-get cannot do falls back to dpkg --purge --force-remove-reinstreq, and a package dpkg still holds is named with the command" \
    "$([[ "$out" == *RC=0* ]] && [[ "$out" == *REACHED-END* ]] && grep -qx 'dpkg --purge --force-remove-reinstreq gpm' "$T/g4.log" && [[ "$out" == *"dpkg still holds gpm half-installed"* ]] && echo 0 || echo 1)" "log: $(tr '\n' '|' < "$T/g4.log") out: $out"

calls="$(grep -v '^ *#' "$INSTALLER" | grep -c -E '^ *install_gpm *$' || true)"
row "G5 install_gpm is called once, from install_packages" "$([ "$calls" = 1 ] && echo 0 || echo 1)" "calls: $calls"

echo "test-install-gpm: $passed passed, $failed failed"
[ "$passed" -eq 0 ] && { echo "test-install-gpm: NOTHING RAN"; exit 2; }
[ "$failed" -eq 0 ]
