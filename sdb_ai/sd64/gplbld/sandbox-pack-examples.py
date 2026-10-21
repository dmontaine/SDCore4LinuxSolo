#!/usr/bin/env python3
#
# sandbox-pack-examples.py - the generated knowledge pack (agent-pack/pack) against a RUNNING SD CORE SOLO.  S.69 row 1b, Solo's copy
#                            (LSOLO 55).  No install, no sudo.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/sandbox-pack-examples.py <dir> [--build]
#
# <dir> is a sandbox made by Solo's sandbox-fromtree.py (needs a `make`d bin/sd-solo).  With --build it is built first from THIS tree
# (it must be empty or absent).  SDSOLOBOX_KEYSET=n picks the keys.  Exit 0 every row passed, 1 one failed, 2 it could not run.  Stop
# the sandbox with sandbox-fromtree.py <dir> stop.
#
# START-HISTORY:
# 19 Oct 26 dm  Written for S.69 row 1b (evaluation 5A.2b, "the example runner"): gplbld/test-pack-units.py proves the pack equals a
#               build from the SOURCES; this proves the sources are what a built SD actually holds.  The pack is read AS COMMITTED,
#               not regenerated, so a stale pack and a drifted SD are both findings.
# 20 Oct 26 dm  SOLO: the session is a PLAIN session of the one account, sduser (sd-solo, the account password as the first line, read
#               from <dir>/account.pw, never printed), so the VOC compared is the one an agent sees, `newvoc` whole, and a block of a
#               voc:entry chunk that shows both layers is read at its FIRST fence (newvoc's); Core compares SDSYS's, the last.  Group 4
#               (the printed syntax of create.account and modify.account) does not exist: Solo has neither verb.  Its place is taken
#               by the wall messages: the text of the pack's msg:2001, msg:11008 and msg:11029 is what a session that has not typed
#               `admin` is told by `config`, a `copy` into the VOC and `catalog ... global` (msg:11028 is not driven: `deletef` and
#               `syncgcat` print it and neither is run here).
# END-HISTORY
#
# WHAT IT RUNS.  The sandbox's sduser account is built from sdsys/newvoc, and its dictionaries are written by write_install_dicts
# from gplbld/FILES_DICTS.  The pack quotes both.  For each:
#   1. VERBS     every tcl: verb chunk says how the verb dispatches (type, mode, target).  A BASIC program reads the VOC record of the
#                running SD and compares.  A verb the pack names that the VOC does not hold is a row.
#   2. VOC ENTRIES  every voc:entry chunk quotes a shipped S, PA, PH, Q, F, R or X record verbatim; the program compares it with the
#                record in the running account's VOC.
#   3. DICTIONARY ITEMS  every dict:item chunk quotes a shipped item; the program opens the installed dictionary and compares.
#                (In the SDSYS internal session since 20 Oct 26: it opens them by pathname in SDSYS, which the OS switch refuses a
#                plain session with `os` off.  The first run after the switch was red 0 of 74 for exactly that reason.)
#   4. WALL MESSAGES  the three refusals above print the text the pack's message chunks give.
# The expected records are written into a scratch DIRECTORY file (gzpack) with the bytes the pack quotes, so the program compares
# what SD holds with what the pack says, and prints OK or DIFF for each.  A RUN THAT COMPARED NOTHING FAILS: each group must have
# compared as many records as the pack has chunks of that kind, and every id the program was given must have an answer line.

import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "sandbox-fromtree.py")
PACK = os.environ.get("SDPACK_DIR") or os.path.join(SD64, "agent-pack", "pack")      # SDPACK_DIR: a mutated copy, for the selftest
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
passed = failed = 0
ACCOUNT = "sduser"
SECRETS = []                                  # the password read from the sandbox, scrubbed from anything printed


def say(s=""):
    for sec in SECRETS:
        s = s.replace(sec, "<password>")
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
    say("sandbox-pack-examples: CANNOT RUN - " + msg)
    sys.exit(2)


CHUNK = re.compile(r"(?m)^### (\S+)\n> (.*)\n")


def load_pack():
    """({id: body}, {id: the chunk's second line, its meta})"""
    chunks = {}
    metas = {}
    for root, _d, names in os.walk(PACK):
        for n in sorted(names):
            if not n.endswith(".md"):
                continue
            text = open(os.path.join(root, n), encoding="utf-8").read()
            heads = list(CHUNK.finditer(text))
            for i, m in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
                chunks[m.group(1)] = text[m.end():end].strip()
                metas[m.group(1)] = m.group(2)
    return chunks, metas


def fence_body(body):
    """The text inside the first fenced block of a chunk body, or None."""
    m = re.search(r"(?s)^(`{3,})\n(.*?)\n\1$", body, re.M)
    return m.group(2) if m else None


