#!/bin/bash
# verify-solo-ssh.sh - does ssh on Solo's own port land straight in SD Core for Linux Solo?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-ssh.sh HOME_DIR ACCOUNT_PASSWORD_FILE
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh (daemon running) with
# --account-password-file ACCOUNT_PASSWORD_FILE.  LSOLO 29 (owner, 2 Oct 2026): Solo runs its OWN
# sshd, one process per connection, from the sshd_config that "solo-ssh.sh setup" writes in
# <tree>/sshd.  This script starts exactly that sshd the way the systemd unit does
# (systemd-socket-activate --inetd, "sshd -i -f <tree>/sshd/sshd_config") on a private
# 127.0.0.1 port, so it never touches the machine's sshd, the unit directory or ~/.ssh.  What it
# cannot prove is the systemd unit itself (the unit text is checked by test-sshport-units.py, a
# real start by witness-live-upgrade.sh on the installed Solo).
#
# THE CONTROL: leg K5 runs the same sshd_config WITHOUT its ForceCommand line and shows that a
# shell then answers.  Without it, "no shell" (K4) could pass because nothing could run a shell.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE"
H="$1"; PWF="$2"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -s "$PWF" ] || refuse "cannot read the password file $PWF"
GOOD="$(head -1 "$PWF")"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSHTOOL="$here/solo-ssh.sh"
[ -f "$SSHTOOL" ] || refuse "$SSHTOOL is missing"
SD="$H/bin/sd-solo"
SSHD=/usr/sbin/sshd
[ -x "$SSHD" ] || refuse "$SSHD is not installed"
for t in ssh ssh-keygen scp systemd-socket-activate; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
PORT=12222
CPORT=12223
for p in $PORT $CPORT; do ss -ltn 2>/dev/null | grep -q ":$p " && refuse "port $p is already in use"; done
pre="$(printf '%s\nWHO\nOFF\n' "$GOOD" | timeout 60 "$SD" 2>&1)"
printf '%s\n' "$pre" | grep -qE '^[0-9]+ sduser' \
  || refuse "no session works against $H - is its daemon running (solo-stage.sh leaves it running)?"

W="$(mktemp -d)" || refuse "mktemp"
chmod 700 "$W"
LISTENERS=()
cleanup() {
  local p
  for p in "${LISTENERS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done
  rm -rf "$W"
}
trap cleanup EXIT

echo "verify-solo-ssh inputs:"
echo "  tree       : $H"
echo "  tool       : $SSHTOOL"
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

# ---- S1. setup writes Solo's own sshd directory.
so="$(bash "$SSHTOOL" setup "$H" 2>&1)"
if printf '%s\n' "$so" | grep -q '^SOLO SSHD READY port=4251 ' && [ -f "$H/sshd/sshd_config" ] \
   && [ "$(stat -c %a "$H/sshd")" = 700 ] && [ "$(stat -c %a "$H/sshd/authorized_keys")" = 600 ]; then
  leg "S1 setup" "READY, sshd/ is 0700, the key file 0600" 0 "$(printf '%s\n' "$so" | tail -1 | cut -c1-80)"
else
  leg "S1 setup" "READY, sshd/ is 0700, the key file 0600" 1 "$(printf '%s\n' "$so" | tail -2 | tr '\n' ' ')"
fi

# ---- keys: one that gets sd (added by the tool), one never added.
ssh-keygen -q -t ed25519 -N '' -f "$W/sdkey"      || refuse "ssh-keygen (sd key)"
ssh-keygen -q -t ed25519 -N '' -f "$W/stranger"   || refuse "ssh-keygen (stranger key)"
AKF="$H/sshd/authorized_keys"
cp "$AKF" "$W/authorized_keys.original"

# The control sshd_config: the real one with the forced command taken away.
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

