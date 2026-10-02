#!/usr/bin/env python3
# test-soloexe-units.py - the Solo server is installed as sd-solo (owner, 1 Oct 2026: "just
# rename the solo exe to sd-solo"), and what that touches.  Replaces test-launcher-units.py,
# whose launcher no longer exists.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-soloexe-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-soloexe-units.py --selftest
#
# No sudo, no install, no sd.  It CUTS shipped code out of installsdsolo.sh and deletesdsolo.sh
# by their marker lines and runs it with bash in a scratch HOME:
#   command_names   (installer)   what install_command_names makes and removes
#   upgrade_rename  (installer)   what an upgrade of a tree installed BEFORE the rename moves:
#                                 the systemd units, the authorized_keys lines, the sshd drop-in
#   link_detect     (uninstaller) which of the two commands is this tree's to remove
# and it reads the sources for the invariants no run can show: the one constant
# (SD_SERVER_NAME), the four C sites that start the server by file name, the Makefile's output
# name, and that no script still says bin/sd except where it is deliberately about the OLD name.
#
# EVERY CHECK PRINTS WHAT IT EXPECTED AND WHAT IT SAW.  It refuses (exit 2) when a marker is not
# found exactly once or the cut code does not define what the checks run, and --selftest breaks
# the shipped code and the sources and requires the checks to catch each break.
# CANNOT SAY: that a real systemd, sshd or ssh login accepts any of it - that is the install
# witness's job (verify-solo-upgrade.sh, verify-solo-service.sh, verify-solo-ssh.sh).
#
# Exit 0 every check passed, 1 a check failed, 2 it could not measure.

import contextlib
import io
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SD64 = os.path.join(ROOT, "sdb_ai", "sd64")
INSTALLER = os.path.join(ROOT, "installsdsolo.sh")
DELETER = os.path.join(ROOT, "deletesdsolo.sh")
MARK = "SD Core for Linux Solo launcher."

FAKE = "#!/bin/sh\necho SOLO\n"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def cut_code(path, begin, end):
    lines = read(path).split("\n")
    b = [i for i, l in enumerate(lines) if l.strip() == begin]
    e = [i for i, l in enumerate(lines) if l.strip() == end]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        print("REFUSED: %s must hold exactly one '%s' and one '%s' line, in that order "
              "(found %d and %d)" % (path, begin, end, len(b), len(e)), file=sys.stderr)
        sys.exit(2)
    return "\n".join(lines[b[0] + 1:e[0]])


