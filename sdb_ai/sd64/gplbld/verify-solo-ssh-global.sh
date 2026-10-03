#!/bin/bash
# verify-solo-ssh-global.sh - in MANAGED mode, does Solo's own ssh (port 4251, LSOLO 29) take the
# GLOBAL password and give a global (server) session?  (The master logs in to a client
# as sduser with the global password over ssh - owner, 30 Sep 2026; the question the
# Windows Solo agent was told was unmeasured on Linux.)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-ssh-global.sh HOME_DIR ACCOUNT_PW_FILE GLOBAL_PW_FILE
#
# No sudo.  HOME_DIR is a MANAGED tree (solo-stage.sh with --global-password-file) whose
# daemon is running.  A PRIVATE sshd runs as the person running this: own host key, own
# authorized_keys, 127.0.0.1, a high port, no PAM - the machine's sshd and ~/.ssh are
# never touched.  What a "global session" means is measured by what only it may do:
# DENY.VERBS (message 11030 for everyone else, as in verify-solo-global.sh).
#
# THE CONTROLS: G3 signs in over the same ssh with the ACCOUNT password and must be
# REFUSED the same command; G5 shows the same config without its ForceCommand has a shell, so "no shell" (G4) cannot
# pass because nothing could run one.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 3 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PW_FILE GLOBAL_PW_FILE"
H="$1"; PWF="$2"; GLF="$3"
for f in "$PWF" "$GLF"; do [ -s "$f" ] || refuse "cannot read the password file $f"; done
GOOD="$(head -1 "$PWF")"; GLOBALPW="$(head -1 "$GLF")"
[ -n "$GOOD" ] && [ -n "$GLOBALPW" ] || refuse "a password file's first line is empty"
[ "$GOOD" != "$GLOBALPW" ] || refuse "the account and global passwords are the same - the legs could not tell them apart"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -f "$H/\$cred/\$global" ] || refuse "$H is standalone (no \$cred/\$global) - this needs managed mode"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSHTOOL="$here/solo-ssh.sh"
[ -f "$SSHTOOL" ] || refuse "$SSHTOOL is missing"
SD="$H/bin/sd-solo"
SSHD=/usr/sbin/sshd
[ -x "$SSHD" ] || refuse "$SSHD is not installed"
for t in ssh ssh-keygen systemd-socket-activate; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
PORT=12223
CPORT=12224
for p in $PORT $CPORT; do ss -ltn 2>/dev/null | grep -q ":$p " && refuse "port $p is already in use"; done
pre="$(printf '%s\nWHO\nOFF\n' "$GLOBALPW" | timeout 60 "$SD" 2>&1)"
printf '%s\n' "$pre" | grep -qE '^[0-9]+ sduser' \
  || refuse "no global session works against $H - is its daemon running?"

W="$(mktemp -d)" || refuse "mktemp"
chmod 700 "$W"
LISTENERS=()
cleanup() {
  local p
  for p in "${LISTENERS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done
  rm -f "$H/sshd/sshd_config.control"
  rm -rf "$W"
}
trap cleanup EXIT

echo "verify-solo-ssh-global inputs:"
echo "  tree       : $H  (managed: \$cred/\$global present)"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  listener   : systemd-socket-activate --inetd -> sshd -i -f $H/sshd/sshd_config on 127.0.0.1:$PORT (control, no ForceCommand: $CPORT)"
echo "  work dir   : $W (removed at the end)"
echo "  ssh        : $(ssh -V 2>&1)"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}

# LSOLO 29: Solo's own sshd (the tree's sshd/ directory, written by solo-ssh.sh setup), started the way
# the systemd unit starts it.  The CONTROL listener runs the same config WITHOUT its ForceCommand.
ssh-keygen -q -t ed25519 -N '' -f "$W/sdkey"    || refuse "ssh-keygen (sd key)"
so="$(bash "$SSHTOOL" setup "$H" 2>&1)" || { printf '%s\n' "$so" | tail -3; refuse "solo-ssh.sh setup"; }
AKF="$H/sshd/authorized_keys"
grep -v '^ForceCommand ' "$H/sshd/sshd_config" > "$H/sshd/sshd_config.control"
chmod 600 "$H/sshd/sshd_config.control"

# TRAP (measured 2 Oct 2026): sshd -e writes its log to stderr, and a privilege-separated child that
# writes to a REGULAR FILE is killed by SIGXFSZ (every connection reset before the banner), so the
# log goes through a pipe, never straight to a file.
start_listener() {   # start_listener CONFIG PORT
  systemd-socket-activate --accept --inetd -l "127.0.0.1:$2" -- "$SSHD" -i -e -f "$1" 2> >(cat > "$W/listener-$2.log") &
  LISTENERS+=("$!")
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 2>/dev/null | grep -q "127.0.0.1:$2 " && return 0; sleep 0.5; done
  tail -5 "$W/listener-$2.log" 2>&1
  refuse "the listener on port $2 did not start"
}

