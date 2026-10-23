#!/usr/bin/env python3
#
# sandbox-home-solo.py - the home screen, the start setting, tiles off, the account's own programs, the context help, pdf and the readers it may start (SOLO CARRY 14, 23 Oct 2026),
#                        RUN on a private SD Core for Linux Solo, on a pseudo-terminal.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=n python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-home-solo.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (with --build it is built first from THIS tree; it must be empty or absent).  Exit 0 every row passed, 1 a row failed,
# 2 it could not run.  Solo's counterpart of Core's sandbox-home.py and sandbox-docs.py, which hold the rows this one is adapted from.
#
# START-HISTORY:
# 23 Oct 26 dm  New (Solo carry 14).
# END-HISTORY
#
# THE THREE LANES (as sandbox-osgate.py and sandbox-tk-solo.py have them).  A PLAIN session of sduser on a PSEUDO-TERMINAL: sd-solo with the account password as the first line (read from
# <dir>/account.pw, never printed); ADMIN and <dir>/admin.pw typed at the prompt make it the administrator's.  A plain session on a PIPE (the home screen is never handed to one: its
# input would be read as keys).  An INTERNAL session (sandbox-fromtree.py sess): the administrator's verbs without a pty.  An ordinary lane is proved ordinary (WHO.AM.I: Admin? No)
# before any refusal is believed.
#
# WHERE THE SOLO ACCOUNT DIFFERS FROM CORE'S (each of these is a row's reason).  There is one account, so there is no Switch account tile and no per-account start word (the system default
# decides; MODIFY.ACCOUNT does not exist); context.help and pdf/ are in the SD system directory (sys/) and not in a shared account; set.pins is Solo's MODIFY.ACCOUNT PINS-ON / PINS-OFF; an
# administrator verb refuses with message 2001 ("Command requires administrator privileges") where Core's ordinary VOC has no entry.
#
# THE VIEWER.  The viewer must pass !viewlist's test (owned by root, not writable by group or others), so no file the sandbox makes can be one.  /usr/bin/touch does: given one argument it
# sets that file's modification time, which is the EVIDENCE that pdf started it, with the document it was given and nothing else.
#
# WHAT IS HELD.  START: the delivered default (the file start.default absent) is the home screen, on a terminal only; SET.START.DEFAULT, its words and the refusal of an ordinary session;
# ADMIN typed at the prompt.  PAGE: tiles, groups, the header with Sign out alone, the foot, the focus and every key that moves it, the menu bar, F5, F10; the administrator's page; the
# no-colour (boxed) page; the tiles starting commands and the screen coming back; sign out; EXIT where the screen was not used; the mouse; a window too small.  SET.TILE: its words and
# refusals, the register field, the audit line, the page without the tile, Sign out kept, Terminal off ends a session whose screen cannot be drawn.  SET.PINS and MY.MENU's refusal.
# CONTEXT HELP: LOAD.HELP's counts, $tk_help read through a probe in the SD system directory (only the administrator's pages call it in Solo, so there is no ordinary lane), a key folded, a missing key, a bad key.  PDF: the list, every refusal, the document opened, the audit line.  SET.VIEWER:
# its refusals and list.  DOCS.INSTALL.  tool.menus and tool.viewers: the [?] buttons, F1, the help box, the Documentation button, a tile turned off and on through the page, the Bypass
# programs page.  MENU.
# NOT HELD: the installer's questions (test-install-viewer.sh, test-install-osaccess.sh and a real install), a real PDF reader showing a real document, a real ssh sign-on, the account's own
# programs appearing as tiles and MY.MENU's page (only the permission and the group are held), a UTF-8 border, a window bigger than 140 by 43.
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ptydrive import PtySession  # noqa: E402

TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
passed = failed = 0
BOX = SYS = REG = ACCT = ""
SECRETS = []
E = "\x1b"
# the keys of terminfo's linux entry: the LOGIN paragraph (newvoc/login) says TERM LINUX and runs before the home screen starts, whatever TERM the terminal had
KEYS = {"up": E + "[A", "down": E + "[B", "right": E + "[C", "left": E + "[D", "home": E + "[1~", "end": E + "[4~", "pgup": E + "[5~", "pgdn": E + "[6~", "tab": "\t",
        "btab": E + "[Z", "f1": E + "[[A", "f2": E + "[[B", "f3": E + "[[C", "f4": E + "[[D", "f5": E + "[[E", "f6": E + "[17~", "f10": E + "[21~", "enter": "\r", "esc": E,
        "ctrl-q": "\x11", "bs": "\x7f"}
OLD = 1000000000                                  # the modification time given to a fixture document: a viewer that touches it moves it
DOCS = {"01-accounts-and-security.pdf": b"%PDF-1.4\naccounts\n", "29a-sd-tcl-the-home-screen.pdf": b"%PDF-1.4\nhome\n", "guide-one.pdf": b"%PDF-1.4\none\n", "guide-two.pdf": b"%PDF-1.4\ntwo\n",
        "Upper.pdf": b"%PDF-1.4\nupper\n", "notes.txt": b"not a pdf\n"}
LISTED = ["01-accounts-and-security", "29a-sd-tcl-the-home-screen", "guide-one", "guide-two"]       # what PDF lists: regular files, lower case, .pdf
HELPSRC = os.path.join(os.path.dirname(HERE), "sdsys", "helptext")
SIGNOUT_ASK = "Sign out of SD?"


def say(s=""):
    for sec in SECRETS:
        s = s.replace(sec, "<password>")
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
    say("sandbox-home-solo: CANNOT RUN - " + msg)
    sys.exit(2)


def secret(name):
    try:
        with open(os.path.join(BOX, name)) as f:
            pw = f.read().strip()
    except OSError as e:
        bail("cannot read %s: %s" % (name, e))
    if not pw:
        bail("%s is empty" % name)
    if pw not in SECRETS:
        SECRETS.append(pw)
    return pw


def has(lines, pat):
    return any(re.search(pat, ln) for ln in lines)


def put(path, text):
    with open(path, "w", encoding="latin-1") as f:
        f.write(text)


def sd_env(term="xterm", display=None):
    env = dict(os.environ, SD_CONFIG=os.path.join(BOX, "sd.conf"), TERM=term, LC_ALL="C", LANG="C")
    env.pop("SDTEST_ADMIN", None)
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    if display:
        env["DISPLAY"] = display
    return env


class H:
    """One plain session of sduser on a pseudo-terminal.  admin=True types ADMIN and the administrator password at the prompt, so the start setting must be terminal for it."""

    def __init__(self, admin=False, cols=140, rows=43, term="xterm", display=None, settle=2.5):
        self.s = PtySession([os.path.join(SYS, "bin", "sd-solo")], SYS, sd_env(term, display), cols, rows)
        self.cols, self.rows = cols, rows
        self.s.settle(1.5)
        self.s.type(secret("account.pw") + "\r", idle=settle)
        if admin:
            self.s.type("ADMIN\r", idle=0.8)
            self.s.type(secret("admin.pw") + "\r", idle=1.2)

    def lines(self):
        return self.s.screen.lines()

    def line(self, r):
        L = self.lines()
        return L[r].rstrip() if r < len(L) else ""

    def text(self):
        return "\n".join(l.rstrip() for l in self.lines())

    def key(self, name, idle=0.45):
        self.s.type(KEYS[name], idle=idle)

    def typed(self, s, idle=0.8):
        self.s.type(s, idle=idle)

    def click(self, col, rw, idle=0.9):
        self.s.type("%s[<0;%d;%dM%s[<0;%d;%dm" % (E, col + 1, rw + 1, E, col + 1, rw + 1), idle=idle)

    def wheel(self, up, col=60, rw=20, idle=0.6):
        self.s.type("%s[<%d;%d;%dM" % (E, 64 if up else 65, col + 1, rw + 1), idle=idle)

    def style(self, r, c):
        return self.s.screen.style(r, c)

    def find(self, label):
        """(row, column) of a tile's label: the tiles are in the panel (rows 6 to 38), Sign out in the header (rows 1 to 3)."""
        lo, hi = (1, 3) if label == "Sign out" else (6, 38)
        for r, l in enumerate(self.lines()):
            if lo <= r <= hi:
                c = l.find(label)
                if c >= 0:
                    return r, c
        return None

    def focus(self):
        out = []
        for n in ("Editor", "IDE", "Record editor", "Terminal", "Keys", "Add a program", "Menu management", "Bypass programs", "Sign out"):
            p = self.find(n)
            if p and "r" in self.style(p[0], p[1] + 1)[2]:
                out.append(n)
        return out

    def prompt(self):
        return any(l.startswith(":") for l in self.lines())

    def home(self):
        T = self.text()
        return "Everyone" in T and "Terminal" in T and "Sign out" in T

    def alive(self):
        self.s._pump(0.3)
        return not self.s.exited

    def end(self):
        self.s.finish()


