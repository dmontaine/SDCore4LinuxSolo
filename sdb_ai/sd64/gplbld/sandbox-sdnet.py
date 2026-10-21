#!/usr/bin/env python3
#
# sandbox-sdnet.py - SDNet on SD Core for Linux Solo (carry 9 of SD Core's S.65): the NET gate as the kernel holds it, and the
#                    administrator's server definitions.  Solo's copy of the idea of SD Core's sandbox-net.py (which uses SD Core's
#                    fixture accounts, sandbox-gates.py and the sdfiles route); written FIRST, before the code existed, and run red on
#                    8d0a720.  No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-sdnet.py <dir> [--build] [--sections=a,b]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo).  With --build it is built first from THIS tree (it
# must be empty or absent).  SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop the
# sandbox afterwards with sandbox-fromtree.py <dir> stop.  --sections= runs only the named parts (gate, defs, ordinary).
#
# START-HISTORY:
# 20 Oct 26 dm  Stage A of the SDNet carry (owner, 20 Oct: "core to solo complete, solo to core limited, core to core and solo to solo your
#               judgement"): the gate (K$NET, register field 15, the same field that guards API request 29), set.server, list.servers and
#               delete.server and the file netservers.  Nothing opens a remote file yet.
# END-HISTORY
#
# THE LANE.  As sandbox-osgate.py: a plain session of sduser is sd-solo with the account password as the first line of the pipe (read from
# <dir>/account.pw, never printed); the administrator's lane types ADMIN and <dir>/admin.pw first; the internal lane is sandbox-fromtree.py's
# `sess`.  The NET gate is field 15 of the register record accounts/sduser: only the word yes is on.  The suite WRITES that field for each
# state and signs on again (the load is at sign-on).  EVIDENCE IS THE DISK: the definitions file is compared byte for byte before and after
# every refusal.
#
# NOT RUN HERE, said plainly: an API session's load of the gate (a sandbox can host one, sandbox-req29.py reads the register itself), the
# audit lines of an install, the key hash of a real server (stage B).

import argparse
import datetime
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
BOX = SYS = ACCT = REG = ""

PIN_A = "0123456789abcdef" * 4
PIN_B = "fedcba9876543210" * 4
DATE_RE = r"\d{4}-\d{2}-\d{2}"
SUCCESS = r"\) (is defined|was replaced)$"

# the messages this stage prints; a sandbox that lacks one is a FAILED row, not a skipped one
NEEDED = [11412, 11413, 11414, 11415, 11416, 11417, 11418, 11419, 11420, 11421, 11422, 11423, 11424, 11425, 11426, 11427, 11429, 11430,
          11431, 11432, 11433, 11434, 11435, 11436, 11437, 11438, 11439]


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


def bail(msg_):
    say("sandbox-sdnet: CANNOT RUN - " + msg_)
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


def session(cmds, unlock=False, timeout=300, quiet=False):
    """A session of sduser on a pipe.  unlock=True types ADMIN and the administrator password first.  Returns the lines printed after the
    TERM line, echoed commands (those that begin with a colon) and blank lines left out.  The commands are shown."""
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    head = secret("account.pw") + "\n"
    if unlock:
        head += "ADMIN\n" + secret("admin.pw") + "\n"
    body = head + "TERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n"
    if not quiet:
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


def adm1(*cmds):
    return session(list(cmds), unlock=True)


def internal(cmds):
    """An internal session (SDSYS): sandbox-fromtree.py's `sess` writes the one-shot marker."""
    say("    > [internal] " + " | ".join(cmds))
    r = subprocess.run([sys.executable, TOOL, BOX, "sess", SYS] + cmds, capture_output=True, text=True, errors="replace", timeout=600)
    out = ANSI.sub("", r.stdout + r.stderr).split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def has(lines, pattern):
    return any(re.search(pattern, ln) for ln in lines)


def has_line(out, text):
    return any(ln == text for ln in out)


def has_text(out, text):
    return any(text in ln for ln in out)


def put(path, text):
    with open(path, "w", encoding="ascii") as f:
        f.write(text)


def msg(n, *args):
    """The text of message N as the sandbox was built with it, the %n places filled.  A message that is not there reads '<<no message N>>', which
    no output line can equal, so a row that needs it FAILS (the setup row names every missing one)."""
    p = os.path.join(SYS, "messages", str(n))
    if not os.path.exists(p):
        return "<<no message %d>>" % n
    with open(p, encoding="utf-8", errors="replace") as f:
        t = f.read().strip("\n")
    for i, a in enumerate(args, 1):
        t = t.replace("%%%d" % i, str(a))
    return t


