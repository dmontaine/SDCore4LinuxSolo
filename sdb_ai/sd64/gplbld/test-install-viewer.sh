#!/bin/bash
# test-install-viewer.sh - the installer's question "allow a PDF reader to show the documentation?" (Solo carry 14, S.75, 23 Oct 2026; SD Core's installer has the same
# question).  No install, no sudo, no sd.  Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-viewer.sh [--selftest]
#
# THE BLOCK AND ITS PLACE.  installsdsolo.sh keeps find_pdf_reader and ask_viewer between "# BEGIN viewer_ask" and "# END viewer_ask".  This cuts the block out and runs it
# under the installer's own `set -euo pipefail` and IFS (a block tested without them once stopped two real installs: test-install-pass3.sh), with `say` a function, `os_yn`
# a stub that answers from a list and records what it was asked (the real one reads /dev/tty and is held by test-install-osaccess.sh), and the three directories find_pdf_reader
# searches replaced by a scratch directory, so the answer does not depend on what this machine has installed.  Then the places the answer travels - the option, the control
# file's key, both solo-stage.sh calls, the upgrade branch and the install branch, solo-stage's own option - are read as text.  ***IT DOES NOT RUN THE INSTALLER***, so it
# cannot say that a real install asks on a terminal, nor that SET.VIEWER accepts the reader: the first is the owner's witness, the second is sandbox-home-solo.py.
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.

set -euo pipefail
IFS=$'\n\t'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="$ROOT/installsdsolo.sh"
STAGE="$HERE/solo-stage.sh"

passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

