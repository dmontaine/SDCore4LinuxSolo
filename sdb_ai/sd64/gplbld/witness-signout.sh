#!/bin/bash
# witness-signout.sh - does SD Core for Linux Solo survive the user's LAST sign-out?  (LSOLO 7, open since 30 Sep)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/witness-signout.sh mark  [--home DIR]
#   ... sign out of EVERY session (the desktop included), wait a minute, sign in again ...
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/witness-signout.sh check [--home DIR]
#
# NO sudo.  Read-only apart from one small mark file, ~/.sd-solo-signout-mark.  "mark" records the
# daemon's process id and start time, the service's start time and the boot id.  "check" must find the
# SAME daemon process (same pid, same start time) and the same service start: a daemon that was stopped
# and started again by linger would have a new pid and fail here.  It also shows the user's session list,
# so the reader can see that the sign-out really did leave no session in between: the mark file keeps the
# list at "mark" time, and the journal line count says whether the user manager stopped.
#
# Exit 0 survived, 1 it did not, 2 it could not measure (no mark, no install, no daemon).

set -uo pipefail
refuse() { echo "REFUSED: $*" >&2; exit 2; }
mode="${1:-}"; [ "$#" -ge 1 ] && shift
H="$HOME/SDCoreSolo"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --home) [ "$#" -ge 2 ] || refuse "--home needs a directory"; H="$2"; shift 2 ;;
    *) refuse "unknown option: $1" ;;
  esac
done
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -f "$H/.sdcore-install" ] || refuse "$H/.sdcore-install is not there - nothing is installed at $H"
MARK="$HOME/.sd-solo-signout-mark"
ME="$(id -un)"

snapshot() {
  local pid; pid="$(pgrep -u "$(id -u)" -f "$H/bin/sdlnxd" | head -1)"
  [ -n "$pid" ] || return 1
  echo "daemon_pid=$pid"
  echo "daemon_start=$(ps -o lstart= -p "$pid" | sed 's/  */ /g')"
  echo "service_start=$(systemctl --user show sd-solo.service -p ActiveEnterTimestamp --value)"
  echo "user_manager_start=$(systemctl show "user@$(id -u).service" -p ActiveEnterTimestamp --value)"
  echo "boot_id=$(cat /proc/sys/kernel/random/boot_id)"
  echo "linger=$(loginctl show-user "$ME" -p Linger --value)"
  echo "sessions=$(loginctl list-sessions --no-legend | awk -v u="$ME" '$3==u{print $1":"$5}' | tr '\n' ' ')"
}

case "$mode" in
  mark)
    snap="$(snapshot)" || refuse "no sdlnxd is running from $H - start it first (systemctl --user start sd-solo.service)"
    printf '%s\nmarked_at=%s\n' "$snap" "$(date '+%Y-%m-%d %H:%M:%S')" > "$MARK"
    echo "witness-signout inputs:"; echo "  tree : $H"; echo "  user : $ME"
    echo "marked:"; sed 's/^/  /' "$MARK"
    if [ "$(grep '^linger=' "$MARK" | cut -d= -f2)" != "yes" ]; then
      echo "NOTE: linger is OFF for $ME, so SD is EXPECTED to stop at the last sign-out; the check will say so."
    fi
    echo
    echo "Now sign out of every session, including the desktop, wait a minute, sign in, and run:"
    echo "  bash $0 check"
    ;;
  check)
    [ -f "$MARK" ] || refuse "$MARK is not there - run 'mark' first"
    snap="$(snapshot)" || { echo "witness-signout: [FAIL] no sdlnxd is running from $H after the sign-in"; exit 1; }
    echo "witness-signout inputs:"; echo "  tree : $H"; echo "  user : $ME"; echo "  now  : $(date '+%Y-%m-%d %H:%M:%S')"
    echo "before (the mark):"; sed 's/^/  /' "$MARK"
    echo "after:"; printf '%s\n' "$snap" | sed 's/^/  /'
    g() { grep "^$1=" "$2" | head -1 | cut -d= -f2-; }
    printf '%s\n' "$snap" > "$MARK.now"
    same_boot=0; [ "$(g boot_id "$MARK")" = "$(g boot_id "$MARK.now")" ] && same_boot=1
    same_pid=0;  [ "$(g daemon_pid "$MARK")" = "$(g daemon_pid "$MARK.now")" ] && [ "$(g daemon_start "$MARK")" = "$(g daemon_start "$MARK.now")" ] && same_pid=1
    same_svc=0;  [ "$(g service_start "$MARK")" = "$(g service_start "$MARK.now")" ] && same_svc=1
    mgr_new=0;   [ "$(g user_manager_start "$MARK")" != "$(g user_manager_start "$MARK.now")" ] && mgr_new=1
    rm -f "$MARK.now"
    echo
    echo "  same boot            : $same_boot   (must be 1, or a reboot is being measured, not a sign-out)"
    echo "  same daemon process  : $same_pid"
    echo "  same service start   : $same_svc"
    echo "  user manager restarted: $mgr_new   (1 means the sign-out stopped the user's systemd, as it does without linger)"
    if [ "$same_boot" -ne 1 ]; then echo "witness-signout: CANNOT MEASURE - the computer restarted in between"; exit 2; fi
    if [ "$same_pid" -eq 1 ] && [ "$same_svc" -eq 1 ]; then
      echo "witness-signout: PASS - the same daemon process survived the sign-out"; exit 0
    fi
    echo "witness-signout: FAIL - the daemon was replaced or stopped"; exit 1
    ;;
  *) refuse "usage: bash $0 mark|check [--home DIR]" ;;
esac
