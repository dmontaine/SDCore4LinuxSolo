#!/bin/bash
# solo-stage.sh - lay out an SD Core for Linux Solo tree and run the bootstrap.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-stage.sh HOME_DIR
#
# No sudo, no root, no operating-system user: everything is done as the person
# running it, into HOME_DIR, which must not exist or must be empty.  Run it from
# anywhere; it finds the source tree from its own location.  Build first:
#   cd /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64 && make
#
# THIS IS THE STAGING HALF OF THE SOLO INSTALLER (LSOLO 9), written first so the
# BASIC system programs can be compiled and run before the installer exists.  It
# copies what the parent's installsdai.sh copied (lines 722-770 there) and runs
# its bootstrap passes 1-3 (1079-1200), minus everything about users, groups,
# sudo, /etc and systemd.  The account, the passwords and the service are NOT
# here yet.
#
# LAYOUT.  HOME_DIR is both the Solo home and the SDSYS directory (the C code
# finds <sysdir>/bin/sd and <sysdir>/bin/pcode - see gplsrc/config.c):
#   HOME_DIR/bin/sd ...           programs, and bin/pcode built below
#   HOME_DIR/sd.conf              beside bin's parent, found by inipath.c
#   HOME_DIR/.sdcoresolo          the marker inipath.c insists on
#   HOME_DIR/user_accounts/       the account folders
#   HOME_DIR/{gcat,voc,...}       the SDSYS files
#
# EVERY STEP PRINTS WHAT IT RAN AND THE RESULT IS JUDGED ON WHAT THE PROGRAM
# SAID, NOT ON ITS EXIT CODE (sd exits 0 when the command it was given never
# ran - the parent's S.48).  It stops at the first failure and says which.
#
# Exit 0 the bootstrap completed, 1 a step failed, 2 refused to start.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sd64="$(dirname "$here")"

