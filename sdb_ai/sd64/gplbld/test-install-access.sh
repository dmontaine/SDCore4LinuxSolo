#!/bin/bash
#
# test-install-access.sh - installsdsolo.sh asks SD Core's two access questions (owner, 14 Nov 2026: "Solo should follow Core in management of API
# and SSH access", then, of the API's default, "Core's questions, API off").  The ACCESS-ASK block:
#   "Allow API access from other computers? opens TCP port N (y/N)"  - y opens the API to the network, anything else leaves it OFF
#   "Allow ssh access from other computers? opens TCP port N (y/N)"  - y opens ssh to the network, anything else keeps the default (this computer)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-access.sh
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-access.sh --selftest
#   INSTALLER=<copy of the installer> bash .../test-install-access.sh                     (what --selftest uses)
#
# FREE CHECK: no install, no sudo, no sshd.  The block is cut out of the installer, its "< /dev/tty" is taken out so the answer comes on stdin, the sshd
# detection line becomes have_sshd=$HAVE, ssh_default_choice is the installer's own (cut between its definition and "# END ssh_default"), and it runs
# under the installer's own set line.  Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
#   A1  the API: y, Y, yes, YES open it; Enter, n, no, maybe and an ended input leave it off
#   A2  not interactive -> off; an --api given on the command line is kept and nothing is asked
#   S1  ssh, with sshd present: y opens it; Enter, n, no, maybe and an ended input give local (this computer only)
#   S2  no sshd and --skip-packages: off, no question, a warning naming the two commands
#   S3  a key given, or --ssh given, or not interactive: no question; the key or the default or the given value
#   Q   the block asks exactly two questions, each ending (y/N); no off/local/open prompt is left in the installer
# ANCHORED ON THE VARIABLES the block set (api=, ssh=) and on how many prompts it printed.

HERE="$(cd "$(dirname "$0")" && pwd)"
THIS="$HERE/$(basename "$0")"
TREE="$(cd "$HERE/../../.." && pwd)"
INST="${INSTALLER:-$TREE/installsdsolo.sh}"

if [ "${1:-}" = "--selftest" ]; then
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  caught=0; missed=0; total=0
  A='/^# ACCESS-ASK-BEGIN/,/^# ACCESS-ASK-END/'
  mutant() {
    local f="$T/$1.sh"; total=$((total+1))
    sed -e "$2" "$TREE/installsdsolo.sh" > "$f"
    if cmp -s "$TREE/installsdsolo.sh" "$f"; then echo "  [MISSED] $1: the mutation changed nothing"; missed=$((missed+1)); return; fi
    if INSTALLER="$f" bash "$THIS" > "$T/$1.out" 2>&1; then echo "  [MISSED] $1: the check still passed"; missed=$((missed+1))
    else echo "  [caught] $1"; caught=$((caught+1)); fi
  }
  echo "selftest: the real installer first (must pass), then mutants (each must not)"
  bash "$THIS" > "$T/real.out" 2>&1 || { echo "  [FAIL] the real installer does not pass:"; tail -8 "$T/real.out"; exit 1; }
  echo "  [ok] the real installer passes"
  mutant api-default-local   "$A s/\*) api=\"off\" ;; esac/*) api=\"local\" ;; esac/"
  mutant api-any-opens       "$A s/case \"\$yn_api\" in \[yY\]|\[yY\]\[eE\]\[sS\])/case \"\$yn_api\" in *)/"
  mutant ssh-no-means-off    "$A s/\*) ssh=\"\$ssh_default\" ;; esac/*) ssh=\"off\" ;; esac/"
  mutant ssh-any-opens       "$A s/case \"\$yn_ssh\" in \[yY\]|\[yY\]\[eE\]\[sS\])/case \"\$yn_ssh\" in *)/"
  mutant ssh-asked-without-sshd "$A s/if \[ \"\$ssh_default\" = \"off\" \]; then/if false; then/"
  mutant prompt-yn-swapped   "$A s|(y/N) \" yn_api|(Y/n) \" yn_api|"
  mutant old-prompt-back     "/^# ACCESS-ASK-END/i read -r -p \"API listener [off/local/open] (default off): \" x < /dev/tty || true"
  mutant noninteractive-open "$A s/^    api=\"off\"$/    api=\"open\"/"
  echo "selftest: $caught of $total mutants caught, $missed missed"
  [ "$missed" -eq 0 ]
  exit $?
fi

cut_block() { awk -v b="# $1-BEGIN" -v e="# $1-END" '$0 == b {f=1; next} $0 == e {f=0} f {print}' "$INST"; }
BLK=$(cut_block ACCESS-ASK)
FN=$(awk '/^ssh_default_choice\(\) *\{/{f=1} f{print} /^# END ssh_default/{f=0}' "$INST")
OPTS=$(grep -m1 -E '^set -' "$INST")
echo "installer : $INST"
[ -z "$BLK" ] && { echo "test-install-access: CANNOT RUN - no ACCESS-ASK block"; exit 2; }
[ -z "$FN" ] && { echo "test-install-access: CANNOT RUN - no ssh_default_choice"; exit 2; }
[ -z "$OPTS" ] && { echo "test-install-access: CANNOT RUN - no set line"; exit 2; }
BLK="${BLK// < \/dev\/tty/}"
BLK=$(printf '%s\n' "$BLK" | sed -E 's/^have_sshd=0; if command -v sshd .*$/have_sshd=$HAVE/')
printf '%s\n' "$BLK" | grep -q '^have_sshd=\$HAVE$' || { echo "test-install-access: CANNOT RUN - the sshd detection line was not found"; exit 2; }

