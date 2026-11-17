#!/usr/bin/env python3
# test-netdirs-units.py - S.62, 17 Nov 2026: NETDIRS in SD Core Solo for Linux, carried from SD Core for Linux (the owner, 17 Nov: Linux Core
# gains Windows' parameter, delivered empty, and a feature needed for parity is built "on multiple systems if needed to achieve parity, taking
# into account the differences between operating systems and core vs solo purpose").  FREE CHECK: no install, no sudo, no sd; the C and the
# table are read as text, comments removed where a rule is about code.
#
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-netdirs-units.py
#   python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-netdirs-units.py --selftest      (mutants of op_sh.c, config.c, config.h, sysseg.c, the table)
#
# WHERE SOLO DIFFERS FROM CORE'S CHECK OF THE SAME NAME
#   Solo has not got Core's W.11 F9: every sd.conf parameter is read at sd-solo -start into the segment's PCFG template (mode 0600, the one user's)
#   and copied by each process, so NETDIRS takes effect at the next start (D3, T1 'restart').  Solo's gate has no SD.ACCOUNTS step and resolves
#   with resolve_gate_path(), not resolve_name() (G1, G2).  An entry is also ignored when it holds or lies inside the Solo folder, GetHomePath()
#   (E1).  Key 90 is not this check's (Core's K1 rows are left out).
#
# WHAT IT CHECKS
#   D1  delivered empty: config.c sets pcfg.netdirs to "" before it reads sd.conf, and the shipped sd.conf has no NETDIRS= line
#   D2  the value is bounded: MAX_NETDIRS_LEN 191 (what a 199-character sd.conf line leaves after "NETDIRS="), the field is MAX_NETDIRS_LEN+1 in
#       struct PCFG (not CONFIG), and a longer value or a line that did not fit is refused by name before the copy
#   D3  only config.c writes pcfg.netdirs (no PCONFIG, no session can change it); the segment has no field of its own for it (no sysseg->netdirs);
#       CONFIG() does not offer it
#   G1  os_path_ok_for_account(): os_gate_open() (the administrator, an account given OS ON) answers first, the account's own directory next,
#       path_in_netdirs() LAST; os_path_open_ok() trusts an $internal program before it asks; path_in_netdirs is called from nowhere else
#   G2  path_in_netdirs(): an empty list answers no at once; the name is resolved by resolve_gate_path() (the gate's own resolution) BEFORE the
#       dot test, the list and the comparison; a name it cannot resolve, or one still holding "." or "..", is a no; a matching entry is admitted
#       only while no registered account overlaps it (the register is read again)
#   G3  the comparison is case-sensitive (strncmp, never strncasecmp), ends at a component boundary, and never takes "/" as a root
#   E1  an entry is ignored when it is not absolute, not an existing directory (realpath and S_ISDIR), "/", or overlaps the Solo folder, the
#       system directory, sd.conf's directory, USRDIR, GRPDIR or a registered account; a folder that cannot be found refuses; an unreadable
#       register refuses; an over-long element is discarded, not cut
#   E2  start_sd() calls netdirs_report() after bind_sysseg(), which names each ignored entry in the error log and in syslog as sd-solo
#   T1  config.table has a NETDIRS row, kind text, effect restart, write no (so set.config, which changes only write = yes, refuses it)
# WHAT IT CANNOT SAY: that a session is admitted or refused - a session with the OS switch off reading a file in a listed directory, refused in
# an unlisted one, and the rest: those are run-time rows (Solo has no sandbox of its own; see the closing report of the S.62 lane LS3-kernel).
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(SD64, "gplsrc")
FILES = {
    "opsh": os.environ.get("ND_OPSH", os.path.join(SRC, "op_sh.c")),
    "configc": os.environ.get("ND_CONFIGC", os.path.join(SRC, "config.c")),
    "configh": os.environ.get("ND_CONFIGH", os.path.join(SRC, "config.h")),
    "sysseg": os.environ.get("ND_SYSSEG", os.path.join(SRC, "sysseg.c")),
    "table": os.environ.get("ND_TABLE", os.path.join(SD64, "sdsys", "config.table")),
}
passed = failed = 0


