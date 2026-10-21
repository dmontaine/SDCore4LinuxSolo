#!/usr/bin/env python3
#
# sandbox-sdnet-login.py - SDNet on SD Core for Linux Solo, stage B: set.server ... connect (one TLS handshake, the key hash shown and confirmed), the stored logins
#                          ($netcred, <sys>/netlogins) and set.netlogin / delete.netlogin against a FAKE SD API server (gplbld/netfake.py).  Solo's copy of the idea of SD Core's
#                          sandbox-net.py sections connect, netcred and netlogin (S.65 slices 2a and 2b), in Solo's one-account lane, WITHOUT the stand-ins SD Core needs for its
#                          root helper (Solo has none: the store is made by $netcred itself).  No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-sdnet-login.py <dir> [--build] [--sections=connect,netcred,netlogin]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo); SDSOLOBOX_KEYSET=n picks the keys.  With --build it is built first from THIS tree.  Exit 0 every row
# passed, 1 one failed, 2 it could not run.  Stop the sandbox afterwards with the SAME SDSOLOBOX_KEYSET: sandbox-fromtree.py <dir> stop.  It needs the openssl command line (the
# certificates and the expected pins are made with it, never by SD) and loads sandbox-sdnet.py for the lanes (an ordinary session, ADMIN, internal) and the helpers.
#
# START-HISTORY:
# 20 Oct 26 dm  Written for stage B of the SDNet carry (SD Core's S.65 slices 2a and 2b, carried to Solo 20 Oct).  Written after the code, run red on the stage A commit and green on stage B
#               (see the status entry); each row says what the evidence is.
# END-HISTORY
#
# WHAT IT DOES NOT SHOW, said plainly: the channel binding of the SCRAM login (Python's ssl cannot compute the TLS exporter: netfake.py says so; the real two-machine witness is the
# owner's), a real Solo or SD Core server on the other end, the mode and owner of the store against ANOTHER operating system user (the sandbox user owns everything), and the audit
# file of an install (the sandbox's own is read).

