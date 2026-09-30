#!/bin/bash
#
# SD Core for Linux Solo - install script
#   (c) 2026 Donald Montaine.  Released under the Blue Oak Model License 1.0.0,
#   a copy can be found on the web here: https://blueoakcouncil.org/license/1.0.0
#
#   bash installsolo.sh [options]        run it as YOUR OWN USER, never as root
#
# WHAT IT DOES.  Downloads the source of SD Core for Linux Solo (the main branch of
# github.com/dmontaine/SDCore4LinuxSolo) into a TEMPORARY directory under your home,
# builds it there, installs it into ~/SDCoreSolo, sets your passwords, starts it as
# your own systemd service, and deletes the download.  The script itself can be
# carried on a USB stick: it needs the network only for the packages and the download.
#
# WHAT NEEDS sudo, and ONLY this: installing the build packages, opening a firewall
# port you asked for, the optional sshd_config.d block, and "loginctl enable-linger".
# Everything else is done as you, in your own home.  Nothing is written outside it.
#
# OPTIONS (all optional; the script asks for anything it needs that it was not given)
#   --home DIR                    install here instead of ~/SDCoreSolo
#   --control-file FILE           answers for a MANAGED install (see sd-solo-setup.conf.sample);
#                                 its presence makes the install a managed client
#   --managed                     a managed client, answering the questions at the keyboard
#   --account-password-file FILE  the account password, one line (for automation; delete the file)
#   --admin-password-file FILE    the administrator password, one line
#   --global-password-file FILE   the global password, one line (managed mode)
#   --api off|local|open          the API listener (standalone only; managed is always open)
#   --api-port N                  the API port, 1024-65535 (default 4243)
#   --ssh-key FILE                a public key to add for ssh straight into sd
#   --ssh-match                   also write the sshd_config.d block (needs sudo)
#   --enable-linger               run "loginctl enable-linger" so SD survives sign-out
#   --skip-packages               do not install packages; check the tools instead
#   --no-service                  do not install the systemd user service
#   --yes                         do not ask "Continue?"
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
api="" ; api_port="4243"
ssh_key=""; ssh_match=0; enable_linger=0; skip_pkgs=0; no_service=0; assume_yes=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --home)                   [ "$#" -ge 2 ] || refuse "--home needs a directory"; HOME_DIR="$2"; shift 2 ;;
    --control-file)           [ "$#" -ge 2 ] || refuse "--control-file needs a file"; control_file="$2"; managed=1; shift 2 ;;
    --managed)                managed=1; shift ;;
    --account-password-file)  [ "$#" -ge 2 ] || refuse "$1 needs a file"; acc_file="$2"; shift 2 ;;
    --admin-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; adm_file="$2"; shift 2 ;;
    --global-password-file)    [ "$#" -ge 2 ] || refuse "$1 needs a file"; glb_file="$2"; managed=1; shift 2 ;;
    --api)                    [ "$#" -ge 2 ] || refuse "--api needs off, local or open"; api="$2"; shift 2 ;;
    --api-port)               [ "$#" -ge 2 ] || refuse "--api-port needs a number"; api_port="$2"; shift 2 ;;
    --ssh-key)                [ "$#" -ge 2 ] || refuse "--ssh-key needs a public key file"; ssh_key="$2"; shift 2 ;;
    --ssh-match)              ssh_match=1; shift ;;
    --enable-linger)          enable_linger=1; shift ;;
    --skip-packages)          skip_pkgs=1; shift ;;
    --no-service)             no_service=1; shift ;;
    --yes)                    assume_yes=1; shift ;;
    -h|--help)                sed -n '2,45p' "$0"; exit 0 ;;
    *) refuse "unknown option: $1 (see --help)" ;;
  esac
