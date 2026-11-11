#!/usr/bin/env python3
#
# sandbox-ai-solo.py - SET.AI, the ai verb, the kernel's transport (K$AI.*) and the AI choice page TOOL.AI, RUN on a private SD Core for Linux Solo
#                      (SOLO CARRY 15 of S.69 step 2, 23 Oct 2026).  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-ai-solo.py <dir> [--build] [--mutant=NAME]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent).  Exit 0 every row passed, 1 a row failed, 2 it
# could not run.  With --mutant=NAME one change is made to the SANDBOX'S OWN COPY of a program and exit 0 means the rows that had to fail failed and no others (MUTANTS below).
# Solo's counterpart of Core's sandbox-aigate.py (part 2), sandbox-ai-verb.py and sandbox-tool-ai.py, whose rows these are adapted from.
#
# WHAT RUNS.  The helper (gplbld/sd-ai, Solo's: it runs as the user and its gate is a setting) is served by ai-runner.py on a Unix socket as the user unit would serve it; the provider
# is gplbld/fakemodel.py, TLS with a throw-away CA, which LOGS every request, so a row can say what was sent and what was not.  The sessions are the account's own (a plain session of
# sduser on a PIPE, or on a pseudo-terminal), the administrator's (ADMIN at the prompt) and an INTERNAL one; the sandbox's kernel finds the helper through SD_AI_SOCKET (op_ai.c; the
# product never sets it) and SET.AI finds the helper's client through SD_AI_CTL.
#
# THE INSTRUMENT.  Every outcome is read from the DISK or the AUDIT TRAIL or the fake's request log, not from what a verb or the page said: ai.conf, the key file, the audit file.  A row
# that says "nothing was sent" is judged by the fake's log; the control row V4 sees one request arrive, and a null run (the provider never reached) fails its rows, it does not pass them.
#
#   A0-A8   SET.AI: an ordinary session is refused and nothing changes; the reading form; the gate (on, off, a word that is neither); provider, model, custom, ca-file, limit, each with
#           its message, its ai.conf line and one audit line; a word with a character it may not have runs nothing; the key typed on a pseudo-terminal at the helper's own prompt,
#           in the key file (mode 0600) and in no message, no screen byte and no audit line; the helper not running
#   V0-V17  the ai verb: no text, no provider, no model, no key -> the verb's words and the fake saw nothing; the control (preview, answer, ONE request with the right key, model, system
#           text and text, ONE audit line); anything but yes sends nothing; what arrives (quotes, odd characters, bytes above 127); failures of the provider; the helper's own limit;
#           the GATE OFF (V12): 11625 before the preview, nothing sent
#   P1-P4   an INTERNAL probe calling K$AI.START itself: the audit line names the real program; the helper refuses with the gate off (P2); no helper -> ERR nohelper; a program that is
#           not $internal cannot compile a KERNEL call
#   T0-T22  the page, driven on a 140 by 43 pseudo-terminal: the boxes, the five providers with their starting models, Enter on a provider (Cancel, a wrong name, the right one),
#           S, THE SETUP DIALOG (11 Nov 26, carried from SD Core S.170 / S.171; T5-T9: K and M gone, the key a masked entry handed to the helper by the hand-over file and in no
#           other file of the sandbox (T6f), the list of models from the fake, the keep-stars, Other name checked against the list, Esc, SET.AI MODEL's warning and SET.AI MODELS),
#           X, C, D, L, A, the Account box (the gate: Enter asks for the word ai before it turns the gate ON, none to turn it OFF), the helper not running, a window that is too small
#   C0-C8, T30-T38  (11 Nov 26, carried from SD Core's S.160) the standing text: set.ai context hex | - (an ordinary session refused, the helper's file mode 0600, the audit line
#           with the size and no text, a text that names SD's own code refused, a word that is not hexadecimal); the ai verb sends it FIRST in the system text and shows none of it,
#           its size counted; a kept text that names the code sends nothing; the shipped default; and the page's T box (Esc, Save and Run, Shipped default)
# NOT HELD: the installer, the real systemd user socket (test-ai-solo-units.py reads solo-service.sh's units as text), a real provider (the owner's live check), a second operating system
# user (Solo has none: that is the point of the same-user helper, and the page and the help text say so).
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sh = _load("sandbox_home_solo_for_ai", "sandbox-home-solo.py")
import fakemodel  # noqa: E402

say, has, put, bail, dump, plain, adm, H = sh.say, sh.has, sh.put, sh.bail, sh.dump, sh.plain, sh.adm, sh.H
KEY = "test-key-0123456789"
MODEL = "claude-test"
FAILED_IDS = []
STATE = {}


def row(name, ok, detail=""):
    sh.row(name, ok, detail)
    if not ok:
        FAILED_IDS.append(name.split()[0])


MUTANTS = {
    # name: (program of the sandbox, old text, new text, the row ids that must fail and no others)
    "gate-word-wrong": ("setai", "         qargs = \"'gate' '\" : gstate : \"'\"", "         qargs = \"'gate' 'off'\"", ["A2"]),
    "no-gate-check": ("ai", "   if not(st{'gate'}) then", "   if @false then", ["V12"]),
    "no-preview": ("ai", "   if ans # 'y' and ans # 'yes' then", "   if @false then", ["V5", "V6", "V7", "V8"]),
    "no-typed-gate": ("tool_ai", "      typed = 'ai'\n", "      typed = ''\n", ["T18", "T19"]),     # T19 turns the gate off after T18 turned it on: with no word asked T18's Run is the one that fails and T19 follows from its state
}


def box():
    return sh.BOX


def sysdir():
    return sh.SYS


def msg(n, *args):
    with open(os.path.join(sysdir(), "messages", str(n)), encoding="utf-8") as f:
        t = f.read().rstrip("\n")
    for i, a in enumerate(args, 1):
        t = t.replace("%" + str(i), str(a))
    return t


def conf():
    p = os.path.join(box(), "ai", "state", "ai.conf")
    try:
        return [ln.rstrip("\n") for ln in open(p, encoding="ascii")] if os.path.exists(p) else []
    except OSError:
        return []


def conf_text():
    p = os.path.join(box(), "ai", "state", "ai.conf")
    return open(p, encoding="ascii").read() if os.path.exists(p) else None


def keyfile(p):
    return os.path.join(box(), "ai", "state", "keys", p)


def settings(lines=None):
    return [l for l in (conf() if lines is None else lines) if l and not l.startswith("#")]


def audit_off():
    return sh.audit_size()


def audit_new(off):
    return sh.audit_tail(off)


def req_lines(audit):
    return [ln for ln in audit.split("\n") if re.search(r"\bai request\b", ln)]


def requests(fm):
    out = []
    for r in fm.log:
        try:
            body = json.loads(r["body"].decode("utf-8"))
        except ValueError:
            body = None
        out.append((r["path"], r["headers"], body))
    return out


def prompt_of(body):
    return body["messages"][-1]["content"]


def verb_source():
    return open(os.path.join(TREE, "sdsys", "gpl.bp", "ai"), encoding="utf-8").read()


def system_text():
    m = re.search(r"^\s*system\.text = '([^']+)'", verb_source(), re.M)
    if not m:
        bail("the verb's fixed system sentence was not found in the source")
    return m.group(1)


def ask(cmds, label, fm, who="user"):
    """Run the commands in the account's session (or the internal one) and say what the fake and the audit file saw."""
    off = audit_off()
    n0 = len(fm.log)
    out = plain(cmds) if who == "user" else adm(*cmds)
    new = audit_new(off)
    say("    [%s] output: %r" % (label, out[-12:]))
    say("    [%s] requests the fake provider had: %d; audit gained: %r" % (label, len(fm.log) - n0, new))
    return out, len(fm.log) - n0, new or ""


def start_runner():
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "ai-runner.py"), "--socket", os.path.join(box(), "ai", "sock"), "--state", os.path.join(box(), "ai", "state"),
                          "--providers", STATE["providers"]], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if p.stdout.readline().strip() != "ready":
        bail("the AI helper's runner did not start")
    STATE["runner"] = p
    return p


def stop_runner():
    p = STATE.get("runner")
    if p is not None:
        try:
            p.terminate()
            p.wait(timeout=10)
        except Exception:
            pass
    STATE["runner"] = None


def compile_prog(name):
    out = adm("BASIC gpl.bp " + name)
    if not has(out, r"^Compiled 1 program\(s\) with no errors"):
        bail("%s did not compile in the sandbox:\n%s" % (name, "\n".join(out[-6:])))