class Suite:
    def __init__(self, names, migrate, detect, sources):
        self.names, self.migrate, self.detect_code, self.src = names, migrate, detect, sources
        self.checks = 0
        self.failed = 0
        self.quiet = False

    def check(self, name, expected, ok, saw):
        self.checks += 1
        if not ok:
            self.failed += 1
        if not self.quiet or not ok:
            print("  [%s] %s | expected: %s | saw: %s" % ("PASS" if ok else "FAIL", name, expected, saw))

    # ---------------------------------------------------------------- command_names
    def world(self, tmp, tree_name="tree dir"):
        home = os.path.join(tmp, "home")
        tree = os.path.join(tmp, tree_name)         # a space on purpose: nothing may split it
        os.makedirs(os.path.join(home, ".local", "bin"))
        os.makedirs(os.path.join(tree, "bin"))
        for n in ("sd-solo",):
            with open(os.path.join(tree, "bin", n), "w") as f:
                f.write(FAKE)
            os.chmod(os.path.join(tree, "bin", n), 0o755)
        return home, tree

    def names_run(self, home, tree):
        script = ('set -euo pipefail\nwarn() { printf "WARN: %%s\\n" "$*" >&2; }\nHOME=%s\n%s\n'
                  'install_command_names %s\n' % (shlex.quote(home), self.names, shlex.quote(tree)))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)

    def suite_names(self):
        S = self
        with tempfile.TemporaryDirectory() as tmp:
            home, tree = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            r = S.names_run(home, tree)
            S.check("N0 the installer code ran to the end", "exit 0, nothing on stderr",
                    r.returncode == 0 and r.stderr == "", "exit %d %r" % (r.returncode, r.stderr[:200]))
            link = os.path.join(b, "sd-solo")
            S.check("N1 'sd-solo' is a link to the new server file", "-> %s" % os.path.join(tree, "bin", "sd-solo"),
                    os.path.islink(link) and os.readlink(link) == os.path.join(tree, "bin", "sd-solo"),
                    os.readlink(link) if os.path.islink(link) else "not a link")
            S.check("N1b no plain 'sd' is made", "absent", not os.path.lexists(os.path.join(b, "sd")),
                    "present" if os.path.lexists(os.path.join(b, "sd")) else "absent")
            r2 = S.names_run(home, tree)
            S.check("N7 a second install changes nothing", "exit 0, same link",
                    r2.returncode == 0 and os.readlink(link) == os.path.join(tree, "bin", "sd-solo"), "exit %d" % r2.returncode)

        with tempfile.TemporaryDirectory() as tmp:     # N2 an old link to this tree's old bin/sd
            home, tree = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            old = os.path.join(tree, "bin", "sd")
            with open(old, "w") as f:
                f.write(FAKE)
            os.symlink(old, os.path.join(b, "sd"))
            r = S.names_run(home, tree)
            S.check("N2 an old 'sd' link to this tree's bin/sd is removed", "gone, exit 0, says so",
                    r.returncode == 0 and not os.path.lexists(os.path.join(b, "sd")) and "removed the old" in r.stdout,
                    "exit %d lexists=%s stdout=%r" % (r.returncode, os.path.lexists(os.path.join(b, "sd")), r.stdout[:120]))

        with tempfile.TemporaryDirectory() as tmp:     # N3 an old launcher
            home, tree = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            with open(os.path.join(b, "sd"), "w") as f:
                f.write("#!/bin/sh\n# %s\nexec '%s/bin/sd' \"$@\"\n" % (MARK, tree))
            r = S.names_run(home, tree)
            S.check("N3 an old launcher of this product is removed", "gone, exit 0",
                    r.returncode == 0 and not os.path.lexists(os.path.join(b, "sd")),
                    "exit %d lexists=%s" % (r.returncode, os.path.lexists(os.path.join(b, "sd"))))

        for tag, make in (("N4 the user's own 'sd' file", lambda p: open(p, "w").write("#!/bin/sh\necho mine\n")),
                          ("N5 an 'sd' link to some other program", lambda p: os.symlink("/bin/true", p)),
                          ("N5b an 'sd' link to ANOTHER tree's bin/sd", lambda p: os.symlink("/elsewhere/bin/sd", p))):
            with tempfile.TemporaryDirectory() as tmp:
                home, tree = S.world(tmp)
                sd = os.path.join(home, ".local", "bin", "sd")
                make(sd)
                state = lambda: (os.path.lexists(sd), os.path.islink(sd),
                                 os.readlink(sd) if os.path.islink(sd) else (open(sd).read() if os.path.exists(sd) else None))
                before = state()
                r = S.names_run(home, tree)
                after = state()
                S.check(tag + " is left alone, silently (it is not this product's)", "unchanged; no stderr; exit 0; sd-solo still made",
                        r.returncode == 0 and before == after and r.stderr == ""
                        and os.path.islink(os.path.join(home, ".local", "bin", "sd-solo")),
                        "exit %d unchanged=%s stderr=%r" % (r.returncode, before == after, r.stderr[:160]))

        with tempfile.TemporaryDirectory() as tmp:     # N6 the user's own sd-solo file
            home, tree = S.world(tmp)
            f = os.path.join(home, ".local", "bin", "sd-solo")
            open(f, "w").write("#!/bin/sh\necho mine\n")
            r = S.names_run(home, tree)
            S.check("N6 the user's own 'sd-solo' file is left alone, with a warning", "unchanged; WARN; exit 0",
                    r.returncode == 0 and open(f).read() == "#!/bin/sh\necho mine\n" and "exists and is not a link" in r.stderr,
                    "exit %d stderr=%r" % (r.returncode, r.stderr[:160]))

    # ---------------------------------------------------------------- upgrade_rename
    def migrate_run(self, home_dir, unitdir, ak, dropin):
        script = ('set -uo pipefail\nsay() { printf "%%s\\n" "$*"; }\nwarn() { printf "WARN: %%s\\n" "$*" >&2; }\n'
                  'fail() { printf "FAIL: %%s\\n" "$*" >&2; exit 9; }\n%s\n'
                  'migrate_server_name %s %s %s %s\n'
                  % (self.migrate, shlex.quote(home_dir), shlex.quote(unitdir), shlex.quote(ak), shlex.quote(dropin)))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)

    def suite_migrate(self):
        S = self
        for tree_name in ("tree dir", "t.ree"):           # regex characters in the path must not matter
            with tempfile.TemporaryDirectory() as tmp:
                tree = os.path.join(tmp, tree_name)
                os.makedirs(os.path.join(tree, "bin"))
                other = os.path.join(tmp, "tXree")                  # the '.' in "t.ree" must not match this
                units = os.path.join(tmp, "units")
                os.makedirs(units)
                svc = os.path.join(units, "sd-solo.service")
                api = os.path.join(units, "sd-solo-api@.service")
                open(svc, "w").write("[Service]\nDescription=x\nExecStart=%s/bin/sd -start\nExecStop=%s/bin/sd -stop\n" % (tree, tree))
                open(api, "w").write("[Service]\nExecStart=%s/bin/sd -n -q\nExecStartPre=%s/bin/sd -x\n" % (tree, other))
                ak = os.path.join(tmp, "authorized_keys")
                keep = ["ssh-ed25519 AAAA plain-key", 'command="%s/bin/sd",restrict,pty ssh-ed25519 BBBB other-tree' % other]
                open(ak, "w").write("\n".join([
                    'command="%s/bin/sd",restrict,pty ssh-ed25519 CCCC mine' % tree, keep[0], keep[1],
                    'command="%s/bin/sd",restrict,pty ssh-ed25519 DDDD mine2' % tree]) + "\n")
                os.chmod(ak, 0o600)
                dropin = os.path.join(tmp, "50-sd-solo-x.conf")
                open(dropin, "w").write("Match User x\n    ForceCommand %s/bin/sd\n    DisableForwarding yes\n" % tree)
                r = S.migrate_run(tree, units, ak, dropin)
                tag = "[%s] " % tree_name
                S.check(tag + "M0 the migration ran to the end", "exit 0", r.returncode == 0, "exit %d %r" % (r.returncode, r.stderr[:160]))
                got = open(svc).read()
                S.check(tag + "M1 sd-solo.service runs the new file, the rest unchanged",
                        "ExecStart/ExecStop name %s/bin/sd-solo; Description kept" % tree,
                        "ExecStart=%s/bin/sd-solo -start\n" % tree in got and "ExecStop=%s/bin/sd-solo -stop\n" % tree in got
                        and "Description=x\n" in got, got.replace("\n", " | "))
                got = open(api).read()
                S.check(tag + "M1b the API unit moves; a line naming ANOTHER tree is untouched",
                        "ExecStart=%s/bin/sd-solo -n -q and ExecStartPre=%s/bin/sd -x" % (tree, other),
                        "ExecStart=%s/bin/sd-solo -n -q\n" % tree in got and "ExecStartPre=%s/bin/sd -x\n" % other in got,
                        got.replace("\n", " | "))
                lines = open(ak).read().split("\n")
                S.check(tag + "M4 both key lines of this tree move; other lines byte for byte",
                        "two lines now name sd-solo; the plain key and the other tree's line unchanged; 4 lines",
                        lines[0] == 'command="%s/bin/sd-solo",restrict,pty ssh-ed25519 CCCC mine' % tree
                        and lines[3] == 'command="%s/bin/sd-solo",restrict,pty ssh-ed25519 DDDD mine2' % tree
                        and lines[1] == keep[0] and lines[2] == keep[1] and len(lines) == 5 and lines[4] == "",
                        " | ".join(lines))
                S.check(tag + "M4b authorized_keys keeps its mode", "0600", stat.S_IMODE(os.stat(ak).st_mode) == 0o600,
                        oct(stat.S_IMODE(os.stat(ak).st_mode)))
                link = os.path.join(tree, "bin", "sd")
                S.check(tag + "M6 an old drop-in gets a compatibility link and a warning naming the re-apply command",
                        "bin/sd -> sd-solo; WARN mentions solo-ssh.sh match --apply",
                        os.path.islink(link) and os.readlink(link) == "sd-solo" and "match" in r.stderr and "--apply" in r.stderr,
                        "link=%s stderr=%r" % (os.readlink(link) if os.path.islink(link) else "none", r.stderr[:160]))
                # M2/M5 running it again changes nothing and says nothing
                snap = (open(svc).read(), open(api).read(), open(ak).read())
                r2 = S.migrate_run(tree, units, ak, dropin)
                S.check(tag + "M2 a second run changes no unit and no key line, says nothing about them",
                        "same files; no 'systemd:' or 'ssh:' line", (open(svc).read(), open(api).read(), open(ak).read()) == snap
                        and "systemd:" not in r2.stdout and "ssh:" not in r2.stdout, "exit %d stdout=%r" % (r2.returncode, r2.stdout[:120]))

        with tempfile.TemporaryDirectory() as tmp:     # M6b a drop-in already on the new name; no files at all
            tree = os.path.join(tmp, "tree")
            os.makedirs(os.path.join(tree, "bin"))
            dropin = os.path.join(tmp, "d.conf")
            open(dropin, "w").write("Match User x\n    ForceCommand %s/bin/sd-solo\n" % tree)
            r = S.migrate_run(tree, os.path.join(tmp, "nounits"), os.path.join(tmp, "noak"), dropin)
            S.check("M6b a drop-in already on the new name: no link, no warning", "exit 0, no link, no stderr",
                    r.returncode == 0 and not os.path.lexists(os.path.join(tree, "bin", "sd")) and r.stderr == "",
                    "exit %d stderr=%r" % (r.returncode, r.stderr[:120]))
            r = S.migrate_run(tree, os.path.join(tmp, "nounits"), os.path.join(tmp, "noak"), os.path.join(tmp, "nodropin"))
            S.check("M7 no units, no authorized_keys, no drop-in: nothing happens", "exit 0, no output",
                    r.returncode == 0 and r.stdout == "" and r.stderr == "", "exit %d %r %r" % (r.returncode, r.stdout, r.stderr))

    # ---------------------------------------------------------------- link_detect
    def detect(self, home, tree):
        script = 'set -uo pipefail\nHOME=%s\nH=%s\n%s\necho "$link_ours $solo_link_ours"\n' % (
            shlex.quote(home), shlex.quote(tree), self.detect_code)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
        return r.stdout.strip(), r

    def suite_detect(self):
        S = self
        launcher_for = lambda t: "#!/bin/sh\n# %s\nexec '%s/bin/sd' \"$@\"\n" % (MARK, t)
        cases = [
            ("D1 'sd' an old launcher naming this tree; 'sd-solo' the new link", "launcher", "newlink", "1 1"),
            ("D2 'sd' an old link to this tree's bin/sd; no sd-solo", "oldlink", "none", "1 0"),
            ("D3 'sd-solo' still pointing at the OLD bin/sd is ours too", "none", "oldsolo", "0 1"),
            ("D4 'sd' ANOTHER tree's launcher; 'sd-solo' another tree's link: not ours", "otherlauncher", "otherlink", "0 0"),
            ("D5 the user's own files: not ours", "mine", "mine", "0 0"),
            ("D6 links elsewhere: not ours", "elsewhere", "elsewhere", "0 0"),
            ("D7 nothing is there", "none", "none", "0 0"),
            ("D8 the user's own script that runs THIS tree's binary but has no marker: not ours", "ownscript", "none", "0 0"),
        ]
        for name, sd_kind, solo_kind, want in cases:
            with tempfile.TemporaryDirectory() as tmp:
                home, tree = S.world(tmp)
                other = os.path.join(tmp, "other tree")
                os.makedirs(os.path.join(other, "bin"))
                b = os.path.join(home, ".local", "bin")
                for path, kind in ((os.path.join(b, "sd"), sd_kind), (os.path.join(b, "sd-solo"), solo_kind)):
                    if kind == "launcher":
                        open(path, "w").write(launcher_for(tree))
                    elif kind == "otherlauncher":
                        open(path, "w").write(launcher_for(other))
                    elif kind == "oldlink":
                        os.symlink(os.path.join(tree, "bin", "sd"), path)
                    elif kind == "newlink":
                        os.symlink(os.path.join(tree, "bin", "sd-solo"), path)
                    elif kind == "oldsolo":
                        os.symlink(os.path.join(tree, "bin", "sd"), path)
                    elif kind == "otherlink":
                        os.symlink(os.path.join(other, "bin", "sd-solo"), path)
                    elif kind == "elsewhere":
                        os.symlink("/bin/true", path)
                    elif kind == "mine":
                        open(path, "w").write("#!/bin/sh\necho mine\n")
                    elif kind == "ownscript":
                        open(path, "w").write("#!/bin/sh\nexec '%s/bin/sd' \"$@\"\n" % tree)
                got, r = S.detect(home, tree)
                S.check(name, "link_ours solo_link_ours = %s" % want, got == want and r.returncode == 0,
                        "%r (exit %d) with sd=%s sd-solo=%s" % (got, r.returncode, sd_kind, solo_kind))

    # ---------------------------------------------------------------- sources
    def suite_sources(self):
        S, src = self, self.src
        S.check("S1 sddefs.h defines SD_SERVER_NAME as \"sd-solo\"", 'one #define',
                len(re.findall(r'^#define\s+SD_SERVER_NAME\s+"sd-solo"\s*$', src["sddefs.h"], re.M)) == 1,
                "found" if 'SD_SERVER_NAME' in src["sddefs.h"] else "absent")
        for f in ("op_kernel.c", "sysseg.c", "sdlnxd.c", "sdclilib.c"):
            code = re.sub(r'/\*.*?\*/', '', src[f], flags=re.S)
            code = re.sub(r'//[^\n]*', '', code)
            literal = re.findall(r'"[^"\n]*/bin/sd(?![-A-Za-z0-9_])[^"\n]*"', code)
            S.check("S2 %s starts the server through SD_SERVER_NAME and names bin/sd nowhere in code" % f,
                    "uses /bin/\" SD_SERVER_NAME and no \"...bin/sd\" literal",
                    '/bin/" SD_SERVER_NAME' in code and not literal, "uses=%s literals=%r" % ('/bin/" SD_SERVER_NAME' in code, literal[:2]))
        mk = src["Makefile"]
        S.check("S3 the Makefile links bin/sd-solo and never bin/sd", "-o $(GPLBIN)sd-solo; no -o $(GPLBIN)sd ",
                "-o $(GPLBIN)sd-solo\n" in mk and not re.search(r'-o \$\(GPLBIN\)sd(?![-A-Za-z0-9_])', mk), "checked")
        # a comment explains; only a line that RUNS or MATCHES the old name must say it is the old one
        allowed = re.compile(r'(?i)\bold\b|before|compat|earlier|legacy|FORCED_OLD|for n in sd-solo sd|\$H/bin/\$n|oldf|\bwas\b|\$esc/bin/sd|\$home_dir/bin/sd|\.local/bin/sd(?![-A-Za-z0-9_])|\$link|\$solo_link')
        bad = []
        for rel, text in src["scripts"].items():
            for i, ln in enumerate(text.split("\n"), 1):
                if ln.lstrip().startswith("#"):
                    continue
                if re.search(r'(?<!sdsys/)bin/sd(?![-A-Za-z0-9_])', ln) and not allowed.search(ln):
                    bad.append("%s:%d: %s" % (rel, i, ln.strip()[:100]))
        S.check("S4 no script still says bin/sd except about the OLD name", "none", not bad, bad[:3] if bad else "none")

    def suite(self):
        self.suite_names()
        self.suite_migrate()
        self.suite_detect()
        self.suite_sources()


