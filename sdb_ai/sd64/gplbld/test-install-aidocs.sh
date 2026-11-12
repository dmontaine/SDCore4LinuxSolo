#!/bin/bash
#
# test-install-aidocs.sh - installsdsolo.sh's block that puts the documentation under <home>/docs for the AI line (S.216 gap 27; SD Core's installsdcore.sh has the same block,
#                          S.100), run the way the installer runs it.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-aidocs.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-aidocs.sh --selftest
#   INSTALLER=<a copy of the installer> bash .../test-install-aidocs.sh      (what --selftest uses)
#
# FREE CHECK: no network (git is a function here), no install, no sd.  Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
# WHAT IT RUNS.  The text between "# DOCS-CORPUS-BEGIN" and "# DOCS-CORPUS-END" (the fetch, the copy and the modes), cut out verbatim and evaluated under the options read from the
# installer's own "set" line and under IFS=$'\n\t' (Solo's installer sets no IFS; this is the stricter of the two and what the other install tests of this directory use), with
# umask 077 as the installer runs, say and warn as the installer defines them (printing plain), and "git clone" a function that copies a scratch documentation tree and logs its
# arguments.  WHERE gpl.bp/tk_aidocs LOOKS is read from its source here, so the block and the reader cannot drift apart (D0).  Solo's documentation repository has User/markdown
# and no Administrator/markdown, so only docs/user is made; tk_aidocs leaves a missing docs/admin out.
#
#   D0  the directory the block writes is the one tk_aidocs reads: @sdsys : docs : user, with the file names it accepts
#   B1  a good clone: the success line, docs/user holds the User pages and nothing else (no docs/admin), the clone was asked for the installer's branch and the Solo documentation
#       repository (not the source's), a page left by an older install is gone, the scratch clone is removed, the block reached its end
#   B2  the clone fails / has no User/markdown / mktemp fails: a note, the install goes on, and the OLDER docs are still there untouched;  B2d the copy fails (a User/markdown
#       with no page, or cp itself): a warning, no half directory left, the install goes on
#   B3  the modes: docs and docs/user 755, the pages 644, nothing writable by group or other (made under umask 077, where they would be 700 and 600)
#   B4  the order in the installer (text): after the last stage call and the end of the fresh-install branch, before the stop of the stage's daemon; no exit in the block
#
# NOT MEASURED HERE: that a real clone from GitHub works (the first install that runs it) and that the AI line finds the pages in a running Solo (sandbox-docs.py-style row, NOT written
# for Solo).

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
  B='/^# DOCS-CORPUS-BEGIN$/,/^# DOCS-CORPUS-END$/'
  mutant old-docs-kept           's#^    rm -rf "\$HOME_DIR/docs"$#    true#'
  mutant half-copy-left          's#^        rm -rf "\$HOME_DIR/docs"$#        true#'
  mutant user-into-admin         's#cp "\$docs_from"/User/markdown/\*.md "\$HOME_DIR/docs/user/"#cp "$docs_from"/User/markdown/*.md "$HOME_DIR/docs/admin/"#'
  mutant wrong-directory         "$B s#\"\\\$HOME_DIR/docs#\"\$HOME_DIR/doc#g"
  mutant branch-ignored          's#--branch "\$REPO_BRANCH" --depth 1 "\$DOCS_URL"#--depth 1 "$DOCS_URL"#'
  mutant wrong-repository        's#--depth 1 "\$DOCS_URL" "\$docs_tmp/docs"#--depth 1 "$REPO_URL" "$docs_tmp/docs"#'
  mutant user-test-dropped       's# \&\& \[ -d "\$docs_tmp/docs/User/markdown" \]##'
  mutant hard-stop-on-failure    's#^    say "Note: the documentation could not be fetched from .*#    exit 1#'
  mutant hard-stop-on-bad-copy   's#^        warn "The documentation for the AI line could not be copied.*#        exit 1#'
  mutant tmp-guard-dropped       's#docs_tmp=\$(mktemp -d 2>/dev/null) || docs_tmp=""#docs_tmp=$(mktemp -d)#'
  mutant tmp-left-behind         's#^if \[ -n "\$docs_tmp" \]; then rm -rf "\$docs_tmp"; fi$#true#'
  mutant dirs-group-writable     's#chmod 755 "\$HOME_DIR/docs" "\$HOME_DIR/docs/user"#chmod 775 "$HOME_DIR/docs" "$HOME_DIR/docs/user"#'
  mutant dirs-mode-removed       's#^        chmod 755 "\$HOME_DIR/docs" "\$HOME_DIR/docs/user"$#        true#'
  mutant files-group-writable    's#find "\$HOME_DIR/docs/user" -type f -exec chmod 644 {} +#find "$HOME_DIR/docs/user" -type f -exec chmod 664 {} +#'
  mutant files-mode-removed      's#^        find "\$HOME_DIR/docs/user" -type f -exec chmod 644 {} +$#        true#'
  mutant corpus-before-the-stop  '/^# DOCS-CORPUS-BEGIN$/i "$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>\&1 || true'
  mutant docs-url-is-the-source  's#^DOCS_URL="https://github.com/dmontaine/SDCore4LinuxSoloDocs"$#DOCS_URL="https://github.com/dmontaine/SDCore4LinuxSolo"#'
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$caught" -eq "$total" ] && [ "$missed" -eq 0 ]
  exit $?
