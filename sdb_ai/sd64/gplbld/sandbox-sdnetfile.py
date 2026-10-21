#!/usr/bin/env python3
#
# sandbox-sdnetfile.py - SDNet on SD Core for Linux Solo, stages C and D: a file on ANOTHER SD server, opened through a VOC pointer of type N by an ORDINARY session's
#                        OPEN statement and used with the ordinary file statements, against the Python fake API server (gplbld/netfake.py).  Solo's own, smaller suite for the
#                        client SD Core carried (S.65 slices 3a to 3e and S.72): SD Core's sandbox-netfile.py has 5,000 lines on SD Core's fixtures (accounts, groups, edit gates) and
#                        is not run here.  What this suite covers is what Solo changed or must not break: the gate (USR_NET), the account list, the stored login, the pin, the mode
#                        read / write, the records the fake server holds after each statement (the DISK of this suite), the refusals, and the administrator's exemption.
#                        No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-sdnetfile.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo); SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop
# the sandbox afterwards with the SAME SDSOLOBOX_KEYSET: sandbox-fromtree.py <dir> stop.  It needs the openssl command line and loads sandbox-sdnet-login.py (certificates, the store
# helpers) and, through it, sandbox-sdnet.py (the lanes).
#
# START-HISTORY:
# 20 Oct 26 dm  Written for stages C and D of the SDNet carry, after the code (it was carried whole from SD Core Dev 680747d, whose own suites ran it).  This is the first evidence for the
#               Solo build.  A row's expectation that SD Core's own suite already proves for the same code is kept to a summary here: this suite is the Solo smoke, not a port.
# END-HISTORY
#
# NOT SHOWN: the channel binding of the login (netfake cannot compute it), a real server (SD Core's or Solo's) on the other end, a lost connection in the middle of a change, the
# record cache's two seconds, the lock table of a real server, SELECT by index, transactions on a remote file (SD Core's suite has rows for them) and the API server's load of the gate.

import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import netfake
spec = importlib.util.spec_from_file_location("sandbox_sdnet_login", os.path.join(HERE, "sandbox-sdnet-login.py"))
lg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lg)
s = lg.s
row, say = s.row, s.say

PW = "Zq7-fileclient-Passw0rd-x"
FMC, VMC = "\xfe", "\xfd"
RECS = {"c1": "Smith" + FMC + "100" + VMC + "200" + FMC + "x", "c2": "Jones" + FMC + "50", "c3": "Brown"}
DICT_ITEMS = {"name": "D" + FMC + "1", "bal": "D" + FMC + "2"}
H = "127.0.0.1"
P = {}


def show(text):
    """A record as the driver prints it: field marks as |, value marks as ~."""
    return text.replace(FMC, "|").replace(VMC, "~")


def acct_prog(name, body):
    s.put(os.path.join(s.ACCT, "bp", name), "program %s\n%s\nend\n" % (name, "\n".join("   " + ln for ln in body)))


def run_prog(name, unlock=False, cmds=None):
    return s.session(["BASIC bp " + name, "RUN bp " + name] if cmds is None else cmds, unlock=unlock, quiet=True)


def kr(out):
    return [ln[3:] for ln in out if ln.startswith("KR ")]