done
case "$HOME_DIR" in /*) ;; *) refuse "--home must be an absolute path (got '$HOME_DIR')" ;; esac
case "$HOME_DIR" in *" "*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*|*'%'*) refuse "the install directory must not contain a space, quote, backslash, \$, backtick or %: $HOME_DIR" ;; esac
case "$api" in ""|off|local|open) ;; *) refuse "--api must be off, local or open (got '$api')" ;; esac
case "$api_port" in ''|*[!0-9]*) refuse "--api-port must be a number" ;; esac
{ [ "$api_port" -ge 1024 ] && [ "$api_port" -le 65535 ]; } || refuse "--api-port must be 1024-65535: a user cannot bind below 1024"

interactive=0; [ -t 0 ] && [ -r /dev/tty ] && interactive=1

# ---------------------------------------------------------------- what is already here
[ -f "$HOME_DIR/.sdcoresolo" ] && refuse "SD Core for Linux Solo is already installed in $HOME_DIR.
  Upgrading in place is not built yet.  Remove it first (your data can be kept):
      bash $HOME_DIR/tools/deletesolo.sh"
if [ -e "$HOME_DIR" ] && [ -n "$(ls -A "$HOME_DIR" 2>/dev/null)" ]; then
  refuse "$HOME_DIR exists and is not empty, and is not an SD Core for Linux Solo tree; this script will not use it"
fi
if [ -x /usr/local/sdsys/bin/sd ] || [ -e /etc/sd.conf ]; then
  refuse "the multi-user SD Core for Linux is installed on this computer (/usr/local/sdsys or /etc/sd.conf).
  Solo cannot share a computer with it: both use the API port 4243 and the shared-memory name.
  Uninstall it first (its deletesdai.sh)."
fi
systemctl --user is-active sd-solo.service >/dev/null 2>&1 && refuse "a Solo service is already running for this user"
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

# ---------------------------------------------------------------- the control file
cf_admin=""; cf_global=""; cf_ssh_key=""; cf_api=""; cf_match=""; cf_linger=""; cf_deny=""
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
      ssh-match)       cf_match="$val" ;;
      enable-linger)   cf_linger="$val" ;;
      *) warn "the control file has an item this installer does not know, ignored: $key" ;;
    esac
  done < "$control_file"
  # Ruling 34: verb names only (letters, digits, . $ _ - , and spaces); solo-stage.sh checks it again.
  case "$cf_deny" in
    *[!A-Za-z0-9.\$_,\ -]*) refuse "deny-verbs in the control file holds a character that cannot be in a verb name" ;;
  esac
  [ -z "$cf_ssh_key" ] || [ -n "$ssh_key" ] || ssh_key="$cf_ssh_key"
  [ "$cf_match" != "yes" ] || ssh_match=1
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
get_password ACC_PW account "$acc_file" ""
get_password ADM_PW administrator "$adm_file" "$cf_admin"
if [ "$managed" -eq 1 ]; then
  get_password GLB_PW global "$glb_file" "$cf_global"
  [ "$GLB_PW" != "$ACC_PW" ] || refuse "the global password must differ from the account password (ruling 19)"
  [ "$GLB_PW" != "$ADM_PW" ] || refuse "the global password must differ from the administrator password"
fi

# the API and ssh
if [ "$managed" -eq 1 ]; then
  api="open"; ssh_wanted=1
  say "Managed mode: the API is open to the network on port $api_port and ssh is required."
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
  ssh_wanted=0
  if [ -n "$ssh_key" ] || [ "$ssh_match" -eq 1 ]; then ssh_wanted=1; fi
  if [ "$ssh_wanted" -eq 0 ] && [ "$interactive" -eq 1 ]; then
    ask_yn "Set up ssh straight into sd (needs an ssh server)?" n && ssh_wanted=1
  fi
fi
if [ "$ssh_wanted" -eq 1 ] && [ -z "$ssh_key" ] && [ "$interactive" -eq 1 ]; then
  read -r -p "Path to a public key to add for ssh into sd (blank to skip): " ssh_key < /dev/tty
fi
if [ -n "$ssh_key" ]; then
  [ -r "$ssh_key" ] || refuse "cannot read the ssh public key $ssh_key"
fi
if [ "$ssh_wanted" -eq 1 ] && [ "$ssh_match" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  say "Keys added above land in sd.  To let your ssh PASSWORD login land in sd too, a"
  say "'Match User' block goes into the machine's sshd configuration (needs sudo)."
  ask_yn "Write that block?" n && ssh_match=1
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
say "  API           : $api$([ "$api" != off ] && echo " (port $api_port)")"
say "  ssh into sd   : $([ "$ssh_wanted" -eq 1 ] && echo "yes$([ -n "$ssh_key" ] && echo ", key $ssh_key")$([ "$ssh_match" -eq 1 ] && echo ", Match block")" || echo no)"
say "  service       : $([ "$no_service" -eq 1 ] && echo "not installed" || echo "systemd user service$([ "$enable_linger" -eq 1 ] && echo ", linger on" || echo ", linger NOT enabled")")"
say "  packages      : $([ "$skip_pkgs" -eq 1 ] && echo "not installed (checked)" || echo "installed with sudo")"
if [ "$assume_yes" -eq 0 ] && [ "$interactive" -eq 1 ]; then
  ask_yn "Continue?" y || refuse "cancelled by you; nothing was changed"
fi

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
    case "$ids" in *" fedora "*|*" rhel "*) is_fedora=1 ;; esac
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
    say "Fedora or RHEL based: dnf"
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
    refuse "this distribution could not be identified from /etc/os-release; supported: Debian, Ubuntu, Arch, Fedora, RHEL and openSUSE families"
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
[ -x "$SRC/bin/sd" ] || fail "the build reported success but bin/sd is missing"
say "Build complete."

# ---------------------------------------------------------------- stage and bootstrap
say
say "Installing into $HOME_DIR and running the bootstrap."
st_args=()
umask 077
printf '%s\n' "$ACC_PW" > "$WORK/acc.pw"; st_args+=(--account-password-file "$WORK/acc.pw")
printf '%s\n' "$ADM_PW" > "$WORK/adm.pw"; st_args+=(--admin-password-file "$WORK/adm.pw")
if [ "$managed" -eq 1 ]; then printf '%s\n' "$GLB_PW" > "$WORK/glb.pw"; st_args+=(--global-password-file "$WORK/glb.pw"); fi
if [ -n "$cf_deny" ]; then st_args+=(--deny-verbs "$cf_deny"); fi
bash "$SRC/gplbld/solo-stage.sh" "${st_args[@]}" "$HOME_DIR" > "$WORK/stage.log" 2>&1 \
  || { tail -25 "$WORK/stage.log"; fail "the bootstrap (full log: $WORK/stage.log - removed when this script ends; re-run the failing step by hand from $SRC/gplbld/solo-stage.sh)"; }
rm -f "$WORK/acc.pw" "$WORK/adm.pw" "$WORK/glb.pw"
grep -qx 'SOLO PASSWORD SET ACCOUNT' <(sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g' "$WORK/stage.log") \
  || fail "the stage log has no 'SOLO PASSWORD SET ACCOUNT'"
[ -f "$HOME_DIR/user_accounts/sduser/voc/%0" ] || [ -d "$HOME_DIR/user_accounts/sduser" ] || fail "the account directory is missing"

# what was installed
{ printf 'commit %s\n' "$COMMIT"; printf 'date %s\n' "$(date -Is)"; printf 'mode %s\n' "$mode_name"; } > "$HOME_DIR/.sdcore-install"
chmod 600 "$HOME_DIR/.sdcore-install"

# The stage leaves its own daemon running; the service takes over below.
"$HOME_DIR/bin/sd" -stop >/dev/null 2>&1 || true

# ---------------------------------------------------------------- sd on the PATH
mkdir -p "$HOME/.local/bin"
if [ -e "$HOME/.local/bin/sd" ] && [ ! -L "$HOME/.local/bin/sd" ]; then
  warn "$HOME/.local/bin/sd exists and is not a link; left alone (run SD as $HOME_DIR/bin/sd)"
else
  ln -sfn "$HOME_DIR/bin/sd" "$HOME/.local/bin/sd"
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "$HOME/.local/bin is not on your PATH; add it (or run $HOME_DIR/bin/sd)" ;; esac
fi

# ---------------------------------------------------------------- the service, ssh, firewall
svc_state="not installed"
if [ "$no_service" -eq 0 ]; then
  say
  say "Installing the systemd user service."
  svc_args=(install "$HOME_DIR" --api "$api" --api-port "$api_port")
  [ "$enable_linger" -eq 1 ] && svc_args+=(--enable-linger)
  svc_out="$(bash "$HOME_DIR/tools/solo-service.sh" "${svc_args[@]}" 2>&1)" || { printf '%s\n' "$svc_out" | tail -15; fail "solo-service.sh install"; }
  printf '%s\n' "$svc_out" | tail -8
  svc_state="$(printf '%s\n' "$svc_out" | grep '^SOLO SERVICE READY' | tail -1)"
  [ -n "$svc_state" ] || fail "solo-service.sh did not print 'SOLO SERVICE READY'"
else
  say "Not installing the service (--no-service).  Start SD with: $HOME_DIR/bin/sd -start"
  "$HOME_DIR/bin/sd" -start >/dev/null 2>&1 || true
fi

if [ "$ssh_wanted" -eq 1 ]; then
  say
  if ! systemctl is-active ssh >/dev/null 2>&1 && ! systemctl is-active sshd >/dev/null 2>&1; then
    warn "no ssh server is running.  Start one (as an administrator): sudo systemctl enable --now ssh   (or sshd)"
    [ "$managed" -eq 0 ] || warn "managed mode needs ssh reachable from the network"
  fi
  if [ -n "$ssh_key" ]; then
    bash "$HOME_DIR/tools/solo-ssh.sh" key-add "$HOME_DIR" "$ssh_key" | tail -2 || fail "solo-ssh.sh key-add"
  fi
  if [ "$ssh_match" -eq 1 ]; then
    bash "$HOME_DIR/tools/solo-ssh.sh" match "$HOME_DIR" --apply | tail -2 || fail "solo-ssh.sh match --apply"
  fi
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
chk="$(printf '%s\nWHO\nOFF\n' "$ACC_PW" | timeout 60 "$HOME_DIR/bin/sd" 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
printf '%s\n' "$chk" | grep -qE '^[0-9]+ sduser$' || { printf '%s\n' "$chk" | tail -5; fail "a session as sduser did not work"; }
say "  a session as sduser works"
rm -f "$HOME_DIR/\$internal"
gate="$(timeout 60 "$HOME_DIR/bin/sd" -internal WHO 2>&1 | sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\r//g')"
if printf '%s\n' "$gate" | grep -qE '^[0-9]+ sdsys$'; then fail "sd -internal was admitted with no marker: the internal door is OPEN"; fi
printf '%s\n' "$gate" | grep -qx 'Connection terminated' || fail "sd -internal did not end with 'Connection terminated'"
[ ! -e "$HOME_DIR/\$internal" ] || fail "a marker file was left in $HOME_DIR"
say "  sd -internal is closed"
ACC_PW=""; ADM_PW=""; GLB_PW=""

# ---------------------------------------------------------------- summary
say
say "SD Core for Linux Solo is installed."
say "  home          : $HOME_DIR      (mode: $mode_name)"
say "  start a session: sd            (the account is sduser; it asks for the account password)"
say "  administrator : type ADMIN     (the administrator password unlocks the administrator commands)"
say "  service       : ${svc_state:-not installed}"
[ "$api" = "off" ] || say "  API           : $api, port $api_port (TLS 1.3, account password)"
say "  uninstall     : bash $HOME_DIR/tools/deletesolo.sh"
say "  the download in $CLONE_DIR is removed when this script ends"
say
say "SOLO INSTALL COMPLETE $HOME_DIR"
