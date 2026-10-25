#!/usr/bin/env python3
#
# sandbox-auditrot-solo.py - W.11 carry, step 3 (25 Oct 2026): "sd-solo -start" rotates a trail of 1 MB or more (k_error.c audit_rotate()) and does NOT rotate onto a name that
# is already a file.  The rotated name is "audit.YYYYMMDD-HHMMSS", a second's resolution, and rename() replaces what is there; SD Core found two rotations in one second leaving one
# rotated file (its sandbox-auditwriter.py W11) and refused the rotation.  No install, no sudo, no systemd.
#
#   SDSOLOBOX_KEYSET=<n> python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-auditrot-solo.py <dir> [--build]
#
# <dir> is a sandbox made by sandbox-fromtree.py.  With --build it is built first from THIS tree (it must be empty or absent).  Exit 0 every row passed, 1 a row failed, 2 it
# could not run (including: the planted trail was not what the suite meant it to be, the null case).
#
# START-HISTORY:
# 25 Oct 26 dm  New.  k_error.c audit_rotate().
# END-HISTORY
#
# THE EVIDENCE.  Files in <dir>/sys.  Part A plants a trail of 1 MB and a little more, plants a file under EVERY name the rotation could take in the seconds around the start
# (so that whichever second the start lands in, its name is taken), runs "sd-solo -start -nodaemon", and compares the trail and every planted name with what was planted (size and
# SHA-256).  Part B is the control that the refusal does not break the rotation: the same trail, no planted names, and the start must rename it to one new audit.<stamp> that holds
# exactly the planted bytes and leave a new, empty, owner-only audit behind.  The suite stops the sandbox through the harness first and hands it back at the end.
# NOT SAID HERE: the append-only attribute (a sandbox user cannot set it) and the daemon (this suite starts with -nodaemon).

