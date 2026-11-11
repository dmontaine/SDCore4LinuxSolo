#!/usr/bin/env python3
#
# sandbox-qmclient-solo.py - the client library (sdclilib.so) of SD Core for Linux Solo through a REAL logged-in API session on Solo's own
#                            sandbox: the QMClient functions carried from SD Core for Linux on 11 Nov 26 (SD Core's work of 15 Oct 26:
#                            SDRevision, SDGetVar, SDSystem, SDIndices, SDTrans, SDRTrans, SDRecordlocked, SDTxn, SDEvaluate, SDEvalConv,
#                            SDIConv(s), SDOConv(s), the sequential files, SDWriteSeqKey / SDWriteuSeqKey, the multi-character SDDcount,
#                            thread safety, SDExecute's reply copy, vb.call's return).  No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-qmclient-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py.  With --build it is built first from THIS tree (it must be empty or absent).  Set
# SDSOLOBOX_KEYSET so as not to meet another sandbox's keys.  Exit 0 every row passed, 1 a row failed, 2 it could not run.
#
# START-HISTORY:
# 11 Nov 26 dm  Written for the Solo carry of the client library, from SD Core's sandbox-qmclient.py (155 rows, 15-18 Oct and 26-31 Oct 26).
#               WHAT IS SOLO'S HERE AND WHY:
#               - THE SESSION.  SD Core's suite signs on with SDConnectLocal (a local server on pipes); Solo has no local login (SDConnectLocal
#                 is disabled, LSOLO 15).  So the library signs on as Solo's clients do: SDConnect, TLS 1.3 and the SCRAM login with the
#                 account password (<dir>/account.pw, never printed), to a server this suite starts for each connection as the socket
#                 activator starts it (sandbox-apifile.py's Wire: `sd -n -q` with the accepted connection as descriptors 0, 1 and 2).  The
#                 port is below 32768: the library's OpenSocket takes an int16_t, and a negative port is its "no port given" (4249, the live
#                 Solo).  The certificate pin store is a scratch file (SD_KNOWN_SERVERS), never ~/.sdcore/known_servers.
#               - ONE ACCOUNT.  Solo has one account, sduser: the fixtures are made in it by ordinary sessions; SDLogto (M) is tested to the
#                 account the session is in, not to a second one; part S flips the OS switch of sduser's own register record (fields 7 and 8,
#                 SET.OS.ACCESS's), and puts the record back as it was.
#               - REQUEST 49.  SD Core's 49 is QMRevision; Solo's 49 has been SrvrSshKey since 30 Sep 26 (LSOLO 19, agreed with Windows Solo),
#                 so the carry left 49 alone and SDRevision against a Solo server answers 0.0-0 for the server.  Row A2 says so; it is the
#                 measured state of a reported conflict, not a decision.
#               - NOT CARRIED, so not here: part N (MASTER.LOGIN in an API session, sheet 170), part O (the BASIC class !sdclient, sheet 571)
#                 and the QMC_MUTANT runs.
# END-HISTORY
#
# THE INSTRUMENT.  The sandbox's own bin/sdclilib.so is loaded with ctypes, so the C client, the wire protocol and apisrvr are all the ones
# under test.  The expected values are computed apart from the call: the revision from revstamp.h, the data from the records the probe
# wrote, the index details from INDICES() in an ordinary session, a lowered record by lowering the SDRead answer here, the disk read by
# this program.  Every helper process (threads, SIGPIPE, SDExecute) is a CHILD, so a crash or a hang is a failed row.
#
#   A SDRevision, SDSystem(1012)   B SDGetVar   C SDSystem   D SDIndices   E SDTrans / SDRTrans   F NON.DURABLE.TXN (program form)   G SDTxn
#   H SDEvaluate / SDEvalConv   I SDIConv / SDOConv / SDIConvs / SDOConvs   J several sessions, a waiting session, a failed connect,
#   SDRecordlocked, SIGPIPE   L SDDcount / SDChange   U SDChecksum   M SDLogto   P sequential files   Q CREATING.SEQKEY and SDWriteSeqKey
#   R six threads   S a pathname outside the account with the OS switch on   K AUTOLOGOUT   T SDCLIENT in sd.conf (LAST: it restarts SD)
#
# NULL CASES REFUSED OUT LOUD.  The suite stops (exit 2) when: the ordinary session is privileged, the programs do not compile, the fixture
# file is not made, the library does not sign on, or no row ran.

import ctypes
import datetime
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ACCOUNT = "sduser"
FM, VM, SM = b"\xfe", b"\xfd", b"\xfc"
SECRETS = []
passed = failed = 0
BOX = SYS = ACCT = REG = SD = ""
PWB = b""
ACT = None

ND_BODY = ("   open 'zzcl' to f else stop 'no file'\n   sc = field(@sentence, ' ', 4)\n"
           "   transaction start\n"
           "   readu x from f, 'p1' else null\n   readu x from f, 'both' else null\n"
           "   write 'parent' on f, 'p1'\n   write 'parent first' on f, 'both'\n"
           "   transaction start\n"
           "   readu x from f, 'c1' else null\n   readu x from f, 'old' else null\n"
           "   write 'child' on f, 'c1'\n   write 'child second' on f, 'both'\n"
           "   if sc = 'delold' then delete f, 'old'\n"
           "   if sc = 'lock' then readu x from f, 'lk' else x = ''\n"
           "   transaction commit\n"
           "   crt 'LOCK1[':recordlocked(f, 'lk'):']'\n"
           "   crt 'CACHE[':change(change(system(1065), @fm, '/'), @vm, '|'):']'\n"
           "   if sc = 'abort' or sc = 'delold' then\n      transaction abort\n   end else\n      transaction commit\n   end\n"
           "   crt 'LOCK2[':recordlocked(f, 'lk'):']'\n"
           "   crt 'DEPTH[':system(1008):']'\n"
           "end\n")

USER_PROGS = {
    "zzcsub": "subroutine zzcsub(a, b)\n   b = a : '/' : a\nreturn\nend\n",
    "zzcmk": "subroutine zzcmk(a, b)\n   open 'zzlog' to f else return\n   write 'ran ':a on f, 'callmark'\n   b = 'ret:':a\nreturn\nend\n",
    "zzcok": "$sdcall\nsubroutine zzcok(a, b)\n   open 'zzlog' to f else return\n   write 'ran ':a on f, 'okmark'\n   b = 'ret:':a\nreturn\nend\n",
    "zzxmk": "   open 'zzlog' to f else stop\n   write 'ran' on f, 'execmark'\nend\n",
    "zzmrk": ("   open 'zzlog' to f else stop 'no file'\n   sc = field(@sentence, ' ', 4)\n"
              "   for each id in 'callmark':@fm:'okmark':@fm:'execmark'\n"
              "      read r from f, id then crt 'M[':id:'=':r:']' else crt 'M[':id:'=-]'\n"
              "      if sc = 'clear' then delete f, id\n   next id\n"
              "   open 'zzcl' to g else stop 'no zzcl'\n   crt 'TC[':oconv('r1', 'Tzzcl;X;;1'):']'\nend\n"),
    "zzclmk": ("   open 'zzcl' to f else stop 'no file'\n   open 'DICT zzcl' to d else stop 'no dict'\n"
               "   write 'D':@fm:'1':@fm:'':@fm:'Name':@fm:'10L':@fm:'S' on d, 'NAME'\n"
               "   write 'D':@fm:'2':@fm:'':@fm:'Qty':@fm:'5R':@fm:'S' on d, 'QTY'\n"
               "   write 'D':@fm:'3':@fm:'':@fm:'Tags':@fm:'8L':@fm:'M' on d, 'TAGS'\n"
               "   write 'Widget':@fm:'5':@fm:'red':@vm:'blue' on f, 'r1'\n"
               "   write 'Gadget':@fm:'7':@fm:'green' on f, 'r2'\n"
               "   write 'Gizmo':@fm:'9':@fm:'a':@vm:'b':@vm:'c' on f, 'r3'\n"
               "   write 'I':@fm:'QTY * 2':@fm:'':@fm:'Dbl':@fm:'8R':@fm:'S' on d, 'DOUBLE'\n"
               "   write 'I':@fm:'NAME':@fm:'MCU':@fm:'Up':@fm:'10L':@fm:'S' on d, 'UPNAME'\n"
               "   write 'I':@fm:'@ID':@fm:'':@fm:'Id':@fm:'6L':@fm:'S' on d, 'IDCOPY'\n"
               "   write 'I':@fm:'QTY *':@fm:'':@fm:'Bad':@fm:'8R':@fm:'S' on d, 'BADI'\n"
               "   write 'A':@fm:'1':@fm:'Name':@fm:'':@fm:'':@fm:'S':@fm:'MCU':@fm:'':@fm:'L':@fm:'10' on d, 'ANAME'\n"
               "   write 'A':@fm:'2':@fm:'Qty':@fm:'':@fm:'':@fm:'S':@fm:'':@fm:\"A;2*'3'\":@fm:'R':@fm:'5' on d, 'ATRIPLE'\n"
               "   write 'D':@fm:'4':@fm:'D4/':@fm:'When':@fm:'10L':@fm:'S' on d, 'WHEN'\n"
               "   write 'D':@fm:'3':@fm:'MCU':@fm:'TagsUp':@fm:'8L':@fm:'M' on d, 'TAGU'\n"
               "   write 'PH':@fm:'LIST zzcl' on d, 'PH1'\n"
               "   crt 'MADE'\nend\n"),
    "zzndt": "$mode non.durable.txn\n" + ND_BODY,
    "zzdur": ND_BODY,
    "zzndr": ("   open 'zzcl' to f else stop 'no file'\n"
              "   for each id in 'p1' : @fm : 'c1' : @fm : 'both' : @fm : 'old' : @fm : 'lk' : @fm : 'top'\n"
              "      read r from f, id then crt 'R[':id:'=':r:']' else crt 'R[':id:'=-]'\n"
              "   next id\nend\n"),
    "zzndw": ("   open 'zzcl' to f else stop 'no file'\n   write 'old data' on f, 'old'\nend\n"),
    "zzprmp": "   input x\n   crt 'GOT[':x:']'\nend\n",
    "zzstr": ("   crt 'D1[':dcount('a,b,c', ','):']'\n   crt 'D2[':dcount('a::b::c::d', '::'):']'\n   crt 'D3[':dcount('aaaa', 'aa'):']'\n"
              "   crt 'D4[':dcount('a,b', ',,'):']'\n   crt 'D5[':dcount('', ','):']'\n   crt 'D6[':dcount('ab--cd--', '--'):']'\n"
              "   crt 'C1[':change('aaaa', 'aa', 'b'):']'\n   crt 'C2[':change('aaa', 'aa', 'b'):']'\n"
              "   crt 'C3[':change('abababa', 'aba', 'X'):']'\n   crt 'C4[':change('abcabcabcabc', 'abc', 'Z', 2, 2):']'\n"
              "   crt 'C5[':change('hello', 'l', ''):']'\n   crt 'C6[':change('hello', 'xyz', 'Q'):']'\n"
              "   crt 'C7[':change('xx--xx--xx', '--', '<>'):']'\n   crt 'C8[':change('aXbXc', 'X', 'YY', 1, 2):']'\nend\n"),
    "zzsum": ("   crt 'U1[':checksum('ABCDE'):']'\n   crt 'U2[':checksum(''):']'\n   crt 'U3[':checksum('a'):']'\n"
              "   crt 'U4[':checksum('hello world'):']'\n   crt 'U5[':checksum('a':char(200):'z'):']'\n"
              "   crt 'U6[':checksum(char(255)):']'\n   crt 'U7[':checksum(char(128):char(128)):']'\n"
              "   crt 'U8[':checksum(str('0123456789', 1000)):']'\n   crt 'U9[':checksum('ab':@vm:'cd':@fm:'e'):']'\n"
              "   crt 'UA[':checksum('abcdefghijklmnopqrstuvwxyz0123456789'):']'\nend\n"),
    "zzsk": ("   open 'zzsq' to f else stop 'no file'\n   write 'first' to f creating.seqkey id1\n   write 'second' to f creating.seqkey id2\n"
             "   writeu 'third' to f creating.seqkey id3\n   crt 'IDS[':id1:'|':id2:'|':id3:']'\n"
             "   crt 'LOCK3[':recordlocked(f, id3):']'\n   crt 'LOCK2[':recordlocked(f, id2):']'\n   release f, id3\n"
             "   read r from f, id2 then crt 'REC2[':r:']' else crt 'REC2[none]'\n   crt 'LAST[':fileinfo(f, 1031):']'\nend\n"),
    "zzskt": ("   open 'zzsq' to f else stop 'no file'\n   transaction start\n   write 'in txn' to f creating.seqkey tid\n"
              "   transaction commit\n   read r from f, tid then crt 'TXN[':tid:'=':r:']' else crt 'TXN[none]'\nend\n"),
    "zzskd": ("   open 'zzdir' to d else stop 'no dir'\n   id = ''\n   write 'x' to d creating.seqkey id on error crt 'REFUSED[':status():']'\n"
              "   crt 'AFTER[':id:']'\nend\n"),
    "zzclix": ("   open 'zzcl' to f else stop 'no file'\n"
               "   crt 'NAMES[':change(indices(f), @fm, '/'):']'\n"
               "   crt 'DET[':change(change(change(indices(f, 'NAME'), @fm, '/'), @vm, '|'), @sm, '~'):']'\n"
               "end\n"),
}
FIXTURE_FILES = ("zzcl", "zzlog", "zzdir", "zzsq")
CATALOGUED = ("zzcsub", "zzcmk", "zzcok")

