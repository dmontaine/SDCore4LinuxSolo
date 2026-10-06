#!/bin/bash
# witness-fresh-install.sh - READ-ONLY: what a fresh installsdsolo.sh left behind (LSOLO 30).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/witness-fresh-install.sh [--home DIR] [--since 'YYYY-MM-DD HH:MM:SS']
#
# NO sudo.  Nothing is changed and no password is read.  Run it as the user who owns the tree,
# after the install and (with --since) after one real ssh sign-in:
#
#   ssh -p 4251 -o PubkeyAuthentication=no YOU@127.0.0.1    (your Linux password, then the SD password)
#
# Without --since it checks the install.  With --since TIME it also reads the journal of Solo's
# ssh unit from TIME on: it must show at least one "Accepted password for YOU" and no "Failed
# password", and the lockout guard's file must still be empty (a correct password forgets the
# address and counts nothing).  This is the one step of LSOLO 29 that no run has covered: a
# CORRECT password through the lockout guard.
#
# Every line prints what was read.  A check whose input could not be read says so and the run
# ends 2; it never passes by looking at nothing.
# Exit 0 every check passed, 1 one failed, 2 it could not measure.

set -uo pipefail
refuse() { echo "REFUSED: $*" >&2; exit 2; }
H="$HOME/SDCoreSolo"; SINCE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --home)  [ "$#" -ge 2 ] || refuse "--home needs a directory"; H="$2"; shift 2 ;;
    --since) [ "$#" -ge 2 ] || refuse "--since needs a time"; SINCE="$2"; shift 2 ;;
    *) refuse "unknown option: $1" ;;
  esac