def netfile():
    return os.path.join(SYS, "netservers")


def snap():
    """The bytes of the definitions file, or None when there is none."""
    try:
        with open(netfile(), "rb") as f:
            return f.read()
    except OSError:
        return None


def sw(data, prefix):
    """data starts with prefix; False when either is missing (a run on a tree without the verbs has no file, and must go red, not crash)."""
    return data is not None and prefix is not None and data.startswith(prefix)


def file_lines():
    b = snap()
    if b is None:
        return None
    t = b.decode("ascii", errors="replace")
    return t.split("\n")[:-1] if t.endswith("\n") else t.split("\n")


def reg_lines():
    with open(REG) as f:
        lines = f.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def reg_net(value):
    """Write field 15 of the register record accounts/sduser and keep fields 1 to 14 as they were.  value None leaves a record with NO
    field 15 (fourteen fields); a string is written as given (fields 9 to 14 are padded empty when the record is shorter)."""
    lines = reg_lines()
    if value is None:
        lines = lines[:14]
    else:
        lines += [""] * (14 - len(lines))
        lines = lines[:14] + [value]
    put(REG, "\n".join(lines) + "\n")


def reg_os(on):
    """Field 8 (OS.EXEC) yes or blank; the other fields as they were."""
    lines = reg_lines()
    lines += [""] * (8 - len(lines))
    lines[7] = "yes" if on else ""
    put(REG, "\n".join(lines) + "\n")


def compiled(out, n=1):
    return has(out, r"^Compiled %d program\(s\) with no errors" % n) and not has(out, r"^WARNING")


# --------------------------------------------------------------------------------------------------------------------------------

ZZNK = "\n".join([
    "$internal", "program zznk", "$catalog $zznk", "$include keys.h", "$include int$keys.h",
    "   crt 'NK net=':kernel(K$NET,-1):' admin=':kernel(K$ADMINISTRATOR,-1)", "end", ""])
ZZNKSET = "\n".join([
    "$internal", "program zznkset", "$catalog $zznkset", "$include keys.h", "$include int$keys.h",
    "   b = kernel(K$NET,-1)",
    "   s1 = kernel(K$NET,1) ; a1 = kernel(K$NET,-1)",
    "   s0 = kernel(K$NET,0) ; a0 = kernel(K$NET,-1)",
    "   crt 'NS before=':b:' set1=':s1:' ask1=':a1:' set0=':s0:' ask0=':a0", "end", ""])


def nk(out):
    for ln in out:
        m = re.match(r"^NK net=(\d+) admin=(\d+)$", ln)
        if m:
            return m.group(1), m.group(2)
    return None


def prepare():
    """The probes that only an internal program can be (the gate as the kernel holds it, and a setter), reached by VOC verbs in sduser's VOC
    that an internal program writes."""
    put(os.path.join(SYS, "gpl.bp", "zznk"), ZZNK)
    put(os.path.join(SYS, "gpl.bp", "zznkset"), ZZNKSET)
    out = internal(["BASIC gpl.bp zznk zznkset"])
    ok = compiled(out, 2)
    row("setup: the kernel probes zznk and zznkset (K$NET) compile", ok, "output=%r" % (out[-4:],))
    put(os.path.join(SYS, "bp", "zznetfix"), "\n".join([
        "$internal",
        "   openpath '%s/voc' to v else crt 'NETFIX no voc' ; stop" % ACCT,
        "   write 'V':@fm:'CA':@fm:'$zznk' to v, 'zznk'",
        "   write 'V':@fm:'CA':@fm:'$zznkset' to v, 'zznkset'",
        "   crt 'NETFIX done'", "end", ""]))
    out = internal(["BASIC bp zznetfix", "RUN bp zznetfix"])
    row("setup: the probe verbs are written into sduser's VOC by an internal program", has(out, r"^NETFIX done$"), "output=%r" % (out[-4:],))
    missing = [n for n in NEEDED if not os.path.exists(os.path.join(SYS, "messages", str(n)))]
    row("setup: the sandbox holds every message this suite prints (%d)" % len(NEEDED), not missing, "missing %r" % (missing,))
    return ok


# ---- the gate ------------------------------------------------------------------------------------------------------------------

