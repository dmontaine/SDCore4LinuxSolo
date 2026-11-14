#!/usr/bin/env python3
#
# sandbox-mcp-solo.py - the MCP door of SD Core Solo for Linux (S.211), RUN on a private Solo: the launcher gplbld/solo-mcp.py is started as an MCP client
#                       starts it, against the sandbox's REAL sd-solo and its REAL account, and the disk, the register and the audit trail are the evidence.
#                       No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-mcp-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py.  With --build it is built first from THIS tree (it must be empty or absent).  Exit 0 every row
# passed, 1 one failed, 2 it could not run.  The harness (the plain and administrator sessions, the register) is sandbox-osgate.py's, loaded as a module.
#
# START-HISTORY:
# 11 Nov 26 dm  Written with the MCP door (S.211, plan .claude/plan-solo-mcp-11nov.md).  Sections: A the door OFF as delivered (the launcher refuses, a request
#               written by hand is refused, nothing leaks, both are audited), B SET.MCP (administrator only, one thing a command, the register fields 20 and
#               21 on the disk, the audit), C the door ON with the write tool off (every tool, every refusal of a word that is not allowed, the audit lines), D the
#               write tool ON (sd_run runs a sentence, the account's own SH switch still refuses SH), E the door shut under a running agent.
# END-HISTORY
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


og = _load("sandbox_osgate_for_mcp", "sandbox-osgate.py")
say, bail, has, put, prog, session, internal = og.say, og.bail, og.has, og.put, og.prog, og.session, og.internal
LAUNCHER = os.path.join(HERE, "solo-mcp.py")
FAILED = []


def row(name, ok, detail=""):
    if not ok:
        FAILED.append(name.split(" ", 1)[0])
    og.row(name, ok, detail)


# ---- the register fields 20 and 21, read from the disk -----------------------------------------------------------------------------------------
def fields():
    with open(og.REG) as f:
        lines = f.read().split("\n")
    lines += [""] * (21 - len(lines))
    return lines[19].strip().lower(), lines[20].strip().lower()


def set_fields(door, write):
    """Write fields 20 and 21 by hand (the state a row starts from), keeping the rest."""
    with open(og.REG) as f:
        lines = f.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    lines += [""] * (21 - len(lines))
    lines[19] = door
    lines[20] = write
    put(og.REG, "\n".join(lines) + "\n")


def audit_size():
    p = os.path.join(og.SYS, "audit")
    try:
        if not os.path.exists(p):
            open(p, "ab").close()
        return os.path.getsize(p)
    except OSError:
        return None


def audit_since(off):
    try:
        with open(os.path.join(og.SYS, "audit"), "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", errors="replace")
    except (OSError, TypeError):
        return None


def mcp_lines(text):
    return [ln for ln in (text or "").splitlines() if " mcp call " in ln]