def setup_ai(mutant):
    shutil.rmtree(os.path.join(box(), "ai"), ignore_errors=True)
    os.makedirs(os.path.join(box(), "ai", "pki"))
    pki = fakemodel.make_pki(os.path.join(box(), "ai", "pki"))
    fm = fakemodel.FakeModel(pki).start()
    providers = os.path.join(box(), "ai", "ai-providers")
    text = open(os.path.join(HERE, "ai-providers")).read()
    for old, new in (("https://api.anthropic.com/v1/messages", "https://127.0.0.1:%d/v1/messages" % fm.port),
                     ("https://api.openai.com/v1/chat/completions", "https://127.0.0.1:%d/v1/chat/completions" % fm.port),
                     ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "https://127.0.0.1:%d/v1beta/openai/chat/completions" % fm.port),
                     ("https://api.deepseek.com/chat/completions", "https://127.0.0.1:%d/chat/completions" % fm.port)):
        if old not in text:
            bail("the shipped ai-providers has no %s: the suite cannot point it at the fake" % old)
        text = text.replace(old, new)
    put(providers, text)
    defaults = re.findall(r"^model=(.*)$", text, re.M)                  # 11 Nov 26: the starting models, in the file's order (anthropic, openai, google, deepseek)
    if len(defaults) != 4:
        bail("the shipped ai-providers does not give four starting models: %r" % defaults)
    STATE.update(fm=fm, pki=pki, providers=providers, ca=os.path.join(pki, "ca.crt"), port=fm.port, defaults=defaults)
    # the programs of the tree (a sandbox used for an earlier mutant starts from the tree's again), then the mutant's one change
    for n in ("setai", "ai", "tool_ai"):
        shutil.copyfile(os.path.join(TREE, "sdsys", "gpl.bp", n), os.path.join(sysdir(), "gpl.bp", n))
    if mutant is not None:
        prog, old, new, _kills = MUTANTS[mutant]
        path = os.path.join(sysdir(), "gpl.bp", prog)
        src = open(path, encoding="utf-8", errors="replace").read()
        if src.count(old) != 1:
            bail("mutant %s: the text to change is found %d times, not once" % (mutant, src.count(old)))
        put(path, src.replace(old, new))
        say("sandbox-ai-solo: MUTANT %s: %s changed; the rows that must fail, and nothing else: %s" % (mutant, prog, ", ".join(MUTANTS[mutant][3])))
    for n in ("setai", "ai", "tool_ai"):
        compile_prog(n)
    start_runner()
    os.environ["SD_AI_SOCKET"] = os.path.join(box(), "ai", "sock")
    os.environ["SD_AI_CTL"] = os.path.join(HERE, "sd-ai-ctl")


def teardown_ai():
    stop_runner()
    if "fm" in STATE:
        STATE["fm"].stop()
    os.environ.pop("SD_AI_SOCKET", None)
    os.environ.pop("SD_AI_CTL", None)


# ----------------------------------------------------------------------------------------------------------------------------------------- SET.AI

def sec_setai():
    say("\n=== SET.AI ===")
    out = plain(["WHO.AM.I"])
    flag = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    if not (flag and flag.group(1) == "No"):
        bail("the ordinary session is privileged; its refusals prove nothing")
    a0 = audit_off()
    out = plain(["set.ai provider anthropic"])
    row("A0 an ORDINARY session is refused (2001) and nothing changes: no ai.conf line, no audit line", has(out, r"Command requires administrator privileges") and not settings()
        and "set.ai" not in audit_new(a0), repr((out[-3:], conf())))
    out = adm("set.ai")
    row("A1 the reading form, nothing set: the AI is off, the gate is off, five rows with the shipped addresses (the fake's here), none checked, no key",
        has(out, r"^AI provider in use: none \(the AI is off\)") and has(out, r"^\s+gate: off$") and sum(1 for l in out if l.startswith("  [ ] ")) == 5
        and has(out, r"https://127\.0\.0\.1:%d/v1/messages" % STATE["port"]), repr(out[:8]))
    a1 = audit_off()
    out = adm("set.ai gate on")
    new = audit_new(a1)
    row("A2 SET.AI GATE ON: 'The AI gate is now on' (11606), ai.conf holds exactly the line gate=yes, one audit line 'set.ai gate=on'",
        msg(11606, "on") in out and "gate=yes" in settings() and len(re.findall(r"set\.ai gate=on$", new, re.M)) == 1, repr((out[-2:], conf(), new[-120:])))
    out = adm("set.ai")
    row("A2b the reading form now says gate: on", has(out, r"^\s+gate: on$"), repr(out[:4]))
    a1 = audit_off()
    out = adm("set.ai gate off")
    row("A2c SET.AI GATE OFF: 11606 with off, the gate line is gone from ai.conf (off is the absence), one audit line",
        msg(11606, "off") in out and not any(l.startswith("gate") for l in conf()) and len(re.findall(r"set\.ai gate=off$", audit_new(a1), re.M)) == 1, repr((out[-2:], conf())))
    before = conf_text()
    a1 = audit_off()
    out = adm("set.ai gate maybe")
    row("A2d a gate word that is neither on nor off is the usage (11609) and changes nothing", msg(11609) in out and conf_text() == before and "set.ai" not in audit_new(a1), repr(out[-2:]))
    a1 = audit_off()
    out = adm("set.ai provider anthropic")
    new = audit_new(a1)
    row("A3 SET.AI PROVIDER anthropic: 11611, ai.conf holds provider=anthropic, one audit line 'set.ai provider=anthropic'",
        msg(11611, "anthropic") in out and "provider=anthropic" in settings() and len(re.findall(r"set\.ai provider=anthropic$", new, re.M)) == 1, repr((out[-2:], conf(), new[-120:])))
    out = adm("set.ai provider martian")
    row("A3b a provider that is none of the four: 11610, nothing changed", msg(11610, "martian") in out and "provider=anthropic" in settings(), repr(out[-2:]))
    out = adm("set.ai model anthropic " + MODEL)
    row("A4 SET.AI MODEL: 11613, model.anthropic in ai.conf", msg(11613, "anthropic", MODEL) in out and ("model.anthropic=" + MODEL) in settings(), repr((out[-2:], conf())))
    out = adm("set.ai ca " + STATE["ca"], "set.ai limit requests-hour 1000")
    row("A5 SET.AI CA and LIMIT (the delivered 20 requests an hour is more than this suite sends): 11619 and 11621, both in ai.conf",
        msg(11619, STATE["ca"]) in out and msg(11621, "requests-hour", "1000") in out and ("ca-file=" + STATE["ca"]) in settings() and "limit.requests-hour=1000" in settings(), repr((out[-3:], conf())))
    url = "https://127.0.0.1:%d/v1/chat/completions" % STATE["port"]
    a1 = audit_off()
    out = adm("set.ai custom MyLLM %s openai bearer - max_tokens" % url)
    new = audit_new(a1)
    row("A6 SET.AI CUSTOM: 11617, the connection in ai.conf, the audit line names the host and not the address",
        msg(11617, "MyLLM", "127.0.0.1:%d" % STATE["port"]) in out and ("custom.url=" + url) in settings() and re.search(r"set\.ai custom name=MyLLM host=127\.0\.0\.1:%d$" % STATE["port"], new, re.M)
        and "/v1/chat/completions" not in new, repr((out[-2:], new[-160:])))
    out = adm("set.ai custom clear")
    row("A6b SET.AI CUSTOM CLEAR: 11618, no custom line left", msg(11618) in out and not any(l.startswith("custom.") for l in conf()), repr((out[-2:], conf())))
    sentinel = os.path.join(box(), "ai", "ran-not")
    out = adm("set.ai model anthropic x;touch%s" % sentinel.replace("/", "_"), "set.ai model anthropic a$(touch " + sentinel + ")")
    row("A7 a word with a character that is not allowed (a semicolon, a dollar, a bracket) runs nothing: 11622, no sentinel file", not os.path.exists(sentinel)
        and any(l.startswith(msg(11622, "")[:12]) or "not allowed here" in l for l in out), repr(out[-3:]))
    # the key, on a pseudo-terminal: the helper's own prompt
    say("\n--- the key")
    a1 = audit_off()
    h = H(admin=True)
    h.typed("set.ai key anthropic\r", idle=2.0)
    scr = h.text()
    row("A8a the prompt is the helper's own: 'Key for anthropic (not shown):' is on the screen", "Key for anthropic (not shown):" in scr, scr[-300:])
    h.typed(KEY[:6], idle=0.7)
    row("A8b what is typed at the prompt is not shown", KEY[:6] not in h.text(), h.text()[-300:])
    h.typed(KEY[6:] + "\r", idle=2.5)
    scr = h.text()
    new = audit_new(a1)
    kp = keyfile("anthropic")
    row("A8c SD says the key is set (11615); the key file is mode 0600 and holds it; the audit trail has 'set.ai key set provider=anthropic' and no key; the key is in NO byte the terminal got",
        msg(11615, "anthropic") in scr and os.path.exists(kp) and open(kp).read().strip() == KEY and (os.stat(kp).st_mode & 0o777) == 0o600
        and re.search(r"set\.ai key set provider=anthropic$", new, re.M) and KEY not in new and KEY.encode() not in h.s.raw and KEY not in scr, repr((scr[-200:], os.path.exists(kp), new[-160:])))
    h.end()
    out = adm("set.ai")
    row("A8d the reading form shows the key as set and prints no key", has(out, r"key: set") and not any(KEY in l for l in out), repr(out[:8]))
    os.remove(kp)


