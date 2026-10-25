#!/usr/bin/env python3
#
# sandbox-lnxd-solo.py - the daemon's restart carried to Solo (25 Oct 2026, from SD Core's sandbox-auditwriter.py W12 and W13): "sd-solo -start -nodaemon" (what
# sd-solo.service runs) leaves the clean-up daemon out and a plain "sd-solo -start" still forks it; the daemon run on its own, as sd-solo-lnxd.service runs it, ends on
# SIGTERM with status 0 (so that Restart=on-failure does NOT bring it back after a stop); and there is one daemon at a time - a second one ends with status 0, and one that
# starts after its predecessor was killed takes over.  No install, no sudo, no systemd.
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-lnxd-solo.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py.  With --build it is built first from THIS tree (it must be empty or absent).  Exit 0 every row passed, 1 a row failed, 2 it
# could not run (including: the sandbox's segment did not come up, the null case).
#
# START-HISTORY:
# 25 Oct 26 dm  New.  sysseg.c start_sd(with_daemon) / start_lnxd(), sd.c -start -nodaemon, sdlnxd.c another_daemon_runs().
# END-HISTORY
#
# THE EVIDENCE.  The sandbox's own processes: every process whose executable is <dir>/sys/bin/sdlnxd (read from /proc), the sandbox's segment in /proc/sysvipc/shm, the
# text "sd-solo -start" printed, the exit statuses, and the error log <dir>/sys/errlog.  The harness (sandbox-fromtree.py) kills the sandbox's daemon after every start of its
# own, so this suite stops the sandbox through the harness first, starts SD ITSELF with the binary under test, and hands the sandbox back to the harness (start) at the end.
# NOT SAID HERE: that systemd restarts the daemon, and that sd-solo.service's stop leaves nothing running - the unit text is test-lnxdunit-solo-units.py's, the behaviour
# under a real user manager is the VM witness's.

import os
import re
import signal
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
passed = failed = 0


