#!/bin/bash
# solo-service.sh - run SD Core for Linux Solo as the user's own systemd service.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh install HOME_DIR [--api off|local|open] [--api-port N]
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh remove
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/solo-service.sh status
#
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
#   sd-solo-api.socket     only with --api local|open: the API's listener, port 4243
#                          unless --api-port; 127.0.0.1 for "local", 0.0.0.0 for "open"
#   sd-solo-api@.service   one "sd -n -q" per connection (Accept=true)
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
#   SOLO SERVICE READY daemon=<state> api=<off|local|open> linger=<yes|no>
# and a caller must anchor on THAT, not on an exit code.
#
# Exit 0 done, 1 a step failed, 2 refused to start.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
fail()   { echo "FAILED at: $*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; these are user units and Solo never runs as root"
command -v systemctl >/dev/null || refuse "systemctl is not available"
systemctl --user is-system-running >/dev/null 2>&1 || {
  st="$(systemctl --user is-system-running 2>&1)"
  case "$st" in running|degraded) ;; *) refuse "the user systemd manager is not running (said: $st)" ;; esac
}

UNITDIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DAEMON="sd-solo.service"
SOCKET="sd-solo-api.socket"
TEMPLATE="sd-solo-api@.service"

cmd="${1:-}"
case "$cmd" in
  install|remove|status) shift ;;
  *) refuse "usage: bash $0 install HOME_DIR [--api off|local|open] [--api-port N] | remove | status" ;;
esac

linger_state() { loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo unknown; }

if [ "$cmd" = "status" ]; then
  echo "unit directory : $UNITDIR"
  for u in "$DAEMON" "$SOCKET" "$TEMPLATE"; do
    [ -f "$UNITDIR/$u" ] && echo "  present      : $u" || echo "  absent       : $u"
  done
  echo "daemon         : $(systemctl --user is-active "$DAEMON" 2>&1)   (enabled: $(systemctl --user is-enabled "$DAEMON" 2>&1))"
  echo "api socket     : $(systemctl --user is-active "$SOCKET" 2>&1)"
  echo "linger         : $(linger_state)"
  exit 0
fi

if [ "$cmd" = "remove" ]; then
  echo "removing the SD Core for Linux Solo user units"
  systemctl --user disable --now "$SOCKET" >/dev/null 2>&1 || true
  systemctl --user disable --now "$DAEMON" >/dev/null 2>&1 || true
  for u in "$SOCKET" "$TEMPLATE" "$DAEMON"; do rm -f "$UNITDIR/$u"; done
  systemctl --user daemon-reload || fail "daemon-reload"
  for u in "$DAEMON" "$SOCKET"; do
    [ -f "$UNITDIR/$u" ] && fail "$UNITDIR/$u is still there"
  done
  echo "linger is left as it was ($(linger_state)); this script never disables it."
  echo "SOLO SERVICE REMOVED"
  exit 0
fi

# ---- install
[ "$#" -ge 1 ] || refuse "usage: bash $0 install HOME_DIR [--api off|local|open] [--api-port N]"
H="$1"; shift
case "$H" in /*) ;; *) refuse "HOME_DIR must be an absolute path (got '$H')" ;; esac
[ -x "$H/bin/sd" ]  || refuse "$H/bin/sd is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
case "$H" in *" "*|*"%"*|*'$'*) refuse "HOME_DIR contains a space, % or \$, which a unit file cannot carry safely: $H" ;; esac

api="off"; port="4243"; want_linger="no"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --enable-linger) want_linger="yes"; shift ;;
    --api)      [ "$#" -ge 2 ] || refuse "--api needs off, local or open"; api="$2"; shift 2 ;;
    --api-port) [ "$#" -ge 2 ] || refuse "--api-port needs a number"; port="$2"; shift 2 ;;
    *) refuse "unknown argument: $1" ;;
  esac
done
case "$api" in off|local|open) ;; *) refuse "--api must be off, local or open (got '$api')" ;; esac
case "$port" in ''|*[!0-9]*) refuse "--api-port must be a number (got '$port')" ;; esac
[ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || refuse "--api-port must be 1024-65535: a user cannot bind below 1024"

echo "solo-service inputs:"
echo "  tree       : $H"
echo "  unit dir   : $UNITDIR"
echo "  api        : $api (port $port)"
echo "  running as : $(id -un) (uid $(id -u))"

mkdir -p "$UNITDIR" || fail "mkdir $UNITDIR"

# A daemon this tree's own binary started earlier (solo-stage.sh leaves one running)
# would make the unit's "sd -start" fail ("already up"), so stop THAT one first.
"$H/bin/sd" -stop >/dev/null 2>&1 || true

cat > "$UNITDIR/$DAEMON" <<UNIT
[Unit]
Description=SD Core for Linux Solo (daemon)
Documentation=file://$H/sd.conf

[Service]
Type=oneshot
RemainAfterExit=yes
UMask=0077
ExecStart=$H/bin/sd -start
ExecStop=$H/bin/sd -stop

[Install]
WantedBy=default.target
UNIT

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
ExecStart=$H/bin/sd -n -q
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

echo "SOLO SERVICE READY daemon=$d_state api=$api linger=$lg"
