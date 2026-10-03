#!/bin/bash
# probe-solo-ssh-password.sh - can an sshd that is NOT root, started per connection the way Solo's
#                              is, accept its owner's own Linux password?  (LSOLO 29, owner 2 Oct 2026:
#                              ssh into Solo should take account name and password, not a key.)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/probe-solo-ssh-password.sh [--control-only]
#
# NO sudo, nothing installed, nothing of Solo's touched.  It runs a PRIVATE sshd (own host key,
# 127.0.0.1, a high port) as you, with the settings Solo's would have: UsePAM yes, password
# authentication on, ForceCommand a stand-in that prints a marker.  Everything is in a scratch
# directory under $HOME that is removed at the end.
#
# THE TWO PHASES.
#   1. CONTROL, no human: a deliberately WRONG password is typed for you.  It must be refused, and the
#      journal must show PAM's own check refusing it (unix_chkpwd) - otherwise the probe says so and
#      stops, because "accepted" would mean nothing.  (Measured 2 Oct 2026: it is refused.)
#   2. YOUR password: ssh asks "<you>@127.0.0.1's password:" on YOUR terminal and you type your Linux
#      password there.  THIS SCRIPT NEVER SEES IT: ssh reads it from the terminal, not from this script, and
#      only ssh's STANDARD OUTPUT (the stand-in's marker) is captured.  --control-only skips this phase.
#
# It prints the exact ssh command line, what sshd's own log said, the PAM lines of the journal, and ends
# with ONE verdict line.  Exit 0 = your password was accepted and the forced command ran, 1 = it was not,
# 2 = it could not measure.
set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root; the point is a process that is not"
CONTROL_ONLY=0
case "${1:-}" in "") ;; --control-only) CONTROL_ONLY=1 ;; *) refuse "usage: bash $0 [--control-only]" ;; esac
SSHD=/usr/sbin/sshd
[ -x "$SSHD" ] || refuse "$SSHD is not installed"
for t in ssh ssh-keygen python3 systemd-socket-activate journalctl; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
USERNAME="$(id -un)"
PORT=24780
ss -ltn 2>/dev/null | grep -q ":$PORT " && refuse "port $PORT is already in use"

