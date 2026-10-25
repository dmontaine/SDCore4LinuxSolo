#!/bin/bash
# regress-solo.sh - Solo's existing sandbox suites, one after another on ONE built Solo sandbox, a verdict line for each.
#
#   bash /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/regress-solo.sh <dir> [logdir]
#
# <dir> is a sandbox made by this tree's gplbld/sandbox-fromtree.py (all), e.g.
#   SDSOLOBOX_KEYSET=0 python3 gplbld/sandbox-fromtree.py <dir> all
# (no sudo; own shared-memory keys; the live Solo is never touched).  Every suite runs with SDSOLOBOX_KEYSET=0, so nothing else may hold
# keys 0x53434CA1/A2 meanwhile.  logdir (default /tmp/regress-solo-logs) gets sandbox-<suite>.log for each.  Exit 0 when every suite exited 0.
# Written 22 Oct 2026 for carry 13 (the screen library, SED, IDE, CED, tool.keys); Solo has no regress.sh of its own and the list below is the
# whole of Solo's sandbox set at that date.  A failure that looks like left-over state is rerun alone on a FRESH sandbox before it is believed.
# Add sandbox-tk-solo.py's own run (the new suite of carry 13) at the end: it is in the list.
# 23 Oct 2026, carry 14: home-solo (sandbox-home-solo.py: the home screen, tiles off, set.pins, the context help, pdf, set.viewer, docs.install, tool.menus and tool.viewers).
#   It changes start.default, the register record's tile and pins fields and the viewers file while it runs and puts them back; it leaves start.default saying terminal.
# 23 Oct 2026, carry 15: ai-solo (sandbox-ai-solo.py: SET.AI, the ai verb, the kernel's K$AI.* calls and tool.ai against the real helper and a fake provider).  It starts the helper's
#   runner and the fake on a socket and a port of its own inside <dir>/ai, leaves the ai directory it made there, and sets start.default to terminal.
# 23 Oct 2026, carry 16: ai-line-solo (sandbox-ai-line-solo.py: the AI line of the home screen, $tk_ai, against the real helper and the fake provider).  It runs after ai-solo and
#   starts from nothing of ai-solo's: it removes <dir>/ai and makes it again, turns the helper's gate on and off with set.ai, leaves the gate on, and sets start.default to terminal.
#   Its mutants (--mutant=no-preview|action-not-checked|command-default-run|command-not-cleaned) are not run from here.
# 24 Oct 2026, carry 17: ai-apps-solo (sandbox-ai-apps-solo.py: the AI in the IDE, SED and CED, against the real helper and the fake provider).  It runs after ai-line-solo, recompiles tk_ai,
#   sl_form, ide, sed and ced_edit in the sandbox, leaves three records in the account's bp file and the AI configured, and sets start.default to terminal.  Its mutants
#   (--mutant=ide-edit-by-enter|sed-saves|ced-saves|ced-invalid-accepted|dbg-no-source) are not run from here.  Carry 18 added the debugger rows D0-D4 to it (it also recompiles debug).
# 24 Oct 2026, carry 18: oscarry-solo (sandbox-oscarry-solo.py: OSCOPY, !IOSCOPY, SELECT.DIR, SET.MODE, ACCOUNT.PATH, VOCPATH, LOCK.TRACER, INHIBIT.LOGIN, newvoc.mods).  It runs after
#   osgate, changes the register's OS field while it runs and puts it back off, starts a holder session that sleeps 30 s (twice) and kills one (the stale-setter row).
# 24 Oct 2026, carry 20: tool-sessions-solo (sandbox-tool-sessions-solo.py: the administrator's sessions and locks page against live sessions of sduser and the real logout, unlock and
#   inhibit.login).  It runs after oscarry-solo; its holder sessions are logged out by it and a session it kills is reaped by the page; it leaves login.inhibit off and sys/start.default terminal.
# 24 Oct 2026, carry 20b: tool-gates-solo (sandbox-tool-gates-solo.py: the gates page in a plain and an administrator session, the real set.os.access, set.net.access and set.ai verbs).  It runs
#   after tool-sessions-solo, loads sandbox-ai-solo.py's setup (the helper's runner and the fake provider, stopped again at the end), turns every gate off when it starts and when it ends,
#   and leaves sys/start.default terminal.  Its mutants (--mutant=no-typed-name|toggle-by-session|columns-swapped|holder-may-try) are not run from here.
# 25 Oct 2026, W.11 F1 carried: shmmode-solo (sandbox-shmmode-solo.py: the segment and semaphores are 0600 and owned by the user; the daemon sdlnxd, copied to scratch directories, refuses a directory
#   that is not its own and runs the sd-solo beside itself).  It stops the shared sandbox, appends CLEANUP=30 to sd.conf, starts it, signs on a session and kills it so the table holds a lost process,
#   waits up to 60 s for the daemon's scan, then stops the sandbox, puts sd.conf back byte for byte and starts it again.  It runs just before txnfail.

HERE="$(cd "$(dirname "$0")" && pwd)"
BOX="$1"
LOGS="${2:-/tmp/regress-solo-logs}"
[ -n "$BOX" ] || { echo "usage: regress-solo.sh <sandbox dir> [logdir]"; exit 2; }
mkdir -p "$LOGS"
cd "$HERE" || exit 2
bad=0
# txnfail is last: it needs the keys the shared sandbox holds while the suites before it run (23 Oct 2026: it refused with "keys are held" in the middle of the list)
for s in tk-solo home-solo ai-solo ai-line-solo ai-apps-solo apifile crypt csvb csvq guide jsonx osgate oscarry-solo tool-sessions-solo tool-gates-solo pack-examples req29 sdnet-login sdnetfile sdnet sortord vocguard xmlx shmmode-solo txnfail; do
  f="sandbox-$s.py"
  if [ ! -f "$f" ]; then echo "SUITE $s: no such script"; continue; fi
  t0=$(date +%s)
  # txnfail builds its own sandboxes (a fixed one and a mutant per fix) in a directory it is given, which must be empty or absent; the shared sandbox is stopped first
  if [ "$s" = txnfail ]; then
    SDSOLOBOX_KEYSET=0 python3 sandbox-fromtree.py "$BOX" stop > "$LOGS/stop-before-txnfail.log" 2>&1
    args=(--dir "$BOX-txnfail" --clean)
  else args=("$BOX"); fi
  SDSOLOBOX_KEYSET=0 timeout 3000 python3 "$f" "${args[@]}" > "$LOGS/sandbox-$s.log" 2>&1
  rc=$?
  [ $rc -eq 0 ] || bad=$((bad + 1))
  echo "SUITE $s: exit $rc, $(( $(date +%s) - t0 )) s, $(grep -E 'passed|PASS.*of|[0-9]+ pass' "$LOGS/sandbox-$s.log" | tail -1 | cut -c1-130)"
done
echo "regress-solo: $bad suite(s) did not exit 0; logs in $LOGS"
[ $bad -eq 0 ]
