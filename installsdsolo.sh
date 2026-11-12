#!/bin/bash
#
# SD Core for Linux Solo - install script
#   (c) 2026 Donald Montaine.  Released under the Blue Oak Model License 1.0.0,
#   a copy can be found on the web here: https://blueoakcouncil.org/license/1.0.0
#
#   bash installsdsolo.sh [options]        run it as YOUR OWN USER, never as root
#
# WHAT IT DOES.  Downloads the source of SD Core for Linux Solo (the main branch of
# github.com/dmontaine/SDCore4LinuxSolo) into a TEMPORARY directory under your home,
# builds it there, installs it into ~/SDCoreSolo, sets your passwords, starts it as
# your own systemd service, and deletes the download.  The script itself can be
# carried on a USB stick: it needs the network only for the packages and the download.
#
# WHAT NEEDS sudo, and ONLY this: installing the build packages, opening a firewall
# port you asked for (the API's, or ssh's), "loginctl enable-linger", and - only where
# SELinux is enabled and ssh is on - Solo's own PAM service, /etc/pam.d/sd-solo-ssh-<you>
# (LSOLO 31: Fedora's sshd PAM stack refuses a sshd that is not root; see tools/solo-ssh.sh).
# Everything else is done as you, in your own home.  Nothing else is written outside it.
#
# SSH (LSOLO 29, owner, 2 Oct 2026): Solo runs its OWN ssh listener on port 4251, fixed,
# as you and with no root: sign in with your Linux account name and password (checked by PAM, sent
# inside ssh's encrypted channel; a key is an optional extra), straight into sd, which then asks the
# SD account password.  It does not touch the machine's own sshd, so a person who also uses the
# multi-user SD Core reaches that one on port 22 and this one on 4251.  The earlier routes (a
# forced-command line in ~/.ssh/authorized_keys, and the sshd_config.d "Match User" block)
# are gone; --upgrade moves your Solo key lines into the new key file (after a copy of the old
# file) and tells you the one sudo command that removes the old block.  Installing the ssh
# server package (needed for /usr/sbin/sshd) also starts the machine's own sshd on port 22 on
# Debian and Ubuntu; this script does not change that.
#
# THE COMMAND NAMES (owner, 1 Oct 2026: "sd = full version, sd-solo = solo version, both
# windows and linux, just rename the solo exe to sd-solo").  The server is installed as
# <tree>/bin/sd-solo and ~/.local/bin/sd-solo links to it; plain "sd" is the multi-user SD
# Core's and this script never makes it.  An upgrade of a tree installed before this removes the
# old ~/.local/bin/sd (a link or this product's launcher) and moves the unit files and
# authorized_keys lines to the new name.  Until 2 Oct 2026 this script refused a computer that
# had the multi-user product; it no longer does.
#
# OPTIONS (all optional; the script asks for anything it needs that it was not given)
#   --home DIR                    install here instead of ~/SDCoreSolo
#   --control-file FILE           the answers to the questions, for an install nobody sits at
#                                 (see sd-solo-setup.conf.sample)
#   --account-password-file FILE  the account password, one line (for automation; delete the file)
#   --admin-password-file FILE    the administrator password, one line
#   --global-password-file FILE   the global password, one line.  Only a computer that an SD Core
#                                 server manages has one: you are asked for it last and may leave
#                                 it blank.  Having one is what makes the computer "managed".
#   --reload-data                 when the install directory holds the data and configuration that
#                                 "deletesdsolo.sh --keep-data" left there (a .sdcore-kept stamp, the
#                                 account's files, sd.conf, newvoc.mods), use them in this NEW install.  Passwords are
#                                 not kept: the install still asks for new ones.  On a terminal the
#                                 installer asks by itself; with no terminal and no answer it reloads.
#   --start-clean                 the opposite answer: the kept data is moved aside to <home>.kept-<time>
#                                 (never deleted) and the install is a clean one.  Neither option does
#                                 anything when nothing was kept.  Not for --upgrade.
#   --api off|local|open          the API listener, your choice in every install;
#                                 always port 4249 - fixed, not an option (owner, 2 Oct 2026)
#   --ssh off|local|open          Solo's own ssh listener, your choice in every install;
#                                 always port 4251 - fixed, not an option.  Sign-in: your Linux password, or a key.
#                                 DEFAULT local (on, this computer only), as Windows Solo's is, and the ssh server
#                                 package (openssh-server) is installed if it is missing: --ssh off declines it.
#                                 With --skip-packages and no sshd the default is off.  The API's default is off.
#                                 Three wrong passwords from one address within ten minutes lock that address for ten.
#   --ssh-key FILE                a public key to add for ssh straight into sd (turns ssh on, local,
#                                 unless --ssh says otherwise)
#   --os-access none|sh|os|both   the answer to the question "turn on the shell and OS access?" (20 Oct 2026, the OS
#                                 switch): sh = the SH verb and "!"; os = OS.EXECUTE, files outside the account,
#                                 Python and the editors that run outside SD; both = both; none = neither.  BOTH ARE OFF
#                                 unless you say so, and they can be turned on or off later with ADMIN and set.os.access.
#                                 On a terminal the installer asks (a fresh install and an upgrade, default no); with
#                                 no terminal, with --yes and no --os-access, or with none, both stay as they are
#                                 (off on a new account, as you left them on an upgrade).  The control file's os-access.
#   --viewer NAME|none            the answer to the question "allow a PDF reader to show the documentation?" (23 Oct 2026,
#                                 Solo carry 14): the pdf verb shows a documentation PDF even when the account has no OS
#                                 access, so it starts only a reader the administrator allowed.  NOTHING IS ALLOWED unless you
#                                 say so (default no); NAME is a reader found in /usr/bin, /usr/local/bin or /bin (evince,
#                                 okular, zathura, atril, xreader, mupdf, qpdfview, xpdf).  Asked on a terminal when such a
#                                 reader is installed and none is allowed yet; with no terminal, with --yes, or with none,
#                                 nothing is allowed.  Later: ADMIN, then set.viewer add pdf NAME.  The control file's viewer.
#   --enable-linger               run "loginctl enable-linger" so SD keeps running, and reachable, when nobody is signed in.
#                                 THE DEFAULT (9 Nov 26): on for every install, an unattended one included; asked on a terminal.
#   --no-linger                   do not: SD stops when your last session ends (also the control file's enable-linger=no)
#   --skip-packages               do not install packages; check the tools instead
#   --no-service                  do not install the systemd user service
#   --yes                         do not ask "Continue?" (nor the shell and OS access question: with --yes and no --os-access
#                                 nothing is turned on)
#   --upgrade                     bring an installed tree up to the current release in place:
#                                 programs and system objects are replaced; the account, its data,
#                                 the passwords, sd.conf, the audit trail, GLOBAL.BP.OUT and the
#                                 deny list are kept.  A safety copy of the whole tree is made
#                                 first (<home>.before-upgrade-<time>) and put back if any step
#                                 fails.  Takes no password and no other install option but --os-access and --viewer.
#
# EXIT: 0 installed and self-checked; 1 a step failed; 2 refused to start.
# The last line of a good install is "SOLO INSTALL COMPLETE <home>".
#
# OWNER'S RULINGS THIS FOLLOWS (PROJECT_STATUS.md, "WHAT SD CORE FOR LINUX SOLO IS"):
# no root and no OS users; the source is downloaded to a temporary directory under ~
# (29 Sep 2026); password order account, administrator, then - if there is one - global
# (ruling 30); the account password differs from the global one (ruling 19); "sd -internal"
# is closed when the install finishes (ruling 13, LSOLO 9).
# 06 Oct 2026 (owner, LSOLO 38): THERE IS ONE INSTALL, NOT TWO MODES.  The global password is
# optional - leave it blank if no SD Core server manages this computer - and the computer is
# managed if and only if it has one.  The API and ssh are always the user's choice, with or
# without a global password (this REVERSES ruling 22, which forced both open for a managed
# computer); the choice can be made in the install file.

set -euo pipefail

REPO_URL="https://github.com/dmontaine/SDCore4LinuxSolo"
REPO_BRANCH="main"
# 11 Nov 26 dm  S.216 (SD Core's installsdcore.sh DOCS_URL): the documentation repository whose User/markdown pages the AI line draws on (DOCS-CORPUS block below);
#            the same branch name as the source's.
DOCS_URL="https://github.com/dmontaine/SDCore4LinuxSoloDocs"
CLONE_DIR="$HOME/.sdsolotmp"
# TEST HOOK, NOT A FEATURE: SDSOLO_REPO_URL replaces the source repository, so an
# installer change can be tested from a local clone before it is pushed.  It is
# announced on every line of output that names the source, and a production install
# never sets it.  (The installer's contract is "installs origin/main"; anything
# tested through this hook is a test of THAT COMMIT, not of the published branch.)
if [ -n "${SDSOLO_REPO_URL:-}" ]; then
  REPO_URL="$SDSOLO_REPO_URL"
  printf '\033[0;33m*** SDSOLO_REPO_URL IS SET: the source is %s, NOT github.com ***\033[0m\n' "$REPO_URL" >&2
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
say()  { printf '%s\n' "$*"; }
warn() { printf '%b%s%b\n' "$YELLOW" "$*" "$NC"; }
refuse() { printf '%bREFUSED: %s%b\n' "$RED" "$*" "$NC" >&2; exit 2; }
# 02 Oct 26 (owner: "match the windows solo behavior"): what ssh becomes when the user did not choose it.  As in
# SD Core Solo for Windows (sd-solo.iss: the "Install the OpenSSH server" task is offered when no sshd is there
# and is ticked by default; unticking it leaves ssh not set up), the default is ON for this computer only, and
# the ssh server package is installed if it is missing; "--ssh off" (or answering off) is the way to decline.
# The one difference is a Linux one: with --skip-packages the user has forbidden package installation, so a
# missing sshd turns the default off instead of failing the install.  The function between the markers is run by
# gplbld/test-sshport-units.py: keep the lines, and keep it free of anything but its arguments.
# BEGIN ssh_default
ssh_default_choice() {   # ssh_default_choice GIVEN KEY HAVE_SSHD(0|1) SKIP_PACKAGES(0|1) -> off|local|open
  local given="$1" key="$2" have="$3" skip="$4"
  if [ -n "$given" ]; then echo "$given"; return 0; fi
  if [ -n "$key" ]; then echo local; return 0; fi
  if [ "$have" != "1" ] && [ "$skip" = "1" ]; then echo off; else echo local; fi
}
# END ssh_default
fail()   { printf '%bFAILED at: %s%b\n' "$RED" "$*" "$NC" >&2
           [ -z "${kept_aside:-}" ] || printf '%bYour saved data is safe, moved aside to %s%b\n' "$YELLOW" "$kept_aside" "$NC" >&2
           exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "run this as your own user, not root: SD Core for Linux Solo never runs as root"

# 11 Nov 26 dm  S.216 (SD Core's installsdcore.sh installer_dir, 24 Oct 26): WHERE THE INSTALLER LIVES, for the files that travel beside it in a release package (the changes
#            document and the pdf folder: the CHANGES-DOC and MANUALS-PDF blocks below).  Empty when the script was not run from a file (curl | bash), so nothing is looked
#            for in whatever directory the shell is in.
installer_dir=""
if [ -f "${BASH_SOURCE[0]:-}" ]; then installer_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd) || installer_dir=""; fi