W="$(mktemp -d -p "$HOME" .zz-sshpw-XXXX)" || refuse "mktemp under $HOME"
chmod 700 "$W"
LISTENER=""
cleanup() { [ -n "$LISTENER" ] && kill "$LISTENER" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -f "$W/hostkey" || refuse "ssh-keygen"
cat > "$W/standin.sh" <<'STANDIN'
#!/bin/sh
echo "PROBE-FORCED-COMMAND uid=$(id -u) user=$(id -un) original=[$SSH_ORIGINAL_COMMAND]"
STANDIN
chmod 755 "$W/standin.sh"
cat > "$W/sshd_config" <<CFG
HostKey $W/hostkey
UsePAM yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication no
PermitEmptyPasswords no
AllowUsers $USERNAME
MaxAuthTries 3
LoginGraceTime 30
LogLevel VERBOSE
ForceCommand $W/standin.sh
CFG
"$SSHD" -t -f "$W/sshd_config" || refuse "sshd -t rejected the probe's configuration"

echo "probe-solo-ssh-password inputs:"
echo "  running as   : $USERNAME (uid $(id -u)), sshd: $SSHD ($($SSHD -V 2>&1 | head -1))"
echo "  listener     : systemd-socket-activate --inetd -> sshd -i -e -f $W/sshd_config on 127.0.0.1:$PORT"
echo "  settings     : UsePAM yes, PasswordAuthentication yes, PubkeyAuthentication no, AllowUsers $USERNAME"

# sshd -e logs to stderr; a REGULAR FILE there kills its privilege-separated child (SIGXFSZ), so it goes through a pipe.
systemd-socket-activate --accept --inetd -l "127.0.0.1:$PORT" -- "$SSHD" -i -e -f "$W/sshd_config" 2> >(cat > "$W/listener.log") &
LISTENER=$!
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT " && break; sleep 0.5; done
ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT " || refuse "the listener did not start"

SSHOPT=(-p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o LogLevel=ERROR)

# ---------------------------------------------------------------- phase 1: the control
echo
echo "== phase 1, CONTROL: a deliberately WRONG password =="
MARK1="$(date '+%Y-%m-%d %H:%M:%S')"; sleep 1
ctl="$(python3 - "$PORT" "$USERNAME" <<'PYEOF'
import os, pty, select, sys, time
port, user = sys.argv[1], sys.argv[2]
cmd = ["ssh", "-v", "-p", port, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o",
       "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
       user + "@127.0.0.1"]
pid, fd = pty.fork()
if pid == 0:
    os.execvp("ssh", cmd)
out, sent, t0 = b"", False, time.time()
while time.time() - t0 < 25:
    r, _, _ = select.select([fd], [], [], 1)
    if r:
        try:
            d = os.read(fd, 4096)
        except OSError:
            break
        if not d:
            break
        out += d
        if b"assword:" in out and not sent:
            time.sleep(0.5)
            os.write(fd, b"this-is-a-deliberately-wrong-password\r")
            sent = True
print(out.decode(errors="replace").replace("\r", "").strip())
PYEOF
)"
sleep 1
# The -v output also says how the channel is protected: a password typed at this prompt travels INSIDE
# ssh's encrypted channel (key exchange first, then the password), never in clear text on the wire.
printf '%s\n' "$ctl" | grep -E "password:|Permission denied|kex: algorithm|kex: server->client cipher|Host key fingerprint|Server host key" | sed 's/^debug1: //; s/^/      | /'
pamlines="$(journalctl --since "$MARK1" --no-pager 2>/dev/null | grep -E 'unix_chkpwd|pam_unix\(sshd' | cut -c16-220)"
printf '%s\n' "$pamlines" | sed 's/^/      journal: /'
if printf '%s\n' "$ctl" | grep -q 'Permission denied' && printf '%s\n' "$pamlines" | grep -q 'password check failed'; then
  echo "  CONTROL OK: the wrong password was refused, and PAM's own check (unix_chkpwd) said so"
else
  echo "PROBE RESULT: THE CONTROL DID NOT BEHAVE (the wrong password was not refused by PAM's check); nothing below would mean anything"
  exit 2
fi
if [ "$CONTROL_ONLY" -eq 1 ]; then
  echo "PROBE RESULT: control only - a non-root sshd with UsePAM reaches the Linux password check and refuses a wrong password; a CORRECT password was not tried"
  exit 0
fi

# ---------------------------------------------------------------- phase 2: your password
echo
echo "== phase 2: YOUR Linux password =="
echo "  ssh will now ask for the password of '$USERNAME' on this terminal.  Type it there."
echo "  This script does not see it.  (If you would rather not, press Ctrl-C.)"
echo "  > ssh ${SSHOPT[*]} $USERNAME@127.0.0.1"
MARK2="$(date '+%Y-%m-%d %H:%M:%S')"
ssh "${SSHOPT[@]}" "$USERNAME@127.0.0.1" > "$W/out.txt"
RC=$?
sleep 1
echo
echo "  ssh exit status : $RC"
echo "  ssh output      : $(cat "$W/out.txt" | tr '\n' ' ')"
echo "  sshd's own log  :"
grep -E 'Accepted|Failed|PAM|pam|error|fatal|refused' "$W/listener.log" | cut -c1-200 | sed 's/^/      | /' | tail -8
echo "  journal (PAM, since the second phase began):"
journalctl --since "$MARK2" --no-pager 2>/dev/null | grep -i -E 'pam_|unix_chkpwd|sshd' | cut -c16-220 | sed 's/^/      | /' | tail -10
if [ "$RC" -eq 0 ] && grep -q '^PROBE-FORCED-COMMAND' "$W/out.txt" && grep -q 'Accepted password' "$W/listener.log"; then
  echo "PROBE RESULT: YOUR password was ACCEPTED by a non-root sshd and the forced command ran as $USERNAME"
  exit 0
fi
echo "PROBE RESULT: your password was NOT accepted, or the session did not start (see the lines above)"
exit 1
