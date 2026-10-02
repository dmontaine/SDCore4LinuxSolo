#!/usr/bin/env python3
# test-launcher-units.py - the command names installsdsolo.sh makes (owner, 2 Oct 2026).
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-launcher-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-launcher-units.py --selftest
#
# No sudo, no install, no sd.  It CUTS the shipped code out of installsdsolo.sh - the lines
# between "# BEGIN command_names" and "# END command_names" - and runs it with the
# installer's own bash in a scratch HOME, then RUNS the launcher it wrote against two fake
# programs, one standing for SD Core Solo and one for the multi-user SD Core.  What it
# measures is what a person types: "sd", "sd-solo", and which program answers.
#
# EVERY CHECK PRINTS THE COMMAND IT RAN AND WHAT IT SAW.  It refuses (exit 2) when the
# markers are not found exactly once, or when it could not have run the code at all, and
# --selftest breaks the shipped code five ways and requires the checks to catch each one.
#
# Exit 0 every check passed, 1 a check failed, 2 it could not measure.

import os
import shlex
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.normpath(os.path.join(HERE, "..", "..", "..", "installsdsolo.sh"))
DELETER = os.path.normpath(os.path.join(HERE, "..", "..", "..", "deletesdsolo.sh"))
BEGIN = "# BEGIN command_names"
END = "# END command_names"
DBEGIN = "# BEGIN link_detect"
DEND = "# END link_detect"
MARK = "SD Core for Linux Solo launcher."

FAKE = """#!/bin/sh
echo "%(name)s"
for a in "$@"; do printf '[%%s]\\n' "$a"; done
exit %(rc)d
"""


