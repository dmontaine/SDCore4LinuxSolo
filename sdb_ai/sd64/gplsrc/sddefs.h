/* SDDEFS.H
 * SD definitions common to all components.
 * Copyright (c) 2006 Ladybridge Systems, All Rights Reserved
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
 * 02 Jul 24 mab define max string size.
 * 06 Aug 24 mab define sdext max arg
 * 15 Sep 26 dm - SD_CONFIG_ENV / SD_CONFIG_DEFAULT, one pair for both sides.
 * 29 Sep 26 SD Core for Linux Solo - SD_CONFIG_DEFAULT removed; see inipath.c
 * 02 Oct 26 SD Core for Linux Solo - SD_SHM_KEY / SD_SEM_KEY 0x53434C11/12.
 * END-HISTORY
 *
 * START-DESCRIPTION:
 *
 * END-DESCRIPTION
 *
 * START-CODE
 */

#ifndef __SDDEFS
#define __SDDEFS

/* Platforms and derivations */

#define PRODUCT_KEY 2
#define PLATFORM_NAME "Linux"
#define NIX
#define BSD
#define FALLBACK
#define HOT_SPOT_MONITOR

/* 19 Sep 26 dm - GUARDED.  linuxio.c defines _GNU_SOURCE before its includes
   (SO_PEERCRED), and glibc's features.h then sets _XOPEN_SOURCE itself, so an
   unconditional define here warned "redefined" in that one file.  Guarding is
   the correct shape anyway and changes nothing where it is not predefined.  */
#ifndef _XOPEN_SOURCE
#define _XOPEN_SOURCE 700
#endif
#define _XOPEN_CRYPT
#include <unistd.h>

#include <endian.h>

#if __BYTE_ORDER__ == __BIG_ENDIAN__
#define BIG_ENDIAN_SYSTEM
#endif

#define environ __environ


#define Seek(fu, offset, whence) lseek(fu, offset, whence)

/* Derived items */

#define DS '/'
#define DSS "/"
#define Newline "\n"
#define NewlineBytes 1

#define default_access 0666
#define O_BINARY 0
#define O_TEXT 0
#define FOPEN_READ_MODE "r"
#define FOPEN_WRITE_MODE "w"
#define NULL_DEVICE "/dev/null"

#define ALIGN2 __attribute__((aligned(2), packed))

#define MakeDirectory(path) mkdir(path, 0777)

/* 02 Oct 26 dm - A KEY PAIR PER SD CORE PRODUCT (owner, 2 Oct 2026, in the SD
 * Core for Linux session: "choose new shared memory segments for each of the
 * four versions so that they can run concurrently ... not the same as the
 * segment chosen upstream").  All four kept upstream SD's 0x716d0301/02, so
 * Solo could not run beside the multi-user SD (CLAUDE.md's old warning).  SD
 * Core's own family, agreed across the four products (mail 2026-10-02T1245):
 * 0x5343 ("SC"), "L"/"W", 0x full / 1x Solo -
 *   Linux 0x53434C01/02   Linux Solo 0x53434C11/12
 *   Windows 0x53435701/02 Windows Solo 0x53435711/12
 * An instance still running under the old key must be stopped by its own
 * binary first: solo-stage.sh's upgrade does (it runs the installed sd -stop
 * before it copies anything). */
#define SD_SHM_KEY 0x53434C11
#define SD_SEM_KEY 0x53434C12

#define RelinquishTimeslice sched_yield()

/* WINFS denotes use of the Windows file system interface (PDA only so far) */

#define OSError errno
#define OSFILE int
#define INVALID_FILE_HANDLE -1
#define ValidFileHandle(fu) (fu >= 0)
#define CloseFile(fu) close(fu)
#define Read(fu, buff, bytes) (read(fu, buff, bytes))
#define Write(fu, buff, bytes) (write(fu, buff, bytes))

#ifndef DS
#error No environment set
#endif

/* 020240702 mab Max String Size */
/* Max String (record) size is capped at A little under 2Gb or available memory space     */
/* Remember SD is a 32 bit VM, so this limit is a product of the data structres           */
/* created and used by SD.                                                                */
/* The limit introduced here is an arbitrary size less than the  2Gb limit imposed by the */
/* by the VM, modify as you see fit                                                       */
#define MAX_STRING_SIZE   1073741822   /* 1/ GB, 1FFF FFFF */ 

#define MAX_PATHNAME_LEN 255    /* Changes affect file headers */

/* 15 Sep 26 dm - where the configuration file lives.  Adopted from the
 * Windows port's decision of 14 Aug 2026 (its HISTORY.md, "The configuration
 * file finds itself"), which is this port's decision too.
 *
 * ONE VARIABLE AND ONE FILE, for the server and the client alike.  The server
 * read SCARLET_CONFIG (inipath.c) while the client library read SD_CONFIG
 * (sdclilib.c) - so setting the variable you would expect configured exactly
 * one of them.  SCARLET_CONFIG is not read any more: it named a project this
 * is not part of, and the standing rule is to convert rather than tolerate.
 * 29 Sep 26 SD Core for Linux Solo - SD_CONFIG_DEFAULT is gone.  With the
 * variable unset the file is sd.conf in the installation's own folder,
 * found at run time from the executable's path (inipath.c GetHomePath), so
 * no machine path is compiled in.  Same as SD Core Solo for Windows.
 *
 * The client library is a separate toolchain and does not include this header,
 * so it carries its own copy of these two values.  If you change them here,
 * change gplsrc/sdclilib.c to match.
 */
