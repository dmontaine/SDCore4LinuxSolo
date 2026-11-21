#!/bin/bash
# test-install-solodoors.sh - the API and ssh doors across a Keep reinstall (22 Nov 2026, S.282; owner, 21 Nov 2026: "settings do not get changes after delete and
# install if the user chooses keep data"; Windows SOLO 85 was the same defect).  deletesdsolo.sh --keep-data notes each door as its socket unit says
# (doors.saved: api= and ssh=, off, local or open) before it removes the units; keep_prune keeps the note and is_kept_tree accepts it; a reinstall that reloads the
# data takes the note as its answers, so ACCESS-ASK asks nothing about them.  No install, no systemd, no sudo.  Exit 0 every row held, 1 one did not, 2 it could
# not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-solodoors.sh [--selftest]
#
# THE BLOCKS.  deletesdsolo.sh's DOORS-NOTE (door_mode, note_doors) is run on scratch unit files and a scratch tree; installsdsolo.sh's DOORS-KEPT is run under the
# installer's own `set -euo pipefail` and IFS with the variables it reads.  The order (the note BEFORE the units go; the kept doors AFTER the control file and
# BEFORE ACCESS-ASK) and the keep lists are read as TEXT.  It cannot say a real reinstall opens the door again: that is a real-install row, NOT run for this change.
#
# --selftest breaks the two scripts in the ways listed at the end and requires the rows to notice each one.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
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
    if [ "$2" = i ]; then src="$ROOT/installsdsolo.sh"; else src="$ROOT/deletesdsolo.sh"; fi
    sed -e "$3" "$src" > "$f"
    if cmp -s "$src" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if [ "$2" = i ]; then ei="$f"; else er="$f"; fi
    if INSTALLER="$ei" REMOVER="$er" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real scripts first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real scripts do not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real scripts pass"
  mutant open-read-as-local   r 's/    0.0.0.0:\*)   echo open ;;/    0.0.0.0:*)   echo local ;;/'
  mutant unknown-noted        r 's/  if \[ "\$a" = unknown \] || \[ "\$s" = unknown \]; then/  if false; then/'
  mutant noted-on-delete      r 's/^if \[ "\${data:-}" = "keep" \]; then note_doors "\$UNITDIR" "\$H"; fi/note_doors "$UNITDIR" "$H"/'
  mutant note-not-kept        r 's/"\$d"\/start.default "\$d"\/doors.saved; do/"$d"\/start.default; do/'
  mutant kept-tree-refuses    i 's/      audit|audit.\*|start.default|doors.saved) {/      audit|audit.*|start.default) {/'
  mutant option-overridden    i 's/  if \[ -z "\$api" \] \&\& \[ -n "\$kd" \]; then api=/  if [ -n "$kd" ]; then api=/'
  mutant declined-reload-used i 's/^if \[ "\$kept_tree" -eq 1 \] \&\& \[ "\$reload_ans" = "yes" \] \&\& \[ -f "\$HOME_DIR\/doors.saved" \]/if [ "$kept_tree" -eq 1 ] \&\& [ -f "$HOME_DIR\/doors.saved" ]/'
  mutant bad-value-taken      i 's/grep -E "\^\$2=(off|local|open)\\\$"/grep -E "^$2="/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

for f in "$INSTALLER" "$REMOVER"; do [ -r "$f" ] || { echo "test-install-solodoors: CANNOT RUN - $f is not there"; exit 2; }; done
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# DOORS-NOTE-BEGIN$/,/^# DOORS-NOTE-END$/' "$REMOVER" > "$T/note.sh"
awk '/^# DOORS-KEPT-BEGIN$/,/^# DOORS-KEPT-END$/' "$INSTALLER" > "$T/kept.sh"
echo "installer : $INSTALLER"; echo "remover   : $REMOVER"
grep -q '^note_doors()' "$T/note.sh" && grep -q '^kept_door()' "$T/kept.sh" || { echo "test-install-solodoors: CANNOT RUN - a block is missing"; exit 2; }
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

note() {   # note UNITDIR TREE -> said lines
  bash -c 'set -uo pipefail; say() { printf "%s\n" "$*"; }; warn() { printf "WARN %s\n" "$*"; }; restore_warn() { printf "WARN %s | %s\n" "$1" "${2:-}"; }; . "'"$T"'/note.sh"; note_doors "$1" "$2"' _ "$1" "$2" 2>&1
}
mkdir -p "$T/u1" "$T/t1" "$T/u2" "$T/t2" "$T/u3" "$T/t3"
printf 'ListenStream=0.0.0.0:4249\n' > "$T/u1/sd-solo-api.socket"; printf 'ListenStream=127.0.0.1:4251\n' > "$T/u1/sd-solo-ssh.socket"
out="$(note "$T/u1" "$T/t1")"
row "N1 an open API and a local ssh are noted as they are (api=open, ssh=local), mode 600, and said" \
  "$([ "$(cat "$T/t1/doors.saved" 2>/dev/null | tr '\n' ',')" = "api=open,ssh=local," ] && [ "$(stat -c %a "$T/t1/doors.saved")" = 600 ] && has "$out" "the API is open and ssh is local" && echo 0 || echo 1)" "$out / $(tr '\n' ',' < "$T/t1/doors.saved" 2>/dev/null)"
