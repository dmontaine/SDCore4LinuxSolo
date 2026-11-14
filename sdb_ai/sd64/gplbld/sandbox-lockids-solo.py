#!/usr/bin/env python3
#
# sandbox-lockids-solo.py - another session's text reaches GETLOCKS(), LIST.READU, PSTAT, HSM and PROFILER DISPLAY escaped, on a private SD Core Solo for Linux
# (Solo carry of SD Core's sandbox-lockids.py, S.216 gap 13).  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-lockids-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent; keep the path SHORT).  Exit 0 every
# row passed, 1 a row failed, 2 it could not run.
#
# WHERE SOLO DIFFERS FROM CORE'S SUITE.  There is one account, sduser: the holder and the waiter are ORDINARY sessions of it on pipes, signed on with the account
# password (<dir>/account.pw).  The administrator's commands run in an INTERNAL session (the one-shot $internal marker, sd-solo -internal), here started by this
# suite itself so that its output is kept as BYTES (sandbox-fromtree.py's sess decodes it, and bytes 155 and 200 are what several rows look for).  Core's
# tuirows phases are gone: every row counts.
#
# WHAT IT HOLDS (the rows are Core's, by the same names).  The holder takes READU locks in its file zzlf on PLAINID (the control) and on
#   lkok- ESC ]0;pwnlid BEL | ESC [2jclrlid DEL CSI(155) x char(200)     (the file folds case, so the table holds it in upper case)
#   LK-ctl0 / LK1   the holder's own FILEINFO(f, 1039) gives both ids, the planted one raw (a program's own locks are not escaped)
#   LK-ctl1 / LK2 / LK3   GETLOCKS() as the administrator: the control exactly; the planted id with every byte of the rule (0-31, 127, 128-159, 248-255) one '?'
#   LK4-ctl / LK4   LIST.READU WAIT as bytes: the planted lock is listed and no ESC ] 0 ; PWNLID, no ESC [ 2 J
#   LK6-ctl .. LK9  PSTAT USER n of a WAITER that EXECUTEd a DISPLAY holding control bytes, set @PSTAT to text holding them and waits for the planted id
#   GU-ctl .. GU7   GETLOCKS('', n) for user numbers nobody holds or can hold: the counters and no lock line, no fault
#   PL-ctl0 .. PL8  records PLANTED in $IPC (S<n>, H<n> while the waiter is STOPPED, F9999) read by PSTAT, HSM USER n and PROFILER DISPLAY: no raw sequence, each byte '?'
#   LK5 / LK10      the holder ends when told to; the waiter then gets the lock and ends
# The PL rows are the BASIC half of gap 13 (pstat, hsm, profiler through kernel(K$SHOW.SAFE, ...)); the LK rows the kernel half.
#
# START-HISTORY:
# 12 Nov 26 dm  New (S.216 gap 13): Core's suite of 28 Oct / 3 Nov on Solo's harness.
# END-HISTORY
import importlib.util
import os
import re
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sh = _load("sandbox_home_solo_for_lockids", "sandbox-home-solo.py")
say, bail, has = sh.say, sh.bail, sh.has
UNSAFE = set(range(0, 32)) | {127} | set(range(128, 160)) | set(range(248, 256))
COMPILED = r"^Compiled 1 program\(s\) with no errors"

PLANT = (b"lkok-" + b"\x1b]0;pwnlid\x07|" + b"\x1b[2jclrlid" + bytes([127, 155]) + b"x" + bytes([200]))

ZZLK2 = """   open 'zzlf' to f else
      crt 'ZZLK2 nofile'
      stop
   end
   open 'bp' to bpf else
      crt 'ZZLK2 nobp'
      stop
   end
   id = 'lkok-' : char(27) : ']0;pwnlid' : char(7) : '|' : char(27) : '[2jclrlid' : char(127) : char(155) : 'x' : char(200)
   readu r from f, id else null
   readu r2 from f, 'plainid' else null
   own = fileinfo(f, 1039)
   no = dcount(own, @fm)
   for i = 1 to no
      t = own<i, 2>
      out = ''
      for j = 1 to len(t)
         out := seq(t[j, 1]) : ','
      next j
      crt 'ZZOWN ' : own<i, 1> : ' ' : out
   next i
   crt 'ZZLK2 holding'
   loop
      sleep 1
      read s from bpf, 'zzlkstop2' then exit else null
   repeat
   crt 'ZZLK2 done'
end
"""