def dump(h, n=60):
    say("\n".join("%2d|%s" % (i, l.rstrip()[:140]) for i, l in enumerate(h.lines()) if l.strip())[:n * 150])


def plain(cmds, display=None, timeout=300):
    """A plain session of sduser on a PIPE: the password, TERM, the commands, OFF.  Returns the lines printed after the TERM line, the echoed commands and blank lines left out."""
    body = secret("account.pw") + "\nTERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n"
    say("    > %s" % " | ".join(cmds))
    p = subprocess.Popen([os.path.join(SYS, "bin", "sd-solo")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=SYS, env=sd_env("xterm", display),
                         text=True, errors="replace")
    try:
        out, _ = p.communicate(body, timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        out = (out or "") + "\n:TERM 200,9999\nSESSION TIMED OUT\n"
    out = ANSI.sub("", out or "").split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def adm(*cmds, cwd=None):
    """The administrator's verbs in an INTERNAL session (sandbox-fromtree.py's sess), in the SD system directory unless cwd says another."""
    say("    > [internal] " + " | ".join(cmds))
    r = subprocess.run([sys.executable, TOOL, BOX, "sess", cwd or SYS] + list(cmds), capture_output=True, text=True, errors="replace", timeout=600)
    out = ANSI.sub("", r.stdout + r.stderr).split(":TERM 200,9999", 1)[-1]
    return [ln.rstrip() for ln in out.splitlines() if ln.strip() and not ln.startswith(":")]


def default_file():
    return os.path.join(SYS, "start.default")


def file_word():
    """The word in start.default, or None when the file is absent (the delivered state)."""
    try:
        with open(default_file()) as f:
            return f.read().strip()
    except OSError:
        return None


def arrange(word):
    """Put the system default where a row needs it WITHOUT the verb (the verb has its own rows): None is the delivered state, the file absent."""
    if word is None:
        if os.path.exists(default_file()):
            os.remove(default_file())
    else:
        put(default_file(), word + "\n")


def reg_lines():
    with open(REG) as f:
        lines = f.read().split("\n")
    return lines + [""] * (20 - len(lines))


def viewers_file():
    try:
        with open(os.path.join(SYS, "viewers")) as f:
            return f.read()
    except OSError:
        return None


def audit_size():
    path = os.path.join(SYS, "audit")
    try:
        if not os.path.exists(path):
            with open(path, "ab"):
                pass
        return os.path.getsize(path)
    except OSError:
        return 0


def audit_tail(off):
    try:
        with open(os.path.join(SYS, "audit"), "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def pdfp(name):
    return os.path.join(SYS, "pdf", name)


def mtime(name):
    return int(os.path.getmtime(pdfp(name if name.endswith(".pdf") else name + ".pdf")))


def reset_times():
    for n in DOCS:
        os.utime(pdfp(n), (OLD, OLD))


def touched(name, wait=6.0):
    end = time.time() + wait
    while time.time() < end:
        if mtime(name) > OLD + 1000:
            return True
        time.sleep(0.2)
    return False


def untouched(name, wait=2.0):
    time.sleep(wait)
    return mtime(name) == OLD


def make_docs():
    d = os.path.join(SYS, "pdf")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for n, data in DOCS.items():
        with open(os.path.join(d, n), "wb") as f:
            f.write(data)
    os.symlink("guide-one.pdf", os.path.join(d, "linked.pdf"))
    os.makedirs(os.path.join(d, "adir.pdf"))
    reset_times()


def expected_help():
    """What LOAD.HELP must have written: id -> (title, doc, number of paragraphs), from the shipped files."""
    out = {}
    for n in sorted(os.listdir(HELPSRC)):
        with open(os.path.join(HELPSRC, n), encoding="latin-1") as f:
            lines = f.read().rstrip("\n").split("\n")
        out[n] = (lines[0].rstrip(), lines[1].strip() if len(lines) > 1 else "", len(lines) - 2)
    return out


PROBES = {
    "hlook": ["$internal", "program hlook",
              "   key = field(trim(@sentence), ' ', 4)",                    # RUN bp hlook KEY
              "   call $tk_help('text', key, t, l, d)",
              "   crt 'HT=' : t",
              "   crt 'HD=' : d",
              "   for i = 1 to dcount(l, @fm)",
              "      crt 'HL=' : l<i>",
              "   next i", "end", ""],
    "hids": ["$internal", "program hids",
             "   openpath '%s/context.help' to f else crt 'HIDS no file' ; stop",
             "   select f to 11", "   n = 0", "   loop", "      readnext id from 11 else exit",
             "      read r from f, id then",
             "         crt 'ID=' : id : '|' : r<1> : '|' : r<2> : '|' : (dcount(r, @fm) - 2)",
             "         n += 1", "      end", "   repeat", "   crt 'N=' : n", "end", ""],
    "hadd": ["$internal", "program hadd",
             "   openpath '%s/context.help' to f else crt 'HADD no file' ; stop",
             "   write 'Site note' : @fm : '' : @fm : 'kept by the administrator' to f, 'site.note'",
             "   crt 'HADD done'", "end", ""],
}


def make_probes():
    for nm, src in PROBES.items():
        text = "\n".join(src)
        if "%s" in text:
            text = text % SYS
        put(os.path.join(SYS, "bp", nm), text)
    out = adm("BASIC bp hlook hids hadd")
    if not has(out, r"^Compiled 3 program\(s\) with no errors"):
        bail("the probes did not compile in the system directory:\n" + "\n".join(out[-8:]))


def counts(out):
    """(new, changed, already current, kept) from LOAD.HELP's summary line, or None."""
    for l in out:
        m = re.match(r"^Context help: (\d+) new, (\d+) changed, (\d+) already current, (\d+) added by the administrator and kept$", l)
        if m:
            return tuple(int(x) for x in m.groups())
    return None


def hlook(key):
    """What $tk_help gives for a key, read in the SD system directory's internal session.  Only the administrator's pages (tool.menus, tool.viewers) call it in Solo, so there is no ordinary lane."""
    out = adm("RUN bp hlook " + key)
    t = [l[3:] for l in out if l.startswith("HT=")]
    d = [l[3:] for l in out if l.startswith("HD=")]
    ls = [l[3:] for l in out if l.startswith("HL=")]
    return (t[0] if t else None), (d[0] if d else None), ls, out


def hids():
    out = adm("RUN bp hids")
    recs = {}
    for l in out:
        m = re.match(r"^ID=([^|]*)\|([^|]*)\|([^|]*)\|(\d+)$", l)
        if m:
            recs[m.group(1)] = (m.group(2), m.group(3), int(m.group(4)))
    n = [int(l[2:]) for l in out if re.match(r"^N=\d+$", l)]
    return recs, (n[0] if n else None), out


def start_sandbox():
    global BOX, SYS, REG, ACCT
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-home-solo.py <dir> [--build]")
    BOX = os.path.abspath(args[0])
    SYS = os.path.join(BOX, "sys")
    REG = os.path.join(SYS, "accounts", "sduser")
    ACCT = os.path.join(SYS, "user_accounts", "sduser")
    say("sandbox-home-solo: sandbox %s" % BOX)
    if "--build" in sys.argv:
        if os.path.exists(BOX) and os.listdir(BOX):
            bail("%s is not empty" % BOX)
        r = subprocess.run([sys.executable, TOOL, BOX, "all"], capture_output=True, text=True, errors="replace", timeout=1800)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-home-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(SYS, "bin", "sd-solo")):
        bail("%s holds no built Solo sandbox" % BOX)
    subprocess.run([sys.executable, TOOL, BOX, "start"], capture_output=True, text=True, errors="replace", timeout=300)


def teardown():
    if SYS and os.path.isdir(SYS):
        arrange("terminal")
        try:
            os.remove(os.path.join(SYS, "viewers"))          # the list the pdf rows wrote: a later suite starts with nothing allowed, as delivered
        except OSError:
            pass
    if BOX:
        subprocess.run([sys.executable, TOOL, BOX, "stop"], capture_output=True, text=True, errors="replace", timeout=300)


def sec_setup():
    say("\n--- setup and controls")
    arrange("terminal")
    out = plain(["WHO.AM.I"])
    adm_flag = re.search(r"Admin\?\s*:\s*(\w+)", "\n".join(out))
    row("the plain session is a session of sduser and is NOT an administrator (WHO.AM.I says Admin? %s)" % (adm_flag.group(1) if adm_flag else "-"),
        has(out, r"Account\s*:\s*sduser") and bool(adm_flag) and adm_flag.group(1) == "No", repr(out[:4]))
    if not (adm_flag and adm_flag.group(1) == "No"):
        bail("the ordinary session is privileged; its refusals prove nothing")
    out = adm("set.os.access")
    row("the OS switches of the account are OFF (the stage's setting): SH no, OS.EXECUTE no, so pdf below is the bypass and not the account's own right", has(out, r"SH no, OS\.EXECUTE no"), repr(out[-2:]))
    h = H()
    ok = h.prompt() and not h.home()
    h.end()
    row("the sandbox starts at the prompt when start.default says terminal (the control every other suite relies on)", ok, "")
    make_docs()
    make_probes()


def sec_start():
    say("\n--- where a session starts: the system default and a piped session")
    arrange(None)
    h = H()
    ok = h.home()
    if not ok:
        dump(h)
    row("the delivered default is menu: with no start.default file a session on a terminal is given the home screen", ok, "")
    h.end()
    h = H()
    T = h.text()
    row("...it is the ORDINARY page: the group is 'My tools' (not 'Tools'), the identity row says 'sduser @ sduser' and the right end of row 0 says 'home  sduser@sduser'",
        "My tools" in T and h.line(2).strip().startswith("sduser @ sduser") and h.line(0).endswith("home  sduser@sduser"), repr((h.line(0)[-30:], h.line(2)[:30])))
    h.end()
    out = plain(["who.am.i"])
    row("a PIPED session (menu by default) is not given the screen: its command runs (Account : sduser) and no tile is drawn", has(out, r"Account\s*:\s*sduser") and not has(out, r"My tools|Everyone"), repr(out[:6]))
    out = plain(["home"])
    row("HOME in a piped session says it needs a terminal (11863) and does not read the input as keys", has(out, r"^home needs a terminal$"), repr(out[:4]))
    a0 = audit_size()
    out = adm("set.start.default terminal")
    row("SET.START.DEFAULT terminal (administrator): says so (11871), and the file holds the word", has(out, r"^Accounts with no start setting of their own start at: terminal$") and file_word() == "terminal", repr(out[:3]))
    row("...and audited in lower case:  set.start.default terminal", "set.start.default terminal" in audit_tail(a0), repr(audit_tail(a0)[-160:]))
    h = H()
    row("with the default at terminal a session starts at the prompt: a ':' on the screen and no tile", h.prompt() and not h.home(), "")
    h.end()
    out = adm("set.start.default terminal")
    row("the same default again says it is already that and changes nothing (11873)", has(out, r"^The system default start is already terminal; nothing changed$"), repr(out[:3]))
    out = adm("set.start.default")
    row("without a word it says what it is now (11871: terminal)", has(out, r"start at: terminal$"), repr(out[:3]))
    out = adm("set.start.default maybe")
    row("a word that is neither is the usage (11870) and changes nothing", has(out, r"^set\.start\.default \{menu \| terminal\}$") and file_word() == "terminal", repr(out[:3]))
    out = adm("set.start.default menu terminal")
    row("two words are the usage too", has(out, r"^set\.start\.default \{menu \| terminal\}$") and file_word() == "terminal", repr(out[:3]))
    out = plain(["set.start.default menu"])
    row("an ORDINARY session cannot run it: 'Command requires administrator privileges' (2001), and the file is unchanged", has(out, r"Command requires administrator privileges") and file_word() == "terminal", repr(out[:3]))
    h = H(admin=True)
    h.typed("set.start.default menu\r", idle=1.5)
    row("ADMIN typed at the prompt of a pty session, then SET.START.DEFAULT menu: the file holds menu", file_word() == "menu" and "start at: menu" in h.text(), repr((file_word(), h.text()[-200:])))
    h.end()
    h = H()
    row("...and the next session is given the home screen", h.home(), "")
    h.end()


def sec_page():
    say("\n--- the page, the focus, the keys")
    arrange("menu")
    h = H()
    T = h.text()
    if not h.home():
        dump(h)
        bail("the home screen never drew, so no row below can be believed")
    row("the page: group 'My tools' with Editor, IDE and Record editor; group 'Everyone' with Terminal and Keys; Sign out in the header",
        all(w in T for w in ("My tools", "Editor", "IDE", "Record editor", "Everyone", "Terminal", "Keys", "Sign out")), "")
    row("...and NO Switch account (Solo has one account), no Menu management and no Bypass programs (the administrator's), and no 'My programs' group while set.pins is off",
        not any(w in T for w in ("Switch account", "Menu management", "Bypass programs", "My programs")), T[:300])
    row("the identity (row 2) and the date and time (row 3): 'sduser @ sduser' and a line like 'Friday 23 Oct 2026  -  09:03'",
        h.line(2).strip().startswith("sduser @ sduser") and re.match(r"^\s+[A-Z][a-z]+day \d{1,2} [A-Z][a-z]{2} \d{4}  -  \d\d:\d\d", h.line(3)) is not None, repr((h.line(2)[:40], h.line(3)[:50])))
    row("the foot: the hint line (row 39), the status line [Home] (row 40), the border (row 41), the function keys (row 42: Enter start, F5 refresh, F10 menu, ^Q sign out)",
        "arrows move" in h.line(39) and h.line(40).startswith("[Home]") and set(h.line(41)) == {"-"} and h.line(42) == "Enter start  F5 refresh  F10 menu  ^Q sign out", repr((h.line(39)[:30], h.line(40), h.line(42))))
    row("row 0: the menu bar File Go View AI Help at the left, 'home  sduser@sduser' at the right", h.line(0).startswith(" File  Go  View  AI  Help") and h.line(0).endswith("home  sduser@sduser"), repr(h.line(0)))
    row("the focus starts on the first tile of the page (Editor): one tile in reverse video", h.focus() == ["Editor"], repr(h.focus()))
    seq = [("right", "IDE"), ("right", "Record editor"), ("left", "IDE"), ("down", "Terminal"), ("right", "Keys"), ("left", "Terminal"), ("up", "Editor"), ("down", "Terminal"), ("home", "Editor"),
           ("end", "Keys"), ("home", "Editor"), ("tab", "IDE"), ("btab", "Editor"), ("btab", "Sign out"), ("tab", "Editor")]
    bad = []
    for k, want in seq:
        h.key(k)
        if h.focus() != [want]:
            bad.append("%s -> %r (wanted %s)" % (k, h.focus(), want))
    row("the arrow keys move to the nearest tile in that direction, Home and End go to the first and last of the panel, Tab and Back-tab go in reading order (Back-tab from the first goes to Sign out)",
        not bad, "; ".join(bad))
    h.key("up")
    row("up from the first row goes to the header: Sign out has the focus", h.focus() == ["Sign out"], repr(h.focus()))
    h.key("pgdn")
    row("Page Down from a header tile does nothing (it has no group)", h.focus() == ["Sign out"], repr(h.focus()))
    h.key("home")
    h.key("pgdn")
    row("Page Down from the first group goes to the first tile of the next one (Terminal); Page Up goes back (Editor)", h.focus() == ["Terminal"], repr(h.focus()))
    h.key("pgup")
    row("...Page Up: Editor", h.focus() == ["Editor"], repr(h.focus()))
    h.typed("k", idle=0.45)
    row("a letter jumps to the next tile whose label begins with it: k - Keys", h.focus() == ["Keys"], repr(h.focus()))
    h.typed("r", idle=0.45)
    row("...r - Record editor", h.focus() == ["Record editor"], repr(h.focus()))
    h.key("f5", idle=0.8)
    row("F5 builds the page again: the page is the same and the status line says so", h.home() and "page built again" in h.line(40) and h.focus() == ["Editor"], repr((h.line(40), h.focus())))
    h.key("f10", idle=0.8)
    row("F10 opens the menu bar: File's drop-down shows Sign out with ^Q", "Sign out" in h.line(1) and "^Q" in h.line(1), repr(h.line(1)))
    h.key("esc", idle=0.6)
    row("Esc closes the menu and the page is whole again", h.home() and "Sign out" not in h.line(1), repr(h.line(1)))
    h.end()

    say("\n--- the administrator's page (ADMIN, then HOME at the prompt)")
    arrange("terminal")
    h = H(admin=True)
    h.typed("home\r", idle=3.0)
    T = h.text()
    row("the administrator's page: group 'Tools' (not 'My tools'), the System group with Menu management and Bypass programs, the identity 'administrator', row 0 'home  administrator'",
        h.home() and "Tools" in T and "My tools" not in T and "System" in T and "Menu management" in T and "Bypass programs" in T and h.line(2).strip().startswith("administrator")
        and h.line(0).endswith("home  administrator"), repr((h.line(0)[-24:], h.line(2)[:30], T[:300])))
    row("...and the focus starts on the first tile of the page (Menu management)", h.focus() == ["Menu management"], repr(h.focus()))
    h.end()

    say("\n--- no colour: a vt100")
    h = H(term="vt100")
    h.typed("TERM vt100\r", idle=0.8)
    h.typed("home\r", idle=3.0)
    T = h.text()
    p = h.find("Editor")
    row("on a terminal with no colour every tile is boxed: the corners and the lines are on the screen (LC_ALL=C: + - |), and the focused tile (Editor) is in reverse video",
        h.home() and "+-------------------+" in T and "|  [=]" in T and p is not None and "r" in h.style(p[0], p[1] + 1)[2], repr((h.line(7)[:30], p)))
    h.end()


def sec_tiles():
    say("\n--- the tiles start commands, and the screen comes back")
    arrange("menu")
    h = H()
    h.key("down")
    h.key("enter", idle=1.5)
    T = h.text()
    row("Terminal (Enter): the screen is given back - a banner 'Terminal - type exit to return to the home screen' and the ordinary prompt, no tile",
        "Terminal - type exit to return to the home screen" in T and h.prompt() and not h.home(), T[:200])
    h.typed("who.am.i\r", idle=1.2)
    row("...the prompt is the ordinary command processor, in the account the screen was in: WHO.AM.I answers Account : sduser", re.search(r"Account\s*:\s*sduser", h.text()) is not None, h.text()[-300:])
    h.typed("exit\r", idle=1.8)
    row("EXIT comes back to the home screen", h.home(), h.text()[-300:])
    h.key("down")
    h.key("enter", idle=1.5)
    h.typed("exit\r", idle=1.8)
    row("...and again: the flag stays set for the rest of the session", h.home(), h.text()[-300:])
    h.key("home")
    h.key("enter", idle=2.0)
    T = h.text()
    row("Editor (Enter): runs sed - the screen is closed and SED asks 'File name?' at the prompt", "File name?" in T and not h.home(), T[-200:])
    h.typed("\r", idle=1.5)
    row("an empty answer ends SED and the home screen is drawn again", h.home(), h.text()[-300:])
    h.key("right")
    h.key("enter", idle=2.5)
    T = h.text()
    row("IDE (Enter): the IDE takes the terminal (its menu bar is on the screen) and not the home screen", "File" in h.line(0) and "Go" in h.line(0) and "Everyone" not in T, repr(h.line(0)[:60]))
    h.typed("\x11", idle=1.2)
    row("Ctrl-Q ends the IDE and the home screen is drawn again, with the IDE tile still the one selected (not the first tile)", h.home() and h.focus() == ["IDE"], repr((h.home(), h.focus())))
    h.key("end")
    h.key("enter", idle=1.8)
    row("Keys (Enter): tool.keys is on the screen", "Last keys" in h.text(), h.text()[:200])
    h.typed("\x11", idle=1.2)
    row("...Ctrl-Q ends it and the home screen is drawn again", h.home(), h.text()[-200:])
    h.end()

    say("\n--- sign out")
    h = H()
    h.key("ctrl-q", idle=0.8)
    T = h.text()
    row("Ctrl-Q asks 'Sign out of SD?' with two buttons, Sign out and Cancel", SIGNOUT_ASK in T and "Sign out" in T and "Cancel" in T, T[-400:])
    h.key("enter", idle=0.8)
    row("Enter takes the default button, Cancel: the box closes, the home screen is whole and the session is alive", h.home() and SIGNOUT_ASK not in h.text() and h.alive(), "")
    h.key("ctrl-q", idle=0.8)
    h.typed("s", idle=2.0)
    row("the letter S takes Sign out: the session ends", not h.alive(), h.text()[-200:])
    h.end()
    h = H()
    h.key("btab")
    h.key("enter", idle=0.8)
    row("the Sign out tile (reached with Back-tab) asks the same question", SIGNOUT_ASK in h.text(), "")
    h.key("esc", idle=0.5)
    row("Esc is Cancel", SIGNOUT_ASK not in h.text() and h.alive(), "")
    h.end()

    say("\n--- EXIT where the home screen was not used")
    arrange("terminal")
    h = H()
    row("with the default at terminal the session starts at the prompt", h.prompt() and not h.home(), h.text()[-200:])
    h.typed("exit\r", idle=2.0)
    row("EXIT at a prompt that never came from the home screen ends the session, as QUIT does", not h.alive(), h.text()[-200:])
    h.end()
    h = H()
    h.typed("home\r", idle=2.0)
    row("HOME typed at the prompt opens the screen (an account that starts at the terminal can still have it)", h.home(), h.text()[-200:])
    h.key("down")
    h.key("enter", idle=1.5)
    row("its Terminal tile gives the prompt back", h.prompt() and not h.home(), "")
    h.end()
    h = H()
    h.typed("menu\r", idle=2.5)
    row("MENU at the prompt opens the full-screen menu: the home screen, with its Terminal and Sign out tiles", h.home(), h.text()[-300:])
    h.end()

    say("\n--- the mouse")
    arrange("menu")
    h = H()
    p = h.find("IDE")
    h.click(p[1] + 1, p[0], idle=2.5)
    row("a click on the IDE tile starts the IDE", "File" in h.line(0) and "Everyone" not in h.text(), repr(h.line(0)[:50]))
    h.typed("\x11", idle=1.2)
    p = h.find("Sign out")
    h.click(p[1] + 1, p[0])
    row("a click on the Sign out tile (in the header) asks 'Sign out of SD?'", SIGNOUT_ASK in h.text(), "")
    h.key("esc", idle=0.5)
    h.click(1, 0)
    row("a click on the menu bar opens the menu under it (File)", "Sign out" in h.line(1), repr(h.line(1)))
    h.key("esc", idle=0.5)
    fb = h.focus()
    h.wheel(False)
    row("the wheel on a page that fits changes nothing: the page is whole and the focus has not moved", h.home() and h.focus() == fb and h.line(6).strip().startswith("My tools"), repr((fb, h.focus())))
    h.end()

    say("\n--- a window that is too small")
    h = H(cols=100, rows=30)
    T = h.text()
    row("a 100 by 30 window is not handed to the screen: no tile is drawn, the library's size message is shown and the prompt is there", not h.home() and h.prompt() and re.search(r"140", T) is not None, T[-400:])
    h.typed("who.am.i\r", idle=1.2)
    row("...and the session works", re.search(r"Account\s*:\s*sduser", h.text()) is not None, h.text()[-200:])
    h.end()


def sec_tileoff():
    say("\n--- SET.TILE: a tile off for the account (field 17 of the register record)")
    arrange("menu")
    out = adm("set.tile")
    row("SET.TILE alone, with nothing off: 'Every tile is on' (11882)", has(out, r"^Every tile is on$"), repr(out[:3]))
    a0 = audit_size()
    out = adm("set.tile sduser editor off")
    row("set.tile sduser editor off: 'Tile editor is now off for sduser' (11875), and field 17 of the register record is editor on the disk", has(out, r"^Tile editor is now off for sduser$") and reg_lines()[16].strip() == "editor", repr((out[:3], reg_lines()[16])))
    row("...audited in lower case:  set.tile off tile=editor account=sduser", "set.tile off tile=editor account=sduser" in audit_tail(a0), repr(audit_tail(a0)[-160:]))
    out = adm("set.tile sduser editor off")
    row("the same again: 'Tile editor was already off for sduser; nothing changed' (11877)", has(out, r"^Tile editor was already off for sduser; nothing changed$"), repr(out[:3]))
    out = adm("set.tile")
    row("SET.TILE alone lists it: 'Tiles off for sduser: editor' (11880)", has(out, r"^Tiles off for sduser: editor$"), repr(out[:3]))
    h = H()
    T = h.text()
    row("the page has no Editor tile (the first is now IDE, which has the focus), and the other tiles are there", h.home() and "Editor" not in T and h.focus() == ["IDE"] and all(w in T for w in ("IDE", "Record editor", "Terminal", "Keys", "Sign out")), repr((h.focus(), T[:300])))
    h.end()
    for cmd, rx, why in (("set.tile sduser signout off", r"^Sign out cannot be turned off: a person must always be able to leave$", "Sign out cannot be turned off (11878)"),
                         ("set.tile sduser Bad_Name off", r"^bad_name is not a tile name: lower case letters, digits, dots and hyphens, 32 at most$", "a name with an underscore is refused (11881)"),
                         ("set.tile sduser editor maybe", r"^set\.tile account tile \{on \| off\}; set\.tile alone lists what is off$", "a state that is neither is the usage (11874)"),
                         ("set.tile nobody editor off", r"^Account name is invalid$", "an account that is not there is refused (6003)"),
                         ("set.tile sdsys editor off", r"^Account name is invalid$", "sdsys is refused (2202)")):
        out = adm(cmd)
        row("%s: %s" % (cmd, why), has(out, rx), repr(out[:3]))
    out = adm("set.tile sduser zzother off")
    row("an id that is not a standard tile is accepted and said not to be (11883)", has(out, r"^Tile zzother is now off for sduser$") and has(out, r"^zzother is not a standard tile; it applies only to a tile of that name in a page record$"), repr(out[:4]))
    out = adm("set.tile sduser zzother on")
    row("...and it is turned on again (11876)", has(out, r"^Tile zzother is now on for sduser$"), repr(out[:3]))
    out = plain(["set.tile sduser editor on"])
    row("an ORDINARY session cannot run it: 'Command requires administrator privileges', and the tile is still off", has(out, r"Command requires administrator privileges") and reg_lines()[16].strip() == "editor", repr((out[:3], reg_lines()[16])))
    out = adm("set.tile sduser editor on")
    row("set.tile sduser editor on: 'Tile editor is now on for sduser' (11876), and field 17 is empty", has(out, r"^Tile editor is now on for sduser$") and reg_lines()[16].strip() == "", repr((out[:3], reg_lines()[16])))
    out = adm("set.tile sduser terminal off")
    h = H()
    T = h.text()
    row("with Terminal off the page has no Terminal tile and the account's Keys tile is still there", "Everyone" in T and "Sign out" in T and "Terminal" not in T and "Keys" in T and "Editor" in T, repr(T[:300]))
    h.end()
    h = H(cols=100, rows=30)
    time.sleep(3.0)
    row("with Terminal off a window too small for the screen does NOT give the prompt: the session is ended (!home_entry signs the person out)", not h.alive(), h.text()[-300:])
    h.end()
    adm("set.tile sduser terminal on")
    h = H(cols=100, rows=30)
    time.sleep(3.0)
    row("(control) with Terminal on the same window gives the prompt and the session stays", h.alive() and h.prompt(), h.text()[-200:])
    h.end()
    row("every tile is on again (the register field is empty)", reg_lines()[16].strip() == "", repr(reg_lines()[16]))

    say("\n--- SET.PINS: the account's own programs")
    out = adm("set.pins")
    row("SET.PINS alone says it may not, as delivered: 'Account sduser may add its own programs to the home screen: no' (11885)", has(out, r"^Account sduser may add its own programs to the home screen: no$"), repr(out[:3]))
    out = plain(["my.menu"])
    row("MY.MENU in an account that is not allowed says so (11886) and draws nothing", has(out, r"^The administrator has not allowed this account to add its own programs to the home screen$"), repr(out[:3]))
    a0 = audit_size()
    out = adm("set.pins on")
    row("set.pins on: says yes (11885), field 18 of the register record is yes on the disk, audited in lower case", has(out, r"may add its own programs to the home screen: yes$") and reg_lines()[17].strip() == "yes"
        and "set.pins on account=sduser" in audit_tail(a0), repr((out[:3], reg_lines()[17], audit_tail(a0)[-120:])))
    out = adm("set.pins on")
    row("the same again: 'Own programs for sduser were already on; nothing changed' (11931)", has(out, r"^Own programs for sduser were already on; nothing changed$"), repr(out[:3]))
    h = H()
    T = h.text()
    row("the page has a 'My programs' group with an 'Add a program' tile, between the standard tools and Everyone", h.home() and "My programs" in T and "Add a program" in T and T.index("My tools") < T.index("My programs") < T.index("Everyone"), repr(T[:400]))
    h.end()
    out = adm("set.pins maybe")
    row("a word that is neither is the usage (11930)", has(out, r"^set\.pins \{on \| off\}"), repr(out[:3]))
    out = plain(["set.pins off"])
    row("an ORDINARY session cannot run it: 'Command requires administrator privileges', and the permission is still yes", has(out, r"Command requires administrator privileges") and reg_lines()[17].strip() == "yes", repr((out[:3], reg_lines()[17])))
    out = adm("set.pins off")
    row("set.pins off: says no, field 18 is 'no' on the disk", has(out, r"may add its own programs to the home screen: no$") and reg_lines()[17].strip() == "no", repr((out[:3], reg_lines()[17])))
    h = H()
    row("...and the 'My programs' group is gone from the page", h.home() and "My programs" not in h.text(), "")
    h.end()


def sec_help():
    say("\n--- the context help: the file context.help of the SD system directory (LOAD.HELP, $tk_help)")
    expect = expected_help()
    n = len(expect)
    row("the stage loaded the help: the file context.help is in the SD system directory (sys/)", os.path.exists(os.path.join(SYS, "context.help")), repr(sorted(os.listdir(SYS))[:8]))
    recs, cnt, out = hids()
    row("the records ARE the shipped files: the same %d ids, and each one's title, document and number of paragraphs" % n, recs == expect and cnt == n, repr((sorted(set(expect) ^ set(recs)), cnt, out[-3:])))
    out = plain(["load.help"])
    row("an ORDINARY session cannot run LOAD.HELP: 'Command requires administrator privileges'", has(out, r"Command requires administrator privileges"), repr(out[:3]))
    out = adm("load.help")
    row("a second LOAD.HELP changes nothing: 0 new, 0 changed, %d already current, 0 kept (11839)" % n, counts(out) == (0, 0, n, 0), repr(out[-4:]))
    pins = os.path.join(SYS, "helptext", "tool.menus.pins")
    with open(pins, encoding="latin-1") as f:
        src = f.read()
    with open(pins, "w", encoding="latin-1") as f:
        f.write(src.replace("Programs of the account's own", "Own programs (edited)", 1))
    out = adm("load.help")
    t, d, ls, o2 = hlook("tool.menus.pins")
    row("a changed shipped file is written (0 new, 1 changed, %d already current) and the title read back is the new one" % (n - 1), counts(out) == (0, 1, n - 1, 0) and t == "Own programs (edited)", repr((out[-2:], t)))
    with open(pins, "w", encoding="latin-1") as f:
        f.write(src)
    adm("load.help")
    adm("RUN bp hadd")
    out = adm("load.help")
    t, d, ls, o2 = hlook("site.note")
    row("a record the administrator added under an id that is not shipped is KEPT (1 kept, nothing else changed) and still read back", counts(out) == (0, 0, n, 1) and t == "Site note", repr((out[-2:], t, ls)))
    for bad, text in (("Bad_Name", "A title\n\ntext\n"), ("no.title", "\n\ntext\n"), (".hidden", "A title\n\ntext\n")):
        with open(os.path.join(SYS, "helptext", bad), "w") as f:
            f.write(text)
    out = adm("load.help")
    recs, cnt, o2 = hids()
    row("a file whose name is not a key (a capital, an underscore, a leading dot) or that has no title is SKIPPED and named (11840), and is not in the file",
        has(out, r"^Skipped Bad_Name in the help text directory: not a key$") and has(out, r"^Skipped \.hidden in the help text directory: not a key$")
        and has(out, r"^Skipped no\.title in the help text directory: has no title$") and not ({"Bad_Name", "bad_name", ".hidden", "no.title"} & set(recs)), repr(out[-5:]))
    for bad in ("Bad_Name", "no.title", ".hidden"):
        os.remove(os.path.join(SYS, "helptext", bad))
    t, d, ls, out = hlook("tool.menus.pins")
    row("$tk_help gives the title, the document (06-administrator-commands) and the paragraphs of the shipped file", t == "Programs of the account's own" and d == "06-administrator-commands" and len(ls) == 3
        and ls[0].startswith("Off as delivered."), repr((t, d, ls[:1], out[-3:])))
    t, d, ls, out = hlook("Tool.Menus.Pins")
    row("a key is folded to lower case", t == "Programs of the account's own", repr(t))
    t, d, ls, out = hlook("tool.menus.nothing")
    row("a key with no record: the title 11830 and the line 11831 naming the key, not an error", t == "No help has been written for this yet" and any("has no record tool.menus.nothing" in l for l in ls), repr((t, ls)))
    t, d, ls, out = hlook("../etc/passwd")
    row("a key that is not a key (a slash) is not looked up at all: the same words, and no text of any file", t == "No help has been written for this yet" and not any("root:" in l for l in ls) and any("has no record" in l for l in ls), repr((t, ls)))
    os.rename(os.path.join(SYS, "context.help"), os.path.join(SYS, "context.help.away"))
    t, d, ls, out = hlook("tool.menus.pins")
    row("with the file gone $tk_help answers in words (11830 and 11832), not with an error", t == "No help has been written for this yet" and any("Help is not installed here" in l for l in ls), repr(out[-3:]))
    os.rename(os.path.join(SYS, "context.help.away"), os.path.join(SYS, "context.help"))


def sec_pdf():
    say("\n--- pdf: the document list, the viewer list and the bypass")
    reset_times()
    out = plain(["pdf"])
    row("PDF alone lists the documents of the pdf directory, sorted and without the .pdf: regular files with a lower case name only (not Upper, notes.txt, the link or the directory)",
        has(out, r"^Documents \(%d\); pdf name opens one:$" % len(LISTED)) and [l.strip() for l in out if l.startswith("  ")] == LISTED, repr(out))
    out = plain(["pdf guide-one"])
    row("with no viewer allowed, PDF says so (11846) and starts nothing", has(out, r"^No viewer has been allowed for documents\.  The administrator names one with set\.viewer\.$") and untouched("guide-one", 1.0), repr(out))
    out = plain(["set.viewer"])
    row("an ORDINARY session cannot run SET.VIEWER: 'Command requires administrator privileges'", has(out, r"Command requires administrator privileges"), repr(out[:3]))
    out = adm("set.viewer")
    row("SET.VIEWER alone says nothing is allowed (11896)", has(out, r"^No program is allowed to be started without os\.execute$"), repr(out))
    for cmd, rx in (("set.viewer add pdf nosuchreader", r"^nosuchreader was not found in /usr/bin, /usr/local/bin or /bin$"),
                    ("set.viewer add pdf /tmp/anything", r"^The viewer /tmp/anything cannot be used: it is under /tmp, which users can write$"),
                    ("set.viewer add pdf /etc/passwd", r"^The viewer /etc/passwd cannot be used: it is not executable by everyone$"),
                    ("set.viewer add pdf /usr/bin/../bin/touch", r"^The viewer /usr/bin/\.\./bin/touch cannot be used: its path has \.\. in it$"),
                    ("set.viewer add pdf relative/touch", r"^relative/touch was not found in /usr/bin, /usr/local/bin or /bin$"),
                    ("set.viewer add npdf touch", r"^npdf is not a purpose that can be set; only pdf can$"),
                    ("set.viewer add pdf", r"^set\.viewer \{add \| remove\} pdf program; set\.viewer alone says which programs are allowed$"),
                    ("set.viewer remove pdf touch", r"^The program touch was not allowed for pdf; nothing changed$")):
        out = adm(cmd)
        row("%s: %s" % (cmd, rx.strip("^$")[:70]), has(out, rx), repr(out[-3:]))
    row("...and none of these wrote the list (it is still empty or absent)", viewers_file() in (None, ""), repr(viewers_file()))
    if os.path.exists("/usr/bin/sudo") and os.stat("/usr/bin/sudo").st_mode & 0o4000:
        out = adm("set.viewer add pdf /usr/bin/sudo")
        row("a setuid program is refused (sudo)", has(out, r"cannot be used: it has the setuid, setgid or sticky bit set"), repr(out[-3:]))

    a0 = audit_size()
    out = adm("set.viewer add pdf touch")
    row("SET.VIEWER add pdf touch finds /usr/bin/touch, tests it and allows it (11891)", has(out, r"^The program /usr/bin/touch is now allowed for pdf$"), repr(out[-3:]))
    row("...the list is the file viewers: one line, 'pdf /usr/bin/touch', mode 0644", viewers_file() == "pdf /usr/bin/touch\n" and (os.stat(os.path.join(SYS, "viewers")).st_mode & 0o777) == 0o644, repr((viewers_file(),)))
    row("...and audited:  set.viewer add purpose=pdf program=/usr/bin/touch", "set.viewer add purpose=pdf program=/usr/bin/touch" in audit_tail(a0), repr(audit_tail(a0)[-200:]))
    out = adm("set.viewer add pdf touch")
    row("adding it again changes nothing (11893)", has(out, r"^The program /usr/bin/touch was already allowed for pdf; nothing changed$"), repr(out[-3:]))
    out = adm("set.viewer")
    row("SET.VIEWER alone lists it (11895)", has(out, r"^Allowed for pdf: /usr/bin/touch$"), repr(out))

    reset_times()
    out = plain(["pdf guide-one"])
    row("an allowed viewer but NO DISPLAY: PDF refuses in words (11847) and starts nothing", has(out, r"^This session has no graphical display") and untouched("guide-one", 1.0), repr(out))
    a0 = audit_size()
    out = plain(["pdf guide-one"], display=":99")
    row("with a DISPLAY, in the ORDINARY session whose os.execute switch is OFF: PDF says it opened guide-one with /usr/bin/touch (11848)", has(out, r"^Opened guide-one with /usr/bin/touch$"), repr(out))
    row("...and the program REALLY ran, with that document: its modification time moved (the evidence), and the others did not", touched("guide-one") and mtime("guide-two") == OLD and mtime("01-accounts-and-security") == OLD,
        repr((mtime("guide-one"), mtime("guide-two"))))
    row("...one audit line:  pdf open file=guide-one viewer=/usr/bin/touch", "pdf open file=guide-one viewer=/usr/bin/touch" in audit_tail(a0), repr(audit_tail(a0)[-200:]))
    reset_times()
    for cmd, rx in (("pdf ../etc/hostname", r"^\.\./etc/hostname is not a document name$"), ("pdf x;id", r"^x;id is not a document name$"), ("pdf .hidden", r"^\.hidden is not a document name$"),
                    ("pdf Upper", r"^There is no document upper; pdf alone lists them$"), ("pdf linked", r"^There is no document linked; pdf alone lists them$"),
                    ("pdf adir", r"^There is no document adir; pdf alone lists them$"), ("pdf notes", r"^There is no document notes; pdf alone lists them$"),
                    ("pdf guide-one guide-two", r"^pdf \{name\}; pdf alone lists the documents$")):
        out = plain([cmd], display=":99")
        row("%s: %s" % (cmd, rx.strip("^$")[:60]), has(out, rx), repr(out[-3:]))
    row("...and none of them started a program", untouched("guide-one", 1.0) and untouched("guide-two", 0.1) and untouched("01-accounts-and-security", 0.1), repr([mtime(n) for n in DOCS if n.endswith(".pdf")]))
    out = plain(["pdf guide-two.pdf"], display=":99")
    row("a name with .pdf on it is taken as the document (guide-two.pdf opens guide-two)", has(out, r"^Opened guide-two with /usr/bin/touch$") and touched("guide-two"), repr(out))
    reset_times()

    bad = os.path.join(BOX, "fakeviewer")
    put(bad, "#!/bin/sh\nexit 0\n")
    os.chmod(bad, 0o755)
    put(os.path.join(SYS, "viewers"), "pdf %s\n" % bad)
    out = plain(["pdf guide-one"], display=":99")
    row("a list changed by hand to name a program that fails the test (not owned by root, under /tmp): PDF refuses (11849) and starts nothing",
        has(out, r"^The viewer .*fakeviewer cannot be used: it is under /tmp, which users can write$") and untouched("guide-one", 1.0), repr(out))
    put(os.path.join(SYS, "viewers"), "# a comment\n\npdf %s\npdf /usr/bin/touch\n" % bad)
    out = plain(["pdf guide-one"], display=":99")
    row("...but the FIRST program on the list that passes is the one started (a bad first line, then touch)", has(out, r"^Opened guide-one with /usr/bin/touch$") and touched("guide-one"), repr(out))
    put(os.path.join(SYS, "viewers"), "pdf /usr/bin/touch\n")
    reset_times()
    shutil.rmtree(pdfp("adir.pdf"))
    os.rename(os.path.join(SYS, "pdf"), os.path.join(SYS, "pdf.away"))
    out = plain(["pdf"])
    row("no pdf directory: PDF says there are no documents (11888)", has(out, r"^There are no documents: there is no pdf directory in the install directory, or it holds none$"), repr(out))
    os.rename(os.path.join(SYS, "pdf.away"), os.path.join(SYS, "pdf"))

    say("\n--- docs.install")
    src = os.path.join(BOX, "docsrc")
    os.makedirs(src, exist_ok=True)
    for n, data in (("good-one.pdf", b"%PDF-1.5\ngood\n"), ("fake.pdf", b"just text\n"), ("Bad.pdf", b"%PDF-1.4\nbad\n"), ("text.txt", b"%PDF-1.4\n")):
        with open(os.path.join(src, n), "wb") as f:
            f.write(data)
    out = plain(["docs.install " + src])
    row("an ORDINARY session cannot run DOCS.INSTALL: 'Command requires administrator privileges'", has(out, r"Command requires administrator privileges"), repr(out[:3]))
    out = adm("docs.install " + src)
    dest = pdfp("good-one.pdf")
    row("DOCS.INSTALL copies the one good file and names the two it skipped (a capital in the name; no %PDF- at the start); a .txt is not looked at",
        has(out, r"^Copied 1 document\(s\) into the pdf directory; skipped 2$") and has(out, r"^Skipped Bad\.pdf: the name is not lower case") and has(out, r"^Skipped fake\.pdf: it does not start with %PDF-$"), repr(out[-4:]))
    row("...the copy is on the disk, the same bytes, mode 0644; the others are not there", os.path.exists(dest) and open(dest, "rb").read() == b"%PDF-1.5\ngood\n" and (os.stat(dest).st_mode & 0o777) == 0o644
        and not os.path.exists(pdfp("fake.pdf")) and not os.path.exists(pdfp("Bad.pdf")) and not os.path.exists(pdfp("text.txt")), repr(sorted(os.listdir(os.path.join(SYS, "pdf")))))
    out = plain(["pdf"])
    row("...and PDF lists it", has(out, r"^  good-one$"), repr(out))
    out = adm("docs.install /tmp/../etc")
    row("a path with .. in it is refused (11721) and nothing is read", has(out, r"^The directory /tmp/\.\./etc cannot be read, or is not a plain path"), repr(out[-3:]))
    out = adm("docs.install /nonexistent-directory-for-docs")
    row("a directory that is not there is refused (11721)", has(out, r"^The directory /nonexistent-directory-for-docs cannot be read"), repr(out[-3:]))
    os.remove(dest)


def sec_pages():
    say("\n--- tool.menus: the [?] buttons, the help box, a tile turned off and on through the page")
    arrange("terminal")
    reset_times()
    out = plain(["tool.menus"])
    row("an ORDINARY session cannot reach tool.menus: 'Command requires administrator privileges' (11800 or 2001)", has(out, r"Command requires administrator privileges|is for the administrator only"), repr(out[:3]))
    h = H(admin=True, display=":99")
    h.typed("tool.menus\r", idle=3.0)
    T = h.text()
    if "What this means" not in T:
        dump(h)
        bail("tool.menus never drew its page, so no row below can be believed")
    marks = [(r, m.start()) for r in range(2, 10) for m in re.finditer(r"\[\?\]", h.line(r))]
    right = [m for m in marks if m[1] > 70]
    left = [m for m in marks if m[1] < 70]
    row("a [?] at the end of each of the eight rows of the Menu box (Starts in, May add own programs, the six tiles) and one at the head of the Accounts list", len(right) == 8 and len(left) == 1, repr(marks))
    row("the function-key row says F1 help", "F1 help" in h.line(42), repr(h.line(42)))
    h.key("f1", idle=1.2)
    T = h.text()
    row("F1 in the Accounts box shows the help: the title, its first paragraph, and the buttons Documentation and Close", "The account" in T and "The account of this installation, sduser" in T and "Documentation" in T and "Close" in T, T[-700:])
    h.key("esc", idle=0.8)
    T = h.text()
    row("Esc closes it: the box is gone and the page is as it was", "The account of this installation" not in T and "What this means" in T, T[-300:])
    h.key("tab", idle=0.6)
    h.typed("?", idle=1.2)
    T = h.text()
    row("'?' on the first row of the Menu box (where a session starts) shows that setting's help", "Where a session starts" in T and "Chooses what you see when you sign on" in T, T[-500:])
    h.key("esc", idle=0.8)
    h.key("down", idle=0.5)
    h.key("f1", idle=1.2)
    T = h.text()
    row("F1 on the next row (programs of its own) shows that one", "Programs of the account's own" in T and "Off as delivered." in T, T[-500:])
    h.key("esc", idle=0.8)
    for _ in range(4):
        h.key("down", idle=0.4)
    h.key("f1", idle=1.2)
    T = h.text()
    row("F1 on the Terminal row says what turning it off does, including that it is a wall only for the prompt the home screen gives", "The Terminal tile" in T and "OFF" in T and "wall only for the prompt" in T, T[-700:])
    h.key("esc", idle=0.8)
    h.click(right[2][1] + 1, right[2][0], idle=1.4)
    T = h.text()
    row("a click on the [?] of the third row (the Editor tile) shows its help", "The Editor tile" in T and "Starts sed" in T, T[-500:])
    h.key("esc", idle=0.8)
    row("...and selected that row (reverse video on the row), so the box answers the row that was clicked", "r" in h.style(right[2][0], right[2][1] - 10)[2], repr(h.style(right[2][0], right[2][1] - 10)))
    h.key("f1", idle=1.2)
    reset_times()
    h.key("enter", idle=1.4)
    row("Enter in the box chooses Close, the default: the box closes and no program was started", "The Editor tile" not in h.text() and untouched("29a-sd-tcl-the-home-screen", 1.5), h.text()[-300:])
    h.key("f1", idle=1.2)
    h.typed("d", idle=2.0)
    row("the Documentation button runs pdf 29a-sd-tcl-the-home-screen through the allowed viewer: the status line says it was opened, and the program really ran",
        "Opened 29a-sd-tcl-the-home-screen with /usr/bin/touch" in h.line(40) and touched("29a-sd-tcl-the-home-screen"), repr(h.line(40)))
    reset_times()
    # a tile turned off and on through the page: Enter shows the command, Esc cancels, Run runs it.  The click on the third row's [?] above left the Editor row selected.
    h.key("enter", idle=1.2)
    T = h.text()
    row("Enter on the Editor row shows the command and says what it does: set.tile sduser editor off", "set.tile sduser editor off" in T, T[-600:])
    h.key("esc", idle=1.0)
    row("Esc is Cancel: nothing was run and the register field is unchanged", "nothing was run" in h.line(40) and reg_lines()[16].strip() == "", repr((h.line(40), reg_lines()[16])))
    h.key("enter", idle=1.2)
    h.typed("r", idle=2.0)
    row("Run runs it: field 17 of the register record is editor and the line under the page is the verb's own answer (11875)", reg_lines()[16].strip() == "editor" and "Tile editor is now off for sduser" in h.line(40), repr((reg_lines()[16], h.line(40))))
    h.key("enter", idle=1.2)
    h.typed("r", idle=2.0)
    row("Enter and Run again turn it on: field 17 is empty and the line says so (11876)", reg_lines()[16].strip() == "" and "Tile editor is now on for sduser" in h.line(40), repr((reg_lines()[16], h.line(40))))
    h.key("ctrl-q", idle=1.5)
    h.end()

    say("\n--- tool.viewers: the Bypass programs page")
    out = plain(["tool.viewers"])
    row("an ORDINARY session cannot reach it: 'Command requires administrator privileges' (11800 or 2001)", has(out, r"Command requires administrator privileges|is for the administrator only"), repr(out[:3]))
    h = H(admin=True)
    h.typed("tool.viewers\r", idle=3.0)
    T = h.text()
    if "What this means" not in T:
        dump(h)
        bail("tool.viewers never drew its page, so no row below can be believed")
    row("the page: the boxes Allowed for pdf, Found on this machine, What this means and Help", all(w in T for w in ("Allowed for pdf", "Found on this machine", "What this means", "Help")), T[:300])
    row("the Allowed box lists /usr/bin/touch and says it passes the test now", re.search(r"/usr/bin/touch\s+passes", h.line(3)) is not None, repr(h.line(3)[:80]))
    pos = [m.start() for m in re.finditer(r"\[\?\]", h.line(2))]
    row("a [?] at the end of each of the two boxes", len(pos) == 2, repr(h.line(2)))
    if len(pos) == 2:
        h.click(pos[1] + 1, 2, idle=1.4)
        T = h.text()
        row("a click on the [?] of the Found box shows its help", "PDF readers found on this machine" in T, T[-500:])
        h.key("esc", idle=0.8)
        h.click(pos[0] + 1, 2, idle=1.4)
        T = h.text()
        row("a click on the [?] of the Allowed box shows its help (it is the administrator's to grant)", "Programs allowed to start without os.execute" in T and "yours to grant" in T, T[-600:])
        h.key("esc", idle=0.8)
        row("...and a click on a [?] selects its box (the status line names it)", h.line(40).startswith("[Allowed]"), repr(h.line(40)))
    if h.line(40).startswith("[Found]"):
        h.key("tab", idle=0.6)                  # to Allowed
    elif h.line(40).startswith("[Allowed]"):
        pass
    h.key("enter", idle=1.2)
    T = h.text()
    row("Enter on /usr/bin/touch in the Allowed box shows set.viewer remove pdf touch", "set.viewer remove pdf touch" in T and "pdf will no longer start /usr/bin/touch" in T, T[-600:])
    h.key("esc", idle=1.0)
    row("Esc is Cancel: nothing was removed", viewers_file() == "pdf /usr/bin/touch\n" and "nothing was run" in h.line(40), repr((viewers_file(), h.line(40))))
    h.key("ctrl-q", idle=1.5)
    h.end()

    say("\n--- the home screen of the administrator reaches the two pages")
    h = H(admin=True)
    h.typed("menu\r", idle=3.0)
    row("MENU in the administrator's session opens the administrator's page, whose System group has Menu management and Bypass programs", "Menu management" in h.text() and "Bypass programs" in h.text() and "administrator" in h.text(), h.text()[:400])
    h.key("enter", idle=3.0)
    row("Enter on Menu management starts tool.menus: its Accounts and Menu boxes are on the screen", "What this means" in h.text() and "Accounts" in h.text() and "Menu" in h.text(), h.text()[:300])
    h.key("ctrl-q", idle=1.5)
    row("...Ctrl-Q leaves it and the home screen is drawn again", h.home(), h.text()[-200:])
    h.end()


def main():
    try:
        start_sandbox()
        sec_setup()
        sec_start()
        sec_page()
        sec_tiles()
        sec_tileoff()
        sec_help()
        sec_pdf()
        sec_pages()
    finally:
        teardown()
    say("\nsandbox-home-solo: %d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 and passed > 0 else 1)


if __name__ == "__main__":
    main()
