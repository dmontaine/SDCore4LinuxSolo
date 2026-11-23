#!/bin/bash
#
# test-stage-sourcegone.sh - solo-stage.sh leaves no source in the installed tree (S.234 N1, SD Core's S.198; this check S.144, 17 Nov 2026).
#
#   bash /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-stage-sourcegone.sh
#   bash /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-stage-sourcegone.sh --selftest
#   STAGE=<a copy of solo-stage.sh> bash .../test-stage-sourcegone.sh      (what --selftest uses)
#
# FREE CHECK: no install, no sd, no sudo (Solo never uses it).  Exit 0 every row passed, 1 a row failed, 2 it could not run (a missing block is exit
# 2, never a pass).  SD Core's own check is test-install-sourcegone.sh; Solo's block is in solo-stage.sh, not the installer, and has no closing
# recompile (Solo's cproc has no IS_INSTALL code, LSOLO 30), so this is its own file, not a copy.
#
# The block between SOURCE-GONE-BEGIN and SOURCE-GONE-END is cut out of solo-stage.sh and run under its own "set" and "IFS" lines on a scratch
# tree, with sdi (the stage's "sd -internal") a stub that prints what the real session prints and fail() the stage's own.  It cannot say Solo
# still works with the source gone: that is a real install.
#
#   A  a good session: every source item is gone, the compiled programs and the rest of voc_template stay, the session deleted the three records
#   C  the VOC records are not deleted: the stage fails, the source is left
#   E  rm leaves an item behind: the stage fails and the item is named
#   K  --keep-source (keepsource=1): nothing is run and nothing is removed
#   F  the block comes after the stage's last use of gpl.bp and no command after it names the source

HERE="$(cd "$(dirname "$0")" && pwd)"
THIS="$HERE/$(basename "$0")"
STG="${STAGE:-$HERE/solo-stage.sh}"

if [ "${1:-}" = "--selftest" ]; then
  REAL="$HERE/solo-stage.sh"
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  caught=0; missed=0; n=0
  mutant() {   # name, sed expression
    local name="$1" expr="$2" f="$T/$1.sh" rc
    n=$((n+1))
    sed -e "$expr" "$REAL" > "$f"
    if cmp -s "$REAL" "$f"; then echo "  [MISSED] $name: the mutation changed nothing"; missed=$((missed+1)); return; fi
    STAGE="$f" bash "$THIS" > "$T/$name.out" 2>&1; rc=$?
    if [ "$rc" -ne 0 ]; then echo "  [caught] $name (exit $rc)"; caught=$((caught+1))
    else echo "  [MISSED] $name: the check still passed"; missed=$((missed+1)); fi
  }
  echo "selftest: the real solo-stage.sh first (must pass), then mutants (each must not)"
  STAGE="$REAL" bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real solo-stage.sh does not pass:"; tail -5 "$T/real.out"; exit 1; }
  echo "  [ok] the real solo-stage.sh passes"
  mutant keeps-gplbp        's/^  for source_item in gpl\.bp /  for source_item in /'
  mutant keeps-gplsrc       's/^\(  for source_item in .*\) gplsrc /\1 /'
  mutant keeps-template     's/ voc_template\/gpl\.bp / /'
  mutant no-delete-check    "s/grep -qF '3 record(s) deleted' || fail/grep -qF '' || fail/"
  mutant no-rm-check        's/\[ ! -e "\$H\/\$source_item" \] || fail/true || fail/'
  mutant no-voc-delete      's/sdi DELETE VOC gpl\.bp first\.compile second\.compile 2>&1/sdi DELETE VOC first.compile second.compile 2>\&1/'
  mutant keep-ignored       's/^if \[ "\$keepsource" -eq 0 \]; then$/if true; then/'
  echo "selftest: $caught of $n mutants caught, $missed missed"
  [ "$caught" -eq "$n" ] && [ "$missed" -eq 0 ]
  exit $?
fi

