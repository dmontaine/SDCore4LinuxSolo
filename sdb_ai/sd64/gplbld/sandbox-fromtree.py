#!/usr/bin/env python3
#
# sandbox-fromtree.py - a private SD Core for Linux Solo built from THIS TREE, no install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-fromtree.py <dir> all
#   python3 .../sandbox-fromtree.py <dir> start | stop
#   python3 .../sandbox-fromtree.py <dir> sess <cwd> "<command>" ["<command>" ...]
#   (also: build, stage - the two halves of "all", for debugging)
#
# SAME COMMAND LINE AS THE FULL PRODUCT'S sandbox-fromtree.py, so that its sandbox-*.py suites can be pointed at
# this tool by putting the tool beside them (they find it as HERE/sandbox-fromtree.py).  THE CONTRACT THEY READ:
#   <dir> all     prints "bootstrap verdicts:" and, only when the bootstrap really finished, "[PASS] THIRD.COMPILE";
#                 leaves SD stopped;  <dir> start / stop;  <dir> sess <cwd> "cmd" ...  runs the commands in one
#                 session and prints what SD printed, the commands echoed after the prompt (suites split on
#                 ":TERM 200,9999");  <dir>/sys/bp the programs go into;  <dir>/sys/bin/sd the binary;
#                 <dir>/user_accounts the cwd the suites hand to sess.
# Exit 0 done (for "all": every bootstrap step reached its own success wording), 1 a step did not, 2 could not run.
#
# START-HISTORY:
# 18 Oct 26 dm  Written.  Solo has never run its own kernel C: the full product's tool cannot be used (it patches
#               check_admin(), cproc, bbproc, login and write_install_dicts, none of which Solo has in that shape, and
#               it assembles the tree itself), and the three old sandbox-*.py here imported a sandbox-txnfail.py that
#               died on its first patch.  This one builds a key-patched COPY of Solo's tree and hands it to the
#               existing solo-stage.sh, the code that stages the real installer's tree.  Solo-owned: it shares nothing
#               with the full product's file but the command line above.
# END-HISTORY
#
# WHAT IT CHANGES, IN THE COPY ONLY (each patch must match exactly once, or it refuses, and prints the lines):
#   gplsrc/sddefs.h SD_SHM_KEY / SD_SEM_KEY -> this sandbox's pair, 0x53434CA1/A2 plus 0x20 per keyset.
#   NOTHING ELSE.  Solo needs no root stub (check_admin() is empty, sd refuses uid 0), no pcode_bld patch (the home
#   comes from argv) and none of the full product's cproc / bbproc / login patches.
#
# THE KEYS.  Live Solo 0x53434C11/12 (running on this computer as a service, never touched), live full product
# 0x53434C01/02, the full product's sandboxes 0x53434C91/92 + 0x20 * keyset (keysets 0-7: 91 B1 D1 F1 111 131 151 171).
# This tool: SDSOLOBOX_KEYSET (0-7, unset is 0) -> A1 C1 E1 101 121 141 161 181 (and the matching 02 keys: A2 ...).
# No overlap with any of the above (checked when the tool loads, and by test-solo-sandbox-units.py), so a Solo
# sandbox and a full-product sandbox can run together.  The pair is refused if it is already held; the built binary
# is READ for the key before anything is started (a binary that still carried the live key would stop or attach to
# the live Solo); the live pairs are printed before and after and the run FAILS if one changed.
#
# WHOSE SEGMENT.  The keys come from SDSOLOBOX_KEYSET, not from the directory, so two directories can end up with
# the same pair, and a `-stop` or `ipcrm` on keys the OTHER one holds would take its sandbox from under it.  When a
# directory starts its SD it writes the segment and semaphore-set ids ipcs showed to <dir>/.ipc-ids; start and stop
# act on held keys only while ipcs still shows exactly those ids, and otherwise say so and touch nothing.  The keys
# are removed with ipcrm only after `-stop` left them held, and only the sandbox's own two.
#
# THE LAYOUT.  solo-stage.sh's HOME is both the Solo home and SDSYS, so HOME = <dir>/sys.  Beside it:
#   <dir>/tree          the patched copy of the source tree, built
#   <dir>/sys/bin/sd    a symbolic link to sd-solo (the suites look for bin/sd; the process's own path still resolves
#                       to sd-solo, which is what Solo's GetHomePath wants)
#   <dir>/sd.conf       a symbolic link to sys/sd.conf (suites that rewrite it write through the link)
#   <dir>/user_accounts, <dir>/group_accounts   empty; the cwd suites give sess (Solo ignores the cwd)
#   <dir>/account.pw, <dir>/admin.pw   generated passwords, 0600, NEVER printed and never on a command line
#                                      (solo-stage reads password FILES)
#
# THE SESSION.  "sess" writes the one-shot $internal marker (LOGIN deletes it on admission and it expires after ten
# minutes) and runs  sys/bin/sd-solo -internal  with the commands on a pipe.  That lands in SDSYS, the same account
# the full product's sandbox sessions run in, so a suite sees the same bp/ and VOC.
#
# THE INSTRUMENT.  Each bootstrap step is judged on the wording it prints only when it worked, read from solo-stage's
# own output (kept whole in <dir>/stage.log); a step whose section is missing from that output FAILS (the null case).
# solo-stage's exit status is printed and required to be 0 but is not the evidence: sd exits 0 through a pass that
# failed.  "all" with no step judged fails.

