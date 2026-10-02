#!/bin/bash
# verify-solo-sshkey.sh - API request 49: the master installs its ssh key (LSOLO 19).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-sshkey.sh HOME_DIR ACCOUNT_PW_FILE GLOBAL_PW_FILE
#
# No sudo.  HOME_DIR is a MANAGED tree (solo-stage.sh with --global-password-file; its
# stage daemon may be running).  This script installs the tree's USER units, runs the
# API on a high port, and removes them again, so STOP any other Solo service first:
# the shared-memory key is machine-wide (a second tree would attach to the first).
# It never touches the real ~/.ssh: the request writes the scratch file named by
# SDSOLO_AUTHORIZED_KEYS, which this script puts in the systemd user manager's
# environment for its duration and takes out again.  Every reply is printed as the
# client received it.
#
# THE CONTROLS: K7 signs in with the ACCOUNT password and must be refused 11041 with the
# file byte-for-byte unchanged; K9 sends shell syntax in the key and must NOT run it
# (a marker file is looked for).  K10 closes the loop: the key the API installed gets an
# ssh login into sd through a private sshd, and the global password makes it a global
# session.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 3 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PW_FILE GLOBAL_PW_FILE"
H="$1"; PWF="$2"; GLF="$3"
for f in "$PWF" "$GLF"; do [ -s "$f" ] || refuse "cannot read the password file $f"; done
GOOD="$(head -1 "$PWF")"; GLOBALPW="$(head -1 "$GLF")"
[ -n "$GOOD" ] && [ -n "$GLOBALPW" ] && [ "$GOOD" != "$GLOBALPW" ] || refuse "the password files must hold two different non-empty passwords"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
[ -f "$H/\$cred/\$global" ] || refuse "$H is standalone - request 49 needs managed mode"
[ -f "$H/tools/solo-ssh.sh" ] || refuse "$H/tools/solo-ssh.sh is missing - the tree predates LSOLO 19"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC="$here/solo-service.sh"; PROBE="$here/scram-probe.py"
[ -f "$SVC" ] && [ -f "$PROBE" ] || refuse "solo-service.sh or scram-probe.py is missing"
for t in ssh ssh-keygen python3 systemctl; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
SSHD=/usr/sbin/sshd; [ -x "$SSHD" ] || refuse "$SSHD is not installed"
SD="$H/bin/sd-solo"
PORT=14244; SSHPORT=12224
ss -ltn 2>/dev/null | grep -qE ":($PORT|$SSHPORT) " && refuse "port $PORT or $SSHPORT is already in use"
# The units have one fixed name per user, so installing this tree's REPLACES an installed
# service's and the cleanup REMOVES them (found 30 Sep: it took the owner's real service
# away).  Refuse when any exist; reinstall the real one afterwards with its own solo-service.sh.
[ ! -e "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/sd-solo.service" ] || refuse "an sd-solo.service unit is installed for this user - this script would replace and then remove it; run 'solo-service.sh remove' on the installed tree first and reinstall it afterwards"
systemctl --user is-active --quiet sd-solo.service && refuse "a Solo service is already active for this user - stop it first (one machine-wide shared-memory key)"

W="$(mktemp -d)" || refuse "mktemp"; chmod 700 "$W"
AK="$W/authorized_keys"; SSHD_PID=""
cleanup() {
  [ -n "$SSHD_PID" ] && kill "$SSHD_PID" 2>/dev/null
  systemctl --user unset-environment SDSOLO_AUTHORIZED_KEYS 2>/dev/null
  bash "$SVC" remove >/dev/null 2>&1
  "$SD" -stop >/dev/null 2>&1
  rm -rf "$W"
}
trap cleanup EXIT

echo "verify-solo-sshkey inputs:"
echo "  tree       : $H  (managed)"
echo "  binary     : $SD  ($(stat -c '%y' "$SD" | cut -c1-19))"
echo "  authorized_keys used by request 49: $AK (scratch; the real ~/.ssh is not touched)"
echo "  API        : 127.0.0.1:$PORT (SDSOLO_TEST_API_PORT=$PORT; the product's port is 4249)   private sshd: 127.0.0.1:$SSHPORT"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}