def load_sources():
    src = {n: read(os.path.join(SD64, "gplsrc", n)) for n in ("sddefs.h", "op_kernel.c", "sysseg.c", "sdlnxd.c", "sdclilib.c")}
    src["Makefile"] = read(os.path.join(SD64, "Makefile"))
    scripts = {"installsdsolo.sh": read(INSTALLER), "deletesdsolo.sh": read(DELETER)}
    g = os.path.join(SD64, "gplbld")
    for f in sorted(os.listdir(g)):
        if f in ("solo-service.sh", "solo-ssh.sh", "solo-stage.sh") or (f.startswith("verify-solo") and f.endswith(".sh")):
            scripts["gplbld/" + f] = read(os.path.join(g, f))
    src["scripts"] = scripts
    return src


def selftest(names, migrate, detect, src):
    def nm(old, new):
        return ("names", old, new)
    mutants = [
        ("names", "the new link points at the OLD file", 'ln -sfn "$tree/bin/sd-solo" "$bindir/sd-solo"', 'ln -sfn "$tree/bin/sd" "$bindir/sd-solo"'),
        ("names", "an old sd link is never removed", 'rm -f "$old"; printf \'removed the old %s (a link to %s)\\n\' "$old" "$tree/bin/sd"', ':'),
        ("names", "any sd link is removed", '[ "$(readlink "$old")" = "$tree/bin/sd" ]', 'true'),
        ("names", "a user's own sd file is removed", "elif [ -f \"$old\" ] && grep -qF 'SD Core for Linux Solo launcher.' \"$old\" 2>/dev/null; then", "elif [ -f \"$old\" ]; then"),
        ("migrate", "the units are not moved", 'sed -i "s#^\\\\(Exec[A-Za-z]*=\\\\)$esc/bin/sd #\\\\1$home_dir/bin/sd-solo #" "$u"', ':'),
        ("migrate", "the key lines are not moved", "'index($0, old) == 1 { $0 = new substr($0, length(old) + 1) } { print }'", "'{ print }'"),
        ("migrate", "no compatibility link for an old drop-in", 'ln -sfn sd-solo "$home_dir/bin/sd"', ':'),
        ("migrate", "the regex characters of the path are not escaped", "sed 's/[][\\.*^$#&/]/\\\\&/g'", "cat"),
        ("detect", "the new sd-solo link is never ours", 'case "$(readlink "$solo_link")" in "$H/bin/sd-solo"|"$H/bin/sd") solo_link_ours=1 ;; esac', ':'),
        ("detect", "another tree's launcher is taken for ours", ' && grep -qF "\'$H/bin/sd\'" "$link" 2>/dev/null', ''),
        ("detect", "a user's own file is taken for our launcher", "grep -qF 'SD Core for Linux Solo launcher.' \"$link\" 2>/dev/null && ", ""),
        ("source", "the Makefile still links bin/sd", "-o $(GPLBIN)sd-solo\n", "-o $(GPLBIN)sd\n"),
        ("source", "a C site still names bin/sd", '"%s/bin/" SD_SERVER_NAME, sysseg->sysdir) >= (MAX_PATHNAME_LEN + 1)) {', '"%s/bin/sd", sysseg->sysdir) >= (MAX_PATHNAME_LEN + 1)) {'),
    ]
    bad = 0
    for target, name, old, new in mutants:
        s_names, s_migrate, s_detect, s_src = names, migrate, detect, dict(src)
        if target == "source":
            where = "Makefile" if "GPLBIN" in old else "op_kernel.c"
            if where == "op_kernel.c":
                where = "op_kernel.c" if old in s_src["op_kernel.c"] else "sysseg.c"
            if s_src[where].count(old) != 1:
                print("REFUSED: mutant '%s' could not be applied to %s (%d matches)" % (name, where, s_src[where].count(old)), file=sys.stderr)
                sys.exit(2)
            s_src[where] = s_src[where].replace(old, new)
        else:
            code = {"names": names, "migrate": migrate, "detect": detect}[target]
            if code.count(old) != 1:
                print("REFUSED: mutant '%s' could not be applied (the text appears %d times)" % (name, code.count(old)), file=sys.stderr)
                sys.exit(2)
            mutated = code.replace(old, new)
            if target == "names":
                s_names = mutated
            elif target == "migrate":
                s_migrate = mutated
            else:
                s_detect = mutated
        s = Suite(s_names, s_migrate, s_detect, s_src)
        s.quiet = True
        with contextlib.redirect_stdout(io.StringIO()):
            s.suite()
        caught = s.failed > 0
        print("  mutant [%s] '%s': %s (%d of %d checks failed)" % (target, name, "CAUGHT" if caught else "NOT CAUGHT", s.failed, s.checks))
        bad += 0 if caught else 1
    print("selftest: %d mutants, %d not caught" % (len(mutants), bad))
    return 0 if bad == 0 else 1