def say(s=""):
    print(s)
    sys.stdout.flush()


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        say("  [PASS] " + name)
    else:
        failed += 1
        say("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def bail(msg):
    say("sandbox-lnxd-solo: CANNOT RUN - " + msg)
    sys.exit(2)


def tool(box, *args, timeout=600):
    p = subprocess.run([sys.executable, TOOL, box] + list(args), capture_output=True, text=True, errors="replace", timeout=timeout)
    return ANSI.sub("", p.stdout + p.stderr)


def held_keys(keys):
    with open("/proc/sysvipc/shm") as fh:
        shm = {int(l.split()[0]) for l in fh.read().splitlines()[1:] if l.split()}
    with open("/proc/sysvipc/sem") as fh:
        sem = {int(l.split()[0]) for l in fh.read().splitlines()[1:] if l.split()}
    return (keys[0] in shm, keys[1] in sem)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-lnxd-solo.py <dir> [--build]")
    box = os.path.abspath(args[0])
    keyset = int(os.environ.get("SDSOLOBOX_KEYSET", "0"))
    keys = (0x53434CA1 + 0x20 * keyset, 0x53434CA2 + 0x20 * keyset)
    say("sandbox-lnxd-solo: sandbox %s, keyset %d, keys 0x%X / 0x%X" % (box, keyset, keys[0], keys[1]))
    if "--build" in sys.argv:
        if os.path.exists(box) and os.listdir(box):
            bail("%s is not empty" % box)
        out = tool(box, "all", timeout=1800)
        if "[FAIL]" in out or "[PASS] THIRD.COMPILE" not in out:
            bail("the sandbox build did not pass:\n" + out[-800:])
        say("sandbox-lnxd-solo: built, bootstrap passed")
        box = os.path.realpath(box)
    sysd = os.path.join(box, "sys")
    sd = os.path.join(sysd, "bin", "sd-solo")
    daemon = os.path.join(sysd, "bin", "sdlnxd")
    if not (os.path.isfile(sd) and os.path.isfile(daemon)):
        bail("%s holds no built sandbox (use --build, or point it at one)" % box)
    daemon_real = os.path.realpath(daemon)
    env = dict(os.environ, SD_CONFIG=os.path.join(box, "sd.conf"))
    env.pop("SDTEST_ADMIN", None)

    # THIS SUITE RUNS "sd-solo -start" AND "-stop" ITSELF, so before it runs either it READS the binaries for the key they will use: the sandbox's pair must be in them and the
    # Solo that runs on this computer (0x53434C11 / 0x53434C12) must not (a binary that still carried the live key would stop the live Solo).  The harness does the same
    # before its own start; this suite does not go through the harness for the starts.
    live_keys = (0x53434C11, 0x53434C12)
    for path in (sd, daemon):
        data = open(path, "rb").read()
        if struct.pack("<I", keys[0]) not in data or struct.pack("<I", keys[1]) not in data:
            bail("%s does not carry this sandbox's keys 0x%X / 0x%X" % (path, keys[0], keys[1]))
        if struct.pack("<I", live_keys[0]) in data or struct.pack("<I", live_keys[1]) in data:
            bail("%s carries the live Solo's key: it would stop or attach to the Solo that runs on this computer" % path)
    live_before = held_keys(live_keys)
    say("  the binaries carry the sandbox's keys and not the live Solo's; the live Solo's segment and semaphores are held now: %r" % (live_before,))

    def lnxd_pids():
        out = []
        for p in os.listdir("/proc"):
            if p.isdigit():
                try:
                    if os.readlink("/proc/%s/exe" % p) == daemon_real:
                        out.append(int(p))
                except OSError:
                    pass
        return sorted(out)

    def wait_pids(want_some, seconds=10):
        end = time.time() + seconds
        while True:
            ps = lnxd_pids()
            if bool(ps) == want_some or time.time() > end:
                return ps
            time.sleep(0.25)

    def sd_run(args_, name):
        """sd-solo <args> into a FILE: the daemon a plain start forks keeps the standard output it was given, and a pipe would be held open by it until the timeout"""
        outf = os.path.join(box, "lnxd-%s-%d.out" % (name, time.time_ns()))
        say("    > sd-solo " + " ".join(args_))
        with open(outf, "w") as fh:
            rc = subprocess.run([sd] + args_, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=sysd, timeout=90).returncode
        with open(outf, errors="replace") as fh:
            return rc, fh.read()

    def kill_all(sig=signal.SIGTERM):
        for p in lnxd_pids():
            try:
                os.kill(p, sig)
            except OSError:
                pass

    def start_daemon():
        return subprocess.Popen([daemon], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=sysd, env=env)

    def stop_all():
        kill_all()
        sd_run(["-stop"], "stop")
        kill_all(signal.SIGKILL)
        time.sleep(0.5)

    live = []
    try:
        say("\n--- L0. the null case: SD stopped, nothing of this sandbox running -----------------------------------------")
        tool(box, "stop", timeout=300)
        kill_all(signal.SIGKILL)
        time.sleep(0.5)
        row("L0 with SD stopped the sandbox's keys are not held and no sdlnxd of this sandbox is running", held_keys(keys) == (False, False) and lnxd_pids() == [],
            "keys %r, daemons %r" % (held_keys(keys), lnxd_pids()))
        if held_keys(keys) != (False, False):
            bail("the sandbox's keys are still held after the harness's stop; refusing to go on")

        say("\n--- L1-L3. 'sd-solo -start -nodaemon' (what sd-solo.service runs) leaves the daemon out ---------------------")
        rc, out = sd_run(["-start", "-nodaemon"], "nodaemon")
        time.sleep(2)
        p_nd = lnxd_pids()
        row("L1 'sd-solo -start -nodaemon' starts SD (exit 0, says it did, says the daemon was left out) and NO sdlnxd of this sandbox is running afterwards",
            rc == 0 and "without the daemon sdlnxd" in out and p_nd == [], "exit %d, stdout %r, daemons %r" % (rc, out.strip(), p_nd))
        row("L2 and SD IS started: the sandbox's shared segment and semaphores are there", held_keys(keys) == (True, True), "keys %r" % (held_keys(keys),))
        if held_keys(keys) != (True, True):
            bail("SD did not start with -start -nodaemon")
        d1 = start_daemon()
        live.append(d1)
        time.sleep(3)
        row("L3 the daemon run on its own, as the unit runs it, stays up and is the only one of this sandbox", d1.poll() is None and lnxd_pids() == [d1.pid],
            "status %r, daemons %r, pid %d" % (d1.poll(), lnxd_pids(), d1.pid))
        d1.send_signal(signal.SIGTERM)
        try:
            rc_t = d1.wait(timeout=15)
        except subprocess.TimeoutExpired:
            rc_t = None
            d1.kill()
            d1.wait()
        row("L4 and it ends on SIGTERM with status 0 (a clean end: Restart=on-failure does not start it again after 'sd-solo -stop')", rc_t == 0, "status %r" % rc_t)
        live.remove(d1)

        say("\n--- L5. (control) a plain 'sd-solo -start' still forks the daemon ----------------------------------------")
        stop_all()
        rc, out = sd_run(["-start"], "plain")
        p_plain = wait_pids(True)
        row("L5 a plain 'sd-solo -start' (exit 0, the ordinary success line) forks the daemon: one sdlnxd of this sandbox is running",
            rc == 0 and "has been started" in out and "without the daemon" not in out and len(p_plain) == 1, "exit %d, daemons %r, stdout %r" % (rc, p_plain, out.strip()))

        say("\n--- L6-L9. there is one daemon at a time ---------------------------------------------------------------------")
        first = lnxd_pids()
        second = start_daemon()
        live.append(second)
        try:
            rc2 = second.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc2 = None
            second.kill()
            second.wait()
        live.remove(second)
        still = lnxd_pids()
        row("L6 a second sdlnxd started by hand ENDS at once with status 0 (so the service does not count it a failure and start it again)", rc2 == 0, "second daemon's status %r" % rc2)
        row("L7 the first daemon is still the only one running, with the same pid", first != [] and still == first, "before %r, after %r" % (first, still))
        try:
            with open(os.path.join(sysd, "errlog"), errors="replace") as fh:
                el = fh.read()
        except OSError:
            el = ""
        row("L8 the error log says which daemon the second one found", bool(first) and re.search(r"sdlnxd: pid %d is already the daemon" % first[0], el) is not None, "errlog tail %r" % el[-200:])
        for p in first:
            os.kill(p, signal.SIGKILL)
        gone = wait_pids(False)
        d3 = start_daemon()
        live.append(d3)
        time.sleep(4)
        row("L9 after the first daemon was killed (kill -9: the segment still names its pid) a new one is NOT turned away: it stays up and is the only one",
            gone == [] and d3.poll() is None and lnxd_pids() == [d3.pid], "gone %r, status %r, daemons %r, pid %d" % (gone, d3.poll(), lnxd_pids(), d3.pid))
        d4 = start_daemon()
        live.append(d4)
        try:
            rc4 = d4.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc4 = None
            d4.kill()
            d4.wait()
        live.remove(d4)
        row("L10 and it IS the daemon now: it wrote its own pid, so another one that starts after it ends with status 0", rc4 == 0 and d3.poll() is None and lnxd_pids() == [d3.pid],
            "status %r, first-of-two %r, daemons %r" % (rc4, d3.poll(), lnxd_pids()))
    finally:
        for d in live:
            if d.poll() is None:
                d.kill()
                d.wait()
        stop_all()
        held = held_keys(keys)
        if held != (False, False):
            say("  note: the sandbox's keys are still held after sd-solo -stop %r; removing exactly the sandbox's own two" % (held,))
            if held[0]:
                subprocess.run(["ipcrm", "-M", "0x%08x" % keys[0]], capture_output=True)
            if held[1]:
                subprocess.run(["ipcrm", "-S", "0x%08x" % keys[1]], capture_output=True)
        out = tool(box, "start", timeout=300)
        say("  the sandbox was handed back to the harness (start): " + ("keys held" if held_keys(keys) == (True, True) else "KEYS NOT HELD - " + out[-200:]))

    say("\n--- L11. the Solo that runs on this computer was not touched -------------------------------------------------")
    row("L11 CONTROL: its segment and semaphores are held exactly as before this suite ran (%r)" % (live_before,), held_keys(live_keys) == live_before,
        "before %r, after %r" % (live_before, held_keys(live_keys)))

    say("")
    say("sandbox-lnxd-solo: %d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
