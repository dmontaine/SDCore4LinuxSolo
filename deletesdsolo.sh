#!/bin/bash
#
# SD Core for Linux Solo - delete script
#   (c) 2026 Donald Montaine.  Released under the Blue Oak Model License 1.0.0,
#   a copy can be found on the web here: https://blueoakcouncil.org/license/1.0.0
#
#   bash deletesdsolo.sh [--home DIR] [--keep-data | --delete-data] [--yes]
#
# Removes SD Core for Linux Solo for the user who runs it: the systemd user units,
# the running daemon, the ~/.local/bin/sd and sd-solo commands, the ssh key lines an earlier
# release added to your ~/.ssh/authorized_keys, the old sshd_config.d block (sudo, only if it
# exists), Solo's own PAM service /etc/pam.d/sd-solo-ssh-<you> (sudo, only if it exists -
# SELinux machines, LSOLO 31), and the installation directory (which holds Solo's own ssh directory: its host
# key and key file).  Run as YOUR OWN USER, never as root.
#
# YOUR DATA.  The account's files live in <home>/user_accounts/sduser.  --keep-data
# moves that directory to ~/SDCoreSolo-data-<date> before anything is deleted;
# --delete-data removes it with the rest.  Asked when neither is given.  The
# passwords, the audit trail and the system files are always removed: a kept
# user_accounts is data, not an installation, and a reinstall starts from a clean
# tree.  (It cannot be re-attached to a new install by this script yet.)
#
# Linger is left as it is: it is a persistent setting of your account and other things
# may rely on it.  A firewall rule the installer added is not removed; the script says so.
#
# The last line of a good run is "SOLO DELETE COMPLETE <home>".
# EXIT: 0 done; 1 a step failed; 2 refused to start.

set -uo pipefail

RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
say()  { printf '%s\n' "$*"; }
warn() { printf '%b%s%b\n' "$YELLOW" "$*" "$NC"; }
refuse() { printf '%bREFUSED: %s%b\n' "$RED" "$*" "$NC" >&2; exit 2; }
fail()   { printf '%bFAILED at: %s%b\n' "$RED" "$*" "$NC" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "run this as your own user, not root"

# ---- options
H=""; data=""; assume_yes=0; from_copy=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --home)        [ "$#" -ge 2 ] || refuse "--home needs a directory"; H="$2"; shift 2 ;;
    --keep-data)   data="keep"; shift ;;
    --delete-data) data="delete"; shift ;;
    --yes)         assume_yes=1; shift ;;
    --from-copy)   from_copy=1; shift ;;
    -h|--help)     sed -n '2,30p' "$0"; exit 0 ;;
    *) refuse "unknown option: $1" ;;
  esac
done

# ---- which tree.  Default: the tree this script sits in (<home>/tools/deletesdsolo.sh),
# else ~/SDCoreSolo.
if [ -z "$H" ]; then
  self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$self_dir/../.sdcoresolo" ]; then H="$(cd "$self_dir/.." && pwd)"; else H="$HOME/SDCoreSolo"; fi
