#!/usr/bin/env python3
#
# test-aihelper.py - the in-SD model helper `sd-ai` RUN against the fake provider (S.69 step 2, plan .claude/plan-ai-step2.md, group A).
# No sd, no sudo, no install, no network but the loopback; needs the openssl command line (throw-away certificates).
#
#   python3 /home/don/Projects/SDCore4Linux/sdb_ai/sd64/gplbld/test-aihelper.py [--helper FILE] [--selftest]
#
# The helper's handler is called in this process on a Unix socketpair, so its caller's uid really comes from SO_PEERCRED, against gplbld/fakemodel.py
# (TLS, the two wire formats, every failure the plan lists).  SOLO'S HELPER (carry 15): the caller must be the helper's own user and ai.conf must say
# gate=yes.  The gate rows set that line; a STRANGER is made by having the helper read another uid than the real one (the helper's peer_uid is replaced
# for those rows and no other - own_user() and the refusal around it are the code under test).  Exit 0 every row passed, 1 a row failed, 2 it could not run.
#   --helper FILE   test that copy of the helper (the self-test's mutants)
#   --selftest      each MUTANT of the helper (a rule weakened by one change) must turn this suite red; each is run on a copy in a scratch directory
#
# WHAT IS HELD: the gate (gate=yes, no gate line, a damaged value, a stranger's uid, a connection that is not a socket); disabled / nomodel / nokey (a key file anyone can
# read, a link); the three shipped providers and Custom in both formats with the header, the body and the reply-size field each must have; the
# refusal of an http URL, a userinfo, a bad format; every failure of the provider (401, 429 once then 200, 429 and 500 for good, not JSON, wrong
# shape, a refusal, a redirect that is NOT followed); the reply cut to ASCII; an oversize reply and request; the clamp of maxtokens; the hourly and
# daily limits; the certificate of another name and one no CA vouches for, and the system store refusing the test CA unless ca-file names it;
# a timeout; `status` (the gate, the details for the user's own processes, nothing for a stranger); the settings and keys (any process of the user, a
# stranger refused); and the canaries - a string in the environment and in a decoy file never reaches the
# provider, and the key is in no reply and no log line.  NOT HELD: a real provider (witness-ai-live.sh is the owner's), systemd's user socket,
# OpenAI's own endpoint.
import importlib.machinery
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakemodel  # noqa: E402

KEY = "test-key-0123456789"
SHIPPED = os.path.join(HERE, "ai-providers")
passed = failed = 0
FILTER = None