def gate_section():
    say("\n--- the gate: K$NET as the session holds it, loaded at sign-on from register field 15 (yes is on, anything else is off) ---")
    states = (("no", "no", 0), ("yes", "yes", 1), ("blank field", "", 0), ("a record with no field 15", None, 0), ("Yes (the test ignores case)", "Yes", 1),
              ("true (only yes is yes)", "true", 0), ("' yes ' (spaces are trimmed)", " yes ", 1))
    for label, value, want in states:
        reg_net(value)
        out = session(["zznk"], quiet=True)
        r = nk(out)
        row("field 15 %s -> net=%d, and the session is not an administrator" % (label, want),
            r is not None and r[0] == str(want) and r[1] == "0", "NK line: %r  output: %r" % (r, out[-3:]))
    reg_net("no")
    out = session(["zznk"], unlock=True, quiet=True)
    r = nk(out)
    row("the administrator (ADMIN) with the field off: admin=1 and net=0 - the gate follows the record, the later remote-open check lets the administrator through by its own flag",
        r is not None and r == ("0", "1"), repr((r, out[-3:])))
    reg_net("yes")
    out = session(["zznk"], unlock=True, quiet=True)
    r = nk(out)
    row("the administrator with the field on: admin=1 and net=1", r is not None and r == ("1", "1"), repr((r, out[-3:])))

    reg_net("no")
    out = session(["zznkset", "zznk"], quiet=True)
    row("zznkset (an internal program) sets K$NET and reads it back (before 0, set 1 -> 1, set 0 -> 0)",
        has_line(out, "NS before=0 set1=1 ask1=1 set0=0 ask0=0"), repr(out[:4]))
    reg_net("yes")
    out = session(["zznkset"], quiet=True)
    row("the same on a record that says yes: it starts from 1", has_line(out, "NS before=1 set1=1 ask1=1 set0=0 ask0=0"), repr(out[:4]))
    out = session(["zznkset", "zznk"], quiet=True)
    row("a session that turned it off still reports what its program left (0): the key is the session's, not the register's",
        nk(out) is not None and nk(out)[0] == "0", repr(out[:4]))
    out = session(["zznk"], quiet=True)
    row("CONTROL: a NEW session starts at the register's 1 again (the setter changed nothing on disk)", nk(out) is not None and nk(out)[0] == "1", repr(out[:3]))

    # an ordinary program cannot reach the key at all: KERNEL() is for $internal programs, and the compiler takes it for an array
    put(os.path.join(ACCT, "bp", "zznkord"), "\n".join([
        "program zznkord",
        "   a = kernel(127,1)",
        "   crt 'NO after-set=':kernel(127,-1)",
        "end", ""]))
    reg_net("no")
    out = session(["BASIC bp zznkord", "RUN bp zznkord", "zznk"], quiet=True)
    row("an ordinary program that tries to set the key does not run (KERNEL is not a function for it), prints no 'after-set' line, and the key still reads 0",
        not has(out, r"^NO after-set=") and has(out, r"KERNEL") and nk(out) is not None and nk(out)[0] == "0", repr(out[-5:]))
    reg_net("no")


# ---- the definitions -----------------------------------------------------------------------------------------------------------

def dates():
    d = datetime.date.today()
    return {d.isoformat(), (d - datetime.timedelta(days=1)).isoformat(), (d + datetime.timedelta(days=1)).isoformat()}


def line_is(line, fields):
    """A stored line is these eight fields, the last a date from today (give or take midnight)."""
    if line is None:
        return False
    parts = line.split("|")
    return len(parts) == 8 and parts[:7] == list(fields) and parts[7] in dates()


def refused(label, cmd, expect, answers=()):
    """A definition that must be refused: every expected message is printed as a line of its own, no success wording is, the file is the same
    bytes as before, and there is no netservers.new."""
    before = snap()
    out = adm1(cmd, *answers)
    after = snap()
    miss = [t for t in expect if not has_line(out, t)]
    row("%s -> refused, nothing written" % label,
        not miss and not has(out, SUCCESS) and before == after and not os.path.exists(netfile() + ".new"),
        "missing %r; file unchanged=%s; output %r" % (miss, before == after, out[-4:]))
    return out


