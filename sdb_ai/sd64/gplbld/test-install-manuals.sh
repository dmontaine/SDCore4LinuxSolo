#!/bin/bash
#
# test-install-manuals.sh - installsdsolo.sh's block that puts the documentation PDFs of a release package into <home>/pdf (S.216 gap 28; SD Core's installsdcore.sh has the same
#                           block, S.143, owner, 3 Nov 2026: "Yes, installer copies them").
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-manuals.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-manuals.sh --selftest
#   INSTALLER=<a copy of the installer> bash .../test-install-manuals.sh      (what --selftest uses)
#
# FREE CHECK: no sudo (Solo's installer uses none), no install, no running sd.  Everything happens in a scratch directory.  Exit 0 every row passed, 1 a row failed, 2 it could not
# run (no block, no set line).
#
# WHAT IT RUNS.  The text between "# MANUALS-PDF-BEGIN" and "# MANUALS-PDF-END", under the installer's OWN "set -euo pipefail" and under IFS=$'\n\t' (Solo's installer sets no
# IFS; this is the stricter of the two and what the other install tests of this directory use), with umask 077 as the installer runs, say and warn as the installer defines them
# (printing plain).  HOME_DIR/bin/sd-solo is a STUB that plays "sd-solo -internal docs.install DIR" the way the real door works: it needs a fresh marker file $internal in the
# install directory and consumes it (LOGIN does), and then it copies each *.pdf of DIR whose name is lower case letters, digits and . _ - and whose contents begin %PDF-, as the verb
# does.  It logs its arguments, whether the marker was there and what its standard input was.
#
#   M1  a pdf folder of three good PDFs: docs.install is asked for exactly that folder, through the internal door (a marker was there, standard input was /dev/null), the copies are
#       made, the marker is gone, the line counts 3
#   M2  one of three has a capital in its name: the verb skips it, the block says WARNING 2 of 3 and the command to run
#   M3  no pdf folder: nothing is asked, the note says so;  M4  the pdf folder is a link: the same;  M5  installer_dir empty: the same
#   M6  no pdf directory in the install: docs.install is not asked;  M7  docs.install copies nothing, or fails: WARNING 0 of 2, the block still ends 0
#   M8  the door refuses (it consumes no marker): the block takes the marker away itself
#   S   the block follows the changes document and precedes the stop of the stage's daemon; it copies only through docs.install (no cp or install); it has no exit
#
# NOT MEASURED HERE, and said so: the real docs.install and the real internal door (sandbox-docs.py in SD Core runs the verb; this tree has no equivalent row), and a real install from a package.

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
  B='/^# MANUALS-PDF-BEGIN/,/^# MANUALS-PDF-END/'
  mutant follows-link        "$B s/ \&\& \[ ! -L \"\$installer_dir\/pdf\" \]//"
  mutant without-pdf-dir     "$B s/^elif \[ -d \"\$HOME_DIR\/pdf\" \]; then/elif true; then/"
  mutant no-marker           "$B{/^    printf 'installsdsolo pid=/d}"
  mutant marker-misnamed     "$B s#> \"\$HOME_DIR/\\\\\\\$internal\"\$#> \"\$HOME_DIR/internal\"#"
  mutant marker-left         "$B{/^    rm -f \"\$HOME_DIR\/\\\\\\\$internal\"\$/d}"
  mutant judged-by-nothing   "$B s/manuals_ok=\$((manuals_ok+1))/manuals_ok=\$manuals_n/"
  mutant failure-aborts      "$B s/docs.install \"\$installer_dir\/pdf\" < \/dev\/null || true/docs.install \"\$installer_dir\/pdf\" < \/dev\/null || exit 3/"
  mutant wrong-folder        "$B s/docs.install \"\$installer_dir\/pdf\"/docs.install \"\$installer_dir\"/"
  mutant stdin-left-open     "$B s/docs.install \"\$installer_dir\/pdf\" < \/dev\/null/docs.install \"\$installer_dir\/pdf\"/"
  mutant copies-itself       "$B s/^    rm -f \"\$HOME_DIR\/\\\\\\\$internal\"\$/    cp \"\$installer_dir\"\/pdf\/*.pdf \"\$HOME_DIR\/pdf\/\"/"
  mutant block-after-the-stop '/^# MANUALS-PDF-BEGIN$/i "$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>\&1 || true'
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

IFS_LINE="IFS=\$'\\n\\t'"
OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-manuals: CANNOT RUN - no set line in the installer"; exit 2; }
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-$IFS_LINE}"
BLOCK=$(awk '/^# MANUALS-PDF-BEGIN/{f=1;next} /^# MANUALS-PDF-END/{f=0} f{print}' "$INST")
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ';')"
[ -z "$BLOCK" ] && { echo "test-install-manuals: CANNOT RUN - no block between MANUALS-PDF-BEGIN and MANUALS-PDF-END (nothing to check)"; exit 2; }
echo "block     : $(printf '%s\n' "$BLOCK" | wc -l) lines"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export BLOCK OPTS T
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}
ok() { [ "$1" = yes ] && echo 0 || echo 1; }
PDFS="$T/home/pdf"

