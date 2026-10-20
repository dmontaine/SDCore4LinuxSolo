# The agent's own installation: a real wall for an AI agent, with no code

**Words used:** none (this product has no account words)

**Scripts used:** `installsdsolo.sh`, `solo-ssh.sh`

An agent that works on an SD project needs a place to work and a limit on what it can reach. Prompts, tool scopes and promises inside the agent's own software protect against mistakes and against instructions injected into data it reads. They do not stop an agent that can run as the Linux user who owns the installation: it can read the kept copy of the account password, open an interactive `sd-solo` as the owner and do anything the owner can. **The wall is the operating system, and in this product it can only be a computer.** SD Core for Linux Solo has **one account**, so there is no account to make for the agent and no switch that scopes it inside; and **only one SD can run on a computer** (the shared-memory name and the API and ssh ports, 4249 and 4251, are machine-wide, so a second Solo for another Linux user would attach to the first one's), so the agent cannot have an installation of its own beside the owner's. This recipe gives the agent a computer of its own and nothing else.

It needs no code from this project and no change to an installed system. Everything marked [unverified] below was read from the documentation and the source and was not run end to end for this recipe; the refusals in step 5 were run (they are the probes of `guide/sd-basic-guide.md`, part B2, run by `gplbld/sandbox-guide.py` in a sandbox, in a plain session of `sduser`).

## Before you start

- The agent is **never you**. Do not give it your passwords, your ssh key or a terminal that is already signed in, and do not point it at your own installation.
- Decide what the agent is for (one project, one set of programs) and which files it needs. Everything else stays on your own computer.
- Decide how it reaches the machine. The way in is **a session of the one account**, so whoever has the account password has the whole account: on the agent's computer that is the agent's installation and it is disposable, which is the point.
- What the agent's installation can reach is what its Linux user can reach, because `sh`, `os.execute` and `openseq` of any path are not gated in this product (guide, B2). Keep nothing on that computer that you do not want the agent to be able to read.

## Steps

1. **Get the computer.** A separate machine, a virtual machine, or a container with its own IPC namespace and its own network address. [unverified] Not a second Linux user on your own computer.

2. **Install the product there as an ordinary Linux user of its own**, with `installsdsolo.sh` (it refuses to run as root and installs into that user's home). Choose **new passwords** for the account and for the administrator on this installation; they are not your passwords and they are not given to the agent beyond what it needs: the agent is given the **account password**, never the administrator password. [unverified: the installer's prompts are documented in the Solo Getting Started pages, not run here]

3. **Give it a workspace.** Copy in what it needs to read. Do not mount your real data. Its account directory is `user_accounts/sduser` under the installation, with a `bp` file for source and whatever test files it creates.

4. **Give it a way in.** Either the agent runs as the installation's Linux user on that computer and pipes commands to `sd-solo` (the first line is the account password, the second `TERM 200,9999`, the last `OFF`), or it comes in over ssh to port 4251 with a key you added with `solo-ssh.sh key-add` and then types the account password at the SD prompt. [unverified: read from the Solo ssh page and `gplbld/solo-ssh.sh`, not run here] The API on port 4249 is a third way and needs the password too.

5. **Prove the walls before you trust them.** As the agent, run the probes of `guide/sd-basic-guide.md` part B2: `config`, a `copy` into the VOC, `catalog ... global`, a program's write to the VOC, a restricted statement and `$internal` must each be refused with the wording the guide quotes. And read, in the same part, what is **not** refused (`sh`, `os.execute`, a path outside the account): if you did not want that, the computer was the wrong place for the agent.

6. **Install the knowledge.** The skill (`agent-pack/skill/sd-core-solo/` into the project's `.claude/skills/sd-core-solo/`) and `agent-pack/templates/CLAUDE.md` in the project root, filled in. They carry the rules; they are not the wall.

7. **Keep the hand-over human.** The agent proposes; a person reads `bp/NAME` on the agent's computer and copies it to yours. The agent has no route to your computer, so it cannot promote its own work.

8. **Watch it.** Its sessions and its refusals are in the installation's audit trail, with the account named `sduser`. [unverified: the trail's wording is read from the source]

9. **Take it back.** Stop or delete the virtual machine or container, or remove the key (`solo-ssh.sh key-remove`) and change the account password on that installation. All of it is yours to do and takes effect at the next sign-in.

## What this does not give you

- **No scopes inside the account.** The agent can read, change and delete everything in `sduser` and everything its Linux user can reach. That is why your data is somewhere else.
- **No audit of content.** The trail names what the agent did, not what it saw.
- **No MCP door.** `sdctl` and `sd-mcp` are not built; the `.mcp.json` example in `templates/` shows the shape and does not work today. Over ssh or a pipe the agent is driving `sd-solo` itself, with commands piped to it, as `gplbld/sandbox-guide.py` does in a sandbox.
- **No protection against a prompt that persuades the agent to ask you for more.** When it asks for the administrator password, the answer is yours, and the safe default is no.

## A checklist to keep in the project

- [ ] the agent has a computer, virtual machine or container of its own, and no password or key of mine
- [ ] the account and administrator passwords on that installation are new ones
- [ ] the refusal probes of step 5 were run and every one was refused as the guide says
- [ ] nothing I care about is on that computer or reachable from it
- [ ] a person reviews everything before it reaches production
