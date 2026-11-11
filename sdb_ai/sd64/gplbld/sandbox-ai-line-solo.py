#!/usr/bin/env python3
#
# sandbox-ai-line-solo.py - the toolkit's AI line ($tk_ai) on the HOME SCREEN, driven on a pseudo-terminal on a private SD Core for Linux Solo
#                           (SOLO CARRY 16 of S.69, AI line stage 1, 23 Oct 2026; Core commit d6c031e).  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-ai-line-solo.py <dir> [--build] [--mutant=NAME]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent; give it a name that is not the same length as
# another sandbox's directory if the two can exist together).  Exit 0 every row passed, 1 a row failed, 2 it could not run.  With --mutant=NAME one change is made to the SANDBOX'S
# OWN COPY of $tk_ai and exit 0 means the rows that had to fail failed and no others (MUTANTS below).  Solo's counterpart of Core's sandbox-ai-line.py, whose rows these are; the
# row ids L0-L16 and the four mutants are Core's.
#
# START-HISTORY:
# 23 Oct 26 dm  New (Solo carry 16).
# 11 Nov 26 dm  Brought to the pages carried from SD Core on 10 Nov, after Core's sandbox-ai-line.py.  L1: the hint says "press F6" (S.176).  L4: the ring is F6 / Shift-F6
#               (L4a F6 from the first tile, L4d Tab from Sign out goes round the tiles and NOT to the line, L4e Shift-F6, new L4e2 F6 in the line gives the focus back).
#               L5a / L5b: the preview shows the person's request and not SD's own text (S.175: the fixed instruction and the page's actions are sent, counted in the
#               size, and not shown).  L11: the fake's fenced reply names the IDE (fakemodel.py, as Core's: the Record editor tile `ced` went with S.88 g-P1).
# END-HISTORY
#
# WHAT RUNS.  The real helper (gplbld/sd-ai, served by ai-runner.py: Solo's, which runs as the user and has no gate group) and the fake provider (gplbld/fakemodel.py, TLS with a
# throw-away CA, which LOGS every request and answers in the JSON form the line asks for when the LAST line of the prompt carries a marker such as [[act_ide]]).  The helper, the fake,
# the providers file, the programs setai / ai / tool_ai and the environment (SD_AI_SOCKET, SD_AI_CTL) are made by sandbox-ai-solo.py's setup_ai(), which this suite loads as a module;
# this suite then puts the tree's $tk_ai and tool_home into the sandbox (with the mutant's one change in tk_ai) and compiles them.  The provider, model and key are set with SET.AI
# and a key file, as sandbox-ai-solo.py does.
#
# THE INSTRUMENT.  "Nothing was sent" is judged by the FAKE's request log and the audit file, not by what the screen said; "a tile started" by the screen it gave (the IDE's menu bar);
# "a command ran" by the output of the command; a row that needs a request counts one arriving at the fake first.  The suite stops with exit 2 (it does not fail rows) when the tree
# has no tk_ai or the fake has no JSON replies: a missing carry is not a finding about the line.
#
# WHERE SOLO DIFFERS FROM CORE (each is a comment on its row).  ONE account, sduser (Core: the fixture account zzhd); the administrator is ADMIN typed at the prompt of the same session
# (Core: SDTEST_ADMIN), which needs the start setting terminal, so the administrator's page is opened with HOME; the gate is a SETTING of the helper, turned on and off with
# set.ai gate on|off in an internal session (Core: the helper's group, a runner started with a gate group that does not exist); there is no Switch account tile, so the ring has one
# header tile (Sign out) and the page's action list has no tile the AI could name that Solo lacks; the audit line names account=sduser; the start setting is arrange("menu") (Core:
# set_default).  The home screen's rows are Core's: the AI row is row 39 at 140 by 43 (the hint row of Solo's tool_home, row lh-4 - sandbox-home-solo.py holds the hint at 39 and
# the status line [Home] at 40), the tiles of the holder's page are Editor, IDE, Record editor (group My tools), Terminal, Keys (group Everyone), Sign out in the header.
#
#   L0-L3  the line is NOT DRAWN when the AI is off: no provider, no model, no key, the gate off, no helper; the old hint is there instead; with everything set the line replaces the hint
#   L4     the F6 ring: F6 from the first tile, Tab from Sign out round the tiles only, Esc, Shift-F6, F6 back, a click
#   L5-L6  Enter shows everything that will leave the machine (the fixed instruction, the list of the page's actions, what the page says, the request) and the provider and model;
#          Cancel is the default; Enter on it sends nothing (the fake and the audit file agree)
#   L7     Send: ONE request at the fake with the key, the instruction, the actions of THIS page and the typed request as the last line; ONE audit line from the kernel
#   L8-L9  an action the AI names is started only on Accept (Enter alone accepts, the tile only opens a tool); one the page does not offer, and Sign out, are ignored and said so
#   L10    a command is shown; Enter alone rejects it; Run runs it as the Terminal would; a command with a tab, or of 300 characters, is not shown
#   L11-L14 a code fence round the object, words that are not JSON, a say with no proposal, an argument with characters the line does not allow, a say that gives orders
#   L15    Esc during the wait gives the request up and the screen is the home screen again
#   L16    the administrator's page has the line too, with the administrator's tiles in the list
#   L18    (11 Nov 26, Core's L16a-d of 3 Nov) Follow up: the earlier question and answer arrive at the provider as messages before the request; followup=1 in the audit line
#   L17    (11 Nov 26, Core's S.160 rows) the standing text: not in the preview, first in the system text that arrives, the shipped default when there is none of the
#          administrator's, and a text that names SD's own code sends nothing (14013)
# NOT HELD: the IDE, SED, CED and the debugger (later stages), the AI menu item, a window under 140 by 43 (the toolkit's one size check), the end of the input during the wait, a real
# provider, the installer.  The rows were written from the Core suite and the Solo tool_home / $tk_ai as carried; none of them was run when this file was written.
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


