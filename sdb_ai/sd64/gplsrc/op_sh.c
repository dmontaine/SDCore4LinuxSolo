/* OP_SH.C
 * Shell command execution
 * Copyright (c) 2007 Ladybridge Systems, All Rights Reserved
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
 * 
 * START-HISTORY:
 * 17 Nov 26 dm  S.62 NETDIRS (the owner's decision of 17 Nov, carried from SD Core in Solo's terms): os_path_ok_for_account() asks path_in_netdirs()
 *               last - a path resolved as the gate resolves it, inside a directory sd.conf's NETDIRS lists, is admitted to a session the OS switch
 *               holds to its account.  Entries are realpath'd once per process and ignored (named at sd-solo -start, netdirs_report()) when not
 *               absolute, not a directory, "/", or overlapping the Solo folder, the system directory, sd.conf's directory, USRDIR, GRPDIR or a
 *               registered account (re-read at each admission).
 * 17 Nov 26 dm  S.62 P-1225, P-1226 (Solo carry of SD Core's fix): sh_execute()'s child ends with _exit(127) when execv() fails (it fell through into the parent's code), and puts SD_SESSION=1 in the environment of the shell SH and OS.EXECUTE start, which sd.c refuses to start inside.
 * 11 Nov 26 dm  Carried from SD Core (S.96 M4, 2 Nov 26, commit 4324e2a4): resolve_gate_path() (Core's resolve_name()) refuses a name that is a link
 *               whose target does not exist (it was taken as a new name and judged inside the directory, so a write through it created a file wherever
 *               the link pointed).
 * 06 Nov 26 dm  S.152: os_sd_accounts_open() is gone; nothing called it (found by linking with --gc-sections).
 * 24 Oct 26 dm Solo carry 19 (the owner: "check, and close it if open"): MEASURED, an ordinary session with the OS switch OFF could overwrite, append to and delete the VOC's
 *           own files (voc/%0) through OSCOPY, !IOSCOPY, OPENSEQ + WRITESEQ and DELETESEQ, past the VOC rule (ruling 14) which only watches record writes.  The OS-path
 *           routes now ask edit_os_path_refusal() (SD Core's S.64 name; here it knows one kind, a component named voc below the account's directory) and edit_leaf_counts().
 *           path_inside_dir() was split: resolve_gate_path() is its resolution, shared with the new test (behaviour-preserving, the OS-gate rows prove it).
 * 21 Oct 26 dm Solo carry 10 (SD Core's S.73 item 1): path_inside_account() became path_inside_dir(rootdir, name) (rootdir NULL is the working directory, so the
 *           account's own test is unchanged) and os_path_inside() is the geometry alone, for K_PATH_IN.
 * 20 Oct 26 SOLO OS SWITCH (the owner: two words like SD Core, SET.OS.ACCESS, the installer asks): SD Core's S.63 (13 Oct 26) carried
 *           to Solo, by hunk from Core 215ce2c and abcda0c.  os_permitted() is back and the gate reaches OS paths.  OS.EXECUTE and the SH
 *           verb are refused (10053, 10054) to an account that has not been given them; OPENSEQ, OPENPATH, DIR() and the other routes
 *           are refused (ER_PERM) outside the account's own directory unless it holds OS.EXECUTE; K_PATH_OK lets an $internal program
 *           ask the same question on the user's behalf.  SH and OS.EXECUTE are OFF unless the administrator turns them on (SET.OS.ACCESS),
 *           which is Solo's own: SD Core's per-account verbs, the SD.ACCOUNTS gate and the S.64 edit gates are not here.
 * 18 Sep 26 dm Teardown (S.27): os_permitted() and its refusal are gone.
 *           OS.EXECUTE and the SH verb now run at the account's own Linux
 *           permissions - the euid drop already made a session the account's
 *           OS user, and SD keeps no second wall (owner's teardown of the
 *           tier model, 18 Sep 2026).
 * 10 Sep 26 dm  Parity audit: the SH1 clparse bound is 8, so a long configured
 *               SH1 cannot write past argv (the Windows port's PRE_RELEASE 174).
 * 09 Sep 26 dm PRE_RELEASE 23 commit 2: os_permitted() also honours USR_OS_EXEC,
 *           the per-account ACC$OS.EXEC grant loaded at account entry, so an
 *           administrator can give a named non-admin account OS.EXECUTE.
 * 09 Sep 26 dm PRE_RELEASE 23 commit 1: os_permitted() gates OS.EXECUTE to a
 *           $internal program or an administrator (owner's model, 9 Sep 26:
 *           "os.execute and shell are off for anyone but administrators").
 *           op_sh() was previously ungated.  The per-account ACC$OS.EXEC grant
 *           that widens this to named non-admins is commit 2.
 * 31 Dec 23 SD launch - prior history suppressed
 * END-HISTORY
 *
 * START-DESCRIPTION:
 *
 * END-DESCRIPTION
 *
 * START-CODE
 */

