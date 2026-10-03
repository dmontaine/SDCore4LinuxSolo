#!/usr/bin/env python3
"""test-sshguard-units.py - gplbld/solo-sshguard.py, the per-address lockout in front of Solo's sshd (LSOLO 29).

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-sshguard-units.py
  python3 .../test-sshguard-units.py --selftest     each mutant must go red

No sudo, no install, no sd.  Exit 0 every row passed, 1 a row failed, 2 it could not run.  Written 2 Oct 26.
(Owner, 2 Oct 2026: "is there any way to implement the 3 tries lockout that windows has" - chosen:
per address, 3 wrong passwords in 10 minutes lock that address for 10 minutes.)

WHAT IT MEASURES.  Every row runs the REAL guard on a REAL TCP connection (client addresses 127.0.0.2,
127.0.0.3 ... are all loopback, so "another address" is real), with a FAKE sshd that prints the log lines
the real one prints, so the state logic can be driven exactly; and END-TO-END rows run the real sshd with the
configuration solo-ssh.sh writes and type wrong passwords at ssh's own prompt through a pty.
  LOCK rows   - two wrong passwords do not lock, the third does AND kills that connection's sshd; the next
                connection from that address is refused WITHOUT starting sshd; another address is not
                affected; key failures never count; a sign-in forgets the failures; failures older than the
                window and a lock older than its length are forgotten.
  ADMIN rows  - --list, --unlock, the state file's mode, the usage refusal.
  END-TO-END  - real sshd, wrong passwords: the first two get the ordinary refusal, the fourth connection is
                refused outright, "locked" names the address, "unlock" lets it in again.

THE NULL CASE IS REFUSED: without sshd, ssh or python3's pty the end-to-end rows cannot run and the run exits 2;
--selftest builds mutant copies of the guard (never locks, records nothing, lock not enforced, key failures
counted, a sign-in not forgetting, sshd not killed, the window ignored, the lock never ending) and requires each
to fail at least one row.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "solo-sshguard.py")
SSH_TOOL = os.path.join(HERE, "solo-ssh.sh")
HOME = os.path.expanduser("~")
USER = os.environ.get("USER") or os.popen("id -un").read().strip()
RESULTS = {"pass": 0, "fail": 0}


def say(s=""):
    print(s)
    sys.stdout.flush()


def row(kind, name, ok, detail):
    RESULTS["pass" if ok else "fail"] += 1
    say("  [%s] %-6s %s" % ("PASS" if ok else "FAIL", kind, name))
    for line in detail:
        say("         | " + line)


FAKE_SSHD = """#!/usr/bin/env python3
# a stand-in for sshd -i -e -f CONFIG: prints the lines named in <tree>/fake.script on stderr, one per line;
# "sleep N" waits; the last thing it does, after "survive", is print SURVIVED (it never gets there if killed)
import os, sys, time
tree = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[sys.argv.index("-f") + 1])))
with open(os.path.join(tree, "started.log"), "a") as f:
    f.write("%d\\n" % os.getpid())
for line in open(os.path.join(tree, "fake.script")).read().splitlines():
    if line.startswith("sleep "):
        time.sleep(float(line.split()[1]))
    elif line == "survive":
        sys.stderr.write("SURVIVED\\n"); sys.stderr.flush()
    else:
        sys.stderr.write(line + "\\n"); sys.stderr.flush()
"""


def make_tree(base):
    tree = os.path.join(base, "tree")
    os.makedirs(os.path.join(tree, "sshd"))
    os.makedirs(os.path.join(tree, "bin"))
    os.chmod(tree, 0o700)
    with open(os.path.join(tree, ".sdcoresolo"), "w"):
        pass
    fake = os.path.join(tree, "fake-sshd")
    with open(fake, "w") as f:
        f.write(FAKE_SSHD)
    os.chmod(fake, 0o755)
    # the fake finds "<tree>/fake.script" from its -f argument (tree/sshd/sshd_config)
    with open(os.path.join(tree, "sshd", "sshd_config"), "w") as f:
        f.write("# fake\n")
    return tree, fake


def connection(client_addr):
    """A real loopback TCP connection whose SERVER end's peer is client_addr; returns (server_side, client_side)."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    cli = socket.socket()
    cli.bind((client_addr, 0))
    cli.connect(srv.getsockname())
    conn, _ = srv.accept()
    srv.close()
    return conn, cli