sh = _load("sandbox_home_solo_for_ailine", "sandbox-home-solo.py")
ai = _load("sandbox_ai_solo_for_ailine", "sandbox-ai-solo.py")
# sandbox-ai-solo.py loaded a copy of sandbox-home-solo.py of its own, with a BOX and a SYS nobody sets: point it at THIS suite's copy, which start_sandbox() fills in
ai.sh = sh
for _n in ("say", "has", "put", "bail", "dump", "plain", "adm", "H"):
    setattr(ai, _n, getattr(sh, _n))
import fakemodel  # noqa: E402

say, bail, has, put, dump, plain, adm, H = sh.say, sh.bail, sh.has, sh.put, sh.dump, sh.plain, sh.adm, sh.H
sh.KEYS["shift-f6"] = "\x1b[17;2~"      # 11 Nov 26 (Core's S.176): Shift-F6 in xterm's modifier form, as Core's suite sends it: the box keys are F6 / Shift-F6
KEY = ai.KEY
MODEL = ai.MODEL
FAILED_IDS = []
ACCT = "sduser"
NEEDED_REPLIES = ("act_ide", "act_terminal", "act_bad", "act_signout", "cmd_list", "cmd_tab", "cmd_long", "fenced", "notjson", "sayonly", "argbad", "hostile")


def arow(rid, name, ok, detail=""):
    sh.row("%s %s" % (rid, name), ok, detail)
    if not ok:
        FAILED_IDS.append(rid)


MUTANTS = {
    # name: (old text of the sandbox's tk_ai, new text, the row ids that must fail and no others)
    "no-preview": ("   if bn # 1 then\n      b = 'none' : @fm : '' : @fm : '' : @fm : '' : @fm : sysmsg(11630)", "   if @false then\n      b = 'none' : @fm : '' : @fm : '' : @fm : '' : @fm : sysmsg(11630)", ["L6"]),
    # (found = 1 takes the first offered action's label for whatever the AI names, so L9 - Sign out - and the two proposals that show a label fail with L8)
    "action-not-checked": ("      if found then\n         pk = 'action'", "      found = 1\n      if found then\n         pk = 'action'", ["L8", "L9", "L11", "L14"]),
    "command-default-run": ("         btn = '&Run,&Cancel'                              ;* (not Reject: its letter would be Run's)\n         dflt = 2", "         btn = '&Run,&Cancel'                              ;* (not Reject: its letter would be Run's)\n         dflt = 1", ["L10"]),
    "command-not-cleaned": ("         if len(c) > 200 or c # raw then", "         if len(c) > 200 then", ["L10"]),
}


