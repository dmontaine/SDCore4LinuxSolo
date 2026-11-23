#!/bin/bash
# test-install-restorewarn.sh (SOLO) - S.292, S.299 (22 Nov 2026), carried from SD Core: what an install or an uninstall could not put back is collected and
# printed ONCE, in bold red, with the line to type for each (owner, 21 Nov 2026, Windows chat, relayed T0800: "if the admin says not to delete during a deletion
# then the system should be put back exactly as it was before the uninstall.  If that is impossible then the admin needs to be warned during the install the
# exact steps they must take to restore the system exactly as it was." and "If there are warnings they should not be buried in other text.  They need to be
# explicit, stand out so that they can not be missed."; 22 Nov 2026: "use the same wording and format that windows is using").  No sudo, no install, no systemd.
# Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-restorewarn.sh [--selftest]
#
# S.299 IS THE DEFECT THIS CHECK MISSED: it matched that a command was printed, and set.job restore is refused to every person, two commands were joined on one
# line, and a failed timer never reached the box at all (the stage read "0 job(s) given their timers again" as success).  So the installer's, the stage's and the
# remover's own blocks are RUN here and their lines compared whole.  The block equals SD Core's (B2, skipped with a notice when that tree is not here).  It
# cannot say that a step works on an install: that is a real-install row.
#
# --selftest breaks the scripts in the ways listed at the end and requires the rows to notice each one.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
STAGE="${STAGE:-$HERE/solo-stage.sh}"
CORE_INSTALLER="${CORE_INSTALLER:-/home/don/SDCoreProject/SDCore4Linux/installsdcore.sh}"
SYS="$HERE/../sdsys"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, file (i, r or s), sed expression
    local f="$T/$1.sh" ei="$ROOT/installsdsolo.sh" er="$ROOT/deletesdsolo.sh" es="$HERE/solo-stage.sh" src
    case "$2" in i) src="$ei" ;; r) src="$er" ;; *) src="$es" ;; esac
    sed -e "$3" "$src" > "$f"
    if cmp -s "$src" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    case "$2" in i) ei="$f" ;; r) er="$f" ;; *) es="$f" ;; esac
    if INSTALLER="$ei" REMOVER="$er" STAGE="$es" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real scripts first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real scripts do not pass:"; tail -12 "$T/real.out"; exit 1; }
  echo "  [ok] the real scripts pass"
  mutant copies-differ       r 's/At the colon prompt type:\\n/At the prompt type:\\n/'
  mutant not-bold-red        i 's/\\033\[1;31mWARNING: SOME/\\033[0;31mWARNING: SOME/'
  mutant prints-when-empty   i 's/^    \[ "\${#restore_warns\[@\]}" -gt 0 \] || return 0$/    :/'
  mutant no-grouping         i 's/^        case "\$seen" in .*$/        :/'
  mutant printed-twice       i 's/^            case "\$shown" in .*$/            :/'
  mutant install-block-gone  i 's/^restore_warn_block "To correct.*$/:/'
  mutant restore-is-back     i "s/    printf 'set.job change %s %s %s\\\\n' \"\$2\" \"\$sched\" \"\$cmd\"/    echo 'set.job restore'/"
  mutant no-admin            i 's/^  restore_warn "\$title" "admin"$/  :/'
  mutant no-switch-on        i '/    restore_warn "\$title" "set.jobs.access on"/d'
  mutant no-switch-back      i 's/; then restore_warn "\$title" "set.jobs.access off"; fi/; then :; fi/'
  mutant switch-forgotten    i 's/ "15:set.net.access on"//'
  mutant tiles-forgotten     i 's/    steps+=("set.tile sduser \$tile off")/    :/'
  mutant any-schedule        i 's/  if \[\[ "\$sched" =~ \$sched_re \]\] \&\& /  if /'
  mutant control-chars       i 's/ \&\& \[\[ "\$cmd" =~ \$text_re \]\]//'
  mutant jobs-silent         i 's/^  "the kept definitions were NOT given their timers"\*) job_steps/  "never matches") job_steps/'
  mutant register-silent     i 's/^  "NOT carried"\*) switch_steps/  "never matches") switch_steps/'
  mutant count-is-success    s 's/if \[ -n "\$jr_n" \] \&\& \[ "\$jr_n" -eq "\$jr_total" \]; then/if [ -n "$jr_n" ]; then/'
  mutant names-not-said      s '/echo "solo-stage: job-not-restored: \$jr_name"/d'
  mutant ufw-failure-silent  i 's/|| fw_failed "\$what" "sudo ufw/|| : "$what" "sudo ufw/'
  mutant fwd-failure-silent  i 's/|| fw_failed "\$what" "sudo firewall-cmd/|| : "$what" "sudo firewall-cmd/'
  mutant deleter-no-block    r 's/^restore_warn_block "To correct.*$/:/'
  mutant deleter-joined      r 's/^    restore_warn "\$title" "remote.api \$a"$/    restore_warn "$title" "remote.api $a   and   remote.ssh $s"/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

