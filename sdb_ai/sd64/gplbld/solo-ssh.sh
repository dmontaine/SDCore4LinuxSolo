#!/bin/bash
# solo-ssh.sh - let ssh land straight in SD Core for Linux Solo.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-add    HOME_DIR PUBKEY_FILE [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-remove HOME_DIR PUBKEY_FILE [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh key-list   HOME_DIR [--authorized-keys FILE]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-ssh.sh match      HOME_DIR [--apply | --remove]
#
# LSOLO 8, owner's ruling Q2 (29 Sep 2026): the DEFAULT route is a key line with a
# forced command in the user's own ~/.ssh/authorized_keys - no root, key logins
# only; the OPTIONAL second route is a "Match User" block in sshd_config.d, which
# needs sudo and is what lets a PASSWORD login land in sd too.
#
# THE KEY ROUTE.  key-add appends the public key with the options
#     command="<HOME_DIR>/bin/sd",restrict,pty
# so that key gets sd - at the account-password prompt, ruling 21 - and nothing
# else: no shell, no scp or sftp (they receive sd instead of their server), and
# "restrict" turns off every forwarding and agent facility; "pty" gives sd the
# terminal it needs.  IT DOES NOT TOUCH THE USER'S OTHER KEYS: a key without the
# forced command still gets a shell, exactly as before - which is the point of
# choosing this route by default.  Our lines are recognised by the command
# string, so key-remove and key-list find them and nothing else, and key-add
# twice adds one line.
#
# THE MATCH ROUTE.  "match" prints (default), applies (--apply) or removes
# (--remove) /etc/ssh/sshd_config.d/50-sd-solo-<user>.conf:
#     Match User <user>
#         ForceCommand <HOME_DIR>/bin/sd
#         DisableForwarding yes
# so EVERY ssh login of the user - key or password - lands in sd, and the user has
# no shell over ssh at all.  It needs sudo and it changes the machine's sshd, so it
# is opt-in, checked with "sshd -t" BEFORE the reload and put back if the check
# fails.  ***--apply and --remove are written but NOT MEASURED*** (they need a
# password for sudo); --print and the block's syntax ARE measured
# (verify-solo-ssh.sh).
#
# Exit 0 done, 1 a step failed, 2 refused to start.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
fail()   { echo "FAILED at: $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; the key route edits the user's own authorized_keys"
cmd="${1:-}"
case "$cmd" in
  key-add|key-remove|key-list|match) shift ;;
  *) refuse "usage: bash $0 key-add|key-remove|key-list|match HOME_DIR ..." ;;
esac
[ "$#" -ge 1 ] || refuse "HOME_DIR is required"
H="$1"; shift
case "$H" in /*) ;; *) refuse "HOME_DIR must be an absolute path (got '$H')" ;; esac
[ -x "$H/bin/sd" ] || refuse "$H/bin/sd is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
# A path that would break an authorized_keys option or an sshd_config line.
case "$H" in *" "*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*) refuse "HOME_DIR contains a space, quote, backslash, \$ or backtick, which an ssh option or config line cannot carry safely: $H" ;; esac

AK="$HOME/.ssh/authorized_keys"
FORCED="command=\"$H/bin/sd\",restrict,pty"
pubfile=""
mode=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --authorized-keys) [ "$#" -ge 2 ] || refuse "--authorized-keys needs a file"; AK="$2"; shift 2 ;;
    --apply)  mode="apply";  shift ;;
    --remove) mode="remove"; shift ;;
    -*) refuse "unknown argument: $1" ;;
    *)  [ -z "$pubfile" ] || refuse "one public key file only"; pubfile="$1"; shift ;;
  esac
done

is_ours() { case "$1" in "$FORCED "*) return 0 ;; *) return 1 ;; esac; }

if [ "$cmd" = "key-list" ]; then
  echo "authorized_keys : $AK"
  [ -f "$AK" ] || { echo "  (does not exist)"; echo "SOLO SSH KEYS 0"; exit 0; }
  n=0
  while IFS= read -r line; do
    if is_ours "$line"; then
      n=$((n+1))
      echo "  $n. ${line#"$FORCED "}" | cut -c1-140
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
  newline="$FORCED $key"
fi

if [ "$cmd" = "key-add" ]; then
  mkdir -p "$(dirname "$AK")" || fail "mkdir $(dirname "$AK")"
  chmod 700 "$(dirname "$AK")" 2>/dev/null || true
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

# ---- match
user="$(id -un)"
DROPIN="/etc/ssh/sshd_config.d/50-sd-solo-$user.conf"
block="# SD Core for Linux Solo: every ssh login of $user lands in sd (no shell, no forwarding).
# Written by $H/../gplbld/solo-ssh.sh; remove it with 'solo-ssh.sh match $H --remove'.
Match User $user
    ForceCommand $H/bin/sd
    DisableForwarding yes"

case "$mode" in
  "")
    echo "file    : $DROPIN"
    echo "contents:"
    printf '%s\n' "$block" | sed 's/^/    /'
    echo
    echo "To apply it (needs sudo; checks with sshd -t first and reloads only if that passes):"
    echo "    bash $0 match $H --apply"
    echo "To take it away again:"
    echo "    bash $0 match $H --remove"
    echo "SOLO SSH MATCH PRINTED"
    ;;
  apply)
    command -v sshd >/dev/null || [ -x /usr/sbin/sshd ] || refuse "sshd is not installed"
    SSHD="$(command -v sshd || echo /usr/sbin/sshd)"
    grep -qE '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config 2>/dev/null \
      || refuse "/etc/ssh/sshd_config has no 'Include /etc/ssh/sshd_config.d/*.conf', so the drop-in would be ignored; add that line yourself, then re-run"
    tmp="$(mktemp)" || fail "mktemp"
    printf '%s\n' "$block" > "$tmp"
    old="$(sudo cat "$DROPIN" 2>/dev/null || true)"
    sudo install -m 644 -o root -g root "$tmp" "$DROPIN" || { rm -f "$tmp"; fail "install $DROPIN"; }
    rm -f "$tmp"
    if ! sudo "$SSHD" -t; then
      echo "sshd -t REJECTED the configuration; putting it back" >&2
      if [ -n "$old" ]; then printf '%s\n' "$old" | sudo tee "$DROPIN" >/dev/null; else sudo rm -f "$DROPIN"; fi
      fail "sshd -t"
    fi
    sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd || fail "reload sshd"
    echo "SOLO SSH MATCH APPLIED $DROPIN"
    ;;
  remove)
    sudo rm -f "$DROPIN" || fail "remove $DROPIN"
    SSHD="$(command -v sshd || echo /usr/sbin/sshd)"
    sudo "$SSHD" -t || fail "sshd -t after removing $DROPIN"
    sudo systemctl reload ssh 2>/dev/null || sudo systemctl reload sshd || fail "reload sshd"
    echo "SOLO SSH MATCH REMOVED $DROPIN"
    ;;
esac