# --------------------------------------------------------------------------------------------------------------------------------------- the ai verb

def sec_verb():
    say("\n=== the ai verb ===")
    fm = STATE["fm"]
    sysx = system_text()
    adm("set.ai provider none", "set.ai gate off", "set.ai model anthropic -")          # the model section A set is cleared: V2 needs a provider with no model
    out, n, aud = ask(["ai"], "V0", fm)
    row("V0 no text: the usage (11623), nothing sent, no 'ai request' audit line", msg(11623) in out and n == 0 and not req_lines(aud), repr(out[-4:]))
    out, n, aud = ask(["ai hello", "y"], "V1", fm)
    row("V1 no provider is chosen: 11624 (the AI is off), no preview, nothing sent, no audit line", msg(11624) in out and n == 0 and not req_lines(aud)
        and not any(ln.startswith("This will be sent to") for ln in out), repr(out[-4:]))
    adm("set.ai provider anthropic")
    out, n, aud = ask(["ai hello", "y"], "V12a", fm)
    row("V12a a provider, the gate OFF (as delivered): 11625 (turn it on with set.ai gate on), no preview, nothing sent, no audit line", msg(11625) in out and n == 0 and not req_lines(aud)
        and not any(ln.startswith("This will be sent to") for ln in out), repr(out[-4:]))
    adm("set.ai gate on")
    out, n, aud = ask(["ai hello", "y"], "V2", fm)
    row("V2 a named provider with no model set has its starting model (11 Nov 26), so what is missing is the key: 11626 (anthropic, key), not (anthropic, model); no preview, nothing sent",
        msg(11626, "anthropic", "key") in out and msg(11626, "anthropic", "model") not in out and n == 0 and not req_lines(aud), repr(out[-4:]))
    adm("set.ai model anthropic " + MODEL)
    out, n, aud = ask(["ai hello", "y"], "V3", fm)
    row("V3 a model and no key: 11626 (anthropic, key), no preview, nothing sent", msg(11626, "anthropic", "key") in out and n == 0 and not req_lines(aud), repr(out[-4:]))
    kp = keyfile("anthropic")
    put(kp, KEY + "\n")
    os.chmod(kp, 0o600)

    q = "what is the answer"
    out, n, aud = ask(["ai " + q, "y"], "V4", fm)
    rq = requests(fm)
    last = rq[-1] if rq else (None, {}, None)
    body = last[2] or {}
    size = len(q) + len(sysx)
    # 11 Nov 26 (S.117, Core's S.175): SD's fixed sentence is sent and counted in the size (row V4c reads it in the request) and is NOT shown in the preview
    row("V4a the preview names the provider, the model and the size (the fixed sentence counted), shows the text and NOT the fixed sentence, then asks", msg(11628, "anthropic", MODEL, size) in out and sysx not in out and q in out
        and any(ln.startswith(msg(11629)) for ln in out), repr(out[:8]))
    row("V4b the answer is printed as text, with the token line (11634) and no failure line", fakemodel.PLAIN_TEXT in out and msg(11634, 11, 7, "anthropic") in out
        and not any(ln.startswith("The AI did not answer") for ln in out), repr(out[-6:]))
    row("V4c ONE request reached the provider, with the key in the right header, the model, the fixed system sentence, the limit of 1024 tokens and exactly the text that was typed",
        n == 1 and last[0] == "/v1/messages" and last[1].get("x-api-key") == KEY and body.get("model") == MODEL and body.get("max_tokens") == 1024 and prompt_of(body) == q
        and body.get("system", [{}])[0].get("text") == sysx and sorted(body.keys()) == ["max_tokens", "messages", "model", "system"] and len(body["messages"]) == 1, repr((n, last[0], body)))
    rl = req_lines(aud)
    row("V4d ONE audit line, written by the kernel: account, the program's name and the size; the text and the key are in no audit line",
        len(rl) == 1 and re.search(r"ai request account=sduser program=ai bytes\.out=%d$" % size, rl[0]) is not None and q not in aud and KEY not in aud, repr(rl))
    row("V4e the key is on no screen line", not any(KEY in ln for ln in out), repr(out[:3]))

    for rid, label, answer in (("V5", "n", "n"), ("V6", "an empty answer", ""), ("V7", "'yep'", "yep")):
        out, n, aud = ask(["ai " + q, answer], rid, fm)
        row("%s the answer %s: 11630 ('Nothing was sent'), nothing at the provider, no audit line" % (rid, label), msg(11630) in out and n == 0 and not req_lines(aud), repr(out[-3:]))
    out, n, aud = ask(["ai " + q], "V8", fm)
    row("V8 the input ends at the question (the session's next line is OFF): nothing is sent, as for a pipe that has ended", n == 0 and not req_lines(aud) and msg(11630) in out, repr(out[-3:]))
    out, n, aud = ask(["ai " + q, "Y"], "V8b", fm)
    row("V8b 'Y' is yes (case does not matter): one request, the answer is printed", n == 1 and fakemodel.PLAIN_TEXT in out and len(req_lines(aud)) == 1, repr(out[-4:]))
    out, n, aud = ask(["ai " + q, "yes"], "V8c", fm)
    row("V8c 'yes' is yes", n == 1 and fakemodel.PLAIN_TEXT in out, repr(out[-4:]))

    out, n, aud = ask(['ai "what is a select list?"', "y"], "V9", fm)
    got = prompt_of(requests(fm)[-1][2]) if n else None
    row("V9 a pair of double quotes round the text is taken off; the preview shows the text without them", got == "what is a select list?" and "what is a select list?" in out, repr((got, out[:5])))
    odd = "a\\b $c \"d\" 'e' ; | & `f` {g} <h> * . ? x"
    out, n, aud = ask(["ai " + odd, "y"], "V10", fm)
    got = prompt_of(requests(fm)[-1][2]) if n else None
    row("V10 a backslash, dollar, both quotes, semicolon, pipe, ampersand, backtick, braces, angle brackets, a star and a question mark inside arrive exactly as typed", got == odd, repr((got, odd)))
    out, n, aud = ask(["ai what is it?", "y"], "V10b", fm)
    row("V10b text that ENDS with ? is not run (TCL adds a command that ends with ? to the stack without running it): no preview, nothing sent, which is why 11623 says to quote it",
        n == 0 and not req_lines(aud) and not any(ln.startswith("This will be sent to") for ln in out) and "quotes" in msg(11623), repr(out[-3:]))
    out, n, aud = ask(["ai café au lait", "y"], "V11", fm)
    got = prompt_of(requests(fm)[-1][2]) if n else None
    row("V11 bytes above 127 become ? on the way out (English only; each byte of the two that make an e-acute)", got == "caf?? au lait", repr(got))

    for rid, marker, check, what in (
            ("V14", "[[err500]]", lambda o: any(ln.startswith("The AI did not answer: ") for ln in o) and not any("Traceback" in ln for ln in o), "words, and no traceback"),
            ("V15", "[[ctrl]]", lambda o: any(ln.startswith("Fine.") for ln in o), "the text, with nothing that moves the cursor"),
            ("V16", "[[trunc]]", lambda o: msg(11632) in o, "the cut said (11632)")):
        out, n, aud = ask(["ai " + marker + " tell me", "y"], rid, fm)
        row("%s the provider answers %s: %s" % (rid, marker, what), check(out) and n >= 1 and not any(("\x1b" in ln or "\x07" in ln) for ln in out), repr(out[-6:]))

    adm("set.ai limit requests-hour 1")
    out, n, aud = ask(["ai hello", "y"], "V17", fm)
    adm("set.ai limit requests-hour 1000")
    row("V17 the helper's hourly limit is reached: the verb says so in words (11627, 'limit'), nothing reached the provider, and the audit line is there all the same",
        any(ln.startswith("The AI did not answer: limit (") for ln in out) and n == 0 and len(req_lines(aud)) == 1, repr(out[-3:]))
    adm("set.ai gate off")
    out, n, aud = ask(["ai hello", "y"], "V12", fm)
    row("V12 the gate turned off again after it had been on: 11625 before the preview, nothing sent (the helper looks at the setting at every request)", msg(11625) in out and n == 0
        and not any(ln.startswith("This will be sent to") for ln in out), repr(out[-3:]))
    adm("set.ai gate on")