def fm():
    return ai.STATE["fm"]


def requests():
    return ai.requests(fm())


def line_row(h):
    """The AI row: the row above the status line (row 39 at 140 by 43; the hint row of the home screen when the AI is off)."""
    return h.line(39)


def msg(n, *args):
    return ai.msg(n, *args)


def setup_line(mutant):
    """The tree's $tk_ai and tool_home into the sandbox (a sandbox used for an earlier mutant starts from the tree's again), the mutant's one change, and the compile."""
    for n in ("tk_ai", "tool_home"):
        if not os.path.isfile(os.path.join(TREE, "sdsys", "gpl.bp", n)):
            bail("the tree has no sdsys/gpl.bp/%s: the AI line has not been carried yet" % n)
    missing = [k for k in NEEDED_REPLIES if k not in getattr(fakemodel, "JSON_REPLIES", {})]
    if missing:
        bail("gplbld/fakemodel.py has no JSON reply for %s: the fake has not been carried yet" % ", ".join(missing))
    for n in ("tk_ai", "tool_home"):
        shutil.copyfile(os.path.join(TREE, "sdsys", "gpl.bp", n), os.path.join(sh.SYS, "gpl.bp", n))
    if mutant is not None:
        old, new, _kills = MUTANTS[mutant]
        path = os.path.join(sh.SYS, "gpl.bp", "tk_ai")
        src = open(path, encoding="utf-8", errors="replace").read()
        if src.count(old) != 1:
            bail("mutant %s: the text to change is found %d times, not once" % (mutant, src.count(old)))
        put(path, src.replace(old, new))
        say("sandbox-ai-line-solo: MUTANT %s: the rows that must fail, and nothing else: %s" % (mutant, ", ".join(MUTANTS[mutant][2])))
    for n in ("tk_ai", "tool_home"):           # tk_ai first: tool_home calls it
        ai.compile_prog(n)


def configure(provider=True, model=True, key=True, gate=True):
    """provider, model, key and gate through the verb / the key file, as the administrator would; any of them left out is cleared.  SOLO: the gate is the helper's setting (set.ai gate on|off, off
    as delivered), not a group of the helper's caller; the helper looks at it at every request, so no restart is needed."""
    cmds = ["set.ai ca " + ai.STATE["ca"], "set.ai limit requests-hour 1000", "set.ai provider anthropic" if provider else "set.ai provider none",
            ("set.ai model anthropic " + MODEL) if model else "set.ai model anthropic -", "set.ai gate on" if gate else "set.ai gate off"]
    adm(*cmds)
    kp = ai.keyfile("anthropic")
    if key:
        os.makedirs(os.path.dirname(kp), mode=0o700, exist_ok=True)
        put(kp, KEY + "\n")
        os.chmod(kp, 0o600)
    elif os.path.exists(kp):
        os.remove(kp)


def home(admin=False):
    """A session on a pseudo-terminal with the home screen drawn.  SOLO: the holder's page is the start setting menu; the administrator's is ADMIN at the prompt (which needs the start
    setting terminal, as sandbox-home-solo.py has it) and then HOME."""
    if admin:
        sh.arrange("terminal")
        h = H(admin=True)
        h.typed("home\r", idle=3.0)
    else:
        sh.arrange("menu")
        h = H()
        if not h.home():
            h.s.settle(2.0)
    return h


def ask(h, text):
    """Focus the line (F6 from the tiles, as Core's suite does since its S.176; until 11 Nov 26 this was Back-tab from the first tile, which no longer reaches the line, so every
    row that asked failed for that reason alone), type the request, Enter: the preview."""
    h.key("f6", idle=0.8)
    h.typed(text, idle=0.6)
    h.key("enter", idle=1.5)


def reply(text, wait=4.0):
    """Ask with a marker, Send, and return the session and the screen text of the popup."""
    h = home()
    ask(h, text)
    h.typed("s", idle=wait)
    return h, h.text()


