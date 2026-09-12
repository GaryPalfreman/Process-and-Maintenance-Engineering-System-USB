#!/bin/sh
set -eu
APP="${XDG_DATA_HOME:-$HOME/.local/share}/PMES-USB"
PY="$APP/.venv/bin/python"
if [ ! -x "$PY" ]; then
  printf '%s\n' 'Engineering System is not installed on this Linux computer.'
  printf '%s\n' 'Run install_local.py once on this computer first.'
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title='Engineering System not installed' --text='Run install_local.py once on this Linux computer before using this launcher.' || true
  fi
  exit 1
fi
cd "$APP"
exec "$PY" launch_local.py
