#!/usr/bin/env python3
#
# sandbox-ai-apps-solo.py - the AI in the IDE, SED, CED and the debugger (AI line stages 2 and 3), driven on a pseudo-terminal on a private SD Core for Linux Solo
#                           (SOLO CARRY 17 of S.69, 24 Oct 2026; Core commit 0f0e6d9 and the stage 3 commit after it; the debugger rows with the debugger's own carry, 24 Oct 2026).  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-ai-apps-solo.py <dir> [--build] [--mutant=NAME]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent).  Exit 0 every row passed, 1 a row failed, 2 it
# could not run.  With --mutant=NAME one change is made to the SANDBOX'S OWN COPY of a program and exit 0 means the rows that had to fail failed and no others (MUTANTS below).
# Solo's counterpart of Core's sandbox-ai-ide.py (the IDE rows) and sandbox-ai-apps.py (SED, CED and the debugger).  The harness
# is sandbox-ai-line-solo.py's (the home / ai modules, the helper's runner and the fake provider, the gate as the helper's setting); the programs run in the one account, sduser, at the
# terminal prompt of a session that has just signed on (Core: a fixture account and SDTEST_ADMIN).  What each app DID is read from the DISK afterwards (CT in a pipe session), never
# from what the screen said; "nothing was sent" from the fake's request log and the audit file.
#
#   I0-I1   the IDE, AI off: the menu bar as ever, no AI> row;  AI on: the AI menu before Help and the AI> row
#   I3-I7   Enter in the AI entry shows EVERYTHING that will be sent, Cancel the default; Send makes ONE request and the kernel's one audit line; the edit is a diff; Reject leaves the
#           buffer; Accept changes the buffer (not the disk) and one Ctrl-Z takes it back
#   I9      an edit set that does not fit is ignored whole and said so
#   S0-S9   SED: Tools has the two AI items only with the AI on; Ask: the request on the message row, the preview, Cancel, Send, the diff, Reject, Accept (buffer, not disk), ONE Ctrl-Z;
#           Explain the selection with no mark says so, with a mark previews the selected text; the command typed with its request
#   C0-C7   CED: F2 does nothing with the AI off; on, a menu of three; the preview shows the record as indented JSON; the diff; Accept changes the record (not the disk); Ctrl-S saves;
#           an edit that would leave invalid JSON is ignored; the AI's last change is undone from the menu; explain the selected element
#   D0-D4   the debugger: ai is not a command with the AI off; on, ai shows the program, the stack and the source round the stop in the preview; Send answers in words; the popup goes and
#           the debugger's screen is whole and still works; the SECOND stop of the program has the command too (the setting is in the debugger's common)
# NOT HELD: the end of the input during the wait, a record over 24000 bytes, SED's split window, the debugger in line mode and in a phantom, a real provider.
import importlib.util
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ll = _load("sandbox_ai_line_solo_for_apps", "sandbox-ai-line-solo.py")
sh, ai = ll.sh, ll.ai
import fakemodel  # noqa: E402

