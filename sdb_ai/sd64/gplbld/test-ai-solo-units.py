#!/usr/bin/env python3
"""test-ai-solo-units.py - the AI helper, its gate, SET.AI, the ai verb, the kernel transport and the page of SD Core for Linux Solo (carry 15 of S.69 step 2, 23 Oct 2026), as
invariants read off the source.  Solo's counterpart of Core's test-ai-units.py (whose checks about a Linux group, sd-elevate and the OS user sdai have no Solo equivalent and are not here).

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-ai-solo-units.py
  python3 .../test-ai-solo-units.py --selftest [--from=N]

No sudo, no install, no sd.  Exit 0 every check passed, 1 a check failed, 2 it could not run.

***WHAT THIS IS, AND WHAT IT IS NOT.***  It reads the helper, the C and BASIC sources, the units that solo-service.sh writes and the installer's blocks as TEXT (comments removed
where a comment could stand in for code), so a rule that survives only in a comment does not count.  IT RUNS NOTHING OF SD AND CANNOT SAY THAT THE GATE REFUSES ANYBODY: that is
test-aihelper.py (the helper run against a fake provider, 163 rows) and sandbox-ai-solo.py (SET.AI, the verb, the transport and the page on a private Solo).  The one thing it does run
is `solo-service.sh ai <tree> --print`, which writes nothing.  What a text check is for: the invariants that make this a gate are mostly ORDERING (the stranger refused before any
setting is read or written, the gate before the model and the key, the audit line before the connection) and an edit that moves one still compiles.

THE SHAPE (owner, 23 Oct 2026, "same-user helper"): Solo installs no OS user and no root-owned file, so the helper runs as the Solo user from a user systemd socket, its gate is the
setting gate=yes in <tree>/ai/ai.conf (off as delivered, changed by set.ai gate on|off), the keys and settings are private files of the user, and a process of the same user can talk to
the helper: that weakness is said in the helper's head, in the help text, in the page and in the docs, and the checks below hold that it is said.
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.abspath(os.path.join(HERE, os.pardir))
SDSYS = os.path.join(SD64, "sdsys")
GPL = os.path.join(SDSYS, "gpl.bp")
GPLSRC = os.path.join(SD64, "gplsrc")
ROOT = os.path.dirname(os.path.dirname(SD64))

FILES = {
    "sd-ai": os.path.join(HERE, "sd-ai"),
    "sd-ai-ctl": os.path.join(HERE, "sd-ai-ctl"),
    "ai-runner": os.path.join(HERE, "ai-runner.py"),
    "solo-service.sh": os.path.join(HERE, "solo-service.sh"),
    "solo-stage.sh": os.path.join(HERE, "solo-stage.sh"),
    "installsdsolo.sh": os.path.join(ROOT, "installsdsolo.sh"),
    "deletesdsolo.sh": os.path.join(ROOT, "deletesdsolo.sh"),
    "op_ai.c": os.path.join(GPLSRC, "op_ai.c"),
    "op_kernel.c": os.path.join(GPLSRC, "op_kernel.c"),
    "keys.h": os.path.join(GPLSRC, "keys.h"),
    "sd.h": os.path.join(GPLSRC, "sd.h"),
    "int$keys.h": os.path.join(GPL, "int$keys.h"),
    "gpl.src": os.path.join(SD64, "gpl.src"),
    "ai": os.path.join(GPL, "ai"),
    "setai": os.path.join(GPL, "setai"),
    "tool_ai": os.path.join(GPL, "tool_ai"),
    "tk_runx": os.path.join(GPL, "tk_runx"),
    "newvoc/ai": os.path.join(SDSYS, "newvoc", "ai"),
    "newvoc/set.ai": os.path.join(SDSYS, "newvoc", "set.ai"),
    "newvoc/tool.ai": os.path.join(SDSYS, "newvoc", "tool.ai"),
    "voc_template/ai": os.path.join(SDSYS, "voc_template", "ai"),
    "voc_template/set.ai": os.path.join(SDSYS, "voc_template", "set.ai"),
    "voc_template/tool.ai": os.path.join(SDSYS, "voc_template", "tool.ai"),
    "helptext/providers": os.path.join(SDSYS, "helptext", "tool.ai.providers"),
    "helptext/accounts": os.path.join(SDSYS, "helptext", "tool.ai.accounts"),
}
MSGS = list(range(11606, 11635))


def read(path):
    with open(path, encoding="latin-1") as f:
        return f.read()


def strip_c(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def strip_bas(t):
    out = []
    for ln in t.split("\n"):
        s = ln.lstrip()
        if s.startswith("*") or s.startswith("!"):
            continue
        out.append(re.sub(r";\*.*$", "", ln))
    return "\n".join(out)


def strip_py(t):
    return "\n".join(ln for ln in t.split("\n") if not ln.lstrip().startswith("#"))


def strip_sh(t):
    return "\n".join(ln for ln in t.split("\n") if not ln.lstrip().startswith("#"))


def ordered(t, *needles):
    pos = -1
    for n in needles:
        i = t.find(n, pos + 1)
        if i < 0:
            return False
        pos = i
    return True


def load():
    s = {k: read(p) for k, p in FILES.items()}
    s["msgs"] = {n: (read(os.path.join(SDSYS, "messages", str(n))) if os.path.exists(os.path.join(SDSYS, "messages", str(n))) else None) for n in MSGS}
    return s


FAKE_TREE = "/tmp/sdsolo-test-tree"


def printed_units(script=None):
    """The units `solo-service.sh ai <tree> --print` prints for a scratch tree that has what the script asks of one (bin/sd-solo and the .sdcoresolo marker): nothing outside the
    scratch directory is touched.  FAKE_TREE is where the scratch tree is made, so the printed paths are known."""
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix="sdsolo-test-tree-")
    try:
        os.makedirs(os.path.join(d, "bin"))
        with open(os.path.join(d, "bin", "sd-solo"), "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(os.path.join(d, "bin", "sd-solo"), 0o755)
        open(os.path.join(d, ".sdcoresolo"), "w").close()
        r = subprocess.run(["bash", script or FILES["solo-service.sh"], "ai", d, "--print"], capture_output=True, text=True)
        r.stdout = r.stdout.replace(d, FAKE_TREE)
        return r
    finally:
        shutil.rmtree(d, ignore_errors=True)


def checks(s, run_print=True):
    rows = []

    def ck(name, ok, detail=""):
        rows.append((name, bool(ok), detail))

    ai_py = strip_py(s["sd-ai"])
    ctl = strip_py(s["sd-ai-ctl"])
    runner = strip_py(s["ai-runner"])
    own = ai_py[ai_py.find("def own_user"):ai_py.find("# ----", ai_py.find("def own_user"))]
    handle = ai_py[ai_py.find("def handle("):ai_py.find("def serve(")]
    adm_op = ai_py[ai_py.find("def admin_op("):ai_py.find("def handle(")]
    kc = strip_c(s["op_ai.c"])
    ai_b = strip_bas(s["ai"])
    set_b = strip_bas(s["setai"])
    page = strip_bas(s["tool_ai"])
    svc = strip_sh(s["solo-service.sh"])

    # ------------------------------------------------------------------------------------------------ the helper
    ck("H1 no Linux group and no administrator name is left in the helper: no grp or pwd import, no GATE_GROUP, ADMIN_USER, in_group or is_admin",
       not re.search(r"\bimport (grp|pwd)\b|GATE_GROUP|ADMIN_USER|\bin_group\b|\bis_admin\b|sdaiusers|sdsys", ai_py), "")
    ck("H2 own_user() is true only for a known uid equal to the helper's own (None, a stranger and every doubt are false)", "return uid is not None and uid == os.getuid()" in own, own[:200])
    ck("H3 gate_on() is exactly gate=yes: nothing absent, empty or misspelt can open it", 'return conf.get("gate", "") == "yes"' in ai_py, "")
    ck("H4 handle(): the stranger is refused with nogate BEFORE the settings are changed, before ai.conf is read and before the gate is looked at",
       ordered(handle, "peer_uid(fd)", "if not own_user(uid):", '"code": "nogate"', "admin_op(", "parse_kv(", "if not gate_on(conf):"), handle[:400])
    ck("H5 status is answered with the gate off (the page needs it) and reports the gate; a request to ASK is refused with nogate while the gate is off, before the provider, the model and the key are looked at",
       ordered(handle, 'req["op"] == "status"', "status_reply(", "if not gate_on(conf):", "selected(conf, table)", "read_key(") and '"gate": gate_on(conf)' in ai_py, "")
    ck("H6 the gate setting: yes or no only (badreq otherwise), stored as the line gate=yes, and OFF IS THE ABSENCE OF THE LINE",
       'if v not in ("yes", "no"):' in adm_op and 'new["gate"] = "yes" if v == "yes" else ""' in adm_op
       and 'if conf[k] != "" or k == "provider":' in ai_py[ai_py.find("def write_conf"):ai_py.find("def write_key")], "")
    ck("H7 ai.conf is written whole and atomically with mode 0600; a key file with mode 0600; the state directories are made 0700 by the helper",
       ai_py.count("0o640") == 0 and "0o600" in ai_py[ai_py.find("def write_conf"):ai_py.find("def write_key")] and "os.replace(tmp, path)" in ai_py
       and 'os.makedirs(os.path.join(state, sub), mode=0o700, exist_ok=True)' in adm_op, "")
    ck("H8 the key file must be private before it is read (a file others can read is refused), a link is not followed", "st.st_mode & 0o077" in ai_py and "os.lstat(path)" in ai_py, "")
    ck("H9 the defaults are the tree's own: <tree>/ai for the state and tools/ai-providers beside the helper",
       'DEFAULT_STATE = os.path.join(os.path.dirname(TOOLS), "ai")' in ai_py and 'DEFAULT_PROVIDERS = os.path.join(TOOLS, "ai-providers")' in ai_py, "")
    ck("H10 the helper says what is weaker than Core's: the weakness paragraph (a process of the same user can reach the key) is in its head",
       "THAT IS THE WEAKNESS" in s["sd-ai"] and "no safer" in s["sd-ai"], "")
    ck("H11 the client: the default socket is $XDG_RUNTIME_DIR/sd-solo-ai.sock (or /run/user/<uid>), SD_AI_SOCKET and --socket override, gate on|off is a set request with yes / no",
       'sd-solo-ai.sock' in ctl and "XDG_RUNTIME_DIR" in ctl and '"what": "gate"' in ctl and '"yes" if rest == ["on"] else "no"' in ctl and 'rest in (["on"], ["off"])' in ctl, "")
    ck("H12 the client never takes a key as an argument and never prints it: getpass for a terminal, stdin otherwise", "getpass.getpass" in ctl and "sys.stdin.readline()" in ctl and 'print("The key for %s is set."' in ctl, "")
    ck("H13 the test runner has no administrator and no group to replace and makes the socket mode 0600", "--admin-user" not in runner and "--gate-group" not in runner and "os.chmod(opts[\"--socket\"], 0o600)" in runner, "")

    # ------------------------------------------------------------------------------------------------ the units
    if run_print:
        r = printed_units()
        t = r.stdout
        ck("U1 `solo-service.sh ai <tree> --print` runs, writes nothing and prints the two units (exit 0)", r.returncode == 0 and "# sd-solo-ai.socket" in t and "# sd-solo-ai@.service" in t, (r.stderr or "")[:200])
        ck("U2 the socket is a Unix socket in the user's runtime directory, mode 0600, Accept=true, with NO network address", "ListenStream=%t/sd-solo-ai.sock" in t and "SocketMode=0600" in t and "Accept=true" in t
           and not re.search(r"ListenStream=(\d|\[|0\.0\.0\.0|127\.)", t), t[:300])
        ck("U3 the service runs the tree's own helper with the state and the providers table named, as the user (no User= line), with the socket as stdin and stdout and a time limit",
           "ExecStart=/usr/bin/python3 /tmp/sdsolo-test-tree/tools/sd-ai --state /tmp/sdsolo-test-tree/ai --providers /tmp/sdsolo-test-tree/tools/ai-providers" in t.replace(shutil_python(t), "/usr/bin/python3")
           and "StandardInput=socket" in t and "StandardOutput=socket" in t and "RuntimeMaxSec=330" in t and "User=" not in t, t[-500:])
        ck("U4 what a user manager always allows is kept: NoNewPrivileges, a restricted set of address families, MemoryDenyWriteExecute and a private umask", "NoNewPrivileges=yes" in t and "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in t
           and "MemoryDenyWriteExecute=yes" in t and "UMask=0077" in t, t[-400:])
    ck("U5 install writes the pair after the ssh units and before the final line, remove disables and deletes them and checks they are gone, status lists them",
       ordered(svc, 'ssh_apply "$H" "$ssh"', 'ai_apply "$H"', 'echo "SOLO SERVICE READY') and 'disable --now "$AI_SOCKET"' in svc and '"$AI_SOCKET" "$AI_TEMPLATE" "$SOCKET"' in svc
       and 'for u in "$DAEMON" "$SOCKET" "$SSH_SOCKET" "$AI_SOCKET"; do' in svc and '"$AI_SOCKET" "$AI_TEMPLATE"; do' in svc, "")
    ck("U6 one pair per user: a pair that names another tree is refused, and the unit is not written before the helper is known to be there",
       ordered(svc, 'grep -qF -e " $tree/tools/sd-ai "', "belong to another Solo tree", '[ -f "$tree/tools/sd-ai" ]', 'ai_socket_text > "$UNITDIR/$AI_SOCKET"'), "")
    ck("U7 the final line the installer anchors on is unchanged: SOLO SERVICE READY daemon= api= ssh= linger=", 'echo "SOLO SERVICE READY daemon=$d_state api=$api ssh=$ssh linger=$lg"' in svc, "")
    ck("U8 the stager copies the helper, its client and the providers table into tools/, mode 0755 for the two programs", re.search(r'cp gplbld/sd-ai gplbld/sd-ai-ctl gplbld/ai-providers "\$H/tools/"', s["solo-stage.sh"])
       and 'chmod 0755 "$H/tools/sd-ai" "$H/tools/sd-ai-ctl"' in s["solo-stage.sh"], "")
    inst = strip_sh(s["installsdsolo.sh"])
    ck("U9 an UPGRADE writes the units too (an install from before this release has none), inside the branch that has a service, after the ssh block, and a refusal does not stop the upgrade",
       ordered(inst, 'solo-service.sh" ssh "$HOME_DIR" "$ssh"', 'solo-service.sh" ai "$HOME_DIR" 2>&1 | tail -2 || true', 'There was no service; starting SD directly'), "")
    ck("U10 the remover's fallback (no solo-service.sh left) takes the two AI units as well", "sd-solo-ai.socket" in s["deletesdsolo.sh"] and "sd-solo-ai@.service" in s["deletesdsolo.sh"], "")

    # ------------------------------------------------------------------------------------------------ the kernel
    ck("K1 the numbers are Core's, 160 to 163, the same in keys.h and int$keys.h",
       all(re.search(r"#define K_AI_%s\s+%d\b" % (n, v), s["keys.h"]) for n, v in (("START", 160), ("POLL", 161), ("CANCEL", 162), ("STATUS", 163)))
       and all(re.search(r"\$define K\$AI\.%s\s+%d\b" % (n, v), s["int$keys.h"]) for n, v in (("START", 160), ("POLL", 161), ("CANCEL", 162), ("STATUS", 163))), "")
    ck("K2 k_ai is declared, dispatched from op_kernel for the four keys, and op_ai is in gpl.src", "k_ai(int action" in s["sd.h"] and all("case K_AI_%s:" % n in strip_c(s["op_kernel.c"]) for n in ("START", "POLL", "CANCEL", "STATUS"))
       and "k_ai(action, descr, &result);" in strip_c(s["op_kernel.c"]) and re.search(r"^op_ai$", s["gpl.src"], re.M), "")
    ck("K3 only a $internal program may use it: the first statement of k_ai refuses with ERR internal", ordered(kc, "void k_ai(int action", "HDR_INTERNAL", 'ai_answer("ERR", "internal"', "switch (action)"), "")
    ck("K4 THE AUDIT LINE IS WRITTEN BEFORE THE CONNECTION: audit_message, then the request is built, then ai_connect; the line holds the account, the program and the size and never the text",
       ordered(kc, "void ai_start(", "audit_message(audit);", "ai.fd = ai_connect();") and "ai request account=%s program=%s bytes.out=%d" in kc and "account()" in kc, "")
    ck("K5 the default socket is the user's own: /run/user/<uid>/sd-solo-ai.sock from getuid(), and SD_AI_SOCKET alone overrides", '"/run/user/%d/sd-solo-ai.sock", (int)getuid()' in kc and 'getenv("SD_AI_SOCKET")' in kc and "/run/sd-ai" not in kc, "")
    ck("K6 a request is an ask and nothing else (the settings are not reachable from here): the only op written is ask, the others come from the status call", kc.count('\\"op\\":\\"ask\\"') == 1 and kc.count('\\"op\\":\\"status\\"') == 1
       and "set" not in re.findall(r'\\"op\\":\\"(\w+)\\"', kc), "")

    # ------------------------------------------------------------------------------------------------ the verbs
    ck("V1 the ai verb asks for the provider (11624) BEFORE the gate (11625) BEFORE the model and the key (11626), and before any preview or request",
       ordered(ai_b, "if prov = '' then", "sysmsg(11624)", "if not(st{'gate'}) then", "sysmsg(11625", "if model = '' then", "if not(st{'key'}) then", "K$AI.START"), "")
    ck("V2 nothing is sent unless the answer is y or yes", "if ans # 'y' and ans # 'yes' then" in ai_b and ordered(ai_b, "input ans", "if ans # 'y' and ans # 'yes' then", "K$AI.START"), "")
    ck("S1 SET.AI is the administrator's: the test is the first statement that does anything", ordered(set_b, "program set.ai", "kernel(K$ADMINISTRATOR, -1)", "sysmsg(2001)", "ctl = env('SD_AI_CTL')"), "")
    ck("S2 the helper's client is <tree>/tools/sd-ai-ctl (@sdsys), SD_AI_CTL only for the tests, and a path with a character a command line may not carry is refused", "@sdsys : @ds : 'tools' : @ds : 'sd-ai-ctl'" in set_b and "env('SD_AI_CTL')" in set_b
       and "stop sysmsg(11607)" in set_b, "")
    ck("S3 the gate word: set.ai gate on|off only, through the client, audited as set.ai gate=on|off after the helper said ok, and the message is 11606",
       ordered(set_b, "case sub = 'gate' and n.words = 3", "qargs = \"'gate' '\" : gstate", "gosub run.ctl", "gosub need.ok", "'set.ai gate=' : gstate", "sysmsg(11606, gstate)"), "")
    ck("S4 every word of the sentence is checked against the allowed characters before anything is run", ordered(set_b, "okc = ", "for i = 2 to n.words", "sysmsg(11622", "begin case"), "")
    ck("S5 THE KEY NEVER PASSES THROUGH SD: SET.AI KEY hands the terminal to the client (os.execute with no capturing), the verb reads back only the listing", ordered(set_b, "sub = 'key' and n.words = 3", "os.execute \"'\" : ctl : \"' 'key' '\"", "check.key")
       and "capturing" not in set_b[set_b.find("sub = 'key' and n.words = 3"):set_b.find("sub = 'custom' and n.words = 3")], "")
    ck("P1 the page is the administrator's (the toolkit's 'admin' profile), runs only SET.AI through $tk_runx, never modify.account, never $tk_gates and never $tk_run",
       "$tk_open('tool.ai', 'admin'" in page and "allow.set = 'set.ai'" in page and "modify.account" not in page and "$tk_gates" not in page and "call $tk_run(" not in page and page.count("call $tk_runx(") == 1, "")
    ck("P2 every change goes through $tk_confirm before it runs, and turning the gate ON asks for the word ai to be typed, OFF asks for none",
       ordered(page, "confirm.and.run:", "call $tk_confirm(sent, el, typed, res, cmsg)", "if res = 'run' then", "call $tk_runx(allow.set, sent, out, st, err)")
       and ordered(page, "toggle.gate:", "sent = 'set.ai gate '", "typed = ''", "typed = 'ai'", "gosub confirm.and.run"), "")
    ck("P3 the page says what Solo's helper cannot promise: the ON confirmation names that Solo runs the helper as the user", "Solo runs the AI helper as you" in page, "")
    ck("P4 the Account box is one row, read from the helper's status (no register, no $tk_gates), and the gate shows off when the helper cannot be reached",
       "read.accounts:" in page and "an = 1" in page and "if hj{'gate'} then ast = 1" in page and "openpath @sdsys:@ds:'accounts'" not in page, "")
    ck("P5 the key is typed at the helper's prompt: the page gives the terminal to SET.AI KEY (execute sent) and takes the screen again", ordered(page, "do.key:", "call $tk_confirm(sent, el, '', res, cmsg)", "call $tk_close(ctx)", "execute sent", "gosub reopen"), "")
    ck("P6 tk_runx is the toolkit's wider $tk_run: capitals and : / @ + , - are allowed in a word and nothing else", "A-Z" in strip_bas(s["tk_runx"]) or "ABCDEFGHIJKLMNOPQRSTUVWXYZ" in strip_bas(s["tk_runx"]), "")

    # ------------------------------------------------------------------------------------------------ the VOC and the words
    ck("W1 ai is in every account's VOC (newvoc) and in SDSYS's (voc_template); set.ai and tool.ai too (Solo's single account is also the administrator: the program refuses the rest)",
       all(re.search(r"(?m)^\$%s$" % pg, s[k]) for k, pg in (("newvoc/ai", "ai"), ("voc_template/ai", "ai"), ("newvoc/set.ai", "setai"), ("voc_template/set.ai", "setai"), ("newvoc/tool.ai", "tool_ai"), ("voc_template/tool.ai", "tool_ai"))), "")
    bad = [n for n in MSGS if s["msgs"][n] is None]
    ck("W2 messages 11606 to 11634 exist, each one line", not bad and all(len(s["msgs"][n].rstrip("\n").split("\n")) == 1 for n in MSGS if s["msgs"][n] is not None), repr(bad))
    ck("W3 the three Solo wordings: 11606 says the gate, 11609 names the gate word, 11625 names set.ai gate on",
       s["msgs"][11606] == "The AI gate is now %1\n" and "set.ai {gate on|off |" in s["msgs"][11609] and "set.ai gate on" in s["msgs"][11625] and "modify.account" not in s["msgs"][11625], "")
    ck("W4 no message of the block names a command word in capitals or a Linux group Solo does not make", not any(re.search(r"[A-Z]{3,}\.[A-Z]|sdaiusers|sdai\b", (s["msgs"][n] or "")) for n in MSGS), "")
    ck("W5 the help records say the weakness in plain words and name the Solo document page", "any process you run can talk to it" in s["helptext/accounts"] and "24-the-ai-helper" in s["helptext/accounts"]
       and "24-the-ai-helper" in s["helptext/providers"] and "sdai" not in s["helptext/providers"].replace("sdaiusers", "") and "sdaiusers" not in s["helptext/accounts"], "")
    return rows


def shutil_python(t):
    m = re.search(r"ExecStart=(\S+) /tmp/sdsolo-test-tree/tools/sd-ai", t)
    return m.group(1) if m else "/usr/bin/python3"


# Each mutant breaks one rule the way an edit plausibly would: (name, file key, old, new, the check that must notice)
MUTANTS = [
    ("the stranger is not refused", "sd-ai", "    if not own_user(uid):", "    if False:", "H4"),
    ("every uid is the helper's own", "sd-ai", "    return uid is not None and uid == os.getuid()", "    return True", "H2"),
    ("any gate word opens it", "sd-ai", '    return conf.get("gate", "") == "yes"', '    return conf.get("gate", "") != ""', "H3"),
    ("the gate is not asked", "sd-ai", "        if not gate_on(conf):\n", "        if False:\n", "H5"),
    ("ai.conf is made group readable", "sd-ai", "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n    with os.fdopen(fd, \"w\", encoding=\"ascii\") as f:\n        f.write(\"\\n\".join(lines)",
     "    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)\n    with os.fdopen(fd, \"w\", encoding=\"ascii\") as f:\n        f.write(\"\\n\".join(lines)", "H7"),
    ("the socket takes a network address", "solo-service.sh", "ListenStream=%t/sd-solo-ai.sock", "ListenStream=127.0.0.1:4260", "U2"),
    ("the socket is group readable", "solo-service.sh", "SocketMode=0600\nAccept=true\nMaxConnections=16", "SocketMode=0660\nAccept=true\nMaxConnections=16", "U2"),
    ("the upgrade does not write the units", "installsdsolo.sh", 'bash "$HOME_DIR/tools/solo-service.sh" ai "$HOME_DIR" 2>&1 | tail -2 || true', ":", "U9"),
    ("the audit line comes after the connection", "op_ai.c", "  audit_message(audit);\n", "", "K4"),
    ("a program that is not internal may call it", "op_ai.c", "  if (!(process.program.flags & HDR_INTERNAL)) {", "  if (0) {", "K3"),
    ("the gate is checked after the model", "ai", "   if not(st{'gate'}) then", "   if @false then", "V1"),
    ("turning the gate on asks for nothing", "tool_ai", "      typed = 'ai'\n", "      typed = ''\n", "P2"),
    ("the page runs modify.account", "tool_ai", "allow.set = 'set.ai'", "allow.set = 'set.ai modify.account'", "P1"),
    ("the key is captured by SD", "setai", "         os.execute \"'\" : ctl : \"' 'key' '\" : prov : \"' 2>&1\"", "         os.execute \"'\" : ctl : \"' 'key' '\" : prov : \"' 2>&1\" capturing junk", "S5"),
    ("the gate word is not audited", "setai", "         void kernel(K$AUDIT, 'set.ai gate=' : gstate)\n", "", "S3"),
    ("11625 sends the person to a Core command", "msgs", None, None, "W3"),
]


def run(srcs_override=None, run_print=True):
    s = load()
    if srcs_override:
        s.update(srcs_override)
    return checks(s, run_print)


def selftest(first=0):
    base = run()
    base_fail = {n.split()[0] for n, ok, _ in base if not ok}
    print("selftest: the unchanged tree fails %d check(s): %s" % (len(base_fail), ", ".join(sorted(base_fail)) or "none"))
    if base_fail:
        print("selftest: the tree is not whole, so a mutant's own failure cannot be told from the tree's; run the plain check first")
        return 1
    s0 = load()
    bad = 0
    for name, key, old, new, want in MUTANTS[first:]:
        try:
            if key == "msgs":
                msgs = dict(s0["msgs"])
                msgs[11625] = "This account may not use the AI: the administrator can allow it with modify.account %1 ai-on\n"
                over = {"msgs": msgs}
            else:
                if s0[key].count(old) != 1:
                    print("  [FAIL] selftest: %s: the old text occurs %d times in %s, not once" % (name, s0[key].count(old), key))
                    bad += 1
                    continue
                over = {key: s0[key].replace(old, new)}
            rows = run(over, run_print=(key != "solo-service.sh"))
            if key == "solo-service.sh":
                # the printed units come from the real script: a mutant of the script's text is judged on a scratch copy
                import tempfile, shutil
                d = tempfile.mkdtemp(prefix="aisolo-mut-")
                try:
                    p = os.path.join(d, "solo-service.sh")
                    with open(p, "w") as f:
                        f.write(over[key])
                    r = printed_units(p)
                    t = r.stdout
                    hit = bool(re.search(r"ListenStream=(\d|\[|0\.0\.0\.0|127\.)", t)) or "SocketMode=0600" not in t
                    failed = ["U2"] if hit else []
                finally:
                    shutil.rmtree(d, ignore_errors=True)
            else:
                failed = [n.split()[0] for n, ok, _ in rows if not ok]
        except Exception as exc:
            print("  [FAIL] selftest: %s  <- %s" % (name, exc))
            bad += 1
            continue
        hit = want in failed
        print("  [%s] selftest: %s is caught by %s (failed: %s)" % ("PASS" if hit else "FAIL", name, want, " ".join(failed) or "none"))
        bad += 0 if hit else 1
    print("selftest: %s" % ("every mutant was caught" if bad == 0 else "%d problem(s)" % bad))
    return 0 if bad == 0 else 1


def main(argv):
    for k, p in FILES.items():
        if not os.path.exists(p):
            print("test-ai-solo-units: CANNOT RUN - %s is missing (%s)" % (k, p))
            return 2
    if "--selftest" in argv:
        first = 0
        for a in argv:
            if a.startswith("--from="):
                first = int(a[len("--from="):])
        return selftest(first)
    rows = run()
    bad = 0
    for n, ok, d in rows:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", n, "" if ok else "   <- " + str(d)[:300]))
        bad += 0 if ok else 1
    print("test-ai-solo-units: %d checks, %d failed" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
