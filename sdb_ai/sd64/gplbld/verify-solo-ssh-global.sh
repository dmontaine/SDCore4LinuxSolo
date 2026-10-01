#!/bin/bash
# verify-solo-ssh-global.sh - in MANAGED mode, does the forced-command ssh route take the
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
# REFUSED the same command; G5 shows a plain key has a shell, so "no shell" (G4) cannot
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
[ -x "$H/bin/sd" ] || refuse "$H/bin/sd is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -f "$H/\$cred/\$global" ] || refuse "$H is standalone (no \$cred/\$global) - this needs managed mode"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSHTOOL="$here/solo-ssh.sh"
[ -f "$SSHTOOL" ] || refuse "$SSHTOOL is missing"
SD="$H/bin/sd"
SSHD=/usr/sbin/sshd
[ -x "$SSHD" ] || refuse "$SSHD is not installed"
for t in ssh ssh-keygen; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
PORT=12223
ss -ltn 2>/dev/null | grep -q ":$PORT " && refuse "port $PORT is already in use"
pre="$(printf '%s\nWHO\nOFF\n' "$GLOBALPW" | timeout 60 "$SD" 2>&1)"
printf '%s\n' "$pre" | grep -qE '^[0-9]+ sduser' \
  || refuse "no global session works against $H - is its daemon running?"

W="$(mktemp -d)" || refuse "mktemp"
chmod 700 "$W"
SSHD_PID=""
cleanup() {
  [ -n "$SSHD_PID" ] && kill "$SSHD_PID" 2>/dev/null
  rm -rf "$W"
}
trap cleanup EXIT

echo "verify-solo-ssh-global inputs:"
echo "  tree       : $H  (managed: \$cred/\$global present)"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  private sshd: 127.0.0.1:$PORT, work dir $W (removed at the end)"
echo "  ssh        : $(ssh -V 2>&1)"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}

ssh-keygen -q -t ed25519 -N '' -f "$W/host"     || refuse "ssh-keygen (host key)"
ssh-keygen -q -t ed25519 -N '' -f "$W/sdkey"    || refuse "ssh-keygen (sd key)"
ssh-keygen -q -t ed25519 -N '' -f "$W/plainkey" || refuse "ssh-keygen (plain key)"
AKF="$W/authorized_keys"
printf '%s\n' "$(cat "$W/plainkey.pub")" > "$AKF"

cat > "$W/sshd_config" <<CFG
Port $PORT
ListenAddress 127.0.0.1
HostKey $W/host
PidFile $W/sshd.pid
AuthorizedKeysFile $AKF
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM no
StrictModes no
LogLevel VERBOSE
CFG
"$SSHD" -t -f "$W/sshd_config" 2>&1 | head -3
"$SSHD" -D -f "$W/sshd_config" -E "$W/sshd.log" &
SSHD_PID=$!
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT " && break; sleep 0.5; done
ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT " || { tail -5 "$W/sshd.log" 2>&1; refuse "the private sshd did not start"; }

SSHO=(-tt -p "$PORT" -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR)

# Typing rules measured in verify-solo-ssh.sh: wait for the prompt (input typed ahead is
# discarded when sd goes to hidden input), end each line with CR, and run under timeout.
feed() { local l; sleep 3; for l in "$@"; do printf '%s\r' "$l"; sleep 1.5; done; sleep 1; }
ssh_feed() { local key="$1"; shift; feed "$@" | timeout 60 ssh "${SSHO[@]}" -i "$key" 127.0.0.1 2>&1 | strip; }

M30='The denied verbs can only be listed or changed by the SD Core server'

# ---- G1. the key route is installed, and the line is the forced command.
o="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" --authorized-keys "$AKF" 2>&1)"
want="command=\"$H/bin/sd\",restrict,pty $(cat "$W/sdkey.pub")"
if printf '%s\n' "$o" | grep -q '^SOLO SSH KEY ADDED' && grep -qxF -- "$want" "$AKF"; then
  leg "G1 key-add" "SOLO SSH KEY ADDED and the forced-command line is in the file" 0 "$(printf '%s\n' "$o" | tail -1)"
else
  leg "G1 key-add" "SOLO SSH KEY ADDED and the forced-command line is in the file" 1 "$(printf '%s\n' "$o" | tail -1)"
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
o="$(timeout 60 ssh "${SSHO[@]}" -i "$W/sdkey" 127.0.0.1 'echo $((6*7))' </dev/null 2>&1 | strip)"
if ! printf '%s\n' "$o" | grep -qx '42'; then
  leg "G4 the forced key runs no shell command" "'echo \$((6*7))' prints no 42" 0 "no 42"
else
  leg "G4 the forced key runs no shell command" "'echo \$((6*7))' prints no 42" 1 "42 was printed"
fi

# ---- G5. THE CONTROL for G4: a plain key over the same sshd does run it.
o="$(timeout 60 ssh "${SSHO[@]}" -i "$W/plainkey" 127.0.0.1 'echo $((6*7))' </dev/null 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qx '42'; then
  leg "G5 control: a plain key has a shell" "'echo \$((6*7))' prints 42" 0 "42"
else
  leg "G5 control: a plain key has a shell" "'echo \$((6*7))' prints 42" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

echo "verify-solo-ssh-global: $pass of $legs legs passed"
[ "$fail" -eq 0 ]