import argparse
import getpass
import os
import re
import secrets
import shutil
import signal
import string
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
SD64 = os.path.dirname(HERE)

LIVE_SOLO = ("0x53434c11", "0x53434c12")      # sddefs.h, and the service on this computer
LIVE_CORE = ("0x53434c01", "0x53434c02")      # the full product's install
CORE_BOX_BASE = (0x53434C91, 0x53434C92)      # the full product's sandboxes, + 0x20 * keyset (SDBOX_KEYSET)
SOLO_BOX_BASE = (0x53434CA1, 0x53434CA2)      # this tool's, + 0x20 * keyset (SDSOLOBOX_KEYSET)
KEYSET_VAR = "SDSOLOBOX_KEYSET"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def box_keys(keyset):
    return tuple(b + 0x20 * keyset for b in SOLO_BOX_BASE)


def all_other_keys():
    """Every pair this tool must never use: both live pairs and all eight keysets of the full product's sandboxes."""
    ks = {int(k, 16) for k in LIVE_SOLO + LIVE_CORE}
    for j in range(8):
        ks.update(b + 0x20 * j for b in CORE_BOX_BASE)
    return ks


def say(s=""):
    print(s)
    sys.stdout.flush()


def die(msg):
    """Could not run, or refused to: exit 2."""
    say(msg)
    sys.exit(2)


_KEYSET = os.environ.get(KEYSET_VAR, "0")
if not re.fullmatch("[0-7]", _KEYSET):
    die("sandbox-fromtree: REFUSED - %s must be a digit 0-7, not %r" % (KEYSET_VAR, _KEYSET))
KEYSET = int(_KEYSET)
SHM_BOX, SEM_BOX = box_keys(KEYSET)
BOX_KEYS = tuple("0x%08x" % k for k in (SHM_BOX, SEM_BOX))
# Every keyset of this tool against everything else: checked on every load, so an edit of a constant cannot
# silently make a sandbox share a segment with the live Solo or with the full product.
for _k in range(8):
    if set(box_keys(_k)) & all_other_keys():
        die("sandbox-fromtree: REFUSED - keyset %d (%s) overlaps a key already in use" % (_k, box_keys(_k)))


# ---------------------------------------------------------------------------
# ipcs

def ipcs_rows():
    """{key: (kind, id, owner)} for every SD-family segment and semaphore set (0x5343xxxx, and the old
    0x716d0x0x), from ipcs.  Raises if ipcs cannot be run: a tool that cannot see the keys must not guess."""
    rows = {}
    for kind, flag in (("shm", "-m"), ("sem", "-s")):
        p = subprocess.run(["ipcs", flag], capture_output=True, text=True)
        if p.returncode != 0:
            die("sandbox-fromtree: CANNOT RUN - ipcs %s failed: %s" % (flag, p.stderr.strip()))
        for line in p.stdout.splitlines():
            f = line.split()
            if len(f) >= 3 and re.fullmatch(r"0x(?:5343[0-9a-f]{4}|716d0[0-9]0[12])", f[0], re.I):
                rows[f[0].lower()] = (kind, f[1], f[2])
    return rows