ZZGL = """$internal
   locks = getlocks('', 0)
   del locks<1>
   nl = dcount(locks, @fm)
   for i = 1 to nl
      s = locks<i>
      if index(s<1, 2>, 'zzlf', 1) then
         t = s<1, 5>
         out = ''
         for j = 1 to len(t)
            out := seq(t[j, 1]) : ','
         next j
         crt 'ZZGL ' : s<1, 4> : ' ' : out
      end
   next i
   crt 'ZZGL done'
end
"""

ZZLK3 = """   open 'zzlf' to f else
      crt 'ZZLK3 nofile'
      stop
   end
   execute 'DISPLAY zzcmd-' : char(27) : ']0;pwncmd' : char(7) : '-end'
   @pstat = 'zzps-' : char(27) : '[2jclrps' : char(155) : 'x' : char(200) : @vm : 'tail'
   id = 'lkok-' : char(27) : ']0;pwnlid' : char(7) : '|' : char(27) : '[2jclrlid' : char(127) : char(155) : 'x' : char(200)
   crt 'ZZLK3 user ' : @userno
   crt 'ZZLK3 waiting'
   readu r from f, id else null
   crt 'ZZLK3 got'
   release f, id
end
"""

PSTAT_CMD = b"zzcmd-?]0;pwncmd?-end"
PSTAT_TEXT = b"zzps-?[2jclrps?x" + bytes([200]) + b" tail"

ZZPL = """$internal
program zzpl
$include gpl.bp syscom.h
   args = trim(@sentence)
   kind = field(args, ' ', 4)
   n = field(args, ' ', 5)
   open 'bp' to bpf else
      crt 'ZZPL nobp'
      stop
   end
   esc = char(27)
   srec = '0':@vm:'0':@vm:'0'
   srec<2> = 'zzplcmd-':esc:']0;pwnplc':char(7):'-end'
   srec<3> = 'zzplprog-':esc:'[2jclrpp':@sm:'10':@tm:'7':esc:'[2jclrln'
   srec<4> = '5':@vm:'zzplfile-':esc:']0;pwnplf':char(7):@vm:'zzplid-':esc:'[2jclrpi'
   srec<5> = 'zzplacct-':esc:']0;pwnpla':char(7)
   srec<6> = 'zzplps-':esc:'[2jclrpz':char(155)
   hrec = 'zzplhsm-':esc:'[2jclrph':char(155):@vm:'9':esc:'c':@vm:'2000':@vm:'1':@vm:'2':@vm:'3':@vm:'4'
   frec = 'PROFILE':@vm:'1023':@vm:'1':@vm:'0'
   frec<2> = 'zzplev-':esc:']0;pwnpe':char(7):@vm:'zzplq-':esc:'[2jclrpq':@vm:'zzplp-':esc:'[2jclrpr':char(155):@vm:'12':@vm:'3'
   begin case
      case kind = 'SH'
         crt 'ZZPL writing ' : n
         tries = 0
         loop
            write srec to ipc.f, 'S':n
            write hrec to ipc.f, 'H':n
            read s from bpf, 'zzplstop' then exit else null
            tries += 1
         until tries > 1200
            nap 50
         repeat
         delete ipc.f, 'S':n
         delete ipc.f, 'H':n
         delete bpf, 'zzplstop'
         crt 'ZZPL done'
      case kind = 'F'
         write frec to ipc.f, 'F':n
         crt 'ZZPL planted ' : n
      case kind = 'X'
         delete ipc.f, 'F':n
         crt 'ZZPL removed ' : n
   end case
end
"""

