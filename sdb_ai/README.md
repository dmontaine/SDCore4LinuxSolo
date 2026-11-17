# SD Core Solo for Linux — source tree

The source of SD Core Solo for Linux, the single-user edition of SD Core for
Linux, the multivalue String Database. SD Core for Linux is the version the
other SD Core versions follow; this edition has its features except those that
exist to serve more than one person. The repository's top-level `README.md`
describes the product and how to install it.

SD is a multivalue database in the Pr1me Information tradition. It contains open
source code from OpenQM and ScarletDME, code written by the SD developers after
their fork from ScarletDME ([sdb64](https://codeberg.org/stringdatabase/sdb64)),
and the changes made in SD Core for Linux and in this edition.

The tree contains no binaries. `installsdsolo.sh` clones it and builds everything
from source during the install.

| | |
|---|---|
| `sd64/gplsrc/` | the C source of the server and the client library |
| `sd64/sdsys/` | the SDSYS system account as shipped: `gpl.bp` (the SD BASIC system programs), `messages`, `newvoc`, `voc_template`, and the `changelog` |
| `sd64/gplbld/` | the build: the Python tooling that compiles the SD BASIC system programs, `solo-stage.sh`, which stages the built tree, and the helpers the installer copies into the installation's `tools` folder (`solo-service.sh`, which writes the systemd user units, `solo-ssh.sh`, `solo-sshguard.py`, `solo-mcp.py`, `sd-ai`, `sd-ai-ctl`, `ai-context`); there is no root helper |
| `sd64/Makefile` | builds the C half |
| `sd64/agent-pack/` | the SD BASIC guide and knowledge pack for an AI agent; the installer copies `guide/` and `pack/` into the installation |
| `sd64/examples/` | example programs, including embedded Python |
| `sd64/terminfo.src/` | terminal definitions |

See `sd64/sdsys/changelog` for the changes in each version.
