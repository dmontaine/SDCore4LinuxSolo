#!/usr/bin/env python3
#
# sandbox-ai-apps-solo.py - the AI in the IDE, SED, CED and the debugger (AI line stages 2 and 3), driven on a pseudo-terminal on a private SD Core Solo for Linux
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
#   I3-I7   Enter in the AI entry shows the preview (the text being worked on and the request; SD's own instruction is sent and not shown), Cancel the default; Send makes ONE request
#           and the kernel's one audit line; the edit is a diff; Reject leaves the buffer; Accept changes the buffer (not the disk) and one Ctrl-Z takes it back
#   I9      an edit set that does not fit is ignored whole and said so
#   S0-S7   the verb SED, which is the IDE's editor by itself: no Tools menu and no files pane; AI off: no AI menu, no AI> row; AI on: the AI menu and the AI> row; the preview, Cancel,
#           Send, the diff, Accept (buffer, not disk), ONE Ctrl-Z, and Ctrl-S writes what was accepted
#   C0-C7   CED: F2 does nothing with the AI off; on, a menu of three; the preview shows the record as indented JSON; the diff; Accept changes the record (not the disk); Ctrl-S saves;
#           an edit that would leave invalid JSON is ignored; the AI's last change is undone from the menu; explain the selected element
#   D0-D4   the debugger: ai is not a command with the AI off; on, ai shows the request in the preview (the program, the stack and the source round the stop are sent: D2 reads them where
#           they arrive); Send answers in words; the popup goes and the debugger's screen is whole and still works; the SECOND stop of the program has the command too
# NOT HELD: the end of the input during the wait, a record over 24000 bytes, the debugger in line mode and in a phantom, a real provider, Follow up in these apps (Core's C8, D5).
#
# START-HISTORY:
# 24 Oct 26 dm  New (Solo carry 17; the debugger rows with carry 18).
# 11 Nov 26 dm  Brought to the carry of 10 Nov from SD Core.  THE PROGRAM gpl.bp/sed IS GONE (Core's S.184 stage 7: the verb SED runs the IDE as the editor by itself), so the suite
#               stopped with FileNotFoundError before its first row.  REMOVED: the old SED rows S0-S9 (SED's own Tools menu with Ask the AI... and Explain the selection, the request typed
#               on SED's message row, Explain with and without a mark, Esc . as the mark) and the mutant sed-saves: the program they drove does not exist.  In their place S0-S7 start the
#               IDE as `SED bp <record>` and ask through the IDE's AI entry, as Core's sandbox-ide-alone.py starts it.  KEYS: the boxes change with F6 (Tab indents in the editor, Core's
#               S.176), so focus_entry and the way back to the editor press F6.  PREVIEWS (Core's S.175): SD's own instruction ("who is using IDE / CED / debugger") is sent and NOT
#               shown, so I3, C2 and D1 want it absent from the preview; I4 and D2 still read it where it arrives.  The debugger's screen is Core's S.98 H1 one: D3 reads the command
#               line on row 39 and the key row on row 42, D3b looks for the answer from the echo of the command on (both as Core's sandbox-ai-apps.py).  CED's AI code moved from
#               ced_edit to ced_core: the mutant ced-invalid-accepted is made there; the mutant ced-saves is REMOVED (its one-line change called save.record, which is ced_edit's and
#               not ced_core's; C4b still holds that Accept does not write).  The mutants were NOT run on 11 Nov 26.
# END-HISTORY
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
PROGS = ("sl_form", "tk_ai", "ide", "ced_core", "ced_edit", "debug")       # 11 Nov 26: no sed (the verb runs ide); ced_core holds CED's AI code now
DBG_PROG = "zzaid" + RUN                 # x = 5 / y = 'abc' / debug / crt 'AFTER-DEBUG' / debug / crt 'AFTER-TWO' / end   (compiled DEBUGGING; two stops)
FAILED_IDS = []
DOWN, RIGHT, TAB, RET, ESC = "\x1b[B", "\x1b[C", "\t", "\r", "\x1b"      # a Solo session is not in application cursor-key mode: the keys are ESC [ B / C (sandbox-home-solo.py KEYS), not ESC O B / C as in Core's harness
F10, F2, F7 = "\x1b[21~", "\x1bOQ", "\x1b[18~"
F6 = "\x1b[17~"                          # 11 Nov 26: the next box (Core's S.176); Tab indents in the IDE's editor
CTRL_Z, CTRL_S = "\x1a", "\x13"


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
    # (11 Nov 26: sed-saves and ced-saves are gone, see the history; ced-invalid-accepted is made in ced_core, where CED's AI code is now)
    "ced-invalid-accepted": ("ced_core", "   if ai.bad then\n      message.text = sysmsg(11677)\n      return\n   end\n", "   if ai.bad then\n      ai.y = jparse('{}')\n   end\n", ["C6", "C7"]),
    "dbg-no-source": ("debug", "   for ai.q = ai.first to ai.last\n", "   for ai.q = ai.first to ai.first - 1\n", ["D2"]),   # (D2 reads the request at the fake; D1's preview shows only the first eight lines of the page)
}
MUTANT_SECTIONS = {"ide-edit-by-enter": "ide", "ced-invalid-accepted": "ced", "dbg-no-source": "dbg"}


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
    # 11 Nov 26: the bar is File Edit Go Search Build View Tools AI Help (Edit since Core's S.180, Tools since its S.75 DV10; started as SED there is no Tools)
    return re.search(r"File\s+Edit\s+Go\s+Search\s+Build\s+View\s+(Tools\s+)?AI\s+Help", h.lines()[0]) is not None and "AI>" in h.text()


