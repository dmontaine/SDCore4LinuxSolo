#!/usr/bin/env python3
#
# sandbox-osgate.py - the Solo OS-access switch (SH and OS) RUN on a private SD Core Solo for Linux: ordinary sessions of the one
#                     account, sduser, that refuse, run, and leave a sentinel on the disk as evidence.  Solo's copy of the idea of
#                     SD Core's sandbox-gates.py (S.63); written FIRST, before the switch existed, and run red on a423ed5.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-osgate.py <dir> [--build] [--only=gate,netdirs,lanes]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo).  With --build it is built first from THIS tree
# (it must be empty or absent).  SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop
# the sandbox afterwards with sandbox-fromtree.py <dir> stop.
#
# --only picks sections (no --only: all three).  The controls (a plain session, the register OFF) and the probes' setup always run.
#   gate     the four states, the administrator and SET.OS.ACCESS (the suite as it was before 17 Nov 26)
#   netdirs  sd.conf's NETDIRS with the switch OFF: it RESTARTS the sandbox's SD several times and puts sd.conf back at the end; it makes
#            and removes four directories beside <dir> (<dir>-ndA, <dir>-ndAx, <dir>-ndB, <dir>-NDA)
#   lanes    one row each for the S.62 round-1 fixes no other Solo suite drives: RENAME.FILE, .S, the denied-verb fold, sdtic with no -p,
#            SETTINGS.REPORT with $cred unreadable, SET.CONFIG's renumbered messages
#
# START-HISTORY:
# 20 Oct 26 dm  Written for the Solo OS switch (owner, 20 Oct: two words like Core, SET.OS.ACCESS, the installer asks).
# 17 Nov 26 dm  S.62 (P-1225, P-1226, P-1228): row B2 in the two SH-on states - sd-solo --version from SH refuses with "SD is already running in this
#               session" (op_sh.c's SD_SESSION=1, sd.c's test before any option), the control an SH echo that runs and shows SD_SESSION=1.
# 17 Nov 26 dm  S.62 round 1, second test lane: --only (gate, netdirs, lanes); section netdirs (NETDIRS, LS3-kernel's twelve rows and their controls,
#               the sandbox restarted on a rewritten sd.conf) and section lanes (cname, .S, the denied-verb fold, sdtic, settings_os, setconfig).
# 17 Nov 26 dm  S.62 L4 S1: row LR2 - $cred mode 000 (it opens, the read of $global fails) makes [mode] say the record could not be read, not "not managed".
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
import hashlib
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
SECTIONS = ("gate", "netdirs", "lanes")
ONLY = []


