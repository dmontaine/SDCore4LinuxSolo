# SD Core for Linux Solo — the API, as built

How a client reaches a Solo computer, what runs on it, and what each step is
checked by. It is the Linux counterpart of the Windows Solo design note, written
**after** the build: everything here was measured on a staged tree by
`gplbld/verify-solo-service.sh` (14 legs) unless a line says otherwise.

The client libraries are unchanged from the multiuser product's: **the wire
protocol is too.** A network login is SCRAM-SHA-256 inside TLS 1.3, requests 47
and 48, and nothing else. Request 24 (cleartext) is refused, and request 25
(`SDConnectLocal`) is refused with message 11021.

## What runs

| | |
|---|---|
| The daemon | `sd-solo.service`, a systemd **user** unit: `sd -start`. It owns the shared-memory segment. Runs as the user, never as root |
| The listener | `sd-solo-api.socket`, only with `--api local\|open`. `Accept=true`, so systemd accepts each connection and starts one `sd-solo-api@.service` per connection |
| One connection | `sd -n -q`, with the accepted socket as its standard input. `-n` is a network session, `-q` no banner. It runs as the user |
| The TLS relay | `sd_tls_relay_start()` (`gplsrc/sd_tlssrv.c`) forks; the relay does the handshake and copies bytes, `sd` gets one end of a socketpair and a 32-byte channel binding. The relay's "drop from root to nobody" is skipped: **Solo is never root, so the relay runs as the user** — but it is confined (LSOLO 18): before it reads one byte from the network it sets `no_new_privs` and installs a seccomp whitelist (`confine()`), so it cannot open a file, make a socket or run a program, and any such call kills it with SIGSYS. `sd` and the session are not filtered. Checked by `gplbld/test-tls-relay.py` (group H: the filter is on, three forbidden calls kill, an allowed one does not) and `verify-solo-service.sh` S6g (a live relay is confined, the session is not). Whitelist for x86_64 and aarch64; any other architecture runs unconfined and logs a warning. The aarch64 list is unbuilt and untested |
| The identity | `~/SDCoreSolo/sd-tls/api.pem` (private key and self-signed certificate), made on the first connection. The directory must be 0700 and the file 0600 and owned by the user, or the relay refuses to start |
| Pinning (LSOLO 19) | The client library (`sd_tls_client_pin()`, called by `SDConnect` after the handshake and before any login byte) records the SHA-256 of the server's whole certificate for `host:port` the first time it connects, in `$SD_KNOWN_SERVERS` or `~/.sdcore/known_servers` (0600, one `host:port <64 hex>` line per server, host in lower case). A later connection that presents another certificate is refused with a message that names both fingerprints and the line to remove; a store that cannot be used refuses too. **Trust on first use:** a man in the middle present at the very first connection is pinned instead of the server, as with ssh's `known_hosts`. A reinstalled server has a new certificate and needs its line removed. Checked by `gplbld/test-tls-relay.py` group P (10 checks) and `gplbld/verify-solo-pin.sh` (5 legs: the pin equals the SHA-256 openssl computes, a replaced identity is refused with no login started, removing the line re-pins) |

`local` binds `127.0.0.1`, `open` binds `0.0.0.0`; the port is **4249 and cannot be
changed** (owner, 2 Oct 2026: no adjustable ports). 4243 is OpenQM's and ScarletDME's,
4245 upstream SD's and 4247 the full SD Core products', so a Solo, a full product and
those databases can all run on one computer. **Changing the address is
`tools/solo-service.sh install` again**, which stops the old listener first
(verified: open → off → local). A client that named 4243 must name 4249.

## The login

1. **TLS 1.3** handshake (measured: `openssl s_client` reports TLSv1.3,
   `TLS_AES_256_GCM_SHA384`). Anything older is refused.