PL_S_SAFE = [b"zzplcmd-?]0;pwnplc?-end", b"zzplacct-?]0;pwnpla?", b"zzplprog-?[2jclrpp", b"7?[2jclrln", b"zzplfile-?]0;pwnplf?", b"zzplid-?[2jclrpi",
             b"zzplps-?[2jclrpz?"]
PL_S_RAW = [b"\x1b]0;pwnplc", b"\x1b]0;pwnpla", b"\x1b[2jclrpp", b"\x1b[2jclrln", b"\x1b]0;pwnplf", b"\x1b[2jclrpi", b"\x1b[2jclrpz"]
PL_H_SAFE = [b"zzplhsm-?[2jclrph?", b"9?c"]
PL_H_RAW = [b"\x1b[2jclrph", b"\x1bc"]
PL_F_SAFE = [b"zzplev-?]0;pwnpe?", b"zzplq-?[2jclrpq", b"zzplp-?[2jclrpr?"]
PL_F_RAW = [b"\x1b]0;pwnpe", b"\x1b[2jclrpq", b"\x1b[2jclrpr"]
PL_FUSER = "9999"

ZZGU = """$internal
   hi = system(1053)
   nos = '%s':@fm:'12345':@fm:(hi + 1):@fm:'65537':@fm:'-5':@fm:hi
   for k = 1 to dcount(nos, @fm)
      l = getlocks('', nos<k>)
      t = ''
      for i = 2 to dcount(l, @fm)
         t := l<i, 4> : ','
      next i
      crt 'ZZGU ' : k : ' ' : nos<k> : ' n=' : dcount(l, @fm) : ' c=' : dcount(l<1>, @vm) : ' t=' : t
   next k
   crt 'ZZGU end'
end
"""


def row(name, ok, detail=""):
    sh.row(name, ok, detail)


def codes(s):
    if isinstance(s, bytes):
        s = s.decode("latin-1")
    s = (s or "").strip().strip(",")
    return bytes(int(x) for x in s.split(",")) if s else b""


def upper_ascii(b):
    return bytes((c - 32) if 97 <= c <= 122 else c for c in b)


def internal_argv():
    """The one-shot $internal marker (LOGIN deletes it on admission), then sd-solo -internal: an administrator's session in the system directory."""
    with open(os.path.join(sh.SYS, "$internal"), "w") as f:
        f.write("sandbox-lockids-solo pid=%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%S")))
    env = dict(os.environ, SD_CONFIG=os.path.join(sh.BOX, "sd.conf"))
    for k in ("SSH_CONNECTION", "SSH_TTY", "SDTEST_ADMIN"):
        env.pop(k, None)
    return [os.path.join(sh.SYS, "bin", "sd-solo"), "-internal"], env


def marker_left():
    m = os.path.join(sh.SYS, "$internal")
    if os.path.exists(m):
        os.remove(m)
        return True
    return False


def adm_raw(cmds):
    """The administrator's internal session with the commands on stdin; returns the BYTES it wrote."""
    argv, env = internal_argv()
    say("    > [internal, bytes] %s in %s: %s" % (argv, sh.SYS, " | ".join(cmds)))
    body = ("\nTERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n").encode()
    p = subprocess.run(argv, input=body, cwd=sh.SYS, env=env, capture_output=True, timeout=300)
    if marker_left():
        bail("the internal session did not take its $internal marker, so it was not the administrator's: %r" % (p.stdout + p.stderr)[-300:])
    return p.stdout + p.stderr


def adm(cmds):
    out = adm_raw(cmds).decode("latin-1")
    out = sh.ANSI.sub("", out).split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