check() {   # check INSTALLER STAGE - every row, against these two files
  local inst="$1" stage="$2" blk blk2 scratch rd out
  blk="$(mktemp)"; blk2="$(mktemp)"; scratch="$(mktemp -d)"; rd="$scratch/bin"; mkdir -p "$rd" "$scratch/home"
  sed -n '/^# BEGIN viewer_ask$/,/^# END viewer_ask$/p' "$inst" > "$blk"
  if [ "$(wc -l < "$blk")" -lt 10 ]; then
    row "the installer holds a '# BEGIN viewer_ask' ... '# END viewer_ask' block" 1 "found $(wc -l < "$blk") lines"
    rm -rf "$blk" "$blk2" "$scratch"; return
  fi
  row "the installer holds a '# BEGIN viewer_ask' ... '# END viewer_ask' block" 0
  sed 's#for d in /usr/bin /usr/local/bin /bin; do#for d in "$READER_DIR"; do#' "$blk" > "$blk2"
  row "...which searches /usr/bin, /usr/local/bin and /bin (the line this test replaces by a scratch directory is there)" "$(cmp -s "$blk" "$blk2" && echo 1 || echo 0)"

  run_block() {   # run_block interactive assume_yes viewer "y n ..." -> prints  RESULT <viewer>  ASKED <n>  then what was said and asked
    ( set -euo pipefail; IFS=$'\n\t'
      say() { printf '%s\n' "$*"; }
      interactive="$1"; assume_yes="$2"; viewer="$3"; answers="$4"; asked=0; questions=""
      HOME_DIR="$scratch/home"; READER_DIR="$rd"
      # shellcheck disable=SC1090
      . "$blk2"
      os_yn() { questions="$questions|$1"; asked=$((asked+1)); local a="${answers%% *}"; answers="${answers#* }"; [ "$a" = y ]; }
      ask_viewer
      printf 'RESULT %s ASKED %s\n' "$viewer" "$asked"
      printf 'Q%s\n' "$questions" )
  }
  find_in() { ( set -euo pipefail; IFS=$'\n\t'; READER_DIR="$rd"; . "$blk2"; find_pdf_reader ); }

  rm -f "$rd"/* "$scratch/home/viewers"
  out="$(find_in)"
  row "find_pdf_reader finds nothing in an empty directory" "$([ -z "$out" ] && echo 0 || echo 1)" "got '$out'"
  : > "$rd/okular"; chmod 644 "$rd/okular"
  out="$(find_in)"
  row "...and ignores a file that is not executable" "$([ -z "$out" ] && echo 0 || echo 1)" "got '$out'"
  chmod 755 "$rd/okular"; : > "$rd/zathura"; chmod 755 "$rd/zathura"
  out="$(find_in)"
  row "...finds the first reader of its list that is there (okular before zathura)" "$([ "$out" = okular ] && echo 0 || echo 1)" "got '$out'"
  : > "$rd/evince"; chmod 755 "$rd/evince"
  out="$(find_in)"
  row "...and evince before okular" "$([ "$out" = evince ] && echo 0 || echo 1)" "got '$out'"
  : > "$rd/xdg-open"; : > "$rd/firefox"; chmod 755 "$rd/xdg-open" "$rd/firefox"; rm -f "$rd/evince" "$rd/okular" "$rd/zathura"
  out="$(find_in)"
  row "...and does not offer a program that is not a PDF reader (xdg-open and a browser are not on its list)" "$([ -z "$out" ] && echo 0 || echo 1)" "got '$out'"
  rm -f "$rd"/*

  : > "$rd/evince"; chmod 755 "$rd/evince"
  out="$(run_block 1 0 mupdf "y y" 2>&1)"
  row "an answer already given (--viewer or the control file) is kept and nothing is asked" "$(printf '%s\n' "$out" | grep -qx 'RESULT mupdf ASKED 0' && echo 0 || echo 1)" "$out"
  out="$(run_block 0 0 '' "y y" 2>&1)"
  row "no terminal: none, nothing is asked (even when a stub would have said yes)" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 0' && echo 0 || echo 1)" "$out"
  out="$(run_block 1 1 '' "y y" 2>&1)"
  row "--yes with a terminal and no answer: none, nothing asked" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 0' && echo 0 || echo 1)" "$out"
  printf 'pdf /usr/bin/evince\n' > "$scratch/home/viewers"
  out="$(run_block 1 0 '' "y y" 2>&1)"
  row "a reader is already allowed (an upgrade): none, nothing asked, the administrator's choice is not touched" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 0' && echo 0 || echo 1)" "$out"
  rm -f "$scratch/home/viewers"
  rm -f "$rd"/*
  out="$(run_block 1 0 '' "y y" 2>&1)"
  row "no known reader installed: none, nothing asked" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 0' && echo 0 || echo 1)" "$out"
  : > "$rd/evince"; chmod 755 "$rd/evince"
  out="$(run_block 1 0 '' "y" 2>&1)"
  row "a terminal, a reader installed and the answer y: that reader, after exactly one question that names it" \
    "$(printf '%s\n' "$out" | grep -qx 'RESULT evince ASKED 1' && printf '%s\n' "$out" | grep -q '^Q|Allow evince to show the documentation?$' && echo 0 || echo 1)" "$out"
  out="$(run_block 1 0 '' "n" 2>&1)"
  row "...and the answer n: none" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 1' && echo 0 || echo 1)" "$out"
  row "...the text tells the person that none is allowed unless they say so, and how to change it later" \
    "$(printf '%s\n' "$(run_block 1 0 '' "n" 2>&1)" | grep -q 'none is allowed unless you say so' && printf '%s\n' "$(run_block 1 0 '' "n" 2>&1)" | grep -q 'ADMIN, then set.viewer' && echo 0 || echo 1)"
  row "the block runs nothing but its own arguments: no sd, no sudo, no SET.VIEWER" "$(grep -q -e 'sudo' -e 'SET.VIEWER' -e '"\$SD"' -e 'bin/sd' "$blk" && echo 1 || echo 0)"

  # where the answer travels
  row "--viewer is an option, validated none or a plain name (letters, digits and . _ + -, not starting with a dot)" \
    "$(grep -q -- '--viewer) *\[ "\$#" -ge 2 \]' "$inst" && grep -qF 'case "$viewer" in ""|none) ;; *[!a-z0-9._+-]*|.*) refuse' "$inst" && echo 0 || echo 1)"
  row "the control file's viewer key is read, validated and used only when no option gave an answer" \
    "$(grep -q 'viewer) *cf_viewer=' "$inst" && grep -qF 'case "$cf_viewer" in ""|none) ;; *[!a-z0-9._+-]*|.*) refuse' "$inst" && grep -qF '[ -n "$viewer" ] || viewer="$cf_viewer"' "$inst" && echo 0 || echo 1)"
  row "the question is asked on an upgrade BEFORE 'Continue?' (after the OS-access question) and on a first install after it" \
    "$(awk '/^if \[ "\$upgrade" -eq 1 \]; then$/ {u=1} u && /^  ask_os_access$/ {o=NR} u && /^  ask_viewer$/ {a=NR} u && /read -r -p "Continue\? \[Y\/n\] "/ && !c {c=NR} /^ask_os_access$/ {io=NR} /^ask_viewer$/ {i=NR} END {exit !(o && a && c && o<a && a<c && io && i && io<i)}' "$inst" && echo 0 || echo 1)"
  row "both solo-stage.sh calls pass the answer (a fresh stage, and --upgrade), none when there is none" \
    "$(grep -qF 'solo-stage.sh" --upgrade --os-access "${os_access:-none}" --viewer "${viewer:-none}" "$HOME_DIR"' "$inst" && grep -qF 'st_args+=(--os-access "${os_access:-none}" --viewer "${viewer:-none}")' "$inst" && echo 0 || echo 1)"
  row "the summary and the log carry the state: the stage's 'PDF reader:' line is read on both paths and the summary prints it" \
    "$([ "$(grep -c "solo-stage: PDF reader: //p" "$inst")" -ge 2 ] && grep -q "say \"  pdf reader    : " "$inst" && echo 0 || echo 1)"
  row "an upgrade still refuses every other install option (os-access and viewer are the exceptions)" \
    "$(grep -q 'it takes no password, control-file, --reload-data, --start-clean, --api, --ssh, --ssh-key or --enable-linger option' "$inst" && echo 0 || echo 1)"
  row "solo-stage.sh takes --viewer NAME|none, makes none the empty word and refuses anything that is not a plain name" \
    "$(grep -qF '"--viewer"' "$stage" && grep -qF 'case "$2" in none) viewer="" ;;' "$stage" && grep -qF '*[!a-z0-9._+-]*) refuse "--viewer must be none or the name of a reader' "$stage" && echo 0 || echo 1)"
  row "solo-stage.sh allows a reader only when one was asked for, through SET.VIEWER ADD PDF (which tests the program), and says what the list holds afterwards" \
    "$(grep -qF 'if [ -n "$viewer" ]; then' "$stage" && grep -qF 'sdi SET.VIEWER ADD PDF "$viewer"' "$stage" && grep -qF 'solo-stage: PDF reader: allowed' "$stage" && grep -qF 'solo-stage: PDF reader: none allowed' "$stage" && echo 0 || echo 1)"
  rm -rf "$blk" "$blk2" "$scratch"
}

selftest() {
  local tmp name target expr file ok=0 n=0 out p0 f0
  tmp="$(mktemp -d)"
  # name | which file | sed expression that breaks it  (the block's own lines are addressed by range, since ask_os_access has lines like them)
  while IFS='|' read -r name target expr; do
    [ -n "$name" ] || continue
    n=$((n+1))
    cp "$INSTALLER" "$tmp/installsdsolo.sh"; cp "$STAGE" "$tmp/solo-stage.sh"
    case "$target" in i) file="$tmp/installsdsolo.sh" ;; s) file="$tmp/solo-stage.sh" ;; esac
    sed -i -e "$expr" "$file"
    if cmp -s "$file" "$( [ "$target" = i ] && echo "$INSTALLER" || echo "$STAGE" )"; then
      echo "  [FAIL] selftest: $name  <- the mutation changed nothing"; failed=$((failed+1)); continue
    fi
    p0=$passed; f0=$failed
    out="$(check "$tmp/installsdsolo.sh" "$tmp/solo-stage.sh" 2>&1 || true)"
    passed=$p0; failed=$f0
    if printf '%s\n' "$out" | grep -q '\[FAIL\]'; then
      echo "  [PASS] selftest: $name is caught ($(printf '%s\n' "$out" | grep -c '\[FAIL\]') row(s) failed)"; passed=$((passed+1)); ok=$((ok+1))
    else
      echo "  [FAIL] selftest: $name is NOT caught"; failed=$((failed+1))
    fi
  done <<'EOF'
the terminal test is gone, so a run with no terminal asks|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/\[ "\$interactive" -ne 1 \] || \[ "\$assume_yes" -eq 1 \]/false/
--yes no longer skips the question|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/ || \[ "\$assume_yes" -eq 1 \]; then$/; then/
a reader that is already allowed is asked about again|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/if grep -qs '\^pdf ' "\$HOME_DIR\/viewers"; then/if false; then/
a bare no allows the reader|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/then viewer="\$found"; else viewer="none"; fi/then viewer="none"; else viewer="$found"; fi/
the answer is not kept when one was given|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/\[ -z "\$viewer" \] || return 0/true/
the question is asked when no reader is installed|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/if \[ -z "\$found" \]; then viewer="none"; return 0; fi/true/
a file that is not executable counts as a reader|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/if \[ -x "\$d\/\$v" \]/if [ -e "$d\/$v" ]/
a browser is offered as a reader|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/for v in evince okular/for v in firefox evince okular/
the block runs set.viewer itself|i|/^# BEGIN viewer_ask$/,/^# END viewer_ask$/ s/^# END viewer_ask$/sudo true SET.VIEWER\n# END viewer_ask/
the upgrade no longer asks|i|s/^  ask_viewer$/  true/
the first install no longer asks|i|s/^ask_viewer$/true/
the upgrade passes no viewer to solo-stage|i|s/--upgrade --os-access "\${os_access:-none}" --viewer "\${viewer:-none}"/--upgrade --os-access "${os_access:-none}"/
the fresh stage passes no viewer to solo-stage|i|s/ --viewer "\${viewer:-none}")/)/
the control file's viewer is not read|i|s/viewer)          cf_viewer=/viewerX)         cf_viewer=/
the option accepts any name|i|s/case "\$viewer" in ""|none) ;; \*\[!a-z0-9._+-\]\*|\.\*) refuse/case "$viewer" in ""|none) ;; ZZ) refuse/
the summary line is gone|i|s/say "  pdf reader    : /say "  /
solo-stage calls none a reader|s|s/none) viewer="" ;;/none) viewer="none" ;;/
solo-stage accepts any name|s|s/""|\.\*|\*\[!a-z0-9\._+-\]\*) refuse "--viewer/"") refuse "--viewer/
solo-stage allows a reader nobody asked for|s|s/^if \[ -n "\$viewer" \]; then$/if true; then/
solo-stage no longer says what the list holds|s|s/solo-stage: PDF reader: allowed/solo-stage: PDF reader allowed/
EOF
  rm -rf "$tmp"
  echo "selftest: $ok of $n mutants caught"
}

for f in "$INSTALLER" "$STAGE"; do
  [ -f "$f" ] || { echo "test-install-viewer: CANNOT RUN - $f is not there"; exit 2; }
done
echo "test-install-viewer: installer $INSTALLER"
echo "test-install-viewer: stage     $STAGE"
check "$INSTALLER" "$STAGE"
if [ "${1:-}" = "--selftest" ]; then selftest; fi
echo
echo "test-install-viewer: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
