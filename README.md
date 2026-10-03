# SD Core for Linux Solo

A personal, single-user edition of SD Core for Linux: the SD multivalue
database for one Linux user, installed entirely under that user's home
directory (`~/SDCoreSolo`), with no root-owned files of its own.

SD is a multivalue database in the Pr1me Information tradition, descended from
OpenQM and ScarletDME through [sdb64](https://codeberg.org/stringdatabase/sdb64).
SD Core for Linux Solo has every feature of the full SD Core for Linux except
those that exist to serve more than one person: there is one account, named
after the Linux user, and no commands to create accounts or grant access to
them. It is the Linux counterpart of
[SD Core Solo for Windows](https://github.com/dmontaine/SDCore4WindowsSolo).

**Version LS1.1-3, not yet released.** It started on 29 September 2026 as a copy
of SD Core for Linux L1.1-1. The one-account model, the passwords and ADMIN, the
API login, the systemd user service, ssh into `sd`, the installer, the in-place
upgrade (`bash installsdsolo.sh --upgrade`), the managed-mode server controls
(global catalogue, denied commands) and the account password chosen at first
login are built and have been run on one machine. LS1.1-2 added, for a managed
installation, the API request that lets the server install its own ssh key
(request 49) and first-use pinning of the server's TLS certificate by the client
library; both are described in [docs/SOLO_API.md](docs/SOLO_API.md). LS1.1-3 gives Solo its
own ssh listener on port 4251 (your Linux account name and password, or a key if you add one; run by you with no root, nothing changed in the
machine's own sshd, so Solo and the multi-user SD Core can both be reached by ssh). The documentation is in the
separate repository
[SDCore4LinuxSoloDocs](https://github.com/dmontaine/SDCore4LinuxSoloDocs);
[docs/SOLO_API.md](docs/SOLO_API.md) describes the API. **What has not been run,
and is the owner's to run** (`sudo` paths, `loginctl enable-linger`, the firewall
rule for an open ssh or API port, an install from the published branch) is listed in the
documentation's page 19 and in `PROJECT_STATUS.md`.

SD Core is English only: it has no support for other languages or locales.

## Installing

Run as your own user - never as root. The script asks for `sudo` only to install
the build packages, to open a firewall port you asked for and to enable linger.

```sh
bash installsdsolo.sh          # asks its questions; --help lists the options
```

It downloads the source (the `main` branch of this repository) into a temporary
directory under your home, builds it there, installs into `~/SDCoreSolo`, sets your
passwords, starts SD as your own systemd service and deletes the download. The
script can be carried on a USB stick; it needs the network for the packages and the
download. `bash ~/SDCoreSolo/tools/deletesdsolo.sh` removes it again, keeping your
data if you ask.

**Requirements:** a 64-bit Linux with a systemd user manager and one of the
Debian/Ubuntu, Fedora, openSUSE or Arch families (RHEL and its clones are not supported); a user who can use `sudo`.
It cannot be installed on a computer that has the multi-user SD Core for Linux.

## What it is for

- **Standalone** — a local, single-user database, used much as you would use
  SQLite.
- **Managed client** — a local store in a distributed setup, where a master
  SD Core server holds the central data and manages its clients. A global
  password, set by the installer, lets the master server reach the client.

## Source

This repository contains no binaries; everything is built from source.

## Related repositories

- [SDCore4Linux](https://github.com/dmontaine/SDCore4Linux) — the multi-user
  SD Core for Linux this edition is derived from.
- [SDCore4WindowsSolo](https://github.com/dmontaine/SDCore4WindowsSolo) — the
  Windows edition of Solo, whose features this one follows.

## Licence

Most of SD is licensed under the GPL v3.0; the install and delete scripts are
licensed under the Blue Oak Model License 1.0.0. The header of each source file
says which applies; see `sdb_ai/LICENSE`.