class Holder:
    """An ORDINARY session of sduser on a pipe, kept open, that runs a program (zzlk2, the holder: it stops when bp/zzlkstop2 appears; zzlk3, the waiter:
    it ends when it gets the lock)."""

    def __init__(self, prog="zzlk2", label="holder"):
        env = sh.sd_env("xterm")
        self.out = os.path.join(sh.BOX, "%s-lockids.out" % label)
        self.fh = open(self.out, "wb")
        argv = [os.path.join(sh.SYS, "bin", "sd-solo")]
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=self.fh, stderr=subprocess.STDOUT, cwd=sh.SYS, env=env)
        self.p.stdin.write((sh.secret("account.pw") + "\nTERM 200,9999\nRUN bp %s\nOFF\n" % prog).encode())
        self.p.stdin.flush()
        say("  [%s] argv=%s cwd=%s (ordinary, account password) pid=%d stdin: TERM 200,9999 | RUN bp %s | OFF" % (label, argv, sh.SYS, self.p.pid, prog))

    def raw(self):
        try:
            self.fh.flush()
        except ValueError:
            pass
        with open(self.out, "rb") as f:
            return f.read()

    def stop(self):
        try:
            self.p.wait(timeout=20)
            return True
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
            return False
        finally:
            try:
                self.fh.close()
            except OSError:
                pass


class Planter:
    """The administrator's internal session in the background: RUN bp zzpl SH n, which writes S<n> and H<n> until told to stop."""

    def __init__(self, user):
        argv, env = internal_argv()
        self.out = os.path.join(sh.BOX, "planter-lockids.out")
        self.fh = open(self.out, "wb")
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=self.fh, stderr=subprocess.STDOUT, cwd=sh.SYS, env=env)
        self.p.stdin.write(("\nTERM 200,9999\nRUN bp zzpl SH %s\nOFF\n" % user).encode())
        self.p.stdin.flush()
        say("  [planter] argv=%s cwd=%s pid=%d stdin: TERM 200,9999 | RUN bp zzpl SH %s | OFF" % (argv, sh.SYS, self.p.pid, user))

    def raw(self):
        try:
            self.fh.flush()
        except ValueError:
            pass
        with open(self.out, "rb") as f:
            return f.read()

    def stop(self):
        sh.put(os.path.join(sh.SYS, "bp", "zzplstop"), "stop\n")
        try:
            self.p.wait(timeout=30)
            return True
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
            return False
        finally:
            try:
                self.fh.close()
            except OSError:
                pass


