#!/bin/bash
# verify-solo-ssh.sh - does ssh land straight in SD Core for Linux Solo?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-ssh.sh HOME_DIR ACCOUNT_PASSWORD_FILE
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh (daemon running) with
# --account-password-file ACCOUNT_PASSWORD_FILE.  It runs a PRIVATE sshd as the
# person running this - own host key, own authorized_keys file, 127.0.0.1, a high
# port, no PAM - so it never touches the machine's sshd or the user's real
# ~/.ssh.  What it proves is what a key line does; what it cannot prove is the
# machine's own sshd_config, so the Match route is checked for its text and its
# syntax only ("sshd -t"), never applied (that needs sudo).
#
# THE CONTROL: leg K5 shows that a key WITHOUT the forced command gets a real
# shell over the same sshd.  Without it, "no shell" (K4) could pass because
# nothing could run a shell at all.
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
for t in ssh ssh-keygen scp; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
PORT=12222
ss -ltn 2>/dev/null | grep -q ":$PORT " && refuse "port $PORT is already in use"
pre="$(printf '%s\nWHO\nOFF\n' "$GOOD" | timeout 60 "$SD" 2>&1)"
printf '%s\n' "$pre" | grep -qE '^[0-9]+ sduser' \
  || refuse "no session works against $H - is its daemon running (solo-stage.sh leaves it running)?"

W="$(mktemp -d)" || refuse "mktemp"
chmod 700 "$W"
SSHD_PID=""
cleanup() {
  [ -n "$SSHD_PID" ] && kill "$SSHD_PID" 2>/dev/null
  rm -rf "$W"
}
trap cleanup EXIT

echo "verify-solo-ssh inputs:"
echo "  tree       : $H"
echo "  tool       : $SSHTOOL"
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

# ---- keys: one that gets sd (added by the tool), one plain control key.
ssh-keygen -q -t ed25519 -N '' -f "$W/host"       || refuse "ssh-keygen (host key)"
ssh-keygen -q -t ed25519 -N '' -f "$W/sdkey"      || refuse "ssh-keygen (sd key)"
ssh-keygen -q -t ed25519 -N '' -f "$W/plainkey"   || refuse "ssh-keygen (plain key)"
AKF="$W/authorized_keys"
# A pre-existing line of the user's own: it must survive add and remove untouched.
printf '%s\n' "$(cat "$W/plainkey.pub")" > "$AKF"
cp "$AKF" "$W/authorized_keys.original"

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
# CR into newline, so the plain-key shell control leg is unaffected.
feed() { local l; sleep 3; for l in "$@"; do printf '%s\r' "$l"; sleep 1.5; done; sleep 1; }
ssh_feed() { local key="$1"; shift; feed "$@" | timeout 60 ssh "${SSHO[@]}" -i "$key" 127.0.0.1 2>&1 | strip; }

# ---- K1. key-add says so, writes the forced-command line, and is idempotent.
o1="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" --authorized-keys "$AKF" 2>&1)"
o2="$(bash "$SSHTOOL" key-add "$H" "$W/sdkey.pub" --authorized-keys "$AKF" 2>&1)"
n="$(bash "$SSHTOOL" key-list "$H" --authorized-keys "$AKF" | grep -x 'SOLO SSH KEYS 1')"
want="command=\"$H/bin/sd-solo\",restrict,pty $(cat "$W/sdkey.pub")"
if printf '%s\n' "$o1" | grep -q '^SOLO SSH KEY ADDED' && printf '%s\n' "$o2" | grep -q 'already present' \
   && [ -n "$n" ] && grep -qxF -- "$want" "$AKF"; then
  leg "K1 key-add" "adds exactly one forced-command line, twice is once" 0 "$n"
else
  leg "K1 key-add" "one forced-command line; second add says 'already present'" 1 "$(printf '%s\n' "$o1" | tail -1) / $(printf '%s\n' "$o2" | tail -1) / list: '$n'"
fi

# ---- K2. the key lands in sd at the password prompt and a session works.
o="$(ssh_feed "$W/sdkey" "$GOOD" WHO OFF)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$'; then
  leg "K2 ssh with the key lands in sd" "the password prompt, then WHO answers '<n> sduser'" 0 "$(printf '%s\n' "$o" | grep -E '^[0-9]+ sduser$' | head -1)"
else
  leg "K2 ssh with the key lands in sd" "WHO answers '<n> sduser'" 1 "$(printf '%s\n' "$o" | grep -v '^[[:space:]]*$' | tail -2 | tr '\n' ' ')"
fi

# ---- K3. wrong passwords over ssh are refused (ruling 21: every session asks).  On a
# terminal sd allows THREE tries (login's require.password), so three wrong ones
# end the session; one wrong one would just re-prompt, and the leg would stall.
o="$(ssh_feed "$W/sdkey" 'not-the-password-1' 'not-the-password-2' 'not-the-password-3')"
n_wrong="$(printf '%s\n' "$o" | grep -cx 'Wrong password')"
if [ "$n_wrong" -eq 3 ] && printf '%s\n' "$o" | grep -qx 'Connection terminated'; then
  leg "K3 wrong passwords refused over ssh" "three 'Wrong password', then 'Connection terminated'" 0 "refused after $n_wrong tries"