refuse() { echo "REFUSED: $*" >&2; exit 2; }
fail()   { echo "FAILED at: $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; Solo never runs as root"
[ "$#" -eq 1 ] || refuse "usage: bash $0 HOME_DIR"
H="$1"
case "$H" in
  /*) ;;
  *) refuse "HOME_DIR must be an absolute path (got '$H')" ;;
esac
if [ -e "$H" ] && [ -n "$(ls -A "$H" 2>/dev/null)" ]; then
  refuse "$H exists and is not empty; remove it yourself (this script never deletes)"
fi
for f in bin/sd bin/sdlnxd bin/sdtic sdsys gplbld/bbcmp.py gplbld/pcode_bld.py sd.conf; do
  [ -e "$sd64/$f" ] || refuse "$sd64/$f is missing - run make in $sd64 first"
done
command -v python3 >/dev/null || refuse "python3 is required"

echo "solo-stage inputs:"
echo "  source tree : $sd64"
echo "  HOME_DIR    : $H"
echo "  running as  : $(id -un) (uid $(id -u))"

mkdir -p "$H"
cd "$sd64"

# ---- the SDSYS files, then the empty places the parent's installer touched.
cp -R sdsys/. "$H/"
touch "$H/gcat/\$CPROC"        # fool sd's vm into thinking gcat is populated
touch "$H/errlog"
mkdir -p "$H/user_accounts" "$H/group_accounts" "$H/gplbld"

# ---- programs and what the bootstrap compiles from.
cp -R bin "$H/bin"
cp -R gplsrc "$H/gplsrc"
cp -R gplobj "$H/gplobj"
cp -R gplbld/FILES_DICTS "$H/gplbld/FILES_DICTS"
cp -R terminfo "$H/terminfo"
cp Makefile gpl.src terminfo.src "$H/"
cp sd.conf "$H/sd.conf"
: > "$H/.sdcoresolo"

# ---- program objects for the bootstrap, and the pcode file.
echo "building the bootstrap objects"
python3 gplbld/bbcmp.py "$H" gpl.bp/bbproc gpl.bp.out/bbproc
python3 gplbld/bbcmp.py "$H" gpl.bp/bcomp gpl.bp.out/bcomp
python3 gplbld/bbcmp.py "$H" gpl.bp/pathtkn gpl.bp.out/pathtkn
python3 gplbld/pcode_bld.py "$H"
[ -s "$H/bin/pcode" ] || fail "pcode_bld.py wrote no $H/bin/pcode"

SD="$H/bin/sd"
cd "$H"

echo
echo "Starting SD ($SD -start)"
"$SD" -stop >/dev/null 2>&1 || true
"$SD" -start || fail "$SD -start"

# run_step LABEL COMMAND... - run one sd step, print its whole output, and
# refuse on failure WORDING, because sd's exit code is not evidence (it exits 0
# when the command never ran, and did so for both a refusal and a crash here).
# Success wording for -i and SECOND.COMPILE is NOT anchored: it has not been
# read from a clean run yet, so a step that prints none of these but did
# nothing would pass.  Pass 3 below is anchored on COMPLETE.
run_step() {
  local label="$1"; shift
  local o rc=0 plain badw
  echo
  echo "$label ($*)"
  o="$("$@" 2>&1)" || rc=$?
  printf '%s\n' "$o"
  plain="$(printf '%s\n' "$o" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  badw="$(printf '%s\n' "$plain" | grep -i -E 'requires administrator|Unable to load|Segmentation|core dumped|System Already Installed|compilation (failed|aborted)|error[s]? (found|in)|[1-9][0-9]* error\(s\)|not registered|Connection terminated|not allowed|restricted to|Unrecognised|cannot open|not found' || true)"
  [ "$rc" -eq 0 ] || fail "$label: exit code $rc"
  [ -z "$badw" ] || fail "$label said: $badw"
}

run_step "Bootstrap pass 1" "$SD" -i
run_step "Bootstrap pass 2" "$SD" -internal SECOND.COMPILE

# Steps from here run through the INTERNAL door (-internal), not as a session in
# the account: the account does not exist until solo_account below, and in Solo
# nobody but the installer lands in SDSYS.
echo
echo "Bootstrap pass 3 ($SD -internal RUN gpl.bp write_install_dicts NO.PAGE)"
out="$("$SD" -internal RUN gpl.bp write_install_dicts NO.PAGE 2>&1)" || true
printf '%s\n' "$out"
plain="$(printf '%s\n' "$out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
bad="$(printf '%s\n' "$plain" | grep -E 'ERROR OPENING|PROCESS ABORTED|READLIST EMPTY|NO DIRECTORY RECORDS FOUND|CANNOT READ TRANSFER_FILE|ERROR CANNOT OPEN|Invalid runfile|requires administrator' || true)"
if [ -n "$bad" ] || ! printf '%s\n' "$plain" | grep -qx '[[:space:]]*COMPLETE[[:space:]]*'; then
  fail "pass 3: no COMPLETE line, or it said: ${bad:-nothing matched}"
fi

run_step "Compiling C and I type dictionaries" "$SD" -internal THIRD.COMPILE

echo
echo "Creating the one account ($SD -internal RUN gpl.bp solo_account)"
acct_out="$("$SD" -internal RUN gpl.bp solo_account 2>&1)" || true
printf '%s\n' "$acct_out"
acct_plain="$(printf '%s\n' "$acct_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
printf '%s\n' "$acct_plain" | grep -qE '^SOLO ACCOUNT READY sduser ' || fail "solo_account did not print 'SOLO ACCOUNT READY sduser'"
[ -d "$H/user_accounts/sduser" ] || fail "solo_account said READY but $H/user_accounts/sduser is not there"

echo
echo "solo-stage: bootstrap passes 1-3, THIRD.COMPILE and the account completed in $H"
echo "  SD is running from $H; stop it with: $SD -stop"