# The children sign on as this suite does: argv carries the library, the port and the sandbox (the password is read there, from
# account.pw: it is never on a command line).
CONNECT_PRELUDE = r'''
import ctypes, os, sys
def _pw(box):
    with open(os.path.join(box, "account.pw")) as f:
        return f.read().strip().encode()
def sd_connect(lib, port, box):
    lib.SDConnect.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.SDConnect.restype = ctypes.c_int
    return lib.SDConnect(b"127.0.0.1", port, b"sduser", _pw(box), b"sduser")
'''

# R: the client library used by several threads of one process (sheet 456).  argv: the library, the thread count, the revision, the port,
# the sandbox.
THREAD_CHILD = CONNECT_PRELUDE + r'''
import json, threading

lib = ctypes.CDLL(sys.argv[1])
NT = int(sys.argv[2])
REV = sys.argv[3]
PORT = int(sys.argv[4])
BOX = sys.argv[5]
for fn in ("SDGetVar", "SDRead", "SDSystem", "SDError", "SDGetArg"):
    getattr(lib, fn).restype = ctypes.c_void_p
for fn in ("SDOpen", "SDGetSession", "SDSetSession", "SDConnected"):
    getattr(lib, fn).restype = ctypes.c_int


def text(p):
    if not p:
        return None
    b = ctypes.string_at(p)
    lib.SDFree(ctypes.c_void_p(p))
    return b


def err():
    p = lib.SDError()
    return ctypes.string_at(p) if p else b""


out = {"nt": NT}
errors = []
bar = threading.Barrier(NT, timeout=120)
sess = [None] * NT


def phases(i):
    s = {"ok": None, "idx": None, "who": None, "bad": None, "wrong": None}
    sess[i] = s
    bar.wait()
    s["ok"] = sd_connect(lib, PORT, BOX)
    s["idx"] = lib.SDGetSession()
    who = text(lib.SDGetVar(b"@USERNO"))
    s["who"] = None if who is None else who.decode("latin-1")
    bar.wait()
    bad = 0
    for _ in range(100):
        if lib.SDGetSession() != s["idx"]:
            bad += 1
        w = text(lib.SDGetVar(b"@USERNO"))
        if w is None or w.decode("latin-1") != s["who"]:
            bad += 1
    s["bad"] = bad
    fno = lib.SDOpen(b"zzlog")
    rid = ("thr%d" % i).encode()
    data = bytes([65 + i]) * (3000 + 7000 * i)
    lib.SDWrite(fno, rid, data)
    bar.wait()
    wrong = 0
    for _ in range(40):
        got = text(lib.SDRead(fno, rid, ctypes.byref(ctypes.c_int())))
        if got != data:
            wrong += 1
    s["wrong"] = wrong
    cw = 0
    for n in range(40):
        tok = ("t%d-%d" % (i, n)).encode()
        lib.SDCallx(b"zzcsub", ctypes.c_int16(2), tok, b"")
        got = text(lib.SDGetArg(2))
        if got != tok + b"/" + tok:
            cw += 1
    s["callx_wrong"] = cw
    bar.wait()
    lib.SDDelete(fno, rid)
    lib.SDDisconnect()


def guard(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        errors.append(repr(e))


ts = [threading.Thread(target=guard, args=(phases, i)) for i in range(NT)]
for t in ts:
    t.start()
for t in ts:
    t.join(200)
out["sessions"] = sess

bar4 = threading.Barrier(2, timeout=120)
box = {}


def failer():
    box["r"] = lib.SDConnect(b"127.0.0.1", 1, b"nobody", b"x", b"sduser")
    box["e1"] = err().decode("latin-1")
    bar4.wait()
    bar4.wait()
    box["e2"] = err().decode("latin-1")
    box["connected"] = lib.SDConnected()


def churner():
    bar4.wait()
    n = 0
    for _ in range(10):
        if sd_connect(lib, PORT, BOX) == 1:
            n += 1
            lib.SDDisconnect()
    box["churn"] = n
    bar4.wait()


t1 = threading.Thread(target=guard, args=(failer,))
t2 = threading.Thread(target=guard, args=(churner,))
t1.start(); t2.start(); t1.join(180); t2.join(180)
out["failed"] = box

ok = sd_connect(lib, PORT, BOX)
rv = text(lib.SDSystem(1012))
lib.SDDisconnect()
out["control"] = [ok, None if rv is None else rv.decode("latin-1")]
out["errors"] = errors
print("RESULT " + json.dumps(out))
'''

# T: SDExecute several times in a child process.  argv: the library, the count, the command, the port, the sandbox.
EXEC_CHILD = CONNECT_PRELUDE + r'''
lib = ctypes.CDLL(sys.argv[1])
lib.SDExecute.restype = ctypes.c_void_p
if sd_connect(lib, int(sys.argv[4]), sys.argv[5]) != 1:
    print("NOCONNECT")
    sys.exit(2)
n = int(sys.argv[2])
for i in range(n):
    e = ctypes.c_int()
    p = lib.SDExecute(sys.argv[3].encode(), ctypes.byref(e))
    if i == 0:
        print("FIRST err", e.value, flush=True)
    if p:
        lib.SDFree(ctypes.c_void_p(p))
print("LOOPS", n, flush=True)
lib.SDDisconnect()
'''

# J5: SIGPIPE at its default action.  The child signs on, says CONNECTED and waits; the suite kills the server the activator started for it;
# the child then sends a request.  argv: the library, the port, the sandbox.
PIPE_CHILD = CONNECT_PRELUDE + r'''
import signal, time
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
lib = ctypes.CDLL(sys.argv[1])
lib.SDSystem.restype = ctypes.c_void_p
if sd_connect(lib, int(sys.argv[2]), sys.argv[3]) != 1:
    print('NOCONNECT', flush=True); sys.exit(2)
print('CONNECTED', flush=True)
sys.stdin.readline()
time.sleep(1)
r = lib.SDSystem(1012)
print('ANSWER', 'EMPTY' if (not r or ctypes.string_at(r) == b'') else 'GOT', flush=True)
r = lib.SDSystem(1012)
print('SURVIVED', flush=True)
lib.SDDisconnect()
print('DISCONNECTED', flush=True)
'''


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
    say("sandbox-qmclient-solo: CANNOT RUN - " + msg)
    if ACT is not None:
        ACT.stop()
    sys.exit(2)


def env():
    e = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"))
    e.pop("SSH_CONNECTION", None)
    e.pop("SSH_TTY", None)
    return e


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