fi

IFS_LINE="IFS=\$'\\n\\t'"
OPTS="$(grep -m1 -E '^set -' "$INST" || true)"
[ -n "$OPTS" ] || { echo "test-install-aidocs: CANNOT RUN - no set line in the installer"; exit 2; }
OWN_IFS="$(grep -m1 -E '^IFS=' "$INST" || true)"
OPTS="$OPTS"$'\n'"${OWN_IFS:-$IFS_LINE}"
BLK=$(awk '/^# DOCS-CORPUS-BEGIN$/{f=1;next} /^# DOCS-CORPUS-END$/{f=0} f{print}' "$INST")
REPO_BRANCH_V=$(sed -n 's/^REPO_BRANCH="\(.*\)"$/\1/p' "$INST" | head -1)
DOCS_URL_V=$(sed -n 's/^DOCS_URL="\(.*\)"$/\1/p' "$INST" | head -1)
REPO_URL_V=$(sed -n 's/^REPO_URL="\(.*\)"$/\1/p' "$INST" | head -1)
echo "installer : $INST"
echo "options   : $(printf '%s' "$OPTS" | tr '\n' ';')"
[ -z "$BLK" ] && { echo "test-install-aidocs: CANNOT RUN - no block between DOCS-CORPUS-BEGIN and DOCS-CORPUS-END (nothing to check)"; exit 2; }
[ -n "$REPO_BRANCH_V" ] && [ -n "$DOCS_URL_V" ] && [ -n "$REPO_URL_V" ] || { echo "test-install-aidocs: CANNOT RUN - REPO_BRANCH, REPO_URL or DOCS_URL is not set in the installer"; exit 2; }
echo "block     : $(printf '%s\n' "$BLK" | wc -l) lines"

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export BLK OPTS T REPO_BRANCH_V DOCS_URL_V REPO_URL_V
pass=0; fail=0
row() {   # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then pass=$((pass+1)); printf '  [PASS] %s\n' "$1"
  else fail=$((fail+1)); printf '  [FAIL] %s   <- %s\n' "$1" "$3"; fi
}

setup() {   # a scratch install directory, a scratch "documentation repository", empty logs
  rm -rf "$T/home" "$T/repo" "$T/cwd" "$T/tmpd"; mkdir -p "$T/home" "$T/cwd" "$T/repo/User/markdown"
  printf '# Guide\n\nUser page one, zzuserword.\n' > "$T/repo/User/markdown/01-guide.md"
  printf '# Tutorial\n\nUser page two.\n' > "$T/repo/User/markdown/02-tutorial.md"
  : > "$T/git.log"
}
run() {   # run [extra shell to run first]: prints what the block printed, then REACHED-END
  HOMEDIR="$T/home" EXTRA="${1:-}" bash -c '
      eval "$OPTS"
      HOME_DIR="$HOMEDIR"; RED=; NC=
      say()  { printf "%s\n" "$*"; }
      warn() { printf "%s\n" "$*"; }
      umask 077
      mkdir -p "$T/tmpd"; export TMPDIR="$T/tmpd"
      REPO_BRANCH="$REPO_BRANCH_V"; DOCS_URL="$DOCS_URL_V"; REPO_URL="$REPO_URL_V"; pkg_source=""
      git() {
        ( IFS=" "; printf "%s\n" "$*" ) >> "$T/git.log"
        if [ -n "${GITFAIL:-}" ]; then return 128; fi
        local dest; for dest in "$@"; do :; done
        mkdir -p "$dest" && cp -R "$T/repo/." "$dest/"
      }
      eval "$EXTRA"
      cd "$T/cwd"
      eval "$BLK"
      echo "REACHED-END"' 2>&1
}
DOCS="$T/home/docs"
older() {   # an older install's docs
  mkdir -p "$DOCS/user" "$DOCS/admin"; printf 'old user page\n' > "$DOCS/user/stale.md"; printf 'old admin page\n' > "$DOCS/admin/stale.md"
}