def run_guard(tree, fake, client_addr, script, now=None, guard=GUARD, timeout=20):
    """One connection from client_addr served by the guard over the fake sshd; returns (rc, guard stderr)."""
    with open(os.path.join(tree, "fake.script"), "w") as f:
        f.write("\n".join(script) + "\n")
    conn, cli = connection(client_addr)
    env = dict(os.environ)
    if now is not None:
        env["SDSOLO_TEST_NOW"] = str(now)
    try:
        p = subprocess.Popen([sys.executable, guard, tree, fake], stdin=conn, stdout=conn, stderr=subprocess.PIPE, env=env)
        _, err = p.communicate(timeout=timeout)
        return p.returncode, err.decode("utf-8", "replace")
    finally:
        conn.close()
        cli.close()


def state(tree):
    try:
        return json.load(open(os.path.join(tree, "sshd", "guard.json")))
    except (OSError, ValueError):
        return {}


def started(tree):
    try:
        return len(open(os.path.join(tree, "started.log")).read().split())
    except OSError:
        return 0


FAIL = "Failed password for don from 127.0.0.2 port 5555 ssh2"


def suite(guard, work):
    tree, fake = make_tree(work)
    A, B = "127.0.0.2", "127.0.0.3"
    T0 = 1_800_000_000

    # ------------------------------------------------------------------ LOCK rows
    rc1, err1 = run_guard(tree, fake, A, [FAIL, "survive"], now=T0, guard=guard)
    rc2, err2 = run_guard(tree, fake, A, [FAIL, "survive"], now=T0 + 1, guard=guard)
    s2 = state(tree).get(A, {})
    row("LOCK", "one and two wrong passwords are counted and do not lock",
        len(s2.get("fails", [])) == 2 and "locked_until" not in s2 and "SURVIVED" in err1 and "SURVIVED" in err2,
        ["  after two connections: %s" % {A: s2}])
    rc3, err3 = run_guard(tree, fake, A, [FAIL, "sleep 6", "survive"], now=T0 + 2, guard=guard)
    s3 = state(tree).get(A, {})
    row("LOCK", "the third wrong password LOCKS the address and KILLS that connection's sshd",
        s3.get("locked_until") == T0 + 2 + 600 and "SURVIVED" not in err3 and "locking %s" % A in err3,
        ["  state: %s ; guard said: %r ; the sshd survived: %s" % (s3, [l for l in err3.splitlines() if "sshguard" in l][:1], "SURVIVED" in err3)])
    n_before = started(tree)
    rc4, err4 = run_guard(tree, fake, A, ["survive"], now=T0 + 3, guard=guard)
    row("LOCK", "the next connection from that address is refused WITHOUT starting sshd",
        started(tree) == n_before and "refusing %s" % A in err4 and "SURVIVED" not in err4,
        ["  sshd started %d time(s) before, %d after; guard said: %r" % (n_before, started(tree), err4.strip()[:100])])
    rc5, err5 = run_guard(tree, fake, B, ["survive"], now=T0 + 3, guard=guard)
    row("LOCK", "another address is not affected",
        "SURVIVED" in err5 and started(tree) == n_before + 1,
        ["  %s: sshd started and ran (%s)" % (B, "SURVIVED" in err5)])
    rc6, err6 = run_guard(tree, fake, B, ["Failed publickey for don from %s port 1 ssh2" % B] * 5 + ["survive"], now=T0 + 4, guard=guard)
    row("LOCK", "failed KEYS never count (an ssh agent with several keys must not be punished)",
        B not in state(tree) and "SURVIVED" in err6, ["  state for %s: %s" % (B, state(tree).get(B))])
    run_guard(tree, fake, B, [FAIL.replace("127.0.0.2", B), FAIL.replace("127.0.0.2", B)], now=T0 + 5, guard=guard)
    two = len(state(tree).get(B, {}).get("fails", []))
    run_guard(tree, fake, B, ["Accepted password for don from %s port 5 ssh2" % B, "survive"], now=T0 + 6, guard=guard)
    gone = B not in state(tree)
    row("LOCK", "a sign-in forgets that address's wrong passwords",
        two == 2 and gone, ["  before the sign-in %d failure(s); after: %s" % (two, "forgotten" if gone else state(tree).get(B))])
    C = "127.0.0.4"
    run_guard(tree, fake, C, [FAIL.replace("127.0.0.2", C)] * 2, now=T0, guard=guard)
    run_guard(tree, fake, C, [FAIL.replace("127.0.0.2", C)], now=T0 + 601, guard=guard)
    sc = state(tree).get(C, {})
    row("LOCK", "wrong passwords older than the ten-minute window are forgotten (two at t, one at t+601 s is one, not three)",
        len(sc.get("fails", [])) == 1 and "locked_until" not in sc, ["  state: %s" % sc])
    n_before = started(tree)
    rc7, err7 = run_guard(tree, fake, A, ["survive"], now=T0 + 2 + 601, guard=guard)
    row("LOCK", "a lock ends after ten minutes: the address is served again",
        started(tree) == n_before + 1 and "SURVIVED" in err7, ["  sshd started again: %s" % (started(tree) == n_before + 1)])

    # ------------------------------------------------------------------ ADMIN rows
    run_guard(tree, fake, A, [FAIL] * 3, now=T0 + 10_000, guard=guard)
    env = dict(os.environ, SDSOLO_TEST_NOW=str(T0 + 10_001))
    lst = subprocess.run([sys.executable, guard, tree, "--list"], capture_output=True, env=env)
    out = lst.stdout.decode()
    row("ADMIN", "--list names the locked address and ends 'SOLO SSH GUARD LOCKED <n>'",
        lst.returncode == 0 and re.search(r"^127\.0\.0\.2  LOCKED until ", out, re.M) and "SOLO SSH GUARD LOCKED 1" in out,
        ["  " + l for l in out.splitlines()[-2:]])
    mode = os.stat(os.path.join(tree, "sshd", "guard.json")).st_mode & 0o777
    row("ADMIN", "the state file is mode 0600", mode == 0o600, ["  mode %s" % oct(mode)])
    un = subprocess.run([sys.executable, guard, tree, "--unlock", A], capture_output=True, env=env)
    row("ADMIN", "--unlock ADDRESS forgets it ('SOLO SSH GUARD UNLOCKED 1') and it is served again",
        un.returncode == 0 and b"SOLO SSH GUARD UNLOCKED 1" in un.stdout and A not in state(tree),
        ["  " + un.stdout.decode().strip()])
    bad = subprocess.run([sys.executable, guard, tree], capture_output=True)
    row("ADMIN", "no operation is a usage refusal (exit 2)", bad.returncode == 2 and b"usage" in bad.stderr,
        ["  exit %d %r" % (bad.returncode, bad.stderr.decode().strip()[:80])])

    # ------------------------------------------------------------------ END-TO-END with the real sshd
    e2e(guard, work)


