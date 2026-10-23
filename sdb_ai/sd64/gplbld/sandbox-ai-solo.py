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
#   T0-T22  the page, driven on a 140 by 43 pseudo-terminal: the boxes, the four providers, Enter on a provider (Cancel, a wrong name, the right one), M, K (the helper's prompt, the key
#           in no byte of the terminal), X, C, D, L, A, the Account box (the gate: Enter asks for the word ai before it turns the gate ON, none to turn it OFF), the helper not running,
#           a window that is too small
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
                     ("https://api.deepseek.com/chat/completions", "https://127.0.0.1:%d/chat/completions" % fm.port)):
        text = text.replace(old, new)
    put(providers, text)
    STATE.update(fm=fm, pki=pki, providers=providers, ca=os.path.join(pki, "ca.crt"), port=fm.port)
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
    row("A1 the reading form, nothing set: the AI is off, the gate is off, four rows with the shipped addresses (the fake's here), none checked, no model, no key",
        has(out, r"^AI provider in use: none \(the AI is off\)") and has(out, r"^\s+gate: off$") and sum(1 for l in out if l.startswith("  [ ] ")) == 4
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
    row("V2 a provider and no model: 11626 (anthropic, model), no preview, nothing sent", msg(11626, "anthropic", "model") in out and n == 0 and not req_lines(aud), repr(out[-4:]))
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
    row("V4a the preview names the provider, the model and the size, then shows the fixed sentence and the text, then asks", msg(11628, "anthropic", MODEL, size) in out and sysx in out and q in out
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


def page(cols=140, rows=43):
    h = H(admin=True, cols=cols, rows=rows)
    h.typed("tool.ai\r", idle=3.0)
    return h


def sec_page():
    say("\n=== TOOL.AI ===")
    adm("set.ai provider none", "set.ai gate off", "set.ai model anthropic -", "set.ai custom clear")
    for p in ("anthropic", "openai", "deepseek", "custom"):
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
    urls = ("https://127.0.0.1:%d/v1/messages" % port, "https://127.0.0.1:%d/v1/chat/completions" % port, "https://127.0.0.1:%d/chat/completions" % port)
    names = ("Anthropic", "OpenAI", "DeepSeek")
    ok = all(re.match(r"^\[ \] %s\s+%s\s+\(not set\)\s+not set$" % (re.escape(nm), re.escape(u)), cell(h, 3 + i)) for i, (nm, u) in enumerate(zip(names, urls)))
    row("T1b the three named providers are filled in with their shipped address, no model and no key, none checked", ok, repr([cell(h, r) for r in range(3, 7)]))
    row("T1c the fourth row is Custom, not filled in, nothing checked", re.match(r"^\[ \] Custom\s+\(not filled in\)\s+\(not set\)\s+not set$", cell(h, 6)) is not None, repr(cell(h, 6)))
    row("T1d the summary says the AI is off (no provider is selected)", h.line(8)[3:].startswith("The AI is OFF: no provider is selected."), repr(h.line(8)[3:80]))
    row("T2 a [?] at the end of the Provider box and of the Account box", h.line(2)[134:137] == "[?]" and h.line(24)[134:137] == "[?]", repr((h.line(2)[130:139], h.line(24)[130:139])))
    row("T1e the row under the cursor is described: the Anthropic request layout, the x-api-key header and the version header",
        all(w in h.text() for w in ("anthropic  (the Messages API)", "x-api-key: <key>", "2023-06-01", "max_tokens")), h.text()[1500:2600])

    say("\n--- Enter on a provider")
    a0 = audit_off()
    h.key("enter", idle=1.4)
    T = h.text()
    row("T3a Enter shows the command and its effect, and warns that no model and no key are set", "set.ai provider anthropic" in T and "Anthropic will be used" in T and "No model is set for it yet" in T
        and "No key is set for it yet" in T, T[-900:])
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
    row("T4d the summary says what is missing: no model and no key yet", "In use: Anthropic, model (not set), key not set.  It cannot be used until both are set" in h.line(8), repr(h.line(8)[3:130]))

    say("\n--- M: the model")
    h.typed("m", idle=1.2)
    row("T5a M asks for the model name of the row under the cursor", "Model name for Anthropic" in h.text(), h.text()[-500:])
    h.typed(MODEL + "\r", idle=1.5)
    T = h.text()
    row("T5b the sentence and its effect are shown before anything runs", "set.ai model anthropic " + MODEL in T and "will ask model " + MODEL in T, T[-700:])
    h.typed("r", idle=2.0)
    row("T5c Run: ai.conf holds the model, the row shows it, the verb's own words are on the status line", ("model.anthropic=" + MODEL) in settings() and MODEL in h.line(3)
        and msg(11613, "anthropic", MODEL) in st(h), repr((conf(), h.line(3)[3:100], st(h))))
    a1 = audit_off()
    before = list(conf())
    h.typed("m", idle=1.0)
    h.typed("a;b\r", idle=1.5)
    row("T6 a model name with a semicolon is refused by the page (words), nothing is run, nothing is audited", "A model name has 1 to 80 letters" in st(h) and conf() == before and "set.ai" not in audit_new(a1),
        repr((st(h), audit_new(a1))))
    h.key("down", idle=0.6)
    h.typed("m", idle=1.0)
    h.typed("GPT-Test:1\r", idle=1.5)
    h.typed("r", idle=2.0)
    row("T7 capitals and a colon in a model name go through $tk_runx (the OpenAI row)", "model.openai=GPT-Test:1" in settings() and "GPT-Test:1" in h.line(4), repr((conf(), h.line(4)[3:100], st(h))))
    h.key("up", idle=0.6)

    say("\n--- K: the key")
    a2 = audit_off()
    h.typed("k", idle=1.4)
    T = h.text()
    row("T8a K shows set.ai key anthropic and says the key does not pass through SD", "set.ai key anthropic" in T and "does not pass through SD" in T, T[-800:])
    h.typed("r", idle=2.5)
    scr = h.text()
    row("T8b the terminal is the helper's: its prompt 'Key for anthropic (not shown):' is on the screen and the page is not", "Key for anthropic (not shown):" in scr and "What this means" not in scr, scr[-400:])
    h.typed(KEY[:6], idle=0.7)
    row("T8c what is typed at the prompt is not shown", KEY[:6] not in h.text(), h.text()[-300:])
    h.typed(KEY[6:] + "\r", idle=3.0)
    scr = h.text()
    row("T8d SD says the key is set (11615) and waits for Enter before it takes the screen again", msg(11615, "anthropic") in scr and KEY not in scr, scr[-400:])
    h.key("enter", idle=2.5)
    new = audit_new(a2)
    kp = keyfile("anthropic")
    row("T9a back on the page: the row shows the key set, the summary no longer says it cannot be used", re.search(r"claude-test\s+set$", cell(h, 3)) is not None
        and "In use: Anthropic, model claude-test, key set" in h.line(8) and "cannot be used" not in h.line(8), repr((cell(h, 3), cell(h, 8))))
    row("T9b the key file is the helper's: mode 0600, holds the key; the audit trail has 'set.ai key set provider=anthropic' and no key", os.path.exists(kp) and open(kp).read().strip() == KEY
        and (os.stat(kp).st_mode & 0o777) == 0o600 and re.search(r"set\.ai key set provider=anthropic$", new, re.M) is not None and KEY not in new, repr((os.path.exists(kp), new[-200:])))
    row("T9c the key sentinel is in NO byte the terminal received, and on no screen line", KEY.encode() not in h.s.raw and KEY not in h.text(), "")
    h.typed("x", idle=1.2)
    T = h.text()
    row("T9d X shows set.ai key anthropic clear", "set.ai key anthropic clear" in T and "will be removed from the AI helper" in T, T[-600:])
    h.typed("r", idle=2.0)
    row("T9e Run removes it: the key file is gone, the row says not set", not os.path.exists(kp) and cell(h, 3).endswith("not set") and msg(11616, "anthropic") in st(h), repr((os.path.exists(kp), cell(h, 3), st(h))))

    say("\n--- C: Custom")
    for _ in range(3):
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
        "MyLLM" in h.line(6) and ("custom.url=" + url) in settings() and re.search(r"set\.ai custom name=MyLLM host=127\.0\.0\.1:%d$" % port, new, re.M) is not None and "/v1/chat/completions" not in new,
        repr((h.line(6)[3:110], new[-200:])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    h.typed("custom\r", idle=2.0)
    marks = [h.line(r)[3:6] for r in range(3, 7)]
    row("T12 selecting Custom moves the check box: exactly one [x], on the Custom row, and ai.conf says provider=custom", marks == ["[ ]", "[ ]", "[ ]", "[x]"] and "provider=custom" in settings(), repr((marks, conf())))
    h.typed("d", idle=1.0)
    h.typed("r", idle=2.0)
    row("T13a D while Custom is in use: the helper refuses and the page shows its words; the connection stays", "The AI helper refused" in st(h) and any(l.startswith("custom.url=") for l in conf()), repr((st(h), conf())))
    h.key("enter", idle=1.2)
    h.typed("r", idle=2.0)
    marks = [h.line(r)[3:6] for r in range(3, 7)]
    row("T13b Enter on the provider in use unchecks it: no [x] anywhere, the summary says the AI is off, ai.conf has an empty provider", marks == ["[ ]"] * 4 and h.line(8)[3:].startswith("The AI is OFF")
        and "provider=" in settings(), repr((marks, h.line(8)[3:60], conf())))
    h.typed("d", idle=1.0)
    h.typed("r", idle=2.0)
    row("T14 D now works: no custom.* line is left and the row is not filled in again", not any(l.startswith("custom.") for l in conf()) and "(not filled in)" in h.line(6) and msg(11618) in st(h),
        repr((conf(), h.line(6)[3:80], st(h))))

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
    row("T17a Tab moves to the Account box (the status line names it)", st(h).startswith("[Account]"), repr(st(h)))
    r25 = cell(h, 25)
    row("T17b one row, the account and the Linux user, the gate off", re.match(r"^this account\s+%s\s+off$" % re.escape(os.environ.get("USER", "")), r25) is not None, repr(r25))
    row("T17c the summary says the gate is off (as delivered) and what Enter does", h.line(31)[3:].startswith("The gate is off (as delivered): nothing can be sent to the provider.  Enter turns the gate on."), repr(h.line(31)[3:120]))
    a0 = audit_off()
    h.key("enter", idle=1.4)
    T = h.text()
    row("T18a Enter shows set.ai gate on and the effect, including that Solo runs the helper as you", "set.ai gate on" in T and "will be able to send text to Anthropic" in T and "Solo runs the AI helper as you" in T, T[-900:])
    h.typed("r", idle=1.2)
    h.typed("nope\r", idle=1.6)
    row("T18b a wrong word runs nothing: no gate line in ai.conf and the row is off", not any(l.startswith("gate") for l in conf()) and "off" in h.line(25)[3:], repr((conf(), h.line(25)[3:80])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=1.2)
    h.typed("ai\r", idle=2.5)
    new = audit_new(a0)
    row("T18 the word ai typed: gate=yes is in ai.conf, the row says ON, the summary says so, the audit trail has 'set.ai gate=on'",
        "gate=yes" in settings() and re.search(r"this account\s+%s\s+ON$" % re.escape(os.environ.get("USER", "")), cell(h, 25)) is not None
        and h.line(31)[3:].startswith("The gate is ON") and len(re.findall(r"set\.ai gate=on$", new, re.M)) == 1, repr((conf(), cell(h, 25), cell(h, 31), new[-200:])))
    h.key("enter", idle=1.2)
    T = h.text()
    row("T19a Enter again shows set.ai gate off, and no word is asked for turning the gate OFF", "set.ai gate off" in T and "no longer be able" in T, T[-600:])
    h.typed("r", idle=2.5)
    row("T19b Run: the gate line is gone and the row says off", not any(l.startswith("gate") for l in conf()) and "off" in h.line(25)[3:], repr((conf(), h.line(25)[3:80])))
    h.typed("m", idle=0.9)
    row("T19c a Provider key in the Account box is refused in words", "Move to the Provider box" in st(h), repr(st(h)))
    h.key("ctrl-q", idle=1.5)
    h.end()

    say("\n--- the helper not running, a small window")
    h = page()
    stop_runner()
    h.key("f5", idle=2.0)
    row("T20a the helper is not running: the summary says so in words and the rows are blank", h.line(8)[3:].startswith("The AI helper is not running"), repr(h.line(8)[3:100]))
    h.typed("m", idle=1.0)
    row("T20b M then says the helper could not be reached (11607); the page is still there", msg(11607) in st(h) and "What this means" in h.text(), repr(st(h)))
    h.key("enter", idle=1.0)
    row("T20c Enter on a provider says the same and opens no box", msg(11607) in st(h) and "set.ai provider" not in h.text(), repr(st(h)))
    h.key("tab", idle=0.8)
    h.key("enter", idle=1.0)
    row("T20d Enter in the Account box says the same and opens no box", msg(11607) in st(h) and "set.ai gate" not in h.text(), repr(st(h)))
    h.key("ctrl-q", idle=1.5)
    h.end()
    h = page(cols=100, rows=30)
    T = h.text()
    row("T22 a window under 140 by 43 gets no page (the toolkit's one size check)", "AI provider" not in T and "What this means" not in T, T[-300:])
    h.end()


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
