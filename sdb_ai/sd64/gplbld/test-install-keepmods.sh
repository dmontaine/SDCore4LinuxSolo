#!/bin/bash
# test-install-keepmods.sh - the keep cycle of newvoc.mods in SD Core for Linux Solo (PAL-36, the owner's "build the keep cycle", 24 Oct 2026).
# newvoc.mods is the administrator's directory of site-local VOC additions (QM4 gap 501) in the install folder.  "deletesdsolo.sh --keep-data"
# used to remove it with the rest of the installation; now it stays beside the account and sd.conf, the installer accepts it as part of a kept
# folder, and solo-stage.sh puts it back before the VOC is refreshed.  No install, no sudo, no sd.  Exit 0 every row held, 1 one did not, 2 it
# could not run.
#
#   bash /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-install-keepmods.sh [--selftest]
#
# WHAT IT RUNS.  keep_prune (deletesdsolo.sh, cut out between "# BEGIN keep_prune" and "# END keep_prune") under the remover's own
# `set -uo pipefail`, and is_kept_tree (installsdsolo.sh, between "# BEGIN is_kept_tree" and "# END is_kept_tree") under the installer's own
# `set -euo pipefail` (a block tested without the script's options once stopped two real installs), each on scratch folders, with the disk as the
# evidence (a before listing and an after listing are printed for the removal).  solo-stage.sh's reload branch is read as TEXT: it is only
# reached by a whole install over a kept folder, which is verify-solo-install.sh's F8 and needs a real Solo.  ***IT DOES NOT RUN THE REMOVER
# OR THE INSTALLER OR THE STAGE***, so it cannot say the cycle works end to end; that is a real-install row, NOT run for this change.
#
# --selftest breaks the three files in the ways listed at the end and requires the rows to notice each one.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
INSTALLER="${INSTALLER:-$ROOT/installsdsolo.sh}"
REMOVER="${REMOVER:-$ROOT/deletesdsolo.sh}"
STAGE="${STAGE:-$HERE/solo-stage.sh}"

passed=0; failed=0
row() {   # row "name" ok(0|1) ["detail"]
  if [ "$2" = 0 ]; then passed=$((passed+1)); echo "  [PASS] $1"
  else failed=$((failed+1)); echo "  [FAIL] $1${3:+   <- $3}"; fi
}

top() { ( cd "$1" && ls -A | LC_ALL=C sort | tr '\n' ' ' ); }

# a folder as "deletesdsolo.sh --keep-data" finds it before it removes anything: the installation, the account, sd.conf
mk_install() {   # mk_install DIR
  local d="$1"
  mkdir -p "$d/bin" "$d/tools" "$d/\$cred" "$d/user_accounts/sduser/voc"
  echo exe > "$d/bin/sd-solo"; echo x > "$d/tools/solo-service.sh"; echo pw > "$d/\$cred/sduser"
  echo rec > "$d/user_accounts/sduser/voc/%0"; echo "SORTMEM=1" > "$d/sd.conf"
  : > "$d/.sdcoresolo"; echo "commit abc" > "$d/.sdcore-install"
}

