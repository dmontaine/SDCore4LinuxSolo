#!/usr/bin/env python3
"""test-apiaccount-units.py - Solo's API server: request 3 by registered name only, and OPENSEQ by pathname held to the VOC rule.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-apiaccount-units.py
  python3 .../test-apiaccount-units.py --selftest

No sudo, no install, no sd.  Exit 0 all checks passed, 1 a check failed, 2 it could not run.

START-HISTORY:
17 Nov 26 dm  Written for S.62 (the four-version audit, round 1; P-1904 and the CARRY-apisrvr findings P-1274 to P-1278 as Solo
              carried them).  Rows R0-R6 are SD Core's test-apiroute-units.py rows R0-R5 (Solo has no sdapi group, so the rest of
              that file does not apply and the file itself was removed from Solo by LSOLO 6), plus R6 (the user table's account set
              after the directory change).  Rows O0-O3 hold the OPENSEQ-by-pathname branch of request 54's handler: it asks
              K$PATH.OK, then K$EDIT.OS.OK, and a pathname the VOC rule refuses is opened for reading only.
END-HISTORY

***WHAT THIS IS NOT.***  It reads sdsys/gpl.bp/apisrvr as TEXT.  It cannot say the server refuses anybody: that a path given to
request 3 is refused, and that an API client without ADMIN cannot write a VOC record named by its path, are runtime facts for a
real `sd-solo -Q` server (sandbox-req29.py's login(), sandbox-apifile.py).  It holds the ORDER the fix rests on - a later edit
that moves a line still compiles and still reads well in a diff.  --selftest mutates the source the ways the fix could plausibly be
undone and requires each mutation to be caught.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SDSYS = os.path.abspath(os.path.join(HERE, os.pardir, "sdsys"))
APISRVR = os.path.join(SDSYS, "gpl.bp", "apisrvr")

RQ3_FOLD = "new.account = downcase(cmnd)"
RQ3_READ = "read acc.rec from acc.f, downcase(new.account)"
RQ3_REFUSE = "if account.path = '' then"
RQ3_AUDIT = "'account refused branch=1 no.path.in.register account=' : new.account"
RQ3_ENTRY = "gosub account.entry.check"
RQ3_CD = "ospath(account.path, OS$CD)"
RQ3_SETACC = "kernel(K$SET.ACCOUNT, who)"
OS_BRANCH = "if os.id = '' then"
OS_PATHOK = "kernel(K$PATH.OK, os.name)"
OS_EDITOK = "os.edit.ok = kernel(K$EDIT.OS.OK, os.name)"
OS_READONLY = "if not(os.edit.ok) then os.m = 1"


def code_lines(src):
    """(line number, line) for every line that is not a whole-line comment.  Trailing ;* comments are kept: no anchor holds one."""
    return [(i, ln) for i, ln in enumerate(src.splitlines(), 1) if not ln.lstrip().startswith("*")]


def checks(src):
    lines = code_lines(src)
    out = []

    def ck(name, ok, detail):
        out.append((name, bool(ok), detail))

    def find(needle, after=0, cond=lambda ln: True):
        return next((n for n, ln in lines if n > after and needle in ln and cond(ln)), None)

    # ---- request 3 (vb.account), from its label to the private catalogue
    start = find("vb.account:")
    stop = find("K$PRIVATE.CATALOGUE", start) if start is not None else None
    block = [(n, ln) for n, ln in lines if start is not None and stop is not None and start < n < stop]
    ck("R0 the vb.account block is found (its label, and the private catalogue after it)", bool(block),
       f"vb.account {start}, K$PRIVATE.CATALOGUE {stop}, {len(block)} code lines")
    if block:
        def at(needle, cond=lambda ln: True):
            return next((n for n, ln in block if needle in ln and cond(ln)), None)

        fold = at(RQ3_FOLD)
        old_fold = [n for n, ln in block if re.search(r"index\(new\.account,\s*@ds,\s*1\)\s*=\s*0\s+then\s+new\.account\s*=", ln)]
        ck("R1 every name is folded: new.account = downcase(cmnd), and no 'unless it is a path' fold",
           fold is not None and not old_fold, f"fold at {fold}, path-exempt fold at {old_fold}")
        read = at(RQ3_READ)
        clr_path = at("account.path = ''", lambda ln: re.match(r"^\s*account\.path\s*=\s*''", ln) is not None)
        clr_rec = at("acc.rec = ''", lambda ln: re.match(r"^\s*acc\.rec\s*=\s*''", ln) is not None)
        ck("R2 account.path = '' and acc.rec = '' are set BEFORE the register is read",
           None not in (read, clr_path, clr_rec) and clr_path < read and clr_rec < read,
           f"account.path '' {clr_path}, acc.rec '' {clr_rec}, read {read}")
        refuse, entry, cd = at(RQ3_REFUSE), at(RQ3_ENTRY), at(RQ3_CD)
        body = []
        if refuse is not None:
            for n, ln in block:
                if n <= refuse:
                    continue
                if ln.strip() == "end":
                    break
                body.append(ln)
        text = "\n".join(body)
        ck("R3 a name with no register record is refused AFTER the read and BEFORE account.entry.check and OS$CD",
           None not in (refuse, read, entry, cd) and read < refuse < entry and refuse < cd,
           f"read {read}, refusal {refuse}, entry check {entry}, OS$CD {cd}")
        ck("R4 the refusal audits 'account refused branch=1 no.path.in.register', answers 10003 and goes back",
           RQ3_AUDIT in text and "kernel(K$AUDIT" in text and "sysmsg(10003)" in text and "goto revert.to.old.account" in text,
           repr(text[:160]))
        typed = [n for n, ln in block if re.match(r"^\s*account\.path\s*=\s*(new\.account|cmnd)\b", ln)]
        ck("R5 no line gives account.path the typed name (it is set only from a register record)", not typed, f"assignments at {typed}")
        setacc = at(RQ3_SETACC)
        ck("R6 the user table's account is set (K$SET.ACCOUNT) only after the entry check and the directory change",
           None not in (setacc, entry, cd) and entry < setacc and cd < setacc, f"entry {entry}, OS$CD {cd}, K$SET.ACCOUNT {setacc}")

    # ---- OPENSEQ by pathname (the branch with no record id)
    br = find(OS_BRANCH)
    pathok = find(OS_PATHOK, br) if br is not None else None
    editok = find(OS_EDITOK, br) if br is not None else None
    els = find("end else", br, lambda ln: ln.strip() == "end else") if br is not None else None
    ro = find(OS_READONLY, br) if br is not None else None
    ck("O0 the OPENSEQ-by-pathname branch is found (if os.id = '' then ... end else)", None not in (br, els), f"branch {br}, end else {els}")
    ck("O1 the pathname branch asks K$EDIT.OS.OK of the name, inside the branch",
       None not in (br, editok, els) and br < editok < els, f"branch {br}, K$EDIT.OS.OK {editok}, end else {els}")
    ck("O2 K$EDIT.OS.OK is asked after the OS switch (K$PATH.OK), whose refusal returns first",
       None not in (pathok, editok) and pathok < editok, f"K$PATH.OK {pathok}, K$EDIT.OS.OK {editok}")
    no_true = [n for n, ln in lines if br is not None and els is not None and br < n < els and re.match(r"^\s*os\.edit\.ok\s*=\s*@true", ln)]
    ck("O3 nothing in the pathname branch sets os.edit.ok to @true, and a refused name is opened for reading only (os.m = 1) after it",
       not no_true and None not in (ro, els) and ro > els, f"@true at {no_true}, read-only line {ro}")
    return out


MUTANTS = [
    ("a path is not folded again",
     lambda s: s.replace("new.account = downcase(cmnd)\n",
                         "new.account = cmnd\nif index(new.account, @ds, 1) = 0 then new.account = downcase(new.account)\n")),
    ("acc.rec is not cleared before the read",
     lambda s: s.replace("\nacc.rec = ''            ;*", "\n* acc.rec = ''          ;*")),
    ("the typed name goes back into account.path",
     lambda s: s.replace("\naccount.path = ''       ;*", "\naccount.path = new.account       ;*")),
    ("the refusal moves below account.entry.check",
     lambda s: _move_refusal_after_entry(s)),
    ("the refusal writes no audit line",
     lambda s: s.replace("   void kernel(K$AUDIT, " + RQ3_AUDIT + ")", "*  no audit")),
    ("the refusal answers another message",
     lambda s: s.replace("   error.msg = sysmsg(10003) ;* User not allowed in requested account\n   abort.message = error.msg",
                         "   error.msg = sysmsg(5037) ;* Invalid account name\n   abort.message = error.msg")),
    ("K$SET.ACCOUNT is taken out",
     lambda s: s.replace("void " + RQ3_SETACC, "* void " + RQ3_SETACC)),
    ("the pathname branch goes back to os.edit.ok = @true (the audited tree)",
     lambda s: s.replace("   " + OS_EDITOK, "   os.edit.ok = @true")),
    ("K$EDIT.OS.OK is asked before K$PATH.OK",
     lambda s: _swap_pathok(s)),
    ("the read-only line is taken out",
     lambda s: s.replace(OS_READONLY, "* " + OS_READONLY)),
]


def _move_refusal_after_entry(src):
    lines = src.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == RQ3_REFUSE), None)
    if start is None:
        return src
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == "end"), None)
    if end is None:
        return src
    block = lines[start:end + 1]
    rest = lines[:start] + lines[end + 1:]
    at = next((i for i, ln in enumerate(rest) if RQ3_ENTRY in ln and i > start), None)
    if at is None:
        return src
    return "".join(rest[:at + 1] + block + rest[at + 1:])


def _swap_pathok(src):
    """Put the K$EDIT.OS.OK line just after the 'if os.id' line, ahead of the K$PATH.OK test."""
    lines = src.splitlines(keepends=True)
    br = next((i for i, ln in enumerate(lines) if ln.strip() == OS_BRANCH), None)
    ed = next((i for i, ln in enumerate(lines) if br is not None and i > br and OS_EDITOK in ln), None)
    if br is None or ed is None:
        return src
    moved = lines[ed]
    rest = lines[:ed] + lines[ed + 1:]
    return "".join(rest[:br + 1] + [moved] + rest[br + 1:])


def selftest(src):
    print("--- self-test: each mutation must be CAUGHT by at least one check ---")
    bad = [n for n, ok, _ in checks(src) if not ok]
    if bad:
        print("REFUSING - the unmutated source already fails: %s" % ", ".join(bad), file=sys.stderr)
        return 2
    holes = 0
    for name, fn in MUTANTS:
        mutated = fn(src)
        if mutated == src:
            print(f"  [FAIL] {name}: the mutation did not change the file (this test no longer understands the source)")
            holes += 1
            continue
        caught = [n.split()[0] for n, ok, _ in checks(mutated) if not ok]
        if caught:
            print(f"  [pass] {name}: caught by {', '.join(caught)}")
        else:
            print(f"  [FAIL] {name}: NOT CAUGHT by any check")
            holes += 1
    print(f"\n{len(MUTANTS) - holes} of {len(MUTANTS)} mutants caught")
    return 1 if holes else 0


def main(argv):
    if not os.path.isfile(APISRVR):
        print(f"test-apiaccount-units: CANNOT RUN - {APISRVR} is not there", file=sys.stderr)
        return 2
    with open(APISRVR, encoding="latin-1") as f:
        src = f.read()
    print(f"test-apiaccount-units: reading {APISRVR}")
    if "--selftest" in argv:
        return selftest(src)
    res = checks(src)
    for name, ok, detail in res:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   <- {detail}"))
    failed = sum(1 for _, ok, _ in res if not ok)
    print(f"\ntest-apiaccount-units: {len(res) - failed} passed, {failed} failed")
    if not res:
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
