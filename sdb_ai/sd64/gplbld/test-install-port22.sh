#!/bin/bash
# test-install-port22.sh - installsdsolo.sh's port-22 rule (21 Nov 2026, S.281; owner, relayed by the Windows agent as SOLO 84):
# "Port 22 should not be opened by a solo install as we dont use it" and "if 22 is already open at the time of the install we do not manage it".
# When THIS install brings the ssh server package (no sshd program yet) and nothing listened on port 22, the package's service is stopped and
# disabled right after it is installed; an sshd already installed, port 22 already open, or no `ss` to tell leaves everything as found; the
# uninstall never touches port 22.  No install, no sudo, no apt-get, no systemctl.  Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-port22.sh [--selftest]
#
# THE BLOCK.  installsdsolo.sh keeps the functions between "# PORT22-BEGIN" and "# PORT22-END".  This cuts them out and runs them under the
# installer's own `set -euo pipefail` and IFS, with `sudo` a function, `systemctl` a stub that logs its arguments, `ss` a stub (SD_SS) that
# prints what a case says, and the sshd program a path (SD_SSHD_BIN) that exists or not.  ANCHORED ON THE ARGUMENTS the systemctl stub was
# given and on what the function printed.  The order in install_packages and the uninstaller's silence are read as TEXT.  It cannot say that
# the package's service really stops, or that a real `ss` prints these columns: that is a real-install row, NOT run for this change.
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.
set -euo pipefail
IFS=$'\n\t'
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS="$HERE/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

