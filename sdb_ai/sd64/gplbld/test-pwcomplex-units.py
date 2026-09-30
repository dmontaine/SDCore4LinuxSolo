#!/usr/bin/env python3
"""Unit test for SD's password rule, SD Core for Linux Solo.  Free - no install,
no sudo, no sd.

29 Sep 2026, LSOLO 4: THE BASH COPY IS GONE.  gplbld/sd-elevate, which held the
second implementation (the installer's sdsys prompt), was deleted with the
multi-user machinery, so the legs that drove it (S, S1-S3) and the installer
arm of the partition check (P) are removed.  What is left is the BASIC rule,
A, B2, B2b, B3, P over gpl.bp, and Z.  The installer's own password prompts
(LSOLO 9) must be put under a rule check when they are written; until then
this test says nothing about them.  The text below still describes the
two-implementation history.

Written 19 Sep 2026, on the SD Core for Windows agent's mail of 14:30 the same
day.  It took this tree's `pw_complex` case block verbatim and asked for two
rows back: one proving an arm-order mutation is not vacuous, and one showing
the OLD shape accepting the TAB row the new one refuses.  Both are here (B2,
B3, S2, S3), and the port has the equivalent as `test-pwcomplex-units`.

WHAT IT IS FOR.  The owner's ruling of 19 Sep 2026 is that SD requires a
complex password whatever the operating system allows: 8+ characters with a
lower-case letter, an upper-case letter, a digit and a symbol (any other
printable ASCII, space included); a byte outside 32-126 fails outright.  ONE
RULE, WRITTEN TWICE IN THIS TREE, and they cannot be merged: `gpl.bp/pw_complex`
serves everything inside SD, and `gplbld/sd-elevate`'s `pw_complex` serves the
installer's sdsys prompt, which runs before SD can be reached at all.  A third
copy is the Windows port's.  So the table below is the rule's SPEC and both
implementations are driven through it.

THE BASIC IS CHECKED WITHOUT BEING RUN, AND THE LIMIT IS STATED RATHER THAN
GLOSSED.  Nothing in a session can execute SD BASIC - a GPL.BP change is proven
by commit, push and reinstall.  So this reads the RANGES and the ARM ORDER out
of `gpl.bp/pw_complex` and drives the table through what the file says.  That
is weaker than running it: it proves the rule the file states, not the rule the
compiler emits.  The compiled behaviour is witnessed on an install
(`witness-absence.sh` M2e/f, M11a-d).

WHY THE ARM ORDER IS WORTH A TEST AT ALL.  The port's first shape tested
out-of-range in the FIRST arm and let the catch-all mean "symbol".  That is
correct only while nobody reorders the arms: move it and a byte outside 32-126
falls through to the catch-all and SATISFIES the symbol requirement it exists
to fail - it fails OPEN.  This tree's shape names 32-126 in the symbol arm and
returns false from the catch-all, so an unmatched byte is refused whatever the
order.  B2 drives EVERY permutation of the arms and requires the non-printable
rows to be refused by all of them; B3 shows the old shape accepting the tab row
once its guard arm is no longer first.  Mutants run on text.  THE LIVE FILES
ARE ASSERTED BYTE-IDENTICAL AFTERWARDS.

Null case refused out loud: a run with no ALLOW rows, no REFUSE rows, no
permutations, or a mutant that stayed green, exits 2 rather than reporting
success.

  python3 /home/don/Projects/SDCore4Linux/sdb_ai/sd64/gplbld/test-pwcomplex-units.py

No sudo.  Exit 0 all rows passed, 1 a row failed, 2 a premise was not found in
the source or the run established nothing.
"""

import itertools
import os
import re
import subprocess
import sys

ALLOW, REFUSE = "ALLOW", "REFUSE"

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
BASIC = os.path.join(SD64, "sdsys", "gpl.bp", "pw_complex")