#include "sd.h"
#include "header.h"
#include "syscom.h"
#include "tio.h"
#include "config.h"
#include <signal.h>
#include <dirent.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

#include <sys/stat.h>
#include <sys/wait.h>

/* Modified by Composer AI - 2026/06/10.
   k_error() never returns, but the analyzer cannot see that across
   translation units. */
void k_error(char msg[], ...) __attribute__((noreturn));
/* -------------------- */

void set_term(bool trap_break);
void set_old_tty_modes(void);
void set_new_tty_modes(void);
void op_capture(void);

Private void sh(bool capture);
Private void sh_execute(char *command);
Private int clparse(char *p, char *argv[], int maxargs);
Private bool os_permitted(void);
Private bool path_inside_dir(const char *rootdir, const char *name);

int ChildPipe = -1;
bool in_sh = FALSE; /* 0562 Doing SH command? */

#define MAX_SH_COMMAND_LENGTH 32000
Private char *cmd_str = NULL;

/* ======================================================================
   op_sh()  -  Launch a DOS command                                       */

void op_sh() {
  /* Stack:

     |=============================|=============================|
     |            BEFORE           |           AFTER             |
     |=============================|=============================|
 top |  Command to execute         |                             |
     |=============================|=============================|
 */

  sh(FALSE);
}

/* ======================================================================
   op_shcap  -  Launch SH command, capturing output                       */

void op_shcap() {
  /* Stack:

     |=============================|=============================|
     |            BEFORE           |           AFTER             |
     |=============================|=============================|
 top |  ADDR to capture variable   |                             |
     |-----------------------------|-----------------------------|
     |  Command to execute         |                             |
     |=============================|=============================|
 */

  DESCRIPTOR temp;

  /* Swap top two stack items so that the command is on top */

  temp = *(e_stack - 1);
  *(e_stack - 1) = *(e_stack - 2);
  *(e_stack - 2) = temp;

  sh(TRUE);
}

/* ======================================================================
   The OS-access gates (13 Oct 26, S.63; carried to Solo 20 Oct 26).

   os_gate_open()  -  has THIS ACCOUNT been given OS access?  The administrator always has it; anyone else
   has it only if the administrator switched it on (SET.OS.ACCESS OS ON), which LOGIN and APISRVR load into the
   session at account entry.  It does NOT look at HDR_INTERNAL, because the question it answers is about
   the person, not about the program: an $internal program that acts for the user (QPROC writing a CSV report
   to a pathname) is exempt from the gate itself and must not become the way round it.

   os_permitted()  -  may THIS PROGRAM run OS.EXECUTE or the SH verb?  A $internal system program (every shipped
   OS.EXECUTE caller is one) is trusted; otherwise the account must hold the gate.  The SH verb and "!" are gated
   by CPROC at the prompt (os.command, on K_SH) and reach here as an internal caller.

   os_path_ok_for_account()  -  may this account open this OS pathname with OPENSEQ or OPENPATH?  Yes if
   it holds the gate; otherwise only inside its own directory (the process's working directory, which is
   the account, set by LOGIN and not changeable from BASIC).  The name is resolved with realpath() before the
   comparison - the longest part that exists, then the rest - so ".." and a symbolic link inside the account
   that points out of it do not get round it.  A path it cannot resolve is a no.  (17 Nov 26, S.62: then, last, a directory
   sd.conf's NETDIRS lists - path_in_netdirs(), empty as delivered.)

   os_path_open_ok()  -  the same for a caller: an $internal program is trusted, anyone else is asked.   */

bool os_gate_open(void) {
  return (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC)) != 0;
}

Private bool os_permitted(void) {
  if (process.program.flags & HDR_INTERNAL)
    return TRUE;
  return os_gate_open();
}

/* 21 Oct 26 (Solo carry 10, SD Core's second sitting of 13 Oct): the test is "inside THIS directory", and the account's own directory is the case where the directory
   is the working directory (rootdir NULL).  A directory given is for API request 29 (os_path_inside, K_PATH_IN), which asks it of the account NAMED in the request.
   A relative name is relative to the directory asked about.                                                                                                   */
/* 24 Oct 26, Solo carry 19: the resolution half of path_inside_dir(), shared with edit_os_path_refusal().  ROOT (PATH_MAX + 1 bytes) is the directory asked about and
   RESOLVED (2 * PATH_MAX + 2) the name, both through realpath() (what exists, then the tail), root without a trailing slash.  FALSE if either cannot be resolved,
   the tail has a "." or "..", or the directory is "/".                                                                                                       */