# run_block PKGDIR(or -) PDFDIR(yes|no) [nocopy|crash|refuse]   - prints the block's output, then RC=n; the stub's log is $T/solo.log
run_block() {
  local pkg="$1" pdfd="$2" mode="${3:-}"
  rm -rf "$T/home"; mkdir -p "$T/home/bin"
  [ "$pdfd" = yes ] && mkdir -p "$T/home/pdf"
  : > "$T/solo.log"
  cat > "$T/home/bin/sd-solo" <<'EOS'
#!/bin/bash
# plays "sd-solo -internal docs.install DIR"
{ printf 'sd-solo'; printf ' %s' "$@"; echo; } >> "$SOLO_LOG"
[ "$1" = -internal ] && [ "$2" = docs.install ] || exit 1
if [ -f "$SOLO_HOME/\$internal" ]; then echo "marker=yes" >> "$SOLO_LOG"; else echo "marker=no" >> "$SOLO_LOG"; fi
echo "stdin=$(readlink /proc/self/fd/0)" >> "$SOLO_LOG"
if [ "$SOLO_MODE" = refuse ]; then echo "Connection terminated"; exit 0; fi
if [ ! -f "$SOLO_HOME/\$internal" ]; then echo "Connection terminated"; exit 0; fi
rm -f "$SOLO_HOME/\$internal"                       # LOGIN consumes the marker on admission
[ "$SOLO_MODE" = crash ] && exit 1
[ "$SOLO_MODE" = nocopy ] && exit 0
for f in "$3"/*.pdf; do
  [ -f "$f" ] || continue
  b=$(basename "$f")
  [[ "$b" =~ ^[a-z0-9][a-z0-9._-]*\.pdf$ ]] || { echo "  $b skipped: the name is not lower case letters, digits and . _ -"; continue; }
  [ "$(head -c 5 "$f")" = "%PDF-" ] || { echo "  $b skipped: it does not start with %PDF-"; continue; }
  cp "$f" "$SOLO_HOME/pdf/$b"
done
exit 0
EOS
  chmod 755 "$T/home/bin/sd-solo"
  local instdir="$pkg"; [ "$pkg" = - ] && instdir=""
  printf 'x\n' | SOLO_LOG="$T/solo.log" SOLO_HOME="$T/home" SOLO_MODE="$mode" INSTDIR="$instdir" HOMEDIR="$T/home" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"; installer_dir="$INSTDIR"; RED=; NC=
      say()  { printf "%s\n" "$*"; }
      warn() { printf "%s\n" "$*"; }
      umask 077
      eval "$BLOCK"
      echo END-OF-BLOCK' 2>&1; echo "RC=$?"
}
mkpkg() {   # mkpkg dir name...: a package with a pdf folder holding the named PDFs
  local d="$1"; shift
  rm -rf "$d"; mkdir -p "$d/pdf"
  for n in "$@"; do printf '%%PDF-1.4 %s\n' "$n" > "$d/pdf/$n"; done
}
asked() { grep -c '^sd-solo' "$T/solo.log" || true; }

# ---- M1 -----------------------------------------------------------------------------------------------------------------
mkpkg "$T/pkg" 01-first-steps.pdf 02-sessions-and-locks.pdf 29-sd-tcl-the-terminal-and-the-session.pdf
out=$(run_block "$T/pkg" yes)
row "M1 docs.install is asked for the package's pdf folder, once" "$(ok "$(grep -q -x "sd-solo -internal docs.install $T/pkg/pdf" "$T/solo.log" && [ "$(asked)" = 1 ] && echo yes)")" "$(cat "$T/solo.log")"
row "M1 through the internal door: a fresh marker was there when sd was started, and standard input was /dev/null" "$(ok "$(grep -q -x 'marker=yes' "$T/solo.log" && grep -q -x 'stdin=/dev/null' "$T/solo.log" && echo yes)")" "$(cat "$T/solo.log")"
row "M1 the marker is gone afterwards"                       "$(ok "$([ ! -e "$T/home/\$internal" ] && echo yes)")" "marker left in $T/home"
row "M1 the three PDFs are in the pdf directory"             "$(ok "$([ "$(ls "$PDFS" | wc -l)" = 3 ] && cmp -s "$T/pkg/pdf/01-first-steps.pdf" "$PDFS/01-first-steps.pdf" && echo yes)")" "found: $(ls "$PDFS")"
row "M1 the line counts three, the block ends 0"             "$(ok "$(printf '%s' "$out" | grep -q 'Installed the documentation PDFs (3) into:' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- M2 -----------------------------------------------------------------------------------------------------------------
mkpkg "$T/pkg" 01-first-steps.pdf 02-sessions-and-locks.pdf Admin-Guide.pdf
out=$(run_block "$T/pkg" yes)
row "M2 a capital in a name: WARNING 2 of 3 and the command" "$(ok "$(printf '%s' "$out" | grep -q 'WARNING: 2 of 3 documentation PDFs were installed' && printf '%s' "$out" | grep -q "docs.install $T/pkg/pdf" && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- M3, M4, M5 ---------------------------------------------------------------------------------------------------------
rm -rf "$T/nopdf"; mkdir "$T/nopdf"
out=$(run_block "$T/nopdf" yes)
row "M3 no pdf folder: nothing asked, no marker made, a note" "$(ok "$([ "$(asked)" = 0 ] && [ ! -e "$T/home/\$internal" ] && printf '%s' "$out" | grep -q 'No documentation PDFs beside the installer' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
mkpkg "$T/real" 01-first-steps.pdf
rm -rf "$T/lnk"; mkdir "$T/lnk"; ln -s "$T/real/pdf" "$T/lnk/pdf"
out=$(run_block "$T/lnk" yes)
row "M4 a pdf folder that is a link is not used"             "$(ok "$([ "$(asked)" = 0 ] && [ "$(ls "$PDFS" | wc -l)" = 0 ] && echo yes)")" "$out"
out=$(run_block - yes)
row "M5 no installer directory: nothing asked"               "$(ok "$([ "$(asked)" = 0 ] && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
# ---- M6, M7, M8 ---------------------------------------------------------------------------------------------------------
mkpkg "$T/pkg" 01-first-steps.pdf 02-sessions-and-locks.pdf
out=$(run_block "$T/pkg" no)
row "M6 no pdf directory: docs.install not asked, no marker made, a note" "$(ok "$([ "$(asked)" = 0 ] && [ ! -e "$T/home/\$internal" ] && printf '%s' "$out" | grep -q 'were not installed: there is no pdf directory' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block "$T/pkg" yes nocopy)
row "M7 docs.install copies nothing: WARNING 0 of 2, ends 0" "$(ok "$(printf '%s' "$out" | grep -q 'WARNING: 0 of 2 documentation PDFs' && printf '%s' "$out" | grep -q 'END-OF-BLOCK' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block "$T/pkg" yes crash)
row "M7b docs.install fails (exit 1): WARNING 0 of 2, the install is not stopped" "$(ok "$(printf '%s' "$out" | grep -q 'WARNING: 0 of 2 documentation PDFs' && printf '%s' "$out" | grep -q 'END-OF-BLOCK' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "$out"
out=$(run_block "$T/pkg" yes refuse)
row "M8 the door refuses and consumes no marker: the block removes it, says WARNING 0 of 2, ends 0" "$(ok "$([ ! -e "$T/home/\$internal" ] && printf '%s' "$out" | grep -q 'WARNING: 0 of 2 documentation PDFs' && printf '%s' "$out" | grep -q '^RC=0$' && echo yes)")" "marker: $(ls -A "$T/home" | tr '\n' ' ') / $out"
# ---- S ------------------------------------------------------------------------------------------------------------------
ln_of() { grep -n -m1 -F -x -- "$1" "$INST" | cut -d: -f1; }
l_chg=$(ln_of '# CHANGES-DOC-END'); l_beg=$(ln_of '# MANUALS-PDF-BEGIN'); l_end=$(ln_of '# MANUALS-PDF-END')
l_stop=$(ln_of '"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true')
row "S the block follows the changes document, precedes the stop of the stage's daemon (it needs the daemon the stage left running)" "$(ok "$([ -n "$l_chg" ] && [ -n "$l_beg" ] && [ -n "$l_end" ] && [ -n "$l_stop" ] && [ "$l_chg" -lt "$l_beg" ] && [ "$l_end" -lt "$l_stop" ] && echo yes)")" "lines $l_chg $l_beg $l_end $l_stop"
row "S it copies only through docs.install (no cp, no install)" "$(ok "$(printf '%s\n' "$BLOCK" | grep -v '^\s*#' | grep -q -E '(^|[ ;])(cp|install) ' && echo no || echo yes)")" "a cp or install is in the block"
row "S the block has no exit"                                "$(ok "$(printf '%s\n' "$BLOCK" | grep -q -E '(^|[^a-z_])exit( |$)' && echo no || echo yes)")" "an exit is in the block"

echo "test-install-manuals: $pass passed, $fail failed"
[ "$((pass + fail))" -eq 0 ] && { echo "test-install-manuals: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