for k in a b c d e plain; do ssh-keygen -q -t ed25519 -N '' -f "$W/$k" || refuse "ssh-keygen $k"; done
cp "$W/plain.pub" "$AK"                      # the user's own line, which must survive everything
fp_of() { ssh-keygen -l -f "$1" | awk '{print $2}'; }
FORCED="command=\"$H/bin/sd-solo\",restrict,pty"
ours() { grep -cF -- "$FORCED " "$AK"; }

"$SD" -stop >/dev/null 2>&1
systemctl --user set-environment "SDSOLO_AUTHORIZED_KEYS=$AK" || refuse "cannot set the user manager's environment"
# LSOLO 23: there is no --api-port; the private port goes through the announced test hook.
out="$(SDSOLO_TEST_API_PORT="$PORT" bash "$SVC" install "$H" --api local 2>&1 | strip | grep -E '^SOLO SERVICE READY' | tail -1)"
[ -n "$out" ] || refuse "solo-service.sh install did not say READY"
echo "  service    : $out"

api() {   # api PASSWORD ARG...  -> the probe's output, logged in as sduser
  local pw="$1"; shift
  SD_SCRAM_PASSWORD="$pw" timeout 90 python3 "$PROBE" --port "$PORT" --user sduser "$@" 2>&1 | strip
}
VERIFIED='SCRAM: server signature VERIFIED'
field() { printf '%s\n' "$1" | sed -n "s/^| field $2: //p" | head -1; }
keyline() { cat "$W/$1.pub" | tr -d '\n'; }
M41='Only the SD Core server may manage ssh keys'
M42='The ssh key request was refused: the key or fingerprint is not valid'
M43='The ssh key request was refused: four Solo ssh keys are already installed'
M45='The ssh key request was refused: unknown request, use ADD, REMOVE or LIST'
HOSTFP=""; [ -r /etc/ssh/ssh_host_ed25519_key.pub ] && HOSTFP="$(fp_of /etc/ssh/ssh_host_ed25519_key.pub)"

# ---- K1. a global session lists nothing at first.
o="$(api "$GLOBALPW" --sshkey LIST)"
if printf '%s\n' "$o" | grep -qx "$VERIFIED" && printf '%s\n' "$o" | grep -qx 'ssh-key LIST: OK, 0 field(s)'; then
  leg "K1 LIST on a clean file" "VERIFIED, 'ssh-key LIST: OK, 0 field(s)'" 0 "empty"
else
  leg "K1 LIST on a clean file" "VERIFIED, 0 fields" 1 "$(printf '%s\n' "$o" | grep -E 'ssh-key|SCRAM' | head -2 | tr '\n' ' ')"
fi

# ---- K2. ADD: five fields, the right ones, the forced line written, the user's line kept.
o="$(api "$GLOBALPW" --sshkey "ADD=$(keyline a)")"
fpa="$(fp_of "$W/a.pub")"
if printf '%s\n' "$o" | grep -qx 'ssh-key ADD: OK, 5 field(s)' \
   && [ "$(field "$o" 1)" = "$(id -un)" ] && [ "$(field "$o" 2)" = "$(hostname)" ] \
   && [ "$(field "$o" 3)" = "$fpa" ] && [ "$(field "$o" 4)" = "ADDED" ] && [ "$(field "$o" 5)" = "$HOSTFP" ] \
   && grep -qxF -- "$FORCED $(keyline a)" "$AK" && grep -qxF -- "$(cat "$W/plain.pub")" "$AK"; then
  leg "K2 ADD" "user=$(id -un) host=$(hostname) fingerprint=$fpa ADDED, host-key fingerprint, forced line written, own line kept" 0 "$(printf '%s\n' "$o" | grep -E '^\| field' | tr '\n' ' ')"
else
  leg "K2 ADD" "5 fields (user, host, fingerprint, ADDED, host key), forced line written" 1 "$(printf '%s\n' "$o" | grep -E 'ssh-key|field|SCRAM' | head -7 | tr '\n' ' ')"
fi

# ---- K3. the same key again is PRESENT and adds no line.
o="$(api "$GLOBALPW" --sshkey "ADD=$(keyline a)")"
if [ "$(field "$o" 4)" = "PRESENT" ] && [ "$(ours)" -eq 1 ]; then
  leg "K3 ADD twice" "PRESENT, still one Solo line" 0 "PRESENT"
else
  leg "K3 ADD twice" "PRESENT, still one Solo line" 1 "field4='$(field "$o" 4)' lines=$(ours)"
fi

