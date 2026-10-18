#!/usr/bin/env python3
"""LSOLO sandbox harness (18 Oct 2026) - the free check over gplbld/sandbox-fromtree.py.

WHY THIS EXISTS.  The tool is what lets the full product's sandbox-*.py suites run on Solo's kernel, and what keeps
a sandbox from touching the live Solo.  Both are promises that a run proves only once, on the day it is run, and
that an edit can break without any suite noticing: a changed key constant would make a sandbox share the live
Solo's shared memory; a judge that stopped looking for its success wording would print "[PASS] THIRD.COMPILE" over
a bootstrap that failed.  This reads the tool and exercises its pure parts (the judge on fixture output, the stop
guard with ipcs and subprocess faked, the password writer), with no SD, no sandbox, no install, no sudo.

WHAT IT CHECKS (a row id each; the mutants below name the rows they must turn red):
  A1  the tool compiles.   A2  it answers all / start / stop / sess.
  A3  every subcommand the full product's suites call is one it answers (reads the full product's tree by absolute
      path; skipped, and said, when that tree is not there).
  A4  its base for the full product's sandbox keys is the full product's (same skip).
  K1  all 8 keysets of this tool: two distinct keys each, none equal to the live Solo pair, the live full-product
      pair, or any of the full product's 8 sandbox pairs.  The expected sets are written HERE, not read from the tool.
  K2  the two key patches match sddefs.h exactly once each, and the live constants there are 0x53434C11/12.
  K3  SDSOLOBOX_KEYSET=9 is refused with exit 2; =3 gives the keys 0x53434D01/02.
  S1  the judge, on a fixture of solo-stage's output in its real shape: five steps, all passing.
  S2  and each failure wording or missing line, one at a time, turns exactly its own step red; empty output turns
      every step red (a judge that passes on nothing is the null case).
  B1  Box.stop runs `-stop` only with this sandbox's binary and only when this sandbox's keys are held, and removes
      with ipcrm only this sandbox's own keys.
  P1  generated passwords satisfy SD's rule, differ, are written 0600, and are never on a command line.
  R1  the tool refuses uid 0; it has no sudo and no path of the live Solo or of /usr/local/sdsys outside the one
      refusal; it never builds under an installed tree.
  R2  `all` on a non-empty directory and `sess` with no sandbox exit 2 and build nothing.
  D1  none of this directory's sandbox-*.py names the full product's /usr/local/sdsys or /home/sd (the three dead
      scripts did, and could not run).

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-solo-sandbox-units.py
  python3 .../test-solo-sandbox-units.py --selftest      (mutants of the tool: each must turn its rows red)

No sudo.  Exit 0 all rows passed, 1 a row failed, 2 the run established nothing.
"""

import glob
import importlib.util
import os
import re
import stat
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.realpath(__file__))
SD64 = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
CORE_GPLBLD = "/home/don/Projects/SDCore4Linux/sdb_ai/sd64/gplbld"

# Written here on purpose: the tool's own constants are what is being checked.
LIVE_SOLO = (0x53434C11, 0x53434C12)
LIVE_CORE = (0x53434C01, 0x53434C02)
CORE_BOXES = {k for j in range(8) for k in (0x53434C91 + 0x20 * j, 0x53434C92 + 0x20 * j)}


class Report:
    def __init__(self):
        self.rows = []          # (id, ok, detail)

    def row(self, rid, ok, detail=""):
        self.rows.append((rid, bool(ok), detail))

    def skip(self, rid, why):
        self.rows.append((rid, None, why))