Private bool resolve_gate_path(const char *rootdir, const char *name, char *root, char *resolved) {
  char cwd[PATH_MAX + 1];
  char work[2 * PATH_MAX + 2];
  char tail[PATH_MAX + 1];
  char *p;
  size_t root_len;
  size_t n;

  if ((name == NULL) || (name[0] == '\0'))
    return FALSE;
  if (rootdir != NULL) {
    if ((rootdir[0] != '/') || (strlen(rootdir) > PATH_MAX))
      return FALSE;
    strcpy(cwd, rootdir);
  } else if (getcwd(cwd, sizeof(cwd)) == NULL)
    return FALSE;
  if (realpath(cwd, root) == NULL)
    return FALSE;

  if (name[0] == '/') {
    if (strlen(name) > PATH_MAX)
      return FALSE;
    strcpy(work, name);
  } else {
    if (strlen(cwd) + strlen(name) + 2 > sizeof(work))
      return FALSE;
    strcpy(work, cwd);
    strcat(work, "/");
    strcat(work, name);
  }

  /* Resolve what exists; whatever does not yet exist (a file about to be created) is the tail, and a tail
     may not contain ".." because there is nothing to resolve it against. */
  tail[0] = '\0';
  for (;;) {
    struct stat lst;

    if (realpath(work, resolved) != NULL)
      break;
    /* 2 Nov 26 (SD Core S.96 M4, carried 11 Nov 26): a name that is a LINK whose target is not there is not "a file about to be created": a write
       through it creates the target wherever the link points.  It cannot be judged, so it is refused (the OS switch asks this function). */
    if ((lstat(work, &lst) == 0) && S_ISLNK(lst.st_mode))
      return FALSE;
    p = strrchr(work, '/');
    if (p == NULL)
      return FALSE;
    if ((strcmp(p + 1, "..") == 0) || (strcmp(p + 1, ".") == 0))
      return FALSE;
    if (p[1] != '\0') {
      /* prepend this component to the tail */
      n = strlen(p + 1);
      if (n + strlen(tail) + 2 > sizeof(tail))
        return FALSE;
      if (tail[0] != '\0') {
        memmove(tail + n + 1, tail, strlen(tail) + 1);
        tail[n] = '/';
        memcpy(tail, p + 1, n);
      } else {
        memcpy(tail, p + 1, n + 1);
      }
    }
    if (p == work) {
      /* only the root is left */
      strcpy(resolved, "/");
      break;
    }
    *p = '\0';
  }

  if (tail[0] != '\0') {
    if (strlen(resolved) + strlen(tail) + 2 > (size_t)(2 * PATH_MAX + 2))
      return FALSE;
    if (strcmp(resolved, "/") != 0)
      strcat(resolved, "/");
    strcat(resolved, tail);
  }

  root_len = strlen(root);
  while ((root_len > 1) && (root[root_len - 1] == '/'))
    root[--root_len] = '\0';
  if (root_len == 1)           /* an account at "/" would contain the whole machine: refuse */
    return FALSE;
  return TRUE;
}

Private bool path_inside_dir(const char *rootdir, const char *name) {
  char root[PATH_MAX + 1];
  char resolved[2 * PATH_MAX + 2];      /* realpath() needs PATH_MAX; the tail is appended after it */
  size_t root_len;

  if (!resolve_gate_path(rootdir, name, root, resolved))
    return FALSE;
  root_len = strlen(root);
  if (strncmp(resolved, root, root_len) != 0)
    return FALSE;
  return (resolved[root_len] == '\0') || (resolved[root_len] == '/');
}

