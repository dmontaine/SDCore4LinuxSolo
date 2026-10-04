#!/usr/bin/env python3
# test-sshpam-units.py - Solo's own PAM service under SELinux (LSOLO 31, 3 Oct 2026)
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-sshpam-units.py [--selftest]
#
# On Fedora 44 (SELinux enforcing) Solo's sshd, which is not root, failed the session step of
# /etc/pam.d/sshd ("session required pam_selinux.so open") after the password was accepted.
# solo-ssh.sh "pam --install" builds /etc/pam.d/sd-solo-ssh-<user> from that file without the
# session modules that need root.  This cuts pam_stack out of solo-ssh.sh by its marker lines,
# runs it on Fedora 44's real stack (read from the VM, 3 Oct 2026, below) and checks:
#   1. the function was found (a test of nothing must fail);
#   2. no live pam_selinux, pam_loginuid or pam_namespace line is left;
#   3. every other live line is kept, in order (auth and account above all);
#   4. one "#%PAM-1.0" header, and the marker line deletesdsolo.sh looks for;
#   5. the wiring: deletesdsolo.sh's marker is solo-ssh.sh's, setup names the service only when
#      the file is Solo's, and the installer's check matches what setup prints.
# --selftest runs the same checks on mutants of the function and the wiring; each must fail.
# Free: no install, no sudo, no sd.  Exit 0 passed, 1 failed, 2 could not measure.

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOLO_SSH = os.path.join(HERE, "solo-ssh.sh")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
DELETE = os.path.join(ROOT, "deletesdsolo.sh")
INSTALL = os.path.join(ROOT, "installsdsolo.sh")
DROPPED = ("pam_selinux", "pam_loginuid", "pam_namespace")

FEDORA44 = """#%PAM-1.0
auth       substack     password-auth
auth       include      postlogin
account    required     pam_sepermit.so
account    required     pam_nologin.so
account    include      password-auth
password   include      password-auth
# pam_selinux.so close should be the first session rule
session    required     pam_selinux.so close
session    required     pam_loginuid.so
# pam_selinux.so open should only be followed by sessions to be executed in the user context
session    required     pam_selinux.so open env_params
session    required     pam_namespace.so
session    optional     pam_keyinit.so force revoke
session    optional     pam_motd.so
session    include      password-auth
session    include      postlogin
"""


def cut(text, name):
    m = re.search(r"^# BEGIN %s\n(.*?)^# END %s$" % (name, name), text, re.S | re.M)
    return m.group(1) if m else ""


def live(lines):
    return [l for l in lines if l.strip() and not l.lstrip().startswith("#")]


def run_stack(fn, stack_text):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "sshd")
        open(src, "w").write(stack_text)
        r = subprocess.run(["bash", "-c", fn + '\npam_stack "$1" tester', "x", src],
                           capture_output=True, text=True)
        return r.returncode, r.stdout


