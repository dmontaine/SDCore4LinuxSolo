#!/usr/bin/env python3
#
# sandbox-sdnetfile.py - SDNet on SD Core for Linux Solo, stages C and D: a file on ANOTHER SD server, opened through a VOC pointer of type N by an ORDINARY session's
#                        OPEN statement and used with the ordinary file statements, against the Python fake API server (gplbld/netfake.py).  Solo's own, smaller suite for the
#                        client SD Core carried (S.65 slices 3a to 3e and S.72): SD Core's sandbox-netfile.py has 5,000 lines on SD Core's fixtures (accounts, groups, edit gates) and
#                        is not run here.  What this suite covers is what Solo changed or must not break: the gate (USR_NET), the account list, the stored login, the pin, the mode
#                        read / write, the records the fake server holds after each statement (the DISK of this suite), the refusals, and the administrator's exemption.
#                        No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-sdnetfile.py <dir> [--build] [--mutant=NAME]
#   (--mutant=NAME takes one rule out of the sandbox's own copy of $netfile, the class !sdclient or the kernel, and says whether the rows that failed are exactly the rows listed for it in
#   MUTANT_KILLS below; what each mutant changes is in sandbox-sdnet.py, MUTANTS.  A kernel mutant is a copy of the sandbox's tree made again, and the sandbox is stopped and started with it.)
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo); SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop
# the sandbox afterwards with the SAME SDSOLOBOX_KEYSET: sandbox-fromtree.py <dir> stop.  It needs the openssl command line and loads sandbox-sdnet-login.py (certificates, the store
# helpers) and, through it, sandbox-sdnet.py (the lanes).
#
# START-HISTORY:
# 21 Oct 26 dm  RUNTIME MUTANTS (--mutant, MUTANT_KILLS).  Rows added because a mutant found no row: a stored login of mode 640 and a link to a good login (netcred READ's private test, end to end),
#               the handler's own gate (an $internal program calls $netfile directly: the kernel's check is not on its way), and the kernel's gate before the handler is loaded (the handler
#               replaced by a stub that says when it is reached: the kernel's and the handler's refusal are otherwise the same message and the same audit line, and the kernel mutant failed NO row).
# 20 Oct 26 dm  Written for stages C and D of the SDNet carry, after the code (it was carried whole from SD Core Dev 680747d, whose own suites ran it).  This is the first evidence for the
#               Solo build.  A row's expectation that SD Core's own suite already proves for the same code is kept to a summary here: this suite is the Solo smoke, not a port.
# END-HISTORY
#
# NOT SHOWN: the channel binding of the login (netfake cannot compute it), a real server (SD Core's or Solo's) on the other end, a lost connection in the middle of a change, the
# record cache's two seconds, the lock table of a real server, SELECT by index, transactions on a remote file (SD Core's suite has rows for them).  (The API server's load of the gate is
# sandbox-apifile.py section N since 21 Oct 26.)

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


# An $internal program is exempt from the kernel's gate (the S.63 lesson), so one that calls the HANDLER directly reaches only the handler's own check.gate; the kernel's net_gate_ok() is
# not on its way.  Reached by a catalogued verb, so that it runs in an ORDINARY (non-administrator) session.
ZZNFGATE = "\n".join([
    "$internal", "program zznfgate", "$catalog $zznfgate", "$include keys.h", "$include int$keys.h", "$include netfile.h",
    "   out = ''", "   rc = ''",
    "   call $netfile(NF$OPEN, 'nfa', 'customers', '', out, rc)",
    "   crt 'NG rc=':rc<1>:' msg=':rc<2>", "end", ""])


# A HANDLER THAT SAYS WHEN IT IS REACHED.  The kernel's net_gate_ok() and the handler's check.gate refuse in the same words, audit the same line and dial nothing, so with both in place no row can
# tell which one refused.  The kernel is documented to ask BEFORE the handler is loaded; with the handler replaced by this stub (it audits `netfile-stub reached op=<n>` and answers an error) an
# OPEN with the gate OFF must not reach it.  The stub is the sandbox's gpl.bp/netfile for the length of the rows that need it; what was there is put back (compiled again), whether it was the staged
# handler or a mutant of it.  A killed run leaves a gpl.bp/netfile that is not the staged one, which sandbox-sdnet.py's pristine control (and its restore) catches.
HANDLER_STUB = "\n".join([
    "$internal", "subroutine netfile(op, a, b, c, out, rc)", "$catalog $netfile", "$include keys.h", "$include int$keys.h", "$include netfile.h",
    "   void kernel(K$AUDIT, 'netfile-stub reached op=' : op)",
    "   out = ''", "   rc = ''", "   rc<1> = NF$RC.ERROR", "   rc<2> = 11490", "   rc<3> = 'stub'", "end", ""])


