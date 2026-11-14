#!/bin/bash
#
# test-install-agentpack.sh - installsdsolo.sh's blocks that put the AI guide and knowledge pack in <home>/agent-pack (S.216 gap 26; SD Core's
#                             installsdcore.sh has the same two blocks, S.69 rows 1 and 1b), run the way the installer runs them.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-agentpack.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-agentpack.sh --selftest
#   INSTALLER=<a copy of the installer> bash .../test-install-agentpack.sh      (what --selftest uses)
#
# FREE CHECK: no sudo (Solo's installer uses none), no install, no sd.  Everything happens in a scratch directory.  Exit 0 every row passed,
# 1 a row failed, 2 it could not run (a refusal to pass on nothing: a missing block, or an anchor that is not in the installer).
#
# WHY IT EXISTS.  test-install-pass3.sh (SD Core) says why a block must be tested under the installer's own "set -euo pipefail": a harness that
# evaluated one without those options passed a block that stopped two real installs.  This block is a pipeline-and-test block of exactly that
# kind (a sed that finds no stamp, a file that is not there), and it must NEVER stop an install: the pack is documents, an older tag has none,
# and a documents-only feature does not get to fail an install.
#
# WHAT IT RUNS.  The text between "# AGENTPACK-BEGIN" and "# AGENTPACK-END" (the copy) and between "# AGENTPACK-MODE-BEGIN" and "# AGENTPACK-MODE-END"
# (the file modes), cut out verbatim and evaluated under the options read from the installer's own "set" line and under IFS=$'\n\t' (Solo's
# installer sets no IFS; this is the stricter of the two and what the other install tests of this directory use), with umask 077 as the installer
# runs, say and warn as the installer defines them (printing plain), SRC the "download" - a scratch copy of THIS tree's real sdb_ai/sd64/agent-pack/ -
# holding the real sdsys/gpl.bp/revstamp.h too (the block reads the version from the download since S.234 N1: an installed tree holds no gpl.bp),
# and HOME_DIR a scratch install directory.  The working directory is an empty one: the block must use $SRC.
#
#   A1  the real pack installs: the success line names the version, guide and every pack file are there and byte-equal to the download's
#   A2  nothing else is copied: no skill, templates, recipe, generator or notes
#   A3  no agent-pack in the download / the guide but no manifest / no core.md / no guide: a note, no copy, rc 0, the block reached its end,
#       and an older install's pack is left as it was
#   A4  the manifest's rev_stamp is not the installed revstamp.h's: not installed, the note names both, rc 0
#   A5  no revstamp.h at all / a manifest with no rev_stamp / a manifest that cannot be read: not installed, rc 0
#   A5d a copy that fails: a warning, no half pack left, rc 0;  A5e an upgrade replaces the old pack whole (a stale file is gone)
#   A6  the mode block: files 644, directories 755, nothing writable by group or other (the copy itself is private, 600, under umask 077: the
#       control that the block does something); with no agent-pack it does nothing
#   A7  the order in the installer (text): after the last stage call and the end of the fresh-install branch, before the stop of the stage's daemon;
#       the mode block after the copy
#   A8  neither block has an exit in it
#
# NOT MEASURED HERE, and said so: a real install from a clone (the owner's witness), and that deletesdsolo.sh removes it (it removes the whole tree
# unless --keep-data, which keeps the accounts and sd.conf only).

