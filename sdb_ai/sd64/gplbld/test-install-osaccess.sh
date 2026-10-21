#!/bin/bash
# test-install-osaccess.sh - the installer's question "turn on the shell and OS access?" (the Solo OS switch, owner 20 Oct 2026:
# "ask during install").  No install, no sudo, no sd.  Exit 0 every row held, 1 one did not, 2 it could not run.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-osaccess.sh [--selftest]
#
# THE BLOCK AND ITS PLACE.  installsdsolo.sh keeps os_access_word, os_yn and ask_os_access between "# BEGIN os_access" and
# "# END os_access".  This cuts the block out and runs it under the installer's own `set -euo pipefail` and IFS (a block tested without
# them once stopped two real installs: test-install-pass3.sh), with `say` a function and `os_yn` replaced by a stub that answers from a
# list and records what it was asked, because the real os_yn reads /dev/tty.  The real os_yn is read as text: its default is NO.
# Then the places the answer travels - the option, the control file's key, both solo-stage.sh calls, the upgrade branch and the install
# branch, solo-stage's verb lines - are read as text.  ***IT DOES NOT RUN THE INSTALLER***, so it cannot say that a real install asks
# on a terminal; the witness for that is the owner's, with a terminal.
#
# --selftest breaks the installer in the ways listed at the end and requires the rows to notice each one.

set -euo pipefail
IFS=$'\n\t'

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="$ROOT/installsdsolo.sh"
STAGE="$HERE/solo-stage.sh"
SAMPLE="$HERE/sd-solo-setup.conf.sample"

passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