def live_snapshot():
    rows = ipcs_rows()
    return {k: rows.get(k) for k in LIVE_SOLO + LIVE_CORE}


def show_live(label, snap):
    say("  live segments %s: %s" % (label, "; ".join("%s %s" % (k, ("%s id %s owner %s" % snap[k]) if snap[k] else "not held")
                                                   for k in sorted(snap))))


def check_live_unchanged(before, quiet=False):
    after = live_snapshot()
    changed = [k for k in before if before[k] != after[k]]
    if not quiet or changed:
        show_live("after", after)
    if changed:
        say("  [FAIL] the live segments changed during this run: %s" % " ".join(changed))
        return False
    if not quiet:
        say("  live segments unchanged")
    return True


# ---------------------------------------------------------------------------
# the copy and its patches

def replace_once(path, old, new, label):
    with open(path, "r", encoding="latin-1", newline="") as f:
        text = f.read()
    n = text.count(old)
    if n != 1:
        die("sandbox-fromtree: CANNOT RUN - %s: expected exactly one match for %r in %s, found %d" % (label, old, path, n))
    with open(path, "w", encoding="latin-1", newline="") as f:
        f.write(text.replace(old, new))
    line = text[:text.index(old)].count("\n") + 1
    say("    patched %s:%d (%s)" % (os.path.relpath(path, os.path.dirname(os.path.dirname(path))), line, label))
    say("      was: %s" % old)
    say("      now: %s" % new)


def sandbox_patches():
    return [
        ("gplsrc/sddefs.h", "#define SD_SHM_KEY 0x53434C11", "#define SD_SHM_KEY 0x%08X" % SHM_BOX, "sandbox shm key"),
        ("gplsrc/sddefs.h", "#define SD_SEM_KEY 0x53434C12", "#define SD_SEM_KEY 0x%08X" % SEM_BOX, "sandbox sem key"),
    ]


def le32(n):
    return n.to_bytes(4, "little")


def binary_keys_ok(path, quiet=False):
    """READ the key out of the built binary.  The sandbox pair must appear in it and the live Solo pair must not:
    a binary that still carried the live key would, on -start or -stop, act on the live Solo.  True/False.  Printed
    unless quiet (a session's output is parsed by suites, so a session says nothing unless the check fails)."""
    with open(path, "rb") as f:
        data = f.read()
    ok = True
    for name, key in (("shm", SHM_BOX), ("sem", SEM_BOX)):
        has = le32(key) in data
        if not quiet or not has:
            say("    %s holds the sandbox %s key 0x%08x: %s" % (os.path.basename(path), name, key, "yes" if has else "NO"))
        ok = ok and has
    for k in LIVE_SOLO:
        has = le32(int(k, 16)) in data
        if not quiet or has:
            say("    %s holds the live Solo key %s: %s" % (os.path.basename(path), k, "YES" if has else "no"))
        ok = ok and not has
    return ok


def refuse_inside_a_solo_tree(root):
    """A sandbox must not be made inside an installed Solo (or the full product's sysdir): any ancestor holding the
    .sdcoresolo marker, or being /usr/local/sdsys, is refused."""
    p = os.path.realpath(root)
    while True:
        if os.path.exists(os.path.join(p, ".sdcoresolo")):
            die("sandbox-fromtree: REFUSED - %s lies inside a Solo tree (%s has .sdcoresolo)" % (root, p))
        if p == "/usr/local/sdsys":
            die("sandbox-fromtree: REFUSED - %s lies inside the full product's /usr/local/sdsys" % root)
        up = os.path.dirname(p)
        if up == p:
            return
        p = up


