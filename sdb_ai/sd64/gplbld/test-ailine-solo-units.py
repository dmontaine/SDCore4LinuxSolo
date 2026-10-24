#!/usr/bin/env python3
"""test-ailine-solo-units.py - the toolkit's AI line ($tk_ai) and its use by Solo's home screen, as invariants read off the source (Solo carry 16, 23 Oct 2026).

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-ailine-solo-units.py
  python3 .../test-ailine-solo-units.py --selftest [--from=N]

Solo's counterpart of Core's test-ailine-units.py (Core d6c031e).  No sudo, no install, no sd.  Exit 0 every check passed, 1 a check failed, 2 it could not run.  It reads the BASIC as
text, comments removed, so a rule that survives only in a comment does not count.  IT RUNS NOTHING OF SD: that the line really asks first, sends nothing on Cancel and starts a tile
only on Accept is a sandbox suite's job.  What a text check is for: the invariants are mostly ORDERING (the preview before the request, the offered ids before an action is used) and
an edit that moves one still compiles.

Differences from Core's file, all forced by Solo's shape: the paths; Solo has no Switch account tile, so H1 names only Sign out and S3 asks that no tile or routine of that name comes
back; the gate is the helper's own setting (set.ai gate on), so A13 reads the same four tests off the helper's status line and S1 checks that the four kernel keys the file uses are
Solo's; S2 checks that every message number the two programs cite is a file in Solo's messages (a number that exists in Core only is the fault this catches).
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.abspath(os.path.join(HERE, os.pardir))
GPL = os.path.join(SD64, "sdsys", "gpl.bp")
MSG = os.path.join(SD64, "sdsys", "messages")
FILES = {"tk_ai": os.path.join(GPL, "tk_ai"), "tool_home": os.path.join(GPL, "tool_home"), "tk.h": os.path.join(GPL, "tk.h"),
         "int$keys.h": os.path.join(GPL, "int$keys.h"),
         "ide": os.path.join(GPL, "ide"), "sl_form": os.path.join(GPL, "sl_form"), "sed": os.path.join(GPL, "sed"), "ced_edit": os.path.join(GPL, "ced_edit")}
MSGS = list(range(11635, 11653))
MSGS2 = list(range(11653, 11681))        # Solo carry 17 (24 Oct 26): the IDE (11653-11669), SED and CED (11670-11680).  11681 is the debugger's, which Solo does not have (its debugger is not Core's)


def read(p):
    with open(p, encoding="latin-1") as f:
        return f.read()


def strip_bas(t):
    out = []
    for ln in t.split("\n"):
        s = ln.lstrip()
        if s.startswith("*") or s.startswith("!"):
            continue
        out.append(re.sub(r";\*.*$", "", ln))
    return "\n".join(out)


def ordered(t, *needles):
    pos = -1
    for n in needles:
        i = t.find(n, pos + 1)
        if i < 0:
            return False
        pos = i
    return True


def msg_files():
    return {int(n) for n in os.listdir(MSG) if n.isdigit()}


def load():
    s = {k: read(p) for k, p in FILES.items()}
    s["msgs"] = {n: (read(os.path.join(MSG, str(n))) if os.path.exists(os.path.join(MSG, str(n))) else None) for n in MSGS + MSGS2}
    s["msgfiles"] = msg_files()
    return s


def checks(s):
    rows = []

    def ck(name, ok, detail=""):
        rows.append((name, bool(ok), detail))

    ai = strip_bas(s["tk_ai"])
    home = strip_bas(s["tool_home"])
    ask = ai[ai.find("run.ask:"):ai.find("read.proposal:")]
    prop = ai[ai.find("read.proposal:"):ai.find("clean:\n")]

    ck("A1 the preview comes first: the msgbox with Send and Cancel (Cancel the default), then the request is made, then the wait, then the answer is read",
       ordered(ask, "buttons '&Send,&Cancel' default 2", "if bn # 1 then", "kernel(K$AI.START", "kernel(K$AI.POLL", "jparse(rp<2>)", "gosub read.proposal"), "")
    ck("A2 nothing is sent on Cancel: the branch on bn # 1 returns before K$AI.START (there is no other call of it)", ai.count("K$AI.START") == 1 and ordered(ask, "if bn # 1 then", "return", "kernel(K$AI.START"), "")
    ck("A3 the preview shows EVERYTHING that leaves: the fixed instruction, every action line, what the page tells about itself and the request, with sizes (messages 11640 to 11644)",
       all(("sysmsg(%d" % n) in ask for n in (11640, 11641, 11642, 11643)) and "sysx" in ask and "prompt = " in ask, "")
    ck("A4 an action is used only if it is exactly one of the ids the app offered (a loop over the offered values, a match on the whole id), and the note 11649 is shown otherwise",
       ordered(prop, "for i = 1 to n.acts", "field(acts<1, i>, ':', 1) = act", "if found then", "pk = 'action'") and "sysmsg(11649" in prop and prop.count("found = ") == 2, "")
    ck("A5 the proposal's argument is cleaned twice: ASCII only, then only letters, digits and . _ : / - and space, 100 characters", "gosub clean" in prop and "[1, 100]" in prop
       and "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/- '" in prop, "")
    ck("A6 a command is shown and never run here: no execute, no os.execute, no kernel call but the K$AI.* of this file; it must be printable, at most 200 characters and unchanged by the cleaning",
       not re.search(r"\b(execute|os\.execute|perform)\b", ai) and "if len(c) > 200 or c # raw then" in prop and "sysmsg(11650)" in prop, "")
    ck("A7 a command's default button is the one that does NOT run it, and its letters are distinct (Run, Cancel): Enter alone never runs a command", "btn = '&Run,&Cancel'" in ask and re.search(r"btn = '&Run,&Cancel'[^\n]*\n\s*dflt = 2", ask) is not None, "")
    ck("A8 Enter alone accepts an action only when the app said every action just navigates (actx<5>), else it rejects", "dflt = (if nav then 1 else 2)" in ask and "nav = a<5>" in ask, "")
    ck("A9 the model's text is read as ONE JSON object from the first { to the last } (a fence round it does no harm) and anything else is shown as words with the note 11651 and nothing proposed",
       ordered(prop, "index(atext, '{', 1)", "jparse(atext[f1, l1 - f1 + 1])", "sysmsg(11651)") and "obj.ok" in prop, "")
    ck("A10 a parsed JSON object is never compared with a string (that raises 'Value not found' and the error is swallowed: the answer popup never came, 23 Oct): a flag says whether obj holds one",
       not re.search(r"\bobj\s*(=|#)\s*''", ai) and not re.search(r"\bhj\s*(=|#)\s*''", ai), "")
    ck("A11 the audit line is the kernel's: this file writes none and calls no audit of its own", "K$AUDIT" not in ai and "audit" not in ai.lower().replace("the audit", ""), "")
    ck("A12 the app's words are cleaned like the person's: every offered action line goes through clean before the preview or the prompt", ordered(ask, "for i = 1 to dcount(a<4>, @vm)", "gosub clean", "acts<1, i> = ", "sysx = sysmsg(11635, app)"), "")
    ck("A13 the line is not drawn at all when the AI is not usable (the helper's gate, a provider, a model and a key): read.status sets ai.on only after all four tests, and the other ops do nothing when it is 0",
       ordered(ai, "read.status:", "if not(hj{'gate'}) then return", "hj{'provider'} = ''", "if not(hj{'key'}) then return", "ai.on = 1") and ai.count("if ai.on then") >= 6, "")
    ck("A14 the wait gives up on Esc, on the cursor lock's way out and on an input that has ended, and cancels the request", ordered(ask, "screen key timeout 1 returning nm", "nm = 'esc' or nm = 'guardquit'", "ER$EOF", "kernel(K$AI.CANCEL, 0)"), "")
    ck("H1 the home screen offers only tiles that start a tool: 'cmd:' tiles and the terminal; never Sign out", "if ta[1, 4] = 'cmd:' or ta = 'terminal' then" in home
       and "acts<1, -1> = " in home, "")
    ck("H2 the page's text goes in as VALUES of one field (a field mark would move the fields after it: the action list was empty on 23 Oct), and every action is a navigation (actx<5> = 1)",
       "ctxt := @vm : " in home and "@vm : 'Each action starts the tool" in home and re.search(r"actx = 'home' : @fm : 'home' : @fm : ctxt : @fm : acts : @fm : 1", home) is not None, "")
    ck("H3 an accepted action is looked up by id among the page's own tiles and started through start.tile, as a click would; a command goes through run.command, as the Terminal's prompt would",
       ordered(home, "case res<1> = 'action'", "tl<i, HT.ID> = res<2>", "gosub start.tile", "case res<1> = 'command'", "gosub run.command"), "")
    ck("H4 the AI line is the last stop of the Tab ring and the first of Back-tab, and without the AI the old keys are unchanged (the tests ask ctx<TK.C.AI>)", "if ctx<TK.C.AI> and fi = nt then" in home and "if ctx<TK.C.AI> and fi = 1 then" in home, "")
    ck("H5 the hint row is drawn only when there is no AI line, and the AI line is made again on a resize, a new session and F5", home.count("call $tk_ai('init', ctx, '', '')") >= 4 and "if ctx<TK.C.AI> then\n      call $tk_ai('draw', ctx, aif, '')" in home, "")
    ck("H6 while the line has the focus no tile does (draw.tile), and the cursor is in the line (the loop draws it and does not park the cursor on the status line)",
       "if aif then focused = 0" in home and ordered(home, "if aif then", "call $tk_ai('draw', ctx, 1, '')", "call $sl_curat(0, ctx<TK.C.YSTAT>)"), "")
    ck("H7 a click on the AI line gives it the focus, and the click case comes before the click on a tile (else a tile under row lh - 4 would take it)",
       ordered(home, "case kind = 'press' and mev<2> = 1 and ctx<TK.C.AI> and my = lh - 4", "gosub ai.focus.on", "case kind = 'press' and mev<2> = 1\n"), "")
    ck("H8 a key while the line has the focus goes to the line first, before the tile keys (on.key hands it to ai.key and returns)", ordered(home, "on.key:", "if aif then", "gosub ai.key", "return", "case nm = 'up'"), "")
    ck("M1 messages 11635 to 11652 exist, each one line", all(s["msgs"][n] is not None and len(s["msgs"][n].rstrip("\n").split("\n")) == 1 for n in MSGS), repr([n for n in MSGS if s["msgs"][n] is None]))
    ck("M2 the fixed instruction (11635) asks for ONE JSON object with say, action, arg and command, plain ASCII, and offers an action only for a request the list covers",
       all(w in (s["msgs"][11635] or "") for w in ('"say"', '"action"', '"arg"', '"command"', "ONE JSON object", "Plain ASCII only")), "")
    ck("T1 tk.h defines TK.C.AI (11)", re.search(r"\$define TK\.C\.AI\s+11\b", s["tk.h"]) is not None, "")

    # what is Solo's own
    keys = re.findall(r"K\$AI\.[A-Z]+", ai)
    have = set(re.findall(r"\$define (K\$AI\.[A-Z]+)\s+16\d", s["int$keys.h"]))
    ck("S1 every kernel key tk_ai uses (K$AI.STATUS, START, POLL, CANCEL) is defined in Solo's int$keys.h (160 to 163, carry 15)",
       set(keys) == {"K$AI.STATUS", "K$AI.START", "K$AI.POLL", "K$AI.CANCEL"} and set(keys) <= have, "uses %s, defined %s" % (sorted(set(keys)), sorted(have)))
    cited = {int(n) for n in re.findall(r"sysmsg\((\d+)", ai + "\n" + home)}
    missing = sorted(cited - s["msgfiles"])
    ck("S2 every message number tk_ai and tool_home cite is a file of Solo's messages (carry 14 and 15 numbers, and 11635 to 11652)", cited and not missing, "missing: %s" % missing)
    ck("S3 Solo has one account: the home screen offers no Switch account (no tile, no 'switch' action, no routine) and tk_ai knows nothing of accounts but its own gate",
       "switch" not in home.lower() and "is_grp_member" not in home, "")
    ck("S4 tk_ai reads the helper's gate, not a Linux group: no group test, no register read, no modify.account word in the file", not re.search(r"is_grp_member|openpath|ACC\$|modify\.account|ai-on", ai), "")
    ck("S5 the history of each carried file says so (Solo carry 16), so the next reader knows the code is Core's d6c031e", "Solo carry 16" in s["tk_ai"] and "SOLO CARRY 16" in s["tool_home"], "")

    # Solo carry 17 (24 Oct 2026): AI line stages 2 and 3 - the IDE, SED and CED (the debugger's is not carried: Solo's debugger is older than Core's)
    edits = ai[ai.find("read.edits:"):ai.find("map1:")]
    ide = strip_bas(s["ide"])
    apply_ = ide[ide.find("ai.apply:"):ide.find("get.context:")]
    splice = ai[ai.find("splice.edits:"):ai.find("* ----", ai.find("splice.edits:"))]
    ck("E1 edits are all or none: a set with one edit that does not fit gives the note 11660 and returns BEFORE the diff is built and before pk is set to 'edit'",
       ordered(edits, "if bad.why # '' then", "note.p = sysmsg(11660, bad.why)", "return", "diff.lines = ''", "pk = 'edit'"), "")
    ck("E2 an old text must be in the text shown exactly once and be what the model was shown there (not found, found twice, differs from the original)",
       ordered(edits, "ep = index(tbm, eo, 1)", "bad.why = 'old text not found'", "index(tbm, eo, 2) > 0", "bad.why = 'old text found more than once'", "tb.raw[ep, len(eo)] # eo"), "")
    ck("E3 at most 8 edits, no empty old text, no new text over 4000 bytes, no two edits that overlap, and a diff of more than 30 lines is not offered (11659)",
       all(w in edits for w in ("for ei = 1 to 8", "'more than 8 edits'", "bad.why = 'an empty old text'", "len(en) > 4000", "epos<i> + elen<i> > epos<i + 1>", "bad.why = 'two edits overlap'", "if dl > 30 then", "sysmsg(11659, dl)")), "")
    ck("E4 a change to a text is never accepted by Enter alone: the popup of an edit has Accept and Reject and Reject is the default", re.search(r"case pk = 'edit'.*?btn = '&Accept,&Reject'\s*\n\s*dflt = 2", ask, re.S) is not None, "")
    ck("E5 the diff shows EVERY edit in full: each old line with -, each new line with +, the change number and the line it is at (11658)",
       ordered(edits, "sysmsg(11658, k, ed.n, line.no)", "'- ' : field(eo, nl, j)", "'+ ' : field(en, nl, j)"), "")
    ck("E6 an app that has nowhere to run a command says so ('nocmd') and a command is then ignored; an action is looked for first, edits second, a command last",
       "no.cmd" in ai and ordered(prop, "if found then", "if pk = '' and tbm # '' then gosub read.edits", "if pk = '' and not(no.cmd) then"), "")
    ck("E7 the accepted edits are returned only for an edit proposal, with the model's own words: pk, the edit list, the argument, the words", "(if pk = 'action' then pid else (if pk = 'edit' then ed.list else pcmd))" in ask, "")
    ck("I1 the edits are applied only if the buffer still holds, at every place, exactly what the model was shown ($tk_ai 'splice'): it answers null otherwise, and the IDE then says 11666, changes nothing and returns",
       ordered(splice, "s.now[s.off + s.p, s.l] # s.win[s.p, s.l]", "if not(s.fits) then return", "s.new = s.now")
       and ordered(apply_, "call $tk_ai('splice'", "if ai.sp = '' then", "msg = sysmsg(11666)", "return", "mw{'value'} = "), "")
    ck("I2 the change is ONE undo step: the old text and cursor go on the memo's undo stack before the new value is set, and redo is forgotten",
       ordered(apply_, "mw{'undo'} = ai.snap", "mw{'redo'} = ''", "mw{'value'} = "), "")
    ck("I3 the IDE writes nothing to the disk for the AI: no write, no save in the routine that applies the edits", not re.search(r"\b(write|writev|save|do\.save|delete)\b", apply_), "")
    ck("I4 the AI is asked through $tk_ai only, only when a record is open, and the IDE gives the text, the line it starts at, the selection and 'nocmd'",
       ide.count("call $tk_ai('ask'") == 1 and ordered(ide, "ai.go:", "if nbuf = 0 then", "msg = sysmsg(11662)", "call $tk_ai('ask'") and "ai.sel : @fm : 'nocmd'" in ide, "")
    ck("I5 the AI entry, the AI menu and the shorter table exist only when the AI is usable (ai.on, from $tk_ai usable)", "call $tk_ai('usable', '', ai.on, ai.pm)" in ide and "ai.rows = (if ai.on then 1 else 0)" in ide
       and "if j = 11230 and ai.on then" in ide and ordered(ide, "if ai.on then", "screen label f, 'ailab'", "screen entry f, 'ai'"), "")
    ck("I6 a request typed in the AI entry goes through the same route as the menu (ai.go), and only on Enter (the entry activates)", "case focus.id = 'ai'" in ide and "gosub ai.go" in ide and "aw{'activate'} = 1" in ide, "")
    ck("I7 sl_form lets an entry activate on Enter only when the app asked for it (the flag), so no other form's entry changes", "(aw{'type'} = 'entry' and aw{'activate'} + 0)" in strip_bas(s["sl_form"]), "")
    ck("M3 messages 11653 to 11680 exist, each one line", all(s["msgs"][n] is not None and len(s["msgs"][n].rstrip("\n").split("\n")) == 1 for n in MSGS2), repr([n for n in MSGS2 if s["msgs"][n] is None]))
    sed = strip_bas(s["sed"])
    sed_ai = sed[sed.find("ai.run:"):sed.find("ai.say:")]
    ced = strip_bas(s["ced_edit"])
    ced_ai = ced[ced.find("ai.menu:"):ced.find("revert:")]
    ck("X1 the shared routines are the library's: 'select', 'window' and 'splice' are in $tk_ai and the IDE and SED use them (CED the window and the splice), no editor has its own copy",
       all(("case op = '%s'" % o) in ai for o in ("select", "window", "splice")) and "call $tk_ai('window'" in ide and "call $tk_ai('splice'" in ide and "call $tk_ai('select'" in ide
       and "call $tk_ai('window'" in sed and "call $tk_ai('splice'" in sed and "call $tk_ai('select'" in sed and "call $tk_ai('window'" in ced and "call $tk_ai('splice'" in ced
       and "ai.total = dcount" in ide and "> 24000" not in ide and "> 24000" not in sed, "")
    ck("X2 SED offers the AI only when it is usable for the account: the menu items and the command both ask ai.ok ($tk_ai 'usable', once at the start), and the command says 11670 otherwise",
       "call $tk_ai('usable', '', ai.ok, ai.pm)" in sed and ordered(sed, "if ai.ok then", "'Ask the &AI...'", "'Ex&plain the selection'") and ordered(sed_ai, "if not(ai.ok) then", "sysmsg(11670)", "return"), "")
    ck("X3 SED sends nothing but through $tk_ai 'ask' (ONE call: the preview, the wait, the answer), the text and the selection as the model is told, 'nocmd' (a command is ignored), the mouse reports off while it runs and the screen drawn again after",
       sed_ai.count("call $tk_ai('ask'") == 1 and "'nocmd'" in sed_ai and ordered(sed_ai, "gosub mouse.disarm", "call $tk_ai('ask'", "mat image = sw.space ; mat simage = ''", "gosub refresh.all"), "")
    ck("X4 SED applies an accepted set to its BUFFER only: not in a read only buffer, only if it still fits (11666), by rebuilding the chunks (the main loop's capture before the command is the undo step), and the routine saves nothing",
       ordered(sed_ai, "ai.apply:", "if read.only then", "gosub read.only.buffer", "call $tk_ai('splice'", "if ai.sp = '' then", "sysmsg(11666)", "gosub rebuild.chunks", "record.updated = @true")
       and not re.search(r"\b(save\.record|write|writeu|writev)\b", sed_ai), "")
    ck("X5 CED offers F2 only when the AI is usable; an accepted set must leave a JSON collection or array (else 11677 and c is not touched); the old record is kept for one undo BEFORE c is replaced; the routines save nothing",
       "case c.key = 'f2' and ai.ok" in ced and "call $tk_ai('usable', '', ai.ok, ai.pm)" in ced
       and ordered(ced_ai, "ai.apply:", "call $tk_ai('splice'", "ai.y = jparse(ai.sp<1>)", "if ai.bad then", "sysmsg(11677)", "return", "ai.undo = jbuild(c)", "c = ai.y", "dirty = @true")
       and "'nocmd'" in ced_ai and not re.search(r"\b(save\.record|writeu|writev)\b", ced_ai), "")
    ck("X6 Solo's debugger has no AI command (its debugger is older than Core's: no relayout, no 140 by 42 layout): the debugger asks nothing of $tk_ai", "tk_ai" not in read(os.path.join(GPL, "debug")), "")
    return rows


MUTANTS = [
    ("the preview is skipped", "tk_ai", "   if bn # 1 then\n      b = 'none'", "   if @false then\n      b = 'none'", "A1"),
    ("Send is the default button", "tk_ai", "buttons '&Send,&Cancel' default 2", "buttons '&Send,&Cancel' default 1", "A1"),
    ("any action id is accepted", "tk_ai", "      if found then\n         pk = 'action'", "      found = 1\n      if found then\n         pk = 'action'", "A4"),
    ("a command is run", "tk_ai", "            pk = 'command'\n            pcmd = c", "            pk = 'command'\n            pcmd = c\n            execute c", "A6"),
    ("a command's default is Run", "tk_ai", "         dflt = 2\n      case 1\n         btn = '&Close'", "         dflt = 1\n      case 1\n         btn = '&Close'", "A7"),
    ("Run and Reject share a letter", "tk_ai", "btn = '&Run,&Cancel'", "btn = '&Run,&Reject'", "A7"),
    ("an object is compared with a string", "tk_ai", "   if not(obj.ok) then", "   if obj = '' then", "A10"),
    ("Sign out is offered", "tool_home", "if ta[1, 4] = 'cmd:' or ta = 'terminal' then", "if ta[1, 4] = 'cmd:' or ta = 'terminal' or ta = 'signout' then", "H1"),
    ("the page's lines are fields", "tool_home", "ctxt := @vm : 'The person is '", "ctxt := @fm : 'The person is '", "H2"),
    ("the line is drawn without the AI", "tk_ai", "   if not(hj{'key'}) then return", "   null", "A13"),
    # Solo's own (first mutant of this file's own set: --from=10)
    ("the gate is not read", "tk_ai", "   if not(hj{'gate'}) then return\n", "", "A13"),
    ("the click on the AI line is not handled", "tool_home",
     "      case kind = 'press' and mev<2> = 1 and ctx<TK.C.AI> and my = lh - 4\n         gosub ai.focus.on                                 ;* a click on the AI line gives it the focus\n",
     "", "H7"),
    ("a key reaches the tiles while the line has the focus", "tool_home", "   if aif then\n      gosub ai.key\n      return\n   end\n", "", "H8"),
    ("a Switch account action comes back", "tool_home", "      case act = 'signout'\n         gosub do.signout\n", "      case act = 'switch'\n         gosub switch.account\n      case act = 'signout'\n         gosub do.signout\n", "S3"),
    ("tk_ai asks a Linux group", "tk_ai", "   if not(hj{'gate'}) then return", "   if not(hj{'gate'}) and not(is_grp_member(@logname, 'sdai')) then return", "S4"),
    ("a message is missing", "msgfiles", None, None, "S2"),
    ("the kernel key START is not Solo's", "int$keys.h", "$define K$AI.START        160", "$define K$AI.STARTX       160", "S1"),
    ("the carry is not recorded in tk_ai", "tk_ai", "Solo carry 16 (Core d6c031e)", "Core d6c031e", "S5"),
    # Solo carry 17 (the first of these is marker 18 for --from=18)
    ("an old text found twice is accepted", "tk_ai", "               case index(tbm, eo, 2) > 0\n", "               case @false\n", "E2"),
    ("a bad edit is only skipped, not the whole set", "tk_ai", "      note.p = sysmsg(11660, bad.why)\n      return\n", "      note.p = sysmsg(11660, bad.why)\n", "E1"),
    ("Enter accepts an edit", "tk_ai", "         dflt = 2                                         ;* a change to a text is never accepted by Enter alone", "         dflt = 1", "E4"),
    ("splice applies without the fit test", "tk_ai", "      if s.now[s.off + s.p, s.l] # s.win[s.p, s.l] then s.fits = 0", "      null", "I1"),
    ("the IDE's change is not an undo step", "ide", "   mw{'undo'} = ai.snap : @fm : mw{'undo'}\n", "", "I2"),
    ("the IDE saves after applying", "ide", "   msg = sysmsg(11661, ai.n)\n", "   msg = sysmsg(11661, ai.n)\n   write ai.new on fv, bi<cb>\n", "I3"),
    ("the IDE does not say nocmd", "ide", "ai.sel : @fm : 'nocmd'", "ai.sel", "I4"),
    ("every entry activates", "sl_form", "(aw{'type'} = 'entry' and aw{'activate'} + 0)", "aw{'type'} = 'entry'", "I7"),
    ("SED saves after applying", "sed", "   message = sysmsg(11661, ai.sp<3>)\n   gosub ai.say\n", "   gosub save.record\n   message = sysmsg(11661, ai.sp<3>)\n   gosub ai.say\n", "X4"),
    ("SED applies in a read only buffer", "sed", "   if read.only then\n      gosub read.only.buffer\n      return\n   end\n   gosub save.current\n   gosub assemble.record\n   ai.now", "   gosub save.current\n   gosub assemble.record\n   ai.now", "X4"),
    ("SED offers the AI without the gate", "sed", "   if ai.ok then\n      ml = '-' ; mc = 'x:' ; gosub add.item\n      ml = 'Ask the &AI...'", "   if @true then\n      ml = '-' ; mc = 'x:' ; gosub add.item\n      ml = 'Ask the &AI...'", "X2"),
    ("SED lets the mouse report during the wait", "sed", "   gosub mouse.disarm\n   call $tk_ai('ask'", "   call $tk_ai('ask'", "X3"),
    ("CED accepts invalid JSON", "ced_edit", "   if ai.bad then\n      message.text = sysmsg(11677)\n      return\n   end\n", "   if ai.bad then\n      ai.y = jparse('{}')\n   end\n", "X5"),
    ("CED replaces c before keeping the old record", "ced_edit", "   ai.undo = jbuild(c)\n   c = ai.y\n", "   c = ai.y\n   ai.undo = jbuild(c)\n", "X5"),
    ("CED saves after applying", "ced_edit", "   message.text = sysmsg(11676, ai.sp<3>)\n", "   gosub save.record\n   message.text = sysmsg(11676, ai.sp<3>)\n", "X5"),
]
M_SOLO = 10
M_STAGE23 = 18


def run(over=None):
    s = load()
    if over:
        s.update(over)
    return checks(s)


def selftest(first=0):
    base = run()
    base_fail = {n.split()[0] for n, ok, _ in base if not ok}
    print("selftest: the unchanged tree fails %d check(s): %s" % (len(base_fail), ", ".join(sorted(base_fail)) or "none"))
    if base_fail:
        return 1
    s0 = load()
    bad = 0
    for name, key, old, new, want in MUTANTS[first:]:
        if key == "msgfiles":
            over = {"msgfiles": s0["msgfiles"] - {11640}}                 # the file of a message the line cites is gone
        else:
            if s0[key].count(old) != 1:
                print("  [FAIL] selftest: %s: the old text occurs %d times in %s, not once" % (name, s0[key].count(old), key))
                bad += 1
                continue
            over = {key: s0[key].replace(old, new)}
        failed = [n.split()[0] for n, ok, _ in run(over) if not ok]
        hit = want in failed
        print("  [%s] selftest: %s is caught by %s (failed: %s)" % ("PASS" if hit else "FAIL", name, want, " ".join(failed) or "none"))
        bad += 0 if hit else 1
    print("selftest: %s" % ("every mutant was caught" if bad == 0 else "%d problem(s)" % bad))
    return 0 if bad == 0 else 1


def main(argv):
    for k, p in FILES.items():
        if not os.path.exists(p):
            print("test-ailine-solo-units: CANNOT RUN - %s is missing" % k)
            return 2
    if "--selftest" in argv:
        first = 0
        for a in argv:
            if a.startswith("--from="):
                first = int(a[len("--from="):])
        return selftest(first)
    rows = run()
    bad = 0
    for n, ok, d in rows:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", n, "" if ok else "   <- " + str(d)[:300]))
        bad += 0 if ok else 1
    print("test-ailine-solo-units: %d checks, %d failed" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
