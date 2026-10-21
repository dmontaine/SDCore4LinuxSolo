#!/usr/bin/env python3
"""test-netgate-units.py - the Solo NET gate and the rule for API request 29 (the SDNet open), as invariants read off the source.  Solo's copy of the
shape of SD Core's fix fccf976 (18 Oct 26), written FIRST, before any of it existed, and run red.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-netgate-units.py
  python3 .../test-netgate-units.py --selftest

No sudo, no install, no sd.  Exit 0 every check passed, 1 a check failed, 2 it could not run.  Written 20 Oct 26.

***WHAT THIS IS, AND WHAT IT IS NOT.***  It reads apisrvr (BASIC) and the verb's program as text, with comments removed.  ***IT DOES NOT RUN
ANYTHING, SO IT CANNOT SAY THAT REQUEST 29 REFUSES ANYBODY***: that is sandbox-req29.py (a real TLS and SCRAM API session on a private Solo).  What a
text check is for: the invariants that make request 29 a gate are ORDERING (SDCLIENT and the account rules before the process is marked an SDNet user
and before anything is opened; the account's directory taken from its register record and never from the request), and an edit that moves one still
compiles.

THE SHAPE.  Request 29 (apisrvr's vb.open.sdnet, "account;file") used to be gated by bit 2 of NETFILES alone.  It now also refuses under SDCLIENT (as
request 4 does), requires a register record (a path names none), applies the rule request 3 applies - account.entry.check, ONE internal subroutine
both ask: a suspended account is refused, and the account must be the one the session holds (Solo has one account; SDSYS is never a target) - and
requires the account's NET gate, register field 15 (ACC$NET, Core's number), off unless the word is yes.  The administrator turns the gate on and
off with SET.NET.ACCESS ON|OFF (setnetacc).  The default is as secure as it was: bit 2 is 0, the gate is off.

***AND THE CHECKS ARE THEMSELVES CHECKED.***  --selftest breaks each invariant in the way an edit plausibly would and requires some check to notice.  A
mutant that nothing catches is reported as a FAILURE of the self-test.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.abspath(os.path.join(HERE, os.pardir))
SDSYS = os.path.join(SD64, "sdsys")
GPL = os.path.join(SDSYS, "gpl.bp")

FILES = {
    "apisrvr": os.path.join(GPL, "apisrvr"),
    "setnetacc": os.path.join(GPL, "setnetacc"),
    "syscom/keys.h": os.path.join(SDSYS, "syscom", "keys.h"),
    "newvoc/set.net.access": os.path.join(SDSYS, "newvoc", "set.net.access"),
    "voc_template/set.net.access": os.path.join(SDSYS, "voc_template", "set.net.access"),
}
RAW_FILES = ("newvoc/set.net.access", "voc_template/set.net.access")          # a VOC record: no comments to strip


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


def code(name, src):
    return src if name in RAW_FILES else strip_bas(src)


def at(text, needle, start=0):
    return text.find(needle, start)


def label_block(text, label, length=6000):
    """The text of a BASIC internal subroutine from its label to the next label at the start of a line (or LENGTH characters), '' when absent."""
    m = re.search(r"(?m)^%s:\s*$" % re.escape(label), text)
    if not m:
        return ""
    nxt = re.search(r"(?m)^[a-zA-Z][a-zA-Z0-9._$]*:\s*$", text[m.end():])
    end = m.end() + (nxt.start() if nxt else length)
    return text[m.start():end]


def checks(srcs, messages_dir):
    """[(id, ok, detail)] - every invariant the gate and the rule rest on."""
    rows = []

    def ck(i, ok, detail=""):
        rows.append((i, bool(ok), detail))

    c = {name: code(name, text) for name, text in srcs.items()}
    api = c["apisrvr"]

    # ---- K. the register field --------------------------------------------------------------------------------------
    ck("K1 ACC$NET is field 15 of the register (Core's number)", re.search(r"\$define ACC\$NET\s+15\b", srcs["syscom/keys.h"]), "absent or another number")

    # ---- R. request 29 --------------------------------------------------------------------------------------------------
    aec = label_block(api, "account.entry.check")
    snc = label_block(api, "sdnet.account.check")
    ck("R1 apisrvr has the internal subroutines account.entry.check and sdnet.account.check", aec != "" and snc != "")
    ck("R2 account.entry.check refuses a suspended account with 10003 and audits it in lower case: 'account refused branch=2 suspended account='",
       "kernel(K$AUDIT, 'account refused branch=2 suspended account=' : ent.name)" in aec and "sysmsg(10003)" in aec and "ent.suspended" in aec)
    ck("R3 account.entry.check refuses an account that is not the session's own (SDSYS never) with 10003 and audits it: 'account refused branch=4 not.own.account user='",
       "downcase(kernel(K$USERNAME, 0))" in aec and "# 'sdsys'" in aec and "'account refused branch=4 not.own.account user='" in aec)
    ck("R4 request 3 (vb.account) asks account.entry.check, and its two tests are not written out again there (the audit text is in one place only)",
       api.count("gosub account.entry.check") == 2 and api.count("account refused branch=2 suspended") == 1
       and api.count("account refused branch=4 not.own.account") == 1)
    ck("R5 sdnet.account.check asks account.entry.check too (request 29 applies the rule request 3 applies)", "gosub account.entry.check" in snc)
    i_who = at(snc, "net.who = downcase(kernel(K$USERNAME, 0))")
    i_guard = at(snc, "index(net.acct, @ds, 1) = 0")
    i_reg = at(snc, "openpath @sdsys:@ds:'accounts'")
    i_entry = at(snc, "gosub account.entry.check")
    i_gate = at(snc, "net.rec<ACC$NET>")
    i_path = at(snc, "net.acc.path = parse.pathname.tokens(net.rec<ACC$PATH>)")
    ck("R6 sdnet.account.check: a name with a path separator is not looked up (the guard comes first), the register is read, the account rule is asked, then the NET gate, "
       "then the directory is taken from the record - in that order",
       min(i_who, i_guard, i_reg, i_entry, i_gate, i_path) >= 0 and i_guard < i_reg < i_entry < i_gate < i_path,
       "offsets guard %s reg %s entry %s gate %s path %s" % (i_guard, i_reg, i_entry, i_gate, i_path))
    ck("R7 the NET gate is on only when the word is yes: blank, 'no' and a record with no such field are off (the test is = 'YES', never # 'NO')",
       re.search(r"if not\(upcase\(trim\(net\.rec<ACC\$NET>\)\) = 'YES'\) then", snc) is not None)
    ck("R8 a missing register record and a gate that is off are refused with ER$XREMOTE and SV$ELSE and audited in lower case, with the user and the account: "
       "'api refused request=29 reason=no register record user=' and 'reason=net gate off user='",
       "kernel(K$AUDIT, 'api refused request=29 reason=no register record user=' : net.who : ' account=' : net.acct)" in snc
       and "kernel(K$AUDIT, 'api refused request=29 reason=net gate off user=' : net.who : ' account=' : net.acct)" in snc
       and snc.count("set.status ER$XREMOTE") == 2 and snc.count("server.error = SV$ELSE") == 2)
    # the request spans two labels (vb.open.sdnet: and vb.open.sdnet.continue:) and ends where the next request's label (indented in the file) begins
    r0 = api.find("\nvb.open.sdnet:")
    r1 = api.find("vb.lock.record:", r0) if r0 >= 0 else -1
    rq = api[r0:r1] if r0 >= 0 and r1 > r0 else ""
    ck("R0 the text of request 29 (vb.open.sdnet to vb.lock.record) was found and is not empty (the checks below read it)", len(rq) > 1500, "length %d" % len(rq))
    j_bit = at(rq, "bitand(config('NETFILES'), 2)")
    j_cli = at(rq, "config('SDCLIENT') # 0")
    j_msg = at(rq, "sysmsg(5262)")
    j_acct = at(rq, "net.acct = field(cmnd, ';', 1)")
    j_chk = at(rq, "gosub sdnet.account.check")
    j_ret = at(rq, "if net.refused then return")
    j_mark = at(rq, "kernel(K$SDNET, 1)")
    j_open = at(rq, "acc = net.acc.path")
    ck("R9 vb.open.sdnet: the NETFILES bit, then SDCLIENT (the 5262 text), the account named, sdnet.account.check, its refusal returns, THEN the process is marked an SDNet user, "
       "THEN the account's directory is the one from the record - in that order",
       min(j_bit, j_cli, j_msg, j_acct, j_chk, j_ret, j_mark, j_open) >= 0 and j_bit < j_cli < j_msg < j_acct < j_chk < j_ret < j_mark < j_open,
       "offsets bit %s sdclient %s 5262 %s acct %s check %s return %s mark %s open %s" % (j_bit, j_cli, j_msg, j_acct, j_chk, j_ret, j_mark, j_open))
    ck("R10 the request no longer takes the account's directory from the request itself (no 'acc = field(cmnd' and no read of the register inside vb.open.sdnet)",
       "acc = field(cmnd" not in rq and "read acc.rec from acc.f" not in rq)

    # ---- V. the verb ------------------------------------------------------------------------------------------------------
    v = c["setnetacc"]
    i_admin = at(v, "kernel(K$ADMINISTRATOR, -1)")
    i_open = at(v, "openpath @sdsys:@ds:'accounts'")
    i_readu = at(v, "readu acc.rec from acc.f, acc.name")
    i_write = at(v, "write acc.new to acc.f, acc.name")
    ck("V1 SET.NET.ACCESS is $internal, catalogued as $SETNETACC, and refuses a session that is not the administrator (2001) BEFORE it opens the register",
       "$internal" in v and "$catalog $SETNETACC" in v and i_admin >= 0 and i_open >= 0 and i_admin < i_open and "stop sysmsg(2001)" in v)
    ck("V2 it reads the register under a lock (readu), writes the record back and releases the lock; a failed write says 10114 and the state is unchanged",
       min(i_readu, i_write) >= 0 and i_readu < i_write and "release acc.f, acc.name" in v and v.count("sysmsg(10114, acc.name)") >= 3)
    ck("V3 the only words it writes into ACC$NET are 'yes' and 'no'", "acc.new<ACC$NET> = 'yes'" in v and "acc.new<ACC$NET> = 'no'" in v
       and len(re.findall(r"acc\.new<[^>]+> = ", v)) == 2)
    ck("V4 one action per command: a second word, a word that is not on or off, and a bare word each give the syntax message 11927 and change nothing",
       "word.2 # ''" in v and "case upcase(word.1) = 'ON'" in v and "case upcase(word.1) = 'OFF'" in v and "sysmsg(11927)" in v)
    ck("V5 with no argument it shows the state and changes nothing (11928); after a change it says where the gate now stands; an unchanged state says 10080",
       v.count("sysmsg(11928, acc.name, ") == 2 and "sysmsg(10080, acc.name)" in v)
    ck("V6 the change is written to the audit trail in lower case: 'set.net.access ' with the word and 'account='",
       "kernel(K$AUDIT, 'set.net.access ' : downcase(word.1) : ' account=' : acc.name)" in v)
    for n in ("newvoc/set.net.access", "voc_template/set.net.access"):
        ck("V7 %s is a verb that runs $setnetacc (V, CA, $setnetacc)" % n, c[n].replace("\r", "").strip().split("\n") == ["V", "CA", "$setnetacc"], repr(c[n][:40]))

    # ---- M. the messages ------------------------------------------------------------------------------------------------
    for num, text in (("11927", "Syntax: set.net.access"), ("11928", "Account %1 has NET %2"), ("10080", "%1 already had that access"),
                      ("10114", "Unable to change the state of %1")):
        try:
            with open(os.path.join(messages_dir, num), encoding="latin-1") as f:
                body = f.read()
        except OSError as exc:
            ck("M1 message %s exists" % num, False, str(exc))
            continue
        ck("M1 message %s exists and starts as the code expects" % num, body.startswith(text), repr(body[:80]))
    return rows


# --------------------------------------------------------------- self-test
def sub(name, old, new):
    def f(srcs):
        s = dict(srcs)
        if old not in s[name]:
            raise KeyError("%s: %r is not in the file, so the mutant cannot be made" % (name, old[:50]))
        s[name] = s[name].replace(old, new, 1)
        return s
    return f


def sub_all(name, old, new):
    def f(srcs):
        s = dict(srcs)
        if old not in s[name]:
            raise KeyError("%s: %r is not in the file, so the mutant cannot be made" % (name, old[:50]))
        s[name] = s[name].replace(old, new)
        return s
    return f


MUTANTS = [
    ("the NET gate is taken as on unless the word is no (blank means ON)", "R7",
     sub("apisrvr", "if not(upcase(trim(net.rec<ACC$NET>)) = 'YES') then", "if upcase(trim(net.rec<ACC$NET>)) = 'NO' then")),
    ("SDCLIENT is not asked", "R9", sub("apisrvr", "if config('SDCLIENT') # 0 then", "if 0 then")),
    ("SDCLIENT is asked after the process is marked an SDNet user", "R9",
     sub("apisrvr", "net.acct = field(cmnd, ';', 1)\n                        gosub sdnet.account.check\n                        if net.refused then return",
         "i = kernel(K$SDNET, 1)\n                        net.acct = field(cmnd, ';', 1)\n                        gosub sdnet.account.check\n                        if net.refused then return")),
    ("request 29 does not ask sdnet.account.check", "R9", sub("apisrvr", "gosub sdnet.account.check", "net.refused = @false")),
    ("the directory comes from the request, not the register record", "R10", sub("apisrvr", "acc = net.acc.path", "acc = field(cmnd, ';', 1)")),
    ("a path is looked up as an account name (the guard is gone)", "R6", sub("apisrvr", "net.acct # '' and index(net.acct, @ds, 1) = 0", "net.acct # ''")),
    ("the NET gate is asked before the account rule", "R6", sub("apisrvr", "gosub account.entry.check\nif ent.refused then return", "if ent.refused then return")),
    ("request 3 has its own copy of the rule again", "R4", sub("apisrvr", "gosub account.entry.check\nif ent.refused then goto revert.to.old.account",
                                                             "gosub account.entry.check\nif ent.refused then goto revert.to.old.account\nvoid kernel(K$AUDIT, 'account refused branch=2 suspended account=')")),
    ("sdnet.account.check does not ask the account rule", "R5", sub("apisrvr", "ent.suspended = (upcase(trim(net.rec<ACC$SUSPENDED>)) = 'SUSPENDED')\ngosub account.entry.check",
                                                                    "ent.suspended = (upcase(trim(net.rec<ACC$SUSPENDED>)) = 'SUSPENDED')\nent.refused = @false")),
    ("SDSYS is a target", "R3", sub("apisrvr", "(downcase(ent.name) # 'sdsys') and ", "")),
    ("a refusal's audit line is in capitals", "R8", sub("apisrvr", "'api refused request=29 reason=net gate off user='", "'API REFUSED REQUEST=29 REASON=NET GATE OFF USER='")),
    ("ACC$NET is another field", "K1", sub("syscom/keys.h", "$define ACC$NET", "$define ACC$NET.X")),
    ("the verb is open to everyone", "V1", sub("setnetacc", "if not(kernel(K$ADMINISTRATOR, -1)) then", "if 0 then")),
    ("the verb writes without a lock", "V2", sub("setnetacc", "readu acc.rec from acc.f, acc.name", "read acc.rec from acc.f, acc.name")),
    ("the verb writes 'on' for an on request", "V3", sub("setnetacc", "acc.new<ACC$NET> = 'yes'", "acc.new<ACC$NET> = 'on'")),
    ("the verb takes two words", "V4", sub("setnetacc", "word.2 # ''", "0")),
    ("the audit line is written in capitals", "V6", sub("setnetacc", "'set.net.access ' : downcase(", "'SET.NET.ACCESS ' : downcase(")),
    ("the VOC record runs another program", "V7", sub("newvoc/set.net.access", "$setnetacc", "$setosacc")),
]


def run_selftest(srcs, messages_dir):
    ok_all = True
    base = checks(srcs, messages_dir)
    base_fail = {r[0] for r in base if not r[1]}
    print("selftest: the unchanged tree fails %d check(s): %s" % (len(base_fail), ", ".join(sorted(base_fail)[:6]) or "none"))
    if base_fail:
        print("selftest: the gate is not whole, so a mutant's own failure cannot be told from the tree's; run the plain check first")
        return False
    for name, want, mut in MUTANTS:
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
    srcs = {}
    missing = []
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
    print("test-netgate-units: tree %s" % SD64)
    if "apisrvr" in missing:
        print("test-netgate-units: CANNOT RUN - gpl.bp/apisrvr is not there")
        return 2
    if missing:
        print("test-netgate-units: not there yet (their checks fail): %s" % ", ".join(missing))
    messages_dir = os.path.join(SDSYS, "messages")
    rows = checks(srcs, messages_dir)
    failed = 0
    for i, ok, detail in rows:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", i, "" if ok or not detail else "   <- " + str(detail)[:200]))
        failed += 0 if ok else 1
    print("\ntest-netgate-units: %d passed, %d failed" % (len(rows) - failed, failed))
    ok = failed == 0
    if "--selftest" in argv:
        ok = run_selftest(srcs, messages_dir) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