HERE="$(cd "$(dirname "$0")" && pwd)"
THIS="$HERE/$(basename "$0")"
SD64="$(cd "$HERE/.." && pwd)"
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
  mutant copy-removed            's#^        if mkdir -p "\$HOME_DIR/agent-pack" \&\& cp -R .*; then$#        if true; then#'
  mutant mkdir-removed           's#if mkdir -p "\$HOME_DIR/agent-pack" \&\& cp -R#if cp -R#'
  mutant skill-copied-too        's#cp -R "\$SRC/agent-pack/guide" "\$SRC/agent-pack/pack" #cp -R "$SRC/agent-pack/guide" "$SRC/agent-pack/pack" "$SRC/agent-pack/skill" #'
  mutant generator-copied-too    's#cp -R "\$SRC/agent-pack/guide" "\$SRC/agent-pack/pack" #cp -R "$SRC/agent-pack/guide" "$SRC/agent-pack/pack" "$SRC/agent-pack/mkpack.py" #'
  mutant stamp-test-inverted     's#\[ "\$pack_stamp" = "\$tree_stamp" \]#[ "$pack_stamp" != "$tree_stamp" ]#'
  mutant stamp-test-removed      's#\[ -n "\$pack_stamp" \] \&\& \[ "\$pack_stamp" = "\$tree_stamp" \]#true#'
  mutant hard-stop-when-absent   's#^    say "Note: the download holds no complete AI guide.*#    exit 1#'
  mutant hard-stop-on-mismatch   's#^        say "Note: the AI knowledge pack in the download is for version .*#        exit 1#'
  mutant completeness-dropped    's# \&\& \[ -f "\$SRC/agent-pack/pack/core.md" \]##'
  mutant manifest-test-dropped   's# \&\& \[ -f "\$SRC/agent-pack/pack/manifest.json" \]##'
  mutant guide-test-dropped      's#\[ -f "\$SRC/agent-pack/guide/sd-basic-guide.md" \] \&\& ##'
  mutant unguarded-revstamp-read 's#2>/dev/null) || tree_stamp=""#2>/dev/null)#'
  mutant unguarded-manifest-read 's#agent-pack/pack/manifest.json") || pack_stamp=""#agent-pack/pack/manifest.json")#'
  mutant source-from-cwd         '/^# AGENTPACK-BEGIN$/,/^# AGENTPACK-END$/ s#"\$SRC/agent-pack#"agent-pack#g'
  mutant old-pack-kept           's#^        rm -rf "\$HOME_DIR/agent-pack"$#        true#'
  mutant half-copy-left          's#^            rm -rf "\$HOME_DIR/agent-pack"$#            true#'
  mutant failed-copy-stops       's#^            warn "The AI guide and knowledge pack could not be copied.*#            exit 1#'
  mutant block-after-the-stop    '/^# AGENTPACK-BEGIN$/i "$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>\&1 || true'
  mutant files-group-writable    's#find "\$HOME_DIR/agent-pack" -type f -exec chmod 644 {} +#find "$HOME_DIR/agent-pack" -type f -exec chmod 664 {} +#'
  mutant dirs-group-writable     's#find "\$HOME_DIR/agent-pack" -type d -exec chmod 755 {} +#find "$HOME_DIR/agent-pack" -type d -exec chmod 775 {} +#'
  mutant files-mode-removed      's#find "\$HOME_DIR/agent-pack" -type f -exec chmod 644 {} +#true#'
  mutant dirs-mode-removed       's#find "\$HOME_DIR/agent-pack" -type d -exec chmod 755 {} +#true#'
  mutant mode-block-removed      's#^if \[ -d "\$HOME_DIR/agent-pack" \]; then$#if false; then#'
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

IFS_LINE="IFS=\$'\\n\\t'"
OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-agentpack: CANNOT RUN - no set line in the installer"; exit 2; }
# the installer's own IFS line if it ever gets one, else the strict one the other install tests use
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-$IFS_LINE}"
BLK=$(awk '/^# AGENTPACK-BEGIN$/{f=1;next} /^# AGENTPACK-END$/{f=0} f{print}' "$INST")
MODE=$(awk '/^# AGENTPACK-MODE-BEGIN$/{f=1;next} /^# AGENTPACK-MODE-END$/{f=0} f{print}' "$INST")
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ';')"
echo "tree      : $SD64"
[ -z "$BLK" ]  && { echo "test-install-agentpack: CANNOT RUN - no block between AGENTPACK-BEGIN and AGENTPACK-END (nothing to check)"; exit 2; }
[ -z "$MODE" ] && { echo "test-install-agentpack: CANNOT RUN - no block between AGENTPACK-MODE-BEGIN and AGENTPACK-MODE-END (nothing to check)"; exit 2; }
[ -d "$SD64/agent-pack/pack" ] && [ -f "$SD64/agent-pack/guide/sd-basic-guide.md" ] || { echo "test-install-agentpack: CANNOT RUN - this tree has no agent-pack/guide and agent-pack/pack to install"; exit 2; }
[ -f "$SD64/sdsys/gpl.bp/revstamp.h" ] || { echo "test-install-agentpack: CANNOT RUN - no sdsys/gpl.bp/revstamp.h"; exit 2; }
echo "block     : $(printf '%s\n' "$BLK" | wc -l) lines;  mode block: $(printf '%s\n' "$MODE" | wc -l) lines"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export BLK MODE OPTS T
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}

