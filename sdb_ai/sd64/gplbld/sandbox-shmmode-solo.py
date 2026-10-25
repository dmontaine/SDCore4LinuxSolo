#!/usr/bin/env python3
#
# sandbox-shmmode-solo.py - W.11 F1 carried to Solo (25 Oct 2026): a running Solo makes its shared memory segment and its semaphores owner-only (0600), and its
# daemon sdlnxd runs "sd-solo -cleanup" from the directory it was STARTED in, not from a path read out of the segment.  No install, no sudo.
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-shmmode-solo.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py.  With --build it is built first from THIS tree (it must be empty or absent).  Exit 0 every row passed,
# 1 a row failed, 2 it could not run (including: the sandbox's segment is not there, or the lost-process setup did not happen - the null cases).
#
# START-HISTORY:
# 25 Oct 26 dm  New.  Twin of the full product's sandbox-shmmode.py (0660 and the group sdusers there) plus the rows for the daemon, which that suite
#               could not run: the full product's sandbox kills its own sdlnxd after every start, and so does this one's harness.
# END-HISTORY
#
# THE EVIDENCE.  A: /proc/sysvipc/shm and /proc/sysvipc/sem, the mode and owner of the sandbox's own keys (0x53434CA1 / 0x53434CA2 plus 0x20 per keyset).
# B: the daemon binary of the sandbox, COPIED into scratch directories that are not the sandbox, and run there: in a directory that is not <something>/bin
# or has no executable sd-solo beside it, it must end with status 3 and say why; in a directory that has a stub sd-solo beside it, and with a session killed
# so that the table holds a lost process (CLEANUP=30 in the sandbox's sd.conf, the sandbox restarted), it must run THAT sd-solo with "-cleanup" - the stub
# writes a file.  The old daemon ran the sandbox's own <sysdir>/bin/sd-solo, taken from the segment, so the stub is never called by it.
# NOT SAID HERE: that a user who is not the owner cannot attach (this suite has one user and no sudo; the mode and owner are what the kernel decides that
# on).  A different user planting a sysdir in the segment is therefore not run: with the segment closed there is no such user, and the daemon rows show it
# would not matter if there were.

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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
    say("sandbox-shmmode-solo: CANNOT RUN - " + msg)
    sys.exit(2)


def tool(box, *args, timeout=600):
    p = subprocess.run([sys.executable, TOOL, box] + list(args), capture_output=True, text=True, errors="replace", timeout=timeout)
    return ANSI.sub("", p.stdout + p.stderr)


def sess(box, *cmds):
    say("    > " + " | ".join(cmds))
    out = tool(box, "sess", os.path.join(box, "user_accounts"), *cmds)
    return out.split(":TERM 200,9999", 1)[-1]


def users_listed(out):
    """{user number: pid} from the LISTU report in a session's output."""
    return {int(m.group(1)): int(m.group(2)) for m in re.finditer(r"^\*?\s*(\d+)\s+(\d+)\s", out, re.M)}


def ipc(kind, key):
    """the row of /proc/sysvipc/<kind> for this key: {'perms': octal int, 'uid': n, 'cuid': n}"""
    with open("/proc/sysvipc/" + kind) as fh:
        lines = fh.read().split("\n")
    head = lines[0].split()
    for ln in lines[1:]:
        f = ln.split()
        if f and int(f[head.index("key")]) == key:
            return {"perms": int(f[head.index("perms")], 8), "uid": int(f[head.index("uid")]), "cuid": int(f[head.index("cuid")])}
    return None


