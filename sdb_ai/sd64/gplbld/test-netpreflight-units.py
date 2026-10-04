#!/usr/bin/env python3
"""test-netpreflight-units.py - installsdsolo.sh's net_preflight, run and ordered.

  python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-netpreflight-units.py
  python3 .../test-netpreflight-units.py --selftest

No sudo, no install, no sd, no internet.  Exit 0 all checks passed, 1 a check
failed, 2 it could not run.  Written 4 Oct 26 for LSOLO 35 (the multi-user
installer's twin is S.57; this file is its Solo copy and differs in the cut
(marker lines), the refusal (refuse(): "REFUSED: ...", exit 2) and the anchors).

WHAT IT CHECKS.  net_preflight is cut out of the installer between its
BEGIN/END markers and RUN, under the installer's own `set` line (the S.48
lesson: a block tested without the installer's options passed while real
installs stopped), against a listener this test opens on 127.0.0.1, a port it
opened and closed, and a name that cannot resolve.  Then the CALL is checked
by position: after the "systemctl" checks, before the password rule, before
the first question and the first sudo; and that it tests only an https source,
the host it clones from.

WHAT IT DOES NOT CHECK.  Whether github.com is reachable from here (it never
asks), and the whole installer on an offline computer: that is a run in a
network namespace (unshare -Un --map-user=UID) or on a machine with no
network, and is in PROJECT_STATUS LSOLO 35.

--selftest mutates the installer in the ways the check could plausibly be
broken and requires each mutant to be CAUGHT.
"""

import os
import re
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir, "installsdsolo.sh"))
PROXY_VARS = ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY", "SD_SKIP_NET_CHECK")


def cut_function(src):
    """The text between '# BEGIN net_preflight' and '# END net_preflight', start line."""
    lines = src.splitlines()
    try:
        a = lines.index("# BEGIN net_preflight")
        b = lines.index("# END net_preflight")
    except ValueError:
        return None, 0
    return "\n".join(lines[a + 1:b]), a + 2


def option_lines(src):
    return "\n".join(l for l in src.splitlines() if re.match(r"^(set -|IFS=)", l))


def run_fn(src, host, port, env_extra=None):
    """Run net_preflight HOST PORT under the installer's options.  (rc, output)."""
    fn, _ = cut_function(src)
    script = ("%s\nRED=; NC=\nrefuse() { printf 'REFUSED: %%s\\n' \"$*\" >&2; exit 2; }\n"
              "%s\nnet_preflight %s %s\necho REACHED-END\n") % (option_lines(src), fn, host, port)
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS}
    env.update(env_extra or {})
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        p = subprocess.run(["bash", path], env=env, capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    return p.returncode, p.stdout + p.stderr


def code_line(src, pattern):
    for n, line in enumerate(src.splitlines(), 1):
        if not line.lstrip().startswith("#") and re.search(pattern, line):
            return n
    return None


def checks(src):
    out = []

    def ck(name, ok, detail=""):
        out.append((name, bool(ok), detail))

    fn, fline = cut_function(src)
    ck("net_preflight is defined between its markers", fn is not None and "net_preflight()" in fn, "line %s" % fline)
    if fn is None:
        return out

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    open_port = listener.getsockname()[1]
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()

    rc, o = run_fn(src, "127.0.0.1", open_port)
    ck("reachable host and port: goes on quietly",
       rc == 0 and o.strip() == "REACHED-END", "rc=%s out=%r" % (rc, o))

    rc, o = run_fn(src, "127.0.0.1", closed_port)
    ck("closed port: refuses with exit 2, before going on", rc == 2 and "REACHED-END" not in o, "rc=%s" % rc)
    ck("closed port: says it cannot connect, and that nothing has been changed",
       ("cannot connect to 127.0.0.1 port %d" % closed_port) in o and "Nothing has been changed" in o,
       o.strip().splitlines()[0] if o.strip() else "no output")
    ck("closed port: names the override for a proxy it cannot see", "SD_SKIP_NET_CHECK=1" in o)
    ck("closed port: says the stick carries the installer and documentation, not SD",
       "USB stick carries this installer" in o and "not SD" in o)

    rc, o = run_fn(src, "sd-no-such-host.invalid", 443)
    ck("name that does not resolve: refuses with 'cannot look up'",
       rc == 2 and "cannot look up sd-no-such-host.invalid" in o and "REACHED-END" not in o, "rc=%s" % rc)

    for v in ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        rc, o = run_fn(src, "127.0.0.1", closed_port, {v: "http://proxy.invalid:3128"})
        ck("%s set: does not test, goes on" % v, rc == 0 and "REACHED-END" in o, "rc=%s" % rc)
    rc, o = run_fn(src, "127.0.0.1", closed_port, {"https_proxy": ""})
    ck("https_proxy set but EMPTY: still tests, refuses", rc == 2 and "REACHED-END" not in o, "rc=%s" % rc)

    rc, o = run_fn(src, "127.0.0.1", closed_port, {"SD_SKIP_NET_CHECK": "1"})
    ck("SD_SKIP_NET_CHECK=1: goes on", rc == 0 and "REACHED-END" in o, "rc=%s" % rc)
    rc, o = run_fn(src, "127.0.0.1", closed_port, {"SD_SKIP_NET_CHECK": "0"})
    ck("SD_SKIP_NET_CHECK=0: does not skip", rc == 2 and "REACHED-END" not in o, "rc=%s" % rc)
    listener.close()

    # The call: position and arguments.
    call = code_line(src, r'^if \[\[ "\$REPO_URL" =~ .*net_preflight\b')
    ck("the installer calls net_preflight", call is not None, "line %s" % call)
    ck("the call tests port 443 of the host in an https REPO_URL only",
       call is not None and 'net_preflight "${BASH_REMATCH[1]}" 443' in src.splitlines()[call - 1]
       and "^https://" in src.splitlines()[call - 1])
    sysd = code_line(src, r'^command -v systemctl')
    pwrule = code_line(src, r'^pw_ok\(\)')
    first_ask = code_line(src, r'(^|[^#_a-z])read_password\s+"|read -r -p|\bread -r\b')
    first_sudo = code_line(src, r'(^|[ (;])sudo\s')
    ck("after the systemctl checks", call and sysd and sysd < call, "systemctl %s call %s" % (sysd, call))
    ck("before the password rule", call and pwrule and call < pwrule, "call %s pw %s" % (call, pwrule))
    ck("before the first question", call and first_ask and call < first_ask, "call %s ask %s" % (call, first_ask))
    ck("before the first sudo", call and first_sudo and call < first_sudo, "call %s sudo %s" % (call, first_sudo))
    host = re.search(r'^REPO_URL="https://([^/"]+)', src, re.M)
    ck("the source it would test is github.com", bool(host) and host.group(1) == "github.com",
       str(host and host.group(1)))

    # The condition line, evaluated: an https URL calls it with the host; a path does not.
    if call is not None:
        cond = src.splitlines()[call - 1]
        for url, want in (("https://github.com/a/b", "github.com"), ("/home/x/clone", ""),
                          ("file:///x/y", ""), ("https://other.example/x", "other.example")):
            script = 'net_preflight() { echo "CALLED:$1:$2"; }\nREPO_URL=%s\n%s\n' % (url, cond)
            p = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=20)
            got = p.stdout.strip()
            expect = ("CALLED:%s:443" % want) if want else ""
            ck("REPO_URL %s -> %s" % (url, expect or "no check"), got == expect, "got %r" % got)
    return out