def defs_section():
    say("\n--- set.server / list.servers / delete.server, run as the administrator (ADMIN) ------------------------------------------")
    for p in (netfile(), netfile() + ".new", netfile() + ".lock"):
        if os.path.exists(p):
            os.remove(p)
            say("  [note] a leftover %s was removed" % os.path.basename(p))
    ok_cmd = lambda name, host="valid.example.org", port="4247", account="acct", pin=PIN_A, extra="": \
        "set.server %s %s %s %s %s%s" % (name, host, port, account, pin, (" " + extra) if extra else "")

    # -- the first listing: no file at all
    out = adm1("list.servers")
    row("list.servers with no file: 'No servers are defined', and listing makes no file", has_line(out, msg(11433)) and snap() is None, repr(out[-3:]))
    out = adm1("delete.server nosuch")
    row("delete.server with no file: 'No server is defined with the name nosuch', and no file made", has_line(out, msg(11430, "nosuch")) and snap() is None, repr(out[-3:]))

    # -- usage
    for cmd, label in (("set.server", "no words"), ("set.server alpha1 host", "two words"), ("set.server a b c d", "four words")):
        out = refused("set.server with %s" % label, cmd, [msg(11412)])
        row("...and it says where the pin comes from (11413)", has(out, "^" + re.escape(msg(11413)[:60])), repr(out[-3:]))

    # -- the first definition: well formed, mode 644, one line
    old = os.umask(0o077)
    try:
        out = adm1(ok_cmd("alpha1", "host1.example.org", "4247", "reader", PIN_A, "write accounts sduser"))
    finally:
        os.umask(old)
    row("a valid set.server says 'Server alpha1 (host1.example.org:4247) is defined'", has_line(out, msg(11424, "alpha1", "host1.example.org", "4247")), repr(out[-3:]))
    row("...and gives no 'no account is listed' warning (an account was given)",
        has_line(out, msg(11424, "alpha1", "host1.example.org", "4247")) and not has_text(out, msg(11439, "alpha1")[:30]), repr(out[-3:]))
    lines = file_lines()
    row("...the file netservers holds exactly one line", lines is not None and len(lines) == 1, repr(lines))
    row("...of eight fields: name|host|port|account|pin|mode|accounts|created",
        lines is not None and line_is(lines[0], ["alpha1", "host1.example.org", "4247", "reader", PIN_A, "write", "sduser"]), repr(lines))
    try:
        st = os.stat(netfile())
        row("...mode 0644 although this process ran with umask 077 (the program sets 022 around the creation), owned by the session's user, a plain file",
            (st.st_mode & 0o7777) == 0o644 and st.st_uid == os.getuid() and os.path.isfile(netfile()), oct(st.st_mode))
    except OSError as e:
        row("...mode 0644 (the file could not be examined)", False, repr(e))
    row("...no copy netservers.new and no lock record netservers.lock are left behind (and the file itself is there)",
        os.path.exists(netfile()) and not os.path.exists(netfile() + ".new") and not os.path.exists(netfile() + ".lock"), "")
    first = snap()

    # -- a second one with the defaults, and one typed in upper case
    out = adm1(ok_cmd("beta", "h2.example.net", "4249", "admin", PIN_B))
    row("a second server with no mode and no accounts: defined, and told that no account may use it yet (11439)",
        has_line(out, msg(11424, "beta", "h2.example.net", "4249")) and has_line(out, msg(11439, "beta")), repr(out[-3:]))
    lines = file_lines()
    row("...two lines now, the first byte for byte as it was", lines is not None and len(lines) == 2 and sw(snap(), first), repr(lines))
    row("...the new line has mode read and an EMPTY accounts field (two bars), nothing else",
        lines is not None and len(lines) == 2 and line_is(lines[1], ["beta", "h2.example.net", "4249", "admin", PIN_B, "read", ""]), repr(lines))
    out = adm1("set.server UPPEROK Host3.Example.ORG 04250 Remote.Acct %s WRITE ACCOUNTS SDUSER" % PIN_A.upper())
    lines = file_lines() or []
    row("upper case is converted: name, host, pin, mode and accounts are stored in lower case, the port without its zero, the remote account as typed",
        len(lines) == 3 and line_is(lines[2], ["upperok", "host3.example.org", "4250", "Remote.Acct", PIN_A, "write", "sduser"]), repr(lines))
    out = adm1("set.server dupacc h4.example.net 4247 acct %s read accounts sduser,sduser,sduser" % PIN_A)
    lines = file_lines() or []
    row("a name listed twice in the accounts list is kept once (sduser)",
        len(lines) == 4 and line_is(lines[3], ["dupacc", "h4.example.net", "4247", "acct", PIN_A, "read", "sduser"]), repr(lines))
    adm1("delete.server dupacc")

    # -- list.servers
    out = adm1("list.servers")
    want = [msg(11434, "alpha1", "host1.example.org:4247", "reader/write", PIN_A[:16] + "...  sduser"),
            msg(11434, "beta", "h2.example.net:4249", "admin/read", PIN_B[:16] + "...  " + msg(11438)),
            msg(11434, "upperok", "host3.example.org:4250", "Remote.Acct/write", PIN_A[:16] + "...  sduser")]
    in_order = all(w in out for w in want) and out.index(want[0]) < out.index(want[1]) < out.index(want[2])
    row("list.servers: one line for each, in the order they were defined: name, host:port, account/mode, the pin shortened to 16 digits and '...', the accounts or 'none'",
        in_order, repr(out[-5:]))
    row("...and NO full pin appears anywhere in the list (the list is not empty: it has the alpha1 line)",
        has_text(out, "alpha1") and not has_text(out, PIN_A) and not has_text(out, PIN_B), repr([x for x in out if PIN_A in x or PIN_B in x]))
    out = adm1("list.servers alpha1")
    row("list.servers alpha1: that server only, with the FULL pin and the date it was defined",
        has_line(out, msg(11434, "alpha1", "host1.example.org:4247", "reader/write", PIN_A + "  sduser"))
        and any(re.fullmatch(re.escape(msg(11435, "@@")).replace("@@", DATE_RE), ln) for ln in out) and not has_text(out, "beta"), repr(out[-4:]))
    out = adm1("LIST.SERVERS ALPHA1")
    row("...the name is converted to lower case", has_line(out, msg(11434, "alpha1", "host1.example.org:4247", "reader/write", PIN_A + "  sduser")), repr(out[-3:]))
    out = adm1("list.servers nosuch")
    row("list.servers of an unknown name: 'No server is defined with the name nosuch'", has_line(out, msg(11430, "nosuch")), repr(out[-3:]))
    out = adm1("list.servers a b")
    row("list.servers with two words: its usage line (11432)", has_line(out, msg(11432)), repr(out[-3:]))
    row("CONTROL: none of the listings changed the file", sw(snap(), first), "")

    # -- replacing a name asks
    before = snap()
    new_cmd = ok_cmd("alpha1", "other.example.org", "4300", "reader", PIN_B, "write")
    prompt = msg(11423, "alpha1", "host1.example.org:4247")
    for answer, label in (("n", "n"), ("", "an empty line"), ("N", "N")):
        out = adm1(new_cmd, answer)
        row("replacing alpha1 with the answer '%s': the question is put, 'Server alpha1 was not changed', and the file is the same bytes" % label,
            has_text(out, prompt) and has_text(out, msg(11426, "alpha1")) and not has(out, SUCCESS) and snap() == before, repr(out[-3:]))
    out = adm1(new_cmd, "maybe", "n")
    row("an answer that is neither y nor n puts the question again, and the n after it ends it: unchanged",
        sum(ln.count(prompt) for ln in out) >= 2 and has_text(out, msg(11426, "alpha1")) and snap() == before, repr(out[-4:]))
    out = adm1(new_cmd)
    row("the question with NO answer in the input (end of input) is a no: unchanged", has_text(out, msg(11426, "alpha1")) and snap() == before, repr(out[-3:]))
    out = adm1(new_cmd, "y")
    lines = file_lines() or []
    row("the answer y replaces it: 'Server alpha1 (other.example.org:4300) was replaced', in the same place, still three lines",
        has_text(out, msg(11425, "alpha1", "other.example.org", "4300")) and len(lines) == 3
        and line_is(lines[0], ["alpha1", "other.example.org", "4300", "reader", PIN_B, "write", ""]), repr(lines))
    row("...the other two lines are as they were", len(lines) == 3 and lines[1:] == before.decode("ascii").split("\n")[1:3], repr(lines))
    row("...and it warns that no account is listed any more (11439) - replacing does not keep the old accounts",
        has_line(out, msg(11439, "alpha1")), repr(out[-3:]))
    out = adm1(ok_cmd("alpha1", "host1.example.org", "4247", "reader", PIN_A, "write accounts sduser no.query"))
    lines = file_lines() or []
    row("NO.QUERY replaces with no question at all", has_text(out, msg(11425, "alpha1", "host1.example.org", "4247")) and not has_text(out, "is already defined")
        and len(lines) == 3 and line_is(lines[0], ["alpha1", "host1.example.org", "4247", "reader", PIN_A, "write", "sduser"]), repr(out[-3:]))
    out = adm1(ok_cmd("beta", "h2.example.net", "4249", "admin", PIN_B, "no.query"), ok_cmd("ALPHA1", "host1.example.org", "4247", "reader", PIN_A, "write accounts sduser"), "Y")
    lines = file_lines() or []
    row("the name is converted before the test (ALPHA1 is alpha1) and the answer Y is accepted", has_text(out, msg(11425, "alpha1", "host1.example.org", "4247")) and len(lines) == 3, repr(out[-3:]))

    # -- boundary controls: the values just inside every limit are accepted, then the values just outside are refused
    ctl = [
        ("a name of 16 characters", ok_cmd("abcdefghijklmnop"), ["abcdefghijklmnop", "valid.example.org", "4247", "acct", PIN_A, "read", ""]),
        ("port 1", ok_cmd("ctl", port="1", extra="no.query"), ["ctl", "valid.example.org", "1", "acct", PIN_A, "read", ""]),
        ("port 65535", ok_cmd("ctl", port="65535", extra="no.query"), ["ctl", "valid.example.org", "65535", "acct", PIN_A, "read", ""]),
        ("a host of 253 characters", ok_cmd("ctl", host="a" * 253, extra="no.query"), ["ctl", "a" * 253, "4247", "acct", PIN_A, "read", ""]),
        ("an IPv6 literal host", ok_cmd("ctl", host="fe80::1", extra="no.query"), ["ctl", "fe80::1", "4247", "acct", PIN_A, "read", ""]),
        ("a host that starts with a digit and holds hyphens", ok_cmd("ctl", host="10-0-0-1.example", extra="no.query"), ["ctl", "10-0-0-1.example", "4247", "acct", PIN_A, "read", ""]),
        ("a remote account of 32 characters", ok_cmd("ctl", account="B" * 32, extra="no.query"), ["ctl", "valid.example.org", "4247", "B" * 32, PIN_A, "read", ""]),
        ("a remote account with dots, underscores and hyphens", ok_cmd("ctl", account="a.b_c-d", extra="no.query"), ["ctl", "valid.example.org", "4247", "a.b_c-d", PIN_A, "read", ""]),
    ]
    for label, cmd, fields in ctl:
        out = adm1(cmd)
        lines = file_lines() or []
        got = [x for x in lines if x.startswith(fields[0] + "|")]
        row("CONTROL, inside the limit: %s is accepted and stored" % label, len(got) == 1 and line_is(got[0], fields) and not has(out, r"is not valid"), repr((out[-2:], got)))

    # -- every invalid field, one at a time, each refused with its own message and each writing NOTHING
    say("  (every invalid field, one at a time: the message of its own, the file the same bytes)")
    for name in ("1abc", "ab_cd", "a.b", "a" * 17, "-abc"):
        refused("name %r" % name, ok_cmd(name), [msg(11414, name)])
    for host in ("-bad.org", ".bad.org", "ba|d.org", "ba/d.org", "bad_host", "a" * 254, "ba@d.org"):
        refused("host %r" % (host if len(host) < 40 else host[:10] + "..."), ok_cmd("hostx", host=host), [msg(11415, host)])
    for port in ("0", "65536", "abc", "-1", "12ab", "1.5", "123456", "99999", "00000"):
        refused("port %s" % port, ok_cmd("portx", port=port), [msg(11416, port)])
    for account in ("bad@acct", "a" * 33, "bad/acct", "bad:acct"):
        refused("remote account %r" % (account if len(account) < 40 else account[:10] + "..."), ok_cmd("accx", account=account), [msg(11417, account)])
    for label, pin in (("63 digits", PIN_A[:63]), ("65 digits", PIN_A + "a"), ("64 with a non-hex character", PIN_A[:63] + "g"), ("xyz", "xyz"), ("64 with a hyphen", PIN_A[:63] + "-")):
        refused("pin of %s" % label, ok_cmd("pinx", pin=pin), [msg(11418)])
    refused("mode 'append'", ok_cmd("modex", extra="append"), [msg(11419, "append")])
    refused("two mode words (read write)", ok_cmd("modex", extra="read write"), [msg(2018, "write")])
    refused("an unknown extra word", ok_cmd("modex", extra="read frobnicate"), [msg(2018, "frobnicate")])
    refused("accounts: an unregistered account", ok_cmd("accl", extra="accounts zznnosuch"), [msg(11421, "zznnosuch")])
    refused("accounts: a registered account first and an unregistered one after it (nothing is written for the good one)",
            ok_cmd("accl", extra="accounts sduser,zznnosuch"), [msg(11421, "zznnosuch")])
    refused("accounts: an empty name between commas", ok_cmd("accl", extra="accounts sduser,,x"), [msg(11420)])
    refused("accounts: a name with a bar", ok_cmd("accl", extra="accounts sduser,a|b"), [msg(11420)])
    refused("accounts: a name of 33 characters", ok_cmd("accl", extra="accounts " + "a" * 33), [msg(11420)])
    long_list = ",".join(("a" * 31 + str(i % 10)) for i in range(64))
    refused("accounts: a list of %d characters (over 2000)" % len(long_list), ok_cmd("accl", extra="accounts " + long_list), [msg(11420)])
    refused("a space inside the remote account shifts the words: the pin position holds 'acct' and a stray word is left",
            "set.server spacex valid.example.org 4247 bad acct %s" % PIN_A, [msg(11418)])
    refused("name, port and pin all wrong at once: every message is shown, still nothing is written",
            ok_cmd("1x", port="0", pin="zz"), [msg(11414, "1x"), msg(11416, "0"), msg(11418)])

    # -- the limit of ten
    lines = file_lines() or []
    fill = [("s%02d" % i) for i in range(1, 30)]
    todo = [n for n in fill if not any(x.startswith(n + "|") for x in lines)][:max(0, 10 - len(lines))]
    out = adm1(*[ok_cmd(n) for n in todo])
    lines = file_lines() or []
    row("filled to ten definitions (%d more were defined)" % len(todo), len(lines) == 10 and all(has_line(out, msg(11424, n, "valid.example.org", "4247")) for n in todo), repr((len(lines), out[-2:])))
    refused("an 11th definition (a new name)", ok_cmd("eleven"), [msg(11422, 10)])
    out = adm1(ok_cmd("s05", host="changed.example.org", extra="no.query"))
    lines = file_lines() or []
    pos = [i for i, x in enumerate(lines) if x.startswith("s05|")]
    row("CONTROL: with ten defined, REPLACING one is still allowed (no new name), and it stays ten",
        has_text(out, msg(11425, "s05", "changed.example.org", "4247")) and len(lines) == 10 and len(pos) == 1, repr(out[-3:]))

    # -- delete.server
    before = snap()
    out = adm1("delete.server nosuch")
    row("delete.server of an unknown name: 'No server is defined with the name nosuch', the file the same bytes", has_line(out, msg(11430, "nosuch")) and snap() == before, repr(out[-3:]))
    for cmd in ("delete.server", "delete.server a b"):
        out = adm1(cmd)
        row("%r: its usage line (11429), the file the same bytes" % cmd, has_line(out, msg(11429)) and snap() == before, repr(out[-3:]))
    keep = [x for x in (file_lines() or []) if not x.startswith("beta|")]
    out = adm1("delete.server beta")
    lines = file_lines() or []
    row("delete.server beta: 'Server beta was deleted', that line gone and the nine others as they were, in order",
        has_line(out, msg(11431, "beta")) and lines == keep and len(lines) == 9, repr((out[-2:], len(lines))))
    out = adm1("delete.server BETA")
    row("...a second time it is not there (11430), and nothing changes", has_line(out, msg(11430, "beta")) and (file_lines() or []) == keep, repr(out[-3:]))
    out = adm1("DELETE.SERVER UPPEROK")
    row("the name is converted to lower case: DELETE.SERVER UPPEROK removes upperok", has_line(out, msg(11431, "upperok")) and not any(x.startswith("upperok|") for x in (file_lines() or [])), repr(out[-3:]))
    out = adm1("list.servers upperok")
    row("...and list.servers no longer finds it", has_line(out, msg(11430, "upperok")), repr(out[-3:]))
    rest = [x.split("|")[0] for x in (file_lines() or [])]
    out = adm1(*["delete.server " + n for n in rest])
    row("every remaining definition deleted (%d)" % len(rest), len(rest) > 0 and all(has_line(out, msg(11431, n)) for n in rest), repr(out[-3:]))
    row("...the file is still there and EMPTY (a list of no servers is a file of no lines), with no copy left", snap() == b"" and not os.path.exists(netfile() + ".new"), repr(snap()))
    out = adm1("list.servers")
    row("...and list.servers says 'No servers are defined' again", has_line(out, msg(11433)), repr(out[-3:]))
    adm1(ok_cmd("alpha1", "host1.example.org", "4247", "reader", PIN_A, "write accounts sduser"))
    row("CONTROL: a definition made after the file was emptied is the only line", len(file_lines() or []) == 1, repr(file_lines()))


