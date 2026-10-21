#!/usr/bin/env python3
"""test-sdnet-units.py - the Solo SDNet CLIENT (SD Core's S.65 and S.72 carried on 20 Oct 2026) as invariants read off the source: the gate, the definitions, the stored logins, the handler and
the kernel's remote-file type.  Written after the carry, to be run with --selftest.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-sdnet-units.py
  python3 .../test-sdnet-units.py --selftest

No sudo, no install, no sd.  Exit 0 every check passed, 1 a check failed, 2 it could not run.

***WHAT THIS IS, AND WHAT IT IS NOT.***  It reads the C and BASIC source as text, comments removed.  ***IT DOES NOT RUN ANYTHING, SO IT CANNOT SAY THAT A GATE REFUSES ANYBODY***: that is
sandbox-sdnet.py (the gate and the definitions), sandbox-sdnet-login.py (the logins against a fake server) and sandbox-sdnetfile.py (the statements on a remote file).  What a text check is for: the
invariants that make these a gate and a private store are ORDERING (the gate, the list and the stored login are asked before anything is dialled; the private-file test before any use of a stored
login; the directory made before the prompts) and PRESENCE (the administrator-only verbs ask for the administrator; the audit line carries no pin or password), and an edit that moves or drops one still
compiles.  It also holds the deliberate differences from SD Core: nothing here may mention a gates word, an edit gate, a Linux group route or sd-elevate, because Solo has none of them.

***AND THE CHECKS ARE THEMSELVES CHECKED.***  --selftest breaks each invariant in the way an edit plausibly would and requires the NAMED check to notice.  A mutant that nothing catches is a FAILURE of
the self-test.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.abspath(os.path.join(HERE, os.pardir))
SDSYS = os.path.join(SD64, "sdsys")
GPL = os.path.join(SDSYS, "gpl.bp")
SRC = os.path.join(SD64, "gplsrc")

FILES = {
    "netfiles.c": os.path.join(SRC, "netfiles.c"),
    "op_kernel.c": os.path.join(SRC, "op_kernel.c"),
    "keys.h": os.path.join(SRC, "keys.h"),
    "sysseg.h": os.path.join(SRC, "sysseg.h"),
    "descr.h": os.path.join(SRC, "descr.h"),
    "gpl.src": os.path.join(SD64, "gpl.src"),
    "int$keys.h": os.path.join(GPL, "int$keys.h"),
    "login": os.path.join(GPL, "login"),
    "apisrvr": os.path.join(GPL, "apisrvr"),
    "netcred": os.path.join(GPL, "netcred"),
    "setnetlogin": os.path.join(GPL, "setnetlogin"),
    "deletenetlogin": os.path.join(GPL, "deletenetlogin"),
    "setserver": os.path.join(GPL, "setserver"),
    "deleteserver": os.path.join(GPL, "deleteserver"),
    "listservers": os.path.join(GPL, "listservers"),
    "netfile": os.path.join(GPL, "netfile"),
    "sdclient": os.path.join(GPL, "sdclient"),
    # the suites that hold the RUNTIME mutants (21 Oct 26): the table of what each changes, and the tables of which rows must fail (checks R1 and R2)
    "sandbox-sdnet.py": os.path.join(HERE, "sandbox-sdnet.py"),
    "sandbox-sdnet-login.py": os.path.join(HERE, "sandbox-sdnet-login.py"),
    "sandbox-sdnetfile.py": os.path.join(HERE, "sandbox-sdnetfile.py"),
    "sandbox-apifile.py": os.path.join(HERE, "sandbox-apifile.py"),
}
SUITES = ("sandbox-sdnet.py", "sandbox-sdnet-login.py", "sandbox-sdnetfile.py", "sandbox-apifile.py")
VERBS =("set.server", "delete.server", "list.servers", "set.netlogin", "delete.netlogin")
PROGRAMS = {"set.server": "$setserver", "delete.server": "$deleteserver", "list.servers": "$listservers", "set.netlogin": "$setnetlogin", "delete.netlogin": "$deletenetlogin"}
for _v in VERBS:
    FILES["newvoc/" + _v] = os.path.join(SDSYS, "newvoc", _v)
    FILES["voc_template/" + _v] = os.path.join(SDSYS, "voc_template", _v)
RAW = tuple(k for k in FILES if k.startswith(("newvoc/", "voc_template/")))
C_FILES = ("netfiles.c", "op_kernel.c")


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


def strip_c(src):
    src = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def code(name, src):
    if name in RAW or name.endswith(".h") and name not in ("keys.h", "sysseg.h", "descr.h"):
        return src
    if name in C_FILES or name in ("keys.h", "sysseg.h", "descr.h"):
        return strip_c(src)
    if name == "gpl.src":
        return src
    return strip_bas(src)


def at(text, needle, start=0):
    return text.find(needle, start)


def case_block(text, label, length=2600):
    i = text.find(label)
    return text[i:i + length] if i >= 0 else ""


def checks(srcs, messages_dir):
    """[(id, ok, detail)]"""
    rows = []

    def ck(i, ok, detail=""):
        rows.append((i, bool(ok), detail))

    c = {name: code(name, text) for name, text in srcs.items()}

    # ---- K. the key, the flag and the register field -------------------------------------------------------------------
    m1 = re.search(r"#define\s+K_NET\s+(\d+)", srcs["keys.h"])
    m2 = re.search(r"\$define\s+K\$NET\s+(\d+)", srcs["int$keys.h"])
    ck("K1 K_NET is 127 (SD Core's number) in keys.h and K$NET the same in int$keys.h", m1 and m2 and m1.group(1) == m2.group(1) == "127", "%s %s" % (m1 and m1.group(1), m2 and m2.group(1)))
    flags = re.findall(r"#define\s+(USR_[A-Z_]+)\s+(0x[0-9a-fA-F]+)", srcs["sysseg.h"])
    vals = [v.lower() for n, v in flags if n != "USR_GROUPED"]
    ck("K2 USR_NET is 0x1000 and no two USR_ flags share a value (it is a bit of the user table's int16 flags)", ("USR_NET", "0x1000") in flags and len(vals) == len(set(vals)), repr(flags[-6:]))

    # ---- G. the gate ------------------------------------------------------------------------------------------------------
    kall = c["op_kernel.c"]
    kn = kall[kall.find("case K_NET:"):kall.find("case K_PATH_OK")]
    ck("G1 K_NET is set only from a $internal program (both the -2 branch and the set), to USR_NET in the flags word, and a set empties the key ring and drops the account's remote files",
       kn.count("process.program.flags & HDR_INTERNAL") == 2 and "my_uptr->flags |= USR_NET" in kn and "my_uptr->flags &= ~USR_NET" in kn and "kr_wipe()" in kn and "net_close_all()" in kn, kn[:160])
    ck("G2 K_NET -2 (CPROC at the prompt) sends the queued closes, from $internal only", "n == -2" in kn and "net_flush_closes()" in kn and kn.find("HDR_INTERNAL") < kn.find("net_flush_closes()"))
    nets = re.search(r"net_gate_ok\(\)\s*\{(.*?)\}", c["netfiles.c"], re.S)
    ck("G3 net_gate_ok() is the administrator OR the USR_NET flag, nothing else", nets and "USR_ADMIN" in nets.group(1) and "USR_NET" in nets.group(1) and nets.group(1).count("&&") == 0,
       nets and nets.group(1).strip())
    lg = c["login"]
    ck("G4 LOGIN loads K$NET from field 15 (ACC$NET), only the word yes is on, after K$SH and K$OS.EXEC",
       "void kernel(K$NET, upcase(trim(acc.rec<ACC$NET>)) = 'YES')" in lg and at(lg, "void kernel(K$SH,") < at(lg, "void kernel(K$NET,"))
    api = c["apisrvr"]
    ck("G5 the API server reads field 15 for every account it enters, starts it off, and loads K$NET beside K$SH and K$OS.EXEC (only after the entry has passed)",
       "api.net.grant = @false" in api and "api.net.grant = (upcase(trim(acc.rec<ACC$NET>)) = 'YES')" in api
       and 0 < at(api, "void kernel(K$OS.EXEC, api.os.grant)") < at(api, "void kernel(K$NET,     api.net.grant)") and at(api, "api.net.grant = @false") < at(api, "api.net.grant = (upcase"))
    nf = c["netfile"]
    ao = nf[nf.find("act.open:"):]
    i_gate, i_cred, i_conn = at(ao, "gosub check.gate"), at(ao, "$netcred('READ'"), at(ao, "gosub find.slot")
    ck("G6 the handler's open asks the gate (check.gate: the administrator, or K$NET) BEFORE it reads a stored login, and the login BEFORE it takes a slot to dial", 0 < i_gate < i_cred < i_conn, "%s %s %s" % (i_gate, i_cred, i_conn))
    ck("G7 check.gate tests the administrator OR K$NET", "if not(is.admin) and not(kernel(K$NET, -1)) then gate.ok = @false" in nf)

    # ---- S. the definitions ------------------------------------------------------------------------------------------------
    for name in ("setserver", "deleteserver", "listservers"):
        ck("S1 %s asks for the administrator first and stops with 2001 otherwise" % name,
           0 < at(c[name], "kernel(K$ADMINISTRATOR, -1)") < at(c[name], "sysmsg(2001)") < 900 + at(c[name], "kernel(K$ADMINISTRATOR, -1)"))
    ss = c["setserver"]
    ck("S2 set.server audits name, host, port, mode, replaced and HOW the pin was got (typed or confirmed) and never the pin: ' pin=' : pin.how",
       "' pin=' : pin.how" in ss and not re.search(r"K\$AUDIT[^\n]*: pin\b(?!\.)", ss))
    ck("S3 set.server with connect asks the key question after every other check and before the write, and the dial is bounded by NETWAIT",
       0 < at(ss, "if bad # 0 then stop") < at(ss, "gosub connect.pin") < at(ss, "call !netdefs('WRITE'") and "config('NETWAIT')" in ss)

    # ---- N. the store ---------------------------------------------------------------------------------------------------
    nc = c["netcred"]
    ck("N1 the store is <sys>/netlogins, made by $netcred itself with mkdir -m 700 (a quote in the path refused), the file umask is 077, no Linux user name is read",
       "$define NETCRED.DIR   'netlogins'" in nc and "mkdir -m 700 -- '" in nc and "index(cred.dir, \"'\", 1) # 0" in nc and "$define NETCRED.UMASK 63" in nc
       and "K$USERNAME" not in nc and "sd-elevate" not in nc and "/var/lib/sd-net" not in nc)
    ck("N2 EVERY use of a stored login or of its directory is preceded by SD_FILE_PRIVATE (directory test for ENSURE, READ, WRITE; file test for EXISTS, READ, WRITE's temporary file, DELETE)",
       nc.count("SD_FILE_PRIVATE") >= 6 and "SDEXT(tmp : @FM : 'FILE', @TRUE, SD_FILE_PRIVATE)" in nc and "SDEXT(path : @FM : 'FILE', @TRUE, SD_FILE_PRIVATE)" in nc, nc.count("SD_FILE_PRIVATE"))
    ck("N3 WRITE is whole or not at all: a temporary file, tested, then renamed; and the pin ARGUMENT is what is stored", "tmp = path : '.new'" in nc and "osrename(tmp, path)" in nc and "one<6> = pin" in nc)
    ck("N4 the stored line is never the password: $netcred has no password argument, only the derived values", "subroutine netcred(action, server, record, pin, err)" in nc and "password" not in nc.lower())

    # ---- L. set.netlogin --------------------------------------------------------------------------------------------------
    sn = c["setnetlogin"]
    order = [at(sn, "stop sysmsg(11460"), at(sn, "stop sysmsg(11430"), at(sn, "stop sysmsg(11461"), at(sn, "call $netcred('ENSURE'"), at(sn, "crt sysmsg(11464"), at(sn, "open.socket(")]
    ck("L1 set.netlogin asks, in this order and before any prompt or connection: the gate (11460), the definition (11430), the list (11461), the directory (ENSURE), then the prompts (11464), then dials",
       all(x > 0 for x in order) and order == sorted(order), order)
    ck("L2 the gate and the list do not apply to the administrator (the administrator's own login is kept in Solo)", "if not(is.admin) and not(kernel(K$NET, -1)) then" in sn and "if not(is.admin) then" in sn
       and "11462" not in sn and "ACCOS" not in sn and "sd-elevate" not in sn)
    ck("L3 the password is typed hidden, is never in an audit line, is never written, and the key hash is compared with the pin before the first SCRAM packet is sent",
       "input pw HIDDEN" in sn and not re.search(r"K\$AUDIT[^\n]*\bpw\b", sn) and not re.search(r"(writeseq|write)\b[^\n]*\bpw\b", sn)
       and 0 < at(sn, "if spki # pin then") < at(sn, "ptype = SrvrScramFirst"))
    ck("L4 the audit line is set.netlogin server= remote= and delete.netlogin server=, in lower case", "'set.netlogin server=' : name : ' remote=' : ru" in sn and "'delete.netlogin server=' : name" in c["deletenetlogin"])

    # ---- M. messages ----------------------------------------------------------------------------------------------------
    def msg(n):
        try:
            with open(os.path.join(messages_dir, str(n)), encoding="latin-1") as f:
                return f.read()
        except OSError:
            return None
    need = list(range(11412, 11447)) + list(range(11450, 11462)) + list(range(11463, 11480)) + list(range(11490, 11513))
    missing = [n for n in need if msg(n) is None]
    ck("M1 every message the client prints exists (%d)" % len(need), not missing, "missing %r" % missing[:8])
    ck("M2 11439 and 11460 name set.net.access (Solo's word for the gate), not modify.account", msg(11439) and "set.net.access on" in msg(11439) and msg(11460) and "set.net.access on" in msg(11460))
    bad = [n for n in need if msg(n) and re.search(r"modify\.account|sd-elevate|net-on|sdfiles", msg(n), re.I)]
    ck("M3 no carried message names a SD Core command Solo does not have (modify.account, sd-elevate, net-on, sdfiles)", not bad, "%r" % bad)
    gone = [n for n in (11458, 11462, 11480, 11482, 11521, 11522, 11523) if n not in (11458,) and msg(n) is not None]
    ck("M4 the SD Core messages of the Linux-group route and the administrator refusal are not here (11462, 11480, 11482, 11521 to 11523)", not gone, "%r" % gone)

    # ---- A. the server side ---------------------------------------------------------------------------------------------
    i_dict, i_plain = at(api, "if upcase(cmnd[1,5]) = 'DICT ' then"), at(api, "open cmnd to files(i)")
    ck("A1 apisrvr's OPEN takes 'dict <file>' in any case as a dictionary (OPEN 'DICT', name), before the plain OPEN", 0 < i_dict < i_plain and "open 'DICT', trim(cmnd[6,9999]) to files(i)" in api)

    # ---- X. what must NOT be here, because Solo has none of it --------------------------------------------------------------
    nfc = c["netfiles.c"]
    ck("X1 netfiles.c has no gates word, no UG_ bit, no edit gate (S.64 is not in Solo)", not re.search(r"->gates|\bUG_|edit_permitted|edit_kind|EDIT_", nfc), re.findall(r"->gates|\bUG_\w+|edit_\w+", nfc)[:4])
    ck("X2 the NET part of FILE_VAR has no edit_kind and NET_FILE is type 4", not re.search(r"\bedit_kind\b", c["descr.h"]) and re.search(r"#define\s+NET_FILE\s+4\b", c["descr.h"]))
    ck("X3 there is no files-only route here: no apifilesok program, no sdfiles in the API server", not os.path.exists(os.path.join(GPL, "apifilesok")) and "sdfiles" not in api)
    ck("X4 netfiles is in the build list", re.search(r"^netfiles\s*$", c["gpl.src"], re.M))

    # ---- R. the RUNTIME mutants of the sandbox suites ---------------------------------------------------------------------------
    # sandbox-sdnet.py holds MUTANTS (what each runtime mutant changes, in the SANDBOX's copy, text for text).  They stay mutants only while the old text occurs exactly once in the source they
    # change, and are worth having only while some suite lists the rows that must fail.  Both are read as TEXT here, with no sandbox.
    table = re.search(r"^MUTANTS = \{\n(.*?)^\}\n", srcs["sandbox-sdnet.py"], re.S | re.M)
    names = re.findall(r'^    "([a-z0-9-]+)": \(\n', table.group(1), re.M) if table else []
    olds = []
    bad_old = []
    if table:
        ns = {}
        try:
            exec("MUTANTS = {\n" + table.group(1) + "}\n", ns)
            for mname, (_why, parts) in ns["MUTANTS"].items():
                for kind, fn, old, _new in parts:
                    key = fn if kind == "bas" else os.path.basename(fn)
                    olds.append((mname, key))
                    if srcs.get(key, "").count(old) != 1:
                        bad_old.append("%s: %d in %s" % (mname, srcs.get(key, "").count(old), key))
        except Exception as exc:        # a table that does not run is a failed check, not a crashed one
            bad_old.append("the MUTANTS table does not run: %r" % (exc,))
    ck("R1 every RUNTIME mutant of sandbox-sdnet.py (%d, %d changes) finds its old text EXACTLY ONCE in the source it changes (so it is a mutant, not the fixed program under a new name)" % (len(names), len(olds)),
       names and olds and not bad_old, "; ".join(bad_old[:4]))
    unjudged = [n for n in names if not any(('"%s": dict(' % n) in srcs[f] for f in SUITES)]
    ck("R2 every RUNTIME mutant is judged by at least one suite: a MUTANT_KILLS entry (the rows that must fail) in sandbox-sdnet.py, -login, -sdnetfile or sandbox-apifile.py", names and not unjudged, "judged by no suite: %r" % unjudged[:6])
    # R3: the judge itself, run on rows made up here (the module's text is executed, so that the self-test's mutants of that text are seen).  A judge that passes a mutant nothing caught would
    # make every mutant run a green lie.
    import contextlib
    import io
    ns = {"__file__": FILES["sandbox-sdnet.py"], "__name__": "sandbox_sdnet_text"}
    got = {}
    try:
        exec(compile(srcs["sandbox-sdnet.py"], FILES["sandbox-sdnet.py"], "exec"), ns)

        def judge(rows_, required, also=(), survives=False):
            ns["ROWS"][:] = rows_
            with contextlib.redirect_stdout(io.StringIO()):
                return ns["mutant_verdict"]("t", required, also, survives)
        got = {
            "caught": judge([("r1 x", False), ("r2 y", True)], ["r1"]),                      # 0: the required row failed, nothing else did
            "missed": judge([("r1 x", True), ("r2 y", True)], ["r2"]),                       # 1: the required row PASSED on the mutant (and nothing else failed)
            "extra": judge([("r1 x", False), ("r3 z", False)], ["r1"]),                      # 1: a row that is on no list failed
            "also": judge([("r1 x", False), ("r3 z", False)], ["r1"], ["r3"]),               # 0: it is on the `also` list
            "absent": judge([("r1 x", False)], ["no such row"]),                             # 1: the expectation names no row
            "twice": judge([("r1 a", False), ("r1 b", False)], ["r1"]),                      # 1: the expectation names two rows
            "survives": judge([("r1 x", True)], [], (), True),                               # 0: the table says no row can notice, and none did
            "caught-survivor": judge([("r1 x", False)], [], (), True),                       # 1: it was said to survive and a row failed
        }
        want = {"caught": 0, "missed": 1, "extra": 1, "also": 0, "absent": 1, "twice": 1, "survives": 0, "caught-survivor": 1}
    except Exception as exc:        # a judge that does not run is a failed check, not a crashed one
        want = {}
        got = {"error": repr(exc)}
    ck("R3 the judge of a mutant run (mutant_verdict) gives 0 only when the required rows failed, no row outside the lists did, and a documented survivor failed none: eight made-up runs",
       want and got == want, repr(got)[:200])

    # ---- V. the verbs ---------------------------------------------------------------------------------------------------
    for v in VERBS:
        for where in ("newvoc/", "voc_template/"):
            txt = srcs.get(where + v, "")
            parts = txt.split("\n")
            ck("V1 %s%s is a V record (field 1 begins with V), dispatch CA, naming %s" % (where, v, PROGRAMS[v]),
               len(parts) >= 3 and parts[0][:1] == "V" and parts[1] == "CA" and parts[2] == PROGRAMS[v], repr(txt[:40]))
    return rows


def sub(name, old, new):
    def f(srcs):
        s = dict(srcs)
        if old not in s[name]:
            raise KeyError("%s: %r is not in the file, so the mutant cannot be made" % (name, old[:60]))
        s[name] = s[name].replace(old, new, 1)
        return s
    return f


MUTANTS = [
    ("the gate is open to everyone", "G3", sub("netfiles.c", "((my_uptr->flags & USR_NET) != 0)", "1")),
    ("K_NET sets another flag", "G1", sub("op_kernel.c", "my_uptr->flags |= USR_NET;", "my_uptr->flags |= USR_SH;")),
    ("K_NET can be set from any program", "G1", sub("op_kernel.c", "if (process.program.flags & HDR_INTERNAL) {\n          if (n > 0)\n            my_uptr->flags |= USR_NET;", "if (1) {\n          if (n > 0)\n            my_uptr->flags |= USR_NET;")),
    ("a set no longer drops the remote files", "G1", sub("op_kernel.c", "net_close_all();", "")),
    ("USR_NET shares a bit", "K2", sub("sysseg.h", "#define USR_NET         0x1000", "#define USR_NET         0x2000")),
    ("LOGIN loads the gate as on unless the word is no", "G4", sub("login", "upcase(trim(acc.rec<ACC$NET>)) = 'YES')", "upcase(trim(acc.rec<ACC$NET>)) # 'NO')")),
    ("the API server never loads the gate", "G5", sub("apisrvr", "void kernel(K$NET,     api.net.grant)", "")),
    ("the API server's gate starts on", "G5", sub("apisrvr", "api.net.grant = @false", "api.net.grant = @true")),
    ("the handler dials before it reads the login", "G6", sub("netfile", "$netcred('READ'", "$netcred('XREAD'")),
    ("set.server is open to everyone", "S1", sub("setserver", "if not(kernel(K$ADMINISTRATOR, -1)) then", "if 0 then")),
    ("the audit line carries the pin", "S2", sub("setserver", "' pin=' : pin.how", "' pin=' : pin")),
    ("set.server dials before it has checked the fields", "S3", sub("setserver", "if bad # 0 then stop", "if 0 then stop")),
    ("the store is world readable (umask 022)", "N1", sub("netcred", "$define NETCRED.UMASK 63", "$define NETCRED.UMASK 18")),
    ("the directory is made mode 755", "N1", sub("netcred", "mkdir -m 700 -- '", "mkdir -m 755 -- '")),
    ("READ trusts the file without the private test", "N2", sub("netcred", "SDEXT(path : @FM : 'FILE', @TRUE, SD_FILE_PRIVATE) # '1'", "0")),
    ("WRITE renames without testing the new file", "N2", sub("netcred", "SDEXT(tmp : @FM : 'FILE', @TRUE, SD_FILE_PRIVATE) # '1'", "0")),
    ("WRITE writes in place", "N3", sub("netcred", "osrename(tmp, path)", "1")),
    ("set.netlogin makes the directory after the prompts", "L1", sub("setnetlogin", "call $netcred('ENSURE', name, rec, pin, err)", "ens.skip = 1")),
    ("set.netlogin does not ask the gate", "L2", sub("setnetlogin", "if not(is.admin) and not(kernel(K$NET, -1)) then", "if 0 then")),
    ("set.netlogin audits the password", "L3", sub("setnetlogin", "' remote=' : ru", "' remote=' : ru : ' pw=' : pw")),
    ("a message names modify.account again", "M3", None),
    ("the API server does not open a lower case dict", "A1", sub("apisrvr", "if upcase(cmnd[1,5]) = 'DICT ' then", "if cmnd[1,5] = 'DICT ' then")),
    ("netfiles.c asks a gates word again", "X1", sub("netfiles.c", "(my_uptr->flags & USR_ADMIN) != 0)", "(my_uptr->flags & USR_ADMIN) != 0) || (my_uptr->gates & 1)")),
    ("a verb's VOC record runs another program", "V1", sub("newvoc/set.netlogin", "$setnetlogin", "$setserver")),
    ("the text a runtime mutant changes is edited away", "R1", sub("setnetlogin", "if spki # pin then", "if spki # pin then   ;* the key must be the pin")),
    ("a runtime mutant is judged by no suite", "R2", sub("sandbox-sdnetfile.py", '"netfile-no-gate": dict(', '"netfile-no-gate-x": dict(')),
    ("the judge of a mutant run forgets the rows that are on no list", "R3", sub("sandbox-sdnet.py", "    extra = [n for n in bad_rows if n not in named and n not in tolerated]", "    extra = []")),
    ("the judge of a mutant run lets a required row pass", "R3", sub("sandbox-sdnet.py", "        if hits[0][1]:\n            say(\"  [MISSED]", "        if False:\n            say(\"  [MISSED]")),
]


def run_selftest(srcs, messages_dir):
    ok_all = True
    base = checks(srcs, messages_dir)
    base_fail = {r[0] for r in base if not r[1]}
    print("selftest: the unchanged tree fails %d check(s): %s" % (len(base_fail), ", ".join(sorted(base_fail)[:6]) or "none"))
    if base_fail:
        print("selftest: the tree is not whole, so a mutant's own failure cannot be told from the tree's; run the plain check first")
        return False
    for name, want, mut in MUTANTS:
        if mut is None:
            # a message mutant: the messages directory is the unit, so make a scratch copy in memory by checking a one-off
            import tempfile
            import shutil
            tmp = tempfile.mkdtemp(prefix="sdnet-units-")
            try:
                for fn in os.listdir(messages_dir):
                    shutil.copy(os.path.join(messages_dir, fn), os.path.join(tmp, fn))
                with open(os.path.join(tmp, "11439"), "w") as f:
                    f.write("No account is listed (modify.account name net-on)\n")
                failed = sorted({r[0].split()[0] for r in checks(srcs, tmp) if not r[1]})
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        else:
            try:
                mutated = mut(srcs)
            except KeyError as exc:
                print("  [FAIL] selftest: %s  <- %s" % (name, exc))
                ok_all = False
                continue
            failed = sorted({r[0].split()[0] for r in checks(mutated, messages_dir) if not r[1]})
        hit = want in failed
        print("  [%s] selftest: %s is caught by %s (failed: %s)" % ("PASS" if hit else "FAIL", name, want, " ".join(failed) or "none"))
        ok_all = ok_all and hit
    return ok_all


def load():
    srcs, missing = {}, []
    for name, path in FILES.items():
        try:
            with open(path, encoding="latin-1") as f:
                srcs[name] = f.read()
        except OSError:
            srcs[name] = ""
            missing.append(name)
    return srcs, missing


def main(argv):
    srcs, missing = load()
    print("test-sdnet-units: tree %s" % SD64)
    if "netfiles.c" in missing or "netcred" in missing:
        print("test-sdnet-units: CANNOT RUN - netfiles.c or gpl.bp/netcred is not there")
        return 2
    if missing:
        print("test-sdnet-units: not there (their checks fail): %s" % ", ".join(missing))
    messages_dir = os.path.join(SDSYS, "messages")
    rows = checks(srcs, messages_dir)
    failed = 0
    for i, ok, detail in rows:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", i, "" if ok or not detail else "   <- " + str(detail)[:200]))
        failed += 0 if ok else 1
    print("\ntest-sdnet-units: %d passed, %d failed" % (len(rows) - failed, failed))
    ok = failed == 0
    if "--selftest" in argv:
        ok = run_selftest(srcs, messages_dir) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
