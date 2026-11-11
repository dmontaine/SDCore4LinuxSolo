#!/bin/bash
#
# test-install-changesdoc.sh - installsdsolo.sh's block that copies the changes document into <home>/pdf (S.216 gap 28; SD Core's installsdcore.sh has the same block, owner,
#                              24 Oct 2026: "included with the installer as an additional document and upon installation also copied into the 'shared' directory" - Solo has
#                              no shared account, so the directory is the install directory's pdf, the one the pdf verb reads).
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-changesdoc.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-changesdoc.sh --selftest
#   INSTALLER=<a copy of the installer> bash .../test-install-changesdoc.sh      (what --selftest uses)
#
# FREE CHECK: no sudo (Solo's installer uses none), no install, no sd.  Everything happens in a scratch directory.  Exit 0 every row passed, 1 a row failed, 2 it could not run
# (a refusal to pass on nothing: no block, no set line).
#
# WHAT IT RUNS.  The text between "# CHANGES-DOC-BEGIN" and "# CHANGES-DOC-END", under the installer's OWN "set -euo pipefail" and under IFS=$'\n\t' (Solo's installer sets no
# IFS; this is the stricter of the two and what the other install tests of this directory use), with umask 077 as the installer runs, say and warn as the installer defines them
# (printing plain), and the REAL install command.  installer_dir and HOME_DIR are scratch paths, as the installer sets them.
#
#   C1  three files beside the installer (pdf, html, md of a lower case name sd-core-solo-for-linux-<version>-changes) are copied into <home>/pdf, mode 644 (the umask is
#       077), their content equal, and the success line counts them
#   C2  no file beside the installer: nothing copied, "No changes document beside the installer", exit 0
#   C3  a symbolic link of the right name is left alone;  C4  a name with a capital or a space, other pdf files and SD Core's own sd-core-for-linux-* names are left alone
#   C5  installer_dir empty (not run from a file): nothing is looked for;  C6  no pdf directory
#   C7  a failed copy prints a warning, the block still ends 0, and the count line says it could not be copied
#   S   static: the block follows the documentation block and precedes the manuals block and the stop of the stage's daemon; installer_dir comes from BASH_SOURCE and only when that
#       is a file; the block has no exit
#
# NOT MEASURED HERE, and said so: that a release package really holds the three files (Solo has no mkrelease script yet; they are put beside the installer by hand).

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
  B='/^# CHANGES-DOC-BEGIN/,/^# CHANGES-DOC-END/'
  mutant group-writable       "$B s/-m 644/-m 664/"
  mutant world-writable       "$B s/-m 644/-m 666/"
  mutant private-only         "$B s/-m 644/-m 600/"
  mutant follows-links        "$B s/ \&\& \[ ! -L \"\$changes_f\" \]//"
  mutant any-name             "$B s/if ! \[\[ \"\$changes_b\" =~ .*\]\]; then/if false; then/"
  mutant any-pdf              "$B s#sd-core-solo-for-linux-\*-changes.pdf#*.pdf#"
  mutant cores-names          "$B s#sd-core-solo-for-linux-#sd-core-for-linux-#g"
  mutant without-installer-dir "$B s/^if \[ -n \"\$installer_dir\" \] \&\& /if /"
  mutant without-pdf-dir      "$B s/ \&\& \[ -d \"\$HOME_DIR\/pdf\" \]//"
  mutant wrong-destination    "$B s#\"\$HOME_DIR/pdf/\${changes_b}\"#\"\$HOME_DIR/\${changes_b}\"#"
  mutant failure-aborts       "$B s/^        if install -m 644 \"\$changes_f\" \"\$HOME_DIR\/pdf\/\${changes_b}\"; then/        install -m 644 \"\$changes_f\" \"\$HOME_DIR\/pdf\/\${changes_b}\"; if true; then/"
  mutant counts-nothing       "$B s/changes_copied=\$((changes_copied+1))/:/"
  mutant block-after-the-stop '/^# CHANGES-DOC-BEGIN$/i "$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>\&1 || true'
  mutant installer-dir-from-cwd 's/^if \[ -f "\${BASH_SOURCE\[0\]:-}" \]; then installer_dir=.*$/installer_dir=$(pwd)/'
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

