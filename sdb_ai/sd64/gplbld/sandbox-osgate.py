#!/usr/bin/env python3
#
# sandbox-osgate.py - the Solo OS-access switch (SH and OS) RUN on a private SD Core for Linux Solo: ordinary sessions of the one
#                     account, sduser, that refuse, run, and leave a sentinel on the disk as evidence.  Solo's copy of the idea of
#                     SD Core's sandbox-gates.py (S.63); written FIRST, before the switch existed, and run red on a423ed5.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-osgate.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo).  With --build it is built first from THIS tree
# (it must be empty or absent).  SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop
# the sandbox afterwards with sandbox-fromtree.py <dir> stop.
#
# START-HISTORY:
# 20 Oct 26 dm  Written for the Solo OS switch (owner, 20 Oct: two words like Core, SET.OS.ACCESS, the installer asks).
# END-HISTORY
#
# THE LANE.  A plain session of sduser: sd-solo with the account password as the first line of the pipe (read from <dir>/account.pw,
# never printed), then TERM, the commands, OFF.  It has not typed `admin`, which WHO.AM.I proves (the null case; exit 2 otherwise).
# The administrator's lane is the same with `ADMIN` and <dir>/admin.pw typed first.  The internal lane is sandbox-fromtree.py's `sess`.
#
# THE STATES.  The switch is two fields of the register record accounts/sduser (field 7 SH, field 8 OS.EXEC), 'yes' is on and anything
# else is off.  The suite WRITES the record for each of four states (off, sh, os, both) and signs on again: the load is at sign-on,
# so a change is seen by the NEXT session, never the running one.  EVIDENCE IS THE DISK: a file that appears, a file that is gone, a
# file that is still there.
#
# NOT RUN HERE, said plainly: SKT$INFO.TRACE (needs a socket peer), an API session's load of the switches (sandbox-apifile.py can host one; not driven here), the installer's question
# (test-install-osaccess.sh), the audit file (read by the owner's witness).

import argparse
import getpass
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ACCOUNT = "sduser"
USER = getpass.getuser()
SECRETS = []
passed = failed = 0
BOX = SYS = ACCT = REG = OUT = ""


def say(s=""):
    for sec in SECRETS:
        s = s.replace(sec, "<password>")
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
    say("sandbox-osgate: CANNOT RUN - " + msg)
    sys.exit(2)


def secret(name):
    path = os.path.join(BOX, name)
    try:
        with open(path) as f:
            pw = f.read().strip()
    except OSError as e:
        bail("cannot read %s: %s" % (path, e))
    if not pw:
        bail("%s is empty" % path)
    if pw not in SECRETS:
        SECRETS.append(pw)
    return pw