# 12 Nov 26 dm - S.218 (SD Core's S.144 PACKAGE-SOURCE block, line for line; owner, 12 Nov 2026: "bring solo up to the same release state, programs,
#            documentation, release notes as Core").  THE RELEASE PACKAGE CARRIES THE SOURCE.  When the folder this script is in holds source/sdb_ai/sd64,
#            the install (and an --upgrade) builds from it: no GitHub check, no clone, and the AI line's documentation comes from source/docs.  The
#            package is checked first, before any question: every file under source/ must be listed in SHA256SUMS and match it, and source/SDCORE-RELEASE
#            must name the commit and branch it was made from.  A mismatch stops the install.  (The sums find damage; they cannot stop someone who
#            rewrites both.)  Without source/ the install is what it always was: a clone of REPO_BRANCH from REPO_URL.  The build packages still come from
#            the distribution (apt-get).  gplbld/mkrelease.sh makes the package; gplbld/test-install-package.sh runs this block.
# PACKAGE-SOURCE-BEGIN
pkg_source=""
pkg_commit=""
pkg_branch=""
pkg_pre=""
if [ -n "$installer_dir" ] && [ -d "$installer_dir/source/sdb_ai/sd64" ] && [ ! -L "$installer_dir/source" ]; then
    pkg_bad=""
    if [ ! -f "$installer_dir/SHA256SUMS" ] || [ -L "$installer_dir/SHA256SUMS" ]; then
        pkg_bad="it has no SHA256SUMS"
    elif ! (cd "$installer_dir" && sha256sum --quiet --strict -c SHA256SUMS >/dev/null 2>&1); then
        pkg_bad="a file under source/ does not match SHA256SUMS"
    elif [ "$(cd "$installer_dir" && find source -type f | wc -l)" != "$(grep -c '' "$installer_dir/SHA256SUMS" || true)" ]; then
        pkg_bad="source/ holds files that SHA256SUMS does not list"
    elif [ -n "$(cd "$installer_dir" && find source ! -type f ! -type d | head -1)" ]; then
        pkg_bad="source/ holds something that is neither a file nor a directory"
    else
        pkg_commit=$(sed -n 's/^commit=\([0-9a-f]\{40\}\)$/\1/p' "$installer_dir/source/SDCORE-RELEASE" 2>/dev/null | head -1 || true)
        pkg_branch=$(sed -n 's/^branch=\([A-Za-z0-9._-]\{1,40\}\)$/\1/p' "$installer_dir/source/SDCORE-RELEASE" 2>/dev/null | head -1 || true)
        if [ -z "$pkg_commit" ] || [ -z "$pkg_branch" ]; then pkg_bad="source/SDCORE-RELEASE does not name a commit and a branch"; fi
    fi
    if [ -n "$pkg_bad" ]; then
        printf "%b\n" "$RED"
        echo "This release package cannot be installed: ${pkg_bad}."
        echo "Download the package again, unpack it into an empty folder and run the installer from there."
        printf "%b\n" "$NC"
        exit 1
    fi
    pkg_source="$installer_dir/source"
    # a package made from a release-candidate tag (LS2.0-0-rc1) says so at the start and at the end of the install; the version stamp (LS2.0-0) is the
    # same in a candidate and in the release, so the build that was tested is the build that ships.
    case "$pkg_branch" in *-rc[0-9]*) pkg_pre="$pkg_branch" ;; esac
    REPO_BRANCH="$pkg_branch"
    REPO_URL="package:${installer_dir}"
fi
# PACKAGE-SOURCE-END
if [ -n "$pkg_source" ]; then
    src_desc="this package (${pkg_branch}, commit ${pkg_commit:0:12}), copied to $CLONE_DIR to build and removed afterwards"
else
    src_desc="$REPO_URL ($REPO_BRANCH), downloaded to $CLONE_DIR and removed afterwards"
fi

# ---------------------------------------------------------------- options
HOME_DIR="$HOME/SDCoreSolo"
control_file=""; managed=0   # managed is decided from the global password, below: there is no mode to choose
acc_file=""; adm_file=""; glb_file=""
reload_ans=""        # yes (--reload-data), no (--start-clean) or "": what to do with data a previous uninstall kept in the install directory
kept_tree=0; kept_aside=""; reload_dir=""
# 02 Oct 26 - THE API PORT IS 4249, FIXED (owner, 2 Oct 2026: "make ports 4247 and 4249
# -- do not allow adjustable ports").  --api-port is gone.  The witnesses' private
# ports go through solo-service.sh's announced test hook, SDSOLO_TEST_API_PORT.
api="" ; api_port="4249"
# 02 Oct 26 - Solo's own ssh listener, port 4251, FIXED (LSOLO 29, owner).  --ssh-match is gone
# with the routes it belonged to.  The witnesses' private port goes through the announced hook
# SDSOLO_TEST_SSH_PORT, as the API's does.
ssh=""; ssh_port="4251"
ssh_key=""; enable_linger=1; skip_pkgs=0; no_service=0; assume_yes=0; upgrade=0
linger_cli=""  # 9 Nov 26 (owner: "Yes, on by default"): yes|no when --enable-linger / --no-linger was given; linger_decide settles enable_linger
os_access=""   # 20 Oct 26, the OS switch: none|sh|os|both once answered (by --os-access, the control file, or the question)
viewer=""      # 23 Oct 26, Solo carry 14: a PDF reader to allow for the pdf verb (a name), or none; "" until answered
while [ "$#" -gt 0 ]; do
  case "$1" in
    --os-access)              [ "$#" -ge 2 ] || refuse "--os-access needs none, sh, os or both"; os_access="$2"; shift 2 ;;
    --viewer)                 [ "$#" -ge 2 ] || refuse "--viewer needs a reader name or none"; viewer="$2"; shift 2 ;;
    --home)                   [ "$#" -ge 2 ] || refuse "--home needs a directory"; HOME_DIR="$2"; shift 2 ;;
    --control-file)           [ "$#" -ge 2 ] || refuse "--control-file needs a file"; control_file="$2"; shift 2 ;;
    --managed)                refuse "--managed is gone: there is one install now. A computer is managed if it has a global password: give --global-password-file FILE, or answer the global password question; leave it blank if no SD Core server manages this computer." ;;
    --account-password-file)  [ "$#" -ge 2 ] || refuse "$1 needs a file"; acc_file="$2"; shift 2 ;;
    --admin-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; adm_file="$2"; shift 2 ;;
    --global-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; glb_file="$2"; shift 2 ;;
    --reload-data)            [ "$reload_ans" != "no" ] || refuse "--reload-data and --start-clean contradict each other"; reload_ans="yes"; shift ;;
    --start-clean)            [ "$reload_ans" != "yes" ] || refuse "--reload-data and --start-clean contradict each other"; reload_ans="no"; shift ;;
    --api)                    [ "$#" -ge 2 ] || refuse "--api needs off, local or open"; api="$2"; shift 2 ;;
    --ssh)                    [ "$#" -ge 2 ] || refuse "--ssh needs off, local or open"; ssh="$2"; shift 2 ;;
    --ssh-key)                [ "$#" -ge 2 ] || refuse "--ssh-key needs a public key file"; ssh_key="$2"; shift 2 ;;
    --ssh-match)              refuse "--ssh-match is gone: Solo's ssh has its own port (4251) now and no longer uses the machine's sshd_config. Use --ssh local or --ssh open." ;;
    --enable-linger)          linger_cli=yes; shift ;;
    --no-linger)              linger_cli=no; shift ;;
    --skip-packages)          skip_pkgs=1; shift ;;
    --no-service)             no_service=1; shift ;;
    --yes)                    assume_yes=1; shift ;;
    --upgrade)                upgrade=1; shift ;;
    -h|--help)                sed -n '2,95p' "$0"; exit 0 ;;
    *) refuse "unknown option: $1 (see --help)" ;;
  esac
done
case "$HOME_DIR" in /*) ;; *) refuse "--home must be an absolute path (got '$HOME_DIR')" ;; esac
case "$HOME_DIR" in *" "*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*|*'%'*) refuse "the install directory must not contain a space, quote, backslash, \$, backtick or %: $HOME_DIR" ;; esac
case "$api" in ""|off|local|open) ;; *) refuse "--api must be off, local or open (got '$api')" ;; esac
case "$ssh" in ""|off|local|open) ;; *) refuse "--ssh must be off, local or open (got '$ssh')" ;; esac
case "$os_access" in ""|none|sh|os|both) ;; *) refuse "--os-access must be none, sh, os or both (got '$os_access')" ;; esac
case "$viewer" in ""|none) ;; *[!a-z0-9._+-]*|.*) refuse "--viewer must be none or the name of a reader: letters, digits and . _ + - (got '$viewer')" ;; esac
if [ "$ssh" = "off" ] && [ -n "$ssh_key" ]; then refuse "--ssh-key needs ssh on; give --ssh local or --ssh open, or leave --ssh out"; fi
if [ -n "${SDSOLO_TEST_SSH_PORT:-}" ]; then
  case "$SDSOLO_TEST_SSH_PORT" in *[!0-9]*) refuse "SDSOLO_TEST_SSH_PORT must be a number (got '$SDSOLO_TEST_SSH_PORT')" ;; esac
  { [ "$SDSOLO_TEST_SSH_PORT" -ge 1024 ] && [ "$SDSOLO_TEST_SSH_PORT" -le 65535 ]; } 2>/dev/null || refuse "SDSOLO_TEST_SSH_PORT must be 1024-65535"
  ssh_port="$SDSOLO_TEST_SSH_PORT"
  printf '\033[0;33m*** SDSOLO_TEST_SSH_PORT IS SET: the ssh port is %s, NOT 4251 (a test hook) ***\033[0m\n' "$ssh_port" >&2
fi
# The test hook, validated here as solo-service.sh validates it, because $api_port goes into
# a sed and a ufw command below, and announced on every use like SDSOLO_REPO_URL.
if [ -n "${SDSOLO_TEST_API_PORT:-}" ]; then
  case "$SDSOLO_TEST_API_PORT" in *[!0-9]*) refuse "SDSOLO_TEST_API_PORT must be a number (got '$SDSOLO_TEST_API_PORT')" ;; esac
  { [ "$SDSOLO_TEST_API_PORT" -ge 1024 ] && [ "$SDSOLO_TEST_API_PORT" -le 65535 ]; } 2>/dev/null || refuse "SDSOLO_TEST_API_PORT must be 1024-65535"
  api_port="$SDSOLO_TEST_API_PORT"
  printf '\033[0;33m*** SDSOLO_TEST_API_PORT IS SET: the API port is %s, NOT 4249 (a test hook) ***\033[0m\n' "$api_port" >&2
fi

interactive=0; [ -t 0 ] && [ -r /dev/tty ] && interactive=1

# ---------------------------------------------------------------- what is already here
# BEGIN is_kept_tree
is_kept_tree() {   # is_kept_tree DIR: what "deletesdsolo.sh --keep-data" leaves - the stamp, the account, sd.conf and, if there was one, newvoc.mods; nothing else
  local d="$1" e
  { [ -f "$d/.sdcore-kept" ] && [ ! -f "$d/.sdcoresolo" ] && [ -d "$d/user_accounts/sduser/voc" ]; } || return 1
  { [ ! -L "$d" ] && [ ! -L "$d/user_accounts" ] && [ ! -L "$d/user_accounts/sduser" ]; } || return 1
  [ "$(stat -c %u "$d/user_accounts/sduser")" = "$(id -u)" ] || return 1
  for e in "$d"/* "$d"/.[!.]* "$d"/..?*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    case "${e##*/}" in
      user_accounts|sd.conf|.sdcore-kept) ;;
      # 24 Oct 26 (PAL-36): the administrator's site-local VOC additions are read into the VOC as the administrator, so only a REAL directory owned by this user is
      # accepted: a link, a file of that name, or somebody else's directory makes the folder "not ours" and the install refuses it, as it refuses any other stranger.
      # 9 Nov 26 (Solo carry 22): the saved copies of VOC records the update removed (voc_removed.saved) are kept on the same terms.
      newvoc.mods|voc_removed.saved) { [ -d "$e" ] && [ ! -L "$e" ] && [ "$(stat -c %u "$e")" = "$(id -u)" ]; } || return 1 ;;
      *) return 1 ;;
    esac
  done
  [ -z "$(ls -A "$d/user_accounts" | grep -v '^sduser$')" ] || return 1
  return 0
}
# END is_kept_tree
if [ -f "$HOME_DIR/.sdcoresolo" ] && [ "$upgrade" -eq 0 ]; then
  refuse "SD Core for Linux Solo is already installed in $HOME_DIR.
  To bring it up to the current release, keeping your account, data and passwords:
      bash $0 --upgrade --home $HOME_DIR
  To remove it instead (your data can be kept):
      bash $HOME_DIR/tools/deletesdsolo.sh"
fi
if [ "$upgrade" -eq 1 ]; then
  [ -f "$HOME_DIR/.sdcoresolo" ] || refuse "there is no SD Core for Linux Solo in $HOME_DIR to upgrade (no .sdcoresolo marker)"
  [ -f "$HOME_DIR/.sdcore-install" ] || refuse "$HOME_DIR has no .sdcore-install record - it was not installed by installsdsolo.sh; upgrade it by hand or reinstall"
  [ -z "$control_file$acc_file$adm_file$glb_file$api$ssh$ssh_key$reload_ans$linger_cli" ] \
    || refuse "--upgrade keeps the passwords (and so whether a global password is set), the account's data and sd.conf, and the API and ssh settings as installed; it takes no password, control-file, --reload-data, --start-clean, --api, --ssh, --ssh-key, --enable-linger or --no-linger option"