check() {   # check INSTALLER STAGE SAMPLE - every row, against these three files
  local inst="$1" stage="$2" sample="$3" blk w out
  blk="$(mktemp)"
  sed -n '/^# BEGIN os_access$/,/^# END os_access$/p' "$inst" > "$blk"
  if [ "$(wc -l < "$blk")" -lt 10 ]; then
    row "the installer holds a '# BEGIN os_access' ... '# END os_access' block" 1 "found $(wc -l < "$blk") lines"
    rm -f "$blk"; return
  fi
  row "the installer holds a '# BEGIN os_access' ... '# END os_access' block" 0

  # the block, run as the installer runs it
  run_block() {   # run_block interactive assume_yes upgrade os_access "y n ..." -> prints  RESULT <os_access>  ASKED <n>  then what was said
    ( set -euo pipefail; IFS=$'\n\t'
      say() { printf '%s\n' "$*"; }
      interactive="$1"; assume_yes="$2"; upgrade="$3"; os_access="$4"
      answers="$5"; asked=0; questions=""
      # shellcheck disable=SC1090
      . "$blk"
      os_yn() { questions="$questions|$1"; asked=$((asked+1)); local a="${answers%% *}"; answers="${answers#* }"; [ "$a" = y ]; }
      ask_os_access
      printf 'RESULT %s ASKED %s\n' "$os_access" "$asked"
      printf 'Q%s\n' "$questions" )
  }
  for w in "1 1:both" "1 0:sh" "0 1:os" "0 0:none"; do
    out="$( IFS=' ' read -r a1 a2 <<< "${w%%:*}"; . "$blk"; os_access_word "$a1" "$a2" )"
    row "os_access_word ${w%%:*} is ${w##*:}" "$([ "$out" = "${w##*:}" ] && echo 0 || echo 1)" "got '$out'"
  done
  out="$(run_block 1 0 0 sh "y y y y" 2>&1)"
  row "an answer already given (--os-access or the control file) is kept and nothing is asked" \
    "$(printf '%s\n' "$out" | grep -qx 'RESULT sh ASKED 0' && echo 0 || echo 1)" "$out"
  out="$(run_block 0 0 0 '' "y y y y" 2>&1)"
  row "no terminal: the answer is none, nothing is asked (even when a stub would have said yes), and it is said" \
    "$([ "$(printf '%s\n' "$out" | grep -c 'RESULT none ASKED 0')" = 1 ] && printf '%s\n' "$out" | grep -q 'nothing is turned on here' && echo 0 || echo 1)" "$out"
  out="$(run_block 1 1 0 '' "y y y y" 2>&1)"
  row "--yes with a terminal and no answer: none, nothing asked" "$(printf '%s\n' "$out" | grep -qx 'RESULT none ASKED 0' && echo 0 || echo 1)" "$out"
  for w in "n n:none" "y n:sh" "n y:os" "y y:both"; do
    out="$(run_block 1 0 0 '' "${w%%:*}" 2>&1)"
    row "a terminal and the answers '${w%%:*}' give ${w##*:}, after exactly two questions" \
      "$(printf '%s\n' "$out" | grep -qx "RESULT ${w##*:} ASKED 2" && echo 0 || echo 1)" "$out"
  done
  out="$(run_block 1 0 0 '' "n n" 2>&1)"
  row "the first question is about the shell and the second about OS access" \
    "$(printf '%s\n' "$out" | grep -q '^Q|Turn on the shell.*|Turn on OS access' && echo 0 || echo 1)" "$out"
  out="$(run_block 1 0 1 '' "n n" 2>&1)"
  row "an upgrade says that the shell and OS access used to be always on" "$(printf '%s\n' "$out" | grep -q 'Until this release the shell and OS access were always on' && echo 0 || echo 1)" "$out"
  out="$(run_block 1 0 0 '' "n n" 2>&1)"
  row "a first install does not say that" "$(printf '%s\n' "$out" | grep -q 'Until this release' && echo 1 || echo 0)" "$out"

  # the real os_yn, as text: the default is NO
  row "the real os_yn reads the terminal, and only an answer starting y is yes (a bare Enter is no)" \
    "$(grep -qF 'read -r -p "$1 [y/N] " a < /dev/tty' "$blk" && grep -qF 'y|Y|yes|YES) return 0 ;; *) return 1 ;;' "$blk" && echo 0 || echo 1)"

  # where the answer travels
  row "--os-access is an option, validated none|sh|os|both" \
    "$(grep -q -- '--os-access) *\[ "\$#" -ge 2 \]' "$inst" && grep -q 'case "\$os_access" in ""|none|sh|os|both) ;;' "$inst" && echo 0 || echo 1)"
  row "the control file's os-access key is read, validated and used only when no option gave an answer" \
    "$(grep -q 'os-access) *cf_osacc=' "$inst" && grep -q 'case "\$cf_osacc" in ""|none|sh|os|both) ;;' "$inst" && grep -q '\[ -n "\$os_access" \] || os_access="\$cf_osacc"' "$inst" && echo 0 || echo 1)"
  row "the question is asked on an upgrade BEFORE 'Continue?' and on a first install BEFORE the passwords" \
    "$(awk '/^if \[ "\$upgrade" -eq 1 \]; then$/ {u=1} u && /^  ask_os_access$/ {a=NR} u && /read -r -p "Continue\? \[Y\/n\] "/ && !c {c=NR} /^ask_os_access$/ {i=NR} /^get_password\(\) \{/ {g=NR} END {exit !(a && c && a<c && i && g && i<g)}' "$inst" && echo 0 || echo 1)"
  row "both solo-stage.sh calls pass the answer (a fresh stage, and --upgrade), none when there is none" \
    "$(grep -q 'solo-stage.sh" --upgrade --os-access "\${os_access:-none}" "\$HOME_DIR"' "$inst" && grep -q 'st_args+=(--os-access "\${os_access:-none}")' "$inst" && echo 0 || echo 1)"
  row "the summary and the log carry the state: the installer fails if solo-stage printed no 'OS access:' line" \
    "$([ "$(grep -c "solo-stage: OS access: //p" "$inst")" -ge 2 ] && grep -q "say \"  shell and OS  : " "$inst" && echo 0 || echo 1)"
  row "an upgrade still refuses every other install option (os-access is the one exception)" \
    "$(grep -q 'it takes no password, control-file, --reload-data, --start-clean, --api, --ssh, --ssh-key or --enable-linger option' "$inst" && echo 0 || echo 1)"
  row "solo-stage.sh takes --os-access none|sh|os|both and refuses anything else" \
    "$(grep -q '"--os-access" \]' "$stage" && grep -q 'none|sh|os|both) osaccess=' "$stage" && grep -q -- '--os-access must be none, sh, os or both' "$stage" && echo 0 || echo 1)"
  row "solo-stage.sh turns on only what was said: SH for sh and both, OS for os and both, each with the verb and a success wording" \
    "$(grep -q 'case "\$osaccess" in sh|both) osacc_one SH ;; esac' "$stage" && grep -q 'case "\$osaccess" in os|both) osacc_one OS ;; esac' "$stage" && grep -q 'sdi SET.OS.ACCESS "\$1" ON' "$stage" && grep -q "Account sduser has SH yes" "$stage" && echo 0 || echo 1)"
  row "solo-stage.sh always reads the state back (the verb with no argument) and fails when it prints no state line" \
    "$(grep -q 'oa_out="$(sdi SET.OS.ACCESS 2>&1)"' "$stage" && grep -q 'did not print its .Account sduser has SH' "$stage" && echo 0 || echo 1)"
  row "the control file sample documents os-access" "$(grep -q '^# os-access$' "$sample" && grep -q '^os-access=$' "$sample" && echo 0 || echo 1)"
  rm -f "$blk"
}

selftest() {
  local tmp name expr target file ok=0 n=0
  tmp="$(mktemp -d)"
  # name | which file | sed expression that breaks it
  while IFS='|' read -r name target expr; do
    [ -n "$name" ] || continue
    n=$((n+1))
    cp "$INSTALLER" "$tmp/installsdsolo.sh"; cp "$STAGE" "$tmp/solo-stage.sh"; cp "$SAMPLE" "$tmp/sample"
    case "$target" in i) file="$tmp/installsdsolo.sh" ;; s) file="$tmp/solo-stage.sh" ;; c) file="$tmp/sample" ;; esac
    sed -i -e "$expr" "$file"
    if cmp -s "$file" "$( [ "$target" = i ] && echo "$INSTALLER" || { [ "$target" = s ] && echo "$STAGE" || echo "$SAMPLE"; } )"; then
      echo "  [FAIL] selftest: $name  <- the mutation changed nothing"; failed=$((failed+1)); continue
    fi
    local p0=$passed f0=$failed
    out="$(check "$tmp/installsdsolo.sh" "$tmp/solo-stage.sh" "$tmp/sample" 2>&1 || true)"
    passed=$p0; failed=$f0
    if printf '%s\n' "$out" | grep -q '\[FAIL\]'; then
      echo "  [PASS] selftest: $name is caught ($(printf '%s\n' "$out" | grep -c '\[FAIL\]') row(s) failed)"; passed=$((passed+1)); ok=$((ok+1))
    else
      echo "  [FAIL] selftest: $name is NOT caught"; failed=$((failed+1))
    fi
  done <<'EOF'