setup() {   # a fresh installed tree (just the stamp) and a fresh "download": a copy of this tree's agent-pack, in the sd64 directory $SRC points at
  rm -rf "$T/home" "$T/work" "$T/cwd"; mkdir -p "$T/home" "$T/work/sd64/sdsys/gpl.bp" "$T/cwd"
  cp "$SD64/sdsys/gpl.bp/revstamp.h" "$T/work/sd64/sdsys/gpl.bp/revstamp.h"
  cp -R "$SD64/agent-pack" "$T/work/sd64/agent-pack"
}
run() {   # run BLOCK-VARIABLE-NAME [extra shell to run first]: prints what the block printed, then REACHED-END
  HOMEDIR="$T/home" SRCDIR="$T/work/sd64" WHICH="$1" EXTRA="${2:-}" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"; SRC="$SRCDIR"; RED=; NC=
      say()  { printf "%s\n" "$*"; }
      warn() { printf "%s\n" "$*"; }
      umask 077
      eval "$EXTRA"
      cd "$T/cwd"
      eval "${!WHICH}"
      echo "REACHED-END"' 2>&1
}
DEST="$T/home/agent-pack"
GOOD=$(sed -n '/"rev_stamp"/{s/^[^:]*: *"\([^"]*\)".*/\1/p;q}' "$SD64/agent-pack/pack/manifest.json")
[ -n "$GOOD" ] || { echo "test-install-agentpack: CANNOT RUN - the real manifest holds no rev_stamp"; exit 2; }
OK="Installed the AI guide and knowledge pack (version $GOOD): "

echo "--- A1, A2: the real pack"
setup; [ ! -e "$DEST" ] || { echo "test-install-agentpack: CANNOT RUN - the destination existed before the block"; exit 2; }
OUT=$(run BLK)
printf '%s\n' "$OUT" | sed 's/^/      | /'
row "A1 the success line names the version and the block reached its end" \
    "$(printf '%s' "$OUT" | grep -q -F "$OK" && printf '%s' "$OUT" | grep -q REACHED-END && echo 0 || echo 1)" "$OUT"
row "A1b ...the guide and every file of pack/ are in the destination, byte for byte (and there are some: a block that did nothing leaves none)" \
    "$([ -f "$DEST/guide/sd-basic-guide.md" ] && [ "$(find "$DEST/pack" -type f | wc -l)" -ge 10 ] && diff -r "$T/work/sd64/agent-pack/pack" "$DEST/pack" > /dev/null && diff -r "$T/work/sd64/agent-pack/guide" "$DEST/guide" > /dev/null && echo 0 || echo 1)" "$(ls -R "$DEST" 2>&1 | head -5)"
row "A2 only guide/ and pack/ are copied: no skill, templates, recipe, generator or notes" \
    "$([ "$(ls "$DEST" | tr '\n' ' ')" = "guide pack " ] && echo 0 || echo 1)" "destination holds: $(ls "$DEST" | tr '\n' ' ')"

absent() {   # name, what-to-remove-from-the-download
  setup; ( cd "$T/work/sd64" && rm -rf $2 ); mkdir -p "$DEST"; echo older > "$DEST/keep.txt"
  OUT=$(run BLK)
  row "$1: a note, nothing copied, an older pack untouched, the install is not stopped" \
      "$(printf '%s' "$OUT" | grep -q 'Note: the download holds no complete AI guide' && printf '%s' "$OUT" | grep -q REACHED-END && [ "$(ls "$DEST")" = keep.txt ] && echo 0 || echo 1)" "$OUT / dest: $(ls "$DEST" 2>&1 | head -3 | tr '\n' ' ')"
}
echo "--- A3: nothing, or half, to install"
absent "A3 no agent-pack at all (an older tag)" "agent-pack"
absent "A3b the guide but no manifest" "agent-pack/pack/manifest.json"
absent "A3c the manifest but no core.md" "agent-pack/pack/core.md"
absent "A3d the pack but no guide" "agent-pack/guide/sd-basic-guide.md"

