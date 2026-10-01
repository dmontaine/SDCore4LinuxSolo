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

`local` binds `127.0.0.1`, `open` binds `0.0.0.0`; the port is 4243 unless
`--api-port`. **Changing any of it is `tools/solo-service.sh install` again**, which
stops the old listener first (verified: open → off → local).

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
