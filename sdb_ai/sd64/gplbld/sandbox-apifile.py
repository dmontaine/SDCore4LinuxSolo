#!/usr/bin/env python3
#
# sandbox-apifile.py - API requests 32 and 33 (file lock, file unlock) act on the file number the client names, and the text of an ON ERROR
#                      reply belongs to the request that got it, through a REAL logged-in API session on Solo's own sandbox.
#                      No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-apifile.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py (Solo's own).  With --build it is built first from THIS tree (it must be empty or absent).
# Exit 0 every row passed, 1 a row failed, 2 it could not run.  Set SDSOLOBOX_KEYSET so as not to meet another sandbox's keys.
#
# START-HISTORY:
# 20 Oct 26 dm  Written for Solo carry 3.  The two defects are SD Core's K8a and K1 (19 Oct 26, sandbox-req29.py sections F and G): apisrvr's requests 32 and 33
#               used `files(i)`, the scratch variable of the last open, instead of `files(fno)`, so a lock or an unlock went to whichever file had been opened last;
#               and an ON ERROR reply carried @abort.message, which a refusal sets and nothing cleared, so a WRITE with an over-long id answered the text of the last
#               refusal.  Core's rows speak the wire over a local pipe after a local login; Solo has no local login (SDConnectLocal is disabled, request 25 refused),
#               so this suite does what Solo's clients do: TLS 1.3, then the SCRAM-SHA-256 login bound to the TLS session, with gplbld/scram-probe.py's own code (no SD
#               code on the client side), then the account.  Sections F and G of Core's suite, the same requests, bodies and expectations; nothing of its section A-E
#               (request 29 and the NET gate: Solo has neither) and nothing of netfake.py.
# END-HISTORY
#
# THE INSTRUMENT.  Each session is a REAL `sd -n -q` process started as the socket activator starts it (descriptors 0, 1 and 2 the accepted TCP connection) in
# the sandbox; the client is Python with libssl through scram-probe.py's Tls class; the login is SCRAM with the sandbox's own account password, read from
# <dir>/account.pw and NEVER printed (its length is).  Every request and every reply is printed.  The rows' expected values come from what the suite did (which
# session took which lock), never from the server's own words, apart from the ON ERROR text, which is compared with message 5263 as the sandbox was built.
#
#   NULL CASES REFUSED OUT LOUD.  The suite stops (exit 2) when: the SCRAM login is not VERIFIED, the account is not entered, three files do not open with three
#   different numbers, the control (a lock taken and refused by number) does not behave, or no row ran.
#
#   F  file locks: S1 locks zzsec by number; S2 (the same account, a second session) asks for the lock on each of three files (no wait) and LOCKED says where S1's lock is;
#      unlock goes to the file named; the BLOCKING form (the wait flag set) holds the request back until the lock is free and locks the file asked for
#   G  the text of an ON ERROR reply: after a refusal that has a text, a WRITE whose ON ERROR clause has nothing to say answers ON ERROR with NO text
#   S  the OS switches over the API (20 Oct 26, the Solo OS switch): the server reads fields 7 and 8 of the register when it enters the account; SH OFF is
#      refused (10053) and SH ON runs, the sentinel on the disk being the evidence.  K now turns the SH switch on for its own rows: its program waits in SH sleep
#      and SH is OFF as delivered.
#   C2 S.71 (SD Core, 20 Oct 26) the reply to an INPUT prompt declares a length the server cannot accept ('garb' = 1,651,663,207; 5, below the header): the server
#      ends the session at once and does not spin (the second packet reader, process_client_input; Core's part C2)
#   K  S.71 CLEARINPUT after the connection has gone: the command waits in SH sleep, the client closes, CLEARINPUT then runs: the server ends and does not spin
#   L  S.71's limit BEFORE the login, which is Solo's own (20 Oct 26): a first packet declaring 65,537 or 1,000,000,000 bytes is refused, 65,536 is not; after the login a
#      request of 3 MB is written and read back and a declared 1,000,000,000 is waited for.  Core asks `is_sdApiSrvr && geteuid() == 0`; Solo's server is never root, so
#      it asks the flag api_logged_in, which K$SET.USERNAME sets once the SCRAM proof has been accepted
#      (keyready / keyin; Core's part K).  What a row looks at is the server's process family (/proc: its session id): is anything of it still there N seconds
#      after, and how many CPU ticks did the survivor use in one second (100 is a whole processor)