def want(name):
    return not ONLY or name in ONLY


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
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    if a.only:
        ONLY[:] = [w.strip() for w in a.only.split(",") if w.strip()]
        bad = [w for w in ONLY if w not in SECTIONS]
        if bad or not ONLY:
            bail("--only takes %s; not %r" % (",".join(SECTIONS), a.only))
    say("sandbox-osgate: sections %s" % ",".join(ONLY or SECTIONS))
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

    states = (("OFF", False, False), ("SH only", True, False), ("OS only", False, True), ("BOTH", True, True)) if want("gate") else ()
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

        # B. the SH verb (9 Nov 26, Solo carry 22: "!" was removed with SD Core's S.87; it is no longer a verb)
        out = session(["SH touch %s/sh.sentinel" % OUT, "SH touch own.sentinel"])
        refusals = sum(1 for ln in out if re.search(r"is not permitted to use the operating system shell$", ln))
        if sh_on:
            row("%s: SH runs: both sentinels are on the disk and nothing was refused" % label,
                os.path.exists(os.path.join(OUT, "sh.sentinel")) and refusals == 0
                and os.path.exists(os.path.join(ACCT, "own.sentinel")), "output=%r" % (out,))
        else:
            row("%s: SH is refused (10053, once each, two commands): no sentinel on the disk, in the account either" % label,
                refusals == 2 and not os.path.exists(os.path.join(OUT, "sh.sentinel"))
                and not os.path.exists(os.path.join(ACCT, "own.sentinel")), "output=%r" % (out,))

        # B2. one SD per session (17 Nov 26, S.62 P-1228): the shell SH starts carries SD_SESSION, and sd-solo started from it refuses before
        #     it reads an option, --version included.  The control is the same shell's echo, which also shows the variable.
        if sh_on:
            # (SD's SH refuses a command holding '$' - "Error 2 executing operating system command" - so the variable is read with printenv)
            out = session(["SH %s --version" % os.path.join(SYS, "bin", "sd-solo"), "SH echo zzshok", "SH printenv SD_SESSION"])
            row("%s: sd-solo --version from SH says 'SD is already running in this session' and prints no version; the control SH echo runs and "
                "the shell's SD_SESSION is 1" % label,
                has(out, r"^SD is already running in this session - type exit to return to it\.$") and has(out, r"^zzshok$") and has(out, r"^1$")
                and not any("Version" in ln for ln in out), "output=%r" % (out,))

        # C-D. OS.EXECUTE and every route to an OS path, in one program (a T line each)
        prog("ogroute", [
            "crt 'T begin'",
            "openseq '%s/existing.txt' to f1 then" % OUT,
            "   crt 'T openseq-outside OPENED'",
            "   close f1",
            "end else",
            "   crt 'T openseq-outside REFUSED ':status()",
            "end",
            "openseq 'inside.txt' to f2 then",
            "   crt 'T openseq-inside OPENED'",
            "   close f2",
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
                has(out, "sduser has no OS access") and not has(out, "%1") and not os.path.exists(os.path.join(OUT, "prt.out")) and not has(out, r"^T print-end$"),
                "output=%r" % (out,))
            row("%s: a '$hold ../../..' print name does not climb out of the account (refused, no file, the program stopped)" % label,
                has(out2, "sduser has no OS access") and not has(out2, "%1") and not os.path.exists(os.path.join(OUT, "hold.out")) and not has(out2, r"^T hold-end$"),
                "output=%r" % (out2,))
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

    if want("gate"):
        part_admin_and_verb()
    if want("netdirs"):
        part_netdirs()
    if want("lanes"):
        part_lanes()
    reg_state(False, False)

    shutil.rmtree(OUT, ignore_errors=True)
    for p in ("ogroute", "ogosx", "ogmore", "ogprint", "oghold", "ogptr", "ogpy", "ognd", "ogndx", "ogndv", "zzids"):
        for d in ("bp", "bp.out"):
            q = os.path.join(ACCT, d, p)
            if os.path.exists(q):
                os.remove(q)
    say("\nsandbox-osgate: %d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 and passed > 0 else 1)


def part_admin_and_verb():
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


# --------------------------------------------------------------------------------------------------------------------------------
# helpers of the netdirs and lanes sections (17 Nov 26)

def tool(step):
    r = subprocess.run([sys.executable, TOOL, BOX, step], capture_output=True, text=True, errors="replace", timeout=180)
    return r.returncode, ANSI.sub("", r.stdout + r.stderr)


def restart(label):
    """Stop the sandbox's SD and start it again: Solo reads sd.conf at sd-solo -start only.  True when it is running again."""
    rc1, o1 = tool("stop")
    rc2, o2 = tool("start")
    said = " / ".join(ln.strip() for ln in (o1 + o2).splitlines() if "keys" in ln)
    say("    [restart: %s] stop rc=%d, start rc=%d: %s" % (label, rc1, rc2, said))
    return rc2 == 0


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_probe(tag, path):
    return ["openseq '%s' to f then" % path,
            "   readseq ln from f then crt 'T %s READ ':ln else crt 'T %s EMPTY'" % (tag, tag),
            "   close f",
            "end else",
            "   st = status()",
            "   crt 'T %s REFUSED ':st" % tag,
            "   if st = 0 then close f",
            "end"]


def write_probe(tag, path):
    return ["ok = 1",
            "openseq '%s' to f else" % path,
            "   st = status()",
            "   if st # 0 then",
            "      ok = 0",
            "      crt 'T %s REFUSED ':st" % tag,
            "   end",
            "end",
            "if ok then",
            "   writeseq 'NDWRITE-%s' to f else crt 'T %s WRITESEQ-FAILED ':status()" % (tag, tag),
            "   close f",
            "   crt 'T %s WROTE'" % tag,
            "end"]


def open_probe(tag, path):
    """Opens and tries to write.  For a file under a VOC the kernel opens it READ ONLY (Solo carry 19, op_seqio.c), so the OPENSEQ
    succeeds and the WRITESEQ is the refusal; the caller also compares the file's bytes before and after."""
    return ["openseq '%s' to f then" % path,
            "   writeseq 'NDWRITE-%s' to f then crt 'T %s WROTE' else crt 'T %s WRITE-REFUSED ':status()" % (tag, tag, tag),
            "   close f",
            "end else",
            "   st = status()",
            "   crt 'T %s REFUSED ':st" % tag,
            "   if st = 0 then close f",
            "end"]


def tval(out, tag):
    for ln in out:
        m = re.match(r"^T %s (.*)$" % re.escape(tag), ln)
        if m:
            return m.group(1)
    return None


# --------------------------------------------------------------------------------------------------------------------------------
# NETDIRS (17 Nov 26, S.62 round 1; the rows LS3-kernel listed).  The switch is OFF (fields 7 and 8 blank) unless a row says otherwise.
# sd.conf is rewritten through <dir>/sd.conf and SD restarted, because Solo reads it at sd-solo -start only.  Evidence: what the probe's
# OPENSEQ answered (READ with the file's first line, or REFUSED with STATUS()), the files on the disk, the error log's new lines and
# start.log.  The directories are beside the sandbox, outside the Solo folder (<dir>/sys) and outside sd.conf's directory (<dir>).

def part_netdirs():
    say("\n=== NETDIRS (sd.conf), the OS switch OFF ===========================================================================")
    conf = os.path.join(BOX, "sd.conf")
    with open(conf) as f:
        conf0 = f.read()
    if "NETDIRS" in conf0:
        bail("the sandbox's sd.conf already names NETDIRS: %s" % conf)
    errlog = os.path.join(SYS, "errlog")
    nda, ndax, ndb, ndc, missing = BOX + "-ndA", BOX + "-ndAx", BOX + "-ndB", BOX + "-NDA", BOX + "-ndMissing"
    made = (nda, ndax, ndb, ndc)
    for d in made + (missing,):
        clean(d)
    for d in made:
        os.makedirs(d)
    put(os.path.join(nda, "in.txt"), "NDA-SECRET\n")
    put(os.path.join(ndb, "out.txt"), "NDB-SECRET\n")
    put(os.path.join(ndax, "x.txt"), "NDAX-SECRET\n")
    put(os.path.join(ndc, "c.txt"), "NDCASE-SECRET\n")
    os.symlink(os.path.join(ndb, "out.txt"), os.path.join(nda, "linkout"))
    os.makedirs(OUT, exist_ok=True)
    put(os.path.join(OUT, "ndin.txt"), "SOLO-FOLDER-SECRET\n")
    dotdot = "%s/../%s/out.txt" % (nda, os.path.basename(ndb))
    voc0 = os.path.join(ACCT, "voc", "%0")
    say("    listed-to-be %s, unlisted %s, look-alike %s, other case %s, never made %s" % (nda, ndb, ndax, ndc, missing))

    def setconf(line):
        put(conf, conf0 + ("" if conf0.endswith("\n") else "\n") + ("" if line is None else line + "\n"))
        say("    sd.conf: %s" % ("(as delivered: no NETDIRS line)" if line is None else (line if len(line) < 120 else line[:100] + "... (%d characters)" % len(line))))

    prog("ognd", ["crt 'T begin'"]
         + read_probe("a", os.path.join(nda, "in.txt")) + read_probe("b", os.path.join(ndb, "out.txt"))
         + read_probe("lnk", os.path.join(nda, "linkout")) + read_probe("dd", dotdot)
         + read_probe("case", os.path.join(ndc, "c.txt")) + read_probe("ax", os.path.join(ndax, "x.txt"))
         + read_probe("solo", os.path.join(OUT, "ndin.txt"))
         + write_probe("wa", os.path.join(nda, "new.txt")) + write_probe("wb", os.path.join(ndb, "new.txt"))
         + ["crt 'T end'"])
    prog("ogndx", ["crt 'T osx-begin'", "os.execute 'touch %s/osx.sentinel'" % nda, "crt 'T osx-end'"])
    # The VOC write is a program of its own, run ONLY with the switch OFF: with OS ON the kernel lets the account write its own VOC
    # by pathname (edit_os_path_refusal() passes USR_OS_EXEC), and a probe run then overwrote voc/%0 (17 Nov 26, this lane's 2nd run).
    prog("ogndv", open_probe("voc", "voc/%0") + ["crt 'T vend'"])

    def probe(first=False):
        for p in (os.path.join(nda, "new.txt"), os.path.join(ndb, "new.txt")):
            clean(p)
        out = session((["BASIC bp ognd ogndx ogndv"] if first else []) + ["RUN bp ognd"])
        return out

    def ran(out, label):
        if not has(out, r"^T end$"):
            row("%s: the NETDIRS probe ran to its end" % label, False, "output=%r" % (out[-8:],))
            return False
        return True

    try:
        reg_state(False, False)
        # N0: the control - as delivered (no line) a directory outside the account is refused
        out = probe(first=True)
        if not compiled(out, 3):
            row("netdirs: the probes ognd, ogndx and ogndv compile", False, "output=%r" % (out[-6:],))
            return
        if ran(out, "N0"):
            row("N0 control: with no NETDIRS line (as delivered) and the switch OFF, a file in the directory-to-be-listed is refused (3035)",
                tval(out, "a") == "REFUSED 3035" and tval(out, "b") == "REFUSED 3035", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))

        # N1-N9: NETDIRS=<ndA>
        setconf("NETDIRS=" + nda)
        if not restart("NETDIRS=ndA"):
            row("N1: SD starts with NETDIRS=%s" % nda, False, "the sandbox did not start again")
            return
        out = probe()
        if ran(out, "N1"):
            row("N1: a file in the listed directory is read (READ NDA-SECRET) and one in an unlisted directory is refused (3035)",
                tval(out, "a") == "READ NDA-SECRET" and tval(out, "b") == "REFUSED 3035", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))
            wa = os.path.join(nda, "new.txt")
            body = open(wa).read() if os.path.isfile(wa) else None
            row("N2: a write in the listed directory makes the file on the disk ('NDWRITE-wa'); a write in the unlisted one is refused (3035) and makes nothing",
                tval(out, "wa") == "WROTE" and (body or "").strip() == "NDWRITE-wa" and tval(out, "wb") == "REFUSED 3035"
                and not os.path.lexists(os.path.join(ndb, "new.txt")),
                "wa=%r disk=%r wb=%r" % (tval(out, "wa"), body, tval(out, "wb")))
            row("N3: a link in the listed directory that leads out of it is refused (3035); control: the link resolves to the unlisted file, which exists",
                tval(out, "lnk") == "REFUSED 3035" and os.path.realpath(os.path.join(nda, "linkout")) == os.path.realpath(os.path.join(ndb, "out.txt"))
                and os.path.isfile(os.path.join(ndb, "out.txt")), "lnk=%r" % tval(out, "lnk"))
            row("N4: <listed>/../<unlisted>/out.txt is refused (3035); control: that path names an existing file",
                tval(out, "dd") == "REFUSED 3035" and os.path.isfile(dotdot), "dd=%r path=%s" % (tval(out, "dd"), dotdot))
            row("N5: the listed name in another case (%s) is refused (3035); control: it is a different existing directory on this disk" % os.path.basename(ndc),
                tval(out, "case") == "REFUSED 3035" and os.path.isdir(ndc) and not os.path.samefile(ndc, nda), "case=%r" % tval(out, "case"))
            row("N6: %s is not inside %s: refused (3035); control: it exists" % (os.path.basename(ndax), os.path.basename(nda)),
                tval(out, "ax") == "REFUSED 3035" and os.path.isdir(ndax), "ax=%r" % tval(out, "ax"))
            row("N7: a file of the Solo folder outside the account is still refused (3035)", tval(out, "solo") == "REFUSED 3035", "solo=%r" % tval(out, "solo"))
        if reg_fields() != ("", ""):
            row("N8: the VOC write probe is run only with both switches OFF", False, "fields=%r" % (reg_fields(),))
        else:
            keep = {}
            for leaf in ("%0", "%1"):
                with open(os.path.join(ACCT, "voc", leaf), "rb") as f:
                    keep[leaf] = f.read()
            outv = session(["RUN bp ogndv"])
            # The session itself may change the VOC's file on the way (a whole-file hash, taken at the start of the section, differed
            # after a refused write on this lane's third run), so the evidence is where the write would land: the file's first bytes,
            # and no NDWRITE anywhere in it.
            with open(voc0, "rb") as f:
                now = f.read()
            same = now[:64] == keep["%0"][:64] and b"NDWRITE" not in now
            row("N8: a write to the account's own voc/%0 is still refused (OPENSEQ opens it read only, the WRITESEQ takes its ELSE, or the OPENSEQ is refused) "
                "and nothing was written (the file's first 64 bytes as before the probe, no NDWRITE in it)",
                has(outv, r"^T vend$") and re.match(r"^(WRITE-REFUSED -?\d+|REFUSED -?[1-9]\d*)$", tval(outv, "voc") or "") is not None and same,
                "voc=%r same=%s output=%r" % (tval(outv, "voc"), same, outv[-4:]))
            if not same:
                for leaf, data in keep.items():
                    with open(os.path.join(ACCT, "voc", leaf), "wb") as f:
                        f.write(data)
                say("    voc/%0 and voc/%1 put back from the copy taken before the probe")
        clean(os.path.join(nda, "sh.sentinel"))
        clean(os.path.join(nda, "osx.sentinel"))
        out = session(["SH touch %s/sh.sentinel" % nda, "RUN bp ogndx"])
        row("N9: SH and OS.EXECUTE are still refused with the listed directory as their target (10053, 10054): no sentinel in it",
            sum(1 for ln in out if re.search(r"is not permitted to use the operating system shell$", ln)) == 1
            and has(out, r"is not permitted to use OS\.EXECUTE") and not has(out, r"^T osx-end$")
            and not os.path.exists(os.path.join(nda, "sh.sentinel")) and not os.path.exists(os.path.join(nda, "osx.sentinel")), "output=%r" % (out,))

        # N13: the control - with the switch ON nothing changes: the unlisted directory is read as before
        reg_state(False, True)
        out = probe()
        if ran(out, "N13"):
            row("N13 control: the switch ON reads both the listed and the unlisted directory (NETDIRS changes nothing for it)",
                tval(out, "a") == "READ NDA-SECRET" and tval(out, "b") == "READ NDB-SECRET", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))
        reg_state(False, False)

        # N10: a change while SD runs reaches nothing until the next start
        setconf("NETDIRS=" + ndb)
        out = probe()
        if ran(out, "N10a"):
            row("N10a: sd.conf changed to NETDIRS=ndB WITHOUT a restart: a new session still reads ndA and is still refused ndB (3035)",
                tval(out, "a") == "READ NDA-SECRET" and tval(out, "b") == "REFUSED 3035", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))
        if not restart("NETDIRS=ndB"):
            row("N10b: SD starts with NETDIRS=ndB", False, "the sandbox did not start again")
            return
        out = probe()
        if ran(out, "N10b"):
            row("N10b: after the restart ndB is read and ndA is refused (3035)",
                tval(out, "b") == "READ NDB-SECRET" and tval(out, "a") == "REFUSED 3035", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))

        # N11: entries SD must ignore, each named in the error log at the start
        bad = (("rel/dir", "it is not an absolute path"), ("/", "it is the root directory"), (SYS, "the SD Core Solo folder"),
               (os.path.join(SYS, "user_accounts"), "the SD Core Solo folder"), (missing, "it is not an existing directory"))
        setconf("NETDIRS=" + ";".join(e for e, _ in bad))
        size0 = os.path.getsize(errlog) if os.path.exists(errlog) else 0
        started = restart("bad entries")
        with open(errlog, "rb") as f:
            f.seek(size0)
            new = f.read().decode("ascii", "replace").splitlines()
        nd_lines = [ln for ln in new if "NETDIRS:" in ln]
        say("    error log, new NETDIRS lines: %r" % (nd_lines,))
        each = []
        for e, why in bad:
            hits = [ln for ln in nd_lines if ("NETDIRS: %s is ignored - " % e) in ln]
            each.append(len(hits) == 1 and why in hits[0])
        row("N11a: SD starts with five bad entries (relative, '/', the Solo folder, its user_accounts, a missing directory) and the error log names "
            "each once, with its reason", started and all(each) and len(nd_lines) == len(bad), "per entry %r" % (each,))
        if started:
            out = probe()
            if ran(out, "N11b"):
                row("N11b: those entries admit nothing: ndA, ndB (which '/' would hold) and the Solo folder's file (which the folder entry would) are refused (3035)",
                    tval(out, "a") == "REFUSED 3035" and tval(out, "b") == "REFUSED 3035" and tval(out, "solo") == "REFUSED 3035",
                    "a=%r b=%r solo=%r" % (tval(out, "a"), tval(out, "b"), tval(out, "solo")))

        # N12: the length limit, 191 accepted and 192 refused by name at the start
        v191 = nda + ";/" + "y" * (191 - len(nda) - 2)
        setconf("NETDIRS=" + v191)
        ok191 = restart("191 characters")
        out = probe() if ok191 else []
        row("N12a control: a value of exactly 191 characters starts SD and its first entry works (ndA read)",
            len(v191) == 191 and ok191 and tval(out, "a") == "READ NDA-SECRET", "len=%d started=%s a=%r" % (len(v191), ok191, tval(out, "a")))
        setconf("NETDIRS=" + v191 + "y")
        ok192 = restart("192 characters")
        try:
            with open(os.path.join(BOX, "start.log")) as f:
                slog = f.read()
        except OSError:
            slog = ""
        row("N12b: a value of 192 characters stops the start with 'NETDIRS value is longer than 191 characters.' and SD is not running",
            not ok192 and "NETDIRS value is longer than 191 characters." in slog, "started=%s start.log=%r" % (ok192, slog[-300:]))

        # N14: an empty list refuses as the delivered system does
        setconf("NETDIRS=")
        if not restart("NETDIRS= (empty)"):
            row("N14: SD starts with an empty NETDIRS", False, "the sandbox did not start again")
            return
        out = probe()
        if ran(out, "N14"):
            row("N14 control: NETDIRS= (empty) admits nothing: ndA and ndB are refused (3035)",
                tval(out, "a") == "REFUSED 3035" and tval(out, "b") == "REFUSED 3035", "a=%r b=%r" % (tval(out, "a"), tval(out, "b")))
    finally:
        reg_state(False, False)
        put(conf, conf0)
        back = restart("sd.conf as it was")
        say("    sd.conf put back (%s), SD %s" % ("identical" if open(conf).read() == conf0 else "DIFFERENT", "running" if back else "NOT RUNNING"))
        for d in made + (missing,):
            clean(d)
        clean(os.path.join(OUT, "ndin.txt"))


