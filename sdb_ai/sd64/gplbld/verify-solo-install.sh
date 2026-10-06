#!/bin/bash
# verify-solo-install.sh - does installsdsolo.sh / deletesdsolo.sh do what they say?
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
INSTALL="$REPO/installsdsolo.sh"; DELETE="$REPO/deletesdsolo.sh"
[ -f "$INSTALL" ] && [ -f "$DELETE" ] || refuse "installsdsolo.sh or deletesdsolo.sh is missing from $REPO"
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
# LSOLO 23: --api-port is gone (owner, 2 Oct 2026: no adjustable ports).  R2 is the test hook's
# own range check; R2b is the option's absence.
SDSOLO_TEST_API_PORT=80 refusal "R2 a test-hook API port below 1024" "must be 1024-65535" "$W/h2" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
refusal "R2b --api-port is not an option"   "unknown option: --api-port"   "$W/h2b" --api-port 14244 --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
mkdir -p "$W/h3" && echo x > "$W/h3/somefile"
refusal "R3 a directory that is not empty"  "exists and is not empty"       "$W/h3" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
refusal "R4 no password and no terminal"    "no terminal to ask on"          "$W/h4"
refusal "R5 global password = account's"    "must differ from the account"   "$W/h5" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" --global-password-file "$W/same.pw"
mkdir -p "$W/h6" && : > "$W/h6/.sdcoresolo"
refusal "R6 already installed"              "already installed"              "$W/h6" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
refusal "R8 --upgrade with nothing installed" "there is no SD Core for Linux Solo in .* to upgrade" "$W/h7" --upgrade
refusal "R9 --upgrade of a tree the installer did not make" "has no .sdcore-install record" "$W/h6" --upgrade
mkdir -p "$W/h8" && : > "$W/h8/.sdcoresolo" && echo "commit x" > "$W/h8/.sdcore-install"
refusal "R10 --upgrade takes no password option" "keeps the passwords .*API and ssh settings" "$W/h8" --upgrade --account-password-file "$W/acc.pw"
# LSOLO 38 (6 Oct 2026): there is one install; a computer is managed if it has a global password.
refusal "R11 --managed is gone"             "--managed is gone"              "$W/h11" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" --managed
printf '[install]\nadmin-password=%s\napi=sometimes\n' "$(head -1 "$W/adm.pw")" > "$W/ctl-badapi.conf"
refusal "R12 a bad api answer in the install file" "api in the control file must be off, local or open" "$W/h12" --control-file "$W/ctl-badapi.conf"
printf '[install]\nadmin-password=%s\nssh=off\nssh-public-key-file=%s\n' "$(head -1 "$W/adm.pw")" "$W/acc.pw" > "$W/ctl-sshkey.conf"
refusal "R13 ssh off in the install file with a key" "an ssh public key needs ssh on" "$W/h13" --control-file "$W/ctl-sshkey.conf"
printf '[install]\nadmin-password=%s\nglobal-password=\n' "$(head -1 "$W/adm.pw")" > "$W/ctl-noglobal.conf"
refusal "R14 an install file with no global password still asks for the account password" "no account password was given and there is no terminal to ask on" "$W/h14" --control-file "$W/ctl-noglobal.conf"
# LSOLO 39: the one non-empty folder the installer will use is what an uninstall that kept the data leaves - the
# .sdcore-kept stamp, user_accounts/sduser and sd.conf and NOTHING else.  A folder with the stamp and anything more
# is refused (it is someone's folder), and the two answers cannot both be given.
mkdir -p "$W/h15/user_accounts/sduser/voc" && printf 'commit x\nkept 2026-10-06T00:00:00+00:00\n' > "$W/h15/.sdcore-kept" && echo x > "$W/h15/notes.txt"
refusal "R15 a kept-data folder with something else in it is refused" "exists and is not empty" "$W/h15" --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw"
refusal "R16 --upgrade takes no --reload-data" "keeps the passwords .*the account's data and sd.conf" "$W/h8" --upgrade --reload-data
refusal "R17 --reload-data and --start-clean contradict" "contradict each other" "$W/h17" --reload-data --start-clean
printf '[install]\nadmin-password=%s\nreload-data=maybe\n' "$(head -1 "$W/adm.pw")" > "$W/ctl-badreload.conf"
refusal "R18 a bad reload-data answer in the install file" "reload-data in the control file must be yes or no" "$W/h18" --control-file "$W/ctl-badreload.conf"
absent=0; for d in h1 h2 h2b h4 h5 h7 h11 h12 h13 h14 h17 h18; do [ -e "$W/$d" ] && absent=1; done
[ "$absent" -eq 0 ] && leg "R7 a refusal creates nothing" "h1, h2, h4 and h5 do not exist" 0 "none created" || leg "R7 a refusal creates nothing" "h1, h2, h4, h5 do not exist" 1 "one was created"