say, bail, has, put, plain, adm, H = sh.say, sh.bail, sh.has, sh.put, sh.plain, sh.adm, sh.H
RUN = "%05d" % (os.getpid() % 100000)
OK_REC = "zzaio" + RUN                   # crt 'hello' / x = 1 / crt 'bye' / end
ERR_REC = "zzaie" + RUN                  # crt "one" / x = = 1 / end
CED_REC = "zzaic" + RUN                  # {"name":"widget","size":3,"tags":["a","b"]}
BODY = ["   crt 'hello'", "   x = 1", "   crt 'bye'", "end"]
PROGS = ("sl_form", "tk_ai", "ide", "sed", "ced_edit", "debug")
DBG_PROG = "zzaid" + RUN                 # x = 5 / y = 'abc' / debug / crt 'AFTER-DEBUG' / debug / crt 'AFTER-TWO' / end   (compiled DEBUGGING; two stops)
FAILED_IDS = []
DOWN, RIGHT, TAB, RET, ESC = "\x1b[B", "\x1b[C", "\t", "\r", "\x1b"      # a Solo session is not in application cursor-key mode: the keys are ESC [ B / C (sandbox-home-solo.py KEYS), not ESC O B / C as in Core's harness
F10, F2, F7 = "\x1b[21~", "\x1bOQ", "\x1b[18~"
CTRL_Z = "\x1a"
TOOLS = RIGHT * 5                        # SED: F10 opens File; Tools is the sixth title
AI_MENU = RIGHT * 5                      # the IDE: F10 opens File; the AI menu is the sixth title (File Go Search Build View AI Help)
ASK_KEY, EXPLAIN_KEY = "a", "p"          # SED's Tools: Ask the &AI...  and  Ex&plain the selection


def arow(rid, name, ok, detail=""):
    sh.row("%s %s" % (rid, name), ok, detail)
    if not ok:
        FAILED_IDS.append(rid)
        if STATE.get("last"):
            say("      screen at the failure of %s:" % rid)
            for ln in STATE["last"].split("\n"):
                say("      | " + ln.rstrip()[:140])


STATE = {}

MUTANTS = {
    # name: (program of the sandbox, old text, new text, the row ids that must fail and no others)
    "ide-edit-by-enter": ("tk_ai", "         dflt = 2                                         ;* a change to a text is never accepted by Enter alone", "         dflt = 1", ["I6"]),
    "sed-saves": ("sed", "   message = sysmsg(11661, ai.sp<3>)\n   gosub ai.say\n", "   gosub save.record\n   message = sysmsg(11661, ai.sp<3>)\n   gosub ai.say\n", ["S5", "S8"]),
    "ced-saves": ("ced_edit", "   message.text = sysmsg(11676, ai.sp<3>)\n", "   gosub save.record\n   message.text = sysmsg(11676, ai.sp<3>)\n", ["C4"]),
    "ced-invalid-accepted": ("ced_edit", "   if ai.bad then\n      message.text = sysmsg(11677)\n      return\n   end\n", "   if ai.bad then\n      ai.y = jparse('{}')\n   end\n", ["C6", "C7"]),
    "dbg-no-source": ("debug", "   for ai.q = ai.first to ai.last\n", "   for ai.q = ai.first to ai.first - 1\n", ["D2"]),   # (D2 reads the request at the fake; D1's preview shows only the first eight lines of the page)
}
MUTANT_SECTIONS = {"ide-edit-by-enter": "ide", "sed-saves": "sed", "ced-saves": "ced", "ced-invalid-accepted": "ced", "dbg-no-source": "dbg"}


class Sess(H):
    """sandbox-home-solo.py's session, with a command typed at the prompt (the start setting is terminal)."""

    def __init__(self, cmd, cols=140, rows=43, term=None):
        H.__init__(self, cols=cols, rows=rows)
        if term:                 # a Solo session starts as terminal type `linux` (no alternate screen, F2 is ESC [ [ B): CED's F2 and the debugger's full-screen display need `TERM xterm`, as Core's harness types
            self.typed("TERM %s\r" % term, idle=0.8)
        self.typed(cmd + "\r", idle=2.0)

    def lines(self):
        L = H.lines(self)
        STATE["last"] = "\n".join(l.rstrip() for l in L if l.strip())
        return L

    def keys(self, *chunks, idle=0.6):
        for c in chunks:
            self.s.type(c, idle=idle)
        return self.lines()

    def end(self):
        self.s.type("\rOFF\r", idle=0.5)
        self.s.finish()


def wait_popup(h, tmax=15.0):
    """The answer's popup has Accept or Close on it; the pty is read only while the suite waits on it."""
    t0 = time.time()
    while time.time() - t0 < tmax:
        h.s.settle(0.5)
        T = h.text()
        if "[ Close ]" in T or "[ Accept ]" in T:
            return T
    return h.text()