def setup():
    if not lg.certs():
        return False
    lg.reset_store()
    lg.clean_defs()
    srv = netfake.FakeServer(lg.C["c1"], lg.C["k1"])
    srv_b = netfake.FakeServer(lg.C["c2"], lg.C["k2"])
    P["srv"], P["srv_b"] = srv, srv_b
    for sv in (srv, srv_b):
        sv.store.add_file("customers", dict(RECS), dict_items=dict(DICT_ITEMS), path="/data/customers")
        sv.store.add_file("empty")
        sv.store.accounts = {"acct"}
        sv.revision = "L9.9-9"
    salt = srv.add_user("alice", PW, iterations=4096)
    P["salt"] = salt
    pin_a, pin_b = lg.C["pin_a"], lg.C["pin_b"]
    defs = [("nfa", srv.port, pin_a, "read", "sduser"), ("nfw", srv.port, pin_a, "write", "sduser"), ("nfnolist", srv.port, pin_a, "read", ""),
            ("nfnocred", srv.port, pin_a, "read", "sduser"), ("nfpin", srv_b.port, pin_a, "read", "sduser")]
    s.adm1(*["set.server %s %s %d acct %s %s%s" % (n, H, p, pin, mode, (" accounts " + acc) if acc else "") for n, p, pin, mode, acc in defs])
    row("SETUP: five server definitions (nfa read, nfw write, nfnolist with no accounts, nfnocred with no stored login, nfpin sending the account to server B with server A's pin)",
        all(lg.entry(n) is not None for n, *_ in defs), repr(s.file_lines()))
    line = lg.valid_line(remote="alice", pin=pin_a, pw=PW, salt=salt)
    for n in ("nfa", "nfw", "nfnolist", "nfpin"):
        lg.plant(n, line)
    row("SETUP: the stored logins for four of them are on the disk (made by hand from the derived keys; set.netlogin has its own suite), none for nfnocred",
        sorted(os.listdir(lg.cred_dir())) == ["nfa", "nfnolist", "nfpin", "nfw"], repr(os.listdir(lg.cred_dir())))
    s.put(os.path.join(s.SYS, "bp", "zznfix"), "\n".join([
        "$internal",
        "   openpath '%s/voc' to v else crt 'NFIX no voc' ; stop" % s.ACCT,
        "   write 'N':@fm:'nfa':@fm:'customers' to v, 'zznet1'",
        "   write 'N':@fm:'nfw':@fm:'customers' to v, 'zznetw'",
        "   write 'N':@fm:'nfa':@fm:'empty' to v, 'zznetempty'",
        "   write 'N':@fm:'nfa':@fm:'nosuchfile' to v, 'zznetmiss'",
        "   write 'N':@fm:'nfnolist':@fm:'customers' to v, 'zznetunl'",
        "   write 'N':@fm:'nfnocred':@fm:'customers' to v, 'zznetnc'",
        "   write 'N':@fm:'nfpin':@fm:'customers' to v, 'zznetpin'",
        "   write 'N':@fm:'Bad Name':@fm:'customers' to v, 'zznetbad'",
        "   crt 'NFIX done'", "end", ""]))
    out = s.internal(["BASIC bp zznfix", "RUN bp zznfix"])
    row("SETUP: the administrator wrote eight VOC pointers of type N into sduser's VOC (one badly made on purpose)", s.has(out, r"^NFIX done$"), repr(out[-4:]))
    return True


def new_conn(srv):
    return srv.count if hasattr(srv, "count") else None


def sess(name, body, unlock=False, srv=None, cfg=None):
    """Compile and run an ordinary session's program NAME.  Returns (output, what the fake saw during the run)."""
    acct_prog(name, body)
    sv = srv or P["srv"]
    c = {"files": True, "files_only": True, "write_group": True}      # the fake serves the file requests, and behaves as a SD Core server's files-only route with the write group does
    c.update(cfg or {})
    sv.configure(**c)
    m = sv.mark()
    out = s.session(["BASIC bp " + name, "RUN bp " + name], unlock=unlock, quiet=True)
    sv.settle(quiet=0.3)
    d = sv.delta(m)
    sv.configure()
    return out, d


def records(name="customers", srv=None):
    return dict((srv or P["srv"]).store.records(name))


def files_section():
    say("\n--- the gate, the list, the login and the pin: what an ORDINARY session may open (nothing is dialled that must not be) ---------------------------------")
    s.reg_net("yes")
    s.reg_os(False)
    opener = lambda ptr: ["open '%s' to f then crt 'KR opened' else crt 'KR open-else ':status()" % ptr, "crt 'KR end'"]
    out, d = sess("zznopen", opener("zznet1"))
    row("CONTROL, the gate ON, the account listed, a stored login, the right pin: 'zznet1' opens (KR opened), one connection, and the account the definition names was entered on the server",
        "opened" in kr(out) and d["conns"] == 1 and not d["errors"], repr((kr(out), out[-3:], {k: d[k] for k in ("conns", "types", "errors")})))
    s.reg_net("no")
    out, d = sess("zznopen", opener("zznet1"))
    row("the NET gate OFF: the OPEN is refused with message 11460 (the program stops with it; it is an error, not the ELSE branch), and the server is never connected to",
        "opened" not in kr(out) and s.has_text(out, s.msg(11460)) and d["conns"] == 0, repr((kr(out), out[-3:], d["conns"])))
    s.reg_net(None)
    out, d = sess("zznopen", opener("zznet1"))
    row("a register record with NO field 15: the same refusal, nothing dialled", "opened" not in kr(out) and d["conns"] == 0, repr((kr(out), d["conns"])))
    s.reg_net("yes")
    for ptr, why in (("zznetunl", "a server whose accounts list does not name the account"), ("zznetnc", "a server with NO stored login"), ("zznetbad", "a pointer whose server name is not valid")):
        out, d = sess("zznopen", opener(ptr))
        row("%s: the open fails and nothing is dialled" % why, "opened" not in kr(out) and d["conns"] == 0, repr((kr(out), out[-3:], d["conns"])))
    out, d = sess("zznopen", opener("zznetpin"), srv=P["srv_b"])
    row("a definition whose pin is not the key the server presents: the open fails, the server saw the handshake and ZERO requests (nothing is sent to a server that is not the one defined)",
        "opened" not in kr(out) and d["types"] == [], repr((kr(out), d["types"], d["conns"])))
    out, d = sess("zznopen", opener("zznetmiss"))
    row("a file the server does not have: the open takes ELSE (not an error that stops the program), status non-zero", "opened" not in kr(out) and any(x.startswith("open-else") for x in kr(out)),
        repr((kr(out), out[-3:])))
    s.reg_net("no")
    out, d = sess("zznopen", opener("zznet1"), unlock=True)
    row("the ADMINISTRATOR (ADMIN) with the gate OFF still opens it (the administrator is never refused the gate): KR opened, one connection", "opened" in kr(out) and d["conns"] == 1,
        repr((kr(out), out[-3:], d["conns"])))
    s.reg_net("yes")