def sec_probes():
    say("\n=== the internal probe and the program that is not internal ===")
    fm = STATE["fm"]
    put(os.path.join(sysdir(), "gpl.bp", "zzaip"), "\n".join([
        "$internal", "program zzaip", "$catalog $zzaip", "$include keys.h", "$include int$keys.h",
        "   r = kernel(K$AI.START, 'sys':@fm:'64':@fm:'probe question')",
        "   crt 'AIP start=':convert(@fm, '|', r)",
        "   if r<1> = 'OK' then",
        "      for i = 1 to 150",
        "         r = kernel(K$AI.POLL, 0)",
        "         if r<1> # 'W' then exit",
        "         nap 100",
        "      next i",
        "      crt 'AIP poll=':convert(@fm, '|', r)",
        "   end",
        "end", ""]))
    out = adm("BASIC gpl.bp zzaip")
    if not has(out, r"^Compiled 1 program\(s\) with no errors"):
        bail("the probe did not compile:\n" + "\n".join(out[-6:]))
    ni = os.path.join(sh.ACCT, "bp", "zzni")
    os.makedirs(os.path.dirname(ni), exist_ok=True)
    put(ni, "\n".join(["   crt 'NI status=':convert(@fm, '|', kernel(163, 0))",
                       "   crt 'NI start=':convert(@fm, '|', kernel(160, 'sys':@fm:'64':@fm:'not internal'))", "end", ""]))
    n0 = len(fm.log)
    out = plain(["BASIC bp zzni"])
    row("P4 a program that is not $internal cannot call KERNEL() at all: it does not compile (the kernel's own internal-only test in k_ai is the second wall, read as text); nothing is sent",
        has(out, r"Compiled 1 program\(s\) with errors") and has(out, r"KERNEL") and len(fm.log) == n0, repr(out[-4:]))
    out, n, aud = ask(["RUN gpl.bp zzaip"], "P1", fm, who="internal")
    rl = req_lines(aud)
    poll = [ln for ln in out if ln.startswith("AIP poll=D|")]
    row("P1 an internal program calls K$AI.START: the request goes, the reply is the helper's JSON, and the audit line names THAT program (zzaip), not 'ai'",
        n == 1 and len(poll) == 1 and '"t": "ok"' in poll[0] and len(rl) == 1 and "program=zzaip" in rl[0] and "bytes.out=%d" % (len("sys") + len("probe question")) in rl[0], repr((out[-3:], rl)))
    adm("set.ai gate off")
    out, n, aud = ask(["RUN gpl.bp zzaip"], "P2", fm, who="internal")
    poll = [ln for ln in out if ln.startswith("AIP poll=D|")]
    row("P2 the verb is skipped and the kernel is called directly with the gate OFF: the HELPER refuses (nogate), nothing reaches the provider, the audit line is there (the kernel wrote it first)",
        n == 0 and len(poll) == 1 and '"code": "nogate"' in poll[0] and len(req_lines(aud)) == 1, repr((out[-3:], aud[-120:])))
    adm("set.ai gate on")
    stop_runner()
    out, n, aud = ask(["ai hello", "y"], "V13", fm)
    row("V13 the helper is not running: 11607 (could not be reached), nothing sent", msg(11607) in out and n == 0, repr(out[-3:]))
    out, n, aud = ask(["RUN gpl.bp zzaip"], "P3", fm, who="internal")
    row("P3 no helper: K$AI.START answers ERR|nohelper at once (nothing is waiting for an answer that cannot come)", has(out, r"^AIP start=ERR\|nohelper$"), repr(out[-3:]))
    out = adm("set.ai provider openai")
    row("A9 SET.AI with no helper running: 11607 (could not be reached), ai.conf unchanged", msg(11607) in out and "provider=anthropic" in settings(), repr((out[-2:], conf())))
    start_runner()


# ----------------------------------------------------------------------------------------------------------------------------------------- the page

def st(h):
    return h.line(40)


def cell(h, r):
    """The text of a row inside the boxes: from column 3, without the border at column 139 and without the padding."""
    return h.line(r)[3:138].rstrip()


def key_copies(own):
    """11 Nov 26: every file under the sandbox that holds the test key, but the helper's own key file (own).  The key typed in the setup dialog passes through SD's
    session; this says it is not LEFT anywhere: the hand-over directory, the tree, the audit trail, the error log, the helper's state.  A file that cannot be read is named."""
    hits = []
    needle = KEY.encode()
    for root, dirs, files in os.walk(box()):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p) or os.path.abspath(p) == os.path.abspath(own):
                continue
            try:
                stt = os.stat(p)
                if not (stt.st_mode & 0o170000) == 0o100000 or stt.st_size > 64 * 1024 * 1024:     # regular files only (the helper's socket is not one)
                    continue
                with open(p, "rb") as fh:
                    if needle in fh.read():
                        hits.append(p)
            except OSError as e:
                hits.append("%s (unreadable: %s)" % (p, e.__class__.__name__))
    return hits


def f6(h):
    """F6, the key that changes box on every page (the linux terminal's sequence, typed, so that the suite does not depend on the key map of the home suite's H)."""
    h.typed("\x1b[17~", idle=0.8)


def page(cols=140, rows=43):
    h = H(admin=True, cols=cols, rows=rows)
    h.typed("tool.ai\r", idle=3.0)
    return h


