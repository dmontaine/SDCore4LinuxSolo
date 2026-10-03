#!/usr/bin/env python3
"""solo-sshguard.py - the lockout in front of Solo's own sshd (LSOLO 29).

  solo-sshguard.py TREE SSHD            serve ONE connection: stdin is the connection socket
                                        (this is the unit's ExecStart, one process per connection)
  solo-sshguard.py TREE --list          who is locked, who has failures
  solo-sshguard.py TREE --unlock ADDR   forget one address
  solo-sshguard.py TREE --unlock all    forget every address

OWNER, 2 Oct 2026: Solo's ssh takes the Linux account name and password, so anyone who can reach
the port can guess it; he asked for the lockout Windows has.  This is the version that needs no
root and cannot lock the OWNER out: PER ADDRESS.  Three wrong passwords from one address within ten
minutes, and that address is refused for ten minutes.  The lockout is not the computer's: the
Linux account is never locked, the computer's own ssh server and console are not touched.

HOW.  systemd starts this for every connection instead of starting sshd.  It reads the peer
address from the connection itself (never from anything sshd or the client prints), refuses at
once if that address is locked, and otherwise runs "sshd -i -e -f TREE/sshd/sshd_config" with
the same connection and reads sshd's own log lines from its standard error:

    "Failed password for ..."   one wrong password: count it, and at three LOCK the address AND KILL
                                this connection's sshd (a client that is not the stock ssh may be
                                allowed six tries per connection)
    "Accepted ..."              a sign-in: forget that address's failures

Only a failed PASSWORD counts: a client that offers several keys the server does not know (an ssh
agent) fails publickey over and over and must not be punished for it.  Every line sshd prints is
passed on to the journal unchanged, followed by this guard's own "sd-solo-sshguard:" lines.

THE STATE is TREE/sshd/guard.json (mode 0600), changed under a lock so connections that overlap
cannot lose each other's failures.  Entries older than the window are dropped whenever it is written.

WHAT IT DOES NOT DO: stop a guess spread over MANY addresses (each address gets its three), and a
burst of connections that all start before the third failure is recorded can each make up to
three tries (each is killed when the lock engages).  It does not need the clock to be right beyond
ordinary drift.  TEST HOOK, NOT A FEATURE: SDSOLO_TEST_NOW (seconds since the epoch) replaces the
clock, so the unit test can move time; a real unit never sets it.
"""

import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

MAX_FAILS = 3        # wrong passwords from one address ...
WINDOW = 600         # ... within this many seconds lock it ...
LOCK = 600           # ... for this many seconds


def now():
    t = os.environ.get("SDSOLO_TEST_NOW")
    return float(t) if t else time.time()


def say(msg):
    sys.stderr.write("sd-solo-sshguard: %s\n" % msg)
    sys.stderr.flush()


class State:
    """TREE/sshd/guard.json under TREE/sshd/guard.lock; use as a context manager."""

    def __init__(self, tree):
        d = os.path.join(tree, "sshd")
        self.path = os.path.join(d, "guard.json")
        self.lockpath = os.path.join(d, "guard.lock")
        self.data = {}

    def __enter__(self):
        self.lock = os.open(self.lockpath, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            with open(self.path) as f:
                self.data = json.load(f)
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}
        return self

    def prune(self):
        t = now()
        for addr in list(self.data):
            e = self.data[addr]
            e["fails"] = [x for x in e.get("fails", []) if t - x < WINDOW]
            if e.get("locked_until", 0) <= t:
                e.pop("locked_until", None)
            if not e["fails"] and "locked_until" not in e:
                del self.data[addr]

    def save(self):
        self.prune()
        tmp = self.path + ".%d.tmp" % os.getpid()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def __exit__(self, *exc):
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        os.close(self.lock)
        return False


def peer_address():
    s = socket.socket(fileno=os.dup(0))
    try:
        a = s.getpeername()
    except OSError:
        return "local"
    finally:
        s.detach()
    host = a[0] if isinstance(a, tuple) else str(a)
    if host.startswith("::ffff:"):
        host = host[7:]
    return host.split("%")[0] or "local"


def serve(tree, sshd):
    addr = peer_address()
    with State(tree) as st:
        until = st.data.get(addr, {}).get("locked_until", 0)
        if until > now():
            say("refusing %s: locked until %s after %d wrong passwords within %d minutes"
                % (addr, time.strftime("%H:%M:%S", time.localtime(until)), MAX_FAILS, WINDOW // 60))
            return 0
    # Its own process group, so one signal reaches sshd AND the unprivileged child it forks for the session.
    proc = subprocess.Popen([sshd, "-i", "-e", "-f", os.path.join(tree, "sshd", "sshd_config")],
                            stderr=subprocess.PIPE, universal_newlines=True, errors="replace",
                            start_new_session=True)
    killed = False

    def stop_group(sig):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
    for line in proc.stderr:
        sys.stderr.write(line)
        sys.stderr.flush()
        text = line.strip()
        if text.startswith("Failed password for "):
            with State(tree) as st:
                e = st.data.setdefault(addr, {"fails": []})
                e["fails"] = [x for x in e.get("fails", []) if now() - x < WINDOW] + [now()]
                tripped = len(e["fails"]) >= MAX_FAILS
                if tripped:
                    e["locked_until"] = now() + LOCK
                st.save()
            if tripped and not killed:
                say("locking %s for %d minutes: %d wrong passwords within %d minutes"
                    % (addr, LOCK // 60, MAX_FAILS, WINDOW // 60))
                killed = True
                stop_group(signal.SIGTERM)
                threading.Timer(3.0, stop_group, (signal.SIGKILL,)).start()   # whatever ignored the first
        elif text.startswith("Accepted "):
            with State(tree) as st:
                if addr in st.data:
                    del st.data[addr]
                st.save()
    rc = proc.wait()
    return 0 if killed else rc


def admin(tree, args):
    with State(tree) as st:
        st.prune()
        if args[0] == "--list":
            locked = 0
            for addr in sorted(st.data):
                e = st.data[addr]
                if e.get("locked_until"):
                    locked += 1
                    print("%s  LOCKED until %s  (%d wrong passwords)"
                          % (addr, time.strftime("%H:%M:%S", time.localtime(e["locked_until"])), len(e["fails"])))
                else:
                    print("%s  %d wrong password(s), not locked" % (addr, len(e["fails"])))
            print("SOLO SSH GUARD LOCKED %d" % locked)
            return 0
        if args[0] == "--unlock" and len(args) == 2:
            if args[1] == "all":
                n = len(st.data)
                st.data = {}
            else:
                n = 1 if st.data.pop(args[1], None) is not None else 0
            st.save()
            print("SOLO SSH GUARD UNLOCKED %d" % n)
            return 0
    sys.stderr.write("usage: solo-sshguard.py TREE SSHD | TREE --list | TREE --unlock ADDRESS|all\n")
    return 2


def main(argv):
    if len(argv) >= 3 and argv[1].startswith("/") and os.path.isdir(os.path.join(argv[1], "sshd")):
        if argv[2].startswith("--"):
            return admin(argv[1], argv[2:])
        return serve(argv[1], argv[2])
    sys.stderr.write("usage: solo-sshguard.py TREE SSHD | TREE --list | TREE --unlock ADDRESS|all\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
