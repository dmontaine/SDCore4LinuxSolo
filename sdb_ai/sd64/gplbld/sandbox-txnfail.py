#!/usr/bin/env python3
#
# sandbox-txnfail.py - P.6: the step-2 fixes that only an INDUCED FAILURE can
#                      exercise (A1, A3, A5, A6), run in a private Solo sandbox,
#                      each against a mutant build that reverts it.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-txnfail.py --dir <empty scratch dir>
#   python3 .../sandbox-txnfail.py --dir <dir> --keep      leave the sandbox started
#   python3 .../sandbox-txnfail.py --dir <dir> --clean     remove <dir> at the end (default: leave it, say how big)
#
# NO SUDO, AND NEVER THE LIVE SYSTEM.  Exit 0 every decisive row passed on the
# fixed build AND went red on its mutant; 1 a row failed or a mutant did not go
# red; 2 it could not run (or refused to).
#
# START-HISTORY:
# 18 Oct 26 dm  Rewritten on sandbox-fromtree.py (this directory), which builds a
#               key-patched copy of the tree and stages it with solo-stage.sh.  The
#               file had been renamed from the full product's on 29 Sep 26 and
#               never run: it copied the full product's /usr/local/sdsys and a
#               /home/sd account, and its check_admin patch matched nothing in
#               Solo, so it stopped at its first patch.  The probes and the three
#               mutant lists are unchanged; what changed is where they run (the
#               sandbox's SDSYS, through the internal door, since Solo has no
#               other account worth building) and how a mutant is run (its
#               binary is put in the sandbox's bin, because Solo finds its home
#               from its own executable's path).  A5 is run at two limits a
#               kilobyte apart and its red row counts "another status than 8506"
#               as a form of red (said apart from index damage): the old rule
#               could not go red at 32768, where the mutant shows only the other
#               status, which its own comment said was one of the forms.  First
#               run in Solo, 18 Oct 26: 26 rows, the fix green and each mutant
#               red; at 32768 the mutant differs only in status (8006), at 33792
#               it loses index entries, keeps losing them and hangs - the
#               full product's own record of the two limits, reproduced.
# END-HISTORY
#
# ===========================================================================
# WHY A SANDBOX
# ===========================================================================
# Every one of these needs a commit, a truncate or an index write to FAIL part
# way, and the record says what that looks like on the live system when a fix
# is wrong: a stranded lock that survives OFF (queue 27) and the 11 Sep wedge.
# PROJECT_STATUS P.6: "sandbox work, not DON work".  The sandbox is
# sandbox-fromtree.py's: its own shared-memory keys (0x53434CA1/A2, the live
# Solo is 0x53434C11/12), a copy of this tree, staged by solo-stage.sh.  The
# mutants are two more builds of the same tree with one fix reverted each, and
# are run by putting their sd-solo in the sandbox's bin.  The live segments are
# printed before and after and must not change.
#
# ===========================================================================
# WHAT EACH ROW MEASURES (the fix, and what its mutant does instead)
# ===========================================================================
# A6  WEOFSEQ on /dev/null (ftruncate EINVAL) must take ON ERROR with 3010;
#     OPENSEQ ... OVERWRITE on a read-only regular file must too, and leave the
#     file as it was.  A device cannot reach the OVERWRITE truncate
#     (op_seqio.c: SQ_NOTFL skips the special modes), which is why that half
#     uses a read-only file.  Mutant: both "succeed", the old content stays.
# L1  after that failed OVERWRITE, the NEXT session sees no record lock - the
#     op_openseq cleanup fix of 14 Sep 2026, found by this script's first run.
# A3  a transaction that deletes a directory-file record from a directory made
#     mode 555 must fail its COMMIT out loud.  Mutant (bare remove()): COMMIT
#     returns status 0 and the record is still there.
# A1  that same commit wrote two DH records first; the failure must put both
#     back (errlog: "3 record(s) restored").  Mutant (no replay_undo): the two
#     NEW values stay - a half-applied commit.
# A5  an I-type index with 245-byte keys over tiny records, grown under
#     RLIMIT_FSIZE with SIGXFSZ ignored: every write whose index node cannot
#     be allocated must be REPORTED (8506, from get_ak_node), and afterwards the
#     index must hold exactly the records whose writes were not reported as
#     failed, with no wrong entries, and keep working.  MUTANT (grow check
#     removed): WHERE THE LIMIT FALLS DECIDES HOW IT SHOWS.  Measured by hand at
#     32768 it gave the fix's counts with another status (8006); at 33792, this
#     script's first full run, it reported 204 failures while 239 records were
#     missing from the index, lost 16 of 40 later writes after the limit was
#     lifted, and never finished 41..600.  So A5.R asks for ANY of: index loss
#     beyond the reported failures, loss after the limit is lifted, or a hang.
#     The free-node READ-failure path (the double allocation the fix's comment
#     describes) needs a transient read error nothing here can induce, and is
#     stated as unexercised.
#
# ***A1's LOCK HALF IS NOT SCORED***: after the failed commit no locks remain on
# the fixed build AND on its mutant, so this probe cannot see it.  Printed.
#
# THE SANDBOX'S sdlnxd IS KILLED AFTER -start (by executable path): its
# periodic check would run "sd -cleanup" mid-run.  sandbox-fromtree.py does it.

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("sbx", os.path.join(HERE, "sandbox-fromtree.py"))
sbx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sbx)
say, die = sbx.say, sbx.die