def rec(rid):
    return "\n".join(plain(["CT bp %s" % rid]))


def requests():
    return ai.requests(ai.STATE["fm"])


def make_records():
    prog = "zzaimk" + RUN
    body = "\n".join([
        "   open 'bp' to f else stop 'no bp'",
        "   write \"%s\" on f, '%s'" % ("\":@fm:\"".join(BODY), OK_REC),
        "   write 'crt \"one\"':@fm:'x = = 1':@fm:'end' on f, '%s'" % ERR_REC,
        "   write '{\"name\":\"widget\",\"size\":3,\"tags\":[\"a\",\"b\"]}' on f, '%s'" % CED_REC,
        "   crt 'RECORDS DONE'", "end", ""])
    put(os.path.join(sh.ACCT, "bp", prog), body)
    out = "\n".join(plain(["BASIC bp %s" % prog, "RUN bp %s" % prog]))
    if "RECORDS DONE" not in out:
        bail("the records were not made:\n" + out[-500:])


def make_debug_program():
    src = "\n".join(["   x = 5", "   y = 'abc'", "   debug", "   crt 'AFTER-DEBUG'", "   debug", "   crt 'AFTER-TWO'", "end", ""])      # two stops: ai.ok lives in debug.h's common, set at the FIRST
    put(os.path.join(sh.ACCT, "bp", DBG_PROG), src)
    out = "\n".join(plain(["BASIC bp %s DEBUGGING" % DBG_PROG]))
    if "with no errors" not in out:
        bail("the debugger's program did not compile:\n" + out[-500:])


def setup_apps(mutant):
    for n in PROGS + ("debug.h",):
        shutil.copyfile(os.path.join(TREE, "sdsys", "gpl.bp", n), os.path.join(sh.SYS, "gpl.bp", n))
    if mutant is not None:
        prog, old, new, _k = MUTANTS[mutant]
        path = os.path.join(sh.SYS, "gpl.bp", prog)
        src = open(path, encoding="utf-8", errors="replace").read()
        if src.count(old) != 1:
            bail("mutant %s: the text to change is found %d times, not once" % (mutant, src.count(old)))
        put(path, src.replace(old, new))
        say("sandbox-ai-apps-solo: MUTANT %s: %s changed; the rows that must fail, and nothing else: %s" % (mutant, prog, ", ".join(MUTANTS[mutant][3])))
    for n in PROGS:
        ai.compile_prog(n)


def ide_has_ai(h):
    return re.search(r"File\s+Go\s+Search\s+Build\s+View\s+AI\s+Help", h.text()) is not None and "AI>" in h.text()


def focus_entry(h):
    for _ in range(6):
        if "[AI]" in h.lines()[-1] or any("[AI]" in l for l in h.lines()[-3:]):
            return True
        h.keys(TAB)
    return any("[AI]" in l for l in h.lines()[-3:])


def sec_ide_off():
    say("\n--- the IDE, the AI off")
    ll.configure(provider=False)
    h = Sess("IDE bp %s" % OK_REC)
    L = h.lines()
    arow("I0", "no provider: the menu bar is File Go Search Build View Help as ever and there is no AI> row", re.search(r"File\s+Go\s+Search\s+Build\s+View\s+Help", L[0]) is not None and "AI>" not in h.text(), repr(L[0][:80]))
    h.end()
    ll.configure()


