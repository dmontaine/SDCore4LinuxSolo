#!/usr/bin/env python3
"""test-soloexamples-units.py - examples.bp in Solo's one account (S.261, 17 Nov 2026) as invariants read off the source.  Free: no install, no sudo, no sd.

    python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-soloexamples-units.py [--selftest]

The owner, 17 Nov 2026: "there should be a examples.bp file available to all users that contains those programs and a set of training programs typical for
a Computer Science 101 course"; for Solo: "just include examples.bp in the single account, no need to load or remove".  SD Core's way (the verbs LOAD.EXAMPLES
and REMOVE.EXAMPLES, LOGTO into each account) is not Solo's: Solo has one account, no LOGTO and no verb for this.  What it holds:
  E1  the 28 shipped programs are the ones SD Core ships, byte for byte (the Core tree /home/don/Projects/SDCore4Linux; exit 2 when it is missing)
  E2  gpl.bp/solo_examples is the installer's alone (K$INTERNAL before it opens anything), reads the account sduser from the register, has no LOGTO, writes
      its two temporary VOC entries BEFORE the first compile and deletes them AFTER the last, keeps programs it does not ship, judges every compile on the
      compiler's success line, and ends on the line the stage anchors on
  E3  solo-stage.sh's EXAMPLES block is there once, before SYNC.GLOBAL.CATALOG and SOURCE-GONE, is run by a fresh stage AND BY AN UPGRADE (the call is at the
      top level, outside the "not an upgrade" branch: the owner, 17 Nov 2026, "all four versions need to add examples.bp to every account during upgrade")
      and again after a reload of kept data, warns and goes on when solo_examples does not report 0 failed
  E4  there is NO verb: no load.examples, remove.examples or solo_examples VOC record, and no loadexamples or removeexamples program
It cannot say a program compiles or runs: the Solo sandbox (sandbox-fromtree.py all, then RUN gpl.bp solo_examples) did that on 17 Nov 2026.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.normpath(os.path.join(HERE, ".."))
SDSYS = os.path.join(SD64, "sdsys")
EX = os.path.join(SDSYS, "examples")
CORE_EX = "/home/don/Projects/SDCore4Linux/sdb_ai/sd64/sdsys/examples"


def rd(p):
    try:
        with open(p, encoding="latin-1") as f:
            return f.read()
    except OSError:
        return None


def load():
    raw = {"prog": rd(os.path.join(SDSYS, "gpl.bp", "solo_examples")), "stage": rd(os.path.join(HERE, "solo-stage.sh"))}
    raw["files"] = {n: rd(os.path.join(EX, n)) for n in sorted(os.listdir(EX))} if os.path.isdir(EX) else {}
    raw["core"] = {n: rd(os.path.join(CORE_EX, n)) for n in sorted(os.listdir(CORE_EX))} if os.path.isdir(CORE_EX) else {}
    raw["verbs"] = {os.path.join(d, n): rd(os.path.join(SDSYS, d, n)) for d in ("voc_template", "newvoc") for n in ("load.examples", "remove.examples", "solo_examples")}
    raw["progs"] = {n: rd(os.path.join(SDSYS, "gpl.bp", n)) for n in ("loadexamples", "removeexamples")}
    return raw


def code(src):
    return "\n".join(re.sub(r"\s*;\*.*$", "", l) for l in (src or "").split("\n") if not re.match(r"^\s*\*", l))


def checks(raw):
    rows = []

    def ck(i, what, ok, detail=""):
        rows.append((i, what, bool(ok), detail))

    files, core = raw["files"], raw["core"]
    diff = sorted(n for n in set(files) | set(core) if files.get(n) != core.get(n))
    ck("E1", "the %d shipped programs are SD Core's, byte for byte" % len(files), len(files) >= 25 and not diff, repr(diff[:6]))
    p = code(raw["prog"])
    ck("E2a", "solo_examples is the installer's alone: K$INTERNAL asked before the examples directory or the register is opened",
       raw["prog"] is not None and 0 <= p.find("if not(kernel(K$INTERNAL, -1)) then") < p.find("dir(src)") < p.find("openpath @sdsys : @ds : 'accounts'"))
    ck("E2b", "it reads sduser from the register, through the token form, and has no LOGTO",
       "read acc.rec from acc.f, 'sduser' else" in p and "parse.pathname.tokens(acc.rec<ACC$PATH>)" in p and "logto" not in p.lower())
    w = p.find("write tmp1 to svoc, 'examples.bp'")
    first = p.find("execute 'basic examples.bp '")
    d1 = p.find("delete svoc, 'examples.bp'")
    d2 = p.find("delete svoc, 'examples.bp.out'")
    ck("E2c", "the two temporary VOC entries are written before the first compile and deleted after the last, and nothing else is executed",
       0 < w < p.find("write tmp2 to svoc, 'examples.bp.out'") < first < d1 < d2 and p.count("execute ") == 1)
    ck("E2d", "a program it does not ship is kept (no delete or clear of the examples file), every compile is judged on the compiler's success line",
       "delete xf" not in p and "clear.file" not in p.lower() and "if index(out, 'Compiled 1 program(s) with no errors', 1) then" in p)
    ck("E2e", "it ends on the line the stage anchors on, and is told 'only the installer' when it is not",
       "solo_examples: examples.bp ready: ' : n.new : ' new, ' : n.changed : ' changed, ' : n.same : ' the same, compiled ' : n.compiled : ' of ' : n.tried : ', ' : n.bad : ' failed'" in p
       and "solo_examples: only the installer may run this." in p)
    st = raw["stage"] or ""
    b = st.find("# EXAMPLES-BEGIN")
    e = st.find("# EXAMPLES-END")
    blk = st[b:e] if b >= 0 else ""
    ck("E3a", "the stage's EXAMPLES block: once, before SYNC.GLOBAL.CATALOG and SOURCE-GONE, running RUN gpl.bp solo_examples internally, anchored on 0 failed",
       st.count("# EXAMPLES-BEGIN") == 1 and 0 <= b < st.find("Syncing the global catalogue") < st.find("# SOURCE-GONE-BEGIN")
       and "sdi RUN gpl.bp solo_examples" in blk and "compiled [0-9]+ of [0-9]+, 0 failed" in blk)
    ck("E3b", "a failure is a WARNING and the stage goes on (no fail, no exit in the block)", "WARNING: the example programs were not put into the account" in blk
       and "fail " not in blk and "exit" not in blk)
    calls = [m.start() for m in re.finditer(r"^\s*examples_step\b(?!\s*\(\))", st, re.M)]       # the calls, not the definition
    cn = st.find("  convert_nocase\n")
    ck("E3c", "examples_step is called twice: after the fresh account, and again after a reload's convert_nocase",
       len(calls) == 2 and cn >= 0 and calls[1] > cn and calls[0] < st.find("Syncing the global catalogue"))
    # 17 Nov 26 - the owner, in the Windows chat: "yes all four versions need to add examples.bp to every account during upgrade".  The first call is
    # reached by a fresh stage AND by --upgrade only while it stays at the top level, after the end of the "not an upgrade" branch.
    marker = 'fi   # end of "not an upgrade"'
    mk = st.find(marker)
    seg = st[mk + len(marker):calls[0]] if mk >= 0 and calls else ""
    top_if = len(re.findall(r"^if ", seg, re.M))
    top_fi = len(re.findall(r"^fi\b", seg, re.M))
    line0 = st[st.rfind("\n", 0, calls[0]) + 1:st.find("\n", calls[0])] if calls else ""
    ck("E3d", "AN UPGRADE GETS IT TOO: the first call is at the top level, after the end of the 'not an upgrade' branch and inside no if (%d opened, %d closed since)" % (top_if, top_fi),
       st.count(marker) == 1 and calls and mk < calls[0] and line0 == "examples_step" and top_if == top_fi and top_if > 0, repr((mk, calls[:1], line0, top_if, top_fi)))
    ck("E4", "no verb: no load.examples, remove.examples or solo_examples record in voc_template or newvoc, no loadexamples or removeexamples program",
       all(v is None for v in raw["verbs"].values()) and all(v is None for v in raw["progs"].values()), repr([k for k, v in list(raw["verbs"].items()) + list(raw["progs"].items()) if v is not None]))
    return rows


def sub(key, old, new):
    def f(raw):
        if raw.get(key) is None or old not in raw[key]:
            return None
        r = dict(raw)
        r[key] = raw[key].replace(old, new, 1)
        return r
    return f


MUTANTS = [
    ("a shipped program drifts from Core's", "E1", lambda raw: dict(raw, files=dict(raw["files"], hello=(raw["files"]["hello"] or "") + "x"))),
    ("solo_examples does not ask for the installer", "E2a", sub("prog", "if not(kernel(K$INTERNAL, -1)) then", "if 0 then")),
    ("solo_examples enters the account with logto", "E2b", sub("prog", "   openpath xpath to xf else", "   execute 'logto sduser' capturing lt\n   openpath xpath to xf else")),
    ("the temporary entries are not deleted", "E2c", sub("prog", "      delete svoc, 'examples.bp'\n", "")),
    ("the temporary entries are written after the compile", "E2c", sub("prog", "      write tmp1 to svoc, 'examples.bp'\n      write tmp2 to svoc, 'examples.bp.out'\n", "")),
    ("the examples file is cleared first", "E2d", sub("prog", "   openpath xpath to xf else", "   execute 'clear.file examples.bp'\n   openpath xpath to xf else")),
    ("the compile is not judged", "E2d", sub("prog", "if index(out, 'Compiled 1 program(s) with no errors', 1) then", "if 1 then")),
    ("the closing line changes", "E2e", sub("prog", "' failed'", "' fail'")),
    ("the stage block runs another program", "E3a", sub("stage", "sdi RUN gpl.bp solo_examples", "sdi RUN gpl.bp solo_account")),
    ("the stage fails the install on a bad examples run", "E3b", sub("stage", "    echo \"solo-stage: WARNING: the example programs were not put", "    fail \"the example programs were not put")),
    ("the examples are put in on a fresh install only, not on an upgrade", "E3d",
     lambda raw: dict(raw, stage=raw["stage"].replace("examples_step\n\n# Ruling 33", "\n# Ruling 33", 1).replace('fi   # end of "not an upgrade"', 'examples_step\nfi   # end of "not an upgrade"', 1))),
    ("the examples call is put under an upgrade test", "E3d", sub("stage", "examples_step\n\n# Ruling 33", "if [ \"$upgrade\" -eq 0 ]; then\n  examples_step\nfi\n\n# Ruling 33")),
    ("no examples after a reload", "E3c", sub("stage", "  examples_step                                  #", "  :                                              #")),
    ("load.examples is given to the account", "E4", lambda raw: dict(raw, verbs=dict(raw["verbs"], **{os.path.join("newvoc", "load.examples"): "V\nCA\n$loadexamples\n"}))),
]


def main(argv):
    raw = load()
    if not raw["core"]:
        print("test-soloexamples-units: CANNOT RUN - no Core tree at %s" % CORE_EX)
        return 2
    if not raw["files"] or raw["prog"] is None:
        print("test-soloexamples-units: CANNOT RUN - no %s or no solo_examples" % EX)
        return 2
    if "--selftest" in argv:
        if any(not ok for _, _, ok, _ in checks(raw)):
            print("REFUSING - the unmutated source already fails")
            return 1
        missed = 0
        for name, tag, f in MUTANTS:
            m = f(raw)
            failed = [] if m is None else [i for i, _, ok, _ in checks(m) if not ok]
            if m is None or not any(x.startswith(tag) for x in failed):
                print("  [MISSED] %s" % name)
                missed += 1
            else:
                print("  [pass] %s: caught by %s" % (name, ",".join(sorted(set(x for x in failed if x.startswith(tag))))))
        print("self-test: %d mutants, %d not caught" % (len(MUTANTS), missed))
        return 1 if missed else 0
    rows = checks(raw)
    bad = 0
    for i, what, ok, detail in rows:
        print("  [%s] %s %s%s" % ("PASS" if ok else "FAIL", i, what, "" if ok else "   <- " + str(detail)[:300]))
        bad += 0 if ok else 1
    print("test-soloexamples-units: %d checks, %d failed" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
