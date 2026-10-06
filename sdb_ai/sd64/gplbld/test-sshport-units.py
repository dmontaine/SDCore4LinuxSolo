#!/usr/bin/env python3
"""test-sshport-units.py - Solo's own ssh listener (LSOLO 29): gplbld/solo-ssh.sh,
gplbld/solo-service.sh's ssh units, the installer's upgrade-scope rule, and a REAL key
login through the sshd_config that solo-ssh.sh writes.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-sshport-units.py
  python3 .../test-sshport-units.py --selftest     each mutant must go red

No sudo, no install, no sd, and nothing of the user's is touched: every row works in a scratch
tree made under $HOME (sshd's StrictModes refuses a key file whose directories up to a home
directory are group-writable, and refuses anything under /tmp, so the scratch cannot live there).
Exit 0 every row passed, 1 a row failed, 2 it could not run.  Written 2 Oct 26 for LSOLO 29.

WHAT IT MEASURES.  Every row runs the REAL script and prints the command line and what came back.
  CONFIG rows  - setup writes a config sshd -t accepts, with the Linux password through PAM (keys
                 optional), StrictModes, a forced command and no forwarding; setup twice keeps the host key; the key file is
                 0600 in a 0700 directory; a group-writable tree is WARNED about by name.
  KEYS rows    - key-add/key-list/key-remove, the refusals, API request 49's add/list/remove
                 with its cap of four, the PORT answer and the NOSSH refusal.
  MIGRATE rows - both spellings of the old forced command move to the new file after a
                 backup; a plain key and ANOTHER tree's line stay; running it twice moves nothing.
  UNIT rows    - the two ssh units as solo-service.sh --print writes them (local and open).
  INSTALLER    - ssh_upgrade_scope, cut out of installsdsolo.sh by its marker lines, for each
                 evidence an upgrade can find; the new option refusals.
  LOGIN rows   - sshd -i, started per connection exactly as the systemd unit does it
                 (systemd-socket-activate --inetd), with a stand-in for sd-solo: a good key
                 reaches the forced command on a pty and a command of the client's own is NOT
                 run; a stranger's key and a password are refused; a forwarding request is
                 refused, and a CONTROL with that one line removed lets the same forward through
                 (so the refusal is not an instrument that cannot see a forward); StrictModes
                 refuses the key file at 0666 and accepts it again at 0600.

THE NULL CASE IS REFUSED.  Without sshd, ssh, ssh-keygen or systemd-socket-activate the run exits
2 rather than reporting rows that did nothing.  --selftest builds mutant copies of the tools
(password login off, PAM off, forwarding allowed, StrictModes off, the forced command gone, the
second spelling not migrated, the Solo key options dropped, the cap raised, a managed tree on an
old route not open, a managed tree with no ssh evidence forced open) and requires each to fail at
least one row.  A CORRECT password is not tried here: it needs the
owner's own, typed at ssh's prompt (probe-solo-ssh-password.sh).
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
INSTALLER = os.path.join(REPO, "installsdsolo.sh")
SSH_TOOL = "solo-ssh.sh"
SVC_TOOL = "solo-service.sh"
HOME = os.path.expanduser("~")
USER = os.environ.get("USER") or os.popen("id -un").read().strip()

RESULTS = {"pass": 0, "fail": 0}


def say(s=""):
    print(s)
    sys.stdout.flush()


def row(kind, name, ok, detail):
    RESULTS["pass" if ok else "fail"] += 1
    say("  [%s] %-8s %s" % ("PASS" if ok else "FAIL", kind, name))
    for line in detail:
        say("         | " + line)


def sh(args, env=None, stdin=None, timeout=60):
    e = dict(os.environ)
    if env:
        e.update(env)
    if args and args[0] == "ssh":
        timeout = min(timeout, 15)      # a login either answers at once or is waiting for a shell's input
    try:
        p = subprocess.run(args, capture_output=True, env=e, input=stdin, timeout=timeout)
    except subprocess.TimeoutExpired as t:
        # A hang is a result, not a crash: a mutant that gives the client a real shell waits for input.
        return 124, (t.stdout or b"").decode("utf-8", "replace"), "TIMEOUT after %ss: %s" % (timeout, " ".join(args[-3:]))
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def make_tree(base, name="tree"):
    tree = os.path.join(base, name)
    os.makedirs(os.path.join(tree, "bin"))
    standin = os.path.join(tree, "bin", "sd-solo")
    with open(standin, "w") as f:
        f.write('#!/bin/sh\necho "STANDIN-SD uid=$(id -u) tty=$(tty 2>&1) original=[$SSH_ORIGINAL_COMMAND]"\n')
    os.chmod(standin, 0o755)
    open(os.path.join(tree, ".sdcoresolo"), "w").close()
    os.chmod(tree, 0o700)
    return tree


def keygen(path, comment):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", path], check=True)
    return open(path + ".pub").read().strip()


def mode(path):
    return os.stat(path).st_mode & 0o777


def suite(tools, work):
    """tools: a directory holding solo-ssh.sh and solo-service.sh (the real ones, or a mutant's);
    installer: the file the scope function is cut from (a mutant's copy when given)."""
    ssh_tool = os.path.join(tools, SSH_TOOL)
    svc_tool = os.path.join(tools, SVC_TOOL)
    installer = os.path.join(tools, "installsdsolo.sh")
    tree = make_tree(work)
    d = os.path.join(tree, "sshd")
    keys = os.path.join(work, "keys")
    os.makedirs(keys)
    k = {n: keygen(os.path.join(keys, n), "key-" + n) for n in ("a", "b", "c", "d", "e", "stranger", "client")}

    # ------------------------------------------------------------- CONFIG
    cmd = ["bash", ssh_tool, "setup", tree]
    rc, out, err = sh(cmd)
    ready = re.search(r"^SOLO SSHD READY port=4251 hostfp=(SHA256:\S+) user=%s$" % re.escape(USER), out, re.M)
    conf_path = os.path.join(d, "sshd_config")
    conf = open(conf_path).read() if os.path.isfile(conf_path) else ""
    wanted = ["PasswordAuthentication yes", "KbdInteractiveAuthentication no", "UsePAM yes", "PubkeyAuthentication yes",
              "StrictModes yes", "AllowUsers " + USER, "DisableForwarding yes", "PermitTTY yes",
              "ForceCommand " + os.path.join(tree, "bin", "sd-solo"), "HostKey " + os.path.join(d, "ssh_host_ed25519_key"),
              "AuthorizedKeysFile " + os.path.join(d, "authorized_keys")]
    missing = [w for w in wanted if w not in conf.splitlines()]
    rc2, out2, err2 = sh(["/usr/sbin/sshd", "-t", "-f", conf_path])
    row("CONFIG", "setup writes the config and says READY with the host key's fingerprint",
        rc == 0 and ready is not None and not missing and rc2 == 0,
        ["$ " + " ".join(cmd), "  -> exit %d; last line: %s" % (rc, out.strip().splitlines()[-1:] or err.strip()[:120]),
         "  config lines missing: %s" % (missing or "none"), "  $ sshd -t -f <config> -> exit %d %s" % (rc2, err2.strip()[:100])])
    modes = {"dir": mode(d), "config": mode(conf_path), "hostkey": mode(os.path.join(d, "ssh_host_ed25519_key")),
             "keyfile": mode(os.path.join(d, "authorized_keys"))}
    row("CONFIG", "the sshd directory is 0700 and the config, host key and key file are 0600",
        modes == {"dir": 0o700, "config": 0o600, "hostkey": 0o600, "keyfile": 0o600},
        ["  modes: %s" % {n: oct(m) for n, m in modes.items()}])
    fp1 = ready.group(1) if ready else None
    rc, out, err = sh(cmd)
    ready2 = re.search(r"hostfp=(SHA256:\S+)", out)
    row("CONFIG", "setup run again keeps the host key (same fingerprint) and rewrites the config",
        rc == 0 and ready2 is not None and ready2.group(1) == fp1 and open(conf_path).read() == conf,
        ["  fingerprint before %s after %s" % (fp1, ready2.group(1) if ready2 else None)])
    os.chmod(tree, 0o777)
    rc, out, err = sh(cmd)
    warned = "StrictModes will REFUSE" in err and tree in err
    os.chmod(tree, 0o775)
    rc2, out2, err2 = sh(cmd)
    os.chmod(tree, 0o700)
    rc3, out3, err3 = sh(cmd)
    row("CONFIG", "a world-writable tree is WARNED about by name; 0775 (accepted by sshd, measured) and 0700 are not",
        warned and "StrictModes will REFUSE" not in err2 and "StrictModes will REFUSE" not in err3,
        ["  at 0777: %s" % err.strip().replace("\n", " | ")[:200], "  at 0775: %r" % err2.strip()[:80], "  at 0700: %r" % err3.strip()[:80]])
    rc, out, err = sh(cmd, env={"SDSOLO_TEST_SSH_PORT": "24123"})
    rc4, out4, err4 = sh(cmd, env={"SDSOLO_TEST_SSH_PORT": "80"})
    row("CONFIG", "the test hook moves the port in the answer, is announced, and refuses 80",
        "port=24123" in out and "IS SET" in err and rc4 == 2 and "1024-65535" in err4,
        ["  hook 24123 -> %s ; %s" % (out.strip().splitlines()[-1][:60], err.strip()[:60]), "  hook 80 -> exit %d %s" % (rc4, err4.strip()[:70])])

    # ----------------------------------------------------------------- KEYS
    pubfile = os.path.join(keys, "a.pub")
    ak = os.path.join(d, "authorized_keys")
    rc, out, err = sh(["bash", ssh_tool, "key-add", tree, pubfile])
    lines = open(ak).read().splitlines()
    rc2, out2, err2 = sh(["bash", ssh_tool, "key-add", tree, pubfile])
    lines2 = open(ak).read().splitlines()
    rc3, out3, err3 = sh(["bash", ssh_tool, "key-list", tree])
    row("KEYS", "key-add writes 'restrict,pty <key>', twice makes one line, key-list counts it",
        rc == 0 and lines == ["restrict,pty " + k["a"]] and lines2 == lines and "SOLO SSH KEYS 1" in out3,
        ["  file after add: %s" % [l[:40] for l in lines], "  after the second add: %d line(s)" % len(lines2), "  key-list: %s" % out3.strip().splitlines()[-1]])
    rc, out, err = sh(["bash", ssh_tool, "key-remove", tree, pubfile])
    rc2, out2, err2 = sh(["bash", ssh_tool, "key-list", tree])
    row("KEYS", "key-remove takes that line out",
        rc == 0 and "SOLO SSH KEY REMOVED 1" in out and "SOLO SSH KEYS 0" in out2,
        ["  -> %s ; %s" % (out.strip().splitlines()[-1], out2.strip().splitlines()[-1])])
    bad = os.path.join(keys, "notakey.pub")
    open(bad, "w").write("hello world\n")
    quoted = os.path.join(keys, "quoted.pub")
    open(quoted, "w").write('ssh-ed25519 AAAA"evil comment\n')
    multi = os.path.join(keys, "multi.pub")
    open(multi, "w").write(k["a"] + "\n" + k["b"] + "\n")
    refusals = []
    for label, f, want in (("not a key", bad, "does not look like an ssh public key"), ("a quote", quoted, "quote or backslash"),
                           ("two lines", multi, "more than one line")):
        rcx, outx, errx = sh(["bash", ssh_tool, "key-add", tree, f])
        refusals.append((label, rcx == 2 and want in errx, errx.strip()[:70]))
    row("KEYS", "key-add refuses a file that is not a key, a key with a quote, and two lines",
        all(r[1] for r in refusals) and open(ak).read() == "", ["  %s: %s" % (r[0], r[2]) for r in refusals])

    # API request 49: the hook names a scratch key file
    api_ak = os.path.join(work, "api_keys")
    env = {"SDSOLO_AUTHORIZED_KEYS": api_ak}
    res = []
    for n in ("a", "b", "c", "d", "e"):
        rcx, outx, errx = sh(["bash", ssh_tool, "api-add", tree, os.path.join(keys, n + ".pub")], env=env)
        res.append(outx)
    first = dict(l.split("=", 1) for l in res[0].splitlines() if "=" in l)
    cap = "ERROR=CAP" in res[4]
    row("KEYS", "API add answers USER, HOST, FP, HOSTFP (Solo's own), PORT=4251 and RESULT=ADDED, and the fifth key hits the cap of four",
        first.get("RESULT") == "ADDED" and first.get("PORT") == "4251" and first.get("USER") == USER
        and first.get("HOSTFP") == fp1 and first.get("FP", "").startswith("SHA256:") and cap,
        ["  first answer: %s" % {kk: v[:30] for kk, v in first.items()}, "  fifth: %s" % res[4].strip().splitlines()[-1]])
    fp_a = first.get("FP", "")
    fpf = os.path.join(work, "fp.txt")
    open(fpf, "w").write(fp_a + "\n")
    rcl, outl, errl = sh(["bash", ssh_tool, "api-list", tree], env=env)
    rcr, outr, errr = sh(["bash", ssh_tool, "api-remove", tree, fpf], env=env)
    rcr2, outr2, errr2 = sh(["bash", ssh_tool, "api-remove", tree, fpf], env=env)
    row("KEYS", "API list shows four fingerprints; remove answers REMOVED with 3 left, then ABSENT",
        outl.count("FP=") == 4 and "RESULT=REMOVED" in outr and "REMAINING=3" in outr and "RESULT=ABSENT" in outr2,
        ["  list: %d FP lines" % outl.count("FP="), "  remove: %s" % " ".join(outr.split()[-2:]), "  again: %s" % " ".join(outr2.split()[-2:])])
    hk = os.path.join(d, "ssh_host_ed25519_key.pub")
    os.rename(hk, hk + ".gone")
    rcn, outn, errn = sh(["bash", ssh_tool, "api-add", tree, os.path.join(keys, "e.pub")], env=env)
    os.rename(hk + ".gone", hk)
    row("KEYS", "API add with no ssh set up says ERROR=NOSSH and writes nothing", "ERROR=NOSSH" in outn,
        ["  -> %s" % outn.strip()])

    # -------------------------------------------------------------- MIGRATE
    old = os.path.join(work, "old_authorized_keys")
    new = os.path.join(work, "new_keys")
    other = '/other/tree/bin/sd-solo'
    old_lines = [k["a"], 'command="%s/bin/sd-solo",restrict,pty %s' % (tree, k["b"]),
                 'command="%s/bin/sd",restrict,pty %s' % (tree, k["c"]),
                 'command="%s",restrict,pty %s' % (other, k["d"])]
    open(old, "w").write("\n".join(old_lines) + "\n")
    os.chmod(old, 0o600)
    cmd = ["bash", ssh_tool, "migrate", tree, "--old-authorized-keys", old, "--authorized-keys", new]
    rc, out, err = sh(cmd)
    after_old = open(old).read().splitlines()
    after_new = open(new).read().splitlines() if os.path.exists(new) else []
    baks = [f for f in os.listdir(work) if f.startswith("old_authorized_keys.sdsolo-backup-")]
    bak_ok = bool(baks) and open(os.path.join(work, baks[0])).read().splitlines() == old_lines
    row("MIGRATE", "both spellings move to the new file after a backup; a plain key and another tree's line stay",
        rc == 0 and "SOLO SSH MIGRATED 2" in out and after_new == ["restrict,pty " + k["b"], "restrict,pty " + k["c"]]
        and after_old == [old_lines[0], old_lines[3]] and bak_ok and mode(old) == 0o600,
        ["$ " + " ".join(cmd[1:]), "  -> %s" % out.strip().splitlines()[-1], "  old file now: %d lines, new file: %d, backup identical to the original: %s" % (len(after_old), len(after_new), bak_ok)])
    rc, out, err = sh(cmd)
    row("MIGRATE", "running it again moves nothing and makes no second backup",
        "SOLO SSH MIGRATED 0" in out and len([f for f in os.listdir(work) if f.startswith("old_authorized_keys.sdsolo-backup-")]) == 1,
        ["  -> %s" % out.strip().splitlines()[-1]])

    # ----------------------------------------------------------------- UNITS
    rc, out, err = sh(["bash", svc_tool, "ssh", tree, "local", "--print"])
    rco, outo, erro = sh(["bash", svc_tool, "ssh", tree, "open", "--print"])
    # LSOLO 29: the unit starts the lockout guard (solo-sshguard.py), which runs "sshd -i -e -f <tree>/sshd/sshd_config"
    tmpl = "ExecStart=%s %s/tools/solo-sshguard.py %s %s" % (shutil.which("python3") or "/usr/bin/python3", tree, tree,
                                                             shutil.which("sshd") or "/usr/sbin/sshd")
    rch, outh, errh = sh(["bash", svc_tool, "ssh", tree, "local", "--print"], env={"SDSOLO_TEST_SSH_PORT": "24555"})
    row("UNITS", "local listens on 127.0.0.1:4251, open on 0.0.0.0:4251, one sshd -i per connection on the tree's own config",
        rc == 0 and "ListenStream=127.0.0.1:4251" in out and "ListenStream=0.0.0.0:4251" in outo and "Accept=true" in out
        and tmpl in out and "StandardInput=socket" in out and "Requires=sd-solo.service" in out and "ListenStream=127.0.0.1:24555" in outh,
        ["  local: %s" % [l for l in out.splitlines() if l.startswith(("ListenStream", "ExecStart", "StandardInput", "Requires"))],
         "  open : %s" % [l for l in outo.splitlines() if l.startswith("ListenStream")], "  hook : %s" % [l for l in outh.splitlines() if l.startswith("ListenStream")]])
    rcb, outb, errb = sh(["bash", svc_tool, "ssh", tree, "sideways", "--print"])
    rcm, outm, errm = sh(["bash", svc_tool, "ssh", os.path.join(work, "nope"), "local", "--print"])
    rco2, outo2, erro2 = sh(["bash", svc_tool, "ssh", tree, "off", "--print"])
    row("UNITS", "a bad mode and a missing tree are refused; off prints no units",
        rcb == 2 and "off, local or open" in errb and rcm == 2 and "not there" in errm and rco2 == 0 and "ssh off" in outo2,
        ["  sideways -> %d %s" % (rcb, errb.strip()[:60]), "  no tree  -> %d %s" % (rcm, errm.strip()[:60]), "  off -> %s" % outo2.strip()[:40]])

    # The unit names are ONE PAIR PER USER, not per tree.  Found 2 Oct 2026: a test of "solo-service.sh ssh
    # <scratch tree> off" on the owner's own user manager removed his live listener.  The script now refuses
    # to replace or remove a pair that names another tree.  THE TEST USES A SCRATCH XDG_CONFIG_HOME, only
    # the REFUSAL is exercised (it happens before any systemctl), and THERE MUST BE NO MUTANT OF THIS GUARD:
    # without it the script would run systemctl against the user's REAL manager.
    xdg = os.path.join(work, "xdg")
    udir = os.path.join(xdg, "systemd", "user")
    os.makedirs(udir)
    other_tree = "/home/someone/other-tree"
    open(os.path.join(udir, "sd-solo-ssh@.service"), "w").write(
        "[Service]\nExecStart=/usr/sbin/sshd -i -e -f %s/sshd/sshd_config\n" % other_tree)
    open(os.path.join(udir, "sd-solo-ssh.socket"), "w").write("[Socket]\nListenStream=127.0.0.1:4251\n")
    snap = {n: open(os.path.join(udir, n)).read() for n in os.listdir(udir)}
    rcg, outg, errg = sh(["bash", svc_tool, "ssh", tree, "off"], env={"XDG_CONFIG_HOME": xdg})
    unchanged = {n: open(os.path.join(udir, n)).read() for n in os.listdir(udir)} == snap
    row("UNITS", "ssh for one tree REFUSES to replace or remove the ssh units that name another tree (one pair per user)",
        rcg == 2 and "belong to another Solo tree" in errg and other_tree in errg and unchanged,
        ["$ XDG_CONFIG_HOME=<scratch> solo-service.sh ssh <this tree> off", "  -> exit %d %r" % (rcg, errg.strip()[:150]),
         "  the other tree's two unit files unchanged: %s" % unchanged])

    # ------------------------------------------------------------- INSTALLER
    src = open(installer).read()
    m = re.search(r"^# BEGIN upgrade_ssh\n(.*?)^# END upgrade_ssh\n", src, re.M | re.S)
    if not m:
        row("INSTALL", "the marker lines for ssh_upgrade_scope are in the installer", False, ["  no BEGIN/END upgrade_ssh markers in " + installer])
    else:
        func = m.group(1)
        scen = os.path.join(work, "scope")
        os.makedirs(scen)
        unit = os.path.join(scen, "units")
        os.makedirs(unit)
        akf = os.path.join(scen, "ak")
        drop = os.path.join(scen, "dropin.conf")
        sock = os.path.join(unit, "sd-solo-ssh.socket")
        bare = os.path.join(scen, "bare-tree")      # a tree with no sshd directory of its own
        os.makedirs(bare)

        def scope(mode_name="unmanaged", ak_text=None, dropin=False, socket_text=None, home=None):
            for p in (akf, drop, sock):
                if os.path.exists(p):
                    os.remove(p)
            if ak_text is not None:
                open(akf, "w").write(ak_text)
            if dropin:
                open(drop, "w").write("x\n")
            if socket_text is not None:
                open(sock, "w").write(socket_text)
            script = func + '\nssh_upgrade_scope "%s" "%s" "%s" "%s" "%s"\n' % (home or bare, unit, mode_name, akf, drop)
            rcs, outs, errs = sh(["bash", "-c", script])
            return outs.strip() if rcs == 0 else "rc=%d %s" % (rcs, errs.strip()[:60])
        got = {
            "socket 0.0.0.0 kept": scope(socket_text="[Socket]\nListenStream=0.0.0.0:4251\n"),
            "socket 127.0.0.1 kept": scope(socket_text="[Socket]\nListenStream=127.0.0.1:4251\n"),
            # LSOLO 38 (6 Oct 2026): managed is no longer open by rule, so a managed tree with no evidence of ssh is off;
            # only a managed tree on an OLD route (before the socket) keeps what that meant, which was open.
            "managed, no evidence": scope(mode_name="managed"),
            "managed, old drop-in": scope(mode_name="managed", dropin=True),
            "managed, old key line": scope(mode_name="managed", ak_text='command="%s/bin/sd-solo",restrict,pty ssh-ed25519 AAAA x\n' % bare),
            "managed, socket 127.0.0.1 kept": scope(mode_name="managed", socket_text="[Socket]\nListenStream=127.0.0.1:4251\n"),
            "old drop-in": scope(dropin=True),
            "old key line, sd-solo": scope(ak_text='command="%s/bin/sd-solo",restrict,pty ssh-ed25519 AAAA x\n' % bare),
            "old key line, sd": scope(ak_text='command="%s/bin/sd",restrict,pty ssh-ed25519 AAAA x\n' % bare),
            "another tree's line only": scope(ak_text='command="/other/bin/sd-solo",restrict,pty ssh-ed25519 AAAA x\nssh-ed25519 BBBB y\n'),
            # found 2 Oct 2026: the socket unit was gone (removed by a test) and nothing else was left as evidence
            "sshd directory present, no unit": scope(home=tree),
            "nothing": scope(),
        }
        want = {"socket 0.0.0.0 kept": "open", "socket 127.0.0.1 kept": "local",
                "managed, no evidence": "off", "managed, old drop-in": "open", "managed, old key line": "open",
                "managed, socket 127.0.0.1 kept": "local", "old drop-in": "local",
                "old key line, sd-solo": "local", "old key line, sd": "local", "another tree's line only": "off",
                "sshd directory present, no unit": "local", "nothing": "off"}
        row("INSTALL", "ssh_upgrade_scope: a new socket keeps its address, an sshd directory or either old route is local (open for a managed tree on an old route), otherwise off",
            got == want, ["  %s -> %s" % (n, got[n]) for n in want] + ["  expected: %s" % want])
    # 2 Oct 2026 (owner: "match the windows solo behavior"): as Windows Solo's installer ticks "Install the OpenSSH
    # server" by default, the DEFAULT is local and installs the ssh server package if it is missing; --ssh off declines;
    # the one Linux difference is --skip-packages, where a missing sshd makes the default off (not a failed install).
    md = re.search(r"^# BEGIN ssh_default\n(.*?)^# END ssh_default\n", src, re.M | re.S)
    if not md:
        row("INSTALL", "the marker lines for ssh_default_choice are in the installer", False, ["  no BEGIN/END ssh_default markers in " + installer])
    else:
        dfunc = md.group(1)

        def dflt(given, key, have, skip):
            rcd, outd, errd = sh(["bash", "-c", dfunc + '\nssh_default_choice "%s" "%s" "%s" "%s"\n' % (given, key, have, skip)])
            return outd.strip() if rcd == 0 else "rc=%d %s" % (rcd, errd.strip()[:60])
        dgot = {
            "nothing asked, sshd here": dflt("", "", 1, 0),
            "nothing asked, NO sshd (the package gets installed)": dflt("", "", 0, 0),
            "nothing asked, NO sshd, --skip-packages": dflt("", "", 0, 1),
            "nothing asked, sshd here, --skip-packages": dflt("", "", 1, 1),
            "--ssh open, NO sshd": dflt("open", "", 0, 0),
            "--ssh off, NO sshd": dflt("off", "", 0, 0),
            "--ssh off, sshd here": dflt("off", "", 1, 0),
            "a key given, NO sshd": dflt("", "/k.pub", 0, 0),
            # a key is asking for ssh: it is not turned off by --skip-packages (the installer refuses that combination itself)
            "a key given, NO sshd, --skip-packages": dflt("", "/k.pub", 0, 1),
        }
        dwant = {"nothing asked, sshd here": "local", "nothing asked, NO sshd (the package gets installed)": "local",
                 "nothing asked, NO sshd, --skip-packages": "off", "nothing asked, sshd here, --skip-packages": "local",
                 "--ssh open, NO sshd": "open", "--ssh off, NO sshd": "off", "--ssh off, sshd here": "off", "a key given, NO sshd": "local",
                 "a key given, NO sshd, --skip-packages": "local"}
        row("INSTALL", "ssh_default_choice: nothing asked is local (the ssh server package is installed if missing); --skip-packages with no sshd makes it off; --ssh wins",
            dgot == dwant, ["  %s -> %s" % (n, dgot[n]) for n in dwant] + ["  expected: %s" % dwant])
    refs = []
    # --upgrade is checked against a tree that exists, so the refusal under test is the one that comes back.
    open(os.path.join(tree, ".sdcore-install"), "w").write("commit x\nmode unmanaged\n")
    for label, args, want in (("--ssh-match", ["--ssh-match"], "--ssh-match is gone"), ("--ssh sideways", ["--ssh", "sideways"], "off, local or open"),
                              ("--ssh off --ssh-key", ["--ssh", "off", "--ssh-key", "/x"], "needs ssh on"),
                              ("--upgrade --ssh local", ["--upgrade", "--home", tree, "--ssh", "local"], "takes no password")):
        rcx, outx, errx = sh(["bash", installer] + args)
        refs.append((label, rcx == 2 and want in errx, errx.strip()[-70:]))
    row("INSTALL", "the installer refuses --ssh-match, a bad --ssh, --ssh off with a key, and --upgrade with --ssh",
        all(r[1] for r in refs), ["  %s: %s" % (r[0], r[2]) for r in refs])

    # ----------------------------------------------------------------- LOGIN
    login_suite(tools, work, tree, keys, k, ssh_tool)


def start_listener(conf, port):
    p = subprocess.Popen(["systemd-socket-activate", "--accept", "--inetd", "-l", "127.0.0.1:%d" % port, "--",
                          "/usr/sbin/sshd", "-i", "-e", "-f", conf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return p
        except OSError:
            time.sleep(0.1)
    return p


def stop_listener(p):
    p.terminate()
    try:
        _, err = p.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
        _, err = p.communicate()
    return (err or b"").decode("utf-8", "replace")


def ssh_cmd(port, key, extra=(), tty=False, loglevel="ERROR"):
    return (["ssh"] + (["-tt"] if tty else []) +
            ["-i", key, "-p", str(port), "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=no",
             "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes", "-o", "LogLevel=" + loglevel] + list(extra))


def wrong_password_login(port, offer_keys=()):
    """Type a deliberately WRONG password at ssh's own prompt, through a pty; return what ssh printed.
    offer_keys: private key files the client offers FIRST (none of them is in the server's key file), the way an
    ssh agent holding several keys does; without them the client goes straight to the password."""
    import pty
    import select
    if offer_keys:
        auth = ["-o", "IdentitiesOnly=yes"] + [a for k in offer_keys for a in ("-i", k)]
    else:
        auth = ["-o", "PreferredAuthentications=password", "-o", "PubkeyAuthentication=no"]
    cmd = ["ssh", "-p", str(port), "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"] + auth + [
           "-o", "NumberOfPasswordPrompts=1", "-o", "LogLevel=ERROR", USER + "@127.0.0.1"]
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
                time.sleep(0.5)
                os.write(fd, b"this-is-a-deliberately-wrong-password\r")
                sent = True
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    return out.decode("utf-8", "replace").replace("\r", "")


def pam_refusal_lines():
    """The journal's record that PAM's own check refused the wrong password, or '' when it cannot be read."""
    if not shutil.which("journalctl"):
        return ""
    p = subprocess.run(["journalctl", "--since", "-1min", "--no-pager"], capture_output=True)
    lines = [l for l in p.stdout.decode("utf-8", "replace").splitlines() if "unix_chkpwd" in l and "password check failed" in l]
    return lines[-1][16:130] if lines else ""


def login_suite(tools, work, tree, keys, k, ssh_tool):
    d = os.path.join(tree, "sshd")
    ak = os.path.join(d, "authorized_keys")
    conf = os.path.join(d, "sshd_config")
    client, stranger = os.path.join(keys, "client"), os.path.join(keys, "stranger")
    open(ak, "w").write("restrict,pty " + k["client"] + "\n")
    os.chmod(ak, 0o600)
    port = free_port()
    p = start_listener(conf, port)
    try:
        cmd = ssh_cmd(port, client, ["127.0.0.1"], tty=True)
        rc, out, err = sh(cmd, timeout=30)
        row("LOGIN", "a good key on a pty reaches the forced command (the stand-in for sd-solo) as this user",
            rc == 0 and "STANDIN-SD uid=%d" % os.getuid() in out and "tty=/dev/pts/" in out and "original=[]" in out,
            ["$ " + " ".join(cmd), "  -> exit %d, output %r" % (rc, out.strip()[:100] or err.strip()[:100])])
        marker = os.path.join(work, "SHOULD-NOT-EXIST")
        cmd = ssh_cmd(port, client, ["127.0.0.1", "touch " + marker], tty=True)
        rc, out, err = sh(cmd, timeout=30)
        row("LOGIN", "a command of the client's own is NOT run: the forced command still answers, with the request in SSH_ORIGINAL_COMMAND",
            not os.path.exists(marker) and "STANDIN-SD" in out and ("original=[touch " + marker) in out,
            ["$ " + " ".join(cmd[-3:]), "  -> %r ; marker file made: %s" % (out.strip()[:120], os.path.exists(marker))])
        cmd = ssh_cmd(port, stranger, ["127.0.0.1"])
        rc, out, err = sh(cmd, timeout=30)
        row("LOGIN", "a key that is not in the key file is refused",
            rc == 255 and "Permission denied" in err and "STANDIN-SD" not in out,
            ["  -> exit %d %r" % (rc, err.strip()[:80])])
        # LSOLO 29, owner 2 Oct 2026: the sign-in is the Linux account name and PASSWORD.  The password is
        # checked by PAM's own helper even though sshd is not root.  A WRONG one is typed by a pty harness
        # (the test never handles a real password): ssh must be OFFERED a password prompt and be refused.
        # A CORRECT password cannot be tried here; probe-solo-ssh-password.sh has the owner type his.
        out_pw = wrong_password_login(port)
        pam_evidence = pam_refusal_lines()
        row("LOGIN", "a password is asked for, and a WRONG one is refused (PAM's check, no key involved)",
            "assword:" in out_pw and "Permission denied" in out_pw and "STANDIN-SD" not in out_pw,
            ["  -> %r" % out_pw.strip().replace("\n", " | ")[:140],
             "  journal evidence that PAM's own check refused it: %s" % (pam_evidence or "none readable here (the row does not need it)")])
        # MaxAuthTries (measured 2 Oct 2026): every key offered that the server does not know counts as a failure, so a
        # client whose ssh agent holds several keys was cut off "Too many authentication failures" BEFORE the password
        # prompt when the limit was 3.  Four unknown keys must still reach the prompt.
        many = [os.path.join(keys, n) for n in ("a", "b", "c", "d")]
        out_many = wrong_password_login(port, offer_keys=many)
        row("LOGIN", "a client offering FOUR keys the server does not know still reaches the password prompt (MaxAuthTries)",
            "assword:" in out_many and "Too many authentication failures" not in out_many,
            ["  -> %r" % out_many.strip().replace("\n", " | ")[:140]])
        # StrictModes: the key file at 0666 must refuse the GOOD key; back at 0600 it is accepted.
        os.chmod(ak, 0o666)
        rc, out, err = sh(ssh_cmd(port, client, ["127.0.0.1"]), timeout=30)
        os.chmod(ak, 0o600)
        rc2, out2, err2 = sh(ssh_cmd(port, client, ["127.0.0.1"]), timeout=30)
        row("LOGIN", "StrictModes: the good key is refused with the key file at 0666 and accepted again at 0600",
            rc == 255 and "STANDIN-SD" not in out and rc2 == 0 and "STANDIN-SD" in out2,
            ["  at 0666: exit %d %r ; at 0600: exit %d %r" % (rc, err.strip()[:50], rc2, out2.strip()[:40])])
    finally:
        stop_listener(p)
    # Forwarding.  TWO things refuse a forward: DisableForwarding in the config and the 'restrict'
    # option of the key line (measured 2 Oct 26: with the config line removed the forward was
    # STILL refused, "refused local port forward").  Each is measured ALONE, the other taken
    # away, and a CONTROL with both taken away shows the same probe can see a forward go through.
    pty_ak = os.path.join(d, "authorized_keys_pty_only")
    open(pty_ak, "w").write("pty " + k["client"] + "\n")
    os.chmod(pty_ak, 0o600)

    def variant(name, drop_forwarding, ak_path):
        text = open(conf).read().replace("AuthorizedKeysFile " + ak, "AuthorizedKeysFile " + ak_path)
        if drop_forwarding:
            text = text.replace("DisableForwarding yes\n", "")
        path = os.path.join(d, "sshd_config_" + name)
        open(path, "w").write(text)
        os.chmod(path, 0o600)
        return path

    def probe(conf_path):
        port2 = free_port()
        p2 = start_listener(conf_path, port2)
        try:
            fwd = free_port()
            fcmd = ssh_cmd(port2, client, ["-N", "-L", "%d:127.0.0.1:%d" % (fwd, port2), "127.0.0.1"], loglevel="INFO")
            fp = subprocess.Popen(fcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            banner = b""
            for _ in range(60):
                try:
                    c = socket.create_connection(("127.0.0.1", fwd), 1)
                    c.settimeout(3)
                    try:
                        banner = c.recv(64)
                    except OSError:
                        banner = b""
                    c.close()
                    break
                except OSError:
                    time.sleep(0.1)
            time.sleep(0.5)
            fp.terminate()
            ferr = fp.communicate(timeout=5)[1].decode("utf-8", "replace")
            return banner, ferr, fcmd
        finally:
            stop_listener(p2)
    for label, conf_path, want_through in (
            ("as written (config and key line both refuse)", conf, False),
            ("the config alone refuses (key line without 'restrict')", variant("cfg", False, pty_ak), False),
            ("the key line's 'restrict' alone refuses (config without DisableForwarding)", variant("key", True, ak), False),
            ("CONTROL, neither refuses: the same forward carries the sshd banner through", variant("ctl", True, pty_ak), True)):
        banner, ferr, fcmd = probe(conf_path)
        through = b"SSH-2.0" in banner
        ok = through if want_through else (not through and ("administratively prohibited" in ferr or "refused" in ferr))
        row("LOGIN", "forwarding, " + label, ok,
            ["$ " + " ".join(fcmd[-6:]), "  -> through the forward: %r ; ssh said: %r" % (banner[:24], ferr.strip().splitlines()[-1][:90] if ferr.strip() else "")])


MUTANTS = [
    ("password login off (key-only again)", SSH_TOOL, "PasswordAuthentication yes\nKbd", "PasswordAuthentication no\nKbd"),
    ("PAM off", SSH_TOOL, "UsePAM yes\nPubkey", "UsePAM no\nPubkey"),
    ("MaxAuthTries back to 3", SSH_TOOL, "MaxAuthTries 6\nLoginGraceTime", "MaxAuthTries 3\nLoginGraceTime"),
    ("forwarding allowed", SSH_TOOL, "DisableForwarding yes", "DisableForwarding no"),
    ("StrictModes off", SSH_TOOL, "StrictModes yes", "StrictModes no"),
    ("forced command gone", SSH_TOOL, "ForceCommand $H/bin/sd-solo", "#ForceCommand $H/bin/sd-solo"),
    ("Solo key options dropped", SSH_TOOL, 'KEYOPTS="restrict,pty"', 'KEYOPTS="pty"'),
    ("cap raised", SSH_TOOL, "MAXKEYS=4", "MAXKEYS=400"),
    ("second spelling not migrated", SSH_TOOL, 'forms=("$FORCED_NEW" "$FORCED_OLD")', 'forms=("$FORCED_NEW")'),
    ("sshd directory not counted as evidence", "installsdsolo.sh", 'if [ -f "$home_dir/sshd/sshd_config" ]; then echo local; return 0; fi',
     'if false; then echo local; return 0; fi'),
    ("managed tree on an old drop-in not open", "installsdsolo.sh",
     'if [ -f "$dropin" ]; then if [ "$mode_name" = "managed" ]; then echo open; else echo local; fi; return 0; fi',
     'if [ -f "$dropin" ]; then echo local; return 0; fi'),
    ("managed tree on an old key line not open", "installsdsolo.sh",
     '    if [ "$mode_name" = "managed" ]; then echo open; else echo local; fi; return 0\n  fi',
     '    echo local; return 0\n  fi'),
    ("a managed tree with no ssh evidence forced open (the old rule)", "installsdsolo.sh",
     "  # Solo's own ssh directory is evidence ssh was in use even if its socket unit is gone",
     '  if [ "$mode_name" = "managed" ]; then echo open; return 0; fi\n  # Solo\'s own ssh directory is evidence ssh was in use even if its socket unit is gone'),
    ("default off where sshd is absent (the first, rejected, version)", "installsdsolo.sh",
     'if [ "$have" != "1" ] && [ "$skip" = "1" ]; then echo off; else echo local; fi', 'if [ "$have" != "1" ]; then echo off; else echo local; fi'),
    ("--skip-packages with no sshd not honoured", "installsdsolo.sh",
     'if [ "$have" != "1" ] && [ "$skip" = "1" ]; then echo off; else echo local; fi', 'echo local'),
    ("a key does not turn ssh on", "installsdsolo.sh", 'if [ -n "$key" ]; then echo local; return 0; fi', 'if false; then echo local; return 0; fi'),
    ("an explicit --ssh is overridden", "installsdsolo.sh", 'if [ -n "$given" ]; then echo "$given"; return 0; fi', 'if false; then echo "$given"; return 0; fi'),
    ("open listens locally", SVC_TOOL, 'if [ "$1" = "open" ]; then listen="0.0.0.0:$2"; else listen="127.0.0.1:$2"; fi',
     'listen="127.0.0.1:$2"'),
]


def main():
    selftest = "--selftest" in sys.argv[1:]
    say("test-sshport-units: %s" % HERE)
    need = ["ssh", "ssh-keygen", "systemd-socket-activate", "bash"]
    missing = [t for t in need if not shutil.which(t)] + ([] if os.path.exists("/usr/sbin/sshd") else ["/usr/sbin/sshd"])
    if missing:
        say("CANNOT RUN - missing: %s" % ", ".join(missing))
        return 2
    for f in (os.path.join(HERE, SSH_TOOL), os.path.join(HERE, SVC_TOOL), INSTALLER):
        if not os.path.isfile(f):
            say("CANNOT RUN - the tool is missing: " + f)
            return 2
    base = tempfile.mkdtemp(prefix=".zz-sshport-", dir=HOME)
    os.chmod(base, 0o700)
    try:
        real_tools = os.path.join(base, "real-tools")
        os.makedirs(real_tools)
        for f in (SSH_TOOL, SVC_TOOL):
            shutil.copy(os.path.join(HERE, f), os.path.join(real_tools, f))
        shutil.copy(INSTALLER, os.path.join(real_tools, "installsdsolo.sh"))
        work = os.path.join(base, "real")
        os.makedirs(work)
        say("  scratch: %s\n" % base)
        suite(real_tools, work)
        if RESULTS["pass"] + RESULTS["fail"] == 0:
            say("\nREFUSED: the null case - no rows ran")
            return 2
        say("\n%(pass)d passed, %(fail)d failed" % RESULTS)
        if RESULTS["fail"]:
            return 1
        if not selftest:
            return 0
        red = 0
        for label, fname, old, new in MUTANTS:
            src = open(os.path.join(real_tools, fname)).read()
            if src.count(old) != 1:
                say("CANNOT RUN - mutant '%s': expected one match of its target in %s, found %d" % (label, fname, src.count(old)))
                return 2
            mt = os.path.join(base, "m-" + re.sub(r"[^a-z0-9]+", "-", label))
            os.makedirs(mt)
            for f in (SSH_TOOL, SVC_TOOL, "installsdsolo.sh"):
                shutil.copy(os.path.join(real_tools, f), os.path.join(mt, f))
            open(os.path.join(mt, fname), "w").write(src.replace(old, new))
            for kk in RESULTS:
                RESULTS[kk] = 0
            mw = os.path.join(mt, "work")
            os.makedirs(mw)
            say("\n--- mutant: %s" % label)
            suite(mt, mw)
            went_red = RESULTS["fail"] > 0
            red += went_red
            say("--- mutant '%s': %s (%d rows failed)" % (label, "RED as it must be" if went_red else "STILL GREEN - the test misses it", RESULTS["fail"]))
        say("\nselftest: %d of %d mutants went red" % (red, len(MUTANTS)))
        return 0 if red == len(MUTANTS) else 1
    finally:
        for root, dirs, files in os.walk(base):
            for n in dirs:
                try:
                    os.chmod(os.path.join(root, n), 0o700)
                except OSError:
                    pass
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
