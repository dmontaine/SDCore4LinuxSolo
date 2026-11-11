#!/usr/bin/env python3
#
# sandbox-netindex-solo.py - what a REAL Solo server answers to the index QUERY requests: 35 and 36 (INDICES), 26 and 39 (SELECTINDEX of a value), 38 (SELECTINDEX, the indexed values), 42 to 45
#                            (SETLEFT, SETRIGHT, SELECTLEFT, SELECTRIGHT), asked by an ACCOUNT-PASSWORD session.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-netindex-solo.py <dir> [--build]
#
# START-HISTORY:
# 11 Nov 26 dm  Written for the Solo carry of SD Core's S.73 item 3 D1 (7fd83ad3): SD Core's sandbox-netindex.py on Solo's server.  The client side of D1 (the $netfile handler's NF$INDEXQ and the
#               kernel's net_index_query) is built from what a server REALLY answers; this measures the answers of Solo's apisrvr, which a SD Core client (or a Solo one) gets from a Solo server.
#               SD Core's session is a files-only login with no group (its test device); Solo has no files-only route, and the D1 rule "no new gate" maps to: an ACCOUNT-PASSWORD session (the
#               ordinary Solo login, which is refused the administration set) is served every index query.  Rows S1d and S7 hold the two server fixes D1 carried (vb.selectright's RETURN,
#               check.list in both scans).
# END-HISTORY
#
#   I  INDICES: requests 35 and 36
#   V  the indexed values: request 38
#   K  the ids for a value: requests 39 and 26
#   S  the scan: requests 42 to 45, the end of a scan, the position SELECTINDEX sets, an index that is not there, a list number outside 0 to 10
#   G  no new gate: the session that asked all of it is an account-password one, which the administration set refuses (14964)

import importlib.util
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("fadm", os.path.join(HERE, "sandbox-fileadmin-solo.py"))
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)
rq, af, say = fa.rq, fa.af, fa.say
TOOL = fa.TOOL
FM = "\xfe"

PROG = ("   open 'zzx' to f else crt 'IX nofile' ; stop\n"
        "   open 'DICT', 'zzx' to d else crt 'IX nodict' ; stop\n"
        "   write 'D':@fm:'1':@fm:'':@fm:'City':@fm:'12L':@fm:'M' on d, 'CITY'\n"
        "   write 'D':@fm:'2':@fm:'':@fm:'Amt':@fm:'8R':@fm:'S' on d, 'AMT'\n"
        "   write 'Paris':@fm:100 on f, 'r1'\n   write 'Rome':@fm:20 on f, 'r2'\n   write 'Paris':@fm:3 on f, 'r3'\n"
        "   write 'Oslo':@fm:100 on f, 'r4'\n   write 'Rome':@fm:7 on f, 'r5'\n   write 'Paris':@vm:'Oslo':@fm:50 on f, 'r6'\n"
        "   select f to 6\n   readlist ids from 6 else ids = ''\n   crt 'IX[':dcount(ids, @fm):']'\nend\n")

# What INDICES(f, name) answers for the two indices, as SD Core's server sent it (sandbox-netindex.py): a dictionary item's description with the index's flags
INFO_CITY = "D\xfd\xfd\xfd1\xfd0\xfdL\xfd\xfe1\xfe\xfeCity\xfeL\xfeM"
INFO_AMT = "D\xfd\xfd\xfd1\xfd1\xfdL\xfd\xfe2\xfe\xfeAmt\xfeR\xfeS"


def S(n):
    return struct.pack("<h", n)


def padname(s):
    """A name as request 26 carries it: its length, the name, a null when the length is odd (the other index requests do NOT pad)."""
    return S(len(s)) + s.encode("latin-1") + (b"\0" if len(s) % 2 else b"")


