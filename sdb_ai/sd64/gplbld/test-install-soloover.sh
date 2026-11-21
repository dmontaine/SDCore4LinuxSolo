#!/bin/bash
# test-install-soloover.sh - installsdsolo.sh run over an installed Solo upgrades it in place, with no flag (22 Nov 2026, S.282; owner, 21 Nov 2026: "the
# windows installers just install over and existing installation updating what needs to be updated there is no delete required", then "yes please implement
# parity with windows on how install works").  It used to refuse and name --upgrade.  No install, no sudo, no sd.  Exit 0 every row held, 1 one did not, 2 it
# could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-soloover.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh keeps it between "# INSTALL-OVER-BEGIN" and "# INSTALL-OVER-END".  This cuts it out and runs it under the installer's own
# `set -euo pipefail` and IFS on scratch folders, and prints what `upgrade` became.  That the block comes BEFORE the upgrade checks (so an install over gets
# exactly --upgrade's checks and refusals) and that no refusal of an installed tree is left are read as TEXT.  It cannot say a real upgrade works: that is
# verify-solo-install.sh on a real Solo, NOT run for this change.
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
  mutant() {   # name, sed expression applied to the installer
    local f="$T/$1.sh"
    sed -e "$2" "$ROOT/installsdsolo.sh" > "$f"
    if cmp -s "$ROOT/installsdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if INSTALLER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  mutant refuses-again   '/^# INSTALL-OVER-BEGIN$/,/^# INSTALL-OVER-END$/ s/^  upgrade=1$/  refuse "already installed"/'
  mutant always-upgrade  '/^# INSTALL-OVER-BEGIN$/,/^# INSTALL-OVER-END$/ s/^if \[ -f "\$HOME_DIR\/.sdcoresolo" \] \&\& \[ "\$upgrade" -eq 0 \]; then$/if true; then/'
  mutant silent          '/^# INSTALL-OVER-BEGIN$/,/^# INSTALL-OVER-END$/ s/upgrading it in place/going on/'
  mutant after-checks    '/^# INSTALL-OVER-BEGIN$/,/^# INSTALL-OVER-END$/d'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

[ -r "$INSTALLER" ] || { echo "test-install-soloover: CANNOT RUN - no installer at $INSTALLER"; exit 2; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# INSTALL-OVER-BEGIN$/,/^# INSTALL-OVER-END$/' "$INSTALLER" > "$T/block.sh"
echo "installer : $INSTALLER"
grep -q 'upgrade=1' "$T/block.sh" || { echo "test-install-soloover: CANNOT RUN - no INSTALL-OVER block that sets upgrade"; exit 2; }

run_block() {   # run_block HOME UPGRADE -> the block's output, then UPGRADE=<value>
  HOME_DIR="$1" upgrade="$2" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    RED=""; NC=""
    say() { printf "%s\n" "$*"; }
    refuse() { printf "REFUSED: %s\n" "$*"; exit 2; }
    . "'"$T"'/block.sh"
    echo "UPGRADE=$upgrade"
  ' 2>&1 || true
}
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

mkdir -p "$T/inst" "$T/fresh"; : > "$T/inst/.sdcoresolo"
out="$(run_block "$T/inst" 0)"
row "O1 over an installed Solo (the .sdcoresolo marker) with no flag: it becomes the upgrade (upgrade=1) and says so; nothing is refused" \
  "$(has "$out" "UPGRADE=1" && has "$out" "already installed in $T/inst: upgrading it in place" && ! has "$out" "REFUSED" && echo 0 || echo 1)" "$out"
out="$(run_block "$T/fresh" 0)"
row "O2 CONTROL: a folder with no installed Solo stays a new install (upgrade=0), with nothing said" "$(has "$out" "UPGRADE=0" && ! has "$out" "upgrading" && echo 0 || echo 1)" "$out"
out="$(run_block "$T/inst" 1)"
row "O3 --upgrade given over an installed Solo means the same: upgrade=1, and the block adds nothing" "$(has "$out" "UPGRADE=1" && ! has "$out" "upgrading it in place" && echo 0 || echo 1)" "$out"

code() { grep -v '^[[:space:]]*#' "$INSTALLER"; }
row "T1 no refusal of an installed tree is left in the code" "$(code | grep -qF 'is already installed in $HOME_DIR.' && echo 1 || echo 0)"
l_blk="$(grep -n '^# INSTALL-OVER-BEGIN$' "$INSTALLER" | head -1 | cut -d: -f1)"
l_chk="$(grep -n '^if \[ "\$upgrade" -eq 1 \]; then$' "$INSTALLER" | head -1 | cut -d: -f1)"
row "T2 the block comes BEFORE the upgrade checks, so an install over is checked and refused exactly as --upgrade is" \
  "$([ -n "$l_blk" ] && [ -n "$l_chk" ] && [ "$l_blk" -lt "$l_chk" ] && echo 0 || echo 1)" "block $l_blk, checks $l_chk"

echo
echo "test-install-soloover: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