#define SD_CONFIG_ENV     "SD_CONFIG"

/* 02 Oct 26 SD Core for Linux Solo - THE SERVER'S FILE NAME (owner, 1 Oct 2026, in chat:
 * "sd = full version, sd-solo = solo version, both windows and linux, just rename the solo
 * exe to sd-solo").  Everything in this tree that starts the server by file name builds the
 * path from this - op_kernel.c (phantoms), sysseg.c (start_sd), sdlnxd.c (the cleanup tick)
 * and sdclilib.c (the local connect) - so the name lives in one place.  The Makefile's output
 * name and the scripts under gplbld/ and the installer carry it as text; gplbld/
 * test-soloexe-units.py checks that none of them still says bin/sd. */
#define SD_SERVER_NAME    "sd-solo"

/* 29 Sep 26 SD Core for Linux Solo (LSOLO 6) - THE ONE ACCOUNT, and every
 * session's user name (kernel.c init_kernel), whatever the Linux user is
 * called.  Owner's ruling 29 for Solo for Windows: "the name of the single
 * account is always sduser, not the name of the [operating system] account".
 * The BASIC side spells it in gpl.bp/solo_account; the installer and the
 * verify script use the same literal.  It is NOT an operating system user:
 * the process keeps running as the Linux user who owns the tree, and ssh
 * still authenticates that user.                                           */
#define SOLO_ACCOUNT_NAME "sduser"

#define MAX_ID_LEN 255          /* Increasing requires major file changes */
#define MAX_CALL_NAME_LEN 63    /* Cannot exceed MAX_ID_LEN */
#define MAX_TRIGGER_NAME_LEN 32 /* Increasing would alter file header */
#define MAX_PROGRAM_NAME_LEN 128
#define MAX_USERNAME_LEN 32
#define MAX_MATCH_TEMPLATE_LEN 256
#define MAX_MATCHED_STRING_LEN 8192
#define MAX_PACKAGES 32
#define MAX_PACKAGE_NAME_LEN 15
#define MAX_ACCOUNT_NAME_LEN 32
#define MAX_SORTMRG 10
#define MAX_SORT_KEYS 32
#define MAX_SORT_KEY_LEN 1024
/* 20240127 mab mods to handle AF_UNIX path length, defined in un.h as 108 characters  (108 + term char)*/
#define MAX_SOCKET_ADDR_STR_LEN 109

#define MAX_ERROR_LINES 3        /* because I HATE magic numbers! */
#define MAX_EMSG_LEN 80          /* These are used in k_error() in k_error.c */
/* 20240806 mab define sdext max arg */
#define SD_MAX_ARGS 10           /* max number of args passed by SDEXT function */ 
#define SD_ERR_MSG_LEN 512       /* max characters for error message */

#define Private static

#ifndef Public
#define Public extern
#endif

#ifndef init
#define init(a)
#endif

/* ======================================================================
   Type definitions                                                       */

typedef int16_t bool;
#define FALSE 0
#define TRUE 1

typedef int64_t int64;
typedef u_int64_t u_int64;

/* ======================================================================
   Byte ordering macros                                                   */

#ifdef BIG_ENDIAN_SYSTEM
short int swap2(int16_t n);
long int swap4(int32_t n);
#define ShortInt(n) swap2(n)
#define LongInt(n) swap4(n)
#else
#define ShortInt(n) (n)
#define LongInt(n) (n)
#endif

/* ======================================================================
   Case conversion macros and data                                        */

Public char uc_chars[256];
Public char lc_chars[256];
#define UpperCase(c) (uc_chars[((u_char)(c))])
#define LowerCase(c) (lc_chars[((u_char)(c))])

Public u_char char_types[256];
#define CT_ALPHA 0x01
#define CT_DIGIT 0x02
#define CT_GRAPH 0x04
#define CT_MARK 0x08
#define CT_DELIM 0x10

#define IsAlnum(c) (char_types[((u_char)(c))] & (CT_ALPHA | CT_DIGIT))
#define IsAlpha(c) (char_types[((u_char)(c))] & CT_ALPHA)
#define IsDigit(c) (char_types[((u_char)(c))] & CT_DIGIT)
#define IsGraph(c) (char_types[((u_char)(c))] & CT_GRAPH)
#define IsDelim(c) (char_types[((u_char)(c))] & CT_DELIM)
#define IsMark(c) (char_types[((u_char)(c))] & CT_MARK)

/* Collation map */

Public char* collation_map_name init(NULL);
Public char* collation init(NULL);

#define SortCompare(s1, s2, n, nocase) \
  ((nocase) ? MemCompareNoCase(s1, s2, n) : memcmp(s1, s2, n))

#define TEXT_MARK ((char)-5)
#define SUBVALUE_MARK ((char)-4)
#define VALUE_MARK ((char)-3)
#define FIELD_MARK ((char)-2)
#define ITEM_MARK ((char)-1)

#define U_TEXT_MARK ((u_char)'\xFB')
#define U_SUBVALUE_MARK ((u_char)'\xFC')
#define U_VALUE_MARK ((u_char)'\xFD')
#define U_FIELD_MARK ((u_char)'\xFE')
#define U_ITEM_MARK ((u_char)'\xFF')

#define TEXT_MARK_STRING "\xFB"
#define SUBVALUE_MARK_STRING "\xFC"
#define VALUE_MARK_STRING "\xFD"
#define FIELD_MARK_STRING "\xFE"
#define ITEM_MARK_STRING "\xFF"

#endif

/* END-CODE */