class HandlerStub:
    def __enter__(self):
        self.saved = s._read(s.sandbox_bp("netfile"))
        s._write(s.sandbox_bp("netfile"), HANDLER_STUB)
        self.ok, out = s.compile_bp("netfile")
        row("SETUP: the handler stub (gpl.bp/netfile replaced for the next rows) compiles", self.ok, repr(out[-4:]))
        return self

    def __exit__(self, *exc):
        s._write(s.sandbox_bp("netfile"), self.saved)
        ok, out = s.compile_bp("netfile")
        row("SETUP: the handler that was there before the stub is compiled again", ok, repr(out[-4:]))
        return False


def verb(cmd, unlock=False, srv=None):
    """An ordinary session runs the verb CMD against the fake.  Returns (output, what the fake saw during the run)."""
    sv = srv or P["srv"]
    sv.configure(files=True, files_only=True, write_group=True)
    m = sv.mark()
    out = s.session([cmd], unlock=unlock, quiet=True)
    sv.settle(quiet=0.3)
    d = sv.delta(m)
    sv.configure()
    return out, d


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
            ("nfnocred", srv.port, pin_a, "read", "sduser"), ("nfpin", srv_b.port, pin_a, "read", "sduser"),
            ("nfmode", srv.port, pin_a, "read", "sduser"), ("nflink", srv.port, pin_a, "read", "sduser")]
    s.adm1(*["set.server %s %s %d acct %s %s%s" % (n, H, p, pin, mode, (" accounts " + acc) if acc else "") for n, p, pin, mode, acc in defs])
    row("SETUP: seven server definitions (nfa read, nfw write, nfnolist with no accounts, nfnocred with no stored login, nfpin sending the account to server B with server A's pin, nfmode and "
        "nflink whose stored logins are not private)", all(lg.entry(n) is not None for n, *_ in defs), repr(s.file_lines()))
    line = lg.valid_line(remote="alice", pin=pin_a, pw=PW, salt=salt)
    for n in ("nfa", "nfw", "nfnolist", "nfpin"):
        lg.plant(n, line)
    lg.plant("nfmode", line, mode=0o640)                       # a GOOD login in every respect but its mode: group bits
    os.symlink(lg.cred_path("nfa"), lg.cred_path("nflink"))    # the name of a login that is a LINK to a good login (nfa's)
    row("SETUP: the stored logins are on the disk (made by hand from the derived keys; set.netlogin has its own suite): nfa nfnolist nfpin nfw private, nfmode with mode 640, nflink a symbolic "
        "link to nfa's, none for nfnocred",
        sorted(os.listdir(lg.cred_dir())) == ["nfa", "nflink", "nfmode", "nfnolist", "nfpin", "nfw"] and os.path.islink(lg.cred_path("nflink"))
        and (os.stat(lg.cred_path("nfmode")).st_mode & 0o7777) == 0o640, repr(os.listdir(lg.cred_dir())))
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
        "   write 'N':@fm:'nfmode':@fm:'customers' to v, 'zznetmode'",
        "   write 'N':@fm:'nflink':@fm:'customers' to v, 'zznetlink'",
        "   write 'V':@fm:'CA':@fm:'$zznfgate' to v, 'zznfgate'",
        "   crt 'NFIX done'", "end", ""]))
    s.put(os.path.join(s.SYS, "gpl.bp", "zznfgate"), ZZNFGATE)
    out = s.internal(["BASIC gpl.bp zznfgate"])
    row("SETUP: the probe zznfgate (an $internal program that calls the HANDLER, $netfile, directly) compiles", s.compiled(out), repr(out[-4:]))
    out = s.internal(["BASIC bp zznfix", "RUN bp zznfix"])
    row("SETUP: the administrator wrote ten VOC pointers of type N into sduser's VOC (one badly made on purpose) and the verb zznfgate", s.has(out, r"^NFIX done$"), repr(out[-4:]))
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
    for ptr, why in (("zznetunl", "a server whose accounts list does not name the account"), ("zznetnc", "a server with NO stored login"), ("zznetbad", "a pointer whose server name is not valid"),
                     ("zznetmode", "a server whose stored login file has group bits (mode 640, a good login in every other respect)"),
                     ("zznetlink", "a server whose stored login is a SYMBOLIC LINK to a good login")):
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

    say("  (the HANDLER asks the gate itself: the kernel's check is not on the way of an $internal program that calls $netfile)")
    s.reg_net("no")
    out, d = verb("zznfgate")
    row("the HANDLER asks the gate itself: an $internal program that calls $netfile (NF$OPEN) directly, the gate OFF, is answered rc 3, message 11460, and nothing is dialled",
        s.has_line(out, "NG rc=3 msg=11460") and d["conns"] == 0, repr((out[-3:], d["conns"])))
    s.reg_net("yes")
    out, d = verb("zznfgate")
    row("...and with the gate ON the same call opens (rc 0, one connection): the refusal above is the gate and not the call", s.has_line(out, "NG rc=0 msg=") and d["conns"] == 1, repr((out[-3:], d["conns"])))

    say("  (the KERNEL asks the gate before the handler is loaded: the handler is replaced by a stub that says when it is reached)")
    with HandlerStub():
        s.reg_net("no")
        off = lg.audit_off()
        out, d = sess("zznopen", opener("zznet1"))
        new = lg.audit_new(off)
        row("the KERNEL asks the gate before the handler is loaded: with the handler replaced by a stub and the gate OFF, an ordinary OPEN is refused with 11460 and the stub is NEVER REACHED "
            "(the audit trail has the refusal and no 'netfile-stub reached')",
            "opened" not in kr(out) and s.has_text(out, s.msg(11460)) and new is not None and "netfile refused server=nfa reason=gate" in new and "netfile-stub reached" not in new
            and d["conns"] == 0, repr((kr(out), out[-2:], new)))
        s.reg_net("yes")
        off = lg.audit_off()
        out, d = sess("zznopen", opener("zznet1"))
        new = lg.audit_new(off)
        row("...and with the gate ON the same OPEN does reach the stub (the audit trail says 'netfile-stub reached op=1'): the row above is the kernel's gate and not a stub that is never called",
            new is not None and "netfile-stub reached op=1" in new and d["conns"] == 0, repr((kr(out), out[-2:], new)))


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