def show(d):
    return {k: (oct(v) if k == "perms" else v) for k, v in d.items()}


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def layout(tmp, name, kind, daemon_src):
    """A scratch directory holding a COPY of the sandbox's sdlnxd; kind says what stands beside it.  Returns (directory, path of the copy)."""
    d = os.path.join(tmp, name)
    bindir = os.path.join(d, "libexec" if kind == "notbin" else "bin")
    os.makedirs(bindir)
    dst = os.path.join(bindir, "sdlnxd")
    shutil.copy2(daemon_src, dst)
    sd_solo = os.path.join(bindir, "sd-solo")
    ran = os.path.join(d, "ran")
    if kind in ("notbin", "nosd"):
        pass
    elif kind == "notexec":
        with open(sd_solo, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(sd_solo, 0o644)
    elif kind == "dir":
        os.mkdir(sd_solo)
    elif kind == "stub":
        with open(sd_solo, "w") as f:
            f.write("#!/bin/sh\necho \"$0 $*\" > '%s'\n" % ran)
        os.chmod(sd_solo, 0o755)
    return d, dst


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-shmmode-solo.py <dir> [--build]")
    box = os.path.abspath(args[0])
    sysd = os.path.join(box, "sys")
    keyset = int(os.environ.get("SDSOLOBOX_KEYSET", "0"))
    shm_key = 0x53434CA1 + 0x20 * keyset
    sem_key = 0x53434CA2 + 0x20 * keyset
    me = os.getuid()
    say("sandbox-shmmode-solo: sandbox %s, keyset %d, keys 0x%X / 0x%X, user %d" % (box, keyset, shm_key, sem_key, me))
    if "--build" in sys.argv:
        if os.path.exists(box) and os.listdir(box):
            bail("%s is not empty" % box)
        out = tool(box, "all", timeout=1800)
        if "[FAIL]" in out or "[PASS] THIRD.COMPILE" not in out:
            bail("the sandbox build did not pass:\n" + out[-800:])
        say("sandbox-shmmode-solo: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(sysd, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % box)
    tool(box, "start", timeout=120)

    shm = ipc("shm", shm_key)
    sem = ipc("sem", sem_key)
    if shm is None or sem is None:
        bail("the sandbox's segment or semaphores (keys 0x%X / 0x%X) are not there: %s" % (shm_key, sem_key, (shm, sem)))
    say("  segment %s, semaphores %s" % (show(shm), show(sem)))

    say("\n--- the segment ------------------------------------------------------------------------------------------")
    row("the segment is mode 0600 (it was 0666)", shm["perms"] & 0o777 == 0o600, oct(shm["perms"]))
    row("no access for group or others: those bits are 0", shm["perms"] & 0o077 == 0, oct(shm["perms"]))
    row("it belongs to the user who started SD (owner and creator)", shm["uid"] == me and shm["cuid"] == me, str(show(shm)))
    say("\n--- the semaphores ---------------------------------------------------------------------------------------")
    row("the semaphores are mode 0600 (they were 0666)", sem["perms"] & 0o777 == 0o600, oct(sem["perms"]))
    row("no access for group or others: those bits are 0", sem["perms"] & 0o077 == 0, oct(sem["perms"]))
    row("they belong to the user who started SD (owner and creator)", sem["uid"] == me and sem["cuid"] == me, str(show(sem)))

    say("\n--- a session of the same user still works ---------------------------------------------------------------")
    out = sess(box, "LISTU")
    listed = users_listed(out)
    row("CONTROL: a new session attaches the 0600 segment and runs LISTU, which lists a signed-on user (itself)", len(listed) >= 1, out[-300:])
    after = ipc("shm", shm_key)
    row("and the session left the mode and owner as they were", after is not None and after["perms"] == shm["perms"] and after["uid"] == me, str(after))

    daemon_src = os.path.join(sysd, "bin", "sdlnxd")
    if not os.path.isfile(daemon_src):
        bail("the sandbox has no %s" % daemon_src)
    tmp = tempfile.mkdtemp(prefix="shmsolo")
    conf = os.path.realpath(os.path.join(box, "sd.conf"))
    with open(conf, "rb") as f:
        conf_before = f.read()
    holder = None
    daemon = None
    restore_needed = False
    try:
        say("\n--- the daemon refuses a directory that is not its own ---------------------------------------------------")
        for kind, what in (("notbin", "its parent directory is not named bin"), ("nosd", "there is no sd-solo beside it"),
                           ("notexec", "the sd-solo beside it is not executable"), ("dir", "the sd-solo beside it is a directory")):
            d, dst = layout(tmp, kind, kind, daemon_src)
            try:
                p = subprocess.run([dst], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=15, cwd=tmp)
                row("B %s: the daemon ends with status 3 and says it cannot find its system directory" % what,
                    p.returncode == 3 and "cannot find the system directory" in p.stderr, "status %d, stderr %r" % (p.returncode, p.stderr[-200:]))
            except subprocess.TimeoutExpired:
                row("B %s: the daemon ends with status 3 and says it cannot find its system directory" % what, False,
                    "it was still running after 15 s (it attached the segment and went on)")

        say("\n--- the daemon runs the sd-solo that stands beside it ----------------------------------------------------")
        d, dst = layout(tmp, "own", "stub", daemon_src)
        ran = os.path.join(d, "ran")
        tool(box, "stop", timeout=300)
        restore_needed = True
        with open(conf, "wb") as f:
            f.write(conf_before + (b"" if conf_before.endswith(b"\n") else b"\n") + b"CLEANUP=30\n")
        tool(box, "start", timeout=300)
        if ipc("shm", shm_key) is None or ipc("sem", sem_key) is None:
            bail("the sandbox did not start again with CLEANUP=30 in sd.conf")
        say("  sd.conf now ends with CLEANUP=30; the sandbox was restarted")

        marker = os.path.join(sysd, "$internal")
        with open(marker, "w") as f:
            f.write("sandbox-shmmode-solo pid=%d %s\n" % (os.getpid(), time.strftime("%Y-%m-%dT%H:%M:%S")))
        env = dict(os.environ, SD_CONFIG=os.path.join(box, "sd.conf"), TERM="xterm", LC_ALL="C", LANG="C")
        env.pop("SDTEST_ADMIN", None)
        holder = subprocess.Popen([os.path.join(sysd, "bin", "sd-solo"), "-internal"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, cwd=sysd, env=env, text=True)
        holder.stdin.write("\nTERM 200,9999\nSLEEP 300\n")
        holder.stdin.flush()
        for _ in range(40):
            if not os.path.exists(marker):
                break
            time.sleep(0.5)
        admitted = not os.path.exists(marker)
        if os.path.exists(marker):
            os.remove(marker)
        say("  holder session: pid %d, admitted: %s" % (holder.pid, admitted))
        if not admitted:
            bail("the holder session was not admitted (its $internal marker is still there)")
        time.sleep(1)
        listed = users_listed(sess(box, "LISTU"))
        row("CONTROL: the holder session is signed on - LISTU lists its pid", holder.pid in listed.values(), "pids listed: %s" % sorted(listed.values()))
        holder.kill()
        holder.wait()
        time.sleep(1)
        listed = users_listed(sess(box, "LISTU"))
        row("CONTROL: the killed session is gone as a process but still in the table - this is what the daemon looks for",
            (not pid_alive(holder.pid)) and holder.pid in listed.values(), "alive %s, listed %s" % (pid_alive(holder.pid), sorted(listed.values())))
        holder = None

        errf = open(os.path.join(tmp, "daemon.err"), "w")
        daemon = subprocess.Popen([os.path.join(d, "bin", "sdlnxd")], stdin=subprocess.DEVNULL, stdout=errf, stderr=errf, cwd=tmp)
        say("  daemon started: pid %d, copied to %s; waiting up to 60 s for it to scan (CLEANUP=30, a tick every 10 s)" % (daemon.pid, d))
        end = time.time() + 60
        while time.time() < end and not os.path.exists(ran) and daemon.poll() is None:
            time.sleep(1)
        errf.flush()
        with open(os.path.join(tmp, "daemon.err"), errors="replace") as f:
            err = f.read()
        alive = daemon.poll() is None
        row("B the daemon was still running when the scan came (CONTROL: it did not end early)", alive, "status %s, output %r" % (daemon.poll(), err[-200:]))
        text = ""
        if os.path.exists(ran):
            with open(ran) as f:
                text = f.read().strip()
        row("B it found the lost process and ran the sd-solo BESIDE ITSELF with -cleanup (the stub wrote its name and arguments)",
            text == "%s/bin/sd-solo -cleanup" % d, "file says %r" % text)
        if alive:
            daemon.send_signal(signal.SIGTERM)
            try:
                daemon.wait(timeout=20)
                row("CONTROL: the daemon ends on SIGTERM", True)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()
                row("CONTROL: the daemon ends on SIGTERM", False, "it needed SIGKILL after 20 s")
        daemon = None
    finally:
        if holder is not None and holder.poll() is None:
            holder.kill()
            holder.wait()
        if daemon is not None and daemon.poll() is None:
            daemon.kill()
            daemon.wait()
        if restore_needed:
            tool(box, "stop", timeout=300)
            with open(conf, "wb") as f:
                f.write(conf_before)
            tool(box, "start", timeout=300)
            with open(conf, "rb") as f:
                same = f.read() == conf_before
            say("  sd.conf put back (%s); the sandbox was restarted" % ("identical" if same else "DIFFERENT"))
        shutil.rmtree(tmp, ignore_errors=True)

    say("")
    say("sandbox-shmmode-solo: %d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