else
  leg "K3 wrong passwords refused over ssh" "three 'Wrong password', then 'Connection terminated'" 1 "wrong=$n_wrong; $(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

# ---- K4/K5. NO SHELL for the forced key - and the CONTROL that a plain key has one.
o4="$(ssh_feed "$W/sdkey" "$GOOD" 'echo $((6*7))' OFF)"
o5="$(ssh_feed "$W/plainkey" 'echo $((6*7))' exit)"
if printf '%s\n' "$o5" | grep -qx '42'; then
  leg "K5 CONTROL: a plain key has a shell" "the shell prints 42" 0 "42"
else
  leg "K5 CONTROL: a plain key has a shell" "the shell prints 42" 1 "no 42 - so K4 below proves nothing: $(printf '%s\n' "$o5" | tail -1)"
fi
if ! printf '%s\n' "$o4" | grep -qx '42'; then
  leg "K4 the forced key has no shell" "'echo \$((6*7))' does NOT print 42 (sd does not run shell syntax)" 0 "no 42 in $(printf '%s\n' "$o4" | wc -l) lines"
else
  leg "K4 the forced key has no shell" "no 42" 1 "the shell ran the command"
fi

# ---- K6. forwarding is refused for the forced key (restrict): a remote forward fails.
o="$(feed "$GOOD" OFF | timeout 60 ssh "${SSHO[@]}" -i "$W/sdkey" -o ExitOnForwardFailure=yes -R 15998:127.0.0.1:1 127.0.0.1 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qiE 'remote port forwarding failed|forwarding.*(failed|prohibited)' && ! printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser'; then
  leg "K6 forwarding is refused" "'remote port forwarding failed' and no session" 0 "refused"
else
  leg "K6 forwarding is refused" "'remote port forwarding failed'" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
fi

# ---- K7. scp does not work against the forced key, and writes nothing.
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

# ---- K8. key-remove takes exactly our line away, the user's own line is
# byte-for-byte as it was, and the removed key can no longer log in.
o="$(bash "$SSHTOOL" key-remove "$H" "$W/sdkey.pub" --authorized-keys "$AKF" 2>&1 | tail -1)"
denied="$(feed "$GOOD" OFF | timeout 30 ssh "${SSHO[@]}" -i "$W/sdkey" 127.0.0.1 2>&1 | strip | grep -ci 'permission denied')"
if [ "$o" = "SOLO SSH KEY REMOVED 1" ] && cmp -s "$AKF" "$W/authorized_keys.original" && [ "$denied" -ge 1 ]; then
  leg "K8 key-remove" "'REMOVED 1', the user's own line unchanged, the key is refused" 0 "$o"
else
  leg "K8 key-remove" "'REMOVED 1', own line unchanged, key refused" 1 "said '$o'; file-restored=$(cmp -s "$AKF" "$W/authorized_keys.original" && echo yes || echo NO); denied=$denied"
fi

# ---- M1/M2. the Match route: its text, and that sshd accepts it (never applied).
mo="$(bash "$SSHTOOL" match "$H" 2>&1)"
if printf '%s\n' "$mo" | grep -q "^    Match User $(id -un)$" \
   && printf '%s\n' "$mo" | grep -q "^        ForceCommand $H/bin/sd-solo$" \
   && printf '%s\n' "$mo" | grep -q '^        DisableForwarding yes$' \
   && printf '%s\n' "$mo" | grep -qx 'SOLO SSH MATCH PRINTED'; then
  leg "M1 match prints the block" "Match User, ForceCommand, DisableForwarding" 0 "printed"
else
  leg "M1 match prints the block" "Match User, ForceCommand, DisableForwarding" 1 "$(printf '%s\n' "$mo" | tail -2 | tr '\n' ' ')"
fi
{ cat "$W/sshd_config"; printf '%s\n' "$mo" | sed -n '/^Match User /,/^        DisableForwarding/p' ; } > "$W/sshd_config.match" 2>/dev/null
# the printed block is indented four spaces under "contents:"; rebuild it plainly.
{ cat "$W/sshd_config"; echo "Match User $(id -un)"; echo "    ForceCommand $H/bin/sd-solo"; echo "    DisableForwarding yes"; } > "$W/sshd_config.match"
if "$SSHD" -t -f "$W/sshd_config.match" >"$W/t.out" 2>&1; then
  leg "M2 sshd accepts the block" "sshd -t exits 0 on the configuration with the block" 0 "sshd -t clean"
else
  leg "M2 sshd accepts the block" "sshd -t exits 0" 1 "$(head -2 "$W/t.out" | tr '\n' ' ')"
fi
echo "  [NOTE] the Match route's --apply and --remove need sudo and are NOT MEASURED"

echo
echo "verify-solo-ssh: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
