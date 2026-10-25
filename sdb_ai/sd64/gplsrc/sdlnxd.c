/* SDLNXD.C
 * SD Linux daemon.
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
 * 25 Oct 26 dm  The daemon's restart (carried): sd-solo-lnxd.service runs this program and restarts it if it dies (Restart=on-failure), so a daemon that finds another one
 *               already named in the segment (and running this same executable) ends with status 0 - there is one daemon at a time.
 * 25 Oct 26 dm  W.11 F1 (carried from the full product): this daemon no longer takes the system directory from the shared segment,
 *               which any process that can attach may change.  The directory is found from the daemon's own executable (own_sysdir()),
 *               "sd-solo -cleanup" is started with execl and no shell, and the error log is opened under the same directory.
 * 16 Oct 26 dm  The scan for lost processes runs every CLEANUP seconds (sd.conf, 30 to 3600, default 300) - QM4 gaps.
 * 10 Sep 26 dm  Parity audit: a semaphore failure prints its reason before
 *               exit(2) (UPSTREAM_FIXES 3, the Windows port's proposal).
 * 31 Dec 23 SD launch - prior history suppressed
 * END-HISTORY
 *
 * START-DESCRIPTION:
 *
 * END-DESCRIPTION
 *
 * START-CODE
 */

#define Public
#define init(a) = a
#include "sd.h"

#include <time.h>
#include <ctype.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <signal.h>
#include <sched.h>
#include <limits.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>

int shmid; /* Shared memory id */

bool terminate = FALSE;

/* W.11 F1: the system directory, taken from this program's own path (<sysdir>/bin/sdlnxd), NOT from the shared segment. */
static char own_sysdir_path[PATH_MAX + 1];

static bool own_sysdir(void) {
  char exe[PATH_MAX + 1];
  char* slash;
  ssize_t n;
  struct stat st;
  char sdpath[PATH_MAX + 16];

  if ((n = readlink("/proc/self/exe", exe, PATH_MAX)) <= 0)
    return FALSE;
  exe[n] = '\0';
  if ((slash = strrchr(exe, '/')) == NULL)
    return FALSE;
  *slash = '\0'; /* .../bin */
  if (((slash = strrchr(exe, '/')) == NULL) || (strcmp(slash, "/bin") != 0))
    return FALSE;
  *slash = '\0'; /* the system directory */
  if (exe[0] == '\0')
    return FALSE;
  if (snprintf(sdpath, sizeof(sdpath), "%s/bin/" SD_SERVER_NAME, exe) >= (int)sizeof(sdpath))
    return FALSE;
  if ((stat(sdpath, &st) != 0) || !S_ISREG(st.st_mode) || (access(sdpath, X_OK) != 0))
    return FALSE;
  strcpy(own_sysdir_path, exe);
  return TRUE;
}

void check_lost_users(void);

void signal_handler(int signum);

/* ====================================================================== */

#define TICK_SECONDS 10

void log_message(char* msg);

/* Does the segment name another live process that is running this program?  The pid alone is not enough: a daemon that died leaves its pid in the segment, and the number
   may be reused by anything, so the other process's executable must be this one's. */
static bool another_daemon_runs(void) {
  char link[48];
  char other[PATH_MAX + 1];
  char mine[PATH_MAX + 1];
  ssize_t n_other;
  ssize_t n_mine;
  pid_t pid = (pid_t)sysseg->sdlnxd_pid;

  if ((pid <= 0) || (pid == getpid()))
    return FALSE;
  if ((kill(pid, 0) != 0) && (errno != EPERM))
    return FALSE;
  snprintf(link, sizeof(link), "/proc/%d/exe", (int)pid);
  n_other = readlink(link, other, sizeof(other) - 1);
  n_mine = readlink("/proc/self/exe", mine, sizeof(mine) - 1);
  if ((n_other <= 0) || (n_mine <= 0) || (n_other != n_mine))
    return FALSE;
  return memcmp(other, mine, (size_t)n_mine) == 0;
}