def row(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print("  [PASS] " + name)
    else:
        failed += 1
        print("  [FAIL] " + name + ("   <- " + detail if detail else ""))


def read(p):
    return open(p, encoding="latin-1").read()


def code(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def func(src, sig):
    """The body of the C function whose definition starts with sig, up to the closing brace at column 0."""
    i = src.find(sig)
    if i < 0:
        return ""
    j = src.find("\n}", i)
    return src[i:j + 2] if j > 0 else ""


def at(s, t):
    return s.find(t)


def run():
    raw = {k: read(p) for k, p in FILES.items() if os.path.exists(p)}
    if len(raw) != len(FILES):
        print("test-netdirs-units: CANNOT RUN - missing %s" % sorted(set(FILES) - set(raw)))
        return 2
    opsh, cfgc, cfgh = code(raw["opsh"]), code(raw["configc"]), code(raw["configh"])
    if "os_path_ok_for_account" not in opsh or "read_config" not in cfgc:
        print("test-netdirs-units: CANNOT RUN - op_sh.c or config.c is not the file this check reads (NULL CASE)")
        return 2

    # D1 delivered empty
    i_def, i_open = at(cfgc, "pcfg.netdirs[0] = '\\0';"), at(cfgc, "fu = fopen(config_path, \"r\");")
    row("D1 config.c sets pcfg.netdirs to the empty string before it opens sd.conf", 0 <= i_def < i_open, "%d %d" % (i_def, i_open))
    conf = read(os.path.join(SD64, "sd.conf"))
    row("D1 the shipped sd.conf has no NETDIRS= line", not re.search(r"^\s*NETDIRS\s*=", conf, re.M))

    # D2 bounded
    pc = cfgh[cfgh.find("struct PCFG"):]
    cf = cfgh[cfgh.find("struct CONFIG"):cfgh.find("struct PCFG")]
    row("D2 MAX_NETDIRS_LEN is 191 and the field is MAX_NETDIRS_LEN+1 in struct PCFG, not in struct CONFIG",
        re.search(r"#define MAX_NETDIRS_LEN 191\b", cfgh) is not None and "char netdirs[MAX_NETDIRS_LEN+1];" in pc and "netdirs" not in cf)
    br = cfgc[cfgc.find('strncmp(rec, "NETDIRS=", 8) == 0'):]
    br = br[:br.find("else if")]
    i_len, i_err, i_cpy = at(br, "if (!line_whole || (strlen(rec + 8) > MAX_NETDIRS_LEN))"), at(br, '"NETDIRS value is longer than %d characters."'), at(br, "strcpy(pcfg.netdirs, rec + 8);")
    row("D2 the NETDIRS branch refuses a value over the limit, or a line that did not fit, by name and stops reading, before the copy",
        0 <= i_len < i_err < i_cpy and "goto exit_read_config;" in br[i_err:i_cpy], "%d %d %d" % (i_len, i_err, i_cpy))
    lw = cfgc[cfgc.find("while (fgets(rec, 200, fu) != NULL) {"):]
    row("D2 line_whole is set TRUE for every line and FALSE only when the line went on past the buffer (the newline of a 199-character line is taken)",
        lw.find("line_whole = TRUE;") >= 0 and "if ((c != EOF) && (c != '\\n')) {" in lw and "ungetc(c, fu);" in lw and lw.find("line_whole = TRUE;") < lw.find("line_whole = FALSE;"))

    # D3 written once, at start; not a segment field of its own; not CONFIG()
    writers, segreaders = [], []
    for n in sorted(os.listdir(SRC)):
        if n.endswith((".c", ".h")):
            s = code(read(os.path.join(SRC, n)))
            if re.search(r"pcfg\.netdirs\s*(\[[^\]]*\]\s*)?=[^=]|strn?cpy\(\s*pcfg\.netdirs|memcpy\(\s*pcfg\.netdirs|snprintf\(\s*pcfg\.netdirs", s):
                writers.append(n)
            if "sysseg->netdirs" in s:
                segreaders.append(n)
    row("D3 only config.c writes pcfg.netdirs (read at sd-solo -start; no PCONFIG or session changes it)", writers == ["config.c"], ", ".join(writers))
    sysh = code(read(os.path.join(SRC, "sysseg.h")))
    row("D3 no source file reads sysseg->netdirs and the segment has no netdirs field of its own", not segreaders and "netdirs" not in sysh, ", ".join(segreaders))
    row("D3 CONFIG() does not offer NETDIRS (op_config.c does not name it)", "NETDIRS" not in read(os.path.join(SRC, "op_config.c")))

    # G1 who is asked
    ok_f = func(opsh, "bool os_path_ok_for_account(const char *name) {")
    i_gate, i_own, i_nd = at(ok_f, "if (os_gate_open())\n    return TRUE;"), at(ok_f, "if (path_inside_dir(NULL, name))\n    return TRUE;"), at(ok_f, "return path_in_netdirs(name);")
    row("G1 os_path_ok_for_account(): os_gate_open() first, the account's own directory, then path_in_netdirs() as the last answer",
        0 <= i_gate < i_own < i_nd and ok_f.count("path_in_netdirs") == 1, "%d %d %d" % (i_gate, i_own, i_nd))
    op_f = func(opsh, "bool os_path_open_ok(const char *name) {")
    row("G1 os_path_open_ok() trusts an $internal program before it asks the account", at(op_f, "HDR_INTERNAL") >= 0 and at(op_f, "HDR_INTERNAL") < at(op_f, "os_path_ok_for_account(name)"))
    row("G1 os_gate_open() is the administrator or the OS switch, nothing else", "return (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC)) != 0;" in func(opsh, "bool os_gate_open(void) {"))
    row("G1 path_in_netdirs is defined once and called only by os_path_ok_for_account", opsh.count("path_in_netdirs(") == 2, str(opsh.count("path_in_netdirs(")))

    # G2 resolved first
    nd = func(opsh, "Private bool path_in_netdirs(const char *name) {")
    seq = [at(nd, "if (pcfg.netdirs[0] == '\\0')\n    return FALSE;"), at(nd, "if (!resolve_gate_path(NULL, name, root, resolved))\n    return FALSE;"), at(nd, "if (netdir_dot_component(resolved))\n    return FALSE;"),
           at(nd, "netdirs_load(FALSE);"), at(nd, "netdir_within(resolved, netdirs_root[i])")]
    row("G2 path_in_netdirs(): empty list -> no; resolve_gate_path() -> no when it fails; a dot component -> no; then the list; then the comparison",
        all(x >= 0 for x in seq) and seq == sorted(seq), str(seq))
    row("G2 a matching entry admits only while no registered account overlaps it (netdir_account_clash() == 0, read at the admission)",
        "netdir_within(resolved, netdirs_root[i]) && (netdir_account_clash(netdirs_root[i], NULL, 0) == 0)" in nd)
    dc = func(opsh, "Private bool netdir_dot_component(const char *p) {")
    row("G2 the dot test finds a \".\" or \"..\" component in the middle or at the end", "(p[0] == '.') && ((p[1] == '\\0') || (p[1] == '/') || ((p[1] == '.') && ((p[2] == '\\0') || (p[2] == '/'))))" in dc)
    rn = func(opsh, "Private bool resolve_gate_path(const char *rootdir, const char *name, char *root, char *resolved) {")
    row("G2 resolve_gate_path() still refuses a \"..\" or \".\" in the part that does not exist and a link to nothing",
        '(strcmp(p + 1, "..") == 0) || (strcmp(p + 1, ".") == 0)' in rn and "S_ISLNK(lst.st_mode)" in rn)

    # G3 comparison
    wi = func(opsh, "Private bool netdir_within(const char *a, const char *b) {")
    row("G3 the comparison is case-sensitive, at a component boundary, and never takes a root of one character (\"/\")",
        "strncmp(a, b, n)" in wi and "strncasecmp" not in wi and "(n <= 1)" in wi and "return (a[n] == '\\0') || (a[n] == '/');" in wi)

    # E1 entry rules
    ld = func(opsh, "Private void netdirs_load(bool report) {")
    rules = ["if (item[0] != '/')", "(realpath(item, root) == NULL) || (stat(root, &st) != 0) || !S_ISDIR(st.st_mode)", 'strcmp(root, "/") == 0',
             "!have_home || netdir_overlap(root, homedir)", "!have_sys || netdir_overlap(root, sysdir)", "!have_conf || netdir_overlap(root, confdir)",
             "netdir_resolved(pcfg.usrdir, other) && netdir_overlap(root, other)", "netdir_resolved(pcfg.grpdir, other) && netdir_overlap(root, other)",
             "(clash = netdir_account_clash(root, which, sizeof(which))) != 0", "netdirs_count >= MAX_NETDIRS"]
    pos = [at(ld, r) for r in rules]
    row("E1 an entry is ignored when not absolute, not a directory, \"/\", or overlapping the Solo folder, the system directory, sd.conf's directory, USRDIR, GRPDIR or an account, in that order",
        all(x >= 0 for x in pos) and pos == sorted(pos), str(pos))
    row("E1 the Solo folder is GetHomePath() resolved, and a folder that cannot be found (or is \"/\") takes every entry with it",
        "have_home = GetHomePath(home, sizeof(home)) && netdir_resolved(home, homedir) && (strcmp(homedir, \"/\") != 0);" in ld)
    row("E1 only an entry that passed every rule is taken (the copy is in the else of the 'why' test)",
        "if (why[0] != '\\0')\n        netdir_note(report, item, why);\n      else\n        strcpy(netdirs_root[netdirs_count++], root);" in ld)
    cl = func(opsh, "Private int netdir_account_clash(const char *root, char *which, size_t which_len) {")
    row("E1 an unreadable register is a clash (-1) and every caller takes non-zero as a refusal",
        cl.count("return -1;") == 2 and "(clash = netdir_account_clash(root, which, sizeof(which))) != 0" in ld and "== 0))" in nd)
    row("E1 an element longer than a pathname is discarded, never cut", "if (n > MAX_PATHNAME_LEN) {" in ld and at(ld, "if (n > MAX_PATHNAME_LEN) {") < at(ld, "memcpy(item, p, n);"))
    row("E1 the list is split at ';'", 'strcspn(p, ";")' in ld)

    # E2 start
    ss = code(raw["sysseg"])
    st = func(ss, "bool start_sd(bool with_daemon) {")
    row("E2 start_sd() calls netdirs_report() after bind_sysseg()", 0 <= at(st, "bind_sysseg(TRUE, errmsg)") < at(st, "netdirs_report();"))
    rp = func(opsh, "void netdirs_report(void) {")
    row("E2 netdirs_report() judges with report TRUE and leaves the session's own judgement to the session", "netdirs_load(TRUE);" in rp and "netdirs_count = -1;" in rp)
    nn = func(opsh, "Private void netdir_note(bool report, const char *entry, const char *why) {")
    row("E2 an ignored entry is named in the error log and in syslog as sd-solo (Solo's command), and only when reporting",
        "if (!report)\n    return;" in nn and "log_message(msg);" in nn and 'syslog(LOG_WARNING, "sd-solo: %s", msg);' in nn)

    # T1 table
    trow = [l for l in raw["table"].split("\n") if l.startswith("NETDIRS|")]
    f = trow[0].split("|") if len(trow) == 1 else []
    row("T1 config.table has one NETDIRS row: text, no default, restart, live, write no, with a reason", len(f) == 10 and f[1] == "text" and f[2] == "" and f[5] == "restart" and f[8] == "no" and f[9] != "", repr(trow))

    print("test-netdirs-units: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


def selftest():
    import shutil
    t = tempfile.mkdtemp()
    caught = missed = 0
    env_of = {"opsh": "ND_OPSH", "configc": "ND_CONFIGC", "configh": "ND_CONFIGH", "sysseg": "ND_SYSSEG", "table": "ND_TABLE"}

    def mutant(name, which, old, new):
        nonlocal caught, missed
        src = read(FILES[which])
        if old not in src:
            print("  [MISSED] %s: the text to change is not there" % name)
            missed += 1
            return
        f = os.path.join(t, name)
        open(f, "w", encoding="latin-1").write(src.replace(old, new, 1))
        env = dict(os.environ)
        env[env_of[which]] = f
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True, text=True)
        if r.returncode == 1:
            print("  [caught] %s" % name)
            caught += 1
        else:
            print("  [MISSED] %s: exit %d" % (name, r.returncode))
            missed += 1

    print("selftest: the real files first (must pass), then mutants (each must fail)")
    r = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [FAIL] the real files do not pass:\n" + r.stdout[-800:])
        return 1
    print("  [ok] the real files pass")
    mutant("netdirs-before-gate", "opsh", "  if (os_gate_open())\n    return TRUE;\n  if (path_inside_dir(NULL, name))", "  if (path_in_netdirs(name))\n    return TRUE;\n  if (os_gate_open())\n    return TRUE;\n  if (path_inside_dir(NULL, name))")
    mutant("no-resolve", "opsh", "if (!resolve_gate_path(NULL, name, root, resolved))\n    return FALSE;\n  if (netdir_dot_component", "if (strlen(strcpy(resolved, name)) == 0)\n    return FALSE;\n  if (netdir_dot_component")
    mutant("no-dot-test", "opsh", "  if (netdir_dot_component(resolved))\n    return FALSE;\n", "")
    mutant("case-blind", "opsh", "(strncmp(a, b, n) != 0)", "(strncasecmp(a, b, n) != 0)")
    mutant("no-boundary", "opsh", "return (a[n] == '\\0') || (a[n] == '/');\n}\n\nPrivate bool netdir_overlap", "return TRUE;\n}\n\nPrivate bool netdir_overlap")
    mutant("root-accepted", "opsh", "if ((n <= 1) || (strncmp(a, b, n) != 0))", "if (strncmp(a, b, n) != 0)")
    mutant("relative-taken", "opsh", "if (item[0] != '/')\n        strcpy(why, \"it is not an absolute path\");\n      else ", "")
    mutant("solo-folder-taken", "opsh", "!have_home || netdir_overlap(root, homedir)", "0")
    mutant("solo-folder-missing-opens", "opsh", "have_home = GetHomePath(home, sizeof(home)) && netdir_resolved(home, homedir)", "have_home = 1 || GetHomePath(home, sizeof(home)) && netdir_resolved(home, homedir)")
    mutant("sysdir-taken", "opsh", "!have_sys || netdir_overlap(root, sysdir)", "0")
    mutant("account-not-rechecked", "opsh", " && (netdir_account_clash(netdirs_root[i], NULL, 0) == 0)", "")
    mutant("register-unreadable-opens", "opsh", "  if ((d = opendir(regdir)) == NULL)\n    return -1;\n  while ((clash == 0)", "  if ((d = opendir(regdir)) == NULL)\n    return 0;\n  while ((clash == 0)")
    mutant("long-element-cut", "opsh", "if (n > MAX_PATHNAME_LEN) {", "if (0) {")
    mutant("syslog-names-core", "opsh", 'syslog(LOG_WARNING, "sd-solo: %s", msg);', 'syslog(LOG_WARNING, "sd: %s", msg);')
    mutant("default-not-empty", "configc", "pcfg.netdirs[0] = '\\0';", "strcpy(pcfg.netdirs, \"/tmp\");")
    mutant("no-length-refusal", "configc", "if (!line_whole || (strlen(rec + 8) > MAX_NETDIRS_LEN)) {", "if (0) {")
    mutant("long-line-not-seen", "configc", "if (!line_whole || (strlen", "if ((strlen")
    mutant("limit-raised", "configh", "#define MAX_NETDIRS_LEN 191", "#define MAX_NETDIRS_LEN 1023")
    mutant("no-start-report", "sysseg", "  netdirs_report();\n", "")
    mutant("table-writable", "table", "beyond its own directory.", "beyond its own directory.|")
    mutant("table-says-session", "table", "NETDIRS|text||||restart|", "NETDIRS|text||||session|")
    shutil.rmtree(t, ignore_errors=True)
    print("selftest: %d of %d mutants caught, %d missed" % (caught, caught + missed, missed))
    return 0 if missed == 0 else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())