for f in "$INSTALLER" "$REMOVER" "$STAGE"; do [ -r "$f" ] || { echo "test-install-restorewarn: CANNOT RUN - $f is not there"; exit 2; }; done
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
echo "installer : $INSTALLER"; echo "remover   : $REMOVER"; echo "stage     : $STAGE"
awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$INSTALLER" > "$T/inst-block.sh"
awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$REMOVER" > "$T/del-block.sh"
awk '/^# SOLO-STEPS-BEGIN$/,/^# SOLO-STEPS-END$/' "$INSTALLER" > "$T/steps.sh"
awk '/^  # JOBS-RESTORE-BEGIN$/,/^  # JOBS-RESTORE-END$/' "$STAGE" > "$T/stage.sh"
awk '/^# DOORS-NOTE-BEGIN$/,/^# DOORS-NOTE-END$/' "$REMOVER" > "$T/doors.sh"
for b in inst-block:restore_warn_block del-block:restore_warn_block steps:job_steps stage:jr_out doors:note_doors; do
  grep -q "${b#*:}" "$T/${b%%:*}.sh" || { echo "test-install-restorewarn: CANNOT RUN - no ${b%%:*} block"; exit 2; }
done
run_block() {   # run_block FILE 'script' -> output: the block under the installer's own options, then the script
  BLOCKFILE="$1" SCRIPT="$2" bash -c '
    set -euo pipefail
    . "$BLOCKFILE"
    eval "$SCRIPT"
  ' 2>&1
}
HOW='To correct, start SD Core Solo.'
HOWR='To correct, after the next install start SD Core Solo.'

row "B1 the two copies of the block (installer and remover) are byte for byte equal" "$(cmp -s "$T/inst-block.sh" "$T/del-block.sh" && echo 0 || echo 1)" "$(diff "$T/inst-block.sh" "$T/del-block.sh" | head -4)"
if [ -r "$CORE_INSTALLER" ]; then
  awk '/^# RESTORE-WARN-BEGIN$/,/^# RESTORE-WARN-END$/' "$CORE_INSTALLER" > "$T/core-block.sh"
  row "B2 the block equals SD Core's (one text for both products)" "$(cmp -s "$T/inst-block.sh" "$T/core-block.sh" && echo 0 || echo 1)" "$(diff "$T/inst-block.sh" "$T/core-block.sh" | head -4)"
else
  echo "  [SKIP] B2 SD Core's installer is not at $CORE_INSTALLER"
fi

out="$(run_block "$T/inst-block.sh" 'restore_warn_block "H"')"
row "F1 NULL CASE: no records, so the block prints NOTHING at all" "$([ -z "$out" ] && echo 0 || echo 1)" "[$out]"
out="$(HOW="$HOW" run_block "$T/inst-block.sh" '
restore_warn "ONE." "admin"
restore_warn "ONE." "set.pins on"
restore_warn "TWO." "admin"
restore_warn "ONE." "admin"
restore_warn_block "$HOW"; echo END')"
want="$(printf '%b' '\n\033[1;31mWARNING: SOME SETTINGS NEED TO BE FIXED.\n\n'\
"1. ONE.\n$HOW\nAt the colon prompt type:\n     admin\n     set.pins on\n\n2. TWO.\n$HOW\nAt the colon prompt type:\n     admin\n\n"\
'\033[0mEND')"
row "F2 the whole box, exactly: Windows' heading, one item per heading, the commands 5 spaces in and once each, bold red and a reset" "$([ "$out" = "$want" ] && echo 0 || echo 1)" "$(diff <(printf '%s\n' "$out") <(printf '%s\n' "$want") | head -8)"