def load(path, keyset=None):
    """The tool as a module (not executed as a program).  SDSOLOBOX_KEYSET is set for the load only."""
    old = os.environ.get("SDSOLOBOX_KEYSET")
    if keyset is None:
        os.environ.pop("SDSOLOBOX_KEYSET", None)
    else:
        os.environ["SDSOLOBOX_KEYSET"] = str(keyset)
    try:
        spec = importlib.util.spec_from_file_location("sbxtool_%d" % abs(hash((path, keyset))), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is None:
            os.environ.pop("SDSOLOBOX_KEYSET", None)
        else:
            os.environ["SDSOLOBOX_KEYSET"] = old


def code_lines(text):
    """Source lines with comments and docstring-free blank lines removed (a # inside a string is rare enough here)."""
    out = []
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        out.append(l)
    return out


# ---------------------------------------------------------------------------
# the fixture: solo-stage's output in the shape a real run printed it (18 Oct 26), cut short

GOOD = """solo-stage inputs:
  source tree : /x/tree
Starting SD (/x/sys/bin/sd-solo -start)

Bootstrap pass 1 (/x/sys/bin/sd-solo -i)
compile: term
****
0 error(s)
creating: /x/sys/voc.dic

Bootstrap pass 2 (/x/sys/bin/sd-solo -internal SECOND.COMPILE)
Compiling gpl.bp listlck
****
0 error(s)
$listlck added to global catalogue
Compiled 214 program(s) with no errors

Bootstrap pass 3 (/x/sys/bin/sd-solo -internal RUN gpl.bp write_install_dicts NO.PAGE)
Internal session admitted (opened by solo-stage)
COMPLETE

Compiling C and I type dictionaries (/x/sys/bin/sd-solo -internal THIRD.COMPILE)
SD Core for Linux Solo, the Essential Multivalue String Database, version LS1.1-3
Internal session admitted (opened by solo-stage pid=1 2026-10-18T09:36:03-07:00)
Compiling gname
Compiling mode.flag
Compiling size

Creating the one account (/x/sys/bin/sd-solo -internal RUN gpl.bp solo_account)
Internal session admitted (opened by solo-stage)
solo_account: 417 VOC entries copied from NEWVOC
SOLO ACCOUNT READY sduser /x/sys/user_accounts/sduser
"""

LABELS = ["pass 1", "pass 2", "pass 3", "THIRD", "account"]


def verdict_map(mod, text):
    """{step label: ok} - the judge's rows keyed by the first words of their labels."""
    out = {}
    for label, ok, _ in mod.judge(text):
        for key in LABELS:
            if label.startswith(key if key != "THIRD" else "THIRD.COMPILE") or (key == "account" and label.startswith("account")):
                out[key] = ok
    return out


# (id, description, edit of GOOD, the step that must turn red)
JUDGE_CASES = [
    ("pass 1 shows an error", lambda t: t.replace("0 error(s)", "3 error(s)", 1), "pass 1"),
    ("pass 1 says Errors in compile", lambda t: t.replace("compile: term", "Errors in compile: term", 1), "pass 1"),
    ("pass 1 has no 0 error(s) line", lambda t: t.replace("0 error(s)\ncreating", "creating", 1), "pass 1"),
    ("pass 2 has no Compiled line", lambda t: t.replace("Compiled 214 program(s) with no errors\n", ""), "pass 2"),
    ("pass 2 warns a constant is not assigned a value",
     lambda t: t.replace("$listlck added", "warning: K$X is not assigned a value\n$listlck added", 1), "pass 2"),
    ("pass 3 has no COMPLETE line", lambda t: t.replace("\nCOMPLETE\n", "\n"), "pass 3"),
    ("pass 3 says Unable to load", lambda t: t.replace("COMPLETE\n", "COMPLETE\nUnable to load x\n", 1), "pass 3"),
    ("THIRD.COMPILE compiled nothing", lambda t: re.sub(r"(?m)^Compiling (gname|mode\.flag|size)\n", "", t), "THIRD"),
    ("THIRD.COMPILE says Compilation error", lambda t: t.replace("Compiling size\n", "Compiling size\nCompilation error in 'size'\n"), "THIRD"),
    ("THIRD.COMPILE says Source record not found", lambda t: t.replace("Compiling size\n", "Source record 'x' not found\n"), "THIRD"),
    ("THIRD.COMPILE's session was never admitted",
     lambda t: t.replace("Internal session admitted (opened by solo-stage pid=1 2026-10-18T09:36:03-07:00)\n", ""), "THIRD"),
    ("the THIRD.COMPILE section is missing",
     lambda t: re.sub(r"(?s)Compiling C and I type dictionaries.*?(?=Creating the one account)", "", t), "THIRD"),
    ("the account section has no READY line", lambda t: t.replace("SOLO ACCOUNT READY sduser", "solo_account: refused"), "account"),
    ("the pass 3 section is missing",
     lambda t: re.sub(r"(?s)Bootstrap pass 3.*?(?=Compiling C and I type)", "", t), "pass 3"),
]


def check_judge(rep, mod):
    base = verdict_map(mod, GOOD)
    rep.row("S1 a real-shaped solo-stage output passes all five steps", base == {k: True for k in LABELS}, repr(base))
    for desc, edit, step in JUDGE_CASES:
        txt = edit(GOOD)
        if txt == GOOD:
            rep.row("S2 %s (the edit changed nothing: a broken case)" % desc, False)
            continue
        got = verdict_map(mod, txt)
        want = {k: (k != step) for k in LABELS}
        rep.row("S2 %s -> %s red and no other step" % (desc, step), got == want, "got %r" % got)
    empty = verdict_map(mod, "")
    rep.row("S2 empty output turns every step red (the null case)", len(empty) == 5 and not any(empty.values()), repr(empty))


# ---------------------------------------------------------------------------

def check_static(rep, mod, text):
    try:
        compile(text, TOOL, "exec")
        rep.row("A1 the tool compiles", True)
    except SyntaxError as e:
        rep.row("A1 the tool compiles", False, str(e))
    m = re.search(r'add_argument\("step", choices=\[([^\]]*)\]', text)
    steps = set(re.findall(r'"(\w+)"', m.group(1))) if m else set()
    rep.row("A2 it answers all, start, stop and sess", {"all", "start", "stop", "sess"} <= steps, repr(sorted(steps)))

    suites = sorted(glob.glob(os.path.join(CORE_GPLBLD, "sandbox-*.py")))
    if suites:
        used = set()
        for p in suites:
            with open(p, errors="replace") as f:
                used.update(re.findall(r'TOOL, box, "(\w+)"', f.read()))
        rep.row("A3 every subcommand the full product's %d suites call (%s) is answered" % (len(suites), " ".join(sorted(used))),
                bool(used) and used <= steps, "missing: %s" % sorted(used - steps))
    else:
        rep.skip("A3 the full product's suites", "no %s/sandbox-*.py" % CORE_GPLBLD)

    ctx = os.path.join(CORE_GPLBLD, "sandbox-txnfail.py")
    if os.path.isfile(ctx):
        with open(ctx, errors="replace") as f:
            ct = f.read()
        shm = re.search(r"SHM_BOX = (0x[0-9A-Fa-f]+) \+ 0x20 \* KEYSET", ct)
        sem = re.search(r"SEM_BOX = (0x[0-9A-Fa-f]+) \+ 0x20 \* KEYSET", ct)
        ok = bool(shm and sem) and (int(shm.group(1), 16), int(sem.group(1), 16)) == tuple(mod.CORE_BOX_BASE) \
            and (int(shm.group(1), 16), int(sem.group(1), 16)) == (0x53434C91, 0x53434C92)
        rep.row("A4 the full product's sandbox key base is 0x53434C91/92 + 0x20 per keyset, as the tool and this test assume",
                ok, "%s %s, tool %s" % (shm and shm.group(1), sem and sem.group(1), tuple(map(hex, mod.CORE_BOX_BASE))))
    else:
        rep.skip("A4 the full product's key base", "no %s" % ctx)

    # K1 - written here: eight keysets, none touching anything in use
    taken = set(LIVE_SOLO) | set(LIVE_CORE) | CORE_BOXES
    bad = []
    seen = set()
    for k in range(8):
        try:
            shm, sem = mod.box_keys(k)
        except Exception as e:
            bad.append("keyset %d: %s" % (k, e))
            continue
        for key in (shm, sem):
            if key in taken:
                bad.append("keyset %d key 0x%08x is in use" % (k, key))
            if key in seen:
                bad.append("keyset %d key 0x%08x repeats" % (k, key))
            seen.add(key)
        if shm == sem:
            bad.append("keyset %d: shm == sem" % k)
    rep.row("K1 eight keysets, sixteen distinct keys, none live and none a full-product sandbox key", not bad and len(seen) == 16,
            "; ".join(bad) or "%d keys" % len(seen))
    rep.row("K1b keyset 0 is 0x53434CA1/A2", tuple(mod.box_keys(0)) == (0x53434CA1, 0x53434CA2), repr(mod.box_keys(0)))

    # K2 - the patches against the real header
    with open(os.path.join(SD64, "gplsrc", "sddefs.h"), errors="replace") as f:
        h = f.read()
    probs = []
    for rel, old, new, label in mod.sandbox_patches():
        if rel != "gplsrc/sddefs.h":
            probs.append("%s patches %s, not sddefs.h" % (label, rel))
        if h.count(old) != 1:
            probs.append("%r matches %d times" % (old, h.count(old)))
    live = re.findall(r"#define SD_(?:SHM|SEM)_KEY (0x[0-9A-Fa-f]+)", h)
    rep.row("K2 the key patches each match sddefs.h once and the live constants are 0x53434C11/12",
            not probs and sorted(int(x, 16) for x in live) == sorted(LIVE_SOLO), "; ".join(probs) or repr(live))

    # K3 - the keyset variable
    env = dict(os.environ, SDSOLOBOX_KEYSET="9")
    p = subprocess.run([sys.executable, mod.__file__, "/nonexistent-sandbox", "stop"], env=env, capture_output=True, text=True)
    rep.row("K3 SDSOLOBOX_KEYSET=9 is refused with exit 2", p.returncode == 2 and "REFUSED" in p.stdout, "exit %d: %s" % (p.returncode, p.stdout.strip()[:100]))
    try:
        m3 = load(mod.__file__, keyset=3)
        rep.row("K3b SDSOLOBOX_KEYSET=3 gives 0x53434D01/02", (m3.SHM_BOX, m3.SEM_BOX) == (0x53434D01, 0x53434D02), "%x %x" % (m3.SHM_BOX, m3.SEM_BOX))
    except BaseException as e:
        rep.row("K3b SDSOLOBOX_KEYSET=3 loads", False, repr(e))

    # R1 - what the code must not contain
    code = "\n".join(code_lines(text))
    rep.row("R1 the tool refuses uid 0", re.search(r"os\.getuid\(\) == 0:\s*\n\s*die\(", code) is not None)
    rep.row("R1b no sudo in its code", re.search(r"sudo", code) is None)
    live_paths = [l for l in code_lines(text) if ("SDCoreSolo" in l or "/usr/local/sdsys" in l or "/home/sd" in l)]
    m = re.search(r"def refuse_inside_a_solo_tree.*?(?=\ndef )", text, re.S)
    body_lines = set(code_lines(m.group(0))) if m else set()
    rep.row("R1c the live Solo's path and the full product's sysdir appear only inside the refusal that keeps a "
            "sandbox out of an installed tree", bool(live_paths) and all(l in body_lines for l in live_paths)
            and not any("SDCoreSolo" in l for l in live_paths), repr(live_paths))
    rep.row("R1d ipcrm is run in one place only", len(re.findall(r'"ipcrm"', code)) == 1, "%d" % len(re.findall(r'"ipcrm"', code)))


def check_box(rep, mod):
    """B1 - Box.stop with ipcs and subprocess faked."""
    calls = []
    held = {}

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    fake_sub = types.SimpleNamespace(run=fake_run, DEVNULL=-3, STDOUT=-2, PIPE=-1, TimeoutExpired=subprocess.TimeoutExpired)
    saved = (mod.subprocess, mod.ipcs_rows, mod.say)
    mod.subprocess = fake_sub
    mod.say = lambda *a, **k: None
    try:
        with tempfile.TemporaryDirectory() as t:
            root = os.path.join(t, "box")
            os.makedirs(os.path.join(root, "sys", "bin"))
            box = mod.Box(root)
            open(box.sd, "w").close()
            sbx_keys = {k: ("shm", "1", "u") for k in mod.BOX_KEYS}
            sbx_keys[mod.BOX_KEYS[0]] = ("shm", "777", "u")
            sbx_keys[mod.BOX_KEYS[1]] = ("sem", "888", "u")
            live = {k: ("shm", "1", "u") for k in ("0x53434c11", "0x53434c12", "0x53434c01")}

            def owner(shm="777", sem="888"):
                with open(box.ids_file(), "w") as f:
                    f.write("shm %s\nsem %s\n" % (shm, sem))

            def run_stop(rows_before, rows_after=None):
                calls.clear()
                # stop() asks ipcs three times before it acts (held, the ownership check, the keys left): the first
                # two see the state before, the rest the state after
                seq = [rows_before, rows_before] + [rows_after if rows_after is not None else {}] * 6
                it = iter(seq)
                cur = {"r": rows_before}

                def rows():
                    try:
                        cur["r"] = next(it)
                    except StopIteration:
                        pass
                    return cur["r"]
                mod.ipcs_rows = rows
                box.stop()
                return [c for c in calls if isinstance(c, list)]

            if os.path.exists(box.ids_file()):
                os.remove(box.ids_file())
            c = run_stop({})
            rep.row("B1 nothing held: no -stop and no ipcrm", not any("-stop" in x or "ipcrm" in x for x in c), repr(c))
            c = run_stop(dict(live))
            rep.row("B1b only the LIVE keys held: no -stop and no ipcrm (the live Solo is never stopped)",
                    not any("-stop" in x or "ipcrm" in x for x in c), repr(c))
            owner()
            c = run_stop(dict(live, **sbx_keys), {})
            stops = [x for x in c if "-stop" in x]
            rep.row("B1c the sandbox's keys held, the ids this directory recorded: -stop runs once, with the sandbox's own binary",
                    len(stops) == 1 and stops[0][0] == box.sd and box.sd.startswith(box.root + os.sep), repr(stops))
            c = run_stop(dict(live, **sbx_keys), dict(live, **sbx_keys))
            rm = [x for x in c if x and x[0] == "ipcrm"]
            removed = {x[2] for x in rm}
            rep.row("B1d a key that stays after -stop is removed with ipcrm, and only the sandbox's keys are",
                    removed and removed <= set(mod.BOX_KEYS), repr(rm))
            owner(shm="999")
            c = run_stop(dict(live, **sbx_keys), dict(live, **sbx_keys))
            rep.row("B1e the sandbox's keys held by ANOTHER sandbox (other ids): no -stop and no ipcrm",
                    not any("-stop" in x or "ipcrm" in x for x in c), repr(c))
            os.remove(box.ids_file())
            c = run_stop(dict(live, **sbx_keys), dict(live, **sbx_keys))
            rep.row("B1f the keys held and this directory never recorded owning them: no -stop and no ipcrm",
                    not any("-stop" in x or "ipcrm" in x for x in c), repr(c))
            # start: does not claim keys somebody else holds
            calls.clear()
            mod.ipcs_rows = lambda: dict(live, **sbx_keys)
            ok = box.start()
            rep.row("B1g start() with the keys held by another sandbox refuses and does not run -start",
                    ok is False and not any("-start" in x for x in calls if isinstance(x, list)), repr(calls))
    finally:
        mod.subprocess, mod.ipcs_rows, mod.say = saved


def check_passwords(rep, mod):
    def rule(pw):
        return len(pw) >= 8 and any("a" <= c <= "z" for c in pw) and any("A" <= c <= "Z" for c in pw) \
            and any("0" <= c <= "9" for c in pw) and any(32 <= ord(c) <= 126 and not c.isalnum() for c in pw) \
            and all(33 <= ord(c) <= 126 for c in pw)
    try:
        pws = [mod.make_password() for _ in range(60)]
    except BaseException as e:      # the generator asserts its own rule; an assertion firing is the rule being kept
        rep.row("P1 sixty generated passwords satisfy SD's rule", False, "make_password raised %r" % (e,))
        return
    rep.row("P1 sixty generated passwords satisfy SD's rule (printable, 33-126, four kinds, 8+)", all(rule(p) for p in pws),
            "first bad: %r" % next((p for p in pws if not rule(p)), None))
    rep.row("P1b and no two are alike", len(set(pws)) == len(pws))
    with tempfile.TemporaryDirectory() as t:
        old = os.umask(0)
        try:
            pth = os.path.join(t, "x.pw")
            saved = mod.say
            mod.say = lambda *a, **k: None
            try:
                mod.write_secret(pth)
            finally:
                mod.say = saved
        finally:
            os.umask(old)
        mode = stat.S_IMODE(os.stat(pth).st_mode)
        body = open(pth).read()
        rep.row("P1c a password file is mode 0600 and holds one line", mode == 0o600 and body.endswith("\n") and body.count("\n") == 1, "%o" % mode)
        # never on a command line: stage() with subprocess faked
        argv = []

        def fake_run(cmd, *a, **kw):
            argv.append(list(cmd))
            return types.SimpleNamespace(returncode=0)
        saved_sub, saved_say, saved_ipcs = mod.subprocess, mod.say, mod.ipcs_rows
        mod.subprocess = types.SimpleNamespace(run=fake_run, DEVNULL=-3, STDOUT=-2, PIPE=-1, TimeoutExpired=subprocess.TimeoutExpired)
        mod.say = lambda *a, **k: None
        mod.ipcs_rows = lambda: {}
        try:
            root = os.path.join(t, "box")
            os.makedirs(os.path.join(root, "tree", "gplbld"))
            box = mod.Box(root)
            mod.stage(box)
        finally:
            mod.subprocess, mod.say, mod.ipcs_rows = saved_sub, saved_say, saved_ipcs
        secrets_ = [open(os.path.join(root, n)).read().strip() for n in ("account.pw", "admin.pw") if os.path.exists(os.path.join(root, n))]
        flat = " ".join(" ".join(a) for a in argv)
        rep.row("P1d stage() hands solo-stage password FILES: two are written and neither password is on the command line",
                len(secrets_) == 2 and all(s and s not in flat for s in secrets_) and "--account-password-file" in flat
                and "--admin-password-file" in flat, "%d files, argv: %s" % (len(secrets_), flat[:160]))


def check_cli(rep, tool):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, "nonempty")
        os.makedirs(d)
        open(os.path.join(d, "x"), "w").close()
        p = subprocess.run([sys.executable, tool, d, "all"], capture_output=True, text=True, timeout=120)
        built = os.path.exists(os.path.join(d, "tree"))
        rep.row("R2 `all` on a non-empty directory exits 2, says REFUSED and builds nothing",
                p.returncode == 2 and "REFUSED" in p.stdout and not built, "exit %d, tree made: %s" % (p.returncode, built))
        p = subprocess.run([sys.executable, tool, os.path.join(t, "none"), "sess", t, "WHO"], capture_output=True, text=True, timeout=120)
        rep.row("R2b `sess` with no sandbox exits 2 and says it is not there",
                p.returncode == 2 and "is not there" in p.stdout, "exit %d: %s" % (p.returncode, p.stdout.strip()[-120:]))