def cut_code(path, begin, end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    b = [i for i, l in enumerate(lines) if l.strip() == begin]
    e = [i for i, l in enumerate(lines) if l.strip() == end]
    if len(b) != 1 or len(e) != 1 or b[0] >= e[0]:
        print("REFUSED: %s must hold exactly one '%s' and one '%s' line, in that order "
              "(found %d and %d)" % (path, begin, end, len(b), len(e)), file=sys.stderr)
        sys.exit(2)
    return "\n".join(lines[b[0] + 1:e[0]])


class Suite:
    def __init__(self, code, dcode):
        self.code = code
        self.dcode = dcode
        self.checks = 0
        self.failed = 0
        self.quiet = False

    def check(self, name, expected, ok, saw):
        self.checks += 1
        if not ok:
            self.failed += 1
        if not self.quiet or not ok:
            print("  [%s] %s | expected: %s | saw: %s" % ("PASS" if ok else "FAIL", name, expected, saw))

    # one scratch world: home/.local/bin, tree/bin/sd (Solo), full/sd (the multi-user SD Core)
    def world(self, tmp, solo_rc=3, full_rc=7, with_full=False, full_exec=True):
        home = os.path.join(tmp, "home")
        tree = os.path.join(tmp, "tree dir")        # a space on purpose: nothing may split it
        full = os.path.join(tmp, "full", "sd")
        os.makedirs(os.path.join(home, ".local", "bin"))
        os.makedirs(os.path.join(tree, "bin"))
        os.makedirs(os.path.dirname(full))
        solo_bin = os.path.join(tree, "bin", "sd")
        with open(solo_bin, "w") as f:
            f.write(FAKE % {"name": "SOLO", "rc": solo_rc})
        os.chmod(solo_bin, 0o755)
        if with_full:
            self.put_full(full, full_rc, full_exec)
        return home, tree, full

    @staticmethod
    def put_full(full, rc=7, execbit=True):
        with open(full, "w") as f:
            f.write(FAKE % {"name": "FULL", "rc": rc})
        os.chmod(full, 0o755 if execbit else 0o644)

    def install(self, home, tree, full):
        script = ('set -euo pipefail\nwarn() { printf "WARN: %%s\\n" "$*" >&2; }\n'
                  'HOME=%s\n%s\ninstall_command_names %s %s\n'
                  % (shlex.quote(home), self.code, shlex.quote(tree), shlex.quote(full)))
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)

    @staticmethod
    def run(cmd, args):
        try:
            r = subprocess.run([cmd] + args, capture_output=True, text=True, timeout=30)
        except OSError as e:     # not executable, or gone: the check must fail, not the test
            return -1, "cannot run %s: %s" % (cmd, e)
        return r.returncode, r.stdout

    def suite(self):
        S = self
        # A1 a fresh install makes both commands
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            r = S.install(home, tree, full)
            b = os.path.join(home, ".local", "bin")
            sd, sdsolo = os.path.join(b, "sd"), os.path.join(b, "sd-solo")
            S.check("A0 the installer code ran to the end", "exit 0, no output on stderr",
                    r.returncode == 0 and r.stderr == "", "exit %d %r" % (r.returncode, r.stderr[:200]))
            isreg = os.path.isfile(sd) and not os.path.islink(sd)
            S.check("A1 'sd' is a launcher file, not a link", "a regular file with the marker line",
                    isreg and MARK in open(sd).read() if isreg else False,
                    "islink=%s exists=%s" % (os.path.islink(sd), os.path.exists(sd)))
            S.check("A1b it is executable", "mode 0755",
                    isreg and stat.S_IMODE(os.stat(sd).st_mode) == 0o755,
                    oct(stat.S_IMODE(os.stat(sd).st_mode)) if os.path.exists(sd) else "absent")
            S.check("A1c 'sd-solo' is a link to the Solo binary", "-> %s" % os.path.join(tree, "bin", "sd"),
                    os.path.islink(sdsolo) and os.readlink(sdsolo) == os.path.join(tree, "bin", "sd"),
                    os.readlink(sdsolo) if os.path.islink(sdsolo) else "not a link")
            left = [n for n in os.listdir(b) if n.startswith(".sd-launcher")]
            S.check("A1d no temporary file is left behind", "none", not left, left)

            # A2 the multi-user SD Core is NOT installed: sd starts Solo, arguments intact
            args = ["a", "b c", "", "-x"]
            rc, out = S.run(sd, args)
            S.check("A2 full absent: 'sd a \"b c\" \"\" -x' starts Solo, args intact, its exit code",
                    "SOLO then [a] [b c] [] [-x], exit 3",
                    out == "SOLO\n[a]\n[b c]\n[]\n[-x]\n" and rc == 3, "exit %d %r" % (rc, out))
            # A5 sd-solo is Solo whatever else is installed
            S.put_full(full)
            rc, out = S.run(sdsolo, ["q"])
            S.check("A5 full present: 'sd-solo q' still starts Solo", "SOLO then [q], exit 3",
                    out == "SOLO\n[q]\n" and rc == 3, "exit %d %r" % (rc, out))
            # A3 the multi-user SD Core installed: sd hands over to it, args and exit code intact
            rc, out = S.run(sd, args)
            S.check("A3 full present: 'sd a \"b c\" \"\" -x' starts the FULL product, args intact, its exit code",
                    "FULL then [a] [b c] [] [-x], exit 7",
                    out == "FULL\n[a]\n[b c]\n[]\n[-x]\n" and rc == 7, "exit %d %r" % (rc, out))
            # A4 a file at the full path that is not executable is not an installed product
            S.put_full(full, execbit=False)
            rc, out = S.run(sd, ["z"])
            S.check("A4 full path present but not executable: 'sd z' starts Solo", "SOLO then [z]",
                    out == "SOLO\n[z]\n" and rc == 3, "exit %d %r" % (rc, out))
            # A9 running the installer again changes nothing it should not
            before = open(sd).read()
            r2 = S.install(home, tree, full)
            S.check("A9 a second install rewrites the launcher identically", "same content, exit 0",
                    r2.returncode == 0 and open(sd).read() == before, "exit %d" % r2.returncode)

        # A6 an OLD install made 'sd' a link to the Solo binary: the link is replaced, the binary is not
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            os.symlink(os.path.join(tree, "bin", "sd"), os.path.join(b, "sd"))
            solo_before = open(os.path.join(tree, "bin", "sd")).read()
            r = S.install(home, tree, full)
            sd = os.path.join(b, "sd")
            S.check("A6 an old link 'sd -> the Solo binary' becomes the launcher", "a regular file; the Solo binary unchanged",
                    r.returncode == 0 and os.path.isfile(sd) and not os.path.islink(sd)
                    and open(os.path.join(tree, "bin", "sd")).read() == solo_before,
                    "exit %d islink=%s" % (r.returncode, os.path.islink(sd)))
            rc, out = S.run(sd, ["k"])
            S.check("A6b and it starts Solo", "SOLO then [k]", out == "SOLO\n[k]\n" and rc == 3, "exit %d %r" % (rc, out))

        # A10 a link to anything else is replaced, as it was before this change
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            os.symlink("/bin/true", os.path.join(b, "sd"))
            r = S.install(home, tree, full)
            S.check("A10 a link to some other program is replaced", "a regular launcher file",
                    r.returncode == 0 and os.path.isfile(os.path.join(b, "sd")) and not os.path.islink(os.path.join(b, "sd")),
                    "exit %d" % r.returncode)

        # A7 a file of the user's own named 'sd' is left alone, with a warning, and sd-solo still works
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            mine = "#!/bin/sh\necho mine\n"
            with open(os.path.join(b, "sd"), "w") as f:
                f.write(mine)
            r = S.install(home, tree, full)
            S.check("A7 the user's own 'sd' file is left alone and named in a warning",
                    "content unchanged; WARN names it; exit 0",
                    r.returncode == 0 and open(os.path.join(b, "sd")).read() == mine
                    and "neither a link nor this product's launcher" in r.stderr,
                    "exit %d stderr=%r" % (r.returncode, r.stderr[:200]))
            S.check("A7b 'sd-solo' is made all the same", "a link to the Solo binary",
                    os.path.islink(os.path.join(b, "sd-solo")),
                    "link -> " + os.readlink(os.path.join(b, "sd-solo")) if os.path.islink(os.path.join(b, "sd-solo")) else "no link")

        # A8 a file of the user's own named 'sd-solo' is left alone, and sd is still written
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            mine = "#!/bin/sh\necho mine\n"
            with open(os.path.join(b, "sd-solo"), "w") as f:
                f.write(mine)
            r = S.install(home, tree, full)
            S.check("A8 the user's own 'sd-solo' file is left alone and named in a warning",
                    "content unchanged; WARN names it; exit 0",
                    r.returncode == 0 and open(os.path.join(b, "sd-solo")).read() == mine
                    and "sd-solo exists and is not a link" in r.stderr,
                    "exit %d stderr=%r" % (r.returncode, r.stderr[:200]))
            wrote = os.path.isfile(os.path.join(b, "sd")) and MARK in open(os.path.join(b, "sd")).read()
            S.check("A8b 'sd' is written all the same", "the launcher", wrote,
                    "a launcher file with the marker" if wrote else "no launcher")

        # A11 an earlier launcher of this product is rewritten for the tree being installed
        with tempfile.TemporaryDirectory() as tmp:
            home, tree, full = S.world(tmp)
            b = os.path.join(home, ".local", "bin")
            with open(os.path.join(b, "sd"), "w") as f:
                f.write("#!/bin/sh\n# %s old\nexec '/old/tree/bin/sd' \"$@\"\n" % MARK)
            r = S.install(home, tree, full)
            S.check("A11 an earlier launcher is rewritten for this tree", "names %s, not /old/tree" % tree,
                    r.returncode == 0 and tree in open(os.path.join(b, "sd")).read()
                    and "/old/tree" not in open(os.path.join(b, "sd")).read(), "exit %d" % r.returncode)

        self.suite_delete()

    # deletesdsolo.sh: which of the two commands is THIS tree's to remove.  The block it cuts out
    # sets link_ours (sd) and solo_link_ours (sd-solo) from $HOME and $H.
    def detect(self, home, tree):
        script = 'set -uo pipefail\nHOME=%s\nH=%s\n%s\necho "$link_ours $solo_link_ours"\n' % (
            shlex.quote(home), shlex.quote(tree), self.dcode)
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60)
        return r.stdout.strip(), r

    def suite_delete(self):
        S = self
        launcher_for = lambda t: "#!/bin/sh\n# %s\nif [ -x '/x/sd' ]; then exec '/x/sd' \"$@\"; fi\nexec '%s/bin/sd' \"$@\"\n" % (MARK, t)
        cases = [
            # id, what 'sd' is, what 'sd-solo' is, expected "link_ours solo_link_ours"
            ("D1 'sd' is this tree's launcher and 'sd-solo' its link", "launcher", "link", "1 1"),
            ("D2 'sd' is an old link to this tree", "oldlink", "none", "1 0"),
            ("D3 'sd' is ANOTHER tree's launcher: not ours", "otherlauncher", "otherlink", "0 0"),
            ("D4 'sd' is the user's own file: not ours", "mine", "mine", "0 0"),
            ("D5 'sd' is a link elsewhere: not ours", "elsewhere", "elsewhere", "0 0"),
            ("D6 nothing is there", "none", "none", "0 0"),
            ("D7 'sd' is the user's own script that runs THIS tree's binary but has no marker: not ours",
             "ownscript", "none", "0 0"),
        ]
        for name, sd_kind, solo_kind, want in cases:
            with tempfile.TemporaryDirectory() as tmp:
                home, tree, full = S.world(tmp)
                other = os.path.join(tmp, "other tree")
                os.makedirs(os.path.join(other, "bin"))
                b = os.path.join(home, ".local", "bin")
                sd, sds = os.path.join(b, "sd"), os.path.join(b, "sd-solo")
                mine = "#!/bin/sh\necho mine\n"
                for path, kind in ((sd, sd_kind), (sds, solo_kind)):
                    if kind == "launcher":
                        open(path, "w").write(launcher_for(tree))
                    elif kind == "otherlauncher":
                        open(path, "w").write(launcher_for(other))
                    elif kind == "link":
                        os.symlink(os.path.join(tree, "bin", "sd"), path)
                    elif kind == "oldlink":
                        os.symlink(os.path.join(tree, "bin", "sd"), path)
                    elif kind == "otherlink":
                        os.symlink(os.path.join(other, "bin", "sd"), path)
                    elif kind == "elsewhere":
                        os.symlink("/bin/true", path)
                    elif kind == "mine":
                        open(path, "w").write(mine)
                    elif kind == "ownscript":
                        open(path, "w").write("#!/bin/sh\nexec '%s/bin/sd' \"$@\"\n" % tree)
                got, r = S.detect(home, tree)
                S.check(name, "link_ours solo_link_ours = %s" % want, got == want and r.returncode == 0,
                        "%r (exit %d) with sd=%s sd-solo=%s" % (got, r.returncode, sd_kind, solo_kind))