import importlib.util
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
_spec = importlib.util.spec_from_file_location("scram_probe", os.path.join(HERE, "scram-probe.py"))
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)
sp.say = lambda text: None        # the probe's own chatter is off; every request and reply is printed here

USER = "sduser"                   # the one account (sddefs.h SOLO_ACCOUNT_NAME): the SCRAM user and the account entered
SV = {0: "OK", 1: "ON.ERROR", 2: "ELSE", 3: "ERROR", 4: "LOCKED"}
BOX = SYS = SD = PW = None
passed = failed = 0
WIRES = []


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
    say("sandbox-apifile: CANNOT RUN - " + msg)
    for w in list(WIRES):
        w.kill()
    sys.exit(2)


def env():
    e = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    e.pop("SSH_CONNECTION", None)
    e.pop("SSH_TTY", None)
    return e


class Wire:
    """One logged-in API session: a real `sd -n -q` on an accepted connection, TLS, SCRAM, then the account."""

    def __init__(self, tag_, login=True):
        self.tag = tag_
        self.pending = None
        self.th = None
        self.box = []
        os.makedirs(os.path.join(BOX, "sd-tls"), mode=0o700, exist_ok=True)
        lst = socket.socket()
        lst.bind(("127.0.0.1", 0))
        lst.listen(2)
        cli = socket.create_connection(lst.getsockname())
        conn, _ = lst.accept()
        lst.close()
        self.p = subprocess.Popen([SD, "-n", "-q"], stdin=conn, stdout=conn, stderr=conn, start_new_session=True, env=env(), cwd=SYS)
        conn.close()
        WIRES.append(self)
        say("    > wire %s: started `%s -n -q` (pid %d) on an accepted connection, as the socket activator does" % (tag_, SD, self.p.pid))
        try:
            self.sock = sp.Tls(cli)
            ack = sp.recv_exact(self.sock, 1)
        except (OSError, ConnectionError) as e:
            bail("wire %s: no TLS session with the sandbox's server: %s" % (tag_, e))
        if ack != b"\x06":
            bail("wire %s: expected ACK 0x06 inside TLS, got %r" % (tag_, ack))
        if not login:
            say("    > wire %s: TLS %s and the ACK, and NO login: the server is before the login (section L)" % (tag_, self.sock.version))
            return
        a = types.SimpleNamespace(no_binding=False, gs2=None, bad_cbind=False, legacy=False, final_only=False, tamper_nonce=False, user=USER)
        try:
            rc, _ = sp.login(self.sock, a, PW)
        except (OSError, ConnectionError) as e:
            bail("wire %s: the SCRAM login failed part way: %s" % (tag_, e))
        say("    > wire %s: TLS %s, SCRAM-SHA-256 login as %s with the account password (%d characters): %s"
            % (tag_, self.sock.version, USER, len(PW), "server signature VERIFIED" if rc == 0 else "NOT verified (rc %d)" % rc))
        if rc != 0:
            bail("wire %s: the SCRAM login was not verified, so no row below could be believed" % tag_)
        r = self.req(3, USER)
        if r is None or r[0] != 0:
            bail("wire %s: the account %s was not entered: %r" % (tag_, USER, r))

    def _write(self, ptype, data):
        if isinstance(data, str):
            data = data.encode("latin-1")
        self.sock.sendall(struct.pack("<ih", len(data) + 6, ptype) + data)
        return data

    def _answer(self):
        n, err, st = struct.unpack("<ihi", sp.recv_exact(self.sock, 10))
        if n < 10 or n > 64 * 1024 * 1024:
            raise ConnectionError("invalid reply length %d" % n)
        return err, st, (sp.recv_exact(self.sock, n - 10) if n > 10 else b"")

    def abandon(self):
        """A request whose answer never came leaves the reader thread inside SSL_read, and libssl must not be written to meanwhile: end the
        server (the connection closes, the thread ends), then let go of the session.  Every later request on it answers None."""
        say("      %s ABANDONED: the server is ended and the session is not used again" % self.tag)
        self.abandoned = True
        self.kill()
        if self.th is not None:
            self.th.join(5)

    abandoned = False

    def req(self, ptype, data=b"", shown=None):
        if self.abandoned:
            return None
        data = self._write(ptype, data)
        what = shown if shown is not None else data[:60]
        try:
            err, st, body = self._answer()
        except (OSError, ConnectionError) as e:
            say("      %s request %d %r -> %s" % (self.tag, ptype, what, e))
            return None
        say("      %s request %d %r -> error %d (%s) status %d data %r" % (self.tag, ptype, what, err, SV.get(err, "?"), st, body[:70]))
        return err, st, body

    def send(self, ptype, data=b"", shown=None):
        """Send a request and do NOT wait for its answer: recv() reads it.  The server is meant to hold a file lock with the wait flag back."""
        data = self._write(ptype, data)
        self.pending = shown if shown is not None else data[:60]
        self.box = []

        def reader():
            try:
                self.box.append(self._answer())
            except (OSError, ConnectionError) as e:
                self.box.append(e)
        self.th = threading.Thread(target=reader, daemon=True)
        self.th.start()
        say("      %s request %d %r -> (sent; the answer is read later)" % (self.tag, ptype, self.pending))

    def recv(self, secs):
        """The answer to the request sent with send(), or None when nothing came within SECS seconds (it is then still pending)."""
        if self.abandoned or self.th is None:
            return None
        self.th.join(secs)
        if self.th.is_alive():
            say("      %s answer to %r -> nothing (within %s s)" % (self.tag, self.pending, secs))
            return None
        got = self.box[0]
        if isinstance(got, Exception):
            say("      %s answer to %r -> %s" % (self.tag, self.pending, got))
            return None
        err, st, body = got
        say("      %s answer to %r -> error %d (%s) status %d data %r" % (self.tag, self.pending, err, SV.get(err, "?"), st, body[:70]))
        return got

    def open4(self, name):
        r = self.req(4, name)
        if r and r[0] == 0 and len(r[2]) == 2:
            return struct.unpack("<h", r[2])[0], r
        return None, r

    def filelock(self, fno, wait=0):
        return self.req(32, struct.pack("<hh", fno, wait), shown="filelock fno %r wait %d" % (fno, wait))

    def filelock_wait(self, fno):
        if self.abandoned:
            return
        self.send(32, struct.pack("<hh", fno, 1), shown="filelock fno %r wait 1" % (fno,))

    def fileunlock(self, fno):
        return self.req(33, struct.pack("<h", fno), shown="fileunlock fno %r" % (fno,))

    def execute(self, cmd):
        r = self.req(21, cmd)
        return r[2].decode("latin-1") if r else None

    def kill(self):
        for sig in (signal.SIGHUP, signal.SIGKILL):
            try:
                os.killpg(self.p.pid, sig)
            except OSError:
                pass
            t0 = time.time()
            while time.time() - t0 < 2.0 and self.p.poll() is None:
                time.sleep(0.1)
        if self in WIRES:
            WIRES.remove(self)

    def close(self):
        if self.abandoned:
            return
        try:
            self.sock.sendall(struct.pack("<ih", 6, 1))
        except (OSError, ConnectionError):
            pass
        try:
            self.sock.close()
        except (OSError, ConnectionError):
            pass
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.kill()
        if self in WIRES:
            WIRES.remove(self)