# ---- K4. four keys are allowed; the fifth is refused 11043 and nothing changes.
for k in b c d; do api "$GLOBALPW" --sshkey "ADD=$(keyline $k)" >/dev/null; done
before="$(sha256sum "$AK" | cut -d' ' -f1)"
o="$(api "$GLOBALPW" --sshkey "ADD=$(keyline e)")"
after="$(sha256sum "$AK" | cut -d' ' -f1)"
if [ "$(ours)" -eq 4 ] && printf '%s\n' "$o" | grep -qF "ssh-key ADD: REFUSED: $M43" && [ "$before" = "$after" ]; then
  leg "K4 the cap" "4 Solo lines, the fifth refused '$M43', file unchanged" 0 "refused"
else
  leg "K4 the cap" "4 Solo lines, the fifth refused 11043, file unchanged" 1 "lines=$(ours) $(printf '%s\n' "$o" | grep -E 'ssh-key' | head -1)"
fi

# ---- K5. LIST names all four.
o="$(api "$GLOBALPW" --sshkey LIST)"
ok=0; for k in a b c d; do printf '%s\n' "$o" | grep -qF -- "$(fp_of "$W/$k.pub")" && ok=$((ok+1)); done
if printf '%s\n' "$o" | grep -qx 'ssh-key LIST: OK, 4 field(s)' && [ "$ok" -eq 4 ]; then
  leg "K5 LIST" "4 fields, the four fingerprints" 0 "4 of 4"
else
  leg "K5 LIST" "4 fields, the four fingerprints" 1 "$(printf '%s\n' "$o" | grep -E 'ssh-key' | head -1) found=$ok"
fi

# ---- K6. REMOVE takes one key, says ABSENT the second time, and leaves the user's line.
o1="$(api "$GLOBALPW" --sshkey "REMOVE=$(fp_of "$W/b.pub")")"
o2="$(api "$GLOBALPW" --sshkey "REMOVE=$(fp_of "$W/b.pub")")"
if [ "$(field "$o1" 1)" = "REMOVED" ] && [ "$(field "$o1" 2)" = "3" ] && [ "$(field "$o2" 1)" = "ABSENT" ] \
   && [ "$(ours)" -eq 3 ] && ! grep -qF -- "$(keyline b)" "$AK" && grep -qxF -- "$(cat "$W/plain.pub")" "$AK"; then
  leg "K6 REMOVE" "REMOVED (3 left), then ABSENT; the user's own line is still there" 0 "REMOVED, ABSENT"
else
  leg "K6 REMOVE" "REMOVED/3 then ABSENT; own line kept" 1 "1='$(field "$o1" 1)/$(field "$o1" 2)' 2='$(field "$o2" 1)' lines=$(ours)"
fi

# ---- K7. THE CONTROL: the account password signs in but may not manage keys.
before="$(sha256sum "$AK" | cut -d' ' -f1)"
o="$(api "$GOOD" --sshkey "ADD=$(keyline e)" --sshkey LIST --sshkey "REMOVE=$(fp_of "$W/a.pub")")"
after="$(sha256sum "$AK" | cut -d' ' -f1)"
n="$(printf '%s\n' "$o" | grep -cF "REFUSED: $M41")"
if printf '%s\n' "$o" | grep -qx "$VERIFIED" && [ "$n" -eq 3 ] && [ "$before" = "$after" ]; then
  leg "K7 control: account password" "signed in, ADD, LIST and REMOVE each refused '$M41', file unchanged" 0 "3 refusals"
else
  leg "K7 control: account password" "3 refusals '$M41', file unchanged" 1 "refusals=$n changed=$([ "$before" = "$after" ] && echo no || echo YES) $(printf '%s\n' "$o" | grep -E 'SCRAM' | head -1)"
fi

# ---- K8. bad arguments are refused and change nothing: not a key, a quote, an empty key, a bad verb.
before="$(sha256sum "$AK" | cut -d' ' -f1)"
o1="$(api "$GLOBALPW" --sshkey 'ADD=this is not a key')"
o2="$(api "$GLOBALPW" --sshkey "ADD=ssh-ed25519 AAAAC3\"quote")"
o3="$(api "$GLOBALPW" --sshkey 'ADD')"
o4="$(api "$GLOBALPW" --sshkey 'REMOVE=notafingerprint')"
o5="$(api "$GLOBALPW" --sshkey 'FROB=x')"
after="$(sha256sum "$AK" | cut -d' ' -f1)"
n=0
for o in "$o1" "$o2" "$o3" "$o4"; do printf '%s\n' "$o" | grep -qF "REFUSED: $M42" && n=$((n+1)); done
printf '%s\n' "$o5" | grep -qF "REFUSED: $M45" && n=$((n+1))
if [ "$n" -eq 5 ] && [ "$before" = "$after" ]; then
  leg "K8 bad arguments" "5 refusals (4 not valid, 1 unknown request), file unchanged" 0 "5 of 5"