def build(tree_dir, logpath, extra_patches=()):
    """A patched COPY of the tree, built.  extra_patches (same shape as sandbox_patches) is for a MUTANT build: the
    sandbox-txnfail.py rows revert one fix in a copy and require the row to go red; each must match exactly once."""
    say("  build %s" % tree_dir)
    shutil.copytree(SD64, tree_dir, ignore=shutil.ignore_patterns("bin", "gplobj", "terminfo", "__pycache__"))
    os.makedirs(os.path.join(tree_dir, "bin"))
    os.makedirs(os.path.join(tree_dir, "gplobj"))
    for rel, old, new, label in list(sandbox_patches()) + list(extra_patches):
        replace_once(os.path.join(tree_dir, rel), old, new, label)
    say("  make (serial; log %s)" % logpath)
    with open(logpath, "w") as log:
        p = subprocess.run(["make"], cwd=tree_dir, stdout=log, stderr=subprocess.STDOUT, text=True)
    binary = os.path.join(tree_dir, "bin", "sd-solo")
    if p.returncode != 0 or not os.path.isfile(binary):
        with open(logpath, errors="replace") as f:
            say("".join(f.readlines()[-30:]))
        die("sandbox-fromtree: CANNOT RUN - make failed in %s (exit %d)" % (tree_dir, p.returncode))
    say("    make exit 0, %s built" % binary)
    if not binary_keys_ok(binary):
        die("sandbox-fromtree: CANNOT RUN - the built binary does not carry exactly the sandbox keys; nothing will be started")


# ---------------------------------------------------------------------------
# passwords: generated here, 0600, never printed, never on a command line

def make_password():
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "-_.+="]
    chars = [secrets.choice(p) for p in pools]
    allc = "".join(pools)
    chars += [secrets.choice(allc) for _ in range(20)]
    secrets.SystemRandom().shuffle(chars)
    pw = "".join(chars)
    # SD's own rule (gpl.bp/pw_complex): 8+ characters, one of each of four kinds, printable ASCII
    assert len(pw) >= 8 and any(c.islower() for c in pw) and any(c.isupper() for c in pw) \
        and any(c.isdigit() for c in pw) and any(c in "-_.+=" for c in pw)
    return pw