if [ "${1:-}" = "--selftest" ]; then
  T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
  caught=0; missed=0
  mutant() {   # name, sed expression applied to the installer's whole text
    local f="$T/$1.sh"
    sed -e "$2" "$ROOT/installsdsolo.sh" > "$f"
    if cmp -s "$ROOT/installsdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if INSTALLER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  mutant manages-open-22     's/  if \[ "\$rc" -eq 1 \]; then echo 1; else echo 0; fi/  echo 1/'
  mutant ignores-sshd-there  's/^    if \[ -x "\$SD_SSHD_BIN" \]; then echo 0; return 0; fi/    true/'
  mutant unknown-is-closed   's/command -v "\$ss_cmd" > \/dev\/null 2>\&1 || return 2/command -v "$ss_cmd" > \/dev\/null 2>\&1 || return 1/'
  mutant substring-port      's/\$4 ~ \/:22\$\/ { f = 1 }/$4 ~ \/:22\/ { f = 1 }/'
  mutant leaves-service-on   's/disable --now ssh.socket ssh.service sshd.service/status ssh.service/'
  mutant no-warning          's/WARNING: port 22 may still be open/port 22 is as it was/'
  mutant closes-before-apt   's/^  local p22_ours=0; if \[ "\$ssh_pkg" -eq 1 \]; then p22_ours="\$(port22_ours_to_close)"; fi/  local p22_ours=1/'
  mutant never-called        's/^  \[ "\$p22_ours" -ne 1 \] || close_package_sshd/  true/'
  echo "selftest: $caught caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

[ -r "$INSTALLER" ] || { echo "test-install-port22: CANNOT RUN - no installer at $INSTALLER"; exit 2; }
[ -r "$REMOVER" ] || { echo "test-install-port22: CANNOT RUN - no remover at $REMOVER"; exit 2; }
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
awk '/^# PORT22-BEGIN$/,/^# PORT22-END$/' "$INSTALLER" > "$T/block.sh"
echo "installer : $INSTALLER"
grep -q '^port22_ours_to_close()' "$T/block.sh" || { echo "test-install-port22: CANNOT RUN - no port22_ours_to_close between # PORT22-BEGIN and # PORT22-END"; exit 2; }
printf '#!/bin/sh\nprintf "%%s\\n" "$SS_OUT"\n' > "$T/ss"; chmod +x "$T/ss"
: > "$T/sshd"; chmod +x "$T/sshd"   # an sshd program that exists; "$T/no-sshd" does not

HDR='State  Recv-Q Send-Q Local Address:Port Peer Address:Port'
L4251="LISTEN 0 128 0.0.0.0:4251 0.0.0.0:*"
L22="LISTEN 0 128 0.0.0.0:22 0.0.0.0:*"
L22v6="LISTEN 0 128 [::]:22 [::]:*"
L2222="LISTEN 0 128 0.0.0.0:2222 0.0.0.0:*"

# run_case FUNCTION SSHD SS_BIN SS_OUT [AFTER_OUT] -> the function's output, then RC=<status>, then the systemctl log
run_case() {
  local fn="$1" sshd="$2" ssbin="$3" ssout="$4" log="$T/log.$$.$RANDOM"
  : > "$log"
  LOG="$log" SD_SSHD_BIN="$sshd" SD_SS="$ssbin" SS_OUT="$ssout" bash -c '
    set -euo pipefail
    IFS=$'"'"'\n\t'"'"'
    say()  { printf "%s\n" "$*"; }
    warn() { printf "%s\n" "$*"; }
    sudo() { "$@"; }
    systemctl() { { printf "systemctl"; printf " %s" "$@"; echo; } >> "$LOG"; }
    . "'"$T"'/block.sh"
    '"$fn"'
    echo "RC=$?"
  ' 2>&1 || echo "RC=$?"
  echo "LOG: $(tr '\n' ';' < "$log")"
}
has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

out="$(run_case port22_ours_to_close "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L4251")"
row "R1 no sshd program and nothing on port 22 (only Solo's 4251): this install brings the package, so it prints 1" "$(printf '%s\n' "$out" | head -1 | grep -qx 1 && echo 0 || echo 1)" "$out"
out="$(run_case port22_ours_to_close "$T/sshd" "$T/ss" "$HDR"$'\n'"$L4251")"
row "R2 an sshd program is already there (the machine had ssh): prints 0, left as found" "$(printf '%s\n' "$out" | head -1 | grep -qx 0 && echo 0 || echo 1)" "$out"
out="$(run_case port22_ours_to_close "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L22")"
row "R3 port 22 already open (IPv4): prints 0, we do not manage it" "$(printf '%s\n' "$out" | head -1 | grep -qx 0 && echo 0 || echo 1)" "$out"
out="$(run_case port22_ours_to_close "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L22v6")"
row "R4 port 22 already open (IPv6 [::]:22): prints 0" "$(printf '%s\n' "$out" | head -1 | grep -qx 0 && echo 0 || echo 1)" "$out"
out="$(run_case port22_ours_to_close "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L2222"$'\n'"$L4251")"
row "R5 a listener on 2222 is not port 22: prints 1" "$(printf '%s\n' "$out" | head -1 | grep -qx 1 && echo 0 || echo 1)" "$out"
out="$(run_case port22_ours_to_close "$T/no-sshd" "$T/no-ss" "")"
row "R6 NULL CASE: no \`ss\` to tell, so it cannot know 22 was closed: prints 0, left as found" "$(printf '%s\n' "$out" | head -1 | grep -qx 0 && echo 0 || echo 1)" "$out"
out="$(run_case close_package_sshd "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L4251")"
row "R7 closing: systemctl disable --now of ssh.socket, ssh.service and sshd.service, and 'Port 22 is closed' said when nothing listens after" \
  "$(has "$out" "LOG: systemctl disable --now ssh.socket ssh.service sshd.service;" && has "$out" "Port 22 is closed" && echo 0 || echo 1)" "$out"
out="$(run_case close_package_sshd "$T/no-sshd" "$T/ss" "$HDR"$'\n'"$L22")"
row "R8 closing, but 22 is still listening afterwards: a WARNING, not 'closed'" "$(has "$out" "WARNING: port 22 may still be open" && ! has "$out" "Port 22 is closed" && echo 0 || echo 1)" "$out"

# ---- order in install_packages, and the uninstaller's silence (text) -------------------------------------------------
ip="$(awk '/^install_packages\(\) \{/,/^}/' "$INSTALLER")"
l_dec="$(printf '%s\n' "$ip" | grep -n 'p22_ours="$(port22_ours_to_close)"' | head -1 | cut -d: -f1)"
l_apt="$(printf '%s\n' "$ip" | grep -n 'sudo apt-get -y install \$pk' | head -1 | cut -d: -f1)"
l_cls="$(printf '%s\n' "$ip" | grep -n 'close_package_sshd' | head -1 | cut -d: -f1)"
row "T1 install_packages decides BEFORE apt-get installs the package and closes AFTER it, and only for the openssh-server case" \
  "$([ -n "$l_dec" ] && [ -n "$l_apt" ] && [ -n "$l_cls" ] && [ "$l_dec" -lt "$l_apt" ] && [ "$l_apt" -lt "$l_cls" ] && printf '%s\n' "$ip" | grep -qF 'if [ "$ssh_pkg" -eq 1 ]; then p22_ours="$(port22_ours_to_close)"; fi' && echo 0 || echo 1)" "decide $l_dec, apt $l_apt, close $l_cls"
row "T2 the uninstaller never stops, disables or closes port 22 or the machine's sshd (no ssh.service / sshd.service / ufw 22 in a command)" \
  "$(grep -v '^[[:space:]]*#' "$REMOVER" | grep -qE 'systemctl[^|]*(stop|disable|mask)[^|]*[[:space:]](ssh|sshd)\.(service|socket)|ufw[^|]*(allow|delete|deny)[^|]*[ /]22(/| |$)' && echo 1 || echo 0)"

echo
echo "test-install-port22: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
