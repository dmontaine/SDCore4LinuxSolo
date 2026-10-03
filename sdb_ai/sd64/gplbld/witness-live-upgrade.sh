#!/usr/bin/env bash
#
# witness-live-upgrade.sh - the half of LSOLO 26 (the server is installed as sd-solo) that the
#                           upgrade itself does not show: an ssh login through the forced
#                           command, and an API session through the socket unit.
#
#   L1  the API: a SCRAM login over TLS as sduser (gplbld/scram-probe.py, a client that shares
#       no code with SD), WHO answers, and WHILE THE SESSION IS OPEN a process whose
#       /proc/<pid>/exe is <tree>/bin/sd-solo is serving it (the socket unit's ExecStart is
#       "bin/sd-solo -n -q");
#   L2  CONTROL: the same login with a wrong password is REFUSED and never VERIFIED;
#   L3  ssh, on SOLO'S OWN PORT 4251 (LSOLO 29): a key login as you lands in SD Core Solo - the
#       sign-on banner, the password asked and taken, WHO answers sduser - and while it is open
#       a process whose exe is <tree>/bin/sd-solo is running that login;
#   L4  CONTROL: a throwaway key that is not in Solo's key file (<tree>/sshd/authorized_keys)
#       is refused (publickey);
#   L5  the host key that port 4251 presents is SOLO'S OWN (<tree>/sshd/ssh_host_ed25519_key.pub),
#       and, when the machine's own sshd is listening on 22, it presents a DIFFERENT one - the
#       proof that the two are separate daemons and the routing is by port.
#   It also says whether the old sshd_config.d drop-in is still on the machine (Solo no longer
#   uses it; "solo-ssh.sh match <tree> --remove" takes it away).
#
# READS REAL STATE AND CHANGES NONE: it only opens sessions on the installed Solo (each leaves
# its sign-on in the audit trail and the logs, which cannot be avoided).  It does not install,
# restart or edit anything; its scratch files are in a mktemp directory it removes.
#
# THE PASSWORD: the kept copy in <tree>/$cred/$stored (what "sd-solo <command>" signs in with)
# is read here and passed only through the environment and the ssh session's input.  It is never
# printed; the output is checked for it and the run FAILS, with the lines masked, if it appears.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/witness-live-upgrade.sh
#
# ***NO sudo.***  Run it as the user who owns the Solo tree (the owner, in his own terminal).
# Optional: HOME_DIR as the first argument (default ~/SDCoreSolo), SD_WITNESS_KEY for a private
# key other than ~/.ssh/id_ed25519.  Exit 0 every leg passed, 1 a leg failed or was not reached,
# 2 it could not run.  The log is /var/tmp/witness-live-upgrade-<time>.log.
#
# THE KEY MUST BE IN SOLO'S OWN KEY FILE, which is not ~/.ssh/authorized_keys any more.  If it is
# not, L3/L4/L5 say NOT REACHED and name the one command that adds it:
#     bash <tree>/tools/solo-ssh.sh key-add <tree> <the public key file>
#
set -u

SELF="$(cd "$(dirname "$0")" 2>/dev/null && pwd)/$(basename "$0")"
HERE="$(cd "$(dirname "$0")" && pwd)"
H="${1:-$HOME/SDCoreSolo}"
KEY="${SD_WITNESS_KEY:-$HOME/.ssh/id_ed25519}"
PROBE="$HERE/scram-probe.py"
PORT=4249
SSH_PORT=4251
STAMP=$(date +%Y%m%dT%H%M%S)
LOG="${SD_WITNESS_LOG:-/var/tmp/witness-live-upgrade-$STAMP.log}"   # the logged re-run keeps the first run's name
PASS=0; FAIL=0; NOTREACHED=0

