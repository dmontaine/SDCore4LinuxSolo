#!/bin/bash
# solo-service.sh - run SD Core for Linux Solo as the user's own systemd service.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh install HOME_DIR [--api off|local|open] [--ssh off|local|open]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh ssh HOME_DIR off|local|open [--print]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh remove
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh status
#
# "ssh" (LSOLO 29) writes or removes ONLY the two ssh units and leaves the daemon and the
# API alone; "install --ssh" does the same as part of an install.  --print shows the two
# units and touches nothing (no systemctl, no file): that is what the free test reads.
# No sudo for the units: they are USER units, in ${XDG_CONFIG_HOME:-~/.config}/systemd/user,
# started by the user's own systemd manager, running as the user (LSOLO 7; owner's
# ruling Q1, 29 Sep 2026: systemd --user plus loginctl enable-linger).
#
# THREE FILES, named for the product and written with the tree's ABSOLUTE path
# (a user unit cannot expand an arbitrary directory):
#   sd-solo.service        the daemon: Type=oneshot + RemainAfterExit, as the parent's
#                          sd.service (its 13 Sep 26 note: "sd -start" forks a daemon
#                          that forks again, and Type=forking makes systemd guess the
#                          main PID and declare the service dead)
#   sd-solo-api.socket     only with --api local|open: the API's listener, port 4249;
#                          127.0.0.1 for "local", 0.0.0.0 for "open"
#
# THE PORT IS 4249, FIXED (owner, 2 Oct 2026: "make ports 4247 and 4249 -- do not
# allow adjustable ports"; was 4243, and --api-port moved it).  Both SD Core Solos use
# 4249 and the full products 4247; OpenQM and ScarletDME use 4243, upstream SD 4245.
# TEST HOOK, NOT A FEATURE: SDSOLO_TEST_API_PORT moves it, so the witnesses can run a
# staged tree beside a live Solo.  Announced on every use; a real install never sets
# it (the same rule as installsdsolo.sh's SDSOLO_REPO_URL).
#   sd-solo-api@.service   one "sd -n -q" per connection (Accept=true)
#
# THE ssh PORT IS 4251, FIXED (owner, 2 Oct 2026: a separate port for sd-solo, routing by
# port).  Two more units, only with --ssh local|open, the same shape as the API's:
#   sd-solo-ssh.socket     the listener, 127.0.0.1:4251 for "local", 0.0.0.0:4251 for "open"
#   sd-solo-ssh@.service   one "sshd -i -e -f <tree>/sshd/sshd_config" per connection
# The tree's own sshd directory (config, host key, key file) is made by solo-ssh.sh setup,
# which must have run first.  TEST HOOK, NOT A FEATURE: SDSOLO_TEST_SSH_PORT moves the port
# (announced on every use), as SDSOLO_TEST_API_PORT does for the API.
#
# LINGER.  Without it the user manager - and SD with it - stops when the user's last
# session ends, which defeats "remote access while signed out" (ruling 2).  It is a
# persistent setting of the user's account, so it is OPT-IN: with --enable-linger
# this runs "loginctl enable-linger" (which may need authority the user lacks);
# without it, or if that is refused, it PRINTS the one sudo command to run and says
# linger=no.  It never runs sudo itself and never disables linger (something else
# may rely on it).  The installer (LSOLO 9) tells the user and passes the flag.
#
# The last line of a successful install is
#   SOLO SERVICE READY daemon=<state> api=<off|local|open> ssh=<off|local|open> linger=<yes|no>
# and a caller must anchor on THAT, not on an exit code.
#
# Exit 0 done, 1 a step failed, 2 refused to start.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
fail()   { echo "FAILED at: $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; these are user units and Solo never runs as root"

UNITDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DAEMON="sd-solo.service"
SOCKET="sd-solo-api.socket"
TEMPLATE="sd-solo-api@.service"
SSH_SOCKET="sd-solo-ssh.socket"
SSH_TEMPLATE="sd-solo-ssh@.service"

# ---- the ssh units (LSOLO 29).  Defined before the systemd checks because "ssh ... --print"
# needs no systemd at all.
ssh_port() {
  local p=4251
  if [ -n "${SDSOLO_TEST_SSH_PORT:-}" ]; then
    p="$SDSOLO_TEST_SSH_PORT"
    case "$p" in ''|*[!0-9]*) refuse "SDSOLO_TEST_SSH_PORT must be a number (got '$p')" ;; esac
    [ "$p" -ge 1024 ] && [ "$p" -le 65535 ] || refuse "SDSOLO_TEST_SSH_PORT must be 1024-65535"
    printf '\033[0;33m*** SDSOLO_TEST_SSH_PORT IS SET: the ssh port is %s, NOT 4251 (a test hook) ***\033[0m\n' "$p" >&2
  fi
  echo "$p"
}
ssh_sshd_path() {
  local s; s="$(command -v sshd 2>/dev/null || true)"
  [ -n "$s" ] || { [ -x /usr/sbin/sshd ] && s=/usr/sbin/sshd; }
  [ -n "$s" ] || return 1
  echo "$s"
}
ssh_socket_text() {   # ssh_socket_text MODE PORT
  local listen
  if [ "$1" = "open" ]; then listen="0.0.0.0:$2"; else listen="127.0.0.1:$2"; fi
  cat <<UNIT
[Unit]
Description=SD Core for Linux Solo (ssh listener, $1)

[Socket]
ListenStream=$listen
Accept=true

[Install]
WantedBy=sockets.target
UNIT
}
ssh_python_path() { command -v python3 2>/dev/null || echo /usr/bin/python3; }
# The unit starts the GUARD (solo-sshguard.py: three wrong passwords from one address within ten
# minutes lock that address for ten minutes, owner 2 Oct 2026), which runs "sshd -i -e -f
# <tree>/sshd/sshd_config" itself with the same connection.
ssh_template_text() {   # ssh_template_text TREE SSHD PYTHON
  cat <<UNIT
[Unit]
Description=SD Core for Linux Solo (one ssh connection)
Requires=$DAEMON
After=$DAEMON
CollectMode=inactive-or-failed

[Service]
UMask=0077
ExecStart=$3 $1/tools/solo-sshguard.py $1 $2
StandardInput=socket
StandardError=journal
SuccessExitStatus=5 255
UNIT
}
# ssh_apply TREE MODE: off removes the two units; local or open writes them and starts the socket.
ssh_apply() {
  local tree="$1" mode="$2" port sshd other
  # THE UNIT NAMES ARE ONE PAIR PER USER, NOT PER TREE.  Writing or removing them for a scratch tree
  # takes the real Solo's ssh away (found 2 Oct 2026: a test of this script against a scratch tree,
  # run on the owner's own user manager, removed his live listener and nothing said so).  So refuse to
  # replace or remove a pair that names another tree.
  # (Both unit formats name the tree: the earlier "sshd -i -f <tree>/sshd/sshd_config" and the guard's.)
  if [ -f "$UNITDIR/$SSH_TEMPLATE" ] && ! grep -qF -e " -f $tree/sshd/sshd_config" -e " $tree/tools/solo-sshguard.py " "$UNITDIR/$SSH_TEMPLATE"; then
    other="$(sed -n -e 's#^ExecStart=.* -f \(.*\)/sshd/sshd_config.*#\1#p' -e 's#^ExecStart=[^ ]* \(.*\)/tools/solo-sshguard.py .*#\1#p' "$UNITDIR/$SSH_TEMPLATE" | head -1)"
    refuse "the ssh units installed for this user belong to another Solo tree (${other:-unknown}); doing this for $tree would replace or remove them.  Remove them from that tree (solo-service.sh ssh ${other:-<tree>} off) first, if that is what you mean"
  fi
  systemctl --user disable --now "$SSH_SOCKET" >/dev/null 2>&1 || true
  rm -f "$UNITDIR/$SSH_SOCKET" "$UNITDIR/$SSH_TEMPLATE"
  if [ "$mode" = "off" ]; then
    systemctl --user daemon-reload || fail "daemon-reload"
    return 0
  fi
  [ -f "$tree/sshd/sshd_config" ] || fail "$tree/sshd/sshd_config is missing: run solo-ssh.sh setup $tree first"
  sshd="$(ssh_sshd_path)" || fail "sshd is not installed (the openssh-server package)"
  port="$(ssh_port)" || exit $?
  mkdir -p "$UNITDIR" || fail "mkdir $UNITDIR"
  ssh_socket_text "$mode" "$port" > "$UNITDIR/$SSH_SOCKET"
  [ -f "$tree/tools/solo-sshguard.py" ] || fail "$tree/tools/solo-sshguard.py is missing (the ssh guard); an upgrade installs it"
  ssh_template_text "$tree" "$sshd" "$(ssh_python_path)" > "$UNITDIR/$SSH_TEMPLATE"
  systemctl --user daemon-reload || fail "daemon-reload"
  systemctl --user enable --now "$SSH_SOCKET" 2>&1 | tail -2
  local s; s="$(systemctl --user is-active "$SSH_SOCKET" 2>&1)"
  [ "$s" = "active" ] || { systemctl --user status "$SSH_SOCKET" --no-pager 2>&1 | tail -12; fail "$SSH_SOCKET is '$s', not active"; }
}
ssh_check_tree() {   # ssh_check_tree TREE
  case "$1" in /*) ;; *) refuse "HOME_DIR must be an absolute path (got '$1')" ;; esac
  [ -x "$1/bin/sd-solo" ]  || refuse "$1/bin/sd-solo is not there"
  [ -f "$1/.sdcoresolo" ] || refuse "$1 has no .sdcoresolo marker - not a Solo tree"
  case "$1" in *" "*|*"%"*|*'$'*) refuse "HOME_DIR contains a space, % or \$, which a unit file cannot carry safely: $1" ;; esac
}

# "ssh TREE MODE --print": the two units on stdout, nothing written, no systemctl.
if [ "${1:-}" = "ssh" ] && [ "$#" -eq 4 ] && [ "$4" = "--print" ]; then
  ssh_check_tree "$2"
  case "$3" in
    local|open) ;;
    off) echo "(ssh off: neither unit exists)"; exit 0 ;;
    *) refuse "the ssh mode must be off, local or open (got '$3')" ;;
  esac
  port="$(ssh_port)" || exit $?
  sshd="$(ssh_sshd_path)" || sshd="/usr/sbin/sshd"
  echo "# $SSH_SOCKET"; ssh_socket_text "$3" "$port"
  echo
  echo "# $SSH_TEMPLATE"; ssh_template_text "$2" "$sshd" "$(ssh_python_path)"
  exit 0
fi

command -v systemctl >/dev/null || refuse "systemctl is not available"
systemctl --user is-system-running >/dev/null 2>&1 || {
  st="$(systemctl --user is-system-running 2>&1)"
  case "$st" in running|degraded) ;; *) refuse "the user systemd manager is not running (said: $st)" ;; esac
}

cmd="${1:-}"
case "$cmd" in
  install|remove|status|ssh) shift ;;
  *) refuse "usage: bash $0 install HOME_DIR [--api off|local|open] [--ssh off|local|open] | ssh HOME_DIR off|local|open [--print] | remove | status" ;;
esac

linger_state() { loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo unknown; }

if [ "$cmd" = "ssh" ]; then
  [ "$#" -eq 2 ] || refuse "usage: bash $0 ssh HOME_DIR off|local|open [--print]"
  ssh_check_tree "$1"
  case "$2" in off|local|open) ;; *) refuse "the ssh mode must be off, local or open (got '$2')" ;; esac
  ssh_apply "$1" "$2"
  # LSOLO 32 (4 Oct 2026): "open" behind a running firewall reaches nobody until the port is
  # allowed - measured on the Fedora VM, where it timed out at firewalld.  No sudo here (see the
  # header), so the one command is printed, as for linger.
  if [ "$2" = "open" ]; then
    if command -v firewall-cmd >/dev/null 2>&1 && [ "$(firewall-cmd --state 2>/dev/null)" = running ]; then
      echo "firewalld is running: allow TCP $(ssh_port) or nothing outside this computer reaches it:"
      echo "    sudo firewall-cmd --permanent --add-port=$(ssh_port)/tcp && sudo firewall-cmd --reload"
    elif command -v ufw >/dev/null 2>&1; then
      echo "if ufw is active, allow TCP $(ssh_port) or nothing outside this computer reaches it:"
      echo "    sudo ufw allow $(ssh_port)/tcp"
    fi
  fi
  echo "SOLO SSH LISTENER $2"
  exit 0
fi

if [ "$cmd" = "status" ]; then
  echo "unit directory : $UNITDIR"
  for u in "$DAEMON" "$SOCKET" "$TEMPLATE" "$SSH_SOCKET" "$SSH_TEMPLATE"; do
    [ -f "$UNITDIR/$u" ] && echo "  present      : $u" || echo "  absent       : $u"
  done
  echo "daemon         : $(systemctl --user is-active "$DAEMON" 2>&1)   (enabled: $(systemctl --user is-enabled "$DAEMON" 2>&1))"
  echo "api socket     : $(systemctl --user is-active "$SOCKET" 2>&1)"
  echo "ssh socket     : $(systemctl --user is-active "$SSH_SOCKET" 2>&1)"
  echo "linger         : $(linger_state)"
  exit 0
fi

if [ "$cmd" = "remove" ]; then
  echo "removing the SD Core for Linux Solo user units"
  systemctl --user disable --now "$SSH_SOCKET" >/dev/null 2>&1 || true
  systemctl --user disable --now "$SOCKET" >/dev/null 2>&1 || true
  systemctl --user disable --now "$DAEMON" >/dev/null 2>&1 || true
  for u in "$SSH_SOCKET" "$SSH_TEMPLATE" "$SOCKET" "$TEMPLATE" "$DAEMON"; do rm -f "$UNITDIR/$u"; done
  systemctl --user daemon-reload || fail "daemon-reload"
  for u in "$DAEMON" "$SOCKET" "$SSH_SOCKET"; do
    [ -f "$UNITDIR/$u" ] && fail "$UNITDIR/$u is still there"
  done
  echo "linger is left as it was ($(linger_state)); this script never disables it."
  echo "SOLO SERVICE REMOVED"
  exit 0
fi

# ---- install
[ "$#" -ge 1 ] || refuse "usage: bash $0 install HOME_DIR [--api off|local|open] [--ssh off|local|open]"
H="$1"; shift
ssh_check_tree "$H"

api="off"; ssh="off"; port="4249"; want_linger="no"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --enable-linger) want_linger="yes"; shift ;;
    --api)      [ "$#" -ge 2 ] || refuse "--api needs off, local or open"; api="$2"; shift 2 ;;
    --ssh)      [ "$#" -ge 2 ] || refuse "--ssh needs off, local or open"; ssh="$2"; shift 2 ;;
    *) refuse "unknown argument: $1" ;;
  esac
done
case "$api" in off|local|open) ;; *) refuse "--api must be off, local or open (got '$api')" ;; esac
case "$ssh" in off|local|open) ;; *) refuse "--ssh must be off, local or open (got '$ssh')" ;; esac
if [ -n "${SDSOLO_TEST_API_PORT:-}" ]; then
  port="$SDSOLO_TEST_API_PORT"
  case "$port" in ''|*[!0-9]*) refuse "SDSOLO_TEST_API_PORT must be a number (got '$port')" ;; esac
  [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || refuse "SDSOLO_TEST_API_PORT must be 1024-65535"
  printf '\033[0;33m*** SDSOLO_TEST_API_PORT IS SET: the API port is %s, NOT 4249 (a test hook) ***\033[0m\n' "$port" >&2
fi

echo "solo-service inputs:"
echo "  tree       : $H"
echo "  unit dir   : $UNITDIR"
echo "  api        : $api (port $port)"
echo "  ssh        : $ssh$([ "$ssh" = off ] || echo " (port $(ssh_port))")"
echo "  running as : $(id -un) (uid $(id -u))"

mkdir -p "$UNITDIR" || fail "mkdir $UNITDIR"

# A daemon this tree's own binary started earlier (solo-stage.sh leaves one running)
# would make the unit's "sd -start" fail ("already up"), so stop THAT one first.
"$H/bin/sd-solo" -stop >/dev/null 2>&1 || true

cat > "$UNITDIR/$DAEMON" <<UNIT
[Unit]
Description=SD Core for Linux Solo (daemon)
Documentation=file://$H/sd.conf

[Service]
Type=oneshot
RemainAfterExit=yes
UMask=0077
ExecStart=$H/bin/sd-solo -start
ExecStop=$H/bin/sd-solo -stop

[Install]
WantedBy=default.target
UNIT

# Re-running install to CHANGE the API (off, local, open, another port) must not leave the
# old listener behind: stop and disable the socket unit before its file is rewritten or
# removed (measured 30 Sep 26: after "--api off" systemd still reported the removed unit
# "active", and a changed address was not applied until the unit was restarted).
systemctl --user disable --now "$SOCKET" >/dev/null 2>&1 || true
rm -f "$UNITDIR/$SOCKET" "$UNITDIR/$TEMPLATE"
if [ "$api" != "off" ]; then
  if [ "$api" = "open" ]; then listen="0.0.0.0:$port"; else listen="127.0.0.1:$port"; fi
  cat > "$UNITDIR/$SOCKET" <<UNIT
[Unit]
Description=SD Core for Linux Solo (API listener, $api)

[Socket]
ListenStream=$listen
Accept=true

[Install]
WantedBy=sockets.target
UNIT
  cat > "$UNITDIR/$TEMPLATE" <<UNIT
[Unit]
Description=SD Core for Linux Solo (one API connection)
Requires=$DAEMON
After=$DAEMON

[Service]
UMask=0077
ExecStart=$H/bin/sd-solo -n -q
StandardInput=socket
UNIT
fi

systemctl --user daemon-reload || fail "daemon-reload"
systemctl --user enable --now "$DAEMON" 2>&1 | tail -2
sleep 1
d_state="$(systemctl --user is-active "$DAEMON" 2>&1)"
[ "$d_state" = "active" ] || { systemctl --user status "$DAEMON" --no-pager 2>&1 | tail -12; fail "$DAEMON is '$d_state', not active"; }

if [ "$api" != "off" ]; then
  systemctl --user enable --now "$SOCKET" 2>&1 | tail -2
  s_state="$(systemctl --user is-active "$SOCKET" 2>&1)"
  [ "$s_state" = "active" ] || { systemctl --user status "$SOCKET" --no-pager 2>&1 | tail -12; fail "$SOCKET is '$s_state', not active"; }
fi

# The ssh units; ssh_apply also removes a pair left by an earlier install when this one says off.
ssh_apply "$H" "$ssh"

lg="$(linger_state)"
if [ "$lg" != "yes" ] && [ "$want_linger" = "yes" ]; then
  echo "linger is '$lg': running loginctl enable-linger (no sudo; --enable-linger was given)"
  loginctl enable-linger "$USER" 2>&1 | tail -2 || true
  lg="$(linger_state)"
fi
if [ "$lg" != "yes" ]; then
  echo
  echo "LINGER IS NOT ENABLED.  SD runs while you are signed in, and stops when your last"
  echo "session ends - remote access while you are signed out will NOT work.  As an"
  echo "administrator, once:"
  echo
  echo "    sudo loginctl enable-linger $USER"
  echo
fi

echo "SOLO SERVICE READY daemon=$d_state api=$api ssh=$ssh linger=$lg"