# ---------------------------------------------------------------------------
# THE SPEC.  The owner's rule of 19 Sep 2026, as one table.  Every REFUSE row
# lacks exactly ONE thing, so an implementation that stopped checking any one
# class fails here; the ALLOW rows are the control - a rule that refused
# everything would pass every REFUSE row and be useless.
#
# Rows 5 and 6 are the SD Core for Windows agent's additions of 19 Sep 2026:
# the two ends of the symbol range, which no other row pins.
# `test-sd-elevate.py` imports this table rather than keeping its own copy.
SPEC = [
    (ALLOW,  "Abcdef1!",       "exactly 8, all four kinds"),
    (ALLOW,  "zZ9 zzzz",       "a space is a symbol"),
    (ALLOW,  "Pass:word1",     "a colon (chpasswd's separator) is only a symbol"),
    (ALLOW,  "Aa1~" * 30,      "long is fine - no maximum"),
    (ALLOW,  "Abcdef1 ",       "a trailing SPACE, chr 32 - the symbol range's low end"),
    (ALLOW,  "Abcdef1~",       "a trailing TILDE, chr 126 - its high end"),
    (REFUSE, "Abcde1!",        "7 characters - one short"),
    (REFUSE, "abcdef1!",       "no upper-case letter"),
    (REFUSE, "ABCDEF1!",       "no lower-case letter"),
    (REFUSE, "Abcdefg!",       "no digit"),
    (REFUSE, "Abcdefg1",       "no symbol"),
    (REFUSE, "Abcdef1\t",      "a tab is not printable ASCII"),
    (REFUSE, "Abcdef\x7f1!",   "chr 127 (DEL) is one past the range"),
    (REFUSE, "Abcdéf1!",  "a non-ASCII letter"),
    (REFUSE, "",               "empty"),
]

# The two rows the mutants turn on, looked up by note rather than by index so
# a reordering of SPEC cannot silently point them at something else.
TAB_ROW = "Abcdef1\t"
GOOD_ROW = "Abcdef1!"


