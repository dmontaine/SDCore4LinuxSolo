/* INIPATH.C
 * Get system paths
 * Copyright (c) 2004 Ladybridge Systems, All Rights Reserved
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
 * 31 Dec 23 SD launch - prior history suppressed
 * 15 Sep 26 dm - read SD_CONFIG, not SCARLET_CONFIG, and bound the copy.
 * 29 Sep 26 SD Core for Linux Solo (LSOLO 3) - SD_CONFIG_DEFAULT is gone; the
 *           home is found from the executable's own path (GetHomePath).
 * END-HISTORY
 *
 * START-DESCRIPTION:
 *
 * The variable is SD_CONFIG (SD_CONFIG_ENV in sddefs.h, where the reasoning
 * is).  It was SCARLET_CONFIG here while sdclilib.c read SD_CONFIG, so
 * setting the one you would expect configured the server or the client but
 * never both.  SCARLET_CONFIG is not read any more.
 *
 * SD CORE FOR LINUX SOLO: THE HOME IS WHERE THE PROGRAMS ARE.  Solo installs
 * into one folder, ~/SDCoreSolo, with the programs in its bin, so the home is
 * the folder above the directory holding the running executable.  sd.conf is
 * <home>/sd.conf, SDSYS defaults to <home> itself (the Linux code finds
 * <sysdir>/bin/pcode) and the account folders sit in it; nothing holds the
 * user's path, so the tree works wherever it is
 * put.  Mirrors SD Core Solo for Windows (its inipath.c).
 *
 * FROM THE EXECUTABLE'S OWN PATH (/proc/self/exe), NOT FROM THE WORKING
 * DIRECTORY OR $HOME.  And the folder must carry the marker file
 * .sdcoresolo, written by the installer: without it this refuses, because a
 * guess at the home from an executable somewhere else is worse than an error
 * - in particular a development run from sdb_ai/sd64/bin would otherwise
 * take the SOURCE TREE for an installation.  A development run sets
 * SD_CONFIG.
 *
 * END-DESCRIPTION
 *
 * START-CODE
 */

#include "sd.h"
#include <unistd.h>

/* ======================================================================
   GetHomePath()  -  The installation's own folder, with no trailing
                     slash.  FALSE if it cannot be had; callers must fail
                     rather than guess.                                     */

bool GetHomePath(char* buff, int buff_len) {
  char exe[MAX_PATHNAME_LEN + 1];
  char marker[MAX_PATHNAME_LEN + 16];
  char* p;
  ssize_t n;

  if ((buff == NULL) || (buff_len < 2))
    return FALSE;

  n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
  if ((n <= 0) || (n >= (ssize_t)sizeof(exe) - 1))
    return FALSE;
  exe[n] = '\0';

  /* <home>/bin/sd  ->  <home>.  Strip the name, then insist on bin.        */

  if (((p = strrchr(exe, '/')) == NULL) || (p == exe))
    return FALSE;
  *p = '\0';
  if (((p = strrchr(exe, '/')) == NULL) || (p == exe) ||
      (strcmp(p + 1, "bin") != 0))
    return FALSE;
  *p = '\0';

  if (snprintf(marker, sizeof(marker), "%s/.sdcoresolo", exe) >=
      (int)sizeof(marker))
    return FALSE;
  if (access(marker, F_OK) != 0)
    return FALSE;

  return (snprintf(buff, (size_t)buff_len, "%s", exe) < buff_len);
}

/* ======================================================================
   GetDefaultSysdir()  -  <home> itself, used when sd.conf names no SDSYS.
   The Linux code finds <sysdir>/bin/sd and <sysdir>/bin/pcode, so unlike
   Solo for Windows the SDSYS directory is the home, not a folder in it.    */

bool GetDefaultSysdir(char* buff, int buff_len) {
  char home[MAX_PATHNAME_LEN + 1];

  if (!GetHomePath(home, sizeof(home)))
    return FALSE;

  return (snprintf(buff, (size_t)buff_len, "%s", home) < buff_len);
}

/* ====================================================================== */

bool GetConfigPath(char *inipath) {

  char home[MAX_PATHNAME_LEN + 1];
  char* p;

  /* Callers pass a buffer of MAX_PATHNAME_LEN + 1.  Nothing here may write
     more than that - the environment supplies the string, so it is not ours
     to trust.                                                              */

  p = getenv(SD_CONFIG_ENV);
  if ((p != NULL) && (*p != '\0')) {
    snprintf(inipath, MAX_PATHNAME_LEN + 1, "%s", p);
    return TRUE;
  }

  if (!GetHomePath(home, sizeof(home))) {
    fprintf(stderr, "Cannot determine the SD Core for Linux Solo folder.\n");
    return FALSE;
  }

  return (snprintf(inipath, MAX_PATHNAME_LEN + 1, "%s/sd.conf", home) <
          MAX_PATHNAME_LEN + 1);
}

/* END-CODE */