elif [ -e "$HOME_DIR" ] && [ -n "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  # LSOLO 39: the one non-empty directory this installer will use is what deletesdsolo.sh --keep-data leaves:
  # the stamp, the account, sd.conf and, if there was one, newvoc.mods, and NOTHING else (a folder you have put other things in is never touched).
  if is_kept_tree "$HOME_DIR"; then
    kept_tree=1
  else
    refuse "$HOME_DIR exists and is not empty, and is not an SD Core for Linux Solo tree or the data and configuration one left (the .sdcore-kept stamp, user_accounts/sduser, sd.conf and a newvoc.mods directory, and nothing else); this script will not use it"
  fi
fi
# 02 Oct 26 - THE MULTI-USER PRODUCT NO LONGER BLOCKS THIS INSTALL (owner, 2 Oct 2026: yes to
# installing both).  The two have separate API ports (4247 / 4249) and shared-memory keys, and
# the command names below say which one you start.
[ "$upgrade" -eq 1 ] || { systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is already running for this user"; }
command -v systemctl >/dev/null || refuse "systemctl is required (a systemd user manager)"
[ -d "/run/user/$(id -u)" ] || warn "no /run/user/$(id -u): the systemd user manager may not be running in this shell"

# 04 Oct 26 - LSOLO 35: THE NETWORK IS CHECKED BEFORE ANYTHING IS ASKED OR CHANGED (owner, 4 Oct 2026:
# on Linux a USB stick carries only this installer and the documentation; the install downloads SD,
# because there are several target distributions to build for).  Without this an offline computer
# was asked every question, then sudo, and failed in the package step.  This needs only bash and
# getent (git may not be installed yet).  It refuses ONLY when it is sure: any proxy variable, or
# SD_SKIP_NET_CHECK=1, skips it, because a false refusal is worse than the late failure.  The
# function between the markers is run by gplbld/test-netpreflight-units.py: keep the lines, and
# keep it free of anything but its arguments and refuse().
# BEGIN net_preflight
net_preflight() {   # net_preflight HOST PORT
  local host="$1" port="$2" v why
  [ "${SD_SKIP_NET_CHECK:-}" = "1" ] && return 0
  for v in https_proxy HTTPS_PROXY all_proxy ALL_PROXY; do
    [ -n "${!v:-}" ] && return 0
  done
  if ! getent hosts "$host" >/dev/null 2>&1; then
    why="cannot look up $host"
  elif ! timeout 8 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$host" "$port" >/dev/null 2>&1; then
    why="cannot connect to $host port $port"
  else
    return 0
  fi
  refuse "this computer is not online: $why.
  This installer downloads SD from $host and the build packages from your distribution, so the
  computer must be connected to the internet while it runs.  A USB stick carries this installer
  and the documentation, not SD.  Nothing has been changed.  Connect to the internet and run it
  again.  If you do reach $host through a proxy this check cannot see, run it again as:
      SD_SKIP_NET_CHECK=1 bash $0"
}
# END net_preflight
# 11 Nov 26 - DEBIAN AND UBUNTU ONLY (owner, 11 Nov 2026: "Yes, Debian and Ubuntu only"; SD Core's S.105 of
# 2 Nov 2026).  The distribution is read HERE, before the network check, the banner, the questions, the
# first sudo and the first change to the machine; reading /etc/os-release needs no sudo.  A machine is
# accepted when ID or ID_LIKE names debian or ubuntu as a whole word (Debian, Ubuntu, Mint, Pop!_OS);
# Fedora, RHEL and its clones, Arch, openSUSE, anything else and a machine with no /etc/os-release are
# refused (refuse(): exit 2, nothing changed).  Until now Fedora had a dnf branch and every other
# distribution was refused only in the package step, after the questions.  gplbld/test-install-distro.sh
# runs this function on fake os-release files.
detect_distro() {
  local ids="" read_from
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    ids=" ${ID:-} ${ID_LIKE:-} "
    read_from="read from /etc/os-release: ${ID:-unknown}"
  else
    read_from="there is no /etc/os-release to read"
  fi
  case "$ids" in *" debian "*|*" ubuntu "*) return 0 ;; esac
  refuse "this distribution is not supported ($read_from).
  This installer supports Debian and Ubuntu (and their common derivatives) only.
  Fedora, RHEL and RHEL's clones, Arch and openSUSE are not supported.
  Nothing has been changed."
}
detect_distro
# The host is the one the installer clones from.  SDSOLO_REPO_URL (the test hook above) may name a
# local path, which needs no network, so only an https URL is tested.
if [ -z "$pkg_source" ] && [[ "$REPO_URL" =~ ^https://([^/:]+)/ ]]; then net_preflight "${BASH_REMATCH[1]}" 443; fi   # S.218: a release package carries the source, nothing is fetched

# ---------------------------------------------------------------- the password rule
# SD's rule (owner, 19 Sep 2026): 8 or more characters with a lower-case letter, an
# upper-case letter, a digit and a symbol, all printable ASCII 33-126 (no space - the
# same as gpl.bp/solo_password, which applies it again).  LC_ALL=C: English only.
pw_ok() {
  local p="$1"
  [ "${#p}" -ge 8 ] || return 1
  ( export LC_ALL=C
    [[ "$p" =~ ^[\!-\~]+$ ]] && [[ "$p" =~ [a-z] ]] && [[ "$p" =~ [A-Z] ]] && [[ "$p" =~ [0-9] ]] && [[ "$p" =~ [^a-zA-Z0-9] ]] )
}
PWRULE="at least 8 characters, with a lower-case letter, an upper-case letter, a digit and a symbol (letters, digits and punctuation only)"

read_password() {   # read_password "Prompt: " VARNAME  - stars, from the terminal
  local prompt="$1" __name="$2" ch pw=""
  printf '%s' "$prompt" > /dev/tty
  while IFS= read -r -s -n1 ch < /dev/tty; do
    case "$ch" in
      "") break ;;
      $'\177'|$'\b') if [ -n "$pw" ]; then pw=${pw%?}; printf '\b \b' > /dev/tty; fi ;;
      *) pw="$pw$ch"; printf '*' > /dev/tty ;;
    esac
  done
  printf '\n' > /dev/tty
  printf -v "$__name" '%s' "$pw"
}

# 20 Oct 26, THE SOLO OS SWITCH (owner: "ask during install"; his ruling of 18 Oct: OFF unless the administrator turns it on).  The shell
# and OS access are two switches of the one account, SH and OS, OFF as delivered.  The question is asked on a terminal, once, with default
# NO for each, on a first install AND on an upgrade (the upgrade is the one run in which an existing Solo, whose shell was never gated
# before, would otherwise lose it without a word); the answer is --os-access, and solo-stage.sh turns on what was said, with the verb.
# With no terminal, with --yes, or with neither answer, nothing is turned on here: off on a new account, as it was on an upgrade.
# The functions between the markers are run by gplbld/test-install-osaccess.sh: keep them free of anything but their arguments and
# the variables named in them.
# BEGIN os_access
os_access_word() {   # os_access_word SH_YES OS_YES (1 or 0 each) -> none|sh|os|both
  if [ "$1" = 1 ] && [ "$2" = 1 ]; then echo both
  elif [ "$1" = 1 ]; then echo sh
  elif [ "$2" = 1 ]; then echo os
  else echo none
  fi
}
os_yn() {   # os_yn "question": 0 only for an answer that starts with y; anything else, and an empty answer, is no
  local a
  read -r -p "$1 [y/N] " a < /dev/tty
  case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}
ask_os_access() {   # settles os_access when --os-access and the control file gave none: asks on a terminal, else none
  local sh_yes=0 os_yes=0
  [ -z "$os_access" ] || return 0
  if [ "$interactive" -ne 1 ] || [ "$assume_yes" -eq 1 ]; then
    os_access="none"
    say "  (the shell and OS access were not asked about - no terminal, or --yes, and no --os-access: nothing is turned on here)"
    return 0
  fi
  say
  say "The shell and OS access: OFF unless you turn them on."
  say "  The shell is the SH verb, which runs Linux commands.  OS access is OS.EXECUTE in a program, the embedded Python,"
  say "  micro, and files and directories outside the account by pathname.  Either lets whoever signs in do what your"
  say "  Linux user can do.  You can change this later: type ADMIN, then set.os.access."
  if [ "$upgrade" -eq 1 ]; then
    say "  Until this release the shell and OS access were always on; now they are off unless you say yes."
  fi
  if os_yn "Turn on the shell (SH) for your SD account?"; then sh_yes=1; fi
  if os_yn "Turn on OS access (os.execute, outside files, Python, micro) for your SD account?"; then os_yes=1; fi
  os_access="$(os_access_word "$sh_yes" "$os_yes")"
}
# END os_access

# 23 Oct 26, Solo carry 14 (S.75; SD Core's installer has the same question): THE QUESTION ABOUT A PDF READER.  The pdf verb shows the documentation even when the account has
# no OS access, which is a looser default than Solo's, so the list of readers it may start is EMPTY as delivered and this asks once, default NO.  It is asked on a terminal
# when a known reader is installed in /usr/bin, /usr/local/bin or /bin and the tree has no reader allowed yet (an upgrade keeps what the administrator chose); the answer is
# --viewer, and solo-stage.sh runs set.viewer, which tests the program.  With no terminal, with --yes, or with none, nothing is allowed.
# The functions between the markers are run by gplbld/test-install-viewer.sh: keep them free of anything but their arguments and the variables named in them.
# BEGIN viewer_ask
find_pdf_reader() {   # find_pdf_reader: the first known reader that is installed, or nothing
  local v d
  for v in evince okular zathura atril xreader mupdf qpdfview xpdf; do
    for d in /usr/bin /usr/local/bin /bin; do
      if [ -x "$d/$v" ]; then echo "$v"; return 0; fi
    done
  done
  return 0
}
ask_viewer() {   # settles viewer when --viewer and the control file gave none: asks on a terminal, else none
  local found
  [ -z "$viewer" ] || return 0
  if [ "$interactive" -ne 1 ] || [ "$assume_yes" -eq 1 ]; then
    viewer="none"
    return 0
  fi
  if grep -qs '^pdf ' "$HOME_DIR/viewers"; then viewer="none"; return 0; fi
  found="$(find_pdf_reader)"
  if [ -z "$found" ]; then viewer="none"; return 0; fi
  say
  say "The pdf verb shows the documentation in a PDF reader, even when your account may not run programs."
  say "  It starts only a reader that the administrator has allowed, and none is allowed unless you say so.  $found is installed here."
  say "  You can change this later: type ADMIN, then set.viewer."
  if os_yn "Allow $found to show the documentation?"; then viewer="$found"; else viewer="none"; fi
}
# END viewer_ask

# An upgrade asks only that one question (above) and reads the install's own record; a first install does
# everything from here to "scratch space".
cf_admin=""; cf_global=""; cf_ssh_key=""; cf_api=""; cf_ssh=""; cf_linger=""; cf_deny=""; cf_reload=""; cf_osacc=""; cf_viewer=""
ACC_PW=""; ADM_PW=""; GLB_PW=""
ssh_wanted=0; first_login=0
if [ "$upgrade" -eq 1 ]; then
  api="off"   # not used: an upgrade leaves the service and API as they are
  ssh="off"   # the upgrade works out Solo's own ssh from what the tree already has (ssh_upgrade_scope)
  old_commit="$(sed -n 's/^commit //p' "$HOME_DIR/.sdcore-install" | head -1)"
  mode_name="$(sed -n 's/^mode //p' "$HOME_DIR/.sdcore-install" | head -1)"
  # LSOLO 38: a tree installed before 6 Oct 2026 records "standalone" for what is now called unmanaged.
  case "$mode_name" in standalone|unmanaged) managed=0; mode_name="unmanaged" ;; managed) managed=1 ;; *) refuse "$HOME_DIR/.sdcore-install has no usable 'mode' line" ;; esac
  say
  say "SD Core for Linux Solo - upgrade"
  say "  tree        : $HOME_DIR ($mode_name, installed from ${old_commit:-an unknown commit})"
  [ -z "$pkg_pre" ] || say "  This package is the pre-release ${pkg_pre}, for testing."
  say "  source      : $src_desc"
  say "  kept        : the account and its data, all passwords, sd.conf, the audit trail, GLOBAL.BP.OUT, the deny list,"
  say "                the service and ssh settings"
  say "  replaced    : programs and system objects; a safety copy of the whole tree is made first"
  say "  running as  : $(id -un)"
  ask_os_access
  ask_viewer
  if [ "$assume_yes" -eq 0 ] && [ "$interactive" -eq 1 ]; then
    read -r -p "Continue? [Y/n] " a < /dev/tty; a="${a:-y}"
    case "$a" in y|Y|yes|YES) ;; *) refuse "cancelled by you; nothing was changed" ;; esac
  fi
