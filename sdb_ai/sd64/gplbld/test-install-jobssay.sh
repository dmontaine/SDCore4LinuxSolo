#!/bin/bash
#
# test-install-jobssay.sh - installsdsolo.sh's JOBS-SAY block (19 Nov 2026, S.274): a reload install says the stage's "solo-stage: jobs:" line, which was only in
# $WORK/stage.log (deleted when the installer ends), so the person never learned whether the kept scheduled jobs got their timers back.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-jobssay.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-jobssay.sh --selftest
#
# FREE CHECK: no sudo, no install, no running sd.  Exit 0 every row passed, 1 a row failed, 2 it could not run (the block or the installer's set line missing).
#
# WHAT IT RUNS.  The block cut out between its markers and evaluated under the installer's own "set" line and IFS, with a scratch stage.log and say() as the
# installer defines it.
#
#   J1  the success line (with colour codes and a CR, as the stage's sd output can carry): "Scheduled jobs: 1 job(s) given their timers again ..."
#   J2  the failure line: "Scheduled jobs: the kept definitions were NOT given their timers: ..."
#   J3  no jobs line (no kept $jobs): nothing said, the block ends 0
#   J4  two jobs lines: the last one is said, once
#   P   the block is in the fresh-install branch after the stage ran (after the bootstrap's stage.log is written) and has no exit
#
# NOT MEASURED HERE: the real stage and a real reload, which is witness-s247.py J10b on the VM.

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
  B='/^# JOBS-SAY-BEGIN/,/^# JOBS-SAY-END/'
  mutant says-nothing   "$B s/|| say \"Scheduled jobs: /|| true \"Scheduled jobs: /"
  mutant first-not-last "$B s/| tail -1)\"\$/| head -1)\"/"
  mutant no-ansi-strip  "$B s/sed -e 's\/\\\\x1b[^ ]* -e 's\/\\\\r\/\/g' /cat /"
  mutant says-empty     "$B s/^\[ -z \"\$jobs_state\" \] || say/say/"
  mutant block-removed  "/^# JOBS-SAY-BEGIN/,/^# JOBS-SAY-END/{/^jobs_state=/d}"
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-jobssay: CANNOT RUN - no set line in the installer"; exit 2; }
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-IFS=\$'\\n\\t'}"
BLOCK="$(awk '/^# JOBS-SAY-BEGIN/ {f=1; next} /^# JOBS-SAY-END/ {f=0} f {print}' "$INST")"
[ -n "$BLOCK" ] || { echo "test-install-jobssay: CANNOT RUN - no JOBS-SAY block in $INST"; exit 2; }
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ' ')"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pass=0; failn=0
row() { if [ "$2" = 1 ]; then echo "  [PASS] $1"; pass=$((pass+1)); else echo "  [FAIL] $1"; echo "         got: $3"; failn=$((failn+1)); fi; }

run_block() {   # stage.log contents -> prints what the block said, then rc=N
  mkdir -p "$T/w"; printf '%b' "$1" > "$T/w/stage.log"
  bash -c "$OPTS"$'\n'"say()  { printf '%s\n' \"\$*\"; }"$'\n'"WORK='$T/w'"$'\n'"$BLOCK" 2>&1; echo "rc=$?"
}

OK='1 job(s) given their timers again from the kept definitions'
BAD='the kept definitions were NOT given their timers: Job wkeep: systemctl failed'

out="$(run_block "solo-stage: OS access: none\n\x1b[1msolo-stage: jobs: $OK\x1b[0m\r\nSOLO RELOAD DONE data=reloaded config=kept\n")"
row "J1 the success line is said, colour codes and CR taken off" "$([ "$out" = "Scheduled jobs: $OK"$'\n'"rc=0" ] && echo 1)" "$out"
out="$(run_block "solo-stage: jobs: $BAD\nSOLO RELOAD DONE\n")"
row "J2 the failure line is said" "$([ "$out" = "Scheduled jobs: $BAD"$'\n'"rc=0" ] && echo 1)" "$out"
out="$(run_block "solo-stage: OS access: none\nSOLO RELOAD DONE\n")"
row "J3 no jobs line: nothing said, the block ends 0" "$([ "$out" = "rc=0" ] && echo 1)" "$out"
out="$(run_block "solo-stage: jobs: $BAD\nsolo-stage: jobs: $OK\n")"
row "J4 two jobs lines: the last is said, once" "$([ "$out" = "Scheduled jobs: $OK"$'\n'"rc=0" ] && echo 1)" "$out"

# P: the place.  The block comes after the bootstrap stage writes stage.log in the fresh-install branch, before the passwords check, and has no exit.
stage_ln=$(grep -n 'bash "\$SRC/gplbld/solo-stage.sh" "\${st_args\[@\]}"' "$INST" | head -1 | cut -d: -f1)
say_ln=$(grep -n '^# JOBS-SAY-BEGIN' "$INST" | head -1 | cut -d: -f1)
pw_ln=$(grep -n "solo-stage: passwords: reloaded" "$INST" | head -1 | cut -d: -f1)
place=0; [ -n "$stage_ln" ] && [ -n "$say_ln" ] && [ -n "$pw_ln" ] && [ "$stage_ln" -lt "$say_ln" ] && [ "$say_ln" -lt "$pw_ln" ] && place=1
printf '%s\n' "$BLOCK" | grep -qE '(^|[^_])exit( |$)' && place=0
row "P  the block follows the bootstrap stage, precedes the passwords check, has no exit" "$place" "stage=$stage_ln block=$say_ln passwords=$pw_ln"

echo "test-install-jobssay: $pass passed, $failn failed"
[ "$failn" -eq 0 ]