def plant_rows(waiter, user):
    sh.put(os.path.join(sh.SYS, "bp", "zzpl"), ZZPL)
    out = adm(["BASIC bp zzpl"])
    if not has(out, COMPILED):
        bail("zzpl did not compile: " + " | ".join(out[-8:]))
    planter = Planter(user)
    stopped = False
    ps = hs = b""
    try:
        for _ in range(40):
            if b"ZZPL writing" in planter.raw() or b"ZZPL no" in planter.raw():
                break
            time.sleep(0.5)
        marker_left()
        pr = planter.raw()
        row("PL-ctl0 the planter is writing S%s and H%s in $IPC" % (user, user), b"ZZPL writing " + user.encode() in pr, repr(pr[-200:]))
        if b"ZZPL writing" not in pr:
            return
        os.kill(waiter.p.pid, signal.SIGSTOP)
        stopped = True
        say("  the waiter (pid %d) is STOPPED: it cannot answer PSTAT or HSM" % waiter.p.pid)
        ps = adm_raw(["PSTAT USER " + user])
        say("  PSTAT USER %s wrote %d bytes: %r" % (user, len(ps), ps[-900:]))
        hs = adm_raw(["HSM USER " + user])
        say("  HSM USER %s wrote %d bytes: %r" % (user, len(hs), hs[-600:]))
    finally:
        if stopped:
            os.kill(waiter.p.pid, signal.SIGCONT)
            say("  the waiter is running again")
        ended = planter.stop()
        say("  planter output: %r" % planter.raw()[-300:])
    row("PL-ctl1 the planter ended by itself when told to, and removed what it wrote", ended and b"ZZPL done" in planter.raw(), repr(planter.raw()[-200:]))
    psu = ps.upper()
    ctl = all(p in psu for p in (b"ZZPLCMD-", b"ZZPLACCT-", b"ZZPLPROG-", b"ZZPLFILE-", b"ZZPLID-", b"ZZPLPS-"))
    row("PL1-ctl PSTAT read the PLANTED S%s: ZZPLCMD-, ZZPLACCT-, ZZPLPROG-, ZZPLFILE-, ZZPLID- and ZZPLPS- are all in its output" % user, ctl, "not all in %d bytes" % len(ps))
    hits = [b for b in PL_S_RAW if b.upper() in psu] + ([155] if 155 in ps else [])
    row("PL1 PSTAT writes none of the planted record's sequences and no byte 155", ctl and not hits, "raw: %r" % hits)
    miss = [t for t in PL_S_SAFE if t.upper() not in psu]
    row("PL2 PSTAT shows every planted text with each byte of the rule one '?': command, account, program, line, file, record id, @PSTAT", ctl and not miss, "missing %r" % miss)
    hsu = hs.upper()
    hctl = b"ZZPLHSM-" in hsu
    row("PL3-ctl HSM USER %s read the PLANTED H%s (ZZPLHSM- is in its output)" % (user, user), hctl, "not in %d bytes" % len(hs))
    hits = [b for b in PL_H_RAW if b in hs] + ([155] if 155 in hs else [])
    miss = [t for t in PL_H_SAFE if t not in hs]
    row("PL3 HSM writes neither of the planted sequences (ESC [ 2 j in the name, ESC c in the calls column) and no byte 155", hctl and not hits, "raw: %r" % hits)
    row("PL4 HSM shows the name and the calls column with each byte of the rule one '?' (%r)" % PL_H_SAFE, hctl and not miss, "missing %r" % miss)
    out = adm(["RUN bp zzpl F " + PL_FUSER])
    planted = any(("ZZPL planted " + PL_FUSER) in ln for ln in out)
    row("PL5-ctl the planter wrote F%s" % PL_FUSER, planted, " | ".join(out[-6:]))
    fs = adm_raw(["PROFILER DISPLAY USER " + PL_FUSER, "1", "1", "1", "Q"])
    say("  PROFILER DISPLAY USER %s (answers 1 1 1 Q) wrote %d bytes: %r" % (PL_FUSER, len(fs), fs[-900:]))
    fsu = fs.upper()
    fctl = planted and all(p in fsu for p in (b"ZZPLEV-", b"ZZPLQ-", b"ZZPLP-"))
    row("PL5 PROFILER DISPLAY reached the three levels of the planted profile (ZZPLEV-, ZZPLQ-, ZZPLP-)", fctl, "not all in %d bytes" % len(fs))
    hits = [b for b in PL_F_RAW if b in fs] + ([155] if 155 in fs else [])
    miss = [t for t in PL_F_SAFE if t not in fs]
    row("PL6 PROFILER DISPLAY writes none of the planted sequences and no byte 155", fctl and not hits, "raw: %r" % hits)
    row("PL7 PROFILER DISPLAY shows the event, the qualifier and the program with each byte of the rule one '?' (%r)" % PL_F_SAFE, fctl and not miss, "missing %r" % miss)
    out = adm(["RUN bp zzpl X " + PL_FUSER])
    row("PL8 the planter removed F%s" % PL_FUSER, any(("ZZPL removed " + PL_FUSER) in ln for ln in out), " | ".join(out[-6:]))


def getlocks_user_rows(wno):
    sh.put(os.path.join(sh.SYS, "bp", "zzgu"), ZZGU % wno)
    out = adm(["BASIC bp zzgu", "RUN bp zzgu"])
    say("  [GU] the administrator's $internal zzgu, getlocks('', n) for n = %s 12345 hi+1 65537 -5 hi:" % wno)
    rows = {}
    for ln in out:
        m = re.match(r"^ZZGU (\d) (\S+) n=(\d+) c=(\d+) t=(\S*)$", ln.strip())
        if m:
            rows[int(m.group(1))] = (m.group(2), int(m.group(3)), int(m.group(4)), m.group(5))
            say("    " + ln.strip())
    ended = any(ln.strip() == "ZZGU end" for ln in out)
    c = rows.get(1)
    row("GU-ctl the waiter's own number (%s) gives the counters and its WAIT line" % wno, c is not None and c[2] == 3 and "WAIT" in c[3].split(","), repr(c))
    for k, what in ((2, "12345 (past the user map)"), (3, "hi_user_no + 1 (one past the map)"), (4, "65537 (16 bits would make it user 1)"),
                    (5, "-5"), (6, "hi_user_no (in range, held by nobody)")):
        r = rows.get(k)
        row("GU%d getlocks('', %s) answers with the three counters and no lock line" % (k, what), r is not None and r[1] == 1 and r[2] == 3 and r[3] == "", repr(r))
    row("GU7 the program went on to its last line after all six (no fault)", ended, " | ".join(out[-6:]))