def mutants(src):
    fn, _ = cut_function(src)
    res = []
    if fn is None:
        return res
    loop = re.search(r"  for v in https_proxy.*?\n  done\n", src, re.S)
    if loop:
        res.append(("proxy variables no longer skip the test", src.replace(loop.group(0), "")))
    res.append(("the override no longer skips", src.replace('[ "${SD_SKIP_NET_CHECK:-}" = "1" ] && return 0', ":")))
    res.append(("a closed port is no longer a refusal", src.replace('elif ! timeout 8 bash -c', 'elif false && ! timeout 8 bash -c')))
    res.append(("a name that does not resolve is no longer a refusal", src.replace('if ! getent hosts "$host"', 'if false && ! getent hosts "$host"')))
    res.append(("it refuses everything", src.replace("  else\n    return 0\n  fi\n  refuse", "  fi\n  refuse")))
    callline = [l for l in src.splitlines() if l.startswith('if [[ "$REPO_URL" =~') and "net_preflight" in l]
    if callline:
        c = callline[0]
        res.append(("the call is deleted", src.replace(c + "\n", "", 1)))
        res.append(("the call moves after the password rule",
                    src.replace(c + "\n", "", 1).replace("read_password() {", c + "\nread_password() {", 1)))
        res.append(("the call tests the wrong port", src.replace(c, c.replace("443", "80"), 1)))
        res.append(("the call also fires for a local path", src.replace(c, 'net_preflight "${REPO_URL:-x}" 443', 1)))
    return res


def main():
    if not os.path.isfile(INSTALLER):
        print("test-netpreflight-units: CANNOT RUN - no installer at %s" % INSTALLER)
        return 2
    src = open(INSTALLER).read()
    if "--selftest" in sys.argv:
        base = checks(src)
        if not all(ok for _, ok, _ in base):
            print("selftest: CANNOT RUN - the unmutated installer already fails:")
            for n, ok, d in base:
                if not ok:
                    print("  FAIL %s (%s)" % (n, d))
            return 2
        bad = 0
        ms = mutants(src)
        for name, msrc in ms:
            if msrc == src:
                print("  [NOT APPLIED] %s - the mutation did not change the source" % name)
                bad += 1
                continue
            caught = [n for n, ok, _ in checks(msrc) if not ok]
            if caught:
                print("  [caught] %s  (%d check(s) failed)" % (name, len(caught)))
            else:
                print("  [MISSED] %s" % name)
                bad += 1
        print("test-netpreflight-units --selftest: %d mutant(s), %d not caught" % (len(ms), bad))
        return 1 if bad else 0

    print("installer : %s" % INSTALLER)
    res = checks(src)
    fails = 0
    for name, ok, detail in res:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name, "" if ok or not detail else "  (" + str(detail) + ")"))
        fails += 0 if ok else 1
    print("test-netpreflight-units: %d checks, %d failed" % (len(res), fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