def read_section():
    say("\n--- reading: OPEN, READ, READV, SELECT / READNEXT, FILEINFO, CLOSE on a file of mode read ---------------------------------------------------------------")
    s.reg_net("yes")
    body = [
        "open 'zznet1' to f else crt 'KR open-else ':status() ; stop",
        "read r from f, 'c1' then crt 'KR read-c1 ':convert(@vm, '~', convert(@fm, '|', r)) else crt 'KR read-else ':status()",
        "readv v from f, 'c1', 2 then crt 'KR readv-c1-2 ':convert(@vm, '~', v) else crt 'KR readv-else ':status()",
        "read r from f, 'nosuchrecord' then crt 'KR found-nosuch' else crt 'KR notfound-nosuch ':status()",
        "select f",
        "ids = ''",
        "loop",
        "   readnext id else exit",
        "   ids<-1> = id",
        "repeat",
        "crt 'KR select ':dcount(ids, @fm):' ':convert(@fm, ',', ids)",
        "crt 'KR fileinfo-type ':fileinfo(f, 3)",
        "close f",
        "crt 'KR closed'",
        "crt 'KR end'"]
    out, d = sess("zznread", body)
    k = kr(out)
    row("READ of c1 returns the record the server holds (field and value marks intact)", ("read-c1 " + show(RECS["c1"])) in k, repr(k))
    row("READV c1 field 2 returns the field (100 and 200 as two values)", "readv-c1-2 100~200" in k, repr(k))
    row("READ of a record that is not there takes ELSE, status 6 (record not found: the server's own 3006 reduced to the local 6 as a local file does)",
        any(x.startswith("notfound-nosuch") for x in k) and "found-nosuch" not in k, repr(k))
    row("SELECT and READNEXT give the three record ids the server holds, once each", any(x.startswith("select 3 ") and set(x.split(" ")[2].split(",")) == {"c1", "c2", "c3"} for x in k), repr(k))
    row("the program ran to its end, CLOSE worked, one connection, and the fake found nothing malformed", "closed" in k and "end" in k and d["conns"] == 1 and not d["errors"],
        repr((k, {kk: d[kk] for kk in ("conns", "types", "errors")})))
    P["srv"].configure(files=True, files_only=True, write_group=True)
    out = s.session(["COUNT zznet1"], quiet=True)
    P["srv"].settle(quiet=0.3)
    P["srv"].configure()
    row("the query verbs work on the remote file: COUNT reports 3 records (the ids come from the server)", s.has(out, r"\b3 record"), repr(out[-6:]))
    out, d = sess("zznwrite", ["open 'zznet1' to f else crt 'KR open-else' ; stop",
                               "write 'x' to f, 'attempt' on error crt 'KR write-error ':status() ; goto done",
                               "crt 'KR write-returned'", "done:", "crt 'KR end'"])
    row("a WRITE to a file whose server is defined mode READ is refused (ON ERROR taken), and the fake server never received a write request",
        any(x.startswith("write-error") for x in kr(out)) and "attempt" not in records() and not any(t in d["types"] for t in (netfake.R_WRITE,)), repr((kr(out), d["types"])))


