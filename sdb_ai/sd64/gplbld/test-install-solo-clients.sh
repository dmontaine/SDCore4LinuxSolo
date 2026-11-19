#!/bin/bash
#
# test-install-solo-clients.sh - the Solo installer's block that puts the clean-room client library from the release package into the built tree's bin
# (S.262, 19 Nov 2026, carried from SD Core's test-install-clients.sh: the source builds no client library any more).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-solo-clients.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-solo-clients.sh --selftest
#   INSTALLER=<a copy of the installer> bash .../test-install-solo-clients.sh      (what --selftest uses)
#
# FREE CHECK: no sudo, no install, no sd.  Everything happens in a scratch directory.  Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
# WHAT IT RUNS.  The text between "# CLIENTS-BEGIN" and "# CLIENTS-END" of installsdsolo.sh, under the installer's OWN "set -euo pipefail", with the
# real "install" on scratch files, say / warn as the installer has them, and ldd a function that answers with the libssl the row names.
#
#   K1  OpenSSL 3: both files of clients/Linux64 are put in the built tree's bin, mode 755, content equal; the success line counts 2
#   K2  OpenSSL 4: from clients/Linux64-openssl4
#   K3  no clients folder, and no installer directory: nothing installed, said so, exit 0
#   K4  no build for this OpenSSL: nothing installed, said so, exit 0
#   K5  a symbolic link is left alone
#   S   static: the block comes after "Build complete." and before the stage and bootstrap; it has no exit

HERE="$(cd "$(dirname "$0")" && pwd)"
THIS="$HERE/$(basename "$0")"
INST="${INSTALLER:-$(cd "$HERE/../../.." && pwd)/installsdsolo.sh}"

