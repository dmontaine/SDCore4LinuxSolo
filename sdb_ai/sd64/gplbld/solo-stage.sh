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

# Everything this creates - and everything sd creates while it runs from here -
# is private to the user (files 0600, directories 0700): the tree is the user's
# own, and $cred holds the kept account password in clear (!SOLO_STORE_PW).
umask 077

# --account-password-file FILE: the account password, one line, printable ASCII
# (33-126).  For automation and tests; it goes to sd's INPUT, never a command
# line.  Without it no password is set and every session is refused (11020).
# --admin-password-file FILE: the same for the administrator password (ADMIN).
# Without it ADMIN answers 11007 and no administrator command can be unlocked.
# --global-password-file FILE: the global password - its presence IS managed mode
# (ruling 15).  Set AFTER the account password so the two records share a salt
# (!CRED_SET's partner rule, ruling 19); it must differ from the account password.
pwfile=""
adminfile=""
globalfile=""
usage="usage: bash $0 [--account-password-file FILE] [--admin-password-file FILE] [--global-password-file FILE] HOME_DIR"
while [ "${1:-}" = "--account-password-file" ] || [ "${1:-}" = "--admin-password-file" ] || [ "${1:-}" = "--global-password-file" ]; do
  [ "$#" -ge 3 ] || refuse "$usage"
  f="$2"
  [ -r "$f" ] || refuse "cannot read the password file $f"
  [ -s "$f" ] || refuse "the password file $f is empty"
  case "$1" in
    --account-password-file) pwfile="$f" ;;
    --admin-password-file)   adminfile="$f" ;;
    --global-password-file)  globalfile="$f" ;;
  esac
  shift 2
done
if [ -n "$globalfile" ] && [ -z "$pwfile" ]; then
  refuse "--global-password-file needs --account-password-file: the two share a salt, so the account's is set first"
fi
[ "$#" -eq 1 ] || refuse "$usage"
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
# The audit trail (K$AUDIT appends to it; it is not created on demand).  The
# parent made it append-only with chattr +a, which needs root; Solo cannot, so
# the user who owns the tree can edit it - say so in the docs.
: > "$H/audit"
mkdir -p "$H/user_accounts" "$H/group_accounts" "$H/gplbld"
mkdir -p "$H/\$cred"           # the credential register: SCRAM verifiers, $STORED
chmod 700 "$H/\$cred"
echo "  credential register: $(stat -c '%U %a' "$H/\$cred")"

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

# THE INTERNAL DOOR IS ONE-SHOT (ruling 13): "sd -internal" is admitted only against a
# fresh marker file $internal in the tree, which LOGIN deletes on admission.  So a
# marker is written immediately before EVERY internal session - and only these.  sdi
# is "sd -internal" with that marker; run_step does the same for any command it is
# given that contains -internal.
write_marker() { printf 'solo-stage pid=%s %s\n' "$$" "$(date -Is)" > "$H/\$internal"; }
sdi() { write_marker; "$SD" -internal "$@"; }

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
  case " $* " in *" -internal "*) write_marker ;; esac
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
out="$(sdi RUN gpl.bp write_install_dicts NO.PAGE 2>&1)" || true
printf '%s\n' "$out"
plain="$(printf '%s\n' "$out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
bad="$(printf '%s\n' "$plain" | grep -E 'ERROR OPENING|PROCESS ABORTED|READLIST EMPTY|NO DIRECTORY RECORDS FOUND|CANNOT READ TRANSFER_FILE|ERROR CANNOT OPEN|Invalid runfile|requires administrator' || true)"
if [ -n "$bad" ] || ! printf '%s\n' "$plain" | grep -qx '[[:space:]]*COMPLETE[[:space:]]*'; then
  fail "pass 3: no COMPLETE line, or it said: ${bad:-nothing matched}"
fi

run_step "Compiling C and I type dictionaries" "$SD" -internal THIRD.COMPILE

