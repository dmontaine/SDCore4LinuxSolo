#!/usr/bin/env python3
# test-retired-units.py - is solo-stage.sh's list of RETIRED files right?  (LSOLO 30, 3 Oct 2026)
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-retired-units.py [--selftest]
#
# An upgrade overlays sdsys/ onto the old tree and only adds and replaces, so a file a release
# stops shipping stays in an upgraded tree unless solo-stage.sh deletes it.  Three things can go
# wrong with that list, and this checks each:
#   1. a file on the list is STILL in sdsys/ - the upgrade would delete what the release ships;
#   2. a name on the list was never shipped - a typo, and "rm -f" would say nothing;
#   3. the list is empty or could not be read - the check would pass having looked at nothing.
# (2) is judged against the last release tag, LS1.1-2.  Without that tag in the repository the
# check says so and exits 2 rather than pass.  Free: no install, no sudo, no sd.
#
# Exit 0 every check passed, 1 one failed, 2 it could not measure.

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
STAGE = os.path.join(HERE, "solo-stage.sh")
SDSYS = os.path.join(SD64, "sdsys")
TAG = "LS1.1-2"
fails = 0


def say(ok, name, saw):
    global fails
    print("  [%s] %s | %s" % ("PASS" if ok else "FAIL", name, saw))
    if not ok:
        fails += 1


def read_list(path):
    text = open(path, encoding="utf-8").read()
    m = re.search(r"for f in ([^;]+); do\s*\n\s*rm -f \"\$H/\$f\"\s*\n\s*done", text)
    return m.group(1).split() if m else []


def judge(files, shipped_in_tag):
    """Return a list of (name, ok, saw) for a retired-file list."""
    rows = []
    rows.append(("1 the list is not empty", len(files) > 0, "%d name(s)" % len(files)))
    still = [f for f in files if os.path.exists(os.path.join(SDSYS, f))]
    rows.append(("2 nothing on the list is still shipped", not still, "still in sdsys/: %s" % (still or "none")))
    never = [f for f in files if not shipped_in_tag(f)]
    rows.append(("3 every name on the list was shipped in %s" % TAG, not never, "never shipped: %s" % (never or "none")))
    return rows


def shipped_in_tag(f):
    r = subprocess.run(["git", "-C", SD64, "cat-file", "-e", "%s:sdb_ai/sd64/sdsys/%s" % (TAG, f)],
                       capture_output=True)
    return r.returncode == 0


def main():
    print("test-retired-units inputs:")
    print("  list read from : %s" % STAGE)
    if subprocess.run(["git", "-C", SD64, "rev-parse", "--verify", "-q", TAG + "^{commit}"],
                      capture_output=True).returncode != 0:
        print("REFUSED: the release tag %s is not in this repository, so (3) cannot be judged" % TAG)
        return 2
    tag_commit = subprocess.run(["git", "-C", SD64, "rev-parse", "--short", TAG + "^{commit}"],
                                capture_output=True, text=True).stdout.strip()
    files = read_list(STAGE)
    print("  names          : %s" % (" ".join(files) or "(none found)"))
    print("  release tag    : %s = %s" % (TAG, tag_commit))
    if "--selftest" in sys.argv:
        return selftest(files)
    for name, ok, saw in judge(files, shipped_in_tag):
        say(ok, name, saw)
    print("test-retired-units: %s" % ("FAILED" if fails else "PASSED"))
    return 1 if fails else 0


def selftest(real):
    # Each mutant is a list the checks must NOT accept.
    shipped_here = [f for f in ("gpl.bp/login", "gpl.bp/cproc") if os.path.exists(os.path.join(SDSYS, f))]
    mutants = [
        ("a file that is still shipped", shipped_here[:1] or ["gpl.bp/login"]),
        ("a name that was never shipped", ["gpl.bp/zz_never_shipped"]),
        ("an empty list", []),
    ]
    bad = 0
    for label, lst in mutants:
        rows = judge(lst, shipped_in_tag)
        red = any(not ok for _, ok, _ in rows)
        print("  [%s] mutant: %s | %s" % ("PASS" if red else "FAIL", label, "detected" if red else "NOT DETECTED"))
        bad += 0 if red else 1
    print("test-retired-units --selftest: %s" % ("FAILED" if bad else "PASSED, %d of %d mutants red" % (len(mutants), len(mutants))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
