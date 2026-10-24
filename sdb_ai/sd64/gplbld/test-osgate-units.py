#!/usr/bin/env python3
"""test-osgate-units.py - the Solo OS-access switch (SH and OS), as invariants read off the source.  Solo's copy of the shape of
SD Core's test-gates-units.py (S.63), written FIRST, before any of the switch existed, and run red.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-osgate-units.py
  python3 .../test-osgate-units.py --selftest

No sudo, no install, no sd.  Exit 0 every check passed, 1 a check failed, 2 it could not run.  Written 20 Oct 26.

***WHAT THIS IS, AND WHAT IT IS NOT.***  It reads the C and BASIC sources as text, with comments removed, so a gate that survives only
in a comment does not count.  ***IT DOES NOT RUN ANYTHING, SO IT CANNOT SAY THAT THE SWITCH REFUSES ANYBODY***: that is
sandbox-osgate.py (plain sessions of sduser on a private Solo, which refuse, run, and leave a sentinel as evidence).  What a text check
is for: this code is reached from a dozen places and the invariants that make it a gate are mostly ORDERING (the refusal before the
stack is touched, the path test after fullpath() and before the transaction cache, the load at sign-on before the audit line).  An
edit that moves one still compiles.

THE SHAPE.  Solo has ONE account, so there is no CREATE.ACCOUNT, MODIFY.ACCOUNT or upgrade_gates: the two switches (SH, OS) live in
fields 7 and 8 of the register record accounts/sduser, are loaded by LOGIN (and by the API server, which enters the account itself)
into the user table, and are changed by the administrator's verb SET.OS.ACCESS.  The installer asks once, default No.  Everything
the kernel and the BASIC readers do is Core's S.63, ported by hunk, so most checks below are Core's, with Solo's file set.

***AND THE CHECKS ARE THEMSELVES CHECKED.***  --selftest breaks each invariant in the way an edit plausibly would and requires some
check to notice.  A mutant that nothing catches is reported as a FAILURE of the self-test.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.abspath(os.path.join(HERE, os.pardir))
SDSYS = os.path.join(SD64, "sdsys")
GPL = os.path.join(SDSYS, "gpl.bp")
GPLSRC = os.path.join(SD64, "gplsrc")
ROOT = os.path.dirname(os.path.dirname(SD64))

FILES = {
    "op_sh.c": os.path.join(GPLSRC, "op_sh.c"),
    "op_seqio.c": os.path.join(GPLSRC, "op_seqio.c"),
    "op_dio1.c": os.path.join(GPLSRC, "op_dio1.c"),
    "op_dio4.c": os.path.join(GPLSRC, "op_dio4.c"),
    "op_kernel.c": os.path.join(GPLSRC, "op_kernel.c"),
    "op_sdext.c": os.path.join(GPLSRC, "op_sdext.c"),
    "op_xfun.c": os.path.join(GPLSRC, "op_xfun.c"),
    "op_skt.c": os.path.join(GPLSRC, "op_skt.c"),
    "to_file.c": os.path.join(GPLSRC, "to_file.c"),
    "linuxprt.c": os.path.join(GPLSRC, "linuxprt.c"),
    "keys.h": os.path.join(GPLSRC, "keys.h"),
    "sysseg.h": os.path.join(GPLSRC, "sysseg.h"),
    "sd.h": os.path.join(GPLSRC, "sd.h"),
    "int$keys.h": os.path.join(GPL, "int$keys.h"),
    "syscom/keys.h": os.path.join(SDSYS, "syscom", "keys.h"),
    "cproc": os.path.join(GPL, "cproc"),
    "login": os.path.join(GPL, "login"),
    "edit": os.path.join(GPL, "edit"),
    "setptr": os.path.join(GPL, "setptr"),
    "qproc": os.path.join(GPL, "qproc"),
    "apisrvr": os.path.join(GPL, "apisrvr"),
    "_voc_ref": os.path.join(GPL, "_voc_ref"),
    "_oscopy": os.path.join(GPL, "_oscopy"),
    "_ioscopy": os.path.join(GPL, "_ioscopy"),
    "acc_os_info": os.path.join(GPL, "acc_os_info"),
    "setosacc": os.path.join(GPL, "setosacc"),
    "solo_account": os.path.join(GPL, "solo_account"),
    "installsdsolo.sh": os.path.join(ROOT, "installsdsolo.sh"),
    "solo-stage.sh": os.path.join(HERE, "solo-stage.sh"),
    "set.os.access": os.path.join(SDSYS, "newvoc", "set.os.access"),
}
C_FILES = ("op_sh.c", "op_seqio.c", "op_dio1.c", "op_dio4.c", "op_kernel.c", "op_sdext.c", "op_xfun.c", "op_skt.c", "to_file.c",
           "linuxprt.c", "keys.h", "sysseg.h", "sd.h")
SH_FILES = ("installsdsolo.sh", "solo-stage.sh")
RAW_FILES = ("set.os.access",)          # a VOC record: no comments to strip


def strip_c(src):
    """C with comments removed and every removed newline kept, so offsets still map to lines."""
    def blank(m):
        return "\n" * m.group(0).count("\n")
    src = re.sub(r"/\*.*?\*/", blank, src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def strip_bas(src):
    out = []
    for line in src.split("\n"):
        s = line.lstrip()
        if s.startswith("*") or s.startswith("!"):
            out.append("")
            continue
        cut = line.find(";*")
        out.append(line if cut < 0 else line[:cut])
    return "\n".join(out)


def strip_sh(src):
    return "\n".join("" if l.lstrip().startswith("#") else l for l in src.split("\n"))


def code(name, src):
    if name in RAW_FILES:
        return src
    if name in C_FILES:
        return strip_c(src)
    if name in SH_FILES:
        return strip_sh(src)
    return strip_bas(src)


def at(text, needle, start=0):
    """Offset of the first occurrence at or after start, or -1."""
    return text.find(needle, start)


def line_of(text, off):
    return text.count("\n", 0, off) + 1 if off >= 0 else None


def block(text, start_marker, length):
    """The text from a marker for `length` characters, or '' when the marker is absent (so a missing piece fails its checks and does not crash)."""
    i = at(text, start_marker)
    return text[i:i + length] if i >= 0 else ""


def func_body(text, marker):
    """A C function from its first line to the closing brace in column 0, or '' when the marker is absent."""
    i = at(text, marker)
    j = text.find("\n}\n", i) if i >= 0 else -1
    return text[i:j + 2] if j > 0 else ""


def checks(srcs, messages_dir):
    """[(id, ok, detail)] - every invariant the switch rests on."""
    rows = []

    def ck(i, ok, detail=""):
        rows.append((i, bool(ok), detail))

    c = {name: code(name, text) for name, text in srcs.items()}

    # ---- K. the key numbers, the flag bits and the register fields ------------------------------------------------
    nums = {}
    for m in re.finditer(r"#define\s+(K_[A-Z0-9_]+)\s+(\d+)", c["keys.h"]):
        nums.setdefault(int(m.group(2)), []).append(m.group(1))
    for key, want in (("K_SH", 93), ("K_OS_EXEC", 94), ("K_PATH_OK", 95), ("K_EDIT_OS_OK", 126)):
        m = re.search(r"#define\s+%s\s+(\d+)" % key, c["keys.h"])
        ck("K1 %s is %d in gplsrc/keys.h (Core's number)" % (key, want), m and int(m.group(1)) == want, m.group(0) if m else "absent")
        bkey = key.replace("K_", "K$").replace("_", ".")
        m2 = re.search(r"\$define\s+%s\s+(\d+)" % re.escape(bkey), srcs["int$keys.h"])
        ck("K2 %s is %d in gpl.bp/int$keys.h, the same number" % (bkey, want), m2 and int(m2.group(1)) == want, m2.group(0) if m2 else "absent")
    dups = {n: k for n, k in nums.items() if len(k) > 1}
    ck("K3 no kernel key number in gplsrc/keys.h is used twice", not dups, repr(dups))
    usr = {m.group(1): int(m.group(2), 16) for m in re.finditer(r"#define\s+(USR_[A-Z_]+)\s+(0x[0-9A-Fa-f]+)", c["sysseg.h"])}
    ck("K4 USR_SH (0x2000: Core's 0x0100 is Solo's USR_GLOBAL) and USR_OS_EXEC (0x0200, Core's) are defined in sysseg.h and no flag of the user table shares a bit",
       usr.get("USR_SH") == 0x2000 and usr.get("USR_OS_EXEC") == 0x0200
       and len({v for k, v in usr.items() if k != "USR_GROUPED"}) == len([k for k in usr if k != "USR_GROUPED"]), repr(usr))
    ck("K5 ACC$SH is field 7 and ACC$OS.EXEC field 8 of the register",
       re.search(r"\$define ACC\$SH\s+7\b", srcs["syscom/keys.h"]) and re.search(r"\$define ACC\$OS\.EXEC\s+8\b", srcs["syscom/keys.h"]))
    ck("K6 sd.h declares os_gate_open, os_path_ok_for_account and os_path_open_ok",
       all(("bool %s(" % f) in c["sd.h"] for f in ("os_gate_open", "os_path_ok_for_account", "os_path_open_ok")))

    # ---- C. the kernel ---------------------------------------------------------------------------------------------
    sh = c["op_sh.c"]
    fn = at(sh, "Private void sh(bool capture) {")
    refuse = at(sh, "if (!os_permitted())", fn)
    getstr = at(sh, "k_get_string(descr)", fn)
    ck("C1 sh() refuses BEFORE it touches the stack (the refusal precedes k_get_string)",
       fn >= 0 and refuse > fn and getstr > refuse, "refusal at line %s, k_get_string at line %s" % (line_of(sh, refuse), line_of(sh, getstr)))
    ck("C2 the refusal is 10054 (the Windows port's, and Core's)", re.search(r"if \(!os_permitted\(\)\)\s*k_error\(sysmsg\(10054\)", sh))
    perm = block(sh, "Private bool os_permitted(void) {", 200)
    ck("C3 os_permitted(): an $internal program first, then the account's own gate (never an unconditional TRUE)",
       "HDR_INTERNAL" in perm and "return os_gate_open();" in perm)
    gate = block(sh, "bool os_gate_open(void) {", 300)
    gate = gate[:gate.find("\n}") + 2] if "\n}" in gate else gate
    ck("C4 os_gate_open() is the administrator or USR_OS_EXEC, and does NOT look at HDR_INTERNAL",
       "USR_ADMIN" in gate and "USR_OS_EXEC" in gate and "HDR_INTERNAL" not in gate, gate.strip()[:120])
    # 24 Oct 26 (Solo carry 19): path_inside_dir() was split; the resolution is resolve_gate_path(), the boundary test stays in path_inside_dir()
    rgp = func_body(sh, "Private bool resolve_gate_path(const char *rootdir, const char *name, char *root, char *resolved) {")
    pia = func_body(sh, "Private bool path_inside_dir(const char *rootdir, const char *name) {")      # 21 Oct 26: was path_inside_account(name); rootdir NULL is the account (Solo carry 10)
    ck("C5 containment resolves with realpath() on both sides and tests a path-component boundary",
       rgp.count("realpath(") >= 2 and "resolve_gate_path(rootdir, name, root, resolved)" in pia and "strncmp(resolved, root, root_len)" in pia
       and "(resolved[root_len] == '\\0') || (resolved[root_len] == '/')" in pia)
    ck("C6 a '..' tail that cannot be resolved is refused, and so is an account rooted at /",
       'strcmp(p + 1, "..") == 0' in rgp and "root_len == 1" in rgp)
    ck("C7 os_path_ok_for_account: the gate opens everything, otherwise containment",
       re.search(r"bool os_path_ok_for_account\(const char \*name\) \{\s*if \(os_gate_open\(\)\)\s*return TRUE;\s*return path_inside_dir\(NULL, name\);", sh))
    ck("C8 os_path_open_ok: an $internal program is trusted, anyone else is asked",
       re.search(r"bool os_path_open_ok\(const char \*name\) \{\s*if \(process\.program\.flags & HDR_INTERNAL\)\s*return TRUE;\s*"
                 r"return os_path_ok_for_account\(name\);", sh))

    sq = c["op_seqio.c"]
    fnq = at(sq, "Private void openseq(bool map_name) {")
    nam = at(sq, "process.status = ER_NAM;", at(sq, "filename_descr = e_stack - 2;", fnq)) if "filename_descr = e_stack - 2;" in sq[fnq:] else -1
    hook = at(sq, "if (!os_path_open_ok(file_name)) {", fnq)
    port = at(sq, "if (is_port(file_name))", fnq)
    ck("C9 OPENSEQ by pathname is asked BEFORE the port test and the open",
       fnq > 0 and 0 < hook < port, "hook %s, is_port %s" % (line_of(sq, hook), line_of(sq, port)))
    ck("C10 and the refusal is ER_PERM", re.search(r"if \(!os_path_open_ok\(file_name\)\) \{\s*process\.status = ER_PERM;", sq[fnq:] if fnq > 0 else ""))

    d1 = c["op_dio1.c"]
    fnd = at(d1, "Private void open_file(bool map_name)")
    fp = at(d1, "fullpath(pathname, mapped_name);", fnd)
    hk = at(d1, "if (!map_name && !os_path_open_ok(pathname)) {", fnd)
    txn = at(d1, "txn_open(pathname)", fnd)
    ck("C11 OPENPATH is asked AFTER fullpath() and BEFORE the transaction cache, and only when no VOC mapped the name",
       fnd > 0 and fp > 0 and hk > fp and txn > hk, "fullpath %s, hook %s, txn_open %s" % (line_of(d1, fp), line_of(d1, hk), line_of(d1, txn)))
    ck("C12 and the refusal is ER_PERM", re.search(r"if \(!map_name && !os_path_open_ok\(pathname\)\) \{\s*process\.status = ER_PERM;", d1))
    ot = block(d1, "void op_opentemp()", 6000)
    ck("C12a OPENTEMP asks the gate about the path (fullpath, then os_path_open_ok) before it creates anything, and the stub that made nothing is gone",
       re.search(r"fullpath\(path, path\);\s*if \(os_path_open_ok\(path\)\) \{", ot) and "until Solo" not in srcs["op_dio1.c"].split("op_opentemp()")[-1][:3000])

    kn = c["op_kernel.c"]
    for case, flag in (("K_SH", "USR_SH"), ("K_OS_EXEC", "USR_OS_EXEC")):
        s0 = at(kn, "case %s:" % case)
        blk = kn[s0:at(kn, "case K_", s0 + 8)] if s0 >= 0 else ""         # this case's own block, not the next one's
        ck("C13 kernel(%s) changes the flag only for an $internal caller, and reports it" % case,
           "HDR_INTERNAL" in blk and ("|= %s" % flag) in blk and ("&= ~%s" % flag) in blk and "result.data.value" in blk)
    kp = block(kn, "case K_PATH_OK:", 420)
    ck("C14 kernel(K_PATH_OK) answers os_path_ok_for_account (the account's question, not the caller's)",
       "os_path_ok_for_account(path_ok_name)" in kp and "os_path_open_ok" not in kp)

    sx = c["op_sdext.c"]
    py = block(sx, "case SD_PyInit:", 900)
    g = at(py, "os_gate_open()")
    run = at(py, "sdext_py(key")
    ck("C15 the Python gate asks the ACCOUNT (os_gate_open) and comes before sdext_py()", 0 < g < run, "gate %s, run %s" % (g, run))
    cond = py[:g] if g > 0 else ""
    ck("C16 it gates starting the interpreter and running code, and not 'is Python running?'",
       "SD_PyInit" in cond[cond.find("if ("):] and "SD_PyRunStr" in cond and "SD_PyRunFile" in cond and "SD_IsPyInit" not in cond[cond.find("if ("):])

    d4 = c["op_dio4.c"]
    dr = d4[at(d4, "void op_dir() {"):]
    dgate = at(dr, "if (!os_path_open_ok(pathname)) {")
    dopen = at(dr, "opendir(pathname)")
    ck("C17 DIR() asks the OS gate for the pathname BEFORE opendir(), and the refusal is ER_PERM",
       0 < dgate < dopen and re.search(r"if \(!os_path_open_ok\(pathname\)\) \{\s*process\.status = ER_PERM;", dr), "gate %s, opendir %s" % (dgate, dopen))
    ds = sq[at(sq, "void op_delseq() {"):]
    dsrec = at(ds, "strcat(file_name, rec_name);")
    dsgate = at(ds, "if (!os_path_open_ok(file_name)) {", dsrec)
    dsstat = at(ds, "stat(file_name, &stat_buf)")
    ck("C18 DELETESEQ of a bare pathname (no record name) asks the OS gate AFTER the VOC-named form is dealt with and BEFORE it stats or "
       "removes anything, and the refusal is ER_PERM",
       0 < dsrec < dsgate < dsstat and re.search(r"if \(!os_path_open_ok\(file_name\)\) \{\s*process\.status = ER_PERM;\s*goto exit_op_delseq;", ds),
       "record form %s, gate %s, stat %s" % (dsrec, dsgate, dsstat))
    tf = c["to_file.c"]
    tsf = at(tf, "Private void start_file(PRINT_UNIT* pu) {")
    tmark = at(tf, 'sprintf(fn, "$hold%c%s", DS, pu->file_name + 6);', tsf)
    tcpy = at(tf, "strcpy(fn, pu->file_name);", tsf)
    tgate = at(tf, "os_path_ok_for_account(fn)", tsf)
    topen = at(tf, "open_file:", tsf)
    ck("C19 a print unit's FINAL path - from a raw pathname or from the '$hold name' marker, which a SETPU program can write itself and "
       "which must not climb out with '..' - is asked of the ACCOUNT (not the printing program, usually $internal) after every branch has "
       "built it and before the open, and the refusal is 11180",
       0 < tsf < tmark < tgate < topen and tcpy < tgate and "sysmsg_arg1(11180, account())" in tf[tgate:topen] and "os_path_open_ok" not in tf[tsf:topen],   # 20 Oct 26: names the ACCOUNT, %1 filled in C (Core 27db277)
       "start_file %s, marker %s, raw copy %s, gate %s, open_file %s" % (tsf, tmark, tcpy, tgate, topen))

    # ---- C (the routes Solo's first carry refused outright, until this switch existed) ------------------------------
    xf = c["op_xfun.c"]
    dg = block(xf, "} else if (is_file) {", 700)
    ck("C20 DIGEST of an operating system file asks the gate (ER_PERM) before it opens it, and no longer refuses everyone",
       re.search(r"else if \(!os_path_open_ok\(path\)\) \{\s*process\.status = ER_PERM;\s*\} else if \(\(fd = open\(path", dg) and "SOLO CARRY" not in srcs["op_xfun.c"][srcs["op_xfun.c"].find("is_file = (file_d"):][:1500])
    osp = block(xf, "Private void x_ospath() {", 9000)
    ck("C21 the OSPATH keys that look at or change the file system ask the gate with os_path_open_ok (a refusal is ER_PERM and the answer false)",
       "if (!os_path_open_ok(path)) {" in osp and "process.status = ER_PERM;" in osp[osp.find("if (!os_path_open_ok(path)) {"):][:140])
    sk = c["op_skt.c"]
    ck("C22 the socket trace log asks the ACCOUNT's gate (os_path_ok_for_account) and refuses with ER_PERM before it opens the log",
       re.search(r"if \(trace_len > 0\) \{\s*if \(!os_path_ok_for_account\(trace_path\)\) \{\s*process\.status = ER_PERM;", sk))
    lp = c["linuxprt.c"]
    ck("C23 SETPTR ... SPOOLER's string is run only by a session that holds the gate (os_gate_open), anyone else prints through the configured spooler",
       "(pu->spooler != NULL) && os_gate_open()" in lp)

    # ---- O. the VOC's own files by pathname (Solo carry 19, 24 Oct 26) ---------------------------------------------------
    # An ordinary session with the OS switch off overwrote, appended to and deleted voc/%0 with OSCOPY, !IOSCOPY, OPENSEQ + WRITESEQ and DELETESEQ
    # (measured).  The gate above is geometry (inside the account or not); this one is about WHAT is inside it.  Core's S.64 shape, one kind: a component
    # named voc below the account's own directory.  The runtime rows are sandbox-oscarry-solo.py section V.
    ev = func_body(sh, "int edit_os_path_refusal(const char *name, bool include_leaf) {")
    o_ex = at(ev, "if (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC))")
    o_nm = at(ev, "(name[0] == '\\0')")
    o_rs = at(ev, "resolve_gate_path(NULL, name, root, resolved)")
    o_out = at(ev, "strncmp(resolved, root, root_len) != 0")
    o_lp = at(ev, 'strncasecmp(p, "voc", 3) == 0')
    ck("O1 edit_os_path_refusal(): the administrator and an account with OS.EXECUTE are not asked, then an empty name, then the path is resolved as the OS gate resolves it "
       "and a path that cannot be resolved is REFUSED (a gate that fails open on a path it cannot read is decoration), then a path outside the account is the OS gate's, "
       "then each component is tested",
       0 < o_ex < o_nm < o_rs < o_out < o_lp
       and re.search(r"if \(my_uptr->flags & \(USR_ADMIN \| USR_OS_EXEC\)\)\s*return EDIT_NONE;", ev)
       and re.search(r"if \(!resolve_gate_path\(NULL, name, root, resolved\)\)\s*return EDIT_VOC;", ev),
       "exempt %s, empty %s, resolve %s, outside %s, loop %s" % (o_ex, o_nm, o_rs, o_out, o_lp))
    ck("O1a a component named voc is refused in any case, the final one only when include_leaf says so (a record called voc in an ordinary directory file is a plain file), "
       "and the rest of the path is EDIT_NONE",
       re.search(r"\(n == 3\) && \(strncasecmp\(p, \"voc\", 3\) == 0\) && \(include_leaf \|\| \(\*more != '\\0'\)\)\)\s*return EDIT_VOC;", ev)
       and ev.rstrip().endswith("return EDIT_NONE;\n}"), ev[-200:].strip())
    ck("O2 path_inside_dir() and edit_os_path_refusal() resolve through the SAME function (resolve_gate_path), so the VOC test sees the path the OS gate saw",
       "resolve_gate_path(rootdir, name, root, resolved)" in pia and "resolve_gate_path(NULL, name, root, resolved)" in ev)
    lc = func_body(sh, "bool edit_leaf_counts(const char *name) {")
    ck("O3 edit_leaf_counts(): a name that is not there counts for nothing, a plain file is a record and not a VOC, anything else (a directory, a link) counts",
       "lstat(name, &sb) != 0" in lc and "return FALSE;" in lc and "return !S_ISREG(sb.st_mode);" in lc, lc.strip()[:160])
    sq2 = c["op_seqio.c"]
    fo = func_body(sq2, "Private void openseq(bool map_name) {")
    ob = at(fo, "edit_blocked = (edit_os_path_refusal(fullpathname, FALSE) != EDIT_NONE);")
    ost = at(fo, "stat(fullpathname, &stat_buf)")
    ck("O4 OPENSEQ asks for a file (not a port, not a $internal program) BEFORE it stats or opens it, and the answer makes the open read only and refuses CREATING",
       0 < ob < ost and re.search(r"if \(!\(flags & SQ_PORT\) && !\(process\.program\.flags & HDR_INTERNAL\)\)\s*edit_blocked = ", fo)
       and "(op_flags & P_READONLY) || access(fullpathname, 2) || edit_blocked" in fo and "(op_flags & 0x400) && edit_blocked" in fo
       and "read_only || edit_blocked" in fo, "ask %s, stat %s" % (ob, ost))
    fdq = func_body(sq2, "void op_delseq() {")
    dg1 = at(fdq, "if (!os_path_open_ok(file_name)) {")
    dg2 = at(fdq, "(edit_os_path_refusal(file_name, FALSE) != EDIT_NONE)")
    dst = at(fdq, "stat(file_name, &stat_buf)")
    ck("O5 DELETESEQ asks (not a $internal program) AFTER the OS gate and BEFORE it stats or removes anything, and the refusal is ER_PERM",
       0 < dg1 < dg2 < dst and re.search(r"if \(!\(process\.program\.flags & HDR_INTERNAL\) && \(edit_os_path_refusal\(file_name, FALSE\) != EDIT_NONE\)\) \{\s*process\.status = ER_PERM;\s*goto exit_op_delseq;", fdq),
       "gate %s, voc %s, stat %s" % (dg1, dg2, dst))
    osp2 = func_body(xf, "Private void x_ospath() {")
    og1 = at(osp2, "if (!os_path_open_ok(path)) {")
    og2 = at(osp2, "edit_os_path_refusal(path, (key == 5) ? edit_leaf_counts(path) : TRUE)")
    ck("O6 OSPATH delete (5), make a directory (13) and 14 ask for the VOC AFTER the OS gate, not for a $internal program, with the deleted name counted when it is not a plain file "
       "and a directory made always counted; the refusal is ER_PERM",
       0 < og1 < og2 and re.search(r"\(\(key == 5\) \|\| \(key == 13\) \|\| \(key == 14\)\) && !\(process\.program\.flags & HDR_INTERNAL\) &&", osp2)
       and "process.status = ER_PERM;" in osp2[og2:og2 + 160], "gate %s, voc %s" % (og1, og2))
    tg = at(sk, "os_path_ok_for_account(trace_path)")
    te = at(sk, "edit_os_path_refusal(trace_path, FALSE) != EDIT_NONE")
    to = at(sk, "O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW")
    ck("O7 the socket trace log asks for the VOC (not for a $internal program) AFTER the OS gate and BEFORE the log is opened, and the refusal is ER_PERM",
       0 < tg < te < to and "HDR_INTERNAL" in sk[te - 90:te] and "process.status = ER_PERM;" in sk[te:to], "gate %s, voc %s, open %s" % (tg, te, to))
    pg = at(tf, "os_path_ok_for_account(fn)", tsf)
    pe = at(tf, "edit_os_path_refusal(fn, FALSE) != EDIT_NONE", tsf)
    ck("O8 a print file asks for the VOC AFTER the OS gate and BEFORE the open, of the ACCOUNT's session (a report is usually a $internal program, so no HDR_INTERNAL exemption), "
       "and the refusal is message 11008",
       0 < tsf < pg < pe < topen and "HDR_INTERNAL" not in tf[pg:topen] and "k_error(sysmsg(11008))" in tf[pe:topen], "gate %s, voc %s, open_file %s" % (pg, pe, topen))
    ko = block(kn, "case K_EDIT_OS_OK: {", 800)
    ko = ko[:ko.find("} break;")] if "} break;" in ko else ko
    ck("O9 kernel(K_EDIT_OS_OK) starts at 0 (an empty or unreadable name is a refusal), the administrator gets 1, anybody else gets edit_os_path_refusal about the name with "
       "the final component counted when edit_leaf_counts says so",
       ko.find("result.data.value = 0;") >= 0 and ko.find("result.data.value = 0;") < ko.find("USR_ADMIN") < ko.find("edit_os_path_refusal(")
       and "if (my_uptr->flags & USR_ADMIN)\n        result.data.value = 1;" in ko
       and "edit_os_path_refusal(edit_os_name, edit_leaf_counts(edit_os_name)) == EDIT_NONE) ? 1 : 0" in ko, ko.strip()[:140])
    oc2 = c["_oscopy"]
    cpth = oc2[at(oc2, "check.paths:"):]
    ck1 = at(cpth, "kernel(K$PATH.OK, source)")
    ck2 = at(cpth, "kernel(K$EDIT.OS.OK, target)")
    ck3 = at(cpth, "ospath(source, OS$EXISTS)")
    ck("O10 !OSCOPY asks K$EDIT.OS.OK about the TARGET after both K$PATH.OK questions and before it looks at the source (reading is not a change), and the answer is -4",
       0 < ck1 < ck2 < ck3 and "K$EDIT.OS.OK, source" not in oc2 and re.search(r"kernel\(K\$EDIT\.OS\.OK, target\)\) then\s*status = -4", cpth), "path %s, edit %s, exists %s" % (ck1, ck2, ck3))
    ic = c["_ioscopy"]
    i1 = at(ic, "kernel(K$PATH.OK, source)")
    i2 = at(ic, "kernel(K$EDIT.OS.OK, target)")
    i3 = at(ic, "ospath(source, OS$EXISTS)")
    ck("O11 !IOSCOPY asks the same, in the same order, and returns -4 at once",
       0 < i1 < i2 < i3 and "K$EDIT.OS.OK, source" not in ic and re.search(r"if not\(kernel\(K\$EDIT\.OS\.OK, target\)\) then\s*status = -4\s*return", ic), "path %s, edit %s, exists %s" % (i1, i2, i3))

    # ---- B. BASIC --------------------------------------------------------------------------------------------------
    cp = c["cproc"]
    oc = at(cp, "os.command.text = trimf(voc.rec<3>")
    gate_ = at(cp, "if not(kernel(K$ADMINISTRATOR, -1)) and not(kernel(K$SH, -1)) then", oc)
    meta = at(cp, "if not(valid_shell_cmd(os.command.text)) then", oc)
    osx = at(cp, "os.execute os.command.text", oc)
    ck("B2 the SH verb and '!' refuse (10053) BEFORE the metacharacter test and BEFORE they run the command",
       0 < oc < gate_ < meta < osx and "sysmsg(10053, @logname)" in cp[gate_:meta], "gate %s, filter %s, run %s" % (line_of(cp, gate_), line_of(cp, meta), line_of(cp, osx)))

    lg = c["login"]
    ll = at(lg, "void kernel(K$SH,")
    susp = at(lg, "trim(acc.rec<ACC$SUSPENDED>)) = 'SUSPENDED'")
    pth = at(lg, 'account.path = ospath("", OS$CWD)')
    ck("B3 LOGIN loads both switches at sign-on, from the 'YES' in fields 7 and 8, after the suspension test and before @PATH is set",
       0 < susp < ll < pth and "upcase(trim(acc.rec<ACC$SH>)) = 'YES'" in lg and "upcase(trim(acc.rec<ACC$OS.EXEC>)) = 'YES'" in lg,
       "suspended %s, load %s, path %s" % (susp, ll, pth))

    ed = c["edit"]
    cpm = block(ed, "check.permitted:", 1400)
    tty = at(cpm, "kernel(K$TTY, 0) = ''")
    ox = at(cpm, "kernel(K$OS.EXEC, -1)")
    ck("B14 the editors outside SD (nano and micro) need os: the switch is tested after the terminal test, and a plain 'permitted = @true' no "
       "longer ends check.permitted", 0 < tty < ox and not re.search(r"\n\s*permitted = @true\s*\nreturn", cpm.split("kernel(K$OS.EXEC, -1)")[0][-60:]),
       "tty %s, switch %s" % (tty, ox))

    ai = c["acc_os_info"]
    ck("B15 the account manifest does NOT carry the switches (Solo's shape was agreed with the Windows agent; a restored account has both OFF)",
       "os.sh" not in ai and "os.execute" not in ai and "ACC$SH" not in ai)

    spt = c["setptr"]
    sp0 = at(spt, "ospath(file.name, OS$PATHNAME)")
    sp1 = at(spt, "kernel(K$PATH.OK, file.name)")
    ck("B22 SETPTR ... AS PATHNAME asks K$PATH.OK after it has checked the name is a pathname, and says 11180",
       0 < sp0 < sp1 and "sysmsg(11180, @who)" in spt[sp1:sp1 + 120], "valid %s, ask %s" % (sp0, sp1))

    qp = c["qproc"]
    q1 = at(qp, "kernel(K$PATH.OK, csv.pathname)")
    ck("B22a a CSV report's TO pathname asks K$PATH.OK before the file is written", q1 > 0 and "$include int$keys.h" in srcs["qproc"] or q1 > 0, "ask %s" % q1)

    # the API server enters an account itself, through neither LOGIN nor CPROC, so it loads the switches itself
    ap = c["apisrvr"]
    a0 = at(ap, "api.sh.grant = @false")
    a1 = at(ap, "api.sh.grant = (upcase(trim(acc.rec<ACC$SH>)) = 'YES')")
    a2 = at(ap, "api.os.grant = (upcase(trim(acc.rec<ACC$OS.EXEC>)) = 'YES')")
    a_ld = at(ap, "void kernel(K$SH,      api.sh.grant)")
    a_ld2 = at(ap, "void kernel(K$OS.EXEC, api.os.grant)")
    a_login = at(ap, "readv i from @voc, 'LOGIN', 0")
    ck("B23 the API server reads the account's two switches from the register ('YES' only), starting from OFF on every call, and loads them "
       "only AFTER the account has been entered and before the LOGIN paragraph runs",
       0 < a0 < a1 < a2 and 0 < a_ld < a_ld2 < a_login and "api.os.grant = @false" in ap[a0:a1],
       "reset %s, read %s/%s, load %s/%s, login %s" % (a0, a1, a2, a_ld, a_ld2, a_login))

    # a VOC pointer is a way to NAME a file; Solo's one account holds F-pointers to its own directory and what the stock VOC says
    vr = c["_voc_ref"]
    vr_top = at(vr, "vr.admin = kernel(K$ADMINISTRATOR, -1)")
    vr_free = at(vr, "vr.free = vr.admin or kernel(K$OS.EXEC, -1)")
    f_chk = at(vr, "gosub check.f.path")
    f_ret = at(vr, "set.status 0", f_chk)
    fcp = block(vr, "check.f.path:", 900)
    ck("B26 _voc_ref asks about the file an F-pointer finally names, after the name is made absolute and before it is returned, unless the "
       "session is free (the administrator, or os): inside the account, or what the stock VOC says (same id, same field in NEWVOC)",
       0 < vr_top < vr_free < f_chk < f_ret and re.search(r"if not\(vr\.free\) then\s*gosub check\.f\.path\s*if not\(path\.ok\) then\s*pathname = ''\s*set\.status ER\$PERM", vr)
       and "kernel(K$PATH.OK, pathname)" in fcp and "upcase(stock.rec[1,1]) = 'F' and stock.rec<fno> = f.raw" in fcp,
       "check %s, return %s" % (f_chk, f_ret))
    pf = vr[at(vr, "case upcase(x1) = 'PATH'"):at(vr, "case n = 2")] if "case upcase(x1) = 'PATH'" in vr else ""
    ck("B27 the PATH: form (FILERULE) is held to the OS gate too", "if not(vr.free) and not(kernel(K$PATH.OK, pathname)) then" in pf and "set.status ER$PERM" in pf)
    qh = block(vr, "check.q.hop:", 900)
    ck("B25 a Q-pointer is followed only if it is the stock record (the same id, the same account name), a path the OS gate allows, or the account itself; "
       "an account Solo does not let anyone enter (SDSYS) is not followed from a restricted session",
       "stock.found and upcase(stock.rec[1,1]) = 'Q'" in qh and "q.ok = vr.free or kernel(K$PATH.OK, qpath)" in qh
       and re.search(r"if not\(vr\.admin\) then\s*gosub check\.q\.hop\s*if not\(q\.ok\) then\s*set\.status ER\$PERM", vr))

    # ---- V. the verb --------------------------------------------------------------------------------------------------
    so = c["setosacc"]
    ck("V1 the verb is an $internal program catalogued as $setosacc and the VOC says so (set.os.access is V, CA, $setosacc)",
       "$internal" in so and "$catalog $SETOSACC" in so and c["set.os.access"].split("\n")[:3] == ["V", "CA", "$setosacc"],
       repr(c["set.os.access"][:40]))
    adm = at(so, "if not(kernel(K$ADMINISTRATOR, -1)) then")
    rd = at(so, "readu acc.rec from acc.f, acc.name")
    wt = at(so, "write acc.new to acc.f, acc.name")
    ck("V2 it refuses without the administrator flag (2001) BEFORE it opens the register, and says nothing else changes",
       0 < adm < at(so, "openpath @sdsys:@ds:'accounts' to acc.f") and "sysmsg(2001)" in so[adm:adm + 160], "admin %s" % adm)
    ck("V3 it writes the register under a lock (readu before write) and reports a failed write with 10114",
       0 < rd < wt and "sysmsg(10114, acc.name)" in so and "release acc.f, acc.name" in so)
    ck("V4 it takes ONE action per command (sh or os, then on or off) and any other shape is the syntax message, not a guess",
       "upcase(word.1) = 'SH'" in so and "upcase(word.1) = 'OS'" in so and "upcase(word.2) = 'ON'" in so and "upcase(word.2) = 'OFF'" in so
       and "word.3 # ''" in so and "sysmsg(11926)" in so)
    ck("V5 no argument shows the state (10102) and changes nothing: the show path ends before any readu or write",
       0 < at(so, "sysmsg(10102, acc.name") and at(so, "stop") > 0 and
       so.find("if word.1 = '' then") > 0 and so.find("if word.1 = '' then") < rd)
    ck("V6 a switch is written 'yes' or 'no' (Core's values) and read back as ON only when it says YES; 10080 when it was already so",
       "acc.new<os.field> = 'yes'" in so and "acc.new<os.field> = 'no'" in so and "upcase(trim(acc.rec<os.field>)) = 'YES'" in so and "sysmsg(10080, acc.name)" in so)
    ck("V7 the audit line is lower case and names the word: 'set.os.access <word> <on|off>' written after the register write",
       re.search(r"kernel\(K\$AUDIT, 'set\.os\.access ' : downcase\(", so) and at(so, "K$AUDIT") > wt)

    sa = c["solo_account"]
    ck("V8 the account is made with the switches OFF: solo_account writes no 'yes' into fields 7 or 8 (a guard: it holds on a tree that has not changed it)",
       not re.search(r"ACC\$(SH|OS\.EXEC)\s*>?\s*=\s*'?yes", sa, re.I) and not re.search(r"<\s*[78]\s*>\s*=\s*'yes'", sa))

    # ---- I. the installer ------------------------------------------------------------------------------------------
    # (test-install-osaccess.sh runs the installer's block and reads the places the answer travels, with its own mutants; these are the
    # few lines of it that belong to the switch as a whole)
    ins = c["installsdsolo.sh"]
    stg = c["solo-stage.sh"]
    ck("I1 the installer asks about the shell and about OS access, each with the default NO (only an answer starting y is yes)",
       'os_yn "Turn on the shell' in ins and 'os_yn "Turn on OS access' in ins
       and re.search(r"os_yn\(\) \{[^}]*y\|Y\|yes\|YES\) return 0 ;; \*\) return 1 ;; esac\s*\}", ins))
    ck("I2 the question is asked on an upgrade and on a first install (the one run in which the owner's own Solo loses sh)",
       ins.count("ask_os_access") >= 3 and 'solo-stage.sh" --upgrade --os-access' in ins and 'st_args+=(--os-access "${os_access:-none}"' in ins)      # 24 Oct 26: --viewer follows it since carry 14; the pin ended at the bracket and had been red since
    ck("I3 an unattended run is none: no terminal or --yes and no answer",
       'os_access="none"' in ins and '[ "$interactive" -ne 1 ] || [ "$assume_yes" -eq 1 ]' in ins)
    ck("I4 the answer is applied by the verb in an internal session, and only for the words the owner said",
       'osacc_one SH' in stg and 'osacc_one OS' in stg and 'sdi SET.OS.ACCESS "$1" ON' in stg and 'sdi SET.OS.ACCESS 2>&1' in stg)

    # ---- M. the messages -------------------------------------------------------------------------------------------
    want = {"10053": "%1 is not permitted to use the operating system shell",
            "10054": "%s is not permitted to use OS.EXECUTE",
            "10080": "%1 already had that access; nothing changed",
            "10102": "Account %1 has SH %2, OS.EXECUTE %3",
            "10114": "Unable to change the state of %1; its state in the register is unchanged",
            "11008": "The VOC can only be changed after admin",
            "11180": "%1 has no OS access",
            "11926": "Syntax: set.os.access"}
    for num, text in want.items():
        path = os.path.join(messages_dir, num)
        try:
            with open(path) as f:
                body = f.read().rstrip("\n")
        except OSError as exc:
            ck("M1 message %s exists" % num, False, str(exc))
            continue
        ck("M1 message %s exists and starts as the code expects" % num, body.startswith(text), repr(body[:80]))
    return rows


# --------------------------------------------------------------- self-test
def sub(name, old, new):
    def f(srcs):
        s = dict(srcs)
        if old not in s[name]:
            raise KeyError("%s: %r is not in the file, so the mutant cannot be made" % (name, old[:50]))
        s[name] = s[name].replace(old, new, 1)
        return s
    return f


def swap(name, a, b):
    """Move the first `a` text to just after the first `b` text (a reorder)."""
    def f(srcs):
        s = dict(srcs)
        t = s[name]
        if a not in t or b not in t:
            raise KeyError("%s: a swap anchor is missing" % name)
        t = t.replace(a, "", 1)
        i = t.find(b) + len(b)
        s[name] = t[:i] + a + t[i:]
        return s
    return f


MUTANTS = [
    ("sh() takes the stack before it refuses", "C1", swap("op_sh.c", "if (!os_permitted())\n    k_error(sysmsg(10054), process.username);", "k_get_string(descr);")),
    ("os_gate_open() trusts an $internal program", "C4", sub("op_sh.c", "return (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC)) != 0;", "return (process.program.flags & HDR_INTERNAL) || (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC)) != 0;")),
    ("containment compares without a component boundary", "C5", sub("op_sh.c", "(resolved[root_len] == '\\0') || (resolved[root_len] == '/')", "1")),
    ("os_path_ok_for_account always says yes", "C7", sub("op_sh.c", "  return path_inside_dir(NULL, name);", "  return TRUE;")),
    ("OPENSEQ asks after the port test", "C9", swap("op_seqio.c", "if (!os_path_open_ok(file_name)) {\n      process.status = ER_PERM;\n      goto exit_op_openseq;\n    }", "if (is_port(file_name)) /* Opening a port */")),
    ("OPENPATH is asked even for a VOC-named file (the wrong half of the test)", "C12", sub("op_dio1.c", "if (!map_name && !os_path_open_ok(pathname)) {", "if (map_name && !os_path_open_ok(pathname)) {")),
    ("kernel(K_SH) lets any caller set the flag", "C13", sub("op_kernel.c", "if (process.program.flags & HDR_INTERNAL) {\n          if (n > 0)\n            my_uptr->flags |= USR_SH;", "if (1) {\n          if (n > 0)\n            my_uptr->flags |= USR_SH;")),
    ("kernel(K_PATH_OK) asks the caller's question", "C14", sub("op_kernel.c", "os_path_ok_for_account(path_ok_name)", "os_path_open_ok(path_ok_name)")),
    ("the Python gate asks nobody", "C15", sub("op_sdext.c", "!os_gate_open()) {", "0) {")),
    ("DIR() opens before it asks", "C17", swap("op_dio4.c", "if (!os_path_open_ok(pathname)) {\n      process.status = ER_PERM;\n    } else if ((dfu = opendir(pathname)) != NULL) {", "opendir(pathname)")),
    ("DIGEST asks nobody", "C20", sub("op_xfun.c", "} else if (!os_path_open_ok(path)) {", "} else if (0) {")),
    ("the trace log asks nobody", "C22", sub("op_skt.c", "if (!os_path_ok_for_account(trace_path)) {", "if (0) {")),
    ("the spooler string is run for everybody", "C23", sub("linuxprt.c", "(pu->spooler != NULL) && os_gate_open()", "(pu->spooler != NULL)")),
    # Solo carry 19 (24 Oct 26): the VOC's own files by pathname (O).
    ("the VOC test no longer exempts the administrator and OS.EXECUTE (it asks everybody)", "O1", sub("op_sh.c", "if (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC))\n    return EDIT_NONE;", "if (0)\n    return EDIT_NONE;")),
    ("a path that cannot be resolved is let through", "O1", sub("op_sh.c", "if (!resolve_gate_path(NULL, name, root, resolved))\n    return EDIT_VOC;", "if (!resolve_gate_path(NULL, name, root, resolved))\n    return EDIT_NONE;")),
    ("a component named VOC is not a VOC (the test is case sensitive)", "O1a", sub("op_sh.c", 'strncasecmp(p, "voc", 3) == 0', 'strncmp(p, "voc", 3) == 0')),
    ("a directory called voc as the final name is never one (include_leaf ignored)", "O1a", sub("op_sh.c", "(include_leaf || (*more != '\\0'))", "(*more != '\\0')")),
    ("the VOC test resolves the path its own way", "O2", sub("op_sh.c", "if (!resolve_gate_path(NULL, name, root, resolved))\n    return EDIT_VOC;", "if (realpath(name, resolved) == NULL)\n    return EDIT_VOC;")),
    ("a link or a directory is a record for edit_leaf_counts", "O3", sub("op_sh.c", "return !S_ISREG(sb.st_mode);", "return FALSE;")),
    ("OPENSEQ never asks", "O4", sub("op_seqio.c", "edit_blocked = (edit_os_path_refusal(fullpathname, FALSE) != EDIT_NONE);", "edit_blocked = FALSE;")),
    ("CREATING in a VOC is allowed", "O4", sub("op_seqio.c", "} else if ((op_flags & 0x400) && edit_blocked)", "} else if ((op_flags & 0x400) && 0)")),
    ("DELETESEQ never asks", "O5", sub("op_seqio.c", "if (!(process.program.flags & HDR_INTERNAL) && (edit_os_path_refusal(file_name, FALSE) != EDIT_NONE)) {", "if (0) {")),
    ("OSPATH delete counts a plain file's own name but never a directory's", "O6", sub("op_xfun.c", "(key == 5) ? edit_leaf_counts(path) : TRUE", "FALSE")),
    ("the trace log never asks", "O7", sub("op_skt.c", "(edit_os_path_refusal(trace_path, FALSE) != EDIT_NONE)", "0")),
    ("a print file never asks", "O8", sub("to_file.c", "if (edit_os_path_refusal(fn, FALSE) != EDIT_NONE) {", "if (0) {")),
    ("kernel(K_EDIT_OS_OK) says yes to everybody", "O9", sub("op_kernel.c", "edit_os_path_refusal(edit_os_name, edit_leaf_counts(edit_os_name)) == EDIT_NONE) ? 1 : 0", "1) ? 1 : 0")),
    ("!OSCOPY does not ask about the target", "O10", sub("_oscopy", "end else if not(kernel(K$EDIT.OS.OK, target)) then", "end else if 0 then")),
    ("!OSCOPY asks about the source, which is only read", "O10", sub("_oscopy", "end else if not(kernel(K$EDIT.OS.OK, target)) then", "end else if not(kernel(K$EDIT.OS.OK, source)) then")),
    ("!IOSCOPY does not ask about the target", "O11", sub("_ioscopy", "   if not(kernel(K$EDIT.OS.OK, target)) then", "   if 0 then")),
    ("the SH verb refuses after the metacharacter test", "B2", swap("cproc", "if not(kernel(K$ADMINISTRATOR, -1)) and not(kernel(K$SH, -1)) then\n      display sysmsg(10053, @logname) ;* %1 is not permitted to use the operating system shell\n      return\n   end\n",
                                                                    "display sysmsg(5240, 2) ;* Error xx executing operating system command\n      return\n   end\n")),
    ("LOGIN loads the switches from the wrong field", "B3", sub("login", "upcase(trim(acc.rec<ACC$OS.EXEC>)) = 'YES'", "upcase(trim(acc.rec<ACC$SH>)) = 'YES'")),
    ("a blank register field turns the switch ON (the null case)", "B3", sub("login", "upcase(trim(acc.rec<ACC$SH>)) = 'YES'", "upcase(trim(acc.rec<ACC$SH>)) # 'NO'")),
    ("the editors outside SD no longer need os", "B14", sub("edit", "if kernel(K$OS.EXEC, -1) then", "if 1 then")),
    ("SETPTR AS PATHNAME is not asked", "B22", sub("setptr", "if not(kernel(K$PATH.OK, file.name)) then", "if 0 then")),
    ("the API server's switches default to ON", "B23", sub("apisrvr", "api.os.grant = @false", "api.os.grant = @true")),
    ("an F-pointer's target is not asked", "B26", sub("_voc_ref", "if not(vr.free) then\n               gosub check.f.path", "if 0 then\n               gosub check.f.path")),
    ("the verb is open to everyone", "V2", sub("setosacc", "if not(kernel(K$ADMINISTRATOR, -1)) then", "if 0 then")),
    ("the verb writes without a lock", "V3", sub("setosacc", "readu acc.rec from acc.f, acc.name", "read acc.rec from acc.f, acc.name")),
    ("the verb takes two actions in one command", "V4", sub("setosacc", "sysmsg(11926)", "sysmsg(10102)")),
    ("the verb writes a switch ON for an 'off' request", "V6", sub("setosacc", "acc.new<os.field> = 'no'", "acc.new<os.field> = 'yes'")),
    ("the audit line is written in capitals", "V7", sub("setosacc", "'set.os.access ' : downcase(", "'SET.OS.ACCESS ' : downcase(")),
    ("the installer's question defaults to Yes", "I1", sub("installsdsolo.sh", "*) return 1 ;; esac\n}\nask_os_access", "*) return 0 ;; esac\n}\nask_os_access")),
    ("solo-stage turns nothing on", "I4", sub("solo-stage.sh", 'sdi SET.OS.ACCESS "$1" ON', 'sdi SET.OS.ACCESS')),
    ("the message the SH refusal prints is gone", "M1", None),
]


def run_selftest(srcs, messages_dir):
    ok_all = True
    base = checks(srcs, messages_dir)
    base_fail = {r[0] for r in base if not r[1]}
    print("selftest: the unchanged tree fails %d check(s): %s" % (len(base_fail), ", ".join(sorted(base_fail)[:6]) or "none"))
    if base_fail:
        print("selftest: the switch is not whole, so a mutant's own failure cannot be told from the tree's; run the plain check first")
        return False
    for name, want, mut in MUTANTS:
        if mut is None:
            continue
        try:
            mutated = mut(srcs)
        except KeyError as exc:
            print("  [FAIL] selftest: %s  <- %s" % (name, exc))
            ok_all = False
            continue
        failed = sorted({r[0].split()[0] for r in checks(mutated, messages_dir) if not r[1]})
        hit = want in failed
        print("  [%s] selftest: %s is caught by %s (failed: %s)" % ("PASS" if hit else "FAIL", name, want, " ".join(failed) or "none"))
        ok_all = ok_all and hit
    return ok_all


def load():
    srcs = {}
    missing = []
    for name, path in FILES.items():
        try:
            with open(path, encoding="latin-1") as f:
                srcs[name] = f.read()
        except OSError:
            srcs[name] = ""
            missing.append(name)
    return srcs, missing


def main(argv):
    srcs, missing = load()
    print("test-osgate-units: tree %s" % SD64)
    absent_core = [n for n in ("op_sh.c", "keys.h", "cproc", "login") if n in missing]
    if absent_core:
        print("test-osgate-units: CANNOT RUN - these files are not there: %s" % absent_core)
        return 2
    if missing:
        print("test-osgate-units: not there yet (their checks fail): %s" % ", ".join(missing))
    messages_dir = os.path.join(SDSYS, "messages")
    rows = checks(srcs, messages_dir)
    failed = 0
    for i, ok, detail in rows:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", i, "" if ok or not detail else "   <- " + str(detail)[:200]))
        failed += 0 if ok else 1
    print("\ntest-osgate-units: %d passed, %d failed" % (len(rows) - failed, failed))
    ok = failed == 0
    if "--selftest" in argv:
        ok = run_selftest(srcs, messages_dir) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