def write_secret(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(make_password() + "\n")
    say("    wrote %s (mode %o, not printed)" % (path, os.stat(path).st_mode & 0o777))


# ---------------------------------------------------------------------------
# the sandbox's SD: start, stop, kill the daemon

class Box:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.tree = os.path.join(self.root, "tree")
        self.sys = os.path.join(self.root, "sys")
        self.conf = os.path.join(self.root, "sd.conf")
        self.sd = os.path.join(self.sys, "bin", "sd-solo")

    def env(self):
        e = dict(os.environ)
        e["SD_CONFIG"] = self.conf
        return e

    def held(self):
        rows = ipcs_rows()
        return [k for k in BOX_KEYS if k in rows]

    def kill_daemons(self):
        """The sandbox's sdlnxd runs a periodic check that would run 'sd -cleanup' mid-run.  Killed by executable path,
        and only a path under this sandbox's own directory."""
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                exe = os.readlink("/proc/%s/exe" % pid)
            except OSError:
                continue
            if exe.startswith(self.root + os.sep):
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except OSError:
                    continue
                say("    killed sandbox process %s (%s)" % (pid, os.path.relpath(exe, self.root)))

    def session(self, lines, cwd=None, binary=None, limit=None, timeout=600):
        """One internal session: the one-shot $internal marker, then <binary> -internal with the commands on a pipe.
        Returns (exit code, output with the ANSI codes removed, True when the marker was left unconsumed).
        binary is the sandbox's own sd-solo unless a mutant is swapped in; limit (bytes) is RLIMIT_FSIZE with SIGXFSZ
        ignored, for the rows that need a write to fail."""
        binary = binary or self.sd
        marker = os.path.join(self.sys, "$internal")
        with open(marker, "w") as f:
            f.write("sandbox-fromtree pid=%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%S")))
        body = "\nTERM 200,9999\n" + "".join(l + "\n" for l in lines) + "OFF\n"
        cmd = [binary, "-internal"]
        if limit:
            cmd = [sys.executable, "-c",
                   "import os,resource,signal,sys; signal.signal(signal.SIGXFSZ, signal.SIG_IGN); "
                   "resource.setrlimit(resource.RLIMIT_FSIZE, (%d, %d)); os.execv(sys.argv[1], sys.argv[1:])"
                   % (limit, limit)] + cmd
        # errors="replace": SD prints a raw field mark (0xFE) when a verb shows a record it was given, and a strict
        # decode killed the whole session's output once in the full product's tool.
        try:
            p = subprocess.run(cmd, input=body, cwd=cwd or self.sys, env=self.env(), capture_output=True,
                               text=True, errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            self.kill_daemons()
            return 124, "TIMEOUT", os.path.exists(marker)
        left = os.path.exists(marker)
        if left:
            os.remove(marker)
        return p.returncode, ANSI.sub("", p.stdout + p.stderr), left

    # WHO OWNS THE SEGMENT.  Two directories can use the same keyset (the keys come from SDSOLOBOX_KEYSET, not from the
    # directory), and `-stop` or `ipcrm` on keys held by the OTHER one would take its sandbox from under it.  So the
    # segment and semaphore-set ids ipcs showed when this directory started its SD are written to <dir>/.ipc-ids, and
    # start / stop act on held keys only when ipcs still shows exactly those ids.
    def ids_file(self):
        return os.path.join(self.root, ".ipc-ids")

    def record_owner(self):
        rows = ipcs_rows()
        if all(k in rows for k in BOX_KEYS):
            with open(self.ids_file(), "w") as f:
                f.write("shm %s\nsem %s\n" % (rows[BOX_KEYS[0]][1], rows[BOX_KEYS[1]][1]))
            return True
        return False

    def owns_held_keys(self):
        """True when the held sandbox keys are the segment this directory started (ids as recorded)."""
        rows = ipcs_rows()
        try:
            with open(self.ids_file()) as f:
                want = f.read().split()
        except OSError:
            return False
        have = ["shm", rows[BOX_KEYS[0]][1] if BOX_KEYS[0] in rows else "-",
                "sem", rows[BOX_KEYS[1]][1] if BOX_KEYS[1] in rows else "-"]
        return want == have

    def start(self):
        if not os.path.isfile(self.sd):
            die("sandbox-fromtree: CANNOT RUN - %s is not there (run 'all' first)" % self.sd)
        if self.held():
            if not self.owns_held_keys():
                say("    REFUSED: the sandbox keys %s are held by a different sandbox (this directory did not start them)"
                    % " ".join(self.held()))
                return False
            say("    sandbox keys already held (%s): SD is running" % " ".join(self.held()))
            return True
        with open(os.path.join(self.root, "start.log"), "w") as log:
            subprocess.run([self.sd, "-start"], stdout=log, stderr=log, env=self.env(), cwd=self.sys)
        time.sleep(1)
        self.kill_daemons()
        held = self.held()
        if len(held) == 2:
            self.record_owner()
        say("    started: sandbox keys now held: %s" % (" ".join(held) or "NONE"))
        return len(held) == 2

    def stop(self):
        """Stops only this sandbox's SD, with this sandbox's binary, and only when the held keys are the segment this
        directory started.  Keys held by anyone else are left alone and said."""
        held = self.held()
        if held and not self.owns_held_keys():
            say("    REFUSED: the sandbox keys %s are held, but not by a segment this directory started: "
                "nothing is stopped and nothing is removed" % " ".join(held))
            return False
        if os.path.isfile(self.sd) and held:
            with open(os.path.join(self.root, "stop.log"), "w") as log:
                subprocess.run([self.sd, "-stop"], stdout=log, stderr=log, env=self.env(), cwd=self.sys)
        self.kill_daemons()
        left = self.held()
        for k in left:
            # -stop did not remove it (or the binary is gone): remove exactly this sandbox's own key, nothing else
            rows = ipcs_rows()
            if k not in rows:
                continue                    # it went between the two looks
            flag = "-M" if rows[k][0] == "shm" else "-S"
            if int(k, 16) in box_keys(KEYSET):
                p = subprocess.run(["ipcrm", flag, k], capture_output=True, text=True)
                say("    ipcrm %s %s: %s" % (flag, k, (p.stdout + p.stderr).strip() or "removed"))
        say("    stopped: sandbox keys held now: %s" % (" ".join(self.held()) or "none"))
        return not self.held()


# ---------------------------------------------------------------------------
# staging and the verdicts

SECTIONS = [
    # (label, the line of solo-stage's output that opens the section)
    ("pass 1", r"^Bootstrap pass 1 \("),
    ("pass 2", r"^Bootstrap pass 2 \("),
    ("pass 3", r"^Bootstrap pass 3 \("),
    ("THIRD.COMPILE", r"^Compiling C and I type dictionaries \("),
    ("account", r"^Creating the one account \("),
]


def split_sections(plain):
    """{label: text} - each section runs from its opening line to the next opening line (or the end)."""
    lines = plain.splitlines()
    starts = []
    for label, pat in SECTIONS:
        idx = [i for i, l in enumerate(lines) if re.search(pat, l)]
        starts.append((idx[0] if idx else None, label))
    found = sorted((i, l) for i, l in starts if i is not None)
    out = {}
    for n, (i, label) in enumerate(found):
        j = found[n + 1][0] if n + 1 < len(found) else len(lines)
        out[label] = "\n".join(lines[i:j])
    return out


def judge(plain):
    """[(label, ok, said)] - each on the wording it prints only when it worked."""
    secs = split_sections(plain)
    v = []

    def add(label, ok, said):
        v.append((label, ok, said))

    s = secs.get("pass 1")
    if s is None:
        add("pass 1 (sd -i)", False, "no section in solo-stage's output")
    else:
        nonzero = re.search(r"(?m)^\s*[1-9][0-9]* error\(s\)", s)
        add("pass 1 (sd -i)", "Errors in compile" not in s and "Unable to load" not in s and "0 error(s)" in s and not nonzero,
            "0 error(s)" if "0 error(s)" in s and not nonzero else "no '0 error(s)' line, or a nonzero one")
    s = secs.get("pass 2")
    if s is None:
        add("pass 2 (SECOND.COMPILE)", False, "no section in solo-stage's output")
    else:
        m = re.search(r"Compiled (\d+) program\(s\) with no errors", s)
        # A compiler warning that a constant is "not assigned a value" is a failure even at "0 error(s)": a program
        # that compiles with it fails at run time (the full product met it 2 Oct 26: K$ADMINISTRATOR unassigned).
        unassigned = "is not assigned a value" in s
        nonzero = re.search(r"(?m)^\s*[1-9][0-9]* error\(s\)", s)
        add("pass 2 (SECOND.COMPILE) %s%s" % (m.group(0) if m else "- no success line",
                                               " BUT a warning says a constant is not assigned a value" if unassigned else ""),
            m is not None and "Unable to load" not in s and not unassigned and not nonzero,
            m.group(0) if m else "no success line")
    s = secs.get("pass 3")
    if s is None:
        add("pass 3 (write_install_dicts)", False, "no section in solo-stage's output")
    else:
        add("pass 3 (write_install_dicts)", re.search(r"(?m)^\s*COMPLETE\s*$", s) is not None and "Unable to load" not in s,
            "COMPLETE" if re.search(r"(?m)^\s*COMPLETE\s*$", s) else "no COMPLETE line")
    s = secs.get("THIRD.COMPILE")
    if s is None:
        add("THIRD.COMPILE", False, "no section in solo-stage's output")
    else:
        # THIRD.COMPILE is the VOC paragraph  CD $MAP / CD accounts / CD dict.dict / CD voc.  CD prints "Compiling <item>"
        # for each I- or C-type it compiles and has no summary line; its failures are messages 2811, 2974, 2975 and 2976.
        # So: the session ran (admitted line), at least one item was compiled, and none of the four failure texts.
        # (the section's own opening line, "Compiling C and I type dictionaries (...)", is not one of them)
        n_comp = len(re.findall(r"(?m)^Compiling \S", s.split("\n", 1)[1] if "\n" in s else ""))
        bad3 = THIRD_BAD.search(s)
        ok3 = "Internal session admitted" in s and n_comp > 0 and bad3 is None
        add("THIRD.COMPILE", ok3, ("Compiling lines: %d" % n_comp) if bad3 is None else "said: " + bad3.group(0))
    s = secs.get("account")
    if s is None:
        add("account (solo_account)", False, "no section in solo-stage's output")
    else:
        m = re.search(r"(?m)^SOLO ACCOUNT READY sduser ", s)
        add("account (solo_account) SOLO ACCOUNT READY sduser", m is not None, "READY" if m else "no READY line")
    return v


# what CD prints when an item cannot be compiled (sdsys/messages 2811, 2974, 2975, 2976), and the load failure
THIRD_BAD = re.compile(r"Source record '.*' not found|Record '.*' is not a C or I-type|Record '.*' has no expression"
                       r"|Compilation error in '.*'|Unable to load")


def stage(box):
    say("  stage: solo-stage.sh from the copy, into %s" % box.sys)
    for name in ("account.pw", "admin.pw"):
        write_secret(os.path.join(box.root, name))
    script = os.path.join(box.tree, "gplbld", "solo-stage.sh")
    cmd = ["bash", script, "--account-password-file", os.path.join(box.root, "account.pw"),
           "--admin-password-file", os.path.join(box.root, "admin.pw"), box.sys]
    say("  > %s (cwd %s)" % (" ".join(cmd), box.tree))
    env = {k: v for k, v in os.environ.items() if k != "SD_CONFIG"}    # solo-stage finds sd.conf from the binary's own path
    log = os.path.join(box.root, "stage.log")
    # TO A FILE, NOT A PIPE: solo-stage leaves SD's daemon (sdlnxd) running, and the daemon inherits the pipe, so a
    # reader waiting for end of file waits for ever (measured 18 Oct 26: the first run hung ten minutes after the
    # bootstrap had finished).  The full product's tool never met this because it starts SD itself, into a log.
    with open(log, "w") as lf:
        try:
            p = subprocess.run(cmd, cwd=box.tree, env=env, stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                               timeout=1800)
        finally:
            # whatever solo-stage left running was started by THIS run (the keys were not held when it began):
            # record its ids so that stop can tell it from another sandbox's
            if box.held():
                box.record_owner()
    with open(log, errors="replace") as f:
        raw = f.read()
    plain = ANSI.sub("", raw).replace("\r", "")
    tail = plain.splitlines()[-25:]
    say("  solo-stage output, last %d of %d lines (all of it is in %s):" % (len(tail), len(plain.splitlines()), log))
    for l in tail:
        say("    | " + l)
    say("  solo-stage exit %d" % p.returncode)
    return p.returncode, plain


def layout(box):
    """The shims the full product's suites expect around solo-stage's tree."""
    if not os.path.isdir(os.path.join(box.sys, "bin")):
        say("    layout: %s/bin is not there (solo-stage stopped before it was made): no shims" % box.sys)
        return
    link = os.path.join(box.sys, "bin", "sd")
    if os.path.lexists(link):
        os.remove(link)
    os.symlink("sd-solo", link)
    if os.path.lexists(box.conf):
        os.remove(box.conf)
    os.symlink(os.path.join("sys", "sd.conf"), box.conf)
    for d in ("user_accounts", "group_accounts"):
        os.makedirs(os.path.join(box.root, d), exist_ok=True)
    say("    layout: sys/bin/sd -> sd-solo, sd.conf -> sys/sd.conf, user_accounts/ and group_accounts/ (empty) made")
    # 23 Oct 26 (Solo carry 14, S.75): a session on a terminal now starts in the HOME SCREEN unless the system default says terminal, and every pty suite types at the prompt, so the
    # sandbox starts at the terminal (Core's tool writes the same file); the suites that test the home screen change it for their own rows.
    with open(os.path.join(box.sys, "start.default"), "w") as f:
        f.write("terminal\n")
    say("    layout: sys/start.default says terminal (the delivered default is menu; the sandbox starts at the prompt)")


def do_all(box):
    patches_log = os.path.join(box.root, "make.log")
    build(box.tree, patches_log)
    rc, plain = stage(box)
    layout(box)
    # the daemon solo-stage leaves running is this sandbox's: stop it with this sandbox's binary
    box.stop()
    verdicts = judge(plain)
    final = "solo-stage: bootstrap passes 1-3, THIRD.COMPILE and the account completed in %s" % box.sys
    finished = final in plain
    say("\nbootstrap verdicts:")
    for label, ok, _ in verdicts:
        say("  [%s] %s" % ("PASS" if ok else "FAIL", label))
    if not verdicts:
        say("  [FAIL] no step was judged")
    ok_all = bool(verdicts) and all(ok for _, ok, _ in verdicts) and rc == 0 and finished
    say("  [%s] solo-stage ended with exit 0 and its own completion line" % ("PASS" if rc == 0 and finished else "FAIL"))
    return 0 if ok_all else 1


def do_sess(box, rest):
    if len(rest) < 2:
        die("sandbox-fromtree: sess needs <cwd> and at least one command")
    cwd, cmds = rest[0], rest[1:]
    if not os.path.isfile(box.sd):
        die("sandbox-fromtree: CANNOT RUN - %s is not there (run 'all' first)" % box.sd)
    if not os.path.isdir(cwd):
        die("sandbox-fromtree: CANNOT RUN - the cwd %s is not a directory" % cwd)
    rc, out, left = box.session(cmds, cwd=cwd)
    say(out)
    say("exit %d" % rc)
    if ":TERM 200,9999" not in out:
        say("sandbox-fromtree: THE SESSION DID NOT RUN - no ':TERM 200,9999' echo in what SD printed (marker consumed: %s)"
            % ("NO" if left else "yes"))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("step", choices=["all", "build", "stage", "start", "stop", "sess"])
    ap.add_argument("rest", nargs="*")
    a = ap.parse_args()
    if os.getuid() == 0:
        die("sandbox-fromtree: REFUSED - run it as an ordinary user; Solo never runs as root")
    root = os.path.abspath(a.dir)
    box = Box(root)
    refuse_inside_a_solo_tree(root)
    # A session's output is parsed by the suites, so "sess" prints nothing of its own unless something is wrong;
    # every other step prints its real inputs and the live segments before and after.
    quiet = a.step == "sess"
    before = live_snapshot()
    held = [k for k in BOX_KEYS if k in ipcs_rows()]
    if not quiet:
        say("sandbox-fromtree (Solo)")
        say("  tree        : %s" % SD64)
        say("  sandbox     : %s" % box.root)
        say("  user        : %s (uid %d)" % (getpass.getuser(), os.getuid()))
        say("  step        : %s%s" % (a.step, (" " + " ".join(a.rest)) if a.rest else ""))
        say("  keyset      : %d (%s=%s): shm %s, sem %s" % (KEYSET, KEYSET_VAR, _KEYSET, BOX_KEYS[0], BOX_KEYS[1]))
        show_live("before", before)
        say("  sandbox keys held before: %s" % (" ".join(held) or "none"))
    rc = 0
    try:
        if a.step in ("all", "build"):
            if held:
                die("sandbox-fromtree: REFUSED - sandbox keys %s are held; stop the old sandbox first" % " ".join(held))
            if os.path.exists(box.root) and os.listdir(box.root):
                die("sandbox-fromtree: REFUSED - %s is not empty" % box.root)
            os.makedirs(box.root, exist_ok=True)
        if a.step == "all":
            rc = do_all(box)
        elif a.step == "build":
            build(box.tree, os.path.join(box.root, "make.log"))
        elif a.step == "stage":
            if held:
                die("sandbox-fromtree: REFUSED - sandbox keys %s are held; stop the old sandbox first" % " ".join(held))
            if os.path.exists(box.sys):
                die("sandbox-fromtree: REFUSED - %s exists" % box.sys)
            if not binary_keys_ok(os.path.join(box.tree, "bin", "sd-solo")):
                die("sandbox-fromtree: CANNOT RUN - the binary does not carry exactly the sandbox keys")
            rc, plain = stage(box)
            layout(box)
            box.stop()
            verdicts = judge(plain)
            say("\nbootstrap verdicts:")
            for label, ok, _ in verdicts:
                say("  [%s] %s" % ("PASS" if ok else "FAIL", label))
            rc = 0 if verdicts and all(ok for _, ok, _ in verdicts) and rc == 0 else 1
        elif a.step == "start":
            rc = 0 if box.start() else 1
        elif a.step == "stop":
            rc = 0 if box.stop() else 1
        elif a.step == "sess":
            if not os.path.isfile(box.sd):
                die("sandbox-fromtree: CANNOT RUN - %s is not there (run 'all' first)" % box.sd)
            if not binary_keys_ok(box.sd, quiet=True):
                die("sandbox-fromtree: CANNOT RUN - the binary does not carry exactly the sandbox keys; no session")
            rc = do_sess(box, a.rest)
    except subprocess.TimeoutExpired as e:
        say("sandbox-fromtree: TIMEOUT after %s s: %s" % (e.timeout, " ".join(map(str, e.cmd))))
        box.stop()
        rc = 1
    except BaseException:
        # a failed 'all' or 'stage' must not leave the sandbox's SD running
        if a.step in ("all", "build", "stage") and os.path.isdir(box.root):
            box.stop()
        raise
    if not check_live_unchanged(before, quiet):
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