# ---- K1. key-add says so, writes the key line, and is idempotent.
o1="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" 2>&1)"
o2="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" 2>&1)"
n="$(bash "$SSHTOOL" key-list "$H" | grep -x 'SOLO SSH KEYS 1')"
want="restrict,pty $(cat "$W/sdkey.pub")"
if printf '%s\n' "$o1" | grep -q '^SOLO SSH KEY ADDED' && printf '%s\n' "$o2" | grep -q 'already present' \
   && [ -n "$n" ] && grep -qxF -- "$want" "$AKF"; then
  leg "K1 key-add" "adds exactly one 'restrict,pty' line, twice is once" 0 "$n"
else
  leg "K1 key-add" "one key line; second add says 'already present'" 1 "$(printf '%s\n' "$o1" | tail -1) / $(printf '%s\n' "$o2" | tail -1) / list: '$n'"
fi

start_listener "$H/sshd/sshd_config" "$PORT"
start_listener "$H/sshd/sshd_config.control" "$CPORT"
SSHO=(-tt -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR)

# feed LINES... : type each line into the session with a PAUSE before it.  A real
# person types after the prompt appears; input sent the instant the connection
# opens is typed AHEAD of sd, and the pty discards typed-ahead input when sd
# switches its terminal to hidden-password mode - the session then waits for a
# password that was thrown away, for ever.  (MEASURED 30 Sep 2026: the first
# version of this script hung on exactly that, 10 minutes, with nothing on the
# screen.)  Every ssh here also runs under timeout, so a stall is a FAIL, not a hang.
#
# AND EACH LINE ENDS IN CARRIAGE RETURN, not newline: that is what a keyboard's
# Enter sends, and sd's hidden-password input on a terminal takes CR as the end of
# the line.  (MEASURED the same day: with "\n" every later line was typed INTO the
# password field - "Password: ******************".)  bash's own tty driver turns
# CR into newline, so the control shell leg is unaffected.
feed() { local l; sleep 3; for l in "$@"; do printf '%s\r' "$l"; sleep 1.5; done; sleep 1; }
ssh_feed() { local key="$1" port="$2"; shift 2; feed "$@" | timeout 60 ssh "${SSHO[@]}" -p "$port" -i "$key" 127.0.0.1 2>&1 | strip; }

# ---- K2. the key lands in sd at the password prompt and a session works.
o="$(ssh_feed "$W/sdkey" "$PORT" "$GOOD" WHO OFF)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$'; then
  leg "K2 ssh with the key lands in sd" "the password prompt, then WHO answers '<n> sduser'" 0 "$(printf '%s\n' "$o" | grep -E '^[0-9]+ sduser$' | head -1)"
else
  leg "K2 ssh with the key lands in sd" "WHO answers '<n> sduser'" 1 "$(printf '%s\n' "$o" | grep -v '^[[:space:]]*$' | tail -2 | tr '\n' ' ')"
fi

# ---- K3. wrong passwords over ssh are refused (ruling 21: every session asks).  On a
# terminal sd allows THREE tries (login's require.password), so three wrong ones
# end the session; one wrong one would just re-prompt, and the leg would stall.
o="$(ssh_feed "$W/sdkey" "$PORT" 'not-the-password-1' 'not-the-password-2' 'not-the-password-3')"
n_wrong="$(printf '%s\n' "$o" | grep -cx 'Wrong password')"
if [ "$n_wrong" -eq 3 ] && printf '%s\n' "$o" | grep -qx 'Connection terminated'; then
  leg "K3 wrong passwords refused over ssh" "three 'Wrong password', then 'Connection terminated'" 0 "refused after $n_wrong tries"
else
  leg "K3 wrong passwords refused over ssh" "three 'Wrong password', then 'Connection terminated'" 1 "wrong=$n_wrong; $(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

# ---- K4/K5. NO SHELL over the real config - and the CONTROL that the config without its
# ForceCommand does give one.
o4="$(ssh_feed "$W/sdkey" "$PORT" "$GOOD" 'echo $((6*7))' OFF)"
o5="$(ssh_feed "$W/sdkey" "$CPORT" 'echo $((6*7))' exit)"
if printf '%s\n' "$o5" | grep -qx '42'; then
  leg "K5 CONTROL: without the forced command the same key has a shell" "the shell prints 42" 0 "42"