echo "--- A4: a pack for another version"
setup; mkdir -p "$DEST"; echo older > "$DEST/keep.txt"
sed 's/"rev_stamp": "[^"]*"/"rev_stamp": "LS9.9-9"/' "$T/work/sd64/agent-pack/pack/manifest.json" > "$T/m.json" && cp "$T/m.json" "$T/work/sd64/agent-pack/pack/manifest.json"
grep -q 'LS9.9-9' "$T/work/sd64/agent-pack/pack/manifest.json" || { echo "test-install-agentpack: CANNOT RUN - the manifest edit changed nothing"; exit 2; }
OUT=$(run BLK)
row "A4 not installed, the note names the pack's version LS9.9-9 and the installed one $GOOD, the older pack is untouched, the install goes on" \
    "$(printf '%s' "$OUT" | grep -q -F "for version 'LS9.9-9' and this is '$GOOD'" && printf '%s' "$OUT" | grep -q REACHED-END && [ "$(ls "$DEST")" = keep.txt ] && echo 0 || echo 1)" "$OUT"

echo "--- A5: no installed revstamp.h (would stop an install under pipefail), no rev_stamp, an unreadable manifest, a failing copy"
setup; rm -f "$T/work/sd64/sdsys/gpl.bp/revstamp.h"
OUT=$(run BLK)
row "A5 not installed, the install goes on, the note says the installed version is unknown" \
    "$(printf '%s' "$OUT" | grep -q -F "and this is '?'" && printf '%s' "$OUT" | grep -q REACHED-END && [ ! -e "$DEST" ] && echo 0 || echo 1)" "$OUT"
setup; printf '{\n "chunk_count": 1\n}\n' > "$T/work/sd64/agent-pack/pack/manifest.json"
OUT=$(run BLK)
row "A5b a manifest with no rev_stamp: not installed, the install goes on" \
    "$(printf '%s' "$OUT" | grep -q -F "for version '?'" && printf '%s' "$OUT" | grep -q REACHED-END && [ ! -e "$DEST" ] && echo 0 || echo 1)" "$OUT"
setup; chmod 000 "$T/work/sd64/agent-pack/pack/manifest.json"
if [ -r "$T/work/sd64/agent-pack/pack/manifest.json" ]; then
  echo "  (A5c skipped: this caller can read a mode-000 file, so it cannot make a manifest unreadable)"
else
  OUT=$(run BLK)
  row "A5c a manifest that cannot be read: not installed, the install goes on (the read is guarded, not assumed to work)" \
      "$(printf '%s' "$OUT" | grep -q -F "for version '?'" && printf '%s' "$OUT" | grep -q REACHED-END && [ ! -e "$DEST" ] && echo 0 || echo 1)" "$OUT"
fi
chmod 644 "$T/work/sd64/agent-pack/pack/manifest.json"
setup
OUT=$(run BLK 'cp() { return 1; }')
row "A5d a copy that fails: a warning, no half pack left behind, the install goes on" \
    "$(printf '%s' "$OUT" | grep -q 'could not be copied into' && printf '%s' "$OUT" | grep -q REACHED-END && ! printf '%s' "$OUT" | grep -q -F "$OK" && [ ! -e "$DEST" ] && echo 0 || echo 1)" "$OUT / dest: $(ls "$DEST" 2>&1 | head -3 | tr '\n' ' ')"
setup; mkdir -p "$DEST/pack" "$DEST/guide"; echo stale > "$DEST/pack/stale-chunk.md"; echo stale > "$DEST/old-top.txt"
OUT=$(run BLK)
row "A5e an upgrade replaces the old pack whole: the stale files are gone, the new pack is there" \
    "$(printf '%s' "$OUT" | grep -q -F "$OK" && [ ! -e "$DEST/pack/stale-chunk.md" ] && [ ! -e "$DEST/old-top.txt" ] && diff -r "$T/work/sd64/agent-pack/pack" "$DEST/pack" > /dev/null && echo 0 || echo 1)" "$OUT / dest: $(ls "$DEST" | tr '\n' ' ')"