def is_(rr, status, data):
    return rr is not None and rr[0] == 0 and rr[1] == status and rr[2].decode("latin-1") == data


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        fa.bail("usage: sandbox-netindex-solo.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    ACCT = os.path.join(SYS, "user_accounts", fa.ACCOUNT)
    fa.BOX, fa.SYS, fa.ACCT = BOX, SYS, ACCT
    rq.BOX, rq.SYS, rq.ACCT, rq.REG = BOX, SYS, ACCT, os.path.join(SYS, "accounts", fa.ACCOUNT)
    af.BOX, af.SYS, af.SD = BOX, SYS, os.path.join(SYS, "bin", "sd")
    say("sandbox-netindex-solo: sandbox  %s" % BOX)
    if os.geteuid() == 0:
        fa.bail("this is root; Solo never runs as root")
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            fa.bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            fa.bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-netindex-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        fa.bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    af.PW = rq.secret("account.pw")
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    row = fa.row

    try:
        say("\n--- preparation: a hashed file zzx, two dictionary items and six records, then the indices CITY and AMT made and built by an ordinary session of sduser ---")
        fa.ordinary("DELETE.FILE zzx NO.QUERY")
        rq.put(os.path.join(ACCT, "bp", "zzix"), PROG)
        out = fa.ordinary("CREATE.FILE zzx DYNAMIC", "BASIC bp zzix", "RUN bp zzix")
        if fa.tag(out, "IX") != ["6"]:
            fa.bail("the fixture file zzx does not hold its six records: %r" % (out[-6:],))
        out = fa.ordinary("CREATE.INDEX zzx CITY", "CREATE.INDEX zzx AMT", "BUILD.INDEX zzx CITY", "BUILD.INDEX zzx AMT")
        if not any("6 records processed" in x for x in out):
            fa.bail("the indices were not built: %r" % (out[-6:],))

        N = fa.wire("IN")
        fN = N.open4("zzx")[0]
        if fN is None:
            fa.bail("zzx did not open in the account-password session")
        say("  [session] an ACCOUNT-PASSWORD session of sduser, zzx open as file %r" % fN)

        def req(ptype, data, shown):
            return N.req(ptype, data, shown=shown)

        def scan(ptype, name, lst, shown):
            k = req(ptype, S(fN) + S(lst) + name.encode("latin-1"), shown)
            ids = req(14, S(lst), "readlist of list %d" % lst)
            return k, ids

        say("\n--- I. INDICES: requests 35 and 36 ---")
        a = req(35, S(fN), "indices1 (the names)")
        row("I1 request 35 answers the names of the indices, field marks between, STATUS() 0", is_(a, 0, "CITY" + FM + "AMT"), repr(a))
        a, b, c, d = (req(36, S(fN) + n.encode(), "indices2 " + n) for n in ("CITY", "AMT", "NOSUCH", "city"))
        row("I2 request 36 answers the description of CITY and of AMT, byte for byte what SD Core's server answers", is_(a, 0, INFO_CITY) and is_(b, 0, INFO_AMT), repr((a, b)))
        row("I3 ...a name that is not an index is the null string with STATUS() 0, and the case of the name matters (city is not CITY)", is_(c, 0, "") and is_(d, 0, ""), repr((c, d)))

        say("\n--- V. the indexed values: request 38 ---")
        a, b, c = (req(38, S(fN) + n.encode(), "selectindexv " + n) for n in ("CITY", "AMT", "NOSUCH"))
        row("V1 request 38 answers the indexed values in index order: CITY Oslo Paris Rome, AMT 3 7 20 50 100 (numerically, the index is right aligned), STATUS() 0",
            is_(a, 0, FM.join(["Oslo", "Paris", "Rome"])) and is_(b, 0, FM.join(["3", "7", "20", "50", "100"])), repr((a, b)))
        row("V2 ...an index that is not there is the null string with STATUS() 1", is_(c, 1, ""), repr(c))

        say("\n--- K. the ids for a value: requests 39 and 26 ---")
        a = req(39, S(fN) + S(4) + b"CITY" + b"Paris", "selectindexk CITY Paris")
        b = req(39, S(fN) + S(4) + b"CITY" + b"Rome", "selectindexk CITY Rome")
        c = req(39, S(fN) + S(4) + b"CITY" + b"Nowhere", "selectindexk CITY Nowhere")
        d = req(39, S(fN) + S(4) + b"CITY", "selectindexk CITY '' (a null value)")
        e = req(39, S(fN) + S(6) + b"NOSUCH" + b"Paris", "selectindexk NOSUCH Paris")
        f = req(39, S(fN) + S(3) + b"AMT" + b"100", "selectindexk AMT 100 (the name is NOT padded)")
        g = req(39, S(fN) + S(3) + b"AMT" + b"7", "selectindexk AMT 7")
        row("K1 request 39 answers the ids that hold the value, in id order: Paris r1 r3 r6 (r6 holds two cities), Rome r2 r5",
            is_(a, 0, FM.join(["r1", "r3", "r6"])) and is_(b, 0, FM.join(["r2", "r5"])), repr((a, b)))
        row("K2 ...a value nobody holds and a null value are the null string with STATUS() 0; an index that is not there is STATUS() 1",
            is_(c, 0, "") and is_(d, 0, "") and is_(e, 1, ""), repr((c, d, e)))
        row("K3 ...the right aligned index finds 100 (r1 r4) and 7 (r5) by the number as typed", is_(f, 0, FM.join(["r1", "r4"])) and is_(g, 0, "r5"), repr((f, g)))
        a = req(26, S(fN) + S(3) + padname("CITY") + padname("Paris"), "selectindex CITY Paris into list 3 (request 26: the names are padded)")
        n1 = req(12, S(3), "readnext of list 3")
        n2 = req(14, S(3), "readlist of list 3")
        b = req(26, S(fN) + S(3) + padname("NOSUCH") + padname("Paris"), "selectindex NOSUCH Paris into list 3")
        n3 = req(14, S(3), "readlist of list 3 after an unknown index")
        row("K4 request 26 leaves the ids in the server's list: STATUS() 0, readnext gives r1 and readlist the rest (r3 r6)", is_(a, 0, "") and is_(n1, 0, "r1") and is_(n2, 0, FM.join(["r3", "r6"])),
            repr((a, n1, n2)))
        row("K5 ...an index that is not there is STATUS() 1 and an empty list", is_(b, 1, "") and is_(n3, 0, ""), repr((b, n3)))

        say("\n--- S. the scan: requests 42 to 45 ---")
        s0 = req(42, S(fN) + b"CITY", "setleft CITY")
        ks = [scan(45, "CITY", 4, "selectright CITY (call %d, after setleft)" % (i + 1)) for i in range(5)]
        row("S1a setleft is STATUS() 0; each selectright then answers the NEXT key with STATUS() 0 and leaves its ids in the list: Oslo r4 r6, Paris r1 r3 r6, Rome r2 r5",
            is_(s0, 0, "") and is_(ks[0][0], 0, "Oslo") and is_(ks[0][1], 0, FM.join(["r4", "r6"])) and is_(ks[1][0], 0, "Paris") and is_(ks[1][1], 0, FM.join(["r1", "r3", "r6"]))
            and is_(ks[2][0], 0, "Rome") and is_(ks[2][1], 0, FM.join(["r2", "r5"])), repr(ks[:3]))
        row("S1d ...past the last key it answers the null key with STATUS() 1 (before the carry Solo's vb.selectright fell into vb.mark.mapping and answered 0), an empty list, and stays at the end",
            is_(ks[3][0], 1, "") and is_(ks[3][1], 0, "") and is_(ks[4][0], 1, ""), repr(ks[3:]))
        s0 = req(43, S(fN) + b"CITY", "setright CITY")
        ks = [scan(44, "CITY", 4, "selectleft CITY (call %d, after setright)" % (i + 1)) for i in range(4)]
        row("S2 setright, then selectleft answers Rome, Paris, Oslo and then the null key with STATUS() 1",
            is_(s0, 0, "") and is_(ks[0][0], 0, "Rome") and is_(ks[0][1], 0, FM.join(["r2", "r5"])) and is_(ks[1][0], 0, "Paris") and is_(ks[1][1], 0, FM.join(["r1", "r3", "r6"]))
            and is_(ks[2][0], 0, "Oslo") and is_(ks[2][1], 0, FM.join(["r4", "r6"])) and is_(ks[3][0], 1, ""), repr(ks))
        s0 = req(42, S(fN) + b"AMT", "setleft AMT")
        ks = [scan(45, "AMT", 4, "selectright AMT (call %d, after setleft)" % (i + 1)) for i in range(6)]
        row("S3 the right aligned index scans in numeric order: 3 r3, 7 r5, 20 r2, 50 r6, 100 r1 r4, then the end (STATUS() 1)",
            [(k[0][1], k[0][2].decode("latin-1"), k[1][2].decode("latin-1")) for k in ks if k[0] and k[1]] == [(0, "3", "r3"), (0, "7", "r5"), (0, "20", "r2"), (0, "50", "r6"),
                                                                                                             (0, "100", FM.join(["r1", "r4"])), (1, "", "")],
            repr([(k[0][1], k[0][2], k[1][2]) for k in ks if k[0] and k[1]]))
        req(39, S(fN) + S(4) + b"CITY" + b"Paris", "selectindexk CITY Paris (sets the position)")
        k1 = scan(45, "CITY", 4, "selectright CITY (after selectindexk Paris)")
        k2 = scan(45, "CITY", 4, "selectright CITY again")
        row("S4 SELECTINDEX of a value sets the position: the next selectright answers Rome r2 r5, and then the end (STATUS() 1)",
            is_(k1[0], 0, "Rome") and is_(k1[1], 0, FM.join(["r2", "r5"])) and is_(k2[0], 1, ""), repr((k1, k2)))
        req(26, S(fN) + S(3) + padname("CITY") + padname("Paris"), "selectindex CITY Paris into list 3 (request 26 sets the position too)")
        k3 = scan(44, "CITY", 4, "selectleft CITY after request 26")
        row("S5 ...request 26 too: the next selectleft answers Oslo r4 r6", is_(k3[0], 0, "Oslo") and is_(k3[1], 0, FM.join(["r4", "r6"])), repr(k3))
        a = req(44, S(fN) + S(4) + b"NOSUCH", "selectleft NOSUCH")
        b = req(45, S(fN) + S(4) + b"NOSUCH", "selectright NOSUCH")
        c = req(42, S(fN) + b"NOSUCH", "setleft NOSUCH")
        d = req(43, S(fN) + b"NOSUCH", "setright NOSUCH")
        row("S6 an index that is not there is STATUS() 1 and the null string for all four", is_(a, 1, "") and is_(b, 1, "") and is_(c, 1, "") and is_(d, 1, ""), repr((a, b, c, d)))
        bad_l = []
        for lst, ptype, nm in ((99, 44, "selectleft"), (-1, 45, "selectright"), (11, 44, "selectleft")):
            x = req(ptype, S(fN) + S(lst) + b"CITY", "%s CITY into list %d" % (nm, lst))
            bad_l.append((x, fa.errtext(N)))
        alive = req(35, S(fN), "indices1 (the session is still alive)")
        row("S7 a list number outside 0 to 10 (99, -1, 11) is refused by both scans with an ERROR reply and message 5269, and the session goes on (request 35 is answered after them)",
            all(x is not None and x[0] == 3 and t == af.msg(5269) for x, t in bad_l) and is_(alive, 0, "CITY" + FM + "AMT"), repr((bad_l, alive)))

        say("\n--- G. no new gate ---")
        g70 = fa.fileadmin(N, 1, fN)
        rd = req(6, S(fN) + b"r1", "read r1")
        row("G1 CONTROL: the session that asked all of the above is an ACCOUNT-PASSWORD one - request 70 is refused it with 14964 - and it reads r1 (Paris, 100): the index queries needed nothing more",
            fa.refused_with(g70, 14964, 70) and is_(rd, 0, "Paris" + FM + "100"), repr((g70, rd)))
        N.close()
    finally:
        for w in list(af.WIRES):
            w.kill()
        fa.ordinary("DELETE.FILE zzx NO.QUERY")
        for p in (os.path.join(ACCT, "bp", "zzix"), os.path.join(ACCT, "bp.out", "zzix")):
            try:
                os.remove(p)
            except OSError:
                pass
        subprocess.run([os.path.join(SYS, "bin", "sd"), "-cleanup"], env=af.env(), capture_output=True, timeout=60)

    say("\nsandbox-netindex-solo: %d passed, %d failed" % (fa.passed, fa.failed))
    if fa.passed + fa.failed == 0:
        fa.bail("no row ran - a broken test, not a pass")
    return 1 if fa.failed else 0


if __name__ == "__main__":
    sys.exit(main())