/* ======================================================================
   NETDIRS (17 Nov 26, S.62; the owner's decision of 17 Nov: Linux Core gains Windows' parameter, and a feature needed for parity is built "on
   multiple systems if needed to achieve parity, taking into account the differences between operating systems and core vs solo purpose").
   Carried from SD Core for Linux in Solo's terms.  sd.conf's NETDIRS= names directories, separated by ";", OUTSIDE THE ACCOUNT that a session
   the OS switch holds to its account may still reach, to read and to write.  Empty as delivered: nothing is added.

   WHO IT REACHES: only the sessions os_path_ok_for_account() would refuse - not the administrator or an account given OS ON (SET.OS.ACCESS),
   which pass before it is asked, and not an $internal program (os_path_open_ok() trusts it before).  It is asked LAST, after the account's own
   directory.  It widens nothing else: the VOC rule on OS paths (edit_os_path_refusal(), below, and the record rule in op_dio3.c), OS.EXECUTE and
   the SH verb (os_permitted()), the AI wall and the SDSYS tests are separate questions the callers ask after this one.

   WHEN: Solo reads sd.conf at sd-solo -start only (config.c; the segment's template, copied by each process in bind_sysseg()), so the list a
   session holds is the one read at the last start: A CHANGE TAKES EFFECT AT THE NEXT START.  (SD Core reads it in every session, its W.11 F9,
   which Solo did not take: Solo's segment is mode 0600 and belongs to the one user.)

   THE PATH is resolved exactly as the gate resolves it (resolve_gate_path(): links and ".." resolved as far as the path exists, a link to nothing
   refused, a ".." or "." in the part that does not exist refused), and a resolved name that still holds a "." or ".." component is refused
   before any comparison.  The comparison is case-sensitive and ends at a component boundary, so /data/xkey is not inside /data/x.

   AN ENTRY is resolved with realpath() when the list is read (once per process), so an entry that is a link matches by its target.  It is
   IGNORED - and named in the error log and syslog at sd-solo -start (netdirs_report(), start_sd()) - when it is not absolute, is not an existing
   directory, is "/", holds or lies inside the SOLO FOLDER (GetHomePath(): sd.conf, the account in user_accounts, the passwords in $cred, the
   ssh server's sshd, the AI key folder ai, the TLS files, the tools with the MCP launcher - all of them are in it), the SD system directory, the
   directory of sd.conf, USRDIR or GRPDIR (each may be moved out of the folder by sd.conf), or the directory of any registered account (read again
   at every admission), or when more than MAX_NETDIRS are listed.  A folder that cannot be found or resolved takes every entry with it (refused,
   not guessed).  An element longer than a pathname is discarded, never cut.                                                                  */

#define MAX_NETDIRS 16

Private char netdirs_root[MAX_NETDIRS][PATH_MAX + 1];
Private int netdirs_count = -1; /* -1: the list has not been read in this process */

/* Is the resolved name A the directory B or inside it?  B has no trailing "/" (realpath() leaves none) and is never "/". */
Private bool netdir_within(const char *a, const char *b) {
  size_t n = strlen(b);

  if ((n <= 1) || (strncmp(a, b, n) != 0))
    return FALSE;
  return (a[n] == '\0') || (a[n] == '/');
}

Private bool netdir_overlap(const char *a, const char *b) {
  return netdir_within(a, b) || netdir_within(b, a);
}

/* A "." or ".." component left in a resolved name: the prefix test would mean nothing. */
Private bool netdir_dot_component(const char *p) {
  while ((p = strchr(p, '/')) != NULL) {
    p++;
    if ((p[0] == '.') && ((p[1] == '\0') || (p[1] == '/') || ((p[1] == '.') && ((p[2] == '\0') || (p[2] == '/')))))
      return TRUE;
  }
  return FALSE;
}

/* Does ROOT hold, or lie inside, the directory of a registered account?  1 yes (its name in WHICH), 0 no, -1 the register cannot be read
   (taken as yes by every caller).  Line 1 of each record of the register (<sysdir>/accounts) is the account's path. */
Private int netdir_account_clash(const char *root, char *which, size_t which_len) {
  char regdir[PATH_MAX + 1];
  char recpath[PATH_MAX + 1];
  char body[4096];
  char acct[PATH_MAX + 1];
  char *p;
  DIR *d;
  struct dirent *ent;
  FILE *fp;
  size_t got;
  int clash = 0;

  if (snprintf(regdir, sizeof(regdir), "%s%caccounts", (char *)(sysseg->sysdir), DS) >= (int)sizeof(regdir))
    return -1;
  if ((d = opendir(regdir)) == NULL)
    return -1;
  while ((clash == 0) && ((ent = readdir(d)) != NULL)) {
    if ((ent->d_name[0] == '.') || (ent->d_name[0] == '%') || (strchr(ent->d_name, '/') != NULL))
      continue;
    if (snprintf(recpath, sizeof(recpath), "%s%c%s", regdir, DS, ent->d_name) >= (int)sizeof(recpath))
      continue;
    if ((fp = fopen(recpath, "r")) == NULL)
      continue;
    got = fread(body, 1, sizeof(body) - 1, fp);
    fclose(fp);
    body[got] = '\0';
    if ((p = strchr(body, '\n')) != NULL)
      *p = '\0';
    if ((body[0] != '/') || (strlen(body) > PATH_MAX) || (realpath(body, acct) == NULL))
      continue; /* no directory there to protect */
    if (netdir_overlap(root, acct)) {
      clash = 1;
      if (which != NULL)
        snprintf(which, which_len, "%.64s", ent->d_name); /* an account name is far shorter; the name is only reported */
    }
  }
  closedir(d);
  return clash;
}

/* Say why an entry is ignored, at sd-solo -start; a session ignores it without a word.  The starter is the one user, who owns errlog. */
Private void netdir_note(bool report, const char *entry, const char *why) {
  char msg[MAX_PATHNAME_LEN + 200];

  if (!report)
    return;
  snprintf(msg, sizeof(msg), "NETDIRS: %s is ignored - %s", entry, why);
  log_message(msg);
  syslog(LOG_WARNING, "sd-solo: %s", msg);
}