def selftest(code, dcode):
    mutants = [
        ("install", "the full product is never chosen",
         "if [ -x '$full' ]; then exec '$full' \"\\$@\"; fi\n", ""),
        ("install", "the arguments are dropped", "exec '$solo' \"\\$@\"", "exec '$solo'"),
        ("install", "a user's own 'sd' file is overwritten",
         "&& ! grep -qF 'SD Core for Linux Solo launcher.' \"$bindir/sd\" 2>/dev/null", "&& false"),
        ("install", "'sd-solo' points at the wrong program", "ln -sfn \"$tree/bin/sd\" \"$bindir/sd-solo\"",
         "ln -sfn \"$full\" \"$bindir/sd-solo\""),
        ("install", "the launcher is not executable", "chmod 755 \"$tmpl\"", "chmod 644 \"$tmpl\""),
        ("delete", "another tree's launcher is taken for ours", " && grep -qF \"'$H/bin/sd'\" \"$link\" 2>/dev/null", ""),
        ("delete", "a user's own file is taken for our launcher",
         "grep -qF 'SD Core for Linux Solo launcher.' \"$link\" 2>/dev/null && ", ""),
        ("delete", "the sd-solo link is never ours", "solo_link_ours=1", "solo_link_ours=0"),
    ]
    bad = 0
    for target, name, old, new in mutants:
        src = code if target == "install" else dcode
        if src.count(old) != 1:
            print("REFUSED: mutant '%s' could not be applied (the text appears %d times)" % (name, src.count(old)),
                  file=sys.stderr)
            sys.exit(2)
        mutated = src.replace(old, new)
        s = Suite(mutated if target == "install" else code, mutated if target == "delete" else dcode)
        s.quiet = True
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            s.suite()
        caught = s.failed > 0
        print("  mutant [%s] '%s': %s (%d of %d checks failed)" % (target, name, "CAUGHT" if caught else "NOT CAUGHT", s.failed, s.checks))
        bad += 0 if caught else 1
    print("selftest: %d mutants, %d not caught" % (len(mutants), bad))
    return 0 if bad == 0 else 1