def all_fences(body):
    return [m.group(2) for m in re.finditer(r"(?s)^(`{3,})\n(.*?)\n\1$", body, re.M)]


def unclean(s):
    """The pack writes bytes 128 and up and control characters as \\xNN; this gives them back."""
    return re.sub(r"\\x([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), s)


PROGRAM = r"""program gzpackcheck
   * reads each record of the scratch directory file gzpack and compares it with what the running SD holds
   open 'gzpack' to ex else stop 'GZPACK no gzpack file'
   open 'voc' to voc else stop 'GZPACK no voc'
   select ex to 1
   nv = 0 ; nd = 0 ; nbad = 0
   loop
      readnext id from 1 else exit
      read exp from ex, id else continue
      kind = field(id, '^', 1)
      name = field(id, '^', 2, 99)
      begin case
         case kind = 'verb'
            read act from voc, name else crt 'MISSING ' : id ; continue
            nv += 1
            t = act<1>[1,1]
            if t = 'K' then d = act<4> ; g = act<5> else d = act<2> ; g = act<3>
            got = t : @fm : upcase(d) : @fm : g
            gosub compare
         case kind = 'voc'
            read act from voc, name else crt 'MISSING ' : id ; continue
            nv += 1
            got = act
            gosub compare
         case kind = 'dict'
            dname = field(name, '^', 1)
            item = field(name, '^', 2, 99)
            openpath @sdsys : @ds : dname to dd else crt 'MISSING ' : id : ' (no dictionary ' : dname : ')' ; continue
            read act from dd, item else crt 'MISSING ' : id ; continue
            nd += 1
            * an I-type is compiled when the dictionaries are written: field 15 is the compile stamp and the object code follows it.
            * They differ with every build, so the comparison is of fields 1 to 14, which is the item as a person wrote it.
            got = '' ; want = ''
            for k = 1 to 14
               got<k> = act<k>
               want<k> = exp<k>
            next k
            exp = want
            gosub compare
      end case
   repeat
   crt 'GZPACK DONE verbs-and-voc=' : nv : ' dict=' : nd : ' different=' : nbad
   stop
compare:
   * trailing empty fields are not part of a record
   e1 = exp ; g1 = got
   loop while e1[1] = @fm do e1 = e1[1, len(e1) - 1] repeat
   loop while g1[1] = @fm do g1 = g1[1, len(g1) - 1] repeat
   if e1 = g1 then
      crt 'OK ' : id
   end else
      crt 'DIFF ' : id
      crt '   pack: ' : change(e1, @fm, '|')
      crt '   SD:   ' : change(g1, @fm, '|')
      nbad += 1
   end
   return
end
"""


def read_secret(box, name):
    """<box>/<name>, written 0600 by sandbox-fromtree.py; kept out of anything this suite prints."""
    path = os.path.join(box, name)
    try:
        with open(path) as f:
            pw = f.read().strip()
    except OSError as e:
        bail("cannot read %s: %s" % (path, e))
    if not pw:
        bail("%s is empty" % path)
    if pw not in SECRETS:
        SECRETS.append(pw)
    return pw


def sess(box, cmds, timeout=600):
    """A plain session of sduser on a pipe: the account password, TERM, the commands, OFF.  It has not typed `admin`."""
    conf = os.path.join(box, "sd.conf")
    env = dict(os.environ, SD_CONFIG=conf)
    env.pop("SSH_CONNECTION", None)
    env.pop("SSH_TTY", None)
    body = read_secret(box, "account.pw") + "\nTERM 200,9999\n" + "".join(c + "\n" for c in cmds) + "OFF\n"
    p = subprocess.run([os.path.join(box, "sys", "bin", "sd-solo")], input=body, cwd=os.path.join(box, "sys"), env=env,
                       capture_output=True, text=True, errors="replace", timeout=timeout)
    return ANSI.sub("", p.stdout + p.stderr).split(":TERM 200,9999", 1)[-1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        bail("usage: sandbox-pack-examples.py <dir> [--build]")
    box = os.path.abspath(args[0])
    sysd = os.path.join(box, "sys")
    say("sandbox-pack-examples: sandbox %s" % box)
    say("sandbox-pack-examples: pack    %s" % PACK)
    if "--build" in sys.argv:
        if os.path.exists(box) and os.listdir(box):
            bail("%s is not empty" % box)
        r = subprocess.run([sys.executable, TOOL, box, "all"], capture_output=True, text=True, errors="replace", timeout=900)
        if "[FAIL]" in r.stdout or r.returncode != 0 or "[PASS] THIRD.COMPILE" not in r.stdout:
            bail("the sandbox build did not pass:\n" + r.stdout[-800:])
        say("sandbox-pack-examples: built, bootstrap passed")
    elif not os.path.isfile(os.path.join(sysd, "bin", "sd-solo")):
        bail("%s holds no built sandbox (use --build, or point it at one)" % box)
    subprocess.run([sys.executable, TOOL, box, "start"], capture_output=True, text=True, errors="replace", timeout=120)
    if not os.path.isdir(PACK):
        bail("there is no pack at %s" % PACK)
    chunks, metas = load_pack()

    # what to compare.  The one account's VOC is `newvoc` whole, so a voc:entry chunk that quotes a newvoc record is compared with
    # sduser's VOC (its FIRST fence is newvoc's when the layers differ); a chunk that quotes ONLY a voc_template record is SDSYS's own
    # (the system account, which a person never enters) and is compared in an internal session, which lands in SDSYS.
    expected = {}        # record id in gzpack -> raw text, for sduser's plain session
    expected_sys = {}    # the same, for SDSYS: the voc_template-only records
    n_verb = n_voc = n_dict = n_vocsys = 0
    for cid, body in chunks.items():
        if cid.startswith("tcl:"):
            m = re.search(r"- dispatch `([A-Z]+)`(?: (\S+))?:", body)
            kind = re.search(r"- VOC record `[^`]+`: (type V|a keyword that is also a verb)", body)
            if not m or not kind:
                continue
            typ = "V" if kind.group(1) == "type V" else "K"
            expected["verb^" + cid[4:]] = "%s\n%s\n%s" % (typ, m.group(1), m.group(2) or "")
            n_verb += 1
        elif cid.startswith("voc:entry:"):
            fences = all_fences(body)
            if fences:
                in_newvoc = "src=sdsys/newvoc/" in metas.get(cid, "")
                if in_newvoc:
                    expected["voc^" + cid[len("voc:entry:"):]] = unclean(fences[0])
                    n_voc += 1
                else:
                    expected_sys["voc^" + cid[len("voc:entry:"):]] = unclean(fences[-1])
                    n_vocsys += 1
        elif cid.startswith("dict:item:"):
            raw = fence_body(body)
            dname, item = cid[len("dict:item:"):].split(":", 1)
            if raw is not None:
                # The dictionaries are read by PATHNAME (openpath @sdsys:@ds:name), and that path is in SDSYS, outside sduser's own
                # directory: since the OS switch (20 Oct 26) a plain session with `os` off is refused it (3035), so the comparison is
                # made where the kernel trusts the program, in the SDSYS internal session. The files are the same whoever reads them.
                expected_sys["dict^%s^%s" % (dname, item)] = unclean(raw)
                n_dict += 1
    say("sandbox-pack-examples: the pack gives %d verbs, %d shipped VOC records (+ %d of SDSYS's own) and %d shipped dictionary items to compare" % (
        n_verb, n_voc, n_vocsys, n_dict))
    row("the pack has something to compare (>= 90 verbs, >= 20 VOC records, >= 40 dictionary items)", n_verb >= 90 and n_voc >= 20 and n_dict >= 40,
        "%d / %d / %d" % (n_verb, n_voc, n_dict))

    # the scratch directory file, written with the bytes the pack quotes
    acct_dir = os.path.join(sysd, "user_accounts", ACCOUNT)

    def comparison(label, run, where, exp):
        """Make gzpack in `where` (an account directory) through `run` (a function of a command list), put the program in its bp, run it.
        Returns (output lines, raw output)."""
        run(["DELETE.FILE gzpack NO.QUERY", "CREATE.FILE gzpack DIRECTORY"])
        gz = os.path.join(where, "gzpack")
        if not os.path.isdir(gz):
            bail("CREATE.FILE gzpack DIRECTORY made no directory at %s" % gz)
        for rid, text in exp.items():
            with open(os.path.join(gz, rid), "wb") as f:
                f.write(text.encode("latin-1", "replace"))
        with open(os.path.join(where, "bp", "gzpackcheck"), "w") as f:
            f.write(PROGRAM)
        say("sandbox-pack-examples: [%s] wrote %d expected records to %s and the program bp/gzpackcheck" % (label, len(exp), gz))
        out = run(["BASIC bp gzpackcheck", "RUN bp gzpackcheck", "DELETE.FILE gzpack NO.QUERY"])
        lines = [l.strip() for l in out.splitlines()]
        if not any(l == "Compiled 1 program(s) with no errors" for l in lines):
            bail("the comparison program did not compile in %s:\n%s" % (label, "\n".join(lines[:12])))
        for p in (os.path.join(where, "bp", "gzpackcheck"), os.path.join(where, "bp.out", "gzpackcheck")):
            if os.path.exists(p):
                os.remove(p)
        shutil.rmtree(gz, ignore_errors=True)
        return lines, out

    def internal(cmds):
        """An internal session, which lands in SDSYS: sandbox-fromtree.py's `sess` writes the one-shot marker."""
        r = subprocess.run([sys.executable, TOOL, box, "sess", sysd] + cmds, capture_output=True, text=True, errors="replace", timeout=600)
        return ANSI.sub("", r.stdout + r.stderr).split(":TERM 200,9999", 1)[-1]

    lines, out = comparison("sduser's plain session", lambda c: sess(box, c, timeout=600), acct_dir, expected)
    ok_ids = {l[3:] for l in lines if l.startswith("OK ")}
    diff = [l[5:] for l in lines if l.startswith("DIFF ")]
    missing = [l[8:] for l in lines if l.startswith("MISSING ")]
    if "--show" in sys.argv:          # what differed, field marks shown as |
        say("\n".join(l for l in out.splitlines() if l.startswith(("DIFF", "   pack:", "   SD:", "MISSING"))))
    done = next((l for l in lines if l.startswith("GZPACK DONE")), None)
    say("sandbox-pack-examples: %s" % (done or "the program printed no GZPACK DONE line"))
    if expected_sys:
        lines_s, out_s = comparison("SDSYS, an internal session", internal, sysd, expected_sys)
        ok_ids |= {"sys:" + l[3:] for l in lines_s if l.startswith("OK ")}
        diff += ["sys:" + l[5:] for l in lines_s if l.startswith("DIFF ")]
        missing += ["sys:" + l[8:] for l in lines_s if l.startswith("MISSING ")]
        if "--show" in sys.argv:
            say("\n".join(l for l in out_s.splitlines() if l.startswith(("DIFF", "   pack:", "   SD:", "MISSING"))))
        say("sandbox-pack-examples: %s" % (next((l for l in lines_s if l.startswith("GZPACK DONE")), None) or "the SDSYS program printed no GZPACK DONE line"))

    def group(prefix, label, want_n, table=None, pre=""):
        ids = [i for i in (table if table is not None else expected) if i.startswith(prefix)]
        got = [i for i in ids if pre + i in ok_ids]
        bad = [i for i in ids if pre + i in diff]
        gone = [i for i in ids if any(pre + i in m for m in missing)]
        row("%s: the running SD holds what the pack says (%d of %d compared equal)" % (label, len(got), want_n),
            want_n > 0 and len(got) == want_n and not bad and not gone,
            "different: %s; missing: %s" % (bad[:4], gone[:4]))

    group("verb^", "VERBS (type, dispatch mode and target of every tcl: verb chunk, in sduser's VOC)", n_verb)
    group("voc^", "VOC RECORDS (every voc:entry chunk that quotes newvoc, against the record in sduser's VOC)", n_voc)
    group("dict^", "DICTIONARY ITEMS (every dict:item chunk against the installed dictionaries, read in the SDSYS internal session)", n_dict,
          table=expected_sys, pre="sys:")
    if expected_sys:
        group("voc^", "SDSYS'S OWN VOC RECORDS (every voc:entry chunk that quotes only voc_template, against SDSYS's VOC)", n_vocsys, table=expected_sys, pre="sys:")

    # the wall messages: what a session that has not typed `admin` is told is the text of the pack's message chunks
    probes = (("2001", "config"), ("11008", "copy from bp to voc gzwall"), ("11029", "catalog bp gzwall global"))
    with open(os.path.join(acct_dir, "bp", "gzwall"), "w") as f:
        f.write("program gzwall\n   crt 'gzwall'\nend\n")
    for num, cmd in probes:
        body = chunks.get("msg:" + num)
        fences = all_fences(body) if body else []
        want = [l.rstrip() for l in unclean(fences[0]).splitlines() if l.strip()] if fences else []
        printed = [l.rstrip() for l in sess(box, ["BASIC bp gzwall", cmd], timeout=120).splitlines() if l.strip() and not l.startswith(":")]
        row("`%s` is refused with the %d line(s) of msg:%s in the pack" % (cmd.split(" ")[0] + (" ..." if " " in cmd else ""), len(want), num),
            bool(want) and want[0] in printed,
            "pack %r, printed %r" % (want[:1], printed[-3:]))
    for p in (os.path.join(acct_dir, "bp", "gzwall"), os.path.join(acct_dir, "bp.out", "gzwall")):
        if os.path.exists(p):
            os.remove(p)
    say("\nsandbox-pack-examples: %d passed, %d failed" % (passed, failed))
    sys.exit(0 if failed == 0 and passed > 0 else 1)


if __name__ == "__main__":
    main()
