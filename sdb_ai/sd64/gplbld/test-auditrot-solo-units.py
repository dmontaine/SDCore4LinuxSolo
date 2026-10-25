#!/usr/bin/env python3
# test-auditrot-solo-units.py - W.11 carry, step 3 (25 Oct 2026): Solo's audit_rotate() (k_error.c, called by start_sd() at "sd-solo -start") does not rotate onto a name that
# is already a file.  The rotated name has a second's resolution and rename() replaces what is there, so two rotations in one second used to destroy the first rotated file.
# SD Core found it with a sandbox (W11 of sandbox-auditwriter.py) and refused the rotation in audit_rotate_file(); Solo keeps its rotation inline.  FREE CHECK, text only
# (comments removed), no install, no sudo, no sd.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-auditrot-solo-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-auditrot-solo-units.py --selftest      (mutants)
#
#   A1  audit_rotate() is found and still rotates at AUDIT_ROTATE_BYTES (1 MB) onto "<trail>.YYYYMMDD-HHMMSS"
#   A2  it asks lstat(rotated) and treats "exists" and "any error other than ENOENT" as a refusal that leaves through the function's one exit
#   A3  and it asks BEFORE it opens the trail, lifts the append-only attribute or renames anything - so a refusal has nothing to undo
#   A4  the rotation itself is unchanged: rename(path, rotated), a new file made O_EXCL with the old owner and mode, the attribute given back to both
# NOT SAID HERE: that the trail stays whole and a taken name is left alone when SD starts - sandbox-auditrot-solo.py (it also rotates once with the name free).
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "gplsrc", "k_error.c"))
FILE = os.environ.get("AUDROT_K_ERROR", SRC)
passed = failed = 0


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  [PASS] " + name)
    else:
        failed += 1
        print("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def code(path):
    s = open(path, encoding="latin-1").read()
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


def func(src, head):
    m = re.search(re.escape(head) + r"[^;{]*\{.*?\n\}", src, re.S)
    return m.group(0) if m else ""


def run():
    src = code(FILE)
    body = func(src, "void audit_rotate(void)")
    row("A1 audit_rotate() is found, rotates at AUDIT_ROTATE_BYTES and names the file <trail>.YYYYMMDD-HHMMSS",
        bool(body) and "st_size >= AUDIT_ROTATE_BYTES" in body and '"%s.%04d%02d%02d-%02d%02d%02d"' in body and "#define AUDIT_ROTATE_BYTES 1048576L" in src, body[:120])
    guard = "if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))\n        goto exit_audit_rotate;"
    row("A2 a rotated name that exists - or that cannot be looked at - refuses the rotation through the function's exit (lstat, not stat: a link there counts)",
        "struct stat existing;" in body and guard in body and body.count("goto exit_audit_rotate;") == 2 and body.count("exit_audit_rotate:") == 1, "")
    i_g = body.find(guard)
    i_name = body.find("snprintf(rotated")
    i_open = body.find("open(path, O_RDONLY")
    i_lift = body.find("FS_IOC_SETFLAGS")
    i_ren = body.find("rename(path, rotated)")
    row("A3 it asks after the name is built and BEFORE the trail is opened, the attribute lifted or anything renamed",
        0 <= i_name < i_g < i_open < i_lift < i_ren, "positions name %d guard %d open %d lift %d rename %d" % (i_name, i_g, i_open, i_lift, i_ren))
    row("A4 the rotation is unchanged: the new file is O_CREAT | O_EXCL | O_NOFOLLOW with the old owner and mode, and the attribute goes back on both files",
        "O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW" in body and "fchown(newfd, statbuf.st_uid, statbuf.st_gid)" in body and "fchmod(newfd, statbuf.st_mode & 07777)" in body
        and body.count("FS_APPEND_FL") >= 4 and "if (had_append) {" in body and "if (had_append &&" in body, "")
    print("test-auditrot-solo-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


MUTANTS = [   # name, old, new
    ("no-guard", "      if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))\n        goto exit_audit_rotate;\n", ""),
    ("guard-exists-only", "if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))", "if (lstat(rotated, &existing) == 0)"),
    ("guard-uses-stat", "if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))", "if ((stat(rotated, &existing) == 0) || (errno != ENOENT))"),
    ("guard-does-not-leave", "        goto exit_audit_rotate;\n      fd = open(path, O_RDONLY", "        ;\n      fd = open(path, O_RDONLY"),
    ("guard-refuses-everything", "if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))", "if (1)"),
    ("guard-after-open", "      if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))\n        goto exit_audit_rotate;\n      fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);",
     "      fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);\n      if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))\n        goto exit_audit_rotate;"),
    ("guard-before-the-name", "    if (snprintf(rotated, sizeof(rotated),", "    if ((lstat(rotated, &existing) == 0) || (errno != ENOENT))\n      goto exit_audit_rotate;\n    if (snprintf(rotated, sizeof(rotated),"),
    ("name-without-seconds", '"%s.%04d%02d%02d-%02d%02d%02d", path,\n                 ltime->tm_year + 1900, ltime->tm_mon + 1, ltime->tm_mday,\n                 ltime->tm_hour, ltime->tm_min, ltime->tm_sec)',
     '"%s.%04d%02d%02d-%02d%02d", path,\n                 ltime->tm_year + 1900, ltime->tm_mon + 1, ltime->tm_mday,\n                 ltime->tm_hour, ltime->tm_min)'),
    ("rotation-threshold-gone", "(statbuf.st_size >= AUDIT_ROTATE_BYTES)", "(statbuf.st_size >= 0)"),
    ("new-file-not-exclusive", "O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW", "O_WRONLY | O_CREAT | O_NOFOLLOW"),
]


def selftest(start=0):
    import shutil
    t = tempfile.mkdtemp()
    caught = missed = 0
    print("selftest: the real file first (must pass), then mutants from number %d (each must not)" % start)
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real file does not pass:\n" + r.stdout[-900:])
        return 1
    print("  [ok] the real file passes")
    real = open(SRC, encoding="latin-1").read()
    for name, old, new in MUTANTS[start:]:
        if old not in real:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            continue
        f = os.path.join(t, name + ".c")
        open(f, "w", encoding="latin-1").write(real.replace(old, new, 1))
        env = dict(os.environ, AUDROT_K_ERROR=f)
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print("  [caught] %s (exit %d)" % (name, r.returncode))
            caught += 1
        else:
            print("  [MISSED] %s: the check still passed" % name)
            missed += 1
    shutil.rmtree(t, ignore_errors=True)
    print("selftest: %d of %d mutants caught, %d missed" % (caught, caught + missed, missed))
    return 0 if missed == 0 and caught > 0 else 1


if __name__ == "__main__":
    _from = [int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--from=")]
    sys.exit(selftest(_from[0] if _from else 0) if "--selftest" in sys.argv else run())