fi
if [ "$upgrade" -eq 0 ]; then
# ---------------------------------------------------------------- the control file
if [ -n "$control_file" ]; then
  [ -r "$control_file" ] || refuse "cannot read the control file $control_file"
  in_install=0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; '[install]') in_install=1; continue ;; '['*) in_install=0; continue ;; esac
    [ "$in_install" -eq 1 ] || continue
    key="${line%%=*}"; val="${line#*=}"
    case "$key" in
      admin-password)  cf_admin="$val" ;;
      global-password) cf_global="$val" ;;
      deny-verbs)      cf_deny="$val" ;;
      ssh-public-key-file) cf_ssh_key="$val" ;;
      api)             cf_api="${val//[[:space:]]/}" ;;
      ssh)             cf_ssh="${val//[[:space:]]/}" ;;
      reload-data)     cf_reload="$val" ;;
      os-access)       cf_osacc="${val//[[:space:]]/}" ;;
      viewer)          cf_viewer="${val//[[:space:]]/}" ;;
      ssh-match)       warn "the control file's ssh-match is gone (LSOLO 29: Solo's ssh has its own port, 4251, and no longer uses the machine's sshd_config); ignored" ;;
      enable-linger)   cf_linger="$val" ;;
      *) warn "the control file has an item this installer does not know, ignored: $key" ;;
    esac
  done < "$control_file"
  # Ruling 34: verb names only (letters, digits, . $ _ - , and spaces); solo-stage.sh checks it again.
  case "$cf_deny" in
    *[!A-Za-z0-9.\$_,\ -]*) refuse "deny-verbs in the control file holds a character that cannot be in a verb name" ;;
  esac
  [ -z "$cf_ssh_key" ] || [ -n "$ssh_key" ] || ssh_key="$cf_ssh_key"
  # LSOLO 38: the file can make the API and ssh choices (a flag on the command line wins).
  case "$cf_api" in ""|off|local|open) ;; *) refuse "api in the control file must be off, local or open (got '$cf_api')" ;; esac
  case "$cf_ssh" in ""|off|local|open) ;; *) refuse "ssh in the control file must be off, local or open (got '$cf_ssh')" ;; esac
  [ -n "$api" ] || api="$cf_api"
  [ -n "$ssh" ] || ssh="$cf_ssh"
  case "$cf_reload" in ""|yes|no) ;; *) refuse "reload-data in the control file must be yes or no (got '$cf_reload')" ;; esac
  [ -n "$reload_ans" ] || reload_ans="$cf_reload"
  case "$cf_osacc" in ""|none|sh|os|both) ;; *) refuse "os-access in the control file must be none, sh, os or both (got '$cf_osacc')" ;; esac
  [ -n "$os_access" ] || os_access="$cf_osacc"
  case "$cf_viewer" in ""|none) ;; *[!a-z0-9._+-]*|.*) refuse "viewer in the control file must be none or the name of a reader: letters, digits and . _ + - (got '$cf_viewer')" ;; esac
  [ -n "$viewer" ] || viewer="$cf_viewer"
  if [ "$ssh" = "off" ] && [ -n "$ssh_key" ]; then refuse "an ssh public key needs ssh on: the install says ssh off and also gives a key (--ssh-key or the control file's ssh-public-key-file)"; fi
fi

# ---------------------------------------------------------------- questions
say
say "SD Core for Linux Solo - install"
say "  into        : $HOME_DIR"
[ -z "$pkg_pre" ] || say "  This package is the pre-release ${pkg_pre}, for testing."
say "  source      : $src_desc"
say "  running as  : $(id -un)"
say

# BEGIN linger
# linger_decide: is "loginctl enable-linger" run, so that SD (and its API and ssh) keeps running and reachable when nobody is signed in?
# 9 Nov 26 - the owner: "linux and windows solo both need to be set up so that SD is accessible remotely even if the user is not logged
# in at the console", then "Yes, on by default" (told that linger keeps SD and its open ports running while he is signed out).  So it is
# ON for every install, an unattended one included.  The order: --enable-linger / --no-linger (the command line wins), then the control
# file's enable-linger yes|no, then the question on a terminal (default yes), else on.  With --no-service there is no service to keep.
linger_decide() {
  case "$linger_cli" in
    yes) enable_linger=1; return 0 ;;
    no)  enable_linger=0; return 0 ;;
  esac
  case "$cf_linger" in
    yes) enable_linger=1; return 0 ;;
    no)  enable_linger=0; return 0 ;;
    "")  ;;
    *)   refuse "enable-linger in the control file must be yes or no (got '$cf_linger')" ;;
  esac
  enable_linger=1
  if [ "$no_service" -eq 0 ] && [ "$interactive" -eq 1 ]; then
    say
    say "So that SD stays reachable when nobody is signed in, 'loginctl enable-linger' keeps it running after you sign out."
    ask_yn "Keep SD running when you are signed out?" y || enable_linger=0
  fi
  return 0
}
# END linger

ask_yn() {   # ask_yn "question" default(y|n)  -> 0 yes, 1 no ; non-interactive: the default
  local q="$1" d="$2" a
  if [ "$interactive" -ne 1 ]; then [ "$d" = y ]; return; fi
  read -r -p "$q [$([ "$d" = y ] && echo Y/n || echo y/N)] " a < /dev/tty
  a="${a:-$d}"; case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# LSOLO 39 (owner, 6 Oct 2026: "the installer script should offer to reload the saved data and config";
# "you and windows should handle removal and reinstall the same way"): the install directory holds what
# deletesdsolo.sh --keep-data left there.  On a terminal the user is asked; the answer can be given as
# --reload-data / --start-clean or the control file's reload-data=yes|no; with no terminal and no answer the
# data is reloaded (it is kept either way, and an unattended install was given its passwords).
if [ "$kept_tree" -eq 1 ]; then
  say "Saved data was found: $HOME_DIR"
  say "  (the account's files$([ -f "$HOME_DIR/sd.conf" ] && echo " and sd.conf")$([ -d "$HOME_DIR/newvoc.mods" ] && echo " and your local VOC modifications (newvoc.mods)"), left here by deletesdsolo.sh$(sed -n 's/^commit \(.......\).*/ from commit \1/p' "$HOME_DIR/.sdcore-kept" | head -1)$(sed -n 's/^kept \([0-9-]*\)T.*/ on \1/p' "$HOME_DIR/.sdcore-kept" | head -1))"
  say "  Passwords are not kept: this install asks for new ones."
  if [ -z "$reload_ans" ]; then
    if [ "$interactive" -eq 1 ]; then
      if ask_yn "Reload your saved data and configuration into this new install?" y; then reload_ans="yes"; else reload_ans="no"; fi
    else
      reload_ans="yes"
      say "  (no terminal and no --reload-data or --start-clean: reloading it)"
    fi
  fi
  say
fi

# 20 Oct 26, the OS switch: the shell and OS access question (see ask_os_access above); OFF unless the answer says otherwise.
ask_os_access
# 23 Oct 26, Solo carry 14: the PDF reader question (see ask_viewer above); NOTHING is allowed unless the answer says so.
ask_viewer

# passwords, in the owner's order (ruling 30): account, administrator, then - if there is one - global
get_password() {   # get_password VAR "what" "from-file" "from-control"
  local __var="$1" what="$2" file="$3" cf="$4" p1="" p2="" tries=0
  if [ -n "$file" ]; then
    [ -r "$file" ] || refuse "cannot read the $what password file $file"
    p1="$(head -1 "$file" | tr -d '\r')"
    pw_ok "$p1" || refuse "the $what password in $file does not meet the rule: $PWRULE"
    printf -v "$__var" '%s' "$p1"; return
  fi
  if [ -n "$cf" ]; then
    pw_ok "$cf" || refuse "the $what password in the control file does not meet the rule: $PWRULE"
    printf -v "$__var" '%s' "$cf"; return
  fi
  [ "$interactive" -eq 1 ] || refuse "no $what password was given and there is no terminal to ask on (use --$what-password-file)"
  while [ "$tries" -lt 3 ]; do
    tries=$((tries+1))
    read_password "Choose the $what password: " p1
    if ! pw_ok "$p1"; then warn "The password must be $PWRULE."; continue; fi
    read_password "Confirm the $what password: " p2
    if [ "$p1" != "$p2" ]; then warn "The two did not match."; continue; fi
    printf -v "$__var" '%s' "$p1"; return
  done
  refuse "no acceptable $what password after three tries"
}

# LSOLO 38 (owner, 6 Oct 2026): the global password is optional.  It comes from --global-password-file or
# the control file when either gives one.  With a control file it comes from the file ALONE (agreed with
# Windows Solo, 6 Oct): blank or absent is none and nothing is asked, but it is said out loud, because a
# typo or an old file would otherwise make an unmanaged computer without a word.  Without a control file it
# is asked, last, and a blank answer means no SD Core server manages this computer; with nothing given
# and nobody to ask, there is none.
get_global() {
  local p1="" p2="" tries=0
  if [ -n "$glb_file$cf_global" ]; then get_password GLB_PW global "$glb_file" "$cf_global"; return; fi
  if [ -n "$control_file" ]; then
    warn "The control file gives no global password, so this computer will NOT be managed by an SD Core server."
    return 0
  fi
  [ "$interactive" -eq 1 ] || return 0
  say
  say "A GLOBAL password is for a computer that an SD Core server manages: the server uses it to manage this one."
  say "If no SD Core server manages this computer, leave it blank."
  while [ "$tries" -lt 3 ]; do
    tries=$((tries+1))
    read_password "Global password (leave blank if no SD Core server manages this computer): " p1
    [ -n "$p1" ] || return 0
    if ! pw_ok "$p1"; then warn "The password must be $PWRULE.  (Leave it blank for none.)"; continue; fi
    read_password "Confirm the global password: " p2
    if [ "$p1" != "$p2" ]; then warn "The two did not match."; continue; fi
    GLB_PW="$p1"; return 0
  done
  refuse "no acceptable global password after three tries (leave it blank to install without one)"
}

say "Passwords. Every SD session asks for the ACCOUNT password; the ADMINISTRATOR password unlocks"
say "SD's administrator commands (ADMIN).  A GLOBAL password is asked for last, and is optional."
say
ACC_PW=""; ADM_PW=""; GLB_PW=""
# LSOLO 14 (Windows Solo SOLO 18, owner 27 Sep 2026): a control file never holds the
# account password.  With one and no --account-password-file, the installer does not
# ask for it either: the user chooses it at the console on first login, which is what
# lets one control file initialise several computers.  --account-password-file still
# sets it at install time, as before.
# LSOLO 38: that is a feature of a MANAGED computer (the first login is checked against
# the global password), so it applies only when a global password is also given, by the
# file or by --global-password-file.  Without one the account password is asked as usual.
first_login=0
if [ -n "$control_file" ] && [ -z "$acc_file" ] && [ -n "$glb_file$cf_global" ]; then
  first_login=1
  say "The account password is not asked for: whoever first starts SD at this computer's keyboard chooses it."
else
  get_password ACC_PW account "$acc_file" ""
fi
get_password ADM_PW administrator "$adm_file" "$cf_admin"
get_global
managed=0; [ -z "$GLB_PW" ] || managed=1
mode_name="unmanaged"; [ "$managed" -eq 1 ] && mode_name="managed"
if [ "$managed" -eq 1 ]; then
  [ "$first_login" -eq 1 ] || [ "$GLB_PW" != "$ACC_PW" ] || refuse "the global password must differ from the account password (ruling 19)"
  [ "$GLB_PW" != "$ADM_PW" ] || refuse "the global password must differ from the administrator password"
fi

# the API and ssh: the user's choice in every install, with or without a global password
# (LSOLO 38 - they used to be forced open for a managed computer, ruling 22)
if [ -z "$api" ]; then
  if [ "$interactive" -eq 1 ]; then
    say
    say "The API lets programs on other computers (or this one) connect to SD over TLS 1.3 with your account"
    say "password.  off = no listener; local = this computer only; open = reachable from the network."
    [ "$managed" -eq 0 ] || say "An SD Core server manages this computer through the API: it can reach this computer only if the API is open."
    read -r -p "API listener [off/local/open] (default off): " api < /dev/tty
    api="${api:-off}"
    case "$api" in off|local|open) ;; *) refuse "the API answer must be off, local or open (got '$api')" ;; esac
  else
    api="off"
  fi