if [ "$full" -eq 1 ]; then
  command -v systemctl >/dev/null || refuse "systemctl is required for --full"
  systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is already running for this user; --full would collide with it"
  ss -ltn 2>/dev/null | grep -q ':14244 ' && refuse "port 14244 is in use"
  export SDSOLO_TEST_API_PORT=14244   # the installer's announced test hook; there is no --api-port (LSOLO 23)
  ls -d "$HOME/.sdsolotmp" >/dev/null 2>&1 && refuse "$HOME/.sdsolotmp exists; remove it (a previous install may have been interrupted)"
  H="$W/inst"
  echo "  (full install into $H - a download, a build and a bootstrap; about three minutes)"
  out="$(timeout 900 bash "$INSTALL" --home "$H" --skip-packages --yes --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" --api local 2>&1 | strip)"
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
  # 02 Oct 26 - THE COMMAND NAMES: sd-solo is a link to this tree's binary, and this product makes
  # no plain sd (a file of the user's own called sd is theirs; a link to this tree's old bin/sd, or
  # a launcher carrying the marker line, would be this product's and must not be there).
  [ -L "$HOME/.local/bin/sd-solo" ] && [ "$(readlink "$HOME/.local/bin/sd-solo")" = "$H/bin/sd-solo" ] || { ok=0; why="$why sd-solo-link;"; }
  [ -x "$H/bin/sd-solo" ] || { ok=0; why="$why no-sd-solo-exe;"; }
  [ ! -e "$H/bin/sd" ] && [ ! -L "$H/bin/sd" ] || { ok=0; why="$why old-bin-sd-left;"; }
  if [ -L "$HOME/.local/bin/sd" ]; then case "$(readlink "$HOME/.local/bin/sd")" in "$H/bin/"*) ok=0; why="$why sd-link-ours;" ;; esac; fi
  if [ -f "$HOME/.local/bin/sd" ] && grep -qF 'SD Core for Linux Solo launcher.' "$HOME/.local/bin/sd" 2>/dev/null; then ok=0; why="$why sd-launcher-left;"; fi
  [ "$ok" -eq 1 ] && leg "F2 what the installer promised" "self-checks ran; stamp is HEAD; clone and marker gone; modes 700; service active; link" 0 "all" || leg "F2 what the installer promised" "self-checks; stamp; clone/marker gone; modes; service; link" 1 "$why"
  # F3 the installed tree passes its own witness
  if [ -f "$here/verify-solo.sh" ]; then
    v="$(timeout 900 bash "$here/verify-solo.sh" "$H" "$W/acc.pw" "$W/adm.pw" 2>&1 | strip | grep -E 'verify-solo:|\[FAIL\]' | cut -c1-240)"
    case "$v" in
      *", 0 failed,"*) leg "F3 the installed tree passes verify-solo.sh" "0 failed" 0 "$(printf '%s\n' "$v" | tail -1)" ;;
      *) leg "F3 the installed tree passes verify-solo.sh" "0 failed" 1 "$v" ;;
    esac
  fi
  # U1-U3 the installer's own in-place upgrade (LSOLO 13): the data, the password and the
  # service survive, the stamp records where it came from, the safety copy is left.
  echo "kept data" > "$H/user_accounts/sduser/keepme.txt"
  kept_sum="$(cd "$H" && find user_accounts '$cred' -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)"
  # the second refusal: without --upgrade an installed tree is still refused, and the refusal says how to upgrade
  o="$(timeout 60 bash "$INSTALL" --home "$H" --skip-packages --yes --account-password-file "$W/acc.pw" --admin-password-file "$W/adm.pw" </dev/null 2>&1 | strip)"
  if printf '%s\n' "$o" | grep -q '^REFUSED: .*already installed' && printf '%s\n' "$o" | grep -q -- '--upgrade --home'; then
    leg "U0 an installed tree is refused, with the way to upgrade it" "REFUSED ... already installed, naming --upgrade --home" 0 "refused"
  else
    leg "U0 an installed tree is refused, with the way to upgrade it" "REFUSED ... already installed, naming --upgrade" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' ' ')"
  fi
  uout="$(timeout 900 bash "$INSTALL" --upgrade --home "$H" --skip-packages --yes 2>&1 | strip)"
  if printf '%s\n' "$uout" | grep -qx "SOLO UPGRADE COMPLETE $H" \
     && printf '%s\n' "$uout" | grep -qx '  a session as sduser works' && printf '%s\n' "$uout" | grep -qx '  sd -internal is closed'; then
    leg "U1 --upgrade completes and self-checks" "'SOLO UPGRADE COMPLETE <home>', a session works, the internal door is closed" 0 "complete"
  else
    leg "U1 --upgrade completes and self-checks" "'SOLO UPGRADE COMPLETE <home>'" 1 "$(printf '%s\n' "$uout" | tail -6 | tr '\n' ' ')"
  fi
  ok=1; why=""
  [ "$(sed -n 1p "$H/.sdcore-install")" = "commit $COMMIT" ] || { ok=0; why="$why stamp-commit;"; }
  grep -q '^upgraded-from ' "$H/.sdcore-install" || { ok=0; why="$why no-upgraded-from;"; }
  grep -qx 'mode unmanaged' "$H/.sdcore-install" || { ok=0; why="$why mode;"; }
  [ "$(cd "$H" && find user_accounts '$cred' -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)" = "$kept_sum" ] || { ok=0; why="$why data-changed;"; }
  [ "$(systemctl --user is-active sd-solo.service)" = "active" ] || { ok=0; why="$why service;"; }
  ls -d "$H".before-upgrade-* >/dev/null 2>&1 || { ok=0; why="$why no-safety-copy;"; }
  [ ! -e "$HOME/.sdsolotmp" ] && [ ! -e "$H/\$internal" ] && [ ! -e "$H/.last-upgrade-backup" ] || { ok=0; why="$why leftovers;"; }
  [ "$ok" -eq 1 ] && leg "U2 what the upgrade promised" "stamp is HEAD with upgraded-from; account data and \$cred byte-identical; service active; safety copy left; no leftovers" 0 "all" \
                  || leg "U2 what the upgrade promised" "stamp, data identical, service, safety copy, no leftovers" 1 "$why"
  if [ -f "$here/verify-solo.sh" ]; then
    v="$(timeout 900 bash "$here/verify-solo.sh" "$H" "$W/acc.pw" "$W/adm.pw" 2>&1 | strip | grep -E 'verify-solo:|\[FAIL\]' | cut -c1-240)"
    case "$v" in
      *", 0 failed,"*) leg "U3 the upgraded tree passes verify-solo.sh" "0 failed" 0 "$(printf '%s\n' "$v" | tail -1)" ;;
      *) leg "U3 the upgraded tree passes verify-solo.sh" "0 failed" 1 "$v" ;;
    esac
  fi
  rm -rf "$H".before-upgrade-*
  # F4 uninstall, keeping the data, from the tree's own copy of the script.  LSOLO 39 (owner: "the uninstaller
  # leaves the data in place", and Windows does the same): the account's files and sd.conf STAY WHERE THEY ARE in
  # the install folder and everything else goes, with a .sdcore-kept stamp left beside them.
  echo "kept data" > "$H/user_accounts/sduser/keepme.txt"
  # Change a value the daemon accepts, so a reload can be told from the default.
  sed -i 's/^SORTMEM=.*/SORTMEM=2048/' "$H/sd.conf"
  want_conf="$(cat "$H/sd.conf")"
  dout="$(bash "$H/tools/deletesdsolo.sh" --keep-data --yes 2>&1 | strip)"
  left=0
  [ -e "$HOME/.local/bin/sd" ] || [ -L "$HOME/.local/bin/sd" ] && left=1
  [ -e "$HOME/.local/bin/sd-solo" ] || [ -L "$HOME/.local/bin/sd-solo" ] && left=1
  systemctl --user is-active sd-solo.service >/dev/null 2>&1 && left=1
  ss -ltn 2>/dev/null | grep -q ':14244 ' && left=1
  rest="$(LC_ALL=C ls -A "$H" 2>/dev/null | LC_ALL=C sort | tr '\n' ' ')"
  accs="$(LC_ALL=C ls -A "$H/user_accounts" 2>/dev/null | tr '\n' ' ')"
  if printf '%s\n' "$dout" | grep -qx "SOLO DELETE COMPLETE $H" && [ "$left" -eq 0 ] \
     && [ "$rest" = ".sdcore-kept sd.conf user_accounts " ] && [ "$accs" = "sduser " ] \
     && [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ] \
     && [ "$(cat "$H/sd.conf" 2>/dev/null)" = "$want_conf" ] && grep -q '^commit ' "$H/.sdcore-kept" && grep -q '^kept ' "$H/.sdcore-kept" \
     && printf '%s\n' "$dout" | grep -qx "your configuration is in $H/sd.conf" && [ ! -e "$H/\$cred" ] && [ ! -e "$H/bin" ]; then
    leg "F4 uninstall leaves the data and the configuration in place and nothing else" "'SOLO DELETE COMPLETE', no link/service/port, the folder holds exactly .sdcore-kept, sd.conf (SORTMEM=2048) and user_accounts/sduser (keepme.txt), no \$cred, no bin" 0 "kept in place in $H"
  else
    leg "F4 uninstall leaves the data and the configuration in place and nothing else" "complete; nothing left but .sdcore-kept, sd.conf, user_accounts/sduser" 1 "left=$left rest='$rest' accounts='$accs' conf=$(cat "$H/sd.conf" 2>/dev/null | tr '\n' '|') $(printf '%s\n' "$dout" | tail -2 | tr '\n' ' ')"
  fi

  # F8 (LSOLO 39) A NEW INSTALL OVER THE KEPT DATA.  inst runs the installer unattended into $H, over what F4 left;
  # take_aside turns the safety copy a reload leaves ($H.kept-<time>, which is again exactly what an uninstall
  # leaves) back into $H, so each scenario starts from the same kept tree.
  printf 'New-Pass-9z!\n' > "$W/acc2.pw"; printf 'Admin-Pass-8y!\n' > "$W/adm2.pw"; printf 'Glob-Pass-7x!\n' > "$W/glb2.pw"
  inst() { timeout 900 bash "$INSTALL" --home "$H" --skip-packages --yes --account-password-file "$W/acc2.pw" --admin-password-file "$W/adm2.pw" --api local --ssh off "$@" 2>&1 < /dev/null | strip; }
  take_aside() { local a; a="$(ls -d "$H".kept-* 2>/dev/null | tail -1)"; [ -n "$a" ] || return 1; rm -rf "$H"; mv "$a" "$H"; rm -rf "$H".kept-*; }
  asideof() { ls -d "$H".kept-* 2>/dev/null | tail -1; }
  sdwho() { printf '%s\nWHO\nOFF\n' "$1" | timeout 60 "$H/bin/sd-solo" 2>&1 | strip; }
  # F8: --reload-data: the account's files are back, sd.conf is the kept one, the stage says so, the passwords are
  # the NEW ones (the old account password no longer opens it), the kept folder is still there untouched as a safety
  # copy, the new tree is an ordinary one, and it passes verify-solo.sh.
  out="$(inst --reload-data)"
  ok=1; why=""; aside="$(asideof)"
  printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H" || { ok=0; why="$why not-complete;"; }
  printf '%s\n' "$out" | grep -qF '  reloaded      : your saved data; configuration: reloaded' || { ok=0; why="$why no-reloaded-line;"; }
  [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ] || { ok=0; why="$why data-not-back;"; }
  [ "$(cat "$H/sd.conf" 2>/dev/null)" = "$want_conf" ] || { ok=0; why="$why sdconf-not-the-kept-one;"; }
  [ -n "$aside" ] && [ "$(cat "$aside/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ] && [ "$(cat "$aside/sd.conf")" = "$want_conf" ] && [ -f "$aside/.sdcore-kept" ] || { ok=0; why="$why kept-copy-missing-or-changed;"; }
  [ ! -e "$H/.sdcore-kept" ] && [ -f "$H/.sdcoresolo" ] && grep -qx 'mode unmanaged' "$H/.sdcore-install" || { ok=0; why="$why not-an-ordinary-tree;"; }
  new="$(sdwho "$(head -1 "$W/acc2.pw")")"; old="$(sdwho "$(head -1 "$W/acc.pw")")"
  printf '%s\n' "$new" | grep -qE '^[0-9]+ sduser$' || { ok=0; why="$why new-password-refused;"; }
  ! printf '%s\n' "$old" | grep -qE '^[0-9]+ sduser$' || { ok=0; why="$why OLD-password-works;"; }
  [ "$ok" -eq 1 ] && leg "F8 a new install over the kept data reloads it" "COMPLETE, 'reloaded', keepme.txt and sd.conf (SORTMEM=2048) back, the new password opens it and the old one does not, the kept folder still there as .kept-<time>, an ordinary tree" 0 "reloaded" \
                  || leg "F8 a new install over the kept data reloads it" "COMPLETE, reloaded, data and sd.conf back, new password only, kept copy untouched" 1 "$why $(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|reload' | head -3 | tr '\n' ' ')"
  if [ -f "$here/verify-solo.sh" ]; then
    v="$(timeout 900 bash "$here/verify-solo.sh" "$H" "$W/acc2.pw" "$W/adm2.pw" 2>&1 | strip | grep -E 'verify-solo:|\[FAIL\]' | cut -c1-240)"
    case "$v" in
      *", 0 failed,"*) leg "F8b the reloaded tree passes verify-solo.sh" "0 failed" 0 "$(printf '%s\n' "$v" | tail -1)" ;;
      *) leg "F8b the reloaded tree passes verify-solo.sh" "0 failed" 1 "$v" ;;
    esac
  fi
  bash "$H/tools/deletesdsolo.sh" --delete-data --yes >/dev/null 2>&1; take_aside

  # F8c a kept sd.conf this release refuses: the install still completes, the default sd.conf is used (and that is
  # said), the data is reloaded, and the kept copy is not touched.
  printf 'ZZUNKNOWN=1\n' >> "$H/sd.conf"
  out="$(inst --reload-data)"; aside="$(asideof)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H" && printf '%s\n' "$out" | grep -qF 'configuration: NOT accepted by SD, the default was kept' \
     && [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ] && ! grep -q 'ZZUNKNOWN' "$H/sd.conf" && grep -q '^SORTMEM=4096$' "$H/sd.conf" \
     && [ -n "$aside" ] && grep -q 'ZZUNKNOWN=1' "$aside/sd.conf"; then
    leg "F8c a kept sd.conf SD refuses is not installed" "COMPLETE, 'NOT accepted by SD, the default was kept', data back, sd.conf is the default (SORTMEM=4096), the kept copy untouched" 0 "default kept"
  else
    leg "F8c a kept sd.conf SD refuses is not installed" "COMPLETE, NOT accepted, default kept, data back" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|reload|COMPLETE|not accepted' | head -4 | tr '\n' ' ') conf=$(grep -c ZZUNKNOWN "$H/sd.conf" 2>/dev/null)"
  fi
  bash "$H/tools/deletesdsolo.sh" --delete-data --yes >/dev/null 2>&1; take_aside; sed -i '/^ZZUNKNOWN=/d' "$H/sd.conf"

  # F8d --start-clean: a clean install; the kept data is moved aside, not deleted, and not reloaded.
  out="$(inst --start-clean)"; aside="$(asideof)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H" && printf '%s\n' "$out" | grep -qF "  saved data    : NOT reloaded; it is in $aside" \
     && [ ! -e "$H/user_accounts/sduser/keepme.txt" ] && grep -q '^SORTMEM=4096$' "$H/sd.conf" \
     && [ -n "$aside" ] && [ "$(cat "$aside/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ]; then
    leg "F8d --start-clean installs clean and moves the kept data aside" "COMPLETE, 'saved data : NOT reloaded; it is in <dir>', no keepme.txt in the new account, default sd.conf, the kept data in <dir>" 0 "clean"
  else
    leg "F8d --start-clean installs clean and moves the kept data aside" "COMPLETE, NOT reloaded, kept data aside" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|saved data|COMPLETE' | head -3 | tr '\n' ' ')"
  fi
  bash "$H/tools/deletesdsolo.sh" --delete-data --yes >/dev/null 2>&1; take_aside

  # F8e no answer and no terminal: the kept data is reloaded (it is kept either way), and the installer says so.
  out="$(inst)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H" && printf '%s\n' "$out" | grep -qF 'no terminal and no --reload-data or --start-clean: reloading it' \
     && [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ]; then
    leg "F8e with no answer and no terminal the kept data is reloaded" "COMPLETE, 'no terminal and no --reload-data or --start-clean: reloading it', keepme.txt back" 0 "reloaded"
  else
    leg "F8e with no answer and no terminal the kept data is reloaded" "COMPLETE, said so, keepme.txt back" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|reload|COMPLETE' | head -3 | tr '\n' ' ')"
  fi
  bash "$H/tools/deletesdsolo.sh" --delete-data --yes >/dev/null 2>&1; take_aside

  # F9 a global password can be ADDED to a computer that was installed without one: keep the data, install again
  # GIVING one, reload.  It is managed afterwards (the global record, the stamp), the data and sd.conf are back, and
  # the global password opens it - the supported way from "not managed" to "managed".
  out="$(inst --reload-data --global-password-file "$W/glb2.pw")"
  gw="$(sdwho "$(head -1 "$W/glb2.pw")")"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H" && [ -f "$H/\$cred/\$global" ] && grep -qx 'mode managed' "$H/.sdcore-install" \
     && [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ] && [ "$(cat "$H/sd.conf")" = "$want_conf" ] \
     && printf '%s\n' "$gw" | grep -qE '^[0-9]+ sduser$'; then
    leg "F9 an unmanaged computer becomes managed by reinstalling with a global password and reloading" "COMPLETE, \$cred/\$global, mode managed, keepme.txt and sd.conf back, the global password opens it" 0 "managed, data kept"
  else
    leg "F9 an unmanaged computer becomes managed by reinstalling with a global password and reloading" "COMPLETE, global record, mode managed, data back, global password opens it" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|COMPLETE' | head -3 | tr '\n' ' ') global-record=$([ -f "$H/\$cred/\$global" ] && echo yes || echo NO)"
  fi
  # F10 (agreed with Windows Solo, whose silent uninstall does the same) an uninstall with NO terminal and NEITHER
  # --keep-data nor --delete-data deletes nothing: it keeps the data and sd.conf in place and says so.
  dout="$(bash "$H/tools/deletesdsolo.sh" --yes 2>&1 < /dev/null | strip)"
  rest="$(LC_ALL=C ls -A "$H" 2>/dev/null | LC_ALL=C sort | tr '\n' ' ')"
  if printf '%s\n' "$dout" | grep -qx "SOLO DELETE COMPLETE $H" && printf '%s\n' "$dout" | grep -qF 'keeping your data and configuration' \
     && [ "$rest" = ".sdcore-kept sd.conf user_accounts " ] && [ "$(cat "$H/user_accounts/sduser/keepme.txt" 2>/dev/null)" = "kept data" ]; then
    leg "F10 an uninstall with no terminal and no choice keeps the data" "COMPLETE, 'keeping your data and configuration', the folder holds exactly .sdcore-kept, sd.conf and user_accounts/sduser (keepme.txt)" 0 "kept"
  else
    leg "F10 an uninstall with no terminal and no choice keeps the data" "COMPLETE, keeping, data left in place" 1 "rest='$rest' $(printf '%s\n' "$dout" | grep -E 'REFUSED|FAILED|keeping|COMPLETE' | head -3 | tr '\n' ' ')"
  fi
  rm -rf "$H" "$H".kept-*

  # F5 a MANAGED install (it has a global password) from a control file that has no account
  # password (LSOLO 14): the installer neither asks for one nor sets one, the global password
  # opens the account, the deny list from the file is in place, and there is no $cred/sduser
  # until first login.  LSOLO 38: the file also makes the API and ssh choices - here API local
  # and ssh off, which a managed computer used to be refused (it was forced open).
  H2="$W/inst2"
  cat > "$W/ctl.conf" <<CTL