PASS = FAIL = 0


def ck(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    say("  [%s] %s%s" % ("PASS" if ok else "FAIL", name, (": " + detail) if detail else ""))


# ---------------------------------------------------------------------------
# The mutants.  Each patch must match exactly once, or the build refuses: a
# patch that matched nothing would build a "mutant" identical to the fix and
# every red control would silently pass.  (The sandbox's own patches - the key
# pair - are sandbox-fromtree.py's and go into every build.)

MUTANT_A = [  # A6 both sites, A1, A5
    ("gplsrc/op_seqio.c",
     "  if (chsize64(fu, sq_file->posn) != 0) {\n    process.status = -ER_IOE;\n    process.os_error = OSError;\n  }\n",
     "  chsize64(fu, sq_file->posn);  /* MUTANT A6 weofseq */\n", "mutant A6 WEOFSEQ"),
    ("gplsrc/op_seqio.c",
     "        if (chsize64(fu, sq_file->posn)) {\n          process.status = -ER_IOE;\n          process.os_error = OSError;\n          goto exit_op_openseq;\n        }\n",
     "        chsize64(fu, sq_file->posn);  /* MUTANT A6 overwrite */\n", "mutant A6 OVERWRITE"),
    ("gplsrc/txn.c",
     "  replay_undo();\n\n  if (commit_txn_id != 0) {\n    unlock_txn(commit_txn_id);\n    commit_txn_id = 0;\n  }\n",
     "  /* MUTANT A1 */\n", "mutant A1 undo+locks"),
    ("gplsrc/dh_ak.c",
     "    if (chsize64(dh_file->sf[subfile].fu, file_bytes + DH_AK_NODE_SIZE)) {\n      dh_err = DHE_AK_WRITE_ERROR;\n      new_node_num = 0;\n      goto exit_get_ak_node;\n    }\n",
     "    chsize64(dh_file->sf[subfile].fu, file_bytes + DH_AK_NODE_SIZE);  /* MUTANT A5 */\n", "mutant A5 grow"),
]

MUTANT_B = [  # A3 alone: with A3 reverted the commit never fails, so A1 cannot share it
    ("gplsrc/txn.c",
     "              if (remove(path) < 0) {\n                process.os_error = errno;\n                if (process.os_error != ENOENT) {\n                  process.status = -ER_PERM;\n                  log_permissions_error(fvar);\n                  k_error(sysmsg(1423));\n                  goto exit_op_txncmt;\n                }\n              }\n",
     "              remove(path);  /* MUTANT A3 */\n", "mutant A3 remove"),
]

# ---------------------------------------------------------------------------
# The BASIC probes, written into the sandbox's bp (SDSYS is the account).

PROBES = {
"zza6": r"""* ZZA6 - A6: WEOFSEQ and OPENSEQ OVERWRITE must report a failed truncate.
path = @path:'/zza6.dat'
openseq path to c then null else null
writeblk 'ABCDE' to c else crt 'CONTROL writeblk failed'
closeseq c
openseq path to c else crt 'CONTROL reopen failed'
readblk x from c, 2 else null
weofseq c on error
   crt 'CONTROL ON ERROR status=':status()
end
crt 'CONTROL weofseq status=':status()
closeseq c
d = '?'
openseq path to c then
   readblk d from c, 100 else d = ''
   closeseq c
end else null
crt 'CONTROL content=':d
openseq '/dev/null' to n else crt 'DEVICE openseq ELSE status=':status()
writeblk 'XYZ' to n else null
weofseq n on error
   crt 'DEVICE ON ERROR status=':status()
   goto done
end
crt 'DEVICE weofseq returned without error, status=':status()
done:
closeseq n
ropath = @path:'/zza6ro.dat'
openseq ropath overwrite to o on error
   crt 'OVERWRITE ON ERROR status=':status()
   goto done2
end then
   crt 'OVERWRITE opened without error, status=':status()
   closeseq o
end else
   crt 'OVERWRITE ELSE status=':status()
end
done2:
openseq path overwrite to c then
   closeseq c
end else crt 'CONTROL overwrite ELSE status=':status()
d = '?'
openseq path to c then
   readblk d from c, 100 else d = ''
   closeseq c
end else null
crt 'CONTROL after overwrite len=':len(d)
crt 'ZZA6 END'
end
""",
"zza1s": r"""* ZZA1S - the BEFORE values, outside any transaction.
open 'zza1h' to h else stop 'ZZA1S cannot open zza1h'
open 'zza1d' to d else stop 'ZZA1S cannot open zza1d'
write 'OLDK1' to h, 'k1'
write 'OLDK2' to h, 'k2'
write 'OLDR1' to d, 'r1'
crt 'ZZA1S wrote k1=OLDK1 k2=OLDK2 r1=OLDR1'
end
""",
"zza1t": r"""* ZZA1T - two DH writes, then a directory-file delete the driver made impossible.
open 'zza1h' to h else stop 'ZZA1T cannot open zza1h'
open 'zza1d' to d else stop 'ZZA1T cannot open zza1d'
crt 'ZZA1T.BEGIN'
begin transaction
   readu x from h, 'k1' else x = ''
   write 'NEWK1' to h, 'k1'
   readu x from h, 'k2' else x = ''
   write 'NEWK2' to h, 'k2'
   readu x from d, 'r1' else x = ''
   delete d, 'r1'
   commit
end transaction
crt 'ZZA1T.COMMIT.RETURNED status=':status()
end
""",
"zza1r": r"""* ZZA1R - what is on file now.
open 'zza1h' to h else stop 'ZZA1R cannot open zza1h'
open 'zza1d' to d else stop 'ZZA1R cannot open zza1d'
read k1 from h, 'k1' else k1 = '(missing)'
read k2 from h, 'k2' else k2 = '(missing)'
read r1 from d, 'r1' else r1 = '(missing)'
crt 'ZZA1R k1=':k1:' k2=':k2:' r1=':r1
end
""",
"zza5d": r"""* ZZA5D - an I-type index key of 245 bytes (MAX_KEY_LEN is 255).
open 'dict', 'zza5' to dd else stop 'ZZA5D cannot open dict zza5'
write 'I':@fm:"STR('K',240):@ID":@fm:'':@fm:'LKEY':@fm:'250L':@fm:'S' to dd, 'lkey'
crt 'ZZA5D wrote dict zza5 lkey'
end
""",
"zza5w": r"""* ZZA5W lo hi - write records lo..hi, each checked.
lo = field(trim(@sentence), ' ', 2) + 0
hi = field(trim(@sentence), ' ', 3) + 0
open 'zza5' to f else stop 'ZZA5W cannot open zza5'
ok = 0 ; bad = 0 ; first.bad = ''
for i = lo to hi
   failed = @false
   write 'D' to f, i on error
      failed = @true
      bad += 1
      if first.bad = '' then first.bad = status()
   end
   if not(failed) then ok += 1
next i
crt 'ZZA5W lo=':lo:' hi=':hi:' ok=':ok:' failed=':bad:' first.status=':first.bad
end
""",
"zza5v": r"""* ZZA5V - every record on file must be found by its index key, exactly.
open 'zza5' to f else stop 'ZZA5V cannot open zza5'
select f to 1
ids = '' ; n.data = 0
loop
   readnext id from 1 else exit
   n.data += 1
   ids<-1> = id
repeat
miss = 0 ; wrong = 0
for i = 1 to n.data
   id = ids<i>
   selectindex 'lkey', str('K', 240):id from f to 2
   got = ''
   loop
      readnext g from 2 else exit
      got<-1> = g
   repeat
   if got = '' then
      miss += 1
   end else
      if got # id then wrong += 1
   end
next i
crt 'ZZA5V data.records=':n.data:' index.missing=':miss:' index.wrong=':wrong
end
""",
}


class Rig:
    """The sandbox plus the binary currently in its bin.  A mutant is run by copying its sd-solo over the sandbox's
    (Solo finds its home from its own executable's path, so a mutant cannot run from its own build directory);
    the fixed binary is kept beside the sandbox and put back."""

    def __init__(self, root, bins):
        self.box = sbx.Box(root)
        self.root = self.box.root
        self.bins = bins            # {"fixed": path, "mutA": path, "mutB": path}
        self.current = "fixed"

    def use(self, which):
        """Make `which` the running binary (a stop, a copy, a start), unless it already is."""
        if which == self.current:
            return
        self.box.stop()
        shutil.copy2(self.bins[which], self.box.sd + ".new")
        os.replace(self.box.sd + ".new", self.box.sd)
        self.current = which
        say("    binary now: %s (%s)" % (which, self.bins[which]))
        self.box.start()

    def restart(self):
        self.box.stop()
        self.box.start()

    def session(self, lines, which="fixed", limit=None, timeout=120):
        self.use(which)
        say("    > [%s]%s %s" % (which, (" (RLIMIT_FSIZE=%d, SIGXFSZ ignored)" % limit) if limit else "", " | ".join(lines)))
        rc, out, left = self.box.session(lines, limit=limit, timeout=timeout)
        if out == "TIMEOUT":
            say("      | TIMEOUT after %d s - the session was killed" % timeout)
            return "TIMEOUT"
        if ":TERM 200,9999" not in out:
            say("      | THE SESSION DID NOT RUN (no ':TERM 200,9999' echo; marker left: %s)" % left)
        for l in out.splitlines():
            if re.match(r"^(ZZA|CONTROL|DEVICE|OVERWRITE|[0-9A-F]{8}:|There are|User |\s+\d+\s+\d+ )", l):
                say("      | " + l)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="an EMPTY or absent scratch directory")
    ap.add_argument("--keep", action="store_true", help="leave the sandbox started")
    ap.add_argument("--clean", action="store_true", help="remove the directory at the end")
    a = ap.parse_args()
    if os.getuid() == 0:
        die("sandbox-txnfail: REFUSED - run it as an ordinary user; Solo never runs as root")
    root = os.path.abspath(a.dir)
    sbx.refuse_inside_a_solo_tree(root)

    say("sandbox-txnfail (Solo)")
    say("  tree        : %s" % sbx.SD64)
    say("  sandbox     : %s" % root)
    say("  keys        : %s %s (%s=%s)" % (sbx.BOX_KEYS[0], sbx.BOX_KEYS[1], sbx.KEYSET_VAR, sbx.KEYSET))
    before = sbx.live_snapshot()
    sbx.show_live("before", before)
    held = [k for k in sbx.BOX_KEYS if k in sbx.ipcs_rows()]
    if held:
        die("sandbox-txnfail: REFUSED - sandbox keys %s are held; stop the old sandbox first" % " ".join(held))
    if os.path.exists(root) and os.listdir(root):
        die("sandbox-txnfail: REFUSED - %s is not empty." % root)
    os.makedirs(root, exist_ok=True)

    rig = None
    try:
        say("\n=== 1. build: the sandbox (sandbox-fromtree.py all) and two mutants")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sandbox-fromtree.py"), root, "all"],
                           capture_output=True, text=True, errors="replace", timeout=1800)
        say("\n".join("    | " + l for l in r.stdout.splitlines()[-12:]))
        if r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout or "[FAIL]" in r.stdout:
            die("sandbox-txnfail: CANNOT RUN - the sandbox bootstrap did not pass (exit %d)" % r.returncode)
        sbx.build(os.path.join(root, "mutA"), os.path.join(root, "make-mutA.log"), MUTANT_A)
        sbx.build(os.path.join(root, "mutB"), os.path.join(root, "make-mutB.log"), MUTANT_B)
        bins = {"fixed": os.path.join(root, "fixed-sd-solo"),
                "mutA": os.path.join(root, "mutA", "bin", "sd-solo"),
                "mutB": os.path.join(root, "mutB", "bin", "sd-solo")}
        shutil.copy2(os.path.join(root, "sys", "bin", "sd-solo"), bins["fixed"])
        rig = Rig(root, bins)
        box = rig.box
        sysd = box.sys

        say("\n=== 2. start, and the probes")
        box.start()
        rows = sbx.ipcs_rows()
        ck("S0 the sandbox has its own keys and the live keys are untouched",
           all(k in rows for k in sbx.BOX_KEYS) and all(before[k] == rows.get(k) for k in before))
        for name, src in PROBES.items():
            with open(os.path.join(sysd, "bp", name), "w") as f:
                f.write(src)
        out = rig.session(["CREATE.FILE zza1d DIRECTORY", "CREATE.FILE zza1h", "CREATE.FILE zza5",
                           "BASIC BP " + " ".join(n.upper() for n in PROBES)]
                          + ["CATALOG BP %s LOCAL" % n for n in PROBES])
        ck("S1 every probe compiled", "Compiled %d program(s) with no errors" % len(PROBES) in out)

        # ---- A6 and L1 -------------------------------------------------------
        say("\n=== 3. A6 (and L1): a failed truncate is reported, and leaves no lock")
        ro = os.path.join(sysd, "zza6ro.dat")
        results = {}
        for label, which in (("fixed", "fixed"), ("mutant", "mutA")):
            rig.restart()
            with open(ro, "w") as f:
                f.write("OLDCONTENT")
            os.chmod(ro, 0o444)
            out = rig.session(["ZZA6"], which)
            os.chmod(ro, 0o644)
            with open(ro) as f:
                kept = f.read()
            locks = rig.session(["LIST.READU"], "fixed")
            results[label] = (out, kept, locks)
        out, kept, locks = results["fixed"]
        ck("A6.0 control: a regular file truncates (content AB)", "CONTROL content=AB" in out)
        ck("A6.1 WEOFSEQ on /dev/null takes ON ERROR with 3010", "DEVICE ON ERROR status=3010" in out)
        ck("A6.2 OVERWRITE of a read-only file takes ON ERROR with 3010", "OVERWRITE ON ERROR status=3010" in out)
        ck("A6.3 and the read-only file is unchanged", kept == "OLDCONTENT", repr(kept))
        ck("L1 the next session holds no stranded lock", "There are no active file, read or update locks" in locks)
        out, kept, locks = results["mutant"]
        ck("A6.1R RED: the mutant's WEOFSEQ reports nothing", "DEVICE weofseq returned without error" in out)
        ck("A6.2R RED: the mutant's OVERWRITE 'opens' and truncates nothing", "OVERWRITE opened without error" in out and kept == "OLDCONTENT")

        # ---- A3 and A1 -------------------------------------------------------
        say("\n=== 4. A3 and A1: a commit that fails part way says so and puts back what it wrote")
        d = os.path.join(sysd, "zza1d")
        errlog = os.path.join(sysd, "errlog")

        def txn_run(which):
            os.chmod(d, 0o755)
            rig.session(["ZZA1S"], "fixed")
            n0 = os.path.getsize(errlog) if os.path.exists(errlog) else 0
            os.chmod(d, 0o555)
            say("    zza1d is now mode %o" % (os.stat(d).st_mode & 0o7777))
            out = rig.session(["ZZA1T", "LIST.READU"], which)
            os.chmod(d, 0o755)
            back = rig.session(["ZZA1R"], "fixed")
            with open(errlog, errors="replace") as f:
                f.seek(n0)
                new = f.read()
            for l in new.splitlines():
                if l.strip():
                    say("      errlog| " + l.strip())
            return out, back, new

        out, back, new = txn_run("fixed")
        ck("A3.1 the commit fails out loud", "Delete error in transaction commit" in out and "ZZA1T.COMMIT.RETURNED" not in out)
        ck("A1.1 both DH writes are put back", "ZZA1R k1=OLDK1 k2=OLDK2 r1=OLDR1" in back)
        ck("A1.2 errlog names the undo", "3 record(s) restored" in new)
        say("    A1 lock half (NOT SCORED): LIST.READU after the failure said: %s"
            % ("no locks" if "There are no active" in out else "locks listed"))
        out, back, new = txn_run("mutA")
        ck("A1.1R RED: without the undo the commit is left half applied", "ZZA1R k1=NEWK1 k2=NEWK2 r1=OLDR1" in back)
        say("    A1 lock half on the mutant (NOT SCORED): %s" % ("no locks" if "There are no active" in out else "locks listed"))
        out, back, new = txn_run("mutB")
        ck("A3.1R RED: with a bare remove() the commit returns 0", "ZZA1T.COMMIT.RETURNED status=0" in out)
        ck("A3.2R RED: and the 'deleted' record is still there", "r1=OLDR1" in back)

        # ---- A5 --------------------------------------------------------------
        say("\n=== 5. A5: index node allocation failing under RLIMIT_FSIZE")
        rig.session(["ZZA5D", "CREATE.INDEX zza5 lkey", "ZZA5W 1 40", "BUILD.INDEX zza5 lkey"], "fixed")
        base = rig.session(["ZZA5V"], "fixed")
        ck("A5.0 baseline: 40 records, index exact", "ZZA5V data.records=40 index.missing=0 index.wrong=0" in base)
        snap = os.path.join(root, "zza5.base")
        shutil.copytree(os.path.join(sysd, "zza5"), snap)
        ak = os.path.join(sysd, "zza5", "%2")
        vocmax = max(os.path.getsize(os.path.join(sysd, "voc", x)) for x in os.listdir(os.path.join(sysd, "voc")))
        limit0 = max(os.path.getsize(ak) + 2 * 4096, vocmax + 4096)
        say("    index subfile %%2 = %d bytes; largest voc subfile %d; first limit %d" % (os.path.getsize(ak), vocmax, limit0))
        # WHERE THE LIMIT FALLS DECIDES HOW THE MUTANT SHOWS (the record above: 32768 gave only another status, 33792
        # gave index loss, loss after the limit was lifted, and a hang), so two limits a kilobyte apart are run, the
        # fixed rows are required at both, and the mutant has to go red in some form at one of them.
        red_forms = {}
        for limit in (limit0, limit0 + 1024):
            found = {}
            for label, which in (("fixed", "fixed"), ("mutant", "mutA")):
                shutil.rmtree(os.path.join(sysd, "zza5"))
                shutil.copytree(snap, os.path.join(sysd, "zza5"))
                w = rig.session(["ZZA5W 41 300"], which, limit=limit)
                v1 = rig.session(["ZZA5V"], "fixed")
                w2 = rig.session(["ZZA5W 601 640"], "fixed")
                v2 = rig.session(["ZZA5V"], "fixed")
                m = re.search(r"ok=(\d+) failed=(\d+) first.status=(\d*)", w)
                found[label] = (m.groups() if m else None, v1, w2, v2)
            g, v1, w2, v2 = found["fixed"]
            ck("A5.1 @%d writes past the limit were REPORTED, with 8506 (get_ak_node)" % limit,
               g is not None and int(g[1]) > 0 and g[2] == "8506", str(g))
            if g:
                ck("A5.2 @%d the index misses exactly the reported failures, no wrong entries" % limit,
                   ("index.missing=%s index.wrong=0" % g[1]) in v1)
                ck("A5.3 @%d and keeps working: 40 more writes, still exact apart from those" % limit,
                   "ok=40 failed=0" in w2 and ("index.missing=%s index.wrong=0" % g[1]) in v2)
            gm, mv1, mw2, mv2 = found["mutant"]
            say("    mutant reported %s; status %s where the fix gives 8506" % (str(gm), gm[2] if gm else "?"))
            # The first run of the full product's script found the mutant did not finish 41..600
            # inside 120 s where the fix did at once.  Measured again here, bounded.
            hung = {}
            for label, which in (("fixed", "fixed"), ("mutant", "mutA")):
                shutil.rmtree(os.path.join(sysd, "zza5"))
                shutil.copytree(snap, os.path.join(sysd, "zza5"))
                t0 = time.time()
                w = rig.session(["ZZA5W 41 600"], which, limit=limit, timeout=60)
                hung[label] = (w == "TIMEOUT")
                say("    %s, 41..600 under the limit: %s in %.1f s"
                    % (label, "TIMEOUT" if hung[label] else "finished", time.time() - t0))
            ck("A5.4 @%d the fix finishes 41..600 under the limit" % limit, not hung["fixed"])
            # THE FORMS OF RED: the mutant's unchecked grow (a) loses index entries it reported as written, (b) keeps
            # losing them after the limit is lifted, (c) never finishes, or (d) is reported with another status than
            # the fix's 8506 - the weakest, the only one at 32768, and a status is not damage, so it is said apart.
            silent = False
            if gm:
                mm = re.search(r"index.missing=(\d+)", mv1)
                silent = bool(mm) and int(mm.group(1)) != int(gm[1])
            mm2 = re.search(r"index.missing=(\d+)", mv2)
            mm1 = re.search(r"index.missing=(\d+)", mv1)
            drift = bool(mm1 and mm2) and int(mm2.group(1)) != int(mm1.group(1))
            status_only = bool(gm and g and gm[2] != g[2])
            red_forms[limit] = {"silent index loss": silent, "loss after the limit lifted": drift,
                                "hang": hung["mutant"], "another status than 8506": status_only}
            say("    mutant @%d: %s" % (limit, ", ".join("%s=%s" % kv for kv in red_forms[limit].items())))
        data_red = any(v for f in red_forms.values() for k, v in f.items() if k != "another status than 8506")
        any_red = any(v for f in red_forms.values() for v in f.values())
        ck("A5.R RED: without the grow check the write is reported differently, or the index is damaged, or it never finishes",
           any_red)
        say("    A5.R went red by %s" % ("DATA (index loss or a hang) at some limit" if data_red
                                         else "STATUS ONLY at both limits (another status than 8506; no index damage seen)"))
        say("    A5 UNEXERCISED: the free-node read-failure path (the double-allocation damage) needs a transient read error.")
    finally:
        say("\n=== teardown")
        if rig is not None:
            try:
                rig.use("fixed")
            except Exception as e:
                say("    restoring the fixed binary: %s" % e)
            if not a.keep:
                rig.box.stop()
            else:
                say("    --keep: SD left started (stop it with: python3 %s %s stop)"
                    % (os.path.join(HERE, "sandbox-fromtree.py"), root))
        elif os.path.isdir(os.path.join(root, "sys")):
            sbx.Box(root).stop()
        after = sbx.live_snapshot()
        sbx.show_live("after", after)
        rows = sbx.ipcs_rows()
        ck("T0 no sandbox key is left (unless --keep) and the live keys are as they were",
           (a.keep or not any(k in rows for k in sbx.BOX_KEYS)) and all(before[k] == after[k] for k in before))
        if a.clean:
            for dirpath, dirnames, files in os.walk(root):
                for n in dirnames + files:
                    try:
                        if not os.path.islink(os.path.join(dirpath, n)):
                            os.chmod(os.path.join(dirpath, n), 0o755)
                    except OSError:
                        pass
            shutil.rmtree(root, ignore_errors=True)
            say("  removed %s" % root)
        else:
            say("  %s left in place (%d entries); remove it yourself, after stopping the sandbox if --keep"
                % (root, sum(len(d) + len(f) for _, d, f in os.walk(root))))

    say("\n  passed: %d   failed: %d" % (PASS, FAIL))
    if PASS == 0:
        say("sandbox-txnfail: FAILED - no row ran.")
        return 1
    if FAIL:
        say("sandbox-txnfail: FAILED - %d row(s)." % FAIL)
        return 1
    say("sandbox-txnfail: PASSED - every decisive row passed on the fix and went red on its mutant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