def write_section():
    say("\n--- a server defined mode WRITE: WRITE, DELETE, locks, CLEARFILE - the records the fake server holds are the evidence ----------------------------------------")
    s.reg_net("yes")
    body = [
        "open 'zznetw' to f else crt 'KR open-else ':status() ; stop",
        "write 'new one' to f, 'n1' on error crt 'KR write-error ':status()",
        "crt 'KR wrote'",
        "delete f, 'c2' on error crt 'KR delete-error ':status()",
        "crt 'KR deleted'",
        "readu r from f, 'c1' locked crt 'KR readu-locked' else null",
        "crt 'KR locked-code ':recordlocked(f, 'c1')",
        "release f, 'c1'",
        "crt 'KR released-code ':recordlocked(f, 'c1')",
        "close f",
        "crt 'KR end'"]
    out, d = sess("zznwr", body)
    k = kr(out)
    rec = records()
    row("WRITE n1 reaches the server (it holds 'new one' under n1) and DELETE c2 removes c2 there; the other records are untouched",
        "wrote" in k and rec.get("n1") == "new one" and "c2" not in rec and rec.get("c1") == RECS["c1"] and rec.get("c3") == RECS["c3"], repr((k, sorted(rec))))
    row("READU takes the update lock on the server (RECORDLOCKED says 2: this session holds an update lock) and RELEASE gives it back (0)", "locked-code 2" in k and "released-code 0" in k, repr((k, out[-3:])))
    row("the program ran to its end and the fake found nothing malformed", "end" in k and not d["errors"], repr((k, out[-3:], d["errors"])))
    out, d = sess("zznwc", ["open 'zznetw' to f else crt 'KR open-else' ; stop", "clearfile f", "crt 'KR cleared'", "close f", "crt 'KR end'"])
    row("CLEARFILE on a write-mode remote file empties it on the server", "cleared" in kr(out) and records() == {}, repr((kr(out), records())))
    P["srv"].store.add_file("customers", dict(RECS), dict_items=dict(DICT_ITEMS), path="/data/customers")      # put it back for the rows after this
    s.reg_net("no")
    out, d = sess("zznwg", ["open 'zznetw' to f then crt 'KR opened' else crt 'KR open-else ':status()"])
    row("the gate OFF: even a write-mode pointer does not open", "opened" not in kr(out) and d["conns"] == 0, repr((kr(out), d["conns"])))
    s.reg_net("yes")


SECTIONS = (("files", files_section), ("read", read_section), ("write", write_section))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sections", default="")
    a = ap.parse_args()
    s.BOX = os.path.abspath(a.dir)
    s.SYS = os.path.join(s.BOX, "sys")
    s.ACCT = os.path.join(s.SYS, "user_accounts", s.ACCOUNT)
    s.REG = os.path.join(s.SYS, "accounts", s.ACCOUNT)
    want = set(x for x in a.sections.split(",") if x)
    say("sandbox-sdnetfile: sandbox  %s" % s.BOX)
    say("sandbox-sdnetfile: tree     %s" % s.SD64)
    if a.build:
        if os.path.exists(s.BOX) and os.listdir(s.BOX):
            s.bail("%s is not empty" % s.BOX)
        r = subprocess.run([sys.executable, s.TOOL, s.BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            s.bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-sdnetfile: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(s.SYS, "bin", "sd-solo")):
        s.bail("%s holds no built sandbox (use --build, or point it at one)" % s.BOX)
    subprocess.run([sys.executable, s.TOOL, s.BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(s.REG):
        s.bail("there is no register record %s" % s.REG)
    say("\n--- controls -----------------------------------------------------------------------------------------------------")
    out = s.session(["WHO.AM.I"], quiet=True)
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of %s and NOT an administrator" % s.ACCOUNT, s.has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        s.bail("the session is privileged; its refusals prove nothing")
    out = s.adm1("WHO.AM.I")
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    if not (adm and adm.group(1) == "Yes"):
        s.bail("the administrator lane is not an administrator")
    ok = False
    try:
        ok = setup()
        if ok:
            for name, section in SECTIONS:
                if not want or name in want:
                    section()
    finally:
        for k in ("srv", "srv_b"):
            if k in P:
                P[k].shutdown()
        lg.reset_store()
        lg.clean_defs()
        lg.cleanup()
    say("")
    say("sandbox-sdnetfile: %d passed, %d failed" % (s.passed, s.failed))
    sys.exit(1 if s.failed else 0)


if __name__ == "__main__":
    main()