def plain(cmds, timeout=300):
    """An ordinary session of sduser on a pipe (the account password as the first line, never printed).  The lines printed after the TERM
    line, echoed commands and blank lines left out."""
    body = secret("account.pw") + "\n" + "TERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n"
    say("    > " + " | ".join(cmds))
    p = subprocess.Popen([os.path.join(SYS, "bin", "sd-solo")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         cwd=SYS, env=env(), text=True, errors="replace")
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


def has(lines, pattern):
    return any(re.search(pattern, ln) for ln in lines)


def audit_off():
    """Size of the sandbox's audit file (SD appends to it and never creates it: made empty when missing); None when it cannot be."""
    path = os.path.join(SYS, "audit")
    try:
        if not os.path.exists(path):
            with open(path, "ab"):
                pass
        return os.path.getsize(path)
    except OSError:
        return None


def audit_new(off):
    """What the audit trail gained since OFF; None when it cannot be read (a row that needs a line then FAILS)."""
    if off is None:
        return None
    try:
        with open(os.path.join(SYS, "audit"), "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def tag(lines, name):
    out = []
    for ln in lines:
        m = re.match(r"^%s\[(.*)\]\s*$" % re.escape(name), ln)
        if m:
            out.append(m.group(1))
    return out


def put(path, text_):
    with open(path, "w", encoding="latin-1") as f:
        f.write(text_)


def s(b):
    if b is None:
        return "None"
    return b.decode("latin-1").replace("\xfe", "<FM>").replace("\xfd", "<VM>").replace("\xfc", "<SM>")


def cap_stderr(fn):
    with tempfile.TemporaryFile() as tf:
        saved = os.dup(2)
        os.dup2(tf.fileno(), 2)
        try:
            r = fn()
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        tf.seek(0)
        return r, tf.read().decode("latin-1")


class Activator:
    """What Solo's socket activator does for each connection, for this suite's own port: accept, and start `sd -n -q` with the connection as
    descriptors 0, 1 and 2 (sandbox-apifile.py's Wire does the same for one connection).  The port is chosen below 32768 (see the header)."""

    def __init__(self):
        self.lst = socket.socket()
        self.lst.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        for _ in range(200):
            port = random.randint(21000, 32000)
            try:
                self.lst.bind(("127.0.0.1", port))
                break
            except OSError:
                continue
        else:
            bail("no free port below 32768 for the activator")
        self.port = self.lst.getsockname()[1]
        self.lst.listen(64)
        self.procs = []
        self.lock = threading.Lock()
        self.th = threading.Thread(target=self.loop, daemon=True)
        self.th.start()
        say("sandbox-qmclient-solo: activator on 127.0.0.1:%d starts `%s -n -q` for each connection" % (self.port, SD))

    def loop(self):
        while True:
            try:
                conn, _ = self.lst.accept()
            except OSError:
                return
            try:
                p = subprocess.Popen([SD, "-n", "-q"], stdin=conn, stdout=conn, stderr=conn, start_new_session=True, env=env(), cwd=SYS)
                with self.lock:
                    self.procs.append(p)
            except OSError as e:
                say("    activator: could not start the server: %s" % e)
            finally:
                conn.close()

    def count(self):
        with self.lock:
            return len(self.procs)

    def since(self, n):
        with self.lock:
            return list(self.procs[n:])

    @staticmethod
    def kill(p):
        for sig in (signal.SIGHUP, signal.SIGKILL):
            try:
                os.killpg(p.pid, sig)
            except OSError:
                pass
            t0 = time.time()
            while time.time() - t0 < 2.0 and p.poll() is None:
                time.sleep(0.1)

    def stop(self):
        try:
            self.lst.close()
        except OSError:
            pass
        with self.lock:
            procs = list(self.procs)
        for p in procs:
            if p.poll() is None:
                self.kill(p)


def restart(*extra):
    """Stop the sandbox, put `extra` lines at the end of sd.conf below a marker (none: the file as built), start it, say whether SD runs (an
    ordinary session of sduser signs on and WHO.AM.I names the account)."""
    mark = "# --- sandbox-qmclient-solo below ---"
    conf = os.path.join(BOX, "sd.conf")
    subprocess.run([sys.executable, TOOL, BOX, "stop"], capture_output=True, text=True, errors="replace", timeout=120)
    with open(conf) as f:
        base = f.read().split(mark)[0].rstrip("\n") + "\n"
    with open(conf, "w") as f:
        f.write(base + ((mark + "\n" + "".join(l + "\n" for l in extra)) if extra else ""))
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=180)
    out = plain(["WHO.AM.I"])
    ok = has(out, r"Account\s*:\s*sduser")
    say("  -- sd.conf %s: SD %s" % (("+ " + " ".join(extra)) if extra else "as built", "up" if ok else "NOT UP"))
    return ok


def main():
    global BOX, SYS, ACCT, REG, SD, PWB, ACT
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-qmclient-solo.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    SD = os.path.join(SYS, "bin", "sd")
    ACCT = os.path.join(SYS, "user_accounts", ACCOUNT)
    REG = os.path.join(SYS, "accounts", ACCOUNT)
    say("sandbox-qmclient-solo: sandbox  %s" % BOX)
    say("sandbox-qmclient-solo: tree     %s" % SD64)
    if os.geteuid() == 0:
        bail("this is root; Solo never runs as root")
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-qmclient-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % BOX)
    if not os.path.isfile(REG):
        bail("there is no register record %s" % REG)
    PWB = secret("account.pw").encode()
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    os.makedirs(os.path.join(BOX, "sd-tls"), mode=0o700, exist_ok=True)
    pins = os.path.join(BOX, "qmclient-known-servers")
    if os.path.exists(pins):
        os.remove(pins)
    os.environ["SD_KNOWN_SERVERS"] = pins          # the library's certificate pins go here, never to ~/.sdcore/known_servers
    os.environ["SD_CONFIG"] = os.path.join(BOX, "sd.conf")
    with open(REG, "rb") as f:
        reg_orig = f.read()

    say("\n--- preparation ------------------------------------------------------------------------------------------------")
    out = plain(["WHO.AM.I"])
    adm = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("setup: the session is a plain session of sduser and NOT an administrator (WHO.AM.I says Admin? %s)" % (adm.group(1) if adm else "-"),
        has(out, r"Account\s*:\s*sduser") and bool(adm) and adm.group(1) == "No", "output=%r" % (out[:4],))
    if not (adm and adm.group(1) == "No"):
        bail("the session is privileged; its refusals prove nothing")
    plain(["DELETE.CATALOG %s LOCAL" % " ".join(CATALOGUED)] + ["DELETE.FILE %s NO.QUERY" % f for f in FIXTURE_FILES])   # a run before this one
    for nm, body in USER_PROGS.items():
        put(os.path.join(ACCT, "bp", nm), body)
    comp = plain(["BASIC bp " + " ".join(USER_PROGS)])
    if not has(comp, r"^Compiled %d program\(s\) with no errors" % len(USER_PROGS)):
        bail("the probe programs did not compile: " + repr(comp[-8:]))
    fx = plain(["CREATE.FILE zzcl DYNAMIC", "RUN bp zzclmk", "CREATE.INDEX zzcl NAME", "BUILD.INDEX zzcl NAME", "CREATE.FILE zzlog DYNAMIC",
                "CREATE.FILE zzdir DIRECTORY", "CREATE.FILE zzsq DYNAMIC"])
    if not has(fx, r"^MADE$"):
        bail("the fixture file was not made: " + repr(fx[-8:]))
    csub = plain(["CATALOG bp %s LOCAL" % nm for nm in CATALOGUED])
    say("    catalogue: %r" % csub[-4:])
    ix = plain(["RUN bp zzclix"])
    if not tag(ix, "NAMES"):
        bail("the index of the fixture file was not made: " + repr(ix))
    for nm in ("inside.txt",):
        if os.path.exists(os.path.join(ACCT, nm)):
            os.remove(os.path.join(ACCT, nm))

    with open(os.path.join(SD64, "gplsrc", "revstamp.h")) as f:
        m = re.search(r'#define\s+SD_REV_STAMP\s+"([^"]+)"', f.read())
    rev = m.group(1).encode() if m else None
    if rev is None:
        bail("no SD_REV_STAMP in revstamp.h")

    ACT = Activator()
    LIBPATH = os.path.join(SYS, "bin", "sdclilib.so")
    lib = ctypes.CDLL(LIBPATH)
    for fn in ("SDRevision", "SDGetVar", "SDSystem", "SDIndices", "SDTrans", "SDRTrans", "SDRead", "SDReadu", "SDReadl", "SDExecute", "SDError",
               "SDEvaluate", "SDEvalConv", "SDIConv", "SDOConv", "SDIConvs", "SDOConvs", "SDChange", "SDRespond",
               "SDReadSeq", "SDReadBlk", "SDGetArg", "SDWriteSeqKey", "SDWriteuSeqKey"):
        getattr(lib, fn).restype = ctypes.c_void_p
    for fn in ("SDOpen", "SDStatus", "SDConnectLocal", "SDGetSession", "SDSetSession", "SDLogto", "SDOpenSeq", "SDRecordlocked", "SDConnected"):
        getattr(lib, fn).restype = ctypes.c_int
    lib.SDConnect.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.SDConnect.restype = ctypes.c_int

    def connect():
        return lib.SDConnect(b"127.0.0.1", ACT.port, ACCOUNT.encode(), PWB, ACCOUNT.encode())

    def text(ptr):
        if not ptr:
            return None
        b = ctypes.string_at(ptr)
        lib.SDFree(ctypes.c_void_p(ptr))
        return b

    def call(name, *a):
        return text(getattr(lib, name)(*a))

    def err():
        p = lib.SDError()
        return ctypes.string_at(p) if p else b""

    try:
        say("\n--- A. SDRevision, SDConnectLocal ------------------------------------------------------------------------------")
        r0 = call("SDRevision")
        row("A1: before a connection SDRevision is the client's revision alone (SD_REV_STAMP of revstamp.h)", r0 == rev, s(r0) + " vs " + s(rev))
        lr = lib.SDConnectLocal(b"sduser")
        row("A1b: SDConnectLocal is still disabled in Solo (LSOLO 15): it fails and says to connect with SDConnect and the account password",
            lr == 0 and b"SDConnectLocal is not available" in err(), "%r, %s" % (lr, s(err())))
        ok = connect()
        row("A0: SDConnect signs on to the sandbox's server (TLS, SCRAM with the account password) and enters sduser", ok == 1,
            "connect %r, error %s" % (ok, s(err())))
        if ok != 1:
            bail("no API session; nothing below can run")
        r1 = call("SDRevision")
        row("A2: connected it is client, a value mark, server - the server part is this build's revision: request 49 is SD Core's "
            "QMRevision on Solo too since 11 Nov 26 (the ssh key moved to 72)", r1 == rev + VM + rev, s(r1))
        sy = call("SDSystem", 1012)
        row("A3: SDSystem(1012) is the server revision, this build's", sy == rev, s(sy))

        say("\n--- B. SDGetVar -----------------------------------------------------------------------------------------------")
        text(lib.SDExecute(b"SELECT zzcl", ctypes.byref(ctypes.c_int())))
        sel = call("SDGetVar", b"@SELECTED")
        row("B1: @SELECTED after a select of the three records is 3, as a string", sel == b"3", s(sel))
        row("B1: ... with no @ and in lower case the same", call("SDGetVar", b"selected") == b"3" and call("SDGetVar", b"SELECTED") == b"3", "")
        pth = call("SDGetVar", b"@PATH")
        row("B2: @PATH is the account's directory", pth is not None and os.path.realpath(pth.decode()) == os.path.realpath(ACCT), s(pth))
        row("B2: @WHO is the account's name", call("SDGetVar", b"@WHO") == b"sduser", s(call("SDGetVar", b"@WHO")))
        row("B3: a name it does not know gives the null string, not an error", call("SDGetVar", b"@NOSUCHTHING") == b"", s(call("SDGetVar", b"@NOSUCHTHING")))
        text(lib.SDExecute(b'SELECT zzcl WITH NAME = "Widget"', ctypes.byref(ctypes.c_int())))
        row("B4: CONTROL: after a select of one record @SELECTED is 1 (the value follows the session, it is not a constant)",
            call("SDGetVar", b"@SELECTED") == b"1", s(call("SDGetVar", b"@SELECTED")))
        row("B5: @USERNO is a user number, a plain integer", re.fullmatch(rb"\d+", call("SDGetVar", b"@USERNO") or b"") is not None,
            s(call("SDGetVar", b"@USERNO")))

        say("\n--- C. SDSystem -----------------------------------------------------------------------------------------------")
        row("C1: SDSystem(1052), the count of child phantoms, is 0 in a session that started none", call("SDSystem", 1052) == b"0", s(call("SDSystem", 1052)))
        row("C2: a key the server has no meaning for answers 0 and the session goes on", call("SDSystem", 99999) in (b"0", b""), s(call("SDSystem", 99999)))
        row("C3: CONTROL: the session still works afterwards (SDSystem(1012) again)", call("SDSystem", 1012) == rev, "")

        say("\n--- D. SDIndices ----------------------------------------------------------------------------------------------")
        fno = lib.SDOpen(b"zzcl")
        row("D0: the file opens through the API", fno >= 1, str(fno))
        names = call("SDIndices", fno, b"")
        want_names = (tag(ix, "NAMES") or [""])[0].replace("/", "\xfe").encode("latin-1")
        row("D1: with no index name SDIndices gives the file's index names (INDICES(f) in a session)", names == want_names, s(names) + " vs " + s(want_names))
        det = call("SDIndices", fno, b"NAME")
        want = (tag(ix, "DET") or [""])[0].replace("/", "\xfe").replace("|", "\xfd").replace("~", "\xfc").encode("latin-1")
        row("D2: with a name it gives the details of the index (INDICES(f, name) in a session)", det == want and det != b"", s(det) + " vs " + s(want))
        row("D3: an index the file has not gives the null string", call("SDIndices", fno, b"NOPE") == b"", s(call("SDIndices", fno, b"NOPE")))
        row("D4: CONTROL: a file number that was never opened is refused (nothing returned, no crash)",
            call("SDIndices", 99, b"") in (b"", None), s(call("SDIndices", 99, b"")))

        say("\n--- E. SDTrans and SDRTrans -----------------------------------------------------------------------------------")
        rec1 = text(lib.SDRead(fno, b"r1", ctypes.byref(ctypes.c_int())))
        row("E0: the records read back as written (the oracle)", rec1 == b"Widget" + FM + b"5" + FM + b"red" + VM + b"blue", s(rec1))
        if rec1 is None:
            bail("the fixture record r1 cannot be read through the API")
        row("E1: SDTrans of a dictionary field (NAME) of r1 is Widget", call("SDTrans", b"zzcl", b"r1", b"NAME", b"X") == b"Widget", s(call("SDTrans", b"zzcl", b"r1", b"NAME", b"X")))
        row("E1: ... a field number (2) the same way: 5", call("SDTrans", b"zzcl", b"r1", b"2", b"X") == b"5", "")
        low = rec1.replace(VM, SM).replace(FM, VM)
        whole = call("SDTrans", b"zzcl", b"r1", b"-1", b"X")
        row("E2: field -1 is the whole record with the marks lowered one level (field marks become value marks)", whole == low, s(whole) + " vs " + s(low))
        raw = call("SDRTrans", b"zzcl", b"r1", b"-1", b"X")
        row("E2: SDRTrans leaves the marks as they are: the record exactly as SDRead has it", raw == rec1, s(raw))
        multi = call("SDTrans", b"zzcl", b"r1" + VM + b"r2", b"NAME", b"X")
        row("E3: a list of ids gives the answers as a value mark list: Widget, Gadget", multi == b"Widget" + VM + b"Gadget", s(multi))
        mv = call("SDTrans", b"zzcl", b"r3", b"TAGS", b"X")
        rmv = call("SDRTrans", b"zzcl", b"r3", b"TAGS", b"X")
        row("E4: a multivalued field: SDRTrans gives its value marks, SDTrans lowers them to subvalue marks",
            rmv == b"a" + VM + b"b" + VM + b"c" and mv == b"a" + SM + b"b" + SM + b"c", s(mv) + " / " + s(rmv))
        row("E5: a record that is not there: X gives the null string, C gives the id", call("SDTrans", b"zzcl", b"nope", b"NAME", b"X") == b""
            and call("SDTrans", b"zzcl", b"nope", b"NAME", b"C") == b"nope", s(call("SDTrans", b"zzcl", b"nope", b"NAME", b"C")))
        row("E5: no action means X", call("SDTrans", b"zzcl", b"nope", b"NAME", b"") == b"", "")
        row("E6: a file that is not there gives the null string", call("SDTrans", b"nosuchfile", b"r1", b"NAME", b"X") == b"", "")
        row("E6: so does a field the dictionary has not",
            call("SDTrans", b"zzcl", b"r1", b"NOSUCH", b"X") in (b"", b"r1"), s(call("SDTrans", b"zzcl", b"r1", b"NOSUCH", b"X")))
        bad = call("SDTrans", b"zzcl", b"r1", b"NAME", b"B")
        row("E7: the B (binary) action is refused: nothing returned", bad == b"" or bad is None, s(bad))
        row("E7: CONTROL: the session still works afterwards", call("SDTrans", b"zzcl", b"r2", b"QTY", b"X") == b"7", "")

        say("\n--- F. NON.DURABLE.TXN (the program form) ---------------------------------------------------------------------")

        def disk():
            out_ = plain(["RUN bp zzndr"])
            return {m_.group(1): m_.group(2) for m_ in (re.match(r"^R\[([a-z0-9]+)=(.*)\]$", t) for t in out_) if m_}

        def reset():
            plain(["DELETE zzcl p1", "DELETE zzcl c1", "DELETE zzcl both", "DELETE zzcl lk", "RUN bp zzndw"])

        def run(prog, sc):
            reset()
            out_ = plain(["RUN bp %s %s" % (prog, sc)])
            return out_, disk()

        out, d = run("zzndt", "commit")
        cache = (tag(out, "CACHE") or [""])[0]
        row("F1: non-durable, the child's COMMIT writes nothing: the cache lists the child's records under the PARENT's transaction "
            "(p1, both, c1 - all W, one transaction number)",
            len(cache.split("/")) == 3 and len({e.split("|")[0] for e in cache.split("/")}) == 1
            and {e.split("|")[2] for e in cache.split("/") if len(e.split("|")) > 2} == {"p1", "c1", "both"}, cache)
        row("F1: ... and the parent's COMMIT then writes them all, the later write of 'both' (the child's) winning",
            d.get("p1") == "parent" and d.get("c1") == "child" and d.get("both") == "child second", repr(d))
        out, d = run("zzndt", "abort")
        row("F2: non-durable, the parent ABORTS after the child committed: neither the parent's nor the child's record reached the disk",
            d.get("p1") == "-" and d.get("c1") == "-" and d.get("both") == "-", repr(d))
        out, d = run("zzdur", "abort")
        row("F3: CONTROL, the same program without the mode: the child's COMMIT is durable and survives the parent's abort",
            d.get("c1") == "child" and d.get("both") == "child second" and d.get("p1") == "-", repr(d))
        out, d = run("zzdur", "commit")
        row("F3: CONTROL, durable, parent commits: everything on disk too", d.get("p1") == "parent" and d.get("c1") == "child", repr(d))
        out, d = run("zzndt", "delold")
        row("F4: non-durable: a record the child deleted comes back when the parent aborts ('old' still on disk)", d.get("old") == "old data", repr(d))
        out, d = run("zzdur", "delold")
        row("F4: CONTROL, durable: the same delete stays deleted", d.get("old") == "-", repr(d))
        out, d = run("zzndt", "lock")
        row("F5: the child's lock is held after its non-durable COMMIT (RECORDLOCKED non-zero) and released when the parent commits (0)",
            tag(out, "LOCK1") not in ([], ["0"]) and tag(out, "LOCK2") == ["0"], repr((tag(out, "LOCK1"), tag(out, "LOCK2"))))
        out, d = run("zzdur", "lock")
        row("F5: CONTROL, durable: the child's COMMIT releases its lock at once (0)", tag(out, "LOCK1") == ["0"], repr(tag(out, "LOCK1")))
        row("F6: the transaction level is back to 0 after both end", tag(out, "DEPTH") == ["0"], repr(tag(out, "DEPTH")))

        say("\n--- G. SDTxn --------------------------------------------------------------------------------------------------")
        reset()
        fno2 = lib.SDOpen(b"zzcl")
        row("G0: the file is open", fno2 >= 1, str(fno2))

        def api_write(i, v):
            text(lib.SDReadu(fno2, i, 0, ctypes.byref(ctypes.c_int())))
            lib.SDWrite(fno2, i, v)

        lib.SDTxn(1)
        api_write(b"p1", b"parent")
        lib.SDTxn(1)
        api_write(b"c1", b"child")
        lib.SDTxn(4)
        row("G1: SDTxn(4), a non-durable commit of the nested transaction, leaves STATUS 0 and the session usable", lib.SDStatus() == 0,
            str(lib.SDStatus()))
        lib.SDTxn(3)
        d = disk()
        row("G2: SDTxn(3), the parent aborted: neither record reached the disk", d.get("p1") == "-" and d.get("c1") == "-", repr(d))
        lib.SDTxn(1)
        api_write(b"p1", b"parent")
        lib.SDTxn(1)
        api_write(b"c1", b"child")
        lib.SDTxn(2)
        lib.SDTxn(3)
        d = disk()
        row("G3: CONTROL, SDTxn(2) a durable commit of the child: c1 survives the parent's abort, p1 does not",
            d.get("c1") == "child" and d.get("p1") == "-", repr(d))
        lib.SDTxn(1)
        api_write(b"p1", b"parent")
        lib.SDTxn(2)
        d = disk()
        row("G4: a top-level SDTxn(2) writes: p1 on disk", d.get("p1") == "parent", repr(d))
        lib.SDTxn(2)
        e2 = err()
        row("G5: a commit with no transaction is refused, with a message, and the session goes on",
            lib.SDStatus() != 0 or b"Transaction mode" in e2, repr((lib.SDStatus(), e2)))
        lib.SDTxn(7)
        e2 = err()
        row("G5: mode 7 is refused the same way", b"Transaction mode" in e2, repr(e2))
        row("G5: CONTROL: after the refusals the session still answers", call("SDSystem", 1012) == rev, "")

        say("\n--- H. SDEvaluate and SDEvalConv ------------------------------------------------------------------------------")
        IM = b"\xff"
        flds = rec1.split(FM)
        day = (datetime.date(2026, 10, 15) - datetime.date(1967, 12, 31)).days
        dfno = lib.SDOpen(b"DICT zzcl")
        row("H0: the dictionary opens through the API (SDOpen of DICT zzcl)", dfno >= 1, str(dfno))
        want_item = text(lib.SDRead(dfno, b"DOUBLE", ctypes.byref(ctypes.c_int())))
        for spelling in (b"dict zzcl", b"Dict zzcl", b"dIcT zzcl", b"dict  zzcl"):
            lo = lib.SDOpen(spelling)
            got_item = text(lib.SDRead(lo, b"DOUBLE", ctypes.byref(ctypes.c_int()))) if lo >= 1 else None
            row("H0a: SDOpen of %r opens the dictionary of zzcl (a file number, and the item DOUBLE reads back as through DICT zzcl)" % s(spelling),
                lo >= 1 and want_item is not None and got_item == want_item and len(want_item.split(FM)) == 6, "fno=%s item=%r want=%r err=%s" % (lo, got_item, want_item, s(err())))
        no_such = lib.SDOpen(b"dict nosuchfile")
        row("H0b: SDOpen of dict and a file that is not there gives 0, no file number", no_such == 0, "fno=%s err=%s" % (no_such, s(err())))
        plainf = lib.SDOpen(b"zzcl")
        plain_item = text(lib.SDRead(plainf, b"DOUBLE", ctypes.byref(ctypes.c_int()))) if plainf >= 1 else None
        row("H0c: CONTROL: the DATA file zzcl opened by its plain name does not hold the dictionary item DOUBLE",
            plainf >= 1 and plain_item in (None, b""), "fno=%s item=%r" % (plainf, plain_item))
        no_dict = lib.SDOpen(b"dictzzcl")
        row("H0d: CONTROL: 'dictzzcl' (no space) is a plain file name, not a dictionary open: gives 0", no_dict == 0, "fno=%s" % no_dict)

        def ev(name, data=rec1, id_=b"r1", fn="SDEvaluate", f=None):
            return call(fn, dfno if f is None else f, name, data, id_)

        row("H1: SDEvaluate of a D item (NAME) is the record's field 1", ev(b"NAME") == flds[0], s(ev(b"NAME")))
        row("H1: ... the data given is what is evaluated, not the stored record: other data, other answer",
            ev(b"NAME", b"Other" + FM + b"1") == b"Other", s(ev(b"NAME", b"Other" + FM + b"1")))
        row("H2: an I-type (QTY * 2) is evaluated, though the dictionary record holds no object code", ev(b"DOUBLE") == str(int(flds[1]) * 2).encode(),
            s(ev(b"DOUBLE")))
        drec = text(lib.SDRead(dfno, b"DOUBLE", ctypes.byref(ctypes.c_int())))
        row("H2: ... and the dictionary was NOT written to by the evaluation (still its six fields, no object code in field 16)",
            drec is not None and len(drec.split(FM)) == 6, s(drec))
        row("H3: an I-type that is @ID answers the id given", ev(b"IDCOPY") == b"r1" and ev(b"IDCOPY", id_=b"zz9") == b"zz9", s(ev(b"IDCOPY")))
        row("H3: ... and the null id gives the null string", ev(b"IDCOPY", id_=b"") == b"", s(ev(b"IDCOPY", id_=b"")))
        row("H5: several names (value marks) give the answers joined by item marks (character 255)",
            ev(b"NAME" + VM + b"QTY") == flds[0] + IM + flds[1], s(ev(b"NAME" + VM + b"QTY")))
        row("H6: SDEvaluate applies NO conversion: the I-type UPNAME (conversion MCU) is Widget", ev(b"UPNAME") == b"Widget", s(ev(b"UPNAME")))
        row("H6: SDEvalConv applies it: WIDGET", ev(b"UPNAME", fn="SDEvalConv") == b"WIDGET", s(ev(b"UPNAME", fn="SDEvalConv")))
        row("H6: SDEvalConv of an item with no conversion is the plain value (NAME)", ev(b"NAME", fn="SDEvalConv") == flds[0], "")
        dated = rec1 + FM + str(day).encode()
        row("H7: a date item: SDEvaluate gives the day number, SDEvalConv the date its D4/ conversion makes",
            ev(b"WHEN", dated) == str(day).encode() and ev(b"WHEN", dated, fn="SDEvalConv") == b"10/15/2026",
            s(ev(b"WHEN", dated)) + " / " + s(ev(b"WHEN", dated, fn="SDEvalConv")))
        row("H8: a multivalued item: SDEvaluate keeps the values, SDEvalConv converts each (MCU: RED and BLUE)",
            ev(b"TAGU") == b"red" + VM + b"blue" and ev(b"TAGU", fn="SDEvalConv") == b"RED" + VM + b"BLUE",
            s(ev(b"TAGU")) + " / " + s(ev(b"TAGU", fn="SDEvalConv")))
        row("H8: several names with a conversion: NAME is left, UPNAME converted",
            ev(b"NAME" + VM + b"UPNAME", fn="SDEvalConv") == flds[0] + IM + b"WIDGET", s(ev(b"NAME" + VM + b"UPNAME", fn="SDEvalConv")))
        row("H9: a name in lower case finds the item (a dictionary folds case)", ev(b"double") == ev(b"DOUBLE") and ev(b"double") != b"", s(ev(b"double")))
        row("H10: an item that is not in the dictionary gives nothing, and no error text about types or compiling",
            ev(b"NOSUCH") == b"" and b"defines data" not in err() and b"compiled" not in err(), s(err()))
        row("H11: a phrase (type PH) defines no data: nothing, and the error says so", ev(b"PH1") == b"" and b"defines data" in err(), s(err()))
        row("H11b: an A item is not evaluated (the A and S types are gone in Solo too): nothing, and the error says it defines no data",
            ev(b"ANAME") == b"" and b"ANAME" in err() and b"defines data" in err() and ev(b"ATRIPLE") == b"" and b"ATRIPLE" in err() and b"defines data" in err(), s(err()))
        row("H12: an I-type that will not compile gives nothing, and the error says it cannot be compiled",
            ev(b"BADI") == b"" and b"cannot be compiled" in err(), s(err()))
        row("H13: a file number that was never opened is refused with the file number message", ev(b"NAME", f=99) == b"" and b"file number" in err().lower(), s(err()))
        idb = call("SDGetVar", b"@ID")
        ev(b"IDCOPY", id_=b"r3")
        row("H14: CONTROL: @ID on the server is what it was before an evaluation that set it (the environment is put back)",
            call("SDGetVar", b"@ID") == idb, s(idb) + " -> " + s(call("SDGetVar", b"@ID")))
        row("H15: CONTROL: after the refusals the session still answers", ev(b"NAME") == flds[0], "")

        say("\n--- I. SDIConv, SDOConv, SDIConvs and SDOConvs ----------------------------------------------------------------")
        d1 = str(day).encode()
        d2 = str(day + 1).encode()
        row("I1: SDOConv of the day number with D4/ is the date, and the status is 0",
            call("SDOConv", d1, b"D4/") == b"10/15/2026" and lib.SDStatus() == 0, s(call("SDOConv", d1, b"D4/")))
        row("I2: SDIConv of that date with D4/ is the day number, and the status is 0",
            call("SDIConv", b"10/15/2026", b"D4/") == d1 and lib.SDStatus() == 0, s(call("SDIConv", b"10/15/2026", b"D4/")))
        r = call("SDIConv", b"13/45/2026", b"D4/")
        bad_status = lib.SDStatus()
        row("I3: an impossible date gives the null string and a NON-ZERO status, the conversion's own", r == b"" and bad_status != 0,
            "result %s status %d" % (s(r), bad_status))
        call("SDIConv", b"10/15/2026", b"D4/")
        row("I3: CONTROL: the next successful conversion leaves the status 0 again (it is per call, not left over)", lib.SDStatus() == 0, str(lib.SDStatus()))
        two = d1 + VM + d2
        row("I4: SDOConvs converts each value of a dynamic array in turn",
            call("SDOConvs", two, b"D4/") == b"10/15/2026" + VM + b"10/16/2026", s(call("SDOConvs", two, b"D4/")))
        row("I4: ... each field the same way", call("SDOConvs", d1 + FM + d2, b"D4/") == b"10/15/2026" + FM + b"10/16/2026", "")
        row("I4: CONTROL: SDOConv of the same array does not (it treats it as one string), so the plural is not the singular",
            call("SDOConv", two, b"D4/") != b"10/15/2026" + VM + b"10/16/2026", s(call("SDOConv", two, b"D4/")))
        row("I5: SDIConvs converts each value of a dynamic array of dates", call("SDIConvs", b"10/15/2026" + VM + b"10/16/2026", b"D4/") == two,
            s(call("SDIConvs", b"10/15/2026" + VM + b"10/16/2026", b"D4/")))
        row("I6: other codes: MCU upper-cases, MD2 turns 12.34 into 1234",
            call("SDOConv", b"widget", b"MCU") == b"WIDGET" and call("SDIConv", b"12.34", b"MD2") == b"1234",
            s(call("SDOConv", b"widget", b"MCU")) + " / " + s(call("SDIConv", b"12.34", b"MD2")))
        call("SDIConv", b"x", b"ZZ")
        row("I7: a code that does not exist leaves a non-zero status", lib.SDStatus() != 0, str(lib.SDStatus()))
        row("I8: null data is converted to the null string", call("SDOConv", b"", b"D4/") == b"", s(call("SDOConv", b"", b"D4/")))
        row("I9: CONTROL: the session still answers", call("SDSystem", 1012) == rev, "")

        say("\n--- J. sessions: more than four, one waiting for input while another comes and goes, a failed connect, SDRecordlocked ---")
        main_idx = lib.SDGetSession()
        idxs = [main_idx]
        okc = []
        for _ in range(5):
            r = connect()
            okc.append(r)
            if r == 1:
                idxs.append(lib.SDGetSession())
        row("J1: six sessions open at once, each with an index of its own (sheet 134: the client held four)",
            okc == [1] * 5 and len(set(idxs)) == 6, "connects %r, indexes %r, error %s" % (okc, idxs, s(err())))
        answers = 0
        for i in idxs:
            if lib.SDSetSession(i) and call("SDSystem", 1012) == rev:
                answers += 1
        row("J1: ... and each answers when it is selected", answers == len(idxs), "%d of %d" % (answers, len(idxs)))
        for i in idxs[1:]:
            lib.SDSetSession(i)
            lib.SDDisconnect()
        row("J1: CONTROL: the first session is still there and answers after the five others were disconnected",
            lib.SDSetSession(main_idx) == 1 and call("SDSystem", 1012) == rev, "")

        perr = ctypes.c_int(-1)
        text(lib.SDExecute(b"RUN bp zzprmp", ctypes.byref(perr)))
        prompted = perr.value
        r = connect()
        lib.SDDisconnect()
        lib.SDSetSession(main_idx)
        rerr = ctypes.c_int(-1)
        out2 = text(lib.SDRespond(b"hello", ctypes.byref(rerr)))
        row("J2: a session waiting for input (EXECUTING) is not harmed when another one connects and disconnects (sheet 281): the answer "
            "reaches the command and its output comes back", prompted == 5 and r == 1 and out2 is not None and b"GOT[hello]" in out2
            and rerr.value == 0, "prompt status %d, second connect %d, reply %s, status %d" % (prompted, r, s(out2), rerr.value))
        row("J2: CONTROL: the session is an ordinary one again afterwards", call("SDSystem", 1012) == rev, "")

        r = lib.SDConnect(b"127.0.0.1", 1, b"nobody", b"x", b"sduser")
        failed_error = err()
        row("J3: a connect to a port nothing listens on fails, says why, and the session it started from can be selected and used again",
            r == 0 and failed_error != b"" and lib.SDSetSession(main_idx) == 1 and call("SDSystem", 1012) == rev,
            "result %d, error %s" % (r, s(failed_error)))

        rl = lib.SDRecordlocked
        lf = lib.SDOpen(b"zzcl")
        e0 = ctypes.byref(ctypes.c_int())
        s_none = rl(lf, b"r1")
        text(lib.SDReadu(lf, b"r1", 0, e0))
        s_mine_u = rl(lf, b"r1")
        lib.SDRelease(lf, b"r1")
        s_rel = rl(lf, b"r1")
        text(lib.SDReadl(lf, b"r1", 0, e0))
        s_mine_l = rl(lf, b"r1")
        lib.SDRelease(lf, b"r1")
        row("J4: SDRecordlocked: 0 when nothing is held, 2 for this session's update lock, 0 after SDRelease, 1 for its read lock",
            (s_none, s_mine_u, s_rel, s_mine_l) == (0, 2, 0, 1), repr((s_none, s_mine_u, s_rel, s_mine_l)))
        connect()
        idx_b = lib.SDGetSession()
        fb = lib.SDOpen(b"zzcl")
        text(lib.SDReadu(fb, b"r1", 0, e0))
        lib.SDSetSession(main_idx)
        s_other = rl(lf, b"r1")
        lib.SDSetSession(idx_b)
        lib.SDRelease(fb, b"r1")
        lib.SDDisconnect()
        lib.SDSetSession(main_idx)
        s_after = rl(lf, b"r1")
        row("J4: a lock held by ANOTHER session shows as -2 (update) to this one, and 0 once it is released", (s_other, s_after) == (-2, 0),
            repr((s_other, s_after)))
        bad_fno = rl(99, b"r1")
        row("J4: a file number that was never opened gives 0 and says so (no abort, no crash)", bad_fno == 0 and b"file number" in err().lower(),
            "%d, %s" % (bad_fno, s(err())))

        # J5: Python ignores SIGPIPE, so the test is in a child with the signal at its default action.  Its server is the one the
        # activator started after the child began; this suite kills it, then lets the child send.
        n0 = ACT.count()
        cout, crc = [], None
        cp = subprocess.Popen([sys.executable, "-I", "-c", PIPE_CHILD, LIBPATH, str(ACT.port), BOX], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ))
        killer = threading.Timer(60, cp.kill)
        killer.start()
        try:
            first = cp.stdout.readline().strip()
            cout.append(first)
            if first == "CONNECTED":
                victims = [p for p in ACT.since(n0) if p.poll() is None]
                for p in victims:
                    Activator.kill(p)
                cout.append("KILLED %d" % len(victims))
                cp.stdin.write("go\n")
                cp.stdin.flush()
            rest, errs = cp.communicate(timeout=50)
            cout += rest.split()
            crc = cp.returncode
            if crc != 0:
                cout += ["STDERR:", errs.strip()[-300:]]
        except (subprocess.TimeoutExpired, OSError, ValueError) as e:
            cout.append("TIMEOUT/ERROR %s" % e)
        finally:
            killer.cancel()
        row("J5: with SIGPIPE at its default action, a request to a server that was killed fails (nothing back) and the program lives "
            "to disconnect: the write is a failed write, not a signal (over TLS, Solo's only sign-on)",
            "KILLED 1" in " ".join(cout) and "SURVIVED" in cout and "DISCONNECTED" in cout and "EMPTY" in cout and crc == 0,
            "output %r, exit %r" % (cout, crc))

        say("\n--- L. SDDcount and SDChange against SD's own DCOUNT() and CHANGE() ------------------------------------------")
        sout = plain(["RUN bp zzstr"])
        for t, src_, dl_ in (("D1", b"a,b,c", b","), ("D2", b"a::b::c::d", b"::"), ("D3", b"aaaa", b"aa"), ("D4", b"a,b", b",,"),
                             ("D5", b"", b","), ("D6", b"ab--cd--", b"--")):
            want = (tag(sout, t) or [None])[0]
            got = lib.SDDcount(src_, dl_)
            row("L1: SDDcount(%s, %s) is what DCOUNT() gives (%s)%s" % (s(src_), s(dl_), want, "  <- a multi-character delimiter (sheet 260)" if len(dl_) > 1 else ""),
                want is not None and str(got) == want, "got %d" % got)
        row("L1: no delimiter gives 0, as it always did", lib.SDDcount(b"abc", b"") == 0, "")
        for t, args_ in (("C1", (b"aaaa", b"aa", b"b", 0, 0)), ("C2", (b"aaa", b"aa", b"b", 0, 0)), ("C3", (b"abababa", b"aba", b"X", 0, 0)),
                         ("C4", (b"abcabcabcabc", b"abc", b"Z", 2, 2)), ("C5", (b"hello", b"l", b"", 0, 0)), ("C6", (b"hello", b"xyz", b"Q", 0, 0)),
                         ("C7", (b"xx--xx--xx", b"--", b"<>", 0, 0)), ("C8", (b"aXbXc", b"X", b"YY", 1, 2))):
            want = (tag(sout, t) or [None])[0]
            got = text(lib.SDChange(*args_))
            row("L2: SDChange%s is what CHANGE() gives (%s)" % (repr(args_).replace("b'", "'"), want),
                want is not None and got is not None and got.decode("latin-1") == want, "got %s" % s(got))

        say("\n--- U. SDChecksum against SD's own CHECKSUM() and against the algorithm written out here -----------------------")

        def ref_checksum(b):
            acc = 0
            for ch in b:
                v = ch - 256 if ch > 127 else ch
                acc = ((acc << 1) | (acc >> 31)) & 0xFFFFFFFF
                acc ^= v & 0xFFFFFFFF
            return acc - (1 << 32) if acc >= (1 << 31) else acc

        fn = lib.SDChecksum
        fn.argtypes = [ctypes.c_char_p]
        fn.restype = ctypes.c_int
        uout = plain(["RUN bp zzsum"])
        ucases = (("U1", b"ABCDE"), ("U2", b""), ("U3", b"a"), ("U4", b"hello world"), ("U5", b"a\xc8z"), ("U6", b"\xff"),
                  ("U7", b"\x80\x80"), ("U8", b"0123456789" * 1000), ("U9", b"ab" + VM + b"cd" + FM + b"e"),
                  ("UA", b"abcdefghijklmnopqrstuvwxyz0123456789"))
        seen = set()
        for t, data in ucases:
            want = (tag(uout, t) or [None])[0]
            got = fn(data)
            refv = ref_checksum(data)
            seen.add(got)
            row("%s: SDChecksum(%s) is %s, what CHECKSUM() gives" % (t, s(data)[:30], want),
                want is not None and str(got) == want and got == refv, "client %s, server %s, written out here %s" % (got, want, refv))
        row("U11: CONTROL: ten different strings give more than five different values (it is not a constant)", len(seen) > 5, "values %s" % sorted(map(str, seen)))
        row("U12: the null string is 0", fn(b"") == 0, "")
        cp = subprocess.run([sys.executable, "-I", "-c",
                             "import ctypes, sys\nlib = ctypes.CDLL(sys.argv[1])\nlib.SDChecksum.argtypes = [ctypes.c_char_p]\n"
                             "print('CONNECTED', lib.SDConnected())\nprint('SUM', lib.SDChecksum(b'ABCDE'))\n", LIBPATH],
                            capture_output=True, text=True, timeout=30)
        row("U13: needs no connection: a process that never connected (SDConnected() is 0) gets the same value",
            ("CONNECTED 0" in cp.stdout) and ("SUM %d" % ref_checksum(b"ABCDE")) in cp.stdout, "output %r %r" % (cp.stdout, cp.stderr[-200:]))

        say("\n--- M. SDLogto (Solo has one account: the LOGTO is to the account the session is in) ---------------------------")
        lg = lib.SDLogto(b"sduser")
        row("M1: SDLogto to sduser returns true (sheet 272: it always returned false) and the session is in it (@WHO)",
            lg == 1 and call("SDGetVar", b"@WHO") == b"sduser", "%r, %s, error %s" % (lg, s(call("SDGetVar", b"@WHO")), s(err())))
        r = lib.SDLogto(b"nosuchaccountzz")
        row("M2: SDLogto to an account that is not there returns false, says why, and the session stays where it was",
            r == 0 and err() != b"" and call("SDGetVar", b"@WHO") == b"sduser", "result %d, error %s, @WHO %s" % (r, s(err()), s(call("SDGetVar", b"@WHO"))))
        pth2 = call("SDGetVar", b"@PATH")
        row("M2b: ... and @PATH after the refused LOGTO is still the account's directory (11 Nov 26: the first run showed every later SDOpen "
            "and SDOpenSeq by VOC name refused after M2; apisrvr's revert.to.old.account goes back to the old directory but leaves "
            "account.path naming the account that was refused - SD Core's apisrvr has the same lines)",
            pth2 is not None and os.path.realpath(pth2.decode("latin-1")) == os.path.realpath(ACCT), s(pth2))
        row("M3: CONTROL: back to sduser it returns true again (as SD Core's M3 does), and the session answers",
            lib.SDLogto(b"sduser") == 1 and call("SDGetVar", b"@WHO") == b"sduser" and call("SDSystem", 1012) == rev, s(err()))
        p3 = call("SDGetVar", b"@PATH")
        row("M3: ... and @PATH is the account's directory again", p3 is not None and os.path.realpath(p3.decode("latin-1")) == os.path.realpath(ACCT), s(p3))

        say("\n--- P. sequential files (sheet 441): SDOpenSeq, SDReadSeq, SDReadBlk, SDWriteSeq, SDWriteBlk, SDSeek, SDWeofSeq ---")
        disk_dir = os.path.join(ACCT, "zzdir")

        def ondisk(name):
            try:
                with open(os.path.join(disk_dir, name), "rb") as fh:
                    return fh.read()
            except OSError:
                return None

        rs_err = ctypes.c_int()
        rb_n = ctypes.c_int()

        def rseq(f):
            t = text(lib.SDReadSeq(f, ctypes.byref(rs_err)))
            return t, rs_err.value

        def rblk(f, n):
            ptr = lib.SDReadBlk(f, n, ctypes.byref(rb_n))
            data = ctypes.string_at(ptr, rb_n.value) if ptr else b""
            if ptr:
                lib.SDFree(ctypes.c_void_p(ptr))
            return data, rb_n.value

        sf = lib.SDOpenSeq(b"zzdir", b"lines", 512)
        row("P1: SDOpenSeq of an item of a directory file in overwrite mode gives a file number of its own, above SDOpen's", sf > 10000, "%d, %s" % (sf, s(err())))
        for ln in (b"alpha", b"beta", b"gamma"):
            lib.SDWriteSeq(sf, ln)
        lib.SDClose(sf)
        row("P1: three SDWriteSeq lines are on the disk, each with its terminator, once the file is closed (read from the disk)",
            ondisk("lines") == b"alpha\nbeta\ngamma\n", repr(ondisk("lines")))
        sf = lib.SDOpenSeq(b"zzdir", b"lines", 0)
        got = [rseq(sf) for _ in range(4)]
        row("P2: SDReadSeq gives the three lines without their terminators and then the empty string with the ELSE answer (2) at the end",
            got == [(b"alpha", 0), (b"beta", 0), (b"gamma", 0), (b"", 2)], repr(got))
        lib.SDSeek(sf, 6, 0)
        b1 = rblk(sf, 4)
        lib.SDSeek(sf, -6, 2)
        b2 = rblk(sf, 10)
        lib.SDSeek(sf, 0, 0)
        lib.SDSeek(sf, 6, 1)
        b3 = rblk(sf, 4)
        b4 = rblk(sf, 100)
        row("P3: SDSeek from the start, from the end, from here, then SDReadBlk by count, and nothing at the end",
            (b1, b2, b3) == ((b"beta", 4), (b"gamma\n", 6), (b"beta", 4)) and b4 == (b"\ngamma\n", 7) and rblk(sf, 5) == (b"", 0),
            repr((b1, b2, b3, b4)))
        lib.SDClose(sf)

        sf = lib.SDOpenSeq(b"zzdir", b"bin", 512)
        binary = b"\x00\x01\xfe\xff\n\x00z"
        lib.SDWriteBlk(sf, binary, len(binary))
        lib.SDClose(sf)
        sf = lib.SDOpenSeq(b"zzdir", b"bin", 16)
        back = rblk(sf, 100)
        lib.SDClose(sf)
        row("P4: SDWriteBlk writes bytes exactly as given, zeros and high bytes included, and SDReadBlk returns them by its count",
            ondisk("bin") == binary and back == (binary, len(binary)), "disk %r, back %r" % (ondisk("bin"), back))

        sf = lib.SDOpenSeq(b"zzdir", b"lines", 256)
        lib.SDWriteSeq(sf, b"delta")
        lib.SDClose(sf)
        row("P5: append mode (256) adds to what is there", ondisk("lines") == b"alpha\nbeta\ngamma\ndelta\n", repr(ondisk("lines")))
        sf = lib.SDOpenSeq(b"zzdir", b"lines", 16)
        lib.SDWriteSeq(sf, b"not allowed")
        lib.SDClose(sf)
        row("P5: read only (16) cannot be written: the file is as it was", ondisk("lines") == b"alpha\nbeta\ngamma\ndelta\n", repr(ondisk("lines")))
        sf = lib.SDOpenSeq(b"zzdir", b"lines", 0)
        lib.SDSeek(sf, 6, 0)
        lib.SDWeofSeq(sf)
        lib.SDClose(sf)
        row("P5: SDWeofSeq cuts the file off at the position (6: after alpha)", ondisk("lines") == b"alpha\n", repr(ondisk("lines")))
        sf = lib.SDOpenSeq(b"zzdir", b"lines", 512)
        lib.SDClose(sf)
        row("P5: overwrite mode (512) empties the file on opening it", ondisk("lines") == b"", repr(ondisk("lines")))

        sf = lib.SDOpenSeq(b"zzdir", b"flush", 512 + 1024)
        lib.SDWriteSeq(sf, b"at once")
        flushed = ondisk("flush")
        lib.SDClose(sf)
        sf = lib.SDOpenSeq(b"zzdir", b"flush2", 512)
        lib.SDWriteSeq(sf, b"later")
        held_back = ondisk("flush2")
        lib.SDClose(sf)
        row("P6: with 1024 (unbuffered) a line is on the disk before the file is closed; the CONTROL, the same without it, has nothing there "
            "until the close", flushed == b"at once\n" and held_back in (b"", None) and ondisk("flush2") == b"later\n",
            repr((flushed, held_back, ondisk("flush2"))))

        row("P7: a file number that was never given is refused with the file number message, for each of the functions",
            rseq(10999) == (b"", 3) and b"file number" in err().lower() and rblk(10999, 5) == (b"", 0)
            and (lib.SDWriteSeq(10999, b"x"), b"file number" in err().lower())[1] and (lib.SDSeek(10999, 0, 0), b"file number" in err().lower())[1],
            s(err()))
        sf = lib.SDOpenSeq(b"zzdir", b"lines", 0)
        lib.SDClose(sf)
        row("P7: after SDClose the number is no longer good", rseq(sf)[1] == 3, repr(rseq(sf)))
        row("P7: an item in a file that is not there gives 0 and a message, and so does a null file name",
            lib.SDOpenSeq(b"nosuchdirfile", b"x", 0) == 0 and lib.SDOpenSeq(b"", b"", 0) == 0 and b"name" in err().lower(), s(err()))

        pf = lib.SDOpenSeq(b"inside.txt", b"", 512)
        lib.SDWriteSeq(pf, b"in the account")
        lib.SDClose(pf)
        try:
            with open(os.path.join(ACCT, "inside.txt"), "rb") as fh:
                inside = fh.read()
        except OSError:
            inside = None
        row("P8: THE GATE, by pathname: a file inside the account's own directory can be opened and written with the OS switch off",
            pf > 10000 and inside == b"in the account\n", "%d, %r, %s" % (pf, inside, s(err())))
        before = open("/etc/hostname", "rb").read()
        refused = [lib.SDOpenSeq(p, b"", 16) for p in (b"/etc/hostname", b"../zzsibling/inside.txt", b"sub/../../zzsibling/x", b"/tmp/zzqms-seq-out")]
        e_out = err()
        w = lib.SDOpenSeq(b"/tmp/zzqms-seq-out", b"", 512)
        row("P8: ... and a pathname OUTSIDE it is refused with the OS switch off: /etc/hostname, a path beside the account, a path that "
            "climbs out, a new file in /tmp - none gets a number, the message says it may not be opened, and nothing was made",
            refused == [0, 0, 0, 0] and w == 0 and b"may open" in e_out and not os.path.exists("/tmp/zzqms-seq-out")
            and open("/etc/hostname", "rb").read() == before, "%r %d %s" % (refused, w, s(e_out)))

        sa = lib.SDGetSession()
        first = lib.SDOpenSeq(b"zzdir", b"held", 512)
        connect()
        sb = lib.SDGetSession()
        second = lib.SDOpenSeq(b"zzdir", b"held", 2)
        sec_status = lib.SDStatus()
        lib.SDSetSession(sa)
        lib.SDClose(first)
        lib.SDSetSession(sb)
        third = lib.SDOpenSeq(b"zzdir", b"held", 2)
        lib.SDDisconnect()
        lib.SDSetSession(sa)
        row("P9: a file another session has open is refused to a second open with 2 (give up), and can be opened once the first has closed it",
            first > 10000 and second == 0 and third > 10000, "first %d, second %d (status %d), third %d" % (first, second, sec_status, third))

        sa = lib.SDGetSession()
        held_a = lib.SDOpenSeq(b"zzdir", b"absent16", 16)
        connect()
        sb = lib.SDGetSession()
        while_open = lib.SDOpenSeq(b"zzdir", b"absent16", 512 + 2)
        while_status = lib.SDStatus()
        lib.SDSetSession(sa)
        lib.SDClose(held_a)
        lib.SDSetSession(sb)
        after_close = lib.SDOpenSeq(b"zzdir", b"absent16", 512 + 2)
        if after_close > 10000:
            lib.SDClose(after_close)
        lib.SDDisconnect()
        lib.SDSetSession(sa)
        row("P9b: an item that is not there: the open is given a file number (read-only), the name is held by that open, and once it is "
            "closed another session can make the item", held_a > 10000 and while_open == 0 and after_close > 10000,
            "A: %d; B while A holds it: %d (status %d); B after A closed it: %d" % (held_a, while_open, while_status, after_close))

        say("\n--- Q. WRITE ... CREATING.SEQKEY, FILEINFO(1031), CONFIGURE.FILE NEXT, SDWriteSeqKey and SDWriteuSeqKey ------------------")
        r1 = plain(["RUN bp zzsk"])
        row("Q1: three writes with CREATING.SEQKEY (two WRITE, one WRITEU) on a new hashed file are given 1, 2 and 3", tag(r1, "IDS") == ["1|2|3"],
            repr(r1[-6:]))
        row("Q1: ... the WRITEU keeps its update lock (RECORDLOCKED 2), the WRITE released its own (0), and the record is read back by its id",
            tag(r1, "LOCK3") == ["2"] and tag(r1, "LOCK2") == ["0"] and tag(r1, "REC2") == ["second"], repr((tag(r1, "LOCK3"), tag(r1, "LOCK2"), tag(r1, "REC2"))))
        row("Q1: FILEINFO(file, 1031) is the id of the last record written with it: 3", tag(r1, "LAST") == ["3"], repr(tag(r1, "LAST")))
        plain(["CONFIGURE.FILE zzsq NEXT 100"])
        r2 = plain(["RUN bp zzsk"])
        row("Q2: CONFIGURE.FILE NEXT 100 sets the counter: the next three are 100, 101 and 102 (and 1031 says 102)",
            tag(r2, "IDS") == ["100|101|102"] and tag(r2, "LAST") == ["102"], repr((tag(r2, "IDS"), tag(r2, "LAST"))))
        qq = plain(["CONFIGURE.FILE zzsq NEXT QUERY"])
        row("Q2: NEXT QUERY says what the next id will be (103)", any("next sequential record id is 103" in ln for ln in qq), repr(qq[-3:]))
        rt = plain(["RUN bp zzskt"])
        row("Q3: in a transaction the id is taken at the WRITE and the record is there after the commit (103)", tag(rt, "TXN") == ["103=in txn"],
            repr(tag(rt, "TXN")))
        rd = plain(["RUN bp zzskd"])
        row("Q4: a DIRECTORY file is refused (status 3005, not a dynamic file) and the id variable is left null",
            any(re.fullmatch(r"REFUSED\[-?3005\]", ln) for ln in rd) and tag(rd, "AFTER") == [""], repr(rd[-4:]))
        # 11 Nov 2026, the merge with the SDNet file administration carry: requests 68 and 69 (SDWriteSeqKey, SDWriteuSeqKey) are served by a Solo
        # server ONLY to a session signed in with the GLOBAL password (the owner's rule; the gate before apisrvr's dispatch, message 14964, an audit
        # line 'api refused request=N global=off').  This session signed in with the ACCOUNT password, so the rows below hold the refusal: no id, the
        # audit line, the counter and the files untouched.  The served path (the ids, the locks) is sandbox-fileadmin-solo.py's Q3 / Q4, by the global session.
        def refused_68_69(off, wanted):
            new = audit_new(off)
            got = re.findall(r"api refused request=(6[89]) global=off user=" + ACCOUNT + r"$", new or "", re.M)
            return new is not None and got == wanted, got
        qf = lib.SDOpen(b"zzsq")
        aoff = audit_off()
        k1 = text(lib.SDWriteSeqKey(qf, b"api one"))
        k2 = text(lib.SDWriteuSeqKey(qf, b"api two"))
        aok, agot = refused_68_69(aoff, ["68", "69"])
        row("Q5: SDWriteSeqKey and SDWriteuSeqKey from an ACCOUNT-password session are refused by the global-session gate: no id, and the audit "
            "trail gains 'api refused request=68 global=off' then 69", qf >= 1 and k1 in (b"", None) and k2 in (b"", None) and aok,
            "fno %r, ids %r, audit %r" % (qf, (k1, k2), agot))
        qdf = lib.SDOpen(b"zzdir")
        aoff = audit_off()
        kd = text(lib.SDWriteSeqKey(qdf, b"x"))
        aok, agot = refused_68_69(aoff, ["68"])
        row("Q5: on a directory file the gate refuses first (68 audited), before the hashed-file test", kd in (b"", None) and aok,
            "id %r, audit %r" % (kd, agot))
        qq = plain(["CONFIGURE.FILE zzsq NEXT QUERY"])
        row("Q5: the refused requests took no id from the counter: NEXT QUERY still says 104", any("next sequential record id is 104" in ln for ln in qq),
            repr(qq[-3:]))
        vf = lib.SDOpen(b"VOC")
        vbefore = plain(["COUNT VOC"])
        aoff = audit_off()
        vk = text(lib.SDWriteSeqKey(vf, b"X" + FM + b"written by SDWriteSeqKey")) if vf >= 1 else None
        aok, agot = refused_68_69(aoff, ["68"])
        vafter = plain(["COUNT VOC"])
        row("Q6: SDWriteSeqKey on the account's VOC from an account-password session is refused at the gate (68 audited) and nothing is written "
            "(COUNT VOC the same before and after); the VOC rule behind it (check.voc.edit) is read by test-fileadmin-solo-units.py S9",
            vf >= 1 and vk in (b"", None) and aok and vbefore == vafter and has(vafter, r"record"),
            "fno %r, id %r, audit %r, count %r -> %r" % (vf, vk, agot, vbefore[-1:], vafter[-1:]))

        say("\n--- R. threads (sheet 456): sessions, buffers and a failed connect's error, six threads in one process --------------")
        NTH = 6
        try:
            cp = subprocess.run([sys.executable, "-I", "-c", THREAD_CHILD, LIBPATH, str(NTH), rev.decode(), str(ACT.port), BOX],
                                capture_output=True, text=True, timeout=400, env=dict(os.environ))
            res_line = [ln for ln in cp.stdout.splitlines() if ln.startswith("RESULT ")]
            tres = json.loads(res_line[-1][7:]) if res_line else None
            tcrc, terr = cp.returncode, cp.stderr.strip()[-300:]
        except subprocess.TimeoutExpired:
            tres, tcrc, terr = None, None, "TIMEOUT"
        say("sandbox-qmclient-solo: thread child exit %r, result %s" % (tcrc, json.dumps(tres)[:900] if tres else None))
        if tres is None:
            for t in ("R1", "R2", "R3", "R4", "R5"):
                row("%s: the thread child gave no result (exit %r) - %s" % (t, tcrc, terr), False, "")
        else:
            ss = [x for x in tres["sessions"] if x]
            row("R1: six threads connect at the same moment: every connect succeeds and each thread is given a session index of its "
                "own and a user number of its own", len(ss) == NTH and all(x["ok"] == 1 for x in ss)
                and len({x["idx"] for x in ss}) == NTH and len({x["who"] for x in ss}) == NTH,
                repr([(x["ok"], x["idx"], x["who"]) for x in ss]))
            row("R2: each thread's current session stays its own through 100 rounds of asking while the others do the same",
                len(ss) == NTH and all(x["bad"] == 0 for x in ss), repr([x["bad"] for x in ss]))
            row("R3: each thread writes a record of its own size (3 KB to 38 KB) and reads it back 40 times at the same moment as the "
                "others: every read is exactly what it wrote", len(ss) == NTH and all(x["wrong"] == 0 for x in ss),
                repr([x["wrong"] for x in ss]))
            row("R3: ... and each thread's SDCallx of a catalogued subroutine gives it, through SDGetArg, the argument that call returned, "
                "40 times (the Callx buffers are per thread)", len(ss) == NTH and all(x.get("callx_wrong") == 0 for x in ss),
                repr([x.get("callx_wrong") for x in ss]))
            fl = tres["failed"]
            row("R4: a connect that fails keeps its error text for its own thread while another thread connects and disconnects ten times",
                fl.get("r") == 0 and fl.get("e1", "") != "" and fl.get("e2") == fl.get("e1") and fl.get("churn") == 10 and fl.get("connected") == 0,
                repr(fl))
            row("R5: CONTROL: afterwards one thread connects, asks the server's revision and disconnects as before",
                tres["control"] == [1, rev.decode()], repr(tres["control"]))
        row("R6: the thread child ended normally (exit 0, no exception in any thread, no barrier broken)",
            tres is not None and tcrc == 0 and tres.get("errors") == [], "exit %r, errors %r %s" % (tcrc, (tres or {}).get("errors"), terr))
        plain(["DELETE zzlog %s" % ("thr%d" % i) for i in range(NTH)])

        say("\n--- S. a pathname outside the account with the OS switch ON (SET.OS.ACCESS: register fields 7 and 8) ---------------")
        out_path = "/tmp/zzqms-os-out"
        nodir = "/tmp/zzqms-nodir-xyz"
        for p_ in (out_path, nodir):
            if os.path.exists(p_):
                bail("%s exists before the run; remove it (it is this suite's own scratch name)" % p_)

        def register(osx):
            """Fields 7 (SH) and 8 (OS) of sduser's register record; the rest as the install wrote it.  A session reads it at login."""
            lines = reg_orig.decode("latin-1").split("\n")
            while lines and lines[-1] == "":
                lines.pop()
            lines += [""] * (8 - len(lines))
            lines = lines[:6] + ["", "yes" if osx else ""] + lines[8:]
            put(REG, "\n".join(lines) + "\n")
            say("sandbox-qmclient-solo: register sduser -> fields 7-8 %r" % (open(REG).read().split("\n")[6:8],))

        def seq_open_out(mode):
            f_ = lib.SDOpenSeq(out_path.encode(), b"", mode + 2)
            return f_, err()

        try:
            register(False)
            ok_a = connect()
            sess_a = lib.SDGetSession()
            fa, ea = seq_open_out(512)
            row("S1: CONTROL, OS switch off: a new session is refused a pathname in /tmp - no file number, the message says it may not be "
                "opened, nothing was made", ok_a == 1 and fa == 0 and b"may open" in ea and not os.path.exists(out_path),
                "connect %r, %r, %s" % (ok_a, fa, s(ea)))
            register(True)
            ok_b = connect()
            sess_b = lib.SDGetSession()
            row("S2: the register flipped and a NEW session made: it connects and is in sduser", ok_b == 1 and sess_b != sess_a
                and call("SDGetVar", b"@WHO") == b"sduser", "%r %r %s" % (ok_b, sess_b, s(call("SDGetVar", b"@WHO"))))
            fb, eb = seq_open_out(512)
            row("S3: OS switch on: the pathname in /tmp is OPENED (a file number of the sequential range)", fb > 10000, "%r, %s" % (fb, s(eb)))
            if fb > 10000:
                lib.SDWriteSeq(fb, b"written with the OS switch on")
                lib.SDWriteSeq(fb, b"second line")
                lib.SDClose(fb)
            try:
                with open(out_path, "rb") as fh:
                    on_disk = fh.read()
            except OSError:
                on_disk = None
            row("S3: ... the two lines are on the disk in /tmp with their terminators, read back by this program, not by SD",
                on_disk == b"written with the OS switch on\nsecond line\n", repr(on_disk))
            rf = lib.SDOpenSeq(out_path.encode(), b"", 16 + 2)
            l1, st1 = rseq(rf) if rf else (None, None)
            l2, st2 = rseq(rf) if rf else (None, None)
            if rf:
                lib.SDClose(rf)
            row("S4: ... and read back through the API (read only): both lines, without their terminators",
                rf > 10000 and (l1, l2) == (b"written with the OS switch on", b"second line"), "%r %r %r" % (rf, l1, l2))
            host_line = open("/etc/hostname", "rb").read().split(b"\n")[0]
            hf = lib.SDOpenSeq(b"/etc/hostname", b"", 16)
            h1, _ = rseq(hf) if hf else (None, None)
            if hf:
                lib.SDClose(hf)
            row("S4: a file the account does not own, /etc/hostname, is opened read only and its first line is read (the P8 refusal, lifted)",
                hf > 10000 and h1 == host_line, "%r %r vs %r" % (hf, h1, host_line))
            before_h = open("/etc/hostname", "rb").read()
            (ovf, _) = cap_stderr(lambda: lib.SDOpenSeq(b"/etc/hostname", b"", 512))
            row("S5: STILL REFUSED by the operating system, not the switch: /etc/hostname (root's, mode 644) in overwrite mode gets no file "
                "number and the file is as it was", ovf == 0 and open("/etc/hostname", "rb").read() == before_h, "%r, %s" % (ovf, s(err())))
            af = lib.SDOpenSeq(b"/etc/hostname", b"", 256)
            cap_stderr(lambda: lib.SDWriteSeq(af, b"zz") if af else -1)
            wst = lib.SDStatus()
            if af:
                lib.SDClose(af)
            row("S5: ... in append mode the open is answered but the WRITE fails (a non-zero status), and the file is as it was",
                wst != 0 and open("/etc/hostname", "rb").read() == before_h, "open %r, status %r" % (af, wst))
            ndf = lib.SDOpenSeq((nodir + "/x").encode(), b"", 512)
            if ndf > 10000:
                lib.SDWriteSeq(ndf, b"made")
                lib.SDClose(ndf)
            nd_data = open(nodir + "/x", "rb").read() if os.path.exists(nodir + "/x") else None
            row("S5: the OS switch is not limited to directories that exist: a file in a new directory under /tmp is made, written and found "
                "on the disk (OPENSEQ makes the directory)", ndf > 10000 and nd_data == b"made\n", "%r, %r" % (ndf, nd_data))
            ef = lib.SDOpenSeq(b"", b"", 512)
            row("S5: STILL REFUSED: a null name - the message says a sequential file needs a name", ef == 0 and b"needs a name" in err(),
                "%r, %s" % (ef, s(err())))
            if os.path.exists(out_path):
                os.remove(out_path)
            lib.SDSetSession(sess_a)
            fa2, ea2 = seq_open_out(512)
            row("S6: the session made BEFORE the flip is still refused after it (the switches are loaded at login), nothing made",
                fa2 == 0 and b"may open" in ea2 and not os.path.exists(out_path), "%r, %s" % (fa2, s(ea2)))
            lib.SDDisconnect()
            lib.SDSetSession(sess_b)
            lib.SDDisconnect()
            register(False)
            ok_c = connect()
            fc, ec = seq_open_out(512)
            row("S7: CONTROL: with the switch off again a NEW session is refused again", ok_c == 1 and fc == 0 and b"may open" in ec
                and not os.path.exists(out_path), "%r %r, %s" % (ok_c, fc, s(ec)))
            lib.SDDisconnect()
        finally:
            with open(REG, "wb") as f:
                f.write(reg_orig)
            for p_ in (out_path, nodir + "/x"):
                if os.path.exists(p_):
                    os.remove(p_)
            if os.path.isdir(nodir):
                os.rmdir(nodir)
        lib.SDSetSession(main_idx)

        say("\n--- K. AUTOLOGOUT in an API session (sheet 474): two sessions, one given AUTOLOGOUT 1, both idle for 70 seconds ------")
        connect()
        ia = lib.SDGetSession()
        eK = ctypes.c_int()
        text(lib.SDExecute(b"AUTOLOGOUT 1", ctypes.byref(eK)))
        shown = text(lib.SDExecute(b"AUTOLOGOUT", ctypes.byref(eK)))
        connect()
        ib = lib.SDGetSession()
        shown_b = text(lib.SDExecute(b"AUTOLOGOUT", ctypes.byref(eK)))
        row("K0: AUTOLOGOUT is set by the command in one session (1 minute) and is off in the other", shown is not None and b"1 minute" in shown
            and shown_b is not None and b"disabled" in shown_b, "%s / %s" % (s(shown), s(shown_b)))
        time.sleep(70)
        box = {}

        def idle_call():
            lib.SDSetSession(ia)
            t0 = time.time()
            box["answer"] = call("SDSystem", 1012)
            box["secs"] = time.time() - t0
            box["err"] = err()

        th = threading.Thread(target=idle_call, daemon=True)
        th.start()
        th.join(30)
        row("K1: after the minute the session whose AUTOLOGOUT has run out is gone: its next request comes back at once with nothing and an error",
            not th.is_alive() and box.get("answer") in (b"", None) and box.get("err", b"") != b"",
            "answer %r after %s s, error %s" % (box.get("answer"), box.get("secs"), s(box.get("err"))))
        lib.SDSetSession(ib)
        row("K2: CONTROL: the other session, idle for the same time without AUTOLOGOUT, still answers", call("SDSystem", 1012) == rev, "")
        lib.SDDisconnect()
        lib.SDSetSession(ia)
        t0 = time.time()
        lib.SDDisconnect()
        row("K3: disconnecting the session whose server has gone returns (no SIGPIPE ended this program, no wait)", time.time() - t0 < 20,
            "%.1f s" % (time.time() - t0))
        lib.SDSetSession(main_idx)
        row("K3: CONTROL: the first session is still there", call("SDSystem", 1012) == rev, "")
        lib.SDDisconnect()

        say("\n--- T. SDCLIENT in sd.conf (sheet 571 family): every request that tests it; 0 is the control, then 1, then 2 -----------")
        say("sandbox-qmclient-solo: part T restarts the sandbox for each mode, which ends every session, so it runs after K and last")
        cap = cap_stderr

        def marks(clear=False):
            o = plain(["RUN bp zzmrk" + (" clear" if clear else "")])
            dd = {m_.group(1): m_.group(2) for m_ in (re.match(r"^M\[([a-z]+)=(.*)\]$", t) for t in o) if m_}
            return dd, (tag(o, "TC") or [None])[0]

        def phase(mode, up):
            marks(clear=True)
            for nm in ("sdcl%d" % mode, "sdclpath%d.txt" % mode):
                for base in (os.path.join(ACCT, "zzdir"), ACCT):
                    if os.path.exists(os.path.join(base, nm)):
                        os.remove(os.path.join(base, nm))
            P = "T%d-" % mode
            allow_file = mode == 0
            okc_ = connect()
            row("%s0: with SDCLIENT=%d SD is up and a NEW session connects" % (P, mode), up and okc_ == 1, "SD up %s, connect %r, %s" % (up, okc_, s(err())))
            if not (up and okc_ == 1):
                return
            row("%s1: ... and still answers SDSystem(1012) with the revision" % P, call("SDSystem", 1012) == rev, "")
            row("%s1: ... and SDGetVar(@WHO) names the account" % P, call("SDGetVar", b"@WHO") == b"sduser", "")
            fno_, e = cap(lambda: lib.SDOpen(b"zzcl"))
            row("%s2: SDOpen of a hashed file %s" % (P, "gives a file number" if allow_file else "gives 0, no file number (message 5262)"),
                (fno_ >= 1) if allow_file else (fno_ == 0), "%r, stderr %r, error %s" % (fno_, e, s(err())))
            tw, et = cap(lambda: call("SDTrans", b"zzcl", b"r1", b"NAME", b"X"))
            rw, er = cap(lambda: call("SDRTrans", b"zzcl", b"r1", b"NAME", b"X"))
            row("%s3: SDTrans and SDRTrans of a dictionary field %s" % (P, "give Widget" if allow_file else "give nothing (message 5262)"),
                (tw == b"Widget" and rw == b"Widget") if allow_file else (tw in (b"", None) and rw in (b"", None)),
                "%s %s, stderr %r %r" % (s(tw), s(rw), et, er))
            qf_, eq = cap(lambda: lib.SDOpenSeq(b"zzdir", ("sdcl%d" % mode).encode(), 512))
            if qf_ > 10000:
                lib.SDWriteSeq(qf_, b"seq")
                lib.SDClose(qf_)
            pf_, ep = cap(lambda: lib.SDOpenSeq(os.path.join(ACCT, "sdclpath%d.txt" % mode).encode(), b"", 512))
            if pf_ > 10000:
                lib.SDWriteSeq(pf_, b"path")
                lib.SDClose(pf_)
            f1 = os.path.join(ACCT, "zzdir", "sdcl%d" % mode)
            f2 = os.path.join(ACCT, "sdclpath%d.txt" % mode)
            dd1 = open(f1, "rb").read() if os.path.exists(f1) else None
            dd2 = open(f2, "rb").read() if os.path.exists(f2) else None
            if allow_file:
                row("%s4: SDOpenSeq by VOC name and by a pathname in the account both open, write, and the bytes are on the disk" % P,
                    qf_ > 10000 and pf_ > 10000 and dd1 == b"seq\n" and dd2 == b"path\n", "%r %r %r %r" % (qf_, pf_, dd1, dd2))
            else:
                row("%s4: SDOpenSeq by VOC name and by a pathname in the account both give 0 (message 5262) and NOTHING was made on the disk" % P,
                    qf_ == 0 and pf_ == 0 and dd1 is None and dd2 is None, "%r %r %r %r, error %s" % (qf_, pf_, dd1, dd2, s(err())))
                row("%s4: ... the text reaches the client (File access is disabled)" % P,
                    b"File access is disabled" in err() or "File access is disabled" in ep or "File access is disabled" in eq, "%s / %r" % (s(err()), ep))
            rounds = 1 if allow_file else 300
            try:
                xp = subprocess.run([sys.executable, "-I", "-c", EXEC_CHILD, LIBPATH, str(rounds), "RUN bp zzxmk", str(ACT.port), BOX],
                                    capture_output=True, text=True, errors="replace", timeout=300,
                                    env=dict(os.environ, GLIBC_TUNABLES="glibc.malloc.tcache_count=0"))
                xrc, xout, ex = xp.returncode, xp.stdout, xp.stderr
            except subprocess.TimeoutExpired:
                xrc, xout, ex = None, "", "TIMEOUT"
            m1, tc = marks()
            if allow_file:
                row("%s5: SDExecute runs the command: its mark is in the file" % P, m1.get("execmark") == "ran" and "FIRST err 0" in xout,
                    "%r, %r, child exit %r" % (m1, xout, xrc))
            else:
                row("%s5: SDExecute is refused - 'Command execution is disabled' on stderr, an on-error answer - and the command did NOT run "
                    "(no mark)" % P, "Command execution is disabled" in ex and "FIRST err 1" in xout and m1.get("execmark") == "-",
                    "stderr %r, stdout %r, marks %r" % (ex[:120], xout, m1))
                row("%s5: ... and 300 refused SDExecutes in a row leave the client library's heap sound: the child ends normally (exit 0, all 300 done)" % P,
                    xrc == 0 and "LOOPS 300" in xout, "exit %r, stdout %r, stderr tail %r" % (xrc, xout, ex[-160:]))
            lib.SDCallx(b"zzcmk", ctypes.c_int16(2), b"X", b"")
            text(lib.SDGetArg(2))
            _, ec = cap(lambda: lib.SDCallx(b"zzcmk", ctypes.c_int16(2), b"Y", b""))
            ra2 = text(lib.SDGetArg(2))
            lib.SDCallx(b"zzcok", ctypes.c_int16(2), b"Z", b"")
            rb = text(lib.SDGetArg(2))
            m2, _ = marks()
            if mode < 2:
                row("%s6: SDCall of an unflagged subroutine runs (only SDCLIENT=2 restricts calls): it returned its argument and left its mark" % P,
                    ra2 == b"ret:Y" and m2.get("callmark") == "ran Y", "%r %r" % (ra2, m2))
            else:
                row("%s6: SDCall of a subroutine NOT flagged $sdcall is refused (message 5264): it returned nothing and did NOT run (no mark) - "
                    "SD Core's vb.call return of 15 Oct 26, carried" % P,
                    "cannot be called from a SDClient session" in ec and ra2 in (b"", None) and m2.get("callmark") == "-",
                    "stderr %r, returned %r, marks %r" % (ec, ra2, m2))
            row("%s7: SDCall of a subroutine flagged $sdcall runs in every mode: it returned its argument and left its mark" % P,
                rb == b"ret:Z" and m2.get("okmark") == "ran Z", "%r %r" % (rb, m2))
            tconv, _ = cap(lambda: call("SDOConv", b"r1", b"Tzzcl;X;;1"))
            err_t = err()
            uconv = call("SDOConv", b"x", b"U50BB")
            err_u = err()
            sconv = call("SDOConv", b"widget", b"MCU")
            if mode == 0:
                row("%s8: SDOConv with a T conversion that reads a file is done (the answer is what OCONV gives in a session: %s)" % (P, tc),
                    tc not in (None, "") and tconv == tc.encode("latin-1"), "%s vs %r" % (s(tconv), tc))
                row("%s8: ... and a U conversion is not refused for being a conversion that calls a program" % P,
                    b"not allowed in this session" not in err_u, s(err_u))
            else:
                row("%s8: SDOConv with a T conversion that reads a file gives nothing and says it is not allowed in this session (11343)" % P,
                    tconv in (b"", None) and b"not allowed in this session" in err_t, "%s, %s" % (s(tconv), s(err_t)))
                row("%s8: ... so does a U conversion (one that calls a program)" % P,
                    uconv in (b"", None) and b"not allowed in this session" in err_u, "%s, %s" % (s(uconv), s(err_u)))
            row("%s8: CONTROL: a conversion that does neither (MCU) is done in every mode" % P, sconv == b"WIDGET", s(sconv))
            row("%s9: CONTROL: the session still answers afterwards" % P, call("SDSystem", 1012) == rev, "")
            lib.SDDisconnect()

        up = True
        try:
            phase(0, True)
            for mode in (1, 2):
                lib.SDDisconnectAll()
                up = restart("SDCLIENT=%d" % mode)
                phase(mode, up)
        finally:
            lib.SDDisconnectAll()
            up = restart()
        okz = connect()
        zf = lib.SDOpen(b"zzcl")
        row("Tz: sd.conf restored: SD is up and a new session opens a file again", up and okz == 1 and zf >= 1, "%s %r %r" % (up, okz, zf))
        lib.SDDisconnect()
    finally:
        try:
            lib.SDDisconnectAll()
        except Exception:
            pass
        ACT.stop()
        with open(REG, "wb") as f:
            f.write(reg_orig)
        plain(["DELETE.CATALOG %s LOCAL" % " ".join(CATALOGUED)] + ["DELETE.FILE %s NO.QUERY" % f for f in FIXTURE_FILES])
        for nm in list(USER_PROGS) + ["inside.txt"]:
            for d_ in (os.path.join(ACCT, "bp"), os.path.join(ACCT, "bp.out"), ACCT):
                p = os.path.join(d_, nm)
                if nm == "inside.txt" and d_ != ACCT:
                    continue
                if nm != "inside.txt" and d_ == ACCT:
                    continue
                if os.path.isfile(p):
                    os.remove(p)
        if os.path.exists(pins):
            os.remove(pins)

    say("\nsandbox-qmclient-solo: %d passed, %d failed" % (passed, failed))
    if passed + failed == 0:
        bail("no row ran - a broken test, not a pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