say() { printf '%s\n' "$*"; }
strip() { sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g'; }
pass() { PASS=$((PASS+1)); say "  PASS  $1"; }
fail() { FAIL=$((FAIL+1)); say "  FAIL  $1"; }
notreached() { NOTREACHED=$((NOTREACHED+1)); say "  NOT REACHED  $1"; }
need() { say "CANNOT RUN: $1"; exit 2; }

# solo_pids - the pids of this user's processes whose executable is the Solo server
solo_pids() {   # one find, not a fork per process (the first version took over a minute a scan)
  find /proc -maxdepth 2 -name exe -user "$(id -u)" -lname "$H/bin/sd-solo" 2>/dev/null | sed -n 's#^/proc/\([0-9][0-9]*\)/exe$#\1#p'
}

if [ "${SD_WITNESS_LOGGED:-}" != 1 ]; then
  [ "$(id -u)" -ne 0 ] || need "do not run this as root"
  SD_WITNESS_LOGGED=1 SD_WITNESS_LOG="$LOG" LOG="$LOG" exec bash -c 'bash "$0" "$@" 2>&1 | tee "$LOG"; exit ${PIPESTATUS[0]}' "$SELF" "$@"
fi

say "witness-live-upgrade.sh  $STAMP"
say "  script  : $SELF"
say "  tree    : $H"
say "  user    : $(id -un) (uid $(id -u))   log: $LOG"
[ -x "$H/bin/sd-solo" ] || need "$H/bin/sd-solo is not there"
[ -f "$H/.sdcoresolo" ] || need "$H has no .sdcoresolo marker - not a Solo tree"
[ -r "$H/\$cred/\$stored" ] || need "no kept password copy ($H/\$cred/\$stored): this install was made without one, so this script cannot sign in"
[ -f "$PROBE" ] || need "$PROBE is missing"
command -v python3 >/dev/null && command -v ssh >/dev/null && command -v ssh-keygen >/dev/null || need "python3, ssh and ssh-keygen are required"
[ "$(systemctl --user is-active sd-solo.service 2>/dev/null)" = active ] || need "sd-solo.service is not active"
ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT " || ss -ltn 2>/dev/null | grep -q "0.0.0.0:$PORT " || need "nothing is listening on port $PORT (is the API on?)"
# The record is two lines: the account name in capitals, then the password (login reads
# pw.rec<1> = account, pw.rec<2> = password).  The first version read line 1 and every login failed.
STORED_ACCT="$(sed -n 1p "$H/\$cred/\$stored")"
[ "$STORED_ACCT" = SDUSER ] || need "the kept password record names '$STORED_ACCT', not SDUSER: not the format this script reads"
PW="$(sed -n 2p "$H/\$cred/\$stored")"
[ -n "$PW" ] || need "the kept password copy is empty"

W="$(mktemp -d)"; chmod 700 "$W"
trap 'rm -rf "$W"' EXIT
say "  stamp   : $(sed -n 1,2p "$H/.sdcore-install" | tr '\n' ' ')"
say "  server  : $(readlink -f "$H/bin/sd-solo")   units: $(grep -h '^ExecStart' "$HOME/.config/systemd/user/sd-solo-api@.service" 2>/dev/null | head -1)"
DROPIN="/etc/ssh/sshd_config.d/50-sd-solo-$(id -un).conf"
SSH_AK="$H/sshd/authorized_keys"
say "  ssh     : Solo's own listener on port $SSH_PORT: $(systemctl --user is-active sd-solo-ssh.socket 2>&1) ($(sed -n 's/^ListenStream=//p' "$HOME/.config/systemd/user/sd-solo-ssh.socket" 2>/dev/null | head -1)); ForceCommand: $(grep -m1 '^ForceCommand' "$H/sshd/sshd_config" 2>/dev/null)"
if [ -e "$DROPIN" ]; then say "  old route: $DROPIN is STILL THERE (Solo no longer uses it; remove it: bash $H/tools/solo-ssh.sh match $H --remove)"; else say "  old route: no $DROPIN"; fi
say "  before  : service $(systemctl --user is-active sd-solo.service), solo server pids: [$(solo_pids | tr '\n' ' ')]"

leaked() { # leaked FILE - the password must not be in the output
  if grep -qF -- "$PW" "$1" 2>/dev/null; then sed -i "s|$(printf '%s' "$PW" | sed 's/[][\.*^$/|&]/\\&/g')|<PASSWORD MASKED>|g" "$1"; return 0; fi
  return 1
}

# ------------------------------------------------------------------ L1 / L2: the API
say ""
say "== L1: an API session, served by bin/sd-solo =="
say "  > scram-probe.py --port $PORT --user sduser --account sduser --pause 8 -- WHO   (password via the environment)"
SD_SCRAM_PASSWORD="$PW" timeout 60 python3 "$PROBE" --port "$PORT" --user sduser --account sduser --pause 8 -- WHO > "$W/api1.out" 2>&1 &
PPID1=$!
found=""
for _ in $(seq 1 20); do
  for p in $(solo_pids); do
    if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -- ' -n -q'; then found="$p: $(tr '\0' ' ' < "/proc/$p/cmdline") -> $(readlink "/proc/$p/exe")"; break 2; fi
  done
  sleep 0.5
done
wait "$PPID1"
LEAK1=0; leaked "$W/api1.out" && LEAK1=1      # masked BEFORE it is printed or logged
strip < "$W/api1.out" | sed -e 's/^/      | /'
[ "$LEAK1" -eq 0 ] || fail "L1 the password appeared in the probe's output (masked above)"
if grep -qx 'SCRAM: server signature VERIFIED' <(strip < "$W/api1.out") && grep -q '^account sduser: entered' <(strip < "$W/api1.out") && grep -qE '^\| [0-9]+ sduser' <(strip < "$W/api1.out"); then
  pass "L1 SCRAM login VERIFIED, account entered, WHO answers sduser"
else
  fail "L1 the API login did not end VERIFIED / entered / WHO sduser"
fi
if [ -n "$found" ]; then pass "L1 while the session was open, the server serving it was: $found"; else fail "L1 no process with exe $H/bin/sd-solo and ' -n -q' was seen while the API session was open"; fi

say ""
say "== L2: CONTROL - a wrong password =="
SD_SCRAM_PASSWORD="not-the-password-$STAMP" timeout 60 python3 "$PROBE" --port "$PORT" --user sduser --account sduser -- WHO > "$W/api2.out" 2>&1
strip < "$W/api2.out" | grep -E '^SCRAM|^transport|^TLS' | sed -e 's/^/      | /'
if grep -q '^SCRAM: login REFUSED' <(strip < "$W/api2.out") && ! grep -q 'server signature VERIFIED' <(strip < "$W/api2.out"); then pass "L2 a wrong password is REFUSED and never VERIFIED"; else fail "L2 the wrong password was not refused"; fi

# ------------------------------------------------------------------ L3 / L4: ssh
say ""
say "== L3: an ssh login with your key, on Solo's own port $SSH_PORT =="
if ! ss -ltn 2>/dev/null | grep -qE "[:.]$SSH_PORT "; then
  notreached "L3/L4/L5 nothing is listening on port $SSH_PORT (is the ssh listener on? bash $H/tools/solo-service.sh status; bash $H/tools/solo-service.sh ssh $H local)"
elif [ ! -r "$KEY" ] || [ ! -r "$KEY.pub" ]; then
  notreached "L3 $KEY or $KEY.pub is not readable (set SD_WITNESS_KEY to a private key whose public key is in $SSH_AK)"
else
  FP="$(ssh-keygen -lf "$KEY.pub" 2>/dev/null | awk '{print $2}')"
  if ssh-keygen -lf "$SSH_AK" 2>/dev/null | awk '{print $2}' | grep -qxF "$FP"; then
    say "  key $KEY ($FP) is in $SSH_AK"
    SSHO="-p $SSH_PORT -o BatchMode=yes -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey -o UserKnownHostsFile=$W/kh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
    say "  > ssh -tt $SSHO -i $KEY 127.0.0.1   (the password is typed after SD asks for it; WHO and OFF follow)"
    before="$(solo_pids | tr '\n' ' ')"
    # A terminal's Enter is CR, not LF: SD reads the password and the commands in raw mode, where an
    # LF is just another character.  The first two runs sent LF, so the 10 password characters, WHO and
    # OFF were all taken as ONE password (16 stars on the screen) and nothing was ever submitted.
    ( sleep 3; printf '%s\r' "$PW"; sleep 6; printf 'WHO\rOFF\r'; sleep 1 ) | timeout 60 ssh -tt $SSHO -i "$KEY" "$(id -un)@127.0.0.1" > "$W/ssh1.out" 2>&1 &
    SPID=$!
    sleep 6
    during=""
    for p in $(solo_pids); do case " $before " in *" $p "*) ;; *) during="$during $p: $(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)-> $(readlink "/proc/$p/exe")" ;; esac; done
    wait "$SPID"
    LEAK3=0; leaked "$W/ssh1.out" && LEAK3=1      # masked BEFORE it is printed or logged
    strip < "$W/ssh1.out" | sed -e 's/^/      | /'
    [ "$LEAK3" -eq 0 ] || fail "L3 the password appeared in the ssh session's output (masked above)"
    out="$(strip < "$W/ssh1.out")"
    if printf '%s\n' "$out" | grep -qE '^[0-9]+ sduser' && printf '%s\n' "$out" | grep -q 'Password:' && ! printf '%s\n' "$out" | grep -q -E 'Permission denied|Connection (closed|refused)|No such file'; then
      pass "L3 the ssh login reached SD Core Solo: it asked for the password and WHO answers sduser"
    else
      fail "L3 the ssh login did not reach a signed-in SD Core Solo session"
    fi
    if [ -n "$during" ]; then pass "L3 while it was open, a new server process ran it:$during"; else fail "L3 no NEW process with exe $H/bin/sd-solo was seen while the ssh session was open"; fi
    say ""
    say "== L4: CONTROL - a key that is not in Solo's key file =="
    ssh-keygen -q -t ed25519 -N '' -f "$W/stranger" -C witness-stranger
    timeout 30 ssh -tt $SSHO -i "$W/stranger" "$(id -un)@127.0.0.1" < /dev/null > "$W/ssh2.out" 2>&1
    strip < "$W/ssh2.out" | sed -e 's/^/      | /'
    if grep -q 'Permission denied' "$W/ssh2.out" && ! grep -qE '^[0-9]+ sduser|Password:' <(strip < "$W/ssh2.out"); then pass "L4 a stranger's key is refused (Permission denied), no SD session"; else fail "L4 the stranger's key was not refused as expected"; fi
    say ""
    say "== L5: port $SSH_PORT presents Solo's own host key, not the machine's =="
    solo_hk="$(ssh-keygen -lf "$H/sshd/ssh_host_ed25519_key.pub" 2>/dev/null | awk '{print $2}')"
    seen_hk="$(ssh-keyscan -t ed25519 -p "$SSH_PORT" 127.0.0.1 2>/dev/null | ssh-keygen -lf - 2>/dev/null | awk '{print $2}' | head -1)"
    say "  Solo's host key file : ${solo_hk:-none}"
    say "  port $SSH_PORT presented    : ${seen_hk:-nothing}"
    if [ -n "$solo_hk" ] && [ "$solo_hk" = "$seen_hk" ]; then pass "L5 port $SSH_PORT presents the host key in $H/sshd"; else fail "L5 port $SSH_PORT did not present Solo's own host key"; fi
    if ss -ltn 2>/dev/null | grep -qE '[:.]22 '; then
      sys_hk="$(ssh-keyscan -t ed25519 -p 22 127.0.0.1 2>/dev/null | ssh-keygen -lf - 2>/dev/null | awk '{print $2}' | head -1)"
      say "  port 22 presented     : ${sys_hk:-nothing}"
      if [ -n "$sys_hk" ] && [ "$sys_hk" != "$seen_hk" ]; then pass "L5 CONTROL: the machine's own sshd on 22 presents a DIFFERENT host key (two daemons, routing by port)"; else fail "L5 CONTROL: port 22 presented the same host key (or none) - the two are not separate"; fi
    else
      say "  nothing listens on port 22 on this computer; the separation control is not applicable"
    fi
  else
    notreached "L3/L4/L5 $KEY.pub ($FP) is not in $SSH_AK, so no login can be made with it; add it: bash $H/tools/solo-ssh.sh key-add $H $KEY.pub"
  fi
fi

say ""
say "  NOT CHECKED BY THIS SCRIPT: a sign-in with your LINUX PASSWORD on port $SSH_PORT (LSOLO 29, owner 2 Oct 2026: the"
say "  sign-in is the Linux account name and password; a key is optional).  The script never handles that password. Try it yourself:"
say "      ssh -p $SSH_PORT -o PubkeyAuthentication=no $(id -un)@127.0.0.1      (your Linux password, then SD's account password)"
say ""
say "  after   : service $(systemctl --user is-active sd-solo.service), solo server pids: [$(solo_pids | tr '\n' ' ')]"
say ""
say "== result: $PASS passed, $FAIL failed, $NOTREACHED not reached =="
[ -f "$LOG" ] && chmod 600 "$LOG"
[ "$FAIL" -eq 0 ] && [ "$NOTREACHED" -eq 0 ] && exit 0 || exit 1