import datetime
import errno
import hashlib
import importlib.util
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import netfake                                   # the fake API server and the SCRAM arithmetic; self-tested: netfake.py --selftest
spec = importlib.util.spec_from_file_location("sandbox_sdnet", os.path.join(HERE, "sandbox-sdnet.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
row, say = s.row, s.say

PIN_A = s.PIN_A
NL_PW = "Zq7-remote-Passw0rd-x"        # the remote passwords the rows type: strings that appear nowhere else, so their presence anywhere is a leak
NL_BADPW = "Wrong-Passw0rd-q3"
NL_REMOTE = "alice"
SUCC = r"is stored\.  The password is not stored$"          # the success wording of 11477 and of nothing else
SALT0 = "AAECAwQFBgcICQoLDA0ODw=="                           # base64 of 16 bytes, for the rows that write a login by hand
NEEDED = list(range(11450, 11460)) + [11461] + list(range(11463, 11480)) + list(range(11440, 11447))


def run_ssl(args, data=None):
    p = subprocess.run(["openssl"] + args, input=data, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("openssl %s failed: %s" % (" ".join(args[:3]), p.stderr.decode(errors="replace")[-300:]))
    return p.stdout


def make_key(path):
    run_ssl(["genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", path])


def make_cert(key, cert, cn, serial):
    run_ssl(["req", "-x509", "-new", "-key", key, "-out", cert, "-days", "2", "-subj", "/CN=" + cn, "-set_serial", str(serial)])


def expected_pin(cert):
    """The pin a definition must hold for this certificate, computed WITHOUT sd: the SHA-256 of the SubjectPublicKeyInfo (openssl x509 -pubkey | pkey -pubin -outform DER | dgst
    -sha256), lower case hex; Python's hashlib must agree."""
    pub = run_ssl(["x509", "-in", cert, "-pubkey", "-noout"])
    der = run_ssl(["pkey", "-pubin", "-outform", "DER"], pub)
    dg = run_ssl(["dgst", "-sha256", "-binary"], der)
    if dg != hashlib.sha256(der).digest():
        raise RuntimeError("openssl dgst and hashlib disagree about the SubjectPublicKeyInfo of " + cert)
    return dg.hex()


def cert_fingerprint(cert):
    der = run_ssl(["x509", "-in", cert, "-outform", "DER"])
    return run_ssl(["dgst", "-sha256", "-binary"], der).hex()


def closed_port():
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.bind(("127.0.0.1", 0))
    port = sk.getsockname()[1]
    sk.close()
    return port


class TestServer(threading.Thread):
    """A local server standing in for the other SD server.  MODE 'tls': a TLS 1.3 handshake (no client certificate), then it waits up to 2 seconds for application data (a
    handshake-only client sends none and closes), then closes.  MODE 'plain': a TCP server that is not TLS.  Counts connections accepted, handshakes completed and application bytes."""

    def __init__(self, mode, cert=None, key=None, life=1500):
        threading.Thread.__init__(self, daemon=True)
        self.mode, self.count, self.handshakes, self.app_bytes, self.busy = mode, 0, 0, 0, False
        self.ended = threading.Event()
        self.deadline = time.time() + life
        self.ctx = None
        if mode == "tls":
            self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            self.ctx.maximum_version = ssl.TLSVersion.TLSv1_3
            self.ctx.load_cert_chain(cert, key)
        self.lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.lsock.bind(("127.0.0.1", 0))
        self.lsock.listen(8)
        self.lsock.settimeout(0.1)
        self.port = self.lsock.getsockname()[1]
        self.start()

    def run(self):
        while not self.ended.is_set() and time.time() < self.deadline:
            try:
                conn, _addr = self.lsock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.busy = True
            self.count += 1
            try:
                conn.settimeout(10)
                self.handle(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                self.busy = False
        try:
            self.lsock.close()
        except OSError:
            pass

    def handle(self, conn):
        if self.mode == "plain":
            try:
                conn.recv(4096)
            except OSError:
                pass
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        tls = self.ctx.wrap_socket(conn, server_side=True)
        self.handshakes += 1
        tls.settimeout(2)
        try:
            self.app_bytes += len(tls.recv(4096))
        except (OSError, ssl.SSLError):
            pass
        try:
            tls.close()
        except OSError:
            pass

    def settle(self, quiet=0.7, limit=8.0):
        time.sleep(quiet)
        t0 = time.time()
        while self.busy and time.time() - t0 < limit:
            time.sleep(0.05)

    def shutdown(self):
        self.ended.set()
        self.join(timeout=5)


# ---- helpers on the sandbox ------------------------------------------------------------------------------------------------------------------

def sysdir():
    return s.SYS


def entry(name):
    for ln in s.file_lines() or []:
        if ln.startswith(name + "|"):
            return ln
    return None


def audit_off():
    """Size of <sys>/audit.  SD APPENDS to it and never creates it (the install makes it), so the file is made here, empty, when it is missing."""
    path = os.path.join(s.SYS, "audit")
    try:
        if not os.path.exists(path):
            with open(path, "ab"):
                pass
        return os.path.getsize(path)
    except OSError:
        return None


def audit_new(off):
    try:
        with open(os.path.join(s.SYS, "audit"), "rb") as f:
            f.seek(off or 0)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def first_idx(out, text):
    for i, ln in enumerate(out):
        if text in ln:
            return i
    return -1


def msg_re(n, *args):
    t = re.escape(s.msg(n, *["QQ%dQQ" % i for i in range(1, len(args) + 1)]))
    for i, a in enumerate(args, 1):
        t = t.replace("QQ%dQQ" % i, a)
    return t


def has_msg(out, text):
    """The message is on the screen: a line of its own, or - when longer than the 200 columns the sessions are given - its first 120 characters at the start of a line."""
    if s.has_line(out, text):
        return True
    return len(text) > 190 and any(ln.startswith(text[:120]) for ln in out)


def conn_cmd(name, port, extra="", host="127.0.0.1", account="reader", word="connect"):
    return "set.server %s %s %s %s %s%s" % (name, host, port, account, word, (" " + extra) if extra else "")


def conn_run(cmd, answers, srv=None):
    """CMD and the ANSWERS in an administrator session.  Returns the output, the definitions before and after, the audit gained, and how many connections SRV accepted."""
    c0 = srv.count if srv is not None else 0
    before = s.snap()
    a0 = audit_off()
    out = s.adm1(cmd, *answers)
    after = s.snap()
    if srv is not None:
        srv.settle()
    return out, before, after, audit_new(a0), (srv.count - c0 if srv is not None else None)


def audit_rx(name, host, port, mode, replaced, how):
    return r"set\.server name=%s host=%s port=%s mode=%s replaced=%s pin=%s(?:\s|$)" % tuple(re.escape(str(x)) for x in (name, host, port, mode, replaced, how))


def sock_probe(port):
    return "\n".join([
        "$include keys.h",
        "   skt = open.socket('127.0.0.1', %d, SKT$BLOCKING, 5)" % port,
        "   if status() # 0 then crt 'SK plain-open FAILED ':status() ; stop",
        "   h = socket.info(skt, SKT$INFO.TLS.SPKI)",
        "   crt 'SK plain len=':len(h):' [':h:']'",
        "   close.socket skt",
        "   skt = open.socket('127.0.0.1', %d, SKT$BLOCKING + SKT$TLS, 5)" % port,
        "   if status() # 0 then crt 'SK tls-open FAILED ':status() ; stop",
        "   h = socket.info(skt, SKT$INFO.TLS.SPKI)",
        "   crt 'SK tls len=':len(h):' [':h:']'",
        "   close.socket skt",
        "   crt 'SK end'", "end", ""])


def clean_defs():
    for p in (s.netfile(), s.netfile() + ".new", s.netfile() + ".lock"):
        if os.path.exists(p):
            os.remove(p)


# ---- certificates, once ----------------------------------------------------------------------------------------------------------------------

C = {}


def certs():
    if "pin_a" in C:
        return True
    if shutil.which("openssl") is None:
        row("SETUP: the openssl command line is needed to make the test certificates and the expected pins, and it is NOT installed: NONE of the rows can run", False,
            "install openssl and run again")
        return False
    work = tempfile.mkdtemp(prefix="sdnet-login-")
    C["work"] = work
    try:
        k1, k2 = os.path.join(work, "k1.pem"), os.path.join(work, "k2.pem")
        c1, c1b, c2 = (os.path.join(work, n) for n in ("c1.pem", "c1b.pem", "c2.pem"))
        make_key(k1)
        make_key(k2)
        make_cert(k1, c1, "sdnet-test-one", 1)
        make_cert(k1, c1b, "sdnet-test-one-renewed", 2)       # a NEW certificate over the SAME key
        make_cert(k2, c2, "sdnet-test-two", 3)                # a certificate over a NEW key
        C.update(k1=k1, k2=k2, c1=c1, c1b=c1b, c2=c2, pin_a=expected_pin(c1), pin_a2=expected_pin(c1b), pin_b=expected_pin(c2),
                 fp_a=cert_fingerprint(c1), fp_a2=cert_fingerprint(c1b))
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        row("SETUP: the test certificates and the expected pins were made with the openssl command line", False, repr(e))
        return False
    row("SETUP: the independent computation (openssl): a renewed certificate over the same key has the SAME pin and a DIFFERENT certificate hash; a certificate over a new key has a "
        "different pin; each pin is 64 lower case hex digits",
        C["pin_a"] == C["pin_a2"] and C["fp_a"] != C["fp_a2"] and C["pin_b"] != C["pin_a"] and all(re.fullmatch(r"[0-9a-f]{64}", x) for x in (C["pin_a"], C["pin_b"])),
        repr((C["pin_a"], C["pin_a2"], C["pin_b"])))
    return True


def cleanup():
    w = C.get("work")
    if w and os.path.isdir(w) and os.path.basename(w).startswith("sdnet-login-"):
        shutil.rmtree(w, ignore_errors=True)


# ---- set.server ... connect -------------------------------------------------------------------------------------------------------------------

def connect_section():
    say("\n--- set.server ... connect: ONE TLS handshake, the hash of the key shown, SDSYS asked; a local TLS 1.3 server stands in for the other SD ------------")
    clean_defs()
    if not certs():
        return
    servers, probes = [], []
    pin_a, pin_b, fp_a = C["pin_a"], C["pin_b"], C["fp_a"]
    try:
        srv_a, srv_a2, srv_b, srv_p = TestServer("tls", C["c1"], C["k1"]), TestServer("tls", C["c1b"], C["k1"]), TestServer("tls", C["c2"], C["k2"]), TestServer("plain")
        servers += [srv_a, srv_a2, srv_b, srv_p]
        dead = closed_port()
        H = "127.0.0.1"
        pa = srv_a.port
        succ = lambda out: s.has(out, s.SUCCESS)
        q_key = lambda out: s.has_text(out, s.msg(11442))

        out, b, a, au, dials = conn_run(conn_cmd("conna", pa), ["y"], srv_a)
        order = [first_idx(out, s.msg(11440, H, pa)), next((i for i, ln in enumerate(out) if ln == pin_a), -1), first_idx(out, s.msg(11441)[:60]),
                 first_idx(out, s.msg(11442)), first_idx(out, s.msg(11424, "conna", H, pa))]
        row("CONTROL, a new name and the answer y: 'Connected to host:port', the hash ALONE on a line, the advice to compare it, 'Trust this key (y/<n>)?', then 'Server conna is defined' - in that order",
            all(i >= 0 for i in order) and order[0] < order[1] < order[2] <= order[3] <= order[4], repr((order, out[-6:])))
        row("...the stored pin is EXACTLY the one computed with openssl (SHA-256 of the SubjectPublicKeyInfo), and it is not the certificate's own hash",
            s.line_is(entry("conna"), ["conna", H, str(pa), "reader", pin_a, "read", ""]) and entry("conna").split("|")[4] != fp_a, "file now: %r  expected pin %s" % (s.file_lines(), pin_a))
        row("...the audit trail says how the pin was obtained (pin=confirmed) and does not carry the hash",
            au is not None and re.search(audit_rx("conna", H, pa, "read", "no", "confirmed"), au) is not None and pin_a not in au, repr((au or "NO AUDIT FILE")[-300:]))
        row("...the server saw ONE connection, ONE completed handshake and NO application data at all (a handshake only), and no copy netservers.new is left",
            dials == 1 and srv_a.handshakes == 1 and srv_a.app_bytes == 0 and not os.path.exists(s.netfile() + ".new"), repr((dials, srv_a.handshakes, srv_a.app_bytes)))

        for label, answers in (("n", ["n"]), ("an empty line", [""]), ("N", ["N"]), ("x and then n (the question is put again)", ["x", "n"]), ("no answer at all (end of input)", [])):
            out, b, a, au, dials = conn_run(conn_cmd("connb", pa), answers, srv_a)
            asked = sum(ln.count(s.msg(11442)) for ln in out)
            row("the key question answered with %s: the hash was shown, 'The key was not trusted', the file the SAME BYTES, no audit line, no copy left" % label,
                s.has_line(out, pin_a) and s.has_text(out, s.msg(11443, "connb")) and not succ(out) and b == a and entry("connb") is None and au is not None and "name=connb" not in au
                and asked >= (2 if label.startswith("x") else 1) and dials == 1, "asked=%d dials=%s before==after %s  out %r" % (asked, dials, b == a, out[-4:]))

        out, b, a, au, dials = conn_run(conn_cmd("connc", pa, "no.query"), ["n"], srv_a)
        row("NO.QUERY does not skip the key question: it is on the screen, the answer n writes NOTHING, and the server was dialled",
            q_key(out) and s.has_text(out, s.msg(11443, "connc")) and b == a and entry("connc") is None and dials == 1, repr((b == a, dials, out[-3:])))
        out, b, a, au, dials = conn_run(conn_cmd("conna", srv_b.port, "no.query"), ["y"], srv_b)
        row("NO.QUERY skips only the question about replacing: conna is replaced with no 'already defined' question, the KEY question is put, and the pin is now the other key's",
            not s.has_text(out, "is already defined") and q_key(out) and s.line_is(entry("conna"), ["conna", H, str(srv_b.port), "reader", pin_b, "read", ""]), repr((out[-3:], entry("conna"))))
        out, b, a, au, dials = conn_run(conn_cmd("conna", pa), ["n"], srv_a)
        row("replacing conna: the answer n to 'Replace it' ends it - 'Server conna was not changed', the file the same bytes and NO connection at all (counted %s)" % dials,
            s.has_text(out, s.msg(11426, "conna")) and b == a and dials == 0 and not q_key(out), repr((b == a, dials, out[-3:])))

        out, b, a, au, dials = conn_run(conn_cmd("connr", srv_a2.port), ["y"], srv_a2)
        row("a RENEWED certificate over the SAME key gives the SAME pin as the first server",
            s.line_is(entry("connr"), ["connr", H, str(srv_a2.port), "reader", C["pin_a2"], "read", ""]) and C["pin_a2"] == pin_a and dials == 1, repr((entry("connr"), C["pin_a2"])))

        out, b, a, au, dials = conn_run(conn_cmd("connp", srv_p.port), [], srv_p)
        row("a plain TCP server that is not TLS is refused with the HANDSHAKE message (11445): no hash, no question, the file the same bytes",
            s.has(out, msg_re(11445, re.escape(H), str(srv_p.port))) and not q_key(out) and not succ(out) and b == a and entry("connp") is None and dials == 1, repr((b == a, dials, out[-3:])))
        out, b, a, au, dials = conn_run(conn_cmd("connd", dead), [])
        row("a CLOSED port is refused with the CANNOT CONNECT message (11444, os error %d), not the handshake one, nothing written" % errno.ECONNREFUSED,
            s.has(out, msg_re(11444, re.escape(H), str(dead), r"\d+", str(errno.ECONNREFUSED))) and not s.has(out, msg_re(11445, ".*", ".*")) and not q_key(out) and b == a and entry("connd") is None,
            repr((b == a, out[-3:])))
        out, b, a, au, dials = conn_run(conn_cmd("conne", pa, host="nosuchhost.invalid"), [], srv_a)
        row("a host name that does not resolve is a clear failure (11444), no question, nothing written, and the real server was NOT dialled (%s)" % dials,
            s.has(out, msg_re(11444, "nosuchhost\\.invalid", str(pa), r"\d+", r"\d+")) and not q_key(out) and b == a and entry("conne") is None and dials == 0, repr((b == a, dials, out[-3:])))

        say("  (a definition that would be refused is never dialled)")
        for label, cmd, expect in (("a bad name", conn_cmd("1bad", pa), [s.msg(11414, "1bad")]), ("a bad host", conn_cmd("badh", pa, host="-bad.org"), [s.msg(11415, "-bad.org")]),
                                   ("a bad port", conn_cmd("badp", 0), [s.msg(11416, "0")]), ("a bad mode", conn_cmd("badm", pa, "append"), [s.msg(11419, "append")]),
                                   ("an unregistered account in the list", conn_cmd("badl", pa, "accounts zznnosuch"), [s.msg(11421, "zznnosuch")])):
            out, b, a, au, dials = conn_run(cmd, [], srv_a)
            miss = [t for t in expect if not s.has_line(out, t)]
            dialled = s.has(out, r"Connected to |Cannot connect to |The TLS handshake with ") or q_key(out)
            row("%s with connect -> refused with its own message, nothing dialled (the server counted %s), the file the same bytes" % (label, dials),
                not miss and not dialled and dials == 0 and b == a and not succ(out), "missing %r; dialled=%s dials=%s out %r" % (miss, dialled, dials, out[-4:]))

        out, b, a, au, dials = conn_run("set.server connt %s %d reader %s read" % (H, pa, pin_b), [], srv_a)
        row("a TYPED pin makes NO connection (counted %s) and no key question, even for a port with a TLS server on it; it is stored as typed, and the audit line says pin=typed" % dials,
            dials == 0 and not q_key(out) and s.line_is(entry("connt"), ["connt", H, str(pa), "reader", pin_b, "read", ""]) and au is not None
            and re.search(audit_rx_typed(H, pa), au) is not None, repr((dials, out[-3:])))

        prog = "zznetsk"
        s.put(os.path.join(s.ACCT, "bp", prog), sock_probe(srv_a.port))
        probes.append(os.path.join(s.ACCT, "bp", prog))
        s.reg_os(False)
        out = s.session(["BASIC bp " + prog, "RUN bp " + prog], quiet=True)
        row("an ORDINARY session (os off): SOCKET.INFO(SKT$INFO.TLS.SPKI) answers the NULL string for a socket opened without SKT$TLS (length 0), and for one opened with it the 64 digits "
            "openssl computed for that server (the hash is a public key's: no gate hides it)",
            s.compiled(out) and s.has_line(out, "SK plain len=0 []") and s.has_line(out, "SK tls len=64 [%s]" % pin_a) and s.has_line(out, "SK end"), repr(out[-5:]))
    finally:
        for sv in servers:
            sv.shutdown()
        for p in probes:
            for q in (p, p.replace(os.sep + "bp" + os.sep, os.sep + "bp.out" + os.sep)):
                if os.path.exists(q):
                    os.remove(q)
        clean_defs()


def audit_rx_typed(host, port):
    return audit_rx("connt", host, port, "read", "no", "typed")


# ---- $netcred --------------------------------------------------------------------------------------------------------------------------------

ZZNC = "\n".join([
    "$internal", "program zznc", "$catalog $zznc", "$include err.h",
    "   done = @false", "   rec = ''", "   err = ''",
    "   loop",
    "      input ln",
    "      done = (ln = 'END') or (ln = '' and status() = ER$EOF)",
    "   until done do",
    "      act = field(ln, '|', 1)", "      srv = field(ln, '|', 2)", "      pn = field(ln, '|', 3)", "      rec = ''",
    "      for i = 1 to 7", "         rec<i> = field(ln, '|', 3 + i)", "      next i",
    "      err = ''",
    "      call $netcred(act, srv, rec, pn, err)",
    "      crt 'NC ':act:' ':srv:' err=':convert(@vm, '~', err):' rec=':convert(@fm, '|', rec)",
    "   repeat",
    "   crt 'NC end'", "end", ""])


def cred_dir():
    return os.path.join(s.SYS, "netlogins")


def cred_path(server):
    return os.path.join(cred_dir(), server)


def cred_state():
    """The whole store as the disk holds it: None when the directory is not there, else {name: (mode, inode, mtime_ns, bytes or None)}."""
    d = cred_dir()
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return None
    out = {}
    for n in names:
        p = os.path.join(d, n)
        try:
            lst = os.lstat(p)
            data = None
            if (lst.st_mode & 0o170000) == 0o100000:
                with open(p, "rb") as f:
                    data = f.read()
            out[n] = (lst.st_mode, lst.st_ino, lst.st_mtime_ns, data)
        except OSError as e:
            out[n] = ("error", repr(e))
    return out


def read_cred(server):
    try:
        with open(cred_path(server), "rb") as f:
            return f.read()
    except OSError:
        return None


def cred_line(remote, salt_b64, iters, ck_b64, sk_b64, pin, date=None):
    return "|".join(["v1", remote, salt_b64, str(iters), ck_b64, sk_b64, pin, date or datetime.date.today().isoformat()])


def valid_line(remote=NL_REMOTE, pin=PIN_A, iters=4096, pw=NL_PW, salt=SALT0):
    k = netfake.derive(pw, salt, iters)
    return cred_line(remote, salt, iters, k["client_key_b64"], k["server_key_b64"], pin)


def cred_matches(server, remote, salt_b64, iters, ck_b64, sk_b64, pin):
    raw = read_cred(server)
    if raw is None:
        return False
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return False
    if text.endswith("\n"):
        text = text[:-1]
    parts = text.split("|")
    return "\n" not in text and len(parts) == 8 and parts[:7] == ["v1", remote, salt_b64, str(iters), ck_b64, sk_b64, pin] and parts[7] in s.dates()


def plant(server, line=None, mode=0o600, raw=None):
    """A login put on the disk by hand, as the sandbox user: for the rows that need a file to be there, or to be wrong."""
    os.makedirs(cred_dir(), exist_ok=True)
    os.chmod(cred_dir(), 0o700)
    p = cred_path(server)
    with open(p, "wb") as f:
        f.write(raw if raw is not None else (line + "\n").encode("ascii"))
    os.chmod(p, mode)


def reset_store():
    d = cred_dir()
    if os.path.lexists(d) and d.startswith(s.SYS + os.sep):
        if os.path.isdir(d) and not os.path.islink(d):
            shutil.rmtree(d, ignore_errors=True)
        else:
            os.remove(d)


def L(act, server, pin="", *attrs):
    return "|".join([act, server, pin] + list(attrs))


def nc_session(lines):
    """Run the probe zznc (an internal program) with these input lines.  Returns [(action, server, [err values], [record attributes])] and whether it reached its end line."""
    out = s.internal(["RUN gpl.bp zznc"] + list(lines) + ["END"])
    res = []
    for ln in out:
        m = re.match(r"^NC (\S+) (\S*) err=(.*?) rec=(.*)$", ln)
        if m:
            res.append((m.group(1), m.group(2), m.group(3).split("~") if m.group(3) != "" else [], m.group(4).split("|") if m.group(4) != "" else []))
    return res, s.has_line(out, "NC end"), out


def netcred_section():
    say("\n--- $netcred: the store <sys>/netlogins, driven by an internal probe, the DISK as the evidence ------------------------------------------------------")
    reset_store()
    s.put(os.path.join(s.SYS, "gpl.bp", "zznc"), ZZNC)
    out = s.internal(["BASIC gpl.bp zznc"])
    if not row("SETUP: the probe zznc compiles with no errors", s.compiled(out), repr(out[-4:])):
        pass
    pin_a, pin_b = PIN_A, "fedcba9876543210" * 4
    good = valid_line()
    k = netfake.derive(NL_PW, SALT0, 4096)
    attrs = (NL_REMOTE, SALT0, "4096", k["client_key_b64"], k["server_key_b64"], "", "")

    res, ended, out = nc_session([L("EXISTS", "nlcred")])
    row("EXISTS with no directory at all: record 0 and NO error, and the probe made no directory (the null case is not an error)",
        ended and res and res[0][2] == [] and res[0][3] == ["0"] and cred_state() is None, repr((res, cred_state())))
    res, ended, out = nc_session([L("READ", "nlcred", pin_a)])
    row("READ with no directory: 11453 (no login stored), nothing made", ended and res and res[0][2][:1] == ["11453"] and cred_state() is None, repr(res))
    res, ended, out = nc_session([L("ENSURE", "nlcred")])
    st = os.lstat(cred_dir()) if os.path.isdir(cred_dir()) else None
    row("ENSURE makes the directory <sys>/netlogins with mode 700, owned by the user running SD, and answers no error",
        ended and res and res[0][2] == [] and st is not None and (st.st_mode & 0o7777) == 0o700 and st.st_uid == os.getuid(), repr((res, st and oct(st.st_mode))))
    res, ended, out = nc_session([L("ENSURE", "nlcred")])
    row("ENSURE again changes nothing and answers no error (idempotent)", ended and res and res[0][2] == [] and (os.lstat(cred_dir()).st_mode & 0o7777) == 0o700, repr(res))
    res, ended, out = nc_session([L("WRITE", "nlcred", pin_a, *attrs)])
    st = os.lstat(cred_path("nlcred")) if os.path.exists(cred_path("nlcred")) else None
    row("WRITE stores ONE line v1|remote|salt|iterations|ClientKey|ServerKey|pin|date, the keys the ones hashlib derives, the pin the ARGUMENT, mode 600, no .new left",
        ended and res and res[0][2] == [] and cred_matches("nlcred", NL_REMOTE, SALT0, 4096, k["client_key_b64"], k["server_key_b64"], pin_a) and st is not None
        and (st.st_mode & 0o7777) == 0o600 and not os.path.exists(cred_path("nlcred") + ".new"), repr((res, st and oct(st.st_mode), read_cred("nlcred"))))
    res, ended, out = nc_session([L("READ", "nlcred", pin_a), L("EXISTS", "nlcred")])
    row("READ with the same pin returns the seven values; EXISTS says 1",
        ended and len(res) == 2 and res[0][2] == [] and res[0][3][:5] == [NL_REMOTE, SALT0, "4096", k["client_key_b64"], k["server_key_b64"]] and res[0][3][5] == pin_a
        and res[1][3] == ["1"], repr(res))
    res, ended, out = nc_session([L("READ", "nlcred", pin_b)])
    row("READ with a DIFFERENT pin (the definition's key was renewed): 11455, and no record is returned", ended and res and res[0][2][:1] == ["11455"] and res[0][3] == [], repr(res))
    res, ended, out = nc_session([L("READ", "nlcred", "xyz")])
    row("READ with a pin that is not 64 hexadecimal digits: 11459", ended and res and res[0][2][:1] == ["11459"], repr(res))
    for name in ("1abc", "a_b", "A", "a" * 17, ""):
        res, ended, out = nc_session([L("READ", name, pin_a)])
        row("a server name %r: 11452, and nothing is looked up" % name, ended and res and res[0][2][:1] == ["11452"], repr(res))
    res, ended, out = nc_session([L("FROB", "nlcred")])
    row("an unknown action: 2018", ended and res and res[0][2][:1] == ["2018"], repr(res))

    say("  (a file or a directory that is not what $netcred made is refused and NOT used)")
    plant("nlbits", good, mode=0o640)
    res, ended, out = nc_session([L("READ", "nlbits", pin_a), L("EXISTS", "nlbits"), L("DELETE", "nlbits")])
    row("a login file with group bits (640): READ, EXISTS and DELETE each answer 11454 and the file is still there", ended and len(res) == 3 and all(r[2][:1] == ["11454"] for r in res)
        and os.path.exists(cred_path("nlbits")), repr(res))
    plant("nlbits2", good, mode=0o604)
    res, ended, out = nc_session([L("READ", "nlbits2", pin_a)])
    row("... and with a world bit (604)", ended and res and res[0][2][:1] == ["11454"], repr(res))
    if os.path.lexists(cred_path("nllink")):
        os.remove(cred_path("nllink"))
    os.symlink(cred_path("nlcred"), cred_path("nllink"))
    res, ended, out = nc_session([L("READ", "nllink", pin_a), L("EXISTS", "nllink")])
    row("a SYMBOLIC LINK with the name of a login (to a good file): READ and EXISTS answer 11454 - the last component is lstat'ed, a link is never followed", ended and len(res) == 2
        and all(r[2][:1] == ["11454"] for r in res), repr(res))
    os.remove(cred_path("nllink"))
    os.mkdir(cred_path("nldir"))
    res, ended, out = nc_session([L("READ", "nldir", pin_a), L("DELETE", "nldir")])
    row("a DIRECTORY with the name of a login: READ and DELETE answer 11454 and it is left", ended and len(res) == 2 and all(r[2][:1] == ["11454"] for r in res) and os.path.isdir(cred_path("nldir")),
        repr(res))
    os.rmdir(cred_path("nldir"))
    plant("nldamaged", raw=b"v1|alice|AAAA\n")
    res, ended, out = nc_session([L("READ", "nldamaged", pin_a)])
    row("a damaged file (too few fields): 11456 (damaged), not used", ended and res and res[0][2][:1] == ["11456"], repr(res))
    plant("nlmarks", raw=(good + "\xfe").encode("latin-1") + b"\n")
    res, ended, out = nc_session([L("READ", "nlmarks", pin_a)])
    row("a file holding a mark byte (it would make a second attribute): 11456", ended and res and res[0][2][:1] == ["11456"], repr(res))

    say("  (WRITE is whole or not at all; DELETE removes only a trusted plain file)")
    before = cred_state()
    res, ended, out = nc_session([L("WRITE", "nlcred", pin_a, NL_REMOTE, "!!!", "4096", k["client_key_b64"], k["server_key_b64"])])
    row("WRITE of a salt that is not base64: 11456, the store the SAME BYTES, inode and mtime (an existing login is untouched by a failure)", ended and res and res[0][2][:1] == ["11456"]
        and cred_state() == before, repr(res))
    res, ended, out = nc_session([L("WRITE", "nlcred", pin_a, NL_REMOTE, SALT0, "4095", k["client_key_b64"], k["server_key_b64"])])
    row("WRITE of an iteration count below the floor (4095): 11456, nothing changed", ended and res and res[0][2][:1] == ["11456"] and cred_state() == before, repr(res))
    res, ended, out = nc_session([L("WRITE", "nlcred", "zz", *attrs)])
    row("WRITE with a pin that is not 64 digits: 11459, nothing changed", ended and res and res[0][2][:1] == ["11459"] and cred_state() == before, repr(res))
    res, ended, out = nc_session([L("DELETE", "nlcred"), L("EXISTS", "nlcred"), L("DELETE", "nlcred")])
    row("DELETE removes the login (the file is gone), EXISTS then says 0, and a second DELETE says 11453", ended and len(res) == 3 and res[0][2] == [] and not os.path.exists(cred_path("nlcred"))
        and res[1][3] == ["0"] and res[2][2][:1] == ["11453"], repr(res))
    reset_store()
    os.makedirs(cred_dir())
    os.chmod(cred_dir(), 0o755)
    res, ended, out = nc_session([L("ENSURE", "nlcred"), L("READ", "nlcred", pin_a), L("WRITE", "nlcred", pin_a, *attrs)])
    row("a directory that is mode 755 (not private): ENSURE, READ and WRITE all refuse it (11463 / 11454), and no login was written", ended and len(res) == 3
        and res[0][2][:1] == ["11463"] and res[1][2][:1] == ["11454"] and res[2][2][:1] == ["11454"] and not os.path.exists(cred_path("nlcred")), repr(res))
    reset_store()


# ---- set.netlogin and delete.netlogin ---------------------------------------------------------------------------------------------------------

def nl_run(cmd, answers=(), srv=None, admin=False):
    """One session: CMD, then the ANSWERS as the lines the prompts read.  Returns the output, the store before and after, the audit gained and what the fake server saw."""
    a0 = audit_off()
    st0 = cred_state()
    m = srv.mark() if srv is not None else None
    cmds = [cmd] + list(answers)
    out = s.adm1(*cmds) if admin else s.session(cmds, quiet=True)
    if srv is not None:
        srv.settle(quiet=0.3)
    return {"out": out, "before": st0, "after": cred_state(), "audit": audit_new(a0), "d": srv.delta(m) if srv is not None else None}


def scan_for(needles, roots):
    """Every regular file under ROOTS is read for each byte string in NEEDLES.  Returns (files read, {needle: [paths]})."""
    found = {n: [] for n in needles}
    nfiles = 0
    skip_tree = os.path.join(s.BOX, "tree")      # the sandbox's own COPY of the source tree, this suite's text included: it holds the passwords the rows type
    for root in roots:
        for dp, _dn, fns in os.walk(root, followlinks=False):
            if dp == skip_tree or dp.startswith(skip_tree + os.sep):
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    if os.path.islink(p) or not os.path.isfile(p) or os.path.getsize(p) > 256 * 1024 * 1024:
                        continue
                    nfiles += 1
                    with open(p, "rb") as f:
                        data = f.read()
                    for n in needles:
                        if n in data and p not in found[n]:
                            found[n].append(p)
                except OSError:
                    continue
    return nfiles, found


def netlogin_section():
    say("\n--- set.netlogin / delete.netlogin, against a FAKE SD API SERVER (gplbld/netfake.py) that records every packet ---------------------------------------")
    if not certs():
        return
    reset_store()
    clean_defs()
    srvs = []
    try:
        srvA, srvB = netfake.FakeServer(C["c1"], C["k1"]), netfake.FakeServer(C["c2"], C["k2"])
        srvs += [srvA, srvB]
        salt_a = srvA.add_user(NL_REMOTE, NL_PW, iterations=4096)
        pa, pb = srvA.port, srvB.port
        pin_a, pin_b = C["pin_a"], C["pin_b"]
        H = "127.0.0.1"
        defs = [("nlok", pa, pin_a, "sduser"), ("nlf", pa, pin_a, "sduser"), ("nlpin", pb, pin_a, "sduser"), ("nlnolist", pa, pin_a, "")]
        s.adm1(*["set.server %s %s %d reader %s read%s" % (n, H, p, pin, (" accounts " + accs) if accs else "") for n, p, pin, accs in defs])
        row("SETUP: four server definitions are on the disk (nlok and nlf for sduser; nlnolist for nobody; nlpin sends sduser to server B with server A's pin)",
            all(s.line_is(entry(n), [n, H, str(p), "reader", pin, "read", accs]) for n, p, pin, accs in defs), repr(s.file_lines()))
        if not all(entry(n) for n, *_ in defs):
            return
        missing = [n for n in NEEDED if not os.path.exists(os.path.join(s.SYS, "messages", str(n)))]
        row("SETUP: the sandbox holds every message this section prints (%d)" % len(NEEDED), not missing, "missing %r" % (missing,))

        def refuse(label, cmd, want, answers=(), prompts=False, no_pw_prompt=False, admin=False):
            """A command that must be refused BEFORE anything is dialled: the message on the screen, no success wording, the store the same bytes, the fake server never connected to, no audit line."""
            r = nl_run(cmd, answers, srvA, admin=admin)
            out, d = r["out"], r["d"]
            row("%s -> refused, nothing stored: %s" % (label, want[:70] + ("..." if len(want) > 70 else "")),
                has_msg(out, want) and not s.has(out, SUCC) and r["before"] == r["after"] and d["conns"] == 0 and s.has_text(out, s.msg(11465)) == prompts
                and (not no_pw_prompt or not s.has_text(out, s.msg(11466))) and r["audit"] is not None and "set.netlogin server=" not in r["audit"],
                "message on screen=%s prompts shown=%s connections=%d before==after %s  out %r" % (has_msg(out, want), s.has_text(out, s.msg(11465)), d["conns"], r["before"] == r["after"], out[-4:]))
            return r

        s.reg_net("yes")
        out = s.session(["set.netlogin", "delete.netlogin"], quiet=True)
        row("both verbs are in the account's VOC, from newvoc: each answers its usage line (11450, 11451)", s.has_line(out, s.msg(11450)) and s.has_line(out, s.msg(11451)), repr(out[-4:]))
        say("  (every local check comes before any prompt and before any connection)")
        refuse("set.netlogin with two words", "set.netlogin nlok nlf", s.msg(11450))
        for nm in ("1abc", "a_b", "a" * 17, "Upper_x"):
            refuse("set.netlogin with the server name %r" % nm, "set.netlogin " + nm, s.msg(11452, nm.lower()))
        for label, val in (("NET gate off (field 15 'no')", "no"), ("a record with no NET field", None), ("field 15 'true': only yes is yes", "true")):
            s.reg_net(val)
            refuse("the account with %s, on a server it is LISTED for" % label, "set.netlogin nlok", s.msg(11460))
        refuse("the gate is asked BEFORE the definition: the gate off on a server that does not exist", "set.netlogin nosuch", s.msg(11460))
        s.reg_net("yes")
        refuse("the gate on, a server that is not defined", "set.netlogin nosuch", s.msg(11430, "nosuch"))
        refuse("the gate on, a server whose list does not name the account", "set.netlogin nlnolist", s.msg(11461, "sduser", "nlnolist"))
        say("  (the prompts: a remote user or password that is not acceptable ends the command with nothing sent.  The store's directory is made BEFORE the prompts, as SD Core's helper "
            "is run before them, so it is made here first: an empty directory is not 'something stored')")
        os.makedirs(cred_dir(), exist_ok=True)
        os.chmod(cred_dir(), 0o700)
        refuse("an empty remote user", "set.netlogin nlok", s.msg(11467), [""], prompts=True, no_pw_prompt=True)
        refuse("a remote user with a space", "set.netlogin nlok", s.msg(11467), ["bad user"], prompts=True, no_pw_prompt=True)
        refuse("a remote user of 64 characters", "set.netlogin nlok", s.msg(11467), ["u" * 64], prompts=True, no_pw_prompt=True)
        refuse("an empty remote password", "set.netlogin nlok", s.msg(11468), [NL_REMOTE, ""], prompts=True)

        def fail_row(tag, server, cfg, label, user, pw, want, types):
            srvA.configure(**cfg)
            r = nl_run("set.netlogin " + server, [user, pw], srvA)
            srvA.configure()
            out, d = r["out"], r["d"]
            row("[%s] %s -> refused: %s ... nothing stored, the store the same bytes" % (tag, label, want[:60]),
                has_msg(out, want) and not s.has(out, SUCC) and r["before"] == r["after"] and d["conns"] == 1 and d["types"] == types and not d["errors"] and r["audit"] is not None
                and "set.netlogin server=" not in r["audit"] and pw not in "\n".join(out),
                "message on screen=%s before==after %s server saw %s  out %r" % (has_msg(out, want), r["before"] == r["after"], {k: d[k] for k in ("conns", "types", "errors")}, out[-4:]))

        say("  (a server that goes wrong at each step, and a wrong password; the exchange is cut short at the step named)")
        ref = s.msg(11474, " (Authentication failed)")
        for label, cfg, user, pw, want, types in (
                ("a wrong password", {}, NL_REMOTE, NL_BADPW, ref, [47, 48]),
                ("a remote user the server does not know", {}, "mallory", NL_PW, ref, [47]),
                ("an iteration count of 4095 (one below the floor)", dict(offer_iter=4095), NL_REMOTE, NL_PW, s.msg(11473, "first", "unacceptable iteration count"), [47]),
                ("a nonce that does not extend ours", dict(nonce="wrong"), NL_REMOTE, NL_PW, s.msg(11473, "first", "the nonce does not extend ours"), [47]),
                ("a WRONG v= signature (the server does not know the password)", dict(bad_v=True), NL_REMOTE, NL_PW, s.msg(11475), [47, 48]),
                ("a connection closed after the first message", dict(close_after="first"), NL_REMOTE, NL_PW, s.msg(11472, H, pa, "the server's first reply"), [47])):
            fail_row("nlf", "nlf", cfg, label, user, pw, want, types)
        row("...and after all of them the store holds nothing at all for nlf", (cred_state() or {}).get("nlf") is None, repr(cred_state()))

        say("  (the pin: a server whose key is not the pinned one is sent NOTHING)")
        r = nl_run("set.netlogin nlpin", [NL_REMOTE, NL_PW], srvB)
        out, d = r["out"], r["d"]
        row("nlpin (server B's key, server A's pin) -> 11471, the server saw the handshake and ZERO packets, nothing stored",
            has_msg(out, s.msg(11471, H, pb, "nlpin")) and d["conns"] == 1 and d["types"] == [] and r["before"] == r["after"] and (cred_state() or {}).get("nlpin") is None, repr((out[-3:], d["types"])))

        say("  (the success: the account with the gate on, listed, the right password)")
        r = nl_run("set.netlogin nlok", [NL_REMOTE, NL_PW], srvA)
        out, d = r["out"], r["d"]
        keys = netfake.derive(NL_PW, salt_a, 4096)
        ex = d["exchanges"][0] if d["exchanges"] else None
        row("set.netlogin nlok: the header (11464), both prompts, and 'Your login on server nlok as %s is stored.  The password is not stored' (11477)" % NL_REMOTE,
            has_msg(out, s.msg(11464, "nlok", H, pa)) and s.has_text(out, s.msg(11465)) and s.has_text(out, s.msg(11466)) and has_msg(out, s.msg(11477, "nlok", NL_REMOTE)), repr(out[-6:]))
        row("...the fake server saw ONE connection, exactly two packets of types 47 then 48 and nothing after, one proof verified, nothing it found wrong",
            d["conns"] == 1 and d["handshakes"] == 1 and d["types"] == [47, 48] and d["ok"] == 1 and d["bad"] == 0 and not d["errors"],
            repr({k: d[k] for k in ("conns", "handshakes", "types", "ok", "bad", "errors")}))
        row("...the ClientProof the client sent EQUALS the one computed here (PBKDF2 of the typed password with the salt and count the server gave, over the AuthMessage the server recorded)",
            ex is not None and ex["proof"] == netfake.client_proof(keys["client_key"], keys["stored_key"], ex["authmsg"]), repr(ex and ex["proof"].hex()))
        row("...the store holds the directory <sys>/netlogins (mode 700) and ONE file nlok (mode 600) with the keys hashlib derives from the password and the salt the server gave",
            cred_matches("nlok", NL_REMOTE, salt_a, 4096, keys["client_key_b64"], keys["server_key_b64"], pin_a) and (os.lstat(cred_dir()).st_mode & 0o7777) == 0o700
            and (os.lstat(cred_path("nlok")).st_mode & 0o7777) == 0o600 and sorted(os.listdir(cred_dir())) == ["nlok"], repr((cred_state(), salt_a)))
        row("...the audit trail says 'set.netlogin server=nlok remote=%s' and carries no password, key or hash" % NL_REMOTE,
            r["audit"] is not None and "set.netlogin server=nlok remote=%s" % NL_REMOTE in r["audit"] and NL_PW not in r["audit"] and keys["client_key_b64"] not in r["audit"], repr(r["audit"]))
        row("...the password is not on the screen", NL_PW not in "\n".join(out), "")
        nfiles, found = scan_for([NL_PW.encode(), NL_BADPW.encode()], [s.BOX, os.path.join(os.path.expanduser("~"), ".sd")] if os.path.isdir(os.path.expanduser("~/.sd")) else [s.BOX])
        row("...the password appears in NO file of the sandbox (%d files read, the sandbox's own copy of the source tree left out)" % nfiles, nfiles > 100 and not found[NL_PW.encode()] and not found[NL_BADPW.encode()],
            repr((nfiles, found)))

        say("  (a second login replaces the first; a failure leaves the first untouched)")
        before = cred_state()
        srvA.configure(bad_v=True)
        r = nl_run("set.netlogin nlok", [NL_REMOTE, NL_PW], srvA)
        srvA.configure()
        row("a failed replacement (a wrong server signature) leaves the stored login the same bytes, inode and mtime", not s.has(r["out"], SUCC) and cred_state() == before, repr(r["out"][-3:]))
        r = nl_run("set.netlogin nlok", [NL_REMOTE, NL_PW], srvA)
        row("a good replacement is stored (one file, the same keys: the server's salt did not change)", has_msg(r["out"], s.msg(11477, "nlok", NL_REMOTE)) and sorted(os.listdir(cred_dir())) == ["nlok"],
            repr(r["out"][-3:]))

        say("  (Solo: the ADMINISTRATOR keeps a login too, exempt from the NET gate and the accounts list; SD Core refuses it for want of a Linux login of its own)")
        s.reg_net("no")
        r = nl_run("set.netlogin nlnolist", [NL_REMOTE, NL_PW], srvA, admin=True)
        out = r["out"]
        keys = netfake.derive(NL_PW, salt_a, 4096)
        row("the administrator with the gate OFF on a server whose list names nobody: the login is stored (11477), the file nlnolist is there",
            has_msg(out, s.msg(11477, "nlnolist", NL_REMOTE)) and cred_matches("nlnolist", NL_REMOTE, salt_a, 4096, keys["client_key_b64"], keys["server_key_b64"], pin_a), repr(out[-4:]))
        s.reg_net("yes")

        say("  (delete.netlogin)")
        r = nl_run("delete.netlogin nlok")
        row("delete.netlogin nlok: 'Your login on server nlok was deleted' (11478), the file gone, the audit line says so, and the other login is untouched",
            has_msg(r["out"], s.msg(11478, "nlok")) and not os.path.exists(cred_path("nlok")) and os.path.exists(cred_path("nlnolist"))
            and r["audit"] is not None and "delete.netlogin server=nlok" in r["audit"], repr(r["out"][-3:]))
        r = nl_run("delete.netlogin nlok")
        row("...a second time: 11453 (no login stored), nothing changed", has_msg(r["out"], s.msg(11453, "nlok")) and r["before"] == r["after"], repr(r["out"][-3:]))
        r = nl_run("delete.netlogin 1bad")
        row("delete.netlogin with a bad server name: 11452", has_msg(r["out"], s.msg(11452, "1bad")), repr(r["out"][-3:]))
    finally:
        for sv in srvs:
            sv.shutdown()
        reset_store()
        clean_defs()


SECTIONS = (("connect", connect_section), ("netcred", netcred_section), ("netlogin", netlogin_section))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--sections", default="")
    a = ap.parse_args()
    s.BOX = os.path.abspath(a.dir)
    s.SYS = os.path.join(s.BOX, "sys")
    s.ACCT = os.path.join(s.SYS, "user_accounts", s.ACCOUNT)
    s.REG = os.path.join(s.SYS, "accounts", s.ACCOUNT)
    want = set(x for x in a.sections.split(",") if x)
    say("sandbox-sdnet-login: sandbox  %s" % s.BOX)
    say("sandbox-sdnet-login: tree     %s" % s.SD64)
    if a.build:
        if os.path.exists(s.BOX) and os.listdir(s.BOX):
            s.bail("%s is not empty" % s.BOX)
        r = subprocess.run([sys.executable, s.TOOL, s.BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            s.bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-sdnet-login: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(s.SYS, "bin", "sd-solo")):
        s.bail("%s holds no built sandbox (use --build, or point it at one)" % s.BOX)
    subprocess.run([sys.executable, s.TOOL, s.BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isfile(s.REG):
        s.bail("there is no register record %s" % s.REG)

    say("\n--- controls -----------------------------------------------------------------------------------------------------")
    out = s.session(["WHO.AM.I"], quiet=True)
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the session is a plain session of %s and NOT an administrator (WHO.AM.I says Admin? %s)" % (s.ACCOUNT, adm.group(1) if adm else "-"),
        s.has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        s.bail("the session is privileged; its refusals prove nothing")
    out = s.adm1("WHO.AM.I")
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("CONTROL: the ADMIN lane is an administrator (WHO.AM.I says Admin? %s)" % (adm.group(1) if adm else "-"), bool(adm) and adm.group(1) == "Yes", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "Yes"):
        s.bail("the administrator lane is not an administrator: every set.server row would be meaningless")
    try:
        for name, section in SECTIONS:
            if not want or name in want:
                section()
    finally:
        cleanup()
    say("")
    say("sandbox-sdnet-login: %d passed, %d failed" % (s.passed, s.failed))
    sys.exit(1 if s.failed else 0)


if __name__ == "__main__":
    main()
