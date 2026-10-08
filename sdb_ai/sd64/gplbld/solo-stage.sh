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
# finds <sysdir>/bin/sd-solo and <sysdir>/bin/pcode - see gplsrc/config.c):
#   HOME_DIR/bin/sd-solo ...           programs, and bin/pcode built below
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
# --deny-verbs LIST: the verbs denied to the local user (ruling 34), a comma
# separated list; set with DENY.VERBS SET, which normalises each name and drops
# ADMIN, OFF, QUIT and LO.  Not a secret; only verb-name characters and commas.
pwfile=""
adminfile=""
globalfile=""
denyverbs=""
# --upgrade (LSOLO 13): HOME_DIR is an EXISTING Solo tree; replace its programs and
# system objects, keep the account, its data, the passwords, sd.conf, the audit
# trail, GLOBAL.BP.OUT and the deny list, run the bootstrap over it, refresh the
# account's VOC (UPDATE.ACCOUNTS ALL) and re-sync the global catalogue.  A full
# copy of the tree is made first and put back if any step fails.  Takes no
# password and no --deny-verbs: nothing about the credentials changes.
upgrade=0
# --reload-data DIR (LSOLO 39, owner 6 Oct 2026): DIR is a KEPT TREE, what deletesdsolo.sh --keep-data
# leaves (user_accounts/sduser and, if it was there, sd.conf), moved aside by the installer so
# HOME_DIR could be made.  After the account and its passwords exist, the new account's files are
# replaced by the kept ones, the kept sd.conf replaces the default (and is put back if SD will not
# start with it), and the account's VOC is refreshed as an upgrade does.  DIR is only read: it is
# copied, never moved.  Fresh stages only: an upgrade already keeps both.
reloaddir=""
usage="usage: bash $0 [--account-password-file FILE] [--admin-password-file FILE] [--global-password-file FILE] [--deny-verbs LIST] [--reload-data DIR] HOME_DIR
       bash $0 --upgrade HOME_DIR"