def sec_ide():
    say("\n--- the IDE, the AI on")
    fm = ai.STATE["fm"]
    h = Sess("IDE bp %s" % OK_REC)
    arow("I1", "the AI menu is before Help and there is an AI> row under the editor", ide_has_ai(h), h.text()[:300])
    focus_entry(h)
    n0, a0 = len(fm.log), ai.audit_off()
    h.keys("make the greeting longer [[edit_ok]]")
    T = "\n".join(h.keys(RET))
    arow("I3", "Enter shows EVERYTHING that will be sent (provider, the instruction naming the IDE, the record's lines, the request), Send and Cancel, and sends nothing",
         "This will be sent to anthropic" in T and "who is using IDE" in T and "crt 'hello'" in T and "make the greeting longer [[edit_ok]]" in T and "Send" in T and "Cancel" in T and len(fm.log) == n0, T[-1200:])
    h.keys(RET)
    arow("I3c", "Enter on the default button is Cancel: nothing was sent (the fake and the audit file agree)", len(fm.log) == n0 and not ai.req_lines(ai.audit_new(a0)), "")
    h.end()
    h = Sess("IDE bp %s" % OK_REC)
    focus_entry(h)
    n0, a0 = len(fm.log), ai.audit_off()
    h.keys("make the greeting longer [[edit_ok]]", RET)
    h.keys("s")
    T = wait_popup(h)
    rq = requests()
    pr = ai.prompt_of(rq[-1][2]) if len(rq) > n0 else ""
    rl = ai.req_lines(ai.audit_new(a0))
    arow("I4", "Send: ONE request, the request as its last line, with the record's lines; ONE audit line, the kernel's, program tk_ai, none holds the record's text",
         len(fm.log) == n0 + 1 and pr.endswith("Request: make the greeting longer [[edit_ok]]") and "crt 'hello'" in pr and len(rl) == 1 and "program=tk_ai" in rl[0] and "crt 'hello'" not in ai.audit_new(a0), repr((len(fm.log) - n0, rl)))
    arow("I5", "the answer is a popup with the diff (the old line with -, the new with +), Accept and Reject", "I made the greeting longer." in T and "- crt 'hello'" in T and "+ crt 'hello world'" in T and "[ Accept ]" in T and "[ Reject ]" in T, T[-900:])
    h.keys(RET)
    arow("I6", "Enter alone is Reject: the editor and the disk are as they were", "hello world" not in h.text() and "hello world" not in rec(OK_REC), "")
    focus_entry(h)
    h.keys("longer [[edit_ok]]", RET, "s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    arow("I7a", "Accept: the editor shows the new line and the disk does not have it", "crt 'hello world'" in h.text() and "hello world" not in rec(OK_REC), h.text()[-500:])
    for _ in range(6):
        if any("[Editor]" in l or "[Edit" in l for l in h.lines()[-3:]):
            break
        h.keys(TAB)
    h.keys(CTRL_Z)
    time.sleep(0.8)
    h.s.settle(0.5)
    arow("I7c", "ONE Ctrl-Z takes the change back", "crt 'hello world'" not in h.text() and "crt 'hello'" in h.text(), h.text()[-500:])
    h.end()                              # a new session: the AI entry still holds the earlier requests' text, and the request would be appended to it
    h = Sess("IDE bp %s" % OK_REC)
    focus_entry(h)
    h.keys("x [[edit_dup]]", RET, "s")
    T = wait_popup(h)
    arow("I9", "edit_dup: a set that does not fit is ignored whole and said so (found more than once), no Accept button", ai.msg(11660, "old text found more than once") in T and "[ Accept ]" not in T and "[ Close ]" in T, T[-700:])
    h.keys(RET)
    h.end()


def sed_ask(h, request):
    h.keys(F10, TOOLS)
    h.keys(ASK_KEY)
    h.keys(request)
    return "\n".join(h.keys(RET))


def tools_has(h, text):
    h.keys(F10, TOOLS)
    T = h.text()
    h.keys(ESC)
    return text in T


def sec_sed():
    say("\n--- SED")
    fm = ai.STATE["fm"]
    ll.configure(provider=False)
    h = Sess("SED bp %s" % OK_REC)
    arow("S0", "no provider: the Tools menu has no Ask the AI and no Explain the selection", tools_has(h, "Compile") and not tools_has(h, "Ask the AI") and not tools_has(h, "Explain the selecti"), "")
    h.end()
    ll.configure()
    h = Sess("SED bp %s" % OK_REC)
    arow("S1", "the Tools menu lists Ask the AI... and Explain the selection", tools_has(h, "Ask the AI...") and tools_has(h, "Explain the selecti"), h.text()[:300])
    n0, a0 = len(fm.log), ai.audit_off()
    T = sed_ask(h, "make the greeting longer [[edit_ok]]")
    arow("S2", "Enter on the request shows EVERYTHING that will be sent (the provider, the instruction naming SED, the record's lines, the request), Send and Cancel, and sends nothing",
         "This will be sent to anthropic" in T and "who is using SED" in T and "crt 'hello'" in T and "x = 1" in T and "make the greeting longer [[edit_ok]]" in T and "Send" in T and "Cancel" in T and len(fm.log) == n0, T[-1500:])
    h.keys(RET)
    arow("S3", "Enter on the default button is Cancel: nothing was sent", len(fm.log) == n0 and not ai.req_lines(ai.audit_new(a0)), "")
    sed_ask(h, "make the greeting longer [[edit_ok]]")
    h.keys("s")
    T = wait_popup(h)
    rq = requests()
    pr = ai.prompt_of(rq[-1][2]) if len(rq) > n0 else ""
    rl = ai.req_lines(ai.audit_new(a0))
    arow("S4a", "Send: ONE request, the request as its last line, with the record's lines; ONE audit line, the kernel's, program tk_ai, none holds the record's text",
         len(fm.log) == n0 + 1 and pr.endswith("Request: make the greeting longer [[edit_ok]]") and "crt 'hello'" in pr and len(rl) == 1 and "program=tk_ai" in rl[0] and "crt 'hello'" not in ai.audit_new(a0), repr((len(fm.log) - n0, rl)))
    arow("S4b", "the answer is a popup: what the AI said and the diff with Accept and Reject", "I made the greeting longer." in T and "- crt 'hello'" in T and "+ crt 'hello world'" in T and "[ Accept ]" in T and "[ Reject ]" in T, T[-900:])
    h.keys(RET)
    arow("S4c", "Enter alone is Reject: the buffer is as it was and so is the disk", "hello world" not in h.text() and "hello world" not in rec(OK_REC), "")
    sed_ask(h, "make the greeting longer [[edit_ok]]")
    h.keys("s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    arow("S5", "Accept: the buffer shows the new line, the disk does not have it", "crt 'hello world'" in h.text() and "hello world" not in rec(OK_REC), h.text()[-600:])
    h.keys(RIGHT)
    h.keys(CTRL_Z)
    time.sleep(0.8)
    arow("S6", "ONE Ctrl-Z takes the change back: the old line is in the buffer", "crt 'hello world'" not in h.text() and "crt 'hello'" in h.text(), h.text()[-500:])
    sed_ask(h, "x [[edit_dup]]")
    h.keys("s")
    T = wait_popup(h)
    arow("S9", "edit_dup: a set that does not fit is ignored whole and said so, no Accept button", ai.msg(11660, "old text found more than once") in T and "[ Accept ]" not in T and "[ Close ]" in T, T[-700:])
    h.keys(RET)
    h.end()
    h = Sess("SED bp %s" % OK_REC)
    n0 = len(fm.log)
    h.keys(F10, TOOLS)
    h.keys(EXPLAIN_KEY)
    arow("S7", "Explain the selection with no mark: the message row says to set one (11671) and nothing is sent", ai.msg(11671)[:30] in h.text() and len(fm.log) == n0, h.text()[-300:])
    h.keys(RET)
    h.keys("\x1b.")
    h.keys(DOWN)
    h.keys(F10, TOOLS)
    h.keys(EXPLAIN_KEY)
    T = h.text()
    arow("S8", "with a mark and the cursor a line down: the preview shows the selected text and its size and sends nothing", ai.msg(11669, 1).split("1")[0][:20] in T and "crt 'hello'" in T and len(fm.log) == n0, T[-900:])
    h.keys(RET)
    h.end()


def ced_ask(h, request):
    h.keys(F2)
    h.keys("a")
    h.keys(request, RET)
    return h.text()


def sec_ced():
    say("\n--- CED")
    fm = ai.STATE["fm"]
    ll.configure(provider=False)
    h = Sess("CED bp %s" % CED_REC, term="xterm")
    h.keys(F2)
    arow("C0", "no provider: F2 does nothing (no AI menu), and the record is on screen", "Explain the selected element" not in h.text() and "widget" in h.text(), h.text()[-400:])
    h.end()
    ll.configure()
    h = Sess("CED bp %s" % CED_REC, term="xterm")
    h.keys(F2)
    T = h.text()
    arow("C1", "F2 opens a menu of three: Explain the selected element, Ask the AI about this record, Undo the AI's last change", "Explain the selected element" in T and "Ask the AI about this record" in T and "Undo the AI's last change" in T, T[-600:])
    h.keys(ESC)
    n0 = len(fm.log)
    T = ced_ask(h, "raise the size [[ced_ok]]")
    arow("C2", "Ask: the preview shows the record as indented JSON, one element to a line, and the request; Send and Cancel; nothing sent", "This will be sent to anthropic" in T and "who is using CED" in T
         and '"size": 3' in T and '"name": "widget"' in T and "raise the size [[ced_ok]]" in T and len(fm.log) == n0, T[-1400:])
    h.keys("s")
    T = wait_popup(h)
    arow("C3", "the answer is a diff of the text with Accept and Reject", '- "size": 3' in T and '+ "size": 4' in T and "[ Accept ]" in T, T[-900:])
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    T = h.text()
    arow("C4", "Accept: the table shows size 4 and the record is marked changed", re.search(r"size\s+number\s+4", T) is not None and T.split("\n")[0].rstrip().endswith("*"), T[:300])
    arow("C4b", "...and the disk is untouched: the record still says 3", '"size":3' in rec(CED_REC), rec(CED_REC)[-200:])
    h.keys(F2)
    h.keys("u")
    time.sleep(0.8)
    arow("C5", "Undo the AI's last change: the table shows size 3 again", re.search(r"size\s+number\s+3", h.text()) is not None, h.text()[:300])
    ced_ask(h, "break it [[ced_bad]]")
    h.keys("s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    T = h.text()
    arow("C6", "Accept of a change that leaves invalid JSON is refused: the table still shows size 3 and the message says so", re.search(r"size\s+number\s+3", T) is not None and ai.msg(11677)[:30] in T, T[:300] + T[-300:])
    h.keys("\x1bOB")                     # xterm's Down (the session is TERM xterm here)
    n1 = len(fm.log)
    h.keys(F2)
    h.keys("e")
    T = h.text()
    arow("C7", "Explain the selected element: the preview has the element and its path in the request", "This will be sent to anthropic" in T and "Explain this part of the record" in T and len(fm.log) == n1, T[-900:])
    h.keys(RET)
    h.end()
    make_records()
    h = Sess("CED bp %s" % CED_REC, term="xterm")
    ced_ask(h, "raise the size [[ced_ok]]")
    h.keys("s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.keys("\x13")
    time.sleep(1.0)
    arow("C4c", "Ctrl-S saves the AI's change, as ever: the disk now says 4", '"size":4' in rec(CED_REC), rec(CED_REC)[-200:])
    h.end()


def sec_dbg():
    say("\n--- the debugger")
    ll.configure(provider=False)
    h = Sess("RUN bp %s" % DBG_PROG, term="xterm")
    T = "\n".join(h.keys("ai", RET))
    arow("D0", "no provider: ai is not the debugger's (a format error), nothing is previewed", "This will be sent" not in T and "debug" in T, T[-300:])
    h.end()
    ll.configure()
    fm = ai.STATE["fm"]
    h = Sess("RUN bp %s" % DBG_PROG, term="xterm")
    n0, a0 = len(fm.log), ai.audit_off()
    T = "\n".join(h.keys("ai what is y [[sayonly]]", RET))
    arow("D1", "ai: the preview names the program and line, the source round the stop and the request; nothing sent yet", "This will be sent to anthropic" in T and "who is using debugger" in T
         and DBG_PROG in T and "debug" in T and "what is y [[sayonly]]" in T and len(fm.log) == n0, T[-1400:])
    h.keys("s")
    T = wait_popup(h)
    rq = requests()
    pr = ai.prompt_of(rq[-1][2]) if len(rq) > n0 else ""
    rl = ai.req_lines(ai.audit_new(a0))
    arow("D2", "Send: ONE request whose prompt has the stop and the source lines (x = 5, debug), ONE audit line, and the answer is words with Close", len(fm.log) == n0 + 1 and "x = 5" in pr and "debug" in pr
         and len(rl) == 1 and "[ Close ]" in T, repr((len(fm.log) - n0, pr[-300:], rl)))
    h.keys(RET)
    time.sleep(0.6)
    h.s.settle(0.6)
    L = h.lines()
    arow("D3", "the popup is gone and the debugger's screen is whole: the source with its line numbers, the command line on the last row", any(re.match(r"^\s*3:\s+debug", l) for l in L) and L[-1].startswith(">"), "\n".join(L[:6] + L[-4:]))
    L = h.keys("/x", RET)
    arow("D3b", "...and it goes on working: /x shows the variable", any("5" in l for l in L[-9:-1]), "\n".join(L[-9:]))
    h.keys("r", RET)
    time.sleep(1.5)
    h.s.settle(0.6)
    n1 = len(fm.log)
    T = "\n".join(h.keys("ai again [[sayonly]]", RET))
    arow("D4", "the SECOND stop of the program: ai works there too (the setting lives in the debugger's common, not in a variable of the first call), the preview is shown and nothing is sent", "This will be sent to anthropic" in T
         and "again [[sayonly]]" in T and len(fm.log) == n1, T[-700:])
    h.keys(RET)
    h.end()


def main():
    mutant = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--mutant=")), None)
    if mutant is not None and mutant not in MUTANTS:
        bail("usage: sandbox-ai-apps-solo.py <dir> [--build] [--mutant=%s]" % "|".join(MUTANTS))
    try:
        sh.start_sandbox()
        sh.arrange("terminal")
        ai.setup_ai(None)
        setup_apps(mutant)
        ll.configure()
        make_records()
        make_debug_program()
        if mutant is None:
            sec_ide_off()
            sec_ide()
            sec_sed()
            sec_ced()
            sec_dbg()
        else:
            {"ide": sec_ide, "sed": sec_sed, "ced": sec_ced, "dbg": sec_dbg}[MUTANT_SECTIONS[mutant]]()
    finally:
        ai.teardown_ai()
        sh.teardown()
    say("\nsandbox-ai-apps-solo: %d passed, %d failed" % (sh.passed, sh.failed))
    if mutant is not None:
        want = sorted(set(MUTANTS[mutant][3]))
        got = sorted({re.match(r"[ISCD]\d+", i).group(0) for i in FAILED_IDS if re.match(r"[ISCD]\d+", i)})
        ok = want == got
        say("sandbox-ai-apps-solo: MUTANT %s: the rows that failed are %s; they had to be exactly %s -> %s" % (mutant, got, want, "KILLED BY ITS OWN ROWS" if ok else "NOT AS EXPECTED"))
        return 0 if ok else 1
    return 0 if sh.failed == 0 and sh.passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