/* The resolved form of a directory SD keeps a listed directory clear of; FALSE when it is not there (nothing to keep clear of). */
Private bool netdir_resolved(const char *dir, char *out) {
  return (dir != NULL) && (dir[0] == '/') && (strlen(dir) <= PATH_MAX) && (realpath(dir, out) != NULL);
}

Private void netdirs_load(bool report) {
  char item[MAX_PATHNAME_LEN + 1];
  char root[PATH_MAX + 1];
  char home[MAX_PATHNAME_LEN + 1];
  char homedir[PATH_MAX + 1];
  char sysdir[PATH_MAX + 1];
  char confdir[PATH_MAX + 1];
  char other[PATH_MAX + 1];
  char which[64 + 1];
  char why[128 + 1];
  const char *p;
  char *slash;
  size_t n;
  int clash;
  struct stat st;
  bool have_home, have_sys, have_conf;

  netdirs_count = 0;
  if (pcfg.netdirs[0] == '\0')
    return;

  have_home = GetHomePath(home, sizeof(home)) && netdir_resolved(home, homedir) && (strcmp(homedir, "/") != 0);
  have_sys = netdir_resolved((char *)(sysseg->sysdir), sysdir);
  have_conf = netdir_resolved(config_path, confdir);
  if (have_conf) {
    slash = strrchr(confdir, '/');
    if ((slash == NULL) || (slash == confdir))
      have_conf = FALSE; /* sd.conf in "/": every entry would hold its directory, so none is taken */
    else
      *slash = '\0';
  }

  p = pcfg.netdirs;
  while (*p != '\0') {
    n = strcspn(p, ";");
    if (n > MAX_PATHNAME_LEN) {
      /* Discarded, never cut: a cut path is a SHORTER directory, which would admit more than was written. */
      snprintf(item, sizeof(item), "%.40s...", p);
      netdir_note(report, item, "it is longer than a pathname may be");
    } else if (n > 0) {
      memcpy(item, p, n);
      item[n] = '\0';
      why[0] = '\0';
      if (item[0] != '/')
        strcpy(why, "it is not an absolute path");
      else if ((realpath(item, root) == NULL) || (stat(root, &st) != 0) || !S_ISDIR(st.st_mode))
        strcpy(why, "it is not an existing directory");
      else if (strcmp(root, "/") == 0)
        strcpy(why, "it is the root directory, which holds the whole machine");
      else if (!have_home || netdir_overlap(root, homedir))
        strcpy(why, "it holds, or lies inside, the SD Core Solo folder");
      else if (!have_sys || netdir_overlap(root, sysdir))
        strcpy(why, "it holds, or lies inside, the SD system directory");
      else if (!have_conf || netdir_overlap(root, confdir))
        strcpy(why, "it holds, or lies inside, the directory of sd.conf");
      else if (netdir_resolved(pcfg.usrdir, other) && netdir_overlap(root, other))
        strcpy(why, "it holds, or lies inside, the directory of user accounts (USRDIR)");
      else if (netdir_resolved(pcfg.grpdir, other) && netdir_overlap(root, other))
        strcpy(why, "it holds, or lies inside, the directory of group accounts (GRPDIR)");
      else if ((clash = netdir_account_clash(root, which, sizeof(which))) != 0) {
        if (clash < 0)
          strcpy(why, "the account register cannot be read");
        else
          snprintf(why, sizeof(why), "it holds, or lies inside, the account %s", which);
      } else if (netdirs_count >= MAX_NETDIRS)
        snprintf(why, sizeof(why), "only %d directories are taken", MAX_NETDIRS);

      if (why[0] != '\0')
        netdir_note(report, item, why);
      else
        strcpy(netdirs_root[netdirs_count++], root);
    }
    p += n;
    if (*p == ';')
      p++;
  }
}

/* start_sd(): the list judged once at sd-solo -start, each entry it ignores named in the error log. */
void netdirs_report(void) {
  netdirs_load(TRUE);
  netdirs_count = -1; /* a session judges again in its own process */
}

/* Is NAME, resolved as the gate resolves it, inside a directory NETDIRS lists?  Asked by os_path_ok_for_account() alone, last. */
Private bool path_in_netdirs(const char *name) {
  char root[PATH_MAX + 1];
  char resolved[2 * PATH_MAX + 2];
  int i;

  if (pcfg.netdirs[0] == '\0')
    return FALSE;
  if (!resolve_gate_path(NULL, name, root, resolved))
    return FALSE;
  if (netdir_dot_component(resolved))
    return FALSE;
  if (netdirs_count < 0)
    netdirs_load(FALSE);
  for (i = 0; i < netdirs_count; i++) {
    if (netdir_within(resolved, netdirs_root[i]) && (netdir_account_clash(netdirs_root[i], NULL, 0) == 0))
      return TRUE;
  }
  return FALSE;
}

