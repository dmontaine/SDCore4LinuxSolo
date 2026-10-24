#!/usr/bin/env python3
"""test-toolgates-solo-units.py - the gates page, TOOL.GATES (`gpl.bp/tool_gates`), as invariants read off the source (Solo carry 20b of Core's S.75 A2).  Free: no install, no sudo, no sd.

    python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-toolgates-solo-units.py [--selftest]

Core has two pages under this name (the administrator's matrix of every registered account against every gate, test-toolgates-units.py, and the holder's read-only view, test-toolmygates-units.py);
Solo has one account and no modify.account, so it has ONE page with four rows (sh, os, net, ai) and two modes: it shows what the session may do to every session, and turns a gate ON or off through
the three verbs that own the gates (set.os.access, set.net.access, set.ai gate) for the administrator.  This file holds that page against the three verbs, keys.h and int$keys.h.

WHAT THIS IS, AND WHAT IT IS NOT.  It reads the page's BASIC as text, with comments removed.  ***IT RUNS NOTHING, SO IT CANNOT SAY THAT A GATE CHANGES***: that is `sandbox-tool-gates-solo.py`
(a private SD, plain and administrator sessions on pseudo-terminals, the register on the disk, the helper's own reading form and the audit file as the evidence).  What a text check is for: the
properties that make the page a FRONT END - it is open to every session but offers its keys to the administrator only, it reads the register for the administrator only, it asks and never tries, it
runs three commands through the one place that runs commands each only after the box was answered Run, it asks for the gate's name before turning a gate ON, it decides ON or off from the REGISTER
and not from the session, and its table of words is the verbs' own - which are mostly ORDER and ABSENCE, and an edit that moves one still compiles.

--selftest breaks each invariant in the way an edit plausibly would and requires a check to notice; a mutant that nothing catches is a failure of the self-test.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SDSYS = os.path.normpath(os.path.join(HERE, "..", "sdsys"))
GPL = os.path.join(SDSYS, "gpl.bp")
FILES = {
    "page": os.path.join(GPL, "tool_gates"),
    "run": os.path.join(GPL, "tk_run"),
    "voc": os.path.join(SDSYS, "voc_template", "tool.gates"),
    "newvoc": os.path.join(SDSYS, "newvoc", "tool.gates"),
    "help": os.path.join(SDSYS, "helptext", "tool.gates.page"),
    "setos": os.path.join(GPL, "setosacc"),
    "setnet": os.path.join(GPL, "setnetacc"),
    "setai": os.path.join(GPL, "setai"),
    "keys": os.path.join(SDSYS, "syscom", "keys.h"),
    "ikeys": os.path.join(GPL, "int$keys.h"),
}


def load():
    raw = {}
    for k, p in FILES.items():
        try:
            with open(p, encoding="latin-1") as f:
                raw[k] = f.read()
        except OSError:
            raw[k] = ""
    return raw


def strip_bas(src):
    out = []
    for line in src.split("\n"):
        s = line.lstrip()
        if s.startswith("*") or s.startswith("!"):
            out.append("")
            continue
        cut = line.find(";*")
        out.append(line if cut < 0 else line[:cut])
    return "\n".join(out)


def block(text, label):
    """The text of an internal subroutine: from its label to the next label at the start of a line (or to END)."""
    m = re.search(r"^" + re.escape(label) + r":\s*$", text, re.M)
    if not m:
        return ""
    n = re.search(r"^[a-z][a-z.0-9]*:\s*$|^end\s*$", text[m.end():], re.M)
    return text[m.start(): m.end() + (n.start() if n else len(text))]


def define(src, name):
    m = re.search(r"\$define\s+" + re.escape(name) + r"\s+(\d+)", src)
    return int(m.group(1)) if m else None


def checks(raw):
    rows = []

    def ck(i, what, ok, detail=""):
        rows.append((i, what, bool(ok), detail))

    pg = strip_bas(raw["page"])
    ck("GS0", "NULL CASE: the page, both VOC entries, the help record, the three verbs and the two key headers were found and are not empty (a check on nothing would pass)",
       len(pg) > 9000 and raw["voc"].strip() != "" and raw["newvoc"].strip() != "" and len(raw["help"].split("\n")) >= 4 and len(raw["run"]) > 500
       and all(len(raw[k]) > 500 for k in ("setos", "setnet", "setai", "keys", "ikeys")), "%d" % len(pg))
    ck("GS1", "the page is an internal program catalogued as $tool_gates, and both of Solo's VOC layers (voc_template and newvoc) have it as a verb for that program: the page is open to every session and "
       "decides by itself what to offer",
       re.search(r"^\$internal\s*\nprogram \$tool_gates\s*\n\$catalog \$tool_gates\b", pg, re.M) is not None and raw["voc"].split("\n")[:3] == ["V", "CA", "$tool_gates"]
       and raw["newvoc"].split("\n")[:3] == ["V", "CA", "$tool_gates"], repr((raw["voc"][:30], raw["newvoc"][:30])))
    i_open = pg.find("call $tk_open('tool.gates', '', ctx, err)")
    i_adm = pg.find("adm = (if kernel(K$ADMINISTRATOR, -1) then 1 else 0)")
    i_aud = pg.find("if adm then void kernel(K$AUDIT, 'tool start app=tool.gates')")
    i_read = pg.find("gosub read.all")
    ck("GS2", "it opens the toolkit's base for ANY session first (an audience of '', a refusal is shown and the program stops), asks who it is, writes the one audit line 'tool start' for the "
       "administrator only, and reads only after that; there is no other K$AUDIT in the page (the three verbs write their own)",
       0 < i_open < i_adm < i_aud < i_read and re.search(r"call \$tk_open\('tool\.gates', '', ctx, err\)\s*\n\s*if err # '' then\s*\n\s*display err\s*\n\s*stop\s*\n\s*end", pg) is not None
       and pg.count("K$AUDIT") == 1, "open %s adm %s audit %s read %s" % (i_open, i_adm, i_aud, i_read))
    ck("GS3", "it runs THREE commands, set.os.access, set.net.access and set.ai, through $tk_run and nowhere else: one allow list, ONE call of $tk_run, directly after the confirm box and guarded by "
       "res = 'run'; no execute, perform, chain, write, delete or sequential-file statement",
       re.findall(r"\ballow = '([^']*)'", pg) == ["set.os.access set.net.access set.ai"] and pg.count("call $tk_run(allow, sent, out, st, err)") == 1
       and len(re.findall(r"call \$tk_confirm\(sent, el, typed, res, cmsg\)\s*\n\s*if res = 'run' then\s*\n\s*call \$tk_run\(allow, sent, out, st, err\)", pg)) == 1
       and not re.search(r"^\s*(?:execute|os\.execute|perform|chain|write[uv]?|delete[uv]?|matwrite[u]?|openseq|writeseq|deleteseq)\b", pg, re.M),
       "run %d" % pg.count("call $tk_run("))
    gi = re.search(r"gids = '([^']+)'((?: : @fm : '[^']+')+)", pg)
    ids = ([gi.group(1)] + re.findall(r"'([^']+)'", gi.group(2))) if gi else []
    con = re.search(r"gcmd\.on = ([^\n]+)", pg)
    cof = re.search(r"gcmd\.off = ([^\n]+)", pg)
    cons = re.findall(r"'([^']+)'", con.group(1)) if con else []
    cofs = re.findall(r"'([^']+)'", cof.group(1)) if cof else []
    ck("GS4", "the table has four gates in this order: sh, os, net, ai; each gate's ON and OFF sentence is the verb's own words: set.os.access sh|os on|off, set.net.access on|off, set.ai gate on|off",
       ids == ["sh", "os", "net", "ai"] and cons == ["set.os.access sh on", "set.os.access os on", "set.net.access on", "set.ai gate on"]
       and cofs == ["set.os.access sh off", "set.os.access os off", "set.net.access off", "set.ai gate off"] and "NG = 4" in pg, repr((ids, cons, cofs)))
    so, sn, sa = strip_bas(raw["setos"]), strip_bas(raw["setnet"]), strip_bas(raw["setai"])
    ck("GS5", "those words are what the three verbs take, read off their sources: set.os.access takes SH or OS and ON or OFF in that order, set.net.access takes ON or OFF, set.ai takes GATE and on or off; "
       "each verb asks for the administrator by itself",
       "case upcase(word.1) = 'SH' ; os.field = ACC$SH" in so and "case upcase(word.1) = 'OS' ; os.field = ACC$OS.EXEC" in so and "upcase(word.2) = 'ON'" in so and "upcase(word.2) = 'OFF'" in so
       and "case upcase(word.1) = 'ON'" in sn and "case upcase(word.1) = 'OFF'" in sn and "sub = 'gate' and n.words = 3" in sa and "downcase(field(words, ' ', 3)) = 'on'" in sa
       and all("kernel(K$ADMINISTRATOR, -1)" in t or "K$ADMINISTRATOR" in t for t in (so, sn, sa)))
    ra = block(pg, "read.all")
    ck("GS6", "what the page reads is the register's fields 7, 8 and 15 (ACC$SH, ACC$OS.EXEC, ACC$NET - the fields the verbs write), the kernel's K$SH, K$OS.EXEC and K$NET with -1 (an ask, never a set), "
       "and the helper's status; the field numbers and the key numbers are the headers'",
       "acc.rec<ACC$SH>" in ra and "acc.rec<ACC$OS.EXEC>" in ra and "acc.rec<ACC$NET>" in ra and "kernel(K$SH, -1)" in ra and "kernel(K$OS.EXEC, -1)" in ra and "kernel(K$NET, -1)" in ra
       and "kernel(K$AI.STATUS, 0)" in ra and not re.search(r"kernel\(K\$(?:SH|OS\.EXEC|NET), [^-]", pg)
       and (define(raw["keys"], "ACC$SH"), define(raw["keys"], "ACC$OS.EXEC"), define(raw["keys"], "ACC$NET")) == (7, 8, 15)
       and (define(raw["ikeys"], "K$SH"), define(raw["ikeys"], "K$OS.EXEC"), define(raw["ikeys"], "K$NET")) == (93, 94, 127)
       and "acc.rec<ACC$SH>" in so and "acc.rec<ACC$OS.EXEC>" in so and "acc.rec<ACC$NET>" in sn,
       repr((define(raw["keys"], "ACC$SH"), define(raw["keys"], "ACC$OS.EXEC"), define(raw["keys"], "ACC$NET"), define(raw["ikeys"], "K$SH"), define(raw["ikeys"], "K$OS.EXEC"), define(raw["ikeys"], "K$NET"))))
    i_if = ra.find("   if adm then\n      openpath @sdsys:@ds:'accounts' to acc.f then")
    ck("GS7", "THE REGISTER IS READ FOR THE ADMINISTRATOR ONLY: the one openpath of the register is inside 'if adm then', it reads the one record of the one account (sduser) and closes the file, and "
       "a session that is not the administrator gets null for the three register states (a dash on the page)",
       0 < i_if and pg.count("openpath") == 1 and "acc.name = 'sduser'" in pg and "read acc.rec from acc.f, acc.name then" in ra and "close acc.f" in ra and "reg.ok = 0" in ra
       and ra.find("reg.ok = 0") < i_if and re.search(r"gnow = '' ; gset = ''", ra) is not None and ra.count("gset<") >= 4, "if at %d" % i_if)
    ck("GS8", "THE ADMINISTRATOR IS ASKED OF THE KERNEL EACH TIME: read.all asks again (a session can type ADMIN while another page is up), and the Enter handler refuses before it builds a sentence",
       "adm = (if kernel(K$ADMINISTRATOR, -1) then 1 else 0)" in ra and re.search(r"^change:\s*\n\s*if not\(kernel\(K\$ADMINISTRATOR, -1\)\) then\s*\n\s*msg = '[^']*'\s*\n\s*return\s*\n\s*end", pg, re.M) is not None
       and pg.find("sent = (if on.now") > pg.find("^change:" if False else "change:\n"), "")
    ch = block(pg, "change")
    ck("GS9", "ON or OFF is decided from the REGISTER (gset), never from the session (gnow): a gate switched on a moment ago, and not yet in this session, is offered OFF; the sentence is one of the two table "
       "columns; the AI needs the helper (message 11607) and the other three need the register to have been read",
       "on.now = (gset<k> = 1)" in ch and "sent = (if on.now then gcmd.off<k> else gcmd.on<k>)" in ch and "gnow" not in ch and "case gids<k> = 'ai' and not(helper.ok)\n         msg = sysmsg(11607)" in ch and "case gids<k> # 'ai' and not(reg.ok)" in ch
       and ch.count("sent = ") == 1)
    i_on = ch.find("   end else\n      el<-1> = 'ON  - '")
    ck("GS10", "turning a gate ON asks for its name to be typed (typed = the gate's id) and says that a gate off as delivered is being turned on; turning it OFF asks for no name and says what it can still do",
       0 < i_on and "typed = gids<k>" in ch[i_on:] and "typed = gids<k>" not in ch[:i_on] and "typed = ''" in ch[:i_on] and "Leaving it off is the tighter choice; you decide." in ch[i_on:]
       and "It will still be able to " in ch[:i_on] and ch.count("typed = ") == 2, "on at %d" % i_on)
    acts = sorted(set(re.findall(r"call \$tk_keys\('add', keys, '[^']+', '[^']+', '([a-z]+)'", pg)))
    ck("GS11", "the key table has exactly: help, change, refresh, quit - and 'change' (Enter) is added only for the administrator; there is no key that turns everything on, no queue and no 'tighten'",
       acts == sorted(["help", "change", "refresh", "quit"]) and "if adm then call $tk_keys('add', keys, 'enter', 'change', 'change', '', 1)" in pg and "case nm = 'enter' or nm = ' '" in pg
       and not re.search(r"case nm = '(?:a|t|r|u)'", pg) and " all" not in re.sub(r"[^\n]*(?:rows? ?|gates? ?)all[^\n]*", "", pg).split("on.key:")[-1].split("redraw:")[0], " ".join(acts))
    ck("GS12", "after a command the state is read again and the whole page is drawn again, and what the status line shows is the verb's own last line",
       re.search(r"call \$tk_run\(allow, sent, out, st, err\)[\s\S]*?for oi = dcount\(out, @fm\) to 1 step -1[\s\S]*?msg = \(if said # '' then said\[1, 130\] else 'ran, status ' : st\)[\s\S]*?gosub read\.all\s*\n\s*gosub draw\.all", ch) is not None)
    ck("GS13", "the page has a [?] and F1, ? and a click show tool.gates.page, whose record exists with a title, a documentation page and a body of at least two paragraphs",
       pg.count("'tool.gates.page'") == 2 and "call $tk_help('mark', 134, 2, 0, 0)" in pg and "call $tk_help('hit', mev, 134, 2, hit.m)" in pg and raw["help"].split("\n")[0].strip() != ""
       and raw["help"].split("\n")[1].strip() == "06b-operating-system-access" and len([l for l in raw["help"].split("\n")[2:] if l.strip()]) >= 2)
    dl = block(pg, "draw.all")
    dlst = block(pg, "draw.list")
    drow = block(pg, "draw.row")
    dsrc = block(pg, "draw.source")
    ck("GS14", "the layout fits the 140 by 43 frame: three boxes (rows 1-11, 12-25, 26-34), four gate rows at y 3-6 under the headings at 2, the three summary lines at 8-10, 12 lines of explanation at y 13-24 "
       "and 7 lines of source at y 27-33",
       "screen box at 1,1 size 138,11" in dl and "screen box at 1,12 size 138,14" in dl and "screen box at 1,26 size 138,9" in dl and "VIS = 4" in pg and "at 3,2 + r attr" in dlst
       and "at 3,8 attr" in dlst and "at 3,9 width" in dlst and "at 3,10 width" in dlst and "for r = 1 to 12" in drow and "at 3,12 + r width 134" in drow and "for r = 1 to 7" in dsrc and "at 3,26 + r width 134" in dsrc)
    ck("GS15", "every gate is shown as off as delivered and as reaching beyond SD (nothing is on as delivered, and each one reaches the operating system or beyond SD), and the page says when a change reaches you: "
       "next sign-on three times, at the next request for the AI",
       "fmt('off', '14L') : fmt('yes', '11L')" in dlst and "gwhen = 'next sign-on' : @fm : 'next sign-on' : @fm : 'next sign-on' : @fm : 'at the next request'" in pg)
    ck("GS16", "THE SESSION'S STATE AND THE REGISTER'S ARE TWO COLUMNS: the row says when they differ and that the register is what the next sign-on loads; the AI's two cells are the helper's one setting",
       "'The register says ' : (if gset<k> = 1 then 'ON' else 'off') : ' and this session holds ' : (if gnow<k> = 1 then 'ON' else 'off')" in drow and "gset<4> = gnow<4>" in ra
       and "fmt('This session', '14L') : fmt('Register', '10L')" in dlst)
    ck("GS17", "the page does not tell the administrator to sign in as SDSYS (Solo has no such sign-in: ADMIN is typed after sign-on), says so for a session that is not the administrator, and the help record "
       "says that only the administrator changes a gate",
       "type admin" in raw["page"] and "sign in as" not in pg and "SDSYS" not in raw["page"].split("START-CODE")[-1] and "administrator" in raw["help"])
    ck("GS18", "no gate is turned on by opening the page, by a key that is not Enter or the space bar, or by the mouse: the only place a sentence is built is 'change', and the mouse handler never calls it",
       pg.count("gosub change") == 1 and "gosub change" in block(pg, "on.key") and "gosub change" not in block(pg, "on.mouse") and "gcmd.on" not in pg.split("on.mouse:")[-1].split("change:")[0])
    return rows


def sub(key, old, new):
    def f(raw):
        r = dict(raw)
        if old not in r[key]:
            raise KeyError("%s: %r is not in the file, so the mutant cannot be made" % (key, old[:60]))
        r[key] = r[key].replace(old, new, 1)
        return r
    return f


def setkey(key, val):
    def f(raw):
        r = dict(raw)
        r[key] = val
        return r
    return f


MUTANTS = [
    ("the page is opened for the administrator only", "GS2", sub("page", "call $tk_open('tool.gates', '', ctx, err)", "call $tk_open('tool.gates', 'admin', ctx, err)")),
    ("the page reads before it asks who it is", "GS2", sub("page", "   adm = (if kernel(K$ADMINISTRATOR, -1) then 1 else 0)\n   if adm then void kernel(K$AUDIT", "   gosub read.all\n   adm = (if kernel(K$ADMINISTRATOR, -1) then 1 else 0)\n   if adm then void kernel(K$AUDIT")),
    ("the start line is written for every session", "GS2", sub("page", "if adm then void kernel(K$AUDIT, 'tool start app=tool.gates')", "void kernel(K$AUDIT, 'tool start app=tool.gates')")),
    ("a second audit line", "GS2", sub("page", "   keys = ''\n", "   void kernel(K$AUDIT, 'tool x')\n   keys = ''\n")),
    ("the newvoc entry is missing", "GS1", setkey("newvoc", "")),
    ("the voc_template entry names another program", "GS1", sub("voc", "$tool_gates", "$tool_sessions")),
    ("the page may run another command", "GS3", sub("page", "allow = 'set.os.access set.net.access set.ai'", "allow = 'set.os.access set.net.access set.ai sh'")),
    ("the page runs a command itself", "GS3", sub("page", "      call $tk_run(allow, sent, out, st, err)\n", "      execute sent capturing out\n")),
    ("the box is skipped", "GS3", sub("page", "   call $tk_confirm(sent, el, typed, res, cmsg)\n   if res = 'run' then", "   res = 'run'\n   if res = 'run' then")),
    ("the page writes a file", "GS3", sub("page", "   acc.name = 'sduser'", "   acc.name = 'sduser'\n   write 'x' to acc.f, 'y'")),
    ("the gates are in the wrong order", "GS4", sub("page", "gids = 'sh' : @fm : 'os' : @fm : 'net' : @fm : 'ai'", "gids = 'os' : @fm : 'sh' : @fm : 'net' : @fm : 'ai'")),
    ("os is switched with the sh word", "GS4", sub("page", "'set.os.access os on'", "'set.os.access sh on'")),
    ("net uses a word the verb does not take", "GS4", sub("page", "'set.net.access off'", "'set.net.access disable'")),
    ("ai uses another verb", "GS4", sub("page", "'set.ai gate off'", "'set.ai provider none'")),
    ("a fifth gate", "GS4", sub("page", "NG = 4", "NG = 5")),
    ("the register field of net is the os one", "GS6", sub("page", "acc.rec<ACC$NET>", "acc.rec<ACC$OS.EXEC>")),
    ("the page sets a gate in the kernel", "GS6", sub("page", "gnow<1> = (if kernel(K$SH, -1) then 1 else 0)", "gnow<1> = (if kernel(K$SH, 1) then 1 else 0)")),
    ("the helper is asked for something else", "GS6", sub("page", "kernel(K$AI.STATUS, 0)", "kernel(K$AI.STATUS, 1)")),
    ("the register is read for every session", "GS7", sub("page", "   if adm then\n      openpath @sdsys:@ds:'accounts' to acc.f then", "   if 1 then\n      openpath @sdsys:@ds:'accounts' to acc.f then")),
    ("a second openpath", "GS7", sub("page", "   helper.ok = 0\n   hj = ''\n", "   openpath @sdsys:@ds:'accounts' to acc2.f then close acc2.f\n   helper.ok = 0\n   hj = ''\n")),
    ("the administrator is not asked again by read.all", "GS8", sub("page", "read.all:\n   adm = (if kernel(K$ADMINISTRATOR, -1) then 1 else 0)\n", "read.all:\n")),
    ("Enter does not refuse a holder", "GS8", sub("page", "   if not(kernel(K$ADMINISTRATOR, -1)) then\n      msg = 'Only the administrator can change a gate: type admin, then open this page again'\n      return\n   end\n", "")),
    ("ON or off follows the session", "GS9", sub("page", "   on.now = (gset<k> = 1)\n", "   on.now = (gnow<k> = 1)\n")),
    ("the AI is changed without the helper", "GS9", sub("page", "      case gids<k> = 'ai' and not(helper.ok)\n         msg = sysmsg(11607)", "      case @false\n         msg = sysmsg(11607)")),
    ("the register need is not checked", "GS9", sub("page", "      case gids<k> # 'ai' and not(reg.ok)", "      case @false")),
    ("no name is asked when a gate is turned ON", "GS10", sub("page", "      typed = gids<k>\n", "      typed = ''\n")),
    ("a name is asked when a gate is turned OFF", "GS10", sub("page", "   if on.now then\n      el<-1> = 'OFF - '", "   if on.now then\n      typed = gids<k>\n      el<-1> = 'OFF - '")),
    ("the tighter-choice sentence is gone", "GS10", sub("page", "Leaving it off is the tighter choice; you decide.", "You decide.")),
    ("a key that turns everything on", "GS11", sub("page", "   call $tk_keys('add', keys, 'f5', 'refresh', 'refresh', '', 1)\n", "   call $tk_keys('add', keys, 'f5', 'refresh', 'refresh', '', 1)\n   call $tk_keys('add', keys, 'a', 'all on', 'allon', '', 1)\n")),
    ("Enter is offered to every session", "GS11", sub("page", "if adm then call $tk_keys('add', keys, 'enter', 'change', 'change', '', 1)", "call $tk_keys('add', keys, 'enter', 'change', 'change', '', 1)")),
    ("the page is not read again after a command", "GS12", sub("page", "      gosub read.all\n      gosub draw.all\n   end else\n      msg = cmsg", "      gosub draw.all\n   end else\n      msg = cmsg")),
    ("the help key names a record that does not exist", "GS13", sub("page", "call $tk_help('box', 'tool.gates.page', hm, 0, 0)\n         if hm # '' then msg = hm\n      case nm = 'f5'", "call $tk_help('box', 'tool.gates.nopage', hm, 0, 0)\n         if hm # '' then msg = hm\n      case nm = 'f5'")),
    ("the help record names no page", "GS13", sub("help", "06b-operating-system-access", "")),
    ("the second box overruns the third", "GS14", sub("page", "screen box at 1,12 size 138,14 title 'The row under the cursor'", "screen box at 1,12 size 138,15 title 'The row under the cursor'")),
    ("a gate row is drawn on the border", "GS14", sub("page", "at 3,2 + r attr (if k = ci", "at 3,1 + r attr (if k = ci")),
    ("a gate is delivered on", "GS15", sub("page", "fmt('off', '14L') : fmt('yes', '11L')", "fmt('ON', '14L') : fmt('yes', '11L')")),
    ("a change is said to reach the AI at the next sign-on", "GS15", sub("page", "'next sign-on' : @fm : 'at the next request'", "'next sign-on' : @fm : 'next sign-on'")),
    ("the AI's register cell is not the helper's", "GS16", sub("page", "      gset<4> = gnow<4>\n", "")),
    ("the two columns are not told apart", "GS16", sub("page", "fmt('This session', '14L') : fmt('Register', '10L')", "fmt('This session', '14L') : fmt('Session', '10L')")),
    ("the page tells the administrator to sign in as SDSYS", "GS17", sub("page", "type admin, then open this page again", "sign in as SDSYS, then open this page again")),
    ("the mouse changes a gate", "GS18", sub("page", "         ci = my - 2\n         gosub redraw\n", "         ci = my - 2\n         gosub change\n")),
]


def report(rows):
    bad = 0
    for i, what, ok, detail in rows:
        print("  [%s] %s %s%s" % ("PASS" if ok else "FAIL", i, what, "" if ok or not detail else "   <- " + str(detail)[:200]))
        bad += 0 if ok else 1
    return bad


def selftest(raw):
    base = [r[0] for r in checks(raw) if not r[2]]
    if base:
        print("selftest: the unchanged tree fails %s, so a mutant's own failure cannot be told from the tree's; run the plain check first" % base)
        return 1
    holes = 0
    for name, want, mut in MUTANTS:
        try:
            m = mut(raw)
        except KeyError as exc:
            print("  [FAIL] selftest: %s  <- %s" % (name, exc))
            holes += 1
            continue
        failed = sorted({r[0] for r in checks(m) if not r[2]})
        hit = want in failed
        print("  [%s] selftest: %s is caught by %s (failed: %s)" % ("PASS" if hit else "FAIL", name, want, " ".join(failed) or "none"))
        holes += 0 if hit else 1
    print("selftest: %d mutants, %d not caught" % (len(MUTANTS), holes))
    return 1 if holes else 0


def main(argv):
    raw = load()
    print("test-toolgates-solo-units: tree %s" % os.path.dirname(GPL))
    if not raw["page"]:
        print("test-toolgates-solo-units: CANNOT RUN - %s is not there" % FILES["page"])
        return 2
    rows = checks(raw)
    bad = report(rows)
    print("\ntest-toolgates-solo-units: %d passed, %d failed" % (len(rows) - bad, bad))
    rc = 1 if bad else 0
    if "--selftest" in argv:
        rc = (selftest(raw) or rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