done
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
case "$H" in /*) ;; *) refuse "--home must be an absolute path (got $H)" ;; esac
[ -f "$H/.sdcore-install" ] || refuse "$H/.sdcore-install is not there - nothing is installed at $H"
REPO=/home/don/Projects/SDCore4LinuxSolo
ME="$(id -un)"
pass=0; fail=0
leg() { if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2 | $4"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }

echo "witness-fresh-install inputs:"
echo "  tree      : $H"
echo "  user      : $ME (uid $(id -u))"
echo "  now       : $(date '+%Y-%m-%d %H:%M:%S')"
echo "  since     : ${SINCE:-(not given - install checks only)}"
echo "  stamp     :"; sed 's/^/              /' "$H/.sdcore-install"

# ---- F1. the stamp names the pushed head, and this is not an upgrade.
commit="$(awk '$1=="commit"{print $2}' "$H/.sdcore-install")"
remote="$(git -C "$REPO" ls-remote origin refs/heads/main 2>/dev/null | awk '{print $1}')"
[ -n "$remote" ] || refuse "could not read origin/main from $REPO (no network?) - F1 would compare with nothing"
if [ "$commit" = "$remote" ] && ! grep -q '^upgraded-from' "$H/.sdcore-install" && grep -qx 'mode unmanaged' "$H/.sdcore-install"; then
  leg "F1 stamp" "the commit equals origin/main, unmanaged, no upgraded-from" 0 "${commit:0:7}"
else
  leg "F1 stamp" "the commit equals origin/main, unmanaged, no upgraded-from" 1 "stamp ${commit:0:7} origin/main ${remote:0:7}; $(grep -c '^upgraded-from' "$H/.sdcore-install") upgraded-from line(s)"
fi

# ---- F2. the units: the daemon and the ssh listener on, the API off (the default).
st() { systemctl --user is-active "$1" 2>&1 | head -1; }
d="$(st sd-solo.service)"; s="$(st sd-solo-ssh.socket)"; a="$(st sd-solo-api.socket)"
failed="$(systemctl --user list-units --all --state=failed 'sd-solo*' --no-legend 2>/dev/null | wc -l)"
if [ "$d" = active ] && [ "$s" = active ] && [ "$a" != active ] && [ "$failed" -eq 0 ]; then
  leg "F2 units" "sd-solo.service and sd-solo-ssh.socket active, sd-solo-api.socket not, none failed" 0 "daemon=$d ssh=$s api=$a failed=$failed"
else
  leg "F2 units" "sd-solo.service and sd-solo-ssh.socket active, sd-solo-api.socket not, none failed" 1 "daemon=$d ssh=$s api=$a failed=$failed"
fi

# ---- F3. listeners: 4251 on this computer only, nothing on 4249.
l4251="$(ss -ltn 2>/dev/null | awk '$4 ~ /:4251$/ {print $4}' | head -1)"
l4249="$(ss -ltn 2>/dev/null | awk '$4 ~ /:4249$/ {print $4}' | head -1)"
if [ "$l4251" = "127.0.0.1:4251" ] && [ -z "$l4249" ]; then
  leg "F3 listeners" "127.0.0.1:4251 listening, nothing on 4249" 0 "4251=$l4251 4249=${l4249:-none}"
else
  leg "F3 listeners" "127.0.0.1:4251 listening, nothing on 4249" 1 "4251=${l4251:-none} 4249=${l4249:-none}"
fi

# ---- F4. the ssh server program is there (the installer puts it in when it is missing).
sshd_path="$(command -v sshd || ls /usr/sbin/sshd 2>/dev/null || true)"
if [ -n "$sshd_path" ] && [ -x "$sshd_path" ]; then leg "F4 sshd program" "present" 0 "$sshd_path"; else leg "F4 sshd program" "present" 1 "none found"; fi

# ---- F5. Solo's own sshd configuration.
cfg="$H/sshd/sshd_config"
if [ -f "$cfg" ] && grep -qx 'StrictModes yes' "$cfg" && grep -qx 'PasswordAuthentication yes' "$cfg" && grep -qx 'UsePAM yes' "$cfg" \
   && grep -q "ForceCommand $H/bin/sd-solo" "$cfg" && [ "$(stat -c '%a' "$H/sshd")" = "700" ] && ls "$H"/sshd/*host*key* >/dev/null 2>&1; then
  leg "F5 sshd_config" "StrictModes, PasswordAuthentication, UsePAM yes; ForceCommand names sd-solo; directory 700; a host key" 0 "mode $(stat -c '%a' "$H/sshd")"
else
  leg "F5 sshd_config" "StrictModes, PasswordAuthentication, UsePAM yes; ForceCommand names sd-solo; directory 700; a host key" 1 "$(grep -E '^(StrictModes|PasswordAuthentication|UsePAM|ForceCommand)' "$cfg" 2>&1 | tr '\n' ';')"
fi

# ---- F6. the daemon is Solo's: its own shared-memory key and a daemon running from this tree.
seg="$(ipcs -m 2>/dev/null | awk '$1=="0x53434c11"{print $1}' | head -1)"
dm="$(ps -eo cmd | grep -F "$H/bin/sdlnxd" | grep -v grep | head -1)"
if [ -n "$seg" ] && [ -n "$dm" ]; then leg "F6 daemon" "segment 0x53434c11 and sdlnxd from $H" 0 "$seg / $dm"; else leg "F6 daemon" "segment 0x53434c11 and sdlnxd from $H" 1 "segment=${seg:-none} daemon=${dm:-none}"; fi

# ---- G1. (with --since) a correct password went through the guard.
if [ -n "$SINCE" ]; then
  jr="$(journalctl --user -u 'sd-solo-ssh@*' --since "$SINCE" --no-pager 2>&1)" || refuse "journalctl failed: $(printf '%s\n' "$jr" | head -1)"
  acc="$(printf '%s\n' "$jr" | grep -c "Accepted password for $ME")"
  bad="$(printf '%s\n' "$jr" | grep -c 'Failed password')"
  guard="$(tr -d ' \n' < "$H/sshd/guard.json" 2>/dev/null)"
  if [ "$acc" -ge 1 ] && [ "$bad" -eq 0 ] && [ "$guard" = "{}" ]; then
    leg "G1 correct password" "Accepted password for $ME at least once, no Failed password, guard.json {}" 0 "accepted=$acc failed=$bad guard=$guard"
  else
    leg "G1 correct password" "Accepted password for $ME at least once, no Failed password, guard.json {}" 1 "accepted=$acc failed=$bad guard=${guard:-unreadable}; journal lines read: $(printf '%s\n' "$jr" | wc -l)"
  fi
fi

echo
echo "witness-fresh-install: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