echo
echo "Creating the one account ($SD -internal RUN gpl.bp solo_account)"
acct_out="$(sdi RUN gpl.bp solo_account 2>&1)" || true
printf '%s\n' "$acct_out"
acct_plain="$(printf '%s\n' "$acct_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
printf '%s\n' "$acct_plain" | grep -qE '^SOLO ACCOUNT READY sduser ' || fail "solo_account did not print 'SOLO ACCOUNT READY sduser'"
[ -d "$H/user_accounts/sduser" ] || fail "solo_account said READY but $H/user_accounts/sduser is not there"

if [ -n "$pwfile" ]; then
  echo
  echo "Setting the account password (cat $pwfile | $SD -internal RUN gpl.bp solo_password ACCOUNT sduser)"
# A PIPE, NOT "< FILE": measured 29 Sep 2026, sd ends the session ("Process
# terminated") at the first INPUT when its standard input is a redirected
# regular file, and reads the same bytes from a pipe.
  pw_out="$(write_marker; cat "$pwfile" | "$SD" -internal RUN gpl.bp solo_password ACCOUNT sduser 2>&1)" || true
  pw_plain="$(printf '%s\n' "$pw_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$pw_plain" | tail -3
  printf '%s\n' "$pw_plain" | grep -qx 'SOLO PASSWORD SET ACCOUNT' || fail "solo_password did not print 'SOLO PASSWORD SET ACCOUNT'"
  printf '%s\n' "$pw_plain" | grep -q 'solo_password:' && fail "solo_password said: $(printf '%s\n' "$pw_plain" | grep 'solo_password:' | head -1)"
  echo "  credential register now holds: $(ls "$H/\$cred" | tr '\n' ' ')"
else
  echo
  echo "NOTE: no --account-password-file, so NO PASSWORD IS SET and every session will be refused (11020)."
fi

if [ -n "$adminfile" ]; then
  echo
  echo "Setting the administrator password (cat $adminfile | $SD -internal RUN gpl.bp solo_password ADMIN)"
  ad_out="$(write_marker; cat "$adminfile" | "$SD" -internal RUN gpl.bp solo_password ADMIN 2>&1)" || true
  ad_plain="$(printf '%s\n' "$ad_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$ad_plain" | tail -3
  printf '%s\n' "$ad_plain" | grep -qx 'SOLO PASSWORD SET ADMIN' || fail "solo_password did not print 'SOLO PASSWORD SET ADMIN'"
  printf '%s\n' "$ad_plain" | grep -q 'solo_password:' && fail "solo_password said: $(printf '%s\n' "$ad_plain" | grep 'solo_password:' | head -1)"
else
  echo
  echo "NOTE: no --admin-password-file, so ADMIN cannot be unlocked (11007)."
fi

if [ -n "$globalfile" ]; then
  echo
  echo "Setting the global password - MANAGED MODE (cat $globalfile | $SD -internal RUN gpl.bp solo_password GLOBAL)"
  gl_out="$(write_marker; cat "$globalfile" | "$SD" -internal RUN gpl.bp solo_password GLOBAL 2>&1)" || true
  gl_plain="$(printf '%s\n' "$gl_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$gl_plain" | tail -3
  printf '%s\n' "$gl_plain" | grep -qx 'SOLO PASSWORD SET GLOBAL' || fail "solo_password did not print 'SOLO PASSWORD SET GLOBAL'"
  printf '%s\n' "$gl_plain" | grep -q 'solo_password:' && fail "solo_password said: $(printf '%s\n' "$gl_plain" | grep 'solo_password:' | head -1)"
  # The two records must share a salt or the master cannot log in (ruling 19).
  s_acc="$(sed -n 3p "$H/\$cred/sduser")"; s_glb="$(sed -n 3p "$H/\$cred/\$global")"
  [ -n "$s_acc" ] && [ "$s_acc" = "$s_glb" ] || fail "sduser and \$global do not share a salt ('$s_acc' / '$s_glb')"
  echo "  the account and global records share a salt"
fi

echo
echo "solo-stage: bootstrap passes 1-3, THIRD.COMPILE and the account completed in $H"
echo "  SD is running from $H; stop it with: $SD -stop"
