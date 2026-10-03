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
# port you asked for (the API's, or ssh's), and "loginctl enable-linger".
# Everything else is done as you, in your own home.  Nothing is written outside it.
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
#   --control-file FILE           answers for a MANAGED install (see sd-solo-setup.conf.sample);
#                                 its presence makes the install a managed client
#   --managed                     a managed client, answering the questions at the keyboard
#   --account-password-file FILE  the account password, one line (for automation; delete the file)
#   --admin-password-file FILE    the administrator password, one line
#   --global-password-file FILE   the global password, one line (managed mode)
#   --api off|local|open          the API listener (standalone only; managed is always open);
#                                 always port 4249 - fixed, not an option (owner, 2 Oct 2026)
#   --ssh off|local|open          Solo's own ssh listener (standalone only; managed is always open);
#                                 always port 4251 - fixed, not an option.  Sign-in: your Linux password, or a key.
#   --ssh-key FILE                a public key to add for ssh straight into sd (turns ssh on, local,
#                                 unless --ssh says otherwise)
#   --enable-linger               run "loginctl enable-linger" so SD survives sign-out
#   --skip-packages               do not install packages; check the tools instead
#   --no-service                  do not install the systemd user service
#   --yes                         do not ask "Continue?"
#   --upgrade                     bring an installed tree up to the current release in place:
#                                 programs and system objects are replaced; the account, its data,
#                                 the passwords, sd.conf, the audit trail, GLOBAL.BP.OUT and the
#                                 deny list are kept.  A safety copy of the whole tree is made
#                                 first (<home>.before-upgrade-<time>) and put back if any step
#                                 fails.  Takes no password and no other install option.
#
# EXIT: 0 installed and self-checked; 1 a step failed; 2 refused to start.
# The last line of a good install is "SOLO INSTALL COMPLETE <home>".
#
# OWNER'S RULINGS THIS FOLLOWS (PROJECT_STATUS.md, "WHAT SD CORE FOR LINUX SOLO IS"):
# no root and no OS users; the source is downloaded to a temporary directory under ~
# (29 Sep 2026); password order account, administrator, then - managed only - global
# (ruling 30); the account password differs from the global one (ruling 19); managed
# mode forces the API open and ssh on (ruling 22); "sd -internal" is closed when the
# install finishes (ruling 13, LSOLO 9).

set -euo pipefail

REPO_URL="https://github.com/dmontaine/SDCore4LinuxSolo"
REPO_BRANCH="main"
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
fail()   { printf '%bFAILED at: %s%b\n' "$RED" "$*" "$NC" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || refuse "run this as your own user, not root: SD Core for Linux Solo never runs as root"

# ---------------------------------------------------------------- options
HOME_DIR="$HOME/SDCoreSolo"
control_file=""; managed=0
acc_file=""; adm_file=""; glb_file=""
# 02 Oct 26 - THE API PORT IS 4249, FIXED (owner, 2 Oct 2026: "make ports 4247 and 4249
# -- do not allow adjustable ports").  --api-port is gone.  The witnesses' private
# ports go through solo-service.sh's announced test hook, SDSOLO_TEST_API_PORT.
api="" ; api_port="4249"
# 02 Oct 26 - Solo's own ssh listener, port 4251, FIXED (LSOLO 29, owner).  --ssh-match is gone
# with the routes it belonged to.  The witnesses' private port goes through the announced hook
# SDSOLO_TEST_SSH_PORT, as the API's does.
ssh=""; ssh_port="4251"
ssh_key=""; enable_linger=0; skip_pkgs=0; no_service=0; assume_yes=0; upgrade=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --home)                   [ "$#" -ge 2 ] || refuse "--home needs a directory"; HOME_DIR="$2"; shift 2 ;;
    --control-file)           [ "$#" -ge 2 ] || refuse "--control-file needs a file"; control_file="$2"; managed=1; shift 2 ;;
    --managed)                managed=1; shift ;;
    --account-password-file)  [ "$#" -ge 2 ] || refuse "$1 needs a file"; acc_file="$2"; shift 2 ;;
    --admin-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; adm_file="$2"; shift 2 ;;
    --global-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; glb_file="$2"; managed=1; shift 2 ;;
    --api)                    [ "$#" -ge 2 ] || refuse "--api needs off, local or open"; api="$2"; shift 2 ;;
    --ssh)                    [ "$#" -ge 2 ] || refuse "--ssh needs off, local or open"; ssh="$2"; shift 2 ;;
    --ssh-key)                [ "$#" -ge 2 ] || refuse "--ssh-key needs a public key file"; ssh_key="$2"; shift 2 ;;
    --ssh-match)              refuse "--ssh-match is gone: Solo's ssh has its own port (4251) now and no longer uses the machine's sshd_config. Use --ssh local or --ssh open." ;;
    --enable-linger)          enable_linger=1; shift ;;
    --skip-packages)          skip_pkgs=1; shift ;;
    --no-service)             no_service=1; shift ;;
    --yes)                    assume_yes=1; shift ;;
    --upgrade)                upgrade=1; shift ;;
    -h|--help)                sed -n '2,70p' "$0"; exit 0 ;;
    *) refuse "unknown option: $1 (see --help)" ;;
  esac
