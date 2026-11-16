#!/bin/zsh
# Doppelklick im Finder startet die Test-Instanz. Beenden: Strg+C oder Fenster schließen.
cd "$(dirname "$0")/../.."
exec ../mcz-venv/bin/python devtools/testinstanz/start.py "$@"
