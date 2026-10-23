#!/usr/bin/env python3
#
# sandbox-tk-solo.py - the screen library, SED, the IDE and tool.keys in SD Core for Linux Solo (carry 13, 22 Oct 2026), on a pseudo-terminal.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 .../sandbox-tk-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent).  Exit 0 every row passed, 1 a row failed,
# 2 it could not run.  A plain session of Solo is signed on with the account password as its FIRST line (read from <dir>/account.pw and never printed); ADMIN asks the
# administrator password (<dir>/admin.pw) at a hidden prompt.  Core's suites for the same things are sandbox-tk-keys.py, sandbox-tk-base.py, sandbox-ide.py and the sed suites:
# this one is the Solo-shaped subset that proves the CARRIED programs run on Solo's own kernel, and the one place Solo differs from Core on purpose.
#
# START-HISTORY:
# 22 Oct 26 dm  New (Solo carry 13).
# END-HISTORY
#
# WHAT IS HELD.  tool.keys: the first screen, the keys of three terminal types named as terminfo.src gives them (the same tables as Core's suite), a character, an Alt-letter, the
# grid, the mouse, raw bytes, the theme, Ctrl-Q, a window too small, the lock and its way out, the end of a piped input.  The screen library: a SCREEN program with a check box, a
# slider, a selector, an entry with ACCEL and a label whose marked letters are Alt-letters and are drawn underlined (mono theme).  THE ONE DIFFERENCE FROM CORE (deviation 1 of
# .claude/solo-carry-13-plan.md): Solo has no edit gates, so SED and the IDE refuse a save into the VOC without ADMIN, with the reason Solo's voc_guard gives, and save into a
# user file without it; the DISK is read back by a BASIC program in a separate session.  The default display of a session with no terminal is 140 by 42.  NOT HELD HERE: CED
# (its save check is the same line, read in the text check only), a real terminal's bytes, UTF-8 borders, the cursor lock's own Ctrl-Q, y (Core's suite has it).
import os
import re
import resource
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ptydrive import PtySession  # noqa: E402

TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
passed = failed = 0
BOX = SYS = ""
E = "\x1b"
XTERM = {"up": E + "OA", "down": E + "OB", "right": E + "OC", "left": E + "OD", "home": E + "[1~", "end": E + "[4~", "pgup": E + "[5~", "pgdn": E + "[6~", "ins": E + "[2~",
         "del": E + "[3~", "btab": E + "[Z", "f1": E + "OP", "f2": E + "OQ", "f3": E + "OR", "f4": E + "OS", "f5": E + "[15~", "f6": E + "[17~", "f7": E + "[18~",
         "f8": E + "[19~", "f9": E + "[20~", "f10": E + "[21~", "f11": E + "[23~", "f12": E + "[24~"}
LINUX = dict(XTERM, up=E + "[A", down=E + "[B", right=E + "[C", left=E + "[D", f1=E + "[[A", f2=E + "[[B", f3=E + "[[C", f4=E + "[[D", f5=E + "[[E")
VT100 = {"up": E + "OA", "down": E + "OB", "right": E + "OC", "left": E + "OD", "home": E + "[H", "f1": E + "OP", "f2": E + "OQ", "f3": E + "OR", "f4": E + "OS", "f5": E + "OT",
         "f6": E + "OU", "f7": E + "OV", "f8": E + "OL", "f9": E + "OW", "f10": E + "OX"}
PLAIN = {"tab": "\t", "enter": "\r", "bs": "\x7f", "esc": E, "ctrl-a": "\x01", "ctrl-g": "\x07", "alt-s": E + "s"}
F2, CTRL_X_S = E + "OQ", "\x18\x13"
VOC_REFUSAL = "The VOC can only be changed after admin (the administrator password)"