def e2e(guard, work):
    import pty
    import select
    tree = os.path.join(work, "e2etree")
    os.makedirs(os.path.join(tree, "bin"))
    os.makedirs(os.path.join(tree, "tools"))
    os.chmod(tree, 0o700)
    with open(os.path.join(tree, "bin", "sd-solo"), "w") as f:
        f.write("#!/bin/sh\necho STANDIN\n")
    os.chmod(os.path.join(tree, "bin", "sd-solo"), 0o755)
    open(os.path.join(tree, ".sdcoresolo"), "w").close()
    shutil.copy(guard, os.path.join(tree, "tools", "solo-sshguard.py"))
    shutil.copy(SSH_TOOL, os.path.join(tree, "tools", "solo-ssh.sh"))
    rc = subprocess.run(["bash", os.path.join(tree, "tools", "solo-ssh.sh"), "setup", tree], capture_output=True)
    if rc.returncode != 0:
        row("E2E", "solo-ssh.sh setup for the end-to-end tree", False, ["  " + rc.stderr.decode()[-200:]])
        return
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    lis = subprocess.Popen(["systemd-socket-activate", "--accept", "--inetd", "-l", "127.0.0.1:%d" % port, "--",
                            sys.executable, os.path.join(tree, "tools", "solo-sshguard.py"), tree, "/usr/sbin/sshd"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    # the readiness probe above is itself a connection, but it types nothing: no failure is recorded for it

    def wrong():
        cmd = ["ssh", "-p", str(port), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
               "-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
               "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=10", USER + "@127.0.0.1"]
        pid, fd = pty.fork()
        if pid == 0:
            os.execvp("ssh", cmd)
        out, sent, t0 = b"", False, time.time()
        while time.time() - t0 < 20:
            r, _, _ = select.select([fd], [], [], 1)
            if r:
                try:
                    d = os.read(fd, 4096)
                except OSError:
                    break
                if not d:
                    break
                out += d
                if b"assword:" in out and not sent:
                    time.sleep(0.3)
                    os.write(fd, b"a-deliberately-wrong-password\r")
                    sent = True
        try:
            os.waitpid(pid, os.WNOHANG)
        except OSError:
            pass
        return out.decode("utf-8", "replace").replace("\r", "")
    try:
        r1, r2, r3 = wrong(), wrong(), wrong()
        r4 = wrong()
        lk = subprocess.run(["bash", SSH_TOOL, "locked", tree], capture_output=True).stdout.decode()
        row("E2E", "with the real sshd: wrong passwords 1 and 2 get the ordinary refusal, the 3rd locks, the 4th connection is refused outright",
            "Permission denied" in r1 and "Permission denied" in r2 and "assword:" in r3
            and "assword:" not in r4 and ("reset" in r4 or "closed" in r4.lower() or r4.strip() == ""),
            ["  #1 %r" % r1.strip().replace("\n", " | ")[-70:], "  #2 %r" % r2.strip().replace("\n", " | ")[-70:],
             "  #3 %r" % r3.strip().replace("\n", " | ")[-50:], "  #4 %r" % r4.strip().replace("\n", " | ")[-70:]])
        row("E2E", "solo-ssh.sh locked names the address",
            "127.0.0.1  LOCKED until" in lk and "SOLO SSH GUARD LOCKED 1" in lk, ["  " + l for l in lk.strip().splitlines()[-2:]])
        un = subprocess.run(["bash", SSH_TOOL, "unlock", tree, "127.0.0.1"], capture_output=True).stdout.decode()
        r5 = wrong()
        row("E2E", "solo-ssh.sh unlock lets the address in again (the password prompt is offered)",
            "SOLO SSH GUARD UNLOCKED 1" in un and "assword:" in r5, ["  " + un.strip(), "  #5 %r" % r5.strip().replace("\n", " | ")[-60:]])
    finally:
        lis.terminate()
        try:
            lis.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            lis.kill()


def read(p):
    return open(p).read()


MUTANTS = [
    ("never locks", "MAX_FAILS = 3 ", "MAX_FAILS = 3000 "),
    ("records nothing", 'e["fails"] = [x for x in e.get("fails", []) if now() - x < WINDOW] + [now()]',
     'e["fails"] = [x for x in e.get("fails", []) if now() - x < WINDOW]'),
    ("lock not enforced", "if until > now():", "if False:"),
    ("key failures counted", 'text.startswith("Failed password for ")', 'text.startswith("Failed ")'),
    ("sign-in does not forget", "                if addr in st.data:\n                    del st.data[addr]\n", "                pass\n"),
    ("sshd not killed", "                stop_group(signal.SIGTERM)\n                threading.Timer(3.0, stop_group, (signal.SIGKILL,)).start()   # whatever ignored the first\n", ""),
    ("window ignored", "WINDOW = 600 ", "WINDOW = 10 ** 9 "),
    ("lock never ends", "LOCK = 600 ", "LOCK = 10 ** 9 "),
]


def main():
    selftest = "--selftest" in sys.argv[1:]
    say("test-sshguard-units: %s" % GUARD)
    missing = [t for t in ("ssh", "systemd-socket-activate", "ssh-keygen") if not shutil.which(t)] + ([] if os.path.exists("/usr/sbin/sshd") else ["/usr/sbin/sshd"])
    if missing or not os.path.isfile(GUARD):
        say("CANNOT RUN - missing: %s" % (", ".join(missing) or GUARD))
        return 2
    base = tempfile.mkdtemp(prefix=".zz-sshguard-", dir=HOME)
    os.chmod(base, 0o700)
    try:
        work = os.path.join(base, "real")
        os.makedirs(work)
        say("  scratch: %s\n" % base)
        suite(GUARD, work)
        if RESULTS["pass"] + RESULTS["fail"] == 0:
            say("\nREFUSED: the null case - no rows ran")
            return 2
        say("\n%(pass)d passed, %(fail)d failed" % RESULTS)
        if RESULTS["fail"]:
            return 1
        if not selftest:
            return 0
        src = read(GUARD)
        red = 0
        for label, old, new in MUTANTS:
            if src.count(old) != 1:
                say("CANNOT RUN - mutant '%s': expected one match of its target, found %d" % (label, src.count(old)))
                return 2
            mt = os.path.join(base, "m-" + re.sub(r"[^a-z0-9]+", "-", label))
            os.makedirs(mt)
            mg = os.path.join(mt, "solo-sshguard.py")
            open(mg, "w").write(src.replace(old, new))
            for k in RESULTS:
                RESULTS[k] = 0
            mw = os.path.join(mt, "work")
            os.makedirs(mw)
            say("\n--- mutant: %s" % label)
            suite(mg, mw)
            went_red = RESULTS["fail"] > 0
            red += went_red
            say("--- mutant '%s': %s (%d rows failed)" % (label, "RED as it must be" if went_red else "STILL GREEN - the test misses it", RESULTS["fail"]))
        say("\nselftest: %d of %d mutants went red" % (red, len(MUTANTS)))
        return 0 if red == len(MUTANTS) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