echo "--- D0: the block writes where tk_aidocs reads"
AID="$SD64/sdsys/gpl.bp/tk_aidocs"
[ -f "$AID" ] || { echo "test-install-aidocs: CANNOT RUN - no sdsys/gpl.bp/tk_aidocs to read the location from"; exit 2; }
row "D0 tk_aidocs reads @sdsys : docs : user (and docs/admin only for the administrator), and accepts a file name that ends .md of lower case letters, digits and . _ -" \
    "$(grep -q -F "ent = dir(@sdsys : @ds : 'docs' : @ds : dkind)" "$AID" && grep -q -F "if dkind # 'user' and dkind # 'admin' then return" "$AID" && grep -q -F "okn = 'abcdefghijklmnopqrstuvwxyz0123456789._-'" "$AID" && echo 0 || echo 1)" "the reader's lines are not as expected"
row "D0b ...and the block's directory is <home>/docs/user, where @sdsys of an install is <home> (solo-stage.sh: HOME_DIR is both the Solo home and the SDSYS directory)" \
    "$(printf '%s\n' "$BLK" | grep -q -F 'mkdir -p "$HOME_DIR/docs/user"' && grep -q -F 'HOME_DIR is both the Solo home and the SDSYS directory' "$SD64/gplbld/solo-stage.sh" && echo 0 || echo 1)" "block or stage layout line not found"

echo "--- B1: a good clone"
setup; older; OUT=$(run)
printf '%s\n' "$OUT" | sed 's/^/      | /'
row "B1 the success line, and the block reached its end" "$(printf '%s' "$OUT" | grep -q -F "Installed the documentation the AI line draws on: $T/home/docs" && printf '%s' "$OUT" | grep -q REACHED-END && echo 0 || echo 1)" "$OUT"
row "B1b docs/user holds the User pages and nothing else (and there are some); there is no docs/admin" \
    "$([ "$(ls "$DOCS/user" | tr '\n' ' ')" = "01-guide.md 02-tutorial.md " ] && cmp -s "$T/repo/User/markdown/01-guide.md" "$DOCS/user/01-guide.md" && [ ! -e "$DOCS/admin" ] && echo 0 || echo 1)" "user: $(ls "$DOCS/user" | tr '\n' ' '); docs: $(ls "$DOCS" | tr '\n' ' ')"
row "B1c the page an older install left is gone (the null case for the removal: it was there before)" "$([ ! -e "$DOCS/user/stale.md" ] && [ ! -e "$DOCS/admin/stale.md" ] && echo 0 || echo 1)" "stale pages are still there"
row "B1d the clone asked for the installer's branch ($REPO_BRANCH_V), one level deep, from the documentation repository ($DOCS_URL_V) and not the source's ($REPO_URL_V)" \
    "$(grep -q -F -- "clone --quiet --branch $REPO_BRANCH_V --depth 1 $DOCS_URL_V " "$T/git.log" && ! grep -q -F -- "$REPO_URL_V " "$T/git.log" && echo 0 || echo 1)" "git log: $(cat "$T/git.log")"
row "B1e the scratch clone was removed afterwards" "$([ -d "$T/tmpd" ] && [ -z "$(ls -A "$T/tmpd")" ] && echo 0 || echo 1)" "left behind: $(ls -A "$T/tmpd" 2>&1)"

