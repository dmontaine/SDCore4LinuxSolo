#!/usr/bin/env python3
# test-tkrestart-units.py - the restart box of SD Core Solo for Linux (S.301, carried from SD Core; SD Core for Windows' row 382), read off
# the source as text.
#
#   python3 /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-tkrestart-units.py [--selftest]
#
# Differs from SD Core's check of the same name where Solo does: Solo is the user's own systemd unit (sd-solo.service), so there is no root
# helper and no sudoers rule to hold (Core's R1 to R4); the restart is one fixed command to the user's systemd, held here as S1 and S2.
#
#   S1  THE COMMAND IS FIXED TEXT: the user's systemd (systemctl --user), the unit sd-solo.service, both from the program's own two names;
#       no variable of the caller's (why, ctx, the page's name) is in it
#   S2  ITS ORDER: the unit must be active (else a sentence and exit 3, nothing restarted), then restart --no-block, then the line that
#       only the way that worked prints
#   R5  $tk_restart is $internal, catalogued, takes four arguments, and starts as 'later'
#   R6  THE BOX: Restart and Not now, NOT NOW LAST (the default); anything but Restart returns before the page is closed or systemd asked
#   R7  THE ORDER ON RESTART: the page is closed, the screen cleared, the line shown, THEN the command - one os.execute; no execute, perform
#       or chain
#   R8  SUCCESS IS THE COMMAND'S OWN LINE and a non-zero status is never success
#   R9  ONE AUDIT LINE, lower case, after the command answered: sd restart app=<page> status=asked|refused
#   R10 AFTER IT: a wait of a minute only when it was asked; then 'failed', the reason shown, Press Enter - never 'later'
#   R11 tool.config: ONE call, only under "takes effect: restart" AND the file and the running SD differing (the row's own mark), inside the
#       branch where the file is known to hold the new value, the status line drawn first, and take.screen when the answer is 'failed'
#   R12 ONLY AN ADMINISTRATOR'S PAGE calls $tk_restart, and no other program restarts the unit
#
# It cannot say that SD restarts or what the screen shows: Solo has no sandbox.  That is an install's row: tool.config after admin, E on
# LGNWAIT, Restart.  Exit 0 every check held, 1 one did not, 2 it could not run.

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
BP = os.path.join(TREE, "sdsys", "gpl.bp")
ME = "test-tkrestart-units"


def read(path):
    try:
        with open(path, encoding="latin-1") as f:
            return f.read()
    except OSError:
        print("%s: CANNOT RUN - no %s" % (ME, path))
        sys.exit(2)


def code(src):
    """BASIC without comment lines and ;* tails."""
    return "\n".join(re.sub(r"\s*;\*.*$", "", ln) for ln in src.split("\n") if not ln.lstrip().startswith("*"))


def ordered(text, *needles):
    at = 0
    for n in needles:
        at = text.find(n, at)
        if at < 0:
            return False
        at += len(n)
    return True


def load():
    raw = {}
    for name in sorted(os.listdir(BP)):
        p = os.path.join(BP, name)
        if os.path.isfile(p) and not name.endswith(".h"):
            raw[name] = read(p)
    if "tk_restart" not in raw or "tool_config" not in raw:
        print("%s: CANNOT RUN - no tk_restart or tool_config in %s" % (ME, BP))
        sys.exit(2)
    return raw