def refuse(why):
    print("REFUSED: %s" % why, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# The BASIC, read rather than run.

ALWAYS, RANGE, OUTSIDE = "always", "range", "outside"
SET, REJECT = "set", "reject"

ARM_RE = re.compile(r"^\s*case\s+(?P<cond>.+?)\s*;\s*(?P<act>[^;]+?)\s*(?:;\*.*)?$")
COND_RANGE = re.compile(r"^c\s*>=\s*(\d+)\s+and\s+c\s*<=\s*(\d+)$")
COND_OUTSIDE = re.compile(r"^c\s*<\s*(\d+)\s+or\s+c\s*>\s*(\d+)$")
ACT_SET = re.compile(r"^has\.(lower|upper|digit|symbol)\s*=\s*@true$")
ACT_REJECT = re.compile(r"^return\s+@false$")


def parse_cond(text, where):
    if text == "1":
        return (ALWAYS, None, None)
    m = COND_RANGE.match(text)
    if m:
        return (RANGE, int(m.group(1)), int(m.group(2)))
    m = COND_OUTSIDE.match(text)
    if m:
        return (OUTSIDE, int(m.group(1)), int(m.group(2)))
    refuse("%s: a case condition this test cannot read: %r" % (where, text))


def parse_act(text, where):
    m = ACT_SET.match(text)
    if m:
        return (SET, m.group(1))
    if ACT_REJECT.match(text):
        return (REJECT, None)
    refuse("%s: a case action this test cannot read: %r" % (where, text))


def parse_basic(text, where):
    """Lift (minlen, arms, required) out of the BASIC source.

    ANY PREMISE NOT FOUND IS A REFUSAL, not a guess - the whole point is that
    the model is the file's, not this test's.
    """
    m = re.search(r"if\s+len\(pw\)\s*<\s*(\d+)\s+then\s+return\s+@false", text)
    if not m:
        refuse("%s: no minimum-length guard 'if len(pw) < N then return @false'" % where)
    minlen = int(m.group(1))

    # The rule must look at EVERY byte, or a table row could pass for the
    # wrong reason.  Both premises are read, neither assumed.
    if not re.search(r"for\s+i\s*=\s*1\s+to\s+n", text):
        refuse("%s: no 'for i = 1 to n' - nothing proves every character is examined" % where)
    if not re.search(r"c\s*=\s*seq\(pw\[i,1\]\)", text):
        refuse("%s: no 'c = seq(pw[i,1])' - nothing proves c is the character's code" % where)

    block = re.search(r"^\s*begin case\s*$(.*?)^\s*end case\s*$", text, re.S | re.M)
    if not block:
        refuse("%s: no 'begin case' ... 'end case' block" % where)
    arms = []
    for line in block.group(1).split("\n"):
        if not line.strip():
            continue
        m = ARM_RE.match(line)
        if not m:
            refuse("%s: a line inside the case block this test cannot read: %r" % (where, line))
        arms.append((parse_cond(m.group("cond"), where),
                     parse_act(m.group("act"), where),
                     line.strip()))
    if not arms:
        refuse("%s: the case block is empty" % where)

    m = re.search(r"return\s*\(\s*(has\.[a-z.\s]+?)\s*\)", text)
    if not m:
        refuse("%s: no final 'return (has.… and has.…)' conjunction" % where)
    required = [p.strip() for p in m.group(1).split(" and ")]
    for r in required:
        if not re.match(r"^has\.(lower|upper|digit|symbol)$", r):
            refuse("%s: an unreadable term in the final conjunction: %r" % (where, r))
    return minlen, arms, [r.split(".")[1] for r in required]


def basic_verdict(model, pw):
    """Evaluate the parsed BASIC against one password.  Bytes, as seq() sees."""
    minlen, arms, required = model
    raw = pw.encode("utf-8")
    if len(raw) < minlen:
        return REFUSE
    flags = set()
    for c in raw:
        for cond, act, _ in arms:
            kind, lo, hi = cond
            hit = (kind == ALWAYS
                   or (kind == RANGE and lo <= c <= hi)
                   or (kind == OUTSIDE and (c < lo or c > hi)))
            if not hit:
                continue
            if act[0] == REJECT:
                return REFUSE
            flags.add(act[1])
            break
        # No arm matched: SD BASIC's begin case simply falls through, so the
        # character is silently ignored.  That is the fail-open shape, modelled
        # faithfully rather than defended against here.
    return ALLOW if all(f in flags for f in required) else REFUSE


# The port's ORIGINAL shape, quoted from its mail of 19 Sep 2026 13:40: the
# out-of-range test in the FIRST arm, the catch-all meaning "symbol".  Correct
# as written; the mutant is what happens when it is reordered.
OLD_SHAPE = """      begin case
         case c < 32 or c > 126 ; return @false
         case c >= 97 and c <= 122 ; has.lower = @true
         case c >= 65 and c <= 90  ; has.upper = @true
         case c >= 48 and c <= 57  ; has.digit = @true
         case 1 ; has.symbol = @true
      end case
"""


def with_block(text, block):
    """Return text with its begin case ... end case replaced by block."""
    return re.sub(r"^\s*begin case\s*$.*?^\s*end case\s*$\n",
                  block, text, count=1, flags=re.S | re.M)


# ---------------------------------------------------------------------------

def main():
    passed = failed = 0
    n_allow = n_refuse = n_mutant = 0
    failures = []

    def row(tag, ok, said):
        nonlocal passed, failed
        passed += ok
        failed += not ok
        print("  [%s] %s | %s" % ("PASS" if ok else "FAIL", tag, said))
        if not ok:
            failures.append((tag, said))

    if not os.path.exists(BASIC):
        refuse("%s is missing - there is nothing to test" % BASIC)

    basic_text = open(BASIC, "rb").read().decode("utf-8")

    print("inputs, as used this run:")
    print("  BASIC    : %s" % BASIC)
    print("  spec     : %d rows (%d ALLOW, %d REFUSE)"
          % (len(SPEC), sum(1 for r in SPEC if r[0] == ALLOW),
             sum(1 for r in SPEC if r[0] == REFUSE)))

    model = parse_basic(basic_text, "gpl.bp/pw_complex")
    minlen, arms, required = model
    print("  premises read out of gpl.bp/pw_complex:")
    print("    minimum length  : %d" % minlen)
    print("    required classes: %s" % ", ".join(required))
    for i, (_, _, src) in enumerate(arms, 1):
        print("    arm %d           : %s" % (i, src))
    print()

    # ---- A: the live BASIC, as the file states it.
    print("A - gpl.bp/pw_complex, read out of the file:")
    for expect, pw, note in SPEC:
        got = basic_verdict(model, pw)
        n_allow += expect == ALLOW
        n_refuse += expect == REFUSE
        row("A %-6s basic " % expect, got == expect,
            "%-14s %s (said %s)" % (repr(pw)[:14], note, got))

    # ---- B2: THE ARM ORDER CANNOT LET A NON-PRINTABLE BYTE THROUGH.
    # ---- Every permutation of the arms, not one chosen reordering.
    print("B2 - every permutation of the BASIC arms still refuses a non-printable byte:")
    nonprintable = [pw for expect, pw, note in SPEC
                    if expect == REFUSE and any(c < 32 or c > 126 for c in pw.encode("utf-8"))]
    if not nonprintable:
        refuse("no SPEC row carries a byte outside 32-126, so B2 would measure nothing")
    perms = list(itertools.permutations(range(len(arms))))
    leaked = []
    live_refused_good = 0
    for p in perms:
        m2 = (minlen, [arms[i] for i in p], required)
        for pw in nonprintable:
            if basic_verdict(m2, pw) != REFUSE:
                leaked.append((p, pw))
        if basic_verdict(m2, GOOD_ROW) == REFUSE:
            live_refused_good += 1
    n_mutant += len(perms)
    row("B2 order      ", not leaked,
        "%d permutations x %d non-printable rows, all refused; leaks: %s"
        % (len(perms), len(nonprintable),
           "none" if not leaked else repr(leaked[:3])))

    # ---- B2b: AND THE PERMUTATION DRIVER IS NOT VACUOUS.  If reordering the
    # ---- arms changed nothing at all, B2 would pass on a driver that does
    # ---- nothing.  The Windows agent's row: a scrambled order must still
    # ---- REFUSE A GOOD PASSWORD, or the order row proves nothing.
    print("B2b - the permutation driver is live (some order refuses a GOOD password):")
    row("B2b liveness  ", live_refused_good > 0,
        "%d of %d permutations refuse %r; the shipped order accepts it (%s)"
        % (live_refused_good, len(perms), GOOD_ROW, basic_verdict(model, GOOD_ROW)))

    # ---- B3: THE OLD SHAPE, AND WHAT REORDERING DOES TO IT.  Control first:
    # ---- as the port wrote it, it must agree with ours on every row - so the
    # ---- mutant below is the ORDER, not a shape this test broke.
    print("B3 - the port's original shape: identical as written, fails OPEN when reordered:")
    old_model = parse_basic(with_block(basic_text, OLD_SHAPE), "the old shape")
    old_disagree = [pw for _, pw, _ in SPEC
                    if basic_verdict(old_model, pw) != basic_verdict(model, pw)]
    n_mutant += 1
    row("B3 control    ", not old_disagree,
        "as written it agrees with ours on all %d rows; disagreements: %s"
        % (len(SPEC), ", ".join(repr(d) for d in old_disagree) if old_disagree else "none"))

    # Its guard arm demoted past the catch-all - the reordering it cannot
    # survive.  A tab now reaches `case 1` and is counted as a SYMBOL.
    old_arms = old_model[1]
    guard = [a for a in old_arms if a[0][0] == OUTSIDE]
    if len(guard) != 1:
        refuse("the old shape did not parse with exactly one out-of-range arm")
    demoted = (old_model[0], [a for a in old_arms if a[0][0] != OUTSIDE] + guard, old_model[2])
    n_mutant += 1
    got = basic_verdict(demoted, TAB_ROW)
    row("B3 mutant     ", got == ALLOW,
        "guard arm demoted past the catch-all: %r -> %s (ours: %s)"
        % (TAB_ROW, got, basic_verdict(model, TAB_ROW)))

    # ---- P: THE PARTITION.  Every prompt that sets a password runs the rule.
    # ---- This is the regression no row about the rule itself can see: the
    # ---- rule can be perfect and simply not reached.
    print("P - every password prompt in the tree applies the rule:")
    gplbp = os.path.join(SD64, "sdsys", "gpl.bp")
    prompts = []
    verify_only = []
    for name in sorted(os.listdir(gplbp)):
        path = os.path.join(gplbp, name)
        if not os.path.isfile(path):
            continue
        body = open(path, "rb").read().decode("latin-1")
        if re.search(r"^\s*input\s+\S+\s+HIDDEN\s*$", body, re.M | re.I):
            # A prompt that only VERIFIES a password (calls !CRED_VERIFY, never
            # !CRED_SET) must NOT apply the rule: a password set before the
            # rule, or by another port, would lock its owner out of login.
            # CODE only: a comment that names !CRED_SET is not a call to it.
            code = "\n".join(l for l in body.splitlines()
                             if not l.lstrip().startswith("*"))
            calls_verify = re.search(r"call\s+!CRED_VERIFY", code, re.I) is not None
            calls_set = re.search(r"call\s+!CRED_SET", code, re.I) is not None
            if calls_verify and not calls_set:
                verify_only.append("sdsys/gpl.bp/" + name)
            else:
                prompts.append(("sdsys/gpl.bp/" + name, body, r"pw_complex\("))
    for where in verify_only:
        vbody = open(os.path.join(SD64, where), "rb").read().decode("latin-1")
        # Applying the rule where a password is only checked is the defect: it
        # would refuse a correct old password.  So the row goes red if it does.
        row("P  verify-only", re.search(r"pw_complex\s*\(", vbody) is None,
            "%-28s only verifies (CRED_VERIFY, no CRED_SET) and does not call pw_complex" % where)
    partition_skipped = not prompts and not verify_only
    if partition_skipped:
        # LSOLO 4 deleted every password prompt (MODIFY.PASSWORD, CREATE.ACCOUNT)
        # and LSOLO 6's SET.PASSWORD does not exist yet.  Said out loud, not
        # passed silently; when a prompt exists again this leg must run.
        print("  [SKIP] P  partition   | NO password prompt exists in gpl.bp "
              "(LSOLO 6 adds SET.PASSWORD); this leg measured NOTHING")
    for where, body, needle in prompts:
        row("P  partition  ", re.search(needle, body) is not None,
            "%-28s prompts for a password and calls %s" % (where, needle.replace("\\", "")))

    # ---- THE LIVE FILES ARE UNCHANGED.  Mutants ran on text; if any of this
    # ---- reached the tree, every verdict above is void.
    print("Z - the live files are byte-identical after the mutants:")
    row("Z  untouched  ",
        open(BASIC, "rb").read().decode("utf-8") == basic_text,
        "gpl.bp/pw_complex unchanged on disk")

    print()

    # ---- refuse the null case, out loud.
    if n_allow == 0:
        refuse("no ALLOW rows ran; nothing proved the rule discriminates "
               "rather than refusing everything")
    if n_refuse == 0:
        refuse("no REFUSE rows ran; nothing tested the rule")
    if n_mutant == 0:
        refuse("no mutants ran; nothing proved these rows can go red")

    print("%d passed, %d failed (%d ALLOW rows, %d REFUSE rows, %d mutants)"
          % (passed, failed, n_allow, n_refuse, n_mutant))
    if partition_skipped:
        print("SKIPPED: leg P (password-prompt partition) - no prompt in the tree yet")

    if failed:
        print("\nfailures:", file=sys.stderr)
        for tag, said in failures:
            print("  %s: %s" % (tag.strip(), said), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
