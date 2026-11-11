#!/usr/bin/env python3
#
# sandbox-fileadmin-solo.py - API requests 70 (fileadmin: a verb run on the server for the session), 71 (fcontrol), 68 and 69 (write ... creating.seqkey) against a REAL Solo server,
#                             and SOLO'S GATE for them: a session signed in with the GLOBAL password, nothing else.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-fileadmin-solo.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py (Solo's own).  With --build it is built first from THIS tree (it must be empty or absent).  Exit 0 every row passed, 1 a row failed,
# 2 it could not run.
#
# START-HISTORY:
# 11 Nov 26 dm  Written for the Solo carry of SD Core's S.73 item 3 (ef9d5946), on the owner's decision of 11 Nov 26 ("the whole purpose of the global admin password is that a server can
#               administer solo").  SD Core's sandbox-fileadmin.py, adapted: SD Core's gate is the Linux group sdfilesadmin of a files-only login, put in front of its apisrvr by a TEST DEVICE;
#               Solo's gate is the global password, which a sandbox CAN have for real, so there is no device: the global password is set in the sandbox with the installer's own command
#               (`sd -internal RUN gpl.bp solo_password GLOBAL`, as solo-stage.sh does it), the sessions sign in over TLS with SCRAM exactly as Solo's clients do (sandbox-apifile.py's Wire), and
#               the $cred directory is put back byte for byte at the end, so the sandbox is standalone again for the suites after this one.  The evidence is the DISK as an ordinary session
#               of sduser reads it (ANALYZE.FILE, LIST.INDEX, COUNT, a program's CREATING.SEQKEY), never what the server said about itself.  SD Core's section E (the S.64 dict.edit gate by
#               path) has no Solo counterpart: Solo has no edit gates.
# END-HISTORY
#
#   Z  NO global password (the delivered state): an account-password session asks 70, 71, 68, 69 and is refused each with 14964, audited, the disk unchanged; its reads and writes are served
#   P  the global password is set, the way the installer sets it; it shares the account's salt
#   G  with a global password: an account-password session is STILL refused; a global-password session signs on (audited via=global) and is served
#   V  the verbs of request 70 on a hashed file, run by the global session, each read back from the disk by an ordinary session
#   Q  request 71 (the FC$ keys) and requests 68 and 69 (the id the server's counter gives), by the global session
#   R  what is refused before anything runs, even for the global session: a word the grammar does not take, an operation that is not one, a file number that is not open
#   U  the audit trail gained exactly the lines of the run
#   N  the global password taken away again ($cred put back): a new account-password session is refused as in Z

import importlib.util
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
_spec = importlib.util.spec_from_file_location("req29", os.path.join(HERE, "sandbox-req29.py"))
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)
af = rq.af
say = af.say
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ACCOUNT = "sduser"
BOX = SYS = ACCT = CRED = ""
GPW = None
passed = failed = 0
FAILED_IDS = []

