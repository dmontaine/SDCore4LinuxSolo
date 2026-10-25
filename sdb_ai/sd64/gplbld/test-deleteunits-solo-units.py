#!/usr/bin/env python3
# test-deleteunits-solo-units.py - the uninstaller removes the systemd user units OR LEAVES THE TREE (25 Oct 2026, a follow-up of the real-install witness).  Found on the VM: a shell with no
# user-manager environment made "solo-service.sh remove" refuse, its output went through "| tail -2", and deletesdsolo.sh went on and deleted ~/SDCoreSolo, leaving sd-solo.service (enabled),
# the daemon unit and the AI units pointing at nothing.  FREE CHECK: no install, no sudo, no systemd, nothing of the user's is touched - it cuts the block between "# BEGIN remove_units" and
# "# END remove_units" and the call that follows "# ---- 1." out of deletesdsolo.sh and RUNS them under bash in a scratch directory (HOME and the unit directory in it) with a stub
# solo-service.sh and a stub systemctl first on PATH.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-deleteunits-solo-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-deleteunits-solo-units.py --selftest      (mutants)
#
#   T1  solo-service.sh remove succeeds: nothing more is done, the script goes on to the tree
#   T2  it REFUSES (exit 2) and the units are there: the unit files AND the links that enable them are removed by hand, only Solo's names (sd-solo*), and the script goes on
#   T3  it refuses and the unit files cannot be removed (a read-only directory): the script STOPS with "THE INSTALLATION DIRECTORY AND YOUR DATA WERE NOT TOUCHED" and never reaches the tree
#   T4  it refuses and there are no units (a install with no service): harmless, the script goes on
#   T5  no solo-service.sh in the tree: the daemon unit is stopped FIRST, the units disabled, the files removed; and a read-only directory stops it the same way
#   T6  user_manager_env: fills XDG_RUNTIME_DIR and the D-Bus address from the run directory when the shell has neither and the manager's socket is there; leaves both alone otherwise
#   T7  the call stands before anything that deletes the tree
# NOT SAID HERE: that a real systemd user manager lets go of the units - that is the VM witness (witness-solo-w11.py, rows X).
import os
import re
import socket
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.normpath(os.path.join(HERE, "..", "..", "..", "deletesdsolo.sh"))
FILE = os.environ.get("LDU_DELETESDSOLO", REAL)
passed = failed = 0
UNITS = ["sd-solo.service", "sd-solo-lnxd.service", "sd-solo-api.socket", "sd-solo-api@.service", "sd-solo-ssh.socket", "sd-solo-ssh@.service", "sd-solo-ai.socket", "sd-solo-ai@.service"]
OTHERS = ["sd-other.service", "keep.service", "sd.service"]       # not Solo's: must be left alone


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  [PASS] " + name)
    else:
        failed += 1
        print("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def pieces():
    s = open(FILE, encoding="latin-1").read()
    m = re.search(r"# BEGIN remove_units\n.*?# END remove_units\n", s, re.S)
    c = re.search(r"# ---- 1\. the service and the daemon\n(.*?)\nfor n in sd-solo sd; do", s, re.S)
    return (m.group(0) if m else ""), (c.group(1) if c else ""), s


STUB_OK = '#!/bin/bash\n[ "$1" = remove ] || exit 9\nd="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"\nrm -f "$d"/sd-solo* "$d"/*.wants/sd-solo*\necho "SOLO SERVICE REMOVED"\nexit 0\n'
STUB_REFUSE = '#!/bin/bash\necho "REFUSED: the user systemd manager is not running (said: offline)" >&2\nexit 2\n'


def scenario(stub, units=True, readonly=False, with_script=True):
    """run the block and the call in a scratch home; returns (rc, output, left (list of unit paths), log (systemctl calls), others_ok, reached)"""
    block, call, _ = pieces()
    root = tempfile.mkdtemp(prefix="ldu")
    try:
        home = os.path.join(root, "home")
        ud = os.path.join(home, ".config", "systemd", "user")
        for sub in ("", "default.target.wants", "sockets.target.wants"):
            os.makedirs(os.path.join(ud, sub), exist_ok=True)
        if units:
            for n in UNITS:
                open(os.path.join(ud, n), "w").write("[Unit]\n")
            os.symlink(os.path.join(ud, "sd-solo.service"), os.path.join(ud, "default.target.wants", "sd-solo.service"))
            os.symlink(os.path.join(ud, "sd-solo-api.socket"), os.path.join(ud, "sockets.target.wants", "sd-solo-api.socket"))
        for n in OTHERS:
            open(os.path.join(ud, n), "w").write("[Unit]\n")
        tree = os.path.join(root, "tree")
        os.makedirs(os.path.join(tree, "tools"))
        if with_script:
            p = os.path.join(tree, "tools", "solo-service.sh")
            open(p, "w").write(stub)
        shim = os.path.join(root, "shim")
        os.makedirs(shim)
        log = os.path.join(root, "systemctl.log")
        sc = os.path.join(shim, "systemctl")
        open(sc, "w").write('#!/bin/bash\necho "$*" >> "%s"\nexit 0\n' % log)
        os.chmod(sc, 0o755)
        runner = os.path.join(root, "run.sh")
        open(runner, "w").write('set -uo pipefail\nH="%s"\nwarn() { printf "WARN: %%s\\n" "$*"; }\nfail() { printf "FAILED: %%s\\n" "$*" >&2; exit 1; }\nsay() { printf "%%s\\n" "$*"; }\n%s\n%s\n'
                                'echo REACHED-THE-TREE\n' % (tree, block, call))
        if readonly:
            for sub in ("", "default.target.wants", "sockets.target.wants"):
                os.chmod(os.path.join(ud, sub), 0o500)
        env = {"HOME": home, "PATH": shim + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
        p = subprocess.run(["bash", runner], capture_output=True, text=True, errors="replace", env=env, timeout=60)
        for sub in ("", "default.target.wants", "sockets.target.wants"):
            os.chmod(os.path.join(ud, sub), 0o700)
        left = sorted(os.path.relpath(os.path.join(d, f), ud) for d, _, fs in os.walk(ud) for f in fs if f.startswith("sd-solo"))
        others_ok = all(os.path.exists(os.path.join(ud, n)) for n in OTHERS)
        calls = open(log).read().strip().split("\n") if os.path.exists(log) else []
        return p.returncode, p.stdout + p.stderr, left, calls, others_ok, "REACHED-THE-TREE" in p.stdout
    finally:
        for d, ds, fs in os.walk(root):
            for x in ds:
                os.chmod(os.path.join(d, x), 0o700)
        shutil.rmtree(root, ignore_errors=True)


def env_case(mode):
    """user_manager_env RUNDIR in a bash with the given environment; returns the two variables afterwards, ' '-joined"""
    block, _, _ = pieces()
    root = tempfile.mkdtemp(prefix="lde")
    try:
        run = os.path.join(root, "run")
        os.makedirs(run)
        if mode in ("fills", "xdg-set-no-bus", "dbus-set"):
            s = socket.socket(socket.AF_UNIX)
            s.bind(os.path.join(run, "bus"))
            s.close()
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        rundir = run
        if mode == "no-run-dir":
            rundir = os.path.join(root, "absent")
        if mode == "xdg-set-no-bus":
            env["XDG_RUNTIME_DIR"] = os.path.join(root, "elsewhere")
        if mode == "dbus-set":
            env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/already/set"
        script = 'set -uo pipefail\nwarn() { :; }\nfail() { exit 1; }\nsay() { :; }\n%s\nuser_manager_env "%s"\necho "XDG=${XDG_RUNTIME_DIR:-}|DBUS=${DBUS_SESSION_BUS_ADDRESS:-}"\n' % (block, rundir)
        p = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=30)
        return p.stdout.strip().replace(root, "<scratch>"), run.replace(root, "<scratch>")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run():
    block, call, whole = pieces()
    row("T0 the block and the call are found in deletesdsolo.sh", bool(block) and bool(call), "block %d chars, call %d chars" % (len(block), len(call)))
    if not (block and call):
        print("test-deleteunits-solo-units: %d passed, %d failed" % (passed, failed))
        return 1
    rc, out, left, calls, ok, reached = scenario(STUB_OK)
    row("T1 solo-service.sh remove succeeds: the script goes on to the tree, no warning, and no unit of Solo's is left", rc == 0 and reached and left == [] and "WARN" not in out and ok, "rc %d, left %r, out %r" % (rc, left, out[-160:]))
    rc, out, left, calls, ok, reached = scenario(STUB_REFUSE)
    row("T2 it REFUSES (exit 2) with the units there: a warning, the unit files AND their links removed by hand, the script goes on, and no file that is not Solo's was touched",
        rc == 0 and reached and left == [] and "WARN" in out and ok, "rc %d, left %r, others kept %s, out %r" % (rc, left, ok, out[-200:]))
    row("T2b and systemd is told to reload after the files went", any("daemon-reload" in c for c in calls), "calls %r" % calls)
    rc, out, left, calls, ok, reached = scenario(STUB_REFUSE, readonly=True)
    row("T3 it refuses and the files cannot be removed (read-only directories): the script STOPS with 'THE INSTALLATION DIRECTORY AND YOUR DATA WERE NOT TOUCHED', names what is left, and never reaches the tree",
        rc == 1 and not reached and "FAILED" in out and "THE INSTALLATION DIRECTORY AND YOUR DATA WERE NOT TOUCHED" in out and "sd-solo.service" in out and len(left) > 0, "rc %d, reached %s, left %d, out %r" % (rc, reached, len(left), out[-240:]))
    rc, out, left, calls, ok, reached = scenario(STUB_REFUSE, units=False)
    row("T4 it refuses and there are no units (an install with no service): harmless, the script goes on", rc == 0 and reached and left == [], "rc %d, out %r" % (rc, out[-160:]))
    rc, out, left, calls, ok, reached = scenario("", with_script=False)
    i_stop = next((i for i, c in enumerate(calls) if "stop sd-solo-lnxd.service" in c), -1)
    i_dis = next((i for i, c in enumerate(calls) if c.startswith("--user disable --now")), -1)
    row("T5 no solo-service.sh in the tree: the daemon unit is stopped FIRST, the units disabled, the files removed, and the script goes on", rc == 0 and reached and left == [] and 0 <= i_stop < i_dis and ok,
        "rc %d, left %r, stop at %d, disable at %d" % (rc, left, i_stop, i_dis))
    rc, out, left, calls, ok, reached = scenario("", with_script=False, readonly=True)
    row("T5b no solo-service.sh and the files cannot be removed: the same stop, and the tree is not reached", rc == 1 and not reached and "THE INSTALLATION DIRECTORY AND YOUR DATA WERE NOT TOUCHED" in out, "rc %d, reached %s" % (rc, reached))
    got, run_dir = env_case("fills")
    row("T6a no XDG_RUNTIME_DIR and no D-Bus address, the run directory and its bus socket there: both are filled in from it", got == "XDG=%s|DBUS=unix:path=%s/bus" % (run_dir, run_dir), got)
    got, _ = env_case("no-run-dir")
    row("T6b the run directory is not there: nothing is invented", got == "XDG=|DBUS=", got)
    got, _ = env_case("xdg-set-no-bus")
    row("T6c XDG_RUNTIME_DIR already set by the shell: it is NOT replaced, and with no bus socket there the address stays empty", got.startswith("XDG=<scratch>/elsewhere|") and got.endswith("DBUS="), got)
    got, _ = env_case("dbus-set")
    row("T6d a D-Bus address already set: it is NOT replaced", got.endswith("DBUS=unix:path=/already/set"), got)
    i_call = whole.find("remove_units_step \"$H\" \"$UNITDIR\"")
    i_tree = whole.find('rm -rf "$H"')
    i_keep = whole.find('keep_prune "$H" ||')
    i_stop = whole.find('"$H/bin/$n" -stop')
    row("T7 the call stands before the daemon is stopped, the tree pruned or deleted", 0 <= i_call < i_stop and i_call < i_keep and i_call < i_tree, "positions call %d stop %d keep %d rm %d" % (i_call, i_stop, i_keep, i_tree))
    i_env = whole.find('user_manager_env "/run/user/$(id -u)"', whole.find("# END remove_units"))
    row("T7b the shell is given the user manager's environment (the run directory of THIS user) before the units are asked about", 0 <= i_env < i_call, "positions env %d call %d" % (i_env, i_call))
    print("test-deleteunits-solo-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


MUTANTS = [   # name, old, new
    ("failed-remove-ignored", '    if [ "$rc" -ne 0 ]; then\n      warn "solo-service.sh could not', '    if false; then\n      warn "solo-service.sh could not'),
    ("no-left-check", '  [ -z "$(unit_files_left "$unitdir")" ]\n}', '  true\n}'),
    ("call-only-warns", '  || fail "the systemd user units could not be removed', '  || warn "the systemd user units could not be removed'),
    ("links-not-listed", ' "$d"/*.wants/sd-solo*.service "$d"/*.wants/sd-solo*.socket; do', '; do'),
    ("sockets-not-listed", ' "$d"/sd-solo*.socket "$d"/*.wants/sd-solo*.service "$d"/*.wants/sd-solo*.socket; do', ' "$d"/*.wants/sd-solo*.service; do'),
    ("removes-more-than-solo", 'for f in "$d"/sd-solo*.service', 'for f in "$d"/sd*.service'),
    ("fallback-no-reload", '      remove_unit_files "$unitdir"\n      systemctl --user daemon-reload 2>/dev/null || true\n    fi', '      remove_unit_files "$unitdir"\n    fi'),
    ("branch-without-script-stops-last", '    systemctl --user stop sd-solo-lnxd.service >/dev/null 2>&1 || true\n    systemctl --user disable --now sd-solo-ssh.socket sd-solo-ai.socket sd-solo-api.socket sd-solo.service >/dev/null 2>&1 || true\n',
     '    systemctl --user disable --now sd-solo-ssh.socket sd-solo-ai.socket sd-solo-api.socket sd-solo.service >/dev/null 2>&1 || true\n    systemctl --user stop sd-solo-lnxd.service >/dev/null 2>&1 || true\n'),
    ("env-not-filled", '  if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "$run" ]; then export XDG_RUNTIME_DIR="$run"; fi', '  :'),
    ("env-overwrites-xdg", '  if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "$run" ]; then', '  if [ -d "$run" ]; then'),
    ("env-overwrites-dbus", '  if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ]', '  if [ -n "${XDG_RUNTIME_DIR:-}" ]'),
    ("env-invents-dbus", ' && [ -S "$XDG_RUNTIME_DIR/bus" ]; then export DBUS', '; then export DBUS'),
    ("daemon-stopped-before-the-units", 'remove_units_step "$H" "$UNITDIR" \\\n  || fail', 'for n in sd-solo sd; do "$H/bin/$n" -stop >/dev/null 2>&1 || true; done\nremove_units_step "$H" "$UNITDIR" \\\n  || fail'),
    ("env-call-removed", '# ---- 1. the service and the daemon\nuser_manager_env "/run/user/$(id -u)"\n', '# ---- 1. the service and the daemon\n'),
]


def selftest(start=0):
    t = tempfile.mkdtemp()
    caught = missed = 0
    print("selftest: the real file first (must pass), then mutants from number %d (each must not)" % start)
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real file does not pass:\n" + r.stdout[-1200:])
        return 1
    print("  [ok] the real file passes")
    real = open(REAL, encoding="latin-1").read()
    for name, old, new in MUTANTS[start:]:
        if old not in real:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            continue
        f = os.path.join(t, name + ".sh")
        open(f, "w", encoding="latin-1").write(real.replace(old, new, 1))
        env = dict(os.environ, LDU_DELETESDSOLO=f)
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