def checks(fn, ssh_text, del_text, inst_text):
    rows = []
    rows.append(("1 pam_stack found between its markers", "pam_stack()" in fn,
                 "%d line(s) cut" % fn.count("\n")))
    if "pam_stack()" not in fn:
        return rows
    rc, out = run_stack(fn, FEDORA44)
    lines = out.splitlines()
    left = [l for l in live(lines) if any(m in l for m in DROPPED)]
    rows.append(("2 no live pam_selinux/pam_loginuid/pam_namespace line", rc == 0 and not left,
                 "rc %d, left: %s" % (rc, left or "none")))
    want = [l for l in live(FEDORA44.splitlines()) if not any(m in l for m in DROPPED)
            and not l.startswith("#%PAM")]
    got = [l for l in live(lines) if not l.startswith("#%PAM")]
    rows.append(("3 every other live line kept, in order", got == want and len(want) == 10,
                 "%d of %d kept%s" % (len([g for g in got if g in want]), len(want),
                                      "" if got == want else "; got %s" % got)))
    mark = re.search(r'^PAMMARK="([^"]+)"', ssh_text, re.M)
    mark = mark.group(1) if mark else None
    hdr = sum(1 for l in lines if l.strip() == "#%PAM-1.0")
    rows.append(("4 one #%PAM-1.0 header and the marker line", hdr == 1 and lines[:1] == ["#%PAM-1.0"]
                 and bool(mark) and any(l.startswith(mark) for l in lines),
                 "headers %d, marker %r %s" % (hdr, mark, "found" if mark and any(l.startswith(mark) for l in lines) else "MISSING")))
    del_ok = bool(mark) and ("grep -qF '%s'" % mark) in del_text
    setup_ok = re.search(r'if pam_ours; then\s*\n\s*echo "PAMServiceName \$PAMNAME" >> "\$tmp"', ssh_text) is not None
    inst_ok = "grep -q '^pam service    : /etc/pam.d/'" in inst_text and \
        'echo "pam service    : $pam_state"' in ssh_text and 'pam_state="$PAMFILE (SELinux)"' in ssh_text
    rows.append(("5 wiring: delete's marker, setup's condition, installer's check", del_ok and setup_ok and inst_ok,
                 "delete %s, setup %s, installer %s" % (del_ok, setup_ok, inst_ok)))
    return rows


def report(rows):
    fails = 0
    for name, ok, saw in rows:
        print("  [%s] %s | %s" % ("PASS" if ok else "FAIL", name, saw))
        fails += 0 if ok else 1
    return fails


def main():
    try:
        ssh_text = open(SOLO_SSH).read()
        del_text = open(DELETE).read()
        inst_text = open(INSTALL).read()
    except OSError as e:
        print("CANNOT MEASURE: %s" % e)
        return 2
    fn = cut(ssh_text, "pam_stack")
    print("inputs : %s (pam_stack), %s, %s; stack = Fedora 44's /etc/pam.d/sshd (17 lines)" % (SOLO_SSH, DELETE, INSTALL))
    if "--selftest" in sys.argv:
        mutants = [
            ("no filter at all", fn.replace("(pam_selinux|pam_loginuid|pam_namespace)", "(no_such_module)"), ssh_text, del_text, inst_text),
            ("pam_namespace kept", fn.replace("|pam_namespace", ""), ssh_text, del_text, inst_text),
            ("header copied twice", fn.replace("/^[[:space:]]*#%PAM/ { next }", ""), ssh_text, del_text, inst_text),
            ("every session line dropped", fn.replace("[^#[:space:]].*(pam_selinux|pam_loginuid|pam_namespace)\\.so", "session"), ssh_text, del_text, inst_text),
            ("function missing", "", ssh_text, del_text, inst_text),
            ("delete looks for another marker", fn, ssh_text, del_text.replace("the PAM service of", "the PAM file of"), inst_text),
            ("setup names it unconditionally", fn, ssh_text.replace("if pam_ours; then\n    echo \"PAMServiceName", "if true; then\n    echo \"PAMServiceName"), del_text, inst_text),
            ("installer checks another line", fn, ssh_text, del_text, inst_text.replace("'^pam service    : /etc/pam.d/'", "'^pam : /etc/pam.d/'")),
        ]
        caught = 0
        for name, f, s, d, i in mutants:
            rows = checks(f, s, d, i)
            bad = [r for r in rows if not r[1]]
            print("  mutant %-34s %s" % (name, "CAUGHT by %s" % bad[0][0] if bad else "NOT CAUGHT"))
            caught += 1 if bad else 0
        print("selftest: %d of %d mutants caught" % (caught, len(mutants)))
        return 0 if caught == len(mutants) else 1
    fails = report(checks(fn, ssh_text, del_text, inst_text))
    print("test-sshpam-units: %s" % ("PASSED" if fails == 0 else "%d FAILED" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