def check_dead(rep):
    bad = []
    n = 0
    for p in sorted(glob.glob(os.path.join(HERE, "sandbox-*.py"))):
        if os.path.basename(p) == "sandbox-fromtree.py":
            continue            # the tool names /usr/local/sdsys once, to refuse it: R1c reads that
        n += 1
        with open(p, errors="replace") as f:
            for i, l in enumerate(f, 1):
                s = l.strip()
                if s.startswith("#"):
                    continue
                if "/usr/local/sdsys" in l or "/home/sd" in l or "LIVE_SYS" in l:
                    bad.append("%s:%d" % (os.path.basename(p), i))
    rep.row("D1 none of the %d sandbox-*.py here names the full product's sysdir or account folder in code" % n, n > 0 and not bad, ", ".join(bad))


def run_all(tool_path):
    rep = Report()
    with open(tool_path) as f:
        text = f.read()
    try:
        mod = load(tool_path)
    except SystemExit as e:
        # the tool's own load-time guards (a keyset that overlaps a key in use, a bad SDSOLOBOX_KEYSET) refused it
        rep.row("L0 the tool loads (its own guards did not refuse it)", False, "exit %r" % (e.code,))
        return rep
    rep.row("L0 the tool loads (its own guards did not refuse it)", True)
    check_static(rep, mod, text)
    check_judge(rep, mod)
    check_box(rep, mod)
    check_passwords(rep, mod)
    check_cli(rep, tool_path)
    check_dead(rep)
    return rep