fi
case "$H" in /*) ;; *) refuse "--home must be an absolute path (got '$H')" ;; esac
[ -f "$H/.sdcoresolo" ] || refuse "$H is not an SD Core for Linux Solo tree (no .sdcoresolo marker); nothing was changed"
# A last defence against a wrong path: never the home directory itself, "/" or a top-level directory.
[ "$H" != "$HOME" ] && [ "$H" != "/" ] && [ "$(printf '%s' "$H" | tr -cd '/' | wc -c)" -ge 2 ] \
  || refuse "$H is not a plausible install directory"

# ---- do not delete the tree we are running from: run from a copy.
if [ "$from_copy" -eq 0 ]; then
  case "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/" in
    "$H"/*)
      tmp="$(mktemp -t deletesdsolo.XXXXXX)" || refuse "cannot make a temporary copy of this script"
      cp "${BASH_SOURCE[0]}" "$tmp" || refuse "cannot copy this script to $tmp"
      extra=()
      [ -z "$data" ] || extra+=("--${data}-data")
      [ "$assume_yes" -eq 0 ] || extra+=(--yes)
      exec bash "$tmp" --home "$H" --from-copy "${extra[@]}"
      ;;
  esac
fi

interactive=0; [ -t 0 ] && [ -r /dev/tty ] && interactive=1

say
say "SD Core for Linux Solo - delete"
say "  tree        : $H"
say "  running as  : $(id -un)"
[ -f "$H/.sdcore-install" ] && sed 's/^/  installed   : /' "$H/.sdcore-install" | head -3
say

AK="$HOME/.ssh/authorized_keys"
FORCED="command=\"$H/bin/sd-solo\",restrict,pty "
FORCED_OLD="command=\"$H/bin/sd\",restrict,pty "   # lines an install before the 2 Oct 26 rename wrote
n_keys=0
[ -f "$AK" ] && n_keys="$(grep -cF -e "$FORCED" -e "$FORCED_OLD" "$AK" 2>/dev/null || true)"
DROPIN="/etc/ssh/sshd_config.d/50-sd-solo-$(id -un).conf"
# LSOLO 31: Solo's own PAM service where SELinux is enabled (solo-ssh.sh pam); removed only when it
# carries Solo's marker line.
PAMFILE="/etc/pam.d/sd-solo-ssh-$(id -un)"
pam_ours=0
[ -f "$PAMFILE" ] && grep -qF '# SD Core for Linux Solo: the PAM service of' "$PAMFILE" 2>/dev/null && pam_ours=1
# 02 Oct 26 - THE COMMAND NAMES (owner, 1 Oct 2026).  "sd-solo" is a link to this tree's
# bin/sd-solo.  "sd" is NOT this product's name any more, but an install before the rename made
# ~/.local/bin/sd (a link to this tree's old bin/sd, or a launcher naming it), and an upgrade
# that did not run leaves it.  Each is removed only when it is this tree's: a launcher is
# recognised by its marker line AND by naming this tree's old binary, so a file of yours,
# another tree's launcher or a link elsewhere is never touched.  The link to the NEW name
# is also recognised when it points at the OLD one.
# (gplbld/test-launcher-units.py cuts the lines between the markers out of this file and runs them.)
# BEGIN link_detect
link="$HOME/.local/bin/sd"
solo_link="$HOME/.local/bin/sd-solo"
link_ours=0; solo_link_ours=0
if [ -L "$link" ]; then
  [ "$(readlink "$link")" = "$H/bin/sd" ] && link_ours=1
elif [ -f "$link" ] && grep -qF 'SD Core for Linux Solo launcher.' "$link" 2>/dev/null && grep -qF "'$H/bin/sd'" "$link" 2>/dev/null; then
  link_ours=1
fi
if [ -L "$solo_link" ]; then
  case "$(readlink "$solo_link")" in "$H/bin/sd-solo"|"$H/bin/sd") solo_link_ours=1 ;; esac
fi
# END link_detect

say "This will remove:"
say "  - the systemd user units (sd-solo.service, the API and ssh sockets) and stop SD"
say "  - the installation directory $H"
[ "$link_ours" -eq 1 ] && say "  - the command $link"
[ "$solo_link_ours" -eq 1 ] && say "  - the link $solo_link"
[ "${n_keys:-0}" -gt 0 ] && say "  - $n_keys ssh key line(s) in $AK that force sd (your other keys are untouched)"
[ -f "$DROPIN" ] && say "  - $DROPIN (needs sudo)"
[ "$pam_ours" -eq 1 ] && say "  - $PAMFILE, Solo's PAM service (needs sudo)"
say

if [ -z "$data" ]; then
  if [ "$interactive" -eq 1 ]; then
    say "Your data is the account's files in $H/user_accounts/sduser."
    read -r -p "Keep it (moved to ~/SDCoreSolo-data-<date>) or delete it? [keep/delete] " data < /dev/tty
    case "$data" in keep|delete) ;; *) refuse "answer keep or delete (got '$data'); nothing was changed" ;; esac
  else
    refuse "say --keep-data or --delete-data (there is no terminal to ask on); nothing was changed"
  fi
fi
if [ "$assume_yes" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  read -r -p "Continue? [y/N] " a < /dev/tty
  case "$a" in y|Y|yes|YES) ;; *) refuse "cancelled by you; nothing was changed" ;; esac
fi

# ---- 1. the service and the daemon
if [ -f "$H/tools/solo-service.sh" ]; then
  bash "$H/tools/solo-service.sh" remove 2>&1 | tail -2
else
  systemctl --user disable --now sd-solo-ssh.socket sd-solo-api.socket sd-solo.service >/dev/null 2>&1 || true
  rm -f "${XDG_CONFIG_HOME:-$HOME/.config}"/systemd/user/sd-solo.service "${XDG_CONFIG_HOME:-$HOME/.config}"/systemd/user/sd-solo-api.socket "${XDG_CONFIG_HOME:-$HOME/.config}"/systemd/user/sd-solo-api@.service \
        "${XDG_CONFIG_HOME:-$HOME/.config}"/systemd/user/sd-solo-ssh.socket "${XDG_CONFIG_HOME:-$HOME/.config}"/systemd/user/sd-solo-ssh@.service
  systemctl --user daemon-reload 2>/dev/null || true
fi
for n in sd-solo sd; do   # the new name, then an old install's
  if [ -x "$H/bin/$n" ]; then "$H/bin/$n" -stop >/dev/null 2>&1 || true; fi
done
sleep 1
if pgrep -u "$(id -u)" -f "$H/bin/" >/dev/null 2>&1; then
  warn "processes are still running from $H; stopping them"
  pkill -u "$(id -u)" -f "$H/bin/" 2>/dev/null || true
  sleep 1
fi

# ---- 2. the link, the ssh lines, the sshd block
[ "$link_ours" -eq 1 ] && rm -f "$link" && say "removed $link"
[ "$solo_link_ours" -eq 1 ] && rm -f "$solo_link" && say "removed $solo_link"
if [ "${n_keys:-0}" -gt 0 ]; then
  tmp="$(mktemp "$AK.XXXXXX")" || fail "mktemp"
  removed=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in "$FORCED"*|"$FORCED_OLD"*) removed=$((removed+1)) ;; *) printf '%s\n' "$line" >> "$tmp" ;; esac
  done < "$AK"
  chmod 600 "$tmp"; mv "$tmp" "$AK" || fail "replace $AK"
  say "removed $removed ssh key line(s) from $AK"
fi
if [ -f "$DROPIN" ]; then
  if [ -f "$H/tools/solo-ssh.sh" ]; then bash "$H/tools/solo-ssh.sh" match "$H" --remove || warn "the sshd block was NOT removed; remove $DROPIN as an administrator"
  else warn "remove $DROPIN as an administrator (sudo rm, then reload sshd)"; fi
fi
if [ "$pam_ours" -eq 1 ]; then
  if sudo rm -f "$PAMFILE" && [ ! -e "$PAMFILE" ]; then say "removed $PAMFILE"
  else warn "$PAMFILE was NOT removed; remove it as an administrator (sudo rm $PAMFILE)"; fi
fi

# ---- 3. the data, then the tree
if [ "$data" = "keep" ]; then
  if [ -d "$H/user_accounts/sduser" ]; then
    dest="$HOME/SDCoreSolo-data-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$dest" && mv "$H/user_accounts/sduser" "$dest/" || fail "moving your data to $dest"
    chmod -R go-rwx "$dest"
    say "your data is in $dest/sduser"
  else
    warn "there is no $H/user_accounts/sduser to keep"
  fi
fi
rm -rf "$H" || fail "removing $H"
[ ! -e "$H" ] || fail "$H is still there"
say "removed $H"

# 02 Oct 26 - the API port is 4249, fixed (owner, 2 Oct 2026).  Its rule is reported, not
# removed (the installer added it with your sudo); 4243 is OpenQM's and ScarletDME's port, so a
# rule for it is only mentioned: it may belong to another database.
if command -v ufw >/dev/null 2>&1; then
  ufw_rules="$(sudo -n ufw status 2>/dev/null)"
  if printf '%s\n' "$ufw_rules" | grep -qE '^4249/tcp .*ALLOW'; then
    warn "ufw still allows TCP 4249, this product's API port; if the installer added it, remove it with 'sudo ufw delete allow 4249/tcp'"
  fi
  if printf '%s\n' "$ufw_rules" | grep -qE '^4251/tcp .*ALLOW'; then
    warn "ufw still allows TCP 4251, this product's ssh port; if the installer added it, remove it with 'sudo ufw delete allow 4251/tcp'"
  fi
  if printf '%s\n' "$ufw_rules" | grep -qE '^4243/tcp .*ALLOW'; then
    warn "ufw allows TCP 4243: that is OpenQM's and ScarletDME's port, not this product's, so it was left alone"
  fi
fi
# LSOLO 32 (4 Oct 2026): the installer adds firewalld rules too now; reported the same way, not removed.
# (systemd, not "firewall-cmd --state", which polkit refuses an ordinary user - Fedora 44.)
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
  for p in 4249 4251; do
    # the exact entry: Fedora Workstation's own 1025-65535/tcp would answer --query-port too
    if sudo -n firewall-cmd --permanent --list-ports 2>/dev/null | tr ' ' '\n' | grep -qx -- "$p/tcp"; then
      warn "firewalld still allows TCP $p, this product's $( [ "$p" = 4249 ] && echo API || echo ssh ) port; if the installer added it, remove it with 'sudo firewall-cmd --permanent --remove-port=$p/tcp && sudo firewall-cmd --reload'"
    fi
  done
fi
say
say "SOLO DELETE COMPLETE $H"