echo "--- A6: the mode block"
setup; run BLK > /dev/null
row "A6 control: the copy itself is private (600) under the installer's umask 077, so the mode block has something to do" \
    "$([ -n "$(find "$DEST" -type f -perm 600 | head -1)" ] && [ -z "$(find "$DEST" -type f -perm 644 | head -1)" ] && echo 0 || echo 1)" "modes: $(find "$DEST" -type f -printf '%m\n' | sort | uniq -c | tr '\n' ' ')"
OUT=$(run MODE)
row "A6a every file of agent-pack is 644 (the text is not a program) and the block reached its end" \
    "$([ -z "$(find "$DEST" -type f ! -perm 644)" ] && [ -n "$(find "$DEST" -type f)" ] && printf '%s' "$OUT" | grep -q REACHED-END && echo 0 || echo 1)" "not 644: $(find "$DEST" -type f ! -perm 644 | head -3 | tr '\n' ' ') / $OUT"
row "A6b ...directories are 755 and nothing in it is writable by group or other (no one else can plant text for the user's agent)" \
    "$([ -z "$(find "$DEST" -type d ! -perm 755)" ] && [ -z "$(find "$DEST" -perm /022)" ] && echo 0 || echo 1)" "writable by group/other or not 755: $(find "$DEST" -perm /022 | head -3 | tr '\n' ' ')"
setup; OUT=$(run MODE)
row "A6c no agent-pack installed: the mode block does nothing and does not stop the install" \
    "$(printf '%s' "$OUT" | grep -q REACHED-END && [ ! -e "$DEST" ] && echo 0 || echo 1)" "$OUT"

echo "--- A7: the order in the installer"
ln_of() { grep -n -m1 -F -x -- "$1" "$INST" | cut -d: -f1; }
ln_last_part() { grep -n -F -- "$1" "$INST" | tail -1 | cut -d: -f1; }
L_SRC=$(ln_of 'SRC="$CLONE_DIR/sdb_ai/sd64"'); L_STG=$(ln_last_part 'bash "$SRC/gplbld/solo-stage.sh"')
L_FRESH=$(ln_of 'chmod 600 "$HOME_DIR/.sdcore-install"')
L_B=$(ln_of '# AGENTPACK-BEGIN'); L_E=$(ln_of '# AGENTPACK-END'); L_M=$(ln_of '# AGENTPACK-MODE-BEGIN')
L_STOP=$(ln_of '"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true')
echo "      lines: SRC set $L_SRC, last stage call $L_STG, end of the fresh branch $L_FRESH, copy block $L_B-$L_E, mode block $L_M, stop of the stage's daemon $L_STOP"
if [ -z "$L_SRC" ] || [ -z "$L_STG" ] || [ -z "$L_FRESH" ] || [ -z "$L_B" ] || [ -z "$L_E" ] || [ -z "$L_M" ] || [ -z "$L_STOP" ]; then
  echo "test-install-agentpack: CANNOT RUN - an anchor line is not in the installer (so the order cannot be judged)"; exit 2
fi
row "A7 the copy comes after SRC is set, after the last stage call and after the fresh-install branch ends (so it runs for an upgrade as well), before the daemon is stopped" \
    "$([ "$L_SRC" -lt "$L_B" ] && [ "$L_STG" -lt "$L_B" ] && [ "$((L_FRESH+1))" -lt "$L_B" ] && [ "$L_E" -lt "$L_STOP" ] && echo 0 || echo 1)" "lines $L_SRC $L_STG $L_FRESH < $L_B-$L_E < $L_STOP"
row "A7b the mode block comes after the copy block" \
    "$([ "$L_M" -gt "$L_E" ] && [ "$L_M" -lt "$L_STOP" ] && echo 0 || echo 1)" "mode block $L_M, copy block ends $L_E"
row "A8 neither block contains an exit (a documents-only feature never ends an install)" \
    "$(printf '%s\n%s\n' "$BLK" "$MODE" | grep -q -E '(^|[^a-z_])exit([^a-z_]|$)' && echo 1 || echo 0)" "an exit is in the block"

echo "test-install-agentpack: $pass passed, $fail failed"
[ "$((pass + fail))" -eq 0 ] && { echo "test-install-agentpack: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
