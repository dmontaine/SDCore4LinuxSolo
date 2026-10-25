#!/usr/bin/env python3
# test-shmmode-solo-units.py - W.11 F1 carried to Solo (25 Oct 2026): the shared segment and the semaphores are owner-only, and the daemon does not take
# what it runs from the segment.  FREE CHECK, text only (comments removed), no install, no sudo, no sd.  The full product's twin is its own
# test-shmmode-units.py, which reads 0660 and the group sdusers; Solo has one user and no such group, so the mode here is 0600.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-shmmode-solo-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-shmmode-solo-units.py --selftest      (mutants)
#
#   S1  sysseg.c create_shared_segment(): IPC_CREAT | 0600, never 0666 or 0660
#   S2  sdsem.c get_semaphores(): IPC_CREAT | IPC_EXCL | 0600, never 0666 or 0660
#   S3  sdlnxd.c: no use of sysseg->sysdir, no system() or popen(), "sd-solo -cleanup" started with execl, own_sysdir() called before the segment is attached
#   S4  own_sysdir() takes the directory from /proc/self/exe, wants the parent to be "bin", and wants <sysdir>/bin/sd-solo to be an executable regular file
# NOT SAID HERE: that a running SD makes the segment 0600 and that the daemon runs what it should - that is sandbox-shmmode-solo.py.
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "gplsrc"))
F = {"sysseg": os.path.join(SRC, "sysseg.c"), "sdsem": os.path.join(SRC, "sdsem.c"), "sdlnxd": os.path.join(SRC, "sdlnxd.c")}
for k in F:
    F[k] = os.environ.get("SHM_" + k.upper(), F[k])
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
    # the definition, not a prototype: after the head comes a "{" before any ";"
    m = re.search(re.escape(head) + r"[^;{]*\{.*?\n\}", src, re.S)
    return m.group(0) if m else ""


