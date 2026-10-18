#!/usr/bin/env python3
#
# sandbox-vocguard.py - the $internal verbs that write a file the USER named must ask !voc_guard.  No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-vocguard.py <dir> [--build] [--only=dellist,cd,...]
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-vocguard.py --text
#
# --only names verbs (dellist getlist sortlst savelst copylst-to copylst-del format cd reformat settrig fixdir generate como mapcat
# createf): the runtime rows of those alone, which is how a mutant (one program's guard taken out of the sandbox's own copy) is run
# against its rows.  The fixture, S0 and part T always run.
#
# <dir> is a sandbox made by sandbox-fromtree.py (SDSOLOBOX_KEYSET picks its keys; unset is 0).  With --build it is built
# first from THIS tree (it must be empty or absent); without it <dir> must already be built, which is how the same script
# is run against an OLD tree to prove it can fail.  --text runs part T alone: no sandbox, no sd, a free check.
# Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
# START-HISTORY:
# 18 Oct 26 dm  Written (Solo carry A, owner's ruling B).  Solo's C gate on the VOC (voc_write_refused) and on gcat, global.bp.out and
#               solo.policy (global_write_refused) stops a USER PROGRAM's own write, but an $internal verb passes it, so every verb that
#               changes a file the user names has to ask !voc_guard for itself.  Solo's ED, EDIT, COPY, COPYP, DELETE, CLEAR.FILE and
#               RENAME did; getlist, savelst, dellist, sortlst, copylst, mapcat, format, fixdir, spview, generate, cd, settrig, qproc
#               (REFORMAT, PAGESEQ), createf, como and basic did not, nor did the API server's record writes.  This suite is the proof,
#               written before the fix and run against the tree without it (red) and the tree with it (green).
# END-HISTORY
#
# WHAT IT MEASURES.  An ORDINARY session (the account password, no ADMIN, as the owner of a Solo installation uses it) in the
# account sduser.  The protected files are
#   a VOC-named file   zzvgv, a pointer to zzvgd/voc, a dynamic file whose last path component is "voc": by voc_guard's rule
#                      (and voc_write_refused's) that IS a VOC, so the real VOC is not damaged by the probes;
#   a global file      global.bp.out, which the account's VOC points at (@SDSYS/global.bp.out), a directory file.
# Each verb is run against
#   R  the VOC-named file as an ordinary user          -> refused (message 11008), nothing changed
#   O  an ordinary file of the account (control)       -> works, the same command, the same effect
#   A  the VOC-named file as the ADMINISTRATOR         -> works (ADMIN opens the VOC)
#   G  global.bp.out as an ordinary user               -> refused (message 11028), nothing changed
#   GA global.bp.out as the ADMINISTRATOR              -> refused too (ADMIN is not enough for the global files, ruling 33)
#   E  COPY and CLEAR.FILE on the VOC-named file       -> still refused (they asked !voc_guard before; it is a wrapper now)
# The state before and after is read two ways: BASIC dumps every record of the files (a program run in the session itself, before
# and after the command), and for the directory files this script reads the bytes on the disk.  "Worked" is the verb's own positive
# wording AND the change; "refused" is the refusal's own text AND no change.
#
# THE NULL CASES.  S0 refuses the run (exit 2, no verdict) unless the control facts hold: an ordinary session is not ADMIN; the
# existing DELETE refuses the VOC-named file and leaves its record; the same DELETE works on the ordinary file; the fixture is what the
# seed program wrote.  A refusal that happens because the fixture is missing would otherwise pass every R row.
#
# NOT RUN, SAID HERE: SP.VIEW (a full-screen reader of keys, it hangs on a pipe), PAGESEQ (a report to a printer: the report is
# queued to lp), BASIC's object file (its name is derived from the source file's), and the API server (a sandbox cannot host an API
# session; verify-solo-service.sh is its harness).  Part T reads their program text instead: each guard is there, is asked of the
# file as opened, and comes before the first statement that changes it.  Text is not a run.

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
GPLBP = os.path.join(SD64, "sdsys", "gpl.bp")
MSGS = os.path.join(SD64, "sdsys", "messages")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
passed = failed = 0