def say(s=""):
    print(s, flush=True)


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say("  [PASS] " + name)
    else:
        failed += 1
        say("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def bail(msg):
    say("sandbox-tk-solo: CANNOT RUN - " + msg)
    sys.exit(2)


def secret(name):
    try:
        with open(os.path.join(BOX, name)) as f:
            pw = f.read().strip()
    except OSError as e:
        bail("cannot read %s: %s" % (name, e))
    if not pw:
        bail("%s is empty" % name)
    return pw


class Term:
    """A plain Solo session of sduser on a pseudo-terminal: the account password, then TERM; with admin=True also ADMIN and its password."""

    def __init__(self, cmd=None, cols=140, rows=43, term="xterm", admin=False):
        env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"), TERM=term, LC_ALL="C", LANG="C")
        env.pop("SDTEST_ADMIN", None)
        self.s = PtySession([os.path.join(SYS, "bin", "sd-solo")], SYS, env, cols, rows)
        self.s.settle(1.5)
        self.s.type(secret("account.pw") + "\r", idle=1.5)
        self.s.type("TERM %s\r" % term)
        self.s.type("TERM %d,%d\r" % (cols, rows))
        if admin:
            self.s.type("ADMIN\r", idle=0.8)
            self.s.type(secret("admin.pw") + "\r", idle=1.0)
        if cmd:
            self.s.type(cmd + "\r", idle=1.2)

    def lines(self):
        return self.s.screen.lines()

    def line(self, r):
        L = self.lines()
        return L[r].rstrip() if r < len(L) else ""

    def text(self):
        return "\n".join(self.lines())

    def rev(self, r):
        return self.s.screen.reverse(r)

    def key(self, seq, idle=0.4):
        self.s.type(seq, idle=idle)

    def end(self):
        self.s.type("OFF\r", idle=0.4)
        self.s.finish()

    def hangup(self):
        self.s.finish(limit=0.5)             # the terminal is closed under the program: SD gets SIGHUP and ends cleanly


def newest(t):
    m = re.match(r"\s*(\d+)\s+(\S+)\s?(.*)$", t.line(14)[2:45])
    return (int(m.group(1)), m.group(2), m.group(3).strip()) if m else None


def write_prog(name, body):
    path = os.path.join(SYS, "user_accounts", "sduser", "bp", name)
    with open(path, "w", encoding="latin-1") as f:
        f.write(body)


def compile_and_run(t, name):
    t.key("BASIC bp %s\r" % name, idle=2.2)
    t.key("RUN bp %s\r" % name, idle=1.5)


def voc_first_field():
    t = Term()
    t.key("RUN bp zzrdv\r", idle=1.2)
    m = re.findall(r"VOCREC\[([^\]]*)\]", t.text())
    t.end()
    return m[-1] if m else None


def user_first_field():
    t = Term()
    t.key("RUN bp zzrdu\r", idle=1.2)
    m = re.findall(r"USERREC\[([^\]]*)\]", t.text())
    t.end()
    return m[-1] if m else None


def names_row(term, table):
    t = Term("tool.keys", term=term)
    if "Last keys" not in t.text():
        say("\n".join(l.rstrip() for l in t.lines() if l.strip())[:900])
        bail("tool.keys never drew its screen under %s, so no row below can be believed" % term)
    bad = []
    for name, seq in table.items():
        before = newest(t)
        t.key(seq, idle=0.35)
        after = newest(t)
        if not after or after[1] != name or (before and after[0] != before[0] + 1) or (not before and after[0] != 1):
            bad.append("%s -> %r (was %r)" % (name, after, before))
    row("%s: the %d keys of its terminal type are each named as terminfo.src gives them, one line added for each" % (term, len(table)), not bad, "; ".join(bad)[:600])
    t.end()


def main():
    global BOX, SYS
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-tk-solo.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    say("sandbox-tk-solo: sandbox %s" % BOX)
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=1800)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-tk-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built Solo sandbox" % BOX)
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=300)
    try:
        run_rows()
    finally:
        subprocess.run([sys.executable, TOOL, BOX, "stop"], capture_output=True, text=True, errors="replace", timeout=300)
    say("\nsandbox-tk-solo: %d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


def sec_keys():
    say("\n--- tool.keys on Solo (xterm, 140 by 43)")
    t = Term("tool.keys")
    L = t.text()
    if "Last keys" not in L:
        say("\n".join(l.rstrip() for l in t.lines() if l.strip())[:900])
        bail("tool.keys never drew its screen, so no row below can be believed")
    row("the seven boxes are there: Terminal, Last keys, Keys seen, Mouse, Box drawing, Help, Styles", all(s in L for s in ("Terminal", "Last keys", "Keys seen", "Mouse", "Box drawing", "Help", "Styles")), L[:200])
    row("the function-key row is row 42: '^L clear  ^R raw/names  ^T theme  ^Q quit'; the status line [Keys]; row 0 names the app and the user", t.line(42) == "^L clear  ^R raw/names  ^T theme  ^Q quit"
        and t.line(40).startswith("[Keys]") and "tool.keys" in t.line(0) and "sduser" in t.line(0), repr((t.line(42), t.line(40), t.line(0)[-40:])))
    for want in ("TERM (SD)   xterm", "Window      140 x 43  (layout 140 x 43)", "Colour      yes", "Theme       mono", "Keys seen   0 of 52, 0 pressed"):
        row("Terminal box: %r" % want, want in L, "")
    t.end()
    names_row("xterm", dict(XTERM, **PLAIN))
    names_row("linux", LINUX)
    names_row("vt100", VT100)

    t = Term("tool.keys")
    t.key("a")
    t.key(E + "S")
    t.key(E + "[<0;20;10M")
    t.key(E + "[<64;20;10M")
    n = newest(t)
    L = t.text()
    row("a character, an Alt+Shift letter, a mouse press and a wheel: the newest is the wheel, the grid ticks char, alt-x and mouse, 'Keys seen   3 of 52, 4 pressed'",
        n is not None and n[1] == "mouse" and all(s in L for s in ("[x] char", "[x] alt-x", "[x] mouse")) and "Keys seen   3 of 52, 4 pressed" in L and "Mouse       2 events" in L, repr((n, t.line(2)[2:45])))
    t.key("\x12")
    t.key(XTERM["f5"])
    row("Ctrl-R, then F5 of xterm: the bytes '1b 5b 31 35 7e' and the characters '.[15~'", "1b 5b 31 35 7e" in t.line(14)[2:45] and ".[15~" in t.line(14)[2:45], repr(t.line(14)[2:45]))
    t.key("\x11")
    t.s.settle(0.8)
    row("Ctrl-Q in raw mode leaves: the screen is gone", "Last keys" not in t.text(), "")
    t.key("WHO.AM.I\r", idle=1.0)
    row("...and the Solo session is alive and is not the administrator ('Admin?      : No')", re.search(r"Admin\?\s*:\s*No", t.text()) is not None, t.text()[-200:])
    t.end()
    t = Term("tool.keys", term="vt100")
    t.key("\x14")
    row("Ctrl-T on a vt100 (no colour) keeps mono and says why", "Theme       mono" in t.text() and "cannot show colour" in t.line(40), repr(t.line(40)))
    t.end()
    t = Term("tool.keys", cols=100, rows=30)
    row("a window of 100 by 30 is refused: 'tool.keys needs a window of at least 140 columns by 43 lines'", "tool.keys needs a window of at least 140 columns by 43 lines" in t.text() and "Last keys" not in t.text(), t.text()[-200:])
    t.end()
    t = Term("tool.keys")
    t.key("a")
    t.s.resize(100, 30, idle=1.0)
    lock = "is laid out for 140 by 43" in t.text()
    t.s.resize(140, 43, idle=1.2)
    row("a window made smaller shows the cursor lock, made larger gives the screen back with the key pressed before", lock and "Last keys" in t.text() and newest(t) is not None and newest(t)[1] == "a", repr(newest(t)))
    t.end()

def sec_screen():
    say("\n--- a SCREEN program: Alt-letters, the underlined letter, ACCEL")
    write_prog("zzscr", """   opened = @false
   screen open clear then
      opened = @true
   end
   if not(opened) then
      crt 'NOOPEN'
      stop
   end
   screen form title 'Solo' at 5,3 size 70,14 returning f
   screen check f, 'ck', '&Verbose' at 3,2
   screen slider f, 'sl', '&Switch' at 3,4
   screen selector f, 'se', '&Colour', 'red':@vm:'green':@vm:'blue' at 3,6
   screen entry f, 'en' at 3,8 width 20 accel 'f5'
   screen label f, 'nm', '&Name' at 3,10
   screen button f, 'go', '&Go' at 3,12 default
   screen run f returning r else r = 'cancel'
   screen get f, 'ck' returning v1
   screen get f, 'sl' returning v2
   screen get f, 'se' returning v3
   screen get f, 'en' returning v4
   screen close
   crt 'RESULT ' : r : ' ck=' : v1 : ' sl=' : v2 : ' se=' : v3 : ' en=' : v4
end
""")
    t = Term()
    t.key("BASIC bp zzscr\r", idle=2.5)
    row("the program compiles in Solo's compiler (SELECTOR, SLIDER, ACCEL are in its table)", "Compiled 1 program(s) with no errors" in t.text(), t.text()[-300:])
    t.key("RUN bp zzscr\r", idle=1.5)
    L = t.text()
    row("the form is drawn: 'Verbose [ ]', 'Switch [OFF | on]', 'Colour [RED | green | blue]', '[ Go ]', 'Name'; no & shown", all(s in L for s in ("Verbose [ ]", "Switch [OFF | on]", "Colour [RED | green | blue]", "[ Go ]", "Name")) and "&" not in L, L[:300])
    # the check box has the focus at the start (the whole of it is in reverse video then), so the unfocused slider is read
    rv, cv = next(((r_, l_.find("Switch")) for r_, l_ in enumerate(t.lines()) if "Switch [OFF | on]" in l_), (0, 0))
    sc = t.s.screen
    row("the marked letter S of Switch is underlined (the hotkey style of the mono theme), the letters next to it are not",
        "u" in sc.style(rv, cv)[2] and "u" not in sc.style(rv, cv + 1)[2] and "u" not in sc.style(rv, cv + 2)[2], repr((sc.style(rv, cv), sc.style(rv, cv + 1))))
    rf, cf = next(((r_, l_.find("Verbose")) for r_, l_ in enumerate(t.lines()) if "Verbose [ ]" in l_), (0, 0))
    row("...and the focused check box is in reverse video, its letter not drawn apart", "r" in sc.style(rf, cf)[2] and "u" not in sc.style(rf, cf)[2], repr(sc.style(rf, cf)))
    t.key(E + "v")
    t.key(E + "s")
    t.key(E + "c")
    L = t.text()
    row("Alt+V ticks the check box, Alt+S slides the switch, Alt+C chooses the next word: 'Verbose [x]', 'Switch [off | ON]', 'Colour [red | GREEN | blue]'", all(s in L for s in ("Verbose [x]", "Switch [off | ON]", "Colour [red | GREEN | blue]")), L[:300])
    t.key("\x1b[15~")
    t.key("ab")
    t.key(E + "g", idle=1.0)
    row("ACCEL 'f5' took the focus to the entry (what was typed landed in it) and Alt+G pressed &Go: the form ends and the program prints 'RESULT go ck=1 sl=1 se=2 en=ab'",
        "RESULT go ck=1 sl=1 se=2 en=ab" in t.text(), t.text()[-300:])
    t.end()

def sec_voc():
    say("\n--- SED and the IDE save into the VOC only after ADMIN (the one deliberate difference from Core), and into a user file without it")
    write_prog("zzmkv", "   open 'VOC' to v else crt 'NOVOC' ; stop\n   write 'X':@fm:'one' to v, 'zzvoc'\n   crt 'MADE'\nend\n")
    write_prog("zzrdv", "   open 'VOC' to v else crt 'NOVOC' ; stop\n   read r from v, 'zzvoc' then crt 'VOCREC[' : r<1> : ']' else crt 'VOCREC[none]'\nend\n")
    write_prog("zzmku", "   open 'zzufile' to f else crt 'NOFILE' ; stop\n   write 'X':@fm:'one' to f, 'rec1'\n   crt 'MADE'\nend\n")
    write_prog("zzrdu", "   open 'zzufile' to f else crt 'NOFILE' ; stop\n   read r from f, 'rec1' then crt 'USERREC[' : r<1> : ']' else crt 'USERREC[none]'\nend\n")
    t = Term(admin=True)
    for p in ("zzmkv", "zzrdv", "zzmku", "zzrdu"):
        t.key("BASIC bp %s\r" % p, idle=2.2)
    t.key("CREATE.FILE zzufile DYNAMIC\r", idle=1.5)
    t.key("RUN bp zzmkv\r", idle=1.2)
    t.key("RUN bp zzmku\r", idle=1.2)
    row("setup: the administrator made the VOC record zzvoc and the user file's record", t.text().count("MADE") >= 2, t.text()[-300:])
    t.end()
    row("setup: the VOC record starts 'X', the user file's record 'X'", voc_first_field() == "X" and user_first_field() == "X", repr((voc_first_field(), user_first_field())))

    t = Term("SED VOC zzvoc")
    t.key("ABC")
    t.key(CTRL_X_S, idle=1.0)
    row("SED, not ADMIN: Ctrl-X Ctrl-S into the VOC is refused with Solo's reason in the message line", VOC_REFUSAL in t.line(40), repr(t.line(40)))
    t.hangup()
    row("...and the VOC record on the disk is as it was ('X')", voc_first_field() == "X", repr(voc_first_field()))
    t = Term("IDE VOC zzvoc")
    t.key("ABC")
    t.key(F2, idle=1.0)
    row("the IDE, not ADMIN: F2 into the VOC is refused with the same reason in the status line", VOC_REFUSAL in t.line(42), repr(t.line(42)))
    t.hangup()
    row("...and the VOC record is still 'X'", voc_first_field() == "X", repr(voc_first_field()))

    t = Term("SED VOC zzvoc", admin=True)
    t.key("Q")
    t.key(CTRL_X_S, idle=1.0)
    t.hangup()
    row("SED after ADMIN: the save into the VOC goes through (the record is 'QX')", voc_first_field() == "QX", repr(voc_first_field()))
    t = Term("IDE VOC zzvoc", admin=True)
    t.key("ABC")
    t.key(F2, idle=1.0)
    row("the IDE after ADMIN: 'Saved VOC zzvoc' in the status line", "Saved VOC zzvoc" in t.line(42), repr(t.line(42)))
    t.hangup()
    row("...read from the disk", voc_first_field() == "ABCQX", repr(voc_first_field()))

    t = Term("SED zzufile rec1")
    t.key("Q")
    t.key(CTRL_X_S, idle=1.0)
    t.hangup()
    row("SED saves into a USER file without ADMIN (the check refuses only the VOC): the record is 'QX'", user_first_field() == "QX", repr(user_first_field()))
    t = Term("IDE zzufile rec1")
    t.key("ABC")
    t.key(F2, idle=1.0)
    saved = "Saved zzufile rec1" in t.line(42)
    t.hangup()
    row("the IDE saves into a user file without ADMIN: 'Saved zzufile rec1' and the record is 'ABCQX'", saved and user_first_field() == "ABCQX", repr((t.line(42), user_first_field())))

def sec_size():
    say("\n--- the default display is 140 by 42 (Core's 18 Oct change, carried)")
    write_prog("zzsz", "   crt 'SIZE ' : @crtwide : 'x' : @crthigh\nend\n")
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"), LC_ALL="C")
    env.pop("SDTEST_ADMIN", None)
    body = secret("account.pw") + "\nBASIC bp zzsz\nRUN bp zzsz\nTERM 200,50\nRUN bp zzsz\nTERM DEFAULT\nRUN bp zzsz\nOFF\n"
    p = subprocess.run([os.path.join(SYS, "bin", "sd-solo")], input=body, capture_output=True, text=True, errors="replace", cwd=SYS, env=env, timeout=120)
    sizes = re.findall(r"^SIZE (\d+x\d+)", ANSI.sub("", p.stdout), re.M)
    row("a session with no terminal has 140 by 42; TERM 200,50 sets 200 by 50; TERM DEFAULT gives 140 by 42 again", sizes == ["140x42", "200x50", "140x42"], repr(sizes))

def sec_eof():
    say("\n--- the end of the input ends tool.keys (a pipe)")
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"), TERM="xterm", LC_ALL="C")
    env.pop("SDTEST_ADMIN", None)
    r0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    p = subprocess.Popen([os.path.join(SYS, "bin", "sd-solo")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=SYS, env=env)
    t0 = time.time()
    p.stdin.write((secret("account.pw") + "\nTERM 140,43\ntool.keys\n").encode())
    p.stdin.flush()
    p.stdin.close()
    ended = False
    while time.time() - t0 < 20:
        if p.poll() is not None:
            ended = True
            break
        time.sleep(0.2)
    took = time.time() - t0
    if not ended:
        os.kill(p.pid, 1)
        time.sleep(1)
        if p.poll() is None:
            p.kill()
    p.wait()
    r1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
    say("    [measured] ended: %s after %.1f s, the child's CPU %.2f s" % (ended, took, cpu))
    row("a piped session whose input ENDS ends the app within 20 s and does not spin (under 3 s of CPU)", ended and cpu < 3.0, "%.1f s, %.2f s" % (took, cpu))


SECTIONS = [("keys", sec_keys), ("screen", sec_screen), ("voc", sec_voc), ("size", sec_size), ("eof", sec_eof)]


def run_rows():
    only = [a[len("--only="):].split(",") for a in sys.argv[1:] if a.startswith("--only=")]
    only = only[0] if only else []
    for name, fn in SECTIONS:
        if not only or name in only:
            fn()


if __name__ == "__main__":
    main()