def sec_off():
    say("\n--- the line is not drawn when the AI is off")
    for rid, label, kw in (("L0a", "no provider", dict(provider=False)), ("L0b", "a provider and no model", dict(model=False)), ("L0c", "no key", dict(key=False))):
        configure(**kw)
        h = home()
        arow(rid, "%s: no AI row, the old hint is on the row above the status line" % label, "AI>" not in line_row(h) and "arrows move" in line_row(h) and h.home(), repr(line_row(h)[:80]))
        h.key("btab", idle=0.6)
        arow(rid + "t", "...and Back-tab from the first tile goes to the last tile (Sign out), not to a line that is not there", "Sign out" in h.focus(), repr(h.focus()))
        h.key("ctrl-q", idle=1.5)
        h.end()
    configure(gate=False)
    h = home()
    arow("L0d", "everything set and the gate OFF (as delivered; Core: the account is not in the helper's group): no AI row, the hint is there",
         "AI>" not in line_row(h) and "arrows move" in line_row(h), repr(line_row(h)[:80]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    configure()
    ai.stop_runner()
    h = home()
    arow("L0e", "the helper is not running: no AI row, the hint is there, the screen is whole", "AI>" not in line_row(h) and "arrows move" in line_row(h) and h.home(), repr(line_row(h)[:80]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    ai.start_runner()                          # (set.ai below needs the helper)
    configure()
    h = home()
    arow("L1", "everything set and the gate on: the AI row replaces the hint, with the dim sentence that says how to reach it",
         line_row(h).lstrip().startswith("AI>") and "Ask the AI: press F6" in line_row(h) and "arrows move" not in line_row(h), repr(line_row(h)[:100]))
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_ring():
    say("\n--- the F6 ring (Core's S.176: the tiles and the line; Tab goes round the tiles only)")
    h = home()
    first = h.focus()
    h.key("f6", idle=0.8)
    arow("L4a", "F6 from the first tile gives the focus to the AI line: no tile has it, the row shows the label bold and the status line says how to use it",
         h.focus() == [] and msg(11638) in h.line(40) and "AI>" in line_row(h), repr((h.focus(), h.line(40)[:90])))
    h.typed("abc", idle=0.5)
    arow("L4b", "what is typed is in the line", "abc" in line_row(h), repr(line_row(h)[:60]))
    h.key("esc", idle=0.8)
    arow("L4c", "Esc gives the focus back to the tile it came from (the first tile again; the typed text is kept in the line)", h.focus() != [] and "abc" in line_row(h), repr((h.focus(), line_row(h)[:60])))
    for _ in range(40):                        # SOLO: Sign out is the one header tile and the last of the ring; the ring grows with every tile, the loop ends at Sign out
        h.key("tab", idle=0.3)
        if "Sign out" in h.focus():
            break
    h.key("tab", idle=0.8)
    arow("L4d", "Tab from Sign out (the last tile) goes round the tiles to the first one, NOT to the AI line", h.focus() == first and msg(11638) not in h.line(40),
         repr((h.focus(), first, h.line(40)[:80])))
    h.key("shift-f6", idle=0.8)
    arow("L4e", "Shift-F6 gives the focus to the AI line too", h.focus() == [] and msg(11638) in h.line(40), repr((h.focus(), h.line(40)[:80])))
    h.key("f6", idle=0.8)
    arow("L4e2", "F6 in the line gives the focus back to the tile it came from (the first), and is not typed into the line", h.focus() == first and "abc" in line_row(h)
         and "abc\x1b" not in line_row(h), repr((h.focus(), first, line_row(h)[:60])))
    h.click(40, 39, idle=1.0)                  # (no Esc first: on the top page Esc opens the menu bar, and the click would only close it - Core's note)
    arow("L4f", "a click on the AI row gives it the focus", h.focus() == [] and msg(11638) in h.line(40), repr((h.focus(), h.line(40)[:80])))
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_preview():
    say("\n--- the preview and Cancel")
    h = home()
    n0, a0 = len(fm().log), ai.audit_off()
    ask(h, "open the ide [[act_ide]]")
    T = h.text()
    # Core's S.175 (the owner, 8 Nov 26: "it is showing the standard prefix text, it is not supposed to"): SD's own text is sent but not shown
    arow("L5a", "Enter shows the preview: the provider, the model and the size, and the request, and nothing has been sent",
         msg(11628, "anthropic", MODEL, "").split("%")[0][:30] in T and "open the ide [[act_ide]]" in T and "Send" in T and "Cancel" in T and len(fm().log) == n0, T[-1200:])
    arow("L5b", "the preview does NOT show SD's own text: no fixed instruction, no list of the page's actions, nothing of what the page says about itself",
         "You help a person who is using home" not in T and "ide:IDE" not in T and "terminal:Terminal" not in T and "the home screen of the SD database system" not in T
         and "The fixed instruction" not in T, T[-900:])
    h.key("enter", idle=1.5)
    arow("L6", "Enter on the default button is Cancel: nothing was sent (the fake's log and the audit file agree) and the status line says so",
         len(fm().log) == n0 and not ai.req_lines(ai.audit_new(a0)) and msg(11630) in h.line(40) and h.home(), repr((len(fm().log) - n0, h.line(40)[:80])))
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_send():
    say("\n--- Send, and what arrives")
    h = home()
    n0, a0 = len(fm().log), ai.audit_off()
    ask(h, "open the ide [[act_ide]]")
    h.typed("s", idle=4.0)
    rq = requests()
    last = rq[-1] if len(rq) > n0 else (None, {}, None)
    body = last[2] or {}
    sysx = ""
    try:
        sysx = body["system"][0]["text"]
    except (KeyError, IndexError, TypeError):
        pass
    prompt = body["messages"][-1]["content"] if body.get("messages") else ""
    arow("L7a", "Send: ONE request at the fake, with the key, the model and an instruction that names the app; the prompt ends with the typed request", len(fm().log) == n0 + 1 and last[0] == "/v1/messages"
         and last[1].get("x-api-key") == KEY and body.get("model") == MODEL and "who is using home" in sysx and prompt.endswith("Request: open the ide [[act_ide]]"), repr((len(fm().log) - n0, last[0], sysx[:60], prompt[-60:])))
    # (Solo has no Switch account tile at all; the check stays so that a carried tile table that gained one would show)
    arow("L7b", "the prompt lists the page's tiles as id:what it does, and does NOT list Sign out (or Switch account)", "  ide:IDE - programs and files" in prompt and "  terminal:Terminal" in prompt
         and "signout" not in prompt and "switch:" not in prompt, repr(prompt[:400]))
    aud = ai.audit_new(a0)
    rl = ai.req_lines(aud)
    arow("L7c", "ONE audit line, written by the kernel before the request: the account (sduser), the program (tk_ai) and the size; neither the request nor the key is in the audit trail",
         len(rl) == 1 and re.search(r"ai request account=%s program=tk_ai bytes\.out=\d+$" % ACCT, rl[0]) is not None and "open the ide" not in aud and KEY not in aud, repr(rl))
    T = h.text()
    arow("L8a", "the answer is a popup: what the AI said, and the proposal with Accept and Reject, and the tokens used", "Opening the IDE for you." in T and msg(11647, "IDE - programs and files") in T
         and "Accept" in T and "Reject" in T and msg(11634, 11, 7, "anthropic") in T, T[-900:])
    # SOLO: the header holds Sign out alone (Core's row looked for the Switch account tile); the popup is in the middle of the screen, so the header is still there
    arow("L8b", "nothing has started yet: the home screen is under the popup (the Sign out tile of the header is still drawn)", h.find("Sign out") is not None, T[:200])
    h.key("enter", idle=3.5)
    arow("L8c", "Enter alone accepts a proposal that only opens a tool: the IDE takes the terminal (its menu bar is on the screen)", "File" in h.line(0) and "Go" in h.line(0) and "Everyone" not in h.text(), repr(h.line(0)[:70]))
    h.key("ctrl-q", idle=2.5)
    arow("L8d", "Ctrl-Q ends the IDE and the home screen is drawn again, with the AI row and an empty line", h.home() and "AI>" in line_row(h) and "open the ide" not in line_row(h), repr((h.home(), line_row(h)[:80])))
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_proposals():
    say("\n--- what the AI can and cannot cause")
    # an action the page does not have
    h, T = reply("format it [[act_bad]]")
    arow("L8", "an action the page does not offer is ignored and said so: the AI's words, the note (11649), only a Close button, nothing started", "Formatting the disk." in T
         and msg(11649, "format-disk") in T and "Close" in T and "Accept" not in T and "Run" not in T, T[-800:])
    h.key("enter", idle=1.5)
    arow("L8e", "Close returns to the home screen, which is whole", h.home(), repr(h.text()[:100]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("sign me out [[act_signout]]")
    arow("L9", "Sign out is never offered, so an action 'signout' from the AI is ignored (11649) and the session is not ended", msg(11649, "signout") in T and "Accept" not in T, T[-600:])
    h.key("enter", idle=1.5)
    arow("L9b", "...and the session is still there", h.home(), "")
    h.key("ctrl-q", idle=1.5)
    h.end()
    # a command
    h, T = reply("who am i [[cmd_list]]")
    arow("L10a", "a command is shown (11648, with the command on a line of its own) and offered for Run or Reject; the default is Reject", "List the files like this." in T and msg(11648) in T and "who.am.i" in T
         and "Run" in T and "Cancel" in T, T[-800:])
    h.key("enter", idle=1.5)
    arow("L10", "Enter alone rejects it: nothing ran (the home screen is still under, no command output)", h.home() and "Account" not in h.text().split("AI>")[0][-300:], repr(h.text()[:120]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("who am i [[cmd_list]]")
    h.typed("r", idle=3.0)
    O = h.text()
    # SOLO: WHO.AM.I prints "Account : sduser" (sandbox-home-solo.py has the same pattern), which no part of the home screen does
    arow("L10b", "Run runs it as the Terminal would: the command's output (Account : sduser) is on the screen and the terminal waits for Enter", re.search(r"Account\s*:\s*sduser", O) is not None, O[-500:])
    h.key("enter", idle=3.0)
    arow("L10c", "Enter brings the home screen back", h.home(), repr(h.text()[:100]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("odd [[cmd_tab]]")
    arow("L10d", "a command with a tab in it is not shown (11650) and not offered", msg(11650) in T and "Run" not in T, T[-600:])
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("long [[cmd_long]]")
    arow("L10e", "a command of 300 characters is not shown (11650) and not offered", msg(11650) in T and "Run" not in T, T[-600:])
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()
    # the forms the reply may take
    h, T = reply("fence [[fenced]]")
    arow("L11", "an object inside a code fence with words round it is read: the IDE is proposed (the Record editor until its tile went, S.88 g-P1)", "From a fence." in T and msg(11647, "IDE - programs and files") in T, T[-700:])
    h.key("esc", idle=1.5)
    arow("L11b", "Esc on the popup is Reject: the home screen, nothing started", h.home(), repr(h.text()[:100]))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("plain words [[notjson]]")
    arow("L12", "words that are not a JSON object are shown as they are with the note (11651) and nothing is proposed", "I would start the editor, I think." in T and msg(11651) in T and "Accept" not in T, T[-600:])
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("just talk [[sayonly]]")
    arow("L13", "a say with action none and no command is shown with Close only", "Nothing to do here" in T and "Close" in T and "Accept" not in T, T[-500:])
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("arg [[argbad]]")
    arow("L14", "an argument with characters the line does not allow is dropped: the proposal is shown without it", msg(11647, "IDE - programs and files") in T and "rm -rf" not in T, T[-600:])
    h.key("esc", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()
    h, T = reply("orders [[hostile]]")
    arow("L14b", "a say that gives orders is only text: shown, no command offered, the screen is whole", "Ignore the person" in T and "Run" not in T and "Accept" not in T, T[-500:])
    h.key("enter", idle=1.5)
    arow("L14c", "...and nothing ran", h.home(), "")
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_wait():
    say("\n--- giving the request up")
    h = home()
    ask(h, "slow [[slow]]")
    h.typed("s", idle=1.0)
    arow("L15a", "while the AI is answering the line says so and Esc gives it up", msg(11645) in line_row(h), repr(line_row(h)[:100]))
    h.key("esc", idle=1.5)
    arow("L15", "Esc: the request is given up (the status line says so), no popup, the home screen", msg(11646) in h.line(40) and h.home() and "Accept" not in h.text(), repr((h.line(40)[:80], h.home())))
    time.sleep(3.5)
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_admin():
    say("\n--- the administrator's page (ADMIN at the prompt, then HOME)")
    h = home(admin=True)
    if not h.home():
        dump(h)
        bail("the administrator's home screen never drew, so no L16 row can be believed")
    arow("L16a", "the administrator's page has the AI line too", line_row(h).lstrip().startswith("AI>"), repr(line_row(h)[:80]))
    n0 = len(fm().log)
    ask(h, "plain ask")
    h.typed("s", idle=4.0)
    rq = requests()
    prompt = rq[-1][2]["messages"][-1]["content"] if len(rq) > n0 else ""
    arow("L16b", "its list has the administrator's tiles (Menu management, Bypass programs) and says the person is the administrator", "  menus:Menu management" in prompt and "  viewers:Bypass programs" in prompt
         and "the administrator." in prompt, repr(prompt[:500]))
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_follow():
    """11 Nov 26 (carried from Core's sec_follow of 3 Nov; Core's ids are L16a-d, which are Solo's administrator rows): Follow up on the home screen.  The earlier exchange is read
    where it ARRIVES (the fake) and in the audit file.  Until 11 Nov 26 Solo's helper had no handling of "history": the kernel sent it and the helper dropped it, so L18d's
    three messages were one."""
    say("\n--- Follow up on the home screen (the helper's history, carried 11 Nov 26)")
    h = home()
    ask(h, "first question [[sayonly]]")
    h.typed("s", idle=4.0)
    T = h.text()
    arow("L18a", "the answer's box has Follow up beside Close", "Follow up" in T and "Close" in T, T[-500:])
    h.typed("f", idle=1.5)
    arow("L18b", "Follow up applies nothing: the home screen is back and the AI line says a follow-up is waiting", h.home() and "follow-up" in line_row(h).lower(), repr(line_row(h)[:80]))
    n0, a0 = len(fm().log), ai.audit_off()
    ask(h, "second question [[plain]]")
    T = h.text()
    arow("L18c", "the follow-up's preview shows the earlier question; nothing is sent yet", "first question [[sayonly]]" in T and len(fm().log) == n0, T[-1200:])
    h.typed("s", idle=4.0)
    rq = requests()
    body = (rq[-1][2] or {}) if len(rq) > n0 else {}
    msgs = body.get("messages", []) if body else []
    rl = ai.req_lines(ai.audit_new(a0) or "")
    arow("L18d", "Send: ONE request, carrying the earlier question and answer as the user's and the assistant's messages before the request, and the audit line says followup=1",
         len(fm().log) == n0 + 1 and len(msgs) == 3 and msgs[0].get("role") == "user" and msgs[0].get("content", "").endswith("first question [[sayonly]]") and msgs[1].get("role") == "assistant"
         and "Nothing to do here" in str(msgs[1].get("content", "")) and str(msgs[2].get("content", "")).endswith("second question [[plain]]") and len(rl) == 1 and "followup=1" in rl[0],
         repr(([(m.get("role"), str(m.get("content"))[-60:]) for m in msgs], rl)))
    h.key("enter", idle=1.5)
    h.key("ctrl-q", idle=1.5)
    h.end()


def sec_context():
    """11 Nov 26 (carried from Core's sec_context, S.160): the standing text.  It is put where the stager and SET.AI put it (beside the providers file; the helper's state directory)
    and read where it arrives.  Until 11 Nov 26 Solo's helper gave no "context" in its status, so the system text began with the instruction and L17b / L17c could not pass."""
    say("\n--- the standing text (Core S.160, carried 11 Nov 26)")
    dflt = os.path.join(os.path.dirname(ai.STATE["providers"]), "ai-context")
    own = os.path.join(ai.box(), "ai", "state", "context")
    shutil.copyfile(os.path.join(HERE, "ai-context"), dflt)
    put(own, "Our site ZQX9 keeps its invoices in the file inv.\nSecond line of ours.\n")
    h = None
    try:
        h = home()
        n0 = len(fm().log)
        ask(h, "what is a select list [[sayonly]]")
        T = h.text()
        arow("L17a", "the preview shows NOTHING of the standing text (no heading, no line of it) nor the instruction; the request is shown; nothing is sent yet",
             "ZQX9" not in T and "Second line of ours." not in T and "Standing" not in T and "You help a person" not in T and "what is a select list" in T and len(fm().log) == n0, T[-1500:])
        h.typed("s", idle=4.0)
        rq = requests()
        body = (rq[-1][2] or {}) if len(rq) > n0 else {}
        sysx = ""
        try:
            sysx = body["system"][0]["text"]
        except (KeyError, IndexError, TypeError):
            pass
        prompt = body["messages"][-1]["content"] if body.get("messages") else ""
        arow("L17b", "Send: the system text that arrives BEGINS with 'Standing information from the administrator of this SD system:' and the two lines, then the instruction; "
             "the person's request is unchanged (the prompt ends with it and holds nothing of the standing text)",
             sysx.startswith("Standing information from the administrator of this SD system:\nOur site ZQX9 keeps its invoices in the file inv.\nSecond line of ours.\n\n")
             and "You help a person who is using home" in sysx and prompt.endswith("Request: what is a select list [[sayonly]]") and "ZQX9" not in prompt, repr((sysx[:200], prompt[-80:])))
        h.key("enter", idle=1.5)
        os.remove(own)
        n0 = len(fm().log)
        ask(h, "what is a select list [[sayonly]]")
        T = h.text()
        h.typed("s", idle=4.0)
        rq = requests()
        body = (rq[-1][2] or {}) if len(rq) > n0 else {}
        sysx = ""
        try:
            sysx = body["system"][0]["text"]
        except (KeyError, IndexError, TypeError):
            pass
        arow("L17c", "with no text of the administrator's, the shipped default (Solo's) is what is sent first, and the preview showed none of it",
             "About this system: SD Core for Linux Solo" not in T
             and sysx.startswith("Standing information from the administrator of this SD system:\nAbout this system: SD Core for Linux Solo") and "Answer briefly and plainly." in sysx, repr(sysx[:200]))
        h.key("enter", idle=1.5)
        put(own, "Please explain gpl.bp to everyone.\n")
        n0, a0 = len(fm().log), ai.audit_off()
        ask(h, "what is a select list [[sayonly]]")
        aud = ai.audit_new(a0) or ""
        arow("L17d", "a standing text that names SD's own code (written past SET.AI, straight into the helper's file) sends NOTHING: no preview, the fake saw nothing, "
             "the status line says why (14013) and the trail says 'ai refused why=context'", len(fm().log) == n0 and "Send" not in h.text()[-600:]
             and "names SD's own code" in h.line(40) and "ai refused why=context app=home name=gpl.bp" in aud, repr((h.line(40)[:120], aud[-200:])))
        h.key("ctrl-q", idle=1.5)
    finally:
        if h is not None:
            h.end()
        for p in (own, dflt):
            if os.path.exists(p):
                os.remove(p)


def main():
    mutant = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--mutant=")), None)
    if mutant is not None and mutant not in MUTANTS:
        bail("usage: sandbox-ai-line-solo.py <dir> [--build] [--mutant=%s]" % "|".join(MUTANTS))
    try:
        sh.start_sandbox()
        sh.arrange("terminal")
        ai.setup_ai(None)                       # the fake, the providers file, the helper's runner, SD_AI_SOCKET and SD_AI_CTL (and setai / ai / tool_ai compiled)
        setup_line(mutant)
        configure()
        if mutant is None:
            sec_off()
            sec_ring()
            sec_preview()
            sec_send()
        if mutant == "no-preview":
            sec_preview()                       # the row that holds Cancel (L6) is in this section
        else:
            sec_proposals()
        if mutant is None:
            sec_wait()
            sec_admin()
            sec_follow()                        # 11 Nov 26: the helper's history and the standing text, carried from SD Core
            sec_context()
    finally:
        ai.teardown_ai()
        sh.teardown()
    say("\nsandbox-ai-line-solo: %d passed, %d failed" % (sh.passed, sh.failed))
    if mutant is not None:
        want = sorted(set(MUTANTS[mutant][2]))
        got = sorted({re.match(r"L\d+", i).group(0) for i in FAILED_IDS if re.match(r"L\d+", i)})
        ok = want == got
        say("sandbox-ai-line-solo: MUTANT %s: the rows that failed are %s; they had to be exactly %s -> %s" % (mutant, got, want, "KILLED BY ITS OWN ROWS" if ok else "NOT AS EXPECTED"))
        return 0 if ok else 1
    return 0 if sh.failed == 0 and sh.passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
