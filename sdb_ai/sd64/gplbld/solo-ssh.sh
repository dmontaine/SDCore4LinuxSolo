#!/bin/bash
# solo-ssh.sh - Solo's own ssh: its sshd, its host key and its key file.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh setup      HOME_DIR
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-add    HOME_DIR PUBKEY_FILE [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-remove HOME_DIR PUBKEY_FILE [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-list   HOME_DIR [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh migrate    HOME_DIR [--old-authorized-keys FILE] [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh match      HOME_DIR [--remove]
#
# LSOLO 29 (owner, 2 Oct 2026): SOLO'S ssh LISTENS ON ITS OWN PORT, 4251, FIXED, and is
# run by the Solo owner with no root.  Routing is by port, so nothing in the machine's
# own sshd_config is touched and a person who owns Solo AND is a member of the multi-user
# product reaches the two on 22 and 4251.  It is KEY-ONLY (a sshd that is not root cannot
# check the Linux password; sd-solo then asks the SD account password).  This REPLACES
# the two routes of LSOLO 8 - the forced-command key line in ~/.ssh/authorized_keys and
# the "Match User" block in sshd_config.d - which are removed (owner: "Replace them").
#
# WHAT IT KEEPS, in <tree>/sshd/ (mode 0700): sshd_config (generated; rewritten by every
# "setup"), ssh_host_ed25519_key[.pub] (made once, kept across upgrades) and
# authorized_keys.  The listener is a systemd user SOCKET that starts "sshd -i -f
# <tree>/sshd/sshd_config" per connection (solo-service.sh), the way the API is started.
#
# THE KEY FILE is Solo's own, not ~/.ssh/authorized_keys, so a key added for Solo gives
# nothing on the machine's sshd and the reverse.  Lines are "restrict,pty <key>": no
# agent, port or X11 forwarding and no rc file, the pty sd needs.  The forced command is
# in sshd_config (ForceCommand <tree>/bin/sd-solo), so no key can run anything else.
#
# StrictModes is ON: sshd refuses the key file when it, its directory or any directory
# up to the home directory is owned by someone else or writable by others (measured: 0666
# and 0777 refused, 0664 and 0775 accepted).  setup checks the same walk and says which path
# to fix.
#
# "migrate" moves the key lines an earlier release put in ~/.ssh/authorized_keys (the ones
# whose forced command names this tree) into the new file, after a timestamped copy of
# the old one, and removes them from the old one.  Every other key line is left alone.
# "match" shows or, with --remove (needs sudo), removes the old sshd_config.d drop-in.
#
# TEST HOOKS, NOT FEATURES, announced when used: SDSOLO_TEST_SSH_PORT moves the port the
# answers name (the listener's own port is solo-service.sh's), SDSOLO_AUTHORIZED_KEYS
# names the key file the API requests edit (LSOLO 19).
#
# Exit 0 done, 1 a step failed, 2 refused to start.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
fail()   { echo "FAILED at: $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; Solo's ssh is the owner's own"
cmd="${1:-}"
case "$cmd" in
  setup|key-add|key-remove|key-list|migrate|match|api-add|api-remove|api-list) shift ;;
  *) refuse "usage: bash $0 setup|key-add|key-remove|key-list|migrate|match|api-add|api-remove|api-list HOME_DIR ..." ;;
esac
[ "$#" -ge 1 ] || refuse "HOME_DIR is required"
H="$1"; shift
case "$H" in /*) ;; *) refuse "HOME_DIR must be an absolute path (got '$H')" ;; esac
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
# A path that would break an authorized_keys option or an sshd_config line.
case "$H" in *" "*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*) refuse "HOME_DIR contains a space, quote, backslash, \$ or backtick, which an ssh option or config line cannot carry safely: $H" ;; esac

PORT=4251
if [ -n "${SDSOLO_TEST_SSH_PORT:-}" ]; then
  PORT="$SDSOLO_TEST_SSH_PORT"
  case "$PORT" in ''|*[!0-9]*) refuse "SDSOLO_TEST_SSH_PORT must be a number (got '$PORT')" ;; esac
  [ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || refuse "SDSOLO_TEST_SSH_PORT must be 1024-65535"
  printf '\033[0;33m*** SDSOLO_TEST_SSH_PORT IS SET: the ssh port is %s, NOT 4251 (a test hook) ***\033[0m\n' "$PORT" >&2
fi

user="$(id -un)"
D="$H/sshd"
HOSTKEY="$D/ssh_host_ed25519_key"
CONF="$D/sshd_config"
AK="$D/authorized_keys"
AK_DEFAULT=1
# TEST HOOK (LSOLO 19): the API request that installs the master's key runs this script
# from a session the witness cannot hand an --authorized-keys argument to, so the
# witness names a scratch file in the environment.  Said on the output, so a run that
# used it cannot be mistaken for one that wrote the real file.
if [ -n "${SDSOLO_AUTHORIZED_KEYS:-}" ]; then
  AK="$SDSOLO_AUTHORIZED_KEYS"; AK_DEFAULT=0
  case "$cmd" in api-*) echo "NOTE=test hook SDSOLO_AUTHORIZED_KEYS is in use" ;; esac
fi
KEYOPTS="restrict,pty"
pubfile=""
mode=""
OLD_AK="$HOME/.ssh/authorized_keys"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --authorized-keys) [ "$#" -ge 2 ] || refuse "--authorized-keys needs a file"; AK="$2"; AK_DEFAULT=0; shift 2 ;;
    --old-authorized-keys) [ "$#" -ge 2 ] || refuse "--old-authorized-keys needs a file"; OLD_AK="$2"; shift 2 ;;
    --remove) mode="remove"; shift ;;
    -*) refuse "unknown argument: $1" ;;
    *)  [ -z "$pubfile" ] || refuse "one public key file only"; pubfile="$1"; shift ;;
  esac
done

is_ours() { case "$1" in "$KEYOPTS "*) return 0 ;; *) return 1 ;; esac; }
fp_of() { ssh-keygen -l -f "$1" 2>/dev/null | awk '{print $2}' | head -1; }
mk_akdir() {
  mkdir -p "$(dirname "$AK")" || return 1
  [ "$AK_DEFAULT" -eq 0 ] || chmod 700 "$(dirname "$AK")" 2>/dev/null || true
}

# sshd's StrictModes walk: the file and every directory above it, up to and including the
# home directory (or to / when the file is not under it), must be owned by the user or root and
# not writable by others.  Prints each path that sshd WILL refuse.  MEASURED 2 Oct 2026 with
# OpenSSH 10.5 on Ubuntu (a private group of one): a key file or directory at 0664 or 0775 was
# ACCEPTED, and at 0666 or 0777 REFUSED ("bad ownership or modes"), so this reports world-writable
# and wrongly owned paths only; a group-writable path would be refused on a machine where the
# group has other members, which this does not try to decide.
strict_offenders() {   # strict_offenders FILE
  local p="$1" st own mod
  while [ -n "$p" ] && [ "$p" != "/" ]; do
    st="$(stat -c '%u %a' -- "$p" 2>/dev/null)" || { echo "$p (cannot stat)"; return; }
    own="${st% *}"; mod="${st#* }"
    if { [ "$own" != "$(id -u)" ] && [ "$own" != 0 ]; } || [ $(( 8#$mod & 8#002 )) -ne 0 ]; then
      echo "$p (owner $own, mode $mod)"
    fi
    [ "$p" = "$HOME" ] && return
    p="${p%/*}"
  done
}

# ---- setup: the directory, the host key, the generated config
if [ "$cmd" = "setup" ]; then
  command -v ssh-keygen >/dev/null || refuse "ssh-keygen is not installed (the openssh client package)"
  SSHD="$(command -v sshd 2>/dev/null || true)"; [ -n "$SSHD" ] || { [ -x /usr/sbin/sshd ] && SSHD=/usr/sbin/sshd; }
  [ -n "$SSHD" ] || refuse "sshd is not installed (the openssh-server package); Solo runs its own copy per connection, not the machine's service"
  mkdir -p "$D" || fail "mkdir $D"
  chmod 700 "$D" || fail "chmod $D"
  if [ ! -f "$HOSTKEY" ]; then
    ssh-keygen -q -t ed25519 -N '' -C "SD Core for Linux Solo host key" -f "$HOSTKEY" || fail "ssh-keygen $HOSTKEY"
  fi
  chmod 600 "$HOSTKEY"; chmod 644 "$HOSTKEY.pub" 2>/dev/null || true
  [ -f "$AK" ] || { : > "$AK" && chmod 600 "$AK" || fail "create $AK"; }
  tmp="$(mktemp "$D/sshd_config.XXXXXX")" || fail "mktemp in $D"
  cat > "$tmp" <<CONFIG
# SD Core for Linux Solo: the sshd it runs for itself, one process per connection
# (sd-solo-ssh.socket on port $PORT).  WRITTEN BY $H/tools/solo-ssh.sh setup and
# REWRITTEN every time it runs; add keys with solo-ssh.sh key-add, do not edit this.
HostKey $HOSTKEY
AuthorizedKeysFile $AK
UsePAM no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PermitRootLogin no
PermitEmptyPasswords no
StrictModes yes
AllowUsers $user
DisableForwarding yes
PermitTTY yes
PermitUserEnvironment no
PermitUserRC no
PrintLastLog no
MaxAuthTries 3
LoginGraceTime 30
LogLevel INFO
ForceCommand $H/bin/sd-solo
CONFIG
  if ! out="$("$SSHD" -t -f "$tmp" 2>&1)"; then
    rm -f "$tmp"; printf '%s\n' "$out" >&2; fail "sshd -t rejected the generated configuration"
  fi
  chmod 600 "$tmp"; mv -f "$tmp" "$CONF" || fail "replace $CONF"
  hostfp="$(fp_of "$HOSTKEY.pub")"
  [ -n "$hostfp" ] || fail "no fingerprint for $HOSTKEY.pub"
  off="$(strict_offenders "$AK")"
  if [ -n "$off" ]; then
    echo "WARNING: sshd's StrictModes will REFUSE every key login until these are owned by you (or root) and not writable by others:" >&2
    printf '%s\n' "$off" | sed 's/^/  /' >&2
  fi
  echo "sshd           : $SSHD"
  echo "config         : $CONF"
  echo "host key       : $HOSTKEY.pub ($hostfp)"
  echo "key file       : $AK"
  echo "SOLO SSHD READY port=$PORT hostfp=$hostfp user=$user"
  exit 0
fi

# ---- api-add / api-remove / api-list: what API request 49 runs (LSOLO 19).
# The master installs its public key through the API; APISRVR (a global session only)
# calls these with the key in a file and reads the answer from stdout as KEY=value
# lines, so nothing the master sent is ever placed in a command line.  A refusal is
# "ERROR=<CODE> text" on stdout with exit 0: the answer is in the output, as for
# the success lines.  The key file is Solo's own, so every line carrying the Solo key
# options is ours; any other line is never listed, counted or removed.
if [ "$cmd" = "api-add" ] || [ "$cmd" = "api-remove" ] || [ "$cmd" = "api-list" ]; then
  MAXKEYS=4
  err() { echo "ERROR=$*"; exit 0; }
  command -v ssh-keygen >/dev/null || err "FAILED ssh-keygen is not installed"
  work="$(mktemp -d)" || err "FAILED mktemp"
  trap 'rm -rf "$work"' EXIT
  line_fp() { printf '%s\n' "$1" > "$work/k.pub"; fp_of "$work/k.pub"; }
  count_ours() {
    local n=0 l
    [ -f "$AK" ] || { echo 0; return; }
    while IFS= read -r l || [ -n "$l" ]; do is_ours "$l" && n=$((n+1)); done < "$AK"
    echo "$n"
  }
  case "$cmd" in
  api-list)
    if [ -f "$AK" ]; then
      while IFS= read -r l || [ -n "$l" ]; do
        is_ours "$l" || continue
        echo "FP=$(line_fp "${l#"$KEYOPTS "}")"
      done < "$AK"
    fi
    echo "RESULT=LISTED"
    ;;
  api-add)
    [ -f "$HOSTKEY.pub" ] || err "NOSSH Solo's ssh is not set up on this computer"
    [ -n "$pubfile" ] && [ -r "$pubfile" ] || err "INVALID there is no key"
    [ "$(wc -l < "$pubfile")" -le 1 ] || err "INVALID the key has more than one line"
    key="$(head -1 "$pubfile" | tr -d '\r')"
    case "$key" in ssh-*|ecdsa-*|sk-*) ;; *) err "INVALID the key does not start ssh-, ecdsa- or sk-" ;; esac
    case "$key" in *'"'*|*'\'*) err "INVALID the key contains a quote or backslash" ;; esac
    fp="$(line_fp "$key")"
    [ -n "$fp" ] || err "INVALID ssh-keygen does not accept the key"
    newline="$KEYOPTS $key"
    if [ -f "$AK" ] && grep -qxF -- "$newline" "$AK"; then
      state=PRESENT
    else
      n="$(count_ours)"
      [ "$n" -lt "$MAXKEYS" ] || err "CAP there are already $n Solo ssh keys"
      mk_akdir || err "FAILED mkdir $(dirname "$AK")"
      if [ -s "$AK" ] && [ "$(tail -c1 "$AK" | od -An -c | tr -d ' ')" != '\n' ]; then echo >> "$AK"; fi
      printf '%s\n' "$newline" >> "$AK" || err "FAILED append to $AK"
      chmod 600 "$AK" 2>/dev/null || true
      grep -qxF -- "$newline" "$AK" || err "FAILED the line is not in $AK after the append"
      state=ADDED
    fi
    echo "USER=$(id -un)"
    echo "HOST=$(hostname)"
    echo "FP=$fp"
    echo "HOSTFP=$(fp_of "$HOSTKEY.pub")"
    echo "PORT=$PORT"
    echo "RESULT=$state"
    ;;
  api-remove)
    # The fingerprint comes in a FILE, like the key for api-add, so nothing the master
    # sent is ever part of a command line.
    [ -n "$pubfile" ] && [ -r "$pubfile" ] || err "INVALID there is no fingerprint"
    want="$(head -1 "$pubfile" | tr -d '\r')"
    case "$want" in SHA256:*) ;; *) err "INVALID the fingerprint must start SHA256:" ;; esac
    case "${want#SHA256:}" in ""|*[!A-Za-z0-9+/=]*) err "INVALID the fingerprint has characters a fingerprint cannot" ;; esac
    removed=0
    if [ -f "$AK" ]; then
      tmp="$(mktemp "$AK.XXXXXX")" || err "FAILED mktemp beside $AK"
      while IFS= read -r l || [ -n "$l" ]; do
        if is_ours "$l" && [ "$(line_fp "${l#"$KEYOPTS "}")" = "$want" ]; then removed=$((removed+1)); else printf '%s\n' "$l" >> "$tmp"; fi
      done < "$AK"
      if [ "$removed" -gt 0 ]; then chmod 600 "$tmp"; mv "$tmp" "$AK" || { rm -f "$tmp"; err "FAILED replace $AK"; }
      else rm -f "$tmp"; fi
    fi
    echo "REMAINING=$(count_ours)"
    if [ "$removed" -gt 0 ]; then echo "RESULT=REMOVED"; else echo "RESULT=ABSENT"; fi
    ;;
  esac
  exit 0
fi

if [ "$cmd" = "key-list" ]; then
  echo "key file        : $AK"
  [ -f "$AK" ] || { echo "  (does not exist)"; echo "SOLO SSH KEYS 0"; exit 0; }
  n=0
  while IFS= read -r line; do
    if is_ours "$line"; then
      n=$((n+1))
      echo "  $n. ${line#"$KEYOPTS "}" | cut -c1-140
    fi
  done < "$AK"
  echo "SOLO SSH KEYS $n"
  exit 0
fi

if [ "$cmd" = "key-add" ] || [ "$cmd" = "key-remove" ]; then
  [ -n "$pubfile" ] || refuse "a public key file is required"
  [ -r "$pubfile" ] || refuse "cannot read $pubfile"
  [ "$(wc -l < "$pubfile")" -le 1 ] || refuse "$pubfile has more than one line; give one public key"
  key="$(head -1 "$pubfile" | tr -d '\r')"
  case "$key" in
    ssh-*|ecdsa-*|sk-*) ;;
    *) refuse "$pubfile does not look like an ssh public key (it starts '$(printf '%s' "$key" | cut -c1-20)')" ;;
  esac
  case "$key" in *'"'*|*'\'*) refuse "the key line contains a quote or backslash" ;; esac
  # Fingerprint through ssh-keygen when available: what is added must be a real key.
  if command -v ssh-keygen >/dev/null; then
    fp="$(ssh-keygen -l -f "$pubfile" 2>&1)" || refuse "ssh-keygen does not accept $pubfile: $fp"
    echo "key            : $fp"
  fi
  newline="$KEYOPTS $key"
fi

if [ "$cmd" = "key-add" ]; then
  mk_akdir || fail "mkdir $(dirname "$AK")"
  if [ -f "$AK" ] && grep -qxF -- "$newline" "$AK"; then
    echo "already present: nothing to do"
  else
    # A file with no final newline would glue the new line to the last key.
    if [ -s "$AK" ] && [ "$(tail -c1 "$AK" | od -An -c | tr -d ' ')" != '\n' ]; then echo >> "$AK"; fi
    printf '%s\n' "$newline" >> "$AK" || fail "append to $AK"
  fi
  chmod 600 "$AK" 2>/dev/null || true
  grep -qxF -- "$newline" "$AK" || fail "the line is not in $AK after the append"
  echo "SOLO SSH KEY ADDED $AK"
  exit 0
fi

if [ "$cmd" = "key-remove" ]; then
  [ -f "$AK" ] || refuse "$AK does not exist"
  tmp="$(mktemp "$AK.XXXXXX")" || fail "mktemp"
  removed=0
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$line" = "$newline" ]; then removed=$((removed+1)); else printf '%s\n' "$line" >> "$tmp"; fi
  done < "$AK"
  if [ "$removed" -eq 0 ]; then rm -f "$tmp"; echo "no such Solo key line in $AK"; echo "SOLO SSH KEY REMOVED 0"; exit 0; fi
  chmod 600 "$tmp"
  mv "$tmp" "$AK" || fail "replace $AK"
  grep -qxF -- "$newline" "$AK" && fail "the line is still in $AK"
  echo "SOLO SSH KEY REMOVED $removed"
  exit 0
fi

# ---- migrate: the key lines an earlier release put in ~/.ssh/authorized_keys
if [ "$cmd" = "migrate" ]; then
  # Both spellings of the forced command: bin/sd-solo, and bin/sd from before the rename.
  FORCED_NEW="command=\"$H/bin/sd-solo\",restrict,pty "
  FORCED_OLD="command=\"$H/bin/sd\",restrict,pty "   # an install before the 2 Oct 26 rename wrote these
  forms=("$FORCED_NEW" "$FORCED_OLD")
  if [ ! -f "$OLD_AK" ]; then echo "no $OLD_AK: nothing to migrate"; echo "SOLO SSH MIGRATED 0"; exit 0; fi
  moved=()
  while IFS= read -r l || [ -n "$l" ]; do
    for f in "${forms[@]}"; do
      case "$l" in "$f"*) moved+=("${l#"$f"}"); break ;; esac
    done
  done < "$OLD_AK"
  if [ "${#moved[@]}" -eq 0 ]; then echo "no Solo key line in $OLD_AK: nothing to migrate"; echo "SOLO SSH MIGRATED 0"; exit 0; fi
  mk_akdir || fail "mkdir $(dirname "$AK")"
  bak="$OLD_AK.sdsolo-backup-$(date +%Y%m%dT%H%M%S)"
  cp -p -- "$OLD_AK" "$bak" || fail "backup $OLD_AK"
  echo "backup         : $bak"
  [ -e "$AK" ] || { : > "$AK" && chmod 600 "$AK"; } || fail "create $AK"
  if [ -s "$AK" ] && [ "$(tail -c1 "$AK" | od -An -c | tr -d ' ')" != '\n' ]; then echo >> "$AK"; fi
  for k in "${moved[@]}"; do
    grep -qxF -- "$KEYOPTS $k" "$AK" || printf '%s\n' "$KEYOPTS $k" >> "$AK" || fail "append to $AK"
  done
  for k in "${moved[@]}"; do
    grep -qxF -- "$KEYOPTS $k" "$AK" || fail "a migrated key is not in $AK; $OLD_AK was NOT changed (the copy is $bak)"
  done
  chmod 600 "$AK" 2>/dev/null || true
  tmp="$(mktemp "$OLD_AK.XXXXXX")" || fail "mktemp beside $OLD_AK"
  while IFS= read -r l || [ -n "$l" ]; do
    drop=0
    for f in "${forms[@]}"; do case "$l" in "$f"*) drop=1; break ;; esac; done
    [ "$drop" -eq 1 ] || printf '%s\n' "$l" >> "$tmp"
  done < "$OLD_AK"
  chmod --reference="$OLD_AK" "$tmp" 2>/dev/null || chmod 600 "$tmp"
  mv -f -- "$tmp" "$OLD_AK" || { rm -f "$tmp"; fail "replace $OLD_AK"; }
  echo "SOLO SSH MIGRATED ${#moved[@]}"
  exit 0
fi

# ---- match: the old sshd_config.d drop-in, which is gone as a route
DROPIN="/etc/ssh/sshd_config.d/50-sd-solo-$user.conf"
case "$mode" in
  "")
    if [ -f "$DROPIN" ]; then
      echo "$DROPIN is still there; Solo no longer uses it (its ssh has its own port now)."
      echo "Remove it (needs sudo):"
      echo "    bash $0 match $H --remove"
      echo "SOLO SSH MATCH PRESENT $DROPIN"
    else
      echo "no $DROPIN: nothing to remove"
      echo "SOLO SSH MATCH ABSENT $DROPIN"
    fi
    ;;
  remove)
    SSHD="$(command -v sshd || echo /usr/sbin/sshd)"
    sudo rm -f "$DROPIN" || fail "remove $DROPIN"
    sudo "$SSHD" -t || fail "sshd -t after removing $DROPIN"
    sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd || fail "reload sshd"
    # The compatibility link an upgrade leaves at bin/sd while an OLD drop-in still names it.
    if [ -L "$H/bin/sd" ] && [ "$(readlink "$H/bin/sd")" = "sd-solo" ]; then rm -f "$H/bin/sd"; echo "removed the compatibility link $H/bin/sd"; fi
    echo "SOLO SSH MATCH REMOVED $DROPIN"
    ;;
esac