PROGS = {
    # the fixture: a hashed file zzh with one dictionary item CITY (field 1) and three records, read back by the program itself
    "zzfx": ("   open 'zzh' to f else crt 'FX nofile' ; stop\n"
             "   open 'DICT', 'zzh' to d else crt 'FX nodict' ; stop\n"
             "   write 'D':@fm:'1':@fm:'':@fm:'City':@fm:'12L':@fm:'S' on d, 'CITY'\n"
             "   write 'Paris' on f, 'r1'\n   write 'Rome' on f, 'r2'\n   write 'Paris' on f, 'r3'\n"
             "   select f to 6\n   readlist ids from 6 else ids = ''\n   crt 'FX[':dcount(ids, @fm):']'\nend\n"),
    # the next id the counter of zzh gives, TAKEN by an ordinary session: it writes a probe record under CREATING.SEQKEY, says the id, and deletes the probe
    "zzfs": ("   open 'zzh' to f else crt 'FS nofile' ; stop\n"
             "   id = ''\n   write 'probe' to f creating.seqkey id\n   crt 'FS[':id:']'\n   delete f, id\nend\n"),
}


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say("  [PASS] " + name)
    else:
        failed += 1
        FAILED_IDS.append(name.split()[0])
        say("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def bail(msg):
    say("sandbox-fileadmin-solo: CANNOT RUN - " + msg)
    for w in list(af.WIRES):
        w.kill()
    sys.exit(2)


def wire(tag_, global_pw=False):
    """A logged-in session of sduser: with the account password, or with the global password (af.Wire signs on with af.PW)."""
    keep = af.PW
    af.PW = GPW if global_pw else rq.secret("account.pw")
    try:
        say("    > wire %s signs on with the %s password" % (tag_, "GLOBAL" if global_pw else "account"))
        return af.Wire(tag_)
    finally:
        af.PW = keep


def text(rr):
    return rr[2].decode("latin-1") if rr is not None else None


def refused_with(rr, number, request):
    want = af.msg(number).replace("%1", str(request))
    return rr is not None and rr[0] == 1 and text(rr) == want


def errtext(w):
    rr = w.req(2, shown="get extended error text")
    return text(rr)


def fileadmin(w, op, fno, words="", secs=None):
    return w.req(70, struct.pack("<hh", op, fno) + words.encode("latin-1"), shown="fileadmin op %d fno %r words %r" % (op, fno, words[:60]))


def fcontrol(w, fno, key, value=""):
    return w.req(71, struct.pack("<hh", fno, key) + value.encode("latin-1"), shown="fcontrol fno %r key %d value %r" % (fno, key, value[:40]))


def seqkey(w, fno, rec, keep=False):
    return w.req(69 if keep else 68, struct.pack("<h", fno) + rec.encode("latin-1"), shown="writeseqkey fno %r record %r keep %s" % (fno, rec[:30], keep))


def reclocked(w, fno, rid):
    """Request 34: the signed code -3 to 3 (2: this session holds the update lock), or None."""
    rr = w.req(34, struct.pack("<h", fno) + rid, shown="recordlocked fno %r id %r" % (fno, rid))
    if rr is None or rr[0] != 0 or len(rr[2]) < 4:
        return None
    return struct.unpack("<i", rr[2][:4])[0]


def read6(w, fno, rid):
    return w.req(6, struct.pack("<h", fno) + rid, shown="read (request 6) fno %r id %r" % (fno, rid))


def ordinary(*cmds):
    return rq.plain(list(cmds))


def analyse_field(lines, label):
    for ln in lines:
        m = re.match(r"^\s*(?:\d\d)?\s*" + re.escape(label) + r"\s*:\s*(.*)$", ln)
        if m:
            return m.group(1).strip()
    return None


def count_records(f="zzh"):
    """The number COUNT gives, or None when the file is not there."""
    for ln in ordinary("COUNT " + f):
        m = re.search(r"(\d+) record\(s\) counted", ln)
        if m:
            return int(m.group(1))
    return None


def index_line(lines, name="CITY"):
    for ln in lines:
        m = re.match(r"^%s\s+([YN])\s+(\S+)" % re.escape(name), ln, re.I)
        if m:
            return m.group(1), m.group(2)
    return None


def tag(lines, t):
    return [m.group(1) for ln in lines for m in [re.match(r"^%s\[(.*)\]$" % t, ln)] if m]


def snapshot_cred():
    snap = {}
    for fn in os.listdir(CRED):
        with open(os.path.join(CRED, fn), "rb") as f:
            snap[fn] = f.read()
    return snap


def restore_cred(snap):
    for fn in os.listdir(CRED):
        if fn not in snap:
            os.remove(os.path.join(CRED, fn))
    for fn, data in snap.items():
        with open(os.path.join(CRED, fn), "wb") as f:
            f.write(data)


def set_global():
    """The global password, set with the installer's own command (solo-stage.sh): the one-shot $internal marker, then `sd-solo -internal RUN gpl.bp solo_password GLOBAL`, the password on a
    pipe.  The password is never printed and never on a command line.  Returns the session's lines."""
    marker = os.path.join(SYS, "$internal")
    with open(marker, "w") as f:
        f.write("sandbox-fileadmin-solo pid=%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%S")))
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    body = "\nTERM 200,9999\nRUN gpl.bp solo_password GLOBAL\n" + GPW + "\nOFF\n"
    say("    > [internal] RUN gpl.bp solo_password GLOBAL   (the password, %d characters, on the pipe)" % len(GPW))
    p = subprocess.run([os.path.join(SYS, "bin", "sd-solo"), "-internal"], input=body, cwd=SYS, env=env, capture_output=True, text=True, errors="replace", timeout=300)
    if os.path.exists(marker):
        os.remove(marker)
    out = ANSI.sub("", p.stdout + p.stderr).replace(GPW, "<global password>")
    return [ln.rstrip() for ln in out.splitlines() if ln.strip()]