bool os_path_ok_for_account(const char *name) {
  if (os_gate_open())
    return TRUE;
  if (path_inside_dir(NULL, name))
    return TRUE;
  return path_in_netdirs(name); /* 17 Nov 26, S.62: the directories the administrator listed, asked last */
}

/* os_path_inside()  -  is this pathname inside THAT directory?  The OS gate is not asked: this is the geometry alone, for a BASIC program (APISRVR's request 29)
   that has already decided which directory is the account's.                                                                                            */
bool os_path_inside(const char *rootdir, const char *name) {
  return path_inside_dir(rootdir, name);
}

bool os_path_open_ok(const char *name) {
  if (process.program.flags & HDR_INTERNAL)
    return TRUE;
  return os_path_ok_for_account(name);
}

/* ======================================================================
   edit_os_path_refusal()  -  the OS-PATH routes to the VOC: OPENSEQ, DELETESEQ, OSPATH (delete, make), OSRENAME, a print file, a trace file, OSCOPY.

   24 Oct 26, Solo carry 19 (the owner: "check, and close it if open").  The VOC rule of 29 Sep (ruling 14, voc_write_refused() in op_dio3.c) watches the
   RECORD routes: a file variable on the VOC.  The VOC is a directory of the account (voc/%0, voc/%1), so a pathname gives the same power past it: MEASURED
   on a fresh sandbox, an ordinary session with the OS switch off overwrote, appended to and deleted voc/%0 with OSCOPY, !IOSCOPY, OPENSEQ + WRITESEQ and
   DELETESEQ.  SD Core's S.64 closes these with edit_os_path_refusal(), which knows three kinds (VOC, dictionary, program file); Solo has one rule, the VOC's, so
   this keeps Core's name and shape and classifies one: a component named voc (any case) below the account's own directory.

   The path is resolved as the OS gate resolves it.  Returns EDIT_NONE when the session may go on, or EDIT_VOC.  Read-only use is not asked: the callers use
   this where they would write, create, delete or rename.  INCLUDE_LEAF says whether the FINAL component counts: a caller that makes or removes a plain file
   (OPENSEQ, DELETESEQ, a print file) passes FALSE, since a record called voc in an ordinary directory file is a plain file, not a VOC; one whose final name may
   be a directory (OSCOPY's target, OSPATH deleting or making one) passes TRUE.  Every directory below the final component counts either way.

   NOT ASKED: the administrator (ADMIN, who may change the VOC) and an account that holds OS.EXECUTE, which has a shell and reaches the files as it always could.
   A path outside the account is the OS gate's to refuse, not this.  A path that cannot be resolved is refused.                                              */

int edit_os_path_refusal(const char *name, bool include_leaf) {
  char root[PATH_MAX + 1];
  char resolved[2 * PATH_MAX + 2];
  const char *rel;
  const char *p;
  const char *more;
  size_t root_len;
  size_t n;

  if (my_uptr->flags & (USR_ADMIN | USR_OS_EXEC))
    return EDIT_NONE;
  if ((name == NULL) || (name[0] == '\0'))
    return EDIT_NONE;
  if (!resolve_gate_path(NULL, name, root, resolved))
    return EDIT_VOC;   /* cannot tell: refuse (a gate that fails open on a path it cannot read is decoration) */

  root_len = strlen(root);
  if ((strncmp(resolved, root, root_len) != 0) || ((resolved[root_len] != '\0') && (resolved[root_len] != '/')))
    return EDIT_NONE;  /* outside the account's own directory: the OS gate has refused or allowed it */
  rel = resolved + root_len;

  for (p = rel; *p != '\0';) {
    while (*p == '/')
      p++;
    n = 0;
    while ((p[n] != '\0') && (p[n] != '/'))
      n++;
    more = p + n;
    while (*more == '/')
      more++;
    if ((n == 3) && (strncasecmp(p, "voc", 3) == 0) && (include_leaf || (*more != '\0')))
      return EDIT_VOC;
    p += n;
  }
  return EDIT_NONE;
}

/* edit_leaf_counts()  -  for a caller that DELETES, or COPIES INTO, an OS pathname whose final name may be a plain file or a directory (OSCOPY's target, OSPATH's
   delete): does that final name need classifying (include_leaf TRUE)?  Only if it is there and is not a plain file.  A plain file called voc is a record of whatever
   directory holds it, not a VOC; a name not made yet becomes a plain file when copied to, and there is nothing to delete.  A link, which could be to a directory,
   counts.  (SD Core's, unchanged.)                                                                                                                            */

