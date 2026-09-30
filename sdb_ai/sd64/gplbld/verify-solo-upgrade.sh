#!/bin/bash
# verify-solo-upgrade.sh - does "solo-stage.sh --upgrade" keep what it must and replace what it must?
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/verify-solo-upgrade.sh
#
# No sudo.  Run as an ordinary user, after "make" in sdb_ai/sd64.  It stages a
# MANAGED scratch tree with solo-stage.sh (test passwords it writes itself, 0600,
# deleted when it ends), puts data of every kind the upgrade must not touch into
# it, upgrades it, and compares.  Then it makes a second upgrade FAIL half way
# and checks the tree came back exactly.  About four minutes.  It leaves nothing
# running and removes its scratch directory.
#
# KEPT (compared byte for byte before and after): the account's files, the
# credential register, sd.conf, the deny list, an object in GLOBAL.BP.OUT and the
# audit trail's old lines.  REPLACED: bin/sd, gplsrc, and the tree's own
# system objects (a marker file planted in each is gone).  WORKS AFTER: the
# account password, the administrator password, the global password, the
# catalogue entry still resolves, verify-solo-global.sh passes.
#
# Exit 0 every leg passed, 1 a leg failed, 2 it could not measure.

set -uo pipefail

refuse() { echo "REFUSED: $*" >&2; exit 2; }
[ "$(id -u)" -ne 0 ] || refuse "do not run this as root"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sd64="$(dirname "$here")"
[ -x "$sd64/bin/sd" ] || refuse "$sd64/bin/sd is not built - run make first"
systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is running for this user; its daemon would collide with this test's"

W="$(mktemp -d)"; chmod 700 "$W"
H="$W/tree"
cleanup() { [ -x "$H/bin/sd" ] && "$H/bin/sd" -stop >/dev/null 2>&1; rm -rf "$W" "$W".* 2>/dev/null; }
trap cleanup EXIT
umask 077

printf 'Acct-Up-Test-4711!\n'  > "$W/a.pw"
printf 'Admin-Up-Test-4712!\n' > "$W/b.pw"
printf 'Glob-Up-Test-4713!\n'  > "$W/c.pw"
ACC="$(head -1 "$W/a.pw")"; ADM="$(head -1 "$W/b.pw")"; GLB="$(head -1 "$W/c.pw")"

echo "verify-solo-upgrade inputs:"
echo "  source tree : $sd64  (bin/sd $(stat -c '%y' "$sd64/bin/sd" | cut -c1-19))"
echo "  scratch     : $W"
echo "  running as  : $(id -un) (uid $(id -u))"

pass=0; fail=0; legs=0
leg() { legs=$((legs+1)); if [ "$3" -eq 0 ]; then pass=$((pass+1)); echo "  [PASS] $1 | $2"; else fail=$((fail+1)); echo "  [FAIL] $1 | expected: $2 | saw: $4"; fi; }
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
clean() { strip | grep -v -E '^\[K:|^\*+$|^[[:space:]]*$|Ladybridge|free software|welcome to|conditions|SD Core for Linux Solo, the'; }
sess() { local pw="$1"; shift; printf '%s\n' "$pw" "$@" OFF | timeout 120 "$H/bin/sd" 2>&1 | clean; }

echo
echo "staging a managed tree with a deny list ..."
bash "$sd64/gplbld/solo-stage.sh" --account-password-file "$W/a.pw" --admin-password-file "$W/b.pw" \
     --global-password-file "$W/c.pw" --deny-verbs DATE "$H" > "$W/stage.log" 2>&1 || { tail -15 "$W/stage.log"; refuse "the first stage failed"; }
"$H/bin/sd" -stop >/dev/null 2>&1

# ---- data of every kind the upgrade must not touch.
echo "keep me" > "$H/user_accounts/sduser/keepme.txt"
mkdir -p "$H/user_accounts/sduser/bp"
cat > "$H/user_accounts/sduser/bp/zzup" <<'BASIC'
   CRT 'ZZUP-RAN'
   END