def show(rep, verbose=True):
    p = f = s = 0
    for rid, ok, detail in rep.rows:
        if ok is None:
            s += 1
            if verbose:
                print("  [SKIP] %s: %s" % (rid, detail))
        elif ok:
            p += 1
            if verbose:
                print("  [PASS] %s" % rid)
        else:
            f += 1
            if verbose:
                print("  [FAIL] %s   <- %s" % (rid, detail))
    return p, f, s


# ---------------------------------------------------------------------------
# mutants of the tool: (name, [(old text, new text), ...], row-id prefixes that must turn red)
# Two of them change a key constant: the tool's own load-time guard refuses those (L0), and the same edit with the
# guard taken out is what K1 has to catch by itself.

GUARD = ("    if set(box_keys(_k)) & all_other_keys():", "    if False:")
MUTANTS = [
    ("keys: the sandbox pair is the full product's keyset 0 (the tool's own guard)",
     [("SOLO_BOX_BASE = (0x53434CA1, 0x53434CA2)", "SOLO_BOX_BASE = (0x53434C91, 0x53434C92)")], ["L0"]),
    ("keys: the sandbox pair is the full product's keyset 0, tool guard off",
     [("SOLO_BOX_BASE = (0x53434CA1, 0x53434CA2)", "SOLO_BOX_BASE = (0x53434C91, 0x53434C92)"), GUARD], ["K1"]),
    ("keys: the sandbox pair is the live Solo's, tool guard off",
     [("SOLO_BOX_BASE = (0x53434CA1, 0x53434CA2)", "SOLO_BOX_BASE = (0x53434C11, 0x53434C12)"), GUARD], ["K1"]),
    ("keys: the keyset step is too small (keysets overlap), tool guard off",
     [("return tuple(b + 0x20 * keyset for b in SOLO_BOX_BASE)", "return tuple(b + 0x1 * keyset for b in SOLO_BOX_BASE)"), GUARD], ["K1"]),
    ("stop: runs -stop whether or not the sandbox's keys are held",
     [("if os.path.isfile(self.sd) and held:", "if os.path.isfile(self.sd):")], ["B1"]),
    ("stop: acts on keys without asking who started them",
     [("if held and not self.owns_held_keys():", "if False:")], ["B1e", "B1f"]),
    ("held(): any SD key counts, not only the sandbox's (the live Solo's would be stopped), ownership check off",
     [("return [k for k in BOX_KEYS if k in rows]", "return [k for k in rows]"),
      ("if held and not self.owns_held_keys():", "if False:")], ["B1b"]),
    ("start: takes over keys another sandbox holds",
     [("            if not self.owns_held_keys():\n                say(\"    REFUSED: the sandbox keys %s are held by a different sandbox",
       "            if False:\n                say(\"    REFUSED: the sandbox keys %s are held by a different sandbox")], ["B1g"]),
    ("judge: THIRD.COMPILE passes whatever it printed",
     [("ok3 = \"Internal session admitted\" in s and n_comp > 0 and bad3 is None", "ok3 = True")], ["S2 THIRD"]),
    ("judge: THIRD.COMPILE counts its own opening line as a compiled item",
     [("s.split(\"\\n\", 1)[1] if \"\\n\" in s else \"\"", "s")], ["S2 THIRD.COMPILE compiled nothing"]),
    ("judge: pass 3 does not need its COMPLETE line",
     [("add(\"pass 3 (write_install_dicts)\", re.search(r\"(?m)^\\s*COMPLETE\\s*$\", s) is not None and \"Unable to load\" not in s,",
       "add(\"pass 3 (write_install_dicts)\", \"Unable to load\" not in s,")], ["S2 pass 3"]),
    ("judge: a missing THIRD.COMPILE section passes",
     [("add(\"THIRD.COMPILE\", False, \"no section in solo-stage's output\")", "add(\"THIRD.COMPILE\", True, \"\")")],
     ["S2 the THIRD", "S2 empty"]),
    ("judge: pass 2 ignores the not-assigned-a-value warning",
     [("m is not None and \"Unable to load\" not in s and not unassigned and not nonzero,", "m is not None and \"Unable to load\" not in s and not nonzero,")],
     ["S2 pass 2 warns"]),
    ("passwords: written world readable", [("fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)",
                                            "fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)")], ["P1c"]),
    ("passwords: the symbol class is left out", [('pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "-_.+="]',
                                                   'pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "a"]')], ["P1"]),
    ("root: the uid 0 refusal is gone",
     [("    if os.getuid() == 0:\n        die(\"sandbox-fromtree: REFUSED - run it as an ordinary user; Solo never runs as root\")\n", "")],
     ["R1 the tool refuses"]),
    ("safety: `all` no longer refuses a non-empty directory",
     [("if os.path.exists(box.root) and os.listdir(box.root):\n                die(\"sandbox-fromtree: REFUSED - %s is not empty\" % box.root)",
       "if False:\n                die(\"sandbox-fromtree: REFUSED - %s is not empty\" % box.root)")], ["R2"]),
    ("safety: `sess` with no sandbox no longer says so",
     [("            if not os.path.isfile(box.sd):\n                die(\"sandbox-fromtree: CANNOT RUN - %s is not there (run 'all' first)\" % box.sd)\n            if not binary_keys_ok(box.sd, quiet=True):",
       "            if not binary_keys_ok(box.sd, quiet=True):")], ["R2b"]),
]


