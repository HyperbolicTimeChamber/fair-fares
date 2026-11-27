#!/usr/bin/env sh
# Thin wrapper: uses Python 3 if present, else explains the alternative.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 install.py "$@"; fi
if command -v python >/dev/null 2>&1; then exec python install.py "$@"; fi
echo "Python 3 not found. Install it, or use: npx skills add <owner>/<repo>" >&2
exit 1