os_yn answers yes to a bare Enter|i|s/\*) return 1 ;; esac/*) return 0 ;; esac/
the terminal test is gone, so a run with no terminal asks|i|s/\[ "\$interactive" -ne 1 \] || \[ "\$assume_yes" -eq 1 \]/false/
--yes no longer skips the question|i|s/ || \[ "\$assume_yes" -eq 1 \]; then$/; then/
the answer is not kept when one was given|i|s/\[ -z "\$os_access" \] || return 0/true/
os_access_word says sh for both|i|s/if \[ "\$1" = 1 \] \&\& \[ "\$2" = 1 \]; then echo both/if [ "$1" = 1 ] \&\& [ "$2" = 1 ]; then echo sh/
the first install no longer asks|i|s/^ask_os_access$/true/
the upgrade passes no answer to solo-stage|i|s/--upgrade --os-access "\${os_access:-none}"/--upgrade/
the fresh stage passes no answer to solo-stage|i|s/st_args+=(--os-access "\${os_access:-none}")/true/
the control file's os-access is not read|i|s/os-access)       cf_osacc=/os-accessX)      cf_osacc=/
the summary line is gone|i|s/say "  shell and OS  : /say "  /
solo-stage turns on OS for sh|s|s/case "\$osaccess" in os|both) osacc_one OS ;; esac/case "$osaccess" in sh|os|both) osacc_one OS ;; esac/
solo-stage no longer reads the state back|s|s/oa_out="\$(sdi SET.OS.ACCESS 2>\&1)" || true/oa_out=""/
the sample no longer documents os-access|c|s/^# os-access$/# nothing/
EOF
  rm -rf "$tmp"
  echo "selftest: $ok of $n mutants caught"
}

for f in "$INSTALLER" "$STAGE" "$SAMPLE"; do
  [ -f "$f" ] || { echo "test-install-osaccess: CANNOT RUN - $f is not there"; exit 2; }
done
echo "test-install-osaccess: installer $INSTALLER"
echo "test-install-osaccess: stage     $STAGE"
check "$INSTALLER" "$STAGE" "$SAMPLE"
if [ "${1:-}" = "--selftest" ]; then selftest; fi
echo
echo "test-install-osaccess: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ]