fi
# 02 Oct 26 (owner: "Match Windows as built"): ssh is ON BY DEFAULT, this computer only, as Windows Solo's is
# (its own sshd is set up wherever OpenSSH is found; only reaching it from other computers is a box,
# unchecked).  The API stays OFF by default on both.  "off" is still a choice.
# 02 Oct 26 (owner: "match the windows solo behavior", after a first version that installed the ssh server only
# when asked): Windows Solo OFFERS "Install the OpenSSH server" when no sshd is there and ticks it by default, so
# here too the default installs the ssh server package if it is missing, and --ssh off (or an answer of off) is
# the way to decline.  See ssh_default_choice for the one Linux difference, --skip-packages.
have_sshd=0; if command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ]; then have_sshd=1; fi
ssh_default="$(ssh_default_choice "" "$ssh_key" "$have_sshd" "$skip_pkgs")"
if [ -z "$ssh" ]; then
  if [ -n "$ssh_key" ]; then
    ssh="$ssh_default"
  elif [ "$interactive" -eq 1 ]; then
    say
    say "ssh straight into sd uses Solo's own listener on port $ssh_port (your Linux account and password, or a key; the machine's own ssh on"
    say "port 22 is not used).  off = none; local = this computer only; open = reachable from the network."
    if [ "$have_sshd" -eq 0 ] && [ "$skip_pkgs" -eq 0 ]; then
      say "The ssh server program (sshd) is not installed here: local or open INSTALLS the openssh-server package with sudo (on Debian"
      say "and Ubuntu that package also starts the computer's own ssh server on port 22).  Answer off to leave it out."
    elif [ "$have_sshd" -eq 0 ]; then
      say "The ssh server program (sshd) is not installed here and --skip-packages does not install it, so the default is off."
    fi
    read -r -p "ssh listener [off/local/open] (default $ssh_default): " ssh < /dev/tty
    ssh="${ssh:-$ssh_default}"
    case "$ssh" in off|local|open) ;; *) refuse "the ssh answer must be off, local or open (got '$ssh')" ;; esac
  else
    ssh="$ssh_default"
    if [ "$ssh" = "off" ]; then
      warn "no ssh server program (sshd) here and --skip-packages: Solo's ssh is OFF.  Install the ssh server package, then: bash <tree>/tools/solo-ssh.sh setup <tree> && bash <tree>/tools/solo-service.sh ssh <tree> local"
    fi
  fi
fi
if [ "$managed" -eq 1 ] && { [ "$api" != "open" ] || [ "$ssh" != "open" ]; }; then
  warn "This computer has a global password, so an SD Core server is expected to manage it, but the API is $api and ssh is $ssh: the server reaches it only through what is open to the network."
fi
ssh_wanted=0; [ "$ssh" = "off" ] || ssh_wanted=1
# Asking for ssh installs the ssh server package; --skip-packages forbids that, so say so now, not after the build.
if [ "$ssh_wanted" -eq 1 ] && [ "$skip_pkgs" -eq 1 ] && ! { command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ]; }; then
  refuse "ssh needs the ssh server program (sshd), which is not installed here, and --skip-packages does not install it: install the openssh-server package first, or leave ssh off (--ssh off)"
fi
if [ "$ssh_wanted" -eq 1 ] && [ -z "$ssh_key" ] && [ "$interactive" -eq 1 ]; then
  read -r -p "Path to a public key to add for ssh into sd (blank to skip): " ssh_key < /dev/tty
fi
if [ -n "$ssh_key" ]; then
  [ -r "$ssh_key" ] || refuse "cannot read the ssh public key $ssh_key"
fi
linger_decide

# ---------------------------------------------------------------- confirmation
say
say "Ready to install:"
if [ "$kept_tree" -eq 1 ]; then
  if [ "$reload_ans" = "yes" ]; then
    say "  reload        : your saved data$([ -f "$HOME_DIR/sd.conf" ] && echo " and configuration") from $HOME_DIR (the folder is kept aside as $HOME_DIR.kept-<date and time> until you delete it)"
  else
    say "  start clean   : your saved data in $HOME_DIR is moved aside to $HOME_DIR.kept-<date and time>, not deleted, and NOT reloaded"
  fi
fi
say "  global pw     : $([ "$managed" -eq 1 ] && echo "set - an SD Core server is expected to manage this computer" || echo "none - no SD Core server manages this computer")"
say "  account pw    : $([ "$first_login" -eq 1 ] && echo "chosen at first login, at this computer's keyboard" || echo "set now")"
say "  API           : $api$([ "$api" != off ] && echo " (port $api_port)")"
say "  ssh into sd   : $ssh$([ "$ssh" != off ] && echo " (port $ssh_port, Linux password or key)")$([ -n "$ssh_key" ] && echo ", key $ssh_key")"
say "  service       : $([ "$no_service" -eq 1 ] && echo "not installed" || echo "systemd user service$([ "$enable_linger" -eq 1 ] && echo ", linger on: SD keeps running when nobody is signed in" || echo ", linger off: SD stops when you sign out")")"
say "  packages      : $([ "$skip_pkgs" -eq 1 ] && echo "not installed (checked)" || echo "installed with sudo")"
if [ "$assume_yes" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  ask_yn "Continue?" y || refuse "cancelled by you; nothing was changed"
fi
fi   # end of "a first install asks its questions"

# ---------------------------------------------------------------- scratch space
WORK="$(mktemp -d)"; chmod 700 "$WORK"
cleanup() {
  rm -rf "$WORK"
  rm -rf "$CLONE_DIR"
}
trap cleanup EXIT
umask 077

# ---------------------------------------------------------------- packages
# LSOLO 33 (owner, 4 Oct 2026): the pacman and zypper branches are gone.
# 11 Nov 26 - DEBIAN AND UBUNTU ONLY (owner, 11 Nov 2026: "Yes, Debian and Ubuntu only", carrying SD Core's
#   S.105 of 2 Nov 2026).  The dnf branch is gone, and detect_distro (above, beside net_preflight) has already
#   refused every other distribution before the banner and the first sudo, so the packages are apt-get's alone.
install_packages() {
  local ssh_pkg=0; [ "$ssh_wanted" -eq 1 ] && ssh_pkg=1
  say "Debian or Ubuntu based: apt-get"
  # "openssl" (the command) as well as the headers: a minimal system may ship without it.
  local pk="git build-essential micro lynx libsodium-dev libssl-dev openssl python3-dev"
  [ "$ssh_pkg" -eq 1 ] && pk="$pk openssh-server"
  # shellcheck disable=SC2086
  sudo apt-get -y install $pk || fail "apt-get"
  sudo apt-get -y --ignore-missing install libcrypt-dev || true
  install_gpm
}
# 11 Nov 26 (S.117; SD Core's installer, S.94): gpm, the console mouse daemon, so that the full-screen pages have a mouse
# on a bare Linux console (SD talks to /dev/gpmctl itself).  It has a call of its own after the required packages, and
# ITS FAILURE IS A WARNING, NOT THE END OF THE INSTALL (SD Core's owner, 7 Nov 2026: in a container "gpm couldn't be
# installed and the installation failed ... a gpm installation failure doesn't kill the install").  SD runs without it:
# there is then no mouse on a bare console.  The installer neither enables nor starts gpm.service; the package does
# what the distribution's package does.
install_gpm() {
  if ! sudo apt-get -y install gpm; then
    sudo apt-get -y remove gpm > /dev/null 2>&1 || true
    warn "gpm could not be installed; the install goes on without a mouse on the Linux console.  To add it later:  sudo apt-get install gpm"
  fi
}
say
if [ "$skip_pkgs" -eq 1 ]; then
  say "Skipping package installation (--skip-packages); checking the tools instead."
else
  say "Installing the build packages (sudo)."
  install_packages
fi
for t in git make gcc python3 python3-config openssl; do
  command -v "$t" >/dev/null || refuse "the tool '$t' is not installed (install the build packages, or run without --skip-packages)"
done
python3-config --includes >/dev/null 2>&1 || refuse "the Python development headers are missing (python3-dev)"

# ---------------------------------------------------------------- download and build
say
# 10 Oct 26  Said "(main branch)" whatever REPO_BRANCH was; a release zip's copy is pinned to a tag.
# 12 Nov 26 dm - S.218: from a release package the source is copied (the package itself is never written), and the commit is the one SDCORE-RELEASE
#            names, checked against SHA256SUMS above; the package has no .git.
if [ -n "$pkg_source" ]; then
  say "Copying the source ($REPO_BRANCH) from the package to $CLONE_DIR"
  rm -rf "$CLONE_DIR"
  mkdir -p "$CLONE_DIR"
  cp -a "$pkg_source/." "$CLONE_DIR/" || fail "copying the package's source to $CLONE_DIR"
  COMMIT="$pkg_commit"
else
  say "Downloading the source ($REPO_BRANCH) to $CLONE_DIR"
  git ls-remote -q "$REPO_URL" >/dev/null 2>&1 || refuse "cannot reach $REPO_URL - check the network"
  rm -rf "$CLONE_DIR"
  git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$CLONE_DIR" 2>&1 | tail -2
  COMMIT="$(git -C "$CLONE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
fi
say "Installing commit $COMMIT"
SRC="$CLONE_DIR/sdb_ai/sd64"
[ -d "$SRC" ] || fail "the download has no sdb_ai/sd64 - the repository layout changed"

echo '#include <Python.h>' > "$SRC/gplsrc/sdext_python_inc.h"
say "Building (this takes a minute)."
( cd "$SRC" && make -B >"$WORK/make.log" 2>&1 ) || { tail -20 "$WORK/make.log"; fail "make"; }
[ -x "$SRC/bin/sd-solo" ] || fail "the build reported success but bin/sd-solo is missing"
say "Build complete."

# ---------------------------------------------------------------- stage and bootstrap
say
umask 077
had_service=0
if [ "$upgrade" -eq 1 ]; then
  say "Upgrading $HOME_DIR and running the bootstrap over it."
  # The service holds the shared-memory segment and the daemon; stop it (and the API
  # socket that would start it again) before the tree is touched, and start it again
  # afterwards whether the upgrade worked or was put back.
  if systemctl --user is-active sd-solo.service >/dev/null 2>&1 || [ -f "$HOME/.config/systemd/user/sd-solo.service" ]; then
    had_service=1
    # 25 Oct 26 - the clean-up daemon's own unit first (an install made since this release has one), so that it is not restarted while SD is being taken down
    systemctl --user stop sd-solo-lnxd.service >/dev/null 2>&1 || true
    systemctl --user stop sd-solo-ssh.socket sd-solo-api.socket sd-solo.service >/dev/null 2>&1 || true
  fi
  if ! bash "$SRC/gplbld/solo-stage.sh" --upgrade --os-access "${os_access:-none}" --viewer "${viewer:-none}" "$HOME_DIR" > "$WORK/stage.log" 2>&1; then
    tail -25 "$WORK/stage.log"
    [ "$had_service" -eq 0 ] || systemctl --user start sd-solo.service sd-solo-api.socket sd-solo-ssh.socket >/dev/null 2>&1 || true
    fail "the upgrade (full log: $WORK/stage.log - removed when this script ends). The tree was put back as it was; if the log above does not say so, do not use $HOME_DIR: your data is in the safety copy $HOME_DIR.before-upgrade-*"
  fi
  grep -qx "solo-stage: UPGRADE COMPLETE in $HOME_DIR" <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'solo-stage: UPGRADE COMPLETE'"
  os_state="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^solo-stage: OS access: //p' | tail -1)"
  [ -n "$os_state" ] || fail "the stage log has no 'solo-stage: OS access:' line (SET.OS.ACCESS did not report)"
  viewer_state="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^solo-stage: PDF reader: //p' | tail -1)"
  upgrade_backup="$(cat "$HOME_DIR/.last-upgrade-backup" 2>/dev/null || true)"
  rm -f "$HOME_DIR/.last-upgrade-backup"
  { printf 'commit %s\n' "$COMMIT"; printf 'date %s\n' "$(date -Is)"; printf 'mode %s\n' "$mode_name"; \
    printf 'upgraded-from %s\n' "${old_commit:-unknown}"; printf 'origin %s\n' "$REPO_URL"; } > "$HOME_DIR/.sdcore-install"
  chmod 600 "$HOME_DIR/.sdcore-install"
else
# LSOLO 39: data a previous uninstall left in the install directory is moved aside whole, so the new tree can be
# made there, and the stage copies it back in when the answer was yes.  It is never deleted: the aside folder
# stays until the user removes it (and if this install fails, fail() says where it is).
if [ "$kept_tree" -eq 1 ]; then
  kept_aside="$HOME_DIR.kept-$(date +%Y%m%d-%H%M%S)"
  mv "$HOME_DIR" "$kept_aside" || fail "moving your saved data aside to $kept_aside"
  say "Your saved data is moved aside to $kept_aside."
  [ "$reload_ans" != "yes" ] || reload_dir="$kept_aside"
fi
say "Installing into $HOME_DIR and running the bootstrap."
st_args=()
if [ "$first_login" -eq 0 ]; then printf '%s\n' "$ACC_PW" > "$WORK/acc.pw"; st_args+=(--account-password-file "$WORK/acc.pw"); fi
printf '%s\n' "$ADM_PW" > "$WORK/adm.pw"; st_args+=(--admin-password-file "$WORK/adm.pw")
if [ "$managed" -eq 1 ]; then printf '%s\n' "$GLB_PW" > "$WORK/glb.pw"; st_args+=(--global-password-file "$WORK/glb.pw"); fi
if [ -n "$cf_deny" ]; then st_args+=(--deny-verbs "$cf_deny"); fi
if [ -n "$reload_dir" ]; then st_args+=(--reload-data "$reload_dir"); fi
st_args+=(--os-access "${os_access:-none}" --viewer "${viewer:-none}")
bash "$SRC/gplbld/solo-stage.sh" "${st_args[@]}" "$HOME_DIR" > "$WORK/stage.log" 2>&1 \
  || { tail -25 "$WORK/stage.log"; fail "the bootstrap (full log: $WORK/stage.log - removed when this script ends; re-run the failing step by hand from $SRC/gplbld/solo-stage.sh)"; }
rm -f "$WORK/acc.pw" "$WORK/adm.pw" "$WORK/glb.pw"
os_state="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^solo-stage: OS access: //p' | tail -1)"
[ -n "$os_state" ] || fail "the stage log has no 'solo-stage: OS access:' line (SET.OS.ACCESS did not report)"
viewer_state="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^solo-stage: PDF reader: //p' | tail -1)"
if [ "$first_login" -eq 0 ]; then
  grep -qx 'SOLO PASSWORD SET ACCOUNT' <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'SOLO PASSWORD SET ACCOUNT'"
else
  grep -qx 'SOLO PASSWORD SET GLOBAL' <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'SOLO PASSWORD SET GLOBAL' (a first-login install is managed, so the global password must be set)"
  [ ! -e "$HOME_DIR/\$cred/sduser" ] || fail "\$cred/sduser exists on a first-login install"
fi
[ -f "$HOME_DIR/user_accounts/sduser/voc/%0" ] || [ -d "$HOME_DIR/user_accounts/sduser" ] || fail "the account directory is missing"
reload_note=""; mods_note=""
if [ -n "$reload_dir" ]; then
  # LSOLO 39: anchored on the stage's own success line, whose config part says what happened to sd.conf.
  reload_note="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^SOLO RELOAD DONE data=reloaded config=//p' | head -1)"
  [ -n "$reload_note" ] || fail "the stage log has no 'SOLO RELOAD DONE data=reloaded' (the saved data in $reload_dir was NOT reloaded)"
  # 24 Oct 26 (PAL-36): a newvoc.mods directory kept beside the account is put back by the stage before the VOC is refreshed; it says so on a line of its own.
  # When the kept folder HAS one, a stage that did not put it back is a failure: the administrator's VOC additions would be gone without a word.
  mods_note="$(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log" | sed -n 's/^solo-stage: newvoc.mods: //p' | tail -1)"
  if [ -d "$reload_dir/newvoc.mods" ]; then
    [ "$mods_note" = "reloaded" ] || fail "the kept folder has a newvoc.mods but the stage log has no 'solo-stage: newvoc.mods: reloaded' (it was NOT put back; it is still in $reload_dir)"
  fi