int main() {
  char errmsg[80];
  int elapsed = 0;  /* seconds since the last scan for lost processes */
  int interval;     /* CLEANUP */

  process.user_no = -2; /* Mark as sdlnxd for semaphore table */

  if (!own_sysdir()) {
    fprintf(stderr, "sdlnxd: cannot find the system directory from its own path (it must run as <sysdir>/bin/sdlnxd)\n");
    exit(3);
  }

  signal(SIGTERM, signal_handler);

  /* Attach the shared memory segment */

  if (((shmid = shmget(SD_SHM_KEY, 0, 0666)) == -1) ||
      (((sysseg = (SYSSEG*)shmat(shmid, NULL, 0))) == (void*)(-1))) {
    exit(1);
  }

  /* Get access to semaphores */

  /* 10 Sep 26 dm - Parity audit (UPSTREAM_FIXES 3, the port's proposal):
     errmsg has just been filled in with the reason and was discarded, so a
     daemon that would not start left nothing anywhere to read.  log_message()
     cannot be used this early - it takes ERRLOG_SEM, and the semaphores are
     precisely what failed - so stderr it is. */
  if (!get_semaphores(FALSE, errmsg)) {
    fprintf(stderr, "sdlnxd: %s\n", errmsg);
    exit(2);
  }

  /* 25 Oct 26 dm - one daemon at a time.  The daemon can now be started two ways (forked by a plain "sd-solo -start", or run by sd-solo-lnxd.service), and a second one
     would scan for lost users twice.  If the segment names a live process that runs this very program, this one ends - with status 0, so that the service does not count
     it as a failure and start it again. */
  if (another_daemon_runs()) {
    char note[100];

    snprintf(note, sizeof(note), "sdlnxd: pid %d is already the daemon; this one (pid %d) ends", (int)sysseg->sdlnxd_pid, (int)getpid());
    log_message(note);
    shmdt((void*)sysseg);
    return 0;
  }

  /* Set process id into shared memory */

  sysseg->sdlnxd_pid = getpid();

  /* ========================= Main loop ========================= */

  /* 16 Oct 26 dm - QM4 gaps, CLEANUP.  The scan for lost processes runs every CLEANUP seconds (30 to 3600, 300 unless sd.conf
     says otherwise; it was a fixed five minutes).  The loop wakes every ten seconds so that the shortest interval is kept to
     within one tick and so that a terminate signal is acted on without waiting out a minute.  A segment that holds no usable
     value (one made by an older build) gets the five minutes it always had.                                              */

  while (!terminate) {
    interval = sysseg->cleanup;
    if ((interval < 30) || (interval > 3600))
      interval = 300;

    elapsed += TICK_SECONDS;
    if (elapsed >= interval) {
      elapsed = 0;
      check_lost_users();
    }

    sleep(TICK_SECONDS);
  }

  /* Tidy up on our way out */

  shmdt((void*)sysseg); /* Dettach shared memory */

  return 0;
}

/* ======================================================================
   check_lost_users()  -  Clear down "lost" processes                     */