def say(s=""):
    print(s, flush=True)


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say("  [PASS] " + name)
    else:
        failed += 1
        say("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def socketpair_pair():
    return socket.socketpair()


def load(path):
    loader = importlib.machinery.SourceFileLoader("sdai_under_test", path)
    spec = importlib.util.spec_from_loader("sdai_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Env:
    """A state directory, a providers file pointing at the fake, and the helper's handler."""

    def __init__(self, mod, tmp, fm, ca):
        self.mod, self.tmp, self.fm, self.ca = mod, tmp, fm, ca
        self.state = os.path.join(tmp, "state")
        for sub in ("", "keys", "state"):
            os.makedirs(os.path.join(self.state, sub), exist_ok=True)
        self.providers = os.path.join(tmp, "ai-providers")
        base = "https://127.0.0.1:%d" % fm.port
        with open(SHIPPED) as f:
            text = f.read()
        for old, new in (("https://api.anthropic.com/v1/messages", base + "/v1/messages"), ("https://api.openai.com/v1/chat/completions", base + "/v1/chat/completions"),
                         ("https://api.deepseek.com/chat/completions", base + "/chat/completions")):
            assert old in text, old
            text = text.replace(old, new)
        with open(self.providers, "w") as f:
            f.write(text)
        self.logs = []
        self.gate_yes = True
        self.real_peer_uid = mod.peer_uid

    def gate(self, yes):
        """The setting gate=yes (the next conf() writes it) or no gate line at all."""
        self.gate_yes = yes

    def stranger(self, yes):
        """The helper reads another uid off the connection than the one that really made it (only peer_uid is replaced)."""
        self.mod.peer_uid = (lambda fd: self.real_peer_uid(fd) + 1) if yes else self.real_peer_uid

    def conf(self, **kv):
        """Write ai.conf.  A double underscore in a name is a dot (model__anthropic is model.anthropic); ca-file is the test CA unless a row says otherwise
        (an empty value means the system store); a name with a dot or hyphen in it is passed as **{"limit.timeout": "1"}."""
        base = {"ca-file": self.ca}
        if self.gate_yes:
            base["gate"] = "yes"
        base.update(kv)
        lines = ["# test"] + ["%s=%s" % (k.replace("__", "."), v) for k, v in base.items()]
        with open(os.path.join(self.state, "ai.conf"), "w") as f:
            f.write("\n".join(lines) + "\n")

    def key(self, name, text=KEY, mode=0o600):
        p = os.path.join(self.state, "keys", name)
        if os.path.lexists(p):
            os.remove(p)
        with open(p, "w") as f:
            f.write(text + "\n")
        os.chmod(p, mode)

    def reset_counters(self):
        d = os.path.join(self.state, "state")
        for n in os.listdir(d):
            os.remove(os.path.join(d, n))

    def ask(self, prompt="hello", system="You help.", op="ask", raw=None, fd=None, **extra):
        req = raw if raw is not None else json.dumps(dict({"v": 1, "op": op, "system": system, "prompt": prompt}, **extra)).encode("utf-8") + b"\n"
        if fd is not None:                    # a pipe instead of a socket: the helper cannot learn who is calling
            r, w = fd
            os.write(w, req)
            os.close(w)
            null = os.open(os.devnull, os.O_WRONLY)
            reply = self.run(r, null)
            os.close(null)
            os.close(r)
            return reply
        a, b = socketpair_pair()
        a.sendall(req)
        reply = self.run(b.fileno(), b.fileno())
        b.close()
        a.close()
        return reply

    def run(self, fd_in, fd_out):
        """serve() returns the reply it wrote on fd_out (for a socketpair, the socket the caller reads), and logs one line."""
        self.logs.clear()
        return self.mod.serve(fd_in, fd_out, self.state, self.providers, self.logs.append)


def rows(env, fm):
    mod = env.mod
    M = "claude-test-model"
    say("\n--- the shipped table and the connection rules")
    try:
        table = mod.read_providers(SHIPPED)
        row("the shipped gplbld/ai-providers is read: Anthropic, OpenAI and DeepSeek, every URL https, the formats and token parameters as planned",
            set(table) == {"anthropic", "openai", "deepseek"} and table["anthropic"]["format"] == "anthropic" and table["anthropic"]["auth"] == "x-api-key"
            and table["openai"]["maxparam"] == "max_completion_tokens" and table["deepseek"]["format"] == "openai" and table["deepseek"]["url"] == "https://api.deepseek.com/chat/completions"
            and all(p["url"].startswith("https://") for p in table.values()), repr(table))
    except mod.Refuse as e:
        row("the shipped table is read", False, "%s %s" % (e.code, e.msg))
    good = {"name": "Mine", "url": "https://llm.example.org:8443/v1/chat/completions", "format": "openai", "auth": "bearer", "maxparam": "max_tokens"}
    ok = True
    try:
        mod.check_connection(good, "x")
    except mod.Refuse:
        ok = False
    row("a well-formed custom connection passes check_connection", ok, "")
    for what, change in (("an http URL", {"url": "http://llm.example.org/v1/x"}), ("a URL with userinfo", {"url": "https://user:pw@llm.example.org/v1/x"}),
                         ("a URL with a space", {"url": "https://llm.example.org/v1/x y"}), ("a URL with a fragment", {"url": "https://llm.example.org/v1/x#a"}),
                         ("a URL with a backslash", {"url": "https://llm.example.org\\evil/v1"}), ("port 0", {"url": "https://llm.example.org:0/v1"}),
                         ("a URL with a query string (a place to hide a key)", {"url": "https://llm.example.org/v1/x?api-key=SECRET"}),
                         ("a URL with a % escape", {"url": "https://llm.example.org/v1/%2e%2e/x"}),
                         ("an unknown format", {"format": "gemini"}), ("an unknown auth style", {"auth": "basic"}), ("an unknown token parameter", {"maxparam": "n"}),
                         ("a version with a newline", {"version": "1\nX-Evil: 1"})):
        p = dict(good, **change)
        try:
            mod.check_connection(p, "x")
            refused = False
        except mod.Refuse as e:
            refused = e.code == "badconf"
        row("check_connection refuses " + what, refused, "")

    say("\n--- the gate")
    env.conf(provider="anthropic", model__anthropic=M)
    env.key("anthropic")
    env.reset_counters()
    env.gate(False)
    env.conf(provider="anthropic", model__anthropic=M)
    r = env.ask()
    row("with no gate line in ai.conf (the delivered state) a request is refused with nogate and told nothing else", r["t"] == "err" and r.get("code") == "nogate" and "anthropic" not in json.dumps(r) and M not in json.dumps(r), repr(r))
    for bad in ("YES", "no", "true", "1", "yes please", "y"):
        env.conf(provider="anthropic", model__anthropic=M, gate=bad)
        r = env.ask()
        row("gate=%s is not the word yes: nogate (only exactly yes opens the gate)" % bad, r["t"] == "err" and r.get("code") == "nogate", repr(r))
    env.conf(provider="anthropic", model__anthropic=M, gate="")
    r = env.ask()
    row("an empty gate= line is off too", r.get("code") == "nogate", repr(r))
    env.gate(True)
    env.conf(provider="anthropic", model__anthropic=M)
    env.stranger(True)
    r = env.ask()
    row("a caller whose uid is not the helper's own is refused with nogate even with gate=yes, and told nothing", r["t"] == "err" and r.get("code") == "nogate" and "anthropic" not in json.dumps(r) and M not in json.dumps(r), repr(r))
    for req in ({"op": "status"}, {"op": "set", "what": "gate", "value": "no"}, {"op": "keyset", "provider": "openai", "key": KEY}, {"op": "keyclear", "provider": "anthropic"}):
        r = env.ask(raw=json.dumps(dict(req, v=1)).encode() + b"\n")
        row("...and %s from that stranger is refused the same way and changes nothing" % req["op"], r.get("code") == "nogate" and "gate=yes" in open(os.path.join(env.state, "ai.conf")).read().splitlines()
            and not os.path.exists(os.path.join(env.state, "keys", "openai")) and os.path.exists(os.path.join(env.state, "keys", "anthropic")), repr(r))
    env.stranger(False)
    r = env.ask()
    row("the gate is on and the caller is the helper's own user: an ok reply with the text, the token counts and the provider", r["t"] == "ok" and r["text"] == fakemodel.PLAIN_TEXT and r["in"] == 11 and r["out"] == 7 and r["provider"] == "anthropic", repr(r))
    rp, wp = os.pipe()
    r = env.ask(fd=(rp, wp))
    row("a connection that is not a socket (a pipe) is refused: the uid cannot be known, so fail closed", r["t"] == "err" and r.get("code") == "nogate", repr(r))
    r = env.ask(raw=b"not json at all\n")                       # (a stranger would be refused first; the caller is a member here)
    row("a line that is not a request is badreq", r["t"] == "err" and r.get("code") == "badreq", repr(r))
    r = env.ask(raw=b'{"v":2,"op":"ask","prompt":"x"}\n')
    row("a request of another version is badreq", r.get("code") == "badreq", repr(r))
    r = env.ask(raw=b'{"v":1,"op":"shell","prompt":"x"}\n')
    row("an operation the helper does not have is badreq", r.get("code") == "badreq", repr(r))
    r = env.ask(prompt="")
    row("an empty prompt is badreq", r.get("code") == "badreq", repr(r))

    say("\n--- disabled, no model, no key")
    env.conf(provider="")
    r = env.ask()
    row("no provider selected (the delivered state): disabled", r.get("code") == "disabled", repr(r))
    env.conf(provider="anthropic")
    r = env.ask()
    row("a provider with no model: nomodel", r.get("code") == "nomodel", repr(r))
    env.conf(provider="anthropic", model__anthropic=M)
    os.remove(os.path.join(env.state, "keys", "anthropic"))
    r = env.ask()
    row("a provider with no key: nokey", r.get("code") == "nokey", repr(r))
    env.key("anthropic", mode=0o640)
    r = env.ask()
    row("a key file that group can read is refused (nokey): the helper does not repair it", r.get("code") == "nokey", repr(r))
    p = os.path.join(env.state, "keys", "anthropic")
    os.remove(p)
    target = os.path.join(env.tmp, "keytarget")
    with open(target, "w") as f:
        f.write(KEY + "\n")
    os.chmod(target, 0o600)
    os.symlink(target, p)
    r = env.ask()
    row("a key file that is a link is refused (nokey)", r.get("code") == "nokey", repr(r))
    env.key("anthropic", text="short")
    r = env.ask()
    row("a key file that does not hold a key (too short) is nokey", r.get("code") == "nokey", repr(r))
    env.key("anthropic")
    env.conf(provider="anthropic", model__anthropic="bad model; rm -rf")
    r = env.ask()
    row("a model name with characters a model name may not have is badconf, and nothing is sent", r.get("code") == "badconf", repr(r))
    env.conf(provider="martian", model__martian=M)
    r = env.ask()
    row("a provider that is none of the four is badconf", r.get("code") == "badconf", repr(r))

    say("\n--- the wire formats: what is sent to each provider")
    env.reset_counters()
    for name, path, hdr, maxparam in (("anthropic", "/v1/messages", "x-api-key", "max_tokens"), ("openai", "/v1/chat/completions", "authorization", "max_completion_tokens"),
                                     ("deepseek", "/chat/completions", "authorization", "max_tokens")):
        env.conf(**{"provider": name, "model__" + name: M})
        env.key(name)
        n0 = len(fm.log)
        r = env.ask("What is six times seven?", system="Be brief.", maxtokens=200)
        sent = fm.log[n0] if len(fm.log) > n0 else None
        body = json.loads(sent["body"]) if sent else {}
        good_hdr = sent and (sent["headers"].get(hdr) == (KEY if hdr == "x-api-key" else "Bearer " + KEY))
        shape = (body.get("model") == M and body.get(maxparam) == 200 and (("system" in body and body["system"][0]["text"] == "Be brief.") if name == "anthropic" else
                 body["messages"][0] == {"role": "system", "content": "Be brief."}))
        row("%s: ok reply; path %s, the key in %s, model, %s, system and the user's words as the format wants" % (name, path, hdr, maxparam),
            r["t"] == "ok" and r["provider"] == name and sent and sent["path"] == path and good_hdr and shape and body["messages"][-1] == {"role": "user", "content": "What is six times seven?"},
            repr((r, sent and sent["path"], sent and sorted(sent["headers"]))))
        if name == "anthropic":
            row("anthropic: the version header is sent (2023-06-01) and Authorization is not", sent["headers"].get("anthropic-version") == "2023-06-01" and "authorization" not in sent["headers"], repr(sent["headers"]))
        else:
            row("%s: no anthropic-version header and no x-api-key" % name, "anthropic-version" not in sent["headers"] and "x-api-key" not in sent["headers"], repr(sent["headers"]))

    say("\n--- Custom: everything is the administrator's")
    env.conf(provider="custom", model__custom="my-model", custom__name="My LLM", custom__url="https://127.0.0.1:%d/v1/chat/completions" % fm.port, custom__format="openai",
             custom__auth="bearer", custom__maxparam="max_tokens")
    env.key("custom")
    n0 = len(fm.log)
    r = env.ask("hi")
    body = json.loads(fm.log[n0]["body"]) if len(fm.log) > n0 else {}
    row("custom, openai format with a bearer key: ok, max_tokens used as the setting says", r["t"] == "ok" and r["provider"] == "custom" and "max_tokens" in body and "max_completion_tokens" not in body, repr(r))
    env.conf(provider="custom", model__custom="my-model", custom__url="https://127.0.0.1:%d/v1/messages" % fm.port, custom__format="anthropic", custom__auth="x-api-key",
             custom__version="2024-01-01", custom__maxparam="max_tokens")
    n0 = len(fm.log)
    r = env.ask("hi")
    row("custom, anthropic format with x-api-key and its own version header: ok, 2024-01-01 sent", r["t"] == "ok" and fm.log[n0]["headers"].get("anthropic-version") == "2024-01-01", repr(r))
    env.conf(provider="custom", model__custom="my-model", custom__url="http://127.0.0.1:%d/v1/messages" % fm.port, custom__format="anthropic", custom__auth="x-api-key", custom__maxparam="max_tokens")
    n0 = len(fm.log)
    r = env.ask("hi")
    row("custom with an http URL is badconf and NOTHING is sent (http is not allowed, for a local model server either)", r.get("code") == "badconf" and len(fm.log) == n0, repr(r))
    env.conf(provider="custom", model__custom="my-model")
    r = env.ask("hi")
    row("custom with no connection details is badconf", r.get("code") == "badconf", repr(r))

    say("\n--- what the provider can do wrong")
    env.conf(provider="anthropic", model__anthropic=M)
    env.key("anthropic")
    env.reset_counters()
    cases = (("[[err401]]", "refused", "a 401 (the provider did not accept the key)"), ("[[badjson]]", "badreply", "an answer that is not JSON"), ("[[shape]]", "badreply", "valid JSON of a shape nobody knows"),
             ("[[refuse]]", "declined", "a refusal by the model (anthropic)"), ("[[err429always]]", "busy", "a 429 twice (one retry, then busy)"), ("[[err500]]", "busy", "a 500 twice"))
    for marker, code, what in cases:
        t0 = time.time()
        r = env.ask("please " + marker)
        row("%s: %s" % (what, code), r["t"] == "err" and r.get("code") == code, repr(r))
    env.conf(provider="openai", model__openai=M)
    env.key("openai")
    r = env.ask("[[refuse]]")
    row("a refusal by the model (openai message.refusal): declined", r.get("code") == "declined", repr(r))
    env.conf(provider="anthropic", model__anthropic=M)
    fm.count.clear()
    n0 = len(fm.log)
    r = env.ask("[[err429]]")
    row("a 429 once, then 200: the one retry succeeds, two requests were made", r["t"] == "ok" and len(fm.log) - n0 == 2, repr((r, len(fm.log) - n0)))
    n0 = len(fm.log)
    r = env.ask("[[redirect]]")
    row("a 302 is refused and NOT followed: one request reached the fake, none went to the other host", r["t"] == "err" and r.get("code") == "refused" and "redirect" in r["msg"] and len(fm.log) - n0 == 1, repr((r, len(fm.log) - n0)))
    r = env.ask("[[trunc]]")
    row("a reply that stopped at the token limit is ok and says truncated", r["t"] == "ok" and r["truncated"] is True, repr(r))

    say("\n--- the reply is ASCII, newline and tab")
    r = env.ask("[[ctrl]]")
    t = r.get("text", "")
    row("escape sequences, the OSC string, mark bytes and non-English letters are gone: only ASCII, newline and tab remain",
        r["t"] == "ok" and all(c in "\n\t" or 32 <= ord(c) < 127 for c in t), repr(t))
    row("curly quotes and the em dash become plain ones, the carriage return is dropped, and the count of replaced characters is reported (not zero)",
        '"quoted"' in t and " - dash" in t and "\r" not in t and r["replaced"] > 0, repr((t, r.get("replaced"))))
    r = env.ask("[[big]]")
    row("a reply over the byte limit is toobig, not cut", r["t"] == "err" and r.get("code") == "toobig", repr(r)[:200])
    r = env.ask("x" * 70000)
    row("a request over the byte limit is toobig, and nothing is sent", r["t"] == "err" and r.get("code") == "toobig", repr(r)[:200])
    n0 = len(fm.log)
    r = env.ask("hello", maxtokens=999999)
    row("maxtokens is clamped to the limit (1024): the provider is asked for 1024", r["t"] == "ok" and json.loads(fm.log[n0]["body"])["max_tokens"] == 1024, repr(r))

    say("\n--- limits")
    env.reset_counters()
    env.conf(provider="anthropic", model__anthropic=M, **{"limit.requests-hour": "2"})
    a = env.ask()
    b = env.ask()
    c = env.ask()
    row("requests per hour: two are let through and the third is limit (and not sent)", a["t"] == "ok" and b["t"] == "ok" and c["t"] == "err" and c["code"] == "limit", repr((a["t"], b["t"], c)))
    st = os.stat(os.path.join(env.state, "state", "u%d" % os.getuid()))
    row("the counters file is the helper's own, mode 0600", stat.S_IMODE(st.st_mode) == 0o600, oct(st.st_mode))
    env.reset_counters()
    env.conf(provider="anthropic", model__anthropic=M, **{"limit.tokens-day": "10"})
    a = env.ask()
    b = env.ask()
    row("tokens per day: the first request (18 tokens) passes, the second is limit: a loop is stopped", a["t"] == "ok" and b["t"] == "err" and b["code"] == "limit", repr((a["t"], b)))
    env.conf(provider="anthropic", model__anthropic=M, **{"limit.timeout": "0"})
    r = env.ask()
    row("a limit that is not in range (timeout 0) is badconf", r.get("code") == "badconf", repr(r))

    say("\n--- the certificate")
    env.reset_counters()
    env.conf(provider="anthropic", model__anthropic=M, **{"ca-file": ""})
    r = env.ask()
    row("the system store does not know the test CA: net, the certificate was not accepted (no ca-file named)", r["t"] == "err" and r.get("code") == "net" and "certificate" in r["msg"], repr(r))
    env.conf(provider="anthropic", model__anthropic=M)
    r = env.ask()
    row("with ca-file naming the CA the same call is ok", r["t"] == "ok", repr(r))
    env.conf(provider="anthropic", model__anthropic=M, **{"ca-file": "relative/ca.pem"})
    r = env.ask()
    row("a ca-file that is not a plain absolute path is badconf", r.get("code") == "badconf", repr(r))

    say("\n--- the timeout")
    env.reset_counters()
    env.conf(provider="anthropic", model__anthropic=M, **{"limit.timeout": "1"})
    t0 = time.time()
    r = env.ask("[[slow]]")
    row("a provider that answers after 3 s with a 1 s limit: timeout, in about a second", r["t"] == "err" and r.get("code") == "timeout" and time.time() - t0 < 2.9, repr((r, round(time.time() - t0, 1))))

    say("\n--- status")
    env.reset_counters()
    env.conf(provider="openai", model__openai=M)
    env.key("openai")
    env.gate(True)
    env.conf(provider="openai", model__openai=M)
    r = env.ask(op="status")
    ok = r["t"] == "status" and r["provider"] == "openai" and r["model"] == M and r["key"] is True and r["gate"] is True and set(r.get("providers", {})) == {"anthropic", "openai", "deepseek", "custom"} \
        and r["providers"]["openai"]["key"] is True and r["providers"]["anthropic"]["key"] is True \
        and r["providers"]["openai"]["maxparam"] == "max_completion_tokens" and r["limits"]["tokens-day"] == 100000 and r["ca-file"] == env.ca
    row("status for the user's own process: the provider, the model, a key is set, the gate is on, the four rows with their details and keys, the limits and the ca-file", ok, repr(r)[:300])
    row("no status reply holds the key", KEY not in json.dumps(r), "")
    env.gate(False)
    env.conf(provider="openai", model__openai=M)
    r = env.ask(op="status")
    row("status is answered with the gate off (the page needs it) and says so: gate false", r["t"] == "status" and r["gate"] is False and r["provider"] == "openai", repr(r)[:200])
    env.gate(True)

    say("\n--- what leaves the machine, and what does not")
    os.environ["SD_CANARY_ENV"] = "canary-in-the-environment-4711"
    decoy = os.path.join(env.tmp, "decoy.txt")
    with open(decoy, "w") as f:
        f.write("canary-in-a-file-4711\n")
    env.reset_counters()
    env.conf(provider="anthropic", model__anthropic=M)
    env.key("anthropic")
    n0 = len(fm.log)
    for p in ("hello", "second [[echo]]", "third"):
        env.ask(p)
    blob = b"".join(json.dumps(x["headers"]).encode() + x["body"] for x in fm.log[n0:])
    row("the canary in the environment and the one in a file never appear in anything sent to the provider (%d requests)" % (len(fm.log) - n0),
        b"canary-in-the-environment-4711" not in blob and b"canary-in-a-file-4711" not in blob and len(fm.log) - n0 == 3, "")
    sent_keys = {x["headers"].get("x-api-key") for x in fm.log[n0:]}
    row("the key goes only in its own header", sent_keys == {KEY} and all(KEY.encode() not in x["body"] for x in fm.log[n0:]), repr(sent_keys))
    env.logs.clear()
    r = env.ask("[[echo]] show me")
    row("the key is in no reply and no log line (the [[echo]] reply holds the whole request body, and the key is a header, not in it)",
        KEY not in json.dumps(r) and not any(KEY in l for l in env.logs) and r["t"] == "ok", repr(env.logs))
    row("the one line the helper logs has the uid, provider, status and sizes - no text", len(env.logs) == 1 and "uid=%d" % os.getuid() in env.logs[0] and "provider=anthropic" in env.logs[0]
        and "show me" not in env.logs[0], repr(env.logs))

    say("\n--- the other certificates")
    for stem, what in (("wrongname", "a certificate for another name"), ("rogue", "a certificate no CA vouches for")):
        fm2 = fakemodel.FakeModel(env.ca.rsplit("/", 1)[0], cert=stem).start()
        try:
            with open(env.providers) as f:
                text = f.read()
            alt = os.path.join(env.tmp, "providers-" + stem)
            with open(alt, "w") as f:
                f.write(text.replace(":%d" % fm.port, ":%d" % fm2.port))
            env.conf(provider="anthropic", model__anthropic=M)
            old = env.providers
            env.providers = alt
            r = env.ask()
            env.providers = old
        finally:
            fm2.stop()
        row("%s is refused: net, certificate" % what, r["t"] == "err" and r.get("code") == "net" and "certificate" in r["msg"], repr(r))
    say("\n--- the real program")
    env.gate(False)
    env.conf(provider="anthropic", model__anthropic=M)
    env.gate(True)
    a, b = socket.socketpair()
    a.sendall(b'{"v":1,"op":"ask","prompt":"hi"}\n')
    p = subprocess.run([sys.executable, env.helper_path, "--state", env.state, "--providers", env.providers], stdin=b.fileno(), stdout=b.fileno(), stderr=subprocess.PIPE, timeout=30)
    b.close()
    data = a.recv(65536)
    a.close()
    r = json.loads(data.decode()) if data else {}
    row("run as a program with the delivered ai.conf (no gate line): exit 0 and a nogate reply, one stderr line", p.returncode == 0 and r.get("code") == "nogate" and p.stderr.count(b"\n") == 1, repr((p.returncode, r, p.stderr)))
    p = subprocess.run([sys.executable, env.helper_path, "--bogus"], capture_output=True, timeout=30)
    row("an argument it does not know is a usage message and exit 2", p.returncode == 2 and b"usage" in p.stderr, repr(p))


def conf_text(env):
    p = os.path.join(env.state, "ai.conf")
    return open(p).read() if os.path.exists(p) else None


def rows_settings(env, fm):
    """The administrator's settings through the same socket (set, keyset, keyclear), in this process."""
    mod = env.mod
    M = "claude-test-model"
    say("\n--- the settings: who may change them")
    env.stranger(True)
    env.conf(provider="anthropic", model__anthropic=M)
    before = conf_text(env)
    for stale in ("openai",):
        if os.path.exists(os.path.join(env.state, "keys", stale)):
            os.remove(os.path.join(env.state, "keys", stale))
    for req in ({"op": "set", "what": "provider", "value": "openai"}, {"op": "keyset", "provider": "openai", "key": KEY}, {"op": "keyclear", "provider": "anthropic"},
                {"op": "set", "what": "limit", "name": "tokens-day", "value": "5"}, {"op": "set", "what": "gate", "value": "no"}):
        r = env.ask(raw=json.dumps(dict(req, v=1)).encode() + b"\n")
        row("a caller whose uid is not the helper's own is refused %s with nogate" % req["op"] + ("/" + req.get("what", "") if "what" in req else ""),
            r.get("code") == "nogate", repr(r))
    row("...and nothing was changed: ai.conf is as it was and no key file for openai was made", conf_text(env) == before and not os.path.exists(os.path.join(env.state, "keys", "openai")), "")
    env.stranger(False)
    say("\n--- the settings: provider, model")
    os.remove(os.path.join(env.state, "ai.conf"))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"openai"}\n')
    t = conf_text(env)
    st = os.stat(os.path.join(env.state, "ai.conf"))
    row("the user's own process selects openai with no ai.conf yet: ok, ai.conf is made with provider=openai, mode 0600, no temporary file left", r.get("t") == "ok" and "provider=openai" in t.splitlines() and stat.S_IMODE(st.st_mode) == 0o600
        and not os.path.exists(os.path.join(env.state, "ai.conf.new")), repr((r, t)))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"gate","value":"yes"}\n')
    row("the gate is turned on: ok, and ai.conf holds exactly the line gate=yes", r.get("t") == "ok" and "gate=yes" in conf_text(env).splitlines(), repr((r, conf_text(env))))
    t = conf_text(env)
    for v in ("maybe", "", "YES", 1, None):
        r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "gate", "value": v}).encode() + b"\n")
        row("a gate value %r is badreq and ai.conf is unchanged" % (v,), r.get("code") == "badreq" and conf_text(env) == t, repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"gate","value":"no"}\n')
    row("the gate is turned off: ok, and the gate line is gone from ai.conf (off is the absence, never a word that could be misread)", r.get("t") == "ok" and not any(l.startswith("gate") for l in conf_text(env).splitlines()), repr((r, conf_text(env))))
    env.ask(raw=b'{"v":1,"op":"set","what":"gate","value":"yes"}\n')
    r = env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"martian"}\n')
    row("a provider that is none of the four is badreq and ai.conf is unchanged", r.get("code") == "badreq" and conf_text(env) == t, repr(r))
    r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "model", "provider": "openai", "value": M}).encode() + b"\n")
    row("a model for openai: ok, model.openai in ai.conf, and provider kept", r.get("t") == "ok" and "model.openai=" + M in conf_text(env).splitlines() and "provider=openai" in conf_text(env).splitlines(), repr(r))
    t = conf_text(env)
    for bad in ("bad model; rm -rf /", "a" * 101, "-leading", "new\nline"):
        r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "model", "provider": "openai", "value": bad}).encode() + b"\n")
        row("a model name %r is badreq and ai.conf is unchanged" % bad[:20], r.get("code") == "badreq" and conf_text(env) == t, repr(r))
    r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "model", "provider": "martian", "value": M}).encode() + b"\n")
    row("a model for a provider that does not exist is badreq", r.get("code") == "badreq", repr(r))
    r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "model", "provider": "openai", "value": ""}).encode() + b"\n")
    row("an empty model clears it", r.get("t") == "ok" and "model.openai" not in conf_text(env), repr(r))

    say("\n--- the settings: Custom")
    t = conf_text(env)
    r = env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"custom"}\n')
    row("custom cannot be selected before its connection details are given: badconf, ai.conf unchanged", r.get("code") == "badconf" and conf_text(env) == t, repr(r))
    good = {"v": 1, "op": "set", "what": "custom", "name": "My LLM", "url": "https://llm.example.org/v1/chat/completions", "format": "openai", "auth": "bearer", "version": "", "maxparam": "max_tokens"}
    r = env.ask(raw=json.dumps(good).encode() + b"\n")
    c = conf_text(env).splitlines()
    row("the custom connection is stored whole: custom.name, .url, .format, .auth, .maxparam (no empty version line)", r.get("t") == "ok" and "custom.url=https://llm.example.org/v1/chat/completions" in c
        and "custom.name=My LLM" in c and "custom.maxparam=max_tokens" in c and not any(l.startswith("custom.version") for l in c), repr((r, c)))
    t = conf_text(env)
    for what, change in (("an http URL", {"url": "http://llm.example.org/v1"}), ("a bad format", {"format": "gemini"}), ("a bad auth style", {"auth": "basic"}), ("a URL with userinfo", {"url": "https://a:b@llm.example.org/"})):
        r = env.ask(raw=json.dumps(dict(good, **change)).encode() + b"\n")
        row("custom with %s is badconf and ai.conf is unchanged" % what, r.get("code") == "badconf" and conf_text(env) == t, repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"custom"}\n')
    row("now custom can be selected", r.get("t") == "ok" and "provider=custom" in conf_text(env).splitlines(), repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"custom-clear"}\n')
    row("clearing custom while it is the selected provider is refused (badreq): select another first", r.get("code") == "badreq" and "custom.url=https://llm.example.org/v1/chat/completions" in conf_text(env), repr(r))
    env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"anthropic"}\n')
    r = env.ask(raw=b'{"v":1,"op":"set","what":"custom-clear"}\n')
    row("with another provider selected, custom-clear removes every custom.* line", r.get("t") == "ok" and not any(l.startswith("custom.") for l in conf_text(env).splitlines()), repr(r))

    say("\n--- the settings: ca-file, limits")
    r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "ca", "value": env.ca}).encode() + b"\n")
    row("ca-file naming an existing readable file: ok", r.get("t") == "ok" and "ca-file=" + env.ca in conf_text(env).splitlines(), repr(r))
    t = conf_text(env)
    for v in ("/no/such/file.pem", "relative.pem", "/tmp/../etc/passwd"):
        r = env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "ca", "value": v}).encode() + b"\n")
        row("ca-file %r is badreq and ai.conf is unchanged" % v, r.get("code") == "badreq" and conf_text(env) == t, repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"ca","value":""}\n')
    row("an empty ca-file goes back to the system store", r.get("t") == "ok" and "ca-file" not in conf_text(env), repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"limit","name":"tokens-day","value":"250000"}\n')
    row("a limit: tokens-day 250000 is stored", r.get("t") == "ok" and "limit.tokens-day=250000" in conf_text(env).splitlines(), repr(r))
    t = conf_text(env)
    for req, code in (({"name": "tokens-day", "value": "lots"}, "badreq"), ({"name": "colour", "value": "5"}, "badreq"), ({"name": "timeout", "value": "301"}, "badconf"), ({"name": "tokens-day", "value": "0"}, "badconf")):
        r = env.ask(raw=json.dumps(dict({"v": 1, "op": "set", "what": "limit"}, **req)).encode() + b"\n")
        row("limit %s=%s is %s and ai.conf is unchanged" % (req["name"], req["value"], code), r.get("code") == code and conf_text(env) == t, repr(r))
    r = env.ask(raw=b'{"v":1,"op":"set","what":"flavour","value":"x"}\n')
    row("a setting that does not exist is badreq", r.get("code") == "badreq", repr(r))
    with open(os.path.join(env.state, "ai.conf"), "a") as f:
        f.write("this line has no equals sign\n")
    r = env.ask(raw=b'{"v":1,"op":"set","what":"provider","value":"openai"}\n')
    row("a damaged ai.conf (a line with no =) makes set refuse with badconf instead of rewriting around it", r.get("code") == "badconf", repr(r))
    env.conf(provider="anthropic", model__anthropic=M)

    say("\n--- the settings: keys")
    for f in os.listdir(os.path.join(env.state, "keys")):
        os.remove(os.path.join(env.state, "keys", f))
    env.logs.clear()
    r = env.ask(raw=json.dumps({"v": 1, "op": "keyset", "provider": "deepseek", "key": KEY}).encode() + b"\n")
    kp = os.path.join(env.state, "keys", "deepseek")
    row("a key is set: ok, the file keys/deepseek holds it, mode 0600, no temporary file left", r.get("t") == "ok" and open(kp).read().strip() == KEY and stat.S_IMODE(os.stat(kp).st_mode) == 0o600
        and sorted(os.listdir(os.path.join(env.state, "keys"))) == ["deepseek"], repr((r, os.listdir(os.path.join(env.state, "keys")))))
    row("the key is in no reply and in no log line", KEY not in json.dumps(r) and not any(KEY in l for l in env.logs) and len(env.logs) == 1, repr(env.logs))
    r = env.ask(raw=json.dumps({"v": 1, "op": "keyset", "provider": "deepseek", "key": KEY + "-two"}).encode() + b"\n")
    row("a second key replaces the first, whole", r.get("t") == "ok" and open(kp).read().strip() == KEY + "-two", repr(r))
    for what, req in (("a key that is too short", {"provider": "openai", "key": "short"}), ("a key with a space", {"provider": "openai", "key": "has a space in it"}),
                      ("a key with a newline", {"provider": "openai", "key": "line1\nline2-0123456789"}), ("a key for a provider that does not exist", {"provider": "martian", "key": KEY}),
                      ("a key that is not text", {"provider": "openai", "key": 12345678})):
        r = env.ask(raw=json.dumps(dict({"v": 1, "op": "keyset"}, **req)).encode() + b"\n")
        row("%s is badreq and no file is made" % what, r.get("code") == "badreq" and not os.path.exists(os.path.join(env.state, "keys", "openai")), repr(r))
    r = env.ask(raw=b'{"v":1,"op":"keyclear","provider":"deepseek"}\n')
    row("keyclear removes the file", r.get("t") == "ok" and not os.path.exists(kp), repr(r))
    r = env.ask(raw=b'{"v":1,"op":"keyclear","provider":"deepseek"}\n')
    row("keyclear of a key that is not there is ok too", r.get("t") == "ok", repr(r))
    r = env.ask(raw=b'{"v":1,"op":"keyclear","provider":"../x"}\n')
    row("keyclear with a path for a provider is badreq", r.get("code") == "badreq", repr(r))

    say("\n--- the settings: made through the socket, then used")
    for f in os.listdir(os.path.join(env.state, "keys")):
        os.remove(os.path.join(env.state, "keys", f))
    os.remove(os.path.join(env.state, "ai.conf"))
    env.ask(raw=json.dumps({"v": 1, "op": "set", "what": "ca", "value": env.ca}).encode() + b"\n")
    for req in ({"op": "set", "what": "provider", "value": "deepseek"}, {"op": "set", "what": "model", "provider": "deepseek", "value": M}, {"op": "keyset", "provider": "deepseek", "key": KEY},
                {"op": "set", "what": "gate", "value": "yes"}):
        assert env.ask(raw=json.dumps(dict(req, v=1)).encode() + b"\n").get("t") == "ok"
    env.reset_counters()
    n0 = len(fm.log)
    r = env.ask("What is six times seven?")
    row("provider, model, key and gate all set through the socket: a request goes to deepseek's path with that key and that model",
        r.get("t") == "ok" and r.get("provider") == "deepseek" and fm.log[n0]["path"] == "/chat/completions" and fm.log[n0]["headers"].get("authorization") == "Bearer " + KEY
        and json.loads(fm.log[n0]["body"])["model"] == M, repr(r))
    r = env.ask(op="status")
    row("status now shows deepseek selected with its model and key, and the gate on", r.get("provider") == "deepseek" and r["providers"]["deepseek"]["model"] == M and r["providers"]["deepseek"]["key"] is True
        and r["providers"]["anthropic"]["key"] is False and r["gate"] is True, repr(r)[:300])


