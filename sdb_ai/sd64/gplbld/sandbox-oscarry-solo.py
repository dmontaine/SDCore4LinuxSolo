#!/usr/bin/env python3
#
# sandbox-oscarry-solo.py - the features Core has and Solo lacked until SOLO CARRY 18 (24 Oct 2026), RUN on a private SD Core for Linux Solo
#                           as ordinary sessions of the one account, sduser, with the disk as the evidence: OSCOPY and !IOSCOPY, SELECT.DIR,
#                           SET.MODE, the functions ACCOUNT.PATH and VOCPATH (the OS-path programs held since carry 2 until Solo had an OS
#                           switch), LOCK.TRACER (its VOC entry was missing), INHIBIT.LOGIN and the newvoc.mods file.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-oscarry-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo).  With --build it is built first from THIS tree (it must be
# empty or absent).  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop the sandbox afterwards with sandbox-fromtree.py <dir> stop.
#
# START-HISTORY:
# 24 Oct 26 dm  Written for Solo carry 18.  The harness (the plain, administrator and internal lanes, the register states) is sandbox-osgate.py's,
#               loaded as a module; the Core suites these rows come from are sandbox-oq2.py (OSCOPY, !IOSCOPY), sandbox-list-a7.py (SELECT.DIR),
#               sandbox-stmt-q3.py (SET.MODE), sandbox-func-q1.py (ACCOUNT.PATH, VOCPATH), sandbox-q5.py (LOCK.TRACER) and sandbox-inhibit-q8.py.
# END-HISTORY
#
#   A  the OS switch OFF (the delivered state): OSCOPY / !OSCOPY / !IOSCOPY / SELECT.DIR inside the account work and outside it are refused with
#      nothing on the disk; SET.MODE is refused for an ordinary session and not for the administrator; ACCOUNT.PATH and VOCPATH answer for the
#      account's own paths and not for an F-pointer that leads out of it (3035)
#   B  the OS switch ON (set.os.access os on): the same routes reach outside; SET.MODE changes the bits on the disk
#   C  LOCK.TRACER: the administrator's, off until switched on, the log shows a record locked by a program, an ordinary session is refused
#   D  INHIBIT.LOGIN: a second session is refused (11281) while a first holds it, the setter can switch it off, a setter that is gone does not lock
#      anybody out, an ordinary session cannot set it
#   E  newvoc.mods: a record of the file reaches the account's VOC at the next UPDATE.ACCOUNTS
# NOT RUN HERE: the API server's refusal (source only), an installed Solo, newvoc.mods across an uninstall that keeps the data (not built), a
# terminal's window size (the debugger's rows are sandbox-ai-apps-solo.py's).
import importlib.util
import os
import re
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


og = _load("sandbox_osgate_for_oscarry", "sandbox-osgate.py")
say, bail, has, put, prog, clean = og.say, og.bail, og.has, og.put, og.prog, og.clean
session, internal, reg_state, compiled = og.session, og.internal, og.reg_state, og.compiled
FAILED_IDS = []

# Runtime mutants: one change to the SANDBOX'S OWN COPY of a program (recompiled there, put back from the tree afterwards).  name: (program, old text, new
# text, the section that is run, the row ids that must fail and no others).  Exit 0 means exactly those rows failed.
MUTANTS = {
    "oscopy-no-gate": ("_oscopy", "      if not(kernel(K$PATH.OK, source)) or not(kernel(K$PATH.OK, target)) then\n", "      if @false then\n", "off", ["A5", "A5b", "A6"]),
    "seldir-no-gate": ("seldir", "   if not(kernel(K$PATH.OK, path)) then\n", "   if @false then\n", "off", ["A8"]),
    "setmode-no-gate": ("setmode", "   if not(kernel(K$ADMINISTRATOR, -1) or kernel(K$OS.EXEC, -1)) then\n", "   if @false then\n", "off", ["A11"]),
    "inhibit-always-allowed": ("login_inhibit", "               allowed = is.admin\n", "               allowed = @true\n", "inhibit", ["D4", "D5", "D8"]),   # (a TEST that gave an error would refuse EVERY session, the mutant runner's own included)
}