BASIC
cat > "$H/user_accounts/sduser/bp/zzgsub" <<'BASIC'
      SUBROUTINE zzgsub(X)
      X = 'GLOBAL.OK'
      RETURN
   END
BASIC
cat > "$H/user_accounts/sduser/bp/zzgcall" <<'BASIC'
      X = ''
      CALL *zzgsub(X)
      CRT 'GCALL=':X
   END
BASIC
"$H/bin/sd" -start >/dev/null 2>&1
o="$(sess "$ACC" 'BASIC BP zzup zzgsub zzgcall')"
printf '%s\n' "$o" | grep -q 'Compiled 3 program(s) with no errors' || { printf '%s\n' "$o" | tail -5; refuse "the probe programs did not compile"; }
o="$(sess "$GLB" 'COPY FROM BP.OUT TO GLOBAL.BP.OUT zzgsub' SYNC.GLOBAL.CATALOG)"
printf '%s\n' "$o" | grep -qx 'SYNC GLOBAL CATALOG DONE 1 catalogued 0 removed 0 refused' || { printf '%s\n' "$o" | tail -5; refuse "could not put a program in GLOBAL.BP.OUT"; }
o="$(sess "$ACC" 'CREATE.FILE ZZDATA DYNAMIC' 'WRITE-not-a-verb')"
sess "$ACC" 'ED VOC ZZREC' >/dev/null 2>&1 || true
"$H/bin/sd" -stop >/dev/null 2>&1

# a line appended to sd.conf, and a marker in each place the upgrade replaces
echo "# kept by verify-solo-upgrade" >> "$H/sd.conf"
echo x > "$H/gplsrc/ZZ_MARKER"; echo x > "$H/bin/ZZ_MARKER"; echo x > "$H/tools/ZZ_MARKER"

snap() {   # snap DIR  -> a digest of what must be kept
  ( cd "$1" && {
      find user_accounts -type f -print0 | sort -z | xargs -0 sha256sum
      find '$cred' -type f -print0 | sort -z | xargs -0 sha256sum
      sha256sum sd.conf
      find solo.policy global.bp.out -type f -print0 | sort -z | xargs -0 sha256sum
    } ) | sha256sum | cut -c1-64
}
audit_lines="$(wc -l < "$H/audit")"
kept_before="$(snap "$H")"
echo "  kept-state digest before: $kept_before   (audit: $audit_lines lines)"

# ---- 1. the upgrade runs and says so.
echo
echo "upgrading ..."
bash "$sd64/gplbld/solo-stage.sh" --upgrade "$H" > "$W/up.log" 2>&1; rc=$?
plain="$(strip < "$W/up.log")"
if [ "$rc" -eq 0 ] && printf '%s\n' "$plain" | grep -qx "solo-stage: UPGRADE COMPLETE in $H"; then
  leg "1 the upgrade completes" "exit 0 and 'solo-stage: UPGRADE COMPLETE in <home>'" 0 "complete"
else
  leg "1 the upgrade completes" "exit 0 and 'solo-stage: UPGRADE COMPLETE in <home>'" 1 "rc=$rc; $(printf '%s\n' "$plain" | tail -4 | tr '\n' '|')"
  tail -30 "$W/up.log"; echo "verify-solo-upgrade: $pass passed, $fail failed, of $legs legs"; exit 1
fi

# ---- 2. what must be kept is byte for byte what it was.
kept_after="$(snap "$H")"
[ "$kept_before" = "$kept_after" ] && leg "2 kept state is unchanged" "the digest of the account's files, \$cred, sd.conf, solo.policy and global.bp.out" 0 "$kept_after" \
  || leg "2 kept state is unchanged" "digest $kept_before" 1 "$kept_after"

