#!/usr/bin/env python3
# test-auditjournal-units.py - W.11 F4, option B, in SD Core Solo for Linux: every audit record is ALSO sent to the system journal, whose daemon
# stamps the sender's real uid and pid, and which the Solo user cannot rewrite (the audit file is that user's own).  FREE CHECK, text only (comments
# removed), no install, no sudo, no sd.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-auditjournal-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-auditjournal-units.py --selftest      (mutants)
#
# START-HISTORY
# 18 Nov 26 dm  S.62 (P-6770 to P-6773), carried from SD Core for Linux (its test-auditjournal-units.py of 24 Oct 26).  Solo's audit_message() writes the
#               file itself (no audit daemon, no audit socket: PAL-40), so J3 and J4 look for the call after the function's own EndExclusive(ERRLOG_SEM)
#               where Core's look after its call of audit_append_file(); the mutant "only-when-the-daemon-did-not-take-it" became
#               "only-when-the-file-opened".
# END-HISTORY
#
#   J1  k_error.c includes <syslog.h>
#   J2  audit_message() makes exactly one syslog() call: facility LOG_AUTHPRIV, level LOG_NOTICE, the format "sd-audit %s" (the record is an ARGUMENT, never the format)
#   J3  it is made AFTER EndExclusive(ERRLOG_SEM): a stalled syslog socket must not hold the semaphore every session's audit and error logging waits on
#   J4  it is made whether or not the file could be opened or written (the copy is the point when the file is not available), guarded only by "bytes > 0"
#   J5  the record's trailing newline is removed first, and the text is the SAME buffer the file got (one record, two places)
# NOT SAID HERE: that the journal holds the record with the right _UID and _PID - Solo has no sandbox of its own; that is a real-install witness.
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "gplsrc"))
F = os.environ.get("AJ_KERROR", os.path.join(SRC, "k_error.c"))
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
    k = code(F)
    row("J1 k_error.c includes <syslog.h>", "#include <syslog.h>" in k)
    am = func(k, "void audit_message(char* msg)")
    row("J0 audit_message() is found", bool(am))
    calls = re.findall(r"\bsyslog\s*\(([^;]*)\);", k)
    row("J2 k_error.c makes exactly one syslog() call, in audit_message(): LOG_AUTHPRIV | LOG_NOTICE, the format \"sd-audit %s\", the record as an argument",
        len(calls) == 1 and "syslog(" in am and re.fullmatch(r'\s*LOG_AUTHPRIV\s*\|\s*LOG_NOTICE\s*,\s*"sd-audit %s"\s*,\s*buff\s*', calls[0]) is not None, "calls: %r" % (calls,))
    i_start, i_end, i_sys = am.find("StartExclusive(ERRLOG_SEM"), am.rfind("EndExclusive(ERRLOG_SEM);"), am.find("syslog(")
    row("J3 audit_message() takes ERRLOG_SEM once, for the file, and the syslog() call comes after it is released",
        am.count("StartExclusive") == 1 and am.count("EndExclusive") == 1 and 0 <= i_start < i_end < i_sys,
        "start at %d, end at %d, syslog at %d" % (i_start, i_end, i_sys))
    tail = am[i_end:] if i_end >= 0 else ""
    row("J4 and the copy is made whether or not the file was written: guarded only by 'bytes > 0', outside the file branch",
        re.search(r"EndExclusive\(ERRLOG_SEM\);\s*if \(bytes > 0\) \{\s*buff\[bytes - 1\] = '\\0';\s*syslog\(", tail) is not None, tail[:200])
    row("J5 the trailing newline is removed before the record goes to the journal", "buff[bytes - 1] = '\\0';" in tail)
    i_wr, i_nul = am.find("write(fd, buff, bytes)"), am.find("buff[bytes - 1] = '\\0';")
    row("J5b and the file got the record WITH its newline first (the write precedes the cut)", 0 <= i_wr < i_nul, "write at %d, cut at %d" % (i_wr, i_nul))
    print("test-auditjournal-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


MUTANTS = [
    ("no-syslog-call", '    syslog(LOG_AUTHPRIV | LOG_NOTICE, "sd-audit %s", buff);\n', ""),
    ("wrong-facility", "syslog(LOG_AUTHPRIV | LOG_NOTICE,", "syslog(LOG_LOCAL1 | LOG_NOTICE,"),
    ("record-as-format", 'syslog(LOG_AUTHPRIV | LOG_NOTICE, "sd-audit %s", buff);', "syslog(LOG_AUTHPRIV | LOG_NOTICE, buff);"),
    ("no-prefix", '"sd-audit %s"', '"%s"'),
    ("inside-the-semaphore", "  EndExclusive(ERRLOG_SEM);\n\n  if (bytes > 0) {",
     "  if (bytes > 0) {\n    syslog(LOG_AUTHPRIV | LOG_NOTICE, \"sd-audit %s\", buff);\n  }\n  EndExclusive(ERRLOG_SEM);\n\n  if (bytes > 0) {"),
    ("only-when-file-written", "      if (write(fd, buff, bytes) != bytes) {\n        /* silent - see the banner */\n      }\n      close(fd);",
     "      if (write(fd, buff, bytes) == bytes) {\n        syslog(LOG_AUTHPRIV | LOG_NOTICE, \"sd-audit %s\", buff);\n      }\n      close(fd);"),
    ("only-when-the-file-opened", "  EndExclusive(ERRLOG_SEM);\n\n  if (bytes > 0) {", "  EndExclusive(ERRLOG_SEM);\n\n  if ((bytes > 0) && (fd >= 0)) {"),
    ("newline-kept", "    buff[bytes - 1] = '\\0';\n", ""),
    ("include-gone", "#include <syslog.h>\n", ""),
]


def selftest():
    import shutil
    t = tempfile.mkdtemp()
    caught = missed = 0
    real = open(F, encoding="latin-1").read()
    print("selftest: the real file first (must pass), then mutants (each must not)")
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real file does not pass:\n" + r.stdout[-600:])
        return 1
    print("  [ok] the real file passes")
    for name, old, new in MUTANTS:
        if old not in real:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            continue
        f = os.path.join(t, name + ".c")
        open(f, "w", encoding="latin-1").write(real.replace(old, new, 1))
        env = dict(os.environ, AJ_KERROR=f)
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
    sys.exit(selftest() if "--selftest" in sys.argv else run())