steps() {   # steps HOME KEPT JOBS_STATE REG_STATE -> the lines to type, in order
  HOME_DIR="$1" reload_dir="$2" jobs_state="$3" reg_state="$4" WORK="$T/work" BL="$T/inst-block.sh" ST="$T/steps.sh" bash -c '
    set -euo pipefail
    . "$BL"; . "$ST"
    restore_warn_block H' 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | sed -n 's/^     //p'
}
reg() {   # reg FILE FIELD=VALUE...: a register record of 24 lines
  local f="$1" i kv v; shift; mkdir -p "$(dirname "$f")"; : > "$f"
  for i in $(seq 1 24); do v=""; for kv in "$@"; do if [ "${kv%%=*}" = "$i" ]; then v="${kv#*=}"; fi; done; echo "$v" >> "$f"; done
}
def() { mkdir -p "$(dirname "$1")"; printf '%s\n%s\n%s\n20000\n30000\n' "$2" "cal" "$3" > "$1"; }
mkdir -p "$T/work"; H="$T/h"; K="$T/k"; J="$H/\$jobs"
FAILEDJ="the kept definitions were NOT given their timers: x"
def "$J/nightly" "daily 02:30" 'backup.account all'
def "$J/often" "every 15 minutes" 'list voc "a b" | x'
def "$J/broken" "daily 25:00" 'who'
def "$J/ctl" "hourly" "$(printf 'who\033[2Jx')"
printf 'solo-stage: job-not-restored: %s\n' nightly often broken ctl Bad > "$T/work/stage.log"
reg "$H/accounts/sduser" 23=yes; reg "$K/accounts/sduser" 23=yes
want="set.job change nightly daily 02:30 backup.account all
set.job change often every 15 minutes list voc \"a b\" | x
set.job change broken <schedule> <command>
set.job change ctl <schedule> <command>
(a definition whose name is not plain: delete it from $J)"
out="$(steps "$H" "$K" "$FAILEDJ" "")"
row "S1 the jobs: set.job CHANGE with the schedule and the command as kept, one line each, and only what set.job accepts" "$([ "$out" = "$want" ] && echo 0 || echo 1)" "$out"
echo 'solo-stage: job-not-restored: nightly' > "$T/work/stage.log"
reg "$H/accounts/sduser"; reg "$K/accounts/sduser"
out="$(steps "$H" "$K" "$FAILEDJ" "")"
row "S2 the jobs switch off now and off before: admin, switch on, the job, switch off again" "$([ "$out" = "admin
set.jobs.access on
set.job change nightly daily 02:30 backup.account all
set.jobs.access off" ] && echo 0 || echo 1)" "$out"
reg "$K/accounts/sduser" 23=YES
out="$(steps "$H" "$K" "$FAILEDJ" "")"
row "S3 the jobs switch was on before: it is left on" "$([ "$out" = "admin
set.jobs.access on
set.job change nightly daily 02:30 backup.account all" ] && echo 0 || echo 1)" "$out"
: > "$T/work/stage.log"
out="$(steps "$H" "$K" "$FAILEDJ" "")"
row "S4 no job named by the stage: the page that lists them, as the administrator" "$([ "$out" = "admin
tool.jobs" ] && echo 0 || echo 1)" "$out"
reg "$K/accounts/sduser" 7=yes 8=YES 15=yes 17="ide sed" 18=yes 19=yes 20=yes 21=yes 22=yes 23=yes 24=yes
want="admin
set.os.access sh on
set.os.access os on
set.net.access on
set.pins on
set.recovery on
set.mcp on
set.mcp write on
set.xfer.access on
set.jobs.access on
set.stored.access on
set.tile sduser ide off
set.tile sduser sed off"
out="$(steps "$H" "$K" "" "NOT carried (x)")"
row "S5 a register not carried: each switch that was on, its own verb on a line of its own, after admin" "$([ "$out" = "$want" ] && echo 0 || echo 1)" "$out"
reg "$K/accounts/sduser"
out="$(steps "$H" "$K" "" "NOT carried (x)")"
row "S6 a register not carried that had no switch on, and a reload that worked: nothing to type" "$([ -z "$out" ] && [ -z "$(steps "$H" "$K" "4 job(s) given their timers again" "3 switch(es) carried")" ] && echo 0 || echo 1)" "$out"