2. **Request 47**: the client sends `n,,n=<user>,r=<nonce>`. The server reads the
   account's own credential and, on a managed computer, `$global`, and answers with
   the salt and iteration count. **The two records share one salt** (`!CRED_SET`
   takes the account's salt for `$global`), so the server can send one challenge that
   either password answers. Measured: with two different salts the master could
   never log in.
3. **Request 48**: the client proof. The server checks it against the account
   record first and `$global` second.
   - account proof → `via=account`, an ordinary session;
   - global proof (managed only) → the administrator flag **and** `K$GLOBAL.SESSION`
     are set (`USR_GLOBAL`), audited `API LOGIN user=sduser via=global`;
   - neither → `API REFUSED user=… reason=wrong password`.
4. The server's signature is sent back and the client verifies it (`VERIFIED`).

**Who may log in:** the user name is always `sduser`. `vb.account` lets the session
enter only its own account — asking for SDSYS, or any other name, gives *User not
allowed in requested account*, the same words as for an account that does not
exist. **The administrator password is not an API login** (leg S6d). **Until a
control-file install's first console login, only `$global` verifies** — the
account record does not exist; that path has been read in the source and not
exercised (GettingStarted 19).

## Request 49: the managed server's ssh key (LS1.1-2)

In managed mode the server logs in as `sduser` with the global password, over the API
and over ssh, and knows only the client's address. ssh needs a real Linux user, so after
a global login the server installs its public key through request 49 and learns the
user name from the reply. Windows Solo answers the same request in the same words.

- **Who may send it:** only a session signed in with the global password
  (`K$GLOBAL.SESSION`). An account-password session, or ADMIN, gets message 11041,
  "Only the SD Core server may manage ssh keys". It is not admitted before login, and on a
  standalone computer no session can be a global one.
- **The request:** a verb, then a field mark and an argument. `ADD` and a one-line public
  key; `REMOVE` and a `SHA256:...` fingerprint; `LIST` alone.
- **The reply:** `ADD` gives five fields: the Linux user, the host name, the key's
  `SHA256:` fingerprint, `ADDED` or `PRESENT`, and the fingerprint of sshd's ed25519 host
  key (empty if unreadable). `REMOVE` gives `REMOVED` or `ABSENT`, then how many Solo
  lines are left. `LIST` gives one fingerprint per field.
- **The refusals,** message 11042, "The ssh key request was refused: %1", with the reason
  "the key or fingerprint is not valid", "four Solo ssh keys are already installed",
  "unknown request, use ADD, REMOVE or LIST" or "the request could not be carried out".
- **What it writes:** one line in the user's `~/.ssh/authorized_keys`,
  `command="<tree>/bin/sd",restrict,pty <key>`, so the key starts `sd` and nothing else:
  no shell, no forwarding. At most four such lines; the user's own keys are never listed,
  counted or touched. The key reaches `tools/solo-ssh.sh api-add|api-remove|api-list` in a
  file, never on a command line, and the script's answer comes back in another file.
- **Audit:** every verb writes `API SSHKEY <verb> ... peer=<address>` with the key's
  fingerprint and never its text.
- **Test hook:** `SDSOLO_AUTHORIZED_KEYS` names another file for the script to edit; the
  witness uses it so the real `~/.ssh` is not touched. The script says so in its output.

## Pinning the server's certificate (LS1.1-2)

Covered in the table of "What runs" above: the client library records each server's
certificate on first use and refuses a changed one before any login byte is sent.

## What is checked, and by which leg

| leg | proves |
|---|---|
| S6 | the socket listens on the chosen address and answers TLS 1.3 |
| S6a | the account password logs in, the server signature verifies, WHO says `sduser` |
| S6b | a wrong password, `sdsys` and `$admin` are each refused and never `VERIFIED` |
| S6c | `sduser` can enter no other account — not SDSYS, not one that does not exist |
| S6d | the administrator password is not an API login |
| S6e | managed: the global password carries ADMIN, the account password does not (needs a managed tree) |
| S6f | `SDConnectLocal` returns at once with the refusal text (it used to hang) |
| S7 | `sd-tls` is 0700 and `api.pem` 0600 |
| S7b | re-running install changes the listener |

Request 49 and the pin have their own witnesses (not part of `verify-solo-service.sh`):

| script | legs | proves |
|---|---|---|
| `gplbld/verify-solo-sshkey.sh HOME ACCOUNT_PW GLOBAL_PW` | 11 | LIST, ADD with its five fields, ADD twice, the cap of four, REMOVE then ABSENT, the account-password control refused 11041 with the file unchanged, bad arguments, shell syntax not run, the installed key reaches `sd` over a private sshd with the global password, the audit trail |
| `gplbld/verify-solo-ssh-global.sh HOME ACCOUNT_PW GLOBAL_PW` | 5 | over ssh the global password is a global session and the account password is not; the forced key has no shell |
| `gplbld/verify-solo-pin.sh HOME ACCOUNT_PW` | 5 | the pin equals the SHA-256 `openssl` computes; a replaced `api.pem` is refused with no login started; removing the line re-pins; an unusable store refuses |
| `gplbld/test-tls-relay.py`, group P | 10 | the pin store rules without a server (52 checks in all) |

`verify-solo-sshkey.sh` and `verify-solo-pin.sh` install the user's systemd units under
the same names as a real install, so they refuse while `sd-solo.service` is installed.

`gplbld/scram-probe.py` is the client the legs use: it speaks the whole exchange
over TLS. `gplbld/test-tls-relay.py` and `test-scram-vectors.py` are the free
checks of the relay and the SCRAM arithmetic.

## What is not established

- **Containment** of an API session to the account's files (the multiuser
  product's `OPEN` refusal, status 3035) has not been tested on Solo.
- **The relay's filter** has been run only on x86_64, with OpenSSL 4.0.1. A different
  OpenSSL or libc that needs another system call would kill the relay, and the API
  connection would drop; `journalctl -t sd` would show nothing, because the kill is
  instant. If that happens, run `gplbld/test-tls-relay.py` on that machine.
- **The address of a refused login is not in the audit trail**, only in the
  journal (`journalctl -t sd_Log`: *API connection over TCP from …*).
- Not run: an API session from another computer, `open` behind a real firewall.
