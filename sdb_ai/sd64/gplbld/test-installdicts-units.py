#!/usr/bin/env python3
"""test-installdicts-units.py - WRITE_INSTALL_DICTS runs only for a session holding the administrator flag.

  python3 /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-installdicts-units.py
  python3 .../test-installdicts-units.py --selftest

No sudo, no install, no sd.  Exit 0 all checks passed, 1 a check failed, 2 it could not run.

START-HISTORY:
17 Nov 26 dm  Written for S.62 (P-1959).  LSOLO 6 dropped SD Core's root test from write_install_dicts instead of mapping it, so any
              session could rewrite the system dictionaries from the build data.  The test now is Windows Solo's, SYSTEM(1050) (the
              administrator flag), which CPROC sets for the internal door that solo-stage.sh opens for bootstrap pass 3.  The first form
              of the fix also asked KERNEL(K$INTERNAL, -1); this program is not $internal, the compiler took KERNEL for an array, and
              the sandbox build died at pass 3 ("Expected array variable KERNEL") - row W3 holds that.
END-HISTORY

It reads the program as TEXT.  That the build's pass 3 passes is sandbox-fromtree.py's verdict "[PASS] pass 3 (write_install_dicts)";
that an ordinary session is refused is a run in a sandbox (an ordinary login, RUN gpl.bp write_install_dicts: "Command requires
administrator privileges" and no dictionary changed).  --selftest mutates the program and requires each mutation to be caught.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
PROG = os.path.join(SD64, "sdsys", "gpl.bp", "write_install_dicts")
CPROC = os.path.join(SD64, "sdsys", "gpl.bp", "cproc")

TEST = "IF NOT(SYSTEM(1050)) THEN"
STOP = "STOP 'Command requires administrator privileges'"


def code_lines(src):
    return [(i, ln) for i, ln in enumerate(src.splitlines(), 1) if not ln.lstrip().startswith("*")]


def checks(src, cproc):
    lines = code_lines(src)
    out = []

    def ck(name, ok, detail):
        out.append((name, bool(ok), detail))

    def find(needle, after=0):
        return next((n for n, ln in lines if n > after and needle.upper() in ln.upper()), None)

    test = find(TEST)
    stop = find(STOP, test) if test is not None else None
    first = next((n for n, ln in lines if re.match(r"^\s*(OPENPATH|OPEN|WRITE|SSELECT|SELECT)\b", ln, re.I)), None)
    ck("W1 the program refuses unless SYSTEM(1050) (the administrator flag) is set", test is not None, f"test at {test}")
    ck("W2 the refusal STOPs with 'Command requires administrator privileges' straight after the test",
       None not in (test, stop) and stop == test + 1, f"test {test}, stop {stop}")
    ck("W3 the program is not $internal and asks no KERNEL() (the compiler takes KERNEL for an array there)",
       not any(re.match(r"^\s*\$internal\b", ln, re.I) for _, ln in lines) and not any(re.search(r"\bkernel\s*\(", ln, re.I) for _, ln in lines),
       "")
    ck("W4 the test comes before the first OPENPATH / OPEN / SELECT / WRITE", None not in (test, first) and test < first, f"test {test}, first {first}")
    cl = code_lines(cproc)
    door = next((n for n, ln in cl if "if kernel(K$INTERNAL, -1) then" in ln), None)
    grant = next((n for n, ln in cl if door is not None and n > door and "kernel(K$ADMINISTRATOR, 1)" in ln), None)
    ck("W5 CPROC still gives the internal door (sd-solo -i / -internal, the install's pass 3) the administrator flag",
       None not in (door, grant) and grant <= door + 2, f"internal test {door}, grant {grant}")
    return out


MUTANTS = [
    ("the test is taken out (the LSOLO 6 tree)", lambda s, c: (s.replace(TEST, "IF @FALSE THEN"), c)),
    ("the first form of the fix: KERNEL(K$INTERNAL) asked", lambda s, c: (s.replace(TEST, "IF NOT(KERNEL(K$INTERNAL, -1)) AND NOT(SYSTEM(1050)) THEN"), c)),
    ("the refusal does not stop", lambda s, c: (s.replace(STOP, "CRT 'Command requires administrator privileges'"), c)),
    ("the test asks root (SD Core's SYSTEM(27))", lambda s, c: (s.replace(TEST, "IF SYSTEM(27) # 0 THEN"), c)),
    ("CPROC no longer flags the internal door", lambda s, c: (s, c.replace("void kernel(K$ADMINISTRATOR, 1)   ;* bootstrap", "* void kernel(K$ADMINISTRATOR, 1)   ;* bootstrap"))),
]


def read(p):
    with open(p, encoding="latin-1") as f:
        return f.read()


def main(argv):
    for p in (PROG, CPROC):
        if not os.path.isfile(p):
            print(f"test-installdicts-units: CANNOT RUN - {p} is not there", file=sys.stderr)
            return 2
    src, cproc = read(PROG), read(CPROC)
    print(f"test-installdicts-units: reading {PROG} and {CPROC}")
    if "--selftest" in argv:
        bad = [n for n, ok, _ in checks(src, cproc) if not ok]
        if bad:
            print("REFUSING - the unmutated source already fails: %s" % ", ".join(bad), file=sys.stderr)
            return 2
        holes = 0
        for name, fn in MUTANTS:
            s2, c2 = fn(src, cproc)
            if (s2, c2) == (src, cproc):
                print(f"  [FAIL] {name}: the mutation did not change the file")
                holes += 1
                continue
            caught = [n.split()[0] for n, ok, _ in checks(s2, c2) if not ok]
            print(f"  [{'pass' if caught else 'FAIL'}] {name}: " + (f"caught by {', '.join(caught)}" if caught else "NOT CAUGHT"))
            holes += 0 if caught else 1
        print(f"\n{len(MUTANTS) - holes} of {len(MUTANTS)} mutants caught")
        return 1 if holes else 0
    res = checks(src, cproc)
    for name, ok, detail in res:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"   <- {detail}"))
    failed = sum(1 for _, ok, _ in res if not ok)
    print(f"\ntest-installdicts-units: {len(res) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