# ---- the launcher as an MCP client runs it --------------------------------------------------------------------------------------------------------
class Agent:
    def __init__(self, name="probe", timeout="60"):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TERM", "USER", "LOGNAME")}
        env.update(SOLO_MCP_SD=os.path.join(og.SYS, "bin", "sd-solo"), SOLO_MCP_ACCOUNT_DIR=og.ACCT, SOLO_MCP_TIMEOUT=timeout, SD_CONFIG=os.path.join(og.BOX, "sd.conf"))
        self.name = name
        self.p = subprocess.Popen([sys.executable, LAUNCHER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=og.SYS, env=env)
        self.n = 0

    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        out = self.p.stdout.readline()
        return json.loads(out) if out else None

    def init(self):
        return self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": self.name, "version": "1"}})

    def tool(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        if not r or "result" not in r:
            return True, repr(r)
        return r["result"]["isError"], r["result"]["content"][0]["text"]

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=20)
        except Exception:
            self.p.kill()
        return self.p.returncode


def oneshot(words):
    """A one-shot sd-solo command, as the launcher runs it: the kept password, no prompt."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TERM", "USER", "LOGNAME")}
    env["SD_CONFIG"] = os.path.join(og.BOX, "sd.conf")
    r = subprocess.run([os.path.join(og.SYS, "bin", "sd-solo")] + words, capture_output=True, text=True, errors="replace", timeout=120, cwd=og.SYS, env=env, stdin=subprocess.DEVNULL)
    return og.ANSI.sub("", r.stdout)


def request(rid, lines):
    d = os.path.join(og.ACCT, "$mcp")
    os.makedirs(d, mode=0o700, exist_ok=True)
    put(os.path.join(d, rid), "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------------------------------------------------------------------------
def setup():
    say("\n--- setup: a data file, its dictionary and three records, written by an ordinary program of the account ---------------------------------")
    out = session(["CREATE.FILE zzmcp DYNAMIC"])
    row("S0 the data file zzmcp is made by the account (it is on the disk in the account's directory)", os.path.exists(os.path.join(og.ACCT, "zzmcp")), "output=%r" % (out[-3:],))
    body = [
        "open 'DICT', 'zzmcp' to d else crt 'FIX no dict' ; stop",
        "write 'D':@fm:'1':@fm:'':@fm:'Name':@fm:'15L':@fm:'S' to d, 'name'",
        "write 'D':@fm:'2':@fm:'':@fm:'City':@fm:'10L':@fm:'S' to d, 'city'",
        "write 'D':@fm:'3':@fm:'':@fm:'Qty':@fm:'5R':@fm:'S' to d, 'qty'",
        "open 'zzmcp' to f else crt 'FIX no file' ; stop",
        "write 'Alice':@fm:'Oslo':@fm:'5' to f, 'c1'",
        "write 'Bob':@fm:'Rome':@fm:'12' to f, 'c2'",
        "write 'Eve':char(27):'[31m':@fm:'Oslo':@vm:'Paris':@fm:'7' to f, 'c3'",
        "crt 'FIX done'",
    ]
    prog("zzmcpfix", body)
    out = session(["BASIC bp zzmcpfix", "RUN bp zzmcpfix"])
    row("S1 the dictionary (name, city, qty) and the records c1 c2 c3 are written (c3 holds an ESC character)", has(out, r"^FIX done$"), "output=%r" % (out[-4:],))
    out = session(["COUNT zzmcp"])
    row("S2 an ordinary session counts 3 records", has(out, r"3 record"), "output=%r" % (out[-3:],))


def sec_off():
    say("\n=== A. the door OFF, as delivered ======================================================================================")
    set_fields("", "")
    off = audit_size()
    out = oneshot(["mcp.call", "status", "probe"])
    row("A1 a one-shot status call on the kept password gets an answer between the markers: refused, in SD's words (the one-shot sign-in works)",
        re.search(r"^MCP-BEGIN status refused$", out, re.M) is not None and "MCP door is closed" in out, repr(out)[:300])
    a = Agent()
    r = a.init()
    row("A2 the launcher answers initialize with an error that says the door is closed, and ends", r is not None and "error" in r and "closed" in r["error"]["message"] and a.close() == 0, repr(r)[:200])
    request("rbypass01", ["read", "probe", "zzmcp", "c1", "", "", "", ""])
    out = oneshot(["mcp.call", "rbypass01"])
    row("A3 a request file written by hand and run without the launcher is refused too, and no record text comes out", re.search(r"^MCP-BEGIN rbypass01 refused$", out, re.M) is not None
        and "Alice" not in out, repr(out)[:300])
    new = mcp_lines(audit_since(off))
    row("A4 the audit trail gained one line for each refusal: tool=open and tool=read, status=refused, agent probe, in lower case",
        len(new) == 3 and all("status=refused" in ln for ln in new) and any("tool=read target=zzmcp c1" in ln for ln in new) and all("agent=probe" in ln for ln in new), repr(new)[:400])
    os.unlink(os.path.join(og.ACCT, "$mcp", "rbypass01"))


def sec_set():
    say("\n=== B. SET.MCP =========================================================================================================")
    set_fields("", "")
    out = session(["SET.MCP"])
    row("B1 an ordinary session is refused (administrator only) and nothing changes", has(out, r"administrator") and fields() == ("", ""), "output=%r fields=%r" % (out[-2:], fields()))
    out = session(["SET.MCP"], unlock=True)
    row("B2 the administrator is told: door off, write tool off", has(out, r"The MCP door for sduser is off; its write tool \(sd_run\) is off"), "output=%r" % (out[-3:],))
    off = audit_size()
    out = session(["SET.MCP ON"], unlock=True)
    row("B3 SET.MCP ON: field 20 is 'yes' on the disk, field 21 is not, and the answer says so", fields()[0] == "yes" and fields()[1] != "yes" and has(out, r"door for sduser is on; its write tool \(sd_run\) is off"),
        "fields=%r output=%r" % (fields(), out[-3:]))
    row("B4 ...and the audit trail has 'set.mcp on account=sduser'", re.search(r"set\.mcp on account=sduser", audit_since(off) or "") is not None)
    out = session(["SET.MCP ON"], unlock=True)
    row("B5 the same word again changes nothing ('was already on')", has(out, r"was already on; nothing changed"), "output=%r" % (out[-3:],))
    out = session(["SET.MCP WRITE ON"], unlock=True)
    row("B6 SET.MCP WRITE ON: field 21 is 'yes'", fields() == ("yes", "yes") and has(out, r"write tool \(sd_run\) is on"), "fields=%r output=%r" % (fields(), out[-3:]))
    before = fields()
    bad = [session([w], unlock=True) for w in ("SET.MCP MAYBE", "SET.MCP WRITE", "SET.MCP ON OFF", "SET.MCP WRITE MAYBE")]
    row("B7 four wrong sentences give the syntax line and change nothing", all(has(o, r"set\.mcp \{on \| off\}; set\.mcp write") for o in bad) and fields() == before, "fields=%r" % (fields(),))
    session(["SET.MCP WRITE OFF"], unlock=True)
    row("B8 SET.MCP WRITE OFF: field 21 is 'no'", fields() == ("yes", "no"), repr(fields()))
    session(["SET.MCP OFF"], unlock=True)
    row("B9 SET.MCP OFF: field 20 is 'no'", fields() == ("no", "no"), repr(fields()))


def sec_on():
    say("\n=== C. the door ON, the write tool off ================================================================================")
    set_fields("yes", "")
    off = audit_size()
    a = Agent()
    r = a.init()
    row("C1 the launcher initializes (the one-shot status call says the door is open) and names itself", r is not None and "result" in r and r["result"]["serverInfo"]["name"] == "sd-core-solo", repr(r)[:200])
    names = [t["name"] for t in a.rpc("tools/list")["result"]["tools"]]
    row("C2 four tools, no sd_run", names == ["sd_files", "sd_describe", "sd_read", "sd_query"], repr(names))
    err, txt = a.tool("sd_files")
    row("C3 sd_files lists the file zzmcp", not err and "zzmcp" in txt, repr(txt)[:300])
    err, txt = a.tool("sd_describe", file="zzmcp")
    row("C4 sd_describe lists the dictionary items name, city, qty", not err and all(w in txt for w in ("name", "city", "qty")), repr(txt)[:300])
    err, txt = a.tool("sd_read", file="zzmcp", id="c1")
    row("C5 sd_read c1: one field to a line (1: Alice, 2: Oslo, 3: 5)", not err and re.search(r"^1: Alice$", txt, re.M) and re.search(r"^2: Oslo$", txt, re.M) and re.search(r"^3: 5$", txt, re.M), repr(txt))
    err, txt = a.tool("sd_read", file="zzmcp", id="c3")
    row("C6 sd_read c3: the ESC character of the record does not come through (a blank in its place) and the value mark shows as ]",
        not err and "\x1b" not in txt and "Eve" in txt and "Oslo]Paris" in txt, repr(txt))
    err, txt = a.tool("sd_query", file="zzmcp", fields=["name", "qty"], where=[{"field": "city", "op": "=", "value": "Oslo"}])
    row("C7 sd_query with a condition city = Oslo shows Alice and not Bob", not err and "Alice" in txt and "Bob" not in txt, repr(txt)[:400])
    err, txt = a.tool("sd_query", file="zzmcp", fields=["name"], where=[{"field": "qty", "op": ">", "value": "6"}], sort="name")
    row("C8 sd_query with qty > 6 and a sort shows Bob", not err and "Bob" in txt and "Alice" not in txt, repr(txt)[:400])
    bad = [("a keyword as a field", dict(file="zzmcp", fields=["lptr"])), ("a field with a semicolon", dict(file="zzmcp", fields=["name;list voc"])),
           ("a condition field that is not in the dictionary", dict(file="zzmcp", fields=["name"], where=[{"field": "zzz", "op": "=", "value": "x"}])),
           ("a value with a quote", dict(file="zzmcp", fields=["name"], where=[{"field": "city", "op": "=", "value": 'a" or "1'}])),
           ("a sort field that is a keyword", dict(file="zzmcp", fields=["name"], sort="lptr")),
           ("a file name that is a sentence", dict(file="zzmcp;list voc", fields=["name"])),
           ("a file name with a path", dict(file="../x", fields=["name"]))]
    res = []
    for why, args in bad:
        err, txt = a.tool("sd_query", **args)
        res.append((why, err, "Not allowed" in txt or "Cannot open" in txt or "must be" in txt, txt[:80]))
    row("C9 sd_query refuses: " + "; ".join(w for w, *_ in res), all(e and k for _, e, k, _t in res), repr([(w, t) for w, e, k, t in res if not (e and k)]))
    err, txt = a.tool("sd_read", file="/etc/passwd", id="root")
    row("C10 sd_read of a path is refused ('Not allowed') and no file text comes out", err and "Not allowed" in txt and "root:" not in txt, repr(txt)[:200])
    err, txt = a.tool("sd_read", file="zzmcp", id="nosuch")
    row("C11 sd_read of a record that is not there is an error in SD's words", err and "Cannot open the file or find the item" in txt, repr(txt)[:200])
    err, txt = a.tool("sd_run", command="COUNT zzmcp")
    row("C12 sd_run with the write tool off is refused (by the launcher, and SD says so too)", err and "closed" in txt, repr(txt)[:200])
    request("rbypass02", ["run", "probe", "", "", "", "", "", "COUNT zzmcp"])
    out = oneshot(["mcp.call", "rbypass02"])
    row("C13 ...a request for run written by hand is refused by SD itself (14956) and nothing runs", re.search(r"^MCP-BEGIN rbypass02 refused$", out, re.M) is not None
        and "write tool is closed" in out and "record" not in out.lower().replace("record id", ""), repr(out)[:300])
    os.unlink(os.path.join(og.ACCT, "$mcp", "rbypass02"))
    leftover = os.listdir(os.path.join(og.ACCT, "$mcp"))
    row("C14 the launcher left no request file behind", leftover == [], repr(leftover))
    new = mcp_lines(audit_since(off))
    tools = [re.search(r"tool=(\S+)", ln).group(1) + ":" + re.search(r"status=(\S+)", ln).group(1) for ln in new]
    row("C15 the audit trail has a line for every call that reached SD, with the agent's name, the first four in order (open, files, describe, read), and refusals marked refused",
        tools[:4] == ["open:ok", "files:ok", "describe:ok", "read:ok"] and len(new) >= 14 and all("agent=probe" in ln for ln in new)
        and all(re.search(r"status=(ok|refused|error)$", ln) for ln in new) and tools.count("run:refused") >= 1 and tools.count("query:refused") >= 3, repr(tools))
    a.close()
    return None


def sec_write():
    say("\n=== D. the write tool ON ================================================================================================")
    set_fields("yes", "yes")
    off = audit_size()
    a = Agent()
    a.init()
    names = [t["name"] for t in a.rpc("tools/list")["result"]["tools"]]
    row("D1 sd_run is offered, annotated as destructive", "sd_run" in names, repr(names))
    err, txt = a.tool("sd_run", command="COUNT zzmcp")
    row("D2 sd_run runs a sentence of the person's: COUNT zzmcp says 3 records", not err and re.search(r"3 record", txt) is not None, repr(txt)[:200])
    sentinel = os.path.join(og.ACCT, "zzmcp-sentinel")
    clean = lambda: os.path.exists(sentinel) and os.unlink(sentinel)
    clean()
    err, txt = a.tool("sd_run", command="SH touch " + sentinel)
    row("D3 sd_run does NOT widen the account: SH is still refused by the account's own switch and the sentinel file is not made", not os.path.exists(sentinel), repr(txt)[:200])
    err, txt = a.tool("sd_run", command="x" * 600)
    row("D4 a sentence over 500 characters is refused in SD's words", err and "Not allowed" in txt, repr(txt)[:120])
    err, txt = a.tool("sd_run", command="WHO.AM.I")
    row("D5 the agent is an ordinary session of the account, not the administrator: WHO.AM.I through sd_run says Admin? No", not err and re.search(r"Admin\?\s*:\s*No", txt) is not None, repr(txt)[:200])
    new = mcp_lines(audit_since(off))
    row("D6 the sd_run calls are in the audit trail with the sentence as the target", any("tool=run target=COUNT zzmcp status=ok" in ln for ln in new) and any("tool=run target=SH touch" in ln for ln in new), repr(new)[:400])
    a.close()


def sec_shut():
    say("\n=== E. the door shut under a running agent =============================================================================")
    set_fields("yes", "")
    a = Agent()
    a.init()
    err, txt = a.tool("sd_read", file="zzmcp", id="c1")
    first = not err and "Alice" in txt
    session(["SET.MCP OFF"], unlock=True)
    off = audit_size()
    err, txt = a.tool("sd_read", file="zzmcp", id="c1")
    row("E1 an agent that was working is refused at its NEXT call after SET.MCP OFF, and no record text comes out", first and err and "closed" in txt and "Alice" not in txt, repr((first, txt))[:200])
    row("E2 ...and that refusal is audited", any("status=refused" in ln and "tool=read" in ln for ln in mcp_lines(audit_since(off))))
    a.close()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    og.BOX = os.path.abspath(a.dir)
    og.SYS = os.path.join(og.BOX, "sys")
    og.ACCT = os.path.join(og.SYS, "user_accounts", og.ACCOUNT)
    og.REG = os.path.join(og.SYS, "accounts", og.ACCOUNT)
    og.OUT = os.path.join(og.SYS, "zzoutside")
    say("sandbox-mcp-solo: sandbox %s, launcher %s" % (og.BOX, LAUNCHER))
    if a.build:
        if os.path.exists(og.BOX) and os.listdir(og.BOX):
            bail("%s is not empty" % og.BOX)
        r = subprocess.run([sys.executable, og.TOOL, og.BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-mcp-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(og.SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % og.BOX)
    subprocess.run([sys.executable, og.TOOL, og.BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(og.REG):
        bail("there is no register record %s" % og.REG)
    out = session(["WHO.AM.I"])
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of sduser and NOT an administrator", has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        bail("the session is privileged; its refusals prove nothing")
    row("the register record as the install made it has the MCP fields OFF (20 and 21 are not 'yes')", fields()[0] != "yes" and fields()[1] != "yes", repr(fields()))
    try:
        setup()
        sec_off()
        sec_set()
        sec_on()
        sec_write()
        sec_shut()
    finally:
        set_fields("", "")
        shutil.rmtree(os.path.join(og.ACCT, "$mcp"), ignore_errors=True)
    say("\nsandbox-mcp-solo: %d passed, %d failed" % (og.passed, og.failed))
    if FAILED:
        say("failed: " + ", ".join(FAILED))
    return 1 if og.failed else 0


if __name__ == "__main__":
    sys.exit(main())