SSHO=(-tt -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR)

# Typing rules measured in verify-solo-ssh.sh: wait for the prompt (input typed ahead is
# discarded when sd goes to hidden input), end each line with CR, and run under timeout.
feed() { local l; sleep 3; for l in "$@"; do printf '%s\r' "$l"; sleep 1.5; done; sleep 1; }
ssh_feed() { local key="$1"; shift; feed "$@" | timeout 60 ssh "${SSHO[@]}" -p "$PORT" -i "$key" 127.0.0.1 2>&1 | strip; }

M30='The denied verbs can only be listed or changed by the SD Core server'

# ---- G1. the key is added to Solo's own key file ('restrict,pty <key>'; the forced command is in
# the sshd_config), and the two listeners start.
o="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" 2>&1)"
want="restrict,pty $(cat "$W/sdkey.pub")"
start_listener "$H/sshd/sshd_config" "$PORT"
start_listener "$H/sshd/sshd_config.control" "$CPORT"
if printf '%s\n' "$o" | grep -q '^SOLO SSH KEY ADDED' && grep -qxF -- "$want" "$AKF"; then
  leg "G1 key-add" "SOLO SSH KEY ADDED and the key line is in Solo's key file" 0 "$(printf '%s\n' "$o" | tail -1)"
else
  leg "G1 key-add" "SOLO SSH KEY ADDED and the key line is in Solo's key file" 1 "$(printf '%s\n' "$o" | tail -1)"
fi

# ---- G2. ssh with the key and the GLOBAL password is a global session: DENY.VERBS answers
# 'DENY.VERBS n:' (the list), the success wording; the refusal wording 11030 must be absent.
o="$(ssh_feed "$W/sdkey" "$GLOBALPW" WHO DENY.VERBS OFF)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$o" | grep -qE '^DENY\.VERBS [0-9]+:' \
   && ! printf '%s\n' "$o" | grep -qF "$M30"; then
  leg "G2 ssh + global password = a global session" "WHO answers '<n> sduser' and DENY.VERBS lists ('DENY.VERBS n:'), no 11030" 0 "$(printf '%s\n' "$o" | grep -E '^DENY\.VERBS [0-9]+:' | head -1)"
else
  leg "G2 ssh + global password = a global session" "WHO answers '<n> sduser' and DENY.VERBS lists ('DENY.VERBS n:')" 1 "$(printf '%s\n' "$o" | grep -v '^[[:space:]]*$' | tail -3 | tr '\n' ' ')"
fi

# ---- G3. THE CONTROL: the same ssh with the ACCOUNT password signs in but is refused DENY.VERBS.
o="$(ssh_feed "$W/sdkey" "$GOOD" WHO DENY.VERBS OFF)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$o" | grep -qF "$M30" \
   && ! printf '%s\n' "$o" | grep -qE '^DENY\.VERBS [0-9]+:'; then
  leg "G3 ssh + account password is NOT a global session" "WHO answers, DENY.VERBS refused with 11030" 0 "refused"
else
  leg "G3 ssh + account password is NOT a global session" "WHO answers, DENY.VERBS refused with 11030" 1 "$(printf '%s\n' "$o" | grep -v '^[[:space:]]*$' | tail -3 | tr '\n' ' ')"
fi

# ---- G4. the forced key has no shell: a command asked for over ssh is not run.
o="$(timeout 60 ssh "${SSHO[@]}" -p "$PORT" -i "$W/sdkey" 127.0.0.1 'echo $((6*7))' </dev/null 2>&1 | strip)"
if ! printf '%s\n' "$o" | grep -qx '42'; then
  leg "G4 the forced key runs no shell command" "'echo \$((6*7))' prints no 42" 0 "no 42"
else
  leg "G4 the forced key runs no shell command" "'echo \$((6*7))' prints no 42" 1 "42 was printed"
fi

# ---- G5. THE CONTROL for G4: the same key over the same config WITHOUT its ForceCommand does run it.
o="$(timeout 60 ssh "${SSHO[@]}" -p "$CPORT" -i "$W/sdkey" 127.0.0.1 'echo $((6*7))' </dev/null 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qx '42'; then
  leg "G5 control: without the forced command the same key has a shell" "'echo \$((6*7))' prints 42" 0 "42"
else
  leg "G5 control: without the forced command the same key has a shell" "'echo \$((6*7))' prints 42" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

echo "verify-solo-ssh-global: $pass of $legs legs passed"
[ "$fail" -eq 0 ]
