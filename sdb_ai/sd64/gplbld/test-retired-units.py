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
#   3. the list is empty or could not be read - the check would pass having looked at nothing;
#   4. (12 Nov 26) a file git records as DELETED from sdsys/ since the release tag, and not shipped again, is NOT on the list.
#      The S.117 carry removed gpl.bp/sed and three more without listing them; a real upgrade of a 26 Oct install then
#      compiled the left-behind sed against the new headers, bootstrap pass 2 failed (168 errors) and the upgrade rolled back.
# (2) and (4) are judged against the release tag, LS1.1-2.  Without that tag in the repository the
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


LIST = os.path.join(HERE, "retired-sdsys.txt")


def read_list(path):
    # 9 Nov 26 (Solo carry 22): the list moved from solo-stage.sh's for loop to gplbld/retired-sdsys.txt, one path a line.  solo-stage.sh must
    # still read that file in its upgrade branch, or the list would be ignored: an empty answer (check 1) when it does not.
    stage = open(STAGE, encoding="utf-8").read()
    if not re.search(r'retired_list="\$sd64/gplbld/retired-sdsys\.txt"[\s\S]{0,400}?rm -f -- "\$H/\$f"[\s\S]{0,40}?done < "\$retired_list"', stage):
        return []
    lines = open(path, encoding="utf-8").read().splitlines()
    return [ln for ln in lines if ln.strip() and not ln.startswith("#")]


def judge(files, shipped_in_tag, deleted):
    """Return a list of (name, ok, saw) for a retired-file list.  deleted: the sdsys/ paths git records as deleted since TAG."""
    rows = []
    rows.append(("1 the list is not empty", len(files) > 0, "%d name(s)" % len(files)))
    still = [f for f in files if os.path.exists(os.path.join(SDSYS, f))]
    rows.append(("2 nothing on the list is still shipped", not still, "still in sdsys/: %s" % (still or "none")))
    never = [f for f in files if not shipped_in_tag(f)]
    rows.append(("3 every name on the list was shipped in %s" % TAG, not never, "never shipped: %s" % (never or "none")))
    listed = set(files)
    gone = [f for f in deleted if not os.path.exists(os.path.join(SDSYS, f)) and f not in listed]
    rows.append(("4 every file deleted from sdsys/ since %s (%d) is on the list" % (TAG, len(deleted)), len(deleted) > 0 and not gone,
                 "deleted, not listed: %s" % (gone or "none")))
    return rows


def deleted_since_tag():
    """The sdsys/ paths (relative to sdsys/) that a commit since TAG deleted, or the work tree has deleted from HEAD."""
    top = ":(top)sdb_ai/sd64/sdsys"
    out = subprocess.run(["git", "-C", SD64, "log", TAG + "..HEAD", "--diff-filter=D", "--name-only", "--format=", "--", top],
                         capture_output=True, text=True).stdout.split()
    out += subprocess.run(["git", "-C", SD64, "diff", "--diff-filter=D", "--name-only", "HEAD", "--", top], capture_output=True, text=True).stdout.split()
    pre = "sdb_ai/sd64/sdsys/"
    return sorted({p[len(pre):] for p in out if p.startswith(pre)})


def shipped_in_tag(f):
    # Shipped in the release tag, or (9 Nov 26) shipped by a later Dev commit and deleted since: the file is in HEAD (removed in the
    # work tree, not yet committed) or git records its deletion.  A typo is none of these.
    path = "sdb_ai/sd64/sdsys/%s" % f
    for ref in (TAG, "HEAD"):
        if subprocess.run(["git", "-C", SD64, "cat-file", "-e", "%s:%s" % (ref, path)], capture_output=True).returncode == 0:
            return True
    r = subprocess.run(["git", "-C", SD64, "log", "-1", "--format=%h", "--diff-filter=D", "--", ":(top)" + path], capture_output=True, text=True)   # the path is from the repository's top
    return r.stdout.strip() != ""


def main():
    print("test-retired-units inputs:")
    print("  list read from : %s (read by %s)" % (LIST, STAGE))
    if subprocess.run(["git", "-C", SD64, "rev-parse", "--verify", "-q", TAG + "^{commit}"],
                      capture_output=True).returncode != 0:
        print("REFUSED: the release tag %s is not in this repository, so (3) cannot be judged" % TAG)
        return 2
    tag_commit = subprocess.run(["git", "-C", SD64, "rev-parse", "--short", TAG + "^{commit}"],
                                capture_output=True, text=True).stdout.strip()
    files = read_list(LIST)
    print("  names          : %s" % (" ".join(files) or "(none found)"))
    print("  release tag    : %s = %s" % (TAG, tag_commit))
    deleted = deleted_since_tag()
    print("  deleted since  : %d path(s) under sdsys/ (git log %s..HEAD --diff-filter=D, and the work tree)" % (len(deleted), TAG))
    if "--selftest" in sys.argv:
        return selftest(files, deleted)
    for name, ok, saw in judge(files, shipped_in_tag, deleted):
        say(ok, name, saw)
    print("test-retired-units: %s" % ("FAILED" if fails else "PASSED"))
    return 1 if fails else 0


def selftest(real, deleted):
    # Each mutant is a list the checks must NOT accept.
    shipped_here = [f for f in ("gpl.bp/login", "gpl.bp/cproc") if os.path.exists(os.path.join(SDSYS, f))]
    gone = [f for f in deleted if f in real and not os.path.exists(os.path.join(SDSYS, f))]
    mutants = [
        ("a file that is still shipped", shipped_here[:1] or ["gpl.bp/login"]),
        ("a name that was never shipped", ["gpl.bp/zz_never_shipped"]),
        ("an empty list", []),
        ("a deleted file left off the list (%s)" % (gone[-1] if gone else "none to take off"), [f for f in real if f != (gone[-1] if gone else None)] if gone else None),
    ]
    bad = 0
    for label, lst in mutants:
        if lst is None:
            print("  [FAIL] mutant: %s | NOTHING TO MUTATE: no listed file is among the deletions" % label)
            bad += 1
            continue
        rows = judge(lst, shipped_in_tag, deleted)
        red = any(not ok for _, ok, _ in rows)
        print("  [%s] mutant: %s | %s" % ("PASS" if red else "FAIL", label, "detected" if red else "NOT DETECTED"))
        bad += 0 if red else 1
    print("test-retired-units --selftest: %s" % ("FAILED" if bad else "PASSED, %d of %d mutants red" % (len(mutants), len(mutants))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