import hashlib
import os
import re
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ROTATED = re.compile(r"^audit\.\d{8}-\d{6}$")
LIMIT = 1048576                # AUDIT_ROTATE_BYTES in k_error.c
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
    say("sandbox-auditrot-solo: CANNOT RUN - " + msg)
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


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-auditrot-solo.py <dir> [--build]")
    box = os.path.abspath(args[0])
    keyset = int(os.environ.get("SDSOLOBOX_KEYSET", "0"))
    keys = (0x53434CA1 + 0x20 * keyset, 0x53434CA2 + 0x20 * keyset)
    live_keys = (0x53434C11, 0x53434C12)
    say("sandbox-auditrot-solo: sandbox %s, keyset %d, keys 0x%X / 0x%X, user %d" % (box, keyset, keys[0], keys[1], os.getuid()))
    if "--build" in sys.argv:
        if os.path.exists(box) and os.listdir(box):
            bail("%s is not empty" % box)
        out = tool(box, "all", timeout=1800)
        if "[FAIL]" in out or "[PASS] THIRD.COMPILE" not in out:
            bail("the sandbox build did not pass:\n" + out[-800:])
        say("sandbox-auditrot-solo: built, bootstrap passed")
        box = os.path.realpath(box)
    sysd = os.path.join(box, "sys")
    sd = os.path.join(sysd, "bin", "sd-solo")
    audit = os.path.join(sysd, "audit")
    if not os.path.isfile(sd):
        bail("%s holds no built sandbox (use --build, or point it at one)" % box)
    env = dict(os.environ, SD_CONFIG=os.path.join(box, "sd.conf"))
    env.pop("SDTEST_ADMIN", None)

    # THIS SUITE RUNS "sd-solo -start" AND "-stop" ITSELF: read the binary for the key it will use first (the sandbox's pair in it, the live Solo's not), as sandbox-lnxd-solo.py does.
    data = open(sd, "rb").read()
    if struct.pack("<I", keys[0]) not in data or struct.pack("<I", keys[1]) not in data:
        bail("%s does not carry this sandbox's keys 0x%X / 0x%X" % (sd, keys[0], keys[1]))
    if struct.pack("<I", live_keys[0]) in data or struct.pack("<I", live_keys[1]) in data:
        bail("%s carries the live Solo's key: it would stop or attach to the Solo that runs on this computer" % sd)
    live_before = held_keys(live_keys)
    say("  the binary carries the sandbox's keys and not the live Solo's; the live Solo's segment and semaphores are held now: %r" % (live_before,))

    def sd_run(args_, name):
        outf = os.path.join(box, "auditrot-%s-%d.out" % (name, time.time_ns()))
        say("    > sd-solo " + " ".join(args_))
        with open(outf, "w") as fh:
            rc = subprocess.run([sd] + args_, stdout=fh, stderr=subprocess.STDOUT, env=env, cwd=sysd, timeout=90).returncode
        with open(outf, errors="replace") as fh:
            return rc, fh.read()

    def rotated_names():
        return sorted(n for n in os.listdir(sysd) if ROTATED.match(n))

    def plant_trail(extra):
        """A trail of LIMIT + extra bytes of numbered lines, mode 0600; returns (size, sha256)"""
        line = "zzplant %06d " + "x" * 100 + "\n"
        with open(audit, "w") as fh:
            i, n = 0, 0
            while n < LIMIT + extra:
                s = line % i
                fh.write(s)
                n += len(s)
                i += 1
        os.chmod(audit, 0o600)
        return os.path.getsize(audit), sha(audit)

    had_audit = os.path.exists(audit)
    orig = open(audit, "rb").read() if had_audit else None
    orig_mode = (os.stat(audit).st_mode & 0o7777) if had_audit else 0o600
    names_before = rotated_names()
    made = []
    try:
        say("\n--- the null case --------------------------------------------------------------------------------------")
        tool(box, "stop", timeout=300)
        row("N0 with SD stopped the sandbox's keys are not held", held_keys(keys) == (False, False), "keys %r" % (held_keys(keys),))
        if held_keys(keys) != (False, False):
            bail("the sandbox's keys are still held after the harness's stop")

        say("\n--- A. a taken name: the trail is not rotated -------------------------------------------------------------")
        size0, sum0 = plant_trail(4096)
        t0 = int(time.time())
        held = {}
        for t in range(t0 - 1, t0 + 9):
            p = os.path.join(sysd, "audit." + time.strftime("%Y%m%d-%H%M%S", time.localtime(t)))
            if not os.path.exists(p):
                with open(p, "w") as fh:
                    fh.write("placeholder %s\n" % os.path.basename(p))
                made.append(p)
            held[p] = sha(p)
        before = set(rotated_names())
        row("A0 (null case) the trail is %d bytes (at least the 1 MB limit) and a file stands under each of the %d names the start could rotate onto" % (size0, len(held)),
            size0 >= LIMIT and len(held) == 10 and all(os.path.exists(p) for p in held), "size %d, names %d" % (size0, len(held)))
        rc, out = sd_run(["-start", "-nodaemon"], "taken")
        after = set(rotated_names())
        row("A1 'sd-solo -start -nodaemon' starts SD (exit 0): a refused rotation does not stop the start", rc == 0 and held_keys(keys) == (True, True),
            "exit %d, keys %r, stdout %r" % (rc, held_keys(keys), out.strip()[-160:]))
        row("A2 the trail is whole: the same size and the same SHA-256 as planted", os.path.exists(audit) and os.path.getsize(audit) == size0 and sha(audit) == sum0,
            "size %s of %d" % (os.path.getsize(audit) if os.path.exists(audit) else None, size0))
        changed = [os.path.basename(p) for p, s in held.items() if not os.path.exists(p) or sha(p) != s]
        row("A3 and every file that stood under a name this second could take is as it was (rename() would have replaced one)", changed == [], "changed: %r" % changed)
        row("A4 no other rotated file appeared", after == before, "new: %r" % sorted(after - before))
        sd_run(["-stop"], "taken-stop")
        for p in held:
            if p in made and os.path.exists(p):
                os.remove(p)
        made = []

        say("\n--- B. (control) a free name: the trail IS rotated ---------------------------------------------------------")
        size1, sum1 = plant_trail(4096)
        before = set(rotated_names())
        row("B0 (null case) the trail is planted again, %d bytes, and no placeholder is left" % size1, size1 >= LIMIT and before == set(names_before), "size %d, rotated names %r" % (size1, sorted(before)))
        rc, out = sd_run(["-start", "-nodaemon"], "free")
        new = sorted(set(rotated_names()) - before)
        made.extend(os.path.join(sysd, n) for n in new)
        row("B1 'sd-solo -start -nodaemon' starts SD (exit 0)", rc == 0 and held_keys(keys) == (True, True), "exit %d, stdout %r" % (rc, out.strip()[-160:]))
        row("B2 exactly one new audit.<stamp> appeared and it holds the planted trail byte for byte", len(new) == 1 and sha(os.path.join(sysd, new[0])) == sum1 and
            os.path.getsize(os.path.join(sysd, new[0])) == size1, "new: %r" % new)
        st = os.stat(audit) if os.path.exists(audit) else None
        fresh = st is not None and st.st_size < 4096 and b"zzplant" not in open(audit, "rb").read()
        row("B3 a new audit file stands in its place: none of the planted trail in it (SD may write a line of its own), mode 0600, the same owner",
            fresh and (st.st_mode & 0o777) == 0o600 and st.st_uid == os.getuid(),
            "no file" if st is None else "size %d, mode %o, uid %d, planted lines in it: %s" % (st.st_size, st.st_mode & 0o777, st.st_uid, not fresh))
        sd_run(["-stop"], "free-stop")
    finally:
        sd_run(["-stop"], "final-stop")
        for p in made:
            if os.path.exists(p):
                os.remove(p)
        if orig is None:
            if os.path.exists(audit):
                os.remove(audit)
        else:
            with open(audit, "wb") as fh:
                fh.write(orig)
            os.chmod(audit, orig_mode)
        hk = held_keys(keys)
        if hk != (False, False):
            say("  note: the sandbox's keys are still held after sd-solo -stop %r; removing exactly the sandbox's own two" % (hk,))
            if hk[0]:
                subprocess.run(["ipcrm", "-M", "0x%08x" % keys[0]], capture_output=True)
            if hk[1]:
                subprocess.run(["ipcrm", "-S", "0x%08x" % keys[1]], capture_output=True)
        out = tool(box, "start", timeout=300)
        say("  the audit trail and the rotated names were put back as they were; the sandbox was handed back to the harness (start): " +
            ("keys held" if held_keys(keys) == (True, True) else "KEYS NOT HELD - " + out[-200:]))

    say("\n--- the Solo that runs on this computer was not touched -----------------------------------------------------")
    row("L CONTROL: its segment and semaphores are held exactly as before this suite ran (%r)" % (live_before,), held_keys(live_keys) == live_before,
        "before %r, after %r" % (live_before, held_keys(live_keys)))
    row("R the rotated names in the sandbox are the ones it had before the suite", rotated_names() == names_before, "now %r, before %r" % (rotated_names(), names_before))
    say("")
    say("sandbox-auditrot-solo: %d passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