done
case "$HOME_DIR" in /*) ;; *) refuse "--home must be an absolute path (got '$HOME_DIR')" ;; esac
case "$HOME_DIR" in *" "*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*|*'%'*) refuse "the install directory must not contain a space, quote, backslash, \$, backtick or %: $HOME_DIR" ;; esac
case "$api" in ""|off|local|open) ;; *) refuse "--api must be off, local or open (got '$api')" ;; esac
case "$ssh" in ""|off|local|open) ;; *) refuse "--ssh must be off, local or open (got '$ssh')" ;; esac
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
  [ -z "$control_file$acc_file$adm_file$glb_file$api$ssh$ssh_key" ] && [ "$managed" -eq 0 ] && [ "$enable_linger" -eq 0 ] \
    || refuse "--upgrade keeps the mode, passwords, API and ssh settings as installed; it takes no password, control-file, --api, --ssh, --ssh-key, --enable-linger or --managed option"
elif [ -e "$HOME_DIR" ] && [ -n "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  refuse "$HOME_DIR exists and is not empty, and is not an SD Core for Linux Solo tree; this script will not use it"
fi
# 02 Oct 26 - THE MULTI-USER PRODUCT NO LONGER BLOCKS THIS INSTALL (owner, 2 Oct 2026: yes to
# installing both).  The two have separate API ports (4247 / 4249) and shared-memory keys, and
# the command names below say which one you start.
[ "$upgrade" -eq 1 ] || { systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is already running for this user"; }
command -v systemctl >/dev/null || refuse "systemctl is required (a systemd user manager)"
[ -d "/run/user/$(id -u)" ] || warn "no /run/user/$(id -u): the systemd user manager may not be running in this shell"

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

# An upgrade asks nothing and reads the install's own record; a first install does
# everything from here to "scratch space".
cf_admin=""; cf_global=""; cf_ssh_key=""; cf_api=""; cf_linger=""; cf_deny=""
ACC_PW=""; ADM_PW=""; GLB_PW=""
ssh_wanted=0; first_login=0
if [ "$upgrade" -eq 1 ]; then
  api="off"   # not used: an upgrade leaves the service and API as they are
  ssh="off"   # the upgrade works out Solo's own ssh from what the tree already has (ssh_upgrade_scope)
  old_commit="$(sed -n 's/^commit //p' "$HOME_DIR/.sdcore-install" | head -1)"
  mode_name="$(sed -n 's/^mode //p' "$HOME_DIR/.sdcore-install" | head -1)"
  case "$mode_name" in standalone) managed=0 ;; managed) managed=1 ;; *) refuse "$HOME_DIR/.sdcore-install has no usable 'mode' line" ;; esac
  say
  say "SD Core for Linux Solo - upgrade"
  say "  tree        : $HOME_DIR ($mode_name, installed from ${old_commit:-an unknown commit})"
  say "  source      : $REPO_URL ($REPO_BRANCH), downloaded to $CLONE_DIR and removed afterwards"
  say "  kept        : the account and its data, all passwords, sd.conf, the audit trail, GLOBAL.BP.OUT, the deny list,"
  say "                the service and ssh settings"
  say "  replaced    : programs and system objects; a safety copy of the whole tree is made first"
  say "  running as  : $(id -un)"
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
  [ "$cf_linger" != "yes" ] || enable_linger=1
fi

# ---------------------------------------------------------------- questions
say
say "SD Core for Linux Solo - install"
say "  into        : $HOME_DIR"
say "  source      : $REPO_URL ($REPO_BRANCH), downloaded to $CLONE_DIR and removed afterwards"
say "  running as  : $(id -un)"
say

ask_yn() {   # ask_yn "question" default(y|n)  -> 0 yes, 1 no ; non-interactive: the default
  local q="$1" d="$2" a
  if [ "$interactive" -ne 1 ]; then [ "$d" = y ]; return; fi
  read -r -p "$q [$([ "$d" = y ] && echo Y/n || echo y/N)] " a < /dev/tty
  a="${a:-$d}"; case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

if [ "$managed" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  say "SD Core for Linux Solo runs in one of two modes, fixed now (changing it means reinstalling):"
  say "  standalone - a local single-user database, like SQLite"
  say "  managed    - a client of an SD Core server, which manages this computer with a global"
  say "               password; the API and ssh are always on and reachable from the network"
  ask_yn "Is this computer managed by an SD Core server?" n && managed=1
fi
mode_name="standalone"; [ "$managed" -eq 1 ] && mode_name="managed"

# passwords, in the owner's order (ruling 30): account, administrator, then - managed - global
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

say "Passwords. Every SD session asks for the ACCOUNT password; the ADMINISTRATOR password unlocks"
say "SD's administrator commands (ADMIN)."
say
ACC_PW=""; ADM_PW=""; GLB_PW=""
# LSOLO 14 (Windows Solo SOLO 18, owner 27 Sep 2026): a control file never holds the
# account password.  With one and no --account-password-file, the installer does not
# ask for it either: the user chooses it at the console on first login, which is what
# lets one control file initialise several computers.  --account-password-file still
# sets it at install time, as before.
first_login=0
if [ -n "$control_file" ] && [ -z "$acc_file" ]; then
  first_login=1
  say "The account password is not asked for: whoever first starts SD at this computer's keyboard chooses it."
else
  get_password ACC_PW account "$acc_file" ""
fi
get_password ADM_PW administrator "$adm_file" "$cf_admin"
if [ "$managed" -eq 1 ]; then
  get_password GLB_PW global "$glb_file" "$cf_global"
  [ "$first_login" -eq 1 ] || [ "$GLB_PW" != "$ACC_PW" ] || refuse "the global password must differ from the account password (ruling 19)"
  [ "$GLB_PW" != "$ADM_PW" ] || refuse "the global password must differ from the administrator password"
fi

# the API and ssh
if [ "$managed" -eq 1 ]; then
  api="open"; ssh="open"
  say "Managed mode: the API is open to the network on port $api_port and ssh is open on port $ssh_port (your Linux password, or a key)."
else
  if [ -z "$api" ]; then
    if [ "$interactive" -eq 1 ]; then
      say
      say "The API lets programs on other computers (or this one) connect to SD over TLS 1.3 with your account"
      say "password.  off = no listener; local = this computer only; open = reachable from the network."
      read -r -p "API listener [off/local/open] (default off): " api < /dev/tty
      api="${api:-off}"
      case "$api" in off|local|open) ;; *) refuse "the API answer must be off, local or open (got '$api')" ;; esac
    else
      api="off"
    fi
  fi
  if [ -z "$ssh" ]; then
    if [ -n "$ssh_key" ]; then
      ssh="local"
    elif [ "$interactive" -eq 1 ]; then
      say
      say "ssh straight into sd uses Solo's own listener on port $ssh_port (your Linux account and password, or a key; the machine's own ssh on"
      say "port 22 is not used).  off = none; local = this computer only; open = reachable from the network."
      read -r -p "ssh listener [off/local/open] (default off): " ssh < /dev/tty
      ssh="${ssh:-off}"
      case "$ssh" in off|local|open) ;; *) refuse "the ssh answer must be off, local or open (got '$ssh')" ;; esac
    else
      ssh="off"
    fi
  fi
fi
ssh_wanted=0; [ "$ssh" = "off" ] || ssh_wanted=1
if [ "$ssh_wanted" -eq 1 ] && [ -z "$ssh_key" ] && [ "$interactive" -eq 1 ]; then
  read -r -p "Path to a public key to add for ssh into sd (blank to skip): " ssh_key < /dev/tty
fi
if [ -n "$ssh_key" ]; then
  [ -r "$ssh_key" ] || refuse "cannot read the ssh public key $ssh_key"
fi
if [ "$enable_linger" -eq 0 ] && [ "$no_service" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  say
  say "To keep SD running (and reachable) after you sign out, 'loginctl enable-linger' is needed."
  ask_yn "Enable it now?" y && enable_linger=1
fi

# ---------------------------------------------------------------- confirmation
say
say "Ready to install:"
say "  mode          : $mode_name"
say "  account pw    : $([ "$first_login" -eq 1 ] && echo "chosen at first login, at this computer's keyboard" || echo "set now")"
say "  API           : $api$([ "$api" != off ] && echo " (port $api_port)")"
say "  ssh into sd   : $ssh$([ "$ssh" != off ] && echo " (port $ssh_port, Linux password or key)")$([ -n "$ssh_key" ] && echo ", key $ssh_key")"
say "  service       : $([ "$no_service" -eq 1 ] && echo "not installed" || echo "systemd user service$([ "$enable_linger" -eq 1 ] && echo ", linger on" || echo ", linger NOT enabled")")"
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
detect_distro() {
  is_arch=0; is_debian=0; is_fedora=0; is_suse=0
  if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    ids=" ${ID:-} ${ID_LIKE:-} "
    case "$ids" in *" arch "*) is_arch=1 ;; esac
    case "$ids" in *" debian "*|*" ubuntu "*) is_debian=1 ;; esac
    # Fedora only (owner, 30 Sep 2026).  RHEL and its clones name "rhel" and also
    # "fedora" in ID_LIKE, so they are turned away here, not matched by the fedora test.
    case "$ids" in *" fedora "*) is_fedora=1 ;; esac
    case "$ids" in *" rhel "*) [ "${ID:-}" = fedora ] || is_fedora=0 ;; esac
    case "$ids" in *" suse "*|*" opensuse"*|*" sles "*) is_suse=1 ;; esac
  fi
}
install_packages() {
  detect_distro
  local ssh_pkg=0; [ "$ssh_wanted" -eq 1 ] && ssh_pkg=1
  if [ "$is_debian" -eq 1 ]; then
    say "Debian or Ubuntu based: apt-get"
    local pk="git build-essential micro lynx libsodium-dev libssl-dev python3-dev"
    [ "$ssh_pkg" -eq 1 ] && pk="$pk openssh-server"
    # shellcheck disable=SC2086
    sudo apt-get -y install $pk || fail "apt-get"
    sudo apt-get -y --ignore-missing install libcrypt-dev || true
  elif [ "$is_fedora" -eq 1 ]; then
    say "Fedora based: dnf"
    local pk="git make automake gcc gcc-c++ kernel-devel micro lynx libsodium-devel openssl-devel python3-devel"
    [ "$ssh_pkg" -eq 1 ] && pk="$pk openssh-server"
    # shellcheck disable=SC2086
    sudo dnf -y install $pk || fail "dnf"
  elif [ "$is_suse" -eq 1 ]; then
    say "openSUSE or SUSE based: zypper"
    local pk="git make automake gcc gcc-c++ kernel-default-devel micro-editor lynx libsodium-devel libopenssl-devel python3-devel"
    [ "$ssh_pkg" -eq 1 ] && pk="$pk openssh"
    # shellcheck disable=SC2086
    sudo zypper --non-interactive install $pk || fail "zypper"
  elif [ "$is_arch" -eq 1 ]; then
    say "Arch based: pacman"
    local pk="git base-devel micro lynx libsodium openssl python"
    [ "$ssh_pkg" -eq 1 ] && pk="$pk openssh"
    # shellcheck disable=SC2086
    sudo pacman -Sy --noconfirm $pk || fail "pacman"
  else
    refuse "this distribution could not be identified from /etc/os-release; supported: Debian, Ubuntu, Arch, Fedora and openSUSE families (not RHEL or its clones)"
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
say "Downloading the source (main branch) to $CLONE_DIR"
git ls-remote -q "$REPO_URL" >/dev/null 2>&1 || refuse "cannot reach $REPO_URL - check the network"
rm -rf "$CLONE_DIR"
git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$CLONE_DIR" 2>&1 | tail -2
COMMIT="$(git -C "$CLONE_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
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
    systemctl --user stop sd-solo-ssh.socket sd-solo-api.socket sd-solo.service >/dev/null 2>&1 || true
  fi
  if ! bash "$SRC/gplbld/solo-stage.sh" --upgrade "$HOME_DIR" > "$WORK/stage.log" 2>&1; then
    tail -25 "$WORK/stage.log"
    [ "$had_service" -eq 0 ] || systemctl --user start sd-solo.service sd-solo-api.socket sd-solo-ssh.socket >/dev/null 2>&1 || true
    fail "the upgrade (full log: $WORK/stage.log - removed when this script ends). The tree was put back as it was; if the log above does not say so, do not use $HOME_DIR: your data is in the safety copy $HOME_DIR.before-upgrade-*"
  fi
  grep -qx "solo-stage: UPGRADE COMPLETE in $HOME_DIR" <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'solo-stage: UPGRADE COMPLETE'"
  upgrade_backup="$(cat "$HOME_DIR/.last-upgrade-backup" 2>/dev/null || true)"
  rm -f "$HOME_DIR/.last-upgrade-backup"
  { printf 'commit %s\n' "$COMMIT"; printf 'date %s\n' "$(date -Is)"; printf 'mode %s\n' "$mode_name"; \
    printf 'upgraded-from %s\n' "${old_commit:-unknown}"; } > "$HOME_DIR/.sdcore-install"
  chmod 600 "$HOME_DIR/.sdcore-install"
else
say "Installing into $HOME_DIR and running the bootstrap."
st_args=()
if [ "$first_login" -eq 0 ]; then printf '%s\n' "$ACC_PW" > "$WORK/acc.pw"; st_args+=(--account-password-file "$WORK/acc.pw"); fi
printf '%s\n' "$ADM_PW" > "$WORK/adm.pw"; st_args+=(--admin-password-file "$WORK/adm.pw")
if [ "$managed" -eq 1 ]; then printf '%s\n' "$GLB_PW" > "$WORK/glb.pw"; st_args+=(--global-password-file "$WORK/glb.pw"); fi
if [ -n "$cf_deny" ]; then st_args+=(--deny-verbs "$cf_deny"); fi
bash "$SRC/gplbld/solo-stage.sh" "${st_args[@]}" "$HOME_DIR" > "$WORK/stage.log" 2>&1 \
  || { tail -25 "$WORK/stage.log"; fail "the bootstrap (full log: $WORK/stage.log - removed when this script ends; re-run the failing step by hand from $SRC/gplbld/solo-stage.sh)"; }
rm -f "$WORK/acc.pw" "$WORK/adm.pw" "$WORK/glb.pw"
if [ "$first_login" -eq 0 ]; then
  grep -qx 'SOLO PASSWORD SET ACCOUNT' <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'SOLO PASSWORD SET ACCOUNT'"
else
  grep -qx 'SOLO PASSWORD SET GLOBAL' <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
    || fail "the stage log has no 'SOLO PASSWORD SET GLOBAL' (a first-login install is managed, so the global password must be set)"
  [ ! -e "$HOME_DIR/\$cred/sduser" ] || fail "\$cred/sduser exists on a first-login install"
fi
[ -f "$HOME_DIR/user_accounts/sduser/voc/%0" ] || [ -d "$HOME_DIR/user_accounts/sduser" ] || fail "the account directory is missing"

# what was installed
{ printf 'commit %s\n' "$COMMIT"; printf 'date %s\n' "$(date -Is)"; printf 'mode %s\n' "$mode_name"; } > "$HOME_DIR/.sdcore-install"
chmod 600 "$HOME_DIR/.sdcore-install"
fi

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
# managed tree is open, a tree that used either old route is local (the tight default: the
# owner opens it by choice, "bash <tree>/tools/solo-service.sh ssh <tree> open" plus the firewall
# rule), and a tree that used neither stays off.  The function between the markers is run by
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
  if [ "$mode_name" = "managed" ]; then echo open; return 0; fi
  if [ -f "$dropin" ]; then echo local; return 0; fi
  if [ -f "$ak" ] && { grep -qF -- "command=\"$home_dir/bin/sd-solo\",restrict,pty " "$ak" \
                       || grep -qF -- "command=\"$home_dir/bin/sd\",restrict,pty " "$ak"; }; then echo local; return 0; fi
  echo off
}
# END upgrade_ssh
ssh_prepare() {   # the tree's own sshd directory, then the key if one was given
  local out
  out="$(bash "$HOME_DIR/tools/solo-ssh.sh" setup "$HOME_DIR" 2>&1)" || { printf '%s\n' "$out" | tail -8; fail "solo-ssh.sh setup"; }
  printf '%s\n' "$out" | grep -E '^(WARNING|  /|host key|SOLO SSHD READY)' || true
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
if [ "$ssh" = "open" ] && command -v ufw >/dev/null 2>&1 && sudo -n ufw status 2>/dev/null | grep -q 'Status: active'; then
  say "ufw is active: opening TCP $ssh_port for ssh (sudo)."
  sudo ufw allow "$ssh_port/tcp" || warn "could not add the ufw rule; open port $ssh_port yourself"
elif [ "$ssh" = "open" ]; then
  warn "ssh is open on port $ssh_port; if a firewall runs on this computer, allow TCP $ssh_port"
fi
if [ "$api" = "open" ] && command -v ufw >/dev/null 2>&1 && sudo -n ufw status 2>/dev/null | grep -q 'Status: active'; then
  say "ufw is active: opening TCP $api_port for the API (sudo)."
  sudo ufw allow "$api_port/tcp" || warn "could not add the ufw rule; open port $api_port yourself"
elif [ "$api" = "open" ]; then
  warn "the API is open on port $api_port; if a firewall runs on this computer, allow TCP $api_port"
fi

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
say "  home          : $HOME_DIR      (mode: $mode_name)"
if [ "$first_login" -eq 1 ]; then
  say "  start a session: sd-solo       (at THIS computer's keyboard: it asks you to choose the account password)"
else
  say "  start a session: sd-solo       (the account is sduser; it asks for the account password)"
fi
say "  command name  : sd-solo starts this one (plain sd is the multi-user SD Core's, if it is installed)"
say "  administrator : type ADMIN     (the administrator password unlocks the administrator commands)"
say "  service       : ${svc_state:-not installed}"
[ "$api" = "off" ] || say "  API           : $api, port $api_port (TLS 1.3, account password)"
[ "$ssh" = "off" ] || say "  ssh           : $ssh, port $ssh_port (ssh -p $ssh_port $(id -un)@<this computer>: your Linux password, then the SD account password); optional keys: bash $HOME_DIR/tools/solo-ssh.sh key-add $HOME_DIR <public key file>"
say "  uninstall     : bash $HOME_DIR/tools/deletesdsolo.sh"
say "  the download in $CLONE_DIR is removed when this script ends"
say
if [ "$upgrade" -eq 1 ]; then say "SOLO UPGRADE COMPLETE $HOME_DIR"; else say "SOLO INSTALL COMPLETE $HOME_DIR"; fi