echo "--- B2: no documentation: a note, the install goes on, an older install's docs are untouched"
chk() {   # name, extra, mutate (shell run in the scratch repository first)
  setup; older; ( eval "$3" ); OUT=$(run "$2")
  row "$1: a note, REACHED-END, the older pages are still there" \
      "$(printf '%s' "$OUT" | grep -q 'Note: the documentation could not be fetched' && printf '%s' "$OUT" | grep -q REACHED-END && [ -e "$DOCS/user/stale.md" ] && [ -e "$DOCS/admin/stale.md" ] && echo 0 || echo 1)" "$OUT"
}
chk "B2 the clone fails" "GITFAIL=1" "true"
chk "B2b the clone has no User/markdown" "" "rm -rf '$T/repo/User'"
chk "B2c mktemp fails" "mktemp() { return 1; }" "true"
bad() {   # name, extra, mutate
  setup; older; ( eval "$3" ); OUT=$(run "$2")
  row "$1: a warning, no half directory left, REACHED-END, no success line" \
      "$(printf '%s' "$OUT" | grep -q 'could not be copied into' && printf '%s' "$OUT" | grep -q REACHED-END && ! printf '%s' "$OUT" | grep -q 'Installed the documentation' && [ ! -e "$DOCS" ] && echo 0 || echo 1)" "$OUT / docs: $(ls "$DOCS" 2>&1 | tr '\n' ' ')"
}
bad "B2d User/markdown holds no page" "" "rm -f '$T/repo/User/markdown/'*.md"
bad "B2e cp fails (only the block's copy into docs/user: the clone stub copies with cp too)" "cp() { case \"\$*\" in *docs/user*) return 1 ;; esac; command cp \"\$@\"; }" "true"

echo "--- B3: the modes"
setup; OUT=$(run)
row "B3 docs and docs/user are 755 (made under umask 077 they would be 700)" "$([ "$(stat -c %a "$DOCS")" = 755 ] && [ "$(stat -c %a "$DOCS/user")" = 755 ] && printf '%s' "$OUT" | grep -q REACHED-END && echo 0 || echo 1)" "docs $(stat -c %a "$DOCS"), user $(stat -c %a "$DOCS/user")"
row "B3b the pages are 644 (and there are some)" "$([ -z "$(find "$DOCS/user" -type f ! -perm 644)" ] && [ -n "$(find "$DOCS/user" -type f)" ] && echo 0 || echo 1)" "not 644: $(find "$DOCS/user" -type f ! -perm 644 | head -2 | tr '\n' ' ')"
row "B3c nothing in docs is writable by group or other" "$([ -z "$(find "$DOCS" -perm /022)" ] && echo 0 || echo 1)" "writable: $(find "$DOCS" -perm /022 | head -2 | tr '\n' ' ')"

echo "--- B4: the order in the installer"
ln_of() { grep -n -m1 -F -x -- "$1" "$INST" | cut -d: -f1; }
ln_last_part() { grep -n -F -- "$1" "$INST" | tail -1 | cut -d: -f1; }
L_STG=$(ln_last_part 'bash "$SRC/gplbld/solo-stage.sh"'); L_FRESH=$(ln_of 'chmod 600 "$HOME_DIR/.sdcore-install"')
L_B=$(ln_of '# DOCS-CORPUS-BEGIN'); L_E=$(ln_of '# DOCS-CORPUS-END'); L_STOP=$(ln_of '"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true')
echo "      lines: last stage call $L_STG, end of the fresh branch $L_FRESH, block $L_B-$L_E, stop of the stage's daemon $L_STOP"
if [ -z "$L_STG" ] || [ -z "$L_FRESH" ] || [ -z "$L_B" ] || [ -z "$L_E" ] || [ -z "$L_STOP" ]; then echo "test-install-aidocs: CANNOT RUN - an anchor line is not in the installer"; exit 2; fi
row "B4 the block comes after the last stage call and after the fresh-install branch ends (so it runs for an upgrade as well), before the daemon is stopped" \
    "$([ "$L_STG" -lt "$L_B" ] && [ "$((L_FRESH+1))" -lt "$L_B" ] && [ "$L_E" -lt "$L_STOP" ] && echo 0 || echo 1)" "lines $L_STG $L_FRESH < $L_B-$L_E < $L_STOP"
row "B4b the block contains no exit (documentation never ends an install)" "$(printf '%s\n' "$BLK" | grep -q -E '(^|[^a-z_])exit([^a-z_]|$)' && echo 1 || echo 0)" "an exit is in the block"

echo "test-install-aidocs: $pass passed, $fail failed"
[ "$((pass + fail))" -eq 0 ] && { echo "test-install-aidocs: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
