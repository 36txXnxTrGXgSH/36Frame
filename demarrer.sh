#!/bin/sh
# Lance 36Frame sous Linux : ./demarrer.sh [image | dossier]
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements.txt; }
exec .venv/bin/python -m frame36 "$@"