if [ "${1:-}" = "--selftest" ]; then
  REAL="$(cd "$HERE/../../.." && pwd)/installsdsolo.sh"
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  caught=0; missed=0; total=0
  mutant() {   # name, sed expression
    local name="$1" expr="$2" f="$T/$1.sh" rc
    total=$((total+1))
    sed -e "$expr" "$REAL" > "$f"
    if cmp -s "$REAL" "$f"; then echo "  [MISSED] $name: the mutation changed nothing"; missed=$((missed+1)); return; fi
    INSTALLER="$f" bash "$THIS" > "$T/$name.out" 2>&1; rc=$?
    if [ "$rc" -ne 0 ]; then echo "  [caught] $name (exit $rc)"; caught=$((caught+1))
    else echo "  [MISSED] $name: the check still passed"; missed=$((missed+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  INSTALLER="$REAL" bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  B='/^# CLIENTS-BEGIN/,/^# CLIENTS-END/'
  mutant group-writable     "$B s/install -m 755/install -m 775/"
  mutant follows-links      "$B s/ \&\& \[ ! -L \"\$clients_src\/\$clients_f\" \]//"
  mutant ignores-openssl    "$B s/if \[ \"\$clients_ssl\" = \"4\" \]; then/if false; then/"
  mutant counts-nothing     "$B s/clients_installed=\$((clients_installed+1))/:/"
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

OPTS=$(grep -E '^set -' "$INST" | head -1)
BLOCK=$(awk '/^# CLIENTS-BEGIN/{f=1;next} /^# CLIENTS-END/{f=0} f{print}' "$INST")
echo "installer : $INST"
echo "options   : ${OPTS:-<none found>}"
printf '%s\n' "$OPTS" | grep -q '^set -' || { echo "test-install-solo-clients: CANNOT RUN - no set line in the installer"; exit 2; }
[ -z "$BLOCK" ] && { echo "test-install-solo-clients: CANNOT RUN - no block between CLIENTS-BEGIN and CLIENTS-END (nothing to check)"; exit 2; }
echo "block     : $(printf '%s\n' "$BLOCK" | wc -l) lines"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}
ok() { [ "$1" = yes ] && echo 0 || echo 1; }

run_block() {   # run_block PKGDIR(or -) SSL - prints the block's output, then RC=n; the built bin is $T/src/bin
  local pkg="$1" ssl="$2"
  rm -rf "$T/src"; mkdir -p "$T/src/bin"; : > "$T/src/bin/sd-solo"
  local instdir="$pkg"; [ "$pkg" = - ] && instdir=""
  {
    printf '%s\n' "$OPTS"
    echo "YELLOW=''; NC=''"
    echo "installer_dir='$instdir'; SRC='$T/src'; SSLV='$ssl'"
    cat <<'EOS'
say()  { printf '%s\n' "$*"; }
warn() { printf '%b%s%b\n' "$YELLOW" "$*" "$NC"; }
ldd() { printf '\tlibssl.so.%s => /usr/lib/x86_64-linux-gnu/libssl.so.%s (0x0)\n' "$SSLV" "$SSLV"; }
EOS
    printf '%s\n' "$BLOCK"
    echo "echo END-OF-BLOCK"
  } > "$T/run.sh"
  bash "$T/run.sh" 2>&1; echo "RC=$?"
}
mkpkg() {
  rm -rf "$1"; mkdir -p "$1/clients/Linux64" "$1/clients/Linux64-openssl4"
  for n in sdclilib.so libsdcli.so; do echo "ssl3 $n" > "$1/clients/Linux64/$n"; echo "ssl4 $n" > "$1/clients/Linux64-openssl4/$n"; done
}
mode() { stat -c %a "$1" 2>/dev/null; }

mkpkg "$T/pkg"
out=$(run_block "$T/pkg" 3)
row "K1 OpenSSL 3: both names in the built bin, from clients/Linux64" "$(ok "$(grep -q '^ssl3 sdclilib.so$' "$T/src/bin/sdclilib.so" 2>/dev/null && grep -q '^ssl3 libsdcli.so$' "$T/src/bin/libsdcli.so" 2>/dev/null && echo yes)")" "bin: $(ls "$T/src/bin") | $out"
row "K1 ... mode 755"                                "$(ok "$([ "$(mode "$T/src/bin/sdclilib.so")" = 755 ] && [ "$(mode "$T/src/bin/libsdcli.so")" = 755 ] && echo yes)")" "$(mode "$T/src/bin/sdclilib.so")"
row "K1 ... the success line counts 2, the block ends 0" "$(ok "$(printf '%s' "$out" | grep -q 'Installed the client library (2 files, OpenSSL 3)' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block "$T/pkg" 4)
row "K2 OpenSSL 4: from clients/Linux64-openssl4"    "$(ok "$(grep -q '^ssl4 sdclilib.so$' "$T/src/bin/sdclilib.so" 2>/dev/null && echo yes)")" "$out"
rm -rf "$T/bare"; mkdir "$T/bare"
out=$(run_block "$T/bare" 3)
row "K3 no clients folder: nothing installed, said so, exit 0" "$(ok "$([ ! -e "$T/src/bin/sdclilib.so" ] && printf '%s' "$out" | grep -q 'not run from a release package' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block - 3)
row "K3 no installer directory: nothing looked for"  "$(ok "$([ ! -e "$T/src/bin/sdclilib.so" ] && printf '%s' "$out" | grep -q 'not run from a release package' && echo yes)")" "$out"
rm -rf "$T/only4"; mkdir -p "$T/only4/clients/Linux64-openssl4"; echo x > "$T/only4/clients/Linux64-openssl4/sdclilib.so"
out=$(run_block "$T/only4" 3)
row "K4 no build for this OpenSSL: nothing installed, said so, exit 0" "$(ok "$([ ! -e "$T/src/bin/sdclilib.so" ] && printf '%s' "$out" | grep -q "No client library for this system's OpenSSL" && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
rm -rf "$T/lnk"; mkdir -p "$T/lnk/clients/Linux64"; echo target > "$T/lnk/real.so"; ln -s ../../real.so "$T/lnk/clients/Linux64/sdclilib.so"
echo "ssl3 libsdcli.so" > "$T/lnk/clients/Linux64/libsdcli.so"
out=$(run_block "$T/lnk" 3)
row "K5 a link is left alone, the plain file is installed" "$(ok "$([ ! -e "$T/src/bin/sdclilib.so" ] && [ -f "$T/src/bin/libsdcli.so" ] && echo yes)")" "bin: $(ls "$T/src/bin") | $out"
l_built=$(grep -n '^say "Build complete."' "$INST" | head -1 | cut -d: -f1); l_beg=$(grep -n '^# CLIENTS-BEGIN' "$INST" | cut -d: -f1)
l_stage=$(grep -n -- '-- stage and bootstrap' "$INST" | head -1 | cut -d: -f1)
row "S the block follows the build and precedes the stage" "$(ok "$([ -n "$l_built" ] && [ -n "$l_beg" ] && [ -n "$l_stage" ] && [ "$l_built" -lt "$l_beg" ] && [ "$l_beg" -lt "$l_stage" ] && echo yes)")" "lines $l_built $l_beg $l_stage"
row "S the block has no exit"                         "$(ok "$(printf '%s\n' "$BLOCK" | grep -q -E '(^|[^a-z_])exit( |$)' && echo no || echo yes)")" "an exit is in the block"

echo "test-install-solo-clients: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