bool edit_leaf_counts(const char *name) {
  struct stat sb;

  if ((name == NULL) || (name[0] == '\0') || (lstat(name, &sb) != 0))
    return FALSE;
  return !S_ISREG(sb.st_mode);
}

/* ======================================================================
   sh()  -  Execute shell command                                         */

Private void sh(bool capture) {
  DESCRIPTOR *descr;
  STRING_CHUNK *str;
  int bytes;

  /* 20 Oct 26 SOLO OS SWITCH (S.63): refuse before the stack is touched, so a refusal leaves it as it was found - the
     Windows port's placement.  k_error() does not return.                                            */
  if (!os_permitted())
    k_error(sysmsg(10054), process.username);

  descr = e_stack - 1;
  k_get_string(descr);
  str = descr->data.str.saddr;
  bytes = (str != NULL) ? str->string_len : 0;
  if (bytes > MAX_SH_COMMAND_LENGTH) {
    process.status = ER_LENGTH;
    k_dismiss();
  } else {
    if (cmd_str != NULL)
      k_free(cmd_str); /* From an earlier k_error() */

    cmd_str = k_alloc(111, bytes + MAX_PATHNAME_LEN + 10); /* Allow for strcat on Windows */
    k_get_c_string(descr, cmd_str, bytes);
    k_dismiss();

    if (capture) {
      /* Set up capture mechanism */

      if (capturing) /* This is a nested EXECUTE...CAPTURING structure */
      {
        process.program.flags |= PF_CAPTURING;

        if (capture_head != NULL) /* Stack data already captured */
        {
          process.program.saved_capture_head = capture_head;
          process.program.saved_capture_tail = capture_tail;
        }
      }

      capture_head = NULL;
      capturing = TRUE;
      stack_display_pu();
    }

    sh_execute(cmd_str);
    k_free(cmd_str);
    cmd_str = NULL;

    if (capture) {
      op_capture(); /* Use op_capture() to save the command output */
    }
  }
}

/* ======================================================================
   sh_execute()  -  Execute SH command                                    */