# ---- an ordinary session --------------------------------------------------------------------------------------------------------

def ordinary_section():
    say("\n--- an ordinary session cannot run the verbs and cannot write the file ----------------------------------------------------")
    if snap() is None:
        adm1("set.server alpha1 host1.example.org 4247 reader %s write accounts sduser" % PIN_A)
    before = snap()
    row("setup: the definitions file exists and has a definition to protect", before is not None and before.count(b"\n") >= 1, repr(before))
    cmds = ["SET.SERVER hackx evil.example.org 4247 acct %s read" % PIN_A, "DELETE.SERVER alpha1", "LIST.SERVERS"]
    for state, gate in (("the NET gate off", "no"), ("the NET gate ON (it does not give the verbs)", "yes")):
        reg_net(gate)
        out = session(cmds, quiet=True)
        n_ad = sum(1 for ln in out if ln == msg(2001))
        row("an ordinary session with %s: each of the three answers 'Command requires administrator privileges', the file the same bytes" % state,
            n_ad == 3 and snap() == before and not has(out, SUCCESS) and not has_text(out, msg(11433)), repr(out[-4:]))
    reg_net("no")

    nf = netfile()
    prog_w = [
        "program zznetw",
        "   crt 'NW begin'",
        "   openseq '%s' to f1 then crt 'NW read-open OK' else crt 'NW read-open REFUSED ':status()" % nf,
        "   openseq '%s.new' to f2 then crt 'NW new-open OK' else" % nf,
        "      st = status()",
        "      if st = 3035 then",
        "         crt 'NW new-open REFUSED ':st",
        "      end else",
        "         create f2 then crt 'NW new-open CREATED' else crt 'NW new-open FAILED ':st",
        "      end",
        "   end",
        "   dok = @true",
        "   deleteseq '%s', 'netservers' else dok = @false" % SYS,
        "   crt 'NW delete ':(if dok then 'OK' else 'REFUSED')",
        "   crt 'NW end'", "end", ""]
    put(os.path.join(ACCT, "bp", "zznetw"), "\n".join(prog_w))
    reg_os(False)
    out = session(["BASIC bp zznetw", "RUN bp zznetw"], quiet=True)
    got = {m.group(1): m.group(2) for m in (re.match(r"^NW (\S+) (OK|CREATED|REFUSED(?: \d+)?|FAILED(?: \d+)?)$", ln) for ln in out) if m}
    row("os off: a program that opens the file, makes netservers.new and deletes the file by its operating system path is refused each time (3035 for the opens)",
        has(out, r"^NW end$") and got.get("read-open") == "REFUSED 3035" and got.get("new-open") == "REFUSED 3035" and got.get("delete") == "REFUSED",
        repr((got, out[-3:])))
    row("...and the disk agrees: the file is the same bytes and there is no netservers.new", snap() == before and not os.path.exists(nf + ".new"), repr(snap()))
    reg_os(True)
    put(os.path.join(ACCT, "bp", "zznetr"), "\n".join([
        "program zznetr",
        "   openseq '%s' to f1 then crt 'NR read-open OK' else crt 'NR read-open REFUSED ':status()" % nf,
        "   crt 'NR end'", "end", ""]))
    out = session(["BASIC bp zznetr", "RUN bp zznetr"], quiet=True)
    row("CONTROL: the same open with os ON works, so the refusal above is the OS switch and not a file that cannot be opened",
        has(out, r"^NR read-open OK$") and snap() == before, repr(out[-3:]))
    reg_os(False)
    for nm in ("zznetw", "zznetr", "zznkord"):
        for d in ("bp", "bp.out"):
            p = os.path.join(ACCT, d, nm)
            if os.path.exists(p):
                os.remove(p)