def main():
    global BOX, SYS, ACCT, CRED, GPW
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-fileadmin-solo.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    ACCT = os.path.join(SYS, "user_accounts", ACCOUNT)
    CRED = os.path.join(SYS, "$cred")
    rq.BOX, rq.SYS, rq.ACCT, rq.REG = BOX, SYS, ACCT, os.path.join(SYS, "accounts", ACCOUNT)
    af.BOX, af.SYS, af.SD = BOX, SYS, os.path.join(SYS, "bin", "sd")
    say("sandbox-fileadmin-solo: sandbox  %s" % BOX)
    say("sandbox-fileadmin-solo: tree     %s" % os.path.dirname(HERE))
    if os.geteuid() == 0:
        bail("this is root; Solo never runs as root")
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-fileadmin-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    af.PW = rq.secret("account.pw")
    GPW = "Gz9-" + secrets.token_hex(8) + "-Qx"
    rq.SECRETS.append(GPW)
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isdir(CRED):
        bail("%s is not there: the sandbox has no credential register" % CRED)
    snap = snapshot_cred()
    me = os.environ.get("USER", "?")

    try:
        # ---- preparation ------------------------------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- preparation: a hashed file zzh (dictionary item CITY, three records), read back by ordinary sessions of sduser ---")
        row("S0 NULL CASE: the sandbox has NO global password ($cred holds %s, no $global): the delivered state, standalone" % sorted(snap), "$global" not in snap, repr(sorted(snap)))
        if "$global" in snap:
            bail("this sandbox already has a global password, so section Z would not measure the delivered state")
        ordinary("DELETE.FILE zzh NO.QUERY", "DELETE.FILE zznew NO.QUERY", "DELETE.FILE zzdirx NO.QUERY")
        for name, body in PROGS.items():
            rq.put(os.path.join(ACCT, "bp", name), body)
        out = ordinary("CREATE.FILE zzh DYNAMIC", "BASIC bp zzfx", "BASIC bp zzfs", "RUN bp zzfx")
        if tag(out, "FX") != ["3"]:
            bail("the fixture file zzh does not hold its three records: %r" % (out[-8:],))
        base = ordinary("ANALYZE.FILE zzh")
        minmod0 = analyse_field(base, "Minimum modulus")
        if minmod0 is None:
            bail("an ordinary session's ANALYZE.FILE zzh shows no minimum modulus, so no row below could be read from the disk:\n" + "\n".join(base[-14:]))
        say("  [done] zzh holds three records; an ordinary session reads its minimum modulus as %r" % minmod0)
        off0 = rq.audit_off()
        row("S1 the audit file can be read (a row that needs a line from it fails, it does not pass for want of one)", off0 is not None, repr(off0))

        # ---- Z. no global password --------------------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- Z. NO global password: an account-password session asks for the administration set -------------------------------------------------")
        U = wire("U")
        fU = U.open4("zzh")[0]
        if fU is None:
            bail("zzh did not open in the account-password session")
        z70 = fileadmin(U, 2, fU, "MINIMUM.MODULUS 7")
        z70c = fileadmin(U, 8, 0, "zznew")
        z71 = fcontrol(U, fU, 2, "100")
        z68 = seqkey(U, fU, "x")
        z69 = seqkey(U, fU, "y", keep=True)
        row("Z1 request 70 (configure.file) is refused - ON ERROR with message 14964 for request 70 (%r)" % af.msg(14964).replace("%1", "70"), refused_with(z70, 14964, 70), repr(z70))
        row("Z2 ...request 70 (create.file zznew) the same, and an ordinary session finds no zznew", refused_with(z70c, 14964, 70) and count_records("zznew") is None, repr(z70c))
        row("Z3 ...request 71 (fcontrol) the same (14964 for request 71)", refused_with(z71, 14964, 71), repr(z71))
        row("Z4 ...requests 68 and 69 (write ... creating.seqkey) the same (14964 for 68 and 69), and zzh still holds exactly its three records",
            refused_with(z68, 14964, 68) and refused_with(z69, 14964, 69) and count_records("zzh") == 3, repr((z68, z69)))
        row("Z5 ...and the disk is as it was: the minimum modulus an ordinary session reads is still %r" % minmod0, analyse_field(ordinary("ANALYZE.FILE zzh"), "Minimum modulus") == minmod0)
        zr = read6(U, fU, b"r1")
        zw = U.req(16, struct.pack("<hh", fU, 2) + b"r9" + b"Lima", shown="write (request 16) r9 Lima")
        zd = U.req(18, struct.pack("<h", fU) + b"r9", shown="delete (request 18) r9")
        row("Z6 CONTROL: the same session keeps what an account-password session has: READ r1 gives Paris, WRITE r9 and DELETE r9 are served (OK)",
            zr is not None and zr[0] == 0 and text(zr) == "Paris" and zw is not None and zw[0] == 0 and zd is not None and zd[0] == 0, repr((zr, zw, zd)))
        new = rq.audit_new(off0)
        got = re.findall(r"^.*api refused request=(\d+) global=off user=(\S+)$", new or "", re.M)
        row("Z7 the audit trail gained exactly one 'api refused request=N global=off user=sduser' line for each refusal, in order: 70 70 71 68 69",
            got == [(n, "sduser") for n in ("70", "70", "71", "68", "69")], repr(got))

        # ---- P. the global password -------------------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- P. the global password is set, with the installer's own command ---------------------------------------------------------------------------")
        out = set_global()
        say("      " + "\n      ".join(out[-4:]))
        salt_ok = False
        try:
            with open(os.path.join(CRED, "sduser"), encoding="latin-1") as f:
                s_acc = f.read().split("\n")[2]
            with open(os.path.join(CRED, "$global"), encoding="latin-1") as f:
                s_glb = f.read().split("\n")[2]
            salt_ok = s_acc != "" and s_acc == s_glb
        except (OSError, IndexError):
            pass
        row("P1 solo_password GLOBAL said SOLO PASSWORD SET GLOBAL, $cred/$global exists and shares the account's salt (line 3)", "SOLO PASSWORD SET GLOBAL" in out and salt_ok, repr(out[-3:]))
        if not ("SOLO PASSWORD SET GLOBAL" in out and salt_ok):
            bail("the global password could not be set, so no row below measures a global session")

        # ---- G. the gate with a global password ------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- G. with a global password: the account password is still refused, the global password is served -------------------------------------")
        off_g = rq.audit_off()
        U2 = wire("U2")
        fU2 = U2.open4("zzh")[0]
        g1 = fileadmin(U2, 1, fU2)
        g1b = fcontrol(U2, fU2, 6, "abc")
        row("G1 an account-password session made AFTER the global password was set is still refused 70 and 71 (14964): the password it signed on with decides, not the mode of the computer",
            refused_with(g1, 14964, 70) and refused_with(g1b, 14964, 71), repr((g1, g1b)))
        A = wire("A", global_pw=True)
        new = rq.audit_new(off_g)
        row("G2 a session signs on as sduser with the GLOBAL password: the server audits 'api login user=sduser via=global - administrator commands unlocked'",
            rq.audit_has(new, r"api login user=sduser via=global - administrator commands unlocked$"), repr(new))
        fA = A.open4("zzh")[0]
        if fA is None:
            bail("zzh did not open in the global session")
        a1 = fileadmin(A, 1, fA)
        row("G3 the global session asks request 70 operation 1 (analyze.file): served - OK with STATUS() 0, and what the verb printed names the file (the first run answered 'analyse.file is not "
            "in your VOC': SD Core's verb name, removed by S.87)", a1 is not None and a1[0] == 0 and a1[1] == 0 and b"zzh" in a1[2].lower() and b"not in your voc" not in a1[2].lower(), repr(a1))
        say("      [what analyze.file printed on the server]\n        " + "\n        ".join((text(a1) or "").replace("\xfe", "\n").split("\n")[:12]))

        # ---- V. the verbs ---------------------------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- V. the verbs of request 70 on a hashed file, each read back from the disk by an ordinary session -----------------------------------------")
        before = analyse_field(ordinary("ANALYZE.FILE zzh"), "Minimum modulus")
        v2 = fileadmin(A, 2, fA, "MINIMUM.MODULUS 7")
        after = analyse_field(ordinary("ANALYZE.FILE zzh"), "Minimum modulus")
        row("V1 configure.file MINIMUM.MODULUS 7 (operation 2): OK, and an ordinary session reads the minimum modulus as 7 from the disk (it was %r)" % before,
            v2 is not None and v2[0] == 0 and after == "7" and before != "7", repr((v2, before, after)))
        rb = read6(A, fA, b"r1")
        row("V1a the file number still works afterwards: the server opened zzh again under the same number (READ r1 gives Paris)", rb is not None and rb[0] == 0 and text(rb) == "Paris", repr(rb))
        v3 = fileadmin(A, 3, fA, "CITY")
        li = ordinary("LIST.INDEX zzh CITY")
        row("V2 create.index CITY (operation 3): OK, and LIST.INDEX in an ordinary session lists the index, not yet enabled", v3 is not None and v3[0] == 0 and index_line(li) is not None
            and index_line(li)[0] == "N", repr((v3, index_line(li), li[-4:])))
        v3a = fileadmin(A, 4, fA, "CITY")
        li_a = ordinary("LIST.INDEX zzh CITY")
        row("V2a build.index CITY while U and U2 hold zzh open: the verb refuses - reply OK, STATUS() non-zero, 'exclusive access' in its words - and the index is still not enabled",
            v3a is not None and v3a[0] == 0 and v3a[1] != 0 and b"exclusive access" in v3a[2].lower() and index_line(li_a) is not None and index_line(li_a)[0] == "N",
            repr((v3a[:2] if v3a else v3a, index_line(li_a))))
        for w_, f_ in ((U, fU), (U2, fU2)):
            w_.req(5, struct.pack("<h", f_), shown="close fno %r" % f_)
        v4 = fileadmin(A, 4, fA, "CITY")
        li2 = ordinary("LIST.INDEX zzh CITY")
        say("      [LIST.INDEX after the build]\n        " + "\n        ".join(li2[-6:]))
        row("V3 the same request once the others have closed it: OK with STATUS() 0, and the index is ENABLED on the disk", v4 is not None and v4[0] == 0 and v4[1] == 0
            and index_line(li2) is not None and index_line(li2)[0] == "Y", repr((v4[:2] if v4 else v4, index_line(li2))))
        v6 = fileadmin(A, 6, fA, "CITY")
        li3 = ordinary("LIST.INDEX zzh CITY")
        row("V4 disable.index CITY (operation 6): OK, and LIST.INDEX shows the index switched off", v6 is not None and v6[0] == 0 and v6[1] == 0 and index_line(li3) is not None
            and index_line(li3)[0] == "N", repr((v6[:2] if v6 else v6, index_line(li3))))
        v5 = fileadmin(A, 5, fA, "CITY")
        li4 = ordinary("LIST.INDEX zzh CITY")
        row("V5 delete.index CITY (operation 5): OK, and LIST.INDEX has no CITY row any more", v5 is not None and v5[0] == 0 and v5[1] == 0 and index_line(li4) is None, repr((v5[:2] if v5 else v5, li4[-4:])))
        v8 = fileadmin(A, 8, 0, "zznew MINIMUM.MODULUS 3")
        cnt = count_records("zznew")
        op4 = A.open4("zznew")
        row("V6 create.file zznew MINIMUM.MODULUS 3 (operation 8, no file number): OK, an ordinary session counts it (0 records), and the session can OPEN it by name",
            v8 is not None and v8[0] == 0 and cnt == 0 and op4[0] is not None, repr((v8, cnt, op4)))
        if op4[0] is not None:
            # 11 Nov 26 (SD Core's S.169): a delete the VERB refuses.  Z holds zznew open (a session of its own, ENDED afterwards: closing the file number is not enough, the server
            # process keeps the file in its cache and DELETE.FILE still finds it open), so delete.file stops with "Data part ... is open"; the server used to forget the number all the
            # same (the file on the disk, the handle dead) and the verb's return code said 0.
            Z = wire("Z")
            zl = Z.open4("zznew")
            hz = zl[0]
            v9r = fileadmin(A, 9, op4[0]) if hz is not None else None
            row("V7a delete.file (operation 9) on zznew while Z holds it open: the verb refuses - reply OK, STATUS() non-zero, the words 'is open' come back - and the file is still there (an ordinary session counts it)",
                hz is not None and v9r is not None and v9r[0] == 0 and v9r[1] != 0 and b"is open" in v9r[2] and count_records("zznew") == 0, repr((zl, v9r[:3] if v9r else v9r)))
            a9 = fileadmin(A, 1, op4[0])
            row("V7b ...and the number it was opened under still works: analyze.file through it is served and names zznew (it used to be 'Invalid file number')",
                a9 is not None and a9[0] == 0 and b"zznew" in a9[2], repr(a9))
            Z.close()
            time.sleep(1.0)                  # the server process of Z ends when its pipes close
            v9 = fileadmin(A, 9, op4[0])
            op5 = A.open4("zznew")
            row("V7 delete.file (operation 9) on zznew, through the number it was opened under: OK, and the file is gone - the name no longer opens (ELSE), an ordinary session cannot count it",
                v9 is not None and v9[0] == 0 and op5[0] is None and op5[1] is not None and op5[1][0] == 2 and count_records("zznew") is None, repr((v9, op5)))
        else:
            row("V7 delete.file (operation 9)", False, "zznew did not open, so there was nothing to delete")
        row("V8 zzh itself is untouched by all of it: its three records are there", count_records("zzh") == 3, repr(count_records("zzh")))

        # ---- Q. request 71, 68 and 69 -----------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- Q. request 71 (fcontrol) and requests 68 / 69 (the id the file's counter gives), by the global session ------------------------------------")
        q1 = fcontrol(A, fA, 6, "abc")
        row("Q1 fcontrol key 6 (FC$VALID.ID) 'abc': OK with the answer 1", q1 is not None and q1[0] == 0 and text(q1) == "1", repr(q1))
        q2 = fcontrol(A, fA, 2, "100")
        row("Q2 fcontrol key 2 (FC$SET.SEQ.KEY) 100: OK with the answer 1 (it was set; Z3's refused request had not set it)", q2 is not None and q2[0] == 0 and text(q2) == "1", repr(q2))
        q3_ = seqkey(A, fA, "first")
        row("Q3 request 68 'first': OK and the id is the one the counter was set to, 100", q3_ is not None and q3_[0] == 0 and text(q3_) == "100", repr(q3_))
        rd = read6(A, fA, b"100")
        row("Q3a ...and the record is in the file under that id (READ 100 gives 'first')", rd is not None and rd[0] == 0 and text(rd) == "first", repr(rd))
        q4 = seqkey(A, fA, "second", keep=True)
        row("Q4 request 69 (keeping the update lock): the next id, 101", q4 is not None and q4[0] == 0 and text(q4) == "101", repr(q4))
        l101, l100 = reclocked(A, fA, b"101"), reclocked(A, fA, b"100")
        row("Q4a ...and the session holds the update lock on 101 (RECORDLOCKED 2), not on 100 (0: request 68 released it)", l101 == 2 and l100 == 0, repr((l101, l100)))
        A.req(15, struct.pack("<h", fA) + b"101", shown="release (request 15) 101")
        q5 = fcontrol(A, fA, 3)
        row("Q5 fcontrol key 3 (FC$GET.SEQ.KEY): takes the next id - the answer is 102", q5 is not None and q5[0] == 0 and text(q5) == "102", repr(q5))
        ps = ordinary("RUN bp zzfs")
        row("Q6 an ORDINARY session writing a probe under creating.seqkey is given 103: the counter on the disk moved with the server's", tag(ps, "FS") == ["103"], repr(ps[-3:]))
        ck = fcontrol(A, fA, 99, "x")
        alive = A.req(2, shown="get extended error text (the session is alive)")
        row("Q7 an unknown key (99) is the function's own error and the session lives: the reply is an error (ON ERROR or ERROR), and the next request is answered",
            ck is not None and ck[0] in (1, 3) and alive is not None and alive[0] == 0, repr((ck, alive)))

        # ---- R. refused before anything runs ----------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- R. what is refused before anything runs, even for the global session: the disk and the audit trail are as they were ------------------")
        off_r = rq.audit_off()
        before = analyse_field(ordinary("ANALYZE.FILE zzh"), "Minimum modulus")
        bad = [("PATHNAME x", "PATHNAME"), ("MINIMUM.MODULUS 9 PATHNAME", "PATHNAME"), ("LPTR", "LPTR"), ("FORCE", "FORCE"), ("NO.QUERY", "NO.QUERY"), ("a;b", "a;b"), ("a'b", "a'b"),
               ("a/b", "a/b"), ("a  b", "(two blanks)"), ("x" * 201, "x" * 20 + "..."), ("DIRECTORY x", "DIRECTORY")]
        results = [(w, shown, fileadmin(A, 2, fA, w)) for w, shown in bad]
        row("R1 operation 2 with a word the grammar does not take - %s - each is refused with message 11530 naming the word" % ", ".join(repr(w[:12]) for w, s in bad),
            all(rr is not None and rr[0] == 1 and text(rr) == af.msg(11530).replace("%1", s) for w, s, rr in results),
            repr([(w[:12], text(rr)) for w, s, rr in results if text(rr) != af.msg(11530).replace("%1", s)]))
        row("R2 ...and the disk is as it was (the minimum modulus is still %r)" % before, analyse_field(ordinary("ANALYZE.FILE zzh"), "Minimum modulus") == before, repr(before))
        ops = [fileadmin(A, n, fA, "") for n in (0, 7, 10, 99)]
        row("R3 an operation that is not one (0, 7, 10, 99) is refused with message 11531 naming it", all(refused_with(rr, 11531, n) for rr, n in zip(ops, (0, 7, 10, 99))), repr(ops))
        nf_ = fileadmin(A, 2, 99, "MINIMUM.MODULUS 5")
        row("R4 a file number that is not open (99) is an error (ERROR, the 5268 text) and changes nothing", nf_ is not None and nf_[0] == 3 and errtext(A) == af.msg(5268), repr(nf_))
        dr = fileadmin(A, 8, 0, "zzdirx DIRECTORY")
        isdir = analyse_field(ordinary("ANALYZE.FILE zzdirx"), "Type")
        row("R5 DIRECTORY as the LAST word makes a directory file: OK, and an ordinary session's ANALYZE.FILE reads its type as Directory", dr is not None and dr[0] == 0 and isdir == "Directory",
            repr((dr, isdir)))
        d_del = A.open4("zzdirx")
        if d_del[0] is not None:
            fileadmin(A, 9, d_del[0])
        new = rq.audit_new(off_r)
        row("R6 the audit trail has NO 'api admin' line for the refused requests of R1 to R4: the lines are the two of R5 only",
            new is not None and re.findall(r"api admin request=70 op=(\S+) file=(\S+) user=", new) == [("create.file", "zzdirx"), ("delete.file", "zzdirx")],
            repr(re.findall(r"api admin request=70[^\n]*", new or "")))

        # ---- U. the audit trail ----------------------------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- U. the audit trail gained exactly the lines of the run, in order ----------------------------------------------------------------------")
        new = rq.audit_new(off0)
        got = re.findall(r"api (refused request=\d+ global=off|admin request=\d+ op=\S+ file=.+?) user=sduser$", new or "", re.M)
        want = ["refused request=70 global=off", "refused request=70 global=off", "refused request=71 global=off", "refused request=68 global=off", "refused request=69 global=off",
                "refused request=70 global=off", "refused request=71 global=off",
                "admin request=70 op=analyze.file file=zzh","admin request=70 op=configure.file file=zzh", "admin request=70 op=create.index file=zzh",
                "admin request=70 op=build.index file=zzh", "admin request=70 op=build.index file=zzh", "admin request=70 op=disable.index file=zzh",
                "admin request=70 op=delete.index file=zzh", "admin request=70 op=create.file file=zznew",
                "admin request=70 op=delete.file file=zznew", "admin request=70 op=analyze.file file=zznew",      # V7a (the verb refused: zznew held open by Z) and V7b
                "admin request=70 op=delete.file file=zznew",
                "admin request=70 op=create.file file=zzdirx", "admin request=70 op=delete.file file=zzdirx"]
        row("U1 the 'api refused ... global=off' and 'api admin ...' lines of the whole run are exactly these %d, in this order, all user=sduser (the refusals of Z and G1, then every verb that ran "
            "for the global session - V2a's refused build too, the line is written before the command - and nothing for the words the grammar refused)" % len(want), got == want, repr(got))

        # ---- N. the global password taken away again ----------------------------------------------------------------------------------------------------------------------------------------
        say("\n--- N. the global password is taken away again ($cred put back as it was): the delivered state ------------------------------------------")
        for w in list(af.WIRES):
            w.close()
        restore_cred(snap)
        left = sorted(os.listdir(CRED))
        U3 = wire("U3")
        fU3 = U3.open4("zzh")[0]
        n70 = fileadmin(U3, 1, fU3)
        row("N1 $cred is as it was (%s, no $global) and a new account-password session is refused request 70 with 14964 as in Z" % left,
            left == sorted(snap) and refused_with(n70, 14964, 70), repr((left, n70)))
        U3.close()
    finally:
        for w in list(af.WIRES):
            w.kill()
        restore_cred(snap)
        ordinary("DELETE.FILE zzh NO.QUERY", "DELETE.FILE zznew NO.QUERY", "DELETE.FILE zzdirx NO.QUERY")
        for name in PROGS:
            for p in (os.path.join(ACCT, "bp", name), os.path.join(ACCT, "bp.out", name)):
                try:
                    os.remove(p)
                except OSError:
                    pass
        subprocess.run([os.path.join(SYS, "bin", "sd"), "-cleanup"], env=af.env(), capture_output=True, timeout=60)

    say("\nsandbox-fileadmin-solo: %d passed, %d failed" % (passed, failed))
    if passed + failed == 0:
        bail("no row ran - a broken test, not a pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