def sec_page():
    say("\n=== TOOL.AI ===")
    # the list of models is a real request to the fake provider, whose certificate only the test CA vouches for (11 Nov 26)
    adm("set.ai provider none", "set.ai gate off", "set.ai model anthropic -", "set.ai custom clear", "set.ai ca " + STATE["ca"])
    for p in ("anthropic", "openai", "google", "deepseek", "custom"):
        try:
            os.remove(keyfile(p))
        except OSError:
            pass
    port = STATE["port"]
    out = plain(["tool.ai"])
    row("T0 an ordinary session cannot reach it: 'Command requires administrator privileges'", has(out, r"Command requires administrator privileges|is for the administrator only"), repr(out[:3]))
    a_open = audit_off()
    h = page()
    T = h.text()
    if "What this means" not in T:
        dump(h)
        bail("tool.ai never drew its page, so no row below can be believed")
    row("T0b opening the page writes one audit line, 'tool start app=tool.ai', and changes nothing: no provider, no gate line in ai.conf",
        len(re.findall(r"tool start app=tool\.ai$", audit_new(a_open) or "", re.M)) == 1 and not any(l.startswith(("model.", "custom.", "gate")) for l in settings())
        and "provider=anthropic" not in settings(), repr((audit_new(a_open), conf())))
    row("T1a the four boxes", all(w in T for w in ("AI provider", "The row under the cursor", "May this account use the AI?", "What this means")), T[:400])
    urls = ("https://127.0.0.1:%d/v1/messages" % port, "https://127.0.0.1:%d/v1/chat/completions" % port, "https://127.0.0.1:%d/v1beta/openai/chat/completions" % port,
            "https://127.0.0.1:%d/chat/completions" % port)
    names = ("Anthropic", "OpenAI", "Google", "DeepSeek")
    ok = all(re.match(r"^\[ \] %s\s+%s\s+%s \(default\)\s+not set$" % (re.escape(nm), re.escape(u), re.escape(d)), cell(h, 3 + i))
             for i, (nm, u, d) in enumerate(zip(names, urls, STATE["defaults"])))
    row("T1b the four named providers (Google among them, 11 Nov 26) are filled in with their shipped address and their starting model marked (default), no key, none checked",
        ok, repr([cell(h, r) for r in range(3, 8)]))
    row("T1c the fifth row is Custom, not filled in, no model, nothing checked", re.match(r"^\[ \] Custom\s+\(not filled in\)\s+\(not set\)\s+not set$", cell(h, 7)) is not None, repr(cell(h, 7)))
    row("T1d the summary says the AI is off (no provider is selected) and that the model has a default", h.line(9)[3:].startswith("The AI is OFF: no provider is selected.")
        and "the model has a default" in h.line(9), repr(h.line(9)[3:140]))
    row("T2 a [?] at the end of the Provider box and of the Account box", h.line(2)[134:137] == "[?]" and h.line(25)[134:137] == "[?]", repr((h.line(2)[130:139], h.line(25)[130:139])))
    row("T1e the row under the cursor is described: the Anthropic request layout, the x-api-key header and the version header",
        all(w in h.text() for w in ("anthropic  (the Messages API)", "x-api-key: <key>", "2023-06-01", "max_tokens")), h.text()[1500:2600])

    say("\n--- Enter on a provider")
    a0 = audit_off()
    h.key("enter", idle=1.4)
    T = h.text()
    row("T3a Enter shows the command and its effect: it will ask its default model, and no key is set", "set.ai provider anthropic" in T and "Anthropic will be used" in T
        and ("It will ask its default model, " + STATE["defaults"][0]) in re.sub(r"\s+", " ", T) and "No key is set for it yet" in T, T[-900:])
    h.key("esc", idle=1.0)
    row("T3b Esc is Cancel: nothing was run (the status line says so), ai.conf holds no provider, no audit line", "nothing was run" in st(h) and "provider=anthropic" not in settings()
        and "set.ai" not in audit_new(a0), repr((st(h), conf())))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    T = h.text()
    row("T4a Run asks for the provider's NAME to be typed", "anthropic" in T and re.search(r"[Tt]ype", T) is not None, T[-400:])
    h.typed("nope\r", idle=1.5)
    row("T4b a name that is not the provider's runs nothing", "provider=anthropic" not in settings() and h.line(3)[3:6] == "[ ]", repr((conf(), h.line(3)[3:20])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    h.typed("anthropic\r", idle=2.0)
    new = audit_new(a0)
    row("T4c the right name runs it: Anthropic is checked, ai.conf holds provider=anthropic, the audit trail has one 'set.ai provider=anthropic', and the page says what the verb said",
        h.line(3)[3:6] == "[x]" and "provider=anthropic" in settings() and len(re.findall(r"set\.ai provider=anthropic$", new, re.M)) == 1 and msg(11611, "anthropic") in st(h),
        repr((h.line(3)[3:20], conf(), new[-200:], st(h))))
    row("T4d the summary says what is missing: the key (the model is the default)", ("In use: Anthropic, model %s (default), key not set.  It cannot be used until the key is set" % STATE["defaults"][0]) in h.line(9),
        repr(h.line(9)[3:130]))

    # ------------------------------------------------------------------------------------------ S, the one setup dialog
    # 11 Nov 26, carried from SD Core's S.170 / S.171 (the owner, 8 Nov: "There should be only S for a setup dialog that looks the same no matter if the model and key has been
    # selected previously.  If there are already values they should be displayed.  The model should be selected from a list.  The key in a password type field."; to Solo,
    # 11 Nov: "Carry Core's dialog").  K and M are gone.  Core's rows T5-T9 of sandbox-tool-ai.py, with Solo's rows and the hand-over directory in the Solo tree.
    say("\n--- S: the one setup dialog (carried from SD Core S.170 / S.171)")
    hdir = os.path.join(sysdir(), "$aikey")
    kp = keyfile("anthropic")
    fl = lambda: [l for l in h.text().split("\n") if any(w in l for w in ("AI setup", "Key", "Model", "Other", "list", "set", "fake", "claude", "Save"))]
    gone = lambda: "AI setup:" not in h.text()
    key_before = set(key_copies(kp))          # the files that hold the test key's TEXT before the dialog runs: the suite's own sources in <dir>/tree (measured 11 Nov 26)
    for k_ in ("m", "k"):
        h.typed(k_, idle=1.0)
    row("T5 K and M do nothing any more: no dialog and no Run box opens, the old prompts are gone", gone() and "Model name for" not in h.text() and "set.ai key anthropic" not in h.text(), repr(st(h)))
    a1 = audit_off()
    h.typed("s", idle=1.5)
    T = h.text()
    row("T5a S on a provider with NO key: 'AI setup: Anthropic' with an EMPTY Key entry, the Model list saying the key comes first, Other name, Save and Cancel",
        "AI setup: Anthropic" in T and "set the key first" in T and "Other name" in T and "Save" in T and "No key is set for Anthropic yet" in re.sub(r"\s+", " ", T) and "*****" not in T, repr(fl()))
    h.typed("\r", idle=1.5)
    row("T5b Save with no key is refused in the dialog, which stays; nothing is run", "AI setup: Anthropic" in h.text() and "type or paste it first" in re.sub(r"\s+", " ", h.text())
        and "set.ai" not in (audit_new(a1) or ""), repr(fl()))
    h.typed(KEY, idle=0.8)
    T = h.text()
    row("T6a the key typed into the Key entry is shown as * and not as itself", KEY not in T and ("*" * 10) in T, repr(fl()))
    a2 = audit_off()
    h.key("tab", idle=4.0)
    T = h.text()
    TS = re.sub(r"\s+", " ", T)
    new = audit_new(a2) or ""
    row("T6b Tab out of the Key entry hands the key over and fills the Model list from the provider WITH it; the dialog stays and says the key is set",
        "AI setup: Anthropic" in T and "fake-small" in T and "deepseek-v4-pro" in T and "The key for Anthropic is set" in TS and "set the key first" not in T, repr(fl()))
    row("T6c the key file is the helper's (0600, the key); the audit trail has 'set.ai key set provider=anthropic from=page' and no key; the hand-over file is gone, its directory 0700",
        os.path.exists(kp) and open(kp).read().strip() == KEY and (os.stat(kp).st_mode & 0o777) == 0o600 and re.search(r"set\.ai key set provider=anthropic from=page$", new, re.M) is not None
        and KEY not in new and not os.path.exists(os.path.join(hdir, "key")) and os.path.isdir(hdir) and (os.stat(hdir).st_mode & 0o777) == 0o700, repr((os.path.exists(kp), new[-200:])))
    row("T6d the model in use (the default, " + STATE["defaults"][0] + ") is not in the fake's list, and the dialog says so", ("The model now set, " + STATE["defaults"][0] + ", is not in") in TS, repr(fl()))
    copies = [p for p in key_copies(kp) if p not in key_before]
    outside = [p for p in key_before if not p.startswith(os.path.join(box(), "tree") + os.sep)]
    row("T6f THE KEY IS LEFT NOWHERE BUT THE HELPER'S OWN FILE: after the dialog no file under the sandbox (the Solo tree, its $aikey, the audit trail, the error log, the helper's state) "
        "holds it that did not before, and before it only the suite's own sources in <dir>/tree did (%d files)" % len(key_before),
        copies == [] and outside == [] and os.path.exists(kp), repr((copies, outside)))
    # the list is sorted: claude-test, claude-test-model, deepseek-v4-pro, fake-large, fake-small, gemini-fake; the first is chosen; Tab Tab reaches Save
    h.key("tab", idle=0.5)
    h.key("tab", idle=0.5)
    h.key("enter", idle=3.0)
    row("T6e Save: the dialog is gone, ai.conf holds model.anthropic=claude-test (the entry chosen), and the page says the key is set and the model is now claude-test",
        gone() and ("model.anthropic=" + MODEL) in settings() and "The key for Anthropic is set" in st(h) and ("now " + MODEL) in st(h), repr((st(h), conf())))
    row("T9a back on the page: the row shows the key set, the summary no longer says it cannot be used", re.search(r"claude-test\s+set$", cell(h, 3)) is not None
        and "In use: Anthropic, model claude-test, key set" in h.line(9) and "cannot be used" not in h.line(9), repr((cell(h, 3), cell(h, 9))))
    row("T9c the key sentinel is in NO byte the terminal received, and on no screen line", KEY.encode() not in h.s.raw and KEY not in h.text(), "")
    # the SAME dialog with values already set: the keep-stars, the list with the model in use chosen
    h.typed("s", idle=3.0)
    T = h.text()
    row("T7a S again: the same dialog, the Key entry shows the keep-stars (twelve *), the list is there at once and says the model in use, claude-test, is chosen",
        "AI setup: Anthropic" in T and "************" in T and "fake-small" in T and "the one in use, claude-test, is chosen" in re.sub(r"\s+", " ", T), repr(fl()))
    h.key("tab", idle=0.5)
    for _ in range(4):
        h.key("down", idle=0.3)
    h.key("tab", idle=0.4)
    h.key("tab", idle=0.4)
    h.key("enter", idle=3.0)
    row("T7b four rows down the list (fake-small) and Save, the keep-stars left alone: the model is fake-small and the key is unchanged",
        gone() and "model.anthropic=fake-small" in settings() and "The key is unchanged" in st(h) and open(kp).read().strip() == KEY, repr((st(h), conf())))
    # Other name: checked against the list
    a5 = audit_off()
    before = list(conf())
    h.typed("s", idle=3.0)
    h.key("tab", idle=0.4)
    h.key("tab", idle=0.4)
    h.typed("Claude-Test", idle=0.5)
    h.key("enter", idle=1.5)
    TL = h.text().split("\n")
    TS = re.sub(r"\s+", " ", h.text())
    row("T7c Other name Claude-Test (the case wrong) is refused IN the dialog, which names claude-test; nothing changed",
        "AI setup:" in h.text() and any("does not list a model named Claude-Test" in l for l in TL) and "claude-test" in TS and "case-sensitive" in TS
        and conf() == before and "set.ai model" not in (audit_new(a5) or ""), repr(fl()))
    h.typed("\x15a;b", idle=0.5)
    h.key("enter", idle=1.5)
    row("T7d Other name with a semicolon is refused by the dialog's own word check", "A model name has 1 to 80 letters" in re.sub(r"\s+", " ", h.text()) and conf() == before, repr(fl()))
    h.key("esc", idle=1.2)
    row("T7e Esc closes the dialog: nothing was changed", gone() and "nothing was changed" in st(h) and conf() == before, repr(st(h)))
    # a model set with the wrong capitals, from the prompt (SD Core's owner's Deepseek-V4-Pro); SET.AI MODEL itself warns, the dialog says so and chooses the listed one
    out = adm("set.ai model anthropic Claude-Test")
    row("T8 SET.AI MODEL with a name the provider does not list sets it and says so (14016) with the listed one that differs only in case (14018)",
        msg(11613, "anthropic", "Claude-Test") in out and msg(14016, "anthropic", "Claude-Test") in out and msg(14018, MODEL) in out, repr(out[-4:]))
    out = adm("set.ai models anthropic")
    row("T8c SET.AI MODELS lists the provider's names (14017 and one indented name to a line)",
        msg(14017, "anthropic", 6) in out and "  fake-small" in out and "  gemini-fake" in out, repr(out[-8:]))
    h.key("f5", idle=1.5)
    h.typed("s", idle=3.0)
    TS = re.sub(r"\s+", " ", h.text())
    row("T8a a model set with the wrong capitals (Claude-Test): S says it is not in the list (case-sensitive) and chooses claude-test",
        "The model now set, Claude-Test, is not in Anthropic's list (model names are case-sensitive)" in TS and "claude-test is chosen" in TS, repr(fl()))
    h.key("tab", idle=0.4)
    h.key("tab", idle=0.4)
    h.key("tab", idle=0.4)
    h.key("enter", idle=3.0)
    row("T8b Save puts claude-test in its place", gone() and ("model.anthropic=" + MODEL) in settings(), repr((st(h), conf())))
    h.typed("x", idle=1.2)
    T = h.text()
    row("T9d X shows set.ai key anthropic clear", "set.ai key anthropic clear" in T and "will be removed from the AI helper" in T, T[-600:])
    h.typed("r", idle=2.0)
    row("T9e Run removes it: the key file is gone, the row says not set", not os.path.exists(kp) and cell(h, 3).endswith("not set") and msg(11616, "anthropic") in st(h), repr((os.path.exists(kp), cell(h, 3), st(h))))

    say("\n--- C: Custom")
    for _ in range(4):                          # Custom is the fifth row since Google's (11 Nov 26)
        h.key("down", idle=0.5)
    h.typed("x", idle=0.9)
    row("T10a X on a row with no key says so and runs nothing", "No key is set for Custom" in st(h), repr(st(h)))
    h.typed("c", idle=1.0)
    for ans in ("Bad", "http://127.0.0.1/v1", "openai", "bearer", "", "max_tokens"):
        h.typed(ans + "\r", idle=1.0)
    row("T10b an http address is refused by the page: 'Not accepted: the address', nothing changed", "Not accepted: the address" in st(h) and not any(l.startswith("custom.") for l in conf()), repr((st(h), conf())))
    h.typed("c", idle=1.0)
    url = "https://127.0.0.1:%d/v1/chat/completions" % port
    for ans in ("MyLLM", url, "openai", "bearer", "", "max_tokens"):
        h.typed(ans + "\r", idle=1.0)
    T = h.text()
    row("T11a the whole sentence is shown before it runs: set.ai custom MyLLM <url> openai bearer - max_tokens, and the effect names the host",
        ("set.ai custom MyLLM " + url + " openai bearer - max_tokens") in re.sub(r"\s+", " ", T) or ("set.ai custom MyLLM" in T and "openai bearer - max_tokens" in T), T[-900:])
    a3 = audit_off()
    h.typed("r", idle=1.2)
    h.typed("custom\r", idle=2.0)
    new = audit_new(a3)
    row("T11b with the word custom typed it runs: the row shows MyLLM and the address, ai.conf holds the connection, the audit line has the host and not the address",
        "MyLLM" in h.line(7) and ("custom.url=" + url) in settings() and re.search(r"set\.ai custom name=MyLLM host=127\.0\.0\.1:%d$" % port, new, re.M) is not None and "/v1/chat/completions" not in new,
        repr((h.line(7)[3:110], new[-200:])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    h.typed("custom\r", idle=2.0)
    marks = [h.line(r)[3:6] for r in range(3, 8)]
    row("T12 selecting Custom moves the check box: exactly one [x], on the Custom row, and ai.conf says provider=custom", marks == ["[ ]", "[ ]", "[ ]", "[ ]", "[x]"] and "provider=custom" in settings(), repr((marks, conf())))
    h.typed("d", idle=1.0)
    h.typed("r", idle=2.0)
    row("T13a D while Custom is in use: the helper refuses and the page shows its words; the connection stays", "The AI helper refused" in st(h) and any(l.startswith("custom.url=") for l in conf()), repr((st(h), conf())))
    h.key("enter", idle=1.2)
    h.typed("r", idle=2.0)
    marks = [h.line(r)[3:6] for r in range(3, 8)]
    row("T13b Enter on the provider in use unchecks it: no [x] anywhere, the summary says the AI is off, ai.conf has an empty provider", marks == ["[ ]"] * 5 and h.line(9)[3:].startswith("The AI is OFF")
        and "provider=" in settings(), repr((marks, h.line(9)[3:60], conf())))
    h.typed("d", idle=1.0)
    h.typed("r", idle=2.0)
    row("T14 D now works: no custom.* line is left and the row is not filled in again", not any(l.startswith("custom.") for l in conf()) and "(not filled in)" in h.line(7) and msg(11618) in st(h),
        repr((conf(), h.line(7)[3:80], st(h))))

    say("\n--- L and A")
    h.typed("l", idle=1.0)
    h.typed("speed\r", idle=1.3)
    row("T15a L with a name that is none of the six runs nothing", "speed is not one of the six limits" in st(h), repr(st(h)))
    h.typed("l", idle=1.0)
    h.typed("requests-hour\r", idle=1.0)
    h.typed("77\r", idle=1.4)
    row("T15b the sentence is shown: set.ai limit requests-hour 77", "set.ai limit requests-hour 77" in h.text(), h.text()[-600:])
    h.typed("r", idle=2.0)
    row("T15c Run: ai.conf holds limit.requests-hour=77 and the Limits line shows it", "limit.requests-hour=77" in settings() and "requests-hour 77" in h.text(), repr((conf(), st(h))))
    adm("set.ai limit requests-hour 1000")
    h.typed("a", idle=1.0)
    h.typed(STATE["ca"] + "\r", idle=1.5)
    h.typed("r", idle=1.2)
    h.typed("ca\r", idle=2.0)
    row("T16 A: a certificate file needs the word ca typed; then ai.conf holds ca-file and the page shows it", ("ca-file=" + STATE["ca"]) in settings() and ("Certificate authorities: " + STATE["ca"]) in h.text(),
        repr((conf(), st(h))))
    h.key("ctrl-q", idle=1.5)
    h.end()

    say("\n--- the Account box: the gate")
    adm("set.ai provider anthropic")
    h = page()
    h.key("tab", idle=0.8)
    row("T17a0 Tab does NOT change box (11 Nov 26, S.117: F6 does, on every page): the status line still names Provider", st(h).startswith("[Provider]"), repr(st(h)))
    f6(h)
    row("T17a F6 moves to the Account box (the status line names it)", st(h).startswith("[Account]"), repr(st(h)))
    r26 = cell(h, 26)
    row("T17b one row, the account and the Linux user, the gate off", re.match(r"^this account\s+%s\s+off$" % re.escape(os.environ.get("USER", "")), r26) is not None, repr(r26))
    row("T17c the summary says the gate is off (as delivered) and what Enter does", h.line(31)[3:].startswith("The gate is off (as delivered): nothing can be sent to the provider.  Enter turns the gate on."), repr(h.line(31)[3:120]))
    a0 = audit_off()
    h.key("enter", idle=1.4)
    T = h.text()
    row("T18a Enter shows set.ai gate on and the effect, including that Solo runs the helper as you", "set.ai gate on" in T and "will be able to send text to Anthropic" in T and "Solo runs the AI helper as you" in T, T[-900:])
    h.typed("r", idle=1.2)
    h.typed("nope\r", idle=1.6)
    row("T18b a wrong word runs nothing: no gate line in ai.conf and the row is off", not any(l.startswith("gate") for l in conf()) and "off" in h.line(26)[3:], repr((conf(), h.line(26)[3:80])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    h.typed("ai\r", idle=2.5)
    new = audit_new(a0)
    row("T18 the word ai typed: gate=yes is in ai.conf, the row says ON, the summary says so, the audit trail has 'set.ai gate=on'",
        "gate=yes" in settings() and re.search(r"this account\s+%s\s+ON$" % re.escape(os.environ.get("USER", "")), cell(h, 26)) is not None
        and h.line(31)[3:].startswith("The gate is ON") and len(re.findall(r"set\.ai gate=on$", new, re.M)) == 1, repr((conf(), cell(h, 26), cell(h, 31), new[-200:])))
    h.key("enter", idle=1.2)
    T = h.text()
    row("T19a Enter again shows set.ai gate off, and no word is asked for turning the gate OFF", "set.ai gate off" in T and "no longer be able" in T, T[-600:])
    h.typed("r", idle=2.5)
    row("T19b Run: the gate line is gone and the row says off", not any(l.startswith("gate") for l in conf()) and "off" in h.line(26)[3:], repr((conf(), h.line(26)[3:80])))
    h.typed("s", idle=0.9)
    row("T19c a Provider key in the Account box is refused in words", "Move to the Provider box" in st(h), repr(st(h)))
    h.key("ctrl-q", idle=1.5)
    h.end()

    say("\n--- the helper not running, a small window")
    h = page()
    stop_runner()
    h.key("f5", idle=2.0)
    row("T20a the helper is not running: the summary says so in words and the rows are blank", h.line(9)[3:].startswith("The AI helper is not running"), repr(h.line(9)[3:100]))
    h.typed("s", idle=1.0)
    row("T20b S then says the helper could not be reached (11607) and opens no dialog; the page is still there", msg(11607) in st(h) and "What this means" in h.text()
        and "AI setup:" not in h.text(), repr(st(h)))
    h.key("enter", idle=1.0)
    row("T20c Enter on a provider says the same and opens no box", msg(11607) in st(h) and "set.ai provider" not in h.text(), repr(st(h)))
    f6(h)
    h.key("enter", idle=1.0)
    row("T20d Enter in the Account box says the same and opens no box", msg(11607) in st(h) and "set.ai gate" not in h.text(), repr(st(h)))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h = page(cols=100, rows=30)
    T = h.text()
    row("T22 a window under 140 by 43 gets no page (the toolkit's one size check)", "AI provider" not in T and "What this means" not in T, T[-300:])
    h.end()


# ------------------------------------------------------------------------------------------------------------------------------ the standing text

def ctx_file():
    return os.path.join(box(), "ai", "state", "context")


def ctx_text():
    try:
        return open(ctx_file(), encoding="ascii").read()
    except OSError:
        return None


def sec_context():
    """11 Nov 26 (carried from SD Core's S.160; Core's rows are sandbox-tool-ai.py T30-T38): the standing text.  Every outcome is the helper's file (box/ai/state/context), the audit
    trail, what the ai verb printed, or the request the fake provider received.  The shipped default is put beside the providers file, where solo-stage.sh puts it beside the installed
    one.  WHAT THE TREE BEFORE WOULD DO: its helper had no "context" (set.ai context is the usage, 11609; the status carries no text), so C0 alone would pass and every other row fail."""
    say("\n=== the standing text (Core S.160) ===")
    fm = STATE["fm"]
    sysx = system_text()
    head = "Standing information from the administrator of this SD system:\n"
    dflt = os.path.join(os.path.dirname(STATE["providers"]), "ai-context")
    shipped = open(os.path.join(HERE, "ai-context")).read().rstrip("\n")
    for p in (ctx_file(), dflt):
        if os.path.exists(p):
            os.remove(p)
    adm("set.ai ca " + STATE["ca"], "set.ai limit requests-hour 1000", "set.ai provider anthropic", "set.ai model anthropic " + MODEL, "set.ai gate on")
    kp = keyfile("anthropic")
    put(kp, KEY + "\n")
    os.chmod(kp, 0o600)
    q = "what is a select list"
    h = None
    try:
        out, n, aud = ask(["ai " + q, "y"], "C0", fm)
        body = (requests(fm)[-1][2] or {}) if n else {}
        row("C0 (control) no default beside the providers file and no text of the administrator's: the system text that arrives is the fixed sentence alone, and the size is the question's and its",
            n == 1 and body.get("system", [{}])[0].get("text") == sysx and msg(11628, "anthropic", MODEL, len(q) + len(sysx)) in out, repr((n, out[:4])))
        mine = "Our site ZQX7 keeps its invoices in the file inv.\nSecond line of ours."
        hx = mine.encode("ascii").hex()
        a0 = audit_off()
        out = plain(["set.ai context " + hx])
        row("C1 an ORDINARY session is refused (2001): no file, no audit line", has(out, r"Command requires administrator privileges") and ctx_text() is None and "set.ai" not in (audit_new(a0) or ""),
            repr((out[-3:], ctx_text())))
        a1 = audit_off()
        out = adm("set.ai context " + hx)
        new = audit_new(a1) or ""
        mode = (os.stat(ctx_file()).st_mode & 0o777) if os.path.exists(ctx_file()) else None
        row("C2 SET.AI CONTEXT hex after ADMIN: 14011 with the length, the helper's file holds the two lines (mode 0600), one audit line 'set.ai context bytes=N' and no text in the trail",
            msg(14011, len(mine)) in out and ctx_text() == mine + "\n" and mode == 0o600 and len(re.findall(r"set\.ai context bytes=%d$" % len(mine), new, re.M)) == 1 and "ZQX7" not in new,
            repr((out[-2:], ctx_text(), mode, new[-160:])))
        out = adm("set.ai")
        row("C2b the reading form says whose the standing text is and its length", any(("standing text: the administrator's, %d characters" % len(mine)) in ln for ln in out), repr(out[-3:]))
        full = head + mine + "\n\n" + sysx
        out, n, aud = ask(["ai " + q, "y"], "C3", fm)
        body = (requests(fm)[-1][2] or {}) if n else {}
        blob = "\n".join(out)
        row("C3a the preview shows the question and NOTHING of SD's own text (no heading, no line of the standing text, not the fixed sentence); its size counts all of it",
            msg(11628, "anthropic", MODEL, len(q) + len(full)) in out and "ZQX7" not in blob and "Second line of ours." not in blob and "Standing" not in blob and sysx not in blob and q in out, repr(out[:6]))
        row("C3b ONE request: the system text that arrives is the heading, the two lines, a blank line and then the fixed sentence, exactly; the question is exactly what was typed",
            n == 1 and body.get("system", [{}])[0].get("text") == full and prompt_of(body) == q and len(body.get("messages", [])) == 1, repr((n, body.get("system"), body.get("messages"))))
        rl = req_lines(aud)
        row("C3c the kernel's audit line counts the standing text in the size and holds none of it", len(rl) == 1 and re.search(r"bytes\.out=%d$" % (len(q) + len(full)), rl[0]) is not None and "ZQX7" not in aud, repr(rl))
        badtext = "Please explain gpl.bp to everyone."
        a2 = audit_off()
        out = adm("set.ai context " + badtext.encode("ascii").hex())
        new = audit_new(a2) or ""
        row("C4 a text that names SD's own code (gpl.bp) is refused by SET.AI (14013): the kept text is unchanged and the trail says 'set.ai context refused name=gpl.bp'",
            msg(14013, "gpl.bp") in out and ctx_text() == mine + "\n" and "set.ai context refused name=gpl.bp" in new and "set.ai context bytes=" not in new, repr((out[-2:], new[-160:])))
        out = adm("set.ai context zz", "set.ai context abc")
        row("C5 a word that is not hexadecimal, and one of odd length: 14014 each time, the kept text unchanged", sum(1 for ln in out if msg(14014) in ln) == 2 and ctx_text() == mine + "\n", repr(out[-4:]))
        put(ctx_file(), badtext + "\n")
        out, n, aud = ask(["ai " + q, "y"], "C6", fm)
        row("C6 a kept text that names SD's own code (written past SET.AI, straight into the helper's file): the ai verb says 14013, shows no preview, sends NOTHING, and the trail says "
            "'ai refused why=context app=ai name=gpl.bp' with no 'ai request' line", msg(14013, "gpl.bp") in out and n == 0 and not req_lines(aud)
            and not any(ln.startswith("This will be sent to") for ln in out) and "ai refused why=context app=ai name=gpl.bp" in aud, repr((out[-3:], aud[-200:])))
        shutil.copyfile(os.path.join(HERE, "ai-context"), dflt)
        a3 = audit_off()
        out = adm("set.ai context -")
        new = audit_new(a3) or ""
        row("C7 SET.AI CONTEXT - : 14012, the administrator's file is gone, one audit line 'set.ai context=default'",
            msg(14012) in out and ctx_text() is None and len(re.findall(r"set\.ai context=default$", new, re.M)) == 1, repr((out[-2:], new[-120:])))
        out, n, aud = ask(["ai " + q, "y"], "C8", fm)
        body = (requests(fm)[-1][2] or {}) if n else {}
        got = body.get("system", [{}])[0].get("text", "")
        row("C8 with no text of the administrator's the shipped default (Solo's own gplbld/ai-context) is what is sent first, whole, before the fixed sentence; the preview shows none of it",
            n == 1 and got == head + shipped + "\n\n" + sysx and shipped.startswith("About this system: SD Core for Linux Solo") and "About this system" not in "\n".join(out), repr((n, got[:160])))

        say("\n--- T on the page: the box")
        first = shipped.split("\n")[0]
        h = page()
        if "What this means" not in h.text():
            dump(h)
            bail("tool.ai never drew its page, so no T3x row can be believed")
        h.typed("t", idle=1.5)
        T = h.text()
        row("T30 T opens a box titled 'Standing text sent with every AI request' that says the text in use is the shipped default and shows its first line",
            "Standing text sent with every AI request" in T and "Now: the shipped default." in T and first[:60] in T, T[:600])
        a0 = audit_off()
        h.key("esc", idle=1.5)
        row("T31 Esc closes it: the page is back, the status says unchanged, no file was made and nothing was audited",
            "What this means" in h.text() and "unchanged" in st(h) and ctx_text() is None and not (audit_new(a0) or "").strip(), repr((st(h), audit_new(a0))))
        h.typed("t", idle=1.5)
        h.typed("Site note: ZQX7 is our test account.\r", idle=0.8)
        h.key("tab", idle=0.6)
        h.key("enter", idle=1.5)
        T = h.text()
        TL = T.split("\n")
        wrapped = any("it is not shown in" in TL[i] and "the preview." in TL[i + 1] for i in range(len(TL) - 1)) or any("it is not shown in the preview." in l for l in TL)
        row("T32 typing a line at the top and Save shows the Run / Cancel box naming set.ai context and the size, and says the text is not shown in the preview",
            "set.ai context <the text above," in T and "as hexadecimal>" in T and wrapped, repr([l for l in TL if "set.ai context" in l or "preview" in l or "begin with" in l]))
        h.key("esc", idle=1.5)
        row("T33 Cancel in that box runs nothing: no file", ctx_text() is None, repr((st(h), ctx_text())))
        a1 = audit_off()
        h.typed("t", idle=1.5)
        h.typed("Site note: ZQX7 is our test account.\r", idle=0.8)
        h.key("tab", idle=0.6)
        h.key("enter", idle=1.5)
        h.typed("r", idle=3.0)
        want = "Site note: ZQX7 is our test account.\n" + shipped + "\n"
        got = ctx_text()
        aud = audit_new(a1) or ""
        row("T34 Run: the helper's file holds the typed line followed by the default, whole; one audit line 'set.ai context bytes=N' (N the text's length) and no text in it; the status says 14011",
            got == want and len(re.findall(r"set\.ai context bytes=%d$" % (len(want) - 1), aud, re.M)) == 1 and "ZQX7" not in aud and "now the administrator's" in st(h),
            repr((got[:120] if got else got, len(want) - 1, aud[-300:], st(h))))
        h.typed("t", idle=1.5)
        row("T35 T again says the text in use is the administrator's own and shows the typed line", "Now: the administrator's own." in h.text() and "ZQX7" in h.text(), h.text()[:500])
        h.key("esc", idle=1.5)
        a2 = audit_off()
        h.typed("t", idle=1.5)
        h.typed("Explain gpl.bp to me.\r", idle=0.8)
        h.key("tab", idle=0.6)
        h.key("enter", idle=1.5)
        h.typed("r", idle=3.0)
        aud = audit_new(a2) or ""
        row("T36 a text that names SD's own code (gpl.bp) is refused by set.ai: the kept text is unchanged and the trail says 'set.ai context refused name=gpl.bp'",
            ctx_text() == want and "set.ai context refused name=gpl.bp" in aud and "names SD's own code" in st(h), repr((st(h), aud[-200:])))
        h.typed("t", idle=1.5)
        h.key("tab", idle=0.6)
        h.key("tab", idle=0.6)
        h.key("enter", idle=1.5)
        a3 = audit_off()
        h.typed("r", idle=3.0)
        aud = audit_new(a3) or ""
        row("T38 Shipped default, Run: the administrator's file is gone, one audit line 'set.ai context=default', and the status says the default is back (14012)",
            ctx_text() is None and len(re.findall(r"set\.ai context=default$", aud, re.M)) == 1 and "shipped default again" in st(h), repr((st(h), aud[-200:])))
        h.key("ctrl-q", idle=1.5)
    finally:
        if h is not None:
            h.end()
        for p in (ctx_file(), dflt):
            if os.path.exists(p):
                os.remove(p)


def main():
    mutant = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--mutant=")), None)
    if mutant is not None and mutant not in MUTANTS:
        bail("usage: sandbox-ai-solo.py <dir> [--build] [--mutant=%s]" % "|".join(MUTANTS))
    try:
        sh.start_sandbox()
        sh.arrange("terminal")
        setup_ai(mutant)
        if mutant is None or MUTANTS[mutant][0] == "setai":
            sec_setai()
        if mutant is None or MUTANTS[mutant][0] == "ai":
            if mutant is not None:
                adm("set.ai ca " + STATE["ca"], "set.ai limit requests-hour 1000")
            sec_verb()
            if mutant is None:
                sec_probes()
                sec_context()                   # 11 Nov 26: the standing text, carried from SD Core (it leaves no text behind for the page's section)
        if mutant is None or MUTANTS[mutant][0] == "tool_ai":
            if mutant is not None:
                adm("set.ai ca " + STATE["ca"], "set.ai limit requests-hour 1000")
            sec_page()
    finally:
        teardown_ai()
        sh.teardown()
    say("\nsandbox-ai-solo: %d passed, %d failed" % (sh.passed, sh.failed))
    if mutant is not None:
        want = sorted(set(MUTANTS[mutant][3]))
        got = sorted({re.match(r"[AVPT]\d+", i).group(0) for i in FAILED_IDS if re.match(r"[AVPT]\d+", i)})
        ok = want == got
        say("sandbox-ai-solo: MUTANT %s: the rows that failed are %s; they had to be exactly %s -> %s" % (mutant, got, want, "KILLED BY ITS OWN ROWS" if ok else "NOT AS EXPECTED"))
        return 0 if ok else 1
    return 0 if sh.failed == 0 and sh.passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