def msg(n):
    with open(os.path.join(SYS, "messages", str(n)), encoding="utf-8", errors="replace") as f:
        return f.read().strip("\n")


# ---------------------------------------------------------------------------------------------------------------------
# What a server's process family is doing (sandbox-apispin.py's Watch, shortened): the family is every live process in the server's session
# (it is started as a session leader; the TLS relay it forks is in it).

def read_stat(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            s = f.read()
        rest = s[s.rindex(")") + 2:].split()
        return {"state": rest[0], "sid": int(rest[3]), "ticks": int(rest[11]) + int(rest[12]),
                "rss": int(rest[21]) * os.sysconf("SC_PAGE_SIZE") // 1024}
    except (OSError, ValueError, IndexError):
        return None


def family(sid):
    out = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            st = read_stat(int(d))
            if st is not None and st["sid"] == sid and st["state"] != "Z":
                out[int(d)] = st
    return out


def watch(w, seconds):
    """Poll the family of server W every 0.1 s until it is gone or SECONDS have passed.  (ended, seconds it took, CPU ticks the busiest survivor used in the
    last second, peak size in KB, whether any process of it was ever seen alive)."""
    seen = False
    peak = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        w.p.poll()
        fam = family(w.p.pid)
        seen = seen or bool(fam)
        for st in fam.values():
            peak = max(peak, st["rss"])
        if not fam:
            return True, round(time.time() - t0, 2), 0, peak, seen
        time.sleep(0.1)
    before = family(w.p.pid)
    time.sleep(1.0)
    after = family(w.p.pid)
    spin = 0
    for pid, st in after.items():
        spin = max(spin, st["ticks"] - before.get(pid, st)["ticks"])
        peak = max(peak, st["rss"])
    return (not after), seconds, spin, peak, seen or bool(after)


def describe(res):
    ended, secs, spin, peak, seen = res
    return ("ended after %.1f s" % secs) if ended else "SURVIVED (%d ticks of CPU in 1 s, %d KB)" % (spin, peak)


PROGS = {
    # waits for a line: the reply to the prompt is the packet part C2 corrupts
    "zzprmp": "   input x\n   crt 'GOT[':x:']'\nend\n",
    # waits in a shell (while one runs the input signal is not acted on), then clears the input: with the client gone, CLEARINPUT is the first thing to find out
    "zzclr": "   execute 'SH sleep 2'\n   clearinput\n   crt 'CLEARED'\nend\n",
}


def put_programs():
    """Write the two BASIC programs into the account's BP file through the API and compile them in a session of their own."""
    w = Wire("P")
    fno, r = w.open4("bp")
    if fno is None:
        bail("the account's BP file did not open: %r" % (r,))
    for name, src in PROGS.items():
        rid = name.encode("ascii")
        w.req(16, struct.pack("<hh", fno, len(rid)) + rid + src.replace("\n", "\xfe").encode("latin-1"), shown="write bp %s" % name)
        out = w.execute("BASIC bp %s" % name)
        if out is None or "Compiled 1 program(s) with no errors" not in out:
            bail("the program %s did not compile through the API: %r" % (name, out))
    w.close()


def section_c2():
    say("\n--- C2. the reply to an INPUT prompt declares a length the server cannot accept (S.71) ---------------------------------------")
    cases = [("'garb' = 1,651,663,207", b"garb" + struct.pack("<H", 22)), ("5, below the header", struct.pack("<I", 5) + struct.pack("<H", 22))]
    for name, raw in cases:
        w = Wire("C2")
        r = w.req(21, "RUN bp zzprmp")
        prompted = r is not None and r[0] == 5            # SV$PROMPT: the program is waiting for its INPUT
        was_alive = w.p.poll() is None                    # a server that ends at once can be gone before the first scan of /proc: it was alive when the client acted
        try:
            w.sock.sendall(raw)
        except (OSError, ConnectionError) as e:
            say("      C2 the bad reply could not be sent: %s" % e)
        res = watch(w, 6.0)
        say("      C2 the reply to the prompt declared %s: %s (it was alive when the client sent it: %s)" % (name, describe(res), was_alive))
        row("C2: the reply to an INPUT prompt declares %s: the server refuses it and ends the session (client still connected)" % name,
            prompted and was_alive and res[0], "prompted %s, was alive %s, %s" % (prompted, was_alive, describe(res)))
        w.kill()
        subprocess.run([SD, "-cleanup"], env=env(), capture_output=True, timeout=60)


def reg_switch(sh, osx):
    """Write fields 7 (SH) and 8 (OS.EXEC) of the register record accounts/sduser, 'yes' or blank, and keep the other fields.  The API server reads
    them when it enters the account, so a change is seen by the NEXT login (the OS switch, 20 Oct 26)."""
    path = os.path.join(SYS, "accounts", USER)
    with open(path) as f:
        lines = f.read().split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    lines += [""] * (8 - len(lines))
    lines = lines[:6] + ["yes" if sh else "", "yes" if osx else ""] + lines[8:]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def section_s():
    say("\n--- S. the OS switches over the API (the Solo OS switch, 20 Oct 26): the server loads them when it enters the account ------------")
    mark = os.path.join(BOX, "api-sh.sentinel")
    for sh_on in (False, True):
        reg_switch(sh_on, False)
        if os.path.exists(mark):
            os.remove(mark)
        w = Wire("S%d" % int(sh_on))
        out = w.execute("SH touch %s" % mark)
        made = os.path.exists(mark)
        w.close()
        if sh_on:
            row("S1: with the SH switch ON in the register, an API session's SH runs: the sentinel is on the disk", made, "reply %r" % (out,))
        else:
            row("S0: with the SH switch OFF in the register (as delivered), an API session's SH is refused (10053): no sentinel on the disk",
                (not made) and out is not None and "is not permitted to use the operating system shell" in out, "reply %r, sentinel %s" % (out, made))
    reg_switch(False, False)
    if os.path.exists(mark):
        os.remove(mark)


def section_k():
    say("\n--- K. CLEARINPUT after the connection has gone (S.71) ---------------------------------------------------------------------")
    # The program waits in SH sleep 2, so the account needs the SH switch (OFF as delivered, since the OS switch of 20 Oct 26): the register is written
    # for this section and put back at its end.  A section that turns a switch on says so, and which one.
    reg_switch(True, False)
    w = Wire("K0")
    r = w.req(21, "RUN bp zzclr")
    row("K0 CONTROL: with the client still connected the command runs through (SH sleep 2, CLEARINPUT) and says CLEARED", r is not None and b"CLEARED" in r[2], repr(r)[:120])
    w.close()
    w = Wire("K1")
    w._write(21, "RUN bp zzclr")                  # the command starts; its answer is never read
    time.sleep(0.7)                               # it is in SH sleep 2
    w.sock.close()                                # the client goes
    res = watch(w, 8.0)
    say("      K1 the client closed while the command waited in SH sleep: %s" % describe(res))
    row("K1: the client closes while the command waits in SH sleep; CLEARINPUT then runs: the server ends within 8 s and does not spin", res[0] and res[4], describe(res))
    w.kill()
    subprocess.run([SD, "-cleanup"], env=env(), capture_output=True, timeout=60)
    reg_switch(False, False)


def section_f():
    say("\n--- F. file locks, requests 32 and 33: the lock goes to the file NUMBER asked for (K8a) ---------------------------------------")
    s1 = Wire("F1")
    for extra in ("zzsec", "zzsec2", "zzsec3"):
        s1.execute("DELETE.FILE %s" % extra)
        out = s1.execute("CREATE.FILE %s DYNAMIC" % extra)
        say("    [setup] CREATE.FILE %s -> %r" % (extra, (out or "")[-60:]))
    s2 = Wire("F2")
    row("F0 two sessions of the one account: the holder S1 and the observer S2 (SCRAM verified, account entered, both)", True)
    names = ("zzsec", "zzsec2", "zzsec3")
    n1 = [s1.open4(n)[0] for n in names]
    n2 = [s2.open4(n)[0] for n in names]
    row("F1 each session opens zzsec, zzsec2 and zzsec3 in that order and is given three different file numbers; the LAST file opened (zzsec3) is not the one the first "
        "lock asks for, which is what makes the stale `files(i)` show", None not in n1 + n2 and len(set(n1)) == 3 and len(set(n2)) == 3, repr((n1, n2)))
    if None in n1 + n2:
        bail("a file did not open, so no lock row can be believed")
    a1, b1, c1 = n1
    a2, b2, c2 = n2
    r = s1.filelock(a1, 0)
    row("F2 S1 takes the file lock on zzsec by its number (no wait): OK", r is not None and r[0] == 0, repr(r))
    if r is None or r[0] != 0:
        bail("the first lock was not granted, so no lock row can be believed")
    r = s2.filelock(a2, 0)
    row("F3 S2 asks for the file lock on zzsec (no wait): LOCKED (error 4) - the lock S1 took is on zzsec", r is not None and r[0] == 4, repr(r))
    r = s2.filelock(b2, 0)
    row("F4 CONTROL: S2 asks for the file lock on zzsec2 (no wait): granted (OK) - S1 did not lock it, and a server that answered LOCKED to everything fails here",
        r is not None and r[0] == 0, repr(r))
    if r is not None and r[0] == 0:
        s2.fileunlock(b2)
    r = s2.filelock(c2, 0)
    row("F5 CONTROL: S2 asks for the file lock on zzsec3, the file opened last: granted (OK) - the bug put S1's lock here", r is not None and r[0] == 0, repr(r))
    if r is not None and r[0] == 0:
        s2.fileunlock(c2)
    s1.fileunlock(b1)
    r = s2.filelock(a2, 0)
    row("F6 S1 releases zzsec2, which it never locked: zzsec is STILL locked (S2: LOCKED) - an unlock goes to the file named, not to the last one opened",
        r is not None and r[0] == 4, repr(r))
    r = s1.fileunlock(a1)
    row("F7 S1 releases zzsec by its number: OK", r is not None and r[0] == 0, repr(r))
    r = s2.filelock(a2, 0)
    row("F8 S2 now gets the file lock on zzsec (OK): the unlock released the file that was named", r is not None and r[0] == 0, repr(r))
    if r is not None and r[0] == 0:
        s2.fileunlock(a2)
    r = s1.filelock(99, 0)
    row("F9 CONTROL: a file number that is not open (99) is the invalid-file-number error (error ERROR 3), not a lock", r is not None and r[0] == 3, repr(r))

    say("\n  -- the blocking form: the wait flag set (the server holds the request until the lock is free) --")
    r = s1.filelock(a1, 0)
    row("F10 S1 takes the file lock on zzsec (no wait): OK - S2 has something to wait for", r is not None and r[0] == 0, repr(r))
    s2.filelock_wait(a2)
    held = s2.recv(3)
    row("F11 S2 asks for the file lock on zzsec WITH the wait flag: NO answer in 3 seconds - the server holds the request while S1 has the lock (the stale `files(i)` "
        "would lock zzsec3, the file S2 opened last, and answer at once)", held is None, repr(held))
    r = s1.fileunlock(a1)
    row("F12 S1 releases zzsec: OK", r is not None and r[0] == 0, repr(r))
    got = s2.recv(15)
    row("F13 ...and the request S2 was held back on is then answered, OK (error 0) - S2 has the lock on zzsec now", got is not None and got[0] == 0, repr(got))
    if got is None:
        s2.abandon()
    r = s1.filelock(a1, 0)
    row("F14 S1 asks for the file lock on zzsec (no wait): LOCKED (error 4) - it is S2 that holds it, and zzsec is the file the wait was for",
        r is not None and r[0] == 4, repr(r))
    r = s1.filelock(c1, 0)
    row("F15 CONTROL: S1 asks for the file lock on zzsec3, the file S2 opened last (no wait): granted (OK) - the wait did not lock the stale index's file",
        r is not None and r[0] == 0, repr(r))
    if r is not None and r[0] == 0:
        s1.fileunlock(c1)
    s2.fileunlock(a2)
    r = s1.filelock(a1, 0)
    row("F16 S2 let go of zzsec: S1 gets it (OK); S1 holds zzsec again for the next rows", r is not None and r[0] == 0, repr(r))
    s2.filelock_wait(b2)
    free = s2.recv(3)
    row("F17 S2 asks WITH the wait flag for zzsec2, which nobody holds, while S1 holds zzsec: granted at once (error 0, inside 3 seconds) - waiting is only for a lock "
        "that is taken", free is not None and free[0] == 0, repr(free))
    if free is None:
        s2.abandon()
    r = s1.filelock(b1, 0)
    row("F18 ...and the lock S2 was granted is on zzsec2: S1 asking for it (no wait) is LOCKED (error 4)", r is not None and r[0] == 4, repr(r))
    r = s1.filelock(c1, 0)
    row("F19 CONTROL: S1 asks for zzsec3 (no wait): granted (OK) - the wait on a free file did not lock the stale index's file either",
        r is not None and r[0] == 0, repr(r))
    if r is not None and r[0] == 0:
        s1.fileunlock(c1)
    s2.fileunlock(b2)
    s1.fileunlock(a1)
    s1.close()
    s2.close()


def section_g():
    say("\n--- G. the text of an ON ERROR reply belongs to the request that got it (K1) -----------------------------------------------")
    w = Wire("G")
    w.execute("DELETE.FILE zzsec")
    w.execute("CREATE.FILE zzsec DYNAMIC")
    fno, r = w.open4("zzsec")
    row("G0 the file zzsec opens (a file number comes back)", fno is not None, repr(r))
    if fno is None:
        bail("the file did not open")
    bad_call = struct.pack("<h", 0)                         # a call name of length 0: refused with 5263 (abort.message set, SV$ON.ERROR)
    long_id = b"x" * 100                                    # longer than MAXIDLEN (63): the WRITE statement takes its ON ERROR clause
    write_long = struct.pack("<hh", fno, len(long_id)) + long_id + b"data"
    r1 = w.req(20, bad_call, shown="call, name length 0")
    row("G1 CONTROL: request 20 with a call name of length 0 is refused with ON ERROR and the text of 5263 (%r): a refusal's text is sent" % msg(5263),
        r1 is not None and r1[0] == 1 and r1[2].decode("latin-1") == msg(5263), repr(r1))
    r2 = w.req(16, write_long, shown="write fno %d, an id of %d characters" % (fno, len(long_id)))
    say("      [evidence] the WRITE of a 100 character id answered error %r status %r data %r" % (r2 and r2[0], r2 and r2[1], r2 and r2[2]))
    row("G2 a WRITE that takes its ON ERROR clause (an id over MAXIDLEN) right after that refusal is ON ERROR with NO text: the refusal's text is not repeated",
        r2 is not None and r2[0] == 1 and r2[2] == b"", repr(r2))
    r3 = w.req(20, bad_call, shown="call, name length 0")
    row("G3 CONTROL: the same refusal again sends its text again (emptying the message at the top of a request does not touch a refusal)",
        r3 is not None and r3[0] == 1 and r3[2].decode("latin-1") == msg(5263), repr(r3))
    w.close()
    w = Wire("G2")
    fno, r = w.open4("zzsec")
    r4 = w.req(16, struct.pack("<hh", fno, len(long_id)) + long_id + b"data", shown="write fno %r, an id of %d characters" % (fno, len(long_id)))
    row("G4 CONTROL: in a NEW session, with no refusal before it, the same WRITE is ON ERROR with no text (the same answer as G2)",
        r4 is not None and r4[0] == 1 and r4[2] == b"", repr(r4))
    row("G5 ...and the status is the same in both sessions (the clearing did not touch STATUS())",
        r2 is not None and r4 is not None and r2[1] == r4[1], repr((r2 and r2[1], r4 and r4[1])))
    w.close()
    w = Wire("Gz")
    for nm in ("zzsec", "zzsec2", "zzsec3"):
        w.execute("DELETE.FILE %s" % nm)         # every session that had a file open has closed: the fixture is removed
    w.close()


def section_l():
    say("\n--- L. the limit on a packet BEFORE the login, and the flag that lifts it after it (S.71, Solo's own test) -------------------------")
    # SD Core refuses a packet over 65,536 bytes while its API server is still root and nobody has logged in (`is_sdApiSrvr && geteuid() == 0`).  Solo's server is never
    # root, so Solo asks the same question of a flag, api_logged_in, that K$SET.USERNAME sets once the SCRAM proof has been accepted (owner's permission, 20 Oct 26).
    cases = [("65,536, the most a packet may declare before the login", 65536, False),
             ("65,537, one over", 65537, True),
             ("1,000,000,000, under the largest string", 1000000000, True)]
    for name, n, refused in cases:
        w = Wire("L", login=False)
        was_alive = w.p.poll() is None
        try:
            w.sock.sendall(struct.pack("<I", n))
        except (OSError, ConnectionError) as e:
            say("      L the declared length could not be sent: %s" % e)
        res = watch(w, 4.0)
        say("      L a first packet that declares %s: %s (alive when sent: %s)" % (name, describe(res), was_alive))
        if refused:
            row("L1: BEFORE the login a first packet that declares %s is refused: the server ends the session with the client still connected" % name,
                was_alive and res[0], describe(res))
        else:
            row("L1: BEFORE the login a first packet that declares %s is NOT refused (the boundary: the server waits for it)" % name,
                was_alive and not res[0], describe(res))
        w.kill()
        subprocess.run([SD, "-cleanup"], env=env(), capture_output=True, timeout=60)
    # after the login the limit is the largest string + 10: the flag is set, and a big request is read
    w = Wire("L2")
    w.execute("DELETE.FILE zzlfile")
    w.execute("CREATE.FILE zzlfile DYNAMIC")
    fno, r = w.open4("zzlfile")
    row("L2 AFTER the login: the file zzlfile opens (a file number comes back)", fno is not None, repr(r))
    if fno is not None:
        big = (b"0123456789abcdef" * 64 + b"x") * 3000                      # 3,075,000 bytes, far over 65,536
        rid = b"big"
        r = w.req(16, struct.pack("<hh", fno, len(rid)) + rid + big, shown="write fno %d, a record of %d bytes" % (fno, len(big)))
        row("L3 AFTER the login: a record of %d bytes (a request over 65,536 bytes) is written: the flag has lifted the limit" % len(big), r is not None and r[0] == 0, repr(r)[:100])
        r = w.req(6, struct.pack("<h", fno) + rid, shown="read fno %d id big" % fno)
        row("L4 ... and read back byte for byte", r is not None and r[0] == 0 and r[2] == big, "%s bytes back" % (len(r[2]) if r else None))
    try:
        w.sock.sendall(struct.pack("<I", 1000000000))
    except (OSError, ConnectionError) as e:
        say("      L2 the declared length could not be sent: %s" % e)
    res = watch(w, 3.0)
    say("      L2 after the login a packet that declares 1,000,000,000: %s" % describe(res))
    row("L5 AFTER the login a packet that declares 1,000,000,000 (under the largest string) is waited for, not refused: the limit before the login is gone",
        not res[0], describe(res))
    w.kill()
    subprocess.run([SD, "-cleanup"], env=env(), capture_output=True, timeout=60)
    w = Wire("Lz")
    w.execute("DELETE.FILE zzlfile")
    w.close()


def main():
    global BOX, SYS, SD, PW
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-apifile.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    SD = os.path.join(SYS, "bin", "sd")
    say("sandbox-apifile: sandbox  %s" % BOX)
    if os.geteuid() == 0:
        bail("this is root; Solo never runs as root")
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-apifile: built, bootstrap passed")
    elif not os.path.isfile(SD):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    try:
        with open(os.path.join(BOX, "account.pw")) as f:
            PW = f.read().strip()
    except OSError as e:
        bail("no account password file in the sandbox (%s)" % e)
    if not PW:
        bail("the account password file is empty")
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    try:
        section_f()
        section_g()
        put_programs()
        section_c2()
        section_s()
        section_k()
        section_l()
    finally:
        for w in list(WIRES):
            w.kill()
        subprocess.run([SD, "-cleanup"], env=env(), capture_output=True, timeout=60)
    say("\nsandbox-apifile: %d passed, %d failed" % (passed, failed))
    if passed + failed == 0:
        bail("no row ran - a broken test, not a pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
