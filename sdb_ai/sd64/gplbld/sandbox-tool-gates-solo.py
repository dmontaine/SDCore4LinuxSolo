#!/usr/bin/env python3
#
# sandbox-tool-gates-solo.py - the gates page, TOOL.GATES, driven on a PSEUDO-TERMINAL on a private SD Core for Linux Solo (Solo carry 20b; Core has two pages under this name, the
# administrator's matrix (sandbox-tool-gates.py) and the holder's read-only view (sandbox-tool-mygates.py); Solo has one account and one page with two modes).  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-tool-gates-solo.py <dir> [--build] [--mutant=NAME]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent; keep the path SHORT).  Exit 0 every row passed, 1 a row
# failed, 2 it could not run.  With --mutant=NAME one change is made to the SANDBOX'S OWN COPY of the page and exit 0 means the rows that had to fail failed and no others (MUTANTS).
#
# WHAT RUNS.  Two kinds of session of the one account, sduser, on pseudo-terminals: a PLAIN one (the holder's read-only view) and one made administrator by typing ADMIN and the
# administrator password at the prompt.  The page runs the REAL set.os.access, set.net.access and set.ai verbs.  The AI rows run the real AI helper (gplbld/sd-ai, served by
# ai-runner.py) through sandbox-ai-solo.py's setup, with the fake provider that suite starts; the page never sends anything to it.
#
# THE INSTRUMENT.  Every outcome is read from SD, not from the page: the register record on the disk (fields 7, 8 and 15), `set.ai`'s reading form (the helper's own gate), the
# audit file, and a second, new session (which loads what the register holds at its sign-on).  A page that drew a cell, or said it ran a command, is not taken to have done it.
#
#   G0   controls: the evidence reads what it claims to (the register has its fields, the verbs say all off, the helper answers)
#   G1   the holder's view (a plain session, the helper not running): the rows, the columns, the sentences, Enter refused with no box, no audit line, the key bar without Enter
#   G2   the administrator's view: one audit line, the Register column, the key bar with Enter, 'Enter runs: ...'
#   G3   Shell ON through the box: Esc, a wrong word and the right word; the register on the disk; the audit line; the page; a NEW session loads it at sign-on
#   G4   Shell off again: no word asked; the register; the audit line
#   G5   OS.EXECUTE and Remote files: ON with their words, off again, each changes its own field and no other
#   G6   the page does not change by itself: a change by the verb shows after F5 and not before
#   G7   AI (the helper running): ON with its word, off again, the helper's own reading form agrees; the helper stopped: the cell shows it and Enter says so
#   G8   F5, F1, a click on the [?], a click on a row; a window under 140 by 43 gets no page; the page ends when its input ends
# NOT HELD: the first sign-on after a change on a REAL install, the help text itself (sandbox-docs.py's job on Core; here the words of the record), a real provider.
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


sh = _load("sandbox_home_solo_for_toolgates", "sandbox-home-solo.py")
ai = _load("sandbox_ai_solo_for_toolgates", "sandbox-ai-solo.py")
# sandbox-ai-solo.py loaded a copy of sandbox-home-solo.py of its own, with a BOX and a SYS nobody sets: point it at THIS suite's copy, which start_sandbox() fills in
ai.sh = sh
for _n in ("say", "has", "put", "bail", "dump", "plain", "adm", "H"):
    setattr(ai, _n, getattr(sh, _n))
say, row, bail, has, dump, H, adm = sh.say, sh.row, sh.bail, sh.has, sh.dump, sh.H, sh.adm

FAILED_IDS = []
MUTANT = None

MUTANTS = {
    # name: (old text of the sandbox's tool_gates, new text, the row ids that must fail and no others, the last section run)
    "no-typed-name": ("      typed = gids<k>\n", "      typed = ''\n", ["G3"], "G3"),
    "toggle-by-session": ("   on.now = (gset<k> = 1)\n", "   on.now = (gnow<k> = 1)\n", ["G4"], "G4"),
    "columns-swapped": ("            gset<2> = (if upcase(trim(acc.rec<ACC$OS.EXEC>)) = 'YES' then 1 else 0)\n            gset<3> = (if upcase(trim(acc.rec<ACC$NET>)) = 'YES' then 1 else 0)\n",
                        "            gset<3> = (if upcase(trim(acc.rec<ACC$OS.EXEC>)) = 'YES' then 1 else 0)\n            gset<2> = (if upcase(trim(acc.rec<ACC$NET>)) = 'YES' then 1 else 0)\n", ["G5"], "G5"),
    "holder-may-try": ("   if not(kernel(K$ADMINISTRATOR, -1)) then\n      msg = 'Only the administrator can change a gate: type admin, then open this page again'\n      return\n   end\n", "", ["G1"], "G1"),
}