def say(s=""):
    print(s)
    sys.stdout.flush()


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say("  [PASS] " + name)
    else:
        failed += 1
        say("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def bail(msg):
    say("sandbox-vocguard: CANNOT RUN - " + msg)
    sys.exit(2)


# ---------------------------------------------------------------------------------------------------------------------
# Part T: program text.  No sandbox.

def code_of(name):
    """The program's source with whole-line comments and trailing ;* comments removed, lower-cased, one string."""
    path = os.path.join(GPLBP, name)
    if not os.path.isfile(path):
        return ""        # a program this tree does not have: every row that needs its text fails, none passes by default
    out = []
    with open(path, encoding="latin-1") as fh:
        for ln in fh:
            if re.match(r"\s*\*", ln):
                continue
            ln = re.sub(r";\*.*$", "", ln)
            out.append(ln.rstrip())
    return "\n".join(out).lower()


def before(code, guard, write, start=0):
    """True when the first `guard` (a substring) comes before the first `write` (a substring), both after `start`."""
    g = code.find(guard.lower(), start)
    w = code.find(write.lower(), start)
    return g >= 0 and w >= 0 and g < w


def part_text():
    say("\n--- part T: the program text (no sandbox) ---------------------------------------------------------------")
    sites = [
        # (program, guard, first statement that changes the file, what the guard is for)
        ("getlist", "voc_guard(saved.lists.file)", "delete saved.lists.file", "GET.LIST ... IN file DELETING"),
        ("savelst", "voc_guard(saved.lists.file)", "write list.rec to saved.lists.file", "SAVE.LIST ... IN file"),
        ("dellist", "voc_guard(saved.lists.file)", "delete saved.lists.file", "DELETE.LIST ... IN file"),
        ("sortlst", "voc_guard(list.f)", "write sorted to list.f", "SORT.LIST ... FROM file"),
        ("copylst", "voc_guard(tgt.file)", "write list.rec to tgt.file", "COPY.LIST ... TO file"),
        ("copylst", "voc_guard(src.file)", "delete src.file", "COPY.LIST ... FROM file DELETING"),
        ("mapcat", "voc_guard(map.f)", "clearfile map.f", "MAP FILE file"),
        ("format", "voc_guard(src.f)", "write out.rec to src.f", "FORMAT file id"),
        ("fixdir", "voc_guard(f)", "write rec to f", "FIXDIR file"),
        ("spview", "voc_refusal(data.f)", "delete data.f", "SP.VIEW: X deletes the item shown"),
        ("generate", "voc_guard(target.f)", "openseq file.name, record.name overwrite", "GENERATE: the include file"),
        ("cd", "voc_guard(dict.f)", "writeu itype.rec to dict.f", "CD DATA file"),
        ("settrig", "voc_guard(fu)", "set.trigger fu", "SET.TRIGGER file"),
        ("qproc", "voc_guard(pageseq.f)", "readvu pageseq from pageseq.f", "PAGESEQ file"),
        ("qproc", "voc_guard(reformat.f)", "write s to reformat.f", "REFORMAT ... TO file"),
        ("createf", "gosub guard.existing.file", "writeu voc.rec to voc.f, file.name", "CREATE.FILE on an existing file"),
        ("como", "voc_guard(alt.f)", "target.dir = fileinfo(alt.f", "COMO ON ... IN file"),
        ("basic", "voc_guard(out.f)", "delete out.f, record.name", "BASIC: the object file"),
    ]
    for prog, guard, write, what in sites:
        code = code_of(prog)
        row("T %-9s %-38s asks %s before it changes the file" % (prog, what, guard), before(code, guard, write),
            "guard at %d, write at %d" % (code.find(guard.lower()), code.find(write.lower())))
    # every verb declares what it calls
    for prog, decl in (("getlist", "voc_guard"), ("savelst", "voc_guard"), ("dellist", "voc_guard"), ("sortlst", "voc_guard"),
                       ("copylst", "voc_guard"), ("mapcat", "voc_guard"), ("format", "voc_guard"), ("fixdir", "voc_guard"),
                       ("spview", "voc_refusal"), ("generate", "voc_guard"), ("cd", "voc_guard"), ("settrig", "voc_guard"),
                       ("qproc", "voc_guard"), ("createf", "voc_guard"), ("como", "voc_guard"), ("basic", "voc_guard"),
                       ("apisrvr", "voc_refusal")):
        code = code_of(prog)
        want = "deffun %s(f) calling '!%s'" % (decl, decl)
        row("T %-9s declares %s" % (prog, decl), want in code, "no line '%s'" % want)
    # the qproc subroutine and its two callers
    code = code_of("qproc")
    row("T qproc     check.reformat.target is called from the TO clause and from the Output file: prompt",
        code.count("gosub check.reformat.target") == 2, "calls: %d" % code.count("gosub check.reformat.target"))
    row("T qproc     check.reformat.target asks the file REFORMAT writes",
        re.search(r"check\.reformat\.target:\s*\n\s*if voc_guard\(reformat\.f\) then return", code) is not None)
    # the API server: five sites, each guarded after check.file and before the statement
    code = code_of("apisrvr")
    for label, stmt in (("vb.write", "write cmnd[5 + id.len, 99999999] to files(fno), id"),
                        ("vb.writeu", "writeu cmnd[5 + id.len, 99999999] to files(fno), id"),
                        ("vb.delete", "delete files(fno), id"),
                        ("vb.deleteu", "deleteu files(fno), id"),
                        ("vb.clearfile", "clearfile files(fno)")):
        start = code.find("\n" + label + ":")
        row("T apisrvr   %-12s asks check.voc.edit after check.file and before it changes the file" % label,
            start >= 0 and before(code, "gosub check.voc.edit", stmt, start)
            and before(code, "gosub check.file", "gosub check.voc.edit", start), "label at %d" % start)
    row("T apisrvr   no API request clears files(i) (a stale loop variable) any more", "clearfile files(i)" not in code)
    row("T apisrvr   check.voc.edit asks voc_refusal(files(fno)) and sends the text as the client's error",
        re.search(r"check\.voc\.edit:\s*\n\s*err = @true\s*\n\s*voc\.refusal = voc_refusal\(files\(fno\)\)\s*\n\s*if voc\.refusal then"
                  r"\s*\n\s*server\.error = sv\$error\s*\n\s*error\.msg = sysmsg\(voc\.refusal\)", code) is not None)
    # the rule itself lives in one place, in this order
    rule = code_of("voc_refusal")
    row("T voc_refusal  the global files are asked BEFORE the administrator test (ADMIN is not enough for them)",
        before(rule, "k$global.session", "k$administrator") and "return 11028" in rule)
    row("T voc_refusal  the VOC answer is 11008 and the function displays nothing",
        "return 11008" in rule and "display" not in rule)
    guard = code_of("voc_guard")
    row("T voc_guard    is voc_refusal and a display (it carries no copy of the rule)",
        "voc_refusal(f)" in guard and "display sysmsg(n)" in guard and "kernel(" not in guard)
    # the bootstrap compiles BASIC before anything else is catalogued by SECOND.COMPILE
    boot = code_of("bbproc")
    row("T bbproc    voc_refusal and voc_guard are in the bootstrap list (BASIC calls !voc_guard)",
        "src.list<-1> = 'voc_refusal'" in boot and "src.list<-1> = 'voc_guard'" in boot)
    # the message texts the runtime rows look for
    for n in (11008, 11028):
        row("T message %d exists" % n, os.path.isfile(os.path.join(MSGS, str(n))))


# ---------------------------------------------------------------------------------------------------------------------
# The sandbox

def text_of(n):
    with open(os.path.join(MSGS, str(n)), encoding="latin-1") as fh:
        return fh.read().strip()


class Box:
    def __init__(self, path):
        self.root = os.path.abspath(path)
        self.sysd = os.path.join(self.root, "sys")
        self.acct = os.path.join(self.sysd, "user_accounts", "sduser")
        self.glob = os.path.join(self.sysd, "global.bp.out")
        self.sd = os.path.join(self.sysd, "bin", "sd-solo")
        self.conf = os.path.join(self.root, "sd.conf")
        with open(os.path.join(self.root, "account.pw")) as fh:
            self.pw = fh.read().strip()
        with open(os.path.join(self.root, "admin.pw")) as fh:
            self.apw = fh.read().strip()

    def session(self, cmds, admin=False, timeout=180):
        """One ORDINARY login (the account password; no -internal), the commands, OFF.  Returns the text after the TERM line,
        with ANSI codes removed and both passwords replaced.  A session that does not finish is killed and its text is
        'SESSION TIMED OUT'."""
        lines = [self.pw, "TERM 200,9999"]
        if admin:
            lines += ["ADMIN", self.apw]
        lines += list(cmds) + ["OFF"]
        env = dict(os.environ, SD_CONFIG=self.conf)
        try:
            p = subprocess.run([self.sd], input="\n".join(lines) + "\n", cwd=self.sysd, env=env, capture_output=True,
                               text=True, errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            return "SESSION TIMED OUT"
        out = ANSI.sub("", p.stdout + p.stderr).replace("\r", "")
        out = out.replace(self.pw, "<pw>").replace(self.apw, "<admin-pw>")
        return out.split(":TERM 200,9999", 1)[-1] if ":TERM 200,9999" in out else "NO TERM ECHO: " + out[-300:]

    def bp(self, name, body):
        d = os.path.join(self.acct, "bp")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w") as fh:
            fh.write(body)


SEED = """   crt 'SEED START'
   open 'voc' to v else crt 'SEED no voc' ; stop
   write 'F':@fm:'zzvgd/voc':@fm:'zzvgd.dic' to v, 'zzvgv'
   files = 'zzvgv':@fm:'zzvgo'
   for f = 1 to 2
      open files<f> to d else crt 'SEED cannot open ':files<f> ; stop
      for s = 1 to 3
         write 'a':@fm:'b' to d, 'dl':s
         write 'a':@fm:'b' to d, 'gl':s
         write 'a':@fm:'b' to d, 'dr':s
         write 'c':@fm:'a':@fm:'b' to d, 'so':s
         write 'program x':@fm:'if a then':@fm:'b = 1':@fm:'end':@fm:'end' to d, 'fm':s
         it = 'I':@fm:'1+1'
         for k = 3 to 15 ; it := @fm ; next k
         it := @fm:'xobj'
         write it to d, 'cd':s
      next s
   next f
   open 'zzvgsrc' to d else crt 'SEED cannot open zzvgsrc' ; stop
   write 'one':@fm:'two' to d, 'p1'
   write 'three':@fm:'four' to d, 'p2'
   open 'zzvgsr2' to d else crt 'SEED cannot open zzvgsr2' ; stop
   write 'five':@fm:'six' to d, 'q1'
   write 'seven':@fm:'eight' to d, 'q2'
   open 'DICT','zzvgg' to d else crt 'SEED cannot open dict zzvgg' ; stop
   write 'X':@fm:'global.bp.out':@fm:'zzvgg.h':@fm:'g.':@fm:'':@fm:'':@fm:'':@fm:'D' to d, '$INCLUDE'
   write 'D':@fm:'1' to d, 'NAME'
   open 'DICT','zzvgh' to d else crt 'SEED cannot open dict zzvgh' ; stop
   write 'X':@fm:'zzvgdir':@fm:'zzvgh.h':@fm:'h.':@fm:'':@fm:'':@fm:'':@fm:'D' to d, '$INCLUDE'
   write 'D':@fm:'1' to d, 'NAME'
   crt 'SEED DONE'
end
"""

DUMP = """   crt 'DUMP-BEGIN'
   files = 'zzvgv':@fm:'zzvgo'
   for f = 1 to 2
      open files<f> to d else
         crt 'D|':files<f>:'|CANNOT OPEN'
         continue
      end
      select d to 1
      loop
         readnext id from 1 else exit
         read r from d, id then
            crt 'D|':files<f>:'|':id:'|':change(change(r, @fm, '^'), @vm, '~')
         end
      repeat
   next f
   open 'voc' to v then
      for f = 1 to 2
         read r from v, files<f> then crt 'V|':files<f>:'|':change(change(r, @fm, '^'), @vm, '~')
      next f
   end
   crt 'DUMP-END'
end
"""

UNFORMATTED = "program x\nif a then\nb = 1\nend\nend\n"
DIR_SEEDS = {   # name -> bytes: made on the disk by this script in global.bp.out and in zzvgdir
    "zzcr": b"a\rb\r",
    "zzgl": b"x",
    "zzgg": b"a\nb\n",
    "zzgdr": b"a\nb\n",
    "zzgsort": b"c\na\nb\n",
    "zzgf": UNFORMATTED.encode(),
}


def parse_dumps(text):
    """[ {('D', file, id): content, ('V', file): content} ... ] one per DUMP-BEGIN ... DUMP-END in the text."""
    dumps = []
    cur = None
    for ln in text.split("\n"):
        if ln == "DUMP-BEGIN":
            cur = {}
        elif ln == "DUMP-END" and cur is not None:
            dumps.append(cur)
            cur = None
        elif cur is not None:
            m = re.match(r"D\|([^|]*)\|([^|]*)\|(.*)$", ln)
            if m:
                cur[("D", m.group(1), m.group(2))] = m.group(3)
                continue
            m = re.match(r"D\|([^|]*)\|(CANNOT OPEN)$", ln)
            if m:
                cur[("D", m.group(1), "")] = m.group(2)
                continue
            m = re.match(r"V\|([^|]*)\|(.*)$", ln)
            if m:
                cur[("V", m.group(1))] = m.group(2)
    return dumps


def dir_snapshot(path):
    snap = {}
    for n in sorted(os.listdir(path)):
        p = os.path.join(path, n)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                snap[n] = fh.read()
    return snap


FIXTURE_VOC = ["zzvgv", "zzvgd", "zzvgo", "zzvgsrc", "zzvgsr2", "zzvgg", "zzvgh", "zzvgdir"]
FIXTURE_ACCT = ["zzvgv", "zzvgd", "zzvgd.dic", "zzvgo", "zzvgo.dic", "zzvgsrc", "zzvgsrc.dic", "zzvgsr2", "zzvgsr2.dic",
                "zzvgg", "zzvgg.dic", "zzvgh", "zzvgh.dic", "zzvgdir"]
FIXTURE_LISTS = ["zzvgl1", "zzvgl2", "zzvgl3", "zzvgd1", "dr1", "dr2", "dr3", "zzgdrG", "zzgdrO"]   # saved lists the probes made


def remove_exact(parent, name):
    """Remove parent/name (a file, or a directory with what is in it) if it exists.  The name is one component of the
    list above, never a pattern, and the result must still lie inside parent."""
    p = os.path.join(parent, name)
    if "/" in name or not os.path.realpath(p).startswith(os.path.realpath(parent) + os.sep):
        bail("cleanup refuses %r" % p)
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p)
    elif os.path.lexists(p):
        os.remove(p)


def reset_dirs(box):
    """The seeds are put in both directories again; anything else a probe left there is removed."""
    for d in (box.glob, os.path.join(box.acct, "zzvgdir")):
        os.makedirs(d, exist_ok=True)
        for n in os.listdir(d):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                os.remove(p)
        for n, data in DIR_SEEDS.items():
            with open(os.path.join(d, n), "wb") as fh:
                fh.write(data)


# ---------------------------------------------------------------------------------------------------------------------
# The cases.  A case is run as one session: dump, the commands, dump.

VOCMSG = None
GLBMSG = None
# Each of the three runs of a verb (R the VOC-named file, O the ordinary file, A the VOC-named file as ADMIN) uses its own record
# ids and list names: R = 1, A = 2, O = 3.  In the tree WITHOUT the guard the R run really changes the file, and a later run that
# used the same ids would then find the work already done and be judged on a fixture the earlier run had spoiled.
RUN_S = {"R": 1, "A": 2, "O": 3}
# REFORMAT's source file: a second one for the ADMIN run, so that a first run's records cannot hide it
SRC = {1: "zzvgsrc", 2: "zzvgsr2", 3: "zzvgsrc"}


def has_line(text, pattern):
    return re.search(r"(?m)^" + pattern + r"$", text) is not None


def run_rec_case(box, cmds, admin):
    """-> (text, before, after) for a case on records: two dumps around the commands."""
    text = box.session(["RUN bp zzvgdump"] + cmds + ["RUN bp zzvgdump"], admin=admin)
    d = parse_dumps(text)
    if len(d) != 2:
        return text, None, None
    return text, d[0], d[1]


def rec_cases():
    """(id, label, commands(T, s), positive-wording patterns(T, s), effect(before, after, T, s) -> bool)"""
    def gone(i):
        return lambda b, a, T, s: ("D", T, i % s) in b and ("D", T, i % s) not in a

    def made(i):
        return lambda b, a, T, s: ("D", T, i % s) not in b and ("D", T, i % s) in a

    def changed(i):
        return lambda b, a, T, s: ("D", T, i % s) in b and ("D", T, i % s) in a and b[("D", T, i % s)] != a[("D", T, i % s)]

    return [
        ("dellist", "DELETE.LIST dlN IN file", lambda T, s: ["DELETE.LIST dl%d IN %s" % (s, T)],
         lambda T, s: [r"Deleted saved select list 'dl%d'" % s], gone("dl%d")),
        ("getlist", "GET.LIST glN IN file DELETING", lambda T, s: ["GET.LIST gl%d IN %s DELETING" % (s, T)],
         lambda T, s: [r"2 record\(s\) selected to select list 0"], gone("gl%d")),
        ("sortlst", "SORT.LIST soN FROM file", lambda T, s: ["SORT.LIST so%d FROM %s" % (s, T)],
         lambda T, s: [r"3 records saved to select list 'so%d'" % s], changed("so%d")),
        ("savelst", "SAVE.LIST slN IN file", lambda T, s: ["SELECT zzvgo SAMPLE 2", "SAVE.LIST sl%d IN %s" % (s, T)],
         lambda T, s: [r"2 records saved to select list 'sl%d'" % s], made("sl%d")),
        ("copylst-to", "COPY.LIST a,clN TO file", lambda T, s: ["SELECT zzvgo SAMPLE 2", "SAVE.LIST zzvgl%d" % s,
                                                               "COPY.LIST zzvgl%d,cl%d TO %s" % (s, s, T)],
         lambda T, s: [r"1 record\(s\) copied"], made("cl%d")),
        ("copylst-del", "COPY.LIST drN FROM file DELETING", lambda T, s: ["COPY.LIST dr%d FROM %s DELETING" % (s, T)],
         lambda T, s: [r"1 record\(s\) copied"], gone("dr%d")),
        ("format", "FORMAT file fmN", lambda T, s: ["FORMAT %s fm%d" % (T, s)],
         lambda T, s: [], changed("fm%d")),
        ("cd", "CD DATA file cdN", lambda T, s: ["CD DATA %s cd%d" % (T, s)],
         lambda T, s: [r"Compiling cd%d" % s], changed("cd%d")),
        ("reformat", "REFORMAT source @RECORD TO file", lambda T, s: ["REFORMAT %s @ID @RECORD TO %s" % (SRC[s], T)],
         lambda T, s: [r"\d+ record\(s\) reformated, \d+ record\(s\) overwritten"],
         lambda b, a, T, s: any(k[0] == "D" and k[1] == T and k not in b for k in a)),
    ]


def want(name):
    """--only=a,b limits the runtime rows to the verbs named (a mutant is run against its own rows); no --only, all of them."""
    only = [a[len("--only="):].split(",") for a in sys.argv[1:] if a.startswith("--only=")]
    return not only or name in only[0]


def main():
    global VOCMSG, GLBMSG
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--text" in sys.argv:
        say("sandbox-vocguard --text: tree %s" % SD64)
        part_text()
        say("\nsandbox-vocguard: %d passed, %d failed" % (passed, failed))
        return 1 if failed else 0
    if len(args) != 1:
        bail("usage: sandbox-vocguard.py <dir> [--build]   |   sandbox-vocguard.py --text")
    boxdir = os.path.abspath(args[0])
    for n in (11008, 11028):
        if not os.path.isfile(os.path.join(MSGS, str(n))):
            bail("message %d is not in %s" % (n, MSGS))
    VOCMSG, GLBMSG = re.escape(text_of(11008)), re.escape(text_of(11028))
    say("sandbox-vocguard: sandbox  %s" % boxdir)
    say("sandbox-vocguard: tree     %s" % SD64)
    say("sandbox-vocguard: keyset   SDSOLOBOX_KEYSET=%s" % os.environ.get("SDSOLOBOX_KEYSET", "(unset, 0)"))
    if "--build" in sys.argv:
        if os.path.exists(boxdir) and os.listdir(boxdir):
            bail("%s is not empty" % boxdir)
        r = subprocess.run([sys.executable, TOOL, boxdir, "all"], capture_output=True, text=True, errors="replace", timeout=1800)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-1200:])
        say("sandbox-vocguard: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(boxdir, "sys", "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % boxdir)
    box = Box(boxdir)
    r = subprocess.run([sys.executable, TOOL, boxdir, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    say("sandbox-vocguard: binary   %s  (%s)" % (box.sd, subprocess.run(["stat", "-c", "%y", os.path.realpath(box.sd)],
                                                                          capture_output=True, text=True).stdout.strip()[:19]))
    say("sandbox-vocguard: account  sduser, home %s (ordinary login with the account password; ADMIN only where a row says so)" % box.acct)
    say("sandbox-vocguard: messages 11008 = '%s'" % text_of(11008))
    say("sandbox-vocguard:          11028 = '%s'" % text_of(11028))

    try:
        # ---- the fixture
        say("\n--- the fixture ---------------------------------------------------------------------------------------------")
        out = box.session(["CREATE.FILE zzvgo", "CREATE.FILE zzvgsrc", "CREATE.FILE zzvgsr2", "CREATE.FILE zzvgg", "CREATE.FILE zzvgh",
                           "CREATE.FILE DATA zzvgdir DIRECTORY", "CREATE.FILE zzvgd,voc DYNAMIC"])
        made_n = len(re.findall(r"(?m)^Created (DATA|DICT) part as", out))
        if made_n < 7:
            bail("the fixture files were not made (%d 'Created ... part' lines of 7+):\n%s" % (made_n, out[-500:]))
        box.bp("zzvgseed", SEED)
        box.bp("zzvgdump", DUMP)
        out = box.session(["BASIC bp zzvgseed"], admin=True)
        out += box.session(["BASIC bp zzvgdump"])
        if len(re.findall(r"(?m)^Compiled 1 program\(s\) with no errors", out)) != 2:
            bail("the seed and dump programs did not compile:\n" + out[-600:])
        out = box.session(["RUN bp zzvgseed"], admin=True)
        if not has_line(out, "SEED DONE"):
            bail("the seed program did not finish:\n" + out[-500:])
        reset_dirs(box)

        # ---- S0, the null cases
        say("\n--- S0: the control facts (a run is refused, exit 2, if one is not as expected) -------------------------------")
        out = box.session(["LISTU"])
        s0a = has_line(out, "Command requires administrator privileges")
        text, b, a = run_rec_case(box, ["DELETE zzvgv fm2"], admin=False)
        s0b = (b is not None and ("D", "zzvgv", "fm2") in b and ("D", "zzvgv", "fm2") in a and has_line(text, VOCMSG))
        text2, b2, a2 = run_rec_case(box, ["DELETE zzvgo fm2"], admin=False)
        s0c = (b2 is not None and ("D", "zzvgo", "fm2") in b2 and ("D", "zzvgo", "fm2") not in a2 and not has_line(text2, VOCMSG))
        s0d = b is not None and len([k for k in b if k[0] == "D" and k[1] == "zzvgv"]) >= 10 \
            and len([k for k in b if k[0] == "D" and k[1] == "zzvgo"]) >= 10
        say("    an ordinary session is not ADMIN (LISTU refused): %s" % s0a)
        say("    DELETE (already guarded) refuses the VOC-named file and keeps fm2: %s" % s0b)
        say("    the same DELETE works on the ordinary file: %s" % s0c)
        say("    the seeded fixture is there (>= 10 records in each file): %s" % s0d)
        out = box.session(["LISTU"], admin=True)
        s0e = re.search(r"(?m)^\s*User\s+Pid", out) is not None
        say("    ADMIN works in this harness (LISTU lists the users): %s" % s0e)
        if not (s0a and s0b and s0c and s0d and s0e):
            bail("a control fact does not hold, so no verdict would mean anything:\n" + text[-600:] + "\n" + text2[-400:])
        row("S0 control: the VOC-named file is protected by DELETE and the ordinary file is not (the instrument can tell them apart)", True)

        # ---- records: R, O, A
        say("\n--- R / O / A: verbs on a VOC-named file, an ordinary file, and the VOC-named file as the administrator --------")
        for cid, label, cmds, oks, effect in rec_cases():
            if not want(cid):
                continue
            say("  %s  (%s)" % (cid, label))
            for kind, T, admin in (("R", "zzvgv", False), ("O", "zzvgo", False), ("A", "zzvgv", True)):
                s = RUN_S[kind]
                c = cmds(T, s)
                say("    %s > %s" % (kind, " | ".join(c)))
                text, b, a = run_rec_case(box, c, admin)
                if b is None:
                    row("%s %s: the run printed two dumps" % (cid, kind), False, text[-300:])
                    continue
                worked_text = all(has_line(text, p) for p in oks(T, s))
                changed = effect(b, a, T, s)
                refused = has_line(text, VOCMSG)
                detail = "refusal line %s; wording %s; effect %s" % ("yes" if refused else "no", "yes" if worked_text else "no",
                                                                       "yes" if changed else "no")
                if kind == "R":
                    row("%s R: ordinary user on a VOC-named file is refused (11008) and nothing changes" % cid,
                        refused and not changed and not (oks(T, s) and worked_text), detail + "  " + excerpt(text))
                else:
                    row("%s %s: %s works and does what it says" % (cid, kind, "the control" if kind == "O" else "ADMIN"),
                        worked_text and changed and not refused, detail + "  " + excerpt(text))

        # ---- SET.TRIGGER (a report of the state, not a record)
        say("  settrig  (SET.TRIGGER file $acomp, then the report, then the trigger removed)")
        for kind, T, admin in ((("R", "zzvgv", False), ("O", "zzvgo", False), ("A", "zzvgv", True)) if want("settrig") else ()):
            c = ["SET.TRIGGER %s $acomp" % T, "SET.TRIGGER %s" % T, 'SET.TRIGGER %s ""' % T, "SET.TRIGGER %s" % T]
            say("    %s > %s" % (kind, " | ".join(c)))
            text = box.session(c, admin=admin)
            n_set = len(re.findall(r"(?m)^Trigger function: \$acomp$", text))
            refused = has_line(text, VOCMSG)
            none_after = len(re.findall(r"(?m)^File has no trigger function$", text))
            if kind == "R":
                row("settrig R: ordinary user on a VOC-named file is refused (11008) and no trigger is set",
                    refused and n_set == 0 and none_after >= 1, "refusal %s; trigger lines %d; 'no trigger' lines %d  %s" %
                    (refused, n_set, none_after, excerpt(text)))
            else:
                row("settrig %s: %s sets the trigger, the report shows it, and it is removed" % (kind, "the control" if kind == "O" else "ADMIN"),
                    n_set >= 2 and none_after >= 1 and not refused, "trigger lines %d; 'no trigger' lines %d; refusal %s  %s" %
                    (n_set, none_after, refused, excerpt(text)))
        # a trigger left on the VOC-named file (the hole) would run on the next write; it is removed as ADMIN
        box.session(['SET.TRIGGER zzvgv ""', 'SET.TRIGGER zzvgo ""'], admin=True)

        # ---- the directory files: G and its control, and GA
        say("\n--- G / O / GA: verbs on global.bp.out (a global file), zzvgdir (an ordinary directory file), and ADMIN on the global file --")
        dirs = {"G": (box.glob, "global.bp.out", "zzvgg"), "O": (os.path.join(box.acct, "zzvgdir"), "zzvgdir", "zzvgh")}

        def dir_cases(T, dictname, k="G"):
            cases = [
                ("dellist", "DELETE.LIST zzgl IN dir", ["DELETE.LIST zzgl IN %s" % T], [r"Deleted saved select list 'zzgl'"],
                 lambda b, a: "zzgl" in b and "zzgl" not in a),
                ("getlist", "GET.LIST zzgg IN dir DELETING", ["GET.LIST zzgg IN %s DELETING" % T], [r"2 record\(s\) selected to select list 0"],
                 lambda b, a: "zzgg" in b and "zzgg" not in a),
                ("sortlst", "SORT.LIST zzgsort FROM dir", ["SORT.LIST zzgsort FROM %s" % T], [r"3 records saved to select list 'zzgsort'"],
                 lambda b, a: "zzgsort" in a and a["zzgsort"] != b["zzgsort"]),
                ("savelst", "SAVE.LIST zzgs IN dir", ["SELECT zzvgo SAMPLE 2", "SAVE.LIST zzgs IN %s" % T], [r"2 records saved to select list 'zzgs'"],
                 lambda b, a: "zzgs" not in b and "zzgs" in a),
                ("copylst-to", "COPY.LIST zzvgd1,zzgc TO dir", ["SELECT zzvgo SAMPLE 2", "SAVE.LIST zzvgd1", "COPY.LIST zzvgd1,zzgc TO %s" % T],
                 [r"1 record\(s\) copied"], lambda b, a: "zzgc" not in b and "zzgc" in a),
                ("copylst-del", "COPY.LIST zzgdr FROM dir DELETING", ["COPY.LIST zzgdr,zzgdr%s FROM %s DELETING" % (k, T)], [r"1 record\(s\) copied"],
                 lambda b, a: "zzgdr" in b and "zzgdr" not in a),
                ("format", "FORMAT dir zzgf", ["FORMAT %s zzgf" % T], [], lambda b, a: "zzgf" in a and a["zzgf"] != b["zzgf"]),
                ("fixdir", "FIXDIR dir zzcr", ["FIXDIR %s zzcr" % T], [r"1 record\(s\) fixed in %s" % re.escape(T)],
                 lambda b, a: "zzcr" in a and a["zzcr"] != b["zzcr"]),
                ("generate", "GENERATE dictionary whose $INCLUDE names dir", ["GENERATE %s" % dictname], [],
                 lambda b, a: ("%s.h" % dictname) not in b and ("%s.h" % dictname) in a),
                ("como", "COMO ON zzco IN dir", ["COMO ON zzco IN %s" % T, "COMO OFF"], [r"COMO file activated to zzco"],
                 lambda b, a: "zzco" not in b and "zzco" in a),
                ("reformat", "REFORMAT zzvgsrc @ID @RECORD TO dir", ["REFORMAT zzvgsrc @ID @RECORD TO %s" % T], [r"\d+ record\(s\) reformated, \d+ record\(s\) overwritten"],
                 lambda b, a: any(k not in b for k in a)),
                ("mapcat", "MAP FILE dir (and Y)", ["MAP FILE %s" % T, "Y"], [], lambda b, a: "zzcr" in b and "zzcr" not in a),
            ]
            return cases

        for cid in [c[0] for c in dir_cases("x", "y")]:
            if not want(cid):
                continue
            say("  %s" % cid)
            for kind, t in (("G", "G"), ("O", "O")):
                d, T, dictname = dirs[t]
                case = [c for c in dir_cases(T, dictname, kind) if c[0] == cid][0]
                _, label, cmds, oks, effect = case
                reset_dirs(box)
                b = dir_snapshot(d)
                say("    %s > %s" % (kind, " | ".join(cmds)))
                text = box.session(cmds)
                a = dir_snapshot(d)
                worked_text = all(has_line(text, p) for p in oks)
                changed = effect(b, a)
                refused = has_line(text, GLBMSG)
                detail = "refusal line %s; wording %s; effect on the disk %s" % ("yes" if refused else "no", "yes" if worked_text else "no",
                                                                                  "yes" if changed else "no")
                if kind == "G":
                    row("%s G: ordinary user on global.bp.out is refused (11028) and the directory is unchanged" % cid,
                        refused and not changed and b == a and not (oks and worked_text), detail + "  " + excerpt(text))
                else:
                    row("%s O: the control - the same command on an ordinary directory file works" % cid,
                        worked_text and changed and not refused, detail + "  " + excerpt(text))
        # ADMIN is not enough for the global files (ruling 33): the order inside the rule
        for cid, cmds, effect in (("dellist", ["DELETE.LIST zzgl IN global.bp.out"], lambda b, a: "zzgl" in b and "zzgl" not in a),
                                  ("savelst", ["SELECT zzvgo SAMPLE 2", "SAVE.LIST zzgs IN global.bp.out"], lambda b, a: "zzgs" in a)):
            if not want(cid):
                continue
            reset_dirs(box)
            b = dir_snapshot(box.glob)
            say("    GA > ADMIN | %s" % " | ".join(cmds))
            text = box.session(cmds, admin=True)
            a = dir_snapshot(box.glob)
            refused = has_line(text, GLBMSG)
            row("%s GA: the ADMINISTRATOR is refused on global.bp.out too (11028) - ADMIN is not the global session" % cid,
                refused and b == a, "refusal %s; unchanged %s  %s" % (refused, b == a, excerpt(text)))

        # ---- E: the verbs that already asked !voc_guard still do, now that it is !voc_refusal and a display
        say("\n--- E: the older verbs (COPY, CLEAR.FILE) still refuse through !voc_guard, which is a wrapper now ------------------")
        for cid, cmds, eff in (
                ("copy-into", ["COPY FROM zzvgo TO zzvgv fm3,zzcp"], lambda b, a: ("D", "zzvgv", "zzcp") in a),
                ("clearfile", ["CLEAR.FILE zzvgv", "Y"],
                 lambda b, a: len([k for k in a if k[0] == "D" and k[1] == "zzvgv"]) < len([k for k in b if k[0] == "D" and k[1] == "zzvgv"]))):
            if not want(cid):
                continue
            say("    E > %s" % " | ".join(cmds))
            text, b, a = run_rec_case(box, cmds, False)
            if b is None:
                row("%s E: the run printed two dumps" % cid, False, text[-300:])
                continue
            refused = has_line(text, VOCMSG)
            row("%s E: the older verb still refuses the VOC-named file (11008) and changes nothing" % cid,
                refused and not eff(b, a), "refusal %s; changed %s  %s" % (refused, eff(b, a), excerpt(text)))

        # ---- the two verbs that change the whole file last (they spoil the fixture)
        say("\n--- MAP FILE and CREATE.FILE on the VOC-named file (last: they change the file's shape) ----------------------------")
        for kind, T, admin in ((("R", "zzvgv", False), ("O", "zzvgo", False), ("A", "zzvgv", True)) if want("mapcat") else ()):
            c = ["MAP FILE %s" % T, "Y"]
            if kind == "A":
                # the tree without the guard let the R run clear and refill the file; the seed records are put back so that this
                # run starts from a file that holds them (the seed program is idempotent), as it does in the tree with the guard
                box.session(["RUN bp zzvgseed"], admin=True)
            say("    %s > %s" % (kind, " | ".join(c)))
            text, b, a = run_rec_case(box, c, admin)
            if b is None:
                row("mapcat %s: the run printed two dumps" % kind, False, text[-300:])
                continue
            ids_b = sorted(k[2] for k in b if k[0] == "D" and k[1] == T)
            ids_a = sorted(k[2] for k in a if k[0] == "D" and k[1] == T)
            cleared = ids_a != ids_b and not set(ids_b) <= set(ids_a)
            refused = has_line(text, VOCMSG)
            prompt = "will be cleared and overwritten" in text
            if kind == "R":
                row("mapcat R: ordinary user on a VOC-named file is refused (11008), is not even asked to confirm, and nothing changes",
                    refused and not cleared and not prompt, "refusal %s; confirm prompt shown %s; file cleared %s  %s" %
                    (refused, prompt, cleared, excerpt(text)))
            else:
                row("mapcat %s: %s clears and refills the file" % (kind, "the control" if kind == "O" else "ADMIN"),
                    cleared and prompt and not refused, "refusal %s; prompt %s; cleared %s  %s" % (refused, prompt, cleared, excerpt(text)))
        # createf: the F record of the VOC-named file is rewritten (and the file moved) by a conversion to a multifile
        for kind, T, admin in ((("R", "zzvgv", False), ("O", "zzvgo", False), ("A", "zzvgv", True)) if want("createf") else ()):
            # the ADMIN run adds a different component: in the tree without the guard the R run has already converted the file
            c = ["CREATE.FILE %s,%s NO.QUERY" % (T, "zzcompa" if kind == "A" else "zzcomp")]
            say("    %s > %s" % (kind, " | ".join(c)))
            text, b, a = run_rec_case(box, c, admin)
            if b is None:
                row("createf %s: the run printed two dumps" % kind, False, text[-300:])
                continue
            changed = b.get(("V", T)) != a.get(("V", T)) and a.get(("V", T)) is not None
            wording = has_line(text, r'Converting to multifile named "%s,%s"' % (T, T))
            refused = has_line(text, VOCMSG)
            if kind == "R":
                row("createf R: ordinary user cannot convert a VOC-named file (11008); its VOC record is unchanged",
                    refused and not changed and not wording, "refusal %s; converted %s; wording %s  %s" % (refused, changed, wording, excerpt(text)))
            elif kind == "O":
                row("createf O: the control converts an ordinary file to a multifile",
                    changed and wording and not refused, "refusal %s; converted %s; wording %s  %s" % (refused, changed, wording, excerpt(text)))
            else:
                row("createf A: ADMIN changes the VOC-named file's pointer (a component is added)",
                    changed and not refused, "refusal %s; changed %s; wording %s  %s" % (refused, changed, wording, excerpt(text)))
    finally:
        say("\n--- cleanup -------------------------------------------------------------------------------------------------")
        # The VOC pointers are taken out through SD (as ADMIN: one of them is a VOC-named file's); the files themselves, which
        # DELETE.FILE would ask three questions about, by exact name on the disk: nothing here is a pattern.
        try:
            box.session(["DELETE VOC %s" % n for n in FIXTURE_VOC], admin=True)
        except Exception as e:  # the sandbox is disposable; say so and go on
            say("    cleanup session: %r" % e)
        for n in FIXTURE_ACCT:
            remove_exact(box.acct, n)
        for n in FIXTURE_LISTS:
            remove_exact(os.path.join(box.acct, "$svlists"), n)
        for n in ("zzvgseed", "zzvgdump"):
            for dd in ("bp", "bp.out"):
                remove_exact(os.path.join(box.acct, dd), n)
        for n in list(DIR_SEEDS) + ["zzgs", "zzgc", "zzvgg.h", "zzco", "p1", "p2"]:
            remove_exact(box.glob, n)
        left = [n for n in os.listdir(box.glob) if n.startswith("zz") or n in ("p1", "p2")]
        left += [n for n in os.listdir(box.acct) if n.startswith("zzvg")]
        out = box.session(["COUNT VOC WITH @ID LIKE 'zzvg...'"])
        left += [] if has_line(out, r"0 record\(s\) counted") else ["VOC:" + excerpt(out)]
        row("cleanup: nothing of the fixture is left (global.bp.out, the account's directory, the VOC)", not left, " ".join(left))
        say("    the sandbox is left running; stop it with: python3 %s %s stop" % (TOOL, box.root))

    part_text()
    say("\nsandbox-vocguard: %d passed, %d failed" % (passed, failed))
    if passed + failed == 0:
        bail("no row ran - a broken test, not a pass")
    return 1 if failed else 0


def excerpt(text):
    """The last lines SD printed that are not echoes, for a failing row (kept short)."""
    ls = [l for l in text.split("\n") if l.strip() and not l.startswith(":") and not l.startswith("D|") and not l.startswith("V|")
          and l not in ("DUMP-BEGIN", "DUMP-END")]
    return "[" + " / ".join(ls[-4:])[:220] + "]"


if __name__ == "__main__":
    sys.exit(main())