fi

# what was installed
{ printf 'commit %s\n' "$COMMIT"; printf 'date %s\n' "$(date -Is)"; printf 'mode %s\n' "$mode_name"; printf 'origin %s\n' "$REPO_URL"; } > "$HOME_DIR/.sdcore-install"   # S.218: origin (a URL, or package:<folder>)
chmod 600 "$HOME_DIR/.sdcore-install"
fi

# ---------------------------------------------------------------- documentation that travels with the install (S.216)
# 11 Nov 26 dm  S.216, gaps 26-28 of the Core-Solo parity report (SD Core's installsdcore.sh AGENTPACK, DOCS-CORPUS, CHANGES-DOC and MANUALS-PDF blocks).  They run here, after the
#            stage has laid the tree out and in the fresh install and the upgrade alike, and BEFORE the daemon the stage left running is stopped below (the manuals go in through
#            SD's own docs.install).  Solo has no shared account and no sdsys user, so every destination is in the install directory: agent-pack/, docs/user and pdf/ (the
#            directories gpl.bp/tk_aidocs and the pdf verb read).  NONE OF THEM STOPS THE INSTALL: no pack, a half pack, a pack for another version, no network to the
#            documentation, no files beside the installer, a failed copy each print a note or a warning and go on.  The files are 644 and the directories 755 (the install directory
#            itself is the user's, 700 from umask 077); nothing is group- or other-writable.  test-install-agentpack.sh, test-install-aidocs.sh, test-install-changesdoc.sh and
#            test-install-manuals.sh (gplbld) run these blocks under the installer's set options.
#
# THE AI GUIDE AND KNOWLEDGE PACK: sdb_ai/sd64/agent-pack/{guide,pack} of the download, to <home>/agent-pack.  TEXT ONLY, for the person to copy to the machine where an AI agent
#            runs; nothing here is read by SD itself.  The skill, the templates, the recipe and the generator are NOT installed.  Skipped with a note when the download holds no
#            complete pack, or when its manifest is for another version than the one installed (a pack that describes version X on a machine running Y is worse than none).  A
#            missing revstamp.h or manifest must not stop the install under set -e: hence the "|| x=''" on each read.  An upgrade replaces the old pack whole.
# AGENTPACK-BEGIN
if [ -f "$SRC/agent-pack/guide/sd-basic-guide.md" ] && [ -f "$SRC/agent-pack/pack/manifest.json" ] && [ -f "$SRC/agent-pack/pack/core.md" ]; then
    pack_stamp=$(sed -n '/"rev_stamp"/{s/^[^:]*: *"\([^"]*\)".*/\1/p;q}' "$SRC/agent-pack/pack/manifest.json") || pack_stamp=""
    tree_stamp=$(sed -n '/^\$define SD\.REV\.STAMP/{s/^[^"]*"\([^"]*\)".*/\1/p;q}' "$HOME_DIR/gpl.bp/revstamp.h" 2>/dev/null) || tree_stamp=""
    if [ -n "$pack_stamp" ] && [ "$pack_stamp" = "$tree_stamp" ]; then
        rm -rf "$HOME_DIR/agent-pack"
        if mkdir -p "$HOME_DIR/agent-pack" && cp -R "$SRC/agent-pack/guide" "$SRC/agent-pack/pack" "$HOME_DIR/agent-pack/"; then
            say "Installed the AI guide and knowledge pack (version ${pack_stamp}): $HOME_DIR/agent-pack"
        else
            rm -rf "$HOME_DIR/agent-pack"
            warn "The AI guide and knowledge pack could not be copied into $HOME_DIR/agent-pack, so none was installed."
        fi
    else
        say "Note: the AI knowledge pack in the download is for version '${pack_stamp:-?}' and this is '${tree_stamp:-?}', so it was not installed."
    fi
else
    say "Note: the download holds no complete AI guide and knowledge pack (agent-pack/), so none was installed."
fi
# AGENTPACK-END
# The pack is text, not programs: files 644, directories 755 (the copy above was made under umask 077).  Nobody but the user can write it, and that is the point: an agent
#            is told to trust this text, so a file anyone else could edit would be a way to plant instructions for the user's agent.
# AGENTPACK-MODE-BEGIN
if [ -d "$HOME_DIR/agent-pack" ]; then
    find "$HOME_DIR/agent-pack" -type d -exec chmod 755 {} +
    find "$HOME_DIR/agent-pack" -type f -exec chmod 644 {} +
fi
# AGENTPACK-MODE-END
#
# THE DOCUMENTATION THE AI LINE DRAWS ON: the markdown of the User document, from the documentation repository (branch REPO_BRANCH), to <home>/docs/user.  gpl.bp/tk_aidocs
#            (the same program as SD Core's) picks a few sections of them for a request and the preview shows them before anything is sent; it reads docs/user (and docs/admin,
#            which Solo's documentation has no pages for, so there is none and it is left out).  SKIPPED WITH A NOTE, NEVER AN ERROR: no network to the documentation, no
#            clone, a clone without User/markdown, no mktemp or a failed copy leaves the AI line working as it did, without passages; an older install's docs are replaced only
#            when the new ones are complete.
#            12 Nov 26 dm - S.218: a release package carries User/markdown in source/docs; only without a package is it cloned.
# DOCS-CORPUS-BEGIN
docs_tmp=$(mktemp -d 2>/dev/null) || docs_tmp=""
docs_from=""
if [ -n "$pkg_source" ] && [ -d "$pkg_source/docs/User/markdown" ]; then
    docs_from="$pkg_source/docs"
elif [ -z "$pkg_source" ] && [ -n "$docs_tmp" ] && GIT_TERMINAL_PROMPT=0 git clone --quiet --branch "$REPO_BRANCH" --depth 1 "$DOCS_URL" "$docs_tmp/docs" >/dev/null 2>&1 \
   && [ -d "$docs_tmp/docs/User/markdown" ]; then
    docs_from="$docs_tmp/docs"
