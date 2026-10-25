#!/usr/bin/env python3
# test-lnxdunit-solo-units.py - the restart of a dead clean-up daemon, carried to Solo (25 Oct 2026, from SD Core's sd-lnxd.service, option A): sdlnxd is run by the
# user unit sd-solo-lnxd.service, which systemd starts again when it fails; "sd-solo -start -nodaemon" (what sd-solo.service runs) leaves the fork of the daemon to that
# unit.  FREE CHECK: no install, no sudo, no systemd.  It READS the C source and the installer and deleter as text (comments removed), and it RUNS solo-service.sh -
# "daemon --print", "daemon", "remove" and "install" - in a scratch directory with a stub systemctl and loginctl first on PATH, HOME and XDG_CONFIG_HOME in the scratch:
# the user's own systemd manager and the units of the Solo that runs on this computer are never touched (memory: user-unit-names-are-per-user).
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-lnxdunit-solo-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-lnxdunit-solo-units.py --selftest [--from=N]      (mutants)
#
#   U  the two units "solo-service.sh daemon TREE --print" shows: sd-solo-lnxd.service is Type=simple, the daemon with no arguments, Restart=on-failure (NEVER always:
#      "sd-solo -stop" ends the daemon with SIGTERM and it exits 0), a pause, a start limit, UMask=0077, After= and BindsTo= sd-solo.service, no [Install] section;
#      sd-solo.service runs "-start -nodaemon", is still oneshot, wants the daemon unit, stops with "-stop"; --print writes nothing
#   R  the script run against the stub: "daemon" writes both files and reloads systemd and starts, stops and enables NOTHING; it refuses a pair that names another
#      tree and replaces one of this tree (the new and the pre-rename ExecStart); "remove" stops the daemon unit before the service and removes both files;
#      "install" writes both, enables the service, never starts the daemon unit itself, and FAILS when that unit is not active
#   C  sysseg.c / sd.h: start_sd(bool with_daemon) forks the daemon (start_lnxd) only when asked, runs the STARTUP command either way, and a child whose exec fails ends
#   D  sd.c: "-nodaemon" is read only after -start and only as that word; -restart still forks the daemon
#   G  sdlnxd.c: one daemon at a time: it ends with status 0 (not a failure, so the service does not start it again) when the segment names a live process running the
#      same executable, and asks that BEFORE it writes its own pid into the segment
#   I  installsdsolo.sh: an upgrade stops the daemon unit first and, before it starts the service again, runs "solo-service.sh daemon" - and warns, never fails, when it
#      cannot (the tree is already upgraded)
#   X  deletesdsolo.sh (the branch for a tree with no solo-service.sh) stops the daemon unit first and removes its file
# NOT SAID HERE: that systemd restarts the daemon, that stop leaves nothing running, that a real user manager accepts the units - the VM witness; that "-start -nodaemon"
# leaves the daemon out and a second daemon ends - sandbox-lnxd-solo.py.
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.normpath(os.path.join(HERE, ".."))
TREE = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
REAL = {
    "solo-service.sh": os.path.join(HERE, "solo-service.sh"),
    "sysseg.c": os.path.join(SD64, "gplsrc", "sysseg.c"),
    "sd.c": os.path.join(SD64, "gplsrc", "sd.c"),
    "sd.h": os.path.join(SD64, "gplsrc", "sd.h"),
    "sdlnxd.c": os.path.join(SD64, "gplsrc", "sdlnxd.c"),
    "installsdsolo.sh": os.path.join(TREE, "installsdsolo.sh"),
    "deletesdsolo.sh": os.path.join(TREE, "deletesdsolo.sh"),
}
FILES = {k: os.environ.get("LUS_" + re.sub(r"\W", "_", k).upper(), v) for k, v in REAL.items()}
passed = failed = 0


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  [PASS] " + name)
    else:
        failed += 1
        print("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def raw(name):
    return open(FILES[name], encoding="latin-1").read()


def code(name):
    s = raw(name)
    if name.endswith((".c", ".h")):
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        return re.sub(r"//[^\n]*", "", s)
    return "\n".join(l for l in s.split("\n") if not l.lstrip().startswith("#"))      # shell: whole-line comments


def func(src, head):
    m = re.search(re.escape(head) + r"[^;{]*\{.*?\n\}", src, re.S)
    return m.group(0) if m else ""


def keys(unit_text, section):
    """the Key=Value lines of one section of a unit"""
    out, cur = [], None
    for l in unit_text.split("\n"):
        m = re.match(r"^\[(\w+)\]\s*$", l.strip())
        if m:
            cur = m.group(1)
        elif cur == section and "=" in l:
            out.append(l.strip())
    return out


# ---------------------------------------------------------------------------------------------------------------- the scratch the script runs in
SHIM = """#!/bin/bash
echo "$*" >> "$STUB_LOG"
case "$*" in
  *is-system-running*) echo running; exit 0 ;;
  *is-active*sd-solo-lnxd.service*) echo "${STUB_LNXD_STATE:-active}"; [ "${STUB_LNXD_STATE:-active}" = active ]; exit $? ;;
  *is-active*) echo active; exit 0 ;;
  *is-enabled*) echo enabled; exit 0 ;;
esac
exit 0
"""
LOGINCTL = "#!/bin/bash\necho yes\n"
SD_SOLO = "#!/bin/bash\necho \"$*\" >> \"$STUB_SD_LOG\"\nexit 0\n"


class Scratch:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="lus")
        self.bindir = os.path.join(self.root, "shim")
        self.cfg = os.path.join(self.root, "cfg")
        self.home = os.path.join(self.root, "home")
        self.tree = os.path.join(self.root, "tree")
        self.log = os.path.join(self.root, "systemctl.log")
        self.sdlog = os.path.join(self.root, "sd-solo.log")
        for d in (self.bindir, self.home, os.path.join(self.tree, "bin"), os.path.join(self.tree, "tools")):
            os.makedirs(d)
        for name, text in (("systemctl", SHIM), ("loginctl", LOGINCTL)):
            p = os.path.join(self.bindir, name)
            open(p, "w").write(text)
            os.chmod(p, 0o755)
        p = os.path.join(self.tree, "bin", "sd-solo")
        open(p, "w").write(SD_SOLO)
        os.chmod(p, 0o755)
        open(os.path.join(self.tree, ".sdcoresolo"), "w").write("")
        open(os.path.join(self.tree, "tools", "sd-ai"), "w").write("#!/bin/sh\n")
        open(self.log, "w").close()
        self.units = os.path.join(self.cfg, "systemd", "user")

    def run(self, args, state=None):
        env = dict(os.environ, PATH=self.bindir + os.pathsep + os.environ.get("PATH", ""), HOME=self.home, XDG_CONFIG_HOME=self.cfg,
                   STUB_LOG=self.log, STUB_SD_LOG=self.sdlog)
        env.pop("SDSOLO_TEST_API_PORT", None)
        env.pop("SDSOLO_TEST_SSH_PORT", None)
        if state:
            env["STUB_LNXD_STATE"] = state
        p = subprocess.run(["bash", FILES["solo-service.sh"]] + args, capture_output=True, text=True, errors="replace", env=env, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def calls(self):
        return [l.strip() for l in open(self.log).read().split("\n") if l.strip()]

    def unit(self, name):
        p = os.path.join(self.units, name)
        return open(p).read() if os.path.exists(p) else None

    def clear(self):
        open(self.log, "w").close()

    def drop(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)


def split_print(text):
    """{unit name: its text} from the '# name' headed parts of a --print"""
    parts, cur = {}, None
    for l in text.split("\n"):
        if l.startswith("# sd-solo"):
            cur = l[2:].strip()
            parts[cur] = []
        elif cur is not None:
            parts[cur].append(l)
    return {k: "\n".join(v).strip() + "\n" for k, v in parts.items()}


def mutating(calls):
    """the calls that start, stop, enable or restart something (reload and the questions are not)"""
    return [c for c in calls if re.search(r"\b(start|stop|enable|disable|restart|reset-failed)\b", c)]


def run():
    sc = Scratch()
    try:
        # ------------------------------------------------------------------------------------------------------------------------ U
        rc, out = sc.run(["daemon", sc.tree, "--print"])
        parts = split_print(out)
        s, u = parts.get("sd-solo.service", ""), parts.get("sd-solo-lnxd.service", "")
        row("U0 'daemon TREE --print' shows both units, exits 0, and WRITES NOTHING (no unit directory, no call to the stub)",
            rc == 0 and bool(s) and bool(u) and not os.path.exists(sc.cfg) and sc.calls() == [], "exit %d, parts %r, cfg exists %s, calls %r" % (rc, sorted(parts), os.path.exists(sc.cfg), sc.calls()))
        d = sc.tree
        row("U1 sd-solo-lnxd.service runs the daemon in the foreground: Type=simple, ExecStart=<tree>/bin/sdlnxd with no arguments, nothing else for ExecStart",
            keys(u, "Service").count("Type=simple") == 1 and [k for k in keys(u, "Service") if k.startswith("ExecStart")] == ["ExecStart=%s/bin/sdlnxd" % d], str(keys(u, "Service")))
        row("U2 it is restarted on failure and NOT always: Restart=on-failure once, no Restart=always",
            keys(u, "Service").count("Restart=on-failure") == 1 and not any(k.startswith("Restart=") and k != "Restart=on-failure" for k in keys(u, "Service")), str(keys(u, "Service")))
        row("U3 with a pause before the restart (RestartSec=2) and a limit on a start that keeps failing (5 in 60 s)",
            "RestartSec=2" in keys(u, "Service") and "StartLimitIntervalSec=60" in keys(u, "Unit") and "StartLimitBurst=5" in keys(u, "Unit"), str(keys(u, "Unit")))
        row("U4 it makes its files under UMask=0077, like every Solo unit", "UMask=0077" in keys(u, "Service"), str(keys(u, "Service")))
        row("U5 it starts after sd-solo.service (the segment must exist) and stops with it", "After=sd-solo.service" in keys(u, "Unit") and "BindsTo=sd-solo.service" in keys(u, "Unit"), str(keys(u, "Unit")))
        row("U6 it has no [Install] section (sd-solo.service wants it)", "[Install]" not in u, "")
        row("U7 sd-solo.service runs '<tree>/bin/sd-solo -start -nodaemon' (and only that for ExecStart), is still oneshot with RemainAfterExit, stops with '-stop', and is wanted by default.target",
            [k for k in keys(s, "Service") if k.startswith("ExecStart=")] == ["ExecStart=%s/bin/sd-solo -start -nodaemon" % d] and "Type=oneshot" in keys(s, "Service")
            and "RemainAfterExit=yes" in keys(s, "Service") and "ExecStop=%s/bin/sd-solo -stop" % d in keys(s, "Service") and "WantedBy=default.target" in keys(s, "Install"), str(keys(s, "Service")))
        row("U8 sd-solo.service wants sd-solo-lnxd.service and keeps UMask=0077", "Wants=sd-solo-lnxd.service" in keys(s, "Unit") and "UMask=0077" in keys(s, "Service"), str(keys(s, "Unit")))

        # ------------------------------------------------------------------------------------------------------------------------ R
        sc.clear()
        rc, out = sc.run(["daemon", sc.tree])
        calls = sc.calls()
        row("R0 (null case) the stub systemctl is what the script called: its log holds the script's own questions",
            any("is-system-running" in c for c in calls), "calls %r" % calls)
        row("R1 'daemon TREE' exits 0, says so, writes sd-solo.service and sd-solo-lnxd.service exactly as --print shows them",
            rc == 0 and "SOLO DAEMON UNITS WRITTEN" in out and sc.unit("sd-solo.service") == s and sc.unit("sd-solo-lnxd.service") == u,
            "exit %d, out %r" % (rc, out[-200:]))
        row("R2 and reloads systemd but starts, stops, enables and restarts NOTHING", any("daemon-reload" in c for c in calls) and mutating(calls) == [], "calls %r" % calls)

        sc2 = Scratch()
        try:
            os.makedirs(sc2.units)
            other = "[Service]\nType=oneshot\nExecStart=/home/somebody/else/bin/sd-solo -start\nExecStop=/home/somebody/else/bin/sd-solo -stop\n"
            open(os.path.join(sc2.units, "sd-solo.service"), "w").write(other)
            rc2, out2 = sc2.run(["daemon", sc2.tree])
            row("R3 a daemon unit that names ANOTHER tree is refused (exit 2, REFUSED, the other tree named), left as it was, no lnxd unit made, systemd not reloaded",
                rc2 == 2 and "REFUSED" in out2 and "/home/somebody/else" in out2 and sc2.unit("sd-solo.service") == other and sc2.unit("sd-solo-lnxd.service") is None
                and not any("daemon-reload" in c for c in sc2.calls()), "exit %d, out %r" % (rc2, out2[-240:]))
        finally:
            sc2.drop()
        for tag, old in (("the previous release's", "[Service]\nType=oneshot\nExecStart=%s/bin/sd-solo -start\nExecStop=%s/bin/sd-solo -stop\n"),
                         ("the pre-rename", "[Service]\nType=oneshot\nExecStart=%s/bin/sd -start\nExecStop=%s/bin/sd -stop\n")):
            sc3 = Scratch()
            try:
                os.makedirs(sc3.units)
                open(os.path.join(sc3.units, "sd-solo.service"), "w").write(old % (sc3.tree, sc3.tree))
                rc3, out3 = sc3.run(["daemon", sc3.tree])
                t3 = split_print(sc3.run(["daemon", sc3.tree, "--print"])[1])
                row("R4 %s unit of THIS tree is replaced by this release's two units" % tag,
                    rc3 == 0 and sc3.unit("sd-solo.service") == t3.get("sd-solo.service") and sc3.unit("sd-solo-lnxd.service") == t3.get("sd-solo-lnxd.service")
                    and "-nodaemon" in (sc3.unit("sd-solo.service") or ""), "exit %d, out %r" % (rc3, out3[-200:]))
            finally:
                sc3.drop()

        sc.clear()
        rc, out = sc.run(["remove"])
        calls = sc.calls()
        i_l = next((i for i, c in enumerate(calls) if re.search(r"\bstop\b.*sd-solo-lnxd\.service", c)), -1)
        i_d = next((i for i, c in enumerate(calls) if re.search(r"disable --now sd-solo\.service", c)), -1)
        row("R5 'remove' stops the daemon unit BEFORE it disables the service, and exits 0 with SOLO SERVICE REMOVED", rc == 0 and "SOLO SERVICE REMOVED" in out and 0 <= i_l < i_d,
            "exit %d, stop at %d, disable at %d, calls %r" % (rc, i_l, i_d, calls))
        row("R6 and both daemon files are gone", sc.unit("sd-solo.service") is None and sc.unit("sd-solo-lnxd.service") is None, str(os.listdir(sc.units) if os.path.isdir(sc.units) else "no dir"))

        sc4 = Scratch()
        try:
            rc4, out4 = sc4.run(["install", sc4.tree, "--api", "off", "--ssh", "off"])
            calls4 = sc4.calls()
            row("R7 'install' ends with the READY line, writes both units (the same as --print) and enables the service now",
                rc4 == 0 and re.search(r"^SOLO SERVICE READY daemon=active ", out4, re.M) is not None and sc4.unit("sd-solo.service") == split_print(sc4.run(["daemon", sc4.tree, "--print"])[1]).get("sd-solo.service")
                and sc4.unit("sd-solo-lnxd.service") is not None and any(re.search(r"enable --now sd-solo\.service", c) for c in calls4), "exit %d, out %r" % (rc4, out4[-300:]))
            row("R8 it asks whether the daemon unit is active and NEVER starts it itself (sd-solo.service wants it)",
                any(re.search(r"is-active sd-solo-lnxd\.service", c) for c in calls4) and not any(re.search(r"\b(start|restart|enable)\b.*sd-solo-lnxd", c) for c in calls4), "calls %r" % calls4)
            sd_calls = [l.strip() for l in open(sc4.sdlog).read().split("\n") if l.strip()] if os.path.exists(sc4.sdlog) else []
            row("R9 (control) it still stops a daemon the tree's own binary left running, before the units: the tree's sd-solo was run with -stop", sd_calls == ["-stop"], "sd-solo calls %r" % sd_calls)
        finally:
            sc4.drop()
        sc5 = Scratch()
        try:
            rc5, out5 = sc5.run(["install", sc5.tree, "--api", "off", "--ssh", "off"], state="inactive")
            row("R10 'install' FAILS (exit 1, names the unit and its state, no READY line) when the daemon unit is not active",
                rc5 == 1 and "sd-solo-lnxd.service is 'inactive'" in out5 and "SOLO SERVICE READY" not in out5, "exit %d, out %r" % (rc5, out5[-240:]))
        finally:
            sc5.drop()

        # ------------------------------------------------------------------------------------------------------------------------ C D G
        y = code("sysseg.c")
        sl = func(y, "Private bool start_lnxd(void)")
        ss = func(y, "bool start_sd(bool with_daemon)")
        row("C1 start_lnxd() is the old fork: fork, daemon(1, 1), the sdlnxd path, execl; a failed fork is reported and a child whose exec fails ENDS (_exit(1))",
            bool(sl) and "fork()" in sl and "daemon(1, 1);" in sl and "/bin/sdlnxd" in sl and "execl(path, path, NULL);\n    _exit(1);" in sl and "return FALSE;" in sl
            and "Cannot start sdlnxd - fork() failed" in sl, "")
        i_pid, i_if, i_start = ss.find("sysseg->sdlnxd_pid = -1;"), ss.find("if (with_daemon && !start_lnxd())"), ss.find("if (sysseg->startup[0] != '\\0')")
        row("C2 start_sd(with_daemon) forks the daemon only when asked (after the pid is set to -1), and the STARTUP command is run either way (outside that test)",
            0 <= i_pid < i_if < i_start and "return FALSE;" in ss[i_if:i_start], "positions %d %d %d" % (i_pid, i_if, i_start))
        row("C3 sd.h declares start_sd(bool with_daemon)", "bool start_sd(bool with_daemon);" in code("sd.h"), "")
        row("C4 start_sd() still applies a waiting restore before it binds the segment", 0 <= ss.find("apply_pending_restore();") < ss.find("bind_sysseg(TRUE, errmsg)"), "")

        dd = code("sd.c")
        row("D1 '-nodaemon' is read after -start only, as that exact word (stricmp, the next argument), and start_sd() is given the answer",
            "bool with_daemon = !((arg + 1 < argc) && !stricmp(argv[arg + 1], \"-NODAEMON\"));" in dd and "start_sd(with_daemon)" in dd and dd.count("-NODAEMON") == 1, "")
        row("D2 -restart still starts the daemon itself (start_sd(TRUE))", "stop_sd() && start_sd(TRUE)" in dd, "")

        z = code("sdlnxd.c")
        ag = func(z, "static bool another_daemon_runs(void)")
        mn = func(z, "int main()")
        row("G1 another_daemon_runs() looks at the pid in the segment, ignores 0, -1 and its own, needs the process to exist (kill 0) and to run THIS executable (/proc/<pid>/exe against /proc/self/exe)",
            bool(ag) and "sysseg->sdlnxd_pid" in ag and "(pid <= 0) || (pid == getpid())" in ag and "kill(pid, 0)" in ag and "/proc/%d/exe" in ag and "/proc/self/exe" in ag
            and "memcmp(other, mine, (size_t)n_mine) == 0" in ag, "")
        i_g, i_set = mn.find("if (another_daemon_runs()) {"), mn.find("sysseg->sdlnxd_pid = getpid();")
        gb = mn[i_g:i_set] if 0 <= i_g < i_set else ""
        row("G2 main() asks it BEFORE it writes its own pid into the segment, and a second daemon returns 0 (a clean end, which the service does not restart)",
            0 <= i_g < i_set and "return 0;" in gb and "exit(" not in gb, "positions %d %d" % (i_g, i_set))
        row("G3 and it asks AFTER it has the segment and the semaphores (the log note needs the semaphore) and after its own directory is known",
            0 <= mn.find("own_sysdir()") < mn.find("shmat(") < mn.find("get_semaphores(FALSE, errmsg)") < mn.find("another_daemon_runs()"), "")

        # ------------------------------------------------------------------------------------------------------------------------ I X
        inst = code("installsdsolo.sh")
        i_stop_l = inst.find("systemctl --user stop sd-solo-lnxd.service")
        i_stage = inst.find('solo-stage.sh" --upgrade')
        row("I1 an upgrade stops the daemon unit before it touches the tree (before solo-stage.sh --upgrade)", 0 <= i_stop_l < i_stage, "positions %d %d" % (i_stop_l, i_stage))
        i_say = inst.find('say "Starting the systemd user service again."')
        i_call = inst.find('solo-service.sh" daemon "$HOME_DIR"')
        i_go = inst.find("systemctl --user start sd-solo.service || fail")
        row("I2 it writes this release's daemon units after the tree is upgraded and BEFORE it starts the service again", 0 <= i_say < i_call < i_go, "positions %d %d %d" % (i_say, i_call, i_go))
        blk = inst[i_call - 30:i_go] if 0 <= i_call < i_go else ""
        row("I3 and a failure of that call is a WARNING that names the retry command, never a fail (the tree is already upgraded)",
            'warn "the daemon\'s service units were NOT updated' in blk and "solo-service.sh daemon $HOME_DIR" in blk and "fail " not in blk, blk[:300])
        dl = code("deletesdsolo.sh")
        j1, j2 = dl.find("systemctl --user stop sd-solo-lnxd.service"), dl.find("systemctl --user disable --now sd-solo-ssh.socket")
        row("X1 deletesdsolo.sh (no solo-service.sh to ask) stops the daemon unit before it disables the service", 0 <= j1 < j2, "positions %d %d" % (j1, j2))
        row("X2 and removes the unit file with the others (every file whose name begins sd-solo; test-deleteunits-solo-units.py removes the daemon's among them)", '"$d"/sd-solo*.service' in dl, "")
    finally:
        sc.drop()
    print("test-lnxdunit-solo-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


MUTANTS = [   # name, file, old, new
    ("svc-restart-always", "solo-service.sh", "Restart=on-failure\nRestartSec=2", "Restart=always\nRestartSec=2"),
    ("svc-no-restart", "solo-service.sh", "Restart=on-failure\nRestartSec=2", "RestartSec=2"),
    ("svc-restart-on-abnormal-only", "solo-service.sh", "Restart=on-failure\nRestartSec=2", "Restart=on-abnormal\nRestartSec=2"),
    ("svc-umask-022", "solo-service.sh", "RestartSec=2\nUMask=0077", "RestartSec=2\nUMask=0022"),
    ("svc-no-bindsto", "solo-service.sh", "After=$DAEMON\nBindsTo=$DAEMON\n", "After=$DAEMON\n"),
    ("svc-before-service", "solo-service.sh", "After=$DAEMON\nBindsTo=$DAEMON\n", "Before=$DAEMON\nBindsTo=$DAEMON\n"),
    ("svc-daemon-with-argument", "solo-service.sh", "ExecStart=$1/bin/sdlnxd\n", "ExecStart=$1/bin/sdlnxd -x\n"),
    ("svc-forking", "solo-service.sh", "Type=simple", "Type=forking"),
    ("svc-no-start-limit", "solo-service.sh", "StartLimitBurst=5\n", ""),
    ("svc-no-restart-pause", "solo-service.sh", "RestartSec=2\n", ""),
    ("svc-installs-itself", "solo-service.sh", "RestartSec=2\nUMask=0077\nUNIT", "RestartSec=2\nUMask=0077\n\n[Install]\nWantedBy=default.target\nUNIT"),
    ("svc-service-forks-the-daemon", "solo-service.sh", "ExecStart=$1/bin/sd-solo -start -nodaemon", "ExecStart=$1/bin/sd-solo -start"),
    ("svc-service-does-not-want-it", "solo-service.sh", "Wants=$LNXD\n", ""),
    ("svc-service-no-stop", "solo-service.sh", "ExecStop=$1/bin/sd-solo -stop\n", ""),
    ("svc-daemon-no-lnxd-file", "solo-service.sh", '  lnxd_text "$1" > "$UNITDIR/$LNXD" || fail "writing $UNITDIR/$LNXD"\n', ""),
    ("svc-daemon-starts-the-service", "solo-service.sh", '  daemon_write "$tree"\n  systemctl --user daemon-reload || fail "daemon-reload"', '  daemon_write "$tree"\n  systemctl --user start "$DAEMON"\n  systemctl --user daemon-reload || fail "daemon-reload"'),
    ("svc-daemon-no-reload", "solo-service.sh", '  daemon_write "$tree"\n  systemctl --user daemon-reload || fail "daemon-reload"', '  daemon_write "$tree"'),
    ("svc-daemon-no-guard", "solo-service.sh", 'if [ -f "$UNITDIR/$DAEMON" ] && ! grep -qF -e "=$tree/bin/sd-solo "', 'if false && ! grep -qF -e "=$tree/bin/sd-solo "'),
    ("svc-guard-refuses-the-old-name", "solo-service.sh", ' -e "=$tree/bin/sd " "$UNITDIR/$DAEMON"; then', ' "$UNITDIR/$DAEMON"; then'),
    ("svc-print-writes", "solo-service.sh", '  echo "# $DAEMON"; daemon_text "$2"\n', '  daemon_write "$2"\n  echo "# $DAEMON"; daemon_text "$2"\n'),
    ("svc-remove-stops-it-last", "solo-service.sh", '  systemctl --user stop "$LNXD" >/dev/null 2>&1 || true\n  systemctl --user disable --now "$DAEMON" >/dev/null 2>&1 || true',
     '  systemctl --user disable --now "$DAEMON" >/dev/null 2>&1 || true\n  systemctl --user stop "$LNXD" >/dev/null 2>&1 || true'),
    ("svc-remove-keeps-the-unit-file", "solo-service.sh", '"$TEMPLATE" "$LNXD" "$DAEMON"; do rm', '"$TEMPLATE" "$DAEMON"; do rm'),
    ("svc-install-no-lnxd-check", "solo-service.sh", '[ "$l_state" = "active" ] || { systemctl --user status "$LNXD"', 'true || { systemctl --user status "$LNXD"'),
    ("svc-install-starts-the-daemon-unit", "solo-service.sh", 'systemctl --user enable --now "$DAEMON" 2>&1 | tail -2\nsleep 1', 'systemctl --user enable --now "$DAEMON" 2>&1 | tail -2\nsystemctl --user start "$LNXD"\nsleep 1'),
    ("sysseg-always-forks", "sysseg.c", "if (with_daemon && !start_lnxd())", "if (!start_lnxd())"),
    ("sysseg-never-forks", "sysseg.c", "if (with_daemon && !start_lnxd())", "if (FALSE && !start_lnxd())"),
    ("sysseg-child-returns-after-failed-exec", "sysseg.c", "execl(path, path, NULL);\n    _exit(1);", "execl(path, path, NULL);"),
    ("sysseg-startup-only-with-daemon", "sysseg.c", "  /* Run startup command, if defined */\n\n  if (sysseg->startup[0] != '\\0') {", "  /* Run startup command, if defined */\n\n  if (with_daemon && sysseg->startup[0] != '\\0') {"),
    ("sysseg-restore-after-bind", "sysseg.c", "  apply_pending_restore();\n\n  if (!bind_sysseg(TRUE, errmsg)) {\n    fprintf(stderr, \"%s\\n\", errmsg);\n    return FALSE;\n  }\n\n  /* 11 Sep 26",
     "  if (!bind_sysseg(TRUE, errmsg)) {\n    fprintf(stderr, \"%s\\n\", errmsg);\n    return FALSE;\n  }\n  apply_pending_restore();\n\n  /* 11 Sep 26"),
    ("sd-h-old-prototype", "sd.h", "bool start_sd(bool with_daemon);", "bool start_sd(void);"),
    ("sd-nodaemon-misspelt", "sd.c", '!stricmp(argv[arg + 1], "-NODAEMON")', '!stricmp(argv[arg + 1], "-NODAEMOX")'),
    ("sd-restart-without-daemon", "sd.c", "stop_sd() && start_sd(TRUE)", "stop_sd() && start_sd(FALSE)"),
    ("sd-start-ignores-the-option", "sd.c", "if (start_sd(with_daemon)) {", "if (start_sd(TRUE)) {"),
    ("guard-off", "sdlnxd.c", "if (another_daemon_runs()) {", "if (FALSE) {"),
    ("guard-no-executable-check", "sdlnxd.c", "return memcmp(other, mine, (size_t)n_mine) == 0;", "return TRUE;"),
    ("guard-no-liveness-check", "sdlnxd.c", "if ((kill(pid, 0) != 0) && (errno != EPERM))\n    return FALSE;\n", ""),
    ("guard-ends-as-a-failure", "sdlnxd.c", "    shmdt((void*)sysseg);\n    return 0;\n  }\n\n  /* Set process id", "    shmdt((void*)sysseg);\n    return 1;\n  }\n\n  /* Set process id"),
    ("guard-after-registering", "sdlnxd.c", "  if (another_daemon_runs()) {", "  sysseg->sdlnxd_pid = getpid();\n  if (another_daemon_runs()) {"),
    ("guard-before-semaphores", "sdlnxd.c", "  /* Get access to semaphores */", "  if (another_daemon_runs()) return 0;\n  /* Get access to semaphores */"),
    ("installer-no-daemon-call", "installsdsolo.sh", 'solo-service.sh" daemon "$HOME_DIR" 2>&1', 'solo-service.sh" ai "$HOME_DIR" 2>&1'),
    ("installer-fails-the-upgrade", "installsdsolo.sh", 'warn "the daemon\'s service units were NOT updated', 'fail "the daemon\'s service units were NOT updated'),
    ("installer-no-stop-of-the-unit", "installsdsolo.sh", "    systemctl --user stop sd-solo-lnxd.service >/dev/null 2>&1 || true\n", ""),
    ("installer-call-before-the-say", "installsdsolo.sh", '    say "Starting the systemd user service again."\n', ""),
    ("deleter-no-stop", "deletesdsolo.sh", "  systemctl --user stop sd-solo-lnxd.service >/dev/null 2>&1 || true\n", ""),
    ("deleter-keeps-the-unit-file", "deletesdsolo.sh", 'for f in "$d"/sd-solo*.service "$d"/sd-solo*.socket', 'for f in "$d"/sd-solo.service "$d"/sd-solo*.socket'),
]


def selftest(start=0):
    import shutil
    t = tempfile.mkdtemp()
    caught = missed = 0
    print("selftest: the real files first (must pass), then mutants from number %d (each must not)" % start)
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real files do not pass:\n" + r.stdout[-1200:])
        return 1
    print("  [ok] the real files pass")
    for name, which, old, new in MUTANTS[start:]:
        real = open(REAL[which], encoding="latin-1").read()
        if real.count(old) < 1:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            continue
        f = os.path.join(t, name + "-" + which)
        open(f, "w", encoding="latin-1").write(real.replace(old, new, 1))
        env = dict(os.environ)
        env["LUS_" + re.sub(r"\W", "_", which).upper()] = f
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
