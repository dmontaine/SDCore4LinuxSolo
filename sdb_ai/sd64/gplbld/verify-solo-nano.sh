#!/bin/bash
# verify-solo-nano.sh - does the NANO verb start nano with SD BASIC highlighting? (LSOLO 16)
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-nano.sh HOME_DIR ACCOUNT_PASSWORD_FILE
#
# No sudo.  HOME_DIR is a Solo tree built by solo-stage.sh with the account password, its daemon
# running.  Needs nano on the PATH (exit 2 without it).  Drives sd over a pty (ptyrun.py).
#
# WHAT IT PROVES: mkrc.sh copies /etc/nanorc, the user's own rc files and then includes SD's
# syntax file - the user's settings survive; the NANO verb writes <tree>/nanocfg/sd.nanorc and starts
# nano with it and nano prints no rc error ("Mistakes in ..."; measured first with an include of
# /etc/nanorc, which nano refuses); and nano, given that rc, KNOWS the syntax "sdbasic".
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || refuse "usage: bash $0 HOME_DIR ACCOUNT_PASSWORD_FILE"
H="$1"; PWF="$2"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
[ -x "$H/bin/sd" ] && [ -f "$H/.sdcoresolo" ] || refuse "$H is not a built Solo tree"
[ -s "$PWF" ] || refuse "cannot read $PWF"
[ -f "$H/nanocfg/mkrc.sh" ] || refuse "$H has no nanocfg/mkrc.sh - the tree predates LSOLO 16"
NANO="$(command -v nano)" || refuse "nano is not installed"
command -v python3 >/dev/null || refuse "python3 is required"
GOOD="$(head -1 "$PWF")"
umask 077

echo "verify-solo-nano inputs:"
echo "  tree    : $H"
echo "  nano    : $NANO ($("$NANO" --version | head -1))"
echo "  running as : $(id -un)"

pass=0; fail=0; legs=0
leg() { legs=$((legs+1)); if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT

# ---- 1. mkrc.sh keeps the user's own settings and ends with SD's syntax.
mkdir -p "$W/hm/.config/nano"
printf 'set zapme\n' > "$W/hm/.nanorc"
printf 'set tabsize 3\n' > "$W/hm/.config/nano/nanorc"
HOME="$W/hm" XDG_CONFIG_HOME="$W/hm/.config" sh "$H/nanocfg/mkrc.sh" "$H/nanocfg/sdbasic.nanorc" "$W/out.nanorc"
if [ -s "$W/out.nanorc" ] && grep -qx 'set zapme' "$W/out.nanorc" && grep -qx 'set tabsize 3' "$W/out.nanorc" \
   && [ "$(tail -1 "$W/out.nanorc")" = "include \"$H/nanocfg/sdbasic.nanorc\"" ] \
   && { [ ! -r /etc/nanorc ] || grep -qx 'include "/usr/share/nano/\*.nanorc"' "$W/out.nanorc" || [ "$(grep -c . /etc/nanorc)" -gt 0 ]; }; then
  leg "1 the rc file keeps the user's settings and ends with SD's syntax" "~/.nanorc and the XDG rc copied in, /etc/nanorc first, the include last" 0 "$(grep -c . "$W/out.nanorc") lines"
else
  leg "1 the rc file keeps the user's settings and ends with SD's syntax" "user rc lines present, SD include last" 1 "$(tail -3 "$W/out.nanorc" 2>&1 | tr '\n' '|')"
fi

# ---- 2. the NANO verb writes the rc and starts nano with it, with no rc error on the screen.
rm -f "$H/nanocfg/sd.nanorc"
t="$(python3 "$here/ptyrun.py" --timeout 25 "$H/bin/sd" expect:'Password:' send:"$GOOD" expect:'^:|:' send:'nano bp zzverifynano' \
     expect:'Read 0 lines|New Buffer' raw:'\x18' expect:'editor was given|:' send:'OFF' 2>&1)"
rc2=$?
if [ "$rc2" -eq 0 ] && [ -s "$H/nanocfg/sd.nanorc" ] && ! printf '%s\n' "$t" | grep -qi 'Mistakes in\|Error in\|Unknown syntax'; then
  leg "2 the NANO verb starts nano with its rc file, and nano finds nothing wrong with it" "nanocfg/sd.nanorc written; no 'Mistakes in' / 'Error in' on the screen" 0 "started"
else
  leg "2 the NANO verb starts nano with its rc file" "sd.nanorc written and no rc error" 1 "rc=$rc2 rc-file=$([ -s "$H/nanocfg/sd.nanorc" ] && echo yes || echo NO); $(printf '%s\n' "$t" | grep -i 'Mistakes\|Error in\|ptyrun:' | head -2 | tr '\n' '|')"
fi
rm -f "$H/user_accounts/sduser/bp/zzverifynano"

# ---- 3. nano, given that rc, knows the syntax "sdbasic" (an unknown name is refused on the screen).
t="$(python3 "$here/ptyrun.py" --timeout 15 --arg --rcfile="$H/nanocfg/sd.nanorc" --arg -Y --arg sdbasic --arg "$W/zz.txt" "$NANO" expect:'Read 0 lines|New Buffer|GNU nano' raw:'\x18' 2>&1)"
if printf '%s\n' "$t" | grep -q 'ptyrun: step' ; then
  leg "3 nano knows the syntax sdbasic" "starts with -Y sdbasic and an SD rc file" 1 "$(printf '%s\n' "$t" | grep 'ptyrun:' | head -1)"
elif printf '%s\n' "$t" | grep -qi 'Unknown syntax\|Mistakes in\|Error in'; then
  leg "3 nano knows the syntax sdbasic" "no 'Unknown syntax' / rc error" 1 "$(printf '%s\n' "$t" | grep -i 'Unknown syntax\|Mistakes\|Error in' | head -1)"
else
  leg "3 nano knows the syntax sdbasic" "-Y sdbasic accepted" 0 "accepted"
fi

echo
echo "verify-solo-nano: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