stage() {   # stage WHAT_SET_JOB_RESTORE_SAID -> the stage's lines
  H="$T/sh" SAID="$1" ST="$T/stage.sh" bash -c '
    set -euo pipefail
    sdi() { printf "%s\n" "$SAID"; }
    . "$ST"' 2>&1
}
SJ="$T/sh/\$jobs"; def "$SJ/alpha" hourly who; def "$SJ/beta" hourly who
out="$(stage "2 job(s) given their timers again from the kept definitions")"
row "G1 the stage: every kept job counted is success, and none is named" "$([ "$out" = "solo-stage: jobs: 2 job(s) given their timers again from the kept definitions" ] && echo 0 || echo 1)" "$out"
out="$(stage "beta: systemd did not do it (status 1)
1 job(s) given their timers again from the kept definitions")"
row "G2 the stage: 1 of 2 is a FAILURE and names the job that failed, only it" "$(printf '%s\n' "$out" | grep -q '^solo-stage: jobs: the kept definitions were NOT given' && [ "$(printf '%s\n' "$out" | sed -n 's/^solo-stage: job-not-restored: //p')" = beta ] && echo 0 || echo 1)" "$out"
out="$(stage "Connection terminated")"
row "G3 the stage: no count at all names every kept job" "$([ "$(printf '%s\n' "$out" | sed -n 's/^solo-stage: job-not-restored: //p' | tr '\n' ,)" = "alpha,beta," ] && echo 0 || echo 1)" "$out"

mkdir -p "$T/units" "$T/ro"; chmod 555 "$T/ro"
printf 'ListenStream=0.0.0.0:4249\n' > "$T/units/sd-solo-api.socket"
out="$(BL="$T/del-block.sh" DN="$T/doors.sh" bash -c 'set -uo pipefail; say() { :; }; . "$BL"; . "$DN"; note_doors "$1" "$2"; restore_warn_block H' _ "$T/units" "$T/ro" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | sed -n 's/^     //p')"
chmod 755 "$T/ro"
row "D1 the remover: doors it could not note are admin, then one line for each door as it was" "$([ "$out" = "admin
remote.api open
remote.ssh off" ] && echo 0 || echo 1)" "$out"

# ---- the call sites, read as text ---------------------------------------------------------------------------------------------
l_ban="$(grep -n -x -F -m1 -- '  say "SD Core Solo for Linux is installed."' "$INSTALLER" | cut -d: -f1)"
l_call="$(grep -n -x -F -m1 -- "restore_warn_block \"$HOW\"" "$INSTALLER" | cut -d: -f1)"
row "T1 the install prints the box right under its banner" "$([ -n "$l_ban" ] && [ -n "$l_call" ] && [ "$l_ban" -lt "$l_call" ] && [ $((l_call - l_ban)) -le 4 ] && echo 0 || echo 1)" "banner $l_ban, call $l_call"
bad=""
for v in admin set.job set.os.access set.net.access set.pins set.recovery set.mcp set.xfer.access set.jobs.access set.stored.access set.tile remote.api remote.ssh tool.gates tool.jobs; do
  [ -f "$SYS/voc_template/$v" ] || [ -f "$SYS/newvoc/$v" ] || bad="$bad $v"
done
! grep -E '^[^#]*restore_warn "' "$INSTALLER" "$REMOVER" | grep -q -E 'set\.job restore|   and   |open\|local\|off[^>]' || bad="$bad a-refused-or-joined-line"
row "T2 every verb printed is in Solo's vocabulary; no set.job restore and no two commands on a line" "$([ -z "$bad" ] && echo 0 || echo 1)" "$bad"
fw="$(awk '/^fw_open\(\)/,/^}/' "$INSTALLER")"
row "T3 a firewall rule that fails (ufw or firewalld) gets Windows' warning with the terminal's command, under the box" \
  "$(printf '%s\n' "$fw" | grep -qF '|| fw_failed "$what" "sudo ufw allow $port/tcp"' && printf '%s\n' "$fw" | grep -qF '|| fw_failed "$what" "sudo firewall-cmd --permanent --add-port=$port/tcp && sudo firewall-cmd --reload"' && grep -qF 'WARNING: NO FIREWALL RULE LETS OTHER COMPUTERS REACH $name.' "$INSTALLER" && grep -q '^if \[ "${#fw_warns\[@\]}" -gt 0 \]; then printf' "$INSTALLER" && echo 0 || echo 1)"
l_done="$(grep -n -x -F -m1 'say "SOLO DELETE COMPLETE $H"' "$REMOVER" | cut -d: -f1)"; l_dblk="$(grep -n -x -F -m1 -- "restore_warn_block \"$HOWR\"" "$REMOVER" | cut -d: -f1)"
row "T4 the remover prints its box after 'SOLO DELETE COMPLETE' and says the steps are for after the next install" "$([ -n "$l_done" ] && [ -n "$l_dblk" ] && [ "$l_done" -lt "$l_dblk" ] && echo 0 || echo 1)" "complete $l_done, block $l_dblk"

echo
echo "test-install-restorewarn: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
