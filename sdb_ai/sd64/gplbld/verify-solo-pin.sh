#!/bin/bash
# verify-solo-pin.sh - the client library pins the server's TLS certificate on first
# use (LSOLO 19, agreed with Solo for Windows 30 Sep 2026).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-pin.sh HOME_DIR ACCOUNT_PW_FILE
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh (managed or not).  Like
# verify-solo-sshkey.sh it installs the tree's USER units on a high port and removes them
# again, so it REFUSES when an sd-solo.service unit is already installed for this user.
# It uses the freshly built client library (bin/sdclilib.so under sd64, printed with its
# date) through api-probe.py, and a scratch pin store (SD_KNOWN_SERVERS); the real
# ~/.sdcore is never touched.
#
# THE INDEPENDENT MEASUREMENT: the pinned value is compared with the certificate's SHA-256
# computed by openssl s_client / openssl x509 / sha256sum, which share no code with SD.
# THE CONTROLS: P3 replaces the server's identity and must be refused with the audit trail
# showing NO login attempt (nothing was sent before the refusal); P4 removes the pin as the
# message says and must connect and pin the NEW certificate.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PW_FILE"
H="$1"; PWF="$2"
[ -s "$PWF" ] || refuse "cannot read the password file $PWF"
GOOD="$(head -1 "$PWF")"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd-solo" ] || refuse "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || refuse "$H has no .sdcoresolo marker - not a Solo tree"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$here/../bin/sdclilib.so"
SVC="$here/solo-service.sh"; PROBE="$here/api-probe.py"
[ -f "$LIB" ] || refuse "$LIB is not built (run make in sd64)"
[ -f "$SVC" ] && [ -f "$PROBE" ] || refuse "solo-service.sh or api-probe.py is missing"
for t in python3 openssl sha256sum systemctl; do command -v "$t" >/dev/null || refuse "$t is not installed"; done
PORT=14245
ss -ltn 2>/dev/null | grep -q ":$PORT " && refuse "port $PORT is already in use"
[ ! -e "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/sd-solo.service" ] || refuse "an sd-solo.service unit is installed for this user - this script would replace and then remove it; run 'solo-service.sh remove' on the installed tree first and reinstall it afterwards"
systemctl --user is-active --quiet sd-solo.service && refuse "a Solo service is already active for this user - stop it first (one machine-wide shared-memory key)"
[ "$LIB" -nt "$here/../gplsrc/sd_tls.c" ] || refuse "$LIB is older than gplsrc/sd_tls.c - rebuild first, or this would measure a library without the pin"

W="$(mktemp -d)" || refuse "mktemp"; chmod 700 "$W"
STORE="$W/known_servers"
cleanup() { bash "$SVC" remove >/dev/null 2>&1; "$H/bin/sd-solo" -stop >/dev/null 2>&1; rm -rf "$W"; }
trap cleanup EXIT

echo "verify-solo-pin inputs:"
echo "  tree       : $H"
echo "  library    : $(cd "$(dirname "$LIB")" && pwd)/$(basename "$LIB")  ($(stat -c '%y' "$LIB" | cut -c1-19))"
echo "  pin store  : $STORE (scratch)"
echo "  API        : 127.0.0.1:$PORT  (SDSOLO_TEST_API_PORT=$PORT; the product's port is 4249)"
echo "  running as : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}

"$H/bin/sd-solo" -stop >/dev/null 2>&1
# LSOLO 23: there is no --api-port; the private port goes through the announced test hook.
out="$(SDSOLO_TEST_API_PORT="$PORT" bash "$SVC" install "$H" --api local 2>&1 | strip | grep -E '^SOLO SERVICE READY' | tail -1)"
[ -n "$out" ] || refuse "solo-service.sh install did not say READY"
echo "  service    : $out"

probe() { SD_KNOWN_SERVERS="${1:-$STORE}" SD_PROBE_PASSWORD="$GOOD" timeout 90 python3 "$PROBE" --lib "$LIB" --port "$PORT" --user sduser --account sduser WHO 2>&1 | strip; }
server_sha() { echo | timeout 30 openssl s_client -connect "127.0.0.1:$PORT" -tls1_3 2>/dev/null | openssl x509 -outform DER 2>/dev/null | sha256sum | cut -d' ' -f1; }
audit_lines() { wc -l < "$H/audit"; }
KEY="127.0.0.1:$PORT"

# ---- P1. first use: the connection works, and the pin is the certificate's SHA-256.
o="$(probe)"
sha1="$(server_sha)"
if printf '%s\n' "$o" | grep -qx 'SDConnect returned 1' && printf '%s\n' "$o" | grep -qE '^\| [0-9]+ sduser' \
   && [ -n "$sha1" ] && [ "$(cat "$STORE" 2>/dev/null)" = "$KEY $sha1" ]; then
  leg "P1 first use connects and pins" "SDConnect returned 1, WHO answers; the store holds '$KEY' and the SHA-256 openssl computes" 0 "$sha1"
