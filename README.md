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

**Version LS1.1-1. This repository is a work in progress: nothing has been
built or released yet.** It started on 29 September 2026 as a copy of
SD Core for Linux L1.1-1, and the Solo changes are being made to it in the
order listed in the project's task table. Until they are done, the code here
still installs and behaves as the multi-user SD Core for Linux.

SD Core is English only: it has no support for other languages or locales.

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