def row(name, ok, detail=""):
    if not ok:
        FAILED_IDS.append(name.split(" ", 1)[0])
    og.row(name, ok, detail)


def slurp(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def run_prog(name, body, unlock=False):
    """A plain program in sduser's bp, compiled and run by an ordinary session (or the administrator's): its output lines."""
    prog(name, body)
    return session(["BASIC bp " + name, "RUN bp " + name], unlock=unlock)


def modes(d, names):
    out = {}
    for n in names:
        try:
            out[n] = os.stat(os.path.join(d, n)).st_mode & 0o777
        except OSError:
            out[n] = None
    return out


# ---------------------------------------------------------------------------------------------------------------------------------

def sec_off():
    ACCT, OUT = og.ACCT, og.OUT
    say("\n=== A. the OS switch OFF (the delivered state) =========================================================================")
    reg_state(False, False)
    d = os.path.join(ACCT, "zzoc")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    a, b = os.path.join(d, "a"), os.path.join(d, "b")
    put(a, "hello\n")
    out = session(["OSCOPY %s %s" % (a, b)])
    row("A1 OSCOPY inside the account copies ('copied to') and the target is on the disk", has(out, r"copied to") and slurp(b) == b"hello\n", "output=%r" % (out,))
    out = session(["OSCOPY %s %s" % (a, b)])
    row("A2 ...and refuses to replace it without an option ('already exists'); the target is as it was", has(out, r"already exists") and slurp(b) == b"hello\n", "output=%r" % (out,))
    session(["OSCOPY %s %s APPEND" % (a, b)])
    row("A3 APPEND adds the source to the end of the target", slurp(b) == b"hello\nhello\n", repr(slurp(b)))
    put(a, "new\n")
    session(["OSCOPY %s %s OVERWRITE" % (a, b)])
    row("A3b OVERWRITE replaces it", slurp(b) == b"new\n", repr(slurp(b)))
    out = session(["OSCOPY %s %s" % (os.path.join(d, "none"), os.path.join(d, "c"))])
    row("A4 a source inside the account that is not there is reported ('not found'), nothing is made", has(out, r"not found") and slurp(os.path.join(d, "c")) is None, "output=%r" % (out,))

    put(os.path.join(OUT, "secret.txt"), "OUTSIDE-SECRET-12345\n")
    out = session(["OSCOPY %s %s" % (os.path.join(OUT, "secret.txt"), os.path.join(d, "stolen"))])
    row("A5 OSCOPY from a file OUTSIDE the account is refused (no OS access) and the copy is not on the disk",
        has(out, r"has no OS access") and slurp(os.path.join(d, "stolen")) is None, "output=%r" % (out,))
    clean(os.path.join(OUT, "planted"))
    out = session(["OSCOPY %s %s" % (a, os.path.join(OUT, "planted"))])
    row("A5b OSCOPY to a target OUTSIDE the account is refused too and nothing was written there",
        has(out, r"has no OS access") and slurp(os.path.join(OUT, "planted")) is None, "output=%r" % (out,))

    # !IOSCOPY, called from an ordinary program (the status is the evidence as well as the disk)
    tree = os.path.join(d, "tree")
    os.makedirs(os.path.join(tree, "sub"))
    put(os.path.join(tree, "f1"), "one\n")
    put(os.path.join(tree, "sub", "f2"), "two\n")
    out = run_prog("zzocio", ["call !ioscopy('%s', '%s', st1)" % (tree, os.path.join(d, "tree2")), "crt 'IO inside ':st1",
                              "call !ioscopy('%s', '%s', st2)" % (OUT, os.path.join(d, "tree3")), "crt 'IO outside ':st2",
                              "call !oscopy('%s', '%s', 1, st3)" % (a, os.path.join(OUT, "planted")), "crt 'OC to-outside ':st3"])
    row("A6 !IOSCOPY copies a tree inside the account (status 0, the files are there); !IOSCOPY of a tree outside is status -4 and nothing is made; !OSCOPY into the outside is -4",
        compiled(out) and has(out, r"^IO inside 0$") and slurp(os.path.join(d, "tree2", "sub", "f2")) == b"two\n" and has(out, r"^IO outside -4$")
        and not os.path.exists(os.path.join(d, "tree3")) and has(out, r"^OC to-outside -4$") and slurp(os.path.join(OUT, "planted")) is None, "output=%r" % (out,))

    # SELECT.DIR
    sd = os.path.join(ACCT, "zzsd")
    shutil.rmtree(sd, ignore_errors=True)
    os.makedirs(os.path.join(sd, "gamma"))
    for n in ("alpha.txt", "beta.txt"):
        put(os.path.join(sd, n), "x\n")
    prog("zzsl", ["loop", "   readnext id else exit", "   crt 'L ':id", "repeat", "crt 'L end'"])
    session(["BASIC bp zzsl"])
    out = session(["SELECT.DIR " + sd, "RUN bp zzsl"])
    got = sorted(ln[2:] for ln in out if ln.startswith("L ") and ln != "L end")
    row("A7 SELECT.DIR of a directory inside the account lists the two files and the subdirectory", got == ["alpha.txt", "beta.txt", "gamma"] and has(out, r"^3 record\(s\) selected to select list 0$"), "output=%r" % (out,))
    out = session(["SELECT.DIR " + OUT, "RUN bp zzsl"])
    row("A8 SELECT.DIR of a directory OUTSIDE the account is refused (no OS access) and selects nothing", has(out, r"has no OS access") and not any(ln.startswith("L ") and ln != "L end" for ln in out), "output=%r" % (out,))
    out = session(["SELECT.DIR " + sd + "/nosuchdir"])
    row("A9 CONTROL: a directory inside the account that is not there is 'Cannot read directory'", has(out, r"(?i)cannot read directory"), "output=%r" % (out,))

    # SET.MODE: a directory file with three records; the modes are on the disk
    prog("zzsmmk", ["open 'zzsmdir' to f else crt 'NOOPEN' ; stop", "for r = 1 to 3", "   write 'rec':r on f, 'abc'[r, 1]", "next r", "crt 'MK done'"])
    out = session(["CREATE.FILE zzsmdir DIRECTORY", "BASIC bp zzsmmk", "RUN bp zzsmmk"])
    smdir = os.path.join(ACCT, "zzsmdir")
    for n in "abc":                      # the records start at 0644 whatever an earlier run on this sandbox left (the mode is the runner's own to set: it owns the files)
        if os.path.exists(os.path.join(smdir, n)):
            os.chmod(os.path.join(smdir, n), 0o644)
    before = modes(smdir, "abc")
    row("A10 setup: a directory file with three records, all 0644 (none is 0640)", has(out, r"^MK done$") and all(v is not None and v != 0o640 for v in before.values()), "output=%r modes=%r" % (out[-3:], before))
    out = session(["SET.MODE zzsmdir a 640"])
    row("A11 SET.MODE changes OS permission bits, so an ordinary session with the switch OFF is refused (11314) and nothing changes",
        has(out, r"needs the account's operating system access \(set\.os\.access os on\)") and modes(smdir, "abc") == before, "output=%r modes=%r" % (out, modes(smdir, "abc")))
    out = session(["SET.MODE zzsmdir a 640"], unlock=True)
    row("A12 the administrator is not refused: 1 record set to mode 640, record a is 0640 on the disk and b and c are as they were",
        has(out, r"^1 record\(s\) set to mode 640$") and modes(smdir, "abc") == {"a": 0o640, "b": before["b"], "c": before["c"]}, "output=%r modes=%r" % (out, modes(smdir, "abc")))

    # ACCOUNT.PATH and VOCPATH
    out = run_prog("zzapf", ["a = account.path(@who)", "crt 'AP own ':a", "crt 'AP none [':account.path('zznosuch'):']'",
                             "p = vocpath('bp')", "st1 = status()", "crt 'VP bp ':p:' st=':st1",
                             "q = vocpath('zznosuch')", "st2 = status()", "crt 'VP none [':q:'] st#0=':(st2 # 0)",
                             "d1 = vocpath('DICT zzsmdir')", "d2 = vocpath('zzsmdir', @true)", "d3 = vocpath('zzsmdir')", "crt 'VP dict ':(d1 # ''):(d1 = d2):(d1 # d3)",
                             "r = vocpath('zzptr')", "st3 = status()", "crt 'VP pointer-out [':r:'] st=':st3"])
    own = next((ln[7:] for ln in out if ln.startswith("AP own ")), "")
    bpp = next((re.match(r"VP bp (\S+) st=(\S+)", ln) for ln in out if ln.startswith("VP bp ")), None)
    row("A13 ACCOUNT.PATH(@who) is the account's directory and ACCOUNT.PATH of an account that is not there is a null string",
        compiled(out) and bool(own) and os.path.realpath(own) == os.path.realpath(ACCT) and has(out, r"^AP none \[\]$"), "output=%r" % (out,))
    row("A14 VOCPATH('bp') is the file's absolute path and STATUS() 0; of a file that is not there a null string and a status; DICT in front or a true second argument give the dictionary part",
        bool(bpp) and os.path.realpath(bpp.group(1)) == os.path.realpath(os.path.join(ACCT, "bp")) and bpp.group(2) == "0" and has(out, r"^VP none \[\] st#0=1$") and has(out, r"^VP dict 111$"), "output=%r" % (out,))
    row("A15 VOCPATH of an F-pointer that leads out of the account is a null string with the status 3035 while the switch is OFF (the pointer cannot be opened)",
        has(out, r"^VP pointer-out \[\] st=3035$"), "output=%r" % (out,))


def sec_on():
    ACCT, OUT = og.ACCT, og.OUT
    say("\n=== B. the OS switch ON (set.os.access os on) =========================================================================")
    reg_state(False, True)
    d = os.path.join(ACCT, "zzoc")
    out = session(["OSCOPY %s %s" % (os.path.join(OUT, "secret.txt"), os.path.join(d, "fetched"))])
    row("B1 OSCOPY from a file outside the account works: 'copied to', the content is on the disk", has(out, r"copied to") and slurp(os.path.join(d, "fetched")) == b"OUTSIDE-SECRET-12345\n", "output=%r" % (out,))
    out = session(["OSCOPY %s %s" % (os.path.join(d, "fetched"), os.path.join(OUT, "planted"))])
    row("B2 ...and to a target outside the account", has(out, r"copied to") and slurp(os.path.join(OUT, "planted")) == b"OUTSIDE-SECRET-12345\n", "output=%r" % (out,))
    out = run_prog("zzocio2", ["call !ioscopy('%s', '%s', st1)" % (OUT, os.path.join(d, "tree4")), "crt 'IO outside ':st1"])
    row("B3 !IOSCOPY of a tree outside the account works (status 0, a file of the tree is on the disk)", has(out, r"^IO outside 0$") and slurp(os.path.join(d, "tree4", "secret.txt")) == b"OUTSIDE-SECRET-12345\n", "output=%r" % (out,))
    os.makedirs(os.path.join(OUT, "listme"), exist_ok=True)
    put(os.path.join(OUT, "listme", "a.txt"), "a\n")
    out = session(["SELECT.DIR " + os.path.join(OUT, "listme"), "RUN bp zzsl"])
    row("B4 SELECT.DIR of a directory outside the account lists it", has(out, r"^L a\.txt$"), "output=%r" % (out,))

    smdir = os.path.join(ACCT, "zzsmdir")
    before = modes(smdir, "abc")
    out = session(["SET.MODE zzsmdir a 640"])
    now = modes(smdir, "abc")
    row("B5 SET.MODE for an ordinary session with the switch ON: '1 record(s) set to mode 640' and a is 0640 on the disk, b and c untouched",
        has(out, r"^1 record\(s\) set to mode 640$") and now["a"] == 0o640 and now["b"] == before["b"] and now["c"] == before["c"], "output=%r modes=%r" % (out, now))
    out = session(["SET.MODE zzsmdir ALL 600"])
    row("B6 ALL: three records, all 0600", has(out, r"^3 record\(s\) set to mode 600$") and set(modes(smdir, "abc").values()) == {0o600}, "output=%r modes=%r" % (out, modes(smdir, "abc")))
    out = session(["SET.MODE zzsmdir a 649", "SET.MODE zzsmdir a 64", "SET.MODE zzsmdir zzno 600", "CREATE.FILE zzsmdyn", "SET.MODE zzsmdyn a 600"])
    row("B7 a mode that is not three octal digits is refused twice, a record that is not there is said so, and a file that is not a directory file is refused; the bits are as they were",
        sum(1 for ln in out if "The mode must be three octal digits" in ln) == 2 and has(out, r"Record 'zzno' not found") and has(out, r"A directory file is required")
        and set(modes(smdir, "abc").values()) == {0o600}, "output=%r modes=%r" % (out, modes(smdir, "abc")))

    out = run_prog("zzapf2", ["r = vocpath('zzptr')", "st3 = status()", "crt 'VP pointer-out [':r:'] st=':st3"])
    row("B8 VOCPATH of the F-pointer that leads out of the account is its path (/etc) and STATUS() 0 once the switch is ON", has(out, r"^VP pointer-out \[/etc\] st=0$"), "output=%r" % (out,))
    reg_state(False, False)


def sec_tracer():
    SYS = og.SYS
    say("\n=== C. LOCK.TRACER ===================================================================================================")
    trace = os.path.join(SYS, "locktrace")
    clean(trace)
    out = session(["LOCK.TRACER ON"])
    row("C1 an ordinary session is refused (11361) and no trace file is made", has(out, r"lock tracing is for the administrator") and not os.path.exists(trace), "output=%r" % (out,))
    prog("zzlt", ["open 'bp' to f else crt 'NOOPEN' ; stop", "readu x from f, 'zzlkrec' else x = ''", "release f, 'zzlkrec'", "crt 'LT done'"])
    out = session(["LOCK.TRACER ON", "BASIC bp zzlt", "RUN bp zzlt", "LOCK.TRACER OFF", "LOCK.TRACER"], unlock=True)
    row("C2 the administrator: ON ('lock tracing is on'), a program locks and releases a record, OFF ('lock tracing is off'), the report names the record",
        has(out, r"lock tracing is on") and has(out, r"^LT done$") and has(out, r"lock tracing is off") and has(out, r"zzlkrec") and has(out, r"record id"), "output=%r" % (out,))
    row("C3 the log is a file in the system directory (the kernel writes it) and it holds the record id", os.path.exists(trace) and b"zzlkrec" in (slurp(trace) or b""), "exists=%r" % os.path.exists(trace))
    clean(trace)


def start_holder(cmds):
    """A session of the administrator that stays open: commands written now, stdin kept open.  Returns the Popen."""
    env = dict(os.environ, SD_CONFIG=os.path.join(og.BOX, "sd.conf"))
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    head = og.secret("account.pw") + "\nADMIN\n" + og.secret("admin.pw") + "\n"
    say("    > [holder, stays open] " + " | ".join(cmds))
    p = subprocess.Popen([os.path.join(og.SYS, "bin", "sd-solo")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         cwd=og.SYS, env=env, text=True, errors="replace")
    p.stdin.write(head + "TERM 200,9999\n" + "".join(c + "\n" for c in cmds))
    p.stdin.flush()
    return p


def wait_for(path, present, tmax=45.0):
    t0 = time.time()
    while time.time() - t0 < tmax:
        if os.path.exists(path) == present:
            return True
        time.sleep(0.4)
    return False


def sec_inhibit():
    SYS, ACCT = og.SYS, og.ACCT
    hold = os.path.join(SYS, "login.inhibit")
    say("\n=== D. INHIBIT.LOGIN ===================================================================================================")
    clean(hold)
    prog("zzin", ["crt 'IN-RAN'"])
    prog("zzslp", ["sleep 30", "crt 'SLEPT'"])
    out = session(["BASIC bp zzin zzslp"])
    row("D0 setup: the two probes compile", compiled(out, 2), "output=%r" % (out,))
    out = session(["INHIBIT.LOGIN ON"])
    row("D1 an ordinary session cannot set it (2001) and nothing is on the disk", has(out, r"Command requires administrator privileges") and not os.path.exists(hold), "output=%r" % (out,))
    out = session(["INHIBIT.LOGIN", "RUN bp zzin"], unlock=True)
    row("D2 CONTROL: with nothing set the state is 'Logins are allowed' and a new session runs its program", has(out, r"^Logins are allowed$") and has(out, r"^IN-RAN$"), "output=%r" % (out,))

    p = start_holder(["INHIBIT.LOGIN ON", "RUN bp zzslp"])
    try:
        up = wait_for(hold, True)
        row("D3 the holder (an administrator session) set it: the record login.inhibit is on the disk", up, "no login.inhibit after 45 s")
        if not up:
            return
        time.sleep(1.0)
        out = session(["RUN bp zzin"])
        row("D4 a NEW plain session is refused with 'SD is not accepting new sessions' and its program never ran",
            has(out, r"SD is not accepting new sessions: logins have been inhibited by") and not has(out, r"^IN-RAN$"), "output=%r" % (out,))
        out = session(["RUN bp zzin"], unlock=True)
        row("D5 a new session that types ADMIN is refused too: in Solo ADMIN comes after sign-on, so no new session is the administrator at the door (the setter and its phantoms are let in)",
            has(out, r"SD is not accepting new sessions") and not has(out, r"^IN-RAN$"), "output=%r" % (out,))
        row("D6 the hold records who set it (user number, process id, name, date, time)", len((slurp(hold) or b"").split(b"\n")) >= 5, "record=%r" % (slurp(hold),))
    finally:
        p.kill()
        p.communicate()
    # the setter was KILLED without switching it off: the record is still there, the setter is gone
    stale = os.path.exists(hold)
    time.sleep(1.0)
    out = session(["INHIBIT.LOGIN", "RUN bp zzin"], unlock=True)
    row("D7 the setter has gone (killed, no OFF): its record is still on the disk but nobody is locked out - a new session runs and the state is 'Logins are allowed'",
        stale and has(out, r"^IN-RAN$") and has(out, r"^Logins are allowed$"), "stale=%r output=%r" % (stale, out))
    clean(hold)

    # the setter switches it off itself, and the audit trail is not asked: the evidence is the disk and the sessions
    p = start_holder(["INHIBIT.LOGIN ON", "RUN bp zzslp"])
    try:
        up = wait_for(hold, True)
        if not up:
            row("D8 the second holder set it", False, "no login.inhibit after 45 s")
            return
        time.sleep(1.0)
        refused = has(session(["RUN bp zzin"]), r"SD is not accepting new sessions")
    finally:
        out = finish_holder_after_off(p)
    row("D8 a refused session while it is set, then the holder's INHIBIT.LOGIN OFF removes the record and the next new session runs",
        refused and not os.path.exists(hold) and has(session(["RUN bp zzin"]), r"^IN-RAN$"), "refused=%r holder output tail=%r" % (refused, out[-300:]))
    clean(hold)


def finish_holder_after_off(p):
    """The holder is asleep in zzslp for 30 s.  INHIBIT.LOGIN OFF and OFF are written to its pipe now: it reads them when the sleep ends, switches the
    hold off itself and signs off (killing it instead would be the stale case of D7)."""
    try:
        p.stdin.write("INHIBIT.LOGIN OFF\nOFF\n")
        p.stdin.flush()
        p.stdin.close()
    except (OSError, ValueError):
        pass
    try:
        out, _ = p.communicate(timeout=70)
    except subprocess.TimeoutExpired:
        p.send_signal(signal.SIGKILL)
        out, _ = p.communicate()
    return out or ""


def sec_mods():
    SYS = og.SYS
    say("\n=== E. newvoc.mods ====================================================================================================")
    mods = os.path.join(SYS, "newvoc.mods")
    shutil.rmtree(mods, ignore_errors=True)
    out = session(["zznvm"])
    row("E0 CONTROL: before the file exists, the command zznvm does not run the paragraph", not has(out, r"^NVM-APPLIED$"), "output=%r" % (out,))
    put(os.path.join(SYS, "bp", "zznvmw"), "\n".join([
        "$internal", "   mk = '" + mods + "'", "   openpath mk to f else crt 'NVM no-dir' ; stop",
        "   write 'PA':@fm:'DISPLAY NVM-APPLIED' on f, 'zznvm'", "   crt 'NVM written'", "end", ""]))
    os.makedirs(mods)
    out = internal(["BASIC bp zznvmw", "RUN bp zznvmw"])
    row("E1 setup: a paragraph record is written to the directory file newvoc.mods in the system directory", has(out, r"^NVM written$") and os.path.exists(os.path.join(mods, "zznvm")), "output=%r" % (out[-4:],))
    out = internal(["UPDATE.ACCOUNTS ALL"])
    row("E2 UPDATE.ACCOUNTS ALL reports the account's VOC updated", has(out, r"1 account\(s\) had their VOC updated"), "output=%r" % (out[-4:],))
    out = session(["zznvm"])
    row("E3 the record of newvoc.mods is in the account's VOC: the command runs the paragraph ('NVM-APPLIED')", has(out, r"^NVM-APPLIED$"), "output=%r" % (out,))
    shutil.rmtree(mods, ignore_errors=True)
    session(["DELETE VOC zznvm"], unlock=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--mutant", choices=sorted(MUTANTS))
    a = ap.parse_args()
    og.BOX = os.path.abspath(a.dir)
    og.SYS = os.path.join(og.BOX, "sys")
    og.ACCT = os.path.join(og.SYS, "user_accounts", og.ACCOUNT)
    og.REG = os.path.join(og.SYS, "accounts", og.ACCOUNT)
    og.OUT = os.path.join(og.SYS, "zzoutside")
    say("sandbox-oscarry-solo: sandbox %s" % og.BOX)
    if a.build:
        if os.path.exists(og.BOX) and os.listdir(og.BOX):
            bail("%s is not empty" % og.BOX)
        r = subprocess.run([sys.executable, og.TOOL, og.BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-oscarry-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(og.SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % og.BOX)
    subprocess.run([sys.executable, og.TOOL, og.BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(og.REG):
        bail("there is no register record %s" % og.REG)

    say("\n--- controls -----------------------------------------------------------------------------------------------------")
    out = session(["WHO.AM.I"])
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of sduser and NOT an administrator (WHO.AM.I says Admin? %s)" % (adm.group(1) if adm else "-"),
        has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        bail("the session is privileged; its refusals prove nothing")
    sh0, os0 = og.reg_fields()
    row("the register record as the install made it has the switches OFF", sh0 != "yes" and os0 != "yes", "fields=%r %r" % (sh0, os0))
    # the F-pointer at /etc that the VOCPATH rows use, written by an internal program (the VOC is the administrator's)
    put(os.path.join(og.SYS, "bp", "zzocfix"), "\n".join([
        "$internal", "   openpath '%s/voc' to v else crt 'FIX no voc' ; stop" % og.ACCT,
        "   write 'F':@fm:'/etc':@fm:'' to v, 'zzptr'", "   crt 'FIX done'", "end", ""]))
    out = internal(["BASIC bp zzocfix", "RUN bp zzocfix"])
    row("setup: an F-pointer at /etc is written into sduser's VOC by an internal program", has(out, r"^FIX done$"), "output=%r" % (out[-4:],))
    shutil.rmtree(og.OUT, ignore_errors=True)
    os.makedirs(og.OUT)

    mprog = None
    try:
        if a.mutant is None:
            sec_off()
            sec_on()
            sec_tracer()
            sec_inhibit()
            sec_mods()
        else:
            mprog, old, new, section, _want = MUTANTS[a.mutant]
            path = os.path.join(og.SYS, "gpl.bp", mprog)
            src = open(path, encoding="utf-8", errors="replace").read()
            if src.count(old) != 1:
                bail("mutant %s: the text to change is found %d times in %s, not once" % (a.mutant, src.count(old), mprog))
            put(path, src.replace(old, new))
            out = internal(["BASIC gpl.bp " + mprog])
            if not has(out, r"^Compiled 1 program\(s\) with no errors"):
                bail("mutant %s: %s did not compile in the sandbox: %r" % (a.mutant, mprog, out[-4:]))
            say("sandbox-oscarry-solo: MUTANT %s: %s changed and recompiled in the sandbox; the rows that must fail, and nothing else: %s" % (a.mutant, mprog, ", ".join(_want)))
            {"off": sec_off, "inhibit": sec_inhibit}[section]()
    finally:
        if mprog is not None:                  # the sandbox's program put back from the tree, whatever happened
            shutil.copyfile(os.path.join(og.SD64, "sdsys", "gpl.bp", mprog), os.path.join(og.SYS, "gpl.bp", mprog))
            internal(["BASIC gpl.bp " + mprog])
        reg_state(False, False)
        shutil.rmtree(og.OUT, ignore_errors=True)
        for dd in ("zzoc", "zzsd"):          # NOT zzsmdir and zzsmdyn: their VOC entries outlive a directory that is removed, and a rerun on the same sandbox then cannot make them again
            clean(os.path.join(og.ACCT, dd))
        clean(os.path.join(og.SYS, "login.inhibit"))
        for pn in ("zzocio", "zzocio2", "zzsl", "zzsmmk", "zzapf", "zzapf2", "zzlt", "zzin", "zzslp", "zznvmw"):
            for d in ("bp", "bp.out"):
                q = os.path.join(og.ACCT, d, pn)
                if os.path.exists(q):
                    os.remove(q)
        for pn in ("zzocfix", "zznvmw"):
            q = os.path.join(og.SYS, "bp", pn)
            if os.path.exists(q):
                os.remove(q)
    say("\nsandbox-oscarry-solo: %d passed, %d failed" % (og.passed, og.failed))
    if a.mutant is not None:
        want = sorted(set(MUTANTS[a.mutant][4]))
        got = sorted(set(FAILED_IDS))
        ok = want == got
        say("sandbox-oscarry-solo: MUTANT %s: the rows that failed are %s; they had to be exactly %s -> %s" % (a.mutant, got, want, "KILLED BY ITS OWN ROWS" if ok else "NOT AS EXPECTED"))
        sys.exit(0 if ok else 1)
    sys.exit(0 if og.failed == 0 and og.passed > 0 else 1)


if __name__ == "__main__":
    main()