IFS_LINE="IFS=\$'\\n\\t'"
OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-changesdoc: CANNOT RUN - no set line in the installer"; exit 2; }
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-$IFS_LINE}"
BLOCK=$(awk '/^# CHANGES-DOC-BEGIN/{f=1;next} /^# CHANGES-DOC-END/{f=0} f{print}' "$INST")
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ';')"
[ -z "$BLOCK" ] && { echo "test-install-changesdoc: CANNOT RUN - no block between CHANGES-DOC-BEGIN and CHANGES-DOC-END (nothing to check)"; exit 2; }
echo "block     : $(printf '%s\n' "$BLOCK" | wc -l) lines"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export BLOCK OPTS T
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}
ok() { [ "$1" = yes ] && echo 0 || echo 1; }

# run_block PKGDIR(or -) PDFDIR(yes|no) [FAIL]   - prints the block's output, then RC=n
run_block() {
  local pkg="$1" pdfd="$2" failinst="${3:-}"
  rm -rf "$T/home"; mkdir -p "$T/home"
  [ "$pdfd" = yes ] && mkdir -p "$T/home/pdf"
  local instdir="$pkg"; [ "$pkg" = - ] && instdir=""
  INSTDIR="$instdir" FAILINST="$failinst" HOMEDIR="$T/home" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"; installer_dir="$INSTDIR"; RED=; NC=
      say()  { printf "%s\n" "$*"; }
      warn() { printf "%s\n" "$*"; }
      umask 077
      if [ -n "$FAILINST" ]; then install() { return 1; }; fi
      eval "$BLOCK"
      echo END-OF-BLOCK' 2>&1; echo "RC=$?"
}
mkpkg() {   # mkpkg dir: the three files of a good name
  rm -rf "$1"; mkdir -p "$1"
  for e in pdf html md; do echo "doc $e" > "$1/sd-core-solo-for-linux-ls2.0-0-changes.$e"; done
}
PDFS="$T/home/pdf"