def rows_ctl(env, fm):
    """sd-ai-ctl against a real Unix socket served by ai-runner.py, as the user."""
    say("\n--- sd-ai-ctl, the client, against a socket served as systemd would serve it")
    ctl = os.path.join(HERE, "sd-ai-ctl")
    runner = os.path.join(HERE, "ai-runner.py")
    sock = os.path.join(env.tmp, "sock")
    for f in os.listdir(os.path.join(env.state, "keys")):
        os.remove(os.path.join(env.state, "keys", f))
    if os.path.exists(os.path.join(env.state, "ai.conf")):
        os.remove(os.path.join(env.state, "ai.conf"))
    p = subprocess.Popen([sys.executable, runner, "--socket", sock, "--state", env.state, "--providers", env.providers,
                          "--helper", env.helper_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        if p.stdout.readline().strip() != "ready":
            row("the test runner started", False, "")
            return

        def run(*a, stdin=None):
            r = subprocess.run([sys.executable, ctl, "--socket", sock] + list(a), input=stdin, capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout, r.stderr

        rc, out, err = run("show")
        row("show with nothing set: exit 0, says the AI is off and the gate is off, and lists the four rows with their details", rc == 0 and "none (the AI is off)" in out and "gate: off" in out and out.count("[ ]") == 4
            and ("https://127.0.0.1:%d/v1/messages" % fm.port) in out and "(not set)" in out, repr((rc, out[:400], err)))
        rc, out, err = run("gate", "on")
        row("gate on: ok, and ai.conf holds gate=yes, mode 0600", rc == 0 and out.strip() == "ok" and "gate=yes" in conf_text(env).splitlines() and stat.S_IMODE(os.stat(os.path.join(env.state, "ai.conf")).st_mode) == 0o600, repr((rc, out, err)))
        rc, out, err = run("show")
        row("show now says the gate is on", rc == 0 and "gate: on" in out, repr(out[:200]))
        rc, out, err = run("gate", "maybe")
        row("gate with a word that is neither on nor off is a usage message and exit 2, and the gate stays on", rc == 2 and "gate=yes" in conf_text(env).splitlines(), repr((rc, out, err)))
        rc, out, err = run("gate", "off")
        row("gate off: ok, and the gate line is gone", rc == 0 and out.strip() == "ok" and not any(l.startswith("gate") for l in conf_text(env).splitlines()), repr((rc, out, err)))
        rc, out, err = run("provider", "openai")
        row("provider openai: ok", rc == 0 and out.strip() == "ok", repr((rc, out, err)))
        rc, out, err = run("model", "openai", "gpt-test")
        row("model openai gpt-test: ok", rc == 0 and out.strip() == "ok", repr((rc, out, err)))
        rc, out, err = run("key", "openai", stdin=KEY + "\n")
        kp = os.path.join(env.state, "keys", "openai")
        row("key openai, the key on stdin (not a terminal): 'The key for openai is set.', the file holds it, mode 0600, and the key is in neither stdout nor stderr",
            rc == 0 and out.strip() == "The key for openai is set." and open(kp).read().strip() == KEY and stat.S_IMODE(os.stat(kp).st_mode) == 0o600 and KEY not in out + err, repr((rc, out, err)))
        rc, out, err = run("show")
        row("show now: openai is [x] with its model, key set, and the key is not printed", rc == 0 and "[x] openai" in out and "model: gpt-test" in out and "key: set" in out and KEY not in out, repr(out))
        rc, out, err = run("show", "--json")
        j = json.loads(out)
        row("show --json is the helper's status: provider openai, the four providers with details and keys", j.get("provider") == "openai" and j["providers"]["openai"]["key"] is True and set(j["providers"]) == {"anthropic", "openai", "deepseek", "custom"}, repr(out)[:200])
        rc, out, err = run("custom", "My LLM", "https://llm.example.org/v1/chat/completions", "openai", "bearer", "-", "max_tokens")
        row("custom with - for the version: ok", rc == 0 and out.strip() == "ok" and "custom.url=https://llm.example.org/v1/chat/completions" in conf_text(env), repr((rc, out, err)))
        rc, out, err = run("custom", "My LLM", "http://llm.example.org/v1", "openai", "bearer", "-", "max_tokens")
        row("custom with an http URL: exit 1 and the helper's words (badconf)", rc == 1 and out.startswith("error: badconf"), repr((rc, out, err)))
        rc, out, err = run("limit", "tokens-day", "50000")
        row("limit tokens-day 50000: ok", rc == 0 and "limit.tokens-day=50000" in conf_text(env).splitlines(), repr((rc, out, err)))
        rc, out, err = run("key", "openai", stdin="short\n")
        row("a key that is too short: exit 1, error: badreq, and the old key is still there", rc == 1 and out.startswith("error: badreq") and open(kp).read().strip() == KEY, repr((rc, out, err)))
        rc, out, err = run("key-clear", "openai")
        row("key-clear openai: the file is gone", rc == 0 and not os.path.exists(kp), repr((rc, out, err)))
        rc, out, err = run("provider", "none")
        row("provider none turns the AI off: provider= is empty", rc == 0 and "provider=" in conf_text(env).splitlines(), repr((rc, out, err, conf_text(env))))
        for args, what in ((("provider",), "no provider word"), (("model", "openai"), "a model with no name"), (("frobnicate",), "a command that does not exist"), (("key", "martian"), "a key for no provider")):
            rc, out, err = run(*args, stdin="x\n")
            row("%s is a usage message and exit 2" % what, rc == 2, repr((rc, out, err)))
        r = subprocess.run([sys.executable, ctl, "--socket", os.path.join(env.tmp, "no-such-socket"), "show"], capture_output=True, text=True, timeout=60)
        row("a socket that is not there: exit 2 and a plain sentence, not a traceback", r.returncode == 2 and "could not be reached" in r.stderr and "Traceback" not in r.stderr, repr((r.returncode, r.stderr)))
        mode = stat.S_IMODE(os.stat(sock).st_mode)
        row("the runner's socket is mode 0600 (as the user unit makes it): nobody else can connect", mode == 0o600, oct(mode))
    finally:
        p.terminate()
        p.wait(timeout=10)


MUTANTS = [
    ("the gate is not asked", '        if not gate_on(conf):\n            return {"t": "err", "code": "nogate", "msg": "the AI is not turned on for this account"}, "-"\n', "        pass\n"),
    ("any gate word opens it", '    return conf.get("gate", "") == "yes"', '    return conf.get("gate", "") != ""'),
    ("a stranger is not refused", "    if not own_user(uid):", "    if False:"),
    ("every uid is the helper's own", "    return uid is not None and uid == os.getuid()", "    return True"),
    ("a connection that is not a socket is the helper's own", "    return uid is not None and uid == os.getuid()", "    return uid is None or uid == os.getuid()"),
    ("status says the gate is on when it is off", '"gate": gate_on(conf)}', '"gate": True}'),
    ("the gate is stored as a word that can be misread", '            new["gate"] = "yes" if v == "yes" else ""', '            new["gate"] = v'),
    ("ai.conf is made readable by the group", "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n    with os.fdopen(fd, \"w\", encoding=\"ascii\") as f:\n        f.write(\"\\n\".join(lines)", "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)\n    with os.fdopen(fd, \"w\", encoding=\"ascii\") as f:\n        f.write(\"\\n\".join(lines)"),
    ("certificate verification off", "    ctx.check_hostname = True\n    ctx.verify_mode = ssl.CERT_REQUIRED\n", "    ctx.check_hostname = False\n    ctx.verify_mode = ssl.CERT_NONE\n"),
    ("host name not checked", "    ctx.check_hostname = True\n", "    ctx.check_hostname = False\n"),
    ("the reply is not cut to ASCII", "        text, replaced = hygiene(text)\n", "        replaced = 0\n"),
    ("a key file anyone can read is used", "        if st.st_mode & 0o077 or not stat.S_ISREG(st.st_mode):", "        if not stat.S_ISREG(st.st_mode):"),
    ("the hourly and daily limits are not applied", "        counters(state, uid, time.time(), limits, count=True)\n", "        pass\n"),
    ("tokens are not added to the day's total", "        counters(state, uid, time.time(), limits, add_tokens=tin + tout)\n", "        pass\n"),
    ("a 429 is not retried", "        if status in (429, 500, 502, 503, 504) and attempt == 1:", "        if status in (429, 500, 502, 503, 504) and attempt == 0:"),
    ("an http URL is accepted", 'URL_RE = re.compile(r"^https://', 'URL_RE = re.compile(r"^https?://'),
    ("maxtokens is not clamped", "        maxtokens = max(1, min(maxtokens, limits[\"max-tokens\"]))\n", "        pass\n"),
    ("a redirect is treated as an answer to parse", "        if 300 <= status < 400:\n", "        if False:\n"),
    ("the model name is not checked", "        if not MODEL_RE.match(model):\n", "        if False:\n"),
    ("the request size is not checked", "        if len(prompt.encode(\"utf-8\")) + len(system.encode(\"utf-8\")) > limits[\"bytes-request\"]:", "        if False:"),
    ("a refusal by the model is not recognised (anthropic)", '            if j.get("stop_reason") == "refusal":', '            if False:'),
    ("a setting is not checked as a whole before it is written", "        selected(new, table)", "        pass  #"),
    ("a key file is made readable by others", 'tmp = os.path.join(d, "." + name + ".new")\n    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)',
     'tmp = os.path.join(d, "." + name + ".new")\n    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)'),
    ("keyset gives the key back in its reply", 'return {"t": "ok", "key": "set"}', 'return {"t": "ok", "key": "set", "echo": key}'),
    ("the range of a limit is not checked when it is set", "        for k in LIMITS:\n            int_setting(new, k)\n        write_conf(state, new)", "        write_conf(state, new)"),
    ("a ca-file that is not there is accepted", " or not os.path.isfile(v) or not os.access(v, os.R_OK)", ""),
    ("a damaged ai.conf is skipped over", '                    raise Refuse("badconf", "%s line %d has no =" % (os.path.basename(path), n))', "                    continue"),
]


def selftest(helper, first=0, count=None):
    """Every mutant from number `first` on (--selftest --from=N: a sitting runs its own mutants, the whole set runs at a release); --count=K stops after K
    (the eight of Solo's own gate come first: --from=0 --count=8)."""
    with open(helper) as f:
        src = f.read()
    bad = 0
    for name, old, new in (MUTANTS[first:] if count is None else MUTANTS[first:first + count]):
        if src.count(old) != 1:
            say("  [FAIL] mutant %r: the old text occurs %d times in the helper, it must occur once" % (name, src.count(old)))
            bad += 1
            continue
        d = tempfile.mkdtemp(prefix="aihelper-mut-")
        try:
            path = os.path.join(d, "sd-ai")
            with open(path, "w") as f:
                f.write(src.replace(old, new))
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "--helper", path], capture_output=True, text=True, timeout=600)
            failed_rows = [l for l in p.stdout.splitlines() if "[FAIL]" in l]
            if p.returncode == 1 and failed_rows:
                say("  [caught] %s (%d rows red, e.g. %s)" % (name, len(failed_rows), failed_rows[0].strip()[:90]))
            else:
                say("  [MISSED] %s (exit %d, no row failed)" % (name, p.returncode))
                bad += 1
        finally:
            shutil.rmtree(d, ignore_errors=True)
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--helper", helper], capture_output=True, text=True, timeout=600)
    say("  [%s] control: the unmutated helper passes (exit %d)" % ("ok" if p.returncode == 0 else "FAIL", p.returncode))
    bad += p.returncode != 0
    say("\nselftest: %s" % ("all behaved" if bad == 0 else "%d problem(s)" % bad))
    return 0 if bad == 0 else 1


def main():
    helper = os.path.join(HERE, "sd-ai")
    if "--helper" in sys.argv:
        helper = os.path.abspath(sys.argv[sys.argv.index("--helper") + 1])
    if "--selftest" in sys.argv:
        first, count = 0, None
        for a in sys.argv:
            if a.startswith("--from="):
                first = int(a[len("--from="):])
            if a.startswith("--count="):
                count = int(a[len("--count="):])
        return selftest(helper, first, count)
    if not shutil.which("openssl"):
        say("test-aihelper: CANNOT RUN - the openssl command line is needed for the throw-away certificates")
        return 2
    say("test-aihelper: helper %s" % helper)
    tmp = tempfile.mkdtemp(prefix="aihelper-")
    fm = None
    try:
        os.makedirs(os.path.join(tmp, "pki"))
        pki = fakemodel.make_pki(os.path.join(tmp, "pki"))
        fm = fakemodel.FakeModel(pki).start()
        env = Env(load(helper), tmp, fm, os.path.join(pki, "ca.crt"))
        env.helper_path = helper
        rows(env, fm)
        rows_settings(env, fm)
        rows_ctl(env, fm)
    finally:
        if fm:
            fm.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    say("\ntest-aihelper: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 and passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