def main():
    say("sandbox-lockids-solo: S.216 gap 13 - another session's text, escaped.  SDSOLOBOX_KEYSET=%s" % os.environ.get("SDSOLOBOX_KEYSET", "(unset)"))
    hold = None
    waiter = None
    try:
        sh.start_sandbox()
        sh.arrange("terminal")                       # a session starts at the prompt, not on the home screen
        if not os.path.isdir(os.path.join(sh.SYS, "bp")):
            bail("the system directory has no bp file: %s" % os.path.join(sh.SYS, "bp"))
        sh.put(os.path.join(sh.ACCT, "bp", "zzlk2"), ZZLK2)
        sh.put(os.path.join(sh.ACCT, "bp", "zzlk3"), ZZLK3)
        out = sh.plain(["CREATE.FILE zzlf", "BASIC bp zzlk2", "BASIC bp zzlk3"])
        n_ok = sum(1 for ln in out if re.match(COMPILED, ln))
        if n_ok != 2:
            bail("zzlk2 / zzlk3 did not compile (%d of 2): %s" % (n_ok, " | ".join(out[-8:])))
        sh.put(os.path.join(sh.SYS, "bp", "zzgl"), ZZGL)
        out = adm(["BASIC bp zzgl"])
        if not has(out, COMPILED):
            bail("zzgl did not compile: " + " | ".join(out[-8:]))
        hold = Holder()
        for _ in range(40):
            if b"ZZLK2 holding" in hold.raw() or b"ZZLK2 no" in hold.raw():
                break
            time.sleep(0.5)
        hr = hold.raw()
        say("  holder output: %r" % hr[-400:])
        if b"ZZLK2 holding" not in hr:
            bail("the ordinary holder did not reach 'holding', so no lock exists to read: %r" % hr[-200:])
        raw_up = upper_ascii(PLANT)
        own = [codes(m) for m in re.findall(rb"ZZOWN RU (\S*)", hr)]
        say("  the holder's own locks (FILEINFO 1039): %r" % own)
        row("LK-ctl0 the ordinary holder took its two locks and listed them (FILEINFO 1039 gave %d)" % len(own), len(own) == 2, repr(own))
        row("LK1 a program's OWN lock ids are still given raw by FILEINFO(f, 1039) (27, 7, 127, 155 and 200 are there)",
            any(all(c in o for c in (27, 7, 127, 155, 200)) for o in own), repr(own))
        out = adm(["RUN bp zzgl"])
        got = {}
        for ln in out:
            m = re.match(r"^ZZGL (\S+) (\S*)$", ln.strip())
            if m:
                got.setdefault(m.group(1), []).append(codes(m.group(2)))
        say("  GETLOCKS for zzlf, as the administrator: %r" % got)
        ids = got.get("RU", [])
        plain = [i for i in ids if i in (b"PLAINID", b"plainid")]
        row("LK-ctl1 GETLOCKS gives the control lock's id exactly (PLAINID)", len(plain) == 1, repr(ids))
        planted = [i for i in ids if i.upper().startswith(b"LKOK-")]
        bad = [c for i in planted for c in i if c in UNSAFE]
        row("LK2 GETLOCKS gives the other session's planted id with no control byte, DEL, C1 byte or mark", len(planted) == 1 and not bad, "planted %r unsafe bytes %r" % (planted, bad))
        want = bytes(63 if c in UNSAFE else c for c in raw_up)
        row("LK3 ... the same length as the raw id, each such byte '?' and every other byte (200 included) as the lock table holds it",
            len(planted) == 1 and upper_ascii(planted[0]) == want, "got %r want %r" % (planted, want))
        lr = adm_raw(["LIST.READU WAIT"])
        pre = b"LKOK-" in lr.upper()
        say("  LIST.READU wrote %d bytes; the plain prefix LKOK- is there: %s" % (len(lr), pre))
        row("LK4-ctl LIST.READU listed the planted lock (its plain prefix LKOK- reached the output)", pre, "not in %d bytes" % len(lr))
        lu = lr.upper()
        hits = [b for b in (b"\x1b]0;PWNLID", b"\x1b[2JCLRLID") if b in lu]
        row("LK4 LIST.READU writes no ESC ] 0 ; PWNLID and no ESC [ 2 J of another session's id", pre and not hits, "raw: %r" % hits)

        waiter = Holder("zzlk3", "waiter")
        for _ in range(40):
            if b"ZZLK3 waiting" in waiter.raw() or b"ZZLK3 no" in waiter.raw():
                break
            time.sleep(0.5)
        time.sleep(1.0)
        wr = waiter.raw()
        say("  waiter output: %r" % wr[-400:])
        mu = re.search(rb"ZZLK3 user (\d+)", wr)
        if b"ZZLK3 waiting" not in wr or not mu or b"ZZLK3 got" in wr:
            bail("the ordinary waiter is not waiting for the planted lock, so PSTAT has nothing to show: %r" % wr[-200:])
        ps = adm_raw(["PSTAT USER " + mu.group(1).decode()])
        psu = ps.upper()
        say("  PSTAT USER %s wrote %d bytes: %r" % (mu.group(1).decode(), len(ps), ps[-900:]))
        ctl_cmd = b"ZZCMD-" in psu
        ctl = b"ZZPS-" in psu and b"LKOK-" in psu
        row("LK6-ctl PSTAT reached the waiter's status record: its @PSTAT (zzps-) and the record line (LKOK-) are in the output; command zzcmd- there: %s" % ctl_cmd,
            ctl, "not in %d bytes" % len(ps))
        hits = [b for b in (b"\x1b]0;PWNCMD", b"\x1b[2JCLRPS", b"\x1b]0;PWNLID", b"\x1b[2JCLRLID") if b in psu] + ([155] if 155 in ps else [])
        row("LK6 PSTAT writes none of the waiter's sequences (ESC ] 0 ; PWNCMD, ESC [ 2 J CLRPS, ESC ] 0 ; PWNLID, ESC [ 2 J CLRLID) and no byte 155",
            ctl and not hits, "raw: %r" % hits)
        row("LK7 the command line is the DISPLAY sentence with each control byte one '?' (%r, case aside)" % PSTAT_CMD, PSTAT_CMD.upper() in psu, "not in output")
        row("LK8 the record line holds the waited-for id as GETLOCKS gives it (%r)" % want, want.upper() in psu, "not in output")
        row("LK9 the @PSTAT line is %r: control bytes '?', byte 200 kept, the value mark a space (sheet 492)" % PSTAT_TEXT, PSTAT_TEXT in ps, "not in output")

        getlocks_user_rows(mu.group(1).decode())
        plant_rows(waiter, mu.group(1).decode())
    finally:
        if hold is not None:
            sh.put(os.path.join(sh.ACCT, "bp", "zzlkstop2"), "stop\n")
            row("LK5 the holder ended by itself once told to (its locks were given back)", hold.stop(), "the holder had to be killed")
        if waiter is not None:
            ended = waiter.stop()
            row("LK10 the waiter got the lock once the holder had gone, and ended", ended and b"ZZLK3 got" in waiter.raw(), "ended=%s output %r" % (ended, waiter.raw()[-200:]))
        sh.teardown()
    say("\nsandbox-lockids-solo: %d passed, %d failed" % (sh.passed, sh.failed))
    return 0 if sh.failed == 0 and sh.passed > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
