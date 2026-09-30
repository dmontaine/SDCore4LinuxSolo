#!/bin/bash
# verify-solo-install.sh - does installsolo.sh / deletesolo.sh do what they say?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-install.sh [--full]
#
# No sudo.  Without --full it runs the REFUSAL legs only: each is a way the installer
# must stop BEFORE it downloads or changes anything (a weak password, a port below
# 1024, a directory that is not empty, no way to ask for a password, a global
# password equal to the account's, an already-installed tree).  With --full it also
# does a real install into a scratch directory - a download, a build, the bootstrap,
# a systemd user service with a local API socket - runs the installed tree's own
# checks, and uninstalls with the data kept.  --full takes about three minutes.
#
# THE SOURCE IS THE COMMITTED HEAD OF THIS REPOSITORY, not GitHub: it sets
# SDSOLO_REPO_URL (the installer's announced test hook) to this checkout, so it
# refuses when the working tree has uncommitted changes - what would be installed
# is HEAD, and a dirty tree would be measuring something else.  The installer is
# tested against origin/main only after it is pushed.
#
# EVERY LEG ANCHORS ON THE INSTALLER'S OWN WORDS ("REFUSED: ...", "SOLO INSTALL
# COMPLETE", "SOLO DELETE COMPLETE"), never on an exit code alone, and a refusal leg
# also checks that NOTHING was created (the scratch directory stays absent).
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
full=0
[ "${1:-}" = "--full" ] && { full=1; shift; }
[ "$#" -eq 0 ] || refuse "usage: bash $0 [--full]"
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$here" rev-parse --show-toplevel 2>/dev/null)" || refuse "this is not inside a git checkout"
INSTALL="$REPO/installsolo.sh"; DELETE="$REPO/deletesolo.sh"
[ -f "$INSTALL" ] && [ -f "$DELETE" ] || refuse "installsolo.sh or deletesolo.sh is missing from $REPO"
[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ] || refuse "the working tree has uncommitted changes; the installer installs the committed HEAD, so commit first"
export SDSOLO_REPO_URL="file://$REPO"
COMMIT="$(git -C "$REPO" rev-parse HEAD)"

W="$(mktemp -d)"; chmod 700 "$W"
trap 'rm -rf "$W"' EXIT
echo "verify-solo-install inputs:"
echo "  repository : $REPO (HEAD $COMMIT)"
echo "  installer  : $INSTALL"
echo "  scratch    : $W (removed at the end)"
echo "  mode       : $([ "$full" -eq 1 ] && echo 'refusals + FULL install/uninstall' || echo 'refusals only')"
echo "  running as : $(id -un) (uid $(id -u))"

printf 'Test-Pass-1!\n' > "$W/acc.pw"; printf 'Admin-Pass-2!\n' > "$W/adm.pw"; printf 'Global-Pass-5!\n' > "$W/glb.pw"
printf 'weak\n' > "$W/weak.pw"; printf 'Test-Pass-1!\n' > "$W/same.pw"

pass=0; fail=0; legs=0
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
leg() {
  legs=$((legs+1))
  if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"
  else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi
}
# refusal NAME EXPECTED-TEXT HOME_DIR ARGS... - run the installer, non-interactively
# (stdin from /dev/null), and require its REFUSED line to contain the text and the
# scratch home to still not exist.
refusal() {
  local name="$1" want="$2" home="$3"; shift 3
  local out
  out="$(timeout 120 bash "$INSTALL" --home "$home" --skip-packages --yes "$@" < /dev/null 2>&1 | strip)"
  if printf '%s\n' "$out" | grep -q "^REFUSED: .*$want" && ! printf '%s\n' "$out" | grep -q '^SOLO INSTALL COMPLETE' \
     && ! printf '%s\n' "$out" | grep -q '^Downloading the source'; then
    leg "$name" "REFUSED ... $want, before any download" 0 "refused"
  else
    leg "$name" "REFUSED ... $want, before any download" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|Downloading' | head -2 | tr '\n' ' ')"
  fi
}

# ---- R1-R6: refusals, all before the download.
refusal "R1 a weak account password"        "does not meet the rule"        "$W/h1" --account-password-file "$W/weak.pw" --admin-password-file "$W/adm.pw"
refusal "R2 an API port below 1024"         "must be 1024-65535"            "$W/h2" --api-port 80 --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
mkdir -p "$W/h3" && echo x > "$W/h3/somefile"
refusal "R3 a directory that is not empty"  "exists and is not empty"       "$W/h3" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
refusal "R4 no password and no terminal"    "no terminal to ask on"          "$W/h4"
refusal "R5 global password = account's"    "must differ from the account"   "$W/h5" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" --global-password-file "$W/same.pw"
mkdir -p "$W/h6" && : > "$W/h6/.sdcoresolo"
refusal "R6 already installed"              "already installed"              "$W/h6" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
absent=0; for d in h1 h2 h4 h5; do [ -e "$W/$d" ] && absent=1; done
[ "$absent" -eq 0 ] && leg "R7 a refusal creates nothing" "h1, h2, h4 and h5 do not exist" 0 "none created" || leg "R7 a refusal creates nothing" "h1, h2, h4, h5 do not exist" 1 "one was created"