out="$(note "$T/u2" "$T/t2")"
row "N2 no socket units at all: both doors are off, and noted so" "$([ "$(tr '\n' ',' < "$T/t2/doors.saved" 2>/dev/null)" = "api=off,ssh=off," ] && echo 0 || echo 1)" "$out"
printf 'ListenStream=%%t/x.sock\n' > "$T/u3/sd-solo-api.socket"
out="$(note "$T/u3" "$T/t3")"
row "N3 NULL CASE: a door it cannot read is not guessed: no note is written, and it says a reinstall will ask" "$([ ! -e "$T/t3/doors.saved" ] && has "$out" "WARN the API or ssh door could not be read" && echo 0 || echo 1)" "$out"

kept() {   # kept KEPT_TREE RELOAD_ANS API SSH NOTE_TEXT -> said lines, then API=... SSH=...
  local h="$T/h.$RANDOM"; mkdir -p "$h"; [ -z "$5" ] || printf '%s' "$5" > "$h/doors.saved"
  HOME_DIR="$h" kept_tree="$1" reload_ans="$2" api="$3" ssh="$4" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    say() { printf "%s\n" "$*"; }
    . "'"$T"'/kept.sh"
    echo "API=$api SSH=$ssh"
  ' 2>&1
}
out="$(kept 1 yes "" "" $'api=open\nssh=local\n')"
row "K1 a reload takes the note: API open and ssh local, each said 'as it was before: not asked'" "$(has "$out" "API=open SSH=local" && has "$out" "The API is open, as it was before: not asked." && echo 0 || echo 1)" "$out"
out="$(kept 1 yes local "" $'api=open\nssh=open\n')"
row "K2 an --api (or control file) value given still wins; only the door not given is taken from the note" "$(has "$out" "API=local SSH=open" && echo 0 || echo 1)" "$out"
out="$(kept 1 no "" "" $'api=open\nssh=open\n')"
row "K3 a reload declined (start clean) does not use the note: nothing is set, ACCESS-ASK will ask" "$(has "$out" "API= SSH=" && ! has "$out" "not asked" && echo 0 || echo 1)" "$out"
out="$(kept 1 yes "" "" $'api=wide\nssh=open\n')"
row "K4 a value that is not off, local or open is ignored (that door is asked); a good one is still taken" "$(has "$out" "API= SSH=open" && echo 0 || echo 1)" "$out"
out="$(kept 0 yes "" "" $'api=open\nssh=open\n')"
row "K5 CONTROL: not a kept tree: nothing is taken" "$(has "$out" "API= SSH=" && echo 0 || echo 1)" "$out"

l_note="$(grep -n '^if \[ "\${data:-}" = "keep" \]; then note_doors "\$UNITDIR" "\$H"; fi' "$REMOVER" | cut -d: -f1)"
l_units="$(grep -n '^remove_units_step "\$H" "\$UNITDIR"' "$REMOVER" | cut -d: -f1)"
row "T1 the remover notes the doors only with --keep-data and BEFORE the units are removed" "$([ -n "$l_note" ] && [ -n "$l_units" ] && [ "$l_note" -lt "$l_units" ] && echo 0 || echo 1)" "note $l_note, units $l_units"
row "T2 keep_prune keeps doors.saved (a regular file) and is_kept_tree accepts it" \
  "$(grep -qF '"$d"/start.default "$d"/doors.saved; do' "$REMOVER" && grep -qF 'audit|audit.*|start.default|doors.saved) {' "$INSTALLER" && echo 0 || echo 1)"
l_cf="$(grep -n '^  \[ -n "\$api" \] || api="\$cf_api"' "$INSTALLER" | head -1 | cut -d: -f1)"
l_kept="$(grep -n '^# DOORS-KEPT-BEGIN$' "$INSTALLER" | cut -d: -f1)"
l_ask="$(grep -n '^# ACCESS-ASK-BEGIN$' "$INSTALLER" | cut -d: -f1)"
l_rel="$(grep -n 'if ask_yn "Reload your saved data and configuration into this new install?"' "$INSTALLER" | cut -d: -f1)"
row "T3 the installer takes the note AFTER the control file and the reload question and BEFORE ACCESS-ASK" \
  "$([ -n "$l_cf" ] && [ -n "$l_rel" ] && [ -n "$l_kept" ] && [ -n "$l_ask" ] && [ "$l_cf" -lt "$l_kept" ] && [ "$l_rel" -lt "$l_kept" ] && [ "$l_kept" -lt "$l_ask" ] && echo 0 || echo 1)" "cf $l_cf, reload $l_rel, kept $l_kept, ask $l_ask"

echo
echo "test-install-solodoors: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