SECTIONS = (("gate", gate_section), ("defs", defs_section), ("ordinary", ordinary_section))


def main():
    global BOX, SYS, ACCT, REG
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sections", default="")
    a = ap.parse_args()
    BOX = os.path.abspath(a.dir)
    SYS = os.path.join(BOX, "sys")
    ACCT = os.path.join(SYS, "user_accounts", ACCOUNT)
    REG = os.path.join(SYS, "accounts", ACCOUNT)
    want = set(x for x in a.sections.split(",") if x)
    say("sandbox-sdnet: sandbox  %s" % BOX)
    say("sandbox-sdnet: tree     %s" % SD64)
    say("sandbox-sdnet: user %s; the one account is %s, its register record %s" % (USER, ACCOUNT, REG))
    if a.build:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-sdnet: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(REG):
        bail("there is no register record %s" % REG)

    say("\n--- controls -----------------------------------------------------------------------------------------------------")
    out = session(["WHO.AM.I"], quiet=True)
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of %s and NOT an administrator (WHO.AM.I says Admin? %s)" % (ACCOUNT, adm.group(1) if adm else "-"),
        has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        bail("the session is privileged; its refusals prove nothing")
    out = adm1("WHO.AM.I")
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("CONTROL: the ADMIN lane is an administrator (WHO.AM.I says Admin? %s)" % (adm.group(1) if adm else "-"), bool(adm) and adm.group(1) == "Yes", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "Yes"):
        bail("the administrator lane is not an administrator: every set.server row would be meaningless")
    prepare()

    for name, section in SECTIONS:
        if not want or name in want:
            section()

    say("")
    say("sandbox-sdnet: %d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
