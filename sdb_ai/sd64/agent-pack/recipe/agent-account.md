# Giving an AI agent a way into SD Core for Linux Solo: two shapes, no code

**Words used:** none (this product has no account words)

**Scripts used:** `installsdsolo.sh`, `solo-ssh.sh`

An agent that works on an SD project needs a place to work and a limit on what it can reach. Prompts, tool scopes and promises inside the agent's own software protect against mistakes and against instructions injected into data it reads. They do not stop an agent that can run as the Linux user who owns the installation: it can read the kept copy of the account password, open an interactive `sd-solo` as the owner and do anything the owner can. What decides how far an agent can reach is **who it runs as**, and **whether the two OS switches are on** (the shell, `sh`, and OS access, `os`; both are off as delivered, and `set.os.access` turns each on). SD Core for Linux Solo has **one account**, so there is no account to make for the agent and nothing inside the account that scopes it: whoever has the account password has all of the account. And **only one SD can run on a computer** (the shared-memory name and the API and ssh ports, 4249 and 4251, are machine-wide), so a second Solo for another Linux user on the same computer is not an option.

It needs no code from this project and no change to an installed system. Everything marked [unverified] below was read from the documentation and the source and was not run end to end for this recipe; the refusals in step 4 of shape 1 were run (they are the probes of `guide/sd-basic-guide.md`, part B2, run by `gplbld/sandbox-guide.py` in a sandbox, in a plain session of `sduser` with both switches off).

## Before you start

- The agent is **never you**. Do not give it your passwords, your Linux password, or a terminal that is already signed in.
- Decide what the agent is for (one project, one set of programs) and which files it needs.
- Decide whether it needs the shell or OS access. Most work on SD programs and data needs neither: compiling, running, files and queries are all inside SD. If it does need one, that is the case for shape 2, and the switch is the user's to turn on (`ADMIN`, then `set.os.access sh on` or `set.os.access os on`).

## Shape 1: the agent is a client of your installation, with both switches OFF

What it gets: the account (`sduser`) and nothing outside it. With `sh` and `os` off an agent that holds the account password cannot run a Linux command, read or write a file outside the account's directory, or change the VOC. It can read, change and delete everything the account holds, **including your production data**, so use this only for an account whose data the agent may touch.

1. **Check the switches are off.** Type `ADMIN`, then `set.os.access` with no argument: it must say `Account sduser has SH no, OS.EXECUTE no`. If it does not, `set.os.access sh off` and `set.os.access os off` put it right, and the next sign-in sees it.
2. **Give the agent a way in that is not your Linux login.** Over ssh: add the agent's public key to Solo's own key file with `solo-ssh.sh key-add` (the agent then signs in on port 4251 with the key and types the **account password**; the ssh sign-in runs `sd-solo`, never a shell). Or through the API on port 4249, which takes the account password and no key. [unverified: read from the Solo ssh and API pages, not run here] The agent runs as nothing on your computer: it is a client, on another machine or as a Linux user that has no access to your installation.
3. **Give it the account password and nothing else.** Never the administrator password, the global password or your Linux password. A password you gave out is a password to change when the work ends (`set.password`).
4. **Prove the walls before you trust them.** As the agent, run the probes of `guide/sd-basic-guide.md` part B2: `sh` and `os.execute` must say they are not permitted, a file outside the account must be refused (status 3035), `config`, a `copy` into the VOC and `catalog ... global` must be refused. If one succeeds, a switch is on that you did not mean to turn on.
5. **Install the knowledge.** The skill (`agent-pack/skill/sd-core-solo/` into the project's `.claude/skills/sd-core-solo/`) and `agent-pack/templates/CLAUDE.md` in the project root, filled in. They carry the rules; they are not the wall.
6. **Keep the hand-over human.** The agent proposes; a person reads the program and puts it where it belongs.
7. **Watch it.** Its sessions and its refusals are in the installation's audit trail, with the account named `sduser`. [unverified: the trail's wording is read from the source]
8. **Take it back.** `solo-ssh.sh key-remove`, and change the account password. Both are yours.

## Shape 2: the agent has a computer of its own

Use it when the agent needs the shell or OS access, or when it must not see your account. The wall is the operating system: the agent's computer holds nothing you want to keep from it.

1. **Get the computer.** A separate machine, a virtual machine, or a container with its own IPC namespace and its own network address. [unverified] Not a second Linux user on your own computer.
2. **Install the product there as an ordinary Linux user of its own**, with `installsdsolo.sh` (it refuses to run as root and installs into that user's home). Choose **new passwords** for the account and for the administrator; they are not your passwords. The installer asks whether to turn on the shell and OS access: say yes only for what the project needs. [unverified: the installer's prompts are documented in the Solo Getting Started pages, not run here]
3. **Give it a workspace** with copies of what it needs. Do not mount your real data.
4. **Give it a way in** as in shape 1, step 2, or let it run on that computer as the installation's own Linux user.
5. **Prove the walls**, as in shape 1, step 4 (with a switch on, the matching probe is allowed, and that is what you chose).
6. **Install the knowledge**, keep the hand-over human, and watch the audit trail, as in shape 1.
7. **Take it back** by stopping or deleting the virtual machine or container.

## What this does not give you

- **No scopes inside the account.** The agent can read, change and delete everything in `sduser`, and, with a switch on, everything its Linux user can reach. That is why production data belongs somewhere else, or behind shape 2.
- **No protection if you turn a switch on later.** The switches are yours; a refusal that stops the agent today does not stop it after `set.os.access os on`.
- **No audit of content.** The trail names what the agent did, not what it saw.
- **No MCP door.** `sdctl` and `sd-mcp` are not built; the `.mcp.json` example in `templates/` shows the shape and does not work today. Over ssh or a pipe the agent is driving `sd-solo` itself, with commands piped to it, as `gplbld/sandbox-guide.py` does in a sandbox.
- **No protection against a prompt that persuades the agent to ask you for more.** When it asks for the administrator password, or for a switch to be turned on, the answer is yours, and the safe default is no.

## A checklist to keep in the project

- [ ] the agent is not on my Linux login and holds no password of mine but the account password (shape 1) or has a computer of its own (shape 2)
- [ ] `set.os.access` says no and no unless the project needs a switch, and I said so
- [ ] the refusal probes were run and every one was refused as the guide says
- [ ] nothing I care about is reachable from the agent beyond what the project needs
- [ ] a person reviews everything before it reaches production
