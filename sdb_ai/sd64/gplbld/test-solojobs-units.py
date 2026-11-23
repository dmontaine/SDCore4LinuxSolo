#!/usr/bin/env python3
"""test-solojobs-units.py - Solo's scheduled jobs (S.247, 17 Nov 2026): SET.JOB, RUN.JOB, SET.JOBS.ACCESS, the TOOL.JOBS page and the scripts' parts, as invariants.

    python3 /home/don/SDCoreProject/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-solojobs-units.py [--selftest]

FREE: no install, no sudo, no sd, and NEVER the real systemd user manager (the deleter's step is run with systemctl a stub, on a scratch directory).
Exit 0 every check passed, 1 a check failed, 2 it could not run.

WHAT IT HOLDS (the owner, 15 Nov 2026: "your plan is fine" - off as delivered, a job made only with the password typed, its command fixed then, the
user's own timers; the plan is .claude/plan-s247-solo-jobs.md in SD Core for Linux's private record):
  J1  the switch is field 23 (ACC$JOBS), and only 'yes' is on; SET.JOBS.ACCESS asks for the administrator first and writes that field alone
  J2  SET.JOB: ADD, CHANGE, RUN and RESTORE ask the switch before anything is changed; DELETE and the list do not need it
  J3  ADD and CHANGE ask for the account password (typed at a terminal, or from the page's hand-over) BEFORE the definition is written; a one-shot or a
      session with no terminal is refused (14941); one try
  J4  the name rule and the five schedules are SD Core's, each with the OnCalendar SD Core's root helper writes for it
  J5  a command is printable ASCII, at most 500 characters, not RUN.JOB or SET.JOB; it is kept in $jobs and never written into a unit file
  J6  the units: Type=oneshot, ExecStart <tree>/bin/sd-solo "run.job <name>", After=sd-solo.service, Persistent=false, WantedBy=timers.target; a link in
      the way is refused; each file is written to a temporary name and renamed
  J7  the hand-over file is read and REMOVED before anything is decided; a first line other than add or change is refused
  J8  RUN.JOB runs only as the one-shot "run.job <name>", asks the switch at every run, audits the start and the end, and EXECUTEs the definition's command
  J9  RESTORE is the installer's internal session's word only
  J10 the page runs SET.JOB and nothing else, through $tk_run after a box answered Run; N and C have a masked password field; D asks for the name typed
  J11 the deleter removes the job units first (timers disabled, services stopped, files gone) - RUN here on a scratch directory with systemctl a stub -
      and keeps $jobs with the data; the installer's kept-tree test and the stage's reload take $jobs; the stage gives the timers back after a reload
  J12 the messages the programs cite exist, and the VOC records name the programs
It cannot say systemd runs a job, or that a timer fires: that is a real Solo install (the units are the user's real manager's).
--selftest breaks each invariant the way an edit plausibly would and requires a check to notice.
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SD64 = os.path.normpath(os.path.join(HERE, ".."))
ROOT = os.path.normpath(os.path.join(SD64, "..", ".."))
SDSYS = os.path.join(SD64, "sdsys")
GPL = os.path.join(SDSYS, "gpl.bp")
FILES = {
    "job": os.path.join(GPL, "solojob"),
    "run": os.path.join(GPL, "runjob"),
    "acc": os.path.join(GPL, "setjobsacc"),
    "page": os.path.join(GPL, "tool_solojobs"),
    "keys": os.path.join(SDSYS, "syscom", "keys.h"),
    "deleter": os.path.join(ROOT, "deletesdsolo.sh"),
    "installer": os.path.join(ROOT, "installsdsolo.sh"),
    "stage": os.path.join(HERE, "solo-stage.sh"),
}
VOCS = {"set.job": "$solojob", "run.job": "$runjob", "set.jobs.access": "$setjobsacc", "tool.jobs": "$tool_solojobs"}


def load():
    raw = {}
    for k, p in FILES.items():
        try:
            with open(p, encoding="latin-1") as f:
                raw[k] = f.read()
        except OSError:
            raw[k] = None
    for v in VOCS:
        for d in ("newvoc", "voc_template"):
            p = os.path.join(SDSYS, d, v)
            try:
                with open(p, encoding="latin-1") as f:
                    raw[d + "/" + v] = f.read()
            except OSError:
                raw[d + "/" + v] = None
    return raw


def code(src):
    """BASIC with comment lines and ;* tails removed."""
    out = []
    for ln in (src or "").split("\n"):
        if re.match(r"^\s*\*", ln):
            continue
        out.append(re.sub(r"\s*;\*.*$", "", ln))
    return "\n".join(out)


def block(text, label):
    """A routine: from its label to the next label (an inner return does not end it)."""
    m = re.search(r"^" + re.escape(label) + r":\s*$(.*?)(?=^[a-z][a-z0-9.]*:\s*$|\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def shell_block(text, begin, end):
    m = re.search(r"^\s*# " + re.escape(begin) + r"\s*$(.*?)^\s*# " + re.escape(end) + r"\s*$", text or "", re.M | re.S)
    return m.group(1) if m else ""


def run_remove_job_units(deleter_text):
    """J11: cut remove_job_units out of the deleter and run it on a scratch unit directory; systemctl is a function that logs its arguments."""
    m = re.search(r"^remove_job_units\(\) \{.*?^\}\s*$", deleter_text or "", re.M | re.S)
    if not m:
        return None, "no remove_job_units function"
    d = tempfile.mkdtemp(prefix="solojobs-")
    try:
        ud = os.path.join(d, "units")
        os.makedirs(os.path.join(ud, "timers.target.wants"))
        for f in ("sd-solo-job-a.timer", "sd-solo-job-a.service", "sd-solo-job-b-2.timer", "sd-solo-job-b-2.service", "sd-solo.service", "other.timer"):
            with open(os.path.join(ud, f), "w") as fh:
                fh.write("x\n")
        os.symlink("../sd-solo-job-a.timer", os.path.join(ud, "timers.target.wants", "sd-solo-job-a.timer"))
        log = os.path.join(d, "log")
        script = "set -uo pipefail\nsystemctl() { printf '%s\\n' \"$*\" >> '" + log + "'; return 0; }\n" + m.group(0) + "\nremove_job_units '" + ud + "'\necho DONE\n"
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30)
        left = sorted(os.listdir(ud)) + sorted("w/" + x for x in os.listdir(os.path.join(ud, "timers.target.wants")))
        calls = open(log).read().split("\n") if os.path.exists(log) else []
        return {"rc": r.returncode, "out": r.stdout, "left": left, "calls": [c for c in calls if c]}, ""
    finally:
        subprocess.run(["rm", "-rf", "--", d])


def checks(raw):
    rows = []

    def ck(i, what, ok, detail=""):
        rows.append((i, what, bool(ok), detail))

    missing = [k for k, v in raw.items() if v is None and not k.startswith("newvoc/") and not k.startswith("voc_template/")]
    if missing:
        ck("J0", "every file this check reads exists", False, ", ".join(missing))
        return rows
    jb, rn, ac, pg = code(raw["job"]), code(raw["run"]), code(raw["acc"]), code(raw["page"])

    # J1
    ck("J1", "the switch is field 23 (ACC$JOBS) and only 'yes' is on; SET.JOBS.ACCESS asks for the administrator before it opens the register, writes ACC$JOBS alone, under a lock",
       re.search(r"\$define ACC\$JOBS\s+23\b", raw["keys"]) and ac.find("if not(kernel(K$ADMINISTRATOR, -1)) then") >= 0
       and ac.find("if not(kernel(K$ADMINISTRATOR, -1)) then") < ac.find("openpath")
       and "if jb.want then acc.new<ACC$JOBS> = 'yes' else acc.new<ACC$JOBS> = 'no'" in ac and len(re.findall(r"acc\.new<ACC\$[A-Z.]+>\s*=", ac)) == 2
       and "readu acc.rec from acc.f, acc.name else" in ac
       and "if upcase(trim(sw.rec<ACC$JOBS>)) = 'YES' then sw.on = @true" in jb and "if upcase(trim(sw.rec<ACC$JOBS>)) = 'YES' then sw.on = @true" in rn)

    # J2
    main = jb.split("* ------------------------------------------------------------------------------------------------- the actions")[0]
    i_sw = main.find("if action # 'delete' then\n      gosub switch.on")
    i_open = main.find("gosub open.jobs\n   if not(ok)")
    ck("J2", "ADD, CHANGE and RUN ask the switch before the definitions are opened, DELETE does not, the list says it; RESTORE is outside that test but writes no definition",
       i_sw > 0 and i_open > i_sw and "stop sysmsg(14948)" in main[i_sw:i_open] and "gosub switch.on" in block(jb, "list.jobs"))

    # J3
    ds = block(jb, "do.set")
    ck("J3", "ADD and CHANGE ask for the password before the definition is written; it is the account's (CRED_VERIFY of sduser), one try, refused with no terminal or in a one-shot",
       0 < ds.find("gosub ask.password") < ds.find("write new.rec to jobs.f, jname")
       and "if kernel(K$TTY, 0) = '' or trim(system(1026)) # '' then" in block(jb, "ask.password")
       and "call !CRED_VERIFY(acc.name, pw.text, pw.match)" in jb and "call !CRED_VERIFY(acc.name, ho.pw, pw.match)" in jb
       and "acc.name = 'sduser'" in jb and "for pw." not in block(jb, "ask.password"))

    # J4
    so = block(jb, "sched.ok")
    ck("J4", "the name rule and the five schedules with SD Core's OnCalendar: every N minutes *-*-* *:0/N:00, hourly *-*-* *:00:00, daily *-*-* hh:mm:00, weekly Ddd *-*-* hh:mm:00, monthly *-*-D hh:mm:00",
       "if convert('abcdefghijklmnopqrstuvwxyz0123456789-', '', jname) # '' then return" in block(jb, "name.ok") and "if len(jname) < 1 or len(jname) > 32 then return" in block(jb, "name.ok")
       and "cal = '*-*-* *:0/' : s2 : ':00'" in so and "(s2 = '5' or s2 = '10' or s2 = '15' or s2 = '20' or s2 = '30')" in so
       and "cal = '*-*-* *:00:00'" in so and "cal = '*-*-* ' : tm : ':00'" in so and "cal = upcase(s2[1, 1]) : s2[2, 2] : ' *-*-* ' : tm : ':00'" in so
       and "cal = '*-*-' : dd : ' ' : tm : ':00'" in so and "dd >= 1 and dd <= 28" in so and "if hh > 23 or mm > 59 then return" in block(jb, "time.ok"))

    # J5
    co = block(jb, "cmd.ok")
    wu = block(jb, "write.units")
    ck("J5", "a command is printable ASCII (32-126), at most 500, not run.job or set.job; it is field 3 of the definition and never part of a unit file",
       "if cc < 32 or cc > 126 then return" in co and "$define MAX.CMD    500" in raw["job"] and "if cw = 'run.job' or cw = 'set.job' then return" in co
       and "new.rec = sched : @fm : cal : @fm : jcmd" in ds and "jcmd" not in wu and "rec<3>" in rn)

    # J6
    ck("J6", "the units: oneshot, ExecStart sd-solo \"run.job NAME\", After=sd-solo.service, Persistent=false, WantedBy=timers.target; a link refused; written to a temporary name and renamed",
       "svc<-1> = 'Type=oneshot'" in wu and "svc<-1> = 'ExecStart=' : sd.bin : ' \"run.job ' : jname : '\"'" in wu and "svc<-1> = 'After=sd-solo.service'" in wu
       and "tmr<-1> = 'Persistent=false'" in wu and "tmr<-1> = 'WantedBy=timers.target'" in wu and "if [ -L '" in wu and "mv -f '." in wu
       and "sd.bin = @sdsys : @ds : 'bin' : @ds : 'sd-solo'" in jb)

    # J7
    rh = block(jb, "read.handover")
    i_rm = rh.rfind("cmd = \"rm -f '\" : ho.file : \"'\"")
    ck("J7", "the hand-over file is read, then removed, before its action is judged; only add or change is taken; a link or a missing file is refused and removed",
       "ho.file = @sdsys : @ds : '$jobsho' : @ds : 'req'" in rh and 0 < rh.find("readseq") < i_rm < rh.find("ho.action = downcase(trim(ho.lines<1>))")
       and "if ho.action # 'add' and ho.action # 'change' then return" in rh and "[ ! -L '" in rh)

    # J8
    i_one = rn.find("if not(ok.call) then")
    i_swr = rn.find("if not(sw.on) then")
    i_ex = rn.find("execute jcmd")
    ck("J8", "RUN.JOB: only as the one-shot 'run.job NAME' (system(1026)), then the name rule, then the switch, then the definition; the start and the end are audited around the EXECUTE",
       0 < i_one < i_swr < rn.find("if jcmd = '' then") < i_ex and "one = trim(system(1026))" in rn
       and rn.find("'run.job start name='") < i_ex < rn.find("'run.job end name='") and rn.count("execute ") == 1
       and re.search(r"@system\.return\.code = 0\s*\n\s*execute jcmd", rn) is not None)        # 17 Nov 26: a command that sets no code is status 0 (witness-s247 J4b saw -1)

    # J9
    ck("J9", "RESTORE only for the installer's internal session",
       "if not(kernel(K$INTERNAL, -1)) then stop sysmsg(14945)" in main and main.find("if not(kernel(K$INTERNAL, -1)) then") < main.find("gosub restore.all"))

    # J10
    ck("J10", "the page runs set.job alone, through $tk_run after a confirm box answered Run; the password field is masked (kind 1); D asks for the name typed; the hand-over directory is made 0700",
       "allow = 'set.job'" in pg and pg.count("allow = ") == 1 and pg.count("call $tk_run(") == 2 and "call $tk_run(allow, 'set.job', jout, jst, jrerr)" in pg
       and "spec<-1> = 'pw' : @vm : 'Account password' : @vm : 34 : @vm : 64 : @vm : 1" in pg
       and "call $tk_confirm(sent, el, fname, res, cmsg)" in block(pg, "job.delete") and "chmod 700 '" in block(pg, "hand.over")
       and block(pg, "job.confirm").find("call $tk_confirm(sent, el, '', res, cmsg)") < block(pg, "job.confirm").find("gosub hand.over")
       and not re.search(r"^\s*(?:execute|perform|chain|write[uv]?|delete[uv]?)\b", pg, re.M))

    # J11
    r, why = run_remove_job_units(raw["deleter"])
    if r is None:
        ck("J11", "the deleter's remove_job_units runs", False, why)
    else:
        ck("J11", "the deleter's remove_job_units, run on a scratch directory: every sd-solo-job unit and its wants link gone, sd-solo.service and other.timer left; each timer disabled --now, each service stopped",
           r["rc"] == 0 and "DONE" in r["out"] and r["left"] == ["other.timer", "sd-solo.service", "timers.target.wants"]
           and "--user disable --now sd-solo-job-a.timer" in r["calls"] and "--user disable --now sd-solo-job-b-2.timer" in r["calls"]
           and "--user stop sd-solo-job-a.service" in r["calls"] and "--user stop sd-solo-job-b-2.service" in r["calls"], repr(r))
    rus = shell_block(raw["deleter"], "BEGIN remove_units", "END remove_units")
    ck("J11b", "the deleter runs it first in remove_units_step, its unit test sees timers, and keep_prune keeps $jobs; the installer's kept-tree test and the stage's reload take $jobs; the stage restores after a reload",
       re.search(r"remove_units_step\(\) \{[^\n]*\n[^\n]*\n\s*remove_job_units \"\$unitdir\"", rus) is not None and '"$d"/sd-solo*.timer' in rus
       and "for n in newvoc.mods voc_removed.saved '$cred' '$jobs' accounts sd-tls sshd ai netlogins; do" in raw["deleter"]
       and "'$cred'|'$jobs'|accounts|sd-tls|sshd|ai|netlogins)" in raw["installer"] and "for kept_item in '$cred' '$jobs' sd-tls sshd ai netlogins; do" in raw["stage"]
       and "sdi SET.JOB RESTORE" in shell_block(raw["stage"], "JOBS-RESTORE-BEGIN", "JOBS-RESTORE-END")
       and raw["stage"].find("# JOBS-RESTORE-BEGIN") < raw["stage"].find('echo "SOLO RELOAD DONE'))

    # J12
    cited = set(re.findall(r"sysmsg\((\d+)", jb + rn + ac + pg))
    gone = sorted(n for n in cited if not os.path.exists(os.path.join(SDSYS, "messages", n)))
    vocbad = [d + "/" + v for v, prog in VOCS.items() for d in ("newvoc", "voc_template")
              if raw.get(d + "/" + v) is None or raw[d + "/" + v].split("\n")[1:3] != ["CA", prog]]
    ck("J12", "every message the four programs cite exists (%d), and each verb's VOC record in newvoc and voc_template is CA of its program" % len(cited), cited and not gone and not vocbad, repr((gone, vocbad)))
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
    ("the switch is another field", "J1", sub("keys", "$define ACC$JOBS         23", "$define ACC$JOBS         22")),
    ("set.jobs.access skips the administrator", "J1", sub("acc", "   if not(kernel(K$ADMINISTRATOR, -1)) then\n      stop sysmsg(2001)", "   if 0 then\n      stop sysmsg(2001)")),
    ("run.job takes any switch value", "J1", sub("run", "if upcase(trim(sw.rec<ACC$JOBS>)) = 'YES' then sw.on = @true", "sw.on = @true")),
    ("add does not ask the switch", "J2", sub("job", "   if action # 'delete' then\n      gosub switch.on", "   if action = 'none' then\n      gosub switch.on")),
    ("the definition is written before the password", "J3", sub("job", "   gosub ask.password\n   if not(pw.ok) then", "   write new.rec to jobs.f, jname on error null\n   gosub ask.password\n   if not(pw.ok) then")),
    ("a one-shot may set a job", "J3", sub("job", "if kernel(K$TTY, 0) = '' or trim(system(1026)) # '' then", "if kernel(K$TTY, 0) = '' then")),
    ("every 7 minutes is taken", "J4", sub("job", "(s2 = '5' or s2 = '10'", "(s2 = '5' or s2 = '7' or s2 = '10'")),
    ("monthly takes day 31", "J4", sub("job", "dd >= 1 and dd <= 28", "dd >= 1 and dd <= 31")),
    ("a command may hold a control character", "J5", sub("job", "if cc < 32 or cc > 126 then return", "if cc < 9 then return")),
    ("the command goes into the unit", "J5", sub("job", "svc<-1> = 'ExecStart=' : sd.bin : ' \"run.job ' : jname : '\"'", "svc<-1> = 'ExecStart=' : sd.bin : ' \"' : jcmd : '\"'")),
    ("a missed run is made up", "J6", sub("job", "tmr<-1> = 'Persistent=false'", "tmr<-1> = 'Persistent=true'")),
    ("the hand-over file is judged before it is removed", "J7", sub("job", "   ho.action = downcase(trim(ho.lines<1>))\n   if ho.action # 'add' and ho.action # 'change' then return", "   ho.action = downcase(trim(ho.lines<1>))\n   if ho.action # 'add' and ho.action # 'change' then return\n   cmd = \"rm -f '\" : ho.file : \"'\"")),
    ("run.job runs from any session", "J8", sub("run", "   if not(ok.call) then", "   if @false then")),
    ("run.job leaves its own -1 as a command's status", "J8", sub("run", "   @system.return.code = 0\n   execute jcmd", "   execute jcmd")),
    ("restore for anyone", "J9", sub("job", "if not(kernel(K$INTERNAL, -1)) then stop sysmsg(14945)", "if @false then stop sysmsg(14945)")),
    ("the page may run another command", "J10", sub("page", "allow = 'set.job'", "allow = 'set.job sh'")),
    ("the password is shown as typed", "J10", sub("page", "@vm : 'Account password' : @vm : 34 : @vm : 64 : @vm : 1", "@vm : 'Account password' : @vm : 34 : @vm : 64 : @vm : ''")),
    ("the deleter leaves the timers", "J11", sub("deleter", 'rm -f "$d"/sd-solo-job-*.timer "$d"/sd-solo-job-*.service', 'rm -f "$d"/sd-solo-job-*.service')),
    ("the deleter does not keep $jobs", "J11b", sub("deleter", "'$cred' '$jobs' accounts sd-tls", "'$cred' accounts sd-tls")),
    ("the stage does not restore", "J11b", sub("stage", "jr_out=\"$(sdi SET.JOB RESTORE 2>&1)\"", "jr_out=\"\"")),
    ("a cited message is missing", "J12", sub("job", "stop sysmsg(14945)", "stop sysmsg(14899)")),
]


def report(rows):
    bad = 0
    for i, what, ok, detail in rows:
        print("  [%s] %s %s%s" % ("PASS" if ok else "FAIL", i, what, "" if ok or not detail else "   <- " + str(detail)[:400]))
        bad += 0 if ok else 1
    return bad


def main(argv):
    raw = load()
    print("test-solojobs-units: " + ", ".join(sorted(os.path.relpath(p, ROOT) for p in FILES.values())))
    if "--selftest" in argv:
        base = checks(raw)
        if any(not ok for _, _, ok, _ in base):
            print("REFUSING - the unmutated source already fails: " + ", ".join(i for i, _, ok, _ in base if not ok))
            return 1
        missed = 0
        for name, tag, f in MUTANTS:
            m = f(raw)
            if m is None:
                print("  [MISSED] %s: the mutation changed nothing" % name)
                missed += 1
                continue
            failed = [i for i, _, ok, _ in checks(m) if not ok]
            if tag in failed:
                print("  [pass] %s: caught by %s" % (name, tag))
            else:
                print("  [MISSED] %s: %s did not fail (failed: %s)" % (name, tag, failed))
                missed += 1
        print("self-test: %d mutants, %d not caught" % (len(MUTANTS), missed))
        return 1 if missed else 0
    rows = checks(raw)
    if not rows:
        print("test-solojobs-units: VOID - no check ran")
        return 2
    bad = report(rows)
    print("test-solojobs-units: %d checks, %d failed" % (len(rows), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