# --------------------------------------------------------------------------------------------------------------------------------
# lanes (17 Nov 26, S.62 round 1): one row each for a fix no other Solo suite drives.

def part_lanes():
    say("\n=== the S.62 round-1 fixes (cname, .S, the denied-verb fold, sdtic, settings_os, setconfig) ===========================")
    reg_state(False, False)
    prog("zzids", [
        "open 'voc' to v else stop 'T no voc'",
        "select v",
        "loop",
        "   readnext id else exit",
        "   if downcase(id[1,4]) = 'zzcn' or downcase(id[1,4]) = 'zzsd' or downcase(id[1,4]) = 'zzdv' then",
        "      read r from v, id else r = ''",
        "      crt 'ID ':id:' ':r<1>:' ':r<2>:' ':r<3>",
        "   end",
        "repeat",
        "crt 'T end'"])

    # LC: CNAME - the new name is stored lower case; a case-only rename and a fold twin are refused (6151).  What an earlier run left is
    # removed first (DELETE.FILE asks "OK to delete DATA portion ...", answered Y; a Y with no question is an unknown verb, harmless).
    def tidy():
        session(["DELETE VOC zzsdot", "DELETE.FILE ZZCNC", "Y", "DELETE.FILE ZZCNB", "Y", "DELETE.FILE ZZCNA", "Y"], unlock=True)
    tidy()
    out = session(["BASIC bp zzids", "CREATE.FILE ZZCNA", "CREATE.FILE ZZCNB", "CNAME ZZCNA TO ZZCNC", "CNAME zzcnc TO ZZCNC", "CNAME ZZCNB TO ZZCNC",
                   "RUN bp zzids"], unlock=True)
    ids = [ln for ln in out if ln.startswith("ID ")]
    say("    VOC ids: %r" % (ids,))
    if not (compiled(out) and any(re.match(r"^ID zzcnb F", ln) for ln in ids)):
        row("LC0: the id lister compiled and CREATE.FILE made zzcnb (the fixture)", False, "output=%r" % (out,))
    else:
        row("LC1: CNAME ZZCNA TO ZZCNC stores the new name lower case (VOC id zzcnc, type F; no ZZCNC, no zzcna)",
            any(re.match(r"^ID zzcnc F", ln) for ln in ids) and not any(re.match(r"^ID (ZZCNC|zzcna|ZZCNA)\b", ln) for ln in ids), "ids=%r" % (ids,))
        refused = [ln for ln in out if re.search(r"is already defined in your VOC$", ln)]
        row("LC2: a case-only rename (zzcnc TO ZZCNC) and a fold twin (ZZCNB TO ZZCNC) are each refused with 6151; zzcnb and zzcnc are both still there",
            len(refused) == 2 and sum(1 for ln in ids if re.match(r"^ID zzcnc F", ln)) == 1 and any(re.match(r"^ID zzcnb F", ln) for ln in ids),
            "refusals=%r ids=%r" % (refused, ids))

    # LS: .S - a NEW saved sentence is saved under a lower-case id
    out = session(["WHO", ".S ZZSDOT 1 1", "RUN bp zzids"], unlock=True)
    ids = [ln for ln in out if ln.startswith("ID ")]
    row("LS1: .S ZZSDOT saves the new sentence under the lower-case id zzsdot (type S, holding WHO); no ZZSDOT",
        any(re.match(r"^ID zzsdot S (WHO|who)\b", ln) for ln in ids) and not any(ln.startswith("ID ZZSDOT") for ln in ids), "ids=%r output=%r" % (ids, out[-6:]))
    tidy()

    # LD: the denied-verb check folds field 3 - a VOC record naming $QPROC is denied like LIST's $qproc.  (COUNT is not usable: the
    #     shipped VOC record 'count' is the keyword COUNT, field 1 begins with K.)
    #     22 Nov 26 (S.290): the fixture writes LIST in capitals on purpose - it is now the list of an OLDER install, which CPROC folds as it reads.
    pol = os.path.join(SYS, "solo.policy")
    put(os.path.join(SYS, "bp", "zzdvfix"), "\n".join([
        "$internal",
        "   openpath '%s/voc' to v else crt 'DVFIX no voc' ; stop" % ACCT,
        "   openpath '%s' to p else crt 'DVFIX no policy' ; stop" % pol,
        "   read c from v, 'list' else crt 'DVFIX no list' ; stop",
        "   read x from p, 'denied.verbs' then crt 'DVFIX a denied.verbs record exists' ; stop",
        "   u = c ; u<3> = upcase(c<3>)",
        "   write u to v, 'zzdvu'",
        "   write c to v, 'zzdvl'",
        "   write 'LIST' to p, 'denied.verbs'",
        "   crt 'DVFIX done ':c<1>:' ':c<2>:' ':c<3>:' ':u<3>", "end", ""]))
    put(os.path.join(SYS, "bp", "zzdvundo"), "\n".join([
        "$internal",
        "   openpath '%s/voc' to v else crt 'DVUNDO no voc' ; stop" % ACCT,
        "   openpath '%s' to p else crt 'DVUNDO no policy' ; stop" % pol,
        "   delete v, 'zzdvu'",
        "   delete v, 'zzdvl'",
        "   delete p, 'denied.verbs'",
        "   crt 'DVUNDO done'", "end", ""]))
    fx = internal(["BASIC bp zzdvfix zzdvundo", "RUN bp zzdvfix"])
    if not has(fx, r"^DVFIX done .* \$qproc \$QPROC$"):
        row("LD0: the fixture: LIST on the deny list, zzdvu (LIST's record with field 3 $QPROC) and zzdvl (field 3 as shipped) in the VOC", False, "output=%r" % (fx[-5:],))
    else:
        try:
            out = session(["LIST VOC 'zzdvl'", "ZZDVU VOC 'zzdvl'", "ZZDVL VOC 'zzdvl'", "SORT VOC 'zzdvu'"])
            den = [ln for ln in out if ln == "Command requires administrator privileges"]
            row("LD1: with LIST denied, zzdvu (its program named $QPROC) is denied too, as are LIST and zzdvl (2001 three times, nothing listed by them); "
                "control: SORT, which shares $qproc with another field 4, still runs and lists zzdvu",
                len(den) == 3 and has(out, r"zzdvu") and not has(out, r"zzdvl"), "output=%r" % (out,))
        finally:
            ud = internal(["RUN bp zzdvundo"])
            if not has(ud, r"^DVUNDO done$"):
                row("LD9: the deny list and the two records are taken away again", False, "output=%r" % (ud[-4:],))

    # LT: sdtic run with no -p finds the home's terminfo (it stopped with "Unable to locate SDSYS directory")
    sdtic = os.path.join(SYS, "bin", "sdtic")
    env = {k: v for k, v in os.environ.items() if k != "SD_CONFIG"}
    r1 = subprocess.run([sdtic, "-v", "-i"], cwd="/tmp", env=env, capture_output=True, text=True, errors="replace", timeout=60)
    r2 = subprocess.run([sdtic, "-p" + os.path.join(SYS, "terminfo"), "-i"], cwd="/tmp", env=env, capture_output=True, text=True, errors="replace", timeout=60)
    say("    > %s -v -i   (exit %d, %d lines)   and   %s -p<terminfo> -i   (exit %d, %d lines)" % (sdtic, r1.returncode, len(r1.stdout.splitlines()),
                                                                                              sdtic, r2.returncode, len(r2.stdout.splitlines())))
    idx1 = [ln for ln in r1.stdout.splitlines() if ln.strip() and not ln.startswith("#[") and not ln.startswith("Terminfo directory")]
    idx2 = [ln for ln in r2.stdout.splitlines() if ln.strip() and not ln.startswith("#[")]
    row("LT1: bin/sdtic with no -p (no SD_CONFIG, sd.conf names no SDSYS) uses <home>/terminfo and lists the same index as with -p<home>/terminfo",
        r1.returncode == 0 and "Unable to locate SDSYS directory" not in r1.stdout
        and ("Terminfo directory = %s/terminfo" % os.path.realpath(SYS)) in r1.stdout and len(idx1) > 5 and idx1 == idx2,
        "exit=%d out=%r" % (r1.returncode, r1.stdout[:400]))

    # LR: SETTINGS.REPORT when $cred cannot be read says so instead of "not managed"
    cred = os.path.join(SYS, "$cred")
    mode0 = os.stat(cred).st_mode & 0o7777

    def mode_line(out):
        for i, ln in enumerate(out):
            if ln.strip() == "[mode]" and i + 1 < len(out):
                return out[i + 1].strip()
        return None
    # SETTINGS.REPORT is not a verb of the internal session's account (SDSYS's VOC) and an ADMIN session cannot sign in while $cred is
    # unreadable, so the report's OS half, !settings_os (what changed), is called by an internal program and its lines printed.
    put(os.path.join(SYS, "bp", "zzsetos"), "\n".join([
        "$internal",
        "   call !settings_os(lines, err)",
        "   n = dcount(lines, @fm)",
        "   for i = 1 to n",
        "      crt lines<i>",
        "   next i",
        "   crt 'SETOS end ':n:' err=':err", "end", ""]))
    out = internal(["BASIC bp zzsetos", "RUN bp zzsetos"])
    m0 = mode_line(out) if has(out, r"^SETOS end [1-9]") else None
    # "Cannot be opened" is $cred absent: SD's OPENPATH of a directory file whose mode is 000 SUCCEEDS (only the READ after it fails),
    # which the second test lane of 17 Nov measured; row LR2 (17 Nov, L4 S1) judges what [mode] says then.
    aside = cred + ".zzaside"
    try:
        os.chmod(cred, 0)
        out = internal(["RUN bp zzsetos"])
        m000 = mode_line(out) if has(out, r"^SETOS end [1-9]") else None
        os.chmod(cred, mode0)
        os.rename(cred, aside)
        out = internal(["RUN bp zzsetos"])
        m1 = mode_line(out) if has(out, r"^SETOS end [1-9]") else None
    finally:
        if os.path.lexists(aside) and not os.path.lexists(cred):
            os.rename(aside, cred)
        os.chmod(cred, mode0)
    say("    with $cred present but mode 000, [mode] says %r" % (m000,))
    row("LR0 control: with $cred readable the report's [mode] (!settings_os) says 'not managed (no global password)'", m0 == "not managed (no global password)", "mode=%r" % m0)
    row("LR1: with $cred that cannot be opened (moved aside) [mode] says the register could not be read, with a status, not 'not managed'",
        bool(m1) and re.match(r"^unknown \(the credential register could not be read, status -?\d+\)$", m1) is not None, "mode=%r" % m1)
    # 17 Nov 26 (S.62, L4 S1): $cred opens but the READ of $global fails for another reason than "no such record" (the directory is mode 000): not "not managed" either
    row("LR2: with $cred present but mode 000 (it opens, the read fails) [mode] says the global password record could not be read, with a status, not 'not managed'",
        bool(m000) and re.match(r"^unknown \(the global password record could not be read, status -?\d+ os error 13\)$", m000) is not None, "mode=%r" % m000)

    # LG: SET.CONFIG's two refusals print SD Core's numbers' texts (11932, 11931), the files renumbered from 14972 / 14973
    msgs = os.path.join(SD64, "sdsys", "messages")
    t32 = open(os.path.join(msgs, "11932")).read().strip()
    t31 = open(os.path.join(msgs, "11931")).read().strip()
    c0 = sha(os.path.join(BOX, "sd.conf"))
    out = session(["SET.CONFIG BAD-NAME 5", "SET.CONFIG ONLYONE"], unlock=True)
    row("LG1: SET.CONFIG BAD-NAME 5 prints message 11932's text and SET.CONFIG ONLYONE prints 11931's, as the files say; sd.conf unchanged",
        any(ln.strip() == t32 for ln in out) and any(ln.strip() == t31 for ln in out) and sha(os.path.join(BOX, "sd.conf")) == c0, "output=%r" % (out,))


if __name__ == "__main__":
    main()
