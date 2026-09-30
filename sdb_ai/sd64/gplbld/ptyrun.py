#!/usr/bin/env python3
#
# ptyrun.py - drive one interactive "sd" session over a pseudo-terminal.
#
#   python3 ptyrun.py [--env NAME=VALUE]... [--timeout SECONDS] SD_BINARY STEP...
#
# A STEP is  expect:REGEX  (wait until the output so far matches; the match is
# consumed)  or  send:TEXT  (type TEXT and Enter - a pty's Enter is CR).
# Nothing is ever sent before its preceding expect matched: input typed AHEAD of
# sd over a pty is discarded (measured 30 Sep 2026), so a script that sent early
# would be measuring nothing.
#
# It prints the transcript (screen escapes removed) between two marker lines and
# exits 0 when every step ran, 2 naming the step that did not, 3 when sd could
# not be started.  The text of a send: step is never printed - it may be a
# password - and is replaced by <sent> in the transcript header.
#
# Used by verify-solo-firstlogin.sh; usable by any witness that must talk to sd
# the way a person at a keyboard does (LSOLO 10's owed installer-prompt leg).

import os
import pty
import re
import select
import signal
import sys
import time


def main():
    args = sys.argv[1:]
    env = dict(os.environ)
    timeout = 30.0
    argv_extra = []
    while args and args[0] in ("--env", "--timeout", "--arg"):
        if args[0] == "--env":
            k, v = args[1].split("=", 1)
            env[k] = v
        elif args[0] == "--arg":
            argv_extra.append(args[1])   # an argument for the program, in order
        else:
            timeout = float(args[1])
        args = args[2:]
    if len(args) < 2:
        print("usage: ptyrun.py [--env N=V] [--timeout S] [--arg A]... PROGRAM STEP...", file=sys.stderr)
        return 3
    sd, steps = args[0], args[1:]
    # An SSH_CONNECTION set by the caller's own environment would silently turn a
    # console test into an ssh one; the caller must ask for it with --env.
    if not any(a == "--env" for a in sys.argv[1:]):
        env.pop("SSH_CONNECTION", None)
        env.pop("SSH_TTY", None)

    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execve(sd, [sd] + argv_extra, env)
        except OSError as e:
            os.write(2, ("ptyrun: cannot start %s: %s\n" % (sd, e)).encode())
            os._exit(127)

    esc = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
    buf = b""
    rc = 0
    failed = None
    consumed = 0

    def pump(deadline):
        nonlocal buf
        r, _, _ = select.select([fd], [], [], max(0.0, deadline - time.time()))
        if not r:
            return False
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            return False
        if not chunk:
            return False
        buf += chunk
        return True

    for i, step in enumerate(steps):
        kind, _, val = step.partition(":")
        if kind == "expect":
            rx = re.compile(val)
            deadline = time.time() + timeout
            while True:
                # The screen text so far; a match consumes only up to its own end,
                # so a prompt that arrived in the same read is still there for the
                # next expect.
                screen = esc.sub(b"", buf).replace(b"\r", b"").decode("utf-8", "replace")
                m = rx.search(screen, consumed)
                if m:
                    consumed = m.end()
                    break
                if time.time() >= deadline:
                    failed = "step %d: expect:%s (timed out after %ss)" % (i + 1, val, timeout)
                    break
                if not pump(deadline):
                    screen = esc.sub(b"", buf).replace(b"\r", b"").decode("utf-8", "replace")
                    m = rx.search(screen, consumed)
                    if m:
                        consumed = m.end()
                        break
                    failed = "step %d: expect:%s (sd ended first or nothing arrived)" % (i + 1, val)
                    break
            if failed:
                break
            time.sleep(0.15)   # let sd reach its read before anything is typed
        elif kind == "send":
            os.write(fd, val.encode() + b"\r")
        else:
            failed = "step %d: unknown step kind '%s'" % (i + 1, kind)
            break

    # Let the tail arrive, then end the session.
    end = time.time() + 2.0
    while time.time() < end and pump(end):
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass

    out = esc.sub(b"", buf).replace(b"\r", b"").decode("utf-8", "replace")
    print("----- ptyrun transcript (%d steps; send: texts not shown) -----" % len(steps))
    print(out)
    print("----- end of transcript -----")
    if failed:
        print("ptyrun: " + failed)
        return 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