[install]
admin-password=$(head -1 "$W/adm.pw")
global-password=$(head -1 "$W/glb.pw")
api=local
ssh=off
deny-verbs=DATE
CTL
  out="$(timeout 900 bash "$INSTALL" --home "$H2" --skip-packages --yes --control-file "$W/ctl.conf" 2>&1 < /dev/null | strip)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H2" && printf '%s\n' "$out" | grep -q 'The account password is not asked for' \
     && [ -f "$H2/\$cred/\$global" ] && [ ! -e "$H2/\$cred/sduser" ] && [ "$(sed -n 's/^mode //p' "$H2/.sdcore-install")" = "managed" ]; then
    leg "F5 a control-file install sets no account password" "COMPLETE, 'not asked for', \$cred/\$global and no \$cred/sduser, mode managed" 0 "complete"
  else
    leg "F5 a control-file install sets no account password" "COMPLETE, no \$cred/sduser, mode managed" 1 "$(printf '%s\n' "$out" | tail -5 | tr '\n' ' ')"
  fi
  # F5d a managed computer is no longer forced open: the API is on this computer only, and ssh is off
  # (no ssh socket unit, no tree sshd directory), because that is what the file said.
  uf="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  if grep -qx 'ListenStream=127.0.0.1:14244' "$uf/sd-solo-api.socket" 2>/dev/null && [ ! -e "$uf/sd-solo-ssh.socket" ] && [ ! -e "$H2/sshd/sshd_config" ]; then
    leg "F5d a managed install keeps the API and ssh choices in its file" "API 127.0.0.1:14244 (not 0.0.0.0), no ssh listener" 0 "local, off"
  else
    leg "F5d a managed install keeps the API and ssh choices in its file" "API 127.0.0.1:14244, no ssh socket or sshd directory" 1 "api=$(sed -n 's/^ListenStream=//p' "$uf/sd-solo-api.socket" 2>/dev/null | head -1) ssh-socket=$([ -e "$uf/sd-solo-ssh.socket" ] && echo present || echo absent)"
  fi
  if [ -x "$H2/bin/sd-solo" ]; then
    g="$(printf '%s\nWHO\nOFF\n' "$(head -1 "$W/glb.pw")" | timeout 60 "$H2/bin/sd-solo" 2>&1 | strip)"
    d="$(printf '%s\nDATE\nOFF\n' "$(head -1 "$W/glb.pw")" | timeout 60 "$H2/bin/sd-solo" 2>&1 | strip)"
    if printf '%s\n' "$g" | grep -qE '^[0-9]+ sduser$' && printf '%s\n' "$d" | grep -qE '[0-9]{4} +[0-9]+:[0-9]{2}(am|pm)' \
       && [ "$(grep -cx DATE "$H2/solo.policy/denied.verbs" 2>/dev/null)" -eq 1 ]; then
      leg "F5b the global password opens it; the file's deny list is in place" "WHO answers sduser; solo.policy lists DATE" 0 "as expected"
    else
      leg "F5b the global password opens it; the file's deny list is in place" "WHO answers sduser; DATE on the list" 1 "$(printf '%s\n' "$g" | tail -2 | tr '\n' '|')"
    fi
    dout2="$(bash "$H2/tools/deletesdsolo.sh" --delete-data --yes 2>&1 | strip)"
    if printf '%s\n' "$dout2" | grep -qx "SOLO DELETE COMPLETE $H2" && [ ! -e "$H2" ] && ! systemctl --user is-active sd-solo.service >/dev/null 2>&1; then
      leg "F5c the control-file install is removed" "'SOLO DELETE COMPLETE', no tree, no service" 0 "removed"
    else
      leg "F5c the control-file install is removed" "'SOLO DELETE COMPLETE', no tree, no service" 1 "$(printf '%s\n' "$dout2" | tail -2 | tr '\n' ' ')"
    fi
  fi
  # F7 (LSOLO 38) an install file with a BLANK global password: nothing is asked, it is said out loud that the
  # computer will not be managed, the account password (given as a file, since an install file never carries
  # one and there is no global password to open a first login) is the one that works, there is no $global
  # record and the stamp says unmanaged.  The file's api=local and ssh=off are honoured the same way as in F5.
  H3="$W/inst3"
  cat > "$W/ctl-blank.conf" <<CTL