else
  leg "P1 first use connects and pins" "connects; store = '$KEY <openssl's SHA-256>'" 1 "sha='$sha1' store='$(cat "$STORE" 2>/dev/null)' $(printf '%s\n' "$o" | grep -E 'SDConnect|SDError' | head -1)"
fi

# ---- P2. second use: connects, and the store is unchanged.
before="$(sha256sum "$STORE" | cut -d' ' -f1)"
a0="$(audit_lines)"
o="$(probe)"
a1="$(audit_lines)"
after="$(sha256sum "$STORE" | cut -d' ' -f1)"
# THE NULL CASE for P3: a login that reaches the server must leave an audit line, or
# "no audit line after the refused attempt" would hold whether or not a login started.
if printf '%s\n' "$o" | grep -qx 'SDConnect returned 1' && [ "$before" = "$after" ] && [ "$(wc -l < "$STORE")" -eq 1 ] && [ "$a1" -gt "$a0" ]; then
  leg "P2 second use connects, store unchanged, and a login DOES leave an audit line" "SDConnect returned 1, one line, byte-identical, audit $a0 -> $a1" 0 "unchanged; audit $a0 -> $a1"
else
  leg "P2 second use connects, store unchanged" "SDConnect returned 1, store unchanged" 1 "$(printf '%s\n' "$o" | grep -E 'SDConnect|SDError' | head -1)"
fi

# ---- P3. THE CONTROL: the server's identity is replaced.  Refused, store untouched, and
# the server's audit trail gets NO line from the attempt: no login was started.
[ -f "$H/sd-tls/api.pem" ] || refuse "$H/sd-tls/api.pem is not there - cannot replace the identity"
rm -f "$H/sd-tls/api.pem"
n_before="$(audit_lines)"; store_before="$(cat "$STORE")"
o="$(probe)"
n_after="$(audit_lines)"
sha2="$(server_sha)"
if printf '%s\n' "$o" | grep -qx 'SDConnect returned 0' && printf '%s\n' "$o" | grep -q "SDError: THE SERVER'S CERTIFICATE HAS CHANGED" \
   && printf '%s\n' "$o" | grep -qF "remove the line for $KEY" && [ "$sha1" != "$sha2" ] && [ "$store_before" = "$(cat "$STORE")" ] \
   && [ "$n_before" = "$n_after" ]; then
  leg "P3 a replaced certificate is refused" "SDConnect returned 0 'HAS CHANGED', store untouched, no audit line (no login started); the new certificate really differs" 0 "refused; old ${sha1:0:12}... new ${sha2:0:12}..."
else
  leg "P3 a replaced certificate is refused" "refused 'HAS CHANGED', store untouched, audit lines $n_before = $n_after" 1 "audit $n_before->$n_after differs=$([ "$sha1" != "$sha2" ] && echo yes || echo NO) $(printf '%s\n' "$o" | grep -E 'SDConnect|SDError' | head -2 | tr '\n' ' ')"
fi

# ---- P4. the message's remedy works: remove the line, connect, and the NEW certificate is pinned.
: > "$STORE"
o="$(probe)"
if printf '%s\n' "$o" | grep -qx 'SDConnect returned 1' && [ "$(cat "$STORE")" = "$KEY $sha2" ]; then
  leg "P4 removing the pin re-pins the new certificate" "connects; store = '$KEY' and the NEW SHA-256" 0 "$sha2"
else
  leg "P4 removing the pin re-pins the new certificate" "connects; store holds the new SHA-256" 1 "store='$(cat "$STORE")' $(printf '%s\n' "$o" | grep -E 'SDConnect|SDError' | head -1)"
fi

# ---- P5. an unusable store refuses the connection instead of connecting unpinned.
o="$(probe "$W/no-such-directory/known_servers")"
if printf '%s\n' "$o" | grep -qx 'SDConnect returned 0' && printf '%s\n' "$o" | grep -q 'SDError: cannot pin the server: cannot open'; then
  leg "P5 an unusable pin store refuses" "SDConnect returned 0 'cannot pin the server: cannot open'" 0 "refused"
else
  leg "P5 an unusable pin store refuses" "SDConnect returned 0 'cannot pin the server'" 1 "$(printf '%s\n' "$o" | grep -E 'SDConnect|SDError' | head -2 | tr '\n' ' ')"
fi

echo "verify-solo-pin: $pass of $legs legs passed"
[ "$fail" -eq 0 ]