def run():
    ss = code(F["sysseg"])
    body = func(ss, "Private bool create_shared_segment(")
    row("S1 create_shared_segment() is found", bool(body))
    row("S1 the segment is created 0600 (owner only), never 0666 or 0660",
        "IPC_CREAT | 0600" in body and "0666" not in body and "0660" not in body, body[:200])
    se = code(F["sdsem"])
    body = func(se, "bool get_semaphores(")
    row("S2 get_semaphores() is found", bool(body))
    row("S2 the semaphores are created 0600, never 0666 or 0660 (the attach calls ask for 0666 as access bits, which is not a creation)",
        "IPC_CREAT | IPC_EXCL | 0600" in body and "IPC_CREAT | IPC_EXCL | 0666" not in body and "IPC_CREAT | IPC_EXCL | 0660" not in body)
    ld = code(F["sdlnxd"])
    row("S3 sdlnxd.c never reads sysseg->sysdir", "sysseg->sysdir" not in ld)
    row("S3 and never runs a shell command", not re.search(r"\b(system|popen)\s*\(", ld))
    row("S3 'sd-solo -cleanup' is started with execl", bool(re.search(r'execl\(cmd, SD_SERVER_NAME, "-cleanup"', ld)))
    row("S3 and the program it starts is <own sysdir>/bin/<server name>", bool(re.search(r'snprintf\(cmd, sizeof\(cmd\), "%s/bin/" SD_SERVER_NAME, own_sysdir_path\)', ld)))
    m_main = re.search(r"int main\(\) \{(.*?)\n\}", ld, re.S)
    mb = m_main.group(1) if m_main else ""
    i_own = mb.find("own_sysdir()")
    i_att = mb.find("shmat(")
    row("S3 own_sysdir() is called in main() before the segment is attached", 0 <= i_own < i_att, "own at %d, shmat at %d" % (i_own, i_att))
    row("S3 a daemon that cannot find its directory ends with status 3", bool(re.search(r"if \(!own_sysdir\(\)\) \{[^}]*exit\(3\);", mb)))
    od = func(ld, "static bool own_sysdir(void)")
    row("S4 the directory comes from /proc/self/exe", 'readlink("/proc/self/exe"' in od)
    row("S4 the parent must be bin", 'strcmp(slash, "/bin") != 0' in od)
    row("S4 <sysdir>/bin/sd-solo must be an executable regular file",
        '"%s/bin/" SD_SERVER_NAME' in od and "S_ISREG(st.st_mode)" in od and "access(sdpath, X_OK)" in od)
    row("S4 the log path is built from the daemon's own directory, with snprintf",
        bool(re.search(r'snprintf\(buff, BUFF_SIZE, "%s%cerrlog", own_sysdir_path, DS\)', ld)))
    print("test-shmmode-solo-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


def selftest():
    import shutil
    t = tempfile.mkdtemp()
    caught = missed = 0
    real = {k: open(v, encoding="latin-1").read() for k, v in F.items()}

    def mutant(name, which, old, new):
        nonlocal caught, missed
        if old not in real[which]:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            return
        f = os.path.join(t, name + ".c")
        open(f, "w", encoding="latin-1").write(real[which].replace(old, new, 1))
        env = dict(os.environ)
        env["SHM_" + which.upper()] = f
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print("  [caught] %s (exit %d)" % (name, r.returncode))
            caught += 1
        else:
            print("  [MISSED] %s: the check still passed" % name)
            missed += 1

    print("selftest: the real files first (must pass), then mutants (each must not)")
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real files do not pass:\n" + r.stdout[-600:])
        return 1
    print("  [ok] the real files pass")
    mutant("segment-0666", "sysseg", "IPC_CREAT | 0600", "IPC_CREAT | 0666")
    mutant("segment-0660", "sysseg", "IPC_CREAT | 0600", "IPC_CREAT | 0660")
    mutant("sem-0666", "sdsem", "IPC_CREAT | IPC_EXCL | 0600", "IPC_CREAT | IPC_EXCL | 0666")
    mutant("sem-0660", "sdsem", "IPC_CREAT | IPC_EXCL | 0600", "IPC_CREAT | IPC_EXCL | 0660")
    mutant("daemon-system-again", "sdlnxd", 'execl(cmd, SD_SERVER_NAME, "-cleanup", (char*)NULL);', 'system(cmd);')
    mutant("daemon-popen", "sdlnxd", 'execl(cmd, SD_SERVER_NAME, "-cleanup", (char*)NULL);', 'popen(cmd, "r");')
    mutant("daemon-segment-errlog", "sdlnxd", 'own_sysdir_path, DS) >= BUFF_SIZE', 'sysseg->sysdir, DS) >= BUFF_SIZE')
    mutant("daemon-segment-cleanup-path", "sdlnxd", '"%s/bin/" SD_SERVER_NAME, own_sysdir_path) >= (int)sizeof(cmd)',
           '"%s/bin/" SD_SERVER_NAME, sysseg->sysdir) >= (int)sizeof(cmd)')
    mutant("daemon-no-own-sysdir-call", "sdlnxd", "if (!own_sysdir()) {", "if (0) {")
    mutant("daemon-attaches-before-own-sysdir", "sdlnxd", "process.user_no = -2; /* Mark as sdlnxd for semaphore table */",
           "process.user_no = -2; /* Mark as sdlnxd for semaphore table */\n  shmat(0, NULL, 0);")
    mutant("daemon-exit-status-lost", "sdlnxd", "    exit(3);\n", "    exit(0);\n")
    mutant("daemon-no-bin-check", "sdlnxd", 'strcmp(slash, "/bin") != 0', "0")
    mutant("daemon-no-exec-check", "sdlnxd", "(access(sdpath, X_OK) != 0)", "0")
    mutant("daemon-no-regular-check", "sdlnxd", "!S_ISREG(st.st_mode)", "0")
    mutant("daemon-wrong-server-name", "sdlnxd", 'snprintf(sdpath, sizeof(sdpath), "%s/bin/" SD_SERVER_NAME, exe)',
           'snprintf(sdpath, sizeof(sdpath), "%s/bin/sd", exe)')
    mutant("daemon-exe-not-read", "sdlnxd", 'readlink("/proc/self/exe", exe, PATH_MAX)', 'readlink("/proc/self/cwd", exe, PATH_MAX)')
    shutil.rmtree(t, ignore_errors=True)
    print("selftest: %d of %d mutants caught, %d missed" % (caught, caught + missed, missed))
    return 0 if missed == 0 else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())
