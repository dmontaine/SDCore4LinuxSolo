#!/bin/sh
# mkrc.sh - write the rc file the NANO verb starts nano with, so SD BASIC is highlighted.
#
#   sh mkrc.sh /path/to/sdbasic.nanorc /path/to/output.nanorc
#
# SD Core for Linux Solo writes nothing outside the user's home directory, so the
# multi-user installer's system-wide /usr/share/nano/sdbasic.nanorc is not available.
# nano has no per-user syntax directory it searches by itself, but it will read ONE rc
# file named by --rcfile - and that file REPLACES /etc/nanorc and ~/.nanorc.  So this
# writes an rc file that COPIES whichever of these exist, in nano's own order, and then
# includes SD's syntax:
#
#     /etc/nanorc
#     ~/.nanorc
#     ${XDG_CONFIG_HOME:-~/.config}/nano/nanorc
#     include "<sdsys>/nanocfg/sdbasic.nanorc"
#
# so the user's own settings (line numbers, tabs, colours) still apply.
#
# WHY COPIED AND NOT INCLUDED (measured 30 Sep 2026, nano 9.2): nano's manual says a file
# named by "include" must not itself contain set/unset or include commands, and /etc/nanorc
# holds both - "include"-ing it made nano start with "[ Mistakes in '/etc/nanorc' ]".  Only
# SD's own syntax file, which is nothing but colour rules, is included.
#
# Each copy is made only if the file is readable.  Silent on failure by design - a missing
# rc costs colour, never the ability to edit.  Called by gpl.bp/edit (place.syntax) before
# every nano session, so it heals after a move.

master="$1"
out="$2"
[ -n "$master" ] && [ -n "$out" ] || exit 0
[ -r "$master" ] || exit 0
tmp="$out.$$"
{
  for f in /etc/nanorc "$HOME/.nanorc" "${XDG_CONFIG_HOME:-$HOME/.config}/nano/nanorc"; do
    [ -r "$f" ] && cat "$f"
  done
  printf 'include "%s"\n' "$master"
} > "$tmp" 2>/dev/null && mv "$tmp" "$out" 2>/dev/null
rm -f "$tmp" 2>/dev/null
exit 0