check() {   # check REMOVER INSTALLER STAGE - every row against these three files
  local rem="$1" inst="$2" stage="$3" T blk out rc d before after
  T="$(mktemp -d)"

  # ---- P. keep_prune ------------------------------------------------------------------------------------------------
  blk="$T/keep_prune.sh"
  sed -n '/^# BEGIN keep_prune$/,/^# END keep_prune$/p' "$rem" > "$blk"
  if [ "$(wc -l < "$blk")" -lt 8 ]; then
    row "the remover holds a '# BEGIN keep_prune' ... '# END keep_prune' block" 1 "found $(wc -l < "$blk") lines"
    rm -rf "$T"; return
  fi
  row "the remover holds a '# BEGIN keep_prune' ... '# END keep_prune' block" 0
  run_prune() {   # run_prune DIR -> status
    ( set -uo pipefail; . "$blk"; keep_prune "$1" ); echo $?
  }

  d="$T/p1"; mk_install "$d"; mkdir -p "$d/newvoc.mods/sub"; echo "SDVOC" > "$d/newvoc.mods/sub/rec"; echo top > "$d/newvoc.mods/toprec"
  before="$(top "$d")"; rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P1 a REAL newvoc.mods directory stays, with what is in it, beside the account, sd.conf and \$cred (S.234 N9); the installation and the markers go (status 0)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred newvoc.mods sd.conf user_accounts " ] && [ "$(cat "$d/newvoc.mods/sub/rec" 2>/dev/null)" = SDVOC ] && [ "$(cat "$d/newvoc.mods/toprec" 2>/dev/null)" = top ] && [ -f "$d/user_accounts/sduser/voc/%0" ] && echo 0 || echo 1)" \
    "rc=$rc before='$before' after='$after'"

  d="$T/p2"; mk_install "$d"
  before="$(top "$d")"; rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P2 NULL CASE: with no newvoc.mods the empty array is harmless under set -u and the folder holds exactly the account and sd.conf (status 0)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred sd.conf user_accounts " ] && echo 0 || echo 1)" "rc=$rc before='$before' after='$after'"

  d="$T/p3"; mk_install "$d"; mkdir -p "$T/elsewhere"; echo precious > "$T/elsewhere/rec"; ln -s "$T/elsewhere" "$d/newvoc.mods"
  before="$(top "$d")"; rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P3 a newvoc.mods that is a LINK to a directory is not kept (the link goes; the directory it pointed to is untouched)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred sd.conf user_accounts " ] && [ "$(cat "$T/elsewhere/rec" 2>/dev/null)" = precious ] && echo 0 || echo 1)" "rc=$rc before='$before' after='$after'"

  d="$T/p4"; mk_install "$d"; echo "not a directory" > "$d/newvoc.mods"
  before="$(top "$d")"; rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P4 a newvoc.mods that is a plain FILE is not kept" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred sd.conf user_accounts " ] && echo 0 || echo 1)" "rc=$rc before='$before' after='$after'"

  # 14 Nov 26 (S.234 N9, owner: "N9 same as core"): what SD Core's keep cycle keeps stays - real directories $cred sd-tls sshd ai netlogins, regular files
  # audit, audit.<date>, start.default - and the same names as LINKS go (their targets untouched), as does a directory called audit.
  d="$T/p6"; mk_install "$d"; mkdir -p "$d/sd-tls" "$d/sshd" "$d/ai/keys" "$d/netlogins/srv"; echo pem > "$d/sd-tls/api.pem"; echo hk > "$d/sshd/ssh_host_ed25519_key"
  echo k > "$d/ai/keys/anthropic"; echo n > "$d/netlogins/srv/rec"; echo line1 > "$d/audit"; echo old > "$d/audit.20261101-000000"; echo menu > "$d/start.default"
  rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P6 the keep cycle's set stays, with its contents: \$cred, ai, audit and its rotated copy, netlogins, sd-tls, sshd, start.default (status 0)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred ai audit audit.20261101-000000 netlogins sd-tls sd.conf sshd start.default user_accounts " ] && [ "$(cat "$d/sd-tls/api.pem")" = pem ] && [ "$(cat "$d/ai/keys/anthropic")" = k ] && [ "$(cat "$d/sshd/ssh_host_ed25519_key")" = hk ] && echo 0 || echo 1)" "rc=$rc after='$after'"
  d="$T/p7"; mk_install "$d"; mkdir -p "$T/else7"; echo keep7 > "$T/else7/rec"; ln -s "$T/else7" "$d/sd-tls"; ln -s "$T/else7/rec" "$d/start.default"; mkdir "$d/audit"
  rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P7 a LINK named sd-tls or start.default, and a DIRECTORY named audit, go; the link's target is untouched" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred sd.conf user_accounts " ] && [ "$(cat "$T/else7/rec" 2>/dev/null)" = keep7 ] && echo 0 || echo 1)" "rc=$rc after='$after'"

  d="$T/p5"; mk_install "$d"; mkdir "$d/newvoc.mods"; echo sentinel > "$T/outside-sentinel"
  rc="$(run_prune "$d")"
  # 20 Nov 26 (S.278): the account register stays, as a real directory, with what is in it; a link of that name goes.
  d="$T/p8"; mk_install "$d"; mkdir -p "$d/accounts"; printf 'x\n' > "$d/accounts/sduser"
  rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P8 a REAL accounts directory (the register) stays with its record (status 0)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred accounts sd.conf user_accounts " ] && [ "$(cat "$d/accounts/sduser" 2>/dev/null)" = x ] && echo 0 || echo 1)" "rc=$rc after='$after'"
  d="$T/p9"; mk_install "$d"; mkdir -p "$T/else9"; echo keep9 > "$T/else9/sduser"; ln -s "$T/else9" "$d/accounts"
  rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P9 an accounts that is a LINK goes; its target is untouched" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred sd.conf user_accounts " ] && [ "$(cat "$T/else9/sduser" 2>/dev/null)" = keep9 ] && echo 0 || echo 1)" "rc=$rc after='$after'"

  # 22 Nov 26 (S.287): the PDF reader allow-list, pdf/ and solo.policy stay with the data.
  d="$T/p10"; mk_install "$d"; mkdir -p "$d/pdf" "$d/solo.policy"; echo "a.pdf" > "$d/pdf/a.pdf"; echo "deny" > "$d/solo.policy/x"; echo "pdf /usr/bin/evince" > "$d/viewers"
  rc="$(run_prune "$d")"; after="$(top "$d")"
  row "P10 viewers (a file), pdf and solo.policy (directories) stay with what is in them (S.287)" \
    "$([ "$rc" = 0 ] && [ "$after" = "\$cred pdf sd.conf solo.policy user_accounts viewers " ] && [ "$(cat "$d/pdf/a.pdf")" = a.pdf ] && [ "$(cat "$d/solo.policy/x")" = deny ] && echo 0 || echo 1)" "rc=$rc after='$after'"
  row "P5 nothing outside the folder is touched" "$([ "$rc" = 0 ] && [ "$(cat "$T/outside-sentinel" 2>/dev/null)" = sentinel ] && [ -d "$T/elsewhere" ] && echo 0 || echo 1)" "rc=$rc"

  # ---- I. is_kept_tree ----------------------------------------------------------------------------------------------
  blk="$T/is_kept_tree.sh"
  sed -n '/^# BEGIN is_kept_tree$/,/^# END is_kept_tree$/p' "$inst" > "$blk"
  if [ "$(wc -l < "$blk")" -lt 8 ]; then
    row "the installer holds a '# BEGIN is_kept_tree' ... '# END is_kept_tree' block" 1 "found $(wc -l < "$blk") lines"
    rm -rf "$T"; return
  fi
  row "the installer holds a '# BEGIN is_kept_tree' ... '# END is_kept_tree' block" 0
  kept() {   # kept DIR -> YES or NO
    ( set -euo pipefail; . "$blk"; if is_kept_tree "$1"; then echo YES; else echo NO; fi )
  }
  mk_kept() {   # mk_kept DIR: what the remover leaves
    local k="$1"
    mkdir -p "$k/user_accounts/sduser/voc"; echo rec > "$k/user_accounts/sduser/voc/%0"; echo "SORTMEM=1" > "$k/sd.conf"
    printf 'commit abc\nkept 2026-10-24T00:00:00-07:00\n' > "$k/.sdcore-kept"
  }
  d="$T/k1"; mk_kept "$d"
  out="$(kept "$d")"; row "I1 CONTROL: a folder holding the stamp, the account and sd.conf is a kept tree" "$([ "$out" = YES ] && echo 0 || echo 1)" "got $out"
  d="$T/k2"; mk_kept "$d"; mkdir -p "$d/newvoc.mods/a/b"; echo r > "$d/newvoc.mods/a/b/rec"
  out="$(kept "$d")"; row "I2 ...and so is one that also holds a REAL newvoc.mods directory, whatever is in it" "$([ "$out" = YES ] && echo 0 || echo 1)" "got $out"
  d="$T/k3"; mk_kept "$d"; ln -s "$T/elsewhere" "$d/newvoc.mods"
  out="$(kept "$d")"; row "I3 a newvoc.mods that is a LINK makes it a stranger's folder (the installer would refuse it)" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k4"; mk_kept "$d"; echo f > "$d/newvoc.mods"
  out="$(kept "$d")"; row "I4 a newvoc.mods that is a plain FILE does too" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k5"; mk_kept "$d"; mkdir "$d/bin"
  out="$(kept "$d")"; row "I5 any other extra entry still does (bin/): the allowance is for newvoc.mods only" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k6"; mk_kept "$d"; : > "$d/.sdcoresolo"
  out="$(kept "$d")"; row "I6 a folder that still has the installation's marker is not a kept tree" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k7"; mk_kept "$d"; rm "$d/.sdcore-kept"
  out="$(kept "$d")"; row "I7 without the stamp it is not a kept tree" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k8"; mk_kept "$d"; mkdir "$d/user_accounts/other"
  out="$(kept "$d")"; row "I8 a second account folder is not allowed" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  # 14 Nov 26 (S.234 N9): the keep cycle's set is part of a kept tree; a link in its place is a stranger's, as for newvoc.mods.
  d="$T/k9"; mk_kept "$d"; mkdir "$d/\$cred" "$d/sd-tls" "$d/sshd" "$d/ai" "$d/netlogins"; echo a > "$d/audit"; echo b > "$d/audit.20261101-000000"; echo menu > "$d/start.default"
  out="$(kept "$d")"; row "I10 a folder that also holds \$cred, sd-tls, sshd, ai, netlogins, audit, audit.<date> and start.default is a kept tree" "$([ "$out" = YES ] && echo 0 || echo 1)" "got $out"
  d="$T/k10"; mk_kept "$d"; ln -s "$T/elsewhere" "$d/\$cred"
  out="$(kept "$d")"; row "I11 a \$cred that is a LINK makes it a stranger's folder" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k11"; mk_kept "$d"; mkdir -p "$d/accounts"; echo r > "$d/accounts/sduser"
  out="$(kept "$d")"; row "I12 a folder that also holds a REAL accounts directory (the register) is a kept tree" "$([ "$out" = YES ] && echo 0 || echo 1)" "got $out"
  d="$T/k12"; mk_kept "$d"; ln -s "$T/elsewhere" "$d/accounts"
  out="$(kept "$d")"; row "I13 an accounts that is a LINK makes it a stranger's folder" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  d="$T/k13"; mk_kept "$d"; mkdir -p "$d/pdf" "$d/solo.policy"; echo "pdf /usr/bin/evince" > "$d/viewers"
  out="$(kept "$d")"; row "I14 a folder that also holds viewers, pdf and solo.policy is a kept tree (S.287)" "$([ "$out" = YES ] && echo 0 || echo 1)" "got $out"
  d="$T/k14"; mk_kept "$d"; ln -s "$T/elsewhere" "$d/pdf"
  out="$(kept "$d")"; row "I15 a pdf that is a LINK makes it a stranger's folder" "$([ "$out" = NO ] && echo 0 || echo 1)" "got $out"
  row "I9 the allowance asks the owner as well as the type (somebody else's directory named newvoc.mods is a stranger's)" \
    "$(awk '/^# BEGIN is_kept_tree$/,/^# END is_kept_tree$/' "$inst" | grep -qF 'newvoc.mods|voc_removed.saved) { [ -d "$e" ] && [ ! -L "$e" ] && [ "$(stat -c %u "$e")" = "$(id -u)" ]; } || return 1 ;;' && echo 0 || echo 1)"

  # ---- T. where they are used (text) ---------------------------------------------------------------------------------
  local keep_call stamp_mv
  keep_call="$(grep -n 'keep_prune "\$H" ||' "$rem" | head -1 | cut -d: -f1)"
  stamp_mv="$(grep -n 'mv "\$stamp" "\$H/.sdcore-kept"' "$rem" | head -1 | cut -d: -f1)"
  row "T1 the remover's keep branch calls keep_prune on the install folder BEFORE it writes the stamp, and no inline find over the install folder is left" \
    "$([ -n "$keep_call" ] && [ -n "$stamp_mv" ] && [ "$keep_call" -lt "$stamp_mv" ] && ! grep -q 'find "\$H" -mindepth 1 -maxdepth 1' "$rem" && echo 0 || echo 1)" "call line '$keep_call', stamp line '$stamp_mv'"
  row "T2 the remover says where the modifications are when it kept them" "$(grep -qF 'your local VOC modifications are in $H/newvoc.mods' "$rem" && echo 0 || echo 1)"
  row "T3 the installer says what it found in its reload offer, and refuses a folder that is neither an install nor a kept tree with newvoc.mods in its list" \
    "$(grep -qF 'and your local VOC modifications (newvoc.mods)' "$inst" && grep -qF 'sd.conf and a newvoc.mods directory, and nothing else' "$inst" && echo 0 || echo 1)"
  row "T4 the installer FAILS when the kept folder has a newvoc.mods and the stage did not say it put it back (the administrator's additions would be gone without a word)" \
    "$(grep -qF "mods_note=\"\$(sed -e 's/\\x1b\\[[0-9;?]*[A-Za-z]//g' -e 's/\\r//g' \"\$WORK/stage.log\" | sed -n 's/^solo-stage: newvoc.mods: //p' | tail -1)\"" "$inst" \
       && grep -qF 'if [ -d "$reload_dir/newvoc.mods" ]; then' "$inst" && grep -qF '[ "$mods_note" = "reloaded" ] || fail' "$inst" && echo 0 || echo 1)"

  local r_acc r_mods r_ua
  r_acc="$(grep -n 'cp -a "\$reloaddir/user_accounts/sduser"' "$stage" | head -1 | cut -d: -f1)"
  r_mods="$(grep -n 'cp -a "\$reloaddir/newvoc.mods"' "$stage" | head -1 | cut -d: -f1)"
  r_ua="$(grep -n 'ua_out="\$(sdi UPDATE.ACCOUNTS ALL' "$stage" | cut -d: -f1 | awk -v a="${r_acc:-0}" '$1 > a { print; exit }')"      # the refresh AFTER the account copy: the upgrade branch has an earlier one
  row "S1 solo-stage.sh's reload copies newvoc.mods AFTER the account and BEFORE UPDATE.ACCOUNTS ALL (which applies it)" \
    "$([ -n "$r_acc" ] && [ -n "$r_mods" ] && [ -n "$r_ua" ] && [ "$r_acc" -lt "$r_mods" ] && [ "$r_mods" -lt "$r_ua" ] && echo 0 || echo 1)" "account line '$r_acc', mods line '$r_mods', update line '$r_ua'"
  row "S2 ...only a real directory (not a link) of the kept folder is taken, the new tree's own is replaced whole, and the copy is made private" \
    "$(grep -qF 'if [ -d "$reloaddir/newvoc.mods" ] && [ ! -L "$reloaddir/newvoc.mods" ]; then' "$stage" && grep -qF 'rm -rf "$H/newvoc.mods"' "$stage" && grep -qF 'chmod -R go-rwx "$H/newvoc.mods"' "$stage" && echo 0 || echo 1)"
  row "S3 ...and it says so on a line of its own, 'solo-stage: newvoc.mods: reloaded', or 'none was saved'; the DONE line the installer parses is as it was" \
    "$(grep -qF 'echo "solo-stage: newvoc.mods: $reload_mods"' "$stage" && grep -qF 'reload_mods="none was saved"' "$stage" && grep -qF 'reload_mods="reloaded"' "$stage" && grep -qF 'echo "SOLO RELOAD DONE data=reloaded config=$reload_conf"' "$stage" && echo 0 || echo 1)"

  # ---- R. carry_register (S.278): the kept record's administrator switches, read back into the new record, only ever to yes ----------------------------------
  blk="$T/carry_register.sh"
  sed -n '/^  # REGISTER-CARRY-BEGIN$/,/^  # REGISTER-CARRY-END$/p' "$stage" > "$blk"
  if [ "$(wc -l < "$blk")" -lt 8 ]; then
    row "the stage holds a '# REGISTER-CARRY-BEGIN' ... '# REGISTER-CARRY-END' block" 1 "found $(wc -l < "$blk") lines"
    rm -rf "$T"; return
  fi
  row "the stage holds a '# REGISTER-CARRY-BEGIN' ... '# REGISTER-CARRY-END' block" 0
  carry() {   # carry KEPT NEW -> prints the function's line; the new file is left changed
    ( set -euo pipefail; . "$blk"; carry_register "$1" "$2" )
  }
  mkrec() {   # mkrec FILE trailing(1|0) f1 f2 ... : one field per line; an unset field is passed as ''
    local f="$1" t="$2" i; shift 2; : > "$f"
    for i in "$@"; do printf '%s\n' "$i" >> "$f"; done
    [ "$t" = 1 ] || truncate -s -1 "$f"
  }
  fld() { sed -n "${2}p" "$1"; }   # fld FILE N
  # 24 fields: path descr group (4) suspended (5) prior (6) sh os sdacc voc bp dict shr.read shr.write net start tiles pins rec mcp mcpw xfer jobs stored
  local kf nf msg
  kf="$T/kept.rec"; nf="$T/new.rec"
  mkrec "$kf" 1 /h/k "kept descr" grp "" "" "" yes yes no yes yes no "" "" yes menu "t1 t2" yes yes no yes yes yes yes
  mkrec "$nf" 1 /h/n "new descr" grp2 "" "" "" no no no no no no "" "" no "" "" no no no no no no no
  msg="$(carry "$kf" "$nf" 2>&1)"
  row "R1 each switch the kept record had on is on in the new one (7, 8, 10, 11, 15, 18, 19, 21-24) and the line counts them and the tiles: 12" \
    "$([ "$(fld "$nf" 7)$(fld "$nf" 8)$(fld "$nf" 10)$(fld "$nf" 11)$(fld "$nf" 15)$(fld "$nf" 18)$(fld "$nf" 19)$(fld "$nf" 21)$(fld "$nf" 22)$(fld "$nf" 23)$(fld "$nf" 24)" = yesyesyesyesyesyesyesyesyesyesyes ] && [ "$(fld "$nf" 9)" = no ] && [ "$(fld "$nf" 12)" = no ] && [ "$(fld "$nf" 20)" = no ] && [ "$msg" = "solo-stage: register: 12 switch(es) carried from the kept record" ] && echo 0 || echo 1)" "msg='$msg' fields=$(tr '\n' '|' < "$nf")"
  row "R2 what the new record owns is left: the path, description, group (1-3), the suspension, the start word and the shared account's two (13, 14, 16)" \
    "$([ "$(fld "$nf" 1)" = /h/n ] && [ "$(fld "$nf" 2)" = "new descr" ] && [ "$(fld "$nf" 3)" = grp2 ] && [ -z "$(fld "$nf" 5)" ] && [ -z "$(fld "$nf" 13)" ] && [ -z "$(fld "$nf" 14)" ] && [ -z "$(fld "$nf" 16)" ] && echo 0 || echo 1)"
  row "R3 the tiles that are off (17) are taken when the new record's is blank" "$([ "$(fld "$nf" 17)" = "t1 t2" ] && echo 0 || echo 1)" "got '$(fld "$nf" 17)'"
  mkrec "$kf" 1 /h/k d g "" "" "" no no no no no no "" "" no "" "" no no no no no no no
  mkrec "$nf" 1 /h/n d g "" "" "" yes no no no no no "" "" no "" "" no no no yes no no no
  cp "$nf" "$T/new.before"; msg="$(carry "$kf" "$nf" 2>&1)"
  row "R4 NOTHING IS TURNED OFF and nothing is opened that was not: a kept record with every switch off leaves a new one with two on exactly as it was (0 carried)" \
    "$(cmp -s "$nf" "$T/new.before" && [ "$msg" = "solo-stage: register: 0 switch(es) carried from the kept record" ] && echo 0 || echo 1)" "msg='$msg'"
  mkrec "$kf" 1 /h/k d g "" "" "" "" "" "" "" "" "" "" ""
  mkrec "$nf" 1 /h/n d g "" "" no no no no no no "" "" no "" "" no no no no no no no
  cp "$nf" "$T/new.before"; msg="$(carry "$kf" "$nf" 2>&1)"
  row "R5 a SHORT kept record (nothing past field 15) and a blank field are 'off': nothing is carried, the new record is unchanged" \
    "$(cmp -s "$nf" "$T/new.before" && echo 0 || echo 1)" "msg='$msg'"
  mkrec "$kf" 1 /h/k d g "" "" "" YES "" "" "" "" "" "" "" "" "" "" "" "" "" "" "" "Yes"
  mkrec "$nf" 0 /h/n d g
  msg="$(carry "$kf" "$nf" 2>&1)"
  row "R6 'YES' and 'Yes' count (the register is read case blind); a SHORT new record is extended to the field, and a record with no trailing newline is written with none" \
    "$([ "$(fld "$nf" 7)" = yes ] && [ "$(fld "$nf" 23)" = yes ] && [ "$(tail -c1 "$nf" | od -An -c | tr -d ' ')" != '\n' ] && echo 0 || echo 1)" "msg='$msg' tail=$(tail -c1 "$nf" | od -An -c)"
  rm -f "$T/nokept.rec"; mkrec "$nf" 1 /h/n d g "" "" no; cp "$nf" "$T/new.before"; msg="$(carry "$T/nokept.rec" "$nf" 2>&1)"
  row "R7 NULL CASE: no kept record says 'none was saved' and the new one is untouched" "$(cmp -s "$nf" "$T/new.before" && [ "$msg" = "solo-stage: register: none was saved" ] && echo 0 || echo 1)" "msg='$msg'"
  mkrec "$kf" 1 /h/k d g "" "" "" yes; ln -s "$kf" "$T/kept.link"; cp "$nf" "$T/new.before"; msg="$(carry "$T/kept.link" "$nf" 2>&1)"
  row "R8 a kept record that is a LINK is not read" "$(cmp -s "$nf" "$T/new.before" && [ "$msg" = "solo-stage: register: none was saved" ] && echo 0 || echo 1)" "msg='$msg'"
  rm -f "$T/nonew.rec"; msg="$(carry "$kf" "$T/nonew.rec" 2>&1)"
  row "R9 a new install with no register record is said, not guessed (the switches stay as delivered) and nothing is created" "$([ ! -e "$T/nonew.rec" ] && printf '%s' "$msg" | grep -q 'NOT carried' && echo 0 || echo 1)" "msg='$msg'"
  local c_rel c_end c_up
  c_rel="$(grep -n '^  # RELOAD-KEPT-END$' "$stage" | head -1 | cut -d: -f1)"
  c_end="$(grep -n 'carry_register "\$reloaddir/accounts/sduser" "\$H/accounts/sduser"' "$stage" | head -1 | cut -d: -f1)"
  c_up="$(grep -n 'ua_out="\$(sdi UPDATE.ACCOUNTS ALL' "$stage" | cut -d: -f1 | awk -v a="${c_rel:-0}" '$1 > a { print; exit }')"
  row "R10 the stage calls it on the kept and the new record AFTER the kept set is copied and BEFORE the VOC refresh and the account's start" \
    "$([ -n "$c_rel" ] && [ -n "$c_end" ] && [ -n "$c_up" ] && [ "$c_rel" -lt "$c_end" ] && [ "$c_end" -lt "$c_up" ] && echo 0 || echo 1)" "kept-set end '$c_rel', call '$c_end', refresh '$c_up'"
  row "R11 the generic copy loop does NOT take accounts (it would replace the new record whole)" \
    "$(grep -q "for kept_item in '\$cred' '\$jobs' sd-tls sshd ai netlogins; do" "$stage" && echo 0 || echo 1)"
  rm -rf "$T"
}

selftest() {
  local tmp name target expr file ok=0 n=0 out p0 f0 orig
  tmp="$(mktemp -d)"
  # name | which file (r remover, i installer, s stage) | sed expression that breaks it
  while IFS='|' read -r name target expr; do
    [ -n "$name" ] || continue
    n=$((n+1))
    cp "$REMOVER" "$tmp/deletesdsolo.sh"; cp "$INSTALLER" "$tmp/installsdsolo.sh"; cp "$STAGE" "$tmp/solo-stage.sh"
    case "$target" in r) file="$tmp/deletesdsolo.sh"; orig="$REMOVER" ;; i) file="$tmp/installsdsolo.sh"; orig="$INSTALLER" ;; s) file="$tmp/solo-stage.sh"; orig="$STAGE" ;; esac
    sed -i -e "$expr" "$file"
    if cmp -s "$file" "$orig"; then echo "  [FAIL] selftest: $name  <- the mutation changed nothing"; failed=$((failed+1)); continue; fi
    p0=$passed; f0=$failed
    out="$(check "$tmp/deletesdsolo.sh" "$tmp/installsdsolo.sh" "$tmp/solo-stage.sh" 2>&1 || true)"
    passed=$p0; failed=$f0
    if printf '%s\n' "$out" | grep -q '\[FAIL\]'; then
      echo "  [PASS] selftest: $name is caught ($(printf '%s\n' "$out" | grep -c '\[FAIL\]') row(s) failed: $(printf '%s\n' "$out" | grep '\[FAIL\]' | sed -e 's/.*\[FAIL\] \([A-Z][0-9]*\) .*/\1/' | tr '\n' ' '))"; passed=$((passed+1)); ok=$((ok+1))
    else
      echo "  [FAIL] selftest: $name is NOT caught"; failed=$((failed+1))
    fi
  done <<'EOF'