Private void sh_execute(char *command) {
#define PIPE_BUFFER_SIZE 2048
  char buffer[PIPE_BUFFER_SIZE];
  bool saved_trap_break_char;
  bool saved_pagination;
  bool use_output_pipe;
  /* Modified by Composer AI - 2026/06/10.
     Initialize pipe fd pairs so paths that skip pipe() do not read
     indeterminate values; use -1 for unused slots. */
  /* int ChildToSDPipe[2]; */
  int ChildToSDPipe[2] = {-1, -1};
  bool use_input_pipe;
  /* int SDToChildPipe[2]; */
  int SDToChildPipe[2] = {-1, -1};
  /* -------------------- */
  char *argv[10];
  int cpid;
  int16_t i;
  int bytes;
  int child_status;

  char dflt_sh[] = "/bin/bash -i";
  char dflt_sh1[] = "/bin/bash -c";

  saved_trap_break_char = trap_break_char;
  saved_pagination = (tio.dsp.flags & PU_PAGINATE) != 0;

  process.status = 0;
  process.os_error = 0;

  flush_dh_cache();

  /* Turn off pagination.  Much as it would be nice, we get thoroughly
    confused about whether input is for the executed command or a response
    to the end of page prompt.                                             */

  tio.dsp.flags &= ~PU_PAGINATE;

  set_old_tty_modes();
  in_sh = TRUE; /* 0562 */

  /* If the user entered SD from the operating system command prompt, we
    can simply let the child process take over our stdout and stderr.
    If they have come in from a network or we need to capture the output
    for some reason, we must use a pipe. Although it sounds simpler always
    to use the pipe, this has some impact on the executed commands if they
    check the device type of the standard file handles.                     */

  use_output_pipe = capturing                          /* Trap output for EXECUTE CAPTURING */
                    || (connection_type != CN_CONSOLE) /* Not a direct connection */
                    || (tio.como_file >= 0);           /* Real como file */

  /* Similarly, on the input side, we need to use a pipe to feed the shell
    process if the real source of input is a socket. This allows us to
    perform input editing and avoids the shell moaning that stdin is not
    suitable.                                                             */

  use_input_pipe = (connection_type == CN_SOCKET);

  if (use_output_pipe && pipe(ChildToSDPipe)) {
    k_error("Cannot create child output pipe");
  }

  if (use_input_pipe && pipe(SDToChildPipe)) {
    /* Modified by Composer AI - 2026/06/10.
       Close the output pipe if input pipe creation fails. */
    if (use_output_pipe) {
      close(ChildToSDPipe[0]);
      close(ChildToSDPipe[1]);
    }
    /* -------------------- */
    k_error("Cannot create child input pipe");
  }

  /* 0420 Disable sigchld handler
    We need to do this to prevent the handler catching termination of
    the child process created below to execute this command.           */

  signal(SIGCHLD, SIG_DFL);

  cpid = fork();
  if (cpid == 0) /* Child process */
  {
    if (use_output_pipe) {
      dup2(ChildToSDPipe[1], 1);
      dup2(ChildToSDPipe[1], 2);
    }

    if (use_input_pipe) {
      dup2(SDToChildPipe[0], 0);
    }

    for (i = 3; i < 1024; i++)
      close(i);

    /* 17 Nov 26 dm - S.62 P-1226 (Solo carry of SD Core's fix).  The shell that SH and OS.EXECUTE start is marked as SD's
       child, so that sd.c refuses to start a second sd-solo inside it (the owner's rule of 15 Aug 26: somebody who shells
       out of SD with SH must not be able to run SD again).  A GUARD, NOT A BOUNDARY: the variable is in the user's own shell
       and the user can unset it.  Set in the CHILD, after the fork, so SD's own environment is untouched; a phantom
       (op_kernel.c, its own environment), the SENDMAIL and spooler commands (system()) and a scheduled job (a systemd user
       unit, started by the user's manager with its own environment) are not marked. */
    setenv("SD_SESSION", "1", 1);

    if (command[0] == '\0') /* Interactive shell */
    {
      clparse((pcfg.sh[0] != '\0') ? pcfg.sh : dflt_sh, argv, 10);
    } else /* Single command */
    {
      /* 10 Sep 26 dm - Parity audit: 8, NOT 9 (the Windows port's fix, its
         PRE_RELEASE_FIXES 174).  clparse returns AT MOST maxargs, and the two
         lines below write argv[i] and argv[i + 1]; argv holds 10 pointers, so a
         maxargs of 9 could write argv[10], one past the end, for any configured
         SH1 of nine or more space-separated tokens.  Reachable from the config
         file.  The interactive branch above keeps 10: it appends nothing. */
      i = clparse((pcfg.sh1[0] != '\0') ? pcfg.sh1 : dflt_sh1, argv, 8);
      argv[i] = command;
      argv[i + 1] = NULL;
    }

    execv(argv[0], argv);

    /* 17 Nov 26 dm - S.62 P-1225 (Solo carry).  execv() returns only when it failed, and the child then fell through into
       the PARENT's code below: a second copy of the session closing the parent's pipes and waiting for itself.  127 is what
       os.error() callers already read as "the command could not be run".  _exit, not exit: the child must not run the
       parent's atexit handlers or flush its stdio buffers. */
    _exit(127);
  } else if (cpid == -1) /* Error */
  {
    /* Modified by Composer AI - 2026/06/10.
       fork() failed; close any pipes that were opened. */
    if (use_output_pipe) {
      close(ChildToSDPipe[0]);
      close(ChildToSDPipe[1]);
    }
    if (use_input_pipe) {
      close(SDToChildPipe[0]);
      close(SDToChildPipe[1]);
    }
    /* -------------------- */
    k_error("Failed to start");
  } else /* Parent process */
  {
    if (use_input_pipe) {
      ChildPipe = SDToChildPipe[1];
      close(SDToChildPipe[0]);
    }

    if (use_output_pipe) {
      close(ChildToSDPipe[1]);

      while ((bytes = read(ChildToSDPipe[0], buffer, PIPE_BUFFER_SIZE)) > 0) {
        tio_display_string(buffer, bytes, TRUE, FALSE);
      }

      close(ChildToSDPipe[0]);
    }

    waitpid(cpid, &child_status, 0);
    process.os_error = WEXITSTATUS(child_status); /* 0420 */

    /* 0420 Re-enable sigchld handler and clear any backlog */

    signal(SIGCHLD, sigchld_handler);
    while (waitpid(-1, &child_status, WNOHANG) > 0) {
    }

    if (use_input_pipe) {
      ChildPipe = -1;
      close(SDToChildPipe[1]);
    }
  }

  set_new_tty_modes();
  in_sh = FALSE; /* 0562 */

  if (saved_pagination)
    tio.dsp.flags |= PU_PAGINATE;
  else
    tio.dsp.flags &= ~PU_PAGINATE;
  set_term(saved_trap_break_char);
}

/* ======================================================================
   clparse()  -  Parse a command line into an argv array                  */

Private int clparse(char *p, char *argv[], int maxargs) {
  int argc; /* resolves CWE-197 */

  /* Although this works for our purposes, it isn't perfect. It really
    should handle quotes and \ escapes.                                */

  for (argc = 0; argc < maxargs; argc++) {
    if ((argv[argc] = strtok(p, " ")) == NULL)
      break;
    p = NULL;
  }

  return argc;
}

/* END-CODE */