# ---- 3. the audit trail's old lines are still its first lines.
if [ "$(head -n "$audit_lines" "$H/audit" | sha256sum | cut -c1-16)" = "$(head -n "$audit_lines" "$W"/tree.before-upgrade-*/audit | sha256sum | cut -c1-16)" ]; then
  leg "3 the audit trail keeps its history" "the first $audit_lines lines equal the safety copy's" 0 "kept"
else
  leg "3 the audit trail keeps its history" "the first $audit_lines lines equal the safety copy's" 1 "differ"
fi

# ---- 4. what must be replaced is replaced.
gone=0
for f in "$H/gplsrc/ZZ_MARKER" "$H/bin/ZZ_MARKER" "$H/tools/ZZ_MARKER"; do [ -e "$f" ] && gone=1; done
if [ "$gone" -eq 0 ] && [ "$H/bin/sd" -nt "$W/a.pw" ] && cmp -s "$H/bin/sd" "$sd64/bin/sd"; then
  leg "4 code is replaced" "the planted markers are gone and bin/sd is the source tree's" 0 "replaced"
else
  leg "4 code is replaced" "markers gone, bin/sd identical to the source tree's" 1 "markers-left=$gone"
fi

# ---- 5. every password still works, on the new code.
"$H/bin/sd" -start >/dev/null 2>&1
o1="$(sess "$ACC" WHERE)"; o2="$(sess "$ACC" ADMIN "$ADM" LISTU)"; o3="$(sess "$GLB" WHERE)"
if printf '%s\n' "$o1" | grep -q 'user_accounts/sduser' && printf '%s\n' "$o2" | grep -qx 'Administrator commands unlocked for this session' \
   && printf '%s\n' "$o3" | grep -q 'user_accounts/sduser'; then
  leg "5 the three passwords still work" "account, administrator and global sign in" 0 "all three"
else
  leg "5 the three passwords still work" "account, administrator, global" 1 "$(printf '%s\n' "$o1" | tail -1) / $(printf '%s\n' "$o2" | tail -1) / $(printf '%s\n' "$o3" | tail -1)"
fi

# ---- 6. the account's data and the server's program are usable.
o="$(sess "$ACC" 'RUN BP zzup' 'RUN BP zzgcall')"
n_ran="$(printf '%s\n' "$o" | grep -cx 'ZZUP-RAN')"; n_g="$(printf '%s\n' "$o" | grep -cx 'GCALL=GLOBAL.OK')"
if [ "$n_ran" -eq 1 ] && [ "$n_g" -eq 1 ] && [ "$(cat "$H/user_accounts/sduser/keepme.txt")" = "keep me" ]; then
  leg "6 the account's program and the global program run" "ZZUP-RAN and GCALL=GLOBAL.OK" 0 "both ran"
else
  leg "6 the account's program and the global program run" "ZZUP-RAN and GCALL=GLOBAL.OK" 1 "zzup=$n_ran global=$n_g; $(printf '%s\n' "$o" | tail -2 | tr '\n' '|')"
fi

# ---- 7. the deny list is as installed (DATE still denied, ADMIN runs it).
o="$(sess "$ACC" 'DATE')"
o2="$(sess "$ACC" ADMIN "$ADM" 'DATE')"
if [ "$(printf '%s\n' "$o" | grep -cx 'Command requires administrator privileges')" -eq 1 ] && printf '%s\n' "$o2" | grep -qE '[0-9]{4} +[0-9]+:[0-9]{2}(am|pm)'; then
  leg "7 the deny list survived" "DATE refused without ADMIN; ADMIN still works" 0 "kept"
else
  leg "7 the deny list survived" "DATE refused without ADMIN" 1 "$(printf '%s\n' "$o" | tail -2 | tr '\n' '|')"
fi
"$H/bin/sd" -stop >/dev/null 2>&1