OPTS=$(grep -m1 -E '^set -' "$STG")
IFSL=$(grep -m1 -E '^IFS=' "$STG")
FAILF=$(grep -m1 -E '^fail\(\)' "$STG")
BLOCK=$(awk '/^# SOURCE-GONE-BEGIN$/{f=1;next} /^# SOURCE-GONE-END$/{f=0} f{print}' "$STG")
echo "stage     : $STG"
echo "options   : ${OPTS:-<none found>}"
echo "ifs       : ${IFSL:-<none: the stage sets no IFS>}"
echo "fail()    : ${FAILF:-<none found>}"
[ -z "$OPTS" ]  && { echo "test-stage-sourcegone: CANNOT RUN - no set line in solo-stage.sh"; exit 2; }
[ -z "$FAILF" ] && { echo "test-stage-sourcegone: CANNOT RUN - no fail() in solo-stage.sh"; exit 2; }
[ -z "$BLOCK" ] && { echo "test-stage-sourcegone: CANNOT RUN - no SOURCE-GONE block in solo-stage.sh (nothing to check)"; exit 2; }
echo "block     : $(printf '%s\n' "$BLOCK" | wc -l) lines"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}
SOURCE_ITEMS=$'gpl.bp\ngplsrc\ngplobj\ngplbld\ngpl.src\nMakefile\nvoc_template/gpl.bp\nvoc_template/first.compile\nvoc_template/second.compile'
make_tree() {   # dir: a scratch Solo system directory
  mkdir -p "$1/gpl.bp" "$1/gplsrc" "$1/gplobj" "$1/gplbld" "$1/gpl.bp.out" "$1/voc_template" "$1/bin"
  echo x > "$1/gpl.bp/cproc"; echo x > "$1/gplsrc/sd.c"; echo x > "$1/gplobj/sd.o"; echo x > "$1/gplbld/solo-stage.sh"; echo x > "$1/gpl.src"
  echo x > "$1/Makefile"; echo x > "$1/gpl.bp.out/cproc"; echo x > "$1/voc_template/gpl.bp"; echo x > "$1/voc_template/first.compile"
  echo x > "$1/voc_template/second.compile"; echo x > "$1/voc_template/gpl.bp.out"; echo x > "$1/voc_template/who"
}
run_block() {   # scratch dir, stub's output lines (\n escapes), keepsource, what rm does: real or leave
  local d="$1" said="$2" keep="$3" rmode="${4:-real}"
  bash -c "$OPTS"$'\n'"${IFSL:-}"$'\n'"$FAILF"$'\n'"H='$d'; SD='$d/bin/sd'; keepsource=$keep
sdi() { printf '%s\n' \"\$*\" >> '$d/.session'; printf '$said'; }
rm() { if [ '$rmode' = leave ] && [ \"\${@: -1}\" = '$d/gplsrc' ]; then return 0; fi; command rm \"\$@\"; }"$'\n'"$BLOCK"$'\n''echo BLOCK-FINISHED' 2>&1
}
GOOD='3 record(s) deleted\n'
present() { local d="$1" i n=0; while IFS= read -r i; do [ -e "$d/$i" ] && n=$((n+1)); done <<< "$SOURCE_ITEMS"; echo "$n"; }

# A
make_tree "$T/a0"
row "A0: the scratch tree had every item before the run (the null case)" $([ "$(present "$T/a0")" -eq 9 ] && echo 0 || echo 1) "items: $(present "$T/a0")"
make_tree "$T/a"; out=$(run_block "$T/a" "$GOOD" 0); rc=$?
row "A: the block ends normally and says the source was removed" $([ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q BLOCK-FINISHED && printf '%s' "$out" | grep -qF 'solo-stage: source: removed' && echo 0 || echo 1) "rc=$rc $out"
row "A1: every source item is gone" $([ "$(present "$T/a")" -eq 0 ] && echo 0 || echo 1) "left: $(present "$T/a")"
row "A2: the compiled programs stay (gpl.bp.out/cproc) and bin stays" $([ -f "$T/a/gpl.bp.out/cproc" ] && [ -d "$T/a/bin" ] && echo 0 || echo 1) "gone"
row "A3: the rest of voc_template stays" $([ -f "$T/a/voc_template/gpl.bp.out" ] && [ -f "$T/a/voc_template/who" ] && echo 0 || echo 1) "gone"
row "A4: the session deleted exactly the three VOC records" $([ "$(cat "$T/a/.session" 2>/dev/null)" = 'DELETE VOC gpl.bp first.compile second.compile' ] && echo 0 || echo 1) "session: $(tr '\n' '|' < "$T/a/.session" 2>/dev/null)"

# C
make_tree "$T/c"; out=$(run_block "$T/c" '0 record(s) deleted\n' 0); rc=$?
row "C: the records not deleted: the stage fails, and the source is left" $([ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "did not say '3 record(s) deleted'" && [ "$(present "$T/c")" -eq 9 ] && echo 0 || echo 1) "rc=$rc left=$(present "$T/c")"

# E
make_tree "$T/e"; out=$(run_block "$T/e" "$GOOD" 0 leave); rc=$?
row "E: an item rm left behind: the stage fails, and it is named" $([ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qF "$T/e/gplsrc could not be removed" && echo 0 || echo 1) "rc=$rc $out"

# K
make_tree "$T/k"; out=$(run_block "$T/k" "$GOOD" 1); rc=$?
row "K: --keep-source runs no session and removes nothing" $([ "$rc" -eq 0 ] && [ ! -e "$T/k/.session" ] && [ "$(present "$T/k")" -eq 9 ] && printf '%s' "$out" | grep -qF 'source: kept (--keep-source)' && echo 0 || echo 1) "rc=$rc left=$(present "$T/k")"

# F
lb=$(grep -n '^# SOURCE-GONE-BEGIN$' "$STG" | cut -d: -f1)
le=$(grep -n '^# SOURCE-GONE-END$' "$STG" | cut -d: -f1)
lu=$(head -n "$((${lb:-1} - 1))" "$STG" | grep -vE '^[[:space:]]*#' | grep -nE '(RUN|BASIC|CATALOG) gpl\.bp' | tail -1 | cut -d: -f1)
row "F: the stage runs gpl.bp before the block" $([ -n "$lb" ] && [ -n "$le" ] && [ -n "$lu" ] && [ "$lu" -lt "$lb" ] && echo 0 || echo 1) "last use ${lu:-?} block ${lb:-?}-${le:-?}"
after=$(tail -n "+$((${le:-0} + 1))" "$STG" | grep -vE '^[[:space:]]*#' | grep -nE '\$H/(gpl\.bp/|gpl\.bp"|gplsrc|gplobj|gplbld|gpl\.src)|(RUN|BASIC|CATALOG) gpl\.bp' || true)
row "F2: no command after the block names the installed source" $([ -z "$after" ] && echo 0 || echo 1) "$after"

echo "test-stage-sourcegone: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