def main(argv):
    code = cut_code(INSTALLER, BEGIN, END)
    dcode = cut_code(DELETER, DBEGIN, DEND)
    print("test-launcher-units inputs:")
    print("  installer : %s  (%d lines between '%s' and '%s')" % (INSTALLER, len(code.split("\n")), BEGIN, END))
    print("  uninstaller: %s  (%d lines between '%s' and '%s')" % (DELETER, len(dcode.split("\n")), DBEGIN, DEND))
    print("  bash      : %s" % subprocess.run(["bash", "--version"], capture_output=True, text=True).stdout.split("\n")[0])
    if "install_command_names" not in code or "write_launcher" not in code or "link_ours" not in dcode:
        print("REFUSED: the cut code does not define what the checks run; nothing could be measured",
              file=sys.stderr)
        return 2
    if argv[1:] == ["--selftest"]:
        return selftest(code, dcode)
    if argv[1:]:
        print("usage: %s [--selftest]" % argv[0], file=sys.stderr)
        return 2
    s = Suite(code, dcode)
    s.suite()
    print("\n%d checks, %d failed" % (s.checks, s.failed))
    if s.checks == 0:
        print("REFUSED: no check ran", file=sys.stderr)
        return 2
    print("PASSED" if s.failed == 0 else "FAILED")
    return 0 if s.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