fi
if [ -n "$docs_from" ]; then
    rm -rf "$HOME_DIR/docs"
    if mkdir -p "$HOME_DIR/docs/user" && cp "$docs_from"/User/markdown/*.md "$HOME_DIR/docs/user/"; then
        chmod 755 "$HOME_DIR/docs" "$HOME_DIR/docs/user"
        find "$HOME_DIR/docs/user" -type f -exec chmod 644 {} +
        say "Installed the documentation the AI line draws on: $HOME_DIR/docs"
    else
        rm -rf "$HOME_DIR/docs"
        warn "The documentation for the AI line could not be copied into $HOME_DIR/docs, so it will answer without passages of it."
    fi
elif [ -n "$pkg_source" ]; then
    say "Note: the package holds no documentation for the AI line (source/docs), so it will answer without passages of it."
else
    say "Note: the documentation could not be fetched from ${DOCS_URL}, so the AI line will answer without passages of it."
fi
if [ -n "$docs_tmp" ]; then rm -rf "$docs_tmp"; fi
# DOCS-CORPUS-END
#
# THE CHANGES DOCUMENT TRAVELS WITH THE INSTALLER AND IS COPIED INTO THE PDF DIRECTORY (SD Core's CHANGES-DOC block; owner, 24 Oct 2026: "included with the installer as an
#            additional document and upon installation also copied into the 'shared' directory" - Solo has no shared account, so the directory is <home>/pdf, the one the pdf
#            verb reads).  A release package holds, beside this script, the document in three forms named sd-core-solo-for-linux-<version>-changes.pdf / .html / .md (lower
#            case, the names docs.install takes).  Each regular file of that name is put in <home>/pdf, mode 644.  A file that is a link, or whose name is not plain lower case,
#            is left.  Nothing is needed for the install to go on: no files (a clone from GitHub has none), no pdf directory, a failed copy each print a note.
# CHANGES-DOC-BEGIN
changes_copied=0
changes_seen=0
if [ -n "$installer_dir" ] && [ -d "$HOME_DIR/pdf" ]; then
    for changes_f in "$installer_dir"/sd-core-solo-for-linux-*-changes.pdf "$installer_dir"/sd-core-solo-for-linux-*-changes.html "$installer_dir"/sd-core-solo-for-linux-*-changes.md; do
        [ -f "$changes_f" ] && [ ! -L "$changes_f" ] || continue
        changes_b=$(basename "$changes_f")
        # docs.install takes only a name of a-z 0-9 dot dash underscore, not starting with a dot, up to 80 characters
        if ! [[ "$changes_b" =~ ^[a-z0-9][a-z0-9._-]{0,79}$ ]]; then
            say "Note: ${changes_b} was not copied: the name must be lower case letters, digits and . _ - (rename it and run:  docs.install <directory>)."
            continue
        fi
        changes_seen=$((changes_seen+1))
        if install -m 644 "$changes_f" "$HOME_DIR/pdf/${changes_b}"; then
            changes_copied=$((changes_copied+1))
        else
            warn "WARNING: ${changes_b} was not copied into $HOME_DIR/pdf."
        fi
    done
    if [ "$changes_copied" -gt 0 ]; then
        say "Copied the changes document (${changes_copied} files) into:  $HOME_DIR/pdf"
    elif [ "$changes_seen" -gt 0 ]; then
        say "The changes document could not be copied into $HOME_DIR/pdf (see the warnings above)."
    else
        say "No changes document beside the installer, so none was copied."
    fi
else
    say "No changes document was copied (not run from a release package, or no pdf directory)."
fi
# CHANGES-DOC-END
#
# THE DOCUMENTATION PDFS TRAVEL WITH THE INSTALLER TOO (SD Core's MANUALS-PDF block; owner, 3 Nov 2026: "Yes, installer copies them").  A release package holds, beside this
#            script, a folder pdf/ with the per-chapter PDFs of the documentation (the names the help pages' Documentation buttons open).  They are put in <home>/pdf by SD's own
#            docs.install, which judges every file (a lower case plain name, contents beginning %PDF-, a regular file), writes the audit line and makes the copies 644.  The verb
#            is run through the internal door, which is admitted only against a fresh marker file (ruling 13), written here immediately before the one session and removed
#            after it, as the stage script does for each of its steps; the stage's daemon is still running.  The result is judged file by file on <home>/pdf, not on sd's exit
#            code.  Nothing here stops the install: no folder (a clone from GitHub has none), no pdf directory or a refusal each print a note or a warning that says what to run.
# MANUALS-PDF-BEGIN
manuals_n=0
manuals_ok=0
if [ -n "$installer_dir" ] && [ -d "$installer_dir/pdf" ] && [ ! -L "$installer_dir/pdf" ]; then
    for manuals_f in "$installer_dir"/pdf/*.pdf; do
        if [ -f "$manuals_f" ] && [ ! -L "$manuals_f" ]; then manuals_n=$((manuals_n+1)); fi
    done
fi
if [ "$manuals_n" -eq 0 ]; then
    say "No documentation PDFs beside the installer (the pdf folder of a release package), so none were installed."
    say "  In an administrator session:  docs.install <directory of PDFs>"
elif [ -d "$HOME_DIR/pdf" ]; then
    printf 'installsdsolo pid=%s %s\n' "$$" "$(date -Is)" > "$HOME_DIR/\$internal"
    "$HOME_DIR/bin/sd-solo" -internal docs.install "$installer_dir/pdf" < /dev/null || true
    rm -f "$HOME_DIR/\$internal"
    for manuals_f in "$installer_dir"/pdf/*.pdf; do
        [ -f "$manuals_f" ] && [ ! -L "$manuals_f" ] || continue
        if cmp -s "$manuals_f" "$HOME_DIR/pdf/$(basename "$manuals_f")"; then
            manuals_ok=$((manuals_ok+1))
        fi
    done
    if [ "$manuals_ok" -eq "$manuals_n" ]; then
        say "Installed the documentation PDFs (${manuals_ok}) into:  $HOME_DIR/pdf"
    else
        warn "WARNING: ${manuals_ok} of ${manuals_n} documentation PDFs were installed (docs.install says why above)."
        say "  In an administrator session:  docs.install ${installer_dir}/pdf"
    fi
else
    say "The documentation PDFs were not installed: there is no pdf directory in $HOME_DIR."
fi
# MANUALS-PDF-END

# The stage leaves its own daemon running; the service takes over below.
"$HOME_DIR/bin/sd-solo" -stop >/dev/null 2>&1 || true

# ---------------------------------------------------------------- the command names
# 02 Oct 26 (owner, 1 Oct 2026, relayed in Windows' mails 2026-10-02T2400 and T2445):
#   sd-solo  always starts THIS SD Core Solo: a link to <tree>/bin/sd-solo;
#   sd       is the multi-user SD Core's own name and is never made here.  An EARLIER release
#            made ~/.local/bin/sd as a link to <tree>/bin/sd or as a launcher; an upgrade removes
#            it when it is ours (a link to this tree's old bin/sd, or a file carrying the
#            launcher's marker line) and leaves any other file called sd alone.
# The function between the markers is run by gplbld/test-launcher-units.py, which cuts it
# out of this file by those marker lines: keep the lines, and keep the code between them
# free of anything that needs the rest of the installer except warn() and $HOME.
# BEGIN command_names
install_command_names() {   # install_command_names TREE
  local tree="$1" bindir="$HOME/.local/bin" old
  mkdir -p "$bindir"
  if [ -e "$bindir/sd-solo" ] && [ ! -L "$bindir/sd-solo" ]; then
    warn "$bindir/sd-solo exists and is not a link; left alone (run SD Core Solo as $tree/bin/sd-solo)"
  else
    ln -sfn "$tree/bin/sd-solo" "$bindir/sd-solo"
  fi
  old="$bindir/sd"
  if [ -L "$old" ]; then
    if [ "$(readlink "$old")" = "$tree/bin/sd" ]; then rm -f "$old"; printf 'removed the old %s (a link to %s)\n' "$old" "$tree/bin/sd"; fi
  elif [ -f "$old" ] && grep -qF 'SD Core for Linux Solo launcher.' "$old" 2>/dev/null; then
    rm -f "$old"; printf 'removed the old %s (this product'"'"'s launcher)\n' "$old"
  fi   # anything else called sd is not this product's: left alone, and not complained about
}
# END command_names
install_command_names "$HOME_DIR"

# THE UPGRADE OF A TREE INSTALLED BEFORE THE RENAME.  The server's file name changed, so three
# places that named it by file name move too (Windows' cycle caught the same gap: a stop by
# the new name stops nothing on an old install).  Each is a no-op on a tree installed since.
# The function between the markers is run by gplbld/test-soloexe-units.py (it needs say(), warn()
# and fail(), and nothing else of the installer): keep the lines, and keep its arguments.
# BEGIN upgrade_rename
migrate_server_name() {   # migrate_server_name HOME_DIR UNITDIR AUTHORIZED_KEYS DROPIN
  local home_dir="$1" unitdir="$2" ak="$3" dropin="$4" esc u oldf aktmp
  # 1. the systemd user units: ExecStart=<tree>/bin/sd -start, ExecStop=..., ExecStart=... -n -q
  esc="$(printf '%s' "$home_dir" | sed 's/[][\.*^$#&/]/\\&/g')"
  for u in "$unitdir/sd-solo.service" "$unitdir/sd-solo-api@.service"; do
    [ -f "$u" ] || continue
    if grep -q "^Exec[A-Za-z]*=$esc/bin/sd " "$u"; then
      sed -i "s#^\\(Exec[A-Za-z]*=\\)$esc/bin/sd #\\1$home_dir/bin/sd-solo #" "$u"
      grep -q "^Exec[A-Za-z]*=$esc/bin/sd " "$u" && fail "moving $u to the new server name"
      say "systemd: $(basename "$u") now runs $home_dir/bin/sd-solo."
    fi
  done
  # 2. the forced command on every ssh key line this product added
  oldf="command=\"$home_dir/bin/sd\",restrict,pty "
  if [ -f "$ak" ] && grep -qF -- "$oldf" "$ak"; then
    aktmp="$(mktemp "$ak.XXXXXX")" || fail "mktemp beside $ak"
    awk -v old="$oldf" -v new="command=\"$home_dir/bin/sd-solo\",restrict,pty " \
        'index($0, old) == 1 { $0 = new substr($0, length(old) + 1) } { print }' "$ak" > "$aktmp" \
      && chmod --reference="$ak" "$aktmp" && mv -f "$aktmp" "$ak" || { rm -f "$aktmp"; fail "moving the forced command in $ak"; }
    say "ssh: the forced command in $ak now names $home_dir/bin/sd-solo."
  fi
  # 3. the sshd drop-in is root's; it keeps working through a link until it is re-applied
  if [ -f "$dropin" ] && grep -qxF "    ForceCommand $home_dir/bin/sd" "$dropin" 2>/dev/null; then
    ln -sfn sd-solo "$home_dir/bin/sd"
    warn "$dropin still names $home_dir/bin/sd; a link keeps it working until you remove it, which you should: Solo no longer uses it (its ssh has its own port, 4251): bash $home_dir/tools/solo-ssh.sh match $home_dir --remove  (needs sudo; it also removes the link)"
  fi
  return 0
}
# END upgrade_rename
if [ "$upgrade" -eq 1 ]; then
  migrate_server_name "$HOME_DIR" "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" "$HOME/.ssh/authorized_keys" \
    "/etc/ssh/sshd_config.d/50-sd-solo-$(id -un).conf"
fi

# ---------------------------------------------------------------- Solo's own ssh (LSOLO 29)
# THE UPGRADE OF A TREE THAT USED THE EARLIER ssh ROUTES (a forced-command key line in
# ~/.ssh/authorized_keys, or the sshd_config.d "Match User" block).  An upgrade asks nothing, so
# the listener's scope is derived: a tree that already has the new socket keeps its address, a
# tree that used either old route is local (the tight default: the owner opens it by choice,
# "bash <tree>/tools/solo-service.sh ssh <tree> open" plus the firewall rule) - except a managed
# tree on an old route, which was open - and a tree that used neither stays off.  The function between the markers is run by
# gplbld/test-sshport-units.py: keep the lines, and keep it free of anything but its arguments.
# BEGIN upgrade_ssh
ssh_upgrade_scope() {   # ssh_upgrade_scope HOME_DIR UNITDIR MODE_NAME AUTHORIZED_KEYS DROPIN -> off|local|open
  local home_dir="$1" unitdir="$2" mode_name="$3" ak="$4" dropin="$5" sock listen
  sock="$unitdir/sd-solo-ssh.socket"
  if [ -f "$sock" ]; then
    listen="$(sed -n 's/^ListenStream=//p' "$sock" | head -1)"
    case "$listen" in 0.0.0.0:*) echo open ;; *) echo local ;; esac
    return 0
  fi
  # Solo's own ssh directory is evidence ssh was in use even if its socket unit is gone (found 2 Oct 2026:
  # an upgrade that found no unit, no old key line and no drop-in left a tree that had ssh WITHOUT it).
  if [ -f "$home_dir/sshd/sshd_config" ]; then echo local; return 0; fi
  # LSOLO 38 (6 Oct 2026): a managed tree is no longer open by rule, so "managed" is no evidence of ssh.  It
  # only keeps what it meant for a tree that used an OLD route (one that predates the socket): that was open.
  if [ -f "$dropin" ]; then if [ "$mode_name" = "managed" ]; then echo open; else echo local; fi; return 0; fi
  if [ -f "$ak" ] && { grep -qF -- "command=\"$home_dir/bin/sd-solo\",restrict,pty " "$ak" \
                       || grep -qF -- "command=\"$home_dir/bin/sd\",restrict,pty " "$ak"; }; then
    if [ "$mode_name" = "managed" ]; then echo open; else echo local; fi; return 0
  fi
  echo off
}
# END upgrade_ssh
ssh_prepare() {   # the tree's own sshd directory, then the key if one was given
  local out
  out="$(bash "$HOME_DIR/tools/solo-ssh.sh" setup "$HOME_DIR" 2>&1)" || { printf '%s\n' "$out" | tail -8; fail "solo-ssh.sh setup"; }
  # LSOLO 31: under SELinux a sshd that is not root fails Fedora's PAM session step, so Solo's
  # sshd gets a PAM service of its own (sudo), and setup runs again to name it.
  if [ -e /sys/fs/selinux/enforce ] && ! printf '%s\n' "$out" | grep -q '^pam service    : /etc/pam.d/'; then
    say "SELinux is enabled: Solo's ssh needs its own PAM service, /etc/pam.d/sd-solo-ssh-$(id -un) (sudo)."
    if bash "$HOME_DIR/tools/solo-ssh.sh" pam "$HOME_DIR" --install 2>&1 | tail -3; then
      out="$(bash "$HOME_DIR/tools/solo-ssh.sh" setup "$HOME_DIR" 2>&1)" || { printf '%s\n' "$out" | tail -8; fail "solo-ssh.sh setup"; }
    else
      warn "Solo's PAM service was NOT installed, so the ssh sign-in will be refused; the line below says how to retry"
    fi
  fi
  printf '%s\n' "$out" | grep -E '^(WARNING|  /|  bash|host key|pam service|SOLO SSHD READY)' || true
  if [ -n "$ssh_key" ]; then
    bash "$HOME_DIR/tools/solo-ssh.sh" key-add "$HOME_DIR" "$ssh_key" | tail -2 || fail "solo-ssh.sh key-add"
  fi
}
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "$HOME/.local/bin is not on your PATH; add it (or run $HOME_DIR/bin/sd-solo)" ;; esac

# ---------------------------------------------------------------- the service, ssh, firewall
svc_state="not installed"
if [ "$upgrade" -eq 1 ]; then
  # The units name the tree by absolute path and the tree has not moved, so they are
  # kept; the daemon and the API socket are started again.
  if [ "$had_service" -eq 1 ]; then
    # 02 Oct 26 - THE API PORT MOVES TO 4249 ON UPGRADE (owner, 2 Oct 2026; it was 4243,
    # or whatever --api-port chose).  Only the port changes: the address - 127.0.0.1
    # (local) or 0.0.0.0 (open) - is kept, so the API stays as local or as open as it was.
    sock="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/sd-solo-api.socket"
    if [ -f "$sock" ]; then
      old_listen="$(sed -n 's/^ListenStream=//p' "$sock" | head -1)"
      old_port="${old_listen##*:}"
      if [ -n "$old_listen" ] && [ "$old_port" != "$api_port" ]; then
        sed -i "s/^ListenStream=\(.*\):$old_port\$/ListenStream=\1:$api_port/" "$sock"
        grep -q "^ListenStream=.*:$api_port\$" "$sock" || fail "moving the API listener from port $old_port to $api_port in $sock"
        say "The API listener moves from port $old_port to $api_port (${old_listen%:*} kept)."
        if [ "${old_listen%:*}" = "0.0.0.0" ] && command -v ufw >/dev/null 2>&1; then
          if sudo -n ufw allow "$api_port/tcp" >/dev/null 2>&1; then
            say "ufw: added 'allow $api_port/tcp'."
          else
            warn "the API is open to the network: allow TCP $api_port in the firewall (sudo ufw allow $api_port/tcp)"
          fi
          warn "a firewall rule for the old port $old_port may remain; remove it if nothing else uses it (sudo ufw delete allow $old_port/tcp)"
        fi
      fi
    fi
    say
    say "Starting the systemd user service again."
    # 25 Oct 26 - the daemon's restart (carried from SD Core's sd-lnxd.service).  The units above are kept on an upgrade, so an install made before this release would
    #   go on running "sd-solo -start", which forks a clean-up daemon that nothing watches, and would have no sd-solo-lnxd.service.  This writes this release's two
    #   daemon units over the kept ones (idempotent; it starts nothing - the start below does).  The script refuses a pair that names another tree, and the upgrade
    #   goes on without it.  test-lnxdunit-solo-units.py reads this block's place.
    if ! lnxd_out="$(bash "$HOME_DIR/tools/solo-service.sh" daemon "$HOME_DIR" 2>&1)"; then
      printf '%s\n' "$lnxd_out" | tail -3
      warn "the daemon's service units were NOT updated, so the clean-up daemon is not restarted if it dies; retry: bash $HOME_DIR/tools/solo-service.sh daemon $HOME_DIR"
    fi
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    systemctl --user start sd-solo.service || fail "systemctl --user start sd-solo.service"
    if [ -f "$sock" ]; then systemctl --user restart sd-solo-api.socket || fail "systemctl --user restart sd-solo-api.socket"; fi
    [ "$(systemctl --user is-active sd-solo.service)" = "active" ] || fail "sd-solo.service is not active after the upgrade"
    svc_state="sd-solo.service active"
    # LSOLO 29: Solo's own ssh.  The scope is read BEFORE "migrate", which removes the old key
    # lines that are part of the evidence that ssh was in use.
    old_dropin="/etc/ssh/sshd_config.d/50-sd-solo-$(id -un).conf"
    ssh="$(ssh_upgrade_scope "$HOME_DIR" "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" "$mode_name" "$HOME/.ssh/authorized_keys" "$old_dropin")"
    if [ "$ssh" != "off" ]; then
      ssh_wanted=1; ssh_key=""
      say
      say "Solo's own ssh: $ssh, port $ssh_port, your Linux password or a key."
      if ! { command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ]; }; then
        warn "sshd is not installed, so Solo's ssh is NOT set up.  Install it (sudo apt install openssh-server, or your distribution's package), then: bash $HOME_DIR/tools/solo-ssh.sh setup $HOME_DIR && bash $HOME_DIR/tools/solo-ssh.sh migrate $HOME_DIR && bash $HOME_DIR/tools/solo-service.sh ssh $HOME_DIR $ssh"
        ssh="off"; ssh_wanted=0
      else
        ssh_prepare
        bash "$HOME_DIR/tools/solo-ssh.sh" migrate "$HOME_DIR" | tail -3 || fail "solo-ssh.sh migrate"
        bash "$HOME_DIR/tools/solo-service.sh" ssh "$HOME_DIR" "$ssh" | tail -2 || fail "solo-service.sh ssh"
        if [ -f "$old_dropin" ] && [ ! -L "$HOME_DIR/bin/sd" ]; then
          warn "$old_dropin is the old ssh route and Solo no longer uses it; remove it (needs sudo): bash $HOME_DIR/tools/solo-ssh.sh match $HOME_DIR --remove"
        fi
      fi
    fi
    # LSOLO 66 (Solo carry 15, S.69 step 2): the AI helper's two user units.  An install from before this release has none; they are written (inert until the
    # administrator has set the AI up) and the socket started.  The script refuses a pair that names another tree, and the upgrade goes on without it.
    bash "$HOME_DIR/tools/solo-service.sh" ai "$HOME_DIR" 2>&1 | tail -2 || true
  else
    say "There was no service; starting SD directly ($HOME_DIR/bin/sd-solo -start)."
    "$HOME_DIR/bin/sd-solo" -start >/dev/null 2>&1 || true
  fi
elif [ "$no_service" -eq 0 ]; then
  say
  say "Installing the systemd user service."
  # Solo's own sshd directory (config, host key, key file) must exist before its units do.
  if [ "$ssh_wanted" -eq 1 ]; then ssh_prepare; fi
  svc_args=(install "$HOME_DIR" --api "$api" --ssh "$ssh")
  [ "$enable_linger" -eq 1 ] && svc_args+=(--enable-linger)
  svc_out="$(bash "$HOME_DIR/tools/solo-service.sh" "${svc_args[@]}" 2>&1)" || { printf '%s\n' "$svc_out" | tail -15; fail "solo-service.sh install"; }
  printf '%s\n' "$svc_out" | tail -8
  svc_state="$(printf '%s\n' "$svc_out" | grep '^SOLO SERVICE READY' | tail -1)"
  [ -n "$svc_state" ] || fail "solo-service.sh did not print 'SOLO SERVICE READY'"
else
  say "Not installing the service (--no-service).  Start SD with: $HOME_DIR/bin/sd-solo -start"
  "$HOME_DIR/bin/sd-solo" -start >/dev/null 2>&1 || true
fi

if [ "$upgrade" -eq 0 ] && [ "$ssh_wanted" -eq 1 ] && [ "$no_service" -eq 1 ]; then
  # No units were made, so there is no listener; the directory and the key are in place.
  say
  ssh_prepare
  warn "ssh is set up but NOT listening (no service): bash $HOME_DIR/tools/solo-service.sh install $HOME_DIR --ssh $ssh"
fi
# LSOLO 32 (owner, 4 Oct 2026: "yes - for both sd core and sd solo"): firewalld as well as ufw.
# On the Fedora VM "open" got no rule, and a connection from outside timed out at firewalld.  The
# rule goes to whichever of the two is RUNNING (ufw first, as before); with neither, the warning.
fw_open() {   # fw_open PORT WHAT
  local port="$1" what="$2"
  if command -v ufw >/dev/null 2>&1 && sudo -n ufw status 2>/dev/null | grep -q 'Status: active'; then
    say "ufw is active: opening TCP $port for $what (sudo)."
    sudo ufw allow "$port/tcp" || warn "could not add the ufw rule; open port $port yourself"
  # "firewall-cmd --state" is refused by polkit for an ordinary user (measured on Fedora 44:
  # "Authorization failed", so a running firewalld read as stopped); systemd answers anyone.
  elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    say "firewalld is running: opening TCP $port for $what (sudo)."
    { sudo firewall-cmd -q --permanent --add-port="$port/tcp" && sudo firewall-cmd -q --reload; } \
      || warn "could not add the firewalld rule; open port $port yourself (sudo firewall-cmd --permanent --add-port=$port/tcp && sudo firewall-cmd --reload)"
  else
    warn "$what is open on port $port; if a firewall runs on this computer, allow TCP $port"
  fi
}
[ "$ssh" = "open" ] && fw_open "$ssh_port" "ssh"
[ "$api" = "open" ] && fw_open "$api_port" "the API"

# ---------------------------------------------------------------- self-check (ruling 13 included)
say
say "Checking the install."
if [ "$upgrade" -eq 1 ]; then
  # No password is known here; a one-shot command uses the copy SD keeps for it.
  chk="$(echo "" | timeout 60 "$HOME_DIR/bin/sd-solo" WHO 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
elif [ "$first_login" -eq 1 ]; then
  # There is no account password yet; the global password (which this installer
  # has) opens the same account, and that is what the check can prove.
  chk="$(printf '%s\nWHO\nOFF\n' "$GLB_PW" | timeout 60 "$HOME_DIR/bin/sd-solo" 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
else
  chk="$(printf '%s\nWHO\nOFF\n' "$ACC_PW" | timeout 60 "$HOME_DIR/bin/sd-solo" 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
fi
printf '%s\n' "$chk" | grep -qE '^[0-9]+ sduser$' || { printf '%s\n' "$chk" | tail -5; fail "a session as sduser did not work"; }
say "  a session as sduser works"
rm -f "$HOME_DIR/\$internal"
# stdin is /dev/null: "timeout" runs its command in a BACKGROUND process group, and an sd
# that meets the terminal there is stopped by SIGTTIN - which hung this check for ever
# whenever the installer was run from a real terminal (found by verify-solo-interactive.sh).
gate="$(timeout 60 "$HOME_DIR/bin/sd-solo" -internal WHO </dev/null 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
if printf '%s\n' "$gate" | grep -qE '^[0-9]+ sdsys$'; then fail "sd -internal was admitted with no marker: the internal door is OPEN"; fi
printf '%s\n' "$gate" | grep -qx 'Connection terminated' || fail "sd -internal did not end with 'Connection terminated'"
[ ! -e "$HOME_DIR/\$internal" ] || fail "a marker file was left in $HOME_DIR"
say "  sd -internal is closed"
ACC_PW=""; ADM_PW=""; GLB_PW=""

# ---------------------------------------------------------------- summary
say
if [ "$upgrade" -eq 1 ]; then
  say "SD Core for Linux Solo is upgraded."
  say "  from commit   : ${old_commit:-unknown}"
  say "  to commit     : $COMMIT"
  say "  safety copy   : ${upgrade_backup:-not recorded}   (the tree as it was; delete it when you are satisfied)"
else
  say "SD Core for Linux Solo is installed."
fi
say "  home          : $HOME_DIR      ($mode_name)"
if [ -n "${reload_note:-}" ]; then
  say "  reloaded      : your saved data; configuration: $reload_note$([ "${mods_note:-}" != reloaded ] || echo "; your local VOC modifications (newvoc.mods)")"
  say "                  (your data as you left it is still in $kept_aside, a safety copy; delete it when you are satisfied)"
elif [ -n "${kept_aside:-}" ]; then
  say "  saved data    : NOT reloaded; it is in $kept_aside (not deleted)"
fi
if [ "$first_login" -eq 1 ]; then
  say "  start a session: sd-solo       (at THIS computer's keyboard: it asks you to choose the account password)"
else
  say "  start a session: sd-solo       (the account is sduser; it asks for the account password)"
fi
say "  command name  : sd-solo starts this one (plain sd is the multi-user SD Core's, if it is installed)"
say "  administrator : type ADMIN     (the administrator password unlocks the administrator commands)"
say "  shell and OS  : ${os_state:-unknown}   (off unless turned on; type ADMIN, then set.os.access, to see or change it)"
say "  pdf reader    : ${viewer_state:-unknown}   (none is allowed unless you said so; ADMIN, then set.viewer; documents: docs.install, then pdf)"
say "  service       : ${svc_state:-not installed}"
[ "$api" = "off" ] || say "  API           : $api, port $api_port (TLS 1.3, account password)"
[ "$ssh" = "off" ] || say "  ssh           : $ssh, port $ssh_port (ssh -p $ssh_port $(id -un)@<this computer>: your Linux password, then the SD account password); optional keys: bash $HOME_DIR/tools/solo-ssh.sh key-add $HOME_DIR <public key file>"
say "  uninstall     : bash $HOME_DIR/tools/deletesdsolo.sh"
say "  the download in $CLONE_DIR is removed when this script ends"
[ -z "$pkg_pre" ] || say "Pre-release ${pkg_pre}, commit ${COMMIT:0:12}.  What is installed is recorded in $HOME_DIR/.sdcore-install"
say
if [ "$upgrade" -eq 1 ]; then say "SOLO UPGRADE COMPLETE $HOME_DIR"; else say "SOLO INSTALL COMPLETE $HOME_DIR"; fi