def status_rows(h):
    """The status line is above the foot's border and the key row; the rows from the fifth from the bottom on are read so that a foot of another height still shows it."""
    return h.lines()[-5:]


def focus_entry(h):
    """The AI entry is a stop of the F6 ring; the status line names the box that has the focus ([AI])."""
    for _ in range(6):
        if any("[AI]" in l for l in status_rows(h)):
            return True
        h.keys(F6)
    return any("[AI]" in l for l in status_rows(h))


def focus_editor(h):
    for _ in range(6):
        if any("[Edit" in l for l in status_rows(h)):
            return True
        h.keys(F6)
    return any("[Edit" in l for l in status_rows(h))


def sec_ide_off():
    say("\n--- the IDE, the AI off")
    ll.configure(provider=False)
    h = Sess("IDE bp %s" % OK_REC)
    L = h.lines()
    arow("I0", "no provider: the menu bar is File Edit Go Search Build View (Tools) Help with no AI menu, and there is no AI> row", re.search(r"File\s+Edit\s+Go\s+Search\s+Build\s+View\s+(Tools\s+)?Help", L[0]) is not None
         and "AI" not in L[0] and "AI>" not in h.text(), repr(L[0][:80]))
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
    arow("I3", "Enter shows the preview (the provider, the record's lines, the request; NOT SD's own instruction, Core's S.175), Send and Cancel, and sends nothing",
         "This will be sent to anthropic" in T and "who is using IDE" not in T and "crt 'hello'" in T and "make the greeting longer [[edit_ok]]" in T and "Send" in T and "Cancel" in T and len(fm.log) == n0, T[-1200:])
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
    focus_editor(h)                      # F6 round the ring back to the editor (11 Nov 26: it was Tab)
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
    """11 Nov 26: SED is the IDE's editor by itself, so the request goes into the IDE's AI entry (F6 to it), and Enter shows the preview."""
    focus_entry(h)
    h.keys(request)
    return "\n".join(h.keys(RET))