else
  leg "K8 bad arguments" "5 refusals, file unchanged" 1 "refusals=$n changed=$([ "$before" = "$after" ] && echo no || echo YES)"
fi

# ---- K9. THE CONTROL for injection: shell syntax in the key is data, never run.
mark="$W/pwned"
api "$GLOBALPW" --sshkey "ADD=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA; touch $mark; echo \$(touch $mark) \`touch $mark\`" >/dev/null
api "$GLOBALPW" --sshkey "REMOVE=SHA256:abc; touch $mark" >/dev/null
if [ ! -e "$mark" ] && ! grep -q 'touch' "$AK"; then
  leg "K9 shell syntax is not run" "no marker file, nothing with 'touch' in authorized_keys" 0 "no marker"
else
  leg "K9 shell syntax is not run" "no marker file" 1 "marker exists=$([ -e "$mark" ] && echo YES || echo no)"
fi

# ---- K10. the key the API installed really gets into sd over ssh, and the global password
# makes that a global session (DENY.VERBS lists; the account password would be refused 11030).
ssh-keygen -q -t ed25519 -N '' -f "$W/host" || refuse "ssh-keygen host"
cat > "$W/sshd_config" <<CFG
Port $SSHPORT
ListenAddress 127.0.0.1
HostKey $W/host
PidFile $W/sshd.pid
AuthorizedKeysFile $AK
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM no
StrictModes no
LogLevel VERBOSE
CFG
"$SSHD" -D -f "$W/sshd_config" -E "$W/sshd.log" &
SSHD_PID=$!
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 2>/dev/null | grep -q "127.0.0.1:$SSHPORT " && break; sleep 0.5; done
ss -ltn 2>/dev/null | grep -q "127.0.0.1:$SSHPORT " || refuse "the private sshd did not start"
SSHO=(-tt -p "$SSHPORT" -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes -o LogLevel=ERROR)
feed() { local l; sleep 3; for l in "$@"; do printf '%s\r' "$l"; sleep 1.5; done; sleep 1; }
o="$(feed "$GLOBALPW" WHO DENY.VERBS OFF | timeout 60 ssh "${SSHO[@]}" -i "$W/a" 127.0.0.1 2>&1 | strip)"
if printf '%s\n' "$o" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$o" | grep -qE '^DENY\.VERBS [0-9]+:'; then
  leg "K10 the installed key reaches sd over ssh" "key A and the global password: WHO answers, DENY.VERBS lists" 0 "$(printf '%s\n' "$o" | grep -E '^DENY\.VERBS [0-9]+:' | head -1)"
else
  leg "K10 the installed key reaches sd over ssh" "WHO answers, DENY.VERBS lists" 1 "$(printf '%s\n' "$o" | grep -v '^[[:space:]]*$' | tail -3 | tr '\n' ' ')"
fi

# ---- K11. the audit trail has every verb and no key text.
aud="$H/audit"
if grep -q 'API SSHKEY ADD ADDED fp=.* peer=127\.0\.0\.1$' "$aud" && grep -q 'API SSHKEY REMOVE REMOVED' "$aud" && grep -q 'API SSHKEY ADD REFUSED - CAP' "$aud" \
   && grep -q 'API SSHKEY REFUSED - not a global session' "$aud" && ! grep -q 'AAAAC3NzaC1lZDI1NTE5' "$aud"; then
  leg "K11 audit" "ADDED, REMOVED, CAP and not-a-global-session lines, and no key text" 0 "$(grep -c 'API SSHKEY' "$aud") SSHKEY lines"
else
  leg "K11 audit" "ADDED, REMOVED, CAP and not-a-global-session lines, no key text" 1 "$(grep 'API SSHKEY' "$aud" | head -3 | cut -c1-120 | tr '\n' '|')"
fi

echo "verify-solo-sshkey: $pass of $legs legs passed"
[ "$fail" -eq 0 ]