pass=0; fail=0
row() { if [ "$2" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1"; else fail=$((fail+1)); echo "  [FAIL] $1   <- $3"; fi; }

run() {   # input interactive have-sshd skip-packages given-api given-ssh key
  printf '%s' "$1" | OPTS="$OPTS" FN="$FN" BLK="$BLK" IA="$2" HAVE="$3" SKIP="$4" GA="$5" GS="$6" KEY="$7" bash -c '
      eval "$OPTS"
      say() { :; }; warn() { echo "WARN: $*"; }; refuse() { echo "REFUSED: $*"; exit 3; }
      read() { [ "${2:-}" = -p ] && echo "PROMPT: $3"; builtin read "$@"; }   # read -p prints its prompt only on a terminal
      eval "$FN"
      interactive=$IA; skip_pkgs=$SKIP; api=$GA; ssh=$GS; ssh_key=$KEY; api_port=4249; ssh_port=4251; managed=0
      eval "$BLK"
      echo "API=$api SSH=$ssh"' 2>&1
}
nprompts() { printf '%s' "$1" | grep -o -E 'access from other computers\?' | wc -l; }

bad=""
for a in y Y yes YES; do out=$(run "$a"$'\n' 1 1 0 "" "" ""); [[ "$out" == *"API=open "* ]] || bad="$bad '$a'"; done
for a in "" n no maybe; do out=$(run "$a"$'\n' 1 1 0 "" "" ""); [[ "$out" == *"API=off "* ]] || bad="$bad '$a'"; done
out=$(run "" 1 1 0 "" "" ""); [[ "$out" == *"API=off "* ]] || bad="$bad ended"
row "A1 API: only y or yes opens it; Enter, n, no, maybe and an ended input leave it off" "$([ -z "$bad" ] && echo 0 || echo 1)" "wrong for:$bad"
out1=$(run "y"$'\n'"y"$'\n' 0 1 0 "" "" ""); out2=$(run "n"$'\n' 1 1 0 local "" "")
row "A2 not interactive -> off; a given --api is kept and not asked" \
    "$([[ "$out1" == *"API=off "* && "$out2" == *"API=local "* ]] && [ "$(nprompts "$out2")" = 1 ] && echo 0 || echo 1)" "$out1 | $out2"

bad=""
for a in y Y yes YES; do out=$(run "n"$'\n'"$a"$'\n' 1 1 0 "" "" ""); [[ "$out" == *"SSH=open"* ]] || bad="$bad '$a'"; done
for a in "" n no maybe; do out=$(run "n"$'\n'"$a"$'\n' 1 1 0 "" "" ""); [[ "$out" == *"SSH=local"* ]] || bad="$bad '$a'"; done
out=$(run "n"$'\n' 1 1 0 "" "" ""); [[ "$out" == *"SSH=local"* ]] || bad="$bad ended"
row "S1 ssh with sshd: only y or yes opens it; anything else is this computer only" "$([ -z "$bad" ] && echo 0 || echo 1)" "wrong for:$bad"
out=$(run "n"$'\n'"y"$'\n' 1 0 1 "" "" "")
row "S2 no sshd and --skip-packages: off, not asked, a warning with the commands" \
    "$([[ "$out" == *"SSH=off"* && "$out" == *"WARN: no ssh server program"* && "$out" == *"solo-ssh.sh setup"* ]] && [ "$(nprompts "$out")" = 1 ] && echo 0 || echo 1)" "$out"
o1=$(run "n"$'\n'"y"$'\n' 1 1 0 "" "" /tmp/k.pub); o2=$(run "n"$'\n'"y"$'\n' 1 1 0 "" off ""); o3=$(run "" 0 1 0 "" "" "")
row "S3 a key, a given --ssh, or no terminal: ssh not asked (local, off, local)" \
    "$([[ "$o1" == *"SSH=local"* && "$o2" == *"SSH=off"* && "$o3" == *"SSH=local"* ]] && [ "$(nprompts "$o1")" = 1 ] && [ "$(nprompts "$o2")" = 1 ] && [ "$(nprompts "$o3")" = 0 ] && echo 0 || echo 1)" "$o1 | $o2 | $o3"

nq=$(printf '%s\n' "$BLK" | grep -c 'read -r -p')
yn=$(printf '%s\n' "$BLK" | grep 'read -r -p' | grep -c '(y/N) "')
old=$(grep -v '^ *#' "$INST" | grep -c -E '\[off/local/open\]' || true)
row "Q two questions, each (y/N); no off/local/open prompt left" "$([ "$nq" = 2 ] && [ "$yn" = 2 ] && [ "$old" = 0 ] && echo 0 || echo 1)" "questions=$nq yn=$yn old=$old"

echo "test-install-access: $pass passed, $fail failed"
[ "$pass" -eq 0 ] && { echo "test-install-access: NOTHING RAN"; exit 2; }
[ "$fail" -eq 0 ]