keep_prune never keeps anything|r|s/then keep+=(! -name "\$n"); fi/then true; fi/
keep_prune keeps a link too|r|s/    if \[ -d "\$d\/\$n" \] \&\& \[ ! -L "\$d\/\$n" \]; then keep+=/    if [ -e "$d\/$n" ]; then keep+=/
keep_prune keeps a plain file too|r|s/    if \[ -d "\$d\/\$n" \] \&\& \[ ! -L "\$d\/\$n" \]; then keep+=/    if [ -e "$d\/$n" ] \&\& [ ! -L "$d\/$n" ]; then keep+=/
keep_prune keeps the wrong name|r|s/for n in newvoc.mods voc_removed.saved/for n in newvoc.mod voc_removed.saved/
the remover goes back to the inline find|r|s/keep_prune "\$H" ||/find "$H" -mindepth 1 -maxdepth 1 ! -name user_accounts ! -name sd.conf -exec rm -rf {} + ||/
the remover stays silent about what it kept|r|s/your local VOC modifications are in/your files are in/
is_kept_tree has no line for newvoc.mods|i|/^      newvoc.mods|voc_removed.saved) /d
is_kept_tree accepts a link|i|s/{ \[ -d "\$e" \] \&\& \[ ! -L "\$e" \] \&\& /{ [ -d "$e" ] \&\& /
is_kept_tree accepts a stranger's directory|i|s/ \&\& \[ "\$(stat -c %u "\$e")" = "\$(id -u)" \]; } || return 1 ;;/; } || return 1 ;;/
is_kept_tree accepts anything|i|s/^      \*) return 1 ;;$/      *) ;;/
the installer no longer checks the stage put newvoc.mods back|i|s/\[ "\$mods_note" = "reloaded" \] || fail/true || fail/
the installer does not read the stage's newvoc.mods line|i|s/s\/\^solo-stage: newvoc.mods: \/\/p/s\/^solo-stage: nothing: \/\/p/
the stage no longer copies newvoc.mods|s|/cp -a "\$reloaddir\/newvoc.mods"/d
the stage takes a link as well|s|s/ \&\& \[ ! -L "\$reloaddir\/newvoc.mods" \]; then/; then/
the stage keeps the new tree's own newvoc.mods under the copy|s|/rm -rf "\$H\/newvoc.mods"/d
the stage says nothing about it|s|/echo "solo-stage: newvoc.mods: \$reload_mods"/d
keep_prune drops the register|r|s/'\$jobs' accounts sd-tls/'\$jobs' sd-tls/
is_kept_tree refuses the register|i|s/|accounts|sd-tls|/|sd-tls|/
carry_register turns switches OFF|s|s/if (tolower(k\[j\]) == "yes" \&\& tolower(f\[j\]) != "yes") { f\[j\] = "yes"/if (tolower(k[j]) != tolower(f[j])) { f[j] = k[j]/
the generic reload loop takes the register whole|s|s/for kept_item in '\$cred' '\$jobs' sd-tls/for kept_item in '\$cred' '\$jobs' accounts sd-tls/
the stage never calls carry_register|s|/^  carry_register "\$reloaddir/d
EOF
  rm -rf "$tmp"
  echo "selftest: $ok of $n mutants caught"
  [ "$ok" -eq "$n" ]
}

for f in "$REMOVER" "$INSTALLER" "$STAGE"; do
  [ -f "$f" ] || { echo "test-install-keepmods: CANNOT RUN - $f is not there"; exit 2; }
done
echo "test-install-keepmods: remover   $REMOVER"
echo "test-install-keepmods: installer $INSTALLER"
echo "test-install-keepmods: stage     $STAGE"
check "$REMOVER" "$INSTALLER" "$STAGE"
st=0
if [ "${1:-}" = "--selftest" ]; then selftest || st=1; fi
echo
echo "test-install-keepmods: $passed passed, $failed failed"
[ "$failed" -eq 0 ] && [ "$passed" -gt 0 ] && [ "$st" -eq 0 ]