void check_lost_users() {
  USER_ENTRY* uptr;
  int32_t pid;
  int16_t u;
  int16_t num_checked = 0;
  bool lost_user_detected = FALSE;
  char cmd[MAX_PATHNAME_LEN + 10];

  StartExclusive(SHORT_CODE, 69);

  for (u = 1; u <= sysseg->max_users; u++) {
    uptr = UPtr(u);
    pid = uptr->pid;
    if (uptr->uid) {
      if ((++num_checked % 5) == 0) {
        /* Be nice - don't hold sempahore for entire table scan */

        EndExclusive(SHORT_CODE);
        RelinquishTimeslice;
        StartExclusive(SHORT_CODE, 69);
        if (uptr->uid == 0)
          continue; /* User logged out */
      }

      if (kill(pid, 0) && (errno != EPERM)) {
        lost_user_detected = TRUE;
        break;
      }
    }
  }

  EndExclusive(SHORT_CODE);

  if (lost_user_detected) {
    /* Fire off a SD session to clear down the users. Although it would be
      nice to do the whole job here, there are so many dependencies that
      sdlnxd ends up carrying around most of SD.                          */
    // converted to snprintf() -gwb 25Feb20
    /* Modified by Composer AI - 2026/06/10.
       Single-quote the executable path so spaces or shell metacharacters
       in the (administrator controlled) system directory cannot break or
       inject into the command. Also do not execute the command at all if
       it would have been truncated, instead of running a mangled path. */
    /* if (snprintf(cmd, MAX_PATHNAME_LEN + 10, "%s/bin/sd -cleanup", sysseg->sysdir) >= (MAX_PATHNAME_LEN + 10)) {
        printf(
            "Overflowed path/filename buffer. Truncated to:\n%s/bin/sd "
            "-cleanup",
            sysseg->sysdir);
      }
    system(cmd); */
    /* 25 Oct 26 dm - W.11 F1: the program is <own sysdir>/bin/sd-solo, started with execl (no shell), never a path read from the segment. */
    if (snprintf(cmd, sizeof(cmd), "%s/bin/" SD_SERVER_NAME, own_sysdir_path) >= (int)sizeof(cmd)) {
        printf(
            "Overflowed path/filename buffer. Cleanup not run for:\n%s/bin/" SD_SERVER_NAME " "
            "-cleanup",
            own_sysdir_path);
      } else {
        pid_t child = fork();
        if (child == 0) {
          execl(cmd, SD_SERVER_NAME, "-cleanup", (char*)NULL);
          _exit(127);
        } else if (child > 0) {
          waitpid(child, NULL, 0);
        }
      }
    /* -------------------- */
  }
}

/* ======================================================================
   Signal handler                                                         */

void signal_handler(signum) int signum;
{
  switch (signum) {
    case SIGTERM:
      signal(SIGTERM, SIG_IGN);
      terminate = TRUE;
      break;
  }
}

/* ======================================================================
   log_message()  -  Add message to error log                             */

void log_message(char* msg) {
  int errlog;
  time_t timenow;
  struct tm* ltime;
  int bytes;
#define BUFF_SIZE 4096
  char buff[BUFF_SIZE];
  static char* month_names[12] = {
      "January", "February", "March",     "April",   "May",      "June",
      "July",    "August",   "September", "October", "November", "December"};

  if (sysseg->errlog) {
    StartExclusive(ERRLOG_SEM, 71);

    /* W.11 F1: not the segment's copy; snprintf, because the path can be up to PATH_MAX long */
    if (snprintf(buff, BUFF_SIZE, "%s%cerrlog", own_sysdir_path, DS) >= BUFF_SIZE)
      errlog = -1;
    else
      errlog = open(buff, O_RDWR | O_CREAT | O_BINARY, 0777);

    /* Modified by Composer AI - 2026/06/10.
       If the open() failed, "bytes" was used uninitialized and write()/
       close() were called with a negative file descriptor. Move the
       write and close inside the successful-open branch. */
    /* if (errlog >= 0) {
      lseek(errlog, 0, SEEK_END);

      timenow = time(NULL);
      ltime = localtime(&timenow);

      bytes = sprintf(buff, "%02d %.3s %02d %02d:%02d:%02d [sdlnxd]:%s   %s%s",
                      ltime->tm_mday, month_names[ltime->tm_mon],
                      ltime->tm_year % 100, ltime->tm_hour, ltime->tm_min,
                      ltime->tm_sec, Newline, msg, Newline);
    }

    write(errlog, buff, bytes);

    close(errlog); */
    if (errlog >= 0) {
      lseek(errlog, 0, SEEK_END);

      timenow = time(NULL);
      ltime = localtime(&timenow);

      bytes = sprintf(buff, "%02d %.3s %02d %02d:%02d:%02d [sdlnxd]:%s   %s%s",
                      ltime->tm_mday, month_names[ltime->tm_mon],
                      ltime->tm_year % 100, ltime->tm_hour, ltime->tm_min,
                      ltime->tm_sec, Newline, msg, Newline);

      write(errlog, buff, bytes);

      close(errlog);
    }
    /* -------------------- */

    EndExclusive(ERRLOG_SEM);
  }
}

/* END-CODE */
