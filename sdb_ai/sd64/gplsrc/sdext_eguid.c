/* SDEXT_EGUID.C
 * SD_EUID_SET / SD_EUID_RESTORE via SDEXT (op_sdext.c) - NO-OPS in Solo
 * Copyright (c)2025 The SD Developers, All Rights Reserved
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
 * rev 0.9.0 Jan 25 mab initial commit
 * 29 Sep 26 SD Core for Linux Solo (LSOLO 4) - THE BODY IS GONE.  It switched
 *               the process's effective uid and gid to a named account's
 *               operating system user, and back, so a session could reach
 *               that account's files.  Solo has one account, sduser, which is
 *               not an operating system user, and every session runs as the
 *               one Linux user who owns the tree, so there is nothing to
 *               switch to and nothing to restore.  See PROJECT_STATUS.md.
 * END-HISTORY
 *
 * START-DESCRIPTION:
 *
 * Both keys answer 0 (success) and change nothing: no uid, no gid, no
 * supplementary group, not process.username.  They are kept, not deleted,
 * for two reasons.  The SDEXT key numbers 102 and 103 are shared with SD Core
 * for Linux and SD Core for Windows and are not renumbered.  And the BASIC
 * programs EUID_SET and EUID_RESTORE, and CPROC's LOGTO, still call them
 * until LSOLO 6 rebuilds the administrator gate; a call that returned an
 * error would break them for no gain.
 *
 * END-DESCRIPTION
 *
 * START-CODE
 */


#include "sd.h"

#include "keys.h"

void sdext_eguid_set(int key, char* Arg){

  (void)Arg;

  process.status = 0;   /* setup status() value */

  switch (key) {

    case SD_EUID_SET :     /* nothing to become */
    case SD_EUID_RESTORE : /* nothing to restore */
      InitDescr(e_stack, INTEGER);
      (e_stack++)->data.value = 0;
      break;

  }

  return;
}

/* END-CODE */