def arow(rid, name, ok, detail=""):
    """A row with an id (G3 ...): the mutant mode compares the ids that failed with the ids that had to."""
    row("%s %s" % (rid, name), ok, detail)
    if not ok:
        FAILED_IDS.append(re.match(r"G\d+", rid).group(0))


def norm(t):
    return re.sub(r"[|\s]+", " ", t)


def st(h):
    return h.line(40)


def audit_off():
    path = os.path.join(sh.SYS, "audit")
    try:
        if not os.path.exists(path):
            with open(path, "ab"):
                pass
        return os.path.getsize(path)
    except OSError:
        return None


def audit_new(off):
    if off is None:
        return None
    try:
        with open(os.path.join(sh.SYS, "audit"), "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def reg_fields():
    """(sh, os, net) as the register record on the disk holds them: 'yes', 'no' or '' (fields 7, 8 and 15)."""
    with open(sh.REG) as f:
        lines = f.read().split("\n")
    lines += [""] * (15 - len(lines))
    return tuple(lines[i].strip().lower() for i in (6, 7, 14))


def reg_on():
    return tuple(v == "yes" for v in reg_fields())


def gate_word():
    """The AI helper's own gate, from set.ai's reading form: 'on', 'off' or None when it did not answer."""
    out = adm("set.ai")
    for ln in out:
        m = re.match(r"^\s+gate: (on|off)$", ln)
        if m:
            return m.group(1)
    return None


class Page:
    """A session on tool.gates on a pseudo-terminal: the holder's (admin=False) or the administrator's (admin=True)."""

    def __init__(self, admin, cols=140, rows=43):
        self.admin = admin
        self.h = H(admin=admin, cols=cols, rows=rows)
        self.h.typed("tool.gates\r", idle=3.5)

    def text(self):
        return self.h.text()

    def line(self, n):
        return self.h.line(n)

    def key(self, name, idle=0.6):
        if len(name) == 1:                         # a letter is typed; the harness's key table has the named keys only
            self.h.typed(name, idle=idle)
        else:
            self.h.key(name, idle=idle)

    def typed(self, s, idle=0.9):
        self.h.typed(s, idle=idle)

    def idle(self, seconds):
        self.h.s.settle(seconds)

    def gates(self):
        out = []
        for n in range(3, 7):
            ln = self.line(n)
            out.append(dict(name=ln[3:19].strip(), now=ln[19:33].strip(), reg=ln[33:43].strip(), dflt=ln[43:57].strip(), beyond=ln[57:68].strip(), when=ln[68:].strip().rstrip("|").strip()))
        return out

    def detail(self):
        return norm(" ".join(self.line(n)[3:137] for n in range(13, 25)))

    def bar(self):
        return norm(" ".join(self.line(n) for n in range(41, 43)))

    def end(self):
        self.h.end()

    def quit(self):
        self.key("ctrl-q", idle=1.5)
        self.h.end()


def run_gate(p, word, expect_typed=True):
    """Enter on the row under the cursor, Run, the word (when one is asked for): the page's own keys."""
    p.key("enter", 1.5)
    p.typed("r", 1.3)
    if expect_typed:
        p.typed(word + "\r", 2.5)
    else:
        p.idle(2.5)


def setup_gates():
    shutil.copyfile(os.path.join(TREE, "sdsys", "gpl.bp", "tool_gates"), os.path.join(sh.SYS, "gpl.bp", "tool_gates"))
    out = adm("BASIC gpl.bp tool_gates")
    if not has(out, r"^Compiled 1 program\(s\) with no errors"):
        bail("tool_gates did not compile in the sandbox:\n" + "\n".join(out[-8:]))


def mutate(name):
    old, new, _kills, _last = MUTANTS[name]
    path = os.path.join(sh.SYS, "gpl.bp", "tool_gates")
    src = open(path, encoding="utf-8", errors="replace").read()
    if src.count(old) != 1:
        bail("mutant %s: the text to change is found %d times, not once" % (name, src.count(old)))
    sh.put(path, src.replace(old, new))
    out = adm("BASIC gpl.bp tool_gates")
    if not has(out, r"^Compiled 1 program\(s\) with no errors"):
        bail("the mutant page did not compile:\n" + "\n".join(out[-8:]))


def all_off():
    """The delivered state: every gate off (the register through the verbs, the AI's gate through set.ai)."""
    adm("set.os.access sh off", "set.os.access os off", "set.net.access off", "set.ai gate off")


def section_g0():
    say("\n--- G0: controls")
    all_off()
    f = reg_fields()
    first = open(sh.REG).read().split("\n")[0]
    arow("G0a", "the register record is there (its first line is the account's directory) and all three gates are off (blank or no): the instrument reads the disk", first.endswith("sduser") and all(v != "yes" for v in f), repr((first, f)))
    out = adm("set.os.access", "set.net.access")
    T = " ".join(out)
    arow("G0b", "the verbs say the same: SH no, OS.EXECUTE no, NET no", re.search(r"has SH no, OS\.EXECUTE no", T) is not None and re.search(r"has NET no", T) is not None, T[:300])
    arow("G0c", "the AI helper answers set.ai and its gate is off (as delivered)", gate_word() == "off", repr(adm("set.ai")[:6]))


def section_g1():
    say("\n--- G1: the holder's view (a plain session, the AI helper not running)")
    ai.stop_runner()
    a0 = audit_off()
    p = Page(admin=False)
    T = p.text()
    if "The row under the cursor" not in T:
        dump(p.h)
        bail("tool.gates never drew its page in a plain session, so no row below can be believed")
    G = p.gates()
    arow("G1a", "three boxes and a [?]; the headings; four gate rows in order: Shell, OS.EXECUTE, Remote files, AI",
         all(w in T for w in ("Gates of this account", "The row under the cursor", "Where this comes from")) and "[?]" in p.line(2)
         and all(w in p.line(2) for w in ("Gate", "This session", "Register", "As delivered", "Beyond SD", "A change reaches you")) and [g["name"] for g in G] == ["Shell", "OS.EXECUTE", "Remote files", "AI"], repr(G))
    arow("G1b", "THIS SESSION: Shell, OS.EXECUTE and Remote files are off (the kernel's answer for a session with everything off); AI cannot be read (-) with the helper stopped",
         [g["now"] for g in G] == ["off", "off", "off", "-"], repr([g["now"] for g in G]))
    arow("G1c", "REGISTER is shown to the administrator only: a dash for the three gates of the register, a dash for the AI that cannot be read", [g["reg"] for g in G] == ["-", "-", "-", "-"], repr([g["reg"] for g in G]))
    arow("G1d", "as delivered every gate is off, every gate reaches beyond SD, and the page says when a change reaches you (next sign-on three times, at the next request for the AI)",
         all(g["dflt"] == "off" and g["beyond"] == "yes" for g in G) and [g["when"] for g in G] == ["next sign-on", "next sign-on", "next sign-on", "at the next request"], repr(G))
    s1, s2, s3 = norm(p.line(8)), norm(p.line(9)), norm(p.line(10))
    arow("G1e", "the summary: whose session, how many gates are on (none), that only the administrator can change a gate, that the Register column is the administrator's",
         "0 of 4 gates are on for this session" in s1 and "Only the administrator can change a gate (type admin). Nothing on this page can." in s2 and "shown to the administrator only" in s3, repr((s1, s2, s3)))
    D = p.detail()
    arow("G1f", "the row under the cursor (Shell): off for this session, what it cannot do and what it still can, and the command the ADMINISTRATOR would use",
         "Shell [sh] - off for this session. You cannot use the SH verb and !" in D and "With it off you can still do everything inside SD" in D and "The administrator changes it with: set.os.access sh on" in D
         and "This gate reaches BEYOND SD" in D, D[:400])
    p.key("down", 0.6)
    D = p.detail()
    arow("G1g", "Down moves the cursor: OS.EXECUTE is explained, with its own command", "OS.EXECUTE [os] - off for this session" in D and "set.os.access os on" in D and "SPOOLER" in D, D[:300])
    p.key("down", 0.6)
    p.key("down", 0.6)
    D = p.detail()
    arow("G1h", "the AI row with the helper stopped says it cannot be read, why, and that it is off as delivered", "AI [ai] - cannot be read" in D and "No answer from the AI helper" in D and "The AI is off as delivered" in D, D[:400])
    p.key("home", 0.6)
    arow("G1i", "Home goes back to the first gate", "Shell [sh]" in p.detail(), p.detail()[:100])
    bar = p.bar()
    arow("G1j", "the key bar offers help, refresh and quit and does NOT offer Enter 'change' (the key is not added for a session that is not the administrator)",
         all(w in bar.lower() for w in ("help", "refresh", "quit")) and "change" not in bar.lower(), bar)
    arow("G1k", "opening the page as a holder writes no audit line at all (it changes nothing and has nothing to record)", (audit_new(a0) or "") == "" or "tool start" not in (audit_new(a0) or ""), repr(audit_new(a0)))
    a1 = audit_off()
    f0 = reg_fields()
    p.key("enter", 1.2)
    T = norm(p.text())
    arow("G1", "Enter: the status line says only the administrator can change a gate, NO box opens, the register is as it was and no audit line is written",
         "Only the administrator can change a gate" in st(p.h) and "this will run" not in T.lower() and "Run this command" not in T and reg_fields() == f0 and (audit_new(a1) or "") == "", repr((st(p.h), audit_new(a1), reg_fields())))
    p.quit()


def section_g2():
    say("\n--- G2: the administrator's view")
    ai.start_runner()
    all_off()
    a0 = audit_off()
    p = Page(admin=True)
    T = p.text()
    if "The row under the cursor" not in T:
        dump(p.h)
        bail("tool.gates never drew its page in the administrator's session, so no row below can be believed")
    new = audit_new(a0) or ""
    arow("G2a", "opening the page writes one audit line, 'tool start app=tool.gates', and no other", len(re.findall(r"tool start app=tool\.gates$", new, re.M)) == 1 and "tool run" not in new, repr(new[-200:]))
    G = p.gates()
    arow("G2b", "THIS SESSION off, off, off for the three gates of the register; the AI's gate off (the helper answers: it is the helper's own setting)", [g["now"] for g in G] == ["off", "off", "off", "off"], repr(G))
    arow("G2c", "REGISTER is shown to the administrator: off for every gate (the three register fields, and the helper's gate for the AI)", [g["reg"] for g in G] == ["off", "off", "off", "off"], repr(G))
    s2, s3 = norm(p.line(9)), norm(p.line(10))
    arow("G2d", "the summary says who can change a gate and what the Register column is",
         "You are the administrator: Enter turns the gate on the cursor's row ON or off" in s2 and "The Register column is what the next sign-on will load" in s3, repr((s2, s3)))
    D = p.detail()
    arow("G2e", "the row under the cursor says what Enter runs: set.os.access sh on", "Enter runs: set.os.access sh on" in D, D[:300])
    bar = p.bar().lower()
    arow("G2f", "the key bar now offers Enter 'change'", "change" in bar, bar)
    return p


def section_g3(p):
    say("\n--- G3: Shell ON through the box")
    a0 = audit_off()
    f0 = reg_fields()
    p.key("enter", 1.8)
    T = norm(p.text())
    arow("G3a", "Enter shows the exact command, what ON allows, that a gate off as delivered is being turned ON, that the name has to be typed and when a change reaches you",
         "set.os.access sh on" in T and "ON - Shell: this account will be able to use the SH verb" in T and "A gate that is off as delivered is being turned ON" in T and "its name has to be typed" in T
         and "A change reaches you: next sign-on" in T, T[-900:])
    p.key("esc", 1.2)
    arow("G3b", "Esc runs nothing: the status line says so, the register is as it was and the audit trail has no line", "nothing was run" in st(p.h) and reg_fields() == f0 and (audit_new(a0) or "") == "", repr((st(p.h), reg_fields(), audit_new(a0))))
    p.key("enter", 1.5)
    p.typed("r", 1.3)
    p.typed("xx\r", 1.8)
    arow("G3c", "Run and a word that is not the gate's name runs nothing: the status line names the word asked for, the register is as it was, no audit line",
         "what was typed is not sh" in st(p.h) and reg_fields() == f0 and "set.os.access" not in (audit_new(a0) or ""), repr((st(p.h), reg_fields(), audit_new(a0))))
    if MUTANT == "no-typed-name":                  # the mutant asked for no word and ran the command at Run: what follows depends on the register being as it was
        return
    run_gate(p, "sh")
    new = audit_new(a0) or ""
    arow("G3d", "the word typed: the register holds SH yes and the other two fields are as they were, and the verb wrote its audit line (set.os.access sh on account=sduser)",
         reg_fields() == ("yes",) + f0[1:] and len(re.findall(r"set\.os\.access sh on account=sduser$", new, re.M)) == 1, repr((reg_fields(), new[-200:])))
    arow("G3e", "the status line is the verb's own last line: SH yes, OS.EXECUTE no", re.search(r"has SH yes, OS\.EXECUTE no", st(p.h)) is not None, st(p.h))
    G = p.gates()
    D = p.detail()
    arow("G3f", "the page reads again: REGISTER on for Shell, THIS SESSION still off (the gates are loaded at sign-on), and the row says so",
         G[0]["reg"] == "ON" and G[0]["now"] == "off" and "The register says ON and this session holds off: Shell reaches you next sign-on" in D and "Enter runs: set.os.access sh off" in D, repr((G[0], D[:300])))
    q = Page(admin=False)
    G2 = q.gates()
    arow("G3g", "a NEW session (a holder's) loaded it at its sign-on: THIS SESSION says ON for Shell and off for the others, and counts 1 of 4",
         G2[0]["now"] == "ON" and G2[1]["now"] == "off" and G2[2]["now"] == "off" and "1 of 4 gates are on for this session" in norm(q.line(8)), repr((G2, q.line(8))))
    q.quit()


def section_g4(p):
    say("\n--- G4: Shell off again")
    a0 = audit_off()
    p.key("enter", 1.8)
    T = norm(p.text())
    arow("G4a", "the box for turning a gate OFF: the command, what it will no longer be able to do, what it still can - and no name is asked for",
         "set.os.access sh off" in T and "OFF - Shell: this account will no longer be able to use the SH verb" in T and "It will still be able to do everything inside SD" in T and "its name has to be typed" not in T
         and "A gate that is off as delivered is being turned ON" not in T, T[-800:])
    p.typed("r", 2.5)
    new = audit_new(a0) or ""
    arow("G4", "Run: SH is off in the register again, the verb's audit line is there, the page shows REGISTER off, and no word was asked for",
         reg_on() == (False, False, False) and len(re.findall(r"set\.os\.access sh off account=sduser$", new, re.M)) == 1 and p.gates()[0]["reg"] == "off" and re.search(r"has SH no, OS\.EXECUTE no", st(p.h)) is not None,
         repr((reg_fields(), new[-160:], p.gates()[0], st(p.h))))


def section_g5(p):
    say("\n--- G5: OS.EXECUTE and Remote files")
    a0 = audit_off()
    p.key("down", 0.7)
    run_gate(p, "os")
    new = audit_new(a0) or ""
    arow("G5a", "OS.EXECUTE ON with its word 'os': field 8 only, the audit line, the page: REGISTER on for OS.EXECUTE and for nothing else",
         reg_on() == (False, True, False) and len(re.findall(r"set\.os\.access os on account=sduser$", new, re.M)) == 1 and [g["reg"] for g in p.gates()] == ["off", "ON", "off", "off"], repr((reg_fields(), p.gates(), new[-160:])))
    p.key("enter", 1.5)
    p.typed("r", 2.5)
    arow("G5b", "OS.EXECUTE off again: field 8 is no, nothing else moved", reg_on() == (False, False, False) and p.gates()[1]["reg"] == "off", repr((reg_fields(), p.gates())))
    p.key("down", 0.7)
    a1 = audit_off()
    p.key("enter", 1.8)
    T = norm(p.text())
    arow("G5c", "Remote files: the box shows set.net.access on and asks for the word net", "set.net.access on" in T and "ON - Remote files: this account will be able to open a file on another SD server" in T and "its name has to be typed" in T, T[-700:])
    p.key("esc", 1.2)
    run_gate(p, "net")
    new = audit_new(a1) or ""
    arow("G5d", "Remote files ON: field 15 only, the audit line, the page: REGISTER on for Remote files and for nothing else",
         reg_on() == (False, False, True) and len(re.findall(r"set\.net\.access on account=sduser$", new, re.M)) == 1 and [g["reg"] for g in p.gates()] == ["off", "off", "ON", "off"]
         and re.search(r"has NET yes", st(p.h)) is not None, repr((reg_fields(), p.gates(), new[-160:], st(p.h))))
    p.key("enter", 1.5)
    p.typed("r", 2.5)
    arow("G5e", "Remote files off again: all three fields off", reg_on() == (False, False, False) and p.gates()[2]["reg"] == "off", repr((reg_fields(), p.gates())))


def section_g6(p):
    say("\n--- G6: the page does not change by itself")
    p.key("home", 0.7)
    adm("set.os.access sh on")
    p.idle(4.0)
    arow("G6a", "the register was changed by the verb outside the page: the page still shows off (it reads when it is told to, not on a timer)", p.gates()[0]["reg"] == "off" and reg_on()[0], repr((p.gates()[0], reg_fields())))
    p.key("f5", 1.5)
    G = p.gates()
    arow("G6b", "F5 asks again: REGISTER on, THIS SESSION off, and the status line says so", G[0]["reg"] == "ON" and G[0]["now"] == "off" and "asked the system again" in st(p.h), repr((G[0], st(p.h))))
    adm("set.os.access sh off")
    p.key("f5", 1.5)
    arow("G6c", "and back: F5 shows REGISTER off", p.gates()[0]["reg"] == "off" and reg_on() == (False, False, False), repr((p.gates()[0], reg_fields())))


def section_g7(p):
    say("\n--- G7: the AI gate (the helper running)")
    p.key("end", 0.7)
    a0 = audit_off()
    arow("G7a", "the cursor is on the AI row: it is explained, with the tool.ai page named", "AI [ai] - off for this session" in p.detail() and "tool.ai" in p.detail() and "Enter runs: set.ai gate on" in p.detail(), p.detail()[:400])
    p.key("enter", 1.8)
    T = norm(p.text())
    arow("G7b", "Enter: the box shows set.ai gate on, the AI sentence (the text leaves this machine) and asks for the word ai",
         "set.ai gate on" in T and "ON - AI: this account will be able to use the ai verb" in T and "leaves this machine" in T and "its name has to be typed" in T, T[-800:])
    p.key("esc", 1.2)
    arow("G7c", "Esc: the helper's gate is as it was and the audit trail has no set.ai line", gate_word() == "off" and "set.ai" not in (audit_new(a0) or ""), repr((gate_word(), audit_new(a0))))
    run_gate(p, "ai")
    new = audit_new(a0) or ""
    arow("G7d", "the word typed: the helper's own reading form says gate: on, the kernel wrote 'set.ai gate=on', the page shows ON for the AI in both columns",
         gate_word() == "on" and len(re.findall(r"set\.ai gate=on$", new, re.M)) == 1 and p.gates()[3]["now"] == "ON" and p.gates()[3]["reg"] == "ON", repr((gate_word(), new[-160:], p.gates()[3])))
    p.key("enter", 1.5)
    p.typed("r", 2.5)
    arow("G7e", "off again: the helper says gate: off and the page shows off", gate_word() == "off" and p.gates()[3]["now"] == "off", repr((gate_word(), p.gates()[3])))
    ai.stop_runner()
    p.key("f5", 2.0)
    G = p.gates()
    arow("G7f", "the helper stopped: F5 shows a dash for the AI in both columns and the row says it cannot be read", G[3]["now"] == "-" and G[3]["reg"] == "-" and "AI [ai] - cannot be read" in p.detail(), repr((G[3], p.detail()[:200])))
    a1 = audit_off()
    p.key("enter", 1.5)
    T = norm(p.text())
    arow("G7g", "Enter on it says the helper could not be reached (message 11607), opens no box and writes no audit line", "The AI helper could not be reached" in st(p.h) and "Run this command" not in T and (audit_new(a1) or "") == "", repr((st(p.h), audit_new(a1))))
    ai.start_runner()


def section_g8(p):
    say("\n--- G8: F1, the mouse, a small window, an input that ends")
    p.key("f5", 2.0)
    p.h.click(30, 4)
    arow("G8a", "a click on a gate row puts the cursor there", "OS.EXECUTE [os]" in p.detail(), p.detail()[:120])
    p.h.click(135, 2)
    T = norm(p.text())
    words = ("switches", "chooses", "everything", "Documentation", "Close")       # single words that only the help box has: it is drawn over the middle of the page and wraps its text, so a phrase is cut by the rows behind it
    arow("G8b", "a click on the [?] shows the record tool.gates.page (the Solo build loads the help into sys/context.help): its title and words of its paragraphs", all(w in T for w in words) and "Help is not installed" not in T, T[-600:])
    p.key("esc", 1.0)
    p.key("f1", 1.2)
    T = norm(p.text())
    arow("G8c", "F1 shows the same record", all(w in T for w in words) and "Help is not installed" not in T, T[-600:])
    p.key("esc", 1.0)
    p.quit()
    h = H(admin=True, cols=100, rows=30)
    h.typed("tool.gates\r", idle=3.0)
    T = h.text()
    arow("G8d", "a window under 140 by 43 gets no page (the toolkit's one size check)", "The row under the cursor" not in T and "This session" not in T, T[-300:])
    h.end()
    # a terminal that is hung up (a window closed): the page must end on its own, not spin and wait to be killed
    h = H(admin=True)
    h.typed("tool.gates\r", idle=3.5)
    started = "The row under the cursor" in h.text()
    t0 = time.time()
    h.s.finish(limit=0.5)
    arow("G8e", "a page whose terminal is hung up ends by itself and is not killed (the null case: the page was on the screen first)", started and h.s.exited and not getattr(h.s, "killed", False),
         "started %s, exited %s, killed %s, %.1f s" % (started, h.s.exited, getattr(h.s, "killed", None), time.time() - t0))


def main():
    mutant = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--mutant=")), None)
    if mutant is not None and mutant not in MUTANTS:
        bail("usage: sandbox-tool-gates-solo.py <dir> [--build] [--mutant=%s]" % "|".join(MUTANTS))
    last = MUTANTS[mutant][3] if mutant else "G8"
    global MUTANT
    MUTANT = mutant
    order = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]

    def run(s):
        return mutant is None or order.index(s) <= order.index(last)

    try:
        sh.start_sandbox()
        sh.arrange("terminal")                       # a session starts at the prompt: the page is typed there
        ai.setup_ai(None)                            # the fake provider, the helper's runner, SD_AI_SOCKET and SD_AI_CTL (and setai / ai / tool_ai compiled)
        setup_gates()
        if mutant is not None:
            mutate(mutant)
            say("sandbox-tool-gates-solo: MUTANT %s: the rows that must fail, and nothing else: %s" % (mutant, ", ".join(MUTANTS[mutant][2])))
        if mutant is None:
            section_g0()
        else:
            all_off()
        section_g1()
        if run("G2"):
            p = section_g2()
            if run("G3"):
                section_g3(p)
            if run("G4"):
                section_g4(p)
            if run("G5"):
                section_g5(p)
            if mutant is None:
                section_g6(p)
                section_g7(p)
                section_g8(p)
            else:
                p.end()
        all_off()
    finally:
        ai.teardown_ai()
        sh.teardown()
    say("\nsandbox-tool-gates-solo: %d passed, %d failed" % (sh.passed, sh.failed))
    if mutant is not None:
        want = sorted(set(MUTANTS[mutant][2]))
        got = sorted(set(FAILED_IDS))
        ok = want == got
        say("sandbox-tool-gates-solo: MUTANT %s: the rows that failed are %s; they had to be exactly %s -> %s" % (mutant, got, want, "KILLED BY ITS OWN ROWS" if ok else "NOT AS EXPECTED"))
        return 0 if ok else 1
    return 0 if sh.failed == 0 and sh.passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