def sec_sed():
    say("\n--- the verb SED: the IDE's editor by itself")
    fm = ai.STATE["fm"]
    ll.configure(provider=False)
    h = Sess("SED bp %s" % OK_REC)
    L = h.lines()
    arow("S0", "no provider: SED brings up the IDE's menu bar with the record in the editor, no Tools menu, no AI menu and no AI> row", re.search(r"File\s+Edit\s+Go\s+Search\s+Build\s+View\s+Help", L[0]) is not None
         and "Tools" not in L[0] and "AI" not in L[0] and "crt 'hello'" in h.text() and "AI>" not in h.text(), repr(L[0][:90]))
    h.end()
    ll.configure()
    h = Sess("SED bp %s" % OK_REC)
    L = h.lines()
    arow("S1", "the AI on: the AI menu is before Help (still no Tools menu) and there is an AI> row under the editor", re.search(r"File\s+Edit\s+Go\s+Search\s+Build\s+View\s+AI\s+Help", L[0]) is not None
         and "AI>" in h.text() and "crt 'hello'" in h.text(), repr(L[0][:90]))
    arow("S1b", "there is no files pane: the list of the account's files is not on the screen", not any(l[:30].strip("| ").startswith("bp.out") for l in L), "\n".join(l[:30] for l in L[:8]))
    n0, a0 = len(fm.log), ai.audit_off()
    T = sed_ask(h, "make the greeting longer [[edit_ok]]")
    arow("S2", "Enter on the request shows the preview (the provider, the record's lines, the request; not SD's own instruction), Send and Cancel, and sends nothing",
         "This will be sent to anthropic" in T and "who is using" not in T and "crt 'hello'" in T and "x = 1" in T and "make the greeting longer [[edit_ok]]" in T and "Send" in T and "Cancel" in T and len(fm.log) == n0, T[-1500:])
    h.keys(RET)
    arow("S3", "Enter on the default button is Cancel: nothing was sent", len(fm.log) == n0 and not ai.req_lines(ai.audit_new(a0)), "")
    h.end()                              # a new session: the AI entry still holds the request's text
    h = Sess("SED bp %s" % OK_REC)
    n0, a0 = len(fm.log), ai.audit_off()
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
    h.end()
    h = Sess("SED bp %s" % OK_REC)
    sed_ask(h, "longer [[edit_ok]]")
    h.keys("s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    arow("S5", "Accept: the buffer shows the new line, the disk does not have it", "crt 'hello world'" in h.text() and "hello world" not in rec(OK_REC), h.text()[-600:])
    focus_editor(h)
    h.keys(CTRL_Z)
    time.sleep(0.8)
    h.s.settle(0.5)
    arow("S6", "ONE Ctrl-Z takes the change back: the old line is in the buffer", "crt 'hello world'" not in h.text() and "crt 'hello'" in h.text(), h.text()[-500:])
    h.end()
    h = Sess("SED bp %s" % OK_REC)
    sed_ask(h, "longer [[edit_ok]]")
    h.keys("s")
    wait_popup(h)
    h.keys("a")
    time.sleep(1.0)
    h.s.settle(0.6)
    focus_editor(h)
    h.keys(CTRL_S)
    time.sleep(1.0)
    h.s.settle(0.5)
    arow("S7", "Ctrl-S in the editor writes what was accepted: the disk now has the new line (the person's save, not the AI's)", "crt 'hello world'" in rec(OK_REC), rec(OK_REC)[-200:])
    h.end()
    make_records()                       # the record as it was, for whatever runs next


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
    arow("C2", "Ask: the preview shows the record as indented JSON, one element to a line, and the request; Send and Cancel; nothing sent", "This will be sent to anthropic" in T and "who is using CED" not in T
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
    arow("D1", "ai: the preview shows the request and NOT SD's instruction (the program, line and source are sent: D2 reads the request); nothing sent yet",
         "This will be sent to anthropic" in T and "who is using debugger" not in T and "what is y [[sayonly]]" in T and len(fm.log) == n0, T[-1400:])
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
    arow("D3", "the popup is gone and the debugger's screen is whole: the source with its line numbers, the command line on row 39, the key row at the foot", any(re.match(r"^[ *>]\s*3:\s+debug", l) for l in L)
         and L[39].startswith(">") and L[42].startswith("F1 help"), "\n".join(L[:6] + L[38:43]))
    L = h.keys("/x", RET)
    ix = max([i for i, l in enumerate(L) if "/x" in l] or [-1])         # the answer is looked for from the echo of the command on, wherever the display puts it (Core's row)
    arow("D3b", "...and it goes on working: /x shows the variable", ix >= 0 and any("5" in l for l in L[ix:]), "\n".join(l for l in L if l.strip()))
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
