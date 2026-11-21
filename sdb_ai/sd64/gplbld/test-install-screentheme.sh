#!/bin/bash
# S.293 (owner 21 Nov 26): a kept sd.conf keeps its SCREENTHEME exactly as it was.  Text check on solo-stage.sh:
# nothing writes a SCREENTHEME line into a kept file (no default_screentheme, no sed that inserts one), and the
# shipped sd.conf still says paper for a new install.  --selftest plants the old function and wants it refused.
here="$(cd "$(dirname "$0")" && pwd)"
stage="${STAGE:-$here/solo-stage.sh}"
shipped="$here/../sd.conf"
bad=0
check() {  # file
  local f="$1"
  [ -s "$f" ] || { echo "CANNOT RUN: $f is missing or empty"; return 2; }
  if grep -q -E 'default_screentheme|SCREENTHEME=paper/' "$f"; then return 1; fi
  return 0
}
if [ "${1:-}" = "--selftest" ]; then
  tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
  cp "$stage" "$tmp"; echo 'default_screentheme() { sed -i "s/x/SCREENTHEME=paper/" "$1"; }' >> "$tmp"
  check "$tmp"; r=$?
  if [ "$r" -eq 1 ]; then echo "PASS mutant (the old step) refused"; else echo "FAIL mutant not refused ($r)"; exit 1; fi
  exit 0
fi
check "$stage"; r=$?
case "$r" in
  0) echo "PASS solo-stage.sh adds no SCREENTHEME line to a kept sd.conf" ;;
  1) echo "FAIL solo-stage.sh still adds SCREENTHEME to a kept sd.conf"; bad=1 ;;
  *) exit 2 ;;
esac
if grep -q '^SCREENTHEME=paper$' "$shipped"; then echo "PASS the shipped sd.conf says paper"; else echo "FAIL the shipped sd.conf lacks SCREENTHEME=paper"; bad=1; fi
[ "$bad" -eq 0 ] && echo "2 passed, 0 failed" || echo "FAILED"
exit "$bad"