# ---- 8. the witness for the server controls passes on the upgraded tree - after the
# probe program is taken out of GLOBAL.BP.OUT again (it starts from an empty one).
"$H/bin/sd" -start >/dev/null 2>&1
sess "$GLB" 'DELETE GLOBAL.BP.OUT zzgsub' SYNC.GLOBAL.CATALOG >/dev/null
v="$(bash "$here/verify-solo-global.sh" "$H" "$W/a.pw" "$W/b.pw" "$W/c.pw" 2>&1 | strip | grep -E 'verify-solo-global:|\[FAIL\]|REFUSED')"
"$H/bin/sd" -stop >/dev/null 2>&1
case "$v" in
  *", 0 failed,"*) leg "8 verify-solo-global.sh on the upgraded tree" "0 failed" 0 "$(printf '%s\n' "$v" | tail -1)" ;;
  *) leg "8 verify-solo-global.sh on the upgraded tree" "0 failed " 1 "$(printf '%s\n' "$v" | head -3 | tr '\n' '|')" ;;
esac

# ---- 9. a failing upgrade puts the tree back exactly.
# python3 is shimmed so that pcode_bld.py - which runs AFTER the tree's code has been
# replaced - fails.  The whole tree (data included) must then equal what it was.
mkdir "$W/shim"
cat > "$W/shim/python3" <<EOF
#!/bin/bash
case "\$*" in *pcode_bld.py*) echo "shim: pcode_bld.py refused" >&2; exit 1 ;; esac
exec $(command -v python3) "\$@"
EOF
chmod +x "$W/shim/python3"
full_before="$(cd "$H" && find . -type f -not -name 'audit' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)"
ls -d "$W"/tree.before-upgrade-* > "$W/backups.before"
PATH="$W/shim:$PATH" bash "$sd64/gplbld/solo-stage.sh" --upgrade "$H" > "$W/up2.log" 2>&1; rc2=$?
full_after="$(cd "$H" && find . -type f -not -name 'audit' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)"
p2="$(strip < "$W/up2.log")"
new_backups="$(ls -d "$W"/tree.before-upgrade-* | grep -vxFf "$W/backups.before" | wc -l)"
if [ "$rc2" -ne 0 ] && printf '%s\n' "$p2" | grep -q 'UPGRADE FAILED - putting the tree back' \
   && printf '%s\n' "$p2" | grep -q 'the tree is as it was before the upgrade' && [ "$full_before" = "$full_after" ] && [ "$new_backups" -eq 0 ]; then
  leg "9 a failed upgrade puts the tree back" "non-zero exit, the put-back said, every file (audit aside) identical, the failed run's safety copy consumed" 0 "restored"
else
  leg "9 a failed upgrade puts the tree back" "non-zero exit, the put-back said, every file identical" 1 "rc=$rc2 same=$([ "$full_before" = "$full_after" ] && echo yes || echo NO) leftovers=$new_backups; $(printf '%s\n' "$p2" | tail -3 | tr '\n' '|')"
fi

# ---- 10. refusals: not a Solo tree, and a password argument.
mkdir "$W/notree"; : > "$W/notree/x"
o="$(bash "$sd64/gplbld/solo-stage.sh" --upgrade "$W/notree" 2>&1 | strip)"
o2="$(bash "$sd64/gplbld/solo-stage.sh" --upgrade --account-password-file "$W/a.pw" "$H" 2>&1 | strip)"
if printf '%s\n' "$o" | grep -q '^REFUSED: .*not an SD Core for Linux Solo tree' && printf '%s\n' "$o2" | grep -q '^REFUSED: --upgrade takes no password file'; then
  leg "10 refusals" "a non-Solo directory, and a password with --upgrade" 0 "both refused"
else
  leg "10 refusals" "a non-Solo directory, and a password with --upgrade" 1 "$(printf '%s\n' "$o" | tail -1) / $(printf '%s\n' "$o2" | tail -1)"
fi

echo
echo "verify-solo-upgrade: $pass passed, $fail failed, of $legs legs"
[ "$legs" -gt 0 ] || refuse "no leg ran"
[ "$fail" -eq 0 ]