def main(argv):
    names = cut_code(INSTALLER, "# BEGIN command_names", "# END command_names")
    migrate = cut_code(INSTALLER, "# BEGIN upgrade_rename", "# END upgrade_rename")
    detect = cut_code(DELETER, "# BEGIN link_detect", "# END link_detect")
    src = load_sources()
    print("test-soloexe-units inputs:")
    for label, path, code in (("command_names ", INSTALLER, names), ("upgrade_rename", INSTALLER, migrate), ("link_detect   ", DELETER, detect)):
        print("  %s: %s  (%d lines)" % (label, path, len(code.split("\n"))))
    print("  bash          : %s" % subprocess.run(["bash", "--version"], capture_output=True, text=True).stdout.split("\n")[0])
    if "install_command_names" not in names or "migrate_server_name" not in migrate or "link_ours" not in detect:
        print("REFUSED: the cut code does not define what the checks run; nothing could be measured", file=sys.stderr)
        return 2
    if argv[1:] == ["--selftest"]:
        return selftest(names, migrate, detect, src)
    if argv[1:]:
        print("usage: %s [--selftest]" % argv[0], file=sys.stderr)
        return 2
    s = Suite(names, migrate, detect, src)
    s.suite()
    print("\n%d checks, %d failed" % (s.checks, s.failed))
    if s.checks == 0:
        print("REFUSED: no check ran", file=sys.stderr)
        return 2
    print("PASSED" if s.failed == 0 else "FAILED")
    return 0 if s.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
