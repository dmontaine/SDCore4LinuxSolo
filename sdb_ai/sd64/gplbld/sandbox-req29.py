#!/usr/bin/env python3
#
# sandbox-req29.py - API request 29 (open an 'account;file' file, the SDNet request of apisrvr's vb.open.sdnet) and the Solo NET gate, through a REAL logged-in
#                    API session on Solo's own sandbox.  No install, no sudo.  Solo's copy of the idea of SD Core's sandbox-req29.py (sections A to E, 18 Oct 26).
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-req29.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py (Solo's own).  With --build it is built first from THIS tree (it must be empty or absent).
# Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
# START-HISTORY:
# 21 Oct 26 dm  SOLO CARRY 10 (SD Core's S.73 item 1), rows written FIRST: section X is no longer a documented limit.  The row X1 that said a pointer outside the account opens with the 'os'
#               switch off is replaced by Core's rows X0 to X19 on Solo's one account (register field 8 toggled under the open session).
# 20 Oct 26 dm  Written for Solo carry 8 (the owner's "q3 c": carry Core's fix for API request 29 with a NET gate), FIRST, and run red on Solo Dev 03deb57.
#               The claim, read from apisrvr and never run: with bit 2 of NETFILES set in sd.conf, any API login can open the VOC-named file of ANY directory
#               through request 29, because the request is gated by the bit alone - not by the own-account rule request 3 applies, not by a NET gate, and not by
#               SDCLIENT (which request 4 honours).  Core's rows speak the wire over a local pipe after a local login; Solo has no local login, so this uses
#               sandbox-apifile.py's Wire (TLS 1.3, then the SCRAM-SHA-256 login bound to the TLS session, then the account) and takes its harness from that file.
#               What differs from Core's suite, because Solo has ONE account: Core's "an account the user is not a member of" is "another account's register
#               record" (zzother, whose directory is a decoy holding its own record) and SDSYS; Core's group and suspended fixtures are the one account's
#               suspension, written into the register while the session is open (the request reads the record when it is asked); the NET gate is register
#               field 15 as in Core, off unless the word is yes, turned on by the administrator's verb SET.NET.ACCESS (Core: MODIFY.ACCOUNT NET-ON).
# END-HISTORY
#
# THE INSTRUMENT.  Every session is a REAL `sd -n -q` started as the socket activator starts it; the evidence is the record that comes back through request 6,
# compared with the record planted in the file on the DISK.  The rows' expected values come from what this suite wrote, never from the server's answer, and a
# row that "opens" must also READ BACK the planted record: a file number alone proves nothing.
#
#   NULL CASES REFUSED OUT LOUD.  The suite stops (exit 2) unless: the fixture file holds the record planted in it (read in an ordinary session first); the
#   register as the install made it has no 'yes' in field 15 (the delivered state: off); the control login works; and with NETFILES unset request 29 is refused
#   (so a request that opens a file at all is known to need the bit).
#
#   A  no NETFILES in sd.conf: request 29 is refused whoever asks (the bit is what lets it work at all)
#   B  NETFILES=2, the NET gate on: the control that request 29 works for the account's own file, and adds no refusal to the audit trail
#   C  the account rule: another account's register record (a decoy directory), SDSYS, an account named by a path, and the account suspended after the login
#   D  the NET gate: off ('no') and absent (the register as delivered)
#   X  an F-pointer in the account's VOC that leads OUT of the account (an absolute path, a relative one that climbs out, a symbolic link, a sibling directory whose name begins with the
#      account's, a system directory, a dictionary half) is refused (error ELSE, status 3035, audited) unless the account holds the 'os' switch; the same pointers open with it on; the
#      switch is read at each request (S.73 item 1, SD Core 4f38ad4: until 21 Oct 26 this section recorded the opposite as a documented limit)
#   E  SDCLIENT=1 with NETFILES=2: request 4 is refused (the control), and so must request 29 be
#   V  the verb SET.NET.ACCESS (administrator only; no argument shows; ON and OFF write field 15 and nothing else; the syntax message), and request 29 after it

import importlib.util
import os
import re
import shutil
import signal
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
_spec = importlib.util.spec_from_file_location("apifile", os.path.join(HERE, "sandbox-apifile.py"))
af = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(af)
say = af.say
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ACCOUNT = "sduser"
SECRETS = []
passed = failed = 0
FAILED_IDS = []
BOX = SYS = ACCT = REG = DECOY = ""
BASE_CONF = ""
PLANTED = "secret of sduser"
PLANTED_DECOY = "secret of the decoy"
PLANTED_SYS = "secret of sdsys"
PLANTED_OUTSIDE = "secret outside the account"
PLANTED_SIB = "next door, and a prefix is not inside"
NET_FIELD = 15


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
    say("sandbox-req29: CANNOT RUN - " + msg)
    for w in list(af.WIRES):
        w.kill()
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


def plain(cmds, unlock=False, timeout=300):
    """A session of sduser on a pipe, NOT an administrator unless unlock=True (ADMIN and the administrator password typed first).  Returns the lines printed
    after the TERM line, the echoed commands (they begin with a colon) and blank lines left out."""
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    env.pop("SDTEST_ADMIN", None)
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
    """An internal session (SDSYS): sandbox-fromtree.py's `sess` writes the one-shot marker.  Returns the lines printed, as plain()."""
    say("    > [internal] " + " | ".join(cmds))
    r = subprocess.run([sys.executable, TOOL, BOX, "sess", SYS] + cmds, capture_output=True, text=True, errors="replace", timeout=600)
    out = ANSI.sub("", r.stdout + r.stderr).split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def has(lines, pattern):
    return any(re.search(pattern, ln) for ln in lines)


def put(path, text):
    with open(path, "w", encoding="latin-1") as f:
        f.write(text)


def reg_read(path=None):
    with open(path or REG, encoding="latin-1") as f:
        lines = f.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def reg_set(n, value, path=None):
    """Field N (1-based) of a register record becomes VALUE; the other fields are kept, and a short record is padded with empty fields."""
    lines = reg_read(path)
    lines += [""] * (n - len(lines))
    lines[n - 1] = value
    put(path or REG, "\n".join(lines) + "\n")


def audit_off():
    """Size of the sandbox's audit file, which SD appends to and never creates: it is made, empty, when it is missing.  None when it cannot be."""
    path = os.path.join(SYS, "audit")
    try:
        if not os.path.exists(path):
            with open(path, "ab"):
                pass
        return os.path.getsize(path)
    except OSError:
        return None


def audit_new(off):
    """What the audit trail gained since OFF; None when it cannot be read (a row that needs it then FAILS, it does not pass for want of a line to look at)."""
    if off is None:
        return None
    try:
        with open(os.path.join(SYS, "audit"), "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def audit_has(new, pattern):
    return new is not None and re.search(pattern, new, re.M) is not None


def restart(*conf_lines):
    """Stop the sandbox's SD, write sd.conf as it was built plus CONF_LINES, start it again.  False when it does not come back."""
    subprocess.run([sys.executable, TOOL, BOX, "stop"], capture_output=True, text=True, errors="replace", timeout=120)
    put(os.path.join(BOX, "sd.conf"), BASE_CONF + ("".join(l + "\n" for l in conf_lines) if conf_lines else ""))
    r = subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    say("    > sd.conf %s: %s" % ("+ " + " ".join(conf_lines) if conf_lines else "as built", "restarted" if r.returncode == 0 else "START FAILED: " + r.stdout[-200:]))
    return r.returncode == 0


def open29(w, arg):
    r = w.req(29, arg)
    if r and r[0] == 0 and len(r[2]) == 2:
        return struct.unpack("<h", r[2])[0], r
    return None, r


def read_back(w, fno, rid=b"k1"):
    r = w.req(6, struct.pack("<h", fno) + rid, shown="fno %d id %r" % (fno, rid))
    return r[2].decode("latin-1") if r and r[0] == 0 else None


def msg(n):
    with open(os.path.join(SYS, "messages", str(n)), encoding="utf-8", errors="replace") as f:
        return f.read().strip("\n")


def main():
    global BOX, SYS, ACCT, REG, DECOY, BASE_CONF
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-req29.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    ACCT = os.path.join(SYS, "user_accounts", ACCOUNT)
    REG = os.path.join(SYS, "accounts", ACCOUNT)
    DECOY = os.path.join(SYS, "user_accounts", "zzdecoy")
    af.BOX, af.SYS, af.SD = BOX, SYS, os.path.join(SYS, "bin", "sd")
    say("sandbox-req29: sandbox  %s" % BOX)
    say("sandbox-req29: tree     %s" % os.path.dirname(HERE))
    if os.geteuid() == 0:
        bail("this is root; Solo never runs as root")
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-req29: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    af.PW = secret("account.pw")
    with open(os.path.join(BOX, "sd.conf"), encoding="latin-1") as f:
        BASE_CONF = f.read()
    if BASE_CONF and not BASE_CONF.endswith("\n"):
        BASE_CONF += "\n"
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)

    try:
        say("\n--- preparation: a file zzsec holding one record the DISK is read back for, and a decoy account directory --------------------")
        reg0 = reg_read()
        row("S0 the register as the install made it has NO 'yes' in field %d (the delivered state of the NET gate: off); fields: %r" % (NET_FIELD, reg0[:8]),
            len(reg0) < NET_FIELD or reg0[NET_FIELD - 1].strip().lower() != "yes", repr(reg0))
        plain(["CREATE.FILE zzsec DIRECTORY"])
        put(os.path.join(ACCT, "zzsec", "k1"), PLANTED)
        put(os.path.join(ACCT, "bp", "zzmk"), "   open 'zzsec' to f else crt 'NOFILE' ; stop\n   read r from f, 'k1' else r = '?'\n   crt 'MK[':r:']'\nend\n")
        out = plain(["BASIC bp zzmk", "RUN bp zzmk"])
        row("S1 the fixture file holds the planted record, read in an ordinary session of sduser BEFORE the register is changed",
            has(out, r"^MK\[%s\]$" % re.escape(PLANTED)), repr(out[-4:]))
        if not has(out, r"^MK\[%s\]$" % re.escape(PLANTED)):
            bail("the fixture file does not hold the planted record, so no row below could be believed")
        shutil.rmtree(DECOY, ignore_errors=True)
        shutil.copytree(ACCT, DECOY, symlinks=True)
        put(os.path.join(DECOY, "zzsec", "k1"), PLANTED_DECOY)
        # another account's register record, NET gate on, its directory the decoy: nothing in Solo says its user may enter it
        decoy_reg = os.path.join(SYS, "accounts", "zzother")
        put(decoy_reg, "\n".join([DECOY, "", "", "", "", "", "no", "no", "", "", "", "", "", "", "yes"]) + "\n")
        # and a file of the same name in SDSYS's own account, made by an internal session: the row for 'sdsys;zzsec' then has something to open, so a refusal
        # is the rule's and not a missing file's
        internal(["DELETE.FILE zzsec NO.QUERY", "CREATE.FILE zzsec DIRECTORY"])
        put(os.path.join(SYS, "zzsec", "k1"), PLANTED_SYS)
        reg_set(NET_FIELD, "yes")        # the NET gate ON for sduser: sections B, C and E measure the account rule and SDCLIENT, not the gate

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- A. no NETFILES in sd.conf: request 29 is refused whoever asks (the bit is what lets it work at all) -----------------------")
        if not restart():
            bail("SD does not start with the sandbox's own sd.conf")
        w = af.Wire("A")
        fno, r = open29(w, "sduser;zzsec")
        row("A1 request 29 'sduser;zzsec' with NETFILES unset (0): no file number comes back - refused by the bit (error ELSE)", fno is None and r is not None and r[0] == 2, repr(r))
        w.close()

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- B. NETFILES=2 (bit 2 set), the NET gate on: the control that request 29 works for the account's own file -----------------")
        if not restart("NETFILES=2"):
            bail("SD does not start with NETFILES=2 in sd.conf")
        w = af.Wire("B")
        off = audit_off()
        row("B0a the audit file can be read (a row that needs a line from it fails, it does not pass for want of one)", off is not None, repr(off))
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        row("B1 CONTROL: request 29 'sduser;zzsec' (the account's own file, NET gate on) returns a file number and READ of k1 gives the planted %r" % PLANTED,
            fno is not None and back == PLANTED, repr((fno, back, r)))
        new = audit_new(off)
        row("B2 CONTROL OF THE AUDIT ROWS: the good open above added NO refusal to the audit trail (no 'request=29' line, no 'account refused' line) - a reading that matched "
            "every line would fail here", new is not None and "request=29" not in new and "account refused" not in new, repr(new))

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- C. the account rule: the same session asks for a file of an account it is not -----------------------------------------")
        w2 = af.Wire("C1")
        r = w2.req(3, "zzother")
        txt = w2.req(2)
        row("C1 CONTROL (the rule): request 3 'zzother' - another account's register record - is refused, error ERROR with the text of 10003 (%r)" % msg(10003),
            r is not None and r[0] == 3 and txt is not None and txt[2].decode("latin-1") == msg(10003), repr((r, txt)))
        r = w2.req(3, "sdsys")
        row("C2 CONTROL (the rule): request 3 'sdsys' is refused too (error ERROR)", r is not None and r[0] == 3, repr(r))
        w2.close()
        off = audit_off()
        fno, r = open29(w, "zzother;zzsec")
        back = read_back(w, fno) if fno is not None else None
        new = audit_new(off)
        say("      [evidence] on the disk the decoy file holds %r; request 29 'zzother;zzsec' gave file number %r and READ k1 gave %r" % (PLANTED_DECOY, fno, back))
        row("C3 request 29 'zzother;zzsec' (another account's record, its NET gate on): refused - no file number, and the record %r is not read" % PLANTED_DECOY,
            fno is None and back != PLANTED_DECOY, "OPENED fno %r and READ %r  <- the claim is true" % (fno, back))
        row("C3a ...and the refusal is on the audit trail, in the words of request 3's refusal: 'account refused branch=4 not.own.account user=sduser account=zzother' "
            "(the CALLER sees only 10003; the administrator sees why)",
            audit_has(new, r"account refused branch=4 not\.own\.account user=sduser account=zzother$"), repr(new))
        off = audit_off()
        fno, r = open29(w, "sdsys;zzsec")
        back = read_back(w, fno) if fno is not None else None
        new = audit_new(off)
        row("C4 request 29 'sdsys;zzsec' (SDSYS is never a target in Solo; its file zzsec holds %r): refused, and the record is not read" % PLANTED_SYS,
            fno is None and back != PLANTED_SYS, "OPENED fno %r and READ %r" % (fno, back))
        row("C4a ...audited as 'account refused branch=4 not.own.account user=sduser account=sdsys'",
            audit_has(new, r"account refused branch=4 not\.own\.account user=sduser account=sdsys$"), repr(new))
        off = audit_off()
        fno, r = open29(w, DECOY + ";zzsec")
        back = read_back(w, fno) if fno is not None else None
        new = audit_new(off)
        row("C5 request 29 with the account given as a PATH (%s;zzsec): refused - a path names no register record, so nothing says who may enter it" % DECOY,
            fno is None and back not in (PLANTED_DECOY, PLANTED), "OPENED fno %r and READ %r" % (fno, back))
        row("C5a ...audited as 'api refused request=29 reason=no register record user=sduser account=<the path, lower case>' - the register rule, not the own-account "
            "rule that would refuse an empty record next",
            audit_has(new, r"api refused request=29 reason=no register record user=sduser account=%s$" % re.escape(DECOY.lower())), repr(new))
        # suspended AFTER the login: request 29 reads the register record when it is asked, as the rule for entering an account does
        reg_set(5, "SUSPENDED")
        off = audit_off()
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        new = audit_new(off)
        reg_set(5, "")
        row("C6 request 29 'sduser;zzsec' after the account was marked SUSPENDED in the register (the NET gate still on): refused",
            fno is None and back != PLANTED, "OPENED fno %r and READ %r" % (fno, back))
        row("C6a ...audited as 'account refused branch=2 suspended account=sduser'", audit_has(new, r"account refused branch=2 suspended account=sduser$"), repr(new))
        off = audit_off()
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        new = audit_new(off)
        row("C7 CONTROL AFTER THE REFUSALS (the suspension taken off again): 'sduser;zzsec' opens and reads %r (so the refusals above are the rule and not a broken "
            "session)" % PLANTED, fno is not None and back == PLANTED, repr((fno, back)))
        row("C7a CONTROL OF THE AUDIT ROWS: that good open added no refusal line", new is not None and "request=29" not in new and "account refused" not in new, repr(new))

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- D. the NET gate: the account's own file, the gate 'no' and then absent (the register as delivered) --------------------------")
        for label, value in (("D1", "no"), ("D2", "")):
            reg_set(NET_FIELD, value)
            off = audit_off()
            fno, r = open29(w, "sduser;zzsec")
            back = read_back(w, fno) if fno is not None else None
            new = audit_new(off)
            what = "'no' in register field %d" % NET_FIELD if value else "field %d blank (no word: the register as delivered)" % NET_FIELD
            row("%s request 29 'sduser;zzsec' with the NET gate off (%s): refused (the NET gate is the account's permission to use SDNet files)" % (label, what),
                fno is None and back != PLANTED, "OPENED fno %r and READ %r" % (fno, back))
            row("%sa ...audited as 'api refused request=29 reason=net gate off user=sduser account=sduser'" % label,
                audit_has(new, r"api refused request=29 reason=net gate off user=sduser account=sduser$"), repr(new))
        reg_set(NET_FIELD, "yes")

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- X. an F-pointer OUTSIDE the account: refused unless the account holds the os switch (S.73 item 1, SD Core 4f38ad4; a documented limit in Solo until 21 Oct 26) ------------")
        # An F-pointer in the account's VOC at a directory OUTSIDE the account (written by an internal program: the VOC is the administrator's).  Request 29 opens the file the VOC names with
        # openpath from an internal program, which the OS gate exempts, so the OS switch (register field 8) was never asked of a path that leads out of the account.  The same eight pointers
        # as Core's section X, in the one account Solo has; the switch is toggled in the register under the open session, which also shows it is read at each request.
        outside = os.path.join(SYS, "zzoutside")
        sib = ACCT + "-sib"
        link = os.path.join(ACCT, "zzlink")
        for p_ in (outside, sib):
            shutil.rmtree(p_, ignore_errors=True)
            os.makedirs(p_)
        put(os.path.join(outside, "k1"), PLANTED_OUTSIDE)
        put(os.path.join(sib, "k1"), PLANTED_SIB)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(outside, link)
        pointers = [("zzpabs", outside, ""),                  # an absolute path outside the account
                    ("zzprel", "../../zzoutside", ""),        # a relative path that climbs out of the account
                    ("zzplnk", "zzlink", ""),                 # a name inside the account that is a symbolic link to the outside directory
                    ("zzpsib", sib, ""),                      # the directory next to the account whose name begins with the account's own name
                    ("zzpsys", "@SDSYS/messages", ""),        # a system directory of the installation
                    ("zzpdic", "zzsec", outside),             # the data half is the account's own file, the DICTIONARY half is outside
                    ("zzpin", "zzsec", ""),                   # the control: a file of the account, by a relative path
                    ("zzpinab", ACCT + "/zzsec", "")]         # the control: the same file by an absolute path inside the account
        put(os.path.join(SYS, "bp", "zzptrfix"), "\n".join(["$internal", "   openpath '%s/voc' to v else crt 'FIX no voc' ; stop" % ACCT]
            + ["   write 'F':@fm:'%s':@fm:'%s' to v, '%s'" % (path, dpath, pid) for pid, path, dpath in pointers] + ["   crt 'FIX done'", "end", ""]))
        out = internal(["BASIC bp zzptrfix", "RUN bp zzptrfix"])
        row("X0 the eight F-pointers are written into sduser's VOC by an internal program", has(out, r"^FIX done$"), repr(out[-4:]))
        if not has(out, r"^FIX done$"):
            bail("the pointers were not written into the VOC, so no row below can be believed")
        reg_set(8, "")
        reg_now = reg_read()
        say("      [evidence] register record: field 8 (os) %r, field 15 (net) %r; outside directory %s holds k1 = %r; link %s -> %s; sibling %s holds k1 = %r"
            % (reg_now[7:8], reg_now[14:15], outside, open(os.path.join(outside, "k1")).read(), link, os.readlink(link), sib, open(os.path.join(sib, "k1")).read()))
        row("X0a the register says os OFF and the NET gate ON (the rows below are only meaningful if it does)", reg_now[7:8] == [""] and reg_now[14:15] == ["yes"], repr(reg_now))
        cases = [    # (what the request names, what it is, the record the disk holds in what it leads to; None: only the file number is judged)
            ("zzpabs", "an absolute path outside the account", PLANTED_OUTSIDE),
            ("zzprel", "a relative path that climbs out of the account (../../zzoutside)", PLANTED_OUTSIDE),
            ("zzplnk", "a name inside the account that is a symbolic link to the outside directory", PLANTED_OUTSIDE),
            ("zzpsib", "the directory next to the account whose name begins with the account's own name", PLANTED_SIB),
            ("zzpsys", "a system directory of the installation (@SDSYS/messages)", None),
            ("DICT zzpdic", "a pointer whose DICTIONARY half is outside (its data half is the account's own file)", PLANTED_OUTSIDE)]
        controls = [("zzpin", "the account's own file by a relative path"), ("zzpinab", "the account's own file by an absolute path inside the account"),
                    ("zzpdic", "the data half of the dictionary pointer (the account's own file)")]
        for i, (name, what, planted) in enumerate(cases):
            off = audit_off()
            fno, r = open29(w, "sduser;" + name)
            back = read_back(w, fno) if fno is not None else None
            new = audit_new(off)
            say("      [evidence] request 29 'sduser;%s' (%s), os OFF: file number %r, READ k1 %r, the disk holds %r" % (name, what, fno, back, planted))
            row("X%d request 29 'sduser;%s' - %s - with the os switch OFF: refused with error ELSE and status 3035 (permission), no file number, and the planted record is not read" % (2 + i, name, what),
                fno is None and r is not None and r[0] == 2 and r[1] == 3035 and (planted is None or back != planted),
                "OPENED fno %r and READ %r  <- the claim is true; reply %r" % (fno, back, r))
            if i in (0, 5):
                row("X%da ...and the refusal is on the audit trail, in lower case: 'api refused request=29 reason=os gate off user=sduser account=sduser path=<the path the pointer names>'" % (2 + i),
                    audit_has(new, r"api refused request=29 reason=os gate off user=sduser account=sduser path=/.+$"), repr(new))
        for i, (name, what) in enumerate(controls):
            off = audit_off()
            fno, r = open29(w, "sduser;" + name)
            back = read_back(w, fno) if fno is not None else None
            new = audit_new(off)
            row("X8%s CONTROL (inside the account): request 29 'sduser;%s' - %s - opens and reads %r with the os switch OFF, and the audit trail gains no refusal" % ("abc"[i], name, what, PLANTED),
                fno is not None and back == PLANTED and new is not None and "request=29" not in new, repr((fno, back, r, new)))
        reg_set(8, "yes")
        off = audit_off()
        for i, (name, what, planted) in enumerate(cases):
            fno, r = open29(w, "sduser;" + name)
            back = read_back(w, fno) if fno is not None else None
            say("      [evidence] request 29 'sduser;%s' (%s), os ON: file number %r, READ k1 %r, the disk holds %r" % (name, what, fno, back, planted))
            if planted is None:
                row("X%d request 29 'sduser;%s' - %s - with the os switch ON (turned on in the register under the open session): opens" % (11 + i, name, what), fno is not None, repr((fno, r)))
            else:
                row("X%d request 29 'sduser;%s' - %s - with the os switch ON: opens and reads the planted %r" % (11 + i, name, what, planted), fno is not None and back == planted, repr((fno, back, r)))
        new = audit_new(off)
        row("X17 ...and no refusal is on the audit trail for any of them", new is not None and "request=29" not in new, repr(new))
        reg_set(8, "")
        fno, r = open29(w, "sduser;zzpabs")
        back = read_back(w, fno) if fno is not None else None
        row("X19 the os switch is taken off again in the register AFTER the session signed on and after it was used: request 29 'sduser;zzpabs' is refused now (the register is read at each "
            "request, as the NET gate is)", fno is None and r is not None and r[0] == 2 and r[1] == 3035 and back != PLANTED_OUTSIDE, "OPENED fno %r and READ %r; reply %r" % (fno, back, r))
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        row("X9 CONTROL AFTER THE REFUSALS: 'sduser;zzsec' still opens and reads %r (so the refusals above are the rule and not a broken session)" % PLANTED, fno is not None and back == PLANTED, repr((fno, back)))
        for p_ in (outside, sib):
            shutil.rmtree(p_, ignore_errors=True)
        if os.path.lexists(link):
            os.remove(link)
        for d_ in ("bp", "bp.out"):
            p_ = os.path.join(SYS, d_, "zzptrfix")
            if os.path.exists(p_):
                os.remove(p_)
        w.close()

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- E. SDCLIENT=1 with NETFILES=2: no open from an API client; request 29 is an open ----------------------------------------")
        if not restart("NETFILES=2", "SDCLIENT=1"):
            bail("SD does not start with NETFILES=2 and SDCLIENT=1")
        w = af.Wire("E")
        r = w.req(4, "zzsec")
        row("E1 CONTROL: request 4 (open) 'zzsec' is refused under SDCLIENT=1 (error ON.ERROR, the 5262 text: file access is disabled)", r is not None and r[0] == 1, repr(r))
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        row("E2 request 29 'sduser;zzsec' under SDCLIENT=1 (the account's own file, NET gate on): refused like request 4", fno is None and back != PLANTED,
            "OPENED fno %r and READ %r" % (fno, back))
        w.close()

        # --------------------------------------------------------------------------------------------------------------------
        say("\n--- V. the verb SET.NET.ACCESS: the administrator turns the NET gate on and off ----------------------------------------------")
        reg_set(NET_FIELD, "")
        before = reg_read()
        out = plain(["SET.NET.ACCESS ON"])
        row("V1 an ordinary session is refused (2001, 'Command requires administrator privileges') and the register is unchanged",
            has(out, r"^Command requires administrator privileges$") and reg_read() == before, "output=%r" % (out,))
        out = plain(["SET.NET.ACCESS"], unlock=True)
        row("V2 no argument shows the state (11928) and changes nothing", has(out, r"^Account sduser has NET no$") and reg_read() == before, "output=%r" % (out,))
        off = audit_off()
        out = plain(["SET.NET.ACCESS ON"], unlock=True)
        new = audit_new(off)
        now = reg_read()
        row("V3 ON as the administrator: 'Account sduser has NET yes', field %d is yes and every other field is as it was" % NET_FIELD,
            has(out, r"^Account sduser has NET yes$") and len(now) >= NET_FIELD and now[NET_FIELD - 1] == "yes"
            and all(now[i] == (before[i] if i < len(before) else "") for i in range(len(now)) if i != NET_FIELD - 1), "output=%r register=%r" % (out, now))
        row("V3a ...and the change is on the audit trail in lower case: 'set.net.access on account=sduser'", audit_has(new, r"set\.net\.access on account=sduser$"), repr(new))
        out = plain(["SET.NET.ACCESS ON"], unlock=True)
        row("V4 ON again says it already had that access (10080) and writes nothing", has(out, r"already had that access; nothing changed"), "output=%r" % (out,))
        w = af.Wire("V5")
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        row("V5 END TO END: with the gate turned on by the verb, NETFILES=2 and SDCLIENT=1 still refuse (the server is the one of section E): no file number",
            fno is None, "OPENED fno %r and READ %r" % (fno, back))
        w.close()
        if not restart("NETFILES=2"):
            bail("SD does not start with NETFILES=2 in sd.conf")
        w = af.Wire("V6")
        fno, r = open29(w, "sduser;zzsec")
        back = read_back(w, fno) if fno is not None else None
        row("V6 END TO END: the same register, SDCLIENT off: request 29 'sduser;zzsec' opens and reads %r" % PLANTED, fno is not None and back == PLANTED, repr((fno, back)))
        out = plain(["SET.NET.ACCESS OFF"], unlock=True)
        now = reg_read()
        row("V7 OFF: 'Account sduser has NET no' and field %d is no" % NET_FIELD,
            has(out, r"^Account sduser has NET no$") and len(now) >= NET_FIELD and now[NET_FIELD - 1] == "no", "output=%r register=%r" % (out, now))
        fno, r = open29(w, "sduser;zzsec")
        row("V8 the change is seen by the running session at its next request (the record is read when the request is asked): request 29 is refused now",
            fno is None, "OPENED fno %r" % (fno,))
        w.close()
        before = reg_read()
        out = plain(["SET.NET.ACCESS MAYBE", "SET.NET.ACCESS ON OFF", "SET.NET.ACCESS SH ON", "SET.NET.ACCESS NET"], unlock=True)
        row("V9 a word that is not on or off, two words, another switch's name and a bare 'net' are each the syntax message (11927); the register is unchanged",
            sum(1 for ln in out if ln.startswith("Syntax: set.net.access")) == 4 and reg_read() == before, "output=%r" % (out,))
        out = plain(["set.net.access on", "SET.NET.ACCESS Off", "set.net.access ON"], unlock=True)
        now = reg_read()
        row("V10 the words are case blind (lower and upper case both work): the last command, ON, leaves field %d yes" % NET_FIELD,
            len(now) >= NET_FIELD and now[NET_FIELD - 1] == "yes", "output=%r register=%r" % (out, now))
        w.close()
    finally:
        for w in list(af.WIRES):
            w.kill()
        try:
            reg_set(NET_FIELD, "")
            reg_set(5, "")
        except OSError:
            pass
        for n in ("zzother",):
            p = os.path.join(SYS, "accounts", n)
            if os.path.exists(p):
                os.remove(p)
        restart()
        internal(["DELETE.FILE zzsec NO.QUERY"])
        subprocess.run([os.path.join(SYS, "bin", "sd"), "-cleanup"], env=af.env(), capture_output=True, timeout=60)
        subprocess.run([sys.executable, TOOL, BOX, "stop"], capture_output=True, text=True, errors="replace", timeout=120)
    say("\nsandbox-req29: %d passed, %d failed" % (passed, failed))
    if passed + failed == 0:
        bail("no row ran - a broken test, not a pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