else
  leg "K5 CONTROL: without the forced command the same key has a shell" "the shell prints 42" 1 "no 42 - so K4 below proves nothing: $(printf '%s\n' "$o5" | tail -1)"
fi
if ! printf '%s\n' "$o4" | grep -qx '42'; then
  leg "K4 the key has no shell" "'echo \$((6*7))' does NOT print 42 (sd does not run shell syntax)" 0 "no 42 in $(printf '%s\n' "$o4" | wc -l) lines"
else
  leg "K4 the key has no shell" "no 42" 1 "the shell ran the command"
fi

# ---- K6. forwarding is refused (restrict, and DisableForwarding): a remote forward fails.
o="$(feed "$GOOD" OFF | timeout 60 ssh "${SSHO[@]}" -p "$PORT" -i "$W/sdkey" -o ExitOnForwardFailure=yes -R 15998:127.0.0.1:1 127.0.0.1 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qiE 'remote port forwarding failed|forwarding.*(failed|prohibited)' && ! printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser'; then
  leg "K6 forwarding is refused" "'remote port forwarding failed' and no session" 0 "refused"
else
  leg "K6 forwarding is refused" "'remote port forwarding failed'" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

# ---- K7. scp does not work, and writes nothing.
echo "scp-payload" > "$W/payload"
rm -f "$W/landed"
scp -P "$PORT" -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR \
    -i "$W/sdkey" "$W/payload" "127.0.0.1:$W/landed" >"$W/scp.out" 2>&1 < /dev/null
scp_rc=$?
if [ "$scp_rc" -ne 0 ] && [ ! -e "$W/landed" ]; then
  leg "K7 scp does not work" "scp fails and nothing lands" 0 "rc=$scp_rc"
else
  leg "K7 scp does not work" "scp fails and nothing lands" 1 "rc=$scp_rc landed=$([ -e "$W/landed" ] && echo yes || echo no)"
fi

# ---- K8. a key that was never added is refused, and password login is not on offer.
d1="$(feed "$GOOD" OFF | timeout 30 ssh "${SSHO[@]}" -p "$PORT" -i "$W/stranger" 127.0.0.1 2>&1 | strip | grep -ci 'permission denied')"
d2="$(timeout 30 ssh "${SSHO[@]}" -p "$PORT" -i "$W/stranger" -o PreferredAuthentications=password -o PubkeyAuthentication=no 127.0.0.1 </dev/null 2>&1 | strip | grep -c 'Permission denied (publickey)')"
if [ "$d1" -ge 1 ] && [ "$d2" -ge 1 ]; then
  leg "K8 a stranger's key and a password are refused" "'Permission denied (publickey)' both ways" 0 "key refused, password not offered"
else
  leg "K8 a stranger's key and a password are refused" "'Permission denied (publickey)' both ways" 1 "key-refused=$d1 password-refused=$d2"
fi

# ---- K9. key-remove takes exactly our line away, the file is byte-for-byte as it was, and the
# removed key can no longer log in.
o="$(bash "$SSHTOOL" key-remove "$H" "$W/sdkey.pub" 2>&1 | tail -1)"
denied="$(feed "$GOOD" OFF | timeout 30 ssh "${SSHO[@]}" -p "$PORT" -i "$W/sdkey" 127.0.0.1 2>&1 | strip | grep -ci 'permission denied')"
if [ "$o" = "SOLO SSH KEY REMOVED 1" ] && cmp -s "$AKF" "$W/authorized_keys.original" && [ "$denied" -ge 1 ]; then
  leg "K9 key-remove" "'REMOVED 1', the key file as it was, the key is refused" 0 "$o"
else
  leg "K9 key-remove" "'REMOVED 1', file as it was, key refused" 1 "said '$o'; file-restored=$(cmp -s "$AKF" "$W/authorized_keys.original" && echo yes || echo NO); denied=$denied"
fi
rm -f "$H/sshd/sshd_config.control"

echo
echo "verify-solo-ssh: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