def checks(raw):
    out = []

    def ck(n, what, ok):
        out.append((n, what, bool(ok)))

    tk = code(raw["tk_restart"])
    cmd_lines = "\n".join(ln for ln in tk.split("\n") if re.match(r"\s*cmd\s*(:=|=)", ln))
    ck("S1", "the command is fixed text: systemctl --user and sd-solo.service from the program's own names, no variable of the caller's in it",
       "$define SYSTEMCTL  'LC_ALL=C systemctl --user'" in tk and "$define RS.UNIT    'sd-solo.service'" in tk and cmd_lines.count("\n") == 2
       and not re.search(r"\b(why|ctx|app|lines|msg|res)\b", cmd_lines) and "os.execute cmd : ' 2>&1' capturing out" in tk)
    ck("S2", "its order: the unit active (else a sentence and exit 3), then restart --no-block, then the line only the way that worked prints",
       ordered(cmd_lines, "'if ! ' : SYSTEMCTL : ' is-active --quiet ' : RS.UNIT", "is not active", "exit 3; fi; '",
               "SYSTEMCTL : ' restart --no-block ' : RS.UNIT : ' && echo \"' : anchor : '\"'")
       and "anchor = 'restart of sd-solo.service asked of systemd'" in tk and tk.count("restart --no-block") == 1)
    ck("R5", "$tk_restart is $internal, catalogued, takes four arguments and starts as 'later'",
       ordered(tk, "$internal", "subroutine tk_restart(ctx, why, res, msg)", "$catalog $tk_restart", "res = 'later'", "msg = ''", "call $tk_confirm("))
    ck("R6", "the box: Restart and Not now, Not now last; anything but Restart returns before the page is closed or systemd asked",
       ordered(tk, "call $tk_confirm('systemctl --user restart sd-solo.service', lines, '', cres, cmsg, 'Restart SD?', '&Restart,&Not now')", "if cres # 'run' then", "return", "end",
               "call $tk_close(ctx)", "os.execute")
       and tk.count("call $tk_confirm(") == 1 and "signs out everyone, this session too." in tk)
    ck("R7", "the order on Restart: page closed, screen cleared, the line, then the command - one os.execute; no execute, perform or chain",
       ordered(tk, "call $tk_close(ctx)", "display @(-1) :", "display 'SD is restarting.", "os.execute cmd : ' 2>&1' capturing out", "stat = os.error()")
       and tk.count("os.execute") == 1 and tk.count("call $tk_close(") == 1 and not re.search(r"(?m)^\s*(execute|perform|chain)\b", tk))
    ck("R8", "success is the command's own line, and a non-zero status is never success",
       ordered(tk, "asked = @false", "if ln = anchor then asked = @true", "next i", "if stat # 0 then asked = @false", "kernel(K$AUDIT") and tk.count("asked = @true") == 1)
    ck("R9", "one audit line, lower case, after the command answered",
       tk.count("K$AUDIT") == 1
       and "void kernel(K$AUDIT, 'sd restart app=' : downcase(app) : ' status=' : (if asked then 'asked' else 'refused'))" in tk
       and ordered(tk, "app = ctx<TK.C.APP>", "call $tk_close(ctx)", "stat = os.error()", "void kernel(K$AUDIT"))
    ck("R10", "after it: the wait only when asked; then 'failed', the reason, Press Enter; 'later' is never set again",
       ordered(tk, "void kernel(K$AUDIT", "if asked then", "for w = 1 to 60", "sleep 1", "next w", "end", "res = 'failed'", "display why.not", "display sysmsg(11865) :", "input junk",
               "msg = 'SD was not restarted: ' : why.not", "return")
       and tk.count("res = 'later'") == 1 and tk.count("res = 'failed'") == 1)

    pg = code(raw["tool_config"])
    cp = pg[pg.find("\nchange.param:"):]
    ck("R11", "tool.config: one call, under 'restart' and 'differs', inside the branch where the file holds the new value, the status line first, take.screen on 'failed'",
       pg.count("call $tk_restart(") == 1
       and ordered(cp, "call $tk_run(allow, sent, out, stat, err)", "if stat = 0 and ('S' : trim(now.f)) = ('S' : nv) then", "differs = 0", "if rj > 0 then differs = pdiff<rj>",
                   "\n      if k.eff = 'restart' and differs then\n         why = ", "call $tk_frame(ctx, keys, panes<view>, msg)", "call $tk_restart(ctx, why, rres, rmsg)",
                   "if rres = 'failed' then gosub take.screen", "end", "end else", "msg = 'sd.conf was not changed'")
       and ordered(pg, "\ntake.screen:", "call $tk_open('tool.config', 'admin', ctx, err)", "if err # '' then", "done = 1", "return", "end", "call $tk_aipage('again', ctx, keys, '', '', aout)",
                   "gosub lay.declare", "gosub read.all", "gosub draw.all", "return"))

    callers = sorted(n for n, s in raw.items() if n != "tk_restart" and "$tk_restart(" in code(s))
    # a line that RUNS or BUILDS a command (acc_os_info only shows the sentence to type, in its report)
    others = sorted(n for n, s in raw.items() if n != "tk_restart" and re.search(r"(?m)^\s*(os\.execute|execute|cmd\s*:?=)\b[^\n]*restart[^\n]*sd-solo\.service", code(s)))
    admin = all(re.search(r"call \$tk_open\('[a-z.]+', 'admin', ctx, err\)", code(raw[n])) is not None
                and not re.search(r"call \$tk_open\('[a-z.]+', '(?!admin')", code(raw[n])) for n in callers)
    ck("R12", "only an administrator's page calls it (%s), and no other program restarts the unit (%s)" % (", ".join(callers) or "none", ", ".join(others) or "none"),
       len(callers) >= 1 and admin and not others)
    return out


