# agent-pack: what an AI agent needs to work in SD Core for Linux Solo

S.69 rows 1 and 1b of the AI plan, carried to Solo (LSOLO 55, 20 Oct 2026). Documents, a generator and free and sandbox checks. **Nothing here is installed, compiled into SD or shipped by the installer** (it reads `sdsys`, `bin`, `gplsrc`, `gplobj`, `terminfo` and a few `gplbld` files; this directory is none of those), and nothing here calls a model, holds a key, opens a wall or changes ssh.

| path | what | made by |
|---|---|---|
| `guide/sd-basic-guide.md` | the SD BASIC dialect guide: language, system, walls, 20+ worked programs | by hand; every block compiled and run by `gplbld/sandbox-guide.py` |
| `pack/` | the generated knowledge pack: one chunk per TCL verb, query keyword, VOC type, dictionary type and conversion, BASIC statement, function, `$mode`, option, message, setting and key group, with the source and line of each | `mkpack.py`; guarded by `gplbld/test-pack-units.py` |
| `core-start.md` | the "start here" text embedded in the pack's core | by hand |
| `skill/sd-core-solo/` | a Claude Code skill: `SKILL.md` by hand, `references/` (the guide and the pack) generated | `mkpack.py --write` |
| `templates/` | a CLAUDE.md template for a project that lives in the SD account; an `.mcp.json` shape that does NOT work yet | by hand |
| `recipe/agent-account.md` | the zero-code recipe: give the agent a computer of its own, so that the operating system is the wall | by hand |
| `PACKAGING.md` | the packaging facts verified from the official pages (Core's, unchanged) | by hand |

Regenerate after a change to a verb, a message, a bcomp table, a docs section the pack quotes, the shipped dictionaries, the guide or the stamp:

```
python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/agent-pack/mkpack.py --write
python3 /home/don/Projects/SDCore4LinuxSolo/sdb_ai/sd64/gplbld/test-pack-units.py
```

The generator takes the tree and the docs checkout as arguments (`--tree DIR --docs DIR --out DIR --skill DIR --product NAME`). It reads Solo's docs repository by absolute path (`/home/don/Projects/SDCore4LinuxSoloDocs`) and exits 2, saying so, when the checkout is missing. Line numbers in `src=path:line#hash` are locators that may lag after an edit elsewhere in the same file; the hash of the cited line is the identity and is what the check holds.

## Where this differs from SD Core's agent pack, and why

Solo is the single-user product; SD Core's pack was written for the full product and is the template. Every difference below is a fact about this product, not a choice of wording. The generator is Core's `mkpack.py` with five names and four branches, each marked `SOLO:` in the file.

| | SD Core's pack | Solo's pack | why |
|---|---|---|---|
| accounts | many; `create.account`, `modify.account`, group accounts, `sys:word:<word>` chunks for every account word | one account, `sduser`; **no account-word chunks** (`HAS_ACCOUNT_WORDS = False`); `create.account` and `logto` are "not in your VOC" | Solo has no `createa` and no `modifya` |
| walls | per-account gates, off by default, switched on by SDSYS (chunk `core:gates`) | `admin`, the VOC, the global catalogue and the compiler's restricted names (chunk `core:walls`, quoted from Solo's `12-security` and `06b-operating-system-access` pages) | Solo has no per-account gates |
| the shell and the operating system | `sh`, `!`, `os.execute` and a path outside the account are each gated and refused as delivered | **not gated in this release**; they run with the Linux user's rights; `sh` and `!` filter shell metacharacters, `os.execute` does not. The guide says this in so many words, as a fact and not a permission | Solo's `06b-operating-system-access` page; the Solo OS switch is not built |
| the administrator | SDSYS, entered as the `sdsys` Linux user on a local session | `admin` and the administrator password, typed by the user in the session; the guide never has an agent type or look for it | Solo has no `sdsys` user |
| writing the VOC | `voc-on` gate, status 3035 | `admin`, status 3035, and the run-time text says "(Possible full disk?)", which the guide warns is the wall and not a disk | the same kernel test, a different key |
| compiling and cataloguing | `bp-on` gate; an account without it cannot compile | always allowed; `catalog ... global` is refused | no per-account gates; the global catalogue is the SD Core server's |
| the way in | `sd -a<account>` on a pipe, or ssh to port 22 forced into `sd`, or the API on 4247 | `sd-solo` on a pipe whose first line is the account password, or ssh to Solo's own port 4251, or the API on 4249 | Solo's own ports and sign-on |
| the recipe | an account of its own on the same computer | **a computer, virtual machine or container of its own**: one SD runs on a computer, and one account holds everything | Solo's `03-running-sd` page: "Only one SD can run on a computer" |
| the guide's two lanes | an administrator lane and ordinary accounts `gdoff` and `gdbp` (`as=` on a block) | one lane, a plain session of `sduser` that has not typed `admin`; a block that names `as=` is refused | there is one account and no gates |
| the guide's selftest | `--mutant open-gates` (every gate on) | `--mutant admin` (the blocks run after `admin`): the four rows that show a refusal go red | the wall Solo has to break |
| the skill | `sd-core` | `sd-core-solo` | two skills may be installed side by side |
| the VOC layers in the pack | `newvoc` for every account, `voc_template` for SDSYS, `newvoc.mods` on top | the one account's VOC is `newvoc` whole | Solo has no `newvoc.mods` |
| the docs the generator reads | `SDCore4LinuxDocs` (`User`, `Administrator`) | `SDCore4LinuxSoloDocs` (`User`, `GettingStarted`) | Solo's docs are a separate repository |

Not different: the dialect itself. The guide's Part A, its worked examples (Part C), the table of what SD lacks (B6) and the rosters hold for Solo as they stand: Core's guide was run on Solo with its `as=` lanes taken off, and the only rows that failed, 9 of 201, were the ones about gates, the VOC and one message number (10161, a Core message); those blocks were rewritten and every row of the Solo guide now holds.