# ---- C1 -----------------------------------------------------------------------------------------------------------------
mkpkg "$T/pkg"
out=$(run_block "$T/pkg" yes)
n=$(ls "$PDFS" 2>/dev/null | wc -l)
row "C1 three files copied"                       "$(ok "$([ "$n" = 3 ] && echo yes)")" "found $n files in the pdf directory"
row "C1 content equal"                            "$(ok "$(cmp -s "$T/pkg/sd-core-solo-for-linux-ls2.0-0-changes.pdf" "$PDFS/sd-core-solo-for-linux-ls2.0-0-changes.pdf" && echo yes)")" "pdf differs"
row "C1 mode 644 on all three (the umask is 077, so a plain copy would be 600)" "$(ok "$([ -z "$(find "$PDFS" -type f ! -perm 644)" ] && [ -n "$(find "$PDFS" -type f)" ] && echo yes)")" "modes: $(find "$PDFS" -type f -printf '%m ' 2>/dev/null)"
row "C1 success line counts three"                "$(ok "$(printf '%s' "$out" | grep -q 'Copied the changes document (3 files)' && echo yes)")" "$out"
row "C1 the block ends 0"                         "$(ok "$(printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- C2 -----------------------------------------------------------------------------------------------------------------
rm -rf "$T/empty"; mkdir "$T/empty"
out=$(run_block "$T/empty" yes)
row "C2 none beside: nothing copied"              "$(ok "$([ "$(ls "$PDFS" | wc -l)" = 0 ] && echo yes)")" "files: $(ls "$PDFS")"
row "C2 none beside: said so, exit 0"             "$(ok "$(printf '%s' "$out" | grep -q 'No changes document beside the installer' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- C3, C4 -------------------------------------------------------------------------------------------------------------
rm -rf "$T/odd"; mkdir "$T/odd"; echo target > "$T/odd/real.txt"
ln -s real.txt "$T/odd/sd-core-solo-for-linux-ls9-changes.pdf"
echo x > "$T/odd/sd-core-solo-for-linux-LS2.0-0-changes.pdf"
echo x > "$T/odd/sd-core-solo-for-linux-ls1 2-changes.html"
echo x > "$T/odd/readme.pdf"
echo x > "$T/odd/other-changes.pdf"
for e in pdf html md; do echo x > "$T/odd/sd-core-for-linux-l2.0-0-changes.$e"; done
out=$(run_block "$T/odd" yes)
row "C3 a link is left alone"                     "$(ok "$([ ! -e "$PDFS/sd-core-solo-for-linux-ls9-changes.pdf" ] && echo yes)")" "copied"
row "C4 capital, space, other pdfs and SD Core's own names left alone" "$(ok "$([ "$(ls "$PDFS" | wc -l)" = 0 ] && echo yes)")" "copied: $(ls "$PDFS")"
# ---- C5, C6 -------------------------------------------------------------------------------------------------------------
mkpkg "$T/pkg"
out=$(run_block - yes)
row "C5 no installer directory: nothing looked for" "$(ok "$([ "$(ls "$PDFS" | wc -l)" = 0 ] && printf '%s' "$out" | grep -q 'No changes document was copied' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block "$T/pkg" no)
row "C6 no pdf directory: nothing copied, no directory made" "$(ok "$([ ! -e "$PDFS" ] && printf '%s' "$out" | grep -q 'No changes document was copied' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- C7 -----------------------------------------------------------------------------------------------------------------
out=$(run_block "$T/pkg" yes fail)
row "C7 failed copy: WARNING"                     "$(ok "$(printf '%s' "$out" | grep -q 'WARNING: sd-core-solo-for-linux-ls2.0-0-changes' && echo yes)")" "$out"
row "C7 failed copy: could not be copied, exit 0" "$(ok "$(printf '%s' "$out" | grep -q 'could not be copied' && printf '%s' "$out" | grep -q 'END-OF-BLOCK' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- S ------------------------------------------------------------------------------------------------------------------
ln_of() { grep -n -m1 -F -x -- "$1" "$INST" | cut -d: -f1; }
l_docs=$(ln_of '# DOCS-CORPUS-END'); l_beg=$(ln_of '# CHANGES-DOC-BEGIN'); l_end=$(ln_of '# CHANGES-DOC-END'); l_man=$(ln_of '# MANUALS-PDF-BEGIN')
l_stop=$(ln_of '"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true')
row "S the block follows the documentation block, precedes the manuals block and the stop of the stage's daemon" "$(ok "$([ -n "$l_docs" ] && [ -n "$l_beg" ] && [ -n "$l_end" ] && [ -n "$l_man" ] && [ -n "$l_stop" ] && [ "$l_docs" -lt "$l_beg" ] && [ "$l_end" -lt "$l_man" ] && [ "$l_man" -lt "$l_stop" ] && echo yes)")" "lines $l_docs $l_beg $l_end $l_man $l_stop"
row "S installer_dir from BASH_SOURCE, only when it is a file" "$(ok "$(grep -q '^if \[ -f "\${BASH_SOURCE\[0\]:-}" \]; then installer_dir=' "$INST" && echo yes)")" "line not found"
row "S the block has no exit"                     "$(ok "$(printf '%s\n' "$BLOCK" | grep -q -E '(^|[^a-z_])exit( |$)' && echo no || echo yes)")" "an exit is in the block"

echo "test-install-changesdoc: $pass passed, $fail failed"
[ "$((pass + fail))" -eq 0 ] && { echo "test-install-changesdoc: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