# The mutants this suite judges (sandbox-sdnet.py's MUTANTS says what each changes; --mutant=NAME).  REQUIRED rows are listed BEFORE the first run of the mutant: a substring each, naming exactly one
# row, that must FAIL; `also` may fail because the rule is gone; anything else that fails is EXTRA and fails the run.  `survives` is a DOCUMENTED GAP: no row can notice the mutant.
MUTANT_KILLS = {
    # a stored login that is not private is used (the end of the road of netcred-read-private, which sandbox-sdnet-login.py judges at $netcred): the two rows that put one in the store and OPEN.
    "netcred-read-private": dict(sections=("files",), required=[
        "a server whose stored login file has group bits (mode 640", "a server whose stored login is a SYMBOLIC LINK"]),
    # the server is dialled before a stored login that is missing, not private or a link is refused: every row that asserts "nothing is dialled" for a login problem.
    "netfile-dial-first": dict(sections=("files",), required=[
        "a server with NO stored login: the open fails and nothing is dialled", "a server whose stored login file has group bits (mode 640", "a server whose stored login is a SYMBOLIC LINK"]),
    # the handler does not ask whether the account is listed for the server (check 3), or the class does not compare the pin (the handshake is made, the login sent to whatever answers).
    "netfile-no-list": dict(sections=("files",), required=["a server whose accounts list does not name the account"]),
    "sdclient-no-pin": dict(sections=("files",), required=["a definition whose pin is not the key the server presents"]),
    # the handler does not ask the gate: only the row that reaches the handler without the kernel notices (the kernel's own check answers an ordinary OPEN first).
    "netfile-no-gate": dict(sections=("files",), required=["the HANDLER asks the gate itself"]),
    # the kernel's net_gate_ok() says yes and the handler still asks.  The FIRST RUN of this mutant (21 Oct 26, before the stub rows existed) failed NO row: the two layers say the same message,
    # audit the same line and dial nothing, so no row that reaches the handler can tell which one refused.  The stub rows (the handler replaced by one that says when it is reached) can.
    "netfiles-gate-open": dict(sections=("files", "write"), required=["the KERNEL asks the gate before the handler is loaded: with the handler replaced by a stub"]),
    # both layers gone: every row that opens with the gate off, the direct call of the handler, and the stub row.
    "gate-both": dict(sections=("files", "write"), required=[
        "the NET gate OFF: the OPEN is refused with message 11460", "a register record with NO field 15: the same refusal", "the HANDLER asks the gate itself",
        "the KERNEL asks the gate before the handler is loaded: with the handler replaced by a stub", "the gate OFF: even a write-mode pointer does not open"]),
}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sections", default="")
    s.mutant_args(ap)
    a = ap.parse_args()
    mutant, msections = s.mutant_plan(a, MUTANT_KILLS)
    s.BOX = os.path.abspath(a.dir)
    s.SYS = os.path.join(s.BOX, "sys")
    s.ACCT = os.path.join(s.SYS, "user_accounts", s.ACCOUNT)
    s.REG = os.path.join(s.SYS, "accounts", s.ACCOUNT)
    want = msections if mutant else set(x for x in a.sections.split(",") if x)
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
    if not s.control_pristine():
        s.bail("the sandbox is not pristine")
    ok = False
    try:
        if mutant:
            s.mutant_begin(mutant)
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
        if mutant:
            s.mutant_end()
    say("")
    say("sandbox-sdnetfile: %d passed, %d failed" % (s.passed, s.failed))
    if mutant:
        k = MUTANT_KILLS[mutant]
        sys.exit(s.mutant_verdict(mutant, k["required"], k.get("also", ()), k.get("survives", False)))
    sys.exit(1 if s.failed else 0)


if __name__ == "__main__":
    main()