if [ "$full" -eq 1 ]; then
  command -v systemctl >/dev/null || refuse "systemctl is required for --full"
  systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is already running for this user; --full would collide with it"
  ss -ltn 2>/dev/null | grep -q ':14244 ' && refuse "port 14244 is in use"
  ls -d "$HOME/.sdsolotmp" >/dev/null 2>&1 && refuse "$HOME/.sdsolotmp exists; remove it (a previous install may have been interrupted)"
  H="$W/inst"
  echo "  (full install into $H - a download, a build and a bootstrap; about three minutes)"
  out="$(timeout 900 bash "$INSTALL" --home "$H" --skip-packages --yes --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" --api local --api-port 14244 2>&1 | strip)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H"; then
    leg "F1 install" "'SOLO INSTALL COMPLETE <home>'" 0 "complete"
  else
    leg "F1 install" "'SOLO INSTALL COMPLETE <home>'" 1 "$(printf '%s\n' "$out" | tail -4 | tr '\n' ' ')"
    echo; echo "verify-solo-install: $pass passed, $fail failed, of $legs legs"; exit 1
  fi
  # F2 what the installer promised
  ok=1; why=""
  printf '%s\n' "$out" | grep -qx '  a session as sduser works' || { ok=0; why="$why no-session-check;"; }
  printf '%s\n' "$out" | grep -qx '  sd -internal is closed' || { ok=0; why="$why no-internal-check;"; }
  [ "$(sed -n 1p "$H/.sdcore-install")" = "commit $COMMIT" ] || { ok=0; why="$why stamp-commit;"; }
  [ ! -e "$HOME/.sdsolotmp" ] || { ok=0; why="$why clone-left;"; }
  [ ! -e "$H/\$internal" ] || { ok=0; why="$why marker-left;"; }
  [ "$(stat -c '%a' "$H")" = "700" ] || { ok=0; why="$why home-mode;"; }
  [ "$(stat -c '%a' "$H/\$cred")" = "700" ] || { ok=0; why="$why cred-mode;"; }
  [ "$(systemctl --user is-active sd-solo.service)" = "active" ] || { ok=0; why="$why service;"; }
  [ -L "$HOME/.local/bin/sd" ] && [ "$(readlink "$HOME/.local/bin/sd")" = "$H/bin/sd" ] || { ok=0; why="$why link;"; }
  [ "$ok" -eq 1 ] && leg "F2 what the installer promised" "self-checks ran; stamp is HEAD; clone and marker gone; modes 700; service active; link" 0 "all" || leg "F2 what the installer promised" "self-checks; stamp; clone/marker gone; modes; service; link" 1 "$why"
  # F3 the installed tree passes its own witness
  if [ -f "$here/verify-solo.sh" ]; then
    v="$(timeout 900 bash "$here/verify-solo.sh" "$H" "$W/acc.pw" "$W/adm.pw" 2>&1 | strip | grep -E 'verify-solo:|\[FAIL\]' | cut -c1-240)"
    case "$v" in
      *", 0 failed,"*) leg "F3 the installed tree passes verify-solo.sh" "0 failed" 0 "$(printf '%s\n' "$v" | tail -1)" ;;
      *) leg "F3 the installed tree passes verify-solo.sh" "0 failed" 1 "$v" ;;
    esac
  fi
  # F4 uninstall, keeping the data, from the tree's own copy of the script
  echo "kept data" > "$H/user_accounts/sduser/keepme.txt"
  dout="$(bash "$H/tools/deletesolo.sh" --keep-data --yes 2>&1 | strip)"
  kept="$(printf '%s\n' "$dout" | sed -n 's/^your data is in \(.*\)\/sduser$/\1/p')"
  left=0
  [ -e "$H" ] && left=1
  [ -e "$HOME/.local/bin/sd" ] && left=1
  systemctl --user is-active sd-solo.service >/dev/null 2>&1 && left=1
  ss -ltn 2>/dev/null | grep -q ':14244 ' && left=1
  if printf '%s\n' "$dout" | grep -qx "SOLO DELETE COMPLETE $H" && [ "$left" -eq 0 ] && [ -n "$kept" ] && [ "$(cat "$kept/sduser/keepme.txt" 2>/dev/null)" = "kept data" ]; then
    leg "F4 uninstall keeps the data and leaves nothing" "'SOLO DELETE COMPLETE', no tree/link/service/port, keepme.txt kept" 0 "kept in $kept"
  else
    leg "F4 uninstall keeps the data and leaves nothing" "complete; nothing left; data kept" 1 "left=$left kept='$kept' $(printf '%s\n' "$dout" | tail -2 | tr '\n' ' ')"
  fi
  [ -z "$kept" ] || rm -rf "$kept"    # my own test data, in the home directory
fi

echo
echo "verify-solo-install: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