MUTANTS = [
    ("the system's systemd, not the user's", "tk_restart", "$define SYSTEMCTL  'LC_ALL=C systemctl --user'", "$define SYSTEMCTL  'LC_ALL=C systemctl'"),
    ("another unit", "tk_restart", "$define RS.UNIT    'sd-solo.service'", "$define RS.UNIT    'sd-solo-api.socket'"),
    ("the caller's text on the command line", "tk_restart", "   cmd := SYSTEMCTL : ' restart --no-block ' : RS.UNIT", "   cmd := SYSTEMCTL : ' restart --no-block ' : why : RS.UNIT"),
    ("an inactive unit is restarted", "tk_restart", "   cmd := 'if ! ' : SYSTEMCTL : ' is-active --quiet ' : RS.UNIT", "   cmd := 'if false; then echo ' : RS.UNIT"),
    ("the command waits for the restart", "tk_restart", "' restart --no-block ' : RS.UNIT", "' restart ' : RS.UNIT"),
    ("the success line is printed whatever happened", "tk_restart", "RS.UNIT : ' && echo \"' : anchor : '\"'", "RS.UNIT : ' ; echo \"' : anchor : '\"'"),
    ("not internal", "tk_restart", "$internal\nsubroutine tk_restart", "subroutine tk_restart"),
    ("Restart is the default", "tk_restart", "'&Restart,&Not now'", "'&Not now,&Restart'"),
    ("any answer restarts", "tk_restart", "   if cres # 'run' then\n      msg = 'SD was not restarted: the change takes effect when SD is next started'\n      return\n   end\n", ""),
    ("the screen not cleared", "tk_restart", "   display @(-1) :\n", ""),
    ("success by status alone", "tk_restart", "      if ln = anchor then asked = @true\n", "      asked = @true\n"),
    ("the status ignored", "tk_restart", "   if stat # 0 then asked = @false\n", ""),
    ("no audit line", "tk_restart", "   void kernel(K$AUDIT, 'sd restart app='", "   dummy = ('sd restart app='"),
    ("the audit line in capitals", "tk_restart", "'sd restart app=' : downcase(app)", "'SD RESTART app=' : app"),
    ("no wait for SD", "tk_restart", "      for w = 1 to 60\n         sleep 1\n      next w\n", ""),
    ("a failed restart says later", "tk_restart", "   res = 'failed'\n", "   res = 'later'\n"),
    ("it runs a sentence too", "tk_restart", "   stat = os.error()\n", "   stat = os.error()\n   execute 'who'\n"),
    ("the page asks after a session parameter too", "tool_config", "      if k.eff = 'restart' and differs then\n         why = ", "      if differs then\n         why = "),
    ("the page asks when SD already runs with the value", "tool_config", "      if k.eff = 'restart' and differs then\n         why = ", "      if k.eff = 'restart' then\n         why = "),
    ("the page asks when the file was not changed", "tool_config", "      msg = 'sd.conf was not changed' : (if lastl = '' then '' else ': ' : lastl)\n",
     "      msg = 'sd.conf was not changed' : (if lastl = '' then '' else ': ' : lastl)\n      call $tk_restart(ctx, why, rres, rmsg)\n"),
    ("the page is not taken again", "tool_config", "         if rres = 'failed' then gosub take.screen", "         if rres = 'failed' then null"),
    ("the page comes back for anyone", "tool_config", "take.screen:\n   call $tk_open('tool.config', 'admin', ctx, err)", "take.screen:\n   call $tk_open('tool.config', '', ctx, err)"),
    ("another program restarts the unit", "tool_remote", "$internal\n", "$internal\n   os.execute 'systemctl --user restart sd-solo.service'\n"),
]


def main():
    raw = load()
    if "--selftest" in sys.argv:
        if not all(ok for _, _, ok in checks(raw)):
            print("%s: the real tree does not pass" % ME)
            return 1
        missed = 0
        for label, name, old, new in MUTANTS:
            if old not in raw.get(name, ""):
                print("  [MISSED] %s: nothing to change" % label)
                missed += 1
                continue
            changed = dict(raw)
            changed[name] = raw[name].replace(old, new, 1)
            caught = not all(ok for _, _, ok in checks(changed))
            print("  [%s] %s" % ("caught" if caught else "MISSED", label))
            missed += not caught
        print("selftest: %d caught, %d missed" % (len(MUTANTS) - missed, missed))
        return 1 if missed else 0
    print("%s: tree %s" % (ME, TREE))
    res = checks(raw)
    for n, what, ok in res:
        print("  [%s] %s %s" % ("PASS" if ok else "FAIL", n, what))
    bad = sum(1 for r in res if not r[2])
    print("%s: %d passed, %d failed" % (ME, len(res) - bad, bad))
    return 1 if bad or not res else 0


if __name__ == "__main__":
    sys.exit(main())
