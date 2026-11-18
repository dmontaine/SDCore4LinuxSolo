# SD Core Solo for Linux

A personal, single-user edition of SD Core for Linux: the SD multivalue
database for one Linux user, installed entirely under that user's home
directory (`~/SDCoreSolo`), with no root-owned files of its own.

SD is a multivalue database in the Pr1me Information tradition, descended from
OpenQM and ScarletDME through [sdb64](https://codeberg.org/stringdatabase/sdb64).
SD Core Solo for Linux has every feature of the full SD Core for Linux except
those that exist to serve more than one person: there is one account, `sduser`,
and no commands to create accounts or grant access to them. SD Core for Linux is the version the other SD Core versions follow; this
edition follows its features and differs only where a single user's install
requires it. [SD Core Solo for Windows](https://github.com/dmontaine/SDCore4WindowsSolo)
is the Windows counterpart of this edition.

**Version LS1.1-3, released 9 October 2026.** SD Core Solo for Linux started on
29 September 2026 as a copy of SD Core for Linux L1.1-1.
See `sdb_ai/sd64/sdsys/changelog` for what each release contains.

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
script can be carried on a USB stick (a release zip unzipped there) and run from it
with `bash /media/<you>/<stick>/installsdsolo.sh` - use `bash`, because a stick
formatted FAT, exFAT or NTFS has no execute permission. The stick carries only the
installer and the documentation: the computer must be online for the packages and
the download, and the installer says so, before it asks anything or changes
anything, if it is not. `bash ~/SDCoreSolo/tools/deletesdsolo.sh` removes it again,
leaving your data and `sd.conf` where they are if you ask; a new install into that
directory then offers to reload them (it asks for new passwords).

## Requirements

- A 64-bit Linux with a systemd user manager: Debian or Ubuntu (and their
  derivatives). The installer refuses any other, including Fedora, RHEL and
  RHEL's clones, Arch and openSUSE, before it changes anything.
- A user who can use `sudo`.
- An internet connection: the installer installs the build packages, downloads
  this repository and compiles SD. It checks first and stops, changing nothing,
  if the computer is offline.

It can be installed beside the multi-user SD Core for Linux (`sd-solo` and `sd` are separate commands).

## What it is for

- **On its own** — a local, single-user database, used much as you would use
  SQLite.
- **As a client of an SD Core server** — a local store in a distributed setup,
  where a master SD Core server holds the central data and manages its clients.
  A global password lets the master server reach the client.

There is one install for both. The installer asks for a global password last and
you can leave it blank if no SD Core server manages this computer; a computer is
managed if, and only if, it has a global password. The API and ssh are always your
choice (off, this computer only, or reachable from the network), with or without a
global password; a computer that a server manages needs both open to the network.
An install file (`sd-solo-setup.conf.sample`) can answer these questions for an
install nobody sits at.

## Documentation

The installation guide and the SD BASIC and TCL references are in the separate
[SDCore4LinuxSoloDocs](https://github.com/dmontaine/SDCore4LinuxSoloDocs)
repository; [docs/SOLO_API.md](docs/SOLO_API.md) describes the API.

## Source

This repository contains no binaries; everything is built from source during the install.

## Related repositories

- [SDCore4Linux](https://github.com/dmontaine/SDCore4Linux) — the multi-user
  SD Core for Linux this edition is derived from, and whose features it follows.
- [SDCore4Windows](https://github.com/dmontaine/SDCore4Windows) — SD Core for
  Windows, the multi-user Windows version.
- [SDCore4WindowsSolo](https://github.com/dmontaine/SDCore4WindowsSolo) — the
  Windows edition of Solo.

## Licence

Most of SD is licensed under the GPL v3.0; the install and delete scripts are
licensed under the Blue Oak Model License 1.0.0. The header of each source file
says which applies; see `sdb_ai/LICENSE`.