while [ "${1:-}" = "--account-password-file" ] || [ "${1:-}" = "--admin-password-file" ] || [ "${1:-}" = "--global-password-file" ] || [ "${1:-}" = "--deny-verbs" ] || [ "${1:-}" = "--reload-data" ] || [ "${1:-}" = "--upgrade" ]; do
  if [ "$1" = "--upgrade" ]; then upgrade=1; shift; continue; fi
  [ "$#" -ge 3 ] || refuse "$usage"
  if [ "$1" = "--reload-data" ]; then reloaddir="$2"; shift 2; continue; fi
  if [ "$1" = "--deny-verbs" ]; then
    case "$2" in
      *[!A-Za-z0-9.\$_,\ -]*) refuse "--deny-verbs holds a character that cannot be in a verb name" ;;
    esac
    denyverbs="$(printf '%s' "$2" | tr -d ' ')"
    shift 2
    continue
  fi
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
# LSOLO 14 (Windows Solo SOLO 18): a managed tree may be staged with NO account
# password.  LOGIN then has the user choose it at the console on first login, and
# !CRED_SET takes $global's salt for the new record, so the master still logs in.
[ "$#" -eq 1 ] || refuse "$usage"
if [ -n "$reloaddir" ]; then
  [ "$upgrade" -eq 0 ] || refuse "--reload-data is for a new install: an upgrade keeps the account and sd.conf as they are"
  case "$reloaddir" in /*) ;; *) refuse "--reload-data must be an absolute path (got '$reloaddir')" ;; esac
  [ -d "$reloaddir/user_accounts/sduser/voc" ] || refuse "--reload-data: $reloaddir holds no kept account (no user_accounts/sduser/voc): it is not what deletesdsolo.sh --keep-data leaves"
  [ ! -L "$reloaddir" ] && [ ! -L "$reloaddir/user_accounts" ] && [ ! -L "$reloaddir/user_accounts/sduser" ] || refuse "--reload-data: $reloaddir or its account folder is a symbolic link; give the real directory"
fi
H="$1"
case "$H" in
  /*) ;;
  *) refuse "HOME_DIR must be an absolute path (got '$H')" ;;
esac
if [ "$upgrade" -eq 1 ]; then
  [ -z "$pwfile$adminfile$globalfile$denyverbs" ] || refuse "--upgrade takes no password file and no --deny-verbs: the credentials and the deny list are kept as they are"
  [ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not an SD Core for Linux Solo tree, nothing to upgrade"
  # 02 Oct 26 - the server's file name is sd-solo; a tree installed before that still has bin/sd.
  [ -x "$H/bin/sd-solo" ] || [ -x "$H/bin/sd" ] || refuse "$H/bin/sd-solo is not there (nor the old bin/sd) - the tree is damaged; reinstall"
  [ -d "$H/user_accounts/sduser" ] || refuse "$H/user_accounts/sduser is not there - the tree is damaged; reinstall"
elif [ -e "$H" ] && [ -n "$(ls -A "$H" 2>/dev/null)" ]; then
  refuse "$H exists and is not empty; remove it yourself (this script never deletes)"
fi
for f in bin/sd-solo bin/sdlnxd bin/sdtic sdsys gplbld/bbcmp.py gplbld/pcode_bld.py sd.conf; do
  [ -e "$sd64/$f" ] || refuse "$sd64/$f is missing - run make in $sd64 first"
done
command -v python3 >/dev/null || refuse "python3 is required"

echo "solo-stage inputs:"
echo "  source tree : $sd64"
echo "  HOME_DIR    : $H"
echo "  running as  : $(id -un) (uid $(id -u))"

UPGRADE_BACKUP=""
upgrade_ok=0
if [ "$upgrade" -eq 1 ]; then
  # Stop the OLD daemon with the OLD binary, then take the safety copy.  The copy
  # is of everything, data included: a step that fails halfway through the
  # bootstrap can leave SDSYS's own files half-replaced, and only a whole copy
  # puts that right.  It is kept after a good upgrade too (the installer says
  # where); the user deletes it.
  # stop_any stops with whichever name the tree has: sd-solo, or bin/sd on a tree installed
  # before the rename (the new name alone would stop nothing and leave the daemon running).
  stop_any() { local n; for n in sd-solo sd; do if [ -x "$H/bin/$n" ]; then "$H/bin/$n" -stop >/dev/null 2>&1 || true; fi; done; return 0; }
  echo "stopping the running SD ($H/bin/sd-solo -stop, or the old $H/bin/sd -stop)"
  stop_any
  sleep 1
  if [ -e "$H/\$internal" ]; then rm -f "$H/\$internal"; fi
  UPGRADE_BACKUP="$H.before-upgrade-$(date +%Y%m%d%H%M%S)"
  [ ! -e "$UPGRADE_BACKUP" ] || refuse "$UPGRADE_BACKUP already exists"
  echo "safety copy: $UPGRADE_BACKUP"
  cp -a "$H" "$UPGRADE_BACKUP" || { rm -rf "$UPGRADE_BACKUP"; refuse "could not make the safety copy (disk full?); the tree is unchanged"; }
  put_back() {
    if [ "$upgrade_ok" -eq 0 ] && [ -n "$UPGRADE_BACKUP" ] && [ -d "$UPGRADE_BACKUP" ]; then
      echo "UPGRADE FAILED - putting the tree back from $UPGRADE_BACKUP" >&2
      stop_any
      rm -rf "$H" && mv "$UPGRADE_BACKUP" "$H" && echo "the tree is as it was before the upgrade" >&2
    fi
  }
  trap put_back EXIT
  # What is replaced is code and shipped system objects only.  Nothing below names
  # user_accounts, \$cred, audit, errlog, global.bp.out, solo.policy, sd.conf,
  # sd-tls or the account register's sduser file.
  rm -rf "$H/bin" "$H/gplsrc" "$H/gplobj" "$H/terminfo" "$H/microcfg" "$H/nanocfg" "$H/gplbld/FILES_DICTS" "$H/tools"
  # The bootstrap refuses a tree whose gpl.bp.out already holds LOGIN ("System
  # Already Installed?", bbproc) and re-creates SDSYS's own VOC, so the objects and
  # SDSYS's VOC - system files, rebuilt from the release's sources and templates -
  # go too.  No account file is among them: an account has its own voc.
  # Likewise the files bbproc's create.file makes (it stops on one that exists):
  # SDSYS's VOC and the dictionaries and work files of the system account.
  rm -rf "$H/gpl.bp.out" "$H/voc" "$H/voc.dic" "$H/accounts.dic" "$H/\$hold.dic" \
         "$H/\$map" "$H/\$map.dic" "$H/\$ipc" "$H/dict.dic" "$H/dir_dict"
  # RETIRED FILES (LSOLO 30, 3 Oct 2026).  The overlay below ("cp -R sdsys/. $H/") only adds
  # and replaces, so a file a release stops shipping would stay in the tree - and be compiled
  # and catalogued again, or (the VOC templates) copied back into the account's VOC by
  # UPDATE.ACCOUNTS.  A file removed from sdsys/ in a release goes on this list in the same
  # commit; gplbld/test-retired-units.py checks that none is still shipped.
  # LS1.1-3: the LOGTO verb (its two VOC records) and the helpers only it and the dead
  # SDLocal login used.
  for f in gpl.bp/is_grp_member gpl.bp/euid_set gpl.bp/euid_restore voc_template/logto newvoc/logto; do
    rm -f "$H/$f"
  done
fi

mkdir -p "$H"
cd "$sd64"

# ---- the SDSYS files, then the empty places the parent's installer touched.
cp -R sdsys/. "$H/"
touch "$H/gcat/\$cproc"        # fool sd's vm into thinking gcat is populated (lower case since LSOLO 43: that is what config.c looks for)
touch "$H/errlog"
# The audit trail (K$AUDIT appends to it; it is not created on demand).  The
# parent made it append-only with chattr +a, which needs root; Solo cannot, so
# the user who owns the tree can edit it - say so in the docs.
[ "$upgrade" -eq 1 ] && [ -f "$H/audit" ] || : > "$H/audit"
mkdir -p "$H/user_accounts" "$H/group_accounts" "$H/gplbld"
# LSOLO 12 (rulings 33, 34, 36): the SD Core server's compiled programs (managed
# mode; starts empty) and the deny-verbs list's directory.  Both belong to the
# server: SD refuses a user program's write to either (op_dio3.c).
mkdir -p "$H/global.bp.out" "$H/solo.policy"
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
# The MICRO verb copies its SD BASIC syntax file from <sdsys>/microcfg on first use.
cp -R gplbld/microcfg "$H/microcfg"
# LSOLO 16: the NANO verb's syntax file and the script that writes its --rcfile.
cp -R gplbld/nanocfg "$H/nanocfg"
# The scripts a user needs AFTER the install: stop/start the service, add an ssh key,
# uninstall.  deletesdsolo.sh is at the repository root (beside the installer), two
# levels above this tree's sd64; it is copied when it is there (an installed tree
# built from a clone always has it).
mkdir -p "$H/tools"
cp gplbld/solo-service.sh gplbld/solo-ssh.sh gplbld/solo-sshguard.py "$H/tools/"   # sshguard: the ssh lockout, LSOLO 29
# 02 Oct 26 - LSOLO 20 (S.50): BACKUP.ACCOUNT / RESTORE.ACCOUNT's archive tool, in
# bin beside sd, which runs it: the helpers name <sysdir>/bin/sd-accarchive and
# start_sd() runs "sd-accarchive swap" to put a waiting restore in place.
cp gplbld/sd-accarchive "$H/bin/sd-accarchive"
chmod 0755 "$H/bin/sd-accarchive"
[ -f ../../deletesdsolo.sh ] && cp ../../deletesdsolo.sh "$H/tools/deletesdsolo.sh"
[ "$upgrade" -eq 1 ] && [ -f "$H/sd.conf" ] || cp sd.conf "$H/sd.conf"   # an upgrade keeps the user's
: > "$H/.sdcoresolo"

# ---- program objects for the bootstrap, and the pcode file.
echo "building the bootstrap objects"
python3 gplbld/bbcmp.py "$H" gpl.bp/bbproc gpl.bp.out/bbproc
python3 gplbld/bbcmp.py "$H" gpl.bp/bcomp gpl.bp.out/bcomp
python3 gplbld/bbcmp.py "$H" gpl.bp/pathtkn gpl.bp.out/pathtkn
python3 gplbld/pcode_bld.py "$H"
[ -s "$H/bin/pcode" ] || fail "pcode_bld.py wrote no $H/bin/pcode"

SD="$H/bin/sd-solo"
cd "$H"

# THE INTERNAL DOOR IS ONE-SHOT (ruling 13): "sd -internal" is admitted only against a
# fresh marker file $internal in the tree, which LOGIN deletes on admission.  So a
# marker is written immediately before EVERY internal session - and only these.  sdi
# is "sd -internal" with that marker; run_step does the same for any command it is
# given that contains -internal.
write_marker() { printf 'solo-stage pid=%s %s\n' "$$" "$(date -Is)" > "$H/\$internal"; }
sdi() { write_marker; "$SD" -internal "$@"; }

# 07 Oct 26 (LSOLO 43, the full product's PAL-1 D2 walk).  THE KEPT ACCOUNT'S FILES ARE MADE CASE
# INSENSITIVE.  The kernel now makes every NEW file so, but an upgrade or a reload keeps the old
# ones, built case sensitive.  upgrade_nocase reads every file first and rebuilds only those proven
# to hold no two ids that differ only by case; a file that holds a pair is left as it was and named.
# It also makes the private catalogue's names lower case (cat/ZZSUB -> cat/zzsub), which PAL-1
# stage 3a needs on ext4.  A WARNING about a pair is not a failure; a run that did not reach
# COMPLETE is said, and the stage goes on, because an unconverted file works as it did.
convert_nocase() {
  local nc_out nc_plain
  echo
  echo "Making the kept account's files case insensitive ($SD -internal RUN gpl.bp upgrade_nocase)"
  nc_out="$(sdi RUN gpl.bp upgrade_nocase 2>&1)" || true
  printf '%s\n' "$nc_out"
  nc_plain="$(printf '%s\n' "$nc_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  if ! printf '%s\n' "$nc_plain" | grep -qx '[[:space:]]*COMPLETE[[:space:]]*'; then
    echo "WARNING: the case-insensitive conversion of the kept account did not finish."
    echo "  Nothing was lost: a file that was not converted works as it did."
  fi
}

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

if [ "$upgrade" -eq 1 ]; then
  # LSOLO 13.  The account, its data and every password are kept.  What the new
  # release changes in the account's own files - its VOC, from the shipped
  # vocabulary - is refreshed the way Windows Solo's upgrade does it.
  echo
  echo "Refreshing the account's VOC ($SD -internal UPDATE.ACCOUNTS ALL)"
  ua_out="$(sdi UPDATE.ACCOUNTS ALL 2>&1)" || true
  ua_plain="$(printf '%s\n' "$ua_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$ua_plain" | tail -4
  printf '%s\n' "$ua_plain" | grep -qx '1 account(s) had their VOC updated from the shipped vocabulary.' \
    || fail "UPDATE.ACCOUNTS ALL did not print '1 account(s) had their VOC updated ...'"
  printf '%s\n' "$ua_plain" | grep -q 'requires administrator\|Cannot update every' && fail "UPDATE.ACCOUNTS ALL was refused"
  convert_nocase
else
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
  if [ -n "$pwfile" ]; then
    s_acc="$(sed -n 3p "$H/\$cred/sduser")"; s_glb="$(sed -n 3p "$H/\$cred/\$global")"
    [ -n "$s_acc" ] && [ "$s_acc" = "$s_glb" ] || fail "sduser and \$global do not share a salt ('$s_acc' / '$s_glb')"
    echo "  the account and global records share a salt"
  else
    [ ! -e "$H/\$cred/sduser" ] || fail "no account password was given but \$cred/sduser exists"
    echo "  no account password yet: the user sets it at the console on first login (11025)"
  fi
fi
fi   # end of "not an upgrade"

if [ -n "$denyverbs" ]; then
  echo
  echo "Setting the denied verbs ($SD -internal DENY.VERBS SET $denyverbs)"
  dv_out="$(sdi DENY.VERBS SET "$denyverbs" 2>&1)" || true
  dv_plain="$(printf '%s\n' "$dv_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$dv_plain" | tail -4
  printf '%s\n' "$dv_plain" | grep -q 'is not a verb name\|DENY.VERBS: cannot open\|can only be listed' && fail "DENY.VERBS refused: $(printf '%s\n' "$dv_plain" | tail -2)"
  printf '%s\n' "$dv_plain" | grep -qE '^DENY\.VERBS [0-9]+: ' || fail "DENY.VERBS did not print its 'DENY.VERBS <n>:' line"
fi

# Ruling 33: the SD Core server's programs in GLOBAL.BP.OUT go into the global
# catalogue, last, whether or not there is a global password (without one it says so and succeeds).
echo
echo "Syncing the global catalogue ($SD -internal SYNC.GLOBAL.CATALOG)"
sg_out="$(sdi SYNC.GLOBAL.CATALOG 2>&1)" || true
sg_plain="$(printf '%s\n' "$sg_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
printf '%s\n' "$sg_plain" | tail -3
printf '%s\n' "$sg_plain" | grep -qE '^SYNC GLOBAL CATALOG DONE [0-9]+ catalogued [0-9]+ removed 0 refused[[:space:]]*$' \
  || fail "SYNC.GLOBAL.CATALOG did not print its DONE line with 0 refused"
# LSOLO 38: a fresh stage with no global password must SAY so in the new words (and a managed one must not).
if [ "$upgrade" -eq 0 ]; then
  nogp='sync.global.catalog: this computer has no global password, so no SD Core server manages it and there is nothing to manage.'
  if [ -z "$globalfile" ]; then
    printf '%s\n' "$sg_plain" | grep -qF "$nogp" || fail "SYNC.GLOBAL.CATALOG did not say that this computer has no global password (got: $(printf '%s\n' "$sg_plain" | tail -2 | tr '\n' '|'))"
  else
    ! printf '%s\n' "$sg_plain" | grep -qF 'has no global password' || fail "SYNC.GLOBAL.CATALOG said there is no global password on a tree that has one"
  fi
fi

# LSOLO 39: reload what deletesdsolo.sh --keep-data saved.  The account and its passwords exist
# by now, so nothing in the new account's files is the user's: they are replaced whole by the
# saved copy.  The saved sd.conf replaces the default; SD is started on it, and if SD refuses it
# (an item this release no longer knows) the default is put back and that is said - the saved
# copy is never touched, so it can be corrected and loaded by hand.  Then the account's VOC is
# refreshed the way an upgrade does it, because the saved account may be from an older release.
reload_conf="none was saved"
if [ -n "$reloaddir" ]; then
  echo
  echo "Reloading the saved data and configuration from $reloaddir"
  "$SD" -stop >/dev/null 2>&1 || true
  rm -rf "$H/user_accounts/sduser" || fail "removing the new account's files before the reload"
  cp -a "$reloaddir/user_accounts/sduser" "$H/user_accounts/sduser" || fail "copying the kept account into $H/user_accounts"
  chmod -R go-rwx "$H/user_accounts/sduser"
  [ -d "$H/user_accounts/sduser/voc" ] || fail "the reloaded account has no voc"
  if [ -f "$reloaddir/sd.conf" ]; then
    cp "$H/sd.conf" "$H/sd.conf.default" || fail "keeping the default sd.conf"
    cp "$reloaddir/sd.conf" "$H/sd.conf" && chmod 600 "$H/sd.conf" || fail "copying the saved sd.conf"
    if "$SD" -start > "$H/.reload-start.log" 2>&1; then
      reload_conf="reloaded"
    else
      reload_conf="NOT accepted by SD, the default was kept ($(tr '\n' ' ' < "$H/.reload-start.log" | cut -c1-160))"
      echo "the saved sd.conf was not accepted: $(tr '\n' ' ' < "$H/.reload-start.log" | cut -c1-200)"
      cp "$H/sd.conf.default" "$H/sd.conf"
      "$SD" -stop >/dev/null 2>&1 || true
    fi
    rm -f "$H/sd.conf.default" "$H/.reload-start.log"
  fi
  "$SD" -stop >/dev/null 2>&1 || true
  "$SD" -start || fail "$SD -start after the reload"
  echo "Refreshing the reloaded account's VOC ($SD -internal UPDATE.ACCOUNTS ALL)"
  ua_out="$(sdi UPDATE.ACCOUNTS ALL 2>&1)" || true
  ua_plain="$(printf '%s\n' "$ua_out" | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
  printf '%s\n' "$ua_plain" | tail -4
  printf '%s\n' "$ua_plain" | grep -qx '1 account(s) had their VOC updated from the shipped vocabulary.' \
    || fail "after the reload, UPDATE.ACCOUNTS ALL did not print '1 account(s) had their VOC updated ...'"
  convert_nocase
  echo "SOLO RELOAD DONE data=reloaded config=$reload_conf"
fi

upgrade_ok=1
if [ "$upgrade" -eq 1 ]; then
  echo
  echo "solo-stage: UPGRADE COMPLETE in $H"
  echo "  the safety copy of the tree as it was is $UPGRADE_BACKUP (delete it when you are satisfied)"
  echo "$UPGRADE_BACKUP" > "$H/.last-upgrade-backup"
  "$SD" -stop >/dev/null 2>&1 || true
  exit 0
fi
echo
echo "solo-stage: bootstrap passes 1-3, THIRD.COMPILE and the account completed in $H"
echo "  SD is running from $H; stop it with: $SD -stop"
