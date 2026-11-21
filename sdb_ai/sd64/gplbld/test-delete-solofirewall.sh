#!/bin/bash
# test-delete-solofirewall.sh - deletesdsolo.sh's solo_firewall (22 Nov 2026, S.283; owner, 21 Nov 2026, relayed: "if we opened it we manage it ... if they choose
# delete data and config, then that should include closing any port that we opened", keeping the port as it is when the data is kept).  Solo's own ports are
# 4249 and 4251: with keep their rules stay (said), with delete they are removed (ufw and firewalld); 4243 and port 22 are never touched.  No sudo, no ufw, no
# firewalld.  Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-delete-solofirewall.sh [--selftest]
#
# THE BLOCK.  deletesdsolo.sh keeps it between "# SOLO-FIREWALL-BEGIN" and "# SOLO-FIREWALL-END".  This runs it under `set -uo pipefail` (the remover's options)
# with `sudo` a function, `ufw`, `firewall-cmd` and `systemctl` stubs that log their arguments and answer from the case, and judges the LOG of what was asked and
# what was said.  It cannot say a real firewall changed: that is a real-install row, NOT run for this change.
#
# --selftest breaks the remover in the ways listed at the end and requires the rows to notice each one.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, sed expression applied to the remover
    local f="$T/$1.sh"
    sed -e "$2" "$ROOT/deletesdsolo.sh" > "$f"
    if cmp -s "$ROOT/deletesdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if REMOVER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real remover first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real remover does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real remover passes"
  mutant keep-removes       's/      if \[ "\$mode" = keep \]; then/      if false; then/'
  mutant delete-only-warns  's/      elif sudo -n ufw delete allow "\$p\/tcp" >\/dev\/null 2>\&1; then/      elif false; then/'
  mutant touches-4243       's/    for p in 4249 4251; do/    for p in 4249 4251 4243; do/'
  mutant always-keep        's/^if \[ "\$data" = "keep" \]; then solo_firewall keep; else solo_firewall delete; fi$/solo_firewall keep/'
  mutant firewalld-ignored  's/      elif sudo -n firewall-cmd -q --permanent --remove-port=/      elif false \&\& sudo -n firewall-cmd -q --permanent --remove-port=/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

[ -r "$REMOVER" ] || { echo "test-delete-solofirewall: CANNOT RUN - no remover at $REMOVER"; exit 2; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# SOLO-FIREWALL-BEGIN$/,/^# SOLO-FIREWALL-END$/' "$REMOVER" > "$T/block.sh"
echo "remover : $REMOVER"
grep -q '^solo_firewall()' "$T/block.sh" || { echo "test-delete-solofirewall: CANNOT RUN - no solo_firewall between the markers"; exit 2; }
mkdir -p "$T/bin"
for c in ufw firewall-cmd systemctl; do
  printf '%s\n' '#!/bin/bash' "echo \"$c \$*\" >> \"\$LOG\"" \
    "case \"$c \$*\" in" \
    '  "ufw status") printf "%s\n" "$UFW_STATUS"; exit 0 ;;' \
    '  "ufw delete allow"*) exit "${UFW_DEL_RC:-0}" ;;' \
    '  "firewall-cmd --permanent --list-ports") printf "%s\n" "$FWD_PORTS"; exit 0 ;;' \
    '  "systemctl is-active --quiet firewalld") exit "${FWD_ACTIVE:-1}" ;;' \
    'esac' 'exit 0' > "$T/bin/$c"
  chmod +x "$T/bin/$c"
done
run() {   # run MODE UFW_STATUS FWD_ACTIVE FWD_PORTS -> said lines, then LOG: ...
  local log="$T/log.$RANDOM"; : > "$log"
  LOG="$log" UFW_STATUS="$2" FWD_ACTIVE="$3" FWD_PORTS="$4" PATH="$T/bin:$PATH" bash -c '
    set -uo pipefail
    say()  { printf "%s\n" "$*"; }
    warn() { printf "WARN %s\n" "$*"; }
    sudo() { [ "$1" = -n ] && shift; "$@"; }
    . "'"$T"'/block.sh"
    solo_firewall "$1"
  ' _ "$1" 2>&1
  echo "LOG: $(tr '\n' ';' < "$log")"
}
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }
U='Status: active
4249/tcp                   ALLOW       Anywhere
4251/tcp                   ALLOW       Anywhere
4243/tcp                   ALLOW       Anywhere
22/tcp                     ALLOW       Anywhere'

out="$(run delete "$U" 1 "")"
row "F1 delete: ufw's rules for 4249 and 4251 are removed and said; 4243 is named and left; port 22 is never asked about" \
  "$(has "$out" "ufw delete allow 4249/tcp" && has "$out" "ufw delete allow 4251/tcp" && has "$out" "removed 'allow 4249/tcp'" && ! has "$out" "delete allow 4243" && ! has "$out" "delete allow 22" && has "$out" "4243: that is OpenQM" && echo 0 || echo 1)" "$out"
out="$(run keep "$U" 1 "")"
row "F2 keep: nothing is removed, and each kept rule is said" \
  "$(! has "$out" "ufw delete" && has "$out" "TCP 4249, this product's API port, is kept with your data" && has "$out" "TCP 4251, this product's ssh port, is kept" && echo 0 || echo 1)" "$out"
out="$(run delete "Status: active" 1 "")"
row "F3 NULL CASE: no rule for Solo's ports: nothing is removed and nothing is said about them" "$(! has "$out" "ufw delete" && ! has "$out" "4249" && echo 0 || echo 1)" "$out"
out="$(run delete "" 0 "4249/tcp 4251/tcp 1025-65535/tcp")"
row "F4 delete, firewalld: the exact 4249/tcp and 4251/tcp entries are removed and firewalld reloaded; the 1025-65535 range is not touched" \
  "$(has "$out" "firewall-cmd -q --permanent --remove-port=4249/tcp" && has "$out" "firewall-cmd -q --permanent --remove-port=4251/tcp" && has "$out" "firewall-cmd -q --reload" && ! has "$out" "remove-port=1025" && echo 0 || echo 1)" "$out"
out="$(run keep "" 0 "4249/tcp")"
row "F5 keep, firewalld: nothing is removed, and it is said" "$(! has "$out" "remove-port" && has "$out" "firewalld: TCP 4249, this product's API port, is kept" && echo 0 || echo 1)" "$out"
l_call="$(grep -n '^if \[ "\$data" = "keep" \]; then solo_firewall keep; else solo_firewall delete; fi$' "$REMOVER" | cut -d: -f1)"
row "T1 the remover calls it with keep when the data is kept and delete otherwise" "$([ -n "$l_call" ] && echo 0 || echo 1)"

echo
echo "test-delete-solofirewall: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