def session(cmds, unlock=False, timeout=300):
    """A session of sduser on a pipe.  unlock=True types ADMIN and the administrator password first.  Returns the lines printed after the
    TERM line, echoed commands (those that begin with a colon) and blank lines left out.  The commands are shown."""
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    head = secret("account.pw") + "\n"
    if unlock:
        head += "ADMIN\n" + secret("admin.pw") + "\n"
    body = head + "TERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n"
    say("    > %s%s" % ("[admin] " if unlock else "", " | ".join(cmds)))
    p = subprocess.Popen([os.path.join(SYS, "bin", "sd-solo")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         cwd=SYS, env=env, text=True, errors="replace")
    try:
        out, _ = p.communicate(body, timeout=timeout)
    except subprocess.TimeoutExpired:
        p.send_signal(signal.SIGHUP)
        try:
            out, _ = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        out = (out or "") + "\n:TERM 200,9999\nSESSION TIMED OUT\n"
    out = ANSI.sub("", out or "").split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def internal(cmds):
    """An internal session (SDSYS): sandbox-fromtree.py's `sess` writes the one-shot marker."""
    say("    > [internal] " + " | ".join(cmds))
    r = subprocess.run([sys.executable, TOOL, BOX, "sess", SYS] + cmds, capture_output=True, text=True, errors="replace", timeout=600)
    out = ANSI.sub("", r.stdout + r.stderr).split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def has(lines, pattern):
    return any(re.search(pattern, ln) for ln in lines)


def put(path, text):
    with open(path, "w", encoding="ascii") as f:
        f.write(text)


def reg_state(sh, osx):
    """Write fields 7 and 8 of the register record accounts/sduser ('yes' or blank) and keep the first six as they were."""
    with open(REG) as f:
        lines = f.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    lines += [""] * (8 - len(lines))
    lines = lines[:6] + ["yes" if sh else "", "yes" if osx else ""] + lines[8:]
    put(REG, "\n".join(lines) + "\n")


def reg_fields():
    with open(REG) as f:
        lines = f.read().split("\n")
    lines += [""] * (8 - len(lines))
    return lines[6].strip().lower(), lines[7].strip().lower()


def prog(name, body):
    """A plain program in sduser's bp (compiled by a session, not internal)."""
    put(os.path.join(ACCT, "bp", name), "program %s\n%s\nend\n" % (name, "\n".join("   " + l for l in body)))


def compiled(out, n=1):
    return has(out, r"^Compiled %d program\(s\) with no errors" % n) and not has(out, r"^WARNING")


def clean(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


# --------------------------------------------------------------------------------------------------------------------------------

def prepare():
    """Probes that only an internal program can be: the switches as the kernel holds them, and K$PATH.OK; each reached by a VOC verb
    in sduser's VOC (written by an internal program, since the VOC is the administrator's)."""
    put(os.path.join(SYS, "gpl.bp", "zzkf"), "\n".join([
        "$internal", "program zzkf", "$catalog $zzkf", "$include keys.h", "$include int$keys.h",
        "   crt 'KFLAGS admin=':kernel(K$ADMINISTRATOR,-1):' sh=':kernel(K$SH,-1):' osx=':kernel(K$OS.EXEC,-1)", "end", ""]))
    put(os.path.join(SYS, "gpl.bp", "zzkp"), "\n".join([
        "$internal", "program zzkp", "$catalog $zzkp", "$include keys.h", "$include int$keys.h",
        "   crt 'KP outside=':kernel(K$PATH.OK,'/etc/hostname'):' inside=':kernel(K$PATH.OK,'inside.txt'):"
        "' dotdot=':kernel(K$PATH.OK,'sub/../../outside-of-account'):' empty=':kernel(K$PATH.OK,'')",
        "   openseq '/etc/hostname' to f then crt 'KP internal-openseq-outside OK' else crt 'KP internal-openseq-outside REFUSED'", "end", ""]))
    out = internal(["BASIC gpl.bp zzkf zzkp"])
    ok = has(out, r"^Compiled 2 program\(s\) with no errors")
    row("setup: the two internal probes (the switches as the kernel holds them, K$PATH.OK) compile", ok, "output=%r" % (out[-4:],))
    put(os.path.join(SYS, "bp", "zzfix"), "\n".join([
        "$internal",
        "   openpath '%s/voc' to v else crt 'FIX no voc' ; stop" % ACCT,
        "   write 'V':@fm:'CA':@fm:'$zzkf' to v, 'zzkf'",
        "   write 'V':@fm:'CA':@fm:'$zzkp' to v, 'zzkp'",
        "   write 'F':@fm:'/etc':@fm:'' to v, 'zzptr'",
        "   crt 'FIX done'", "end", ""]))
    out = internal(["BASIC bp zzfix", "RUN bp zzfix"])
    row("setup: the probe verbs and an F-pointer at /etc are written into sduser's VOC by an internal program", has(out, r"^FIX done$"), "output=%r" % (out[-4:],))
    os.makedirs(os.path.join(ACCT, "sub"), exist_ok=True)
    put(os.path.join(ACCT, "inside.txt"), "an ordinary file in the account\n")
    return ok


def main():
    global BOX, SYS, ACCT, REG, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    BOX = os.path.abspath(a.dir)
    SYS = os.path.join(BOX, "sys")
    ACCT = os.path.join(SYS, "user_accounts", ACCOUNT)
    REG = os.path.join(SYS, "accounts", ACCOUNT)
    OUT = os.path.join(SYS, "zzoutside")           # inside sys, outside the account: an ordinary account must not reach it
    say("sandbox-osgate: sandbox  %s" % BOX)
    say("sandbox-osgate: tree     %s" % SD64)
    say("sandbox-osgate: user %s; the one account is %s, its register record %s" % (USER, ACCOUNT, REG))
    if a.build:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-osgate: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(REG):
        bail("there is no register record %s" % REG)

    # --- controls: the session is ordinary, the register starts OFF -------------------------------------------------------------
    say("\n--- controls -----------------------------------------------------------------------------------------------------")
    out = session(["WHO.AM.I"])
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of %s and NOT an administrator (WHO.AM.I says Admin? %s)" % (ACCOUNT, adm.group(1) if adm else "-"),
        has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        bail("the session is privileged; its refusals prove nothing")
    sh0, os0 = reg_fields()
    row("the register record as the install made it has the switches OFF (fields 7 and 8 are not 'yes')", sh0 != "yes" and os0 != "yes", "fields=%r %r" % (sh0, os0))
    prepare()          # a probe that does not compile is a FAILED row here, and the rows that need it fail too: the run still shows every route

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "listme"))
    put(os.path.join(OUT, "existing.txt"), "OUTSIDE-SECRET-12345\n")
    put(os.path.join(OUT, "listme", "a.txt"), "a\n")
    put(os.path.join(OUT, "listme", "b.txt"), "b\n")

    states = (("OFF", False, False), ("SH only", True, False), ("OS only", False, True), ("BOTH", True, True))
    for label, sh_on, os_on in states:
        say("\n=== state: %s (field 7 %s, field 8 %s) ===========================================================" % (
            label, "yes" if sh_on else "blank", "yes" if os_on else "blank"))
        reg_state(sh_on, os_on)
        for junk in ("sh.sentinel", "bang.sentinel", "osx.sentinel", "victim.txt", "mk", "prt.out", "hold.out", "ptr.seen"):
            clean(os.path.join(OUT, junk))
        put(os.path.join(OUT, "victim.txt"), "to be deleted\n")
        put(os.path.join(ACCT, "mine-to-delete.txt"), "an ordinary file of the account\n")
        clean(os.path.join(ACCT, "own.sentinel"))
        os.makedirs(os.path.join(ACCT, "$hold"), exist_ok=True)

        # A. the switches as the kernel holds them (loaded at sign-on from the register)
        out = session(["zzkf"])
        m = [re.match(r"^KFLAGS admin=(\d+) sh=(\d+) osx=(\d+)$", ln) for ln in out]
        m = next((x for x in m if x), None)
        row("%s: the kernel holds sh=%d osx=%d, loaded at sign-on from the register, and the session is not the administrator" % (label, sh_on, os_on),
            bool(m) and (m.group(1), m.group(2), m.group(3)) == ("0", str(int(sh_on)), str(int(os_on))), "output=%r" % (out[-3:],))

        # B. the SH verb and "!"
        out = session(["SH touch %s/sh.sentinel" % OUT, "! touch %s/bang.sentinel" % OUT, "SH touch own.sentinel"])
        refusals = sum(1 for ln in out if re.search(r"is not permitted to use the operating system shell$", ln))
        if sh_on:
            row("%s: SH and '!' run: both sentinels are on the disk and nothing was refused" % label,
                os.path.exists(os.path.join(OUT, "sh.sentinel")) and os.path.exists(os.path.join(OUT, "bang.sentinel")) and refusals == 0
                and os.path.exists(os.path.join(ACCT, "own.sentinel")), "output=%r" % (out,))
        else:
            row("%s: SH and '!' are refused (10053, once each, three commands): no sentinel on the disk, in the account either" % label,
                refusals == 3 and not os.path.exists(os.path.join(OUT, "sh.sentinel")) and not os.path.exists(os.path.join(OUT, "bang.sentinel"))
                and not os.path.exists(os.path.join(ACCT, "own.sentinel")), "output=%r" % (out,))

        # C-D. OS.EXECUTE and every route to an OS path, in one program (a T line each)
        prog("ogroute", [
            "crt 'T begin'",
            "openseq '%s/existing.txt' to f1 then" % OUT,
            "   crt 'T openseq-outside OPENED'",
            "   closeseq f1",
            "end else",
            "   crt 'T openseq-outside REFUSED ':status()",
            "end",
            "openseq 'inside.txt' to f2 then",
            "   crt 'T openseq-inside OPENED'",
            "   closeseq f2",
            "end else",
            "   crt 'T openseq-inside REFUSED ':status()",
            "end",
            "openpath '%s' to d1 then" % OUT,
            "   crt 'T openpath-outside OPENED'",
            "   close d1",
            "end else",
            "   crt 'T openpath-outside REFUSED ':status()",
            "end",
            "x = dir('%s/listme')" % OUT,
            "crt 'T dir-outside ':dcount(x, @fm):' ':status()",
            "y = dir('sub')",
            "crt 'T dir-inside ':status()",
            "deleteseq '%s/victim.txt' then" % OUT,
            "   crt 'T deleteseq-outside DONE'",
            "end else",
            "   crt 'T deleteseq-outside ELSE ':status()",
            "end",
            "deleteseq 'mine-to-delete.txt' then",
            "   crt 'T deleteseq-own DONE'",
            "end else",
            "   crt 'T deleteseq-own ELSE ':status()",
            "end",
            "crt 'T end'",
        ])
        prog("ogosx", ["crt 'T osx-begin'", "os.execute 'touch %s/osx.sentinel'" % OUT, "crt 'T osx-end'"])
        outx = session(["BASIC bp ogosx", "RUN bp ogosx"])
        if os_on:
            row("%s: OS.EXECUTE runs: the sentinel is on the disk and the program went on" % label,
                os.path.exists(os.path.join(OUT, "osx.sentinel")) and has(outx, r"^T osx-end$"), "output=%r" % (outx,))
        else:
            row("%s: OS.EXECUTE is refused (10054): no sentinel on the disk and the program stopped" % label,
                not os.path.exists(os.path.join(OUT, "osx.sentinel")) and has(outx, r"is not permitted to use OS\.EXECUTE") and not has(outx, r"^T osx-end$"),
                "output=%r" % (outx,))
        out = session(["BASIC bp ogroute", "RUN bp ogroute"])
        if not compiled(out):
            row("%s: the route probe compiled" % label, False, "output=%r" % (out[-4:],))
            continue
        if not has(out, r"^T end$"):
            row("%s: the route probe ran to its end" % label, False, "output=%r" % (out[-6:],))
            continue
        row("%s: controls: the account's own files are reached whatever the switch says (OPENSEQ, DIR, DELETESEQ inside)" % label,
            has(out, r"^T openseq-inside OPENED$") and has(out, r"^T dir-inside 0$") and has(out, r"^T deleteseq-own DONE$")
            and not os.path.exists(os.path.join(ACCT, "mine-to-delete.txt")), "output=%r" % (out,))
        if os_on:
            row("%s: OPENSEQ and OPENPATH of a path outside the account work" % label,
                has(out, r"^T openseq-outside OPENED$") and has(out, r"^T openpath-outside OPENED$"), "output=%r" % (out,))
            row("%s: DIR() lists the directory outside (2 entries) and DELETESEQ removes a file outside" % label,
                has(out, r"^T dir-outside 2 0$") and has(out, r"^T deleteseq-outside DONE$") and not os.path.exists(os.path.join(OUT, "victim.txt")),
                "output=%r" % (out,))
        else:
            row("%s: OPENSEQ and OPENPATH outside the account are refused (ELSE 3035)" % label,
                has(out, r"^T openseq-outside REFUSED 3035$") and has(out, r"^T openpath-outside REFUSED 3035$"), "output=%r" % (out,))
            row("%s: DIR() outside gives nothing, status 3035, and DELETESEQ outside is refused (ELSE 3035): the file is still there" % label,
                has(out, r"^T dir-outside 0 3035$") and has(out, r"^T deleteseq-outside ELSE 3035$") and os.path.exists(os.path.join(OUT, "victim.txt")),
                "output=%r exists=%s" % (out, os.path.exists(os.path.join(OUT, "victim.txt"))))

        # D. OPENTEMP, DIGEST, OSPATH keys
        prog("ogmore", [
            "crt 'T begin'",
            "opentemp '%s/zztmpout' to f3 then" % OUT,
            "   crt 'T opentemp-outside OPENED'",
            "   close f3",
            "end else",
            "   crt 'T opentemp-outside REFUSED ':status()",
            "end",
            "opentemp 'zztmpin' to f4 then",
            "   crt 'T opentemp-inside OPENED'",
            "   close f4",
            "end else",
            "   crt 'T opentemp-inside REFUSED ':status()",
            "end",
            "d = digest('%s/existing.txt', 1, 'sha256')" % OUT,
            "crt 'T digest-outside ':status():' ':(len(d) > 0)",
            "d = digest('inside.txt', 1, 'sha256')",
            "crt 'T digest-inside ':status():' ':(len(d) > 0)",
            "e = ospath('%s/existing.txt', 2)" % OUT,
            "crt 'T ospath-exists-outside ':e:' ':status()",
            "m = ospath('%s/mk', 13)" % OUT,
            "crt 'T ospath-mkdir-outside ':m:' ':status()",
            "crt 'T end'",
        ])
        out = session(["BASIC bp ogmore", "RUN bp ogmore"])
        if not compiled(out) or not has(out, r"^T end$"):
            row("%s: the OPENTEMP / DIGEST / OSPATH probe compiled and ran to its end" % label, False, "output=%r" % (out[-5:],))
        else:
            row("%s: OPENTEMP and DIGEST of a name inside the account work whatever the switch says (controls)" % label,
                has(out, r"^T opentemp-inside OPENED$") and has(out, r"^T digest-inside 0 1$") and not os.path.exists(os.path.join(ACCT, "zztmpin")),
                "output=%r" % (out,))
            if os_on:
                row("%s: OPENTEMP outside works (and leaves nothing: it goes at close), DIGEST of an outside file works, OSPATH exists/mkdir work" % label,
                    has(out, r"^T opentemp-outside OPENED$") and has(out, r"^T digest-outside 0 1$") and has(out, r"^T ospath-exists-outside 1 0$")
                    and os.path.isdir(os.path.join(OUT, "mk")) and not os.path.exists(os.path.join(OUT, "zztmpout")), "output=%r" % (out,))
            else:
                row("%s: OPENTEMP outside is refused (ELSE 3035), DIGEST of an outside file gives nothing with status 3035, OSPATH exists says false" % label,
                    has(out, r"^T opentemp-outside REFUSED 3035$") and has(out, r"^T digest-outside 3035 0$") and has(out, r"^T ospath-exists-outside 0 3035$")
                    and not os.path.exists(os.path.join(OUT, "zztmpout")), "output=%r" % (out,))
                row("%s: OSPATH makes no directory outside the account (status 3035, nothing on the disk)" % label,
                    has(out, r"^T ospath-mkdir-outside 0 3035$") and not os.path.exists(os.path.join(OUT, "mk")), "output=%r" % (out,))

        # E. the print unit's pathname: SETPTR ... AS PATHNAME, SETPU, and the $hold marker that tries to climb out
        prog("ogprint", [
            "crt 'T print-begin'",
            "setpu 1, 1, 3",
            "setpu 11, 1, '%s/prt.out'" % OUT,
            "print on 1 'T printed-line-from-setpu'",
            "printer close on 1",
            "crt 'T print-end'",
        ])
        prog("oghold", [
            "crt 'T hold-begin'",
            "setpu 1, 1, 3",
            "setpu 11, 1, '$hold ../../../zzoutside/hold.out'",
            "print on 1 'T printed-via-hold-marker'",
            "printer close on 1",
            "crt 'T hold-end'",
        ])
        out = session(["BASIC bp ogprint oghold", "RUN bp ogprint"])
        out2 = session(["RUN bp oghold", "SETPTR 1,80,60,0,0,3,AS PATHNAME %s/tcl.prt,BRIEF" % OUT])
        if os_on:
            row("%s: SETPU prints into a file outside the account, and so does a '$hold ../..' name (it holds os)" % label,
                os.path.exists(os.path.join(OUT, "prt.out")) and os.path.exists(os.path.join(OUT, "hold.out")) and has(out, r"^T print-end$")
                and has(out2, r"^T hold-end$"), "output=%r %r" % (out, out2))
            row("%s: SETPTR ... AS PATHNAME outside is accepted (no 'has no OS access')" % label, not has(out2, "has no OS access"), "output=%r" % (out2,))
        else:
            row("%s: SETPU cannot print into a file outside the account (refused at print time, no file, the program stopped)" % label,
                has(out, "has no OS access") and not os.path.exists(os.path.join(OUT, "prt.out")) and not has(out, r"^T print-end$"), "output=%r" % (out,))
            row("%s: a '$hold ../../..' print name does not climb out of the account (refused, no file, the program stopped)" % label,
                has(out2, "has no OS access") and not os.path.exists(os.path.join(OUT, "hold.out")) and not has(out2, r"^T hold-end$"), "output=%r" % (out2,))
            row("%s: SETPTR ... AS PATHNAME outside the account is refused (11180)" % label,
                sum(1 for ln in out2 if "has no OS access" in ln) >= 2, "output=%r" % (out2,))

        # F. K$PATH.OK, the question an internal program asks for the user
        out = session(["zzkp"])
        if os_on:
            row("%s: K$PATH.OK answers yes for every path (the account holds os)" % label,
                has(out, r"^KP outside=1 inside=1 dotdot=1 empty=0$"), "output=%r" % (out,))
        else:
            row("%s: K$PATH.OK: outside 0, inside 1, a '..' that climbs out 0, a null name 0" % label,
                has(out, r"^KP outside=0 inside=1 dotdot=0 empty=0$"), "output=%r" % (out,))
        row("%s: an internal program that opens a file for itself is trusted by the kernel (it must ask K$PATH.OK for the user)" % label,
            has(out, r"^KP internal-openseq-outside OK$"), "output=%r" % (out,))

        # G. a VOC pointer is a way to name a file: the F-pointer at /etc written into sduser's VOC
        prog("ogptr", [
            "open 'zzptr' to v then",
            "   crt 'T pointer-outside OPENED'",
            "   close v",
            "end else",
            "   crt 'T pointer-outside REFUSED ':status()",
            "end",
            "open 'syscom' to w then",
            "   crt 'T stock-pointer OPENED'",
            "   close w",
            "end else",
            "   crt 'T stock-pointer REFUSED ':status()",
            "end",
            "open 'dict', 'voc' to dv then",
            "   crt 'T voc-dictionary OPENED'",
            "   close dv",
            "end else",
            "   crt 'T voc-dictionary REFUSED ':status()",
            "end",
            "crt 'T end'",
        ])
        out = session(["BASIC bp ogptr", "RUN bp ogptr"])
        row("%s: a stock VOC pointer still opens (controls: syscom)" % label, has(out, r"^T stock-pointer OPENED$"), "output=%r" % (out,))
        row("%s: the VOC's own dictionary still opens (control: the dictionaries are SD's files, not a path the account names)" % label,
            has(out, r"^T voc-dictionary OPENED$"), "output=%r" % (out,))
        if os_on:
            row("%s: an F-pointer at a directory outside the account opens (it holds os)" % label, has(out, r"^T pointer-outside OPENED$"), "output=%r" % (out,))
        else:
            row("%s: an F-pointer at a directory outside the account is refused (3035)" % label, has(out, r"^T pointer-outside REFUSED 3035$"), "output=%r" % (out,))

        # H0. the embedded Python: starting it and running code in it ask the ACCOUNT (the PY_ wrappers are $internal)
        prog("ogpy", [
            "deffun PY_INITIALIZE() calling '!PY_INITIALIZE'",
            "deffun PY_RUNSTRING(s) calling '!PY_RUNSTRING'",
            "crt 'T py-begin'",
            "r1 = py_initialize()",
            "crt 'T py-init ':r1:' st=':status()",
            "r2 = py_runstring(\"open('%s/py.sentinel', 'w').write('x')\")" % OUT,
            "crt 'T py-run ':r2:' st=':status()",
            "crt 'T py-end'",
        ])
        clean(os.path.join(OUT, "py.sentinel"))
        out = session(["BASIC bp ogpy", "RUN bp ogpy"])
        if not compiled(out) or not has(out, r"^T py-end$"):
            row("%s: the Python probe compiled and ran to its end" % label, False, "output=%r" % (out[-5:],))
        elif os_on:
            row("%s: Python starts and runs code (py_initialize 0, py_runstring 0, the sentinel it wrote is on the disk)" % label,
                has(out, r"^T py-init 0 st=") and has(out, r"^T py-run 0 st=") and os.path.exists(os.path.join(OUT, "py.sentinel")), "output=%r" % (out,))
        else:
            row("%s: Python will not start and will not run code (py_initialize and py_runstring do not answer 0; no sentinel on the disk)" % label,
                has(out, r"^T py-init (?!0 st=)") and has(out, r"^T py-run (?!0 st=)") and not os.path.exists(os.path.join(OUT, "py.sentinel")),
                "output=%r" % (out,))

    # --- H. the administrator passes with both OFF ----------------------------------------------------------------------------
    say("\n=== the administrator (ADMIN typed) with both switches OFF ===========================================================")
    reg_state(False, False)
    for junk in ("sh.sentinel", "osx.sentinel"):
        clean(os.path.join(OUT, junk))
    prog("ogosx", ["crt 'T osx-begin'", "os.execute 'touch %s/osx.sentinel'" % OUT, "crt 'T osx-end'"])
    out = session(["BASIC bp ogosx", "zzkf", "SH touch %s/sh.sentinel" % OUT, "RUN bp ogosx"], unlock=True)
    row("an administrator session passes the gate with both OFF: SH ran, OS.EXECUTE ran (both sentinels), the kernel says admin=1 sh=0 osx=0",
        has(out, r"^KFLAGS admin=1 sh=0 osx=0$") and os.path.exists(os.path.join(OUT, "sh.sentinel")) and os.path.exists(os.path.join(OUT, "osx.sentinel")),
        "output=%r" % (out[:6],))

    # --- I. the verb --------------------------------------------------------------------------------------------------------
    say("\n=== SET.OS.ACCESS ====================================================================================================")
    reg_state(False, False)
    out = session(["SET.OS.ACCESS SH ON"])
    row("an ordinary session is refused (2001, 'Command requires administrator privileges') and the register is unchanged",
        has(out, r"^Command requires administrator privileges$") and reg_fields() == ("", ""), "output=%r fields=%r" % (out, reg_fields()))
    out = session(["SET.OS.ACCESS"], unlock=True)
    row("no argument shows the state (10102) and changes nothing", has(out, r"^Account sduser has SH no, OS\.EXECUTE no$") and reg_fields() == ("", ""),
        "output=%r fields=%r" % (out, reg_fields()))
    out = session(["SET.OS.ACCESS SH ON"], unlock=True)
    row("SH ON as the administrator: 'Account sduser has SH yes, OS.EXECUTE no', field 7 is yes and field 8 is not",
        has(out, r"^Account sduser has SH yes, OS\.EXECUTE no$") and reg_fields() == ("yes", ""), "output=%r fields=%r" % (out, reg_fields()))
    out = session(["SET.OS.ACCESS SH ON"], unlock=True)
    row("SH ON again says it already had that access (10080) and writes nothing", has(out, r"already had that access; nothing changed"), "output=%r" % (out,))
    out = session(["zzkf"])
    row("the change reaches the NEXT sign-on: a new plain session holds sh=1 osx=0", has(out, r"^KFLAGS admin=0 sh=1 osx=0$"), "output=%r" % (out,))
    out = session(["SET.OS.ACCESS OS ON"], unlock=True)
    row("OS ON: both yes, independently of SH", has(out, r"^Account sduser has SH yes, OS\.EXECUTE yes$") and reg_fields() == ("yes", "yes"), "output=%r fields=%r" % (out, reg_fields()))
    out = session(["SET.OS.ACCESS SH OFF"], unlock=True)
    row("SH OFF leaves OS as it was", has(out, r"^Account sduser has SH no, OS\.EXECUTE yes$") and reg_fields() == ("no", "yes"), "output=%r fields=%r" % (out, reg_fields()))
    out = session(["SET.OS.ACCESS OS OFF"], unlock=True)
    row("OS OFF: both off (a withdrawn switch is withdrawn at the next sign-on)", has(out, r"^Account sduser has SH no, OS\.EXECUTE no$") and reg_fields() == ("no", "no"),
        "output=%r fields=%r" % (out, reg_fields()))
    before = reg_fields()
    out = session(["SET.OS.ACCESS SH ON OS ON", "SET.OS.ACCESS SH", "SET.OS.ACCESS NET ON", "SET.OS.ACCESS SH MAYBE"], unlock=True)
    row("two actions in one command, a word without on/off, an unknown word and a bad on/off are each the syntax message (11926); the register is unchanged",
        sum(1 for ln in out if ln.startswith("Syntax: set.os.access")) == 4 and reg_fields() == before, "output=%r fields=%r" % (out, reg_fields()))
    out = session(["set.os.access sh on", "SET.OS.ACCESS OS On"], unlock=True)
    row("the words are case blind (lower and upper case both work)", reg_fields() == ("yes", "yes"), "output=%r fields=%r" % (out, reg_fields()))
    reg_state(False, False)

    shutil.rmtree(OUT, ignore_errors=True)
    for p in ("ogroute", "ogosx", "ogmore", "ogprint", "oghold", "ogptr", "ogpy"):
        for d in ("bp", "bp.out"):
            q = os.path.join(ACCT, d, p)
            if os.path.exists(q):
                os.remove(q)
    say("\nsandbox-osgate: %d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 and passed > 0 else 1)


if __name__ == "__main__":
    main()