[install]
admin-password=$(head -1 "$W/adm.pw")
global-password=
api=local
ssh=off
CTL
  out="$(timeout 900 bash "$INSTALL" --home "$H3" --skip-packages --yes --control-file "$W/ctl-blank.conf" --account-password-file "$W/acc.pw" 2>&1 < /dev/null | strip)"
  if printf '%s\n' "$out" | grep -qx "SOLO INSTALL COMPLETE $H3" \
     && printf '%s\n' "$out" | grep -qF 'The control file gives no global password, so this computer will NOT be managed by an SD Core server.' \
     && printf '%s\n' "$out" | grep -qF 'global pw     : none - no SD Core server manages this computer' \
     && [ ! -e "$H3/\$cred/\$global" ] && [ -e "$H3/\$cred/sduser" ] && [ "$(sed -n 's/^mode //p' "$H3/.sdcore-install")" = "unmanaged" ]; then
    leg "F7 an install file with a blank global password" "COMPLETE, said NOT managed, no \$cred/\$global, \$cred/sduser set, mode unmanaged" 0 "unmanaged"
  else
    leg "F7 an install file with a blank global password" "COMPLETE, 'will NOT be managed', no \$cred/\$global, mode unmanaged" 1 "$(printf '%s\n' "$out" | grep -E 'REFUSED|FAILED|NOT be managed|COMPLETE' | head -3 | tr '\n' ' ')"
  fi
  if [ -x "$H3/bin/sd-solo" ]; then
    g="$(printf '%s\nWHO\nOFF\n' "$(head -1 "$W/acc.pw")" | timeout 60 "$H3/bin/sd-solo" 2>&1 | strip)"
    if printf '%s\n' "$g" | grep -qE '^[0-9]+ sduser$'; then
      leg "F7b the account password opens it" "WHO answers sduser" 0 "as expected"
    else
      leg "F7b the account password opens it" "WHO answers sduser" 1 "$(printf '%s\n' "$g" | tail -2 | tr '\n' '|')"
    fi
    dout3="$(bash "$H3/tools/deletesdsolo.sh" --delete-data --yes 2>&1 | strip)"
    if printf '%s\n' "$dout3" | grep -qx "SOLO DELETE COMPLETE $H3" && [ ! -e "$H3" ] && ! systemctl --user is-active sd-solo.service >/dev/null 2>&1; then
      leg "F7c the install is removed" "'SOLO DELETE COMPLETE', no tree, no service" 0 "removed"
    else
      leg "F7c the install is removed" "'SOLO DELETE COMPLETE', no tree, no service" 1 "$(printf '%s\n' "$dout3" | tail -2 | tr '\n' ' ')"
    fi
  fi
  # the shipped sample, untouched, gives no answers: nothing in it may be taken as one
  o="$(timeout 60 bash "$INSTALL" --home "$W/h9" --skip-packages --yes --control-file "$here/sd-solo-setup.conf.sample" </dev/null 2>&1 | strip)"
  # LSOLO 38: with no global password in the sample the account password is asked first (the first-login
  # route is for a computer that has one), so that is the question an unattended run cannot answer.
  if printf '%s\n' "$o" | grep -q '^REFUSED: .*no account password was given' && [ ! -e "$W/h9" ]; then
    leg "F6 the shipped sample answers nothing" "REFUSED ... no account password was given (its commented samples are not answers)" 0 "refused"
  else
    leg "F6 the shipped sample answers nothing" "REFUSED ... no account password was given" 1 "$(printf '%s\n' "$o" | grep -E 'REFUSED|COMPLETE' | head -2 | tr '\n' ' ')"
  fi
fi

echo
echo "verify-solo-install: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