def selftest():
    with open(TOOL) as f:
        text = f.read()
    ctrl = run_all(TOOL)
    p, f, s = show(ctrl, verbose=False)
    print("selftest: control (the tool as it is): %d passed, %d failed, %d skipped" % (p, f, s))
    if f or p == 0:
        show(ctrl)
        print("selftest: the control is not clean - no mutant means anything")
        return 2
    miss = 0
    with tempfile.TemporaryDirectory() as t:
        for name, edits, want in MUTANTS:
            mtext = text
            broken = None
            for old, new in edits:
                n = mtext.count(old)
                if n != 1:
                    broken = "its text %r matches %d times" % (old[:50], n)
                    break
                mtext = mtext.replace(old, new)
            if broken:
                print("  [BROKEN MUTANT] %s: %s" % (name, broken))
                miss += 1
                continue
            mp = os.path.join(t, "sandbox-fromtree.py")
            with open(mp, "w") as fh:
                fh.write(mtext)
            try:
                rep = run_all(mp)
            except BaseException as e:
                print("  [BROKEN MUTANT] %s: the test died on it: %r" % (name, e))
                miss += 1
                continue
            red = [rid for rid, ok, _ in rep.rows if ok is False]
            caught = all(any(rid.startswith(w) for rid in red) for w in want)
            print("  [%s] mutant: %s   red: %s" % ("CAUGHT" if caught else "MISSED", name, ", ".join(r[:34] for r in red[:4]) or "none"))
            if not caught:
                miss += 1
    print("selftest: %d mutants, %d not caught" % (len(MUTANTS), miss))
    return 1 if miss else 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    print("test-solo-sandbox-units: %s" % TOOL)
    rep = run_all(TOOL)
    p, f, s = show(rep)
    print("\n%d passed, %d failed, %d skipped" % (p, f, s))
    if p == 0:
        print("test-solo-sandbox-units: no row ran - a broken test, not a pass")
        return 2
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
